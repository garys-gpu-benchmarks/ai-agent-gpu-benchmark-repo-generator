#!/usr/bin/env python3
# File: scripts/ci_contract.py
# Version: 1.0.0
# Maintainer: AI Agent GPU Benchmark Repo Generator
# Date: 2026-10-08
# Description: Load config/ci_contract.yaml, derive a workload's CI identity
#   (vendor, OS label, GitHub slug, suite bundle), and render the workflow
#   templates under templates/ by replacing __PLACEHOLDER__ tokens.
# Execution: imported by init_generated_repo.py, fill_generated_docs.py and
#   emit_shared_workflows.py; `python3 scripts/ci_contract.py --show` prints
#   the resolved contract, `--check-callers REPO_ROOT` validates a generated
#   repo's caller workflows against the contract.
# Requirements: Python 3.10+, PyYAML
# License: Apache-2.0
#
# Placeholders use __NAME__ rather than {{ }} because GitHub Actions already
# uses ${{ }} for its own expressions; a {{ }} template engine would rewrite
# those too.
#
# Generation-only: this module is not copied into generated workload repos.

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

from generated_repo_directory import generated_repo_directory_name

TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_REL = Path("config") / "ci_contract.yaml"
WORKLOAD_WORKFLOWS_REL = Path("templates") / "workload" / ".github" / "workflows"
SHARED_WORKFLOWS_REL = Path("templates") / "shared-workflows"
SUITE_TOOLS_REL = Path("templates") / "suite-tools"
# Master copies of the operator scripts, in one place at the generator root.
# Generation never copies this folder into a workload (init_generated_repo.py
# SHARED_DIRS). The suite tools below are emitted to gpu-bench-suite/scripts/.
USER_SCRIPTS_REL = Path("user_scripts")
SUITE_TOOL_SCRIPTS = (
    "run_benchmark_suite.sh",
    "show_metrics.sh",
    "show_ledger_runs.sh",
    "get_benchmark_results.sh",
)

PLACEHOLDER_RE = re.compile(r"__[A-Z][A-Z0-9_]*__")
OS_LABEL_RE = re.compile(r"ubu(\d{2})(\d{2})$")


class ContractError(ValueError):
    """Raised when the contract or a workload's identity is inconsistent."""


