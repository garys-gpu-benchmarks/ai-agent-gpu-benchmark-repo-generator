[![Template CI](https://github.com/garys-gpu-benchmarks/ai-agent-gpu-benchmark-repo-generator/actions/workflows/ci.yml/badge.svg)](https://github.com/garys-gpu-benchmarks/ai-agent-gpu-benchmark-repo-generator/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

# AI Coding Agent Spec-Driven GPU Benchmark Repo Generator

A template-driven generation framework that enables AI coding agents to autonomously build, validate, and document GPU benchmark repositories. It converts single-row workload definitions into complete, standardized, execution-ready codebases with zero manual scaffolding required. Included workload domains span GPU compute, LLM serving, memory and data transfer, CPU and system performance, end-to-end pipelines, and validation/correctness testing.

Instead of manually assembling setup scripts, SPEC files, PRDs, CI workflows, and parsing logic for each workload, the agent consumes this template and executes a strict multi‑phase workflow defined in [`AGENTS.md`](AGENTS.md) and [`docs/generation-workflow.md`](docs/generation-workflow.md). The result is a repository that installs the runtime stack, validates the environment, and executes a smoke test, producing reliable, reproducible benchmark repos at scale. This transforms benchmark creation from a manual, error‑prone process into a scalable, automated pipeline.

## High-Level Capabilities

### Repository Generation & Scale

- **Single Excel Row → Full Repository Generation** — Generates an entire benchmark repo from one spreadsheet row plus one AI agent prompt.
- **Optimized for AI Coding Agents** — Designed for Claude Code, Copilot, Cursor, and similar agents to produce consistent output.
- **Starter Benchmark Library** — `BenchmarkSpecDefinitions.xlsx` defines 32 AMD Ubuntu 24.04, 32 NVIDIA Ubuntu 24.04, 32 AMD Ubuntu 26.04, and 32 NVIDIA Ubuntu 26.04 workloads ready to generate. `implementation_components/` supplies reusable implementation assets selected from `config/implementation_packs.yaml` by Workload Number and GPU Vendor; users do not select components in the workbook. Generated repositories are created as siblings of this generator, not as pre-built folders in this tree.
- **Scales to Hundreds of Benchmarks** — A user can add rows to Excel and generate dozens or hundreds of repositories without manual coding.
- **Batch Mode Generation** — Supports lists and ranges (e.g., "101 through 110") to generate multiple repositories from one prompt.
- **Seven Execution Domains** — GPU Compute (CUDA), GPU Compute (ROCm), LLM Serving, Memory/Transfer, CPU/System, End-to-End Pipeline, Validation/Correctness.

### Setup & Execution

- **Quick Start Guide Included** — See [Generate Your First Benchmark Repository](#generate-your-first-benchmark-repository-in-ten-minutes-one-workload) below.
- **Ready-to-Run Local Repositories** — Delivers every file and directory necessary to run the benchmark end-to-end on the target machine.
- **Effortless Setup & Execution** — Install with `bash run_setup.sh --assume-yes`. A bare `bash run_benchmark.sh` is smoke. Pass `--baseline` or `--extended` for the longer profiles, several of them to run each in turn, and `--repeat N` to run the whole set N times.
- **Reboot-Resilient Install** — A single end-to-end install command that saves state and resumes across reboots.
- **Safe, Idempotent Setup Scripts** — Setup scripts can be rerun without corrupting state.
- **Flexible Benchmark Profiles** — Supports smoke, baseline, and extended runs via CLI flags.
- **Supports Local + Remote Development** — Supports integrating a remote Linux VM which can be used for code development and validation.
- **Isolated Python Environments** — Each generated repo uses its own Python venv.

### Repository Structure & AI-Agent Guidance

- **Rich Template Library** — Includes templates for PRD, README, SPEC, scripts, scaffolding, CI workflows, and GitHub files.
- **Detailed Reference Materials** — Generates `README.md`, `SPEC.md`, `docs/PRD.md`, and `docs/GENERATION_REPORT.md` customized per benchmark.
- **Consistent Repository Structure** — Every generated repo has `run_setup.sh`, `run_benchmark.sh`, `show_metrics.sh` and `list_runs.sh` at the top, plus `config/`, `scripts/`, `schemas/`, `docs/`, `tests/fixtures/` (CI creates `benchmark.db` there with `--seed-fixture`; it is not committed), and `results/`.
- **Local Template Copy During Generation** — `create_generated_repo.py` materializes a nested `ai-agent-gpu-benchmark-repo-generator_copy/` while a workload is generated. `create_one_workload.py` removes it once the workload passes (`--keep-template-copy` keeps it); for other paths run `python3 scripts/remove_template_copy.py --repo-root <repo>`. Finished repositories therefore do not carry the copy, whose deep paths exceed the Windows 260-character limit. While it exists, the tree is gitignored and must not be published to GitHub.

### Results & Observability

- **Workload Specification on the CLI** — `bash run_benchmark.sh --specification` prints the workload's definition (name, goal, framework, metrics, runtime language, execution domain); `--help` lists every profile value and parameter override.
- **Timestamped Run Output Directory** — Saves results, commands, metrics, system info, and exit status per run.
- **Environment Logging** — Creates a log of installed software components and versions.
- **Excel-sourced HW/SW Inventory Capture** — Executes a post-run HW/SW inventory collection script generated from Excel command definitions.
- **Runtime Ledger** — Appends one CSV row per run to `/var/opt/benchmarks/runtime_ledger.csv` with workload identity, metrics, parameters, and two times: setup (install checks, model downloads, server start, model load) and benchmark (the timed work only).
- **Results Pages** — Each run refreshes `results/RESULTS_ACTUAL.md` with the latest run of each profile. The committed `RESULTS_REFERENCE.md` comes from the generation smoke run and can be replaced with a passed baseline run by `user_scripts/promote_results_reference.sh` before publishing.
- **SQLite Result Storage** — Stores parsed benchmark results in a portable database, `results/benchmark.db`, with the latest run in `results/summary.json`.
- **Replayable Command Log** — Records all executed benchmark commands for audit and reproducibility.

### Validation & Quality Gates

- **Self-Validation via GitHub Actions** — Lints scripts, runs the test suite, validates schemas, renders and lints the CI templates, and verifies generator structure on every change.
- **One Shared, Versioned CI for Every Generated Repo** — Each workload gets two thin caller workflows (`ci.yml`, `gpu-smoke.yml`) that call one tagged `shared-workflows` repository; both sides are rendered from `config/ci_contract.yaml`. See [Continuous Integration](#continuous-integration).
- **Meets GitHub Community Standards** — LICENSE, CODE_OF_CONDUCT.md, CONTRIBUTING.md, SECURITY.md, issue templates, PR template.
- **Strict Submission Checklist** — Implements `SUBMISSION_CHECKLIST.md` as a completion gate.
- **Agent-Executed Completion Verification** — Requires passing every checklist item before declaring a repo complete.

## Requirements

- An AI coding agent capable of following multi-file, multi-phase written instructions (agent-agnostic rules defined in `AGENTS.md`).
- Git, and on Windows Git Bash (included with [Git for Windows](https://gitforwindows.org/)); the generator runs its commands in bash.
- Python 3.12+ locally, for the extraction/validation scripts. From this directory: `pip install -e "config[dev]"` (or `pip install jsonschema openpyxl PyYAML`).
- `BenchmarkSpecDefinitions.xlsx` populated with your workload matrix (a starter copy is included). Author smoke/baseline/extended values on the `Parameters_SmokeBaselineExtend` sheet; `Workload_Definitions` command columns are generated from that sheet. Close the workbook in Excel before generating; the batch warns when it is open.
- For benchmark installation and execution, a local or cloud-hosted GPU host: Ubuntu 24.04 (workloads 101–132 and 201–232) or Ubuntu 26.04 (301–332 and 401–432), with an AMD Instinct MI300X (AMD workloads; `run_setup.sh` installs ROCm 10.1.0 for gfx942) or an NVIDIA data-center GPU with 80+ GB of memory, H100 or newer (NVIDIA workloads; `run_setup.sh` installs CUDA 13.3 on both Ubuntu releases). Cloud providers may charge for compute, storage, networking, and related services.
- Optional: a Hugging Face token (`HF_TOKEN`) on the GPU host, for models that may be gated, such as `mistralai/Mistral-7B-v0.3` (x27–x32: vLLM, SGLang and RAG). Generation warns when it is missing.

The generated repositories are local-runtime repositories. When the prompt contains an `ssh` command with an IPv4 address, the specified remote VM is mandatory for generation-time loading, installation, self-check, and smoke-test validation.

## Generate Your First Benchmark Repository in Ten Minutes (one workload)

If you are starting from scratch and need a GPU machine, first follow the [`AMD Developer Cloud Getting Started Guide`](docs/amd-developer-cloud-getting-started.md) for an AMD MI300X droplet (workloads 101–132, 301–332), or the [`Runpod Getting Started Guide`](docs/runpod-getting-started.md) for an NVIDIA GPU Pod (workloads 201–232, 401–432).

Steps to generate your first benchmark repository:

1. **Prerequisites**:
   - Git and Python 3.12+; on Windows, Git Bash (included with Git for Windows)
   - An AI coding agent: Cursor, or another one such as Claude Code or GitHub Copilot
   - Optional but recommended: a GPU server with SSH key access as root, matching the workloads' platform: 101–132 AMD MI300X on Ubuntu 24.04, 201–232 NVIDIA H100 or newer on Ubuntu 24.04, 301–332 AMD MI300X on Ubuntu 26.04, 401–432 NVIDIA H100 or newer on Ubuntu 26.04. A freshly installed server works best.

2. **Check that you can log in to the server** (skip without a server):

   ```bash
   ssh -i /path/to/.ssh/<your-key> root@<server-ip>     # Windows example: /c/Users/<you>/.ssh/<your-key>
   ```

   You should get a root prompt without a password, and the login banner should show the workload's Ubuntu version. Add `-p <port>` if SSH is not on port 22 (Runpod usually needs this).

3. **Create a workspace and clone the generator into it**:

   ```bash
   mkdir -p ~/gpu-bench/workspace
   cd ~/gpu-bench/workspace
   git clone https://github.com/garys-gpu-benchmarks/ai-agent-gpu-benchmark-repo-generator.git
   pip install jsonschema openpyxl PyYAML
   ```

   Generated repositories are written in `workspace/`, next to the generator. Use a dedicated folder like this one: generation also copies the operator tools (`get_benchmark_results.sh`, `list_runs.sh`, `show_metrics.sh`) to the folder above it (`~/gpu-bench/`). The workspace itself also receives those three scripts, `run_benchmark_suite.sh` and a `README.md`, the same top-level files as a cloned bundle (TEMPLATE_00_145).

4. **Open the workspace in your AI coding agent**: open `workspace`, the folder that *contains* `ai-agent-gpu-benchmark-repo-generator`, not the generator folder itself. In Cursor, use **File → Open Folder** and Agent mode; on Windows, make Git Bash the default terminal.

5. **Choose workloads and submit a prompt**: Pick workload numbers from `BenchmarkSpecDefinitions.xlsx` and submit this prompt, with your own key path and server IP address. Keep the backquotes around the `ssh` command. Use the IPv4 address, not a host name: generation recognizes the server only by its IPv4 address and, without one, skips remote validation.

   ```text
   @ai-agent-gpu-benchmark-repo-generator/docs/AI_AGENT_INSTRUCTIONS.md
   Generate workload <WORKLOAD_NUMBER>.
   Remotely access Ubuntu VM with `ssh -i /path/to/.ssh/<your-key> root@<server-ip>`
   ```

   Example 1: one workload with remote validation:

   ```text
   @ai-agent-gpu-benchmark-repo-generator/docs/AI_AGENT_INSTRUCTIONS.md
   Generate workload 101.
   Remotely access Ubuntu VM with `ssh -i /path/to/.ssh/<your-key> root@<server-ip>`
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

   Example 4: a whole platform (inclusive range):

   ```text
   @ai-agent-gpu-benchmark-repo-generator/docs/AI_AGENT_INSTRUCTIONS.md
   Generate workloads 101 through 132.
   Remotely access Ubuntu VM with `ssh -i /path/to/.ssh/<your-key> root@<server-ip>`
   ```

   Workload lists may also use `and`, hyphen ranges, `to` ranges, or `ALL`. The agent validates the requested workloads against the workbook before generation.

6. **Let it run**: The agent saves your prompt as `AI_AGENT_PROMPT_SUBMITTED_<WORKLOADS>_<UTC_TIMESTAMP>.md` in `workspace/`, runs `scripts/generation_host_preflight.py`, then starts `scripts/run_from_prompt.py`, which calls `scripts/create_one_workload.py` for each workload in order. Each repository is fully finished before the next one starts. With an SSH command in the prompt, "finished" includes loading the repository onto that server under `/opt/benchmarks/<repo>`, installing it, and passing its self-check and smoke test there. Most workloads take one to ten minutes each; all 32 of a platform typically take 90 minutes or longer. The agent runs on your computer, so keep it awake and online until it finishes. To follow a batch yourself, read `batch_progress.log` in `workspace/` (one line per finished workload, a heartbeat every 5 minutes during a long one, and a final `[DONE]` line); `batch_generation_manifest.json` beside it holds each workload's state and times.

7. **Use the output**: With a server in the prompt, every workload is already installed and smoke-tested in `/opt/benchmarks`, and the suite tools (`run_benchmark_suite.sh`, `list_runs.sh`, `show_metrics.sh`, `get_benchmark_results.sh`) are installed beside them (see [On a GPU host](#on-a-gpu-host)). Otherwise, copy a generated repository (for example `101-sys-bench-amd-rocm-stack-validation-ubu2404/`) to a matching GPU host, or once published, clone its platform bundle there. Inside a repository:

    ```bash
    bash run_benchmark.sh --help
    bash run_benchmark.sh --smoke      # installs on first use, then runs the smoke profile
    bash show_metrics.sh 101           # this workload's runs from the runtime ledger
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

For each selected workload, the agent creates a sibling repository in the workspace (the folder that holds the generator), using the workload number and exact repository name from the validated benchmark definition:

```text
gpu-bench/
├── get_benchmark_results.sh          # operator tools, copied one level above the workspace
├── list_runs.sh
├── show_metrics.sh
└── workspace/
    ├── README.md                            # bundle README for the workloads in this folder
    ├── get_benchmark_results.sh             # suite scripts, same bytes as user_scripts/
    ├── list_runs.sh
    ├── run_benchmark_suite.sh
    ├── show_metrics.sh
    ├── ai-agent-gpu-benchmark-repo-generator/
    ├── AI_AGENT_PROMPT_SUBMITTED_101_20260805_080015.md
    ├── batch_progress.log                   # one line per finished workload; agents wait on it
    ├── batch_generation_manifest.json       # each workload's state and times
    └── 101-sys-bench-amd-rocm-stack-validation-ubu2404/
        ├── benchmark_specification.json
        ├── docs/PRD.md
        ├── docs/GENERATION_REPORT.md
        ├── SPEC.md
        ├── README.md
        ├── RESULTS_REFERENCE.md          # results of the generation smoke run
        ├── run_setup.sh
        ├── run_benchmark.sh
        ├── show_metrics.sh
        ├── list_runs.sh
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
    runner labels, tools)   user_scripts/ + templates/suite-tools/                 ──► gpu-bench-suite repo   (show_metrics.sh, list_runs.sh, get_benchmark_results.sh; run_benchmark_suite.sh goes to the bundles)
```

| Where | File | Runs on | When |
|---|---|---|---|
| each workload | `.github/workflows/ci.yml` → `shared-workflows/.github/workflows/ci.yml@v1` | GitHub-hosted | every pull request and push to `main`: shellcheck, ruff, `bash -n`, `compileall`, `--help`, spec schema, seeded-fixture validation, required files, actionlint |
| each workload | `.github/workflows/gpu-smoke.yml` → `shared-workflows/.github/workflows/gpu-smoke.yml@v1` | self-hosted `[self-hosted, gpu, <vendor>, <os_label>]` | only by hand (**Run workflow**): verify the pre-provisioned stack, record `results/environment.json`, run the chosen profile, upload results. Never on pull requests. |
| `shared-workflows` | `self-test.yml` | GitHub-hosted | every change to `shared-workflows`: actionlint plus `ci.yml` against a sample workload |

`init_generated_repo.py` renders the callers from the contract and refuses to finish if they do not match it. `self_check_generated_repo.sh`, `prepare_github_publish.sh` and `check_github_publish_ready.sh` fail a workload whose callers do not point at `shared-workflows`, lack `permissions`, carry their own `run:` steps, or let the GPU workflow start from a pull request. The full policy, including the `v1`/`v2` versioning rule, is in [`templates/shared-workflows/README.md`](templates/shared-workflows/README.md).

### Publishing

[`user_scripts/publish_benchmarks_to_github.sh`](user_scripts/publish_benchmarks_to_github.sh) publishes everything: `shared-workflows` (tagged `v1.x.0`, `v1` moved), the 128 workloads, the four platform bundles with the suite tools, this generator, and the workbook on the profile repository. It runs from a dated run folder that you fill by hand, is resumable, and never publishes `docs/OPEN_ISSUES.md`. The step-by-step commands, previewing the shared repositories, and how to change CI later (`v1` vs `v2`) are in [`docs/GITHUB_PUBLISH_GENERATOR_OPERATIONS.md`](docs/GITHUB_PUBLISH_GENERATOR_OPERATIONS.md#publishing-everything-with-publish_benchmarks_to_githubsh).

### Self-hosted GPU runners

Register each GPU host once, at the organization level, with labels that match its vendor and OS (from **garys-gpu-benchmarks → Settings → Actions → Runners → New self-hosted runner**, which also shows the download commands and a registration token):

```bash
./config.sh --url https://github.com/garys-gpu-benchmarks --token <REGISTRATION_TOKEN> \
            --name gpu-amd-2404-01 --labels gpu,amd,ubu2404 --unattended
sudo ./svc.sh install && sudo ./svc.sh start
```

Use `nvidia` instead of `amd` and `ubu2604` instead of `ubu2404` as appropriate. Install the GPU driver and ROCm/CUDA first; the workflow checks them and never installs them. Give the runner user passwordless `sudo` (each workload's first run builds its `.venv` through `run_setup.sh`), and run one runner agent per GPU host so two benchmarks never share a GPU.

### On a GPU host

Each bundle repository holds one platform's 32 workloads as git submodules, with `run_benchmark_suite.sh` at the top:

```bash
git clone --recurse-submodules https://github.com/garys-gpu-benchmarks/bundle-amd-ubuntu-2404 /opt/benchmarks
cd /opt/benchmarks
./run_benchmark_suite.sh --list                   # all 32 should show "ready"
./run_benchmark_suite.sh --smoke                  # every workload, smoke profile
./run_benchmark_suite.sh -w 101,107,121 --baseline
./run_benchmark_suite.sh -w 121 --baseline -r 3     # three repeats
```

The other bundles are `bundle-nvidia-ubuntu-2404`, `bundle-amd-ubuntu-2604` and `bundle-nvidia-ubuntu-2604`. To update a host later: `git -C /opt/benchmarks pull && git -C /opt/benchmarks submodule update --init --recursive`.

### From your laptop

```bash
./get_benchmark_results.sh --host 203.0.113.10   # ledger + each workload's results + suite logs
./get_benchmark_results.sh --host ubuntu@203.0.113.10 --port 2222 -i ~/.ssh/id_ed25519 -o ~/results
./list_runs.sh --host 203.0.113.10               # just the run table (workload, profile, benchmark time, exit code); copies nothing
./show_metrics.sh 332 --host 203.0.113.10         # one workload's metrics from the remote ledger
./show_metrics.sh 332 --baseline --file RUNTIME_LEDGERS/runtime_ledger_301_332_<time>.csv
```

### User scripts

Every script you run by hand has its one master copy in [`user_scripts/`](user_scripts):

| Script | Runs on | What it does |
|---|---|---|
| `run_benchmark_suite.sh` | the GPU host | Runs the workloads under `/opt/benchmarks` for the chosen profiles |
| `show_metrics.sh` | laptop (`--host`) or GPU host | One workload's metrics from the runtime ledger, with per-profile means |
| `list_runs.sh` | laptop (`--host`) or GPU host | The run table only (workload, profile, benchmark time, exit code); copies nothing |
| `get_benchmark_results.sh` | laptop (`--host`) or GPU host | Copies the ledger, every workload's results and the suite logs, and prints the run table |
| `promote_results_reference.sh` | your laptop (Git Bash) | Replaces each workload's committed `RESULTS_REFERENCE.md` with a passed run collected by `get_benchmark_results.sh` (for example a baseline suite), before publishing |
| `publish_benchmarks_to_github.sh` | your laptop (Git Bash) | Publishes the workloads, bundles, generator and workbook (run a copy from `Publishing\`) |

The first four are the suite tools: generation installs them at `/opt/benchmarks`, and every bundle carries them. `scripts/emit_shared_workflows.py` emits the three laptop tools (`show_metrics.sh`, `list_runs.sh`, `get_benchmark_results.sh`) to the top of `gpu-bench-suite/` (with `templates/suite-tools/README.md`), and generation copies those three to the project folder; `run_benchmark_suite.sh` runs only on the GPU host, so it is not in `gpu-bench-suite` (TEMPLATE_00_144). Generation also copies all four, plus a bundle `README.md`, into the project root (TEMPLATE_00_145). `user_scripts/` itself is never copied into a workload.

`show_metrics.sh` prints one row per run in fixed 7-character metric columns, with an Exit column (ledger exit code) after Idx, at most 93 characters wide. Two sheets of `BenchmarkSpecDefinitions.xlsx` supply its text: `Metric_Short_Labels` (one row per workload metric; the column headings, at most 7 characters) and `Workload_Short_Names` (one row per workload; the Name column, at most 12 characters, for example `RAG Sweep` for "RAG Pipeline Sweep"). After changing either, run `python3 scripts/generate_show_metrics.py`; it checks both sheets against `Workload_Definitions` (metric keys from the `Metrics` column, full workload names, no short name used twice in a batch, one short name per full name) and rewrites the two tables in the script. `--check` reports drift without writing (CI runs it), and `--add-missing` adds rows for new metrics and workloads, marked `auto: review`.

Generating a workload (`scripts/create_generated_repo.py`) also regenerates `show_metrics.sh` from the sheet and puts a copy of `get_benchmark_results.sh`, `list_runs.sh` and `show_metrics.sh` in the project folder, one level above the folder that holds the generator and the workloads (for example `Project<NNN>_.../get_benchmark_results.sh` next to `Project<NNN>_.../TEMPLATE_00_<XXX>/`). Run it from there; it writes `DIRECTORIES/` and `RUNTIME_LEDGERS/` beside itself. An existing copy that differs is kept. It also writes `README.md` and the four suite scripts (`get_benchmark_results.sh`, `list_runs.sh`, `run_benchmark_suite.sh`, `show_metrics.sh`) into the project root, next to the workloads (TEMPLATE_00_145). Those scripts are the `user_scripts/` masters, byte for byte. The README is the bundle README (`templates/suite-tools/BUNDLE_README_TEMPLATE.md`) filled in for the platform of the workloads in that folder; a folder with more than one platform says so instead of guessing a platform. An existing file that differs is kept. The copies one level above are unchanged. The project-root `run_benchmark_suite.sh` is the master copy: with no profile option it runs smoke. A full run is `--smoke --baseline --extended`. A published bundle's copy is the same script with that bundle's workload numbers in the examples, and the README text describes that bundle copy. Of these, only `show_metrics.sh` and `list_runs.sh` are also copied into each workload, at its top level next to `run_benchmark.sh` (`WORKLOAD_TOOLS`); none of the user scripts belong in `scripts/`, because everything in `scripts/` is copied into every workload. When a workload is loaded onto the VM, `scripts/create_one_workload.py` installs `user_scripts/show_metrics.sh`, `run_benchmark_suite.sh`, `get_benchmark_results.sh` and `list_runs.sh` at `/opt/benchmarks/` (run without `--host` there, `get_benchmark_results.sh` and `list_runs.sh` read that machine). A published bundle does the same: `user_scripts/publish_benchmarks_to_github.sh` copies all four, so `git clone ... /opt/benchmarks` leaves them there.

## Security

Keep private keys, passwords, API tokens, SSH commands containing secrets, and other credentials outside this repository and outside submitted-prompt artifacts. Use placeholders in prompt files and provide credentials only through the secure mechanism supported by the AI Coding Agent or validation environment. Never commit credentials to Git.

## Repository layout

| Path | Purpose |
|---|---|
| `AGENTS.md`, `.claude/CLAUDE.md`, `.github/copilot-instructions.md` | Cross-agent and agent-specific operating rules, in priority order |
| `.github/CODE_OF_CONDUCT.md`, `.github/CONTRIBUTING.md` | Community standards and contribution guidelines |
| `docs/AI_AGENT_INSTRUCTIONS.md` | Detailed generation workflow and agent operating instructions |
| `templates/PRD_TEMPLATE.md`, `templates/SPEC_TEMPLATE.md`, `templates/README_TEMPLATE.md` | Source templates that generation fills in to write each repo's `docs/PRD.md`, `SPEC.md` and `README.md` (the templates themselves stay in the generator) |
| `config/ci_contract.yaml` | CI contract: GitHub owner, `shared-workflows` tag, caller inputs, runner labels, tool versions, bundle names (generation-only) |
| `templates/workload/.github/workflows/` | Thin caller workflows rendered into every generated repo |
| `templates/shared-workflows/` | The reusable workflows, self-test and docs, emitted once to the `shared-workflows` repo |
| `user_scripts/` | The scripts you run by hand: the four suite tools (`run_benchmark_suite.sh`, `show_metrics.sh`, `list_runs.sh`, `get_benchmark_results.sh`; all but `run_benchmark_suite.sh` are emitted to the `gpu-bench-suite` repo), `promote_results_reference.sh` and `publish_benchmarks_to_github.sh` |
| `templates/suite-tools/` | The `gpu-bench-suite` README template (`README.md`) and the bundle README template (`BUNDLE_README_TEMPLATE.md`) |
| `docs/` | Phase-by-phase generation workflow and machine-checkable contracts |
| `schemas/` | JSON Schemas that generated artifacts must validate against |
| `scripts/` | Generation, validation, and smoke-check tooling |
| `BenchmarkSpecDefinitions.xlsx` | The benchmark matrix workbook: the single source of every workload definition |
| `config/` | Workload parameter catalog, implementation packs, framework registry, platform policy, machine definitions, the MI300X hardware profile, and the HW/SW inventory command workbook |
| `implementation_components/` | Reusable capability-oriented implementation components automatically discovered from the benchmark specification |
| `docs/SUBMISSION_CHECKLIST.md` | Completion gate the agent runs before reporting a generated repo done |
| `docs/OPEN_ISSUES.md` | Findings from batch and suite reviews, open and fixed (git-ignored; never published) |

For the full documentation map, see [`ARCHITECTURE.md`](docs/ARCHITECTURE.md). For dated release notes, see [`CHANGELOG.md`](CHANGELOG.md). For template-maintainer notes, see [`TEMPLATE_README.md`](docs/TEMPLATE_README.md).

## Contributing

See [`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md).

## License

Apache License 2.0 — see [`LICENSE`](LICENSE). Project notices are in [`legal/NOTICE`](legal/NOTICE).
