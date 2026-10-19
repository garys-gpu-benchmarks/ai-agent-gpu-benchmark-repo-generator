#!/usr/bin/env python3
"""Pinned concurrent SGLang serving-latency client. Do not use prompt_response_client.py.

Use the workbook request count as-is. Do not shrink the request count
to the concurrency setting. Baseline/extended send concurrent waves.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from metric_contract import apply_itl_contract, finalize_serving_publication, guarded_percentile

def _f6(value) -> str:
    """6-decimal text for a number; leave an explicit na reason unchanged."""
    if value is None or value == "":
        return ""
    text = str(value)
    if text.lower().startswith("na ("):
        return text
    return f"{float(value):.6f}"


METRIC_KEYS = (
    "end_to_end_request_latency_p50_msec",
    "ttft_p50_msec",
    "time_per_output_token_tpot_p50_msec",
    "inter_token_latency_itl_p50_msec",
    "request_throughput_requests_sec",
)


def pct(values: list[float], p: float) -> float:
    values = [v for v in values if v != ""]
    if not values:
        return ""
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round(p * (len(ordered) - 1)))))
    return ordered[idx]


def _row_metric(key: str, rec: dict) -> float:
    if "end_to_end" in key:
        return rec["e2e_ms"]
    if "ttft" in key:
        return rec["ttft_ms"]  # blank when not measured
    if "throughput" in key:
        return 1.0 / max(rec["e2e_ms"] / 1000.0, 1e-9)
    if "itl" in key:
        return rec.get("itl_ms", "")
    return rec["tpot_ms"]


def one_request(url: str, model_name: str, input_len: int, output_len: int, seed: int) -> dict:
    prompt = f"request {seed} " + ("token " * max(1, input_len)).strip()
    payload = json.dumps({
        "model": model_name,
        "prompt": prompt,
        "max_tokens": output_len,
        "temperature": 0,
        "seed": seed,
        "stream": True,
        "stream_options": {"include_usage": True},
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    )
    start = time.perf_counter()
    first = None
    token_times: list[float] = []
    out_tokens = 0
    usage_tokens = None
    standin = os.environ.get("BENCHMARK_SERVER_KIND", "").lower() == "stub"
    with urllib.request.urlopen(req, timeout=3600) as resp:
        if "stub" in str(resp.headers.get("X-Benchmark-Server") or "").lower():
            standin = True
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            if chunk.get("server_identity") == "stub" or str(chunk.get("id", "")).startswith("tiny-sglang"):
                standin = True
            usage = chunk.get("usage") or {}
            if usage.get("completion_tokens"):
                usage_tokens = int(usage["completion_tokens"])
            choices = chunk.get("choices") or []
            text = choices[0].get("text", "") if choices else ""
            if not text:
                continue
            now = time.perf_counter()
            if first is None:
                first = now
            token_times.append(now)
            out_tokens += 1
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    produced = usage_tokens or out_tokens
    if first is None or produced < 1:
        return {
            "e2e_ms": elapsed_ms, "ttft_ms": "", "tpot_ms": "",
            "itl_ms": "", "itl_gaps_ms": [], "out_tokens": produced,
            "server_identity": "stub" if standin else "",
        }
    ttft_ms = (first - start) * 1000.0
    tpot_ms = (elapsed_ms - ttft_ms) / max(1, produced - 1)
    if len(token_times) >= 2:
        gaps = [(token_times[i] - token_times[i - 1]) * 1000.0 for i in range(1, len(token_times))]
        itl_ms = sum(gaps) / len(gaps)
    else:
        itl_ms = ""
    return {
        "e2e_ms": elapsed_ms, "ttft_ms": ttft_ms, "tpot_ms": tpot_ms,
        "itl_ms": itl_ms, "itl_gaps_ms": gaps if len(token_times) >= 2 else [],
        "out_tokens": produced,
        "server_identity": "stub" if standin else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:30000")
    parser.add_argument("--model-name", default="mistralai/Mistral-7B-v0.3")
    parser.add_argument("--dtype", default="bf16")
    parser.add_argument("--tensor-parallel-size", default="1")
    parser.add_argument("--schedule-policy", default="fcfs")
    parser.add_argument("--prompt-source", default="synthetic")
    parser.add_argument("--input-len", default="64")
    parser.add_argument("--output-len", default="16")
    parser.add_argument("--max-total-tokens", default="2048")
    parser.add_argument("--max-running-requests", default="2")
    parser.add_argument("--max-concurrency", default="2")
    parser.add_argument("--request-rate", default="inf")
    parser.add_argument("--num-prompts", default="2")
    parser.add_argument("--backend", default="sglang")
    parser.add_argument("--dataset-name", default="synthetic")
    parser.add_argument("--seed", default="42")
    args = parser.parse_args()
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    concurrency = max(1, int(float(args.max_concurrency))) if str(args.max_concurrency).lower() not in {"true", "yes"} else 2
    num_prompts = max(1, int(float(args.num_prompts))) if str(args.num_prompts).lower() not in {"true", "yes"} else 2
    url = args.base_url.rstrip("/") + "/v1/completions"
    results = []
    wall_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futs = [
            pool.submit(
                one_request,
                url,
                args.model_name,
                int(args.input_len),
                int(args.output_len),
                int(float(args.seed)) + index,
            )
            for index in range(num_prompts)
        ]
        for fut in as_completed(futs):
            results.append(fut.result())
    wall_s = max(time.perf_counter() - wall_start, 1e-9)
    e2e = [r["e2e_ms"] for r in results]
    ttft = [r["ttft_ms"] for r in results]
    tpot = [r["tpot_ms"] for r in results]
    itl = [gap for result in results for gap in result.get("itl_gaps_ms", [])]
    summary_metrics = {
        "end_to_end_request_latency_p50_msec": pct(e2e, 0.50),
        "end_to_end_request_latency_p95_msec": pct(e2e, 0.95),
        "end_to_end_request_latency_p99_msec": pct(e2e, 0.99),
        "ttft_p50_msec": pct(ttft, 0.50),
        "ttft_p95_msec": pct(ttft, 0.95),
        "ttft_p99_msec": pct(ttft, 0.99),
        "time_per_output_token_tpot_p50_msec": pct(tpot, 0.50),
        "time_per_output_token_tpot_p95_msec": pct(tpot, 0.95),
        "time_per_output_token_tpot_p99_msec": pct(tpot, 0.99),
        "inter_token_latency_itl_p50_msec": pct(itl, 0.50),
        "inter_token_latency_itl_p95_msec": pct(itl, 0.95),
        "inter_token_latency_itl_p99_msec": pct(itl, 0.99),
        "request_throughput_requests_sec": len(results) / wall_s,
        "e2e_p50_ms": pct(e2e, 0.50),
        "e2e_p95_ms": pct(e2e, 0.95),
        "e2e_p99_ms": pct(e2e, 0.99),
        "ttft_p50_ms": pct(ttft, 0.50),
        "ttft_p95_ms": pct(ttft, 0.95),
        "ttft_p99_ms": pct(ttft, 0.99),
        "tpot_p50_ms": pct(tpot, 0.50),
        "tpot_p95_ms": pct(tpot, 0.95),
        "tpot_p99_ms": pct(tpot, 0.99),
    }
    summary_metrics["end_to_end_request_latency_p95_msec"] = guarded_percentile(e2e, 0.95, "p95")
    summary_metrics["end_to_end_request_latency_p99_msec"] = guarded_percentile(e2e, 0.99, "p99")
    summary_metrics["ttft_p95_msec"] = guarded_percentile(ttft, 0.95, "p95")
    summary_metrics["ttft_p99_msec"] = guarded_percentile(ttft, 0.99, "p99")
    summary_metrics["time_per_output_token_tpot_p95_msec"] = guarded_percentile(tpot, 0.95, "p95")
    summary_metrics["time_per_output_token_tpot_p99_msec"] = guarded_percentile(tpot, 0.99, "p99")
    summary_metrics["inter_token_latency_itl_p95_msec"] = guarded_percentile(itl, 0.95, "p95")
    summary_metrics["inter_token_latency_itl_p99_msec"] = guarded_percentile(itl, 0.99, "p99")
    summary_metrics["e2e_p95_ms"] = summary_metrics["end_to_end_request_latency_p95_msec"]
    summary_metrics["e2e_p99_ms"] = summary_metrics["end_to_end_request_latency_p99_msec"]
    summary_metrics["ttft_p95_ms"] = summary_metrics["ttft_p95_msec"]
    summary_metrics["ttft_p99_ms"] = summary_metrics["ttft_p99_msec"]
    summary_metrics["tpot_p95_ms"] = summary_metrics["time_per_output_token_tpot_p95_msec"]
    summary_metrics["tpot_p99_ms"] = summary_metrics["time_per_output_token_tpot_p99_msec"]
    summary_metrics["latency_sample_count"] = len(results)
    apply_itl_contract(summary_metrics)
    identity = " ".join(str(item.get("server_identity", "")) for item in results)
    if os.environ.get("BENCHMARK_SERVER_KIND", "").lower() == "stub":
        identity += " server_identity=stub"
    summary_metrics, serve_status = finalize_serving_publication(summary_metrics, identity)
    params = {
        "model_name": args.model_name,
        "dtype": args.dtype,
        "tensor_parallel_size": args.tensor_parallel_size,
        "schedule_policy": args.schedule_policy,
        "prompt_source": args.prompt_source,
        "input_len": args.input_len,
        "output_len": args.output_len,
        "max_total_tokens": args.max_total_tokens,
        "max_running_requests": args.max_running_requests,
        "max_concurrency": concurrency,
        "request_rate": args.request_rate,
        "num_prompts": num_prompts,
        "backend": args.backend,
        "dataset_name": args.dataset_name,
    }
    rows = []
    for i, rec in enumerate(results):
        rows.append({
            "check_name": f"req_{i}",
            "status": "stub" if serve_status == "stub" else "ok",
            **params,
            "e2e_ms": rec["e2e_ms"],
            "ttft_ms": rec["ttft_ms"],
            "tpot_ms": rec["tpot_ms"],
            **{k: summary_metrics[k] for k in METRIC_KEYS},
        })
    rows.append({"check_name": "summary", "status": "stub" if serve_status == "stub" else "ok", "server_identity": summary_metrics.get("server_identity", ""), **params, "e2e_ms": summary_metrics["end_to_end_request_latency_p50_msec"], "ttft_ms": summary_metrics["ttft_p50_msec"], "tpot_ms": summary_metrics["time_per_output_token_tpot_p50_msec"], **{k: summary_metrics[k] for k in METRIC_KEYS}})
    fieldnames = list(dict.fromkeys([*rows[0].keys(), "server_identity"]))
    with (run_dir / "raw_results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    (run_dir / "raw_results.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    (run_dir / "raw_output.txt").write_text(json.dumps(summary_metrics, indent=2) + "\n", encoding="utf-8")
    print(
        f"e2e_p99_ms={_f6(summary_metrics['e2e_p99_ms'])} ttft_p99_ms={_f6(summary_metrics['ttft_p99_ms'])} "
        f"tpot_p99_ms={_f6(summary_metrics['tpot_p99_ms'])} samples={len(results)}",
        flush=True,
    )
    print("[INFO] summary " + " ".join(f"{k}={summary_metrics[k]}" for k in METRIC_KEYS), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
