#!/usr/bin/env python3
# File: tests/test_readme_bundle_sections.py
# Description: The generated README has the Download as a Bundle and Suite
#   Tools sections, with the workload's own bundle, before section 1.
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import fill_generated_docs  # noqa: E402

CASES = [
    ("101", "sys-bench-amd-rocm-stack-validation-ubu2404", "AMD", "Ubuntu 24.04", "bundle-amd-ubuntu-2404"),
    ("217", "gpu-bench-nvidia-gemm-cublas-micro-ubu2404", "NVIDIA", "Ubuntu 24.04", "bundle-nvidia-ubuntu-2404"),
    ("315", "gpu-bench-amd-babelstream-hbm-bandwidth-ubu2604", "AMD", "Ubuntu 26.04", "bundle-amd-ubuntu-2604"),
    ("428", "gpu-bench-nvidia-vllm-throughput-latency-ubu2604", "NVIDIA", "Ubuntu 26.04", "bundle-nvidia-ubuntu-2604"),
]


class ReadmeBundleSectionTests(unittest.TestCase):
    def test_bundle_and_suite_tools_sections(self) -> None:
        template = (ROOT / "templates" / "README_TEMPLATE.md").read_text(encoding="utf-8")
        for number, repo, vendor, os_version, bundle in CASES:
            with self.subTest(workload=number):
                fields = {"Workload Number": number, "Repo Name": repo, "GPU Vendor": vendor,
                          "OS Version": os_version, "Workload Name": "Sample"}
                fields.update(fill_generated_docs.ci_fields(fields))
                section = fill_generated_docs.TOKEN_RE.sub(
                    lambda m: fields.get(m.group(1).strip(), m.group(0)),
                    template[template.index("## Download as a Bundle"):template.index("## 1. Overview")],
                )
                self.assertNotIn("{{", section)
                self.assertIn(f"git clone --recurse-submodules https://github.com/{fields['CI Owner']}/{bundle} /opt/benchmarks", section)
                self.assertIn(f"cd /opt/benchmarks/{number}-{repo}", section)
                self.assertLess(section.index("## Download as a Bundle"), section.index("## Suite Tools"))
                for script in ("run_benchmark_suite.sh", "get_remote_info.sh", "show_metrics.sh"):
                    self.assertIn(script, section)
                self.assertIn(f"-w {number} ", section)
                self.assertIn(f"show_metrics.sh {number} ", section)
                example = number[0] + "07"
                flat = section.replace("\r\n", "\n")
                self.assertIn("apt-get update && apt-get install -y git\ngit clone --recurse-submodules", flat)
                self.assertIn("  && bash run_benchmark.sh --profile smoke --validate \\\n  && cd /opt/benchmarks \\\n  && echo \"Done:", flat)
                self.assertIn(f"{number}-{repo} smoke run passed", flat)
                self.assertIn(f"./run_benchmark_suite.sh -w {example} --baseline", flat)
                self.assertIn(f"workload {example}, baseline profile", flat)
                for line in flat.splitlines():
                    self.assertEqual(line, line.rstrip(), f"trailing whitespace: {line!r}")


if __name__ == "__main__":
    unittest.main()
