# AGENTS.md: "The AI How"; Cross-agent rules for AI coding agents like Claude, Cursor, Codex, Copilot, etc.

This file provides rules for Agentic Code Creation when working in this repository. It establishes coding conventions, repository structure, guardrails, file responsibilities, and output formats. It is intended for AI Coding Agents such as, but not limited to, Claude, Cursor, Codex, Copilot, and Windsurf.


## Document Priority Order

Read repository documents in this strict order before writing any code, tests, or generated output. Re-consult the relevant document whenever you add or modify anything that touches its scope.

**Note on Phase 0:** `benchmark_specification.json` is listed at priority 1 because it governs all implementation decisions. However, it does not exist until Phase 0 creates it via `scripts/extract_benchmark_definition.py`. Do not begin reading Phase 1 documents or writing any code until Phase 0 extraction and schema validation are complete.

| Priority | File | Role |
|---|---|---|
| 1 | `benchmark_specification.json` | **Single source of truth** for all benchmark metadata — wins over every other file on any conflict. Created during Phase 0. |
| 1a | `implementation_components/<component-id>/component.json` and `files/` | Reusable implementation component automatically discovered by manifest selectors evaluated against the benchmark specification. Components may provide deterministic helpers/source files, but workload identity, parameters, metrics, and requirements remain matrix-derived. |
| 2 | Directly submitted generation prompt recorded as `AI_AGENT_PROMPT_SUBMITTED_<WORKLOADS>_<UTC_TIMESTAMP>.md` in the project root | Workload number(s) plus optional legacy-directory and remote-validation details; the full generation workflow is in `AGENTS.md` -> "Generation Workflow" |
| 3 | `AGENTS.md` | **This file** — cross-agent coding rules, schema, CI contract, and MCP configuration |
| 4 | `.claude/CLAUDE.md` | Claude-specific integration notes; shared operating rules are defined here |
| 5 | `templates/PRD_TEMPLATE.md` (source) / `PRD_TEMPLATE.md` (generated repo) | Template + embedded agent instructions for generating `PRD.md` |
| 6 | `templates/SPEC_TEMPLATE.md` (source) / `SPEC_TEMPLATE.md` (generated repo) | Template + embedded agent instructions for generating `SPEC.md` |
| 7 | `templates/README_TEMPLATE.md` (source) / `README_TEMPLATE.md` (generated repo) | Template + embedded agent instructions for generating `README.md` |
| 8 | `PRD.md` / `SPEC.md` / `README.md` | Generated outputs of items 5–7; consult for already-populated context once they exist, but never treat as authoritative over their templates or `benchmark_specification.json` |
| 9 | `docs/repository-template.md` | Canonical directory layout and per-file responsibilities |
| 10 | `docs/generation-workflow.md` | Authoritative Phase 0–4 generation workflow |
| 11 | `docs/machine-checkable-contracts.md` | Schema contracts, validator usage, and generation manifest contract |
| 12 | `docs/host-prerequisite-contract.md` | Host package derivation, installation, and verification contract |
| 13 | `docs/run-output-contract.md` | Required end-of-run benchmark summary format |
| 14 | `docs/raw-output-parser-contract.md` | Required parser behavior for real tool output |
| 15 | `docs/rocm-reboot-install-contract.md` | Required ROCm reboot + systemd auto-resume setup architecture |
| 16 | `docs/rocm-pytorch-install-contract.md` | Required ROCm PyTorch wheel selection and GPU-backed framework verification |
| 17 | `config/hardware_profile.*.yaml` | GPU chip specs and theoretical peak values used for optional threshold or baseline derivation |
| 18 | `docs/SUBMISSION_CHECKLIST.md` | Completion gate — run every item in order before reporting implementation complete |

**Conflict resolution rules:**

- If `benchmark_specification.json` conflicts with any other file, **`benchmark_specification.json` wins**.
- If a generated file (`PRD.md` / `SPEC.md` / `README.md`) conflicts with its own template or with `benchmark_specification.json`, **the template + JSON win** — the generated file is stale and must be regenerated, not hand-edited or treated as authoritative.
- `AGENTS.md` rules apply to **all agents** (Claude, Cursor, Codex, Copilot, Windsurf, and others). Agent-specific behavior that supplements but does not override these rules lives in the corresponding agent file (e.g., `.claude/CLAUDE.md`).


## Repository Purpose

You are working inside a standardized `gpu-bench-*` or `sys-bench-*` benchmark repository. Follow these rules strictly when generating, editing, or refactoring code.

This repository implements **one focused, high-quality benchmark** as part of the larger GPU and system validation and performance characterization suite.

### Output location contract (template mode)

When operating in a template workspace, generate the workload repository at the project root as a sibling of `ai-agent-gpu-benchmark-repo-generator`, in a subdirectory named `<Workload Number>-<Repo Name>` using the workload number and the exact `benchmark_specification.json` `Repo Name` value (for example: `<project-root>/113-sys-bench-gups-random-memory/`). Do not place generated repositories under `ai-agent-gpu-benchmark-repo-generator`. The AI Coding Agent (ie, Cursor) project-root sibling is the created repository only. Develop the code in the local directory, and copy it to the remote VM for testing. Do not copy anything from the VM back to the local directory. Do not pass `--project-root /root` or treat a validation VM home as project root. `.venv/`, `.cache/`, and other setup/smoke artifacts may exist on the validation VM only. Before Phase 0, the workflow creates a complete active copy named `<template-directory>_copy` inside the generated repository; all generation actions run from that nested copy while generated artifacts remain at the generated repository root. Once the workload passes, the nested copy is removed (`scripts/create_one_workload.py` does this automatically; otherwise run `python3 scripts/remove_template_copy.py --repo-root <project-root>/<Workload Number>-<Repo Name>` from the source template), so finished repositories do not contain it. Unless otherwise specified, all "repo root" paths in this document refer to that generated repository root.

Official create contracts (TEMPLATE_00_87):

- Windows host driver is Git Bash + OpenSSH (`scripts/host_exec.py`). Do not call WSL `bash -lc`.
- `scripts/create_one_workload.py` resumes after a setup reboot, and `--validate-only --reuse-remote-env` retries remote validation without wiping `.venv` or `.cache`.
- Create fails if `run_benchmark.sh` calls `scripts/collect_workload.py` and that file is missing after overlays. A named `collect_*.py` gets a harness adapter. An overlay runner that does not call `collect_workload.py` (vLLM, SGLang) is accepted as-is. The first overlay path is not an entry point.
- `generate_benchmark_config.py` merges sweep into a locked overlay YAML; it does not replace `results/overlay_lock.json` files.
- Official docs are `scripts/fill_generated_docs.py` (PRD.md, SPEC.md, README.md, GENERATION_REPORT.md). Leftover `{{` or `[[GENERATE` is a fail.
- Framework install flags come from `config/framework_registry.yaml`. OS/vendor/driver policy comes from `config/platform_policy.yaml` (at most one ROCm reboot: the amdgpu driver is reloaded first, and setup reboots only if the reload cannot be verified, after everything else is installed).
- Metric contract: blank stays `not measured` (not 0.0). `metrics_summary.txt` prints the first parenthetical key (D1). Mashed `p50_p95_p99` displays as p50 (D2). Collectors emit real p50/p95/p99 (D3). SGLang ITL is blank, never copied from TPOT (D4). D5 (streaming TTFT) is out of scope.


## Generation Workflow

The full five-phase workflow is maintained in:

- `docs/generation-workflow.md` — authoritative generation steps (Phase 0–4)
- `docs/machine-checkable-contracts.md` — schema contracts, validator behavior, and generation manifest requirements

Every agent must read those two files before starting generation work and must follow them exactly. Do not collapse phases or skip validation gates.

**Critical contract gates:**

1. Phase 0 must produce a schema-validated `benchmark_specification.json`.
2. `benchmark_specification.json` must pass schema and semantic checks:

 ```bash
 python3 scripts/validate_template_inputs.py \
     --benchmark-specification benchmark_specification.json \
     --benchmark-schema schemas/benchmark_specification.schema.json
   ```

3. Before completion, every generated repository must contain `results/generation_manifest.json` and it must pass:

 ```bash
 python3 scripts/validate_template_inputs.py \
     --generation-manifest results/generation_manifest.json \
     --generation-schema schemas/generation_report.schema.json
   ```

`benchmark_specification.json` remains the single source of truth for workload-specific decisions. If it conflicts with any other file, `benchmark_specification.json` wins.

### Setup and Execution Contracts

The detailed implementation requirements are maintained in:

- `docs/host-prerequisite-contract.md` — `setup.sh` installation, verification, `.venv`, idempotency, and reboot-resume behavior.
- `docs/run-output-contract.md` — `run_benchmark.sh` execution, metadata, raw-output, command-log, parsing, summary, and exit-code behavior.

Generated repositories must satisfy those contracts. Apply requirements conditionally from the validated workload definition: only install ROCm, compile source, monitor hardware, or create build artifacts when the workload requires them. Use `.venv/bin/python` for Python execution and the standardized `.setup_state` and `results/install_status.txt` setup markers.

### Batch Generation

- Accept comma-separated workload lists, `and` lists, `ALL`, and inclusive workload ranges in the submitted prompt.
- Process multi-workload prompts **strictly sequentially** in ascending workload-number order.
- Create only one repository directory at a time with `scripts/create_generated_repo.py --workload <N>`. Do not call `scripts/create_generated_batch.py` from the AI Coding Agent chatbox path. Do not pre-create later workload directories while an earlier workload is unfinished.
- Finish the current workload completely before starting the next: Phases 0–4, checklist gates, local smoke validation, and remote setup/smoke when a VM is supplied.
- On failure, notify the user and continue to the next workload. If further work is no longer beneficial by agent judgment, record `abandoned` and continue. If the workload is still not running successfully after 60 minutes of calendar time from when work on that workload started, record `timed_out`, notify the user, and continue. The 60-minute limit is elapsed calendar time, not accumulated active effort.
- A user status question is not a stop signal. Answer briefly, then immediately continue the current unfinished workload in the same turn. Do not wait for the user to say "resume." The only reasons to stop the current workload are `passed`, `failed`, `abandoned`, or `timed_out`.
- Finishing one workload is not permission to end the turn. Immediately start the next remaining requested workload in the same turn until the full requested list is recorded.
- Keep one submitted-prompt artifact for the full request. Append or update each finished workload in `<project-root>/batch_generation_manifest.json` as it completes (`passed`, `failed`, `abandoned`, or `timed_out`).
- After every requested workload directory is recorded and the batch finish timestamps are stamped, delete generation-time scratch from the local project root and from the remote validation host home (`*_create_start_time.txt`, `workload_identities.txt`, `rocm_pip_constraints.txt`, `_fill_generated_docs.py`, `patch_generated_repo.py`, `finish_one_workload.sh`, `process_range.sh`, `_generation_helpers/`, `batch_process*.log`, `batch_process*.stdout`, `retry*.stdout`, root `*_setup.log`). Keep the template directory, each `<Workload Number>-<Repo Name>/` directory, `AI_AGENT_PROMPT_SUBMITTED_*.md`, and the local `batch_generation_manifest.json`. After that local manifest is authoritative, also remove the VM-root copy of the manifest and leftover helpers so the VM home keeps no helpers. On the VM, generated repositories live in `/opt/benchmarks/<Workload Number>-<Repo Name>` and the ledger is `/var/opt/benchmarks/runtime_ledger.csv`; keep both.
- Refresh a supplied remote validation VM once before the first workload, not once per workload; reuse that VM sequentially.

## Shared Agent Operating Contract

These rules apply to every coding agent, regardless of vendor or model.

- Phase 0 must complete workbook extraction and schema validation before an agent reads Phase 1 source documents, writes code, or generates output. If `benchmark_specification.json` already exists, validate it before using it.
- Preserve the repository architecture, interfaces, schemas, CLI behavior, determinism, and reproducibility unless the user explicitly requests a change. Keep changes minimal, localized, and reversible; avoid speculative refactors.
- Use `benchmark_specification.json` for raw-output formats, unit conversions, dtype tokens, workload parameters, and database schema. Generate `PRD.md`, `SPEC.md`, and `README.md` from their corresponding templates and remove template instruction blocks from outputs.
- In template mode, create the generated repository at the project root as a sibling of `ai-agent-gpu-benchmark-repo-generator`, using `<Workload Number>-<Repo Name>` as its directory name. The AI Coding Agent (ie, Cursor) project-root sibling is the created repository only. Develop the code in the local directory, and copy it to the remote VM for testing. Do not copy anything from the VM back to the local directory. Create `<template-directory>_copy/` inside it as the complete active template copy before beginning Phase 0; run all generation actions from that nested copy. The generated repository root remains the output root: write `PRD.md`, `SPEC.md`, `README.md`, implementation files, configuration, and results beside the nested copy, never inside `TEMPLATE_*_copy/`. Remove the nested copy once the workload passes (`scripts/remove_template_copy.py`). Do not relocate that sibling to `/root` on a validation VM.
- Preserve the standard execution pipeline:

  ```
  setup.sh -> scripts/build.sh -> run_benchmark.sh -> raw output
  -> scripts/parse_results.py -> results/benchmark.db and summary.json
  -> scripts/validate_results.py
  ```

