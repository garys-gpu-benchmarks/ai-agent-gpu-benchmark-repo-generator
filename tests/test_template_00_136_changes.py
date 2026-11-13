#!/usr/bin/env python3
# File: tests/test_template_00_136_changes.py
# Description: TEMPLATE_00_136. The agent instructions cap a wait on a running batch at
#   120 seconds; results/parsed/ is no longer created, required or collected; generation
#   setup time reaches the ledger; the preflight no longer says the bootstrap installs
#   CUDA; the collector notice warns only when a collector is really missing; host-limit
#   na values use "na (expected: ...)"; run_from_prompt.py adds the prompt's metadata.
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
NS = 1_000_000_000
T0 = 1_794_000_000 * NS


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_00_136", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS))
    try:
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


class PollingRuleTests(unittest.TestCase):
    def test_every_instruction_file_caps_the_wait(self) -> None:
        for rel in ("docs/AI_AGENT_INSTRUCTIONS.md", ".cursor/rules/generate-workloads.mdc", "AGENTS.md"):
            with self.subTest(rel=rel):
                text = (ROOT / rel).read_text(encoding="utf-8")
                self.assertIn("120 s", text)  # 120 seconds (TEMPLATE_00_138 wording)
                self.assertIn("Successful time", text)
                self.assertIn("[RECORD]", text)


class ScratchFileRuleTests(unittest.TestCase):
    def test_helper_scripts_go_to_tmp(self) -> None:
        for rel in ("docs/AI_AGENT_INSTRUCTIONS.md", ".cursor/rules/generate-workloads.mdc", "AGENTS.md"):
            with self.subTest(rel=rel):
                text = (ROOT / rel).read_text(encoding="utf-8")
                self.assertIn("go in `/tmp`", text)
                self.assertIn("deleted when", text)


class ParsedRemovedTests(unittest.TestCase):
    def test_no_generator_file_creates_or_requires_parsed(self) -> None:
        for rel in ("scripts/create_one_workload.py", "scripts/init_generated_repo.py", "scripts/text_io.py",
                    "scripts/self_check_generated_repo.sh", "scripts/smoke_check_generated_repo.sh",
                    "scripts/templates/setup_rocm_reboot_skeleton.sh", ".gitignore",
                    "user_scripts/get_benchmark_results.sh",
                    "templates/shared-workflows/.github/workflows/gpu-smoke.yml"):
            with self.subTest(rel=rel):
                self.assertNotIn("results/parsed", (ROOT / rel).read_text(encoding="utf-8"))

    def test_x30_run_summary_goes_into_the_run_folder(self) -> None:
        for comp in ("sglang-prompt-parser-amd", "sglang-prompt-response-nvidia"):
            text = (ROOT / "implementation_components" / comp / "files" / "scripts" / "parse_results.py").read_text(encoding="utf-8")
            self.assertIn('(run_dir / "run_summary.json")', text)
            self.assertNotIn('results_dir / "parsed"', text)


class GenerationSetupTimeTests(unittest.TestCase):
    """1. The setup.sh that generation runs before the smoke run counts as setup."""

    def setUp(self) -> None:
        self.ledger = load("update_runtime_ledger")

    def columns(self, **extra: str) -> dict[str, str]:
        env = {"BENCHMARK_SCRIPT_START_NS": str(T0 + 200 * NS), "BENCHMARK_SETUP_START_NS": str(T0 + 201 * NS),
               "BENCHMARK_START_NS": str(T0 + 202 * NS), "BENCHMARK_MEASURE_STARTED": "1", **extra}
        return self.ledger.timing_columns(env, benchmark_start="x", benchmark_runtime="3", now_ns=T0 + 210 * NS)

    def test_separate_setup_is_counted(self) -> None:
        cols = self.columns(BENCHMARK_SEPARATE_SETUP_START_NS=str(T0), BENCHMARK_SEPARATE_SETUP_END_NS=str(T0 + 160 * NS))
        self.assertEqual(cols["runtime_setup_mm_ss"], "02:41")  # 160 s of setup.sh + 1 s check
        self.assertEqual(cols["start_setup_datetime"], cols["start_script_datetime"])
        self.assertEqual(cols["runtime_script_mm_ss"], "03:30")
        self.assertEqual(cols["runtime_benchmark_mm_ss"], "00:03")

    def test_without_or_with_bad_separate_times(self) -> None:
        self.assertEqual(self.columns()["runtime_setup_mm_ss"], "00:01")
        bad = self.columns(BENCHMARK_SEPARATE_SETUP_START_NS=str(T0), BENCHMARK_SEPARATE_SETUP_END_NS=str(T0 + 999 * NS))
        self.assertEqual(bad["runtime_setup_mm_ss"], "00:01")

    def test_generation_script_times_setup_before_smoke(self) -> None:
        mod = load("create_one_workload")
        for resume in (False, True):
            script = mod._remote_script("101-x", resume=resume, stamp="s")
            start = script.index('> "$SETUP_T.start"')
            setup = script.index("bash setup.sh --assume-yes")
            end = script.index('date +%s%N > "$SETUP_T.end"')
            smoke = script.index("bash run_benchmark.sh --smoke")
            self.assertLess(start, setup)
            self.assertLess(setup, end)
            self.assertLess(end, smoke)
            self.assertIn("export BENCHMARK_SEPARATE_SETUP_START_NS BENCHMARK_SEPARATE_SETUP_END_NS", script)
            self.assertIn("21600000000000", script)  # 6 h age limit (TEMPLATE_00_137: no find -mmin)


