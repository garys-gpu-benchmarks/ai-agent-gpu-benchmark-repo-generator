#!/usr/bin/env bash
# File:         scripts/lib/rocm_install_24_04.sh
# Version:      1.3.0
# Maintainer: AI Agent GPU Benchmark Repo Generator
# Date:         2026-07-09
# Description:  Authoritative, idempotent ROCm installation functions for gpu-bench-* /
#               sys-bench-* benchmark repositories. These functions must be sourced and
#               called verbatim — do not regenerate or modify them. AI agents working in
#               this repository must not rewrite this library. Aligned to the
#               41-step ROCm install process from CSV spec, including persisted shell-profile
#               updates for PATH / LD_LIBRARY_PATH.
# Execution:    sourced by scripts/lib/rocm_install.sh on Ubuntu 24.04 (not executed directly)
# Options:      Environment variables below may override the pinned defaults.
# Requirements: Ubuntu 24.04 (noble) or Ubuntu 22.04 (jammy); sudo access; internet.
# Environment:  Bare metal or ROCm-capable VM; not required inside a ROCm Docker image.
# Dependencies: curl, wget, apt; sourced after scripts/lib/common.sh for log helpers.
# Variables:
#   ROCM_VERSION        ROCm version string, e.g. 7.2.1      (default: 7.2.1)
#   AMDGPU_INSTALLER    Full .deb URL for amdgpu-install     (default: noble 7.2.1.70201)
#   GFX_TARGET          GPU architecture token, e.g. gfx942  (default: gfx942)
#   UBUNTU_CODENAME     Ubuntu release codename              (default: noble)
# Repository:   gpu-bench / sys-bench workload template
# License:      Apache-2.0

# ────────────────────────────────────────────────────────────────────────────
# Version pins — override with environment variables before sourcing if needed.
# ────────────────────────────────────────────────────────────────────────────
ROCM_VERSION="${ROCM_VERSION:-7.2.1}"
UBUNTU_CODENAME="${UBUNTU_CODENAME:-noble}"
GFX_TARGET="${GFX_TARGET:-gfx942}"

# Installer URL pinned to CSV specification pattern.
AMDGPU_INSTALLER="${AMDGPU_INSTALLER:-https://repo.radeon.com/amdgpu-install/${ROCM_VERSION}/ubuntu/${UBUNTU_CODENAME}/amdgpu-install_${ROCM_VERSION}.70201-1_all.deb}"
_AMDGPU_DEB_FILE="amdgpu-install_${ROCM_VERSION}.70201-1_all.deb"

# ────────────────────────────────────────────────────────────────────────────
# Internal helpers (use log_ functions from common.sh when available, fall back
# to plain echo otherwise so this library is safe to source standalone).
# ────────────────────────────────────────────────────────────────────────────
_rocm_log()  { if declare -f log_info  >/dev/null 2>&1; then log_info  "$*"; else echo "[rocm_install] $*"; fi; }
_rocm_warn() { if declare -f log_warn  >/dev/null 2>&1; then log_warn  "$*"; else echo "[rocm_install] WARN: $*" >&2; fi; }
_rocm_die()  { if declare -f log_error >/dev/null 2>&1; then log_error "$*"; else echo "[rocm_install] ERROR: $*" >&2; fi; exit 1; }

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
mkdir -p "${ROCM_SOURCE_ROOT}"

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
    _rocm_log "Downloading amdgpu-install ${ROCM_VERSION} for ${UBUNTU_CODENAME}..."
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

_rocm_install_linux_modules_extra() {
    local running newest
    running="$(uname -r)"
    run_noninteractive_root DEBIAN_FRONTEND=noninteractive apt-get install -y "linux-modules-extra-${running}" \
        || _rocm_warn "linux-modules-extra-${running} not available"
    newest="$(ls -1 /lib/modules 2>/dev/null | sort -V | tail -1 || true)"
    if [[ -n "${newest}" && "${newest}" != "${running}" ]]; then
        _rocm_log "Pending kernel ${newest} differs from running ${running}; installing extras for both."
        run_noninteractive_root DEBIAN_FRONTEND=noninteractive apt-get install -y "linux-modules-extra-${newest}" \
            || _rocm_warn "linux-modules-extra-${newest} not available"
    fi
}


