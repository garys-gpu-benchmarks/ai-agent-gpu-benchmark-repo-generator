#!/usr/bin/env python3
# File: scripts/run_from_prompt.py
# Description: Chatbox entry point. Parse a short operator prompt and run the sequential driver.
# The template root is the directory that contains this scripts/ folder.
# Repositories are written in that directory's parent. Do not pass --remote-root.
# Children run with PYTHONDONTWRITEBYTECODE=1; leftover caches are removed at the end.
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

from generated_repo_directory import find_generated_repo  # noqa: E402
from log_generator_repair import read_entries, repairs_path  # noqa: E402
from prompt_workflow import available_workloads, parse_workloads  # noqa: E402

# Interpreter caches only. Model and package caches (.cache, .venv) are never touched.
CACHE_DIR_NAMES = ("__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def remote_ip(text: str) -> str:
    matches = re.findall(
        r"\bssh\b[^\n]*@((?:\d{1,3}\.){3}\d{1,3})\b",
        text,
        flags=re.IGNORECASE,
    )
    unique = sorted(set(matches))
    if len(unique) > 1:
        raise SystemExit("[FAIL] Prompt must contain at most one SSH remote IPv4 address.")
    return unique[0] if unique else ""


def ensure_batch_manifest(project_root: Path, prompt: Path, workloads: list[str], ip: str) -> None:
    path = project_root / "batch_generation_manifest.json"
    batch: dict = {}
    if path.is_file():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            batch = loaded
    batch.setdefault("schema_version", "1.0.0")
    batch.setdefault("generation_started_at", utc_now())
    batch["generation_finished_at"] = None
    batch["generation_duration_seconds"] = None
    batch["prompt_file"] = str(prompt)
    batch["submitted_prompt_artifact"] = str(prompt)
    batch["requested_workloads"] = workloads
    batch["remote_validation_ip"] = ip or None
    batch["remote_refresh_requested"] = False
    batch["remote_refresh_confirmed"] = False
    batch["remote_refresh_status"] = "not_requested"
    batch.setdefault("repositories", [])
    path.write_text(json.dumps(batch, indent=2) + "\n", encoding="utf-8", newline="\n")


def stamp_batch_finish(project_root: Path, workloads: list[str]) -> None:
    path = project_root / "batch_generation_manifest.json"
    if not path.is_file():
        return
    batch = json.loads(path.read_text(encoding="utf-8"))
    recorded = {str(row.get("workload")) for row in batch.get("repositories", []) if isinstance(row, dict)}
    if any(workload not in recorded for workload in workloads):
        return
    finished = utc_now()
    started = str(batch.get("generation_started_at") or finished)
    start_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(finished.replace("Z", "+00:00"))
    batch["generation_finished_at"] = finished
    batch["generation_duration_seconds"] = max(0, int((end_dt - start_dt).total_seconds()))
    path.write_text(json.dumps(batch, indent=2) + "\n", encoding="utf-8", newline="\n")


def _seconds(start: object, end: object) -> int:
    try:
        start_dt = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return 0
    return max(0, int((end_dt - start_dt).total_seconds()))


def _hms(seconds: int) -> str:
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}h {minutes:02d}m {secs:02d}s"


def batch_times(batch: dict, workloads: list[str]) -> tuple[int, int, int]:
    """Return (successful seconds, seconds including failed attempts, failed attempt count).

    Successful time is the passing attempt of each passed workload. The other total adds
    every recorded attempt, passed or not, for the requested workloads.
    """
    wanted = set(workloads)
    successful = 0
    everything = 0
    failed_attempts = 0
    for row in batch.get("repositories", []):
        if not isinstance(row, dict) or str(row.get("workload")) not in wanted:
            continue
        attempts = row.get("attempts") or [
            {"status": row.get("status"), "start": row.get("create_start_time"), "end": row.get("create_end_time")}
        ]
        for attempt in attempts:
            seconds = _seconds(attempt.get("start"), attempt.get("end"))
            everything += seconds
            if attempt.get("status") != "passed":
                failed_attempts += 1
        if row.get("status") == "passed":
            successful += _seconds(row.get("create_start_time"), row.get("create_end_time"))
    return successful, everything, failed_attempts


