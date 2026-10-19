# docs/repository-template.md

This file is the **single source of truth for repository layout** across all `gpu-bench-*` / `sys-bench-*` benchmark repositories. Other docs (`AGENTS.md`, `.claude/CLAUDE.md`) must reference this file rather than re-listing the tree themselves.

When used from the template workspace, this layout applies inside the generated repository subdirectory named `<Workload Number>-<Repo Name>` at project root (e.g. `<project-root>/<workload-number>-<repo-name>/`, where `<template-directory>/` is also under `<project-root>/`). Publish that same `<Workload Number>-<Repo Name>` string as the GitHub repository name. The workbook `Repo Name` field stays unprefixed.

Each generated repository also contains a complete active copy of the source template at `<source-template-name>_copy/` during generation; all generation utilities and Phase 0–4 actions run from that nested copy. The nested copy is a local generation workspace, is gitignored, is not published, and must not be required by the completed workload at runtime. It is removed once the workload passes (`scripts/create_one_workload.py` does this automatically, or run `scripts/remove_template_copy.py --repo-root <repo>`); `results/generation_manifest.json` keeps `template_copy_path`, `template_copy_sha256`, and `template_copy_removed_at` as the provenance record.

Within the source template, the shared document templates live under `templates/`. The initializer copies them to the generated repository root, where the generated-repository contract expects them.

For the doc-hierarchy / read-priority order (which file to consult for what), see `AGENTS.md`, `docs/generation-workflow.md`, and `.claude/CLAUDE.md` — it is intentionally not repeated here, to avoid two sources of truth for the same information.

---

## Marker legend

| Marker | Meaning |
|---|---|
| *(none)* | Generic scaffolding — present in every `gpu-bench-*` repo regardless of workload |
| `*` (BMVaries) | Present in most repos, but content/filename varies by workload or is optional depending on workload needs |
| `**` (BMUnique) | Workload-specific file whose name and content are unique to this benchmark — shown below using a real example for illustration only |

Anything below marked `*` or `**` may legitimately be **absent** in a given repo if the workload doesn't need it. Anything unmarked is mandatory (cross-check against `AGENTS.md`'s "Mandatory Repository Structure" section, which lists only the always-required subset).

---

## File placement guidance

- User-facing documentation → `README.md` or `docs/`
- Benchmark requirements (the "why") → `PRD.md`
- Technical implementation requirements (the "how") → `SPEC.md`
- Shared AI-agent rules → `AGENTS.md`
- Claude-specific instructions → `.claude/CLAUDE.md`
- Generation templates for `PRD.md` / `SPEC.md` / `README.md` → `PRD_TEMPLATE.md` / `SPEC_TEMPLATE.md` / `README_TEMPLATE.md` (repo root; shared and generic across all benchmarks — see `.claude/CLAUDE.md`, do not edit per-benchmark)
- Source code → `src/`
- Orchestration scripts → `scripts/`
- Validation fixture sentinels → `tests/fixtures/`
- Generated benchmark outputs (gitignored) → `results/`

Do not invent new top-level directories unless the change is required by the benchmark, and document the addition in both `README.md` and `SPEC.md`.

---

## Repository Layout — generic scaffolding (mandatory in every repo)

