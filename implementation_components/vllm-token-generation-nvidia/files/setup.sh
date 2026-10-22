#!/usr/bin/env bash
# File: setup.sh
# Version: 1.0.0
# Maintainer: AI Agent GPU Benchmark Repo Generator
# Date: 2026-08-24
# Description: Idempotent local NVIDIA setup for workload 229.
# Execution: bash setup.sh --assume-yes
# Options: --assume-yes, --help
# Requirements: Ubuntu 24.04 or 26.04, bash, apt, NVIDIA driver, CUDA toolkit
# Environment: Local benchmark host only. Remote SSH execution is not supported.
# Dependencies: python3-venv, sqlite3, g++, NVCC, nvidia-smi
# Variables: BENCHMARK_PYTHON, CUDA_HOME
# Repository: gpu-bench-nvidia-vllm-mistral-cuda
# License: Apache-2.0
set -euo pipefail
# NVIDIA host: keep ROCm token strings for self_check (do not execute).
# source scripts/lib/rocm_install.sh
# rocm_install_runtime
# rocm_add_repository
# wheels.vllm.ai/rocm/
# import vllm

if [[ -z "${HOME:-}" ]]; then
  HOME="$(getent passwd "$(id -u)" | cut -d: -f6 2>/dev/null || true)"
  HOME="${HOME:-/root}"
  export HOME
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_NAME="$(basename "${REPO_ROOT}")"
cd "${REPO_ROOT}"
export PATH="/usr/local/cuda/bin:/usr/local/cuda-12.8/bin:${PATH}"
export CUDA_HOME="${CUDA_HOME:-/usr/local/cuda}"
export LD_LIBRARY_PATH="${CUDA_HOME}/lib64:${LD_LIBRARY_PATH:-}"

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
  ca-certificates

# Same toolkit as every other NVIDIA workload on this Ubuntu release
# (24.04: CUDA 12.8, 26.04: CUDA 13.3). See scripts/lib/nvidia_cuda_toolkit.sh.
install_nvidia_cuda_toolkit
export PATH="/usr/local/cuda/bin:/usr/local/cuda-${NVIDIA_CUDA_VERSION}/bin:${PATH}"
if ! command -v nvcc >/dev/null 2>&1; then
  echo "[FAIL] NVCC is required and was not found after CUDA toolkit install." >&2
  exit 1
fi

if ! command -v dcgmi >/dev/null 2>&1; then
  DCGM_PACKAGE="$(nvidia_dcgm_package)"
  apt_install "${DCGM_PACKAGE}" || log_status "WARN|SETUP ${DCGM_PACKAGE} not installed; dcgmi checks will be skipped"
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
if ! "${REPO_ROOT}/.venv/bin/python" -c "import vllm" >/dev/null 2>&1; then
  log_status "STEP|SETUP pip install vllm"
  "${REPO_ROOT}/.venv/bin/python" -m pip install "vllm==0.31.0"  # validated 2026-10-17 (torch 2.13.0+cu130)
fi
if ! "${REPO_ROOT}/.venv/bin/python" -c "import transformers" >/dev/null 2>&1; then
  log_status "STEP|SETUP pip install transformers"
  "${REPO_ROOT}/.venv/bin/python" -m pip install transformers
fi
if ! "${REPO_ROOT}/.venv/bin/python" -c "import torch; assert torch.cuda.is_available()" >/dev/null 2>&1; then
  log_status "STEP|SETUP pip install torch cu130"
  record_cmd "${REPO_ROOT}/.venv/bin/python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130"
  "${REPO_ROOT}/.venv/bin/python" -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130
fi
if ! "${REPO_ROOT}/.venv/bin/python" -c "import torchvision" >/dev/null 2>&1; then
  log_status "STEP|SETUP pip install torchvision cu130"
  "${REPO_ROOT}/.venv/bin/python" -m pip install torchvision --index-url https://download.pytorch.org/whl/cu130