def load_contract(template_root: Path | None = None) -> dict:
    root = Path(template_root) if template_root else TEMPLATE_ROOT
    path = root / CONTRACT_REL
    if not path.is_file():
        raise ContractError(f"missing CI contract: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for key in ("github", "shared_workflows", "inputs", "runners", "defaults", "tools", "suite"):
        if key not in data:
            raise ContractError(f"{path}: missing top-level key '{key}'")
    if not str(data["github"].get("owner") or "").strip():
        raise ContractError(f"{path}: github.owner is empty")
    if not re.fullmatch(r"v\d+", str(data["shared_workflows"].get("ref") or "")):
        raise ContractError(f"{path}: shared_workflows.ref must be a major tag such as v1")
    return data


def _choices(contract: dict, name: str) -> list[str]:
    values = [str(item) for item in contract["inputs"].get(name) or []]
    if not values:
        raise ContractError(f"ci_contract inputs.{name} is empty")
    return values


def os_label_display(os_label: str) -> str:
    """ubu2404 -> Ubuntu 24.04"""
    match = OS_LABEL_RE.fullmatch(os_label)
    return f"Ubuntu {match.group(1)}.{match.group(2)}" if match else os_label


def workload_identity(fields: dict[str, str], contract: dict) -> dict[str, str]:
    """Derive the CI identity of one workload from benchmark_specification.json fields."""
    workload = str(fields.get("Workload Number", "")).strip()
    repo_name = str(fields.get("Repo Base Name") or fields.get("Repo Name", "")).strip()
    repo_name = re.sub(r"\s*\[[^\]]*\]\s*$", "", repo_name)  # strip " [Remote_SSH]" style tags
    if not workload or not repo_name:
        raise ContractError("benchmark_specification.json lacks Workload Number or Repo Base Name")

    vendor = str(fields.get("GPU Vendor", "")).strip().lower()
    if vendor not in _choices(contract, "vendor"):
        for candidate in _choices(contract, "vendor"):
            if f"-{candidate}-" in f"-{repo_name}-":
                vendor = candidate
                break
    if vendor not in _choices(contract, "vendor"):
        raise ContractError(
            f"workload {workload}: cannot map GPU Vendor {fields.get('GPU Vendor')!r} "
            f"to one of {_choices(contract, 'vendor')}"
        )

    os_label = ""
    suffix = repo_name.rsplit("-", 1)[-1]
    if OS_LABEL_RE.fullmatch(suffix):
        os_label = suffix
    else:
        match = re.search(r"(\d{2})\.(\d{2})", str(fields.get("OS Version", "")))
        if match:
            os_label = f"ubu{match.group(1)}{match.group(2)}"
    if os_label not in _choices(contract, "os_label"):
        raise ContractError(
            f"workload {workload}: cannot derive an OS label from Repo Base Name {repo_name!r} "
            f"or OS Version {fields.get('OS Version')!r}; expected one of {_choices(contract, 'os_label')}"
        )

    bundle_key = f"{vendor}-{os_label}"
    bundle = str((contract["suite"].get("bundles") or {}).get(bundle_key, "")).strip()
    if not bundle:
        raise ContractError(f"ci_contract suite.bundles has no entry for {bundle_key}")

    return {
        "workload": workload,
        "repo_name": repo_name,
        "slug": generated_repo_directory_name(workload, repo_name),
        "vendor": vendor,
        "os_label": os_label,
        "os_display": os_label_display(os_label),
        "bundle": bundle,
    }


def shared_placeholders(contract: dict) -> dict[str, str]:
    """Values used by the shared-workflows and suite-tools templates."""
    shared = contract["shared_workflows"]
    defaults = contract["defaults"]
    tools = contract["tools"]
    profiles = _choices(contract, "gpu_profile")
    return {
        "__CI_OWNER__": str(contract["github"]["owner"]),
        "__CI_SHARED_REPO__": str(shared["repo"]),
        "__CI_REF__": str(shared["ref"]),
        "__CI_WORKFLOW__": str(shared["workflows"]["ci"]),
        "__GPU_WORKFLOW__": str(shared["workflows"]["gpu"]),
        "__HOSTED_RUNNER__": str(contract["runners"]["hosted"]),
        "__PYTHON_VERSION__": str(defaults["python_version"]),
        "__CI_TIMEOUT__": str(defaults["ci_timeout_minutes"]),
        "__GPU_TIMEOUT__": str(defaults["gpu_timeout_minutes"]),
        "__RETENTION_DAYS__": str(defaults["artifact_retention_days"]),
        "__RUFF_VERSION__": str(tools["ruff"]),
        "__ACTIONLINT_VERSION__": str(tools["actionlint"]),
        "__VENDOR_CHOICES__": " ".join(_choices(contract, "vendor")),
        "__OS_LABEL_CHOICES__": " ".join(_choices(contract, "os_label")),
        "__PROFILE_CHOICES__": " ".join(profiles),
        "__PROFILE_OPTIONS__": "[" + ", ".join(profiles) + "]",
        "__PROFILE_DEFAULT__": profiles[0],
        "__SUITE_INSTALL_ROOT__": str(contract["suite"]["install_root"]),
        "__SUITE_TOOLS_REPO__": str(contract["suite"]["tools_repo"]),
        "__ACTIONLINT_LABELS__": "\n".join(
            f"    - {label}"
            for label in ["gpu", *_choices(contract, "vendor"), *_choices(contract, "os_label")]
        ),
    }


def workload_placeholders(contract: dict, identity: dict[str, str]) -> dict[str, str]:
    values = shared_placeholders(contract)
    values.update(
        {
            "__VENDOR__": identity["vendor"],
            "__OS_LABEL__": identity["os_label"],
            "__REPO_SLUG__": identity["slug"],
            "__BUNDLE_REPO__": identity["bundle"],
        }
    )
    return values


def render_text(text: str, values: dict[str, str], source: str = "<text>") -> str:
    for token, value in values.items():
        text = text.replace(token, value)
    leftovers = sorted(set(PLACEHOLDER_RE.findall(text)))
    if leftovers:
        raise ContractError(f"{source}: unresolved placeholders {leftovers}")
    return text


def render_file(src: Path, dst: Path, values: dict[str, str]) -> None:
    text = src.read_text(encoding="utf-8").replace("\r\n", "\n")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(render_text(text, values, str(src)), encoding="utf-8", newline="\n")
    if src.suffix == ".sh":
        dst.chmod(dst.stat().st_mode | 0o111)


def render_tree(src_root: Path, dst_root: Path, values: dict[str, str]) -> list[Path]:
    """Render every file under src_root into dst_root; return the written paths."""
    written: list[Path] = []
    for src in sorted(path for path in src_root.rglob("*") if path.is_file()):
        if "__pycache__" in src.parts:
            continue
        dst = dst_root / src.relative_to(src_root)
        render_file(src, dst, values)
        written.append(dst)
    return written


def render_workload_callers(
    repo_root: Path,
    fields: dict[str, str],
    template_root: Path | None = None,
) -> dict[str, str]:
    """Write the thin caller workflows into repo_root/.github/workflows."""
    root = Path(template_root) if template_root else TEMPLATE_ROOT
    contract = load_contract(root)
    identity = workload_identity(fields, contract)
    values = workload_placeholders(contract, identity)
    src_dir = root / WORKLOAD_WORKFLOWS_REL
    if not src_dir.is_dir():
        raise ContractError(f"missing caller templates: {src_dir}")
    dest_dir = Path(repo_root) / ".github" / "workflows"
    dest_dir.mkdir(parents=True, exist_ok=True)
    for stale in ("nightly.yml",):
        (dest_dir / stale).unlink(missing_ok=True)
    render_tree(src_dir, dest_dir, values)
    errors = check_callers(Path(repo_root), contract, identity)
    if errors:
        raise ContractError("; ".join(errors))
    return identity


def expected_uses(contract: dict, key: str) -> str:
    shared = contract["shared_workflows"]
    return (
        f"{contract['github']['owner']}/{shared['repo']}/.github/workflows/"
        f"{shared['workflows'][key]}@{shared['ref']}"
    )


def check_callers(repo_root: Path, contract: dict, identity: dict[str, str] | None = None) -> list[str]:
    """Return contract violations for a generated repo's caller workflows."""
    errors: list[str] = []
    wf_dir = Path(repo_root) / ".github" / "workflows"
    ci_name = contract["shared_workflows"]["workflows"]["ci"]
    gpu_name = contract["shared_workflows"]["workflows"]["gpu"]
    present = sorted(path.name for path in wf_dir.glob("*.y*ml")) if wf_dir.is_dir() else []
    if present != sorted([ci_name, gpu_name]):
        errors.append(f".github/workflows must hold exactly {ci_name} and {gpu_name}; found {present}")
    for key, name in (("ci", ci_name), ("gpu", gpu_name)):
        path = wf_dir / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        try:
            doc = yaml.safe_load(text) or {}
        except yaml.YAMLError as exc:
            errors.append(f"{name}: invalid YAML ({exc})")
            continue
        jobs = doc.get("jobs") or {}
        uses = [str(job.get("uses", "")) for job in jobs.values() if isinstance(job, dict)]
        if uses != [expected_uses(contract, key)]:
            errors.append(f"{name}: expected one job using {expected_uses(contract, key)}; found {uses}")
        if "permissions" not in doc:
            errors.append(f"{name}: missing top-level permissions block")
        if PLACEHOLDER_RE.search(text):
            errors.append(f"{name}: unresolved placeholders")
        triggers = doc.get(True, doc.get("on")) or {}  # PyYAML reads the key `on` as True
        if key == "gpu" and isinstance(triggers, dict) and (
            "pull_request" in triggers or "pull_request_target" in triggers
        ):
            errors.append(f"{name}: GPU workflow must never trigger on pull requests")
        if identity:
            for job in jobs.values():
                inputs = (job or {}).get("with") or {}
                if str(inputs.get("vendor")) != identity["vendor"]:
                    errors.append(f"{name}: vendor input is {inputs.get('vendor')!r}, expected {identity['vendor']!r}")
                if str(inputs.get("os_label")) != identity["os_label"]:
                    errors.append(
                        f"{name}: os_label input is {inputs.get('os_label')!r}, expected {identity['os_label']!r}"
                    )
    return errors


def _load_fields(spec_path: Path) -> dict[str, str]:
    data = json.loads(spec_path.read_text(encoding="utf-8"))
    return {
        str(item.get("field_name", "")): str(item.get("value", "") or "")
        for item in data
        if isinstance(item, dict)
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect or validate the CI contract")
    parser.add_argument("--template-root", default="", help="Generator root (default: this checkout)")
    parser.add_argument("--show", action="store_true", help="Print the resolved shared placeholders")
    parser.add_argument("--check-callers", default="", metavar="REPO_ROOT",
                        help="Validate a generated repo's caller workflows against the contract")
    args = parser.parse_args()
    root = Path(args.template_root).resolve() if args.template_root else TEMPLATE_ROOT
    try:
        contract = load_contract(root)
        if args.show:
            print(json.dumps(shared_placeholders(contract), indent=2))
        if args.check_callers:
            repo = Path(args.check_callers).resolve()
            identity = workload_identity(_load_fields(repo / "benchmark_specification.json"), contract)
            errors = check_callers(repo, contract, identity)
            for error in errors:
                print(f"[FAIL] {error}", file=sys.stderr)
            if errors:
                return 1
            print(f"[PASS] caller workflows match the CI contract ({identity['slug']})")
    except ContractError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
