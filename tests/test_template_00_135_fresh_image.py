#!/usr/bin/env python3
# File: tests/test_template_00_135_fresh_image.py
# Description: TEMPLATE_00_135 fresh-image fixes. The Ubuntu apt mirror fallback
#   (scripts/lib/apt_mirror_fallback.sh) against stand-in sources files and a
#   stand-in apt-get, and its use before the first apt step of every setup path
#   and the host bootstrap; the bootstrap leaving the NVIDIA CUDA toolkit to
#   setup (BENCHMARK_BOOTSTRAP_CUDA=1 restores it); /etc/profile.d/cuda-benchmark.sh;
#   batch_remote_output.log kept by the root cleanup; clean-image docs that copy
#   the local repositories. No network, no root, no change to this machine.
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "scripts" / "lib"
MIRROR = LIB / "apt_mirror_fallback.sh"
BASH = shutil.which("bash")

DEB822 = """Types: deb
URIs: http://atl.mirrors.example.net/ubuntu/
Suites: noble noble-updates noble-backports
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

Types: deb
URIs: http://security.ubuntu.com/ubuntu/
Suites: noble-security
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
"""
ONE_LINE = (
    "deb [signed-by=/etc/apt/keyrings/rocm.gpg] https://repo.radeon.com/rocm/apt/7.1 noble main\n"
    "deb http://atl.mirrors.example.net/ubuntu noble-updates main universe\n"
)
# Fails (per FAKE_APT_MODE) while any sources file still names the image mirror.
FAKE_APT = """#!/usr/bin/env bash
echo "$*" >> "${FAKE_APT_LOG}"
if cat ${FAKE_APT_SOURCES} | grep -q atl.mirrors.example.net; then
  case "${FAKE_APT_MODE}" in
    ipv6)
      echo "Err:1 http://atl.mirrors.example.net/ubuntu noble InRelease"
      echo "  Cannot initiate the connection to atl.mirrors.example.net:80 (2001:db8::1). - connect (101: Network is unreachable)"
      echo "W: Failed to fetch http://atl.mirrors.example.net/ubuntu/dists/noble/InRelease  Cannot initiate the connection"
      echo "W: Some index files failed to download. They have been ignored, or old ones used instead."
      exit 0 ;;
    503)
      echo "E: Failed to fetch http://atl.mirrors.example.net/ubuntu/dists/noble/InRelease  503  Service Unavailable"
      exit 100 ;;
    lock)
      echo "E: Could not get lock /var/lib/apt/lists/lock. It is held by process 42 (apt-get)"
      exit 100 ;;
    archive-down)
      echo "E: Failed to fetch http://atl.mirrors.example.net/ubuntu/dists/noble/InRelease  503  Service Unavailable"
      exit 100 ;;
  esac
fi
if [[ "${FAKE_APT_MODE}" == "archive-down" ]]; then
  echo "E: Failed to fetch http://archive.ubuntu.com/ubuntu/dists/noble/InRelease  Temporary failure resolving 'archive.ubuntu.com'"
  exit 100
fi
echo "Hit:1 http://archive.ubuntu.com/ubuntu noble InRelease"
exit 0
"""


