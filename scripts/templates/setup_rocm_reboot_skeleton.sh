#!/usr/bin/env bash
# File: scripts/templates/setup_rocm_reboot_skeleton.sh
# Version: 1.3.0
# Maintainer: AI Agent GPU Benchmark Repo Generator
# Date: 2026-08-26
# Description: Reusable local-only setup.sh skeleton for ROCm workloads with systemd reboot auto-resume.
# Execution: Copy to generated repo root as setup.sh, then adapt workload skip flags if needed.
# Options: --skip-rocm, --skip-rvs, --assume-yes, --resume-auto, --no-resume-auto, --resume-from-service, --help
# Requirements: Ubuntu 24.04 or Ubuntu 26.04; bash; selected Python interpreter; sudo/systemd for ROCm installation.
# Environment: Local benchmark host; remote execution is not supported.
# Dependencies: scripts/lib/common.sh, scripts/lib/rocm_install.sh (dispatches to rocm_install_24_04.sh or rocm_install_26_04.sh), python3-venv, sqlite3, autotools
# Variables: BENCHMARK_PYTHON, BENCHMARK_SKIP_ROCM, BENCHMARK_SKIP_RVS, BENCHMARK_BUILD_FAISS_ROCM, BENCHMARK_INSTALL_RUST, BENCHMARK_INSTALL_PYTORCH, BENCHMARK_INSTALL_TORCHVISION, BENCHMARK_INSTALL_AITER, BENCHMARK_INSTALL_SGLANG, SGLANG_SOURCE_DIR, SGLANG_REPO_URL, AITER_SOURCE_DIR, AITER_REPO_URL, ROCM_VERSION, UBUNTU_CODENAME, GFX_TARGET, ROCM_RELOAD_INSTEAD_OF_REBOOT, PYTORCH_ROCM_INDEX_URL, PYTORCH_VERSION, TORCHVISION_VERSION, PYTORCH_INSTALL_SPEC, TORCHVISION_INSTALL_SPEC
# Repository: gpu-bench/sys-bench template
# License: Apache-2.0

set -euo pipefail

if [[ -z "${HOME:-}" ]]; then
  HOME="$(getent passwd "$(id -u)" | cut -d: -f6 2>/dev/null || true)"
  HOME="${HOME:-/root}"
  export HOME
fi
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}"
export PATH="${HOME}/.cargo/bin:${PATH}"
if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
fi
case "${VERSION_ID:-}" in
  26.04*)
    export ROCM_VERSION="${ROCM_VERSION:-10.1.0}"
    export UBUNTU_CODENAME="${UBUNTU_CODENAME:-resolute}"
    ;;
  *)
    export ROCM_VERSION="${ROCM_VERSION:-10.1.0}"
    export UBUNTU_CODENAME="${UBUNTU_CODENAME:-noble}"
    ;;
esac
export GFX_TARGET="${GFX_TARGET:-gfx942}"
# ROCm 10.1.0 wheels. torch[device-gfx942] pulls the gfx942 device package.
PYTORCH_ROCM_INDEX_URL="${PYTORCH_ROCM_INDEX_URL:-https://stable.repo.amd.com/rocm/whl-next/}"
PYTORCH_VERSION="${PYTORCH_VERSION:-2.13.0+rocm10.1.0}"
TORCHVISION_VERSION="${TORCHVISION_VERSION:-0.28.0+rocm10.1.0}"
TORCHAUDIO_VERSION="${TORCHAUDIO_VERSION:-2.11.0.2+rocm10.1.0}"
PYTORCH_INSTALL_SPEC="${PYTORCH_INSTALL_SPEC:-torch[device-gfx942]==${PYTORCH_VERSION}}"
TORCHVISION_INSTALL_SPEC="${TORCHVISION_INSTALL_SPEC:-torchvision[device-gfx942]==${TORCHVISION_VERSION}}"
TORCHAUDIO_INSTALL_SPEC="${TORCHAUDIO_INSTALL_SPEC:-torchaudio==${TORCHAUDIO_VERSION}}"
VLLM_WHEEL_INDEX_URL="${VLLM_WHEEL_INDEX_URL:-https://rocm.frameworks.amd.com/whl-multi-arch/vllm/}"
VLLM_AMD_CP314_WHEEL_URL="${VLLM_AMD_CP314_WHEEL_URL:-https://rocm.frameworks.amd.com/whl-multi-arch/vllm/vllm/vllm-0.29.1.dev0%2Brocm10.1.0.g98dff2a81.d20261002-cp314-cp314-linux_x86_64.whl}"
FLASH_ATTN_VERSION="${FLASH_ATTN_VERSION:-2.8.3}"
AITER_VERSION="${AITER_VERSION:-0.1.22.post2.dev0+gb4d9154d1.d20261002}"
TENSORIZER_VERSION="${TENSORIZER_VERSION:-2.12.1}"
BENCHMARK_INSTALL_PYTORCH_WAS_SET="${BENCHMARK_INSTALL_PYTORCH+x}"
BENCHMARK_INSTALL_AITER_WAS_SET="${BENCHMARK_INSTALL_AITER+x}"
BENCHMARK_INSTALL_SGLANG_WAS_SET="${BENCHMARK_INSTALL_SGLANG+x}"
BENCHMARK_COMPILE_SGLANG_WAS_SET="${BENCHMARK_COMPILE_SGLANG+x}"
BENCHMARK_INSTALL_PYTORCH="${BENCHMARK_INSTALL_PYTORCH:-0}"
BENCHMARK_INSTALL_TORCHVISION="${BENCHMARK_INSTALL_TORCHVISION:-0}"
BENCHMARK_INSTALL_AITER="${BENCHMARK_INSTALL_AITER:-0}"
BENCHMARK_INSTALL_SGLANG="${BENCHMARK_INSTALL_SGLANG:-0}"
BENCHMARK_INSTALL_JAX="${BENCHMARK_INSTALL_JAX:-0}"
BENCHMARK_INSTALL_RUST="${BENCHMARK_INSTALL_RUST:-0}"
BENCHMARK_COMPILE_SGLANG="${BENCHMARK_COMPILE_SGLANG:-0}"
BENCHMARK_BUILD_FAISS_ROCM="${BENCHMARK_BUILD_FAISS_ROCM:-0}"
SGLANG_SOURCE_DIR="${SGLANG_SOURCE_DIR:-}"
SGLANG_REPO_URL="${SGLANG_REPO_URL:-https://github.com/sgl-project/sglang.git}"
# ROCm 10.1.0 lists SGLang 0.5.18. Pin the commit AMD pairs with torch 2.13.
SGLANG_REPO_REF="${SGLANG_REPO_REF:-71de97b264b04dcd514cf904003028aefe9775c8}"
AITER_SOURCE_DIR="${AITER_SOURCE_DIR:-}"
AITER_REPO_URL="${AITER_REPO_URL:-https://github.com/ROCm/aiter.git}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_NAME="$(basename "${REPO_ROOT}")"
cd "${REPO_ROOT}"
# shellcheck disable=SC1091
source "${REPO_ROOT}/scripts/lib/keep_running_kernel.sh"
if [[ -z "${SGLANG_SOURCE_DIR}" ]]; then
  SGLANG_SOURCE_DIR="${REPO_ROOT}/third_party/sglang"
elif [[ "${SGLANG_SOURCE_DIR}" != "${REPO_ROOT}/"* ]]; then
  echo "[WARN] Ignoring external SGLANG_SOURCE_DIR=${SGLANG_SOURCE_DIR}; using ${REPO_ROOT}/third_party/sglang" >&2
  SGLANG_SOURCE_DIR="${REPO_ROOT}/third_party/sglang"
fi
if [[ -z "${AITER_SOURCE_DIR}" ]]; then
  AITER_SOURCE_DIR="${REPO_ROOT}/third_party/aiter"
elif [[ "${AITER_SOURCE_DIR}" != "${REPO_ROOT}/"* ]]; then
  echo "[WARN] Ignoring external AITER_SOURCE_DIR=${AITER_SOURCE_DIR}; using ${REPO_ROOT}/third_party/aiter" >&2
  AITER_SOURCE_DIR="${REPO_ROOT}/third_party/aiter"
fi
# Check for Ubuntu's own /usr/bin/python3, not any python3 on PATH: some cloud images
# activate a virtualenv (for example /root/.venv, Python 3.11) and ship no distro
# Python, so "command -v python3" succeeded and the version probe asked apt for
# python3.11-venv, which Ubuntu does not publish.
if [[ ! -x /usr/bin/python3 ]]; then
  keep_running_kernel
  DEBIAN_FRONTEND=noninteractive apt-get update -y
  DEBIAN_FRONTEND=noninteractive apt-get install -y python3
