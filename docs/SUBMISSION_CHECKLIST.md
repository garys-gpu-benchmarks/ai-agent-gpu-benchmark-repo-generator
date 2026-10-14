# SUBMISSION_CHECKLIST.md
# Agent completion checklist for `gpu-bench-*` / `sys-bench-*` benchmark repositories.
# Run this checklist in order before reporting implementation complete.
# Each item is a discrete pass/fail. Do not advance past a failed item without resolving it.

# Scope note:
# In template mode, run this checklist from the generated repository subdirectory
# named `<Workload Number>-<Repo Name>` from `benchmark_specification.json` at project root
# (for example: `<project-root>/101_sys-bench-rocm-stack-validation/`, not
# `<project-root>/<template-directory>/<repo-name>/`). All relative paths below are scoped to that
# generated repository root.

---

## Phase 1 — Source document verification
*Complete before writing a single line of code or generated document.*

- [ ] 1.1  `benchmark_specification.json` has been read and internalized as the single source of truth.
- [ ] 1.2  the directly submitted generation prompt and `docs/AI_AGENT_INSTRUCTIONS.md` have been read in full.
- [ ] 1.3  `AGENTS.md` has been read in full, including the SQLite schema, raw output parsing rules, execution-loop validation contract, and CI workflow contract sections.
- [ ] 1.4  `.claude/CLAUDE.md` has been read in full (document priority order, operating model, prohibited modifications). There is no root `CLAUDE.md`.
- [ ] 1.5  `templates/PRD_TEMPLATE.md`, `templates/SPEC_TEMPLATE.md`, and `templates/README_TEMPLATE.md` have been read, including each template's embedded `AGENT INSTRUCTIONS` block.
- [ ] 1.6  `docs/repository-template.md` has been read to establish the canonical directory layout.
- [ ] 1.7  `docs/generation-workflow.md` and `docs/machine-checkable-contracts.md` have been read.
- [ ] 1.8  `docs/run-output-contract.md`, `docs/raw-output-parser-contract.md`, and `docs/rocm-reboot-install-contract.md` have been read.
- [ ] 1.8a `docs/rocm-pytorch-install-contract.md` has been read for ROCm framework wheel selection and GPU-backed verification when applicable.
- [ ] 1.9  `config/hardware_profile.{gpu}.yaml` has been read and peak values noted for threshold or baseline derivation.
- [ ] 1.10 The `Execution Domain` field in `benchmark_specification.json` has been identified and the corresponding installation pattern, metric families, and validation behavior confirmed.
- [ ] 1.10a The complete `Framework` field, translated from the workbook's `Software Framework` column, has been enumerated. Every listed application, tool, utility, program, library, language runtime, and framework is installed and independently verified; no entry is omitted or satisfied only by a transitive dependency.
- [ ] 1.11 `benchmark_specification.json` passes: `python3 scripts/validate_template_inputs.py --benchmark-specification benchmark_specification.json --benchmark-schema schemas/benchmark_specification.schema.json`.
- [ ] 1.12 Confirm the generated repository is local-only: no SSH remote execution path is documented or implemented.
- [ ] 1.12a If the prompt supplies a remote VM login command containing an IPv4 address, copy the local created repository onto that VM, install it there, run its self-check, and run its smoke benchmark there before completion. Develop the code in the local directory, and copy it to the remote VM for testing. Do not copy anything from the VM back to the local directory. The authoritative repository remains the local sibling of `ai-agent-gpu-benchmark-repo-generator`. Do not treat `/root` or any VM home as project root.
- [ ] 1.12b If that command contains an IPv4 address, use the supplied VM without a destructive rebuild unless the user explicitly confirmed `scripts/refresh_remote_vm.sh`. A confirmed refresh of a 101–232 host uses `ubuntu-24-04-x64`; do not rebuild a 301–332 host to 24.04. Confirm the refresh helper was excluded from generated repository runtime files.
- [ ] 1.12c After a confirmed refresh, reconnect the external validation VM by attempting the supplied SSH command, running `ssh-keygen -R <REMOTE_IPV4>` to remove the stale host key, reconnecting, and answering `yes` to accept the new ED25519 key. Confirm the login banner matches the workload `OS Version` (`Ubuntu 24.04` or `Ubuntu 26.04`) before installation or smoke testing.

---

## Phase 2 — Generated document verification
*Complete before deriving the SQLite schema or writing any implementation code.*

