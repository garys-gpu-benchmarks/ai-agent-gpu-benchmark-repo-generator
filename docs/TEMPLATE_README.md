# TEMPLATE_README.md

Template version: **0.9.4** (`TEMPLATE_00_73`, 00_72 collectors with spec-aligned 101–132 / 201–232 workbook)

This directory is the source template for generating one or more workload-specific benchmark repositories. It is for human maintainers of the template, not for the final generated workload repositories.

See [`CHANGELOG.md`](CHANGELOG.md) for the version history and detailed changes in this and future template releases. To publish a generated workload to GitHub next week, start at [`GITHUB_PUBLISH_GENERATOR_OPERATIONS.md`](GITHUB_PUBLISH_GENERATOR_OPERATIONS.md).

Current runner rules live in [`AGENTS.md`](../AGENTS.md) §20.2 and §20.25. Smoke, baseline, and extended timings come only from the workbook `Parameters_SmokeBaselineExtend` sheet. Known-good overlay files live under `implementation_components/` and must not be rewritten after init; see [`implementation_components/README.md`](../implementation_components/README.md). Ubuntu 24.04 and 26.04 / ROCm 10.1.0 pins live in [`rocm-pytorch-install-contract.md`](rocm-pytorch-install-contract.md), including the hipcc GCC 15 pin (`scripts/lib/hipcc_host_gcc.sh`) and the rocHPL 64-bit host-allocation overlay. 301–332 and 401–432 repository names use a `-ubu2604` suffix. NVIDIA 401–432 use CUDA 13.3 on host-native Ubuntu 26.04. The only runtime workbook is `BenchmarkSpecDefinitions.xlsx`. Historical `_1_0` / `_1_1` copies belong in `archive/` and must not be extracted. Author smoke/baseline/extended parameter values on the `Parameters_SmokeBaselineExtend` sheet; `Workload_Definitions` command columns are generated from that sheet. Ledger column order and GPU-name/VRAM parsers changed in 1.04; the smoke/baseline/extended parameter contract is 1.05. Unreleased 00_53 also replaces `runtime_exit_code` with `failure_stage` / `failure_detail` / `raw_run_dir` and adds `run_benchmark_command` before `parameters_set`. Unreleased 00_54 keeps that command column in place as `run_benchmark_command_submitted` and adds `run_benchmark_command_fully_resolved` immediately to its right, then `Parameter_01_Name`/`Parameter_01_Value` through `Parameter_20_Name`/`Parameter_20_Value` before `parameters_set`. See [`CHANGELOG.md`](CHANGELOG.md).

Benchmark comparison CSV SOP:

- After implementation, create `<repo>/benchmark_actual.csv` from the designated workload row in `BenchmarkSpecDefinitions.xlsx`.
- Shift workbook headers and original values one column right; use column A values ``, `Original`, and `Actual` for rows 1–3.
- Add row 4 and write `Changed` when the Actual cell diverges from Original.
- Populate successive `InstalledTool_NN: Version` columns with observed executable/tool names and versions.
- Write row 3 as the replacement cell value in imperative form; do not describe divergence, omissions, or what is not implemented.
- Write the CSV as UTF-8 with a BOM (`utf-8-sig`) so Excel preserves em dashes and other Unicode workbook values. If Excel has the CSV open, close it before replacing the file; Windows may lock the original.

Network workload caveat (applies to iPerf-like UDP tests):

- UDP runs should not use `-b 0`; enforce a positive rate floor (for example `1M`).
- UDP payload sizes should stay MTU-safe; avoid large `buffer_length` values like `128K` unless jumbo-frame path validation is explicitly configured.

## What Belongs In The Template

Keep only stable, shared inputs that apply across generated repositories:

