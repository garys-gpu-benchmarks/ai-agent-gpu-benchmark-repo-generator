"""TEMPLATE_00_141 checks (from the TEMPLATE_00_140 batch debriefs).

  1. batch_progress.log: [RECORD], workload [FAIL], Successful time and a final [DONE]
     line also go to a small file in the project root. Cursor stopped showing the batch
     console after about 1,000 lines (101-132 froze on 114, 201-232 on 214), so waits on
     the console returned up to 30 minutes late. The agent docs say to wait on the file.
  2. [TIME] lines: each local step (template copy, every _run script, the show_metrics
     refresh) and the local-create and remote phases print UTC time and duration. The
     9-10 minute local phase of x02 printed nothing that said which step was slow.
  3. Heartbeat: when the output has not changed it says for how long instead of
     repeating the same "last:" line (330, 332, 431 looked hung).
  4. setup.sh writes to /dev/tty without the shell's "No such device or address" error
     (101 in TEMPLATE_00_140).
  5. The batch warns when Excel has the template workbooks open (~$*.xlsx lock files).
  6. Collectors no longer print the CSV they have just written to the raw file (104 and
     30 more); gups-nvidia and sdc-ecc-nvidia write one row instead of the same row twice.
  7. AMD PyTorch installs numpy with torch, as the NVIDIA install already did.
  8. hipMemcpy (114/314) writes each measurement once to the raw file: the tool's own CSV
     plus the collector's copy made the parser count 114 samples for 57 rows.
  9. vLLM and SGLang runners stop the model server right after the run is measured, not
     only in the EXIT trap: the running server made the inventory take 65-68 s (127-131).
"""
from __future__ import annotations

import contextlib
import importlib
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
COMPONENTS = ROOT / "implementation_components"
AGENT_DOCS = ("docs/AI_AGENT_INSTRUCTIONS.md", ".cursor/rules/generate-workloads.mdc", "AGENTS.md")


class ProgressFileTests(unittest.TestCase):
    def test_progress_prints_and_appends(self) -> None:
        batch_progress = importlib.import_module("batch_progress")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            batch_progress.start(root, ["101", "102"])
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                batch_progress.progress(root, "[RECORD] 101 passed 7m 33s (attempt 1)")
            self.assertEqual(out.getvalue(), "[RECORD] 101 passed 7m 33s (attempt 1)\n")
            lines = (root / "batch_progress.log").read_text(encoding="utf-8").splitlines()
            self.assertTrue(lines[0].startswith("[INFO] batch started"))
            self.assertRegex(lines[1], r"^\[RECORD\] 101 passed 7m 33s \(attempt 1\) \| \d{4}-\d\d-\d\dT")
            batch_progress.start(root, ["103"])  # a new batch starts a new file
            self.assertEqual(len((root / "batch_progress.log").read_text(encoding="utf-8").splitlines()), 1)

    def test_batch_scripts_use_the_progress_file(self) -> None:
        create = (ROOT / "scripts/create_one_workload.py").read_text(encoding="utf-8")
        self.assertIn('progress(project_root, f"[RECORD] {workload}', create)
        self.assertIn('progress(project_root, f"[FAIL] {workload}: {exc}")', create)
        driver = (ROOT / "scripts/run_from_prompt.py").read_text(encoding="utf-8")
        self.assertIn("batch_progress.start(project_root, workloads)", driver)
        self.assertIn('batch_progress.progress(project_root, f"[INFO] Successful time:', driver)
        self.assertIn("[DONE] batch process exiting", driver)

    def test_agent_docs_wait_on_the_progress_file(self) -> None:
        for rel in AGENT_DOCS:
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("tail -n +1 -F batch_progress.log", text, rel)
            self.assertIn("about 1,000 lines", text, rel)
            self.assertIn("wait once per workload", text, rel)  # the TEMPLATE_00_139 rule stays
        for rel in ("AGENTS.md", "docs/generation-workflow.md", "docs/AI_AGENT_INSTRUCTIONS.md"):
            self.assertIn("batch_progress.log", (ROOT / rel).read_text(encoding="utf-8"), rel)


class TimingAndHeartbeatTests(unittest.TestCase):
    def test_local_steps_print_time_lines(self) -> None:
        repo = (ROOT / "scripts/create_generated_repo.py").read_text(encoding="utf-8")
        self.assertIn('_took(f"template copy to {destination.name}", started)', repo)
        self.assertIn("_took(script, started)", repo)
        self.assertIn('_took("show_metrics.sh label refresh", started)', repo)
        create = (ROOT / "scripts/create_one_workload.py").read_text(encoding="utf-8")
        self.assertIn('local create (create_generated_repo.py)', create)
        self.assertIn("remote copy, setup and smoke", create)

    def test_heartbeat_says_how_long_output_has_been_unchanged(self) -> None:
        host_exec = importlib.import_module("host_exec")
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                host_exec.run_host_bash("echo working; sleep 2.6; echo done",
                                        stream_log=Path(tmp) / "l.log", heartbeat_label="330", heartbeat_s=1.0)
        console = out.getvalue()
        self.assertIn("[330] still running", console)
        self.assertIn("no new output for", console)
        self.assertIn("(last: working)", console)


