#!/usr/bin/env python3
# File: tests/test_template_87_contracts.py
# Description: Fixture tests for TEMPLATE_00_87 create contracts, metrics D1-D4, and overlays.
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from framework_registry import resolve_flags  # noqa: E402
from generated_repo_directory import (  # noqa: E402
    generated_repo_directory_name,
    find_generated_repo,
)
from metric_contract import (  # noqa: E402
    coerce_metric_value,
    emit_percentile_metrics,
    itl_must_not_copy_tpot,
    split_percentile_keys,
    unmash_p50_key,
)
from platform_policy import match_policy  # noqa: E402
from print_metric_summary import display_label, extract_paren_keys, resolve_metrics  # noqa: E402
from text_io import ensure_gitkeep, write_lf  # noqa: E402


def _pct(values, p):
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round(p * (len(ordered) - 1)))))
    return ordered[idx]


class DashNamingTests(unittest.TestCase):
    def test_directory_uses_dash(self):
        self.assertEqual(
            generated_repo_directory_name("101", "sys-bench-amd-rocm-stack-validation-ubu2404"),
            "101-sys-bench-amd-rocm-stack-validation-ubu2404",
        )

    def test_finder_prefers_dash_over_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "201_gpu-bench-old").mkdir()
            (root / "201-gpu-bench-new").mkdir()
            found = find_generated_repo(root, "201", "gpu-bench-new")
            self.assertEqual(found.name, "201-gpu-bench-new")


class MetricContractTests(unittest.TestCase):
    def test_blank_is_not_zero(self):
        self.assertIsNone(coerce_metric_value(""))
        self.assertIsNone(coerce_metric_value(None))
        self.assertEqual(coerce_metric_value(0.0, zero_ok=True), 0.0)

    def test_d2_unmash_p50(self):
        self.assertEqual(
            unmash_p50_key("end_to_end_request_latency_p50_p95_p99_msec"),
            "end_to_end_request_latency_p50_msec",
        )

    def test_d3_split_keys(self):
        self.assertEqual(
            split_percentile_keys("ttft_p50_p95_p99_msec"),
            ["ttft_p50_msec", "ttft_p95_msec", "ttft_p99_msec"],
        )

    def test_d3_emit_triplet(self):
        metrics = emit_percentile_metrics("tpot", "_msec", [10.0, 20.0, 30.0], _pct)
        self.assertEqual(metrics["tpot_p50_msec"], 20.0)
        self.assertEqual(metrics["tpot_p95_msec"], 30.0)
        self.assertEqual(metrics["tpot_p99_msec"], 30.0)
        self.assertNotIn("tpot_p50_p95_p99_msec", metrics)

    def test_d4_itl_not_copied_from_tpot(self):
        self.assertEqual(itl_must_not_copy_tpot("", 12.5), "")
        self.assertEqual(itl_must_not_copy_tpot(12.5, 12.5), "")
        self.assertEqual(itl_must_not_copy_tpot(4.0, 12.5), 4.0)


class DisplayLabelTests(unittest.TestCase):
    def test_d1_prints_paren_key(self):
        description = "Peak CPU package temperature (peak_cpu_temp_c)"
        self.assertEqual(extract_paren_keys(description)[0], "peak_cpu_temp_c")
        self.assertEqual(display_label(description, "wrong_resolved_key"), "peak_cpu_temp_c")

    def test_d2_display_unmashes(self):
        description = "E2E latency (end_to_end_request_latency_p50_p95_p99_msec)"
        self.assertEqual(display_label(description, "ignored"), "end_to_end_request_latency_p50_msec")

    def test_resolves_key_from_later_parenthetical(self):
        items = [(
            "3",
            "Output token generation rate (decode), tokens/s (output_tokens_per_s)",
        )]
        found = resolve_metrics(items, {"output_tokens_per_s": 77.289})
        self.assertEqual(found[0][3], 77.289)
        self.assertEqual(display_label(found[0][1], found[0][2]), "output_tokens_per_s")

    def test_resolve_prefers_split_p50(self):
        items = [("1", "E2E (end_to_end_request_latency_p50_p95_p99_msec)")]
        metrics = {
            "end_to_end_request_latency_p50_msec": 11.0,
            "end_to_end_request_latency_p95_msec": 22.0,
            "end_to_end_request_latency_p99_msec": 33.0,
        }
        number, description, label, value = resolve_metrics(items, metrics)[0]
        self.assertEqual(value, 11.0)
        self.assertEqual(display_label(description, label), "end_to_end_request_latency_p50_msec")

    def test_print_splits_p50_p95_p99(self):
        from print_metric_summary import metric_print_fields

        description = "TTFT (ttft_p50_p95_p99_msec)"
        metrics = {"ttft_p50_msec": 1.0, "ttft_p95_msec": 2.0, "ttft_p99_msec": 3.0}
        fields = metric_print_fields(description, "ttft_p50_msec", 1.0, metrics)
        self.assertEqual([name for name, _value in fields], ["ttft_p50_msec"])
        self.assertEqual([value for _name, value in fields], [1.0])


