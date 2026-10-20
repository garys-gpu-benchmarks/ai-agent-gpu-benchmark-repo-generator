#!/usr/bin/env python3
# File: scripts/log_generator_repair.py
# Description: Append one generator repair (file and reason) to results/generator_repairs.md.
# Any change to a file in this generator during a batch is logged here. run_from_prompt.py
# prints the entries added during the batch at the end of its summary.
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

HEADER = (
    "# Generator repairs\n\n"
    "One line per change to a generator file made while a batch was running.\n"
    "Format: UTC time | workload | file | reason\n\n"
)


def repairs_path(template_root: Path) -> Path:
    return template_root / "results" / "generator_repairs.md"


def read_entries(template_root: Path) -> list[str]:
    path = repairs_path(template_root)
    if not path.is_file():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("- ")]


def append_entry(template_root: Path, file: str, reason: str, workload: str = "") -> str:
    path = repairs_path(template_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    clean_reason = " ".join(reason.split())
    line = f"- {stamp} | {workload or '-'} | {file.replace(chr(92), '/')} | {clean_reason}"
    existing = path.read_text(encoding="utf-8") if path.is_file() else HEADER
    if not existing.endswith("\n"):
        existing += "\n"
    path.write_text(existing + line + "\n", encoding="utf-8", newline="\n")
    return line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Log one generator repair made during a batch")
    parser.add_argument("--file", required=True, help="Generator-relative path of the changed file")
    parser.add_argument("--reason", required=True, help="One sentence: what failed and what changed")
    parser.add_argument("--workload", default="", help="Workload being generated when the fix was needed")
    args = parser.parse_args(argv)
    if not args.reason.strip():
        print("[FAIL] --reason must not be empty", file=sys.stderr)
        return 2
    template_root = Path(__file__).resolve().parents[1]
    line = append_entry(template_root, args.file, args.reason, args.workload)
    print(f"[INFO] Logged generator repair: {line[2:]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
