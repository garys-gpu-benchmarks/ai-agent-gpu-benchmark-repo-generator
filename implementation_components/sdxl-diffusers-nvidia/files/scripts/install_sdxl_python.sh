#!/usr/bin/env bash
# File: scripts/install_sdxl_python.sh
# Description: Install Diffusers/Transformers and optionally prefetch SDXL weights.
# Execution: bash scripts/install_sdxl_python.sh [--prefetch]
# run_benchmark.sh passes --prefetch on every profile, smoke included (smoke loads real SDXL).
# The download is resumable: partial files stay in the Hugging Face cache and the next
# attempt continues them. Each attempt has a time limit (SDXL_PREFETCH_TIMEOUT_SEC,
# default 1800) and a stalled read fails after HF_HUB_DOWNLOAD_TIMEOUT seconds (default 60).
# A failed or timed-out attempt is retried (SDXL_PREFETCH_ATTEMPTS, default 2).
# Prefetch downloads only the fp16 Diffusers files that from_pretrained(variant="fp16")
# loads. The full Hub snapshot also contains a 6.9 GiB checkpoint plus ONNX,
# OpenVINO, Flax, and duplicate fp32 weights. That snapshot fills the disk and
# Hugging Face Xet then fails while writing the large files.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="${BENCHMARK_PYTHON:-python3}"
fi
export HF_HOME="${HF_HOME:-${REPO_ROOT}/.cache/huggingface}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-${REPO_ROOT}/.cache/pip}"
export HF_HUB_DISABLE_XET=1
mkdir -p "${HF_HOME}" "${PIP_CACHE_DIR}"

echo "[RUN] ${PYTHON_BIN} -m pip install diffusers transformers accelerate safetensors huggingface_hub"
"${PYTHON_BIN}" -m pip install diffusers transformers accelerate safetensors huggingface_hub

if [[ "${1:-}" != "--prefetch" ]]; then
  echo "[INFO] SDXL Python packages installed; weights not prefetched (smoke path)."
  exit 0
fi

SDXL_HF_ID="${SDXL_HF_ID:-stabilityai/stable-diffusion-xl-base-1.0}"
if SDXL_HF_ID="${SDXL_HF_ID}" HF_HOME="${HF_HOME}" "${PYTHON_BIN}" - <<'PY'
import os
from pathlib import Path

repo = os.environ["SDXL_HF_ID"]
home = Path(os.environ["HF_HOME"]) / "hub" / ("models--" + repo.replace("/", "--"))
needed = [
    "model_index.json",
    "scheduler/scheduler_config.json",
    "tokenizer/tokenizer_config.json",
    "tokenizer_2/tokenizer_config.json",
    "text_encoder/config.json",
    "text_encoder/model.fp16.safetensors",
    "text_encoder_2/config.json",
    "text_encoder_2/model.fp16.safetensors",
    "unet/config.json",
    "unet/diffusion_pytorch_model.fp16.safetensors",
    "vae/config.json",
    "vae/diffusion_pytorch_model.fp16.safetensors",
]
snaps = home / "snapshots"
if not snaps.is_dir():
    raise SystemExit(1)
for snap in snaps.iterdir():
    if snap.is_dir() and all((snap / rel).is_file() for rel in needed):
        raise SystemExit(0)
raise SystemExit(1)
PY
then
  echo "[PASS] SDXL fp16 weights already cached in ${HF_HOME}"
  mkdir -p "${REPO_ROOT}/.cache"
  printf 'ok\n' > "${REPO_ROOT}/.cache/sdxl_prefetch.ok"
  exit 0
fi

if [[ -f "${REPO_ROOT}/scripts/lib/disk_space.sh" ]]; then
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/scripts/lib/disk_space.sh"
  require_free_kib "${HF_HOME}" $((12 * 1024 * 1024)) \
    "SDXL fp16 prefetch needs 12 GiB free before snapshot_download."
