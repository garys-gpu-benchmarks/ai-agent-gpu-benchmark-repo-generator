#!/usr/bin/env bash
# File:         scripts/lib/rocm_install_26_04.sh
# Version:      1.0.0
# Maintainer: AI Agent GPU Benchmark Repo Generator
# Date:         2026-08-25
# Description:  Authoritative, idempotent ROCm installation functions for gpu-bench-* /
#               sys-bench-* benchmark repositories, targeting Ubuntu 26.04 (resolute) /
#               ROCm 10.1.0. Installs amdgpu-dkms 31.60 from repo.radeon.com and
#               amdrocm10.1 userspace from stable.repo.amd.com. Function names match
#               scripts/lib/rocm_install_24_04.sh so callers source one file per OS.
# Execution:    source scripts/lib/rocm_install_26_04.sh  (not executed directly)
# Options:      Environment variables below may override the pinned defaults.
# Requirements: Ubuntu 26.04 (resolute); sudo access; internet.
# Environment:  Bare metal or ROCm-capable VM; not required inside a ROCm Docker image.
# Dependencies: curl, wget, apt; sourced after scripts/lib/common.sh for log helpers.
# Variables:
#   ROCM_VERSION             ROCm version string                      (default: 10.1.0)
#   AMDGPU_DRIVER_VERSION    amdgpu driver product version            (default: 31.60)
#   GFX_TARGET               GPU architecture token, e.g. gfx942      (default: gfx942)
#   UBUNTU_CODENAME          Ubuntu release codename                  (default: resolute)
#   ROCM_APT_DISTRO          stable.repo.amd.com distro directory     (default: ubuntu2604)
# Repository:   gpu-bench / sys-bench workload template
# License:      Apache-2.0

_rocm_kernel_guard="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/keep_running_kernel.sh"
if [[ -f "${_rocm_kernel_guard}" ]]; then
  # shellcheck disable=SC1090
  source "${_rocm_kernel_guard}"
fi
unset _rocm_kernel_guard

# ────────────────────────────────────────────────────────────────────────────
# Version pins — override with environment variables before sourcing if needed.
# ────────────────────────────────────────────────────────────────────────────
ROCM_VERSION="${ROCM_VERSION:-10.1.0}"
UBUNTU_CODENAME="${UBUNTU_CODENAME:-resolute}"
GFX_TARGET="${GFX_TARGET:-gfx942}"
AMDGPU_DRIVER_VERSION="${AMDGPU_DRIVER_VERSION:-31.60}"
AMDGPU_INSTALLER_VERSION="${AMDGPU_INSTALLER_VERSION:-31.60}"
AMDGPU_INSTALLER_BUILD="${AMDGPU_INSTALLER_BUILD:-316000-1}"
ROCM_APT_DISTRO="${ROCM_APT_DISTRO:-ubuntu2604}"
ROCM_META_PACKAGE="${ROCM_META_PACKAGE:-amdrocm10.1-${GFX_TARGET}}"
ROCM_DEV_PACKAGE="${ROCM_DEV_PACKAGE:-amdrocm-core-dev10.1-${GFX_TARGET}}"
RVS_PACKAGE="${RVS_PACKAGE:-amdrocm10-rvs}"
RVS_PACKAGE_VERSION="${RVS_PACKAGE_VERSION:-1.6.131-844}"

# amdgpu-install .deb is unused by the apt-repo path. Kept so a manual download
# still points at the 31.60 package:
#   https://repo.radeon.com/amdgpu-install/31.60/ubuntu/resolute/amdgpu-install_31.60.316000-1_all.deb
_AMDGPU_DEB_FILE="amdgpu-install_${AMDGPU_INSTALLER_VERSION}.${AMDGPU_INSTALLER_BUILD}_all.deb"
AMDGPU_INSTALLER="${AMDGPU_INSTALLER:-https://repo.radeon.com/amdgpu-install/${AMDGPU_INSTALLER_VERSION}/ubuntu/${UBUNTU_CODENAME}/${_AMDGPU_DEB_FILE}}"

# ────────────────────────────────────────────────────────────────────────────
# Internal helpers (use log_ functions from common.sh when available, fall back
# to plain echo otherwise so this library is safe to source standalone).
# ────────────────────────────────────────────────────────────────────────────
_rocm_log()  { if declare -f log_info  >/dev/null 2>&1; then log_info  "$*"; else echo "[rocm_install_26_04] $*"; fi; }
_rocm_warn() { if declare -f log_warn  >/dev/null 2>&1; then log_warn  "$*"; else echo "[rocm_install_26_04] WARN: $*" >&2; fi; }
_rocm_die()  { if declare -f log_error >/dev/null 2>&1; then log_error "$*"; else echo "[rocm_install_26_04] ERROR: $*" >&2; fi; exit 1; }

