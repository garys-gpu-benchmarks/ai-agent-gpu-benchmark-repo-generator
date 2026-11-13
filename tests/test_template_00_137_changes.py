#!/usr/bin/env python3
# File: tests/test_template_00_137_changes.py
# Description: TEMPLATE_00_137 fixes from the TEMPLATE_00_136 Opus 5.5 batch reviews.
#   1. The generation setup timer keeps its start across a reboot (bash arithmetic,
#      no `find -mmin`) and logs each decision.
#   2. One traceability comment in the saved prompt: the agent saves only the chat text,
#      and run_from_prompt.py skips a prompt that already has a comment.
#   4. The collector notice names the adapter first.
#   5. A bare "perf" no longer matches "iPerf3".
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


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_00_137", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS))
    try:
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def timer_block(setup_command: str) -> str:
    """The setup-timer lines of the generation script, with setup.sh replaced."""
    script = load("create_one_workload")._remote_script("301-x", resume=True, stamp="s")
    start = script.index('SETUP_T="$REPO/results/.generation_setup"')
    # TEMPLATE_00_138 wraps the finish in "if [ -f .setup_state ] ... fi".
    end = script.index("\nfi\n", script.index("keeping start $(cat")) + len("\nfi\n")
    block = script[start:end]
    setup_line = "bash setup.sh --assume-yes --resume-auto || bash setup.sh --assume-yes"
    assert setup_line in block
    return block.replace(setup_line, setup_command)


@unittest.skipIf(BASH is None, "bash is not installed")
class SetupTimerTests(unittest.TestCase):
    def run_block(self, repo: Path, saved: str | None) -> tuple[str, int, int]:
        (repo / "results").mkdir(parents=True, exist_ok=True)
        start_file = repo / "results" / ".generation_setup.start"
        if saved is not None:
            start_file.write_text(saved + "\n", encoding="utf-8")
        body = (
            "set -euo pipefail\n"
            f'REPO="{repo.as_posix()}"\n'
            + timer_block('sleep 1; touch "$REPO/.setup_state"')
            + '\necho "S=$BENCHMARK_SEPARATE_SETUP_START_NS E=$BENCHMARK_SEPARATE_SETUP_END_NS"\n'
        )
        result = subprocess.run([BASH, "-c", body], capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        line = next(x for x in result.stdout.splitlines() if x.startswith("S="))
        s, e = (int(part.split("=", 1)[1]) for part in line.split())
        self.assertFalse(start_file.exists(), "the start file is removed after the run")
        return result.stdout, s, e

    def test_start_from_before_a_reboot_is_kept(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            now = int(subprocess.run(["date", "+%s%N"], capture_output=True, text=True, check=True).stdout)
            saved = str(now - 330 * 1_000_000_000)  # setup began 5.5 min ago, before the reboot
            out, s, e = self.run_block(Path(tmp), saved)
            self.assertEqual(s, int(saved))
            self.assertGreaterEqual((e - s) // 1_000_000_000, 330)
            self.assertIn("keeping start", out)
            self.assertIn("setup.sh took 3", out)

    def test_missing_or_stale_start_is_replaced(self) -> None:
        for saved in (None, "123", "garbage"):
            with self.subTest(saved=saved), tempfile.TemporaryDirectory() as tmp:
                out, s, e = self.run_block(Path(tmp), saved)
                self.assertNotEqual(str(s), saved)
                self.assertLess((e - s) // 1_000_000_000, 5)
                self.assertIn("generation setup timer: start", out)

    def test_no_find_mmin(self) -> None:
        self.assertNotIn("-mmin", timer_block("true"))


class PromptMetadataTests(unittest.TestCase):
    def test_agent_saves_chat_text_only(self) -> None:
        text = (ROOT / "docs" / "AI_AGENT_INSTRUCTIONS.md").read_text(encoding="utf-8")
        self.assertNotIn("Append traceability metadata as an HTML comment", text)
        self.assertIn("appends the traceability comment itself", text)

    def test_existing_agent_comment_is_respected(self) -> None:
        workflow = load("prompt_workflow")
        with tempfile.TemporaryDirectory() as tmp:
            prompt = Path(tmp) / "AI_AGENT_PROMPT_SUBMITTED_301to332_x.md"
            prompt.write_text("Generate workloads 301 through 332.\n\n<!-- traceability: agent -->\n", encoding="utf-8")
            self.assertFalse(workflow.ensure_prompt_metadata(prompt, ["301"], "TEMPLATE_00_137"))
            self.assertNotIn("Generation metadata", prompt.read_text(encoding="utf-8"))


class CollectorNoticeOrderTests(unittest.TestCase):
    def test_named_collector_wins_over_runner_check(self) -> None:
        mod = load("materialize_generated_harness")
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "scripts").mkdir()
            (repo / "run_benchmark.sh").write_text("python3 scripts/infer_sdxl.py\n", encoding="utf-8")
            (repo / "scripts" / "collect_sdxl.py").write_text("x", encoding="utf-8")
            self.assertIn("adapter to collect_sdxl.py", mod.collector_notice(repo))
            (repo / "scripts" / "collect_sdxl.py").unlink()
            self.assertIn("no collector adapter needed", mod.collector_notice(repo))


class PerfRuleTests(unittest.TestCase):
    def test_iperf3_does_not_install_perf(self) -> None:
        registry = load("framework_registry")
        for vendor in ("cpu", "nvidia", "amd"):
            with self.subTest(vendor=vendor):
                flags = registry.resolve_flags("Bash, SQLite, Python, PyYAML, iPerf3", vendor=vendor, workload_name="UDP Sweep")
                self.assertEqual(flags.get("BENCHMARK_INSTALL_PERF"), 0)
                self.assertEqual(flags.get("BENCHMARK_INSTALL_IPERF"), 1)
                for framework in ("Bash, Linux perf, stress-ng", "Bash, Linux PMU, stress-ng"):
                    on = registry.resolve_flags(framework, vendor=vendor, workload_name="Linux perf PMU Analysis Harness")
                    self.assertEqual(on.get("BENCHMARK_INSTALL_PERF"), 1, framework)


if __name__ == "__main__":
    unittest.main()
