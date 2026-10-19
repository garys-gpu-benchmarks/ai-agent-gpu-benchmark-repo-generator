#!/usr/bin/env bash
# File: scripts/templates/setup_cpu_system_skeleton.sh
# Description: Host-only setup.sh for Execution Domain CPU / System. Apt, venv, Framework tools, build.sh.
# Execution: Copied to generated repo root as setup.sh.
set -euo pipefail

if [[ -z "${HOME:-}" ]]; then
  HOME="$(getent passwd "$(id -u)" | cut -d: -f6 2>/dev/null || true)"
  HOME="${HOME:-/root}"
  export HOME
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_NAME="$(basename "${REPO_ROOT}")"
cd "${REPO_ROOT}"

ASSUME_YES=0
usage() {
  cat <<'USAGE'
Usage: bash setup.sh [OPTIONS]

Install host prerequisites for a CPU / System workload.

  --assume-yes    Run noninteractively
  --help          Show this help and exit
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --assume-yes|-y) ASSUME_YES=1; shift ;;
    --help|-h) usage; exit 0 ;;
    --skip-rocm|--skip-rvs|--resume-auto|--no-resume-auto|--resume-from-service) shift ;;
    *) echo "[ERROR] Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

mkdir -p results src scripts bin
STATUS_FILE="${REPO_ROOT}/results/install_status.txt"
COMMANDS_FILE="${REPO_ROOT}/results/install_commands.txt"
: >> "${STATUS_FILE}"
: >> "${COMMANDS_FILE}"

log_status() { printf '%s  %s\n' "$(date -u +'%Y-%m-%d %H:%M:%S')" "$1" | tee -a "${STATUS_FILE}"; }
record_cmd() { printf '%s\n' "$1" >> "${COMMANDS_FILE}"; }

apt_install() {
  local pkg
  for pkg in "$@"; do
    if dpkg -s "${pkg}" >/dev/null 2>&1; then
      log_status "STEP already present: ${pkg}"
      continue
    fi
    log_status "STEP apt-get install ${pkg}"
    record_cmd "DEBIAN_FRONTEND=noninteractive apt-get install -y ${pkg}"
    DEBIAN_FRONTEND=noninteractive apt-get install -y "${pkg}"
  done
}

verify_cmd() {
  local name="$1"
  shift
  if ! "$@"; then
    echo "[FAIL] Required framework item failed verification: ${name}" >&2
    exit 1
  fi
  log_status "PASS verified ${name}"
}

# Same rule as the PMU collector: a kernel-matched file under /usr/lib/linux-tools,
# large enough to be the real binary. /usr/bin/perf is often a wrapper whose
# version text says "not found".
kernel_perf_bin() {
  local kernel="$1" candidate size
  for candidate in "/usr/lib/linux-tools/${kernel}/perf" "/usr/lib/linux-tools-${kernel}/perf"; do
    if [[ -f "${candidate}" ]]; then
      size="$(stat -L -c%s "${candidate}" 2>/dev/null || echo 0)"
      if [[ "${size}" -gt 10000 ]]; then
        printf '%s\n' "${candidate}"
        return 0
      fi
    fi
  done
  return 1
}

read_framework_text() {
  if [[ ! -f benchmark_specification.json ]]; then
    printf ''
    return 0
  fi
  "${BENCHMARK_PYTHON:-python3}" - <<'PY'
import json
from pathlib import Path
fields = {
    item.get("field_name", ""): str(item.get("value", ""))
    for item in json.loads(Path("benchmark_specification.json").read_text(encoding="utf-8"))
}
print(fields.get("Framework", ""))
PY
}

perf_is_optional() {
  grep -Eiq 'perf[[:space:]]*\(optional\)' <<< "$1"
}

# No kernel-matched perf: warn and continue. The PMU metrics are then published as
# the expected na "perf not installed", so the workload still runs and passes with
# empty counters. Typical cause: a container running the host's kernel (for example
# 6.8.0-136-generic) under an Ubuntu release whose archive has no linux-tools for it.
warn_missing_kernel_perf() {
  local kernel="$1" os_id common_pkg flavor_pkg
  os_id="$(. /etc/os-release && printf '%s' "${VERSION_ID:-unknown}")"
  common_pkg="linux-tools-${kernel%-*}"
  flavor_pkg="linux-tools-${kernel}"
  log_status "WARN kernel-matched perf is missing for kernel ${kernel} on Ubuntu ${os_id}; PMU metrics will be na"
  echo "[WARN] Kernel-matched perf is missing for kernel ${kernel} on Ubuntu ${os_id}; the PMU metrics will be na." >&2
  echo "[WARN] For counters, install ${common_pkg} and ${flavor_pkg} from the Ubuntu release that built kernel ${kernel} (do not add that release to this machine's apt sources), then rerun." >&2
}