class ReuseEnvTests(unittest.TestCase):
    def test_reuse_requires_matching_stamp_and_clean_registry_log(self):
        from create_one_workload import reuse_env_allowed

        stamp = "flags=BENCHMARK_INSTALL_PYTORCH=1;wheel=cu130"
        self.assertTrue(reuse_env_allowed(stamp, stamp, "PASS|SETUP pytorch"))
        self.assertFalse(reuse_env_allowed(stamp, "flags=;wheel=cu128", "PASS"))
        self.assertFalse(reuse_env_allowed(stamp, "", "PASS"))
        self.assertFalse(
            reuse_env_allowed(stamp, stamp, "framework_registry.py\nModuleNotFoundError: No module named 'yaml'")
        )


class FrameworkAndPolicyTests(unittest.TestCase):
    def test_nvidia_pytorch_not_vllm(self):
        flags = resolve_flags("PyTorch, CUDA", vendor="nvidia")
        self.assertEqual(flags["BENCHMARK_INSTALL_PYTORCH"], 1)
        flags = resolve_flags("vLLM, PyTorch", vendor="nvidia")
        self.assertEqual(flags["BENCHMARK_INSTALL_PYTORCH"], 0)
        self.assertEqual(flags["BENCHMARK_INSTALL_VLLM"], 1)

    def test_cpu_fio(self):
        flags = resolve_flags("fio, flexible I/O tester", vendor="cpu")
        self.assertEqual(flags["BENCHMARK_INSTALL_FIO"], 1)

    def test_nvidia_fio_iperf_nccl(self):
        self.assertEqual(resolve_flags("FIO", vendor="nvidia")["BENCHMARK_INSTALL_FIO"], 1)
        self.assertEqual(resolve_flags("iperf3", vendor="nvidia")["BENCHMARK_INSTALL_IPERF"], 1)
        self.assertEqual(resolve_flags("NCCL", vendor="nvidia")["BENCHMARK_INSTALL_NCCL"], 1)
        self.assertEqual(resolve_flags("PyTorch", vendor="nvidia")["BENCHMARK_INSTALL_NCCL"], 0)

    def test_registry_parses_without_pyyaml(self):
        import yaml
        from framework_registry import _load_simple_yaml

        text = (ROOT / "config" / "framework_registry.yaml").read_text(encoding="utf-8")
        self.assertEqual(_load_simple_yaml(text), yaml.safe_load(text))

    def test_amd_24_one_reboot(self):
        result = match_policy({"GPU Vendor": "AMD", "OS Version": "Ubuntu 24.04"}, os_release="24.04")
        self.assertTrue(result["ok"])
        self.assertEqual(result["reboots"], 1)
        self.assertEqual(result["driver"], "rocm")

    def test_os_mismatch_fails(self):
        result = match_policy({"GPU Vendor": "NVIDIA", "OS Version": "Ubuntu 24.04"}, os_release="26.04")
        self.assertFalse(result["ok"])


class CollectorContractTests(unittest.TestCase):
    def test_entry_point_is_not_the_first_overlay_file(self):
        from resolve_implementation_components import infer_defaults

        data = infer_defaults({
            "component_id": "cublas-gemm-nvidia",
            "overlay": ["scripts/collect_cublas_gemm.py", "scripts/build.sh", "src/cublas_gemm.cu"],
        })
        self.assertEqual(data["entry_point"], "scripts/collect_cublas_gemm.py")

    def test_adapter_satisfies_harness_and_overlay_runner_does_not_need_one(self):
        from apply_component_gaps import _collector_present, _write_collector_adapter

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "scripts").mkdir()
            (repo / "scripts" / "collect_cublas_gemm.py").write_text("print('ok')\n", encoding="utf-8")
            resolved = [{
                "component": {
                    "role": "source",
                    "overlay": ["scripts/collect_cublas_gemm.py"],
                }
            }]
            self.assertFalse(_collector_present(repo, resolved))
            _write_collector_adapter(repo, resolved)
            self.assertTrue((repo / "scripts" / "collect_workload.py").is_file())
            self.assertTrue(_collector_present(repo, resolved))

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "run_benchmark.sh").write_text("#!/bin/bash\npython scripts/benchmark_serving.py\n", encoding="utf-8")
            resolved = [{
                "component": {
                    "role": "collector",
                    "overlay": ["run_benchmark.sh", "scripts/benchmark_serving.py"],
                }
            }]
            self.assertTrue(_collector_present(repo, resolved))


