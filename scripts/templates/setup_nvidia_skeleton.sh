#!/usr/bin/env bash
# File: scripts/templates/setup_nvidia_skeleton.sh
# Description: Canonical NVIDIA setup.sh. Installs CUDA host tools, parser deps,
# Framework-driven CUDA wheels, overlay helpers, then scripts/build.sh.
# Do not source scripts/lib/rocm_install.sh. Overlay setup.sh for vLLM/SGLang
# may replace this file; do not recopy this skeleton after overlays.
set -euo pipefail

if [[ -z "${HOME:-}" ]]; then
  HOME="$(getent passwd "$(id -u)" | cut -d: -f6 2>/dev/null || true)"
  HOME="${HOME:-/root}"
  export HOME
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_NAME="$(basename "${REPO_ROOT}")"
cd "${REPO_ROOT}"
export PATH="/usr/local/cuda/bin:/usr/local/cuda-13.3/bin:/usr/local/cuda-12.8/bin:/usr/local/cuda-12.6/bin:${PATH}"
export CUDA_HOME="${CUDA_HOME:-/usr/local/cuda}"
export LD_LIBRARY_PATH="${CUDA_HOME}/lib64:${CUDA_HOME}/targets/x86_64-linux/lib:${LD_LIBRARY_PATH:-}"

ASSUME_YES=0
usage() {
  cat <<'USAGE'
Usage: bash setup.sh [OPTIONS]

Install and verify NVIDIA host prerequisites.

  --assume-yes    Run noninteractively
  --help          Show this help and exit
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --assume-yes|-y) ASSUME_YES=1; shift ;;
    --help|-h) usage; exit 0 ;;
    --skip-rocm|--skip-rvs|--resume-auto|--no-resume-auto|--resume-from-service) shift ;;
    *) echo "[ERROR] Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

mkdir -p results src scripts bin
STATUS_FILE="${REPO_ROOT}/results/install_status.txt"
COMMANDS_FILE="${REPO_ROOT}/results/install_commands.txt"
: >> "${STATUS_FILE}"
: >> "${COMMANDS_FILE}"

log_status() { printf '%s  %s\n' "$(date -u +'%Y-%m-%d %H:%M:%S')" "$1" | tee -a "${STATUS_FILE}"; }
record_cmd() { printf '%s\n' "$1" >> "${COMMANDS_FILE}"; }

# Returns 1 when apt fails, so "apt_install a || apt_install b" can fall back and
# a bare call stops setup. An explicit return is needed: bash ignores set -e inside
# a function called on the left of ||. A dpkg database left inconsistent is fatal
# (exit, not return) even for an optional package, because every later apt-get
# install on this host would fail.
apt_install() {
  local pkg
  for pkg in "$@"; do
    if dpkg -s "${pkg}" >/dev/null 2>&1; then
      log_status "STEP|SETUP already present: ${pkg}"
      continue
    fi
    log_status "STEP|SETUP apt-get install ${pkg}"
    record_cmd "DEBIAN_FRONTEND=noninteractive apt-get install -y ${pkg}"
    if ! DEBIAN_FRONTEND=noninteractive apt-get install -y "${pkg}"; then
      nvidia_dpkg_consistent "apt-get install ${pkg}" || exit 1
      echo "[WARN] apt-get install ${pkg} failed." >&2
      return 1
    fi
    nvidia_dpkg_consistent "apt-get install ${pkg}" || exit 1
  done
}

verify_cmd() {
  local name="$1"
  shift
  if ! "$@"; then
    echo "[FAIL] Required framework item failed verification: ${name}" >&2
    exit 1
  fi
  log_status "PASS|SETUP verified ${name}"
}

