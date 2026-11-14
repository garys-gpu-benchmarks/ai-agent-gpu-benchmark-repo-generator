#!/usr/bin/env bash
# File: scripts/lib/common.sh
# Version: 1.2.2
# Maintainer: AI Agent GPU Benchmark Repo Generator
# Date: 2026-08-28
# Description: Shared logging, command execution, metadata, secret-masking, ledger-on-die, summary command lines, HTTP ready-wait helpers, and hipcc host-GCC pin.
# Execution: source scripts/lib/common.sh
# Options: None
# Requirements: bash 4+
# Environment: Local benchmark host.
# Dependencies: coreutils, uname, hostname; journalctl when available
# Variables: LOG_LEVEL, RUN_DIR, COMMAND_LOG, BENCHMARK_PROFILE, BENCHMARK_START_DATETIME, BENCHMARK_RUN_ACTIVE, BENCHMARK_RUN_COMMAND, BENCHMARK_RUN_COMMAND_SUBMITTED, BENCHMARK_READY_WAIT_SEC
# Repository: gpu-bench/sys-bench template
# License: Apache-2.0

set -euo pipefail

LOG_LEVEL="${LOG_LEVEL:-INFO}"

# When this run_benchmark.sh started, for the ledger's start_script_datetime and
# runtime_script_mm_ss (TEMPLATE_00_135). Recorded once per process: a second source
# in the same shell keeps it, and a child run_benchmark.sh (the next profile) gets
# its own. Child scripts that source this file (setup.sh) cannot change the parent's.
if [[ "${BENCHMARK_SCRIPT_START_PID:-}" != "$$" ]]; then
  BENCHMARK_SCRIPT_START_NS="$(date +%s%N 2>/dev/null || true)"
  [[ "${BENCHMARK_SCRIPT_START_NS}" =~ ^[0-9]+$ ]] || BENCHMARK_SCRIPT_START_NS="$(date +%s)000000000"
  BENCHMARK_SCRIPT_START_PID="$$"
  export BENCHMARK_SCRIPT_START_NS BENCHMARK_SCRIPT_START_PID
fi

# Keep Hugging Face snapshots and pip wheels on the overlay-root home when
# the workload tree lives on a quotaed volume (this pod: /workspace ~35G).
# Overlay run_benchmark.sh files use ${HF_HOME:-${REPO_ROOT}/.cache/...}, so
# exporting HF_HOME here redirects weights without editing those overlays.
if [[ -z "${HF_HOME:-}" ]]; then
  export HF_HOME="${HOME}/.cache/huggingface"
fi
if [[ -z "${PIP_CACHE_DIR:-}" ]]; then
  export PIP_CACHE_DIR="${HOME}/.cache/pip"
fi
# The Hugging Face xet client fetched bge-small-en-v1.5 one small range at a time
# on the Nov 3 26.04 host (most of 432's 23 minutes). Plain HTTP downloads are the
# default; set HF_HUB_DISABLE_XET=0 to use xet (TEMPLATE_00_119).
export HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"

# hipcc on Ubuntu 26.04 / ROCm 10.1.0 (Clang 24) still needs a GCC 15 host
# pin so <cstdlib> is visible to the HIP wrapper. Export HIPCC_COMPILE_FLAGS_APPEND
# so child `bash scripts/build.sh` from setup and collect inherits the pin.
if [[ -f "${BASH_SOURCE[0]%/*}/hipcc_host_gcc.sh" ]]; then
  # shellcheck disable=SC1091
  source "${BASH_SOURCE[0]%/*}/hipcc_host_gcc.sh"
fi

timestamp_utc() {
  date -u +"%Y-%m-%d %H:%M:%S"
}

iso_utc_now() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

log_msg() {
  local level="$1"
  shift
  log "$level" "$*"
}

set_log_level() {
  LOG_LEVEL="${1:-INFO}"
  export LOG_LEVEL
}

log_phase() {
  log_msg INFO "Phase: $*"
}

log_section() {
  log_msg INFO "========== $* =========="
}

log() {
  local level="$1"
  shift
  case "${level}" in
    ERROR|FAIL) log_fail "$*" ;;
    WARN) log_warn "$*" ;;
    INFO) log_info "$*" ;;
    PASS) log_pass "$*" ;;
    *) echo "[${level}] $*" ;;
  esac
}

