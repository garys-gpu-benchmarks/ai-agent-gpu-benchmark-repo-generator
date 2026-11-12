"""TEMPLATE_00_133: NVIDIA 201-232 (Ubuntu 24.04) use CUDA 13.3, the same toolkit as 401-432.

Until TEMPLATE_00_132, Ubuntu 24.04 installed CUDA 12.8 while 26.04 installed 13.3, and
several builds and runners listed /usr/local/cuda-12.8 or /usr/local/cuda-12.6 on PATH.
A 24.04 image or a host set up by an earlier template can carry nvcc 12.6 or 12.8,
so any of those entries could pick it up.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CUDA12_DIR = re.compile(r"/usr/local/cuda-12(\.\d+)?/")


def nvidia_shell_files() -> list[Path]:
    files = sorted((ROOT / "implementation_components").glob("*-nvidia/files/**/*.sh"))
    files.append(ROOT / "scripts" / "templates" / "setup_nvidia_skeleton.sh")
    return files


def code_lines(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


class Cuda133On2404Test(unittest.TestCase):
    def test_toolkit_helper_maps_both_releases_to_13_3(self) -> None:
        text = (ROOT / "scripts" / "lib" / "nvidia_cuda_toolkit.sh").read_text(encoding="utf-8")
        self.assertIn("24.04*) printf '13.3\\n' ;;", text)
        self.assertIn("26.04*) printf '13.3\\n' ;;", text)
        self.assertNotIn("printf '12.8\\n'", text)

    def test_no_nvidia_build_or_runner_puts_cuda_12_on_path(self) -> None:
        files = nvidia_shell_files()
        self.assertGreater(len(files), 15)
        for path in files:
            for line in code_lines(path):
                with self.subTest(path=path.relative_to(ROOT).as_posix(), line=line.strip()[:80]):
                    self.assertIsNone(CUDA12_DIR.search(line))

    def test_every_cuda_path_export_starts_with_the_installed_toolkit(self) -> None:
        for path in nvidia_shell_files():
            for line in code_lines(path):
                if line.startswith("export PATH=") and "/usr/local/cuda" in line:
                    with self.subTest(path=path.relative_to(ROOT).as_posix()):
                        cuda_dirs = re.findall(r"/usr/local/cuda[^:\"]*/bin", line)
                        self.assertEqual(cuda_dirs[0], "/usr/local/cuda/bin", line)

    def test_cudnn_setup_and_build_use_the_installed_nvcc(self) -> None:
        skeleton = (ROOT / "scripts" / "templates" / "setup_nvidia_skeleton.sh").read_text(encoding="utf-8")
        self.assertIn('build_nvcc="/usr/local/cuda-${NVIDIA_CUDA_VERSION}/bin/nvcc"', skeleton)
        self.assertNotIn("libcudnn9-cuda-12 libcudnn9-headers-cuda-12", skeleton)
        build = (ROOT / "implementation_components" / "cudnn-convolution-nvidia" / "files" / "scripts" / "build.sh")
        self.assertIn('export PATH="/usr/local/cuda/bin:/usr/local/cuda-13.3/bin:${PATH}"',
                      build.read_text(encoding="utf-8"))

    def test_workbook_2xx_rows_name_cuda_13_3(self) -> None:
        import openpyxl

        wb = openpyxl.load_workbook(ROOT / "BenchmarkSpecDefinitions.xlsx", read_only=True)
        leftovers = []
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                for value in row:
                    if isinstance(value, str) and (value.strip() == "12.8" or re.search(r"CUDA 12\.8|cuda-12\.8|cuda-version 12\.8", value)):
                        leftovers.append((ws.title, value[:60]))
        self.assertEqual(leftovers, [])

        defs = wb["Workload_Definitions"]
        header = runtime_col = None
        for row in defs.iter_rows(values_only=True):
            if row and "GPU Runtime Version" in row:
                header = row
                runtime_col = row.index("GPU Runtime Version")
                continue
            if header and isinstance(row[0], int) and 201 <= row[0] <= 232:
                self.assertTrue(str(row[runtime_col]).startswith("CUDA 13.3 "), row[0])
                self.assertIn("Driver 595.91.07 reports CUDA 13.2.", str(row[runtime_col]), row[0])

        params = wb["Parameters_SmokeBaselineExtend"]
        cuda = {row[0]: row[3:6] for row in params.iter_rows(values_only=True)
                if row and row[2] == "cuda_version"}
        self.assertEqual(cuda[201], ("13.3", "13.3", "13.3"))
        self.assertEqual(cuda[201], cuda[401])


if __name__ == "__main__":
    unittest.main()
