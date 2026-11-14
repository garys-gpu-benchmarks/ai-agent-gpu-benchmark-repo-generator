#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import os
import time
from pathlib import Path

import yaml

# Quiet Hugging Face loading: no "Loading weights" progress bar and no LOAD REPORT
# table for the pretraining-head weights (cls.*) that BertModel does not use.
# Both settings are read when transformers is imported, so they come first.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")


def mark_measure_start() -> None:
    """Setup ends here: record when the timed work starts (TEMPLATE_00_141).

    run_benchmark.sh reads BENCHMARK_MEASURE_START_FILE when the benchmark stops and
    starts the benchmark clock at this time, so model load and warmup count as setup.
    The first call of a run wins. Outside run_benchmark.sh it does nothing.
    """
    import os
    import time

    path = os.environ.get("BENCHMARK_MEASURE_START_FILE", "")
    if not path or os.path.exists(path):
        return
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(f"{time.time_ns()}\n")
    except OSError:
        pass


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

def main() -> int:
    args = parse_args()
    params = load_params(args.config)
    seq = int(float(pv(params, "sequence_len", args.profile, 32) or 32))
    batch = int(float(pv(params, "batch_size", args.profile, 1) or 1))
    warmup = int(float(pv(params, "warmup_iters", args.profile, 2) or 2))
    iters = max(1, int(float(pv(params, "num_iterations", args.profile, 5) or 5)))
    model_name = str(pv(params, "model_name", args.profile, "bert-base-uncased"))
    Path(args.run_dir).mkdir(parents=True, exist_ok=True)
    import torch
    from transformers import BertModel
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, loading = BertModel.from_pretrained(model_name, output_loading_info=True)
    model = model.to(device).eval()
    # The hidden load report would also hide encoder weights missing from the
    # checkpoint (randomly initialized), so name those here.
    if loading.get("missing_keys"):
        print(f"[WARN] {model_name}: {len(loading['missing_keys'])} model weights missing from the checkpoint "
              f"(randomly initialized): {', '.join(sorted(loading['missing_keys'])[:5])}", flush=True)
    if "16" in str(pv(params, "dtype", args.profile, "f16_r")).lower():
        model = model.half()
    if device.type == "cuda":
        # Without this reset the peak was the FP32 -> FP16 conversion at load
        # (485951488 bytes on every profile), not the inference working set.
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
    ids = torch.randint(0, 1000, (batch, seq), device=device)
    mask = torch.ones_like(ids)
    with torch.no_grad():
        for _ in range(max(0, warmup)):
            model(input_ids=ids, attention_mask=mask)
        if device.type == "cuda":
            torch.cuda.synchronize()
        mark_measure_start()  # setup ends: model loaded, warmup done
        start = time.perf_counter()
        for _ in range(iters):
            model(input_ids=ids, attention_mask=mask)
        if device.type == "cuda":
            torch.cuda.synchronize()
    elapsed = (time.perf_counter() - start) / iters
    mem = 0.001
    if device.type == "cuda":
        mem = max(0.001, torch.cuda.max_memory_allocated() / 1e9)
    seqs = batch / elapsed
    write_csv(args.raw_file, [
        "batch_size", "sequence_len", "sequences_per_sec", "p50_latency_ms", "mean_latency_ms",
        "p95_latency_ms", "p99_latency_ms", "tokens_per_sec", "peak_gpu_memory_gb",
    ], [{
        "batch_size": batch, "sequence_len": seq, "sequences_per_sec": seqs,
        "p50_latency_ms": elapsed * 1000.0, "mean_latency_ms": elapsed * 1000.0, "p95_latency_ms": elapsed * 1000.0,
        "p99_latency_ms": elapsed * 1000.0, "tokens_per_sec": seqs * seq, "peak_gpu_memory_gb": mem,
    }])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
