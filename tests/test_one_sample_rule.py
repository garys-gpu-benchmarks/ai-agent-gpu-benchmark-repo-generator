"""One measurement, one sample row (all workloads).

validate_results.py used to require two sample rows for workloads 101-123 and
301-323. Collectors that measured once copied their row (rows.append(dict(rows[0])),
summary_repeat) or ran the whole measurement twice (vLLM AMD sweeps; NVIDIA SDXL,
cuBLAS and cuDNN timed passes). The rule now asks for one row, the copies are gone,
and those measurements run once.
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "implementation_components"


class OneSampleRuleTests(unittest.TestCase):
    def test_validator_has_no_two_sample_rule(self) -> None:
        text = (ROOT / "scripts/materialize_generated_harness.py").read_text(encoding="utf-8")
        self.assertNotIn("require at least two sample rows", text)
        self.assertIn('failures.append("no sample rows")', text)

    def test_no_component_copies_a_sample_row(self) -> None:
        for path in COMPONENTS.glob("*/files/**/*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("rows.append(dict(rows[0]))", text, path)
            self.assertNotIn('"summary_repeat"', text, path)
            self.assertNotIn('"loss": 1.0', text, path)  # hand-built duplicate rows

    def test_measurements_run_once(self) -> None:
        for comp in ("vllm-kvcache-amd", "vllm-throughput-amd", "vllm-token-generation-amd"):
            text = (COMPONENTS / comp / "files/scripts/benchmark_serving.py").read_text(encoding="utf-8")
            self.assertNotIn("for _repeat in range(2):", text, comp)
        for rel in ("sdxl-diffusers-nvidia/files/scripts/collect_sdxl.py",
                    "cublas-gemm-nvidia/files/scripts/collect_cublas_gemm.py",
                    "cudnn-convolution-nvidia/files/scripts/collect_cudnn_conv.py"):
            text = (COMPONENTS / rel).read_text(encoding="utf-8")
            self.assertNotIn("for pass_index in (1, 2):", text, rel)
            self.assertNotIn("len(rows) < 2", text, rel)
        for rel in ("bert-inference-nvidia/files/scripts/collect_bert_infer.py",
                    "distilbert-nvidia/files/scripts/collect_distilbert_train.py",
                    "jax-xla-amd/files/scripts/collect_jax_xla.py",
                    "jax-xla-nvidia/files/scripts/collect_jax_xla.py",
                    "resnet50-training-nvidia/files/scripts/collect_resnet50_train.py"):
            text = (COMPONENTS / rel).read_text(encoding="utf-8")
            self.assertNotIn("for index in range(2):", text, rel)
        rocblas = (COMPONENTS / "rocblas-gemm-amd/files/scripts/collect_workload.py").read_text(encoding="utf-8")
        self.assertNotIn("for index in range(2):", rocblas)


if __name__ == "__main__":
    unittest.main()
