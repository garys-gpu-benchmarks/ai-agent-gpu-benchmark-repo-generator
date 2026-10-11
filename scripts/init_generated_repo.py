#!/usr/bin/env python3
# File: scripts/init_generated_repo.py
# Version: 1.9.0
# Maintainer: AI Agent GPU Benchmark Repo Generator
# Date: 2026-10-08
# Description: Bootstraps required generated-repository scaffolding in template mode.
# Execution: python3 scripts/init_generated_repo.py --repo-name <REPO_NAME> --template-root <TEMPLATE_ROOT> --repo-root <REPO_ROOT>
# Options: --repo-name, --template-root, --repo-root, --force, --rocm-setup
# Requirements: Python 3.10+
# Environment: Run from the current template directory with --template-root .. to place output at project root.
# Dependencies: argparse, pathlib, shutil
# Variables: None
# Repository: gpu-bench/sys-bench template
# License: Apache-2.0

from __future__ import annotations

import argparse
import datetime as dt
import json
import hashlib
import re
import shutil
from pathlib import Path

from generated_repo_directory import generated_repo_directory_name
from apply_component_gaps import apply_component_gaps
from ci_contract import ContractError, render_workload_callers
from materialize_generated_harness import materialize_generated_harness
from resolve_implementation_components import (
    resolve_components,
    validate_component_vs_spec,
    validate_overlay_conflicts,
    definition_fields,
)
from setup_bundle import SKELETON_REL, setup_bundle


# Identity files used only to locate the template root. Not all are copied
# onto the generated workload (AGENTS.md and *TEMPLATE.md stay template-only).
TEMPLATE_IDENTITY_FILES = [
    "AGENTS.md",
    ".claude/CLAUDE.md",
    "templates/PRD_TEMPLATE.md",
    "templates/SPEC_TEMPLATE.md",
    "templates/README_TEMPLATE.md",
]

SHARED_FILES = [
    "LICENSE",
    "legal/NOTICE",
    ".gitignore",
    ".gitattributes",
]

SHARED_FILE_DESTINATIONS: dict[str, str] = {}

OPTIONAL_SOURCE_FILES = ["benchmark_specification.json"]

SHARED_DIRS = [".claude", "schemas", "docs", "scripts", "config"]

REQUIRED_PATHS = [
    "setup.sh",
    "run_benchmark.sh",
    "requirements.txt",
    "config/benchmark_config.yaml",
    "scripts/build.sh",
    "scripts/parse_results.py",
    "scripts/validate_results.py",
    "scripts/self_check_generated_repo.sh",
    "scripts/check_github_publish_ready.sh",
    "results/generation_manifest.json",
    "results/raw/.gitkeep",
    "results/parsed/.gitkeep",
    "tests/fixtures/.gitkeep",
]

COPY_EXCLUSIONS = [
    "CLAUDE.md",
    "BenchmarkSpecDefinitions.xlsx",
    "~$BenchmarkSpecDefinitions.xlsx",
    "BenchmarkMatrixDefinitions.xlsx",
    "~$BenchmarkMatrixDefinitions.xlsx",
    "BenchmarkMatrixDefinitions_1_0.xlsx",
    "BenchmarkMatrixDefinitions_1_1.xlsx",
    "BenchmarkMatrixDefinitions_1_1_populated.xlsx",
    "archive",
    "tests",
    "scripts/__pycache__",
    "scripts/refresh_remote_vm.sh",
    "scripts/lib/setup_rocm_full_28_20260628_REFERENCE.sh",
    "archive/setup_rocm_full_28_20260628_REFERENCE.sh",
    # CI contract and suite-level emitters are generation-only; workloads get
    # only the rendered thin callers in .github/workflows/.
    "config/ci_contract.yaml",
    "scripts/ci_contract.py",
    "scripts/emit_shared_workflows.py",
    # Publishes the whole suite from the operator's machine; generation-only.
    "scripts/publish_benchmarks_to_github.sh",
]
NO_BUILD_STEP_SH = """#!/usr/bin/env bash
# This workload has no compile step. setup.sh calls this file; it does nothing.
set -euo pipefail
echo "[INFO] scripts/build.sh: no build step for this workload."
"""

TEXT_SUFFIXES = {".md", ".py", ".sh", ".json", ".yaml", ".yml", ".txt", ".toml"}


