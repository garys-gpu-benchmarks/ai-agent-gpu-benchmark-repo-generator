#!/usr/bin/env python3
"""Shared helpers for the Parameters_SmokeBaselineExtend sheet and derived run_benchmark commands."""

from __future__ import annotations

from typing import Any

PROFILE_SHEET = "Parameters_SmokeBaselineExtend"
DEFINITIONS_SHEET = "Workload_Definitions"
PROFILE_SHEET_ALIASES = (PROFILE_SHEET, "ProfileValues")
DEFINITIONS_SHEET_ALIASES = (DEFINITIONS_SHEET, "Sheet4", "Sheet1")


def resolve_sheet(workbook, names: tuple[str, ...], kind: str):
    for name in names:
        if name in workbook.sheetnames:
            return workbook[name]
    raise SystemExit(
        f"[FAIL] Workbook is missing the {kind} sheet ({names[0]}). "
        f"Found: {', '.join(workbook.sheetnames)}"
    )
PROFILES = ("smoke", "baseline", "extended")
PROFILE_HEADERS = {
    "Workload Number": 1,
    "Workload Name": 2,
    "Parameter": 3,
    "smoke": 4,
    "baseline": 5,
    "extended": 6,
    "notes": 7,
}
COMMAND_COLUMNS = {
    "smoke": "run_benchmark Command Plus Options for Smoke Run (One minute or less)",
    "baseline": "run_benchmark Command Plus Options for Baseline Run (3 to 5 minutes)",
    "extended": "run_benchmark Command Plus Options for Extended Run (8 to 15 minutes)",
}


def header_map(worksheet) -> dict[str, int]:
    return {
        str(worksheet.cell(1, column).value).strip(): column
        for column in range(1, worksheet.max_column + 1)
        if worksheet.cell(1, column).value not in (None, "")
    }


def parameter_names(definitions_sheet, row: int) -> list[str]:
    headers = header_map(definitions_sheet)
    names: list[str] = []
    for name, column in headers.items():
        if not name.startswith("Parameter_"):
            continue
        value = definitions_sheet.cell(row, column).value
        if value in (None, "", "—", "-"):
            continue
        names.append(str(value).strip())
    return names


def definitions_rows(definitions_sheet) -> dict[int, dict[str, Any]]:
    headers = header_map(definitions_sheet)
    number_col = headers["Workload Number"]
    name_col = headers["Workload Name"]
    rows: dict[int, dict[str, Any]] = {}
    for row in range(2, definitions_sheet.max_row + 1):
        raw = definitions_sheet.cell(row, number_col).value
        if raw in (None, ""):
            continue
        try:
            workload = int(raw)
        except (TypeError, ValueError):
            # Repeated header rows (101-132 block then 201-232 block) are not workloads.
            continue
        domain_col = headers.get("Execution Domain")
        rows[workload] = {
            "row": row,
            "name": str(definitions_sheet.cell(row, name_col).value or "").strip(),
            "execution_domain": (
                str(definitions_sheet.cell(row, domain_col).value or "").strip()
                if domain_col
                else ""
            ),
            "parameters": parameter_names(definitions_sheet, row),
        }
    return rows


def load_profile_values(values_sheet) -> dict[int, dict[str, dict[str, str]]]:
    if values_sheet.max_row < 2:
        return {}
    headers = header_map(values_sheet)
    required = ("Workload Number", "Parameter", "smoke", "baseline", "extended")
    missing = [name for name in required if name not in headers]
    if missing:
        raise SystemExit(f"[FAIL] {PROFILE_SHEET} missing columns: {', '.join(missing)}")
    notes_col = headers.get("notes")
    out: dict[int, dict[str, dict[str, str]]] = {}
    for row in range(2, values_sheet.max_row + 1):
        raw = values_sheet.cell(row, headers["Workload Number"]).value
        param = values_sheet.cell(row, headers["Parameter"]).value
        if raw in (None, "") or param in (None, ""):
            continue
        workload = int(raw)
        item = {
            "smoke": _cell_text(values_sheet.cell(row, headers["smoke"]).value),
            "baseline": _cell_text(values_sheet.cell(row, headers["baseline"]).value),
            "extended": _cell_text(values_sheet.cell(row, headers["extended"]).value),
            "notes": _cell_text(values_sheet.cell(row, notes_col).value) if notes_col else "",
        }
        out.setdefault(workload, {})[str(param).strip()] = item
    return out


def _cell_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value).strip()


def needs_quote(text: str) -> bool:
    return any(char in text for char in " \t'\"$&()|<>")


def is_sweep_value(text: str) -> bool:
    return ("," in text or ";" in text) and not text.replace(".", "", 1).lstrip("-").isdigit()


def build_command(profile: str, parameters: list[str], values: dict[str, dict[str, str]]) -> str:
    if profile not in PROFILES:
        raise ValueError(profile)
    parts = ["bash run_benchmark.sh", f"--{profile}"]
    missing: list[str] = []
    for parameter in parameters:
        value = (values.get(parameter) or {}).get(profile, "")
        if value == "":
            missing.append(parameter)
            continue
        flag = "--" + parameter.replace("_", "-")
        if needs_quote(value):
            parts.append(f'{flag} "{value}"')
        else:
            parts.append(f"{flag} {value}")
    if missing:
        raise SystemExit(
            f"[FAIL] {PROFILE_SHEET} missing {profile} values for: {', '.join(missing)}"
        )
    return " ".join(parts)


def coerce_scalar(text: str) -> Any:
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if text.lstrip("-").isdigit():
        return int(text)
    # Keep 0.9 as a float so yaml dumps `gpu_memory_utilization: 0.9`
    # instead of `'0.9'`, which later becomes float("'0.9'") in vLLM CLI.
    if text.count(".") == 1 and text.replace(".", "", 1).lstrip("-").isdigit():
        return float(text)
    return text


def values_to_sweep(
    parameters: list[str],
    values: dict[str, dict[str, str]],
) -> dict[str, Any]:
    sweep: dict[str, Any] = {}
    for parameter in parameters:
        item = values.get(parameter)
        if not item:
            raise SystemExit(f"[FAIL] {PROFILE_SHEET} missing parameter {parameter}")
        profile_map = {profile: item.get(profile, "") for profile in PROFILES}
        if any(value == "" for value in profile_map.values()):
            raise SystemExit(f"[FAIL] {PROFILE_SHEET} has an empty profile value for {parameter}")
        unique = set(profile_map.values())
        if len(unique) == 1:
            sweep[parameter] = coerce_scalar(next(iter(unique)))
        else:
            sweep[parameter] = {profile: coerce_scalar(value) for profile, value in profile_map.items()}
    return sweep


def profile_values_json(parameters: list[str], values: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    payload: dict[str, dict[str, str]] = {}
    for parameter in parameters:
        item = values.get(parameter)
        if not item:
            raise SystemExit(f"[FAIL] {PROFILE_SHEET} missing parameter {parameter}")
        payload[parameter] = {
            "smoke": item.get("smoke", ""),
            "baseline": item.get("baseline", ""),
            "extended": item.get("extended", ""),
            "notes": item.get("notes", ""),
        }
    return payload
