# AI_AGENT_INSTRUCTIONS.md

You are generating one or more complete benchmark repositories from the current template workspace. The user prompt supplies one or more workload numbers and may optionally supply a legacy repository directory and a remote VM login command. If the remote login command contains an IPv4 address, remote validation is mandatory: after each local repository is created, load that repository onto the specified VM, install it there, and run it there before marking the workload complete. The remote VM is an external generation-time validation host only; it never changes the local output location, and no SSH/runtime path is written into the generated repository. The user does not copy this instruction file or create a fixed-name prompt file manually.

## Minimal operator prompt

The chat only needs to name the workloads and, when a VM should run them, the SSH login. Do not ask the user to repeat the defaults below. `through`, `to`, and `-` are inclusive: `101 through 132` means 101, 102, … 132. A trailing word such as `inclusive` is ignored.

When the Cursor workspace is the parent of this generator:

```text
@ai-agent-gpu-benchmark-repo-generator/docs/AI_AGENT_INSTRUCTIONS.md
Generate workloads 101 through 132.
Remotely access Ubuntu VM with `ssh -i /path/to/.ssh/<amd_ssh_key> root@<REMOTE_HOST_IP>`
```

When the Cursor workspace is this generator folder, attach `@docs/AI_AGENT_INSTRUCTIONS.md` instead. The `Generate` line and the SSH line stay the same. Replace the key path and the IPv4 address with the real login. Placeholders do not select a VM. The same three lines work for another range or host by changing only those two facts. An `ssh` command may also include `-p <port>`.

Save that chat text as the submitted-prompt artifact, then run this from the generator directory. This is the only generation action. Do not pass `--remote-root`, `--project-root`, or `--template-root`, and do not reimplement copy, setup, or smoke:

```bash
MSYS_NO_PATHCONV=1 python3 scripts/run_from_prompt.py --prompt-file ../AI_AGENT_PROMPT_SUBMITTED_<WORKLOADS>_<UTC_TIMESTAMP>.md
```

Run it from the generator directory in Git Bash (Windows) or bash, exactly as written. `python3` is the interpreter that passes `scripts/generation_host_preflight.py` (Python 3.10+ with PyYAML); if a different one is first on `PATH`, put that interpreter's full path in its place (preflight prints the full command with it when it fails). `MSYS_NO_PATHCONV=1` stops Git Bash from rewriting paths. Save the prompt in the project root (the generator's parent) and pass it as the relative `../` path, never a `C:\...` or `/c/...` path.

`scripts/run_from_prompt.py` resolves the template from its own file location, writes each repository in the parent of this generator, and calls `scripts/create_one_workload.py` for the whole list in order. Repositories are created in that parent even when Cursor's open folder is this generator.

Defaults when the prompt omits them:

- This generator tree is the only template. Do not read or copy any other `TEMPLATE_*` directory.
- No `Legacy:` line means legacy mode is off. A `Legacy:` line is not read by `run_from_prompt.py`.
- Do not refresh the VM unless the prompt explicitly confirms a refresh.
- Install, develop, and run only under `/opt/benchmarks/<Workload Number>-<Repo Name>`. Never `/root` or `/opt/workloads`.
- Every `run_benchmark.sh` invocation appends to `/var/opt/benchmarks/runtime_ledger.csv`.
- An SSH command with an IPv4 address makes remote setup and smoke mandatory for every requested workload. Debug a remote failure on that VM inside `/opt/benchmarks/<repo>`, fix the local sibling, and recheck with `create_one_workload.py --validate-only`.
- Continue until every requested workload is recorded. Do not stop after the first success.

At the beginning of generation, record the current UTC timestamp as `generation_started_at`. At the end, after all implementation, validation, and checklist gates pass, record `generation_finished_at` and calculate the wall-clock `generation_duration_seconds`. Do not report completion until those values are written to both `results/generation_manifest.json` and `GENERATION_REPORT.md`.

## Inputs and path discovery

