#!/usr/bin/env bash
# File: scripts/lib/keep_running_kernel.sh
# Description: Hold kernel metapackages that follow the newest archive kernel,
#              and stop setup when dpkg is already inconsistent.
# Execution: source scripts/lib/keep_running_kernel.sh; keep_running_kernel
# Requirements: apt-cache, apt-mark, dpkg. Root, or run_noninteractive_root.

[[ -n "${_KEEP_RUNNING_KERNEL_SH:-}" ]] && return 0
_KEEP_RUNNING_KERNEL_SH=1

_keep_running_kernel_run() {
  if declare -f run_noninteractive_root >/dev/null 2>&1; then
    run_noninteractive_root "$@"
  else
    "$@"
  fi
}

# Prints a failure and returns 1 when the modules directory contains any
# kernel other than uname -r. On Ubuntu 26.04 that extra directory is the
# only sign that apt installed a newer kernel: dpkg stays consistent, and
# the next reboot boots the new kernel. A missing modules directory is not
# a failure (self-check on a machine with no /lib/modules).
# KEEP_RUNNING_KERNEL_MODULES_DIR overrides /lib/modules for tests.
refuse_foreign_installed_kernel() {
  local running="" modules_dir="" extra="" base=""
  local -a extras=()
  modules_dir="${KEEP_RUNNING_KERNEL_MODULES_DIR:-/lib/modules}"
  [[ -d "${modules_dir}" ]] || return 0
  running="$(uname -r 2>/dev/null || true)"
  if [[ -z "${running}" ]]; then
    echo "[FAIL] uname -r is empty, so setup cannot confirm ${modules_dir} contains only the running kernel." >&2
    return 1
  fi
  for extra in "${modules_dir}"/*; do
    [[ -d "${extra}" ]] || continue
    base="$(basename "${extra}")"
    [[ "${base}" == "${running}" ]] && continue
    extras+=("${base}")
  done
  if ((${#extras[@]} > 0)); then
    echo "[FAIL] ${modules_dir} contains a kernel other than the running kernel ${running}: ${extras[*]}. The next reboot can boot that kernel. Setup does not remove kernels." >&2
    return 1
  fi
  return 0
}

# Holds each name only when the archive knows it. apt-cache show is inside
# an if, so an unknown name (for example a 24.04 HWE package on Ubuntu 26.04)
# returns non-zero and is skipped instead of aborting setup under set -e.
# A non-empty dpkg --audit means the next apt-get install will try to
# configure those packages and fail. Setup does not remove packages.
keep_running_kernel() {
  local running="" audit="" name failed=0
  local -a names=(
    linux-image-generic
    linux-image-virtual
    linux-headers-generic
    linux-headers-virtual
    linux-generic
    linux-virtual
    linux-tools-generic
    linux-generic-hwe-24.04
    linux-image-generic-hwe-24.04
    linux-headers-generic-hwe-24.04
    linux-virtual-hwe-24.04
    linux-image-virtual-hwe-24.04
    linux-headers-virtual-hwe-24.04
    linux-generic-hwe-26.04
    linux-image-generic-hwe-26.04
    linux-headers-generic-hwe-26.04
    linux-virtual-hwe-26.04
    linux-image-virtual-hwe-26.04
    linux-headers-virtual-hwe-26.04
  )
  running="$(uname -r 2>/dev/null || true)"
  if ! command -v apt-cache >/dev/null 2>&1; then
    echo "[FAIL] apt-cache is required before package installs." >&2
    return 1
  fi
  for name in "${names[@]}"; do
    if ! apt-cache show "${name}" >/dev/null 2>&1; then
      continue
    fi
    _keep_running_kernel_run apt-mark hold "${name}"
  done
  audit="$(_keep_running_kernel_run dpkg --audit 2>&1 || true)"
  if [[ -n "${audit//[[:space:]]/}" ]]; then
    echo "[FAIL] dpkg is not consistent. Every later apt-get install will fail until this is repaired:" >&2
    printf '%s\n' "${audit}" >&2
    if grep -Eiq 'linux-(image|headers)' <<<"${audit}"; then
      echo "[FAIL] Kernel package configuration is incomplete (running kernel: ${running:-unknown}). Setup does not remove kernels. Configure or remove any linux-image or linux-headers package that is not ${running:-the running kernel} before rerunning setup." >&2
    fi
    failed=1
  fi
  if ! refuse_foreign_installed_kernel; then
    failed=1
  fi
  return "${failed}"
}
