#!/usr/bin/env python3
"""103/303 sample the GPU only after their load is running (TEMPLATE_00_117).

rocblas-bench spends 3-4 s loading the rocBLAS library before its first GEMM.
With a fixed start, the 5 s smoke window saw only that start-up (1-4% GPU
utilization), so temperature and power were na, and baseline/extended
averaged those idle seconds into "sustained" power.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "implementation_components" / "system-stress-amd" / "files" / "scripts" / "collect_workload.py"
sys.path.insert(0, str(ROOT / "scripts"))

from metric_contract import classify_na  # noqa: E402


def load():
    spec = importlib.util.spec_from_file_location("system_stress_amd_wait", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeThread:
    def __init__(self, alive=True):
        self.alive = alive

    def is_alive(self):
        return self.alive


class FakeLoad:
    def __init__(self, error="", alive=True, ok_runs=1):
        self.error = error
        self.thread = FakeThread(alive)
        self.ok_runs = ok_runs


def reader(values):
    values = list(values)

    def read():
        return values.pop(0) if len(values) > 1 else values[0]

    return read


class WaitForLoadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load()

    def test_stops_once_utilization_reaches_ten_percent(self) -> None:
        calls = []
        values = [1.0, 3.0, 2.0, 98.0, 100.0]

        def read():
            calls.append(1)
            return values[len(calls) - 1]

        waited, peak = self.mod.wait_for_gpu_load(FakeLoad(), max_wait=5, poll_s=0, read_util=read)
        self.assertEqual(peak, 98.0)
        self.assertEqual(len(calls), 4)
        self.assertLess(waited, 5)

    def test_stops_when_the_load_fails(self) -> None:
        waited, peak = self.mod.wait_for_gpu_load(FakeLoad(error="rocblas-bench exited with code 1"), max_wait=5, poll_s=0, read_util=reader([1.0]))
        self.assertLess(waited, 1)
        self.assertEqual(peak, 1.0)

    def test_stops_when_the_load_thread_ended(self) -> None:
        waited, _ = self.mod.wait_for_gpu_load(FakeLoad(alive=False), max_wait=5, poll_s=0, read_util=reader([2.0]))
        self.assertLess(waited, 1)

    def test_gives_up_after_max_wait(self) -> None:
        waited, peak = self.mod.wait_for_gpu_load(FakeLoad(), max_wait=0.3, poll_s=0.05, read_util=reader([4.0]))
        self.assertGreaterEqual(waited, 0.3)
        self.assertEqual(peak, 4.0)

    def test_unreadable_utilization_counts_as_zero(self) -> None:
        waited, peak = self.mod.wait_for_gpu_load(FakeLoad(), max_wait=0.2, poll_s=0.05, read_util=reader(["na"]))
        self.assertEqual(peak, 0.0)
        self.assertGreaterEqual(waited, 0.2)

    def test_defaults_are_ten_percent_and_thirty_seconds(self) -> None:
        self.assertEqual(self.mod.UTIL_THRESHOLD_PCT, 10.0)
        self.assertEqual(self.mod.LOAD_WAIT_MAX_S, 30)


class LoadFailureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load()

    def test_loaded_window_publishes_values(self) -> None:
        rows = [{"gpu_util_pct": 98.0}, {"gpu_util_pct": 100.0}]
        self.assertEqual(self.mod.gpu_load_failure(FakeLoad(), rows, "smoke"), "")

    def test_idle_window_is_na_in_every_profile_and_counts_as_a_failure(self) -> None:
        rows = [{"gpu_util_pct": 1.0}, {"gpu_util_pct": 4.0}]
        for profile in ("smoke", "baseline", "extended"):
            reason = self.mod.gpu_load_failure(FakeLoad(), rows, profile)
            with self.subTest(profile=profile):
                self.assertTrue(reason.startswith("na (GPU load did not run:"), reason)
                self.assertIn("peaked at 4%", reason)
                self.assertIn("30 s", reason)
                self.assertNotIn("timed loop too short", reason)
                self.assertEqual(classify_na("sustained_gpu_power_w", reason, {"profile": profile}), "unexpected")

    def test_load_error_is_reported(self) -> None:
        reason = self.mod.gpu_load_failure(FakeLoad(error="rocblas-bench not found (setup did not compile it)", ok_runs=0), [], "smoke")
        self.assertIn("rocblas-bench not found", reason)


class OrderTest(unittest.TestCase):
    def test_gpu_load_waits_before_cpu_stress_and_sampling(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        main = text[text.index("def main()"):]
        start_load = main.index("GpuLoad(seconds + LOAD_WAIT_MAX_S")
        wait = main.index("wait_for_gpu_load(gpu_proc)")
        deadline = main.index("gpu_proc.deadline = time.time() + seconds")
        stress = main.index('["stress-ng"')
        sampling = main.index("rows.append(sample_row(")
        self.assertLess(start_load, wait)
        self.assertLess(wait, deadline)
        self.assertLess(deadline, stress)
        self.assertLess(stress, sampling)


if __name__ == "__main__":
    unittest.main()
