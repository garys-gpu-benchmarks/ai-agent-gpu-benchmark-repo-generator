#!/usr/bin/env python3
# File: scripts/collect_workload.py
# Description: Run bin/nccl_bw (libnccl). Fail if NCCL did not run.
from __future__ import annotations

import argparse
import csv
import io
import re
import subprocess
from pathlib import Path

import yaml

# One rank does not cross a GPU-to-GPU link. The binary still runs; the three
# metrics are this text. A profile that asks for two or more GPUs and gets
# fewer still fails.
NA_SINGLE_GPU = "na (requires at least two GPUs)"


def pv(params, key, profile, default=""):
    raw = params.get(key, default)
    if isinstance(raw, dict):
        return raw.get(profile, raw.get("smoke", default))
    return default if raw is None else raw


def as_list(value):
    return [p.strip() for p in str(value or "").replace(";", ",").split(",") if p.strip()]


def parse_line(text: str) -> dict[str, float | str]:
    out: dict[str, float | str] = {}
    match = re.search(r"collective=(\S+)", text)
    if match:
        out["collective"] = match.group(1)
    for key in ("num_gpus", "bytes", "algbw_gb_s", "busbw_gb_s", "latency_us"):
        found = re.search(rf"{key}=([0-9.eE+-]+)", text)
        if found:
            out[key] = float(found.group(1))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--raw-file", required=True)
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--device", default="gpu")
    parser.add_argument("--output-format", default="csv")
    args = parser.parse_args()
    sweep = (yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}).get("sweep") or {}
    min_bytes = max(8, int(float(pv(sweep, "min_bytes", args.profile, 1024) or 1024)))
    max_bytes = max(min_bytes, int(float(pv(sweep, "max_bytes", args.profile, min_bytes) or min_bytes)))
    warmup = max(0, int(float(pv(sweep, "warmup_iters", args.profile, 1) or 1)))
    iters = max(1, int(float(pv(sweep, "num_iterations", args.profile, 2) or 2)))
    num_gpus = int(float(pv(sweep, "num_gpus", args.profile, 1) or 1))
    # Keep the three headline metrics at one defined operating point. A mean
    # across all-reduce, gather, broadcast, reduce, and reduce-scatter has no
    # common algorithmic-bandwidth or latency interpretation.
    collectives = ["all_reduce"]
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    if not Path("bin/nccl_bw").is_file():
        subprocess.run(["bash", "scripts/build.sh"], check=True)
    if not Path("bin/nccl_bw").is_file():
        raise SystemExit("[FAIL] bin/nccl_bw missing; cudaMemcpy is not NCCL")
    rows = []
    step = max(2, int(float(pv(sweep, "step_factor", args.profile, 2) or 2)))
    sizes = []
    size = min_bytes
    while size <= max_bytes:
        sizes.append(size)
        size *= step
    if sizes[-1] != max_bytes:
        sizes.append(max_bytes)
    # Sweep min_bytes..max_bytes (the old code ran min_bytes only, so "bus
    # bandwidth" was an 8-byte-message figure of ~0.001 GB/s). Iterations are
    # scaled down with message size so every size costs roughly the same wall
    # time; the sweep therefore takes ~2x one min_bytes call, and the repeat
    # rounds are halved to keep baseline/extended durations where they were.
    rounds = {"smoke": 1, "baseline": 10, "extended": 24}.get(str(args.profile), 1)
    sweep_log = run_dir / "nccl_sweep.csv"
    sweep_log.write_text("round,collective,bytes,iterations,algbw_gb_s,busbw_gb_s,latency_us\n", encoding="utf-8")
    single_gpu_seen = False
    for round_index in range(rounds):
        if single_gpu_seen:
            # One GPU publishes only na; more rounds cannot change that. 216/416
            # spent 17-21 minutes of extended repeating the same na result.
            print(
                f"[INFO] one GPU: stopped after round 1 of {rounds}; "
                "every metric is na (requires at least two GPUs)",
                flush=True,
            )
            break
        for name in collectives or ["all_reduce"]:
            points = []
            for nbytes in sizes:
                size_iters = max(20, int(iters * min_bytes / nbytes)) if iters >= 20 else iters
                completed = subprocess.run(
                    ["bin/nccl_bw", str(nbytes), str(warmup), str(size_iters), str(num_gpus), name],
                    check=False, capture_output=True, text=True, timeout=3600,
                )
                text = (completed.stdout or "") + "\n" + (completed.stderr or "")
                parsed = parse_line(text)
                if completed.returncode != 0 or "busbw_gb_s" not in parsed:
                    (run_dir / f"nccl_{name}.txt").write_text(text, encoding="utf-8")
                    raise SystemExit(f"[FAIL] NCCL {name} bytes={nbytes} did not report busbw: {text[-400:]}")
                points.append(parsed)
                with sweep_log.open("a", encoding="utf-8") as handle:
                    handle.write(
                        f"{round_index},{parsed.get('collective', name)},{int(parsed.get('bytes', nbytes))},{size_iters},"
                        f"{parsed.get('algbw_gb_s', '')},{parsed['busbw_gb_s']},{parsed.get('latency_us', '')}\n"
                    )
            (run_dir / f"nccl_{name}.txt").write_text(text, encoding="utf-8")
            largest, smallest = points[-1], points[0]
            # GPUs nccl_bw actually used (num_gpus capped at the GPUs present).
            used_gpus = int(float(largest.get("num_gpus", 0) or 0))
            if num_gpus >= 2 and used_gpus < 2:
                raise SystemExit(
                    "[FAIL] NCCL initialized fewer than two GPUs; "
                    "refusing to publish one-rank bandwidth or latency."
                )
            single = used_gpus < 2
            single_gpu_seen = single_gpu_seen or single
            rows.append({
                "status": "ok",
                "collective": largest.get("collective", name),
                "num_gpus": used_gpus or num_gpus,
                "bytes": largest.get("bytes", sizes[-1]),
                # Bandwidth is reported at the largest message; latency at the smallest.
                # One rank publishes the reason instead of a local-copy number.
                "allreduce_busbw_gb_s": NA_SINGLE_GPU if single else largest["busbw_gb_s"],
                "allreduce_algbw_gb_s": NA_SINGLE_GPU if single else largest.get("algbw_gb_s", ""),
                "allreduce_latency_at_min_bytes_us": NA_SINGLE_GPU if single else smallest.get("latency_us", ""),
                "error_message": "",
            })
    header = [
        "sample_index", "status", "collective", "num_gpus", "bytes",
        "allreduce_busbw_gb_s", "allreduce_algbw_gb_s", "allreduce_latency_at_min_bytes_us", "error_message",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=header, extrasaction="ignore", lineterminator=chr(10))
    writer.writeheader()
    if len(rows) == 1:
        rows.append(dict(rows[0]))
    for index, row in enumerate(rows):
        writer.writerow({"sample_index": index, **row})
    Path(args.raw_file).write_text(buf.getvalue(), encoding="utf-8")
    print(buf.getvalue(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
