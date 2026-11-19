#!/usr/bin/env python3
# File: tests/test_publish_bundle_gitattributes.py
# Description: TEMPLATE_00_147 (2026-11-19). A bundle repository had no
#   .gitattributes at its top level, so Git for Windows (core.autocrlf=true,
#   the installer default) checked out the bundle's show_metrics.sh,
#   run_benchmark_suite.sh, list_runs.sh, get_benchmark_results.sh and README.md
#   with CRLF: "diff" against the generated project root reported every line
#   changed, and a CRLF .sh copied to Ubuntu fails. Step 7 now writes
#   ".gitattributes" (* text=auto eol=lf, *.sh text eol=lf) and commits it;
#   step 8 stops when the test clone has no .gitattributes or a top-level
#   file has a CR. The workloads already carried their own .gitattributes.
# Execution: python3 -m unittest tests/test_publish_bundle_gitattributes.py
"""Bundle repositories check out with LF line endings under core.autocrlf=true."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "user_scripts" / "publish_benchmarks_to_github.sh"
BASH = shutil.which("bash")
GIT = shutil.which("git")
TOP_LEVEL_FILES = (
    "README.md",
    "get_benchmark_results.sh",
    "list_runs.sh",
    "run_benchmark_suite.sh",
    "show_metrics.sh",
    ".gitignore",
)


def script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def step(text: str, number: int) -> str:
    start = text.index(f"# STEP {number}:")
    end = text.index(f"# STEP {number + 1}:", start)
    return text[start:end]


def gitattributes_line(text: str) -> str:
    match = re.search(r"^ *printf '[^']*' >\.gitattributes$", step(text, 7), re.MULTILINE)
    if match is None:
        raise AssertionError("step 7 does not write .gitattributes with printf")
    return match.group(0).strip()


class PublishScriptText(unittest.TestCase):
    def test_step_7_writes_lf_gitattributes(self) -> None:
        line = gitattributes_line(script_text())
        self.assertIn("* text=auto eol=lf", line)
        self.assertIn("*.sh text eol=lf", line)

    def test_step_7_commits_gitattributes(self) -> None:
        body = step(script_text(), 7)
        add = next(row for row in body.splitlines() if "again git add .gitmodules" in row)
        self.assertIn(".gitattributes", add.split("||")[0])

    def test_step_8_checks_the_clone_for_crlf(self) -> None:
        body = step(script_text(), 8)
        self.assertIn('stop "${bundle} has no .gitattributes', body)
        self.assertIn("grep -q $'\\r'", body)
        self.assertIn("has CRLF line endings", body)

    def test_script_itself_is_lf(self) -> None:
        self.assertNotIn(b"\r", SCRIPT.read_bytes())


@unittest.skipIf(BASH is None or GIT is None, "bash and git are required")
class BundleCloneLineEndings(unittest.TestCase):
    """Build a bundle-like repository and clone it the way Git for Windows does."""

    def git(self, *args: str, cwd: Path) -> str:
        return subprocess.run(
            [GIT, "-c", "init.defaultBranch=main", "-c", "user.name=t", "-c", "user.email=t@t",
             "-c", "core.autocrlf=false", *args],
            cwd=cwd, capture_output=True, text=True, check=True, timeout=60,
        ).stdout

    def clone_with_autocrlf(self, write_gitattributes: bool) -> Path:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        bundle = tmp / "bundle"
        bundle.mkdir()
        self.git("init", "-q", cwd=bundle)
        for name in TOP_LEVEL_FILES:
            (bundle / name).write_bytes(b"#!/usr/bin/env bash\necho one\necho two\n")
        if write_gitattributes:
            subprocess.run([BASH, "-c", gitattributes_line(script_text())], cwd=bundle,
                           check=True, timeout=60)
        self.git("add", "-A", cwd=bundle)
        self.git("commit", "-q", "-m", "bundle", cwd=bundle)
        clone = tmp / "clone"
        subprocess.run([GIT, "-c", "core.autocrlf=true", "clone", "-q", str(bundle), str(clone)],
                       capture_output=True, text=True, check=True, timeout=60)
        return clone

    def test_without_gitattributes_autocrlf_gives_crlf(self) -> None:
        # The 2026-11-18 bundle: proves this test reproduces the problem.
        clone = self.clone_with_autocrlf(write_gitattributes=False)
        self.assertIn(b"\r\n", (clone / "show_metrics.sh").read_bytes())

    def test_with_step_7_gitattributes_every_file_is_lf(self) -> None:
        clone = self.clone_with_autocrlf(write_gitattributes=True)
        for name in (*TOP_LEVEL_FILES, ".gitattributes"):
            with self.subTest(name=name):
                self.assertNotIn(b"\r", (clone / name).read_bytes())


if __name__ == "__main__":
    unittest.main()
