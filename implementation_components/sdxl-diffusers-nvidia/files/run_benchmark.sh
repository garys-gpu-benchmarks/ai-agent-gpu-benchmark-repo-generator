#!/usr/bin/env bash
# File: run_benchmark.sh
# Description: Every profile loads real SDXL; smoke uses reduced resolution and steps.
# Execution: bash run_benchmark.sh [--profile smoke|baseline|extended] [--validate]
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

Measure Stable Diffusion XL inference latency, images/sec, and peak VRAM.
Every profile loads stabilityai/stable-diffusion-xl-base-1.0.
Smoke uses reduced resolution and steps, but never substitutes a tiny model.

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
  --model-name <name>           SDXL variant token (sdxl-base-1.0)
  --precision <token>           Weight and activation precision (fp16)
  --scheduler <name>            Denoising scheduler (euler)
  --prompt-source <name>        Prompt generation method (synthetic)
  --prompt-len <token>          Synthetic prompt-length token (true)
  --image-resolution <n>        Output image edge length
  --batch-size <token>          Images per step token (true means 1)
  --num-images <n>              Images generated in the timed pass
  --num-inference-steps <n>     Denoising steps per image
  --guidance-scale <n>          Classifier-free guidance scale (0.0)
  --seed <n>                    RNG seed (42)

Information:
  --specification               Print this workload's specification and exit
  --matrix-definition           Same as --specification
  --help                        Show this help and exit
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
PRECISION=""
SCHEDULER=""
PROMPT_SOURCE=""
PROMPT_LEN=""
IMAGE_RESOLUTION=""
BATCH_SIZE=""
NUM_IMAGES=""
NUM_INFERENCE_STEPS=""
GUIDANCE_SCALE=""
SEED=""

for _help_arg in "$@"; do
  case "${_help_arg}" in
    --help) usage; exit 0 ;;
    --specification|--matrix-definition|--benchmark-specification|--benchmark-definition)
      python3 scripts/print_benchmark_definition.py
      exit 0
      ;;
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
    --precision) PRECISION="${2:-}"; shift 2 ;;
    --scheduler) SCHEDULER="${2:-}"; shift 2 ;;
    --prompt-source) PROMPT_SOURCE="${2:-}"; shift 2 ;;
    --prompt-len) PROMPT_LEN="${2:-}"; shift 2 ;;
    --image-resolution) IMAGE_RESOLUTION="${2:-}"; shift 2 ;;
    --batch-size) BATCH_SIZE="${2:-}"; shift 2 ;;
    --num-images) NUM_IMAGES="${2:-}"; shift 2 ;;
    --num-inference-steps) NUM_INFERENCE_STEPS="${2:-}"; shift 2 ;;
    --guidance-scale) GUIDANCE_SCALE="${2:-}"; shift 2 ;;
    --seed) SEED="${2:-}"; shift 2 ;;
    --help|--specification|--matrix-definition|--benchmark-specification|--benchmark-definition) shift ;;
    --remote|--ssh|--host) die "This repository is local-only and does not support remote execution." ;;
    *) die "Unknown option: $1" ;;
  esac
done

case "${PHASE}" in
  all|phase1|phase2|phase3|phase4|1|2|3|4) ;;
  *) die "Unsupported --phase value: ${PHASE}" ;;
esac
if [[ "${PHASE}" == phase* ]]; then PHASE="${PHASE#phase}"; fi
if [[ "${DEVICE}" == "cpu" ]]; then
  die "This SDXL inference benchmark requires --device gpu."
fi

set_log_level "${LOG_LEVEL_VALUE}"
begin_benchmark_run "${PROFILE}"
if [[ "${PHASE}" != "3" && "${PHASE}" != "4" ]]; then
  bash scripts/ensure_setup.sh
