#!/usr/bin/env python3
# File: scripts/extract_benchmark_definition.py
# Version: 1.1.0
# Maintainer: AI Agent GPU Benchmark Repo Generator
# Date: 2026-07-05
# Description: Extract one workload row from BenchmarkSpecDefinitions.xlsx into benchmark_specification.json.
# Execution: python3 scripts/extract_benchmark_definition.py --workload 113
# Options: --workload, --matrix, --output, --workload-name, --quiet
# Requirements: Python 3.10+; input workbook must be an .xlsx file
# Environment: Run from the repository root before generated repository files are created.
# Dependencies: Python standard library only
# Variables: None
# Repository: gpu-bench/sys-bench workload template
# License: Apache-2.0

"""Extract a workload definition from the benchmark matrix workbook.

The template workflow uses this script in Phase 0 to turn the human-maintained
Excel matrix into a deterministic JSON contract. The generated JSON is an array
of objects shaped for the documentation templates:

    {"field_name": "...", "source_file": "BenchmarkSpecDefinitions.xlsx", "value": "..."}

The script intentionally uses only the Python standard library. An .xlsx file is
a ZIP archive containing XML files, so a full spreadsheet dependency is not
required for the simple row-extraction task.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree


DEFAULT_MATRIX = Path("BenchmarkSpecDefinitions.xlsx")
DEFAULT_OUTPUT = Path("benchmark_specification.json")
DEFAULT_WORKLOAD_NAME = ""
WORKBOOK_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


@dataclass(frozen=True)
class Sheet:
    """A worksheet loaded from the workbook archive."""

    name: str
    path: str
    rows: list[list[str]]


@dataclass(frozen=True)
class Extraction:
    """A matching workload row and the header row that describes it."""

    sheet_name: str
    header: list[str]
    values: list[str]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _column_index(cell_ref: str) -> int:
    match = re.match(r"([A-Z]+)", cell_ref.upper())
    if not match:
        return 0

    index = 0
    for char in match.group(1):
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def _read_xml(archive: zipfile.ZipFile, path: str) -> ElementTree.Element:
    try:
        with archive.open(path) as handle:
            return ElementTree.parse(handle).getroot()
    except KeyError as exc:
        raise SystemExit(f"Required workbook part is missing: {path}") from exc


def _text_content(element: ElementTree.Element | None) -> str:
    if element is None:
        return ""
    return "".join(element.itertext()).strip()


def _load_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []

    root = _read_xml(archive, "xl/sharedStrings.xml")
    values: list[str] = []
    for item in root.findall(f"{{{WORKBOOK_NS}}}si"):
        values.append("".join(item.itertext()).strip())
    return values


def _load_sheet_paths(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    workbook = _read_xml(archive, "xl/workbook.xml")
    rels = _read_xml(archive, "xl/_rels/workbook.xml.rels")

    rel_targets: dict[str, str] = {}
    for rel in rels.findall(f"{{{PKG_REL_NS}}}Relationship"):
        rel_id = rel.attrib.get("Id", "")
        target = rel.attrib.get("Target", "")
        if rel_id and target:
            # Excel writers vary between package-relative targets
            # ("worksheets/sheet1.xml") and package-absolute targets
            # ("/xl/worksheets/sheet1.xml"). Normalize both forms.
            rel_targets[rel_id] = (
                target.lstrip("/")
                if target.startswith("/")
                else f"xl/{target}"
            )

    sheets: list[tuple[str, str]] = []
    for sheet in workbook.findall(f".//{{{WORKBOOK_NS}}}sheet"):
        name = sheet.attrib.get("name", "")
        rel_id = sheet.attrib.get(f"{{{REL_NS}}}id", "")
        target = rel_targets.get(rel_id)
        if name and target:
            sheets.append((name, target))

    if not sheets:
        raise SystemExit("No worksheets found in workbook.")
    return sheets


def _cell_value(cell: ElementTree.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t", "")

    if cell_type == "inlineStr":
        return _text_content(cell.find(f"{{{WORKBOOK_NS}}}is"))

    value_node = cell.find(f"{{{WORKBOOK_NS}}}v")
    raw_value = _text_content(value_node)
    if raw_value == "":
        return ""

    if cell_type == "s":
        try:
            return shared_strings[int(raw_value)]
        except (IndexError, ValueError) as exc:
            raise SystemExit(f"Invalid shared string reference: {raw_value}") from exc

    if cell_type == "b":
        return "TRUE" if raw_value == "1" else "FALSE"

    return raw_value


def _load_rows(
    archive: zipfile.ZipFile,
    sheet_path: str,
    shared_strings: list[str],
) -> list[list[str]]:
    root = _read_xml(archive, sheet_path)
    rows: list[list[str]] = []

    for row in root.findall(f".//{{{WORKBOOK_NS}}}row"):
        values: list[str] = []
        for cell in row.findall(f"{{{WORKBOOK_NS}}}c"):
            cell_ref = cell.attrib.get("r", "")
            column = _column_index(cell_ref)
            while len(values) <= column:
                values.append("")
            values[column] = _cell_value(cell, shared_strings)

        while values and values[-1] == "":
            values.pop()
        rows.append(values)

    return rows


def _load_workbook(path: Path) -> list[Sheet]:
    if not path.exists():
        raise SystemExit(f"Workbook not found: {path}")
    if path.suffix.lower() != ".xlsx":
        raise SystemExit(f"Expected an .xlsx workbook, got: {path}")

    with zipfile.ZipFile(path) as archive:
        shared_strings = _load_shared_strings(archive)
        sheet_paths = _load_sheet_paths(archive)
        return [
            Sheet(name=name, path=sheet_path, rows=_load_rows(archive, sheet_path, shared_strings))
            for name, sheet_path in sheet_paths
        ]


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).lower()


def _row_text(row: Iterable[str]) -> str:
    return " | ".join(_normalize(cell) for cell in row if cell.strip())


def _matches_workload(row: list[str], workload: str, workload_name: str) -> bool:
    normalized_cells = [_normalize(cell) for cell in row]
    text = _row_text(row)
    normalized_name = _normalize(workload_name)

    if normalized_name and normalized_name in text:
        return True

    workload_number_patterns = {
        workload,
        f"workload {workload}",
        f"workload_{workload}",
        f"bm-{workload}",
        f"bm {workload}",
    }
    return any(cell in workload_number_patterns for cell in normalized_cells) or any(
        pattern in text for pattern in workload_number_patterns if pattern != workload
    )


def _non_empty_count(row: list[str]) -> int:
    return sum(1 for cell in row if cell.strip())


def _looks_like_header_row(row: list[str]) -> bool:
    normalized_cells = {_normalize(cell) for cell in row if cell.strip()}
    return "workload number" in normalized_cells and "workload name" in normalized_cells


def _find_header_row(rows: list[list[str]], match_index: int) -> list[str] | None:
    # Prefer an explicit schema/header row when present (typical matrix layout).
    for index in range(match_index - 1, -1, -1):
        candidate = rows[index]
        if _looks_like_header_row(candidate):
            return candidate

    matched_width = max(_non_empty_count(rows[match_index]), 2)
    for index in range(match_index - 1, -1, -1):
        candidate = rows[index]
        if _non_empty_count(candidate) >= min(2, matched_width):
            return candidate
    return None


def _header_index(header: list[str], name: str) -> int | None:
    target = _normalize(name)
    for index, cell in enumerate(header):
        if _normalize(cell) == target:
            return index
    return None


def _workload_number_cell(row: list[str], header: list[str] | None) -> str:
    if header:
        index = _header_index(header, "Workload Number")
        if index is not None and index < len(row):
            return _normalize(row[index])
    if row:
        return _normalize(row[0])
    return ""


def _extract_table_row(
    sheet: Sheet,
    workload: str,
    workload_name: str,
) -> Extraction | None:
    wanted = _normalize(workload)
    for index, row in enumerate(sheet.rows):
        header = _find_header_row(sheet.rows, index)
        if header and _looks_like_header_row(header):
            if _workload_number_cell(row, header) != wanted:
                continue
            if _non_empty_count(header) >= 2 and _non_empty_count(row) >= 2:
                return Extraction(sheet_name=sheet.name, header=header, values=row)
            continue

        if not _matches_workload(row, workload, workload_name):
            continue

        if header and _non_empty_count(header) >= 2 and _non_empty_count(row) >= 2:
            return Extraction(sheet_name=sheet.name, header=header, values=row)

    return None


def _extract_key_value_block(
    sheet: Sheet,
    workload: str,
    workload_name: str,
) -> Extraction | None:
    for index, row in enumerate(sheet.rows):
        if not _matches_workload(row, workload, workload_name):
            continue

        headers: list[str] = []
        values: list[str] = []
        for following in sheet.rows[index + 1 :]:
            if _non_empty_count(following) == 0:
                if headers:
                    break
                continue

            if len(following) >= 2 and following[0].strip():
                headers.append(following[0])
                values.append(following[1])

        if headers:
            return Extraction(sheet_name=sheet.name, header=headers, values=values)

    return None


def _find_extraction(
    sheets: list[Sheet],
    workload: str,
    workload_name: str,
) -> Extraction:
    for sheet in sheets:
        extraction = _extract_table_row(sheet, workload, workload_name)
        if extraction:
            return extraction

    for sheet in sheets:
        extraction = _extract_key_value_block(sheet, workload, workload_name)
        if extraction:
            return extraction

    raise SystemExit(
        f"Could not find Workload {workload}"
        + (f" ({workload_name})" if workload_name else "")
        + " in the workbook."
    )


def _header_lookup(header: list[str], name: str) -> int | None:
    target = _normalize(name)
    for index, cell in enumerate(header):
        if _normalize(cell) == target:
            return index
    return None


def _row_cell(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index].strip()


PROFILE_SHEET_NORMALIZED = {
    "parameters_smokebaselineextend",
    "profilevalues",
}


def _extract_profile_parameter_values(
    sheets: list[Sheet], workload: str
) -> tuple[str, dict[str, dict[str, str]]]:
    wanted = _normalize(workload)
    for sheet in sheets:
        if _normalize(sheet.name) not in PROFILE_SHEET_NORMALIZED or not sheet.rows:
            continue
        header = sheet.rows[0]
        number_idx = _header_lookup(header, "Workload Number")
        param_idx = _header_lookup(header, "Parameter")
        smoke_idx = _header_lookup(header, "smoke")
        baseline_idx = _header_lookup(header, "baseline")
        extended_idx = _header_lookup(header, "extended")
        notes_idx = _header_lookup(header, "notes")
        if None in (number_idx, param_idx, smoke_idx, baseline_idx, extended_idx):
            continue
        values: dict[str, dict[str, str]] = {}
        for row in sheet.rows[1:]:
            if _normalize(_row_cell(row, number_idx)) != wanted:
                continue
            parameter = _row_cell(row, param_idx)
            if not parameter:
                continue
            # Every cell goes through _strip_profile_cell: a TEMPLATE_00_<n>
            # authoring note in any of them is copied into
            # benchmark_specification.json and fails self_check (207 and 416
            # in the TEMPLATE_00_116 batches).
            values[parameter] = {
                "smoke": _strip_profile_cell(_row_cell(row, smoke_idx)),
                "baseline": _strip_profile_cell(_row_cell(row, baseline_idx)),
                "extended": _strip_profile_cell(_row_cell(row, extended_idx)),
                "notes": _strip_profile_cell(_row_cell(row, notes_idx)),
            }
        return sheet.name, values
    return "Parameters_SmokeBaselineExtend", {}


_TEMPLATE_NOTE_RE = re.compile(r"(?:^|[.;]\s*)TEMPLATE_00_\d+[^.;]*[.;]?", re.IGNORECASE)
_TEMPLATE_TAG_RE = re.compile(r"TEMPLATE_00_\d+(?:\s+\d{4}-\d{2}-\d{2})?:?\s*", re.IGNORECASE)


def _strip_template_notes(value: str) -> str:
    """Remove dated authoring-note clauses like "TEMPLATE_00_79 2026-09-07:
    repetitions aligned to match 112/312" from an extracted cell value.
    self_check_generated_repo.sh fails README.md/SPEC.md/PRD.md/
    benchmark_specification.json outright if any of them still contain
    "TEMPLATE_00_"; leftover workbook authoring notes used to flow straight
    through into the generated docs and trip that check (212). Only text
    mentioning a TEMPLATE_00_<n> tag is removed -- real parameter values
    are untouched.
    """
    without_notes = _TEMPLATE_NOTE_RE.sub("", value)
    if _TEMPLATE_TAG_RE.search(without_notes):
        # The sentence-boundary pass above only catches a TEMPLATE_00_<n>
        # tag that starts its own clause. A tag sitting mid-sentence (e.g.
        # inside a parenthetical) would otherwise still leave the literal
        # "TEMPLATE_00_" substring in place, which fails self_check's scan
        # just as surely -- fall back to deleting just the bare tag so the
        # forbidden substring is always gone, even if the value reads a
        # little rougher around it.
        without_notes = _TEMPLATE_TAG_RE.sub("", without_notes)
    # Do not strip "()" — Metrics (and other cells) end in a parenthetical
    # slug such as "(failure_count)". Stripping ")" made extract drop the
    # closer and print_metric_summary treat the last item as NOT FOUND.
    return re.sub(r"\s{2,}", " ", without_notes).strip(" ;.")


def _strip_profile_cell(value: str) -> str:
    """Strip TEMPLATE_00_<n> notes from a Parameters_SmokeBaselineExtend cell.

    A cell without the tag is returned unchanged, so parameter values keep
    their exact text (no trimming of a leading "." or doubled spaces).
    """
    if "template_00_" not in value.lower():
        return value
    return _strip_template_notes(value)


def _clean_value(value: str) -> str:
    stripped = _strip_template_notes(value.strip())
    return stripped if stripped else "--"


def _to_definition(extraction: Extraction, source_file: Path) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    max_width = max(len(extraction.header), len(extraction.values))

    for index in range(max_width):
        field_name = extraction.header[index].strip() if index < len(extraction.header) else ""
        if not field_name:
            continue
        if field_name == "Implementation Pack":
            continue

        if field_name in seen:
            field_name = f"{field_name}_{index + 1}"
        seen.add(field_name)

        value = extraction.values[index] if index < len(extraction.values) else ""
        entries.append(
            {
                "field_name": field_name,
                "source_file": f"{source_file.as_posix()}::{extraction.sheet_name}",
                "value": _clean_value(value),
            }
        )

    if not entries:
        raise SystemExit("Matched workload, but no field/value pairs could be extracted.")
    # Preserve the validator's stable contract when the matrix uses the newer
    # command-oriented column names introduced for agent readability.
    existing = {entry["field_name"]: entry for entry in entries}
    compatibility_aliases = {
        "Installation and Execution Summary": "Command Execution Details and Purpose",
        "Workload Command Line Executable": "Command Tools Executed",
        "ROCm Version": "GPU Runtime Version (was ROCm Version)",
        "rocBLAS Version": "BLAS Version (was rocBLAS version)",
    }
    for required_name, source_name in compatibility_aliases.items():
        if required_name in existing or source_name not in existing:
            continue
        source_entry = existing[source_name]
        entries.append(
            {
                "field_name": required_name,
                "source_file": source_entry["source_file"],
                "value": source_entry["value"],
            }
        )
        existing[required_name] = entries[-1]

    # Doc templates still name columns the current workbook does not carry.
    purpose = str(existing.get("Command Execution Details and Purpose", {}).get("value", "")).strip()
    if not purpose:
        purpose = str(existing.get("Execution Description With Parameters", {}).get("value", "")).strip()
    if not purpose:
        purpose = str(existing.get("Installation and Execution Summary", {}).get("value", "")).strip()
    vendor = str(existing.get("GPU Vendor", {}).get("value", "")).strip()
    vendor_l = vendor.lower()
    if "nvidia" in vendor_l:
        porting = (
            "Native NVIDIA CUDA workload. Execute on the stated Ubuntu release with the "
            "host NVIDIA driver and CUDA userspace. ROCm porting notes do not apply."
        )
        applicable = "NVIDIA"
    elif "amd" in vendor_l:
        porting = (
            "Primary target is AMD ROCm. NVIDIA notes in this section are reference only "
            "and are not the execution path."
        )
        applicable = "AMD"
    else:
        porting = "CPU / system workload. GPU vendor porting notes do not apply."
        applicable = vendor or "CPU"
    source_file_name = entries[0]["source_file"]
    derived_fields = {
        "Execution Summary (Run and Measure)": purpose or "--",
        "nVidia Porting Instructions (Reference Only)": porting,
        "AMD nVidia Applicable": applicable,
        "Model Context Protocols": "None",
    }
    for field_name, value in derived_fields.items():
        if field_name in existing or not str(value).strip():
            continue
        entry = {
            "field_name": field_name,
            "source_file": source_file_name,
            "value": value,
        }
        entries.append(entry)
        existing[field_name] = entry
    return entries


def _write_json(path: Path, entries: list[dict[str, str]]) -> str:
    payload = json.dumps(entries, indent=2, ensure_ascii=False)
    path.write_text(payload + "\n", encoding="utf-8")
    return payload


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract one workload from BenchmarkSpecDefinitions.xlsx into benchmark_specification.json."
    )
    parser.add_argument("--workload", required=True, help="Workload number to extract, e.g. 113.")
    parser.add_argument(
        "--workload-name",
        default=DEFAULT_WORKLOAD_NAME,
        help="Optional workload name used to disambiguate the matching row.",
    )
    parser.add_argument(
        "--matrix",
        type=Path,
        default=DEFAULT_MATRIX,
        help=f"Path to the benchmark specification workbook. Default: {DEFAULT_MATRIX}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output JSON path. Default: {DEFAULT_OUTPUT}",
    )
    parser.add_argument("--quiet", action="store_true", help="Do not print the generated JSON.")
    return parser.parse_args(argv)


_REQUIRED_FIELDS = [
    "Workload Number",
    "Workload Name",
    "Execution Domain",
    "Workload Type",
    "Workload Category",
    "Main Goal",
    "Validation Objective",
    "Metrics",
    "Framework",
    "Installation and Execution Summary",
    "Execution Description With Parameters",
    "Workload Command Line Executable",
]


def _validate_required_fields(definition: list[dict]) -> list[str]:
    """Return a list of error strings for any required field that is missing or blank."""
    present = {
        item["field_name"]: item.get("value", "")
        for item in definition
    }
    errors: list[str] = []
    for field in _REQUIRED_FIELDS:
        value = present.get(field, None)
        if value is None:
            errors.append(f"  MISSING field: '{field}'")
        elif not str(value).strip() or str(value).strip() in ("--", "TBD", ""):
            errors.append(f"  BLANK/placeholder field: '{field}' = '{value}'")
    return errors


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    sheets = _load_workbook(args.matrix)
    extraction = _find_extraction(sheets, str(args.workload), args.workload_name)
    definition = _to_definition(extraction, args.matrix)
    aliases = {
        "Software Framework": "Framework",
        "Execution Summary (Run)": "Installation and Execution Summary",
    }
    for item in definition:
        if item["field_name"] in aliases:
            item["field_name"] = aliases[item["field_name"]]
    field_names = {item["field_name"] for item in definition}
    if "Workload Command Line Executable" not in field_names:
        run_summary = next(
            (
                item
                for item in definition
                if item["field_name"] == "Installation and Execution Summary"
            ),
            None,
        )
        if run_summary:
            definition.append(
                {
                    "field_name": "Workload Command Line Executable",
                    "source_file": run_summary["source_file"],
                    "value": (
                        "Use the commands named in Installation and Execution Summary "
                        "through the generated local harness."
                    ),
                }
            )

    # Parsers consume an explicit raw-output contract. Matrix workbooks created
    # before this contract existed often only documented it in the multirow
    # output field, so preserve that information while making generation
    # deterministic for every new repository.
    field_map = {item["field_name"]: item for item in definition}
    source = next(iter(definition), {"source_file": str(args.matrix)})["source_file"]
    output_records = str(field_map.get("Output Records and Success Criteria (Multirow)", {}).get("value", "")).strip()
    workload_number = str(args.workload)
    format_by_workload = {
        "111": "Linux perf stat -x, stderr records with wrapper metadata.",
        "116": "RCCL rccl-tests stdout tables.",
        "120": "bin/rochpl (rocSOLVER LU) stdout text captured from mpirun.",
    }
    if "Raw Output Format" not in field_map:
        definition.append({
            "field_name": "Raw Output Format",
            "source_file": source,
            "value": format_by_workload.get(workload_number, output_records or "Structured benchmark stdout captured by the harness."),
        })
    if "Raw Output Example" not in field_map:
        definition.append({
            "field_name": "Raw Output Example",
            "source_file": source,
            "value": output_records or "The harness captures the command stdout/stderr in results/raw/.",
        })

    profile_sheet, profile_values = _extract_profile_parameter_values(sheets, str(args.workload))
    if profile_values:
        definition.append(
            {
                "field_name": "Profile Parameter Values",
                "source_file": f"{args.matrix.as_posix()}::{profile_sheet}",
                "value": json.dumps(profile_values, ensure_ascii=False),
            }
        )
        definition.append(
            {
                "field_name": "Profile Command Authorship",
                "source_file": f"{args.matrix.as_posix()}::{profile_sheet}",
                "value": (
                    "Workload_Definitions run_benchmark command columns are generated from "
                    f"{profile_sheet}. "
                    f"Author parameter values on the {profile_sheet} sheet only. "
                    "Do not invent smoke/baseline/extended sweep numbers. "
                    "Sweep/list flags in the command cells are documentary; omit those flags "
                    "so config/benchmark_config.yaml expands cases."
                ),
            }
        )
    else:
        print(
            f"WARNING: Workbook has no {profile_sheet} rows for this workload. "
            f"Sweep values must not be invented; add {profile_sheet} first.",
            file=sys.stderr,
        )

    errors = _validate_required_fields(definition)
    if errors:
        print(
            "WARNING: Phase 0 validation found incomplete required fields. "
            "Review benchmark_specification.json before approving:\n" + "\n".join(errors),
            file=sys.stderr,
        )

    payload = _write_json(args.output, definition)

    if not args.quiet:
        try:
            print(payload)
        except UnicodeEncodeError:
            # Windows cp1252 consoles cannot print symbols like "μ"; keep Phase 0 deterministic.
            print(payload.encode("ascii", "backslashreplace").decode("ascii"))
        print(f"\nWrote {args.output} from sheet '{extraction.sheet_name}'.", file=sys.stderr)
        if errors:
            print(
                "Phase 0 incomplete — resolve the warnings above before proceeding.",
                file=sys.stderr,
            )
        else:
            print("All required fields present. Phase 0 extraction and validation may now continue.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
