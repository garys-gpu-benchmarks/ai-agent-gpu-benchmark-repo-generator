#!/usr/bin/env bash
# File: scripts/lib/amdgpu_reload.sh
# Version: 1.1.0
# Maintainer: AI Agent GPU Benchmark Repo Generator
# Date: 2026-10-01
# Description: amdgpu_reload_instead_of_reboot -- after the ROCm runtime install,
#              reload the amdgpu kernel module in place of the post-install reboot,
#              verify that every GPU came back, and report failure so the caller
#              reboots exactly as before.
# Execution: sourced by scripts/lib/rocm_install.sh; called by rocm_install_runtime in
#            scripts/lib/rocm_install_24_04.sh and scripts/lib/rocm_install_26_04.sh.
# Options: amdgpu_reload_instead_of_reboot dkms|firmware
#            dkms      Ubuntu 24.04: amdgpu-dkms built AMD's own amdgpu.ko for the
#                      running kernel; the reload swaps Ubuntu's in-box driver for it.
#            firmware  Ubuntu 26.04: --no-dkms, Ubuntu's in-box driver is kept; the
#                      reload makes it load the new amdgpu-dkms-firmware files.
# Requirements: Linux; root or sudo; modprobe; run_noninteractive_root (noninteractive_root.sh).
# Variables:
#   ROCM_RELOAD_INSTEAD_OF_REBOOT  1 (default) try the reload; 0 always reboot (old behavior).
#   AMDGPU_UNLOAD_TIMEOUT          seconds allowed for "modprobe -r amdgpu" (default 180).
#   AMDGPU_LOAD_TIMEOUT            seconds allowed for "modprobe amdgpu" (default 600).
#   AMDGPU_INIT_WAIT               seconds to wait for every GPU to appear in KFD (default 300).
# Repository: gpu-bench/sys-bench template
# License: Apache-2.0
#
# Return value: 0 = driver reloaded and verified, no reboot needed.
#               1 = not reloaded or not verified; the caller must reboot.
# A reboot after a failed reload is never worse than the reboot setup used to do
# unconditionally: it reads the same driver and firmware files from disk.
#
# Safety rules:
#   * The reload is skipped (reboot instead) when no AMD GPU is on the PCI bus, when
#     amdgpu is in use (refcnt > 0), or when modprobe is missing.
#   * A text console drawn on a framebuffer (fbcon) is released before the unload
#     and bound again afterwards. On the Ubuntu 26.04 MI300X VM, "modprobe -r
#     amdgpu" with the console still on amdgpu's framebuffer did not finish in
#     180 s (rc=137, so setup rebooted); after "echo 0 > .../vtcon0/bind" the
#     same unload took 0.5 s (2026-10-20).
#   * modprobe runs in the background with a deadline. A modprobe stuck in the kernel
#     cannot hang setup; setup gives up and reboots.
#   * Success requires every AMD GPU PCI device to show up as a KFD compute node
#     and, for dkms, the loaded module to be the DKMS build on disk.

[[ -n "${_AMDGPU_RELOAD_SH:-}" ]] && return 0
_AMDGPU_RELOAD_SH=1

# Test hook: tests point this at a fake sysfs tree. Production uses /sys.
_AMDGPU_RELOAD_SYS="${_AMDGPU_RELOAD_SYS:-/sys}"

_amdgpu_reload_log() {
    if declare -f _rocm_log >/dev/null 2>&1; then _rocm_log "$*"; else echo "[amdgpu_reload] $*"; fi
}
_amdgpu_reload_warn() {
    if declare -f _rocm_warn >/dev/null 2>&1; then _rocm_warn "$*"; else echo "[amdgpu_reload] WARN: $*" >&2; fi
}

# AMD GPUs on the PCI bus: vendor 0x1002, class display (0x03xxxx) or processing
# accelerator (0x12xxxx). The HDMI audio function (0x0403xx) is not counted.
amdgpu_pci_gpu_count() {
    local dev vendor class n=0
    for dev in "${_AMDGPU_RELOAD_SYS}"/bus/pci/devices/*; do
        [[ -r "${dev}/vendor" && -r "${dev}/class" ]] || continue
        vendor="$(<"${dev}/vendor")"
        class="$(<"${dev}/class")"
        [[ "${vendor}" == "0x1002" ]] || continue
        case "${class}" in
            0x03*|0x12*) n=$((n + 1)) ;;
        esac
    done
    echo "${n}"
}

# GPUs the ROCm runtime can use: KFD topology nodes with compute units
# (simd_count > 0). CPU nodes have simd_count 0. A partitioned MI300X (CPX)
# reports more KFD nodes than PCI devices, so callers compare with >=.
amdgpu_kfd_gpu_count() {
    local props simd n=0
    for props in "${_AMDGPU_RELOAD_SYS}"/class/kfd/kfd/topology/nodes/*/properties; do
        [[ -r "${props}" ]] || continue
        simd="$(awk '$1 == "simd_count" { print $2; exit }' "${props}")"
        [[ "${simd:-0}" =~ ^[0-9]+$ ]] || continue
        if (( simd > 0 )); then
            n=$((n + 1))
        fi
    done
    echo "${n}"
}

