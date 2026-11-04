#!/usr/bin/env python3
# File: scripts/collect_workload.py
# Description: Sweep CUDA memcpy with separate H2D/D2H/D2D columns.
from __future__ import annotations

import argparse
import csv
import io
import os
import re
import subprocess
from pathlib import Path

import yaml


BANDWIDTH_SIZE_FLOOR = 256 * 1024**2
BANDWIDTH_ITERATION_FLOOR = 10


def pv(params, key, profile, default=""):
    raw = params.get(key, default)
    if isinstance(raw, dict):
        return raw.get(profile, raw.get("smoke", default))
    return default if raw is None else raw


DIRECTIONS = ("H2D", "D2H", "D2D")


def copy_plan(direction_raw, pinned_raw):
    """Directions to report, the copy kind that measures each, and every kind to run.

    direction: "all" or a comma list of H2D, D2H, D2D (same values as hip_memcpy_bw).
    pinned_memory: true uses cudaMallocHost for H2D/D2H; false uses malloc'd
    (pageable) host memory. D2D has no host buffer. Pinned and pageable H2D both
    run whenever H2D is reported, because the pinned-vs-pageable ratio needs both.
    """
    text = str(direction_raw or "all").strip()
    if text.lower() in {"all", "true", ""}:
        directions = list(DIRECTIONS)
    else:
        directions = []
        for token in text.replace(";", ",").split(","):
            token = token.strip().upper()
            if not token:
                continue
            if token not in DIRECTIONS:
                raise SystemExit(f"[FAIL] direction {token!r} is not one of all, H2D, D2H, D2D")
            if token not in directions:
                directions.append(token)
        if not directions:
            raise SystemExit("[FAIL] direction selected no copies")
    pinned = str(pinned_raw if pinned_raw is not None else "true").strip().lower() not in {"false", "0", "no", "off"}
    main = {d: d if (pinned or d == "D2D") else f"{d}_pageable" for d in directions}
    kinds = list(dict.fromkeys(main.values()))
    if "H2D" in directions:
        for kind in ("H2D", "H2D_pageable"):
            if kind not in kinds:
                kinds.append(kind)
    return directions, main, kinds, pinned


def parse_line(text: str) -> dict[str, float]:
    out = {}
    for key in ("bandwidth_gb_s", "latency_us", "elapsed_s", "bytes"):
        match = re.search(rf"{key}=([0-9.eE+-]+)", text)
        if match:
            out[key] = float(match.group(1))
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
    min_bytes = max(64, int(float(pv(sweep, "min_bytes", args.profile, 1024) or 1024)))
    max_bytes = max(
        min_bytes,
        BANDWIDTH_SIZE_FLOOR,
        int(float(pv(sweep, "max_bytes", args.profile, BANDWIDTH_SIZE_FLOOR) or BANDWIDTH_SIZE_FLOOR)),
    )
    step = max(2, int(float(pv(sweep, "step_factor", args.profile, 2) or 2)))
    warmup = max(0, int(float(pv(sweep, "warmup_iters", args.profile, 1) or 1)))
    iters = max(
        BANDWIDTH_ITERATION_FLOOR,
        int(float(pv(sweep, "num_iterations", args.profile, BANDWIDTH_ITERATION_FLOOR) or BANDWIDTH_ITERATION_FLOOR)),
    )
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    if not Path("bin/cuda_memcpy").is_file():
        subprocess.run(["bash", "scripts/build.sh"], check=True)
    if not Path("bin/cuda_memcpy").is_file():
        raise SystemExit("[FAIL] bin/cuda_memcpy missing; host memset is not a CUDA memcpy result")
    directions, main_kind, kinds, pinned = copy_plan(
        pv(sweep, "direction", args.profile, "all"), pv(sweep, "pinned_memory", args.profile, "true"))
    print(f"[INFO] cuda_memcpy: directions={','.join(directions)} pinned_memory={str(pinned).lower()} kinds={','.join(kinds)}", flush=True)
    rows = []
    device_env = os.environ.copy()
    device_env["CUDA_VISIBLE_DEVICES"] = str(pv(sweep, "device_id", args.profile, "0") or "0")
    size = min_bytes
    while size <= max_bytes:
        metrics = {}
        for kind in kinds:
            completed = subprocess.run(
                ["bin/cuda_memcpy", str(size), str(warmup), str(iters), kind],
                check=False, capture_output=True, text=True, timeout=3600, env=device_env,
            )
            text = (completed.stdout or "") + (completed.stderr or "")
            (run_dir / f"memcpy_{kind}_{size}.txt").write_text(text, encoding="utf-8")
            parsed = parse_line(text)
            if completed.returncode != 0 or "bandwidth_gb_s" not in parsed:
                raise SystemExit(f"[FAIL] cuda_memcpy {kind} {size}: {text[-300:]}")
            metrics[kind] = parsed
        ratio = ""
        if "H2D" in metrics and "H2D_pageable" in metrics:
            ratio = metrics["H2D"]["bandwidth_gb_s"] / max(metrics["H2D_pageable"]["bandwidth_gb_s"], 1e-9)
        rows.append({
            "status": "ok",
            "transfer_size_bytes": size,
            "_metrics": metrics,
            "pinned_vs_pageable_host_memory_bandwidth_gb_s": ratio,
            "pinned_vs_pageable_bandwidth_ratio": ratio,
            "error_message": "",
        })
        nxt = size * step
        if nxt <= size:
            break
        size = nxt
    # Bandwidth is reported at the largest transfer size and latency (time per
    # copy) at the smallest, each on that size's row only; the other rows are
    # blank. The parser's mean skips blanks, so the summary is the bandwidth at
    # max_bytes and the latency at min_bytes. A mean over every size let 1 KB
    # copies drag bandwidth down and 1 GB copies (milliseconds) swamp latency.
    # Every size's raw numbers stay in memcpy_<kind>_<size>.txt in the run dir.
    smallest = rows[0]["transfer_size_bytes"] if rows else None
    largest = rows[-1]["transfer_size_bytes"] if rows else None
    for row in rows:
        metrics = row.pop("_metrics")
        # A direction left out of yaml direction stays blank (not measured).
        if row["transfer_size_bytes"] == largest:
            for d in directions:
                row[f"bandwidth_{d.lower()}_gbps"] = metrics[main_kind[d]]["bandwidth_gb_s"]
        else:
            row["pinned_vs_pageable_host_memory_bandwidth_gb_s"] = ""
            row["pinned_vs_pageable_bandwidth_ratio"] = ""
        if row["transfer_size_bytes"] == smallest:
            for d in directions:
                row[f"latency_{d.lower()}_us"] = metrics[main_kind[d]]["latency_us"]
    header = [
        "sample_index", "status", "transfer_size_bytes", "bandwidth_h2d_gbps",
        "bandwidth_d2h_gbps", "bandwidth_d2d_gbps", "latency_h2d_us",
        "latency_d2h_us", "latency_d2d_us",
        "pinned_vs_pageable_host_memory_bandwidth_gb_s", "pinned_vs_pageable_bandwidth_ratio", "error_message",
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
