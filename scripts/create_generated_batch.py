#!/usr/bin/env python3
# File: scripts/create_generated_batch.py
# Version: 1.2.0
# Maintainer: AI Agent GPU Benchmark Repo Generator
# Date: 2026-08-09
# Description: Legacy scaffold helper that creates multiple sibling repository roots from one prompt.
# Execution: python3 scripts/create_generated_batch.py --prompt-file <SUBMITTED_PROMPT_FILE>
# Options: --prompt-file, --template-root, --project-root, --force, --refresh-remote, --confirm-remote-refresh
# Requirements: Python 3.10+; complete template; optional doctl for remote refresh.
# Environment: Run from the template directory or provide --template-root explicitly.
# Dependencies: argparse, datetime, json, pathlib, re, subprocess, tempfile.
# Variables: None.
# Repository: gpu-bench/sys-bench template
# License: Apache-2.0
#
# IMPORTANT: AI Coding Agent chatbox multi-workload generation MUST NOT use this script.
# Agents must call create_generated_repo.py --workload <N> one workload at a time and finish
# each workload (checklist + smoke, including remote when supplied) before creating the next
# directory. See docs/AI_AGENT_INSTRUCTIONS.md "Strict sequential multi-workload generation".

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from generated_repo_directory import generated_repo_directory_name
from prompt_workflow import (
    available_workloads,
    parse_workloads,
    submitted_prompt_path,
    workload_token,
    write_submitted_prompt,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Legacy scaffold helper for multiple sibling repository roots. "
            "AI Coding Agents must not use this for chatbox multi-workload generation; "
            "use create_generated_repo.py --workload <N> sequentially instead."
        )
    )
    parser.add_argument(
        "--prompt-file",
        default="",
        help="Timestamped submitted prompt; defaults to the newest project-root artifact.",
    )
    parser.add_argument("--template-root", default=".")
    parser.add_argument("--project-root", default="")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--refresh-remote",
        action="store_true",
        help="Request a destructive remote VM rebuild when the prompt contains an SSH target",
    )
    parser.add_argument(
        "--confirm-remote-refresh",
        action="store_true",
        help="Explicitly confirm the destructive remote VM rebuild requested by --refresh-remote",
    )
    return parser.parse_args()


def _prompt_text(path: Path) -> str:
    if not path.is_file():
        raise SystemExit(f"[FAIL] Prompt file does not exist: {path}")
    return path.read_text(encoding="utf-8")


def _latest_prompt(project_root: Path) -> Path:
    candidates = sorted(
        project_root.glob("AI_AGENT_PROMPT_SUBMITTED_*.md"),
        key=lambda path: path.stat().st_mtime,
    )
    if not candidates:
        raise SystemExit(
            "[FAIL] No submitted prompt supplied. Use --prompt-file or create a "
            "timestamped project-root prompt artifact."
        )
    return candidates[-1]


def _remote_ip(text: str) -> str:
    matches = re.findall(
        r"\bssh\b[^\n]*@((?:\d{1,3}\.){3}\d{1,3})\b",
        text,
        flags=re.IGNORECASE,
    )
    unique = list(dict.fromkeys(matches))
    if len(unique) > 1:
        raise SystemExit("[FAIL] Batch prompt contains multiple remote VM IP addresses.")
    return unique[0] if unique else ""


def _write_manifest(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _format_duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds:.2f} seconds"
    whole_seconds = int(round(seconds))
    minutes, remaining = divmod(whole_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours} hour" + ("s" if hours != 1 else ""))
    if minutes:
        parts.append(f"{minutes} minute" + ("s" if minutes != 1 else ""))
    if remaining or not parts:
        parts.append(f"{remaining} second" + ("s" if remaining != 1 else ""))
    return " ".join(parts)


def _generated_identity(project_root: Path, workload: str) -> tuple[str, str]:
    for candidate in project_root.iterdir():
        definition = candidate / "benchmark_specification.json"
        if not definition.is_file():
            continue
        try:
            fields = {
                str(item.get("field_name")): str(item.get("value", ""))
                for item in json.loads(definition.read_text(encoding="utf-8"))
                if isinstance(item, dict)
            }
        except (OSError, json.JSONDecodeError):
            continue
        if fields.get("Workload Number") == workload:
            repo_name = fields.get("Repo Base Name") or fields.get("Repo Name") or candidate.name
            return generated_repo_directory_name(workload, repo_name), str(candidate)
    return "", ""


