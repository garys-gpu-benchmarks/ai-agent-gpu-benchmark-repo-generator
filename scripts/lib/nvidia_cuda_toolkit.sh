#!/usr/bin/env bash
# File: scripts/lib/nvidia_cuda_toolkit.sh
# Description: One CUDA toolkit per Ubuntu release for every NVIDIA setup.sh
#              (scripts/templates/setup_nvidia_skeleton.sh and the vLLM/SGLang
#              overlays). Ubuntu 24.04 and Ubuntu 26.04 both use CUDA 13.3
#              (TEMPLATE_00_133; 24.04 was 12.8), from NVIDIA's CUDA apt repository. Ubuntu's own
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
# Ubuntu mirror fallback (TEMPLATE_00_135), used by nvidia_apt_update_once.
if [[ -f "$(dirname "${BASH_SOURCE[0]}")/apt_mirror_fallback.sh" ]]; then
  # shellcheck disable=SC1091
  source "$(dirname "${BASH_SOURCE[0]}")/apt_mirror_fallback.sh"
fi

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
    24.04*) printf '13.3\n' ;;
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

# One apt index refresh per host per BENCHMARK_APT_INDEX_MAX_AGE_SEC (default 6 h)
# (TEMPLATE_00_119). scripts/remote/host_bootstrap.sh and every NVIDIA setup.sh
# record the time in ${BENCHMARK_HOST_STATE_DIR}/apt_updated_epoch. A host with
# no stamp (any machine outside batch generation, or a first run) refreshes as
# before. install_nvidia_cuda_toolkit still refreshes after adding the CUDA repo.
nvidia_apt_update_once() {
  local state stamp max_age now last
  state="${BENCHMARK_HOST_STATE_DIR:-/var/lib/gpu-benchmark-host}"
  stamp="${state}/apt_updated_epoch"
  max_age="${BENCHMARK_APT_INDEX_MAX_AGE_SEC:-21600}"
  now="$(date +%s)"
  if [[ -r "${stamp}" ]]; then
    last="$(cat "${stamp}" 2>/dev/null || true)"
    if [[ "${last}" =~ ^[0-9]+$ ]] && (( now - last >= 0 && now - last < max_age )) \
      && compgen -G "/var/lib/apt/lists/*_Packages" >/dev/null 2>&1; then
      log_status "STEP|SETUP apt index refreshed $(( (now - last) / 60 )) min ago on this host; skipping apt-get update"
      return 0
    fi
  fi
  # A cloud image's Ubuntu mirror can be unreachable; this checks it with one
  # apt-get update and switches to archive.ubuntu.com if needed (0 = updated).
  if declare -f ensure_ubuntu_apt_mirror >/dev/null 2>&1 && ensure_ubuntu_apt_mirror; then
    return 0
  fi
  record_cmd "DEBIAN_FRONTEND=noninteractive apt-get update -y"
  DEBIAN_FRONTEND=noninteractive apt-get update -y || return 1
  { mkdir -p "${state}" && printf '%s\n' "${now}" > "${stamp}"; } 2>/dev/null || true
  return 0
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

# apt packages that make up the toolkit for CUDA release X.Y (TEMPLATE_00_119).
# The full cuda-toolkit-X-Y metapackage also pulls cuda-visual-tools (Nsight
# Systems, Nsight Compute, nvvp), cuda-documentation and cuda-demo-suite: about
# 4.7 GB at 13.3, and 15m48s of the first 26.04 setup on Nov 3. No workload uses
# them. These four keep nvcc, every CUDA library with headers (cuBLAS, cuSOLVER,
# cuFFT, cuRAND, cuSPARSE, NVRTC, cudart, CCCL), the command-line tools (CUPTI,
# NVTX, cuda-gdb, compute-sanitizer) and NVML headers. Prints one name per line.
nvidia_cuda_packages() {
  local tag="${1/./-}"
  printf '%s\n' "cuda-compiler-${tag}" "cuda-libraries-dev-${tag}" \
    "cuda-command-line-tools-${tag}" "cuda-nvml-dev-${tag}"
}

# True when apt knows every package named in the arguments.
nvidia_apt_has_all() {
  local p
  for p in "$@"; do
    apt-cache show "${p}" >/dev/null 2>&1 || return 1
  done
  return 0
}

# Install (or confirm) the CUDA toolkit for this Ubuntu release and put its bin
# directory first on PATH. Exports NVIDIA_CUDA_VERSION. Returns non-zero with a
# [FAIL] line on any problem; the caller's set -e then stops setup.
install_nvidia_cuda_toolkit() {
  local ver repo pkg nvcc_bin keyring_url keyring_deb current
  local -a pkgs
  if ! ver="$(nvidia_cuda_version)"; then
    echo "[FAIL] No CUDA toolkit is defined for Ubuntu $(nvidia_os_version_id). Supported: 24.04 (CUDA 13.3), 26.04 (CUDA 13.3)." >&2
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
    mapfile -t pkgs < <(nvidia_cuda_packages "${ver}")
    if ! nvidia_apt_has_all "${pkgs[@]}" && ! apt-cache show "${pkg}" >/dev/null 2>&1; then
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
    if ! nvidia_apt_has_all "${pkgs[@]}"; then
      if ! apt-cache show "${pkg}" >/dev/null 2>&1; then
        echo "[FAIL] ${pkg} is not available from apt, even with NVIDIA's ${repo} CUDA repository configured." >&2
        return 1
      fi
      log_status "WARN NVIDIA's ${repo} repository is missing one of ${pkgs[*]}; installing the full ${pkg}"
      pkgs=("${pkg}")
    fi
    # --force-unsafe-io: dpkg skips its fsync after every unpacked file, which is
    # most of the unpack time on a container's overlay filesystem. A crash in the
    # middle can leave files unsynced; nvidia_dpkg_consistent and the nvcc check
    # below still catch an incomplete install.
    log_status "STEP|SETUP apt-get install ${pkgs[*]}"
    record_cmd "DEBIAN_FRONTEND=noninteractive apt-get install -y -o Dpkg::Options::=--force-unsafe-io ${pkgs[*]}"
    if ! DEBIAN_FRONTEND=noninteractive apt-get install -y -o Dpkg::Options::=--force-unsafe-io "${pkgs[@]}"; then
      echo "[FAIL] apt-get install ${pkgs[*]} failed." >&2
      nvidia_dpkg_consistent "apt-get install ${pkgs[*]}" || true
      return 1
    fi
    nvidia_dpkg_consistent "apt-get install ${pkgs[*]}" || return 1
    if ! "${nvcc_bin}" --version 2>/dev/null | grep -q "release ${ver}"; then
      echo "[FAIL] ${pkgs[*]} installed, but ${nvcc_bin} does not report CUDA release ${ver}." >&2
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
  nvidia_cuda_login_path || true
  return 0
}

# Login shells find nvcc (TEMPLATE_00_135). Setup put CUDA in /usr/local/cuda but
# not on root's PATH, so "nvcc --version" after ssh said "command not found" even
# though every workload adds /usr/local/cuda/bin itself. Writes
# /etc/profile.d/cuda-benchmark.sh once; it takes effect at the next login.
# NVIDIA_PROFILE_D_FILE overrides the path (tests); with a test NVIDIA_CUDA_PREFIX
# and no override nothing is written.
nvidia_cuda_login_path() {
  local file="${NVIDIA_PROFILE_D_FILE:-}"
  if [[ -z "${file}" ]]; then
    [[ "${NVIDIA_CUDA_PREFIX}" == "/usr/local" ]] || return 0
    file="/etc/profile.d/cuda-benchmark.sh"
  fi
  local body
  body="$(printf '%s\n' \
    "# Written by GPU benchmark setup (scripts/lib/nvidia_cuda_toolkit.sh): put the" \
    "# CUDA toolkit that setup installed on login shells' PATH." \
    "case \":\${PATH}:\" in *:${NVIDIA_CUDA_PREFIX}/cuda/bin:*) ;; *) export PATH=\"${NVIDIA_CUDA_PREFIX}/cuda/bin:\${PATH}\" ;; esac")"
  [[ -f "${file}" && "$(cat "${file}" 2>/dev/null)" == "${body}" ]] && return 0
  [[ -w "$(dirname "${file}")" ]] || return 0
  printf '%s\n' "${body}" > "${file}" || return 0
  log_status "STEP|SETUP ${file}: ${NVIDIA_CUDA_PREFIX}/cuda/bin on login PATH (next login)"
  return 0
}
