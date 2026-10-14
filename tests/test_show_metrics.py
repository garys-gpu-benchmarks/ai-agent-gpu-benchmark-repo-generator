#!/usr/bin/env python3
# File: tests/test_show_metrics.py
# Description: The Metric_Short_Labels and Workload_Short_Names sheets are valid and
#              complete, show_metrics.sh's generated tables match them, and show_metrics.sh
#              prints a ledger with those labels (7 characters) and names (12 characters).
from __future__ import annotations

import contextlib
import csv
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_show_metrics as gsm  # noqa: E402

SCRIPT = ROOT / gsm.TEMPLATE_REL
BASH = shutil.which("bash")


class LabelSheetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        workbook = gsm.load_workbook_file(ROOT / gsm.WORKBOOK_NAME)
        cls.metrics = gsm.workbook_metrics(workbook)
        cls.labels = gsm.label_rows(workbook)
        cls.workloads = gsm.workbook_workloads(workbook)
        cls.names = gsm.name_rows(workbook)
        cls.sheets = list(workbook.sheetnames)
        workbook.close()

    def test_sheet_is_after_workload_definitions(self) -> None:
        # extract_benchmark_definition.py takes the first sheet that has the workload row.
        self.assertLess(self.sheets.index(gsm.DEFINITIONS_SHEET), self.sheets.index(gsm.LABEL_SHEET))
        self.assertLess(self.sheets.index(gsm.DEFINITIONS_SHEET), self.sheets.index(gsm.NAME_SHEET))

    def test_sheet_is_valid_and_complete(self) -> None:
        self.assertEqual(gsm.validate(self.metrics, self.labels), [])
        self.assertEqual(len(self.labels), len(self.metrics))

    def test_name_sheet_is_valid_and_complete(self) -> None:
        self.assertEqual(gsm.validate_names(self.workloads, self.names), [])
        self.assertEqual(len(self.names), len(self.workloads))
        self.assertTrue(all(len(r.short) <= gsm.MAX_NAME for r in self.names))

    def test_name_validation_catches_problems(self) -> None:
        rows = [gsm.NameRow(r.row, r.workload, r.full_name, r.short) for r in self.names]
        by_number = {r.workload: r for r in rows}
        by_number[101].short = "A Name Far Too Long"
        by_number[102].short = by_number[103].short          # same batch, two workloads
        by_number[301].short = "Other Name"                  # same full name as 101, different short name
        by_number[104].full_name = "Stale Name"
        rows.remove(by_number[132])
        errors = "\n".join(gsm.validate_names(self.workloads, rows))
        self.assertIn("longer than 12", errors)
        self.assertIn("also used by workload", errors)
        self.assertIn("one short name per full name", errors)
        self.assertIn("does not match", errors)
        self.assertIn("no row for workload 132", errors)

    def test_template_is_up_to_date(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(gsm.main(["--check", "--template-root", str(ROOT)]), 0)

    def test_validation_catches_bad_labels(self) -> None:
        bad = [gsm.LabelRow(row=r.row, workload=r.workload, number=r.number, key=r.key, label=r.label)
               for r in self.labels]
        bad[0].label = "TooLongLabel"
        bad[1].label = "Has space"
        bad.pop()
        errors = "\n".join(gsm.validate(self.metrics, bad))
        self.assertIn("longer than 7", errors)
        self.assertIn("may use only", errors)
        self.assertIn("no row for workload", errors)

    def test_metric_key_matches_show_metrics(self) -> None:
        self.assertEqual(gsm.metric_key("E2E, ms (end_to_end_query_latency_retrieval_generation_ms)"),
                         "end_to_end_query_latency_retrieval_generation_ms")
        self.assertEqual(gsm.metric_key("Output token generation rate (decode), tokens/s (output_tokens_per_s)"),
                         "output_tokens_per_s")
        self.assertEqual(gsm.metric_key("Solver search time (solver_search_msec), sum of cudnnFind wall time"),
                         "solver_search_msec")

    def test_overrides_only_where_a_workload_differs(self) -> None:
        rows = [gsm.LabelRow(2, 101, 1, "k", "A"), gsm.LabelRow(3, 201, 1, "k", "A"),
                gsm.LabelRow(4, 301, 1, "k", "B")]
        self.assertEqual(gsm.build_table(rows), [("k", "A"), ("301:k", "B")])


@unittest.skipIf(BASH is None or os.name == "nt", "needs bash and POSIX awk")
class ShowMetricsScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.ledger = Path(self._tmp.name) / "runtime_ledger.csv"
        cols = ["table_index_number", "run_id", "workload_number", "benchmark_profile", "exit_code", "workload_name"]
        for i in range(1, 8):
            cols += [f"metric_{i}_def", f"metric_{i}_result"]
        defs = ["E2E, ms (end_to_end_query_latency_retrieval_generation_ms)",
                "Generation TTFT, ms (generation_phase_time_to_first_token_ms)",
                "FAISS index vectors (faiss_index_ntotal)"]
        rows = [("32", "smoke", "0", ["269.017", "41.308", "217"]),
                ("64", "baseline", "0", ["837.016", "74.934", "898"]),
                ("65", "baseline", "1", ["830.228", "74.880", "898"])]
        with self.ledger.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(cols)
            for idx, profile, code, values in rows:
                row = [idx, f"r{idx}", "332", profile, code, "RAG Pipeline Sweep"]
                for i in range(7):
                    row += [defs[i], values[i]] if i < len(defs) else ["", ""]
                writer.writerow(row)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([BASH, str(SCRIPT), *args, "--file", str(self.ledger)],
                              capture_output=True, text=True, check=False)

    def test_prints_generated_labels(self) -> None:
        result = self._run("332")
        self.assertEqual(result.returncode, 0, result.stderr)
        header = next(line for line in result.stdout.splitlines() if line.startswith("WL "))
        self.assertEqual(header.split()[5:], ["E2E_ms", "TTFT_ms", "FAISS_N"])
        self.assertEqual(header.split()[4], "Exit")
        first = next(line for line in result.stdout.splitlines() if line.startswith("332 "))
        self.assertEqual(first[4:16].rstrip(), "RAG Sweep")
        self.assertEqual(first[32:37], "    0")
        failed = next(line for line in result.stdout.splitlines() if "65*" in line)
        self.assertEqual(failed[32:37], "    1")
        self.assertIn("Exit Code (0 is pass)", result.stdout)
        self.assertIn("mean", result.stdout)
        self.assertTrue(all(len(line) <= 93 for line in result.stdout.splitlines()))

    def test_profile_filter_and_missing_workload(self) -> None:
        result = self._run("332", "--smoke", "--no-legend")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("baseline", result.stdout)
        self.assertEqual(self._run("999").returncode, 1)

    def test_no_lab_hosts(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertNotRegex(text, r"\b(?!203\.0\.113\.)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
        self.assertIsNone(re.search(r"__[A-Z][A-Z0-9_]*__", text))


if __name__ == "__main__":
    unittest.main()