# Same rule as the PMU collector: a kernel-matched file under /usr/lib/linux-tools,
# large enough to be the real binary. /usr/bin/perf is often a wrapper whose
# version text says "not found".
kernel_perf_bin() {
  local kernel="$1" candidate size
  for candidate in "/usr/lib/linux-tools/${kernel}/perf" "/usr/lib/linux-tools-${kernel}/perf"; do
    if [[ -f "${candidate}" ]]; then
      size="$(stat -L -c%s "${candidate}" 2>/dev/null || echo 0)"
      if [[ "${size}" -gt 10000 ]]; then
        printf '%s\n' "${candidate}"
        return 0
      fi
    fi
  done
  return 1
}

read_framework_text() {
  if [[ ! -f benchmark_specification.json ]]; then
    printf ''
    return 0
  fi
  "${BENCHMARK_PYTHON:-python3}" - <<'PY'
import json
from pathlib import Path
fields = {
    item.get("field_name", ""): str(item.get("value", ""))
    for item in json.loads(Path("benchmark_specification.json").read_text(encoding="utf-8"))
}
print(fields.get("Framework", ""))
PY
}

perf_is_optional() {
  grep -Eiq 'perf[[:space:]]*\(optional\)' <<< "$1"
}

# No kernel-matched perf: warn and continue. The PMU metrics are then published as
# the expected na "perf not installed", so the workload still runs and passes with
# empty counters. Typical cause: a container running the host's kernel (for example
# 6.8.0-136-generic) under an Ubuntu release whose archive has no linux-tools for it.
warn_missing_kernel_perf() {
  local kernel="$1" os_id common_pkg flavor_pkg
  os_id="$(. /etc/os-release && printf '%s' "${VERSION_ID:-unknown}")"
  common_pkg="linux-tools-${kernel%-*}"
  flavor_pkg="linux-tools-${kernel}"
  log_status "WARN kernel-matched perf is missing for kernel ${kernel} on Ubuntu ${os_id}; PMU metrics will be na"
  echo "[WARN] Kernel-matched perf is missing for kernel ${kernel} on Ubuntu ${os_id}; the PMU metrics will be na." >&2
  echo "[WARN] For counters, install ${common_pkg} and ${flavor_pkg} from the Ubuntu release that built kernel ${kernel} (do not add that release to this machine's apt sources), then rerun." >&2
}

BENCHMARK_INSTALL_PYTORCH="${BENCHMARK_INSTALL_PYTORCH:-0}"
BENCHMARK_INSTALL_TORCHVISION="${BENCHMARK_INSTALL_TORCHVISION:-0}"
BENCHMARK_INSTALL_JAX="${BENCHMARK_INSTALL_JAX:-0}"
BENCHMARK_INSTALL_TRANSFORMERS="${BENCHMARK_INSTALL_TRANSFORMERS:-0}"
BENCHMARK_INSTALL_FIO="${BENCHMARK_INSTALL_FIO:-0}"
BENCHMARK_INSTALL_IPERF="${BENCHMARK_INSTALL_IPERF:-0}"
BENCHMARK_INSTALL_NCCL="${BENCHMARK_INSTALL_NCCL:-0}"
# shellcheck disable=SC1091
source "${REPO_ROOT}/scripts/lib/align_nvidia_userspace.sh"
# shellcheck disable=SC1091
source "${REPO_ROOT}/scripts/lib/nvidia_cuda_toolkit.sh"

if [[ "${ASSUME_YES}" -ne 1 ]]; then
  echo "setup.sh will install Ubuntu packages and create ${REPO_ROOT}/.venv."
  read -r -p "Press Enter to continue or Ctrl-C to abort. "
fi

log_status "PHASE|SETUP start ${REPO_NAME}"
# shellcheck disable=SC1091
source "${REPO_ROOT}/scripts/lib/keep_running_kernel.sh"
keep_running_kernel
nvidia_pin_host_driver
record_cmd "DEBIAN_FRONTEND=noninteractive apt-get update -y"
DEBIAN_FRONTEND=noninteractive apt-get update -y