fi
if [[ -z "${BENCHMARK_PYTHON:-}" && -x /usr/bin/python3 ]]; then
  export BENCHMARK_PYTHON=/usr/bin/python3
fi
if [[ -f benchmark_specification.json ]]; then
  workload_framework="$("${PYTHON_BOOTSTRAP:-python3}" - <<'PY'
import json
from pathlib import Path
fields = {
    item.get("field_name", ""): item.get("value", "")
    for item in json.loads(Path("benchmark_specification.json").read_text(encoding="utf-8"))
}
print(fields.get("Framework") or fields.get("Software Framework", ""))
PY
  )"
  workload_name="$("${PYTHON_BOOTSTRAP:-python3}" - <<'PY'
import json
from pathlib import Path
fields = {
    item.get("field_name", ""): item.get("value", "")
    for item in json.loads(Path("benchmark_specification.json").read_text(encoding="utf-8"))
}
print(fields.get("Workload Name", ""))
PY
  )"
  if [[ -f "${REPO_ROOT}/scripts/framework_registry.py" ]]; then
    eval "$("${PYTHON_BOOTSTRAP:-python3}" "${REPO_ROOT}/scripts/framework_registry.py" --spec benchmark_specification.json --vendor amd --format env)"
    if [[ -n "${BENCHMARK_INSTALL_PYTORCH_WAS_SET}" ]]; then
      BENCHMARK_INSTALL_PYTORCH="${BENCHMARK_INSTALL_PYTORCH_WAS_SET}"
    fi
    if [[ -n "${BENCHMARK_INSTALL_SGLANG_WAS_SET}" ]]; then
      BENCHMARK_INSTALL_SGLANG="${BENCHMARK_INSTALL_SGLANG_WAS_SET}"
    fi
    if [[ -n "${BENCHMARK_INSTALL_AITER_WAS_SET}" ]]; then
      BENCHMARK_INSTALL_AITER="${BENCHMARK_INSTALL_AITER_WAS_SET}"
    fi
    if [[ -n "${BENCHMARK_COMPILE_SGLANG_WAS_SET}" ]]; then
      BENCHMARK_COMPILE_SGLANG="${BENCHMARK_COMPILE_SGLANG_WAS_SET}"
    fi
  else
    if [[ -z "${BENCHMARK_INSTALL_PYTORCH_WAS_SET}" ]] &&
       ! grep -Eiq '(^|[,[:space:]])vllm([,[:space:]]|$)' <<< "${workload_framework}"; then
      if grep -Eiq '(^|[,[:space:]])pytorch([,-]|[[:space:]]|$)' <<< "${workload_framework}" ||
         grep -Eiq 'Silent Data|Tensor Op|Microkernel|ResNet|BERT|DistilBERT|JAX XLA|GEMM / rocBLAS|MIOpen Convolution' <<< "${workload_name}"; then
        BENCHMARK_INSTALL_PYTORCH=1
      fi
    fi
    if grep -Eiq 'torchvision|ResNet' <<< "${workload_framework}${workload_name}"; then
      BENCHMARK_INSTALL_TORCHVISION=1
    fi
    if grep -Eiq '(^|[,[:space:]])jax([,[:space:]]|$)' <<< "${workload_framework}"; then
      BENCHMARK_INSTALL_JAX=1
    fi
    if grep -Eiq '(^|[,[:space:]])sglang([,[:space:]]|$)' <<< "${workload_framework}"; then
      if [[ -z "${BENCHMARK_INSTALL_SGLANG_WAS_SET}" ]]; then
        BENCHMARK_INSTALL_SGLANG=1
      fi
      if [[ -z "${BENCHMARK_INSTALL_AITER_WAS_SET}" ]]; then
        BENCHMARK_INSTALL_AITER=1
      fi
      if [[ -z "${BENCHMARK_COMPILE_SGLANG_WAS_SET}" ]]; then
        BENCHMARK_COMPILE_SGLANG=1
      fi
      BENCHMARK_INSTALL_TORCHVISION=1
    fi
    if grep -Eiq '(^|[,[:space:]])faiss([,[:space:]]|$)' <<< "${workload_framework}"; then
      BENCHMARK_BUILD_FAISS_ROCM=1
    fi
  fi
fi
export ROCM_SOURCE_ROOT="${ROCM_SOURCE_ROOT:-${REPO_ROOT}/third_party}"
# Shared across every repo generated as a sibling under the same parent
# directory (e.g. /root/<N>_<name>/), not per-repo. The first ROCm-torch
# workload in a batch used to cold-download the ~6.2 GB wheel into
# <repo>/.cache/pip; every later repo in the same batch then repeated that
# full download into its own isolated cache instead of reusing pip's HTTP
# cache from the first one -- this is what made the first torch consumer in
# a batch prone to hitting the 60-minute setup/smoke gate before smoke ever
# ran.
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-$(dirname "${REPO_ROOT}")/.shared_pip_cache}"
export PYTORCH_FIND_LINKS="${PYTORCH_FIND_LINKS:-$(dirname "${REPO_ROOT}")/.shared_pytorch_wheels}"
export HF_HOME="${HF_HOME:-${REPO_ROOT}/.cache/huggingface}"
export CARGO_HOME="${CARGO_HOME:-${REPO_ROOT}/.cache/cargo}"
mkdir -p "${ROCM_SOURCE_ROOT}" "${PIP_CACHE_DIR}" "${PYTORCH_FIND_LINKS}" "${HF_HOME}" "${CARGO_HOME}"