fi
mark_benchmark_measure_start
# /usr/local/cuda first: it is the toolkit setup.sh installed and recorded. A
# leftover /usr/local/cuda-12.6 ahead of it would run a different nvcc.
export PATH="/usr/local/cuda/bin:/usr/local/cuda-12.8/bin:/usr/local/cuda-13.3/bin:/usr/local/cuda-12.6/bin:${PATH}"
PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
[[ -x "${PYTHON_BIN}" ]] || die "Missing ${PYTHON_BIN}; run setup.sh first."

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
PRECISION="${PRECISION:-$(yaml_get precision)}"
SCHEDULER="${SCHEDULER:-$(yaml_get scheduler)}"
PROMPT_SOURCE="${PROMPT_SOURCE:-$(yaml_get prompt_source)}"
PROMPT_LEN="${PROMPT_LEN:-$(yaml_get prompt_len)}"
IMAGE_RESOLUTION="${IMAGE_RESOLUTION:-$(yaml_get image_resolution)}"
BATCH_SIZE="${BATCH_SIZE:-$(yaml_get batch_size)}"
NUM_IMAGES="${NUM_IMAGES:-$(yaml_get num_images)}"
NUM_INFERENCE_STEPS="${NUM_INFERENCE_STEPS:-$(yaml_get num_inference_steps)}"
GUIDANCE_SCALE="${GUIDANCE_SCALE:-$(yaml_get guidance_scale)}"
SEED="${SEED:-$(yaml_get seed)}"
OUTPUT_FORMAT="${OUTPUT_FORMAT:-csv}"
BACKEND="sdxl"
IMAGE_RESOLUTION="${IMAGE_RESOLUTION:-256}"
NUM_IMAGES="${NUM_IMAGES:-2}"
NUM_INFERENCE_STEPS="${NUM_INFERENCE_STEPS:-2}"
(( IMAGE_RESOLUTION < 256 )) && IMAGE_RESOLUTION=256
(( NUM_IMAGES < 2 )) && NUM_IMAGES=2
(( NUM_INFERENCE_STEPS < 2 )) && NUM_INFERENCE_STEPS=2

BENCHMARK_RUN_COMMAND="bash run_benchmark.sh --profile ${PROFILE}"
[[ "${VALIDATE}" -eq 1 ]] && BENCHMARK_RUN_COMMAND+=" --validate" || BENCHMARK_RUN_COMMAND+=" --no-validate"
BENCHMARK_RUN_COMMAND+=" --model-name ${MODEL_NAME} --precision ${PRECISION} --scheduler ${SCHEDULER}"
BENCHMARK_RUN_COMMAND+=" --prompt-source ${PROMPT_SOURCE} --prompt-len ${PROMPT_LEN}"
BENCHMARK_RUN_COMMAND+=" --image-resolution ${IMAGE_RESOLUTION} --batch-size ${BATCH_SIZE}"
BENCHMARK_RUN_COMMAND+=" --num-images ${NUM_IMAGES} --num-inference-steps ${NUM_INFERENCE_STEPS}"
BENCHMARK_RUN_COMMAND+=" --guidance-scale ${GUIDANCE_SCALE} --seed ${SEED}"
set_benchmark_run_command "${BENCHMARK_RUN_COMMAND}"

HOSTNAME_VALUE="$(hostname -s 2>/dev/null || hostname)"
STAMP="$(date -u +"%Y%m%d_%H%M%S")"
if [[ -z "${RAW_FILE}" ]]; then
  RUN_DIR="${REPO_ROOT}/results/raw/${STAMP}_${REPO_NAME}_${HOSTNAME_VALUE}"
  mkdir -p "${RUN_DIR}"
  RAW_FILE="${RUN_DIR}/sdxl_infer_raw.txt"
else
  RUN_DIR="$(cd "$(dirname "${RAW_FILE}")" && pwd)"
