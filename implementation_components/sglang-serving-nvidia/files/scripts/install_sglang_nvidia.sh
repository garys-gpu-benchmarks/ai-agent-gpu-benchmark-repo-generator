#!/usr/bin/env bash
# File: scripts/install_sglang_nvidia.sh
# Description: NVIDIA SGLang extras. Call from setup.sh after the venv exists.
# Ubuntu 24.04 / 230/231: sglang 0.5.19, torch 2.13.0+cu130, sglang-kernel 0.4.6.post1.
# Ubuntu 26.04 / 430/431: torch 2.13.0+cu130, sglang 0.5.10.post1 --no-deps,
# sglang-kernel 0.4.6.post1, launch_server runtime deps, Python 3.14 patch.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
if [[ "${EUID}" -eq 0 ]]; then SUDO=""; else SUDO="sudo"; fi
if command -v apt-get >/dev/null 2>&1; then
  ${SUDO} env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ninja-build
fi
PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
[[ -x "${PYTHON_BIN}" ]] || PYTHON_BIN="${BENCHMARK_PYTHON:-python3}"
if [[ -f "${REPO_ROOT}/scripts/lib/disk_space.sh" ]]; then
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/scripts/lib/disk_space.sh"
  require_free_kib "${REPO_ROOT}" $((12 * 1024 * 1024)) \
    "SGLang CUDA wheels need 12 GiB free before pip install."
fi

ubuntu_id() {
  # shellcheck disable=SC1091
  . /etc/os-release
  printf '%s' "${VERSION_ID:-}"
}

python_mm() {
  "${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
}

needs_cu130_sglang() {
  local ver py
  ver="$(ubuntu_id)"
  py="$(python_mm)"
  [[ "${ver}" == "26.04" || "${py}" == "3.14" ]]
}

install_sglang_runtime_deps() {
  # launch_server imports these. sglang is installed --no-deps so they are absent.
  # Keep torch, its CUDA libraries and sglang-kernel out of this transaction.
  # On 2026-11-08 (431, TEMPLATE_00_126) one unconstrained install of this list
  # made pip backtrack: cuda-python==12.9 needs cuda-bindings 12.9, torch
  # 2.13.0+cu130 declares cuda-bindings>=13, and timm/torchao depend on torch, so
  # pip replaced torch with 2.10 from PyPI (915 MB, CUDA 12 libraries) and this
  # script then downloaded 2.13.0+cu130 again (526 MB) and restored NCCL.
  local constraints rc=0
  local -a deps=(
    'uvicorn' 'fastapi' 'uvloop' 'watchfiles' 'python-multipart'
    'aiohttp' 'orjson' 'pyzmq>=25.1.2' 'msgspec' 'setproctitle'
    'partial-json-parser' 'pybase64' 'einops' 'prometheus-client>=0.20.0'
    'psutil' 'requests' 'numpy' 'pillow' 'sentencepiece' 'tiktoken' 'gguf'
    'interegular' 'py-spy' 'scipy' 'packaging' 'nvidia-ml-py'
    'compressed-tensors' 'modelscope' 'blobfile==3.0.0' 'anthropic>=0.20.0'
    'IPython' 'build' 'llguidance>=0.7.11,<0.8'
    'openai==2.6.1' 'openai-harmony==0.0.4' 'mistral_common>=1.9.0'
    'soundfile==0.13.1' 'torch_memory_saver==0.0.9' 'quack-kernels>=0.3.0'
    'nvidia-cutlass-dsl>=4.4.1' 'smg-grpc-servicer>=0.5.0' 'datasets'
    'tqdm' 'pydantic'
  )
  # Pin what is installed now, so nothing in the list can swap it.
  constraints="$(mktemp)"
  "${PYTHON_BIN}" - "${constraints}" <<'PY'
import importlib.metadata as md
import sys

names = ("torch", "torchvision", "torchaudio", "triton", "nvidia-nccl-cu13")
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    for name in names:
        try:
            handle.write(f"{name}=={md.version(name)}\n")
        except md.PackageNotFoundError:
            pass
PY
  "${PYTHON_BIN}" -m pip install -c "${constraints}" "${deps[@]}" || rc=$?
  rm -f "${constraints}"
  if [[ "${rc}" != 0 ]]; then
    # Not seen yet. Keep the old path working: install unpinned, and the torch
    # and NCCL checks after this function put torch 2.13.0+cu130 back.
    echo "[WARN] SGLang runtime deps could not be installed with torch pinned; retrying without the pin" >&2
    "${PYTHON_BIN}" -m pip install "${deps[@]}"
  fi
  # These three pull torch (timm, torchao) or CUDA 12 bindings (cuda-python) as
  # dependencies. Their own dependencies are already installed. cuda-bindings
  # 12.9 with torch 2.13.0+cu130 is what the passing 431 venv had on 2026-11-08.
  "${PYTHON_BIN}" -m pip install --no-deps \
    'timm==1.0.16' 'torchao==0.9.0' 'cuda-python==12.9' 'cuda-bindings~=12.9.0'
}