source scripts/lib/common.sh
source scripts/lib/noninteractive_root.sh
source scripts/lib/rocm_install.sh
PYTHON_BOOTSTRAP="${BENCHMARK_PYTHON:-python3}"
if [[ "${PYTHON_BOOTSTRAP}" == */* ]]; then
  [[ -x "${PYTHON_BOOTSTRAP}" ]] || die "BENCHMARK_PYTHON is not executable: ${PYTHON_BOOTSTRAP}"
else
  PYTHON_BOOTSTRAP="$(command -v "${PYTHON_BOOTSTRAP}")" ||
    die "BENCHMARK_PYTHON was not found: ${BENCHMARK_PYTHON:-python3}"
fi
PYTHON_TARGET_VERSION="$("${PYTHON_BOOTSTRAP}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
VENV_ROOT="${REPO_ROOT}/.venv"
PYTHON_BIN="${VENV_ROOT}/bin/python"

SKIP_ROCM="${BENCHMARK_SKIP_ROCM:-0}"
if [[ -n "${BENCHMARK_SKIP_RVS:-}" ]]; then
  SKIP_RVS="${BENCHMARK_SKIP_RVS}"
elif grep -Eiq '(^|[,[:space:]])rvs([,[:space:]]|$)' <<< "${workload_framework:-}"; then
  SKIP_RVS=0
else
  SKIP_RVS=1
fi
ASSUME_YES=0
RESUME_AUTO=1
RESUME_FROM_SERVICE=0
# 1 while the amdgpu reboot is postponed to the end of this run: the GPU is not
# usable yet, so checks that need it and the workload build wait for the run
# after the reboot.
GPU_CHECKS_AFTER_REBOOT=0

RESUME_SERVICE_NAME="${REPO_NAME}-setup-resume.service"
RESUME_SERVICE_FILE="/etc/systemd/system/${RESUME_SERVICE_NAME}"
RESUME_LOG="results/reboot_resume.log"
RUNTIME_STAGE_FILE=".rocm_runtime_stage.env"
STATUS_FILE="results/install_status.txt"
COMMANDS_FILE="results/install_commands.txt"
LOCK_FILE="${REPO_ROOT}/.setup.lock"

# flock releases this descriptor automatically if setup is killed by reboot.
exec 9>"${LOCK_FILE}"
flock -n 9 || die "Another setup.sh invocation is already running; inspect ${RESUME_LOG}."

usage() {
  cat <<USAGE
Usage: bash setup.sh [options]

Options:
  --skip-rocm          Skip ROCm runtime/repository setup.
  --skip-rvs           Skip ROCm Validation Suite setup.
  --assume-yes, -y     Suppress first-run interactive notice.
  --resume-auto        Enable systemd auto-resume after reboot (default).
  --no-resume-auto     Disable systemd auto-resume; operator reruns setup manually.
  --resume-from-service
                       Internal flag used by the systemd oneshot service.
  --help               Show this help text.

After the ROCm driver/firmware install, setup reloads the amdgpu driver instead
of rebooting. If the reload cannot be verified, setup installs everything else
first and then reboots once; after that reboot the systemd resume service
builds the workload and checks the GPU (a few minutes at most). Set
ROCM_RELOAD_INSTEAD_OF_REBOOT=0 to always reboot, and ROCM_DEFER_REBOOT=0 to
reboot right after the driver install as older templates did.

This generated repository is local-only. Remote execution flags are rejected.
USAGE
}

for arg in "$@"; do
  case "$arg" in
    --skip-rocm) SKIP_ROCM=1 ;;
    --skip-rvs) SKIP_RVS=1 ;;
    --assume-yes|-y) ASSUME_YES=1 ;;
    --resume-auto) RESUME_AUTO=1 ;;
    --no-resume-auto) RESUME_AUTO=0 ;;
    --resume-from-service) RESUME_FROM_SERVICE=1; ASSUME_YES=1 ;;
    --exec-mode=*|--exec-mode|--remote|--ssh-host|--ssh-key|--remote-host)
      die "Remote execution options are not supported; this repository is local-only."
      ;;
    --help) usage; exit 0 ;;
    *) die "Unknown setup option: ${arg}" ;;
  esac
done

run_privileged() {
  # Root runs directly; otherwise sudo. A terminal stdin is replaced with
  # /dev/null and SIGTTOU is ignored, so apt-get cannot stop on sudo's pty when
  # output is redirected (the 26.04 benchmark-loop hang). Pipes/heredocs are kept.
  run_noninteractive_root "$@"
}

install_status_sync_motd() {
  local tmp
  tmp="$(mktemp)"
  {
    echo "${REPO_NAME} setup status"
    echo "========================================"
    [[ -f "${STATUS_FILE}" ]] && cat "${STATUS_FILE}"
    echo
    echo "To see latest status on install, execute the following:"
    echo "cat ${REPO_ROOT}/results/install_status.txt     # Shows recent status (static)"
    echo "tail -f ${REPO_ROOT}/results/install_status.txt # Shows running status (dynamic)"
    echo
  } > "${tmp}"
  run_privileged cp "${tmp}" /etc/motd 2>/dev/null || true
  rm -f "${tmp}"
}

install_commands_log() {
  local raw="$1"
  local cmd
  cmd="${raw%%#*}"
  cmd="${cmd%"${cmd##*[![:space:]]}"}"
  cmd="${cmd#"${cmd%%[![:space:]]*}"}"
  [[ -n "${cmd}" ]] || return 0
  case "${cmd}" in
    sudo\ *|wget\ *|echo\ *|export\ *|git\ *|mkdir\ *|cd\ *|curl\ *|apt\ *|apt-get\ *|amdgpu-install\ *|./*)
      mkdir -p results
      printf '%s\n' "${cmd}" >> "${COMMANDS_FILE}"
      ;;
  esac
}

install_status_log_phase() {
  mkdir -p results
  echo "$(date -u '+%Y-%m-%d %H:%M:%S')  PHASE $*" >> "${STATUS_FILE}"
  install_status_sync_motd
}

install_status_log_step() {
  mkdir -p results
  echo "$(date -u '+%Y-%m-%d %H:%M:%S')  STEP $1 $2" >> "${STATUS_FILE}"
  install_commands_log "$2"
  install_status_sync_motd
}

install_status_log_setup() {
  mkdir -p results
  echo "$(date -u '+%Y-%m-%d %H:%M:%S')  SETUP $*" >> "${STATUS_FILE}"
  install_status_sync_motd
}

log_resume_event() {
  mkdir -p results
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >> "${RESUME_LOG}"
}

# A check that needs a working GPU failed. Before the postponed reboot the GPU
# cannot work yet, so this is only a warning; the run after the reboot repeats
# the check and stops on failure.
gpu_check_failed() {
  if [[ "${GPU_CHECKS_AFTER_REBOOT}" == 1 ]]; then
    log_warn "$* (expected before the amdgpu reboot; checked again after it)"
    return 0
  fi
  die "$*"
}

# Usage: gpu_check "<message if it fails>" command [args...]
gpu_check() {
  local message="$1"
  shift
  "$@" || gpu_check_failed "${message}"
}

# rocm_add_repository adds the user to the render and video groups. Groups apply
# at the next login. When the driver is reloaded instead of rebooting, nothing
# forces that login, so the shell that ran setup.sh (and a benchmark loop that
# continues in it) would get "permission denied" on /dev/kfd. Grant this user
# access to the current GPU device nodes with an ACL. The ACL lasts until the
# nodes are recreated (next reboot or driver reload); by then a new login has
# the groups.
grant_gpu_access_this_session() {
  [[ "$(id -u)" -ne 0 ]] || return 0
  local user
  user="$(id -un)"
  [[ " $(id -nG) " == *" render "* ]] && return 0
  [[ " $(id -nG "${user}" 2>/dev/null) " == *" render "* ]] || return 0
  local -a nodes=()
  local node
  for node in /dev/kfd /dev/dri/renderD* /dev/dri/card*; do
    [[ -e "${node}" ]] && nodes+=("${node}")
  done
  (( ${#nodes[@]} > 0 )) || return 0
  if command -v setfacl >/dev/null 2>&1 && run_privileged setfacl -m "u:${user}:rw" "${nodes[@]}"; then
    install_status_log_phase "Granted ${user} GPU device access for this login; render/video groups apply at next login"
  else
    log_warn "${user} was added to the render and video groups, which apply at the next login."
    log_warn "Log out and back in (or run: newgrp render) before running GPU benchmarks."
  fi
}

install_resume_service() {
  [[ "${RESUME_AUTO}" == 1 ]] || return 0
  if ! command -v systemctl >/dev/null 2>&1; then
    log_resume_event "systemctl unavailable; auto-resume not installed"
    return 0
  fi

  run_privileged tee "${RESUME_SERVICE_FILE}" >/dev/null <<EOF
[Unit]
Description=Resume ${REPO_NAME} setup.sh after reboot
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
# ROCm setup and wheel installation can exceed systemd's default 90-second
# startup timeout. The service must not report a successful setup as failed.
TimeoutStartSec=infinity
TimeoutStopSec=0
KillMode=process
Environment=HOME=/root
Environment=BENCHMARK_REPO_ROOT=${REPO_ROOT}
Environment=BENCHMARK_PYTHON=${PYTHON_BOOTSTRAP}
WorkingDirectory=${REPO_ROOT}
ExecStart=/bin/bash ${REPO_ROOT}/setup.sh --assume-yes --resume-auto --resume-from-service
StandardOutput=append:${REPO_ROOT}/results/reboot_resume.log
StandardError=append:${REPO_ROOT}/results/reboot_resume.log

[Install]
WantedBy=multi-user.target
EOF
  run_privileged systemctl daemon-reload
  run_privileged systemctl enable "${RESUME_SERVICE_NAME}"
  local timeout_start
  timeout_start="$(run_privileged systemctl show -p TimeoutStartUSec --value "${RESUME_SERVICE_NAME}" 2>/dev/null || true)"
  if [[ "${timeout_start}" != "infinity" && "${timeout_start}" != "0" ]]; then
    die "Resume service has unsafe TimeoutStartUSec=${timeout_start}; refusing reboot-capable setup."
  fi
  run_privileged systemctl is-enabled "${RESUME_SERVICE_NAME}" >/dev/null
  install_status_log_phase "Auto-resume service enabled: ${RESUME_SERVICE_NAME}"
  log_resume_event "Enabled ${RESUME_SERVICE_FILE}"
}

cleanup_resume_service() {
  if command -v systemctl >/dev/null 2>&1 && run_privileged test -f "${RESUME_SERVICE_FILE}"; then
    if [[ "${RESUME_FROM_SERVICE}" == 1 ]]; then
      # This setup.sh IS the running start job of that unit. Reloading systemd
      # after removing its file reloads the unit without TimeoutStartSec=infinity;
      # systemd then times the start job out and SIGTERMs setup.sh (seen 26.04,
      # 13:53:13, before .setup_state). Disable without a reload and remove the
      # file; systemd drops the unit at its next reload or boot.
      run_privileged systemctl disable --no-reload "${RESUME_SERVICE_NAME}" >/dev/null 2>&1 || true
      run_privileged rm -f "${RESUME_SERVICE_FILE}"
      install_status_log_phase "Auto-resume service removed (systemd reload deferred): ${RESUME_SERVICE_NAME}"
      log_resume_event "Removed ${RESUME_SERVICE_FILE}; reload deferred while running as that service"
      rm -f "${RUNTIME_STAGE_FILE}"
      return 0
    fi
    run_privileged systemctl disable "${RESUME_SERVICE_NAME}" >/dev/null 2>&1 || true
    run_privileged rm -f "${RESUME_SERVICE_FILE}"
    run_privileged systemctl daemon-reload || true
    # The unit was just disabled and removed above, so it is normally already
    # unloaded and has nothing to reset — only call reset-failed when systemd
    # actually has it recorded as failed, so we don't print a spurious
    # "Unit ... not loaded" error in the common (non-reboot) case.
    if run_privileged systemctl is-failed --quiet "${RESUME_SERVICE_NAME}" 2>/dev/null; then
      run_privileged systemctl reset-failed "${RESUME_SERVICE_NAME}" >/dev/null 2>&1 || true
    fi
    install_status_log_phase "Auto-resume service removed: ${RESUME_SERVICE_NAME}"
    log_resume_event "Removed ${RESUME_SERVICE_FILE}"
  fi
  rm -f "${RUNTIME_STAGE_FILE}"
}

mkdir -p results/raw results/parsed tests/fixtures
if [[ ! -f "${STATUS_FILE}" || "${RESUME_FROM_SERVICE}" != 1 && ! -f "${RUNTIME_STAGE_FILE}" ]]; then
  : > "${STATUS_FILE}"
  : > "${COMMANDS_FILE}"
fi

install_status_log_phase "setup.sh start"

if [[ "${ASSUME_YES}" != 1 && "${SKIP_ROCM}" != 1 ]]; then
  echo "This setup reloads the amdgpu driver in place of a reboot. If the reload cannot"
  echo "be verified (ROCM_RELOAD_INSTEAD_OF_REBOOT=0 always reboots), setup installs"
  echo "everything else first and reboots once at the end."
  echo "Auto-resume after that reboot is enabled by default via systemd; it builds the"
  echo "workload and checks the GPU, then reports SETUP complete."
  echo "Status is in results/install_status.txt and mirrored to /etc/motd."
  echo "Executed install commands are listed in results/install_commands.txt."
  echo "Press Enter to continue."
  read -r _
fi

if [[ "${SKIP_ROCM}" != 1 ]]; then
  # This must happen before any protected ROCm function can request a reboot.
  install_resume_service
fi

if [[ "$(uname -s)" == "Linux" && -x /usr/bin/apt-get ]]; then
  PYTHON_MINOR="${PYTHON_TARGET_VERSION}"
  keep_running_kernel
  run_privileged env DEBIAN_FRONTEND=noninteractive apt-get update -y
  run_privileged env DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3 python3-venv "python${PYTHON_MINOR}-venv" python3-pip ripgrep sqlite3 autoconf automake libtool libtool-bin m4 pkg-config flex bison cmake build-essential ninja-build numactl git curl protobuf-compiler libprotobuf-dev acl
  # Ubuntu 26.04 hipcc (Clang 23) needs GCC 15 headers; GCC 16 has no <cstdlib> for HIP wrappers.
  if [[ "${VERSION_ID:-}" == 26.04* ]]; then
    run_privileged env DEBIAN_FRONTEND=noninteractive apt-get install -y g++-15 gcc-15 || true
  fi
  if [[ "${BENCHMARK_INSTALL_RUST}" == 1 ]]; then
    run_privileged env DEBIAN_FRONTEND=noninteractive apt-get install -y rustc cargo
  fi
  if [[ "${BENCHMARK_BUILD_FAISS_ROCM:-0}" == 1 ]]; then
    run_privileged env DEBIAN_FRONTEND=noninteractive apt-get install -y \
      libopenblas-dev libgflags-dev swig python3-dev "python${PYTHON_MINOR}-dev"
  fi
fi

if [[ "${BENCHMARK_INSTALL_RUST}" == 1 ]]; then
  if ! command -v rustup >/dev/null 2>&1; then
    command -v curl >/dev/null 2>&1 || die "curl is required to install the current Rust toolchain."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable
    export PATH="${HOME}/.cargo/bin:${PATH}"
  fi
  rustup default stable >/dev/null
  command -v cargo >/dev/null 2>&1 || die "Cargo is unavailable after Rust installation."
fi
command -v protoc >/dev/null 2>&1 || die "protoc is unavailable after protobuf-compiler installation."

if [[ "${SKIP_ROCM}" != 1 ]]; then
  # Always process persisted runtime state before any "ROCm already present" shortcut.
  # rocm-smi alone does not mean the GPU can initialize: a refreshed image can
  # ship ROCm userspace with an empty /lib/firmware/amdgpu. The in-tree amdgpu
  # driver then logs "Direct firmware load ... failed" and KFD has no GPU node.
  # Treat missing amdgpu firmware as "runtime not installed" so the runtime
  # install (firmware package + its single reboot) runs.
  amdgpu_firmware_present=0
  if compgen -G "/lib/firmware/updates/amdgpu/*" >/dev/null ||
     compgen -G "/lib/firmware/amdgpu/*" >/dev/null; then
    amdgpu_firmware_present=1
  fi
  # ROCm 10.1 ships amd-smi and hipcc. The older rocm-smi binary is not in the
  # amdrocm10.1 packages (Ubuntu's separate rocm-smi 7.1 package is not this stack).
  rocm_smi_present=0
  if [[ -x /opt/rocm/bin/amd-smi || -x /opt/rocm/core-10.1/bin/amd-smi ||
        -x /opt/rocm/bin/hipcc || -x /opt/rocm/core-10.1/bin/hipcc ||
        -x /opt/rocm/bin/rocm-smi || -x /opt/rocm/core-10.1/bin/rocm-smi ]]; then
    rocm_smi_present=1
  fi
  if [[ -f "${RUNTIME_STAGE_FILE}" || "${rocm_smi_present}" != 1 || "${amdgpu_firmware_present}" != 1 ]]; then
    if [[ "${rocm_smi_present}" == 1 && "${amdgpu_firmware_present}" != 1 ]]; then
      log_resume_event "ROCm userspace present but no amdgpu firmware; running runtime install"
    fi
    # ROCM_DEFER_REBOOT=1: if the driver reload fails, the installer does not
    # reboot; it keeps stage3 and sets ROCM_REBOOT_PENDING=1, and this run
    # installs everything else and reboots once at the end. ROCM_DEFER_REBOOT=0
    # restores the reboot right after the driver install.
    export ROCM_DEFER_REBOOT="${ROCM_DEFER_REBOOT:-1}"
    rocm_install_runtime
    # The protected installer persists stage3 before its single reboot and
    # clears the stage file after that reboot.
    if [[ -f "${RUNTIME_STAGE_FILE}" && "${ROCM_REBOOT_PENDING:-0}" == 1 ]]; then
      GPU_CHECKS_AFTER_REBOOT=1
      export BENCHMARK_GPU_CHECKS_AFTER_REBOOT=1
      install_status_log_phase "amdgpu could not be reloaded in place; installing everything now and rebooting once at the end"
      log_resume_event "Runtime reboot postponed until the rest of setup is installed"
    elif [[ -f "${RUNTIME_STAGE_FILE}" ]]; then
      # An immediate reboot was requested (ROCM_DEFER_REBOOT=0). Do not advance
      # to repository, RVS, or build phases while a runtime stage remains.
      install_status_log_phase "Runtime reboot requested; setup will resume automatically"
      log_resume_event "Runtime stage remains; exiting until systemd resume"
      exit 0
    fi
  fi
  rocm_add_repository
  grant_gpu_access_this_session
else
  install_status_log_step rocm "skipped by operator flag"
fi

if [[ "${SKIP_RVS}" != 1 ]]; then
  command -v rvs >/dev/null 2>&1 || rocm_install_rvs
else
  install_status_log_step rvs "skipped by operator flag"
fi

# shellcheck disable=SC1091
source "${REPO_ROOT}/scripts/lib/uv_python_314.sh"
ensure_uv_python_314 || die "uv could not install CPython 3.14 for the benchmark virtualenv."
PYTHON_BOOTSTRAP="${UV_PYTHON}"
PYTHON_TARGET_VERSION="3.14"
if [[ -x "${VENV_ROOT}/bin/python" ]]; then
  VENV_PYTHON_VERSION="$("${VENV_ROOT}/bin/python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  [[ "${VENV_PYTHON_VERSION}" == "${PYTHON_TARGET_VERSION}" ]] ||
    die "${VENV_ROOT} already uses Python ${VENV_PYTHON_VERSION}; remove it and rerun setup for Python ${PYTHON_TARGET_VERSION}."
fi
if [[ ! -x "${VENV_ROOT}/bin/python" ]] || ! "${VENV_ROOT}/bin/python" -c 'import pip' >/dev/null 2>&1; then
  echo "[WARN] Existing Python venv is incomplete; recreating it with pip: ${VENV_ROOT}"
  "${PYTHON_BOOTSTRAP}" -m venv --clear --upgrade-deps "${VENV_ROOT}" 2>/dev/null ||
    "${PYTHON_BOOTSTRAP}" -m venv --clear "${VENV_ROOT}"
fi
[[ -x "${VENV_ROOT}/bin/python" ]] || die "Unable to create ${VENV_ROOT}/bin/python."
if ! "${VENV_ROOT}/bin/python" -c 'import pip' >/dev/null 2>&1; then
  die "Python venv has no pip after python3-venv installation; install the matching python3.X-venv package."
fi
source "${VENV_ROOT}/bin/activate"
"${PYTHON_BIN}" -m pip install --upgrade pip
if grep -Eq '^[[:space:]]*(torch|torchvision|torchaudio)(\[.*\])?([<>=].*)?$' requirements.txt; then
  grep -Eq 'stable.repo.amd.com/rocm/whl-next|download.pytorch.org/whl/rocm' requirements.txt || \
    die "ROCm workload requirements must reference the official ROCm wheel index."
fi
"${PYTHON_BIN}" -m pip install -r requirements.txt --extra-index-url "${PYTORCH_ROCM_INDEX_URL}"
install_status_log_step python "created ${VENV_ROOT} and installed requirements"

install_rocm_bundled_amdsmi() {
  # PyPI amdsmi 7.x references amdsmi_set_gpu_clk_range, which libamd_smi.so
  # from ROCm 10.1.0 does not export. Use the Python package shipped with ROCm.
  local amd_smi_py="" candidate site_pkg amdsmi_err
  for candidate in /opt/rocm/share/amd_smi /opt/rocm/core-*/share/amd_smi; do
    if [[ -f "${candidate}/amdsmi/__init__.py" ]]; then
      amd_smi_py="${candidate}"
      break
    fi
  done
  if [[ -z "${amd_smi_py}" ]]; then
    die "ROCm Python amdsmi package is missing under /opt/rocm."
  fi
  "${PYTHON_BIN}" -m pip uninstall -y amdsmi >/dev/null 2>&1 || true
  site_pkg="$("${PYTHON_BIN}" -c 'import site; print(site.getsitepackages()[0])')"
  printf '%s\n' "${amd_smi_py}" > "${site_pkg}/rocm_amdsmi.pth"
  export LD_LIBRARY_PATH="/opt/rocm/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
  if ! amdsmi_err="$("${PYTHON_BIN}" -c 'import amdsmi; print(amdsmi.__file__)' 2>&1)"; then
    die "amdsmi installation verification failed: ${amdsmi_err}"
  fi
  printf '%s\n' "${amdsmi_err}"
}

install_workload_rocm_packages() {
  local framework wheel_url
  framework="$("${PYTHON_BIN}" - <<'PY'
import json
from pathlib import Path
fields = {item.get("field_name", ""): item.get("value", "") for item in json.loads(Path("benchmark_specification.json").read_text())}
print(fields.get("Framework") or fields.get("Software Framework", ""))
PY
)"
  if grep -Eiq '(^|[,[:space:]])vllm([,[:space:]]|$)' <<< "${framework}"; then
    wheel_url="$("${PYTHON_BIN}" - <<'PY'
import json
from pathlib import Path
fields = {item.get("field_name", ""): item.get("value", "") for item in json.loads(Path("benchmark_specification.json").read_text())}
print(fields.get("vLLM Wheel/Source Index", "").strip())
PY
)"
    case "${wheel_url}" in
      https://wheels.vllm.ai/rocm/*|https://rocm.frameworks.amd.com/whl-multi-arch/vllm/*|https://rocm.frameworks.amd.com/whl-multi-arch/vllm-cdna/*) ;;
      *) die "ROCm vLLM workload lacks an official ROCm vLLM wheel URL." ;;
    esac
    if [[ "${wheel_url}" != *cp314* ]]; then
      log_warn "Spec vLLM URL is not cp314; installing the ROCm 10.1.0 cp314 wheel."
      wheel_url="${VLLM_AMD_CP314_WHEEL_URL}"
    fi
    "${PYTHON_BIN}" -m pip install \
      --index-url "${PYTORCH_ROCM_INDEX_URL}" \
      --extra-index-url https://pypi.org/simple \
      ${PYTORCH_INSTALL_SPEC} ${TORCHVISION_INSTALL_SPEC} ${TORCHAUDIO_INSTALL_SPEC}
    "${PYTHON_BIN}" -m pip install --no-deps "${wheel_url}"
    "${PYTHON_BIN}" -m pip install \
      "flash-attn==${FLASH_ATTN_VERSION}" \
      --index-url "${VLLM_WHEEL_INDEX_URL}" \
      --extra-index-url https://pypi.org/simple ||
      log_warn "AMD flash-attn ${FLASH_ATTN_VERSION} install skipped"
    "${PYTHON_BIN}" -m pip install "tensorizer==${TENSORIZER_VERSION}" ||
      log_warn "tensorizer ${TENSORIZER_VERSION} install skipped"
    "${PYTHON_BIN}" -m pip install packaging
    "${PYTHON_BIN}" - <<'PY' > "${REPO_ROOT}/.vllm_requirements.txt"
