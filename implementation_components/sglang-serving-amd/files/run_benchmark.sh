#!/usr/bin/env bash
# File: run_benchmark.sh
# Version: 1.0.0
# Description: Smoke uses tiny_sglang; baseline/extended launch python -m sglang.launch_server.
# Execution: bash run_benchmark.sh [--profile smoke|baseline|extended] [--validate]
# Options: --profile, --smoke, --baseline, --extended, --device, --phase, --phase1, --phase2, --phase3, --phase4, --raw-file, --config, --validate, --no-validate, --quiet, --log-level, --output-format, --save-options-file, --model-name, --dtype, --input-len, --output-len, --num-prompts, --concurrency, --seed, --specification, --matrix-definition, --help
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

Run smoke/baseline/extended profile
Run 1) Git provided Python SGLang inference LLM server (sglang.launch_server.py), and 2) User-created Python serving prompt benchmark (sglang.bench_serving.py / scripts/bench_serving.py).

Profiles:
  --profile <name>              Run profile: smoke|baseline|extended (default: smoke)
  --smoke                       Run smoke profile
  --baseline                    Run baseline profile
  --extended                    Run extended profile

Execution:
  --device <gpu|cpu>            Execution device (default: gpu)
  --phase <phaseN|N>            Run one phase (phase1|phase2|phase3|phase4, or 1-4)
  --phase1                      Collection
  --phase2                      Collection alias
  --phase3                      Parse only; requires --raw-file <path>
  --phase4                      Validation only
  --raw-file <path>             Existing raw file for --phase3
  --config <file>               Config file (default: config/benchmark_config.yaml)

Validation and logging:
  --validate                    Enable result validation (default)
  --no-validate                 Skip result validation
  --quiet                       Suppress nonessential stdout
  --log-level <level>           ERROR|WARN|INFO|DEBUG (default: INFO)
  --output-format <fmt>         Override config output_format
  --save-options-file <path>    Write resolved CLI options to PATH

Workload options:
  --model-name <name>           LLM weights
  --dtype <name>                Compute precision
  --input-len <n>               Prompt tokens
  --output-len <n>              Generated tokens
  --num-prompts <n>             Request count
  --concurrency <n>             In-flight requests
  --seed <n>                    RNG seed

Information:
  --specification               Print this workload's specification and exit
  --matrix-definition           Same as --specification
  --help                        Show this help and exit

Examples:
  bash run_benchmark.sh --profile smoke --validate
  bash run_benchmark.sh --baseline --device gpu
  bash run_benchmark.sh --phase3 --raw-file results/raw/<run>/raw_output.txt
  bash run_benchmark.sh --specification
  bash run_benchmark.sh --matrix-definition
USAGE
}

PROFILE="smoke"
DEVICE="gpu"
PHASE="all"
RAW_FILE=""
CONFIG_FILE="config/benchmark_config.yaml"
VALIDATE=1
QUIET=0
LOG_LEVEL_VALUE="INFO"
OUTPUT_FORMAT=""
SAVE_OPTIONS_FILE=""
MODEL_NAME=""
DTYPE=""
INPUT_LEN=""
OUTPUT_LEN=""
NUM_PROMPTS=""
CONCURRENCY=""
SEED=""
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
    --specification|--matrix-definition) python3 scripts/print_benchmark_definition.py; exit 0 ;;
  esac