def _stamp_nvcc_glibc_throw(repo_root: Path) -> None:
    """Record the one canonical helper. Later validation rejects a different copy."""
    paths = [
        repo_root / "scripts" / "lib" / "nvcc_glibc_throw.sh",
        repo_root / "scripts" / "lib" / "nvcc_glibc_throw.py",
    ]
    if not all(path.is_file() for path in paths):
        return
    lines = []
    for path in paths:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(repo_root).as_posix()}")
    dest = repo_root / "results" / "nvcc_glibc_throw.sha256"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("[INFO] Stamped scripts/lib/nvcc_glibc_throw.sh")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize generated repository scaffold")
    parser.add_argument("--repo-name", required=True, help="Generated repository directory name")
    parser.add_argument("--template-root", default=".", help="Template root path")
    parser.add_argument(
        "--repo-root",
        default="",
        help="Explicit generated repository root; defaults to <workload>-<repo-name> beside the template",
    )
    parser.add_argument("--force", action="store_true", help="Allow initializing existing non-empty target")
    parser.add_argument(
        "--rocm-setup",
        action="store_true",
        help="Materialize the canonical reboot-safe ROCm setup skeleton as setup.sh",
    )
    return parser.parse_args()


def _install_generated_repo_github_files(source_root: Path, repo_root: Path) -> None:
    """Install workload-specific GitHub community files and the thin CI callers.

    The CI logic itself lives in the shared-workflows repository
    (templates/shared-workflows, emitted once by emit_shared_workflows.py).
    Each workload only gets two caller files rendered from
    templates/workload/.github/workflows and config/ci_contract.yaml.
    Dependabot is configured in shared-workflows only: the callers reference
    nothing but the shared repository, and automatic pip upgrades would change
    what a benchmark measures.
    """
    github_examples = source_root / "docs" / "examples" / "generated-repo-github"
    github_dest = repo_root / ".github"
    if not github_examples.is_dir():
        raise SystemExit(f"[FAIL] Missing generated-repo GitHub files: {github_examples}")
    github_dest.mkdir(parents=True, exist_ok=True)

    mappings = {
        "CONTRIBUTING.md": ".github/CONTRIBUTING.md",
        "SECURITY.md": ".github/SECURITY.md",
        "CODE_OF_CONDUCT.md": ".github/CODE_OF_CONDUCT.md",
        "PULL_REQUEST_TEMPLATE.md": ".github/PULL_REQUEST_TEMPLATE.md",
        "copilot-instructions.md": ".github/copilot-instructions.md",
        "ISSUE_TEMPLATE/bug_report.md": ".github/ISSUE_TEMPLATE/bug_report.md",
        "ISSUE_TEMPLATE/feature_request.md": ".github/ISSUE_TEMPLATE/feature_request.md",
        "ISSUE_TEMPLATE/config.yml": ".github/ISSUE_TEMPLATE/config.yml",
        "GITHUB_PUBLISH_WORKLOAD_REPO.md": "docs/GITHUB_PUBLISH_WORKLOAD_REPO.md",
    }
    for src_name, dest_name in mappings.items():
        src = github_examples / src_name
        if not src.is_file():
            raise SystemExit(f"[FAIL] Missing generated-repo GitHub source file: {src}")
        copy_path(src, repo_root / dest_name)

    spec_path = source_root / "benchmark_specification.json"
    if not spec_path.is_file():
        raise SystemExit(f"[FAIL] Cannot render CI callers without {spec_path}")
    try:
        identity = render_workload_callers(repo_root, _definition_fields(source_root), source_root)
    except ContractError as exc:
        raise SystemExit(f"[FAIL] CI contract: {exc}") from exc
    print(
        "[INFO] Installed workload-specific GitHub community files and CI callers "
        f"(vendor={identity['vendor']}, os_label={identity['os_label']})."
    )


def copy_path(src: Path, dst: Path) -> None:
    if src.is_dir():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if src.suffix in TEXT_SUFFIXES:
            dst.write_bytes(dst.read_bytes().replace(b"\r\n", b"\n"))


def _contains_template_files(path: Path) -> bool:
    return all((path / rel).exists() for rel in TEMPLATE_IDENTITY_FILES)


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _definition_fields(source_root: Path) -> dict[str, str]:
    definition_path = source_root / "benchmark_specification.json"
    if not definition_path.is_file():
        return {}
    data = json.loads(definition_path.read_text(encoding="utf-8"))
    return {str(item.get("field_name", "")): str(item.get("value", "")) for item in data if isinstance(item, dict)}