from importlib.metadata import requires
from packaging.requirements import Requirement

excluded = {
    "torch", "torchvision", "torchaudio",
    "flash-attn", "flash_attn", "amd-aiter", "aiter", "amd-quark",
}
for raw in requires("vllm") or []:
    requirement = Requirement(raw)
    if requirement.marker is not None and not requirement.marker.evaluate():
        continue
    if requirement.name.lower() not in excluded:
        print(str(requirement))
PY
    "${PYTHON_BIN}" -m pip install \
      -r "${REPO_ROOT}/.vllm_requirements.txt" \
      --extra-index-url "${VLLM_WHEEL_INDEX_URL}" \
      --extra-index-url "${PYTORCH_ROCM_INDEX_URL}" ||
      log_warn "vLLM extra-deps install was non-fatal; installing API-server extras next"
    rm -f "${REPO_ROOT}/.vllm_requirements.txt"
    # vLLM's dependency pin reinstalls tensorizer 2.10.1, whose libsodium lookup
    # raises KeyError: crypto_stream_salsa20_NONCEBYTES on Ubuntu 26.04.
    "${PYTHON_BIN}" -m pip install "tensorizer==${TENSORIZER_VERSION}" ||
      die "tensorizer ${TENSORIZER_VERSION} reinstall failed after vLLM extra-deps."
    # api_server.py imports uvloop on startup. Extra-deps can skip it when
    # amd-quark>=0.8.99 is missing.
    "${PYTHON_BIN}" -m pip install uvloop fastapi "aiohttp>=3.13.3" ||
      die "vLLM API-server extras (uvloop/fastapi/aiohttp) failed."
    install_rocm_bundled_amdsmi
    # Importing torch first empties amdsmi handles on this stack. A .pth
    # import runs before vLLM argparse so baseline/extended can infer ROCm.
    # Do not install sitecustomize.py: Ubuntu's /usr/lib/python3.14 copy wins.
    site_pkg="${VENV_ROOT}/lib/python${PYTHON_TARGET_VERSION}/site-packages"
    src_custom="${REPO_ROOT}/scripts/templates/vllm_rocm_sitecustomize.py"
    if [[ ! -f "${src_custom}" ]]; then
      die "Missing ${src_custom}; published clones must ship scripts/templates/vllm_rocm_sitecustomize.py."
    fi
    cp -a "${src_custom}" "${site_pkg}/vllm_rocm_bootstrap.py"
    printf '%s\n' 'import vllm_rocm_bootstrap' > "${site_pkg}/vllm_rocm_bootstrap.pth"
    gpu_check "Official vLLM ROCm wheel verification failed." \
      "${PYTHON_BIN}" -c 'import vllm, uvloop; print(f"vLLM {vllm.__version__}")'
    install_status_log_step vllm "installed and verified official ROCm wheel"
  fi
  if grep -Eiq '(^|[,[:space:]])amd-smi([,[:space:]]|$)' <<< "${framework}"; then
    install_rocm_bundled_amdsmi
    install_status_log_step amdsmi "installed and verified Python amdsmi package"
  fi
}

