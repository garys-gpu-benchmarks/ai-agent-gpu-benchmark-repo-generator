#!/usr/bin/env python3
"""TEMPLATE_00_119: host robustness after the Nov 3 401-432 run (TEMPLATE_00_118).

The same 401-432 bundle took 1h48m on TEMPLATE_00_117 (Oct 22) and 3h16m on
TEMPLATE_00_118 (Nov 3). The installers were byte-identical. Three 118
collector edits failed on the Nov 3 container (kernel 6.8.0-147-generic, no
NUMA policy, iperf3 3.20), and the slower, cold VM did the rest. These tests
hold the fixes in place.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "implementation_components"


def load_collector(component: str):
    path = COMPONENTS / component / "files" / "scripts" / "collect_workload.py"
    sys.modules.setdefault("yaml", types.ModuleType("yaml"))
    spec = importlib.util.spec_from_file_location(f"collector_{component.replace('-', '_')}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def numactl_collectors() -> list[Path]:
    """Collectors that build a numactl command line themselves."""
    found = []
    for path in sorted(COMPONENTS.glob("*/files/scripts/*.py")):
        text = path.read_text(encoding="utf-8")
        if re.search(r'command\s*=\s*\[\s*"numactl"', text):
            found.append(path)
    return found


class NumactlFallbackTest(unittest.TestCase):
    def test_every_numactl_wrapper_has_a_fallback(self) -> None:
        paths = numactl_collectors()
        self.assertTrue(paths, "expected at least the GUPS and STREAM collectors")
        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertTrue(
                "numactl_or_plain(" in text or "strip_numactl(" in text,
                f"{path.relative_to(ROOT)} wraps the benchmark in numactl with no fallback for a host without NUMA policy",
            )

    def test_numactl_or_plain_drops_the_bind_when_numactl_is_missing(self) -> None:
        for component in ("stream-collect-nvidia", "stream-collect-amd"):
            module = load_collector(component)
            command, note = module.numactl_or_plain(["numactl", "--cpunodebind=0", "--membind=0", "./stream"])
            if note:  # this test host has no numactl (or no NUMA policy)
                self.assertEqual(command, ["./stream"])
                self.assertIn("numactl bind skipped", note)
            self.assertEqual(module.numactl_or_plain(["./stream"]), (["./stream"], ""))

    def test_gups_nvidia_strips_numactl_flags(self) -> None:
        module = load_collector("gups-nvidia")
        self.assertEqual(module.strip_numactl(["numactl", "--cpunodebind=0", "--membind=0", "bin/gups", "1"]), ["bin/gups", "1"])
        self.assertEqual(module.strip_numactl(["bin/gups"]), ["bin/gups"])


class IperfUdpClampTest(unittest.TestCase):
    def test_both_vendors_clamp_udp_block_length(self) -> None:
        for component in ("iperf3-nvidia", "iperf3-amd"):
            module = load_collector(component)
            self.assertEqual(module.UDP_MAX_BLOCK_BYTES, 65507)
            self.assertEqual(module.length_for_protocol("udp", "128K"), "65507")
            self.assertEqual(module.length_for_protocol("tcp", "128K"), "128K")
            self.assertEqual(module.length_for_protocol("udp", "32K"), "32K")
            self.assertEqual(module.length_for_protocol("udp", ""), "")

    def test_no_collector_passes_l_without_the_clamp(self) -> None:
        for path in sorted(COMPONENTS.glob("iperf3-*/files/scripts/collect_workload.py")):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn('cmd += ["-l", str(length).strip()]', text, str(path.relative_to(ROOT)))


class KernelMismatchIsRecordedTest(unittest.TestCase):
    def test_nvidia_status_does_not_depend_on_kernel(self) -> None:
        text = (COMPONENTS / "system-config-nvidia/files/scripts/collect_workload.py").read_text(encoding="utf-8")
        status_line = next(line for line in text.splitlines() if '"status": "ok" if' in line)
        self.assertNotIn("kernel", status_line)
        self.assertIn('"kernel_release_mismatch_count"', text)
        self.assertIn("kernel_check.txt", text)

    def test_amd_and_nvidia_record_the_same_kernel_column(self) -> None:
        amd = (COMPONENTS / "system-config-amd/files/scripts/collect_workload.py").read_text(encoding="utf-8")
        nvidia = (COMPONENTS / "system-config-nvidia/files/scripts/collect_workload.py").read_text(encoding="utf-8")
        for text in (amd, nvidia):
            self.assertIn('"kernel_release_mismatch_count": float(kernel_mismatch)', text)


class LedgerFailedRunIsNotPassTest(unittest.TestCase):
    def test_nonzero_exit_overrides_metric_status(self) -> None:
        text = (ROOT / "scripts/update_runtime_ledger.py").read_text(encoding="utf-8")
        self.assertRegex(text, r"if args\.exit_code != 0:\s*\n(?:\s*#.*\n)*\s*from metric_contract import RUN_FAILED_STATUS\s*\n\s*result_status = RUN_FAILED_STATUS")
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            import metric_contract
        finally:
            sys.path.pop(0)
        self.assertEqual(metric_contract.RUN_FAILED_STATUS, "FAIL")


class SiblingGuardParityTest(unittest.TestCase):
    """A host guard in one vendor's collector must exist in its sibling.

    TEMPLATE_00_118 added iperf3 -l and a GUPS numactl wrapper; the fixes were
    then written in one batch's copy only. Any guard named here must be present
    in both <name>-nvidia and <name>-amd when both exist.
    """

    GUARDS = ("length_for_protocol", "UDP_MAX_BLOCK_BYTES")

    def test_guards_match_across_vendors(self) -> None:
        for nvidia_dir in sorted(COMPONENTS.glob("*-nvidia")):
            amd_dir = COMPONENTS / (nvidia_dir.name[: -len("-nvidia")] + "-amd")
            if not amd_dir.is_dir():
                continue
            for script in sorted((nvidia_dir / "files/scripts").glob("collect_workload.py")):
                sibling = amd_dir / "files/scripts" / script.name
                if not sibling.is_file():
                    continue
                a, b = script.read_text(encoding="utf-8"), sibling.read_text(encoding="utf-8")
                for guard in self.GUARDS:
                    self.assertEqual(guard in a, guard in b, f"{guard}: {nvidia_dir.name} vs {amd_dir.name}")
                self.assertEqual(
                    ("numactl_or_plain(" in a or "strip_numactl(" in a) if '"numactl"' in a else True,
                    True,
                    nvidia_dir.name,
                )
                if '"numactl"' in b:
                    self.assertTrue("numactl_or_plain(" in b or "strip_numactl(" in b, amd_dir.name)


class RemotePreflightTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import remote_host_preflight

        cls.mod = remote_host_preflight

    NOV3 = {
        "os_version_id": "26.04",
        "kernel": "6.8.0-147-generic",
        "vendor": "nvidia",
        "nvcc": "missing",
        "dcgmi": "missing",
        "numactl_bind": "rc=1 This system does not support NUMA policy",
        "disk_free_gb_opt": "480",
        "disk_free_gb_home": "480",
        "hf_token": "present",
        "download_huggingface_bps": "12000000",
        "download_pytorch_bps": "20000000",
    }

    def test_parse_probe_reads_only_marked_lines(self) -> None:
        text = "noise\nPREFLIGHT_KV kernel=6.8.0-147-generic\nPREFLIGHT_KV numactl_bind=rc=1 no NUMA\n"
        self.assertEqual(
            self.mod.parse_probe(text),
            {"kernel": "6.8.0-147-generic", "numactl_bind": "rc=1 no NUMA"},
        )

    def test_nov3_host_produces_warnings_not_errors(self) -> None:
        workloads = [str(n) for n in range(401, 433)]
        kernels = {"401": "7.0.0"}
        warnings, notes = self.mod.evaluate(self.NOV3, workloads, kernels, ssh_call_s=2.0)
        joined = " ".join(warnings)
        self.assertIn("kernel 6.8.0-147-generic does not match workbook kernel_version 7.0.0", joined)
        self.assertIn("numactl cannot bind", joined)
        self.assertIn("huggingface.co is 12.0 MB/s", joined)
        self.assertTrue(any("CUDA toolkit" in note for note in notes))

    def test_estimate_flags_a_slow_host(self) -> None:
        workloads = [str(n) for n in range(401, 433)]
        # TEMPLATE_00_134: reference times are the TEMPLATE_00_131 batches, and only 5% of
        # NVIDIA x21-x32 is download (the host bootstrap prefetches models), so the slow
        # download alone no longer flags the host; a slow SSH round trip still does.
        estimate = self.mod.estimate_minutes(self.NOV3, workloads, ssh_call_s=4.0)
        self.assertEqual(estimate["reference_platform"], "nvidia-26.04")
        self.assertAlmostEqual(estimate["reference_minutes"], 94.3, delta=1.0)
        self.assertGreater(estimate["estimated_minutes"], 1.5 * estimate["reference_minutes"])

    def test_kernel_prefix_rule_matches_the_collector(self) -> None:
        self.assertTrue(self.mod.kernel_matches("7.0.0", "7.0.0-14-generic"))
        self.assertFalse(self.mod.kernel_matches("7.0.0", "6.8.0-147-generic"))
        self.assertTrue(self.mod.kernel_matches("", "6.8.0-147-generic"))

    def test_preflight_never_raises_and_records(self) -> None:
        import tempfile

        def broken_ssh_run(*_args, **_kwargs):
            raise OSError("ssh is down")

        with tempfile.TemporaryDirectory() as tmp:
            report = self.mod.run_preflight(broken_ssh_run, "ssh root@1.2.3.4", ["401", "402"], ROOT, Path(tmp))
            self.assertIn(report["status"], {"error", "probe_failed"})
            manifest = (Path(tmp) / "batch_generation_manifest.json").read_text(encoding="utf-8")
            self.assertIn("remote_host_preflight", manifest)

    def test_workbook_kernel_for_401(self) -> None:
        kernels = self.mod.workbook_values(ROOT / "BenchmarkSpecDefinitions.xlsx", ["401", "402"], "kernel_version")
        self.assertEqual(kernels.get("401"), "7.0.0")
        self.assertNotIn("402", kernels)


class HostBootstrapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        import remote_host_bootstrap

        cls.mod = remote_host_bootstrap

    def test_models_follow_the_batch_and_keep_workload_repo_ids(self) -> None:
        specs = self.mod.models_for([str(n) for n in range(401, 433)])
        repos = [spec.partition("|")[0] for spec in specs]
        self.assertEqual(
            repos,
            [
                "bert-base-uncased",
                "stabilityai/stable-diffusion-xl-base-1.0",
                "distilbert-base-uncased",
                "mistralai/Mistral-7B-v0.3",
                "BAAI/bge-small-en-v1.5",
                "BAAI/bge-reranker-base",
            ],
        )
        self.assertEqual(self.mod.models_for(["402", "407"]), [])
        for spec in specs:
            self.assertNotIn(" ", spec, "specs are passed space-separated")

    def test_sdxl_patterns_match_the_installer(self) -> None:
        installer = (COMPONENTS / "sdxl-diffusers-nvidia/files/scripts/install_sdxl_python.sh").read_text(encoding="utf-8")
        for pattern in self.mod.SDXL_PATTERNS.split(";"):
            self.assertIn(f'"{pattern}"', installer)

    def test_vendor_guess(self) -> None:
        self.assertEqual(self.mod.guess_vendor(["401"], {"values": {"vendor": "amd"}}), "amd")
        self.assertEqual(self.mod.guess_vendor(["401", "432"], None), "nvidia")
        self.assertEqual(self.mod.guess_vendor(["101"], None), "amd")

    def test_bootstrap_files_exist_and_parse(self) -> None:
        import subprocess

        for rel in self.mod.FILES:
            path = ROOT / "scripts" / rel
            self.assertTrue(path.is_file(), rel)
            if path.suffix == ".sh":
                self.assertEqual(subprocess.run(["bash", "-n", str(path)]).returncode, 0, rel)

    def test_bootstrap_always_exits_zero_and_disables_globbing(self) -> None:
        text = (ROOT / "scripts/remote/host_bootstrap.sh").read_text(encoding="utf-8")
        self.assertIn("set -f", text)
        self.assertNotIn("set -e", text.replace("set -euo", ""))
        self.assertTrue(text.rstrip().endswith("exit 0"))
        self.assertIn("setsid nohup", text)

    def test_bootstrap_never_raises(self) -> None:
        import tempfile

        def broken(*_args, **_kwargs):
            raise OSError("down")

        with tempfile.TemporaryDirectory() as tmp:
            report = self.mod.run_bootstrap(broken, broken, "ssh x@1.2.3.4", "ssh x@1.2.3.4", "/tmp", ["401", "432"], Path(tmp))
            self.assertEqual(report["status"], "error")

    def test_driver_runs_host_prep_before_the_loop_and_keeps_going(self) -> None:
        text = (ROOT / "scripts/create_one_workload.py").read_text(encoding="utf-8")
        main = text[text.index("def main() -> int:"):]
        self.assertLess(main.index("host_prep(ssh, workloads"), main.index("for workload in workloads:"))
        self.assertIn("--skip-host-prep", text)
        prep = text[text.index("def host_prep("):text.index("def host_prefetch_report(")]
        self.assertEqual(prep.count("except Exception"), 2)


class AptIndexOnceTest(unittest.TestCase):
    def _run(self, stamp_age: int | None, lists: bool) -> str:
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fake_bin = tmp_path / "bin"
            fake_bin.mkdir()
            (fake_bin / "apt-get").write_text("#!/bin/sh\necho APT_GET_RAN \"$@\"\n", encoding="utf-8")
            (fake_bin / "apt-get").chmod(0o755)
            state = tmp_path / "state"
            state.mkdir()
            if stamp_age is not None:
                import time as _time

                (state / "apt_updated_epoch").write_text(str(int(_time.time()) - stamp_age), encoding="utf-8")
            script = (
                f'export PATH="{fake_bin}:$PATH"; export BENCHMARK_HOST_STATE_DIR="{state}"; '
                f'source "{ROOT}/scripts/lib/nvidia_cuda_toolkit.sh"; '
                + ('compgen() { return 0; }; ' if lists else 'compgen() { return 1; }; ')
                + "nvidia_apt_update_once; echo RC=$?; cat \"$BENCHMARK_HOST_STATE_DIR/apt_updated_epoch\" >/dev/null && echo STAMP"
            )
            done = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
            return done.stdout + done.stderr

    def test_fresh_stamp_skips(self) -> None:
        out = self._run(600, lists=True)
        self.assertNotIn("APT_GET_RAN", out)
        self.assertIn("skipping apt-get update", out)

    def test_old_stamp_or_no_stamp_or_no_lists_refreshes(self) -> None:
        for age, lists in ((30000, True), (None, True), (600, False)):
            out = self._run(age, lists)
            self.assertIn("APT_GET_RAN update -y", out, (age, lists))
            self.assertIn("STAMP", out)

    def test_every_nvidia_setup_uses_it(self) -> None:
        paths = [ROOT / "scripts/templates/setup_nvidia_skeleton.sh"] + sorted(COMPONENTS.glob("*-nvidia/files/setup.sh"))
        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("\nDEBIAN_FRONTEND=noninteractive apt-get update -y\n", text, path.name)
            self.assertIn("nvidia_apt_update_once", text, str(path.relative_to(ROOT)))


class HuggingFaceDownloadTest(unittest.TestCase):
    def test_xet_is_off_by_default(self) -> None:
        common = (ROOT / "scripts/lib/common.sh").read_text(encoding="utf-8")
        self.assertIn('export HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"', common)
        for vendor in ("nvidia", "amd"):
            text = (COMPONENTS / f"rag-faiss-end2end-{vendor}/files/scripts/install_rag_{vendor}.sh").read_text(encoding="utf-8")
            self.assertIn('export HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"', text)
            self.assertIn('export HF_HOME="${HF_HOME:-${HOME}/.cache/huggingface}"', text)


class SglangSingleTorchTest(unittest.TestCase):
    def test_setup_installs_only_torch_2_13(self) -> None:
        text = (COMPONENTS / "sglang-prompt-response-nvidia/files/setup.sh").read_text(encoding="utf-8")
        self.assertNotIn("torch==2.9.1", text)
        self.assertNotIn("torchvision==0.24.1", text)
        self.assertIn("'torch==2.13.0+cu130'", text)

    def test_kernel_reinstall_is_conditional(self) -> None:
        for comp in ("sglang-prompt-response-nvidia", "sglang-serving-nvidia"):
            text = (COMPONENTS / comp / "files/scripts/install_sglang_nvidia.sh").read_text(encoding="utf-8")
            body = text[text.index("install_cu130_sglang() {"):text.index("install_legacy_sglang() {")]
            self.assertIn("if cu130_stack_ok; then", body)
            self.assertIn("if ! cu130_stack_ok; then", body)
            # Two former unconditional reinstalls now go through the stack check.
            self.assertEqual(body.count("reinstall_sglang_kernel"), 2, comp)
            # The only direct one left is the repair path, which runs only when
            # launch_server, the sampler or sgl_kernel fails to import.
            direct = body.count("--force-reinstall --no-deps 'sglang-kernel")
            self.assertEqual(direct, 1, comp)
            repair = body[body.index('if ! "${PYTHON_BIN}" -c "from sglang.srt.entrypoints.http_server import launch_server"'):]
            self.assertIn("--force-reinstall --no-deps 'sglang-kernel", repair.split("\n  fi\n", 1)[0])

    def test_both_sglang_installers_stay_identical(self) -> None:
        a = (COMPONENTS / "sglang-prompt-response-nvidia/files/scripts/install_sglang_nvidia.sh").read_bytes()
        b = (COMPONENTS / "sglang-serving-nvidia/files/scripts/install_sglang_nvidia.sh").read_bytes()
        self.assertEqual(a, b)


class BatchSchemaTest(unittest.TestCase):
    def test_new_manifest_keys_are_allowed(self) -> None:
        import json

        schema = json.loads((ROOT / "schemas/batch_generation_report.schema.json").read_text(encoding="utf-8"))
        for key in ("remote_host_preflight", "host_bootstrap", "host_prefetch", "generation_successful_seconds"):
            self.assertIn(key, schema["properties"])


if __name__ == "__main__":
    unittest.main()
