#!/usr/bin/env python3
# File: tests/test_template_00_127_sglang.py
# Description: TEMPLATE_00_127 SGLang fixes from the 2026-11-08 fresh-VM runs.
#   1. prefetch_sglang_model.py downloads config.json and refuses a snapshot
#      without model_type (130/230/430 servers died on that).
#   2. AMD setup installs only the pinned amd-aiter wheel, defers its import
#      until after the postponed amdgpu reboot, and time-limits it (330 spun 49
#      minutes after building unpinned AITER HEAD).
#   3. Smoke uses max_total_tokens 1024 from the workbook; NVIDIA smoke adds
#      --disable-cuda-graph.
#   4. The SGLang runners restart the published clock after the model download.
#   5. The 26.04 NVIDIA installer pins torch while installing the runtime deps.
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "implementation_components"
SGLANG = (
    "sglang-prompt-response-amd",
    "sglang-prompt-response-nvidia",
    "sglang-serving-amd",
    "sglang-serving-nvidia",
)
AMD_SETUP = ROOT / "scripts" / "templates" / "setup_rocm_reboot_skeleton.sh"
AITER_VERSION = "0.1.22.post2.dev0+gb4d9154d1.d20261002"


def source(component: str, rel: str) -> str:
    return (COMPONENTS / component / "files" / rel).read_text(encoding="utf-8")


