#!/usr/bin/env python3
"""Workload-option help lines: description plus smoke, baseline, and extended values."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from workload_option_help import option_help_lines, replace_workload_options  # noqa: E402


STREAM = {
    "Workload Number": "107",
    "Parameter_01": "numa_node",
    "Parameter_02": "num_threads",
    "Parameter_03": "array_size",
    "Parameter_04": "private_stream_knob",
    "Execution Description With Parameters": "private_stream_knob: STREAM triad passes.",
    "Profile Parameter Values": json.dumps(
        {
            "numa_node": {"smoke": "0", "baseline": "0", "extended": "0", "notes": "retune history"},
            "num_threads": {"smoke": "4", "baseline": "16", "extended": "20", "notes": "do not print"},
            "array_size": {"smoke": "10000000", "baseline": "20000000", "extended": "40000000"},
            "private_stream_knob": {"smoke": "1", "baseline": "1", "extended": "2"},
        }
    ),
}


class WorkloadOptionHelpTests(unittest.TestCase):
    def test_shared_value_is_printed_once_and_notes_are_omitted(self) -> None:
        lines = option_help_lines(STREAM)
        numa = next(line for line in lines if line.startswith("  --numa-node "))
        self.assertIn("NUMA node selected for placement", numa)
        self.assertIn("(smoke/baseline/extended: 0)", numa)
        self.assertNotIn("retune", numa)
        self.assertNotIn("notes", numa)

    def test_different_profile_values_are_all_printed(self) -> None:
        lines = option_help_lines(STREAM)
        threads = next(line for line in lines if line.startswith("  --num-threads "))
        size = next(line for line in lines if line.startswith("  --array-size "))
        self.assertIn("Execution threads issuing work", threads)
        self.assertIn("(smoke 4, baseline 16, extended 20)", threads)
        self.assertNotIn("do not print", threads)
        self.assertIn("Number of elements in benchmark arrays", size)
        self.assertIn("(smoke 10000000, baseline 20000000, extended 40000000)", size)

    def test_unshared_parameter_uses_the_execution_description(self) -> None:
        lines = option_help_lines(STREAM)
        knob = next(line for line in lines if line.startswith("  --private-stream-knob "))
        self.assertIn("STREAM triad passes", knob)
        self.assertIn("(smoke 1, baseline 1, extended 2)", knob)

    def test_replace_keeps_the_following_section(self) -> None:
        original = (
            "Workload options:\n"
            "  --old <value>            Override old\n"
            "\n"
            "Information:\n"
            "  --help                        Show this help and exit\n"
        )
        updated = replace_workload_options(original, ["  --numa-node <n>  NUMA node (smoke/baseline/extended: 0)"])
        self.assertIn("Workload options:\n  --numa-node <n>", updated)
        self.assertNotIn("Override old", updated)
        self.assertIn("Information:\n  --help", updated)


if __name__ == "__main__":
    unittest.main()
