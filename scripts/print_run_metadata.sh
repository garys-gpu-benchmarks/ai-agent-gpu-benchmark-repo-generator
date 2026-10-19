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
  rocblas_version="$(dpkg-query -W -f='${Version}' rocblas 2>/dev/null || true)"
  rocm_version="$(dpkg-query -W -f='${Version}' rocm-core 2>/dev/null || true)"
  printf '[INFO] %-31s %s\n' "rocBLAS Version:" "$(stack_value "${rocblas_version}")"
  printf '[INFO] %-31s %s\n' "ROCm Version:" "$(stack_value "${rocm_version}")"
fi
printf '[INFO] %-31s %s\n' "System:" "$(value_or_not_found "${system_family}")"
printf '[INFO]\n'