done

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="${2:-}"; shift 2 ;;
    --smoke) PROFILE="smoke"; shift ;;
    --baseline) PROFILE="baseline"; shift ;;
    --extended) PROFILE="extended"; shift ;;
    --device) DEVICE="${2:-}"; shift 2 ;;
    --phase) PHASE="${2:-}"; shift 2 ;;
    --phase1|--phase2) PHASE="1"; shift ;;
    --phase3) PHASE="3"; shift ;;
    --phase4) PHASE="4"; shift ;;
    --raw-file) RAW_FILE="${2:-}"; shift 2 ;;
    --config) CONFIG_FILE="${2:-}"; shift 2 ;;
    --validate) VALIDATE=1; shift ;;
    --no-validate) VALIDATE=0; shift ;;
    --quiet) QUIET=1; shift ;;
    --log-level) LOG_LEVEL_VALUE="${2:-}"; shift 2 ;;
    --output-format) OUTPUT_FORMAT="${2:-}"; shift 2 ;;
    --save-options-file) SAVE_OPTIONS_FILE="${2:-}"; shift 2 ;;
    --model-name) MODEL_NAME="${2:-}"; shift 2 ;;
    --dtype) DTYPE="${2:-}"; shift 2 ;;
    --input-len) INPUT_LEN="${2:-}"; shift 2 ;;
    --output-len) OUTPUT_LEN="${2:-}"; shift 2 ;;
    --num-prompts) NUM_PROMPTS="${2:-}"; shift 2 ;;
    --concurrency) CONCURRENCY="${2:-}"; shift 2 ;;
    --seed) SEED="${2:-}"; shift 2 ;;
    --help|--specification|--matrix-definition) shift ;;
    *) die "Unknown option: $1" ;;
  esac
done

case "${PHASE}" in
  all|phase1|phase2|phase3|phase4|1|2|3|4) ;;
  *) die "Unsupported --phase value: ${PHASE}" ;;
esac
if [[ "${PHASE}" == phase* ]]; then PHASE="${PHASE#phase}"; fi

set_log_level "${LOG_LEVEL_VALUE}"
begin_benchmark_run "${PROFILE}"
if [[ "${PHASE}" != "3" && "${PHASE}" != "4" ]]; then
  bash scripts/ensure_setup.sh --profile "${PROFILE}"
fi
mark_benchmark_measure_start
PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
[[ -x "${PYTHON_BIN}" ]] || PYTHON_BIN="${BENCHMARK_PYTHON:-python3}"
yaml_get() {
  "${PYTHON_BIN}" - "${CONFIG_FILE}" "${PROFILE}" "$1" <<'PY'
import sys
from pathlib import Path
import yaml
config, profile, key = sys.argv[1], sys.argv[2], sys.argv[3]
data = yaml.safe_load(Path(config).read_text(encoding="utf-8")) or {}
value = (data.get("sweep") or {}).get(key, "")
if isinstance(value, dict):
    value = value.get(profile, "")
print("" if value is None else value)
PY
}
enable_default() {
  local raw="$1"
  local fallback="$2"
  case "${raw,,}" in
    true|yes|"") printf '%s' "${fallback}" ;;
    *) printf '%s' "${raw}" ;;
  esac
}
MODEL_NAME="${MODEL_NAME:-$(enable_default "$(yaml_get model_name)" "mistralai/Mistral-7B-v0.3")}"
DTYPE="${DTYPE:-$(yaml_get dtype)}"
TENSOR_PARALLEL_SIZE="$(enable_default "$(yaml_get tensor_parallel_size)" "1")"
SCHEDULE_POLICY="$(enable_default "$(yaml_get schedule_policy)" "fcfs")"
PROMPT_SOURCE="$(enable_default "$(yaml_get prompt_source)" "synthetic")"
INPUT_LEN="${INPUT_LEN:-$(yaml_get input_len)}"
OUTPUT_LEN="${OUTPUT_LEN:-$(yaml_get output_len)}"
MAX_TOTAL_TOKENS="${MAX_TOTAL_TOKENS:-$(yaml_get max_total_tokens)}"
MAX_RUNNING_REQUESTS="$(enable_default "$(yaml_get max_running_requests)" "2")"
MAX_CONCURRENCY="${CONCURRENCY:-$(yaml_get max_concurrency)}"
REQUEST_RATE="$(enable_default "$(yaml_get request_rate)" "inf")"
NUM_PROMPTS="${NUM_PROMPTS:-$(yaml_get num_prompts)}"
BACKEND="$(enable_default "$(yaml_get backend)" "sglang")"
DATASET_NAME="$(enable_default "$(yaml_get dataset_name)" "synthetic")"
SEED="${SEED:-42}"
OUTPUT_FORMAT="${OUTPUT_FORMAT:-csv}"
BENCHMARK_RUN_COMMAND="bash run_benchmark.sh --${PROFILE}"
[[ "${VALIDATE}" -eq 1 ]] && BENCHMARK_RUN_COMMAND+=" --validate"
BENCHMARK_RUN_COMMAND+=" --model-name $(printf %q "${MODEL_NAME}") --dtype ${DTYPE} --input-len ${INPUT_LEN} --output-len ${OUTPUT_LEN} --num-prompts ${NUM_PROMPTS} --max-concurrency ${MAX_CONCURRENCY} --max-total-tokens ${MAX_TOTAL_TOKENS} --max-running-requests ${MAX_RUNNING_REQUESTS} --schedule-policy ${SCHEDULE_POLICY} --request-rate ${REQUEST_RATE} --seed ${SEED} --backend ${BACKEND} --dataset-name ${DATASET_NAME}"
set_benchmark_run_command "${BENCHMARK_RUN_COMMAND}"
HOSTNAME_VALUE="$(hostname -s 2>/dev/null || hostname)"
STAMP="$(date -u +"%Y%m%d_%H%M%S")"
if [[ -z "${RAW_FILE}" ]]; then
  RUN_DIR="${REPO_ROOT}/results/raw/${STAMP}_${REPO_NAME}_${HOSTNAME_VALUE}"
  mkdir -p "${RUN_DIR}"
  RAW_FILE="${RUN_DIR}/raw_output.txt"
