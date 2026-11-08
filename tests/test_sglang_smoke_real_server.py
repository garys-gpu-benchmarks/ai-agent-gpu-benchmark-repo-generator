#!/usr/bin/env python3
# File: tests/test_sglang_smoke_real_server.py
# Description: SGLang workloads x30 and x31 start the real SGLang server on
#   every profile, smoke included (2026-11-07). Smoke used to start
#   scripts/tiny_sglang_server.py, which proved nothing about SGLang. The stub
#   stays in the overlays only for the local client tests
#   (tests/test_sglang_stub_clients.py); no runner or setup check may use it.
#   TEMPLATE_00_127: NVIDIA smoke may add --disable-cuda-graph, nothing else.
from __future__ import annotations

import unittest
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "implementation_components"
RUNNERS = (
    "sglang-prompt-response-nvidia",
    "sglang-serving-nvidia",
    "sglang-prompt-response-amd",
    "sglang-serving-amd",
)
AMD_ENSURE = ("sglang-prompt-response-amd", "sglang-serving-amd")
WORKLOADS = {"130", "131", "230", "231", "330", "331", "430", "431"}


class SglangSmokeRealServer(unittest.TestCase):
    def test_every_profile_launches_sglang(self) -> None:
        for component in RUNNERS:
            with self.subTest(component=component):
                text = (COMPONENTS / component / "files" / "run_benchmark.sh").read_text(encoding="utf-8")
                self.assertNotIn("tiny_sglang_server.py", text)
                self.assertNotIn("BENCHMARK_SERVER_KIND=stub", text)
                # TEMPLATE_00_127: the only smoke branch allowed is the NVIDIA one that
                # adds --disable-cuda-graph to the same launch_server command.
                smoke_branches = text.count('"${PROFILE}" == "smoke"')
                if component.endswith("nvidia"):
                    self.assertEqual(smoke_branches, 1)
                    block = text.split('if [[ "${PROFILE}" == "smoke" ]]; then', 1)[1].split("\n  fi\n", 1)[0]
                    code = [line.strip() for line in block.splitlines() if line.strip() and not line.strip().startswith("#")]
                    self.assertEqual(code, ['server_cmd+=" --disable-cuda-graph"'])
                else:
                    self.assertEqual(smoke_branches, 0)
                self.assertEqual(text.count("-m sglang.launch_server --model-path"), 1)

    def test_amd_setup_check_does_not_skip_smoke(self) -> None:
        for component in AMD_ENSURE:
            with self.subTest(component=component):
                text = (COMPONENTS / component / "files" / "scripts" / "ensure_setup.sh").read_text(encoding="utf-8")
                self.assertNotIn("tiny_sglang_server.py", text)
                self.assertNotIn('"${PROFILE}" == "smoke"', text)
                self.assertIn('-c "import sglang"', text)

    def test_workbook_text_no_longer_describes_a_stub_smoke(self) -> None:
        book = openpyxl.load_workbook(ROOT / "BenchmarkSpecDefinitions.xlsx", read_only=True, data_only=True)
        rows = book["Workload_Definitions"].iter_rows(values_only=True)
        header = next(rows)
        seen = set()
        for row in rows:
            number = str(row[0]).strip()
            if number not in WORKLOADS:
                continue
            seen.add(number)
            for name, value in zip(header, row):
                if isinstance(value, str):
                    with self.subTest(workload=number, column=name):
                        self.assertNotIn("tiny_sglang", value)
                        self.assertNotIn("tiny server", value)
        self.assertEqual(seen, WORKLOADS)


if __name__ == "__main__":
    unittest.main()
