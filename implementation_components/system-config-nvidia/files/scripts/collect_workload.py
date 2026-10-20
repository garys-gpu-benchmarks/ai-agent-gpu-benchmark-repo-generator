#!/usr/bin/env python3
# File: scripts/collect_workload.py
# Description: NVIDIA CUDA stack checks. VBIOS must be a real nvidia-smi -q field.
from __future__ import annotations

import argparse
import csv
import io
import os
import re
import shutil
import subprocess
from pathlib import Path

import yaml


def pv(params, key, profile, default=""):
    raw = params.get(key, default)
    if isinstance(raw, dict):
        return raw.get(profile, raw.get("smoke", default))
    return default if raw is None else raw


def run_command(command, timeout=60):
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return 127, f"{command[0]}: {exc}"
    return completed.returncode, (completed.stdout or "") + "\n" + (completed.stderr or "")


def installed_packages() -> dict[str, str]:
    """Package name -> version for every package dpkg reports as installed."""
    _code, text = run_command(["dpkg-query", "-W", "-f=${Package}\t${Status}\t${Version}\n"])
    found: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[1].strip() == "install ok installed":
            found[parts[0].split(":", 1)[0].strip()] = parts[2].strip()
    return found


def dpkg_owner(command: str) -> str:
    """dpkg package that owns the file behind a command, or "" (for example a host mount)."""
    path = shutil.which(command)
    if not path:
        return ""
    for candidate in dict.fromkeys((path, os.path.realpath(path))):
        code, text = run_command(["dpkg", "-S", candidate])
        if code == 0:
            first = text.strip().splitlines()[0] if text.strip() else ""
            return first.split(":", 1)[0].split(",", 1)[0].strip()
    return ""


CUDA_TOOLKIT_PACKAGE = re.compile(r"^(?:cuda-toolkit|cuda-nvcc|nvidia-cuda-toolkit)(?:-(\d+)-(\d+))?$")


def _major(text: str) -> int | None:
    match = re.search(r"(\d+)", text or "")
    return int(match.group(1)) if match else None


def check_packages(
    packages,
    installed: dict[str, str],
    *,
    expected_cuda: str,
    expected_driver: str,
    smi_owner: str,
    smi_ok: bool,
) -> tuple[list[str], list[str]]:
    """Read the installed packages and return (problems, findings), one problem per mismatch.

    cuda-toolkit: an installed cuda-toolkit / cuda-nvcc / nvidia-cuda-toolkit package whose
    CUDA major equals the workbook major. nvidia-smi: the dpkg package that owns the binary,
    at a version that meets the workbook driver minimum; a binary no package owns (the host
    driver mounted into a container) counts when nvidia-smi runs. Any other name: installed.
    """
    problems: list[str] = []
    findings: list[str] = []
    want_cuda = _major(expected_cuda)
    for name in packages:
        normalized = name.strip().lower().replace("_", "-")
        if normalized == "cuda-toolkit":
            versions = []
            for package, version in sorted(installed.items()):
                match = CUDA_TOOLKIT_PACKAGE.match(package)
                if match:
                    shown = f"{match.group(1)}.{match.group(2)}" if match.group(1) else version_token(version)
                    versions.append((package, shown))
            findings.append("cuda-toolkit: " + (", ".join(f"{p} {v}" for p, v in versions) or "not installed"))
            if not versions:
                problems.append("cuda-toolkit not installed")
            elif want_cuda is not None and all(_major(v) != want_cuda for _p, v in versions):
                problems.append(
                    f"cuda-toolkit {', '.join(v for _p, v in versions)} installed; workbook CUDA major is {want_cuda}"
                )
            continue
        if normalized == "nvidia-smi":
            if smi_owner and smi_owner in installed:
                version = installed[smi_owner]
                findings.append(f"nvidia-smi: {smi_owner} {version}")
                if not version_at_least(version_token(version), expected_driver):
                    problems.append(f"{smi_owner} {version} is below driver {expected_driver}")
            elif smi_ok:
                findings.append("nvidia-smi: runs, not owned by a dpkg package (host driver)")
            else:
                findings.append("nvidia-smi: not installed")
                problems.append("nvidia-smi not installed")
            continue
        version = installed.get(name.strip()) or installed.get(normalized)
        findings.append(f"{name.strip()}: {version or 'not installed'}")
        if not version:
            problems.append(f"{name.strip()} not installed")
    return problems, findings