def _workload_id(source_root: Path) -> str:
    definition_path = source_root / "benchmark_specification.json"
    if not definition_path.is_file():
        return ""
    data = json.loads(definition_path.read_text(encoding="utf-8"))
    fields = {str(item.get("field_name")): str(item.get("value", "")) for item in data}
    return fields.get("Workload Number", "").strip()


def _gpu_vendor(source_root: Path) -> str:
    return _definition_fields(source_root).get("GPU Vendor", "").strip()


def _setup_bundle_for(source_root: Path, force_rocm: bool = False) -> str:
    return setup_bundle(_definition_fields(source_root), force_rocm=force_rocm)


def _retarget_workload_pyproject(repo_root: Path, repo_name: str) -> None:
    """Keep ruff/pytest tool config; stop shipping the generator project identity."""
    path = repo_root / "config" / "pyproject.toml"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    slug = repo_name.strip() or "generated-workload"
    text = re.sub(r'(?m)^name = ".*"', f'name = "{slug}"', text, count=1)
    text = re.sub(
        r'(?m)^description = ".*"',
        f'description = "Generated GPU/sys-bench workload repository ({slug})"',
        text,
        count=1,
    )
    text = re.sub(
        r'(?m)^readme = \{ text = ".*"',
        'readme = { text = "Workload repository tooling configuration."',
        text,
        count=1,
    )
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def _write_generation_manifest(
    repo_root: Path,
    template_root: Path,
    resolved_components: list[dict[str, object]],
) -> None:
    manifest_path = repo_root / "results" / "generation_manifest.json"
    if manifest_path.stat().st_size > 0:
        return
    definition_path = repo_root / "benchmark_specification.json"
    fields: dict[str, str] = {}
    if definition_path.is_file():
        data = json.loads(definition_path.read_text(encoding="utf-8"))
        fields = {str(item.get("field_name")): str(item.get("value", "")) for item in data}
    workload_id = fields.get("Workload Number", "")
    workload_name = fields.get("Workload Name", "")
    if not workload_id or not workload_name:
        return
    initialized_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    manifest = {
        "schema_version": "1.0.0",
        "source_template_commit": "0000000000000000000000000000000000000000",
        "workload_id": workload_id,
        "workload_name": workload_name,
        "generated_at": initialized_at,
        "generation_started_at": initialized_at,
        "generation_finished_at": initialized_at,
        "generation_duration_seconds": 0,
        "generated_by": {"agent": "template initializer"},
        "template_repo": template_root.name,
        "template_copy_path": template_root.name,
        "template_copy_sha256": _tree_digest(template_root),
        "implementation_component_resolution": "automatic",
        "implementation_components_discovered": [str(item["component_id"]) for item in resolved_components],
        "implementation_component_reasons": {
            str(item["component_id"]): [str(reason) for reason in item["reasons"]]
            for item in resolved_components
        },
        "notes": (
            "Initialized from the active nested template copy with automatically discovered implementation components; "
            "final generation timing must be recorded before completion."
        ),
    }
    manifest_path.write_bytes((json.dumps(manifest, indent=2) + "\n").encode("utf-8"))


