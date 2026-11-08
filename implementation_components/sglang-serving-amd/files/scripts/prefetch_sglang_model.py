#!/usr/bin/env python3
"""Finish the model snapshot (config, weights, tokenizer) before sglang.launch_server.

Given a repo id, SGLang can find consolidated.safetensors, skip the shard
download, then fetch model.safetensors.index.json and drop the consolidated
file. The weight list is empty and the server exits. This script downloads
the index and every shard it names. consolidated.safetensors is left in place
for vLLM and RAG.

The runner passes the printed snapshot directory to --model-path, so SGLang
never downloads anything itself. Everything it reads at start-up must already
be in that directory:

- config.json with a model_type key. On 2026-11-08 (TEMPLATE_00_126, fresh VMs,
  x30 run first) every server exited with "Unrecognized model ... Should have a
  model_type key in its config.json": this script fetched the weights and the
  tokenizer but not config.json, which earlier runs only had because the vLLM
  workloads had downloaded it first. generation_config.json is fetched when the
  repo has one.
- The tokenizer files. On 2026-11-08 (TEMPLATE_00_125) the first smoke of every
  x30/x31 exited with transformers' generic "You need to have sentencepiece or
  tiktoken installed" because the snapshot held only tokenizer.model.v3.

Before printing the path, the script loads AutoConfig and AutoTokenizer from the
snapshot with network access off. Only the snapshot path goes to stdout; the
runner reads it with tail -n 1.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

INDEX_NAME = "model.safetensors.index.json"
CONFIG_NAME = "config.json"
# Fetched when the repo has them; SGLang reads them but they are not required.
OPTIONAL_CONFIG_FILES = ("generation_config.json",)
TOKENIZER_FILES = (
    "tokenizer.json",
    "tokenizer.model",
    "tokenizer_config.json",
    "special_tokens_map.json",
)
# A fast tokenizer needs tokenizer.json, or tokenizer.model to convert from.
TOKENIZER_VOCAB_FILES = ("tokenizer.json", "tokenizer.model")
TOKENIZER_REQUIRED_FILES = ("tokenizer_config.json",)


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def nonempty(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def index_shard_names(index_path: Path) -> list[str]:
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    names: list[str] = []
    for name in (payload.get("weight_map") or {}).values():
        if isinstance(name, str) and name not in names:
            names.append(name)
    return names


def shards_complete(snapshot: Path) -> bool:
    index_path = snapshot / INDEX_NAME
    if not nonempty(index_path):
        return False
    names = index_shard_names(index_path)
    if not names:
        return False
    return all(nonempty(snapshot / name) for name in names)


def config_problem(snapshot: Path) -> str:
    """Why config.json cannot start a server, or "" when it can."""
    path = snapshot / CONFIG_NAME
    if not nonempty(path):
        return f"{CONFIG_NAME} is missing or empty"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return f"{CONFIG_NAME} is not valid JSON ({exc})"
    if not isinstance(payload, dict) or not str(payload.get("model_type") or "").strip():
        return f"{CONFIG_NAME} has no model_type key"
    return ""


def config_complete(snapshot: Path) -> bool:
    return not config_problem(snapshot)


def missing_tokenizer_files(snapshot: Path) -> list[str]:
    """Names that keep the snapshot from loading a tokenizer offline."""
    missing = [name for name in TOKENIZER_REQUIRED_FILES if not nonempty(snapshot / name)]
    if not any(nonempty(snapshot / name) for name in TOKENIZER_VOCAB_FILES):
        missing.append(" or ".join(TOKENIZER_VOCAB_FILES))
    return missing


def tokenizer_complete(snapshot: Path) -> bool:
    return not missing_tokenizer_files(snapshot)


def snapshot_complete(snapshot: Path) -> bool:
    return shards_complete(snapshot) and config_complete(snapshot) and tokenizer_complete(snapshot)


def snapshot_dirs(repo_id: str) -> list[Path]:
    hf_home = Path(os.environ.get("HF_HOME") or (Path.home() / ".cache/huggingface"))
    root = hf_home / "hub" / ("models--" + repo_id.replace("/", "--")) / "snapshots"
    if not root.is_dir():
        return []
    return [path for path in root.iterdir() if path.is_dir()]


def _entry_not_found() -> tuple[type[BaseException], ...]:
    try:
        from huggingface_hub.utils import EntryNotFoundError
    except ImportError:
        return ()
    return (EntryNotFoundError,)


def ensure_index_shards(repo_id: str) -> Path:
    from huggingface_hub import hf_hub_download

    try:
        hf_hub_download(repo_id, INDEX_NAME)
    except Exception as exc:
        raise SystemExit(f"[FAIL] {repo_id}: cannot fetch {INDEX_NAME}: {exc}") from exc
    candidates = snapshot_dirs(repo_id)
    indexed = [path for path in candidates if nonempty(path / INDEX_NAME)]
    if not indexed:
        raise SystemExit(f"[FAIL] {repo_id}: {INDEX_NAME} is not in the local snapshot")
    snapshot = next((path for path in indexed if shards_complete(path)), indexed[0])
    missing = [name for name in index_shard_names(snapshot / INDEX_NAME) if not nonempty(snapshot / name)]
    for name in missing:
        try:
            hf_hub_download(repo_id, name)
        except Exception as exc:
            raise SystemExit(f"[FAIL] {repo_id}: cannot fetch shard {name}: {exc}") from exc
    complete = [path for path in snapshot_dirs(repo_id) if shards_complete(path)]
    if not complete:
        raise SystemExit(f"[FAIL] {repo_id}: index shards are still missing after download")
    return complete[0]


def _fetch_into_snapshot(repo_id: str, snapshot: Path, name: str, required: bool) -> None:
    """Download one file into the snapshot that holds the shards."""
    from huggingface_hub import hf_hub_download

    if nonempty(snapshot / name):
        return
    try:
        hf_hub_download(repo_id, name, revision=snapshot.name)
    except _entry_not_found():
        if required:
            raise SystemExit(f"[FAIL] {repo_id}: the repository has no {name}") from None
    except Exception as exc:
        raise SystemExit(f"[FAIL] {repo_id}: cannot fetch {name}: {exc}") from exc


def ensure_model_config(repo_id: str, snapshot: Path) -> Path:
    _fetch_into_snapshot(repo_id, snapshot, CONFIG_NAME, required=True)
    for name in OPTIONAL_CONFIG_FILES:
        _fetch_into_snapshot(repo_id, snapshot, name, required=False)
    problem = config_problem(snapshot)
    if problem:
        raise SystemExit(f"[FAIL] {repo_id}: snapshot {snapshot}: {problem}; sglang.launch_server cannot start.")
    return snapshot


def ensure_tokenizer_files(repo_id: str, snapshot: Path) -> Path:
    for name in TOKENIZER_FILES:
        # Not every repo ships all four; missing_tokenizer_files decides.
        _fetch_into_snapshot(repo_id, snapshot, name, required=False)
    missing = missing_tokenizer_files(snapshot)
    if missing:
        raise SystemExit(
            f"[FAIL] {repo_id}: snapshot {snapshot} has no usable tokenizer "
            f"(missing or empty: {', '.join(missing)}). tokenizer.model.v3 does not count."
        )
    return snapshot


def verify_offline_load(snapshot: Path) -> None:
    """Load the config and tokenizer the way sglang.launch_server will, without network."""
    try:
        from transformers import AutoConfig, AutoTokenizer
    except Exception as exc:
        raise SystemExit(f"[FAIL] transformers is not importable in this venv: {exc}") from exc
    try:
        AutoConfig.from_pretrained(str(snapshot), local_files_only=True)
    except Exception as exc:
        raise SystemExit(f"[FAIL] AutoConfig cannot load {snapshot}: {exc}") from exc
    try:
        tokenizer = AutoTokenizer.from_pretrained(str(snapshot), local_files_only=True)
    except Exception as exc:
        raise SystemExit(
            f"[FAIL] AutoTokenizer cannot load {snapshot}: {exc}. "
            "If the tokenizer files are present, check that sentencepiece and tiktoken "
            "import in this venv."
        ) from exc
    if not tokenizer.encode("ready", add_special_tokens=False):
        raise SystemExit(f"[FAIL] AutoTokenizer from {snapshot} encoded a test word to nothing")


def ensure_snapshot(repo_id: str, verify: bool = True) -> Path:
    snapshot = ensure_index_shards(repo_id)
    snapshot = ensure_model_config(repo_id, snapshot)
    snapshot = ensure_tokenizer_files(repo_id, snapshot)
    if verify:
        verify_offline_load(snapshot)
    log(f"[OK] {repo_id}: config, weights and tokenizer complete in {snapshot}")
    return snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", default="mistralai/Mistral-7B-v0.3")
    parser.add_argument(
        "--skip-tokenizer-load",
        action="store_true",
        help="Check the files but do not load AutoConfig and AutoTokenizer.",
    )
    args = parser.parse_args(argv)
    snapshot = ensure_snapshot(args.model_id, verify=not args.skip_tokenizer_load)
    print(snapshot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
