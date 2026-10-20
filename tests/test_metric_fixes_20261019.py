#!/usr/bin/env python3
# File: tests/test_metric_fixes_20261019.py
# Description: Metric fixes from the v1.0.16 review: 204/404 ECC disabled, x15 GPU
# lookup and cache-resident ledger note, 203/403 throttle total, 202/402 Xid lines,
# 201/401 package and driver compliance, 226/426 peak HBM fallback units.
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "implementation_components"
sys.dont_write_bytecode = True
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import metric_contract as mc  # noqa: E402


def load(component: str, rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, COMPONENTS / component / "files" / rel)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


ECC_DISABLED_Q = """==============NVSMI LOG==============
GPU 00000000:00:05.0
    ECC Mode
        Current                           : Disabled
        Pending                           : Disabled
    ECC Errors
        Volatile
            SRAM Correctable              : N/A
            DRAM Uncorrectable            : N/A
"""
ECC_ENABLED_Q = """    ECC Mode
        Current                           : Enabled
    ECC Errors
        Volatile
            SRAM Correctable              : 0
            DRAM Uncorrectable            : 0
"""


class SdcEccNvidia(unittest.TestCase):
    def test_ecc_disabled_is_expected_na_not_zero(self) -> None:
        module = load("sdc-ecc-nvidia", "scripts/collect_workload.py", "sdc_ecc_nvidia_0419")
        self.assertEqual(module.ecc_unavailable_reason(ECC_DISABLED_Q), "na (expected: ECC disabled)")
        self.assertEqual(module.ecc_unavailable_reason(ECC_ENABLED_Q), "")
        self.assertTrue(module.ecc_unavailable_reason("").startswith("na (expected:"))
        self.assertEqual(mc.classify_na("uncorrected_ecc_errors_count", module.ECC_DISABLED, {}), "expected")


class DeviceLookup(unittest.TestCase):
    def test_h100_names(self) -> None:
        self.assertEqual(mc.lookup_device("NVIDIA H100 80GB HBM3")[0], "H100 SXM")
        self.assertEqual(mc.lookup_device("NVIDIA H100 PCIe")[0], "H100 PCIe")
        self.assertEqual(mc.lookup_device("NVIDIA H100 NVL")[0], "H100 NVL")
        self.assertEqual(mc.lookup_device("AMD Instinct MI300X VF")[0], "MI300X")
        self.assertEqual(mc.lookup_device("")[0], "")

    def test_detect_gpu_name_reads_amd_market_name(self) -> None:
        def fake_run(command, **_kwargs):
            out = ""
            if command[0] == "amd-smi":
                out = "GPU: 0\n    ASIC:\n        MARKET_NAME: AMD Instinct MI300X VF\n"
            return mock.Mock(stdout=out)

        with mock.patch("subprocess.run", side_effect=fake_run):
            self.assertEqual(mc.detect_gpu_name(), "AMD Instinct MI300X VF")

    def test_cache_resident_note(self) -> None:
        metrics = mc.annotate_metrics({"bandwidth_gb_s_copy": 1879.0, "working_set_bytes": 25165824}, "NVIDIA H100 PCIe")
        note = mc.cache_resident_note(metrics, "NVIDIA H100 PCIe")
        self.assertIn("cache-resident at smoke size", note)
        self.assertIn("24 MiB", note)
        big = mc.annotate_metrics({"bandwidth_gb_s_copy": 3300.0, "working_set_bytes": 6 * 1024**3}, "NVIDIA H100 PCIe")
        self.assertEqual(mc.cache_resident_note(big, "NVIDIA H100 PCIe"), "")

    def test_ledger_and_summary_pass_a_gpu_name(self) -> None:
        ledger = (ROOT / "scripts" / "update_runtime_ledger.py").read_text(encoding="utf-8")
        self.assertIn("metric_results(args.summary, metrics, detected_gpu, annotated)", ledger)
        self.assertIn("cache_resident_note(annotated, detected_gpu)", ledger)
        summary = (ROOT / "scripts" / "print_metric_summary.py").read_text(encoding="utf-8")
        self.assertIn("gpu_name = detect_gpu_name()", summary)
        amd = (COMPONENTS / "babelstream-hbm-amd" / "files" / "scripts" / "collect_workload.py").read_text(encoding="utf-8")
        self.assertIn("lookup_device(detect_gpu_name())", amd)


class SystemStressThrottle(unittest.TestCase):
    def test_every_sample_carries_the_total(self) -> None:
        text = (COMPONENTS / "system-stress-nvidia" / "files" / "scripts" / "collect_workload.py").read_text(encoding="utf-8")
        self.assertIn('row["thermal_throttle_event_count"] = float(throttle_events)', text)