def print_batch_summary(project_root: Path, workloads: list[str]) -> None:
    path = project_root / "batch_generation_manifest.json"
    if not path.is_file():
        return
    batch = json.loads(path.read_text(encoding="utf-8"))
    rows = {str(r.get("workload")): r for r in batch.get("repositories", []) if isinstance(r, dict)}
    print("", flush=True)
    print("| Workload | Status | Attempts | create_total_time |", flush=True)
    print("|---|---|---|---|", flush=True)
    for workload in workloads:
        row = rows.get(workload, {})
        attempts = len(row.get("attempts") or ([row] if row else []))
        print(
            f"| {workload} | {row.get('status', 'not recorded')} | {attempts} | {row.get('create_total_time', '-')} |",
            flush=True,
        )
    successful, everything, failed_attempts = batch_times(batch, workloads)
    print(f"[INFO] Successful time: {_hms(successful)} ({successful} sec)", flush=True)
    print(
        f"[INFO] Time including failed attempts: {_hms(everything)} ({everything} sec; "
        f"{failed_attempts} failed attempt(s))",
        flush=True,
    )
    batch["generation_successful_seconds"] = successful
    batch["generation_seconds_including_failed_attempts"] = everything
    path.write_text(json.dumps(batch, indent=2) + "\n", encoding="utf-8", newline="\n")


def print_generator_repairs(template_root: Path, before: int) -> None:
    entries = read_entries(template_root)[before:]
    print("", flush=True)
    if not entries:
        print("[INFO] Generator repairs during this batch: none", flush=True)
        return
    print(f"[INFO] Generator repairs during this batch ({len(entries)}), from {repairs_path(template_root)}:", flush=True)
    for line in entries:
        print(line, flush=True)


def remove_interpreter_caches(roots: list[Path]) -> int:
    removed = 0
    for root in roots:
        if not root.is_dir():
            continue
        for dirpath, dirnames, _ in os.walk(root):
            # Never descend into virtual environments or downloaded caches.
            dirnames[:] = [d for d in dirnames if d not in (".venv", ".cache", ".git", "third_party")]
            for name in list(dirnames):
                if name in CACHE_DIR_NAMES:
                    shutil.rmtree(Path(dirpath) / name, ignore_errors=True)
                    dirnames.remove(name)
                    removed += 1
    return removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate every workload named in a short operator prompt")
    parser.add_argument("--prompt-file", required=True)
    args = parser.parse_args(argv)
    template_root = Path(__file__).resolve().parents[1]
    project_root = template_root.parent
    prompt = Path(args.prompt_file).resolve()
    if not prompt.is_file():
        raise SystemExit(f"[FAIL] Prompt file is missing: {prompt}")
    text = prompt.read_text(encoding="utf-8")
    if re.search(r"(?im)^\s*legacy\s*:", text):
        print(
            "[INFO] Legacy: line ignored. This command uses only the current template "
            "and does not read other TEMPLATE_* directories.",
            flush=True,
        )
    workloads = parse_workloads(text, available_workloads(template_root / "BenchmarkSpecDefinitions.xlsx"))
    ip = remote_ip(text)
    print(f"[INFO] Template root: {template_root}", flush=True)
    print(f"[INFO] Project root: {project_root}", flush=True)
    print(f"[INFO] Workloads: {', '.join(workloads)}", flush=True)
    print(f"[INFO] Remote validation: {ip or 'NONE'}", flush=True)
    ensure_batch_manifest(project_root, prompt, workloads, ip)
    repairs_before = len(read_entries(template_root))
    command = [
        sys.executable,
        str(template_root / "scripts" / "create_one_workload.py"),
        "--prompt-file",
        str(prompt),
        "--template-root",
        str(template_root),
        "--project-root",
        str(project_root),
        "--skip-remote-refresh",
    ]
    for workload in workloads:
        command.extend(["--workload", workload])
    env = os.environ.copy()
    env["MSYS_NO_PATHCONV"] = "1"
    env["MSYS2_ARG_CONV_EXCL"] = "*"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(command, cwd=str(template_root), env=env, check=False)
    stamp_batch_finish(project_root, workloads)
    print_batch_summary(project_root, workloads)
    roots = [template_root] + [repo for repo in (find_generated_repo(project_root, w) for w in workloads) if repo]
    removed = remove_interpreter_caches(roots)
    print(f"[INFO] Removed {removed} leftover interpreter cache folder(s)", flush=True)
    print_generator_repairs(template_root, repairs_before)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