# ════════════════════════════════════════════════════════════════════════════
# FUNCTION 1 — rocm_install_runtime
#
# Purpose: Full ROCm runtime install on a bare-metal Ubuntu server that has no
#          existing AMD GPU software. After amdgpu-dkms builds AMD's amdgpu.ko
#          for the running kernel, unloads Ubuntu's in-box amdgpu and loads the
#          DKMS build (modprobe -r / modprobe), then verifies every GPU came
#          back on the DKMS driver. Reboots once only if that reload cannot be
#          done or verified (amdgpu_reload_instead_of_reboot in
#          amdgpu_reload.sh; ROCM_RELOAD_INSTEAD_OF_REBOOT=0 always reboots).
#          Step 02 uses apt-get upgrade, which keeps back new kernels, so the
#          running kernel is the one DKMS built for. linux-modules-extra is
#          still installed for a newer pending kernel too, in case the image
#          already had one installed.
#
# WARNING: If the reload fails, this function calls "sudo reboot" once. The
#          caller must handle reconnection (e.g., systemd auto-resume in
#          setup.sh) and must exit while the stage file remains. When the
#          reload succeeds, the function returns with the stage file cleared.
#
# Deferred reboot: with ROCM_DEFER_REBOOT=1 (set by setup.sh) a failed reload
#          does not reboot here. Stage3 stays saved, ROCM_REBOOT_PENDING=1 is
#          set, and the function returns 0. The caller installs everything
#          else, then reboots once; after that reboot this function logs the
#          reboot step and clears the stage, as for an immediate reboot.
#
# When to call: setup.sh, when benchmark_specification.json
#   Execution Domain is "GPU Compute / ROCm" AND the machine has no ROCm
#   installation (check: [ ! -f /opt/rocm/bin/rocm-smi ]).
# ════════════════════════════════════════════════════════════════════════════
rocm_install_runtime() {
    _rocm_log "=== rocm_install_runtime: ROCm ${ROCM_VERSION} on ${UBUNTU_CODENAME} ==="
    local stage
    # Read by setup.sh after this function returns.
    # shellcheck disable=SC2034
    ROCM_REBOOT_PENDING=0
    stage="$(_rocm_runtime_stage_get)"
    _rocm_log "Runtime install stage: ${stage}"

    if [[ "${stage}" == "stage1" ]]; then
        _rocm_status_phase "Phase 1:  ## Install ROCm Runtime Tools (On Bare Metal Ubuntu Server - NOT ROCm server)"
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

        # Step 03 — Pre-driver reboot removed. One reboot after DKMS loads both
        # a staged kernel (if apt upgrade installed one) and the amdgpu module.
        _rocm_log "Skipping pre-driver reboot; continuing install in this invocation."
        _rocm_status_step 3 "pre-driver reboot skipped; single reboot after amdgpu-dkms"
        # Fall through to the install steps below (same invocation).
    fi

    if [[ "${stage}" == "stage1" || "${stage}" == "stage2" ]]; then
        _rocm_status_phase "Phase 1:  ## Install ROCm Runtime Tools (On Bare Metal Ubuntu Server - NOT ROCm server)"
        # Step 04 — Downloads the AMD GPU installer .deb package from the Radeon (AMD ROCm) repository.
        _rocm_log "Download AMD GPU installer .deb package."
        _rocm_download_installer
        _rocm_status_step 4 "wget -O amdgpu-install_<version>.deb ${AMDGPU_INSTALLER}  # Download AMD GPU installer package"

        # Step 05 — Installs the downloaded AMD GPU installer .deb package used to install the full ROCm software stack.
        _rocm_log "Install the downloaded AMD GPU installer package."
        _rocm_apt_install_local_deb_noninteractive "./${_AMDGPU_DEB_FILE}"  # Install downloaded AMD GPU installer .deb
        _rocm_status_step 5 "sudo apt-get install -y ./amdgpu-install_<version>.deb  # Install downloaded AMD GPU installer .deb"

        # Step 06 — Install ROCm Runtime, HIP Runtime + Compiler (hipcc), rocBLAS, rocBLASLt, rocFFT, rocRAND, rocSOLVER, rocSPARSE, RCCL, MIOpen, rocWMMA, rocPRIM, rocThrust, hipBLASLt, hipBLAS, hipFFT, hipRAND, hipSPARSE, hipSOLVER, hipTensor, OpenCL runtime and graphics stack.
        _rocm_log "Install ROCm usecase stack and userspace components."
        set +e
        run_noninteractive_root amdgpu-install -y \
            --usecase=rocm,rocmdev,hiplibsdk,mlsdk,opencl,graphics \
            --no-dkms  # Install ROCm userspace stack without dkms at this phase
        local rc_usecase=$?
        set -e
        if [[ "${rc_usecase}" -ne 0 ]]; then
            if ! apt-cache show amdgpu-lib >/dev/null 2>&1; then
                _rocm_warn "Primary amdgpu-install usecase requires amdgpu-lib, which is unavailable in current repos."
                _rocm_warn "Retrying with compute-focused usecase (dropping opencl,graphics)."
                run_noninteractive_root amdgpu-install -y \
                    --usecase=rocm,rocmdev,hiplibsdk,mlsdk \
                    --no-dkms \
                    || _rocm_die "amdgpu-install failed for both primary and fallback usecases."
            else
                _rocm_die "amdgpu-install failed for primary usecase. Check apt repositories and amdgpu-install logs."
            fi
        fi
        _rocm_status_step 6 "sudo amdgpu-install -y --usecase=rocm,rocmdev,hiplibsdk,mlsdk,opencl,graphics --no-dkms  # Install ROCm userspace stack"

        # Step 07 — Install the AMD GPU kernel driver module package.
        _rocm_log "Install amdgpu-dkms package."
        run_noninteractive_root DEBIAN_FRONTEND=noninteractive apt-get install -y amdgpu-dkms  # Install AMD GPU DKMS kernel module package
        _rocm_status_step 7 "sudo apt-get install -y amdgpu-dkms  # Install AMD GPU DKMS kernel module package"

        # Step 08 — Install InfiniBand and RDMA userspace libraries required by the amdgpu kernel module.
        _rocm_log "Install RDMA userspace libraries required by ROCm."
        run_noninteractive_root DEBIAN_FRONTEND=noninteractive apt-get install -y rdma-core ibverbs-providers libibverbs1  # Install RDMA/InfiniBand userspace libraries
        _rocm_status_step 8 "sudo apt-get install -y rdma-core ibverbs-providers libibverbs1  # Install RDMA/InfiniBand userspace libraries"

        # Step 09 — Install extra kernel modules including peer memory symbols needed by amdgpu.
        # Install for the running kernel and, if apt upgrade staged a newer one,
        # that pending kernel too — there is no pre-driver reboot to switch first.
        _rocm_log "Install kernel module extras for running and any pending kernel."
        _rocm_install_linux_modules_extra
        _rocm_status_step 9 "sudo apt-get install -y linux-modules-extra-\$(uname -r)  # plus pending kernel if different"

        # Step 10 — Rebuild kernel module dependency map.
        _rocm_log "Refresh kernel module dependency map."
        run_noninteractive_root depmod -a  # Rebuild kernel module dependency map
        _rocm_status_step 10 "sudo depmod -a  # Rebuild kernel module dependency map"

        # Step 11 — BY ITSELF, installs rocm-core, hsa-rocr, hip-runtime-amd, rocblas, rocfft, rocrand, rocsolver, rocsparse, rccl, hipblas, hipblaslt, hipfft, hiprand, hipsparse, hipsolver, hiptensor.
        _rocm_log "Install rocm-libs meta-package."
        run_noninteractive_root DEBIAN_FRONTEND=noninteractive apt-get install -y rocm-libs  # Install rocm-libs meta-package (for runtime libraries)
        _rocm_status_step 11 "sudo apt-get install -y rocm-libs  # Install rocm-libs meta-package (for runtime libraries)"

        # Step 12 — Reload amdgpu so AMD's DKMS driver replaces the in-box one; reboot only if that fails.
        # The stage is saved first: if the reload hangs or the host goes down, setup
        # resumes at stage3 after the reboot, as it always has.
        _rocm_runtime_stage_set "stage3"
        if declare -f amdgpu_reload_instead_of_reboot >/dev/null 2>&1 \
            && amdgpu_reload_instead_of_reboot dkms; then
            _rocm_status_step 12 "sudo modprobe -r amdgpu && sudo modprobe amdgpu  # Reload amdgpu to load the DKMS driver (verified; no reboot)"
            _rocm_runtime_stage_clear
            _rocm_log "Runtime installation stage is complete; amdgpu-dkms loaded without a reboot."
            return 0
        fi
        if [[ "${ROCM_DEFER_REBOOT:-0}" == 1 ]]; then
            # setup.sh installs everything else first and reboots once at the end.
            # shellcheck disable=SC2034
            ROCM_REBOOT_PENDING=1
            echo "ROCM_REBOOT_BOOT_ID=$(_rocm_current_boot_id)" >> "$(_rocm_runtime_stage_file)"
            _rocm_log "Driver reload not possible or not verified; reboot to load amdgpu-dkms postponed until the rest of setup is installed (ROCM_DEFER_REBOOT=1)."
            return 0
        fi
        _rocm_log "Reboot once to load amdgpu-dkms (driver reload not possible or not verified)."
        run_noninteractive_root reboot  # Single reboot after driver install (fallback)
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
        _rocm_status_phase "Phase 1:  ## Install ROCm Runtime Tools (On Bare Metal Ubuntu Server - NOT ROCm server)"
        _rocm_status_step 12 "sudo reboot  # Reboot to load the newly installed amdgpu kernel driver"
        _rocm_runtime_stage_clear
        _rocm_log "Runtime installation stage is complete after post-driver reboot."
    fi
}


