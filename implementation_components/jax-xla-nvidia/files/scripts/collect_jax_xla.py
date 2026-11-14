#!/usr/bin/env python3
"""Collect JAX XLA forward-pass RESULT samples (AMD 126/326 and NVIDIA 226/426)."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from pathlib import Path

import yaml

METRIC_FIELDS = [
    "forward_latency_msec",
    "tokens_per_sec",
    "tflops",
    "jit_compile_msec",
    "peak_hbm_gb",
]
PARAM_FIELDS = [
    "check", "dtype", "sequence_len", "hidden_size", "tflops_method",
    "requested_iterations", "completed_iterations", "status",
]
RESULT_RE = re.compile(
    r"RESULT dtype=(?P<dtype>\S+) sequence_len=(?P<sequence_len>\S+) hidden_size=(?P<hidden_size>\S+) "
    r"num_layers=(?P<num_layers>\S+) batch_size=(?P<batch_size>\S+) "
    r"forward_latency_msec=(?P<forward_latency_msec>[0-9.eE+-]+) tokens_per_sec=(?P<tokens_per_sec>[0-9.eE+-]+) "
    r"tflops=(?P<tflops>[0-9.eE+-]+) tflops_method=(?P<tflops_method>\S+) "
    r"jit_compile_msec=(?P<jit_compile_msec>[0-9.eE+-]+) "
    r"requested_iterations=(?P<requested_iterations>\d+) completed_iterations=(?P<completed_iterations>\d+) "
    r"peak_hbm_gb=(?P<peak_hbm_gb>[0-9.eE+-]+|na) status=(?P<status>\w+)"
)

PEAK_NA_RE = re.compile(r"^PEAK_NA reason=(na \(.*\))\s*$", re.MULTILINE)


def fmt(value: str) -> str:
    """6-decimal number, or an "na (...)" reason unchanged."""
    return value if str(value).startswith("na (") else f"{float(value):.6f}"


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
    parser.add_argument("--device-id", default="")
    parser.add_argument("--dtype", default="")
    parser.add_argument("--model-config", default="")
    parser.add_argument("--activation-fn", default="")
    parser.add_argument("--vocab-size", default="")
    parser.add_argument("--sequence-len", default="")
    parser.add_argument("--hidden-size", default="")
    parser.add_argument("--num-layers", default="")
    parser.add_argument("--num-heads", default="")
    parser.add_argument("--head-dim", default="")
    parser.add_argument("--batch-size", default="")
    parser.add_argument("--warmup-iters", default="")
    parser.add_argument("--num-iterations", default="")
    parser.add_argument("--seed", default="")
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
        str(repo / "scripts" / "gpu-bench-jax-xla-forwardpass.py"),
        "--device-id",
        args.device_id or pick(sweep, "device_id", profile, "0"),
        "--dtype",
        args.dtype or pick(sweep, "dtype", profile, "FP16"),
        "--model-config",
        args.model_config or pick(sweep, "model_config", profile, "true"),
        "--activation-fn",
        args.activation_fn or pick(sweep, "activation_fn", profile, "true"),
        "--vocab-size",
        args.vocab_size or pick(sweep, "vocab_size", profile, "true"),
        "--sequence-len",
        args.sequence_len or pick(sweep, "sequence_len", profile, "16"),
        "--hidden-size",
        args.hidden_size or pick(sweep, "hidden_size", profile, "64"),
        "--num-layers",
        args.num_layers or pick(sweep, "num_layers", profile, "1"),
        "--num-heads",
        args.num_heads or pick(sweep, "num_heads", profile, "4"),
        "--head-dim",
        args.head_dim or pick(sweep, "head_dim", profile, "true"),
        "--batch-size",
        args.batch_size or pick(sweep, "batch_size", profile, "1"),
        "--warmup-iters",
        args.warmup_iters or pick(sweep, "warmup_iters", profile, "1"),
        "--num-iterations",
        args.num_iterations or pick(sweep, "num_iterations", profile, "3"),
        "--profile",
        profile,
        "--seed",
        args.seed or pick(sweep, "seed", profile, "42"),
    ]
    transcripts = []
    parsed = []
    for index in range(1):  # one pass, one sample
        print("[RUN] " + " ".join(command))
        code, text = run(command)
        transcripts.append(f"===== jax-pass{index + 1} rc={code} =====\n{text}")
        print(text.rstrip())
        match = RESULT_RE.search(text)
        if code != 0 or match is None:
            raise SystemExit("[FAIL] JAX XLA forward pass did not emit a RESULT line.")
        item = match.groupdict()
        if int(item["completed_iterations"]) <= 0:
            raise SystemExit("[FAIL] JAX XLA forward pass completed no iterations.")
        if item["peak_hbm_gb"] == "na":
            reason = PEAK_NA_RE.search(text)
            item["peak_hbm_gb"] = reason.group(1) if reason else "na (peak memory not reported)"
        parsed.append(item)
    rows = []
    for index, item in enumerate(parsed, start=1):
        row = {
            "check": f"pass{index}",
            "dtype": item["dtype"],
            "sequence_len": item["sequence_len"],
            "hidden_size": item["hidden_size"],
            "tflops_method": item["tflops_method"],
            "requested_iterations": item["requested_iterations"],
            "completed_iterations": item["completed_iterations"],
            "status": item["status"],
        }
        for name in METRIC_FIELDS:
            row[name] = fmt(item[name])
        rows.append(row)
    summary = {
        "check": "summary",
        "dtype": parsed[0]["dtype"],
        "sequence_len": parsed[0]["sequence_len"],
        "hidden_size": parsed[0]["hidden_size"],
        "tflops_method": parsed[0]["tflops_method"],
        "requested_iterations": parsed[0]["requested_iterations"],
        "completed_iterations": parsed[0]["completed_iterations"],
        "status": "ok",
    }
    for name in METRIC_FIELDS:
        values = [float(row[name]) for row in rows if not str(row[name]).startswith("na (")]
        summary[name] = f"{(sum(values) / len(values)):.6f}" if values else rows[0][name]
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