# 0 while the process exists and is not a zombie. Reads /proc/<pid>/stat, which
# works for a root-owned sudo child where "kill -0" would fail with EPERM.
_amdgpu_reload_running() {
    local stat state
    stat="$(cat "/proc/$1/stat" 2>/dev/null)" || return 1
    state="${stat##*) }"
    state="${state%% *}"
    [[ -n "${state}" && "${state}" != "Z" && "${state}" != "X" ]]
}

# Run a privileged command with a deadline. Returns the command's exit code, or
# 124 if it is still running when the deadline passes. The stuck command is left
# alone: if it is blocked in the kernel, nothing can kill it, and the reboot that
# follows clears it.
_amdgpu_reload_run_with_deadline() {
    local limit="$1" pid waited=0
    shift
    run_noninteractive_root "$@" &
    pid=$!
    while _amdgpu_reload_running "${pid}"; do
        if (( waited >= limit )); then
            _amdgpu_reload_warn "'$*' still running after ${limit}s; giving up on the reload."
            return 124
        fi
        sleep 1
        waited=$((waited + 1))
    done
    wait "${pid}"
}

_amdgpu_reload_module_loaded() {
    [[ -d "${_AMDGPU_RELOAD_SYS}/module/amdgpu" ]]
}

# dkms: the loaded amdgpu must be the DKMS build that modprobe now prefers
# (/lib/modules/<kernel>/updates/dkms/). The loaded module's srcversion (or
# version) must match the file modinfo resolves.
_amdgpu_reload_verify_dkms() {
    local path loaded ondisk
    path="$(modinfo -n amdgpu 2>/dev/null || true)"
    if [[ "${path}" != *"/updates/"* ]]; then
        _amdgpu_reload_warn "modinfo resolves amdgpu to '${path:-nothing}', not the DKMS build under /lib/modules/$(uname -r)/updates/. amdgpu-dkms may not have built for this kernel."
        return 1
    fi
    loaded="$(cat "${_AMDGPU_RELOAD_SYS}/module/amdgpu/srcversion" 2>/dev/null || true)"
    ondisk="$(modinfo -F srcversion amdgpu 2>/dev/null || true)"
    if [[ -z "${loaded}" || -z "${ondisk}" ]]; then
        loaded="$(cat "${_AMDGPU_RELOAD_SYS}/module/amdgpu/version" 2>/dev/null || true)"
        ondisk="$(modinfo -F version amdgpu 2>/dev/null || true)"
    fi
    if [[ -z "${loaded}" || -z "${ondisk}" ]]; then
        _amdgpu_reload_warn "Cannot read srcversion or version for the loaded amdgpu; cannot confirm the DKMS driver is the one running."
        return 1
    fi
    if [[ "${loaded}" != "${ondisk}" ]]; then
        _amdgpu_reload_warn "Loaded amdgpu (${loaded}) is not the DKMS build on disk (${ondisk})."
        return 1
    fi
    _amdgpu_reload_log "Loaded amdgpu is the DKMS build: ${path}"
}

# Firmware load errors logged since the reload. These are reported, not treated as
# failure: a reboot reads the same firmware files, so it would not fix them. The
# KFD node check is what decides success.
_amdgpu_reload_report_firmware_errors() {
    local since="$1" lines
    command -v journalctl >/dev/null 2>&1 || return 0
    lines="$(run_noninteractive_root journalctl -k --since "@${since}" --no-pager -q 2>/dev/null \
        | grep -i -E 'amdgpu' | grep -i -E 'firmware.*(fail|error)|(fail|error).*firmware' || true)"
    if [[ -n "${lines}" ]]; then
        _amdgpu_reload_warn "amdgpu logged firmware messages during the reload (all GPUs initialized):"
        printf '%s\n' "${lines}" | head -20 >&2
    fi
}

# Framebuffer consoles this run unbound, so they can be bound again afterwards.
_AMDGPU_RELOAD_UNBOUND=()

# Unbind every bound framebuffer console (vtconsole named "frame buffer device").
# The console falls back to the dummy device; nothing else changes.
_amdgpu_reload_release_consoles() {
    local con name
    for con in "${_AMDGPU_RELOAD_SYS}"/class/vtconsole/vtcon*; do
        [[ -r "${con}/name" && -r "${con}/bind" ]] || continue
        name="$(<"${con}/name")"
        [[ "${name}" == *"frame buffer"* && "$(<"${con}/bind")" == "1" ]] || continue
        if printf '0\n' | run_noninteractive_root tee "${con}/bind" >/dev/null 2>&1; then
            _AMDGPU_RELOAD_UNBOUND+=("${con}")
            _amdgpu_reload_log "Released the framebuffer console ${con##*/} so amdgpu can unload."
        else
            _amdgpu_reload_warn "Could not release the framebuffer console ${con##*/}; the unload may stall."
        fi
    done
}

