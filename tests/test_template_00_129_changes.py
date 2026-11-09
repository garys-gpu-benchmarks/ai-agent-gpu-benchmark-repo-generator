#!/usr/bin/env python3
# File: tests/test_template_00_129_changes.py
# Description: TEMPLATE_00_129 checks: x20 dense-LU names, 114/314 per-direction
# memcpy metrics, x31 labels and repeated warm-up, x28/x29 extended max_num_seqs,
# fio target guard and qd8 case metric, and the per-case headline tag.
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
COMPONENTS = ROOT / "implementation_components"


def workbook_rows(sheet: str) -> list[dict]:
    from openpyxl import load_workbook

    ws = load_workbook(ROOT / "BenchmarkSpecDefinitions.xlsx", read_only=True)[sheet]
    rows = ws.iter_rows(values_only=True)
    header = next(rows)
    return [dict(zip(header, row)) for row in rows if row and row[0] is not None]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WorkbookTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.defs = {row["Workload Number"]: row for row in workbook_rows("Workload_Definitions")}
        cls.params = workbook_rows("Parameters_SmokeBaselineExtend")

    def test_x20_is_named_dense_lu(self) -> None:
        for number, library in ((120, "rocSOLVER"), (220, "cuSOLVER"), (320, "rocSOLVER"), (420, "cuSOLVER")):
            name = self.defs[number]["Workload Name"]
            self.assertEqual(name, f"{library} FP64 Dense LU Solve (single GPU)")
            self.assertNotIn("HPL", name)
            self.assertNotIn("Linpack", self.defs[number]["Main Goal"])
        for component in ("linpack-rochpl-amd", "linpack-hpl-nvidia"):
            data = json.loads((COMPONENTS / component / "component.json").read_text(encoding="utf-8"))
            values = [s["value"] for s in data["selectors"] if s["field"] == "Workload Name"]
            self.assertTrue(values[0].endswith("FP64 Dense LU Solve (single GPU)"), values)

    def test_amd_memcpy_matches_nvidia_directions(self) -> None:
        nvidia = self.defs[214]["Metrics"].split("#7:")[0].strip()
        for number in (114, 314):
            self.assertEqual(self.defs[number]["Metrics"].strip(), nvidia)

    def test_x31_labels_have_no_queue_wait(self) -> None:
        for number in (131, 231, 331, 431):
            metrics = self.defs[number]["Metrics"]
            self.assertNotIn("queue wait", metrics)
            self.assertIn("client-observed from send", metrics)

    def test_vllm_extended_max_num_seqs_matches_concurrency(self) -> None:
        for workload in (128, 129, 228, 229, 328, 329, 428, 429):
            rows = {r["Parameter"]: r for r in self.params if r["Workload Number"] == workload}
            for profile in ("smoke", "baseline", "extended"):
                self.assertEqual(int(rows["max_num_seqs"][profile]), int(rows["max_concurrency"][profile]), (workload, profile))

    def test_fio_publishes_qd8_case_on_every_profile(self) -> None:
        for number in (106, 206, 306, 406):
            self.assertIn("(iops_mean__randread_4k_qd8);", self.defs[number]["Metrics"])
            rows = {r["Parameter"]: r for r in self.params if r["Workload Number"] == number}
            for profile in ("smoke", "baseline", "extended"):
                self.assertIn("randread", str(rows["rw"][profile]).split(","))
                self.assertIn("4k", str(rows["block_size"][profile]).split(","))
                self.assertIn("8", str(rows["io_depth"][profile]).split(","))


class MemcpyParserTest(unittest.TestCase):
    def test_headline_point_does_not_say_h2d(self) -> None:
        parser = load_module(COMPONENTS / "hipmemcpy-bandwidth-amd/files/scripts/parse_results.py", "memcpy_parse_129")
        rows = [
            {"direction": d, "transfer_size_bytes": str(size), "bandwidth_gbps": str(bw), "latency_us": str(lat)}
            for d, size, bw, lat in (
                ("H2D", 1024, 0.1, 11.0), ("H2D", 1 << 30, 55.0, 19000.0),
                ("D2H", 1024, 0.1, 10.0), ("D2H", 1 << 30, 57.0, 18000.0),
                ("D2D", 1024, 0.4, 2.5), ("D2D", 1 << 24, 3400.0, 5.0), ("D2D", 1 << 30, 1990.0, 540.0),
            )
        ]
        summary: dict = {}
        parser.add_peak_direction_bandwidth(rows, summary)
        parser.add_min_size_direction_latency(rows, summary)
        parser.add_h2d_headline(rows, summary)
        self.assertEqual(summary["bandwidth_d2d_gbps"], 1990.0)  # max size, not the 16 MiB peak
        self.assertEqual(summary["latency_d2h_us"], 10.0)
        self.assertEqual(summary["headline_point"], "at 1024 MiB")
        self.assertEqual(summary["headline_transfer_bytes"], 1 << 30)


