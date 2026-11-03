#!/usr/bin/env python3
# File: scripts/collect_workload.py
# Description: Harness wrapper that resolves config/benchmark_config.yaml's
# sweep: section for the active --profile and forwards the matching flags to
# the overlay gpu-bench-rag-faiss-end2end.py script. That script writes its
# own results/raw/<run>/raw_output.txt and raw_results.csv directly (it
# ignores the harness's --raw-file value), so this wrapper only copies the
# produced raw_output.txt onto --raw-file when the two paths differ.
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

SCRIPT = Path(__file__).resolve().parent / "gpu-bench-rag-faiss-end2end.py"

# sweep: key -> gpu-bench-rag-faiss-end2end.py flag (hyphenated).
FORWARDED_KEYS = (
    "corpus_dataset",
    "chunk_size",
    "chunk_overlap",
    "embedding_model",
    "llm_model",
    "reranker_model",
    "top_k",
    "query_length",
    "batch_size",
    "query_count",
    "max_new_tokens",
)


def resolve_value(value: object, profile: str) -> str | None:
    """sweep values are either a scalar (applies to every profile) or a
    {smoke: ..., baseline: ..., extended: ...} map keyed by profile."""
    if isinstance(value, dict):
        if profile in value:
            return str(value[profile])
        if value:
            return str(next(iter(value.values())))
        return None
    if value is None:
        return None
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect RAG FAISS end-to-end samples")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--raw-file", default="")
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--device", default="gpu")
    parser.add_argument("--output-format", default="")
    args, _unknown = parser.parse_known_args()

    if not SCRIPT.is_file():
        raise SystemExit(f"[FAIL] missing overlay {SCRIPT.name}")

    sweep: dict[str, object] = {}
    config_path = Path(args.config)
    if config_path.is_file():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        sweep = loaded.get("sweep") or {}

    cmd = [sys.executable, str(SCRIPT), "--run-dir", args.run_dir]
    for key in FORWARDED_KEYS:
        value = resolve_value(sweep.get(key), args.profile)
        if value is not None and value != "":
            cmd.extend([f"--{key.replace('_', '-')}", value])

    completed = subprocess.run(cmd, check=False)
    if completed.returncode != 0:
        return completed.returncode

    produced = Path(args.run_dir) / "raw_output.txt"
    if args.raw_file and produced.is_file():
        target = Path(args.raw_file)
        if target.resolve() != produced.resolve():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(produced.read_text(encoding="utf-8"), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
