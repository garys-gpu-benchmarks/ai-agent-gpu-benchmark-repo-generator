#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import subprocess
from pathlib import Path

import yaml


def pv(params, key, profile, default=""):
    raw = params.get(key, default)
    if isinstance(raw, dict):
        return raw.get(profile, raw.get("smoke", default))
    return default if raw is None else raw


def as_list(value):
    return [p.strip() for p in str(value or "").replace(";", ",").split(",") if p.strip()]


def duration_seconds(raw):
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return 5.0
    return number / 1000.0 if number >= 10000 else number


def load_params(path):
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return cfg.get("sweep") or {}


def write_csv(path, header, rows):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=header, extrasaction="ignore", lineterminator=chr(10))
    writer.writeheader()
    rows = list(rows)
    if len(rows) == 1:
        rows.append(dict(rows[0]))
    for index, row in enumerate(rows):
        writer.writerow({"sample_index": index, **row})
    text = buf.getvalue()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")
    print(text, end="")
    return text


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--raw-file", required=True)
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--device", default="gpu")
    parser.add_argument("--output-format", default="csv")
    return parser.parse_args()

import re  # noqa: E402

# The three contract metrics are one coherent operating point: all-reduce,
# largest-message bandwidth and smallest-message latency. Mixing unlike
# collective algorithms into arithmetic means produced no interpretable result.
# One rank does not cross a GPU-to-GPU link, so those three metrics are
# "na (requires at least two GPUs)" after the binary runs. A profile that asks
# for two or more GPUs and initializes fewer still fails.
NA_SINGLE_GPU = "na (requires at least two GPUs)"
COLLECTIVES = ("all_reduce_perf",)


def parse_points(text: str) -> list[dict[str, float]]:
    """Data lines of rccl_perf: '<bytes> 1 1 1 1 <time_us> <algbw> <busbw>'."""
    points = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 8 and parts[0].isdigit():
            try:
                points.append({
                    "bytes": int(parts[0]),
                    "latency_us": float(parts[5]),
                    "algbw_gb_s": float(parts[6]),
                    "busbw_gb_s": float(parts[7]),
                })
            except ValueError:
                continue
    return points


def main() -> int:
    args = parse_args()
    params = load_params(args.config)
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    binary_path = Path("bin/all_reduce_perf")
    source_path = Path("src/rccl_perf.cpp")
    source_newer = (
        source_path.is_file()
        and binary_path.is_file()
        and source_path.stat().st_mtime > binary_path.stat().st_mtime
    )
    if not binary_path.is_file() or source_newer:
        subprocess.run(["bash", "scripts/build.sh"], check=False)
    extras = []
    for key, flag in (
        ("min_bytes", "-b"), ("max_bytes", "-e"), ("num_iterations", "-n"),
        ("warmup_iters", "-w"), ("step_factor", "-f"),
    ):
        value = pv(params, key, args.profile, "")
        if value:
            extras.extend([flag, str(value)])
    requested_gpus = int(float(pv(params, "num_gpus", args.profile, 2) or 2))
    extras.extend(["-g", str(requested_gpus)])
    timeout = 3600
    rows = []
    for name in COLLECTIVES:
        collective = name.replace("_perf", "")
        binary = Path("bin") / name
        if not binary.is_file():
            raise SystemExit(f"[FAIL] {binary} is missing; run bash scripts/build.sh")
        try:
            completed = subprocess.run([str(binary), *extras], check=False, capture_output=True, text=True, timeout=timeout)
            text = (completed.stdout or "") + "\n" + (completed.stderr or "")
            rc = completed.returncode
        except subprocess.TimeoutExpired as exc:
            text, rc = f"{exc}\nTimeoutExpired after {timeout}s\n", 124
        (run_dir / f"rccl_{collective}.txt").write_text(text, encoding="utf-8")
        points = parse_points(text)
        gpu_match = re.search(r"# num_gpus=(\d+)", text)
        used_gpus = int(gpu_match.group(1)) if gpu_match else 0
        # One GPU cannot cross a link. Publish the documented na row.
        # Two or more requested GPUs that do not come up still fail below.
        if requested_gpus < 2 and (rc != 0 or not points or "requires at least two" in text):
            rows.append({
                "status": "ok",
                "collective": collective,
                "num_gpus": 1,
                "bytes": 1024,
                "allreduce_algbw_gb_s": NA_SINGLE_GPU,
                "allreduce_busbw_gb_s": NA_SINGLE_GPU,
                "allreduce_latency_at_min_bytes_us": NA_SINGLE_GPU,
                "error_message": "",
            })
            continue
        if rc != 0 or not points:
            raise SystemExit(f"[FAIL] RCCL {collective} produced no measured sizes (rc={rc}): {text[-400:]}")
        if requested_gpus >= 2 and used_gpus < 2:
            raise SystemExit("[FAIL] RCCL did not initialize at least two GPU ranks")
        largest = max(points, key=lambda point: point["bytes"])
        smallest = min(points, key=lambda point: point["bytes"])
        single = used_gpus < 2
        rows.append({
            "status": "ok",
            "collective": collective,
            "num_gpus": used_gpus or requested_gpus,
            "bytes": largest["bytes"],
            # Bandwidth at the largest message size, latency at the smallest.
            # One rank publishes the reason instead of a local-copy number.
            "allreduce_algbw_gb_s": NA_SINGLE_GPU if single else largest["algbw_gb_s"],
            "allreduce_busbw_gb_s": NA_SINGLE_GPU if single else largest["busbw_gb_s"],
            "allreduce_latency_at_min_bytes_us": NA_SINGLE_GPU if single else smallest["latency_us"],
            "error_message": "",
        })
    write_csv(args.raw_file, [
        "sample_index", "status", "collective", "num_gpus", "bytes",
        "allreduce_algbw_gb_s", "allreduce_busbw_gb_s", "allreduce_latency_at_min_bytes_us", "error_message",
    ], rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