1. Read one or more workload numbers from the user prompt. Accept comma-separated lists, `and` lists, `ALL`, and inclusive `through`, `to`, or hyphen ranges, such as `Generate workloads 102, 105`, `Generate workloads 102 and 105`, `Generate workloads ALL`, and `Generate workloads 101 through 132`. If the list is missing or ambiguous, stop and report the problem.
2. Treat the parent directory of the directory containing this file as the source template directory. Confirm it contains `AGENTS.md`, `.claude/CLAUDE.md`, `BenchmarkSpecDefinitions.xlsx`, `docs/generation-workflow.md`, and `scripts/extract_benchmark_definition.py`.
3. Treat the parent directory of the source template directory as the project root. Do not create the generated repository inside the template directory.
4. Before Phase 0, create `<project-root>/<Workload Number>-<Repo Name>/<source-template-name>_copy/` as a complete copy of the source template. The copied directory is the active template root for extraction, validation, initialization, and all subsequent generation actions. The generated repository root remains the parent directory containing the copy; all generated documents, implementation files, configuration, and results must be written at that parent root, never inside the active copy. The copy is a generation workspace only: it is removed once the workload passes (see Completion gates).
5. If the optional second prompt line is present, parse `Legacy: <directory>` as `LEGACY_DIRECTORY_NAME`. If it is absent, use `NONE`.
6. If the prompt contains an SSH login command with a remote IP address or VM, retain it as `REMOTE_VALIDATION_COMMAND`. If absent, use `NONE`. When an IPv4 address is present, the agent MUST use that VM for every requested workload: copy/load the completed local repository to the VM, set validation-copy directory permissions to `0755` (see below), run `bash setup.sh --assume-yes` on the VM, run `bash scripts/self_check_generated_repo.sh`, and run `bash run_benchmark.sh --profile smoke --validate` on the VM. Do not mark the workload complete until those remote steps finish or the workload is recorded as failed/timed out. This command and all remote activity are generation-time only — never write the command, credentials, IP, or any remote-mode execution path into the generated repository itself (see `docs/ARCHITECTURE.md` → "Two execution contexts" and `AGENTS.md` § 29.1). A supplied SSH command does not authorize a destructive VM rebuild. Ask the user for explicit confirmation before invoking `scripts/refresh_remote_vm.sh`; otherwise use the existing VM and still perform the mandatory load/install/run validation. When a confirmed refresh occurs, reconnect after the rebuild because the VM has a new SSH host key. The first attempt is expected to fail with `REMOTE HOST IDENTIFICATION HAS CHANGED`; remove the stale key and reconnect:

   ```bash
   ssh -i /path/to/.ssh/<amd_ssh_key> root@<REMOTE_HOST_IP>
   ssh-keygen -R <REMOTE_HOST_IP>
   ssh -i /path/to/.ssh/<amd_ssh_key> root@<REMOTE_HOST_IP>
   ```

Answer `yes` when SSH asks whether to add the new host key. Confirm that the login banner matches the workload `OS Version` (`Ubuntu 24.04` or `Ubuntu 26.04`) before installing or smoke-testing.

On the validation VM, install, develop, and run every repository in `/opt/benchmarks/<Workload Number>-<Repo Name>` (`scripts/create_one_workload.py --remote-root`, default `/opt/benchmarks`). Do not install a second copy in `/root` or `/opt/workloads`. Every `run_benchmark.sh` invocation appends to `/var/opt/benchmarks/runtime_ledger.csv` and prints `Runtime entry added to /var/opt/benchmarks/runtime_ledger.csv.`

Immediately after the repository is extracted on the validation VM and before `setup.sh`, set directory modes to `0755` (`drwxr-xr-x`). A Windows-hosted `tar` copy typically extracts as `0777` (`drwxrwxrwx`); `ls --color` then highlights those directories lime green because they are other-writable. `scripts/create_one_workload.py` applies this automatically. If the agent copies the tree without that driver, it must still run:

```bash
REPO=/opt/benchmarks/<Workload Number>-<Repo Name>
find "$REPO" -type d -exec chmod 755 {} +
find "$REPO" -type f -not -path '*/.venv/*' -not -path '*/.cache/*' -exec chmod 644 {} +
chmod +x "$REPO"/*.sh "$REPO"/scripts/*.sh "$REPO"/scripts/lib/*.sh 2>/dev/null || true
```

Do not leave world-writable `/opt/benchmarks/<Workload Number>-<Repo Name>` trees. Regular files outside a preserved `.venv` or `.cache` are `0644` except the executable `.sh` helpers restored above. Do not clear modes inside those two directories: Triton's bundled `ptxas` must stay executable, and NVIDIA vLLM and SGLang `setup.sh` call `restore_triton_nvidia_bin_exec` after pip.

7. Determine the parent project root as the parent of the source template directory. Before Phase 0, save the exact received prompt in that project root as `AI_AGENT_PROMPT_SUBMITTED_<WORKLOADS>_<UTC_TIMESTAMP>.md`. Use `ALL` when every workbook workload was requested, compact `starttoend` tokens for ranges, and underscore-separated tokens for non-contiguous lists. Do not overwrite an existing artifact; append a numeric collision suffix if necessary. Append traceability metadata as an HTML comment without writing private-key contents.

