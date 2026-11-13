#!/usr/bin/env python3
# File: tests/test_template_00_138_changes.py
# Description: TEMPLATE_00_138.
#   1. The generation setup timer survives a ROCm reboot. 301 (TEMPLATE_00_137 batch)
#      logged "setup.sh took 305 s", then the connection closed and the resumed run
#      logged a new start: setup.sh exits 0 after scheduling the reboot, and the
#      timer deleted its start file. The timer now finishes only when .setup_state
#      exists. The test replays that sequence: a first run whose setup.sh returns
#      without .setup_state, then a resumed run whose setup completes, and checks the
#      ledger's setup time covers both.
#   2. The polling rule allows event-triggered waits; plain sleeps stay <= 120 s.
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
BASH = shutil.which("bash")
NS = 1_000_000_000
SETUP_LINE = "bash setup.sh --assume-yes --resume-auto || bash setup.sh --assume-yes"


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_00_138", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS))
    try:
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def timer_block(setup_command: str) -> str:
    script = load("create_one_workload")._remote_script("301-x", resume=True, stamp="s")
    start = script.index('SETUP_T="$REPO/results/.generation_setup"')
    end = script.index("\nfi\n", script.index("keeping start $(cat")) + len("\nfi\n")
    block = script[start:end]
    assert SETUP_LINE in block
    return block.replace(SETUP_LINE, setup_command)


@unittest.skipIf(BASH is None, "bash is not installed")
class RebootTimerTests(unittest.TestCase):
    def run_block(self, repo: Path, setup_command: str) -> tuple[str, dict[str, str]]:
        body = (
            "set -euo pipefail\n"
            f'REPO="{repo.as_posix()}"\n'
            + timer_block(setup_command)
            + 'echo "S=${BENCHMARK_SEPARATE_SETUP_START_NS:-} E=${BENCHMARK_SEPARATE_SETUP_END_NS:-}"\n'
        )
        result = subprocess.run([BASH, "-c", body], capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        line = next(x for x in result.stdout.splitlines() if x.startswith("S="))
        env = dict(part.split("=", 1) for part in line.split())
        return result.stdout, env

    def test_reboot_then_resume_keeps_the_first_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "results").mkdir()
            start_file = repo / "results" / ".generation_setup.start"
            # 1. First run: setup.sh schedules the reboot and exits 0 without .setup_state.
            out, env = self.run_block(repo, "true")
            self.assertIn("a reboot is pending", out)
            self.assertNotIn("setup.sh took", out)
            self.assertEqual(env, {"S": "", "E": ""})
            self.assertTrue(start_file.is_file(), "the start file must survive until setup is complete")
            # The reboot and resume take time: move the saved start 330 s into the past.
            first = int(start_file.read_text(encoding="utf-8").strip()) - 330 * NS
            start_file.write_text(f"{first}\n", encoding="utf-8")
            # 2. Resumed run: setup completes and writes .setup_state.
            out, env = self.run_block(repo, 'touch "$REPO/.setup_state"')
            self.assertIn("keeping start", out)
            self.assertEqual(int(env["S"]), first)
            took = (int(env["E"]) - int(env["S"])) // NS
            self.assertGreaterEqual(took, 330)
            self.assertFalse(start_file.exists())
            # 3. The ledger counts that setup.sh time for the row of the smoke run.
            ledger = load("update_runtime_ledger")
            setup_ns = int(env["E"]) + NS
            cols = ledger.timing_columns(
                {
                    "BENCHMARK_SEPARATE_SETUP_START_NS": env["S"],
                    "BENCHMARK_SEPARATE_SETUP_END_NS": env["E"],
                    "BENCHMARK_SCRIPT_START_NS": str(setup_ns),
                    "BENCHMARK_SETUP_START_NS": str(setup_ns),
                    "BENCHMARK_START_NS": str(setup_ns + 6 * NS),
                    "BENCHMARK_MEASURE_STARTED": "1",
                },
                benchmark_start="x", benchmark_runtime="1", now_ns=setup_ns + 14 * NS,
            )
            minutes, seconds = (int(x) for x in cols["runtime_setup_mm_ss"].split(":"))
            self.assertGreaterEqual(minutes * 60 + seconds, 330)

    def test_completed_setup_finishes_at_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "results").mkdir()
            out, env = self.run_block(repo, 'touch "$REPO/.setup_state"')
            self.assertIn("setup.sh took", out)
            self.assertTrue(env["S"] and env["E"])
            self.assertFalse((repo / "results" / ".generation_setup.start").exists())

    def test_every_setup_writes_setup_state(self) -> None:
        for rel in ("scripts/templates/setup_cpu_system_skeleton.sh", "scripts/templates/setup_nvidia_skeleton.sh",
                    "scripts/templates/setup_rocm_reboot_skeleton.sh"):
            with self.subTest(rel=rel):
                self.assertIn(".setup_state", (ROOT / rel).read_text(encoding="utf-8"))


class PollingRuleTests(unittest.TestCase):
    def test_event_triggered_waits_allowed(self) -> None:
        for rel in ("docs/AI_AGENT_INSTRUCTIONS.md", ".cursor/rules/generate-workloads.mdc", "AGENTS.md"):
            with self.subTest(rel=rel):
                text = (ROOT / rel).read_text(encoding="utf-8")
                self.assertIn("[RECORD]", text)
                self.assertIn("[FAIL]", text)
                self.assertIn("120 seconds", text)
                self.assertNotIn("check its progress at most every 2 minutes", text)


if __name__ == "__main__":
    unittest.main()
