#!/usr/bin/env python3
# File: tests/test_template_00_130_docs.py
# Description: TEMPLATE_00_130 checks that the agent-facing documents describe
# the code: real SDXL on every profile, the 220/420 tensor-core peak, current
# NVIDIA SGLang pins, the MI300X HBM figure, x28/x29 bfloat16 on all four
# platforms, seven Execution Domain values, -ubu2404 repository names, and the
# 2xx workbook CUDA runtime text (column BC) against the installed toolkit, and
# the per-run Hugging Face download-speed row (113.1) in the HW/SW inventory,
# and the renamed GPU Runtime Version / BLAS Version headers with their aliases.
# Only documents that state rules are checked; the CHANGELOGs keep old wording
# as history.
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "implementation_components"
RULE_DOCS = (
    "AGENTS.md",
    "README.md",
    "docs/SUBMISSION_CHECKLIST.md",
    "docs/generation-workflow.md",
    "docs/SIBLING_WORKLOAD_NOTES.md",
    "docs/nvidia-sglang-install-contract.md",
    "docs/nvidia-pytorch-install-contract.md",
    "docs/GITHUB_PUBLISH_GENERATOR_OPERATIONS.md",
    "docs/TEMPLATE_README.md",
    "docs/runpod-getting-started.md",
    "docs/github-profile-README.md",
)
STALE = (
    "tiny Euler denoiser",
    "Smoke may use the tiny denoiser",
    "must not download weights",
    "vector peak rather than tensor-core peak",
    "vLLM 0.26",
    "HBM bandwidth 192 GB/s",
    "torch==2.9.1+cu130",
    "torch 2.9.1+cu130",
    "sglang-kernel==0.4.1",
    "keeps the 230/231 recipe",
    "113-sys-bench-gups-random-memory",
    "128_gpu-bench-amd-vllm-throughput-latency",
    "(x29 and x32)",
    "(x23–x31)",
    "`scripts/publish_benchmarks_to_github.sh` copies",
    "one of the six values",
)


def text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


class StaleWordingTests(unittest.TestCase):
    def test_rule_documents_have_no_stale_wording(self) -> None:
        for rel in RULE_DOCS:
            body = text(rel)
            for phrase in STALE:
                self.assertNotIn(phrase, body, f"{rel}: {phrase}")


class DocsMatchCodeTests(unittest.TestCase):
    def test_sdxl_every_profile_is_real(self) -> None:
        for vendor in ("amd", "nvidia"):
            runner = (COMPONENTS / f"sdxl-diffusers-{vendor}/files/run_benchmark.sh").read_text(encoding="utf-8")
            self.assertIn('BACKEND="sdxl"', runner)
            self.assertIn("install_sdxl_python.sh --prefetch", runner)
        self.assertIn("load real SDXL on every profile, smoke included", text("AGENTS.md"))

    def test_x20_nvidia_peak_is_tensor_core(self) -> None:
        collector = (COMPONENTS / "linpack-hpl-nvidia/files/scripts/collect_workload.py").read_text(encoding="utf-8")
        self.assertIn("percent_of_fp64_tensor_peak", collector)
        self.assertIn("FP64 tensor-core peak that `nvhpl` prints", text("AGENTS.md"))

    def test_x20_amd_repeat_caps_are_documented(self) -> None:
        collector = (COMPONENTS / "linpack-rochpl-amd/files/scripts/collect_workload.py").read_text(encoding="utf-8")
        self.assertIn("return max(2, min(requested, 6))", collector)
        self.assertIn("return max(2, min(requested, 16))", collector)
        self.assertIn("return max(2, min(requested, 4))", collector)
        agents = text("AGENTS.md")
        self.assertIn("`timed_repeats()`", agents)
        self.assertIn("so a smoke request of 1 runs 2", agents)

    def test_nvidia_sglang_pins_match_the_helper(self) -> None:
        helper = (COMPONENTS / "sglang-prompt-response-nvidia/files/scripts/install_sglang_nvidia.sh").read_text(encoding="utf-8")
        contract = text("docs/nvidia-sglang-install-contract.md")
        for pin in ("torch==2.13.0+cu130", "torchvision==0.28.0+cu130", "torchaudio==2.11.0+cu130",
                    "sglang==0.5.10.post1", "sglang==0.5.19", "sglang-kernel==0.4.6.post1"):
            self.assertIn(pin, helper, pin)
            self.assertIn(pin, contract, pin)
        self.assertNotIn("torchaudio==2.13.0+cu130", contract)

    def test_mi300x_hbm_example_uses_the_profile(self) -> None:
        profile = (ROOT / "config/hardware_profile.mi300x.yaml").read_text(encoding="utf-8")
        peak = re.search(r"^peak_hbm_bandwidth_gbps:\s*(\d+)", profile, re.M).group(1)
        self.assertIn(f"MI300X HBM peak {peak} GB/s", text("AGENTS.md"))

    def test_execution_domains_match_the_schema(self) -> None:
        schema = json.loads((ROOT / "schemas/benchmark_specification.schema.json").read_text(encoding="utf-8"))
        found = re.findall(r'"(GPU Compute / (?:ROCm|CUDA)|LLM Serving|Memory / Transfer|CPU / System|'
                           r'End-to-End Pipeline|Validation / Correctness)"', json.dumps(schema))
        agents = text("AGENTS.md")
        for value in set(found):
            self.assertIn(f"| `{value}` |", agents, value)
        self.assertIn("one of the seven values", agents)

    def test_vllm_bfloat16_covers_all_platforms(self) -> None:
        agents = text("AGENTS.md")
        self.assertIn("(128/129, 228/229, 328/329, 428/429) must pass vLLM `--dtype bfloat16`", agents)

    def test_readme_hf_token_names_the_mistral_workloads(self) -> None:
        self.assertIn("(x27–x32: vLLM, SGLang and RAG)", text("README.md"))


