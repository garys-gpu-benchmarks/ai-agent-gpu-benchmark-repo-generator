#!/usr/bin/env python3
"""Collect DistilBERT training RESULT samples."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from pathlib import Path

import yaml

METRIC_FIELDS = [
    "samples_per_sec",
    "step_time_ms",
    "step_time_msec",
    "tokens_per_sec",
    "peak_gpu_memory_gb",
    "status_ok",
]
PARAM_FIELDS = ["check", "model_name", "sequence_len", "batch_size", "status"]
RESULT_RE = re.compile(
    r"RESULT model_name=(?P<model_name>\S+) dataset_name=(?P<dataset_name>\S+) "
    r"sequence_len=(?P<sequence_len>\S+) batch_size=(?P<batch_size>\S+) "
    r"samples_per_sec=(?P<samples_per_sec>[0-9.eE+-]+) step_time_msec=(?P<step_time_msec>[0-9.eE+-]+) "
    r"tokens_per_sec=(?P<tokens_per_sec>[0-9.eE+-]+) peak_gpu_memory_gb=(?P<peak_gpu_memory_gb>[0-9.eE+-]+) "
    r"status=(?P<status>\w+)"
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
    parser.add_argument("--dataset-name", default="")
    parser.add_argument("--num-gpus", default="")
    parser.add_argument("--sequence-len", default="")
    parser.add_argument("--batch-size", default="")
    parser.add_argument("--optimizer", default="")
    parser.add_argument("--learning-rate", default="")
    parser.add_argument("--weight-decay", default="")
    parser.add_argument("--gradient-accumulation", default="")
    parser.add_argument("--warmup-iters", default="")
    parser.add_argument("--num-epochs", default="")
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
        str(repo / "scripts" / "gpu-bench-distilbert-sst2-train.py"),
        "--model-name",
        args.model_name or pick(sweep, "model_name", profile, "distilbert-base-uncased"),
        "--dataset-name",
        args.dataset_name or pick(sweep, "dataset_name", profile, "glue-sst2-synthetic"),
        "--num-gpus",
        args.num_gpus or pick(sweep, "num_gpus", profile, "true"),
        "--sequence-len",
        args.sequence_len or pick(sweep, "sequence_len", profile, "32"),
        "--batch-size",
        args.batch_size or pick(sweep, "batch_size", profile, "2"),
        "--optimizer",
        args.optimizer or pick(sweep, "optimizer", profile, "adamw"),
        "--learning-rate",
        args.learning_rate or pick(sweep, "learning_rate", profile, "5e-05"),
        "--weight-decay",
        args.weight_decay or pick(sweep, "weight_decay", profile, "0.01"),
        "--gradient-accumulation",
        args.gradient_accumulation or pick(sweep, "gradient_accumulation", profile, "true"),
        "--warmup-iters",
        args.warmup_iters or pick(sweep, "warmup_iters", profile, "true"),
        "--num-epochs",
        args.num_epochs or pick(sweep, "num_epochs", profile, "true"),
        "--num-iterations",
        args.num_iterations or pick(sweep, "num_iterations", profile, "2"),
    ]
    transcripts = []
    parsed = []
    for index in range(1):  # one pass, one sample
        print("[RUN] " + " ".join(command))
        code, text = run(command)
        transcripts.append(f"===== distilbert-pass{index + 1} rc={code} =====\n{text}")
        print(text.rstrip())
        match = RESULT_RE.search(text)
        if code != 0 or match is None:
            raise SystemExit("[FAIL] DistilBERT trainer did not emit a RESULT line.")
        parsed.append(match.groupdict())
    rows = []
    for index, item in enumerate(parsed, start=1):
        row = {
            "check": f"pass{index}",
            "model_name": item["model_name"],
            "sequence_len": item["sequence_len"],
            "batch_size": item["batch_size"],
            "status": item["status"],
            "samples_per_sec": f"{float(item['samples_per_sec']):.6f}",
            "step_time_ms": f"{float(item['step_time_msec']):.6f}",
            "step_time_msec": f"{float(item['step_time_msec']):.6f}",
            "tokens_per_sec": f"{float(item['tokens_per_sec']):.6f}",
            "peak_gpu_memory_gb": f"{float(item['peak_gpu_memory_gb']):.6f}",
            "status_ok": "1.000000",
        }
        rows.append(row)
    summary = {
        "check": "summary",
        "model_name": parsed[0]["model_name"],
        "sequence_len": parsed[0]["sequence_len"],
        "batch_size": parsed[0]["batch_size"],
        "status": "ok",
        "status_ok": "1.000000",
    }
    for name in ("samples_per_sec", "step_time_ms", "step_time_msec", "tokens_per_sec", "peak_gpu_memory_gb"):
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
