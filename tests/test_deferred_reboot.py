#!/usr/bin/env python3
# File: tests/test_deferred_reboot.py
# Description: The postponed amdgpu reboot. When the in-place driver reload fails,
#              rocm_install_runtime (24.04 and 26.04) does not reboot if setup.sh set
#              ROCM_DEFER_REBOOT=1: it keeps stage3, records the boot ID, and returns
#              so setup installs everything else and reboots once at the end. A rerun
#              in the same boot keeps the reboot postponed; the first run after the
#              reboot completes the stage. Commands are shell stubs; nothing reboots.
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "scripts" / "lib"
SKELETON = ROOT / "scripts" / "templates" / "setup_rocm_reboot_skeleton.sh"
BASH = shutil.which("bash")

LIBS = (("rocm_install_24_04.sh", 12), ("rocm_install_26_04.sh", 10))


@unittest.skipIf(BASH is None or os.name == "nt", "needs Linux bash")
class DeferredRebootInstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.stage = self.tmp / "stage.env"
        self.boot = self.tmp / "boot_id"
        self.boot.write_text("boot-A\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, lib: str, *, defer: str, reload_rc: int = 1) -> str:
        script = textwrap.dedent(f'''
            set -euo pipefail
            cd "{self.tmp}"
            export ROCM_RUNTIME_STAGE_FILE="{self.stage}" REPO_ROOT="{self.tmp}"
            export ROCM_BOOT_ID_FILE="{self.boot}" ROCM_DEFER_REBOOT="{defer}"
            run_noninteractive_root() {{ while [[ "${{1:-}}" == *=* ]]; do shift; done; echo "ROOT $*" >> calls; }}
            install_status_log_step() {{ echo "STATUS $1 $2" >> calls; }}
            wget() {{ touch "${{2}}"; }}
            apt-cache() {{ return 0; }}
            source <(tr -d '\\r' < "{LIB / lib}")
            amdgpu_reload_instead_of_reboot() {{ echo "RELOAD $1" >> calls; return {reload_rc}; }}
            : > calls
            rocm_install_runtime
            echo "PENDING=${{ROCM_REBOOT_PENDING:-unset}}"
            if [[ -f "{self.stage}" ]]; then echo "STAGEFILE"; cat "{self.stage}"; else echo "STAGEFILE none"; fi
            cat calls
        ''')
        result = subprocess.run([BASH, "-c", script], capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_failed_reload_is_postponed_not_rebooted(self):
        for lib, _step in LIBS:
            with self.subTest(lib=lib):
                self.stage.unlink(missing_ok=True)
                out = self._run(lib, defer="1")
                self.assertNotIn("ROOT reboot", out)
                self.assertIn("PENDING=1", out)
                self.assertIn("ROCM_RUNTIME_STAGE=stage3", out)
                self.assertIn("ROCM_REBOOT_BOOT_ID=boot-A", out)

    def test_rerun_in_same_boot_stays_postponed(self):
        for lib, step in LIBS:
            with self.subTest(lib=lib):
                self.stage.unlink(missing_ok=True)
                self._run(lib, defer="1")
                out = self._run(lib, defer="1")
                self.assertNotIn("ROOT reboot", out)
                self.assertIn("PENDING=1", out)
                self.assertIn("ROCM_RUNTIME_STAGE=stage3", out)
                self.assertNotIn(f"STATUS {step} sudo reboot", out)
                # The rerun does not repeat the install steps.
                self.assertNotIn("ROOT amdgpu-install", out)

    def test_rerun_in_same_boot_without_defer_reboots(self):
        for lib, _step in LIBS:
            with self.subTest(lib=lib):
                self.stage.unlink(missing_ok=True)
                self._run(lib, defer="1")
                out = self._run(lib, defer="0")
                self.assertIn("ROOT reboot", out)
                self.assertIn("ROCM_RUNTIME_STAGE=stage3", out)

    def test_first_run_after_reboot_completes_stage(self):
        for lib, step in LIBS:
            with self.subTest(lib=lib):
                self.stage.unlink(missing_ok=True)
                self._run(lib, defer="1")
                self.boot.write_text("boot-B\n")
                out = self._run(lib, defer="1")
                self.boot.write_text("boot-A\n")
                self.assertIn("PENDING=0", out)
                self.assertIn("STAGEFILE none", out)
                self.assertIn(f"STATUS {step} sudo reboot", out)
                self.assertNotIn("ROOT reboot", out)

    def test_without_defer_failed_reload_still_reboots_immediately(self):
        for lib, _step in LIBS:
            with self.subTest(lib=lib):
                self.stage.unlink(missing_ok=True)
                out = self._run(lib, defer="0")
                self.assertIn("ROOT reboot", out)
                self.assertIn("PENDING=0", out)
                self.assertNotIn("ROCM_REBOOT_BOOT_ID", out)

    def test_successful_reload_needs_no_reboot_with_defer(self):
        for lib, _step in LIBS:
            with self.subTest(lib=lib):
                self.stage.unlink(missing_ok=True)
                out = self._run(lib, defer="1", reload_rc=0)
                self.assertNotIn("ROOT reboot", out)
                self.assertIn("PENDING=0", out)
                self.assertIn("STAGEFILE none", out)


class DeferredRebootSkeletonTests(unittest.TestCase):
    """Order of the postponed reboot in the ROCm setup.sh template."""

    @classmethod
    def setUpClass(cls):
        cls.text = SKELETON.read_text(encoding="utf-8")

    def _pos(self, needle: str) -> int:
        self.assertIn(needle, self.text)
        return self.text.index(needle)

    def test_defer_is_requested_before_runtime_install(self):
        defer = self._pos('export ROCM_DEFER_REBOOT="${ROCM_DEFER_REBOOT:-1}"')
        live_calls = [m.start() for m in re.finditer(r"^\s*rocm_install_runtime\s*$", self.text, re.MULTILINE)]
        self.assertTrue(live_calls)
        self.assertLess(defer, live_calls[0])

    def test_pending_reboot_continues_and_immediate_reboot_exits(self):
        pending = self._pos('"${ROCM_REBOOT_PENDING:-0}" == 1')
        exit_wait = self._pos('log_resume_event "Runtime stage remains; exiting until systemd resume"')
        self.assertLess(pending, exit_wait)

    def test_reboot_comes_after_installs_and_before_build(self):
        reboot = self._pos("  run_privileged reboot\n  exit 0\n")
        for later_than in ("install_workload_rocm_packages\n", "install_rag_amd.sh", "install_status_log_step jax"):
            self.assertLess(self._pos(later_than), reboot, later_than)
        build = self.text.index("  bash scripts/build.sh\n")
        complete = self._pos('install_status_log_setup "complete"')
        self.assertLess(reboot, build)
        self.assertLess(build, complete)

    def test_gpu_checks_do_not_die_before_the_reboot(self):
        for check in ("import vllm, uvloop", "jax.devices()", "import aiter, torch", "sglang.launch_server --help"):
            line = next(text for text in self.text.splitlines() if check in text)
            self.assertNotIn("die", line, check)
        self.assertIn('if [[ "${GPU_CHECKS_AFTER_REBOOT}" == 1 ]]; then', self.text)
        self.assertIn('torch.zeros(1, device="cuda")', self.text)


if __name__ == "__main__":
    unittest.main()
