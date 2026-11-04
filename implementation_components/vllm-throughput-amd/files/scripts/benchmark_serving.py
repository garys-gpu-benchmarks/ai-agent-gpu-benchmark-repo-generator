#!/usr/bin/env python3
# File: scripts/benchmark_serving.py
# Description: Concurrent synthetic-prompt client for AMD vLLM throughput/latency.
from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

def _f6(value) -> str:
    return "" if value is None or value == "" else f"{float(value):.6f}"


METRIC_COLUMNS = [
    "output_token_throughput_tokens_s",
    "tokens_per_sec",
    "time_to_first_token_p50_ms",
    "ttft_p50_ms",
    "time_per_output_token_p50_ms",
    "tpot_p50_ms",
    "inter_token_latency_itl_p50_ms",
    "itl_p50_ms",
        "end_to_end_request_latency_ms",
    "e2e_ms",
    "output_token_throughput_tokens_sec",
    "ttft_p50_msec",
    "time_per_output_token_tpot_p50_msec",
    "inter_token_latency_itl_p50_msec",
    "end_to_end_request_latency_msec",
]
MISTRAL_MAX_MODEL_LEN = 32768
TOKENIZER_BOS_SLACK = 16


def finite_nonneg(value: float) -> float:
    parsed = float(value)
    if parsed != parsed or parsed < 0.0:
        return 0.0
    return parsed


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return finite_nonneg(ordered[index])


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
def record_stream_choice(
    choice: dict,
    now: float,
    token_times: list[float],
    ambiguous_sizes: list[int],
) -> tuple[int, bool, float | None]:
    """Count logprob tokens in one SSE choice and stamp inter-token times.

    A usage-only event has neither text nor logprob tokens. Empty incremental
    text with one logprob token is still one output token. N>1 logprob tokens
    are one engine step; split the gap from the previous stamp into N samples.
    Text with zero logprob tokens stays ambiguous and fails the request.
    """
    text = choice.get("text") or ""
    tokens = ((choice.get("logprobs") or {}).get("tokens")) or []
    count = len(tokens)
    if count == 0 and not text:
        return 0, True, None
    if count == 0:
        ambiguous_sizes.append(0)
        return 0, False, None
    if count == 1:
        token_times.append(now)
        return 1, True, now
    if token_times:
        previous = token_times[-1]
        stamps = [previous + step * (now - previous) / count for step in range(1, count + 1)]
    else:
        stamps = [now] * count
    token_times.extend(stamps)
    return count, True, stamps[0]


