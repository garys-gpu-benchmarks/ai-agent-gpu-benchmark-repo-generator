#!/usr/bin/env python3
# File: tests/test_readme_bundle_sections.py
# Description: The generated README follows templates/README_TEMPLATE.md and
#   scripts/readme_sections.py: required headings in order, the workload's own
#   bundle in "Run the Whole Bundle" with the other three linked, a parameters
#   table taken from Profile Parameter Values, a metrics table, workbook notes,
#   and troubleshooting chosen by setup type and gated model.
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import fill_generated_docs  # noqa: E402
import readme_sections  # noqa: E402

CASES = [
    ("107", "sys-bench-amd-stream-ddr5-bandwidth-ubu2404", "AMD", "Ubuntu 24.04", "bundle-amd-ubuntu-2404", "CPU / System"),
    ("217", "gpu-bench-nvidia-gemm-cublas-micro-ubu2404", "NVIDIA", "Ubuntu 24.04", "bundle-nvidia-ubuntu-2404", "GPU Compute / CUDA"),
    ("315", "gpu-bench-amd-babelstream-hbm-bandwidth-ubu2604", "AMD", "Ubuntu 26.04", "bundle-amd-ubuntu-2604", "Memory / Transfer"),
    ("428", "gpu-bench-nvidia-vllm-throughput-latency-ubu2604", "NVIDIA", "Ubuntu 26.04", "bundle-nvidia-ubuntu-2604", "LLM Serving"),
]

HEADINGS = (
    "## Quick Start",
    "## Profiles and Parameters",
    "## Metrics",
    "### Notes",
    "## Output",
    "## Requirements",
    "## Run the Whole Bundle",
    "## Troubleshooting",
    "## Repository Layout",
    "## Continuous Integration",
)

PROFILES = {
    "num_threads": {"smoke": "4", "baseline": "16", "extended": "20", "notes": ""},
    "event_list": {"smoke": ",".join(f"e{i}" for i in range(16)), "baseline": "x", "extended": "y", "notes": ""},
}


def _fields(number: str, repo: str, vendor: str, os_version: str, domain: str) -> dict[str, str]:
    fields = {
        "Workload Number": number,
        "Workload Name": "Sample Workload",
        "Repo Base Name": repo,
        "GPU Vendor": vendor,
        "OS Version": os_version,
        "Execution Domain": domain,
        "Main Goal": "Measure sample bandwidth",
        "Metrics": "#1: Sample bandwidth, GB/s (sample_gb_s); #2: Search time (search_msec), summed over directions",
        "Parameter_01": "num_threads",
        "Parameter_02": "event_list",
        "Profile Parameter Values": json.dumps(PROFILES),
        "Known Runtime Constraints (<=35 Words Each)": "First constraint. Second constraint",
        "Framework": "Bash, SQLite, Python, PyYAML, C (not C++), GCC"
        + (", vLLM, Mistral-7B-v0.3" if domain == "LLM Serving" else ""),
        "Python Version": "Python 3.14.8 (uv-managed CPython)",
        "GPU Runtime Version (was ROCm Version)": "ROCm 10.1.0" if vendor == "AMD" else "CUDA 13.3 (nvcc 13.3.73)",
        "GPU Model": "MI300X" if vendor == "AMD" else "H100 SXM 80GB",
    }
    fields.update(fill_generated_docs.ci_fields(fields))
    return fields


def _render(fields: dict[str, str]) -> str:
    template = (ROOT / "templates" / "README_TEMPLATE.md").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        for rel in ("config", "scripts", "docs", "tests"):
            (repo / rel).mkdir()
        for rel in ("SPEC.md", "docs/PRD.md", "LICENSE"):
            (repo / rel).touch()
        return fill_generated_docs.render_template(template, fields, repo)


class ReadmeSectionTests(unittest.TestCase):
    def test_rendered_readme(self) -> None:
        for number, repo, vendor, os_version, bundle, domain in CASES:
            with self.subTest(workload=number):
                fields = _fields(number, repo, vendor, os_version, domain)
                text = _render(fields)
                self.assertNotIn("{{", text)
                self.assertNotIn("[[GENERATE", text)
                positions = [text.index(heading) for heading in HEADINGS]
                self.assertEqual(positions, sorted(positions), "README headings out of order")
                self.assertTrue(text.startswith("# Sample Workload Benchmark\n"))
                self.assertIn(f"Measures sample bandwidth. Workload {number} of the {vendor} ", text)
                owner = fields["CI Owner"]
                self.assertIn(f"git clone https://github.com/{owner}/{number}-{repo}.git", text)
                self.assertIn(f"git clone --recurse-submodules https://github.com/{owner}/{bundle} /opt/benchmarks", text)
                self.assertIn(f"./run_benchmark_suite.sh -w {number} --smoke", text)
                self.assertIn(f"./show_metrics.sh {number} ", text)
                other = text[text.index("Other platforms:"):].splitlines()[0]
                self.assertNotIn(f"/{bundle})", other)
                self.assertEqual(other.count("](https://github.com/"), 3)
                # Parameters table comes from Profile Parameter Values; long lists are counted.
                self.assertIn("| `num_threads` | `--num-threads` | 4 | 16 | 20 |", text)
                self.assertIn("| `event_list` | `--event-list` | 16 items | x | y |", text)
                self.assertIn("Long list values are shown as item counts", text)
                # Metrics: trailing key and a key in the middle of the label.
                self.assertIn("| 1 | Sample bandwidth, GB/s | `sample_gb_s` |", text)
                self.assertIn("| 2 | Search time, summed over directions | `search_msec` |", text)
                self.assertIn("- First constraint.\n- Second constraint.", text)
                self.assertNotIn("(not C++)", text)
                self.assertEqual("This is a CPU benchmark: no GPU is used." in text, domain == "CPU / System")
                rocm_reboot = vendor == "AMD" and domain != "CPU / System"
                self.assertEqual("tail -f results/reboot_resume.log" in text, rocm_reboot)
                gated = domain == "LLM Serving"
                self.assertEqual("mistralai/Mistral-7B-v0.3" in text, gated)
                self.assertEqual("start the real model server" in text, gated)
                self.assertIn("├── SPEC.md", text)
                self.assertIn("# PRD and contracts", text)
                for line in text.splitlines():
                    self.assertEqual(line, line.rstrip(), f"trailing whitespace: {line!r}")

    def test_no_parameters(self) -> None:
        fields = _fields(*CASES[0][:4], CASES[0][5])
        for index in range(1, 21):
            fields.pop(f"Parameter_{index:02d}", None)
        text = _render(fields)
        self.assertIn("This workload has no tunable parameters.", text)
        self.assertNotIn("| Parameter | Flag |", text)

    def test_unknown_section_fails(self) -> None:
        with self.assertRaises(SystemExit):
            readme_sections.render_section("no_such_section", {})


if __name__ == "__main__":
    unittest.main()
