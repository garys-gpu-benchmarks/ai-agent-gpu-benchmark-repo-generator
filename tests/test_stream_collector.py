"""STREAM collector (107, 207, 307, 407) checks.

  1. The AMD and NVIDIA components hold the same collector bytes.
  2. One STREAM run, one sample row. The old collector copied its one row to make a
     second sample (the old two-sample rule), so both samples were identical.
  3. Command-line overrides reach the collector. run_benchmark.sh passes
     --num-threads etc. only when the collector's --help lists them; the old
     collector did not, so overrides were printed as resolved but ignored.
  4. Stdout stays short: the STREAM report and the CSV go to the raw file only
     (they were printed once and the CSV twice), and GB/s values are rounded
     (97.82730000000001 became 97.8273).
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AMD = ROOT / "implementation_components/stream-collect-amd/files/scripts/collect_workload.py"
NVIDIA = ROOT / "implementation_components/stream-collect-nvidia/files/scripts/collect_workload.py"

STREAM_OUTPUT = """Function    Best Rate MB/s  Avg time     Min time     Max time
Copy:           97827.3     0.001636     0.001636     0.001636
Scale:          76506.6     0.002091     0.002091     0.002091
Add:           111871.4     0.002145     0.002145     0.002145
Triad:         117288.6     0.002046     0.002046     0.002046
Solution Validates: avg error less than 1.000000e-13 on all three arrays
"""


def load_collector():
    spec = importlib.util.spec_from_file_location("stream_collect", AMD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StreamCollectorTests(unittest.TestCase):
    def test_amd_and_nvidia_collectors_are_identical(self) -> None:
        self.assertEqual(AMD.read_bytes(), NVIDIA.read_bytes())

    def test_no_duplicated_sample_row(self) -> None:
        text = AMD.read_text(encoding="utf-8")
        self.assertNotIn("rows.append(dict(rows[0]))", text)
        self.assertEqual(load_collector().STREAM_SAMPLES, 1)

    def test_full_iteration_count_in_one_run(self) -> None:
        split = load_collector().ntimes_per_sample
        self.assertEqual(split(2, 1), 2)          # smoke: STREAM needs NTIMES >= 2
        self.assertEqual(split(30800, 1), 30800)  # baseline: the full count in one run
        self.assertEqual(split(45600, 1), 45600)  # extended
        self.assertEqual(split(1, 1), 2)

    def test_help_lists_override_flags(self) -> None:
        out = subprocess.run([sys.executable, str(AMD), "--help"], capture_output=True, text=True, check=True).stdout
        for flag in ("--numa-node", "--num-threads", "--thread-affinity", "--array-size", "--num-iterations"):
            self.assertIn(flag, out)

    def test_rates_are_rounded_gb_per_s(self) -> None:
        rates, missing = load_collector().parse_rates(STREAM_OUTPUT)
        self.assertEqual(rates, {"copy": 97.8273, "scale": 76.5066, "add": 111.8714, "triad": 117.2886})
        self.assertEqual(missing, "")
        self.assertEqual(load_collector().parse_rates("Copy: 1.0\n")[1], "scale")

    def test_stream_report_and_csv_not_printed(self) -> None:
        text = AMD.read_text(encoding="utf-8")
        self.assertNotIn("print(text)", text)
        self.assertNotIn("print(csv_block", text)
        self.assertNotIn('print(text, end="")', text)


if __name__ == "__main__":
    unittest.main()