The execution tool and build requirements remain workload-specific and must come from `benchmark_specification.json`.
- Do not modify these shared or authoritative files during normal workload generation: `benchmark_specification.json`, `README.md`, `docs/AI_AGENT_INSTRUCTIONS.md`, `docs/SUBMISSION_CHECKLIST.md`, `docs/repository-template.md`, `scripts/lib/rocm_install.sh`, `scripts/lib/rocm_install_24_04.sh`, `scripts/lib/rocm_install_26_04.sh`, `scripts/lib/noninteractive_root.sh`, `scripts/lib/hipcc_host_gcc.sh`, `templates/PRD_TEMPLATE.md`, `templates/SPEC_TEMPLATE.md`, and `templates/README_TEMPLATE.md`. A user explicitly requesting a change to the template mechanism or shared completion contract is an exception.
- When behavior changes, regenerate the relevant generated documentation from its template, preserve CLI flags and environment overrides, and avoid hard-coding values that belong in `benchmark_specification.json` or configuration YAML.
- Generate `requirements.txt` from the implementation's direct third-party imports and the validated workload framework requirements. Do not add unused or transitive packages. Treat the matrix/profile and direct imports as the dependency contract: install optional packages such as torchvision only when the workload requires them, and report framework-installed transitive packages separately. Keep accelerator packages on their documented vendor-specific installation path rather than unconstrained default PyPI installs. Use tested version bounds or pins where reproducibility requires them, and validate the file with installation, `pip check`, and the repository smoke path inside `.venv`.
- Request clarification before changes that alter benchmark semantics, database schemas, validation contracts, reproducibility, or protected shared templates/contracts.

### Standard Benchmark Commands

Confirm workload-specific requirements in `benchmark_specification.json` before using optional commands. Set `.venv` before Python commands.

```bash
bash setup.sh
bash scripts/build.sh
bash run_benchmark.sh
".venv/bin/python" scripts/validate_results.py
".venv/bin/python" scripts/validate_results.py --seed-fixture
".venv/bin/python" scripts/parse_results.py \
  --raw-file results/raw/<timestamp>.txt
sqlite3 results/benchmark.db "SELECT ...;"
```

## Mandatory Repository Structure

`docs/repository-template.md` is the single source of truth for repository layout — this section does not repeat it. The top-level paths below must exist; do not rename, move, or delete them. See `docs/repository-template.md` for the full annotated tree, per-file descriptions, and any workload-specific variants.

- `run_benchmark.sh` — root-level primary entrypoint
- `setup.sh` — root-level installation and build entrypoint
- `benchmark_specification.json` — single source of truth for benchmark metadata
- `schemas/` — machine-checkable JSON contracts for benchmark definition and generation manifest
- `config/` — sweep parameters, optional thresholds or baselines, machine and hardware-profile definitions
- `docs/` — including `repository-template.md`
- `scripts/` — including `lib/common.sh`
- `src/` — benchmark source or shared utilities
- `tests/` — including `fixtures/.gitkeep`
- `results/` — with `raw/` and `parsed/` subdirectories and `generation_manifest.json`
- `.github/workflows/` — thin CI callers `ci.yml` and `gpu-smoke.yml` (rendered from `config/ci_contract.yaml`)

**Note on `src/` for binary benchmarks:** If the workload uses a pre-compiled binary (e.g., `rocblas-bench`, `babelstream`), `src/` holds shared Python utility modules or a `.gitkeep` sentinel only. Do not generate stub HIP/C++ source if no custom kernel is needed.


## Task

Write complete, production-ready, self-contained code that adheres to the Coding Standards below.

## Execution Domain

Read the `Execution Domain` field from `benchmark_specification.json` first. It contains one of the six values below. Use it to determine installation patterns, metric families, and required validation behavior — do not infer the domain from the workload name or description.

| Execution Domain | Examples | Primary Signals |
|---|---|---|
| `GPU Compute / ROCm` | GEMM, ResNet, TorchBench, rocHPL, MIOpen, JAX, BERT, SDXL, DistilBERT | ROCm required; compute TFLOPS or images/sec primary metric; HIP/C++ or PyTorch-ROCm stack |
| `LLM Serving` | vLLM, SGLang, KV Cache | Inference server + client harness; tokens/sec, TTFT, TPOT primary metrics; model weights required |
| `Memory / Transfer` | BabelStream, hipMemcpy, RCCL | HBM or PCIe bandwidth primary metric; GB/sec dominant unit |
| `CPU / System` | STREAM, lmbench, multichase, FIO, iPerf3, GUPS, NUMA, perf PMU, stress | No ROCm dependency; CPU/DDR/NVMe/network target; latency or bandwidth measured on host |
| `End-to-End Pipeline` | RAG (FAISS + LLM) | Multi-stage workload spanning retrieval, embedding, and generation; e2e latency + retrieval quality metrics |
| `Validation / Correctness` | RVS SDC, PyTorch Tensor Ops, System Config, ROCm Health, System Stress | Pass/fail or error-count primary outcome; correctness or compliance rather than throughput |

**Installation pattern by domain:**

| Execution Domain | ROCm Required | Build Step | Python venv | Model Weights |
|---|---|---|---|---|
| `GPU Compute / ROCm` | Yes | Often (C++/HIP binary or pip) | Yes | No |
| `LLM Serving` | Yes | No (pip install) | Yes | Yes (Hugging Face) |
| `Memory / Transfer` | Yes (GPU targets) / No (CPU targets) | Often (C++/HIP binary) | Yes (parser only) | No |
| `CPU / System` | No | Sometimes (C binary) | Yes (parser only) | No |
| `End-to-End Pipeline` | Yes | No (pip install) | Yes | Yes (Hugging Face) |
| `Validation / Correctness` | Yes (GPU tests) / No (CPU tests) | Sometimes (RVS) | Yes | No |


## Coding Standards

### 1. Detailed Script Headers

Every **script or source file** (`.sh`, `.py`, and any other executable or library source file) must open with a header block, written as a comment in that language's comment syntax, containing: `File`, `Version`, `Author`, `Date`, `Description`, `Execution`, `Options`, `Requirements`, `Environment`, `Dependencies`, `Variables`, `Repository`, `License`.

The `Options:` field is a compact comma-separated inventory of accepted flags. Do not expand it into one-option-per-line descriptions. Operator-facing help for `run_benchmark.sh` is the `usage()` function required by section 20.4 and `docs/run-output-contract.md`.

**Exempt from this rule:** `.json` files (no comment syntax — e.g. `benchmark_specification.json`, `results/summary.json`), `.yaml`/`.yml` config files (document fields/keys with brief inline `#` comments where non-obvious instead), Markdown files, and CI workflow files (`.github/workflows/*.yml` — follow standard GitHub Actions conventions, no header block).

### 2. Clean Structured Code

- Format Bash and Python cleanly with consistent indentation; no commented-out dead code.
- Use clear variable names, logical organization, and consistent style across all files.

### 3. Fully Implemented Code

- Do not generate placeholder code, `TODO` comments, `pass` statements, or `raise NotImplementedError` anywhere.
- Every function must have a complete, working implementation.
- All code paths must be implemented; never use stub or temporary code in production files.

### 4. Standardized Repository Structure

- Maintain the standardized repository structure exactly; do not move `run_benchmark.sh` or rename core directories.
- Keep shared benchmark structure consistent across all `gpu-bench-*` and `sys-bench-*` repositories.
- Change only workload-specific logic between repositories; the orchestration skeleton is shared and immutable.

### 5. Idempotent Installation

- Scripts must be idempotent: repeated execution must not cause errors, duplication, or corruption.
- Check for existing state before creating directories, installing packages, or modifying files.
- Use conditional logic (e.g., `if [ ! -d "path" ]; then mkdir -p "path"; fi`) to prevent re-installation errors.
- `setup.sh` must inspect the workload's declared installation/build requirements and provision missing host prerequisites before creating the virtual environment, compiling, or running the benchmark. This includes the matching `python3-venv` package, compiler/build packages for compiled C/C++ workloads, `git` for source checkout, autotools (`autoconf`, `automake`, `libtool`, `libtool-bin`, `m4`, `pkg-config`, `flex`, `bison`, `cmake`) for source trees that use autotools or CMake, NUMA packages when required, and the `sqlite3` CLI when SQLite exports depend on it. Use `run_privileged env DEBIAN_FRONTEND=noninteractive apt-get` (or `run_noninteractive_root` from `scripts/lib/noninteractive_root.sh`; never raw `sudo apt-get`, which can stop forever on sudo's pty when output is redirected) for idempotent installation, verify every prerequisite afterward, and fail clearly if a prerequisite cannot be installed. Never let `run_benchmark.sh` proceed after a failed setup or build.
- For source trees containing `configure.ac`, `scripts/build.sh` must detect missing generated libtool metadata such as `ltmain.sh` and bootstrap it with the supported autotools flow before invoking a generated installer; do not assume vendored dependencies have already run `libtoolize` or `autoreconf`.
- `setup.sh` is the complete installation and build entrypoint. It must install every software dependency declared or implied by `benchmark_specification.json`, including the workload runtime, libraries, compiler/toolchain, parser dependencies, and benchmark executable. It must not stop after installing generic host packages. For workloads whose execution domain requires ROCm, the default setup path must source and call the applicable protected functions in `scripts/lib/rocm_install.sh`, install the required ROCm runtime/repository components, handle the documented local reboot/resume contract, and build the real HIP executable. A `--skip-rocm`/fallback path is allowed only as an explicit advanced operator override; it must not be the default and must be clearly recorded in setup state. CPU fixtures do not satisfy a GPU workload's normal setup contract.
- For ROCm workloads using PyTorch, never install unconstrained `torch` or `torchvision` from default PyPI. Install pinned or operator-configurable packages from the official ROCm wheel index; install torchvision only when the matrix/profile or implementation requires it. Verify `torch.version.hip is not None`, `torch.cuda.is_available()`, and at least one visible GPU before writing `.setup_state` or any setup completion marker.
- When `GPU Vendor` is NVIDIA, `init_generated_repo.py` materializes `scripts/templates/setup_nvidia_skeleton.sh` as `setup.sh`. That skeleton (or a later NVIDIA overlay `setup.sh` for vLLM/SGLang) must install CUDA wheels through `scripts/install_pytorch_nvidia.sh` when Framework includes PyTorch, JAX, torchvision, or Transformers. Do not put `torch`, `jax`, `vllm`, or `sglang` in `requirements.txt`. Verify `torch.cuda.is_available()` (and `import jax` / `import transformers` when those frameworks apply) before writing `.setup_state`. Never source `scripts/lib/rocm_install.sh` on an NVIDIA host. Never call `install_pytorch_nvidia.sh` from the ROCm setup skeleton.
- A CUDA build identifier such as `+cu130`, a CPU-only wheel, or zero visible GPUs is a setup failure even when `/dev/kfd` and `rocminfo` are present.

### 6. Noninteractive Installation

- Run every privileged command (apt-get, apt, amdgpu-install, tee into /etc, usermod, make install, reboot) through `run_privileged` / `run_noninteractive_root` (`scripts/lib/noninteractive_root.sh`), not raw `sudo`. Under Ubuntu's `Defaults use_pty`, `sudo apt-get` run with stdout redirected and stdin on a terminal stops on SIGTTOU after installing, and the benchmark loop hangs (Ubuntu 26.04, 301 setup step 6). The helper runs directly as root, replaces a terminal stdin with /dev/null, keeps pipes and heredocs, ignores SIGTTOU, and defaults `DEBIAN_FRONTEND=noninteractive`.
- Never prompt for user input during automated installation or execution.
- Use `--assume-yes` or `-y` flags on package managers to avoid hanging on confirmations.

### 7. Full File Retention

