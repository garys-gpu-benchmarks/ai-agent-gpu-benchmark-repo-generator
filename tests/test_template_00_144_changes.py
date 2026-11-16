#!/usr/bin/env python3
# File: tests/test_template_00_144_changes.py
# Description: TEMPLATE_00_144. gpu-bench-suite holds the laptop tools only;
#   run_benchmark_suite.sh (GPU host) ships in the bundles, which now take it
#   from the generator's user_scripts/ instead of from gpu-bench-suite.
# Execution: python3 -m pytest tests/test_template_00_144_changes.py
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ci_contract  # noqa: E402

PUBLISH = ROOT / "user_scripts" / "publish_benchmarks_to_github.sh"
SUITE_README = ROOT / "templates" / "suite-tools" / "README.md"


class SuiteToolsTests(unittest.TestCase):
    def test_suite_runner_not_emitted_to_gpu_bench_suite(self) -> None:
        self.assertNotIn("run_benchmark_suite.sh", ci_contract.SUITE_TOOL_SCRIPTS)
        self.assertEqual(set(ci_contract.SUITE_TOOL_SCRIPTS),
                         {"show_metrics.sh", "list_runs.sh", "get_benchmark_results.sh"})

    def test_master_copy_still_exists_for_bundles_and_vm(self) -> None:
        self.assertTrue((ROOT / "user_scripts" / "run_benchmark_suite.sh").is_file())

    def test_publish_takes_bundle_copy_from_generator(self) -> None:
        text = PUBLISH.read_text(encoding="utf-8")
        self.assertIn('SUITE_SCRIPT="${GEN}/${GENREPO}/user_scripts/run_benchmark_suite.sh"', text)
        self.assertNotIn('SUITE_SCRIPT="${TOOLS_DIR:+${TOOLS_DIR}/run_benchmark_suite.sh}"', text)
        self.assertNotIn('stop "the generator did not write run_benchmark_suite.sh', text)

    def test_publish_removes_previously_published_copy(self) -> None:
        text = PUBLISH.read_text(encoding="utf-8")
        self.assertRegex(text, re.compile(r"^\s*rm -f run_benchmark_suite\.sh\s*$", re.M))

    def test_suite_readme_lists_laptop_tools_only(self) -> None:
        text = SUITE_README.read_text(encoding="utf-8")
        self.assertNotIn("[`run_benchmark_suite.sh`](run_benchmark_suite.sh)", text)
        for name in ("get_benchmark_results.sh", "list_runs.sh", "show_metrics.sh"):
            self.assertIn(f"[`{name}`]({name})", text)


if __name__ == "__main__":
    unittest.main()
