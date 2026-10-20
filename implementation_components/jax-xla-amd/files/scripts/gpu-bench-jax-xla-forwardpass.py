#!/usr/bin/env python3
"""JAX/XLA transformer forward pass on synthetic tokens (AMD 126/326 and NVIDIA 226/426).

Each layer: Q/K/V/O projections, softmax attention over the whole hidden size
(num_heads only sets head_dim x num_heads = hidden), and a GELU MLP (hidden ->
2*hidden -> hidden); then an output projection to the vocabulary."""

from __future__ import annotations

import argparse
import math
import subprocess
import sys
import time

import jax
import jax.numpy as jnp
from jax import random


PROFILE_BUDGET_S = {"smoke": 60.0, "baseline": 120.0, "extended": 330.0}
STEP_CHUNK = 64


def nvidia_vram_used_gb():
    """Used VRAM in GB from nvidia-smi, or "" when unavailable."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    lines = [line.strip() for line in (out.stdout or "").splitlines() if line.strip()]
    if not lines:
        return ""
    try:
        # nvidia-smi nounits memory.used is MiB. The metric is decimal GB (the JAX path
        # divides bytes by 1e9); dividing by 1024 gave GiB under a GB label.
        return float(lines[0].split()[0]) * 1024**2 / 1e9
    except (ValueError, IndexError):
        return ""


def amd_vram_used_gb() -> str:
    """Peak-or-used VRAM in GB when JAX memory_stats has no peak_bytes_in_use."""
    for cmd in (
        ["amd-smi", "metric"],
    ):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        except (OSError, subprocess.TimeoutExpired):
            continue
        for line in ((out.stdout or "") + "\n" + (out.stderr or "")).splitlines():
            low = line.lower()
            if "used" not in low or ("vram" not in low and "memory" not in low):
                continue
            nums = []
            for tok in line.replace(":", " ").replace(",", " ").split():
                try:
                    nums.append(float(tok))
                except ValueError:
                    continue
            if not nums:
                continue
            value = nums[-1]
            if value > 1_000_000:
                return value / 1e9
            if "mib" in low or "mb" in low:
                return value / 1024.0
            return value
    return ""


def gpu_vram_used_gb():
    """Used VRAM in GB when JAX memory_stats has no peak_bytes_in_use: nvidia-smi
    (226/426) or amd-smi (126/326). "" when neither reports it."""
    value = nvidia_vram_used_gb()
    return value if value != "" else amd_vram_used_gb()


def profile_budget_s(profile: str) -> float:
    return PROFILE_BUDGET_S.get(str(profile or "").strip().lower(), 300.0)


def run_bounded(step_chunk, total: int, profile: str) -> tuple[float, int]:
    """Run up to total iterations, in chunks, and stop at the profile budget."""
    limit = profile_budget_s(profile)
    done = 0
    start = time.perf_counter()
    while done < total:
        if done and (time.perf_counter() - start) >= limit:
            break
        n = min(STEP_CHUNK, total - done)
        step_chunk(n)
        done += n
    elapsed = max(time.perf_counter() - start, 1e-9)
    if done < total:
        print(
            f"[WARN] stopped after {done} of {total} iterations at the {profile} "
            f"budget of {limit:.0f}s",
            file=sys.stderr,
        )
    return elapsed, done


def finite_nonneg(value: float) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0.0:
        return 0.0
    return parsed


def token_on(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "on"}


def parse_dtype(text: str):
    token = str(text).strip().lower()
    if token in {"fp16", "f16", "float16"}:
        return jnp.float16
    if token in {"bf16", "bfloat16"}:
        return jnp.bfloat16
    return jnp.float32


def transformer_apply(params, tokens, dtype):
    embed = params["embed"][tokens].astype(dtype)
    x = embed
    for layer in params["layers"]:
        q = x @ layer["wq"]
        k = x @ layer["wk"]
        v = x @ layer["wv"]
        scale = jnp.sqrt(jnp.array(q.shape[-1], dtype=dtype))
        attn = jax.nn.softmax((q @ jnp.swapaxes(k, -1, -2)) / scale, axis=-1) @ v
        x = x + attn @ layer["wo"]
        h = jax.nn.gelu(x @ layer["w1"])
        x = x + h @ layer["w2"]
    return x @ params["lm"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device-id", default="0")
    parser.add_argument("--dtype", default="FP16")
    parser.add_argument("--model-config", default="true")
    parser.add_argument("--activation-fn", default="true")
    parser.add_argument("--vocab-size", default="true")
    parser.add_argument("--sequence-len", default="16")
    parser.add_argument("--hidden-size", default="64")
    parser.add_argument("--num-layers", default="1")
    parser.add_argument("--num-heads", default="4")
    parser.add_argument("--head-dim", default="true")
    parser.add_argument("--batch-size", default="1")
    parser.add_argument("--warmup-iters", default="1")
    parser.add_argument("--num-iterations", default="3")
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--seed", default="42")
    args = parser.parse_args()
    if not token_on(args.model_config):
        raise SystemExit("[FAIL] model_config token must remain enabled.")
    devices = jax.devices("gpu")
    if not devices:
        raise SystemExit("[FAIL] JAX did not see a GPU.")
    dtype = parse_dtype(args.dtype)
    seq = max(4, int(float(args.sequence_len)))
    hidden = max(8, int(float(args.hidden_size)))
    layers_n = max(1, int(float(args.num_layers)))
    heads = max(1, int(float(args.num_heads)))
    head_dim = hidden // heads if token_on(args.head_dim) else max(4, int(float(args.head_dim)))
    hidden = heads * head_dim
    batch = max(1, int(float(args.batch_size)))
    vocab = 128 if token_on(args.vocab_size) else max(8, int(float(args.vocab_size)))
    warmup = max(0, int(float(args.warmup_iters)))
    iters = max(1, int(float(args.num_iterations)))
    key = random.PRNGKey(int(float(args.seed)))
    keys = random.split(key, 3 + layers_n * 6)
    params = {
        "embed": random.normal(keys[0], (vocab, hidden), dtype=dtype),
        "lm": random.normal(keys[1], (hidden, vocab), dtype=dtype),
        "layers": [],
    }
    cursor = 2
    for _ in range(layers_n):
        params["layers"].append(
            {
                "wq": random.normal(keys[cursor], (hidden, hidden), dtype=dtype),
                "wk": random.normal(keys[cursor + 1], (hidden, hidden), dtype=dtype),
                "wv": random.normal(keys[cursor + 2], (hidden, hidden), dtype=dtype),
                "wo": random.normal(keys[cursor + 3], (hidden, hidden), dtype=dtype),
                "w1": random.normal(keys[cursor + 4], (hidden, hidden * 2), dtype=dtype),
                "w2": random.normal(keys[cursor + 5], (hidden * 2, hidden), dtype=dtype),
            }
        )
        cursor += 6
    tokens = random.randint(keys[-1], (batch, seq), 0, vocab)
    compiled = jax.jit(lambda p, t: transformer_apply(p, t, dtype))
    lowered = compiled.lower(params, tokens)
    t0 = time.perf_counter()
    executable = lowered.compile()
    compile_ms = finite_nonneg((time.perf_counter() - t0) * 1000.0)
    out = executable(params, tokens)
    out.block_until_ready()
    for _ in range(warmup):
        compiled(params, tokens).block_until_ready()
    chunk_fns = {}

    def step_chunk(n, _params=params, _tokens=tokens):
        fn = chunk_fns.get(n)
        if fn is None:
            def fn(p, t, _n=n):
                def body(_, _y):
                    return transformer_apply(p, t, dtype)
                seed = jnp.zeros((t.shape[0], t.shape[1], p["lm"].shape[1]), dtype=dtype)
                return jax.lax.fori_loop(0, _n, body, seed)
            fn = jax.jit(fn)
            chunk_fns[n] = fn
        fn(_params, _tokens).block_until_ready()

    # Compile each chunk size before timing. The first call of a chunk size used
    # to JIT-compile inside the timed window, which dominated short runs.
    for size in sorted({min(STEP_CHUNK, iters), iters % STEP_CHUNK} - {0}):
        step_chunk(size)
    elapsed, completed = run_bounded(step_chunk, iters, args.profile)
    if completed <= 0:
        raise SystemExit("[FAIL] JAX XLA forward pass completed no iterations.")
    per_iter = elapsed / completed
    latency_ms = finite_nonneg(per_iter * 1000.0)
    tokens_per_sec = finite_nonneg(float(batch * seq) / per_iter) if elapsed else 0.0
    flops = 2.0 * float(layers_n) * (
        4.0 * batch * seq * hidden * hidden + 2.0 * batch * seq * seq * hidden + 4.0 * batch * seq * hidden * hidden
    )
    # Output projection to the vocabulary (x @ params["lm"]), once per pass.
    flops += 2.0 * batch * seq * hidden * vocab
    tflops = finite_nonneg(flops / per_iter / 1e12) if elapsed else 0.0
    try:
        peak = finite_nonneg(float(jax.local_devices()[0].memory_stats()["peak_bytes_in_use"]) / 1e9)
    except Exception:
        peak = gpu_vram_used_gb()
    # No number from JAX or the vendor tool: report the reason, not a guess (it
    # used to write the output tensor size + 0.01 GB).
    if peak == "":
        print("PEAK_NA reason=na (peak memory not reported)")
        peak_text = "na"
    else:
        peak_text = f"{finite_nonneg(float(peak)):.6f}"
    print(
        "RESULT"
        f" dtype={args.dtype}"
        f" sequence_len={seq}"
        f" hidden_size={hidden}"
        f" num_layers={layers_n}"
        f" batch_size={batch}"
        f" forward_latency_msec={latency_ms:.6f}"
        f" tokens_per_sec={tokens_per_sec:.6f}"
        f" tflops={tflops:.6f}"
        " tflops_method=modeled_from_transformer_operation_count"
        f" jit_compile_msec={compile_ms:.6f}"
        f" requested_iterations={iters}"
        f" completed_iterations={completed}"
        f" peak_hbm_gb={peak_text}"
        " status=ok"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
