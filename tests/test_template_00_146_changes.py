#!/usr/bin/env python3
# File: tests/test_template_00_146_changes.py
# Description: TEMPLATE_00_146 checks: the NVIDIA clean-image gate is conditional
#   on install-code changes and runs x27-x30 first on a fresh image; ROCm pip
#   commands that read the AMD wheel index retry when a pinned build is missing;
#   the generator version comes from VERSION, not the folder name.
"""TEMPLATE_00_146 change checks."""

from __future__ import annotations

import contextlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Full path, as the other bash tests do: on Windows a bare "bash" can start
# System32\bash.exe (WSL) instead of Git Bash.
BASH = shutil.which("bash")
sys.path.insert(0, str(ROOT / "scripts"))

import generator_version as gv  # noqa: E402


def gate_section() -> str:
    text = (ROOT / "docs/AI_AGENT_INSTRUCTIONS.md").read_text(encoding="utf-8")
    return text.split("### Clean-image acceptance")[1].split("\n## ")[0].split("\n### ")[0]


class CleanImageGateTests(unittest.TestCase):
    def test_gate_is_conditional_on_install_code(self) -> None:
        section = gate_section()
        self.assertIn("**When this gate is required.**", section)
        self.assertIn("do not report it as blocking a publish", section)
        for path in ("setup_nvidia_skeleton.sh", "vllm-*-nvidia", "sglang-*-nvidia"):
            with self.subTest(path=path):
                self.assertIn(path, section)

    def test_overlays_run_first_on_fresh_image(self) -> None:
        section = gate_section()
        self.assertIn("**first and only**", section)
        self.assertIn("x27, x28, x29 and x30", section)
        self.assertIn("command -v nvcc", section)

    def test_local_copy_not_bundle_clone(self) -> None:
        self.assertIn("Do **not** `git clone` the published bundle", gate_section())

    def test_after_publish_clone_check_every_publish(self) -> None:
        section = gate_section()
        self.assertIn("**Every publish, NVIDIA and AMD:**", section)
        self.assertIn("git clone --recurse-submodules", section)


ROCM_SKELETON = ROOT / "scripts/templates/setup_rocm_reboot_skeleton.sh"


def rocm_skeleton() -> str:
    return ROCM_SKELETON.read_text(encoding="utf-8")


def logical_commands(text: str) -> list[str]:
    """Join backslash-continued lines into one command each."""
    commands: list[str] = []
    current = ""
    for line in text.splitlines():
        if line.rstrip().endswith("\\"):
            current += line.rstrip()[:-1] + " "
            continue
        commands.append((current + line).strip())
        current = ""
    return commands


def retry_helpers() -> str:
    text = rocm_skeleton()
    return text.split("# BEGIN rocm_pip_retry\n")[1].split("# END rocm_pip_retry\n")[0]


class RocmPipRetryStaticTests(unittest.TestCase):
    def test_every_amd_index_pip_install_retries(self) -> None:
        installs = [
            cmd
            for cmd in logical_commands(rocm_skeleton())
            if "pip install" in cmd and "PYTORCH_ROCM_INDEX_URL" in cmd
        ]
        self.assertGreaterEqual(len(installs), 5)
        for cmd in installs:
            with self.subTest(cmd=cmd[:90]):
                self.assertTrue(cmd.startswith("rocm_pip_retry "), cmd)

    def test_index_probes_go_through_helper(self) -> None:
        text = rocm_skeleton()
        probes = [c for c in logical_commands(text) if "pip index versions" in c]
        self.assertEqual(len(probes), 1, probes)
        self.assertIn("pip index versions", retry_helpers())
        self.assertIn('rocm_index_lists_version torch "${torch_version}"', text)
        self.assertIn('rocm_index_lists_version torchvision "${TORCHVISION_VERSION}"', text)

    def test_retry_is_limited_to_index_omission_and_timeouts(self) -> None:
        helpers = retry_helpers()
        self.assertIn('ROCM_PIP_RETRY_ATTEMPTS="${ROCM_PIP_RETRY_ATTEMPTS:-3}"', helpers)
        self.assertIn('ROCM_PIP_RETRY_DELAY_SEC="${ROCM_PIP_RETRY_DELAY_SEC:-20}"', helpers)
        self.assertIn(r"\+(rocm|git)", helpers)
        self.assertNotIn("--no-index", helpers)
        self.assertRegex(rocm_skeleton(), re.compile(r"^# Version: 1\.4\.0$", re.M))


