<!--
====================================================================
AGENT INSTRUCTIONS — DELETE THIS BLOCK FROM THE FINAL OUTPUT
====================================================================
You are generating README.md from this template.

INPUTS:
  1. This file (README_TEMPLATE.md)
  2. benchmark_specification.json — an array of {field_name, source_file, value}
`
RULES:
  A. Every token of the form {{Field Name}} below must be replaced with the
     exact `value` from the JSON object whose `field_name` matches it
     verbatim (case-sensitive, including punctuation/parentheses).
     If value is empty string, replace with "—" unless the surrounding
     instruction says to omit the line/row entirely.
  B. Every block of the form [[GENERATE: ...]] is NOT in the JSON. Derive
     its content using the JSON fields referenced in that instruction
     (primarily: Execution Description With Parameters, Parameter_01..16,
     Metrics, Test Procedure (80 words), Raw Output Format, Raw Output Example,
     Framework, Hardware Config). Be
     specific and consistent with those fields — do not invent values
     that contradict them. Numeric baselines or thresholds, schema columns, and
     troubleshooting cases should be inferred from Test Procedure,
     Raw Output Format, Raw Output Example, and Metrics; state assumptions where the
     source material is silent (e.g. "no published threshold provided —
     placeholder value, update before CI use").
  C. Title the document "# {{Workload Name}} Benchmark" unless the
     workload name already includes "Benchmark"; in that case use
     "# {{Workload Name}}" without duplication.
  D. Preserve section numbers/order exactly as listed (1–11). Do not add,
     remove, or reorder top-level sections. The unnumbered sections Quick
     Start, Download as a Bundle and Suite Tools come before section 1.
  E. Repo name in shell commands = the repo slug portion of
     {{Repo Name}} (strip any trailing " [Remote_SSH]" / bracket tags).
  F. Output raw Markdown only — no commentary, no surrounding prose,
     no code fences wrapping the whole document.
====================================================================
-->

# {{Workload Name}} Benchmark

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![CI](https://github.com/{{CI Owner}}/{{CI GitHub Slug}}/actions/workflows/ci.yml/badge.svg)](https://github.com/{{CI Owner}}/{{CI GitHub Slug}}/actions/workflows/ci.yml)

Target: {{OS Version}} · {{GPU Vendor}} · see Hardware Requirements. This is a host benchmark, not a laptop `pip install` project.


## Quick Start

[[GENERATE: A 4–6 line bash quick-start block — clone the repo using `git clone https://github.com/<org>/{{Workload Number}}-{{Repo Name}}.git` (publication prep replaces `<org>` via `--github-owner`; the GitHub slug keeps the leading workload number). Run `bash setup.sh --assume-yes`, then `bash run_benchmark.sh --profile smoke --validate`. State that this command runs the configured smoke test. Include `bash scripts/build.sh` only when Installation and Execution Summary / Execution Summary (Run) explicitly requires a compile/build step; otherwise omit build.sh entirely from Quick Start. For LLM Serving workloads, state that a bare `bash run_benchmark.sh` is smoke (tiny local server) and that `--baseline` / `--extended` start the real model server, wait for readiness, run the client, and stop the server. Follow with one sentence stating where results are written (results/benchmark.db and results/summary.json).]]

[[GENERATE: Add one sentence that this workload is local-only and does not support remote SSH execution in `setup.sh` or `run_benchmark.sh`.]]

[[GENERATE: A short Prerequisites paragraph plus bullets: OS Version, GPU vendor/model/HBM from Hardware Config, ROCm or CUDA version from Framework, Python version, that `setup.sh` needs root or sudo, and Hugging Face / `HF_TOKEN` / model-license notes when Framework names vLLM, SGLang, Diffusers, BERT, or RAG. State that this is a host benchmark, not a laptop `pip install` project. Then a mermaid flowchart: setup.sh --> scripts/build.sh (only if a compile step exists) --> run_benchmark.sh --> parse_results.py --> results/benchmark.db.]]


## Download as a Bundle

