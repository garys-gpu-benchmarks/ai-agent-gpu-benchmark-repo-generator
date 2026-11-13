#!/usr/bin/env python3
# File: scripts/results_markdown.py
# Description: Short, readable results pages for a workload (TEMPLATE_00_135).
#   results/RESULTS_ACTUAL.md   refreshed by every run (scripts/update_runtime_ledger.py),
#                               one section per profile holding that profile's latest run.
#                               Under results/, so .gitignore keeps it out of git.
#   RESULTS_REFERENCE.md        committed at the repository root. Generation writes it
#                               from the validation smoke run (scripts/create_one_workload.py);
#                               user_scripts/promote_results_reference.sh can replace it
#                               with a collected --baseline run before publishing.
#   Only summary fields go in: workload description, system line, status, times,
#   metrics and the resolved command. Never hostnames, raw paths, environment
#   variables or tokens.
# Execution: imported; python3 scripts/results_markdown.py --reference-from ACTUAL --out FILE
#            [--template-version TEMPLATE_00_NNN] turns an ACTUAL page into a REFERENCE page.
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

PROFILES = ("smoke", "baseline", "extended")
ACTUAL_REL = Path("results") / "RESULTS_ACTUAL.md"
REFERENCE_NAME = "RESULTS_REFERENCE.md"
EMPTY = {"", "—", "-", "--", "None", "none", "TBD", "n/a", "N/A"}
SMOKE_NOTE = (
    "> Smoke runs use deliberately small sizes. They check that the workload installs and runs "
    "end to end; their numbers are not performance results. Baseline and extended are."
)
_SECTION = re.compile(r"<!-- profile:(\w+) -->\n.*?<!-- /profile:\1 -->\n", re.S)


def _clean(value: object) -> str:
    text = " ".join(str(value or "").split())
    return "" if text in EMPTY else text.rstrip(".")


def _cell(value: object) -> str:
    return _clean(value).replace("|", "\\|") or "—"


