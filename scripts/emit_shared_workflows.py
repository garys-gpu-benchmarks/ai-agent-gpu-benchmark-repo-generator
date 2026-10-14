#!/usr/bin/env python3
# File: scripts/emit_shared_workflows.py
# Version: 1.0.0
# Maintainer: AI Agent GPU Benchmark Repo Generator
# Date: 2026-10-08
# Description: Emit the two persistent, suite-level repositories from their
#   templates and config/ci_contract.yaml:
#     <output-root>/shared-workflows/   reusable GitHub workflows (published once, tagged)
#     <output-root>/gpu-bench-suite/    operator scripts (run_benchmark_suite.sh, get_remote_info.sh, show_metrics.sh)
#   publish_benchmarks_to_github.sh runs this with --output-root set to the
#   publish folder that holds the run folder (Publishing/Publish_<YYYYMMDD>_<NN>).
# Execution: python3 scripts/emit_shared_workflows.py --output-root <DIR> [--update] [--check]
# Requirements: Python 3.10+, PyYAML
# License: Apache-2.0
#
# Ownership rule: files that come from the templates are overwritten on
# --update; .git/ and anything else in the target are left alone. Tags and
# commits are never created here (see templates/shared-workflows/README.md).

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
import tempfile
from pathlib import Path

from ci_contract import (
    SHARED_WORKFLOWS_REL,
    SUITE_TOOLS_REL,
    TEMPLATE_ROOT,
    WORKLOAD_WORKFLOWS_REL,
    ContractError,
    load_contract,
    render_tree,
    shared_placeholders,
    workload_identity,
    workload_placeholders,
)

FIXTURE_REL = Path("tests") / "fixtures" / "sample-workload"


def _ruff_only_pyproject(template_root: Path) -> str:
    text = (template_root / "config" / "pyproject.toml").read_text(encoding="utf-8")
    keep: list[str] = []
    in_ruff = False
    for line in text.splitlines():
        if line.startswith("["):
            in_ruff = line.startswith("[tool.ruff")
        if in_ruff:
            keep.append(line)
    if not keep:
        raise ContractError("config/pyproject.toml has no [tool.ruff] section")
    return "# Lint configuration only (same rules as the generated workloads).\n" + "\n".join(keep).strip() + "\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _copy_lf(src: Path, dst: Path) -> None:
    _write(dst, src.read_text(encoding="utf-8").replace("\r\n", "\n"))


def build_shared_workflows(template_root: Path, contract: dict, dest: Path) -> None:
    render_tree(template_root / SHARED_WORKFLOWS_REL, dest, shared_placeholders(contract))
    _copy_lf(template_root / "LICENSE", dest / "LICENSE")

    fixture = dest / FIXTURE_REL
    _copy_lf(template_root / "LICENSE", fixture / "LICENSE")
    _copy_lf(template_root / "legal" / "NOTICE", fixture / "legal" / "NOTICE")
    _copy_lf(
        template_root / "schemas" / "benchmark_specification.schema.json",
        fixture / "schemas" / "benchmark_specification.schema.json",
    )
    _write(fixture / "config" / "pyproject.toml", _ruff_only_pyproject(template_root))
    fields = {"Workload Number": "900", "Repo Name": "sys-bench-amd-sample-workload-ubu2404", "GPU Vendor": "AMD"}
    identity = workload_identity(fields, contract)
    render_tree(
        template_root / WORKLOAD_WORKFLOWS_REL,
        fixture / ".github" / "workflows",
        workload_placeholders(contract, identity),
    )


def build_suite_tools(template_root: Path, contract: dict, dest: Path) -> None:
    render_tree(template_root / SUITE_TOOLS_REL, dest, shared_placeholders(contract))
    _copy_lf(template_root / "LICENSE", dest / "LICENSE")


def sync(staged: Path, target: Path, apply: bool) -> list[str]:
    """Copy staged files over target. Returns a change list ('A path', 'M path')."""
    changes: list[str] = []
    for src in sorted(path for path in staged.rglob("*") if path.is_file()):
        rel = src.relative_to(staged)
        dst = target / rel
        if not dst.exists():
            changes.append(f"A {rel.as_posix()}")
        elif not filecmp.cmp(src, dst, shallow=False):
            changes.append(f"M {rel.as_posix()}")
        else:
            continue
        if apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    if target.is_dir():
        staged_files = {path.relative_to(staged) for path in staged.rglob("*") if path.is_file()}
        for path in sorted(target.rglob("*")):
            rel = path.relative_to(target)
            if path.is_file() and ".git" not in rel.parts and rel not in staged_files:
                changes.append(f"? {rel.as_posix()} (not from the template; left in place)")
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit shared-workflows and gpu-bench-suite from templates")
    parser.add_argument("--output-root", required=True,
                        help="Folder that holds shared-workflows/ and gpu-bench-suite/ (e.g. Publishing/Publish_20261009_01)")
    parser.add_argument("--template-root", default="", help="Generator root (default: this checkout)")
    parser.add_argument("--only", choices=("shared-workflows", "suite-tools", "both"), default="both")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--update", action="store_true",
                      help="Write into existing folders (keeps .git and non-template files)")
    mode.add_argument("--check", action="store_true",
                      help="Report what would change and exit 1 if anything differs; write nothing")
    args = parser.parse_args()

    template_root = Path(args.template_root).resolve() if args.template_root else TEMPLATE_ROOT
    output_root = Path(args.output_root).resolve()
    if (output_root / "AGENTS.md").is_file() or output_root == template_root:
        raise SystemExit("[FAIL] --output-root must be outside the generator (for example Publishing/Publish_20261009_01)")
    try:
        contract = load_contract(template_root)
    except ContractError as exc:
        raise SystemExit(f"[FAIL] {exc}") from exc

    targets = []
    if args.only in ("shared-workflows", "both"):
        targets.append((str(contract["shared_workflows"]["repo"]), build_shared_workflows))
    if args.only in ("suite-tools", "both"):
        targets.append((str(contract["suite"]["tools_repo"]), build_suite_tools))

    drift = False
    with tempfile.TemporaryDirectory() as tmp:
        for name, builder in targets:
            staged = Path(tmp) / name
            try:
                builder(template_root, contract, staged)
            except ContractError as exc:
                raise SystemExit(f"[FAIL] {name}: {exc}") from exc
            target = output_root / name
            if target.exists() and any(target.iterdir()) and not (args.update or args.check):
                raise SystemExit(
                    f"[FAIL] {target} already exists. Re-run with --update to refresh template-owned files "
                    "(its .git history and tags are kept), or --check to preview."
                )
            changes = sync(staged, target, apply=not args.check)
            real = [change for change in changes if not change.startswith("?")]
            drift = drift or bool(real)
            verb = "would change" if args.check else "updated"
            print(f"[INFO] {name}: {len(real)} file(s) {verb} in {target}")
            for change in changes:
                print(f"  {change}")
    if args.check:
        print("[FAIL] output differs from the templates" if drift else "[PASS] output matches the templates")
        return 1 if drift else 0
    print("[PASS] emitted. Next: review, commit, push, wait for the Self-test, then tag "
          f"(see {contract['shared_workflows']['repo']}/README.md, 'Releasing a change').")
    return 0


if __name__ == "__main__":
    sys.exit(main())
