"""DistilBERT training (125, 225, 325, 425) and ResNet-50 training AMD (121, 321).

  1. DistilBERT: no "Loading weights" bar and no LOAD REPORT table. The table listed
     the pretraining head (vocab_*) as UNEXPECTED and the new classification head
     (pre_classifier, classifier) as MISSING, both expected when fine-tuning from
     distilbert-base-uncased. Missing body weights still print one [WARN] line; the
     classifier head is never reported.
  2. Both AMD collectors wrote two hand-built rows with a fixed loss of 1.0. They
     now write one row with the last timed step's real loss, and no longer print
     the CSV.
"""
from __future__ import annotations

import importlib.util
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "implementation_components"
DISTILBERT = (COMPONENTS / "distilbert-amd/files/scripts/collect_workload.py",
              COMPONENTS / "distilbert-nvidia/files/scripts/gpu-bench-distilbert-sst2-train.py")
RESNET = COMPONENTS / "resnet50-training-amd/files/scripts/collect_workload.py"


def load(path: Path):
    spec = importlib.util.spec_from_file_location(f"t_{path.parent.parent.parent.name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DistilBertQuietLoadTests(unittest.TestCase):
    def test_quiet_settings_come_before_transformers_import(self) -> None:
        for path in DISTILBERT:
            text = path.read_text(encoding="utf-8")
            for setting in ('"HF_HUB_DISABLE_PROGRESS_BARS", "1"', '"TRANSFORMERS_VERBOSITY", "error"'):
                self.assertLess(text.index(setting), text.index("from transformers import"), path)
            self.assertIn("output_loading_info=True", text, path)

    def test_only_body_weights_warn(self) -> None:
        module = load(DISTILBERT[0])
        out = io.StringIO()
        with redirect_stdout(out):
            module.warn_missing_weights("m", {"missing_keys": {"classifier.weight", "pre_classifier.bias"}})
        self.assertEqual(out.getvalue(), "")
        with redirect_stdout(out):
            module.warn_missing_weights("m", {"missing_keys": {"classifier.weight", "distilbert.transformer.layer.0.x"}})
        self.assertIn("[WARN] m: 1 model weights missing", out.getvalue())
        self.assertIn("distilbert.transformer.layer.0.x", out.getvalue())

    def test_one_row_with_real_loss(self) -> None:
        for path in (DISTILBERT[0], RESNET):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn('"loss": 1.0', text, path)
            self.assertIn('"loss": final_loss', text, path)
            self.assertEqual(text.count('{"step": '), 1, path)
            self.assertNotIn('print(text, end="")', text, path)


if __name__ == "__main__":
    unittest.main()
