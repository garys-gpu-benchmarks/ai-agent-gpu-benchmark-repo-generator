#!/usr/bin/env python3
# File: tests/test_template_00_131_changes.py
# Description: TEMPLATE_00_131 checks: the remote preflight download probes time
# a real download (URL-encoded wheel path from href, 2xx and at least 1 MiB) and
# report a failed probe as not measured; the NVIDIA workbook rows name the GPU
# the 00_130 batches were validated on; inventory command 204 is a valid
# nvidia-smi query; the collector does not record SIGPIPE (exit 141) from
# "| head" as a failure; and the SDXL runners prefetch before the clock starts.
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import remote_host_preflight as rhp  # noqa: E402

INDEX = (
    '<a href="/whl/cu130/torch-2.13.0%2Bcu130-cp312-cp312-manylinux_2_28_x86_64.whl#sha256=ab">'
    "torch-2.13.0+cu130-cp312-cp312-manylinux_2_28_x86_64.whl</a><br/>\n"
)

FAKE_CURL = r'''#!/usr/bin/env bash
url="${@: -1}"
printf '%s\n' "$url" >> "$FAKE_LOG"
case "$*" in *" -w "*) ;; *) printf '%s' "$FAKE_INDEX"; exit 0 ;; esac
case "$url" in
  *huggingface.co*) echo "$FAKE_HF" ;;
  *+*) echo "403 243 3100.0" ;;
  *%2B*) echo "$FAKE_PT" ;;
  *) echo "404 0 0.0" ;;
esac
'''


@unittest.skipIf(shutil.which("bash") is None, "bash is not installed")
class PreflightDownloadProbeTests(unittest.TestCase):
    def run_probe(self, hf: str, pt: str, index: str = INDEX) -> tuple[dict[str, str], list[str]]:
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "curl"
            fake.write_text(FAKE_CURL, encoding="utf-8")
            fake.chmod(0o755)
            log = Path(tmp) / "urls.txt"
            env = dict(os.environ, PATH=f"{tmp}:{os.environ.get('PATH', '')}", HOME=tmp,
                       FAKE_LOG=str(log), FAKE_INDEX=index, FAKE_HF=hf, FAKE_PT=pt)
            out = subprocess.run(["bash", "-c", rhp.PROBE_SCRIPT], capture_output=True, text=True,
                                 env=env, timeout=120).stdout
            urls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        return rhp.parse_probe(out), urls

    def test_probe_downloads_the_url_encoded_wheel(self) -> None:
        values, urls = self.run_probe("206 104857600 150000000.0", "206 104857600 41000000.0")
        self.assertEqual(values["download_pytorch_url"],
                         "https://download.pytorch.org/whl/cu130/torch-2.13.0%2Bcu130-cp312-cp312-manylinux_2_28_x86_64.whl")
        self.assertFalse(any("+" in u for u in urls), urls)
        self.assertEqual((values["download_pytorch_http"], values["download_pytorch_bps"]), ("206", "41000000.0"))
        self.assertEqual(values["download_huggingface_bps"], "150000000.0")
        warnings, _ = rhp.evaluate(values, ["101"], {}, 0.5)
        self.assertFalse([w for w in warnings if "Download" in w], warnings)

    def test_error_page_is_not_a_speed(self) -> None:
        values, _ = self.run_probe("206 104857600 150000000.0", "403 243 3100.0")
        self.assertEqual(values["download_pytorch_bps"], "0")
        warnings, _ = rhp.evaluate(values, ["101"], {}, 0.5)
        self.assertIn("Download speed from download.pytorch.org could not be measured (HTTP 403, 243 bytes); "
                      "the batch estimate ignores it.", warnings)
        estimate = rhp.estimate_minutes(values, [str(w) for w in range(101, 133)], 0.5)
        self.assertLessEqual(estimate["download_factor"], 1.0)

    def test_tiny_success_and_no_network_are_not_speeds(self) -> None:
        values, _ = self.run_probe("206 4096 3000.0", "000 0 0.0")
        self.assertEqual(values["download_huggingface_bps"], "0")
        self.assertEqual(values["download_pytorch_http"], "000")
        self.assertEqual(rhp.estimate_minutes(values, ["101"], 0.5)["download_factor"], 2.0)

    def test_missing_index_entry_skips_the_wheel_probe(self) -> None:
        values, urls = self.run_probe("206 104857600 150000000.0", "206 104857600 41000000.0", index="<html></html>")
        self.assertEqual((values["download_pytorch_url"], values["download_pytorch_http"], values["download_pytorch_bps"]),
                         ("none", "none", "0"))
        self.assertEqual(len([u for u in urls if "download.pytorch.org" in u]), 1)


