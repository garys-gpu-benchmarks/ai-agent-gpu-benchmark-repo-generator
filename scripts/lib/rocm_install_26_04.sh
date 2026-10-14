#!/usr/bin/env bash
# File:         scripts/lib/rocm_install_26_04.sh
# Version:      1.0.0
# Maintainer: AI Agent GPU Benchmark Repo Generator
# Date:         2026-08-25
# Description:  Authoritative, idempotent ROCm installation functions for gpu-bench-* /
#               sys-bench-* benchmark repositories, targeting Ubuntu 26.04 (resolute) /
#               ROCm 7.14 (TheRock packaging). These functions must be sourced and
#               called verbatim — do not regenerate or modify them. AI agents working in
#               this repository must not rewrite this library. Aligned to the
#               40-step ROCm install process from the Ubuntu 26.04 column of
#               Tmp_SideBySide_Install_2404_vs_2604_20260825.xlsx, including persisted
#               shell-profile updates for PATH / LD_LIBRARY_PATH. Function names and
#               signatures are intentionally identical to scripts/lib/rocm_install_24_04.sh
#               so callers can source whichever file matches the detected Ubuntu release
#               without branching on OS elsewhere in the generator.
# Execution:    source scripts/lib/rocm_install_26_04.sh  (not executed directly)
# Options:      Environment variables below may override the pinned defaults.
# Requirements: Ubuntu 26.04 (resolute); sudo access; internet.
# Environment:  Bare metal or ROCm-capable VM; not required inside a ROCm Docker image.
# Dependencies: curl, wget, apt; sourced after scripts/lib/common.sh for log helpers.
# Variables:
#   ROCM_VERSION             ROCm version string, e.g. 7.14          (default: 7.14)
#   AMDGPU_INSTALLER_VERSION amdgpu-install TOOL version              (default: 31.40.1)
#   AMDGPU_INSTALLER_BUILD   amdgpu-install .deb build suffix         (default: 314001-1)
#   GFX_TARGET                GPU architecture token, e.g. gfx942     (default: gfx942)
#   UBUNTU_CODENAME           Ubuntu release codename                 (default: resolute)
#
#   IMPORTANT: unlike the 24.04/7.2.1-era packaging, the amdgpu-install TOOL version and
#   the ROCm VERSION it installs are no longer the same number. AMDGPU_INSTALLER_VERSION
#   (31.40.1) selects the installer tool's own .deb; ROCM_VERSION (7.14) is the ROCm line
#   that tool then installs via --usecase=. Do not assume these are coupled as they were
#   for noble/jammy — confirmed this session against the real repo.radeon.com layout.
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
ROCM_VERSION="${ROCM_VERSION:-7.14}"
UBUNTU_CODENAME="${UBUNTU_CODENAME:-resolute}"
GFX_TARGET="${GFX_TARGET:-gfx942}"
AMDGPU_INSTALLER_VERSION="${AMDGPU_INSTALLER_VERSION:-31.40.1}"
AMDGPU_INSTALLER_BUILD="${AMDGPU_INSTALLER_BUILD:-314001-1}"

