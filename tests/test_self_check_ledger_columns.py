#!/usr/bin/env python3
# File: tests/test_self_check_ledger_columns.py
# Description: scripts/self_check_generated_repo.sh checks LEDGER_COLUMNS in
#   scripts/update_runtime_ledger.py against its own expected list. When the
#   ledger gained metrics_na_count, result_status and gpu_model_note
#   (2026-10-17) the list was not updated, and every generated workload failed
#   its self-check. This runs that embedded check against the real module.
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF_CHECK = ROOT / "scripts" / "self_check_generated_repo.sh"


def ledger_check_program() -> str:
    text = SELF_CHECK.read_text(encoding="utf-8")
    blocks = re.findall(r"<<'PY'\n(.*?)\nPY\n", text, re.S)
    matches = [b for b in blocks if "LEDGER_COLUMNS order is incorrect" in b]
    if len(matches) != 1:
        raise AssertionError(f"expected one ledger-column check in the self-check, found {len(matches)}")
    return matches[0]


class SelfCheckLedgerColumnsTests(unittest.TestCase):
    def test_embedded_check_passes_against_the_real_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp) / "scripts"
            scripts.mkdir()
            source = (ROOT / "scripts" / "update_runtime_ledger.py").read_text(encoding="utf-8")
            (scripts / "update_runtime_ledger.py").write_text(source, encoding="utf-8")
            for helper in ("metric_contract.py", "text_io.py"):
                if (ROOT / "scripts" / helper).exists():
                    (scripts / helper).write_text((ROOT / "scripts" / helper).read_text(encoding="utf-8"), encoding="utf-8")
            result = subprocess.run([sys.executable, "-"], input=ledger_check_program(), cwd=tmp,
                                    capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("[FAIL]", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
