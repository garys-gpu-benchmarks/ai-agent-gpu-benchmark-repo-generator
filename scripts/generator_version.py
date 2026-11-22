#!/usr/bin/env python3
# File: scripts/generator_version.py
# Version: 1.0.0
# Maintainer: AI Agent GPU Benchmark Repo Generator
# Date: 2026-11-17
# Description: The generator's template version (TEMPLATE_00_NNN). VERSION at the
#   generator root is the source; the folder path is a fallback for a copy without
#   VERSION (TEMPLATE_00_146). Labels only: nothing fails when no version is found.
# Execution: imported by the generation scripts; or run
#   python3 scripts/generator_version.py [GENERATOR_ROOT] to print it.
# Requirements: Python 3.8+. release_label() runs git when it is installed.
"""Read the generator's template version from VERSION, then the folder path."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from results_markdown import template_version_from_path

VERSION_FILE = "VERSION"
VERSION_PATTERN = re.compile(r"TEMPLATE_\d+_\d+")
GENERATOR_ROOT = Path(__file__).resolve().parents[1]


def version_file_value(root: Path) -> str:
    """TEMPLATE_00_NNN from ROOT/VERSION, or "" when the file is missing or malformed."""
    try:
        text = (Path(root) / VERSION_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return text if VERSION_PATTERN.fullmatch(text) else ""


def generator_version(root: Path | None = None, *, warn: bool = False) -> str:
    """The template version for the generator at ROOT (default: this generator).

    VERSION wins. Without it, the nearest TEMPLATE_00_NNN folder in the path is
    used, and "" when there is none; callers choose their own label for "".
    With warn=True a VERSION that disagrees with a TEMPLATE_00_NNN folder name is
    reported once on stderr (a copy made for a new template without a VERSION bump).
    """
    root = Path(root).resolve() if root is not None else GENERATOR_ROOT
    from_file = version_file_value(root)
    from_folder = template_version_from_path(root)
    if warn and from_file and from_folder and from_file != from_folder:
        print(
            f"[WARN] {VERSION_FILE} says {from_file} but the folder path says {from_folder}; "
            f"using {from_file}. If this is a new template, update {VERSION_FILE} and CHANGELOG.md.",
            file=sys.stderr,
            flush=True,
        )
    return from_file or from_folder


RELEASE_TAG = re.compile(r"v(\d+)\.(\d+)\.(\d+)")


def release_label(root: Path | None = None) -> str:
    """The published release (v1.0.N) this generator clone is checked out at, or "".

    A clone of the published generator carries its release tags, so a user who
    cloned it gets "v1.0.N" here. The maintainer's working copy, a download
    without .git, or a commit after the tag gets "": callers then say
    "a development build" instead of showing the internal TEMPLATE_00_NNN label,
    which is for the changelog and generation records, not for users.
    """
    root = Path(root).resolve() if root is not None else GENERATOR_ROOT
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "tag", "--points-at", "HEAD"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    tags = [tag.strip() for tag in result.stdout.splitlines() if RELEASE_TAG.fullmatch(tag.strip())]
    if not tags:
        return ""
    return max(tags, key=lambda tag: tuple(int(part) for part in RELEASE_TAG.fullmatch(tag).groups()))


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else None
    print(generator_version(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