### PRD.md
- [ ] 2.1  `PRD.md` has been written to disk.
- [ ] 2.2  Zero unresolved `{{...}}` tokens remain.
- [ ] 2.3  Zero unresolved `[[GENERATE...]]` blocks remain.
- [ ] 2.4  The `AGENT INSTRUCTIONS` HTML comment block has been stripped from the output.
- [ ] 2.5  Every substituted `{{Field Name}}` value matches the verbatim field value in `benchmark_specification.json` — spot-check at least three fields.

### SPEC.md
- [ ] 2.6  `SPEC.md` has been written to disk.
- [ ] 2.7  Zero unresolved `{{...}}` tokens remain.
- [ ] 2.8  Zero unresolved `[[GENERATE...]]` blocks remain.
- [ ] 2.9  The `AGENT INSTRUCTIONS` HTML comment block has been stripped from the output.
- [ ] 2.10 Parameters listed in `SPEC.md` exactly match the non-empty `Parameter_01`–`Parameter_20` fields in `benchmark_specification.json` — no extras, no omissions.
- [ ] 2.11 Metrics listed in `SPEC.md` exactly match the `Metrics` field in `benchmark_specification.json`.
- [ ] 2.12 The SQLite column names derived in `SPEC.md` will be reused verbatim in all DB code — confirm no independent re-derivation will occur in Phase 3.

### README.md
- [ ] 2.13 `README.md` has been written to disk.
- [ ] 2.14 Zero unresolved `{{...}}` tokens remain.
- [ ] 2.15 Zero unresolved `[[GENERATE...]]` blocks remain.
- [ ] 2.16 The `AGENT INSTRUCTIONS` HTML comment block has been stripped from the output.
- [ ] 2.17 Every substituted `{{Field Name}}` value matches the verbatim field value in `benchmark_specification.json` — spot-check at least three fields.
- [ ] 2.18 Quick Start/Installation command blocks include `bash scripts/build.sh` only when the workload explicitly requires a compile/build step.

---

## Phase 3 — Implementation verification
*Complete before running any tests or reporting done.*

### Repository structure
- [ ] 3.1  List the repository tree and confirm every path in `docs/repository-template.md` is present.
- [ ] 3.2  `run_benchmark.sh` exists at the repo root.
- [ ] 3.3  `benchmark_specification.json` exists and has not been modified.
- [ ] 3.4  `config/benchmark_config.yaml` exists with `sweep:` populated from `Profile Parameter Values` (workbook `Parameters_SmokeBaselineExtend` sheet). Do not invent smoke/baseline/extended numbers. Confirm the validation configuration pattern matches `benchmark_specification.json` → `Workload Type`:
- `Test` workloads must have a `thresholds:` block with `_min`/`_max`-suffixed keys.
- `Benchmark` workloads should have a `baselines:` block for expected ranges; a `thresholds:` block is allowed only if an explicit pass/fail gate is documented in `benchmark_specification.json`.
- Omitting both blocks is only acceptable if `benchmark_specification.json` provides no numeric reference values and the workload type is `Benchmark`.
- [ ] 3.5  `scripts/lib/common.sh` exists.
- [ ] 3.6  `schemas/benchmark_specification.schema.json` and `schemas/generation_report.schema.json` exist.
- [ ] 3.7  `scripts/validate_template_inputs.py` exists and is executable.
- [ ] 3.8  `scripts/parse_results.py` exists.
- [ ] 3.9  `setup.sh` exists (and `scripts/build.sh` if a build step is required).
- [ ] 3.9d If `scripts/build.sh` or `Makefile` invokes `hipcc`, it sources `scripts/lib/hipcc_host_gcc.sh` or passes `--gcc-install-dir` (Ubuntu 26.04 Clang 23 otherwise misses `<cstdlib>`). `scripts/lib/hipcc_host_gcc.sh` exists. For 120/320, `src/rochpl.cpp` uses 64-bit host matrix length (not `host_a(n * n)`).
- [ ] 3.9c `setup.sh` satisfies `docs/host-prerequisite-contract.md`, creates or reuses `.venv`, uses standardized setup markers, and installs only workload-required prerequisites.
- [ ] 3.9a `setup.sh` is local-only and rejects remote setup options with a clear error.
- [ ] 3.9b For reboot-driven setup flows, `setup.sh` maintains `results/install_status.txt` and mirrors install status into `/etc/motd`.
- [ ] 3.9c `setup.sh` appends each executed install command to
           `results/install_commands.txt` as a bare command line (no timestamp,
           step number, or trailing comment). Preserve the file across reboot
           resume the same way as `results/install_status.txt`.