def load_prefetch():
    path = COMPONENTS / SGLANG[0] / "files" / "scripts" / "prefetch_sglang_model.py"
    spec = importlib.util.spec_from_file_location("prefetch_sglang_127", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _NotFound(Exception):
    pass


class PrefetchRequiresConfig(unittest.TestCase):
    REMOTE = {
        "model.safetensors.index.json": json.dumps({"weight_map": {"a": "model-00001-of-00001.safetensors"}}),
        "model-00001-of-00001.safetensors": "w",
        "config.json": json.dumps({"model_type": "mistral"}),
        "generation_config.json": "{}",
        "tokenizer.json": "{}",
        "tokenizer.model": "m",
        "tokenizer_config.json": "{}",
        "special_tokens_map.json": "{}",
    }

    def setUp(self) -> None:
        self.module = load_prefetch()
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.snapshot = self.tmp / "hub" / "models--m--x" / "snapshots" / "rev1"
        self.snapshot.mkdir(parents=True)
        self.previous_home = os.environ.get("HF_HOME")
        os.environ["HF_HOME"] = str(self.tmp)
        self.saved_modules = {name: sys.modules.get(name) for name in ("huggingface_hub", "huggingface_hub.utils")}
        self.addCleanup(self._restore)
        self.calls: list[str] = []

    def _restore(self) -> None:
        if self.previous_home is None:
            os.environ.pop("HF_HOME", None)
        else:
            os.environ["HF_HOME"] = self.previous_home
        for name, module in self.saved_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def fake_hub(self, remote: dict[str, str]) -> None:
        snapshot, calls = self.snapshot, self.calls

        def download(repo_id, name, revision=None):
            calls.append(name)
            if name not in remote:
                raise _NotFound(name)
            (snapshot / name).write_text(remote[name], encoding="utf-8")
            return str(snapshot / name)

        hub = types.ModuleType("huggingface_hub")
        hub.hf_hub_download = download
        utils = types.ModuleType("huggingface_hub.utils")
        utils.EntryNotFoundError = _NotFound
        sys.modules["huggingface_hub"] = hub
        sys.modules["huggingface_hub.utils"] = utils

    def test_copies_are_identical(self) -> None:
        texts = {source(component, "scripts/prefetch_sglang_model.py") for component in SGLANG}
        self.assertEqual(len(texts), 1)

    def test_fetches_config_into_a_weights_and_tokenizer_snapshot(self) -> None:
        # The 2026-11-08 state: shards and tokenizer cached, no config.json.
        for name in ("model.safetensors.index.json", "model-00001-of-00001.safetensors",
                     "tokenizer.json", "tokenizer.model", "tokenizer_config.json"):
            (self.snapshot / name).write_text(self.REMOTE[name], encoding="utf-8")
        self.assertFalse(self.module.config_complete(self.snapshot))
        self.fake_hub(self.REMOTE)
        self.assertEqual(self.module.ensure_snapshot("m/x", verify=False), self.snapshot)
        self.assertIn("config.json", self.calls)
        self.assertIn("generation_config.json", self.calls)
        self.assertTrue(self.module.snapshot_complete(self.snapshot))

    def test_generation_config_is_optional(self) -> None:
        remote = dict(self.REMOTE)
        remote.pop("generation_config.json")
        self.fake_hub(remote)
        self.module.ensure_snapshot("m/x", verify=False)

    def test_refuses_a_repo_without_config(self) -> None:
        remote = dict(self.REMOTE)
        remote.pop("config.json")
        self.fake_hub(remote)
        with self.assertRaises(SystemExit) as ctx:
            self.module.ensure_snapshot("m/x", verify=False)
        self.assertIn("config.json", str(ctx.exception))

    def test_refuses_config_without_model_type(self) -> None:
        remote = dict(self.REMOTE)
        remote["config.json"] = json.dumps({"hidden_size": 8})
        self.fake_hub(remote)
        with self.assertRaises(SystemExit) as ctx:
            self.module.ensure_snapshot("m/x", verify=False)
        self.assertIn("model_type", str(ctx.exception))

    def test_loads_config_and_tokenizer_offline(self) -> None:
        text = source(SGLANG[0], "scripts/prefetch_sglang_model.py")
        self.assertIn("AutoConfig.from_pretrained(str(snapshot), local_files_only=True)", text)
        self.assertIn("AutoTokenizer.from_pretrained(str(snapshot), local_files_only=True)", text)


class AmdAiterWheelOnly(unittest.TestCase):
    def setUp(self) -> None:
        self.setup = AMD_SETUP.read_text(encoding="utf-8")
        start = self.setup.index('if [[ "${BENCHMARK_INSTALL_AITER}" == 1 ]]; then\n  # ROCm 10.1.0 publishes amd-aiter')
        self.block = self.setup[start:self.setup.index("\nfi\n", start) + 4]

    def test_no_source_build(self) -> None:
        self.assertNotIn("github.com/ROCm/aiter.git", self.setup)
        self.assertNotIn("setup.py develop", self.setup)
        self.assertNotIn("AITER_SOURCE_DIR", self.setup)
        self.assertIn('amd-aiter==${AITER_VERSION}', self.block)
        self.assertIn(f'AITER_VERSION="${{AITER_VERSION:-{AITER_VERSION}}}"', self.setup)

    def test_import_waits_for_the_reboot_and_is_time_limited(self) -> None:
        self.assertIn('if [[ "${GPU_CHECKS_AFTER_REBOOT}" == 1 ]]; then', self.block)
        self.assertIn('timeout "${aiter_import_timeout}"', self.block)
        self.assertIn("AITER_IMPORT_TIMEOUT_SEC", self.block)
        self.assertIn("results/aiter_import.log", self.block)
        self.assertNotIn(">/dev/null 2>&1", self.block.split("aiter_installed_version=")[1].split("export SGLANG_USE_AITER")[0])

    @unittest.skipUnless(shutil.which("bash") and shutil.which("timeout"), "needs bash and timeout")
    def test_block_behaviour(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "block.sh").write_text(self.block, encoding="utf-8")
        fake = tmp / "fakepy"
        fake.write_text(
            "#!/bin/bash\n"
            'if [[ "$1" == "-m" && "$2" == "pip" ]]; then echo PIP >> calls.log; echo "$AITER_VERSION" > ver; exit 0; fi\n'
            'case "$2" in\n'
            '  *importlib.metadata*) [[ -s ver ]] && cat ver || exit 1 ;;\n'
            '  *"import aiter"*) echo IMPORT >> calls.log\n'
            '    case "$FAKE_IMPORT" in ok) exit 0;; fail) echo "ImportError: x" >&2; exit 1;; hang) sleep 20;; esac ;;\n'
            "esac\n",
            encoding="utf-8",
        )
        fake.chmod(0o755)

        def run(installed: str, mode: str, after_reboot: int) -> tuple[int, str, str]:
            for name in ("calls.log", "ver"):
                (tmp / name).unlink(missing_ok=True)
            if installed:
                (tmp / "ver").write_text(installed + "\n", encoding="utf-8")
            script = (
                "set -euo pipefail\n"
                'die(){ echo "DIE: $*"; exit 1; }; log_warn(){ echo "WARN: $*"; }\n'
                'install_status_log_step(){ echo "STEP: $*"; }\n'
                f"PYTHON_BIN=./fakepy VENV_ROOT={tmp}/novenv REPO_ROOT={tmp} BENCHMARK_INSTALL_AITER=1\n"
                f"GPU_CHECKS_AFTER_REBOOT={after_reboot} AITER_IMPORT_TIMEOUT_SEC=2 VLLM_WHEEL_INDEX_URL=https://idx\n"
                "source ./block.sh\n"
            )
            env = dict(os.environ, FAKE_IMPORT=mode, AITER_VERSION=AITER_VERSION)
            done = subprocess.run(["bash", "-c", script], cwd=tmp, env=env, capture_output=True, text=True, timeout=60)
            calls = (tmp / "calls.log").read_text(encoding="utf-8") if (tmp / "calls.log").exists() else ""
            return done.returncode, done.stdout + done.stderr, calls

        rc, out, calls = run("", "ok", 1)
        self.assertEqual(rc, 0, out)
        self.assertIn("import check after the reboot", out)
        self.assertEqual(calls.split(), ["PIP"])  # installed, never imported
        rc, out, calls = run("0.1.29.dev157+gd356386f8", "ok", 1)
        self.assertEqual(rc, 0, out)
        self.assertIn("replacing it with the pinned", out)
        rc, out, calls = run(AITER_VERSION, "ok", 0)
        self.assertEqual(rc, 0, out)
        self.assertEqual(calls.split(), ["IMPORT"])
        rc, out, _ = run(AITER_VERSION, "fail", 0)
        self.assertNotEqual(rc, 0)
        self.assertIn("does not build AITER from source", out)
        rc, out, _ = run(AITER_VERSION, "hang", 0)
        self.assertNotEqual(rc, 0)
        self.assertIn("did not finish within 2s", out)

    def test_runtime_checks_are_time_limited(self) -> None:
        for component in ("sglang-prompt-response-amd", "sglang-serving-amd"):
            with self.subTest(component=component):
                text = source(component, "scripts/ensure_setup.sh")
                self.assertIn('SETUP_CHECK_TIMEOUT_SEC="${SETUP_CHECK_TIMEOUT_SEC:-300}"', text)
                self.assertEqual(text.count('elif ! "${REPO_ROOT}/.venv/bin/python"'), 0)
                self.assertEqual(text.count('elif ! timeout "${SETUP_CHECK_TIMEOUT_SEC}"'), 4)


class SmokeServerAndClock(unittest.TestCase):
    def test_runners_restart_the_clock_after_the_download(self) -> None:
        for component in SGLANG:
            with self.subTest(component=component):
                text = source(component, "run_benchmark.sh")
                prefetch = text.index("scripts/prefetch_sglang_model.py --model-id")
                launch = text.index('server_cmd="${PYTHON_BIN} -m sglang.launch_server')
                restart = text.index("  mark_benchmark_measure_start\n", prefetch)
                self.assertLess(prefetch, restart)
                self.assertLess(restart, launch)

    def test_nvidia_smoke_disables_cuda_graphs_only_on_smoke(self) -> None:
        for component in ("sglang-prompt-response-nvidia", "sglang-serving-nvidia"):
            with self.subTest(component=component):
                text = source(component, "run_benchmark.sh")
                self.assertIn('if [[ "${PROFILE}" == "smoke" ]]; then', text)
                self.assertIn('server_cmd+=" --disable-cuda-graph"', text)
                self.assertIn("--attention-backend flashinfer", text)

    def test_workbook_smoke_kv_budget(self) -> None:
        sheet = openpyxl.load_workbook(ROOT / "BenchmarkSpecDefinitions.xlsx", read_only=True)["Parameters_SmokeBaselineExtend"]
        seen = {}
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if row[2] == "max_total_tokens" and str(row[0]) in {"130", "131", "230", "231", "330", "331", "430", "431"}:
                seen[str(row[0])] = tuple(row[3:6])
        self.assertEqual(len(seen), 8)
        for number, values in seen.items():
            with self.subTest(workload=number):
                self.assertEqual(values, (1024, 16384, 32768))


class NvidiaRuntimeDepsPinTorch(unittest.TestCase):
    def setUp(self) -> None:
        self.texts = [source(c, "scripts/install_sglang_nvidia.sh") for c in ("sglang-prompt-response-nvidia", "sglang-serving-nvidia")]
        text = self.texts[0]
        start = text.index("install_sglang_runtime_deps() {")
        self.function = text[start:text.index("\n}\n", start)]

    def test_copies_are_identical(self) -> None:
        self.assertEqual(self.texts[0], self.texts[1])

    def test_torch_is_constrained_and_torch_pullers_skip_deps(self) -> None:
        deps = self.function.split("local -a deps=(", 1)[1].split(")", 1)[0]
        for name in ("timm", "torchao", "cuda-python"):
            self.assertNotIn(name, deps)
        self.assertIn('pip install -c "${constraints}" "${deps[@]}"', self.function)
        self.assertIn('names = ("torch", "torchvision", "torchaudio", "triton", "nvidia-nccl-cu13")', self.function)
        self.assertIn("pip install --no-deps \\\n    'timm==1.0.16' 'torchao==0.9.0' 'cuda-python==12.9' 'cuda-bindings~=12.9.0'", self.function)

    def test_nccl_is_restored_before_the_first_torch_import(self) -> None:
        text = self.texts[0]
        body = text.split("install_cu130_sglang() {", 1)[1]
        self.assertLess(body.index("restore_nvidia_nccl"), body.index("import torch"))


if __name__ == "__main__":
    unittest.main()