class HeadlineTagTest(unittest.TestCase):
    def test_per_case_key_is_not_tagged_first_case(self) -> None:
        import print_metric_summary

        definition = Path(tempfile.mkdtemp()) / "def.json"
        definition.write_text(json.dumps([{"field_name": "Metrics", "value":
            "#1: IOPS mean at first sweep case (iops_mean); "
            "#4: IOPS, 4k random read, iodepth 8 x 4 jobs = 32 in flight, every profile (iops_mean__randread_4k_qd8);"}]))
        summary = definition.parent / "summary.json"
        summary.write_text(json.dumps({"metrics": {
            "iops_mean": 50000.0, "iops_mean__randread_4k_qd8": 170000.0,
            "headline_point": "first_case randread_4k_qd1"}}))
        with mock.patch.object(sys, "argv", ["x", "--definition", str(definition), "--summary", str(summary)]), \
                mock.patch("builtins.print") as printed:
            self.assertEqual(print_metric_summary.main(), 0)
        lines = [str(call.args[0]) for call in printed.call_args_list]
        self.assertTrue(any("(iops_mean) [first_case randread_4k_qd1]" in line for line in lines), lines)
        qd8 = [line for line in lines if "iops_mean__randread_4k_qd8=" in line]
        self.assertEqual(len(qd8), 1, lines)
        self.assertNotIn("first_case", qd8[0])


class FioTargetGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.modules = [
            load_module(COMPONENTS / f"fio-nvme-{v}/files/scripts/collect_workload.py", f"fio_{v}_129")
            for v in ("amd", "nvidia")
        ]

    def _quiet(self, mounts: str):
        def fake(command):
            if command[0] == "findmnt":
                return mounts
            return ""
        return fake

    def test_file_target_is_never_refused(self) -> None:
        for module in self.modules:
            module.check_target(Path("data/fio_target.bin"), ["randread", "randwrite", "write"])

    def test_mounted_device_and_its_partitions_are_refused(self) -> None:
        for module in self.modules:
            with mock.patch.object(module, "_quiet", self._quiet("/dev/nvme0n1p2 /\n/dev/sdb1 /data")):
                for device in ("/dev/nvme0n1", "/dev/nvme0n1p2", "/dev/sdb"):
                    with self.assertRaises(SystemExit):
                        module.check_target(Path(device), ["randread"])

    def test_raw_device_write_needs_confirmation(self) -> None:
        for module in self.modules:
            with mock.patch.object(module, "_quiet", self._quiet("/dev/sda1 /")):
                module.check_target(Path("/dev/nvme1n1"), ["randread"])  # read-only is allowed
                with mock.patch.dict("os.environ", {"FIO_ALLOW_DEVICE_WRITE": ""}):
                    with self.assertRaises(SystemExit):
                        module.check_target(Path("/dev/nvme1n1"), ["randread", "randwrite"])
                with mock.patch.dict("os.environ", {"FIO_ALLOW_DEVICE_WRITE": "1"}):
                    module.check_target(Path("/dev/nvme1n1"), ["randread", "randwrite"])


class WarmupRoundsTest(unittest.TestCase):
    def test_serving_warmup_repeats_until_settled(self) -> None:
        from test_sglang_stub_clients import SERVING, _Workspace

        ws = _Workspace(SERVING[1], "bench_serving.py")
        try:
            port = ws.start_server()
            ws.env.update(SGLANG_WARMUP_SETTLE_TTFT_MS="-1", SGLANG_WARMUP_MAX_ROUNDS="3")
            result = ws.run_client(port, "--max-concurrency", "2")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stdout.count("[INFO] warm-up: 2 untimed request(s)"), 3, result.stdout)
            self.assertIn("round 3 of at most 3", result.stdout)
            self.assertIn("[WARN] warm-up TTFT still above", result.stdout)
        finally:
            ws.close()

    def test_settled_server_needs_one_round(self) -> None:
        from test_sglang_stub_clients import SERVING, _Workspace

        ws = _Workspace(SERVING[0], "bench_serving.py")
        try:
            port = ws.start_server()
            result = ws.run_client(port, "--max-concurrency", "2")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stdout.count("[INFO] warm-up: 2 untimed request(s)"), 1, result.stdout)
            self.assertNotIn("[WARN] warm-up TTFT", result.stdout)
        finally:
            ws.close()


if __name__ == "__main__":
    unittest.main()
