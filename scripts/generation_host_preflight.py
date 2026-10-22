#!/usr/bin/env python3
"""Fail fast on generation-host gaps before Phase 0 extraction."""
from __future__ import annotations

import argparse
import glob
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

PROMPT_PLACEHOLDER = "../AI_AGENT_PROMPT_SUBMITTED_<WORKLOADS>_<UTC_TIMESTAMP>.md"


def _display_path(python: str) -> str:
    """Show an interpreter path the way Git Bash would type it."""
    if os.name == "nt" or (len(python) > 2 and python[1] == ":"):
        try:
            from host_exec import to_git_bash_path

            return to_git_bash_path(python)
        except Exception:  # noqa: BLE001 - fall back to the native path
            return python.replace("\\", "/")
    return python


def start_command(prompt_file: str = "", python: list[str] | None = None) -> str:
    """The one supported start command, run from the generator directory in Git Bash or bash.

    It names the interpreter (this one unless another is given), disables Git Bash path
    conversion, and passes the prompt as a path relative to the generator (the prompt is
    saved in the project root).
    """
    words = list(python) if python else [sys.executable or "python3"]
    words[0] = _display_path(words[0])
    interpreter = " ".join(f'"{word}"' if " " in word else word for word in words)
    prompt = prompt_file or PROMPT_PLACEHOLDER
    if prompt_file:
        try:
            prompt = os.path.relpath(Path(prompt_file).resolve(), Path(__file__).resolve().parents[1]).replace("\\", "/")
        except ValueError:
            prompt = prompt_file.replace("\\", "/")
    return f"MSYS_NO_PATHCONV=1 {interpreter} scripts/run_from_prompt.py --prompt-file {prompt}"


PYTHON_CHECK = "import sys, yaml; assert sys.version_info >= (3, 10)"


def candidate_pythons() -> list[list[str]]:
    """Interpreters to try, in order, when this one lacks Python 3.10+ or PyYAML.

    GENERATOR_PYTHON (if set), then python3, python and py -3 on PATH, then the usual
    Windows install folders. Duplicates and this interpreter are skipped.
    """
    found: list[list[str]] = []
    override = os.environ.get("GENERATOR_PYTHON", "").strip()
    if override:
        found.append(shlex.split(override, posix=os.name != "nt") or [override])
    for name in ("python3", "python"):
        path = shutil.which(name)
        if path:
            found.append([path])
    launcher = shutil.which("py")
    if launcher:
        found.append([launcher, "-3"])
    patterns = ["/c/Python/python.exe", "/c/Python3*/python.exe", "C:/Python/python.exe", "C:/Python3*/python.exe"]
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        patterns.append(str(Path(local) / "Programs" / "Python" / "Python3*" / "python.exe"))
    for pattern in patterns:
        for path in sorted(glob.glob(pattern), reverse=True):
            found.append([path])
    unique: list[list[str]] = []
    seen = {os.path.normcase(os.path.realpath(sys.executable))} if sys.executable else set()
    for words in found:
        key = os.path.normcase(os.path.realpath(words[0])) + " " + " ".join(words[1:])
        if key in seen:
            continue
        seen.add(key)
        unique.append(words)
    return unique


def passes_python_check(words: list[str]) -> bool:
    """True when this interpreter is Python 3.10+ and imports PyYAML."""
    try:
        result = subprocess.run([*words, "-c", PYTHON_CHECK], capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def has_pip(words: list[str]) -> bool:
    try:
        result = subprocess.run(
            [*words, "-c", "import sys, pip; assert sys.version_info >= (3, 10)"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def find_working_python() -> tuple[list[str] | None, list[list[str]]]:
    """Return the first candidate that passes the Python check, and every candidate tried."""
    tried = candidate_pythons()
    for words in tried:
        if passes_python_check(words):
            return words, tried
    return None, tried


def main() -> int:
    parser = argparse.ArgumentParser(description="Check generation-host prerequisites")
    parser.add_argument("--template-root", default=".")
    parser.add_argument("--ssh-target", default="", help="Optional host for ssh -o BatchMode reachability")
    parser.add_argument("--prompt-file", default="", help="Saved prompt; fills the printed start command")
    args = parser.parse_args()
    errors: list[str] = []
    warnings: list[str] = []
    python_errors: list[str] = []

    if sys.version_info < (3, 10):
        python_errors.append(f"Python 3.10+ required, found {sys.version.split()[0]}")
    try:
        import yaml  # noqa: F401
    except ImportError:
        python_errors.append("PyYAML is not importable")
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
    if python_errors:
        this_python = _display_path(sys.executable or "python3")
        for error in python_errors:
            print(f"[FAIL] {error} on {this_python}")
        for error in errors:
            print(f"[FAIL] {error}")
        working, tried = find_working_python()
        if working:
            name = " ".join(_display_path(word) if index == 0 else word for index, word in enumerate(working))
            if errors:
                print(f"[INFO] {name} has Python 3.10+ and PyYAML. Fix the other items above, then start generation from the generator directory with exactly:")
            else:
                print(f"[INFO] {name} passes preflight. Start generation from the generator directory with exactly:")
            print(f"  {start_command(args.prompt_file, working)}")
        else:
            names = ", ".join(" ".join(words) for words in tried) or "none found"
            print(f"[FAIL] No Python 3.10+ with PyYAML was found. Tried: {names}")
            with_pip = next((words for words in tried if has_pip(words)), None)
            if with_pip:
                print(f"[INFO] Install PyYAML into a Python that has pip, then run preflight again:  {' '.join(with_pip)} -m pip install pyyaml")
            else:
                print("[INFO] Install Python 3.10+ with pip (python.org), then:  python -m pip install pyyaml")
            print("[INFO] Or set GENERATOR_PYTHON to the interpreter to use, then run preflight again.")
        return 1
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
