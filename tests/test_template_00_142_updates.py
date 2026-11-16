#!/usr/bin/env python3
"""TEMPLATE_00_142 updates of 2026-11-16: open issues S7, P1, P2 and M5.

S7  run_benchmark.sh --repeat N (run_profiles_in_order in scripts/lib/common.sh).
P1  x22/x23 map the dtype parameter onto the torch dtype (both vendors).
P2  x26 JAX selects the GPU given by --device-id.
M5  x21 ResNet-50 training reports TFLOP/s from FLOPs counted by FlopCounterMode
    (counted_tflops) instead of a constant per image.
"""
from __future__ import annotations

import ast
import csv
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
IC = ROOT / "implementation_components"
BASH = shutil.which("bash")
OVERLAY_RUNNERS = sorted(IC.glob("*/files/run_benchmark.sh"))
HAS_TORCH = importlib.util.find_spec("torch") is not None
HAS_TORCHVISION = importlib.util.find_spec("torchvision") is not None

DTYPE_FILES = [
    IC / "resnet50-inference-nvidia/files/scripts/gpu-bench-resnet50-pytorch-inference.py",
    IC / "bert-inference-nvidia/files/scripts/gpu-bench-bert-transformers-inference.py",
    IC / "resnet50-inference-amd/files/scripts/collect_workload.py",
    IC / "bert-inference-amd/files/scripts/collect_workload.py",
]
JAX_FILES = [IC / f"jax-xla-{vendor}/files/scripts/gpu-bench-jax-xla-forwardpass.py" for vendor in ("amd", "nvidia")]
RESNET_TRAIN_AMD = IC / "resnet50-training-amd/files/scripts/collect_workload.py"
RESNET_TRAIN_NVIDIA = IC / "resnet50-training-nvidia/files/scripts/train_resnet50.py"
RESNET_COLLECT_NVIDIA = IC / "resnet50-training-nvidia/files/scripts/collect_resnet50_train.py"


