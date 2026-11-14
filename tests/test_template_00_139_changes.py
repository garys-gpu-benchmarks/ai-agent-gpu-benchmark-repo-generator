"""TEMPLATE_00_139 checks.

  1. Batch waits: one wait per workload, on Successful time, [FAIL] or the next
     workload's [RECORD] <N> (never a later one), up to 30 minutes; plain sleeps
     stay at most 120 seconds.
  2. docs/OPEN_ISSUES.md is never published: git ignores it, prepare_github_publish.sh
     deletes it from a workload, and the operator publish script deletes it from every
     workload copy (step 4) and from the generator copy (step 9).
  3. No file the generator CI scans holds a literal private-key header or a live lab IP.
     tests/test_template_00_136_changes.py wrote the header literally and failed the
     published generator's CI on 2026-11-13 (v1.0.37).
  4. (Replaced in TEMPLATE_00_141: setup is measured on every run, see
     tests/test_template_00_141_timing.py. .setup_state_timed stays git-ignored for
     repositories that still have one.)
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ("docs/AI_AGENT_INSTRUCTIONS.md", ".cursor/rules/generate-workloads.mdc", "AGENTS.md")


class NextRecordWaitTests(unittest.TestCase):
    def test_wait_targets_the_next_record(self) -> None:
        for rel in FILES:
            with self.subTest(rel=rel):
                text = (ROOT / rel).read_text(encoding="utf-8")
                self.assertIn("wait once per workload", text)
                self.assertIn("`[RECORD] <N>`", text)
                self.assertIn("next workload not yet recorded (never a later one)", text)
                self.assertIn("30 minutes", text)
                self.assertIn("120 seconds", text)
                self.assertIn("Successful time", text)
                self.assertIn("[FAIL]", text)

    def test_old_wording_is_gone(self) -> None:
        for rel in FILES:
            with self.subTest(rel=rel):
                text = (ROOT / rel).read_text(encoding="utf-8")
                self.assertNotIn("a new `[RECORD]` line appears", text)
                self.assertNotIn("every wait must return as soon as", text)
                self.assertNotIn("every wait on it must return as soon as", text)


class OpenIssuesNotPublishedTests(unittest.TestCase):
    def test_gitignore_lists_it(self) -> None:
        lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("docs/OPEN_ISSUES.md", lines)

    def test_prepare_script_deletes_it(self) -> None:
        text = (ROOT / "scripts" / "prepare_github_publish.sh").read_text(encoding="utf-8")
        block = text[text.index("DOC_LEFTOVERS=("):]
        block = block[: block.index(")")]
        self.assertIn("  docs/OPEN_ISSUES.md\n", block)

    def test_publish_script_deletes_and_checks_it(self) -> None:
        text = (ROOT / "user_scripts" / "publish_benchmarks_to_github.sh").read_text(encoding="utf-8")
        self.assertNotIn("\r", text)
        step4 = text[text.index("# STEP 4:"):text.index("# STEP 5:")]
        self.assertIn('rm -f "${dir}/docs/OPEN_ISSUES.md"', step4)
        self.assertIn("-path '*/docs/OPEN_ISSUES.md'", step4)
        step9 = text[text.index("# STEP 9:"):text.index("# STEP 10:")]
        self.assertIn("rm -f docs/OPEN_ISSUES.md", step9)
        self.assertIn("-path ./docs/OPEN_ISSUES.md", step9)
        # The generator removal happens before the never-publish check and the commit.
        self.assertLess(step9.index("rm -f docs/OPEN_ISSUES.md"), step9.index("never-publish items"))
        self.assertLess(step9.index("never-publish items"), step9.index("commit_all"))


class CiSecretScanTests(unittest.TestCase):
    """Repeats the 'No leftover personal paths' scan in .github/workflows/ci.yml."""

    def test_no_file_matches_the_ci_secret_scan(self) -> None:
        import re

        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("OPENSSH PRIVATE KEY", ci)
        patterns = ["-----BEGIN " + "OPENSSH PRIVATE KEY-----", "129" + ".212.180.31", "205" + ".196.17.122"]
        for p in patterns:
            self.assertIn(re.sub(r"\.", r"\\\\.", p), ci)  # the scan still lists it
        hits = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if path.suffix not in {".md", ".sh", ".py", ".txt", ".yml"}:
                continue
            if path.name in {"ci.yml", "prompt_workflow.py"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            hits += [f"{path.relative_to(ROOT)}: {p}" for p in patterns if p in text]
        self.assertEqual(hits, [])


class SetupMarkerTests(unittest.TestCase):
    def test_marker_is_ignored_by_git(self) -> None:
        lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn(".setup_state", lines)
        self.assertIn(".setup_state_timed", lines)


if __name__ == "__main__":
    unittest.main()
