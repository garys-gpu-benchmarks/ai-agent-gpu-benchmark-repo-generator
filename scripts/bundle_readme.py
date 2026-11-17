#!/usr/bin/env python3
# File: scripts/bundle_readme.py
# Description: Fill in templates/suite-tools/BUNDLE_README_TEMPLATE.md.
#   user_scripts/publish_benchmarks_to_github.sh bundle_readme() reads the same
#   file. The two must produce the same text; tests/test_template_00_145_changes.py
#   compares them to the README the bash function printed before the move.
# Execution: imported. python3 scripts/bundle_readme.py is not a workflow.
from __future__ import annotations

import re
from pathlib import Path

ORG = "garys-gpu-benchmarks"
TEMPLATE_REL = Path("templates") / "suite-tools" / "BUNDLE_README_TEMPLATE.md"

# First character of a workload directory -> bundle slug, link label, title.
# Titles match platform() in the publish script.
PLATFORMS = {
    "1": {
        "slug": "bundle-amd-ubuntu-2404",
        "label": "AMD 24.04",
        "title": "AMD ROCm - Ubuntu 24.04",
        "vendor": "AMD",
        "stack": "ROCm",
        "os": "24.04",
    },
    "2": {
        "slug": "bundle-nvidia-ubuntu-2404",
        "label": "NVIDIA 24.04",
        "title": "NVIDIA CUDA - Ubuntu 24.04",
        "vendor": "NVIDIA",
        "stack": "CUDA",
        "os": "24.04",
    },
    "3": {
        "slug": "bundle-amd-ubuntu-2604",
        "label": "AMD 26.04",
        "title": "AMD ROCm - Ubuntu 26.04",
        "vendor": "AMD",
        "stack": "ROCm",
        "os": "26.04",
    },
    "4": {
        "slug": "bundle-nvidia-ubuntu-2604",
        "label": "NVIDIA 26.04",
        "title": "NVIDIA CUDA - Ubuntu 26.04",
        "vendor": "NVIDIA",
        "stack": "CUDA",
        "os": "26.04",
    },
}

_RESTART_STEPS = """This is planned, not a failure:

1. Log in again as root after a few minutes. Setup continues on its own after
   the restart.
2. To watch it: `tail -f /opt/benchmarks/@S@01-*/results/install_status.txt`
   (Ctrl+C stops watching, not setup).
3. Run the same command again. If it says setup is still running, wait a few
   minutes and run it again. Benchmarks already installed are not installed
   again."""

_UBU_SUFFIX = re.compile(r"-ubu[0-9]{4}$")


def template_text(generator_root: Path) -> str:
    """The template with CR removed and trailing newlines dropped, as bash $(...) does."""
    data = (generator_root / TEMPLATE_REL).read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return data.decode("utf-8").rstrip("\n")


def short_workload_name(directory: str) -> str:
    """The short name publish uses in a bundle README row.

    Mirrors: short=${dir:4}; short=${short%-ubuNNNN}; short=${short#*-bench-}; short=${short#*-}
    """
    short = directory[4:]
    short = _UBU_SUFFIX.sub("", short)
    marker = "-bench-"
    at = short.find(marker)
    if at != -1:
        short = short[at + len(marker):]
    hyphen = short.find("-")
    if hyphen != -1:
        short = short[hyphen + 1:]
    return short


def workload_row(directory: str, org: str = ORG) -> str:
    short = short_workload_name(directory)
    return f"| {directory[:3]} | [{short}](https://github.com/{org}/{directory}) |"


