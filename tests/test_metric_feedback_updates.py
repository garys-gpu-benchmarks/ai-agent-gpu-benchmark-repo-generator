# File: tests/test_metric_feedback_updates.py
# Version: 1.0.0
# Author: AI Coding Agent
# Date: 2026-10-02
# Description: Regression checks for metric-feedback collector and parser corrections.
# Execution: python tests/test_metric_feedback_updates.py
# Options: none
# Requirements: Python 3.12, PyYAML
# Environment: Repository-local development environment
# Dependencies: implementation component source files
# Variables: none
# Repository: ai-agent-gpu-benchmark-repo-generator
# License: Apache-2.0

from __future__ import annotations

import ast
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "implementation_components"


def source(component: str, relative: str) -> str:
    return (COMPONENTS / component / "files" / relative).read_text(encoding="utf-8")


def load_module(component: str, relative: str, name: str):
    path = COMPONENTS / component / "files" / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MetricFeedbackUpdateTests(unittest.TestCase):
    def test_nvidia_health_emits_unit_suffixed_pcie_key(self):
        text = source("gpu-health-nvidia", "scripts/collect_workload.py")
        self.assertIn('"pcie_link_speed_gt_s": speed', text)
        self.assertNotIn('"pcie_link_speed": speed', text)

    def test_lmbench_selects_requested_16mb_row(self):
        module = load_module("lmbench-amd", "scripts/collect_workload.py", "lmbench_feedback")
        value, units = module.lmbench_value(
            "lat_mem_rd",
            "0.00049 1.2\n16.00000 87.5\n32.00000 95.0\n",
        )
        self.assertEqual(value, 87.5)
        self.assertEqual(units, "ns")
        text = source("lmbench-amd", "scripts/collect_workload.py")
        self.assertIn('"lat_syscall_null_us"', text)
        self.assertIn('["bw_mem", "512m", "rd"]', text)
        self.assertIn('"context_switch_latency_us"', text)
        nvidia = load_module("lmbench-nvidia", "scripts/collect_workload.py", "lmbench_nvidia_feedback")
        value, units = nvidia.lmbench_value(
            "lat_mem_rd",
            "0.00049 1.2\n16.00000 87.5\n32.00000 95.0\n",
        )
        self.assertEqual(value, 87.5)
        self.assertEqual(units, "ns")
        nvidia_text = source("lmbench-nvidia", "scripts/collect_workload.py")
        self.assertIn('"lat_syscall_null_us"', nvidia_text)
        self.assertIn('["bw_mem", "512m", "rd"]', nvidia_text)

    def test_fio_collectors_use_explicit_direction_and_real_bandwidth(self):
        for component in ("fio-nvme-amd", "fio-nvme-nvidia"):
            with self.subTest(component=component):
                text = source(component, "scripts/collect_workload.py")
                self.assertIn("rw.lower() in read_modes", text)
                self.assertNotIn('iops * 4096', text)
                self.assertIn("fio reported no bandwidth_bytes value", text)

    def test_collective_metrics_require_multi_gpu_all_reduce(self):
        amd = source("rccl-bandwidth-amd", "scripts/collect_workload.py")
        nvidia = source("nccl-bandwidth-nvidia", "scripts/collect_workload.py")
        self.assertIn('COLLECTIVES = ("all_reduce_perf",)', amd)
        self.assertIn('extras.extend(["-g", str(requested_gpus)])', amd)
        self.assertIn('collectives = ["all_reduce"]', nvidia)
        for text in (amd, nvidia):
            self.assertIn('NA_SINGLE_GPU = "na (requires at least two GPUs)"', text)
        self.assertIn("if requested_gpus >= 2 and used_gpus < 2:", amd)
        self.assertIn("if num_gpus >= 2 and used_gpus < 2:", nvidia)
        self.assertIn('["bin/nccl_bw"', nvidia)

    def test_correctness_collectors_use_norm_ratio_and_suite_failure_total(self):
        amd = source("pytorch-tensor-correctness-amd", "scripts/run_tensor_correctness.py")
        nvidia = source("pytorch-tensor-correctness-nvidia", "scripts/collect_tensor_ops.py")
        for text in (amd, nvidia):
            self.assertIn("vector_norm", text)
            self.assertNotIn("clamp_min(1e-8)", text)
        self.assertIn('row["failure_count"] = float(failed_cases)', amd)
        self.assertIn('row["failure_count"] = failures', nvidia)
        self.assertIn('raise SystemExit("[FAIL] no ROCm GPU")', amd)
        self.assertNotIn('else "cpu"', amd)
        self.assertIn('row["tolerance_compliance"] = compliance', nvidia)

    def test_amd_stream_fails_when_a_kernel_line_is_missing(self):
        amd = source("stream-collect-amd", "scripts/collect_workload.py")
        nvidia = source("stream-collect-nvidia", "scripts/collect_workload.py")
        self.assertNotIn("name: 1.0", amd)
        for text in (amd, nvidia):
            self.assertIn('[FAIL] STREAM did not report {name}', text)
            self.assertIn("return 1", text)

    def test_sdxl_parsers_aggregate_all_timed_images(self):
        amd = source("sdxl-diffusers-amd", "scripts/parse_results.py")
        nvidia = source("sdxl-diffusers-nvidia", "scripts/parse_results.py")
        self.assertIn('"images_per_sec": len(samples) / total_timed_s', amd)
        self.assertIn('"peak_gpu_memory_gb": max(', amd)
        self.assertIn('"images_per_sec": len(latencies) / sum(latencies)', nvidia)
        self.assertIn('"peak_vram_gb": max(memory_values)', nvidia)
        for component in ("sdxl-diffusers-amd", "sdxl-diffusers-nvidia"):
            infer = source(component, "scripts/infer_sdxl.py")
            runner = source(component, "run_benchmark.sh")
            self.assertIn('backend = "sdxl"', infer)
            self.assertIn("MIN_REAL_RESOLUTION = 256", infer)
            self.assertIn("MIN_TIMED_IMAGES = 2", infer)
            self.assertIn("torch.cuda.max_memory_reserved(device)", infer)
            self.assertIn("MIN_SDXL_VRAM_GB = 5.0", infer)
            self.assertLess(
                infer.index("cold_start = time.perf_counter()"),
                infer.index("StableDiffusionXLPipeline.from_pretrained"),
            )
            self.assertIn('BACKEND="sdxl"', runner)
            self.assertNotIn('BACKEND="tiny"', runner)
        collector = source("sdxl-diffusers-nvidia", "scripts/collect_sdxl.py")
        self.assertIn("TinyDenoiser is a setup self-test", collector)
        self.assertIn('"images_per_sec": total_images / total_timed_seconds', collector)
        self.assertIn('"peak_vram_gb": max(', collector)

    def test_vllm_kv_summary_uses_maximum_sweep_peaks(self):
        text = source("vllm-kvcache-nvidia", "scripts/benchmark_serving.py")
        self.assertIn(
            'for peak_key in ("kv_cache_peak_gb", "kv_cache_usage_peak_pct")',
            text,
        )
        self.assertIn("summary_metrics[peak_key] = max(numeric_peaks)", text)

    def test_ecc_collectors_use_deltas_and_real_pass_rates(self):
        amd = source("sdc-ecc-amd", "scripts/collect_workload.py")
        nvidia = source("sdc-ecc-nvidia", "scripts/collect_workload.py")
        cuda = source("sdc-ecc-nvidia", "src/ecc_walk.cu")
        self.assertIn("counter_delta(ecc_before[0], ecc_after[0])", amd)
        self.assertIn('(n * 4 / 1e9) if device.type == "cuda" else ""', amd)
        self.assertIn("(loops - failed_checks) / loops", amd)
        self.assertIn("ecc_after[key] - ecc_before[key]", nvidia)
        self.assertIn("(loops - failed_loops) / loops", nvidia)
        self.assertIn("failed_loops=", cuda)
        self.assertIn("0x00000001u", cuda)
        module = load_module("sdc-ecc-amd", "scripts/collect_workload.py", "sdc_ecc_amd_ras")
        self.assertEqual(
            module.ras_counter_totals("Uncorrectable Error Count: 2\nCorrectable Error Count: 3\n"),
            (2.0, 3.0),
        )
        table = (
            "Block Name Status Correctable Error Uncorrectable Error\n"
            "umc ENABLED 0 1\n"
            "sdma ENABLED 4 0\n"
        )
        self.assertEqual(module.ras_counter_totals(table), (1.0, 4.0))
        self.assertEqual(
            module.ras_counter_totals("Correctable Error Uncorrectable Error\n"),
            ("na (RAS table not parsed)", "na (RAS table not parsed)"),
        )
        self.assertEqual(module.ras_counter_totals(""), ("", ""))
        self.assertEqual(module.counter_delta(1, 4), 3.0)
        self.assertEqual(
            module.counter_delta("na (RAS table not parsed)", 4),
            "na (RAS table not parsed)",
        )

    def test_system_stress_power_is_max_draw_and_ecc_is_interval_delta(self):
        amd = load_module(
            "system-stress-amd",
            "scripts/collect_workload.py",
            "system_stress_amd_power",
        )
        self.assertFalse(amd.is_gpu_power_line("current power: 15"))
        self.assertTrue(amd.is_gpu_power_line("average graphics package power (w): 20.5"))
        self.assertFalse(amd.is_gpu_power_line("power cap (w): 560"))
        self.assertEqual(
            amd.ecc_from_ras_text("Name Status Uncorrectable Error\numc ENABLED 0 1\n"),
            "na (RAS table not parsed)",
        )
        self.assertEqual(amd.ecc_from_ras_text("Uncorrectable Error: 2\nUncorrectable Error: 3\n"), 5.0)
        self.assertEqual(amd.ecc_interval_delta([2, 2, 5]), 3.0)
        self.assertEqual(amd.ecc_interval_delta(["", ""]), "")
        self.assertEqual(amd.ecc_interval_delta(["na (RAS table not parsed)", 4]), "na (RAS table not parsed)")
        nvidia = load_module(
            "system-stress-nvidia",
            "scripts/collect_workload.py",
            "system_stress_nvidia_ecc",
        )
        self.assertEqual(nvidia.ecc_interval_delta([1.0, 1.0, 4.0]), 3.0)
        self.assertIn("temperature.gpu", source("system-stress-nvidia", "scripts/collect_workload.py"))

    def test_stack_collectors_separate_diagnostics(self):
        amd = source("system-config-amd", "scripts/collect_workload.py")
        nvidia = source("system-config-nvidia", "scripts/collect_workload.py")
        self.assertIn('"kernel_mismatch_count"', amd)
        self.assertIn('"driver_mismatch_count"', amd)
        self.assertIn('"kernel_release_mismatch_count": float(kernel_mismatch)', amd)
        self.assertIn("na (in-tree amdgpu has no version)", amd)
        self.assertNotIn("kernel_mismatch + driver_mismatch", amd)
        self.assertIn("if not node.exists() or not os.access", amd)
        self.assertIn('"cuda_major_version_mismatch_count"', nvidia)
        self.assertIn("driver_compliance = 100.0 * sum(compliance_checks)", nvidia)
        self.assertIn("node.is_char_device()", nvidia)
        self.assertIn('normalized == "nvidia-smi"', nvidia)
        self.assertIn('normalized == "cuda-toolkit"', nvidia)
        module = load_module(
            "system-config-nvidia",
            "scripts/collect_workload.py",
            "system_config_nvidia_packages",
        )
        problems, _ = module.check_packages(
            ["nvidia-smi", "cuda-toolkit"],
            {"cuda-nvcc-12-6": "12.6.85-1", "nvidia-utils-580": "580.95.05-0ubuntu1"},
            expected_cuda="12.8", expected_driver="580", smi_owner="nvidia-utils-580", smi_ok=True,
        )
        self.assertEqual(problems, [])
        problems, _ = module.check_packages(
            ["nvidia-smi", "cuda-toolkit"], {},
            expected_cuda="12.8", expected_driver="580", smi_owner="", smi_ok=False,
        )
        self.assertEqual(len(problems), 2)
        harness = (ROOT / "scripts" / "materialize_generated_harness.py").read_text(encoding="utf-8")
        self.assertIn('"compliance"', harness)

    def test_sweep_headlines_preserve_case_metrics(self):
        for component in ("fio-nvme-amd", "fio-nvme-nvidia"):
            text = source(component, "scripts/collect_workload.py")
            self.assertIn('row[f"case_{key}"] = row[key]', text)
            self.assertIn('row["headline_configuration"]', text)
        amd = source("resnet50-inference-amd", "scripts/collect_workload.py")
        nvidia = source("resnet50-inference-nvidia", "scripts/collect_resnet50_infer.py")
        self.assertIn('row["headline_batch_size"]', amd)
        self.assertIn('row[f"case_{name}"] = row[name]', nvidia)

    def test_remote_dram_names_the_missing_numa_node(self):
        collector = source("multichase-numa-amd", "scripts/collect_multichase.py")
        self.assertIn('"na (requires a second NUMA node)"', collector)
        harness = (ROOT / "scripts" / "materialize_generated_harness.py").read_text(encoding="utf-8")
        tree = ast.parse(harness)
        parser = ""
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith("#!/usr/bin/env python3\n# File: scripts/parse_results.py"):
                parser = node.value
                break
        self.assertTrue(parser)
        namespace = {}
        exec(compile(parser, "parse_results.py", "exec"), namespace)
        rows = [
            {"tier": "l1", "latency_ns": "1.2", "stride": "64"},
            {"tier": "local_dram", "latency_ns": "40.0", "stride": "64"},
            {"tier": "remote_dram", "latency_ns": "na (requires a second NUMA node)", "stride": "64"},
        ]
        summary = namespace["build_metrics_summary"](
            ["tier", "latency_ns", "stride"],
            rows,
            {"tier": None, "latency_ns": 20.6, "stride": 64.0},
        )
        self.assertEqual(summary["latency_ns_remote_dram"], "na (requires a second NUMA node)")
        self.assertNotIn("not measured", summary.values())

    def test_numa_unavailable_counter_is_not_zero(self):
        text = source("numa-cache-collector", "scripts/collect_numa_cache.py")
        self.assertIn("na (expected: perf_event_paranoid blocks cache-misses)", text)
        self.assertIn("na (expected: numactl policy not permitted; second numa node not measurable)", text)
        self.assertNotIn("if miss_match is None:\n        return 0.0", text)

    def test_jax_requires_completion_and_reports_modeled_flops(self):
        for component in ("jax-xla-amd", "jax-xla-nvidia"):
            forward = source(component, "scripts/gpu-bench-jax-xla-forwardpass.py")
            collector = source(component, "scripts/collect_jax_xla.py")
            self.assertIn("executable = lowered.compile()", forward)
            self.assertIn("tflops_method=modeled_from_transformer_operation_count", forward)
            self.assertIn("[WARN] stopped after", forward)
            self.assertIn("completed no iterations", forward)
            self.assertNotIn("did not complete every requested iteration", collector)
            self.assertIn("completed no iterations", collector)
            self.assertIn("completed_iterations", collector)

    def test_amd_kv_gib_uses_logged_capacity(self):
        module = load_module(
            "vllm-kvcache-amd",
            "scripts/benchmark_serving.py",
            "vllm_kvcache_amd_feedback",
        )
        self.assertAlmostEqual(module.resolve_kv_gb("", 2.702, 80.0), 2.1616)
        self.assertEqual(module.resolve_kv_gb("", 2.702, None), module.NA_KV_NO_BYTES)
        self.assertEqual(module.resolve_kv_gb("", "", None), module.NA_KV)
        self.assertEqual(module.resolve_kv_gb(1.5, 2.702, 80.0), 1.5)
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "server.log"
            log_path.write_text(
                "Available KV cache memory: 80.0 GiB\nGPU KV cache usage: 2.70%\n",
                encoding="utf-8",
            )
            capacity, percents, offset = module.read_kv_log(log_path, 0)
        self.assertEqual(capacity, 80.0)
        self.assertEqual(percents, [2.70])
        self.assertGreater(offset, 0)
        text = source("vllm-kvcache-amd", "scripts/benchmark_serving.py")
        self.assertIn("Available KV cache memory", text)
        nvidia = source("vllm-kvcache-nvidia", "scripts/benchmark_serving.py")
        self.assertIn("na (server reported a percent and no byte count)", nvidia)

    def test_rocblas_gemm_omits_unpublished_l2(self):
        text = source("rocblas-gemm-amd", "scripts/collect_workload.py")
        self.assertNotIn("norm_error_2", text)
        self.assertIn("cpu_gflops", text)
        nvidia = source("cublas-gemm-nvidia", "scripts/collect_cublas_gemm.py")
        self.assertIn("norm_error_2", nvidia)

    def test_hpl_substitute_uses_tensor_peak_and_records_actual_shape(self):
        # 2026-10-19: Dgetrf runs on the FP64 tensor cores, so percent of peak
        # divides by the tensor-core peak (the vector peak gave 101-102%).
        text = source("linpack-hpl-nvidia", "scripts/collect_workload.py")
        self.assertIn('"percent_of_fp64_tensor_peak"', text)
        self.assertIn('r"peak_fp64_tflops=', text)
        self.assertNotIn("percent_of_fp64_vector_peak", text)
        self.assertIn('"solver_implementation": "cuSOLVER_Dgetrf_Dgetrs"', text)

    def test_llm_decode_and_itl_exclude_prefill_and_pool_token_gaps(self):
        for component in ("vllm-kvcache-amd", "vllm-kvcache-nvidia"):
            text = source(component, "scripts/benchmark_serving.py")
            self.assertIn('"decode_ms"', text)
            self.assertIn('"first_token_at"', text)
            self.assertIn('"completed_at"', text)
            self.assertIn("decode_window_throughput(results)", text)
            self.assertNotIn("sum(float(r[\"decode_ms\"])", text)
        for component in ("sglang-serving-amd", "sglang-serving-nvidia"):
            text = source(component, "scripts/bench_serving.py")
            self.assertIn('"itl_gaps_ms"', text)
            self.assertIn("for gap in result.get(\"itl_gaps_ms\", [])", text)

    def test_kv_cache_uses_real_vllm_wall_window_and_requires_telemetry(self):
        overlapping = [
            {"out_tokens": 10, "first_token_at": 0.0, "completed_at": 2.0},
            {"out_tokens": 10, "first_token_at": 1.0, "completed_at": 3.0},
        ]
        for component in ("vllm-kvcache-amd", "vllm-kvcache-nvidia"):
            with self.subTest(component=component):
                module = load_module(
                    component,
                    "scripts/benchmark_serving.py",
                    f"{component.replace('-', '_')}_wall_window",
                )
                self.assertEqual(module.decode_window_throughput(overlapping), 6.0)
                self.assertEqual(module.require_kv_metrics(2.5, 12.0), (2.5, 12.0))
                with self.assertRaises(SystemExit):
                    module.require_kv_metrics(module.NA_KV, module.NA_KV)
                collector = source(component, "scripts/benchmark_serving.py")
                runner = source(component, "run_benchmark.sh")
                self.assertIn("median(", collector)
                self.assertIn("0.0 <= util <= 1.0", collector)
                self.assertIn("-m vllm.entrypoints.openai.api_server", runner)
                self.assertNotIn("scripts/tiny_kv_server.py --host", runner)

    def test_vllm_throughput_uses_real_server_and_token_validated_itl(self):
        for component in ("vllm-throughput-amd", "vllm-throughput-nvidia"):
            with self.subTest(component=component):
                collector = source(component, "scripts/benchmark_serving.py")
                runner = source(component, "run_benchmark.sh")
                self.assertIn('"logprobs": 1', collector)
                self.assertIn("timed_tokens != out_tokens", collector)
                self.assertIn("cannot map SSE chunks to output tokens", collector)
                self.assertNotIn("apply_itl_contract", collector)
                self.assertIn("min(output_len, 4)", collector)
                self.assertLess(
                    collector.index("min(output_len, 4)"),
                    collector.index("started = time.perf_counter()"),
                )
                self.assertIn("-m vllm.entrypoints.openai.api_server", runner)
                self.assertNotIn("scripts/tiny_kv_server.py --host", runner)
        amd = source("vllm-throughput-amd", "scripts/benchmark_serving.py")
        nvidia = source("vllm-throughput-nvidia", "scripts/benchmark_serving.py")
        self.assertIn('e2e = percentile([item["e2e_ms"] for item in results], 50.0)', amd)
        self.assertIn('"end_to_end_request_latency_msec": pct(e2es, 0.50)', nvidia)

    def test_vllm_token_generation_verifies_model_and_token_timing(self):
        for component in ("vllm-token-generation-amd", "vllm-token-generation-nvidia"):
            with self.subTest(component=component):
                collector = source(component, "scripts/benchmark_serving.py")
                runner = source(component, "run_benchmark.sh")
                for key in (
                    "output_token_throughput_tokens_sec",
                    "time_per_output_token_tpot_p50_msec",
                    "ttft_p50_msec",
                    "inter_token_latency_itl_p50_msec",
                    "end_to_end_request_latency_msec",
                ):
                    self.assertIn(f'"{key}"', collector)
                self.assertIn("/v1/models", collector)
                self.assertIn("loaded_model_id.txt", collector)
                self.assertIn('"logprobs": 1', collector)
                self.assertIn("timed_tokens != out_tokens", collector)
                self.assertIn("min(output_len, 4)", collector)
                self.assertNotIn("itl_must_not_copy_tpot", collector)
                self.assertNotIn("apply_itl_contract", collector)
                self.assertIn("-m vllm.entrypoints.openai.api_server", runner)
                self.assertNotIn("scripts/tiny_kv_server.py --host", runner)
                self.assertIn("loaded_model_id=${LOADED_MODEL_ID}", runner)
        amd = source("vllm-token-generation-amd", "scripts/benchmark_serving.py")
        nvidia = source("vllm-token-generation-nvidia", "scripts/benchmark_serving.py")
        self.assertIn('e2e = percentile([item["e2e_ms"] for item in results], 50.0)', amd)
        self.assertIn('"end_to_end_request_latency_msec": pct(e2es, 0.50)', nvidia)

    def test_numa_cache_metrics_use_configured_tiers_and_threaded_pointer_chase(self):
        module = load_module(
            "numa-cache-collector",
            "scripts/collect_numa_cache.py",
            "numa_cache_feedback",
        )
        self.assertEqual(
            module.summary_indices(
                [32768, 2097152, 16777216, 268435456],
                ["L1", "L2", "L3", "DRAM"],
            ),
            (2, 3),
        )
        self.assertEqual(module.parse_size_bytes("32M"), 32 * 1024**2)
        collector = source("numa-cache-collector", "scripts/collect_numa_cache.py")
        for key in (
            "cache_latency_nsec",
            "local_numa_node_latency_nsec",
            "local_dram_pointer_chase_bandwidth_gb_s",
            "cache_miss_counters_misses_sec",
        ):
            self.assertIn(f'"{key}"', collector)
        self.assertIn('"access_pattern": access_pattern', collector)
        self.assertIn('"cache_misses_per_sec"', collector)
        self.assertNotIn('chase(dram_size, local_key, "random")', collector)
        native = source("numa-cache-collector", "src/numa_sweep.cpp")
        self.assertIn('pick(sweep, "access_pattern", profile, "random")', collector)
        self.assertIn("std::thread", native)
        self.assertIn('std::string pattern = "random"', native)
        self.assertIn("static_cast<double>(threads)", native)
        self.assertIn("static_cast<double>(sizeof(size_t))", native)
        self.assertNotIn("(void)threads", native)

    def test_amd_gups_l3_rate_uses_llc_events_and_outgrows_cache(self):
        module = load_module("gups-amd", "scripts/collect_workload.py", "gups_amd_feedback")
        self.assertEqual(module.parse_cache_size_bytes("32M"), 32 * 1024**2)
        self.assertEqual(
            module.required_table_elements(4_194_304, 64 * 1024**2),
            33_554_432,
        )
        self.assertEqual(
            module.required_table_elements(4_194_304, 128 * 1024**2),
            67_108_864,
        )
        collector = source("gups-amd", "scripts/collect_workload.py")
        self.assertIn("LLC-loads,LLC-load-misses", collector)
        self.assertIn('rate("llc-load-misses", "llc-loads")', collector)
        self.assertIn("na (LLC load counters unavailable)", collector)
        self.assertNotIn("cache-references,cache-misses", collector)
        self.assertIn('"l3_miss_rate": l3', collector)

    def test_memcpy_uses_bandwidth_sized_transfers_and_seven_ledger_slots(self):
        for component in ("hipmemcpy-bandwidth-amd", "cuda-memcpy-nvidia"):
            with self.subTest(component=component):
                collector = load_module(
                    component,
                    "scripts/collect_workload.py",
                    f"{component.replace('-', '_')}_feedback",
                )
                self.assertEqual(collector.BANDWIDTH_SIZE_FLOOR, 256 * 1024**2)
                self.assertEqual(collector.BANDWIDTH_ITERATION_FLOOR, 10)
        nvidia = source("cuda-memcpy-nvidia", "scripts/collect_workload.py")
        self.assertIn('row["pinned_vs_pageable_bandwidth_ratio"] = ""', nvidia)
        self.assertIn('"bandwidth_h2d_gbps"', nvidia)
        ledger_path = ROOT / "scripts" / "update_runtime_ledger.py"
        spec = importlib.util.spec_from_file_location("ledger_feedback", ledger_path)
        ledger = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(ledger)
        self.assertEqual(ledger.METRIC_SLOT_COUNT, 7)
        self.assertIn("metric_6_result", ledger.LEDGER_COLUMNS)
        self.assertIn("metric_7_result", ledger.LEDGER_COLUMNS)
        self.assertLess(
            ledger.LEDGER_COLUMNS.index("metric_7_result"),
            ledger.LEDGER_COLUMNS.index("run_benchmark_command_submitted"),
        )
        migrated = ledger.migrate_row({"metric_5_result": "kept"})
        self.assertEqual(migrated["metric_5_result"], "kept")
        self.assertEqual(migrated["metric_6_result"], "")
        self.assertEqual(migrated["metric_7_result"], "")

    def test_vllm_groups_multi_token_sse_chunks_and_keeps_ninja_on_path(self):
        for component in (
            "vllm-throughput-amd",
            "vllm-throughput-nvidia",
            "vllm-token-generation-amd",
            "vllm-token-generation-nvidia",
        ):
            with self.subTest(component=component):
                collector = source(component, "scripts/benchmark_serving.py")
                self.assertIn('"logprobs": 1', collector)
                self.assertIn("timed_tokens != out_tokens", collector)
                self.assertIn("cannot map SSE chunks to output tokens", collector)
                self.assertIn("chunk_sizes=", collector)
                module = load_module(
                    component,
                    "scripts/benchmark_serving.py",
                    f"{component.replace('-', '_')}_stream_groups",
                )
                ambiguous: list[int] = []
                times: list[float] = []
                added, ok, stamp = module.record_stream_choice(
                    {"text": "", "logprobs": {"tokens": ["x"]}},
                    5.0,
                    times,
                    ambiguous,
                )
                self.assertEqual((added, ok, stamp), (1, True, 5.0))
                self.assertEqual(times, [5.0])
                four: list[float] = []
                added, ok, stamp = module.record_stream_choice(
                    {"text": "abcd", "logprobs": {"tokens": ["a", "b", "c", "d"]}},
                    2.0,
                    four,
                    ambiguous,
                )
                self.assertEqual((added, ok, stamp), (4, True, 2.0))
                self.assertEqual(four, [2.0, 2.0, 2.0, 2.0])
                untouched = [9.0]
                added, ok, stamp = module.record_stream_choice({}, 3.0, untouched, ambiguous)
                self.assertEqual((added, ok, stamp), (0, True, None))
                self.assertEqual(untouched, [9.0])
                paired = [1.0]
                added, ok, stamp = module.record_stream_choice(
                    {"text": "ab", "logprobs": {"tokens": ["a", "b"]}},
                    1.2,
                    paired,
                    ambiguous,
                )
                self.assertEqual((added, ok), (2, True))
                self.assertAlmostEqual(paired[1], 1.1)
                self.assertAlmostEqual(paired[2], 1.2)
                self.assertAlmostEqual(stamp, 1.1)
                before = list(paired)
                added, ok, _stamp = module.record_stream_choice(
                    {"text": "hi", "logprobs": {"tokens": []}},
                    4.0,
                    paired,
                    ambiguous,
                )
                self.assertEqual((added, ok), (0, False))
                self.assertEqual(paired, before)
                self.assertEqual(ambiguous, [0])
        for component in (
            "vllm-kvcache-nvidia",
            "vllm-throughput-nvidia",
            "vllm-token-generation-nvidia",
        ):
            runner = source(component, "run_benchmark.sh")
            self.assertIn("${REPO_ROOT}/.venv/bin:", runner)

    def test_mistral_snapshot_needs_a_real_tokenizer(self):
        for component in ("rag-faiss-end2end-nvidia", "rag-faiss-end2end-amd"):
            with self.subTest(component=component):
                module = load_module(
                    component,
                    "scripts/rag_model_paths.py",
                    f"{component.replace('-', '_')}_tokenizer",
                )
                prefetch = source(component, "scripts/prefetch_rag_models.py")
                self.assertIn("hf_hub_download", prefetch)
                self.assertIn("model.safetensors.index.json", prefetch)
                self.assertIn("ensure_mistral", prefetch)
                runner = source(component, "scripts/gpu-bench-rag-faiss-end2end.py")
                self.assertIn("ensure_mistral", runner)
                self.assertIn("output_loading_info=True", runner)
                self.assertIn("reject_missing_causal_weights", runner)
                self.assertNotIn("transformers_weight_source", runner)
                self.assertNotIn(".transformers-alias-", runner)
                for name in (
                    "tokenizer.json",
                    "tokenizer.model",
                    "tokenizer_config.json",
                    "special_tokens_map.json",
                ):
                    self.assertIn(name, prefetch)
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    snapshot = (
                        root
                        / "hub"
                        / "models--mistralai--Mistral-7B-v0.3"
                        / "snapshots"
                        / "rev"
                    )
                    snapshot.mkdir(parents=True)
                    (snapshot / "config.json").write_text("{}", encoding="utf-8")
                    (snapshot / "consolidated.safetensors").write_bytes(b"weights")
                    (snapshot / "tokenizer.model.v3").write_bytes(b"v3")
                    previous = os.environ.get("HF_HOME")
                    os.environ["HF_HOME"] = str(root)
                    try:
                        self.assertIsNone(module.find_local_causal_lm("mistralai/Mistral-7B-v0.3"))
                        (snapshot / "tokenizer.json").write_bytes(b"")
                        self.assertIsNone(module.find_local_causal_lm("mistralai/Mistral-7B-v0.3"))
                        (snapshot / "tokenizer.json").write_text('{"version":"1"}', encoding="utf-8")
                        self.assertIsNone(module.find_local_causal_lm("mistralai/Mistral-7B-v0.3"))
                        self.assertFalse(module.has_causal_lm_weights(snapshot))
                        (snapshot / "model.safetensors").write_bytes(b"hf-weights")
                        self.assertEqual(
                            module.find_local_causal_lm("mistralai/Mistral-7B-v0.3"),
                            snapshot,
                        )
                        (snapshot / "model.safetensors").unlink()
                        index = {
                            "weight_map": {
                                "model.layers.0": "model-00001-of-00002.safetensors",
                                "model.layers.1": "model-00002-of-00002.safetensors",
                            }
                        }
                        (snapshot / "model.safetensors.index.json").write_text(
                            json.dumps(index),
                            encoding="utf-8",
                        )
                        self.assertIsNone(module.find_local_causal_lm("mistralai/Mistral-7B-v0.3"))
                        (snapshot / "model-00001-of-00002.safetensors").write_bytes(b"a")
                        (snapshot / "model-00002-of-00002.safetensors").write_bytes(b"b")
                        self.assertEqual(
                            module.find_local_causal_lm("mistralai/Mistral-7B-v0.3"),
                            snapshot,
                        )
                        with self.assertRaises(SystemExit):
                            module.reject_missing_causal_weights(
                                {"missing_keys": ["model.layers.0.self_attn.q_proj.weight"]}
                            )
                        module.reject_missing_causal_weights({"missing_keys": ["lm_head.weight"]})
                    finally:
                        if previous is None:
                            os.environ.pop("HF_HOME", None)
                        else:
                            os.environ["HF_HOME"] = previous

    def test_sglang_index_is_incomplete_until_named_shard_is_nonempty(self):
        prompt = source("sglang-prompt-response-nvidia", "scripts/prefetch_sglang_model.py")
        serving = source("sglang-serving-nvidia", "scripts/prefetch_sglang_model.py")
        amd_prompt = source("sglang-prompt-response-amd", "scripts/prefetch_sglang_model.py")
        amd_serving = source("sglang-serving-amd", "scripts/prefetch_sglang_model.py")
        self.assertEqual(prompt, serving)
        self.assertEqual(prompt, amd_prompt)
        self.assertEqual(prompt, amd_serving)
        for component in (
            "sglang-prompt-response-nvidia",
            "sglang-serving-nvidia",
            "sglang-prompt-response-amd",
            "sglang-serving-amd",
        ):
            listed = json.loads((COMPONENTS / component / "component.json").read_text(encoding="utf-8"))
            self.assertIn("scripts/prefetch_sglang_model.py", listed["overlay"])
            self.assertIn("scripts/prefetch_sglang_model.py", listed["provides"])
            runner = source(component, "run_benchmark.sh")
            self.assertIn("prefetch_sglang_model.py", runner)
            self.assertIn("--model-path ${sglang_model_path}", runner)
            self.assertIn("tiny_sglang_server.py", runner)
        module = load_module(
            "sglang-prompt-response-nvidia",
            "scripts/prefetch_sglang_model.py",
            "prefetch_sglang_shards",
        )
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp)
            index = {"weight_map": {"model.layers.0": "model-00001-of-00003.safetensors"}}
            (snapshot / "model.safetensors.index.json").write_text(json.dumps(index), encoding="utf-8")
            self.assertFalse(module.shards_complete(snapshot))
            shard = snapshot / "model-00001-of-00003.safetensors"
            shard.write_bytes(b"")
            self.assertFalse(module.shards_complete(snapshot))
            shard.write_bytes(b"x")
            self.assertTrue(module.shards_complete(snapshot))


if __name__ == "__main__":
    unittest.main()