workload_framework=""
BENCHMARK_INSTALL_FIO="${BENCHMARK_INSTALL_FIO:-0}"
BENCHMARK_INSTALL_IPERF="${BENCHMARK_INSTALL_IPERF:-0}"
BENCHMARK_INSTALL_STRESS_NG="${BENCHMARK_INSTALL_STRESS_NG:-0}"
BENCHMARK_INSTALL_LMBENCH="${BENCHMARK_INSTALL_LMBENCH:-0}"
BENCHMARK_INSTALL_PERF="${BENCHMARK_INSTALL_PERF:-0}"
# Host interpreter: Ubuntu's /usr/bin/python3 unless BENCHMARK_PYTHON is set.
# An interactive root PATH can put an image's uv Python 3.11 first; Ubuntu
# publishes no python3.11-venv, so apt would fail on "python${PY_VER}-venv".
# Minimal images ship no Python. Install the distro interpreter before the version probe.
# Check for Ubuntu's own /usr/bin/python3, not any python3 on PATH: some cloud images
# activate a virtualenv (for example /root/.venv, Python 3.11) and ship no distro
# Python, so "command -v python3" succeeded and the version probe asked apt for
# python3.11-venv, which Ubuntu does not publish.
if [[ ! -x /usr/bin/python3 ]]; then
  log_status "STEP apt-get install python3"
  record_cmd "DEBIAN_FRONTEND=noninteractive apt-get install -y python3"
  DEBIAN_FRONTEND=noninteractive apt-get install -y python3
fi
if [[ -z "${BENCHMARK_PYTHON:-}" && -x /usr/bin/python3 ]]; then
  export BENCHMARK_PYTHON=/usr/bin/python3
fi
if [[ -f benchmark_specification.json ]]; then
  if [[ -f "${REPO_ROOT}/scripts/framework_registry.py" ]]; then
    eval "$("${BENCHMARK_PYTHON:-python3}" "${REPO_ROOT}/scripts/framework_registry.py" --spec benchmark_specification.json --vendor cpu --format env)"
  else
    workload_framework="$("${BENCHMARK_PYTHON:-python3}" - <<'PY'
import json
from pathlib import Path
fields = {
    item.get("field_name", ""): str(item.get("value", ""))
    for item in json.loads(Path("benchmark_specification.json").read_text(encoding="utf-8"))
}
print(fields.get("Framework", ""))
PY
    )"
    if grep -Eiq 'fio|flexible i/o' <<< "${workload_framework}"; then BENCHMARK_INSTALL_FIO=1; fi
    if grep -Eiq 'iperf3' <<< "${workload_framework}"; then BENCHMARK_INSTALL_IPERF=1; fi
    if grep -Eiq 'stress-ng' <<< "${workload_framework}"; then BENCHMARK_INSTALL_STRESS_NG=1; fi
    if grep -Eiq 'lmbench' <<< "${workload_framework}"; then BENCHMARK_INSTALL_LMBENCH=1; fi
    if grep -Eiq '(^|[,[:space:]])perf([,[:space:]]|$)|linux perf|pmu' <<< "${workload_framework}"; then BENCHMARK_INSTALL_PERF=1; fi
  fi
fi

if [[ "${ASSUME_YES}" -ne 1 ]]; then
  echo "setup.sh will install Ubuntu packages and create ${REPO_ROOT}/.venv."
  read -r -p "Press Enter to continue or Ctrl-C to abort. "
fi

log_status "PHASE setup.sh start ${REPO_NAME}"
# shellcheck disable=SC1091
source "${REPO_ROOT}/scripts/lib/keep_running_kernel.sh"
keep_running_kernel
record_cmd "DEBIAN_FRONTEND=noninteractive apt-get update -y"
DEBIAN_FRONTEND=noninteractive apt-get update -y

PY_VER="$(${BENCHMARK_PYTHON:-python3} -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
apt_install \
  python3 python3-venv "python${PY_VER}-venv" python3-pip \
  build-essential gcc g++ make cmake sqlite3 pkg-config \
  numactl libnuma-dev git curl ca-certificates

if [[ "${BENCHMARK_INSTALL_FIO}" == "1" ]]; then
  apt_install fio libaio-dev || apt_install fio
fi
if [[ "${BENCHMARK_INSTALL_IPERF}" == "1" ]]; then
  apt_install iperf3
fi
if [[ "${BENCHMARK_INSTALL_STRESS_NG}" == "1" ]]; then
  apt_install stress-ng
fi
if [[ "${BENCHMARK_INSTALL_LMBENCH}" == "1" ]]; then
  apt_install lmbench || true
fi
if [[ "${BENCHMARK_INSTALL_PERF}" == "1" ]]; then
  # linux-tools-generic follows the newest archive kernel and pulls its image
  # and headers. Those postinst scripts build DKMS for a kernel that is not running.
  # Install only the package named for the running kernel, when this apt cache has it.
  KERNEL_RELEASE="$(uname -r)"
  PERF_PARANOID="$(cat /proc/sys/kernel/perf_event_paranoid 2>/dev/null || echo unknown)"
  log_status "INFO perf_event_paranoid=${PERF_PARANOID}"
  if apt-cache show "linux-tools-${KERNEL_RELEASE}" >/dev/null 2>&1; then
    apt_install linux-tools-common
    apt_install "linux-tools-${KERNEL_RELEASE}"
  fi