if [[ "${SKIP_ROCM}" != 1 ]]; then
  install_workload_rocm_packages
else
  install_status_log_step workload-packages "skipped with explicit --skip-rocm override"
fi

install_rocm_pytorch() {
  local torch_version="${PYTORCH_VERSION}"
  local torch_versions
  torch_versions="$("${PYTHON_BIN}" -m pip index versions torch --index-url "${PYTORCH_ROCM_INDEX_URL}" 2>&1)" \
    || die "Unable to query PyTorch versions at ${PYTORCH_ROCM_INDEX_URL}."
  grep -Fq "${torch_version}" <<< "${torch_versions}" \
    || die "PyTorch ${torch_version} is not published at ${PYTORCH_ROCM_INDEX_URL}."
  read -r -a torch_packages <<< "${PYTORCH_INSTALL_SPEC}"
  if [[ "${BENCHMARK_INSTALL_TORCHVISION}" == 1 ]]; then
    local torchvision_versions
    torchvision_versions="$("${PYTHON_BIN}" -m pip index versions torchvision --index-url "${PYTORCH_ROCM_INDEX_URL}" 2>&1)" \
      || die "Unable to query torchvision versions at ${PYTORCH_ROCM_INDEX_URL}."
    grep -Fq "${TORCHVISION_VERSION}" <<< "${torchvision_versions}" \
      || die "torchvision ${TORCHVISION_VERSION} is not published at ${PYTORCH_ROCM_INDEX_URL}."
    read -r -a torchvision_packages <<< "${TORCHVISION_INSTALL_SPEC}"
    torch_packages+=("${torchvision_packages[@]}")
  fi
  local -a find_links_args=()
  if [[ -n "${PYTORCH_FIND_LINKS:-}" && -d "${PYTORCH_FIND_LINKS}" ]]; then
    find_links_args=(--find-links "${PYTORCH_FIND_LINKS}")
  fi
  "${PYTHON_BIN}" -m pip install --index-url "${PYTORCH_ROCM_INDEX_URL}" \
    --extra-index-url https://pypi.org/simple "${find_links_args[@]}" \
    "${torch_packages[@]}" "${TORCHAUDIO_INSTALL_SPEC}"
  if [[ "${GPU_CHECKS_AFTER_REBOOT}" == 1 ]]; then
    # No usable GPU until the postponed reboot: check the ROCm build only. The
    # run after the reboot does the full GPU check below.
    "${PYTHON_BIN}" -c 'import torch, sys; print(f"PyTorch {torch.__version__}; HIP {torch.version.hip}"); sys.exit(0 if torch.version.hip else 1)' ||
      die "PyTorch ROCm verification failed: the installed torch is not a ROCm build"
    install_status_log_step pytorch "installed ROCm wheel pair (GPU check after the reboot)"
    return 0
  fi
  "${PYTHON_BIN}" - <<'PY'
import torch
if torch.version.hip is None or not torch.cuda.is_available():
    raise SystemExit("PyTorch ROCm verification failed: HIP/GPU is unavailable")
torch.zeros(1, device="cuda")
name = torch.cuda.get_device_name(0)
print(f"PyTorch {torch.__version__}; HIP {torch.version.hip}; GPU {name}; device_count={torch.cuda.device_count()}")
PY
  install_status_log_step pytorch "installed and verified ROCm wheel pair"
}