- [ ] 3.10 `scripts/validate_results.py` exists and accepts `--db`, `--config`, `--seed-fixture`, and `--quiet` flags.
- [ ] 3.10a `scripts/self_check_generated_repo.sh` exists and passes when run from generated repo root.
- [ ] 3.11 `results/generation_manifest.json` exists and passes: `python3 scripts/validate_template_inputs.py --generation-manifest results/generation_manifest.json --generation-schema schemas/generation_report.schema.json`.
- [ ] 3.11a `GENERATION_REPORT.md` contains `generation_started_at`, `generation_finished_at`, and `generation_duration_seconds` matching the final values in `results/generation_manifest.json`.
- [ ] 3.11b For a multi-workload prompt, the project root contains `batch_generation_manifest.json`; it lists every requested workload, records each repository result as `passed`, `failed`, `abandoned`, or `timed_out`, records one remote refresh status, records `create_start_time`, `create_end_time`, and the human-readable `create_total_time` for each repository, and passes the batch manifest schema validation.
- [ ] 3.11c Multi-workload generation was strictly sequential: only `create_generated_repo.py --workload <N>` was used per workload; no later workload directory was created until the current workload finished, failed with user notification, was abandoned, or timed out after 60 minutes of calendar time; `create_generated_batch.py` was not used on the AI Coding Agent chatbox path; status questions were answered without stopping the current unfinished workload; after a workload was recorded the next remaining requested workload started in the same turn.
- [ ] 3.11d After every requested workload directory was recorded, generation-time scratch was removed from the local project root and from the remote validation host home (`*_create_start_time.txt`, `workload_identities.txt`, `rocm_pip_constraints.txt`, `_fill_generated_docs.py`, `patch_generated_repo.py`, `finish_one_workload.sh`, `process_range.sh`, `_generation_helpers/`, `batch_process*.log`, `batch_process*.stdout`, `retry*.stdout`, root `*_setup.log`). The local project root still has the template directory, each `<Workload Number>-<Repo Name>/` directory, `AI_AGENT_PROMPT_SUBMITTED_*.md`, and `batch_generation_manifest.json`. The VM home no longer has leftover helpers or a duplicate batch manifest once the local copy is authoritative. Generated repositories and `/var/opt/benchmarks/runtime_ledger.csv` were not deleted.
- [ ] 3.11e The AI Coding Agent (ie, Cursor) project-root sibling is the created repository only. Every requested `<Workload Number>-<Repo Name>` exists as a sibling of `ai-agent-gpu-benchmark-repo-generator` and contains `setup.sh`, `run_benchmark.sh`, and `config/benchmark_config.yaml`. Remote smoke without that sibling is a fail. A results-only stub (for example under `DIRECTORIES/`) is a fail. `--project-root /root` was not used to relocate output. Nothing was copied from the VM back into that sibling.
- [ ] 3.11e1 After each remote copy, `/opt/benchmarks/<Workload Number>-<Repo Name>` and its subdirectories are `0755` (`drwxr-xr-x`), not world-writable `0777` (`drwxrwxrwx` / lime-green in `ls`). `stat -c '%a' /opt/benchmarks/<Workload Number>-<Repo Name>` prints `755`. `scripts/create_one_workload.py` applies `find … -type d -exec chmod 755 {} +` after extract; a manual copy must do the same before `setup.sh`.
- [ ] 3.11f The local sibling has no validation-host runtime state: `test ! -d .venv`, `test ! -d .cache`, and no `.venvs/`, `venv/`, `.setup_state`, `.setup.lock`, `.rocm_runtime_stage.env`, `results/raw/` run trees, `build/` products, fio `data/`, cloned `third_party/` builds that the overlay did not ship, `*.deb`, `*.safetensors`, or `__pycache__/`. Those paths may exist on the validation VM only. Do not copy them to the local created repository.
- [ ] 3.12 `tests/fixtures/` directory exists with `.gitkeep` sentinel. No binary `benchmark.db` is committed — the fixture is generated on-the-fly by `--seed-fixture`.
- [ ] 3.13 There is no `tests/fixtures/create_fixture_db.py` — `scripts/validate_results.py --seed-fixture` is the replacement.
- [ ] 3.14 `results/raw/.gitkeep` and `results/parsed/.gitkeep` exist.
- [ ] 3.15 `.github/workflows/ci.yml` and `.github/workflows/gpu-smoke.yml` exist, are the only workflow files, and were rendered by `init_generated_repo.py` (no `nightly.yml`, no `.github/dependabot.yml`).
- [ ] 3.16 `.gitignore` excludes `results/`, `.venv/`, `build/`, `tests/fixtures/benchmark.db`, secrets, and credentials.

