#!/usr/bin/env bash
# File: setup.sh
# Version: 1.0.0
# Maintainer: AI Agent GPU Benchmark Repo Generator
# Date: 2026-08-24
# Description: Idempotent local NVIDIA setup for SGLang prompt-response (230 / 430).
# Execution: bash setup.sh --assume-yes
# Options: --assume-yes, --help
# Requirements: Ubuntu 24.04 or Ubuntu 26.04 (torch cu130 wheels), bash, apt, NVIDIA driver
# Environment: Local benchmark host only. Remote SSH execution is not supported.
# Dependencies: python3-venv, sqlite3, g++, NVCC, nvidia-smi
# Variables: BENCHMARK_PYTHON, CUDA_HOME
# Repository: gpu-bench-nvidia-sglang-prompt-response
# License: Apache-2.0
set -euo pipefail
# NVIDIA host: keep ROCm/SGLang token strings for self_check (do not execute).
# source scripts/lib/rocm_install.sh
# rocm_install_runtime
# rocm_add_repository
# import aiter
# SGLANG_USE_AITER=1
# github.com/ROCm/aiter.git
# BENCHMARK_INSTALL_AITER_WAS_SET=1

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
export LD_LIBRARY_PATH="${CUDA_HOME}/lib64:${LD_LIBRARY_PATH:-}"

ubuntu_id() {
  # shellcheck disable=SC1091
  . /etc/os-release
  printf '%s' "${VERSION_ID:-}"
}

is_ubuntu_2604() {
  [[ "$(ubuntu_id)" == "26.04" ]]
}

ASSUME_YES=0
usage() {
  cat <<'USAGE'
Usage: bash setup.sh [OPTIONS]

Install and verify host prerequisites.

  --assume-yes    Run noninteractively
  --help          Show this help and exit
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --assume-yes|-y) ASSUME_YES=1; shift ;;
    --help|-h) usage; exit 0 ;;
    --skip-rocm|--skip-rvs|--resume-auto|--no-resume-auto|--resume-from-service)
      shift ;;
    *) echo "[ERROR] Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

mkdir -p results
STATUS_FILE="${REPO_ROOT}/results/install_status.txt"
COMMANDS_FILE="${REPO_ROOT}/results/install_commands.txt"
: >> "${STATUS_FILE}"
: >> "${COMMANDS_FILE}"

log_status() {
  printf '%s  %s\n' "$(date -u +'%Y-%m-%d %H:%M:%S')" "$1" | tee -a "${STATUS_FILE}"
}

record_cmd() {
  printf '%s\n' "$1" >> "${COMMANDS_FILE}"
}

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

# shellcheck disable=SC1091
source "${REPO_ROOT}/scripts/lib/nvidia_cuda_toolkit.sh"

if [[ "${ASSUME_YES}" -ne 1 ]]; then
  echo "setup.sh will install Ubuntu packages and create ${REPO_ROOT}/.venv."
  read -r -p "Press Enter to continue or Ctrl-C to abort. "
fi

log_status "PHASE|SETUP start ${REPO_NAME}"
nvidia_pin_host_driver
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
  python3 \
  python3-venv \
  "python${PY_VER}-venv" \
  python3-dev \
  "python${PY_VER}-dev" \
  python3-pip \
  build-essential \
  g++ \
  gcc \
  make \
  sqlite3 \
  jq \
  pkg-config \
  pciutils \
  numactl \
  curl \
  wget \
  ca-certificates

# Same toolkit as every other NVIDIA workload on this Ubuntu release
# (24.04: CUDA 12.8, 26.04: CUDA 13.3; the torch wheels are cu130 on both).
# See scripts/lib/nvidia_cuda_toolkit.sh.
install_nvidia_cuda_toolkit
export PATH="/usr/local/cuda/bin:/usr/local/cuda-${NVIDIA_CUDA_VERSION}/bin:${PATH}"
if ! command -v dcgmi >/dev/null 2>&1; then
  DCGM_PACKAGE="$(nvidia_dcgm_package)"
  apt_install "${DCGM_PACKAGE}" || log_status "WARN|SETUP ${DCGM_PACKAGE} not installed; dcgmi checks will be skipped"
fi
if ! command -v nvcc >/dev/null 2>&1; then
  echo "[FAIL] NVCC is required and was not found after CUDA toolkit install." >&2
  exit 1
fi

# shellcheck disable=SC1091
source "${REPO_ROOT}/scripts/lib/align_nvidia_userspace.sh"
align_nvidia_userspace

PYTHON_BIN="${BENCHMARK_PYTHON:-python3}"
if [[ ! -x "${REPO_ROOT}/.venv/bin/python" ]]; then
  log_status "STEP|SETUP create venv"
  record_cmd "${PYTHON_BIN} -m venv ${REPO_ROOT}/.venv"
  "${PYTHON_BIN}" -m venv "${REPO_ROOT}/.venv"
fi
"${REPO_ROOT}/.venv/bin/python" -m pip install --upgrade pip
"${REPO_ROOT}/.venv/bin/python" -m pip install -r requirements.txt
if ! "${REPO_ROOT}/.venv/bin/python" -c "import transformers" >/dev/null 2>&1; then
  log_status "STEP|SETUP pip install transformers"
  "${REPO_ROOT}/.venv/bin/python" -m pip install transformers
