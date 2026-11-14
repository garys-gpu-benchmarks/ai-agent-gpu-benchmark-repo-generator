"""TEMPLATE_00_141 timing: setup on every run, benchmark is the timed work only.

  1. mark_benchmark_measure_start moves the benchmark start on every run, so a rerun
     reports its checks, prefetch and server start as setup (TEMPLATE_00_139 reported
     00:00 after the first run). No .setup_state_timed marker is written.
  2. A collector that loads its model in-process writes the start of its timed loop
     to BENCHMARK_MEASURE_START_FILE; record_benchmark_stop moves the benchmark start
     there. A missing or earlier time changes nothing, and the file is removed.
  3. The 10 vLLM/SGLang runners start the benchmark clock right after wait_for_server.
  4. The 14 in-process collectors call mark_measure_start() before their timed loop,
     and the helper writes once and only under run_benchmark.sh.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / "scripts" / "lib" / "common.sh"
COMPONENTS = ROOT / "implementation_components"

SERVER_RUNNERS = [
    f"{name}-{vendor}/files/run_benchmark.sh"
    for name in ("vllm-kvcache", "vllm-throughput", "vllm-token-generation", "sglang-prompt-response", "sglang-serving")
    for vendor in ("amd", "nvidia")
]
IN_PROCESS = [
    "resnet50-training-amd/files/scripts/collect_workload.py",
    "resnet50-training-nvidia/files/scripts/train_resnet50.py",
    "resnet50-inference-amd/files/scripts/collect_workload.py",
    "resnet50-inference-nvidia/files/scripts/gpu-bench-resnet50-pytorch-inference.py",
    "bert-inference-amd/files/scripts/collect_workload.py",
    "bert-inference-nvidia/files/scripts/gpu-bench-bert-transformers-inference.py",
    "sdxl-diffusers-amd/files/scripts/infer_sdxl.py",
    "sdxl-diffusers-nvidia/files/scripts/infer_sdxl.py",
    "distilbert-amd/files/scripts/collect_workload.py",
    "distilbert-nvidia/files/scripts/gpu-bench-distilbert-sst2-train.py",
    "jax-xla-amd/files/scripts/gpu-bench-jax-xla-forwardpass.py",
    "jax-xla-nvidia/files/scripts/gpu-bench-jax-xla-forwardpass.py",
    "rag-faiss-end2end-amd/files/scripts/gpu-bench-rag-faiss-end2end.py",
    "rag-faiss-end2end-nvidia/files/scripts/gpu-bench-rag-faiss-end2end.py",
]


def run_bash(script: str, *args: str) -> list[str]:
    result = subprocess.run(["bash", "-c", script, "clock", *args], capture_output=True, text=True,
                            timeout=60, check=True)
    return result.stdout.splitlines()


CLOCK_SCRIPT = r"""
set -uo pipefail
REPO_ROOT="$1"; source "$2"; trap - ERR
run() {
  begin_benchmark_run smoke; set +E; trap - ERR
  sleep 1; mark_benchmark_measure_start
  sleep 1; mark_benchmark_measure_start
  echo "$(( (BENCHMARK_START_NS - BENCHMARK_SETUP_START_NS) / 1000000000 ))"
}
touch "$REPO_ROOT/.setup_state"; run
run
"""

COLLECTOR_SCRIPT = r"""
set -uo pipefail
REPO_ROOT="$1"; source "$2"; trap - ERR
begin_benchmark_run smoke; set +E; trap - ERR
mark_benchmark_measure_start
measured="$BENCHMARK_START_NS"
# No file: the start stays.
record_benchmark_stop
[[ "$BENCHMARK_START_NS" == "$measured" ]] && echo "unchanged"
# A collector marks its timed loop 1 s later.
echo "$((measured + 1000000000))" > "$BENCHMARK_MEASURE_START_FILE"
record_benchmark_stop
echo "$(( (BENCHMARK_START_NS - measured) / 1000000 ))"
[[ -e "$BENCHMARK_MEASURE_START_FILE" ]] || echo "removed"
[[ "$BENCHMARK_START_DATETIME" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]{8}Z$ ]] && echo "iso"
# An earlier time is ignored.
moved="$BENCHMARK_START_NS"
echo "$((measured - 5000000000))" > "$BENCHMARK_MEASURE_START_FILE"
record_benchmark_stop
[[ "$BENCHMARK_START_NS" == "$moved" ]] && echo "earlier ignored"
"""


class SetupEveryRunTests(unittest.TestCase):
    def test_every_run_reports_its_setup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = run_bash(CLOCK_SCRIPT, tmp, str(COMMON))
            self.assertEqual(out, ["2", "2"])  # first run and rerun alike
            self.assertFalse((Path(tmp) / ".setup_state_timed").exists())

    def test_first_run_rule_is_gone(self) -> None:
        text = COMMON.read_text(encoding="utf-8")
        self.assertNotIn("BENCHMARK_FIRST_RUN_AFTER_SETUP=", text)
        self.assertNotIn(': >"${root}/.setup_state_timed"', text)


class CollectorMeasureStartTests(unittest.TestCase):
    def test_record_stop_reads_the_collector_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, TMPDIR=tmp)
            result = subprocess.run(["bash", "-c", COLLECTOR_SCRIPT, "clock", tmp, str(COMMON)],
                                    capture_output=True, text=True, timeout=60, check=True, env=env)
            self.assertEqual(result.stdout.splitlines(),
                             ["unchanged", "1000", "removed", "iso", "earlier ignored"], result.stderr)


class ServerRunnerTests(unittest.TestCase):
    def test_clock_starts_after_the_server_is_ready(self) -> None:
        for rel in SERVER_RUNNERS:
            with self.subTest(runner=rel):
                text = (COMPONENTS / rel).read_text(encoding="utf-8")
                match = re.search(r'^  wait_for_server "http[^\n]*\n((?:  #[^\n]*\n)*)  mark_benchmark_measure_start$',
                                  text, flags=re.M)
                self.assertIsNotNone(match, rel)


class InProcessCollectorTests(unittest.TestCase):
    def helper(self, rel: str):
        tree = ast.parse((COMPONENTS / rel).read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "mark_measure_start")
        namespace: dict = {}
        exec(compile(ast.Module(body=[node], type_ignores=[]), rel, "exec"), namespace)
        return namespace["mark_measure_start"]

    def test_each_collector_marks_its_timed_loop(self) -> None:
        for rel in IN_PROCESS:
            with self.subTest(collector=rel):
                text = (COMPONENTS / rel).read_text(encoding="utf-8")
                self.assertIn("def mark_measure_start() -> None:", text)
                calls = re.findall(r"^\s+mark_measure_start\(\)", text, flags=re.M)
                self.assertGreaterEqual(len(calls), 1, rel)

    def test_helper_writes_once_and_only_under_the_runner(self) -> None:
        for rel in IN_PROCESS:
            with self.subTest(collector=rel), tempfile.TemporaryDirectory() as tmp:
                mark = self.helper(rel)
                target = Path(tmp) / "measure"
                saved = os.environ.pop("BENCHMARK_MEASURE_START_FILE", None)
                try:
                    mark()  # outside run_benchmark.sh: nothing
                    self.assertFalse(target.exists())
                    os.environ["BENCHMARK_MEASURE_START_FILE"] = str(target)
                    mark()
                    first = target.read_text(encoding="utf-8")
                    self.assertRegex(first, r"^\d{19}\n$")
                    mark()  # the first call of the run wins
                    self.assertEqual(target.read_text(encoding="utf-8"), first)
                finally:
                    os.environ.pop("BENCHMARK_MEASURE_START_FILE", None)
                    if saved is not None:
                        os.environ["BENCHMARK_MEASURE_START_FILE"] = saved


class OutputTests(unittest.TestCase):
    def test_results_page_path_is_not_printed(self) -> None:
        text = (ROOT / "scripts" / "update_runtime_ledger.py").read_text(encoding="utf-8")
        self.assertNotIn('print(f"Results page updated', text)

    def test_run_tables_have_no_setup_column(self) -> None:
        for rel in ("user_scripts/list_runs.sh", "user_scripts/get_benchmark_results.sh"):
            with self.subTest(script=rel):
                text = (ROOT / rel).read_text(encoding="utf-8")
                self.assertIn('"workload", "profile", "benchmark", "exit_code"', text)
                self.assertNotIn('runtime_setup_mm_ss', text)


if __name__ == "__main__":
    unittest.main()