class WorkbookCudaRuntimeTests(unittest.TestCase):
    def test_2xx_runtime_text_matches_the_installed_toolkit(self) -> None:
        import sys
        from openpyxl import load_workbook

        sys.path.insert(0, str(ROOT / "scripts"))
        from readme_sections import _runtime_display

        wb = load_workbook(ROOT / "BenchmarkSpecDefinitions.xlsx", read_only=True, data_only=True)
        rows = wb["Workload_Definitions"].iter_rows(values_only=True)
        header = list(next(rows))
        col = header.index("GPU Runtime Version")
        runtime = {r[0]: r[col] for r in rows if isinstance(r[0], int)}
        cuda = {}
        for r in wb["Parameters_SmokeBaselineExtend"].iter_rows(values_only=True):
            if r[0] in (201, 401) and r[2] == "cuda_version":
                cuda[r[0] // 100] = str(r[3])
        for wl in range(201, 233):
            self.assertEqual(_runtime_display(runtime[wl]), f"CUDA {cuda[2]}", wl)
            self.assertNotIn("only when nvcc is missing", runtime[wl])
        for wl in range(401, 433):
            self.assertEqual(_runtime_display(runtime[wl]), f"CUDA {cuda[4]}", wl)
        helper = (ROOT / "scripts/lib/nvidia_cuda_toolkit.sh").read_text(encoding="utf-8")
        self.assertIn("24.04 (CUDA 13.3)", helper)


NET_SEQ = "113.1"


def inventory_row(seq: str) -> tuple:
    from openpyxl import load_workbook

    rows = load_workbook(ROOT / "config/hw_sw_info_commands.xlsx", read_only=True)["Sheet2"].iter_rows(values_only=True)
    by_seq = {str(r[0]): r for r in rows if r and r[0] is not None}
    return by_seq[seq]


class NetworkSpeedInventoryTests(unittest.TestCase):
    def test_row_is_bounded_and_runs_on_both_vendors(self) -> None:
        _seq, vendor, domain, command, description = inventory_row(NET_SEQ)[:5]
        self.assertEqual((vendor, domain), ("AMD, nVidia", "hardware"))
        self.assertIn("-r 0-49999999", command)
        self.assertIn("--max-time 15", command)
        self.assertIn("huggingface.co", command)
        self.assertIn("Hugging Face", description)

    def test_generated_collector_carries_the_row(self) -> None:
        import base64

        collector = (ROOT / "scripts/collect_hw_sw_info.sh").read_text(encoding="utf-8")
        lines = [line for line in collector.splitlines() if line.startswith(NET_SEQ + "\t")]
        self.assertEqual(len(lines), 1)
        self.assertEqual(base64.b64decode(lines[0].split("\t")[3]).decode(), inventory_row(NET_SEQ)[3])

    @unittest.skipIf(__import__("shutil").which("bash") is None, "bash is not installed")
    def test_command_reports_speed_partial_and_failure(self) -> None:
        import os
        import subprocess
        import tempfile

        command = inventory_row(NET_SEQ)[3]
        cases = (
            ("206 0.01 0.15 50000000 41234567.0", 0, 0, "speed_MBps=41.2", "partial"),
            ("206 0.02 0.30 18000000 1200000.0", 28, 0, "(partial: stopped at the 15 s limit)", "no download"),
            ("000 0.00 0.00 0 0.0", 6, 1, "(no download: HTTP error or no network)", "partial"),
            ("403 0.01 0.05 0 0.0", 22, 1, "(no download: HTTP error or no network)", "partial"),
        )
        for out, curl_rc, want_rc, want_text, not_text in cases:
            with tempfile.TemporaryDirectory() as tmp:
                fake = Path(tmp) / "curl"
                fake.write_text(f"#!/usr/bin/env bash\necho \"{out}\"\nexit {curl_rc}\n", encoding="utf-8")
                fake.chmod(0o755)
                env = dict(os.environ, PATH=f"{tmp}:{os.environ.get('PATH', '')}")
                result = subprocess.run(["bash", "-o", "pipefail", "-c", command], capture_output=True,
                                        text=True, env=env, timeout=30)
            self.assertEqual(result.returncode, want_rc, (out, result.stdout))
            self.assertIn(want_text, result.stdout)
            self.assertNotIn(not_text, result.stdout)


class RenamedHeaderTests(unittest.TestCase):
    NEW = {"BC": "GPU Runtime Version", "BD": "BLAS Version"}

    def test_every_platform_header_row_uses_the_new_names(self) -> None:
        from openpyxl import load_workbook

        ws = load_workbook(ROOT / "BenchmarkSpecDefinitions.xlsx", read_only=True)["Workload_Definitions"]
        header_rows = [row for row in ws.iter_rows(values_only=True) if row and row[0] == "Workload Number"]
        self.assertEqual(len(header_rows), 4)
        for row in header_rows:
            self.assertEqual((row[54], row[55]), (self.NEW["BC"], self.NEW["BD"]))
            self.assertFalse(any(isinstance(c, str) and "(was " in c for c in row))

    def test_extraction_keeps_the_rocm_and_rocblas_aliases(self) -> None:
        import subprocess
        import sys
        import tempfile

        sys.path.insert(0, str(ROOT / "scripts"))
        from readme_sections import requirements

        expected = {101: "AMD GPU with ROCm 10.1.0", 228: "NVIDIA GPU with CUDA 13.3", 428: "NVIDIA GPU with CUDA 13.3"}
        for workload, gpu_line in expected.items():
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "spec.json"
                subprocess.run([sys.executable, str(ROOT / "scripts/extract_benchmark_definition.py"),
                                "--workload", str(workload), "--output", str(out)],
                               check=True, capture_output=True, cwd=ROOT, timeout=120)
                fields = {d["field_name"]: str(d.get("value") or "") for d in json.loads(out.read_text(encoding="utf-8"))}
            self.assertEqual(fields["ROCm Version"], fields["GPU Runtime Version"], workload)
            self.assertEqual(fields["rocBLAS Version"], fields["BLAS Version"], workload)
            self.assertNotIn("GPU Runtime Version (was ROCm Version)", fields)
            self.assertIn(gpu_line, requirements(fields))

    def test_readme_line_still_reads_an_old_spec(self) -> None:
        import sys

        sys.path.insert(0, str(ROOT / "scripts"))
        from readme_sections import requirements

        old = {"GPU Vendor": "AMD", "Execution Domain": "GPU Compute / ROCm", "OS Version": "Ubuntu 24.04",
               "GPU Runtime Version (was ROCm Version)": "ROCm 10.1.0", "Framework": "Bash"}
        self.assertIn("AMD GPU with ROCm 10.1.0", requirements(old))


if __name__ == "__main__":
    unittest.main()
