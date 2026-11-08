#!/usr/bin/env python3
# File: tests/test_health_monitor_params.py
# Description: 102/202/302/402 health parameters (2026-11-07): monitor_duration_sec,
# expected_gpu_count, min_pcie_link_width. Window results, pass/fail checks, CLI > yaml
# > default precedence, sampling loop, AMD sysfs filtering, and the workbook rows.
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "implementation_components"
sys.dont_write_bytecode = True
PARAMS = ["monitor_duration_sec", "expected_gpu_count", "min_pcie_link_width"]


def load(component: str, name: str):
    spec = importlib.util.spec_from_file_location(name, COMPONENTS / component / "files" / "scripts" / "collect_workload.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


AMD = load("rocm-health-amd", "rocm_health_amd_20261107")
NV = load("gpu-health-nvidia", "gpu_health_nvidia_20261107")


def amd_sample(temp=40.0, agents=1.0, width=16.0, speed=32.0, elapsed=0.0):
    return {"elapsed": elapsed, "temperature": temp, "agents": agents, "width": width, "speed": speed, "queues": 1.0}


def nv_sample(temp=40.0, devices=1.0, width=16.0, speed=32.0, elapsed=0.0):
    return {"elapsed": elapsed, "temperature": temp, "devices": devices, "width": width, "pcie_link_speed_gt_s": speed}


class WindowResult(unittest.TestCase):
    def test_amd_peak_temperature_and_narrowest_link(self):
        result = AMD.window_result([amd_sample(40), amd_sample(47, width=16), amd_sample(44)], 1, 16)
        self.assertEqual(result["gpu_temperature_c"], 47)
        self.assertEqual(result["pcie_link_width_lanes"], 16)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["error_message"], "")

    def test_amd_downtrained_link_fails(self):
        result = AMD.window_result([amd_sample(), amd_sample(width=8.0)], 1, 16)
        self.assertEqual(result["status"], "error")
        self.assertIn("x8 is narrower than min_pcie_link_width x16", result["error_message"])

    def test_amd_missing_gpu_fails_and_more_gpus_pass(self):
        self.assertEqual(AMD.window_result([amd_sample(agents=1), amd_sample(agents=1)], 2, 16)["status"], "error")
        self.assertEqual(AMD.window_result([amd_sample(agents=8), amd_sample(agents=8)], 1, 16)["status"], "ok")
        none = AMD.window_result([amd_sample(agents=0), amd_sample(agents=0)], 1, 16)
        self.assertIn("no GPU HSA agents", none["error_message"])

    def test_unreadable_width_is_skipped_not_failed(self):
        for module, sample in ((AMD, amd_sample), (NV, nv_sample)):
            result = module.window_result([sample(width=""), sample(width="")], 1, 16)
            self.assertEqual(result["status"], "ok")
            self.assertIn("check skipped", result["error_message"])
            self.assertEqual(result["pcie_link_width_lanes"], "")

    def test_nvidia_fewest_devices_and_slowest_link(self):
        result = NV.window_result([nv_sample(devices=2, speed=32.0), nv_sample(devices=1, speed=16.0)], 2, 16)
        self.assertEqual(result["cuda_devices_visible"], 1)
        self.assertEqual(result["pcie_link_speed_gt_s"], 16.0)
        self.assertEqual(result["status"], "error")
        self.assertIn("expected_gpu_count is 2", result["error_message"])


class Rows(unittest.TestCase):
    def test_window_values_repeat_on_every_row(self):
        samples = [amd_sample(40, elapsed=0.0), amd_sample(50, elapsed=1.0), amd_sample(45, elapsed=2.0)]
        result = AMD.window_result(samples, 1, 16)
        rows = AMD.rows_for(samples, result, 0.0, 0.0)
        self.assertEqual([r["gpu_temperature_c"] for r in rows], [50, 50, 50])
        self.assertEqual([r["sample_gpu_temperature_c"] for r in rows], [40, 50, 45])
        self.assertEqual(set(rows[0]), set(AMD.HEADER))

    def test_nvidia_rows_match_header(self):
        samples = [nv_sample(), nv_sample(elapsed=1.0)]
        rows = NV.rows_for(samples, NV.window_result(samples, 1, 16), 0.0, 0.0)
        self.assertEqual(set(rows[0]), set(NV.HEADER))

    def test_new_xids_keeps_unreadable_na(self):
        self.assertEqual(NV.new_xids(NV.DMESG_UNREADABLE, NV.DMESG_UNREADABLE), NV.DMESG_UNREADABLE)
        self.assertEqual(NV.new_xids(1.0, 3.0), 2.0)


class Monitor(unittest.TestCase):
    def run_monitor(self, module, duration):
        now = [0.0]
        calls = []

        def sampler(elapsed):
            calls.append(elapsed)
            return {"elapsed": elapsed}

        def sleep(seconds):
            now[0] += seconds

        return module.monitor(duration, sampler=sampler, clock=lambda: now[0], sleep=sleep), calls

    def test_one_sample_per_second(self):
        for module in (AMD, NV):
            samples, calls = self.run_monitor(module, 5)
            self.assertEqual(calls, [0.0, 1.0, 2.0, 3.0, 4.0, 5.0])

    def test_never_fewer_than_two_samples(self):
        for module in (AMD, NV):
            samples, _ = self.run_monitor(module, 0.1)
            self.assertEqual(len(samples), 2)


