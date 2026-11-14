"""BERT inference (123, 223, 323, 423): quiet model load.

bert-base-uncased carries pretraining heads (cls.predictions.*, cls.seq_relationship.*)
that BertModel does not use. transformers printed a "Loading weights" progress bar and
a LOAD REPORT table marking them UNEXPECTED on every run. Both are off now; the
progress-bar and verbosity settings are read at import, so they are set before
transformers is imported. Missing encoder weights (randomly initialized) still print
one [WARN] line, from output_loading_info. The AMD collector no longer prints its CSV.
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AMD = ROOT / "implementation_components/bert-inference-amd/files/scripts/collect_workload.py"
NVIDIA = ROOT / "implementation_components/bert-inference-nvidia/files/scripts/gpu-bench-bert-transformers-inference.py"


class BertQuietLoadTests(unittest.TestCase):
    def test_quiet_settings_come_before_transformers_import(self) -> None:
        for path in (AMD, NVIDIA):
            text = path.read_text(encoding="utf-8")
            for setting in ('"HF_HUB_DISABLE_PROGRESS_BARS", "1"', '"TRANSFORMERS_VERBOSITY", "error"'):
                self.assertIn(setting, text, path)
                self.assertLess(text.index(setting), text.index("from transformers import"), path)

    def test_missing_weights_still_warn(self) -> None:
        for path in (AMD, NVIDIA):
            text = path.read_text(encoding="utf-8")
            self.assertIn("output_loading_info=True", text, path)
            self.assertIn('loading.get("missing_keys")', text, path)
            self.assertIn("[WARN]", text, path)

    def test_amd_collector_does_not_print_csv(self) -> None:
        self.assertNotIn('print(text, end="")', AMD.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