# Bind the consoles released above again (after the reload, or after it failed).
_amdgpu_reload_restore_consoles() {
    local con
    for con in "${_AMDGPU_RELOAD_UNBOUND[@]}"; do
        printf '1\n' | run_noninteractive_root tee "${con}/bind" >/dev/null 2>&1 ||
            _amdgpu_reload_warn "Could not bind the console ${con##*/} again; the next boot restores it."
    done
    _AMDGPU_RELOAD_UNBOUND=()
}

amdgpu_reload_instead_of_reboot() {
    local rc=0
    _amdgpu_reload_attempt "$@" || rc=$?
    _amdgpu_reload_restore_consoles
    return "${rc}"
}

_amdgpu_reload_attempt() {
    local mode="${1:-firmware}"
    local pci kfd refcnt since waited=0 rc newest running

    if [[ "${ROCM_RELOAD_INSTEAD_OF_REBOOT:-1}" != "1" ]]; then
        _amdgpu_reload_log "ROCM_RELOAD_INSTEAD_OF_REBOOT=${ROCM_RELOAD_INSTEAD_OF_REBOOT}; rebooting instead of reloading amdgpu."
        return 1
    fi
    if ! command -v modprobe >/dev/null 2>&1; then
        _amdgpu_reload_warn "modprobe not found; rebooting instead."
        return 1
    fi
    pci="$(amdgpu_pci_gpu_count)"
    if (( pci == 0 )); then
        _amdgpu_reload_warn "No AMD GPU found on the PCI bus; rebooting instead."
        return 1
    fi

    if [[ "${mode}" == "dkms" && "$(modinfo -n amdgpu 2>/dev/null || true)" != *"/updates/"* ]]; then
        _amdgpu_reload_warn "No DKMS amdgpu for kernel $(uname -r) under /lib/modules/$(uname -r)/updates/; nothing to reload into. Rebooting instead."
        return 1
    fi

    running="$(uname -r)"
    newest="$(ls -1 /lib/modules 2>/dev/null | sort -V | tail -1 || true)"
    if [[ -n "${newest}" && "${newest}" != "${running}" ]]; then
        _amdgpu_reload_log "Note: kernel ${newest} is installed but ${running} is running. The reload uses ${running}; the next boot will use ${newest}."
    fi

    # Keep the next real boot on the same driver/firmware the reload loads.
    if command -v update-initramfs >/dev/null 2>&1; then
        _amdgpu_reload_log "Updating initramfs so the next boot loads the same amdgpu and firmware."
        run_noninteractive_root update-initramfs -u \
            || _amdgpu_reload_warn "update-initramfs -u failed; continuing (a reboot would use the same initramfs)."
    fi

    if _amdgpu_reload_module_loaded; then
        refcnt="$(cat "${_AMDGPU_RELOAD_SYS}/module/amdgpu/refcnt" 2>/dev/null || echo 0)"
        if [[ "${refcnt}" != "0" ]]; then
            _amdgpu_reload_warn "amdgpu is in use (refcnt=${refcnt}); cannot unload it. Rebooting instead."
            return 1
        fi
        _amdgpu_reload_release_consoles
        _amdgpu_reload_log "Unloading amdgpu (modprobe -r amdgpu)."
        rc=0
        _amdgpu_reload_run_with_deadline "${AMDGPU_UNLOAD_TIMEOUT:-180}" modprobe -r amdgpu || rc=$?
        if (( rc != 0 )) || _amdgpu_reload_module_loaded; then
            _amdgpu_reload_warn "modprobe -r amdgpu failed (rc=${rc}); rebooting instead."
            return 1
        fi
    fi

    since="$(date +%s)"
    _amdgpu_reload_log "Loading amdgpu (modprobe amdgpu)."
    rc=0
    _amdgpu_reload_run_with_deadline "${AMDGPU_LOAD_TIMEOUT:-600}" modprobe amdgpu || rc=$?
    if (( rc != 0 )); then
        _amdgpu_reload_warn "modprobe amdgpu failed (rc=${rc}); rebooting instead."
        return 1
    fi
    if command -v udevadm >/dev/null 2>&1; then
        run_noninteractive_root udevadm settle --timeout=60 || true
    fi

    kfd="$(amdgpu_kfd_gpu_count)"
    while (( kfd < pci && waited < ${AMDGPU_INIT_WAIT:-300} )); do
        sleep 5
        waited=$((waited + 5))
        kfd="$(amdgpu_kfd_gpu_count)"
    done
    if (( kfd < pci )); then
        _amdgpu_reload_warn "Only ${kfd} of ${pci} AMD GPUs initialized after the reload; rebooting instead."
        return 1
    fi
    _amdgpu_reload_log "All ${pci} AMD GPU(s) initialized after the reload (${kfd} KFD compute node(s))."

    if [[ "${mode}" == "dkms" ]]; then
        _amdgpu_reload_verify_dkms || { _amdgpu_reload_warn "Rebooting instead."; return 1; }
    fi
    _amdgpu_reload_report_firmware_errors "${since}"
    _amdgpu_reload_log "amdgpu reloaded and verified; no reboot needed."
    return 0
}