# When more than one of --smoke, --baseline, --extended is given, run the
# script once per profile, in the order given, with the other options
# unchanged, then exit with the first non-zero status. (Before 2026-11-06 the
# last profile flag silently replaced the others.) Each profile is a normal
# run: its own results/raw folder and its own ledger row.
run_profiles_in_order() {
  local script="$1"
  shift
  local -a profiles=() rest=()
  local arg profile seen
  for arg in "$@"; do
    case "${arg}" in
      --smoke|--baseline|--extended)
        seen=0
        for profile in "${profiles[@]+"${profiles[@]}"}"; do
          [[ "${profile}" == "${arg}" ]] && seen=1
        done
        [[ "${seen}" -eq 1 ]] || profiles+=("${arg}")
        ;;
      *) rest+=("${arg}") ;;
    esac
  done
  [[ "${#profiles[@]}" -gt 1 ]] || return 0
  local index=0 code status=0 summary=""
  for profile in "${profiles[@]}"; do
    index=$((index + 1))
    echo "[INFO] ===== Profile ${profile#--} (${index} of ${#profiles[@]}) ====="
    code=0
    bash "${script}" "${profile}" "${rest[@]+"${rest[@]}"}" || code=$?
    if [[ "${code}" -eq 0 ]]; then
      summary+="${summary:+, }${profile#--} ok"
    else
      summary+="${summary:+, }${profile#--} FAILED (exit ${code})"
      [[ "${status}" -ne 0 ]] || status="${code}"
    fi
  done
  echo "[INFO] Profiles: ${summary}"
  exit "${status}"
}

debug_enabled() {
  [[ "${LOG_LEVEL:-INFO}" == "DEBUG" ]]
}

# Record "[RUN] <command>". The line always goes to run.log in the run
# directory (once set_benchmark_run_dir has been called) and reaches the
# terminal only at --log-level DEBUG.
log_run() {
  local line="[RUN] $*"
  local run_dir="${BENCHMARK_RUN_DIR:-${RUN_DIR:-}}"
  if [[ -n "${run_dir}" && -d "${run_dir}" ]]; then
    printf '%s\n' "${line}" >> "${run_dir}/run.log"
  fi
  if debug_enabled; then
    printf '%s\n' "${line}"
  fi
  return 0
}

# Pipe filter for step output that is already tee'd into run.log: drop lines
# that start with [RUN] from the terminal unless --log-level DEBUG.
hide_run_lines() {
  if debug_enabled; then
    cat
  else
    grep --line-buffered -v '^[[:space:]]*\[RUN\]' || true
  fi
}

run_cmd() {
  local command_text
  if [[ "$#" -eq 1 ]]; then
    log_run "$1"
    bash -lc "$1"
  else
    printf -v command_text '%q ' "$@"
    log_run "${command_text% }"
    "$@"
  fi
}

run_logged_cmd() {
  run_cmd "$@"
}

ensure_file_header() {
  local target="$1"
  [[ -e "${target}" ]] || : > "${target}"
}

log_error() { echo "[ERROR] $*" >&2; }
log_warn() { echo "[WARN] $*" >&2; }
log_info() { [[ "${LOG_LEVEL}" != "ERROR" && "${LOG_LEVEL}" != "WARN" ]] && echo "[INFO] $*" || true; }
log_pass() { echo "[PASS] $*"; }
log_fail() { echo "[FAIL] $*" >&2; }

benchmark_run_err_trap() {
  local line="${1:-unknown}"
  local cmd="${2:-unknown}"
  # set -e abort that never called die() (102 validation is the usual case).
  # Still exit 1. This does not turn a failure into success.
  append_runtime_ledger_on_error "set -e exit at line ${line}: ${cmd}" || true
  exit 1
}

epoch_ns() {
  # GNU date. A host without %N falls back to whole seconds.
  local raw
  raw="$(date +%s%N 2>/dev/null || true)"
  if [[ "${raw}" =~ ^[0-9]+$ ]]; then
    printf '%s' "${raw}"
  else
    printf '%s000000000' "$(date +%s)"
  fi
}

