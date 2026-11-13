#!/usr/bin/env python3
# File: scripts/text_io.py
# Description: LF-only text writes and generated-repo gitkeep sentinels.
from __future__ import annotations

from pathlib import Path

TEXT_SUFFIXES = {".md", ".py", ".sh", ".json", ".yaml", ".yml", ".txt", ".toml", ".csv"}
GITKEEP_PATHS = (
    "results/raw/.gitkeep",
    "tests/fixtures/.gitkeep",
)


def write_lf(path: Path, text: str, exe: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = str(text).replace("\r\n", "\n").replace("\r", "\n")
    if not data.endswith("\n"):
        data += "\n"
    path.write_bytes(data.encode("utf-8"))
    if exe or path.suffix == ".sh":
        path.chmod(path.stat().st_mode | 0o111)


def normalize_text_tree(root: Path) -> int:
    """Rewrite text files under root as LF. Skip venv, cache, third_party, and binaries."""
    changed = 0
    skip = {".venv", ".cache", "third_party", "__pycache__", ".git"}
    for path in Path(root).rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name != ".gitkeep":
            continue
        raw = path.read_bytes()
        if b"\0" in raw:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if "\r" not in text:
            continue
        write_lf(path, text, exe=path.suffix == ".sh" or bool(path.stat().st_mode & 0o111))
        changed += 1
    return changed


def ensure_gitkeep(repo_root: Path) -> list[str]:
    created: list[str] = []
    for rel in GITKEEP_PATHS:
        path = Path(repo_root) / rel
        if not path.is_file():
            write_lf(path, "")
            created.append(rel)
    return created