- Long files are written to disk in full — never truncate output mid-file.
- Do not use `head`, `tail`, or `sed -n` to limit output; large output is acceptable and expected.
- Always preserve complete file contents when writing or regenerating files.

### 8. Repository Consistency

- Keep shared benchmark structure consistent across all `gpu-bench-*` repositories.
- Ensure core scripts, schemas, and CI patterns are identical except for workload-specific parameters.
- Store workload-specific values in `benchmark_specification.json`, not in hardcoded constants.

### 9. Isolated Python Environment

- Each repository uses its own isolated virtual environment at `<repo-root>/.venv`; never share dependencies implicitly between repositories.
- `setup.sh` creates or reuses `.venv` idempotently and installs Python packages only into that environment.
- `BENCHMARK_PYTHON` optionally selects the system Python executable used to create the environment, such as `/usr/bin/python3.14` or `/usr/bin/python3.13`. The selected interpreter's matching `pythonX.Y-venv` package must be installed before setup.
- An existing `.venv` whose Python major/minor version differs from `BENCHMARK_PYTHON` must be removed before rerunning setup.
- All Python package installation and execution must use `.venv/bin/python`; never use global pip installation or an unrelated environment.
- Create the virtual environment idempotently and activate it in shell scripts that run package-management commands.
- Use `"${BENCHMARK_PYTHON:-python3}" -m venv ".venv"` followed by sourcing its `bin/activate` script before pip operations.

### 10. .gitignore for Results & Virtual Environments

- `.gitignore` must exclude `results/`, `.venv/`, `.venvs/`, `build/`, `*.pyc`, `__pycache__/`, secrets, and credentials.
- `.gitignore` is also the AI Coding Agent (ie, Cursor) project-root deliverable filter. Runtime artifacts listed there may exist on the validation VM after `setup.sh` or smoke. Do not copy them from the VM into the local created repository.
- Never commit compiled binaries, temporary files, `.env` files, or sensitive configuration.
- Use glob patterns to ensure all build artifacts and environment directories are excluded.

### 11. Uniform Benchmark Framework

- Change only workload-specific logic between benchmark repositories.
- The orchestration skeleton (build, run, parse, validate pipeline) is shared and must not be altered.
- Defer workload-specific details to `benchmark_specification.json`, not to runtime scripts.

### 12. "Fast Fail" on Error

- Every Bash script must begin with `set -euo pipefail` at the top of the script.
- `set -euo pipefail` ensures: exit immediately on error (`-e`), fail on undefined variables (`-u`), fail on pipe errors (`-o pipefail`).
- This prevents silent failures and ensures scripts stop at the first problem.

### 13. "Fast Fail" Disabled When Necessary

- Use `set +e` only for expected-failure blocks (e.g., probing an optional resource, checking uptime of a rebooting system, listing optional resources).
- Always restore `set -e` immediately after the exception block using `set -e`.
- Document the reason for disabling fast-fail in an inline comment.

### 14. Final Repository Verification

- Before reporting implementation complete, verify the final repository tree matches the required structure.
- Check that all mandatory directories exist: `config/`, `scripts/`, `src/`, `tests/`, `results/raw/`, `.github/workflows/`.
- Confirm `run_benchmark.sh` is present and executable at the root.

### 15. Grep All Files for Placeholder Code

Before reporting implementation complete, grep all files for `TODO`, `pass`, `raise NotImplementedError`, and `<!-- `. None may remain.

```bash
grep -r "TODO\|raise NotImplementedError\|^[[:space:]]*pass[[:space:]]*$\|<!-- " . --include="*.sh" --include="*.py" --include="*.md"
```

Exit non-zero if any matches are found; fix all instances before completion.

### 16. Confirm .gitignore Exclusions

Before reporting implementation complete, confirm that `results/`, `.venv/`, and `build/` are in `.gitignore`.

```bash
grep -E "^results/|^\.venv/|^build/" .gitignore
```

All three patterns must be present and active.

### 17. Confirm Bash Fast-Fail

Before reporting implementation complete, confirm that `run_benchmark.sh` starts with `set -euo pipefail`.

```bash
head -20 run_benchmark.sh | grep "set -euo pipefail"
```

This line must be present in the first 20 lines of the script.

### 18. Sweep Parameters in Configuration

- **Sweep parameters** (dtypes, sizes, iterations, etc.) must live in `config/benchmark_config.yaml` under the `sweep:` block. Never hardcode sweep values in scripts or test files.
- Parameter **names** come from `Parameter_01` through `Parameter_20`. Parameter **values** come from the workbook `Parameters_SmokeBaselineExtend` sheet (`smoke`, `baseline`, `extended`), extracted as `Profile Parameter Values`. Do not invent profile numbers, sizes, or iteration counts.
- `scripts/create_generated_repo.py` writes the initial `config/benchmark_config.yaml` via `scripts/generate_benchmark_config.py`. Generation may reshape a comma/semicolon cell into a YAML list or map when the runner needs structured sweeps, but must keep the same tokens and numbers.
- `Workload_Definitions` `run_benchmark Command Plus Options for * Run` cells are **generated display**. Author values on `Parameters_SmokeBaselineExtend`, then run `python scripts/sync_matrix_profile_commands.py`. Sweep/list flags in those command cells are documentary; omit them at runtime so yaml expands cases.
- Every parameter must be easily discoverable in one location for reproducibility and modification.

### 19. Optional Pass/Fail Thresholds and Baselines in Configuration

- **Pass/fail thresholds are optional** and must be used only when `benchmark_specification.json` defines a correctness, compliance, health, or explicit pass/fail gate.
- When present, pass/fail thresholds must live in `config/benchmark_config.yaml` under the `thresholds:` block. Never hardcode threshold values in validation scripts.
- Measurement-only benchmark workloads should use a `baselines:` block for expected ranges instead of inventing pass/fail thresholds.
- All threshold and baseline values must derive from hardware peak values, benchmark source data, or published references; do not invent values from memory or guesswork.

### 20. Benchmark Parameters Overridable via CLI

- Every benchmark parameter must be overridable via CLI flag or environment variable in `run_benchmark.sh` without editing any source file.
- Parse command-line arguments in `run_benchmark.sh` to allow `--dtype f16`, `--sweep-size small`, etc.
- Support environment variables (e.g., `BENCHMARK_DTYPE=f16`, `BENCHMARK_SIZE=large`) as an alternative to CLI flags.

### 20.2 Standard Runtime Profiles

