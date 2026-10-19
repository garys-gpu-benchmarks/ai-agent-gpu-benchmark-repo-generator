#!/usr/bin/env python3
# File: tests/test_get_remote_info_options.py
# Description: get_remote_info.sh connection options. Runs the real script
#   against a stand-in ssh that records its arguments and refuses the
#   connection, so the script stops at its first login attempt. Checks that
#   --host/--port/--user, their --option=VALUE forms and the positional form
#   reach ssh, and that bad input is a usage error (exit 2) before ssh runs.
#   No network and no remote machine are used.
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "templates" / "suite-tools" / "scripts" / "get_remote_info.sh"
BASH = shutil.which("bash")

FAKE_SSH = """#!/usr/bin/env bash
printf '%s\\n' "$@" >>"${FAKE_SSH_LOG}"
echo "---" >>"${FAKE_SSH_LOG}"
echo "ssh: connect to host test port 22: Connection refused" >&2
exit 255
"""


@unittest.skipIf(BASH is None, "bash is not installed")
class GetRemoteInfoOptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        ssh = bin_dir / "ssh"
        ssh.write_text(FAKE_SSH, encoding="utf-8")
        ssh.chmod(ssh.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        self.log = self.tmp / "ssh.log"
        home = self.tmp / "home"
        (home / ".ssh").mkdir(parents=True)  # no keys, so only one login attempt
        self.env = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
                        FAKE_SSH_LOG=str(self.log), HOME=str(home))

    def run_script(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([BASH, str(SCRIPT), *args], cwd=self.tmp, env=self.env,
                              capture_output=True, text=True, timeout=30)

    def ssh_calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        calls, current = [], []
        for line in self.log.read_text(encoding="utf-8").splitlines():
            if line == "---":
                calls.append(current)
                current = []
            else:
                current.append(line)
        return calls

    def assert_connects(self, args: tuple[str, ...], target: str, port: str) -> None:
        result = self.run_script(*args)
        self.assertEqual(result.returncode, 1, result.stderr)  # connection refused, not a usage error
        calls = self.ssh_calls()
        self.assertTrue(calls, f"ssh was not run for {args}")
        argv = calls[0]
        self.assertEqual(argv[argv.index("-p") + 1], port, argv)
        self.assertIn(target, argv)
        self.assertIn(f"Connecting to {target} (port {port})", result.stdout)

    def assert_usage_error(self, args: tuple[str, ...], message: str) -> None:
        result = self.run_script(*args)
        self.assertEqual(result.returncode, 2, f"{args}: {result.stderr}")
        self.assertIn(message, result.stderr)
        self.assertEqual(self.ssh_calls(), [], f"ssh ran for {args}")

    def test_host_and_port_options(self) -> None:
        self.assert_connects(("--host", "203.0.113.10", "--port", "39116"), "root@203.0.113.10", "39116")

    def test_option_equals_value(self) -> None:
        self.assert_connects(("--host=203.0.113.10", "--port=39116"), "root@203.0.113.10", "39116")

    def test_short_port(self) -> None:
        self.assert_connects(("--host", "203.0.113.10", "-p", "39116"), "root@203.0.113.10", "39116")

    def test_positional_form_still_works(self) -> None:
        self.assert_connects(("203.0.113.10", "39116"), "root@203.0.113.10", "39116")

    def test_default_port(self) -> None:
        self.assert_connects(("--host", "203.0.113.10"), "root@203.0.113.10", "22")

    def test_user_in_host(self) -> None:
        self.assert_connects(("--host", "ubuntu@203.0.113.10"), "ubuntu@203.0.113.10", "22")

    def test_user_option(self) -> None:
        self.assert_connects(("--user", "ubuntu", "--host", "203.0.113.10", "--port", "2222"),
                             "ubuntu@203.0.113.10", "2222")

    def test_same_value_twice_is_accepted(self) -> None:
        self.assert_connects(("--host", "203.0.113.10", "203.0.113.10"), "root@203.0.113.10", "22")

    def test_conflicting_host(self) -> None:
        self.assert_usage_error(("--host", "203.0.113.10", "203.0.113.11"), "the host is given twice")

    def test_conflicting_port(self) -> None:
        self.assert_usage_error(("--port", "2222", "203.0.113.10", "3333"), "the port is given twice")

    def test_conflicting_user(self) -> None:
        self.assert_usage_error(("--user", "root", "--host", "ubuntu@203.0.113.10"), "the user is given twice")

    def test_bad_ports(self) -> None:
        for port in ("0", "70000", "abc", "22a"):
            with self.subTest(port=port):
                self.assert_usage_error(("--host", "203.0.113.10", "--port", port), "PORT must be a number from 1 to 65535")

    def test_missing_values(self) -> None:
        self.assert_usage_error(("--host",), "--host needs a value")
        self.assert_usage_error(("--host", "--port", "22"), "--host needs a value")
        self.assert_usage_error(("--host", "203.0.113.10", "--port"), "--port needs a value")

    def test_no_host(self) -> None:
        self.assert_usage_error((), "give the benchmark machine with --host HOST")
        self.assert_usage_error(("--port", "22"), "give the benchmark machine with --host HOST")

    def test_too_many_arguments(self) -> None:
        self.assert_usage_error(("203.0.113.10", "22", "extra"), "too many arguments")

    def test_unknown_option(self) -> None:
        self.assert_usage_error(("--frobnicate", "--host", "203.0.113.10"), "unknown option: --frobnicate")

    def test_flag_with_value(self) -> None:
        self.assert_usage_error(("--no-xlsx=yes", "--host", "203.0.113.10"), "--no-xlsx takes no value")

    def test_help(self) -> None:
        result = self.run_script("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--host HOST", result.stdout)
        self.assertIn("-p, --port PORT", result.stdout)
        self.assertIn("--user USER", result.stdout)
        self.assertEqual(self.ssh_calls(), [])


if __name__ == "__main__":
    unittest.main()
