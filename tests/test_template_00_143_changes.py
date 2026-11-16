#!/usr/bin/env python3
"""TEMPLATE_00_143: generated repositories do not include setup.sh.

Nothing calls the compatibility wrapper. run_benchmark.sh goes through
scripts/ensure_setup.sh to run_setup.sh, the ROCm resume unit runs
run_setup.sh, and the suite never calls setup.sh.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD_NAME = re.compile(r"(?<![A-Za-z0-9_\-])setup\.sh(?![A-Za-z0-9_])")


def _fields(spec: Path) -> dict[str, str]:
    data = json.loads(spec.read_text(encoding="utf-8"))
    return {
        str(item.get("field_name", "")): str(item.get("value", ""))
        for item in data
        if isinstance(item, dict)
    }


class GeneratedRepoSetupNameTests(unittest.TestCase):
    def test_generated_repo_has_run_setup_and_docs_omit_setup_sh(self) -> None:
        spec_in_template = ROOT / "benchmark_specification.json"
        self.assertFalse(
            spec_in_template.exists(),
            "refusing to overwrite benchmark_specification.json in the generator root",
        )
        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / "benchmark_specification.json"
            extracted = subprocess.run(
                [
                    sys.executable,
                    "scripts/extract_benchmark_definition.py",
                    "--workload",
                    "101",
                    "--output",
                    str(spec),
                    "--quiet",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(extracted.returncode, 0, extracted.stderr or extracted.stdout)
            repo_name = _fields(spec)["Repo Base Name"]
            repo = Path(tmp) / f"101-{repo_name}"
            spec_in_template.write_bytes(spec.read_bytes())
            try:
                init = subprocess.run(
                    [
                        sys.executable,
                        "scripts/init_generated_repo.py",
                        "--repo-name",
                        repo_name,
                        "--template-root",
                        str(ROOT),
                        "--repo-root",
                        str(repo),
                        "--force",
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                self.assertEqual(init.returncode, 0, init.stdout + init.stderr)
                filled = subprocess.run(
                    [
                        sys.executable,
                        "scripts/fill_generated_docs.py",
                        "--repo-root",
                        str(repo),
                        "--template-root",
                        str(ROOT),
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                self.assertEqual(filled.returncode, 0, filled.stdout + filled.stderr)
            finally:
                spec_in_template.unlink(missing_ok=True)

            self.assertTrue((repo / "run_setup.sh").is_file())
            self.assertFalse((repo / "setup.sh").exists())
            self.assertEqual([p.relative_to(repo).as_posix() for p in repo.rglob("setup.sh")], [])
            for rel in ("README.md", "SPEC.md"):
                text = (repo / rel).read_text(encoding="utf-8")
                hits = [
                    f"{rel}:{number}: {line.strip()[:120]}"
                    for number, line in enumerate(text.splitlines(), start=1)
                    if OLD_NAME.search(line)
                ]
                self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
