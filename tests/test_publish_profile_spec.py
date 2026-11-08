#!/usr/bin/env python3
# File: tests/test_publish_profile_spec.py
# Description: Step 10 copies BenchmarkSpecDefinitions.xlsx, and the
#   organization diagram when given, onto the profile repository and stages
#   only those files. A README and a sample folder already in the repository
#   stay through an add and a later update.
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
    "GIT_AUTHOR_NAME": "profile-spec-test",
    "GIT_AUTHOR_EMAIL": "profile-spec-test@example.com",
    "GIT_COMMITTER_NAME": "profile-spec-test",
    "GIT_COMMITTER_EMAIL": "profile-spec-test@example.com",
}


def profile_program(text: str) -> str:
    again = text[text.index("again() {"):text.index("# Git Bash on Windows", text.index("again() {"))]
    body = text[text.index("publish_profile_spec() {"):text.index("# Attaches GitHub's history")]
    return "\n".join([
        "set -u",
        "sleep() { :; }",
        again,
        body,
        'publish_profile_spec "$1" "$2" "$3" "${4:-}"',
    ])


def git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([GIT, *args], cwd=cwd, env=GIT_ENV, capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(f"git {args} failed:\n{result.stderr}")
    return result


class PublishProfileSpec(unittest.TestCase):
    def setUp(self) -> None:
        if BASH is None or GIT is None:
            self.skipTest("bash and git are required")
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        seed = self.tmp / "seed"
        seed.mkdir()
        git("init", "-q", "-b", "main", cwd=seed)
        git("config", "core.autocrlf", "false", cwd=seed)
        (seed / "README.md").write_text("profile readme\n", encoding="utf-8")
        sample = seed / "107_sys-bench-amd-stream-ddr5-bandwidth"
        sample.mkdir()
        (sample / "README.md").write_text("sample workload\n", encoding="utf-8")
        git("add", "-A", cwd=seed)
        git("commit", "-q", "-m", "profile", cwd=seed)
        self.remote = self.tmp / "remote.git"
        git("clone", "-q", "--bare", seed.as_posix(), self.remote.as_posix(), cwd=self.tmp)
        self.spec = self.tmp / "BenchmarkSpecDefinitions.xlsx"
        self.image = self.tmp / "github-organization.png"
        self.clone = self.tmp / "profile"
        self.program = profile_program(SCRIPT.read_text(encoding="utf-8"))

    def publish(self, payload: bytes, image: bytes | None = None) -> subprocess.CompletedProcess[str]:
        self.spec.write_bytes(payload)
        args = [self.spec.as_posix(), self.clone.as_posix(), self.remote.as_posix()]
        if image is not None:
            self.image.write_bytes(image)
            args.append(self.image.as_posix())
        return subprocess.run(
            [BASH, "-c", self.program, "publish_profile_spec", *args],
            env={**GIT_ENV, "VERSION": "v9.9.9", "PROFILE_REPO": "garymichaelbass/garymichaelbass",
                 "PROFILE_SPEC": "BenchmarkSpecDefinitions.xlsx",
                 "PROFILE_IMAGE": "images/github-organization.png"},
            capture_output=True, text=True, timeout=60,
        )

    def checked_out(self) -> Path:
        n = getattr(self, "_check_n", 0) + 1
        self._check_n = n
        dest = self.tmp / f"checked-{n}"
        git("clone", "-q", self.remote.as_posix(), dest.as_posix(), cwd=self.tmp)
        return dest

    def test_add_and_update_leave_the_rest_of_the_profile_repo(self) -> None:
        body = self.program
        self.assertIn('git add -- "${PROFILE_SPEC}"', body)
        self.assertNotIn("git add -A", body)

        first = self.publish(b"PK\x03\x04spec-v1\x00")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("Published BenchmarkSpecDefinitions.xlsx", first.stdout)
        tree = self.checked_out()
        self.assertEqual((tree / "README.md").read_text(encoding="utf-8"), "profile readme\n")
        self.assertEqual(
            (tree / "107_sys-bench-amd-stream-ddr5-bandwidth" / "README.md").read_text(encoding="utf-8"),
            "sample workload\n",
        )
        self.assertEqual((tree / "BenchmarkSpecDefinitions.xlsx").read_bytes(), b"PK\x03\x04spec-v1\x00")
        self.assertEqual(git("log", "-1", "--format=%s", cwd=tree).stdout.strip(),
                         "Add BenchmarkSpecDefinitions.xlsx (v9.9.9)")

        same = self.publish(b"PK\x03\x04spec-v1\x00")
        self.assertEqual(same.returncode, 0, same.stderr)
        self.assertIn("already this file", same.stdout)
        self.assertEqual(git("rev-list", "--count", "main", cwd=self.remote).stdout.strip(), "2")

        second = self.publish(b"PK\x03\x04spec-v2\x00")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("Published BenchmarkSpecDefinitions.xlsx", second.stdout)
        tree = self.checked_out()
        self.assertEqual((tree / "README.md").read_text(encoding="utf-8"), "profile readme\n")
        self.assertEqual((tree / "BenchmarkSpecDefinitions.xlsx").read_bytes(), b"PK\x03\x04spec-v2\x00")
        self.assertEqual(git("log", "-1", "--format=%s", cwd=tree).stdout.strip(),
                         "Update BenchmarkSpecDefinitions.xlsx to v9.9.9")

    def test_diagram_is_published_with_the_workbook_and_updated_alone(self) -> None:
        body = self.program
        self.assertIn('git add -- "${PROFILE_IMAGE}"', body)

        first = self.publish(b"PK\x03\x04spec-v1\x00", b"\x89PNG-v1")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("Published BenchmarkSpecDefinitions.xlsx", first.stdout)
        self.assertIn("Published images/github-organization.png", first.stdout)
        tree = self.checked_out()
        self.assertEqual((tree / "images" / "github-organization.png").read_bytes(), b"\x89PNG-v1")
        self.assertEqual((tree / "README.md").read_text(encoding="utf-8"), "profile readme\n")
        self.assertEqual(git("log", "-1", "--format=%s", cwd=tree).stdout.strip(),
                         "Add BenchmarkSpecDefinitions.xlsx (v9.9.9); Add organization diagram (v9.9.9)")

        same = self.publish(b"PK\x03\x04spec-v1\x00", b"\x89PNG-v1")
        self.assertEqual(same.returncode, 0, same.stderr)
        self.assertIn("images/github-organization.png on garymichaelbass/garymichaelbass is already this file", same.stdout)
        self.assertEqual(git("rev-list", "--count", "main", cwd=self.remote).stdout.strip(), "2")

        diagram_only = self.publish(b"PK\x03\x04spec-v1\x00", b"\x89PNG-v2")
        self.assertEqual(diagram_only.returncode, 0, diagram_only.stderr)
        self.assertIn("Published images/github-organization.png", diagram_only.stdout)
        self.assertNotIn("Published BenchmarkSpecDefinitions.xlsx", diagram_only.stdout)
        tree = self.checked_out()
        self.assertEqual((tree / "images" / "github-organization.png").read_bytes(), b"\x89PNG-v2")
        self.assertEqual(git("log", "-1", "--format=%s", cwd=tree).stdout.strip(),
                         "Update organization diagram (v9.9.9)")

    def test_a_missing_diagram_fails_before_clone(self) -> None:
        self.spec.write_bytes(b"PK\x03\x04spec\x00")
        result = subprocess.run(
            [BASH, "-c", self.program, "publish_profile_spec", self.spec.as_posix(),
             self.clone.as_posix(), self.remote.as_posix(), (self.tmp / "absent.png").as_posix()],
            env={**GIT_ENV, "VERSION": "v9.9.9", "PROFILE_REPO": "garymichaelbass/garymichaelbass",
                 "PROFILE_SPEC": "BenchmarkSpecDefinitions.xlsx",
                 "PROFILE_IMAGE": "images/github-organization.png"},
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("missing diagram", result.stdout)
        self.assertFalse(self.clone.exists())

    def test_generator_holds_the_diagram(self) -> None:
        image = ROOT / "docs" / "images" / "github-organization.png"
        self.assertTrue(image.is_file())
        self.assertEqual(image.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_a_missing_workbook_fails_before_clone(self) -> None:
        missing = self.tmp / "absent.xlsx"
        result = subprocess.run(
            [BASH, "-c", self.program, "publish_profile_spec",
             missing.as_posix(), self.clone.as_posix(), self.remote.as_posix()],
            env={**GIT_ENV, "VERSION": "v9.9.9", "PROFILE_REPO": "garymichaelbass/garymichaelbass",
                 "PROFILE_SPEC": "BenchmarkSpecDefinitions.xlsx"},
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("missing workbook", result.stdout)
        self.assertFalse(self.clone.exists())


if __name__ == "__main__":
    unittest.main()
