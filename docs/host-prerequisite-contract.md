# Host Prerequisite Contract

This contract defines how generated `setup.sh` scripts discover, install, and verify non-ROCm host prerequisites. It applies before any generated build or benchmark execution.

This contract is only the non-ROCm portion of setup. It must not be interpreted as permission to omit workload runtime installation. `setup.sh` remains the complete installation entrypoint: after host prerequisites, it must install and verify every workload-specific dependency and build the required execution backend. For ROCm-dependent GPU workloads, the generated setup must also follow `docs/rocm-reboot-install-contract.md` by default. A CPU fixture is an explicit fallback only, never the normal completion state for a GPU workload.

## Derivation

The generator must inspect all of the following:

1. `benchmark_specification.json` fields `Installation and Execution Summary`, `Framework`, and `Runtime Language`.
2. The generated `scripts/build.sh`.
3. The generated `run_benchmark.sh`, parser, and export commands.

The resulting prerequisite set must include every package and command actually required by the generated workload. Common conditional requirements include:

| Workload requirement | Typical packages or commands |
|---|---|
| Python virtual environment | `python3-venv` and matching `python3.x-venv` |
| C/C++ compilation | `build-essential`, `gcc`, `make` |
| HIP / `hipcc` on Ubuntu 26.04 | `g++-15`, `gcc-15`; generated `scripts/build.sh` must `source scripts/lib/hipcc_host_gcc.sh` or pass `--gcc-install-dir=/usr/lib/gcc/x86_64-linux-gnu/15`. ROCm 10.1.0 hipcc is Clang 24; the GCC 15 pin still supplies `<cstdlib>` to `__clang_hip_runtime_wrapper.h`. Also export `LD_LIBRARY_PATH=/opt/rocm/lib:/opt/rocm/lib64`. |
| Autotools/source build | `autoconf`, `automake`, `libtool`, `libtool-bin`, `m4`, `pkg-config`, `flex`, `bison`, `cmake` |
| Source checkout | `git` |
| NUMA development/runtime | `libnuma-dev`, `numactl` |
| SQLite CSV/JSON export | `sqlite3` CLI |
| Rust extension build | current stable Rust via `rustup`, `rustc`, `cargo` |
| Protocol Buffer extension build | `protobuf-compiler`, `libprotobuf-dev`, `protoc` |
| AMD SGLang kernels | AITER source checkout with recursive submodules |
| FAISS ROCm source build | `libopenblas-dev`, `libgflags-dev`, `swig`, `python3-dev`, matching `python3.x-dev` |

The table is guidance, not a fixed package list. Workload-specific dependencies derived from the source fields and generated scripts must also be included.

## Setup Implementation Requirements

Generated `setup.sh` must:

1. Be the primary, idempotent installation entry point and begin with `set -euo pipefail`.
2. Create or reuse the repository-local `.venv`; use `.venv/bin/python` for repository Python commands and never install benchmark packages globally.
3. Install only the host packages, ROCm components, compiler toolchains, and workload utilities required by the validated definition.
4. Verify required executables, libraries, imports, GPU visibility, and device permissions before writing the successful `.setup_state` marker.
5. Record progress in `results/install_status.txt`, record bare executed install commands in `results/install_commands.txt`, and support reboot resume when the applicable installation contract requires reboots.
6. Create build prerequisites and `scripts/build.sh` only when the workload requires compilation, source checkout, or an explicit build step.

Setup must be safe to rerun. A completed setup may repeat inexpensive verification, but it must not unnecessarily reinstall or reboot a fully verified environment.

## Installation

For each missing Debian/Ubuntu package, setup must use idempotent, noninteractive commands equivalent to:

```bash
run_privileged env DEBIAN_FRONTEND=noninteractive apt-get update -y
run_privileged env DEBIAN_FRONTEND=noninteractive apt-get install -y <package>
```

