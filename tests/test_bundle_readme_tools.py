#!/usr/bin/env python3
# File: tests/test_bundle_readme_tools.py
# Description: The bundle README (bundle_readme() in the publish scripts) must
#   tell the technician about every script the bundle ships, so none of them
#   sits unexplained in /opt/benchmarks. Renders the README with the real
#   function, for every platform, and checks it.
from __future__ import annotations

import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLISH = [ROOT / "scripts" / "publish_benchmarks_to_github.sh",
           ROOT / "scripts" / "publish_benchmarks_to_github_manual.sh"]
BASH = shutil.which("bash")


def function_source(text: str, name: str) -> str:
    start = text.index(f"\n{name}() {{\n") + 1
    end = text.index("\n}\n", start) + 3
    return text[start:end]


def shipped_scripts(text: str) -> set[str]:
    """Scripts step 7 writes into the bundle: tr -d '\\r' <SRC >NAME.sh"""
    step7 = text[text.index("# STEP 7: BUILD"):text.index("# STEP 8:")]
    return set(re.findall(r"tr -d '\\r' <\"\$\{\w+\}\" >(\w+\.sh)", step7))


@unittest.skipIf(BASH is None, "bash is not installed")
class BundleReadmeToolsTests(unittest.TestCase):
    def render(self, script: Path, digit: str) -> str:
        text = script.read_text(encoding="utf-8")
        program = "\n".join([
            "set -u",
            'platform() { echo "Platform $1"; }',
            "ORG=example-org VERSION=v9.9.9",
            function_source(text, "bundle_readme"),
            f'bundle_readme {digit} bundle-test 32 "- **{digit}01** - row"',
        ])
        result = subprocess.run([BASH, "-c", program], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_ships_the_expected_scripts(self) -> None:
        for script in PUBLISH:
            with self.subTest(script=script.name):
                self.assertEqual(shipped_scripts(script.read_text(encoding="utf-8")),
                                 {"run_benchmark_suite.sh", "show_metrics.sh"})

    def test_readme_explains_every_shipped_script(self) -> None:
        for script in PUBLISH:
            shipped = shipped_scripts(script.read_text(encoding="utf-8"))
            for digit in "1234":
                readme = self.render(script, digit)
                with self.subTest(script=script.name, platform=digit):
                    for name in shipped:
                        self.assertIn(f"./{name} ", readme, f"{name} is shipped but not shown in the README")
                    self.assertIn("./scripts/get_remote_info.sh --host ", readme)
                    self.assertIsNone(re.search(r"@[A-Z]+@", readme), "unfilled placeholder")
                    self.assertNotIn("./run.sh", readme)

    def test_results_section_order(self) -> None:
        readme = self.render(PUBLISH[0], "3")
        self.assertLess(readme.index("## Getting started"), readme.index("## See your results"))
        self.assertLess(readme.index("## See your results"), readme.index("## Run everything"))
        self.assertIn("./show_metrics.sh 315 --baseline", readme)
        self.assertIn("| One benchmark's runs and per-profile means | `./show_metrics.sh <benchmark>` |", readme)


if __name__ == "__main__":
    unittest.main()
