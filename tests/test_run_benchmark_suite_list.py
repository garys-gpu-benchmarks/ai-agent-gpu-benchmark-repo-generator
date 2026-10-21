#!/usr/bin/env python3
# File: tests/test_run_benchmark_suite_list.py
# Description: run_benchmark_suite.sh --list and --show-output, which replaced
#   the bundle's run.sh (2026-10-18). Runs the real script on stand-in
#   workloads (a run_benchmark.sh that echoes and exits with a set code), and
#   checks that no bundle or README still uses run.sh.
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "templates" / "suite-tools" / "scripts" / "run_benchmark_suite.sh"
BASH = shutil.which("bash")
# One publish script since 2026-10-19 (the former _manual variant, renamed).
PUBLISH = [ROOT / "scripts" / "publish_benchmarks_to_github.sh"]
DOCS = [ROOT / "README.md", ROOT / "templates" / "README_TEMPLATE.md",
        ROOT / "templates" / "suite-tools" / "README.md", ROOT / "docs" / "github-profile-README.md"]
RUN_SH = re.compile(r"(?<![\w/.-])\./run\.sh\b")


@unittest.skipIf(BASH is None, "bash is not installed")
class SuiteListTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def workload(self, name: str, exit_code: int | None = 0) -> None:
        folder = self.root / name
        folder.mkdir()
        if exit_code is not None:  # None: an unfetched submodule folder
            (folder / "run_benchmark.sh").write_text(
                f'#!/usr/bin/env bash\necho "OUTPUT-OF-{name} $*"\nexit {exit_code}\n', encoding="utf-8")

    def suite(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([BASH, str(SUITE), "-d", str(self.root), *args],
                              capture_output=True, text=True, timeout=60)

    def test_list_all_ready(self) -> None:
        self.workload("101-alpha")
        self.workload("102-beta")
        result = self.suite("--list")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertTrue(lines[0].startswith("101  101-alpha") and lines[0].endswith(" ready"), lines[0])
        self.assertTrue(lines[1].endswith(" ready"))
        self.assertIn("2 ready, 0 not fetched", result.stdout)
        # the publish script's end-user check counts lines ending in " ready"
        self.assertEqual(sum(1 for line in lines if line.endswith(" ready")), 2)

    def test_list_reports_unfetched_and_fails(self) -> None:
        self.workload("101-alpha")
        self.workload("103-gamma", exit_code=None)
        result = self.suite("--list")
        self.assertEqual(result.returncode, 1)
        self.assertRegex(result.stdout, r"103  103-gamma +not fetched")
        self.assertIn("submodule update --init --recursive", result.stdout)

    @unittest.skipIf(shutil.which("git") is None, "git is not installed")
    def test_list_reads_gitmodules(self) -> None:
        self.workload("101-alpha")
        (self.root / ".gitmodules").write_text(
            '[submodule "101-alpha"]\n\tpath = 101-alpha\n\turl = ../101-alpha.git\n'
            '[submodule "104-delta"]\n\tpath = 104-delta\n\turl = ../104-delta.git\n', encoding="utf-8")
        result = self.suite("--list")
        self.assertEqual(result.returncode, 1)
        self.assertRegex(result.stdout, r"104  104-delta +not fetched")

    def test_list_filters_with_workloads(self) -> None:
        self.workload("101-alpha")
        self.workload("102-beta", exit_code=None)
        result = self.suite("--list", "-w", "101")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("102-beta", result.stdout)

    def test_unfetched_single_workload_is_a_usage_error(self) -> None:
        self.workload("101-alpha")
        self.workload("102-beta", exit_code=None)
        result = self.suite("-w", "102", "--smoke")
        self.assertEqual(result.returncode, 2)
        self.assertIn("workload 102 is not fetched yet", result.stderr)

    def test_missing_workload_in_list_is_a_usage_error(self) -> None:
        self.workload("101-alpha")
        result = self.suite("-w", "101,999", "--smoke")
        self.assertEqual(result.returncode, 2)
        self.assertIn("workload 999 is not installed", result.stderr)

    def test_output_goes_to_log_only_by_default(self) -> None:
        self.workload("101-alpha")
        log = self.root / "suite.log"
        result = self.suite("-w", "101", "--smoke", "-o", str(log))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("OUTPUT-OF-101-alpha", result.stdout)
        self.assertIn("OUTPUT-OF-101-alpha --smoke", log.read_text(encoding="utf-8"))

    def test_show_output_prints_and_logs(self) -> None:
        self.workload("101-alpha")
        log = self.root / "suite.log"
        result = self.suite("-w", "101", "--smoke", "--show-output", "-o", str(log))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OUTPUT-OF-101-alpha --smoke", result.stdout)
        self.assertIn("OUTPUT-OF-101-alpha --smoke", log.read_text(encoding="utf-8"))

    def test_show_output_keeps_the_exit_code(self) -> None:
        self.workload("101-alpha", exit_code=3)
        result = self.suite("-w", "101", "--smoke", "--show-output", "-o", str(self.root / "suite.log"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("with exit code 3", result.stdout)
        self.assertIn("1 failed", result.stdout)

    def dry_run(self, *args: str) -> str:
        result = self.suite("-n", *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        # the would-be log name carries the time, which can tick between runs
        return "\n".join(line for line in result.stdout.splitlines() if not line.startswith("Log file would be:"))

    def test_profile_flags_choose_the_profiles(self) -> None:
        """2026-10-20: profiles are named with --smoke/--baseline/--extended, as in run_benchmark.sh."""
        self.workload("101-alpha")
        self.assertIn("Profiles:  baseline\n", self.dry_run("--baseline") + "\n")
        self.assertIn("Profiles:  baseline extended\n", self.dry_run("--baseline", "--extended") + "\n")
        self.assertIn("Profiles:  extended smoke\n", self.dry_run("--extended", "--smoke") + "\n")  # order as typed
        self.assertIn("Profiles:  smoke baseline extended\n", self.dry_run() + "\n")  # the default

    def test_profile_flags_run_in_the_order_given(self) -> None:
        self.workload("101-alpha")
        log = self.root / "suite.log"
        result = self.suite("-w", "101", "--extended", "--smoke", "-o", str(log))
        self.assertEqual(result.returncode, 0, result.stderr)
        text = log.read_text(encoding="utf-8")
        self.assertLess(text.index("OUTPUT-OF-101-alpha --extended"), text.index("OUTPUT-OF-101-alpha --smoke"))
        self.assertIn("2 passed, 0 failed", result.stdout)

    def test_removed_p_option_names_the_new_flags(self) -> None:
        """-p/--profiles was removed on 2026-10-20; an old command gets a pointer, not just 'unknown option'."""
        self.workload("101-alpha")
        for args in (("-p", "smoke"), ("--profiles", "baseline,extended")):
            with self.subTest(args=args):
                result = self.suite("-n", *args)
                self.assertEqual(result.returncode, 2)
                self.assertIn("was removed", result.stderr)
                self.assertIn("--smoke, --baseline, --extended", result.stderr)

    def test_help_lists_new_options(self) -> None:
        result = subprocess.run([BASH, str(SUITE), "--help"], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0)
        self.assertIn("-l, --list", result.stdout)
        self.assertIn("--show-output", result.stdout)
        for flag in ("--smoke  ", "--baseline  ", "--extended  "):
            self.assertIn(f"      {flag}", result.stdout)
        self.assertIn("-w 101,107,121 --baseline", result.stdout)
        self.assertNotIn("-p,", result.stdout)
        self.assertNotIn("--profiles", result.stdout)


class RunShRetiredTests(unittest.TestCase):
    def test_publish_scripts_no_longer_write_run_sh(self) -> None:
        for path in PUBLISH:
            text = path.read_text(encoding="utf-8")
            with self.subTest(script=path.name):
                self.assertNotIn("write_bundle_run_sh", text)
                self.assertNotIn("RUNSH", text)
                self.assertIn("git rm -q --ignore-unmatch run.sh", text)  # removed from existing bundles
                self.assertIn("./run_benchmark_suite.sh --list", text)
                self.assertIsNone(RUN_SH.search(text), RUN_SH.search(text))

    def test_docs_use_the_suite_runner(self) -> None:
        for path in DOCS:
            with self.subTest(doc=str(path.relative_to(ROOT))):
                self.assertIsNone(RUN_SH.search(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
