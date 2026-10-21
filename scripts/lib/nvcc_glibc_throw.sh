#!/usr/bin/env bash
# File: scripts/lib/nvcc_glibc_throw.sh
# Description: Decide from a real nvcc compile whether rsqrt headers need a
# repo-local fix. Never edits /usr/local/cuda. A quoted include of
# math_functions.h ignores -I, so a needed fix is applied with
# NVCC_PREPEND_FLAGS=--pre-include of a guarded repo-local copy.
# Call nvcc_glibc_prepare in the current shell. A process substitution
# cannot export the flags to nvcc or to FlashInfer.

nvcc_pin_toolkit() {
  local nvcc_bin
  if [[ -x /usr/local/cuda/bin/nvcc ]]; then
    nvcc_bin=/usr/local/cuda/bin/nvcc
  elif command -v nvcc >/dev/null 2>&1; then
    nvcc_bin="$(command -v nvcc)"
  else
    return 0
  fi
  CUDA_HOME="$(cd "$(dirname "${nvcc_bin}")/.." && pwd)"
  export CUDA_HOME
  case ":${PATH}:" in
    *":${CUDA_HOME}/bin:"*) ;;
    *) export PATH="${CUDA_HOME}/bin:${PATH}" ;;
  esac
}

nvcc_release_string() {
  nvcc --version 2>/dev/null | sed -n 's/.*release \([0-9][0-9]*\.[0-9][0-9.]*\).*/\1/p' | head -n 1
}

nvcc_math_header() {
  local root header
  root="${CUDA_HOME:-}"
  if [[ -z "${root}" ]]; then
    return 1
  fi
  for header in \
    "${root}/include/crt/math_functions.h" \
    "${root}/targets/x86_64-linux/include/crt/math_functions.h"
  do
    if [[ -f "${header}" ]]; then
      printf '%s\n' "${header}"
      return 0
    fi
  done
  return 1
}

nvcc_flashinfer_workspace() {
  local header sum
  nvcc_pin_toolkit
  sum="no-header"
  if header="$(nvcc_math_header)"; then
    sum="$(sha256sum "${header}" | awk '{print $1}')"
  fi
  FLASHINFER_WORKSPACE_BASE="${REPO_ROOT}/.cache/flashinfer/${sum}"
  export FLASHINFER_WORKSPACE_BASE
  mkdir -p "${FLASHINFER_WORKSPACE_BASE}/tmp"
  # nvcc writes cudafe intermediates under /tmp. A full overlay then kills the
  # SGLang server with "No space left on device" during FlashInfer JIT, so the
  # temp files go to the repo cache. SGLang also binds ZeroMQ IPC sockets under
  # TMPDIR, and a Unix socket path must stay under 107 bytes. The repo cache
  # path is far longer, so TMPDIR is a short /tmp symlink to it.
  local short_tmp
  short_tmp="/tmp/fi-$(printf '%s' "${REPO_ROOT}" | sha256sum | cut -c1-8)"
  ln -sfn "${FLASHINFER_WORKSPACE_BASE}/tmp" "${short_tmp}"
  export TMPDIR="${short_tmp}"
  export TMP="${TMPDIR}"
  export TEMP="${TMPDIR}"
}

nvcc_write_env() {
  local env_file release nvcc_path
  [[ -n "${REPO_ROOT:-}" ]] || return 0
  nvcc_flashinfer_workspace
  mkdir -p "${REPO_ROOT}/results"
  env_file="${REPO_ROOT}/results/nvcc_toolkit.env"
  release="$(nvcc_release_string)"
  nvcc_path="$(command -v nvcc || true)"
  {
    printf 'export CUDA_HOME=%q\n' "${CUDA_HOME:-}"
    printf 'export PATH=%q\n' "${PATH}"
    if [[ -n "${NVCC_PREPEND_FLAGS:-}" ]]; then
      printf 'export NVCC_PREPEND_FLAGS=%q\n' "${NVCC_PREPEND_FLAGS}"
    else
      printf 'unset NVCC_PREPEND_FLAGS\n'
    fi
    printf 'export FLASHINFER_WORKSPACE_BASE=%q\n' "${FLASHINFER_WORKSPACE_BASE}"
    if [[ -n "${TMPDIR:-}" ]]; then
      printf 'export TMPDIR=%q\n' "${TMPDIR}"
    fi
    printf 'nvcc_release=%q\n' "${release}"
    printf 'nvcc_path=%q\n' "${nvcc_path}"
    printf 'cuda_home=%q\n' "${CUDA_HOME:-}"
  } > "${env_file}"
}