begin_benchmark_run() {
  BENCHMARK_PROFILE="${1:-${BENCHMARK_PROFILE:-smoke}}"
  BENCHMARK_START_DATETIME="${2:-${BENCHMARK_START_DATETIME:-$(iso_utc_now)}}"
  BENCHMARK_START_NS="$(epoch_ns)"
  BENCHMARK_RUN_ACTIVE=1
  BENCHMARK_LEDGER_WRITTEN=0
  # Setup starts here (ensure_setup.sh is the next step). mark_benchmark_measure_start
  # moves BENCHMARK_START_* to the benchmark start but leaves this one, so the ledger
  # can report setup and benchmark separately (TEMPLATE_00_135).
  BENCHMARK_SETUP_START_NS="${BENCHMARK_START_NS}"
  BENCHMARK_MEASURE_STARTED=0
  # A Python collector that loads its model itself writes the time its timed work
  # starts to this file (mark_measure_start in the collector); record_benchmark_stop
  # moves the benchmark start there (TEMPLATE_00_141).
  BENCHMARK_MEASURE_START_FILE="${TMPDIR:-/tmp}/benchmark_measure_start.$$"
  rm -f "${BENCHMARK_MEASURE_START_FILE}" 2>/dev/null || true
  export BENCHMARK_PROFILE BENCHMARK_START_DATETIME BENCHMARK_START_NS BENCHMARK_RUN_ACTIVE BENCHMARK_LEDGER_WRITTEN
  export BENCHMARK_SETUP_START_NS BENCHMARK_MEASURE_STARTED BENCHMARK_MEASURE_START_FILE
  # Without errtrace, ERR is not inherited by functions. 102's validate_phase
  # then exits 1 under set -e and never writes a ledger row.
  set -E
  trap 'benchmark_run_err_trap "${LINENO}" "${BASH_COMMAND}"' ERR
}

mark_benchmark_measure_start() {
  # Setup ends and the benchmark clock starts here, on every run (TEMPLATE_00_141).
  # Setup is everything before the timed work: ensure_setup.sh (the full install on
  # the first run, the "already complete" check after that), model downloads or
  # download checks, and, in the server workloads, starting the server and loading
  # the model (those runners call this again once wait_for_server returns).
  # Benchmark is the timed work only. Calling it again moves the start later.
  # (TEMPLATE_00_139 counted setup only on the first run after setup.sh; reruns showed
  # setup 00:00 and their server start and model load as benchmark time.)
  BENCHMARK_START_DATETIME="$(iso_utc_now)"
  BENCHMARK_START_NS="$(epoch_ns)"
  BENCHMARK_MEASURE_STARTED=1
  export BENCHMARK_START_DATETIME BENCHMARK_START_NS BENCHMARK_MEASURE_STARTED
}

apply_collector_measure_start() {
  # A collector that loads its model in-process (121-126, 132 and their NVIDIA
  # twins) writes the epoch nanoseconds its timed work starts to
  # BENCHMARK_MEASURE_START_FILE. Move the benchmark start there, so model load and
  # warmup count as setup. A missing, unreadable or earlier time changes nothing.
  local file="${BENCHMARK_MEASURE_START_FILE:-}" ns=""
  [[ -n "${file}" && -f "${file}" ]] || return 0
  ns="$(head -n 1 "${file}" 2>/dev/null | tr -dc '0-9')"
  rm -f "${file}" 2>/dev/null || true
  [[ "${BENCHMARK_MEASURE_STARTED:-0}" == "1" && "${ns}" =~ ^[0-9]+$ ]] || return 0
  [[ "${BENCHMARK_START_NS:-}" =~ ^[0-9]+$ ]] || return 0
  (( ns > BENCHMARK_START_NS )) || return 0
  BENCHMARK_START_NS="${ns}"
  BENCHMARK_START_DATETIME="$(date -u -d "@$((ns / 1000000000))" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || echo "${BENCHMARK_START_DATETIME}")"
  export BENCHMARK_START_DATETIME BENCHMARK_START_NS
}

