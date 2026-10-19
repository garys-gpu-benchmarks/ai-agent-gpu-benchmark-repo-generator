#!/usr/bin/env python3
# File: scripts/collect_workload.py
# Description: Build and run mpirun-wrapped bin/rochpl, a single-GPU rocSOLVER
#              LU (dgetrf/dgetrs) Linpack, not upstream rocHPL. Cap timed repeats at large N.
from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
from pathlib import Path

METRIC_COLUMNS = [
    "sustained_fp64_performance_across_problem_size_n_tflops",
    "percent_of_gpu_fp64_matrix_peak",
    "time_to_solution_across_problem_size_n_s",
]


def detect_gpu_name() -> str:
    """Return probe text that names the GPU. Empty when every probe misses.

    amd-smi is the ROCm 10 tool. rocm-smi is the older name. A virtual-function
    MI300X advertises itself as AMD Instinct MI300X VF.
    """
    for command in (
        ["amd-smi", "static", "--asic"],
        ["rocm-smi", "--showproductname"],
        ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
        ["rocminfo"],
    ):
        try:
            completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            continue
        text = (completed.stdout or "") + "\n" + (completed.stderr or "")
        lowered = text.lower()
        if any(token in lowered for token in ("mi300", "instinct", "h100", "nvidia")):
            return text
    return ""


def matrix_peak_percent(tflops: float) -> object:
    from metric_contract import fp64_matrix_peak

    peak = fp64_matrix_peak(detect_gpu_name())
    if isinstance(peak, str):
        return peak
    return 100.0 * tflops / float(peak)


def parse_score(text: str) -> dict[str, float]:
    gflops = None
    seconds = None
    match = re.search(r"Final Score:\s*([0-9.eE+-]+)\s*GFLOPS", text)
    if match:
        gflops = float(match.group(1))
    match = re.search(r"WR\S+\s+\d+\s+\d+\s+\d+\s+\d+\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)", text)
    if match:
        seconds = float(match.group(1))
        if gflops is None:
            gflops = float(match.group(2))
    if gflops is None or seconds is None:
        raise ValueError("bin/rochpl score not found")
    tflops = gflops / 1000.0
    return {
        METRIC_COLUMNS[0]: tflops,
        METRIC_COLUMNS[1]: matrix_peak_percent(tflops),
        METRIC_COLUMNS[2]: seconds,
    }


def timed_repeats(problem_n: int, num_iterations: int, profile: str) -> int:
    requested = max(1, int(num_iterations or 1))
    # N=65536 hung 228 min (host) then died with hipErrorIllegalAddress.
    # N=32768 smoke/baseline: cap 6 (~3-5 min). Extended: cap 16 (~12 min).
    if problem_n >= 65536:
        return 2
    if problem_n >= 32768:
        if str(profile).strip().lower() == "extended":
            return max(2, min(requested, 16))
        return max(2, min(requested, 6))
    return max(2, min(requested, 4))


def clamp_problem_n(problem_n: int) -> int:
    if problem_n >= 65536:
        print(
            f"[WARN] clamping problem_size_N from {problem_n} to 32768 "
            "(N=65536 is multi-hour / hipErrorIllegalAddress on this overlay)",
            flush=True,
        )
        return 32768
    return problem_n


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect rocSOLVER LU FP64 (bin/rochpl) samples.")
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
    parser.add_argument("--output-format", default="csv")
    args = parser.parse_args()
    env = os.environ.copy()
    env["PATH"] = "/opt/rocm/bin:" + env.get("PATH", "")
    env["LD_LIBRARY_PATH"] = "/opt/rocm/lib:/opt/rocm/lib64:" + env.get("LD_LIBRARY_PATH", "")
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["bash", "-c", "source scripts/lib/hipcc_host_gcc.sh && bash scripts/build.sh"],
        check=True,
        env=env,
    )
    Path("HPL.dat").write_text(Path("HPL.dat").read_text(encoding="utf-8"), encoding="utf-8")
    command = [
        "mpirun", "--allow-run-as-root", "-np", args.num_gpus,
        "bin/rochpl",
        "--N", args.problem_size_N,
        "--NB", args.block_size,
        "--P", args.process_grid_P,
        "--Q", args.process_grid_Q,
        "--pfact", args.panel_factorization,
    ]
    problem_n = clamp_problem_n(int(float(args.problem_size_N or 4096)))
    command[command.index("--N") + 1] = str(problem_n)
    repeats = timed_repeats(problem_n, int(args.num_iterations or 1), str(args.profile or "smoke"))
    print(
        f"[INFO] rocSOLVER LU (bin/rochpl) N={problem_n} timed_repeats={repeats} "
        f"(requested num_iterations={args.num_iterations})",
        flush=True,
    )
    texts = []
    rows = []
    solve_timeout = 180 if problem_n >= 32768 else 60
    for _warmup in range(int(args.warmup_iters or 0)):
        subprocess.run(command, check=False, capture_output=True, text=True, env=env, timeout=solve_timeout)
    for _repeat in range(repeats):
        try:
            completed = subprocess.run(
                command, check=False, capture_output=True, text=True, env=env, timeout=solve_timeout
            )
        except subprocess.TimeoutExpired:
            Path(args.raw_file).write_text(
                "\n".join(texts) + f"\n[FAIL] bin/rochpl timed out after {solve_timeout}s\n",
                encoding="utf-8",
                newline="\n",
            )
            print(f"[FAIL] bin/rochpl N={problem_n} timed out after {solve_timeout}s", flush=True)
            return 1
        block = "$ " + " ".join(command) + "\n" + (completed.stdout or "") + "\n" + (completed.stderr or "")
        texts.append(block)
        if completed.returncode != 0 or "Residual Check: PASSED" not in (completed.stdout or ""):
            Path(args.raw_file).write_text("\n".join(texts), encoding="utf-8", newline="\n")
            print(block)
            return 1
        metrics = parse_score((completed.stdout or "") + "\n" + (completed.stderr or ""))
        rows.append({"sample_index": len(rows), "status": "ok", **metrics, "error_message": ""})
    csv_path = run_dir / "raw_results.csv"
    fieldnames = ["sample_index", "status", *METRIC_COLUMNS, "error_message"]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    Path(args.raw_file).write_text(
        "\n".join(texts) + "\n" + csv_path.read_text(encoding="utf-8"),
        encoding="utf-8",
        newline="\n",
    )
    print(f"[PASS] collected {len(rows)} rocSOLVER LU samples into {args.raw_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