- `run_benchmark.sh` should expose profile-oriented run modes via CLI:
- `smoke` (target <= ~60 seconds),
- `baseline` (target ~3-5 minutes),
- `extended` (target ~10-15 minutes).
- Smoke, baseline, and extended numbers come only from the workbook `Parameters_SmokeBaselineExtend` sheet. Do not invent sweep values and do not copy historical timings from older template seeds or CHANGELOG. After generation, `bash run_benchmark.sh --extended` uses the yaml written from `Parameters_SmokeBaselineExtend`.
- Workloads 301–332 and 401–432 `Repo Name` values end with `-ubu2604` (not `-2604`). Local directory and GitHub repository name are `<Workload Number>-<Repo Name>` (example: `301-sys-bench-amd-rocm-stack-validation-ubu2604`).
- NVIDIA 401–432 on Ubuntu 26.04 use CUDA toolkit 13.3 and DCGM `datacenter-gpu-manager-4-cuda13`. Do not install `cuda-drivers` on a host that already has a working NVIDIA driver. Container image is host-native Ubuntu 26.04. Workload 405 and 432 PyTorch pin is `2.13.0+cu130`. Workloads 430 and 431 use a different pin: `torch 2.9.1+cu130`, `torchvision 0.24.1+cu130`, `torchaudio 2.9.1+cu130`, `sglang==0.5.10.post1 --no-deps`. Do not mix those with the vLLM 2.13 stack. Keep the cuDNN overlay `scripts/collect_cudnn_conv.py` (10.0 ms/iter for height > 32). See `docs/nvidia-sglang-install-contract.md`.
- NVIDIA 24.04 230/231 pin is `sglang==0.5.19`, `torch==2.13.0+cu130`, `sglang-kernel==0.4.6.post1` from `https://docs.sglang.ai/whl/cu130/`. Do not leave unpinned `pip install sglang` plus `--force-reinstall torchvision` (that produced torch 2.14 and a dead Hopper `sgl_kernel`). Setup must `import sgl_kernel` and `from sglang.srt.entrypoints.http_server import launch_server`.
- NVIDIA 205: `rc=0` is a successful process status, not a missing metric. Generated `validate_results.py` must skip/allow-zero `rc`. Do not invent tensor pass_rate.
- Linux perf PMU 111/211/311/411: one collector, identical in `linux-perf-pmu-amd` and `linux-perf-pmu-nvidia`. Setup installs `linux-tools-$(uname -r)` when apt has it; prefer `/usr/lib/linux-tools/$(uname -r)/perf` over the `/usr/bin/perf` wrapper. Metrics on every vendor: `instructions_per_cycle_ipc`, `branch_misprediction_rate`, `cache_misses_per_1000_instructions`, `pipeline_stall_pct`, `context_switches_during_workload_switches_s`. Stall event by CPU vendor (`cycle_activity.stalls_total` Intel, `stalled-cycles-backend` AMD). A counter perf cannot read is `na (<reason>)` (PMU denied, not exposed, perf missing), never 0 or a floor; the workload still runs and context switches come from getrusage. Missing stress-ng or a failed workload fails the run. Do not invent IPC.
- NVIDIA 212: `lat_mem_rd 16 128` per-command timeout must be at least 120s (smoke) / 180s (baseline/extended). Catch `TimeoutExpired`. Parse the last table line for memory latency.
- NVIDIA 218: when `src/cudnn_conv.cu` is present, setup must install `libcudnn9-dev-cuda-12` / `libcudnn9-dev-cuda-13` (and headers/runtime) before `scripts/build.sh`. Do not rewrite locked `nvcc -lcudnn`.
- `scripts/ensure_setup.sh` must re-run `setup.sh` when `.setup_state` exists but `.venv/bin/python` is missing. `scripts/lib/common.sh` defaults `HF_HOME` and `PIP_CACHE_DIR` to `$HOME/.cache/...` so overlay runners do not fill a quotaed `/workspace`.
- Do not pass FIO or NUMA sweep-list flags on the CLI (`--rw`, `--block-size`, `--io-depth`, `--working-set-size`). A CLI value is one case and collapses the yaml sweep.
- Workloads 119 and 219 run repository-local `scripts/gemm.py` and `scripts/conv2d.py`. Do not clone or execute official TorchBench model runners.
- Workloads 128, 129, 228, and 229 must pass vLLM `--dtype bfloat16` (vLLM 0.26 rejects `bf16`). Map `bf16` → `bfloat16` if yaml still uses the short token.
- For 127/128/129, 227/228/229, and 327/328/329, smoke may start `scripts/tiny_kv_server.py`. Baseline and extended must start `python -m vllm.entrypoints.openai.api_server` with the yaml model. Do not use tiny_kv for baseline or extended. Keep the 227/228/229 overlays and the AMD `vllm-kvcache-amd`, `vllm-throughput-amd`, and `vllm-token-generation-amd` runners; do not rewrite them. Server `max_model_len` must be at least `input_len + output_len + TOKENIZER_CONTEXT_SLACK` (64), capped at Mistral's 32768. Tight `input+output` is one BOS token short and vLLM returns HTTP 400 before any decode (328/329 baseline 512+18600). The client must clamp `max_tokens` with `TOKENIZER_BOS_SLACK` and print HTTP 400 bodies. On Ubuntu 26.04, vLLM extra-deps pip is non-fatal; always install `uvloop`, `fastapi`, and `aiohttp>=3.13.3` so the API server can start. Filter `flash-attn`, `amd-aiter`, `aiter`, and `amd-quark` from generated extra-deps. Do not pip-build PyPI `flash-attn`. Ubuntu 26.04 wheel pins live in `docs/rocm-pytorch-install-contract.md`.
- NVIDIA vLLM runners (227/427, 228/428, and 229/429) must export `PATH="${REPO_ROOT}/.venv/bin:/usr/local/cuda/bin:/usr/local/cuda-12.6/bin:${PATH}"` before the server starts. FlashInfer's sampler JIT runs `ninja`, and `setup.sh` installs that binary into `.venv/bin`. A CUDA-only `PATH` makes smoke die with `FileNotFoundError: ninja` on a fresh VM until a later SGLang setup installs apt `ninja-build`.
- vLLM throughput and token-generation clients (128/228/328/428 and 129/229/329/429, both vendors) count an SSE choice with N logprob tokens as N output tokens. Empty text with one logprob token still counts. When N>1, split the gap since the previous stamp into N samples and keep the run. Fail when the summed count differs from `usage.completion_tokens`, or when a chunk has text and no logprob tokens. Print `chunk_sizes` only for those still-ambiguous chunks.
- Workloads 130, 230, 330, and 430 are sequential: `scripts/prompt_response_client.py` with exactly one request in flight. Do not use `sglang.bench_serving` or `scripts/bench_serving.py` on these repos. Smoke may start `scripts/tiny_sglang_server.py`. Baseline and extended must start `python -m sglang.launch_server` with Mistral-7B-v0.3 only after `scripts/prefetch_sglang_model.py` prints a snapshot directory. Pass that directory as `--model-path`. A repo id is not safe when the cache has only `consolidated.safetensors`. Keep the 230/430 `run_benchmark.sh` overlay in addition to the leftover-DB parser.
- Workloads 131, 231, 331, and 431 are concurrent: `python -m sglang.bench_serving` or pinned `scripts/bench_serving.py`. Do not use `scripts/prompt_response_client.py` on these repos.
- For 131, 231, 331, and 431, smoke may start `scripts/tiny_sglang_server.py`. Baseline and extended must start `python -m sglang.launch_server` with `mistralai/Mistral-7B-v0.3` (or the yaml `model_name`). Do not use the tiny server for baseline or extended. Do not cap `num_prompts` with `min(num_prompts, concurrency)`.
- Workloads 230 and 231 (NVIDIA, Ubuntu 24.04 / Python 3.12 / CUDA 12.8) must prepend every `.venv/.../nvidia/*/lib` directory to `LD_LIBRARY_PATH` before `import deep_gemm` or `sglang.launch_server` (`libnvrtc.so.13` lives there; `SGLANG_ENABLE_JIT_DEEPGEMM=0` does not help). Launch the server with `bash -c`, not `bash -lc`. Setup must install `ninja` / `ninja-build`. Keep the NVIDIA helper overlays (`scripts/lib/sglang_nvidia_libs.sh`, `scripts/install_sglang_nvidia.sh`) and the 131/231 `run_benchmark.sh` overlays; do not rewrite those runner files. Call `bash scripts/install_sglang_nvidia.sh` from `setup.sh` after the venv exists. The 24.04 branch of that helper keeps the 230/231 recipe (`pip install sglang` plus vision/audio reinstall). Do not apply the 26.04 / Python 3.14 / cu130 SGLang pin to 230/231.
- Workloads 430 and 431 (NVIDIA, Ubuntu 26.04 / Python 3.14 / CUDA 13) must use the 26.04 branch of the same helper: pin `torch==2.9.1+cu130` / `torchvision==0.24.1+cu130` / `torchaudio==2.9.1+cu130`, install `sglang==0.5.10.post1 --no-deps`, skip `outlines` / `outlines_core` (no cp314 wheel), install `sglang-kernel==0.4.1` from `https://docs.sglang.ai/whl/cu130/`, install `flashinfer-python==0.6.7.post3` and `xgrammar==0.1.32`, copy `scripts/sglang_py314_patch.py` + `scripts/sglang_py314.pth`, and run `scripts/install_sglang_launch_deps.py` unless `sglang.launch_server --help` **and** `from sglang.srt.layers.sampler import create_sampler` both succeed. `import sglang` alone is not a pass. A cache that contains only `consolidated.safetensors` is not safe for `--model-path <repo id>`, because SGLang downloads `model.safetensors.index.json` and then ignores the consolidated file. Baseline and extended for 130, 131, 230, 231, 330, 331, 430, and 431 must run `scripts/prefetch_sglang_model.py` and launch with the printed snapshot directory. AMD uses the same script without the CUDA FlashInfer flags. A cache missing `consolidated.safetensors` is still usable once the index shards exist; do not require `snapshot_download(..., local_files_only=True)` to see that file. Do not share a 430/431 venv with vLLM 2.13. Do not run 430 and 431 at the same time (shared port 30000). Delete the previous large serving venv before creating the next one on a quotaed `/workspace`.
- Sequential SGLang prompt-response (130/230/330/430) baseline and extended `num_prompts` is **8** (smoke stays 2). Concurrent 131/231/331/431 stay 24 / 48. Do not change those concurrent counts.
- Workloads 132, 232, 332, and 432 are real RAG: squad_v2 ingest, BGE embed, FAISS retrieve, BGE rerank, Mistral-7B-v0.3 generate. Keep `rag-faiss-end2end-nvidia` (232/432) and `rag-faiss-end2end-amd` (132/332). Setup must call `bash scripts/install_rag_nvidia.sh` or `bash scripts/install_rag_amd.sh`. The AMD helper reuses ROCm torch and must not install a CUDA wheel. Do not ship a `torch.nn.Linear` synthetic stub (`BENCHMARK_RAG_REAL_MODELS=0`). Boolean workbook leftovers (`embedding_model: true`) must resolve to the pinned IDs. `find_local_causal_lm` is usable only when the snapshot has a non-empty `tokenizer.json` or `tokenizer.model` and a Transformers checkpoint: `model.safetensors`, `pytorch_model.bin`, or a complete `model.safetensors.index.json` plus every named `model-*-of-*.safetensors` shard. `consolidated.safetensors` is not a Transformers checkpoint. Do not symlink it to `model.safetensors`. `tokenizer.model.v3` does not count. If the cache has only the consolidated file, `prefetch_rag_models.py` downloads the Hugging Face shards and leaves `consolidated.safetensors` in place for vLLM. The runner calls `ensure_mistral` before `local_files_only` and fails when the load report still has missing causal-LM weights other than a tied `lm_head.weight`. If tokenizer files are missing, prefetch also downloads `tokenizer.json`, `tokenizer.model`, `tokenizer_config.json`, and `special_tokens_map.json`. Keep the `sentencepiece` and `tiktoken` installs; they do not repair a `tokenizer.model.v3`-only snapshot.
- Workloads 130, 131, 230, 231, 330, 331, 430, and 431 require a 600 s ready-wait by default. 231/431 baseline/extended may set `BENCHMARK_READY_WAIT_SEC=1800` because Mistral load plus graph capture is longer than 600 s. `wait_for_server` must fail immediately if `SERVER_PID` has exited; do not wait out the timeout after a crash. AMD 130/131/330/331 also require AITER (`import aiter`) before baseline/extended SGLang launch. On Ubuntu 26.04, install AITER from the AMD `amd-aiter` wheel; do not clone `third_party/aiter` by default. There is no proven ROCm 7.14 / cp314 SGLang wheel. Setup that sees Framework `sglang` must default `BENCHMARK_COMPILE_SGLANG=1` and **die** if `import sglang` still fails. Also install `orjson`, `pybase64`, `starlette`, `pyzmq`, and `jsonschema`, patch `qwen3_asr` `AutoConfig.register(..., exist_ok=True)`, and require both `python -m sglang.launch_server --help` and `from sglang.srt.entrypoints.http_server import launch_server` even when `import sglang` already succeeds. `--help` can pass while `serving_chat` still dies on `No module named 'jsonschema'`. Missing `zmq` and the `qwen3_asr` double-register are why 330/331 smoke passed on `tiny_sglang_server.py` while baseline died in ~17 s. Do not warn-and-continue; that lets smoke pass on `tiny_sglang_server.py` while baseline dies in ~12 s with `No module named 'sglang'`. Keep the AMD `sglang-prompt-response-amd` and `sglang-serving-amd` runners; they must `import sglang` before `launch_server`. AMD 330 and 331 must launch with `--tp 1 --mem-fraction-static 0.8 --disable-cuda-graph --watchdog-timeout 1800` and delete leftover AITER `lock_module_*` files first (430/431 already set TP and mem-fraction; they do not need AITER lock/watchdog hygiene because NVIDIA does not JIT `module_rmsnorm_quant`). A stale `lock_module_rmsnorm_quant` made 331's first decode hang until the 300 s watchdog killed the server (`RemoteDisconnected`). AMD `ensure_setup.sh` must re-run setup when `import sglang`, `import aiter`, `python -m sglang.launch_server --help`, or `from sglang.srt.entrypoints.http_server import launch_server` fails, not only when `.venv` is missing. Smoke still uses `tiny_sglang_server.py` on port 30000. Do not run 130 and 131 at the same time, 230 and 231 at the same time, 330 and 331 at the same time, or 430 and 431 at the same time (shared port 30000).
- Workload 101 and 301 must not map an extended list intent to `rvs -l`. Use `rvs --version` or `rvs -g`.
- Workload 112 and 312 subtest timeout is not a Parameter_*. Use 30s / 60s / 120s by profile plus one retry. Do not use `timeout 8s`.
- Workload 117 and 317 must map `warmup_iters` to rocBLAS `--cold_iters` and `norm_check` to `-v`. Never pass `-w` or `--norm_check`.
- Workload 118 and 318 `search_strategy=find` is Find mode, not `-S 1`. Omit `-S` unless a solution id is explicit.
- Workload 130 keeps five metrics. The “write 0.0 when the server does not expose it” sentence is the metric-#5 fallback, not a sixth metric.
- Workloads 107, 207, 307, and 407 must keep the official STREAM per-element relative checksum in `src/stream.c` from `implementation_components/stream-reference`. Do not sum raw array values and compare an absolute residual to `1e-13`. `run_stream_bandwidth.py` may stay as-is; it only requires stdout `Solution Validates`.
- Workloads 109, 209, 309, and 409 must keep `src/multichase.c` from `implementation_components/multichase-numa-amd`. The chase load is `*(void * volatile *)p`. Do not use a `(void)p;` sink: gcc `-O2` deletes that loop and baseline `num_iterations=1330000000` validates as `latency_ns 0.000000`.
- Workload 105/205 README Overview must come from `Execution Description With Parameters`. Do not write RVS SDC / `rvs_sdc.yaml` text into those repos. 105 compares GPU output to a CPU FP32 reference; 205 compares to a CPU FP64 reference. See `docs/SIBLING_WORKLOAD_NOTES.md`.
- Workloads 124, 224, 324, and 424 are real SDXL on baseline/extended. Smoke may use the overlay tiny Euler denoiser (`scripts/infer_sdxl.py --backend tiny`) and must not download weights. Baseline and extended must prefetch `stabilityai/stable-diffusion-xl-base-1.0` via `scripts/install_sdxl_python.sh --prefetch` and call `StableDiffusionXLPipeline.from_pretrained`. The prefetch must keep `HF_HUB_DISABLE_XET=1` and `snapshot_download(..., allow_patterns=...)` limited to the fp16 Diffusers files (`model_index.json`, scheduler, both tokenizers, and the fp16 `text_encoder`, `text_encoder_2`, `unet`, and `vae` weights). Do not download the full Hub snapshot: ONNX, OpenVINO, Flax, and the single-file checkpoints make Xet fail with `Background writer channel closed`. `num_inference_steps` is 2 / 30 / 50. Do not leave TinyDenoiser / tiny UNet as the only path. Keep the SDXL component overlays (`scripts/infer_sdxl.py`, `scripts/install_sdxl_python.sh`, `run_benchmark.sh`); do not rewrite them. README Overview must describe Diffusers SDXL, not RVS SDC and not a tiny-only stand-in.
- Workloads 131, 231, 331, and 431 must keep overlay `scripts/bench_serving.py` and `scripts/parse_results.py` that persist Metrics #4 Inter-token latency and #5 Request throughput.
- Workloads 130, 230, 330, and 430 must keep the profile `scripts/parse_results.py` that migrates or rebuilds leftover `results/benchmark.db`. Do not regenerate a parser that only `CREATE TABLE IF NOT EXISTS`.
- Immediately after sourcing `scripts/lib/common.sh`, `run_benchmark.sh` must call `capture_benchmark_run_command_submitted "$@"` so the ledger records argv as entered. After parsing args, call `begin_benchmark_run "${profile}"` so `die()` appends a ledger row. After `ensure_setup.sh` returns, call `mark_benchmark_measure_start` so `total_runtime_mm_ss` starts at the benchmark. A setup failure still uses the `begin_benchmark_run` timestamp. After yaml defaults are applied, call `set_benchmark_run_command` with the fully resolved `bash run_benchmark.sh ...` string. Call `finish_benchmark_run` after a successful ledger write.
- LLM Serving runners must call `wait_for_server` (default 600 s; HTTP 503 is not ready). Do not hardcode 180 s. `wait_for_server` must die if `SERVER_PID` is set and that process has already exited.
- For LLM Serving workloads, the no-argument default is `smoke` (tiny local server). `--baseline` and `--extended` start the real model server, wait for readiness, run the client, persist artifacts, and stop the server automatically. Separate server/client terminals are optional troubleshooting modes. The yaml `sweep.profile` default remains `baseline` so `self_check` still sees a baseline yaml default.
- Support `--profile <smoke|baseline|extended>` plus convenience aliases (`--smoke`, `--baseline`, `--extended`).
- Default CLI profile is `smoke` for LLM Serving and for other workloads. Pass `--baseline` or `--extended` for the longer profiles.
- Profile selection must remain compatible with explicit parameter overrides (`--runtime`, `--rw`, etc.) and environment variable overrides.
- Generated `README.md` must include every template section through License (Overview, Hardware Requirements, Installation, Running). A Quick-Start-only stub (~26 lines) is a generation failure. Include a Prerequisites block (OS, GPU, ROCm/CUDA, Python, sudo, HF_TOKEN when serving/weights apply) and a mermaid setup→run→parse diagram. Do not leave `README_TEMPLATE.md`, `PRD_TEMPLATE.md`, `SPEC_TEMPLATE.md`, or root `AGENTS.md` in the published workload tree.
- BabelStream collectors omit `--kernels`. Collectors must use `sys.executable`. Do not list `torch`, `vllm`, `sglang`, or `jax` in `requirements.txt` (parser-only deps such as `PyYAML>=6.0` stay there). FAISS-ROCm is not a smoke gate. Do not rewrite `scripts/lib/rocm_install_24_04.sh` or `scripts/lib/rocm_install_26_04.sh`; `scripts/lib/rocm_install.sh` is a dispatcher only.
- When `GPU Vendor` is NVIDIA, `run_benchmark.sh` must invoke the overlay collector if one exists (`scripts/collect_cublas_gemm.py`, `collect_cudnn_conv.py`, `collect_numa_cache.py`, `collect_babelstream.py`, `collect_torch_micro.py`, `collect_resnet50_train.py`, `collect_resnet50_infer.py`, `collect_bert_infer.py`, `collect_distilbert_train.py`, `collect_jax_xla.py`, `collect_tensor_ops.py`, `collect_sdxl.py`, or overlay `scripts/collect_workload.py` for 201–204 / 206 / 208 / 211–214 / 216 / 220 and the 401 siblings). Do not replace those with a dummy `collect_workload.py` Python loop. `scripts/build.sh` must compile the overlay source that is present (`cublas_gemm.cu`, `cudnn_conv.cu`, `stream.c`, `numa_sweep.cpp`, `babelstream.cu`, `ecc_walk.cu`, `gups.c`, `cuda_memcpy.cu`, `nccl_bw.cu`, `nvhpl.cu`). Do not ship a probe-first `build.sh` that compiles `src/cuda_stack_probe.cu` and skips the real binary. `collect_torch_micro.py` must accept `--batch-size`. Setup must refuse `.setup_state` if those binaries are missing after `build.sh`.
- NVIDIA 201/401, 202/402, 203/403, 204/404, 206/406, 208/408, 211/411, 212/412, 213/413, 214/414, 216/416, and 220/420 must keep the matching `*-nvidia` overlays. Do not invent TFLOPS/bandwidth from column names. 216/416 must link libnccl (`ncclAllReduce`). 220/420 must identify `bin/nvhpl` as the cuSOLVER GETRF/GETRS dense-LU substitute, fail on a residual miss, record requested/actual N and repeats, and compare its FP64 rate with the vector peak rather than tensor-core peak. 213/413 must run OpenMP `bin/gups` and must not hardcode TLB/L3 to 0.0. 214/414 must report H2D/D2H/D2D separately. 204/404 must walk GPU memory with `bin/ecc_walk` and must not label host RAM as `hbm3_coverage_gb`.
- When `GPU Vendor` is AMD, `run_benchmark.sh` must invoke the overlay `scripts/collect_workload.py` when one exists (101–123, 125–126). Do not replace those with a dummy `sample_index,status,value=1.0` loop. Named helpers such as `run_tensor_correctness.py`, `gemm.py` / `conv2d.py`, and `collect_numa_cache.py` stay in place; the AMD wrapper owns `--raw-file` and writes at least two spec CSV rows with `lineterminator=chr(10)`. Do not write a dummy `collect_workload.py` except the rocHPL overlay that already owns that filename.
- Every generated `scripts/build.sh` (or Makefile) that invokes `hipcc` must `source scripts/lib/hipcc_host_gcc.sh` before the compile, or pass `--gcc-install-dir=/usr/lib/gcc/x86_64-linux-gnu/15` (14/13 on Ubuntu 24.04). `scripts/lib/common.sh` also sources that helper so setup and collect inherit `HIPCC_COMPILE_FLAGS_APPEND`. Do **not** put `--gcc-install-dir` on `CXXFLAGS`: host `g++` (130/131/330/331 `sgl-kernel` `setup_rocm.py`) rejects it. On Ubuntu 26.04 / ROCm 7.14, hipcc is Clang 23 and prefers GCC 16; that tree does not expose `<cstdlib>` / `<cmath>` to `__clang_hip_runtime_wrapper.h`, so a bare `hipcc -O2 src/foo.cpp` fails in about one second. Keep the AMD `hipmemcpy-bandwidth-amd`, `babelstream-hbm-amd`, and `rccl-bandwidth-amd` `scripts/build.sh` overlays (114/314, 115/315, 116/316). Also export `LD_LIBRARY_PATH=/opt/rocm/lib:/opt/rocm/lib64` so HIP binaries find `libamdhip64.so.7`. Setup on 26.04 must install `g++-15` / `gcc-15`.
- Workloads 120 and 320 (rocHPL FP64) must keep the `linpack-rochpl-amd` overlay (`src/rochpl.cpp`, `scripts/collect_workload.py`, `scripts/build.sh`, `Makefile`). Host matrix length is `size_t nn = n64 * n64`. Do **not** write `std::vector<double> host_a(n * n)`. Do **not** run extended `N=65536` — it hung 228 min and later died in 2:16 with `hipErrorIllegalAddress`. Clamp `N>=65536` to 32768. At `N=32768` honor up to **6** timed repeats for smoke/baseline (~3–5 min) and **16** for extended (~12 min). The 16-repeat cap applies only when `--profile extended`. GPU `hipMalloc` already uses `size_t`.

