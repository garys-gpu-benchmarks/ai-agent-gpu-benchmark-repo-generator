#!/usr/bin/env python3
# File: scripts/create_generated_repo.py
# Version: 1.5.0
# Maintainer: AI Agent GPU Benchmark Repo Generator
# Date: 2026-10-18
# Description: Creates an independently publishable workload repository with a gitignored nested template copy used during generation
#              (removed by create_one_workload.py once the workload passes, or by scripts/remove_template_copy.py).
# Execution: python3 scripts/create_generated_repo.py --prompt-file <SUBMITTED_PROMPT_FILE>
# Options: --workload, --prompt-file, --template-root, --project-root, --repo-name, --force, --skip-remote-refresh, --refresh-remote, --confirm-remote-refresh
# Requirements: Python 3.10+; template workbook and schema files
# Environment: Run from the template directory or provide --template-root explicitly.
# Dependencies: argparse, json, pathlib, shutil, subprocess, sys, remove_template_copy
# Variables: TEMPLATE_COPY_SUFFIX controls the active nested template directory name.
# Repository: gpu-bench/sys-bench template
# License: Apache-2.0

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from generated_repo_directory import generated_repo_directory_name
from remove_template_copy import reliable_temp_dir, rmtree_reliable
from prompt_workflow import (
    available_workloads,
    parse_workloads,
)


TEMPLATE_COPY_SUFFIX = "_copy"
REQUIRED_TEMPLATE_FILES = (
    "AGENTS.md",
    ".claude/CLAUDE.md",
    "legal/NOTICE",
    "BenchmarkSpecDefinitions.xlsx",
    "docs/generation-workflow.md",
    "schemas/benchmark_specification.schema.json",
    "scripts/extract_benchmark_definition.py",
    "scripts/generate_benchmark_config.py",
    "scripts/init_generated_repo.py",
    "scripts/create_one_workload.py",
    "scripts/setup_bundle.py",
    "scripts/implementation_pack.py",
    "config/implementation_packs.yaml",
    "scripts/templates/setup_cpu_system_skeleton.sh",
    "scripts/materialize_generated_harness.py",
    "scripts/apply_component_gaps.py",
    "scripts/generation_host_preflight.py",
    "scripts/refresh_remote_vm.sh",
    "scripts/validate_template_inputs.py",
    "scripts/generated_repo_directory.py",
    "scripts/fill_generated_docs.py",
    "scripts/framework_registry.py",
    "scripts/platform_policy.py",
    "scripts/metric_contract.py",
    "scripts/host_exec.py",
    "scripts/text_io.py",
    "config/framework_registry.yaml",
    "config/platform_policy.yaml",
    "config/ci_contract.yaml",
    "scripts/ci_contract.py",
    "templates/workload/.github/workflows/ci.yml",
    "templates/workload/.github/workflows/gpu-smoke.yml",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a workload repository from a complete active template copy"
    )
    parser.add_argument(
        "--workload",
        default="",
        help="Workload number from the matrix; defaults to the submitted prompt",
    )
    parser.add_argument(
        "--prompt-file",
        default="",
        help="Submitted prompt containing 'Generate workload <number>.'",
    )
    parser.add_argument(
        "--template-root",
        default=".",
        help="Current template directory; defaults to the current directory",
    )
    parser.add_argument(
        "--project-root",
        default="",
        help="Project root containing the generated repository; defaults to template parent",
    )
    parser.add_argument(
        "--repo-name",
        default="",
        help="Optional expected repository name; must match the extracted definition",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing non-empty generated repository",
    )
    parser.add_argument(
        "--skip-remote-refresh",
        action="store_true",
        help="Do not refresh a remote VM during local repository generation",
    )
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


