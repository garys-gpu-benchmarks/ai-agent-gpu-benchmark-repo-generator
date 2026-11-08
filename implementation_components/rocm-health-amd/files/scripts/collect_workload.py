#!/usr/bin/env python3
# File: scripts/collect_workload.py
# Description: AMD ROCm GPU health (102 / 302). Samples amd-smi, rocminfo, and the
# sysfs PCIe link of every AMD GPU once per second for monitor_duration_sec, then
# checks the fewest visible GPUs against expected_gpu_count and the narrowest link
# against min_pcie_link_width.
from __future__ import annotations

import argparse
import csv
import io
import re
import subprocess
import time
from pathlib import Path

import yaml

AMD_PCI_VENDOR = "0x1002"
SAMPLE_INTERVAL_S = 1.0
DEFAULT_MONITOR_DURATION_S = 5.0
DEFAULT_EXPECTED_GPU_COUNT = 1
DEFAULT_MIN_PCIE_LINK_WIDTH = 16
FATAL_RE = re.compile(r"page fault|gpu hang|hardware reset|uncorrectable", re.IGNORECASE)

# Window results are repeated on every row so the harness mean equals them.
# The sample_* columns hold each one-second reading.
HEADER = [
    "sample_index", "status", "dmesg_gpu_fault_count", "gpu_temperature_c",
    "hsa_agents_visible_count", "pcie_link_width_lanes", "pcie_link_speed_gt_s",
    "queues_available_count", "window_new_dmesg_fault_count", "sample_elapsed_s",
    "sample_gpu_temperature_c", "sample_hsa_agents_visible_count",
    "sample_pcie_link_width_lanes", "sample_pcie_link_speed_gt_s", "error_message",
]


def pv(params, key, profile, default=""):
    raw = params.get(key, default)
    if isinstance(raw, dict):
        return raw.get(profile, raw.get("smoke", default))
    return default if raw is None else raw


def load_params(path):
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return cfg.get("sweep") or {}


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


def parse_args():
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
                        help="Fewest HSA GPU agents that must stay visible (yaml expected_gpu_count).")
    parser.add_argument("--min-pcie-link-width", default=None,
                        help="Narrowest acceptable PCIe link width, lanes (yaml min_pcie_link_width).")
    return parser.parse_args()


def run_command(command):
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 127, f"missing:{command[0]}"
    return completed.returncode, (completed.stdout or "") + "\n" + (completed.stderr or "")


def read_dmesg():
    code, text = run_command(["dmesg", "-T"])
    if code != 0:
        code, text = run_command(["dmesg"])
    return text


def fault_count(dmesg_text: str) -> float:
    return float(len([line for line in dmesg_text.splitlines() if FATAL_RE.search(line)]))


def max_temperature(text: str):
    """Hottest reading in amd-smi output. amd-smi 27 reports EDGE: N/A on the MI300X VF
    and the live temperature on HOTSPOT, so HOTSPOT is preferred, then EDGE/JUNCTION."""
    for pattern in (r"HOTSPOT\s*:\s*([0-9]+(?:\.[0-9]+)?)", r"(?:EDGE|JUNCTION)\s*:\s*([0-9]+(?:\.[0-9]+)?)"):
        values = [float(v) for v in re.findall(pattern, text, re.IGNORECASE)]
        if values:
            return max(values)
    match = re.search(r"(?:edge|Temperature).*?([0-9]+(?:\.[0-9]+)?)", text, re.IGNORECASE)
    return float(match.group(1)) if match else ""


