#!/usr/bin/env python3
"""Concurrent prompt-serving client for KV-cache stress.

Use the real --model-name. Do not hardcode tiny-kv.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from statistics import median

NA_KV = "na (server reported no KV-cache usage)"
NA_KV_NO_BYTES = "na (server reported a percent and no byte count)"
KV_SAMPLE_INTERVAL_S = 0.05


def _f6(value) -> str:
    """6-decimal text for a number; an "na (...)" reason unchanged; blank otherwise."""
    if value is None or value == "":
        return ""
    if str(value).startswith("na ("):
        return str(value)
    return f"{float(value):.6f}"


METRIC_KEYS = (
    "decode_throughput_tokens_sec",
    "ttft_msec",
    # Was time_per_output_token_tpot_under_high_kv_pressure_msec: nothing makes
    # the KV cache full, so the name promised a condition the run never creates.
    # kv_cache_usage_peak_pct shows the occupancy actually reached.
    "tpot_msec",
    "kv_cache_hbm_utilization_gb_and_percentage_of_capacity",
    "kv_cache_peak_gb",
)


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
        "ttft_ms": ttft_ms,
        "tpot_ms": tpot_ms,
        "decode_ms": max(0.0, elapsed_ms - ttft_ms),
        "out_tokens": out_tokens,
        "elapsed_ms": elapsed_ms,
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


_USAGE_RE = re.compile(r"GPU KV cache usage:\s*([0-9.]+)\s*%")
_CAP_RE = re.compile(r"Available KV cache memory:\s*([0-9.]+)\s*GiB")


class KvPeakTracker:
    """Keep the high-water KV usage from while requests are still running.

    The Prometheus gauge is 0 after the last request returns, which makes
    validation reject kv_cache_usage_peak_pct. The engine log line is the
    reading taken during the sweep.
    """

    def __init__(self, base_url: str, log_path: Path):
        self.base_url = base_url
        self.log_path = log_path
        self._char_offset = 0
        if log_path.is_file():
            try:
                self._char_offset = len(log_path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                self._char_offset = 0
        self.peak_pct: float | None = None
        self.peak_gb: float | None = None
        self.capacity_gib: float | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._sample_metrics()
        self._read_log()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def finish(self) -> tuple[str, str]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
        self._sample_metrics()
        self._read_log()
        pct: str | float = NA_KV if self.peak_pct is None else self.peak_pct
        if self.peak_gb is not None:
            gb: str | float = self.peak_gb
        elif self.peak_pct is not None:
            gb = NA_KV_NO_BYTES
        else:
            gb = NA_KV
        return gb, pct

    def _loop(self) -> None:
        while not self._stop.wait(KV_SAMPLE_INTERVAL_S):
            self._sample_metrics()
            self._read_log()

    def _note_pct(self, pct: float) -> None:
        if pct <= 0:
            return
        if self.peak_pct is None or pct > self.peak_pct:
            self.peak_pct = pct
        if self.capacity_gib:
            gb = (pct / 100.0) * self.capacity_gib
            if self.peak_gb is None or gb > self.peak_gb:
                self.peak_gb = gb

    def _note_gb(self, gb: float) -> None:
        if gb <= 0:
            return
        if self.peak_gb is None or gb > self.peak_gb:
            self.peak_gb = gb

    def _sample_metrics(self) -> None:
        gb, pct = kv_stats(self.base_url)
        if pct != "":
            try:
                self._note_pct(float(pct))
            except (TypeError, ValueError):
                pass
        if gb != "":
            try:
                self._note_gb(float(gb))
            except (TypeError, ValueError):
                pass

    def _read_log(self) -> None:
        if not self.log_path.is_file():
            return
        try:
            text = self.log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        for match in _CAP_RE.finditer(text):
            try:
                self.capacity_gib = float(match.group(1))
            except ValueError:
                continue
        for match in _USAGE_RE.finditer(text[self._char_offset :]):
            try:
                self._note_pct(float(match.group(1)))
            except ValueError:
                continue
        self._char_offset = len(text)
        if self.peak_pct and self.capacity_gib:
            self._note_gb((self.peak_pct / 100.0) * self.capacity_gib)


def kv_stats(base_url: str) -> tuple[str, str]:
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/metrics", timeout=5) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return "", ""
    util = _prometheus_gauge(text, "vllm:kv_cache_usage_perc")
    if util is None:
        util = _prometheus_gauge(text, "vllm:gpu_cache_usage_perc")
    gb = _prometheus_gauge(text, "vllm:kv_cache_usage_bytes")
    if gb is None:
        gb = _prometheus_gauge(text, "vllm:gpu_cache_usage_bytes")
    util_pct = ""
    if util is not None and 0.0 <= util <= 1.0:
        util_pct = util * 100.0
    # GiB (1024^3), the unit vLLM uses for "Available KV cache memory", which
    # _note_pct multiplies by; this used to divide bytes by 1e9.
    gb_value = "" if gb is None else gb / (1024 ** 3)
    return gb_value, util_pct


def decode_window_throughput(results: list[dict]) -> float:
    decoded_tokens = sum(max(int(item["out_tokens"]) - 1, 0) for item in results)
    if decoded_tokens <= 0 or not results:
        return 0.0
    decode_start = min(float(item["first_token_at"]) for item in results)
    decode_end = max(float(item["completed_at"]) for item in results)
    decode_seconds = decode_end - decode_start
    return decoded_tokens / decode_seconds if decode_seconds > 0 else 0.0


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


def run_sweep(args, sweep_name: str) -> dict:
    url = args.base_url.rstrip("/") + "/v1/completions"
    one_request(
        url,
        args.model_name,
        int(args.input_len),
        int(args.output_len),
        int(args.seed) - 1,
    )
    tracker = KvPeakTracker(args.base_url, Path(args.run_dir) / "server.log")
    tracker.start()
    results = []
    try:
        with ThreadPoolExecutor(max_workers=max(1, int(args.concurrency))) as pool:
            futs = [
                pool.submit(one_request, url, args.model_name, int(args.input_len), int(args.output_len), int(args.seed) + i)
                for i in range(int(args.num_prompts))
            ]
            for fut in as_completed(futs):
                results.append(fut.result())
    finally:
        kv_gb, kv_pct = tracker.finish()
    kv_gb, kv_pct = require_kv_metrics(kv_gb, kv_pct)
    tokens_per_sec = decode_window_throughput(results)
    ttft = median(r["ttft_ms"] for r in results)
    tpot = median(r["tpot_ms"] for r in results)
    return {
        "check_name": sweep_name,
        "status": "ok",
        "completed_requests": len(results),
        "failed_requests": 0,
        "output_token_throughput": tokens_per_sec,
        "output_tokens_per_sec": tokens_per_sec,
        "TTFT": ttft,
        "TPOT": tpot,
        "kv_cache_usage_peak_pct": kv_pct,
        "gpu_mem_used_peak_gb": "",
        "decode_throughput_tokens_sec": tokens_per_sec,
        "ttft_msec": ttft,
        "tpot_msec": tpot,
        "kv_cache_hbm_utilization_gb_and_percentage_of_capacity": kv_gb,
        "kv_cache_peak_gb": kv_gb,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--serving-engine", default="true")
    parser.add_argument("--model-name", default="mistralai/Mistral-7B-v0.3")
    parser.add_argument("--dtype", default="bfloat16")
    parser.add_argument("--kv-cache-dtype", default="auto")
    parser.add_argument("--gpu-memory-utilization", default="0.9")
    parser.add_argument("--max-model-len", default="128")
    parser.add_argument("--dataset-name", default="true")
    parser.add_argument("--input-len", default="64")
    parser.add_argument("--output-len", default="16")
    parser.add_argument("--num-prompts", default="2")
    parser.add_argument("--concurrency", default="2")
    parser.add_argument("--seed", default="0")
    parser.add_argument("--output-format", default="csv")
    args = parser.parse_args()
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    params = {
        "serving_engine": "vllm" if str(args.serving_engine).lower() in {"true", "vllm", "yes"} else args.serving_engine,
        "model_name": args.model_name,
        "dtype": args.dtype,
        "kv_cache_dtype": args.kv_cache_dtype,
        "gpu_memory_utilization": args.gpu_memory_utilization,
        "max_model_len": args.max_model_len,
        "dataset_name": "synthetic" if str(args.dataset_name).lower() in {"true", "synthetic", "yes"} else args.dataset_name,
        "input_len": args.input_len,
        "output_len": args.output_len,
        "num_prompts": args.num_prompts,
        "concurrency": args.concurrency,
        "seed": args.seed,
    }
    rows = []
    for name in ("sweep_0", "sweep_1"):
        row = run_sweep(args, name)
        row.update(params)
        rows.append(row)
        print(
            f"{name} completed={row['completed_requests']} failed={row['failed_requests']} "
            f"output_token_throughput={row['output_token_throughput']:.6f} TTFT={row['TTFT']:.6f} "
            f"TPOT={row['TPOT']:.6f} kv_cache_usage_peak_pct={_f6(row['kv_cache_usage_peak_pct'])} "
            f"gpu_mem_used_peak_gb={_f6(row['gpu_mem_used_peak_gb'])}",
            flush=True,
        )
    def _mean(values):
        nums = []
        for value in values:
            if value is None or value == "":
                continue
            try:
                nums.append(float(value))
            except (TypeError, ValueError):
                continue
        if nums:
            return sum(nums) / len(nums)
        reasons = {str(v) for v in values if str(v).startswith("na (")}
        return reasons.pop() if len(reasons) == 1 else ""

    summary_metrics = {k: _mean([r[k] for r in rows]) for k in (*METRIC_KEYS, "kv_cache_usage_peak_pct")}
    for peak_key in ("kv_cache_peak_gb", "kv_cache_usage_peak_pct"):
        numeric_peaks = []
        for row in rows:
            try:
                numeric_peaks.append(float(row[peak_key]))
            except (KeyError, TypeError, ValueError):
                continue
        if numeric_peaks:
            summary_metrics[peak_key] = max(numeric_peaks)
    rows.append({"check_name": "summary", "status": "ok", **params, **{k: rows[0][k] for k in rows[0] if k not in params and k != "check_name"}, **summary_metrics})
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
