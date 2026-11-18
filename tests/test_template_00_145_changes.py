#!/usr/bin/env python3
# File: tests/test_template_00_145_changes.py
# Description: TEMPLATE_00_145. The project root gets a bundle README and the
#   four suite scripts. The README text is templates/suite-tools/BUNDLE_README_TEMPLATE.md,
#   filled in by generation and by the publish script. The published text matches
#   the README bundle_readme() printed before that move.
# Execution: python3 -m unittest tests/test_template_00_145_changes.py
from __future__ import annotations

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import bundle_readme  # noqa: E402
from generator_version import generator_version  # noqa: E402
from create_generated_repo import (  # noqa: E402
    PROJECT_ROOT_SUITE_SCRIPTS,
    install_operator_tools,
    install_project_root_bundle,
)
from init_generated_repo import SHARED_DIRS  # noqa: E402

PUBLISH = ROOT / "user_scripts" / "publish_benchmarks_to_github.sh"
TEMPLATE = ROOT / "templates" / "suite-tools" / "BUNDLE_README_TEMPLATE.md"
FIXTURES = ROOT / "tests" / "fixtures" / "bundle_readme_00_144"
BASH = shutil.which("bash")

ROWS = (
    "| 101 | [rocm-stack-validation](https://github.com/garys-gpu-benchmarks/"
    "101-sys-bench-amd-rocm-stack-validation-ubu2404) |\n"
    "| 107 | [stream-ddr5-bandwidth](https://github.com/garys-gpu-benchmarks/"
    "107-sys-bench-amd-stream-ddr5-bandwidth-ubu2404) |\n"
)
BUNDLES = {
    "1": "bundle-amd-ubuntu-2404",
    "2": "bundle-nvidia-ubuntu-2404",
    "3": "bundle-amd-ubuntu-2604",
    "4": "bundle-nvidia-ubuntu-2604",
}
DOC_FILES = (
    "AGENTS.md",
    "docs/AI_AGENT_INSTRUCTIONS.md",
    "docs/generation-workflow.md",
    ".cursor/rules/generate-workloads.mdc",
    "README.md",
    "docs/repository-template.md",
    "docs/SUBMISSION_CHECKLIST.md",
)


def function_source(text: str, name: str) -> str:
    start = text.index(f"\n{name}() {{\n") + 1
    end = text.index("\n}\n", start) + 3
    return text[start:end]


def bash_bundle_readme(digit: str, bundle: str, want: str, rows: str) -> bytes:
    text = PUBLISH.read_text(encoding="utf-8")
    program = "\n".join([
        "set -u",
        "ORG=garys-gpu-benchmarks",
        "VERSION=v1.0.42",
        'BUNDLE_README_TEMPLATE=$1',
        function_source(text, "platform"),
        function_source(text, "bundle_readme"),
        'bundle_readme "$2" "$3" "$4" "$5"',
    ])
    result = subprocess.run(
        [BASH, "-c", program, "bash", str(TEMPLATE), digit, bundle, want, rows],
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr.decode("utf-8", "replace"))
    return result.stdout


class PublishReadmeUnchangedTests(unittest.TestCase):
    @unittest.skipIf(BASH is None, "bash is not installed")
    def test_publish_readme_matches_the_pre_move_text_for_all_four_platforms(self) -> None:
        publish = PUBLISH.read_text(encoding="utf-8")
        self.assertNotIn("cat <<'README'", publish)
        self.assertIn("templates/suite-tools/BUNDLE_README_TEMPLATE.md", publish)
        for digit, bundle in BUNDLES.items():
            with self.subTest(platform=digit):
                golden = (FIXTURES / f"platform-{digit}.md").read_bytes()
                bash = bash_bundle_readme(digit, bundle, "2", ROWS)
                python = bundle_readme.render_bundle_readme(
                    digit, bundle, "2", ROWS,
                    org="garys-gpu-benchmarks", version="v1.0.42", generator_root=ROOT,
                ).encode("utf-8")
                self.assertEqual(bash, golden)
                self.assertEqual(python, golden)
                self.assertNotIn(b"\n\n\n", golden)
                self.assertNotIn(b"@PLATFORM@", golden)

    def test_short_names_match_the_publish_script(self) -> None:
        self.assertEqual(
            bundle_readme.short_workload_name("207-sys-bench-nvidia-stream-ddr5-bandwidth-ubu2404"),
            "stream-ddr5-bandwidth",
        )
        self.assertEqual(
            bundle_readme.short_workload_name("132-gpu-bench-amd-rag-faiss-end2end-ubu2604"),
            "rag-faiss-end2end",
        )


class ProjectRootBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.parent = Path(self._tmp.name) / "Project545"
        self.project = self.parent / "TEMPLATE_00_145"
        self.project.mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _install(self) -> str:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            install_project_root_bundle(ROOT, self.project)
        return out.getvalue()

    def _add(self, name: str) -> None:
        (self.project / name).mkdir()

    def test_scripts_are_the_user_scripts_masters_and_executable(self) -> None:
        self._add("107-sys-bench-amd-stream-ddr5-bandwidth-ubu2404")
        out = self._install()
        self.assertIn("Installed project-root suite file", out)
        for name in PROJECT_ROOT_SUITE_SCRIPTS:
            dst = self.project / name
            expected = (ROOT / "user_scripts" / name).read_bytes().replace(b"\r\n", b"\n")
            self.assertEqual(dst.read_bytes(), expected, name)
            if os.name != "nt":
                self.assertTrue(os.access(dst, os.X_OK), name)
        # The workload directory does not receive the bundle root.
        workload = self.project / "107-sys-bench-amd-stream-ddr5-bandwidth-ubu2404"
        self.assertFalse((workload / "run_benchmark_suite.sh").exists())
        self.assertFalse((workload / "README.md").exists())

    def test_readme_names_the_platform_bundle_and_the_workload(self) -> None:
        self._add("107-sys-bench-amd-stream-ddr5-bandwidth-ubu2404")
        self._install()
        text = (self.project / "README.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# AMD ROCm - Ubuntu 24.04 benchmark bundle\n"))
        self.assertIn("bundle-amd-ubuntu-2404", text)
        self.assertIn("https://github.com/garys-gpu-benchmarks/bundle-amd-ubuntu-2404", text)
        self.assertIn("| 107 | [stream-ddr5-bandwidth](", text)
        # The version comes from VERSION (TEMPLATE_00_146), never a typed-in number.
        self.assertIn(f"pinned to its tested {generator_version(ROOT) or 'local'} release", text)
        self.assertNotIn("More than one platform", text)
        # The other three bundles are linked; this bundle's own slug is not in that list.
        header = text.split("## Requirements", 1)[0]
        self.assertNotIn("(https://github.com/garys-gpu-benchmarks/bundle-amd-ubuntu-2404)", header)
        self.assertIn("bundle-nvidia-ubuntu-2404", header)

    def test_second_workload_refreshes_the_readme(self) -> None:
        self._add("107-sys-bench-amd-stream-ddr5-bandwidth-ubu2404")
        self._install()
        first = (self.project / "README.md").read_bytes()
        self._add("108-sys-bench-amd-fio-filesystem-stress-ubu2404")
        out = self._install()
        second = (self.project / "README.md").read_bytes()
        self.assertIn("Installed project-root suite file", out)
        self.assertIn(b"| 107 |", second)
        self.assertIn(b"| 108 |", second)
        self.assertNotEqual(first, second)
        self.assertIn(b"2 system and GPU benchmarks", second)

    def test_identical_rerun_writes_nothing(self) -> None:
        self._add("107-sys-bench-amd-stream-ddr5-bandwidth-ubu2404")
        self._install()
        out = self._install()
        self.assertNotIn("Installed project-root suite file", out)
        self.assertNotIn("Kept existing", out)

    def test_user_edited_readme_and_script_are_kept(self) -> None:
        self._add("107-sys-bench-amd-stream-ddr5-bandwidth-ubu2404")
        self._install()
        (self.project / "README.md").write_text("edited by hand\n", encoding="utf-8")
        (self.project / "show_metrics.sh").write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
        self._add("108-sys-bench-amd-fio-filesystem-stress-ubu2404")
        out = self._install()
        self.assertIn("Kept existing", out)
        self.assertEqual((self.project / "README.md").read_text(encoding="utf-8"), "edited by hand\n")
        self.assertEqual((self.project / "show_metrics.sh").read_text(encoding="utf-8"), "#!/bin/sh\necho mine\n")
        # The scripts the user did not touch stay the masters.
        expected = (ROOT / "user_scripts" / "list_runs.sh").read_bytes().replace(b"\r\n", b"\n")
        self.assertEqual((self.project / "list_runs.sh").read_bytes(), expected)

    def test_more_than_one_platform_is_named_and_not_guessed(self) -> None:
        self._add("107-sys-bench-amd-stream-ddr5-bandwidth-ubu2404")
        self._add("201-sys-bench-nvidia-rocm-stack-validation-ubu2404")
        self._install()
        text = (self.project / "README.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# More than one platform\n"))
        self.assertIn("does not pick one", text)
        self.assertIn("AMD ROCm - Ubuntu 24.04", text)
        self.assertIn("NVIDIA CUDA - Ubuntu 24.04", text)
        self.assertIn("bundle-amd-ubuntu-2404", text)
        self.assertIn("bundle-nvidia-ubuntu-2404", text)
        self.assertIn("| 107 |", text)
        self.assertIn("| 201 |", text)
        self.assertNotIn("benchmark bundle\n", text.split("## Benchmarks", 1)[0])

    def test_parent_folder_still_gets_only_the_three_laptop_tools(self) -> None:
        self._add("107-sys-bench-amd-stream-ddr5-bandwidth-ubu2404")
        with contextlib.redirect_stdout(io.StringIO()):
            install_operator_tools(ROOT, self.project)
            install_project_root_bundle(ROOT, self.project)
        for name in ("get_benchmark_results.sh", "list_runs.sh", "show_metrics.sh"):
            self.assertTrue((self.parent / name).is_file(), name)
            self.assertTrue((self.project / name).is_file(), name)
        self.assertFalse((self.parent / "run_benchmark_suite.sh").exists())
        self.assertFalse((self.parent / "README.md").exists())
        self.assertTrue((self.project / "run_benchmark_suite.sh").is_file())
        self.assertTrue((self.project / "README.md").is_file())


