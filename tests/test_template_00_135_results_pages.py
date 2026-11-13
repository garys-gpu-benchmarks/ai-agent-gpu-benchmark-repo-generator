#!/usr/bin/env python3
# File: tests/test_template_00_135_results_pages.py
# Description: TEMPLATE_00_135 results pages. results/RESULTS_ACTUAL.md written by
#   update_runtime_ledger.py after every run (one section per profile, latest run);
#   RESULTS_REFERENCE.md made from it at generation (smoke) and by
#   user_scripts/promote_results_reference.sh (a passed baseline run); collection
#   by get_benchmark_results.sh; nothing private on the page. No network.
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
BASH = shutil.which("bash")
sys.path.insert(0, str(SCRIPTS))
import results_markdown as rm  # noqa: E402

FIELDS = {
    "Workload Number": "220",
    "Workload Name": "cuSOLVER FP64 Dense LU Solve (single GPU)",
    "Main Goal": "Measure sustained FP64 dense LU solve throughput with cuSOLVER on one GPU.",
    "Command Tools Executed": "Build src/nvhpl.cu with scripts/build.sh, then run bin/nvhpl",
}


def row(profile: str = "baseline", exit_code: str = "0", **extra: str) -> dict[str, str]:
    base = {
        "run_id": "220_20261112_085025", "benchmark_profile": profile, "result_status": "PASS" if exit_code == "0" else "FAIL",
        "exit_code": exit_code, "start_benchmark_datetime": "2026-11-12T08:50:25Z",
        "runtime_setup_mm_ss": "00:02", "runtime_benchmark_mm_ss": "01:28", "runtime_script_mm_ss": "01:36",
        "suite_id": "vm_20261112_085000", "gpu_name": "NVIDIA H100 80GB HBM3", "gpu_count": "1", "gpu_vram": "81559 MiB",
        "cpu_model": "Intel Xeon Platinum 8480+", "os_version": "Ubuntu 24.04.3 LTS", "kernel_version": "6.8.0-87-generic",
        "gpu_driver_version": "595.91.07", "hostname": "secret-host-name", "raw_run_dir": "/opt/benchmarks/x/results/raw/r1",
        "run_benchmark_command_fully_resolved": f"bash run_benchmark.sh --{profile} --problem-size-N 32768",
        "metric_1_def": "Mean cuSOLVER FP64 dense-LU throughput, TFLOPS (tflops)", "metric_1_result": "28.001",
        "metric_2_def": "Mean percent of FP64 tensor-core peak (percent_of_fp64_tensor_peak)", "metric_2_result": "46.422",
    }
    base.update(extra)
    return base


class PageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.repo, ignore_errors=True)

    def page(self) -> str:
        return (self.repo / "results" / "RESULTS_ACTUAL.md").read_text(encoding="utf-8")

    def test_section_contents_and_nothing_private(self) -> None:
        rm.update_results_actual(self.repo, FIELDS, row())
        text = self.page()
        self.assertIn("# Results: 220 cuSOLVER FP64 Dense LU Solve (single GPU)", text)
        self.assertIn("**Main goal:** Measure sustained FP64 dense LU solve throughput with cuSOLVER on one GPU  ", text)
        self.assertIn("1× NVIDIA H100 80GB HBM3 (81559 MiB) · Intel Xeon Platinum 8480+ · Ubuntu 24.04.3 LTS · "
                      "kernel 6.8.0-87-generic · driver 595.91.07", text)
        self.assertIn("status **PASS** (exit 0)", text)
        self.assertIn("setup 00:02 · benchmark 01:28 · whole run 01:36", text)
        self.assertIn("| 1 | Mean cuSOLVER FP64 dense-LU throughput, TFLOPS (tflops) | 28.001 |", text)
        self.assertNotIn("secret-host-name", text)
        self.assertNotIn("/opt/benchmarks", text)

    def test_latest_run_per_profile_in_order(self) -> None:
        rm.update_results_actual(self.repo, FIELDS, row("baseline", metric_1_result="27.0"))
        rm.update_results_actual(self.repo, FIELDS, row("smoke", metric_1_result="0.70"))
        rm.update_results_actual(self.repo, FIELDS, row("baseline", metric_1_result="28.001"))
        text = self.page()
        self.assertEqual(text.count("<!-- profile:baseline -->"), 1)
        self.assertLess(text.index("## smoke"), text.index("## baseline"))
        self.assertIn("| 28.001 |", text)
        self.assertNotIn("| 27.0 |", text)
        self.assertEqual(text.count("# Results:"), 1)

    def test_failed_run_shows_stage(self) -> None:
        rm.update_results_actual(self.repo, FIELDS, row("smoke", "1", failure_stage="setup",
                                                        failure_detail="apt-get update failed | mirror"))
        text = self.page()
        self.assertIn("status **FAIL** (exit 1)", text)
        self.assertIn("Failed at **setup**: apt-get update failed | mirror", text)

    def test_reference_from_smoke_has_note(self) -> None:
        rm.update_results_actual(self.repo, FIELDS, row("smoke"))
        ref = rm.reference_from_actual(self.page(), template_version="TEMPLATE_00_135", generated="2026-11-12",
                                       profiles=("smoke",))
        self.assertIn("(generator TEMPLATE_00_135 · recorded 2026-11-12)", ref)
        self.assertIn(rm.SMOKE_NOTE, ref)
        self.assertNotIn("Latest run of each profile", ref)

    def test_reference_keeps_only_passed_requested_profiles(self) -> None:
        rm.update_results_actual(self.repo, FIELDS, row("smoke"))
        rm.update_results_actual(self.repo, FIELDS, row("baseline"))
        rm.update_results_actual(self.repo, FIELDS, row("extended", "1"))
        ref = rm.reference_from_actual(self.page(), profiles=("baseline", "extended"), require_pass=True)
        self.assertIn("## baseline", ref)
        self.assertNotIn("## extended", ref)
        self.assertNotIn("## smoke", ref)
        self.assertNotIn(rm.SMOKE_NOTE, ref)
        with self.assertRaises(ValueError):
            rm.reference_from_actual(self.page(), profiles=("extended",), require_pass=True)

    def test_template_version_from_path(self) -> None:
        self.assertEqual(rm.template_version_from_path(Path("/z/P/Project494_x/TEMPLATE_00_135/ai-agent")), "TEMPLATE_00_135")
        self.assertEqual(rm.template_version_from_path(Path("/tmp/none")), "")


class LedgerWriterTests(unittest.TestCase):
    def test_every_run_refreshes_the_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            spec = [{"field_name": k, "value": v} for k, v in FIELDS.items()]
            spec.append({"field_name": "Metrics", "value": "#1: Mean cuSOLVER FP64 dense-LU throughput, TFLOPS (tflops)"})
            (repo / "benchmark_specification.json").write_text(json.dumps(spec), encoding="utf-8")
            (repo / "results").mkdir()
            (repo / "results" / "summary.json").write_text(json.dumps({"metrics": {"tflops": 28.001}}), encoding="utf-8")
            env = dict(os.environ, PATH=os.environ.get("PATH", ""))
            for key in ("BENCHMARK_SUITE_ID", "BENCHMARK_RESULTS_MD"):
                env.pop(key, None)
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "update_runtime_ledger.py"), "--definition", "benchmark_specification.json",
                 "--summary", "results/summary.json", "--profile", "baseline", "--start-datetime", "2026-11-12T08:50:25Z",
                 "--total-runtime", "87.5", "--exit-code", "0", "--ledger", str(repo / "ledger.csv"),
                 "--runtime-root", str(repo)],
                cwd=repo, env=env, capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            page = (repo / "results" / "RESULTS_ACTUAL.md").read_text(encoding="utf-8")
            self.assertIn("## baseline", page)
            self.assertIn("| 28.001 |", page)
            self.assertIn("Results page updated", result.stdout)
            env["BENCHMARK_RESULTS_MD"] = "0"
            (repo / "results" / "RESULTS_ACTUAL.md").unlink()
            subprocess.run(result.args, cwd=repo, env=env, capture_output=True, text=True, timeout=120)
            self.assertFalse((repo / "results" / "RESULTS_ACTUAL.md").exists())