- `README.md` (including supported AI-agent prompt forms)
- `docs/AI_AGENT_INSTRUCTIONS.md`
- `AGENTS.md`
- `.claude/CLAUDE.md`
- `templates/PRD_TEMPLATE.md`
- `templates/SPEC_TEMPLATE.md`
- `templates/README_TEMPLATE.md`
- `docs/SUBMISSION_CHECKLIST.md`
- `docs/repository-template.md`
- `docs/CHANGELOG.md`
- `docs/generation-workflow.md`
- `docs/machine-checkable-contracts.md`
- `scripts/extract_benchmark_definition.py`
- `scripts/generate_benchmark_config.py`
- `scripts/sync_matrix_profile_commands.py`
- `scripts/matrix_profile_values.py`
- `scripts/prompt_workflow.py`
- `scripts/generate_workload_parameters.py`
- `scripts/verify_generation_workflow.py`
- `scripts/validate_template_inputs.py`
- `scripts/smoke_check_generated_repo.sh`
- `scripts/init_generated_repo.py`
- `scripts/self_check_generated_repo.sh`
- `scripts/templates/run_benchmark_help_skeleton.sh`
- `implementation_components/README.md`, `implementation_components/component.schema.json`, component manifests, and reusable overlays
- `scripts/lib/rocm_install.sh` (dispatcher), `scripts/lib/rocm_install_24_04.sh`, `scripts/lib/rocm_install_26_04.sh`, `scripts/lib/hipcc_host_gcc.sh`
- `scripts/templates/setup_nvidia_skeleton.sh`, `scripts/install_pytorch_nvidia.sh`, `docs/nvidia-pytorch-install-contract.md`
- `BenchmarkSpecDefinitions.xlsx` (the only runtime workbook; do not extract `archive/` copies)
- `docs/GITHUB_PUBLISH_WORKLOAD_REPO.md`
- `docs/SIBLING_WORKLOAD_NOTES.md`
- `legal/NOTICE`
- `config/hardware_profile.mi300x.yaml`
- `config/workload_parameters.yaml`
- `schemas/`
- `.github/copilot-instructions.md`
- `.github/CODE_OF_CONDUCT.md`
- `.github/CONTRIBUTING.md`
- `.github/SECURITY.md`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/workflows/ci.yml`
- `config/pyproject.toml`
- `.gitignore`
- `LICENSE`

Generated-repo workflows are rendered, not copied: `templates/workload/.github/workflows/{ci,gpu-smoke}.yml` plus `config/ci_contract.yaml` produce the two thin callers, and `templates/shared-workflows/` is emitted once by `scripts/emit_shared_workflows.py`. Neither is an active workflow in this template.

`config/machines.yaml` may remain in the template only if it describes a shared execution target used by all generated workloads. If machine details vary by workload, generate it per workload instead.

## Repository-local Python environment

Each generated repository uses its own isolated Python environment at `<repo-root>/.venv`. This keeps dependencies isolated when many repositories share one host.

`.venv`:

- Is created idempotently by `setup.sh`.
- Is used by `setup.sh`, `run_benchmark.sh`, build helpers, and reboot-resume services.
- Is excluded from version control.
- Must not be replaced with a global package installation.
- Set `BENCHMARK_PYTHON` when a repository requires a specific installed Python interpreter; its matching `pythonX.Y-venv` package must already be available.
- Must be set explicitly before provisioning, for example:

```bash
export BENCHMARK_PYTHON=/usr/bin/python3.14
bash setup.sh
bash run_benchmark.sh --profile smoke --validate
```

If `.venv` is missing, setup creates it rather than installing Python packages globally or silently using another environment. The AI coding agent may run `setup.sh` and install packages during generation when useful, but must set the repository-local `.venv` first. The same rule applies to operators provisioning the repository after generation.

## What Must Be Generated Per Workload

The AI agent should create these files only after Phase 0 produces a schema-validated root-level `benchmark_specification.json`, and only inside a generated repository subdirectory named `<Workload Number>-<Repo Name>` at project root (e.g. `<project-root>/<workload-number>-<repo-name>/`, not `<project-root>/<template-directory>/<repo-name>/`). That same `<Workload Number>-<Repo Name>` string is the GitHub repository name (for example `128-gpu-bench-amd-vllm-throughput-latency`). The workbook `Repo Name` field stays unprefixed:

- `<Workload Number>-<Repo Name>/benchmark_specification.json`
- `<Workload Number>-<Repo Name>/PRD.md`
- `<Workload Number>-<Repo Name>/SPEC.md`
- `<Workload Number>-<Repo Name>/README.md`
- `<Workload Number>-<Repo Name>/config/benchmark_config.yaml`
- `<Workload Number>-<Repo Name>/setup.sh`
- `<Workload Number>-<Repo Name>/run_benchmark.sh`
- `<Workload Number>-<Repo Name>/requirements.txt`
- workload-specific `<Workload Number>-<Repo Name>/scripts/` files
- workload-specific `<Workload Number>-<Repo Name>/src/` files, if needed
- `<Workload Number>-<Repo Name>/results/.gitkeep`, `<Workload Number>-<Repo Name>/results/raw/.gitkeep`, and `<Workload Number>-<Repo Name>/results/parsed/.gitkeep`
- `<Workload Number>-<Repo Name>/tests/fixtures/.gitkeep`
- `<Workload Number>-<Repo Name>/docs/CHANGELOG.md`
- `<Workload Number>-<Repo Name>/GENERATION_REPORT.md`
- `<Workload Number>-<Repo Name>/results/generation_manifest.json`
- workload-specific `<Workload Number>-<Repo Name>/docs/` files, if useful

## What Should Never Be Pre-Populated

Do not ship completed workload artifacts in the generic template. They are easy for an AI agent to copy too literally.

Do not pre-populate:

- `benchmark_specification.json`
- `config/benchmark_config.yaml`
- generated `PRD.md`, `SPEC.md`, or `README.md`
- `docs/CHANGELOG.md`
- `GENERATION_REPORT.md`
- `run_benchmark.sh`, `setup.sh`, or workload-specific `scripts/` at template root
- a generated workload subdirectory (for example `sys-bench-stream-ddr5-bandwidth/`)
- deployment checklists from prior workloads
- raw or parsed benchmark results
- fixture database files
- workload-specific source code
- workload-specific troubleshooting docs

Avoid carrying examples from previous workloads such as FIO, NVMe, GEMM, rocBLAS, BabelStream, or other benchmark implementations unless they are placed under a clearly marked non-authoritative examples directory.

## Expected Phase 0-4 Flow

1. The agent parses the directly submitted workload prompt, records it as a timestamped project-root `AI_AGENT_PROMPT_SUBMITTED_<WORKLOADS>_<UTC_TIMESTAMP>.md` artifact, and validates requested workloads against `BenchmarkSpecDefinitions.xlsx`.
2. After validation, the agent reads `Repo Name` from `benchmark_specification.json`, creates `<project-root>/<Workload Number>-<Repo Name>/`, copies required shared template scaffolding into that directory, and treats it as the generated repository root.
3. Phase 1 begins only after Phase 0 validation. The agent reads the source guidance files in the priority order defined by `AGENTS.md` and `docs/AI_AGENT_INSTRUCTIONS.md`.
4. Phase 2 generates `<Workload Number>-<Repo Name>/PRD.md`, `<Workload Number>-<Repo Name>/SPEC.md`, and `<Workload Number>-<Repo Name>/README.md` from their templates and `benchmark_specification.json`.
5. Phase 3 generates only the workload-relevant repository files needed to run, parse, validate, document, and operate the benchmark inside `<Workload Number>-<Repo Name>/`.
6. Phase 4 runs `docs/SUBMISSION_CHECKLIST.md` in order and reports exact pass/fail results.
7. Run `bash scripts/smoke_check_generated_repo.sh ../<Workload Number>-<Repo Name>` from `<template-directory>/` to confirm output location and required generated artifacts.
8. Run `bash scripts/self_check_generated_repo.sh` from `<Workload Number>-<Repo Name>/` to confirm generated-repo-local contracts.

The key guardrail is that no code, docs, configs, workflows, or reports should be generated until `benchmark_specification.json` has been extracted and schema-validated.