# Host interpreter: Ubuntu's /usr/bin/python3 unless BENCHMARK_PYTHON is set.
# An interactive root PATH can put an image's uv Python 3.11 first; Ubuntu
# publishes no python3.11-venv, so apt would fail on "python${PY_VER}-venv".
# Minimal images ship no Python. Install the distro interpreter before the version probe.
# Check for Ubuntu's own /usr/bin/python3, not any python3 on PATH: some cloud images
# activate a virtualenv (for example /root/.venv, Python 3.11) and ship no distro
# Python, so "command -v python3" succeeded and the version probe asked apt for
# python3.11-venv, which Ubuntu does not publish.
if [[ ! -x /usr/bin/python3 ]]; then
  log_status "STEP|SETUP apt-get install python3"
  record_cmd "DEBIAN_FRONTEND=noninteractive apt-get install -y python3"
  DEBIAN_FRONTEND=noninteractive apt-get install -y python3
fi
if [[ -z "${BENCHMARK_PYTHON:-}" && -x /usr/bin/python3 ]]; then
  export BENCHMARK_PYTHON=/usr/bin/python3
fi
PY_VER="$(${BENCHMARK_PYTHON:-python3} -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
apt_install \
  python3 python3-venv "python${PY_VER}-venv" python3-dev "python${PY_VER}-dev" python3-pip \
  build-essential g++ gcc make cmake sqlite3 jq pkg-config pciutils numactl libnuma-dev \
  curl ca-certificates ripgrep stress-ng lmbench
# cuDNN is selected after nvcc is on PATH. Ubuntu 26.04's only nvcc is CUDA
# 13.3, and scripts/build.sh then links the venv cu13 wheel. Installing
# libcudnn9-cuda-12 here made that build exit before compile.

# One CUDA toolkit per Ubuntu release, from NVIDIA's CUDA apt repository:
# 24.04 -> 12.8, 26.04 -> 13.3 (scripts/lib/nvidia_cuda_toolkit.sh). This skeleton
# and the vLLM/SGLang overlays call the same function, so a later workload cannot
# move /usr/local/cuda under an earlier one ("nvcc release changed ... since
# setup"). Ubuntu's nvidia-cuda-toolkit is never installed: it pulls
# libnvidia-compute-*, which collides with a bind-mounted host driver and leaves
# dpkg half-configured for every later workload.
install_nvidia_cuda_toolkit
export PATH="/usr/local/cuda/bin:/usr/local/cuda-${NVIDIA_CUDA_VERSION}/bin:${PATH}"
if ! command -v nvcc >/dev/null 2>&1; then
  echo "[FAIL] NVCC is required and was not found after CUDA toolkit install." >&2
  exit 1
fi
align_nvidia_userspace
if ! command -v dcgmi >/dev/null 2>&1; then
  DCGM_PACKAGE="$(nvidia_dcgm_package)"
  apt_install "${DCGM_PACKAGE}" || log_status "WARN|SETUP ${DCGM_PACKAGE} not installed; dcgmi checks will be skipped"
fi

PYTHON_BIN="${BENCHMARK_PYTHON:-python3}"
if [[ ! -x "${REPO_ROOT}/.venv/bin/python" ]]; then
  log_status "STEP|SETUP create venv"
  record_cmd "${PYTHON_BIN} -m venv ${REPO_ROOT}/.venv"
  "${PYTHON_BIN}" -m venv "${REPO_ROOT}/.venv"
fi
"${REPO_ROOT}/.venv/bin/python" -m pip install --upgrade pip
if [[ -f requirements.txt ]]; then
  "${REPO_ROOT}/.venv/bin/python" -m pip install -r requirements.txt
fi
"${REPO_ROOT}/.venv/bin/python" -m pip install PyYAML

if [[ -f benchmark_specification.json && -f "${REPO_ROOT}/scripts/framework_registry.py" ]]; then
  eval "$("${REPO_ROOT}/.venv/bin/python" "${REPO_ROOT}/scripts/framework_registry.py" --spec benchmark_specification.json --vendor nvidia --format env)"
