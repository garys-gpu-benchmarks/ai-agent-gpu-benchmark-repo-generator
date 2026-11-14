#!/usr/bin/env python3
"""Collect overlay train_resnet50.py RESULT samples."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from pathlib import Path

import yaml

METRIC_FIELDS = [
    "step_time_msec",
    "images_per_sec",
    "fp16_tflops",
    "modeled_weight_feature_traffic_gb_s",
    "peak_gpu_memory_gb",
]
PARAM_FIELDS = ["check", "image_size", "batch_size", "precision", "status"]
RESULT_RE = re.compile(
    r"RESULT dataset_name=(?P<dataset_name>\S+) precision=(?P<precision>\S+) "
    r"image_size=(?P<image_size>\S+) batch_size=(?P<batch_size>\S+) "
    r"num_workers=(?P<num_workers>\S+) optimizer=(?P<optimizer>\S+) "
    r"learning_rate=(?P<learning_rate>\S+) gradient_accumulation=(?P<gradient_accumulation>\S+) "
    r"warmup_iters=(?P<warmup_iters>\S+) num_iterations=(?P<num_iterations>\S+) "
    r"step_time_msec=(?P<step_time_msec>[0-9.eE+-]+) images_per_sec=(?P<images_per_sec>[0-9.eE+-]+) "
    r"fp16_tflops=(?P<fp16_tflops>[0-9.eE+-]+) memory_bandwidth_gb_s=(?P<memory_bandwidth_gb_s>[0-9.eE+-]+) "
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
    parser.add_argument("--dataset-name", default="")
    parser.add_argument("--precision", default="")
    parser.add_argument("--image-size", default="")
    parser.add_argument("--batch-size", default="")
    parser.add_argument("--num-workers", default="")
    parser.add_argument("--optimizer", default="")
    parser.add_argument("--learning-rate", default="")
    parser.add_argument("--gradient-accumulation", default="")
    parser.add_argument("--warmup-iters", default="")
    parser.add_argument("--num-iterations", default="")
    parser.add_argument("--device-id", default="0")
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
        str(repo / "scripts" / "train_resnet50.py"),
        "--dataset-name",
        args.dataset_name or pick(sweep, "dataset_name", profile, "synthetic"),
        "--precision",
        args.precision or pick(sweep, "precision", profile, "fp16"),
        "--image-size",
        args.image_size or pick(sweep, "image_size", profile, "64"),
        "--batch-size",
        args.batch_size or pick(sweep, "batch_size", profile, "2"),
        "--num-workers",
        args.num_workers or pick(sweep, "num_workers", profile, "true"),
        "--optimizer",
        args.optimizer or pick(sweep, "optimizer", profile, "true"),
        "--learning-rate",
        args.learning_rate or pick(sweep, "learning_rate", profile, "0.1"),
        "--gradient-accumulation",
        args.gradient_accumulation or pick(sweep, "gradient_accumulation", profile, "true"),
        "--warmup-iters",
        args.warmup_iters or pick(sweep, "warmup_iters", profile, "1"),
        "--num-iterations",
        args.num_iterations or pick(sweep, "num_iterations", profile, "3"),
        "--device-id",
        args.device_id or pick(sweep, "device_id", profile, "0"),
    ]
    transcripts = []
    parsed = []
    for index in range(1):  # one pass, one sample
        print("[RUN] " + " ".join(command))
        code, text = run(command)
        transcripts.append(f"===== resnet50-pass{index + 1} rc={code} =====\n{text}")
        print(text.rstrip())
        match = RESULT_RE.search(text)
        if code != 0 or match is None:
            raise SystemExit("[FAIL] train_resnet50.py did not emit a RESULT line.")
        parsed.append(match.groupdict())
    rows = []
    for index, item in enumerate(parsed, start=1):
        row = {
            "check": f"pass{index}",
            "image_size": item["image_size"],
            "batch_size": item["batch_size"],
            "precision": item["precision"],
            "status": item["status"],
        }
        source_names = {
            "modeled_weight_feature_traffic_gb_s": "memory_bandwidth_gb_s",
        }
        for name in METRIC_FIELDS:
            row[name] = f"{float(item[source_names.get(name, name)]):.6f}"
        rows.append(row)
    summary = {
        "check": "summary",
        "image_size": parsed[0]["image_size"],
        "batch_size": parsed[0]["batch_size"],
        "precision": parsed[0]["precision"],
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