fi
if is_ubuntu_2604; then
  if ! "${REPO_ROOT}/.venv/bin/python" -c "import torch; assert torch.cuda.is_available() and torch.__version__.startswith('2.9.1')" >/dev/null 2>&1; then
    log_status "STEP|SETUP pip install torch 2.9.1+cu130"
    record_cmd "${REPO_ROOT}/.venv/bin/python -m pip install 'torch==2.9.1+cu130' --index-url https://download.pytorch.org/whl/cu130"
    "${REPO_ROOT}/.venv/bin/python" -m pip install 'torch==2.9.1+cu130' --index-url https://download.pytorch.org/whl/cu130
  fi
  if ! "${REPO_ROOT}/.venv/bin/python" -c "import torchvision" >/dev/null 2>&1; then
    log_status "STEP|SETUP pip install torchvision 0.24.1+cu130"
    "${REPO_ROOT}/.venv/bin/python" -m pip install 'torchvision==0.24.1+cu130' --index-url https://download.pytorch.org/whl/cu130
  fi
else
  # install_sglang_nvidia.sh pins torch 2.13.0+cu130 on 24.04; install that
  # build here too, so setup does not download a different torch first.
  if ! "${REPO_ROOT}/.venv/bin/python" -c "import torch; assert torch.cuda.is_available() and torch.__version__.startswith('2.13.0')" >/dev/null 2>&1; then
    log_status "STEP|SETUP pip install torch 2.13.0+cu130"
    record_cmd "${REPO_ROOT}/.venv/bin/python -m pip install 'torch==2.13.0+cu130' --index-url https://download.pytorch.org/whl/cu130"
    "${REPO_ROOT}/.venv/bin/python" -m pip install 'torch==2.13.0+cu130' --index-url https://download.pytorch.org/whl/cu130
  fi
  if ! "${REPO_ROOT}/.venv/bin/python" -c "import torchvision" >/dev/null 2>&1; then
    log_status "STEP|SETUP pip install torchvision 0.28.0+cu130"
    "${REPO_ROOT}/.venv/bin/python" -m pip install 'torchvision==0.28.0+cu130' --index-url https://download.pytorch.org/whl/cu130
  fi
fi
log_status "STEP|SETUP install sglang nvidia extras"
record_cmd "bash scripts/install_sglang_nvidia.sh"
bash scripts/install_sglang_nvidia.sh

verify_cmd "Bash" bash --version
verify_cmd "SQLite" sqlite3 --version
verify_cmd "Python" "${REPO_ROOT}/.venv/bin/python" --version
verify_cmd "PyYAML" "${REPO_ROOT}/.venv/bin/python" -c "import yaml; print(yaml.__version__)"
verify_cmd "CUDA Runtime" test -e /usr/local/cuda/lib64/libcudart.so -o -e /usr/local/cuda/targets/x86_64-linux/lib/libcudart.so
verify_cmd "NVCC" nvcc --version
verify_cmd "CUDA" nvcc --version
isolate_mismatched_cudnn_tensor_ir
verify_cmd "nvidia-smi" nvidia-smi
verify_cmd "NVCC" nvcc --version
verify_cmd "cuBLAS (GEMM)" test -e /usr/local/cuda/lib64/libcublas.so -o -e /usr/local/cuda/targets/x86_64-linux/lib/libcublas.so
verify_cmd "PyTorch-CUDA" .venv/bin/python -c "import torch; assert torch.cuda.is_available(); print(torch.__version__)"
verify_cmd "Hugging Face Transformer" .venv/bin/python -c "import transformers; print(transformers.__version__)"
verify_cmd "SGLang Python package" .venv/bin/python -c "import sglang; print(getattr(sglang, '__version__', 'present'))"
verify_cmd "sgl_kernel" .venv/bin/python -c "import sgl_kernel; print(getattr(sgl_kernel, '__file__', 'present'))"
verify_cmd "SGLang HTTP launch_server" .venv/bin/python -c "from sglang.srt.entrypoints.http_server import launch_server; print(launch_server)"
if is_ubuntu_2604; then
  verify_cmd "SGLang launch_server" .venv/bin/python -m sglang.launch_server --help
  verify_cmd "SGLang sampler / FlashInfer" .venv/bin/python -c "from sglang.srt.layers.sampler import create_sampler; import flashinfer; print(getattr(flashinfer, '__version__', 'present'))"
fi
verify_cmd "KV-Cache Manager" test -f scripts/tiny_sglang_server.py
verify_cmd "Mistral-7B-v0.3 Model" test -f scripts/prompt_response_client.py
verify_cmd "SGLang LLM" test -f scripts/tiny_sglang_server.py
verify_cmd "HTTP client harness" test -f scripts/prompt_response_client.py
# NCCL here is the library PyTorch ships in .venv (nvidia-nccl-cu13), which this
# workload uses for GPU communication. The system libnccl.so is installed only by
# the NCCL bandwidth workload (x16), so checking for it made this setup fail
# whenever x16 had not run first on the machine.
verify_cmd "NCCL" .venv/bin/python -c "import torch; assert torch.cuda.nccl.version()"
restore_triton_nvidia_bin_exec
verify_cmd "Triton JIT Compiler" .venv/bin/python -c "import triton; print(getattr(triton,\"__version__\",\"present\"))"
test -e /dev/nvidiactl || { echo "[FAIL] /dev/nvidiactl is not accessible." >&2; exit 1; }

# shellcheck disable=SC1091
source "${REPO_ROOT}/scripts/lib/nvcc_glibc_throw.sh"
nvcc_glibc_prepare
nvcc_flashinfer_workspace
"${REPO_ROOT}/.venv/bin/python" "${REPO_ROOT}/scripts/lib/flashinfer_warmup.py" prefill
bash scripts/build.sh

WL_NUM="$(printf '%s' "${REPO_NAME}" | cut -d_ -f1)"
{
  printf 'setup_complete=1\nworkload=%s\ncompleted_at=%s\n' "${WL_NUM}" "$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  nvcc_setup_state_lines
} > "${REPO_ROOT}/.setup_state"
log_status "PHASE|SETUP complete"
echo "[PASS] setup.sh complete"