@unittest.skipUnless(BASH, "bash not available")
class RocmPipRetryBehaviorTests(unittest.TestCase):
    PRELUDE = r"""
set -Eeuo pipefail
trap 'echo ERR_TRAP; exit 99' ERR
log_warn() { echo "[WARN] $*" >&2; }
source "$HELPERS"
ROCM_PIP_RETRY_DELAY_SEC=0
bump() { echo $(( $(cat "$COUNTER") + 1 )) > "$COUNTER"; }
calls() { cat "$COUNTER"; }
"""

    def run_bash(self, body: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            helpers = Path(tmp) / "helpers.sh"
            helpers.write_text(retry_helpers(), encoding="utf-8", newline="\n")
            counter = Path(tmp) / "counter"
            counter.write_text("0", encoding="utf-8")
            script = Path(tmp) / "t.sh"
            script.write_text(self.PRELUDE + body, encoding="utf-8", newline="\n")
            return subprocess.run(
                [BASH, script.name],
                cwd=tmp,
                env={**os.environ, "HELPERS": helpers.name, "COUNTER": counter.name},
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )

    def test_missing_rocm_build_is_retried_then_passes(self) -> None:
        proc = self.run_bash(
            'flaky() { bump; if (( $(calls) < 2 )); then '
            'echo "ERROR: No matching distribution found for triton==3.8.0+git669b31ac.rocm10.1.0 (from torch)"; '
            'return 1; fi; echo installed; }\n'
            'rocm_pip_retry flaky\necho "calls=$(calls)"\n'
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("calls=2", proc.stdout)
        self.assertIn("attempt 1 of 3", proc.stderr)

    def test_other_pip_errors_fail_on_first_attempt(self) -> None:
        proc = self.run_bash(
            'bad() { bump; echo "ERROR: No matching distribution found for nosuchpkg==1.0"; return 3; }\n'
            'rc=0; rocm_pip_retry bad || rc=$?\necho "rc=$rc calls=$(calls)"\n'
        )
        self.assertIn("rc=3 calls=1", proc.stdout)

    def test_gives_up_after_three_attempts_and_setup_stops(self) -> None:
        proc = self.run_bash(
            'always() { bump; echo "ERROR: Could not find a version that satisfies the requirement '
            'torch==2.13.0+rocm10.1.0"; return 1; }\n'
            'rocm_pip_retry always\necho NOT_REACHED\n'
        )
        self.assertEqual(proc.returncode, 99)
        self.assertEqual(proc.stdout.count("Could not find a version"), 3)
        self.assertNotIn("NOT_REACHED", proc.stdout)

    def test_index_probe_retries_until_version_listed(self) -> None:
        proc = self.run_bash(
            "PYTHON_BIN=fakepy; PYTORCH_ROCM_INDEX_URL=https://example.invalid/\n"
            'fakepy() { bump; if (( $(calls) < 3 )); then echo "torch (2.12.0+rocm10.1.0)"; '
            'else echo "torch (2.13.0+rocm10.1.0)"; fi; }\n'
            'rc=0; rocm_index_lists_version torch 2.13.0+rocm10.1.0 || rc=$?; echo "rc=$rc calls=$(calls)"\n'
            'echo 0 > "$COUNTER"; rc=0; rocm_index_lists_version torch 9.9.9 || rc=$?; echo "missing=$rc"\n'
            'fakepy() { bump; echo down; return 1; }\n'
            'rc=0; rocm_index_lists_version torch 2.13.0 || rc=$?; echo "queryfail=$rc"\n'
        )
        self.assertIn("rc=0 calls=3", proc.stdout, proc.stderr)
        self.assertIn("missing=1", proc.stdout)
        self.assertIn("queryfail=2", proc.stdout)


class GeneratorVersionTests(unittest.TestCase):
    def test_version_file_matches_newest_changelog_entry(self) -> None:
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertRegex(version, r"^TEMPLATE_\d+_\d+$")
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        newest = re.search(r"^## \d{4}-\d{2}-\d{2} \S+ (TEMPLATE_\d+_\d+):", changelog, re.M)
        self.assertIsNotNone(newest, "no dated TEMPLATE_00_NNN heading in CHANGELOG.md")
        self.assertEqual(
            version,
            newest.group(1),
            "VERSION and the newest CHANGELOG.md heading differ: a new template needs both updated",
        )
        self.assertEqual(gv.generator_version(ROOT), version)

    def test_version_file_wins_in_any_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "mydev" / "ai-agent-gpu-benchmark-repo-generator"
            root.mkdir(parents=True)
            self.assertEqual(gv.generator_version(root), "")
            (root / "VERSION").write_text("TEMPLATE_00_200\n", encoding="utf-8")
            self.assertEqual(gv.generator_version(root), "TEMPLATE_00_200")
            (root / "VERSION").write_text("not a version\n", encoding="utf-8")
            self.assertEqual(gv.generator_version(root), "")

    def test_folder_name_is_the_fallback_and_a_mismatch_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "TEMPLATE_00_201" / "ai-agent-gpu-benchmark-repo-generator"
            root.mkdir(parents=True)
            self.assertEqual(gv.generator_version(root), "TEMPLATE_00_201")
            (root / "VERSION").write_text("TEMPLATE_00_200\n", encoding="utf-8")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(gv.generator_version(root, warn=True), "TEMPLATE_00_200")
            self.assertIn("[WARN] VERSION says TEMPLATE_00_200 but the folder path says TEMPLATE_00_201", err.getvalue())
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                gv.generator_version(root)
            self.assertEqual(err.getvalue(), "")

    def test_every_version_reader_uses_the_shared_function(self) -> None:
        expected = {
            "scripts/create_generated_repo.py": 'generator_version(source_root) or "local"',
            "scripts/create_one_workload.py": "template_version=generator_version(template_root)",
            "scripts/run_from_prompt.py": 'generator_version(template_root, warn=True) or "unknown"',
        }
        for rel, needle in expected.items():
            with self.subTest(rel=rel):
                text = (ROOT / rel).read_text(encoding="utf-8")
                self.assertIn(needle, text)
                self.assertNotIn("template_version_from_path(", text)
        promote = (ROOT / "user_scripts/promote_results_reference.sh").read_text(encoding="utf-8")
        self.assertIn('"${repos_dir}/ai-agent-gpu-benchmark-repo-generator/VERSION"', promote)

    def test_agents_rule_forbids_typed_in_versions_in_tests(self) -> None:
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("## Generator Version", text)
        self.assertIn("never type the current template number", text)


class HostBashTests(unittest.TestCase):
    """Laptop-side shell commands start Git Bash on Windows, never WSL bash."""

    LAPTOP_SCRIPTS = ("scripts/create_generated_repo.py", "scripts/create_generated_batch.py")
    # Run on the benchmark VM (Linux), where a bare "bash" is correct.
    VM_SCRIPTS = {"scripts/update_runtime_ledger.py"}

    def test_vm_refresh_uses_resolve_host_bash(self) -> None:
        for rel in self.LAPTOP_SCRIPTS:
            with self.subTest(rel=rel):
                text = (ROOT / rel).read_text(encoding="utf-8")
                self.assertIn("from host_exec import resolve_host_bash", text)
                self.assertIn("resolve_host_bash(),", text)

    def test_no_bare_bash_launch_in_laptop_scripts(self) -> None:
        bare = re.compile(r'\[\s*"bash"')
        for path in sorted((ROOT / "scripts").glob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if rel in self.VM_SCRIPTS:
                continue
            with self.subTest(rel=rel):
                self.assertIsNone(bare.search(path.read_text(encoding="utf-8")), rel)

    def test_readme_names_git_bash_not_wsl(self) -> None:
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("on Windows the generator runs its commands in Git Bash, never WSL bash", text)


if __name__ == "__main__":
    unittest.main()
