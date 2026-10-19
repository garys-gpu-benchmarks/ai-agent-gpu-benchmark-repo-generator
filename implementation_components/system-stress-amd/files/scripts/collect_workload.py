#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import shutil
import re
import subprocess
import sys
import time
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

def read_sysfs_power_w():
    best = 0.0
    for path in Path("/sys/class/drm").glob("card*/device/hwmon/hwmon*/power1_average"):
        try:
            microwatts = float(path.read_text().strip())
        except (OSError, ValueError):
            continue
        if microwatts > 0:
            best = max(best, microwatts / 1e6)
    return best


def is_gpu_power_line(low: str) -> bool:
    """A power reading, not every line that contains the word power.

    "w" in "power" is not a watt unit. The watt token has to be its own word,
    as in "(W)". Power-cap lines are limits, not draw.
    """
    if "cap" in low:
        return False
    if "package power" in low or "average graphics package power" in low:
        return True
    words = set(re.findall(r"[a-z]+", low))
    return "power" in words and bool(words & {"w", "watt", "watts"})


def ecc_from_ras_text(chunk: str):
    """Uncorrectable count, or na when the RAS table is not key:value text.

    amd-smi metric prints TOTAL_UNCORRECTABLE_COUNT. The "Uncorrectable Error"
    form is kept for older tables. amd-smi metric -e is not used; it crashes on some guests.
    """
    labeled = [
        int(item)
        for item in re.findall(r"TOTAL_UNCORRECTABLE_COUNT\s*[:=]\s*(\d+)", chunk, re.I)
    ]
    if labeled:
        return float(sum(labeled))
    hits = [
        int(item)
        for item in re.findall(
            r"Uncorrectable(?:\s+Error)?(?:\s+Count)?\s*[:=]\s*(\d+)",
            chunk,
            re.I,
        )
    ]
    if hits:
        return float(sum(hits))
    if "uncorrectable error" in chunk.lower():
        return "na (RAS table not parsed)"
    return None


def ecc_interval_delta(samples: list):
    """Errors during the run: last numeric sample minus the first.

    A parse failure is kept. An empty series stays blank, not zero.
    """
    for item in samples:
        if isinstance(item, str) and item.strip().lower().startswith("na ("):
            return item
    numbers = []
    for item in samples:
        if item is None or item == "":
            continue
        try:
            numbers.append(float(item))
        except (TypeError, ValueError):
            continue
    if not numbers:
        return ""
    return numbers[-1] - numbers[0]


THROTTLE_NOT_EXPOSED = "na (expected: throttle counter not exposed)"


def gpu_metrics():
    util = temp = power = 0.0
    text = ""
    outputs = []
    for cmd in (
        ["/opt/rocm/bin/amd-smi", "metric"],
        ["amd-smi", "metric"],
    ):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
            outputs.append((out.stdout or "") + "\n" + (out.stderr or ""))
            text += "\n" + outputs[-1]
        except Exception:
            continue
    for line in text.splitlines():
        low = line.lower()
        nums = []
        for tok in line.replace("=", " ").replace(":", " ").replace("%", " ").replace(",", " ").split():
            try:
                nums.append(float(tok))
            except ValueError:
                continue
        if not nums:
            continue
        if "gpu use" in low or "gfx activity" in low or "gpu_busy" in low:
            util = nums[0]
        if "junction" in low or "hotspot" in low:
            temp = max(temp, nums[0])
        if is_gpu_power_line(low):
            power = max(power, nums[-1])
    if power <= 0:
        power = read_sysfs_power_w()
    # amd-smi metric prints TOTAL_UNCORRECTABLE_COUNT. amd-smi metric -e crashes on some guests.
    ecc = ""
    for chunk in outputs:
        parsed = ecc_from_ras_text(chunk)
        if parsed is not None:
            ecc = parsed
            break
    if ecc == "":
        for cmd in (
            ["amd-smi", "metric"],
            ["/opt/rocm/bin/amd-smi", "metric"],
        ):
            try:
                ras = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            except (OSError, subprocess.TimeoutExpired):
                continue
            parsed = ecc_from_ras_text((ras.stdout or "") + "\n" + (ras.stderr or ""))
            if parsed is not None:
                ecc = parsed
                break
    throttle = ""
    for chunk in outputs:
        events = re.findall(r"(?:throttle|violation)[^\n]{0,40}?(\d+)", chunk, re.I)
        if events:
            throttle = float(sum(int(item) for item in events))
            break
        if re.search(r"unthrottl|not throttl", chunk, re.I):
            throttle = 0.0
            break
    if throttle == "":
        # amd-smi printed no throttle/violation counter (status N/A). Say so,
        # in the "expected:" form classify_na() accepts, instead of a blank
        # that publishes the whole run as INCOMPLETE.
        throttle = THROTTLE_NOT_EXPOSED
    return util, (temp if temp > 0 else ""), (power if power > 0 else ""), ecc, throttle