def _latest_prompt(project_root: Path) -> Path:
    candidates = sorted(
        project_root.glob("AI_AGENT_PROMPT_SUBMITTED_*.md"),
        key=lambda path: path.stat().st_mtime,
    )
    if not candidates:
        raise SystemExit(
            "[FAIL] No submitted prompt supplied. Use --prompt-file or create "
            "AI_AGENT_PROMPT_SUBMITTED_<WORKLOADS>_<UTC_TIMESTAMP>.md in the project root."
        )
    return candidates[-1]


def _workload_from_prompt(prompt_path: Path, matrix_path: Path) -> str:
    if not prompt_path.is_file():
        raise SystemExit(
            f"[FAIL] No workload supplied and prompt file is missing: {prompt_path}"
        )
    text = prompt_path.read_text(encoding="utf-8")
    workloads = parse_workloads(text, available_workloads(matrix_path))
    if len(workloads) != 1:
        raise SystemExit(
            "[FAIL] Single-repository generation requires exactly one workload in the prompt."
        )
    return workloads[0]


def _remote_ip_from_prompt(prompt_path: Path) -> str:
    text = prompt_path.read_text(encoding="utf-8")
    matches = re.findall(
        r"\bssh\b[^\n]*@((?:\d{1,3}\.){3}\d{1,3})\b",
        text,
        flags=re.IGNORECASE,
    )
    if not matches:
        return ""
    if len(set(matches)) != 1:
        raise SystemExit(
            "[FAIL] Prompt must contain at most one SSH remote IPv4 address."
        )
    return matches[0]


def _validate_template_root(template_root: Path) -> None:
    missing = [rel for rel in REQUIRED_TEMPLATE_FILES if not (template_root / rel).exists()]
    if missing:
        missing_text = ", ".join(missing)
        raise SystemExit(f"[FAIL] Template root is incomplete; missing: {missing_text}")


def _run(command: list[str], cwd: Path) -> None:
    print("[RUN] " + " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def _definition_fields(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(item["field_name"]): str(item.get("value", "")).strip()
        for item in data
        if isinstance(item, dict) and "field_name" in item
    }


def _ignore_template_copy(path: str, names: list[str]) -> set[str]:
    ignored = {
        "archive",
        "tests",
        "__pycache__",
        "BenchmarkMatrixDefinitions_1_0.xlsx",
        "BenchmarkMatrixDefinitions_1_1.xlsx",
        "BenchmarkMatrixDefinitions_1_1_populated.xlsx",
    }
    ignored.update(name for name in names if name.startswith("~$") or name.endswith(".egg-info"))
    return ignored.intersection(names)


def _copy_template(source: Path, destination: Path) -> None:
    if destination.exists():
        if not rmtree_reliable(destination):
            raise SystemExit(f"[FAIL] Could not remove the old template copy at {destination}.")
    shutil.copytree(source, destination, ignore=_ignore_template_copy)


# Laptop-side tools the operator runs from the project folder (the folder that
# holds the template/workload folder). get_remote_info.sh writes DIRECTORIES/ and
# RUNTIME_LEDGERS/ next to itself; show_metrics.sh prints one workload's metrics
# from a runtime ledger (local or over ssh). The master copies stay in
# templates/suite-tools/scripts/ (published as gpu-bench-suite); they are never
# copied into a workload. The VM copy is separate: create_one_workload.py and
# the bundle publish both install show_metrics.sh at /opt/benchmarks.
OPERATOR_TOOLS = (
    "templates/suite-tools/scripts/get_remote_info.sh",
    "templates/suite-tools/scripts/show_metrics.sh",
)


