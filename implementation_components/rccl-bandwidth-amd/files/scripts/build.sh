#!/usr/bin/env bash
# File: scripts/build.sh
# Description: Compile the RCCL AllReduce probe bin/all_reduce_perf from src/rccl_perf.cpp.
# Execution: bash scripts/build.sh
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
# shellcheck disable=SC1091
source scripts/lib/hipcc_host_gcc.sh
mkdir -p bin
INCLUDES="-I/opt/rocm/include -I/opt/rocm/core-10.1/include"
LIBS="-L/opt/rocm/lib -L/opt/rocm/lib64 -lrccl"
hipcc -O2 src/rccl_perf.cpp ${INCLUDES} ${LIBS} -o bin/all_reduce_perf
chmod +x bin/all_reduce_perf
echo "[PASS] compiled bin/all_reduce_perf"
