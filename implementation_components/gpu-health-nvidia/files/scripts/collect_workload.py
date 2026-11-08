#!/usr/bin/env python3
# File: scripts/collect_workload.py
# Description: NVIDIA GPU health (202 / 402). Samples nvidia-smi for every GPU once per
# second for monitor_duration_sec, then checks the fewest visible devices against
# expected_gpu_count and the narrowest PCIe link against min_pcie_link_width.
from __future__ import annotations

import argparse
import csv
import io
import re
import subprocess
import time
from pathlib import Path

import yaml

SAMPLE_INTERVAL_S = 1.0
DEFAULT_MONITOR_DURATION_S = 5.0
DEFAULT_EXPECTED_GPU_COUNT = 1
DEFAULT_MIN_PCIE_LINK_WIDTH = 16
QUERY = "--query-gpu=temperature.gpu,pcie.link.width.current,pcie.link.gen.current"
GEN_TO_GT_S = {1: 2.5, 2: 5.0, 3: 8.0, 4: 16.0, 5: 32.0, 6: 64.0}

# Window results are repeated on every row so the harness mean equals them.
# The sample_* columns hold each one-second reading.
HEADER = [
    "sample_index", "status", "dmesg_nvidia_gpu_fault_xid_count",
    "gpu_temperature_c", "cuda_devices_visible",
    "pcie_link_width_lanes", "pcie_link_speed_gt_s", "window_new_xid_count",
    "sample_elapsed_s", "sample_gpu_temperature_c", "sample_cuda_devices_visible",
    "sample_pcie_link_width_lanes", "sample_pcie_link_speed_gt_s", "error_message",
]


def run_command(command, timeout=60):
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return 127, f"{command[0]}: {exc}"
    return completed.returncode, (completed.stdout or "") + "\n" + (completed.stderr or "")


# The driver logs a GPU fault as "NVRM: Xid (PCI:0000:01:00): 79, pid=..., ...".
# Counting every "xid" word in dmesg also counted unrelated lines that mention one.
XID_LINE = re.compile(r"\bNVRM:\s*Xid\b", re.I)
DMESG_UNREADABLE = "na (expected: dmesg not readable)"


def xid_count(returncode: int, dmesg: str):
    """Number of NVRM Xid lines, or an expected na when dmesg could not be read."""
    lines = [line for line in dmesg.splitlines() if XID_LINE.search(line)]
    if returncode != 0 and not lines:
        return DMESG_UNREADABLE
    return float(len(lines))


def pv(params, key, profile, default=""):
    raw = params.get(key, default)
    if isinstance(raw, dict):
        return raw.get(profile, raw.get("smoke", default))
    return default if raw is None else raw


def number(raw, default):
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def settings(args, params) -> tuple[float, int, int]:
    """monitor_duration_sec, expected_gpu_count, min_pcie_link_width: CLI, then yaml, then default."""
    duration = number(args.monitor_duration_sec if args.monitor_duration_sec not in (None, "")
                      else pv(params, "monitor_duration_sec", args.profile, DEFAULT_MONITOR_DURATION_S),
                      DEFAULT_MONITOR_DURATION_S)
    expected = int(number(args.expected_gpu_count if args.expected_gpu_count not in (None, "")
                          else pv(params, "expected_gpu_count", args.profile, DEFAULT_EXPECTED_GPU_COUNT),
                          DEFAULT_EXPECTED_GPU_COUNT))
    width = int(number(args.min_pcie_link_width if args.min_pcie_link_width not in (None, "")
                       else pv(params, "min_pcie_link_width", args.profile, DEFAULT_MIN_PCIE_LINK_WIDTH),
                       DEFAULT_MIN_PCIE_LINK_WIDTH))
    return duration, expected, width


def parse_query(text: str) -> list[tuple]:
    """One (temperature, width, speed GT/s) per GPU line of the --query-gpu CSV.
    The CSV is positional: temperature.gpu, pcie.link.width.current, pcie.link.gen.current
    (e.g. "30, 16, 5"). Report GT/s (as the AMD twin does), not the bare PCIe generation."""
    gpus = []
    for line in text.strip().splitlines():
        fields = [f.strip() for f in line.split(",")]
        if len(fields) < 3:
            continue

        def value(index):
            try:
                return float(fields[index])
            except (IndexError, ValueError):
                return ""

        gen = value(2)
        speed = GEN_TO_GT_S.get(int(gen), gen) if gen != "" else ""
        gpus.append((value(0), value(1), speed))
    return gpus


def take_sample(elapsed: float) -> dict:
    query = run_command(["nvidia-smi", QUERY, "--format=csv,noheader,nounits"])[1]
    listed = run_command(["nvidia-smi", "-L"])[1]
    gpus = parse_query(query)
    temps = [t for t, _, _ in gpus if t != ""]
    widths = [w for _, w, _ in gpus if w != ""]
    speeds = [s for _, _, s in gpus if s != ""]
    speed = min(speeds) if speeds else ""
    return {
        "elapsed": round(elapsed, 2),
        "temperature": max(temps) if temps else "",
        "devices": float(len(re.findall(r"^GPU \d+:", listed, re.M))),
        "width": min(widths) if widths else "",
        "pcie_link_speed_gt_s": speed,
    }


