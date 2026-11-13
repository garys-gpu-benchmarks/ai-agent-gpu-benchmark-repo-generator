#!/usr/bin/env python3
# File: scripts/prompt_workflow.py
# Version: 1.0.0
# Maintainer: AI Agent GPU Benchmark Repo Generator
# Date: 2026-08-05
# Description: Parse workload requests and create traceable submitted-prompt artifacts.
# Execution: python3 scripts/prompt_workflow.py --prompt-file <path>
# Options: --prompt-file, --project-root, --write-artifact
# Requirements: Python 3.10+; BenchmarkSpecDefinitions.xlsx for workload validation.
# Environment: Run from the template directory or provide explicit paths.
# Dependencies: Python standard library and extract_benchmark_definition.py.
# Variables: None.
# Repository: gpu-bench/sys-bench template.
# License: Apache-2.0

from __future__ import annotations

import argparse
import datetime as dt
import re
from pathlib import Path

from extract_benchmark_definition import _load_workbook


PROMPT_LINE = re.compile(
    r"^\s*Generate\s+(?:(?:all\s+workloads?)|(?:workloads?|workload)\s+(?P<expression>.+?))\s*\.?\s*$",
    flags=re.IGNORECASE,
)
RANGE = re.compile(r"^([0-9]+)\s*(?:through|to|-)\s*([0-9]+)$", re.IGNORECASE)


def available_workloads(matrix: Path) -> list[int]:
    """Return workload numbers from the workbook's Workload Number column."""
    values: set[int] = set()
    for sheet in _load_workbook(matrix):
        header_index = next(
            (
                index
                for index, value in enumerate(sheet.rows[0])
                if value.strip().lower() == "workload number"
            ),
            None,
        )
        if header_index is None:
            for row in sheet.rows:
                for index, value in enumerate(row):
                    if value.strip().lower() == "workload number":
                        header_index = index
                        break
                if header_index is not None:
                    break
        if header_index is None:
            continue
        for row in sheet.rows:
            if header_index >= len(row):
                continue
            value = row[header_index].strip()
            if value.isdigit():
                values.add(int(value))
    if not values:
        raise SystemExit(f"[FAIL] No workload numbers found in workbook: {matrix}")
    return sorted(values)


def _directive_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip().lower().startswith("generate ")]


def parse_workloads(text: str, available: list[int]) -> list[str]:
    """Parse and validate one Generate workload(s) directive."""
    lines = _directive_lines(text)
    matches = [PROMPT_LINE.match(line) for line in lines]
    matches = [match for match in matches if match is not None]
    if len(matches) != 1:
        raise SystemExit(
            "[FAIL] Prompt must contain exactly one supported "
            "'Generate workload(s) <number/list/range>.' directive."
        )
    expression = (matches[0].group("expression") or "ALL").strip()
    expression = re.sub(r"[,\s]+inclusive\s*$", "", expression, flags=re.IGNORECASE).strip(" ,")
    if expression.lower() in {"all", "all workloads"}:
        values = list(available)
    else:
        expression = re.sub(r"\s+and\s+", ",", expression, flags=re.IGNORECASE)
        values: list[int] = []
        for part in expression.rstrip(". ").split(","):
            part = part.strip()
            range_match = RANGE.fullmatch(part)
            if range_match:
                start, stop = (int(value) for value in range_match.groups())
                if stop < start:
                    raise SystemExit(f"[FAIL] Invalid descending workload range: {part}")
                values.extend(range(start, stop + 1))
            elif part.isdigit():
                values.append(int(part))
            else:
                raise SystemExit(f"[FAIL] Invalid workload expression: {part}")
    values = sorted(set(values))
    if not values:
        raise SystemExit("[FAIL] No workloads were found in the prompt.")
    unavailable = sorted(set(values) - set(available))
    if unavailable:
        raise SystemExit(
            "[FAIL] Workload numbers are not present in the workbook: "
            + ", ".join(str(value) for value in unavailable)
        )
    return [str(value) for value in values]


def workload_token(workloads: list[str], available: list[int]) -> str:
    """Create a compact, deterministic filename token."""
    values = [int(workload) for workload in workloads]
    if values == available:
        return "ALL"
    parts: list[str] = []
    start = previous = values[0]
    for value in values[1:]:
        if value == previous + 1:
            previous = value
            continue
        parts.append(f"{start}to{previous}" if start != previous else str(start))
        start = previous = value
    parts.append(f"{start}to{previous}" if start != previous else str(start))
    return "_".join(parts)


