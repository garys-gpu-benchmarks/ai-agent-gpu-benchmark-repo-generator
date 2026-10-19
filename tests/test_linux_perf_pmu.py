#!/usr/bin/env python3
# File: tests/test_linux_perf_pmu.py
# Description: 111/211/311/411 Linux perf PMU collector with stand-in perf and
# stress-ng (no PMU needed). AMD and NVIDIA used to ship different collectors:
# 111/311 published IPC-family metrics and left them blank when perf was
# blocked; 211/411 published TSC cycles / CPU time / bogo-ops instead and
# counted a missing stall event as 0. Both now ship this one file.
from __future__ import annotations

import csv
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "implementation_components"
COLLECTOR = COMPONENTS / "linux-perf-pmu-amd" / "files" / "scripts" / "collect_workload.py"
METRICS = (
    "instructions_per_cycle_ipc",
    "branch_misprediction_rate",
    "cache_misses_per_1000_instructions",
    "pipeline_stall_pct",
    "context_switches_during_workload_switches_s",
)

CONFIG = """sweep:
  num_cpus: 2
  workload_commands: stress-ng --cpu {num_cpus} --timeout {duration}s --metrics-brief,stress-ng --cache {num_cpus} --timeout {duration}s --metrics-brief
  event_list: cycles,instructions,L1-dcache-loads,bogus-event
  duration: 1
  output_format: csv
"""

STRESS_NG = """#!/bin/sh
echo "$@" >> "$FAKE_LOG"
if [ -n "$FAKE_STRESS_FAIL" ]; then echo "stress-ng: fail: boom" >&2; exit 2; fi
echo "stress-ng: info:  [10] dispatching hogs: 2 cpu"
echo "stress-ng: metrc: [10] stressor       bogo ops real time  usr time  sys time   bogo ops/s     bogo ops/s"
echo "stress-ng: metrc: [10]                           (secs)    (secs)    (secs)   (real time) (usr+sys time)"
echo "stress-ng: metrc: [10] cpu                 2000      1.00      2.00      0.00      2000.00        1000.00"
echo "stress-ng: info:  [10] successful run completed in 1.00 secs"
"""

# perf stat -x, [-o FILE] -e EVENTS -- CMD...   FAKE_PERF_MODE: intel | amd | nopmu | denied
PERF = r'''#!/usr/bin/env python3
import os, subprocess, sys
mode = os.environ.get("FAKE_PERF_MODE", "intel")
args = sys.argv[1:]
if args[:1] == ["--version"]:
    print("perf version 7.0"); sys.exit(0)
out = None; events = []
i = 1
while args[i] != "--":
    if args[i] == "-o": out = args[i + 1]; i += 2; continue
    if args[i] == "-e": events = args[i + 1].split(","); i += 2; continue
    i += 1
cmd = args[i + 1:]
known = {"cycles", "instructions", "branches", "branch-misses", "cache-misses", "context-switches",
         "stalled-cycles-backend", "stalled-cycles-frontend", "l1-dcache-loads"}
if mode == "intel": known.add("cycle_activity.stalls_total")
for e in events:
    if e.lower() not in known:
        sys.stderr.write(f"event syntax error: '{e}'\n"); sys.exit(129)
if mode == "denied":
    sys.stderr.write("Error:\nNo permission to enable cycles event.\n"); sys.exit(255)
rc = subprocess.call(cmd)
values = {"cycles": 4.0e9, "instructions": 8.0e9, "branches": 1.0e9, "branch-misses": 2.0e7,
          "cache-misses": 4.0e6, "context-switches": 30, "cycle_activity.stalls_total": 1.0e9,
          "stalled-cycles-backend": 2.0e9, "l1-dcache-loads": 3.0e9}
lines = []
for e in events:
    k = e.lower()
    hardware = k not in ("context-switches",)
    if mode == "nopmu" and hardware:
        lines.append(f"<not supported>,,{e},0,100.00,,")
    elif mode == "intel" and k.startswith("stalled-cycles"):
        lines.append(f"<not supported>,,{e},0,100.00,,")
    elif mode == "amd" and k == "stalled-cycles-frontend":
        lines.append(f"<not supported>,,{e},0,100.00,,")
    else:
        lines.append(f"{values.get(k, 1.0):.0f},,{'cpu_core/' + e + '/' if mode == 'intel' and k == 'cycles' else e},1000,{75.0 if k == 'l1-dcache-loads' else 100.0:.2f},,")
text = "# started on today\n\n" + "\n".join(lines) + "\n"
if out: open(out, "w").write(text)
else: sys.stderr.write(text)
sys.exit(rc)
'''


