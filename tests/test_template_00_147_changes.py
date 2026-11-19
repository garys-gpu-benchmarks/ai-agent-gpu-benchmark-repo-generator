#!/usr/bin/env python3
# File: tests/test_template_00_147_changes.py
# Description: TEMPLATE_00_147 checks: the generator's tests pass in a published
#   clone, which has no docs/OPEN_ISSUES.md (gitignored, deleted by publish step 9);
#   generation writes nothing above the project root, so the three laptop tools
#   have one local copy, in the project root (OPEN_ISSUES A8). 2026-11-19: setup waits
#   for apt/dpkg locks (A7); 101/301 fail when no GPU answers; the PMU warning says
#   "may" (A2); "none" is written (A4); preflight prints the ssh-keygen -R fix;
#   the profile README copy has System Requirements (D1); tests start Git Bash (T1).
# Execution: python3 -m unittest tests/test_template_00_147_changes.py
"""TEMPLATE_00_147 change checks."""

from __future__ import annotations

import contextlib
import importlib.util
import inspect
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPEN_ISSUES = "docs/OPEN_ISSUES.md"
LAPTOP_TOOLS = ("get_benchmark_results.sh", "list_runs.sh", "show_metrics.sh")
sys.path.insert(0, str(ROOT / "scripts"))

import create_generated_repo  # noqa: E402


def load_00_145_tests():
    """Load tests/test_template_00_145_changes.py as a fresh module."""
    path = ROOT / "tests" / "test_template_00_145_changes.py"
    spec = importlib.util.spec_from_file_location("template_00_145_published_clone", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PublishedCloneTests(unittest.TestCase):
    def test_open_issues_is_gitignored(self) -> None:
        self.assertIn(OPEN_ISSUES, (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines())

    def test_00_145_doc_check_passes_without_open_issues(self) -> None:
        # The v1.0.43 Template CI failed here with FileNotFoundError: the test
        # read docs/OPEN_ISSUES.md, which a published clone never has.
        module = load_00_145_tests()
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            for rel in module.DOC_FILES:
                (tree / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / rel, tree / rel)
            self.assertFalse((tree / OPEN_ISSUES).exists())
            module.ROOT = tree
            case = module.PublishDoesNotTakeTheProjectRootTests(
                "test_docs_list_the_bundle_root_as_project_root_output"
            )
            result = unittest.TestResult()
            case.run(result)
        problems = [text for _, text in result.errors + result.failures]
        self.assertEqual(problems, [], "\n".join(problems))

    def test_no_test_reads_open_issues_without_a_guard(self) -> None:
        reads = re.compile(r"\.read_(text|bytes)\(|\bopen\(")
        offenders = []
        for path in sorted((ROOT / "tests").glob("test_*.py")):
            if path.name == Path(__file__).name:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "OPEN_ISSUES.md" in line and reads.search(line):
                    offenders.append(f"{path.name}:{number}: {line.strip()}")
        self.assertEqual(offenders, [], "read docs/OPEN_ISSUES.md only after checking it exists")


class NothingAboveProjectRootTests(unittest.TestCase):
    """OPEN_ISSUES A8: the laptop tools were copied to the project root and to the
    folder above it, and a user edit in one place left the other copy behind."""

    def test_generation_has_no_step_that_writes_above_the_project_root(self) -> None:
        self.assertFalse(hasattr(create_generated_repo, "install_operator_tools"))
        self.assertFalse(hasattr(create_generated_repo, "OPERATOR_TOOLS"))
        source = inspect.getsource(create_generated_repo)
        self.assertIsNone(re.search(r"project_root\.parent(?!s)", source))
        main = inspect.getsource(create_generated_repo.main)
        self.assertIn("install_project_root_bundle(source_root, project_root)", main)

    def test_laptop_tools_land_only_in_the_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / "gpu-bench"
            project = parent / "workspace"
            (project / "107-sys-bench-amd-stream-ddr5-bandwidth-ubu2404").mkdir(parents=True)
            with contextlib.redirect_stdout(io.StringIO()):
                create_generated_repo.install_project_root_bundle(ROOT, project)
            self.assertEqual(sorted(path.name for path in parent.iterdir()), ["workspace"])
            for name in LAPTOP_TOOLS:
                with self.subTest(name=name):
                    expected = (ROOT / "user_scripts" / name).read_bytes().replace(b"\r\n", b"\n")
                    self.assertEqual((project / name).read_bytes(), expected)

    def test_docs_say_nothing_is_written_above_the_project_root(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Generation writes nothing outside `workspace/`", readme)
        self.assertIn("Nothing is written above the project root", readme)
        self.assertNotIn("one level above", readme)
        self.assertNotIn("```text\ngpu-bench/\n", readme)
        self.assertIn("```text\nworkspace/\n", readme)
        template = (ROOT / "docs/repository-template.md").read_text(encoding="utf-8")
        self.assertIn("Nothing is written above the project root", template)
        self.assertNotIn("still also copied", template)



# ---------------------------------------------------------------------------
# 2026-11-19: A7, 101/301 GPU probes, A2, A4, preflight host key, D1, T1.
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).resolve().parent))
from host_bash import HOST_BASH, bash_path, path_first  # noqa: E402

