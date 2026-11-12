"""TEMPLATE_00_134: generation-batch robustness from the TEMPLATE_00_133 review.

1. A temporary remote failure (lock, mirror, reboot in progress, status-check timeout) is
   retried once; a real failure is recorded at once with the last lines of setup output.
2. The console stays short: no specification dump, remote output streamed to a batch log.
3. A fresh AMD host is identified by PCI ID or workload series, not reported as "will fail".
4. The estimate uses measured reference times and scales only the download share.
7. Preflight re-runs itself with the Python that has PyYAML instead of exiting 1.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import create_one_workload as col  # noqa: E402
import host_exec  # noqa: E402
import remote_host_preflight as rhp  # noqa: E402

AMD_WORKLOADS = [str(n) for n in range(101, 133)]


def completed(rc: int, out: str = "", err: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["ssh"], rc, out, err)


class TransientRetryTest(unittest.TestCase):
    def test_classifier_retries_only_temporary_causes(self) -> None:
        self.assertEqual(col.classify_transient("E: Could not get lock /var/lib/dpkg/lock-frontend", []), "apt/dpkg lock")
        self.assertEqual(col.classify_transient("E: dpkg was interrupted, you must manually run", []), "dpkg interrupted")
        self.assertEqual(col.classify_transient("E: Failed to fetch http://archive.ubuntu.com/x.deb  Hash Sum mismatch", []), "package mirror")
        self.assertEqual(col.classify_transient("", ["setup.sh start", "Auto-resume service enabled: r127"]),
                         "setup stopped after enabling the reboot-resume service")
        # A missing package is also apt exit 100, and a later build failure is real.
        self.assertEqual(col.classify_transient("E: Unable to locate package libfoo", []), "")
        self.assertEqual(col.classify_transient("make: *** Error 1", ["Auto-resume service enabled: r", "build failed"]), "")

    def _validate(self, runs: list[subprocess.CompletedProcess[str]], tail: list[str]) -> tuple[int, mock.Mock]:
        repo = Path(tempfile.mkdtemp()) / "127-gpu-bench-amd-vllm-kvcache-stress-ubu2404"
        repo.mkdir()
        run_script = mock.Mock(side_effect=runs)
        with mock.patch.object(col, "remote_setup_running", return_value=False), \
                mock.patch.object(col, "_check_platform_policy", return_value=0), \
                mock.patch.object(col, "remote_exists", return_value=False), \
                mock.patch.object(col, "remote_copy", return_value=0), \
                mock.patch.object(col, "env_reuse_stamp", return_value="s"), \
                mock.patch.object(col, "ssh_run", run_script), \
                mock.patch.object(col, "remote_install_tail", return_value=tail), \
                mock.patch.object(col, "wait_for_ssh", return_value=True), \
                mock.patch.object(col, "wait_remote_idle", return_value=True), \
                mock.patch.object(col, "_sync_remote_env_stamp"), \
                mock.patch.object(col.time, "sleep"):
            rc = col.remote_validate("ssh root@h", repo, reuse=False)
        return rc, run_script

    def test_lock_failure_is_retried_once_with_the_resume_script(self) -> None:
        rc, run = self._validate([completed(100, "E: Could not get lock /var/lib/dpkg/lock"), completed(0, col.REMOTE_OK)], [])
        self.assertEqual(rc, 0)
        self.assertEqual(run.call_count, 2)
        self.assertIn("--resume-auto", run.call_args_list[1].args[1])
        self.assertEqual(col.LAST_REMOTE["127-gpu-bench-amd-vllm-kvcache-stress-ubu2404"]["transient_retry"], "apt/dpkg lock")

    def test_missing_package_is_not_retried_and_keeps_the_tail(self) -> None:
        tail = [f"line {n}" for n in range(60)][-col.TAIL_LINES:]
        rc, run = self._validate([completed(100, "E: Unable to locate package libfoo")], tail)
        self.assertEqual(rc, 100)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(col.LAST_REMOTE["127-gpu-bench-amd-vllm-kvcache-stress-ubu2404"]["output_tail"], tail)

    def test_status_check_timeout_waits_for_ssh_and_asks_again(self) -> None:
        calls = [subprocess.TimeoutExpired(["ssh"], 60), completed(0, "")]
        with mock.patch.object(col, "ssh_run", side_effect=calls) as run, \
                mock.patch.object(col, "wait_for_ssh", return_value=True):
            result = col.ssh_probe("ssh root@h", "pgrep -af setup.sh || true")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(run.call_count, 2)

    def test_record_keeps_full_reason_tail_and_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            long_reason = "x" * 900
            col.record(root, "127", "r", "failed", "2026-11-11T00:00:00Z", "2026-11-11T00:01:00Z", long_reason,
                       return_code=100, output_tail=["a", "b"], transient_retry="apt/dpkg lock")
            row = json.loads((root / "batch_generation_manifest.json").read_text(encoding="utf-8"))["repositories"][0]
        attempt = row["attempts"][0]
        self.assertEqual(len(attempt["reason"]), 900)
        self.assertEqual(attempt["output_tail"], ["a", "b"])
        self.assertEqual(attempt["transient_retry"], "apt/dpkg lock")


class ConsoleLogTest(unittest.TestCase):
    def test_specification_extraction_is_quiet(self) -> None:
        import re

        text = (ROOT / "scripts" / "create_generated_repo.py").read_text(encoding="utf-8")
        calls = re.findall(r'"scripts/extract_benchmark_definition\.py",\s*"--workload".*?\]', text, flags=re.S)
        self.assertEqual(len(calls), 2)
        for call in calls:
            self.assertIn('"--quiet"', call)

    def test_stream_writes_the_log_and_prints_only_a_heartbeat(self) -> None:
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "batch.log"
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                result = host_exec.run_host_bash(
                    "echo first; sleep 1.5; echo second; echo oops >&2",
                    stream_log=log, heartbeat_label="216", heartbeat_s=0.5,
                )
            text = log.read_text(encoding="utf-8")
        self.assertEqual(result.returncode, 0)
        self.assertIn("first", result.stdout)
        self.assertIn("oops", result.stderr)
        self.assertIn("first\n", text)
        self.assertIn("[stderr] oops", text)
        console = out.getvalue()
        self.assertIn("[216] still running", console)
        self.assertNotIn("second", console)

    def test_stream_timeout_raises_like_subprocess_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(subprocess.TimeoutExpired):
                host_exec.run_host_bash("sleep 5", timeout=1, stream_log=Path(tmp) / "b.log", heartbeat_s=60)


class VendorAndEstimateTest(unittest.TestCase):
    FRESH_AMD = {"vendor": "none", "os_version_id": "24.04", "pci_gpu_vendors": "0x1002 0x1af4",
                 "download_huggingface_bps": "21400000", "download_pytorch_bps": "457000000"}

    def test_fresh_amd_host_is_amd_from_pci_with_an_info_note(self) -> None:
        values = dict(self.FRESH_AMD)
        warnings, notes = rhp.evaluate(values, AMD_WORKLOADS, {}, 1.0)
        self.assertFalse([w for w in warnings if "will fail" in w])
        self.assertTrue([n for n in notes if "ROCm is not installed yet" in n])
        self.assertEqual((values["vendor_resolved"], values["vendor_source"]), ("amd", "pci"))
        self.assertEqual(rhp.estimate_minutes(values, AMD_WORKLOADS, 1.0)["reference_platform"], "amd-24.04")

    def test_series_decides_when_pci_is_not_readable(self) -> None:
        vendor, source, warnings, _ = rhp.resolve_vendor({"vendor": "none"}, AMD_WORKLOADS)
        self.assertEqual((vendor, source, warnings), ("amd", "workload series", []))

    def test_contradiction_and_no_gpu_warn(self) -> None:
        self.assertTrue(rhp.resolve_vendor({"vendor": "nvidia", "pci_gpu_vendors": "0x10de"}, AMD_WORKLOADS)[2])
        warnings = rhp.resolve_vendor({"vendor": "none", "pci_gpu_vendors": ""}, AMD_WORKLOADS)[2]
        self.assertTrue([w for w in warnings if "No GPU tools" in w])

    def test_missing_nvidia_smi_stays_a_warning(self) -> None:
        warnings = rhp.resolve_vendor({"vendor": "none", "pci_gpu_vendors": "0x10de"}, ["201", "202"])[2]
        self.assertTrue([w for w in warnings if "nvidia-smi is missing" in w])

    def test_estimate_scales_only_the_download_share(self) -> None:
        values = dict(self.FRESH_AMD, vendor_resolved="amd")
        x01 = rhp.estimate_minutes(values, ["101"], 1.0)
        self.assertEqual(x01["estimated_minutes"], x01["reference_minutes"])  # x01 is not a download workload
        heavy = rhp.estimate_minutes(values, ["130"], 1.0)
        factor = heavy["download_factor"]
        expected = heavy["reference_minutes"] * ((1 - rhp.DOWNLOAD_SHARE["amd"]) + rhp.DOWNLOAD_SHARE["amd"] * factor)
        self.assertAlmostEqual(heavy["estimated_minutes"], round(expected, 1), delta=0.1)
        self.assertEqual(heavy["reference_download_mb_s"], 48.8)

    def test_estimates_for_the_template_00_133_batches_are_near_the_real_time(self) -> None:
        # Wall clock (minutes) of the TEMPLATE_00_133 batches, whose old estimates were 369 and 294.
        amd = rhp.estimate_minutes(dict(self.FRESH_AMD, vendor_resolved="amd"), AMD_WORKLOADS, 1.0)
        nvidia = rhp.estimate_minutes(
            {"vendor": "nvidia", "os_version_id": "24.04", "download_huggingface_bps": "21200000",
             "download_pytorch_bps": "269000000"}, [str(n) for n in range(201, 233)], 1.0)
        self.assertLess(amd["estimated_minutes"], 1.5 * amd["reference_minutes"])
        self.assertLess(abs(nvidia["estimated_minutes"] - 75), 15)


if __name__ == "__main__":
    unittest.main()