def module_function(path: Path, name: str):
    """Load one top-level function (and the module constants it needs) without importing the file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    keep = [
        node for node in tree.body
        if (isinstance(node, ast.FunctionDef) and node.name == name)
        or (isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) and t.id.isupper() for t in node.targets))
    ]
    namespace: dict = {}
    exec(compile(ast.Module(body=keep, type_ignores=[]), str(path), "exec"), namespace)  # noqa: S102 - test-only
    return namespace[name], namespace


@unittest.skipIf(BASH is None, "bash is not installed")
class RepeatTests(unittest.TestCase):
    def run_fake(self, *args: str, fail_on: str = "") -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "fake.sh"
            script.write_text(
                "set -euo pipefail\n"
                f'source "{ROOT}/scripts/lib/common.sh"\n'
                'run_profiles_in_order "$0" "$@"\n'
                'echo "child: $* [${BENCHMARK_WORKLOAD_REPEAT_INDEX:-}/${BENCHMARK_WORKLOAD_REPEAT_TOTAL:-}]"\n'
                '[[ -n "${FAIL_ON}" && "$* ${BENCHMARK_WORKLOAD_REPEAT_INDEX:-}" == "${FAIL_ON}" ]] && exit 5\n'
                "exit 0\n",
                encoding="utf-8",
            )
            env = dict(os.environ, FAIL_ON=fail_on)
            env.pop("BENCHMARK_WORKLOAD_REPEAT_INDEX", None)
            env.pop("BENCHMARK_WORKLOAD_REPEAT_TOTAL", None)
            return subprocess.run([BASH, str(script), *args], capture_output=True, text=True, env=env, timeout=30)

    @staticmethod
    def children(out: subprocess.CompletedProcess) -> list[str]:
        return [line for line in out.stdout.splitlines() if line.startswith("child:")]

    def test_one_profile_repeated(self) -> None:
        out = self.run_fake("--baseline", "--repeat", "3", "--num-threads", "8")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.children(out), [
            "child: --baseline --num-threads 8 [1/3]",
            "child: --baseline --num-threads 8 [2/3]",
            "child: --baseline --num-threads 8 [3/3]",
        ])
        self.assertIn("[INFO] ===== Repeat 2 of 3: profile baseline (1 of 1) =====", out.stdout)
        self.assertIn("[INFO] Profiles: baseline #1 ok, baseline #2 ok, baseline #3 ok", out.stdout)

    def test_the_whole_set_is_repeated_like_the_suite(self) -> None:
        out = self.run_fake("--repeat=2", "--smoke", "--extended")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.children(out), [
            "child: --smoke [1/2]", "child: --extended [1/2]",
            "child: --smoke [2/2]", "child: --extended [2/2]",
        ])

    def test_no_profile_repeats_the_default(self) -> None:
        out = self.run_fake("--repeat", "2")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.children(out), ["child:  [1/2]", "child:  [2/2]"])
        self.assertIn("default #1 ok, default #2 ok", out.stdout)

    def test_repeat_one_runs_once_without_the_option(self) -> None:
        out = self.run_fake("--smoke", "--repeat", "1")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.children(out), ["child: --smoke [1/1]"])

    def test_a_failed_run_does_not_stop_the_rest(self) -> None:
        out = self.run_fake("--smoke", "--repeat", "3", fail_on="--smoke 2")
        self.assertEqual(out.returncode, 5)
        self.assertEqual(len(self.children(out)), 3)
        self.assertIn("smoke #1 ok, smoke #2 FAILED (exit 5), smoke #3 ok", out.stdout)

    def test_bad_counts_are_refused_before_any_run(self) -> None:
        for value in ("0", "x", "-1", ""):
            with self.subTest(value=value):
                out = self.run_fake("--smoke", "--repeat", value) if value else self.run_fake("--smoke", "--repeat")
                self.assertEqual(out.returncode, 2)
                self.assertEqual(self.children(out), [])
                self.assertIn("--repeat must be a whole number of 1 or more", out.stderr)

    def test_no_repeat_is_unchanged(self) -> None:
        out = self.run_fake("--baseline")
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout.strip(), "child: --baseline [/]")

    def test_help_lists_repeat_in_the_template_and_every_overlay_runner(self) -> None:
        line = "  --repeat <n>                  Run the selected profiles n times, in order (default: 1)"
        files = [ROOT / "scripts" / "materialize_generated_harness.py",
                 ROOT / "scripts" / "templates" / "run_benchmark_help_skeleton.sh",
                 ROOT / "docs" / "run-output-contract.md", *OVERLAY_RUNNERS]
        self.assertGreaterEqual(len(OVERLAY_RUNNERS), 12)
        for path in files:
            with self.subTest(path=path.name if path not in OVERLAY_RUNNERS else path.parts[-3]):
                self.assertIn(line, path.read_text(encoding="utf-8"))


class DtypeTests(unittest.TestCase):
    def test_every_inference_collector_maps_the_dtype(self) -> None:
        tables = []
        for path in DTYPE_FILES:
            text = path.read_text(encoding="utf-8")
            with self.subTest(file=path.parts[-4]):
                self.assertIn("torch_dtype(", text)
                self.assertNotIn("dtype = torch.bfloat16\n", text)
                self.assertNotIn("dtype = torch.float16\n", text)
                self.assertNotIn("model.half()", text)
                tree = ast.parse(text)
                for node in tree.body:
                    if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "TORCH_DTYPE_NAMES":
                        tables.append(ast.literal_eval(node.value))
        self.assertEqual(len(tables), 4)
        self.assertTrue(all(table == tables[0] for table in tables))

    def test_workbook_dtypes_map(self) -> None:
        table = DtypeTests.table()
        sheet = load_workbook(ROOT / "BenchmarkSpecDefinitions.xlsx", read_only=True)["Parameters_SmokeBaselineExtend"]
        seen = 0
        for row in sheet.iter_rows(values_only=True):
            if row and str(row[0]) in {"122", "123", "222", "223", "322", "323", "422", "423"} and row[2] == "dtype":
                for value in row[3:6]:
                    seen += 1
                    self.assertIn(str(value).strip().lower(), table)
        self.assertEqual(seen, 24)

    @staticmethod
    def table() -> dict:
        tree = ast.parse(DTYPE_FILES[0].read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "TORCH_DTYPE_NAMES")
        return ast.literal_eval(node.value)

    @unittest.skipUnless(HAS_TORCH, "torch is not installed")
    def test_names_resolve_and_unknown_names_fail(self) -> None:
        import torch

        torch_dtype, _ = module_function(DTYPE_FILES[0], "torch_dtype")
        self.assertIs(torch_dtype("f16_r"), torch.float16)
        self.assertIs(torch_dtype("BF16"), torch.bfloat16)
        self.assertIs(torch_dtype("fp32"), torch.float32)
        with self.assertRaises(SystemExit) as caught:
            torch_dtype("int8")
        self.assertIn("dtype 'int8' is not supported", str(caught.exception))


class JaxDeviceTests(unittest.TestCase):
    def test_device_id_selects_the_gpu(self) -> None:
        for path in JAX_FILES:
            text = path.read_text(encoding="utf-8")
            with self.subTest(file=path.parts[-4]):
                self.assertIn("device = devices[device_id]", text)
                self.assertIn('jax.config.update("jax_default_device", device)', text)
                self.assertIn("is not visible; JAX sees", text)
                self.assertIn('device.memory_stats()["peak_bytes_in_use"]', text)
                self.assertNotIn("local_devices()[0]", text)
                # The device is chosen before any parameter is created.
                self.assertLess(text.index("jax_default_device"), text.index("random.PRNGKey"))


class CountedFlopsTests(unittest.TestCase):
    def test_both_trainers_count_flops_before_the_clock(self) -> None:
        for path in (RESNET_TRAIN_AMD, RESNET_TRAIN_NVIDIA):
            text = path.read_text(encoding="utf-8")
            with self.subTest(file=path.parts[-4]):
                self.assertIn("FlopCounterMode", text)
                self.assertIn("counted_tflops", text)
                self.assertNotIn("3.0 * 2.0 * 3.8e9", text)
                self.assertNotIn("RESNET50_INFERENCE_MACS_224", text)
                self.assertNotIn("modeled_tflops", text)
                self.assertNotIn("fp16_tflops", text)
                self.assertLess(text.index("step_flops = counted_step_flops("), text.rindex("mark_measure_start()"))

    def test_workbook_names_the_counted_key(self) -> None:
        book = load_workbook(ROOT / "BenchmarkSpecDefinitions.xlsx", read_only=True)
        rows = {str(r[0]): r for r in book["Workload_Definitions"].iter_rows(values_only=True) if r and r[0]}
        header = list(book["Workload_Definitions"].iter_rows(values_only=True, max_row=1))[0]
        metrics = header.index("Metrics")
        for workload in ("121", "221", "321", "421"):
            with self.subTest(workload=workload):
                text = rows[workload][metrics]
                self.assertIn("#3: Training throughput from counted FLOPs, TFLOP/s (counted_tflops)", text)
                self.assertIn("#4: Peak PyTorch-allocated GPU memory (", text)
                row_text = " ".join(str(v or "") for v in rows[workload])
                self.assertNotIn("fp16_tflops", row_text)
                self.assertNotIn("modeled_tflops", row_text)
        labels = [r for r in book["Metric_Short_Labels"].iter_rows(values_only=True)
                  if r and str(r[0]) in {"121", "221", "321", "421"} and str(r[3]) == "3"]
        self.assertEqual([(r[4], r[6]) for r in labels], [("counted_tflops", "CntTF")] * 4)

    @unittest.skipUnless(HAS_TORCH, "torch is not installed")
    def test_counter_counts_and_reports_failures_as_na(self) -> None:
        import torch

        counted_step_flops, _ = module_function(RESNET_TRAIN_AMD, "counted_step_flops")
        layer = torch.nn.Linear(8, 4)
        inputs = torch.randn(2, 8)

        def step():
            layer(inputs).sum().backward()

        # forward 2*2*8*4 = 128; backward: the weight gradient, 128 more (the
        # input needs no gradient).
        self.assertEqual(counted_step_flops(step), 256.0)

        def broken():
            raise RuntimeError("boom")

        self.assertEqual(counted_step_flops(broken), "na (FlopCounterMode failed: RuntimeError)")
        self.assertEqual(counted_step_flops(lambda: None), "na (FlopCounterMode counted no FLOPs)")

    @unittest.skipUnless(HAS_TORCH and HAS_TORCHVISION, "torch/torchvision are not installed")
    def test_amd_collector_writes_counted_tflops_on_cpu(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "c.yaml"
            config.write_text("sweep:\n  image_size: 32\n  batch_size: 2\n  warmup_iters: 0\n  num_iterations: 1\n"
                              "  precision: fp32\n", encoding="utf-8")
            raw = Path(tmp) / "run" / "raw.csv"
            out = subprocess.run([sys.executable, str(RESNET_TRAIN_AMD), "--run-dir", str(raw.parent),
                                  "--raw-file", str(raw), "--config", str(config)],
                                 capture_output=True, text=True, timeout=300)
            self.assertEqual(out.returncode, 0, out.stderr)
            row = next(csv.DictReader(raw.open(encoding="utf-8")))
            self.assertGreater(float(row["counted_tflops"]), 0.0)

    def run_nvidia_collector(self, result_tail: str, extra: str = "") -> list[dict]:
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp) / "scripts"
            scripts.mkdir()
            shutil.copy(RESNET_COLLECT_NVIDIA, scripts / "collect_resnet50_train.py")
            (scripts / "train_resnet50.py").write_text(
                "print(" + repr(extra) + ")\n" if extra else "", encoding="utf-8")
            with (scripts / "train_resnet50.py").open("a", encoding="utf-8") as handle:
                handle.write("print(" + repr(
                    "RESULT dataset_name=synthetic precision=fp16 image_size=64 batch_size=2 num_workers=0 "
                    "optimizer=true learning_rate=0.1 gradient_accumulation=true warmup_iters=1 num_iterations=3 "
                    "step_time_msec=10.0 images_per_sec=200.0 " + result_tail) + ")\n")
            config = Path(tmp) / "c.yaml"
            config.write_text("sweep: {}\n", encoding="utf-8")
            out = subprocess.run([sys.executable, str(scripts / "collect_resnet50_train.py"), "--run-dir",
                                  str(Path(tmp) / "run"), "--config", str(config)],
                                 capture_output=True, text=True, timeout=60, cwd=tmp)
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
            return list(csv.DictReader((Path(tmp) / "run" / "raw_results.csv").open(encoding="utf-8")))

    def test_nvidia_collector_reads_counted_tflops(self) -> None:
        rows = self.run_nvidia_collector(
            "counted_tflops=1.500000 memory_bandwidth_gb_s=50.0 peak_gpu_memory_gb=2.0 status=ok")
        self.assertEqual([row["check"] for row in rows], ["pass1", "summary"])
        self.assertEqual(rows[1]["counted_tflops"], "1.500000")

    def test_nvidia_collector_keeps_the_na_reason(self) -> None:
        reason = "na (FlopCounterMode failed: RuntimeError)"
        rows = self.run_nvidia_collector(
            "counted_tflops=na memory_bandwidth_gb_s=50.0 peak_gpu_memory_gb=2.0 status=ok",
            extra=f"FLOPS_NA reason={reason}")
        self.assertEqual(rows[0]["counted_tflops"], reason)
        self.assertEqual(rows[1]["counted_tflops"], reason)
        self.assertEqual(rows[1]["images_per_sec"], "200.000000")


if __name__ == "__main__":
    unittest.main()
