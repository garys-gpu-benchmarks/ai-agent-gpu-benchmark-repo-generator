#!/usr/bin/env bash
# File: run_benchmark.sh
# Version: 1.0.0
# Author: AI Agent GPU Benchmark Repo Generator
# Date: 2026-08-27
# Description: Every profile launches python -m sglang.launch_server; smoke uses the smallest request sizes.
# Execution: bash run_benchmark.sh [--smoke|--baseline|--extended]
# Options: --smoke, --baseline, --extended, --config, --quiet, --log-level, --dtype, --input-len, --output-len, --num-prompts, --seed, --streaming, --specification, --help
# Requirements: bash, repository-local .venv after setup.sh
# Environment: Local generated repository. Remote SSH execution is not supported.
# Dependencies: scripts/lib/common.sh, ensure_setup helper, scripts/prompt_response_client.py, scripts/parse_results.py, scripts/validate_results.py, scripts/update_runtime_ledger.py, scripts/collect_hw_sw_info.sh, scripts/print_run_metadata.sh, scripts/print_metric_summary.py
# Variables: BENCHMARK_PYTHON
# Repository: gpu-bench-amd-sglang-prompt-response-ubu2604
# License: Apache-2.0
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_NAME="$(basename "${REPO_ROOT}")"
cd "${REPO_ROOT}"
# shellcheck disable=SC1091
source scripts/lib/common.sh
capture_benchmark_run_command_submitted "$@"

usage() {
  cat <<'USAGE'
Usage: bash run_benchmark.sh [OPTIONS]

Every profile starts python -m sglang.launch_server with
mistralai/Mistral-7B-v0.3; smoke sends the smallest requests. The client is
scripts/prompt_response_client.py (sequential, one request in flight).

Profiles (default: --smoke):
  --smoke                       Run smoke profile
  --baseline                    Run baseline profile
  --extended                    Run extended profile

Parameters (override the profile's value):
  --dtype <name>                Compute precision (bfloat16)
  --input-len <n>               Prompt tokens
  --output-len <n>              Generated tokens
  --num-prompts <n>             Sequential request count
  --seed <n>                    RNG seed
  --streaming <true|false>      Stream responses for TTFT

General options:
  --config <file>               Config file (default: config/benchmark_config.yaml)
  --quiet                       Suppress nonessential stdout
  --log-level <level>           ERROR|WARN|INFO|DEBUG (default: INFO; DEBUG also prints [RUN] commands)
  --specification               Print this workload's specification and exit
  --help                        Show this help and exit

Examples:
  bash run_benchmark.sh --smoke
  bash run_benchmark.sh --baseline
  bash run_benchmark.sh --extended
  bash run_benchmark.sh --baseline --num-prompts 2
USAGE
}

SERVER_PID=""
cleanup_server() {
  if [[ -n "${SERVER_PID}" ]]; then
    kill "${SERVER_PID}" 2>/dev/null || true
    wait "${SERVER_PID}" 2>/dev/null || true
    SERVER_PID=""
  fi
}
trap cleanup_server EXIT

for _help_arg in "$@"; do
  case "${_help_arg}" in
    --help) usage; exit 0 ;;
    --specification) python3 scripts/print_benchmark_definition.py; exit 0 ;;
  esac
done
run_profiles_in_order "${REPO_ROOT}/run_benchmark.sh" "$@"