class NvidiaGpuModelTests(unittest.TestCase):
    def test_nvidia_rows_name_h100_and_never_flag_an_h100_host(self) -> None:
        from openpyxl import load_workbook

        from metric_contract import gpu_model_note
        from readme_sections import requirements

        ws = load_workbook(ROOT / "BenchmarkSpecDefinitions.xlsx", read_only=True, data_only=True)["Workload_Definitions"]
        rows = ws.iter_rows(values_only=True)
        header = list(next(rows))
        col = header.index("GPU Model")
        model = {r[0]: r[col] for r in rows if isinstance(r[0], int)}
        for wl in list(range(201, 233)) + list(range(401, 433)):
            self.assertEqual(model[wl], "H100", wl)
        for wl in list(range(101, 133)) + list(range(301, 333)):
            self.assertEqual(model[wl], "MI300X", wl)
        for detected in ("NVIDIA H100 NVL", "NVIDIA H100 80GB HBM3", "NVIDIA H100 PCIe"):
            self.assertEqual(gpu_model_note(detected, "H100"), "", detected)
        fields = {"GPU Vendor": "NVIDIA", "Execution Domain": "GPU Compute / CUDA", "OS Version": "Ubuntu 24.04",
                  "GPU Runtime Version": "CUDA 12.8 (setup installs it unless ...)", "GPU Model": "H100", "Framework": "Bash"}
        self.assertIn("NVIDIA GPU with CUDA 12.8 (validated on H100)", requirements(fields))


INVENTORY_CMD_204 = "nvidia-smi -q | grep -E 'Driver Version|CUDA Version'"

FAKE_NVIDIA_SMI = r"""#!/usr/bin/env bash
[[ -n "$FAKE_FAIL" ]] && { echo "NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver."; exit 9; }
[[ "$1" == "-q" ]] || { echo "Option $1 is not recognized."; exit 255; }
printf 'Driver Version : 595.91.07\nCUDA Version : 13.0\n'
for i in $(seq 1 4000); do echo "    Field $i : value"; done
"""


def run_one_source() -> str:
    lines = (ROOT / "scripts/collect_hw_sw_info.sh").read_text(encoding="utf-8").splitlines()
    start = lines.index("run_one() {")
    end = next(i for i in range(start, len(lines)) if lines[i] == "}")
    return "\n".join(lines[start : end + 1]) + "\n"