class PublishDoesNotTakeTheProjectRootTests(unittest.TestCase):
    def test_step_1_copies_workload_directories_only(self) -> None:
        text = PUBLISH.read_text(encoding="utf-8")
        step0 = text[text.index("# STEP 0:"):text.index("# STEP 1:")]
        step1 = text[text.index("# STEP 1:"):text.index("# STEP 2:")]
        self.assertIn("which will not be published", step0)
        self.assertIn("for dir in [1-4][0-9][0-9]-*; do", step1)
        self.assertNotIn("run_benchmark_suite.sh", step1)
        self.assertNotIn("BUNDLE_README", step1)
        self.assertNotIn("templates", SHARED_DIRS)
        self.assertNotIn("user_scripts", SHARED_DIRS)

    def test_docs_list_the_bundle_root_as_project_root_output(self) -> None:
        for rel in DOC_FILES:
            with self.subTest(rel=rel):
                text = (ROOT / rel).read_text(encoding="utf-8")
                self.assertIn("TEMPLATE_00_145", text)
                for name in ("README.md", "get_benchmark_results.sh", "list_runs.sh",
                             "run_benchmark_suite.sh", "show_metrics.sh"):
                    self.assertIn(name, text)
        issues = (ROOT / "docs" / "OPEN_ISSUES.md").read_text(encoding="utf-8")
        self.assertIn("| A8 | 00_145 |", issues)


if __name__ == "__main__":
    unittest.main()