@unittest.skipIf(BASH is None, "bash is not installed")
class AptMirrorFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.deb822 = self.tmp / "ubuntu.sources"
        self.one_line = self.tmp / "sources.list"
        self.deb822.write_text(DEB822, encoding="utf-8")
        self.one_line.write_text(ONE_LINE, encoding="utf-8")
        self.os_release = self.tmp / "os-release"
        self.os_release.write_text('NAME="Ubuntu"\nID=ubuntu\nVERSION_ID="24.04"\n', encoding="utf-8")
        self.state = self.tmp / "state"
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        apt = bin_dir / "apt-get"
        apt.write_text(FAKE_APT, encoding="utf-8")
        apt.chmod(apt.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        self.apt_log = self.tmp / "apt.log"
        self.env = dict(
            os.environ,
            PATH=f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            FAKE_APT_LOG=str(self.apt_log),
            FAKE_APT_SOURCES=f"{self.deb822} {self.one_line}",
            APT_MIRROR_SOURCES_FILES=f"{self.deb822} {self.one_line}",
            APT_MIRROR_OS_RELEASE=str(self.os_release),
            BENCHMARK_HOST_STATE_DIR=str(self.state),
            BENCHMARK_APT_FALLBACK_ARCHIVE="http://archive.ubuntu.com/ubuntu/",
        )
        self.env.pop("BENCHMARK_APT_MIRROR_FALLBACK", None)

    def run_helper(self, mode: str, body: str = "ensure_ubuntu_apt_mirror; echo rc=$?", **extra: str):
        script = f'run_noninteractive_root() {{ "$@"; }}\nsource "{MIRROR.as_posix()}"\n{body}\n'
        env = dict(self.env, FAKE_APT_MODE=mode, **extra)
        return subprocess.run([BASH, "-c", script], cwd=self.tmp, env=env, capture_output=True, text=True, timeout=60)

    def rc(self, result) -> int:
        lines = [line for line in result.stdout.splitlines() if line.startswith("rc=")]
        self.assertTrue(lines, result.stdout + result.stderr)
        return int(lines[-1][3:])

    def apt_calls(self) -> int:
        return len(self.apt_log.read_text(encoding="utf-8").splitlines()) if self.apt_log.exists() else 0

    def test_lists_only_third_party_ubuntu_mirrors(self) -> None:
        result = self.run_helper("ok", "ubuntu_mirror_uris")
        self.assertEqual(result.stdout.split(), [
            "http://atl.mirrors.example.net/ubuntu", "http://atl.mirrors.example.net/ubuntu/"])

    def assert_switched(self) -> None:
        deb822 = self.deb822.read_text(encoding="utf-8")
        self.assertIn("URIs: http://archive.ubuntu.com/ubuntu/\n", deb822)
        self.assertIn("URIs: http://security.ubuntu.com/ubuntu/\n", deb822)
        self.assertNotIn("atl.mirrors", deb822)
        one_line = self.one_line.read_text(encoding="utf-8")
        self.assertIn("deb http://archive.ubuntu.com/ubuntu/ noble-updates main universe\n", one_line)
        self.assertIn("https://repo.radeon.com/rocm/apt/7.1 noble main", one_line)
        backups = list((self.state / "apt-sources-backup").glob("*/*"))
        self.assertEqual(sorted(p.name for p in backups), ["sources.list", "ubuntu.sources"])
        backup = next(p for p in backups if p.name == "ubuntu.sources")
        self.assertEqual(backup.read_text(encoding="utf-8"), DEB822)
        self.assertIn("atl.mirrors.example.net", (self.state / "apt_mirror_fallback.txt").read_text(encoding="utf-8"))
        self.assertTrue((self.state / "apt_updated_epoch").is_file())

    def test_ipv6_only_mirror_warns_with_exit_0_and_is_switched(self) -> None:
        result = self.run_helper("ipv6")
        self.assertEqual(self.rc(result), 0, result.stdout + result.stderr)
        self.assert_switched()
        self.assertEqual(self.apt_calls(), 2)
        self.assertIn("switching to http://archive.ubuntu.com/ubuntu/", result.stdout)

    def test_503_mirror_is_switched(self) -> None:
        result = self.run_helper("503")
        self.assertEqual(self.rc(result), 0, result.stdout + result.stderr)
        self.assert_switched()

    def test_working_mirror_is_left_alone_and_checked_once(self) -> None:
        result = self.run_helper("ok", "ensure_ubuntu_apt_mirror; echo rc=$?; ensure_ubuntu_apt_mirror; echo rc=$?")
        self.assertEqual([line for line in result.stdout.splitlines() if line.startswith("rc=")], ["rc=0", "rc=2"])
        self.assertEqual(self.deb822.read_text(encoding="utf-8"), DEB822)
        self.assertEqual(self.apt_calls(), 1)
        self.assertFalse((self.state / "apt-sources-backup").exists())

    def test_other_apt_failure_changes_nothing(self) -> None:
        result = self.run_helper("lock")
        self.assertEqual(self.rc(result), 1)
        self.assertEqual(self.deb822.read_text(encoding="utf-8"), DEB822)
        self.assertEqual(self.one_line.read_text(encoding="utf-8"), ONE_LINE)

    def test_still_failing_after_switch_returns_1(self) -> None:
        result = self.run_helper("archive-down")
        self.assertEqual(self.rc(result), 1)
        self.assertIn("still fails after switching", result.stderr)

    def test_skips(self) -> None:
        self.assertEqual(self.rc(self.run_helper("503", BENCHMARK_APT_MIRROR_FALLBACK="0")), 2)
        self.os_release.write_text("ID=debian\n", encoding="utf-8")
        self.assertEqual(self.rc(self.run_helper("503")), 2)
        self.os_release.write_text('ID="ubuntu"\n', encoding="utf-8")
        self.deb822.write_text(DEB822.replace("atl.mirrors.example.net", "archive.ubuntu.com"), encoding="utf-8")
        self.one_line.write_text("", encoding="utf-8")
        self.assertEqual(self.rc(self.run_helper("ok")), 2)
        self.assertEqual(self.apt_calls(), 0)


class WiringTests(unittest.TestCase):
    def read(self, rel: str) -> str:
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_called_before_the_first_apt_update(self) -> None:
        for rel in ("scripts/templates/setup_cpu_system_skeleton.sh", "scripts/templates/setup_rocm_reboot_skeleton.sh",
                    "scripts/remote/host_bootstrap.sh"):
            with self.subTest(rel=rel):
                text = self.read(rel)
                self.assertIn("lib/apt_mirror_fallback.sh", text)
                call = text.index("ensure_ubuntu_apt_mirror")
                self.assertLess(call, text.index("apt-get update"), rel)
        toolkit = self.read("scripts/lib/nvidia_cuda_toolkit.sh")
        self.assertIn('source "$(dirname "${BASH_SOURCE[0]}")/apt_mirror_fallback.sh"', toolkit)
        body = toolkit[toolkit.index("nvidia_apt_update_once() {"):]
        self.assertLess(body.index("ensure_ubuntu_apt_mirror"),
                        body.index('record_cmd "DEBIAN_FRONTEND=noninteractive apt-get update -y"'))

    def test_shipped_to_vm_and_generated_repos(self) -> None:
        self.assertIn('"lib/apt_mirror_fallback.sh"', self.read("scripts/remote_host_bootstrap.py"))
        self.assertIn('"scripts/lib/apt_mirror_fallback.sh"', self.read("scripts/self_check_generated_repo.sh"))
        self.assertEqual(subprocess.run(["bash", "-n", str(MIRROR)]).returncode, 0)


class BootstrapCudaTests(unittest.TestCase):
    def test_install_only_when_asked(self) -> None:
        text = (ROOT / "scripts/remote/host_bootstrap.sh").read_text(encoding="utf-8")
        guard = '"${BENCHMARK_BOOTSTRAP_CUDA:-0}" == "1" ]]; then'
        self.assertIn(guard, text)
        self.assertGreater(text.index("install_nvidia_cuda_toolkit"), text.index(guard))
        self.assertIn('NVCC_RELEASE="left-to-setup"', text)

    def run_bootstrap(self, env_value: str | None) -> str:
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            import remote_host_bootstrap as mod
        finally:
            sys.path.pop(0)
        commands: list[str] = []

        class Result:
            returncode = 0
            stdout = "BOOTSTRAP_KV cuda_toolkit=left-to-setup\nBOOTSTRAP_OK\n"
            stderr = ""

        def fake_ssh(_ssh, command, **_kwargs):
            commands.append(command)
            return Result()

        saved_copy = mod.copy_bootstrap
        saved_env = os.environ.pop("BENCHMARK_BOOTSTRAP_CUDA", None)
        mod.copy_bootstrap = lambda *_a, **_k: True
        try:
            if env_value is not None:
                os.environ["BENCHMARK_BOOTSTRAP_CUDA"] = env_value
            with tempfile.TemporaryDirectory() as tmp:
                report = mod.run_bootstrap(fake_ssh, fake_ssh, "ssh x@1.2.3.4", "ssh x@1.2.3.4", "/tmp",
                                           ["201", "202"], Path(tmp))
        finally:
            mod.copy_bootstrap = saved_copy
            os.environ.pop("BENCHMARK_BOOTSTRAP_CUDA", None)
            if saved_env is not None:
                os.environ["BENCHMARK_BOOTSTRAP_CUDA"] = saved_env
        self.assertEqual(report["status"], "ok")
        return next(c for c in commands if "host_bootstrap.sh" in c)

    def test_env_is_forwarded_only_when_set(self) -> None:
        self.assertTrue(self.run_bootstrap(None).startswith("bash "))
        self.assertTrue(self.run_bootstrap("1").startswith("BENCHMARK_BOOTSTRAP_CUDA=1 bash "))


@unittest.skipIf(BASH is None, "bash is not installed")
class LoginPathTests(unittest.TestCase):
    def run_lib(self, body: str, **env: str) -> subprocess.CompletedProcess:
        script = (f'log_status() {{ echo "$1"; }}\nsource "{(LIB / "nvidia_cuda_toolkit.sh").as_posix()}"\n{body}\n')
        return subprocess.run([BASH, "-c", script], env=dict(os.environ, **env), capture_output=True, text=True, timeout=60)

    def test_profile_file_written_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "cuda-benchmark.sh"
            result = self.run_lib("nvidia_cuda_login_path; nvidia_cuda_login_path",
                                  NVIDIA_CUDA_PREFIX="/usr/local", NVIDIA_PROFILE_D_FILE=str(target))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.count("on login PATH"), 1)
            text = target.read_text(encoding="utf-8")
            self.assertIn('export PATH="/usr/local/cuda/bin:${PATH}"', text)
            once = subprocess.run([BASH, "-c", f'PATH=/usr/bin:/bin; . "{target}"; . "{target}"; echo "$PATH"'],
                                  capture_output=True, text=True, timeout=30)
            self.assertEqual(once.stdout.strip(), "/usr/local/cuda/bin:/usr/bin:/bin")

    def test_test_prefix_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_lib("nvidia_cuda_login_path; echo done", NVIDIA_CUDA_PREFIX=tmp)
            self.assertIn("done", result.stdout)
            self.assertNotIn("on login PATH", result.stdout)

    def test_called_after_install(self) -> None:
        text = (LIB / "nvidia_cuda_toolkit.sh").read_text(encoding="utf-8")
        body = text[text.index("install_nvidia_cuda_toolkit() {"):text.index("nvidia_cuda_login_path() {")]
        self.assertIn("nvidia_cuda_login_path || true", body)