prefetch_vllm_model_weights() {
  # Download the files vLLM will load before the published clock starts.
  # On 2026-11-08 the first vLLM smoke on each fresh VM (127/227/327/427) spent
  # 111 s of its 3:26 in "Time spent downloading weights"; with the model cached
  # the same smoke took about 30 s. Callers run mark_benchmark_measure_start
  # after this so the ledger times the benchmark, not the download.
  # Best effort: any failure prints a WARN and vLLM downloads as it did before.
  # Set VLLM_SKIP_PREFETCH=1 to skip.
  local python_bin="$1"
  local model_id="${2:-}"
  [[ -n "${model_id}" ]] || return 0
  if [[ "${VLLM_SKIP_PREFETCH:-0}" == "1" ]]; then
    log_info "VLLM_SKIP_PREFETCH=1: vLLM downloads ${model_id} itself inside the timed run"
    return 0
  fi
  log_info "Fetching ${model_id} weights before the timed run (files already cached are not downloaded again)"
  "${python_bin}" - "${model_id}" <<'PY' || log_warn "model prefetch did not finish; vLLM will download ${model_id} inside the timed run"
import os
import sys
import time

repo = sys.argv[1]
if os.path.isdir(repo):
    print(f"[INFO] {repo} is a local directory; nothing to download", flush=True)
    raise SystemExit(0)
try:
    from huggingface_hub import HfApi, snapshot_download
except Exception as exc:
    print(f"[WARN] huggingface_hub is not importable: {exc}", flush=True)
    raise SystemExit(0)
try:
    files = set(HfApi().list_repo_files(repo))
except Exception as exc:
    print(f"[WARN] cannot list {repo} on the Hugging Face Hub: {exc}", flush=True)
    raise SystemExit(0)
# vLLM loads a Mistral-format checkpoint (params.json + consolidated*.safetensors)
# when the repo has one; on 2026-11-08 it downloaded only consolidated.safetensors
# for mistralai/Mistral-7B-v0.3. Otherwise it loads the Hugging Face weights.
if "params.json" in files and any(f.startswith("consolidated") and f.endswith(".safetensors") for f in files):
    patterns = ["*.json", "consolidated*.safetensors", "tokenizer.model*"]
elif any(f.endswith(".safetensors") for f in files):
    patterns = ["*.json", "*.safetensors", "tokenizer*"]
else:
    patterns = ["*.json", "*.bin", "tokenizer*"]
start = time.monotonic()
try:
    path = snapshot_download(repo, allow_patterns=patterns)
except Exception as exc:
    print(f"[WARN] {repo} download failed: {exc}", flush=True)
    raise SystemExit(0)
print(f"[INFO] {repo} ready in {path} ({time.monotonic() - start:.0f} s, patterns {patterns})", flush=True)
PY
}

record_benchmark_stop() {
  # Same instant as the printed Stop time, with sub-second resolution for the summary.
  apply_collector_measure_start
  STOP_TIME="$(iso_utc_now)"
  BENCHMARK_STOP_NS="$(epoch_ns)"
  export STOP_TIME BENCHMARK_STOP_NS
}

isolate_repo_python() {
  # Stop 131 from importing 130's editable sglang/aiter via inherited PYTHONPATH.
  unset PYTHONPATH
  unset PYTHONHOME
  export PYTHONNOUSERSITE=1
}

set_benchmark_run_dir() {
  BENCHMARK_RUN_DIR="${1:-}"
  export BENCHMARK_RUN_DIR
  if [[ -f "${REPO_ROOT:-}/scripts/lib/nvcc_glibc_throw.sh" ]]; then
    # shellcheck disable=SC1091
    source "${REPO_ROOT}/scripts/lib/nvcc_glibc_throw.sh"
    load_nvcc_toolkit_env
  fi
}

benchmark_raw_run_dir_name() {
  # Usage: benchmark_raw_run_dir_name <repo_name> <hostname>
  # Prints the per-run results/raw directory name (UTC timestamp):
  #   YYYYMMDD_HHMMSSZ_WORKLOAD-NNN_SYSTEM-<hostname>
  # e.g. 20261106_100212Z_WORKLOAD-101_SYSTEM-ubuntu-gpu-mi300x1-192gb-devcloud-atl1
  # NNN is the leading number of <repo_name> (<Workload Number>-<Repo Name>),
  # zero-padded to 3 digits. "_" separates fields only, so any "_" in the
  # values is replaced with "-".
  local repo_name="${1:-}"
  local host_value="${2:-}"
  local stamp workload_raw workload
  stamp="$(date -u +"%Y%m%d_%H%M%S")Z"
  workload_raw="${repo_name%%[-_]*}"
  if [[ "${workload_raw}" =~ ^[0-9]+$ ]]; then
    printf -v workload '%03d' "$((10#${workload_raw}))"
  else
    workload="${repo_name:-unknown}"
  fi
  [[ -n "${host_value}" ]] || host_value="$(hostname -s 2>/dev/null || hostname)"
  workload="${workload//_/-}"
  host_value="${host_value//_/-}"
  printf '%s_WORKLOAD-%s_SYSTEM-%s\n' "${stamp}" "${workload}" "${host_value}"
}

