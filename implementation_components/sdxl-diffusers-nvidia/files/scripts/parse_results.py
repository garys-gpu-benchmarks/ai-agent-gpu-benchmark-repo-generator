#!/usr/bin/env python3
# File: scripts/parse_results.py
# Version: 1.0.0
# Author: TEMPLATE_00_54 generator
# Date: 2026-08-19
# Description: Parse SDXL RESULT lines or METRICS_CSV into SQLite and summary.json.
# Execution: .venv/bin/python scripts/parse_results.py --raw-file PATH --db PATH
# Options: --raw-file, --db, --config, --run-dir, --profile
# Requirements: Python 3.12
# Environment: Repository-local .venv
# Dependencies: benchmark_definition.json
# Variables: none
# Repository: gpu-bench-nvidia-sdxl-diffusers-latency
# License: Apache-2.0

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median, pstdev


ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x00")
METRIC_COLUMNS = [
    "per_image_latency_sec",
    "images_per_sec",
    "peak_vram_gb",
    "step_time_ms",
    "first_image_latency_s",
]
PARAM_COLUMNS = [
    "model_name",
    "precision",
    "scheduler",
    "prompt_source",
    "prompt_len",
    "image_resolution",
    "batch_size",
    "num_images",
    "num_inference_steps",
    "guidance_scale",
    "seed",
]
_COL_ALIASES = {
    "latency_ms": "latency_ms",
    "latency_msec": "latency_ms",
    "per_image_latency_s": "per_image_latency_sec",
    "images_per_s": "images_per_sec",
    "images/sec": "images_per_sec",
    "gpu_mem_gb": "peak_vram_gb",
    "peak_gpu_memory_gb": "peak_vram_gb",
    "peak_vram_GB": "peak_vram_gb",
}
RESULT_RE = re.compile(
    r"RESULT\s+"
    r"model_name=(\S+)\s+precision=(\S+)\s+scheduler=(\S+)\s+"
    r"prompt_source=(\S+)\s+prompt_len=(\S+)\s+image_resolution=(\S+)\s+"
    r"batch_size=(\S+)\s+num_images=(\S+)\s+num_inference_steps=(\S+)\s+"
    r"guidance_scale=(\S+)\s+seed=(\S+)\s+"
    r"per_image_latency_sec=([0-9.eE+-]+)\s+images_per_sec=([0-9.eE+-]+)\s+"
    r"peak_vram_gb=([0-9.eE+-]+)\s+status=(\w+)"
)


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def locate_csv(text: str) -> str:
    marker = "# METRICS_CSV"
    if marker in text:
        text = text.split(marker, 1)[1]
    lines = []
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        if line.strip():
            lines.append(line)
    return "\n".join(lines)


def normalize_row(row: dict[str, str]) -> dict[str, str]:
    normalized = {}
    for key, value in row.items():
        raw_key = (key or "").strip()
        alias = _COL_ALIASES.get(raw_key, _COL_ALIASES.get(raw_key.lower(), raw_key))
        normalized[alias] = (value or "").strip()
    return normalized


