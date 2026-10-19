#!/usr/bin/env python3
"""Regression checks for the eight Issue-and-Impact items dated 2026-10-17."""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from metric_contract import (  # noqa: E402
    annotate_metrics,
    apply_storage_aliases,
    cache_resident,
    finalize_serving_publication,
    fp64_matrix_peak,
    gpu_model_note,
    guarded_percentile,
    publication_status,
    same_gpu,
    text_dimension_key,
)
from print_metric_summary import resolve_metrics  # noqa: E402


def generated_parser():
    harness = (ROOT / "scripts" / "materialize_generated_harness.py").read_text(encoding="utf-8")
    tree = ast.parse(harness)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith(
            "#!/usr/bin/env python3\n# File: scripts/parse_results.py"
        ):
            namespace: dict = {}
            exec(compile(node.value, "parse_results.py", "exec"), namespace)
            return namespace
    raise AssertionError("generated parser was not found")


class IssueImpactTests(unittest.TestCase):
    def test_standin_does_not_publish_sglang_numbers(self):
        metrics, status = finalize_serving_publication(
            {"ttft_p50_msec": 1.25, "request_throughput_requests_sec": 80.0},
            "server_identity=stub tiny_sglang_server.py",
        )
        self.assertEqual(status, "stub")
        self.assertEqual(metrics["ttft_p50_msec"], "na (stub server, smoke only)")
        self.assertEqual(metrics["stub_ttft_p50_msec"], 1.25)
        result, _count = publication_status(
            [("ttft_p50_msec", metrics["ttft_p50_msec"])],
            {"status": "stub", "profile": "smoke"},
        )
        self.assertEqual(result, "SMOKE-STANDIN")

    def test_aliases_fix_units_and_drop_positional_guesses(self):
        metrics = apply_storage_aliases(
            {"first_image_latency_sec": 1.5, "gpu_mem_gb": 12.0, "hbm3_coverage_gb": 4.0}
        )
        self.assertAlmostEqual(metrics["first_image_latency_ms"], 1500.0)
        self.assertEqual(metrics["peak_gpu_memory_gb"], 12.0)
        self.assertEqual(metrics["allocated_verification_buffer_gb"], 4.0)
        resolved = resolve_metrics(
            [
                ("5", "First-image latency, cold, ms (first_image_latency_ms)"),
                ("3", "Peak GPU memory, GB (peak_gpu_memory_gb)"),
            ],
            {"first_image_latency_sec": 1.5, "gpu_mem_gb": 12.0},
        )
        self.assertEqual(resolved[0][3], 1500.0)
        self.assertEqual(resolved[1][3], 12.0)
        self.assertTrue(text_dimension_key("Transfer direction (direction)"))
        missing = resolve_metrics([("1", "Missing value (not_a_real_key)")], {"other": 1})
        self.assertEqual(missing[0][3], "NOT FOUND")

    def test_memcpy_headline_is_max_h2d_not_a_blend(self):
        parser = generated_parser()
        rows = [
            {"direction": "h2d", "transfer_size_bytes": "8388608", "bandwidth_gbps": "100", "latency_us": "5"},
            {"direction": "d2h", "transfer_size_bytes": "8388608", "bandwidth_gbps": "40", "latency_us": "9"},
            {"direction": "h2d", "transfer_size_bytes": "268435456", "bandwidth_gbps": "50", "latency_us": "20"},
        ]
        summary = parser["build_metrics_summary"](
            ["direction", "transfer_size_bytes", "bandwidth_gbps", "latency_us"],
            rows,
            {"bandwidth_gbps": 63.0, "latency_us": 11.0, "transfer_size_bytes": 1.0},
        )
        self.assertEqual(summary["bandwidth_gbps"], 50)
        self.assertEqual(summary["latency_us"], 5)
        self.assertIn("H2D", summary["headline_point"])
        self.assertEqual(summary["headline_transfer_bytes"], 268435456)

    def test_fio_first_case_keeps_every_job(self):
        parser = generated_parser()
        rows = [
            {
                "rw": "randread", "block_size": "4k", "io_depth": "1",
                "headline_rule": "first_case", "is_headline": "1",
                "headline_configuration": "randread_4k_qd1", "iops_mean": "10",
            },
            {
                "rw": "read", "block_size": "1m", "io_depth": "8",
                "headline_rule": "first_case", "is_headline": "0",
                "headline_configuration": "read_1m_qd8", "iops_mean": "90",
            },
        ]
        summary = parser["build_metrics_summary"](
            ["rw", "block_size", "io_depth", "iops_mean"],
            rows,
            {"iops_mean": 50.0},
        )
        self.assertEqual(summary["iops_mean"], 10)
        self.assertEqual(summary["iops_mean__read_1m_qd8"], 90)
        self.assertIn("first_case", summary["headline_point"])

    def test_cache_resident_and_peak_flag(self):
        self.assertTrue(cache_resident(8 * 1024**2, "hbm", "H100 SXM"))
        self.assertFalse(cache_resident(2 * 1024**3, "hbm", "H100 SXM"))
        annotated = annotate_metrics(
            {"bandwidth_gb_s_copy": 3700.0, "working_set_bytes": 8 * 1024**2},
            "H100 SXM",
        )
        self.assertEqual(annotated["cache_resident"], 1)
        self.assertIn("cache-resident", annotated["headline_point"])
        self.assertTrue(str(annotated["bandwidth_gb_s_copy"]).startswith("na ("))

    def test_percentile_floor_and_modeled_names(self):
        self.assertTrue(str(guarded_percentile([1, 2, 3], 0.99, "p99")).startswith("na (p99"))
        self.assertEqual(guarded_percentile([1, 2, 3], 1.0, "max"), 3)
        aliased = apply_storage_aliases({"achieved_compute_tflops": 10.0, "gflops": 20.0})
        # GEMM FLOPs are exact (2*M*N*K), so achieved_compute_tflops is its own
        # numbered key in all four GEMM workloads (2026-10-18), not modeled_tflops.
        self.assertEqual(aliased["achieved_compute_tflops"], 10.0)
        self.assertNotIn("modeled_tflops", aliased)
        self.assertEqual(aliased["modeled_gflops_per_s"], 20.0)

    def test_gpu_identity_and_expected_na(self):
        self.assertFalse(same_gpu("NVIDIA H100 NVL", "H100 SXM 80GB"))
        self.assertTrue(same_gpu("NVIDIA H100 80GB SXM", "H100 SXM 80GB"))
        self.assertIn("differs", gpu_model_note("NVIDIA H100 PCIe", "H100 SXM 80GB"))
        self.assertIsInstance(fp64_matrix_peak("AMD Instinct MI300X"), float)
        self.assertTrue(str(fp64_matrix_peak("")).startswith("na ("))
        status, count = publication_status(
            [
                ("latency_ns_remote_dram", "na (requires a second NUMA node)"),
                ("latency_ns_l1", 1.2),
            ],
            {"numa_nodes": 1, "profile": "baseline"},
        )
        self.assertEqual(status, "N/A-EXPECTED")
        self.assertEqual(count, 1)
        unexpected, _count = publication_status(
            [("gpu_utilization_percent", "na (timed loop too short to sample)")],
            {"profile": "baseline"},
        )
        self.assertEqual(unexpected, "INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