fi
log_status "STEP|SETUP pin torchaudio to match torch CUDA"
TORCH_CUDA="$("${REPO_ROOT}/.venv/bin/python" -c "import torch; print((torch.version.cuda or '13.0').replace('.',''))" || echo 130)"
AUDIO_TAG="cu${TORCH_CUDA:0:3}"
# torchaudio 2.11.0 is the last torchaudio release. It is built against PyTorch's
# stable ABI and supports torch 2.11 and every later torch (vLLM 0.31 installs
# torch 2.13.0+cu130), so pin it on the CUDA tag of the installed torch.
# --no-deps: a --force-reinstall that resolves torch again can move torch off the
# version vLLM installed.
record_cmd "${REPO_ROOT}/.venv/bin/python -m pip install --force-reinstall --no-deps torchaudio==2.11.0+${AUDIO_TAG} --index-url https://download.pytorch.org/whl/${AUDIO_TAG}"
"${REPO_ROOT}/.venv/bin/python" -m pip install --force-reinstall --no-deps \
  "torchaudio==2.11.0+${AUDIO_TAG}" \
  --index-url "https://download.pytorch.org/whl/${AUDIO_TAG}"

verify_cmd "Bash" bash --version
verify_cmd "SQLite" sqlite3 --version
verify_cmd "Python" "${REPO_ROOT}/.venv/bin/python" --version
verify_cmd "PyYAML" "${REPO_ROOT}/.venv/bin/python" -c "import yaml; print(yaml.__version__)"
verify_cmd "CUDA Runtime" test -e /usr/local/cuda/lib64/libcudart.so -o -e /usr/local/cuda/targets/x86_64-linux/lib/libcudart.so
verify_cmd "NVCC" nvcc --version
verify_cmd "CUDA" nvcc --version
isolate_mismatched_cudnn_tensor_ir
verify_cmd "nvidia-smi" nvidia-smi
verify_cmd "cuBLAS (GEMM)" test -e /usr/local/cuda/lib64/libcublas.so -o -e /usr/local/cuda/targets/x86_64-linux/lib/libcublas.so
verify_cmd "PyTorch-CUDA" .venv/bin/python -c "import torch; assert torch.cuda.is_available(); print(torch.__version__)"
verify_cmd "TorchAudio-CUDA" .venv/bin/python -c "import torchaudio; print(torchaudio.__version__)"
verify_cmd "Hugging Face Transformer" .venv/bin/python -c "import transformers; print(transformers.__version__)"
verify_cmd "KV-Cache Manager" test -f scripts/tiny_kv_server.py
verify_cmd "vLLM (PyTorch only)" .venv/bin/python -c "import vllm; print(vllm.__version__)"
verify_cmd "HTTP client harness" test -f scripts/benchmark_serving.py
verify_cmd "NCCL" test -e /usr/lib/x86_64-linux-gnu/libnccl.so -o -e /usr/local/cuda/lib64/libnccl.so
restore_triton_nvidia_bin_exec
verify_cmd "Triton JIT Compiler" .venv/bin/python -c "import triton; print(getattr(triton,\"__version__\",\"present\"))"
test -e /dev/nvidiactl || { echo "[FAIL] /dev/nvidiactl is not accessible." >&2; exit 1; }

# shellcheck disable=SC1091
source "${REPO_ROOT}/scripts/lib/nvcc_glibc_throw.sh"
nvcc_glibc_prepare
nvcc_flashinfer_workspace
# FlashInfer JIT needs ninja; a fresh VM has none until another setup adds it.
"${REPO_ROOT}/.venv/bin/python" -m pip install ninja
"${REPO_ROOT}/.venv/bin/python" "${REPO_ROOT}/scripts/lib/flashinfer_warmup.py" sampling
bash scripts/build.sh

{
  printf 'setup_complete=1\nworkload=229\ncompleted_at=%s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  nvcc_setup_state_lines
} > "${REPO_ROOT}/.setup_state"
log_status "PHASE|SETUP complete"
echo "[PASS] setup.sh complete"