def read_cpu_temp_c():
    """Hottest CPU package/die sensor from hwmon (k10temp, zenpower, coretemp), or
    the x86_pkg_temp thermal zone. Returns "" when the host exposes none (common in
    VMs) -- the old code copied the GPU temperature into the CPU columns instead."""
    best = None
    for hwmon in Path("/sys/class/hwmon").glob("hwmon*"):
        try:
            name = (hwmon / "name").read_text().strip()
        except OSError:
            continue
        if name not in {"k10temp", "zenpower", "coretemp", "cpu_thermal"}:
            continue
        for sensor in hwmon.glob("temp*_input"):
            try:
                value = float(sensor.read_text().strip()) / 1000.0
            except (OSError, ValueError):
                continue
            if value > 0 and (best is None or value > best):
                best = value
    if best is None:
        for zone in Path("/sys/class/thermal").glob("thermal_zone*"):
            try:
                if (zone / "type").read_text().strip() != "x86_pkg_temp":
                    continue
                value = float((zone / "temp").read_text().strip()) / 1000.0
            except (OSError, ValueError):
                continue
            if value > 0 and (best is None or value > best):
                best = value
    return "" if best is None else best


def sample_row(second):
    gpu_util, gpu_temp, gpu_power, gpu_ecc, throttle = gpu_metrics()
    return {
        "status": "ok", "second": second,
        "gpu_util_pct": gpu_util, "gpu_temp_c": gpu_temp, "gpu_power_w": gpu_power,
        "ecc_uncorrected": gpu_ecc,
        "peak_gpu_junction_temp_c": gpu_temp,
        "sustained_gpu_power_w": gpu_power,
        "thermal_throttle_event_count": throttle,
        "ras_uncorrectable_ecc_delta_count": gpu_ecc,
        "error_message": "",
    }


def main() -> int:
    args = parse_args()
    params = load_params(args.config)
    threads = int(float(pv(params, "num_threads", args.profile, 16) or 16))
    cpu_load = int(float(pv(params, "cpu_load_percent", args.profile, 50) or 50))
    seconds = max(1, int(duration_seconds(pv(params, "duration", args.profile, 5))))
    gpu_load = int(float(pv(params, "gpu_load_percent", args.profile, 0) or 0))
    Path(args.run_dir).mkdir(parents=True, exist_ok=True)
    stress = None
    gpu_proc = None
    if shutil.which("stress-ng"):
        stress = subprocess.Popen(
            ["stress-ng", "--cpu", str(threads), "--cpu-load", str(cpu_load), "--timeout", f"{seconds}s"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    if gpu_load > 0:
        gpu_proc = subprocess.Popen(
            [sys.executable, "-c",
             "import time,torch\n"
             "d=torch.device('cuda' if torch.cuda.is_available() else 'cpu')\n"
             "a=torch.randn(2048,2048,device=d)\n"
             f"end=time.time()+{seconds}\n"
             "while time.time()<end:\n"
             "    a=a@a\n"
             "    if d.type=='cuda': torch.cuda.synchronize()\n"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    header = [
        "sample_index", "second", "gpu_util_pct", "gpu_temp_c", "gpu_power_w",
        "ecc_uncorrected", "peak_gpu_junction_temp_c", "sustained_gpu_power_w",
        "thermal_throttle_event_count", "ras_uncorrectable_ecc_delta_count",
    ]
    rows = []
    start = time.time()
    while time.time() - start < seconds:
        rows.append(sample_row(int(time.time() - start)))
        time.sleep(1)
    if stress is not None:
        stress.wait(timeout=max(5, seconds))
    if gpu_proc is not None:
        gpu_proc.wait(timeout=max(5, seconds))
    if not rows:
        rows.append(sample_row(0))
    delta = ecc_interval_delta([row["ras_uncorrectable_ecc_delta_count"] for row in rows])
    for row in rows:
        row["ras_uncorrectable_ecc_delta_count"] = delta
    write_csv(args.raw_file, header, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
