#!/usr/bin/env python3
# File: scripts/collect_workload.py
# Description: NVIDIA system stress (203/403). Runs bin/gpu_stress (cuBLAS GEMM
#              load at gpu_load_percent) together with stress-ng (num_threads
#              workers at cpu_load_percent) for the yaml duration, polling
#              nvidia-smi every poll_interval seconds on a fixed schedule.
#              Same three metrics and CSV layout as the AMD twin (103/303):
#              peak_gpu_temperature_c, sustained_gpu_power_w, gpu_system_ecc_error_count.
#              Gates: the run fails if gpu_stress fails or GPU utilization never
#              reaches half the requested load; peak temperature above
#              temp_threshold, mean power above power_threshold, or (with
#              throttle_check) a thermal-slowdown event mark every sample error.
from __future__ import annotations

import argparse
import csv
import io
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import yaml

# One row per poll, same columns as implementation_components/system-stress-amd.
# peak_gpu_temperature_c / sustained_gpu_power_w hold the per-poll reading;
# parse_results.py reduces them by leading word: peak_ -> max, sustained_ -> mean.
HEADER = [
    "sample_index", "status", "second", "gpu_util_pct", "gpu_temp_c", "gpu_power_w",
    "ecc_uncorrected", "peak_gpu_temperature_c", "sustained_gpu_power_w",
    "thermal_throttle_event_count", "gpu_system_ecc_error_count", "error_message",
]
QUERY_FIELDS = "temperature.gpu,power.draw,utilization.gpu,clocks_throttle_reasons.hw_thermal_slowdown"
ECC_FIELD = "ecc.errors.uncorrected.volatile.total"
ECC_DISABLED = "na (expected: ECC disabled)"
NUMBER_RE = re.compile(r"^-?[0-9]+(?:\.[0-9]+)?$")
GPU_STRESS = Path("bin/gpu_stress")
READY_TIMEOUT_S = 120.0


def pv(params, key, profile, default=""):
    raw = params.get(key, default)
    if isinstance(raw, dict):
        return raw.get(profile, raw.get("smoke", default))
    return default if raw is None else raw


def duration_seconds(raw, default=5.0) -> float:
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return default
    return number / 1000.0 if number >= 10000 else number


def as_float(raw, default: float) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def as_bool(raw, default: bool) -> bool:
    if raw is None or raw == "":
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def run_command(command, timeout=30):
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return completed.returncode, (completed.stdout or "") + "\n" + (completed.stderr or "")


def _number(field: str) -> float | None:
    text = field.strip()
    return float(text) if NUMBER_RE.match(text) else None


def _ecc_unavailable(field: str) -> bool:
    """nvidia-smi prints [N/A] when ECC is disabled or the GPU has no ECC counter."""
    text = field.strip().lower().strip("[]")
    return text in {"n/a", "na", "not supported", "not available", "disabled"}


def _gpu_lines(text: str, width: int) -> list[list[str]]:
    """Data lines of a --format=csv,noheader,nounits query: one per GPU.
    Skips warnings and anything without the expected number of fields."""
    lines = []
    for raw in text.splitlines():
        fields = [part.strip() for part in raw.split(",")]
        if len(fields) == width and _number(fields[0]) is not None:
            lines.append(fields)
    return lines


def _thermal_active(field: str) -> bool:
    # Driver 580 prints "Active" or "Not Active". A substring match on
    # "Active" also matches "Not Active" and counted a throttle every poll.
    return re.fullmatch(r"active", field.strip(), re.I) is not None


def gpu_sample(ecc_check: bool):
    """One nvidia-smi call per poll: hottest GPU temperature, highest per-GPU
    power draw, highest utilization, any hardware thermal slowdown, and the
    uncorrectable ECC count summed over GPUs. Disabled ECC is the explicit
    expected-na reason, not a blank, so the numbered metric stays present."""
    fields = QUERY_FIELDS + ("," + ECC_FIELD if ecc_check else "")
    width = 5 if ecc_check else 4
    rc, text = run_command(["nvidia-smi", f"--query-gpu={fields}", "--format=csv,noheader,nounits"])
    if rc != 0 or "Failed to initialize NVML" in text or "version mismatch" in text.lower():
        return None, None, None, False, None
    lines = _gpu_lines(text, width)
    temps = [v for v in (_number(line[0]) for line in lines) if v is not None]
    powers = [v for v in (_number(line[1]) for line in lines) if v is not None]
    utils = [v for v in (_number(line[2]) for line in lines) if v is not None]
    thermal = any(_thermal_active(line[3]) for line in lines)
    ecc = None
    if ecc_check and lines:
        counts = [v for v in (_number(line[4]) for line in lines) if v is not None]
        if counts:
            ecc = float(sum(counts))
        elif all(_ecc_unavailable(line[4]) for line in lines):
            ecc = ECC_DISABLED
    return (
        max(temps) if temps else None,
        max(powers) if powers else None,
        max(utils) if utils else None,
        thermal,
        ecc,
    )