def submitted_prompt_path(project_root: Path, token: str, now: dt.datetime | None = None) -> Path:
    """Return a non-existing UTC timestamped prompt path."""
    timestamp = (now or dt.datetime.now(dt.timezone.utc)).strftime("%Y%m%d_%H%M%S")
    base = project_root / f"AI_AGENT_PROMPT_SUBMITTED_{token}_{timestamp}.md"
    candidate = base
    suffix = 1
    while candidate.exists():
        candidate = project_root / (
            f"AI_AGENT_PROMPT_SUBMITTED_{token}_{timestamp}_{suffix:02d}.md"
        )
        suffix += 1
    return candidate


PROMPT_METADATA_MARKER = "<!-- Generation metadata"


def ensure_prompt_metadata(path: Path, workloads: list[str], template_version: str = "unknown") -> bool:
    """Append the traceability comment to a saved prompt that lacks it (TEMPLATE_00_136).

    Agents save the chat text themselves and some skipped this comment. Returns True
    when it was added. Never touches a file that holds private-key text.
    """
    text = path.read_text(encoding="utf-8")
    # An agent-written "<!-- traceability" comment counts too (TEMPLATE_00_137: all four
    # TEMPLATE_00_136 batches ended up with two comments).
    if PROMPT_METADATA_MARKER in text or "<!-- traceability" in text or "PRIVATE KEY-----" in text:
        return False
    remote_status = "supplied-for-validation" if re.search(r"\bssh\b", text) else "not-supplied"
    metadata = (
        f"{PROMPT_METADATA_MARKER}\n"
        f"created_at_utc: {dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00', 'Z')}\n"
        f"workloads: {', '.join(workloads)}\n"
        f"template_version: {template_version}\n"
        f"prompt_path: {path.as_posix()}\n"
        f"remote_validation_status: {remote_status}\n"
        "added_by: scripts/run_from_prompt.py\n"
        "-->\n"
    )
    path.write_text(text.rstrip() + "\n\n" + metadata, encoding="utf-8", newline="\n")
    return True


def write_submitted_prompt(
    prompt: str,
    path: Path,
    workloads: list[str],
    template_version: str = "unknown",
) -> None:
    """Write the prompt body followed by non-executable traceability metadata."""
    if any(
        marker in prompt
        for marker in (
            "-----BEGIN OPENSSH PRIVATE KEY-----",
            "-----BEGIN RSA PRIVATE KEY-----",
            "-----BEGIN PRIVATE KEY-----",
        )
    ):
        raise SystemExit("[FAIL] Private-key contents must not be written to a prompt artifact.")
    body = prompt.rstrip() + "\n\n"
    remote_status = "supplied-for-validation" if re.search(r"\bssh\b", prompt) else "not-supplied"
    metadata = (
        "<!-- Generation metadata\n"
        f"created_at_utc: {dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00', 'Z')}\n"
        f"workloads: {', '.join(workloads)}\n"
        f"template_version: {template_version}\n"
        f"prompt_path: {path.as_posix()}\n"
        f"remote_validation_status: {remote_status}\n"
        "-->\n"
    )
    path.write_text(body + metadata, encoding="utf-8", newline="\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse and record a submitted workload prompt.")
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--project-root", default="")
    parser.add_argument("--matrix", default="BenchmarkSpecDefinitions.xlsx")
    parser.add_argument("--write-artifact", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    prompt_path = Path(args.prompt_file).resolve()
    template_root = Path(__file__).resolve().parents[1]
    project_root = Path(args.project_root).resolve() if args.project_root else template_root.parent
    prompt = prompt_path.read_text(encoding="utf-8")
    workloads_available = available_workloads(template_root / args.matrix)
    workloads = parse_workloads(prompt, workloads_available)
    token = workload_token(workloads, workloads_available)
    print(f"[PASS] Parsed workloads: {', '.join(workloads)}")
    if args.write_artifact:
        artifact = submitted_prompt_path(project_root, token)
        write_submitted_prompt(prompt, artifact, workloads)
        print(f"[PASS] Submitted prompt artifact: {artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
