"""NUMA cache collector (110, 210, 310, 410): short console output.

The full numa_sweep transcript (parameter echo, perf counter blocks, METRICS_CSV)
goes to numa_sweep_transcript.txt beside --output. The console keeps the INFO
notes, one line per measured case and its ns/access. The AMD wrapper no longer
prints the CSV it writes.
"""
from __future__ import annotations

import importlib.util
import io
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = ROOT / "implementation_components/numa-cache-collector/files/scripts/collect_numa_cache.py"
WRAPPER = ROOT / "implementation_components/numa-cache-wrapper-amd/files/scripts/collect_workload.py"

TRANSCRIPT = """# INFO only one NUMA node is visible so remote may equal local
# numa_sweep dependent pointer-chase raw transcript
# profile=smoke
# target=0 size=32768 cpunodebind=0 membind=0
# numa_sweep_exit=0
ns/access = 5.7016
bandwidth_gb_s = 1.4031

 Performance counter stats for 'numactl ... bin/numa_sweep --size 32768':

             16984      cache-misses
# METRICS_CSV
check,source_numa_node
summary,0
"""


def load():
    spec = importlib.util.spec_from_file_location("numa_cache_output", COLLECTOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NumaCacheOutputTests(unittest.TestCase):
    def test_console_shows_only_useful_lines(self) -> None:
        transcript, console = io.StringIO(), io.StringIO()
        stream = load().ConsoleFilter(transcript, console)
        stream.write(TRANSCRIPT)
        self.assertEqual(transcript.getvalue(), TRANSCRIPT)
        self.assertEqual(console.getvalue().splitlines(), [
            "[INFO] only one NUMA node is visible so remote may equal local",
            "[INFO] measuring target=0 size=32768 cpunodebind=0 membind=0",
            "[INFO]   ns/access = 5.7016",
        ])

    def test_verbose_shows_everything(self) -> None:
        transcript, console = io.StringIO(), io.StringIO()
        load().ConsoleFilter(transcript, console, verbose=True).write(TRANSCRIPT)
        self.assertEqual(console.getvalue(), TRANSCRIPT)

    def test_transcript_file_and_flags(self) -> None:
        text = COLLECTOR.read_text(encoding="utf-8")
        self.assertIn('"numa_sweep_transcript.txt"', text)
        self.assertIn('"--transcript"', text)
        self.assertIn('"--verbose"', text)

    def test_wrapper_does_not_print_csv(self) -> None:
        text = WRAPPER.read_text(encoding="utf-8")
        self.assertNotIn('print(text, end="")', text)


if __name__ == "__main__":
    unittest.main()
