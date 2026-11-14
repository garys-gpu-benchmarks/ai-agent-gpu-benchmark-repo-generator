#!/usr/bin/env python3
"""DistilBERT classification training on synthetic SST-2-style batches."""

from __future__ import annotations

import argparse
import math
import os

# Quiet Hugging Face loading: no "Loading weights" progress bar and no LOAD REPORT
# table. The report lists the pretraining head (vocab_*) as UNEXPECTED and the new
# classification head (pre_classifier, classifier) as MISSING; both are expected
# when fine-tuning from distilbert-base-uncased. The settings are read when
# transformers is imported, so they come first.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")


import torch
from transformers import DistilBertConfig, DistilBertForSequenceClassification


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


def finite_nonneg(value: float) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0.0:
        return 0.0
    return parsed


def token_on(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "on"}


def load_model(name: str, device: torch.device) -> torch.nn.Module:
    try:
        model, loading = DistilBertForSequenceClassification.from_pretrained(
            name, num_labels=2, output_loading_info=True)
        warn_missing_weights(name, loading)
    except Exception:
        model = DistilBertForSequenceClassification(DistilBertConfig(num_labels=2))
    return model.to(device)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-name", default="distilbert-base-uncased")
    parser.add_argument("--dataset-name", default="glue-sst2-synthetic")
    parser.add_argument("--num-gpus", default="true")
    parser.add_argument("--sequence-len", default="32")
    parser.add_argument("--batch-size", default="2")
    parser.add_argument("--optimizer", default="adamw")
    parser.add_argument("--learning-rate", default="5e-05")
    parser.add_argument("--weight-decay", default="0.01")
    parser.add_argument("--gradient-accumulation", default="true")
    parser.add_argument("--warmup-iters", default="true")
    parser.add_argument("--num-epochs", default="true")
    parser.add_argument("--num-iterations", default="2")
    parser.add_argument("--device-id", default="0")
    args = parser.parse_args()
    if "synthetic" not in str(args.dataset_name).lower():
        raise SystemExit("[FAIL] dataset_name must remain glue-sst2-synthetic.")
    if not torch.cuda.is_available():
        raise SystemExit("[FAIL] torch.cuda.is_available() is False")
    device = torch.device(f"cuda:{int(args.device_id)}")
    torch.cuda.set_device(device)
    seq = max(8, int(float(args.sequence_len)))
    batch = max(1, int(float(args.batch_size)))
    warmup = 1 if token_on(args.warmup_iters) else max(0, int(float(args.warmup_iters)))
    iters = max(1, int(float(args.num_iterations)))
    accum = 1 if token_on(args.gradient_accumulation) else max(1, int(float(args.gradient_accumulation)))
    model = load_model(args.model_name, device)
    model.train()
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(args.learning_rate), weight_decay=float(args.weight_decay))
    vocab = int(getattr(model.config, "vocab_size", 30522))
    input_ids = torch.randint(0, max(2, vocab - 1), (batch, seq), device=device)
    attention_mask = torch.ones_like(input_ids)
    labels = torch.randint(0, 2, (batch,), device=device)
    for _ in range(warmup):
        out = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
        (out.loss / accum).backward()
        optimizer.zero_grad(set_to_none=True)
    torch.cuda.synchronize(device)
    torch.cuda.reset_peak_memory_stats(device)
    mark_measure_start()  # setup ends: model loaded, warmup done
    start = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    start.record()
    for step in range(iters):
        out = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
        (out.loss / accum).backward()
        if (step + 1) % accum == 0:
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)
    end.record()
    torch.cuda.synchronize(device)
    elapsed_ms = float(start.elapsed_time(end))
    step_ms = finite_nonneg(elapsed_ms / float(iters))
    samples_per_sec = finite_nonneg(float(batch) / (step_ms / 1000.0)) if step_ms else 0.0
    tokens_per_sec = finite_nonneg(float(batch * seq) / (step_ms / 1000.0)) if step_ms else 0.0
    peak = finite_nonneg(float(torch.cuda.max_memory_allocated(device)) / 1e9)
    print(
        "RESULT"
        f" model_name={args.model_name}"
        f" dataset_name={args.dataset_name}"
        f" sequence_len={seq}"
        f" batch_size={batch}"
        f" samples_per_sec={samples_per_sec:.6f}"
        f" step_time_msec={step_ms:.6f}"
        f" tokens_per_sec={tokens_per_sec:.6f}"
        f" peak_gpu_memory_gb={peak:.6f}"
        " status=ok"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