APT_LIB = ROOT / "scripts" / "lib" / "apt_mirror_fallback.sh"
NVIDIA_SETUPS = (
    "scripts/templates/setup_nvidia_skeleton.sh",
    "implementation_components/sglang-prompt-response-nvidia/files/run_setup.sh",
    "implementation_components/vllm-kvcache-nvidia/files/run_setup.sh",
    "implementation_components/vllm-throughput-nvidia/files/run_setup.sh",
    "implementation_components/vllm-token-generation-nvidia/files/run_setup.sh",
)
WAIT_LINE = "declare -f wait_for_apt_locks >/dev/null 2>&1 && { wait_for_apt_locks || true; }"


def run_apt_lib(tmp: str, body: str, holder_calls_busy: int, **env: str) -> subprocess.CompletedProcess:
    """Source the apt library with _apt_lock_holder replaced: busy for the first N calls."""
    program = f"""
set -u
source "$1"
COUNT_FILE="$2/count"
echo 0 > "$COUNT_FILE"
_apt_lock_holder() {{
  local n; n=$(( $(cat "$COUNT_FILE") + 1 )); echo "$n" > "$COUNT_FILE"
  if (( n <= {holder_calls_busy} )); then echo "4242 unattended-upgr"; fi
}}
{body}
echo "rc=$? calls=$(cat "$COUNT_FILE")"
"""
    full_env = dict(os.environ, BENCHMARK_APT_LOCK_POLL_SEC="0", **env)
    return subprocess.run([HOST_BASH, "-c", program, "test", bash_path(APT_LIB), bash_path(tmp)],
                          capture_output=True, text=True, timeout=60, env=full_env)