# True when torch 2.13.0+cu130 and sglang-kernel 0.4.6.post1 are installed and
# sgl_kernel imports against that torch. Used to skip force-reinstalls that only
# repeat what is already in the venv (TEMPLATE_00_119).
cu130_stack_ok() {
  "${PYTHON_BIN}" - <<'PY' >/dev/null 2>&1
import importlib.metadata as md
import sys
import torch
ok = torch.__version__.startswith("2.13.0") and "cu130" in torch.__version__
ok = ok and md.version("sglang-kernel").startswith("0.4.6.post1")
import sgl_kernel  # noqa: F401  (raises when built against another torch ABI)
sys.exit(0 if ok else 1)
PY
}

reinstall_sglang_kernel() {
  "${PYTHON_BIN}" -m pip install --force-reinstall --no-deps 'sglang-kernel==0.4.6.post1' \
    --index-url https://docs.sglang.ai/whl/cu130/ \
    --extra-index-url https://pypi.org/simple
}

restore_nvidia_nccl() {
  # Runtime deps can overwrite nvidia/nccl/lib/libnccl.so.2 with a larger build
  # that does not export ncclCommResume, while the 2.29.7 dist-info stays.
  # Put the torch 2.13 library back before the next import. An import failure
  # here would otherwise force a torch reinstall from download.pytorch.org.
  "${PYTHON_BIN}" -m pip install --force-reinstall --no-deps 'nvidia-nccl-cu13==2.29.7'
}