fi
export BENCHMARK_INSTALL_PYTORCH BENCHMARK_INSTALL_TORCHVISION BENCHMARK_INSTALL_JAX BENCHMARK_INSTALL_TRANSFORMERS
export BENCHMARK_INSTALL_FIO BENCHMARK_INSTALL_IPERF BENCHMARK_INSTALL_NCCL
BENCHMARK_INSTALL_PERF="${BENCHMARK_INSTALL_PERF:-0}"

if [[ "${BENCHMARK_INSTALL_FIO}" == "1" ]]; then
  apt_install fio libaio-dev || apt_install fio
fi
if [[ "${BENCHMARK_INSTALL_IPERF}" == "1" ]]; then
  apt_install iperf3
fi
if [[ "${BENCHMARK_INSTALL_NCCL}" == "1" || -f src/nccl_bw.cu ]]; then
  apt_install libnccl2 libnccl-dev
fi
if [[ "${BENCHMARK_INSTALL_PERF}" == "1" ]]; then
  # linux-tools-generic follows the newest archive kernel and pulls its image
  # and headers. Install only the package named for the running kernel, when
  # this apt cache has it.
  KERNEL_RELEASE="$(uname -r)"
  PERF_PARANOID="$(cat /proc/sys/kernel/perf_event_paranoid 2>/dev/null || echo unknown)"
  log_status "INFO perf_event_paranoid=${PERF_PARANOID}"
  if apt-cache show "linux-tools-${KERNEL_RELEASE}" >/dev/null 2>&1; then
    log_status "STEP|SETUP apt-get install linux-tools-${KERNEL_RELEASE}"
    record_cmd "DEBIAN_FRONTEND=noninteractive apt-get install -y linux-tools-common linux-tools-${KERNEL_RELEASE}"
    DEBIAN_FRONTEND=noninteractive apt-get install -y linux-tools-common "linux-tools-${KERNEL_RELEASE}"
  fi
fi

if [[ "${BENCHMARK_INSTALL_PYTORCH}" == "1" || "${BENCHMARK_INSTALL_JAX}" == "1" ]]; then
  if [[ -f scripts/install_pytorch_nvidia.sh ]]; then
    log_status "STEP|SETUP install_pytorch_nvidia.sh"
    record_cmd "bash scripts/install_pytorch_nvidia.sh"
    bash scripts/install_pytorch_nvidia.sh
    "${REPO_ROOT}/.venv/bin/python" -m pip install numpy
  else
    echo "[FAIL] Framework requires CUDA PyTorch/JAX but scripts/install_pytorch_nvidia.sh is missing." >&2
    exit 1
  fi
fi
isolate_mismatched_cudnn_tensor_ir

for _helper in install_sglang_nvidia.sh install_rag_nvidia.sh install_sdxl_python.sh; do
  if [[ -f "scripts/${_helper}" ]]; then
    log_status "STEP|SETUP ${_helper}"
    record_cmd "bash scripts/${_helper}"
    bash "scripts/${_helper}"
  fi
done

verify_cmd "Bash" bash --version
verify_cmd "SQLite" sqlite3 --version
verify_cmd "Python" "${REPO_ROOT}/.venv/bin/python" --version
verify_cmd "PyYAML" "${REPO_ROOT}/.venv/bin/python" -c "import yaml; print(yaml.__version__)"
verify_cmd "CUDA Runtime" test -e /usr/local/cuda/lib64/libcudart.so -o -e /usr/local/cuda/targets/x86_64-linux/lib/libcudart.so -o -e /usr/lib/x86_64-linux-gnu/libcudart.so -o -e /usr/lib/x86_64-linux-gnu/libcudart.so.12
verify_cmd "NVCC" nvcc --version
test -e /dev/nvidiactl || { echo "[FAIL] /dev/nvidiactl is not accessible." >&2; exit 1; }
verify_cmd "nvidia-smi" nvidia-smi
if [[ "${BENCHMARK_INSTALL_FIO}" == "1" ]]; then
  verify_cmd "fio" fio --version