### Script quality
- [ ] 3.17 Every `.sh` and `.py` file opens with the required header block (`File`, `Version`, `Author`, `Date`, `Description`, `Execution`, `Options`, `Requirements`, `Environment`, `Dependencies`, `Variables`, `Repository`, `License`).
- [ ] 3.18 `run_benchmark.sh` begins with `set -euo pipefail`.
- [ ] 3.19 Every other Bash script begins with `set -euo pipefail`.
- [ ] 3.20 No `TODO` comments remain anywhere. Grep: `grep -r "TODO" . --include="*.sh" --include="*.py"`.
- [ ] 3.21 No `pass` statements remain. Grep: `rg -n "^\s*pass$" . --glob "*.py"`.
- [ ] 3.22 No `raise NotImplementedError` remains. Grep: `rg -n "NotImplementedError" . --glob "*.py"`.
- [ ] 3.23 No HTML comment placeholders remain in generated artifacts.
           Grep: `rg -n "<!--" . --glob "*.md" --glob "!AGENTS.md" --glob "!.claude/CLAUDE.md" --glob "!SUBMISSION_CHECKLIST.md"`.
- [ ] 3.24 No hardcoded sweep values exist in scripts or test files — all live in `config/benchmark_config.yaml`, and those values match `Profile Parameter Values`. `Workload_Definitions` command columns are generated display, not an authoring source.
- [ ] 3.25 No hardcoded threshold values exist in `validate_results.py` — any required thresholds
           are loaded from `config/benchmark_config.yaml` via `--config`.
- [ ] 3.26 All Python execution is inside the repository-local
      `.venv`; no global package installs introduced.
- [ ] 3.26a `run_benchmark.sh` resolves Python interpreter robustly:
           require `.venv/bin/python` after setup; do not fall back to
           global `python3`.