8. Before Phase 0 extraction, run `python3 scripts/generation_host_preflight.py --template-root <source-template>`. When it fails it prints the exact start command with the interpreter it ran under. The host needs Python 3.10+, PyYAML, and (on the validation VM) `rg`. Write every generated `.sh` / `.py` / `.md` / `.yaml` / `.json` / `.txt` as LF, including the nested `*_copy/` tree. Do not start a second overlapping `setup.sh` on the remote VM.

## Required gated workflow

Follow the five-phase workflow in `docs/generation-workflow.md` exactly. Do not collapse phases or start implementation before Phase 0 succeeds.

### Phase 0 — extract and validate the workload contract

1. From the active template copy, confirm the workbook exists with an exact filesystem check:

   ```bash
   test -f BenchmarkSpecDefinitions.xlsx
   ```

2. Extract the selected workload into `benchmark_specification.json` in the active template copy:

   ```bash
   python3 scripts/extract_benchmark_definition.py \
     --workload <WORKLOAD_NUMBER> \
     --matrix BenchmarkSpecDefinitions.xlsx \
     --output benchmark_specification.json
   ```

3. Validate the extracted definition before reading Phase 1 source documents:

   ```bash
   python3 scripts/validate_template_inputs.py \
     --benchmark-specification benchmark_specification.json \
     --benchmark-schema schemas/benchmark_specification.schema.json
   ```

4. Retain the complete `benchmark_specification.json` for traceability. Confirm it includes `Profile Parameter Values` from the workbook `Parameters_SmokeBaselineExtend` sheet. Those values are the smoke/baseline/extended contract; do not invent sweep numbers. `Workload_Definitions` command columns are generated display. After generation, `bash run_benchmark.sh --extended` uses the yaml written from `Parameters_SmokeBaselineExtend`. Follow the current workload rules in `AGENTS.md` §20.2 and §20.25 (vLLM `bfloat16`, 119/219 local gemm/conv, 130/230 sequential vs 131/231 concurrent, AITER and 600 s ready-wait, 101/112/117/118 flag maps, no CLI sweep-list flags, hipcc host-GCC pin, 120/320 64-bit rocHPL allocations). Call `begin_benchmark_run` so `die()` and the `ERR` trap write a ledger row (still exit 1). After `ensure_setup.sh` returns, call `mark_benchmark_measure_start` so `total_runtime_mm_ss` starts at the benchmark. Keep the 00_78 NVIDIA 201–232 harness/overlay fixes: validator/ledger skip `rc`; 211 versioned `perf`; 212 lmbench 120/180s timeouts; 218 cuDNN apt packages before `build.sh`; 230/231 `sglang==0.5.19` + `torch==2.13.0+cu130` + `sglang-kernel==0.4.6.post1`. `scripts/generate_benchmark_config.py` writes `config/benchmark_config.yaml` from `Parameters_SmokeBaselineExtend` / extracted Profile Parameter Values only; a hand-derived yaml must keep those sheet numbers. For 107/207 keep the official STREAM per-element relative checksum from `implementation_components/stream-reference` (`src/stream.c`); do not rewrite it with a summed-array absolute `1e-13` check. For 130/230 keep the profile `scripts/parse_results.py` that migrates or rebuilds leftover `results/benchmark.db`. For 131/231 keep the smoke-vs-`sglang.launch_server` overlays; for 227/228/229 keep the smoke-vs-`vllm.entrypoints.openai.api_server` overlays; for 230 also keep the real-SGLang `run_benchmark.sh` overlay. For 120/320 keep the `linpack-rochpl-amd` overlay `src/rochpl.cpp` (64-bit host matrix length; do not write `host_a(n * n)`; clamp `N>=65536` to 32768). After init, a smoke-breaking defect in an overlay listed in a matching `component.json` is repaired in the template source, the sibling, and `results/overlay_lock.json`, not by inventing a second parser (`implementation_components/README.md`). Ubuntu 26.04 extras are in `docs/rocm-pytorch-install-contract.md`. Every `scripts/build.sh` that calls `hipcc` must `source scripts/lib/hipcc_host_gcc.sh` or pass `--gcc-install-dir` (Ubuntu 26.04 Clang 23 otherwise fails with `'cstdlib' file not found`). Read `Workload Name` and the exact `Repo Name` from this validated definition. Treat the complete `Framework` value as mandatory software inventory. This value is translated from the workbook's `Software Framework` column. Every application, tool, utility, program, library, language runtime, and framework listed there must be installed and independently verified; do not omit entries or rely on one listed package being installed transitively by another. `setup.sh` must fail clearly if any listed item cannot be installed or verified before `run_benchmark.sh` is allowed to execute.

## Strict sequential multi-workload generation

When the prompt requests more than one workload (comma lists, `and` lists, ranges, or `ALL`), process workloads **strictly one at a time** in ascending numeric order.

Imperative rules:

