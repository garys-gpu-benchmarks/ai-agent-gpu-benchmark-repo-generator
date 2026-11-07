#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${1:-$PWD}"
PYTHON="${REPO_ROOT}/.venv/bin/python"

# GPU Vendor and Execution Domain from the workload's specification decide which
# GPU stack lines are printed and what a missing stack means:
#   CPU / System workload: the GPU stack is not used, so "not installed" is normal.
#   GPU workload: setup installs the stack, so a missing one is a real problem.
spec_field() {
  local name="$1" py
  for py in "${PYTHON}" python3; do
    if command -v "${py}" >/dev/null 2>&1 || [[ -x "${py}" ]]; then
      "${py}" - "${REPO_ROOT}/benchmark_specification.json" "${name}" <<'PY' 2>/dev/null && return 0
import json, sys
try:
    items = json.load(open(sys.argv[1], encoding="utf-8"))
except (OSError, ValueError):
    sys.exit(1)
print(next((str(i.get("value", "")) for i in items if i.get("field_name") == sys.argv[2]), ""))
PY
    fi
  done
  printf ''
}

gpu_vendor="$(spec_field "GPU Vendor" | tr '[:lower:]' '[:upper:]')"
execution_domain="$(spec_field "Execution Domain")"
if [[ "${execution_domain}" == CPU* ]]; then
  missing_text="not installed (not used by this CPU benchmark)"
else
  missing_text="NOT FOUND (GPU setup did not install it)"
fi

value_or_not_found() {
  local value="${1:-}"
  [[ -n "${value}" ]] && printf '%s\n' "${value}" || printf '%s\n' "NOT FOUND"
}
stack_value() {
  local value="${1:-}"
  [[ -n "${value}" ]] && printf '%s\n' "${value}" || printf '%s\n' "${missing_text}"
}

# Version of the first installed package among the names or dpkg patterns given.
first_package_version() {
  local pattern version
  for pattern in "$@"; do
    version="$(dpkg-query -W -f='${db:Status-Abbrev} ${Version}\n' "${pattern}" 2>/dev/null |
      awk '$1 ~ /^ii/ && $2 != "" {print $2; exit}' || true)"
    if [[ -n "${version}" ]]; then
      printf '%s' "${version}"
      return 0
    fi
  done
  return 0
}

# ROCm 10.x (TheRock) installs amdrocm-* packages under /opt/rocm/core-<ver>,
# not the older rocm-core package, so read the install itself first.
rocm_install_version() {
  local file dir version
  for file in /opt/rocm/.info/version /opt/rocm/core-*/.info/version /opt/rocm-*/.info/version; do
    if [[ -r "${file}" ]]; then
      version="$(head -n 1 "${file}" | tr -d '[:space:]')"
      [[ -n "${version}" ]] && { printf '%s' "${version}"; return 0; }
    fi
  done
  version="$(first_package_version rocm-core 'amdrocm-base*' 'amdrocm10.*' 'amdrocm-core*' amdrocm)"
  [[ -n "${version}" ]] && { printf '%s' "${version}"; return 0; }
  for dir in /opt/rocm/core-* /opt/rocm-[0-9]*; do
    if [[ -d "${dir}" ]]; then
      basename "${dir}" | sed -E 's/^(core-|rocm-)//'
      return 0
    fi
  done
  return 0
}

# rocBLAS version, most specific first: the pre-10.x rocblas package; the
# installed library's own version suffix (librocblas.so.<major>.<minor>...);
# else the ROCm 10.x package, named, because its version is the ROCm release
# (amdrocm-blas10.1 10.1.0-3), not the rocBLAS version.
rocblas_install_version() {
  local version lib line
  version="$(first_package_version rocblas)"
  [[ -n "${version}" ]] && { printf '%s' "${version}"; return 0; }
  for lib in /opt/rocm/lib/librocblas.so.*.* /opt/rocm/lib64/librocblas.so.*.* \
             /opt/rocm/core-*/lib/librocblas.so.*.* /opt/rocm/core-*/lib64/librocblas.so.*.*; do
    if [[ -e "${lib}" ]]; then
      basename "${lib}" | sed -E 's/^librocblas\.so\.//'
      return 0
    fi
  done
  lib="$(find /opt/rocm/ -maxdepth 5 -name 'librocblas.so.*.*' -print -quit 2>/dev/null || true)"
  if [[ -n "${lib}" ]]; then
    basename "${lib}" | sed -E 's/^librocblas\.so\.//'
    return 0
  fi
  line="$(dpkg-query -W -f='${db:Status-Abbrev} ${Package} ${Version}\n' 'amdrocm-blas[0-9]*' 2>/dev/null |
    awk '$1 ~ /^ii/ && $3 != "" {print $2 " " $3; exit}' || true)"
  [[ -n "${line}" ]] && printf '%s' "${line}"
  return 0
}

ubuntu_version="$(
  . /etc/os-release 2>/dev/null
  printf '%s' "${PRETTY_NAME:-}"
)"
python_version="NOT FOUND"
if [[ -x "${PYTHON}" ]]; then
  python_version="$("${PYTHON}" --version 2>&1 || true)"
fi
[[ -n "${python_version}" ]] || python_version="NOT FOUND"

system_family="$(
  dmidecode -t system 2>/dev/null |
    awk -F: '/^[[:space:]]*Family:/{gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); print $2; exit}' || true
)"

printf '[INFO] %-31s %s\n' "Repository:" "${REPO_ROOT}"
printf '[INFO] %-31s %s\n' "Ubuntu Version:" "$(value_or_not_found "${ubuntu_version}")"
printf '[INFO] %-31s %s\n' "Python Version:" "${python_version}"
if [[ "${gpu_vendor}" == "NVIDIA" ]]; then
  cuda_version=""
  for nvcc in /usr/local/cuda/bin/nvcc nvcc; do
    if command -v "${nvcc}" >/dev/null 2>&1; then
      cuda_version="$("${nvcc}" --version 2>/dev/null | sed -n 's/.*release \([0-9.]*\).*/\1/p' | head -n 1)"
      [[ -n "${cuda_version}" ]] && break
    fi
  done
  driver_version="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -n 1 || true)"
  printf '[INFO] %-31s %s\n' "CUDA Version:" "$(stack_value "${cuda_version}")"
  printf '[INFO] %-31s %s\n' "NVIDIA Driver Version:" "$(stack_value "${driver_version}")"
else
  rocblas_version="$(rocblas_install_version)"
  rocm_version="$(rocm_install_version)"
  printf '[INFO] %-31s %s\n' "rocBLAS Version:" "$(stack_value "${rocblas_version}")"
  printf '[INFO] %-31s %s\n' "ROCm Version:" "$(stack_value "${rocm_version}")"
fi
printf '[INFO] %-31s %s\n' "System:" "$(value_or_not_found "${system_family}")"
printf '[INFO]\n'