def main() -> int:
    args = parse_args()
    requested_root = Path(args.template_root).resolve()
    cwd = Path.cwd().resolve()

    if _contains_template_files(requested_root):
        source_root = requested_root
        output_root = requested_root.parent
    elif _contains_template_files(cwd):
        source_root = cwd
        output_root = requested_root
    else:
        raise SystemExit(
            "[FAIL] Could not locate template files. Run this command from the "
            "template directory with --template-root .., or pass --template-root "
            "as the template directory itself."
        )

    if args.repo_root:
        repo_root = Path(args.repo_root).resolve()
    else:
        workload_id = _workload_id(source_root)
        directory_name = generated_repo_directory_name(workload_id, args.repo_name) if workload_id else args.repo_name
        repo_root = (output_root / directory_name).resolve()
    if repo_root == source_root or source_root in repo_root.parents:
        raise SystemExit(
            "[FAIL] Generated repository root must not be inside the active template root; "
            "this would recursively copy the repository."
        )

    active_copy_inside_repo = source_root != repo_root and repo_root in source_root.parents
    if (
        repo_root.exists()
        and any(repo_root.iterdir())
        and not args.force
        and not active_copy_inside_repo
    ):
        raise SystemExit(
            f"[FAIL] Target already exists and is non-empty: {repo_root}. "
            "Use --force to reinitialize."
        )

    if repo_root.exists() and args.force and not active_copy_inside_repo:
        shutil.rmtree(repo_root)
    repo_root.mkdir(parents=True, exist_ok=True)

    for rel in SHARED_FILES:
        src = source_root / rel
        if not src.exists():
            raise SystemExit(f"[FAIL] Missing required template file: {src}")
        copy_path(src, repo_root / SHARED_FILE_DESTINATIONS.get(rel, rel))

    for rel in SHARED_DIRS:
        src = source_root / rel
        if not src.exists():
            raise SystemExit(f"[FAIL] Missing required template directory: {src}")
        copy_path(src, repo_root / rel)
    _retarget_workload_pyproject(repo_root, args.repo_name)
    _install_generated_repo_github_files(source_root, repo_root)

    for rel in OPTIONAL_SOURCE_FILES:
        src = source_root / rel
        if src.exists():
            copy_path(src, repo_root / rel)

    try:
        resolved_components = resolve_components(
            source_root / "benchmark_specification.json",
            source_root / "implementation_components",
        )
    except ValueError as exc:
        raise SystemExit(f"[FAIL] {exc}") from exc
    validate_overlay_conflicts(resolved_components)
    spec_fields = definition_fields(source_root / "benchmark_specification.json")
    spec_errors, spec_warnings = validate_component_vs_spec(spec_fields, resolved_components)
    for warning in spec_warnings:
        print(f"[WARN] {warning}")
    if spec_errors:
        raise SystemExit("[FAIL] " + "; ".join(spec_errors))
    try:
        bundle = _setup_bundle_for(source_root, force_rocm=args.rocm_setup)
    except ValueError as exc:
        raise SystemExit(f"[FAIL] {exc}") from exc
    skeleton = source_root / SKELETON_REL[bundle]
    if not skeleton.exists():
        raise SystemExit(f"[FAIL] Missing setup skeleton for bundle {bundle}: {skeleton}")
    skeleton_target = repo_root / "setup.sh"
    shutil.copy2(skeleton, skeleton_target)
    skeleton_target.chmod(skeleton_target.stat().st_mode | 0o111)
    print(f"[INFO] Materialized {bundle} setup skeleton as setup.sh")

    for resolved in resolved_components:
        component_id = str(resolved["component_id"])
        component_root = Path(resolved["component_root"])
        component = resolved["component"]
        for rel in component["overlay"]:
            source = component_root / "files" / str(rel)
            copy_path(source, repo_root / str(rel))
        reason = "; ".join(str(item) for item in resolved["reasons"])
        print(f"[INFO] Automatically discovered implementation component: {component_id} ({reason})")

    if bundle == "rocm":
        # A workload overlay may not replace the canonical ROCm controller with
        # an empty or minimal setup script.
        shutil.copy2(source_root / SKELETON_REL[bundle], repo_root / "setup.sh")
        (repo_root / "setup.sh").chmod((repo_root / "setup.sh").stat().st_mode | 0o111)
    elif bundle == "cpu-system":
        shutil.copy2(source_root / SKELETON_REL[bundle], repo_root / "setup.sh")
        (repo_root / "setup.sh").chmod((repo_root / "setup.sh").stat().st_mode | 0o111)
    # NVIDIA overlay setup.sh (vLLM / SGLang) must win. Do not recopy the
    # NVIDIA skeleton after overlays. Overlay helpers are invoked by the
    # skeleton when those setup.sh files are not present.

    for rel in COPY_EXCLUSIONS:
        target = repo_root / rel
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()

    for rel in REQUIRED_PATHS:
        path = repo_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if rel == "setup.sh":
            if not path.exists() or path.stat().st_size == 0:
                raise SystemExit("[FAIL] setup.sh was not materialized from a setup skeleton.")
            continue
        if rel == "scripts/build.sh" and (not path.exists() or path.stat().st_size == 0):
            # Workloads without a compile step still get a valid script, so
            # setup.sh can call it and shellcheck/bash -n have something real.
            path.write_text(NO_BUILD_STEP_SH, encoding="utf-8", newline="\n")
            path.chmod(path.stat().st_mode | 0o111)
            continue
        if not path.exists():
            path.touch()
    materialize_generated_harness(repo_root)
    _write_generation_manifest(repo_root, source_root, resolved_components)
    if apply_component_gaps(repo_root, source_root / "implementation_components") != 0:
        raise SystemExit("[FAIL] Component contract validation failed.")
    _stamp_nvcc_glibc_throw(repo_root)

    print(f"[PASS] Initialized generated repo scaffold: {repo_root}")
    print("[INFO] Removed template-only artifacts:")
    for rel in COPY_EXCLUSIONS:
        print(f"  - {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
