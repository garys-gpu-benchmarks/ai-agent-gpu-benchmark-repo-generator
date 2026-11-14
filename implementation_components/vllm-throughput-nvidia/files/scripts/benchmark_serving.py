#!/usr/bin/env python3
"""HTTP prompt-serving client for vLLM throughput/latency.

Honor workbook --num-prompts / --max-num-seqs. Do not set
num_prompts = max(2, concurrency). Use the real --model-name, not tiny-kv.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

MISTRAL_MAX_MODEL_LEN = 32768
TOKENIZER_BOS_SLACK = 16

METRIC_KEYS = (
    "output_token_throughput_tokens_sec",
    "ttft_p50_msec",
    "ttft_p95_msec",
    "ttft_p99_msec",
    "time_per_output_token_tpot_p50_msec",
    "time_per_output_token_tpot_p95_msec",
    "time_per_output_token_tpot_p99_msec",
    "inter_token_latency_itl_p50_msec",
    "inter_token_latency_itl_p95_msec",
    "inter_token_latency_itl_p99_msec",
    "end_to_end_request_latency_msec",
)


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round(p * (len(ordered) - 1)))))
    return ordered[idx]


def as_int(raw: object, fallback: int) -> int:
    try:
        if str(raw).lower() in {"", "true", "yes", "none"}:
            return fallback
        return max(1, int(float(raw)))
    except (TypeError, ValueError):
        return fallback


def clamp_max_tokens(input_len: int, output_len: int, max_model_len: int = MISTRAL_MAX_MODEL_LEN) -> int:
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
    tpot_ms = max(0.0, elapsed_ms - ttft_ms) / max(1, out_tokens - 1)
    gaps_ms = [(token_times[i] - token_times[i - 1]) * 1000.0 for i in range(1, len(token_times))]
    itl_ms = sum(gaps_ms) / len(gaps_ms) if gaps_ms else ""
    return {"e2e_ms": elapsed_ms, "ttft_ms": ttft_ms, "tpot_ms": tpot_ms, "itl_ms": itl_ms,
            "gaps_ms": gaps_ms, "out_tokens": out_tokens}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
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
    parser.add_argument("--num-prompts", default="")
    parser.add_argument("--request-rate", default="true")
    parser.add_argument("--output-format", default="csv")
    args = parser.parse_args()
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    concurrency = as_int(args.max_concurrency, 2)
    num_prompts = as_int(args.num_prompts, as_int(args.max_num_seqs, concurrency))
    output_len = clamp_max_tokens(int(args.input_len), int(args.output_len), max_model_len=as_int(args.max_model_len, MISTRAL_MAX_MODEL_LEN))
    url = args.base_url.rstrip("/") + "/v1/completions"
    one_request(url, args.model_name, int(args.input_len), min(output_len, 4))
    started = time.perf_counter()
    results = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futs = [
            pool.submit(one_request, url, args.model_name, int(args.input_len), output_len)
            for _ in range(num_prompts)
        ]
        for fut in as_completed(futs):
            results.append(fut.result())
    wall = time.perf_counter() - started
    out_tokens = sum(r["out_tokens"] for r in results)
    tokens_per_sec = out_tokens / wall if wall > 0 else 0.0
    ttfts = [r["ttft_ms"] for r in results]
    tpots = [r["tpot_ms"] for r in results]
    # ITL percentiles over every inter-token gap of every request (not over
    # per-request means).
    itls = [gap for r in results for gap in r["gaps_ms"]]
    e2es = [r["e2e_ms"] for r in results]
    print(
        f"p50_ttft={pct(ttfts,0.50):.6f} p95_ttft={pct(ttfts,0.95):.6f} p99_ttft={pct(ttfts,0.99):.6f} "
        f"p50_tpot={pct(tpots,0.50):.6f} p99_tpot={pct(tpots,0.99):.6f} "
        f"p50_itl={pct(itls,0.50):.6f} p99_itl={pct(itls,0.99):.6f} "
        f"output_tokens_per_sec={tokens_per_sec:.6f} e2e_ms={pct(e2es,0.50):.6f} samples={len(results)}",
        flush=True,
    )
    params = {
        "model_name": args.model_name,
        "dtype": args.dtype,
        "tensor_parallel_size": args.tensor_parallel_size,
        "gpu_memory_utilization": args.gpu_memory_utilization,
        "prompt_source": args.prompt_source,
        "input_len": args.input_len,
        "output_len": args.output_len,
        "max_num_seqs": args.max_num_seqs,
        "max_concurrency": concurrency,
        "num_prompts": num_prompts,
        "request_rate": "inf" if str(args.request_rate).lower() in {"true", "yes", "inf"} else args.request_rate,
    }
    # Per-request samples go to requests.csv. raw_results.csv (what the harness
    # parses and averages) holds only the run summary, so the published values
    # are the total throughput and true percentiles across requests. Before,
    # per-request rows (each request's own rate, and its single value copied
    # into p50/p95/p99) were averaged with the summary row: throughput came out
    # about 4-5x low and "p50" was a mean.
    request_rows = []
    for i, rec in enumerate(results):
        request_rows.append({
            "request_index": i,
            "status": "ok",
            "output_tokens": rec["out_tokens"],
            "request_output_tokens_per_sec": rec["out_tokens"] / (rec["e2e_ms"] / 1000.0) if rec["e2e_ms"] else 0.0,
            "ttft_msec": rec["ttft_ms"],
            "tpot_msec": rec["tpot_ms"],
            "itl_mean_msec": rec["itl_ms"],
            "end_to_end_request_latency_msec": rec["e2e_ms"],
        })
    with (run_dir / "requests.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(request_rows[0].keys()))
        writer.writeheader()
        writer.writerows(request_rows)
    summary_metrics = {
        "output_token_throughput_tokens_sec": tokens_per_sec,
        "ttft_p50_msec": pct(ttfts, 0.50),
        "ttft_p95_msec": pct(ttfts, 0.95),
        "ttft_p99_msec": pct(ttfts, 0.99),
        "time_per_output_token_tpot_p50_msec": pct(tpots, 0.50),
        "time_per_output_token_tpot_p95_msec": pct(tpots, 0.95),
        "time_per_output_token_tpot_p99_msec": pct(tpots, 0.99),
        "inter_token_latency_itl_p50_msec": pct(itls, 0.50) if itls else "",
        "inter_token_latency_itl_p95_msec": pct(itls, 0.95) if itls else "",
        "inter_token_latency_itl_p99_msec": pct(itls, 0.99) if itls else "",
        "end_to_end_request_latency_msec": pct(e2es, 0.50),
    }
    rows = [
        {"check_name": "summary", "status": "ok", **params, **summary_metrics},
    ]
    fieldnames = list(rows[0].keys())
    with (run_dir / "raw_results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    (run_dir / "raw_results.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    (run_dir / "raw_output.txt").write_text(json.dumps(summary_metrics, indent=2) + "\n", encoding="utf-8")
    print("[INFO] summary " + " ".join(f"{k}={summary_metrics[k]}" for k in METRIC_KEYS), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