# Installer URL pinned to the confirmed-working resolute layout:
#   https://repo.radeon.com/amdgpu-install/31.40.1/ubuntu/resolute/amdgpu-install_31.40.1.314001-1_all.deb
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
rocm_install_runtime() {
    _rocm_log "=== rocm_install_runtime: ROCm ${ROCM_VERSION} on ${UBUNTU_CODENAME} (amdgpu-install ${AMDGPU_INSTALLER_VERSION}) ==="
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
        # Step 04 — Downloads the AMD GPU installer .deb package from the Radeon (AMD ROCm) repository.
        # NOTE: amdgpu-install tool version ${AMDGPU_INSTALLER_VERSION}, ROCm is ${ROCM_VERSION} —
        # these are independent numbers on resolute, unlike the noble/jammy 7.2.x line.
        _rocm_log "Download AMD GPU installer .deb package (resolute=Ubuntu26/noble=Ubuntu24/jammy=Ubuntu22)."
        _rocm_download_installer
        _rocm_status_step 4 "wget -O ${_AMDGPU_DEB_FILE} ${AMDGPU_INSTALLER}  # Download AMD GPU installer package"

        # Step 05 — Installs the downloaded AMD GPU installer .deb package used to install the full ROCm software stack.
        _rocm_log "Install the downloaded AMD GPU installer package."
        _rocm_apt_install_local_deb_noninteractive "./${_AMDGPU_DEB_FILE}"  # Install downloaded AMD GPU installer .deb
        _rocm_status_step 5 "sudo apt install -y ./${_AMDGPU_DEB_FILE}  # Install AMD GPU Installer"

        # Step 06 — Install ROCm Runtime, HIP Runtime + Compiler (hipcc), rocBLAS, rocBLASLt, rocFFT, rocRAND, rocSOLVER, rocSPARSE, RCCL, MIOpen, rocWMMA, rocPRIM, rocThrust, hipBLASLt, hipBLAS, hipFFT, hipRAND, hipSPARSE, hipSOLVER, hipTensor, OpenCL runtime and graphics stack.
        _rocm_log "Install ROCm usecase stack and userspace components."
        set +e
        run_noninteractive_root amdgpu-install -y \
            --usecase=rocm,rocmdev,hiplibsdk,mlsdk,opencl,graphics \
            --no-dkms  # Install ROCm userspace stack without dkms — in-tree amdgpu.ko is used instead (see Step 07)
        local rc_usecase=$?
        set -e
        if [[ "${rc_usecase}" -ne 0 ]]; then
            _rocm_warn "Retrying with compute-focused usecase (dropping opencl,graphics)."
            run_noninteractive_root amdgpu-install -y \
                --usecase=rocm,rocmdev,hiplibsdk,mlsdk \
                --no-dkms \
                || _rocm_die "amdgpu-install failed for both primary and fallback usecases."
        fi
        _rocm_status_step 6 "sudo amdgpu-install -y --usecase=rocm,rocmdev,hiplibsdk,mlsdk,opencl,graphics --no-dkms  # Install ROCm userspace stack"

        # Step 07 — Install AMD GPU firmware blobs for the in-tree amdgpu driver.
        # DELIBERATELY NOT amdgpu-dkms: that package tries to compile the out-of-tree
        # kernel module against Ubuntu 26.04's kernel and fails (GCC15/kernel-API
        # mismatch). amdgpu-dkms-firmware is data-only (no compilation) and is what
        # the in-tree amdgpu.ko driver needs to actually initialize the GPU/KFD.
        _rocm_log "Install AMD GPU firmware blobs for in-tree amdgpu driver."
        run_noninteractive_root DEBIAN_FRONTEND=noninteractive apt-get install -y amdgpu-dkms-firmware  # Install AMD GPU firmware blobs for in-tree amdgpu driver
        _rocm_status_step 7 "sudo apt install -y amdgpu-dkms-firmware  # Install AMD GPU firmware blobs for in-tree amdgpu driver"

        # Step 08 — Install InfiniBand and RDMA userspace libraries required by the amdgpu kernel module.
        _rocm_log "Install RDMA userspace libraries required by ROCm."
        run_noninteractive_root DEBIAN_FRONTEND=noninteractive apt-get install -y rdma-core ibverbs-providers libibverbs1  # Install RDMA/InfiniBand userspace libraries
        _rocm_status_step 8 "sudo apt install -y rdma-core ibverbs-providers libibverbs1  # Install RDMA/InfiniBand userspace libraries"

        # (Omitted for Ubuntu 26.04): sudo apt install -y linux-modules-extra-$(uname -r)
        # This package was removed/folded into linux-modules starting Ubuntu 25.10+;
        # attempting to install it on resolute fails with "Unable to locate package."
        # There is no newest-/lib/modules branch. Do not install linux-modules or
        # linux-modules-extra for any kernel other than uname -r.
        _rocm_log "Skipping linux-modules-extra install: deprecated/removed on Ubuntu 25.10+ (resolute), folded into linux-modules by default. Running kernel only; no newest /lib/modules install."

        # Step 09 — Rebuild kernel module dependency map.
        _rocm_log "Refresh kernel module dependency map."
        run_noninteractive_root depmod -a  # Rebuild kernel module dependency map
        _rocm_status_step 9 "sudo depmod -a  # Rebuild kernel module dependency map"

        # (Omitted for Ubuntu 26.04): sudo apt install -y rocm-libs
        # rocm-libs is no longer functional in the ROCm 7.2+ / TheRock packaging line.
        # Its former contents (rocblas, rocfft, rocrand, rocsolver, rocsparse, rccl,
        # hipblas, hipblaslt, hipfft, hiprand, hipsparse, hipsolver, hiptensor) are
        # already installed as amdrocm-*7.14[-gfxNNN] components via the Step 06
        # --usecase= install; confirmed present via dpkg -l this session.
        _rocm_log "Skipping rocm-libs: superseded by amdrocm-*${ROCM_VERSION} components already installed in Step 06."

        # Step 10 — Reload the in-tree amdgpu driver so it loads the new firmware; reboot only if that fails.
        # The stage is saved first: if the reload hangs or the host goes down, setup
        # resumes at stage3 after the reboot, as it always has.
        _rocm_runtime_stage_set "stage3"
        if declare -f amdgpu_reload_instead_of_reboot >/dev/null 2>&1 \
            && amdgpu_reload_instead_of_reboot firmware; then
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
# Purpose: Add current user to render/video groups and install the amdrocm
#          metapackage + rocm-smi. On resolute, amdgpu-install (Function 1,
#          Step 06) already configures a working apt source
#          (repo.radeon.com/rocmradeon + repo.radeon.com/graphics) — confirmed
#          this session that amdrocm7.14/rocm-smi install successfully from
#          that alone, with no separate repo file required. This function still
#          downloads the ROCm GPG key for parity with the tested command log;
#          it does NOT write an additional sources.list.d entry, since doing so
#          was confirmed unnecessary and the tested recipe omits it.
#          Idempotent: skips steps that are already complete.
#
# When to call: setup.sh, after rocm_install_runtime has completed (stage
#   cleared) and /etc/apt/sources.list.d/rocm.list already exists from
#   amdgpu-install.
# ════════════════════════════════════════════════════════════════════════════
rocm_add_repository() {
    _rocm_log "=== rocm_add_repository: ROCm ${ROCM_VERSION} on ${UBUNTU_CODENAME} ==="
    _rocm_status_phase "Phase 2:  ## Add ROCm Repository  (On Bare Metal Ubuntu Server, ROCm server)"

    # Step 11 — For users not root, adds the current user to the render and video groups for GPU access permissions.
    _rocm_log "Add current user to render and video groups for GPU access."
    local target_user="${LOGNAME:-${SUDO_USER:-${USER:-$(id -un)}}}"
    if [[ -n "${target_user}" ]]; then
        run_noninteractive_root usermod -a -G render,video "${target_user}"  # Adds current user to groups of render, video
        _rocm_status_step 11 "sudo usermod -a -G render,video ${target_user}  # Adds current user to groups of render, video"
    else
        _rocm_warn "Could not resolve target user for render/video group assignment; skipping usermod."
    fi

    # Step 12 — Downloads the ROCm GPG signing key, enabling trusted downloads.
    _rocm_log "Download ROCm GPG signing key into keyring."
    run_noninteractive_root mkdir -p /etc/apt/keyrings
    wget https://repo.amd.com/rocm/packages-multi-arch/gpg/rocm.gpg -O - \
        | gpg --dearmor \
        | run_noninteractive_root tee /etc/apt/keyrings/amdrocm.gpg > /dev/null  # Download ROCm GPG signing key, enabling trusted downloads
    _rocm_status_step 12 "wget https://repo.amd.com/rocm/packages-multi-arch/gpg/rocm.gpg -O - | gpg --dearmor | sudo tee /etc/apt/keyrings/amdrocm.gpg > /dev/null"

    # NOTE: unlike the 24.04/noble recipe, there is deliberately no
    # "echo 'deb ...' | sudo tee /etc/apt/sources.list.d/rocm.list" step here.
    # amdgpu-install already wrote a working rocm.list (repo.radeon.com/rocmradeon +
    # repo.radeon.com/graphics, resolute main) during Function 1 — confirmed this
    # session that Step 14 below installs successfully without any additional repo
    # file, so adding one is unnecessary on this OS/ROCm line.

    # Step 13 — Updates the APT package index, downloading package lists from the ROCm repository already configured by amdgpu-install.
    _rocm_log "Update apt package index."
    run_noninteractive_root apt update  # Update APT package index and download package LISTS from ROCm repository
    _rocm_status_step 13 "sudo apt update  # Update APT package index and download package LISTS from ROCm repository"

    # Step 14 — Install amdrocm metapackage (rocm-dev-equivalent under TheRock naming) and rocm-smi.
    _rocm_log "Install ROCm development metapackage and rocm-smi."
    run_noninteractive_root DEBIAN_FRONTEND=noninteractive apt-get install -y \
        "amdrocm${ROCM_VERSION}" rocm-smi  # Install rocm-dev (dev toolchain), rocm-libs
    _rocm_status_step 14 "sudo apt install -y amdrocm${ROCM_VERSION} rocm-smi  # Install rocm-dev (dev toolchain), rocm-libs"

    _rocm_log "ROCm repository confirmed and base packages installed."
}


# ════════════════════════════════════════════════════════════════════════════
# FUNCTION 3 — rocm_install_rvs
#
# Purpose: Build and install the ROCm Validation Suite (RVS) from source into
#          a repository-local third_party/ directory. Unlike the 24.04/7.2.x
#          line, there is no rocm-validation-suite apt package published for
#          resolute/ROCm 7.14 (confirmed this session against both the apt
#          repo and upstream GitHub releases, which stop at tag rocm-7.2.4),
#          so RVS must be compiled from the default branch against the
#          installed ROCm 7.14 stack.
#          Idempotent: skips the clone+build+install if rvs already resolves.
#
# When to call: setup.sh, when benchmark_specification.json
#   Workload Name contains "ROCm Validation" or "RVS", or when the Workload
#   Command Line Executable is "rvs".
# ════════════════════════════════════════════════════════════════════════════
rocm_install_rvs() {
    _rocm_log "=== rocm_install_rvs: ROCm Validation Suite (built from source) against ROCm ${ROCM_VERSION} ==="
    _rocm_status_phase "Phase 3:  ## Install  ROCm Validation Suite (On Bare Metal Ubuntu Server, ROCm server)"

    local rocm_bin
    rocm_bin="$(_rocm_resolve_rocm_bin || echo /opt/rocm/bin)"

    if command -v rvs >/dev/null 2>&1 || [[ -x "${rocm_bin}/rvs" ]]; then
        _rocm_log "RVS already installed. Skipping clone/build. Verify with: rvs --help"
        return 0
    fi

    # Step 15 — Download the AMD GPU driver installer package (re-confirms amdgpu-install tool is present).
    _rocm_log "Download the AMD GPU driver installer package."
    _rocm_download_installer
    _rocm_status_step 15 "wget -O ${_AMDGPU_DEB_FILE} ${AMDGPU_INSTALLER}  # Download AMD GPU installer package"

    # Step 16 — Install amdgpu-install tool.
    _rocm_log "Install amdgpu-install tool."
    _rocm_apt_install_local_deb_noninteractive "./${_AMDGPU_DEB_FILE}" \
        || { _rocm_warn "Failed to install amdgpu-install tool."; return 1; }
    _rocm_status_step 16 "sudo apt install -y ./${_AMDGPU_DEB_FILE}  # Install AMD GPU Installer"

    # Step 17 — Install RVS build + runtime dependencies. amd-smi-lib and rocblas are
    # already installed as amdrocm-*7.14 components — only the generic build tools and
    # RVS-specific libs need adding. Stock cmake on resolute (>=4.x) already satisfies
    # RVS's cmake >=3.25 requirement; no Kitware repo workaround needed here.
    _rocm_log "Install RVS runtime dependencies."
    run_noninteractive_root DEBIAN_FRONTEND=noninteractive apt-get install -y \
        libpci3 libpci-dev doxygen unzip cmake git libyaml-cpp-dev libnuma-dev \
        || { _rocm_warn "Failed to install one or more RVS build dependency packages."; return 1; }
    _rocm_status_step 17 "sudo apt install -y libpci3 libpci-dev doxygen unzip cmake git libyaml-cpp-dev libnuma-dev  # Install RVS runtime dependencies (amd-smi-lib, rocblas already installed)"

    # Step 18 — Clone into a repository-local third_party/ directory (see RVS_SOURCE_DIR
    # note near the top of this file for why this differs from the tested "cd ~" log).
    _rocm_log "Clone ROCmValidationSuite (no rocm-${ROCM_VERSION} tag exists yet — build from default branch)."
    if [[ ! -d "${RVS_SOURCE_DIR}/.git" ]]; then
        mkdir -p "$(dirname "${RVS_SOURCE_DIR}")"
        git clone https://github.com/ROCm/ROCmValidationSuite.git "${RVS_SOURCE_DIR}"  # Step 19 (clone)
    fi
    _rocm_status_step 18 "cd ~  # Change directory to home directory."
    _rocm_status_step 19 "git clone https://github.com/ROCm/ROCmValidationSuite.git"

    # Step 20 — Change into the RVS source directory.
    cd "${RVS_SOURCE_DIR}"  # no rocm-7.14 tag exists yet — build from master/develop against your installed 7.14 stack
    _rocm_status_step 20 "cd ROCmValidationSuite  # no rocm-${ROCM_VERSION} tag exists yet — build from master/develop against your installed ${ROCM_VERSION} stack"

    # Step 21 — RVS depends on the external/TransferBench submodule.
    _rocm_log "Initialize RVS git submodules (TransferBench)."
    git submodule update --init --recursive
    _rocm_status_step 21 "git submodule update --init --recursive"

    # Step 22 — Configure the build against the installed ROCm 7.14 stack.
    _rocm_log "Configure RVS build."
    cmake -B ./build -DROCM_PATH=/opt/rocm -DCMAKE_INSTALL_PREFIX=/opt/rocm -DCPACK_PACKAGING_INSTALL_PREFIX=/opt/rocm \
        || _rocm_die "RVS cmake configure failed."
    _rocm_status_step 22 "cmake -B ./build -DROCM_PATH=/opt/rocm -DCMAKE_INSTALL_PREFIX=/opt/rocm -DCPACK_PACKAGING_INSTALL_PREFIX=/opt/rocm"

    # Step 23 — Build. Compiles once per target GPU arch (gfx900, gfx906, ..., gfx942, host,
    # etc.) via HIP fat binaries — a long build is expected, not a hang.
    _rocm_log "Build RVS (this compiles for every supported GPU arch; expect a long build)."
    make -C ./build -j "$(nproc)" \
        || _rocm_die "RVS build failed."
    _rocm_status_step 23 "make -C ./build -j \$(nproc)"

    # Step 24 — Install into /opt/rocm.
    _rocm_log "Install RVS into /opt/rocm."
    run_noninteractive_root make -C ./build install \
        || _rocm_die "RVS install failed."
    _rocm_status_step 24 "sudo make -C ./build install"

    cd - >/dev/null 2>&1 || true

    # Step 25 — Add /opt/rocm/bin to PATH for the current session.
    _rocm_log "Add /opt/rocm/bin to PATH in current shell."
    if [[ ":${PATH}:" != *":/opt/rocm/bin:"* ]]; then
        export PATH=/opt/rocm/bin:$PATH  # Add /opt/rocm/bin to PATH
    fi
    _rocm_status_step 25 "export PATH=/opt/rocm/bin:\$PATH  # Add /opt/rocm/bin to PATH"

    # Step 26 — Persist PATH in .bashrc so it survives reboots/new shells.
    _rocm_log "Persist /opt/rocm/bin PATH export in .bashrc."
    _rocm_append_bashrc_once 'export PATH=/opt/rocm/bin:$PATH'
    _rocm_status_step 26 "echo 'export PATH=/opt/rocm/bin:\$PATH' >> ~/.bashrc  # Update PATH in .bashrc"

    if [[ -n "${rocm_bin:-}" && ":${PATH}:" != *":${rocm_bin}:"* ]]; then
        export PATH="${rocm_bin}:${PATH}"
        _rocm_append_bashrc_once "export PATH=${rocm_bin}:\$PATH"
    fi

    if command -v rvs >/dev/null 2>&1; then
        _rocm_log "RVS installed. Verify with: rvs --help"
        return 0
    fi
    if [[ -x "${rocm_bin}/rvs" ]]; then
        _rocm_log "RVS installed at ${rocm_bin}/rvs. Verify with: ${rocm_bin}/rvs --help"
        return 0
    fi
    _rocm_warn "RVS build/install completed but rvs command is still unavailable."
    return 1
}


# ════════════════════════════════════════════════════════════════════════════
# FUNCTION 4 — rocm_compile_rocblas_bench
#
# Purpose: Clone the official ROCm/rocBLAS repository and build the
#          rocblas-bench and rocblas-test clients targeting the configured
#          GFX_TARGET (default: gfx942 / MI300X), into a repository-local
#          third_party/ directory. Unlike the 24.04/7.2.x line, there is no
#          rocm-7.14 git tag yet (confirmed this session — latest tag is
#          rocm-7.2.4), so the build stays on the default branch rather than
#          checking out a version tag. Stock cmake on resolute already
#          satisfies rocBLAS's cmake requirement, so the Kitware-repo
#          workaround from the 24.04 recipe is dropped entirely.
#          Idempotent: skips the build if rocblas-bench already exists at the
#          expected staging path.
#
# Output:  Binary at ${ROCBLAS_SOURCE_DIR}/build/release/clients/staging/rocblas-bench
#          PATH and LD_LIBRARY_PATH are exported for the current session AND
#          persisted to .bashrc so they survive reboots/new shells.
#
# When to call: scripts/build.sh, when a resolved implementation component
#   sets contracts.compile_rocblas_bench.
# ════════════════════════════════════════════════════════════════════════════
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

    # (Omitted for Ubuntu 26.04): git checkout rocm-7.2.1
    # No rocm-${ROCM_VERSION} tag exists upstream yet — stay on the default branch,
    # which builds and links successfully against the installed ${ROCM_VERSION} stack
    # (confirmed by repeated fresh-install runs this session).
    _rocm_log "Staying on default branch: no rocm-${ROCM_VERSION} tag exists upstream yet."

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