if [[ "${BENCHMARK_INSTALL_PYTORCH}" == 1 ]]; then
  install_status_log_phase "Installing and verifying ROCm PyTorch wheels"
  install_rocm_pytorch
fi

if [[ -n "${workload_framework:-}${workload_name:-}" ]]; then
  if grep -Eiq 'hugging[[:space:][:punct:]]?face|bert|distilbert' <<< "${workload_framework}${workload_name}" &&
     ! grep -Eiq '(^|[,[:space:]])vllm([,[:space:]]|$)|sglang' <<< "${workload_framework}"; then
    if ! "${PYTHON_BIN}" -c "import transformers" >/dev/null 2>&1; then
      "${PYTHON_BIN}" -m pip install transformers datasets
    fi
    "${PYTHON_BIN}" -c "import transformers; print(transformers.__version__)" ||
      die "transformers installation verification failed."
    install_status_log_step transformers "installed and verified Hugging Face transformers"
  fi
  if grep -Eiq 'gups|numpy' <<< "${workload_framework}${workload_name}"; then
    "${PYTHON_BIN}" -m pip install numpy
    "${PYTHON_BIN}" -c "import numpy; print(numpy.__version__)" ||
      die "numpy installation verification failed."
    install_status_log_step numpy "installed and verified numpy"
  fi
  if grep -Eiq 'lmbench' <<< "${workload_framework}${workload_name}"; then
    if ! command -v lat_syscall >/dev/null 2>&1 && ! [[ -x /usr/lib/lmbench/bin/lat_syscall ]]; then
      run_privileged env DEBIAN_FRONTEND=noninteractive apt-get install -y lmbench ||
        log_warn "lmbench package install deferred"
    fi
    install_status_log_step lmbench "lmbench binaries available or install attempted"
  fi
  if grep -Eiq 'fio|flexible i/o' <<< "${workload_framework}${workload_name}"; then
    command -v fio >/dev/null 2>&1 || run_privileged env DEBIAN_FRONTEND=noninteractive apt-get install -y fio ||
      log_warn "fio package install deferred"
    install_status_log_step fio "fio available or install attempted"
  fi
  if grep -Eiq 'iperf' <<< "${workload_framework}${workload_name}"; then
    command -v iperf3 >/dev/null 2>&1 || run_privileged env DEBIAN_FRONTEND=noninteractive apt-get install -y iperf3 ||
      log_warn "iperf3 package install deferred"
    install_status_log_step iperf3 "iperf3 available or install attempted"
  fi
  if grep -Eiq 'stress-ng' <<< "${workload_framework}${workload_name}"; then
    command -v stress-ng >/dev/null 2>&1 || run_privileged env DEBIAN_FRONTEND=noninteractive apt-get install -y stress-ng ||
      log_warn "stress-ng package install deferred"
    install_status_log_step stress-ng "stress-ng available or install attempted"
  fi
  if [[ "${BENCHMARK_INSTALL_PERF:-0}" == "1" ]] || grep -Eiq 'linux pmu|linux perf|(^|[^[:alnum:]_])perf([^[:alnum:]_]|$)' <<< "${workload_framework}${workload_name}"; then
    # linux-tools-generic depends on the newest kernel image and headers.
    # A missing linux-tools package for this kernel fails the perf workload.
    run_privileged env DEBIAN_FRONTEND=noninteractive apt-get install -y linux-tools-common \
      "linux-tools-$(uname -r)"
    install_status_log_step perf "installed linux-tools for the running kernel"
  fi
fi

if [[ "${BENCHMARK_INSTALL_JAX}" == 1 ]]; then
  # jax and jaxlib come from PyPI. The ROCm 10 plugin and PJRT come from whl-next.
  JAX_ROCM_PLUGIN_SPEC="${JAX_ROCM_PLUGIN_SPEC:-jax_rocm10_plugin==0.11.1+rocm10.1.0}"
  JAX_ROCM_PJRT_SPEC="${JAX_ROCM_PJRT_SPEC:-jax_rocm10_pjrt==0.11.1+rocm10.1.0}"
  "${PYTHON_BIN}" -m pip install --index-url "${PYTORCH_ROCM_INDEX_URL}" \
    --extra-index-url https://pypi.org/simple \
    "${JAX_ROCM_PLUGIN_SPEC}" "${JAX_ROCM_PJRT_SPEC}" ||
    die "JAX ROCm plugin wheel install failed."
  "${PYTHON_BIN}" -m pip install jax==0.11.1 jaxlib==0.11.1
  gpu_check "JAX ROCm verification failed." \
    "${PYTHON_BIN}" -c 'import jax, sys; devs=[d for d in jax.devices() if "cpu" not in str(d).lower()]; print(devs); sys.exit(0 if devs else 1)'
  install_status_log_step jax "installed and verified JAX ROCm plugin"
fi