This repository is one of the 32 workloads in the {{GPU Vendor}} {{CI OS Display}} bundle, [`{{CI Bundle Repo}}`](https://github.com/{{CI Owner}}/{{CI Bundle Repo}}), which holds them as git submodules pinned to a release. To put every workload for this platform on a GPU host in one step, run this as root (or put `sudo` in front of the `apt-get` and `git clone` commands):

```bash
apt-get update && apt-get install -y git
git clone --recurse-submodules https://github.com/{{CI Owner}}/{{CI Bundle Repo}} {{CI Install Root}} \
  && cd {{CI Install Root}} \
  && ./run_benchmark_suite.sh --list \
  && cd {{CI Install Root}}/{{CI GitHub Slug}} \
  && bash run_benchmark.sh --profile smoke --validate \
  && cd {{CI Install Root}} \
  && echo "Done: 32 workloads in {{CI Install Root}}; {{CI GitHub Slug}} smoke run passed. Next: ./run_benchmark_suite.sh --help"
```

Every line in `./run_benchmark_suite.sh --list` should show `ready`; it exits with an error if any workload is not fetched. The commands are joined with `&&`, so if the clone, the list or the smoke run fails, the chain stops there, and the closing message appears only when everything succeeded. The chain ends in `{{CI Install Root}}`, where the suite runner is. For more extensive testing:

```bash
./run_benchmark_suite.sh --smoke                  # smoke test of all 32 workloads
./run_benchmark_suite.sh -w {{CI Bundle Example Workload}} --baseline        # workload {{CI Bundle Example Workload}}, baseline profile
./run_benchmark_suite.sh --help                   # all options
```

A workload that is not set up yet sets itself up on its first run (its `run_benchmark.sh` calls `scripts/ensure_setup.sh`). See [Suite Tools](#suite-tools) for more.

To move to the newest published release later: `cd {{CI Install Root}} && git pull && git submodule update --init --recursive`.

| Bundle repository | Platform | Workloads |
|---|---|---|
| [`bundle-amd-ubuntu-2404`](https://github.com/{{CI Owner}}/bundle-amd-ubuntu-2404) | AMD · Ubuntu 24.04 | 101–132 |
| [`bundle-nvidia-ubuntu-2404`](https://github.com/{{CI Owner}}/bundle-nvidia-ubuntu-2404) | NVIDIA · Ubuntu 24.04 | 201–232 |
| [`bundle-amd-ubuntu-2604`](https://github.com/{{CI Owner}}/bundle-amd-ubuntu-2604) | AMD · Ubuntu 26.04 | 301–332 |
| [`bundle-nvidia-ubuntu-2604`](https://github.com/{{CI Owner}}/bundle-nvidia-ubuntu-2604) | NVIDIA · Ubuntu 26.04 | 401–432 |

## Suite Tools

Three operator scripts from [`{{CI Owner}}/{{CI Suite Tools Repo}}`](https://github.com/{{CI Owner}}/{{CI Suite Tools Repo}}) work across the whole bundle. `run_benchmark_suite.sh` and `show_metrics.sh` are also at the top of every bundle (and the generator's remote copy installs `show_metrics.sh` at `{{CI Install Root}}`); each script prints full usage with `--help`.

- **`run_benchmark_suite.sh`** (on the GPU host) — runs the installed workloads one after another for each profile, writes one log to `{{CI Install Root}}/benchmark_suite_log/`, and ends with a pass/fail summary.
  ```bash
  cd {{CI Install Root}}
  ./run_benchmark_suite.sh --dry-run                    # list what would run
  ./run_benchmark_suite.sh -w {{Workload Number}} --smoke --baseline  # just this workload
  ./run_benchmark_suite.sh --smoke                      # every workload, smoke profile
  ./run_benchmark_suite.sh -r 20                        # soak: everything, 20 times
  ```
- **`get_remote_info.sh`** (on your laptop; Git Bash on Windows) — over one SSH connection, copies the runtime ledger and every workload's `results/raw`, `results/parsed` and suite logs into `RUNTIME_LEDGERS/` and `DIRECTORIES/`.
  ```bash
  git clone https://github.com/{{CI Owner}}/{{CI Suite Tools Repo}} && cd {{CI Suite Tools Repo}}
  ./scripts/get_remote_info.sh --host 203.0.113.10              # root@host, port 22
  ./scripts/get_remote_info.sh --host ubuntu@203.0.113.10 --port 2222 -i ~/.ssh/id_ed25519 -o ~/results
  ```
- **`show_metrics.sh`** (laptop or GPU host) — prints one workload's runs from the runtime ledger in fixed-width metric columns with per-profile means. On the GPU host it is `{{CI Install Root}}/show_metrics.sh`.
  ```bash
  cd {{CI Install Root}} && ./show_metrics.sh {{Workload Number}}             # on the GPU host
  ./scripts/show_metrics.sh {{Workload Number}} --host 203.0.113.10            # over SSH, all profiles
  ./scripts/show_metrics.sh {{Workload Number}} --baseline --file RUNTIME_LEDGERS/<ledger>.csv
  ```


## 1. Overview

[[GENERATE: 3–5 sentences using Execution Summary (Run and Measure), Execution Summary (Run), and Execution Description With Parameters verbatim/near-verbatim as the source. Do not copy another workload's Overview. If Execution Description names the PyTorch tensor-op suite, do not write RVS SDC / ECC / rvs_sdc.yaml text. If Execution Description names Stable Diffusion XL / SDXL, describe Diffusers `StableDiffusionXLPipeline` loading `stabilityai/stable-diffusion-xl-base-1.0`; do not write TinyDenoiser, tiny UNet, or RVS SDC text, and say smoke is a local tiny denoiser while baseline/extended load the real weights. State what is run, with what tool/function, and what is measured. Include the sweep/shape values and dtype list if present in Test Procedure (80 words). Name the target hardware from Hardware Config.]]


## 2. What It Validates

[[GENERATE: A bullet list, one bullet per item in Metrics, each bullet phrased as a pass condition (direction + threshold if a threshold is derivable from Test Procedure (80 words) or Raw Output Format or Raw Output Example; otherwise phrase qualitatively, e.g. "Kernel execution time is positive and physically sensible for every shape"). Must also reflect Validation Objective (≤10 words).]]


## 3. Metrics Captured

[[GENERATE: A numbered list, one entry per item in Metrics, in the same order. For each: **Metric name** — one-line description — name of the column(s) it maps to in the `samples` / `runs` tables (see Section 8; infer column names from Raw Output Format / Raw Output Example / Metrics using snake_case).]]


## 4. Hardware Requirements

### Supported environment

[[GENERATE: A short paragraph plus bullets for the portable requirements only: {{OS Version}}, a compatible {{GPU Vendor}} GPU, the ROCm or CUDA family from {{Framework}} (major.minor, not the exact lab droplet), and {{Python Version}}. State that other GPUs in the same vendor/stack may work but have not been validated against the reference baseline.]]

### Reference validation environment

The tables below describe the machine used to generate the reference results. They are not a requirement that every user buy that exact cloud instance.

### System

[[GENERATE: A two-column Markdown table (Component | Specification) parsed out of {{Hardware Config}} — split into Provider, Droplet/instance type, vCPUs, RAM, Storage, Network (if stated).]]

### GPU

[[GENERATE: A two-column Markdown table (Component | Specification) parsed out of {{Hardware Config}} — split into GPU Count, GPU Model, Architecture, Compute Units, HBM, GFX Target, Peak Power, and published peak TFLOPS/bandwidth figures for that GPU model if commonly known; otherwise omit that row rather than guess.]]


## 5. Software Requirements

| Component | Version |
|---|---|
| OS | {{OS Version}} |
| Kernel | {{Kernel Version}} |
| Python | {{Python Version}} |
| ROCm | {{ROCm Version}} |
| rocBLAS | {{rocBLAS Version}} |

[[GENERATE: Add one additional row per library or tool named in {{Framework}} that is not already covered by the five rows above (e.g. PyTorch, MIOpen, CMake, HIPCC). Use the version string from {{Framework}} where one is stated; otherwise write "see Installation and Execution Summary" in the Version column. Do not add rows for libraries already represented above.]]


## 6. Installation

[[GENERATE: A bash code block of installation commands consistent with {{Installation and Execution Summary}} and the build steps implied by Test Procedure (80 words) (e.g. git checkout of a specific tag, ./install.sh flags, target GFX arch). Follow with a "> **Note:**" callout describing any environment variables the build script honors (e.g. paths to the ROCm install or a pre-built binary), only if such detail is present or directly implied in the source fields. The generated note must also state:
- `setup.sh` installs Python venv prerequisites idempotently on fresh Ubuntu images before creating an isolated per-repository environment at the repository-local `.venv` path; a repository-local `.venv` is prohibited, and
- `BENCHMARK_PYTHON` may select the interpreter used to create that environment (for example `/usr/bin/python3.13`); each repository may use a different interpreter and venv path, and the matching `pythonX.Y-venv` package must be installed,
- for workload-inherent ROCm tasks, default `bash setup.sh` executes ROCm install steps 1-23 from `scripts/lib/rocm_install.sh` (runtime 1-12, repo 13-17, RVS 18-23) with explicit skip flags as advanced overrides, and
- on first local invocation, `setup.sh` prompts for confirmation that one reboot may occur and that setup auto-resumes after that reboot (Enter to continue), and
- `setup.sh` writes a chronological install status file at `results/install_status.txt`, writes bare executed install commands to `results/install_commands.txt`, and keeps a mirrored install-status block in `/etc/motd` during reboot-driven install, and
- during reboot-driven install, `setup.sh` updates `/etc/motd` with in-progress phase/resume status and writes a persistent completion status block when installation is finished, and
- `/etc/motd` should include operator guidance lines: `To see latest status on install, execute the following:` followed by `cat <repo-root>/results/install_status.txt`, and
- on successful local completion, `setup.sh` prints `setup.sh now complete` to its own output only (no `wall` broadcast, no terminal bell), and
- for ROCm workloads using PyTorch, setup installs PyTorch/torchvision from the official ROCm wheel index rather than default PyPI, with configurable index and version variables, and verifies HIP plus GPU availability before writing the completion marker, and
- for ROCm LLM Serving workloads, setup installs AMD AITER from its official repository with recursive submodules and compiles SGLang `sgl-kernel` for the target GFX architecture; generic CUDA `sgl_kernel` wheels are rejected.]]


## 7. Running the Benchmark

[[GENERATE: A bash code block showing (a) `bash run_benchmark.sh --help`, (b) the configured smoke invocation `bash run_benchmark.sh --profile smoke --validate` for non-LLM workloads, (c) a customized invocation using flags derived 1:1 from Parameter_01 .. Parameter_16 (skip empty parameter slots) and values from Profile Parameter Values; sweep/list flags are documentary, (d) an environment-variable override example if applicable. State that `run_benchmark.sh --help` prints the `usage()` page and exits without running setup. State that `run_benchmark.sh` automatically invokes `scripts/ensure_setup.sh` when `.setup_state` is absent, and that the operator reruns the command after a reboot-driven setup resumes. Include profile examples for `--smoke`, `--baseline`, and `--extended`. For LLM Serving workloads, state that a bare `bash run_benchmark.sh` is smoke (tiny local server) and that `--baseline` / `--extended` start the real model server, wait for readiness, run the client, and stop the server. `--baseline` targets approximately three to five minutes. Follow with a CLI Options table: Option | Default | Description — one row per non-empty Parameter_xx, plus standard rows for --config, --profile, --smoke (Run smoke profile), --baseline (Run baseline profile), --extended (Run extended profile), --validate, --no-validate, --quiet, --log-level, --save-options-file (PATH), --phase (phaseN or N), --phase1, --phase2, --phase3 (parse only; requires --raw-file), --phase4, --raw-file (existing raw file for phase3), --matrix-definition (print this workload's matrix row), --help. Defaults: take numeric/sweep defaults from Test Procedure (80 words) where stated; otherwise mark "TBD". Then add one sentence stating that a benchmark statistics summary block is printed at the end of a successful run (unless --quiet is used), and that summary includes extended statistics (min, max, mean, median, stddev, p95) where applicable.]]

**Validating results separately:**

```bash
export BENCHMARK_PYTHON=/usr/bin/python3.13  # optional
python3 -m venv .venv
source ".venv/bin/activate"
".venv/bin/python" scripts/validate_results.py
```


## 8. Output

### `results/benchmark.db` (SQLite)

[[GENERATE: Two schema tables in Markdown:
1. **`runs`** — one row per run_benchmark.sh execution. Standard columns: run_id, benchmark_id ("{{Workload Number}}"), status (ok/error/timeout/partial), started_at, finished_at, plus one "peak_<metric>" column per metric in Metrics that is a throughput/rate-type metric, plus total/passed sweep-point counters.
2. **`samples`** — one row per parameter combination swept. Standard columns: run_id (FK), sample_index, status, one column per Parameter_xx actually populated, and one column per metric in Metrics using snake_case names consistent with Raw Output Format or Raw Output Example if those fields define them. Use the column-name/unit hints in Raw Output Format and Raw Output Example where present.]]

[[GENERATE: Add a short "Per-run artifact directory" subsection describing that each execution writes to `results/raw/YYYYMMDD_HHMMSS_<repo_name>_<hostname>/` and includes at minimum: `run.log`, `commands_executed.sh`, `env_variables.txt`, `journal_warnings.txt` (`journalctl -p warning`, run-window scoped), `script.sh`, raw benchmark dual-format exports (`raw_results.csv`, `raw_results.jsonl`), per-run sample exports in CSV and JSON, raw tool output text, and the Excel-sourced inventory files `hardware_info.txt`, `software_info.txt`, and `errors_info.txt` written into that same per-run directory by `scripts/collect_hw_sw_info.sh` from `config/hw_sw_info_commands.xlsx`. Do not write `system_info.txt`. `errors_info.txt` records unavailable probes without replacing the benchmark result status. Document the one-row-per-invocation `/var/opt/benchmarks/runtime_ledger.csv` with the required column order from `scripts/update_runtime_ledger.py` (`total_runtime_mm_ss` as `mm:ss`, plus hardware/software, metric, `run_benchmark_command_submitted`, `run_benchmark_command_fully_resolved`, `Parameter_01_Name`/`Parameter_01_Value` through `Parameter_20_Name`/`Parameter_20_Value`, `parameters_set`, and notes fields).]]

### `results/summary.json`

Consolidated metrics from the most recent run — suitable for CI artifact upload or dashboard ingestion.

### `results/raw/<timestamp>.txt`

[[GENERATE: One sentence describing what raw artifact is captured per run, consistent with Raw Output Format and Raw Output Example (e.g. raw stdout/CSV from the benchmark binary).]]


## 9. Baselines / Thresholds

[[GENERATE: If this is a measurement-only benchmark, state that expected ranges live in config/benchmark_config.yaml under `baselines:` and include a table (Metric | Expected Range | Basis). If this workload defines correctness, compliance, health, or explicit pass/fail gates, state that thresholds live in config/benchmark_config.yaml under `thresholds:` and include a table (Threshold Key | Value | Direction | Basis) with one row per gated metric. Use any thresholds explicitly stated in Test Procedure (80 words) (e.g. "exceed published peak thresholds", "error norm exceeding 1e-3"). Where Test Procedure references an external/published baseline rather than a literal number, write "see hardware peak spec — % floor TBD" in the Value column rather than inventing a number. End with: "To update baselines or thresholds, edit `config/benchmark_config.yaml` — never edit validation code directly."]]


## 10. Troubleshooting

[[GENERATE: At least three failure-mode entries, each formatted as: **`<error or symptom>`**
- **Cause:** ...
- **Fix:** ... (include a fenced bash block where a command fixes it)

Derive failure modes from: the build/install step (Section 6), a hardware/resource constraint implied by Hardware config or the largest sweep value in Test Procedure (80 words), and a data-quality failure tied to one of the metrics in Metrics (e.g. a NaN/null or out-of-range value). Add a fourth entry only if Installation and Execution Summary implies a non-trivial dependency (e.g. a Python venv) not already covered.]]


## 11. NVIDIA H100 Coding Differences

{{nVidia Porting Instructions (Reference Only)}}

## Repository layout

```text
.
├── setup.sh
├── run_benchmark.sh
├── benchmark_specification.json
├── .github/workflows/      # thin CI callers (see Continuous Integration)
├── config/
├── scripts/
├── src/
├── tests/
├── docs/
├── results/
└── LICENSE
```

## Continuous Integration

| Workflow | Runs on | When | What it does |
|---|---|---|---|
| [CI](.github/workflows/ci.yml) | GitHub-hosted runner | every pull request, and every push to `main` | shellcheck, ruff, `bash -n`, `compileall`, `run_benchmark.sh --help`, specification schema, the results validator on a seeded fixture, required files, and actionlint. No GPU and no benchmark run. |
| [GPU Smoke Benchmark](.github/workflows/gpu-smoke.yml) | self-hosted runner labeled `gpu`, `{{CI Vendor}}`, `{{CI OS Label}}` | only when started by hand: **Actions → GPU Smoke Benchmark → Run workflow** (choose `smoke`, `baseline` or `extended`) | Verifies the pre-provisioned GPU stack, records `results/environment.json` (driver, runtime, kernel, GPU), runs the profile with `--validate`, shows headline metrics on the run page, and uploads the results. |

Both files are short callers. The steps themselves live once, for every workload in the suite, in [`{{CI Owner}}/{{CI Shared Workflows Repo}}`](https://github.com/{{CI Owner}}/{{CI Shared Workflows Repo}}), pinned at `@{{CI Shared Workflows Ref}}`. The GPU workflow is never triggered by pull requests, so code from a fork cannot run on the GPU host.

The GPU Smoke Benchmark workflow runs one workload. To install and run the whole {{GPU Vendor}} {{CI OS Display}} bundle by hand on the same machines, see [Download as a Bundle](#download-as-a-bundle) and [Suite Tools](#suite-tools).
