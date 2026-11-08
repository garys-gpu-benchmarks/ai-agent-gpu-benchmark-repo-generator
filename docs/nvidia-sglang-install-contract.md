# NVIDIA SGLang install contract

Proven pins from the Ubuntu 26.04 / Python 3.14 / CUDA 13 H100 host. Do not mix these with the vLLM 2.13 stack or with the Ubuntu 24.04 / 230/231 recipe.

## Ubuntu 26.04 (430 / 431)

```text
torch==2.9.1+cu130
torchvision==0.24.1+cu130
torchaudio==2.9.1+cu130
sglang==0.5.10.post1 --no-deps
sglang-kernel==0.4.1  --index-url https://docs.sglang.ai/whl/cu130/ --extra-index-url https://pypi.org/simple
flashinfer-python==0.6.7.post3
flashinfer-cubin==0.6.7.post3
xgrammar==0.1.32
```

- Do not `pip install sglang` with dependencies. That pulls CUDA 12 torch and tries to build `outlines_core` (needs Rust; no cp314 wheel).
- Skip `outlines` / `outlines_core`.
- `import sglang` is not enough. Verify `python -m sglang.launch_server --help` and `from sglang.srt.layers.sampler import create_sampler`.
- Copy `scripts/sglang_py314_patch.py` and `scripts/sglang_py314.pth` into the venv site-packages (no-op `torch.compile`, `ast.Num` shims, disable piecewise CUDA graphs on 3.14).
- A cache that contains only `consolidated.safetensors` is not safe for `--model-path <repo id>`. SGLang logs `skipping download`, then fetches `model.safetensors.index.json` and drops the consolidated file, so the server exits with `Cannot find any model weights` while the named `model-*-of-*.safetensors` shards are still absent. Every profile, smoke included, must run `scripts/prefetch_sglang_model.py` and pass the printed snapshot directory to `sglang.launch_server`. AMD 130, 131, 330, and 331 use that same script. Leave `consolidated.safetensors` in place for vLLM and RAG. A cache that is missing `consolidated.safetensors` is still usable once every index shard exists and is non-empty; do not require `snapshot_download(..., local_files_only=True)` to see that file. No profile starts `scripts/tiny_sglang_server.py` (2026-11-07).
- Do not run 430 and 431 at the same time (port 30000). One large SGLang venv is ~15G; delete the previous one before creating the next on a quotaed `/workspace`.

The overlay helper `scripts/install_sglang_nvidia.sh` selects this branch when `VERSION_ID=26.04` or Python is 3.14.

## Ubuntu 24.04 (230 / 231)

```text
torch==2.13.0+cu130
torchvision==0.28.0+cu130
torchaudio==2.13.0+cu130
sglang==0.5.19
sglang-kernel==0.4.6.post1  --index-url https://docs.sglang.ai/whl/cu130/ --extra-index-url https://pypi.org/simple
```

- Do not `pip install sglang` unpinned and then `--force-reinstall torchvision torchaudio`. That walked 00_77 230/231 to `torch 2.14.0+cu130` while `sglang-kernel==0.4.6.post1` still expected the 2.13 libc10 ABI. Baseline `python -m sglang.launch_server` then died on `undefined symbol: ...c10_cuda_check_implementation`.
- After installing sglang, restore `torch==2.13.0+cu130` and force-reinstall `sglang-kernel==0.4.6.post1` from the SGLang cu130 wheel index.
- `import sglang` and `python -m sglang.launch_server --help` are not enough. Verify `import sgl_kernel` actually loads `common_ops` and `from sglang.srt.entrypoints.http_server import launch_server`.
- Do not apply the Ubuntu 26.04 / Python 3.14 / `sglang==0.5.10.post1 --no-deps` recipe here.
- Do not run 230 and 231 at the same time (port 30000).