nvcc_setup_state_lines() {
  local env_file="${REPO_ROOT}/results/nvcc_toolkit.env"
  [[ -f "${env_file}" ]] || return 0
  grep -E '^(nvcc_release|nvcc_path|cuda_home)=' "${env_file}" || true
}

load_nvcc_toolkit_env() {
  local env_file="${REPO_ROOT:-}/results/nvcc_toolkit.env"
  if [[ -f "${env_file}" ]]; then
    # shellcheck disable=SC1090
    source "${env_file}"
  fi
}

nvcc_header_probe() {
  local dir
  dir="${REPO_ROOT}/build/cuda-header-probe"
  mkdir -p "${dir}"
  cat > "${dir}/probe.cu" <<'CU'
#include <cuda_runtime.h>
#include <cmath>
__global__ void cuda_header_probe(double* out) { *out = rsqrt(2.0); }
CU
  # Keep the compiler's messages for nvcc_unsupported_host_compiler; still show them.
  if ! nvcc -std=c++17 -c -o "${dir}/probe.o" "${dir}/probe.cu" 2> "${dir}/probe.err"; then
    cat "${dir}/probe.err" >&2
    return 1
  fi
  cat "${dir}/probe.err" >&2
}

# nvcc refuses a host GCC newer than its toolkit supports (for example CUDA 12.0
# with Ubuntu 24.04's GCC 13). No header repair can fix that, so name it and stop.
nvcc_unsupported_host_compiler() {
  local err="${REPO_ROOT}/build/cuda-header-probe/probe.err"
  [[ -f "${err}" ]] && grep -q "unsupported GNU version" "${err}"
}

nvcc_write_local_fix() {
  local src_h src_hpp dest_root dest_h dest_hpp
  src_h="$(nvcc_math_header)" || return 1
  src_hpp="${src_h%.h}.hpp"
  dest_root="${REPO_ROOT}/build/cuda-header-fix"
  dest_h="${dest_root}/crt/math_functions.h"
  dest_hpp="${dest_root}/crt/math_functions.hpp"
  mkdir -p "${dest_root}/crt"
  python3 "${REPO_ROOT}/scripts/lib/nvcc_glibc_throw.py" patch "${src_h}" "${src_hpp}" "${dest_h}" "${dest_hpp}"
  NVCC_PREPEND_FLAGS="--pre-include ${dest_h}"
  if [[ -f "${dest_hpp}" ]]; then
    NVCC_PREPEND_FLAGS="${NVCC_PREPEND_FLAGS} --pre-include ${dest_hpp}"
  fi
  export NVCC_PREPEND_FLAGS
}

