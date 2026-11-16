#!/usr/bin/env python3
"""TEMPLATE_00_142 (2026-11-16): the setup script is run_setup.sh.

TEMPLATE_00_143 removed the setup.sh wrapper this file used to install and
execute. These checks still cover the rename, the resume unit's old name,
shared CI accepting either name, and ensure_setup.sh running run_setup.sh.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IC = ROOT / "implementation_components"
BASH = shutil.which("bash")
OLD_NAME = re.compile(r"(?<![A-Za-z0-9_\-])setup\.sh(?![A-Za-z0-9_])")


def tracked_text_files() -> list[Path]:
    listed = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    if listed.returncode != 0:
        return [p for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts]
    return [ROOT / name for name in listed.stdout.splitlines() if name]


class GeneratorNamesTests(unittest.TestCase):
    # Files that may still say setup.sh: release history, the shared CI sample
    # and check that still accept an older published repository's setup.sh,
    # and these tests.
    ALLOWED = {
        "CHANGELOG.md", "docs/CHANGELOG.md",
        "templates/shared-workflows/tests/fixtures/sample-workload/setup.sh",
        "templates/shared-workflows/.github/workflows/ci.yml",
        "scripts/remove_template_copy.py",
        "scripts/update_runtime_ledger.py",
        "tests/test_template_00_142_run_setup.py",
        "tests/test_template_00_143_changes.py",
    }

    def test_no_file_still_names_setup_sh(self) -> None:
        offenders = []
        for path in tracked_text_files():
            rel = path.relative_to(ROOT).as_posix()
            if rel in self.ALLOWED or not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if OLD_NAME.search(line):
                    offenders.append(f"{rel}:{number}: {line.strip()[:120]}")
        self.assertEqual(offenders, [])

    def test_overlays_ship_run_setup_sh(self) -> None:
        overlays = []
        for component in sorted(IC.glob("*/component.json")):
            data = json.loads(component.read_text(encoding="utf-8"))
            names = [str(item) for item in data.get("overlay", []) + data.get("provides", [])]
            with self.subTest(component=component.parent.name):
                self.assertNotIn("setup.sh", names)
                self.assertFalse((component.parent / "files" / "setup.sh").exists())
                if "run_setup.sh" in names:
                    overlays.append(component.parent.name)
                    self.assertTrue((component.parent / "files" / "run_setup.sh").is_file())
        self.assertEqual(sorted(overlays), ["sglang-prompt-response-nvidia", "vllm-kvcache-nvidia",
                                            "vllm-throughput-nvidia", "vllm-token-generation-nvidia"])

    def test_resume_service_runs_run_setup_and_keeps_its_name(self) -> None:
        text = (ROOT / "scripts" / "templates" / "setup_rocm_reboot_skeleton.sh").read_text(encoding="utf-8")
        self.assertIn("ExecStart=/bin/bash ${REPO_ROOT}/run_setup.sh --assume-yes --resume-auto --resume-from-service",
                      text)
        # Same unit name as before, so a repository regenerated in the same folder
        # replaces its old unit instead of leaving a second one enabled.
        self.assertIn('RESUME_SERVICE_NAME="${REPO_NAME}-setup-resume.service"', text)

    def test_generation_runs_run_setup(self) -> None:
        text = (ROOT / "scripts" / "create_one_workload.py").read_text(encoding="utf-8")
        self.assertIn('setup = "bash run_setup.sh --assume-yes"', text)
        self.assertIn('"run_setup.sh"', (ROOT / "scripts" / "init_generated_repo.py").read_text(encoding="utf-8"))

    def test_init_does_not_write_setup_sh(self) -> None:
        text = (ROOT / "scripts" / "init_generated_repo.py").read_text(encoding="utf-8")
        self.assertIsNone(OLD_NAME.search(text))
        self.assertNotIn("setup_compat_wrapper", text)
        self.assertFalse((ROOT / "scripts" / "templates" / "setup_compat_wrapper.sh").exists())

    def test_shared_ci_accepts_either_name(self) -> None:
        text = (ROOT / "templates" / "shared-workflows" / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("for script in run_setup.sh setup.sh; do", text)
        self.assertIn('if [[ ! -s run_setup.sh && ! -s setup.sh ]]; then', text)


@unittest.skipIf(BASH is None, "bash is not installed")
class EnsureSetupTests(unittest.TestCase):
    def test_ensure_setup_runs_run_setup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            shutil.copy(ROOT / "scripts" / "ensure_setup.sh", root / "scripts" / "ensure_setup.sh")
            (root / "run_setup.sh").write_text(
                '#!/usr/bin/env bash\n# accepts --assume-yes\necho "run_setup: $*"\ntouch .setup_state\n',
                encoding="utf-8")
            out = subprocess.run([BASH, "scripts/ensure_setup.sh"], cwd=root, capture_output=True, text=True,
                                 timeout=30)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("run_setup: --assume-yes", out.stdout)
            self.assertIn("[PASS] Automatic setup completed", out.stdout)


if __name__ == "__main__":
    unittest.main()