capture_benchmark_run_command_submitted() {
  local quoted=""
  BENCHMARK_RUN_COMMAND_SUBMITTED="bash run_benchmark.sh"
  if (($#)); then
    printf -v quoted ' %q' "$@"
    BENCHMARK_RUN_COMMAND_SUBMITTED+="${quoted}"
  fi
  export BENCHMARK_RUN_COMMAND_SUBMITTED
}

set_benchmark_run_command_submitted() {
  BENCHMARK_RUN_COMMAND_SUBMITTED="${1:-}"
  export BENCHMARK_RUN_COMMAND_SUBMITTED
}

set_benchmark_run_command() {
  BENCHMARK_RUN_COMMAND="${1:-}"
  export BENCHMARK_RUN_COMMAND
}

set_benchmark_run_command_fully_resolved() {
  set_benchmark_run_command "$@"
}

display_shell_command() {
  # BENCHMARK_RUN_COMMAND is assembled with printf %q, so commas and spaces
  # appear as \, and \ . The summary shows the text a reader can paste.
  local raw="${1:-}"
  local -a parts=()
  [[ -n "${raw}" ]] || return 0
  eval "parts=(${raw})" 2>/dev/null || { printf '%s' "${raw}"; return 0; }
  local IFS=' '
  printf '%s' "${parts[*]}"
}

print_benchmark_summary_commands() {
  printf '[INFO] Command submitted: %s\n' "${BENCHMARK_RUN_COMMAND_SUBMITTED:-}"
  printf '[INFO] Command fully resolved: %s\n' "$(display_shell_command "${BENCHMARK_RUN_COMMAND:-}")"
}

display_device() {
  # Device shown in the run summary: "cpu" for CPU / System workloads (STREAM,
  # FIO, iPerf, lmbench, GUPS, ...), otherwise gpu.
  local spec="${REPO_ROOT:-.}/benchmark_specification.json"
  local domain=""
  if [[ -f "${spec}" ]]; then
    domain="$("${PYTHON_BIN:-python3}" -c 'import json,sys
for item in json.load(open(sys.argv[1], encoding="utf-8")):
    if item.get("field_name") == "Execution Domain":
        print(item.get("value") or ""); break' "${spec}" 2>/dev/null || true)"
  fi
  case "${domain}" in
    CPU*) echo "cpu" ;;
    *) echo "${DEVICE:-gpu}" ;;
  esac
}

elapsed_between() {
  # Whole seconds between two ISO-8601 UTC times; empty if either is unparsable.
  local start_epoch stop_epoch
  start_epoch="$(date -u -d "${1:-}" +%s 2>/dev/null)" || return 0
  stop_epoch="$(date -u -d "${2:-}" +%s 2>/dev/null)" || return 0
  (( stop_epoch >= start_epoch )) && echo "$((stop_epoch - start_epoch))" || echo 0
}

format_elapsed_from_ns() {
  # One decimal second. 400000000 ns prints 0.4, so a sub-second run is not "0 sec".
  local start="$1" stop="$2" delta tenths
  if (( stop < start )); then
    echo "0.0"
    return
  fi
  delta=$((stop - start))
  tenths=$(( (delta + 50000000) / 100000000 ))
  printf '%d.%d\n' "$((tenths / 10))" "$((tenths % 10))"
}

benchmark_elapsed_display() {
  local start_ns="${BENCHMARK_START_NS:-}"
  local stop_ns="${BENCHMARK_STOP_NS:-}"
  if [[ "${start_ns}" =~ ^[0-9]+$ && "${stop_ns}" =~ ^[0-9]+$ ]]; then
    format_elapsed_from_ns "${start_ns}" "${stop_ns}"
    return
  fi
  local start="${START_ISO:-${BENCHMARK_START_DATETIME:-}}"
  local stop="${STOP_ISO:-${STOP_TIME:-}}"
  local whole
  whole="$(elapsed_between "${start}" "${stop}")"
  echo "${whole:-0}"
}

