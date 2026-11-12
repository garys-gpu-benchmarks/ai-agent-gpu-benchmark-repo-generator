#!/usr/bin/env bash
# File: scripts/build.sh
# Description: Compile overlay src/ecc_walk.cu into bin/ecc_walk.
# nvcc_glibc_prepare compiles a header probe and, only if that fails,
# exports NVCC_PREPEND_FLAGS for a repo-local repair. It does not edit
# /usr/local/cuda and it does not pass -I.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
export PATH="/usr/local/cuda/bin:/usr/local/cuda-13.3/bin:${PATH}"
command -v nvcc >/dev/null || { echo "[FAIL] nvcc missing" >&2; exit 1; }
# shellcheck disable=SC1091
source "${REPO_ROOT}/scripts/lib/nvcc_glibc_throw.sh"
nvcc_glibc_prepare
# src/ecc_walk.cu launches its own kernels. Without native SASS a driver
# older than the toolkit rejects them and the walk reports zero failures.
nvcc_arch_flags
mkdir -p bin
echo "[RUN] nvcc -O2 -std=c++17 ${NVCC_ARCH_FLAGS[*]} -o bin/ecc_walk src/ecc_walk.cu"
nvcc -O2 -std=c++17 "${NVCC_ARCH_FLAGS[@]}" -o bin/ecc_walk src/ecc_walk.cu
[[ -x bin/ecc_walk ]] || { echo "[FAIL] bin/ecc_walk missing" >&2; exit 1; }
echo "[PASS] build.sh compiled bin/ecc_walk"
