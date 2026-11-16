#!/usr/bin/env python3
# File: scripts/setup_bundle.py
# Description: Map Execution Domain + GPU Vendor to a run_setup.sh skeleton. No Framework substring matching.
from __future__ import annotations

CPU_SYSTEM = "cpu-system"
ROCM = "rocm"
NVIDIA = "nvidia"

_DOMAIN_VENDOR = {
    ("CPU / System", "AMD"): CPU_SYSTEM,
    ("CPU / System", "NVIDIA"): CPU_SYSTEM,
    ("Validation / Correctness", "AMD"): ROCM,
    ("Validation / Correctness", "NVIDIA"): NVIDIA,
    ("Memory / Transfer", "AMD"): ROCM,
    ("Memory / Transfer", "NVIDIA"): NVIDIA,
    ("GPU Compute / ROCm", "AMD"): ROCM,
    ("GPU Compute / CUDA", "NVIDIA"): NVIDIA,
    ("LLM Serving", "AMD"): ROCM,
    ("LLM Serving", "NVIDIA"): NVIDIA,
    ("End-to-End Pipeline", "AMD"): ROCM,
    ("End-to-End Pipeline", "NVIDIA"): NVIDIA,
}

SKELETON_REL = {
    CPU_SYSTEM: "scripts/templates/setup_cpu_system_skeleton.sh",
    ROCM: "scripts/templates/setup_rocm_reboot_skeleton.sh",
    NVIDIA: "scripts/templates/setup_nvidia_skeleton.sh",
}


def setup_bundle(fields: dict[str, str], *, force_rocm: bool = False) -> str:
    domain = str(fields.get("Execution Domain", "")).strip()
    vendor = str(fields.get("GPU Vendor", "")).strip()
    vendor_key = vendor.casefold()
    if vendor_key == "amd":
        vendor_norm = "AMD"
    elif vendor_key == "nvidia":
        vendor_norm = "NVIDIA"
    else:
        raise ValueError(f"GPU Vendor {vendor!r} is not AMD or NVIDIA.")
    if force_rocm and vendor_norm == "NVIDIA":
        raise ValueError("GPU Vendor NVIDIA cannot materialize the ROCm setup skeleton.")
    if force_rocm and domain != "CPU / System":
        return ROCM
    bundle = _DOMAIN_VENDOR.get((domain, vendor_norm))
    if not bundle:
        raise ValueError(
            f"No setup skeleton for Execution Domain {domain!r} + GPU Vendor {vendor!r}."
        )
    return bundle