class PreflightWordingTests(unittest.TestCase):
    """2. The bootstrap no longer installs CUDA or DCGM, and the preflight says so."""

    def test_no_bootstrap_install_claim(self) -> None:
        text = (SCRIPTS / "remote_host_preflight.py").read_text(encoding="utf-8")
        self.assertNotIn("host bootstrap installs", text)
        self.assertIn("first NVIDIA workload's setup.sh installs it", text)


class CollectorNoticeTests(unittest.TestCase):
    """3. Warn only when a collector is really missing."""

    def setUp(self) -> None:
        self.mod = load("materialize_generated_harness")
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "scripts").mkdir()

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_three_cases(self) -> None:
        runner = self.tmp / "run_benchmark.sh"
        runner.write_text("python3 scripts/infer_sdxl.py\n", encoding="utf-8")
        self.assertTrue(self.mod.collector_notice(self.tmp).startswith("[INFO] run_benchmark.sh does not call"))
        runner.write_text("python3 scripts/collect_workload.py\n", encoding="utf-8")
        (self.tmp / "scripts" / "collect_resnet50_infer.py").write_text("x", encoding="utf-8")
        self.assertIn("adapter to collect_resnet50_infer.py", self.mod.collector_notice(self.tmp))
        (self.tmp / "scripts" / "collect_resnet50_infer.py").unlink()
        self.assertTrue(self.mod.collector_notice(self.tmp).startswith("[WARN]"))
        (self.tmp / "scripts" / "collect_workload.py").write_text("x", encoding="utf-8")
        self.assertEqual(self.mod.collector_notice(self.tmp), "")


class ExpectedNaWordingTests(unittest.TestCase):
    """4. Host-limit na values use the rule's form, na (expected: <reason>)."""

    CASES = {
        "multichase-numa-amd/files/scripts/collect_multichase.py": ('"na (expected: needs a second NUMA node)"', '"na (requires a second NUMA node)"'),
        "gups-amd/files/scripts/collect_workload.py": ('"na (expected: LLC load counters not exposed on this host)"', '"na (LLC load counters unavailable)"'),
        "rccl-bandwidth-amd/files/scripts/collect_workload.py": ('NA_SINGLE_GPU = "na (expected: needs at least two GPUs)"', '"na (requires at least two GPUs)"'),
        "nccl-bandwidth-nvidia/files/scripts/collect_workload.py": ('NA_SINGLE_GPU = "na (expected: needs at least two GPUs)"', '"na (requires at least two GPUs)"'),
        "linux-perf-pmu-amd/files/scripts/collect_workload.py": ('"na (expected: PMU access denied, perf_event_paranoid=', '"na (PMU access denied'),
        "linux-perf-pmu-nvidia/files/scripts/collect_workload.py": ('"na (expected: PMU access denied, perf_event_paranoid=', '"na (PMU access denied'),
    }

    def test_collectors(self) -> None:
        for rel, (new, old) in self.CASES.items():
            with self.subTest(rel=rel):
                text = (ROOT / "implementation_components" / rel).read_text(encoding="utf-8")
                self.assertIn(new, text)
                self.assertNotIn(old, text)

    def test_classifier_unchanged_and_accepts_both(self) -> None:
        contract = load("metric_contract")
        for value in ("na (expected: needs at least two GPUs)", "na (requires at least two GPUs)"):
            self.assertEqual(contract.classify_na("allreduce_busbw_gb_s", value, {"gpu_count": 1}), "expected", value)


class PromptMetadataTests(unittest.TestCase):
    """5. run_from_prompt.py adds the traceability comment when the agent did not."""

    def test_added_once_and_never_to_a_key(self) -> None:
        workflow = load("prompt_workflow")
        with tempfile.TemporaryDirectory() as tmp:
            prompt = Path(tmp) / "AI_AGENT_PROMPT_SUBMITTED_101to132_x.md"
            prompt.write_text("Generate workloads 101 through 132.\nssh -i k root@203.0.113.9\n", encoding="utf-8")
            self.assertTrue(workflow.ensure_prompt_metadata(prompt, ["101", "102"], "TEMPLATE_00_136"))
            text = prompt.read_text(encoding="utf-8")
            self.assertIn("<!-- Generation metadata", text)
            self.assertIn("template_version: TEMPLATE_00_136", text)
            self.assertIn("remote_validation_status: supplied-for-validation", text)
            self.assertFalse(workflow.ensure_prompt_metadata(prompt, ["101"], "x"))
            self.assertEqual(prompt.read_text(encoding="utf-8").count("Generation metadata"), 1)
            key = Path(tmp) / "k.md"
            key.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\n", encoding="utf-8")
            self.assertFalse(workflow.ensure_prompt_metadata(key, ["101"], "x"))

    def test_run_from_prompt_calls_it(self) -> None:
        text = (SCRIPTS / "run_from_prompt.py").read_text(encoding="utf-8")
        self.assertIn("ensure_prompt_metadata(prompt, workloads, version)", text)


if __name__ == "__main__":
    unittest.main()
