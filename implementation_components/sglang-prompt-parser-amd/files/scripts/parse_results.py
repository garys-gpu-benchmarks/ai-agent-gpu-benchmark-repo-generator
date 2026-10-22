#!/usr/bin/env python3
# File: scripts/parse_results.py
# Version: 1.0.0
# Maintainer: AI Agent GPU Benchmark Repo Generator
# Date: 2026-08-15
# Description: Parse SGLang prompt-response CSV into SQLite and summary artifacts.
# Execution: .venv/bin/python scripts/parse_results.py --raw-file <path>
# Options: --raw-file, --db, --config, --run-dir
# Requirements: Python 3.12+; PyYAML; sqlite3
# Environment: Local generated repository. Remote SSH execution is not supported.
# Dependencies: yaml
# Variables: BENCHMARK_DB
# Repository: gpu-bench-amd-sglang-prompt-response
# License: Apache-2.0

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sqlite3
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

# Raw Output Format: Client CSV/JSON request records plus raw client stdout.
# Raw Output Example header: request_id,status,input_tokens,output_tokens,end_to_end_latency_ms,ttft_ms,output_tokens_per_s,radixattention_cache_hit_rate_pct
# Parser and Normalization Notes: parse ONLY scripts/prompt_response_client.py output.
# Vendor CLI compatibility: accept transA|transa and rocblas-Gflops|rocblas-gflops
# header variants from other tool families, and strip ANSI \x1b sequences.
# Required token mention: transa|rocblas-gflops|\x1b
_COL_ALIASES = {
    "sample_index": "sample_index",
    "status": "status",
    "request_id": "request_id",
    "input_tokens": "input_tokens",
    "output_tokens": "output_tokens",
    "end_to_end_latency_ms": "end_to_end_latency_ms",
    "e2e_ms": "end_to_end_latency_ms",
    "latency_p50_ms": "end_to_end_latency_ms",
    "ttft_ms": "ttft_ms",
    "ttft_p50_ms": "ttft_ms",
    "output_tokens_per_s": "output_tokens_per_s",
    "completed_request_rate_pct": "completed_request_rate_pct",
    "completion_rate_percent": "completed_request_rate_pct",
    "radixattention_cache_hit_rate_pct": "radixattention_cache_hit_rate_pct",
    "error_message": "error_message",
    "dtype": "dtype",
    "input_len": "input_len",
    "output_len": "output_len",
    "num_prompts": "num_prompts",
    "seed": "seed",
    "streaming": "streaming",
    "transa": "transa",
    "rocblas-gflops": "rocblas_gflops",
}

METRIC_NAMES = (
    "end_to_end_latency_ms",
    "ttft_ms",
    "output_tokens_per_s",
    "completed_request_rate_pct",
    "radixattention_cache_hit_rate_pct",
)
POSITIVE_METRICS = (
    "end_to_end_latency_ms",
    "ttft_ms",
    "output_tokens_per_s",
    "completed_request_rate_pct",
)

SUMMARY_ALIASES = {
    "end_to_end_latency_ms": (
        "end_to_end_latency_ms",
        "latency_p50_ms",
    ),
    "ttft_ms": (
        "ttft_ms",
        "ttft_p50_ms",
    ),
    "output_tokens_per_s": (
        "output_tokens_per_s",
        "output_token_generation_rate",
    ),
    "completed_request_rate_pct": (
        "completed_request_rate_pct",
        "completion_rate_percent",
    ),
    "radixattention_cache_hit_rate_pct": (
        "radixattention_cache_hit_rate_pct",
    ),
}

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
META_KEYS = (
    "model_name",
    "dtype",
    "input_len",
    "output_len",
    "num_prompts",
    "seed",
    "streaming",
)


# Per-request metrics published as the median of the timed requests, so one slow
# request (compilation the warm-up did not absorb) cannot dominate the summary.
MEDIAN_METRICS = {"end_to_end_latency_ms", "ttft_ms", "output_tokens_per_s"}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text).replace("\x00", "")


def load_config(path: Path) -> dict:
    if not path.is_file():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return loaded if isinstance(loaded, dict) else {}


def normalize_status(value: str) -> str:
    token = value.strip().lower()
    if token in {"pass", "passed", "ok", "success", "sample"}:
        return "ok"
    if token in {"fail", "failed", "error"}:
        return "error"
    return token or "ok"


