[![Template CI](https://github.com/garys-gpu-benchmarks/ai-agent-gpu-benchmark-repo-generator/actions/workflows/ci.yml/badge.svg)](https://github.com/garys-gpu-benchmarks/ai-agent-gpu-benchmark-repo-generator/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

# AI Coding Agent Spec-Driven GPU Benchmark Repo Generator

A template-driven generation framework that enables AI coding agents to autonomously build, validate, and document GPU benchmark repositories. It converts single-row workload definitions into complete, standardized, execution-ready codebases with zero manual scaffolding required. Included workload domains span GPU compute, LLM serving, memory and data transfer, CPU and system performance, end-to-end pipelines, and validation/correctness testing.

Instead of manually assembling setup scripts, SPEC files, PRDs, CI workflows, and parsing logic for each workload, the agent consumes this template and executes a strict multi‑phase workflow defined in [`AGENTS.md`](AGENTS.md) and [`docs/generation-workflow.md`](docs/generation-workflow.md). The result is a repository that installs the runtime stack, validates the environment, and executes a smoke test, producing reliable, reproducible benchmark repos at scale. This transforms benchmark creation from a manual, error‑prone process into a scalable, automated pipeline.

### AI-Agent GPU Benchmark Repository Generator — High-Level Capabilities

#### Repository Generation & Scale

- **Single Excel Row → Full Repository Generation** — Generates an entire benchmark repo from one spreadsheet row plus one AI agent prompt.
- **Optimized for AI Coding Agents** — Designed for Claude Code, Copilot, Cursor, and similar agents to ensure consistent output.
- **Starter Benchmark Library** — `BenchmarkSpecDefinitions.xlsx` defines 32 AMD Ubuntu 24.04, 32 NVIDIA Ubuntu 24.04, 32 AMD Ubuntu 26.04, and 32 NVIDIA Ubuntu 26.04 workloads ready to generate. Workloads 101–132 and 201–232 describe the `TEMPLATE_00_72` collectors. `implementation_components/` supplies reusable implementation assets selected from `config/implementation_packs.yaml` by Workload Number and GPU Vendor; users do not select components in the workbook. Generated repositories are created as siblings of this generator, not as pre-built folders in this tree.
- **Scales to Hundreds of Benchmarks** — A user can add rows to Excel and generate dozens or hundreds of repositories without manual coding.
- **Batch Mode Generation** — Supports lists and ranges (e.g., "101 through 110") to generate multiple repositories from one prompt.
- **Six Execution Domains** — GPU Compute, LLM Serving, Memory/Transfer, CPU/System, End-to-End Pipeline, Validation/Correctness.

#### Setup & Execution

- **Quick Start Guide Included** — Provides a streamlined "Generate Your First Benchmark Repository in Ten Minutes" document.
- **Ready-to-Run Local Repositories** — Delivers every file and directory necessary to run the benchmark end-to-end on the target machine.
- **Effortless Setup & Execution** — Install with `bash setup.sh --assume-yes`. A bare `bash run_benchmark.sh` is smoke. Pass `--baseline` or `--extended` for the longer profiles.
- **Reboot-Resilient Install** — A single end-to-end install command that saves state and resumes across reboots.
- **Safe, Idempotent Setup Scripts** — Setup scripts can be rerun without corrupting state.
- **Flexible Benchmark Profiles** — Supports smoke, baseline, and extended runs via CLI flags.
- **Supports Local + Remote Development** — Supports integrating a remote Linux VM which can be used for code development and validation.
- **Isolated Python Environments** — Each generated repo uses its own Python venv.

#### Repository Structure & AI-Agent Guidance

- **Rich Template Library** — Includes templates for PRD, README, SPEC, scripts, scaffolding, CI workflows, and GitHub files.
- **Detailed Reference Materials** — Generates README, PRD, SPEC, ARCHITECTURE documents customized per benchmark.
- **Consistent Repository Structure** — Every generated repo includes `src/`, `config/`, `scripts/`, `schemas/`, `tests/`, and `results/`.
- **Local Template Copy During Generation** — `create_generated_repo.py` materializes a nested `ai-agent-gpu-benchmark-repo-generator_copy/` while a workload is generated. `create_one_workload.py` removes it once the workload passes (`--keep-template-copy` keeps it); for other paths run `python3 scripts/remove_template_copy.py --repo-root <repo>`. Finished repositories therefore do not carry the copy, whose deep paths exceed the Windows 260-character limit. While it exists, the tree is gitignored and must not be published to GitHub.

#### Results & Observability

- **Rich CLI Details Mode** — Displays workload name, execution summary, framework, metrics, runtime language, and execution domain.
- **Timestamped Run Output Directory** — Saves results, commands, metrics, system info, and exit status per run.
- **Environment Logging** — Creates a log of installed software components and versions.
- **Excel-sourced HW/SW Inventory Capture** — Executes a post-run HW/SW inventory collection script generated from Excel command definitions.
- **Runtime Ledger** — Generates a per‑run one-line CSV ledger entry summarizing workload identity, runtime, metrics, and parameters.
- **SQLite Result Storage** — Stores parsed benchmark results in a portable database.
- **Replayable Command Log** — Records all executed benchmark commands for audit and reproducibility.

#### Validation & Quality Gates

- **Self-Validation via GitHub Actions** — Lints scripts, runs the test suite, validates schemas, renders and lints the CI templates, and verifies generator structure on every change.
- **One Shared, Versioned CI for Every Generated Repo** — Each workload gets two thin caller workflows (`ci.yml`, `gpu-smoke.yml`) that call one tagged `shared-workflows` repository; both sides are rendered from `config/ci_contract.yaml`. See [Continuous Integration](#continuous-integration).
- **Meets GitHub Community Standards** — LICENSE, CODE_OF_CONDUCT.md, CONTRIBUTING.md, SECURITY.md, issue templates, PR template.
- **Strict Submission Checklist** — Implements `SUBMISSION_CHECKLIST.md` as a completion gate.
- **Agent-Executed Completion Verification** — Requires passing every checklist item before declaring a repo complete.

## Requirements

- An AI coding agent capable of following multi-file, multi-phase written instructions (agent-agnostics rules defined in `AGENTS.md`).
- Python 3.12+ locally, for the extraction/validation scripts. From this directory: `pip install -e "config[dev]"` (or `pip install jsonschema openpyxl PyYAML`).
- `BenchmarkSpecDefinitions.xlsx` populated with your workload matrix (a starter copy is included). Author smoke/baseline/extended values on the `Parameters_SmokeBaselineExtend` sheet; `Workload_Definitions` command columns are generated from that sheet. Do not extract historical `_1_0` / `_1_1` copies; those belong in `archive/` only.
- A local or remote Ubuntu 24.04 or Ubuntu 26.04 target with an MI300X or an H100 GPU, for workloads that need real hardware to install/run against.

## Generate Your First Benchmark Repository in Ten Minutes

If you are starting from scratch and need an AMD Developer Cloud account and GPU droplet, first follow the [`AMD Developer Cloud Getting Started Guide`](docs/amd-developer-cloud-getting-started.md).

Steps to generate your first benchmark repository:

1. **Prerequisites**:
   - Git
   - An AI Coding Agent
   - An Ubuntu target for benchmark execution
   - Optional remote Ubuntu validation VM

2. **Set up your project root**:

   ```text
   mkdir my_project_root && cd my_project_root
   ```

3. **Clone the repository generator into project root directory**:

   ```text
   git clone https://github.com/garys-gpu-benchmarks/ai-agent-gpu-benchmark-repo-generator.git ai-agent-gpu-benchmark-repo-generator
   cd ai-agent-gpu-benchmark-repo-generator
   ```

4. **(OPTIONAL) Create a remote VM when the prompt includes an IP address**: On a VM provider (e.g., DigitalOcean, RunPod, AWS, Azure, or GCP), create a freshly installed Ubuntu server, configure access, and include its IPv4 address in the SSH command in the prompt. An IPv4 address makes remote validation mandatory: the AI Coding Agent must load every generated repository onto that VM, install it there, and run its self-check and smoke benchmark there before completion. This VM is not used by the generated repository at runtime.

5. **Choose workloads and submit a prompt**: Open `BenchmarkSpecDefinitions.xlsx`, select one or more workload numbers, attach `ai-agent-gpu-benchmark-repo-generator/docs/AI_AGENT_INSTRUCTIONS.md` to your AI Coding Agent, and submit one of the supported prompt forms below.

   ```text
   @ai-agent-gpu-benchmark-repo-generator/docs/AI_AGENT_INSTRUCTIONS.md
   Generate workload <WORKLOAD_NUMBER>.
   Remotely access Ubuntu VM with `ssh -i /path/to/.ssh/<amd_ssh_key> root@<REMOTE_HOST_IP>`
   ```

  Example 1: one workload with mandatory remote validation:

   ```text
   @ai-agent-gpu-benchmark-repo-generator/docs/AI_AGENT_INSTRUCTIONS.md
   Generate workload 101.
   Remotely access Ubuntu VM with `ssh -i /path/to/.ssh/<amd_ssh_key> root@<REMOTE_HOST_IP>`
   ```

   Example 2: one workload without remote validation:

   ```text
   @ai-agent-gpu-benchmark-repo-generator/docs/AI_AGENT_INSTRUCTIONS.md
   Generate workload 101.
   ```

   Example 3: multiple workloads:

   ```text
   @ai-agent-gpu-benchmark-repo-generator/docs/AI_AGENT_INSTRUCTIONS.md
   Generate workloads 121, 122.
   ```

   Example 4: inclusive workload range:

   ```text
   @ai-agent-gpu-benchmark-repo-generator/docs/AI_AGENT_INSTRUCTIONS.md
   Generate workloads 101 through 104.
   ```

   Workload lists may also use `and`, hyphen ranges, `to` ranges, or `ALL`. The agent validates the requested workloads against the workbook before generation.

6. **Agent records the submitted prompt and generates repositories sequentially**: The agent validates the selected workloads, creates one `AI_AGENT_PROMPT_SUBMITTED_<WORKLOADS>_<UTC_TIMESTAMP>.md` in `my_project_root/`, then creates and fully finishes each sibling repository one at a time with `create_generated_repo.py --workload <N>` before creating the next directory. If the supplied SSH command contains an IPv4 address, "fully finishes" includes loading the repository onto that VM, installing it there, and running its self-check and smoke benchmark there. 

7. **Execute the output**: Once completed, copy the repository (ie, `101-sys-bench-amd-rocm-stack-validation-ubu2404/`) to the Ubuntu target for benchmark execution, or, once published, clone its whole platform bundle there (see [On a GPU host](#on-a-gpu-host)). Enter the generated repository and run:

    ```bash
    bash setup.sh
    bash run_benchmark.sh --help
    bash run_benchmark.sh --profile smoke --validate
    ```

See [`docs/AI_AGENT_INSTRUCTIONS.md`](docs/AI_AGENT_INSTRUCTIONS.md) for the authoritative agent instructions and [`docs/generation-workflow.md`](docs/generation-workflow.md) for what the agent does at each phase.

The shared parameter catalog at `config/workload_parameters.yaml` is generated from `BenchmarkSpecDefinitions.xlsx`; run `python3 scripts/generate_workload_parameters.py --check` to validate active parameter names and `python3 scripts/verify_generation_workflow.py` for the deterministic workflow checks.

## Why this exists

Generating benchmark repos by hand doesn't scale past a handful of workloads, and letting an agent freelance the structure produces inconsistent repos that are hard to CI, diff, or maintain. This template fixes both problems by giving the agent:

- a single source of truth (`benchmark_specification.json`, extracted from `BenchmarkSpecDefinitions.xlsx`) that wins over every other file on conflict,
- a strict document read-order (see [`AGENTS.md`](AGENTS.md)) so agents from different vendors behave consistently,
- machine-checkable contracts (JSON Schemas under [`schemas/`](schemas)) instead of prose-only conventions,
- a reboot-safe ROCm install pattern for workloads that require a kernel driver install and reboot mid-setup, and
- a submission checklist the agent runs before declaring a generated repo complete.

## What this repository generates

For each selected workload, the agent creates a sibling repository under `my_project_root` using the workload number and exact repository name from the validated benchmark definition:

```text
my_project_root/
├── ai-agent-gpu-benchmark-repo-generator/
├── AI_AGENT_PROMPT_SUBMITTED_101_20260805_080015.md
└── 101_sys-bench-rocm-stack-validation/
    ├── benchmark_specification.json
    ├── PRD.md
    ├── SPEC.md
    ├── README.md
    ├── setup.sh
    ├── run_benchmark.sh
    ├── scripts/
    ├── config/
    ├── results/
    └── ai-agent-gpu-benchmark-repo-generator_copy/   # during generation only; removed once the workload passes
```

## Continuous Integration

### How it fits together

```text
config/ci_contract.yaml ──► templates/workload/.github/workflows/   ──► 2 thin callers in each of the 128 workload repos
   (owner, tag, inputs,     templates/shared-workflows/            ──► shared-workflows repo  (published once, tagged v1)
    runner labels, tools)   templates/suite-tools/                 ──► gpu-bench-suite repo   (run_benchmark_suite.sh, get_remote_info.sh, show_metrics.sh)
```

| Where | File | Runs on | When |
|---|---|---|---|
| each workload | `.github/workflows/ci.yml` → `shared-workflows/.github/workflows/ci.yml@v1` | GitHub-hosted | every pull request and push to `main`: shellcheck, ruff, `bash -n`, `compileall`, `--help`, spec schema, seeded-fixture validation, required files, actionlint |
| each workload | `.github/workflows/gpu-smoke.yml` → `shared-workflows/.github/workflows/gpu-smoke.yml@v1` | self-hosted `[self-hosted, gpu, <vendor>, <os_label>]` | only by hand (**Run workflow**): verify the pre-provisioned stack, record `results/environment.json`, run the chosen profile, upload results. Never on pull requests. |
| `shared-workflows` | `self-test.yml` | GitHub-hosted | every change to `shared-workflows`: actionlint plus `ci.yml` against a sample workload |

`init_generated_repo.py` renders the callers from the contract and refuses to finish if they do not match it. `self_check_generated_repo.sh`, `prepare_github_publish.sh` and `check_github_publish_ready.sh` fail a workload whose callers do not point at `shared-workflows`, lack `permissions`, carry their own `run:` steps, or let the GPU workflow start from a pull request. The full policy, including the `v1`/`v2` versioning rule, is in [`templates/shared-workflows/README.md`](templates/shared-workflows/README.md).

### Commands

Publishing is done by [`scripts/publish_benchmarks_to_github.sh`](scripts/publish_benchmarks_to_github.sh). This repository holds the master copy; it is never copied into generated workloads (`init_generated_repo.py` excludes it). The source folders are set at the top of the script under "Settings you may change":

```text
Z:\ServersProcsMemory\Projects\
├── Project341_TEMPLATE_00_104_20261008\TEMPLATE_00_104\
│   └── ai-agent-gpu-benchmark-repo-generator\        # GENERATOR_SOURCE
├── Project342_101_to_132_TEMPLATE_00_104_20261010\DIRECTORIES\   # 101-132
├── Project343_201_to_232_TEMPLATE_00_104_20261010\DIRECTORIES\   # 201-232
├── Project344_301_to_332_TEMPLATE_00_104_20261010\DIRECTORIES\   # 301-332
└── Project345_401_to_432_TEMPLATE_00_104_20261010\DIRECTORIES\   # 401-432
```

One folder per publish run:

```text
Z:\ServersProcsMemory\Github_Garys_GPU_Repos\
└── Publishing\
    ├── publish_benchmarks_to_github.sh             # copy of scripts/publish_benchmarks_to_github.sh
    └── Publish_20261010_02\
        ├── src_342_343_344_345\                    # filled by the script: the 128 workloads + ai-agent-gpu-benchmark-repo-generator
        ├── src_342_343_344_345_PubTree\            # created by the script (logs in _logs\)
        ├── src_342_343_344_345_Bundles\            # created by the script
        ├── shared-workflows\                       # built by the script from this generator
        └── gpu-bench-suite\                        # built by the script from this generator
```

**1. Publish** (Git Bash; use `/` in paths):

```bash
cd /z/ServersProcsMemory/Github_Garys_GPU_Repos/Publishing
cp /z/ServersProcsMemory/Projects/Project341_TEMPLATE_00_104_20261008/TEMPLATE_00_104/ai-agent-gpu-benchmark-repo-generator/scripts/publish_benchmarks_to_github.sh .
./publish_benchmarks_to_github.sh Publish_20261010_02/src_342_343_344_345
```

Step 0 creates the run folder if needed and copies in every workload (from the four `DIRECTORIES` folders) and the generator that it does not have yet; folders already there are kept. It prints how many workloads each batch has and notes a batch with fewer than 32.

The script builds `shared-workflows` and `gpu-bench-suite` with `scripts/emit_shared_workflows.py` from the generator copy in the run folder, publishes `shared-workflows` first (after its Self-test passes it tags the next `v1.x.0` and moves `v1`), then the workloads, the four bundles and this generator. If it stops, fix the problem and run the same command again; finished work is skipped.

**2. Preview the shared repositories** (optional, from this generator folder):

```bash
python3 scripts/ci_contract.py --show                                               # resolved owner, tag, tool versions
python3 scripts/emit_shared_workflows.py --output-root <publish folder> --check      # what would change
```

`<publish folder>` is the folder that holds `shared-workflows/`, for example `Publishing/Publish_20261010_02`.

**3. Change CI later**: edit `templates/shared-workflows/` (or `config/ci_contract.yaml`) here, then publish as in step 1. A compatible change needs no workload changes; the script releases it as the next `v1.x.0` and moves `v1`.

A breaking change (renamed or removed input) is released as `v2.0.0` / `v2`; set `shared_workflows.ref: v2` in `config/ci_contract.yaml` and regenerate the workloads.

### Self-hosted GPU runners

Register each GPU host once, at the organization level, with labels that match its vendor and OS (from **garys-gpu-benchmarks → Settings → Actions → Runners → New self-hosted runner**, which also shows the download commands and a registration token):

```bash
./config.sh --url https://github.com/garys-gpu-benchmarks --token <REGISTRATION_TOKEN> \
            --name gpu-amd-2404-01 --labels gpu,amd,ubu2404 --unattended
sudo ./svc.sh install && sudo ./svc.sh start
```

Use `nvidia` instead of `amd` and `ubu2604` instead of `ubu2404` as appropriate. Install the GPU driver and ROCm/CUDA first; the workflow checks them and never installs them. Give the runner user passwordless `sudo` (each workload's first run builds its `.venv` through `setup.sh`), and run one runner agent per GPU host so two benchmarks never share a GPU.

### On a GPU host

Each bundle repository holds one platform's 32 workloads as git submodules, with `run_benchmark_suite.sh` at the top:

```bash
git clone --recurse-submodules https://github.com/garys-gpu-benchmarks/bundle-amd-ubuntu-2404 /opt/benchmarks
cd /opt/benchmarks
./run_benchmark_suite.sh --list                   # all 32 should show "ready"
./run_benchmark_suite.sh -p smoke                 # every workload, smoke profile
./run_benchmark_suite.sh -w 101,107,121 -p baseline
```

The other bundles are `bundle-nvidia-ubuntu-2404`, `bundle-amd-ubuntu-2604` and `bundle-nvidia-ubuntu-2604`. To update a host later: `git -C /opt/benchmarks pull && git -C /opt/benchmarks submodule update --init --recursive`.

### From your laptop

```bash
./get_remote_info.sh --host 203.0.113.10         # ledger + results/raw + results/parsed + suite logs
./get_remote_info.sh --host ubuntu@203.0.113.10 --port 2222 -i ~/.ssh/id_ed25519 -o ~/results
./show_metrics.sh 332 --host 203.0.113.10         # one workload's metrics from the remote ledger
./show_metrics.sh 332 --baseline --file RUNTIME_LEDGERS/runtime_ledger_301_332_<time>.csv
```

The suite scripts are kept in [`templates/suite-tools/scripts/`](templates/suite-tools/scripts) and emitted to `gpu-bench-suite/`.

`show_metrics.sh` prints one row per run in fixed 7-character metric columns, with an Exit column (ledger exit code) after Idx, at most 93 characters wide. Two sheets of `BenchmarkSpecDefinitions.xlsx` supply its text: `Metric_Short_Labels` (one row per workload metric; the column headings, at most 7 characters) and `Workload_Short_Names` (one row per workload; the Name column, at most 12 characters, for example `RAG Sweep` for "RAG Pipeline Sweep"). After changing either, run `python3 scripts/generate_show_metrics.py`; it checks both sheets against `Workload_Definitions` (metric keys from the `Metrics` column, full workload names, no short name used twice in a batch, one short name per full name) and rewrites the two tables in the script. `--check` reports drift without writing (CI runs it), and `--add-missing` adds rows for new metrics and workloads, marked `auto: review`.

Generating a workload (`scripts/create_generated_repo.py`) also regenerates `show_metrics.sh` from the sheet and puts a copy of `get_remote_info.sh` and `show_metrics.sh` in the project folder, one level above the folder that holds the generator and the workloads (for example `Project347_.../get_remote_info.sh` next to `Project347_.../TEMPLATE_00_105/`). Run it from there; it writes `DIRECTORIES/` and `RUNTIME_LEDGERS/` beside itself. An existing copy that differs is kept. It is never copied into a workload, and it does not belong in `scripts/` next to `publish_benchmarks_to_github.sh`: everything in `scripts/` is copied into every workload. When a workload is loaded onto the VM, `scripts/create_one_workload.py` installs `templates/suite-tools/scripts/show_metrics.sh` at `/opt/benchmarks/show_metrics.sh`. A published bundle does the same: `scripts/publish_benchmarks_to_github.sh` copies it next to `run_benchmark_suite.sh`, so `git clone ... /opt/benchmarks` leaves it there.

## Limitations and prerequisites

- An AI Coding Agent capable of following multi-file, multi-phase instructions.
- Python 3.12 or newer for local extraction and validation tooling.
- A populated `BenchmarkSpecDefinitions.xlsx` workload matrix.
- Ubuntu 24.04 (workloads 101–232) or Ubuntu 26.04 (workloads 301–332) for benchmark installation and execution.
- AMD Instinct MI300X hardware and a compatible ROCm installation for GPU workloads.
- A local or cloud-hosted validation machine; cloud providers may charge for compute, storage, networking, and related services.
- The generated repositories are local-runtime repositories. When the prompt contains an IPv4 address, the specified remote VM is mandatory for generation-time loading, installation, self-check, and smoke-test validation.

## Security

Keep private keys, passwords, API tokens, SSH commands containing secrets, and other credentials outside this repository and outside submitted-prompt artifacts. Use placeholders in prompt files and provide credentials only through the secure mechanism supported by the AI Coding Agent or validation environment. Never commit credentials to Git.

## Repository layout

| Path | Purpose |
|---|---|
| `AGENTS.md`, `.claude/CLAUDE.md`, `.github/copilot-instructions.md` | Cross-agent and agent-specific operating rules, in priority order |
| `.github/CODE_OF_CONDUCT.md`, `.github/CONTRIBUTING.md` | Community standards and contribution guidelines |
| `docs/AI_AGENT_INSTRUCTIONS.md` | Detailed generation workflow and agent operating instructions |
| `templates/PRD_TEMPLATE.md`, `templates/SPEC_TEMPLATE.md`, `templates/README_TEMPLATE.md` | Source templates copied to the generated repo root |
| `config/ci_contract.yaml` | CI contract: GitHub owner, `shared-workflows` tag, caller inputs, runner labels, tool versions, bundle names (generation-only) |
| `templates/workload/.github/workflows/` | Thin caller workflows rendered into every generated repo |
| `templates/shared-workflows/` | The reusable workflows, self-test and docs, emitted once to the `shared-workflows` repo |
| `templates/suite-tools/` | `run_benchmark_suite.sh`, `get_remote_info.sh` and `show_metrics.sh`, emitted to the `gpu-bench-suite` repo |
| `docs/` | Phase-by-phase generation workflow and machine-checkable contracts |
| `schemas/` | JSON Schemas that generated artifacts must validate against |
| `scripts/` | Generation, validation, and smoke-check tooling |
| `config/` | The benchmark matrix workbook, machine definitions, hardware profiles |
| `implementation_components/` | Reusable capability-oriented implementation components automatically discovered from the benchmark specification |
| `docs/SUBMISSION_CHECKLIST.md` | Completion gate the agent runs before reporting a generated repo done |

For the full documentation map, see [`ARCHITECTURE.md`](docs/ARCHITECTURE.md). For dated release notes, see [`docs/CHANGELOG.md`](docs/CHANGELOG.md). For template-maintainer notes, see [`TEMPLATE_README.md`](docs/TEMPLATE_README.md).

## Contributing

See [`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md).

## License

The Apache 2.0 license is in root `LICENSE`; project notices are in `legal/NOTICE`.


Apache License 2.0 — see [`LICENSE`](LICENSE).