def to_float(value: str, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed


def convert_units(row: dict[str, str]) -> dict[str, str]:
    # Raw Output Format may emit latency_ms / gpu_mem_gb; persist seconds and GB.
    if "per_image_latency_sec" not in row and "latency_ms" in row:
        row["per_image_latency_sec"] = str(to_float(row.get("latency_ms", "0")) / 1000.0)
    if "peak_vram_gb" not in row and "gpu_mem_gb" in row:
        row["peak_vram_gb"] = row.get("gpu_mem_gb", "0")
    return row


def stats(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    p95 = ordered[int(0.95 * (len(ordered) - 1))] if ordered else 0.0
    return {
        "min": min(values) if values else 0.0,
        "max": max(values) if values else 0.0,
        "mean": mean(values) if values else 0.0,
        "median": median(values) if values else 0.0,
        "stddev": pstdev(values) if len(values) > 1 else 0.0,
        "p95": p95,
    }


def rows_from_result_lines(text: str) -> list[dict[str, str]]:
    parsed: list[dict[str, str]] = []
    for index, match in enumerate(RESULT_RE.finditer(text), start=1):
        parsed.append(
            {
                "check": f"pass{index}",
                "status": match.group(16) if match.group(16) else "ok",
                "model_name": match.group(1),
                "precision": match.group(2),
                "scheduler": match.group(3),
                "prompt_source": match.group(4),
                "prompt_len": match.group(5),
                "image_resolution": match.group(6),
                "batch_size": match.group(7),
                "num_images": match.group(8),
                "num_inference_steps": match.group(9),
                "guidance_scale": match.group(10),
                "seed": match.group(11),
                "per_image_latency_sec": match.group(12),
                "images_per_sec": match.group(13),
                "peak_vram_gb": match.group(14),
            }
        )
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-file", required=True)
    parser.add_argument("--db", default="results/benchmark.db")
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--run-dir", default="")
    parser.add_argument("--profile", default="smoke")
    args = parser.parse_args()

    raw_path = Path(args.raw_file)
    raw_text = strip_ansi(raw_path.read_text(encoding="utf-8", errors="replace"))
    csv_text = locate_csv(raw_text)
    rows: list[dict[str, str]] = []
    if csv_text and "," in csv_text.splitlines()[0]:
        reader = csv.DictReader(io.StringIO(csv_text))
        if reader.fieldnames:
            rows = [convert_units(normalize_row(row)) for row in reader if any(row.values())]
    if not rows:
        rows = rows_from_result_lines(raw_text)
    if not rows:
        raise SystemExit("[FAIL] No supported SDXL RESULT or METRICS_CSV shape was detected.")

    started = iso_now()
    finished = iso_now()
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(args.db)
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
            framework_version TEXT,
            git_sha TEXT,
            config_path TEXT,
            command_line TEXT,
            error_message TEXT,
            per_image_latency_sec REAL,
            images_per_sec REAL,
            peak_vram_gb REAL
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
            check_name TEXT,
            model_name TEXT,
            precision TEXT,
            scheduler TEXT,
            prompt_source TEXT,
            prompt_len TEXT,
            image_resolution TEXT,
            batch_size TEXT,
            num_images TEXT,
            num_inference_steps TEXT,
            guidance_scale TEXT,
            seed TEXT,
            per_image_latency_sec REAL,
            images_per_sec REAL,
            peak_vram_gb REAL,
            error_message TEXT,
            created_at TEXT
        )
        """
    )
    summary_row = next((row for row in rows if row.get("check") == "summary"), rows[-1])
    image_rows_for_aggregate = [
        row for row in rows if str(row.get("check", "")).lower() != "summary"
    ] or rows
    latencies = [
        to_float(row.get("per_image_latency_sec", "0"))
        for row in image_rows_for_aggregate
    ]
    latencies = [value for value in latencies if value > 0]
    if not latencies:
        raise SystemExit("[FAIL] SDXL rows contained no positive per-image latency.")
    memory_values = [
        to_float(row.get("peak_vram_gb", "0"))
        for row in image_rows_for_aggregate
    ]
    step_values = [
        to_float(row.get("step_time_ms", "0"))
        for row in image_rows_for_aggregate
    ]
    step_values = [value for value in step_values if value > 0]
    aggregates = {
        "per_image_latency_sec": mean(latencies),
        "images_per_sec": len(latencies) / sum(latencies),
        "peak_vram_gb": max(memory_values),
        "step_time_ms": mean(step_values) if step_values else 0.0,
        "first_image_latency_s": to_float(summary_row.get("first_image_latency_s", "0")),
    }
    status = "ok" if all(row.get("status", "").lower() in {"ok", "pass", "passed", ""} for row in rows) else "error"
    cursor = conn.execute(
        """
        INSERT INTO runs (
            benchmark_id, benchmark_name, status, started_at, finished_at, host_name,
            os_version, kernel_version, gpu_name, framework_version, git_sha, config_path,
            command_line, error_message, per_image_latency_sec, images_per_sec, peak_vram_gb
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "224",
            "Stable Diffusion XL Inference Baseline",
            status,
            started,
            finished,
            Path.cwd().name,
            "Ubuntu 24.04",
            "",
            "NVIDIA H100",
            "PyTorch-CUDA / diffusers / Hugging Face Transformer",
            "",
            args.config,
            f"bash run_benchmark.sh --{args.profile} --validate",
            None if status == "ok" else "one or more SDXL inference samples failed",
            aggregates["per_image_latency_sec"],
            aggregates["images_per_sec"],
            aggregates["peak_vram_gb"],
        ),
    )
    run_id = cursor.lastrowid
    created = iso_now()
    for index, row in enumerate(rows):
        sample_status = row.get("status", "ok").lower()
        if sample_status in {"pass", "passed", ""}:
            sample_status = "ok"
        conn.execute(
            """
            INSERT INTO samples (
                run_id, sample_index, status, check_name, model_name, precision, scheduler,
                prompt_source, prompt_len, image_resolution, batch_size, num_images,
                num_inference_steps, guidance_scale, seed, per_image_latency_sec,
                images_per_sec, peak_vram_gb, error_message, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                index,
                "ok" if sample_status == "ok" else "error",
                row.get("check", ""),
                row.get("model_name", ""),
                row.get("precision", ""),
                row.get("scheduler", ""),
                row.get("prompt_source", ""),
                row.get("prompt_len", ""),
                row.get("image_resolution", ""),
                row.get("batch_size", ""),
                row.get("num_images", ""),
                row.get("num_inference_steps", ""),
                row.get("guidance_scale", ""),
                row.get("seed", ""),
                to_float(row.get("per_image_latency_sec", "0")),
                to_float(row.get("images_per_sec", "0")),
                to_float(row.get("peak_vram_gb", "0")),
                None if sample_status == "ok" else row.get("error_message") or "sample failed",
                created,
            ),
        )
    conn.commit()
    metric_stats = {
        name: stats([to_float(row.get(name, "0")) for row in rows]) for name in METRIC_COLUMNS
    }
    image_rows = [row for row in rows if str(row.get("check", "")).lower() != "summary"]
    first_source = image_rows[0] if image_rows else summary_row

    def measured(*keys: str, source: dict | None = None):
        src = source if source is not None else summary_row
        for key in keys:
            raw = src.get(key, "")
            if raw in (None, ""):
                continue
            try:
                parsed = float(raw)
            except (TypeError, ValueError):
                continue
            if parsed > 0:
                return parsed
        return None

    first_image_latency_s = measured(
        "first_image_latency_s",
        "first_image_latency_sec",
        source=first_source,
    )
    step_time_ms = aggregates["step_time_ms"] or None
    summary = {
        "run_id": run_id,
        "status": status,
        "profile": args.profile,
        "sample_count": len(rows),
        "metrics": {
            "per_image_latency_sec": aggregates["per_image_latency_sec"],
            "images_per_sec": aggregates["images_per_sec"],
            "peak_vram_gb": aggregates["peak_vram_gb"],
            "first_image_latency_s": first_image_latency_s if first_image_latency_s is not None else "",
            "step_time_ms": step_time_ms if step_time_ms is not None else "",
        },
        "statistics": metric_stats,
    }
    results_dir = Path("results")
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if args.run_dir:
        run_dir = Path(args.run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        parsed_csv = run_dir / "samples.csv"
        with parsed_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["check", *PARAM_COLUMNS, *METRIC_COLUMNS, "status"],
                lineterminator="\n",
            )
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in writer.fieldnames})
        (run_dir / "samples.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
        (run_dir / "raw_results.csv").write_text(csv_text + "\n" if csv_text else "", encoding="utf-8")
        with (run_dir / "raw_results.jsonl").open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")
    conn.close()
    print(f"[PASS] Parsed {len(rows)} samples into {args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