def version_token(text):
    match = re.search(r"([0-9]+(?:\.[0-9]+)+)", text or "")
    return match.group(1) if match else ""


def version_at_least(actual: str, minimum: str) -> bool:
    try:
        actual_parts = tuple(int(part) for part in actual.split("."))
        minimum_parts = tuple(int(part) for part in minimum.split("."))
    except ValueError:
        return False
    width = max(len(actual_parts), len(minimum_parts))
    return actual_parts + (0,) * (width - len(actual_parts)) >= minimum_parts + (0,) * (width - len(minimum_parts))


def nvidia_module_version():
    proc = Path("/proc/driver/nvidia/version")
    if proc.is_file():
        try:
            token = version_token(proc.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            token = ""
        if token:
            return token
    _code, text = run_command(["modinfo", "-F", "version", "nvidia"])
    return version_token(text)


def libcuda_soname_version():
    _code, text = run_command(["ldconfig", "-p"])
    for path in re.findall(r"libcuda\.so(?:\.\d+)*\s+=>\s+(\S+)", text):
        token = version_token(os.path.realpath(path).rsplit("libcuda.so.", 1)[-1])
        if token and token != "1":
            return token
    for directory in (Path("/usr/lib/x86_64-linux-gnu"), Path("/usr/lib64"), Path("/lib/x86_64-linux-gnu")):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("libcuda.so.*")):
            token = version_token(path.name.replace("libcuda.so.", "", 1))
            if token and token != "1":
                return token
    return ""


def stack_mismatch_count(module_ver, smi_ver, soname_ver):
    """How many of nvidia-smi and libcuda disagree with the loaded kernel module."""
    versions = [module_ver, smi_ver, soname_ver]
    if not module_ver:
        return float(sum(1 for item in versions if not item) or 1)
    return float(sum(1 for item in (smi_ver, soname_ver) if not item or item != module_ver))


def cuda_driver_supports(expected: str, reported: str) -> bool:
    """True when the driver CUDA major is at least the workbook major."""
    expected_match = re.search(r"(\d+)", expected or "")
    reported_match = re.search(r"(\d+)", reported or "")
    if not expected_match or not reported_match:
        return False
    return int(reported_match.group(1)) >= int(expected_match.group(1))