fi
if [[ "${BENCHMARK_INSTALL_IPERF}" == "1" ]]; then
  verify_cmd "iperf3" iperf3 --version
fi
if [[ "${BENCHMARK_INSTALL_PERF}" == "1" ]]; then
  KERNEL_RELEASE="$(uname -r)"
  PERF_BIN="$(kernel_perf_bin "${KERNEL_RELEASE}" || true)"
  PERF_VERSION=""
  if [[ -n "${PERF_BIN}" ]]; then
    PERF_VERSION="$("${PERF_BIN}" --version 2>&1 || true)"
  fi
  if [[ -z "${PERF_BIN}" ]] || grep -qi 'not found' <<< "${PERF_VERSION}"; then
    if perf_is_optional "$(read_framework_text)"; then
      log_status "WARN linux-tools-${KERNEL_RELEASE} is not a runnable kernel-matched perf; optional perf metrics stay na"
    else
      warn_missing_kernel_perf "${KERNEL_RELEASE}"
    fi
  else
    verify_cmd "perf" "${PERF_BIN}" --version
  fi
fi
if [[ "${BENCHMARK_INSTALL_NCCL}" == "1" || -f src/nccl_bw.cu ]]; then
  if [[ ! -f /usr/include/nccl.h && ! -f /usr/include/x86_64-linux-gnu/nccl.h ]]; then
    echo "[FAIL] libnccl-dev is required but nccl.h was not found." >&2
    exit 1
  fi
  log_status "PASS|SETUP verified NCCL headers"
fi
if command -v dcgmi >/dev/null 2>&1; then
  verify_cmd "NVIDIA DCGM Diagnostics" dcgmi --help
else
  log_status "WARN|SETUP dcgmi not installed; continuing with nvidia-smi stack checks"
fi
test -e /dev/nvidiactl || { echo "[FAIL] /dev/nvidiactl is not accessible." >&2; exit 1; }

if [[ -f scripts/lib/nvcc_glibc_throw.sh ]]; then
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/scripts/lib/nvcc_glibc_throw.sh"
  nvcc_glibc_prepare
fi
if [[ -f src/cudnn_conv.cu ]]; then
  # Same nvcc choice as scripts/build.sh. CUDA 12 links the system
  # libcudnn9-cuda-12 packages. CUDA 13 links the venv wheel and refuses
  # the CUDA 12 system library.
  build_nvcc=""
  if [[ -x /usr/local/cuda-12.8/bin/nvcc ]]; then
    build_nvcc=/usr/local/cuda-12.8/bin/nvcc
  elif [[ -x /usr/local/cuda-12.6/bin/nvcc ]]; then
    build_nvcc=/usr/local/cuda-12.6/bin/nvcc
  else
    build_nvcc="$(command -v nvcc || true)"
  fi
  nvcc_major="$(${build_nvcc} --version 2>/dev/null | sed -n 's/.*release \([0-9][0-9]*\)\..*/\1/p' | head -n 1)"
  if [[ "${nvcc_major}" == "13" ]]; then
    if ! compgen -G "${REPO_ROOT}/.venv/lib/python*/site-packages/nvidia/cudnn/lib/libcudnn.so.9" >/dev/null; then
      CUDNN_CU13_SPEC="${CUDNN_CU13_INSTALL_SPEC:-nvidia-cudnn-cu13==9.23.2.1}"
      log_status "STEP|SETUP pip install ${CUDNN_CU13_SPEC}"
      record_cmd "${REPO_ROOT}/.venv/bin/python -m pip install ${CUDNN_CU13_SPEC}"
      "${REPO_ROOT}/.venv/bin/python" -m pip install "${CUDNN_CU13_SPEC}"
    fi
  else
    apt_install libcudnn9-cuda-12 libcudnn9-headers-cuda-12 libcudnn9-dev-cuda-12
  fi