install_cu130_sglang() {
  # A previous attempt may have left a overwritten libnccl.so.2. Restore it
  # before the first torch import, or that import is treated as a bad pin and
  # setup re-downloads torch from download.pytorch.org.
  restore_nvidia_nccl
  "${PYTHON_BIN}" -m pip install ninja
  # sglang-kernel 0.4.6.post1 loads on torch 2.13. Kernel 0.4.1 was built
  # against an older c10 ABI and fails to import on 2.9.1 and 2.13.
  if ! "${PYTHON_BIN}" -c "import torch; import sys; sys.exit(0 if torch.__version__.startswith('2.13.0') and 'cu130' in torch.__version__ else 1)" >/dev/null 2>&1; then
    "${PYTHON_BIN}" -m pip install 'torch==2.13.0+cu130' --index-url https://download.pytorch.org/whl/cu130
  fi
  if ! "${PYTHON_BIN}" -c "import torchvision; import sys; sys.exit(0 if '0.28.0' in torchvision.__version__ else 1)" >/dev/null 2>&1; then
    "${PYTHON_BIN}" -m pip install 'torchvision==0.28.0+cu130' --index-url https://download.pytorch.org/whl/cu130
  fi
  if ! "${PYTHON_BIN}" -c "import torchaudio; import sys; sys.exit(0 if torchaudio.__version__.startswith('2.11.0') else 1)" >/dev/null 2>&1; then
    "${PYTHON_BIN}" -m pip install 'torchaudio==2.11.0+cu130' --index-url https://download.pytorch.org/whl/cu130
  fi
  if ! "${PYTHON_BIN}" -c "import sglang" >/dev/null 2>&1; then
    "${PYTHON_BIN}" -m pip install 'sglang==0.5.10.post1' --no-deps
  fi
  if cu130_stack_ok; then
    echo "[INFO] sglang-kernel 0.4.6.post1 already loads on torch 2.13.0+cu130; not reinstalling"
  else
    reinstall_sglang_kernel
  fi
  local site
  site="$("${PYTHON_BIN}" -c "import sysconfig; print(sysconfig.get_path('purelib'))")"
  if [[ -f "${REPO_ROOT}/scripts/sglang_py314_patch.py" && -f "${REPO_ROOT}/scripts/sglang_py314.pth" ]]; then
    cp "${REPO_ROOT}/scripts/sglang_py314_patch.py" "${site}/sglang_py314_patch.py"
    cp "${REPO_ROOT}/scripts/sglang_py314.pth" "${site}/sglang_py314.pth"
  fi
  install_sglang_runtime_deps
  restore_nvidia_nccl
  if ! "${PYTHON_BIN}" -c "import torch; import sys; sys.exit(0 if torch.__version__.startswith('2.13.0') and 'cu130' in torch.__version__ else 1)" >/dev/null 2>&1; then
    "${PYTHON_BIN}" -m pip install --force-reinstall --no-deps \
      'torch==2.13.0+cu130' 'torchvision==0.28.0+cu130' 'torchaudio==2.11.0+cu130' \
      --index-url https://download.pytorch.org/whl/cu130
  fi
  # The runtime deps can replace torch or the kernel. Reinstall the kernel only
  # when the stack no longer loads, instead of every time.
  if ! cu130_stack_ok; then
    reinstall_sglang_kernel
  fi
  if ! "${PYTHON_BIN}" -c "from sglang.srt.entrypoints.http_server import launch_server" >/dev/null 2>&1 \
    || ! "${PYTHON_BIN}" -c "from sglang.srt.layers.sampler import create_sampler" >/dev/null 2>&1 \
    || ! "${PYTHON_BIN}" -c "import sgl_kernel" >/dev/null 2>&1; then
    "${PYTHON_BIN}" "${REPO_ROOT}/scripts/install_sglang_launch_deps.py" || true
    if ! "${PYTHON_BIN}" -c "import torch; import sys; sys.exit(0 if torch.__version__.startswith('2.13.0') and 'cu130' in torch.__version__ else 1)" >/dev/null 2>&1; then
      "${PYTHON_BIN}" -m pip install --force-reinstall --no-deps \
        'torch==2.13.0+cu130' 'torchvision==0.28.0+cu130' 'torchaudio==2.11.0+cu130' \
        --index-url https://download.pytorch.org/whl/cu130
    fi
    "${PYTHON_BIN}" -m pip install --force-reinstall --no-deps 'sglang-kernel==0.4.6.post1' \
      --index-url https://docs.sglang.ai/whl/cu130/ \
      --extra-index-url https://pypi.org/simple
  fi
  # A later kernel reinstall can overwrite libnccl.so.2 again.
  restore_nvidia_nccl
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/scripts/lib/sglang_nvidia_libs.sh"
  prepend_venv_nvidia_libs "${PYTHON_BIN}"
  if ! command -v ninja >/dev/null 2>&1; then
    echo "[FAIL] ninja is not on PATH (needed for SGLang CUDA-graph capture)" >&2
    exit 1
  fi
  ninja --version
  "${PYTHON_BIN}" - <<'PY'
import torch, torchvision, torchaudio, sglang, flashinfer, sgl_kernel
from sglang.srt.layers.sampler import create_sampler
from sglang.srt.entrypoints.http_server import launch_server
assert torch.__version__.startswith("2.13.0"), torch.__version__
assert "cu130" in torch.__version__, torch.__version__
print("torch", torch.__version__, "cuda", torch.version.cuda)
print("torchvision", torchvision.__version__)
print("torchaudio", torchaudio.__version__)
print("sglang", getattr(sglang, "__version__", "present"))
print("flashinfer", getattr(flashinfer, "__version__", "present"))
print("sampler", create_sampler)
print("launch_server", launch_server)
print("sgl_kernel", getattr(sgl_kernel, "__file__", "present"))
PY
  echo "[PASS] NVIDIA SGLang extras (Ubuntu 26.04 / cu130 / no-deps / FlashInfer)"
}

