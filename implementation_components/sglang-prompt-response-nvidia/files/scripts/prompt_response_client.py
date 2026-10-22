#!/usr/bin/env python3
"""Sequential prompt-response client for SGLang workloads 130/230/330/430.

Exactly one request is in flight. Do not use sglang.bench_serving here.

Metrics (2026-10-01):
- output_tokens_per_s is the decode rate, (output tokens - 1) / (end-to-end - TTFT).
  It used to be output tokens / end-to-end, which charged prefill and TTFT to
  generation.
- Output tokens are the server's usage.completion_tokens (requested with
  stream_options.include_usage), else the number of streamed text chunks. It used
  to fall back to max_tokens, because streamed responses carry no usage unless
  include_usage is sent.
- radixattention_cache_hit_rate_pct is total cached prompt tokens / total prompt
  tokens over the successful requests, from usage.prompt_tokens_details.cached_tokens
  (SGLang returns it with --enable-cache-report). The /metrics scrape is gone: the
  server was never started with --enable-metrics, so real runs published 0.0.
  Prompts share a common first half by design, so ~50% is expected once warm.
- completed_request_rate_pct is successful / attempted requests. A failed request
  is recorded as a status=error row instead of stopping the run. It used to be
  hard-coded to 100.0.
- A value that cannot be measured is "na (<reason>)", never blank.
- One untimed warm-up request runs first (2026-10-20). The first request after
  the server reports ready waited 94-136 s for one-time kernel compilation, and
  that wait was averaged into TTFT (published 11.8-17 s instead of ~45 ms). The
  warm-up prompt shares no prefix with the timed prompts, so it does not change
  the cache hit rate.
- End-to-end latency, TTFT and output_tokens_per_s are the median (p50) of the
  timed requests (TEMPLATE_00_117). With a mean, one request that still waited on
  compilation after the warm-up dominated: 230 baseline published TTFT 1170 ms
  when seven of eight requests took ~29 ms (one took 9156 ms).
"""
from __future__ import annotations

import statistics

import argparse
import csv
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from metric_contract import STUB_NA, finalize_serving_publication

METRIC_KEYS = (
    "end_to_end_latency_ms",
    "ttft_ms",
    "output_tokens_per_s",
    "completed_request_rate_pct",
    "radixattention_cache_hit_rate_pct",
)
NA_STREAMING = "na (requires streaming)"
NA_ONE_TOKEN = "na (needs at least two output tokens)"
NA_NO_CACHE = "na (server reported no cached-token counts)"
NA_FAILED = "na (request failed)"


def _fmt(value) -> str:
    """6-decimal text for a number; na text unchanged."""
    return f"{float(value):.6f}" if isinstance(value, (int, float)) else str(value)


