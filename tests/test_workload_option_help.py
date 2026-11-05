#!/usr/bin/env python3
"""Workload-option help lines: description plus smoke, baseline, and extended values."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from workload_option_help import option_help_lines, override_example, replace_override_example, replace_workload_options  # noqa: E402


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
            "Parameters:\n"
            "  --old <value>            Override old\n"
            "\n"
            "General options:\n"
            "  --help                        Show this help and exit\n"
        )
        updated = replace_workload_options(original, ["  --numa-node <n>  NUMA node (smoke/baseline/extended: 0)"])
        self.assertIn("Parameters (override the profile's value):\n  --numa-node <n>", updated)
        self.assertNotIn("Override old", updated)
        self.assertIn("General options:\n  --help", updated)

    def test_stream_example_halves_baseline_threads(self) -> None:
        self.assertEqual(override_example(STREAM), "bash run_benchmark.sh --baseline --num-threads 8")

    def test_fourth_example_is_replaced_and_removed_when_absent(self) -> None:
        original = (
            "Examples:\n"
            "  bash run_benchmark.sh --smoke\n"
            "  bash run_benchmark.sh --baseline\n"
            "  bash run_benchmark.sh --extended\n"
            "  bash run_benchmark.sh --baseline --old 1\n"
        )
        updated = replace_override_example(original, "bash run_benchmark.sh --baseline --num-threads 8")
        self.assertIn("bash run_benchmark.sh --baseline --num-threads 8", updated)
        self.assertNotIn("--old", updated)
        self.assertIn("bash run_benchmark.sh --extended\n", updated)
        removed = replace_override_example(updated, None)
        self.assertNotIn("--num-threads", removed)
        self.assertIn("bash run_benchmark.sh --extended\n", removed)

    def test_workload_without_parameters_has_no_fourth_example(self) -> None:
        self.assertIsNone(override_example({"Parameter_01": "-", "Profile Parameter Values": "{}"}))


if __name__ == "__main__":
    unittest.main()