_rocm_status_phase() {
    local text="$1"
    if declare -f install_status_log_phase >/dev/null 2>&1; then
        install_status_log_phase "${text}"
    fi
}

_rocm_status_step() {
    local step_no="$1"
    local command_text="$2"
    if declare -f install_status_log_step >/dev/null 2>&1; then
        install_status_log_step "${step_no}" "${command_text}"
    fi
}

ROCM_SOURCE_ROOT="${ROCM_SOURCE_ROOT:-${REPO_ROOT:-$(pwd)}/third_party}"
ROCBLAS_SOURCE_DIR="${ROCBLAS_SOURCE_DIR:-${ROCM_SOURCE_ROOT}/rocBLAS}"
RVS_SOURCE_DIR="${RVS_SOURCE_DIR:-${ROCM_SOURCE_ROOT}/ROCmValidationSuite}"
mkdir -p "${ROCM_SOURCE_ROOT}"

# NOTE ON SOURCE LOCATIONS: the manually-tested command log (spreadsheet) uses
# "cd ~" before cloning ROCmValidationSuite and rocBLAS, i.e. $HOME/ROCmValidationSuite
# and $HOME/rocBLAS. This library deliberately clones into a repository-local
# third_party/ directory instead (ROCM_SOURCE_ROOT, same convention already used by
# rocm_install_24_04.sh) so multiple generated benchmark repos on the same machine
# don't collide in $HOME. Functionally equivalent; only the location differs.

_rocm_append_bashrc_once() {
    local line="$1"
    local bashrc="${HOME}/.bashrc"
    touch "${bashrc}"
    if ! grep -Fq "${line}" "${bashrc}"; then
        echo "${line}" >> "${bashrc}"
        _rocm_log "Appended to .bashrc: ${line}"
    else
        _rocm_log ".bashrc already contains: ${line}"
    fi
}

_rocm_download_installer() {
    if [[ -f "${_AMDGPU_DEB_FILE}" ]]; then
        _rocm_log "amdgpu-install .deb already downloaded: ${_AMDGPU_DEB_FILE}"
        return 0
    fi
    _rocm_log "Downloading amdgpu-install ${AMDGPU_INSTALLER_VERSION} for ${UBUNTU_CODENAME}..."
    wget -O "${_AMDGPU_DEB_FILE}" "${AMDGPU_INSTALLER}" \
        || _rocm_die "Failed to download amdgpu-install from ${AMDGPU_INSTALLER}"
    _rocm_log "Download complete: ${_AMDGPU_DEB_FILE}"
}

_rocm_apt_install_local_deb_noninteractive() {
    local deb_path="$1"
    run_noninteractive_root DEBIAN_FRONTEND=noninteractive apt-get install -y \
        -o Dpkg::Options::=--force-confdef \
        -o Dpkg::Options::=--force-confold \
        "${deb_path}"
}

_rocm_resolve_rocm_bin() {
    if [[ -d "/opt/rocm/bin" ]]; then
        echo "/opt/rocm/bin"
        return 0
    fi
    local candidate
    local best=""
    for candidate in /opt/rocm-*/bin; do
        if [[ -d "${candidate}" ]]; then
            best="${candidate}"
        fi
    done
    if [[ -n "${best}" ]]; then
        echo "${best}"
        return 0
    fi
    return 1
}

_rocm_runtime_stage_file() {
    echo "${ROCM_RUNTIME_STAGE_FILE:-.rocm_runtime_stage.env}"
}

_rocm_runtime_stage_get() {
    local stage_file
    stage_file="$(_rocm_runtime_stage_file)"
    if [[ -f "${stage_file}" ]]; then
        # shellcheck disable=SC1090
        source "${stage_file}"
        echo "${ROCM_RUNTIME_STAGE:-stage1}"
        return
    fi
    echo "stage1"
}

