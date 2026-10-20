#!/usr/bin/env python3
# File: scripts/collect_workload.py
# Description: Two independent NVIDIA health samples. No duplicated row.
from __future__ import annotations

import argparse
import csv
import io
import re
import subprocess
import time
from pathlib import Path

import yaml


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


def first_float(pattern, text, default=0.0):
    match = re.search(pattern, text, re.I)
    if not match:
        return default
    try:
        return float(match.group(1))
    except (TypeError, ValueError):
        return default


def sample(run_dir: Path, index: int) -> dict:
    smi = run_command(["nvidia-smi", "--query-gpu=temperature.gpu,count,pcie.link.width.current,pcie.link.gen.current", "--format=csv,noheader,nounits"])[1]
    smi_q = run_command(["nvidia-smi", "-q"])[1]
    listed = run_command(["nvidia-smi", "-L"])[1]
    dmesg_rc, dmesg = run_command(["dmesg"])
    (run_dir / f"health_{index}.txt").write_text(smi + "\n" + smi_q, encoding="utf-8")
    gpus = float(len(re.findall(r"^GPU \d+:", listed, re.M)) or 0)
    if gpus <= 0:
        raise SystemExit("[FAIL] nvidia-smi -L reported no GPUs")
    # --query-gpu CSV is positional: temperature.gpu, count, pcie.link.width.current,
    # pcie.link.gen.current (e.g. "30, 1, 16, 5"). The old code searched `nvidia-smi -q`
    # for "Link Width : N", but -q prints Max/Current on separate lines, so it fell back
    # to the first comma-separated number -- the temperature -- and reported speed 0.
    fields = [f.strip() for f in (smi.strip().splitlines() or [""])[0].split(",")]

    def csv_float(index: int):
        try:
            return float(fields[index])
        except (IndexError, ValueError):
            return None

    temp = csv_float(0)
    if temp is None:
        temp = first_float(r"GPU Current Temp\s*:\s*([0-9.]+)", smi_q, 0.0)
    width = csv_float(2)
    if width is None:
        match = re.search(r"Link Width\s*\n\s*Max\s*:[^\n]*\n\s*Current\s*:\s*([0-9]+)", smi_q)
        width = float(match.group(1)) if match else ""
    speed = csv_float(3)
    if speed is None:
        speed = first_float(r"PCIe Generation\s*\n\s*Max\s*:[^\n]*\n\s*Current\s*:\s*([0-9.]+)", smi_q, 0.0)
    # Report GT/s (as the AMD twin does), not the bare PCIe generation number.
    speed = {1: 2.5, 2: 5.0, 3: 8.0, 4: 16.0, 5: 32.0, 6: 64.0}.get(int(speed or 0), speed)
    xids = xid_count(dmesg_rc, dmesg)
    return {
        "status": "ok",
        "dmesg_nvidia_gpu_fault_xid_count": xids,
        "gpu_temperature_c": temp,
        "cuda_devices_visible": gpus,
        "pcie_link_width_lanes": width,
        "pcie_link_speed_gt_s": speed,
        "error_message": "",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--raw-file", required=True)
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--device", default="gpu")
    parser.add_argument("--output-format", default="csv")
    args = parser.parse_args()
    yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    rows = [sample(run_dir, 0)]
    time.sleep(1.0)
    rows.append(sample(run_dir, 1))
    header = [
        "sample_index", "status", "dmesg_nvidia_gpu_fault_xid_count",
        "gpu_temperature_c", "cuda_devices_visible",
        "pcie_link_width_lanes", "pcie_link_speed_gt_s", "error_message",
    ]
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
