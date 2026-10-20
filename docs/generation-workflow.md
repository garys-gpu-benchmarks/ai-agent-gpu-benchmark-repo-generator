# Generation Workflow

Template release: `Project37_TEMPLATE_0_02_20260706a`

This document is the authoritative five-phase workflow for generating a new workload repository from the template.

## Phase 0 - Extract and Validate `benchmark_specification.json`

1. Read one or more workload numbers, the optional `Legacy: <directory>` line, and any optional remote VM login command from the directly submitted prompt attached to `docs/AI_AGENT_INSTRUCTIONS.md`. Accept comma-separated lists, `and` lists, `ALL`, and inclusive `through`, `to`, or hyphen ranges. Before Phase 0, record the prompt in the project root as `AI_AGENT_PROMPT_SUBMITTED_<WORKLOADS>_<UTC_TIMESTAMP>.md` without overwriting an existing artifact. Derive `WORKLOAD_NAME` from the workbook during extraction; do not require it in the submitted prompt.

> **Generation-time only — not part of the generated repository.** If the supplied remote login command contains an IPv4 address, remote validation is mandatory. For each workload, load the completed local repository onto that VM, install it there, run its self-check, and execute its smoke benchmark there before marking the workload complete. The VM is never a runtime deployment destination for the finished local repository (see `ARCHITECTURE.md` → "Two execution contexts" and `AGENTS.md` § 29.1).

When it includes an IPv4 address, the command is a mandatory external validation target. It does not authorize a destructive rebuild. Ask the user for explicit confirmation before invoking `scripts/refresh_remote_vm.sh`; otherwise use the existing VM. After the local repository is created, copy it to the VM, set every extracted directory to `0755` (`drwxr-xr-x`) — a Windows `tar` extract is typically `0777` / lime-green in `ls` — then run `bash setup.sh --assume-yes`, run `bash scripts/self_check_generated_repo.sh`, and run `bash run_benchmark.sh --profile smoke --validate` on the VM. `scripts/create_one_workload.py` uses Git Bash + OpenSSH on Windows (never WSL bash), resumes after a setup reboot, and applies `find /opt/benchmarks/<Workload Number>-<Repo Name> -type d -exec chmod 755 {} +` after extract. Retry with `--validate-only --reuse-remote-env` so remote `.venv` and `.cache` are kept. After a confirmed rebuild, run the supplied SSH login command once; the expected host-identification failure indicates that the old key is still cached. Then remove the stale key and reconnect:

   ```bash
   ssh -i /path/to/.ssh/<amd_ssh_key> root@<REMOTE_HOST_IP>
   ssh-keygen -R <REMOTE_HOST_IP>
   ssh -i /path/to/.ssh/<amd_ssh_key> root@<REMOTE_HOST_IP>
   ```

Answer `yes` to accept the new ED25519 host key, and verify the login banner matches the workload `OS Version` (`Ubuntu 24.04` or `Ubuntu 26.04`) before remote installation or smoke testing.
2. Record the current UTC timestamp as `generation_started_at`. This begins the repository-generation timing interval.
3. Confirm `BenchmarkSpecDefinitions.xlsx` exists using an exact filesystem check from `<template-directory>/`. Do not conclude the workbook is missing based only on glob/search results.

```bash
pwd
ls -la config
test -f BenchmarkSpecDefinitions.xlsx
```

4. Run:

```bash
python3 scripts/extract_benchmark_definition.py \
  --workload <WORKLOAD_NUMBER> \
  --matrix BenchmarkSpecDefinitions.xlsx \
  --output benchmark_specification.json
```

5. Validate the result against machine-checkable contracts:

```bash
python3 scripts/validate_template_inputs.py \
  --benchmark-specification benchmark_specification.json \
  --benchmark-schema schemas/benchmark_specification.schema.json
```

