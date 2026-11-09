#!/usr/bin/env python3
"""Workload-option help lines: description plus smoke, baseline, and extended values."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from workload_option_help import help_header_lines, option_help_lines, override_example, replace_help_header, replace_override_example, replace_workload_options  # noqa: E402


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
    HEADER = {
        "Workload Name": "System Config Verification",
        "Main Goal": "Analyze ROCm software stack consistency against yaml expectations",
        "Validation Objective": "Validates ROCm tools, kernel match, amdgpu driver, packages, and GPU device-node permissions",
        "Command Tools Executed": "Run rvs --version, rocminfo, amd-smi version, amd-smi static, uname -a, modinfo amdgpu, hipcc --version, and dpkg-query.",
    }

    def test_help_header_labels_no_periods_and_wrapping(self) -> None:
        lines = help_header_lines(self.HEADER)
        self.assertEqual(lines[0], "Workload Name:          System Config Verification")
        self.assertEqual(lines[1], "Main Goal:              Analyze ROCm software stack consistency against yaml expectations")
        self.assertTrue(lines[2].startswith("Command Tools Executed: Run rvs --version"))
        self.assertFalse(any(line.startswith("Validation Objective:") for line in lines))  # removed 2026-11-06
        self.assertTrue(all(len(line) <= 100 for line in lines))
        self.assertTrue(lines[3].startswith(" " * 24))  # wrapped continuation sits under the value
        joined = "\n".join(lines)
        self.assertTrue(joined.endswith("dpkg-query"))  # a trailing period in the cell is dropped
        self.assertFalse(any(line.rstrip().endswith(".") for line in lines))  # no value ends with a period (2026-11-07)
        self.assertNotIn("amd-smi\n", "\n".join(lines))  # no break inside a hyphenated word

    def test_help_header_replaces_overlay_description(self) -> None:
        text = (
            "usage() {\n  cat <<'USAGE'\nUsage: bash run_benchmark.sh [OPTIONS]\n\n"
            "Every profile starts a server.\nSecond prose line.\n\nProfiles (default: --smoke):\n"
            "  --smoke                       Run smoke profile\nUSAGE\n}\n"
        )
        updated = replace_help_header(text, self.HEADER)
        self.assertNotIn("Every profile starts a server.", updated)
        self.assertIn("cat <<'USAGE'\nUsage: bash run_benchmark.sh [OPTIONS]\n\nWorkload Name:          System Config Verification\n", updated)
        self.assertNotIn("Validation Objective:", updated)
        self.assertIn("dpkg-query\n\nProfiles (default: --smoke):", updated)
        self.assertEqual(replace_help_header(updated, self.HEADER), updated)  # idempotent

    def test_help_page_has_no_leading_blank_line(self) -> None:
        # TEMPLATE_00_127 and earlier opened the page with a blank line; the
        # first printed line is now "Usage:" (GNU / argparse / git convention).
        for blanks in ("", "\n", "\n\n", "  \n"):
            text = (
                f"usage() {{\n  cat <<'USAGE'\n{blanks}Usage: bash run_benchmark.sh [OPTIONS]\n\n"
                "Old prose.\n\nProfiles (default: --smoke):\n  --smoke                       Run smoke profile\nUSAGE\n}\n"
            )
            updated = replace_help_header(text, self.HEADER)
            self.assertIn("cat <<'USAGE'\nUsage: bash run_benchmark.sh [OPTIONS]\n", updated, repr(blanks))
            self.assertEqual(replace_help_header(updated, self.HEADER), updated)

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
        start = lines.index(next(line for line in lines if line.startswith("  --array-size ")))
        size = lines[start:start + 4]  # too wide for one line: description, then one line per profile
        self.assertIn("Execution threads issuing work", threads)
        self.assertIn("(smoke 4, baseline 16, extended 20)", threads)
        self.assertNotIn("do not print", threads)
        self.assertIn("Number of elements in benchmark arrays", size[0])
        self.assertEqual([line.split() for line in size[1:]],
                         [["smoke:", "10000000"], ["baseline:", "20000000"], ["extended:", "40000000"]])

    def test_unshared_parameter_uses_the_execution_description(self) -> None:
        lines = option_help_lines(STREAM)
        start = lines.index(next(line for line in lines if line.startswith("  --private-stream-knob ")))
        knob = "\n".join(lines[start:start + 4])
        self.assertIn("STREAM triad passes", knob)
        self.assertIn("smoke/baseline: 1", knob)
        self.assertIn("extended:       2", knob)

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

    def test_long_entry_wraps_per_profile_within_100_columns(self) -> None:
        commands = ",".join(
            f"stress-ng --{kind} {{num_cpus}} --timeout {{duration}}s --metrics-brief"
            for kind in ("cpu", "cache", "branch", "vm")
        )
        fields = {
            "Parameter_01": "workload_commands",
            "Parameter_02": "omit_initial_seconds",
            "Execution Description With Parameters": "",
            "Profile Parameter Values": json.dumps(
                {
                    "workload_commands": {"smoke": commands.split(",stress-ng --branch")[0], "baseline": commands, "extended": commands},
                    "omit_initial_seconds": {"smoke": "0", "baseline": "1", "extended": "1"},
                }
            ),
        }
        lines = option_help_lines(fields)
        self.assertTrue(all(len(line) <= 100 for line in lines), lines)
        self.assertTrue(lines[0].startswith("  --workload-commands <value>"))
        self.assertNotIn("(smoke", lines[0])  # values moved to their own lines
        self.assertTrue(any(line.lstrip().startswith("smoke:") for line in lines))
        self.assertTrue(any(line.lstrip().startswith("baseline/extended:") for line in lines))  # equal values share a line
        joined = " ".join(line.strip() for line in lines)
        self.assertIn("stress-ng --vm {num_cpus}", joined)  # nothing dropped
        # each list item after the first starts its own line where it fits
        self.assertTrue(any(line.strip().startswith("stress-ng --cache") for line in lines))
        # a flag too long for the 32-column field puts its description on the next line
        omit = lines.index(next(line for line in lines if line.startswith("  --omit-initial-seconds")))
        self.assertEqual(lines[omit].rstrip(), "  --omit-initial-seconds <value>")
        self.assertTrue(lines[omit + 1].startswith(" " * 32) and lines[omit + 1].strip())

    def test_short_entry_keeps_the_one_line_form(self) -> None:
        lines = option_help_lines(STREAM)
        self.assertTrue(all(len(line) <= 100 for line in lines))
        self.assertEqual(lines[0], "  --numa-node <n>               NUMA node selected for placement (smoke/baseline/extended: 0)")
        self.assertTrue(lines[1].startswith("  --num-threads <n>") and lines[1].endswith("(smoke 4, baseline 16, extended 20)"))

    def test_workload_without_parameters_has_no_fourth_example(self) -> None:
        self.assertIsNone(override_example({"Parameter_01": "-", "Profile Parameter Values": "{}"}))


if __name__ == "__main__":
    unittest.main()