def main() -> int:
    args = parse_args()
    print(
        "[WARN] create_generated_batch.py is a legacy scaffold helper. "
        "AI Coding Agent chatbox multi-workload generation must use "
        "create_generated_repo.py --workload <N> one workload at a time and must not "
        "pre-create later workload directories.",
        file=sys.stderr,
    )
    template_root = Path(args.template_root).resolve()
    project_root = (
        Path(args.project_root).resolve()
        if args.project_root
        else template_root.parent
    )
    if template_root == project_root or project_root not in template_root.parents:
        raise SystemExit("[FAIL] Template root must be a child of the project root.")
    prompt_path = (
        Path(args.prompt_file).resolve()
        if args.prompt_file
        else _latest_prompt(project_root)
    )
    prompt_text = _prompt_text(prompt_path)
    available = available_workloads(template_root / "BenchmarkSpecDefinitions.xlsx")
    workloads = parse_workloads(prompt_text, available)
    if not prompt_path.name.startswith("AI_AGENT_PROMPT_SUBMITTED_"):
        artifact = submitted_prompt_path(project_root, workload_token(workloads, available))
        write_submitted_prompt(prompt_text, artifact, workloads)
        prompt_path = artifact
        prompt_text = artifact.read_text(encoding="utf-8")
        print(f"[PASS] Submitted prompt artifact: {prompt_path}")
    remote_ip = _remote_ip(prompt_text)
    manifest_path = project_root / "batch_generation_manifest.json"
    started = _utc_now()
    manifest: dict[str, object] = {
        "schema_version": "1.0.0",
        "generation_started_at": started,
        "generation_finished_at": None,
        "generation_duration_seconds": None,
        "prompt_file": str(prompt_path),
        "submitted_prompt_artifact": str(prompt_path),
        "requested_workloads": workloads,
        "remote_validation_ip": remote_ip or None,
        "remote_refresh_requested": bool(remote_ip and args.refresh_remote),
        "remote_refresh_confirmed": bool(remote_ip and args.refresh_remote and args.confirm_remote_refresh),
        "remote_refresh_status": "validation_only" if remote_ip else "not_requested",
        "repositories": [],
    }
    _write_manifest(manifest_path, manifest)

    if remote_ip and args.refresh_remote and not args.confirm_remote_refresh:
        raise SystemExit(
            "[FAIL] Remote VM refresh is destructive. Re-run with "
            "--confirm-remote-refresh after explicit user confirmation."
        )
    if remote_ip and args.refresh_remote:
        refresh = subprocess.run(
            [
                "bash",
                str(template_root / "scripts/refresh_remote_vm.sh"),
                remote_ip,
                "--confirm",
            ],
            cwd=template_root,
            check=False,
        )
        manifest["remote_refresh_status"] = (
            "submitted" if refresh.returncode == 0 else "failed"
        )
        _write_manifest(manifest_path, manifest)

    results = manifest["repositories"]
    assert isinstance(results, list)
    cumulative_create_seconds = 0.0
    with tempfile.TemporaryDirectory(prefix=".batch_prompt_", dir=project_root) as temp:
        for workload in workloads:
            single_prompt = Path(temp) / f"workload_{workload}.md"
            single_prompt.write_text(
                f"@docs/AI_AGENT_INSTRUCTIONS.md\nGenerate workload {workload}.\n",
                encoding="utf-8",
            )
            command = [
                sys.executable,
                str(template_root / "scripts/create_generated_repo.py"),
                "--prompt-file",
                str(single_prompt),
                "--template-root",
                str(template_root),
                "--project-root",
                str(project_root),
                "--workload",
                workload,
                "--skip-remote-refresh",
            ]
            if args.force:
                command.append("--force")
            create_started_at = _utc_now()
            create_started_monotonic = time.monotonic()
            completed = subprocess.run(command, cwd=template_root, check=False)
            create_finished_at = _utc_now()
            create_elapsed_seconds = time.monotonic() - create_started_monotonic
            cumulative_create_seconds += create_elapsed_seconds
            create_total_time = _format_duration(create_elapsed_seconds)
            entry: dict[str, object] = {
                "workload": workload,
                "status": "passed" if completed.returncode == 0 else "failed",
                "return_code": completed.returncode,
                "create_start_time": create_started_at,
                "create_end_time": create_finished_at,
                "create_total_time": create_total_time,
            }
            if completed.returncode == 0:
                repo_name, repo_path = _generated_identity(project_root, workload)
                entry.update(repo_name=repo_name, repo_path=repo_path)
            results.append(entry)
            _write_manifest(manifest_path, manifest)

    finished = dt.datetime.now(dt.timezone.utc)
    manifest["generation_finished_at"] = _utc_now()
    start_time = dt.datetime.fromisoformat(started.replace("Z", "+00:00"))
    manifest["generation_duration_seconds"] = int(
        (finished - start_time).total_seconds()
    )
    _write_manifest(manifest_path, manifest)
    validation = subprocess.run(
        [
            sys.executable,
            str(template_root / "scripts/validate_template_inputs.py"),
            "--batch-manifest",
            str(manifest_path),
            "--batch-schema",
            str(template_root / "schemas/batch_generation_report.schema.json"),
        ],
        cwd=template_root,
        check=False,
    )
    passed = sum(entry["status"] == "passed" for entry in results)
    failed = len(results) - passed
    print(f"[INFO] Batch manifest: {manifest_path}")
    print("[INFO] Repository creation times:")
    print("| Repository number | Create total time |")
    print("|---:|---:|")
    for entry in results:
        print(f"| {entry['workload']} | {entry['create_total_time']} |")
    print(
        "[INFO] Cumulative repository creation time: "
        f"{_format_duration(cumulative_create_seconds)}"
    )
    print(f"[PASS] Workloads passed: {passed}")
    print(f"[FAIL] Workloads failed: {failed}" if failed else "[PASS] No workload failures")
    return 0 if failed == 0 and validation.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