6. Show or otherwise retain the complete `benchmark_specification.json` for traceability. Confirm it includes `Profile Parameter Values` from the `Parameters_SmokeBaselineExtend` sheet. Do not invent smoke/baseline/extended sweep numbers. `Workload_Definitions` command columns are generated display; author values on `Parameters_SmokeBaselineExtend` and refresh commands with `python scripts/sync_matrix_profile_commands.py`.
7. After validation, read `Workload Number` and `Repo Name` from the copied and validated `benchmark_specification.json`, and create the generated repository as a sibling of the source template directory under the project root using `<Workload Number>-<Repo Name>` (for example: `<project-root>/113-sys-bench-gups-random-memory`, not `<project-root>/<template-directory>/<repo-name>`).
8. Before continuing, create a complete copy of the source template at `<project-root>/<workload-number>_<repo-name>/<source-template-name>_copy/`. This nested copy is the active template root for all remaining phases. It is removed once the workload passes (`scripts/create_one_workload.py` does this automatically; otherwise run `python3 scripts/remove_template_copy.py --repo-root <project-root>/<Workload Number>-<Repo Name>` from the source template). The generated repository root is the parent directory containing the active copy and all generated workload files. Generated documents, implementation files, configuration, and results must be written at that repository root, never inside the active template copy.
9. Populate the generated repository root with required shared template files (`AGENTS.md`, `.claude/CLAUDE.md`, `templates/PRD_TEMPLATE.md`, `templates/SPEC_TEMPLATE.md`, `templates/README_TEMPLATE.md`, `docs/SUBMISSION_CHECKLIST.md`, `schemas/`, `docs/`, `scripts/`, `.gitignore`, `.gitattributes`, root `LICENSE`, and `legal/NOTICE`) before generating workload-specific artifacts. Install workload-specific GitHub community files from `docs/examples/generated-repo-github/` and render the two CI caller workflows from `templates/workload/.github/workflows/` and `config/ci_contract.yaml`; do not copy generator-specific `.github/` guidance into the workload repository. Do not write a root `CLAUDE.md`.
10. For a multi-workload chat prompt, run the entry point once. It calls the official driver for each workload in order and does not take `--remote-root`:

```bash
MSYS_NO_PATHCONV=1 python3 scripts/run_from_prompt.py --prompt-file ../AI_AGENT_PROMPT_SUBMITTED_<WORKLOADS>_<UTC_TIMESTAMP>.md
```

Run it from the generator directory in Git Bash (Windows) or bash, exactly as written. `python3` is the interpreter that passes `scripts/generation_host_preflight.py` (Python 3.10+ with PyYAML); if a different one is first on `PATH`, put that interpreter's full path in its place (preflight prints the full command with it when it fails). `MSYS_NO_PATHCONV=1` stops Git Bash from rewriting paths. Save the prompt in the project root (the generator's parent) and pass it as the relative `../` path, never a `C:\...` or `/c/...` path.

`scripts/create_one_workload.py` remains the per-workload driver. Use it directly only to retry with `--validate-only`. A single-workload invocation is:

```bash
python3 scripts/create_one_workload.py \
  --prompt-file <SUBMITTED_PROMPT_FILE> \
  --workload <WORKLOAD_NUMBER>
```