### 20.25 Implementation-component overlays

- Matching `implementation_components/<id>/files/` paths listed in that component's `overlay` array are copied onto the generated repository by `scripts/init_generated_repo.py`. After init, do not regenerate those files. `results/overlay_lock.json` and `results/component_leftover_work.md` are authoritative. Mixins fill RAG stubs and `build.sh` when the primary overlay does not. Smoke-check uses `contracts.gemm_per_point` / `compile_rocblas_bench`, not Framework substrings. See `implementation_components/README.md`.
- STREAM `src/stream.c` and STREAM `scripts/build.sh` (`stream-reference`), leftover-DB `scripts/parse_results.py` (130/230/330), vLLM/SGLang `run_benchmark.sh` (127–131 / 227–231 / 327–331) including AMD `vllm-kvcache-amd`, `vllm-throughput-amd`, `vllm-token-generation-amd`, and `sglang-prompt-response-amd`, hipcc `scripts/build.sh` (`hipmemcpy-bandwidth-amd`, `babelstream-hbm-amd`, `rccl-bandwidth-amd`), NVIDIA BabelStream `src/babelstream.cu` / `scripts/build.sh` (`babelstream-hbm-nvidia`), SDXL infer/install/run scripts, NVIDIA `scripts/lib/sglang_nvidia_libs.sh` and `scripts/install_sglang_nvidia.sh` plus the 26.04 helpers (`install_sglang_launch_deps.py`, `sglang_py314_patch.py`, `sglang_py314.pth`), NVIDIA/AMD RAG `scripts/gpu-bench-rag-faiss-end2end.py` / `install_rag_nvidia.sh` / `install_rag_amd.sh`, cuBLAS `src/cublas_gemm.cu` / `scripts/build.sh` / `collect_cublas_gemm.py`, cuDNN `src/cudnn_conv.cu` / `scripts/build.sh` / `collect_cudnn_conv.py`, NUMA `src/numa_sweep.cpp` / `scripts/build.sh` / `collect_numa_cache.py`, NVIDIA Torch micro / ResNet / BERT / DistilBERT / JAX collectors, AMD rocHPL `src/rochpl.cpp` plus `scripts/collect_workload.py` (`linpack-rochpl-amd`), and the NVIDIA lock overlays `system-config-nvidia`, `gpu-health-nvidia`, `system-stress-nvidia`, `sdc-ecc-nvidia`, `fio-nvme-nvidia`, `iperf3-nvidia`, `linux-perf-pmu-nvidia`, `lmbench-nvidia`, `gups-nvidia`, `cuda-memcpy-nvidia`, `nccl-bandwidth-nvidia`, `linpack-hpl-nvidia` are overlay-protected. AMD 00_69 collectors (`system-config-amd`, `rocm-health-amd`, `system-stress-amd`, `sdc-ecc-amd`, `pytorch-tensor-correctness-amd`, `fio-nvme-amd`, `iperf3-amd`, `linux-perf-pmu-amd`, `stream-collect-amd`, `numa-cache-wrapper-amd`, `lmbench-amd`, `gups-amd`, hipmemcpy/babelstream/rccl `collect_workload.py`, `rocblas-gemm-amd`, `miopen-convolution-amd`, `torch-micro-amd`, `resnet50-training-amd`, `resnet50-inference-amd`, `bert-inference-amd`, `distilbert-amd`, `jax-xla-amd`) are also overlay-protected.
- `scripts/self_check_generated_repo.sh` and `scripts/smoke_check_generated_repo.sh` enforce overlay identity and STREAM / leftover-DB tokens. Do not weaken those checks.

### 20.3 Standard Device Selection

- GPU-targeted generated runners must default to GPU execution and expose `--device gpu|cpu`.
- `--device cpu` is an explicit comparison mode and must be recorded in the run options and summary.
- A multi-backend component such as FAISS may expose a separate `--faiss-device cpu|gpu` option when vendor/runtime compatibility differs.
- GPU mode must fail clearly when the required GPU backend is unavailable; it must not silently downgrade to CPU. Any safe CPU component retained in GPU mode must be named in the summary.

### 20.4 CLI Help Contract

- `bash run_benchmark.sh --help` must print a `usage()` help page and exit 0. Do not dump the script header with `sed -n '1,20p'` or any other fixed line range.
- Handle `--help`, `--specification`, and `--matrix-definition` before `scripts/ensure_setup.sh`, before sourcing workload run logic, and before any install or benchmark work. These flags must not start setup.
- `--specification` prints every `benchmark_specification.json` field/value for this workload as a two-column table and exits 0. `--matrix-definition` is the same command. The runtime source is the extracted JSON row, not the Excel workbook.
- Copy `scripts/templates/run_benchmark_help_skeleton.sh` into generated `run_benchmark.sh` and customize it. Do not source the skeleton unchanged.
- The first prose line after `Usage:` must match this script's header `Description` field.
- Keep the required common sections: Profiles, Execution, Validation and logging, Information, and Examples.
- Profile aliases must be described as `Run smoke profile`, `Run baseline profile`, and `Run extended profile`.
- Document flag arguments accurately. `--save-options-file`, `--raw-file`, `--config`, `--log-level`, `--phase`, and expected-environment flags take values; they are not boolean switches.
- `--raw-file <path>` is an existing raw file used by `--phase3`. It is not an output-log path.
- Accepted phase forms are `--phase phase3`, `--phase 3`, and `--phase3`. Do not document a literal `--phase1..phase4` flag.
- Do not document `-h` unless the parser accepts it.
- Do not invent `--output-format` values. If the flag exists, say it overrides config `output_format`.
- Print the default profile as `smoke`. `--baseline` and `--extended` remain explicit. The yaml `sweep.profile` seed stays `baseline` for LLM Serving.
- Add a `Workload options:` section for every extra flag this runner parses (for example `--M`, `--dtype`). Omit unused optional sections such as expected-environment overrides when those flags are absent.

### 20.1 Run Output UX Contract

