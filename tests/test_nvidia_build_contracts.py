#!/usr/bin/env python3
# File: tests/test_nvidia_build_contracts.py
# Description: Build contracts for NVIDIA components that compile their own CUDA
# source. Workload 418 failed on Ubuntu 26.04 (CUDA 13.3 nvcc, older driver)
# three ways: build.sh looked for libcudnn.so, which the nvidia-cudnn-cu13 wheel
# never ships (only libcudnn.so.9), the wheel's cudnn.h was not on the include
# path, and kernels built without -gencode were rejected at launch ("the provided
# PTX was compiled with an unsupported toolchain"). Workload 404 had the same
# missing -gencode and did not check launches, so it could report zero failures
# without running a kernel. No GPU or nvcc is needed for these tests.
from __future__ import annotations

import re
import stat
import subprocess
import tempfile
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "implementation_components"
NVCC_LIB = ROOT / "scripts" / "lib" / "nvcc_glibc_throw.sh"
SKELETON = ROOT / "scripts" / "templates" / "setup_nvidia_skeleton.sh"
CUDNN_BUILD = COMPONENTS / "cudnn-convolution-nvidia" / "files" / "scripts" / "build.sh"

LAUNCH = re.compile(r"<<<[^>]*>>>")
LAUNCH_CHECK_WINDOW = 5


# Git Bash on Windows, never System32's WSL bash.exe (TEMPLATE_00_147, OPEN_ISSUES T1).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from host_bash import HOST_BASH  # noqa: E402


def kernel_sources() -> list[Path]:
    found = []
    for src in sorted(COMPONENTS.glob("*/files/src/*.cu")):
        if "__global__" in src.read_text(encoding="utf-8"):
            found.append(src)
    return found


class KernelComponentBuildTest(unittest.TestCase):
    def test_kernel_sources_exist(self) -> None:
        names = {p.parents[2].name for p in kernel_sources()}
        for expected in ("cudnn-convolution-nvidia", "sdc-ecc-nvidia", "babelstream-hbm-nvidia"):
            self.assertIn(expected, names)

    def test_every_kernel_component_builds_native_sass_via_shared_helper(self) -> None:
        for src in kernel_sources():
            build = src.parents[1] / "scripts" / "build.sh"
            with self.subTest(component=src.parents[2].name):
                self.assertTrue(build.is_file(), f"{build} missing")
                text = build.read_text(encoding="utf-8")
                self.assertIn("source \"${REPO_ROOT}/scripts/lib/nvcc_glibc_throw.sh\"", text)
                self.assertRegex(text, r"(?m)^nvcc_arch_flags\s*$")
                nvcc_lines = [ln for ln in text.splitlines() if ln.lstrip().startswith("nvcc ")]
                self.assertTrue(nvcc_lines, "no nvcc invocation")
                for line in nvcc_lines:
                    self.assertIn('"${NVCC_ARCH_FLAGS[@]}"', line)
                # One copy of the detection logic, in scripts/lib.
                self.assertNotIn("compute_cap", text)

    def test_every_kernel_launch_is_checked(self) -> None:
        for src in kernel_sources():
            lines = src.read_text(encoding="utf-8").splitlines()
            for i, line in enumerate(lines):
                if not LAUNCH.search(line) or "__global__" in line:
                    continue
                window = "\n".join(lines[i + 1 : i + 1 + LAUNCH_CHECK_WINDOW])
                with self.subTest(source=src.parents[2].name, line=i + 1):
                    self.assertIn("cudaGetLastError", window, f"unchecked launch: {line.strip()}")


class CudnnWheelLayoutTest(unittest.TestCase):
    def test_build_finds_versioned_library_and_headers(self) -> None:
        text = CUDNN_BUILD.read_text(encoding="utf-8")
        self.assertIn("/lib/libcudnn.so.9", text)
        self.assertIn("/include/cudnn.h", text)
        self.assertIn('-I"${cudnn_root}/include"', text)
        self.assertIn('ln -sfn libcudnn.so.9 "${cudnn_root}/lib/libcudnn.so"', text)
        self.assertNotIn('-e "${candidate}/libcudnn.so" ', text)
        self.assertNotIn("-Wl,", text)

    def test_skeleton_wheel_check_uses_versioned_library(self) -> None:
        text = SKELETON.read_text(encoding="utf-8")
        self.assertIn("nvidia/cudnn/lib/libcudnn.so.9\" >/dev/null", text)
        self.assertNotIn("nvidia/cudnn/lib/libcudnn.so\" >/dev/null", text)


class NvccArchFlagsTest(unittest.TestCase):
    def run_helper(self, smi_output: str | None, env_extra: dict[str, str] | None = None) -> tuple[str, str]:
        with tempfile.TemporaryDirectory() as tmp:
            bindir = Path(tmp)
            smi = bindir / "nvidia-smi"
            if smi_output is None:
                smi.write_text("#!/bin/sh\nexit 9\n", encoding="utf-8")
            else:
                smi.write_text(f"#!/bin/sh\nprintf '%s\\n' '{smi_output}'\n", encoding="utf-8")
            smi.chmod(smi.stat().st_mode | stat.S_IEXEC)
            env = {"PATH": f"{bindir}:/usr/bin:/bin", "HOME": tmp}
            env.update(env_extra or {})
            script = f'source "{NVCC_LIB}"; nvcc_arch_flags; printf "%s\\n" "${{NVCC_ARCH_FLAGS[*]}}"'
            done = subprocess.run([HOST_BASH, "-c", script], env=env, capture_output=True, text=True, check=True)
            return done.stdout.strip(), done.stderr

    def test_detects_h100_from_nvidia_smi(self) -> None:
        out, _ = self.run_helper("9.0")
        self.assertEqual(out, "-gencode arch=compute_90,code=[sm_90,compute_90]")

    def test_override_wins(self) -> None:
        out, _ = self.run_helper("9.0", {"BENCHMARK_CUDA_ARCH": "100"})
        self.assertEqual(out, "-gencode arch=compute_100,code=[sm_100,compute_100]")

    @unittest.skipIf(Path("/proc/driver/nvidia/gpus").exists(), "host has an NVIDIA GPU; /proc fallback would detect it")
    def test_unknown_gpu_leaves_flags_empty_and_warns(self) -> None:
        out, err = self.run_helper(None)
        self.assertEqual(out, "")
        self.assertIn("BENCHMARK_CUDA_ARCH", err)


if __name__ == "__main__":
    unittest.main()