1. Save **one** submitted-prompt artifact that lists every requested workload (`AI_AGENT_PROMPT_SUBMITTED_<WORKLOADS>_<UTC_TIMESTAMP>.md`).
2. Initialize or update `<project-root>/batch_generation_manifest.json` with `requested_workloads` for the full list. Append or update each repository entry **after that workload finishes** (pass, fail, abandon, or timeout). Do not wait until the end of the batch to write the first entry. Leave batch `generation_finished_at` and `generation_duration_seconds` **null** until every requested workload is recorded. Do not stamp a batch finish time after the first workload.
3. Call the chatbox entry point once for the full list. It invokes `create_one_workload.py`, which creates, remote-validates, and records one workload at a time. Do not reinvent copy/setup/smoke helpers, and do not pass `--remote-root`:

   ```bash
   MSYS_NO_PATHCONV=1 python3 scripts/run_from_prompt.py --prompt-file ../AI_AGENT_PROMPT_SUBMITTED_<WORKLOADS>_<UTC_TIMESTAMP>.md
   ```

   Use the exact start command from "Minimal operator prompt" above.

   `create_one_workload.py` catches per-workload failures as `Exception`/`RuntimeError` (not `SystemExit`) and records `failed` before continuing. Do not call it with a separate `--workload` list unless retrying with `--validate-only`.

4. **Do not** call `scripts/create_generated_batch.py` from the AI Coding Agent chatbox path. That script scaffolds many repositories too early and violates this contract. Do not write throwaway `_process_one.py` helpers.
5. **Do not** create the next workload's directory, template copy, or scaffolding until the current workload is finished under the completion rules below.
6. Finish the current workload completely before starting the next: full Phases 0–4, every applicable `docs/SUBMISSION_CHECKLIST.md` item, local `setup.sh` / smoke `run_benchmark.sh` gates, and remote setup/smoke when `REMOTE_VALIDATION_COMMAND` is present.
7. On failure: notify the user with the workload number, failure summary, and artifact paths; record the workload in `batch_generation_manifest.json` with status `failed`; then continue to the next workload.
8. If further work is no longer beneficial by the agent's judgment: notify the user, record status `abandoned` with a short reason, and continue to the next workload.
9. If the current workload is still not running a successful smoke path after **60 minutes of calendar time** from when work on that workload started: notify the user, record status `timed_out`, and continue to the next workload. The 60-minute limit is elapsed calendar time (clock time from start), not accumulated active effort. Idle time, status questions, waiting, and conversation pauses all count. Do not interpret this as "60 minutes of wall-clock effort."
10. Refresh a supplied remote validation VM at most once before the first workload in the batch (only with explicit user confirmation). Reuse that same VM sequentially for later workloads.
11. A user status question, progress check, or "what are you waiting on?" is **not** a stop signal and does **not** require the user to tell the agent to resume. Answer in a few sentences, then immediately continue implementing the current unfinished workload in the same turn. Do not end a turn after a status answer while a workload is still unfinished and its 60-minute calendar clock is still running. The only reasons to stop work on the current workload are: it finished (`passed`), failed with user notification, was abandoned with user notification, or timed out.
12. Finishing the current workload is **not** permission to end the turn. After recording `passed` / `failed` / `abandoned` / `timed_out`, immediately start the next remaining requested workload in the **same turn**. Do not wait for the user to prompt again. The only reasons to end a multi-workload generation turn are: every requested workload is recorded, the user explicitly cancelled the batch, or the agent is blocked on a required user decision (for example a destructive VM refresh).

13. **Log every generator repair.** Any change to a file in this generator during a batch (an overlay under `implementation_components/`, `scripts/metric_contract.py`, a template, the workbook) is logged with one line per file before the recheck:

    ```bash
    python3 scripts/log_generator_repair.py --workload <N> --file <generator-relative path> --reason "<what failed and what changed>"
    ```

    The log is `results/generator_repairs.md` in this generator (ignored by git). `run_from_prompt.py` prints the entries added during the batch at the end of its summary, and the batch report ends with that list (or `Generator repairs: none`).
14. **Counters the host does not have.** When a collector cannot read a counter because the host does not have it (no ECC, no second GPU, no second NUMA node, PMU access denied, a stub server), the collector writes `na (expected: <reason>)` for that metric, for example `na (expected: ECC disabled)`. `scripts/metric_contract.py` already accepts that form. Do not add new string matches to `classify_na` for a new reason; fix the collector to emit `na (expected: <reason>)` and log the repair (rule 13). A plain `na` stays unexpected and blocks `PASS`.

## Generated repository location

Create the generated repository at:

```text
<project-root>/<Workload Number>-<Repo Name>/
```