- `run_benchmark.sh` should print a concise end-of-run statistics block (run id, sample count, key aggregate metrics, and output file locations) to help operators confirm success without querying SQLite manually.
- The end-of-run block must also print UTC `Start time`, UTC `Stop time`, and numeric `Elapsed time` values for the complete benchmark execution, using the exact labels required by `docs/run-output-contract.md`.
- After the Run ID / Status / Samples / Profile / Device line, print `Command submitted` and `Command fully resolved` via `print_benchmark_summary_commands`. Use the captured argv strings (hyphenated flags). Leave a line empty when the string is unknown; do not invent flags.
- Print Artifacts and SQLite DB before the Metrics block, with one empty `[INFO]` spacer before the Metrics lines and one empty `[INFO]` spacer after them. Do not place Metrics above Artifacts or SQLite DB.
- If a `--quiet` flag is present, suppress non-essential informational blocks while preserving warnings, errors, and non-zero exit behavior.
- Where sufficient samples are available, the summary should include extended descriptive statistics (min, max, mean, median, stddev, percentile such as p95) for primary metrics.

### 21. Threshold and Baseline Values with Documented Derivations

- Threshold and baseline values must be derived from `config/hardware_profile.{gpu}.yaml`, `benchmark_specification.json`, or a documented external reference. Add a YAML comment citing the derivation basis next to each value.
- Example: `# ~54% of MI300X FP16 peak 1307 TFLOPS`, `# 45% of MI300X HBM bandwidth 192 GB/s`.
- Never use round numbers or guesses; always trace threshold and baseline values back to their source.

### 22. Threshold Key Names with Suffix Convention

- Threshold key names must use `_min` / `_max` suffixes to encode comparison direction:
- `_min` means observed value must be `>=` threshold value (lower bound).
- `_max` means observed value must be `<=` threshold value (upper bound).
- Threshold keys without a `_min`/`_max` suffix are invalid and must be corrected before validation.
- This suffix convention applies only to `thresholds:` keys. It does not apply to informational `baselines:` ranges.
- Example: `peak_tflops_f16_min: 500`, `max_latency_ms_max: 100`.

### 23. Structured Run Artifact Directory

- Every benchmark run must create a unique run directory under `results/raw/` named: `YYYYMMDD_HHMMSS_<repo_name>_<hostname>`.
- Raw tool output, run transcript, and run-side artifacts for that execution must be stored in that run directory.
- Do not mix artifacts from different runs into a single flat filename namespace.

### 24. Full Transcript + Replayable Commands

- `run_benchmark.sh` must capture a full stdout/stderr transcript as `run.log` in the run directory.
- Every executed external command must be emitted with `[RUN]` prefix and saved to `commands_executed.sh` as a replayable script.
- Keep terminal color output for operators, but strip ANSI color codes from persisted log files.

### 25. System and Software Metadata Artifacts

- Do not write `system_info.txt`. That hostname/`uname`/`lscpu` dump is not the inventory artifact.
- After workload execution and validation, write Excel-derived `hardware_info.txt`, `software_info.txt`, and `errors_info.txt` into the per-run artifact directory.
- Export environment variables to `env_variables.txt` while masking secret/token/key-like values.
- At the end of each run, capture `journal_warnings.txt` via `capture_journal_warnings` from `scripts/lib/common.sh`: `journalctl -p warning` (warning and higher), scoped to the run start/stop timestamps when available; otherwise limit to the current boot. Do not dump the full journal.
- Collect metadata commands on the local target host and save outputs into the local run directory.
- Every generated repository must include `config/hw_sw_info_commands.xlsx`, `scripts/generate_collect_hw_sw_info.sh`, and `scripts/collect_hw_sw_info.sh`. After workload execution and validation, invoke `bash scripts/collect_hw_sw_info.sh "${RUN_DIR}"`; it must write Excel-derived, vendor-filtered `hardware_info.txt`, `software_info.txt`, and `errors_info.txt` into that per-run directory, including the command list, timestamps, and per-command status. Missing optional tools belong in `errors_info.txt` and must not replace the benchmark's own exit status.
- Every generated repository must include `scripts/print_benchmark_definition.py`. `bash run_benchmark.sh --matrix-definition` prints that file's field/value table and exits before setup.
- Every generated repository must include `scripts/update_runtime_ledger.py`. Each `run_benchmark.sh` invocation must append exactly one CSV row to `/var/opt/benchmarks/runtime_ledger.csv`, including successful and failed runs. The row must use the required column order from `LEDGER_COLUMNS` (`runtime_root_dir` before `benchmark_profile`; `total_runtime_mm_ss` after `start_datetime`; `exit_code` then `failure_stage`, `failure_detail`, `raw_run_dir`; then `hostname`, `gpu_name`, `gpu_vram`, `gpu_count`, `os_version`, `cpu_model`, `workload_name`, then the seven metric pairs; then `run_benchmark_command_submitted`, `run_benchmark_command_fully_resolved`, `Parameter_01_Name`/`Parameter_01_Value` through `Parameter_20_Name`/`Parameter_20_Value`, `parameters_set`, `notes`). Do not write `runtime_exit_code`. `gpu_name` is the product name from `rocm-smi --showproductname` Card Series or `amd-smi` MARKET_NAME, never the ROCm SMI banner. `gpu_vram` is the VRAM total-memory value only. Use a `<workload_number>_YYYYMMDD_HHMMSS` run ID, profile, `mm:ss` runtime, one `exit_code`, failure stage/detail, metric definitions/results, the submitted and fully resolved `run_benchmark.sh` commands, parameters, and notes. A ledger-write failure is a warning only and must not alter the benchmark exit status.
- Every generated repository must include `scripts/ensure_setup.sh`, and `run_benchmark.sh` must invoke it before any benchmark command. `--help` is not a benchmark command: handle it in `usage()` and exit before `ensure_setup.sh`. If `.setup_state` is absent, the guard runs `setup.sh` with `--assume-yes` when that option is supported, then requires `.setup_state` before continuing. If setup is waiting for a reboot, the guard exits and instructs the operator to rerun `run_benchmark.sh` after resume; automatic post-reboot benchmark continuation is not part of this contract.

### 26. Logging and UX Conventions

- Prefix informational messages with `[INFO]`, warnings with `[WARN]`, errors with `[ERROR]`, successes with `[PASS]`, failures with `[FAIL]`, and command execution with `[RUN]`.
- Provide phase/section banners for major run stages to improve scanability of large logs.
- Support a configurable `--log-level` flag with at least `ERROR|WARN|INFO|DEBUG` values.

### 27. Output Format Redundancy

- In addition to SQLite and summary JSON, each run must emit machine-friendly per-sample exports in both CSV and JSON formats.
- These files should live in the run directory and correspond to the same `run_id` persisted to SQLite.
- Raw benchmark rows should also be persisted in dual machine-readable formats (for example `raw_results.csv` and `raw_results.jsonl`) alongside the raw text transcript.

### 28. Duration and Option Reproducibility

- Record explicit run start/end times and report total duration on completion.
- Persist effective CLI/user options for each run (for example `cli_options.env`) inside the run directory.
- Optionally support writing the same options snapshot to a user-provided path.

### 29. Resumable Phase Execution

- `run_benchmark.sh` should support phase-oriented execution for recovery workflows (for example `--phase phase3 --raw-file <path>` to rerun parsing only).
- Provide phase aliases (`--phase1` ... `--phase4`) for concise operator usage.
- Phase-only modes must preserve non-zero exit behavior and produce clear phase-completion logs.

### 29.1 Local-Only Execution Mode

See also "## Remote Host Execution" below and `docs/ARCHITECTURE.md` → "Two execution contexts" for the full generation-time-vs-runtime distinction.

- Generated benchmark harnesses must support local execution only.
- Do not add remote prompts, SSH key/IP persistence files, or SSH execution paths.
- If legacy remote options are provided, fail fast with a clear local-only error.
- If the generation prompt contains a remote login command with an IPv4 address, remote validation is mandatory for every workload: load the completed repository onto that VM, set every extracted directory to `0755` (Windows `tar` is typically `0777` / lime-green in `ls`), install it there, run `scripts/self_check_generated_repo.sh`, and run `bash run_benchmark.sh --profile smoke --validate` there before reporting completion. Keep all remote details out of generated files; this is generation-time validation, not generated-repository runtime orchestration. See `docs/AI_AGENT_INSTRUCTIONS.md` for the `chmod 755` find commands.
- For MPI-backed workloads, detect root execution explicitly. When `EUID=0`, invoke the launcher through `env` with the implementation-specific root confirmations; for Open MPI/PRRTE use both `--allow-run-as-root` and `OMPI_ALLOW_RUN_AS_ROOT{,_CONFIRM}=1` plus `PRTE_ALLOW_RUN_AS_ROOT{,_CONFIRM}=1`. Persist the complete effective command and warn that root execution is an operator-approved exception.
- Build scripts must select a benchmark executable by its exact documented install path. If the installer emits helper launchers, copy and verify them beside the selected binary; never select the first broad filename match.

### 29.2 Reboot Continuation Contract

- If benchmark scripts issue a reboot, they must define explicit continuation behavior.
- **Local execution path** must support continuation after user login:
- persist resume state (phase/step) before reboot,
- auto-resume safely on reboot completion (for example via a systemd oneshot resume service) when explicitly enabled by setup defaults,
- detect persisted resume state on startup and continue deterministically.
- Reboot-driven setup flows must append a chronological operator-facing status log to `results/install_status.txt` and keep `/etc/motd` synchronized with that install status. They must also write `results/install_commands.txt` with one bare executed install command per line (no timestamp, step number, or comment) and preserve that file across reboot resume.
- Local first-run setup UX should print a clear Enter-to-continue notice including: expected reboot count, auto-resume behavior, install-status file path, and completion notifications (`wall` + `/etc/motd`).
- Generated implementations should reference:
- `docs/reboot-resume-pattern.md`,
- `scripts/lib/reboot_resume.sh`.

### Final Verification

Work through every item in `docs/SUBMISSION_CHECKLIST.md` in order before reporting implementation complete. All items must be explicitly checked — do not self-certify based on a partial review. Execute each grep, file-existence check, and cross-reference listed in the checklist directly.

Every completed workload repository must also be independently publishable to GitHub. Run `bash scripts/check_github_publish_ready.sh` from the generated workload root and require a passing result before reporting completion. Before a public push, copy the repo and run `bash scripts/prepare_github_publish.sh --apply --github-owner=YOUR_GITHUB_USER` then `bash scripts/check_github_publish_ready.sh --published`. Create the GitHub repository as `<Workload Number>-<Repo Name>` (same as the local folder; example `128-gpu-bench-amd-vllm-throughput-latency`). Generated repositories use workload-specific `.github/` community files and workflows; do not publish generator-specific contribution/security text or `.claude/`. The nested `*_copy/` generation workspace is removed once the workload passes; while it exists it is gitignored, and it must never be required by the published workload.


## Machine-Checkable Contracts

Before any implementation work begins, validate the extracted benchmark contract:

```bash
python3 scripts/validate_template_inputs.py \
  --benchmark-specification benchmark_specification.json \
  --benchmark-schema schemas/benchmark_specification.schema.json
```

Before reporting generation complete, validate traceability metadata:

```bash
# Run from generated repository root (<Workload Number>-<Repo Name>/ in template mode)
python3 scripts/validate_template_inputs.py \
  --generation-manifest results/generation_manifest.json \
  --generation-schema schemas/generation_report.schema.json
```

Rules:

1. Do not proceed to Phase 1 if benchmark contract validation fails.
2. Do not report completion if generation manifest validation fails.
3. `results/generation_manifest.json` is required in every generated repository (path is relative to generated repository root).


## benchmark_specification.json Expected Fields

`benchmark_specification.json` is an array of objects, each shaped as:

```json
{"field_name": "...", "source_file": "BenchmarkSpecDefinitions.xlsx::SheetName", "value": "..."}
```

The following field names are required and must be non-empty after Phase 0 extraction. If any are missing or blank, Phase 0 is incomplete — fix the workbook or the extractor output before proceeding.

| Field Name | Role |
|---|---|
| `Workload Number` | Unique workload identifier (e.g., `113`) |
| `Workload Name` | Human-readable workload name (e.g., `GUPS Random Memory`) |
| `Execution Domain` | One of the six domain values defined in the Execution Domain table |
| `Workload Type` | `Benchmark` or `Test` — controls threshold vs. baseline pattern |
| `Workload Category` | High-level category (e.g., `Memory`, `Compute`, `Correctness`) |
| `Main Goal` | One-sentence statement of what the workload measures or validates |
| `Validation Objective` | Pass/fail or measurement objective |
| `Metrics` | Comma- or numbered-list of primary output metrics |
| `Framework` | Complete mandatory software inventory translated from the workbook's `Software Framework` column; every listed application, tool, utility, program, library, language runtime, and framework must be installed and independently verified |
| `Installation and Execution Summary` | Plain-text installation and run procedure |
| `Execution Description With Parameters` | Parameterized description including sweep details |
| `Workload Command Line Executable` | The binary or command that is directly invoked |

