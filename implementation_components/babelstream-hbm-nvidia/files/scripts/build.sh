#!/usr/bin/env bash
# File: scripts/build.sh
# Description: Compile NVIDIA BabelStream CUDA source into bin/babelstream.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
export PATH="/usr/local/cuda/bin:/usr/local/cuda-13.3/bin:/usr/bin:${PATH}"
command -v nvcc >/dev/null || { echo "[FAIL] nvcc missing" >&2; exit 1; }
# shellcheck disable=SC1091
source "${REPO_ROOT}/scripts/lib/nvcc_glibc_throw.sh"
nvcc_glibc_prepare
mkdir -p bin
# Native SASS for the installed GPU (shared nvcc_arch_flags).
nvcc_arch_flags
echo "[RUN] nvcc -O2 -std=c++17 ${NVCC_ARCH_FLAGS[*]} -o bin/babelstream src/babelstream.cu"
nvcc -O2 -std=c++17 "${NVCC_ARCH_FLAGS[@]}" -o bin/babelstream src/babelstream.cu
[[ -x bin/babelstream ]] || { echo "[FAIL] bin/babelstream missing" >&2; exit 1; }
echo "[PASS] build.sh compiled bin/babelstream"