_rocm_runtime_stage_set() {
    local next_stage="$1"
    local stage_file
    stage_file="$(_rocm_runtime_stage_file)"
    {
        echo "ROCM_RUNTIME_STAGE=${next_stage}"
        echo "ROCM_RUNTIME_SAVED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } > "${stage_file}"
    _rocm_log "Saved runtime stage to ${stage_file}: ${next_stage}"
}

_rocm_runtime_stage_clear() {
    local stage_file
    stage_file="$(_rocm_runtime_stage_file)"
    if [[ -f "${stage_file}" ]]; then
        rm -f "${stage_file}"
        _rocm_log "Cleared runtime stage file: ${stage_file}"
    fi
}

# Boot ID of the running Linux boot (changes on every boot). A postponed reboot
# records it in the stage file, so a rerun in the same boot knows the reboot
# has not happened yet. ROCM_BOOT_ID_FILE overrides the source for tests.
_rocm_current_boot_id() {
    cat "${ROCM_BOOT_ID_FILE:-/proc/sys/kernel/random/boot_id}" 2>/dev/null || true
}

_rocm_runtime_stage_boot_id() {
    local stage_file
    stage_file="$(_rocm_runtime_stage_file)"
    [[ -f "${stage_file}" ]] || return 0
    (
        # shellcheck disable=SC1090
        source "${stage_file}"
        echo "${ROCM_REBOOT_BOOT_ID:-}"
    )
}


# ════════════════════════════════════════════════════════════════════════════
# FUNCTION 1 — rocm_install_runtime
#
# Purpose: Full ROCm runtime install on a bare-metal Ubuntu 26.04 (resolute)
#          server that has no existing AMD GPU software. After the firmware
#          install, reloads the in-tree amdgpu module (modprobe -r / modprobe)
#          so it loads the new firmware, and verifies every GPU came back.
#          Reboots once only if that reload cannot be done or verified
#          (amdgpu_reload_instead_of_reboot in amdgpu_reload.sh;
#          ROCM_RELOAD_INSTEAD_OF_REBOOT=0 always reboots). Step 02 uses
#          apt-get upgrade, which keeps back new kernels, so the running kernel
#          is the one the reload uses.
#
#          Ubuntu 26.04's kernel is too new for amdgpu-dkms to build cleanly
#          (GCC15 / kernel-API mismatches against the out-of-tree DKMS module —
#          confirmed via ROCm/ROCm#6193 and ROCm/amdgpu#220). This function
#          therefore relies on the IN-TREE amdgpu.ko driver Ubuntu 26.04 already
#          ships, installing only the firmware blobs (amdgpu-dkms-firmware)
#          rather than the DKMS kernel module package.
#
# WARNING: If the reload fails, this function calls "sudo reboot" once. The
#          caller must handle reconnection (e.g., systemd auto-resume in
#          setup.sh) and must exit while the stage file remains. Progress is
#          persisted to a stage file (see _rocm_runtime_stage_*) so the
#          function resumes after that single reboot. When the reload
#          succeeds, the function returns with the stage file cleared.
#
# Deferred reboot: with ROCM_DEFER_REBOOT=1 (set by setup.sh) a failed reload
#          does not reboot here. Stage3 stays saved, ROCM_REBOOT_PENDING=1 is
#          set, and the function returns 0. The caller installs everything
#          else, then reboots once; after that reboot this function logs the
#          reboot step and clears the stage, as for an immediate reboot.
#
# When to call: setup.sh, when benchmark_specification.json
#   Execution Domain is "GPU Compute / ROCm" AND the machine has no ROCm
#   installation (check: [ ! -d /opt/rocm ]).
# ════════════════════════════════════════════════════════════════════════════

# ROCm 10.1.0 / amdgpu 31.60 repository helpers. Both Ubuntu libraries call these.
_rocm_ensure_keyring() {
    local dest_path="$1"
    local key_url="$2"
    local tmp_key
    if run_noninteractive_root test -s "${dest_path}"; then
        _rocm_log "Keyring already present: ${dest_path}"
        return 0
    fi
    run_noninteractive_root mkdir -p /etc/apt/keyrings
    tmp_key="$(mktemp)"
    wget -O "${tmp_key}" "${key_url}" || _rocm_die "Failed to download ${key_url}"
    if [[ ! -s "${tmp_key}" ]]; then
        rm -f "${tmp_key}"
        _rocm_warn "Signing key download was empty (${key_url}); continuing without rewriting ${dest_path}."
        return 0
    fi
    gpg --dearmor < "${tmp_key}" | run_noninteractive_root tee "${dest_path}" >/dev/null \
        || { rm -f "${tmp_key}"; _rocm_die "Failed to install keyring ${dest_path}"; }
    rm -f "${tmp_key}"
    run_noninteractive_root chmod 644 "${dest_path}"
}

_rocm_register_amdgpu_repository() {
    _rocm_ensure_keyring /etc/apt/keyrings/rocm.gpg https://repo.radeon.com/rocm/rocm.gpg.key
    run_noninteractive_root tee /etc/apt/sources.list.d/amdgpu.list >/dev/null <<EOF
deb [arch=amd64 signed-by=/etc/apt/keyrings/rocm.gpg] https://repo.radeon.com/amdgpu/${AMDGPU_DRIVER_VERSION}/ubuntu ${UBUNTU_CODENAME} main
EOF
    run_noninteractive_root apt-get update -y
}

_rocm_register_rocm_repository() {
    _rocm_ensure_keyring /etc/apt/keyrings/amdrocm.gpg https://stable.repo.amd.com/rocm/gpg/packages.gpg
    run_noninteractive_root tee /etc/apt/sources.list.d/amdrocm-stable.sources >/dev/null <<EOF
X-Repo-Id: amdrocm-stable
Types: deb
URIs: https://stable.repo.amd.com/rocm/core/packages/${ROCM_APT_DISTRO}/
Suites: stable
Components: main
Architectures: amd64
Signed-By: /etc/apt/keyrings/amdrocm.gpg
Enabled: yes
EOF
    run_noninteractive_root apt-get update -y
}

_rocm_register_rvs_repository() {
    _rocm_ensure_keyring /etc/apt/keyrings/amdrocm.gpg https://stable.repo.amd.com/rocm/gpg/packages.gpg
    run_noninteractive_root tee /etc/apt/sources.list.d/amdrocm-rvs.sources >/dev/null <<EOF
X-Repo-Id: amdrocm-rvs
Types: deb
URIs: https://stable.repo.amd.com/rocm/extras/rvs/packages/${ROCM_APT_DISTRO}/
Suites: stable
Components: main
Architectures: amd64
Signed-By: /etc/apt/keyrings/amdrocm.gpg
Enabled: yes
EOF
    run_noninteractive_root apt-get update -y
}

_rocm_publish_prefix() {
    local root="" candidate name
    for candidate in /opt/rocm/core-10.1 /opt/rocm-10.1.0 /opt/rocm; do
        if [[ -x "${candidate}/bin/hipcc" || -x "${candidate}/bin/rocm-smi" || -d "${candidate}/bin" ]]; then
            root="${candidate}"
            break
        fi
    done
    if [[ -z "${root}" ]]; then
        _rocm_warn "ROCm prefix not found yet under /opt/rocm."
        return 0
    fi
    if [[ "${root}" != "/opt/rocm" ]]; then
        run_noninteractive_root mkdir -p /opt/rocm
        for name in bin lib lib64 include share; do
            if [[ -e "${root}/${name}" && ! -e "/opt/rocm/${name}" ]]; then
                run_noninteractive_root ln -sfn "${root}/${name}" "/opt/rocm/${name}"
            fi
        done
    fi
    export PATH="/opt/rocm/bin:${PATH}"
    export LD_LIBRARY_PATH="/opt/rocm/lib:/opt/rocm/lib64:${LD_LIBRARY_PATH:-}"
    _rocm_append_bashrc_once 'export PATH=/opt/rocm/bin:${PATH}'
    _rocm_append_bashrc_once 'export LD_LIBRARY_PATH=/opt/rocm/lib:/opt/rocm/lib64:${LD_LIBRARY_PATH}'
}

_rocm_assert_dkms_for_running_kernel() {
    if ! command -v dkms >/dev/null 2>&1; then
        return 0
    fi
    if ! dpkg-query -W amdgpu-dkms >/dev/null 2>&1; then
        return 0
    fi
    if dkms status 2>/dev/null | grep -F "amdgpu" | grep -F "$(uname -r)" | grep -q "installed"; then
        return 0
    fi
    _rocm_die "amdgpu-dkms ${AMDGPU_DRIVER_VERSION} did not build for kernel $(uname -r). $(dkms status 2>/dev/null || true)"
}

_rocm_checkout_rocblas_tag() {
    local tag
    for tag in "rocm-${ROCM_VERSION}" "rocblas-5.7.0"; do
        if git rev-parse --verify --quiet "refs/tags/${tag}" >/dev/null 2>&1 \
            || git ls-remote --exit-code --tags origin "refs/tags/${tag}" >/dev/null 2>&1; then
            _rocm_log "Check out rocBLAS tag ${tag} (rocBLAS 5.7.0 ships with ROCm ${ROCM_VERSION})."
            git checkout "${tag}"
            return 0
        fi
    done
    _rocm_log "No rocm-${ROCM_VERSION} or rocblas-5.7.0 tag in this clone; building the default branch against installed ROCm ${ROCM_VERSION}."
}

rocm_install_runtime() {
    _rocm_log "=== rocm_install_runtime: ROCm ${ROCM_VERSION} on ${UBUNTU_CODENAME} (amdgpu ${AMDGPU_DRIVER_VERSION}) ==="
    local stage
    # Read by setup.sh after this function returns.
    # shellcheck disable=SC2034
    ROCM_REBOOT_PENDING=0
    stage="$(_rocm_runtime_stage_get)"
    _rocm_log "Runtime install stage: ${stage}"

    if [[ "${stage}" == "stage1" ]]; then
        _rocm_status_phase "Phase 1:  ## Install ROCm Runtime Tools (On Bare Metal Ubuntu Server - NOT ROCm server) - 26.04"
        if declare -f keep_running_kernel >/dev/null 2>&1; then
            keep_running_kernel
        fi
        # Step 01 — Advanced Package Tool updates the local list of available packages and versions from all configured repositories.
        _rocm_log "Advanced Package Tool updates the local list of available packages and versions from all configured repositories."
        run_noninteractive_root DEBIAN_FRONTEND=noninteractive apt update  # Update the list of available packages (does not install pkgs)
        _rocm_status_step 1 "sudo apt update  # Update the list of available packages (does not install pkgs)"

        # Step 02 — Upgrades installed packages to their latest versions without prompting for confirmation.
        # apt-get upgrade (not apt upgrade) never installs NEW packages, so a new Linux
        # kernel (a new linux-image-<version> package) is kept back. The running kernel
        # then stays the kernel in use, which lets the amdgpu driver be reloaded at the
        # end of this function instead of rebooting. Install kernel updates on purpose,
        # separately, when you want them.
        _rocm_log "Upgrades installed packages (apt-get upgrade keeps back new kernels so the driver can be reloaded without a reboot)."
        run_noninteractive_root DEBIAN_FRONTEND=noninteractive apt-get upgrade -y  # Upgrades installed packages; new kernels are kept back
        _rocm_status_step 2 "sudo apt-get upgrade -y  # Upgrades installed packages; new kernels are kept back"

        # Step 03 — Pre-driver reboot removed. One reboot after firmware install
        # loads both a staged kernel (if apt upgrade installed one) and amdgpu.
        _rocm_log "Skipping pre-driver reboot; continuing install in this invocation."
        _rocm_status_step 3 "pre-driver reboot skipped; single reboot after amdgpu-dkms-firmware"
        # Fall through to the install steps below (same invocation).
    fi

    if [[ "${stage}" == "stage1" || "${stage}" == "stage2" ]]; then
        _rocm_status_phase "Phase 1:  ## Install ROCm Runtime Tools (On Bare Metal Ubuntu Server - NOT ROCm server) - 26.04"
        _rocm_log "Register amdgpu ${AMDGPU_DRIVER_VERSION} and install amdgpu-dkms."
        _rocm_register_amdgpu_repository
        _rocm_status_step 4 "deb [arch=amd64] https://repo.radeon.com/amdgpu/${AMDGPU_DRIVER_VERSION}/ubuntu ${UBUNTU_CODENAME} main"
        run_noninteractive_root DEBIAN_FRONTEND=noninteractive apt-get install -y amdgpu-dkms
        _rocm_status_step 5 "sudo apt-get install -y amdgpu-dkms"

        _rocm_log "Register ROCm ${ROCM_VERSION} and install ${ROCM_META_PACKAGE} plus ${ROCM_DEV_PACKAGE}."
        _rocm_register_rocm_repository
        run_noninteractive_root DEBIAN_FRONTEND=noninteractive apt-get install -y \
            "${ROCM_META_PACKAGE}" "${ROCM_DEV_PACKAGE}"
        _rocm_status_step 6 "sudo apt-get install -y ${ROCM_META_PACKAGE} ${ROCM_DEV_PACKAGE}"
        _rocm_publish_prefix

        _rocm_log "Install RDMA userspace libraries required by ROCm."
        run_noninteractive_root DEBIAN_FRONTEND=noninteractive apt-get install -y rdma-core ibverbs-providers libibverbs1
        _rocm_status_step 7 "sudo apt-get install -y rdma-core ibverbs-providers libibverbs1"

        if declare -f _rocm_install_linux_modules_extra >/dev/null 2>&1; then
            _rocm_log "Install kernel module extras for the running kernel."
            _rocm_install_linux_modules_extra
            _rocm_status_step 8 "sudo apt-get install -y linux-modules-extra-$(uname -r)"
        else
            _rocm_log "Skipping linux-modules-extra: Ubuntu 26.04 folds it into linux-modules."
        fi

        _rocm_assert_dkms_for_running_kernel
        _rocm_log "Refresh kernel module dependency map."
        run_noninteractive_root depmod -a
        _rocm_status_step 9 "sudo depmod -a"

        # Step 10 — Reload the in-tree amdgpu driver so it loads the new firmware; reboot only if that fails.
        # The stage is saved first: if the reload hangs or the host goes down, setup
        # resumes at stage3 after the reboot, as it always has.
        _rocm_runtime_stage_set "stage3"
        if declare -f amdgpu_reload_instead_of_reboot >/dev/null 2>&1 \
            && amdgpu_reload_instead_of_reboot dkms; then
            _rocm_status_step 10 "sudo modprobe -r amdgpu && sudo modprobe amdgpu  # Reload amdgpu to load the new firmware (verified; no reboot)"
            _rocm_runtime_stage_clear
            _rocm_log "Runtime installation stage is complete; amdgpu reloaded without a reboot."
            return 0
        fi
        if [[ "${ROCM_DEFER_REBOOT:-0}" == 1 ]]; then
            # setup.sh installs everything else first and reboots once at the end.
            # shellcheck disable=SC2034
            ROCM_REBOOT_PENDING=1
            echo "ROCM_REBOOT_BOOT_ID=$(_rocm_current_boot_id)" >> "$(_rocm_runtime_stage_file)"
            _rocm_log "Driver reload not possible or not verified; reboot to load amdgpu firmware postponed until the rest of setup is installed (ROCM_DEFER_REBOOT=1)."
            return 0
        fi
        _rocm_log "Reboot once to load amdgpu firmware (driver reload not possible or not verified)."
        run_noninteractive_root reboot  # Single reboot after firmware install (fallback)
        # ── execution stops here; caller must reconnect ──
    fi

    if [[ "${stage}" == "stage3" ]]; then
        local pending_boot
        pending_boot="$(_rocm_runtime_stage_boot_id)"
        if [[ -n "${pending_boot}" && "${pending_boot}" == "$(_rocm_current_boot_id)" ]]; then
            # The reboot was postponed and has not happened yet (setup stopped
            # before its end and was run again in the same boot).
            if [[ "${ROCM_DEFER_REBOOT:-0}" == 1 ]]; then
                # shellcheck disable=SC2034
                ROCM_REBOOT_PENDING=1
                _rocm_log "Postponed amdgpu reboot has not happened yet; it stays postponed until the rest of setup is installed."
                return 0
            fi
            _rocm_log "Postponed amdgpu reboot has not happened yet; rebooting now."
            run_noninteractive_root reboot  # Single reboot after driver install (postponed earlier)
            return 0
        fi
        _rocm_status_phase "Phase 1:  ## Install ROCm Runtime Tools (On Bare Metal Ubuntu Server - NOT ROCm server) - 26.04"
        _rocm_status_step 10 "sudo reboot  # Reboot to load the newly installed amdgpu kernel driver"
        _rocm_runtime_stage_clear
        _rocm_log "Runtime installation stage is complete after post-driver reboot."
    fi
}


# ════════════════════════════════════════════════════════════════════════════
# FUNCTION 2 — rocm_add_repository
#
# Purpose: Add the current user to render/video and install amdrocm10.1 userspace
#          (amd-smi and hipcc) from stable.repo.amd.com when hipcc is missing.
#          Idempotent: skips packages that are already installed.
#
# When to call: setup.sh, after rocm_install_runtime has completed.
# ════════════════════════════════════════════════════════════════════════════
rocm_add_repository() {
    _rocm_log "=== rocm_add_repository: ROCm ${ROCM_VERSION} on ${UBUNTU_CODENAME} ==="
    _rocm_status_phase "Phase 2:  ## Add ROCm 10.1.0 repository"
    _rocm_log "Add current user to render and video groups for GPU access."
    local target_user="${LOGNAME:-${SUDO_USER:-${USER:-$(id -un)}}}"
    if [[ -n "${target_user}" ]]; then
        run_noninteractive_root usermod -a -G render,video "${target_user}"
        _rocm_status_step 11 "sudo usermod -a -G render,video ${target_user}"
    else
        _rocm_warn "Could not resolve target user for render/video group assignment; skipping usermod."
    fi
    _rocm_register_amdgpu_repository
    _rocm_register_rocm_repository
    _rocm_status_step 13 "sudo apt-get update"
    if [[ ! -x /opt/rocm/bin/hipcc && ! -x /opt/rocm/core-10.1/bin/hipcc ]]; then
        run_noninteractive_root DEBIAN_FRONTEND=noninteractive apt-get install -y \
            "${ROCM_META_PACKAGE}" "${ROCM_DEV_PACKAGE}"
    fi
    _rocm_status_step 14 "sudo apt-get install -y ${ROCM_META_PACKAGE} ${ROCM_DEV_PACKAGE}"
    _rocm_publish_prefix
    _rocm_log "ROCm ${ROCM_VERSION} repository confirmed and base packages installed."
}


rocm_install_rvs() {
    _rocm_log "=== rocm_install_rvs: ${RVS_PACKAGE} ${RVS_PACKAGE_VERSION} (ROCm ${ROCM_VERSION}) ==="
    _rocm_status_phase "Phase 3:  ## Install ROCm Validation Suite from the ROCm extras repository"
    local installed candidate
    if command -v rvs >/dev/null 2>&1 || [[ -x /opt/rocm/bin/rvs ]] || [[ -x /usr/bin/rvs ]]; then
        _rocm_log "RVS already installed. Skipping package install."
        return 0
    fi
    _rocm_register_rvs_repository
    _rocm_status_step 15 "deb https://stable.repo.amd.com/rocm/extras/rvs/packages/${ROCM_APT_DISTRO}/ stable main"
    if ! run_noninteractive_root DEBIAN_FRONTEND=noninteractive apt-get install -y "${RVS_PACKAGE}=${RVS_PACKAGE_VERSION}"; then
        _rocm_warn "Pinned ${RVS_PACKAGE}=${RVS_PACKAGE_VERSION} was not available; installing ${RVS_PACKAGE}."
        run_noninteractive_root DEBIAN_FRONTEND=noninteractive apt-get install -y "${RVS_PACKAGE}" \
            || _rocm_die "Failed to install ${RVS_PACKAGE}."
    fi
    installed="$(dpkg-query -W -f='${Version}' "${RVS_PACKAGE}" 2>/dev/null || true)"
    case "${installed}" in
        *"${RVS_PACKAGE_VERSION}"*) ;;
        *) _rocm_die "Installed ${RVS_PACKAGE} version '${installed}', expected ${RVS_PACKAGE_VERSION}." ;;
    esac
    if ! command -v rvs >/dev/null 2>&1; then
        for candidate in /opt/rocm/extras-10/bin/rvs /opt/rocm/bin/rvs /usr/bin/rvs; do
            if [[ -x "${candidate}" ]]; then
                run_noninteractive_root ln -sfn "${candidate}" /usr/local/bin/rvs
                break
            fi
        done
    fi
    command -v rvs >/dev/null 2>&1 || _rocm_die "${RVS_PACKAGE} installed but rvs is not on PATH."
    _rocm_status_step 16 "sudo apt-get install -y ${RVS_PACKAGE}=${RVS_PACKAGE_VERSION}"
    _rocm_log "RVS ${installed} is installed."
}