def write_exec(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


class LinuxPerfPmuCollectorTest(unittest.TestCase):
    def run_collector(self, mode: str | None = "intel", vendor_stall: str | None = None, extra_args=(), **env_extra):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        fakebin = root / "fakebin"
        write_exec(fakebin / "stress-ng", STRESS_NG)
        write_exec(fakebin / "perf", PERF)
        (root / "config").mkdir()
        (root / "config" / "benchmark_config.yaml").write_text(CONFIG, encoding="utf-8")
        env = dict(os.environ)
        env["PATH"] = f"{fakebin}:{env.get('PATH', '/usr/bin:/bin')}"
        env["FAKE_LOG"] = str(root / "stress.log")
        env["BENCHMARK_PERF_BIN"] = str(fakebin / "perf") if mode else "none"
        env["FAKE_PERF_MODE"] = mode or "intel"
        if vendor_stall:
            env["BENCHMARK_PMU_STALL_EVENT"] = vendor_stall
        env.update(env_extra)
        raw = root / "raw.csv"
        done = subprocess.run(
            [sys.executable, str(COLLECTOR), "--run-dir", str(root / "run"), "--raw-file", str(raw),
             "--profile", "smoke", "--config", str(root / "config" / "benchmark_config.yaml"), *extra_args],
            cwd=root, env=env, capture_output=True, text=True, timeout=120,
        )
        rows = list(csv.DictReader(raw.read_text(encoding="utf-8").splitlines())) if raw.is_file() else []
        log = (root / "stress.log").read_text(encoding="utf-8") if (root / "stress.log").is_file() else ""
        events = (root / "run" / "pmu_events.txt").read_text(encoding="utf-8") if (root / "run" / "pmu_events.txt").is_file() else ""
        return done, rows, log, events

    def test_combined_row_is_ratio_of_summed_counts(self):
        """Several commands publish one row whose ratios come from summed counts
        (2026-10-19): a mean of per-command ratios mixed unlike programs."""
        import importlib.util
        path = COMPONENTS / "linux-perf-pmu-amd" / "files" / "scripts" / "collect_workload.py"
        spec = importlib.util.spec_from_file_location("pmu_collector", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        common = {"duration_sec": 10, "elapsed_sec": 10, "cpu_time_sec": 40, "pmu_source": "perf",
                  "pmu_counter_running_pct": 100, "pipeline_stall_event": "x"}
        cpu = {**common, "cycles": 1e10, "instructions": 2e10, "branches": 1e9, "branch_misses": 1e7,
               "cache_misses": 2e6, "stall_cycles": 1e9, "context_switches": 200}
        branch = {**common, "cycles": 1e10, "instructions": 5e9, "branches": 1e8, "branch_misses": 5e7,
                  "cache_misses": 1e6, "stall_cycles": 6e9, "context_switches": 1000}
        row = module.combine_rows([cpu, branch], 4.0)
        self.assertAlmostEqual(row["instructions_per_cycle_ipc"], 1.25)
        self.assertAlmostEqual(row["branch_misprediction_rate"], 100.0 * 6e7 / 1.1e9)
        self.assertAlmostEqual(row["pipeline_stall_pct"], 35.0)
        self.assertAlmostEqual(row["context_switches_during_workload_switches_s"], 60.0)

    def test_both_vendors_ship_the_same_collector(self):
        amd = (COMPONENTS / "linux-perf-pmu-amd" / "files" / "scripts" / "collect_workload.py").read_bytes()
        nvidia = (COMPONENTS / "linux-perf-pmu-nvidia" / "files" / "scripts" / "collect_workload.py").read_bytes()
        self.assertEqual(amd, nvidia)

    def test_metric_columns_match_spec_keys(self):
        done, rows, log, _ = self.run_collector("intel", vendor_stall="cycle_activity.stalls_total")
        self.assertEqual(done.returncode, 0, done.stderr)
        for key in METRICS:
            self.assertIn(key, rows[0])
        self.assertEqual(len(rows), 2)
        self.assertIn("--cpu 2 --timeout 1s", log)
        self.assertIn("--cache 2 --timeout 1s", log)

    def test_intel_pmu_values(self):
        done, rows, _, events = self.run_collector("intel", vendor_stall="cycle_activity.stalls_total")
        self.assertEqual(done.returncode, 0, done.stderr)
        row = rows[0]
        self.assertAlmostEqual(float(row["instructions_per_cycle_ipc"]), 2.0)
        self.assertAlmostEqual(float(row["branch_misprediction_rate"]), 2.0)
        self.assertAlmostEqual(float(row["cache_misses_per_1000_instructions"]), 0.5)
        self.assertAlmostEqual(float(row["pipeline_stall_pct"]), 25.0)
        self.assertEqual(row["pipeline_stall_event"], "cycle_activity.stalls_total")
        self.assertGreater(float(row["context_switches_during_workload_switches_s"]), 0)
        self.assertAlmostEqual(float(row["stress_ng_bogo_ops_s"]), 2000.0)
        self.assertEqual(row["pmu_source"], "perf")
        self.assertAlmostEqual(float(row["pmu_counter_running_pct"]), 100.0)
        self.assertIn("events_dropped_unknown_to_perf=bogus-event", events)
        self.assertIn("L1-dcache-loads", events)

    def test_amd_uses_backend_stall_event(self):
        done, rows, _, _ = self.run_collector("amd", vendor_stall="stalled-cycles-backend")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertAlmostEqual(float(rows[0]["pipeline_stall_pct"]), 50.0)
        self.assertEqual(rows[0]["pipeline_stall_event"], "stalled-cycles-backend")

    def test_missing_stall_event_is_na_not_zero(self):
        done, rows, _, _ = self.run_collector("intel", vendor_stall="stalled-cycles-frontend")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(rows[0]["pipeline_stall_pct"].startswith("na (no stall-cycle event"), rows[0]["pipeline_stall_pct"])
        self.assertAlmostEqual(float(rows[0]["instructions_per_cycle_ipc"]), 2.0)

    def test_no_pmu_reports_reason_and_keeps_host_counters(self):
        done, rows, _, _ = self.run_collector("nopmu")
        self.assertEqual(done.returncode, 0, done.stderr)
        for key in METRICS[:4]:
            self.assertEqual(rows[0][key], "na (hardware PMU counters not available on this host)")
        self.assertGreater(float(rows[0]["context_switches_during_workload_switches_s"]), 0)
        self.assertAlmostEqual(float(rows[0]["stress_ng_bogo_ops_s"]), 2000.0)
        self.assertEqual(rows[0]["pmu_source"], "unavailable")

    def test_denied_reruns_workload_and_names_paranoid(self):
        done, rows, log, _ = self.run_collector("denied")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(rows[0]["instructions_per_cycle_ipc"].startswith("na (PMU access denied: perf_event_paranoid="))
        self.assertEqual(log.count("--cpu 2"), 1)  # perf never started it; the bare rerun did
        self.assertAlmostEqual(float(rows[0]["stress_ng_bogo_ops_s"]), 2000.0)

    def test_perf_missing(self):
        done, rows, _, _ = self.run_collector(None)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(rows[0]["instructions_per_cycle_ipc"].startswith("na (expected: perf not installed"))
        self.assertEqual(rows[0]["pmu_source"], "perf_missing")

    def test_runner_flags_override_yaml(self):
        done, rows, log, _ = self.run_collector(
            "intel", vendor_stall="cycle_activity.stalls_total",
            extra_args=("--num-cpus", "3", "--duration", "2", "--workload-commands",
                        "stress-ng --branch {num_cpus} --timeout {duration}s --metrics-brief"),
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("--branch 3 --timeout 2s", log)
        self.assertEqual(len(rows), 2)  # one command, duplicated for the two-sample rule

    def test_failed_workload_fails_run(self):
        done, _, _, _ = self.run_collector("intel", FAKE_STRESS_FAIL="1")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("workload exited", done.stderr + done.stdout)

    def test_missing_stress_ng_fails_instead_of_profiling_sleep(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "c.yaml").write_text(CONFIG, encoding="utf-8")
        env = {"PATH": "/nonexistent", "BENCHMARK_PERF_BIN": "none"}
        done = subprocess.run(
            [sys.executable, str(COLLECTOR), "--run-dir", str(root / "run"), "--raw-file", str(root / "r.csv"),
             "--config", str(root / "c.yaml")],
            env=env, capture_output=True, text=True, timeout=60,
        )
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("stress-ng is not installed", done.stderr + done.stdout)


if __name__ == "__main__":
    unittest.main()