def amd_gpu_links(drm_root: Path = Path("/sys/class/drm")) -> list[tuple]:
    """(width, speed GT/s) for each AMD GPU card. Connector entries (card0-DP-1) and
    other vendors' display devices (a VM's virtual VGA) are skipped."""
    links, seen = [], set()
    for card in sorted(drm_root.glob("card*")):
        if not re.fullmatch(r"card\d+", card.name):
            continue
        device = card / "device"
        try:
            if (device / "vendor").read_text(encoding="utf-8").strip().lower() != AMD_PCI_VENDOR:
                continue
            key = str(device.resolve())
        except OSError:
            continue
        if key in seen:
            continue
        seen.add(key)
        width = speed = ""
        try:
            width = float((device / "current_link_width").read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            pass
        try:
            match = re.search(r"([0-9]+(?:\.[0-9]+)?)", (device / "current_link_speed").read_text(encoding="utf-8"))
            speed = float(match.group(1)) if match else ""
        except OSError:
            pass
        links.append((width, speed))
    return links


def take_sample(elapsed: float) -> dict:
    amd_text = run_command(["amd-smi", "metric"])[1]
    if amd_text.startswith("missing:"):
        amd_text = run_command(["/opt/rocm/bin/amd-smi", "metric"])[1]
    info_text = run_command(["rocminfo"])[1]
    links = amd_gpu_links()
    widths = [w for w, _ in links if w != ""]
    speeds = [s for _, s in links if s != ""]
    width = min(widths) if widths else ""
    if width == "":
        match = re.search(r"Current(?:\s+Link)?\s+Width\s*[:=]\s*(\d+)", amd_text + "\n" + info_text, re.I)
        width = float(match.group(1)) if match else ""
    return {
        "elapsed": round(elapsed, 2),
        "temperature": max_temperature(amd_text + "\n" + info_text),
        "agents": float(len(re.findall(r"Device Type:\s*GPU", info_text))),
        "width": width,
        "speed": min(speeds) if speeds else "",
        "queues": float(len(re.findall(r"Queue", info_text))),
    }


def window_result(samples: list[dict], expected_gpu_count: int, min_link_width: int) -> dict:
    """Peak temperature, narrowest/slowest link, fewest agents, and the pass/fail verdict."""
    def known(key):
        return [s[key] for s in samples if s[key] != ""]

    temps, widths, speeds, agents = known("temperature"), known("width"), known("speed"), known("agents")
    fewest = min(agents) if agents else 0.0
    narrowest = min(widths) if widths else ""
    failures, notes = [], []
    if fewest < 1:
        failures.append("rocminfo reported no GPU HSA agents")
    elif fewest < expected_gpu_count:
        failures.append(f"only {fewest:g} HSA GPU agent(s) visible, expected_gpu_count is {expected_gpu_count}")
    if narrowest == "":
        notes.append("PCIe link width not readable; min_pcie_link_width check skipped")
    elif narrowest < min_link_width:
        failures.append(f"PCIe link width x{narrowest:g} is narrower than min_pcie_link_width x{min_link_width}")
    return {
        "gpu_temperature_c": max(temps) if temps else "",
        "hsa_agents_visible_count": fewest,
        "pcie_link_width_lanes": narrowest,
        "pcie_link_speed_gt_s": min(speeds) if speeds else "",
        "queues_available_count": min(known("queues")) if known("queues") else "",
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


def rows_for(samples, result, dmesg_faults, new_faults) -> list[dict]:
    rows = []
    for index, sample in enumerate(samples):
        rows.append({
            "sample_index": index, "status": result["status"],
            "dmesg_gpu_fault_count": dmesg_faults,
            "gpu_temperature_c": result["gpu_temperature_c"],
            "hsa_agents_visible_count": result["hsa_agents_visible_count"],
            "pcie_link_width_lanes": result["pcie_link_width_lanes"],
            "pcie_link_speed_gt_s": result["pcie_link_speed_gt_s"],
            "queues_available_count": result["queues_available_count"],
            "window_new_dmesg_fault_count": new_faults,
            "sample_elapsed_s": sample["elapsed"],
            "sample_gpu_temperature_c": sample["temperature"],
            "sample_hsa_agents_visible_count": sample["agents"],
            "sample_pcie_link_width_lanes": sample["width"],
            "sample_pcie_link_speed_gt_s": sample["speed"],
            "error_message": result["error_message"],
        })
    return rows


def write_csv(path, rows):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=HEADER, extrasaction="ignore", lineterminator=chr(10))
    writer.writeheader()
    writer.writerows(rows)
    text = buf.getvalue()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")
    print(text, end="")


def main() -> int:
    args = parse_args()
    duration, expected, min_width = settings(args, load_params(args.config))
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] monitor_duration_sec={duration:g} expected_gpu_count={expected} min_pcie_link_width={min_width}")
    before = fault_count(read_dmesg())
    samples = monitor(duration)
    dmesg_text = read_dmesg()
    (run_dir / "dmesg.txt").write_text(dmesg_text, encoding="utf-8")
    after = fault_count(dmesg_text)
    result = window_result(samples, expected, min_width)
    write_csv(args.raw_file, rows_for(samples, result, after, max(0.0, after - before)))
    if result["status"] != "ok":
        print(f"[FAIL] {result['error_message']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