- [ ] 3.27 All `apt-get` and other privileged calls in `setup.sh` and `scripts/` go through `run_privileged` / `run_noninteractive_root` with `DEBIAN_FRONTEND=noninteractive`; no executed raw `sudo apt-get` (it hangs on sudo's pty when output is redirected).
- [ ] 3.27a No ad-hoc ROCm installation commands exist outside `scripts/lib/rocm_install.sh`
           and the Ubuntu-specific libraries it sources (`rocm_install_24_04.sh`,
           `rocm_install_26_04.sh`). Verify no direct `amdgpu-install`, ROCm repository add, or
           ROCm package-install command appears in other shell scripts:
           `rg -n "amdgpu-install|repo\\.radeon\\.com/rocm|apt(-get)?\\s+install\\s+.*\\brocm|apt(-get)?\\s+install\\s+.*\\brocblas|apt(-get)?\\s+install\\s+.*\\bamd-smi" . --glob "*.sh" --glob "!scripts/lib/rocm_install.sh" --glob "!scripts/lib/rocm_install_24_04.sh" --glob "!scripts/lib/rocm_install_26_04.sh"`
- [ ] 3.27b For ROCm workloads using PyTorch, `requirements.txt` does not install
           unconstrained `torch`/`torchvision` from default PyPI; setup uses the
           official ROCm wheel index with pinned or configurable versions.
- [ ] 3.27c PyTorch setup verification rejects CUDA/CPU wheels and requires
           `torch.version.hip`, `torch.cuda.is_available()`, and at least one
           visible GPU before writing the setup completion marker.
- [ ] 3.28 All scripts are idempotent — repeated execution does not cause errors, duplication, or corruption.
- [ ] 3.29 `run_benchmark.sh` supports `--log-level` with `ERROR|WARN|INFO|DEBUG`.
- [ ] 3.29a `run_benchmark.sh` supports `--profile <smoke|baseline|extended>` and aliases
           `--smoke`, `--baseline`, `--extended`; LLM Serving CLI default is
           `smoke` (tiny local server). `--baseline` has an approximately 3–5
           minute target. Smoke, baseline,
           and extended yaml must match the workbook `Parameters_SmokeBaselineExtend` sheet, not
           historical 00_50/00_51 timings. After generation,
           `bash run_benchmark.sh --extended` uses that yaml. For 128/129/228/229,
           yaml `dtype` must be `bfloat16` (vLLM 0.26 rejects `bf16`). For
           119/219 run repository-local `scripts/gemm.py` and `scripts/conv2d.py`.
           For 130/230 use sequential `scripts/prompt_response_client.py`. For
           131/231 use concurrent `sglang.bench_serving` or `scripts/bench_serving.py`.
           For 130/131, setup must verify `import aiter` and the runner must call
           `wait_for_server` (default 600 s). Do not run 130 and 131 together, or
           230 and 231 together (shared port 30000). LLM Serving yaml
           `sweep.profile` must be `baseline`. Call `begin_benchmark_run` so
           `die()` appends a ledger row, and call `mark_benchmark_measure_start`
           after `ensure_setup.sh` returns. For 101/301 use `rvs --version` or `rvs -g`;
           for 112/312 use 30s/60s/120s timeouts plus retry; for 117/317 map to
           `--cold_iters` / `-v`; for 118/318 omit `-S` unless a solution id is
           explicit. Keep five metrics on 130. For 107/207 keep the official
           STREAM overlay `src/stream.c` (per-element relative checksum). For
           130/230 keep the leftover-DB-safe `scripts/parse_results.py` overlay.
           For 127/128/129, 227/228/229, and 327/328/329, every profile launches
           `vllm.entrypoints.openai.api_server`. A runner that contains
           `scripts/tiny_kv_server.py --host` fails self-check.
           For 130/131/230/231, smoke may use the tiny SGLang server;
           baseline/extended must launch `sglang.launch_server`. Keep the
           00_54 `run_benchmark.sh` overlays for 131/227/228/229/230/231.
           For 124/224 keep the real-SDXL overlays (`scripts/infer_sdxl.py`,
           `scripts/install_sdxl_python.sh`, `run_benchmark.sh`). Smoke may
           use the tiny denoiser; baseline/extended must load
           `stabilityai/stable-diffusion-xl-base-1.0`.
           See `AGENTS.md` §20.2 / §20.25, `implementation_components/README.md`,
           and `docs/rocm-pytorch-install-contract.md`.
           Do not emit comma-joined `--rw` / `--working-set-size` overrides.
- [ ] 3.29b `bash run_benchmark.sh --help` prints a `usage()` page matching
           `docs/run-output-contract.md` and exits 0 before `scripts/ensure_setup.sh`.
           Help is not a header dump (`sed -n '1,20p'`). Profile aliases read
           `Run smoke profile`, `Run baseline profile`, and `Run extended profile`.
           `--raw-file` is documented as an existing file for `--phase3`.
           Value-taking flags are documented as taking values. `-h` is omitted
           unless the parser accepts it.
- [ ] 3.29c `bash run_benchmark.sh --specification` (alias: `--matrix-definition`)
           prints every `benchmark_specification.json` field/value as a two-column
           table and exits 0 before `scripts/ensure_setup.sh`. The runtime source
           is the extracted JSON row, not the Excel workbook.
- [ ] 3.30 `run_benchmark.sh` writes `[RUN]`-prefixed command logs and persists `commands_executed.sh`.
- [ ] 3.30a `run_benchmark.sh` satisfies `docs/run-output-contract.md`,
           including credential-free replay commands, raw artifacts, parsing,
           validation, summary output, and correct exit codes.
- [ ] 3.31 `run_benchmark.sh` persists `run.log` with ANSI color codes stripped in file output.
- [ ] 3.32 `run_benchmark.sh` captures masked `env_variables.txt` and does not
           write `system_info.txt`.
- [ ] 3.32b `run_benchmark.sh` writes `journal_warnings.txt` at end of run via
           `capture_journal_warnings` (`journalctl -p warning`, run-window scoped
           when start/stop times are available; otherwise current boot only).
- [ ] 3.32a Metadata commands execute on the local host and save local run artifacts.
- [ ] 3.33 `run_benchmark.sh` stores `cli_options.env` (and optional user-specified options file, if requested).
- [ ] 3.34 Run artifact directory naming follows `YYYYMMDD_HHMMSS_<repo_name>_<hostname>` under `results/raw/`.
- [ ] 3.35 `run_benchmark.sh` persists per-run sample exports in both CSV and JSON.
- [ ] 3.36 `run_benchmark.sh` reports total run duration at completion.
- [ ] 3.37 `run_benchmark.sh` supports resumable phase execution (`--phase` and `--phase1..--phase4`) with clear completion logs.
- [ ] 3.38 `--phase phase3` requires and honors `--raw-file` for parse-only recovery workflows.
- [ ] 3.39 Per-run raw benchmark rows are exported in dual formats (`raw_results.csv` and `raw_results.jsonl`).
- [ ] 3.40 End-of-run summary includes extended descriptive statistics (min/max/mean/median/stddev/p95) where applicable.
- [ ] 3.40c End-of-run summary emits exactly one `[INFO]` metric line per numbered
           item in `benchmark_specification.json` `Metrics`, preserving each item
           description and units and appending labeled values from the latest
           validated SQLite run; no generic replacement sentence is present.
- [ ] 3.40c1 After `bash run_benchmark.sh` completes, the summary contains every
           required Metrics item in source order and format. Additional output
           is allowed, but no required Metrics item may be omitted or replaced
           by a generic statement.
- [ ] 3.40c2 End-of-run summary follows `docs/run-output-contract.md` line order:
           Run ID/status line, Command submitted, Command fully resolved,
           Start/Stop/Elapsed, Artifacts, SQLite DB, an empty
           `[INFO]` spacer, all Metrics lines, then a trailing empty `[INFO]` spacer.
           Metrics must not appear above Artifacts or SQLite DB. The two command
           lines come from `print_benchmark_summary_commands` (captured argv;
           hyphenated flags; empty if unknown).
- [ ] 3.40c3 After workload execution, `bash scripts/collect_hw_sw_info.sh "${RUN_DIR}"`
           creates `hardware_info.txt`, `software_info.txt`, and `errors_info.txt`
           in the per-run artifact directory. The hardware/software files contain
           Excel-derived General and detected-vendor command sections plus
           per-command timestamp/status blocks; failed optional probes are
           recorded in `errors_info.txt`.
- [ ] 3.40c4 `run_benchmark.sh` appends exactly one row for this invocation to
           `/var/opt/benchmarks/runtime_ledger.csv` using `scripts/update_runtime_ledger.py`.
           The header matches `LEDGER_COLUMNS` (`table_index_number`, `run_id`,
           `workload_number`, `runtime_root_dir`, `benchmark_profile`,
           `start_datetime`, `total_runtime_mm_ss`, `exit_code`,
           `failure_stage`, `failure_detail`, `raw_run_dir`, then `hostname`,
           `gpu_name`, `gpu_vram`,
           `gpu_count`, `os_version`, `cpu_model`, `workload_name`, the five
           metric pairs, `run_benchmark_command_submitted`,
           `run_benchmark_command_fully_resolved`, `Parameter_01_Name` /
           `Parameter_01_Value` through `Parameter_20_Name` /
           `Parameter_20_Value`, `parameters_set`, notes). Unused Parameter_*
           slots stay blank. `gpu_name` is the Card Series /
           MARKET_NAME product string, not the ROCm SMI banner. `gpu_vram` is
           the VRAM total-memory value only. The run ID is
           `<workload_number>_YYYYMMDD_HHMMSS`, `total_runtime_mm_ss` is
           `mm:ss`, and remaining values are populated or explicitly left blank
           when unavailable. Failed runs, including `die()` during server start,
           must still append one row after `begin_benchmark_run`.
- [ ] 3.40d For workload 112, the summary contains the five required metric lines
           in order: syscall null/read/write/stat/open, context-switch,
           memory-read versus working-set size, `bw_mem`, and `bw_pipe`, with
           every named subtest/working-set value measured and persisted.
- [ ] 3.40a `run_benchmark.sh` is local-only and does not expose remote prompts.
- [ ] 3.40b Legacy remote CLI options fail fast with a clear local-only error.
- [ ] 3.40f If reboot is used in local mode, script persists resume state and supports continuation after user login.
- [ ] 3.40g Local first-run reboot notice includes Enter-to-continue guidance, reboot count,
           auto-resume behavior, install-status path, and completion notifications.
- [ ] 3.40h `/etc/motd` includes the operator guidance lines:
           `To see latest status on install, execute the following:`
           and `cat /opt/benchmarks/<repo-name>/results/install_status.txt`, with blank lines
           around this guidance for readability.
- [ ] 3.40h1 `results/install_status.txt` timestamps use
           `YYYY-MM-DD HH:MM:SS  PHASE|STEP|SETUP` formatting.
- [ ] 3.40i On successful local completion, setup prints `setup.sh now complete`
           to its own output (no `wall` broadcast) and writes persistent completion status to `/etc/motd`.
- [ ] 3.40k For ROCm runtime setup flows, `setup.sh` follows
           `docs/rocm-reboot-install-contract.md`: installs/enables a systemd oneshot
           auto-resume service before reboot-capable ROCm steps, resumes with
           `--assume-yes --resume-from-service`, preserves `results/install_status.txt`
           and `results/install_commands.txt` across resumes, and removes the
           service only after successful completion.
- [ ] 3.40l Fresh-VM reboot validation confirms setup starts automatically after each
           ROCm-required reboot without the operator rerunning `bash setup.sh`.
- [ ] 3.40m The generated resume service disables systemd startup and stop timeouts
           (`TimeoutStartSec=0`, `TimeoutStopSec=0`, `KillMode=process`) and setup
           verifies the effective `TimeoutStartUSec` after `systemctl daemon-reload`.
- [ ] 3.40n Successful resume-service cleanup runs `systemctl reset-failed` so a
           completed setup does not retain a stale failed unit state.
- [ ] 3.40j In `setup.sh --exec-mode=remote`, setup is controller-driven:
           step commands execute via SSH wrappers (retry/backoff + keepalive +
           inter-command delay), and remote mode does not invoke long-running
           `bash setup.sh` on the target host.

### SQLite schema
- [ ] 3.41 The `runs` table contains all required columns from `AGENTS.md` plus the workload-specific
           aggregate columns derived from `benchmark_specification.json` `Metrics` field.
- [ ] 3.42 The `samples` table contains all dimension columns (from non-empty `Parameter_*` fields)
           and all metric columns (from `Metrics` field) derived from `benchmark_specification.json`.
- [ ] 3.43 Column names exactly match those derived in `SPEC.md` (item 2.12) — no drift.
- [ ] 3.44 Static run-level facts exist only in `runs`; they are not duplicated in `samples`.
- [ ] 3.45 If `thresholds:` is present, all `_min` keys encode "observed ≥ value" and all `_max`
           keys encode "observed ≤ value".
- [ ] 3.46 Each threshold or baseline value in `config/benchmark_config.yaml` has a YAML comment
           citing its derivation basis (e.g. `# ~50% of hardware_profile.mi300x.fp16_tflops_peak 1,300`).

### Raw output parsing
- [ ] 3.47 `scripts/parse_results.py` reads the output format from `benchmark_specification.json`,
           not from hardcoded column positions or AI training memory.
- [ ] 3.48 The CSV header row is detected dynamically on each invocation.
- [ ] 3.49 A `_COL_ALIASES` dict (or equivalent) maps known header variants to canonical column names.
- [ ] 3.50 Unit conversions are performed at parse time and documented in inline comments.
- [ ] 3.51 Per-shape errors set `sample.status = 'error'` and populate `error_message`
           without aborting the parse of remaining shapes.

### Fixture database (seeded by validate_results.py --seed-fixture)
- [ ] 3.52 `.venv/bin/python scripts/validate_results.py --seed-fixture`
      runs without error and creates `tests/fixtures/benchmark.db`.
- [ ] 3.53 The seeded fixture `runs` row has `status = 'ok'` and all aggregate metric columns are non-NULL,
           finite, and in valid range by metric type (positive for throughput/time-size metrics;
           non-negative for metrics that can validly be zero, e.g., miss rates/error counts), and
           at 40–60% of hardware peak where applicable (derived from `config/hardware_profile.mi300x.yaml`).
- [ ] 3.54 The seeded fixture contains at least two distinct `samples` rows covering different sweep points.
- [ ] 3.55 `sample_index` values are 0-based and contiguous.
- [ ] 3.56 All `created_at`, `started_at`, `finished_at` values are valid ISO-8601 UTC strings.
- [ ] 3.57 `error_message` is NULL on all fixture rows.
- [ ] 3.58 The seeded fixture schema (table names, column names, column types) exactly matches what
           `scripts/parse_results.py` produces.
- [ ] 3.59 `validate_results.py --seed-fixture` imports only the standard library plus
           dependencies explicitly declared in `requirements.txt`; it has no benchmark-runtime dependency.

### Execution-loop validation contract
- [ ] 3.60 `validate_results.py` checks: run exists and `status == 'ok'`; at least one sample
           row; no sample with `status = 'error'`; all aggregate metrics non-NULL, finite, and
           in valid range by metric type (positive or non-negative as appropriate).
- [ ] 3.61 `validate_results.py` checks `BENCHMARK_DB` env var before applying `--db` default.
- [ ] 3.62 `validate_results.py` does not raise `FileNotFoundError` silently — it calls `sys.exit()`
           with an informative message when the database is missing.
- [ ] 3.63 `validate_results.py` runs all integrity checks and, when `thresholds:` is present,
           all threshold checks in one invocation.
- [ ] 3.64 No `tests/conftest.py`, `tests/test_integrity.py`, or other unit-test harness files exist.
- [ ] 3.65 `validate_results.py` skips threshold keys that are absent from config gracefully (no crash).
- [ ] 3.66 Threshold failure messages, when thresholds are configured, report both the measured
           value and the configured threshold.

### CI workflows
- [ ] 3.67 `ci.yml` runs on pull request and push, has `permissions: contents: read`, and its
           only job calls `<owner>/shared-workflows/.github/workflows/ci.yml@<ref>` with the
           workload's `vendor` and `os_label` (shellcheck, ruff, syntax, schema, structure,
           seeded-fixture validation, and actionlint run there).