class GenerationTests(unittest.TestCase):
    def load(self):
        spec = importlib.util.spec_from_file_location("create_one_workload_135", SCRIPTS / "create_one_workload.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_reference_written_from_vm_smoke_page(self) -> None:
        mod = self.load()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "220-gpu-bench-x"
            repo.mkdir()
            rm.update_results_actual(repo, FIELDS, row("smoke", metric_1_result="0.70"))
            text = (repo / "results" / "RESULTS_ACTUAL.md").read_text(encoding="utf-8")

            class Result:
                returncode = 0
                stdout = text
                stderr = ""

            calls: list[str] = []
            saved = mod.ssh_run
            mod.ssh_run = lambda _ssh, script, **_k: (calls.append(script), Result())[1]
            try:
                ok = mod.fetch_results_reference("ssh x@1.2.3.4", repo, Path(tmp) / "TEMPLATE_00_135" / "gen")
            finally:
                mod.ssh_run = saved
            self.assertTrue(ok)
            self.assertIn("/opt/benchmarks/220-gpu-bench-x/results/RESULTS_ACTUAL.md", calls[0])
            ref = (repo / "RESULTS_REFERENCE.md").read_text(encoding="utf-8")
            self.assertIn("generator TEMPLATE_00_135", ref)
            self.assertIn(rm.SMOKE_NOTE, ref)

    def test_called_only_after_a_pass(self) -> None:
        text = (SCRIPTS / "create_one_workload.py").read_text(encoding="utf-8")
        self.assertIn("if rc == 0 and ssh:\n            fetch_results_reference(ssh, repo, template_root)", text)

    def test_results_folder_stays_ignored_and_collected(self) -> None:
        collect = (ROOT / "user_scripts" / "get_benchmark_results.sh").read_text(encoding="utf-8")
        self.assertIn('paths+=("${d}/results/RESULTS_ACTUAL.md")', collect)


@unittest.skipIf(BASH is None, "bash is not installed")
class PromoteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repos = self.tmp / "TEMPLATE_00_135"
        self.collected = self.tmp / "collected"
        for name, rows in (("220-gpu-bench-a", [row("smoke"), row("baseline")]),
                           ("221-gpu-bench-b", [row("smoke"), row("baseline", "1")]),
                           ("222-gpu-bench-c", None)):
            repo = self.repos / name
            (repo / "scripts").mkdir(parents=True)
            shutil.copy(SCRIPTS / "results_markdown.py", repo / "scripts" / "results_markdown.py")
            (repo / "RESULTS_REFERENCE.md").write_text("old smoke page\n", encoding="utf-8")
            if rows:
                target = self.collected / "DIRECTORIES" / name
                for r in rows:
                    rm.update_results_actual(target, FIELDS, r)

    def promote(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run([BASH, str(ROOT / "user_scripts" / "promote_results_reference.sh"),
                               "--results", str(self.collected), "--repos", str(self.repos), *extra],
                              capture_output=True, text=True, timeout=120)

    def ref(self, name: str) -> str:
        return (self.repos / name / "RESULTS_REFERENCE.md").read_text(encoding="utf-8")

    def test_dry_run_writes_nothing(self) -> None:
        result = self.promote("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("would promote baseline", result.stdout)
        self.assertEqual(self.ref("220-gpu-bench-a"), "old smoke page\n")

    def test_promotes_only_passed_baseline(self) -> None:
        result = self.promote()
        self.assertEqual(result.returncode, 0, result.stderr)
        a = self.ref("220-gpu-bench-a")
        self.assertIn("## baseline", a)
        self.assertNotIn("## smoke", a)
        self.assertIn("generator TEMPLATE_00_135", a)
        self.assertEqual(self.ref("221-gpu-bench-b"), "old smoke page\n")
        self.assertEqual(self.ref("222-gpu-bench-c"), "old smoke page\n")
        self.assertIn("Promoted: 1   kept: 1", result.stdout)
        self.assertIn("not collected: 1", result.stdout)
        again = self.promote()
        self.assertIn("unchanged", again.stdout)

    def test_usage_errors(self) -> None:
        result = subprocess.run([BASH, str(ROOT / "user_scripts" / "promote_results_reference.sh"), "--repos", str(self.repos)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 2)
        self.assertIn("give --results DIR", result.stderr)
        self.assertEqual(self.promote("--profiles", "fast").returncode, 2)


if __name__ == "__main__":
    unittest.main()