install_legacy_sglang() {
  "${PYTHON_BIN}" -m pip install ninja
  # Pin the 24.04 serving stack. Unpinned `pip install sglang` plus
  # `--force-reinstall torchvision torchaudio` walked 00_77 230/231 to
  # torch 2.14.0+cu130; sglang-kernel 0.4.6.post1 then failed to load
  # SM90 common_ops (undefined c10 CUDA symbol).
  # torchaudio==2.13.0+cu130 does not exist on the cu130 wheel index (it
  # tops out at 2.11.0+cu130) -- that pin made 00_80's 230/231 setup.sh die
  # before smoke ever ran. torch/torchvision stay at 2.13.0/0.28.0+cu130;
  # only torchaudio is pinned to the newest build actually published there.
  "${PYTHON_BIN}" -m pip install "sglang==0.5.19"
  "${PYTHON_BIN}" -m pip install \
    "torch==2.13.0+cu130" "torchvision==0.28.0+cu130" "torchaudio==2.11.0+cu130" \
    --index-url https://download.pytorch.org/whl/cu130
  "${PYTHON_BIN}" -m pip install --force-reinstall --no-cache-dir "sglang-kernel==0.4.6.post1" \
    --index-url https://docs.sglang.ai/whl/cu130/ \
    --extra-index-url https://pypi.org/simple
  if [[ -f "${REPO_ROOT}/scripts/install_sglang_launch_deps.py" ]]; then
    if ! "${PYTHON_BIN}" -c "import sgl_kernel" >/dev/null 2>&1 \
      || ! "${PYTHON_BIN}" -c "from sglang.srt.entrypoints.http_server import launch_server" >/dev/null 2>&1; then
      "${PYTHON_BIN}" "${REPO_ROOT}/scripts/install_sglang_launch_deps.py" || true
      "${PYTHON_BIN}" -m pip install --force-reinstall --no-cache-dir "sglang-kernel==0.4.6.post1" \
        --index-url https://docs.sglang.ai/whl/cu130/ \
        --extra-index-url https://pypi.org/simple
    fi
  fi
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/scripts/lib/sglang_nvidia_libs.sh"
  prepend_venv_nvidia_libs "${PYTHON_BIN}"
  if ! command -v ninja >/dev/null 2>&1; then
    echo "[FAIL] ninja is not on PATH (needed for SGLang CUDA-graph capture)" >&2
    exit 1
  fi
  ninja --version
  "${PYTHON_BIN}" - <<'PY'
import torch, torchvision, torchaudio, sglang, sgl_kernel
from sglang.srt.entrypoints.http_server import launch_server
torch_cuda = str(getattr(torch.version, "cuda", "") or "")
if not torch.__version__.startswith("2.13.0") or "cu130" not in torch.__version__:
    raise SystemExit(f"[FAIL] 24.04 SGLang requires torch 2.13.0+cu130, got {torch.__version__}")
print("torch", torch.__version__, "cuda", torch_cuda)
print("torchvision", torchvision.__version__)
print("torchaudio", torchaudio.__version__)
print("sglang", getattr(sglang, "__version__", "present"))
print("sgl_kernel", getattr(sgl_kernel, "__file__", "present"))
print("launch_server", launch_server)
PY
  echo "[PASS] NVIDIA SGLang extras (sglang 0.5.19 / torch 2.13.0+cu130 / sglang-kernel 0.4.6.post1)"
}

if needs_cu130_sglang; then
  install_cu130_sglang
else
  install_legacy_sglang
fi
