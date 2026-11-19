#!/usr/bin/env python3
# File: tests/test_system_stress_nvidia.py
# Description: 203/403 NVIDIA system stress collector with stand-in nvidia-smi,
# stress-ng, and bin/gpu_stress (no GPU needed). The collector used to run only
# stress-ng --cpu and ignore gpu_load_percent, so 403 reported an idle GPU
# (0% utilization, ~73 W on an H100 SXM) as its stress result.
from __future__ import annotations

import csv
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "implementation_components" / "system-stress-nvidia"
COLLECTOR = COMPONENT / "files" / "scripts" / "collect_workload.py"

CONFIG = """sweep:
  num_threads: 4
  cpu_load_percent: 50
  gpu_load_percent: 50
  temp_threshold: 75
  power_threshold: 500
  throttle_check: true
  ecc_check: true
  poll_interval: 1
  duration:
    smoke: 2
  output_format: csv
"""

NVIDIA_SMI = """#!/bin/sh
printf '%s, %s, %s, %s, 0\\n' "${FAKE_TEMP:-40}" "${FAKE_POWER:-300.5}" "${FAKE_UTIL:-50}" "${FAKE_THERMAL:-Not Active}"
"""

STRESS_NG = """#!/bin/sh
echo "$@" > stress-ng.args
sleep 1
echo "stress-ng: info: successful run completed"
"""

GPU_STRESS_OK = """#!/bin/sh
echo "GPU_LOAD_READY n=8192 period_ms=100 load_percent=$2"
sleep 1
echo "GPU_LOAD_DONE seconds=1.000 gemms=42 busy_pct=$2 tflops_busy=600.0"
"""

GPU_STRESS_BROKEN = """#!/bin/sh
echo "CUDA the provided PTX was compiled with an unsupported toolchain." >&2
exit 2
"""


def write_exec(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


@unittest.skipIf(sys.platform == "win32", "stand-in stress-ng and gpu_stress have no .exe; the collector runs only on the Linux VM")
class SystemStressNvidiaCollectorTest(unittest.TestCase):
    def run_collector(self, gpu_stress: str | None = GPU_STRESS_OK, **env_extra: str):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        fakebin = root / "fakebin"
        write_exec(fakebin / "nvidia-smi", NVIDIA_SMI)
        write_exec(fakebin / "stress-ng", STRESS_NG)
        if gpu_stress is not None:
            write_exec(root / "bin" / "gpu_stress", gpu_stress)
        (root / "config").mkdir()
        (root / "config" / "benchmark_config.yaml").write_text(CONFIG, encoding="utf-8")
        env = dict(os.environ)
        env["PATH"] = f"{fakebin}:{env.get('PATH', '/usr/bin:/bin')}"
        env.update(env_extra)
        raw = root / "raw.csv"
        done = subprocess.run(
            [sys.executable, str(COLLECTOR), "--run-dir", str(root / "run"), "--raw-file", str(raw),
             "--profile", "smoke", "--config", "config/benchmark_config.yaml",
             "--gpu-load-percent", "50", "--cpu-load-percent", "50", "--duration", "2"],
            cwd=root, env=env, capture_output=True, text=True, timeout=120,
        )
        rows = list(csv.DictReader(raw.read_text(encoding="utf-8").splitlines())) if raw.is_file() else []
        return done, rows, root

    def test_component_ships_gpu_load(self) -> None:
        data = json.loads((COMPONENT / "component.json").read_text(encoding="utf-8"))
        for path in ("src/gpu_stress.cu", "scripts/build.sh", "scripts/probe_setup.sh", "scripts/collect_workload.py"):
            self.assertIn(path, data["overlay"])
            self.assertTrue((COMPONENT / "files" / path).is_file(), path)
        build = (COMPONENT / "files" / "scripts" / "build.sh").read_text(encoding="utf-8")
        self.assertIn("nvcc_arch_flags", build)
        self.assertIn("-lcublas", build)
        self.assertIn('"${NVCC_ARCH_FLAGS[@]}"', build)

    def test_collector_accepts_every_runner_flag(self) -> None:
        help_text = subprocess.run([sys.executable, str(COLLECTOR), "--help"], capture_output=True, text=True).stdout
        for flag in ("--num-threads", "--cpu-load-percent", "--gpu-load-percent", "--temp-threshold",
                     "--power-threshold", "--throttle-check", "--ecc-check", "--poll-interval", "--duration"):
            self.assertIn(flag, help_text)

    def test_loaded_run_is_ok_and_applies_cpu_load(self) -> None:
        done, rows, root = self.run_collector()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertGreaterEqual(len(rows), 2)
        self.assertTrue(all(r["status"] == "ok" for r in rows))
        self.assertEqual(rows[0]["gpu_util_pct"], "50.0")
        self.assertIn("GPU load observed", done.stdout)
        args = (root / "stress-ng.args").read_text(encoding="utf-8").split()
        self.assertEqual(args[args.index("--cpu-load") + 1], "50")
        self.assertIn("GPU_LOAD_DONE", (root / "run" / "gpu_stress.txt").read_text(encoding="utf-8"))

    def test_idle_gpu_fails(self) -> None:
        done, _, _ = self.run_collector(FAKE_UTIL="0")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("GPU load not observed", done.stderr + done.stdout)

    def test_missing_gpu_stress_fails(self) -> None:
        done, _, _ = self.run_collector(gpu_stress=None)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("bin/gpu_stress missing", done.stderr + done.stdout)

    def test_gpu_stress_error_is_reported(self) -> None:
        done, _, _ = self.run_collector(gpu_stress=GPU_STRESS_BROKEN)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("unsupported toolchain", done.stderr + done.stdout)

    def test_temperature_over_threshold_marks_samples_error(self) -> None:
        done, rows, _ = self.run_collector(FAKE_TEMP="80")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue(rows and all(r["status"] == "error" for r in rows))
        self.assertIn("temp_threshold 75", rows[0]["error_message"])

    def test_power_over_threshold_marks_samples_error(self) -> None:
        done, rows, _ = self.run_collector(FAKE_POWER="650")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue(rows and all(r["status"] == "error" for r in rows))
        self.assertIn("power_threshold 500", rows[0]["error_message"])

    def test_thermal_slowdown_marks_samples_error(self) -> None:
        done, rows, _ = self.run_collector(FAKE_THERMAL="Active")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue(rows and all(r["status"] == "error" for r in rows))
        self.assertIn("thermal slowdown", rows[0]["error_message"])


if __name__ == "__main__":
    unittest.main()