The AI Coding Agent (ie, Cursor) project-root sibling is the created repository only. The source template directory is `ai-agent-gpu-benchmark-repo-generator`. Project root is that directory's parent, including when the parent is named `TEMPLATE_00_103` and when Cursor's open folder is the generator itself. Each created repository is a sibling of `ai-agent-gpu-benchmark-repo-generator` in that parent. `/root`, a VM home, a `DIRECTORIES/` folder, and a results-only staging folder are not the project root. Do not pass `--project-root /root` (or any remote home) to `create_generated_repo.py`. If generation-host preflight fails on Windows (missing PyYAML or `rg`), install the missing host tools or still create the local sibling first; do not relocate output to the validation VM.

The created repository is the files written by `create_generated_repo.py` and Phases 1–4 (`setup.sh`, `run_benchmark.sh`, `config/`, `scripts/`, `src/`, overlays, docs, `benchmark_specification.json`, `results/generation_manifest.json`, and, until the workload passes, the nested `*_copy/` generation workspace). Validation-host runtime state must not appear in that project-root sibling. `setup.sh` and smoke may create the following on the Ubuntu VM only; delete them from the project-root tree before recording `passed` if they were created there:

- `.venv/`, `.venvs/`, `venv/`
- `.cache/`
- `.setup_state`, `.setup.lock`, `.rocm_runtime_stage.env`
- `results/raw/`, `results/parsed/`, `*.db` (keep `results/generation_manifest.json` and the `.gitkeep` sentinels)
- `build/`, `*.o`, `*.a`, `*.so`
- workload scratch such as fio `data/`
- cloned or built `third_party/` trees (rocBLAS, aiter, sglang checkouts) unless the matching overlay ships that source
- downloaded `*.deb`, `*.safetensors`, and wheel caches
- `__pycache__/`, `*.pyc`, `*.log`

A results-only stub (for example a folder that contains only `results/`) is not a created repository. A workload is incomplete until these exist on the AI Coding Agent project root:

```text
<project-root>/<N>_<Repo Name>/setup.sh
<project-root>/<N>_<Repo Name>/run_benchmark.sh
<project-root>/<N>_<Repo Name>/config/benchmark_config.yaml
```

Develop the code in the local directory, and copy it to the remote VM for testing. Do not copy anything from the VM back to the local directory. Temporary files, `.venv`, `.cache`, smoke outputs, builds, downloads, and other validation-host runtime state belong on the VM only; they must not enter the created repository that will be published. If a remote test fails, edit the local sibling, then copy that local tree to the VM again. Windows cannot run GPU `setup.sh` or smoke; those executable gates run on the VM. The created files must still exist locally before `passed`.

The directory name must be `<Workload Number>-<Repo Name>`, where `Repo Name` is the exact value from `benchmark_specification.json`, not the human-readable `Workload Name`. Pass the timestamped submitted-prompt path to `scripts/create_generated_repo.py --prompt-file <SUBMITTED_PROMPT_FILE> --workload <WORKLOAD_NUMBER>` from the source template to create the complete active copy and initialize the generated root for **only the current workload**. Thereafter run all template utilities from `<Workload Number>-<Repo Name>/<source-template-name>_copy/`. Use `scripts/init_generated_repo.py` only with explicit `--template-root` and `--repo-root` values when reinitialization is required. Before generating workload-specific implementation files, inspect and use the automatic component resolution provided by `scripts/resolve_implementation_components.py`. Component selection is derived from Workload Number, GPU Vendor, and `config/implementation_packs.yaml`; users do not select components in `BenchmarkSpecDefinitions.xlsx`. Prefer compatible known-good component assets over regenerating equivalent files, but do not force a component when no manifest matches. The matrix-derived definition remains authoritative.

## Legacy-reference mode

When `LEGACY_DIRECTORY_NAME` is not `NONE`, treat `<project-root>/<LEGACY_DIRECTORY_NAME>` as read-only reference material. Compare its workload-specific behavior, selectively reimplement compatible behavior, and record material changes in the generated documentation. Do not copy it wholesale, copy runtime artifacts, or allow it to override the current matrix, schemas, protected libraries, or local-only execution rules.

When no legacy directory is supplied, generate the workload from the current template and workbook, reusing any implementation components automatically discovered by the resolver.

## Phases 1–4

After Phase 0 validation:

