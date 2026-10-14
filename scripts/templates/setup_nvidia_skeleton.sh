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

apt_install() {
  local pkg
  for pkg in "$@"; do
    if dpkg -s "${pkg}" >/dev/null 2>&1; then
      log_status "STEP|SETUP already present: ${pkg}"
      continue
    fi
    log_status "STEP|SETUP apt-get install ${pkg}"
    record_cmd "DEBIAN_FRONTEND=noninteractive apt-get install -y ${pkg}"
    DEBIAN_FRONTEND=noninteractive apt-get install -y "${pkg}" || true
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

BENCHMARK_INSTALL_PYTORCH="${BENCHMARK_INSTALL_PYTORCH:-0}"
BENCHMARK_INSTALL_TORCHVISION="${BENCHMARK_INSTALL_TORCHVISION:-0}"
BENCHMARK_INSTALL_JAX="${BENCHMARK_INSTALL_JAX:-0}"
BENCHMARK_INSTALL_TRANSFORMERS="${BENCHMARK_INSTALL_TRANSFORMERS:-0}"
BENCHMARK_INSTALL_FIO="${BENCHMARK_INSTALL_FIO:-0}"
BENCHMARK_INSTALL_IPERF="${BENCHMARK_INSTALL_IPERF:-0}"
BENCHMARK_INSTALL_NCCL="${BENCHMARK_INSTALL_NCCL:-0}"
# shellcheck disable=SC1091
source "${REPO_ROOT}/scripts/lib/align_nvidia_userspace.sh"

if [[ "${ASSUME_YES}" -ne 1 ]]; then
  echo "setup.sh will install Ubuntu packages and create ${REPO_ROOT}/.venv."
  read -r -p "Press Enter to continue or Ctrl-C to abort. "
fi

log_status "PHASE|SETUP start ${REPO_NAME}"
# shellcheck disable=SC1091
source "${REPO_ROOT}/scripts/lib/keep_running_kernel.sh"
keep_running_kernel
record_cmd "DEBIAN_FRONTEND=noninteractive apt-get update -y"
DEBIAN_FRONTEND=noninteractive apt-get update -y

# Host interpreter: Ubuntu's /usr/bin/python3 unless BENCHMARK_PYTHON is set.
# An interactive root PATH can put an image's uv Python 3.11 first; Ubuntu
# publishes no python3.11-venv, so apt would fail on "python${PY_VER}-venv".
# Minimal images ship no Python. Install the distro interpreter before the version probe.
if ! command -v python3 >/dev/null 2>&1; then
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

# Ubuntu 26.04: every repo uses CUDA 13.3, the same toolkit the SGLang setups
# (430/431) install. If an earlier repo recorded 13.1 and a later setup installs
# 13.3, /usr/local/cuda moves and the earlier repo refuses to run
# ("nvcc release changed from 13.1 to 13.3 since setup").
NVIDIA_SKELETON_OS_ID=""
if [[ -r /etc/os-release ]]; then
  NVIDIA_SKELETON_OS_ID="$(. /etc/os-release && echo "${VERSION_ID:-}")"
fi
if [[ "${NVIDIA_SKELETON_OS_ID}" == 26.04* ]]; then
  if ! command -v nvcc >/dev/null 2>&1 || ! nvcc --version 2>/dev/null | grep -q "release 13.3"; then
    if [[ ! -f /usr/share/keyrings/cuda-archive-keyring.gpg ]]; then
      log_status "STEP|SETUP add NVIDIA CUDA Ubuntu 26.04 repository"
      curl -fsSL "https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2604/x86_64/cuda-keyring_1.1-1_all.deb" \
        -o /tmp/cuda-keyring_1.1-1_all.deb
      dpkg -i /tmp/cuda-keyring_1.1-1_all.deb
      record_cmd "DEBIAN_FRONTEND=noninteractive apt-get update -y"
      DEBIAN_FRONTEND=noninteractive apt-get update -y
    fi
    log_status "STEP|SETUP apt-get install cuda-toolkit-13-3"
    record_cmd "DEBIAN_FRONTEND=noninteractive apt-get install -y cuda-toolkit-13-3"
    DEBIAN_FRONTEND=noninteractive apt-get install -y cuda-toolkit-13-3
  fi
  export PATH="/usr/local/cuda-13.3/bin:${PATH}"
elif ! command -v nvcc >/dev/null 2>&1; then
  apt_install cuda-nvcc-12-8 cuda-cudart-dev-12-8 nvidia-cuda-toolkit || true
  apt_install cuda-nvcc-12-6 cuda-cudart-dev-12-6 || true
  apt_install cuda-nvcc-13-1 cuda-cudart-dev-13-1 nvidia-cuda-toolkit || true
fi
export PATH="/usr/local/cuda/bin:/usr/local/cuda-13.3/bin:/usr/local/cuda-12.8/bin:/usr/local/cuda-12.6/bin:${PATH}"
if ! command -v nvcc >/dev/null 2>&1; then
  echo "[FAIL] NVCC is required and was not found after CUDA toolkit install." >&2
  exit 1
fi
align_nvidia_userspace
if ! command -v dcgmi >/dev/null 2>&1; then
  apt_install datacenter-gpu-manager datacenter-gpu-manager-4 || true
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
  # linux-tools-generic follows the newest archive kernel. Install tools for
  # the running kernel only, and fail this perf workload if that package is absent.
  log_status "STEP|SETUP apt-get install linux-tools-$(uname -r)"
  record_cmd "DEBIAN_FRONTEND=noninteractive apt-get install -y linux-tools-common linux-tools-$(uname -r)"
  DEBIAN_FRONTEND=noninteractive apt-get install -y linux-tools-common "linux-tools-$(uname -r)"
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
  verify_cmd "perf" perf --version
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
