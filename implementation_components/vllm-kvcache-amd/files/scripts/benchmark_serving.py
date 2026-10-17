#!/usr/bin/env python3
# File: scripts/benchmark_serving.py
# Description: Concurrent synthetic-prompt client for AMD vLLM KV-cache stress.
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from statistics import median

NA_KV = "na (server reported no KV-cache usage)"
NA_KV_NO_BYTES = "na (server reported a percent and no byte count)"
_USAGE_RE = re.compile(r"GPU KV cache usage:\s*([0-9.]+)\s*%")
_CAP_RE = re.compile(r"Available KV cache memory:\s*([0-9.]+)\s*GiB")


def _f6(value) -> str:
    """6-decimal text for a number; an "na (...)" reason unchanged; blank otherwise."""
    if value is None or value == "":
        return ""
    if str(value).startswith("na ("):
        return str(value)
    return f"{float(value):.6f}"


METRIC_COLUMNS = [
    "sustained_decode_throughput_under_cache_pressure_tokens_s",
    "time_to_first_token_ms",
    "time_per_output_token_under_high_kv_pressure_ms",
    "kv_cache_hbm_usage_gb",
    "kv_cache_hbm_capacity_utilization",
]
TOKENIZER_BOS_SLACK = 16
GIB = 1024 ** 3
KV_SAMPLE_INTERVAL_S = 0.05


def finite_nonneg(value: float) -> float:
    parsed = float(value)
    if parsed != parsed or parsed < 0.0:
        return 0.0
    return parsed


def clamp_max_tokens(input_len: int, output_len: int, max_model_len: int) -> int:
    room = max(1, int(max_model_len) - max(1, int(input_len)) - TOKENIZER_BOS_SLACK)
    requested = max(1, int(output_len))
    clamped = min(requested, room)
    if clamped != requested:
        print(
            f"[INFO] clamped max_tokens {requested} -> {clamped} "
            f"(input_len={input_len} max_model_len={max_model_len} bos_slack={TOKENIZER_BOS_SLACK})",
            flush=True,
        )
    return clamped


# Streaming fix (2026-09-06): the previous version made a single blocking
# non-streaming request and derived TTFT/ITL by reusing the same elapsed-time
# number (or, on NVIDIA, an arbitrary *0.4 fudge factor) -- neither was a real
# per-token measurement. This version streams the completion (stream=true) and
# times the arrival of each token chunk, so ttft_ms is genuinely time-to-first-
# token and itl_ms/tpot_ms is a genuine mean inter-token gap, independent of e2e.
def one_request(url: str, model_name: str, input_len: int, output_len: int, seed: int) -> dict:
    prompt = f"request {seed} " + ("token " * max(1, input_len)).strip()
    payload = json.dumps({
        "model": model_name,
        "prompt": prompt,
        "max_tokens": output_len,
        "temperature": 0,
        "seed": seed,
        "stream": True,
        # Ask for the token count in the final chunk; a chunk can carry several tokens.
        "stream_options": {"include_usage": True},
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    )
    start = time.perf_counter()
    first_token_time = None
    token_times: list[float] = []
    stream_out_tokens = 0
    usage_tokens = None
    try:
        with urllib.request.urlopen(req, timeout=3600) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                usage = chunk.get("usage") or {}
                if usage.get("completion_tokens"):
                    usage_tokens = int(usage["completion_tokens"])
                choices = chunk.get("choices") or []
                text = choices[0].get("text", "") if choices else ""
                if not text:
                    continue
                now = time.perf_counter()
                if first_token_time is None:
                    first_token_time = now
                token_times.append(now)
                stream_out_tokens += 1
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"[FAIL] HTTP {exc.code} from {url}: {detail[:800]}") from exc
    end = time.perf_counter()
    elapsed_ms = (end - start) * 1000.0
    if first_token_time is None:
        first_token_time = end
    ttft_ms = (first_token_time - start) * 1000.0
    # Output tokens: the server's own count (stream_options usage) when given,
    # else the number of text chunks, else the requested length.
    out_tokens = usage_tokens or stream_out_tokens or output_len
    # TPOT, standard definition: decode time after the first token divided by the
    # tokens after the first. (It used to be the mean gap between stream chunks,
    # which is per chunk, not per token, and fell back to the whole post-TTFT
    # time when fewer than two chunks arrived.)
    tpot_ms = max(0.0, elapsed_ms - ttft_ms) / max(out_tokens - 1, 1)
    return {
        "ttft_ms": finite_nonneg(ttft_ms),
        "tpot_ms": finite_nonneg(tpot_ms),
        "decode_ms": finite_nonneg(max(0.0, elapsed_ms - ttft_ms)),
        "out_tokens": out_tokens,
        "first_token_at": first_token_time,
        "completed_at": end,
    }