1. Read the remaining documents in the priority order defined by `AGENTS.md`.
2. Generate `PRD.md`, `SPEC.md`, and `README.md` from their corresponding templates.
3. Generate every workload-specific implementation file required by the validated definition and the repository template, including helper scripts invoked indirectly by `run_benchmark.sh` or `setup.sh` (for example, `scripts/run_tensor_correctness.py`). Treat the component overlay as a complete file manifest, not just a documentation scaffold; run the repository self-check to prove every referenced helper exists. If `init_generated_repo.py` copied a component overlay file, keep that file byte-identical to its template source; do not regenerate a different `src/stream.c` or `scripts/parse_results.py` for 107, 130, 207, or 230, and do not regenerate a different `scripts/infer_sdxl.py`, `scripts/install_sdxl_python.sh`, or `run_benchmark.sh` for 124 or 224. A smoke failure inside a copied overlay is the three-place repair in `implementation_components/README.md` (template, sibling, and lock digest), not a second parser.
4. Generate `requirements.txt` from the direct third-party imports and validated framework requirements of the implementation. Exclude unused and transitive packages, keep accelerator packages on their documented vendor-specific installation path, and use tested bounds or pins where reproducibility requires them. Apply `docs/dependency-policy.md`: the matrix/profile and implementation together determine direct dependencies; do not install optional packages such as torchvision in workloads that do not require them.
5. Apply all contracts referenced by `docs/generation-workflow.md`, including: `docs/machine-checkable-contracts.md`, `docs/host-prerequisite-contract.md`, `docs/raw-output-parser-contract.md`, `docs/run-output-contract.md`, `docs/rocm-reboot-install-contract.md`, and `docs/rocm-pytorch-install-contract.md` when applicable.
6. Use `scripts/lib/rocm_install.sh` only through its protected functions; do not rewrite or inline that library. That file is a dispatcher: it sources `scripts/lib/rocm_install_24_04.sh` or `scripts/lib/rocm_install_26_04.sh` from the host Ubuntu release. Do not rewrite those versioned libraries either.
7. Keep generated repositories local-runtime repositories. Do not add SSH prompts, remote execution paths, remote metadata collection, or persisted remote credentials to the generated repository. When `REMOTE_VALIDATION_COMMAND` contains an IPv4 address, mandatory generation-time validation still loads, installs, and runs the repository externally on that VM; the local repository remains the authoritative deliverable.
8. Use the repository-local `.venv` created by setup before running Python validation. Set `BENCHMARK_PYTHON` when a specific installed Python interpreter is required. Never use a global Python package environment.
9. Generate `benchmark_actual.csv` and `benchmark_actual_excel.csv` from the designated workbook row according to the template SOP, including shifted headers, `Original`/`Actual`/`Changed` rows, installed-tool version cells, and UTF-8 BOM encoding.
10. Include `config/hw_sw_info_commands.xlsx`, `scripts/generate_collect_hw_sw_info.sh`, and the generated `scripts/collect_hw_sw_info.sh` in every generated repository. After the workload run and validation complete, execute `bash scripts/collect_hw_sw_info.sh "${RUN_DIR}"`; verify that that per-run directory contains `hardware_info.txt`, `software_info.txt`, and `errors_info.txt` with the Excel-derived command list, per-command status blocks, and any failed probes. Do not write `system_info.txt`.
11. Include `scripts/update_runtime_ledger.py` in every generated repository. Ensure `run_benchmark.sh` appends exactly one row to `/var/opt/benchmarks/runtime_ledger.csv` for every invocation, including failures, with the required `LEDGER_COLUMNS` order (`exit_code`, `failure_stage`, `failure_detail`, `raw_run_dir`, then `hostname`, `gpu_name`, `gpu_vram`, `gpu_count`, `os_version`, `cpu_model`, `workload_name`, then the seven metric pairs, then `run_benchmark_command_submitted`, `run_benchmark_command_fully_resolved`, `Parameter_01_Name`/`Parameter_01_Value` through `Parameter_20_Name`/`Parameter_20_Value`, `parameters_set`, `notes`), `<workload_number>_YYYYMMDD_HHMMSS` run ID, profile, `total_runtime_mm_ss` as `mm:ss`, one exit code, failure stage/detail, metric definitions/results, hardware/software fields, the submitted and fully resolved `run_benchmark.sh` commands, parameters, and notes. Call `capture_benchmark_run_command_submitted "$@"` before argument parsing. Do not write `runtime_exit_code`. `gpu_name` must be the Card Series / MARKET_NAME product string, not the ROCm SMI banner. Ledger-write failures must be warnings and must not replace the benchmark exit code.
12. Include `scripts/ensure_setup.sh` in every generated repository and invoke it as the first operational step in `run_benchmark.sh` after `--help` and `--matrix-definition` handling. `bash run_benchmark.sh --help` must print the `usage()` page from `docs/run-output-contract.md` and exit 0 before `ensure_setup.sh`. `bash run_benchmark.sh --matrix-definition` must print this workload's `benchmark_specification.json` field/value table and exit 0 before `ensure_setup.sh`. If `.setup_state` is absent, it must invoke `setup.sh --assume-yes` when supported and refuse benchmark execution unless setup completes. If setup pauses for reboot/resume, report that the operator must rerun `bash run_benchmark.sh` after setup finishes; do not implement automatic post-reboot benchmark continuation.
13. Generate `GENERATION_REPORT.md` and update `results/generation_manifest.json` with the final generation timing fields, then validate the manifest against its schema.