class AptLockWaitTests(unittest.TestCase):
    """OPEN_ISSUES A7: setup waits for another apt/dpkg process before its first apt step."""

    def test_waits_until_the_lock_is_free_and_names_the_pid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            done = run_apt_lib(tmp, "wait_for_apt_locks", holder_calls_busy=2)
        self.assertIn("rc=0 calls=3", done.stdout, done.stderr)
        self.assertIn("Waiting up to 300 s for another apt/dpkg process to finish (PID 4242 unattended-upgr)", done.stderr)
        self.assertIn("apt/dpkg is free after", done.stdout)

    def test_gives_up_after_the_limit_and_says_so(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            done = run_apt_lib(tmp, "wait_for_apt_locks", holder_calls_busy=1000,
                               BENCHMARK_APT_LOCK_WAIT_SEC="3")
        self.assertRegex(done.stdout, r"rc=1 calls=\d+", done.stderr)
        self.assertIn("is still running after 3 s; continuing", done.stderr)

    def test_zero_disables_the_wait(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            done = run_apt_lib(tmp, "wait_for_apt_locks", holder_calls_busy=1000,
                               BENCHMARK_APT_LOCK_WAIT_SEC="0")
        self.assertIn("rc=0 calls=0", done.stdout, done.stderr)

    def test_mirror_check_waits_first_even_when_it_skips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            done = run_apt_lib(tmp, "ensure_ubuntu_apt_mirror", holder_calls_busy=1,
                               BENCHMARK_APT_MIRROR_FALLBACK="0")
        self.assertIn("rc=2 calls=2", done.stdout, done.stderr)

    def test_setups_that_run_apt_before_the_mirror_check_wait_too(self) -> None:
        for rel in NVIDIA_SETUPS:
            with self.subTest(rel=rel):
                text = (ROOT / rel).read_text(encoding="utf-8")
                self.assertIn(WAIT_LINE + "\nnvidia_pin_host_driver\n", text)
        cpu = (ROOT / "scripts/templates/setup_cpu_system_skeleton.sh").read_text(encoding="utf-8")
        first_wait = cpu.index("wait_for_apt_locks || true")
        self.assertLess(first_wait, cpu.index("apt-get install -y python3"))
        self.assertLess(cpu.index('source "${REPO_ROOT}/scripts/lib/apt_mirror_fallback.sh"'), first_wait)


SYSTEM_CONFIG = ROOT / "implementation_components" / "system-config-amd" / "files" / "scripts" / "collect_workload.py"


def load_system_config():
    spec = importlib.util.spec_from_file_location("system_config_amd_00_147", SYSTEM_CONFIG)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@unittest.skipIf(sys.platform == "win32", "the collector reads os.uname(); it runs only on the Linux VM")
class SystemConfigGpuProbeTests(unittest.TestCase):
    """101/301 fail when rocminfo and amd-smi static both fail (no usable GPU)."""

    def run_collector(self, codes: dict[str, int]) -> tuple[int, str, Path]:
        module = load_system_config()

        def fake_run(command):
            key = " ".join(command)
            code = codes.get(key, 0)
            return code, "ROCm version: 10.1.0\n" if code == 0 else "error\n"

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        config = tmp / "benchmark_config.yaml"
        config.write_text("sweep:\n  rocm_version: 10.1.0\n  permissions_check: false\n  required_packages: amdrocm-base10.1\n",
                          encoding="utf-8")
        raw = tmp / "run" / "raw_output.txt"
        argv = ["collect_workload.py", "--run-dir", str(tmp / "run"), "--raw-file", str(raw), "--config", str(config)]
        stderr = io.StringIO()
        with unittest.mock.patch.object(module, "run_command", fake_run), \
                unittest.mock.patch.object(module, "package_version", lambda name: "10.1.0"), \
                unittest.mock.patch.object(module, "driver_package_matches", lambda expected: True), \
                unittest.mock.patch.object(module, "firmware_revision", lambda: ""), \
                unittest.mock.patch.object(sys, "argv", argv), contextlib.redirect_stderr(stderr):
            rc = module.main()
        return rc, stderr.getvalue(), raw

    def test_both_gpu_probes_failing_fails_the_run(self) -> None:
        rc, err, raw = self.run_collector({"rocminfo": 1, "amd-smi static": 2})
        self.assertEqual(rc, 1)
        self.assertIn("[FAIL] No AMD GPU answered: rocminfo exited 1 and amd-smi static exited 2.", err)
        self.assertTrue(raw.is_file(), "the probe rows are still written for the diagnosis")

    def test_one_gpu_probe_answering_still_passes(self) -> None:
        for codes in ({"rocminfo": 1}, {"amd-smi static": 1}, {}):
            with self.subTest(codes=codes):
                rc, err, _raw = self.run_collector(codes)
                self.assertEqual(rc, 0, err)
                self.assertNotIn("No AMD GPU answered", err)


class PmuWarningWordingTests(unittest.TestCase):
    """OPEN_ISSUES A2: a generic perf usually still reads the counters (311 measured all five)."""

    def test_warning_says_may_not_will(self) -> None:
        for rel in ("scripts/templates/setup_cpu_system_skeleton.sh", "scripts/templates/setup_nvidia_skeleton.sh"):
            with self.subTest(rel=rel):
                text = (ROOT / rel).read_text(encoding="utf-8")
                self.assertNotIn("PMU metrics will be na", text)
                self.assertEqual(text.count("PMU metrics may be na if the generic perf cannot read the counters"), 2)


class NoneIsWrittenTests(unittest.TestCase):
    """OPEN_ISSUES A4: transient_retry and generator_repairs.md say "none" instead of being absent."""

    def test_attempt_without_a_retry_says_none(self) -> None:
        import create_one_workload as col

        with tempfile.TemporaryDirectory() as tmp:
            col.record(Path(tmp), "101", "r", "passed", "2026-11-19T00:00:00Z", "2026-11-19T00:01:00Z", "")
            row = json.loads((Path(tmp) / "batch_generation_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(row["repositories"][0]["attempts"][0]["transient_retry"], "none")

    def test_repair_log_exists_and_says_none_until_the_first_entry(self) -> None:
        import log_generator_repair as repairs

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = repairs.ensure_log(root)
            self.assertIn("(none)", path.read_text(encoding="utf-8"))
            self.assertEqual(repairs.read_entries(root), [])
            repairs.ensure_log(root)  # a second batch start changes nothing
            repairs.append_entry(root, "scripts/x.py", "why", "101")
            text = path.read_text(encoding="utf-8")
        self.assertNotIn("(none)", text)
        self.assertEqual(text.count("| 101 | scripts/x.py | why"), 1)

    def test_batch_start_creates_the_log(self) -> None:
        text = (ROOT / "scripts" / "run_from_prompt.py").read_text(encoding="utf-8")
        self.assertLess(text.index("ensure_log(template_root)"), text.index("repairs_before = len(read_entries(template_root))"))


class PreflightHostKeyTests(unittest.TestCase):
    """A VM rebuilt at the same address: preflight prints the ssh-keygen -R fix."""

    def test_hint_names_the_host_and_port(self) -> None:
        import remote_host_preflight as rhp

        failed = "Host key verification failed.\n"
        self.assertIn("ssh-keygen -R gpu-vm ", rhp.host_key_hint("ssh -i key root@gpu-vm", failed))
        self.assertIn("ssh-keygen -R [gpu-vm]:2222 ", rhp.host_key_hint("ssh -p 2222 root@gpu-vm", failed))
        self.assertIn("ssh-keygen -R <host> ", rhp.host_key_hint("ssh root@gpu-vm", failed, show_host=False))
        self.assertEqual(rhp.host_key_hint("ssh root@gpu-vm", "Permission denied (publickey)."), "")

    def test_preflight_prints_the_host_but_records_a_placeholder(self) -> None:
        import subprocess as sp

        import remote_host_preflight as rhp

        def fake_ssh_run(ssh, script, timeout=60):
            return sp.CompletedProcess(["ssh"], 255, "", "Host key verification failed.\r\n")

        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                report = rhp.run_preflight(fake_ssh_run, "ssh -i key root@gpu-vm", ["101"], ROOT, Path(tmp))
            manifest = (Path(tmp) / "batch_generation_manifest.json").read_text(encoding="utf-8")
        self.assertEqual(report["status"], "host_key_changed")
        self.assertIn("ssh-keygen -R gpu-vm ", out.getvalue())
        self.assertIn("ssh-keygen -R <host> ", manifest)
        self.assertNotIn("gpu-vm", manifest)


class ProfileReadmeCopyTests(unittest.TestCase):
    """OPEN_ISSUES D1: the doc copy carries the live page's System Requirements."""

    def test_system_requirements_section(self) -> None:
        text = (ROOT / "docs" / "github-profile-README.md").read_text(encoding="utf-8")
        section = text[text.index("## System Requirements"):text.index("## Install on a GPU Host")]
        for needle in ("Ubuntu 24.04 LTS or 26.04 LTS", "installs ROCm (10.1.0)", "installs CUDA (13.3)",
                       "250 Mbit/s minimum", "runpod-getting-started.md"):
            self.assertIn(needle, section)


class WindowsTestSuiteTests(unittest.TestCase):
    """OPEN_ISSUES T1: tests start Git Bash on Windows and skip only Linux-only collectors there."""

    # host_bash.py names the pattern in its comment; test_template_00_146 holds the regex.
    ALLOWED = {"host_bash.py", "test_template_00_146_changes.py"}

    def test_no_test_launches_a_bare_bash(self) -> None:
        bare = re.compile(r'\[\s*"bash"\s*,')
        for path in sorted((ROOT / "tests").glob("*.py")):
            if path.name in self.ALLOWED:
                continue
            with self.subTest(test=path.name):
                self.assertIsNone(bare.search(path.read_text(encoding="utf-8")), path.name)

    def test_files_using_host_bash_import_it(self) -> None:
        for path in sorted((ROOT / "tests").glob("test_*.py")):
            text = path.read_text(encoding="utf-8")
            if "HOST_BASH," in text or "HOST_BASH]" in text:
                with self.subTest(test=path.name):
                    self.assertIn("from host_bash import HOST_BASH", text)

    def test_stand_in_tools_go_first_inside_the_script(self) -> None:
        # Git's bash.exe puts /mingw64/bin first, so a stand-in curl on the env PATH lost to
        # Git's curl.exe and the tests downloaded from the internet (T1 round 2).
        for name in ("test_nvidia_cuda_toolkit.py", "test_template_00_130_docs.py",
                     "test_template_00_131_changes.py"):
            with self.subTest(test=name):
                self.assertIn("path_first(", (ROOT / "tests" / name).read_text(encoding="utf-8"))
        text = (ROOT / "tests" / "test_template_00_119_host_robustness.py").read_text(encoding="utf-8")
        self.assertIn('export PATH="{bash_path(fake_bin)}:$PATH"', text)

    def test_windows_skips_name_the_linux_vm(self) -> None:
        skips = {
            "test_linux_perf_pmu.py": "class LinuxPerfPmuCollectorTest",
            "test_system_stress_nvidia.py": "class SystemStressNvidiaCollectorTest",
            "test_metric_fixes_20261019.py": "class NcclSingleGpu",
            "test_template_00_129_changes.py": "class FioTargetGuardTest",
            "test_template_00_135_changes.py": "def test_suite_id_pass_and_download",
            "test_batch_generation_tooling.py": "def test_cr_rewrite_touches_only_files_with_cr",
        }
        for name, target in skips.items():
            with self.subTest(test=name):
                text = (ROOT / "tests" / name).read_text(encoding="utf-8")
                before = text[:text.index(target)].rstrip().splitlines()[-1]
                self.assertIn('@unittest.skipIf(sys.platform == "win32"', before)
                self.assertIn("Linux VM", before)



# ---------------------------------------------------------------------------
# 2026-11-19 (Project556): the boot-time helper unattended-upgrade-shutdown is not apt.
# ---------------------------------------------------------------------------

# (expected "PID NAME" or "", one ps -eo pid=,comm=,args= line). The first line is the
# helper exactly as it ran on the 556 VM; the last three only mention the updater.
PROCESS_CASES = (
    ("", "1281 unattended-upgr /usr/bin/python3 /usr/share/unattended-upgrades/unattended-upgrade-shutdown --wait-for-signal"),
    ("", "1281 python3 /usr/bin/python3 /usr/share/unattended-upgrades/unattended-upgrade-shutdown --wait-for-signal"),
    ("4242 unattended-upgrade", "4242 unattended-upgr /usr/bin/python3 /usr/bin/unattended-upgrade"),
    ("4243 unattended-upgrade", "4243 unattended-upgr /usr/bin/python3 /usr/bin/unattended-upgrade --download-only"),
    ("4244 unattended-upgrade", "4244 python3 /usr/bin/python3 -u /usr/bin/unattended-upgrade -d"),
    ("4245 unattended-upgrade", "4245 unattended-upgr /usr/bin/unattended-upgrade"),
    ("5000 apt-get", "5000 apt-get apt-get update -y"),
    ("5001 apt", "5001 apt apt install -y fio"),
    ("5002 dpkg", "5002 dpkg /usr/bin/dpkg --status-fd 23 --configure --pending"),
    ("", "5003 dpkg-query dpkg-query -W -f=${Version} amdgpu-dkms"),
    ("", "5004 apt.systemd.dai /bin/sh /usr/lib/apt/apt.systemd.daily update"),
    ("", "6000 bash bash run_setup.sh --assume-yes"),
    ("", "7000 bash /usr/bin/bash -c echo /usr/bin/python3 /usr/bin/unattended-upgrade"),
    ("", "7001 grep grep unattended-upgrade /var/log/syslog"),
    ("", "7002 bwrap bwrap --new-session --setenv X 1 /usr/bin/unattended-upgrade"),
)
HELPER_LINE = PROCESS_CASES[0][1]


def fake_ps_dir(tmp: str, lines: list[str], pgrep_lines: list[str] | None = None) -> Path:
    """A bin folder whose ps prints these lines (and pgrep, if given, prints pgrep_lines)."""
    bindir = Path(tmp) / "bin"
    bindir.mkdir(exist_ok=True)
    listing = Path(tmp) / "ps.txt"
    listing.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    (bindir / "ps").write_text(f'#!/usr/bin/env bash\ncat "{bash_path(listing)}"\n', encoding="utf-8")
    pg = Path(tmp) / "pgrep.txt"
    pg.write_text("".join(f"{line}\n" for line in (pgrep_lines or [])), encoding="utf-8")
    (bindir / "pgrep").write_text(f'#!/usr/bin/env bash\ncat "{bash_path(pg)}"\n', encoding="utf-8")
    for tool in ("ps", "pgrep"):
        (bindir / tool).chmod(0o755)
    return bindir


class AptBusyFilterTests(unittest.TestCase):
    """Only processes that use apt count; the shutdown helper never does (Project556, 2026-11-19)."""

    def run_filter(self, awk_bin: str | None) -> list[tuple[str, str, str]]:
        wrong = []
        for want, line in PROCESS_CASES:
            prefix = f"awk() {{ {awk_bin} \"$@\"; }}; " if awk_bin else ""
            done = subprocess.run([HOST_BASH, "-c", f'source "$1"; {prefix}_apt_lock_holder_filter', "t", bash_path(APT_LIB)],
                                  input=line + "\n", capture_output=True, text=True, timeout=30)
            if done.stdout.strip() != want:
                wrong.append((want, done.stdout.strip(), line))
        return wrong

    def test_every_case_with_the_default_awk(self) -> None:
        self.assertEqual(self.run_filter(None), [])

    @unittest.skipIf(shutil.which("mawk") is None, "mawk (Ubuntu's default awk) is not installed here")
    def test_every_case_with_mawk_ubuntus_default_awk(self) -> None:
        self.assertEqual(self.run_filter("mawk"), [])

    def test_the_generator_uses_the_identical_filter(self) -> None:
        import create_one_workload as col

        self.assertIn("awk '" + col.APT_BUSY_AWK + "'", APT_LIB.read_text(encoding="utf-8"))
        self.assertNotIn("unattended-upgr'", APT_LIB.read_text(encoding="utf-8"))
        self.assertNotIn("pgrep -f unattended-upgr", (ROOT / "scripts" / "create_one_workload.py").read_text(encoding="utf-8"))

    def test_setup_does_not_wait_for_the_helper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bindir = fake_ps_dir(tmp, [HELPER_LINE, "6000 bash bash run_setup.sh --assume-yes"])
            program = f'{path_first(bindir)}source "$1"; wait_for_apt_locks; echo "rc=$?"'
            done = subprocess.run([HOST_BASH, "-c", program, "t", bash_path(APT_LIB)], capture_output=True, text=True,
                                  timeout=30, env=dict(os.environ, BENCHMARK_APT_LOCK_WAIT_SEC="2", BENCHMARK_APT_LOCK_POLL_SEC="1"))
        self.assertIn("rc=0", done.stdout, done.stderr)
        self.assertNotIn("Waiting", done.stderr)

    def test_setup_still_waits_for_dpkg(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bindir = fake_ps_dir(tmp, [HELPER_LINE, "5002 dpkg /usr/bin/dpkg --configure --pending"])
            program = f'{path_first(bindir)}source "$1"; wait_for_apt_locks; echo "rc=$?"'
            done = subprocess.run([HOST_BASH, "-c", program, "t", bash_path(APT_LIB)], capture_output=True, text=True,
                                  timeout=30, env=dict(os.environ, BENCHMARK_APT_LOCK_WAIT_SEC="1", BENCHMARK_APT_LOCK_POLL_SEC="1"))
        self.assertIn("rc=1", done.stdout, done.stderr)
        self.assertIn("(PID 5002 dpkg)", done.stderr)

    def test_retry_check_is_idle_with_only_the_helper(self) -> None:
        import create_one_workload as col

        name = "103-sys-bench-amd-system-stress-stability-ubu2404"
        own_setup = f"7100 bash {col.REMOTE_ROOT}/{name}/run_setup.sh --assume-yes"
        other_setup = f"7101 bash {col.REMOTE_ROOT}/104-other/run_setup.sh --assume-yes"
        cases = (
            ("IDLE", [HELPER_LINE], []),
            ("IDLE", [HELPER_LINE], [other_setup]),
            ("BUSY", [HELPER_LINE, "5000 apt-get apt-get install -y gfortran"], []),
            ("BUSY", ["4242 unattended-upgr /usr/bin/python3 /usr/bin/unattended-upgrade"], []),
            ("BUSY", [HELPER_LINE], [own_setup]),
        )
        for want, ps_lines, pgrep_lines in cases:
            with self.subTest(want=want, ps=ps_lines, pgrep=pgrep_lines), tempfile.TemporaryDirectory() as tmp:
                bindir = fake_ps_dir(tmp, ps_lines, pgrep_lines)
                done = subprocess.run([HOST_BASH, "-c", path_first(bindir) + col.remote_idle_script(name)],
                                      capture_output=True, text=True, timeout=30)
                self.assertEqual(done.stdout.strip(), want, done.stderr)


if __name__ == "__main__":
    unittest.main()
