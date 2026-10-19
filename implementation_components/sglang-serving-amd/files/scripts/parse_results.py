#!/usr/bin/env python3
"""Parse SGLang serving-latency CSV/JSON into SQLite and summary.json."""
from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from metric_contract import finalize_serving_publication, is_explicit_na


METRIC_COLUMNS = [
    "end_to_end_request_latency_p50_msec",
    "end_to_end_request_latency_p95_msec",
    "end_to_end_request_latency_p99_msec",
    "ttft_p50_msec",
    "ttft_p95_msec",
    "ttft_p99_msec",
    "time_per_output_token_tpot_p50_msec",
    "time_per_output_token_tpot_p95_msec",
    "time_per_output_token_tpot_p99_msec",
    "inter_token_latency_itl_p50_msec",
    "inter_token_latency_itl_p95_msec",
    "inter_token_latency_itl_p99_msec",
    "request_throughput_requests_sec",
]
PARAM_COLUMNS = [
    "model_name",
    "dtype",
    "tensor_parallel_size",
    "schedule_policy",
    "prompt_source",
    "input_len",
    "output_len",
    "max_total_tokens",
    "max_running_requests",
    "max_concurrency",
    "request_rate",
    "num_prompts",
    "backend",
    "dataset_name",
]


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_rows(raw_file: Path, run_dir: Path) -> list[dict]:
    csv_path = run_dir / "raw_results.csv"
    if csv_path.is_file():
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    jsonl = run_dir / "raw_results.jsonl"
    if jsonl.is_file():
        return [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    payload = json.loads(raw_file.read_text(encoding="utf-8"))
    return [{"check_name": "summary", "status": "ok", **payload}]


def to_float(value: object) -> float:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-file", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--summary", default="")
    parser.add_argument("--definition", default="benchmark_specification.json")
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--run-dir", default="")
    parser.add_argument("--profile", default="baseline")
    args = parser.parse_args()
    raw_file = Path(args.raw_file)
    run_dir = Path(args.run_dir) if args.run_dir else raw_file.parent
    rows = load_rows(raw_file, run_dir)
    if len(rows) < 2:
        raise SystemExit("[FAIL] parse_results.py requires at least two samples.")
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE IF EXISTS samples")
    conn.execute("DROP TABLE IF EXISTS runs")
    metric_sql = ", ".join(f"{name} REAL" for name in METRIC_COLUMNS)
    param_sql = ", ".join(f"{name} TEXT" for name in PARAM_COLUMNS)
    conn.execute(
        f"""
        CREATE TABLE runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            benchmark_id TEXT,
            benchmark_name TEXT,
            status TEXT,
            started_at TEXT,
            finished_at TEXT,
            host_name TEXT,
            {metric_sql}
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            sample_index INTEGER,
            status TEXT,
            check_name TEXT,
            {param_sql},
            {metric_sql}
        )
        """
    )
    summary = rows[-1]
    now = iso_now()
    conn.execute(
        f"""
        INSERT INTO runs (benchmark_id, benchmark_name, status, started_at, finished_at, host_name,
            {", ".join(METRIC_COLUMNS)})
        VALUES (?, ?, ?, ?, ?, ?, {", ".join("?" for _ in METRIC_COLUMNS)})
        """,
        (
            "131",
            "SGLang Serving Latency Benchmark",
            "ok",
            now,
            now,
            "localhost",
            *[(None if str(summary.get(name, "") or "").strip() == "" else to_float(summary.get(name))) for name in METRIC_COLUMNS],
        ),
    )
    run_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    for index, row in enumerate(rows, start=1):
        conn.execute(
            f"""
            INSERT INTO samples (run_id, sample_index, status, check_name,
                {", ".join(PARAM_COLUMNS)}, {", ".join(METRIC_COLUMNS)})
            VALUES (?, ?, ?, ?, {", ".join("?" for _ in PARAM_COLUMNS)}, {", ".join("?" for _ in METRIC_COLUMNS)})
            """,
            (
                run_id,
                index,
                str(row.get("status") or "ok"),
                str(row.get("check_name") or f"sample{index}"),
                *[str(row.get(name, "")) for name in PARAM_COLUMNS],
                *[to_float(row.get(name)) for name in METRIC_COLUMNS],
            ),
        )
    conn.commit()
    conn.close()
    summary_path = Path(args.summary) if args.summary else Path("results/summary.json")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    published = {}
    for name in METRIC_COLUMNS:
        raw = summary.get(name, "")
        if str(raw).strip() == "":
            continue
        if is_explicit_na(raw):
            published[name] = str(raw).strip()
            continue
        number = to_float(raw)
        if number is not None:
            published[name] = number
    identity = os.environ.get("BENCHMARK_SERVER_KIND", "") + " " + json.dumps(summary)
    if raw_file.is_file():
        identity += "\n" + raw_file.read_text(encoding="utf-8", errors="replace")[:4000]
    published, serve_status = finalize_serving_publication(published, identity)
    payload = {
        "sample_count": len(rows),
        "status": serve_status,
        "metrics": published,
    }
    summary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"[PASS] Parsed {len(rows)} samples into {db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
