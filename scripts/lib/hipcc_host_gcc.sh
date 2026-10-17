#!/usr/bin/env bash
# File: scripts/lib/hipcc_host_gcc.sh
# Version: 1.0.0
# Maintainer: AI Agent GPU Benchmark Repo Generator
# Date: 2026-08-28
# Description: Pin hipcc (Clang HIP wrappers) to a host GCC that still ships libstdc++ headers.
# Execution: source scripts/lib/hipcc_host_gcc.sh
# Options: none
# Requirements: bash 4+; optional GCC 13/14/15 install dir under /usr/lib/gcc
# Environment: Local ROCm host. Source from common.sh, setup.sh, or scripts/build.sh.
# Dependencies: none
# Variables: HIPCC_COMPILE_FLAGS_APPEND, HIPFLAGS, PATH, LD_LIBRARY_PATH
# Repository: gpu-bench/sys-bench template
# License: Apache-2.0
#
# Ubuntu 26.04 + ROCm 10.1.0 hipcc is Clang 24. A newer host GCC can fail to
# expose <cstdlib>/<cmath> to the HIP wrapper, so a bare
# `hipcc -O2 src/foo.cpp` dies with:
#   __clang_hip_runtime_wrapper.h:115:10: fatal error: 'cstdlib' file not found
# Pinning --gcc-install-dir to GCC 15 (or 14/13) restores those headers.
# Also prepend ROCm lib dirs so HIP binaries find libamdhip64.so.7 at runtime.

_hipcc_append_flag() {
  local varname="$1"
  local flag="$2"
  local current="${!varname:-}"
  case " ${current} " in
    *" ${flag} "*) ;;
    *)
      if [[ -n "${current}" ]]; then
        printf -v "${varname}" '%s %s' "${current}" "${flag}"
      else
        printf -v "${varname}" '%s' "${flag}"
      fi
      # shellcheck disable=SC2163  # varname holds the name of the variable to export
      export "${varname}"
      ;;
  esac
}

hipcc_pin_host_gcc() {
  if [[ -d /opt/rocm/bin ]]; then
    export PATH="/opt/rocm/bin:${PATH}"
  fi
  if [[ -d /opt/rocm/lib || -d /opt/rocm/lib64 ]]; then
    export LD_LIBRARY_PATH="/opt/rocm/lib:/opt/rocm/lib64${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
  fi

  local gcc_dir=""
  local cand
  for cand in \
    /usr/lib/gcc/x86_64-linux-gnu/15 \
    /usr/lib/gcc/x86_64-linux-gnu/14 \
    /usr/lib/gcc/x86_64-linux-gnu/13
  do
    if [[ -d "${cand}" ]]; then
      gcc_dir="${cand}"
      break
    fi
  done

  if [[ -z "${gcc_dir}" ]]; then
    return 0
  fi

  local flag="--gcc-install-dir=${gcc_dir}"
  # Clang/hipcc only. Do not put this on CXXFLAGS: host g++ (sgl-kernel
  # setup_rocm.py) rejects --gcc-install-dir and the ROCm SGLang compile dies.
  _hipcc_append_flag HIPCC_COMPILE_FLAGS_APPEND "${flag}"
  _hipcc_append_flag HIPFLAGS "${flag}"
}

if [[ "${BASH_SOURCE[0]:-}" != "${0:-}" ]]; then
  hipcc_pin_host_gcc
fi