def repo_commit(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    sha = (result.stdout or "").strip()
    return sha if result.returncode == 0 and re.fullmatch(r"[0-9a-f]{7,40}", sha) else ""


def system_line(row: dict[str, str]) -> str:
    gpu = _clean(row.get("gpu_name"))
    count = _clean(row.get("gpu_count"))
    vram = _clean(row.get("gpu_vram"))
    parts = []
    if gpu:
        parts.append(f"{count + '× ' if count else ''}{gpu}{f' ({vram})' if vram else ''}")
    for key, prefix in (("cpu_model", ""), ("os_version", ""), ("kernel_version", "kernel "),
                        ("gpu_driver_version", "driver ")):
        value = _clean(row.get(key))
        if value:
            parts.append(prefix + value)
    return " · ".join(parts) or "—"


def header(fields: dict[str, str]) -> str:
    name = _clean(fields.get("Workload Name")) or _clean(fields.get("Repo Base Name")) or "Workload"
    number = _clean(fields.get("Workload Number"))
    lines = [f"# Results: {number + ' ' if number else ''}{name}", ""]
    for label, key in (("Main goal", "Main Goal"), ("Tools", "Command Tools Executed")):
        value = _clean(fields.get(key))
        if value:
            lines.append(f"**{label}:** {value}  ")
    return "\n".join(lines).rstrip() + "\n"


def render_section(row: dict[str, str], *, commit: str = "") -> str:
    profile = _clean(row.get("benchmark_profile")) or "smoke"
    started = _clean(row.get("start_benchmark_datetime")) or _clean(row.get("start_setup_datetime")) \
        or _clean(row.get("start_script_datetime"))
    status = _clean(row.get("result_status")) or "—"
    exit_code = _clean(row.get("exit_code")) or "—"
    times = " · ".join(
        f"{label} {_clean(row.get(key))}"
        for label, key in (("setup", "runtime_setup_mm_ss"), ("benchmark", "runtime_benchmark_mm_ss"),
                           ("whole run", "runtime_script_mm_ss"))
        if _clean(row.get(key))
    ) or "—"
    source = " · ".join(part for part in (
        f"commit {commit}" if commit else "",
        f"suite {_clean(row.get('suite_id'))}" if _clean(row.get("suite_id")) else "",
        f"run {_clean(row.get('run_id'))}" if _clean(row.get("run_id")) else "",
    ) if part)
    lines = [
        f"<!-- profile:{profile} -->",
        f"## {profile}",
        "",
        f"- **System:** {system_line(row)}",
        f"- **Run:** {started or '—'} · status **{status}** (exit {exit_code})",
        f"- **Time (mm:ss):** {times}",
    ]
    if source:
        lines.append(f"- **Source:** {source}")
    command = _clean(row.get("run_benchmark_command_fully_resolved")) or _clean(row.get("run_benchmark_command_submitted"))
    if command:
        lines.append(f"- **Command:** `{command}`")
    lines += ["", "| # | Metric | Result |", "|---|---|---|"]
    count = 0
    for index in range(1, 21):
        definition = _clean(row.get(f"metric_{index}_def"))
        if not definition:
            continue
        count += 1
        lines.append(f"| {index} | {_cell(definition)} | {_cell(row.get(f'metric_{index}_result'))} |")
    if not count:
        lines.append("| — | No metrics recorded | — |")
    if exit_code not in ("0", "—"):
        stage = _clean(row.get("failure_stage"))
        detail = _clean(row.get("failure_detail"))[:300]
        lines += ["", f"Failed at **{stage or 'unknown'}**{': ' + detail if detail else ''}"]
    lines += ["<!-- /profile:" + profile + " -->", ""]
    return "\n".join(lines) + "\n"


def merge_sections(existing: str, section: str) -> dict[str, str]:
    sections = {m.group(1): m.group(0) for m in _SECTION.finditer(existing or "")}
    new = _SECTION.search(section)
    if new:
        sections[new.group(1)] = new.group(0)
    return sections


def _ordered(sections: dict[str, str]) -> list[str]:
    known = [p for p in PROFILES if p in sections]
    return [sections[p] for p in known] + [sections[p] for p in sorted(sections) if p not in PROFILES]


def update_results_actual(repo_root: Path, fields: dict[str, str], row: dict[str, str]) -> Path:
    """Replace this profile's section of results/RESULTS_ACTUAL.md with the run just written."""
    path = repo_root / ACTUAL_REL
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    sections = merge_sections(existing, render_section(row, commit=repo_commit(repo_root)))
    body = [
        header(fields).rstrip(),
        "",
        "Latest run of each profile on this machine, written by `run_benchmark.sh` after every run. "
        "Full evidence for each run is in `results/raw/`.",
        "",
        *_ordered(sections),
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(body).rstrip() + "\n", encoding="utf-8")
    return path


def reference_from_actual(actual: str, *, template_version: str = "", generated: str = "",
                          profiles: tuple[str, ...] = (), require_pass: bool = False) -> str:
    """A committed RESULTS_REFERENCE.md from a RESULTS_ACTUAL.md page.

    profiles limits the sections kept (generation keeps smoke; a promoted baseline keeps
    baseline and extended). The header says where the numbers come from.
    """
    sections = {m.group(1): m.group(0) for m in _SECTION.finditer(actual)}
    if profiles:
        sections = {p: s for p, s in sections.items() if p in profiles}
    if require_pass:
        sections = {p: s for p, s in sections.items() if "(exit 0)" in s}
    if not sections:
        wanted = ", ".join(profiles) if profiles else "any profile"
        raise ValueError(f"no {'passed ' if require_pass else ''}section for {wanted}")
    head = actual.split("<!-- profile:", 1)[0]
    head = head.split("\nLatest run of each profile", 1)[0].rstrip() + "\n"
    provenance = " · ".join(part for part in (
        f"generator {template_version}" if template_version else "",
        f"recorded {generated}" if generated else "",
    ) if part)
    lines = [
        head,
        "Reference results measured by the maintainer on the system shown in each section"
        + (f" ({provenance})" if provenance else "")
        + ". Your own runs write `results/RESULTS_ACTUAL.md` in the same format.",
        "",
    ]
    if set(sections) == {"smoke"}:
        lines += [SMOKE_NOTE, ""]
    lines += _ordered(sections)
    return "\n".join(lines).rstrip() + "\n"


def template_version_from_path(path: Path) -> str:
    for part in reversed(Path(path).resolve().parts):
        match = re.fullmatch(r"(TEMPLATE_\d+_\d+)(?:_copy)?", part)
        if match:
            return match.group(1)
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Turn results/RESULTS_ACTUAL.md into RESULTS_REFERENCE.md.")
    parser.add_argument("--reference-from", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--template-version", default="")
    parser.add_argument("--generated", default="")
    parser.add_argument("--profiles", default="", help="comma-separated profiles to keep (default: all)")
    parser.add_argument("--require-pass", action="store_true", help="keep only sections whose run exited 0")
    args = parser.parse_args()
    profiles = tuple(p for p in args.profiles.split(",") if p)
    try:
        text = reference_from_actual(args.reference_from.read_text(encoding="utf-8"),
                                     template_version=args.template_version, generated=args.generated,
                                     profiles=profiles, require_pass=args.require_pass)
    except ValueError as exc:
        print(f"SKIP: {exc}")
        return 3
    args.out.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