```
<repo-root>/
├── TEMPLATE_00_32_copy/                 # Active source-template copy during generation only; removed once the workload passes
├── README.md                                 # User-facing quick start and prompt forms
├── docs/AI_AGENT_INSTRUCTIONS.md             # Authoritative AI generation instructions
├── AGENTS.md                       # Cross-agent coding guidance
├── .claude/
│   └── CLAUDE.md                   # Claude-specific coding guidance (not at repo root)
├── PRD_TEMPLATE.md                 # Generation template + agent instructions for PRD.md (shared, generic — do not edit per-repo)
├── SPEC_TEMPLATE.md                # Generation template + agent instructions for SPEC.md (shared, generic — do not edit per-repo)
├── README_TEMPLATE.md              # Generation template + agent instructions for README.md (shared, generic — do not edit per-repo)
├── PRD.md                          # Product requirements (generated from PRD_TEMPLATE.md + benchmark_specification.json)
├── SPEC.md                         # Engineering specification (generated from SPEC_TEMPLATE.md + benchmark_specification.json)
├── README.md                       # Human-facing overview (generated from README_TEMPLATE.md + benchmark_specification.json)
├── LICENSE                         # Repository license terms (root)
├── legal/
│   └── NOTICE                      # Legal notices
├── benchmark_specification.json       # Single source of truth for benchmark metadata (generated in Phase 0)
├── implementation_components/              # Reusable automatically discovered generation components
│   ├── README.md
│   ├── component.schema.json
│   └── <component-id>/
│       ├── component.json          # Semantic selectors + overlay paths
│       └── files/                  # Reusable deterministic implementation assets
├── schemas/
│   ├── benchmark_specification.schema.json # Contract for benchmark_specification.json structure and required fields
│   └── generation_report.schema.json    # Contract for results/generation_manifest.json
├── setup.sh                        # Idempotent environment bootstrap
├── run_benchmark.sh                # Main benchmark entrypoint
├── requirements.txt                # Direct Python runtime dependencies for this workload
├── .gitignore                      # Ignore generated artifacts (build, results, venvs)
├── .gitattributes                  # Enforce LF line endings for scripts/docs/configs
│
├── .github/
│   ├── CODE_OF_CONDUCT.md          # Community conduct standards
│   ├── CONTRIBUTING.md             # Contribution guidelines
│   ├── copilot-instructions.md     # Thin pointer to AGENTS.md
│   ├── PULL_REQUEST_TEMPLATE.md    # Standard PR checklist
│   ├── SECURITY.md                 # Vulnerability reporting guidance
│   ├── ISSUE_TEMPLATE/             # Bug/feature issue templates
│   └── workflows/
│       ├── ci.yml                  # Thin caller → shared-workflows ci.yml@v1 (hosted lint/schema/structure, no GPU)
│       └── gpu-smoke.yml           # Thin caller → shared-workflows gpu-smoke.yml@v1 (manual, self-hosted GPU)
│
├── config/
│   ├── benchmark_config.yaml       # Sweep parameters from Parameters_SmokeBaselineExtend + optional baselines/thresholds
│   ├── machines.yaml               # Machine/droplet definitions
│   ├── hardware_profile.{gpu}.yaml # GPU chip characteristics and peak values
│   └── hw_sw_info_commands.xlsx    # Excel source for post-run HW/SW inventory commands
│
├── docs/
│   ├── CHANGELOG.md                # Chronological record of updates
│   ├── GITHUB_PUBLISH_WORKLOAD_REPO.md # Independent workload publication instructions
│   ├── architecture.md             # Data-flow diagram, schema, config-to-code map
│   ├── environment.md              # Baseline stack: OS, ROCm/CUDA, Python, compiler versions
│   ├── generation-workflow.md      # Authoritative five-phase generation workflow
│   ├── machine-checkable-contracts.md # Schema and contract validator usage
│   ├── host-prerequisite-contract.md # Host package derivation and setup verification
│   ├── raw-output-parser-contract.md # Required parser behavior for real tool output
│   ├── rocm-reboot-install-contract.md # Required ROCm reboot + systemd auto-resume setup contract
│   ├── rocm-pytorch-install-contract.md # ROCm PyTorch wheel and GPU verification contract
│   ├── run-output-contract.md      # Required end-of-run summary output contract
│   ├── remote-execution-pattern.md # Deprecated reference (template is local-only)
│   ├── reboot-resume-pattern.md    # Reference reboot/resume continuation patterns (local)
│   ├── repository-template.md      # This file
│   ├── SUBMISSION_CHECKLIST.md     # Completion gate
│   └── troubleshooting.md          # Common failure modes and fixes
│
├── scripts/
│   ├── extract_benchmark_definition.py # Template utility: matrix row → benchmark_specification.json
│   ├── create_generated_repo.py     # Template utility: complete active-copy orchestrator
│   ├── init_generated_repo.py      # Template utility: scaffold bootstrap and profile application
│   ├── validate_template_inputs.py # Contract validator for benchmark_definition and generation manifest
│   ├── build.sh                    # Build or locate the benchmark binary
│   ├── parse_results.py            # Parse raw output → SQLite + summary.json
│   ├── validate_results.py         # Lightweight SQLite validator
│   ├── generate_collect_hw_sw_info.sh # Generate collector from the Excel command catalog
│   ├── collect_hw_sw_info.sh       # Post-run vendor-filtered HW/SW inventory collector
│   ├── update_runtime_ledger.py    # Append one normalized row to /var/opt/benchmarks/runtime_ledger.csv
│   ├── print_benchmark_definition.py # Print this workload's matrix row (field/value)
│   ├── ensure_setup.sh              # Basic setup-on-demand guard for run_benchmark.sh
│   ├── cleanup.sh                  # Remove stale artifacts
│   ├── self_check_generated_repo.sh # Generated-repo-local contract checks (run from generated repo root)
│   ├── check_github_publish_ready.sh # Final GitHub publication-readiness gate
│   ├── lib/
│       ├── common.sh               # Shared logging, die()/ledger-on-error, wait_for_server (600 s), sources hipcc_host_gcc.sh
│       ├── hipcc_host_gcc.sh       # Pin hipcc to GCC 15/14/13 so Clang 24 HIP wrappers find <cstdlib>
│       ├── reboot_resume.sh        # Helper: local reboot state + resume after login
│       ├── remote_reboot_wait.sh   # Deprecated helper retained for compatibility; do not use in local-only flows
│       ├── rocm_install.sh         # PROTECTED dispatcher: sources the Ubuntu-specific library
│       ├── rocm_install_24_04.sh   # PROTECTED: Ubuntu 24.04 / ROCm 10.1.0 functions
│       ├── rocm_install_26_04.sh   # PROTECTED: Ubuntu 26.04 / ROCm 10.1.0 functions
│   └── templates/
│       ├── setup_rocm_reboot_skeleton.sh # Reusable setup.sh skeleton for ROCm reboot flows
│       └── run_benchmark_help_skeleton.sh # Copy-this usage() and early --help / --matrix-definition handler
│
├── results/                        # Gitignored benchmark outputs
│   ├── .gitkeep
│   ├── generation_manifest.json    # Required traceability metadata for generated repositories
│   ├── install_status.txt*         # Optional setup-time phase/step status log (reboot-driven install flows)
│   ├── install_commands.txt*       # Bare executed install commands (one command per line)
│   ├── raw/.gitkeep
│   └── parsed/.gitkeep
│
├── src/                            # See "src/ variants" below — content depends on workload type
│
└── tests/
    └── fixtures/
        └── .gitkeep                # Placeholder — benchmark.db is generated on-the-fly by validate_results.py --seed-fixture
```

