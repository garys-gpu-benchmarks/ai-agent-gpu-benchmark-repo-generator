"""TEMPLATE_00_140 checks.

  1. Every agent-facing generation doc says that generation installs the operator
     tools (get_benchmark_results.sh, list_runs.sh, show_metrics.sh) in the folder
     above the project root, and that they are expected output, not scratch. The
     TEMPLATE_00_136 and 00_139 batch reviews reported them as files outside the
     project root because only README.md described the location.
  2. The code still installs them there (project_root.parent), so the docs and
     install_operator_tools agree.
"""
from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from create_generated_repo import OPERATOR_TOOLS, install_operator_tools  # noqa: E402

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
                self.assertIn("Generation also installs the operator tools", text)
                for tool in TOOLS:
                    self.assertIn(f"`{tool}`", text)
                self.assertIn("in the folder above the project root", text)
                self.assertIn("They are expected output, not scratch", text)

    def test_readme_still_describes_it(self) -> None:
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("copied one level above the workspace", text)

    def test_code_installs_into_the_parent(self) -> None:
        self.assertEqual(sorted(Path(rel).name for rel in OPERATOR_TOOLS), sorted(TOOLS))
        self.assertIn("target_dir = project_root.parent", inspect.getsource(install_operator_tools))


if __name__ == "__main__":
    unittest.main()