write_metrics_summary_txt() {
  local dest="${RUN_DIR:?RUN_DIR is required}/metrics_summary.txt"
  local python_bin="${PYTHON_BIN:-python3}"
  local summary_path="${REPO_ROOT:-.}/results/summary.json"
  local start="${START_ISO:-${BENCHMARK_START_DATETIME:-}}"
  local stop="${STOP_ISO:-${STOP_TIME:-}}"
  # Run ID is the run folder name (unique per run). The old value was the SQLite
  # row id, which was 1 on most runs, blank or a leftover counter on others.
  local run_id status="ok" samples="0" elapsed
  run_id="$(basename "${RUN_DIR}")"
  if [[ -f "${summary_path}" ]]; then
    status="$("${python_bin}" -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("status","ok"))' "${summary_path}")"
    samples="$("${python_bin}" -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("sample_count",0))' "${summary_path}")"
  fi
  # Elapsed is Stop - Start. Nanosecond clocks keep a tenth of a second; the
  # ISO strings stay whole seconds for the ledger and journal window.
  elapsed="$(benchmark_elapsed_display)"
  {
    echo "===== Benchmark Summary ====="
    if [[ "${status}" == "stub" || "${status}" == "SMOKE-STANDIN" ]]; then
      echo "STUB stand-in server; numbered serving metrics are na (stub server, smoke only)."
    fi
    echo "Run ID: ${run_id} | Status: ${status} | Samples: ${samples} | Profile: ${PROFILE:-} | Device: $(display_device)"
    echo "Command submitted: ${BENCHMARK_RUN_COMMAND_SUBMITTED:-}"
    echo "Command fully resolved: $(display_shell_command "${BENCHMARK_RUN_COMMAND:-}")"
    echo "Start time: ${start}"
    echo "Stop time: ${stop}"
    echo "Elapsed time: ${elapsed:-${ELAPSED:-0}} sec"
    echo "Artifacts: ${RUN_DIR}"
    echo "SQLite DB: ${REPO_ROOT}/results/benchmark.db (holds the latest run only)"
    echo
    if [[ -f scripts/print_metric_summary.py && -f "${summary_path}" ]]; then
      "${python_bin}" scripts/print_metric_summary.py --definition benchmark_specification.json --summary "${summary_path}" | sed 's/^\[INFO\] //'
    fi
    echo
  } > "${dest}"
}

finish_benchmark_run() {
  trap - ERR
  set +E
  rm -f "${BENCHMARK_MEASURE_START_FILE:-}" 2>/dev/null || true
  BENCHMARK_LEDGER_WRITTEN=1
  BENCHMARK_RUN_ACTIVE=0
  echo  # blank line between the run's output and the next shell prompt
}

append_runtime_ledger_on_error() {
  local notes="${1:-error}"
  local python_bin=""
  local start=""
  local start_epoch=""
  local now_epoch=""
  local elapsed=0
  [[ "${BENCHMARK_RUN_ACTIVE:-0}" == "1" ]] || return 0
  [[ "${BENCHMARK_LEDGER_WRITTEN:-0}" != "1" ]] || return 0
  if [[ -x "${REPO_ROOT:-.}/.venv/bin/python" ]]; then
    python_bin="${REPO_ROOT:-.}/.venv/bin/python"
  else
    python_bin="${PYTHON_BIN:-python3}"
  fi
  [[ -f scripts/update_runtime_ledger.py ]] || return 0
  start="${BENCHMARK_START_DATETIME:-$(iso_utc_now)}"
  start_epoch="$(date -u -d "${start}" +%s 2>/dev/null || true)"
  now_epoch="$(date -u +%s)"
  if [[ -n "${start_epoch}" ]]; then
    elapsed=$((now_epoch - start_epoch))
    if (( elapsed < 0 )); then
      elapsed=0
    fi
  fi
  local raw_dir="${BENCHMARK_RUN_DIR:-${RUN_DIR:-}}"
  local extra_args=()
  if [[ -n "${raw_dir}" && -f "${raw_dir}/run.log" ]]; then
    extra_args+=(--run-log "${raw_dir}/run.log")
  fi
  if [[ -n "${raw_dir}" && -f "${raw_dir}/commands_executed.sh" ]]; then
    extra_args+=(--command-log "${raw_dir}/commands_executed.sh")
  fi
  "${python_bin}" scripts/update_runtime_ledger.py \
    --profile "${BENCHMARK_PROFILE:-smoke}" \
    --start-datetime "${start}" \
    --total-runtime "${elapsed}" \
    --exit-code 1 \
    --failure-detail "${notes}" \
    --raw-run-dir "${raw_dir}" \
    --runtime-root "${REPO_ROOT:-$(pwd)}" \
    --run-benchmark-command-submitted "${BENCHMARK_RUN_COMMAND_SUBMITTED:-}" \
    --run-benchmark-command-fully-resolved "${BENCHMARK_RUN_COMMAND:-}" \
    --notes "${notes}" \
    "${extra_args[@]}" || log_warn "Runtime ledger update failed"
  BENCHMARK_LEDGER_WRITTEN=1
}