def _prometheus_gauge(text: str, name: str) -> float | None:
    values = []
    for line in text.splitlines():
        if not line or line.startswith("#") or not line.startswith(name):
            continue
        try:
            values.append(float(line.split()[-1]))
        except ValueError:
            continue
    return max(values) if values else None


def kv_stats(base_url: str, gpu_util: float, max_model_len: int) -> tuple[float, float]:
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/metrics", timeout=5) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, ValueError):
        return "", ""
    util = _prometheus_gauge(text, "vllm:kv_cache_usage_perc")
    if util is None:
        util = _prometheus_gauge(text, "vllm:gpu_cache_usage_perc")
    util_pct = ""
    if util is not None and 0.0 <= util <= 1.0:
        util_pct = util * 100.0
    gb = _prometheus_gauge(text, "vllm:kv_cache_usage_bytes")
    if gb is None:
        gb = _prometheus_gauge(text, "vllm:gpu_cache_usage_bytes")
    # GiB (1024^3), the unit vLLM uses for KV cache memory; this used to divide by 1e9.
    gb_value = "" if gb is None else gb / GIB
    return gb_value, util_pct


def resolve_kv_gb(byte_gb, peak_pct, capacity_gib):
    """Byte gauge when the server exports one. Otherwise percent times the
    logged KV capacity. A percent with neither bytes nor a capacity line
    keeps an na reason instead of claiming the server reported no usage."""
    if byte_gb != "" and byte_gb is not None:
        return byte_gb
    if peak_pct != "" and peak_pct is not None and capacity_gib:
        return (float(peak_pct) / 100.0) * float(capacity_gib)
    if peak_pct != "" and peak_pct is not None:
        return NA_KV_NO_BYTES
    return NA_KV


def read_kv_log(log_path: Path, char_offset: int) -> tuple[float | None, list[float], int]:
    """Capacity from the whole log. Usage percents from text written after char_offset."""
    if not log_path.is_file():
        return None, [], char_offset
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, [], char_offset
    capacity = None
    for match in _CAP_RE.finditer(text):
        try:
            capacity = float(match.group(1))
        except ValueError:
            continue
    percents = []
    for match in _USAGE_RE.finditer(text[char_offset:]):
        try:
            percents.append(float(match.group(1)))
        except ValueError:
            continue
    return capacity, percents, len(text)


def _device_vram_gb() -> float:
    for cmd in (
        ["rocm-smi", "--showmeminfo", "vram"],
        ["/opt/rocm/bin/rocm-smi", "--showmeminfo", "vram"],
        ["amd-smi", "metric"],
        ["/opt/rocm/bin/amd-smi", "metric"],
        ["amd-smi", "static"],
        ["/opt/rocm/bin/amd-smi", "static"],
    ):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        except (OSError, subprocess.TimeoutExpired):
            continue
        for line in ((out.stdout or "") + "\n" + (out.stderr or "")).splitlines():
            low = line.lower()
            if "total" not in low or ("vram" not in low and "memory" not in low):
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
                return value / GIB
            if "mib" in low or "mb" in low:
                return value / 1024.0
            return value
    return 0.0


