"""RAG FAISS end-to-end (132, 232, 332, 432): short console output.

  1. The Mistral load used torch_dtype=, which transformers 4.56+ reports as
     "`torch_dtype` is deprecated! Use `dtype` instead!". It now passes dtype= on
     4.56+ and torch_dtype= on older releases (setup.sh installs transformers unpinned).
  2. Progress bars (Loading weights, Fetching N files, datasets Generating split) and
     library warnings are off; the settings come before the library imports.
  3. The 27-line JSON summary is no longer printed; it stays in raw_output.txt.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = [ROOT / f"implementation_components/rag-faiss-end2end-{v}/files/scripts/gpu-bench-rag-faiss-end2end.py"
           for v in ("amd", "nvidia")]


def dtype_kwarg_for(path: Path, version: str) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    func = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_dtype_kwarg")
    namespace: dict = {"transformers": type("T", (), {"__version__": version})}
    exec(compile(ast.Module(body=[func], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["_dtype_kwarg"]()


class RagQuietOutputTests(unittest.TestCase):
    def test_dtype_argument_by_version(self) -> None:
        for path in SCRIPTS:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("torch_dtype=torch.bfloat16", text, path)
            self.assertIn("**{_dtype_kwarg(): torch.bfloat16}", text, path)
            self.assertEqual(dtype_kwarg_for(path, "5.23.0"), "dtype")
            self.assertEqual(dtype_kwarg_for(path, "4.56.0"), "dtype")
            self.assertEqual(dtype_kwarg_for(path, "4.55.4"), "torch_dtype")
            self.assertEqual(dtype_kwarg_for(path, "4.57.0.dev0"), "dtype")

    def test_quiet_settings_before_imports(self) -> None:
        for path in SCRIPTS:
            text = path.read_text(encoding="utf-8")
            first = text.index("import torch\n")
            for setting in ('"HF_HUB_DISABLE_PROGRESS_BARS", "1"', '"HF_DATASETS_DISABLE_PROGRESS_BARS", "1"',
                            '"TRANSFORMERS_VERBOSITY", "error"', '"HF_HUB_VERBOSITY", "error"'):
                self.assertLess(text.index(setting), first, (path, setting))

    def test_summary_not_dumped(self) -> None:
        for path in SCRIPTS:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("json.dumps(summary, indent=2)", text, path)
            self.assertIn('"SUMMARY " + json.dumps(summary)', text, path)


if __name__ == "__main__":
    unittest.main()
