#!/usr/bin/env python3
"""Append one normalized workload-run row to /var/opt/benchmarks/runtime_ledger.csv."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import shlex
import socket
import subprocess
from pathlib import Path
from typing import Any


PARAMETER_SLOT_COUNT = 20
METRIC_SLOT_COUNT = 7
_EMPTY_PARAM_NAMES = {"", "—", "-", "–", "\ufffd", "\u2014", "\u2013"}
_NON_PARAM_FLAGS = {
    "smoke",
    "baseline",
    "extended",
    "validate",
    "help",
    "matrix_definition",
    "profile",
    "log_level",
}


def parameter_slot_column_names() -> list[str]:
    columns: list[str] = []
    for index in range(1, PARAMETER_SLOT_COUNT + 1):
        columns.append(f"Parameter_{index:02d}_Name")
        columns.append(f"Parameter_{index:02d}_Value")
    return columns


def metric_slot_column_names() -> list[str]:
    columns: list[str] = []
    for index in range(1, METRIC_SLOT_COUNT + 1):
        columns.append(f"metric_{index}_def")
        columns.append(f"metric_{index}_result")
    return columns


LEDGER_COLUMNS = [
    "table_index_number",
    "run_id",
    "workload_number",
    "runtime_root_dir",
    "benchmark_profile",
    "start_datetime",
    "total_runtime_mm_ss",
    "exit_code",
    "failure_stage",
    "failure_detail",
    "raw_run_dir",
    "hostname",
    "gpu_name",
    "gpu_vram",
    "gpu_count",
    "os_version",
    "cpu_model",
    "workload_name",
    *metric_slot_column_names(),
    "run_benchmark_command_submitted",
    "run_benchmark_command_fully_resolved",
    *parameter_slot_column_names(),
    "parameters_set",
    "notes",
    "metrics_na_count",
    "result_status",
    "gpu_model_note",
]

FAILURE_STAGES = (
    "ok",
    "setup",
    "collection",
    "parse",
    "validation",
    "timeout",
    "integrity",
    "other",
)

_SMI_NOISE_MARKERS = (
    "rocm system management interface",
    "end of rocm smi log",
    "product info",
    "memory usage (bytes)",
)


def command_output(command: str) -> str:
    try:
        result = subprocess.run(
            ["bash", "-o", "pipefail", "-c", command],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return (result.stdout or "").strip()


def first_nonempty(*values: str) -> str:
    return next((value.strip() for value in values if value and value.strip()), "")


def is_smi_noise_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    compact = stripped.replace(" ", "")
    if compact and set(compact) <= {"=", "-"}:
        return True
    lower = stripped.lower()
    return any(marker in lower for marker in _SMI_NOISE_MARKERS)


def _leading_label_value(line: str, label: str) -> str:
    """Value for a label that starts the line. Avoids SIZE matching CACHE_SIZE."""
    match = re.match(rf"\s*{re.escape(label)}\s*:\s*(.+)$", line, flags=re.IGNORECASE)
    if not match:
        return ""
    return match.group(1).strip()


def labeled_value(line: str, label: str) -> str:
    match = re.search(rf"{re.escape(label)}\s*:\s*(.+)$", line, flags=re.IGNORECASE)
    if not match:
        return ""
    return match.group(1).strip()


def parse_gpu_name_text(
    *, nvidia: str = "", rocm_product: str = "", amd_smi: str = ""
) -> str:
    for line in nvidia.splitlines():
        text = line.strip()
        if text:
            return text
    for label in ("Card Series", "Card SKU"):
        for line in rocm_product.splitlines():
            if is_smi_noise_line(line):
                continue
            value = labeled_value(line, label)
            if value:
                return value
    for label in ("MARKET_NAME", "Marketing Name"):
        for line in amd_smi.splitlines():
            if is_smi_noise_line(line):
                continue
            value = labeled_value(line, label)
            if value:
                return value
    return ""


def parse_gpu_vram_text(*, nvidia: str = "", rocm_mem: str = "", amd_smi: str = "") -> str:
    for line in nvidia.splitlines():
        text = line.strip()
        if text:
            return text
    for line in rocm_mem.splitlines():
        if is_smi_noise_line(line):
            continue
        lower = line.lower()
        if "vram total memory" not in lower or "used" in lower:
            continue
        value = labeled_value(line, "VRAM Total Memory (B)") or labeled_value(
            line, "VRAM Total Memory"
        )
        if value:
            return value
        if ":" in line:
            return line.rsplit(":", 1)[-1].strip()
    section = ""
    for line in amd_smi.splitlines():
        if is_smi_noise_line(line):
            continue
        stripped = line.strip()
        header = stripped[:-1].strip().lower() if stripped.endswith(":") and " " not in stripped[:-1].strip() else ""
        if header:
            section = header
        for label in ("VRAM_TOTAL", "VRAM Total Memory (B)", "VRAM Total Memory", "VRAM Total", "TOTAL_VRAM"):
            value = _leading_label_value(line, label)
            if value and "used" not in line.lower():
                return value
        if section in {"vram", "mem_usage", "memory"}:
            value = _leading_label_value(line, "SIZE") or _leading_label_value(line, "TOTAL")
            if value and "used" not in line.lower():
                return value
    return ""


def amd_gpu_count(text: str) -> str:
    """Count `GPU: <id>` blocks from amd-smi static or amd-smi list."""
    ids = []
    for line in text.splitlines():
        match = re.match(r"\s*GPU:\s*(\d+)\s*$", line)
        if match:
            ids.append(match.group(1))
    if not ids:
        return ""
    return str(len(set(ids)))


def os_version() -> str:
    values: dict[str, str] = {}
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator:
                values[key] = value.strip().strip('"')
    except OSError:
        pass
    return values.get("PRETTY_NAME", "")


def cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[-1].strip()
    except OSError:
        pass
    return ""


def gpu_name() -> str:
    return parse_gpu_name_text(
        nvidia=command_output(
            "nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null"
        ),
        rocm_product="",  # ROCm 10.x has no rocm-smi; amd-smi static is the source.
        amd_smi=command_output("amd-smi static 2>/dev/null"),
    )


def gpu_vram() -> str:
    return parse_gpu_vram_text(
        nvidia=command_output(
            "nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null"
        ),
        rocm_mem="",  # ROCm 10.x has no rocm-smi; amd-smi is the source.
        amd_smi=command_output("amd-smi static 2>/dev/null; amd-smi metric 2>/dev/null"),
    )


def gpu_count() -> str:
    nvidia = command_output("nvidia-smi -L 2>/dev/null | wc -l")
    if nvidia.isdigit() and int(nvidia) > 0:
        return nvidia
    amd = amd_gpu_count(command_output("amd-smi static 2>/dev/null"))
    if amd.isdigit() and int(amd) > 0:
        return amd
    return ""


def metric_items(definition: Path) -> list[tuple[str, str]]:
    fields = json.loads(definition.read_text(encoding="utf-8"))
    metrics = next(
        str(item.get("value", ""))
        for item in fields
        if item.get("field_name") == "Metrics"
    )
    parts = re.split(r";\s*|,\s*(?=#\d)|\n", metrics)
    items: list[tuple[str, str]] = []
    for part in parts:
        text = part.strip()
        if not text:
            continue
        match = re.match(r"^#(\d+)\s*:\s*(.*)$", text)
        if match:
            items.append((match.group(1), match.group(2).strip()))
    return items


def metric_key(description: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", description).strip("_").lower() or "value"


_NON_RESULT_METRIC_KEYS = {
    "rc", "command", "check", "status", "sample_index", "error_message",
}


def metric_results(summary_path: Path, items: list[tuple[str, str]]) -> list[str]:
    try:
        payload: dict[str, Any] = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [""] * len(items)
    metrics = payload.get("metrics", {})
    if not isinstance(metrics, dict):
        return [""] * len(items)
    filtered = {
        key: value
        for key, value in metrics.items()
        if str(key).lower() not in _NON_RESULT_METRIC_KEYS
    }
    try:
        from metric_contract import annotate_metrics

        filtered = annotate_metrics(filtered, str(payload.get("gpu_name") or ""))
    except Exception:
        pass
    try:
        from print_metric_summary import resolve_metrics

        resolved = resolve_metrics(items, filtered)
    except Exception:
        resolved = []
        for _, description in items:
            match = re.search(r"\(([A-Za-z0-9_]+)(?:[;,/ ].*)?\)$", description.strip())
            paren_key = match.group(1) if match else ""
            key = metric_key(description)
            if paren_key and paren_key in filtered:
                value = filtered[paren_key]
            elif key in filtered:
                value = filtered[key]
            else:
                value = "NOT FOUND"
            resolved.append(("", description, key, value))
    results: list[str] = []
    for _number, _description, _label, value in resolved:
        if value == "NOT FOUND" or value is None:
            results.append("na (unresolved metric)")
        else:
            results.append(str(value))
    return results


def workload_name(definition: Path) -> str:
    fields = json.loads(definition.read_text(encoding="utf-8"))
    return next(
        (
            str(item.get("value", ""))
            for item in fields
            if item.get("field_name") == "Workload Name"
        ),
        "",
    )


def parse_start(value: str) -> dt.datetime:
    normalized = value.strip().replace("Z", "+00:00")
    parsed = dt.datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


FAILURE_DETAIL_MAX = 1200
_RC_MEANINGS = {
    2: "argparse/usage",
    126: "not executable",
    127: "command not found",
    137: "killed",
    143: "terminated",
}
_SKIP_LOG_PREFIXES = (
    "[run]",
    "[info]",
    "[pass]",
    "[warn]",
    "[error]",
)
_SKIP_LOG_SNIPPETS = (
    "userwarning",
    "failed to initialize numpy",
    "triggered internally at",
)


def _one_line(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\x00", "")).strip()


def _parse_status_code(*texts: str) -> int | None:
    for text in texts:
        match = re.search(r"\bstatus(?:\s+code)?[=\s]+(\d+)\b", text or "", flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
        match = re.search(r"\brc=(\d+)\b", text or "", flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _rc_meaning(code: int | None, stderr: str) -> str:
    if code in _RC_MEANINGS:
        return _RC_MEANINGS[code]
    lowered = (stderr or "").lower()
    if "command not found" in lowered:
        return "command not found"
    if "arguments are required" in lowered or "unrecognized arguments" in lowered:
        return "argparse/usage"
    return ""


def _extract_last_cmd(run_log: Path | None, command_log: Path | None) -> str:
    if run_log is not None and run_log.is_file():
        for line in reversed(run_log.read_text(encoding="utf-8", errors="replace").splitlines()):
            stripped = line.strip()
            if stripped.startswith("[RUN]"):
                return _one_line(stripped[5:])
    if command_log is not None and command_log.is_file():
        for line in reversed(command_log.read_text(encoding="utf-8", errors="replace").splitlines()):
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "set -" not in stripped:
                return _one_line(stripped)
    return ""


def _extract_stderr_bits(run_log: Path | None) -> str:
    if run_log is None or not run_log.is_file():
        return ""
    selected: list[str] = []
    for raw in run_log.read_text(encoding="utf-8", errors="replace").splitlines():
        line = _one_line(raw)
        if not line:
            continue
        lowered = line.lower()
        if any(lowered.startswith(prefix) for prefix in _SKIP_LOG_PREFIXES):
            continue
        if any(snippet in lowered for snippet in _SKIP_LOG_SNIPPETS):
            continue
        if lowered.startswith("usage:") or lowered.startswith("--") or "cpu = _conversion" in lowered:
            continue
        useful = (
            "error:" in lowered
            or "command not found" in lowered
            or "no such file" in lowered
            or "traceback" in lowered
            or "required" in lowered
            or lowered.startswith("[fail]")
        )
        if useful:
            selected.append(line)
    return "; ".join(selected[-3:])


def _failure_hint(code: int | None, stderr: str, last_cmd: str) -> str:
    if ";" in last_cmd and (code == 127 or "command not found" in stderr.lower()):
        return "unquoted ';' in argv split the command"
    if code == 127 or "command not found" in stderr.lower():
        return "command not found"
    if "arguments are required" in stderr.lower() or "unrecognized arguments" in stderr.lower():
        return "argparse missing or rejected flags"
    return ""


def enrich_failure_detail(
    wrapper: str,
    *,
    exit_code: int = 1,
    subprocess_exit_code: int | None = None,
    run_log: Path | None = None,
    command_log: Path | None = None,
) -> str:
    """Compress die() text plus run.log into one ledger failure_detail line."""
    wrapper = _one_line(wrapper)
    if not wrapper:
        return ""
    last_cmd = _extract_last_cmd(run_log, command_log)
    stderr = _extract_stderr_bits(run_log)
    code = subprocess_exit_code if subprocess_exit_code is not None else _parse_status_code(wrapper, stderr)
    if code is None and "command not found" in stderr.lower():
        code = 127
    meaning = _rc_meaning(code, stderr)
    hint = _failure_hint(code, stderr, last_cmd)
    parts = [wrapper]
    if code is not None:
        parts.append(f"rc={code}" + (f" ({meaning})" if meaning else ""))
    elif exit_code:
        parts.append(f"runner_exit={exit_code}")
    if stderr:
        parts.append(f"stderr={stderr}")
    if hint:
        parts.append(f"hint={hint}")
    if last_cmd:
        parts.append(f"last_cmd={last_cmd}")
    detail = " | ".join(part for part in parts if part)
    if len(detail) > FAILURE_DETAIL_MAX:
        detail = detail[: FAILURE_DETAIL_MAX - 3].rstrip() + "..."
    return detail


def infer_failure_stage(exit_code: int | str, notes: str, explicit: str = "") -> str:
    token = (explicit or "").strip().lower()
    if token in FAILURE_STAGES:
        return token
    try:
        code = int(str(exit_code).strip() or "0")
    except ValueError:
        code = 1
    if code == 0:
        return "ok"
    text = (notes or "").lower()
    if "collection failed" in text or "stream did not" in text:
        return "collection"
    if "parse failed" in text or "parse_results" in text:
        return "parse"
    if "validation failed" in text or "validate_results" in text:
        return "validation"
    if "did not become ready" in text or "timed out" in text or "timeout" in text:
        return "timeout"
    if "ensure_setup" in text or "setup.sh" in text or text.startswith("setup "):
        return "setup"
    if "integrity" in text:
        return "integrity"
    return "other"


def _needs_quote(text: str) -> bool:
    return any(char in text for char in " \t'\"$&()|<>")


def _param_flag(name: str) -> str:
    return "--" + name.replace("_", "-")


def _format_flag(flag: str, value: str) -> str:
    if _needs_quote(value):
        return f'{flag} "{value}"'
    return f"{flag} {value}"


def _command_has_flag(command: str, flag: str) -> bool:
    return re.search(rf"(?:^|\s){re.escape(flag)}(?:\s|=|$)", command) is not None


def _clean_param_name(name: str) -> str:
    text = (name or "").strip()
    if text in _EMPTY_PARAM_NAMES:
        return ""
    return text


def definition_parameter_names(fields: dict[str, str]) -> list[str]:
    names: list[str] = []
    for index in range(1, PARAMETER_SLOT_COUNT + 1):
        names.append(_clean_param_name(str(fields.get(f"Parameter_{index:02d}", "") or "")))
    return names


def empty_parameter_slots() -> list[tuple[str, str]]:
    return [("", "")] * PARAMETER_SLOT_COUNT


def pad_parameter_slots(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    slots = empty_parameter_slots()
    for index, (name, value) in enumerate(items[:PARAMETER_SLOT_COUNT]):
        slots[index] = (_clean_param_name(name), str(value or "").strip())
    return slots


def apply_parameter_slots(row: dict[str, str], slots: list[tuple[str, str]]) -> dict[str, str]:
    for index, (name, value) in enumerate(pad_parameter_slots(slots), 1):
        row[f"Parameter_{index:02d}_Name"] = name
        row[f"Parameter_{index:02d}_Value"] = value
    return row


def slots_from_row(row: dict[str, str]) -> list[tuple[str, str]]:
    slots: list[tuple[str, str]] = []
    for index in range(1, PARAMETER_SLOT_COUNT + 1):
        slots.append(
            (
                _clean_param_name(str(row.get(f"Parameter_{index:02d}_Name", "") or "")),
                str(row.get(f"Parameter_{index:02d}_Value", "") or "").strip(),
            )
        )
    return slots


def row_has_parameter_slots(row: dict[str, str]) -> bool:
    return any(name for name, _value in slots_from_row(row))


def format_parameters_set(profile: str, slots: list[tuple[str, str]]) -> str:
    parts: list[str] = []
    if profile:
        parts.append(f"profile={profile}")
    for name, value in slots:
        if name:
            parts.append(f"{name}={value}")
    return ";".join(parts)


def parse_parameters_set(blob: str) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for part in (blob or "").split(";"):
        text = part.strip()
        if not text or "=" not in text:
            continue
        name, value = text.split("=", 1)
        name = _clean_param_name(name)
        if not name or name == "profile":
            continue
        items.append((name, value.strip()))
    return items


def parse_command_flag_items(command: str) -> list[tuple[str, str]]:
    text = (command or "").strip()
    if not text:
        return []
    try:
        tokens = shlex.split(text, posix=True)
    except ValueError:
        tokens = text.split()
    items: list[tuple[str, str]] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in {"bash", "run_benchmark.sh"} or not token.startswith("--"):
            index += 1
            continue
        raw = token[2:]
        if "=" in raw:
            name, value = raw.split("=", 1)
            key = name.replace("-", "_")
            if key not in _NON_PARAM_FLAGS:
                items.append((key, value))
            index += 1
            continue
        key = raw.replace("-", "_")
        if key in _NON_PARAM_FLAGS:
            if key == "profile" and index + 1 < len(tokens) and not tokens[index + 1].startswith("--"):
                index += 2
            else:
                index += 1
            continue
        if index + 1 < len(tokens) and not tokens[index + 1].startswith("--"):
            items.append((key, tokens[index + 1]))
            index += 2
        else:
            items.append((key, "true"))
            index += 1
    return items


def parse_command_flag_values(command: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for name, value in parse_command_flag_items(command):
        values[name] = value
    return values


def _yaml_profile_values(fields: dict[str, str], profile: str) -> dict[str, str]:
    raw = fields.get("Profile Parameter Values", "")
    parsed: dict[str, Any] = {}
    if raw:
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError:
            loaded = {}
        if isinstance(loaded, dict):
            parsed = loaded
    values: dict[str, str] = {}
    for name in definition_parameter_names(fields):
        if not name:
            continue
        item = parsed.get(name)
        value = ""
        if isinstance(item, dict):
            value = str(item.get(profile, "") or "").strip()
        elif item is not None:
            value = str(item).strip()
        if value:
            values[name] = value
    return values


def _yaml_profile_flags(fields: dict[str, str], profile: str) -> list[tuple[str, str]]:
    return [
        (_param_flag(name), value)
        for name, value in _yaml_profile_values(fields, profile).items()
    ]


def resolve_parameter_slots(
    fields: dict[str, str],
    profile: str,
    *,
    submitted: str = "",
    resolved_command: str = "",
    parameters_set: str = "",
) -> list[tuple[str, str]]:
    """Workbook Parameter_01..20 names with effective values after CLI overrides."""
    names = definition_parameter_names(fields)
    yaml_values = _yaml_profile_values(fields, profile)
    command_values = parse_command_flag_values(resolved_command)
    submitted_values = parse_command_flag_values(submitted)
    blob_values = dict(parse_parameters_set(parameters_set))
    slots = empty_parameter_slots()
    if any(names):
        for index, name in enumerate(names):
            if not name:
                continue
            value = first_nonempty(
                submitted_values.get(name, ""),
                command_values.get(name, ""),
                blob_values.get(name, ""),
                yaml_values.get(name, ""),
            )
            slots[index] = (name, value)
        return slots
    command_items = parse_command_flag_items(resolved_command or submitted)
    if command_items:
        return pad_parameter_slots(
            [
                (
                    name,
                    first_nonempty(
                        submitted_values.get(name, ""),
                        value,
                        blob_values.get(name, ""),
                    ),
                )
                for name, value in command_items
            ]
        )
    return pad_parameter_slots(parse_parameters_set(parameters_set))


def migrate_parameter_slots(row: dict[str, str]) -> list[tuple[str, str]]:
    command = first_nonempty(
        str(row.get("run_benchmark_command_fully_resolved", "") or ""),
        str(row.get("run_benchmark_command", "") or ""),
        str(row.get("run_benchmark_command_submitted", "") or ""),
    )
    command_values = parse_command_flag_values(command)
    blob_values = dict(parse_parameters_set(str(row.get("parameters_set", "") or "")))
    if row_has_parameter_slots(row):
        filled: list[tuple[str, str]] = []
        for name, value in slots_from_row(row):
            if name and not value:
                value = first_nonempty(command_values.get(name, ""), blob_values.get(name, ""))
            filled.append((name, value))
        return filled
    command_items = parse_command_flag_items(command)
    if command_items:
        return pad_parameter_slots(
            [
                (name, first_nonempty(value, blob_values.get(name, "")))
                for name, value in command_items
            ]
        )
    return pad_parameter_slots(parse_parameters_set(str(row.get("parameters_set", "") or "")))


def reconstruct_run_benchmark_command(
    fields: dict[str, str], profile: str, explicit: str = ""
) -> str:
    """Fully resolved invocation from Profile Parameter Values, or an explicit string."""
    if (explicit or "").strip():
        return explicit.strip()
    parts = ["bash run_benchmark.sh", f"--{profile}", "--validate"]
    for flag, value in _yaml_profile_flags(fields, profile):
        parts.append(_format_flag(flag, value))
    return " ".join(parts)


def resolve_run_benchmark_command_fully_resolved(
    fields: dict[str, str],
    profile: str,
    *,
    submitted: str = "",
    explicit: str = "",
) -> str:
    """Submitted argv plus yaml defaults that were not already on the command line."""
    submitted = (submitted or "").strip()
    explicit = (explicit or "").strip()
    if submitted:
        extras = [
            _format_flag(flag, value)
            for flag, value in _yaml_profile_flags(fields, profile)
            if not _command_has_flag(submitted, flag)
        ]
        if extras:
            return f"{submitted} {' '.join(extras)}"
        return submitted
    if explicit:
        return explicit
    return reconstruct_run_benchmark_command(fields, profile, "")


def format_total_runtime_mm_ss(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if re.fullmatch(r"\d+:[0-5]\d", text):
        minutes, seconds = text.split(":")
        return f"{int(minutes):02d}:{int(seconds):02d}"
    try:
        total_seconds = int(round(float(text)))
    except ValueError:
        return text
    total_seconds = max(total_seconds, 0)
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


def migrate_row(row: dict[str, str]) -> dict[str, str]:
    migrated = {column: str(row.get(column, "") or "") for column in LEDGER_COLUMNS}
    if not migrated["total_runtime_mm_ss"]:
        migrated["total_runtime_mm_ss"] = str(row.get("total_runtime", "") or "")
    migrated["total_runtime_mm_ss"] = format_total_runtime_mm_ss(
        migrated["total_runtime_mm_ss"]
    )
    notes = migrated["notes"] or str(row.get("notes", "") or "")
    if not migrated["failure_stage"]:
        migrated["failure_stage"] = infer_failure_stage(
            migrated["exit_code"] or row.get("exit_code", "0"),
            notes,
        )
    if not migrated["failure_detail"] and migrated["failure_stage"] != "ok":
        migrated["failure_detail"] = notes
    old_command = str(row.get("run_benchmark_command", "") or "")
    if old_command and not migrated["run_benchmark_command_fully_resolved"]:
        migrated["run_benchmark_command_fully_resolved"] = old_command
    apply_parameter_slots(migrated, migrate_parameter_slots(row))
    return migrated


def next_table_index(rows: list[dict[str, str]]) -> int:
    indexes: list[int] = []
    for row in rows:
        raw = str(row.get("table_index_number", "")).strip()
        if raw.isdigit():
            indexes.append(int(raw))
    return max(indexes, default=0) + 1


def definition_fields(definition: Path) -> dict[str, str]:
    return {
        str(item.get("field_name", "")): str(item.get("value", ""))
        for item in json.loads(definition.read_text(encoding="utf-8"))
        if isinstance(item, dict)
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definition", type=Path, default=Path("benchmark_specification.json"))
    parser.add_argument("--summary", type=Path, default=Path("results/summary.json"))
    parser.add_argument("--profile", required=True, choices=("smoke", "baseline", "extended"))
    parser.add_argument("--start-datetime", required=True)
    parser.add_argument(
        "--total-runtime",
        default="",
        help="Elapsed runtime in seconds or mm:ss; stored as total_runtime_mm_ss.",
    )
    parser.add_argument("--exit-code", required=True, type=int)
    parser.add_argument(
        "--failure-stage",
        default="",
        help="ok|setup|collection|parse|validation|timeout|integrity|other. Inferred from notes when omitted.",
    )
    parser.add_argument(
        "--failure-detail",
        default="",
        help="One-line reason for a nonzero exit_code. Enriched from --run-log when present.",
    )
    parser.add_argument(
        "--run-log",
        type=Path,
        default=None,
        help="Optional run.log used to enrich failure_detail on nonzero exit_code.",
    )
    parser.add_argument(
        "--command-log",
        type=Path,
        default=None,
        help="Optional commands_executed.sh used to recover last_cmd.",
    )
    parser.add_argument(
        "--subprocess-exit-code",
        type=int,
        default=None,
        help="Collector/parser/validator status when it differs from runner exit_code.",
    )
    parser.add_argument(
        "--raw-run-dir",
        default="",
        help="Per-invocation results/raw/<timestamp>_<repo>_<host> directory.",
    )
    parser.add_argument("--runtime-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--run-benchmark-command-submitted",
        default="",
        help="Argv as entered: bash run_benchmark.sh plus the original flags.",
    )
    parser.add_argument(
        "--run-benchmark-command-fully-resolved",
        default="",
        help="Submitted argv plus yaml defaults that were not already on the command line.",
    )
    parser.add_argument(
        "--run-benchmark-command",
        default="",
        help="Deprecated alias for --run-benchmark-command-fully-resolved.",
    )
    parser.add_argument(
        "--parameters-set",
        default="",
        help="Optional overlay blob. The writer rebuilds parameters_set from Parameter_01..20 slots.",
    )
    parser.add_argument("--notes", default="")
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path(os.environ.get("BENCHMARK_RUNTIME_LEDGER", "/var/opt/benchmarks/runtime_ledger.csv")),
    )
    args = parser.parse_args()

    fields = definition_fields(args.definition)
    start = parse_start(args.start_datetime)
    start_text = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    run_id = f"{fields.get('Workload Number', '')}_{start.strftime('%Y%m%d_%H%M%S')}"
    metrics = metric_items(args.definition)[:METRIC_SLOT_COUNT]
    results = metric_results(args.summary, metrics)
    metric_defs = [description for _, description in metrics]
    from metric_contract import gpu_model_note, publication_status

    detected_gpu = gpu_name()
    model_note = gpu_model_note(detected_gpu, fields.get("GPU Model", ""))
    result_status, na_count = publication_status(
        list(zip(metric_defs, results)),
        {"profile": args.profile, "gpu_count": gpu_count()},
    )
    notes = args.notes
    if result_status == "SMOKE-STANDIN":
        notes = "stub"
    elif model_note:
        notes = "; ".join(part for part in (notes, model_note) if part)
    metric_defs.extend([""] * (METRIC_SLOT_COUNT - len(metric_defs)))
    results.extend([""] * (METRIC_SLOT_COUNT - len(results)))

    row = {
        "table_index_number": "",
        "run_id": run_id,
        "workload_number": fields.get("Workload Number", ""),
        "runtime_root_dir": str(args.runtime_root.resolve()),
        "benchmark_profile": args.profile,
        "start_datetime": start_text,
        "total_runtime_mm_ss": format_total_runtime_mm_ss(args.total_runtime),
        "exit_code": str(args.exit_code),
        "failure_stage": infer_failure_stage(args.exit_code, args.notes, args.failure_stage),
        "failure_detail": (
            enrich_failure_detail(
                args.failure_detail or (args.notes if args.exit_code != 0 else ""),
                exit_code=args.exit_code,
                subprocess_exit_code=args.subprocess_exit_code,
                run_log=args.run_log,
                command_log=args.command_log,
            )
            if args.exit_code != 0
            else ""
        ),
        "raw_run_dir": args.raw_run_dir,
        "hostname": socket.gethostname(),
        "gpu_name": detected_gpu,
        "gpu_vram": gpu_vram(),
        "gpu_count": gpu_count(),
        "os_version": os_version(),
        "cpu_model": cpu_model(),
        "workload_name": workload_name(args.definition),
        "run_benchmark_command_submitted": (
            args.run_benchmark_command_submitted or ""
        ).strip(),
        "run_benchmark_command_fully_resolved": resolve_run_benchmark_command_fully_resolved(
            fields,
            args.profile,
            submitted=args.run_benchmark_command_submitted,
            explicit=args.run_benchmark_command_fully_resolved or args.run_benchmark_command,
        ),
        "parameters_set": args.parameters_set,
        "notes": notes,
        "metrics_na_count": str(na_count),
        "result_status": result_status,
        "gpu_model_note": model_note,
    }
    for index in range(METRIC_SLOT_COUNT):
        row[f"metric_{index + 1}_def"] = metric_defs[index]
        row[f"metric_{index + 1}_result"] = results[index]
    parameter_slots = resolve_parameter_slots(
        fields,
        args.profile,
        submitted=row["run_benchmark_command_submitted"],
        resolved_command=row["run_benchmark_command_fully_resolved"],
        parameters_set=args.parameters_set,
    )
    apply_parameter_slots(row, parameter_slots)
    row["parameters_set"] = format_parameters_set(args.profile, parameter_slots)

    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    with args.ledger.open("a+", newline="", encoding="utf-8") as handle:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except ImportError:
            pass
        handle.seek(0)
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames) if reader.fieldnames else []
        existing = [migrate_row(old) for old in reader]
        row["table_index_number"] = str(next_table_index(existing))
        writer = csv.DictWriter(handle, fieldnames=LEDGER_COLUMNS, extrasaction="ignore")
        if not header:
            handle.seek(0, os.SEEK_END)
            writer.writeheader()
            writer.writerow(row)
        elif header == LEDGER_COLUMNS:
            handle.seek(0, os.SEEK_END)
            writer.writerow(row)
        else:
            handle.seek(0)
            handle.truncate()
            writer.writeheader()
            for old in existing:
                writer.writerow(old)
            writer.writerow(row)
        handle.flush()
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except ImportError:
            pass
    print(f"Runtime entry added to {args.ledger}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
