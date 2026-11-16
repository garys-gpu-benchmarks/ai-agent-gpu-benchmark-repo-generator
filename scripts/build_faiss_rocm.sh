#!/usr/bin/env bash
# File: scripts/build_faiss_rocm.sh
# Version: 1.0.0
# Maintainer: AI Agent GPU Benchmark Repo Generator
# Date: 2026-07-16
# Description: Builds FAISS Python bindings with ROCm GPU-index support.
# Execution: bash scripts/build_faiss_rocm.sh
# Options: None; FAISS_SOURCE_DIR, FAISS_REPO_URL, GFX_TARGET, and FAISS_JOBS may be overridden.
# Requirements: Ubuntu, ROCm, CMake, Ninja, Git, OpenBLAS, SWIG, Python development headers.
# Environment: Local MI300X host with ROCm installed.
# Dependencies: /opt/rocm, .venv, scripts/lib/common.sh.
# Variables: FAISS_SOURCE_DIR, FAISS_REPO_URL, GFX_TARGET, FAISS_JOBS.
# Repository: gpu-bench/sys-bench template
# License: Apache-2.0

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"
source scripts/lib/common.sh
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
FAISS_SOURCE_DIR="${FAISS_SOURCE_DIR:-${REPO_ROOT}/third_party/faiss}"
FAISS_REPO_URL="${FAISS_REPO_URL:-https://github.com/facebookresearch/faiss.git}"
GFX_TARGET="${GFX_TARGET:-gfx942}"
export PATH="/opt/rocm/bin:${PATH}"

command -v cmake >/dev/null 2>&1 || die "cmake is required"
command -v git >/dev/null 2>&1 || die "git is required"
command -v swig >/dev/null 2>&1 || die "swig is required"
[[ -d /opt/rocm ]] || die "ROCm is required at /opt/rocm"
VENV_ROOT="${repo_root}/.venv"
[[ -x "${VENV_ROOT}/bin/python" ]] || die "${VENV_ROOT}/bin/python is required; run run_setup.sh first"

python_include="$("${VENV_ROOT}/bin/python" -c 'import sysconfig; print(sysconfig.get_path("include"))')"
numpy_include="$("${VENV_ROOT}/bin/python" -c 'import numpy; print(numpy.get_include())')"

if [[ ! -d "${FAISS_SOURCE_DIR}/.git" ]]; then
  git clone --depth 1 "${FAISS_REPO_URL}" "${FAISS_SOURCE_DIR}"
fi

cmake -S "${FAISS_SOURCE_DIR}" -B "${FAISS_SOURCE_DIR}/build" -G Ninja \
  -DFAISS_ENABLE_GPU=ON \
  -DFAISS_ENABLE_ROCM=ON \
  -DFAISS_ENABLE_PYTHON=ON \
  -DFAISS_ENABLE_RAFT=OFF \
  -DFAISS_ENABLE_TESTS=OFF \
  -DFAISS_ENABLE_PERF_TESTS=OFF \
  -DBLA_VENDOR=OpenBLAS \
  -DROCM_PATH=/opt/rocm \
  -DPython_EXECUTABLE="${VENV_ROOT}/bin/python" \
  -DPython_INCLUDE_DIR="${python_include}" \
  -DPython_NumPy_INCLUDE_DIR="${numpy_include}" \
  -DCMAKE_HIP_ARCHITECTURES="${GFX_TARGET}" \
  -DCMAKE_BUILD_TYPE=Release
cmake --build "${FAISS_SOURCE_DIR}/build" --target faiss -j "${FAISS_JOBS:-$(nproc)}"
cmake --build "${FAISS_SOURCE_DIR}/build" --target swigfaiss -j "${FAISS_JOBS:-$(nproc)}"
"${VENV_ROOT}/bin/python" -m pip install --no-deps "${FAISS_SOURCE_DIR}/build/faiss/python"
"${VENV_ROOT}/bin/python" - <<'PY'
import faiss
if not hasattr(faiss, "StandardGpuResources") or faiss.get_num_gpus() < 1:
    raise SystemExit("FAISS ROCm build does not expose a visible GPU index")
print(f"FAISS GPU resources:", faiss.get_num_gpus())
PY
echo "[PASS] FAISS ROCm GPU bindings are installed and visible."
