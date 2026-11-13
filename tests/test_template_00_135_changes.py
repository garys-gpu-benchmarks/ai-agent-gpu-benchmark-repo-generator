#!/usr/bin/env python3
# File: tests/test_template_00_135_changes.py
# Description: TEMPLATE_00_135 runtime ledger columns. Six timing columns
#   (script, setup and benchmark start and runtime), the renamed
#   start_benchmark_datetime and runtime_benchmark_mm_ss with migration of old
#   ledgers, the repeat/suite/network context columns, the driver and kernel
#   versions, the exports in common.sh, and the suite's suite ID, pass number
#   and one download test. No network is used.
from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "scripts" / "update_runtime_ledger.py"
COMMON = ROOT / "scripts" / "lib" / "common.sh"
SUITE = ROOT / "user_scripts" / "run_benchmark_suite.sh"
BASH = shutil.which("bash")
NS = 1_000_000_000
T0 = 1_794_000_000 * NS  # 2026-11-06T21:20:00Z


def load_ledger():
    spec = importlib.util.spec_from_file_location("update_runtime_ledger_00_135", LEDGER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ledger = load_ledger()


class LedgerColumnTests(unittest.TestCase):
    def test_order(self) -> None:
        cols = list(ledger.LEDGER_COLUMNS)
        self.assertEqual(cols[:10], [
            "table_index_number", "run_id", "workload_number", "workload_name", "benchmark_profile",
            "result_status", "exit_code", "metrics_na_count", "failure_stage", "failure_detail"])
        self.assertEqual(cols[10:16], [
            "start_script_datetime", "start_setup_datetime", "start_benchmark_datetime",
            "runtime_script_mm_ss", "runtime_setup_mm_ss", "runtime_benchmark_mm_ss"])
        self.assertEqual(cols[16:24], [
            "workload_repeat_index", "workload_repeat_total", "suite_id", "suite_repeat_index",
            "suite_repeat_total", "network_download_mb_s", "gpu_driver_version", "kernel_version"])
        self.assertEqual(cols[24:26], ["runtime_root_dir", "raw_run_dir"])
        self.assertEqual(cols[-1], "gpu_model_note")
        self.assertEqual(len(cols), len(set(cols)))
        for old in ("start_datetime", "total_runtime_mm_ss"):
            self.assertNotIn(old, cols)


class TimingColumnTests(unittest.TestCase):
    def env(self, **extra: str) -> dict[str, str]:
        base = {"BENCHMARK_SCRIPT_START_NS": str(T0), "BENCHMARK_SETUP_START_NS": str(T0 + 10 * NS)}
        base.update(extra)
        return base

    def test_full_run(self) -> None:
        env = self.env(BENCHMARK_START_NS=str(T0 + 70 * NS), BENCHMARK_MEASURE_STARTED="1")
        cols = ledger.timing_columns(env, benchmark_start="2026-11-06T21:21:10Z",
                                     benchmark_runtime="120", now_ns=T0 + 200 * NS)
        self.assertEqual(cols, {
            "start_script_datetime": "2026-11-06T21:20:00Z",
            "start_setup_datetime": "2026-11-06T21:20:10Z",
            "start_benchmark_datetime": "2026-11-06T21:21:10Z",
            "runtime_script_mm_ss": "03:20",
            "runtime_setup_mm_ss": "01:00",
            "runtime_benchmark_mm_ss": "02:00",
        })

    def test_setup_failure_leaves_benchmark_blank(self) -> None:
        env = self.env(BENCHMARK_START_NS=str(T0 + 10 * NS), BENCHMARK_MEASURE_STARTED="0")
        cols = ledger.timing_columns(env, benchmark_start="2026-11-06T12:00:10Z",
                                     benchmark_runtime="45", now_ns=T0 + 55 * NS)
        self.assertEqual(cols["start_benchmark_datetime"], "")
        self.assertEqual(cols["runtime_benchmark_mm_ss"], "")
        self.assertEqual(cols["runtime_setup_mm_ss"], "00:45")
        self.assertEqual(cols["runtime_script_mm_ss"], "00:55")

    def test_older_caller_keeps_two_values(self) -> None:
        cols = ledger.timing_columns({}, benchmark_start="2026-11-06T12:00:00Z",
                                     benchmark_runtime="75", now_ns=T0)
        self.assertEqual(cols["start_benchmark_datetime"], "2026-11-06T12:00:00Z")
        self.assertEqual(cols["runtime_benchmark_mm_ss"], "01:15")
        for name in ("start_script_datetime", "start_setup_datetime", "runtime_script_mm_ss", "runtime_setup_mm_ss"):
            self.assertEqual(cols[name], "", name)

    def test_missing_script_start_uses_setup_start(self) -> None:
        env = {"BENCHMARK_SETUP_START_NS": str(T0), "BENCHMARK_START_NS": str(T0 + 5 * NS),
               "BENCHMARK_MEASURE_STARTED": "1"}
        cols = ledger.timing_columns(env, benchmark_start="x", benchmark_runtime="10", now_ns=T0 + 20 * NS)
        self.assertEqual(cols["start_script_datetime"], cols["start_setup_datetime"])
        self.assertEqual(cols["runtime_script_mm_ss"], "00:20")


class MigrationAndContextTests(unittest.TestCase):
    def test_old_row_renamed(self) -> None:
        row = {"table_index_number": "4", "run_id": "107_20261106_120000", "workload_number": "107",
               "start_datetime": "2026-11-06T12:00:00Z", "total_runtime_mm_ss": "95",
               "exit_code": "0", "failure_stage": "ok"}
        migrated = ledger.migrate_row(row)
        self.assertEqual(list(migrated), list(ledger.LEDGER_COLUMNS))
        self.assertEqual(migrated["start_benchmark_datetime"], "2026-11-06T12:00:00Z")
        self.assertEqual(migrated["runtime_benchmark_mm_ss"], "01:35")
        self.assertEqual(migrated["runtime_setup_mm_ss"], "")
        self.assertEqual(migrated["runtime_script_mm_ss"], "")

    def test_new_row_unchanged(self) -> None:
        row = {name: "" for name in ledger.LEDGER_COLUMNS}
        row.update(start_benchmark_datetime="2026-11-06T12:00:00Z", runtime_benchmark_mm_ss="02:00",
                   runtime_setup_mm_ss="00:30", runtime_script_mm_ss="02:40", exit_code="0", failure_stage="ok")
        migrated = ledger.migrate_row(row)
        for name in ("start_benchmark_datetime", "runtime_benchmark_mm_ss", "runtime_setup_mm_ss", "runtime_script_mm_ss"):
            self.assertEqual(migrated[name], row[name], name)

    def test_run_context(self) -> None:
        self.assertEqual(ledger.run_context_columns({}), {
            "workload_repeat_index": "1", "workload_repeat_total": "1", "suite_id": "",
            "suite_repeat_index": "", "suite_repeat_total": "", "network_download_mb_s": ""})
        cols = ledger.run_context_columns({
            "BENCHMARK_SUITE_ID": "vm1_20261112_080000", "BENCHMARK_SUITE_REPEAT_INDEX": "2",
            "BENCHMARK_SUITE_REPEAT_TOTAL": "3", "BENCHMARK_NETWORK_DOWNLOAD_MB_S": "48.8"})
        self.assertEqual(cols["suite_id"], "vm1_20261112_080000")
        self.assertEqual((cols["suite_repeat_index"], cols["suite_repeat_total"]), ("2", "3"))
        self.assertEqual(cols["network_download_mb_s"], "48.8")

    def test_amdgpu_version_parse(self) -> None:
        text = "AMDSMI Tool: 26.0.0 | AMDSMI Library version: 26.0.0 | ROCm version: 7.1.0 | amdgpu version: 6.16.6 | hsmp version: N/A"
        self.assertEqual(ledger.parse_amdgpu_version(text), "6.16.6")
        self.assertEqual(ledger.parse_amdgpu_version("nothing here"), "")

    def test_kernel_version(self) -> None:
        self.assertEqual(ledger.kernel_version(), platform.release())


@unittest.skipIf(BASH is None, "bash is not installed")
class CommonShTests(unittest.TestCase):
    def test_exports(self) -> None:
        script = (
            f'source "{COMMON.as_posix()}"\n'
            'echo "S=${BENCHMARK_SCRIPT_START_NS}"\n'
            'begin_benchmark_run smoke\n'
            'bash -c \'echo "U=${BENCHMARK_SETUP_START_NS} M=${BENCHMARK_MEASURE_STARTED}"\'\n'
            'mark_benchmark_measure_start\n'
            'bash -c \'echo "B=${BENCHMARK_START_NS} M=${BENCHMARK_MEASURE_STARTED}"\'\n'
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([BASH, "-c", script], cwd=tmp, capture_output=True, text=True, timeout=60)
        out = dict(part.split("=", 1) for line in result.stdout.splitlines() for part in line.split())
        self.assertRegex(out["S"], r"^\d{15,}$", result.stdout + result.stderr)
        self.assertGreaterEqual(int(out["U"]), int(out["S"]))
        self.assertGreaterEqual(int(out["B"]), int(out["U"]))
        self.assertEqual(out["M"], "1")
        self.assertIn("M=0", result.stdout)


FAKE_CURL = """#!/usr/bin/env bash
printf '%s' "${FAKE_CURL_OUT}"
"""


@unittest.skipIf(BASH is None, "bash is not installed")
class SuiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        folder = self.root / "101-alpha"
        folder.mkdir()
        (folder / "run_benchmark.sh").write_text(
            '#!/usr/bin/env bash\n'
            'echo "CTX id=${BENCHMARK_SUITE_ID} pass=${BENCHMARK_SUITE_REPEAT_INDEX}'
            ' of=${BENCHMARK_SUITE_REPEAT_TOTAL} net=${BENCHMARK_NETWORK_DOWNLOAD_MB_S}"\n',
            encoding="utf-8")
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        curl = bin_dir / "curl"
        curl.write_text(FAKE_CURL, encoding="utf-8")
        curl.chmod(curl.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        self.env = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
        self.env.pop("BENCHMARK_SKIP_NETWORK_TEST", None)

    def suite(self, curl_out: str, **extra: str) -> subprocess.CompletedProcess:
        env = dict(self.env, FAKE_CURL_OUT=curl_out, **extra)
        return subprocess.run([BASH, str(SUITE), "-d", str(self.root), "-w", "101", "--smoke", "-r", "2",
                               "--show-output", "-o", str(self.root / "suite.log")],
                              env=env, capture_output=True, text=True, timeout=60)

    def ctx_lines(self, stdout: str) -> list[str]:
        return [line for line in stdout.splitlines() if line.startswith("CTX ")]

    def test_suite_id_pass_and_download(self) -> None:
        result = self.suite("200 209715200 52428800.000")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Download:   52.4 MB/s from huggingface.co", result.stdout)
        lines = self.ctx_lines(result.stdout)
        self.assertEqual(len(lines), 2, result.stdout)
        self.assertRegex(lines[0], r"^CTX id=\S+_\d{8}_\d{6} pass=1 of=2 net=52\.4$")
        self.assertRegex(lines[1], r" pass=2 of=2 net=52\.4$")
        suite_id = lines[0].split()[1].split("=", 1)[1]
        self.assertIn(f"Suite ID:   {suite_id}", result.stdout)
        self.assertEqual(lines[1].split()[1], f"id={suite_id}")

    def test_failed_download_not_measured(self) -> None:
        for out in ("503 0 0.000", "200 1000 500.000", ""):
            with self.subTest(curl=out):
                result = self.suite(out)
                self.assertIn("Download:   not measured", result.stdout)
                self.assertTrue(all(line.endswith(" net=") for line in self.ctx_lines(result.stdout)))

    def test_skip_network_test(self) -> None:
        result = self.suite("200 209715200 52428800.000", BENCHMARK_SKIP_NETWORK_TEST="1")
        self.assertIn("Download:   not measured", result.stdout)


if __name__ == "__main__":
    unittest.main()