def render_bundle_readme(
    digit: str,
    bundle: str,
    want: str,
    rows: str,
    *,
    org: str,
    version: str,
    generator_root: Path,
) -> str:
    """One platform's bundle README. Same substitutions as bundle_readme()."""
    s = str(digit)[:1]
    if s not in PLATFORMS:
        raise ValueError(f"platform digit must be 1-4, not {digit!r}")
    info = PLATFORMS[s]
    others_parts = []
    for other in "1234":
        if other == s:
            continue
        item = PLATFORMS[other]
        others_parts.append(f"[{item['label']}](https://github.com/@ORG@/{item['slug']})")
    others = " \u00b7\n".join(others_parts)
    if s == "1":
        prereq = "- The first run installs ROCm and may restart the machine once; that must be acceptable."
        restart = (
            "**If the machine restarts.** Installing ROCm may restart the machine once,\n"
            "which closes your connection. " + _RESTART_STEPS
        )
    elif s == "3":
        prereq = "- The first run installs ROCm and restarts the machine once; that must be acceptable."
        restart = (
            "**The machine restarts once.** The Ubuntu 26.04 image cannot start the MI300X\n"
            "until ROCm's firmware is installed, so the first install ends with one restart,\n"
            "which closes your connection. With `--show-output`, the output ends like this:\n"
            "\n"
            "```text\n"
            "Successfully installed PyYAML-6.0.3\n"
            "[WARN] Setup is awaiting reboot-resume completion. Rerun bash run_benchmark.sh after setup completes.\n"
            "Connection to <your-machine-address> closed by remote host.\n"
            "```\n"
            "\n" + _RESTART_STEPS
        )
    else:
        prereq = (
            "- The NVIDIA driver installed: `nvidia-smi` lists the GPUs. The first run installs CUDA;\n"
            "  it never installs the driver or restarts the machine."
        )
        restart = ""
    text = template_text(generator_root)
    text = text.replace("@OTHERS@", others)
    text = text.replace("@PREREQ@", prereq)
    text = text.replace("@RESTART@", restart)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    text = text.replace("@PLATFORM@", info["title"])
    text = text.replace("@VENDOR@", info["vendor"])
    text = text.replace("@STACK@", info["stack"])
    text = text.replace("@OS@", info["os"])
    text = text.replace("@ORG@", org)
    text = text.replace("@BUNDLE@", bundle)
    text = text.replace("@WANT@", str(want))
    text = text.replace("@VERSION@", version)
    text = text.replace("@S@", s)
    if rows.endswith("\n"):
        rows = rows[:-1]
    text = text.replace("@ROWS@", rows)
    return text + "\n"


def render_mixed_readme(directories: list[str], *, org: str = ORG) -> str:
    """A project root that holds more than one platform. Does not pick one."""
    grouped: dict[str, list[str]] = {}
    for name in directories:
        grouped.setdefault(name[0], []).append(name)
    lines = [
        "# More than one platform",
        "",
        "This folder holds workloads from more than one platform, so it is not one bundle.",
        "The table names every platform that is here. It does not pick one.",
        "",
        "| Platform | Workloads | Bundle |",
        "|---|---|---|",
    ]
    for digit in sorted(grouped):
        names = sorted(grouped[digit])
        numbers = ", ".join(name[:3] for name in names)
        info = PLATFORMS[digit]
        lines.append(
            f"| {info['title']} | {len(names)} ({numbers}) | "
            f"[{info['slug']}](https://github.com/{org}/{info['slug']}) |"
        )
    lines += [
        "",
        "The scripts beside this file are the suite tools (`get_benchmark_results.sh`,",
        "`list_runs.sh`, `run_benchmark_suite.sh`, `show_metrics.sh`), copied from",
        "`user_scripts/`. With no profile option, `run_benchmark_suite.sh` runs the",
        "smoke profile. A full run is `--smoke --baseline --extended`. A published",
        "bundle's copy is the same script with that bundle's workload numbers in the examples.",
        "",
        "## Benchmarks",
        "",
        "| # | Repository |",
        "|---|---|",
    ]
    for name in sorted(directories):
        lines.append(workload_row(name, org))
    return "\n".join(lines) + "\n"


def readme_for_directories(
    directories: list[str],
    *,
    org: str = ORG,
    version: str,
    generator_root: Path,
) -> str:
    """Bundle README for one platform, or the mixed-platform page."""
    digits = sorted({name[0] for name in directories})
    if len(digits) != 1:
        return render_mixed_readme(directories, org=org)
    digit = digits[0]
    rows = "\n".join(workload_row(name, org) for name in sorted(directories)) + "\n"
    return render_bundle_readme(
        digit,
        PLATFORMS[digit]["slug"],
        str(len(directories)),
        rows,
        org=org,
        version=version,
        generator_root=generator_root,
    )
