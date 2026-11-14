#!/usr/bin/env python3
# File: tests/test_list_runs.py
# Description: list_runs.sh prints only the runtime ledger's run table
#   (a header line, then one line per run) and copies nothing. Runs the real script against sample ledgers: this machine
#   (no --host, via --file), the profile and --failed filters, Windows line
#   endings, a missing ledger, usage errors, and --host through a stand-in ssh
#   that runs the remote command on this machine. No network is used.
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "user_scripts" / "list_runs.sh"
BASH = shutil.which("bash")

# A pre-TEMPLATE_00_135 ledger: no setup column, benchmark from total_runtime_mm_ss.
LEDGER = (
    "a,b,c,runtime_root_dir,benchmark_profile,start_datetime,total_runtime_mm_ss,exit_code\r\n"
    "1,2,3,/opt/benchmarks/101-sys-bench-a-ubu2404,smoke,x,00:01,0\r\n"
    "1,2,3,/opt/benchmarks/102-sys-bench-b-ubu2404,smoke,x,00:02,1\r\n"
    "1,2,3,/opt/benchmarks/101-sys-bench-a-ubu2404,baseline,x,03:10,0\r\n"
)

# Logs its arguments, then runs the remote command (the last argument) here,
# with stdin passed through, the way ssh would on the benchmark machine.
FAKE_SSH = """#!/usr/bin/env bash
printf '%s\\n' "$@" >>"${FAKE_SSH_LOG}"
echo "---" >>"${FAKE_SSH_LOG}"
for last; do :; done
[[ "${last}" == true ]] && exit 0
exec bash -c "${last}"
"""


@unittest.skipIf(BASH is None, "bash is not installed")
class ListRunsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.ledger = self.tmp / "runtime_ledger.csv"
        self.ledger.write_text(LEDGER, encoding="utf-8", newline="")
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        ssh = bin_dir / "ssh"
        ssh.write_text(FAKE_SSH, encoding="utf-8")
        ssh.chmod(ssh.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        self.log = self.tmp / "ssh.log"
        home = self.tmp / "home"
        (home / ".ssh").mkdir(parents=True)
        self.env = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
                        FAKE_SSH_LOG=str(self.log), HOME=str(home))

    def run_script(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([BASH, str(SCRIPT), *args], cwd=self.tmp, env=self.env,
                              capture_output=True, text=True, timeout=30)

    HEADER = "workload                                                     profile   benchmark exit_code"

    def rows(self, stdout: str) -> list[list[str]]:
        # The whole output is the table: the header line first, nothing else.
        lines = stdout.splitlines()
        self.assertEqual(lines[0], self.HEADER, stdout)
        return [line.split() for line in lines[1:]]

    def test_every_run_on_this_machine(self) -> None:
        result = self.run_script("--file", str(self.ledger))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(self.rows(result.stdout), [
            ["101-sys-bench-a-ubu2404", "smoke", "00:01", "0"],
            ["102-sys-bench-b-ubu2404", "smoke", "00:02", "1"],
            ["101-sys-bench-a-ubu2404", "baseline", "03:10", "0"],
        ])
        self.assertFalse(self.log.exists(), "this machine must not use ssh")
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ["bin", "home", "runtime_ledger.csv"])

    def test_filters(self) -> None:
        result = self.run_script("-l", str(self.ledger), "--baseline")
        self.assertEqual(self.rows(result.stdout), [["101-sys-bench-a-ubu2404", "baseline", "03:10", "0"]])
        self.assertIn("101-sys-bench-a-ubu2404                                      baseline  03:10     0", result.stdout)
        result = self.run_script(f"--file={self.ledger}", "--failed")
        self.assertEqual(self.rows(result.stdout), [["102-sys-bench-b-ubu2404", "smoke", "00:02", "1"]])
        result = self.run_script("--file", str(self.ledger), "--profile", "extended")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows(result.stdout), [])  # just the header

    def test_remote_machine(self) -> None:
        result = self.run_script("--host", "203.0.113.10", "-p", "2222", "--file", str(self.ledger), "--failed")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(self.rows(result.stdout), [["102-sys-bench-b-ubu2404", "smoke", "00:02", "1"]])
        calls = self.log.read_text(encoding="utf-8")
        self.assertIn("root@203.0.113.10", calls)
        self.assertIn("2222", calls)

    def test_new_ledger_columns_and_quoted_commas(self) -> None:
        # TEMPLATE_00_135 header order; workload_name and failure_detail hold commas.
        ledger = self.tmp / "new_ledger.csv"
        ledger.write_text(
            "table_index_number,run_id,workload_number,workload_name,benchmark_profile,result_status,"
            "exit_code,metrics_na_count,failure_stage,failure_detail,start_script_datetime,"
            "start_setup_datetime,start_benchmark_datetime,runtime_script_mm_ss,runtime_setup_mm_ss,"
            "runtime_benchmark_mm_ss,runtime_root_dir\n"
            '1,107_x,107,"Name, with comma",smoke,FAIL,1,0,setup,"apt failed, retry",a,b,,00:40,00:39,,'
            "/opt/benchmarks/107-gpu-bench-x-ubu2404\n"
            '2,107_y,107,"Name, with comma",smoke,PASS,0,0,ok,,a,b,c,05:00,01:00,03:50,'
            "/opt/benchmarks/107-gpu-bench-x-ubu2404\n",
            encoding="utf-8")
        result = self.run_script("--file", str(ledger))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows(result.stdout), [
            ["107-gpu-bench-x-ubu2404", "smoke", "-", "1"],
            ["107-gpu-bench-x-ubu2404", "smoke", "03:50", "0"],
        ])

    def test_no_ledger(self) -> None:
        result = self.run_script("--file", str(self.tmp / "missing.csv"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("no runtime ledger on this machine", result.stderr)
        self.assertIn("give --host HOST", result.stderr)

    def test_usage_errors(self) -> None:
        for args, message in (
            (("--port", "22"), "--port needs --host HOST"),
            (("--user", "ubuntu"), "--user needs --host HOST"),
            (("--smoke", "--baseline"), "give one profile"),
            (("--failed=yes",), "--failed takes no value"),
            (("--frobnicate",), "unknown option: --frobnicate"),
            (("--host", "203.0.113.10", "--port", "0"), "PORT must be a number from 1 to 65535"),
        ):
            with self.subTest(args=args):
                result = self.run_script(*args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(message, result.stderr)

    def test_help(self) -> None:
        result = self.run_script("--help")
        self.assertEqual(result.returncode, 0)
        for text in ("--host HOST", "--failed", "--file FILE", "get_benchmark_results.sh"):
            self.assertIn(text, result.stdout)


if __name__ == "__main__":
    unittest.main()
