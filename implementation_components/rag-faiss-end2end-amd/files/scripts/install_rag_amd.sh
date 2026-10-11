#!/usr/bin/env bash
# File: scripts/install_rag_amd.sh
# Description: AMD RAG extras. Call from setup.sh after the ROCm venv exists.
# Do not install a CUDA torch wheel. Reuse the operator-selected ROCm torch.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
[[ -x "${PYTHON_BIN}" ]] || PYTHON_BIN="${BENCHMARK_PYTHON:-python3}"

if [[ "${BENCHMARK_GPU_CHECKS_AFTER_REBOOT:-0}" == 1 ]]; then
  # setup.sh postponed the amdgpu reboot: no GPU yet. Check that ROCm PyTorch is
  # installed; setup checks the GPU after the reboot.
  if ! "${PYTHON_BIN}" -c "import torch; assert torch.version.hip" >/dev/null 2>&1; then
    echo "[FAIL] ROCm PyTorch must already be installed before AMD RAG extras." >&2
    exit 1
  fi
elif ! "${PYTHON_BIN}" -c "import torch; assert torch.cuda.is_available()" >/dev/null 2>&1; then
  echo "[FAIL] ROCm PyTorch must already be installed and see a GPU before AMD RAG extras." >&2
  exit 1
fi
if ! "${PYTHON_BIN}" -c "import transformers" >/dev/null 2>&1; then
  "${PYTHON_BIN}" -m pip install transformers
fi
# Mistral tokenizer.model is SentencePiece. tiktoken alone is not enough;
# AutoTokenizer.from_pretrained then dies converting the slow tokenizer.
if ! "${PYTHON_BIN}" -c "import sentencepiece" >/dev/null 2>&1; then
  "${PYTHON_BIN}" -m pip install sentencepiece
fi
if ! "${PYTHON_BIN}" -c "import tiktoken" >/dev/null 2>&1; then
  "${PYTHON_BIN}" -m pip install tiktoken
fi
if ! "${PYTHON_BIN}" -c "import faiss" >/dev/null 2>&1; then
  "${PYTHON_BIN}" -m pip install faiss-cpu
fi
if ! "${PYTHON_BIN}" -c "import datasets" >/dev/null 2>&1; then
  "${PYTHON_BIN}" -m pip install datasets
fi
if ! "${PYTHON_BIN}" -c "import llama_index" >/dev/null 2>&1; then
  "${PYTHON_BIN}" -m pip install llama-index-core
fi
"${PYTHON_BIN}" "${REPO_ROOT}/scripts/prefetch_rag_models.py"
echo "[PASS] AMD RAG extras (FAISS, datasets, LlamaIndex, prefetch)"
