#!/usr/bin/env bash
# File:         scripts/lib/rocm_install.sh
# Version:      2.0.0
# Maintainer: AI Agent GPU Benchmark Repo Generator
# Date:         2026-08-26
# Description:  Thin Ubuntu-release dispatcher for protected ROCm install functions.
#               Callers continue to `source scripts/lib/rocm_install.sh`. This file
#               does not implement install steps; it sources
#               scripts/lib/rocm_install_24_04.sh (Ubuntu 24.04 / noble, ROCm 10.1.0, amdgpu 31.60)
#               or scripts/lib/rocm_install_26_04.sh (Ubuntu 26.04 / resolute, ROCm 10.1.0, amdgpu 31.60).
#               Function names and signatures are identical in both libraries.
# Execution:    source scripts/lib/rocm_install.sh  (not executed directly)
# Options:      ROCM_INSTALL_UBUNTU_VERSION may override /etc/os-release detection.
# Requirements: Ubuntu 24.04 or Ubuntu 26.04; sudo access; internet.
# Environment:  Bare metal or ROCm-capable VM; not required inside a ROCm Docker image.
# Dependencies: scripts/lib/rocm_install_24_04.sh, scripts/lib/rocm_install_26_04.sh
# Variables:
#   ROCM_INSTALL_UBUNTU_VERSION   Explicit Ubuntu VERSION_ID, e.g. 26.04
#   UBUNTU_CODENAME               Used as a fallback when VERSION_ID is unavailable
#   ROCM_VERSION                  Used as a fallback when VERSION_ID is unavailable
# Repository:   gpu-bench / sys-bench workload template
# License:      Apache-2.0

_rocm_dispatch_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Every privileged command in the ROCm libraries goes through run_noninteractive_root
# (no sudo pty, terminal stdin replaced, SIGTTOU ignored). See noninteractive_root.sh.
# shellcheck disable=SC1091
source "${_rocm_dispatch_dir}/noninteractive_root.sh"
# rocm_install_runtime reloads amdgpu in place of its post-install reboot and
# reboots only if the reload cannot be verified. See amdgpu_reload.sh.
# shellcheck disable=SC1091
source "${_rocm_dispatch_dir}/amdgpu_reload.sh"

_rocm_detect_ubuntu_version() {
    if [[ -n "${ROCM_INSTALL_UBUNTU_VERSION:-}" ]]; then
        printf '%s\n' "${ROCM_INSTALL_UBUNTU_VERSION}"
        return
    fi
    if [[ -r /etc/os-release ]]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        printf '%s\n' "${VERSION_ID:-}"
        return
    fi
    printf '%s\n' ""
}

_rocm_ubuntu_version="$(_rocm_detect_ubuntu_version)"
case "${_rocm_ubuntu_version}" in
    26.04*)
        # shellcheck disable=SC1091
        source "${_rocm_dispatch_dir}/rocm_install_26_04.sh"
        ;;
    24.04*|22.04*)
        # shellcheck disable=SC1091
        source "${_rocm_dispatch_dir}/rocm_install_24_04.sh"
        ;;
    *)
        case "${UBUNTU_CODENAME:-}" in
            resolute)
                # shellcheck disable=SC1091
                source "${_rocm_dispatch_dir}/rocm_install_26_04.sh"
                ;;
            noble|jammy)
                # shellcheck disable=SC1091
                source "${_rocm_dispatch_dir}/rocm_install_24_04.sh"
                ;;
            *)
                if [[ "${ROCM_VERSION:-}" == "7.14" ]]; then
                    # shellcheck disable=SC1091
                    source "${_rocm_dispatch_dir}/rocm_install_26_04.sh"
                else
                    # shellcheck disable=SC1091
                    source "${_rocm_dispatch_dir}/rocm_install_24_04.sh"
                fi
                ;;
        esac
        ;;
esac