class Settings(unittest.TestCase):
    def args(self, **cli):
        base = {"profile": "baseline", "monitor_duration_sec": None, "expected_gpu_count": None, "min_pcie_link_width": None}
        base.update(cli)
        return SimpleNamespace(**base)

    def test_yaml_profile_values(self):
        params = {"monitor_duration_sec": {"smoke": 5, "baseline": 200, "extended": 580},
                  "expected_gpu_count": 1, "min_pcie_link_width": 16}
        for module in (AMD, NV):
            self.assertEqual(module.settings(self.args(), params), (200.0, 1, 16))

    def test_cli_overrides_yaml(self):
        params = {"monitor_duration_sec": 5, "expected_gpu_count": 1, "min_pcie_link_width": 16}
        for module in (AMD, NV):
            got = module.settings(self.args(monitor_duration_sec="30", expected_gpu_count="8", min_pcie_link_width="8"), params)
            self.assertEqual(got, (30.0, 8, 8))

    def test_defaults_when_absent_or_invalid(self):
        for module in (AMD, NV):
            self.assertEqual(module.settings(self.args(), {}), (5.0, 1, 16))
            self.assertEqual(module.settings(self.args(), {"monitor_duration_sec": "abc", "min_pcie_link_width": 0}), (5.0, 1, 16))

    def test_help_lists_the_flags_run_benchmark_passes(self):
        # run_benchmark.sh forwards an override only when the collector's --help names the flag.
        for component in ("rocm-health-amd", "gpu-health-nvidia"):
            text = (COMPONENTS / component / "files" / "scripts" / "collect_workload.py").read_text(encoding="utf-8")
            for flag in ("--monitor-duration-sec", "--expected-gpu-count", "--min-pcie-link-width"):
                self.assertIn(f'"{flag}"', text)


class AmdSysfs(unittest.TestCase):
    def card(self, root, name, vendor, width=None, speed=None):
        device = root / name / "device"
        device.mkdir(parents=True)
        (device / "vendor").write_text(vendor + "\n", encoding="utf-8")
        if width is not None:
            (device / "current_link_width").write_text(f"{width}\n", encoding="utf-8")
        if speed is not None:
            (device / "current_link_speed").write_text(f"{speed} GT/s PCIe\n", encoding="utf-8")

    def test_only_amd_gpu_cards_are_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.card(root, "card0", "0x1234", width=1, speed=2.5)       # VM virtual VGA
            self.card(root, "card1", "0x1002", width=16, speed=32.0)     # MI300X
            self.card(root, "card2", "0x1002", width=8, speed=16.0)      # downtrained MI300X
            (root / "card1-DP-1").mkdir()                                # connector entry
            self.assertEqual(sorted(AMD.amd_gpu_links(root)), [(8.0, 16.0), (16.0, 32.0)])

    def test_max_temperature_prefers_hotspot_across_gpus(self):
        text = "GPU: 0\n  HOTSPOT: 41 C\n  EDGE: N/A\nGPU: 1\n  HOTSPOT: 57 C\n"
        self.assertEqual(AMD.max_temperature(text), 57.0)


class NvidiaQuery(unittest.TestCase):
    def test_parses_every_gpu_line_and_converts_gen(self):
        self.assertEqual(NV.parse_query("30, 16, 5\n35, 8, 4\n"), [(30.0, 16.0, 32.0), (35.0, 8.0, 16.0)])
        self.assertEqual(NV.parse_query("[N/A], 16, 5\n"), [("", 16.0, 32.0)])
        self.assertEqual(NV.parse_query("nvidia-smi: not found\n"), [])


class Workbook(unittest.TestCase):
    def test_four_health_rows_name_the_three_parameters(self):
        from openpyxl import load_workbook

        wb = load_workbook(ROOT / "BenchmarkSpecDefinitions.xlsx", read_only=True, data_only=True)
        rows = list(wb["Workload_Definitions"].iter_rows(values_only=True))
        header = list(rows[0])
        slots = [header.index(f"Parameter_{i:02d}") for i in (1, 2, 3)]
        found = {str(r[0]): [r[i] for i in slots] for r in rows if str(r[0]) in {"102", "202", "302", "402"}}
        self.assertEqual(found, {w: PARAMS for w in ("102", "202", "302", "402")})
        profile = {(str(r[0]), r[2]): r[3:6] for r in wb["Parameters_SmokeBaselineExtend"].iter_rows(values_only=True)}
        for workload in ("102", "202", "302", "402"):
            self.assertEqual(tuple(profile[(workload, "monitor_duration_sec")]), (5, 200, 580))
            self.assertEqual(tuple(profile[(workload, "expected_gpu_count")]), (1, 1, 1))
            self.assertEqual(tuple(profile[(workload, "min_pcie_link_width")]), (16, 16, 16))


if __name__ == "__main__":
    unittest.main()