class SetupAndBatchWarningTests(unittest.TestCase):
    def test_dev_tty_write_hides_the_shell_error(self) -> None:
        text = (ROOT / "scripts/templates/setup_rocm_reboot_skeleton.sh").read_text(encoding="utf-8")
        self.assertEqual(text.count(">/dev/tty; } 2>/dev/null || true"), 2)
        self.assertNotRegex(text, r"[^;] >/dev/tty \|\| true")

    def test_open_workbooks_are_reported(self) -> None:
        driver = importlib.import_module("run_from_prompt")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(driver.open_workbooks(root), [])
            (root / "~$BenchmarkSpecDefinitions.xlsx").write_bytes(b"lock")
            self.assertEqual(driver.open_workbooks(root), ["BenchmarkSpecDefinitions.xlsx"])
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                driver.warn_open_workbooks(root)
            self.assertIn("[WARN] Excel has BenchmarkSpecDefinitions.xlsx open", out.getvalue())

    def test_amd_pytorch_installs_numpy(self) -> None:
        text = (ROOT / "scripts/templates/setup_rocm_reboot_skeleton.sh").read_text(encoding="utf-8")
        self.assertIn('"${torch_packages[@]}" "${TORCHAUDIO_INSTALL_SPEC}" numpy', text)


class CollectorOutputTests(unittest.TestCase):
    # These print on purpose: SDXL's runner tees stdout into the raw file that
    # parse_results.py reads, the NUMA collector's console is filtered into its transcript,
    # and hipmemcpy prints the unparsed tool output only when no rows were found.
    KEEP = ("sdxl-diffusers-amd", "sdxl-diffusers-nvidia", "numa-cache-collector", "hipmemcpy-bandwidth-amd")
    ECHO = re.compile(r'print\((?:text|buf\.getvalue\(\)|handle\.read\(\)), end=""\)|print\(csv_text\)')

    def test_collectors_do_not_echo_their_csv(self) -> None:
        offenders = []
        for path in sorted(COMPONENTS.glob("*/files/scripts/*.py")):
            component = path.relative_to(COMPONENTS).parts[0]
            if component in self.KEEP:
                continue
            if self.ECHO.search(path.read_text(encoding="utf-8")):
                offenders.append(str(path.relative_to(COMPONENTS)))
        self.assertEqual(offenders, [])

    def test_hipmemcpy_echo_is_only_the_no_rows_fallback(self) -> None:
        text = (COMPONENTS / "hipmemcpy-bandwidth-amd/files/scripts/collect_workload.py").read_text(encoding="utf-8")
        self.assertEqual(len(self.ECHO.findall(text)), 1)
        self.assertIn("    if not rows:\n        Path(args.raw_file).write_text(text", text)

    def test_hipmemcpy_raw_file_holds_each_row_once(self) -> None:
        text = (COMPONENTS / "hipmemcpy-bandwidth-amd/files/scripts/collect_workload.py").read_text(encoding="utf-8")
        self.assertNotIn('write_text(text + "\\n" + csv_text', text)
        self.assertIn('"\\n".join(tool_log)', text)

    def test_nvidia_collectors_write_one_row(self) -> None:
        for component in ("gups-nvidia", "sdc-ecc-nvidia"):
            text = (COMPONENTS / component / "files/scripts/collect_workload.py").read_text(encoding="utf-8")
            self.assertNotIn('writer.writerow({"sample_index": 1, **row})', text, component)


class ServerStopTests(unittest.TestCase):
    RUNNERS = [f"{name}-{vendor}" for name in ("sglang-prompt-response", "sglang-serving", "vllm-throughput",
                                              "vllm-kvcache", "vllm-token-generation") for vendor in ("amd", "nvidia")]

    def test_server_stops_before_the_inventory(self) -> None:
        for component in self.RUNNERS:
            text = (COMPONENTS / component / "files/run_benchmark.sh").read_text(encoding="utf-8")
            stop = text.index("\nrecord_benchmark_stop\n")
            early = text.index("\ncleanup_server\n", stop)
            self.assertLess(early, text.index("collect_hw_sw_info.sh", stop), component)
            self.assertIn("trap cleanup_server EXIT", text, component)  # still covers a failed run


if __name__ == "__main__":
    unittest.main()
