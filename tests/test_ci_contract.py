#!/usr/bin/env python3
# File: tests/test_ci_contract.py
# Description: Tests for the CI contract (config/ci_contract.yaml), the thin
#   caller renderer (scripts/ci_contract.py) and the shared-workflows emitter
#   (scripts/emit_shared_workflows.py).
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ci_contract  # noqa: E402
import emit_shared_workflows  # noqa: E402


def _fields(number: str, repo: str, vendor: str, os_version: str = "") -> dict[str, str]:
    return {"Workload Number": number, "Repo Name": repo, "GPU Vendor": vendor, "OS Version": os_version}


class WorkloadIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = ci_contract.load_contract(ROOT)

    def test_four_platforms(self) -> None:
        cases = [
            ("101", "sys-bench-amd-rocm-stack-validation-ubu2404", "AMD", "amd", "ubu2404", "bundle-amd-ubuntu-2404"),
            ("217", "gpu-bench-nvidia-gemm-cublas-micro-ubu2404", "NVIDIA", "nvidia", "ubu2404", "bundle-nvidia-ubuntu-2404"),
            ("315", "gpu-bench-amd-babelstream-hbm-bandwidth-ubu2604", "AMD", "amd", "ubu2604", "bundle-amd-ubuntu-2604"),
            ("428", "gpu-bench-nvidia-vllm-throughput-latency-ubu2604", "NVIDIA", "nvidia", "ubu2604", "bundle-nvidia-ubuntu-2604"),
        ]
        for number, repo, vendor, want_vendor, want_os, want_bundle in cases:
            identity = ci_contract.workload_identity(_fields(number, repo, vendor), self.contract)
            self.assertEqual(identity["vendor"], want_vendor)
            self.assertEqual(identity["os_label"], want_os)
            self.assertEqual(identity["bundle"], want_bundle)
            self.assertEqual(identity["slug"], f"{number}-{repo}")

    def test_os_label_falls_back_to_os_version(self) -> None:
        identity = ci_contract.workload_identity(
            _fields("101", "sys-bench-amd-rocm-stack-validation", "AMD", "Ubuntu 24.04"), self.contract
        )
        self.assertEqual(identity["os_label"], "ubu2404")

    def test_unknown_vendor_or_os_is_rejected(self) -> None:
        with self.assertRaises(ci_contract.ContractError):
            ci_contract.workload_identity(_fields("101", "sys-bench-x-ubu2404", "Intel"), self.contract)
        with self.assertRaises(ci_contract.ContractError):
            ci_contract.workload_identity(_fields("101", "sys-bench-amd-x", "AMD", "Ubuntu 22.04"), self.contract)


class CallerRenderingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = ci_contract.load_contract(ROOT)
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _render(self) -> dict[str, str]:
        fields = _fields("217", "gpu-bench-nvidia-gemm-cublas-micro-ubu2404", "NVIDIA")
        return ci_contract.render_workload_callers(self.repo, fields, ROOT)

    def test_renders_exactly_two_thin_callers(self) -> None:
        stale = self.repo / ".github" / "workflows" / "nightly.yml"
        stale.parent.mkdir(parents=True)
        stale.write_text("name: old\n", encoding="utf-8")
        self._render()
        wf = self.repo / ".github" / "workflows"
        self.assertEqual(sorted(p.name for p in wf.iterdir()), ["ci.yml", "gpu-smoke.yml"])
        for name, key in (("ci.yml", "ci"), ("gpu-smoke.yml", "gpu")):
            text = (wf / name).read_text(encoding="utf-8")
            self.assertNotRegex(text, ci_contract.PLACEHOLDER_RE)
            doc = yaml.safe_load(text)
            self.assertEqual(doc["permissions"], {"contents": "read"})
            job = next(iter(doc["jobs"].values()))
            self.assertEqual(job["uses"], ci_contract.expected_uses(self.contract, key))
            self.assertEqual(job["with"]["vendor"], "nvidia")
            self.assertEqual(job["with"]["os_label"], "ubu2404")
            self.assertNotIn("steps", job)
        gpu = yaml.safe_load((wf / "gpu-smoke.yml").read_text(encoding="utf-8"))
        self.assertEqual(list(gpu[True]), ["workflow_dispatch"])  # PyYAML reads `on` as True

    def test_check_callers_flags_violations(self) -> None:
        identity = self._render()
        gpu = self.repo / ".github" / "workflows" / "gpu-smoke.yml"
        gpu.write_text(gpu.read_text(encoding="utf-8").replace("on:\n", "on:\n  pull_request:\n", 1), encoding="utf-8")
        ci = self.repo / ".github" / "workflows" / "ci.yml"
        ci.write_text(ci.read_text(encoding="utf-8").replace("@v1", "@main").replace("vendor: nvidia", "vendor: amd"),
                      encoding="utf-8")
        errors = " | ".join(ci_contract.check_callers(self.repo, self.contract, identity))
        self.assertIn("never trigger on pull requests", errors)
        self.assertIn("expected one job using", errors)
        self.assertIn("vendor input is 'amd'", errors)

    def test_unresolved_placeholder_is_an_error(self) -> None:
        with self.assertRaises(ci_contract.ContractError):
            ci_contract.render_text("uses: __NOT_A_KEY__", {}, "x")


class EmitterTests(unittest.TestCase):
    def test_emit_then_check_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            argv = ["emit_shared_workflows.py", "--output-root", tmp, "--template-root", str(ROOT)]
            sys.argv = argv
            self.assertEqual(emit_shared_workflows.main(), 0)
            sys.argv = argv + ["--check"]
            self.assertEqual(emit_shared_workflows.main(), 0)
            shared = Path(tmp) / "shared-workflows"
            for rel in (".github/workflows/ci.yml", ".github/workflows/gpu-smoke.yml",
                        ".github/workflows/self-test.yml", ".github/dependabot.yml", "README.md", "LICENSE",
                        "tests/fixtures/sample-workload/.github/workflows/ci.yml",
                        "tests/fixtures/sample-workload/schemas/benchmark_specification.schema.json"):
                self.assertTrue((shared / rel).is_file(), rel)
            suite = Path(tmp) / "gpu-bench-suite"
            for rel in ("scripts/run_benchmark_suite.sh", "scripts/get_remote_info.sh",
                        "scripts/show_metrics.sh", "README.md"):
                self.assertTrue((suite / rel).is_file(), rel)
            for path in list(shared.rglob("*")) + list(suite.rglob("*")):
                if path.is_file():
                    self.assertNotRegex(path.read_text(encoding="utf-8"), ci_contract.PLACEHOLDER_RE, str(path))
            gpu = yaml.safe_load((shared / ".github/workflows/gpu-smoke.yml").read_text(encoding="utf-8"))
            self.assertEqual(list(gpu[True]), ["workflow_call"])

    def test_refuses_to_overwrite_without_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            (Path(tmp) / "shared-workflows").mkdir()
            (Path(tmp) / "shared-workflows" / "keep.txt").write_text("x", encoding="utf-8")
            sys.argv = ["emit_shared_workflows.py", "--output-root", tmp, "--template-root", str(ROOT)]
            with self.assertRaises(SystemExit):
                emit_shared_workflows.main()

    def test_suite_scripts_carry_no_lab_hosts(self) -> None:
        text = (ROOT / "templates" / "suite-tools" / "scripts" / "get_remote_info.sh").read_text(encoding="utf-8")
        self.assertNotRegex(text, r"\b(?!203\.0\.113\.)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
        self.assertNotIn("gmb-amd", text)


if __name__ == "__main__":
    unittest.main()
