# NVIDIA SGLang install contract

Pins installed by `scripts/install_sglang_nvidia.sh` (identical in `sglang-prompt-response-nvidia` and `sglang-serving-nvidia`). Both Ubuntu releases use torch 2.13.0+cu130 and `sglang-kernel==0.4.6.post1`; they differ in the sglang version and the Python 3.14 patch. Keep each SGLang venv separate from the vLLM venvs.

## Ubuntu 26.04 (430 / 431)

```text
torch==2.13.0+cu130
torchvision==0.28.0+cu130
torchaudio==2.11.0+cu130
sglang==0.5.10.post1 --no-deps
sglang-kernel==0.4.6.post1  --index-url https://docs.sglang.ai/whl/cu130/ --extra-index-url https://pypi.org/simple
flashinfer-python==0.6.7.post3
flashinfer-cubin==0.6.7.post3
xgrammar==0.1.32
```

- Do not `pip install sglang` with dependencies. That pulls CUDA 12 torch and tries to build `outlines_core` (needs Rust; no cp314 wheel).
- Skip `outlines` / `outlines_core`.
- `import sglang` is not enough. Verify `python -m sglang.launch_server --help` and `from sglang.srt.layers.sampler import create_sampler`.
- Copy `scripts/sglang_py314_patch.py` and `scripts/sglang_py314.pth` into the venv site-packages (no-op `torch.compile`, `ast.Num` shims, disable piecewise CUDA graphs on 3.14).
- A cache that contains only `consolidated.safetensors` is not safe for `--model-path <repo id>`. SGLang logs `skipping download`, then fetches `model.safetensors.index.json` and drops the consolidated file, so the server exits with `Cannot find any model weights` while the named `model-*-of-*.safetensors` shards are still absent. Every profile, smoke included, must run `scripts/prefetch_sglang_model.py` and pass the printed snapshot directory to `sglang.launch_server`. The script also downloads `config.json` (it must contain `model_type`), `generation_config.json` when present, and `tokenizer.json`, `tokenizer.model`, `tokenizer_config.json` and `special_tokens_map.json` into that snapshot, and loads `AutoConfig` and `AutoTokenizer` from it offline before printing the path (a snapshot without `config.json` made every fresh-VM x30 smoke exit on 2026-11-08, TEMPLATE_00_126); SGLang never downloads into a directory path, and a weights-only snapshot (only `tokenizer.model.v3`) made every first smoke exit on 2026-11-08. AMD 130, 131, 330, and 331 use that same script. Leave `consolidated.safetensors` in place for vLLM and RAG. A cache that is missing `consolidated.safetensors` is still usable once every index shard exists and is non-empty; do not require `snapshot_download(..., local_files_only=True)` to see that file. No profile starts `scripts/tiny_sglang_server.py` (2026-11-07).
- `install_sglang_runtime_deps` pins the installed torch, torchvision, torchaudio, triton and `nvidia-nccl-cu13` with a pip constraints file, and installs `timm`, `torchao`, `cuda-python==12.9` and `cuda-bindings~=12.9.0` with `--no-deps`. One unconstrained install of that list swapped torch 2.13.0+cu130 for torch 2.10 on 431 (2026-11-08). If the constrained install fails, it retries unpinned and the torch/NCCL checks that follow restore 2.13.0+cu130. NCCL is restored before the first torch import (Project453 repair).
- Do not run 430 and 431 at the same time (port 30000). One large SGLang venv is ~15G; delete the previous one before creating the next on a quotaed `/workspace`.

The overlay helper `scripts/install_sglang_nvidia.sh` selects this branch when `VERSION_ID=26.04` or Python is 3.14.

## Ubuntu 24.04 (230 / 231)

```text
torch==2.13.0+cu130
torchvision==0.28.0+cu130
torchaudio==2.11.0+cu130
sglang==0.5.19
sglang-kernel==0.4.6.post1  --index-url https://docs.sglang.ai/whl/cu130/ --extra-index-url https://pypi.org/simple
```

- Do not `pip install sglang` unpinned and then `--force-reinstall torchvision torchaudio`. That walked 00_77 230/231 to `torch 2.14.0+cu130` while `sglang-kernel==0.4.6.post1` still expected the 2.13 libc10 ABI. Baseline `python -m sglang.launch_server` then died on `undefined symbol: ...c10_cuda_check_implementation`.
- After installing sglang, restore `torch==2.13.0+cu130` and force-reinstall `sglang-kernel==0.4.6.post1` from the SGLang cu130 wheel index.
- `import sglang` and `python -m sglang.launch_server --help` are not enough. Verify `import sgl_kernel` actually loads `common_ops` and `from sglang.srt.entrypoints.http_server import launch_server`.
- Do not apply the Ubuntu 26.04 / Python 3.14 / `sglang==0.5.10.post1 --no-deps` recipe here.
- Do not run 230 and 231 at the same time (port 30000).
