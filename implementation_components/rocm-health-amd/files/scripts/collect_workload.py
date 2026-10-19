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

def run_command(command):
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except FileNotFoundError:
        return 127, f"missing:{command[0]}"
    return completed.returncode, (completed.stdout or "") + "\n" + (completed.stderr or "")


def first_float(pattern, text, default=0.0):
    import re
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return default
    try:
        return float(match.group(1))
    except (TypeError, ValueError):
        return default


def main() -> int:
    args = parse_args()
    load_params(args.config)
    dmesg_code, dmesg_text = run_command(["dmesg", "-T"])
    if dmesg_code != 0:
        dmesg_code, dmesg_text = run_command(["dmesg"])
    import re
    fatal_re = re.compile(r"page fault|gpu hang|hardware reset|uncorrectable", re.IGNORECASE)
    dmesg_faults = float(len([line for line in dmesg_text.splitlines() if fatal_re.search(line)]))
    amd_text = run_command(["amd-smi", "metric"])[1]
    if amd_text.startswith("missing:"):
        amd_text = run_command(["/opt/rocm/bin/amd-smi", "metric"])[1]
    info_text = run_command(["rocminfo"])[1]
    combined = "\n".join([amd_text, info_text])
    # amd-smi 27 reports EDGE: N/A on this MI300X VF and the live temperature on HOTSPOT.
    temp = first_float(r"HOTSPOT\s*:\s*([0-9]+(?:\.[0-9]+)?)", combined, "")
    if temp == "":
        temp = first_float(r"(?:EDGE|JUNCTION)\s*:\s*([0-9]+(?:\.[0-9]+)?)", combined, "")
    if temp == "":
        temp = first_float(r"(?:edge|Temperature).*?([0-9]+(?:\.[0-9]+)?)", combined, "")
    agents = float(len(re.findall(r"Device Type:\s*GPU", info_text)))
    width = ""
    for path in sorted(Path("/sys/class/drm").glob("card*/device/current_link_width")):
        try:
            width = float(path.read_text(encoding="utf-8", errors="replace").strip())
            break
        except (OSError, ValueError):
            continue
    if width == "":
        match = re.search(r"Current(?:\s+Link)?\s+Width\s*[:=]\s*(\d+)", combined, re.I)
        width = float(match.group(1)) if match else ""
    speed = ""
    for path in sorted(Path("/sys/class/drm").glob("card*/device/current_link_speed")):
        try:
            speed_text = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)", speed_text)
        if match:
            speed = float(match.group(1))
            break
    queues = float(len(re.findall(r"Queue", info_text)))
    Path(args.run_dir).mkdir(parents=True, exist_ok=True)
    (Path(args.run_dir) / "dmesg.txt").write_text(dmesg_text, encoding="utf-8")
    status = "ok" if agents > 0 else "error"
    error_message = "" if agents > 0 else "rocminfo reported no GPU HSA agents"
    write_csv(args.raw_file, [
        "sample_index", "status", "dmesg_gpu_fault_count", "gpu_temperature_c",
        "hsa_agents_visible_count", "pcie_link_width_lanes", "pcie_link_speed_gt_s",
        "queues_available_count", "error_message",
    ], [{
        "status": status, "dmesg_gpu_fault_count": dmesg_faults, "gpu_temperature_c": temp,
        "hsa_agents_visible_count": agents, "pcie_link_width_lanes": width,
        "pcie_link_speed_gt_s": speed, "queues_available_count": queues,
        "error_message": error_message,
    }])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