def blank(value):
    return "" if value is None else value


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


def start_gpu_load(seconds: float, load_pct: float, log_path: Path):
    """Start bin/gpu_stress and wait for GPU_LOAD_READY (after cuBLAS init and
    warm-up), so every poll falls inside the load window."""
    if not GPU_STRESS.is_file():
        raise SystemExit("[FAIL] bin/gpu_stress missing; GPU load was not built (scripts/build.sh)")
    log = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [str(GPU_STRESS), f"{seconds + 2:.1f}", f"{load_pct:g}"],
        stdout=log, stderr=subprocess.STDOUT, text=True,
    )
    deadline = time.time() + READY_TIMEOUT_S
    while time.time() < deadline:
        if "GPU_LOAD_READY" in log_path.read_text(encoding="utf-8", errors="replace"):
            return proc, log
        if proc.poll() is not None:
            break
        time.sleep(0.2)
    if proc.poll() is None:
        proc.kill()
        proc.wait()
    log.close()
    tail = log_path.read_text(encoding="utf-8", errors="replace").strip()[-400:]
    raise SystemExit(f"[FAIL] bin/gpu_stress did not start GPU load (exit {proc.returncode}): {tail or 'no output'}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--raw-file", required=True)
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--device", default="gpu")
    parser.add_argument("--output-format", default="csv")
    parser.add_argument("--num-threads", default=None)
    parser.add_argument("--cpu-load-percent", default=None)
    parser.add_argument("--gpu-load-percent", default=None)
    parser.add_argument("--temp-threshold", default=None)
    parser.add_argument("--power-threshold", default=None)
    parser.add_argument("--throttle-check", default=None)
    parser.add_argument("--ecc-check", default=None)
    parser.add_argument("--poll-interval", default=None)
    parser.add_argument("--duration", default=None)
    args = parser.parse_args()
    sweep = (yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}).get("sweep") or {}

    def setting(cli, key, default):
        return cli if cli not in (None, "") else pv(sweep, key, args.profile, default)

    seconds = max(1, int(duration_seconds(setting(args.duration, "duration", 5), 5)))
    threads = str(setting(args.num_threads, "num_threads", os.cpu_count() or 1) or 1)
    cpu_pct = min(100.0, max(0.0, as_float(setting(args.cpu_load_percent, "cpu_load_percent", 100), 100.0)))
    gpu_pct = min(100.0, max(0.0, as_float(setting(args.gpu_load_percent, "gpu_load_percent", 50), 50.0)))
    temp_limit = as_float(setting(args.temp_threshold, "temp_threshold", ""), 0.0)
    power_limit = as_float(setting(args.power_threshold, "power_threshold", ""), 0.0)
    throttle_check = as_bool(setting(args.throttle_check, "throttle_check", True), True)
    ecc_check = as_bool(setting(args.ecc_check, "ecc_check", True), True)
    poll = max(0.5, as_float(setting(args.poll_interval, "poll_interval", 1), 1.0))

    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    if not shutil.which("stress-ng"):
        raise SystemExit("[FAIL] stress-ng is required for NVIDIA system-stress")
    print(f"[INFO] stress: {seconds}s cpu={threads} threads @ {cpu_pct:g}% gpu={gpu_pct:g}% "
          f"poll={poll:g}s temp<={temp_limit or 'n/a'} power<={power_limit or 'n/a'} "
          f"throttle_check={throttle_check} ecc_check={ecc_check}", flush=True)

    gpu_proc, gpu_log = (None, None)
    gpu_log_path = run_dir / "gpu_stress.txt"
    if gpu_pct > 0:
        gpu_proc, gpu_log = start_gpu_load(seconds, gpu_pct, gpu_log_path)
    cpu_cmd = ["stress-ng", "--cpu", threads, "--timeout", f"{seconds}s", "--metrics-brief"]
    if cpu_pct < 100:
        cpu_cmd[3:3] = ["--cpu-load", f"{int(round(cpu_pct))}"]
    proc = subprocess.Popen(cpu_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    rows = []
    throttle_events = 0
    prev_thermal = False
    start = time.time()
    tick = 0
    # Fixed schedule: poll k runs at start + k*poll, so slow nvidia-smi calls
    # do not push later polls back. At least two samples.
    while time.time() - start < seconds or len(rows) < 2:
        temp, power, util, thermal, ecc = gpu_sample(ecc_check)
        if thermal and not prev_thermal:
            throttle_events += 1
        prev_thermal = thermal
        rows.append({
            "status": "ok",
            "second": int(time.time() - start),
            "gpu_util_pct": blank(util),
            "gpu_temp_c": blank(temp),
            "gpu_power_w": blank(power),
            "ecc_uncorrected": blank(ecc),
            "peak_gpu_temperature_c": blank(temp),
            "sustained_gpu_power_w": blank(power),
            "thermal_throttle_event_count": float(throttle_events),
            "gpu_system_ecc_error_count": blank(ecc),
            "error_message": "" if temp is not None else "nvidia-smi returned no GPU reading",
        })
        tick += 1
        wait = start + tick * poll - time.time()
        if wait > 0:
            time.sleep(wait)

    out, _ = proc.communicate(timeout=seconds + 30)
    (run_dir / "stress-ng.txt").write_text(out or "", encoding="utf-8")
    if proc.returncode not in (0, None):
        raise SystemExit(f"[FAIL] stress-ng exited {proc.returncode}")

    if gpu_proc is not None:
        try:
            gpu_proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            gpu_proc.kill()
            gpu_proc.wait()
        gpu_log.close()
        gpu_text = gpu_log_path.read_text(encoding="utf-8", errors="replace")
        done = re.search(r"GPU_LOAD_DONE .*gemms=(\d+)", gpu_text)
        if gpu_proc.returncode != 0 or not done or int(done.group(1)) == 0:
            tail = " | ".join(line.strip() for line in gpu_text.splitlines() if line.strip())[-400:]
            raise SystemExit(f"[FAIL] bin/gpu_stress exited {gpu_proc.returncode} without running GEMMs: {tail}")
        utils = [float(r["gpu_util_pct"]) for r in rows if r["gpu_util_pct"] != ""]
        mean_util = sum(utils) / len(utils) if utils else 0.0
        need = max(10.0, gpu_pct / 2.0)
        if mean_util < need:
            raise SystemExit(
                f"[FAIL] GPU load not observed: mean utilization.gpu {mean_util:.1f}% < {need:g}% "
                f"(requested {gpu_pct:g}%); see {gpu_log_path}"
            )
        print(f"[INFO] GPU load observed: mean utilization.gpu {mean_util:.1f}% (requested {gpu_pct:g}%)", flush=True)

    temps = [float(r["gpu_temp_c"]) for r in rows if r["gpu_temp_c"] != ""]
    powers = [float(r["gpu_power_w"]) for r in rows if r["gpu_power_w"] != ""]
    breaches = []
    if temp_limit > 0 and temps and max(temps) > temp_limit:
        breaches.append(f"peak GPU temperature {max(temps):g} C > temp_threshold {temp_limit:g} C")
    if power_limit > 0 and powers and sum(powers) / len(powers) > power_limit:
        breaches.append(f"sustained GPU power {sum(powers) / len(powers):.1f} W > power_threshold {power_limit:g} W")
    if throttle_check and throttle_events > 0:
        breaches.append(f"{throttle_events} hardware thermal slowdown event(s)")
    if breaches:
        message = "; ".join(breaches)
        print(f"[FAIL] stress threshold exceeded: {message}", flush=True)
        for row in rows:
            row["status"] = "error"
            row["error_message"] = "; ".join(filter(None, [row["error_message"], message]))
    delta = ecc_interval_delta([row["gpu_system_ecc_error_count"] for row in rows])
    for row in rows:
        row["gpu_system_ecc_error_count"] = delta

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=HEADER, extrasaction="ignore", lineterminator=chr(10))
    writer.writeheader()
    for index, row in enumerate(rows):
        writer.writerow({"sample_index": index, **row})
    Path(args.raw_file).write_text(buf.getvalue(), encoding="utf-8")
    print(buf.getvalue(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