class OverlayAndDocsTests(unittest.TestCase):
    def test_gitkeep_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            created = ensure_gitkeep(Path(tmp))
            self.assertIn("tests/fixtures/.gitkeep", created)
            self.assertTrue((Path(tmp) / "tests/fixtures/.gitkeep").is_file())

    def test_locked_overlay_fixture_keeps_custom_yaml(self):
        fixture = ROOT / "tests" / "fixtures" / "overlay_lock_sample"
        yaml_text = (fixture / "config" / "benchmark_config.yaml").read_text(encoding="utf-8")
        self.assertIn("overlay_marker: keep-me", yaml_text)
        self.assertIn("thresholds:", yaml_text)

    def test_fill_docs_rejects_leftover(self):
        from fill_generated_docs import render_template

        with self.assertRaises(SystemExit):
            render_template("Hello {{Missing Field}}\n", {"Repo Base Name": "x"})

    def test_write_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "note.txt"
            write_lf(path, "a\r\nb\r\n")
            self.assertEqual(path.read_bytes(), b"a\nb\n")


def _load_module(path: Path, name: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _generated_parser():
    from materialize_generated_harness import write_parser

    tmp = tempfile.TemporaryDirectory()
    repo = Path(tmp.name)
    (repo / "scripts").mkdir(parents=True)
    write_parser(repo)
    module = _load_module(repo / "scripts" / "parse_results.py", "generated_parse_results")
    module._keep = tmp
    return module


def _aggregates(module, rows, columns):
    aggregates = {}
    for col in columns:
        values = []
        for row in rows:
            number = module.to_number(row.get(col, ""))
            if isinstance(number, (int, float)) and not isinstance(number, bool):
                values.append(float(number))
        aggregates[col] = module.aggregate(col, values)
    return module.build_metrics_summary(columns, rows, aggregates)


class ConvolutionMetricTests(unittest.TestCase):
    def test_resolve_bandwidth_uses_aliased_column_not_batch_n(self):
        items = [("3", "Memory bandwidth, GB/s (memory_bandwidth_gb_s)")]
        found = resolve_metrics(items, {"n": 32, "gflops": 12345.0, "memory_bandwidth_gb_s": 771.0})
        self.assertEqual(found[0][3], 771.0)
        missing = resolve_metrics(items, {"n": 32, "gflops": 12345.0})
        self.assertEqual(missing[0][3], "NOT FOUND")

    def test_normalize_header_aliases_gb_s(self):
        module = _generated_parser()
        self.assertEqual(module.normalize_header("GB/s"), "memory_bandwidth_gb_s")

    def test_peak_token_uses_max_even_when_not_leading(self):
        module = _generated_parser()
        self.assertEqual(module.aggregate("kv_cache_peak_gb", [2.0, 7.0, 4.0]), 7.0)
        self.assertEqual(module.aggregate("kv_cache_usage_peak_pct", [20.0, 80.0, 50.0]), 80.0)
        self.assertEqual(module.aggregate("percent_of_fp64_tensor_peak", [40.0, 60.0]), 50.0)

    def test_direction_headline_is_forward_and_tier_still_drops_the_blend(self):
        module = _generated_parser()
        rows = []
        for direction, gbps in (("fwd", "1055"), ("bwd_data", "497"), ("bwd_weights", "761")):
            raw = {"direction": direction, "n": "32", "flopCnt": "1000", "GB/s": gbps, "GFLOPs": "10"}
            rows.append({module.normalize_header(key): value for key, value in raw.items()})
        summary = _aggregates(module, rows, list(rows[0].keys()))
        self.assertEqual(summary["memory_bandwidth_gb_s"], 1055)
        self.assertEqual(summary["memory_bandwidth_gb_s_fwd"], 1055)
        self.assertEqual(summary["memory_bandwidth_gb_s_bwd_data"], 497)
        self.assertEqual(summary["memory_bandwidth_gb_s_bwd_weights"], 761)
        self.assertEqual(summary["n"], 32)

        no_fwd = [row for row in rows if row["direction"] != "fwd"]
        no_fwd_summary = _aggregates(module, no_fwd, list(no_fwd[0].keys()))
        self.assertNotIn("memory_bandwidth_gb_s", no_fwd_summary)
        self.assertEqual(no_fwd_summary["memory_bandwidth_gb_s_bwd_data"], 497)

        tier_rows = [
            {"tier": "L1", "latency_ns": "1", "bytes": "8"},
            {"tier": "DRAM", "latency_ns": "80", "bytes": "8"},
        ]
        tier_summary = _aggregates(module, tier_rows, ["tier", "latency_ns", "bytes"])
        self.assertNotIn("latency_ns", tier_summary)
        self.assertEqual(tier_summary["latency_ns_l1"], 1)
        self.assertEqual(tier_summary["latency_ns_dram"], 80)
        self.assertEqual(tier_summary["bytes"], 8)

    def test_cudnn_result_parser_sums_search_and_rejects_a_missing_direction(self):
        module = _load_module(
            ROOT / "implementation_components" / "cudnn-convolution-nvidia" / "files" / "scripts" / "collect_cudnn_conv.py",
            "collect_cudnn_conv",
        )

        def line(direction, ms, tflops, gbps, search, algo):
            return (
                f"RESULT direction={direction} dtype=FP16 dtype_effective=HALF input_source=synthetic "
                f"batch_size=1 input_channels=8 input_height=16 input_width=16 output_channels=8 "
                f"kernel_height=3 kernel_width=3 stride_h=1 stride_w=1 pad_h=1 pad_w=1 group_count=1 "
                f"search_strategy=find algo={algo} workspace_bytes=0 warmup_iters=1 num_iterations=2 "
                f"kernel_time_msec={ms} tflops={tflops} memory_bandwidth_gb_s={gbps} "
                f"solver_search_msec={search} status=ok"
            )

        text = "\n".join([
            line("fwd", "4.5", "1.5", "10.5", "10.25", "1"),
            line("bwd_data", "5.5", "2.5", "11.5", "20.25", "2"),
            line("bwd_weights", "6.5", "3.5", "12.5", "30.25", "3"),
        ])
        row = module.pass_row(text, "all", {"dtype": "FP16"}, "pass1")
        self.assertEqual(row["kernel_time_msec"], 4.5)
        self.assertEqual(row["tflops_fwd"], 1.5)
        self.assertEqual(row["memory_bandwidth_gb_s"], 10.5)
        self.assertEqual(row["tflops_bwd_data"], 2.5)
        self.assertEqual(row["tflops_bwd_weights"], 3.5)
        self.assertEqual(row["kernel_time_msec_bwd_data"], 5.5)
        self.assertEqual(row["memory_bandwidth_gb_s_bwd_weights"], 12.5)
        self.assertEqual(row["solver_search_msec"], 60.75)
        self.assertEqual(row["algo_fwd"], 1)
        self.assertEqual(row["dtype_effective"], "HALF")
        self.assertEqual(row["pad_h"], 1)

        nan_text = "\n".join([
            line("fwd", "4.5", "1.5", "10.5", "nan", "1"),
            line("bwd_data", "5.5", "2.5", "11.5", "nan", "2"),
            line("bwd_weights", "6.5", "3.5", "12.5", "nan", "3"),
        ])
        nan_row = module.pass_row(nan_text, "all", {"dtype": "FP16"}, "pass1")
        self.assertEqual(nan_row["solver_search_msec"], "")

        with self.assertRaises(SystemExit):
            module.pass_row("\n".join(text.splitlines()[:2]), "all", {"dtype": "FP16"}, "pass1")

        backward_only = module.pass_row(line("bwd_data", "5.5", "2.5", "11.5", "8", "2"), "bwd_data", {}, "pass1")
        self.assertEqual(backward_only["kernel_time_msec"], "")
        self.assertEqual(backward_only["tflops_bwd_data"], 2.5)

        zero_algo = module.pass_row(line("fwd", "4.5", "1.5", "10.5", "10.25", "0"), "fwd", {"dtype": "FP16"}, "pass1")
        self.assertEqual(zero_algo["algo_fwd"], 0)


class ValidationZeroOkTests(unittest.TestCase):
    def test_algorithm_id_zero_is_allowed_and_chunk_backend_is_not_numeric(self):
        harness = (ROOT / "scripts" / "materialize_generated_harness.py").read_text(encoding="utf-8")
        self.assertIn('"algo"', harness)
        for vendor in ("nvidia", "amd"):
            script = (
                ROOT
                / "implementation_components"
                / f"rag-faiss-end2end-{vendor}"
                / "files"
                / "scripts"
                / "gpu-bench-rag-faiss-end2end.py"
            ).read_text(encoding="utf-8")
            self.assertIn("def _use_private_nltk_data", script)
            self.assertNotIn('1.0 if chunk_backend == "llamaindex" else 0.0', script)
            self.assertIn('"chunk_backend": chunk_backend', script)


if __name__ == "__main__":
    unittest.main()