fi
set_benchmark_run_dir "${RUN_DIR}"
COMMAND_LOG="${RUN_DIR}/commands_executed.sh"
{ echo "#!/usr/bin/env bash"; echo "set -euo pipefail"; } > "${COMMAND_LOG}"
chmod +x "${COMMAND_LOG}"
[[ -n "${SAVE_OPTIONS_FILE}" ]] && printf 'profile=%s\noutput_format=%s\n' "${PROFILE}" "${OUTPUT_FORMAT}" > "${SAVE_OPTIONS_FILE}"
{
  echo "profile=${PROFILE}"
  echo "device=${DEVICE}"
  echo "backend=${BACKEND}"
  echo "model_name=${MODEL_NAME}"
  echo "precision=${PRECISION}"
  echo "scheduler=${SCHEDULER}"
  echo "prompt_source=${PROMPT_SOURCE}"
  echo "prompt_len=${PROMPT_LEN}"
  echo "image_resolution=${IMAGE_RESOLUTION}"
  echo "batch_size=${BATCH_SIZE}"
  echo "num_images=${NUM_IMAGES}"
  echo "num_inference_steps=${NUM_INFERENCE_STEPS}"
  echo "guidance_scale=${GUIDANCE_SCALE}"
  echo "seed=${SEED}"
} > "${RUN_DIR}/cli_options.env"
export PYTHONUNBUFFERED=1
export HF_HOME="${HF_HOME:-${REPO_ROOT}/.cache/huggingface}"
mkdir -p "${HF_HOME}"
cp run_benchmark.sh "${RUN_DIR}/script.sh"
mask_environment "${RUN_DIR}/env_variables.txt"

run_collection() {
  log_section "Collection"
  if [[ "${BACKEND}" == "sdxl" ]]; then
    echo "[RUN] bash scripts/install_sdxl_python.sh --prefetch"
    echo "bash scripts/install_sdxl_python.sh --prefetch" >> "${COMMAND_LOG}"
    bash scripts/install_sdxl_python.sh --prefetch
    export HF_HUB_OFFLINE=1
  fi
  local collect_cmd
  printf -v collect_cmd '%q ' "${PYTHON_BIN}" scripts/collect_sdxl.py \
    --output "${RUN_DIR}/metrics.csv" --config "${CONFIG_FILE}" --profile "${PROFILE}" \
    --backend "${BACKEND}" --model-name "${MODEL_NAME}" --precision "${PRECISION}" \
    --scheduler "${SCHEDULER}" --prompt-source "${PROMPT_SOURCE}" --prompt-len "${PROMPT_LEN}" \
    --image-resolution "${IMAGE_RESOLUTION}" --batch-size "${BATCH_SIZE}" \
    --num-images "${NUM_IMAGES}" --num-inference-steps "${NUM_INFERENCE_STEPS}" \
    --guidance-scale "${GUIDANCE_SCALE}" --seed "${SEED}"
  echo "[RUN] ${collect_cmd}"
  echo "${collect_cmd}" >> "${COMMAND_LOG}"
  "${PYTHON_BIN}" scripts/collect_sdxl.py \
    --output "${RUN_DIR}/metrics.csv" --config "${CONFIG_FILE}" --profile "${PROFILE}" \
    --backend "${BACKEND}" --model-name "${MODEL_NAME}" --precision "${PRECISION}" \
    --scheduler "${SCHEDULER}" --prompt-source "${PROMPT_SOURCE}" --prompt-len "${PROMPT_LEN}" \
    --image-resolution "${IMAGE_RESOLUTION}" --batch-size "${BATCH_SIZE}" \
    --num-images "${NUM_IMAGES}" --num-inference-steps "${NUM_INFERENCE_STEPS}" \
    --guidance-scale "${GUIDANCE_SCALE}" --seed "${SEED}" | tee "${RAW_FILE}"
}

run_parse() {
  log_section "Parse"
  local parse_cmd
  printf -v parse_cmd '%q ' "${PYTHON_BIN}" scripts/parse_results.py --raw-file "${RAW_FILE}" --db "${REPO_ROOT}/results/benchmark.db" --config "${CONFIG_FILE}" --run-dir "${RUN_DIR}" --profile "${PROFILE}"
  echo "[RUN] ${parse_cmd}"
  echo "${parse_cmd}" >> "${COMMAND_LOG}"
  "${PYTHON_BIN}" scripts/parse_results.py --raw-file "${RAW_FILE}" --db "${REPO_ROOT}/results/benchmark.db" --config "${CONFIG_FILE}" --run-dir "${RUN_DIR}" --profile "${PROFILE}" || die "parse failed"
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

if [[ -f "${RAW_FILE}" ]]; then
  cp "${RAW_FILE}" "${RUN_DIR}/run.log"
fi

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
  --notes "validated run" \
  || printf '[WARN] Runtime ledger update failed\n' >&2
finish_benchmark_run
