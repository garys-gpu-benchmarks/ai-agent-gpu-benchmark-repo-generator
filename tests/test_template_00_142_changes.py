"""TEMPLATE_00_142 checks (from the TEMPLATE_00_141 batch review and debriefs).

  1. SGLang clients (x30 prompt-response, x31 serving, both vendors) start the benchmark
     clock after their warm-up: SGLang compiles its kernels on the first request
     (111-158 s on the TEMPLATE_00_141 smokes), which counted as benchmark time.
  2. Every fifth heartbeat also goes to batch_progress.log, so the file the agent
     follows moves during a long workload (431 was silent there for 16m 32s).
  3. The agent docs give the exact wait pattern and say to read the progress file after
     a wait that ends without a match (one agent's mis-escaped pattern sat 30 minutes).
  4. The conflicting `--template-root` preflight and the unanswerable "Answer yes" SSH
     host-key sentences are gone.
  5. The AMD preflight host line prints the GPU count from PCI instead of "x?".
"""
from __future__ import annotations

import ast
import contextlib
import importlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
COMPONENTS = ROOT / "implementation_components"
SGLANG_CLIENTS = [
    "sglang-prompt-response-amd/files/scripts/prompt_response_client.py",
    "sglang-prompt-response-nvidia/files/scripts/prompt_response_client.py",
    "sglang-serving-amd/files/scripts/bench_serving.py",
    "sglang-serving-nvidia/files/scripts/bench_serving.py",
]
AGENT_DOCS = ["docs/AI_AGENT_INSTRUCTIONS.md", ".cursor/rules/generate-workloads.mdc", "AGENTS.md"]


# Git Bash on Windows, never System32's WSL bash.exe (TEMPLATE_00_147, OPEN_ISSUES T1).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from host_bash import HOST_BASH  # noqa: E402


class SglangClockTests(unittest.TestCase):
    def test_clock_starts_after_the_warm_up(self) -> None:
        for rel in SGLANG_CLIENTS:
            with self.subTest(client=rel):
                tree = ast.parse((COMPONENTS / rel).read_text(encoding="utf-8"))
                main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
                calls = [n for n in ast.walk(main) if isinstance(n, ast.Call)
                         and isinstance(n.func, ast.Name) and n.func.id == "mark_measure_start"]
                self.assertEqual(len(calls), 1, rel)
                source = (COMPONENTS / rel).read_text(encoding="utf-8")
                warm = source.rindex("warm-up", 0, source.index("    mark_measure_start()"))
                timed = source.index("    mark_measure_start()")
                self.assertLess(warm, timed)

    def test_helper_writes_once_under_the_runner(self) -> None:
        for rel in SGLANG_CLIENTS:
            with self.subTest(client=rel), tempfile.TemporaryDirectory() as tmp:
                tree = ast.parse((COMPONENTS / rel).read_text(encoding="utf-8"))
                node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "mark_measure_start")
                namespace: dict = {}
                exec(compile(ast.Module(body=[node], type_ignores=[]), rel, "exec"), namespace)
                target = Path(tmp) / "measure"
                saved = os.environ.get("BENCHMARK_MEASURE_START_FILE")
                os.environ["BENCHMARK_MEASURE_START_FILE"] = str(target)
                try:
                    namespace["mark_measure_start"]()
                    first = target.read_text(encoding="utf-8")
                    namespace["mark_measure_start"]()
                    self.assertEqual(target.read_text(encoding="utf-8"), first)
                    self.assertRegex(first, r"^\d{19}\n$")
                finally:
                    if saved is None:
                        os.environ.pop("BENCHMARK_MEASURE_START_FILE", None)
                    else:
                        os.environ["BENCHMARK_MEASURE_START_FILE"] = saved


