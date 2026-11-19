"""TEMPLATE_00_140 checks, updated in TEMPLATE_00_147.

  TEMPLATE_00_140 made every agent-facing generation doc name the operator tools'
  location, because batch reviews reported the copies in the folder above the
  project root as files outside it. TEMPLATE_00_147 stopped that copy (OPEN_ISSUES
  A8): the docs now say generation writes nothing above the project root and still
  name the three tools, so a review does not report or delete copies that an
  earlier template left there.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import create_generated_repo  # noqa: E402

FILES = (
    "docs/AI_AGENT_INSTRUCTIONS.md",
    ".cursor/rules/generate-workloads.mdc",
    "AGENTS.md",
    "docs/generation-workflow.md",
)
TOOLS = ("get_benchmark_results.sh", "list_runs.sh", "show_metrics.sh")


class OperatorToolsLocationDocTests(unittest.TestCase):
    def test_agent_docs_name_the_location(self) -> None:
        for rel in FILES:
            with self.subTest(rel=rel):
                text = (ROOT / rel).read_text(encoding="utf-8")
                self.assertIn("Generation writes nothing above the project root", text)
                for tool in TOOLS:
                    self.assertIn(f"`{tool}`", text)
                self.assertIn("do not report them, and do not delete them for the user", text)
                self.assertNotIn("in the folder above the project root", text)

    def test_readme_no_longer_describes_the_copy_above(self) -> None:
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("copied one level above the workspace", text)

    def test_code_no_longer_installs_into_the_parent(self) -> None:
        self.assertFalse(hasattr(create_generated_repo, "install_operator_tools"))
        self.assertFalse(hasattr(create_generated_repo, "OPERATOR_TOOLS"))


if __name__ == "__main__":
    unittest.main()
