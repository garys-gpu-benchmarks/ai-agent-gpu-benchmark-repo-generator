#!/usr/bin/env bash
# File: scripts/build.sh
# Description: Compile overlay src/cublas_gemm.cu into bin/cublas_gemm.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
export PATH="/usr/local/cuda/bin:/usr/local/cuda-13.3/bin:${PATH}"
command -v nvcc >/dev/null || { echo "[FAIL] nvcc missing" >&2; exit 1; }
# shellcheck disable=SC1091
source "${REPO_ROOT}/scripts/lib/nvcc_glibc_throw.sh"
nvcc_glibc_prepare
mkdir -p bin
echo "[RUN] nvcc -O2 -std=c++17 -o bin/cublas_gemm src/cublas_gemm.cu -lcublas"
nvcc -O2 -std=c++17 -o bin/cublas_gemm src/cublas_gemm.cu -lcublas
[[ -x bin/cublas_gemm ]] || { echo "[FAIL] bin/cublas_gemm missing" >&2; exit 1; }
echo "[PASS] build.sh compiled bin/cublas_gemm"
