#!/usr/bin/env bash
# File: scripts/lib/nvidia_cuda_toolkit.sh
# Description: One CUDA toolkit per Ubuntu release for every NVIDIA setup.sh
#              (scripts/templates/setup_nvidia_skeleton.sh and the vLLM/SGLang
#              overlays). Ubuntu 24.04 uses CUDA 12.8 and Ubuntu 26.04 uses
#              CUDA 13.3, both from NVIDIA's CUDA apt repository. Ubuntu's own
#              nvidia-cuda-toolkit is never installed: it pulls
#              libnvidia-compute-*, which collides with a host driver that is
#              bind-mounted into a container ("Invalid cross-device link") and
#              leaves dpkg half-configured for every later workload.
# Execution: source scripts/lib/nvidia_cuda_toolkit.sh; install_nvidia_cuda_toolkit
# Requirements: apt-get, apt-cache, dpkg, curl. Root. The caller defines
#              log_status and record_cmd.
# Test hooks: NVIDIA_OS_RELEASE_FILE, NVIDIA_ML_LIB, NVIDIA_APT_PIN_FILE,
#              NVIDIA_CUDA_PREFIX (default /usr/local).

[[ -n "${_NVIDIA_CUDA_TOOLKIT_SH:-}" ]] && return 0
_NVIDIA_CUDA_TOOLKIT_SH=1

NVIDIA_OS_RELEASE_FILE="${NVIDIA_OS_RELEASE_FILE:-/etc/os-release}"
NVIDIA_ML_LIB="${NVIDIA_ML_LIB:-/usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1}"
NVIDIA_APT_PIN_FILE="${NVIDIA_APT_PIN_FILE:-/etc/apt/preferences.d/benchmark-host-nvidia-driver}"
NVIDIA_CUDA_PREFIX="${NVIDIA_CUDA_PREFIX:-/usr/local}"

if ! declare -f log_status >/dev/null 2>&1; then
  log_status() { printf '%s  %s\n' "$(date -u +'%Y-%m-%d %H:%M:%S')" "$1"; }
fi
if ! declare -f record_cmd >/dev/null 2>&1; then
  record_cmd() { :; }
fi

nvidia_os_version_id() {
  (
    # shellcheck disable=SC1090
    . "${NVIDIA_OS_RELEASE_FILE}" 2>/dev/null && printf '%s' "${VERSION_ID:-}"
  )
}

# CUDA toolkit release for this Ubuntu release. One value per release, shared by
# every workload, so a later setup cannot move /usr/local/cuda under an earlier
# workload ("nvcc release changed from X to Y since setup").
nvidia_cuda_version() {
  case "$(nvidia_os_version_id)" in
    24.04*) printf '12.8\n' ;;
    26.04*) printf '13.3\n' ;;
    *) return 1 ;;
  esac
}

nvidia_cuda_repo_id() {
  case "$(nvidia_os_version_id)" in
    24.04*) printf 'ubuntu2404\n' ;;
    26.04*) printf 'ubuntu2604\n' ;;
    *) return 1 ;;
  esac
}

# DCGM 4 is published per CUDA major; datacenter-gpu-manager-4 itself is only a
# virtual package and apt cannot install it by that name.
nvidia_dcgm_package() {
  local ver
  ver="$(nvidia_cuda_version)" || return 1
  printf 'datacenter-gpu-manager-4-cuda%s\n' "${ver%%.*}"
}

# A non-empty dpkg --audit means packages were unpacked and never configured.
# Every later apt-get install on this host fails until it is repaired, so this is
# fatal even when the package that was being installed was optional.
nvidia_dpkg_consistent() {
  local what="$1" audit
  audit="$(dpkg --audit 2>&1 || true)"
  if [[ -n "${audit//[[:space:]]/}" ]]; then
    echo "[FAIL] dpkg is not consistent after ${what}. Setup stops here so later workloads do not inherit a broken package database:" >&2
    printf '%s\n' "${audit}" >&2
    return 1
  fi
  return 0
}

# True when the NVIDIA driver's NVML library belongs to a dpkg package (a driver
# installed from Ubuntu or NVIDIA packages). False when it exists but no package
# owns it: a container with the host driver bind-mounted, or a .run install.
nvidia_driver_is_dpkg_owned() {
  local real
  dpkg -S "${NVIDIA_ML_LIB}" >/dev/null 2>&1 && return 0
  real="$(readlink -f "${NVIDIA_ML_LIB}" 2>/dev/null || true)"
  [[ -n "${real}" ]] && dpkg -S "${real}" >/dev/null 2>&1
}