if [[ "${BENCHMARK_INSTALL_AITER}" == 1 ]]; then
  # ROCm 10.1.0 publishes amd-aiter on the vLLM multi-arch index. Import name is aiter.
  export LIBRARY_PATH="/opt/rocm/lib:${LIBRARY_PATH:-}"
  export LD_LIBRARY_PATH="/opt/rocm/lib:${LD_LIBRARY_PATH:-}"
  if [[ -e /opt/rocm/lib/libamdhip64.so && ! -e "${VENV_ROOT}/lib/libamdhip64.so" ]]; then
    ln -sfn /opt/rocm/lib/libamdhip64.so "${VENV_ROOT}/lib/libamdhip64.so"
  fi
  if ! "${PYTHON_BIN}" -c 'import aiter' >/dev/null 2>&1; then
    "${PYTHON_BIN}" -m pip install "amd-aiter==${AITER_VERSION}" \
      --index-url "${VLLM_WHEEL_INDEX_URL}" \
      --extra-index-url https://pypi.org/simple || true
  fi
  if ! "${PYTHON_BIN}" -c 'import aiter' >/dev/null 2>&1; then
    if [[ "${BENCHMARK_COMPILE_SGLANG}" == 1 ]]; then
      if [[ ! -d "${AITER_SOURCE_DIR}/.git" ]]; then
        git clone --recursive "${AITER_REPO_URL}" "${AITER_SOURCE_DIR}"
      else
        git -C "${AITER_SOURCE_DIR}" submodule sync
        git -C "${AITER_SOURCE_DIR}" submodule update --init --recursive
      fi
      (
        cd "${AITER_SOURCE_DIR}"
        PYTORCH_ROCM_ARCH="${GFX_TARGET}" "${PYTHON_BIN}" setup.py develop
      )
    else
      log_warn "AITER source clone skipped; install the AMD amd-aiter wheel so import aiter succeeds."
    fi
  fi
  export SGLANG_USE_AITER=1
  gpu_check "AITER installation failed or ROCm Torch was replaced." \
    "${PYTHON_BIN}" -c 'import aiter, torch; assert torch.version.hip'
  install_status_log_step aiter "installed and verified AMD AITER kernels"
fi

