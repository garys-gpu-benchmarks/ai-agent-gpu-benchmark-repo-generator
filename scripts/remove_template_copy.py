#!/usr/bin/env python3
# File: scripts/remove_template_copy.py
# Version: 1.1.0
# Maintainer: AI Agent GPU Benchmark Repo Generator
# Date: 2026-10-18
# Description: Removes the nested <template>_copy/ generation workspace from a finished generated repository.
# Execution: python3 scripts/remove_template_copy.py --repo-root <project-root>/<Workload Number>-<Repo Name>
# Options: --repo-root (required), --dry-run
# Requirements: Python 3.10+
# Environment: Run from the SOURCE generator (not from inside the nested copy being removed).
# Dependencies: argparse, contextlib, json, os, re, shutil, stat, sys, tempfile, time, datetime, pathlib
# Variables: None.
# Repository: gpu-bench/sys-bench template
# License: Apache-2.0
#
# The nested copy is needed only while a workload is being generated. Once the
# workload has passed (create_one_workload.py calls this automatically), the copy
# is removed so the generated repository does not carry ~800 duplicated generator
# files whose deep paths exceed the Windows 260-character limit.
#
# Before deleting, this script:
#   * snapshots gate.json for every resolved implementation component into
#     results/component_gates.json, so self_check_generated_repo.sh can still run
#     its forbidden-CLI gate checks without the copy;
#   * records template_copy_removed_at in results/generation_manifest.json, so the
#     self-check and smoke check accept the copy's absence. template_copy_path and
#     template_copy_sha256 are kept as the provenance record of the generator used.

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import time
from datetime import datetime, timezone
from collections.abc import Iterator
from pathlib import Path

TEMPLATE_COPY_SUFFIX = "_copy"
# A directory is only treated as a template copy if it contains one of these.
TEMPLATE_MARKERS = ("scripts/create_generated_repo.py", "AGENTS.md")
# Names the generator gives its own nested copy (<generator folder>_copy). An empty folder is
# only removed as a leftover shell when it has one of these names (or the manifest's name).
GENERATOR_COPY_NAME = re.compile(r"^(ai-agent-gpu-benchmark-repo-generator|TEMPLATE_00_\d+)_copy$")
MANIFEST_REL = Path("results") / "generation_manifest.json"
GATES_REL = Path("results") / "component_gates.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fs_path(path: Path) -> str:
    """Absolute path string; on Windows use the \\\\?\\ prefix so paths over 260 chars can be deleted."""
    text = os.path.abspath(str(path))
    if os.name != "nt" or text.startswith("\\\\?\\"):
        return text
    if text.startswith("\\\\"):
        return "\\\\?\\UNC\\" + text[2:]
    return "\\\\?\\" + text


RMTREE_ATTEMPTS = 5
RMTREE_FIRST_DELAY_SECONDS = 0.5


def _make_writable_and_retry(func, path, _exc) -> None:
    """Clear read-only and retry once; never abort the walk, so the rest of the tree is still deleted."""
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        func(path)
    except OSError:
        pass  # left for the next pass of rmtree_reliable


def _rmtree(path: Path) -> None:
    target = _fs_path(path)
    if sys.version_info >= (3, 12):
        shutil.rmtree(target, onexc=_make_writable_and_retry)
    else:
        shutil.rmtree(target, onerror=_make_writable_and_retry)


def _exists(path: Path) -> bool:
    return os.path.lexists(_fs_path(path))


def rmtree_reliable(
    path: Path,
    *,
    attempts: int = RMTREE_ATTEMPTS,
    first_delay: float = RMTREE_FIRST_DELAY_SECONDS,
) -> bool:
    """Delete a directory tree and confirm it is gone. Returns True when nothing is left.

    Files on a network share (Z:) or held briefly by an editor, indexer or antivirus
    scanner can refuse deletion for a moment, and a folder whose files were just
    deleted can still report "not empty". A single shutil.rmtree then stops partway
    and leaves an empty folder skeleton behind. This keeps going past individual
    errors, retries with a growing delay (0.5, 1, 2, 4 s by default), and checks
    that the path really no longer exists.
    """
    path = Path(path)
    last_error: OSError | None = None
    for attempt in range(1, attempts + 1):
        if not _exists(path):
            return True
        try:
            _rmtree(path)
        except OSError as exc:
            last_error = exc
        if not _exists(path):
            return True
        if attempt < attempts:
            time.sleep(first_delay * (2 ** (attempt - 1)))
    detail = f": {last_error}" if last_error else ""
    print(f"[WARN] Could not fully remove {path} after {attempts} attempts{detail}", flush=True)
    return False


@contextlib.contextmanager
def reliable_temp_dir(prefix: str, dir: Path | str) -> Iterator[str]:  # noqa: A002 - mirrors tempfile
    """Like tempfile.TemporaryDirectory, but cleanup retries and a leftover is reported, not ignored."""
    path = tempfile.mkdtemp(prefix=prefix, dir=str(dir))
    try:
        yield path
    finally:
        if not rmtree_reliable(Path(path)):
            print(
                f"[WARN] Temporary generation folder was left behind: {path}. "
                "Delete it before copying or publishing this project folder.",
                flush=True,
            )


def _read_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(payload, indent=2) + "\n").encode("utf-8"))


def _is_copy_dir(path: Path) -> bool:
    return path.is_dir() and not path.is_symlink() and path.name.endswith(TEMPLATE_COPY_SUFFIX)


def _is_template_copy(path: Path) -> bool:
    return _is_copy_dir(path) and any((path / marker).exists() for marker in TEMPLATE_MARKERS)