def one_request(url: str, model_name: str, input_len: int, output_len: int) -> dict:
    prompt = ("token " * input_len).strip()
    payload = json.dumps({
        "model": model_name,
        "prompt": prompt,
        "max_tokens": output_len,
        "temperature": 0,
        "stream": True,
        "logprobs": 1,
        # Ask for the final count. One logprob token is one sample; N tokens in
        # one chunk are split across the gap so the count still matches usage.
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
    ambiguous_sizes: list[int] = []
    timed_tokens = 0
    token_timing_valid = True
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
                choice = choices[0] if choices else {}
                now = time.perf_counter()
                added, ok, first_stamp = record_stream_choice(choice, now, token_times, ambiguous_sizes)
                if not ok:
                    token_timing_valid = False
                if added and first_token_time is None and first_stamp is not None:
                    first_token_time = first_stamp
                timed_tokens += added
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"[FAIL] HTTP {exc.code} from {url}: {detail[:800]}") from exc
    end = time.perf_counter()
    elapsed_ms = (end - start) * 1000.0
    if first_token_time is None:
        first_token_time = end
    ttft_ms = (first_token_time - start) * 1000.0
    out_tokens = usage_tokens or timed_tokens or output_len
    if not token_timing_valid or timed_tokens != out_tokens:
        detail = f"[FAIL] cannot map SSE chunks to output tokens: timed={timed_tokens} usage={out_tokens}"
        if ambiguous_sizes:
            detail += " chunk_sizes=" + ",".join(str(size) for size in ambiguous_sizes)
        raise SystemExit(detail)
    # TPOT: decode time after the first token / tokens after the first (was / all tokens).
    tpot_ms = max(0.0, elapsed_ms - ttft_ms) / max(1, out_tokens - 1)
    gaps_ms = [(token_times[i] - token_times[i - 1]) * 1000.0 for i in range(1, len(token_times))]
    itl_ms = sum(gaps_ms) / len(gaps_ms) if gaps_ms else ""
    return {
        "ttft_ms": finite_nonneg(ttft_ms),
        "tpot_ms": finite_nonneg(tpot_ms),
        "itl_ms": itl_ms if itl_ms == "" else finite_nonneg(itl_ms),
        "e2e_ms": finite_nonneg(elapsed_ms),
        "gaps_ms": gaps_ms,
        "out_tokens": out_tokens,
    }


def run_sweep(args, output_len: int) -> dict[str, float]:
    url = args.base_url.rstrip("/") + "/v1/completions"
    one_request(
        url,
        args.model_name,
        int(float(args.input_len)),
        min(output_len, 4),
    )
    started = time.perf_counter()
    results = []
    n_prompts = max(1, int(float(args.max_num_seqs)))
    workers = max(1, int(float(args.max_concurrency)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [
            pool.submit(one_request, url, args.model_name, int(float(args.input_len)), output_len)
            for _ in range(n_prompts)
        ]
        for fut in as_completed(futs):
            results.append(fut.result())
    wall = time.perf_counter() - started
    out_tokens = sum(item["out_tokens"] for item in results)
    tokens_per_sec = finite_nonneg(out_tokens / wall) if wall > 0 else 0.0
    ttfts = [item["ttft_ms"] for item in results]
    tpots = [item["tpot_ms"] for item in results]
    # ITL percentile over every inter-token gap of every request (not over per-request means).
    itls = [gap for item in results for gap in item["gaps_ms"]]
    e2e = percentile([item["e2e_ms"] for item in results], 50.0)
    ttft_p50 = percentile(ttfts, 50.0)
    tpot_p50 = percentile(tpots, 50.0)
    itl_p50 = percentile(itls, 50.0) if itls else ""
    metrics = {
        "output_token_throughput_tokens_s": tokens_per_sec,
        "tokens_per_sec": tokens_per_sec,
        "time_to_first_token_p50_ms": ttft_p50,
        "ttft_p50_ms": ttft_p50,
        "time_per_output_token_p50_ms": tpot_p50,
        "tpot_p50_ms": tpot_p50,
        "inter_token_latency_itl_p50_ms": itl_p50,
        "itl_p50_ms": itl_p50,
        "end_to_end_request_latency_ms": e2e,
        "e2e_ms": e2e,
        "output_token_throughput_tokens_sec": tokens_per_sec,
        "ttft_p50_msec": ttft_p50,
        "time_per_output_token_tpot_p50_msec": tpot_p50,
        "inter_token_latency_itl_p50_msec": itl_p50,
        "end_to_end_request_latency_msec": e2e,
        "concurrency": float(args.max_concurrency),
    }
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(description="Concurrent vLLM throughput client")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--raw-file", default="")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--model-name", default="mistralai/Mistral-7B-v0.3")
    parser.add_argument("--dtype", default="bfloat16")
    parser.add_argument("--tensor-parallel-size", default="1")
    parser.add_argument("--gpu-memory-utilization", default="0.9")
    parser.add_argument("--prompt-source", default="synthetic")
    parser.add_argument("--input-len", default="64")
    parser.add_argument("--output-len", default="16")
    parser.add_argument("--max-model-len", default=str(MISTRAL_MAX_MODEL_LEN))
    parser.add_argument("--max-num-seqs", default="2")
    parser.add_argument("--max-concurrency", default="2")
    parser.add_argument("--output-format", default="csv")
    args = parser.parse_args()
    if str(args.prompt_source).lower() not in ("synthetic", "true", "yes"):
        raise SystemExit("[FAIL] prompt_source must remain synthetic")
    output_len = clamp_max_tokens(int(float(args.input_len)), int(float(args.output_len)), int(float(args.max_model_len)))
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    texts = ["concurrency,tokens_per_sec,ttft_p50_ms,tpot_p50_ms,itl_p50_ms,e2e_ms"]
    for _repeat in range(2):
        metrics = run_sweep(args, output_len)
        rows.append({"sample_index": len(rows), "status": "ok", **{key: metrics[key] for key in METRIC_COLUMNS}, "error_message": ""})
        texts.append(
            f"{int(metrics['concurrency'])},{metrics['output_token_throughput_tokens_s']:.6f},"
            f"{metrics['time_to_first_token_p50_ms']:.6f},{metrics['time_per_output_token_p50_ms']:.6f},"
            f"{_f6(metrics['inter_token_latency_itl_p50_ms'])},{metrics['end_to_end_request_latency_ms']:.6f}"
        )
    csv_path = run_dir / "raw_results.csv"
    fieldnames = ["sample_index", "status", *METRIC_COLUMNS, "error_message"]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    raw_text = "\n".join(texts) + "\n" + csv_path.read_text(encoding="utf-8")
    Path(args.raw_file or (run_dir / "raw_output.txt")).write_text(raw_text, encoding="utf-8", newline="\n")
    print(f"[PASS] collected {len(rows)} throughput/latency samples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