PROFILE="smoke"
CONFIG_FILE="config/benchmark_config.yaml"
QUIET=0
LOG_LEVEL_VALUE="INFO"
DTYPE=""
INPUT_LEN=""
OUTPUT_LEN=""
NUM_PROMPTS=""
SEED=""
MODEL_NAME=""
MAX_TOTAL_TOKENS=""
MAX_RUNNING_REQUESTS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --smoke) PROFILE="smoke"; shift ;;
    --baseline) PROFILE="baseline"; shift ;;
    --extended) PROFILE="extended"; shift ;;
    --config) CONFIG_FILE="${2:-}"; shift 2 ;;
    --validate) shift ;;  # ignored; result validation always runs
    --quiet) QUIET=1; shift ;;
    --log-level) LOG_LEVEL_VALUE="${2:-}"; shift 2 ;;
    --dtype) DTYPE="${2:-}"; shift 2 ;;
    --input-len) INPUT_LEN="${2:-}"; shift 2 ;;
    --output-len) OUTPUT_LEN="${2:-}"; shift 2 ;;
    --num-prompts) NUM_PROMPTS="${2:-}"; shift 2 ;;
    --seed) SEED="${2:-}"; shift 2 ;;
    --model-name) MODEL_NAME="${2:-}"; shift 2 ;;
    --max-total-tokens) MAX_TOTAL_TOKENS="${2:-}"; shift 2 ;;
    --max-running-requests) MAX_RUNNING_REQUESTS="${2:-}"; shift 2 ;;
    --help|--specification) shift ;;
    *) die "Unknown option: $1" ;;
  esac
done


set_log_level "${LOG_LEVEL_VALUE}"
begin_benchmark_run "${PROFILE}"
bash scripts/ensure_setup.sh --profile "${PROFILE}"
mark_benchmark_measure_start
PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
[[ -x "${PYTHON_BIN}" ]] || die "Missing ${PYTHON_BIN}; run bash setup.sh --assume-yes first."

yaml_get() {
  "${PYTHON_BIN}" - "${CONFIG_FILE}" "${PROFILE}" "$1" <<'PY'
import sys
from pathlib import Path
key = sys.argv[3]
profile = sys.argv[2]
text = Path(sys.argv[1]).read_text(encoding="utf-8")
in_sweep = False
current = None
values = {}
for raw in text.splitlines():
    line = raw.split("#", 1)[0].rstrip()
    if line.strip() == "sweep:":
        in_sweep = True
        continue
    if not in_sweep:
        continue
    if line and not line.startswith(" ") and not line.startswith("\t"):
        break
    if ":" not in line:
        continue
    indent = len(line) - len(line.lstrip(" "))
    name, value = line.split(":", 1)
    name = name.strip()
    value = value.strip()
    if indent <= 2:
        current = name
        values[name] = value
        if value == "":
            values[name] = {}
    elif isinstance(values.get(current), dict):
        values[current][name] = value
raw_value = values.get(key, "")
if isinstance(raw_value, dict):
    raw_value = raw_value.get(profile, next(iter(raw_value.values()), ""))
text = "" if raw_value is None else str(raw_value).strip()
if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
    text = text[1:-1]
print(text)
PY
}

DTYPE="${DTYPE:-$(yaml_get dtype)}"
INPUT_LEN="${INPUT_LEN:-$(yaml_get input_len)}"
OUTPUT_LEN="${OUTPUT_LEN:-$(yaml_get output_len)}"
NUM_PROMPTS="${NUM_PROMPTS:-$(yaml_get num_prompts)}"
SEED="${SEED:-$(yaml_get seed)}"
MODEL_NAME="${MODEL_NAME:-$(yaml_get model_name)}"
MODEL_NAME="${MODEL_NAME:-mistralai/Mistral-7B-v0.3}"
MAX_TOTAL_TOKENS="${MAX_TOTAL_TOKENS:-$(yaml_get max_total_tokens)}"
MAX_TOTAL_TOKENS="${MAX_TOTAL_TOKENS:-2048}"
MAX_RUNNING_REQUESTS="${MAX_RUNNING_REQUESTS:-$(yaml_get max_running_requests)}"
MAX_RUNNING_REQUESTS="${MAX_RUNNING_REQUESTS:-1}"
OUTPUT_FORMAT="$(yaml_get output_format)"
OUTPUT_FORMAT="${OUTPUT_FORMAT:-csv}"
case "${DTYPE}" in
  bf16|BF16) DTYPE="bfloat16" ;;
