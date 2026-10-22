#!/usr/bin/env bash
# File: scripts/install_pytorch_nvidia.sh
# Description: Install CUDA PyTorch/torchvision/jax/transformers from the vendor wheel index.
# Do not put torch/jax in requirements.txt. Do not call this from the ROCm setup skeleton.
# Execution: bash scripts/install_pytorch_nvidia.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "[FAIL] ${PYTHON_BIN} is missing; create the venv before calling install_pytorch_nvidia.sh." >&2
  exit 1
fi
if [[ -f "${REPO_ROOT}/scripts/lib/disk_space.sh" ]]; then
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/scripts/lib/disk_space.sh"
  require_free_kib "${REPO_ROOT}" $((12 * 1024 * 1024)) \
    "PyTorch CUDA wheels need 12 GiB free before pip install."
fi

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
fi

BENCHMARK_INSTALL_TORCHVISION="${BENCHMARK_INSTALL_TORCHVISION:-0}"
BENCHMARK_INSTALL_JAX="${BENCHMARK_INSTALL_JAX:-0}"
BENCHMARK_INSTALL_TRANSFORMERS="${BENCHMARK_INSTALL_TRANSFORMERS:-0}"

case "${VERSION_ID:-}" in
  26.04*)
    TORCH_INDEX="${PYTORCH_CUDA_INDEX_URL:-https://download.pytorch.org/whl/cu130}"
    TORCH_SPEC="${PYTORCH_INSTALL_SPEC:-torch==2.13.0+cu130}"
    VISION_SPEC="${TORCHVISION_INSTALL_SPEC:-torchvision==0.28.0+cu130}"
    ;;
  *)
    # Ubuntu 24.04 uses the same torch as 26.04 (TEMPLATE_00_116). Driver 595
    # supports CUDA 13, and 24.04's vLLM/SGLang workloads already ran
    # torch 2.13.0+cu130, so every NVIDIA workload now runs one PyTorch build.
    TORCH_INDEX="${PYTORCH_CUDA_INDEX_URL:-https://download.pytorch.org/whl/cu130}"
    TORCH_SPEC="${PYTORCH_INSTALL_SPEC:-torch==2.13.0+cu130}"
    VISION_SPEC="${TORCHVISION_INSTALL_SPEC:-torchvision==0.28.0+cu130}"
    ;;
esac

echo "[INFO] pip install ${TORCH_SPEC} --index-url ${TORCH_INDEX}"
"${PYTHON_BIN}" -m pip install "${TORCH_SPEC}" --index-url "${TORCH_INDEX}"
echo "[INFO] pip install numpy"
"${PYTHON_BIN}" -m pip install numpy

if [[ "${BENCHMARK_INSTALL_TORCHVISION}" == "1" ]]; then
  echo "[INFO] pip install ${VISION_SPEC} --index-url ${TORCH_INDEX}"
  "${PYTHON_BIN}" -m pip install "${VISION_SPEC}" --index-url "${TORCH_INDEX}"
fi

# torch==2.13.0+cu130 depends on nvidia-cudnn-cu13==9.20.0.48, which does not
# ship libcudnn_engines_tensor_ir.so.9. Reinstalling 9.20.0.48 does not add it.
# Convolution components replace that pin with the complete 9.23.2.1 wheel.
# Only when this repo is a convolution component and torch.version.cuda is 13.
# This applies on Ubuntu 24.04 and 26.04 alike: both install torch 2.13.0+cu130.
if [[ -f scripts/probe_setup.sh || -f src/cudnn_conv.cu ]]; then
  cuda_major="$("${PYTHON_BIN}" - <<'PY'
import torch
cuda = getattr(torch.version, "cuda", None) or ""
print(cuda.split(".", 1)[0] if cuda else "")
PY
)"
  if [[ "${cuda_major}" == "13" ]]; then
    CUDNN_CU13_SPEC="${CUDNN_CU13_INSTALL_SPEC:-nvidia-cudnn-cu13==9.23.2.1}"
    echo "[INFO] pip install ${CUDNN_CU13_SPEC} (complete cu13 wheel; overrides the torch pin nvidia-cudnn-cu13==9.20.0.48)"
    "${PYTHON_BIN}" -m pip install "${CUDNN_CU13_SPEC}"
    "${PYTHON_BIN}" - <<'PY'
import sys
from pathlib import Path
found = list(Path(".venv").glob("lib/python*/site-packages/nvidia/cudnn/lib/libcudnn_engines_tensor_ir.so.9"))
if not found:
    raise SystemExit("[FAIL] nvidia-cudnn-cu13==9.23.2.1 did not install libcudnn_engines_tensor_ir.so.9")
print("[PASS] venv cuDNN ships libcudnn_engines_tensor_ir.so.9")
PY
  fi
fi

if [[ "${BENCHMARK_INSTALL_JAX}" == "1" ]]; then
  cuda_major="$("${PYTHON_BIN}" - <<'PY'
import torch
cuda = getattr(torch.version, "cuda", None) or ""
print(cuda.split(".", 1)[0] if cuda else "")
PY
)"
  if [[ "${cuda_major}" == "13" ]]; then
    JAX_SPEC="${JAX_INSTALL_SPEC:-jax[cuda13]}"
  else
    JAX_SPEC="${JAX_INSTALL_SPEC:-jax[cuda12]}"
  fi
  echo "[INFO] pip install ${JAX_SPEC}"
  if ! "${PYTHON_BIN}" -m pip install "${JAX_SPEC}"; then
    echo "[FAIL] pip rejected ${JAX_SPEC}. Not falling back to a different CUDA extra." >&2
    exit 1
  fi
fi

if [[ "${BENCHMARK_INSTALL_TRANSFORMERS}" == "1" ]]; then
  echo "[INFO] pip install transformers datasets"
  "${PYTHON_BIN}" -m pip install transformers datasets
fi

"${PYTHON_BIN}" - <<'PY'
import os
import sys
import torch
if getattr(torch.version, "cuda", None) in {None, ""}:
    raise SystemExit("[FAIL] NVIDIA setup installed a non-CUDA torch wheel.")
if not torch.cuda.is_available():
    raise SystemExit("[FAIL] torch.cuda.is_available() is False after NVIDIA PyTorch install.")
print(f"[PASS] torch {torch.__version__} cuda={torch.version.cuda} devices={torch.cuda.device_count()}")
if os.environ.get("BENCHMARK_INSTALL_JAX") == "1":
    import jax
    import jax.numpy as jnp

    @jax.jit
    def _probe(x):
        return x @ x

    y = _probe(jnp.ones((8, 8), dtype=jnp.float32))
    y.block_until_ready()
    print(f"[PASS] jax {jax.__version__} jit matmul devices={jax.devices()}")
if os.environ.get("BENCHMARK_INSTALL_TRANSFORMERS") == "1":
    import transformers
    print(f"[PASS] transformers {transformers.__version__}")
PY