# ════════════════════════════════════════════════════════════════════════════
# FUNCTION 2 — rocm_add_repository
#
# Purpose: Add the official ROCm APT repository to a server that already has
#          an amdgpu driver installed or that will install packages from the
#          ROCm apt feed directly (without amdgpu-install).
#          Idempotent: skips steps that are already complete.
#
# When to call: setup.sh, when the ROCm apt repository
#   is not yet present (check: [ ! -f /etc/apt/sources.list.d/rocm.list ]).
# ════════════════════════════════════════════════════════════════════════════
rocm_add_repository() {
    _rocm_log "=== rocm_add_repository: ROCm ${ROCM_VERSION} on ${UBUNTU_CODENAME} ==="
    _rocm_status_phase "Phase 2:  ## Add ROCm Repository (On Bare Metal Ubuntu Server, ROCm server)"

    # Step 13 — For users not root, adds the current user to the render and video groups for GPU access permissions.
    _rocm_log "Add current user to render and video groups for GPU access."
    local target_user="${LOGNAME:-${SUDO_USER:-${USER:-$(id -un)}}}"
    if [[ -n "${target_user}" ]]; then
        run_noninteractive_root usermod -a -G render,video "${target_user}"  # Add user to render,video groups
        _rocm_status_step 13 "sudo usermod -a -G render,video <user>  # Add user to render,video groups"
    else
        _rocm_warn "Could not resolve target user for render/video group assignment; skipping usermod."
    fi

    # Step 14 — Downloads the ROCm GPG signing key from AMD’s repository.
    _rocm_log "Import ROCm GPG signing key and write keyring."
    wget -qO - https://repo.radeon.com/rocm/rocm.gpg.key \
        | run_noninteractive_root gpg --yes --dearmor \
              -o /usr/share/keyrings/rocm.gpg  # Download + dearmor ROCm key into keyring
    _rocm_status_step 14 "wget -qO - https://repo.radeon.com/rocm/rocm.gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/rocm.gpg"

    # Step 15 — Adds the ROCm repository to the system’s APT sources.
    _rocm_log "Add ROCm apt source list entry for target Ubuntu codename."
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/rocm.gpg] \
https://repo.radeon.com/rocm/apt/debian/ ${UBUNTU_CODENAME} main" \
        | run_noninteractive_root tee /etc/apt/sources.list.d/rocm.list > /dev/null  # (noble_Ubuntu24/jammy_Ubuntu22) Adds ROCm repository to APT sources
    _rocm_status_step 15 "echo 'deb [arch=amd64 signed-by=/usr/share/keyrings/rocm.gpg] https://repo.radeon.com/rocm/apt/debian/ <codename> main' | sudo tee /etc/apt/sources.list.d/rocm.list"

    # Step 16 — Updates the APT package index, downloading package lists from the newly added ROCm repository.
    _rocm_log "Update apt package index after adding ROCm repository."
    run_noninteractive_root apt update -y  # Update apt index to include ROCm repository
    _rocm_status_step 16 "sudo apt update -y  # Update apt index to include ROCm repository"

    # Step 17 — Ensure installation of rocm-dev and rocm-libs.
    _rocm_log "Install ROCm development and runtime meta-packages."
    run_noninteractive_root DEBIAN_FRONTEND=noninteractive apt-get install -y \
        rocm-dev rocm-libs rocm-smi  # Install ROCm repository packages
    _rocm_status_step 17 "sudo apt-get install -y rocm-dev rocm-libs rocm-smi  # Install ROCm repository packages"

    _rocm_log "ROCm repository added and base packages installed."
}