else
  avail_kb="$(df -Pk "${HF_HOME}" | awk 'NR==2 {print $4}')"
  need_kb=$((12 * 1024 * 1024))
  if [[ -z "${avail_kb}" || "${avail_kb}" -lt "${need_kb}" ]]; then
    echo "[FAIL] SDXL fp16 prefetch needs 12 GiB free on the filesystem holding ${HF_HOME}." >&2
    echo "[FAIL] path=${HF_HOME} free_kib=${avail_kb:-unknown} need_kib=${need_kb}" >&2
    exit 1
  fi
fi

PREFETCH_TIMEOUT_SEC="${SDXL_PREFETCH_TIMEOUT_SEC:-1800}"
PREFETCH_ATTEMPTS="${SDXL_PREFETCH_ATTEMPTS:-2}"
export HF_HUB_DOWNLOAD_TIMEOUT="${HF_HUB_DOWNLOAD_TIMEOUT:-60}"
export HF_HUB_ETAG_TIMEOUT="${HF_HUB_ETAG_TIMEOUT:-30}"
PREFETCH_PY="$(mktemp)"
trap 'rm -f "${PREFETCH_PY}"' EXIT
cat > "${PREFETCH_PY}" <<'PY'
import os
from huggingface_hub import snapshot_download

repo = os.environ["SDXL_HF_ID"]
patterns = [
    "model_index.json",
    "scheduler/*",
    "tokenizer/*",
    "tokenizer_2/*",
    "text_encoder/config.json",
    "text_encoder/model.fp16.safetensors",
    "text_encoder_2/config.json",
    "text_encoder_2/model.fp16.safetensors",
    "unet/config.json",
    "unet/diffusion_pytorch_model.fp16.safetensors",
    "vae/config.json",
    "vae/diffusion_pytorch_model.fp16.safetensors",
]
print(f"[INFO] snapshot_download({repo}) allow_patterns={len(patterns)} HF_HUB_DISABLE_XET=1")
# Never force_download: partial *.incomplete blobs from an earlier attempt are resumed.
snapshot_download(repo_id=repo, allow_patterns=patterns)
print("[PASS] SDXL weights cached")
PY
prefetch_ok=0
for ((attempt = 1; attempt <= PREFETCH_ATTEMPTS; attempt++)); do
  echo "[RUN] prefetch ${SDXL_HF_ID} fp16 Diffusers files into ${HF_HOME} (Xet disabled; attempt ${attempt}/${PREFETCH_ATTEMPTS}; limit ${PREFETCH_TIMEOUT_SEC}s)"
  rc=0
  SDXL_HF_ID="${SDXL_HF_ID}" timeout -k 30 "${PREFETCH_TIMEOUT_SEC}" "${PYTHON_BIN}" "${PREFETCH_PY}" || rc=$?
  if [[ "${rc}" -eq 0 ]]; then
    prefetch_ok=1
    break
  fi
  partial_kib="$({ find "${HF_HOME}/hub" -name '*.incomplete' -printf '%k\n' 2>/dev/null || true; } | awk '{s+=$1} END {print s+0}')"
  if [[ "${rc}" -eq 124 || "${rc}" -eq 137 ]]; then
    echo "[WARN] SDXL prefetch attempt ${attempt} hit the ${PREFETCH_TIMEOUT_SEC}s limit; keeping ${partial_kib} KiB of partial files to resume." >&2
  else
    echo "[WARN] SDXL prefetch attempt ${attempt} exited ${rc}; keeping ${partial_kib} KiB of partial files to resume." >&2
  fi
  if (( attempt < PREFETCH_ATTEMPTS )); then
    sleep 10
  fi
done
if [[ "${prefetch_ok}" -ne 1 ]]; then
  echo "[FAIL] SDXL prefetch did not finish after ${PREFETCH_ATTEMPTS} attempt(s). Partial files are kept in ${HF_HOME}; rerun to resume." >&2
  exit 1
fi
mkdir -p "${REPO_ROOT}/.cache"
printf 'ok\n' > "${REPO_ROOT}/.cache/sdxl_prefetch.ok"
