#!/usr/bin/env bash
# File: scripts/build.sh
# Description: Compile overlay src/nvhpl.cu with cuSOLVER into bin/nvhpl.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
export PATH="/usr/local/cuda/bin:/usr/local/cuda-13.3/bin:${PATH}"
command -v nvcc >/dev/null || { echo "[FAIL] nvcc missing" >&2; exit 1; }
# shellcheck disable=SC1091
source "${REPO_ROOT}/scripts/lib/nvcc_glibc_throw.sh"
nvcc_glibc_prepare
mkdir -p bin
echo "[RUN] nvcc -O2 -std=c++17 -o bin/nvhpl src/nvhpl.cu -lcusolver -lcublas"
nvcc -O2 -std=c++17 -o bin/nvhpl src/nvhpl.cu -lcusolver -lcublas
[[ -x bin/nvhpl ]] || { echo "[FAIL] bin/nvhpl missing" >&2; exit 1; }
echo "[PASS] build.sh compiled bin/nvhpl"