That script calls `create_generated_repo.py`, then remote-validates and records the workload. It catches per-workload failures without `SystemExit` so one miss cannot skip the rest of the batch. Do **not** call `scripts/create_generated_batch.py` from the AI Coding Agent chatbox path, and do **not** create later workload directories until the current workload is finished (checklist + local smoke + remote smoke when applicable), failed with user notification, abandoned by agent judgment, or timed out after 60 minutes of calendar time from when work on that workload started. A user status question is not a stop signal: answer briefly and continue the current unfinished workload in the same turn; do not wait for the user to say "resume." After a workload is recorded, immediately start the next remaining requested workload in the same turn. Keep one submitted-prompt artifact for the full request and append each finished workload to `<project-root>/batch_generation_manifest.json` as it completes. A confirmed remote refresh occurs once before the first workload; otherwise the manifest records `not_requested`. After create, change into the nested active template copy before performing any remaining generation action. Init copies component directories from `config/implementation_packs.yaml` using Workload Number and GPU Vendor (not a workbook Implementation Pack column), applies mixins from `apply_when`, and writes `results/overlay_lock.json` plus `results/component_leftover_work.md`. Setup skeleton is `Execution Domain` first (`CPU / System` → `setup_cpu_system_skeleton.sh`) then `GPU Vendor` (`AMD` → ROCm skeleton, `NVIDIA` → NVIDIA skeleton). Leave batch `generation_finished_at` null until the last requested workload is recorded.
11. Apply template copy exclusions in the generated repository root:
- remove `BenchmarkSpecDefinitions.xlsx` (template-only source file),
- remove any template-only helper artifacts not required by `docs/repository-template.md`.
12. The generated repository is local-runtime only. Do not generate or document remote SSH execution paths inside it. If the submitted prompt includes a remote VM login command with an IPv4 address, mandatory generation-time validation must load the repository onto that VM, install it there, run its self-check, and run its smoke benchmark there after the local repository is created. The local repository remains the authoritative output. Develop the code in the local directory (a sibling of `ai-agent-gpu-benchmark-repo-generator`), and copy it to the remote VM for testing. Do not copy anything from the VM back to the local directory. If a remote test fails, edit the local sibling and copy that local tree to the VM again. Do not pass `--project-root /root` or treat the VM home as project root. `.venv/`, `.cache/`, setup markers, smoke `results/raw`, compiled `build/` products, fio `data/`, cloned `third_party/` builds, and downloaded weights or `.deb` files are validation-host runtime state; they must not appear in the created local repository. A refresh is destructive and requires explicit confirmation; do not embed its command, credentials, or remote IP in the generated repository.
13. An implementation component is reusable template source, is named by capability rather than workload number, and must contain every deterministic asset it declares; do not rely on untracked files from a prior generation.
14. Generation uses the repository-local `.venv`. The AI coding agent may run `setup.sh`, install Python packages, or perform workload provisioning at its discretion. For a specific interpreter, set `BENCHMARK_PYTHON`, such as `BENCHMARK_PYTHON=/usr/bin/python3.13`. `setup.sh` creates `.venv` idempotently and must never install benchmark packages globally.
14. After implementation, create `benchmark_actual.csv` from the designated workload row in `BenchmarkSpecDefinitions.xlsx`. Shift headers and original values one column right, use rows labeled `Original` and `Actual`, add a fourth row containing `Changed` for divergent cells, and populate successive `InstalledTool_NN: Version` cells with observed tool versions. Row 3 must contain replacement cell values in imperative form, not commentary about divergence or unimplemented behavior. Write the file as UTF-8 with BOM for Excel compatibility.

### Generated-repo minimum file matrix

Before starting Phase 2 content generation, confirm this minimum set exists under `<REPO_NAME>/`:

- `setup.sh`
- `run_benchmark.sh`
- `requirements.txt`
- `config/benchmark_config.yaml` (initial `sweep:` written by `scripts/generate_benchmark_config.py` from `Profile Parameter Values`)
- `scripts/build.sh`
- `scripts/parse_results.py`
- `scripts/validate_results.py`
- `scripts/self_check_generated_repo.sh`
- `results/generation_manifest.json`
- `results/raw/.gitkeep`
- `results/parsed/.gitkeep`
- `tests/fixtures/.gitkeep`
- `.gitattributes`
- `.claude/CLAUDE.md`

## Phase 1 - Read Source Files in Priority Order

Read and internalize:

1. Root-level `benchmark_specification.json` (template extraction artifact)
2. The directly submitted generation prompt and `docs/AI_AGENT_INSTRUCTIONS.md`
3. `AGENTS.md`
4. `.claude/CLAUDE.md`
5. `templates/PRD_TEMPLATE.md`
6. `templates/SPEC_TEMPLATE.md`
7. `templates/README_TEMPLATE.md`
8. `docs/repository-template.md`
9. `docs/machine-checkable-contracts.md`
10. `docs/host-prerequisite-contract.md`
11. `docs/run-output-contract.md`
12. `docs/raw-output-parser-contract.md`
13. `docs/rocm-reboot-install-contract.md`
14. `docs/rocm-pytorch-install-contract.md`
14a. `docs/nvidia-pytorch-install-contract.md` when `GPU Vendor` is NVIDIA
15. `config/hardware_profile.mi300x.yaml`
16. `docs/SUBMISSION_CHECKLIST.md`
17. `implementation_components/README.md` (automatic overlay discovery, mixins, `gate.json`; `results/overlay_lock.json` is a fingerprint — rewrite it only to store the SHA-256 of a deliberate repair whose sibling bytes also match `implementation_components/<id>/files/`)
17a. `scripts/generation_host_preflight.py` before extraction; `results/component_resolution.json` after init

