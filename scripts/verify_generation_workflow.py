#!/usr/bin/env python3
"""Deterministic smoke checks for prompt parsing, catalog, and documentation links."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from generate_workload_parameters import OUTPUT, build_catalog
from host_exec import normalize_remote_root
from prompt_workflow import available_workloads, parse_workloads, workload_token


ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_ROOTS = [ROOT, ROOT / "docs", ROOT / "templates", ROOT / ".github"]
LINK = re.compile(r"\]\(([^)#]+)(?:#[^)]+)?\)")
# templates/*_TEMPLATE.md become the README/PRD/SPEC at the root of a
# generated workload repository, so their relative links resolve there: files
# the workload copies from the generator root (LICENSE, legal/NOTICE, ...) and
# from templates/workload/ (.github/workflows/ci.yml, gpu-smoke.yml).
GENERATED_REPO_ROOTS = [ROOT, ROOT / "templates" / "workload"]


def link_resolves(path: Path, target: str) -> bool:
    if (path.parent / target).resolve().exists():
        return True
    if path.parent == ROOT / "templates" and path.name.endswith("_TEMPLATE.md"):
        return any((base / target).resolve().exists() for base in GENERATED_REPO_ROOTS)
    return False


def check_prompt_parser() -> None:
    available = available_workloads(ROOT / "BenchmarkSpecDefinitions.xlsx")
    cases = {
        "Generate workload 101.": ["101"],
        "Generate workloads 101 and 103.": ["101", "103"],
        "Generate workloads 104 through 108.": ["104", "105", "106", "107", "108"],
        "Generate workloads 101 through 132, inclusive.": [str(value) for value in range(101, 133)],
        "Generate workloads ALL.": [str(value) for value in available],
    }
    for prompt, expected in cases.items():
        actual = parse_workloads(prompt, available)
        if actual != expected:
            raise AssertionError(f"Parser mismatch for {prompt!r}: {actual} != {expected}")
    if workload_token(cases["Generate workloads ALL."], available) != "ALL":
        raise AssertionError("ALL workload token was not canonicalized.")


def check_remote_root() -> None:
    if normalize_remote_root("/opt/benchmarks") != "/opt/benchmarks":
        raise AssertionError("/opt/benchmarks was rewritten")
    rewritten = normalize_remote_root(r"C:\Program Files\Git\opt\benchmarks")
    if rewritten != "/opt/benchmarks":
        raise AssertionError(f"Git Bash rewrite was not undone: {rewritten}")
    for forbidden in ("/root", "/opt/workloads", "/root/benchmarks"):
        try:
            normalize_remote_root(forbidden)
        except SystemExit:
            continue
        raise AssertionError(f"remote root {forbidden} was accepted")


def check_catalog() -> None:
    catalog = build_catalog()
    stored = yaml.safe_load(OUTPUT.read_text(encoding="utf-8"))
    if catalog != stored:
        raise AssertionError("workload_parameters.yaml is stale; regenerate it from the workbook.")
    if len(catalog["parameters"]) < 2:
        raise AssertionError("Shared parameter catalog unexpectedly contains fewer than two parameters.")


def check_markdown_links() -> None:
    checked: set[Path] = set()
    for directory in MARKDOWN_ROOTS:
        if not directory.exists():
            continue
        for path in directory.rglob("*.md"):
            if path in checked:
                continue
            checked.add(path)
            text = path.read_text(encoding="utf-8")
            for target in LINK.findall(text):
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                if not link_resolves(path, target):
                    raise AssertionError(f"Broken Markdown link in {path}: {target}")


def main() -> int:
    check_prompt_parser()
    check_remote_root()
    check_catalog()
    check_markdown_links()
    print("[PASS] Prompt, catalog, and Markdown-link checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
