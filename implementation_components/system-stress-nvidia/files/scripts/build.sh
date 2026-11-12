#!/usr/bin/env bash
# File: scripts/build.sh
# Description: Compile overlay src/gpu_stress.cu into bin/gpu_stress (cuBLAS GEMM
# load for 203/403 system stress). Native SASS via nvcc_arch_flags so a driver
# older than the toolkit does not have to JIT PTX.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
export PATH="/usr/local/cuda/bin:/usr/local/cuda-13.3/bin:${PATH}"
command -v nvcc >/dev/null || { echo "[FAIL] nvcc missing" >&2; exit 1; }
# shellcheck disable=SC1091
source "${REPO_ROOT}/scripts/lib/nvcc_glibc_throw.sh"
nvcc_glibc_prepare
nvcc_arch_flags
mkdir -p bin
echo "[RUN] nvcc -O2 -std=c++17 ${NVCC_ARCH_FLAGS[*]} -o bin/gpu_stress src/gpu_stress.cu -lcublas"
nvcc -O2 -std=c++17 "${NVCC_ARCH_FLAGS[@]}" -o bin/gpu_stress src/gpu_stress.cu -lcublas
[[ -x bin/gpu_stress ]] || { echo "[FAIL] bin/gpu_stress missing" >&2; exit 1; }
echo "[PASS] build.sh compiled bin/gpu_stress"