## Phase 2 - Generate PRD/SPEC/README

Generate:

- `<REPO_NAME>/PRD.md` from `templates/PRD_TEMPLATE.md`
- `<REPO_NAME>/SPEC.md` from `templates/SPEC_TEMPLATE.md`
- `<REPO_NAME>/README.md` from `templates/README_TEMPLATE.md`

Use exact-match field substitutions from `benchmark_specification.json`.

README generation rule: Quick Start must include `bash scripts/build.sh` only when `benchmark_specification.json` indicates an actual compile/build step. If no build is required, omit `scripts/build.sh` from Quick Start and Installation command blocks.

## Phase 3 - Generate Only Required Workload Files

- Apply `docs/host-prerequisite-contract.md` when generating `setup.sh` and `docs/run-output-contract.md` when generating `run_benchmark.sh`. These are normative implementation contracts; this document defines when they apply.
- Every generated `run_benchmark.sh` must invoke `scripts/ensure_setup.sh` before workload execution. Handle `--help` first with the `usage()` page in `docs/run-output-contract.md` so help exits before setup. The guard performs basic setup-on-demand when `.setup_state` is absent, passes `--assume-yes` only when supported, and stops with a rerun instruction if reboot-driven setup has not completed. It must not implement automatic post-reboot benchmark continuation.
- Follow `docs/repository-template.md` for layout inside `<REPO_NAME>/`.
- Generate only workload-relevant files inside `<REPO_NAME>/`.
- Use `scripts/lib/rocm_install.sh` verbatim when ROCm setup is required. That dispatcher sources `scripts/lib/rocm_install_24_04.sh` or `scripts/lib/rocm_install_26_04.sh` from the host Ubuntu release; do not rewrite those libraries.
- When calling the protected `rocm_compile_rocblas_bench` function, invoke it from `${HOME}` because the protected library's clone step is relative to its current working directory while its build path is `${HOME}/rocBLAS`.
- Initialize `HOME` and `LD_LIBRARY_PATH` before calling protected installer functions; systemd services provide a minimal environment and `set -u` must not turn an unset library path into a build failure.
- Do not add a separate unit-test harness.
- Implement local-only execution support in generated harness scripts.
- Do not add remote prompts, SSH key/IP defaults, or remote execution flags.
- Treat `docs/remote-execution-pattern.md` as deprecated historical context only.
- For MPI-backed local workloads, detect `EUID=0` and pass the MPI implementation's explicit root override (for Open MPI, `--allow-run-as-root`) only in that case. For Open MPI stacks using PRRTE, also set `OMPI_ALLOW_RUN_AS_ROOT=1`, `OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1`, `PRTE_ALLOW_RUN_AS_ROOT=1`, and `PRTE_ALLOW_RUN_AS_ROOT_CONFIRM=1`. Persist the effective command and warn the operator so a launcher refusal is not misreported as a parser failure.
- For workflows that issue reboot commands, implement explicit local resume behavior:
- local mode: save resume-state and continue after user logs back in.
- Reference `docs/reboot-resume-pattern.md`, `docs/rocm-reboot-install-contract.md`, and helper libraries under `scripts/lib/` when implementing reboot-sensitive phases.
- For ROCm workloads using PyTorch, follow `docs/rocm-pytorch-install-contract.md`: install pinned or configurable PyTorch packages from the official ROCm wheel index, never unconstrained default-PyPI wheels, and verify HIP plus GPU availability before setup completion.
- When `GPU Vendor` is NVIDIA, follow `docs/nvidia-pytorch-install-contract.md`. `init_generated_repo.py` copies `scripts/templates/setup_nvidia_skeleton.sh` as `setup.sh` and does **not** recopy it after overlays, so vLLM/SGLang overlay `setup.sh` is kept. The NVIDIA skeleton calls `scripts/install_pytorch_nvidia.sh` for PyTorch/JAX/Transformers, then overlay helpers, then `scripts/build.sh`. Refuse `.setup_state` if overlay binaries (`bin/cublas_gemm`, `bin/cudnn_conv`, `bin/stream`/`build/stream`, `bin/numa_sweep`, `bin/babelstream`) are missing. Do not invent a generic probe-first `build.sh`. Do not write a dummy `collect_workload.py` when an overlay collector exists. Create writes a thin adapter when the overlay collector is named `collect_*.py` and the harness still calls `scripts/collect_workload.py`.
- When `GPU Vendor` is AMD, follow `docs/rocm-pytorch-install-contract.md`. Init recopies `setup_rocm_reboot_skeleton.sh` after overlays. Call overlay `scripts/collect_workload.py` (`--raw-file`); do not invent a stub CSV. After overlays, init materializes empty parse/validate/run_benchmark harness files only. Do not call `install_pytorch_nvidia.sh`.
- Before choosing PyTorch or torchvision defaults, query the configured ROCm wheel index for both packages and verify a compatible published pair. Do not reuse version pins from this template's example blindly: an unavailable pin can fail only after ROCm installation and reboot-resume have completed. Keep the verified versions configurable through environment variables and document the exact tested pair in the generated README.
- For ROCm LLM Serving workloads, install AMD AITER from the `amd-aiter` wheel (`import aiter`) and compile SGLang when Framework includes sglang (`BENCHMARK_COMPILE_SGLANG=1` is the default). Compile `sgl-kernel` from the source tree with `setup_rocm.py` for the target GFX architecture. Do not install the generic PyPI `aiter` package or a CUDA `sgl_kernel` wheel. Setup must verify `import aiter` and `import sglang` before writing the setup-complete marker. Do not warn-and-continue if `sglang` is missing.
- For vLLM workloads (128/129), pass `--dtype bfloat16` to `vllm.entrypoints.openai.api_server`. vLLM 0.26 rejects `bf16`. Map `bf16` → `bfloat16` if yaml still uses the short token.
- For ROCm SGLang installations, replace the cloned source tree's generic `python/pyproject.toml` with upstream `python/pyproject_other.toml` before installing SGLang, and install the `[all_hip]` extra. Do not use `pip install --no-deps -e python`: it omits runtime modules such as `orjson` and `pybase64`, while generic metadata can replace the verified ROCm PyTorch wheel with a CUDA wheel. Always install `orjson`, `pybase64`, `starlette`, and `pyzmq`, patch `qwen3_asr` `AutoConfig.register(..., exist_ok=True)`, and verify `python -m sglang.launch_server --help` even when `import sglang` already succeeds. Re-verify `torch.version.hip`, `torch.cuda.is_available()`, and visible GPU count after installation.
- Repeat that ROCm verification after installing SGLang, vLLM, or other framework extras; dependency resolution can silently replace the ROCm wheel. Do not write the setup-complete marker until the final HIP/GPU check passes.
- Before remote setup or smoke testing, run `bash scripts/self_check_generated_repo.sh`. It verifies canonical shell helpers, parser raw-output contracts, the active template copy, required workload files, and that `README.md` is not a generate-time stub (Prerequisites + mermaid + template headings).
- SGLang readiness may remain HTTP 503 during model loading and first-use AITER JIT compilation. LLM-serving runners must call `wait_for_server` from `scripts/lib/common.sh` (default 600 seconds). Treat HTTP 503 as not ready. Do not hardcode 180 seconds.
- After argument parsing, call `begin_benchmark_run "${profile}"` so `die()` appends a `/var/opt/benchmarks/runtime_ledger.csv` row on failure. After `ensure_setup.sh` returns, call `mark_benchmark_measure_start` so `total_runtime_mm_ss` starts at the benchmark. A setup failure still uses the `begin_benchmark_run` timestamp. Call `finish_benchmark_run` after a successful ledger write.
- SGLang `bench_serving` labels end-to-end metrics as `Mean/Median/P95/P99 E2E Latency` and labels TPOT separately from ITL. Parsers must map E2E aliases explicitly and never use ITL values as TPOT values.
- Implement standard runtime profiles in generated `run_benchmark.sh`:
- `--profile smoke` (<= ~60s target),
- `--profile baseline` (~3-5 min target),
- `--profile extended` (~10-15 min target),
- with aliases `--smoke`, `--baseline`, and `--extended`.
- Load those profile values from `config/benchmark_config.yaml`, which `scripts/generate_benchmark_config.py` seeds from `Profile Parameter Values`. Do not invent sizes, iterations, or dtypes. `Workload_Definitions` command columns are generated from `Parameters_SmokeBaselineExtend`; sweep/list flags in those cells are documentary.
- Implement `bash run_benchmark.sh --help` from `scripts/templates/run_benchmark_help_skeleton.sh` and `docs/run-output-contract.md`. Print a `usage()` page, not the file header. Profile aliases must read `Run smoke profile`, `Run baseline profile`, and `Run extended profile`. `--raw-file` is an existing file for `--phase3`. Value-taking flags must be documented as taking values. Also implement `--specification` (alias `--matrix-definition`) to print this workload's `benchmark_specification.json` field/value table and exit before setup.
- Treat every application, tool, utility, program, library, language runtime, and framework named in the workbook's `Software Framework` column (exposed as `Framework` in `benchmark_specification.json`) as a mandatory installation requirement. Parse the complete field, install every listed item, and verify each item's executable, import, package, or version marker during `setup.sh` and before `run_benchmark.sh` proceeds. Do not omit an item because it seems optional, is only used by a helper, or is transitively installed by another package. Additional transitive dependencies may be installed as needed, but they do not replace explicit installation and verification of every listed item.
- For LLM Serving workloads, the no-argument path is `smoke` (tiny local server). `--baseline` and `--extended` start the real model server, wait for readiness, run the client, persist artifacts, and stop the server automatically. `--baseline` targets approximately 3–5 minutes. `scripts/generate_benchmark_config.py` still seeds yaml `sweep.profile: baseline` for that domain so `self_check` can distinguish yaml default from CLI default. Separate server/client terminals are optional troubleshooting modes, not the primary user workflow.
- Do not hard-code an old vLLM version for ROCm unless its wheel and compiled extension have been tested against the selected PyTorch/HIP pair. Prefer the vendor ROCm index's current compatible wheel and verify the native extension before launching the server.
- Metadata collection must run on the local host only and save local artifacts (masked `env_variables.txt` and end-of-run `journal_warnings.txt` from `journalctl -p warning` via `capture_journal_warnings`). Do not write `system_info.txt`. Every generated repository must include `scripts/collect_hw_sw_info.sh`, generated from `config/hw_sw_info_commands.xlsx` by `scripts/generate_collect_hw_sw_info.sh`. After the workload completes, invoke `bash scripts/collect_hw_sw_info.sh "${RUN_DIR}"` to create `hardware_info.txt`, `software_info.txt`, and `errors_info.txt` in the per-run artifact directory. The collector must include the Excel-selected General and detected-vendor commands in each `DESCRIPTION : Commands To Be Run` section, record timestamp and status for every executed command, and continue after unavailable probes; failed probes belong in `errors_info.txt` and do not replace the benchmark exit status.
- Probe optional benchmark-tool flags against the installed executable. Do not assume flags shown in a matrix example are accepted by every tool release; omit unsupported optional flags with a warning and persist the effective command.
- For workloads whose required installation path includes ROCm repository and/or RVS installation, `setup.sh` should execute those required install functions from `scripts/lib/rocm_install.sh` by default (idempotent), with explicit skip flags available for advanced operators.
- For workloads whose setup may call reboot-capable ROCm install functions, generated `setup.sh` must follow `docs/rocm-reboot-install-contract.md`. In particular, install and enable a local systemd oneshot auto-resume service before `rocm_install_runtime`, resume with `--assume-yes --resume-from-service` after reboot, preserve `results/install_status.txt` and `results/install_commands.txt`, and remove the service only after successful completion.
- For every ROCm workload, materialize `scripts/templates/setup_rocm_reboot_skeleton.sh` as `setup.sh` before making workload-specific edits. Do not write a new reboot controller. The skeleton is the canonical implementation of the numbered ROCm routine. It detects Ubuntu and pins ROCm `10.1.0` and amdgpu `31.60` on both 24.04 and 26.04, with `GFX_TARGET=gfx942`. Benchmark virtualenvs use uv-managed CPython 3.14. Generation may only set dependency-specific variables and the explicit `BENCHMARK_SKIP_RVS` policy; it must not change the state machine, resume service, lock, status hooks, stage ordering, or cleanup behavior.
- The canonical skeleton must be used for the ordered runtime flow. Both Ubuntu releases install amdgpu-dkms `31.60` from `https://repo.radeon.com/amdgpu/31.60/ubuntu` and ROCm `10.1.0` (`amdrocm10.1-<gfx>` plus `amdrocm-core-dev10.1-<gfx>`) from `https://stable.repo.amd.com/rocm/core/packages/`. RVS is the apt package `amdrocm10-rvs` `1.6.131-844`. Callers source `scripts/lib/rocm_install.sh`; do not duplicate or reorder those steps in generated repositories.
- Before completion, generated ROCm repositories must retain the canonical state-machine markers: `install_resume_service`, `install_status_log_phase`, `install_status_log_step`, `flock`, `.rocm_runtime_stage.env`, `--resume-from-service`, `TimeoutStartSec=0`, `KillMode=process`, and `cleanup_resume_service`.
- For reboot-driven ROCm setup flows, generated `setup.sh` must maintain a chronological install status log at `results/install_status.txt`, append phase and successful step entries as steps complete, and mirror that status block into `/etc/motd` while installation is in progress. It must also append each executed install command to `results/install_commands.txt` as a bare command line (no timestamp, step number, or comment) and preserve that file across reboot resume.
- For local first-run reboot flows, generated `setup.sh` should print a clear Enter-to-continue notice saying the amdgpu driver is reloaded in place of a reboot and that setup reboots at most once (only if the reload cannot be verified, and then only after everything else is installed), auto-resume behavior, the install-status file path, and that completion is recorded in `/etc/motd` (no `wall` broadcast).
- When the driver reload fails, generated setup (which exports `ROCM_DEFER_REBOOT=1`) does not reboot at that point: it installs every remaining package, wheel and source build, skips only the checks that need a working GPU, and reboots once at the end. The `scripts/build.sh` workload build and the GPU checks run in the systemd resume invocation after that reboot, which is the only path that completes setup. With `ROCM_DEFER_REBOOT=0`, setup must exit right after a protected ROCm runtime function persists a reboot stage, before later repository or workload phases. Every resume must synchronize the full accumulated install-status log into `/etc/motd`, including the final `SETUP complete` entry.
- In generated `setup.sh`, ensure Python venv prerequisites are installed idempotently on fresh Ubuntu images before invoking the selected `${BENCHMARK_PYTHON:-python3} -m venv` (for example, install `python3-venv` and the matching versioned `python3.x-venv` package when needed).
- Before generating `setup.sh`, derive the complete host prerequisite set from `benchmark_specification.json` and the workload implementation. For compiled C/C++ workloads this includes a compiler and build tools (normally `build-essential`, `gcc`, and `make`); for HIP/`hipcc` workloads on Ubuntu 26.04 this also includes `g++-15` and a `scripts/build.sh` that sources `scripts/lib/hipcc_host_gcc.sh` or passes `--gcc-install-dir=/usr/lib/gcc/x86_64-linux-gnu/15`; for autotools source trees containing `configure.ac`, it also includes `autoconf`, `automake`, `libtool`, `libtool-bin`, `m4`, `pkg-config`, `flex`, `bison`, and `cmake`; for NUMA workloads it includes `libnuma-dev` and `numactl`; source-based workloads include `git`; and all SQLite-exporting workloads include the `sqlite3` CLI. Generated setup must detect missing commands/packages, install them idempotently with `run_privileged env DEBIAN_FRONTEND=noninteractive apt-get` (`scripts/lib/noninteractive_root.sh`; not raw `sudo`), verify them, and fail clearly if installation cannot complete. A failed setup/build must prevent benchmark execution rather than allowing `run_benchmark.sh` to continue. For 120/320 keep the `linpack-rochpl-amd` overlay; do not allocate `host_a(n * n)`.
- Before invoking a generated `install.sh` for a source tree with `configure.ac`, generated build logic must detect missing `ltmain.sh` and bootstrap the autotools metadata with the supported `libtoolize`/`autoreconf` flow. Vendored autotools metadata must not be assumed to exist.
- When an installer emits multiple similarly named launchers, generated build logic must select the exact benchmark binary by its documented install path, preserve required helper launchers beside it, and verify each helper is executable. Never select the first filename matching a broad `*benchmark*` pattern.
- `setup.sh` is the complete workload installation entrypoint, not merely a host-prerequisite checker. Before building or marking setup successful, it must install and verify every software component named or implied by `Installation and Execution Summary`, `Framework`, `Runtime Language`, and the generated implementation. For a GPU-targeted `Memory / Transfer`, `GPU Compute / ROCm`, or other ROCm-dependent workload, the default `bash setup.sh` path must execute the applicable protected functions in `scripts/lib/rocm_install.sh` (including ROCm runtime and repository setup when required), then build the real GPU executable with the required compiler/runtime. `--skip-rocm` or equivalent flags may exist only as explicit advanced overrides and must be documented as disabling the full GPU setup; they must never be the implicit default. A CPU fixture or portable fallback may be used only when an explicit skip flag is supplied or when the workload definition is CPU-only.
- The setup completion marker must be written only after all required workload software and the selected execution backend have been installed, verified, and built. `run_benchmark.sh` must reject a run when the full required setup is absent or when setup completed only in an explicitly skipped/fallback mode.
- Before Phase 4 completion, verify the end-of-run summary against `docs/run-output-contract.md`: numbered `Metrics` items must produce exactly one `[INFO]` line each, in source order, with the complete item description, units, and labeled aggregate values from the latest SQLite run. Confirm the fixed wrapper order: Run ID/status, Command submitted, Command fully resolved, Start/Stop/Elapsed, Artifacts, SQLite DB, empty `[INFO]`, Metrics block, trailing empty `[INFO]`. Metrics must not appear above Artifacts or SQLite DB. For workload 112, the five required lines must cover syscall null/read/write/stat/open, context-switch latency, memory-read latency versus working-set size, `bw_mem`, and `bw_pipe`; every named subtest and working-set point must be measured and persisted before it is printed.

