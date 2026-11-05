#!/usr/bin/env python3
# File: scripts/generated_repo_directory.py
# Description: Shared local-folder and GitHub-slug naming for generated workload repositories.
# The top directory is <Workload Number>-<Repo Base Name>. Workbook Repo Base Name stays unprefixed.
from __future__ import annotations

from pathlib import Path

DIR_SEPARATOR = "-"
LEGACY_DIR_SEPARATOR = "_"


def generated_repo_directory_name(workload_number: str, repo_name: str) -> str:
    workload_number = str(workload_number or "").strip()
    repo_name = str(repo_name or "").strip()
    if workload_number and repo_name:
        return f"{workload_number}{DIR_SEPARATOR}{repo_name}"
    return repo_name or workload_number


def find_generated_repo(project_root: Path, workload_number: str, repo_name: str = "") -> Path | None:
    project_root = Path(project_root)
    workload_number = str(workload_number or "").strip()
    repo_name = str(repo_name or "").strip()
    if not project_root.is_dir() or not workload_number:
        return None
    if repo_name:
        preferred = project_root / generated_repo_directory_name(workload_number, repo_name)
        if preferred.is_dir():
            return preferred
        legacy = project_root / f"{workload_number}{LEGACY_DIR_SEPARATOR}{repo_name}"
        if legacy.is_dir():
            return legacy
    dash_matches = sorted(
        path
        for path in project_root.iterdir()
        if path.is_dir() and path.name.startswith(f"{workload_number}{DIR_SEPARATOR}")
    )
    if dash_matches:
        return dash_matches[0]
    legacy_matches = sorted(
        path
        for path in project_root.iterdir()
        if path.is_dir() and path.name.startswith(f"{workload_number}{LEGACY_DIR_SEPARATOR}")
    )
    if legacy_matches:
        return legacy_matches[0]
    return None