# Only when the driver is not package-managed: stop apt from installing Ubuntu's
# driver userspace over it. On a host whose driver came from packages, nothing is
# written, so that driver keeps receiving its normal updates.
nvidia_pin_host_driver() {
  if [[ ! -e "${NVIDIA_ML_LIB}" ]]; then
    return 0
  fi
  if nvidia_driver_is_dpkg_owned; then
    log_status "INFO NVIDIA driver is managed by dpkg; no apt pin written"
    return 0
  fi
  if [[ -f "${NVIDIA_APT_PIN_FILE}" ]]; then
    return 0
  fi
  record_cmd "write ${NVIDIA_APT_PIN_FILE} (Pin-Priority -1 for Ubuntu NVIDIA driver userspace packages)"
  mkdir -p "$(dirname "${NVIDIA_APT_PIN_FILE}")"
  cat > "${NVIDIA_APT_PIN_FILE}" <<'PIN'
# Written by a GPU benchmark setup.sh. This host's NVIDIA driver is not managed by
# dpkg (for example it is bind-mounted into a container). Installing these
# packages would try to replace the driver's files and leave dpkg half-configured.
# Delete this file to let apt install NVIDIA driver packages on this host again.
Package: nvidia-cuda-toolkit libnvidia-compute-* nvidia-driver-* nvidia-utils-*
Pin: version *
Pin-Priority: -1
PIN
  log_status "STEP|SETUP wrote ${NVIDIA_APT_PIN_FILE}: apt will not install Ubuntu NVIDIA driver packages over the host driver"
}

# Install (or confirm) the CUDA toolkit for this Ubuntu release and put its bin
# directory first on PATH. Exports NVIDIA_CUDA_VERSION. Returns non-zero with a
# [FAIL] line on any problem; the caller's set -e then stops setup.
install_nvidia_cuda_toolkit() {
  local ver repo pkg nvcc_bin keyring_url keyring_deb current
  if ! ver="$(nvidia_cuda_version)"; then
    echo "[FAIL] No CUDA toolkit is defined for Ubuntu $(nvidia_os_version_id). Supported: 24.04 (CUDA 12.8), 26.04 (CUDA 13.3)." >&2
    return 1
  fi
  repo="$(nvidia_cuda_repo_id)"
  pkg="cuda-toolkit-${ver/./-}"
  nvcc_bin="${NVIDIA_CUDA_PREFIX}/cuda-${ver}/bin/nvcc"
  NVIDIA_CUDA_VERSION="${ver}"
  export NVIDIA_CUDA_VERSION

  nvidia_pin_host_driver || return 1

  if [[ -x "${nvcc_bin}" ]] && "${nvcc_bin}" --version 2>/dev/null | grep -q "release ${ver}"; then
    log_status "STEP|SETUP already present: ${pkg}"
  else
    if ! apt-cache show "${pkg}" >/dev/null 2>&1; then
      keyring_url="https://developer.download.nvidia.com/compute/cuda/repos/${repo}/x86_64/cuda-keyring_1.1-1_all.deb"
      keyring_deb="/tmp/cuda-keyring_1.1-1_all.deb"
      log_status "STEP|SETUP add NVIDIA CUDA ${repo} repository"
      record_cmd "curl -fsSL ${keyring_url} -o ${keyring_deb}"
      if ! curl -fsSL "${keyring_url}" -o "${keyring_deb}"; then
        echo "[FAIL] Could not download ${keyring_url}." >&2
        return 1
      fi
      record_cmd "dpkg -i ${keyring_deb}"
      dpkg -i "${keyring_deb}" || return 1
      record_cmd "DEBIAN_FRONTEND=noninteractive apt-get update -y"
      DEBIAN_FRONTEND=noninteractive apt-get update -y || return 1
    fi
    if ! apt-cache show "${pkg}" >/dev/null 2>&1; then
      echo "[FAIL] ${pkg} is not available from apt, even with NVIDIA's ${repo} CUDA repository configured." >&2
      return 1
    fi
    log_status "STEP|SETUP apt-get install ${pkg}"
    record_cmd "DEBIAN_FRONTEND=noninteractive apt-get install -y ${pkg}"
    if ! DEBIAN_FRONTEND=noninteractive apt-get install -y "${pkg}"; then
      echo "[FAIL] apt-get install ${pkg} failed." >&2
      nvidia_dpkg_consistent "apt-get install ${pkg}" || true
      return 1
    fi
    nvidia_dpkg_consistent "apt-get install ${pkg}" || return 1
    if ! "${nvcc_bin}" --version 2>/dev/null | grep -q "release ${ver}"; then
      echo "[FAIL] ${pkg} installed, but ${nvcc_bin} does not report CUDA release ${ver}." >&2
      return 1
    fi
  fi

  # Builds and nvcc_glibc_throw.sh use /usr/local/cuda. Make it this release.
  if [[ -x "${NVIDIA_CUDA_PREFIX}/cuda/bin/nvcc" ]]; then
    current="$("${NVIDIA_CUDA_PREFIX}/cuda/bin/nvcc" --version 2>/dev/null | sed -n 's/.*release \([0-9][0-9]*\.[0-9][0-9]*\).*/\1/p' | head -n 1)"
    if [[ "${current}" != "${ver}" ]]; then
      log_status "STEP|SETUP point /usr/local/cuda at CUDA ${ver} (was ${current:-unknown})"
      record_cmd "update-alternatives --set cuda ${NVIDIA_CUDA_PREFIX}/cuda-${ver}"
      if ! update-alternatives --set cuda "${NVIDIA_CUDA_PREFIX}/cuda-${ver}"; then
        echo "[FAIL] /usr/local/cuda is CUDA ${current:-unknown}, not ${ver}, and update-alternatives could not change it." >&2
        return 1
      fi
    fi
  fi
  export PATH="${NVIDIA_CUDA_PREFIX}/cuda-${ver}/bin:${PATH}"
  return 0
}
