#!/usr/bin/env python3
# File: tests/test_template_00_149_changes.py
# Description: TEMPLATE_00_149 checks. An older installed kernel no longer stops
#   setup: on 2026-11-19 a refreshed AMD 24.04 droplet booted 6.8.0-149-generic
#   with 6.8.0-147-generic still installed, and all 32 bundle setups stopped in
#   2 s with "/lib/modules contains a kernel other than the running kernel".
#   refuse_foreign_installed_kernel (scripts/lib/keep_running_kernel.sh) now
#   fails only on a kernel newer than uname -r (sort -V) and reports older ones.
# Execution: python3 -m unittest tests/test_template_00_149_changes.py
"""TEMPLATE_00_149 change checks."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "scripts" / "lib" / "keep_running_kernel.sh"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from host_bash import HOST_BASH, bash_path  # noqa: E402

# A fake /lib/modules with the running kernel and the extra directories, and a
# fake uname -r. Prints the function's messages and "rc=N".
CHECK = r'''
set -u
fake_running=$1; shift
moddir=$(mktemp -d)
mkdir -p "$moddir/$fake_running"
for extra in "$@"; do mkdir -p "$moddir/$extra"; done
export KEEP_RUNNING_KERNEL_MODULES_DIR="$moddir"
source "$LIB_PATH"
uname() { printf '%s\n' "$fake_running"; }  # not $running: the function has a local of that name
refuse_foreign_installed_kernel 2>&1
echo "rc=$?"
rm -rf "$moddir"
'''

# The whole keep_running_kernel with apt stubbed, as setup runs it.
FULL = r'''
set -u
fake_running=$1; shift
moddir=$(mktemp -d)
mkdir -p "$moddir/$fake_running"
for extra in "$@"; do mkdir -p "$moddir/$extra"; done
export KEEP_RUNNING_KERNEL_MODULES_DIR="$moddir"
source "$LIB_PATH"
uname() { printf '%s\n' "$fake_running"; }  # not $running: the function has a local of that name
apt-cache() { return 1; }
apt-mark() { return 0; }
dpkg() { return 0; }
keep_running_kernel 2>&1
echo "rc=$?"
rm -rf "$moddir"
'''


def run(program: str, running: str, *extras: str) -> tuple[int, str]:
    import os

    done = subprocess.run([HOST_BASH, "-c", program, "t", running, *extras], capture_output=True, text=True,
                          timeout=60, env=dict(os.environ, LIB_PATH=bash_path(LIB)))
    out = done.stdout + done.stderr
    rc_lines = [line for line in out.splitlines() if line.startswith("rc=")]
    if not rc_lines:
        raise AssertionError(out)
    return int(rc_lines[-1][3:]), out


class OlderKernelTests(unittest.TestCase):
    def test_todays_amd_2404_droplet_passes_with_a_note(self) -> None:
        rc, out = run(CHECK, "6.8.0-149-generic", "6.8.0-147-generic")
        self.assertEqual(rc, 0, out)
        self.assertIn("[INFO]", out)
        self.assertIn("also holds older kernel 6.8.0-147-generic", out)
        self.assertIn("the running 6.8.0-149-generic", out)
        self.assertNotIn("[FAIL]", out)

    def test_older_kernel_on_2604_passes(self) -> None:
        rc, out = run(CHECK, "7.0.0-43-generic", "7.0.0-38-generic")
        self.assertEqual(rc, 0, out)

    def test_only_the_running_kernel_passes_silently(self) -> None:
        rc, out = run(CHECK, "6.8.0-149-generic")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("[INFO]", out)
        self.assertNotIn("[FAIL]", out)

    def test_newer_kernel_still_fails(self) -> None:
        for running, extra in (("6.8.0-147-generic", "6.8.0-149-generic"),
                               ("7.0.0-31-generic", "7.0.0-38-generic"),
                               ("6.8.0-149-generic", "7.0.0-43-generic")):
            with self.subTest(running=running, extra=extra):
                rc, out = run(CHECK, running, extra)
                self.assertEqual(rc, 1, out)
                self.assertIn(f"contains a kernel newer than the running kernel {running}: {extra}", out)

    def test_an_older_and_a_newer_kernel_fail_on_the_newer_only(self) -> None:
        rc, out = run(CHECK, "6.8.0-149-generic", "6.8.0-147-generic", "6.8.0-150-generic")
        self.assertEqual(rc, 1, out)
        self.assertIn("older kernel 6.8.0-147-generic", out)
        failure = next(line for line in out.splitlines() if line.startswith("[FAIL]"))
        self.assertIn("6.8.0-150-generic", failure)
        self.assertNotIn("6.8.0-147-generic", failure)

    def test_whole_setup_guard_passes_on_todays_droplet(self) -> None:
        rc, out = run(FULL, "6.8.0-149-generic", "6.8.0-147-generic")
        self.assertEqual(rc, 0, out)
        rc, out = run(FULL, "6.8.0-147-generic", "6.8.0-149-generic")
        self.assertEqual(rc, 1, out)

    def test_docs_describe_the_rule(self) -> None:
        text = (ROOT / "docs" / "rocm-reboot-install-contract.md").read_text(encoding="utf-8")
        self.assertIn("contains a kernel newer than `uname -r`", text)
        self.assertIn("An older kernel is reported with `[INFO]` and does not stop setup", text)
        self.assertNotIn("contains any directory other than `uname -r`", text)
        lib = LIB.read_text(encoding="utf-8")
        self.assertIn("sort -V", lib)
        self.assertNotIn("apt-get purge", lib)
        self.assertNotIn("apt-get remove", lib)


if __name__ == "__main__":
    unittest.main()