def refresh_show_metrics(source_root: Path) -> bool:
    """Regenerate show_metrics.sh's short-label table from the Metric_Short_Labels sheet.

    A problem in the sheet is reported but does not stop workload generation;
    the existing master copy is installed instead.
    """
    script = source_root / "scripts" / "generate_show_metrics.py"
    if not script.is_file():
        print("[WARN] scripts/generate_show_metrics.py is missing; show_metrics.sh labels not regenerated.")
        return False
    result = subprocess.run(
        [sys.executable, str(script), "--template-root", str(source_root)],
        cwd=source_root,
        capture_output=True,
        text=True,
        check=False,
    )
    for line in (result.stdout + result.stderr).splitlines():
        print(line)
    if result.returncode != 0:
        print(
            "[WARN] show_metrics.sh labels were not regenerated (see above); installing the existing copy. "
            "Fix the Metric_Short_Labels sheet, then run python3 scripts/generate_show_metrics.py."
        )
        return False
    return True


def install_operator_tools(source_root: Path, project_root: Path) -> list[Path]:
    """Copy OPERATOR_TOOLS into project_root.parent. An existing copy that differs is kept."""
    target_dir = project_root.parent
    installed: list[Path] = []
    for rel in OPERATOR_TOOLS:
        src = source_root / rel
        if not src.is_file():
            print(f"[WARN] Operator tool missing from the template: {rel}")
            continue
        dst = target_dir / src.name
        data = src.read_bytes().replace(b"\r\n", b"\n")
        if dst.exists():
            if dst.read_bytes().replace(b"\r\n", b"\n") != data:
                print(f"[INFO] Kept existing {dst}; it differs from {rel}. Delete it to get the generator's copy.")
            continue
        dst.write_bytes(data)
        dst.chmod(dst.stat().st_mode | 0o111)
        installed.append(dst)
        print(f"[INFO] Installed operator tool: {dst}")
    return installed