class DocsTests(unittest.TestCase):
    def read(self, rel: str) -> str:
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_batch_log_is_kept(self) -> None:
        for rel in ("AGENTS.md", "docs/AI_AGENT_INSTRUCTIONS.md", "docs/generation-workflow.md", "docs/SUBMISSION_CHECKLIST.md"):
            with self.subTest(rel=rel):
                self.assertIn("batch_remote_output.log", self.read(rel))
        keep = self.read("docs/AI_AGENT_INSTRUCTIONS.md").split("Keep only required local project-root deliverables:")[1]
        keep = keep.split("Remove leftover helpers")[0]
        self.assertIn("`batch_remote_output.log`", keep)

    def test_clean_image_copies_local_repositories(self) -> None:
        section = self.read("docs/AI_AGENT_INSTRUCTIONS.md").split("### Clean-image acceptance")[1].split("\n## ")[0]
        self.assertNotIn("Clone the bundle fresh", section)
        self.assertIn("Do **not** `git clone` the published bundle", section)

    def test_readme_mirror_workaround(self) -> None:
        for rel in ("docs/github-profile-README.md", "docs/amd-developer-cloud-getting-started.md"):
            with self.subTest(rel=rel):
                text = self.read(rel)
                self.assertIn("http://archive.ubuntu.com/ubuntu/", text)
                self.assertIn("/etc/apt/sources.list.d/ubuntu.sources", text)
        self.assertIn("archive.ubuntu.com", self.read("templates/suite-tools/README.md"))


if __name__ == "__main__":
    unittest.main()