class InventoryCollectorTests(unittest.TestCase):
    def test_command_204_is_a_valid_query(self) -> None:
        import base64

        from openpyxl import load_workbook

        rows = list(load_workbook(ROOT / "config/hw_sw_info_commands.xlsx", read_only=True)["Sheet2"].iter_rows(values_only=True))
        by_seq = {str(r[0]): r for r in rows[1:] if r and r[0] is not None}
        self.assertEqual(by_seq["204"][3], INVENTORY_CMD_204)
        self.assertEqual(by_seq["204"][1], "nVidia-only")
        self.assertFalse([r[0] for r in rows[1:] if r and str(r[3] or "").rstrip().endswith(" -")])
        collector = (ROOT / "scripts/collect_hw_sw_info.sh").read_text(encoding="utf-8")
        line = next(ln for ln in collector.splitlines() if ln.startswith("204\t"))
        self.assertEqual(base64.b64decode(line.split("\t")[3]).decode(), INVENTORY_CMD_204)

    @unittest.skipIf(shutil.which("bash") is None, "bash is not installed")
    def test_sigpipe_is_success_and_real_failures_still_fail(self) -> None:
        cases = (
            ("seq 1 3000000 | head -19", None, "STATUS      : SUCCESS"),
            ("false | head -1", None, "STATUS      : FAILED (exit code 1)"),
            ("no_such_command_00_131", None, "STATUS      : FAILED (exit code 127)"),
            ("nvidia-smi -", None, "STATUS      : FAILED (exit code 255)"),
            (INVENTORY_CMD_204, None, "STATUS      : SUCCESS"),
            (INVENTORY_CMD_204, "1", "STATUS      : FAILED"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            fn = Path(tmp) / "run_one.sh"
            fn.write_text(run_one_source(), encoding="utf-8")
            fake = Path(tmp) / "nvidia-smi"
            fake.write_text(FAKE_NVIDIA_SMI, encoding="utf-8")
            fake.chmod(0o755)
            for cmd, fail, expected in cases:
                out = Path(tmp) / "out.txt"
                out.write_text("", encoding="utf-8")
                env = dict(os.environ, PATH=f"{tmp}:{os.environ.get('PATH', '')}")
                if fail:
                    env["FAKE_FAIL"] = fail
                subprocess.run(["bash", "-c", f'source "{fn}"; run_one hardware "$1" test "{out}"', "_", cmd],
                               env=env, capture_output=True, text=True, timeout=60)
                text = out.read_text(encoding="utf-8")
                self.assertIn(expected, text, (cmd, text[:400]))
                if cmd == INVENTORY_CMD_204 and not fail:
                    self.assertIn("Driver Version : 595.91.07", text)
                    self.assertIn("CUDA Version : 13.0", text)

    def test_generator_template_carries_the_sigpipe_rule(self) -> None:
        template = (ROOT / "scripts/generate_collect_hw_sw_info.sh").read_text(encoding="utf-8")
        self.assertIn("[[ $rc -eq 141 ]] && rc=0", template)
        self.assertIn("[[ $rc -eq 141 ]] && rc=0", run_one_source())


class SdxlPrefetchBeforeClockTests(unittest.TestCase):
    PREFETCH = "bash scripts/install_sdxl_python.sh --prefetch"

    def test_prefetch_runs_before_the_last_clock_start(self) -> None:
        for vendor in ("amd", "nvidia"):
            lines = (ROOT / f"implementation_components/sdxl-diffusers-{vendor}/files/run_benchmark.sh").read_text(
                encoding="utf-8").splitlines()
            code = [ln.strip() for ln in lines]
            prefetch = [i for i, ln in enumerate(code) if ln == self.PREFETCH]
            marks = [i for i, ln in enumerate(code) if ln == "mark_benchmark_measure_start"]
            offline = [i for i, ln in enumerate(code) if ln == "export HF_HUB_OFFLINE=1"]
            collection = code.index("run_collection() {")
            run_dir = next(i for i, ln in enumerate(code) if ln.startswith("RUN_DIR="))
            self.assertEqual(len(prefetch), 1, vendor)
            self.assertEqual(len(offline), 1, vendor)
            self.assertLess(prefetch[0], marks[-1], vendor)
            self.assertLess(offline[0], marks[-1], vendor)
            self.assertLess(marks[-1], run_dir, vendor)
            self.assertLess(marks[-1], collection, vendor)
            body_end = next(i for i in range(collection, len(code)) if code[i] == "}")
            body = code[collection:body_end]
            self.assertNotIn(self.PREFETCH, body, vendor)
            self.assertIn(f'echo "{self.PREFETCH}" >> "${{COMMAND_LOG}}"', body, vendor)

    def test_docs_describe_the_new_order(self) -> None:
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("before its last `mark_benchmark_measure_start`", agents)
        self.assertNotIn("Current behavior, not a requirement: `mark_benchmark_measure_start` runs before the prefetch", agents)


if __name__ == "__main__":
    unittest.main()
