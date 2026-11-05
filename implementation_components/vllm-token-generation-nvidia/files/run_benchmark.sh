#!/usr/bin/env bash
# File: run_benchmark.sh
# Version: 1.0.0
# Description: Every profile launches a real vLLM OpenAI-compatible server.
# Execution: bash run_benchmark.sh [--smoke|--baseline|--extended]
# Options: --smoke, --baseline, --extended, --config, --quiet, --log-level, --serving-engine, --model-name, --dtype, --kv-cache-dtype, --gpu-memory-utilization, --max-model-len, --dataset-name, --input-len, --output-len, --num-prompts, --concurrency, --seed, --specification, --help
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_NAME="$(basename "${REPO_ROOT}")"
cd "${REPO_ROOT}"
# FlashInfer JIT looks up ninja on PATH. setup.sh installs it into .venv,
# and this script otherwise replaces PATH with CUDA bins only.
export PATH="${REPO_ROOT}/.venv/bin:/usr/local/cuda/bin:/usr/local/cuda-12.6/bin:${PATH}"
# shellcheck disable=SC1091
source scripts/lib/common.sh
capture_benchmark_run_command_submitted "$@"

usage() {
  cat <<'USAGE'
Usage: bash run_benchmark.sh [OPTIONS]

Run smoke/baseline/extended profile
Run 1) Git provided Python vLLM inference server (vllm.entrypoints.openai.api_server.py), and 2) User-created Python http prompt-serving benchmark (benchmark_serving.py).

Profiles (default: --smoke):
  --smoke                       Run smoke profile
  --baseline                    Run baseline profile
  --extended                    Run extended profile

Parameters (override the profile's value):
  --serving-engine <name>       Inference server
  --model-name <name>           LLM weights
  --dtype <name>                Compute precision
  --kv-cache-dtype <name>       KV storage precision
  --gpu-memory-utilization <n>  GPU memory fraction
  --max-model-len <n>           Context window
  --dataset-name <name>         Prompt source
  --input-len <n>               Prompt tokens
  --output-len <n>              Generated tokens
  --num-prompts <n>             Request count
  --concurrency <n>             In-flight requests
  --seed <n>                    RNG seed

General options:
  --config <file>               Config file (default: config/benchmark_config.yaml)
  --quiet                       Suppress nonessential stdout
  --log-level <level>           ERROR|WARN|INFO|DEBUG (default: INFO)
  --specification               Print this workload's specification and exit
  --help                        Show this help and exit

Examples:
  bash run_benchmark.sh --smoke
  bash run_benchmark.sh --baseline
  bash run_benchmark.sh --extended
  bash run_benchmark.sh --baseline --max-concurrency 4
USAGE
}

PROFILE="smoke"
CONFIG_FILE="config/benchmark_config.yaml"
QUIET=0
LOG_LEVEL_VALUE="INFO"
SERVING_ENGINE=""
MODEL_NAME=""
DTYPE=""
KV_CACHE_DTYPE=""
GPU_MEMORY_UTILIZATION=""
MAX_MODEL_LEN=""
DATASET_NAME=""
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
    --specification) python3 scripts/print_benchmark_definition.py; exit 0 ;;
  esac
done

while [[ $# -gt 0 ]]; do
  case "$1" in
    --smoke) PROFILE="smoke"; shift ;;
    --baseline) PROFILE="baseline"; shift ;;
    --extended) PROFILE="extended"; shift ;;
    --config) CONFIG_FILE="${2:-}"; shift 2 ;;
    --validate) shift ;;  # ignored; result validation always runs
    --quiet) QUIET=1; shift ;;
    --log-level) LOG_LEVEL_VALUE="${2:-}"; shift 2 ;;
    --serving-engine) SERVING_ENGINE="${2:-}"; shift 2 ;;
    --model-name) MODEL_NAME="${2:-}"; shift 2 ;;
    --dtype) DTYPE="${2:-}"; shift 2 ;;
    --kv-cache-dtype) KV_CACHE_DTYPE="${2:-}"; shift 2 ;;
    --gpu-memory-utilization) GPU_MEMORY_UTILIZATION="${2:-}"; shift 2 ;;
    --max-model-len) MAX_MODEL_LEN="${2:-}"; shift 2 ;;
    --dataset-name) DATASET_NAME="${2:-}"; shift 2 ;;
    --input-len) INPUT_LEN="${2:-}"; shift 2 ;;
    --output-len) OUTPUT_LEN="${2:-}"; shift 2 ;;
    --num-prompts) NUM_PROMPTS="${2:-}"; shift 2 ;;
    --concurrency) CONCURRENCY="${2:-}"; shift 2 ;;
    --seed) SEED="${2:-}"; shift 2 ;;
    --help|--specification) shift ;;
    *) die "Unknown option: $1" ;;
  esac