if [[ "${BENCHMARK_INSTALL_SGLANG}" == 1 ]]; then
  "${PYTHON_BIN}" -m pip uninstall -y nvidia-cutlass nvidia-cutlass-dsl cutlass >/dev/null 2>&1 || true
  unset PYTHONPATH
  unset PYTHONHOME
  export PYTHONNOUSERSITE=1
  if "${PYTHON_BIN}" -c 'import sglang, sgl_kernel' >/dev/null 2>&1; then
    sglang_file="$("${PYTHON_BIN}" -c 'import sglang, pathlib; print(pathlib.Path(sglang.__file__).resolve())')"
    case "${sglang_file}" in
      "${REPO_ROOT}"/*) ;;
      *)
        die "sglang is imported from ${sglang_file}, not ${REPO_ROOT}. Unset PYTHONPATH and re-run setup so 131 does not reuse 130's tree."
        ;;
    esac
    if ! "${PYTHON_BIN}" -c 'import sglang, aiter' >/tmp/sglang_import.err 2>&1; then
      if grep -q "nanobind" /tmp/sglang_import.err 2>/dev/null; then
        die "SGLang/AITER nanobind CUTLASS collision. Uninstall CUDA cutlass wheels and reinstall AMD-only aiter/sgl_kernel in this repo venv."
      fi
      die "import sglang, aiter failed. See /tmp/sglang_import.err"
    fi
    install_status_log_step sglang "already importable from this repo"
  elif [[ "${BENCHMARK_COMPILE_SGLANG}" == 1 ]]; then
    if [[ ! -d "${SGLANG_SOURCE_DIR}/.git" ]]; then
      git clone --filter=blob:none "${SGLANG_REPO_URL}" "${SGLANG_SOURCE_DIR}"
      git -C "${SGLANG_SOURCE_DIR}" checkout "${SGLANG_REPO_REF}"
    fi
    # Current sglang.git moved sgl-kernel to python/sglang/kernels/aot.
    SGL_KERNEL_SETUP=""
    if [[ -f "${SGLANG_SOURCE_DIR}/sgl-kernel/setup_rocm.py" ]]; then
      SGL_KERNEL_SETUP="${SGLANG_SOURCE_DIR}/sgl-kernel/setup_rocm.py"
    elif [[ -f "${SGLANG_SOURCE_DIR}/python/sglang/kernels/aot/setup_rocm.py" ]]; then
      SGL_KERNEL_SETUP="${SGLANG_SOURCE_DIR}/python/sglang/kernels/aot/setup_rocm.py"
    fi
    if [[ -n "${SGL_KERNEL_SETUP}" ]]; then
      (
        cd "$(dirname "${SGL_KERNEL_SETUP}")"
        export AMDGPU_TARGET="${GFX_TARGET}"
        export PYTORCH_ROCM_ARCH="${GFX_TARGET}"
        # The venv ships a rocm_sdk_core hipcc that does not add /opt/rocm/include
        # and has no amdgcn device library. Point torch at the system ROCm hipcc.
        export ROCM_HOME=/opt/rocm
        export ROCM_PATH=/opt/rocm
        export PATH="/opt/rocm/bin:${PATH}"
        export CPATH="/opt/rocm/include${CPATH:+:${CPATH}}"
        export CPLUS_INCLUDE_PATH="/opt/rocm/include${CPLUS_INCLUDE_PATH:+:${CPLUS_INCLUDE_PATH}}"
        export LIBRARY_PATH="/opt/rocm/lib:${LIBRARY_PATH:-}"
        export LD_LIBRARY_PATH="/opt/rocm/lib:${LD_LIBRARY_PATH:-}"
        # setup_rocm.py links with host g++, which does not accept Clang's
        # --gcc-install-dir. Keep HIPCC_COMPILE_FLAGS_APPEND for hipcc only.
        unset CXXFLAGS
        "${PYTHON_BIN}" setup_rocm.py install
      )
    else
      log_warn "sgl-kernel setup_rocm.py not in this SGLang tree; installing the HIP python package only"
    fi
    if [[ -f "${SGLANG_SOURCE_DIR}/python/pyproject_other.toml" ]]; then
      cp "${SGLANG_SOURCE_DIR}/python/pyproject_other.toml" \
        "${SGLANG_SOURCE_DIR}/python/pyproject.toml"
    fi
    # Current setup.py requires cargo unless Rust extensions are skipped.
    # all_hip extras (wave-lang, st_attn, petit_kernel) still lack cp314 wheels.
    export SGLANG_BUILD_RUST_EXTS="${SGLANG_BUILD_RUST_EXTS:-none}"
    "${PYTHON_BIN}" -m pip install -e "${SGLANG_SOURCE_DIR}/python[srt_empty]" ||
      "${PYTHON_BIN}" -m pip install -e "${SGLANG_SOURCE_DIR}/python"
    if ! "${PYTHON_BIN}" -c 'import sglang' >/dev/null 2>&1; then
      "${PYTHON_BIN}" -m pip install -e "${SGLANG_SOURCE_DIR}/python"
    fi
    # launch_server imports these; skip outlines (outlines_core needs cargo, no cp314 wheel).
    # jsonschema is required by serving_chat; --help can pass while launch_server import fails.
    "${PYTHON_BIN}" -m pip install "xgrammar==0.2.1" "timm==1.0.16" compressed-tensors \
      orjson pybase64 starlette pyzmq openai uvicorn fastapi dill \
      partial_json_parser sentencepiece msgspec requests setproctitle \
      packaging numpy pyyaml tqdm aiohttp ipython jsonschema \
      soundfile python-multipart ||
      log_warn "SGLang runtime extras install deferred"
    if [[ "${BENCHMARK_INSTALL_PYTORCH}" == 1 ]]; then
      "${PYTHON_BIN}" -m pip uninstall -y nvidia-cublas nvidia-cuda-runtime nvidia-cudnn-cu13 \
        nvidia-cufft nvidia-cufile nvidia-curand nvidia-cusolver nvidia-cusparse \
        nvidia-cusparselt-cu13 nvidia-nccl-cu13 nvidia-nvjitlink nvidia-nvshmem-cu13 \
        nvidia-nvtx nvidia-cuda-cupti nvidia-cuda-nvrtc cuda-toolkit cuda-bindings \
        cuda-pathfinder >/dev/null 2>&1 || true
      install_rocm_pytorch
    fi
    gpu_check "SGLang installation failed." "${PYTHON_BIN}" -c 'import sglang'
    gpu_check "sgl_kernel ROCm compile failed." "${PYTHON_BIN}" -c 'import sgl_kernel'
    if ! "${PYTHON_BIN}" -c 'import sglang, aiter' >/tmp/sglang_import.err 2>&1; then
      if grep -q "nanobind" /tmp/sglang_import.err 2>/dev/null; then
        die "SGLang/AITER nanobind CUTLASS collision. Uninstall CUDA cutlass wheels and reinstall AMD-only aiter/sgl_kernel in this repo venv."
      fi
      gpu_check_failed "import sglang, aiter failed. See /tmp/sglang_import.err"
    fi
    install_status_log_step sglang "installed and verified SGLang from the python subdirectory"
  else
    die "SGLang is not importable. ROCm 10.1.0 builds SGLang 0.5.18 from source against torch 2.13. Re-run setup with BENCHMARK_COMPILE_SGLANG=1 (the default for SGLang workloads). Smoke-only hosts may set BENCHMARK_INSTALL_SGLANG=0, but baseline/extended will fail."
  fi
  # Already-importable and compile paths both skip launch_server extras unless we
  # run them here. Missing pyzmq dies at import zmq. New transformers already
  # registered qwen3_asr, so SGLang AutoConfig.register raises ValueError.
  "${PYTHON_BIN}" -m pip install orjson pybase64 starlette pyzmq openai uvicorn fastapi \
    dill partial_json_parser sentencepiece uvloop gguf msgspec requests setproctitle \
    packaging numpy pyyaml tqdm aiohttp ipython jsonschema \
    soundfile python-multipart ||
    die "SGLang launch extras failed to install."
  "${PYTHON_BIN}" - <<'PY'
from pathlib import Path
import re
import sglang
root = Path(sglang.__file__).resolve().parent
patched = 0
pat = re.compile(r'AutoConfig\.register\(("qwen3_asr[^"]*")\s*,\s*([A-Za-z0-9_]+)\)')
for path in root.rglob("qwen3_asr.py"):
    text = path.read_text(encoding="utf-8")
    new = pat.sub(r"AutoConfig.register(\1, \2, exist_ok=True)", text)
    if new != text:
        path.write_text(new, encoding="utf-8")
        patched += 1
print(f"qwen3_asr exist_ok patches: {patched}")
PY
  "${PYTHON_BIN}" -c 'import zmq, orjson, starlette, pybase64, openai, dill, msgspec, jsonschema' ||
    die "SGLang launch extras are not importable (need zmq, orjson, starlette, pybase64, openai, dill, msgspec, jsonschema)."
  if [[ -f "${REPO_ROOT}/scripts/patch_aiter_gfx1250_optional.py" ]]; then
    "${PYTHON_BIN}" "${REPO_ROOT}/scripts/patch_aiter_gfx1250_optional.py" ||
      die "AITER gfx1250 optional-import patch failed."
  fi
  gpu_check "sglang.launch_server is not importable." \
    "${PYTHON_BIN}" -m sglang.launch_server --help >/dev/null
  gpu_check "sglang.srt.entrypoints.http_server.launch_server is not importable (install jsonschema)." \
    "${PYTHON_BIN}" -c 'from sglang.srt.entrypoints.http_server import launch_server'
fi

# Torch 2.11/2.12 on this host report device_count=0 after HIP init.
# Cache amdsmi handles so SGLang can see the MI300X (vLLM has its own copy).
if [[ "${BENCHMARK_INSTALL_SGLANG}" == 1 ]]; then
  install_rocm_bundled_amdsmi
  site_pkg="${VENV_ROOT}/lib/python${PYTHON_TARGET_VERSION}/site-packages"
  src_custom="${REPO_ROOT}/scripts/templates/vllm_rocm_sitecustomize.py"
  if [[ ! -f "${src_custom}" ]]; then
    die "Missing ${src_custom}; published clones must ship scripts/templates/vllm_rocm_sitecustomize.py."
  fi
  cp -a "${src_custom}" "${site_pkg}/vllm_rocm_bootstrap.py"
  printf '%s\n' 'import vllm_rocm_bootstrap' > "${site_pkg}/vllm_rocm_bootstrap.pth"
fi

if [[ "${BENCHMARK_INSTALL_PYTORCH}" == 1 && "${BENCHMARK_INSTALL_SGLANG}" == 1 ]]; then
  # Framework dependency resolution may replace ROCm torch with a CUDA wheel.
  # Restore and verify the operator-selected ROCm pair before completion.
  install_rocm_pytorch
fi

if [[ "${BENCHMARK_BUILD_FAISS_ROCM}" == 1 ]]; then
  # Official GPU path remains bash scripts/build_faiss_rocm.sh
  # (FAISS_ENABLE_GPU=ON, FAISS_ENABLE_ROCM=ON). Smoke is not gated on that
  # compile; faiss-cpu provides IndexFlatL2.
  if ! "${PYTHON_BIN}" -c 'import faiss' >/dev/null 2>&1; then
    log_warn "FAISS ROCm source compile deferred; installing faiss-cpu so smoke can IndexFlatL2."
    "${PYTHON_BIN}" -m pip install faiss-cpu || true
  fi
  "${PYTHON_BIN}" -c 'import faiss; print("FAISS", getattr(faiss, "__version__", "ok")); print("StandardGpuResources", hasattr(faiss, "StandardGpuResources"))' \
    || die "FAISS import verification failed."
  install_status_log_step faiss "installed and verified FAISS Python module"
  "${PYTHON_BIN}" -m pip install sentence-transformers llama-index-core datasets || log_warn "RAG extra Python packages deferred"
  if [[ "${BENCHMARK_INSTALL_PYTORCH}" == 1 ]]; then
    install_rocm_pytorch
  fi
fi

if [[ -f scripts/install_rag_amd.sh ]]; then
  # Overlay helper: real squad_v2 + BGE + Mistral prefetch. Do not install CUDA torch.
  bash scripts/install_rag_amd.sh
fi
if [[ -f scripts/install_rag_nvidia.sh ]]; then
  bash scripts/install_rag_nvidia.sh
fi

install_rocblas_client_smi_deps() {
  if [[ ! -f scripts/build.sh ]] || ! grep -q 'rocm_compile_rocblas_bench' scripts/build.sh; then
    return 0
  fi
  if [[ -f /usr/include/rocm_smi/rocm_smi.h ]]; then
    return 0
  fi
  # rocBLAS clients still search for include/rocm_smi/rocm_smi.h and librocm_smi64.
  # ROCm 10.1 ships libamd_smi.so instead. Ubuntu's SMI library package provides
  # the old names. The SONAME package is librocm-smi64-7 on 26.04 and
  # librocm-smi64-1 on 24.04. Do not install the rocm-smi CLI package: on 24.04
  # it replaces /opt/rocm/bin/rocm-smi.
  local package
  local -a packages=()
  for package in librocm-smi64-7 librocm-smi64-1 librocm-smi64; do
    if apt-cache show "${package}" >/dev/null 2>&1; then
      packages+=("${package}")
      break
    fi
  done
  if apt-cache show librocm-smi-dev >/dev/null 2>&1; then
    packages+=(librocm-smi-dev)
  fi
  if [[ "${#packages[@]}" -eq 0 ]]; then
    die "rocBLAS clients need librocm-smi64 and librocm-smi-dev, and neither package is available."
  fi
  run_privileged env DEBIAN_FRONTEND=noninteractive apt-get install -y "${packages[@]}"
  [[ -f /usr/include/rocm_smi/rocm_smi.h ]] ||
    die "rocBLAS clients still cannot find /usr/include/rocm_smi/rocm_smi.h."
}

if [[ "${GPU_CHECKS_AFTER_REBOOT}" == 1 ]]; then
  # Everything is installed. The rocBLAS clients name their GPU target
  # (GFX_TARGET), so that long compile runs now; the run after the reboot finds
  # it built. scripts/build.sh itself waits for the reboot: plain hipcc builds
  # pick the GPU architecture from the GPU they can see, and there is none yet.
  if [[ -f scripts/build.sh ]] && grep -q 'rocm_compile_rocblas_bench' scripts/build.sh; then
    install_rocblas_client_smi_deps
    (
      export ROCM_SOURCE_ROOT="${REPO_ROOT}/third_party"
      export ROCBLAS_SOURCE_DIR="${ROCM_SOURCE_ROOT}/rocBLAS"
      export PATH="/opt/rocm/bin:${PATH}"
      export LD_LIBRARY_PATH="/opt/rocm/lib:/opt/rocm/lib64:${LD_LIBRARY_PATH:-}"
      rocm_compile_rocblas_bench
    ) || die "rocBLAS clients build failed."
  fi
  install_status_log_phase "All software installed. Rebooting once to load the amdgpu driver; after the reboot setup builds the workload, checks the GPU, and reports SETUP complete"
  log_resume_event "Rebooting once now that everything is installed (postponed amdgpu reboot)"
  run_privileged reboot
  exit 0
fi

if [[ -f scripts/build.sh ]]; then
  install_rocblas_client_smi_deps
  bash scripts/build.sh
fi
# Mark setup complete before touching the resume service, so a signal during
# cleanup cannot leave a fully installed repo without .setup_state.
install_status_log_setup "complete"
touch .setup_state
if ! cleanup_resume_service; then
  log_warn "Setup completed, but resume-service cleanup was deferred; rerun setup.sh to retry cleanup."
fi
install_status_sync_motd
log_pass "setup.sh now complete"
