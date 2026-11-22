#!/usr/bin/env python3
# File: scripts/generator_files.py
# Description: Removes generator-only files from a generated workload once it has
#   passed, so the folder a user generates matches what a published workload holds.
#   The list is read from scripts/prepare_github_publish.sh (its *_LEFTOVERS arrays),
#   which publish runs inside every workload, so generation and publish cannot drift.
#   Generation keeps docs/GENERATION_REPORT.md and everything under results/: they are
#   the user's record of the generation, and results/ is never published.
# Execution: imported by scripts/create_one_workload.py; or run
#   python3 scripts/generator_files.py --repo-root <project-root>/<NNN>-<repo> [--dry-run]
#   from the source generator.
# Requirements: Python 3.10+.
"""Remove generator-only files from a passed workload, using publish's own list."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path, PurePosixPath

from remove_template_copy import rmtree_reliable

PREPARE_REL = Path("scripts") / "prepare_github_publish.sh"
LEFTOVER_ARRAYS = (
    "ROOT_LEFTOVERS",
    "DOC_LEFTOVERS",
    "SCRIPT_LEFTOVERS",
    "SCHEMA_LEFTOVERS",
    "CI_LEFTOVERS",
    "DIR_LEFTOVERS",
)
# Removed at publish but kept by generation: the user's record of the generation,
# and caches that are not generator files.
KEEP_AT_GENERATION = frozenset({"docs/GENERATION_REPORT.md", ".cache", "models"})
KEEP_PREFIXES = ("results/",)
FAISS_BUILDER = "scripts/build_faiss_rocm.sh"
_FAISS_WORDS = re.compile(r"faiss|rag-faiss|end-to-end rag", re.IGNORECASE)


def leftover_paths(prepare_text: str) -> list[str]:
    """Every path in prepare_github_publish.sh's *_LEFTOVERS arrays, in order."""
    paths: list[str] = []
    for name in LEFTOVER_ARRAYS:
        match = re.search(rf"^{name}=\(\n(.*?)^\)", prepare_text, re.S | re.M)
        if match is None:
            raise ValueError(f"{PREPARE_REL.as_posix()} has no {name}=( ... ) array")
        for line in match.group(1).splitlines():
            item = line.split("#", 1)[0].strip()
            if item:
                paths.append(item)
    return paths


def generation_removals(prepare_text: str) -> list[str]:
    """The leftovers generation removes: publish's list without the generation record,
    results/, caches and nested *_copy folders (remove_template_copy.py owns those)."""
    removals = []
    for rel in leftover_paths(prepare_text):
        posix = PurePosixPath(rel)
        if posix.is_absolute() or ".." in posix.parts:
            raise ValueError(f"unsafe leftover path in {PREPARE_REL.as_posix()}: {rel}")
        if rel in KEEP_AT_GENERATION or rel.startswith(KEEP_PREFIXES) or rel.endswith("_copy"):
            continue
        removals.append(rel)
    return removals


def _needs_faiss(repo: Path) -> bool:
    for name in ("benchmark_specification.json", "run_setup.sh", "run_benchmark.sh"):
        path = repo / name
        try:
            if _FAISS_WORDS.search(path.read_text(encoding="utf-8", errors="replace")):
                return True
        except OSError:
            continue
    return False


def remove_generator_files(repo: Path, template_root: Path, *, dry_run: bool = False) -> list[str]:
    """Remove the generator-only files from repo. Returns the relative paths removed."""
    repo = Path(repo).resolve()
    prepare_text = (Path(template_root) / PREPARE_REL).read_text(encoding="utf-8")
    targets = generation_removals(prepare_text)
    if not _needs_faiss(repo):
        targets.append(FAISS_BUILDER)
    removed: list[str] = []
    for rel in targets:
        path = repo / rel
        if not path.exists() and not path.is_symlink():
            continue
        if repo not in path.resolve().parents:
            raise ValueError(f"{rel} resolves outside {repo}")
        removed.append(rel)
        if dry_run:
            continue
        if path.is_dir() and not path.is_symlink():
            if not rmtree_reliable(path):
                raise OSError(f"could not remove {path}")
        else:
            path.unlink()
    return removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    template_root = Path(__file__).resolve().parents[1]
    removed = remove_generator_files(args.repo_root, template_root, dry_run=args.dry_run)
    verb = "would remove" if args.dry_run else "removed"
    for rel in removed:
        print(f"[INFO] {verb} {rel}")
    print(f"[INFO] {len(removed)} generator-only path(s) {verb} from {args.repo_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