esac

BENCHMARK_RUN_COMMAND="bash run_benchmark.sh --${PROFILE}"
BENCHMARK_RUN_COMMAND+=" --model-name ${MODEL_NAME} --dtype ${DTYPE} --input-len ${INPUT_LEN} --output-len ${OUTPUT_LEN} --num-prompts ${NUM_PROMPTS} --seed ${SEED} --max-total-tokens ${MAX_TOTAL_TOKENS} --max-running-requests ${MAX_RUNNING_REQUESTS}"
set_benchmark_run_command "${BENCHMARK_RUN_COMMAND}"

HOSTNAME_VALUE="$(hostname -s 2>/dev/null || hostname)"
RUN_DIR="${REPO_ROOT}/results/raw/$(benchmark_raw_run_dir_name "${REPO_NAME}" "${HOSTNAME_VALUE}")"
mkdir -p "${RUN_DIR}"
RAW_FILE="${RUN_DIR}/raw_output.txt"
set_benchmark_run_dir "${RUN_DIR}"
COMMAND_LOG="${RUN_DIR}/commands_executed.sh"
{ echo "#!/usr/bin/env bash"; echo "set -euo pipefail"; } > "${COMMAND_LOG}"
chmod +x "${COMMAND_LOG}"
printf 'profile=%s\noutput_format=%s\n' "${PROFILE}" "${OUTPUT_FORMAT}" > "${RUN_DIR}/cli_options.env"
export PYTHONUNBUFFERED=1
export PATH="/opt/rocm/bin:/opt/rocm/core-10.1/bin:${PATH}"
export LD_LIBRARY_PATH="/opt/rocm/lib:/opt/rocm/lib64:${LD_LIBRARY_PATH:-}"
export BENCHMARK_READY_WAIT_SEC="${BENCHMARK_READY_WAIT_SEC:-1800}"
cp run_benchmark.sh "${RUN_DIR}/script.sh"
mask_environment "${RUN_DIR}/env_variables.txt"
: > "${RUN_DIR}/run.log"