- [ ] 3.68 `gpu-smoke.yml` triggers on `workflow_dispatch` only (never `pull_request`), has
           `permissions: contents: read`, and its only job calls
           `<owner>/shared-workflows/.github/workflows/gpu-smoke.yml@<ref>`, which runs
           `run_benchmark.sh --profile <profile> --validate` on `[self-hosted, gpu, <vendor>, <os_label>]`
           and uploads `results/summary.json`, `results/environment.json` and `results/parsed/`.
- [ ] 3.69 No workflow uses `continue-on-error: true` or `|| true` on a lint or validation step.
           `python3 scripts/ci_contract.py --check-callers <repo>` passes.

### Remote execution
- [ ] 3.70 N/A for local-only template: no remote execution path exists in generated repository scripts.

---

## Phase 4 — Final cross-reference
*Last check before reporting complete.*

- [ ] 4.1  Re-grep for `TODO`, `pass`, `raise NotImplementedError`, `<!--` across all files.
           Use: `rg -n "TODO|raise NotImplementedError|^\s*pass\s*$|<!--" . --glob "*.sh" --glob "*.py" --glob "*.md" --glob "!AGENTS.md" --glob "!.claude/CLAUDE.md" --glob "!SUBMISSION_CHECKLIST.md"`
           Zero results required in generated artifacts.
