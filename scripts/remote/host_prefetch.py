#!/usr/bin/env python3
# File: scripts/remote/host_prefetch.py
# Description: Background Hugging Face prefetch on the validation VM, started by
#              scripts/remote/host_bootstrap.sh (TEMPLATE_00_119). Downloads into
#              the same cache the workloads read (HF_HOME, default
#              ~/.cache/huggingface, as set by scripts/lib/common.sh) with the xet
#              range downloader off. A failed model is logged and skipped.
# Execution: python host_prefetch.py --state-dir DIR repo_id[|pattern;pattern] ...
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

# Free space to keep before starting each model, in GiB.
MIN_FREE_GIB = 20


def parse_spec(spec: str) -> tuple[str, list[str] | None]:
    repo, _, patterns = spec.partition("|")
    pats = [p for p in patterns.split(";") if p] if patterns else None
    return repo.strip(), pats


def free_gib(path: Path) -> float:
    path.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(path).free / (1024 ** 3)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("specs", nargs="*")
    args = parser.parse_args()
    state = Path(args.state_dir)
    status_path = state / "prefetch_status.json"
    hf_home = Path(os.environ.get("HF_HOME") or (Path.home() / ".cache/huggingface"))
    status: dict[str, object] = {"started_epoch": int(time.time()), "hf_home": str(hf_home), "models": {}}

    def save() -> None:
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")

    save()
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        status["error"] = f"huggingface_hub not importable: {exc}"
        status["finished_epoch"] = int(time.time())
        save()
        print(f"[WARN] {status['error']}", flush=True)
        return 0
    models = status["models"]
    assert isinstance(models, dict)
    for spec in args.specs:
        repo, patterns = parse_spec(spec)
        started = time.time()
        if free_gib(hf_home) < MIN_FREE_GIB:
            models[repo] = {"status": "skipped", "reason": f"less than {MIN_FREE_GIB} GiB free on {hf_home}"}
            save()
            print(f"[WARN] {repo}: skipped, low disk", flush=True)
            continue
        models[repo] = {"status": "running"}
        save()
        print(f"[RUN] snapshot_download {repo} allow_patterns={patterns}", flush=True)
        try:
            path = snapshot_download(repo, allow_patterns=patterns)
            models[repo] = {"status": "done", "seconds": round(time.time() - started, 1), "path": path}
            print(f"[PASS] {repo} in {time.time() - started:.0f} s", flush=True)
        except Exception as exc:  # gated model without a token, network error, ...
            models[repo] = {"status": "failed", "seconds": round(time.time() - started, 1), "error": repr(exc)[:400]}
            print(f"[WARN] {repo}: {exc!r}", file=sys.stderr, flush=True)
        save()
    status["finished_epoch"] = int(time.time())
    save()
    print("[DONE] prefetch", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