class HeartbeatProgressTests(unittest.TestCase):
    def test_every_fifth_heartbeat_reaches_the_progress_file(self) -> None:
        host_exec = importlib.import_module("host_exec")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                host_exec._stream_to_log([HOST_BASH, "-c", "echo working; sleep 6.5"], cwd=None, timeout=None,
                                         env=dict(os.environ), log_path=root / "l.log", label="431 setup+smoke",
                                         heartbeat_s=1.0, progress_root=root)
            progress_lines = (root / "batch_progress.log").read_text(encoding="utf-8").splitlines()
            console_beats = [line for line in out.getvalue().splitlines() if "still running" in line]
        self.assertGreaterEqual(len(console_beats), 5)
        self.assertEqual(len(progress_lines), len(console_beats) // 5)
        self.assertIn("[431 setup+smoke] still running", progress_lines[0])
        self.assertRegex(progress_lines[0], r" \| \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_no_progress_root_keeps_the_console_only(self) -> None:
        host_exec = importlib.import_module("host_exec")
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                host_exec.run_host_bash("sleep 1.5", stream_log=Path(tmp) / "l.log", heartbeat_label="x", heartbeat_s=1.0)
            self.assertFalse((Path(tmp) / "batch_progress.log").exists())

    def test_batch_passes_the_project_root(self) -> None:
        text = (ROOT / "scripts" / "create_one_workload.py").read_text(encoding="utf-8")
        self.assertIn("progress_root=BATCH_LOG.parent", text)


class AgentDocTests(unittest.TestCase):
    def test_exact_pattern_and_timeout_rule(self) -> None:
        for rel in AGENT_DOCS:
            with self.subTest(doc=rel):
                text = (ROOT / rel).read_text(encoding="utf-8")
                self.assertIn("\\[RECORD\\]", text)
                self.assertIn("read `batch_progress.log`", text)
                self.assertNotIn("if it times out, start the same wait again", text)
                self.assertNotIn("then start it again.", text)
                self.assertNotIn("If neither output moves for 30 minutes", text)
                self.assertIn("every 5 minutes", text)

    def test_conflicting_sentences_are_gone(self) -> None:
        text = (ROOT / "docs" / "AI_AGENT_INSTRUCTIONS.md").read_text(encoding="utf-8")
        self.assertNotIn("run `python3 scripts/generation_host_preflight.py --template-root", text)
        self.assertNotIn("Answer `yes` when SSH asks", text)
        self.assertIn("StrictHostKeyChecking=accept-new", text)


class PreflightGpuCountTests(unittest.TestCase):
    def test_amd_count_from_pci(self) -> None:
        rhp = importlib.import_module("remote_host_preflight")
        self.assertEqual(rhp.pci_gpu_count({"pci_gpu_devices": "0x1002 0x1af4 0x1002"}, "amd"), 2)
        self.assertEqual(rhp.pci_gpu_count({"pci_gpu_devices": "0x1af4"}, "amd"), 0)
        self.assertEqual(rhp.pci_gpu_count({}, "nvidia"), 0)

    def test_evaluate_fills_the_amd_count(self) -> None:
        rhp = importlib.import_module("remote_host_preflight")
        values = {"vendor": "amd", "os_version_id": "24.04", "pci_gpu_vendors": "0x1002 0x1af4",
                  "pci_gpu_devices": "0x1af4 0x1002", "download_huggingface_bps": "21400000",
                  "download_pytorch_bps": "457000000"}
        rhp.evaluate(values, ["101", "102"], {}, 1.0)
        self.assertEqual(values["gpu_count"], "1")
        nvidia = {"vendor": "nvidia", "gpu_count": "8", "os_version_id": "24.04", "pci_gpu_vendors": "0x10de",
                  "pci_gpu_devices": "0x10de", "download_huggingface_bps": "1", "download_pytorch_bps": "1"}
        rhp.evaluate(nvidia, ["201"], {}, 1.0)
        self.assertEqual(nvidia["gpu_count"], "8")  # nvidia-smi's count is kept

    def test_probe_lists_every_device(self) -> None:
        text = (ROOT / "scripts" / "remote_host_preflight.py").read_text(encoding="utf-8")
        self.assertIn("kv pci_gpu_devices", text)


if __name__ == "__main__":
    unittest.main()
