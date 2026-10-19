#!/usr/bin/env python3
# File: tests/test_shell_cd_guarded.py
# Description: Every `cd` in a shell script that does not run under `set -e`
#   must handle failure (`cd DIR || ...`). ShellCheck reports an unguarded cd
#   as SC2164 (warning), and the shared CI fails on warnings. This test catches
#   it without needing shellcheck installed. Heredoc bodies are skipped because
#   they are text, not code.
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SEARCH_DIRS = ("scripts", "templates", "implementation_components")
ERREXIT = re.compile(r"^\s*set\s+(-[a-zA-Z]*e[a-zA-Z]*\b|.*-o\s+errexit)", re.M)
HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
CD_LINE = re.compile(r"^\s*(builtin\s+)?cd(\s|$)")


def shell_files() -> list[Path]:
    files: list[Path] = []
    for name in SEARCH_DIRS:
        base = ROOT / name
        if not base.is_dir():
            continue
        for path in base.rglob("*.sh"):
            rel = path.relative_to(ROOT).as_posix()
            if rel.startswith("scripts/templates/") or "/__pycache__/" in rel:
                continue
            files.append(path)
    return sorted(files)


def unguarded_cd_lines(text: str) -> list[int]:
    if ERREXIT.search(text):
        return []
    hits: list[int] = []
    terminator: str | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        if terminator is not None:
            if line.strip() == terminator:
                terminator = None
            continue
        code = line.split(" #", 1)[0]
        if CD_LINE.match(code) and "||" not in code and "&&" not in code:
            hits.append(number)
        match = HEREDOC.search(code)
        if match and "<<<" not in code:
            terminator = match.group(2)
    return hits


class ShellCdGuardedTests(unittest.TestCase):
    def test_detector(self) -> None:
        sample = "\n".join(
            [
                "f() {",
                '    cd "${X}"  # bad',
                '    cd "${X}" || return 1',
                "    cat <<'EOF'",
                "cd /opt/benchmarks",
                "EOF",
                "}",
            ]
        )
        self.assertEqual(unguarded_cd_lines(sample), [2])
        self.assertEqual(unguarded_cd_lines("set -euo pipefail\ncd /tmp\n"), [])

    def test_no_unguarded_cd_without_errexit(self) -> None:
        problems = []
        for path in shell_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            for number in unguarded_cd_lines(text):
                problems.append(f"{path.relative_to(ROOT).as_posix()}:{number}")
        self.assertEqual(problems, [], "Use `cd DIR || _rocm_die ...` (or `|| return 1` / `|| exit 1`) — shellcheck SC2164")


if __name__ == "__main__":
    unittest.main()
