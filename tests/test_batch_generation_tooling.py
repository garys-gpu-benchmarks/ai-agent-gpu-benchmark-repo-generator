#!/usr/bin/env python3
# File: tests/test_batch_generation_tooling.py
# Description: Batch-driver behavior added 2026-10-19: every attempt kept in the batch
# manifest with both totals, the generator repair log, the start command printed by
# preflight, _copy left out of the remote copy, CR rewrite only for files with CR,
# interpreter caches removed, and the resumable SDXL prefetch.
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.dont_write_bytecode = True
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import create_one_workload as col  # noqa: E402
import generation_host_preflight as preflight  # noqa: E402
import log_generator_repair as repairs  # noqa: E402
import run_from_prompt as rfp  # noqa: E402


class AttemptHistory(unittest.TestCase):
    def test_retry_keeps_failed_attempt_and_both_totals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch("builtins.print"):
                col.record(root, "130", "x", "failed", "2026-10-19T00:00:00Z", "2026-10-19T00:30:00Z", "remote rc=1", 1)
                col.record(root, "130", "x", "passed", "2026-10-19T01:00:00Z", "2026-10-19T01:10:00Z", "", 0)
                col.record(root, "131", "y", "passed", "2026-10-19T02:00:00Z", "2026-10-19T02:05:00Z", "", 0)
            batch = json.loads((root / "batch_generation_manifest.json").read_text(encoding="utf-8"))
            row = next(r for r in batch["repositories"] if r["workload"] == "130")
            self.assertEqual(row["status"], "passed")
            self.assertEqual(row["attempt_count"], 2)
            self.assertEqual([a["status"] for a in row["attempts"]], ["failed", "passed"])
            self.assertEqual(row["attempts"][0]["reason"], "remote rc=1")
            successful, everything, failed = rfp.batch_times(batch, ["130", "131"])
            self.assertEqual(successful, 15 * 60)
            self.assertEqual(everything, 45 * 60)
            self.assertEqual(failed, 1)

    def test_old_entry_without_attempts_becomes_first_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = {"repositories": [{"workload": "124", "status": "failed", "return_code": 1,
                                     "create_start_time": "2026-10-19T00:00:00Z",
                                     "create_end_time": "2026-10-19T00:57:00Z", "create_total_time": "57m"}]}
            (root / "batch_generation_manifest.json").write_text(json.dumps(old), encoding="utf-8")
            with mock.patch("builtins.print"):
                col.record(root, "124", "z", "passed", "2026-10-19T01:00:00Z", "2026-10-19T01:20:00Z", "", 0)
            batch = json.loads((root / "batch_generation_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(batch["repositories"][0]["attempt_count"], 2)
            self.assertEqual(rfp.batch_times(batch, ["124"]), (20 * 60, 77 * 60, 1))

    def test_summary_prints_both_times(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch("builtins.print"):
                col.record(root, "101", "a", "failed", "2026-10-19T00:00:00Z", "2026-10-19T00:01:00Z", "x", 1)
                col.record(root, "101", "a", "passed", "2026-10-19T00:02:00Z", "2026-10-19T00:04:00Z", "", 0)
            with mock.patch("builtins.print") as printed:
                rfp.print_batch_summary(root, ["101"])
            text = "\n".join(str(call.args[0]) for call in printed.call_args_list if call.args)
            self.assertIn("Successful time: 0h 02m 00s (120 sec)", text)
            self.assertIn("Time including failed attempts: 0h 03m 00s (180 sec; 1 failed attempt(s))", text)
            self.assertIn("| 101 | passed | 2 |", text)
            batch = json.loads((root / "batch_generation_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(batch["generation_successful_seconds"], 120)
            self.assertEqual(batch["generation_seconds_including_failed_attempts"], 180)


class RepairLog(unittest.TestCase):
    def test_append_and_batch_slice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repairs.append_entry(root, "implementation_components/a/files/x.py", "first", "101")
            before = len(repairs.read_entries(root))
            repairs.append_entry(root, "scripts\\metric_contract.py", "two\nlines", "102")
            entries = repairs.read_entries(root)
            self.assertEqual(len(entries), 2)
            self.assertIn("| 102 | scripts/metric_contract.py | two lines", entries[1])
            with mock.patch("builtins.print") as printed:
                rfp.print_generator_repairs(root, before)
            text = "\n".join(str(call.args[0]) for call in printed.call_args_list if call.args)
            self.assertIn("Generator repairs during this batch (1)", text)
            self.assertNotIn("first", text)
            with mock.patch("builtins.print") as printed:
                rfp.print_generator_repairs(root, len(entries))
            self.assertIn("none", str(printed.call_args_list[-1].args[0]))

    def test_rule_is_documented(self) -> None:
        for rel in ("AGENTS.md", "docs/AI_AGENT_INSTRUCTIONS.md", ".cursor/rules/generate-workloads.mdc"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("log_generator_repair.py", text, rel)
            self.assertIn("na (expected: <reason>)", text, rel)

    def test_results_folder_is_ignored(self) -> None:
        self.assertIn("results/", (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines())


class StartCommand(unittest.TestCase):
    EXACT = "MSYS_NO_PATHCONV=1 python3 scripts/run_from_prompt.py --prompt-file ../AI_AGENT_PROMPT_SUBMITTED_<WORKLOADS>_<UTC_TIMESTAMP>.md"

    def test_documents_carry_one_exact_command(self) -> None:
        for rel in ("AGENTS.md", "docs/AI_AGENT_INSTRUCTIONS.md", "docs/generation-workflow.md",
                    ".cursor/rules/generate-workloads.mdc"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn(self.EXACT, text, rel)
            self.assertNotIn("python3 scripts/run_from_prompt.py --prompt-file <SUBMITTED_PROMPT_FILE>", text, rel)

    def test_preflight_command_uses_this_python_and_relative_prompt(self) -> None:
        command = preflight.start_command(str(ROOT.parent / "AI_AGENT_PROMPT_SUBMITTED_101_X.md"))
        self.assertTrue(command.startswith("MSYS_NO_PATHCONV=1 "))
        self.assertIn("scripts/run_from_prompt.py --prompt-file ../AI_AGENT_PROMPT_SUBMITTED_101_X.md", command)
        self.assertIn(Path(sys.executable).name, command)

    def test_preflight_prints_command_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "generation_host_preflight.py"), "--template-root", tmp],
                capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"), check=False,
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("start generation from the generator directory with exactly:", result.stdout)
        self.assertIn("MSYS_NO_PATHCONV=1 ", result.stdout)


class RemoteCopy(unittest.TestCase):
    def test_template_copy_is_included_for_remote_self_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "124-x"
            (repo / "TEMPLATE_00_113_copy").mkdir(parents=True)
            (repo / "scripts").mkdir()
            self.assertEqual(col._copy_excludes(repo, prefix="./"), "")
            self.assertEqual(col._copy_excludes(repo, prefix="124-x/"), "")

    def test_cr_rewrite_touches_only_files_with_cr(self) -> None:
        script = col._remote_script("R", resume=False, stamp="s")
        line = next(item for item in script.splitlines() if "grep -lZ" in item)
        self.assertIn("export PYTHONDONTWRITEBYTECODE=1", script)
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "R"
            (repo / "a").mkdir(parents=True)
            crlf = repo / "a" / "w.sh"
            lf = repo / "b.py"
            crlf.write_bytes(b"x\r\ny\r\n")
            lf.write_bytes(b"ok\n")
            os.utime(lf, (1_000_000_000, 1_000_000_000))
            for _ in range(2):  # the second pass finds nothing and must still succeed
                result = subprocess.run(["bash", "-c", f"set -euo pipefail\nREPO={repo}\n{line}"],
                                        capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(crlf.read_bytes(), b"x\ny\n")
            self.assertEqual(int(lf.stat().st_mtime), 1_000_000_000)


class RebootResume(unittest.TestCase):
    """2026-10-20, workload 301: after the amdgpu reboot the resume service was still
    inside setup.sh, and the driver exited instead of waiting for it."""

    def test_resume_waits_for_the_running_setup(self) -> None:
        script = col._remote_script("R", resume=True, stamp="s")
        self.assertIn("setup.sh already running after reboot; waiting for it to finish", script)
        self.assertNotIn("not starting a second copy", script)
        self.assertIn("bash setup.sh --assume-yes --resume-auto || bash setup.sh --assume-yes", script)

    def test_first_run_still_refuses_a_second_setup(self) -> None:
        script = col._remote_script("R", resume=False, stamp="s")
        self.assertIn("not starting a second copy", script)
        self.assertNotIn("waiting for it to finish", script)


class GenerationTimes(unittest.TestCase):
    def test_stamp_writes_report_and_manifest(self) -> None:
        """Per-workload generation_manifest.json kept the initializer times (duration 0)."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "results").mkdir()
            (repo / "GENERATION_REPORT.md").write_text(
                "x\n- generation_started_at: a\n- generation_finished_at: a\n- generation_duration_seconds: 0\n",
                encoding="utf-8",
            )
            manifest = repo / "results" / "generation_manifest.json"
            manifest.write_text(json.dumps({"generation_started_at": "a", "generation_duration_seconds": 0, "keep": 1}),
                                encoding="utf-8")
            col._stamp_generation_report(repo, "2026-10-20T09:00:00Z", "2026-10-20T09:00:42Z")
            data = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(data["generation_duration_seconds"], 42)
            self.assertEqual(data["generation_finished_at"], "2026-10-20T09:00:42Z")
            self.assertEqual(data["keep"], 1)
            self.assertIn("- generation_duration_seconds: 42", (repo / "GENERATION_REPORT.md").read_text(encoding="utf-8"))


class SelfCheckOnTheVm(unittest.TestCase):
    """2026-10-20: leaving *_copy off the VM made self_check fail after a passing smoke
    on x01-x03 of every batch. The copy goes to the VM again, and self_check keeps its
    one rule (the copy, or template_copy_removed_at)."""

    def test_remote_archive_keeps_the_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "101-x"
            (repo / "ai-agent-gpu-benchmark-repo-generator_copy").mkdir(parents=True)
            self.assertEqual(col._copy_excludes(repo, prefix="101-x/"), "")

    def test_self_check_has_no_host_exception(self) -> None:
        text = (SCRIPTS / "self_check_generated_repo.sh").read_text(encoding="utf-8")
        for name in ("BENCHMARK_VALIDATION_HOST", "BENCHMARK_REMOTE_VALIDATION", "/opt/benchmarks/*)"):
            self.assertNotIn(name, text)
        self.assertIn("does not record template_copy_removed_at", text)


class InterpreterCaches(unittest.TestCase):
    def test_removes_caches_but_not_venv_or_model_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel in ("scripts/__pycache__", "tests/.pytest_cache", ".ruff_cache",
                        ".venv/lib/__pycache__", ".cache/huggingface/__pycache__"):
                (root / rel).mkdir(parents=True)
            self.assertEqual(rfp.remove_interpreter_caches([root]), 3)
            self.assertFalse((root / "scripts/__pycache__").exists())
            self.assertTrue((root / ".venv/lib/__pycache__").exists())
            self.assertTrue((root / ".cache/huggingface/__pycache__").exists())

    def test_children_run_without_bytecode(self) -> None:
        text = (SCRIPTS / "run_from_prompt.py").read_text(encoding="utf-8")
        self.assertIn('env["PYTHONDONTWRITEBYTECODE"] = "1"', text)


class SdxlPrefetch(unittest.TestCase):
    def test_resumable_with_limit_and_retry(self) -> None:
        for vendor in ("amd", "nvidia"):
            path = ROOT / "implementation_components" / f"sdxl-diffusers-{vendor}" / "files" / "scripts" / "install_sdxl_python.sh"
            text = path.read_text(encoding="utf-8")
            self.assertIn('timeout -k 30 "${PREFETCH_TIMEOUT_SEC}"', text, vendor)
            self.assertIn('SDXL_PREFETCH_ATTEMPTS:-2', text, vendor)
            self.assertIn("HF_HUB_DOWNLOAD_TIMEOUT", text, vendor)
            self.assertNotIn("force_download", text.replace("Never force_download", ""), vendor)
            run = (path.parents[1] / "run_benchmark.sh").read_text(encoding="utf-8")
            self.assertIn("bash scripts/install_sdxl_python.sh --prefetch", run, vendor)


if __name__ == "__main__":
    unittest.main()
