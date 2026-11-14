#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import os
import shutil
import subprocess
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


def driver_conv(dtype):
    key = str(dtype or "").strip().upper()
    if key == "FP16":
        return "convfp16"
    if key == "BF16":
        return "convbfp16"
    if key == "FP32":
        return "conv"
    raise SystemExit(f"[FAIL] unsupported dtype {dtype}")


def torch_dtype_for(conv_name):
    import torch
    if conv_name == "convfp16":
        return torch.float16
    if conv_name == "convbfp16":
        return torch.bfloat16
    return torch.float32


def miopen_flags(direction):
    key = str(direction or "").strip().lower()
    if key in {"all", "*", ""}:
        return [1, 2, 4]
    if key in {"fwd", "forward"}:
        return [1]
    if key in {"bwd_data", "bwd-data"}:
        return [2]
    if key in {"bwd_weights", "bwd-weights", "bwd_filter", "bwd-filter"}:
        return [4]
    raise SystemExit(f"[FAIL] unsupported conv_direction {direction}")


def write_csv(path, header, rows):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=header, extrasaction="ignore", lineterminator=chr(10))
    writer.writeheader()
    rows = list(rows)
    for index, row in enumerate(rows):
        writer.writerow({"sample_index": index, **row})
    text = buf.getvalue()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")
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

# search_strategy uses the cuDNN twin's values (218/418: find, heuristic, get,
# fixed, none). find keeps MIOpenDriver's default Find path (benchmark the
# applicable solvers once, then reuse the find-db). The others skip that
# benchmarking: MIOPEN_FIND_MODE=FAST answers from the find-db or, on a miss,
# from MIOpen's immediate-mode heuristic. MIOpen has no separate get/fixed/none
# path, so those three map to the same heuristic choice.
SEARCH_FIND_MODE = {"find": None, "heuristic": "FAST", "get": "FAST", "fixed": "FAST", "none": "FAST"}


def search_env(strategy: str) -> dict:
    key = str(strategy or "find").strip().lower()
    if key not in SEARCH_FIND_MODE:
        raise SystemExit(f"[FAIL] unsupported search_strategy {strategy!r}; use one of {', '.join(SEARCH_FIND_MODE)}")
    env = os.environ.copy()
    if SEARCH_FIND_MODE[key]:
        env["MIOPEN_FIND_MODE"] = SEARCH_FIND_MODE[key]
    return env