def main() -> int:
    args = parse_args()
    source_root = Path(args.template_root).resolve()
    _validate_template_root(source_root)
    _run(
        [sys.executable, "scripts/generation_host_preflight.py", "--template-root", str(source_root)],
        source_root,
    )
    project_root = (
        Path(args.project_root).resolve()
        if args.project_root
        else source_root.parent
    )
    if source_root.parent != project_root and source_root not in project_root.parents:
        raise SystemExit("[FAIL] Template root must be located under the project root.")
    prompt_path = Path(args.prompt_file).resolve() if args.prompt_file else _latest_prompt(project_root)
    matrix_path = source_root / "BenchmarkSpecDefinitions.xlsx"
    workload = args.workload.strip() or _workload_from_prompt(prompt_path, matrix_path)
    if not workload.isdigit():
        raise SystemExit("[FAIL] Workload number must contain only digits.")
    if args.prompt_file:
        print(f"[INFO] Read workload {workload} from submitted prompt: {prompt_path}")
    remote_ip = _remote_ip_from_prompt(prompt_path)
    if remote_ip and args.refresh_remote and not args.confirm_remote_refresh:
        raise SystemExit(
            "[FAIL] Remote VM refresh is destructive. Re-run with "
            "--confirm-remote-refresh after explicit user confirmation."
        )
    if remote_ip and args.refresh_remote and not args.skip_remote_refresh:
        print(f"[INFO] Refreshing remote validation VM at {remote_ip}")
        _run(
            ["bash", str(source_root / "scripts/refresh_remote_vm.sh"), remote_ip, "--confirm"],
            source_root,
        )
    elif remote_ip:
        print(f"[INFO] Remote validation target detected; refresh not requested: {remote_ip}")

    copy_name = (
        source_root.name
        if source_root.name.endswith(TEMPLATE_COPY_SUFFIX)
        else source_root.name + TEMPLATE_COPY_SUFFIX
    )

    with reliable_temp_dir(
        prefix=f".{source_root.name}_{workload}_",
        dir=project_root,
    ) as discovery_dir:
        discovery_root = Path(discovery_dir) / copy_name
        _copy_template(source_root, discovery_root)
        _run(
            [
                sys.executable,
                "scripts/extract_benchmark_definition.py",
                "--workload",
                workload,
                "--matrix",
                "BenchmarkSpecDefinitions.xlsx",
                "--output",
                "benchmark_specification.json",
            ],
            discovery_root,
        )
        _run(
            [
                sys.executable,
                "scripts/validate_template_inputs.py",
                "--benchmark-specification",
                "benchmark_specification.json",
                "--benchmark-schema",
                "schemas/benchmark_specification.schema.json",
            ],
            discovery_root,
        )

        fields = _definition_fields(discovery_root / "benchmark_specification.json")
        repo_name = fields.get("Repo Name", "")
        workload_name = fields.get("Workload Name", "")
        if not repo_name or not workload_name:
            raise SystemExit("[FAIL] Extracted definition lacks Workload Name or Repo Name.")
        if args.repo_name and args.repo_name != repo_name:
            raise SystemExit(
                f"[FAIL] --repo-name {args.repo_name!r} does not match extracted Repo Name {repo_name!r}."
            )

        repo_root = (project_root / generated_repo_directory_name(workload, repo_name)).resolve()
        active_copy = repo_root / copy_name
        if repo_root == source_root or repo_root in source_root.parents:
            raise SystemExit(
                "[FAIL] Generated repository would contain the source template; "
                "use a sibling project-root layout."
            )
        if repo_root.exists() and any(repo_root.iterdir()) and not args.force:
            raise SystemExit(
                f"[FAIL] Target already exists and is non-empty: {repo_root}. Use --force to replace it."
            )
        if repo_root.exists() and args.force and not rmtree_reliable(repo_root):
            raise SystemExit(
                f"[FAIL] --force could not remove the existing {repo_root}. "
                "Close any editor, terminal or file browser open inside it, then re-run."
            )
        repo_root.mkdir(parents=True, exist_ok=True)
        _copy_template(source_root, active_copy)

        _run(
            [
                sys.executable,
                "scripts/extract_benchmark_definition.py",
                "--workload",
                workload,
                "--matrix",
                "BenchmarkSpecDefinitions.xlsx",
                "--output",
                "benchmark_specification.json",
            ],
            active_copy,
        )
        _run(
            [
                sys.executable,
                "scripts/validate_template_inputs.py",
                "--benchmark-specification",
                "benchmark_specification.json",
                "--benchmark-schema",
                "schemas/benchmark_specification.schema.json",
            ],
            active_copy,
        )
        _run(
            [
                sys.executable,
                "scripts/init_generated_repo.py",
                "--repo-name",
                repo_name,
                "--template-root",
                str(active_copy),
                "--repo-root",
                str(repo_root),
                "--force",
            ],
            active_copy,
        )
        _run(
            [
                sys.executable,
                "scripts/generate_benchmark_config.py",
                "--benchmark-specification",
                str(repo_root / "benchmark_specification.json"),
                "--output",
                str(repo_root / "config" / "benchmark_config.yaml"),
                "--components-root",
                str(active_copy / "implementation_components"),
            ],
            active_copy,
        )
        _run(
            [
                sys.executable,
                "scripts/apply_component_gaps.py",
                "--repo-root",
                str(repo_root),
                "--components-root",
                str(active_copy / "implementation_components"),
            ],
            active_copy,
        )
        _run(
            [
                sys.executable,
                "scripts/fill_generated_docs.py",
                "--repo-root",
                str(repo_root),
                "--template-root",
                str(active_copy),
            ],
            active_copy,
        )
        from text_io import ensure_gitkeep, normalize_text_tree

        ensure_gitkeep(repo_root)
        normalize_text_tree(repo_root)
        refresh_show_metrics(source_root)
        install_operator_tools(source_root, project_root)
        print(f"[PASS] Created generated repository: {repo_root}")
        print(f"[PASS] Active template copy: {active_copy}")
        print(
            "[INFO] The active template copy is a generation workspace. create_one_workload.py removes it once "
            "the workload passes; otherwise run: python3 scripts/remove_template_copy.py --repo-root "
            f"\"{repo_root}\""
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