## Completion gates

For each workload, before creating the next workload directory, execute every item in `docs/SUBMISSION_CHECKLIST.md` in order for that repository, then run:

```bash
.venv/bin/python scripts/validate_template_inputs.py \
  --generation-manifest results/generation_manifest.json \
  --generation-schema schemas/generation_report.schema.json
bash setup.sh
bash run_benchmark.sh --profile smoke --validate
bash scripts/self_check_generated_repo.sh
bash scripts/smoke_check_generated_repo.sh ../<Workload Number>-<Repo Name>
```

After `bash run_benchmark.sh` completes, inspect its end-of-run summary. It must emit the required output in the exact Metrics order and format derived from `benchmark_specification.json`: one metric line for every numbered Metrics item, preserving each item's description and units and appending measured values. Other output is allowed, but the required Metrics lines may not be omitted or replaced by a generic statement. Confirm the fixed wrapper order from `docs/run-output-contract.md`: Run ID/status, Command submitted, Command fully resolved, Start/Stop/Elapsed, Artifacts, SQLite DB, empty `[INFO]`, Metrics, trailing empty `[INFO]`. Apply that contract for the current workload before starting the next.
After `bash run_benchmark.sh` completes, also confirm that its post-run inventory collection produced `hardware_info.txt`, `software_info.txt`, and `errors_info.txt` in the per-run artifact directory. `errors_info.txt` records unavailable optional probes and is not itself a benchmark failure; the benchmark's own execution, parsing, validation, and exit status remain authoritative.
Also confirm that `/var/opt/benchmarks/runtime_ledger.csv` exists, has one header row matching `scripts/update_runtime_ledger.py`, and has exactly one new row for the workload invocation.

Remove the nested template copy when a workload is recorded `passed`. `scripts/create_one_workload.py` does this automatically after validation passes (pass `--keep-template-copy` to opt out) and keeps the copy when validation fails so the workload can be debugged. If the workload was generated another way, or a `failed` / `abandoned` / `timed_out` workload will not be retried, run `python3 scripts/remove_template_copy.py --repo-root <project-root>/<Workload Number>-<Repo Name>` from the source template, never from inside the copy. The script saves each resolved component's `gate.json` to `results/component_gates.json` and records `template_copy_removed_at` in `results/generation_manifest.json`; `self_check_generated_repo.sh` and `smoke_check_generated_repo.sh` accept a missing copy only when that field is present.

Record each finished workload in `<project-root>/batch_generation_manifest.json` with UTC `create_start_time`, UTC `create_end_time`, human-readable `create_total_time`, and status `passed`, `failed`, `abandoned`, or `timed_out`. Do not self-certify based on a partial review of the current workload. For multi-workload prompts, do not block the remaining queue on one failed/abandoned/timed-out workload after the user has been notified.

When `REMOTE_VALIDATION_COMMAND` contains an IPv4 address, wait for the VM to be reachable, then load, install, self-check, and smoke-run each finished local repository on that same VM before starting the next workload's directory. If refresh is not confirmed, use the supplied VM without rebuilding it. Use cheap-to-expensive remote order: copy → `chmod 755` on every directory in the extracted tree → LF/`rg` preflight → `setup.sh` → smoke → `self_check` → publish-ready → generator `smoke_check`. Confirm `stat -c '%a %n' /opt/benchmarks/<Workload Number>-<Repo Name>` prints `755` (not `777`). The local repositories remain authoritative and must still pass every local gate. Do not add the SSH command, remote IP, key path, or remote execution code to any generated repository.

After `create_generated_repo.py` / init, read `results/component_resolution.json`, `results/overlay_lock.json`, and `results/component_leftover_work.md`. A locked overlay is a recorded fingerprint. When smoke fails inside one of those files, write the same bytes in `implementation_components/<component-id>/files/<path>`, the sibling path, and that path's `sha256` in `results/overlay_lock.json`, then recheck with `create_one_workload.py --validate-only`. `self_check_generated_repo.sh` reports `Locked overlay rewritten` only when the sibling and that digest differ. `smoke_check_generated_repo.sh` reports `Implementation component mismatch` when the sibling and the template source differ. Do not replace the overlay with a new collector or parser. Do not leave the workload failed when those three copies can match. Do not run `create_generated_repo.py` again on a non-empty sibling; `--force` discards it. `scripts/metric_contract.py` has no lock entry: repair the generator copy and the sibling copy, then use the same recheck. Treat Framework as install-and-verify. Apply GEMM runner/parser tokens only when a resolved component sets `contracts.gemm_per_point` (for example `rocblas-gemm-amd`). Workload 103 / `system-stress-amd` compiles and verifies `rocblas-bench` at `<repo>/third_party/rocBLAS/build/release/clients/staging`; it is not a GEMM sweep. For 101 / `system-config-amd`, do not map list intent to `rvs -l`. Use `rvs --version` or `rvs -g`. Prefer each component `gate.json` over rediscovering contracts from `AGENTS.md`.

