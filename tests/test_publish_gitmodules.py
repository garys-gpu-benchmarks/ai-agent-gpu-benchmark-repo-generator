#!/usr/bin/env python3
# File: tests/test_publish_gitmodules.py
# Description: v1.0.17's bundle-nvidia-ubuntu-2604 was published with a .gitmodules
#   entry for 417 that had a path but no url (Windows refused one write during
#   "git submodule add"), so "git clone --recurse-submodules" stopped with
#   "No url found for submodule path". Step 7 now restores a missing url and
#   requires one complete entry per workload; add_submodule only counts an entry
#   with both lines as done; step 8 clones every bundle, not only AMD 24.04.
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "publish_benchmarks_to_github.sh"
BASH = shutil.which("bash")
GIT = shutil.which("git")

GITMODULES = """[submodule "416-x"]
\tpath = 416-x
\turl = ../416-x.git
[submodule "417-x"]
\tpath = 417-x
[submodule "418-x"]
\tpath = 418-x
\turl = ../418-x.git
"""


def repair_block(text: str) -> str:
    start = text.index("    # Every submodule needs a path and a url")
    end = text.index("\n", text.index("((complete == want)) || stop", start))
    return text[start:end]


@unittest.skipIf(BASH is None or GIT is None, "bash and git are required")
class PublishGitmodules(unittest.TestCase):
    def run_repair(self, want: int) -> tuple[subprocess.CompletedProcess[str], Path]:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / ".gitmodules").write_text(GITMODULES, encoding="utf-8")
        program = "\n".join([
            "set -u",
            'again() { "$@"; }',
            'stop() { echo "STOP: $*"; exit 3; }',
            f"bundle=bundle-test want={want}",
            repair_block(SCRIPT.read_text(encoding="utf-8")),
            'echo DONE',
        ])
        result = subprocess.run([BASH, "-c", program], cwd=tmp, capture_output=True, text=True, timeout=60)
        return result, tmp

    def test_missing_url_is_restored(self) -> None:
        result, tmp = self.run_repair(3)
        self.assertIn("restoring the missing url of 417-x", result.stdout, result.stderr)
        self.assertIn("DONE", result.stdout)
        url = subprocess.run([GIT, "config", "-f", ".gitmodules", "--get", "submodule.417-x.url"],
                             cwd=tmp, capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(url, "../417-x.git")

    def test_wrong_entry_count_stops(self) -> None:
        result, _ = self.run_repair(32)
        self.assertIn("STOP: bundle-test/.gitmodules has 3 complete submodule entries, expected 32", result.stdout)
        self.assertNotIn("DONE", result.stdout)

    def test_add_submodule_requires_the_url(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        body = text[text.index("add_submodule() {"):text.index("\n}\n", text.index("add_submodule() {"))]
        self.assertIn('--get "submodule.${path}.url"', body)

    def test_step8_clones_every_bundle(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        step8 = text[text.index("# STEP 8:"):text.index("# STEP 9:")]
        for name in ("amd-ubuntu-2404", "nvidia-ubuntu-2404", "amd-ubuntu-2604", "nvidia-ubuntu-2604"):
            self.assertIn(name, step8)
        self.assertIn('"https://github.com/${ORG}/${bundle}.git"', step8)


if __name__ == "__main__":
    unittest.main()