`tests/` holds only the fixture directory sentinel. There are no unit-test harness files (`conftest.py`, `test_integrity.py`, etc.) in this architecture. All validation is performed by `scripts/validate_results.py` — see `AGENTS.md`'s "Execution-Loop Validation Contract" section for the full specification.

**On `*_TEMPLATE.md` vs. their generated counterparts:** `PRD_TEMPLATE.md`, `SPEC_TEMPLATE.md`, and `README_TEMPLATE.md` are shared, generic files — identical across every `gpu-bench-*` / `sys-bench-*` repo, same category as `AGENTS.md` and `.claude/CLAUDE.md`. `PRD.md`, `SPEC.md`, and `README.md` are the per-benchmark outputs an agent generates from those templates plus `benchmark_specification.json` (see the root `README.md` prompt forms and `docs/AI_AGENT_INSTRUCTIONS.md`). Both the template and its generated output must be present; do not treat one as a substitute for the other, and do not hand-edit a generated file in a way that diverges from what its template would produce.

**On `BenchmarkSpecDefinitions.xlsx`:** This file belongs to the template — it is the upstream human-maintained matrix for all workloads and is retained only inside the complete nested active template copy. The generated workload repository root contains only the extracted `benchmark_specification.json`; the nested active copy retains the matrix for reproducibility.

**On `hw_sw_info_commands.xlsx`:** This command catalog is copied into each generated repository under `config/`. The generated `scripts/collect_hw_sw_info.sh` embeds its rows so collection works without requiring Excel or the workbook at runtime. After each workload run, the collector writes vendor-filtered hardware, software, and failed-probe reports into the per-run artifact directory. The same directory also receives `metrics_summary.txt` (Benchmark Summary without `[INFO]` prefixes) from `write_metrics_summary_txt` in `scripts/lib/common.sh`.

**On `runtime_ledger.csv`:** Each completed or failed `run_benchmark.sh` invocation appends one row to `/var/opt/benchmarks/runtime_ledger.csv`. The file is an operator-owned host-level ledger, not a repository artifact; `scripts/update_runtime_ledger.py` creates the header and serializes values with CSV quoting. Required column order:

`table_index_number`, `run_id`, `workload_number`, `runtime_root_dir`, `benchmark_profile`, `start_datetime`, `total_runtime_mm_ss`, `exit_code`, `failure_stage`, `failure_detail`, `raw_run_dir`, `hostname`, `gpu_name`, `gpu_vram`, `gpu_count`, `os_version`, `cpu_model`, `workload_name`, `metric_1_def`, `metric_1_result`, … `metric_7_def`, `metric_7_result`, `run_benchmark_command_submitted`, `run_benchmark_command_fully_resolved`, `Parameter_01_Name`, `Parameter_01_Value`, … `Parameter_20_Name`, `Parameter_20_Value`, `parameters_set`, `notes`.

