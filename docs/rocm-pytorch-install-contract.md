# ROCm PyTorch Installation Contract

This contract applies to GPU workloads whose `Framework`, installation summary, or implementation requires PyTorch on an AMD ROCm host.

## Required behavior

1. `setup.sh` must not install unconstrained `torch` or `torchvision` from the default PyPI index for a ROCm workload.
2. Parser-only dependencies may remain in `requirements.txt`; accelerator frameworks must be installed explicitly from the official ROCm wheel index.
3. The wheel index and package versions must be configurable through environment variables and documented in `README.md`, for example:

### Agent safeguard: verify pins before generating setup

AI coding agents must not copy version pins from an unrelated template example or assume that a version exists on the selected ROCm index. Before committing defaults in a generated `setup.sh`, query the exact index for both packages and select a compatible pair:

# For non-vLLM ROCm/PyTorch workloads:
```bash
torch_versions="$(python3 -m pip index versions torch \
  --index-url "${PYTORCH_ROCM_INDEX_URL}" 2>&1)"
torchvision_versions="$(python3 -m pip index versions torchvision \
  --index-url "${PYTORCH_ROCM_INDEX_URL}" 2>&1)"
grep -Fq "${PYTORCH_VERSION}" <<< "${torch_versions}"
grep -Fq "${TORCHVISION_VERSION}" <<< "${torchvision_versions}"
```

Do not pipe `pip index` directly into `grep -q` while `set -o pipefail` is active: `grep` can close the pipe after a match and make pip report a `BrokenPipeError`, producing a false "version unavailable" failure.

The generated setup must fail early with an actionable message if either requested version is unavailable. Record the verified pair in the generated README and keep both versions overrideable through environment variables. Never leave an example pin in production setup code without checking that the index actually publishes it.

Ubuntu 24.04 and Ubuntu 26.04 / ROCm 10.1.0. Both releases use the same wheel index and the gfx942 device extra. Do not install unconstrained `torch` from PyPI and do not install `torch[device-all]`.

```bash
PYTORCH_ROCM_INDEX_URL="${PYTORCH_ROCM_INDEX_URL:-https://stable.repo.amd.com/rocm/whl-next/}"
PYTORCH_VERSION="${PYTORCH_VERSION:-2.13.0+rocm10.1.0}"
TORCHVISION_VERSION="${TORCHVISION_VERSION:-0.28.0+rocm10.1.0}"
TORCHAUDIO_VERSION="${TORCHAUDIO_VERSION:-2.11.0.2+rocm10.1.0}"
python -m pip install \
  "torch[device-gfx942]==${PYTORCH_VERSION}" \
  "torchvision[device-gfx942]==${TORCHVISION_VERSION}" \
  "torchaudio==${TORCHAUDIO_VERSION}" \
  --index-url "${PYTORCH_ROCM_INDEX_URL}" \
  --extra-index-url https://pypi.org/simple
```

Benchmark virtualenvs are uv-managed CPython 3.14 on both Ubuntu releases. The system interpreter stays the distro Python (3.12.3 on 24.04, python3.14 on 26.04) and is used only by setup scripts.

vLLM uses the cp314 wheel `vllm-0.29.1.dev0+rocm10.1.0` from `https://rocm.frameworks.amd.com/whl-multi-arch/vllm/`, which requires torch 2.13.0. Also install `flash-attn==2.8.3` and `amd-aiter==0.1.22.post2.dev0+gb4d9154d1.d20261002` from that index, and `tensorizer==2.12.1` from PyPI. Extra-deps pip is non-fatal when an optional dependency is unpublished; always install `uvloop`, `fastapi`, and `aiohttp>=3.13.3` so `vllm.entrypoints.openai.api_server` can start.

## Ubuntu 24.04 and 26.04 / ROCm 10.1.0 extras (AMD 101–132 and 301–332)

`scripts/lib/rocm_install.sh` dispatches to `scripts/lib/rocm_install_24_04.sh` or `scripts/lib/rocm_install_26_04.sh`. Both install amdgpu-dkms 31.60 and ROCm 10.1.0. Do not rewrite those libraries during workload generation.

