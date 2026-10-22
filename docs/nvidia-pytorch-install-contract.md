# NVIDIA PyTorch / JAX install contract

Use this contract when `GPU Vendor` is NVIDIA and `Framework` includes PyTorch, torchvision, JAX, or Hugging Face Transformers.

Do **not** use this helper on AMD / ROCm workloads. AMD continues to follow [`rocm-pytorch-install-contract.md`](rocm-pytorch-install-contract.md).

## Rules

1. Do not list `torch`, `torchvision`, `torchaudio`, `jax`, `vllm`, or `sglang` in `requirements.txt`. Parser-only pins such as `PyYAML>=6.0` stay there.
2. Install CUDA wheels from the official PyTorch CUDA index, never unconstrained default PyPI `torch`.
3. Ubuntu 24.04 default pin: `torch==2.13.0+cu130` from `https://download.pytorch.org/whl/cu130`, the same build as Ubuntu 26.04 (TEMPLATE_00_116). Until TEMPLATE_00_115 it was `torch==2.7.1+cu128`, which made 24.04 and 26.04 results differ by PyTorch version. The NVIDIA driver (595) supports CUDA 13; the system CUDA toolkit stays 12.8 on 24.04 for `nvcc` builds.
4. Ubuntu 26.04 default pin: `torch==2.13.0+cu130` from `https://download.pytorch.org/whl/cu130`. Workloads 430/431 keep their overlay pin (`torch==2.9.1+cu130`) inside `scripts/install_sglang_nvidia.sh`. Ubuntu 24.04 230/231 use the same `torch==2.13.0+cu130`, plus `sglang==0.5.19` / `sglang-kernel==0.4.6.post1` (the sglang install contract that documents this override is a generation-time-only doc and is not shipped with published workload repos).
5. Install torchvision only when Framework or the implementation requires it (`BENCHMARK_INSTALL_TORCHVISION=1`).
6. Install JAX only when Framework includes JAX. Use `jax[cuda13]` when `torch.version.cuda` major is 13, otherwise `jax[cuda12]`. If pip rejects that extra, fail. Do not fall back to the other extra. The post-install check is a JIT matmul, and it runs only in the JAX branch.
7. Install `transformers` / `datasets` only when Framework includes Transformers, BERT, DistilBERT, or Hugging Face.
8. After CUDA torch, install `numpy` so Torch does not warn `Failed to initialize NumPy` (205 tensor correctness).
9. `setup.sh` must verify `torch.cuda.is_available()` (and the matching JAX/Transformers import) before writing `.setup_state`.
10. vLLM and SGLang overlay `setup.sh` files perform their own wheel install. Do not also force `install_pytorch_nvidia.sh` on those workloads.
11. Never source `scripts/lib/rocm_install.sh` and never call `scripts/install_pytorch_nvidia.sh` from `setup_rocm_reboot_skeleton.sh`.
12. CUDA 13 convolution repos install `nvidia-cudnn-cu13==9.23.2.1` into that repo's virtualenv after torch. `torch==2.13.0+cu130` pins `nvidia-cudnn-cu13==9.20.0.48`, which does not ship `libcudnn_engines_tensor_ir.so.9`. The 9.23.2.1 pin is a deliberate override of that incomplete wheel. It is chosen by `torch.version.cuda` major 13, so Ubuntu 24.04 receives it too. `cudnn-convolution-nvidia` (x18) does not use PyTorch and still selects its cuDNN by `nvcc` major (24.04: system `libcudnn9-cuda-12`). vLLM, SGLang, DistilBERT, BERT, and RAG do not.
13. A system `libcudnn_engines_tensor_ir` is moved off the default linker path only when its version differs from the virtualenv `nvidia-cudnn` package. The move wraps only this repo's `bin/cudnn_conv`, and only when the virtualenv itself does not ship `tensor_ir`. The collector prepends `/opt/cudnn-host-extra` only when that library file is present and the virtualenv does not already ship it.
14. The NVIDIA skeleton runs `scripts/probe_setup.sh` only when a component overlaid that file. PyTorch convolution components probe `conv2d`. `cudnn-convolution-nvidia` probes `bin/cudnn_conv`. The probe fails setup; it does not repair a missing library.

## Helper

Generated NVIDIA repositories receive `scripts/install_pytorch_nvidia.sh` from the template `scripts/` tree. The canonical NVIDIA setup skeleton calls it when Framework requires those wheels.
