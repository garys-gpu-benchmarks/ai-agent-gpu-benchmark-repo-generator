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
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# One publish script since 2026-10-19 (the former _manual variant, renamed).
PUBLISH = [ROOT / "scripts" / "publish_benchmarks_to_github.sh"]
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
        # A backtick left unescaped inside a double-quoted string runs as a command
        # (2026-10-20: "With `--show-output`," printed as "With ,"); bash reports it here.
        self.assertEqual(result.stderr, "", result.stderr)
        return result.stdout

    def test_bundle_suite_script_edits_apply(self) -> None:
        """Step 7 rewrites the shared run_benchmark_suite.sh for each bundle with sed and
        stops the publish if an edit misses; run those functions on the real script here."""
        text = PUBLISH[0].read_text(encoding="utf-8")
        suite = ROOT / "templates" / "suite-tools" / "scripts" / "run_benchmark_suite.sh"
        for digit in "1234":
            program = "\n".join([
                "set -u", "cd \"$1\"",
                function_source(text, "bundle_suite_script"),
                function_source(text, "check_bundle_suite_script"),
                f'bundle_suite_script {digit} <"$2" >bundle_copy.sh && check_bundle_suite_script bundle_copy.sh {digit}'
                ' && bash bundle_copy.sh --help',
            ])
            with self.subTest(platform=digit), tempfile.TemporaryDirectory() as tmp:
                result = subprocess.run([BASH, "-c", program, "bash", tmp, str(suite)],
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("Default: --smoke   (full run: --smoke --baseline --extended)", result.stdout)
                self.assertIn("--smoke --baseline --extended    # everything, all 3 profiles", result.stdout)
                self.assertIn(f"-w {digit}01,{digit}07,{digit}21 --baseline", result.stdout)
                self.assertIn(f"-w {digit}05 --smoke --show-output", result.stdout)

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
        self.assertIn("./show_metrics.sh 307 --baseline", readme)  # 2026-10-19: Getting started uses x07
        self.assertIn("| One benchmark's runs and per-profile means | `./show_metrics.sh <benchmark>` |", readme)

    def test_getting_started_shows_success_and_restart(self) -> None:
        """2026-10-19 technician review: show what success looks like, a watched and a
        quiet command for the long install, and the 26.04 ROCm restart."""
        for digit in "1234":
            readme = self.render(PUBLISH[0], digit)
            section = readme[readme.index("## Getting started"):readme.index("## See your results")]
            with self.subTest(platform=digit):
                # Every sample summary sits in a fenced block; bare "=====" lines under
                # text render as Markdown headings on GitHub.
                fenced = re.findall(r"```text\n(.*?)```", section, re.S)
                self.assertEqual(sum("SUMMARY: " in block for block in fenced), 2)
                outside = re.sub(r"```.*?```", "", section, flags=re.S)
                self.assertNotIn("=====", outside)
                self.assertIn("SUMMARY: 1 of 1 runs finished: 1 passed, 0 failed", section)
                self.assertIn("SUMMARY: 3 of 3 runs finished: 3 passed, 0 failed", section)
                self.assertIn(f"-w {digit}01,{digit}02,{digit}14 --smoke --show-output", section)
                self.assertIn(f"-w {digit}01,{digit}02,{digit}14 --smoke                 # quiet", section)
                self.assertNotIn("quiet for 5-20 minutes", section)
                self.assertIn("what matters is `0 failed`", section)
                self.assertIn("### 3. Smoke is a wiring check, not a measurement", section)
                self.assertNotIn("under one minute", section)
                self.assertNotRegex(section, r"\bWith ,")
                if digit == "3":
                    self.assertIn("With `--show-output`, the output ends like this", section)
                    self.assertIn("Connection to <your-machine-address> closed by remote host.", section)
                    self.assertIn("The machine restarts once.", section)
                    self.assertIn("cannot start the MI300X", section)
                elif digit == "1":
                    self.assertIn("If the machine restarts.", section)
                    self.assertNotIn("closed by remote host", section)
                else:
                    self.assertIn("does not restart the machine", section)
                    self.assertNotIn("Log in again as root", section)
                    self.assertIn("`nvidia-smi` lists the GPUs", readme)
                # The restart steps come before the step-2 success sample.
                if digit in "13":
                    self.assertLess(section.index("Log in again as root"), section.index("SUMMARY: 3 of 3"))


if __name__ == "__main__":
    unittest.main()