def decode_window_throughput(results: list[dict]) -> float:
    decoded_tokens = sum(max(int(item["out_tokens"]) - 1, 0) for item in results)
    if decoded_tokens <= 0 or not results:
        return 0.0
    decode_start = min(float(item["first_token_at"]) for item in results)
    decode_end = max(float(item["completed_at"]) for item in results)
    decode_seconds = decode_end - decode_start
    return finite_nonneg(decoded_tokens / decode_seconds) if decode_seconds > 0 else 0.0


def require_kv_metrics(kv_gb, kv_pct) -> tuple[float, float]:
    try:
        gb_value = float(kv_gb)
        pct_value = float(kv_pct)
    except (TypeError, ValueError) as exc:
        raise SystemExit("[FAIL] real vLLM exposed no usable KV-cache occupancy telemetry") from exc
    if gb_value <= 0 or not (0 < pct_value <= 100):
        raise SystemExit(
            f"[FAIL] invalid KV-cache occupancy telemetry: {gb_value} GiB, {pct_value}%"
        )
    return gb_value, pct_value


def run_sweep(args, output_len: int) -> dict[str, float]:
    url = args.base_url.rstrip("/") + "/v1/completions"
    one_request(
        url,
        args.model_name,
        int(float(args.input_len)),
        output_len,
        int(float(args.seed)) - 1,
    )
    results = []
    stop_sample = threading.Event()
    peak = {"byte_gb": "", "pct": ""}
    capacity = {"gib": None}
    log_path = Path(args.run_dir) / "server.log"
    log_state = {"offset": 0}
    if log_path.is_file():
        try:
            log_state["offset"] = len(log_path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            log_state["offset"] = 0

    def _note_pct(pct_f: float) -> None:
        if pct_f > 0 and (peak["pct"] == "" or pct_f > float(peak["pct"])):
            peak["pct"] = pct_f

    def _note_byte_gb(gb_f: float) -> None:
        if gb_f > 0 and (peak["byte_gb"] == "" or gb_f > float(peak["byte_gb"])):
            peak["byte_gb"] = gb_f

    def _apply_log() -> None:
        cap, percents, log_state["offset"] = read_kv_log(log_path, log_state["offset"])
        if cap:
            capacity["gib"] = cap
        for logged in percents:
            _note_pct(logged)

    def _sample() -> None:
        while not stop_sample.is_set():
            gb, pct = kv_stats(args.base_url, float(args.gpu_memory_utilization), int(float(args.max_model_len)))
            if pct != "":
                try:
                    _note_pct(float(pct))
                except (TypeError, ValueError):
                    pass
            if gb != "":
                try:
                    _note_byte_gb(float(gb))
                except (TypeError, ValueError):
                    pass
            _apply_log()
            stop_sample.wait(KV_SAMPLE_INTERVAL_S)

    sampler = threading.Thread(target=_sample, daemon=True)
    sampler.start()
    try:
        with ThreadPoolExecutor(max_workers=max(1, int(float(args.concurrency)))) as pool:
            futs = [
                pool.submit(
                    one_request,
                    url,
                    args.model_name,
                    int(float(args.input_len)),
                    output_len,
                    int(float(args.seed)) + index,
                )
                for index in range(int(float(args.num_prompts)))
            ]
            for fut in as_completed(futs):
                results.append(fut.result())
    finally:
        stop_sample.set()
        sampler.join(timeout=2)
        _apply_log()
    tokens_per_sec = decode_window_throughput(results)
    ttft = finite_nonneg(median(item["ttft_ms"] for item in results))
    tpot = finite_nonneg(median(item["tpot_ms"] for item in results))
    kv_gb = resolve_kv_gb(peak["byte_gb"], peak["pct"], capacity["gib"])
    kv_pct = peak["pct"] if peak["pct"] != "" else NA_KV
    kv_gb, kv_pct = require_kv_metrics(kv_gb, kv_pct)
    return {
        METRIC_COLUMNS[0]: tokens_per_sec,
        METRIC_COLUMNS[1]: ttft,
        METRIC_COLUMNS[2]: tpot,
        METRIC_COLUMNS[3]: kv_gb,
        METRIC_COLUMNS[4]: kv_pct,
        "concurrency": float(args.concurrency),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Concurrent KV-cache serving client")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--raw-file", default="")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--model-name", default="mistralai/Mistral-7B-v0.3")
    parser.add_argument("--dtype", default="bfloat16")
    parser.add_argument("--kv-cache-dtype", default="auto")
    parser.add_argument("--gpu-memory-utilization", default="0.9")
    parser.add_argument("--max-model-len", default="8192")
    parser.add_argument("--input-len", default="64")
    parser.add_argument("--output-len", default="16")
    parser.add_argument("--num-prompts", default="2")
    parser.add_argument("--concurrency", default="2")
    parser.add_argument("--seed", default="0")
    parser.add_argument("--output-format", default="csv")
    args = parser.parse_args()
    output_len = clamp_max_tokens(
        int(float(args.input_len)),
        int(float(args.output_len)),
        int(float(args.max_model_len)),
    )
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    texts = ["concurrency,tokens_per_sec,ttft_ms,tpot_ms,kv_cache_gb,kv_util_percent"]
    for _repeat in range(2):
        metrics = run_sweep(args, output_len)
        aliases = {
            "tokens_per_sec": metrics[METRIC_COLUMNS[0]],
            "decode_tokens_per_sec": metrics[METRIC_COLUMNS[0]],
            "output_tokens_per_sec": metrics[METRIC_COLUMNS[0]],
            "ttft_ms": metrics[METRIC_COLUMNS[1]],
            "ttft_msec": metrics[METRIC_COLUMNS[1]],
            "tpot_ms": metrics[METRIC_COLUMNS[2]],
            "tpot_at_measured_kv_occupancy_ms": metrics[METRIC_COLUMNS[2]],
            "tpot_msec": metrics[METRIC_COLUMNS[2]],
            "kv_cache_gb": metrics[METRIC_COLUMNS[3]],
            "kv_cache_peak_gb": metrics[METRIC_COLUMNS[3]],
            "kv_util_percent": metrics[METRIC_COLUMNS[4]],
            "kv_cache_usage_peak_pct": metrics[METRIC_COLUMNS[4]],
        }
        rows.append({
            "sample_index": len(rows),
            "status": "ok",
            **{key: metrics[key] for key in METRIC_COLUMNS},
            **aliases,
            "error_message": "",
        })
        texts.append(
            f"{int(metrics['concurrency'])},{metrics[METRIC_COLUMNS[0]]:.6f},{metrics[METRIC_COLUMNS[1]]:.6f},"
            f"{metrics[METRIC_COLUMNS[2]]:.6f},{_f6(metrics[METRIC_COLUMNS[3]])},{_f6(metrics[METRIC_COLUMNS[4]])}"
        )
    csv_path = run_dir / "raw_results.csv"
    fieldnames = [
        "sample_index", "status", *METRIC_COLUMNS,
        "tokens_per_sec", "decode_tokens_per_sec", "output_tokens_per_sec", "ttft_ms", "ttft_msec", "tpot_ms",
        "tpot_at_measured_kv_occupancy_ms", "tpot_msec", "kv_cache_gb", "kv_cache_peak_gb",
        "kv_util_percent", "kv_cache_usage_peak_pct",
        "error_message",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    raw_text = "\n".join(texts) + "\n" + csv_path.read_text(encoding="utf-8")
    Path(args.raw_file or (run_dir / "raw_output.txt")).write_text(raw_text, encoding="utf-8", newline="\n")
    print(f"[PASS] collected {len(rows)} KV-cache serving samples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