done


set_log_level "${LOG_LEVEL_VALUE}"
begin_benchmark_run "${PROFILE}"
BENCHMARK_RUN_COMMAND="bash run_benchmark.sh --${PROFILE}"
set_benchmark_run_command "${BENCHMARK_RUN_COMMAND}"
bash scripts/ensure_setup.sh
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
MODEL_NAME="${MODEL_NAME:-$(yaml_get model_name)}"
DTYPE="${DTYPE:-$(yaml_get dtype)}"
TENSOR_PARALLEL_SIZE="${TENSOR_PARALLEL_SIZE:-$(yaml_get tensor_parallel_size)}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-$(yaml_get gpu_memory_utilization)}"
PROMPT_SOURCE="${PROMPT_SOURCE:-$(yaml_get prompt_source)}"
PROMPT_SOURCE="${PROMPT_SOURCE:-synthetic}"
INPUT_LEN="${INPUT_LEN:-$(yaml_get input_len)}"
OUTPUT_LEN="${OUTPUT_LEN:-$(yaml_get output_len)}"
MAX_NUM_SEQS="${MAX_NUM_SEQS:-$(yaml_get max_num_seqs)}"
MAX_CONCURRENCY="${MAX_CONCURRENCY:-$(yaml_get max_concurrency)}"
REQUEST_RATE="${REQUEST_RATE:-$(yaml_get request_rate)}"
OUTPUT_FORMAT="${OUTPUT_FORMAT:-csv}"
BENCHMARK_RUN_COMMAND="bash run_benchmark.sh --${PROFILE}"
BENCHMARK_RUN_COMMAND+=" --model-name ${MODEL_NAME} --dtype ${DTYPE} --tensor-parallel-size ${TENSOR_PARALLEL_SIZE} --gpu-memory-utilization ${GPU_MEMORY_UTILIZATION} --input-len ${INPUT_LEN} --output-len ${OUTPUT_LEN} --max-concurrency ${MAX_CONCURRENCY}"
set_benchmark_run_command "${BENCHMARK_RUN_COMMAND}"
HOSTNAME_VALUE="$(hostname -s 2>/dev/null || hostname)"
STAMP="$(date -u +"%Y%m%d_%H%M%S")"
RUN_DIR="${REPO_ROOT}/results/raw/${STAMP}_${REPO_NAME}_${HOSTNAME_VALUE}"
mkdir -p "${RUN_DIR}"
RAW_FILE="${RUN_DIR}/raw_output.txt"
set_benchmark_run_dir "${RUN_DIR}"
COMMAND_LOG="${RUN_DIR}/commands_executed.sh"
{ echo "#!/usr/bin/env bash"; echo "set -euo pipefail"; } > "${COMMAND_LOG}"
chmod +x "${COMMAND_LOG}"
printf 'profile=%s\noutput_format=%s\n' "${PROFILE}" "${OUTPUT_FORMAT}" > "${RUN_DIR}/cli_options.env"
export PYTHONUNBUFFERED=1
cp run_benchmark.sh "${RUN_DIR}/script.sh"
mask_environment "${RUN_DIR}/env_variables.txt"
: > "${RUN_DIR}/run.log"