def window_result(samples: list[dict], expected_gpu_count: int, min_link_width: int) -> dict:
    """Peak temperature, narrowest/slowest link, fewest devices, and the pass/fail verdict."""
    def known(key):
        return [s[key] for s in samples if s[key] != ""]

    temps, widths, speeds, devices = known("temperature"), known("width"), known("pcie_link_speed_gt_s"), known("devices")
    fewest = min(devices) if devices else 0.0
    narrowest = min(widths) if widths else ""
    failures, notes = [], []
    if fewest < 1:
        failures.append("nvidia-smi -L reported no GPUs")
    elif fewest < expected_gpu_count:
        failures.append(f"only {fewest:g} CUDA device(s) visible, expected_gpu_count is {expected_gpu_count}")
    if narrowest == "":
        notes.append("PCIe link width not readable; min_pcie_link_width check skipped")
    elif narrowest < min_link_width:
        failures.append(f"PCIe link width x{narrowest:g} is narrower than min_pcie_link_width x{min_link_width}")
    speed = min(speeds) if speeds else ""
    return {
        "gpu_temperature_c": max(temps) if temps else "",
        "cuda_devices_visible": fewest,
        "pcie_link_width_lanes": narrowest,
        "pcie_link_speed_gt_s": speed,
        "status": "error" if failures else "ok",
        "error_message": "; ".join(failures + notes),
    }


def monitor(duration_s: float, sampler=take_sample, clock=time.monotonic, sleep=time.sleep) -> list[dict]:
    """One sample per SAMPLE_INTERVAL_S until duration_s has passed; never fewer than two."""
    start = clock()
    samples = []
    while True:
        samples.append(sampler(clock() - start))
        if len(samples) >= 2 and clock() - start >= duration_s:
            return samples
        next_at = start + len(samples) * SAMPLE_INTERVAL_S
        sleep(max(0.0, next_at - clock()))


def new_xids(before, after):
    if isinstance(before, str) or isinstance(after, str):
        return DMESG_UNREADABLE
    return max(0.0, after - before)


def rows_for(samples, result, xids, new_xid_count) -> list[dict]:
    rows = []
    for index, sample in enumerate(samples):
        rows.append({
            "sample_index": index, "status": result["status"],
            "dmesg_nvidia_gpu_fault_xid_count": xids,
            "gpu_temperature_c": result["gpu_temperature_c"],
            "cuda_devices_visible": result["cuda_devices_visible"],
            "pcie_link_width_lanes": result["pcie_link_width_lanes"],
            "pcie_link_speed_gt_s": result["pcie_link_speed_gt_s"],
            "window_new_xid_count": new_xid_count,
            "sample_elapsed_s": sample["elapsed"],
            "sample_gpu_temperature_c": sample["temperature"],
            "sample_cuda_devices_visible": sample["devices"],
            "sample_pcie_link_width_lanes": sample["width"],
            "sample_pcie_link_speed_gt_s": sample["pcie_link_speed_gt_s"],
            "error_message": result["error_message"],
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--raw-file", required=True)
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--device", default="gpu")
    parser.add_argument("--output-format", default="csv")
    parser.add_argument("--monitor-duration-sec", default=None,
                        help="Seconds to keep sampling, once per second (yaml monitor_duration_sec).")
    parser.add_argument("--expected-gpu-count", default=None,
                        help="Fewest CUDA devices that must stay visible (yaml expected_gpu_count).")
    parser.add_argument("--min-pcie-link-width", default=None,
                        help="Narrowest acceptable PCIe link width, lanes (yaml min_pcie_link_width).")
    args = parser.parse_args()
    params = (yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}).get("sweep") or {}
    duration, expected, min_width = settings(args, params)
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] monitor_duration_sec={duration:g} expected_gpu_count={expected} min_pcie_link_width={min_width}")
    (run_dir / "health_first.txt").write_text(run_command(["nvidia-smi", "-q"])[1], encoding="utf-8")
    before = xid_count(*run_command(["dmesg"]))
    samples = monitor(duration)
    dmesg_rc, dmesg = run_command(["dmesg"])
    (run_dir / "dmesg.txt").write_text(dmesg, encoding="utf-8")
    (run_dir / "health_last.txt").write_text(run_command(["nvidia-smi", "-q"])[1], encoding="utf-8")
    after = xid_count(dmesg_rc, dmesg)
    result = window_result(samples, expected, min_width)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=HEADER, extrasaction="ignore", lineterminator=chr(10))
    writer.writeheader()
    writer.writerows(rows_for(samples, result, after, new_xids(before, after)))
    Path(args.raw_file).parent.mkdir(parents=True, exist_ok=True)
    Path(args.raw_file).write_text(buf.getvalue(), encoding="utf-8")
    print(buf.getvalue(), end="")
    if result["status"] != "ok":
        print(f"[FAIL] {result['error_message']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