The following fields are optional but should be populated when available:

| Field Name | Role |
|---|---|
| `Parameter_01` through `Parameter_20` | Swept or fixed parameter **names**; empty slots use `"—"` |
| `Profile Parameter Values` | JSON map of each named parameter to smoke/baseline/extended values from the `Parameters_SmokeBaselineExtend` sheet |
| `run_benchmark Command Plus Options for Smoke/Baseline/Extended Run` | Generated display commands; do not author values here |
| `Raw Output Format` | Description of the tool's stdout/output structure |
| `Raw Output Example` | A concrete sample of actual tool output |
| `Runtime Language` | Primary language(s) used (e.g., `Bash, Python`) |
| `AMD nVidia Applicable` | Whether the workload applies to AMD, NVIDIA, or both |
| `nVidia Porting Instructions (Reference Only)` | NVIDIA porting notes if applicable |
| `Model Context Protocols` | Comma-separated MCP server tokens required for execution |
| `Repo Name` | Unprefixed workbook slug (e.g., `sys-bench-gups-random-memory`). Local folder and GitHub name are `<Workload Number>-<Repo Name>` (e.g., `113-sys-bench-gups-random-memory`). |
| `Hardware Config` | Target machine hardware description |
| `OS Version`, `Kernel Version`, `Python Version`, `ROCm Version` (alias of `GPU Runtime Version (was ROCm Version)`), `rocBLAS Version` (alias of `BLAS Version (was rocBLAS version)`) | Software stack versions |
| `Test Procedure (80 words)` | Concise test procedure for README generation |

## Canonical SQLite Schema

Metrics must persist to `results/benchmark.db` across runs. Use two tables minimum.

**Rule:** Actual column names must be derived from `benchmark_specification.json` — from the `Parameter_*` fields (dimension/sweep columns in `samples`) and `Metrics` field (measurement columns in `samples` and aggregate columns in `runs`). Do not use the generic placeholder names shown below as-is; they are examples only.

### `runs` table

| Column | Type | Notes |
|---|---|---|
| `run_id` | INTEGER PRIMARY KEY AUTOINCREMENT | Unique run identifier |
| `benchmark_id` | TEXT | e.g., `"1001"` |
| `benchmark_name` | TEXT | Human-readable name |
| `status` | TEXT | `ok`, `error`, `timeout`, or `partial` |
| `started_at` | TEXT | ISO-8601 UTC |
| `finished_at` | TEXT | ISO-8601 UTC |
| `host_name` | TEXT | System hostname |
| `os_version` | TEXT | OS version string |
| `kernel_version` | TEXT | Kernel release string |
| `gpu_name` | TEXT | Card Series / MARKET_NAME from `rocm-smi --showproductname` or `amd-smi` (never the ROCm SMI banner) — omit for CPU/System workloads |
| `rocm_version` | TEXT | Installed ROCm version — omit for CPU/System workloads |
| `framework_version` | TEXT | e.g., rocBLAS 4.4.x, PyTorch 2.x, FIO 3.x, gups 1.x — derived from `benchmark_specification.json` Framework field |
| `git_sha` | TEXT | Benchmark repo commit SHA |
| `config_path` | TEXT | Path to config file used |
| `command_line` | TEXT | Exact command that started the run |
| `error_message` | TEXT | NULL on success |
| *(workload aggregate columns)* | REAL / INTEGER | One per metric-family peak/mean — derived from `benchmark_specification.json` |

### `samples` table

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | Unique sample row |
| `run_id` | INTEGER NOT NULL REFERENCES runs(run_id) | Required foreign key |
| `sample_index` | INTEGER | 0-based order within the run |
| `status` | TEXT | `ok` or `error` |
| *(workload dimension columns)* | REAL / INTEGER / TEXT | Per `Parameter_*` fields in `benchmark_specification.json` |
| *(workload metric columns)* | REAL / INTEGER / TEXT | Per `Metrics` field in `benchmark_specification.json` |
| `error_message` | TEXT | NULL on success |
| `created_at` | TEXT | ISO-8601 UTC |

**Static run-level facts must live only in `runs`; do not duplicate them in `samples`.** Join sample rows to run metadata through `run_id`.

### Workload-specific column naming conventions

Derive actual column names from `benchmark_specification.json` — the rows below are naming pattern examples only, organized by execution domain.

| Metric Type | Example Column Names | Applicable Domains |
|---|---|---|
| Compute throughput | `tflops`, `gflops`, `images_per_s` | GPU Compute / ROCm |
| Memory bandwidth | `gb_per_s`, `bandwidth_gbps`, `hbm_bw_gbps` | Memory / Transfer, CPU / System |
| Random access | `gups`, `mups`, `updates_per_s` | CPU / System (GUPS, STREAM) |
| I/O throughput | `iops`, `iops_p95`, `bandwidth_mbps` | CPU / System (FIO, storage) |
| Network throughput | `throughput_mbps`, `throughput_gbps` | CPU / System (iPerf3, RCCL) |
| Latency | `latency_ms`, `latency_us`, `ttft_ms`, `e2e_latency_ms` | All domains |
| LLM tokens | `tokens_per_s`, `tokens_in`, `tokens_out`, `total_tokens` | LLM Serving |
| GPU telemetry | `gpu_util_pct`, `gpu_power_w`, `gpu_temp_c`, `vram_used_mb` | GPU Compute / ROCm |
| Correctness | `error_norm`, `max_abs_error`, `passed` | Validation / Correctness |
| Transfer size | `bytes_transferred`, `problem_size`, `batch_size` | All domains |
| Timing | `exec_time_ms`, `duration_s`, `wall_time_s` | All domains |


## Raw Output Parsing Rules

`scripts/parse_results.py` must follow `docs/raw-output-parser-contract.md` and these rules when parsing benchmark tool stdout:

### Dataset identity and corpus scope

- Hugging Face dataset identifiers must use their canonical namespace-qualified form (for example, `rajpurkar/squad_v2`), not an informal short label.
- Generated implementations must record the resolved dataset identifier and split in run metadata.
- The implementation must state whether it indexes the complete corpus or an explicitly bounded subset; a bounded subset must record its size and remain distinct from a full-corpus result.