`exit_code` is the `run_benchmark.sh` process result (`0` or nonzero). `failure_stage` is `ok` on success, otherwise one of `setup|collection|parse|validation|timeout|integrity|other`. `failure_detail` is the one-line reason for a nonzero `exit_code` (empty on success). `raw_run_dir` is that invocation's `results/raw/<timestamp>_<repo>_<host>` directory. `run_benchmark_command_submitted` is the argv as entered (`bash run_benchmark.sh` plus the original flags). `run_benchmark_command_fully_resolved` is that submitted string plus yaml defaults that were not already on the command line. `Parameter_01_Name`/`Parameter_01_Value` through `Parameter_20_Name`/`Parameter_20_Value` are the workbook `Parameter_*` slots with effective values after CLI overrides. Unused slots stay blank. `parameters_set` is rebuilt from those slots. Do not write a second exit-code column.

`gpu_name` is the Card Series / MARKET_NAME product string (for example `AMD Instinct MI300X VF`), not the `rocm-smi` banner. `gpu_vram` is the VRAM total-memory value only. `gpu_count` and `cpu_model` sit with the other host/GPU/OS fields, before `workload_name` and the metric pairs.

`total_runtime_mm_ss` is elapsed runtime as `mm:ss`. Callers may still pass `--total-runtime` in seconds; the helper converts it.

**On `implementation_components/`:** Components keep the template reusable while making workload-specific generation reproducible. `scripts/resolve_implementation_components.py` evaluates each component manifest selector against benchmark specification fields; components are not keyed by workload number or repository name. `scripts/init_generated_repo.py` applies all compatible, non-conflicting overlays. Component implementation files may specialize the workload, but may not override matrix-derived identity or contradict protected installation contracts. When a component overlay exists, keep those generated files byte-identical to `implementation_components/<id>/files/` rather than regenerating equivalent known-good assets. A smoke failure inside an overlay is repaired by updating that template file, the sibling, and the matching `sha256` in `results/overlay_lock.json` together, then rechecking with `create_one_workload.py --validate-only`.

---

## `src/` variants by workload type

The generic tree above intentionally leaves `src/` unspecified, because its contents differ by whether the workload compiles custom kernels or drives a pre-built vendor binary.

### Variant A — pre-compiled vendor binary (e.g., this repo: `rocblas-bench`, `babelstream`'s prebuilt mode)

```
src/
└── common/
    └── .gitkeep                    # No custom kernel source needed; orchestration lives in scripts/
```

Do not generate stub HIP/C++ source if no custom kernel is required by the workload.

### Variant B — custom HIP/CUDA kernel source (example: `gpu-bench-babelstream-hbm-bandwidth`)

```
src/
├── babelstream_hip/                 # ** workload-specific: HIP backend implementation
│   ├── CMakeLists.txt               # CMake build, gfx942 target
│   ├── main.cpp                     # Driver, CLI, timing loop
│   ├── Stream.h                     # Abstract kernel interface declaration
│   ├── Stream.cpp                   # Host-side verification helpers
│   ├── HIPStream.cpp                # MI300X HIP kernel implementations
│   └── utils.h                      # HIP error-check macros
└── common/
    ├── benchmark_utils.cpp          # Bandwidth math implementation
    └── benchmark_utils.h            # Bandwidth math, stats header
```

Everything under `babelstream_hip/` is `**` (BMUnique) — shown only as an illustration of the custom-kernel pattern; a different custom-kernel workload would use different filenames.

---

## `config/` workload-specific additions

Beyond the generic `benchmark_config.yaml` / `machines.yaml` / `hardware_profile.{gpu}.yaml`, a workload may add its own config files. Example, from `gpu-bench-babelstream-hbm-bandwidth`:

```
config/
├── babelstream_config.h**           # Array size, iterations, precision
└── mi300x_tuning.json*              # MI300X-specific flags, thread/block sizes
```

These are `**`/`*` — present only if the workload needs compile-time or tuning config beyond what `benchmark_config.yaml` covers. This GEMM/rocBLAS repo needs neither.

---

## Optional repository-wide files (not currently mandatory per `AGENTS.md`)

The following appear in some `gpu-bench-*` repos but are **not** required by `AGENTS.md`'s mandatory structure list. Add them only if the project specifically needs them, and update `AGENTS.md` if they become mandatory across the family:

- `.github/CODE_OF_CONDUCT.md` — community conduct standards
- `.github/CONTRIBUTING.md` — contributor guidelines
- `SECURITY.md` — security disclosure policy
- `.github/ISSUE_TEMPLATE/bug_report.md`, `.github/ISSUE_TEMPLATE/feature_request.md`
- `docs/api-spec.md` — CLI and output API contracts, for workloads with a programmatic API
- `docs/test-plan.md` — acceptance test criteria and gates, for workloads with multi-stage validation
- `docs/nvidia-h100-differences.md` — only for AMD-first repos with a documented NVIDIA port path