# ════════════════════════════════════════════════════════════════════════════
# FUNCTION 3 — rocm_install_rvs
#
# Purpose: Install the ROCm Validation Suite (RVS) and its runtime dependencies
#          on a server that already has amdgpu-install available.
#          Idempotent: skips if rvs binary already exists.
#
# When to call: setup.sh, when benchmark_specification.json
#   Workload Name contains "ROCm Validation" or "RVS", or when the Workload
#   Command Line Executable is "rvs".
# ════════════════════════════════════════════════════════════════════════════
rocm_install_rvs() {
    _rocm_log "=== rocm_install_rvs: ROCm Validation Suite ${ROCM_VERSION} ==="
    _rocm_status_phase "Phase 3:  ## Install ROCm Validation Suite (On Bare Metal Ubuntu Server, ROCm server)"

    # Step 18 — Download the AMD GPU driver installer package.
    _rocm_log "Download the AMD GPU driver installer package."
    _rocm_download_installer
    _rocm_status_step 18 "wget -O amdgpu-install_<version>.deb ${AMDGPU_INSTALLER}  # Download AMD GPU driver installer package"

    # Step 19 — Install amdgpu-install tool.
    _rocm_log "Install amdgpu-install tool."
    _rocm_apt_install_local_deb_noninteractive "./${_AMDGPU_DEB_FILE}" \
        || { _rocm_warn "Failed to install amdgpu-install tool."; return 1; }  # Install AMD GPU Installer
    _rocm_status_step 19 "sudo apt-get install -y ./amdgpu-install_<version>.deb  # Install AMD GPU Installer"
    run_noninteractive_root DEBIAN_FRONTEND=noninteractive apt-get update -y \
        || { _rocm_warn "apt update failed after amdgpu-install tool install."; return 1; }

    # Step 20 — Install RVS runtime dependencies.
    _rocm_log "Install RVS runtime dependencies."
    run_noninteractive_root DEBIAN_FRONTEND=noninteractive apt-get install -y \
        libpci3 libpci-dev libyaml-cpp-dev amd-smi-lib rocblas \
        || { _rocm_warn "Failed to install one or more RVS runtime dependency packages."; return 1; }  # Install RVS runtime dependencies
    _rocm_status_step 20 "sudo apt-get install -y libpci3 libpci-dev libyaml-cpp-dev amd-smi-lib rocblas  # Install RVS runtime dependencies"

    # Step 21 — Install the diagnostic and stress-testing framework ROCm Validation Suite (RVS).
    _rocm_log "Skip RVS installation if command already exists on PATH."
    run_noninteractive_root DEBIAN_FRONTEND=noninteractive apt-get install -y rocm-validation-suite \
        || { _rocm_warn "Failed to install rocm-validation-suite package."; return 1; }  # Install the ROCm Validation Suite (RVS)
    _rocm_status_step 21 "sudo apt-get install -y rocm-validation-suite  # Install the ROCm Validation Suite (RVS)"

    # Step 22 — Add /opt/rocm/bin to PATH.
    _rocm_log "Add /opt/rocm/bin to PATH."
    _rocm_log "Add /opt/rocm/bin to PATH in current shell."
    if [[ ":${PATH}:" != *":/opt/rocm/bin:"* ]]; then
        _rocm_log "Adding /opt/rocm/bin to PATH for current session."
        export PATH=/opt/rocm/bin:$PATH  # Add /opt/rocm/bin to PATH
    fi
    _rocm_status_step 22 "export PATH=/opt/rocm/bin:\$PATH  # Add /opt/rocm/bin to PATH"

    # Step 23 — Update PATH in .bashrc.
    _rocm_log "Persist /opt/rocm/bin PATH export in .bashrc."
    _rocm_append_bashrc_once 'export PATH=/opt/rocm/bin:$PATH'
    _rocm_status_step 23 "echo 'export PATH=/opt/rocm/bin:\$PATH' >> ~/.bashrc  # Update PATH in .bashrc"

    local rocm_bin
    if rocm_bin="$(_rocm_resolve_rocm_bin)"; then
        if [[ ":${PATH}:" != *":${rocm_bin}:"* ]]; then
            export PATH="${rocm_bin}:${PATH}"
        fi
        _rocm_append_bashrc_once "export PATH=${rocm_bin}:\$PATH"
    fi

    if command -v rvs >/dev/null 2>&1; then
        _rocm_log "RVS installed. Verify with: rvs --version"
        return 0
    fi
    if [[ -n "${rocm_bin:-}" && -x "${rocm_bin}/rvs" ]]; then
        _rocm_log "RVS installed at ${rocm_bin}/rvs. Verify with: ${rocm_bin}/rvs --version"
        return 0
    fi
    _rocm_warn "RVS package installation completed but rvs command is still unavailable."
    return 1
}


