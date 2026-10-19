#!/usr/bin/env python3
# File: tests/test_generation_checks.py
# Description: scripts/verify_generation_workflow.py and
#   scripts/generate_workload_parameters.py. Fixed 2026-10-18: template README
#   links resolve in the generated-repo layout; an unused Parameter_NN slot
#   ("-") is not a parameter; the workbook is read once (was over two
#   minutes); --check compares the stored catalog with the workbook.
from __future__ import annotations

import contextlib
import io
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_workload_parameters as gwp  # noqa: E402
import verify_generation_workflow as vgw  # noqa: E402


class LinkResolutionTests(unittest.TestCase):
    def test_template_links_resolve_in_generated_repo_layout(self) -> None:
        template = ROOT / "templates" / "README_TEMPLATE.md"
        for target in ("LICENSE", ".github/workflows/ci.yml", ".github/workflows/gpu-smoke.yml"):
            with self.subTest(target=target):
                self.assertTrue(vgw.link_resolves(template, target))

    def test_missing_targets_still_fail(self) -> None:
        self.assertFalse(vgw.link_resolves(ROOT / "templates" / "README_TEMPLATE.md", "no-such-file.md"))
        # The generated-repo layout applies only to templates/*_TEMPLATE.md.
        self.assertFalse(vgw.link_resolves(ROOT / "docs" / "ARCHITECTURE.md", "LICENSE"))


class ParameterCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        start = time.time()
        with contextlib.redirect_stderr(io.StringIO()):
            cls.catalog = gwp.build_catalog()
        cls.seconds = time.time() - start

    def test_empty_slots_are_not_parameters(self) -> None:
        for value in (None, "", "-", "—", "–", " - "):
            self.assertTrue(gwp._is_empty_slot(value), repr(value))
        self.assertFalse(gwp._is_empty_slot("num_gpus"))
        for name in ("-", "—", "–", ""):
            self.assertNotIn(name, self.catalog["parameters"])

    def test_catalog_builds_quickly(self) -> None:
        self.assertLess(self.seconds, 30, "the workbook is being read cell by cell again")

    def test_stored_catalog_matches_workbook(self) -> None:
        import yaml

        stored = yaml.safe_load(gwp.OUTPUT.read_text(encoding="utf-8"))
        self.assertEqual(stored, self.catalog, "run python3 scripts/generate_workload_parameters.py")

    def test_undocumented_parameters_warn_unless_strict(self) -> None:
        from openpyxl import load_workbook

        sheet = gwp._active_sheet(load_workbook(gwp.WORKBOOK, read_only=True))
        missing = gwp.undocumented_parameters(sheet)
        self.assertFalse(any(item.endswith(":-") for item in missing))
        if missing:
            with contextlib.redirect_stderr(io.StringIO()) as err:
                gwp.validate_active_parameters(sheet)
            self.assertIn("[WARN]", err.getvalue())
            with self.assertRaises(SystemExit):
                gwp.validate_active_parameters(sheet, strict=True)


class VerifyGenerationWorkflowTests(unittest.TestCase):
    def test_workflow_check_passes(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(vgw.main(), 0)
        self.assertIn("[PASS]", out.getvalue())


if __name__ == "__main__":
    unittest.main()