rocm_compile_rocblas_bench() {
    _rocm_log "=== rocm_compile_rocblas_bench: rocBLAS (default branch) / ROCm ${ROCM_VERSION} / ${GFX_TARGET} ==="

    local staging_dir="${ROCBLAS_SOURCE_DIR}/build/release/clients/staging"
    local bench_bin="${staging_dir}/rocblas-bench"

    if [[ -x "${bench_bin}" ]]; then
        _rocm_log "rocblas-bench already built at ${bench_bin}. Skipping build."
        export PATH="${staging_dir}:${PATH}"
        export LD_LIBRARY_PATH="/opt/rocm/lib:${LD_LIBRARY_PATH}"
        return 0
    fi

    # Step 27 — APT updates the local list of available packages and versions from all configured repositories.
    _rocm_log "APT updates the local list of available packages and versions from all configured repositories."
    run_noninteractive_root apt update  # Update the list of available packages (does not install pkgs)

    # Step 28 — Install Fortran BLAS/LAPACK symbols used by test and benchmark executables.
    _rocm_log "Install Fortran BLAS/LAPACK symbols used by test and benchmark executables."
    run_noninteractive_root apt install -y gfortran  # Install Fortran BLAS/LAPACK symbols used by executables

    # Step 29 — Install Google Test (GTest) unit testing framework used by test and benchmark executables.
    _rocm_log "Install Google Test (GTest) unit testing framework used by test and benchmark executables."
    run_noninteractive_root apt install -y libgtest-dev  # Install Google Test (GTest) unit testing framework

    # (Omitted for Ubuntu 26.04): cmake removal + Kitware repo workaround.
    # Stock cmake on resolute (4.x) already exceeds rocBLAS's >=3.25 requirement,
    # unlike 24.04's stock cmake 3.22 — no replacement repo needed here.
    _rocm_log "Skipping cmake removal / Kitware repo: stock resolute cmake already satisfies rocBLAS's >=3.25 requirement."

    # Step 30 — Install Python 3 header files and development libraries for compiling C/C++ code.
    _rocm_log "Install Python 3 header files and development libraries for compiling C/C++ code."
    run_noninteractive_root apt install -y git python3-dev  # Install Python 3 header files and development libraries for compiling C/C++ code.

    # Step 31/32 — Clone into a repository-local third_party/ directory (see note near
    # ROCBLAS_SOURCE_DIR at the top of this file for why this differs from the tested
    # "cd ~" log).
    _rocm_log "Clone the official rocBLAS source code repository from GitHub to the local machine."
    if [[ ! -d "${ROCBLAS_SOURCE_DIR}/.git" ]]; then
        mkdir -p "$(dirname "${ROCBLAS_SOURCE_DIR}")"
        git clone https://github.com/ROCm/rocBLAS.git "${ROCBLAS_SOURCE_DIR}"  # Clone inside the workload repository.
    fi

    # Step 33 — Change the current working directory to the newly created rocBLAS project folder.
    _rocm_log "Change the current working directory to the newly created rocBLAS project folder."
    cd "${ROCBLAS_SOURCE_DIR}"  # Change to the repository-local rocBLAS project folder.

    _rocm_log "Select the rocBLAS tag that matches ROCm ${ROCM_VERSION} (rocBLAS 5.7.0)."
    _rocm_checkout_rocblas_tag

    # Step 34 — Fixes rocBLAS client build: rocm_smi/kfd_ioctl.h needs libdrm/drm.h.
    # NEW dependency not present in the 24.04 recipe — without it the build fails at
    # ~62% with: fatal error: 'libdrm/drm.h' file not found.
    _rocm_log "Install libdrm-dev (required by rocm_smi/kfd_ioctl.h during the client build)."
    run_noninteractive_root apt install -y libdrm-dev  # Fixes rocBLAS client build: rocm_smi/kfd_ioctl.h needs libdrm/drm.h

    # Step 35 — Build rocBLAS benchmark and test clients targeting MI300X gfx942.
    _rocm_log "Build rocBLAS benchmark and test clients targeting ${GFX_TARGET}."
    ./install.sh --clients-only -a "${GFX_TARGET}"  # (takes five minutes) Build rocBLAS benchmark and test clients targeting MI300X gfx942.

    if [[ ! -x "${bench_bin}" ]]; then
        cd - >/dev/null 2>&1 || true
        _rocm_die "rocblas-bench was not produced at ${bench_bin} — check the build log for the real error (e.g. grep -iE 'error:|fatal error' on the install.sh output)."
    fi

    # Step 36 — Add staging to PATH for the current session.
    _rocm_log "Add staging to PATH."
    export PATH="${staging_dir}:${PATH}"  # Add staging to PATH

    # Step 37 — Persist staging PATH in .bashrc so it survives reboots/new shells.
    _rocm_log "Persist rocBLAS clients staging PATH in .bashrc."
    _rocm_append_bashrc_once "export PATH=${staging_dir}:\$PATH"  # Update PATH in .bashrc

    # Step 38 — Add libraries to LD_LIBRARY_PATH. --clients-only builds with
    # SKIP_LIBRARY=ON, so the clients link against the already-installed
    # /opt/rocm/lib librocblas.so rather than a local build — confirmed this session
    # that ${ROCBLAS_SOURCE_DIR}/build/release/rocblas/library never gets created,
    # so (unlike the 24.04 recipe) it is deliberately not added here.
    _rocm_log "Add libraries to LD_LIBRARY_PATH."
    export LD_LIBRARY_PATH="/opt/rocm/lib:${LD_LIBRARY_PATH}"  # --clients-only builds link against the installed librocblas.so, not a local build (SKIP_LIBRARY=ON — build/release/rocblas/library never gets created)

    # Step 39 — Persist LD_LIBRARY_PATH in .bashrc so it survives reboots/new shells.
    _rocm_log "Persist LD_LIBRARY_PATH in .bashrc."
    _rocm_append_bashrc_once 'export LD_LIBRARY_PATH="/opt/rocm/lib:$LD_LIBRARY_PATH"'  # Update LD_LIBRARY_PATH in .bashrc

    # Step 40 — Create a results folder.
    _rocm_log "Create a results folder."
    mkdir -p ~/rocblas_tests  # Create a results folder

    # Return to original working directory if available.
    cd - >/dev/null 2>&1 || true

    _rocm_log "rocblas-bench built successfully at ${bench_bin}"
    _rocm_log "Verify with: rocblas-bench -f gemm -r f32_r -m 4096 -n 4096 -k 4096"
}