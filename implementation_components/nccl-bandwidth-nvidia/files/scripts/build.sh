#!/usr/bin/env bash
# File: scripts/build.sh
# Description: Compile overlay src/nccl_bw.cu and link libnccl.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
export PATH="/usr/local/cuda/bin:/usr/local/cuda-13.3/bin:${PATH}"
command -v nvcc >/dev/null || { echo "[FAIL] nvcc missing" >&2; exit 1; }
# shellcheck disable=SC1091
source "${REPO_ROOT}/scripts/lib/nvcc_glibc_throw.sh"
nvcc_glibc_prepare
NCCL_INC=""
for d in /usr/include /usr/local/cuda/include /usr/include/x86_64-linux-gnu; do
  if [[ -f "${d}/nccl.h" ]]; then NCCL_INC="-I${d}"; break; fi
done
if [[ -z "${NCCL_INC}" ]]; then
  echo "[FAIL] nccl.h not found; install libnccl-dev" >&2
  exit 1
fi
NCCL_LIB=""
for d in /usr/lib/x86_64-linux-gnu /usr/local/cuda/lib64 /usr/lib; do
  if [[ -e "${d}/libnccl.so" ]]; then NCCL_LIB="-L${d}"; break; fi
done
mkdir -p bin
echo "[RUN] nvcc -O2 -std=c++17 ${NCCL_INC} ${NCCL_LIB} -o bin/nccl_bw src/nccl_bw.cu -lnccl"
nvcc -O2 -std=c++17 ${NCCL_INC} ${NCCL_LIB} -o bin/nccl_bw src/nccl_bw.cu -lnccl
[[ -x bin/nccl_bw ]] || { echo "[FAIL] bin/nccl_bw missing" >&2; exit 1; }
echo "[PASS] build.sh compiled bin/nccl_bw"
