"""SDXL (124, 224, 324, 424): short console output.

  1. install_sdxl_python.sh skips pip when diffusers, transformers, accelerate,
     safetensors and huggingface_hub are installed (pip printed ~55 "Requirement
     already satisfied" lines on every run) and runs pip --quiet otherwise.
  2. infer_sdxl.py turns off library noise before importing the libraries:
     progress bars, transformers and diffusers warnings, diffusers FutureWarnings,
     and the diffusers "Loading pipeline components" bar.
  3. run_benchmark.sh keeps the whole transcript in the raw file (parse_results.py
     reads it) and shows only tagged lines and the sdxl summary on the console; on
     failure it prints the end of the raw file and dies.
"""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDORS = ("amd", "nvidia")


def files(vendor: str) -> Path:
    return ROOT / "implementation_components" / f"sdxl-diffusers-{vendor}" / "files"


class SdxlQuietOutputTests(unittest.TestCase):
    def test_pip_skipped_when_installed(self) -> None:
        for vendor in VENDORS:
            text = (files(vendor) / "scripts/install_sdxl_python.sh").read_text(encoding="utf-8")
            self.assertIn("importlib.util.find_spec", text)
            self.assertIn("[PASS] SDXL Python packages already installed", text)
            self.assertIn("pip install --quiet --disable-pip-version-check", text)

    def test_library_noise_off_before_imports(self) -> None:
        for vendor in VENDORS:
            text = (files(vendor) / "scripts/infer_sdxl.py").read_text(encoding="utf-8")
            first_import = text.index("import torch\n")
            for setting in ('"HF_HUB_DISABLE_PROGRESS_BARS", "1"', '"TRANSFORMERS_VERBOSITY", "error"',
                            '"DIFFUSERS_VERBOSITY", "error"'):
                self.assertLess(text.index(setting), first_import, (vendor, setting))
            # After the imports (ruff E402), but before diffusers is imported in a function.
            self.assertLess(text.index('filterwarnings("ignore", category=FutureWarning)'),
                            text.index("from diffusers import"), vendor)
            self.assertIn("diffusers_logging.disable_progress_bar()", text)

    def test_console_filter(self) -> None:
        sample = "\n".join([
            "# SDXL backend=sdxl", "[INFO] SDXL load source: /cache", "# CSV", "sample_index,status",
            "0,ok", "sdxl per_image_latency_sec=0.1 images_per_sec=7 peak_vram_gb=8",
            "RESULT model_name=sdxl-base-1.0 status=ok", "[WARN] something",
        ]) + "\n"
        for vendor in VENDORS:
            text = (files(vendor) / "run_benchmark.sh").read_text(encoding="utf-8")
            start = text.index("sdxl_console_lines() {")
            function = text[start:text.index("\n}", start) + 2]
            shown = subprocess.run(["bash", "-c", function + "\nsdxl_console_lines"], input=sample,
                                   capture_output=True, text=True, check=True).stdout.splitlines()
            self.assertEqual(shown, ["[INFO] SDXL load source: /cache",
                                     "sdxl per_image_latency_sec=0.1 images_per_sec=7 peak_vram_gb=8",
                                     "[WARN] something"], vendor)
            self.assertIn('| tee "${RAW_FILE}" | sdxl_console_lines; then', text)
            self.assertIn('tail -n 40 "${RAW_FILE}"', text)


if __name__ == "__main__":
    unittest.main()