die() {
  log_error "$*"
  append_runtime_ledger_on_error "$*" || true
  echo  # blank line between the run's output and the next shell prompt
  exit 1
}

wait_for_server() {
  local url="$1"
  local timeout_sec="${2:-${BENCHMARK_READY_WAIT_SEC:-600}}"
  if [[ "${BENCHMARK_PROFILE:-}" == "baseline" || "${BENCHMARK_PROFILE:-}" == "extended" ]]; then
    if [[ -f "${REPO_ROOT:-}/scripts/lib/nvcc_glibc_throw.sh" ]]; then
      # shellcheck disable=SC1091
      source "${REPO_ROOT}/scripts/lib/nvcc_glibc_throw.sh"
      nvcc_recheck_for_run
      load_nvcc_toolkit_env
    fi
  fi
  local elapsed=0
  local code=""
  [[ -n "${url}" ]] || die "wait_for_server requires a URL"
  log_info "Waiting up to ${timeout_sec}s for ${url} (HTTP 503 is not ready)"
  while (( elapsed < timeout_sec )); do
    if [[ -n "${SERVER_PID:-}" ]] && ! kill -0 "${SERVER_PID}" 2>/dev/null; then
      die "Server process ${SERVER_PID} exited before ready at ${url} (last HTTP ${code:-none})"
    fi
    code="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 2 --max-time 5 "${url}" 2>/dev/null || true)"
    if [[ "${code}" == "200" ]]; then
      log_info "Server ready at ${url} after ${elapsed}s"
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
  die "Server did not become ready at ${url} within ${timeout_sec}s (last HTTP ${code:-none})"
}

run_logged() {
  local command_text="$*"
  log_run "${command_text}"
  if [[ -n "${COMMAND_LOG:-}" ]]; then
    printf '%s\n' "${command_text}" >> "${COMMAND_LOG}"
  fi
  bash -lc "${command_text}"
}

mask_environment() {
  local output_path="$1"
  env | sort | awk -F= '
    BEGIN { IGNORECASE=1 }
    $1 ~ /(TOKEN|SECRET|KEY|PASSWORD|CREDENTIAL|AUTH)/ { print $1"=<masked>"; next }
    { print }
  ' > "${output_path}"
}

# Save journalctl entries at priority warning or higher into journal_warnings.txt.
# Prefer a run window: capture_journal_warnings <run_dir> <since_iso_utc> <until_iso_utc>
# When since/until are omitted, limit to the current boot (-b) to avoid the full journal.
capture_journal_warnings() {
  local run_dir="$1"
  local since="${2:-}"
  local until="${3:-}"
  local out_path="${run_dir}/journal_warnings.txt"
  local -a journal_args

  mkdir -p "${run_dir}"
  if ! command -v journalctl >/dev/null 2>&1; then
    {
      echo "# journalctl unavailable on this host"
      echo "status=unavailable"
    } > "${out_path}"
    return 0
  fi

  journal_args=(-p warning --no-pager -o short-iso)
  if [[ -n "${since}" ]]; then
    journal_args+=(--since="${since}")
  fi
  if [[ -n "${until}" ]]; then
    journal_args+=(--until="${until}")
  fi
  if [[ -z "${since}" && -z "${until}" ]]; then
    journal_args+=(-b)
  fi

  {
    echo "# journalctl -p warning (warning and higher)"
    if [[ -n "${since}" ]]; then
      echo "# since=${since}"
    fi
    if [[ -n "${until}" ]]; then
      echo "# until=${until}"
    fi
    if [[ -z "${since}" && -z "${until}" ]]; then
      echo "# scope=current-boot"
    fi
    journalctl "${journal_args[@]}" 2>&1 || true
  } > "${out_path}"
}

capture_basic_metadata() {
  local run_dir="$1"
  mkdir -p "${run_dir}"
  mask_environment "${run_dir}/env_variables.txt"
}