def main() -> int:
    args = parse_args()
    params = load_params(args.config)
    batch = int(float(pv(params, "batch_size", args.profile, 1) or 1))
    cin = int(float(pv(params, "input_channels", args.profile, 8) or 8))
    hin = int(float(pv(params, "input_height", args.profile, 16) or 16))
    win = int(float(pv(params, "input_width", args.profile, 16) or 16))
    cout = int(float(pv(params, "output_channels", args.profile, 8) or 8))
    kh = int(float(pv(params, "kernel_height", args.profile, 3) or 3))
    kw = int(float(pv(params, "kernel_width", args.profile, kh) or kh))
    stride_h = max(1, int(float(pv(params, "stride_h", args.profile, 1) or 1)))
    stride_w = max(1, int(float(pv(params, "stride_w", args.profile, 1) or 1)))
    groups = max(1, int(float(pv(params, "group_count", args.profile, 1) or 1)))
    pad_h = kh // 2
    pad_w = kw // 2
    dtype = str(pv(params, "dtype", args.profile, "FP16") or "FP16")
    conv_name = driver_conv(dtype)
    warmup = int(float(pv(params, "warmup_iters", args.profile, 1) or 1))
    iters = max(1, int(float(pv(params, "num_iterations", args.profile, 2) or 2)))
    Path(args.run_dir).mkdir(parents=True, exist_ok=True)
    header = ["name", "n", "c", "ho", "wo", "y", "x", "k", "flopCnt", "bytesRead", "bytesWritten", "GFLOPs", "GB/s", "timeMs", "kernel_time_ms", "direction"]
    flag_direction = {1: "fwd", 2: "bwd_data", 4: "bwd_weights"}
    driver = shutil.which("MIOpenDriver") or "/opt/rocm/bin/MIOpenDriver"
    direction = str(pv(params, "conv_direction", args.profile, "all")).lower()
    flags = miopen_flags(direction)
    strategy = str(pv(params, "search_strategy", args.profile, "find") or "find")
    driver_env = search_env(strategy)
    print(f"[INFO] MIOpenDriver: search_strategy={strategy} MIOPEN_FIND_MODE={driver_env.get('MIOPEN_FIND_MODE', 'default')} warmup_iters={warmup}", flush=True)
    rows = []
    texts = []
    if Path(driver).is_file():
        for flag in flags:
            cmd = [
                driver, conv_name,
                "-n", str(batch), "-c", str(cin), "-H", str(hin), "-W", str(win),
                "-k", str(cout), "-y", str(kh), "-x", str(kw),
                "-p", str(pad_h), "-q", str(pad_w),
                "-u", str(stride_h), "-v", str(stride_w),
                "-l", "1", "-j", "1", "-g", str(groups), "-F", str(flag),
                "-t", "1", "-i", str(iters),
            ]
            if warmup > 0:
                # Untimed run of the same shape: fills the find-db and kernel
                # cache and brings the GPU out of idle before the timed run.
                warm = cmd[:-4] + ["-t", "0", "-i", str(warmup)]
                warm_done = subprocess.run(warm, capture_output=True, text=True, timeout=max(300, warmup // 50 + 180), env=driver_env)
                texts.append("# warmup (untimed): " + " ".join(warm) + "\n" + (warm_done.stdout or "") + (warm_done.stderr or ""))
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=max(300, iters // 50 + 180), env=driver_env)
            text = (completed.stdout or "") + "\n" + (completed.stderr or "")
            texts.append(text)
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.lower().startswith("stats:"):
                    stripped = stripped.split(":", 1)[1].strip()
                cells = [part.strip() for part in stripped.split(",")]
                if cells and cells[0] == "name":
                    continue
                if len(cells) >= 14 and cells[0] and not cells[0][0].isdigit():
                    row = {header[i]: cells[i] for i in range(14)}
                    try:
                        flops = float(row["flopCnt"])
                        time_ms = float(row["timeMs"])
                        if time_ms > 0:
                            row["GFLOPs"] = flops / (time_ms / 1000.0) / 1e9
                            traffic = float(row["bytesRead"]) + float(row["bytesWritten"])
                            row["GB/s"] = traffic / (time_ms / 1000.0) / 1e9
                    except (TypeError, ValueError, KeyError):
                        pass
                    row["kernel_time_ms"] = row.get("timeMs", "")
                    row["direction"] = flag_direction[flag]
                    rows.append(row)
        Path(args.run_dir, "miopen_transcript.txt").write_text("\n".join(texts), encoding="utf-8")
        if rows:
            write_csv(args.raw_file, header, rows)
            return 0
    import torch
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    dtype_torch = torch_dtype_for(conv_name)
    x = torch.randn(batch, cin, hin, win, device=device, dtype=dtype_torch)
    w = torch.randn(cout, cin // groups, kh, kw, device=device, dtype=dtype_torch)
    out_h = (hin + 2 * pad_h - kh) // stride_h + 1
    out_w = (win + 2 * pad_w - kw) // stride_w + 1
    for _ in range(max(0, warmup)):
        torch.nn.functional.conv2d(x, w, padding=(pad_h, pad_w), stride=(stride_h, stride_w), groups=groups)
    if device.type == "cuda":
        torch.cuda.synchronize()
    start = time.perf_counter()
    for _ in range(iters):
        torch.nn.functional.conv2d(x, w, padding=(pad_h, pad_w), stride=(stride_h, stride_w), groups=groups)
    if device.type == "cuda":
        torch.cuda.synchronize()
    elapsed = (time.perf_counter() - start) / iters
    flops = 2.0 * batch * cout * (cin / groups) * out_h * out_w * kh * kw
    elem = x.element_size()
    bytes_read = elem * (x.numel() + w.numel())
    bytes_written = elem * batch * cout * out_h * out_w
    write_csv(args.raw_file, header, [{
        "name": "fwd-conv", "n": batch, "c": cin, "ho": out_h, "wo": out_w, "y": kh, "x": kw,
        "k": cout, "flopCnt": flops, "bytesRead": bytes_read, "bytesWritten": bytes_written,
        # Minimum-traffic bandwidth (inputs + weights read once, output written once).
        "GFLOPs": flops / elapsed / 1e9, "GB/s": (bytes_read + bytes_written) / elapsed / 1e9,
        "timeMs": elapsed * 1000.0,
        "kernel_time_ms": elapsed * 1000.0,
        "direction": "fwd",
    }])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