Before completion, generate:

- `<REPO_NAME>/GENERATION_REPORT.md`
- `<REPO_NAME>/results/generation_manifest.json`

Record `generation_finished_at` only after all implementation, validation, and checklist gates pass. Calculate the non-negative wall-clock `generation_duration_seconds` from the two timestamps, write all three timing fields to both generated artifacts, and print the timing summary before reporting completion.

After the full requested list is recorded, delete generation-time scratch files from the local project root and from the remote validation host home. Keep the source template, each `<Workload Number>-<Repo Name>/` directory, `AI_AGENT_PROMPT_SUBMITTED_*.md`, and the local `batch_generation_manifest.json`. Remove leftover helpers and logs such as `*_create_start_time.txt`, `workload_identities.txt`, `rocm_pip_constraints.txt`, `_fill_generated_docs.py`, `patch_generated_repo.py`, `finish_one_workload.sh`, `process_range.sh`, `_generation_helpers/`, `batch_process*.log`, `batch_process*.stdout`, `retry*.stdout`, and root-level `*_setup.log`. After the local batch manifest is authoritative, also remove the VM-root copy of that manifest and leftover helpers. Do not delete generated repositories, files inside a generated `results/` tree, or `/var/opt/benchmarks/runtime_ledger.csv`.

Validate manifest:

