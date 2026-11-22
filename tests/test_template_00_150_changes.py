#!/usr/bin/env python3
# File: tests/test_template_00_150_changes.py
# Description: TEMPLATE_00_150 checks. The ledger summary that
#   get_benchmark_results.sh prints said "other: N" for runs without exit code 0,
#   while run_benchmark_suite.sh says "N passed, M failed" and list_runs.sh has
#   --failed. The summary now says "failed (non-zero or missing exit code): N".
#   list_runs.sh carries the same ledger-table awk program and is kept identical.
#   Runs each script's real awk program on a ledger with a passed run, a failed
#   run and a row with no exit code.
#   Also: on 2026-11-21 the AMD vLLM index served a 91.9 MB flash-attn 2.8.3 cp314
#   wheel (same name and version as the 100.5 MB one that worked on 2026-11-20)
#   whose flash_attn_2_cuda references c10::cuda::CUDAErrorLogCapture, which ROCm
#   torch 2.13 does not export; 127-129 exited before ready. verify_vllm_flash_attn
#   in the ROCm setup skeleton keeps a wheel that imports and removes one that
#   does not. Runs the real function under HOST_BASH with a bash stub as
#   PYTHON_BIN, so no Python interpreter is resolved inside Git Bash.
#   Also (2026-11-22): what a user generates. The workspace README names the
#   generator release (git tag) instead of TEMPLATE_00_NNN and has no bundle clone
#   text; run_benchmark_suite.sh gets the bundle's numbers; generator-only files are
#   removed once a workload passes (publish's own list); RESULTS_REFERENCE.md names
#   no template; TEMPLATE_00_ patterns accept any template number.
# Execution: python3 -m unittest tests/test_template_00_150_changes.py
"""TEMPLATE_00_150 change checks."""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = (ROOT / "user_scripts" / "get_benchmark_results.sh", ROOT / "user_scripts" / "list_runs.sh")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from host_bash import HOST_BASH, bash_path  # noqa: E402

LEDGER = (
    "runtime_root_dir,benchmark_profile,total_runtime_mm_ss,exit_code\n"
    "/opt/benchmarks/101-a-ubu2404,smoke,00:01,0\n"
    "/opt/benchmarks/102-b-ubu2404,smoke,00:02,1\n"
    "/opt/benchmarks/103-c-ubu2404,smoke,00:03,\n"
)
SUMMARY = "Runs in the ledger: 3   passed (exit code 0): 1   failed (non-zero or missing exit code): 2"


def ledger_awk(script: Path) -> str:
    text = script.read_text(encoding="utf-8")
    match = re.search(r"LEDGER_TABLE_AWK=\$\(cat <<'AWK'\n(.*?)\nAWK\n", text, re.S)
    if match is None:
        raise AssertionError(f"no LEDGER_TABLE_AWK in {script}")
    return match.group(1)


class LedgerSummaryWordingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.ledger = self.tmp / "ledger.csv"
        self.ledger.write_text(LEDGER, encoding="utf-8", newline="")

    def summary(self, script: Path) -> str:
        program = self.tmp / "table.awk"
        program.write_text(ledger_awk(script) + "\n", encoding="utf-8", newline="")
        done = subprocess.run(
            [HOST_BASH, "-c", 'awk -v p="" -v failed="" -v summary=true -f "$1" "$2"', "t",
             bash_path(program), bash_path(self.ledger)],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def test_get_benchmark_results_says_failed(self) -> None:
        out = self.summary(SCRIPTS[0])
        self.assertIn(SUMMARY, out)
        self.assertNotIn("other:", out)

    def test_list_runs_awk_says_failed(self) -> None:
        out = self.summary(SCRIPTS[1])
        self.assertIn(SUMMARY, out)
        self.assertNotIn("other:", out)

    def test_both_scripts_share_one_table_program(self) -> None:
        self.assertEqual(ledger_awk(SCRIPTS[0]), ledger_awk(SCRIPTS[1]))



SKELETON = ROOT / "scripts" / "templates" / "setup_rocm_reboot_skeleton.sh"
SYMBOL = "_ZN3c104cuda19CUDAErrorLogCaptureC1Ev"

# Stands in for the venv python. State lives in files under $STUB_STATE:
# installed (flash_attn is on the path), broken (the import probe fails) and
# stuck (pip uninstall fails). Every call is appended to $STUB_STATE/calls.
STUB = r'''#!/usr/bin/env bash
state="$STUB_STATE"
printf '%s\n' "$*" >> "$state/calls"
case "$*" in
  *"-m pip uninstall -y flash-attn"*)
    [[ -e "$state/stuck" ]] && exit 1
    rm -f "$state/installed"
    exit 0 ;;
  *"is not None)"*)
    [[ -e "$state/installed" ]] && exit 1
    exit 0 ;;
  *"is None)"*)
    [[ -e "$state/installed" ]] && exit 0
    exit 1 ;;
  *"flash_attn.ops.triton.rotary"*)
    if [[ -e "$state/broken" ]]; then
      echo "Traceback (most recent call last):" >&2
      echo "ImportError: /opt/x/.venv/lib/python3.14/site-packages/flash_attn_2_cuda.cpython-314-x86_64-linux-gnu.so: undefined symbol: _ZN3c104cuda19CUDAErrorLogCaptureC1Ev" >&2
      exit 1
    fi
    exit 0 ;;
esac
echo "unexpected stub call: $*" >&2
exit 99
'''

# Sources the extracted function with setup's helpers stubbed, runs it under
# set -euo pipefail as run_setup.sh does, and prints "rc=N".
RUNNER = r'''
source "$FUNC_FILE"
install_status_log_step() { printf 'STEP %s %s\n' "$1" "$2"; }
log_warn() { printf 'WARN %s\n' "$*"; }
die() { printf 'DIE %s\n' "$*"; exit 1; }
PYTHON_BIN="$STUB_BIN"
FLASH_ATTN_VERSION=2.8.3
( set -euo pipefail; verify_vllm_flash_attn ) 2>&1
echo "rc=$?"
'''


def skeleton() -> str:
    return SKELETON.read_text(encoding="utf-8")


def function_text() -> str:
    match = re.search(r"^verify_vllm_flash_attn\(\) \{\n.*?^\}\n", skeleton(), re.S | re.M)
    if match is None:
        raise AssertionError("no verify_vllm_flash_attn() in the ROCm setup skeleton")
    return match.group(0)


class FlashAttnProbeBehaviorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.state = self.tmp / "state"
        self.state.mkdir()
        (self.state / "calls").write_text("", encoding="utf-8")
        self.func = self.tmp / "func.sh"
        self.func.write_text(function_text(), encoding="utf-8", newline="")
        self.stub = self.tmp / "python"
        self.stub.write_text(STUB, encoding="utf-8", newline="")
        self.stub.chmod(self.stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def run_probe(self, *flags: str) -> tuple[int, str, str]:
        for flag in flags:
            (self.state / flag).write_text("", encoding="utf-8")
        env = dict(os.environ, FUNC_FILE=bash_path(self.func), STUB_BIN=bash_path(self.stub),
                   STUB_STATE=bash_path(self.state))
        done = subprocess.run([HOST_BASH, "-c", RUNNER], capture_output=True, text=True, timeout=60, env=env)
        out = done.stdout + done.stderr
        rc_lines = [line for line in out.splitlines() if line.startswith("rc=")]
        if not rc_lines:
            raise AssertionError(out)
        calls = (self.state / "calls").read_text(encoding="utf-8")
        self.assertNotIn("unexpected stub call", out)
        return int(rc_lines[-1][3:]), out, calls

    def test_not_installed_is_logged_and_nothing_is_removed(self) -> None:
        rc, out, calls = self.run_probe()
        self.assertEqual(rc, 0, out)
        self.assertIn("STEP flash_attn flash-attn not installed; vLLM will not import it", out)
        self.assertNotIn("pip uninstall", calls)
        self.assertNotIn("WARN", out)

    def test_a_wheel_that_imports_is_kept(self) -> None:
        rc, out, calls = self.run_probe("installed")
        self.assertEqual(rc, 0, out)
        self.assertIn("STEP flash_attn flash-attn 2.8.3 imports; kept", out)
        self.assertNotIn("pip uninstall", calls)
        self.assertNotIn("WARN", out)
        self.assertTrue((self.state / "installed").exists())

    def test_the_nov_21_wheel_is_removed_with_its_error(self) -> None:
        rc, out, calls = self.run_probe("installed", "broken")
        self.assertEqual(rc, 0, out)
        warn = [line for line in out.splitlines() if line.startswith("WARN ")]
        self.assertEqual(len(warn), 1, out)
        self.assertIn("does not import against this ROCm torch; removing it", warn[0])
        self.assertIn(f"undefined symbol: {SYMBOL}", warn[0])
        self.assertIn("-m pip uninstall -y flash-attn", calls)
        self.assertIn("STEP flash_attn flash-attn 2.8.3 failed to import and was removed; vLLM will not import it",
                      out)
        self.assertFalse((self.state / "installed").exists())
        self.assertNotIn("DIE", out)

    def test_setup_dies_when_a_broken_wheel_stays_installed(self) -> None:
        rc, out, calls = self.run_probe("installed", "broken", "stuck")
        self.assertNotEqual(rc, 0, out)
        self.assertIn("DIE flash-attn 2.8.3 fails to import and could not be uninstalled", out)
        self.assertIn(f"undefined symbol: {SYMBOL}", out)
        self.assertIn("-m pip uninstall -y flash-attn", calls)
        self.assertNotIn("was removed", out)


class FlashAttnProbePlacementTests(unittest.TestCase):
    def test_probe_imports_what_vllm_imports(self) -> None:
        text = function_text()
        self.assertIn("import flash_attn.ops.triton.rotary", text)
        self.assertIn("except ModuleNotFoundError:", text)
        self.assertRegex(text, re.compile(r"^\s+import flash_attn$", re.M))
        self.assertIn("-m pip uninstall -y flash-attn", text)
        self.assertIn("find_spec('flash_attn')", text)

    def test_called_after_the_pth_write_and_before_the_vllm_gpu_check(self) -> None:
        text = skeleton()
        pth = text.index("'import vllm_rocm_bootstrap' > \"${site_pkg}/vllm_rocm_bootstrap.pth\"")
        call = text.index("\n    verify_vllm_flash_attn\n")
        check = text.index('gpu_check "Official vLLM ROCm wheel verification failed."')
        self.assertLess(pth, call)
        self.assertLess(call, check)
        self.assertEqual(text.count("\n    verify_vllm_flash_attn\n"), 1)

    def test_install_pin_and_extra_deps_exclusion_are_unchanged(self) -> None:
        text = skeleton()
        self.assertIn('"flash-attn==${FLASH_ATTN_VERSION}"', text)
        self.assertIn('"flash-attn", "flash_attn", "amd-aiter", "aiter", "amd-quark",', text)

    def test_skeleton_parses(self) -> None:
        done = subprocess.run([HOST_BASH, "-n", bash_path(SKELETON)], capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)

# ---------------------------------------------------------------------------
# What a user generates (TEMPLATE_00_150, 2026-11-22). A workspace generated from
# the published generator (v1.0.46) said "each pinned to its tested TEMPLATE_00_149
# release", described cloning the published bundle, carried about 65 generator-only
# files per workload, and showed 301-310 in a 101-132 bundle's --help.
# ---------------------------------------------------------------------------

sys.path.insert(0, str(ROOT / "scripts"))
import bundle_readme  # noqa: E402
import extract_benchmark_definition  # noqa: E402
import generator_files  # noqa: E402
import generator_version  # noqa: E402
import remove_template_copy  # noqa: E402
import results_markdown  # noqa: E402

PUBLISH_SCRIPT = ROOT / "user_scripts" / "publish_benchmarks_to_github.sh"
SUITE_MASTER = ROOT / "user_scripts" / "run_benchmark_suite.sh"
PREPARE = ROOT / "scripts" / "prepare_github_publish.sh"
GIT = shutil.which("git")
WORKLOAD_DIRS = {
    "1": ["101-sys-bench-amd-rocm-stack-validation-ubu2404", "107-sys-bench-amd-stream-ddr5-bandwidth-ubu2404"],
    "2": ["201-sys-bench-nvidia-cuda-stack-validation-ubu2404", "207-sys-bench-nvidia-stream-ddr5-bandwidth-ubu2404"],
    "3": ["301-sys-bench-amd-rocm-stack-validation-ubu2604", "307-sys-bench-amd-stream-ddr5-bandwidth-ubu2604"],
    "4": ["401-sys-bench-nvidia-cuda-stack-validation-ubu2604", "407-sys-bench-nvidia-stream-ddr5-bandwidth-ubu2604"],
}


class AnyTemplateNumberTests(unittest.TestCase):
    """Checks that named TEMPLATE_00_ now accept any TEMPLATE_NN_NNN, so 01_000 needs no code change."""

    def test_workbook_notes_with_any_template_number_are_stripped(self) -> None:
        strip = extract_benchmark_definition._strip_template_notes
        for note in ("TEMPLATE_00_79 2026-09-07: aligned to 112/312.", "TEMPLATE_01_003: aligned to 112/312."):
            with self.subTest(note=note):
                self.assertEqual(strip(f"4096. {note}").strip(" ."), "4096")
                self.assertIsNone(re.search(r"TEMPLATE_\d+_\d+", strip(f"4096 (see {note[:15]})")))

    def test_publish_and_self_checks_reject_any_template_number(self) -> None:
        for rel in ("scripts/self_check_generated_repo.sh", "scripts/check_github_publish_ready.sh"):
            with self.subTest(rel=rel):
                text = (ROOT / rel).read_text(encoding="utf-8")
                self.assertIn('re.search(r"TEMPLATE_\\d+_\\d+", path.read_text(encoding="utf-8"))', text)
                self.assertNotIn('"TEMPLATE_00_" in path', text)

    def test_nested_copy_patterns_accept_any_template_number(self) -> None:
        self.assertIn("TEMPLATE_*_copy/\n", (ROOT / ".gitignore").read_text(encoding="utf-8"))
        for rel in ("scripts/prepare_github_publish.sh", "scripts/check_github_publish_ready.sh"):
            with self.subTest(rel=rel):
                text = (ROOT / rel).read_text(encoding="utf-8")
                self.assertIn("TEMPLATE_*_copy", text)
                self.assertNotIn("TEMPLATE_00_*_copy", text)
        self.assertTrue(remove_template_copy.GENERATOR_COPY_NAME.fullmatch("TEMPLATE_01_000_copy"))
        self.assertTrue(remove_template_copy.GENERATOR_COPY_NAME.fullmatch("TEMPLATE_00_150_copy"))


@unittest.skipUnless(GIT, "git not available")
class ReleaseLabelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def git(self, *args: str) -> None:
        subprocess.run([GIT, "-C", str(self.tmp), *args], check=True, capture_output=True, text=True, timeout=30)

    def commit(self) -> None:
        self.git("init", "-q")
        (self.tmp / "VERSION").write_text("TEMPLATE_00_150\n", encoding="utf-8")
        self.git("add", "VERSION")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "c")

    def test_not_a_git_clone_is_a_development_build(self) -> None:
        self.assertEqual(generator_version.release_label(self.tmp), "")

    def test_template_tag_alone_is_not_a_release(self) -> None:
        self.commit()
        self.git("tag", "template-00-150")
        self.assertEqual(generator_version.release_label(self.tmp), "")

    def test_newest_release_tag_on_head(self) -> None:
        self.commit()
        for tag in ("template-00-149", "v1.0.9", "v1.0.46", "v1.0.10"):
            self.git("tag", tag)
        self.assertEqual(generator_version.release_label(self.tmp), "v1.0.46")


class WorkspaceReadmeTests(unittest.TestCase):
    def test_every_platform_names_the_release_and_no_bundle_install(self) -> None:
        for digit, names in WORKLOAD_DIRS.items():
            slug = bundle_readme.PLATFORMS[digit]["slug"]
            with self.subTest(platform=digit):
                text = bundle_readme.workspace_readme(names, release="v1.0.47", generator_root=ROOT)
                self.assertIn("generated with ai-agent-gpu-benchmark-repo-generator v1.0.47.", text)
                for absent in ("pinned to its tested", "git clone", "submodule", "describe --tags",
                               "Download ZIP", "@@RELEASE@@", slug):
                    self.assertNotIn(absent, text)
                self.assertIsNone(re.search(r"TEMPLATE_\d+_\d+", text))
                self.assertIn(f"scp -r {digit}[0-9][0-9]-* *.sh root@<address>:/opt/benchmarks/", text)
                self.assertIn(f"| {names[1][:3]} | [stream-ddr5-bandwidth]({names[1]}/) |", text)
                self.assertNotIn(f"https://github.com/{bundle_readme.ORG}/{names[0]}", text)
                self.assertIn("## Quick check\n", text)
                self.assertIn("## Update\n\nThese copies do not update themselves.", text)

    def test_development_build_wording(self) -> None:
        text = bundle_readme.workspace_readme(WORKLOAD_DIRS["1"], release="", generator_root=ROOT)
        self.assertIn("generated with a development build of ai-agent-gpu-benchmark-repo-generator.", text)

    def test_published_bundle_readme_is_unchanged(self) -> None:
        rows = "\n".join(bundle_readme.workload_row(n) for n in WORKLOAD_DIRS["1"]) + "\n"
        text = bundle_readme.render_bundle_readme("1", "bundle-amd-ubuntu-2404", "2", rows, org=bundle_readme.ORG,
                                                  version="v1.0.47", generator_root=ROOT)
        self.assertIn("each pinned to its tested v1.0.47 release.", text)
        self.assertIn("git clone --recurse-submodules", text)


class SuiteScriptCopyTests(unittest.TestCase):
    def test_generation_copy_is_the_published_bundle_copy(self) -> None:
        source = PUBLISH_SCRIPT.read_text(encoding="utf-8")
        match = re.search(r"^bundle_suite_script\(\) \{\n.*?^\}\n", source, re.S | re.M)
        self.assertIsNotNone(match)
        master = SUITE_MASTER.read_text(encoding="utf-8")
        for digit in "1234":
            with self.subTest(platform=digit):
                done = subprocess.run([HOST_BASH, "-c", match.group(0) + f'bundle_suite_script {digit} <"$1"',
                                       "t", bash_path(SUITE_MASTER)], capture_output=True, timeout=30)
                self.assertEqual(done.returncode, 0, done.stderr)
                ours = bundle_readme.bundle_suite_script_text(master, digit).encode("utf-8")
                self.assertEqual(ours, done.stdout)
                self.assertIn(f"Examples: {digit}01,{digit}07,{digit}21   {digit}01-{digit}10", ours.decode("utf-8"))


class GeneratorFilesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.prepare = PREPARE.read_text(encoding="utf-8")

    def test_list_is_publish_list(self) -> None:
        paths = generator_files.leftover_paths(self.prepare)
        for rel in ("AGENTS.md", "docs/AI_AGENT_INSTRUCTIONS.md", "docs/CHANGELOG.md", "scripts/create_one_workload.py",
                    "scripts/self_check_generated_repo.sh", "scripts/generator_files.py", ".claude", "scripts/remote"):
            self.assertIn(rel, paths)
        removals = generator_files.generation_removals(self.prepare)
        self.assertNotIn("docs/GENERATION_REPORT.md", removals)
        self.assertFalse([rel for rel in removals if rel.startswith("results/") or rel.endswith("_copy")])
        for kept in ("scripts/prepare_github_publish.sh", "scripts/check_github_publish_ready.sh",
                     "scripts/results_markdown.py", "run_setup.sh"):
            self.assertNotIn(kept, paths)

    def test_removes_generator_files_and_keeps_the_rest(self) -> None:
        repo = self.tmp / "107-sys-bench-amd-stream-ddr5-bandwidth-ubu2404"
        files = ["AGENTS.md", "docs/AI_AGENT_INSTRUCTIONS.md", "docs/GENERATION_REPORT.md", "docs/PRD.md",
                 "scripts/create_one_workload.py", "scripts/remote/host_bootstrap.sh", ".claude/CLAUDE.md",
                 "scripts/build_faiss_rocm.sh", "scripts/prepare_github_publish.sh", "results/generation_manifest.json",
                 "run_setup.sh", "run_benchmark.sh", "benchmark_specification.json", "README.md"]
        for rel in files:
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_text("x\n", encoding="utf-8")
        removed = generator_files.remove_generator_files(repo, ROOT)
        for rel in ("AGENTS.md", "docs/AI_AGENT_INSTRUCTIONS.md", "scripts/create_one_workload.py", "scripts/remote",
                    ".claude", "scripts/build_faiss_rocm.sh"):
            self.assertIn(rel, removed)
            self.assertFalse((repo / rel).exists(), rel)
        for rel in ("docs/GENERATION_REPORT.md", "docs/PRD.md", "scripts/prepare_github_publish.sh",
                    "results/generation_manifest.json", "run_setup.sh", "README.md"):
            self.assertTrue((repo / rel).is_file(), rel)
        self.assertEqual(generator_files.remove_generator_files(repo, ROOT), [])

    def test_rag_workload_keeps_the_faiss_builder(self) -> None:
        repo = self.tmp / "132-gpu-bench-amd-rag-faiss-end2end-ubu2404"
        (repo / "scripts").mkdir(parents=True)
        (repo / "scripts" / "build_faiss_rocm.sh").write_text("x\n", encoding="utf-8")
        (repo / "run_setup.sh").write_text("bash scripts/build_faiss_rocm.sh  # FAISS\n", encoding="utf-8")
        generator_files.remove_generator_files(repo, ROOT)
        self.assertTrue((repo / "scripts" / "build_faiss_rocm.sh").is_file())

    def test_driver_removes_them_after_a_pass_here_and_on_the_vm(self) -> None:
        text = (ROOT / "scripts" / "create_one_workload.py").read_text(encoding="utf-8")
        self.assertIn("        if rc == 0:\n            finish_generator_files(repo, template_root, args, ssh)\n"
                      "        return rc", text)
        self.assertIn("script = remote_cleanup_script(repo.name, removed)", text)  # TEMPLATE_01_000
        self.assertIn("if [ -f scripts/self_check_generated_repo.sh ]; then\n  bash scripts/self_check_generated_repo.sh",
                      text)


class ResultsReferenceHeaderTests(unittest.TestCase):
    def test_no_template_number_and_no_maintainer(self) -> None:
        actual = ("# Results: 107 STREAM\n\nLatest run of each profile on this machine.\n\n"
                  "<!-- profile:smoke -->\n## smoke\n\n- **Run:** x · status **PASS** (exit 0)\n<!-- /profile:smoke -->\n")
        page = results_markdown.reference_from_actual(actual, template_version="TEMPLATE_00_150",
                                                      generated="2026-11-22", profiles=("smoke",))
        self.assertIn("Reference results from the validation run on the system shown in each section "
                      "(recorded 2026-11-22).", page)
        self.assertNotIn("TEMPLATE_00_150", page)
        self.assertNotIn("maintainer", page)

if __name__ == "__main__":
    unittest.main()
