#!/usr/bin/env python3
"""Fail fast on generation-host gaps before Phase 0 extraction."""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

PROMPT_PLACEHOLDER = "../AI_AGENT_PROMPT_SUBMITTED_<WORKLOADS>_<UTC_TIMESTAMP>.md"


def start_command(prompt_file: str = "") -> str:
    """The one supported start command, run from the generator directory in Git Bash or bash.

    It names this interpreter, disables Git Bash path conversion, and passes the prompt
    as a path relative to the generator (the prompt is saved in the project root).
    """
    python = sys.executable or "python3"
    if os.name == "nt":
        try:
            from host_exec import to_git_bash_path

            python = to_git_bash_path(python)
        except Exception:  # noqa: BLE001 - fall back to the native path
            python = python.replace("\\", "/")
    prompt = prompt_file or PROMPT_PLACEHOLDER
    if prompt_file:
        try:
            prompt = os.path.relpath(Path(prompt_file).resolve(), Path(__file__).resolve().parents[1]).replace("\\", "/")
        except ValueError:
            prompt = prompt_file.replace("\\", "/")
    quoted = f'"{python}"' if " " in python else python
    return f"MSYS_NO_PATHCONV=1 {quoted} scripts/run_from_prompt.py --prompt-file {prompt}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Check generation-host prerequisites")
    parser.add_argument("--template-root", default=".")
    parser.add_argument("--ssh-target", default="", help="Optional host for ssh -o BatchMode reachability")
    parser.add_argument("--prompt-file", default="", help="Saved prompt; fills the printed start command")
    args = parser.parse_args()
    errors: list[str] = []
    warnings: list[str] = []

    if sys.version_info < (3, 10):
        errors.append(f"Python 3.10+ required, found {sys.version}")
    try:
        import yaml  # noqa: F401
    except ImportError:
        errors.append("PyYAML is not importable on this interpreter")
    if shutil.which("rg") is None:
        warnings.append("ripgrep (rg) is not on PATH; self_check will fail on the validation host")
    if os.name == "nt":
        try:
            from host_exec import resolve_host_bash

            resolve_host_bash()
        except SystemExit as exc:
            errors.append(str(exc))

    template = Path(args.template_root).resolve()
    required = [
        "AGENTS.md",
        "BenchmarkSpecDefinitions.xlsx",
        "docs/generation-workflow.md",
        "scripts/extract_benchmark_definition.py",
        "scripts/generated_repo_directory.py",
        "scripts/fill_generated_docs.py",
        "scripts/framework_registry.py",
        "scripts/platform_policy.py",
        "config/framework_registry.yaml",
        "config/platform_policy.yaml",
        "implementation_components/component.schema.json",
    ]
    for rel in required:
        if not (template / rel).exists():
            errors.append(f"missing template file: {rel}")

    if args.ssh_target:
        if shutil.which("ssh") is None:
            errors.append("ssh is not on PATH but --ssh-target was provided")
        else:
            warnings.append(f"SSH target recorded for later remote validation: {args.ssh_target}")

    print("[INFO] Write generated .sh/.py/.md/.yaml/.json/.txt as LF only, including nested *_copy/.")
    print("[INFO] Do not start a second overlapping setup.sh on the remote VM.")
    for warning in warnings:
        print(f"[WARN] {warning}")
    command = start_command(args.prompt_file)
    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        print("[FAIL] Fix the items above, then start generation from the generator directory with exactly:")
        print(f"  {command}")
        return 1
    print("[PASS] Generation-host preflight succeeded")
    if args.prompt_file:
        print("[INFO] Start generation from the generator directory with exactly:")
        print(f"  {command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
