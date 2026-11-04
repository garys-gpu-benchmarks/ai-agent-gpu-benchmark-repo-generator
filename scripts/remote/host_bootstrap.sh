#!/usr/bin/env bash
# File: scripts/remote/host_bootstrap.sh
# Description: One-time host preparation on the validation VM, run by
#              scripts/remote_host_bootstrap.py before workload 1 (TEMPLATE_00_119).
#              Foreground: apt index, Python venv support, and on NVIDIA the CUDA
#              toolkit and DCGM through the same scripts/lib/nvidia_cuda_toolkit.sh
#              every setup.sh calls, so later setups find them "already present".
#              Background: Hugging Face prefetch of the models this batch needs.
#              Every step only warns; the script always exits 0 so generation continues.
# Execution: bash host_bootstrap.sh --vendor nvidia|amd [--models "<spec> <spec> ..."]
# Environment: BENCHMARK_HOST_STATE_DIR (default /var/lib/gpu-benchmark-host).
set -uo pipefail
# Model specs carry allow_patterns such as *.json; never expand them as globs.
set -f

VENDOR=""
MODELS=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --vendor) VENDOR="${2:-}"; shift 2 ;;
    --models) MODELS="${2:-}"; shift 2 ;;
    *) shift ;;
  esac
done

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE="${BENCHMARK_HOST_STATE_DIR:-/var/lib/gpu-benchmark-host}"
mkdir -p "${STATE}"
export DEBIAN_FRONTEND=noninteractive
WARNINGS=()

log_status() { printf '%s  %s\n' "$(date -u +'%Y-%m-%d %H:%M:%S')" "$1"; }
record_cmd() { printf '%s\n' "$1" >> "${STATE}/bootstrap_commands.txt"; }
warn() { WARNINGS+=("$1"); echo "[WARN] $1"; }

log_status "PHASE|BOOTSTRAP start vendor=${VENDOR:-unknown}"

apt_ok=1
if [[ -f "${HERE}/../lib/keep_running_kernel.sh" ]]; then
  # shellcheck disable=SC1091
  source "${HERE}/../lib/keep_running_kernel.sh"
  if ! keep_running_kernel; then
    warn "keep_running_kernel refused this host; skipping apt work in the bootstrap (each setup.sh will report it)"
    apt_ok=0
  fi
fi

if [[ "${apt_ok}" == 1 ]]; then
  record_cmd "apt-get update -y"
  if apt-get update -y; then
    date +%s > "${STATE}/apt_updated_epoch"
  else
    warn "apt-get update failed"
  fi
  record_cmd "apt-get install -y python3 python3-venv python3-pip curl ca-certificates"
  apt-get install -y python3 python3-venv python3-pip curl ca-certificates || warn "apt-get install python3-venv failed"
fi

NVCC_RELEASE=""
DCGM_STATE="not-applicable"
if [[ "${VENDOR}" == "nvidia" && "${apt_ok}" == 1 ]]; then
  # shellcheck disable=SC1091
  source "${HERE}/../lib/nvidia_cuda_toolkit.sh"
  started=$(date +%s)
  if install_nvidia_cuda_toolkit; then
    NVCC_RELEASE="${NVIDIA_CUDA_VERSION:-}"
    log_status "STEP|BOOTSTRAP CUDA toolkit ${NVCC_RELEASE} ready in $(( $(date +%s) - started )) s"
  else
    warn "CUDA toolkit install failed in the bootstrap; each setup.sh will try again"
  fi
  if command -v dcgmi >/dev/null 2>&1; then
    DCGM_STATE="present"
  elif pkg="$(nvidia_dcgm_package 2>/dev/null)"; then
    record_cmd "apt-get install -y ${pkg}"
    if apt-get install -y "${pkg}"; then DCGM_STATE="installed"; else DCGM_STATE="failed"; warn "apt-get install ${pkg} failed"; fi
    nvidia_dpkg_consistent "apt-get install ${pkg}" || warn "dpkg is not consistent after ${pkg}"
  fi
fi

# Background Hugging Face prefetch. It runs while the light workloads run, so the
# model workloads find their weights on disk. huggingface_hub file locks make a
# workload that asks for the same file wait for this download instead of racing it.
PREFETCH="not-requested"
if [[ -n "${MODELS// /}" ]]; then
  if [[ -f "${STATE}/prefetch.pid" ]] && kill -0 "$(cat "${STATE}/prefetch.pid" 2>/dev/null)" 2>/dev/null; then
    PREFETCH="already-running"
  else
    PY="$(command -v python3 || true)"
    if [[ -z "${PY}" ]]; then
      warn "python3 is missing; model prefetch skipped"
      PREFETCH="skipped"
    else
      # setsid + nohup: the prefetch must outlive this SSH session.
      # shellcheck disable=SC2086
      setsid nohup bash "${HERE}/prefetch_runner.sh" "${STATE}" "${PY}" ${MODELS} \
        > "${STATE}/prefetch.log" 2>&1 < /dev/null &
      echo $! > "${STATE}/prefetch.pid"
      PREFETCH="started pid $(cat "${STATE}/prefetch.pid")"
    fi
  fi
fi

OS_ID="$(. /etc/os-release 2>/dev/null; printf '%s' "${VERSION_ID:-}")"
{
  printf '{\n'
  printf '  "vendor": "%s",\n' "${VENDOR}"
  printf '  "os_version_id": "%s",\n' "${OS_ID}"
  printf '  "cuda_toolkit": "%s",\n' "${NVCC_RELEASE}"
  printf '  "dcgm": "%s",\n' "${DCGM_STATE}"
  printf '  "prefetch": "%s",\n' "${PREFETCH}"
  printf '  "finished_epoch": %s\n' "$(date +%s)"
  printf '}\n'
} > "${STATE}/host_stamp.json"

for w in "${WARNINGS[@]}"; do echo "BOOTSTRAP_WARN ${w}"; done
echo "BOOTSTRAP_KV cuda_toolkit=${NVCC_RELEASE}"
echo "BOOTSTRAP_KV dcgm=${DCGM_STATE}"
echo "BOOTSTRAP_KV prefetch=${PREFETCH}"
log_status "PHASE|BOOTSTRAP done"
echo "BOOTSTRAP_OK"
exit 0