fi
if [[ -f scripts/build.sh ]]; then
  log_status "STEP|SETUP scripts/build.sh"
  bash scripts/build.sh
fi
wrap_cudnn_conv

if [[ -f src/cublas_gemm.cu && ! -x bin/cublas_gemm ]]; then
  echo "[FAIL] src/cublas_gemm.cu is present but bin/cublas_gemm was not built." >&2
  exit 1
fi
if [[ -f src/cudnn_conv.cu && ! -x bin/cudnn_conv ]]; then
  echo "[FAIL] src/cudnn_conv.cu is present but bin/cudnn_conv was not built." >&2
  exit 1
fi
if [[ -f src/stream.c && ! -x bin/stream && ! -x build/stream ]]; then
  echo "[FAIL] src/stream.c is present but the STREAM binary was not built." >&2
  exit 1
fi
if [[ -f src/numa_sweep.cpp && ! -x bin/numa_sweep ]]; then
  echo "[FAIL] src/numa_sweep.cpp is present but bin/numa_sweep was not built." >&2
  exit 1
fi
if [[ -f src/babelstream.cu && ! -x bin/babelstream ]]; then
  echo "[FAIL] src/babelstream.cu is present but bin/babelstream was not built." >&2
  exit 1
fi
if [[ -f src/ecc_walk.cu && ! -x bin/ecc_walk ]]; then
  echo "[FAIL] src/ecc_walk.cu is present but bin/ecc_walk was not built." >&2
  exit 1
fi
if [[ -f src/gups.c && ! -x bin/gups ]]; then
  echo "[FAIL] src/gups.c is present but bin/gups was not built." >&2
  exit 1
fi
if [[ -f src/cuda_memcpy.cu && ! -x bin/cuda_memcpy ]]; then
  echo "[FAIL] src/cuda_memcpy.cu is present but bin/cuda_memcpy was not built." >&2
  exit 1
fi
if [[ -f src/nccl_bw.cu && ! -x bin/nccl_bw ]]; then
  echo "[FAIL] src/nccl_bw.cu is present but bin/nccl_bw was not built." >&2
  exit 1
fi
if [[ -f src/nvhpl.cu && ! -x bin/nvhpl ]]; then
  echo "[FAIL] src/nvhpl.cu is present but bin/nvhpl was not built." >&2
  exit 1
fi
if [[ -f src/gpu_stress.cu && ! -x bin/gpu_stress ]]; then
  echo "[FAIL] src/gpu_stress.cu is present but bin/gpu_stress was not built." >&2
  exit 1
fi

if [[ -x "${REPO_ROOT}/.venv/bin/python" ]] && "${REPO_ROOT}/.venv/bin/python" -c "import flashinfer" >/dev/null 2>&1; then
  if "${REPO_ROOT}/.venv/bin/python" -c "import vllm" >/dev/null 2>&1; then
    log_status "STEP|SETUP FlashInfer sampling compile"
    "${REPO_ROOT}/.venv/bin/python" "${REPO_ROOT}/scripts/lib/flashinfer_warmup.py" sampling
  elif "${REPO_ROOT}/.venv/bin/python" -c "import sglang" >/dev/null 2>&1; then
    log_status "STEP|SETUP FlashInfer prefill compile"
    "${REPO_ROOT}/.venv/bin/python" "${REPO_ROOT}/scripts/lib/flashinfer_warmup.py" prefill
  fi
fi

if [[ -f scripts/probe_setup.sh ]]; then
  log_status "STEP|SETUP scripts/probe_setup.sh"
  bash scripts/probe_setup.sh
fi

{
  printf 'setup_complete=1\nworkload=%s\ncompleted_at=%s\n' "${REPO_NAME}" "$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  if declare -F nvcc_setup_state_lines >/dev/null 2>&1; then
    nvcc_setup_state_lines
  fi
} > "${REPO_ROOT}/.setup_state"
log_status "PHASE|SETUP complete"
echo "[PASS] setup.sh complete"