- Kernel pin: 6.8.0 on Ubuntu 24.04, 7.0.0 on Ubuntu 26.04. Python pin: 3.14 via uv for every benchmark venv. ROCm pin: 10.1.0 at `/opt/rocm` (packages may live under `/opt/rocm/core-10.1`; setup links `bin`, `lib`, and `include` into `/opt/rocm`).
- Packages: `amdrocm10.1-gfx942` and `amdrocm-core-dev10.1-gfx942`. rocBLAS 5.7.0 is included. RVS is `amdrocm10-rvs` 1.6.131-844 from the extras repository, not a source build. Use distro CMake; do not add the Kitware repository.
- AITER wheel: `amd-aiter==0.1.22.post2.dev0+gb4d9154d1.d20261002` from `https://rocm.frameworks.amd.com/whl-multi-arch/vllm/`. Import name is `aiter`. Prefer the wheel; do not clone `third_party/aiter` by default. The index also publishes `0.1.20.post1`.
- SGLang 0.5.18 is built from source at commit `71de97b264b04dcd514cf904003028aefe9775c8` against torch 2.13. Setup that sees Framework `sglang` must default `BENCHMARK_COMPILE_SGLANG=1` and die if `import sglang` still fails.
- JAX: `jax_rocm10_plugin==0.11.1+rocm10.1.0` and `jax_rocm10_pjrt==0.11.1+rocm10.1.0` from whl-next, then PyPI `jax==0.11.1` and `jaxlib==0.11.1`. `jax.devices()` should show a non-CPU device.
- hipcc still needs a host GCC that exposes `<cstdlib>` to the HIP wrapper. Every hipcc compile must source `scripts/lib/hipcc_host_gcc.sh`. Setup on 26.04 installs `g++-15`. Always export `LD_LIBRARY_PATH=/opt/rocm/lib:/opt/rocm/lib64`.
- rocHPL (120 / 320) host allocations must use 64-bit sizes. Do not run extended `N=65536` (228 min hang, then `hipErrorIllegalAddress`). Keep the `linpack-rochpl-amd` overlay. Clamp `N>=65536` to 32768 and allow up to 16 timed repeats at `N=32768` (~12 min). Missing `help-prun.txt` under pmix2/prrte3 is a secondary Open MPI 5 help-text miss after the child already crashed.
- AMD RAG (132 / 332) must use the `rag-faiss-end2end-amd` overlay. Setup calls `scripts/install_rag_amd.sh` after ROCm torch exists. Do not install a CUDA wheel and do not leave the `torch.nn.Linear` stub.

ROCm wheels may still expose `torch.version.cuda` as an API compatibility shim. Verification must require `torch.version.hip is not None` and a visible GPU; do not treat a non-None CUDA version string as a CUDA wheel.

For vLLM workloads, install the official vLLM ROCm wheel instead; it supplies the compatible PyTorch-family build set and compiled vLLM extensions.

4. Installation must verify all of the following before writing the successful setup marker:

```python
import torch
assert torch.version.hip is not None
assert torch.cuda.is_available()
assert torch.cuda.device_count() >= 1
```

5. The verification must print the PyTorch version, HIP version, and GPU name, and must allocate a tensor on `cuda`. A CUDA wheel such as `torch+cu130`, a CPU wheel, or `torch.version.hip is None` is a setup failure. Some MI300X VF / TheRock wheels report `torch.cuda.device_count() == 0` while `is_available()` and `cuda:0` compute still work; do not treat a zero count as a CUDA-wheel failure when a `cuda` allocation succeeds.
6. The setup failure must prevent benchmark execution and must identify the ROCm wheel index and GPU visibility checks needed for remediation.

The ROCm runtime and GPU device must be installed and visible through `rocminfo`/`amd-smi` before the PyTorch verification is expected to pass.

For LLM-serving workloads, install the verified ROCm Torch pair before installing framework packages. Do not allow a generic CUDA `sgl_kernel` wheel to replace the ROCm build. Build SGLang's `sgl-kernel` from its source tree with `setup_rocm.py` and the target `PYTORCH_ROCM_ARCH`, install the SGLang Python package without dependency replacement, and install AMD AITER from the official ROCm repository with recursive submodules.

vLLM ROCm platform detection also requires the Python `amdsmi` package; generated vLLM repositories must install and import-check it before launching the server. The vLLM serving package is the ROCm 10.1.0 cp314 wheel from `https://rocm.frameworks.amd.com/whl-multi-arch/vllm/`. Verify the resolved PyTorch, torchvision, and torchaudio versions after that wheel is installed. If the selected wheel's V1 engine imports CUDA-only FlashInfer components, generated runners should use a documented ROCm compatibility shim to skip the incompatible warmup, while retaining an explicit opt-out for wheels that fix it.