def is_empty_copy_shell(path: Path) -> bool:
    """A generator *_copy folder that holds no files at all, only (nested) empty folders.

    This is what an interrupted delete leaves behind. Removing it cannot lose data.
    Other empty folders that merely end in _copy (for example data_copy) are left alone.
    """
    if not _is_copy_dir(path) or not GENERATOR_COPY_NAME.match(path.name):
        return False
    for _dirpath, _dirnames, filenames in os.walk(_fs_path(path)):
        if filenames:
            return False
    return True


def find_template_copies(repo_root: Path, manifest: dict) -> list[Path]:
    """Direct children of repo_root that are nested template copies, or what is left of one.

    Matches a full copy (has a generator marker file), an empty *_copy shell, and the
    copy named in the manifest even when a partial delete already removed its markers.
    """
    found: dict[str, Path] = {}
    recorded = str(manifest.get("template_copy_path") or "").strip()
    if recorded and "/" not in recorded and "\\" not in recorded and recorded not in {".", ".."}:
        candidate = repo_root / recorded
        if _is_copy_dir(candidate):
            found[candidate.name] = candidate
    for child in repo_root.iterdir():
        if _is_template_copy(child) or is_empty_copy_shell(child):
            found.setdefault(child.name, child)
    return sorted(found.values())


def _component_ids(repo_root: Path, manifest: dict) -> list[str]:
    ids = {str(item) for item in manifest.get("implementation_components_discovered") or [] if item}
    lock = repo_root / "results" / "overlay_lock.json"
    if lock.is_file():
        try:
            for item in json.loads(lock.read_text(encoding="utf-8")).values():
                if isinstance(item, dict) and item.get("component_id"):
                    ids.add(str(item["component_id"]))
        except (json.JSONDecodeError, AttributeError):
            print(f"[WARN] Could not read {lock}; gate snapshot uses the manifest component list only.")
    return sorted(ids)


def snapshot_component_gates(repo_root: Path, copy_root: Path, manifest: dict) -> int:
    """Copy gate.json for each resolved component into results/component_gates.json."""
    components_root = copy_root / "implementation_components"
    gates: dict[str, object] = {}
    for component_id in _component_ids(repo_root, manifest):
        gate = components_root / component_id / "gate.json"
        if gate.is_file():
            gates[component_id] = json.loads(gate.read_text(encoding="utf-8"))
    gates_path = repo_root / GATES_REL
    if gates_path.is_file():
        try:
            existing = json.loads(gates_path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                existing.update(gates)
                gates = existing
        except json.JSONDecodeError:
            pass
    _write_json(gates_path, gates)
    return len(gates)


def remove_template_copy(repo_root: Path, *, dry_run: bool = False) -> int:
    """Remove the nested template copy from a generated repository. Returns a process exit code."""
    repo_root = Path(repo_root).resolve()
    manifest_path = repo_root / MANIFEST_REL
    if not repo_root.is_dir():
        print(f"[FAIL] Repository root does not exist: {repo_root}")
        return 1
    if not manifest_path.is_file() or not (repo_root / "benchmark_specification.json").is_file():
        print(
            f"[FAIL] {repo_root} is not a generated workload repository "
            "(missing results/generation_manifest.json or benchmark_specification.json)."
        )
        return 1
    if (repo_root / "BenchmarkSpecDefinitions.xlsx").exists() and (repo_root / "scripts" / "create_generated_repo.py").exists() \
            and not (repo_root / "setup.sh").exists():
        print(f"[FAIL] {repo_root} looks like the generator itself, not a generated repository.")
        return 1

    try:
        manifest = _read_json(manifest_path)
    except (OSError, ValueError) as exc:
        print(f"[FAIL] Cannot read {manifest_path}: {exc}")
        return 1
    copies = find_template_copies(repo_root, manifest)
    if not copies:
        if manifest.get("template_copy_removed_at"):
            print(f"[PASS] Template copy already removed at {manifest['template_copy_removed_at']}: {repo_root}")
        else:
            print(f"[INFO] No nested template copy found in {repo_root}; nothing to remove.")
        return 0

    cwd = Path.cwd().resolve()
    for copy_root in copies:
        if cwd == copy_root or copy_root in cwd.parents:
            print(
                f"[FAIL] The current directory is inside {copy_root}. Run this script from the source "
                "generator (for example: python3 <generator>/scripts/remove_template_copy.py --repo-root <repo>)."
            )
            return 1

    for copy_root in copies:
        shell = is_empty_copy_shell(copy_root)
        kind = "empty template copy shell" if shell else "nested template copy"
        if dry_run:
            print(f"[DRY-RUN] Would remove {kind}: {copy_root}")
            continue
        if (copy_root / "implementation_components").is_dir():
            try:
                count = snapshot_component_gates(repo_root, copy_root, manifest)
            except (OSError, ValueError) as exc:
                print(f"[FAIL] Could not save component gates before removing {copy_root}: {exc}")
                return 1
            print(f"[INFO] Saved {count} component gate file(s) to {GATES_REL.as_posix()}")
        if not rmtree_reliable(copy_root):
            print(f"[FAIL] Could not remove {copy_root}")
            print("[FAIL] Close any editor, terminal, or file browser open inside that folder, then re-run.")
            return 1
        print(f"[PASS] Removed {kind}: {copy_root}")

    if not dry_run:
        manifest["template_copy_removed_at"] = _utc_now()
        _write_json(manifest_path, manifest)
        print(f"[PASS] Recorded template_copy_removed_at in {MANIFEST_REL.as_posix()}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove the nested <template>_copy/ generation workspace from a finished generated repository"
    )
    parser.add_argument("--repo-root", required=True, help="Generated repository: <project-root>/<Workload Number>-<Repo Name>")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be removed without deleting anything")
    args = parser.parse_args()
    return remove_template_copy(Path(args.repo_root), dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