def write_csv(path, header, rows):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=header, extrasaction="ignore", lineterminator=chr(10))
    writer.writeheader()
    rows = list(rows)
    if len(rows) == 1:
        rows.append(dict(rows[0]))
    for index, row in enumerate(rows):
        writer.writerow({"sample_index": index, **row})
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(buf.getvalue(), encoding="utf-8")
    print(buf.getvalue(), end="")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--raw-file", required=True)
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--device", default="gpu")
    parser.add_argument("--output-format", default="csv")
    args = parser.parse_args()
    sweep = (yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}).get("sweep") or {}
    # Read for the record; not compared yet (kernel/runtime checks live elsewhere).
    _expected_kernel = str(pv(sweep, "kernel_version", args.profile, "6.8.0"))
    expected_driver = str(pv(sweep, "nvidia_driver_version", args.profile, sweep.get("driver_version", "580")))
    expected_cuda = str(pv(sweep, "cuda_version", args.profile, "12.6"))
    packages = [item.strip() for item in str(pv(sweep, "required_packages", args.profile, "nvidia-smi")).split(",") if item.strip()]
    permissions_check = str(pv(sweep, "permissions_check", args.profile, "true")).lower() in {"1", "true", "yes"}
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    smi_code, smi = run_command(["nvidia-smi"])
    if smi_code != 0:
        raise SystemExit("[FAIL] nvidia-smi is required for NVIDIA system-config")
    smi_q = run_command(["nvidia-smi", "-q"])[1]
    nvcc = run_command(["nvcc", "--version"])[1]
    (run_dir / "nvidia-smi.txt").write_text(smi, encoding="utf-8")
    (run_dir / "nvidia-smi-q.txt").write_text(smi_q, encoding="utf-8")
    (run_dir / "nvcc.txt").write_text(nvcc, encoding="utf-8")
    driver_line = re.search(r"Driver Version\s*:\s*([0-9.]+)", smi_q) or re.search(r"Driver Version:\s*([0-9.]+)", smi)
    driver_ver = driver_line.group(1) if driver_line else ""
    module_ver = nvidia_module_version()
    soname_ver = libcuda_soname_version()
    # Compare the loaded nvidia module, nvidia-smi, and libcuda SONAME with each other.
    # A userspace 595 build against a 580 module is a mismatch even when uname contains 580.
    stack_mismatches = stack_mismatch_count(module_ver, version_token(driver_ver), soname_ver)
    cuda_line = re.search(r"CUDA Version\s*:\s*([0-9.]+)", smi + smi_q) or re.search(r"release\s*([0-9.]+)", nvcc)
    cuda_ver = cuda_line.group(1) if cuda_line else ""
    # nvidia-smi "CUDA Version" is the newest CUDA the driver supports.
    # A driver that reports 13.2 satisfies a workbook major of 12.
    cuda_mismatch = 0 if cuda_driver_supports(expected_cuda, cuda_ver) else 1
    package_problems, package_findings = check_packages(
        packages,
        installed_packages(),
        expected_cuda=expected_cuda,
        expected_driver=expected_driver,
        smi_owner=dpkg_owner("nvidia-smi"),
        smi_ok=(smi_code == 0),
    )
    package_mismatch = len(package_problems)
    (run_dir / "package_check.txt").write_text(
        "\n".join(package_findings + [f"MISMATCH: {item}" for item in package_problems]) + "\n",
        encoding="utf-8",
    )
    vbios = ""
    match = re.search(r"VBIOS Version\s*:\s*(\S+)", smi_q)
    if match:
        vbios = match.group(1)
    vbios_present = 1.0 if vbios and vbios.lower() not in {"n/a", "unknown", ""} else 0.0
    # Detected VBIOS version, for information only (no expected-revision metric or gate).
    (run_dir / "vbios_version.txt").write_text((vbios or "not detected") + "\n", encoding="utf-8")
    permission_errors = 0
    if permissions_check:
        # /dev/nvidia-caps is a directory and is not writable for a normal user.
        nodes = [node for node in Path("/dev").glob("nvidia*") if node.is_char_device()]
        if not nodes:
            permission_errors += 1
        for node in nodes:
            if not os.access(node, os.R_OK | os.W_OK):
                permission_errors += 1
    # Driver version compliance: the share of the three driver components (loaded kernel
    # module, nvidia-smi/NVML, libcuda) whose version meets the workbook driver minimum.
    # Whether they agree with each other is metric #2, so it is not repeated here.
    driver_components = [module_ver, version_token(driver_ver), soname_ver]
    compliance_checks = [bool(item) and version_at_least(item, expected_driver) for item in driver_components]
    driver_compliance = 100.0 * sum(compliance_checks) / len(compliance_checks)
    header = [
        "sample_index", "status",
        "cuda_package_version_mismatches_count",
        "cuda_major_version_mismatch_count",
        "nvidia_kernel_module_driver_version_mismatches_count",
        "vbios_string_present",
        "driver_compliance_percent",
        "required_library_path_device_permission_errors",
        "error_message",
    ]
    row = {
        "status": "ok" if vbios_present == 1.0 and stack_mismatches == 0 else "error",
        "cuda_package_version_mismatches_count": float(package_mismatch),
        "cuda_major_version_mismatch_count": float(cuda_mismatch),
        "nvidia_kernel_module_driver_version_mismatches_count": stack_mismatches,
        "vbios_string_present": vbios_present,
        "driver_compliance_percent": driver_compliance,
        "required_library_path_device_permission_errors": float(permission_errors),
        "error_message": "" if vbios else "VBIOS Version missing from nvidia-smi -q",
    }
    write_csv(args.raw_file, header, [row])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