run_collection() {
  log_section "Collection"
  isolate_repo_python
  export HF_HOME="${HF_HOME:-${HOME}/.cache/huggingface}"
  mkdir -p "${HF_HOME}"
  local server_cmd=""
  if ! "${PYTHON_BIN}" -c "import sglang" >/dev/null 2>&1; then
    die "sglang is not installed in .venv. Re-run: BENCHMARK_COMPILE_SGLANG=1 bash setup.sh --assume-yes"
  fi
  if ! "${PYTHON_BIN}" -c "import aiter" >/dev/null 2>&1; then
    die "aiter is not installed; AMD SGLang requires AITER."
  fi
  if [[ -f "${REPO_ROOT}/scripts/patch_aiter_gfx1250_optional.py" ]]; then
    "${PYTHON_BIN}" "${REPO_ROOT}/scripts/patch_aiter_gfx1250_optional.py" ||
      die "AITER gfx1250 optional-import patch failed."
  fi
  if [[ -f "${REPO_ROOT}/scripts/patch_triton_gluon_gfx1250_optional.py" ]]; then
    "${PYTHON_BIN}" "${REPO_ROOT}/scripts/patch_triton_gluon_gfx1250_optional.py" ||
      die "Triton gluon gfx1250 optional-import patch failed."
  fi
  export SGLANG_USE_AITER=1
  export PATH="/opt/rocm/bin:/opt/rocm/core-10.1/bin:${PATH}"
  export LD_LIBRARY_PATH="/opt/rocm/lib:/opt/rocm/lib64:${LD_LIBRARY_PATH:-}"
  export BENCHMARK_READY_WAIT_SEC="${BENCHMARK_READY_WAIT_SEC:-1800}"
  # Same AITER first-decode hang as 331: leftover lock_module_* plus the
  # default 300s watchdog. 430/431 set --tp/--mem-fraction-static; AMD
  # also needs --disable-cuda-graph and a longer watchdog.
  find "${VENV_ROOT:-${REPO_ROOT}/.venv}/lib" -name 'lock_module_*' -delete 2>/dev/null || true
  rm -f /tmp/aiter_configs/*.lock 2>/dev/null || true
  # A consolidated.safetensors cache is not a finished shard set. Download the
  # index shards, config.json and the tokenizer files, load AutoConfig and
  # AutoTokenizer from the snapshot, and launch with that snapshot directory,
  # not the repo id.
  sglang_model_path="$("${PYTHON_BIN}" scripts/prefetch_sglang_model.py --model-id "${MODEL_NAME}" | tail -n 1)"
  if [[ -z "${sglang_model_path}" || ! -d "${sglang_model_path}" ]]; then
    die "SGLang model prefetch did not return a snapshot with config.json, weights and a loadable tokenizer (see the [FAIL] line above)"
  fi
  # Restart the published clock after the download (as the vLLM runners do):
  # the ledger times the server start and the requests, not the network.
  mark_benchmark_measure_start
  server_cmd="${PYTHON_BIN} -m sglang.launch_server --model-path ${sglang_model_path} --dtype ${DTYPE} --port 30000 --host 127.0.0.1 --tp 1 --mem-fraction-static 0.8 --max-total-tokens ${MAX_TOTAL_TOKENS} --max-running-requests ${MAX_RUNNING_REQUESTS} --disable-cuda-graph --watchdog-timeout 1800 --enable-cache-report"
  log_run "${server_cmd}"
  echo "${server_cmd}" >> "${COMMAND_LOG}"
  bash -c "${server_cmd}" >> "${RUN_DIR}/server.log" 2>&1 &
  SERVER_PID="$!"
  wait_for_server "http://127.0.0.1:30000/v1/models"
  # The model is loaded and the server answers: setup ends, the benchmark clock
  # starts (TEMPLATE_00_141). Server start and model load count as setup on every run.
  mark_benchmark_measure_start
  local collect_cmd
  printf -v collect_cmd '%q ' "${PYTHON_BIN}" scripts/prompt_response_client.py --run-dir "${RUN_DIR}" --raw-file "${RAW_FILE}" --base-url "http://127.0.0.1:30000" --model-name "${MODEL_NAME}" --dtype "${DTYPE}" --input-len "${INPUT_LEN}" --output-len "${OUTPUT_LEN}" --num-prompts "${NUM_PROMPTS}" --seed "${SEED}" --streaming true --output-format "${OUTPUT_FORMAT}"
  log_run "${collect_cmd}"
  echo "${collect_cmd}" >> "${COMMAND_LOG}"
  if ! "${PYTHON_BIN}" scripts/prompt_response_client.py --run-dir "${RUN_DIR}" --raw-file "${RAW_FILE}" --base-url "http://127.0.0.1:30000" --model-name "${MODEL_NAME}" --dtype "${DTYPE}" --input-len "${INPUT_LEN}" --output-len "${OUTPUT_LEN}" --num-prompts "${NUM_PROMPTS}" --seed "${SEED}" --streaming true --output-format "${OUTPUT_FORMAT}" 2>&1 | tee -a "${RUN_DIR}/run.log" | hide_run_lines; then
    die "collection failed with status 1"
  fi
  cleanup_server
}

run_parse() {
  log_section "Parse"
  local parse_cmd
  printf -v parse_cmd '%q ' "${PYTHON_BIN}" scripts/parse_results.py --raw-file "${RAW_FILE}" --db "${REPO_ROOT}/results/benchmark.db" --config "${CONFIG_FILE}" --run-dir "${RUN_DIR}"
  log_run "${parse_cmd}"
  echo "${parse_cmd}" >> "${COMMAND_LOG}"
  "${PYTHON_BIN}" scripts/parse_results.py --raw-file "${RAW_FILE}" --db "${REPO_ROOT}/results/benchmark.db" --config "${CONFIG_FILE}" --run-dir "${RUN_DIR}" || die "parse failed"
}

run_validate() {
  log_section "Validation"
  local validate_cmd
  printf -v validate_cmd '%q ' "${PYTHON_BIN}" scripts/validate_results.py --db "${REPO_ROOT}/results/benchmark.db" --config "${CONFIG_FILE}"
  log_run "${validate_cmd}"
  echo "${validate_cmd}" >> "${COMMAND_LOG}"
  "${PYTHON_BIN}" scripts/validate_results.py --db "${REPO_ROOT}/results/benchmark.db" --config "${CONFIG_FILE}" || die "validation failed"
}

run_collection
run_parse
run_validate
record_benchmark_stop
# Stop the model server as soon as the run is measured. The EXIT trap alone kept it
# holding the GPU through the inventory, summary and ledger: amd-smi and rocminfo
# calls took 2-4 s each instead of under 1 s, and the inventory 65-68 s instead of
# 10-16 s (127-131 in TEMPLATE_00_140). The trap still covers a failed run.
cleanup_server
capture_journal_warnings "${RUN_DIR}" "${BENCHMARK_START_DATETIME}" "${STOP_TIME}"
bash scripts/collect_hw_sw_info.sh "${RUN_DIR}"
START_EPOCH="$(date -u -d "${BENCHMARK_START_DATETIME}" +%s)"
STOP_EPOCH="$(date -u -d "${STOP_TIME}" +%s)"  # Ledger keeps whole seconds. The summary prints tenths.
ELAPSED="$((STOP_EPOCH - START_EPOCH))"
(( ELAPSED < 0 )) && ELAPSED=0
if [[ "${QUIET}" -eq 0 ]]; then
  bash scripts/print_run_metadata.sh "${REPO_ROOT}" || true
  echo  # blank line before the summary
  echo "[INFO] ===== Benchmark Summary ====="
  echo "[INFO] Run ID: $(basename "${RUN_DIR}") | Status: ok | Samples: $(${PYTHON_BIN} -c 'import json; print(json.load(open("results/summary.json")).get("sample_count", 0))') | Profile: ${PROFILE} | Device: $(display_device)"
  print_benchmark_summary_commands
  echo "[INFO] Start time: ${BENCHMARK_START_DATETIME}"
  echo "[INFO] Stop time: ${STOP_TIME}"
  echo "[INFO] Elapsed time: $(benchmark_elapsed_display) sec"
  echo "[INFO] Artifacts: ${RUN_DIR}"
  echo "[INFO] SQLite DB: ${REPO_ROOT}/results/benchmark.db"
  echo "[INFO]"
  "${PYTHON_BIN}" scripts/print_metric_summary.py --definition benchmark_specification.json --summary results/summary.json || true
  echo "[INFO]"
fi
write_metrics_summary_txt

"${PYTHON_BIN}" scripts/update_runtime_ledger.py \
  --profile "${PROFILE}" --start-datetime "${BENCHMARK_START_DATETIME}" --total-runtime "${ELAPSED}" \
  --exit-code 0 --failure-stage ok --failure-detail "" --raw-run-dir "${RUN_DIR}" \
  --runtime-root "${REPO_ROOT}" \
  --run-benchmark-command-submitted "${BENCHMARK_RUN_COMMAND_SUBMITTED}" \
  --run-benchmark-command-fully-resolved "${BENCHMARK_RUN_COMMAND}" \
  --parameters-set "profile=${PROFILE};dtype=${DTYPE};input_len=${INPUT_LEN};output_len=${OUTPUT_LEN};num_prompts=${NUM_PROMPTS}" \
  --notes "validated run" \
  || printf '[WARN] Runtime ledger update failed\n' >&2
finish_benchmark_run
