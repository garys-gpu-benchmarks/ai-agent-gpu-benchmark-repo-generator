#!/usr/bin/env python3
"""Fixes from the 2026-11-06 review of the 96-run VM suites (AMD and NVIDIA)."""
from __future__ import annotations

import csv
import glob
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which("bash")
RUNNERS = sorted(glob.glob(str(ROOT / "implementation_components" / "*" / "files" / "run_benchmark.sh")))


def _ledger():
    spec = importlib.util.spec_from_file_location("ledger_vm_review", ROOT / "scripts" / "update_runtime_ledger.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipIf(BASH is None, "bash is not installed")
class ProfilesInOrderTests(unittest.TestCase):
    def run_fake(self, *args: str, fail_baseline: bool = False) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "fake.sh"
            script.write_text(
                "set -euo pipefail\n"
                f'source "{ROOT}/scripts/lib/common.sh"\n'
                'run_profiles_in_order "$0" "$@"\n'
                'echo "child: $*"\n'
                '[[ " $* " == *" --baseline "* && "${FAIL_BASELINE:-0}" == 1 ]] && exit 7\n'
                "exit 0\n",
                encoding="utf-8",
            )
            env = dict(os.environ, FAIL_BASELINE="1" if fail_baseline else "0")
            return subprocess.run([BASH, str(script), *args], capture_output=True, text=True, env=env, timeout=30)

    def test_each_profile_runs_in_the_order_given_with_the_other_options(self) -> None:
        out = self.run_fake("--smoke", "--baseline", "--extended", "--num-threads", "8")
        self.assertEqual(out.returncode, 0, out.stderr)
        children = [line for line in out.stdout.splitlines() if line.startswith("child:")]
        self.assertEqual(children, [
            "child: --smoke --num-threads 8",
            "child: --baseline --num-threads 8",
            "child: --extended --num-threads 8",
        ])
        self.assertIn("[INFO] Profiles: smoke ok, baseline ok, extended ok", out.stdout)

    def test_a_failed_profile_does_not_stop_the_rest(self) -> None:
        out = self.run_fake("--baseline", "--extended", fail_baseline=True)
        self.assertEqual(out.returncode, 7)
        self.assertIn("child: --extended", out.stdout)
        self.assertIn("baseline FAILED (exit 7), extended ok", out.stdout)

    def test_one_profile_is_unchanged(self) -> None:
        out = self.run_fake("--baseline", "--num-threads", "4")
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout.strip(), "child: --baseline --num-threads 4")

    def test_every_runner_calls_the_helper_after_help(self) -> None:
        template = (ROOT / "scripts" / "materialize_generated_harness.py").read_text(encoding="utf-8")
        self.assertIn('run_profiles_in_order "${{REPO_ROOT}}/run_benchmark.sh" "$@"', template)
        for runner in RUNNERS:
            text = Path(runner).read_text(encoding="utf-8")
            with self.subTest(runner=runner):
                call = text.index('run_profiles_in_order "${REPO_ROOT}/run_benchmark.sh" "$@"')
                self.assertGreater(call, text.index('for _help_arg in "$@"'))
                self.assertLess(call, text.index('while [[ $# -gt 0 ]]', call))  # before option parsing


class IterationNoteTests(unittest.TestCase):
    def write(self, rows: list[dict]) -> str:
        tmp = tempfile.mkdtemp()
        with (Path(tmp) / "raw_results.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        return tmp

    def test_short_run_is_noted(self) -> None:
        run_dir = self.write([{"requested_iterations": "2630000", "completed_iterations": "206272"}])
        self.assertEqual(
            _ledger().iteration_note(run_dir),
            "completed 206272 of 2630000 requested iterations (stopped at the profile time limit)",
        )

    def test_full_run_and_other_workloads_get_no_note(self) -> None:
        ledger = _ledger()
        self.assertEqual(ledger.iteration_note(self.write([{"requested_iterations": "5", "completed_iterations": "5"}])), "")
        self.assertEqual(ledger.iteration_note(self.write([{"status": "ok", "value": "1"}])), "")
        self.assertEqual(ledger.iteration_note(None), "")


class ComponentFixTests(unittest.TestCase):
    def text(self, rel: str) -> str:
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_banner_reads_rocm_10_install(self) -> None:
        banner = self.text("scripts/print_run_metadata.sh")
        self.assertIn("rocm_install_version", banner)
        self.assertIn("/opt/rocm/core-*/.info/version", banner)
        self.assertIn("amdrocm-base*", banner)
        self.assertNotIn("dpkg-query -W -f='${Version}' rocm-core", banner)

    def test_first_venv_is_not_called_incomplete(self) -> None:
        setup = self.text("scripts/templates/setup_rocm_reboot_skeleton.sh")
        self.assertIn('echo "[INFO] Creating Python venv: ${VENV_ROOT}"', setup)

    def test_vllm_amd_warns_without_aiter_and_does_not_fail(self) -> None:
        setup = self.text("scripts/templates/setup_rocm_reboot_skeleton.sh")
        self.assertIn('pip install --no-deps "amd-aiter==${AITER_VERSION}"', setup)
        self.assertIn("amd-aiter missing; vLLM runs without AITER kernels (not fatal)", setup)
        for name in ("vllm-kvcache-amd", "vllm-throughput-amd", "vllm-token-generation-amd"):
            with self.subTest(component=name):
                self.assertIn("amd-aiter is not installed; vLLM runs without its AITER kernels",
                              self.text(f"implementation_components/{name}/files/run_benchmark.sh"))

    def test_single_gpu_collectives_skip_the_sweep(self) -> None:
        self.assertIn("one GPU requested: one quick RCCL check, no size sweep",
                      self.text("implementation_components/rccl-bandwidth-amd/files/scripts/collect_workload.py"))
        self.assertIn("one GPU requested: one quick NCCL check, no size sweep",
                      self.text("implementation_components/nccl-bandwidth-nvidia/files/scripts/collect_workload.py"))

    def test_runners_do_not_read_an_unset_raw_file(self) -> None:
        # 224/230/424/430 smoke stopped under set -u (Project436/438 generator_repairs.md).
        for runner in RUNNERS:
            with self.subTest(runner=runner):
                self.assertNotIn('if [[ -z "${RAW_FILE}" ]]', Path(runner).read_text(encoding="utf-8"))

    def test_rag_retrieval_is_labelled_cpu(self) -> None:
        for vendor in ("amd", "nvidia"):
            with self.subTest(vendor=vendor):
                self.assertIn("FAISS retrieval runs on the CPU (IndexFlatIP)",
                              self.text(f"implementation_components/rag-faiss-end2end-{vendor}/files/scripts/gpu-bench-rag-faiss-end2end.py"))


if __name__ == "__main__":
    unittest.main()