1. **Read the output format from `benchmark_specification.json`** — the `Raw Output Format` field contains the exact CSV column order, column name variants across tool versions, unit definitions, and any flag requirements (e.g., `--norm_check 1`). The `Raw Output Example` field contains a concrete sample of the tool's actual stdout; use it to verify your understanding of the format and to confirm header names, column ordering, and value ranges before writing any parsing code. Do not rely on AI training memory for tool output format details — read both fields.
2. **Detect the CSV header row dynamically** — do not hard-code column positions. Parse the header line to build a column index map on each invocation.
3. **Normalize column name variants** — maintain a `_COL_ALIASES` dict mapping known header variations (e.g., `rocblas-Gflops` → `gflops`, `norm_error_ptr_1` → `norm_error_1`) so the parser tolerates minor differences across tool versions (example only — derive actual aliases from this benchmark's `Raw Output Format` field and confirm them against the header row visible in `Raw Output Example`).
4. **Convert units at parse time** and document each conversion in a comment in the code. Example: `tflops = gflops / 1000  # rocblas-bench reports GFlops/s`.
5. **Handle per-shape errors without aborting** — if the tool exits non-zero for one shape, set `sample.status = 'error'` and populate `error_message`; continue parsing remaining shapes.
6. **Associate each CSV block with its metadata** — `run_benchmark.sh` writes a comment line (e.g., `# dtype=f16_r M=4096 N=4096 K=4096`) before each tool invocation. The parser must read these comment lines to attach sweep dimensions to each CSV block.
7. **Allow metadata keys that include digits** — metadata parsers must support keys like `l3_miss_rate`, not just alphabetic/underscore keys.
8. **Counter portability fallback for CPU/System workloads** — when architecture-specific perf events are unavailable (e.g., `LLC-*`), fallback to portable events (e.g., `cache-references`, `cache-misses`) and annotate fallback/skip behavior in raw output logs.
9. **Vendor CLI compatibility** — probe optional flags against the installed executable. If a tool release rejects an optional flag, omit it with a warning, persist the effective command, and continue remaining sweep points. For rocblas-bench, accept both the example `function,precision,...` CSV header and the versioned `transA,transB,...,rocblas-Gflops,us` header.
10. **Availability semantics** — never convert an absent metric into a measured zero. Derive it with a documented formula or persist an explicit unavailable marker, and report runs with skipped configured points as `partial` unless those points are excluded by configuration.


## Execution-Loop Validation Contract

This repository uses a **lightweight, SQLite-integrated execution loop** for result validation. There is no separate unit-test dependency and no `create_fixture_db.py` script. All validation is performed by `scripts/validate_results.py`, which reads directly from `results/benchmark.db` (or any path supplied via `--db` / `$BENCHMARK_DB`), applies integrity checks and any configured threshold checks from `config/benchmark_config.yaml`, and exits non-zero on any failure. The `tests/` directory exists only for the committed fixture database.

### Validation script: `scripts/validate_results.py`

The script is the single validation entrypoint.  It must:

1. Accept `--db PATH`, `--config PATH`, `--seed-fixture`, and `--quiet` flags.
2. Open the database at the resolved path (env var `$BENCHMARK_DB` overrides `--db`).
3. Fetch the most recent row from `runs` and all matching rows from `samples`.
4. Load the `thresholds:` block from `config/benchmark_config.yaml` if present.
5. Run all integrity checks (run status, timestamps, aggregate columns, sample counts, per-sample metrics, dtype tokens, NULL error_message).
6. Run threshold checks only when a `thresholds:` block is present, using the `_min` / `_max` suffix convention:
- `_min` key → measured value must be `>=` threshold value.
- `_max` key → measured value must be `<=` threshold value.
- Keys without a `_min`/`_max` suffix produce a FAIL check and are reported.
7. Print a structured PASS/FAIL report to stdout.
8. Exit 0 on all checks passing; exit 1 on any failure.

**There is no separate unit-test configuration. Do not generate unit-test harness files.**

### Required integrity checks (built into `validate_results.py`)

Column names in checks 4, 8, 9, and 10 must be derived from `benchmark_specification.json` — not hardcoded. The descriptions below state the generic contract; the generated `validate_results.py` must substitute actual column names from the workload's `Metrics` and `Parameter_*` fields.

1. Latest run exists and `status == 'ok'`.
2. `run.error_message` is NULL.
3. `started_at` and `finished_at` are valid ISO-8601 strings.
4. All aggregate metric columns derived from the `Metrics` field in `benchmark_specification.json` are non-NULL and finite; throughput/time-size metrics must be positive, while rate/error-style metrics that can validly be zero (e.g., miss rates or error counts) must be non-negative.
5. At least 1 sample row exists for the latest `run_id`.
6. At least 2 sample rows exist (sweep coverage check).
7. Every sample has `status == 'ok'` and `error_message` IS NULL.
8. All per-sample metric columns derived from the `Metrics` field in `benchmark_specification.json` are finite and in valid range by metric type: positive for throughput/time-size metrics; non-negative for metrics that can be zero (e.g., miss rates, error counts).
9. Correctness columns (e.g., error norm columns) are non-NULL only when present in the schema as defined by `benchmark_specification.json`. Skip this check for workloads that have no correctness metrics.
10. If `dtype` is a swept parameter in `benchmark_specification.json`, it must be a known precision token (e.g., `f16_r`, `bf16_r`, `f32_r`, `f64_r`). Skip this check for workloads that have no `dtype` parameter.

### Fixture seeding (`--seed-fixture` flag)

CI workflows run `.venv/bin/python scripts/validate_results.py --seed-fixture` to create `tests/fixtures/benchmark.db` on-the-fly from hardware peak values in `config/hardware_profile.{gpu}.yaml`.  This replaces the old `create_fixture_db.py` approach — there is no separate script to maintain and no committed binary `.db` file.

**`--seed-fixture` behaviour:**

- Reads `benchmark_specification.json` to determine actual metric column names, parameter names, and the workload's `Execution Domain`.
- For GPU-domain workloads, reads peak values from `config/hardware_profile.mi300x.yaml` and applies a conservative efficiency factor (40–60% of peak) to seed aggregate metrics.
- For CPU/System workloads, derives realistic seed values from documented reference ranges in `benchmark_specification.json` or `config/hardware_profile.mi300x.yaml` where applicable; uses a placeholder with a `# TBD` comment when no published reference is available.
- Writes at least two samples covering different sweep points, using actual column names derived from `benchmark_specification.json`, and one run row.
- Deletes and recreates `tests/fixtures/benchmark.db` idempotently.
- Immediately validates the seeded database and exits non-zero if it fails.

**Fixture data quality rules (unchanged from prior architecture):**

| Rule | Rationale |
|---|---|
| Aggregate metric values at 40–60% of hardware peak | Matches what real hardware achieves |
| At least 2 `samples` rows | Ensures per-sample loops iterate more than once |
| `sample_index` is 0-based and contiguous | Ordering check |
| `created_at`, `started_at`, `finished_at` are valid ISO-8601 UTC strings | Timestamp format check |
| `status = 'ok'` on both the run row and all sample rows | Baseline assertion |
| `run_id` foreign key in `samples` matches the `runs` row | Referential integrity |
| `error_message` is NULL on all rows | Asserted on success paths |

## CI Workflow Contract

Generated workload repositories do not carry their own CI logic. `scripts/init_generated_repo.py` renders exactly two thin caller workflows from `templates/workload/.github/workflows/` and `config/ci_contract.yaml`; the steps live once in the `shared-workflows` repository (`templates/shared-workflows/`, emitted by `scripts/emit_shared_workflows.py`, published and tagged separately).

`.github/workflows/` in a generated repository contains exactly:

- **`ci.yml`** — triggers on `pull_request` (to `main`, `develop`) and `push` (to `main`); `permissions: contents: read`; one job that `uses: <owner>/shared-workflows/.github/workflows/ci.yml@<ref>` with `vendor` and `os_label`. The shared job runs on a GitHub-hosted runner: shellcheck (`--severity=warning`), ruff with the rules in `config/pyproject.toml`, `bash -n`, `compileall`, `run_benchmark.sh --help`, `benchmark_specification.json` against its schema, `config/benchmark_config.yaml` parse, `scripts/validate_results.py --seed-fixture --quiet`, required files, and actionlint. Every check runs, and the job summary lists each result.
- **`gpu-smoke.yml`** — triggers on `workflow_dispatch` only (with a `profile` choice: smoke, baseline, extended); `permissions: contents: read`; one job that `uses: <owner>/shared-workflows/.github/workflows/gpu-smoke.yml@<ref>`. The shared job runs on `[self-hosted, gpu, <vendor>, <os_label>]`, verifies the pre-provisioned GPU stack without installing it, writes `results/environment.json`, runs `run_benchmark.sh --profile <profile> --validate`, and uploads `results/summary.json`, `results/environment.json` and `results/parsed/`.

Rules:

- Never hand-edit or hand-write workflow files in a generated repository. Change `config/ci_contract.yaml` or the templates and regenerate. `init_generated_repo.py` fails generation when a rendered caller does not match the contract.
- Never add `pull_request` or `pull_request_target` to the GPU workflow: a fork's code would run on the self-hosted GPU runner.
- Never swallow lint failures (`|| true`, `continue-on-error`) in any workflow.
- Do not generate `nightly.yml` or `.github/dependabot.yml` in a workload; Dependabot is configured in `shared-workflows` only.
- `config/ci_contract.yaml`, `scripts/ci_contract.py` and `scripts/emit_shared_workflows.py` are generation-only and are not copied into generated repositories.
- The contract's inputs (`vendor`, `os_label`, `profile`) and the shared workflows' versioning rule (compatible change: move `v1`; breaking change: new `v2` and regenerate) are documented in `templates/shared-workflows/README.md`.

### What the agent must NOT do

- Do not generate `tests/conftest.py`, `tests/test_integrity.py`, or any other unit-test harness infrastructure — validation belongs in `scripts/validate_results.py`.
- Do not generate `tests/fixtures/create_fixture_db.py` — `--seed-fixture` in `validate_results.py` is the replacement.
- Do not commit a binary `tests/fixtures/benchmark.db` file — CI generates it on-the-fly.
- Do not add external unit-test dependencies to `requirements.txt` unless an explicit user instruction requires it.
- Do not hardcode threshold values in `validate_results.py` — when thresholds are required, they must come from `config/benchmark_config.yaml`.


## Authorized ROCm Installation Functions

`scripts/lib/rocm_install.sh` is a thin Ubuntu-release dispatcher. Callers still `source scripts/lib/rocm_install.sh`. That file sources `scripts/lib/rocm_install_24_04.sh` (Ubuntu 24.04 / ROCm 7.2.1) or `scripts/lib/rocm_install_26_04.sh` (Ubuntu 26.04 / ROCm 7.14). Those versioned libraries contain the four pre-written, version-pinned, idempotent shell functions that cover every ROCm system-setup task a benchmark repository might need. The functions must be used **verbatim** — do not regenerate, inline, or paraphrase them, and do not rewrite the dispatcher or the versioned libraries.

### Rule: Never generate new ROCm installation code

If a workload requires any of the four tasks below, the agent must:

1. Source the library: `source "$(dirname "$0")/lib/rocm_install.sh"` (or adjust the relative path to match the calling script's location).
2. Call the appropriate function by name.
3. Not write any new `apt-get`, `amdgpu-install`, `wget`, or `git clone` commands for these tasks outside of the library.
4. Treat workload-inherent ROCm install tasks as normal setup scope in `setup.sh` (idempotent default behavior), rather than optional ad-hoc troubleshooting.
5. For workloads that require only runtime/repository/RVS setup, `setup.sh` defaults should execute ROCm steps 1-23 and intentionally exclude steps 24-41 unless the workload explicitly requires compile steps.
6. `setup.sh` should provide install-status hooks consumed by `scripts/lib/rocm_install.sh` (`install_status_log_phase`, `install_status_log_step`) so phase/step progress can be mirrored to both `results/install_status.txt` and `/etc/motd`, and so executed install commands are appended to `results/install_commands.txt`.
7. If `setup.sh` may call reboot-capable ROCm runtime install functions, it must follow `docs/rocm-reboot-install-contract.md`: install a local systemd oneshot auto-resume service before `rocm_install_runtime`, resume with `--assume-yes --resume-from-service` after each reboot, preserve `results/install_status.txt` and `results/install_commands.txt`, and remove the service only after successful completion.

| Function | When to call |
|---|---|
| `rocm_install_runtime` | GPU Compute / ROCm workload on a bare-metal Ubuntu server with no existing ROCm. Check: `[ ! -f /opt/rocm/bin/rocm-smi ]`. After the driver/firmware install it reloads amdgpu (`scripts/lib/amdgpu_reload.sh`) and returns with no reboot when every GPU comes back; otherwise it triggers one reboot, or with `ROCM_DEFER_REBOOT=1` (generated `setup.sh`) leaves stage3 and `ROCM_REBOOT_PENDING=1` so setup reboots once after installing everything else. Only use from a provisioning harness that can reconnect (generated `setup.sh` systemd auto-resume). |
| `rocm_add_repository` | ROCm apt repository not yet present. Check: `[ ! -f /etc/apt/sources.list.d/rocm.list ]`. |
| `rocm_install_rvs` | `benchmark_specification.json` Workload Name or Workload Command Line Executable references `rvs` or `rocm-validation-suite`. |
| `rocm_compile_rocblas_bench` | `benchmark_specification.json` Framework contains `rocBLAS` or `rocblas-bench`. |

### Version pins

The 24.04 library pins ROCm **7.2.1**, Ubuntu **noble**, and GPU architecture **gfx942**. The 26.04 library pins ROCm **7.14**, Ubuntu **resolute**, and **gfx942**. `setup.sh` detects `/etc/os-release` and exports the matching pins before sourcing the dispatcher. Override only with environment variables when a workload requires it:

```bash
export ROCM_VERSION="7.14"
export UBUNTU_CODENAME="resolute"
export GFX_TARGET="gfx942"
source scripts/lib/rocm_install.sh
```

Do not change these defaults inside the versioned library files themselves — update the environment variable exports in `setup.sh` or `run_benchmark.sh` instead.

### Protected file

`scripts/lib/rocm_install.sh`, `scripts/lib/rocm_install_24_04.sh`, `scripts/lib/rocm_install_26_04.sh`, and `scripts/lib/noninteractive_root.sh` are **protected library files**. Every privileged command in the ROCm libraries runs through `run_noninteractive_root`; keep it that way. Do not modify them unless explicitly instructed by the user to change a version pin or add a new installation task. Treat them the same as `benchmark_specification.json` — read them, source them, do not alter them.

For reboot-safe setup architecture, `docs/rocm-reboot-install-contract.md` is authoritative. Agents must not rely on manual post-reboot reruns as the default behavior for generated repositories that install ROCm runtime components.

## MCP Configuration

The `Model Context Protocols` field in `benchmark_specification.json` lists the MCP servers this benchmark requires access to during execution. Read this field before beginning any file-write, remote execution, or external service step.

## Remote Host Execution

See also § 29.1 "Local-Only Execution Mode" above, `docs/generation-workflow.md` (Phase 0), `docs/remote-execution-pattern.md`, and `docs/ARCHITECTURE.md` → "Two execution contexts" for the full generation-time-vs-runtime distinction.

Generated repositories are local-runtime repositories. Do not generate or document remote host execution guardrails inside them because SSH execution is intentionally out of scope. During generation, an explicitly supplied remote login command containing an IPv4 address MUST be used externally to load, install, self-check, and smoke-test every local output before completion.

### What the field means

Each comma-separated token names an MCP server that the agent must have active to complete the benchmark implementation and execution tasks. The token names map to the servers below. Confirm each required server is connected and authenticated before proceeding with any task that depends on it.

| Token | MCP Server | Used For |
|---|---|---|
| `AMDDigitalOcean` | AMD Digital Ocean | Optional reference only; not used by local-only workload generation |
| `SSH` | SSH / remote shell | Optional reference only; not used by local-only workload generation |
| `FileSystem` | Local filesystem | Reading and writing repository files, results, and config locally |
| `GitHub` | GitHub | Cloning benchmark dependency repositories (e.g., `github.com/ROCm/rocBLAS`) |
| `HuggingFace` | Hugging Face Hub | Downloading model weights required by LLM Serving and End-to-End Pipeline workloads |
| `Docker` | Docker | Pulling or building container images when the workload runs inside a container |
| `Grafana` | Grafana | Pushing parsed metrics to a Grafana dashboard for time-series visualization |

### Rules

1. **Read `Model Context Protocols` from `benchmark_specification.json` before writing any implementation code.** The required servers vary per workload — do not assume a fixed set.

2. **Confirm connectivity before use.** If a required MCP server is listed but not connected or authenticated, stop and surface the missing server to the user before continuing. Do not attempt to proceed without it — silent failures (e.g., a missing local filesystem dependency causing `run_benchmark.sh` to fail mid-execution) are harder to diagnose than an upfront gap.

3. **Do not activate servers not listed in the field.** Only the servers named for this benchmark are in scope. Do not connect to or invoke additional MCP servers speculatively.

4. **Scope of use.** MCP servers are for execution and data movement tasks only — FileSystem for local reads/writes, GitHub for cloning, HuggingFace for weight downloads, Docker for container operations, Grafana for metric push. Do not use MCP servers to bypass the coding standards or alter the protected files listed in each agent's configuration file (e.g., `.claude/CLAUDE.md` for Claude Code).

5. **Credentials and secrets.** MCP server authentication credentials must never be written to any committed file. If a connection requires a token or key, confirm it is supplied via environment variable or the MCP server's own secure credential store — never hardcoded in a script, YAML, or `.env` file committed to the repository. The `.gitignore` rule excluding secrets applies here.

### Checklist addition

Before reporting implementation complete, verify:

```bash
# Confirm the Model Context Protocols field was read from benchmark_specification.json
# and every listed server was confirmed connected before execution began.
# This is a manual confirmation — no grep can substitute for it.
grep '"Model Context Protocols"' benchmark_specification.json
```

The output must match the servers you confirmed active during the run. If the field lists a server you did not use (e.g., `Grafana` on a benchmark that has no metric-push step), document why it was not needed as an inline comment in your execution log — do not silently skip it without acknowledgement.