Each `batch_generation_manifest.json` entry keeps every attempt in `attempts` (status, start, end, total time, reason) and `attempt_count`; the top-level times describe the latest attempt. Retrying a workload appends an attempt and never erases a failed one.

After the full requested list is processed, print a Markdown table with one row per requested workload containing the workload number, status, attempt count, and `create_total_time`, followed by two totals for the current prompt: **Successful time** (the passing attempt of each passed workload) and **Time including failed attempts** (every recorded attempt). Both exclude remote refresh time. `run_from_prompt.py` prints this table and both totals and writes them to the batch manifest as `generation_successful_seconds` and `generation_seconds_including_failed_attempts`.

The final report must include:

```text
Generation start time: <generation_started_at>
Generation stop time: <generation_finished_at>
Generation elapsed time: <generation_duration_seconds> sec
```

End the report with the generator repairs made during the batch, one line per file with the reason (from `results/generator_repairs.md`), or `Generator repairs: none`.

Run generation with `PYTHONDONTWRITEBYTECODE=1` (the start command's children already have it). `run_from_prompt.py` removes leftover `__pycache__`, `.pytest_cache`, `.ruff_cache`, and `.mypy_cache` folders from the generator and the generated repositories at the end of the batch; it never touches `.venv` or `.cache`.

## Post-generation root cleanup

After every requested workload directory is created and recorded (`passed`, `failed`, `abandoned`, or `timed_out`), and after batch `generation_finished_at` / `generation_duration_seconds` are stamped, delete generation-time scratch files from the local project root and from the remote validation host home (`/root`). Do this before reporting the batch complete. The AI Coding Agent (ie, Cursor) project-root sibling remains the created repository; do not treat the VM home as a substitute for those siblings.

Keep only required local project-root deliverables:

- the source template directory
- each `<Workload Number>-<Repo Name>/` directory
- `AI_AGENT_PROMPT_SUBMITTED_*.md`
- `batch_generation_manifest.json`

No `<Workload Number>-<Repo Name>/` directory should still contain a nested `*_copy/`; run `python3 scripts/remove_template_copy.py --repo-root <project-root>/<Workload Number>-<Repo Name>` for any that do.

Remove leftover helpers and logs that are not those deliverables, including:

- `*_create_start_time.txt`
- `workload_identities.txt`
- `rocm_pip_constraints.txt`
- ad-hoc helpers such as `_fill_generated_docs.py`, `patch_generated_repo.py`, `finish_one_workload.sh`, `process_range.sh`, and a project-root `_generation_helpers/` directory
- root-level `batch_process*.log`, `batch_process*.stdout`, `retry*.stdout`, and `*_setup.log`

Do not delete files inside a generated repository `results/` tree. On the remote validation VM, after the local project root has the authoritative `batch_generation_manifest.json`, also remove the VM-root copies of that manifest and any leftover helper `.py` / `.sh` / `.txt` / `.log` / `.stdout` files so the VM home holds no helpers. The generated repositories stay in `/opt/benchmarks/<Workload Number>-<Repo Name>/` and the ledger stays at `/var/opt/benchmarks/runtime_ledger.csv`. Do not delete generated repositories or `/var/opt/benchmarks/runtime_ledger.csv`.

## GitHub publication readiness

Every completed workload repository is an independent GitHub repository candidate. Before reporting a workload complete:

1. Ensure `README.md` is fully generated with no `[[GENERATE: ...]]`, `{{...}}`, TODO generation markers, or template-only instructions.
2. Preserve root `LICENSE` and `legal/NOTICE`.
3. Preserve the workload-specific `.github/` community files and generated-repository workflows installed by the initializer.
4. Keep runtime results, credentials, downloaded weights, archives, virtual environments, and the nested `TEMPLATE_*_copy/` generation workspace excluded by `.gitignore`.
5. Run `bash scripts/check_github_publish_ready.sh` from the generated workload root and require it to pass.
6. The published workload must not require the ignored nested template copy for setup, benchmark execution, parsing, validation, documentation, CI, or legal compliance.