`run_privileged` calls `run_noninteractive_root` from `scripts/lib/noninteractive_root.sh`. Do not write raw `sudo apt-get`: under Ubuntu's `Defaults use_pty`, when `run_benchmark.sh` output is redirected to a log while stdin is still a terminal, sudo gives apt-get a hidden pty, apt-get stops on SIGTTOU while restoring it, and the caller waits forever. The helper runs directly as root, replaces a terminal stdin with /dev/null (pipes and heredocs are kept), and ignores SIGTTOU.

`apt-get update` should be performed only when installation is required. ROCm-specific installation remains exclusively governed by `docs/rocm-reboot-install-contract.md` and `scripts/lib/rocm_install.sh`.

## Verification and failure behavior

After installation, `setup.sh` must verify every required package and command. It must fail with an actionable message identifying the unavailable prerequisite and remediation if provisioning or verification fails.

For source trees that contain `configure.ac`, `setup.sh` must provision and verify `autoconf`, `automake`, `libtoolize`, and `make`. Before invoking a generated `install.sh`, `scripts/build.sh` must detect missing generated libtool metadata such as `ltmain.sh` and bootstrap it with the repository's supported autotools flow (for example, `libtoolize --force --copy` followed by `autoreconf -fi`). Do not assume a vendored dependency has already generated `ltmain.sh`.

When `scripts/build.sh` or a Makefile invokes `hipcc`, that script must be self-contained: source `scripts/lib/hipcc_host_gcc.sh` (copied into every generated repository) or pass `--gcc-install-dir` to a GCC 13/14/15 install dir that still ships libstdc++ headers. `scripts/lib/common.sh` also sources the helper so `setup.sh` and `run_benchmark.sh` export `HIPCC_COMPILE_FLAGS_APPEND` into child `bash scripts/build.sh` processes. A bare `hipcc -O2 src/foo.cpp` is not acceptable on Ubuntu 26.04.

Setup must create a successful setup/build marker only after all checks pass. `run_benchmark.sh` must refuse to run when that marker is absent or stale for the generated repository's setup contract.

For Python workloads that build Rust extensions, the distribution `cargo` package may be too old for the workload's Rust edition. Setup must select the current stable toolchain through `rustup`, prepend `${HOME}/.cargo/bin` to `PATH`, and verify `cargo --version` before building. For protobuf-backed extensions, setup must verify `protoc` before invoking pip.

For ROCm PyTorch workloads, setup must install Torch and torchvision from the official ROCm wheel index before installing framework packages that declare Torch dependencies. It must reject CUDA wheels (`+cu*`) and verify `torch.version.hip`, `torch.cuda.is_available()`, and at least one visible GPU before completion.

For FAISS ROCm source builds, setup must provision and verify the conditional FAISS prerequisites, configure `FAISS_ENABLE_GPU=ON` and `FAISS_ENABLE_ROCM=ON` for the selected GPU target, and verify that the installed Python module exposes `StandardGpuResources` and at least one GPU. A CPU-only `faiss-cpu` package is valid only for an explicitly selected CPU retrieval mode.

For SGLang on ROCm, setup must install AMD's AITER from its official repository with recursive submodules after the verified ROCm Torch pair, set `PYTORCH_ROCM_ARCH` to the target GPU architecture, and export `SGLANG_USE_AITER=1` before importing or launching SGLang. The public PyPI package named `aiter` is not a substitute for AMD AITER. The canonical `setup_rocm_reboot_skeleton.sh` auto-enables `BENCHMARK_INSTALL_SGLANG=1` and `BENCHMARK_INSTALL_AITER=1` when `Framework` names SGLang. Verify `import aiter` and `torch.version.hip` before writing the setup-complete marker. LLM Serving runners must call `wait_for_server` (default 600 s).

For a GPU workload, “all checks pass” includes verification that the expected ROCm/HIP runtime and real GPU executable are available. If an operator uses an explicit skip flag, setup must record that the GPU installation was skipped and must not present the fallback marker as a full GPU setup.

## Documentation

Generated `README.md` must list the host packages provisioned by `setup.sh`, including conditional packages selected from the workload implementation.
