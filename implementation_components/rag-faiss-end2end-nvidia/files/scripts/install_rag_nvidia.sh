#!/usr/bin/env bash
# File: scripts/install_rag_nvidia.sh
# Description: NVIDIA RAG extras. Call from setup.sh after the venv exists.
# Ubuntu 26.04 / 432: torch 2.13.0+cu130. Ubuntu 24.04 / 232: torch 2.7.1+cu128.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
[[ -x "${PYTHON_BIN}" ]] || PYTHON_BIN="${BENCHMARK_PYTHON:-python3}"

ubuntu_id() {
  # shellcheck disable=SC1091
  . /etc/os-release
  printf '%s' "${VERSION_ID:-}"
}

if [[ "$(ubuntu_id)" == "26.04" ]]; then
  if ! "${PYTHON_BIN}" -c "import torch; assert torch.cuda.is_available() and '2.13.0' in torch.__version__" >/dev/null 2>&1; then
    "${PYTHON_BIN}" -m pip install 'torch==2.13.0+cu130' --index-url https://download.pytorch.org/whl/cu130
  fi
  if ! "${PYTHON_BIN}" -c "import torchvision" >/dev/null 2>&1; then
    "${PYTHON_BIN}" -m pip install 'torchvision==0.28.0+cu130' --index-url https://download.pytorch.org/whl/cu130
  fi
else
  if ! "${PYTHON_BIN}" -c "import torch; assert torch.cuda.is_available()" >/dev/null 2>&1; then
    "${PYTHON_BIN}" -m pip install 'torch==2.7.1+cu128' --index-url https://download.pytorch.org/whl/cu128
  fi
  if ! "${PYTHON_BIN}" -c "import torchvision" >/dev/null 2>&1; then
    "${PYTHON_BIN}" -m pip install 'torchvision==0.22.1+cu128' --index-url https://download.pytorch.org/whl/cu128  # matches torch 2.7.1
  fi
fi
if ! "${PYTHON_BIN}" -c "import transformers" >/dev/null 2>&1; then
  "${PYTHON_BIN}" -m pip install transformers
fi
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
echo "[PASS] NVIDIA RAG extras (FAISS, datasets, LlamaIndex, prefetch)"