- [ ] 4.2  `benchmark_specification.json` is byte-for-byte identical to the file provided at submission —
           confirm it has not been modified.
- [ ] 4.3  `README.md`, `docs/AI_AGENT_INSTRUCTIONS.md`, `docs/repository-template.md`, and all `*_TEMPLATE.md` files
           are byte-for-byte identical to the files provided at submission — confirm none were modified.
- [ ] 4.4  Run `.venv/bin/python scripts/validate_results.py --seed-fixture` locally.
           All checks must pass.
- [ ] 4.5  Confirm `results/`, `.venv/`, and `build/` are present in `.gitignore`.
- [ ] 4.6  Confirm no secrets, credentials, API keys, or tokens appear anywhere in committed files.

---
- [ ] 4.4  `bash scripts/check_github_publish_ready.sh` passes from the generated workload repository root.
- [ ] 4.5  Root `LICENSE`, `legal/NOTICE`, `.gitignore`, `.gitattributes`, workload-specific `.github/` community files, and generated-repository CI workflows are present.
- [ ] 4.6  `README.md` is complete and contains no unresolved `[[GENERATE: ...]]`, `{{...}}`, or template-only generation markers.
- [ ] 4.7  The published workload does not depend on the ignored nested `TEMPLATE_*_copy/` workspace; setup, run, parse, validate, docs, CI, and legal files all resolve within the workload repository itself.
- [ ] 4.8  `git status`/ignore rules exclude runtime results, virtual environments, archives, credentials, downloaded weights, `runtime_ledger.csv`, and the nested generation workspace.
- [ ] 4.9  After the workload passes, the nested `*_copy/` generation workspace has been removed (`scripts/create_one_workload.py` does this, or run `python3 scripts/remove_template_copy.py --repo-root <repo>` from the source template) and `results/generation_manifest.json` records `template_copy_removed_at`.

*End of checklist. All items must be checked before implementation is reported complete.*