def prompt_text(input_len: int, seed: int) -> str:
    """First half shared by every request (prefix-cache hits), rest unique per request."""
    words = max(1, int(input_len))
    shared = max(1, words // 2)
    rest = words - shared
    tokens = ["common"] * shared
    if rest:
        tokens.append(f"request{seed}")
        tokens.extend(["token"] * max(0, rest - 1))
    return " ".join(tokens[:words])


def as_int(raw: object, fallback: int) -> int:
    try:
        if str(raw).lower() in {"", "true", "yes", "none"}:
            return fallback
        return max(1, int(float(raw)))
    except (TypeError, ValueError):
        return fallback


def _read_usage(usage: dict, rec: dict) -> None:
    if not isinstance(usage, dict):
        return
    if usage.get("completion_tokens"):
        rec["usage_tokens"] = int(usage["completion_tokens"])
    if usage.get("prompt_tokens") is not None:
        rec["prompt_tokens"] = int(usage["prompt_tokens"])
    details = usage.get("prompt_tokens_details")
    if isinstance(details, dict) and details.get("cached_tokens") is not None:
        rec["cached_tokens"] = int(details["cached_tokens"])


def warmup_prompt(input_len: int) -> str:
    """Same length as a timed prompt, no shared words, so nothing it caches helps a timed request."""
    return " ".join(["warmup"] + ["primer"] * max(0, int(input_len) - 1))


def one_request(
    url: str, model_name: str, input_len: int, output_len: int, seed: int, streaming: bool, prompt: str | None = None
) -> dict:
    payload = {
        "model": model_name,
        "prompt": prompt if prompt is not None else prompt_text(input_len, seed),
        "max_tokens": output_len,
        "temperature": 0,
        "seed": seed,
        "stream": streaming,
    }
    if streaming:
        # Without this, streamed responses carry no usage (token or cached counts).
        payload["stream_options"] = {"include_usage": True}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    rec: dict = {"usage_tokens": None, "prompt_tokens": None, "cached_tokens": None, "server_identity": ""}
    if os.environ.get("BENCHMARK_SERVER_KIND", "").lower() == "stub":
        rec["server_identity"] = "stub"
    start = time.perf_counter()
    first_token = None
    chunks = 0
    with urllib.request.urlopen(req, timeout=3600) as resp:
        if "stub" in str(resp.headers.get("X-Benchmark-Server") or "").lower():
            rec["server_identity"] = "stub"
        if streaming:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    body = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if body.get("server_identity") == "stub" or str(body.get("id", "")).startswith("tiny-sglang"):
                    rec["server_identity"] = "stub"
                choices = body.get("choices") or []
                if choices and choices[0].get("text"):
                    if first_token is None:
                        first_token = time.perf_counter()
                    chunks += 1
                _read_usage(body.get("usage") or {}, rec)
        else:
            body = json.loads(resp.read().decode("utf-8"))
            if body.get("server_identity") == "stub" or str(body.get("id", "")).startswith("tiny-sglang"):
                rec["server_identity"] = "stub"
            _read_usage(body.get("usage") or {}, rec)
    end = time.perf_counter()
    e2e_ms = (end - start) * 1000.0
    out_tokens = rec["usage_tokens"] or chunks or output_len
    if not streaming:
        ttft_ms = rate = NA_STREAMING
    else:
        ttft_ms = ((first_token or end) - start) * 1000.0
        decode_s = (e2e_ms - ttft_ms) / 1000.0
        rate = (out_tokens - 1) / decode_s if out_tokens > 1 and decode_s > 0 else NA_ONE_TOKEN
    return {
        "end_to_end_latency_ms": e2e_ms,
        "ttft_ms": ttft_ms,
        "output_tokens": out_tokens,
        "output_tokens_per_s": rate,
        "prompt_tokens": rec["prompt_tokens"],
        "cached_tokens": rec["cached_tokens"],
        "server_identity": rec["server_identity"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--raw-file", default="")
    parser.add_argument("--base-url", default="http://127.0.0.1:30000")
    parser.add_argument("--model-name", default="mistralai/Mistral-7B-v0.3")
    parser.add_argument("--dtype", default="bf16")
    parser.add_argument("--tensor-parallel-size", default="1")
    parser.add_argument("--schedule-policy", default="fcfs")
    parser.add_argument("--prompt-source", default="synthetic")
    parser.add_argument("--input-len", default="64")
    parser.add_argument("--output-len", default="16")
    parser.add_argument("--max-total-tokens", default="2048")
    parser.add_argument("--max-running-requests", default="1")
    parser.add_argument("--max-concurrency", default="1")
    parser.add_argument("--request-rate", default="inf")
    parser.add_argument("--num-prompts", default="2")
    parser.add_argument("--seed", default="42")
    parser.add_argument("--streaming", default="true")
    parser.add_argument("--output-format", default="csv")
    parser.add_argument("--warmup-requests", default="1", help="Untimed requests before the timed ones (0 disables)")
    args = parser.parse_args()
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    input_len = as_int(args.input_len, 64)
    output_len = as_int(args.output_len, 16)
    num_prompts = as_int(args.num_prompts, 2)
    streaming = str(args.streaming).lower() in {"true", "1", "yes"}
    url = args.base_url.rstrip("/") + "/v1/completions"
    warmups = max(0, int(float(args.warmup_requests))) if str(args.warmup_requests).strip() else 0
    for index in range(warmups):
        began = time.perf_counter()
        try:
            one_request(url, args.model_name, input_len, min(output_len, 32), -1 - index, streaming,
                        prompt=warmup_prompt(input_len))
            print(f"[INFO] warm-up request {index + 1}/{warmups} (untimed): {time.perf_counter() - began:.1f} s", flush=True)
        except (urllib.error.URLError, OSError, TimeoutError, ValueError) as exc:
            print(f"[WARN] warm-up request {index + 1} failed ({type(exc).__name__}: {exc}); timing anyway", flush=True)
    rows = []
    for index in range(num_prompts):
        row = {"request_id": index + 1, "sample_index": index}
        try:
            rec = one_request(url, args.model_name, input_len, output_len, as_int(args.seed, 42) + index, streaming)
            row.update({"status": "ok", "input_tokens": input_len, "output_tokens": rec["output_tokens"],
                        **{key: rec[key] for key in METRIC_KEYS[:3]},
                        "prompt_tokens": "" if rec["prompt_tokens"] is None else rec["prompt_tokens"],
                        "cached_tokens": "" if rec["cached_tokens"] is None else rec["cached_tokens"],
                        "server_identity": rec.get("server_identity", ""),
                        "error_message": ""})
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            row.update({"status": "error", "error_message": f"HTTP {exc.code}: {detail}"})
        except (urllib.error.URLError, OSError, TimeoutError, ValueError) as exc:
            row.update({"status": "error", "error_message": f"{type(exc).__name__}: {exc}"[:300]})
        if row["status"] != "ok":
            row.update({"input_tokens": input_len, "output_tokens": "", "prompt_tokens": "", "cached_tokens": "",
                        **{key: NA_FAILED for key in METRIC_KEYS[:3]}})
        rows.append(row)
        if row["status"] == "ok":
            print(f"request_id={row['request_id']} status=ok e2e_ms={_fmt(row['end_to_end_latency_ms'])} "
                  f"ttft_ms={_fmt(row['ttft_ms'])} output_tokens={row['output_tokens']} "
                  f"output_tokens_per_s={_fmt(row['output_tokens_per_s'])} cached_tokens={row['cached_tokens']}", flush=True)
        else:
            print(f"request_id={row['request_id']} status=error {row['error_message']}", flush=True)

    ok_rows = [row for row in rows if row["status"] == "ok"]
    completed_pct = 100.0 * len(ok_rows) / len(rows)
    cache_rows = [row for row in ok_rows if row["cached_tokens"] != "" and row["prompt_tokens"] not in ("", 0)]
    if cache_rows:
        hit_rate = 100.0 * sum(row["cached_tokens"] for row in cache_rows) / sum(row["prompt_tokens"] for row in cache_rows)
    else:
        hit_rate = NA_NO_CACHE
    meta = {
        "dtype": args.dtype, "input_len": input_len, "output_len": output_len, "num_prompts": num_prompts,
        "seed": args.seed, "streaming": "true" if streaming else "false", "model_name": args.model_name,
        "tensor_parallel_size": args.tensor_parallel_size, "schedule_policy": args.schedule_policy,
        "prompt_source": args.prompt_source,
    }
    identity = " ".join(str(row.get("server_identity", "")) for row in rows)
    standin = "stub" in identity or os.environ.get("BENCHMARK_SERVER_KIND", "").lower() == "stub"
    for row in rows:
        if standin:
            row["status"] = "stub" if row.get("status") == "ok" else row.get("status")
            row["completed_request_rate_pct"] = STUB_NA
            row["radixattention_cache_hit_rate_pct"] = STUB_NA
            for key in METRIC_KEYS[:3]:
                row[key] = STUB_NA
        else:
            row["completed_request_rate_pct"] = completed_pct
            row["radixattention_cache_hit_rate_pct"] = hit_rate if row["status"] == "ok" else NA_FAILED
        row.update(meta)
    fieldnames = ["request_id", "sample_index", "status", "input_tokens", "output_tokens", *METRIC_KEYS,
                  "prompt_tokens", "cached_tokens", "server_identity", "error_message", *meta]
    csv_path = run_dir / "raw_results.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    csv_text = csv_path.read_text(encoding="utf-8")
    # The SGLang parse_results.py reads CSV from raw_output.csv or the raw file.
    (run_dir / "raw_output.csv").write_text(csv_text, encoding="utf-8")
    if args.raw_file:
        raw_path = Path(args.raw_file)
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(csv_text, encoding="utf-8")

    def _summary(key):
        nums = [row[key] for row in ok_rows if isinstance(row[key], (int, float))]
        if nums:
            return statistics.median(nums)
        reasons = {row[key] for row in ok_rows}
        return reasons.pop() if len(reasons) == 1 else NA_FAILED

    summary_metrics = {key: _summary(key) for key in METRIC_KEYS[:3]}
    summary_metrics["completed_request_rate_pct"] = STUB_NA if standin else completed_pct
    summary_metrics["radixattention_cache_hit_rate_pct"] = STUB_NA if standin else hit_rate
    summary_metrics, _serve_status = finalize_serving_publication(summary_metrics, identity if standin else "")
    raw_txt = run_dir / "raw_output.txt"
    if not args.raw_file or Path(args.raw_file).resolve() != raw_txt.resolve():
        raw_txt.write_text(json.dumps(summary_metrics, indent=2) + "\n", encoding="utf-8")
    (run_dir / "raw_results.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    print("[INFO] summary " + " ".join(f"{k}={_fmt(summary_metrics[k])}" for k in METRIC_KEYS), flush=True)
    if not ok_rows:
        print(f"[FAIL] all {len(rows)} requests failed", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
