#!/usr/bin/env python3
# File: tests/test_publish_attach_history.py
# Description: attach_history in publish_benchmarks_to_github.sh puts this
#   run's commit on top of GitHub's history (TEMPLATE_00_142). v1.0.39 pushed a
#   parentless bundle commit after a failed history check and GitHub rejected
#   it; a rerun kept the parentless commit. Uses local bare repositories as
#   "GitHub".
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "user_scripts" / "publish_benchmarks_to_github.sh"
BASH = shutil.which("bash")
GIT = shutil.which("git")

GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "attach-history-test",
    "GIT_AUTHOR_EMAIL": "attach-history-test@example.com",
    "GIT_COMMITTER_NAME": "attach-history-test",
    "GIT_COMMITTER_EMAIL": "attach-history-test@example.com",
    "ATTACH_HISTORY_RETRY_SEC": "0",
}


def program(text: str) -> str:
    again = text[text.index("again() {"):text.index("# Git Bash on Windows", text.index("again() {"))]
    body = text[text.index("attach_history() {"):text.index("# Reads a list of problems on stdin")]
    return "\n".join(["set -u", "sleep() { :; }", again, body, "attach_history"])


def git(*args: str, cwd: Path) -> str:
    result = subprocess.run([GIT, *args], cwd=cwd, env=GIT_ENV, capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(f"git {args} failed:\n{result.stderr}")
    return result.stdout.strip()


class AttachHistory(unittest.TestCase):
    def setUp(self) -> None:
        if BASH is None or GIT is None:
            self.skipTest("bash and git are required")
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.prog = program(SCRIPT.read_text(encoding="utf-8"))

    def remote_with_history(self) -> tuple[Path, str]:
        bare = self.tmp / "github.git"
        git("init", "-q", "--bare", "-b", "main", str(bare), cwd=self.tmp)
        seed = self.tmp / "seed"
        seed.mkdir()
        git("init", "-q", "-b", "main", cwd=seed)
        (seed / "README.md").write_text("v1\n", encoding="utf-8")
        git("add", "-A", cwd=seed)
        git("commit", "-q", "-m", "v1", cwd=seed)
        git("push", "-q", str(bare), "main", cwd=seed)
        return bare, git("rev-parse", "HEAD", cwd=seed)

    def local(self, origin: str) -> Path:
        work = self.tmp / "work"
        work.mkdir()
        git("init", "-q", "-b", "main", cwd=work)
        git("remote", "add", "origin", origin, cwd=work)
        (work / "README.md").write_text("v2\n", encoding="utf-8")
        return work

    def run_attach(self, work: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run([BASH, "-c", self.prog], cwd=work, env=GIT_ENV, capture_output=True, text=True)

    def commit_and_push(self, work: Path) -> None:
        git("add", "-A", cwd=work)
        git("commit", "-q", "-m", "v2", cwd=work)
        git("push", "-q", "origin", "main", cwd=work)  # a rejected push raises

    def test_fresh_folder_goes_on_top_of_github(self) -> None:
        bare, v1 = self.remote_with_history()
        work = self.local(str(bare))
        result = self.run_attach(work)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.commit_and_push(work)
        self.assertEqual(git("rev-parse", "HEAD~1", cwd=work), v1)

    def test_parentless_commit_from_an_earlier_attempt_is_recommitted(self) -> None:
        bare, v1 = self.remote_with_history()
        work = self.local(str(bare))
        git("add", "-A", cwd=work)
        git("commit", "-q", "-m", "orphan from the failed attempt", cwd=work)
        result = self.run_attach(work)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("not on top of GitHub's main", result.stdout)
        self.assertEqual(git("rev-parse", "HEAD", cwd=work), v1)
        self.assertEqual((work / "README.md").read_text(encoding="utf-8"), "v2\n")
        self.commit_and_push(work)
        self.assertEqual(git("show", "HEAD:README.md", cwd=work), "v2")

    def test_local_commit_already_on_top_is_kept(self) -> None:
        bare, v1 = self.remote_with_history()
        work = self.local(str(bare))
        git("fetch", "-q", "origin", "main", cwd=work)
        git("reset", "-q", "--soft", "FETCH_HEAD", cwd=work)
        git("add", "-A", cwd=work)
        git("commit", "-q", "-m", "v2", cwd=work)
        mine = git("rev-parse", "HEAD", cwd=work)
        result = self.run_attach(work)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(git("rev-parse", "HEAD", cwd=work), mine)
        git("push", "-q", "origin", "main", cwd=work)

    def test_new_repository_without_main_is_left_alone(self) -> None:
        bare = self.tmp / "empty.git"
        git("init", "-q", "--bare", "-b", "main", str(bare), cwd=self.tmp)
        work = self.local(str(bare))
        result = self.run_attach(work)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotEqual(subprocess.run([GIT, "rev-parse", "-q", "--verify", "HEAD"], cwd=work,
                                           capture_output=True).returncode, 0)

    def test_unreachable_github_stops_instead_of_a_parentless_commit(self) -> None:
        work = self.local(str(self.tmp / "missing.git"))
        result = self.run_attach(work)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Could not read the history", result.stdout)
        self.assertEqual(result.stdout.count("trying again"), 3)


if __name__ == "__main__":
    unittest.main()
