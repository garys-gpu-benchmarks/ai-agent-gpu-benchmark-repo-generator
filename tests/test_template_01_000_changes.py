#!/usr/bin/env python3
# File: tests/test_template_01_000_changes.py
# Description: TEMPLATE_01_000 checks. The TEMPLATE_00_150 batches (2026-11-22) left
#   ai-agent-gpu-benchmark-repo-generator_copy/ (~800 generator files) in every
#   /opt/benchmarks/<workload> on the VM except the one the end-of-batch recheck copied
#   again: the copy goes to the VM for validation and only the local one was removed.
#   finish_generator_files now also removes *_copy folders on the VM, even when no other
#   generator file was removed locally. The publish script takes the release series
#   from VERSION: TEMPLATE_MM_NNN publishes as v1.MM.N (TEMPLATE_01_000 -> v1.1.0).
# Execution: python3 -m unittest tests/test_template_01_000_changes.py
"""TEMPLATE_01_000 change checks."""

from __future__ import annotations

import argparse
import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import create_one_workload as cow  # noqa: E402

COPY_RM = "find . -mindepth 1 -maxdepth 1 -type d -name '*_copy' -exec rm -rf {} +"


class RemoteCopyCleanupTests(unittest.TestCase):
    def run_finish(self, removed: list[str], *, ssh: str = "ssh -p 22 root@10.0.0.1",
                   keep: bool = False) -> list[str]:
        calls: list[str] = []
        saved_rm, saved_ssh = cow.remove_generator_files, cow.ssh_run
        cow.remove_generator_files = lambda _repo, _root: list(removed)
        cow.ssh_run = lambda _ssh, script, **_k: (calls.append(script),
                                                  subprocess.CompletedProcess([], 0, "", ""))[1]
        try:
            with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
                repo = Path(tmp) / "127-gpu-bench-amd-vllm-kvcache-stress-ubu2404"
                repo.mkdir()
                cow.finish_generator_files(repo, ROOT, argparse.Namespace(keep_template_copy=keep), ssh)
        finally:
            cow.remove_generator_files, cow.ssh_run = saved_rm, saved_ssh
        return calls

    def test_vm_cleanup_removes_the_paths_and_the_nested_copy(self) -> None:
        calls = self.run_finish(["AGENTS.md", "scripts/create_one_workload.py"])
        self.assertEqual(len(calls), 1)
        script = calls[0]
        self.assertTrue(script.startswith(f"cd {cow.REMOTE_ROOT}/127-gpu-bench-amd-vllm-kvcache-stress-ubu2404 && "))
        self.assertIn("rm -rf -- AGENTS.md scripts/create_one_workload.py", script)
        self.assertTrue(script.endswith(COPY_RM))

    def test_nested_copy_is_removed_even_when_nothing_else_was(self) -> None:
        calls = self.run_finish([])
        self.assertEqual(len(calls), 1)
        self.assertNotIn("rm -rf --", calls[0])
        self.assertTrue(calls[0].endswith(COPY_RM))

    def test_no_vm_or_keep_flag_means_no_remote_call(self) -> None:
        self.assertEqual(self.run_finish(["AGENTS.md"], ssh=""), [])
        self.assertEqual(self.run_finish(["AGENTS.md"], keep=True), [])

    def test_the_script_is_valid_shell(self) -> None:
        script = cow.remote_cleanup_script("101-x", ["docs/a b.md", "scripts/remote"])
        self.assertIn("'docs/a b.md'", script)
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from host_bash import HOST_BASH
        done = subprocess.run([HOST_BASH, "-n", "-c", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)


PUBLISH = ROOT / "user_scripts" / "publish_benchmarks_to_github.sh"


def function_source(text: str, name: str) -> str:
    start = text.index(f"\n{name}() {{\n") + 1
    return text[start:text.index("\n}\n", start) + 3]


class ReleaseSeriesTests(unittest.TestCase):
    """TEMPLATE_MM_NNN publishes as v1.MM.N; TEMPLATE_01_000 is the first v1.1.0."""

    def run_bash(self, call: str, *, version_text: str | None = None) -> subprocess.CompletedProcess[str]:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from host_bash import HOST_BASH, bash_path
        text = PUBLISH.read_text(encoding="utf-8")
        program = "\n".join([function_source(text, "template_series"),
                             function_source(text, "next_release_version"), call])
        with tempfile.TemporaryDirectory() as tmp:
            version = Path(tmp) / "VERSION"
            if version_text is not None:
                version.write_text(version_text, encoding="utf-8", newline="")
            return subprocess.run([HOST_BASH, "-c", program, "t", bash_path(version)],
                                  capture_output=True, text=True, timeout=30)

    def series(self, version_text: str | None) -> str:
        done = self.run_bash('template_series "$1"', version_text=version_text)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout.strip()

    def next_version(self, last: str, series: str) -> subprocess.CompletedProcess[str]:
        return self.run_bash(f'next_release_version "{last}" "{series}"')

    def test_series_from_version(self) -> None:
        self.assertEqual(self.series("TEMPLATE_01_000\n"), "1")
        self.assertEqual(self.series("TEMPLATE_00_150\n"), "0")
        self.assertEqual(self.series("TEMPLATE_12_007\r\n"), "12")
        self.assertEqual(self.series(None), "")
        self.assertEqual(self.series("not a version\n"), "")

    def test_next_version(self) -> None:
        cases = {
            ("v1.0.47", "1"): "v1.1.0",   # first TEMPLATE_01 publish after v1.0.47
            ("v1.1.0", "1"): "v1.1.1",
            ("v1.0.46", "0"): "v1.0.47",
            ("v1.0.46", ""): "v1.0.47",   # no VERSION: as before
            ("", "1"): "v1.1.0",
            ("", ""): "v1.0.0",
        }
        for (last, series), expected in cases.items():
            with self.subTest(last=last, series=series):
                done = self.next_version(last, series)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(done.stdout.strip(), expected)

    def test_an_older_generator_does_not_publish(self) -> None:
        done = self.next_version("v1.1.3", "0")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("already has v1.1.3", done.stderr)

    def test_a_hand_written_version_must_match_the_series(self) -> None:
        text = PUBLISH.read_text(encoding="utf-8")
        self.assertIn('series=$(template_series "${GEN}/${GENREPO}/VERSION")', text)
        self.assertIn("((vminor == series)) || stop", text)
        self.assertIn('VERSION=$(next_release_version "${last}" "${series}") || stop', text)

if __name__ == "__main__":
    unittest.main()