# Probe the toolkit nvcc will actually use. On success, export CUDA_HOME and
# leave NVCC_PREPEND_FLAGS unset. On failure, pre-include a repo-local repair
# and probe again. A second failure is fatal and does not write .setup_state
# because the caller exits before that write.
nvcc_glibc_prepare() {
  nvcc_pin_toolkit
  if ! command -v nvcc >/dev/null 2>&1; then
    return 0
  fi
  unset NVCC_PREPEND_FLAGS
  if nvcc_header_probe; then
    nvcc_write_env
    echo "[PASS] CUDA header probe compiled with $(command -v nvcc)" >&2
    return 0
  fi
  if nvcc_unsupported_host_compiler; then
    echo "[FAIL] $(command -v nvcc) (CUDA $(nvcc_release_string)) does not support the host compiler $(gcc -dumpfullversion 2>/dev/null || echo unknown): unsupported GNU version. The rsqrt header repair cannot fix this. Install the CUDA toolkit for this Ubuntu release from NVIDIA's CUDA repository (24.04: 12.8, 26.04: 13.3; scripts/lib/nvidia_cuda_toolkit.sh)." >&2
    return 1
  fi
  echo "[WARN] CUDA header probe failed. Writing a repo-local rsqrt repair. Not editing ${CUDA_HOME}." >&2
  nvcc_write_local_fix || return 1
  if nvcc_header_probe; then
    nvcc_write_env
    echo "[PASS] CUDA header probe compiled after NVCC_PREPEND_FLAGS pre-include" >&2
    return 0
  fi
  echo "[FAIL] CUDA header probe still fails after the repo-local rsqrt repair. Not editing ${CUDA_HOME}." >&2
  return 1
}

nvcc_refuse_if_toolkit_changed() {
  local recorded current state_file
  state_file="${REPO_ROOT}/.setup_state"
  [[ -f "${state_file}" ]] || return 0
  recorded="$(sed -n "s/^nvcc_release=//p" "${state_file}" | head -n 1 | tr -d "'\"")"
  [[ -n "${recorded}" ]] || return 0
  command -v nvcc >/dev/null 2>&1 || return 0
  current="$(nvcc_release_string)"
  if [[ -n "${current}" && "${current}" != "${recorded}" ]]; then
    echo "[FAIL] nvcc release changed from ${recorded} to ${current} since setup. Refusing to run." >&2
    return 1
  fi
  return 0
}

# Used on every benchmark entry, including when .setup_state already exists.
# A later workload must not inherit a toolkit header that no longer compiles.
nvcc_recheck_for_run() {
  nvcc_pin_toolkit
  nvcc_refuse_if_toolkit_changed || return 1
  nvcc_glibc_prepare
}

# Compatibility entry. Prints nothing. Must run in the current shell.
nvcc_glibc_throw_args() {
  nvcc_glibc_prepare
}

# Fill the NVCC_ARCH_FLAGS array with native SASS (plus PTX) for the installed
# GPU. Call it in the current shell before nvcc. Without -gencode, nvcc emits
# an old default arch plus PTX that the driver must JIT at launch. A driver
# older than the toolkit (CUDA 13.3 nvcc on Ubuntu 26.04 with an older driver)
# refuses that PTX: "the provided PTX was compiled with an unsupported
# toolchain". A program that does not check launch errors then reports zeros.
# BENCHMARK_CUDA_ARCH (for example 90) overrides detection.
nvcc_arch_flags() {
  local cap gpu_info
  NVCC_ARCH_FLAGS=()
  cap="${BENCHMARK_CUDA_ARCH:-}"
  if [[ -z "${cap}" ]]; then
    cap="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -n 1 | tr -d ' .' || true)"
  fi
  if [[ ! "${cap}" =~ ^[0-9]+$ ]]; then
    # nvidia-smi can fail on host-injected drivers; infer arch from the proc model.
    gpu_info="$(cat /proc/driver/nvidia/gpus/*/information 2>/dev/null || true)"
    case "${gpu_info}" in
      *B200*) cap=100 ;;   # also matches GB200
      *H100*|*H200*) cap=90 ;;   # *H200* also matches GH200
      *L40*|*Ada*) cap=89 ;;
      *A100*|*A800*) cap=80 ;;
      *) cap="" ;;
    esac
  fi
  if [[ "${cap}" =~ ^[0-9]+$ ]]; then
    # shellcheck disable=SC2034  # read by build.sh scripts that source this helper
    NVCC_ARCH_FLAGS=(-gencode "arch=compute_${cap},code=[sm_${cap},compute_${cap}]")
  else
    echo "[WARN] GPU compute capability not detected; nvcc uses its default arch and the driver must JIT PTX. Set BENCHMARK_CUDA_ARCH to override." >&2
  fi
}
