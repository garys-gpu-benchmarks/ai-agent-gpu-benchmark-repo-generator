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
# table. The report lists the pretraining head (vocab_*) as UNEXPECTED and the new
# classification head (pre_classifier, classifier) as MISSING; both are expected
# when fine-tuning from distilbert-base-uncased. The settings are read when
# transformers is imported, so they come first.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

# The new classification head is expected to be missing from the base checkpoint.
CLASSIFIER_HEAD = ("pre_classifier.", "classifier.")


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


def warn_missing_weights(name: str, loading: dict) -> None:
    """The hidden load report would also hide body weights missing from the
    checkpoint (randomly initialized); name those, but not the classifier head."""
    missing = sorted(key for key in loading.get("missing_keys", ()) if not key.startswith(CLASSIFIER_HEAD))
    if missing:
        print(f"[WARN] {name}: {len(missing)} model weights missing from the checkpoint "
              f"(randomly initialized): {', '.join(missing[:5])}", flush=True)


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


def count_token(raw, true_value, default, minimum):
    """yaml true means the NVIDIA twin's enabled default; a number is used as is."""
    text = str(raw).strip().lower() if raw is not None else ""
    if text in {"true", "yes", "on"}:
        return true_value
    if text in {"", "false", "no", "off"}:
        return default
    return max(minimum, int(float(text)))


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
    batch = int(float(pv(params, "batch_size", args.profile, 2) or 2))
    iters = max(1, int(float(pv(params, "num_iterations", args.profile, 2) or 2)))
    lr = float(pv(params, "learning_rate", args.profile, 5e-5) or 5e-5)
    # Untimed passes before the timer, and backward passes per optimizer step.
    # Without the yaml keys: no warmup and one pass per step, as before.
    warmup = count_token(pv(params, "warmup_iters", args.profile, ""), 1, 0, 0)
    accum = count_token(pv(params, "gradient_accumulation", args.profile, ""), 1, 1, 1)
    model_name = str(pv(params, "model_name", args.profile, "distilbert-base-uncased"))
    Path(args.run_dir).mkdir(parents=True, exist_ok=True)
    import torch
    from transformers import DistilBertForSequenceClassification
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, loading = DistilBertForSequenceClassification.from_pretrained(
        model_name, num_labels=2, output_loading_info=True)
    warn_missing_weights(model_name, loading)
    model = model.to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=float(pv(params, "weight_decay", args.profile, 0.01) or 0.01))
    ids = torch.randint(0, 1000, (batch, seq), device=device)
    mask = torch.ones_like(ids)
    labels = torch.zeros(batch, dtype=torch.long, device=device)
    model.train()
    # Warmup matches the NVIDIA twin (225/425): forward and backward, gradients
    # discarded, so kernel selection and allocator growth stay out of the timing.
    for _ in range(warmup):
        out = model(input_ids=ids, attention_mask=mask, labels=labels)
        (out.loss / accum).backward()
        opt.zero_grad(set_to_none=True)
    if device.type == "cuda":
        # Peak memory covers the training steps, not the model load.
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
    mark_measure_start()  # setup ends: model loaded, warmup done
    print(f"[INFO] distilbert: warmup_iters={warmup} gradient_accumulation={accum} num_iterations={iters}", flush=True)
    start = time.perf_counter()
    opt.zero_grad(set_to_none=True)
    for step in range(iters):
        out = model(input_ids=ids, attention_mask=mask, labels=labels)
        (out.loss / accum).backward()
        if (step + 1) % accum == 0:
            opt.step()
            opt.zero_grad(set_to_none=True)
    if device.type == "cuda":
        torch.cuda.synchronize()
    elapsed = (time.perf_counter() - start) / iters
    final_loss = float(out.loss.item())  # read after the timer: .item() waits for the GPU
    mem = 0.001
    if device.type == "cuda":
        mem = max(0.001, torch.cuda.max_memory_allocated() / 1e9)
    samples = batch / elapsed
    write_csv(args.raw_file, [
        "step", "loss", "samples_per_sec", "step_time_ms", "tokens_per_sec", "peak_gpu_memory_gb",
    ], [
        # One measurement, one row. loss is the last timed step's loss (was a fixed 1.0).
        {"step": iters - 1, "loss": final_loss, "samples_per_sec": samples, "step_time_ms": elapsed * 1000.0,
         "tokens_per_sec": samples * seq, "peak_gpu_memory_gb": mem},
    ])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
