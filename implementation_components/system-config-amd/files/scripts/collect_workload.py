#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import os
import re
import subprocess
from pathlib import Path

import yaml


def pv(params, key, profile, default=""):
    raw = params.get(key, default)
    if isinstance(raw, dict):
        return raw.get(profile, raw.get("smoke", default))
    return default if raw is None else raw


def as_list(value):
    return [p.strip() for p in str(value or "").replace(";", ",").split(",") if p.strip()]


def duration_seconds(raw):
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return 5.0
    return number / 1000.0 if number >= 10000 else number


def load_params(path):
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return cfg.get("sweep") or {}


def write_csv(path, header, rows):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=header, extrasaction="ignore", lineterminator=chr(10))
    writer.writeheader()
    rows = list(rows)
    if len(rows) == 1:
        rows.append(dict(rows[0]))
    for index, row in enumerate(rows):
        writer.writerow({"sample_index": index, **row})
    text = buf.getvalue()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")
    print(text, end="")
    return text


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--raw-file", required=True)
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--device", default="gpu")
    parser.add_argument("--output-format", default="csv")
    return parser.parse_args()

def run_command(command):
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except FileNotFoundError:
        return 127, f"missing:{command[0]}"
    return completed.returncode, (completed.stdout or "") + "\n" + (completed.stderr or "")


# Ubuntu 26.04 TheRock packages replace the older rocm-core / rocm-smi names.
PACKAGE_ALIASES = {
    "rocm-core": (
        "rocm-core",
        "amdrocm10.1",
        "amdrocm10.1-gfx942",
        "amdrocm-core-dev10.1-gfx942",
        "amdrocm",
        "amdrocm-core",
        "amdrocm-base7.14",
    ),
    "rocm-smi": (
        "rocm-smi",
        "amdrocm-amdsmi10.1",
        "amdrocm10.1",
        "amdrocm10.1-gfx942",
        "amdrocm-base7.14",
        "amdrocm",
    ),
    "amdrocm10.1": ("amdrocm10.1", "amdrocm10.1-gfx942", "rocm-core"),
}


def package_version(name):
    candidates = PACKAGE_ALIASES.get(name, (name,))
    if name not in candidates:
        candidates = (name, *candidates)
    for candidate in candidates:
        completed = subprocess.run(
            ["dpkg-query", "-W", "-f=${Version}", candidate],
            check=False,
            capture_output=True,
            text=True,
        )
        version = (completed.stdout or "").strip() if completed.returncode == 0 else ""
        if version:
            return version
    # Ubuntu 24.04's rocm-smi package is 5.7 and replaces /opt/rocm/bin/rocm-smi.
    # The ROCm tree itself is the requested stack when that executable is present.
    root = Path("/opt/rocm")
    for relative in ("bin/amd-smi", "bin/rocm-smi", "core-10.1/bin/amd-smi", "core-10.1/bin/hipcc"):
        if name in {"rocm-smi", "rocm-core", "amdrocm10.1"} and (root / relative).is_file():
            return "opt-rocm"
    return ""


def modinfo_field(text, field):
    prefix = field.lower() + ":"
    for line in text.splitlines():
        if line.strip().lower().startswith(prefix):
            return line.split(":", 1)[1].strip()
    return ""


def version_field_matches(expected, actual):
    """Match the modinfo version field itself, not a substring of the whole dump."""
    expected = (expected or "").strip()
    actual = (actual or "").strip()
    if not expected or not actual:
        return False
    if actual == expected:
        return True
    return actual.startswith(expected + ".") or actual.startswith(expected + "-")


def kernel_release_matches(expected, uname_r):
    expected = (expected or "").strip()
    uname_r = (uname_r or "").strip()
    if not expected or not uname_r:
        return False
    return uname_r == expected or uname_r.startswith(expected + "-") or uname_r.startswith(expected + ".")


def firmware_revision():
    """Detected GPU firmware/VBIOS revision of the first card, or "". Recorded in
    firmware_version.txt for information only; it is not a metric or a gate."""
    for pattern in ("card*/device/fw_version", "card*/device/vbios_version"):
        for path in sorted(Path("/sys/class/drm").glob(pattern)):
            try:
                text = path.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                continue
            if text and text.lower() not in {"n/a", "unknown"}:
                return text
    for command in (["amd-smi", "firmware"], ["rocm-smi", "--showfwinfo"], ["rocm-smi", "--showvbios"]):
        _code, text = run_command(command)
        match = re.search(r"(?:firmware|VBIOS)\s+version\s*[:=]\s*(\S+)", text, re.I)
        if match and match.group(1).lower() not in {"n/a", "unknown"}:
            return match.group(1)
    return ""