# ════════════════════════════════════════════════════════════════════════════
# FUNCTION 4 — rocm_compile_rocblas_bench
#
# Purpose: Clone the official ROCm/rocBLAS repository, check out the pinned
#          release branch, and build the rocblas-bench and test clients
#          targeting the configured GFX_TARGET (default: gfx942 / MI300X).
#          Idempotent: skips the build if rocblas-bench already exists at the
#          expected staging path.
#
# Output:  Binary at ${REPO_ROOT}/third_party/rocBLAS/build/release/clients/staging/rocblas-bench
#          (not /opt/rocm/bin/rocblas-bench and not ~/rocBLAS). PATH and
#          LD_LIBRARY_PATH are exported for the current session.
#
# When to call: scripts/build.sh, when a resolved implementation component
#   sets contracts.compile_rocblas_bench. Framework listing rocblas-bench is
#   install/verify only unless that contract is set.
# ════════════════════════════════════════════════════════════════════════════
rocm_compile_rocblas_bench() {
    _rocm_log "=== rocm_compile_rocblas_bench: rocBLAS ${ROCM_VERSION} / ${GFX_TARGET} ==="

    local staging_dir="${ROCBLAS_SOURCE_DIR}/build/release/clients/staging"
    local bench_bin="${staging_dir}/rocblas-bench"
    if [[ -f "${bench_bin}" ]]; then
        chmod +x "${bench_bin}" || true
        _rocm_log "rocblas-bench already built at ${bench_bin}. Skipping build."
        export PATH="${staging_dir}:${PATH}"
        export LD_LIBRARY_PATH="/opt/rocm/lib:${LD_LIBRARY_PATH:-}"
        return 0
    fi
    # Step 24 — APT updates the local list of available packages and versions from all configured repositories.
    _rocm_log "APT updates the local list of available packages and versions from all configured repositories."
    run_noninteractive_root apt update  # Update the list of available packages (does not install pkgs)

    # Step 25 — Install Fortran BLAS/LAPACK symbols used by test and benchmark executables.
    _rocm_log "Install Fortran BLAS/LAPACK symbols used by test and benchmark executables."
    run_noninteractive_root apt install -y gfortran  # Install Fortran BLAS/LAPACK symbols used by executables

    # Step 26 — Install Google Test (GTest) unit testing framework used by test and benchmark executables.
    _rocm_log "Install Google Test (GTest) unit testing framework used by test and benchmark executables."
    run_noninteractive_root apt install -y libgtest-dev  # Install Google Test (GTest) unit testing framework

    # Step 27 — Remove old cmake as it is version 3.22 is outdated to rocBLAS.
    _rocm_log "Remove old cmake as it is version 3.22 is outdated to rocBLAS."
    run_noninteractive_root apt remove cmake cmake-data -y  # Remove old cmake as it is version 3.22 is outdated to rocBLAS.

    # Step 28 — Download Kitware's GPG public key and add it to Ubuntu's trusted keyring.
    _rocm_log "Download Kitware's GPG public key and add it to Ubuntu's trusted keyring."
    wget -O - https://apt.kitware.com/keys/kitware-archive-latest.asc | run_noninteractive_root apt-key add -  # Download Kitware's GPG public key and add it to Ubuntu's trusted keyring.

    # Step 29 — Adds the official Kitware APT repository to the system.
    _rocm_log "Add the official Kitware APT repository to the system."
    echo 'deb https://apt.kitware.com/ubuntu/ noble main' | run_noninteractive_root tee /etc/apt/sources.list.d/kitware.list  # Adds the official Kitware APT repository to the system.

    # Step 30 — APT updates the local list of available packages and versions from all configured repositories.
    _rocm_log "APT updates the local list of available packages and versions from all configured repositories."
    run_noninteractive_root apt update  # Update the list of available packages (does not install pkgs)

    # Step 31 — Verify cmake version.
    _rocm_log "Verify cmake version."
    run_noninteractive_root apt install -y cmake  # Verify cmake version.

    # Step 32 — Install Python 3 header files and development libraries for compiling C/C++ code.
    _rocm_log "Install Python 3 header files and development libraries for compiling C/C++ code."
    run_noninteractive_root apt install -y git python3-dev  # Install Python 3 header files and development libraries for compiling C/C++ code.

    # Step 33 — Clone the official rocBLAS source code repository from GitHub to the local machine.
    _rocm_log "Clone the official rocBLAS source code repository from GitHub to the local machine."
    if [[ ! -d "${ROCBLAS_SOURCE_DIR}/.git" ]]; then
        mkdir -p "$(dirname "${ROCBLAS_SOURCE_DIR}")"
        git clone https://github.com/ROCm/rocBLAS.git "${ROCBLAS_SOURCE_DIR}"  # Clone inside the workload repository.
    fi

    # Step 34 — Change the current working directory to the newly created rocBLAS project folder.
    _rocm_log "Change the current working directory to the newly created rocBLAS project folder."
    cd "${ROCBLAS_SOURCE_DIR}"  # Change to the repository-local rocBLAS project folder.

    # Step 35 — Switch the repository to the ROCm 7.2.1 branch.
    _rocm_log "Switch the repository to the ROCm 7.2.1 branch."
    git checkout rocm-7.2.1  # Switch the repository to the ROCm 7.2.1 branch.

    # Step 36 — Build rocBLAS benchmark and test clients targeting MI300X gfx942.
    _rocm_log "Build rocBLAS benchmark and test clients targeting MI300X gfx942."
    chmod +x ./install.sh
    ./install.sh --clients-only -a gfx942  # (takes five minutes) Build rocBLAS benchmark and test clients targeting MI300X gfx942.

    # Step 37 — Add staging to PATH.
    _rocm_log "Add staging to PATH."
    export PATH="${ROCBLAS_SOURCE_DIR}/build/release/clients/staging:${PATH}"  # Add staging to PATH

    # Step 38 — Update PATH in .bashrc.
    _rocm_log "Update PATH in .bashrc."
    _rocm_log "Repository-local rocBLAS PATH exported for this setup process."

    # Step 39 — Add libraries to PATH.
    _rocm_log "Add libraries to PATH."
    export LD_LIBRARY_PATH="${ROCBLAS_SOURCE_DIR}/build/release/rocblas/library:${ROCBLAS_SOURCE_DIR}/build/release:/opt/rocm/lib:${LD_LIBRARY_PATH}"  # Add libraries to PATH.

    # Step 40 — Update LD_LIBRARY_PATH in .bashrc.
    _rocm_log "Update LD_LIBRARY_PATH in .bashrc."
    _rocm_log "Repository-local rocBLAS libraries exported for this setup process."

    # Step 41 — Create a results folder.
    _rocm_log "Create a results folder."
    mkdir -p ~/rocblas_tests  # Create a results folder

    # Return to original working directory if available.
    cd - >/dev/null 2>&1 || true

    _rocm_log "rocblas-bench built successfully at ${bench_bin}"
    _rocm_log "Verify with: rocblas-bench --version"
}