```bash
python3 scripts/validate_template_inputs.py \
  --generation-manifest <REPO_NAME>/results/generation_manifest.json \
  --generation-schema schemas/generation_report.schema.json
```

## Phase 4 - Final Verification and GitHub Publication Readiness

Before reporting completion, run `bash scripts/check_github_publish_ready.sh`; it must pass. Then remove the nested template copy with `python3 scripts/remove_template_copy.py --repo-root <project-root>/<Workload Number>-<Repo Name>` if the driver has not already done so. The finished workload must be independently publishable and must not depend on the ignored nested `TEMPLATE_*_copy/` directory.

Run all checks in `docs/SUBMISSION_CHECKLIST.md` in order, scoped to `<WORKLOAD_NUMBER>_<REPO_NAME>/` as the generated repository root.

During result review, treat `duration_sec=0` as valid for sub-second runs when summary timestamps are second-rounded, and use aggregate threshold outcomes as the primary pass/fail signal when individual per-sample compliance fields are `0.0` for non-applicable checks.

Then run template-mode smoke checks from the current template directory:

```bash
bash scripts/smoke_check_generated_repo.sh <WORKLOAD_NUMBER>_<REPO_NAME>
```

Then run generated-repo self-checks from generated repo root:

```bash
bash scripts/self_check_generated_repo.sh
```

Report exact pass/fail results. Fix failures before completion.