else
  RUN_DIR="$(cd "$(dirname "${RAW_FILE}")" && pwd)"
fi
set_benchmark_run_dir "${RUN_DIR}"
COMMAND_LOG="${RUN_DIR}/commands_executed.sh"
{ echo "#!/usr/bin/env bash"; echo "set -euo pipefail"; } > "${COMMAND_LOG}"
chmod +x "${COMMAND_LOG}"
[[ -n "${SAVE_OPTIONS_FILE}" ]] && printf 'profile=%s\noutput_format=%s\n' "${PROFILE}" "${OUTPUT_FORMAT}" > "${SAVE_OPTIONS_FILE}"
printf 'profile=%s\ndevice=%s\noutput_format=%s\n' "${PROFILE}" "${DEVICE}" "${OUTPUT_FORMAT}" > "${RUN_DIR}/cli_options.env"
export PYTHONUNBUFFERED=1
cp run_benchmark.sh "${RUN_DIR}/script.sh"
mask_environment "${RUN_DIR}/env_variables.txt"
: > "${RUN_DIR}/run.log"

run_collection() {
  log_section "Collection"
  isolate_repo_python
  export HF_HOME="${HF_HOME:-${HOME}/.cache/huggingface}"
  mkdir -p "${HF_HOME}"
  local server_cmd=""
  if [[ "${PROFILE}" == "smoke" ]]; then
    server_cmd="${PYTHON_BIN} scripts/tiny_sglang_server.py"
  else
    if ! "${PYTHON_BIN}" -c "import sglang" >/dev/null 2>&1; then
      die "sglang is not installed in .venv. Re-run: BENCHMARK_COMPILE_SGLANG=1 bash setup.sh --assume-yes"
    fi
    if ! "${PYTHON_BIN}" -c "import aiter" >/dev/null 2>&1; then
      die "aiter is not installed; AMD SGLang baseline/extended require AITER."
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
    # A leftover lock_module_* from a killed JIT makes the first decode wait
    # until the 300s scheduler watchdog kills the server.
    find "${VENV_ROOT:-${REPO_ROOT}/.venv}/lib" -name 'lock_module_*' -delete 2>/dev/null || true
    rm -f /tmp/aiter_configs/*.lock 2>/dev/null || true
    # A consolidated.safetensors cache is not a finished shard set. Download the
    # index shards and launch with that snapshot directory, not the repo id.
    sglang_model_path="$("${PYTHON_BIN}" scripts/prefetch_sglang_model.py --model-id "${MODEL_NAME}" | tail -n 1)"
    if [[ -z "${sglang_model_path}" || ! -d "${sglang_model_path}" ]]; then
      die "SGLang shard prefetch did not return a snapshot directory"
    fi
    server_cmd="${PYTHON_BIN} -m sglang.launch_server --model-path ${sglang_model_path} --dtype ${DTYPE} --port 30000 --host 127.0.0.1 --tp 1 --mem-fraction-static 0.8 --schedule-policy ${SCHEDULE_POLICY} --max-total-tokens ${MAX_TOTAL_TOKENS} --max-running-requests ${MAX_RUNNING_REQUESTS} --disable-cuda-graph --watchdog-timeout 1800"
  fi
  echo "[RUN] ${server_cmd}"
  echo "${server_cmd}" >> "${COMMAND_LOG}"
  bash -c "${server_cmd}" >> "${RUN_DIR}/server.log" 2>&1 &
  SERVER_PID="$!"
  wait_for_server "http://127.0.0.1:30000/v1/models"
  local collect_cmd
  printf -v collect_cmd '%q ' "${PYTHON_BIN}" scripts/bench_serving.py --run-dir "${RUN_DIR}" --base-url "http://127.0.0.1:30000" --model-name "${MODEL_NAME}" --dtype "${DTYPE}" --tensor-parallel-size "${TENSOR_PARALLEL_SIZE}" --schedule-policy "${SCHEDULE_POLICY}" --prompt-source "${PROMPT_SOURCE}" --input-len "${INPUT_LEN}" --output-len "${OUTPUT_LEN}" --max-total-tokens "${MAX_TOTAL_TOKENS}" --max-running-requests "${MAX_RUNNING_REQUESTS}" --max-concurrency "${MAX_CONCURRENCY}" --request-rate "${REQUEST_RATE}" --num-prompts "${NUM_PROMPTS}" --backend "${BACKEND}" --dataset-name "${DATASET_NAME}" --seed "${SEED}"
  echo "[RUN] ${collect_cmd}"
  echo "${collect_cmd}" >> "${COMMAND_LOG}"
  if ! "${PYTHON_BIN}" scripts/bench_serving.py --run-dir "${RUN_DIR}" --base-url "http://127.0.0.1:30000" --model-name "${MODEL_NAME}" --dtype "${DTYPE}" --tensor-parallel-size "${TENSOR_PARALLEL_SIZE}" --schedule-policy "${SCHEDULE_POLICY}" --prompt-source "${PROMPT_SOURCE}" --input-len "${INPUT_LEN}" --output-len "${OUTPUT_LEN}" --max-total-tokens "${MAX_TOTAL_TOKENS}" --max-running-requests "${MAX_RUNNING_REQUESTS}" --max-concurrency "${MAX_CONCURRENCY}" --request-rate "${REQUEST_RATE}" --num-prompts "${NUM_PROMPTS}" --backend "${BACKEND}" --dataset-name "${DATASET_NAME}" --seed "${SEED}" 2>&1 | tee -a "${RUN_DIR}/run.log"; then
    die "collection failed with status 1"
  fi
  cleanup_server
}
run_parse() {
  log_section "Parse"
  local parse_cmd
  printf -v parse_cmd '%q ' "${PYTHON_BIN}" scripts/parse_results.py --raw-file "${RAW_FILE}" --db "${REPO_ROOT}/results/benchmark.db" --summary "${REPO_ROOT}/results/summary.json" --definition "${REPO_ROOT}/benchmark_specification.json" --run-dir "${RUN_DIR}"
  echo "[RUN] ${parse_cmd}"
  echo "${parse_cmd}" >> "${COMMAND_LOG}"
  "${PYTHON_BIN}" scripts/parse_results.py --raw-file "${RAW_FILE}" --db "${REPO_ROOT}/results/benchmark.db" --summary "${REPO_ROOT}/results/summary.json" --definition "${REPO_ROOT}/benchmark_specification.json" --run-dir "${RUN_DIR}" || die "parse failed"
}
run_validate() {
  log_section "Validation"
  local validate_cmd
  printf -v validate_cmd '%q ' "${PYTHON_BIN}" scripts/validate_results.py --db "${REPO_ROOT}/results/benchmark.db" --config "${CONFIG_FILE}"
  echo "[RUN] ${validate_cmd}"
  echo "${validate_cmd}" >> "${COMMAND_LOG}"
  "${PYTHON_BIN}" scripts/validate_results.py --db "${REPO_ROOT}/results/benchmark.db" --config "${CONFIG_FILE}" || die "validation failed"
}
case "${PHASE}" in
  all|1|2) run_collection; run_parse; [[ "${VALIDATE}" -eq 1 ]] && run_validate ;;
  3) [[ -n "${RAW_FILE}" && -f "${RAW_FILE}" ]] || die "--phase3 requires --raw-file <existing file>"; run_parse ;;
  4) run_validate ;;
esac
record_benchmark_stop
capture_journal_warnings "${RUN_DIR}" "${BENCHMARK_START_DATETIME}" "${STOP_TIME}"
bash scripts/collect_hw_sw_info.sh "${RUN_DIR}"
START_EPOCH="$(date -u -d "${BENCHMARK_START_DATETIME}" +%s)"
STOP_EPOCH="$(date -u -d "${STOP_TIME}" +%s)"  # Ledger keeps whole seconds. The summary prints tenths.
ELAPSED="$((STOP_EPOCH - START_EPOCH))"
(( ELAPSED < 0 )) && ELAPSED=0
if [[ "${QUIET}" -eq 0 ]]; then
  bash scripts/print_run_metadata.sh "${REPO_ROOT}" || true
  echo "[INFO] ===== Benchmark Summary ====="
  echo "[INFO] Run ID: $(basename "${RUN_DIR}") | Status: ok | Samples: $(${PYTHON_BIN} -c 'import json; print(json.load(open("results/summary.json"))["sample_count"])') | Profile: ${PROFILE} | Device: $(display_device)"
  print_benchmark_summary_commands
  echo "[INFO] Start time: ${BENCHMARK_START_DATETIME}"
  echo "[INFO] Stop time: ${STOP_TIME}"
  echo "[INFO] Elapsed time: $(benchmark_elapsed_display) sec"
  echo "[INFO] Artifacts: ${RUN_DIR}"
  echo "[INFO] SQLite DB: ${REPO_ROOT}/results/benchmark.db"
  echo "[INFO]"
  "${PYTHON_BIN}" scripts/print_metric_summary.py --definition benchmark_specification.json --summary results/summary.json
  echo "[INFO]"
fi
write_metrics_summary_txt

"${PYTHON_BIN}" scripts/update_runtime_ledger.py \
  --profile "${PROFILE}" --start-datetime "${BENCHMARK_START_DATETIME}" --total-runtime "${ELAPSED}" \
  --exit-code 0 --failure-stage ok --failure-detail "" --raw-run-dir "${RUN_DIR}" \
  --runtime-root "${REPO_ROOT}" \
  --run-benchmark-command-submitted "${BENCHMARK_RUN_COMMAND_SUBMITTED}" \
  --run-benchmark-command-fully-resolved "${BENCHMARK_RUN_COMMAND}" \
  --parameters-set "profile=${PROFILE};model=${MODEL_NAME};dtype=${DTYPE};input_len=${INPUT_LEN};output_len=${OUTPUT_LEN};num_prompts=${NUM_PROMPTS};concurrency=${MAX_CONCURRENCY}" --notes "validated run" \
  || printf '[WARN] Runtime ledger update failed\n' >&2
finish_benchmark_run
