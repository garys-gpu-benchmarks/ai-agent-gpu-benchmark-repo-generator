#!/usr/bin/env python3
# File: scripts/collect_workload.py
# Description: Build and run the cuSOLVER dense-LU substitute with residual validation.
from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
from pathlib import Path


METRIC_COLUMNS = [
    "sustained_fp64_performance_across_problem_size_n_tflops",
    "percent_of_fp64_tensor_peak",
    "time_to_solution_across_problem_size_n_s",
]


def parse_score(text: str) -> dict[str, float]:
    gflops = None
    seconds = None
    peak = None
    match = re.search(r"Final Score:\s*([0-9.eE+-]+)\s*GFLOPS", text)
    if match:
        gflops = float(match.group(1))
    match = re.search(r"WR\S+\s+\d+\s+\d+\s+\d+\s+\d+\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)", text)
    if match:
        seconds = float(match.group(1))
        if gflops is None:
            gflops = float(match.group(2))
    # cuSOLVER Dgetrf runs on the FP64 tensor cores (Hopper: twice the vector
    # rate), so percent of peak divides by the tensor-core peak nvhpl prints as
    # peak_fp64_tflops. Dividing by the vector peak reported 101-102%.
    match = re.search(r"peak_fp64_tflops=([0-9.eE+-]+)", text)
    if match:
        peak = float(match.group(1))
    override = os.environ.get("BENCHMARK_PEAK_FP64_TFLOPS", "").strip()
    if override:
        peak = float(override)
    if gflops is None or seconds is None:
        raise ValueError("nvhpl score not found")
    if "Residual Check: FAILED" in text:
        raise ValueError("nvhpl residual failed")
    tflops = gflops / 1000.0
    # Unknown peak -> blank (stored as NULL), never 0: 0 would fail "is not positive" validation
    # and a guessed peak produced the old 165-185% readings.
    percent = 100.0 * tflops / peak if peak and peak > 0 else ""
    return {
        METRIC_COLUMNS[0]: tflops,
        METRIC_COLUMNS[1]: percent,
        METRIC_COLUMNS[2]: seconds,
    }


def timed_repeats(problem_n: int, num_iterations: int, profile: str) -> int:
    requested = max(1, int(num_iterations or 1))
    if problem_n >= 65536:
        return 2
    if problem_n >= 32768:
        if str(profile).strip().lower() == "extended":
            return max(2, min(requested, 16))
        return max(2, min(requested, 6))
    return max(2, min(requested, 4))


def clamp_problem_n(problem_n: int) -> int:
    if problem_n >= 65536:
        print(f"[WARN] clamping problem_size_N from {problem_n} to 32768", flush=True)
        return 32768
    return problem_n


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect NVIDIA cuSOLVER Linpack samples.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--raw-file", required=True)
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--num-gpus", default="1")
    parser.add_argument("--process-grid-P", default="1")
    parser.add_argument("--process-grid-Q", default="1")
    parser.add_argument("--precision", default="fp64")
    parser.add_argument("--problem-size-N", default="4096")
    parser.add_argument("--block-size", default="256")
    parser.add_argument("--panel-factorization", default="2")
    parser.add_argument("--warmup-iters", default="0")
    parser.add_argument("--num-iterations", default="1")
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--device", default="gpu")
    parser.add_argument("--output-format", default="csv")
    args = parser.parse_args()
    try:
        import yaml
        sweep = (yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}).get("sweep") or {}
        raw_n = sweep.get("problem_size_N", args.problem_size_N)
        if isinstance(raw_n, dict):
            raw_n = raw_n.get(args.profile, raw_n.get("smoke", args.problem_size_N))
        if raw_n:
            args.problem_size_N = str(raw_n)
        raw_i = sweep.get("num_iterations", args.num_iterations)
        if isinstance(raw_i, dict):
            raw_i = raw_i.get(args.profile, raw_i.get("smoke", args.num_iterations))
        if raw_i:
            args.num_iterations = str(raw_i)
    except Exception:
        pass
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["bash", "scripts/build.sh"], check=True)
    if not Path("bin/nvhpl").is_file():
        raise SystemExit("[FAIL] bin/nvhpl missing")
    problem_n = clamp_problem_n(int(float(args.problem_size_N or 4096)))
    command = [
        "bin/nvhpl",
        "--N", str(problem_n),
        "--NB", args.block_size,
        "--P", args.process_grid_P,
        "--Q", args.process_grid_Q,
        "--pfact", args.panel_factorization,
    ]
    repeats = timed_repeats(problem_n, int(args.num_iterations or 1), str(args.profile or "smoke"))
    print(f"[INFO] nvhpl N={problem_n} timed_repeats={repeats}", flush=True)
    rows = []
    solve_timeout = 180 if problem_n >= 32768 else 60
    for _warmup in range(int(args.warmup_iters or 0)):
        subprocess.run(command, check=False, capture_output=True, text=True, timeout=solve_timeout)
    for index in range(repeats):
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=solve_timeout)
        text = (completed.stdout or "") + "\n" + (completed.stderr or "")
        (run_dir / f"nvhpl_{index}.txt").write_text(text, encoding="utf-8")
        if completed.returncode != 0:
            raise SystemExit(f"[FAIL] nvhpl residual/solve failed:\n{text[-400:]}")
        score = parse_score(text)
        rows.append({
            "status": "ok",
            "solver_implementation": "cuSOLVER_Dgetrf_Dgetrs",
            "requested_problem_size_n": int(float(args.problem_size_N or 4096)),
            "actual_problem_size_n": problem_n,
            "timed_repeats": repeats,
            **score,
            "error_message": "",
        })
    header = [
        "sample_index", "status", "solver_implementation",
        "requested_problem_size_n", "actual_problem_size_n", "timed_repeats",
        *METRIC_COLUMNS, "error_message",
    ]
    import io
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=header, extrasaction="ignore", lineterminator=chr(10))
    writer.writeheader()
    for index, row in enumerate(rows):
        writer.writerow({"sample_index": index, **row})
    Path(args.raw_file).write_text(buf.getvalue(), encoding="utf-8")
    print(buf.getvalue(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
