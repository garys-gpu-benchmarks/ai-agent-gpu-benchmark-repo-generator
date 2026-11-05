#!/usr/bin/env python3
"""Help lines for run_benchmark.sh workload flags.

Each line is the flag, a short description, and the smoke, baseline, and
extended values. A value shared by all three profiles is printed once.
Profile notes are omitted.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import yaml

from generate_workload_parameters import extract_meaning

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "config" / "workload_parameters.yaml"
HELP_COLUMN = 32
EMPTY = {"", "—", "-", "--", "None", "none", "TBD", "n/a", "N/A"}
PLACEHOLDER_MEANING = "Defined by the workload description"


def _parameters(fields: dict[str, str]) -> list[str]:
    names = []
    for index in range(1, 21):
        value = str(fields.get(f"Parameter_{index:02d}", "") or "").strip()
        if value and value not in EMPTY:
            names.append(value)
    return names


def _flag_of(name: str) -> str:
    return "--" + name.replace("_", "-")


def _profile_values(fields: dict[str, str]) -> dict:
    raw = fields.get("Profile Parameter Values", "")
    if not raw or raw in EMPTY:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _profile_triple(values: dict, name: str) -> tuple[str, str, str]:
    smoke = baseline = extended = ""
    if all(key in values for key in ("smoke", "baseline", "extended")) and isinstance(values.get("smoke"), dict):
        smoke = values["smoke"].get(name, "")
        baseline = values["baseline"].get(name, "")
        extended = values["extended"].get(name, "")
    elif isinstance(values.get(name), dict):
        item = values[name]
        smoke = item.get("smoke", "")
        baseline = item.get("baseline", "")
        extended = item.get("extended", "")
    return smoke, baseline, extended


def _display(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, list):
        return ",".join(item for item in (_display(part) for part in value) if item)
    text = str(value).strip()
    return "" if text in EMPTY else text


def _profile_phrase(smoke, baseline, extended) -> str:
    parts = (
        ("smoke", _display(smoke)),
        ("baseline", _display(baseline)),
        ("extended", _display(extended)),
    )
    present = [(label, value) for label, value in parts if value]
    if not present:
        return ""
    if len(present) == 3 and present[0][1] == present[1][1] == present[2][1]:
        return f"smoke/baseline/extended: {present[0][1]}"
    return ", ".join(f"{label} {value}" for label, value in present)


@lru_cache(maxsize=1)
def _catalog() -> dict:
    if not CATALOG_PATH.is_file():
        return {}
    loaded = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8")) or {}
    parameters = loaded.get("parameters") if isinstance(loaded, dict) else {}
    return parameters if isinstance(parameters, dict) else {}


def _placeholder(data_type: str) -> str:
    kind = (data_type or "").strip().lower()
    if kind in {"integer", "number"}:
        return "<n>"
    if kind == "boolean":
        return "<true|false>"
    return "<value>"


def _description(name: str, execution: str) -> tuple[str, str]:
    entry = _catalog().get(name) or {}
    description = str(entry.get("description") or "").strip().rstrip(".")
    meaning = extract_meaning(execution, name).strip().rstrip(".")
    if description:
        text = description
    elif meaning and meaning != PLACEHOLDER_MEANING:
        text = meaning
    else:
        text = name.replace("_", " ")
    return text, _placeholder(str(entry.get("data_type") or ""))


def _line(flag: str, placeholder: str, description: str, phrase: str) -> str:
    left = f"  {flag} {placeholder}"
    gap = "  " if len(left) >= HELP_COLUMN else " " * (HELP_COLUMN - len(left))
    detail = f"{description} ({phrase})" if phrase else description
    return f"{left}{gap}{detail}"


def option_help_lines(fields: dict[str, str]) -> list[str]:
    """One help line per Parameter_01..Parameter_20."""
    values = _profile_values(fields)
    execution = str(fields.get("Execution Description With Parameters", "") or "")
    lines = []
    for name in _parameters(fields):
        description, placeholder = _description(name, execution)
        phrase = _profile_phrase(*_profile_triple(values, name))
        lines.append(_line(_flag_of(name), placeholder, description, phrase))
    return lines


def replace_workload_options(text: str, lines: list[str]) -> str:
    """Replace the usage() Workload options block. Leave runners without that section unchanged."""
    if "Workload options:\n" not in text:
        return text
    body = "\n".join(lines) if lines else "  (none)"
    block = f"Workload options:\n{body}\n"
    return re.sub(r"Workload options:\n(?:[ \t].*\n)*", block, text, count=1)