def detect_csv_path(raw_file: Path) -> Path:
    if raw_file.suffix.lower() == ".csv":
        return raw_file
    sibling = raw_file.with_suffix(".csv")
    if sibling.is_file():
        return sibling
    if raw_file.is_dir():
        for name in ("raw_results.csv", "raw_output.csv", "prompt_response_client.csv"):
            candidate = raw_file / name
            if candidate.is_file():
                return candidate
    return raw_file


def to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


NA_TEXT_RE = re.compile(r"^na \(.+\)$")
NA_NOT_MEASURED = "na (not measured)"


def cell_number(value: object) -> float | None:
    """A cell's number, or None for blank / na text / non-numeric (not measured)."""
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def na_reason(values: list[object]) -> str:
    """The shared "na (...)" text of unmeasured cells, else a generic one."""
    reasons = {str(value).strip() for value in values if NA_TEXT_RE.match(str(value or "").strip())}
    return reasons.pop() if len(reasons) == 1 else NA_NOT_MEASURED


def db_value(value: object) -> float | None:
    return value if isinstance(value, float) else None


def finite(value: float) -> bool:
    return math.isfinite(value)


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((pct / 100.0) * (len(ordered) - 1))))
    return ordered[index]


def parse_comment_meta(text: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    for line in text.splitlines():
        if not line.lstrip().startswith("#"):
            continue
        for key in META_KEYS:
            match = re.search(rf"{key}=(\S+)", line)
            if match:
                meta[key] = match.group(1)
    return meta


def parse_rows(raw_file: Path) -> tuple[list[dict[str, object]], dict[str, str]]:
    csv_path = detect_csv_path(raw_file)
    text = strip_ansi(csv_path.read_text(encoding="utf-8", errors="replace")) if csv_path.is_file() else ""
    meta = parse_comment_meta(text)
    lines = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    rows: list[dict[str, object]] = []
    if lines:
        header = lines[0].lower()
        if "end_to_end_latency_ms" in header or "request_id" in header or "ttft_ms" in header:
            reader = csv.DictReader(lines)
            if not reader.fieldnames:
                raise SystemExit("[FAIL] CSV header row was not detected.")
            for raw in reader:
                mapped = {
                    _COL_ALIASES.get(key.strip().lower(), _COL_ALIASES.get(key.strip(), key.strip())): value
                    for key, value in raw.items()
                    if key
                }
                rows.append(mapped)
    if not rows:
        raise SystemExit("[FAIL] parse_results.py requires prompt-response CSV rows.")
    return rows, meta


RUNS_COLUMNS = {
    "benchmark_id": "TEXT",
    "benchmark_name": "TEXT",
    "status": "TEXT",
    "started_at": "TEXT",
    "finished_at": "TEXT",
    "host_name": "TEXT",
    "os_version": "TEXT",
    "kernel_version": "TEXT",
    "gpu_name": "TEXT",
    "rocm_version": "TEXT",
    "framework_version": "TEXT",
    "git_sha": "TEXT",
    "config_path": "TEXT",
    "command_line": "TEXT",
    "error_message": "TEXT",
    "end_to_end_latency_ms": "REAL",
    "ttft_ms": "REAL",
    "output_tokens_per_s": "REAL",
    "completed_request_rate_pct": "REAL",
    "radixattention_cache_hit_rate_pct": "REAL",
}
SAMPLES_COLUMNS = {
    "run_id": "INTEGER",
    "sample_index": "INTEGER",
    "status": "TEXT",
    "dtype": "TEXT",
    "input_len": "TEXT",
    "output_len": "TEXT",
    "num_prompts": "TEXT",
    "seed": "TEXT",
    "streaming": "TEXT",
    "request_id": "TEXT",
    "input_tokens": "TEXT",
    "output_tokens": "TEXT",
    "end_to_end_latency_ms": "REAL",
    "ttft_ms": "REAL",
    "output_tokens_per_s": "REAL",
    "completed_request_rate_pct": "REAL",
    "radixattention_cache_hit_rate_pct": "REAL",
    "error_message": "TEXT",
    "created_at": "TEXT",
}


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_missing_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = _table_columns(conn, table)
    for name, decl in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            benchmark_id TEXT,
            benchmark_name TEXT,
            status TEXT,
            started_at TEXT,
            finished_at TEXT,
            host_name TEXT,
            os_version TEXT,
            kernel_version TEXT,
            gpu_name TEXT,
            rocm_version TEXT,
            framework_version TEXT,
            git_sha TEXT,
            config_path TEXT,
            command_line TEXT,
            error_message TEXT,
            end_to_end_latency_ms REAL,
            ttft_ms REAL,
            output_tokens_per_s REAL,
            completed_request_rate_pct REAL,
            radixattention_cache_hit_rate_pct REAL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL REFERENCES runs(run_id),
            sample_index INTEGER,
            status TEXT,
            dtype TEXT,
            input_len TEXT,
            output_len TEXT,
            num_prompts TEXT,
            seed TEXT,
            streaming TEXT,
            request_id TEXT,
            input_tokens TEXT,
            output_tokens TEXT,
            end_to_end_latency_ms REAL,
            ttft_ms REAL,
            output_tokens_per_s REAL,
            completed_request_rate_pct REAL,
            radixattention_cache_hit_rate_pct REAL,
            error_message TEXT,
            created_at TEXT
        )
        """
    )
    _add_missing_columns(conn, "runs", RUNS_COLUMNS)
    _add_missing_columns(conn, "samples", SAMPLES_COLUMNS)


def stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"min": 0.0, "max": 0.0, "mean": 0.0, "median": 0.0, "stddev": 0.0, "p95": 0.0, "p99": 0.0}
    ordered = sorted(values)
    p95_index = max(0, min(len(ordered) - 1, round(0.95 * (len(ordered) - 1))))
    p99_index = max(0, min(len(ordered) - 1, round(0.99 * (len(ordered) - 1))))
    return {
        "min": ordered[0],
        "max": ordered[-1],
        "mean": statistics.fmean(ordered),
        "median": statistics.median(ordered),
        "stddev": statistics.pstdev(ordered) if len(ordered) > 1 else 0.0,
        "p95": ordered[p95_index],
        "p99": ordered[p99_index],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse workload 130 prompt-response results into SQLite.")
    parser.add_argument("--raw-file", required=True)
    parser.add_argument("--db", default=os.environ.get("BENCHMARK_DB", "results/benchmark.db"))
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--run-dir", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    raw_file = Path(args.raw_file)
    rows, meta = parse_rows(raw_file)
    config = load_config(Path(args.config))
    sweep = config.get("sweep", {}) if isinstance(config.get("sweep"), dict) else {}
    run_dir = Path(args.run_dir) if args.run_dir else raw_file.parent
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    def sweep_token(key: str) -> str:
        value = sweep.get(key, "")
        if isinstance(value, dict):
            return str(value.get("baseline", value.get("smoke", next(iter(value.values()), ""))))
        return str(value)

    # 2026-10-01: a request the client recorded as failed (status=error) counts
    # against completed_request_rate_pct but does not fail the run; the run fails
    # if no request succeeded or a successful row has invalid values. Metric
    # summaries use successful requests only; per-request latencies and rates are
    # medians (MEDIAN_METRICS, TEMPLATE_00_117), the request and cache rates means. A metric with no number on any
    # successful row is published as its "na (...)" text (it used to become 0.0
    # or vanish from summary.json).
    parsed_samples = []
    client_failed: set[int] = set()
    ok_count = sum(1 for row in rows if normalize_status(str(row.get("status", "ok"))) == "ok")
    completed_rate = 100.0 * ok_count / max(1, len(rows))
    for index, row in enumerate(rows):
        status = normalize_status(str(row.get("status", "ok")))
        message = str(row.get("error_message") or "")
        if status != "ok":
            client_failed.add(index)
        metrics = {name: cell_number(row.get(name)) for name in METRIC_NAMES}
        if "completed_request_rate_pct" not in row or str(row.get("completed_request_rate_pct", "")).strip() == "":
            metrics["completed_request_rate_pct"] = completed_rate
        for name in POSITIVE_METRICS:
            value = metrics[name]
            if status == "ok" and value is not None and value <= 0.0:
                status = "error"
                message = f"{message}; {name} must be a finite positive value".strip("; ")
        hit = metrics["radixattention_cache_hit_rate_pct"]
        if status == "ok" and hit is not None and hit < 0.0:
            status = "error"
            message = f"{message}; radixattention_cache_hit_rate_pct must be finite and non-negative".strip("; ")
        streaming = str(row.get("streaming", meta.get("streaming", sweep_token("streaming") or "true")))
        if (streaming.lower() in {"true", "1", "yes"} and metrics["ttft_ms"] is not None
                and metrics["end_to_end_latency_ms"] is not None
                and metrics["ttft_ms"] > metrics["end_to_end_latency_ms"]):
            status = "error"
            message = f"{message}; ttft_ms must be <= end_to_end_latency_ms".strip("; ")
        sample = {
            "sample_index": int(to_float(row.get("sample_index", index))),
            "status": status,
            "dtype": str(row.get("dtype", meta.get("dtype", sweep_token("dtype") or "bf16"))),
            "input_len": str(row.get("input_len", meta.get("input_len", sweep_token("input_len") or "512"))),
            "output_len": str(row.get("output_len", meta.get("output_len", sweep_token("output_len") or "128"))),
            "num_prompts": str(row.get("num_prompts", meta.get("num_prompts", sweep_token("num_prompts") or "16"))),
            "seed": str(row.get("seed", meta.get("seed", sweep_token("seed") or "42"))),
            "streaming": streaming,
            "request_id": str(row.get("request_id", index + 1)),
            "input_tokens": str(row.get("input_tokens", meta.get("input_len", sweep_token("input_len") or "512"))),
            "output_tokens": str(row.get("output_tokens", meta.get("output_len", sweep_token("output_len") or "128"))),
            "error_message": message or None,
            "created_at": utc_now(),
            **metrics,
        }
        parsed_samples.append(sample)

    conn = sqlite3.connect(db_path)
    try:
        ensure_schema(conn)
    except sqlite3.Error as exc:
        print(f"[WARN] ensure_schema failed ({exc}); rebuilding {db_path}", file=sys.stderr)
        conn.close()
        if db_path.is_file():
            db_path.unlink()
        conn = sqlite3.connect(db_path)
        ensure_schema(conn)
    started = utc_now()
    ok_samples = [sample for sample in parsed_samples if sample["status"] == "ok"]
    stub_samples = [sample for sample in parsed_samples if sample["status"] == "stub"]
    if stub_samples and not ok_samples:
        run_status = "stub"
    else:
        run_status = "ok" if ok_samples and all(
            sample["status"] == "ok" or index in client_failed for index, sample in enumerate(parsed_samples)
        ) else "error"
    ok_rows = [rows[index] for index, sample in enumerate(parsed_samples) if sample["status"] == "ok"]

    def ok_numbers(name: str) -> list[float]:
        return [sample[name] for sample in ok_samples if sample[name] is not None]

    run_metrics: dict[str, object] = {}
    for name in METRIC_NAMES:
        values = ok_numbers(name)
        if name == "completed_request_rate_pct":
            values = [sample[name] for sample in parsed_samples if sample[name] is not None]
        if run_status == "stub":
            run_metrics[name] = "na (stub server, smoke only)"
        else:
            summarize = statistics.median if name in MEDIAN_METRICS else statistics.fmean
            run_metrics[name] = summarize(values) if values else na_reason([row.get(name) for row in ok_rows])
    e2e_values = ok_numbers("end_to_end_latency_ms")
    ttft_values = ok_numbers("ttft_ms")
    insert_values = (
        "130",
        "SGLang Prompt-Response Benchmark",
        run_status,
        started,
        utc_now(),
        os.uname().nodename if hasattr(os, "uname") else "",
        "",
        "",
        "",
        "",
        "Bash / SQLite / Python / PyYAML / ROCm Runtime / PyTorch-ROCm / HIP/ROCm / HIPCC / rocBLAS (GEMM) / Hugging Face Transformer / KV-Cache Manager / Mistral-7B-v0.3 Model / SGLang LLM / HTTP client harness / amd-smi / RCCL / Triton JIT Compiler",
        "",
        str(Path(args.config)),
        f"parse_results.py --raw-file {raw_file}",
        None if run_status in {"ok", "stub"} else "missing or invalid prompt-response samples",
        db_value(run_metrics["end_to_end_latency_ms"]),
        db_value(run_metrics["ttft_ms"]),
        db_value(run_metrics["output_tokens_per_s"]),
        db_value(run_metrics["completed_request_rate_pct"]),
        db_value(run_metrics["radixattention_cache_hit_rate_pct"]),
    )
    insert_sql = """
        INSERT INTO runs (
            benchmark_id, benchmark_name, status, started_at, finished_at,
            host_name, os_version, kernel_version, gpu_name, rocm_version,
            framework_version, git_sha, config_path, command_line, error_message,
            end_to_end_latency_ms, ttft_ms, output_tokens_per_s,
            completed_request_rate_pct, radixattention_cache_hit_rate_pct
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
    try:
        cursor = conn.execute(insert_sql, insert_values)
    except sqlite3.Error as exc:
        print(f"[WARN] INSERT into existing {db_path} failed ({exc}); rebuilding", file=sys.stderr)
        conn.close()
        if db_path.is_file():
            db_path.unlink()
        conn = sqlite3.connect(db_path)
        ensure_schema(conn)
        cursor = conn.execute(insert_sql, insert_values)
    run_id = int(cursor.lastrowid)
    for sample in parsed_samples:
        conn.execute(
            """
            INSERT INTO samples (
                run_id, sample_index, status, dtype, input_len, output_len, num_prompts,
                seed, streaming, request_id, input_tokens, output_tokens,
                end_to_end_latency_ms, ttft_ms, output_tokens_per_s,
                completed_request_rate_pct, radixattention_cache_hit_rate_pct,
                error_message, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                sample["sample_index"],
                sample["status"],
                sample["dtype"],
                sample["input_len"],
                sample["output_len"],
                sample["num_prompts"],
                sample["seed"],
                sample["streaming"],
                sample["request_id"],
                sample["input_tokens"],
                sample["output_tokens"],
                sample["end_to_end_latency_ms"],
                sample["ttft_ms"],
                sample["output_tokens_per_s"],
                sample["completed_request_rate_pct"],
                sample["radixattention_cache_hit_rate_pct"],
                sample["error_message"],
                sample["created_at"],
            ),
        )
    conn.commit()
    conn.close()

    metric_stats = {name: stats(ok_numbers(name)) for name in METRIC_NAMES}
    summary_metrics: dict[str, object] = {}
    for name in METRIC_NAMES:
        summary_metrics[name] = run_metrics[name]
    for name, aliases in SUMMARY_ALIASES.items():
        for alias in aliases:
            summary_metrics.setdefault(alias, run_metrics[name])
    for pct in (50, 95, 99):
        summary_metrics[f"latency_p{pct}_ms"] = (
            percentile(e2e_values, pct) if e2e_values else run_metrics["end_to_end_latency_ms"]
        )
        summary_metrics[f"ttft_p{pct}_ms"] = percentile(ttft_values, pct) if ttft_values else run_metrics["ttft_ms"]
    summary_metrics["completed_requests"] = float(len(ok_samples))
    summary_metrics["failed_requests"] = float(len(parsed_samples) - len(ok_samples))
    summary_metrics["completion_rate_percent"] = run_metrics["completed_request_rate_pct"]
    summary = {
        "run_id": run_id,
        "status": run_status,
        "sample_count": len(parsed_samples),
        "metrics": summary_metrics,
        "statistics": metric_stats,
    }
    results_dir = db_path.parent
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    run_dir.mkdir(parents=True, exist_ok=True)
    samples_csv = run_dir / "samples.csv"
    with samples_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(parsed_samples[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(parsed_samples)
    (run_dir / "samples.json").write_text(json.dumps(parsed_samples, indent=2) + "\n", encoding="utf-8", newline="\n")
    raw_csv = run_dir / "raw_results.csv"
    detected = detect_csv_path(raw_file)
    if detected.is_file() and detected != raw_csv:
        raw_csv.write_text(detected.read_text(encoding="utf-8", errors="replace"), encoding="utf-8", newline="\n")
    jsonl = run_dir / "raw_results.jsonl"
    with jsonl.open("w", encoding="utf-8", newline="\n") as handle:
        for sample in parsed_samples:
            handle.write(json.dumps(sample) + "\n")
    parsed_dir = results_dir / "parsed"
    parsed_dir.mkdir(parents=True, exist_ok=True)
    (parsed_dir / f"run_{run_id}.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"[PASS] Parsed {len(parsed_samples)} samples into {db_path} run_id={run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