run_collection() {
  log_section "Collection"
  export HF_HOME="${HF_HOME:-${REPO_ROOT}/.cache/huggingface}"
  mkdir -p "${HF_HOME}"
  local server_cmd=""
  TOKENIZER_CONTEXT_SLACK="${TOKENIZER_CONTEXT_SLACK:-64}"
  MISTRAL_NATIVE_MAX_MODEL_LEN="${MISTRAL_NATIVE_MAX_MODEL_LEN:-32768}"
  local max_model_len=$((INPUT_LEN + OUTPUT_LEN + TOKENIZER_CONTEXT_SLACK))
  if (( max_model_len > MISTRAL_NATIVE_MAX_MODEL_LEN )); then
    max_model_len="${MISTRAL_NATIVE_MAX_MODEL_LEN}"
  fi
  MAX_MODEL_LEN="${MAX_MODEL_LEN:-${max_model_len}}"
  export BENCHMARK_READY_WAIT_SEC="${BENCHMARK_READY_WAIT_SEC:-1800}"
  server_cmd="${PYTHON_BIN} -m vllm.entrypoints.openai.api_server --model ${MODEL_NAME} --dtype ${DTYPE} --tensor-parallel-size ${TENSOR_PARALLEL_SIZE} --gpu-memory-utilization ${GPU_MEMORY_UTILIZATION} --max-model-len ${MAX_MODEL_LEN} --max-num-seqs ${MAX_NUM_SEQS} --port 8000 --host 127.0.0.1"
  echo "[RUN] ${server_cmd}"
  echo "${server_cmd}" >> "${COMMAND_LOG}"
  bash -c "${server_cmd}" >> "${RUN_DIR}/server.log" 2>&1 &
  SERVER_PID="$!"
  wait_for_server "http://127.0.0.1:8000/v1/models"
  local collect_cmd
  printf -v collect_cmd '%q ' "${PYTHON_BIN}" scripts/benchmark_serving.py --run-dir "${RUN_DIR}" --base-url "http://127.0.0.1:8000" --model-name "${MODEL_NAME}" --dtype "${DTYPE}" --tensor-parallel-size "${TENSOR_PARALLEL_SIZE}" --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}" --prompt-source "${PROMPT_SOURCE}" --input-len "${INPUT_LEN}" --output-len "${OUTPUT_LEN}" --max-model-len "${MAX_MODEL_LEN}" --max-num-seqs "${MAX_NUM_SEQS}" --max-concurrency "${MAX_CONCURRENCY}" --request-rate "${REQUEST_RATE}" --output-format "${OUTPUT_FORMAT}"
  echo "[RUN] ${collect_cmd}"
  echo "${collect_cmd}" >> "${COMMAND_LOG}"
  if ! "${PYTHON_BIN}" scripts/benchmark_serving.py --run-dir "${RUN_DIR}" --base-url "http://127.0.0.1:8000" --model-name "${MODEL_NAME}" --dtype "${DTYPE}" --tensor-parallel-size "${TENSOR_PARALLEL_SIZE}" --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}" --prompt-source "${PROMPT_SOURCE}" --input-len "${INPUT_LEN}" --output-len "${OUTPUT_LEN}" --max-model-len "${MAX_MODEL_LEN}" --max-num-seqs "${MAX_NUM_SEQS}" --max-concurrency "${MAX_CONCURRENCY}" --request-rate "${REQUEST_RATE}" --output-format "${OUTPUT_FORMAT}" 2>&1 | tee -a "${RUN_DIR}/run.log"; then
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
run_collection
run_parse
run_validate
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
LOADED_MODEL_ID="$(cat "${RUN_DIR}/loaded_model_id.txt" 2>/dev/null || printf 'unknown')"
"${PYTHON_BIN}" scripts/update_runtime_ledger.py \
  --profile "${PROFILE}" --start-datetime "${BENCHMARK_START_DATETIME}" --total-runtime "${ELAPSED}" \
  --exit-code 0 --failure-stage ok --failure-detail "" --raw-run-dir "${RUN_DIR}" \
  --runtime-root "${REPO_ROOT}" \
  --run-benchmark-command-submitted "${BENCHMARK_RUN_COMMAND_SUBMITTED}" \
  --run-benchmark-command-fully-resolved "${BENCHMARK_RUN_COMMAND}" \
  --parameters-set "profile=${PROFILE};model=${MODEL_NAME};dtype=${DTYPE};input_len=${INPUT_LEN};output_len=${OUTPUT_LEN}" --notes "validated run; loaded_model_id=${LOADED_MODEL_ID}" \
  || printf '[WARN] Runtime ledger update failed\n' >&2
finish_benchmark_run
