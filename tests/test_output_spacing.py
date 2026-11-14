"""Blank lines in every run's console output (all workloads).

  1. One blank line before "[INFO] ===== Benchmark Summary =====": the generated
     runner (materialize_generated_harness.py) and every overlay run_benchmark.sh.
  2. One blank line before "Runtime entry added to ..." (update_runtime_ledger.py).
  3. One blank line at the very end, before the next shell prompt: finish_benchmark_run
     on success and die() on failure (scripts/lib/common.sh).
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = '  echo "[INFO] ===== Benchmark Summary ====="'


def function_body(text: str, name: str) -> str:
    start = text.index(f"{name}() {{")
    return text[start:text.index("\n}", start)]


class OutputSpacingTests(unittest.TestCase):
    def test_blank_line_before_summary_in_every_runner(self) -> None:
        runners = [ROOT / "scripts/materialize_generated_harness.py"]
        runners += sorted(ROOT.glob("implementation_components/*/files/run_benchmark.sh"))
        self.assertGreater(len(runners), 1)
        for path in runners:
            lines = path.read_text(encoding="utf-8").splitlines()
            index = lines.index(HEADER)
            self.assertTrue(lines[index - 1].strip().startswith("echo  #"), path)

    def test_blank_line_before_ledger_message(self) -> None:
        text = (ROOT / "scripts/update_runtime_ledger.py").read_text(encoding="utf-8")
        lines = text.splitlines()
        index = next(i for i, line in enumerate(lines) if "Runtime entry added to" in line)
        self.assertTrue(lines[index - 1].strip().startswith("print()"))

    def test_blank_line_at_end_of_run(self) -> None:
        text = (ROOT / "scripts/lib/common.sh").read_text(encoding="utf-8")
        self.assertTrue(function_body(text, "finish_benchmark_run").rstrip().splitlines()[-1].strip().startswith("echo"))
        body = function_body(text, "die").splitlines()
        self.assertTrue(body[body.index("  exit 1") - 1].strip().startswith("echo"))


if __name__ == "__main__":
    unittest.main()
