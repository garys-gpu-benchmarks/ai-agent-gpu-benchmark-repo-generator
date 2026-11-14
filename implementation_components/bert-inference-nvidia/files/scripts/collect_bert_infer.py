#!/usr/bin/env python3
"""Collect BERT inference RESULT samples."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from pathlib import Path

import yaml

METRIC_FIELDS = [
    "sequences_per_sec",
    "mean_latency_ms",
    "latency_p50_msec",
    "latency_p99_msec",
    "tokens_per_sec",
    "peak_gpu_memory_gb",
]
PARAM_FIELDS = ["check", "model_name", "sequence_len", "batch_size", "status"]
RESULT_RE = re.compile(
    r"RESULT model_name=(?P<model_name>\S+) dtype=(?P<dtype>\S+) sequence_len=(?P<sequence_len>\S+) "
    r"batch_size=(?P<batch_size>\S+) sequences_per_sec=(?P<sequences_per_sec>[0-9.eE+-]+) "
    r"mean_latency_ms=(?P<mean_latency_ms>[0-9.eE+-]+) "
    r"latency_p50_msec=(?P<latency_p50_msec>[0-9.eE+-]+) latency_p95_msec=(?P<latency_p95_msec>[0-9.eE+-]+) "
    r"latency_p99_msec=(?P<latency_p99_msec>[0-9.eE+-]+) tokens_per_sec=(?P<tokens_per_sec>[0-9.eE+-]+) "
    r"peak_gpu_memory_gb=(?P<peak_gpu_memory_gb>[0-9.eE+-]+) status=(?P<status>\w+)"
)


def pick(sweep: dict, key: str, profile: str, default: str = "") -> str:
    value = sweep.get(key, default)
    if isinstance(value, dict):
        value = value.get(profile, value.get("smoke", default))
    return "" if value is None else str(value).strip()


def run(command: list[str]) -> tuple[int, str]:
    completed = subprocess.run(command, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return completed.returncode, completed.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--model-name", default="")
    parser.add_argument("--dtype", default="")
    parser.add_argument("--precision", default="")
    parser.add_argument("--num-gpus", default="")
    parser.add_argument("--prompt-source", default="")
    parser.add_argument("--sequence-len", default="")
    parser.add_argument("--batch-size", default="")
    parser.add_argument("--warmup-iters", default="")
    parser.add_argument("--num-iterations", default="")
    parser.add_argument("--output-format", default="csv")
    args = parser.parse_args()
    sweep = (yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}).get("sweep", {})
    profile = args.profile
    repo = Path(__file__).resolve().parents[1]
    python = repo / ".venv" / "bin" / "python"
    if not python.is_file():
        python = Path("python3")
    command = [
        str(python),
        str(repo / "scripts" / "gpu-bench-bert-transformers-inference.py"),
        "--model-name",
        args.model_name or pick(sweep, "model_name", profile, "bert-base-uncased"),
        "--dtype",
        args.dtype or pick(sweep, "dtype", profile, "f16_r"),
        "--precision",
        args.precision or pick(sweep, "precision", profile, "mixed_float16"),
        "--num-gpus",
        args.num_gpus or pick(sweep, "num_gpus", profile, "1"),
        "--prompt-source",
        args.prompt_source or pick(sweep, "prompt_source", profile, "synthetic"),
        "--sequence-len",
        args.sequence_len or pick(sweep, "sequence_len", profile, "32"),
        "--batch-size",
        args.batch_size or pick(sweep, "batch_size", profile, "1"),
        "--warmup-iters",
        args.warmup_iters or pick(sweep, "warmup_iters", profile, "2"),
        "--num-iterations",
        args.num_iterations or pick(sweep, "num_iterations", profile, "5"),
    ]
    transcripts = []
    parsed = []
    for index in range(1):  # one pass, one sample
        print("[RUN] " + " ".join(command))
        code, text = run(command)
        transcripts.append(f"===== bert-pass{index + 1} rc={code} =====\n{text}")
        print(text.rstrip())
        match = RESULT_RE.search(text)
        if code != 0 or match is None:
            raise SystemExit("[FAIL] BERT inference did not emit a RESULT line.")
        parsed.append(match.groupdict())
    rows = []
    for index, item in enumerate(parsed, start=1):
        row = {
            "check": f"pass{index}",
            "model_name": item["model_name"],
            "sequence_len": item["sequence_len"],
            "batch_size": item["batch_size"],
            "status": item["status"],
        }
        for name in METRIC_FIELDS:
            row[name] = f"{float(item[name]):.6f}"
        rows.append(row)
    summary = {
        "check": "summary",
        "model_name": parsed[0]["model_name"],
        "sequence_len": parsed[0]["sequence_len"],
        "batch_size": parsed[0]["batch_size"],
        "status": "ok",
    }
    for name in METRIC_FIELDS:
        values = [float(row[name]) for row in rows]
        summary[name] = f"{(sum(values) / len(values)):.6f}"
    rows.append(summary)
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    fields = [*PARAM_FIELDS, *METRIC_FIELDS]
    with (run_dir / "raw_results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    (run_dir / "raw_results.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    (run_dir / "raw_output.txt").write_text("\n".join(transcripts) + "\n", encoding="utf-8")
    print("# METRICS_CSV")
    print((run_dir / "raw_results.csv").read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