class GpuHealthXid(unittest.TestCase):
    def test_counts_only_nvrm_xid_lines(self) -> None:
        module = load("gpu-health-nvidia", "scripts/collect_workload.py", "gpu_health_nvidia_0419")
        dmesg = "\n".join([
            "[1.0] NVRM: Xid (PCI:0000:01:00): 79, pid=12, GPU has fallen off the bus.",
            "[2.0] some driver: xid table initialised",
            "[3.0] NVRM: Xid (PCI:0000:01:00): 13, pid=1, Graphics Exception",
        ])
        self.assertEqual(module.xid_count(0, dmesg), 2.0)
        self.assertEqual(module.xid_count(0, "[1.0] nothing here"), 0.0)
        self.assertEqual(module.xid_count(1, "dmesg: read kernel buffer failed: Operation not permitted"),
                         "na (expected: dmesg not readable)")


class SystemConfigNvidia(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load("system-config-nvidia", "scripts/collect_workload.py", "system_config_nvidia_0419")

    def test_packages_are_read(self) -> None:
        check = self.module.check_packages
        ok, findings = check(["cuda-toolkit", "nvidia-smi"],
                             {"cuda-nvcc-13-3": "13.3.73-1", "nvidia-utils-580": "580.95.05-0ubuntu1"},
                             expected_cuda="13.3", expected_driver="580", smi_owner="nvidia-utils-580", smi_ok=True)
        self.assertEqual(ok, [])
        self.assertIn("cuda-toolkit: cuda-nvcc-13-3 13.3", findings)
        wrong, _ = check(["cuda-toolkit"], {"cuda-nvcc-12-6": "12.6.85-1"},
                         expected_cuda="13.3", expected_driver="580", smi_owner="", smi_ok=True)
        self.assertEqual(len(wrong), 1)
        host, findings = check(["nvidia-smi"], {}, expected_cuda="13", expected_driver="580", smi_owner="", smi_ok=True)
        self.assertEqual(host, [])
        self.assertIn("host driver", findings[0])
        old, _ = check(["nvidia-smi"], {"nvidia-utils-570": "570.1"}, expected_cuda="13",
                       expected_driver="580", smi_owner="nvidia-utils-570", smi_ok=True)
        self.assertEqual(len(old), 1)

    def test_compliance_is_driver_versions_only(self) -> None:
        text = (COMPONENTS / "system-config-nvidia" / "files" / "scripts" / "collect_workload.py").read_text(encoding="utf-8")
        self.assertIn("driver_components = [module_ver, version_token(driver_ver), soname_ver]", text)
        self.assertNotIn("version_token(driver_ver) == module_ver)", text)


class JaxPeakHbm(unittest.TestCase):
    def test_nvidia_smi_mib_is_converted_to_gb(self) -> None:
        for component in ("jax-xla-nvidia", "jax-xla-amd"):
            text = (COMPONENTS / component / "files" / "scripts" / "gpu-bench-jax-xla-forwardpass.py").read_text(encoding="utf-8")
            self.assertIn("return float(lines[0].split()[0]) * 1024**2 / 1e9", text, component)


class SglangServingConcurrency(unittest.TestCase):
    def test_server_admits_what_the_client_sends(self) -> None:
        """131/331 ran the server at 2 requests at a time against a client concurrency of 8."""
        for component in ("sglang-serving-amd", "sglang-serving-nvidia"):
            text = (COMPONENTS / component / "files" / "run_benchmark.sh").read_text(encoding="utf-8")
            self.assertIn(
                'MAX_RUNNING_REQUESTS="$(enable_default "$(yaml_get max_running_requests)" '
                '"$(enable_default "${MAX_CONCURRENCY}" "2")")"',
                text,
                component,
            )
            self.assertLess(text.index('MAX_CONCURRENCY="${CONCURRENCY:-'), text.index("MAX_RUNNING_REQUESTS="))


NCCL_ONE_GPU = """#!/bin/sh
echo "$*" >> calls.txt
echo "collective=$5 num_gpus=1 bytes=$1 algbw_gb_s=10.0 busbw_gb_s=0.0 latency_us=5.0"
"""


class NcclSingleGpu(unittest.TestCase):
    def test_one_gpu_stops_after_the_first_round(self) -> None:
        import os
        import subprocess
        import tempfile

        script = COMPONENTS / "nccl-bandwidth-nvidia" / "files" / "scripts" / "collect_workload.py"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bin").mkdir()
            fake = root / "bin" / "nccl_bw"
            fake.write_text(NCCL_ONE_GPU, encoding="utf-8")
            fake.chmod(0o755)
            (root / "config").mkdir()
            (root / "config" / "benchmark_config.yaml").write_text(
                "sweep:\n  num_gpus: 1\n  min_bytes: 1024\n  max_bytes: 4096\n  num_iterations: 2\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(script), "--run-dir", "run", "--raw-file", "raw.csv", "--profile", "extended"],
                cwd=root, capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                timeout=60, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("[INFO] one GPU: stopped after round 1 of 24", result.stdout)
            calls = (root / "calls.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(calls), 3)  # 1024, 2048, 4096 once, not 24 times
            self.assertIn("na (requires at least two GPUs)", (root / "raw.csv").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