def driver_package_matches(expected: str) -> bool:
    """amdgpu 31.60.0 is the product version. The DKMS package encodes it as 31600000."""
    expected = (expected or "").strip()
    if not expected:
        return False
    completed = subprocess.run(
        ["dpkg-query", "-W", "-f=${Version}", "amdgpu-dkms"],
        check=False,
        capture_output=True,
        text=True,
    )
    version = (completed.stdout or "").strip() if completed.returncode == 0 else ""
    if not version:
        return False
    if expected in version:
        return True
    compact = expected.replace(".", "")
    return bool(compact) and compact in version.replace(".", "")


def main() -> int:
    args = parse_args()
    sweep = load_params(args.config)
    expected_kernel = str(sweep.get("kernel_version", "6.8.0"))
    expected_driver = str(sweep.get("driver_version", "6"))
    # Read for the record; not compared yet (kernel/runtime checks live elsewhere).
    _expected_rocm = str(sweep.get("rocm_version", "10.1.0"))
    packages = [item.strip() for item in str(sweep.get("required_packages", "rocm-core,rocm-smi")).split(",") if item.strip()]
    permissions_check = str(sweep.get("permissions_check", "true")).lower() in {"1", "true", "yes"}
    uname = os.uname().release
    amdgpu = run_command(["modinfo", "amdgpu"])[1]
    # kernel_driver_mismatch_count is the kernel release only. The amdgpu
    # version field is driver compliance, not part of this count.
    kernel_mismatch = 0 if kernel_release_matches(expected_kernel, uname) else 1
    # In-tree amdgpu (Ubuntu 26.04 --no-dkms) has no modinfo version: field.
    # That is not a kernel mismatch. Say so instead of leaving compliance blank.
    driver_version = modinfo_field(amdgpu, "version")
    if driver_package_matches(expected_driver):
        driver_mismatch = 0
        driver_compliance = 100.0
        driver_available = 1.0
    elif not driver_version:
        driver_mismatch = 0
        driver_compliance = "na (in-tree amdgpu has no version)"
        driver_available = ""
    else:
        driver_mismatch = 0 if version_field_matches(expected_driver, driver_version) else 1
        driver_compliance = 100.0 if driver_mismatch == 0 else 0.0
        driver_available = 1.0
    package_mismatch = 0
    for name in packages:
        if not package_version(name):
            package_mismatch += 1
    permission_errors = 0
    if permissions_check:
        for node in (Path("/dev/kfd"), Path("/dev/dri/renderD128")):
            if not node.exists() or not os.access(node, os.R_OK):
                permission_errors += 1
    Path(args.run_dir).mkdir(parents=True, exist_ok=True)
    (Path(args.run_dir) / "firmware_version.txt").write_text((firmware_revision() or "not detected") + "\n", encoding="utf-8")
    checks = []
    for command in (["rvs", "--version"], ["rocminfo"], ["rocm-smi"], ["amd-smi", "static"], ["uname", "-a"], ["modinfo", "amdgpu"], ["hipcc", "--version"]):
        checks.append((command[0], *run_command(command)))
    header = [
        "sample_index", "check_name", "rocm_package_mismatch_count",
        "kernel_driver_mismatch_count", "kernel_mismatch_count",
        "driver_mismatch_count", "driver_version_available",
        "driver_compliance_percent", "permission_error_count",
    ]
    rows = []
    for name, code, text in checks:
        rows.append({
            "check_name": name,
            "rocm_package_mismatch_count": float(package_mismatch),
            "kernel_driver_mismatch_count": float(kernel_mismatch),
            "kernel_mismatch_count": float(kernel_mismatch),
            "driver_mismatch_count": float(driver_mismatch),
            "driver_version_available": driver_available,
            "driver_compliance_percent": driver_compliance,
            "permission_error_count": float(permission_errors),
        })
        (Path(args.run_dir) / f"{name}.txt").write_text(text, encoding="utf-8")
    write_csv(args.raw_file, header, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
