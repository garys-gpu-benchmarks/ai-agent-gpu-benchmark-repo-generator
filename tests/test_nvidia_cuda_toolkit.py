#!/usr/bin/env python3
"""NVIDIA setup installs one CUDA toolkit per Ubuntu release from NVIDIA's repository.

TEMPLATE_00_114 failed every Ubuntu 24.04 workload on a fresh image: the 24.04
branch never added NVIDIA's CUDA repository, fell back to Ubuntu's
nvidia-cuda-toolkit, and that package broke dpkg on a host with a bind-mounted
driver. These tests run scripts/lib/nvidia_cuda_toolkit.sh and each setup's
apt_install against fake apt/dpkg tools.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "scripts" / "lib" / "nvidia_cuda_toolkit.sh"
NVCC_LIB = ROOT / "scripts" / "lib" / "nvcc_glibc_throw.sh"
SELF_CHECK = ROOT / "scripts" / "self_check_generated_repo.sh"
NVIDIA_SETUPS = [ROOT / "scripts" / "templates" / "setup_nvidia_skeleton.sh"] + sorted(
    (ROOT / "implementation_components").glob("*-nvidia/files/setup.sh")
)

FAKE_TOOLS = {
    "apt-cache": r'''#!/bin/bash
echo "apt-cache $*" >> "$STATE/log"
[[ "$1" == "show" && -f "$STATE/repo" ]] && exit 0
exit 100
''',
    "curl": r'''#!/bin/bash
echo "curl $*" >> "$STATE/log"
out=""
while [[ $# -gt 0 ]]; do [[ "$1" == "-o" ]] && out="$2"; shift; done
[[ -n "$out" ]] && echo deb > "$out"
exit 0
''',
    "dpkg": r'''#!/bin/bash
echo "dpkg $*" >> "$STATE/log"
case "$1" in
  -i) touch "$STATE/repo" ;;
  --audit) cat "$STATE/audit" 2>/dev/null; exit 0 ;;
  -S) [[ -f "$STATE/owned" ]] && exit 0; exit 1 ;;
  -s) exit 1 ;;
esac
exit 0
''',
    "apt-get": r'''#!/bin/bash
echo "apt-get $*" >> "$STATE/log"
[[ "$1" == "install" ]] || exit 0
pkg="${!#}"
if [[ -f "$STATE/audit_after_install" ]]; then cp "$STATE/audit_after_install" "$STATE/audit"; fi
[[ -f "$STATE/apt_fail" ]] && exit 100
if [[ "$pkg" =~ ^cuda-toolkit-([0-9]+)-([0-9]+)$ ]]; then
  ver="${BASH_REMATCH[1]}.${BASH_REMATCH[2]}"
  mkdir -p "$PREFIX/cuda-$ver/bin"
  printf '#!/bin/bash\necho "Cuda compilation tools, release %s, V%s.1"\n' "$ver" "$ver" > "$PREFIX/cuda-$ver/bin/nvcc"
  chmod +x "$PREFIX/cuda-$ver/bin/nvcc"
fi
exit 0
''',
    "update-alternatives": '#!/bin/bash\necho "update-alternatives $*" >> "$STATE/log"\nexit 0\n',
}


class FakeHost:
    def __init__(self, version_id: str = "24.04") -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.state = base / "state"
        self.bin = base / "bin"
        self.prefix = base / "usr-local"
        for d in (self.state, self.bin, self.prefix):
            d.mkdir()
        for name, body in FAKE_TOOLS.items():
            path = self.bin / name
            path.write_text(body, encoding="utf-8", newline="\n")
            path.chmod(0o755)
        self.os_release = base / "os-release"
        self.os_release.write_text(f'VERSION_ID="{version_id}"\n', encoding="utf-8")
        self.ml_lib = base / "libnvidia-ml.so.1"
        self.ml_lib.write_text("", encoding="utf-8")
        self.pin = base / "preferences.d" / "benchmark-host-nvidia-driver"

    def close(self) -> None:
        self._tmp.cleanup()

    def env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.update(
            PATH=f"{self.bin}:{os.environ.get('PATH', '/usr/bin:/bin')}",
            STATE=str(self.state),
            PREFIX=str(self.prefix),
            NVIDIA_OS_RELEASE_FILE=str(self.os_release),
            NVIDIA_ML_LIB=str(self.ml_lib),
            NVIDIA_APT_PIN_FILE=str(self.pin),
            NVIDIA_CUDA_PREFIX=str(self.prefix),
        )
        return env

    def run(self, script: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "-c", f"set -euo pipefail\nsource '{LIB}'\n{script}"],
            env=self.env(), text=True, capture_output=True, check=False,
        )

    def log(self) -> str:
        path = self.state / "log"
        return path.read_text(encoding="utf-8") if path.exists() else ""


def function_source(text: str, name: str) -> str:
    match = re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", text, re.M | re.S)
    if not match:
        raise AssertionError(f"{name}() not found")
    return match.group(0)


class ToolkitChoiceTest(unittest.TestCase):
    def check(self, version_id: str, expected: str) -> None:
        host = FakeHost(version_id)
        try:
            result = host.run("nvidia_cuda_version; nvidia_cuda_repo_id; nvidia_dcgm_package")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.split(), expected.split())
        finally:
            host.close()

    def test_ubuntu_2404_uses_cuda_12_8(self) -> None:
        self.check("24.04", "12.8 ubuntu2404 datacenter-gpu-manager-4-cuda12")

    def test_ubuntu_2604_uses_cuda_13_3(self) -> None:
        self.check("26.04", "13.3 ubuntu2604 datacenter-gpu-manager-4-cuda13")

    def test_unknown_release_fails_with_a_reason(self) -> None:
        host = FakeHost("22.04")
        try:
            result = host.run("install_nvidia_cuda_toolkit")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("No CUDA toolkit is defined for Ubuntu 22.04", result.stderr)
        finally:
            host.close()


class InstallTest(unittest.TestCase):
    def setUp(self) -> None:
        self.host = FakeHost("24.04")

    def tearDown(self) -> None:
        self.host.close()

    def test_fresh_2404_adds_the_repository_then_installs_cuda_toolkit_12_8(self) -> None:
        result = self.host.run('install_nvidia_cuda_toolkit; echo "ver=${NVIDIA_CUDA_VERSION}"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ver=12.8", result.stdout)
        log = self.host.log()
        self.assertIn("compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb", log)
        self.assertIn("apt-get install -y cuda-toolkit-12-8", log)
        self.assertNotIn("nvidia-cuda-toolkit", log)
        self.assertLess(log.index("dpkg -i"), log.index("apt-get install"))

    def test_versioned_nvcc_already_present_installs_nothing(self) -> None:
        nvcc = self.host.prefix / "cuda-12.8" / "bin" / "nvcc"
        nvcc.parent.mkdir(parents=True)
        nvcc.write_text('#!/bin/bash\necho "Cuda compilation tools, release 12.8, V12.8.93"\n', encoding="utf-8")
        nvcc.chmod(0o755)
        result = self.host.run("install_nvidia_cuda_toolkit")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("apt-get install", self.host.log())

    def test_leftover_nvcc_on_path_does_not_skip_the_install(self) -> None:
        stale = self.host.bin / "nvcc"
        stale.write_text('#!/bin/bash\necho "Cuda compilation tools, release 12.0, V12.0.140"\n', encoding="utf-8")
        stale.chmod(0o755)
        result = self.host.run("install_nvidia_cuda_toolkit")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("apt-get install -y cuda-toolkit-12-8", self.host.log())

    def test_inconsistent_dpkg_after_the_install_fails(self) -> None:
        (self.host.state / "audit_after_install").write_text(
            "The following packages have been unpacked but not yet configured:\n gcc-12\n", encoding="utf-8")
        result = self.host.run("install_nvidia_cuda_toolkit")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dpkg is not consistent", result.stderr)

    def test_failed_apt_install_fails(self) -> None:
        (self.host.state / "apt_fail").touch()
        result = self.host.run("install_nvidia_cuda_toolkit")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("apt-get install cuda-toolkit-12-8 failed", result.stderr)


class DriverPinTest(unittest.TestCase):
    def setUp(self) -> None:
        self.host = FakeHost("24.04")

    def tearDown(self) -> None:
        self.host.close()

    def test_unowned_driver_gets_the_pin(self) -> None:
        result = self.host.run("nvidia_pin_host_driver")
        self.assertEqual(result.returncode, 0, result.stderr)
        text = self.host.pin.read_text(encoding="utf-8")
        self.assertIn("Package: nvidia-cuda-toolkit libnvidia-compute-* nvidia-driver-* nvidia-utils-*", text)
        self.assertIn("Pin-Priority: -1", text)
        self.assertNotIn("cuda-toolkit-", text.replace("nvidia-cuda-toolkit", ""))

    def test_dpkg_managed_driver_gets_no_pin(self) -> None:
        (self.host.state / "owned").touch()
        result = self.host.run("nvidia_pin_host_driver")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.host.pin.exists())

    def test_no_driver_library_gets_no_pin(self) -> None:
        self.host.ml_lib.unlink()
        result = self.host.run("nvidia_pin_host_driver")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.host.pin.exists())


class SetupScriptTest(unittest.TestCase):
    def test_every_nvidia_setup_uses_the_shared_install(self) -> None:
        self.assertEqual(len(NVIDIA_SETUPS), 5, [str(p) for p in NVIDIA_SETUPS])
        for path in NVIDIA_SETUPS:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                code = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
                self.assertEqual([line for line in code if "nvidia-cuda-toolkit" in line], [])
                self.assertEqual([line for line in code if "cuda-nvcc-1" in line], [])
                self.assertRegex(text, r"(?m)^install_nvidia_cuda_toolkit$")
                self.assertIn('source "${REPO_ROOT}/scripts/lib/nvidia_cuda_toolkit.sh"', text)
                source_at = text.index('source "${REPO_ROOT}/scripts/lib/nvidia_cuda_toolkit.sh"')
                first_call = re.search(r"(?m)^apt_install ", text)
                self.assertIsNotNone(first_call)
                self.assertLess(source_at, first_call.start())
                self.assertIn("nvidia_pin_host_driver", text)

    def run_apt_install(self, path: Path, script: str, audit: str = "") -> subprocess.CompletedProcess[str]:
        host = FakeHost("24.04")
        try:
            (host.state / "apt_fail").touch()
            if audit:
                (host.state / "audit_after_install").write_text(audit, encoding="utf-8")
            body = function_source(path.read_text(encoding="utf-8"), "apt_install")
            program = "\n".join([
                "log_status() { echo \"$1\"; }", "record_cmd() { :; }", body, script,
            ])
            return host.run(program)
        finally:
            host.close()

    def test_apt_install_reports_failure_so_fallbacks_run(self) -> None:
        for path in NVIDIA_SETUPS:
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                result = self.run_apt_install(path, "apt_install pkg-a || echo fallback-ran")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("fallback-ran", result.stdout)

    def test_bare_apt_install_failure_stops_setup(self) -> None:
        for path in NVIDIA_SETUPS:
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                result = self.run_apt_install(path, "apt_install pkg-a\necho after")
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("after", result.stdout)

    def test_broken_dpkg_stops_setup_even_for_an_optional_package(self) -> None:
        for path in NVIDIA_SETUPS:
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                result = self.run_apt_install(
                    path, "apt_install pkg-a || true\necho after",
                    audit="The following packages have been unpacked but not yet configured:\n x\n")
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("after", result.stdout)
                self.assertIn("dpkg is not consistent", result.stderr)

    def test_vllm_torchaudio_is_pinned_without_touching_torch(self) -> None:
        for path in NVIDIA_SETUPS:
            if "vllm-" not in path.as_posix():
                continue
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                self.assertIn('"torchaudio==2.11.0+${AUDIO_TAG}"', text)
                self.assertIn("--force-reinstall --no-deps", text)
                self.assertNotIn("cu126", text)

    def test_sdxl_runner_puts_the_installed_toolkit_first(self) -> None:
        text = (ROOT / "implementation_components" / "sdxl-diffusers-nvidia" / "files" / "run_benchmark.sh").read_text(encoding="utf-8")
        exports = [line for line in text.splitlines() if line.startswith("export PATH=") and "cuda" in line]
        self.assertTrue(exports)
        for line in exports:
            self.assertTrue(line.startswith('export PATH="/usr/local/cuda/bin:'), line)

    def test_self_check_guards_the_shared_install(self) -> None:
        text = SELF_CHECK.read_text(encoding="utf-8")
        self.assertIn('"scripts/lib/nvidia_cuda_toolkit.sh"', text)
        self.assertIn("installs Ubuntu's nvidia-cuda-toolkit", text)


class NcclCheckTest(unittest.TestCase):
    """vLLM and SGLang use PyTorch's bundled NCCL, so setup must not require the system libnccl.so.

    Only the NCCL bandwidth workload (x16) installs libnccl2/libnccl-dev. In TEMPLATE_00_116,
    230 failed setup on a fresh 24.04 host because x16 had not run first, although
    torch.cuda.nccl.version() in its .venv returned (2, 29, 7).
    """

    OVERLAYS = ("sglang-prompt-response", "vllm-kvcache", "vllm-throughput", "vllm-token-generation")

    def overlay(self, name: str) -> str:
        return (ROOT / "implementation_components" / f"{name}-nvidia" / "files" / "setup.sh").read_text(encoding="utf-8")

    def test_checks_torch_nccl_not_the_system_library(self) -> None:
        for name in self.OVERLAYS:
            text = self.overlay(name)
            with self.subTest(overlay=name):
                self.assertIn('verify_cmd "NCCL" .venv/bin/python -c "import torch; assert torch.cuda.nccl.version()"', text)
                self.assertNotRegex(text, r'(?m)^verify_cmd "NCCL" test ')

    def test_check_passes_and_fails_on_the_venv_answer(self) -> None:
        body = function_source(self.overlay("sglang-prompt-response"), "verify_cmd")
        for answer, expected in (("(2, 29, 7)", 0), ("", 1)):
            with tempfile.TemporaryDirectory() as tmp, self.subTest(answer=answer or "missing"):
                venv = Path(tmp) / ".venv" / "bin"
                venv.mkdir(parents=True)
                python = venv / "python"
                if expected == 0:
                    python.write_text("#!/bin/bash\necho '(2, 29, 7)'\nexit 0\n", encoding="utf-8")
                else:
                    python.write_text("#!/bin/bash\necho 'AssertionError' >&2\nexit 1\n", encoding="utf-8")
                python.chmod(0o755)
                script = "\n".join([
                    'log_status() { echo "$1"; }', body,
                    'verify_cmd "NCCL" .venv/bin/python -c "import torch; assert torch.cuda.nccl.version()"',
                ])
                result = subprocess.run(["bash", "-c", script], cwd=tmp, text=True, capture_output=True, check=False)
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)


class UnsupportedCompilerTest(unittest.TestCase):
    def test_unsupported_gnu_version_fails_without_the_header_repair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "bin").mkdir()
            (base / "repo").mkdir()
            nvcc = base / "bin" / "nvcc"
            nvcc.write_text(
                "#!/bin/bash\n"
                'if [[ "$1" == "--version" ]]; then echo "Cuda compilation tools, release 12.0, V12.0.140"; exit 0; fi\n'
                "echo 'host_config.h:132:2: error: #error -- unsupported GNU version! gcc versions later than 12 are not supported!' >&2\n"
                "exit 1\n",
                encoding="utf-8",
            )
            nvcc.chmod(0o755)
            env = dict(os.environ, PATH=f"{base / 'bin'}:{os.environ.get('PATH', '')}", REPO_ROOT=str(base / "repo"))
            result = subprocess.run(
                ["bash", "-c", f"source '{NVCC_LIB}'; nvcc_pin_toolkit() {{ :; }}; nvcc_glibc_prepare"],
                env=env, text=True, capture_output=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("does not support the host compiler", result.stderr)
            self.assertNotIn("Writing a repo-local rsqrt repair", result.stderr)
            self.assertFalse((base / "repo" / "build" / "cuda-header-fix").exists())


if __name__ == "__main__":
    unittest.main()
