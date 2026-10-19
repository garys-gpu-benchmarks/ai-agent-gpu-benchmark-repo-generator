#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import json
import subprocess
from pathlib import Path

import yaml


def pv(params, key, profile, default=""):
    raw = params.get(key, default)
    if isinstance(raw, dict):
        return raw.get(profile, raw.get("smoke", default))
    return default if raw is None else raw


def as_list(value):
    if value is None:
        return []
    if isinstance(value, (int, float)):
        return [str(value)]
    return [part.strip() for part in str(value).replace(";", ",").split(",") if part.strip()]


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


def percentile(mapping: dict, key: str, default: float) -> float:
    if not mapping:
        return default
    if key in mapping:
        return float(mapping[key])
    for item_key, item_value in mapping.items():
        if str(item_key).startswith(key.split(".")[0]):
            return float(item_value)
    return default


def run_fio(filename: Path, rw: str, block_size: str, io_depth: str, num_jobs: str, size: str, runtime: str, engine: str, direct: str) -> dict:
    if not str(filename).startswith("/dev/"):
        filename.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "fio", "--name=nvme", f"--filename={filename}", f"--rw={rw}", f"--bs={block_size}",
        f"--iodepth={io_depth}", f"--numjobs={num_jobs}", f"--size={size}", f"--runtime={runtime}",
        "--time_based", f"--ioengine={engine}", f"--direct={direct}", "--group_reporting",
        "--output-format=json",
    ]
    timeout = max(30, int(float(runtime or 5)) + 30)
    completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
    if completed.returncode != 0:
        raise SystemExit(f"[FAIL] fio exited {completed.returncode}: {(completed.stderr or completed.stdout)[-400:]}")
    payload = json.loads(completed.stdout or "{}")
    job = (payload.get("jobs") or [None])[0]
    if not job:
        raise SystemExit("[FAIL] fio JSON contained no jobs")
    read_modes = {"read", "randread", "readwrite", "randrw"}
    io_stats = job.get("read") if rw.lower() in read_modes else job.get("write")
    io_stats = io_stats or job.get("read") or job.get("write") or {}
    clat = ((io_stats.get("clat_ns") or {}).get("percentile")) or {}
    iops = float(io_stats.get("iops") or 0.0)
    if iops <= 0:
        raise SystemExit("[FAIL] fio reported 0 IOPS")
    bw_bytes = float(io_stats.get("bw_bytes") or 0.0)
    if bw_bytes <= 0:
        raise SystemExit("[FAIL] fio reported no bandwidth_bytes value")
    p50 = percentile(clat, "50.000000", 0.0) / 1000.0
    p99 = percentile(clat, "99.000000", p50) / 1000.0
    p999 = percentile(clat, "99.900000", p99) / 1000.0
    return {
        "status": "ok",
        "rw": rw,
        "block_size": block_size,
        "io_depth": io_depth,
        "num_jobs": num_jobs,
        "iops_mean": iops,
        "iops_p95": "",
        "iops_p99": "",
        "bandwidth_mb_s": bw_bytes / 1e6,
        "clat_p50_us": p50,
        "clat_p99_us": p99,
        "clat_p999_us": p999,
        "p999_latency_ms": p999 / 1000.0,
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
    params = load_params(args.config)
    rws = as_list(pv(params, "rw", args.profile, "randread"))
    blocks = as_list(pv(params, "block_size", args.profile, "4k"))
    depths = as_list(pv(params, "io_depth", args.profile, "1,8"))
    jobs = str(pv(params, "num_jobs", args.profile, "4"))
    size = str(pv(params, "size", args.profile, "64m"))
    runtime = str(pv(params, "runtime", args.profile, "5"))
    engine = str(pv(params, "io_engine", args.profile, "libaio"))
    direct = str(pv(params, "direct", args.profile, "1"))
    filename = Path(str(pv(params, "filename", args.profile, "data/fio_target.bin")))
    Path(args.run_dir).mkdir(parents=True, exist_ok=True)
    header = [
        "sample_index", "status", "rw", "block_size", "io_depth", "num_jobs",
        "iops_mean", "iops_p95", "iops_p99", "bandwidth_mb_s", "clat_p50_us",
        "clat_p99_us", "clat_p999_us", "p999_latency_ms", "error_message",
    ]
    rows = []
    for rw in rws or ["randread"]:
        for block_size in blocks or ["4k"]:
            for io_depth in depths or ["1"]:
                rows.append(run_fio(filename, rw, block_size, io_depth, jobs, size, runtime, engine, direct))
    # The workbook has one headline value per metric, while this collector
    # retains the complete matrix. Use the first declared rw/bs/qd case as
    # the reproducible headline and preserve every row's measurement under
    # case_* columns instead of averaging incompatible operating points.
    metric_columns = [
        "iops_mean", "iops_p95", "iops_p99", "bandwidth_mb_s",
        "clat_p50_us", "clat_p99_us", "clat_p999_us", "p999_latency_ms",
    ]
    for index, row in enumerate(rows):
        row["headline_configuration"] = f"{row['rw']}_{row['block_size']}_qd{row['io_depth']}"
        row["headline_rule"] = "first_case"
        row["is_headline"] = "1" if index == 0 else "0"
        for key in metric_columns:
            row[f"case_{key}"] = row[key]
    header.extend(["headline_configuration", "headline_rule", "is_headline", *[f"case_{key}" for key in metric_columns]])
    write_csv(args.raw_file, header, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
