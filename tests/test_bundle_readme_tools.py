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
PUBLISH = [ROOT / "user_scripts" / "publish_benchmarks_to_github.sh"]
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
        suite = ROOT / "user_scripts" / "run_benchmark_suite.sh"
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
                                 {"run_benchmark_suite.sh", "show_metrics.sh", "get_benchmark_results.sh", "list_runs.sh"})

    def test_readme_explains_every_shipped_script(self) -> None:
        for script in PUBLISH:
            shipped = shipped_scripts(script.read_text(encoding="utf-8"))
            for digit in "1234":
                readme = self.render(script, digit)
                with self.subTest(script=script.name, platform=digit):
                    for name in shipped:
                        self.assertIn(f"./{name} ", readme, f"{name} is shipped but not shown in the README")
                    self.assertIn("`./get_benchmark_results.sh --host ", readme)
                    self.assertNotIn("./scripts/", readme)
                    self.assertIsNone(re.search(r"@[A-Z]+@", readme), "unfilled placeholder")
                    self.assertNotIn("./run.sh", readme)

    def test_section_order(self) -> None:
        for digit in "1234":
            readme = self.render(PUBLISH[0], digit)
            with self.subTest(platform=digit):
                headings = ["## Requirements", "## Install", "## Quick check", "## Run benchmarks",
                            "## Results", "## Reading the results", "## Update", "## Benchmarks"]
                positions = [readme.index(h + "\n") for h in headings]
                self.assertEqual(positions, sorted(positions))
                self.assertIn(f"./show_metrics.sh {digit}07 [--baseline]", readme)
                self.assertIn("| Runtime ledger (one line per run) | `/var/opt/benchmarks/runtime_ledger.csv` |", readme)

    def test_quick_check_and_restart(self) -> None:
        """2026-11-06 short README: two quick-check commands, what success looks like,
        smoke is not a number to quote, and the ROCm restart only where it happens."""
        for digit in "1234":
            readme = self.render(PUBLISH[0], digit)
            section = readme[readme.index("## Quick check"):readme.index("## Run benchmarks")]
            with self.subTest(platform=digit):
                self.assertIn(f"-w {digit}07 --smoke --show-output", section)
                self.assertIn(f"-w {digit}01,{digit}02,{digit}14 --smoke --show-output", section)
                self.assertIn("What matters is `0 failed`", section)
                self.assertIn("Quote `baseline` or `extended` numbers.", section)
                self.assertNotIn("\n\n\n", readme)
                self.assertNotRegex(section, r"\bWith ,")
                self.assertNotIn("HPL", readme)  # x20 is a cuSOLVER/rocSOLVER LU solve
                self.assertNotIn("v1.0.5", readme)
                if digit == "3":
                    self.assertIn("The machine restarts once.", section)
                    self.assertIn("With `--show-output`, the output ends like this", section)
                    self.assertIn("Connection to <your-machine-address> closed by remote host.", section)
                    self.assertIn("cannot start the MI300X", section)
                    self.assertIn("Log in again as root", section)
                elif digit == "1":
                    self.assertIn("If the machine restarts.", section)
                    self.assertIn("Log in again as root", section)
                    self.assertNotIn("closed by remote host", section)
                else:
                    self.assertIn("`nvidia-smi` lists the GPUs", readme)
                    self.assertIn("never installs the driver or restarts the machine", readme)
                    self.assertNotIn("Log in again as root", readme)

    def test_links_to_the_other_three_bundles_only(self) -> None:
        slugs = {"1": "bundle-amd-ubuntu-2404", "2": "bundle-nvidia-ubuntu-2404",
                 "3": "bundle-amd-ubuntu-2604", "4": "bundle-nvidia-ubuntu-2604"}
        for digit, own in slugs.items():
            readme = self.render(PUBLISH[0], digit)
            header = readme[:readme.index("## Requirements")]
            with self.subTest(platform=digit):
                self.assertNotIn(own, header)
                for other, slug in slugs.items():
                    if other != digit:
                        self.assertIn(f"https://github.com/example-org/{slug})", header)

    def test_benchmark_rows_use_short_names(self) -> None:
        text = PUBLISH[0].read_text(encoding="utf-8")
        program = "\n".join([
            "set -u", "ORG=example-org",
            'rows=""; for dir in 207-sys-bench-nvidia-stream-ddr5-bandwidth-ubu2404 132-gpu-bench-amd-rag-faiss-end2end-ubu2604; do',
            next(line for line in text.splitlines() if line.strip().startswith("short=${dir:4}")),
            next(line for line in text.splitlines() if line.strip().startswith('rows="${rows}| ${dir:0:3}')),
            "done", 'printf "%s" "${rows}"',
        ])
        out = subprocess.run([BASH, "-c", program], capture_output=True, text=True, timeout=30, check=True).stdout
        self.assertIn("| 207 | [stream-ddr5-bandwidth](https://github.com/example-org/207-sys-bench-nvidia-stream-ddr5-bandwidth-ubu2404) |", out)
        self.assertIn("| 132 | [rag-faiss-end2end](https://github.com/example-org/132-gpu-bench-amd-rag-faiss-end2end-ubu2604) |", out)

if __name__ == "__main__":
    unittest.main()
