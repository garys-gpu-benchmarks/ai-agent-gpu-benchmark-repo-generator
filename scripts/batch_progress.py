#!/usr/bin/env python3
"""Batch progress file: the few lines an agent waits on, outside the console.

Cursor stops showing a long-running command's output after about 1,000 lines
(110 KB). In the TEMPLATE_00_140 batches the 101-132 console froze on workload 114
and the 201-232 console on 214, so the `[RECORD] <N>` lines the agents wait on never
appeared and waits returned up to 30 minutes late. Every line printed through
progress() is also appended to batch_progress.log in the project root: one line per
workload record or failure, the Successful time summary, and a final [DONE] line when
the batch process exits. That is about 35 lines per batch, so a terminal that follows
the file (tail -F) never reaches the console limit.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

PROGRESS_LOG_NAME = "batch_progress.log"


def progress_path(project_root: Path) -> Path:
    return Path(project_root) / PROGRESS_LOG_NAME


def start(project_root: Path, workloads: list[str]) -> None:
    """Start a new progress file for this batch (an earlier batch's lines are removed)."""
    path = progress_path(project_root)
    path.write_text(
        f"[INFO] batch started {_now()} workloads {', '.join(workloads)}\n", encoding="utf-8", newline="\n"
    )


def progress(project_root: Path | None, line: str) -> None:
    """Print one line to the console and append it, with a UTC time, to batch_progress.log."""
    print(line, flush=True)
    if project_root is None:
        return
    try:
        with progress_path(project_root).open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"{line} | {_now()}\n")
    except OSError as exc:  # the console line is already out; never fail the batch for this
        print(f"[WARN] could not append to {PROGRESS_LOG_NAME}: {exc}", flush=True)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