fi

if [[ -f benchmark_specification.json ]]; then
  gpu_vendor="$("${BENCHMARK_PYTHON:-python3}" - <<'PY'
import json
from pathlib import Path
fields = {
    item.get("field_name", ""): str(item.get("value", ""))
    for item in json.loads(Path("benchmark_specification.json").read_text(encoding="utf-8"))
}
print(fields.get("GPU Vendor", ""))
PY
  )"
fi

PYTHON_BIN="${BENCHMARK_PYTHON:-python3}"
if grep -Eiq 'amd' <<< "${gpu_vendor:-}"; then
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/scripts/lib/uv_python_314.sh"
  ensure_uv_python_314 || {
    echo "[FAIL] uv could not install CPython 3.14 for the AMD benchmark virtualenv." >&2
    exit 1
  }
  PYTHON_BIN="${UV_PYTHON}"
fi
if [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
  existing_py="$("${REPO_ROOT}/.venv/bin/python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  wanted_py="$("${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  if [[ "${existing_py}" != "${wanted_py}" ]]; then
    rm -rf "${REPO_ROOT}/.venv"
  fi
fi
if [[ ! -x "${REPO_ROOT}/.venv/bin/python" ]]; then
  log_status "STEP python created ${REPO_ROOT}/.venv"
  record_cmd "${PYTHON_BIN} -m venv ${REPO_ROOT}/.venv"
  "${PYTHON_BIN}" -m venv "${REPO_ROOT}/.venv"
fi
"${REPO_ROOT}/.venv/bin/python" -m pip install --upgrade pip
if [[ -f requirements.txt ]]; then
  "${REPO_ROOT}/.venv/bin/python" -m pip install -r requirements.txt
fi
"${REPO_ROOT}/.venv/bin/python" -m pip install 'PyYAML>=6.0'

verify_cmd "Bash" bash --version
verify_cmd "SQLite" sqlite3 --version
verify_cmd "Python" "${REPO_ROOT}/.venv/bin/python" --version
verify_cmd "PyYAML" "${REPO_ROOT}/.venv/bin/python" -c "import yaml; print(yaml.__version__)"
if [[ "${BENCHMARK_INSTALL_FIO}" == "1" ]]; then
  verify_cmd "fio" fio --version
fi
if [[ "${BENCHMARK_INSTALL_IPERF}" == "1" ]]; then
  verify_cmd "iperf3" iperf3 --version
fi
if [[ "${BENCHMARK_INSTALL_STRESS_NG}" == "1" ]]; then
  verify_cmd "stress-ng" stress-ng --version
fi
if [[ "${BENCHMARK_INSTALL_PERF}" == "1" ]]; then
  KERNEL_RELEASE="$(uname -r)"
  PERF_BIN="$(kernel_perf_bin "${KERNEL_RELEASE}" || true)"
  PERF_VERSION=""
  if [[ -n "${PERF_BIN}" ]]; then
    PERF_VERSION="$("${PERF_BIN}" --version 2>&1 || true)"
  fi
  if [[ -z "${PERF_BIN}" ]] || grep -qi 'not found' <<< "${PERF_VERSION}"; then
    if perf_is_optional "$(read_framework_text)"; then
      log_status "WARN linux-tools-${KERNEL_RELEASE} is not a runnable kernel-matched perf; optional perf metrics stay na"
    else
      warn_missing_kernel_perf "${KERNEL_RELEASE}"
    fi
  else
    verify_cmd "perf" "${PERF_BIN}" --version
  fi
fi

if [[ -f scripts/build.sh ]]; then
  log_status "STEP scripts/build.sh"
  bash scripts/build.sh
fi
if [[ -f src/stream.c && ! -x bin/stream && ! -x build/stream ]]; then
  echo "[FAIL] src/stream.c is present but the STREAM binary was not built." >&2
  exit 1
fi
if [[ -f src/numa_sweep.cpp && ! -x bin/numa_sweep ]]; then
  echo "[FAIL] src/numa_sweep.cpp is present but bin/numa_sweep was not built." >&2
  exit 1
fi
if [[ -f src/gups.c && ! -x bin/gups ]]; then
  echo "[FAIL] src/gups.c is present but bin/gups was not built." >&2
  exit 1
fi

printf 'setup_complete=1\nworkload=%s\nbundle=cpu-system\ncompleted_at=%s\n' \
  "${REPO_NAME}" "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" > "${REPO_ROOT}/.setup_state"
log_status "PHASE SETUP complete"
echo "[PASS] setup.sh complete"
