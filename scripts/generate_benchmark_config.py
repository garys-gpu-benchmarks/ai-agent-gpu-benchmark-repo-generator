#!/usr/bin/env python3
"""Write config/benchmark_config.yaml sweep values from the Parameters_SmokeBaselineExtend contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from matrix_profile_values import (  # noqa: E402
    DEFINITIONS_SHEET_ALIASES,
    PROFILE_SHEET,
    PROFILE_SHEET_ALIASES,
    default_profile_for_domain,
    definitions_rows,
    load_profile_values,
    profile_values_json,
    resolve_sheet,
    values_to_sweep,
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate benchmark_config.yaml sweep values from Parameters_SmokeBaselineExtend."
    )
    parser.add_argument("--workload", help="Workload number, required with --matrix.")
    parser.add_argument(
        "--matrix",
        type=Path,
        help="BenchmarkSpecDefinitions.xlsx path.",
    )
    parser.add_argument(
        "--benchmark-specification",
        "--benchmark-definition",
        dest="benchmark_definition",
        type=Path,
        help="benchmark_specification.json that already contains Profile Parameter Values.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("config/benchmark_config.yaml"),
        help="Output YAML path.",
    )
    parser.add_argument(
        "--components-root",
        type=Path,
        default=None,
        help="implementation_components root used to detect locked overlay YAML.",
    )
    return parser.parse_args(argv)


def _yaml_is_locked_overlay(args: argparse.Namespace) -> bool:
    output = Path(args.output)
    lock = output.parent.parent / "results" / "overlay_lock.json"
    if lock.is_file():
        try:
            data = json.loads(lock.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if "config/benchmark_config.yaml" in data:
            return True
    spec = getattr(args, "benchmark_definition", None)
    components = getattr(args, "components_root", None)
    if spec and components and Path(spec).is_file() and Path(components).is_dir():
        try:
            from resolve_implementation_components import resolve_components

            resolved = resolve_components(Path(spec), Path(components))
        except Exception:
            return False
        return any(
            "config/benchmark_config.yaml" in (item["component"].get("overlay") or [])
            for item in resolved
        )
    return False


def _from_definition(path: Path) -> tuple[str, list[str], dict, str]:
    entries = json.loads(path.read_text(encoding="utf-8"))
    fields = {item["field_name"]: item.get("value", "") for item in entries}
    workload = str(fields.get("Workload Number", "")).strip()
    parameters = [
        str(fields[name]).strip()
        for name in (f"Parameter_{index:02d}" for index in range(1, 21))
        if fields.get(name) not in ("", None, "—", "-", "--")
    ]
    raw = fields.get("Profile Parameter Values", "")
    if (not raw or raw in ("--", "TBD")) and not parameters:
        # A workload with every Parameter_NN slot "-" (102/202/302/402 since
        # TEMPLATE_00_119) has nothing to sweep; its config gets an empty sweep.
        return workload, parameters, {}, str(fields.get("Execution Domain", "")).strip()
    if not raw or raw in ("--", "TBD"):
        raise SystemExit("[FAIL] benchmark_specification.json has no Profile Parameter Values.")
    values = json.loads(raw)
    domain = str(fields.get("Execution Domain", "")).strip()
    return workload, parameters, values, domain


def _from_matrix(path: Path, workload: str) -> tuple[str, list[str], dict, str]:
    from openpyxl import load_workbook

    workbook = load_workbook(path, data_only=False)
    definitions_sheet = resolve_sheet(workbook, DEFINITIONS_SHEET_ALIASES, "definitions")
    values_sheet = resolve_sheet(workbook, PROFILE_SHEET_ALIASES, "profile")
    definitions = definitions_rows(definitions_sheet)
    number = int(workload)
    if number not in definitions:
        raise SystemExit(f"[FAIL] Workload {workload} is not in {definitions_sheet.title}.")
    parameters = definitions[number]["parameters"]
    values = load_profile_values(values_sheet).get(number, {})
    domain = str(definitions[number].get("execution_domain", "")).strip()
    return workload, parameters, profile_values_json(parameters, values), domain


def _norm_sweep(value):
    """Compare profile tokens without treating 0.1 and '0.1' as different."""
    if isinstance(value, dict):
        return {str(key): _norm_sweep(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_norm_sweep(item) for item in value]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float):
        return format(value, ".12g")
    if isinstance(value, int):
        return str(value)
    text = str(value).strip()
    try:
        return format(float(text), ".12g")
    except ValueError:
        return text


def _sweep_already_matches(existing: dict, sweep: dict) -> bool:
    current = existing.get("sweep")
    if not isinstance(current, dict):
        return False
    for key, value in sweep.items():
        if key not in current or _norm_sweep(current[key]) != _norm_sweep(value):
            return False
    return True


def _refresh_locked_yaml_hash(output: Path) -> None:
    lock_path = output.parent.parent / "results" / "overlay_lock.json"
    if not lock_path.is_file():
        return
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    rel = "config/benchmark_config.yaml"
    meta = data.get(rel)
    if not isinstance(meta, dict):
        return
    meta["sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    data[rel] = meta
    lock_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.benchmark_definition:
        workload, parameters, values, domain = _from_definition(args.benchmark_definition)
    elif args.matrix and args.workload:
        workload, parameters, values, domain = _from_matrix(args.matrix, args.workload)
    else:
        raise SystemExit("[FAIL] Provide --benchmark-specification or --matrix plus --workload.")

    default_profile = default_profile_for_domain(domain)
    sweep = values_to_sweep(parameters, values, default_profile=default_profile)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if _yaml_is_locked_overlay(args) and args.output.is_file():
        existing = yaml.safe_load(args.output.read_text(encoding="utf-8")) or {}
        if not isinstance(existing, dict):
            existing = {}
        if _sweep_already_matches(existing, sweep):
            print(f"Locked overlay sweep already matches profile values; left {args.output} unchanged.")
            return 0
        current_sweep = existing.get("sweep")
        if not isinstance(current_sweep, dict):
            existing["sweep"] = sweep
        else:
            for key, value in sweep.items():
                current_sweep[key] = value
            existing["sweep"] = current_sweep
        header = (
            f"# Merged sweep from Parameters_SmokeBaselineExtend for workload {workload}.\n"
            "# Workbook profile values replace the same keys in a locked overlay.\n"
        )
        body = yaml.safe_dump(existing, sort_keys=False, allow_unicode=True)
        args.output.write_text(header + body, encoding="utf-8", newline="\n")
        _refresh_locked_yaml_hash(args.output)
        print(f"Merged sweep into locked overlay {args.output} for workload {workload}.")
        return 0
    payload = {
        "sweep": sweep,
    }
    header = (
        f"# Generated from BenchmarkSpecDefinitions.xlsx::{PROFILE_SHEET} "
        f"for workload {workload}.\n"
        "# Parameter names come from Parameter_01..Parameter_20. Values come only from Parameters_SmokeBaselineExtend.\n"
        "# Do not invent or replace these tokens/numbers. Nested list/map reshaping is allowed\n"
        "# when the runner needs structured sweeps; keep the same tokens and numbers.\n"
        "# Command columns on Workload_Definitions are generated display. Sweep/list flags in those\n"
        "# commands are documentary; omit them so yaml expands cases.\n"
        "# sweep.profile is baseline for LLM Serving and smoke otherwise.\n"
        "# Add thresholds: or baselines: from hardware_profile.mi300x.yaml and Workload Type.\n"
    )
    body = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    args.output.write_text(header + body, encoding="utf-8", newline="\n")
    print(f"Wrote {args.output} sweep values for workload {workload}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
