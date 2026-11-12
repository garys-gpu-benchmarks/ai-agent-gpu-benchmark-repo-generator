#!/usr/bin/env bash
# File: scripts/build.sh
# Description: Compile overlay src/cudnn_conv.cu into bin/cudnn_conv.
# Uses the toolkit setup.sh installed (/usr/local/cuda, CUDA 13.3 on both
# Ubuntu releases), never a leftover CUDA 12 nvcc. CUDA 13 links this repo's
# venv cu13 cuDNN wheel. The wheel ships libcudnn.so.9 (no unversioned
# libcudnn.so) and its headers under nvidia/cudnn/include. Do not retarget
# memcpy, NCCL, HPL, or ECC.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
export PATH="/usr/local/cuda/bin:/usr/local/cuda-13.3/bin:${PATH}"
command -v nvcc >/dev/null || { echo "[FAIL] nvcc missing" >&2; exit 1; }
# shellcheck disable=SC1091
source "${REPO_ROOT}/scripts/lib/nvcc_glibc_throw.sh"
nvcc_glibc_prepare
nvcc_major="$(nvcc --version | sed -n 's/.*release \([0-9][0-9]*\)\..*/\1/p' | head -n 1)"
link_args=(-lcudnn)
if [[ "${nvcc_major}" == "13" ]]; then
  cudnn_root=""
  shopt -s nullglob
  for candidate in "${REPO_ROOT}/.venv"/lib/python*/site-packages/nvidia/cudnn; do
    if [[ -e "${candidate}/lib/libcudnn.so.9" && -f "${candidate}/include/cudnn.h" ]]; then
      cudnn_root="${candidate}"
    fi
  done
  shopt -u nullglob
  if [[ -z "${cudnn_root}" ]]; then
    echo "[FAIL] CUDA 13 nvcc requires the venv cu13 cuDNN (libcudnn.so.9 and cudnn.h). Refusing to link a CUDA 12 libcudnn." >&2
    exit 1
  fi
  # The linker resolves -lcudnn through the unversioned name only.
  ln -sfn libcudnn.so.9 "${cudnn_root}/lib/libcudnn.so"
  link_args=(-I"${cudnn_root}/include" -L"${cudnn_root}/lib" -Xlinker -rpath -Xlinker "${cudnn_root}/lib" -lcudnn)
fi
# src/cudnn_conv.cu launches its own fill kernels, so it needs native SASS.
nvcc_arch_flags
mkdir -p bin
echo "[RUN] nvcc -O2 -std=c++17 ${NVCC_ARCH_FLAGS[*]} -o bin/cudnn_conv src/cudnn_conv.cu ${link_args[*]}"
nvcc -O2 -std=c++17 "${NVCC_ARCH_FLAGS[@]}" -o bin/cudnn_conv src/cudnn_conv.cu "${link_args[@]}"
[[ -x bin/cudnn_conv ]] || { echo "[FAIL] bin/cudnn_conv missing" >&2; exit 1; }
echo "[PASS] build.sh compiled bin/cudnn_conv"
