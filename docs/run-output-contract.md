# Run Output Contract

After `bash run_benchmark.sh` completes, it must print a concise end-of-run summary after benchmark execution and optional validation. The summary must include one output line for every required item in the `Metrics` field of `benchmark_specification.json`. Additional output is allowed, but omitting or replacing a required Metrics item is not allowed.

During execution, generated harnesses must print each executed command with exactly one `[RUN]` prefix per command line. Do not emit one `[RUN]` token per argv element. For Bash array commands, format the full command into one string first, then print:

```bash
printf -v command_text '%q ' "${cmd[@]}"
echo "[RUN] ${command_text}"
```

Python-backed workloads must execute the workload process with unbuffered output (for example `PYTHONUNBUFFERED=1`) and print progress before each long-running sample or sweep point so operators can identify where a VM-side run is spending time.

The wrapper format is fixed. Line order is mandatory for every generated workload (all 32 benchmarks). Emit empty `[INFO]` spacer lines exactly where shown (prefix only; no other text on those lines):

```text
[RUN] <benchmark command>
[INFO] Repository:                    <repository path>
[INFO] Ubuntu Version:                <Ubuntu release>
[INFO] Python Version:                <Python version>
[INFO] rocBLAS Version:               <rocBLAS package version>          (AMD workloads)
[INFO] ROCm Version:                  <ROCm package version>             (AMD workloads)
[INFO] CUDA Version:                  <nvcc release>                     (NVIDIA workloads, instead of the two lines above)
[INFO] NVIDIA Driver Version:         <nvidia-smi driver_version>        (NVIDIA workloads)
[INFO] System:                        <DMI system family>
[INFO]
[INFO] ===== Benchmark Summary =====
[INFO] Run ID: <run_id> | Status: <status> | Samples: <sample_count> | Profile: <profile> | Device: <device>
[INFO] Command submitted: <bash run_benchmark.sh plus the original flags>
[INFO] Command fully resolved: <submitted flags plus yaml defaults that were not already on the command line>
[INFO] Start time: <iso8601_utc_start>
[INFO] Stop time: <iso8601_utc_stop>
[INFO] Elapsed time: <elapsed_seconds> sec
[INFO] Artifacts: <run_artifact_directory>
[INFO] SQLite DB: <benchmark_db_path>
[INFO]
[INFO] <metric summary lines derived from benchmark_specification.json Metrics>
[INFO]
```

When the GPU stack is missing, `scripts/print_run_metadata.sh` prints `not installed (not used by this CPU benchmark)` for a workload whose Execution Domain is `CPU / System`, and `NOT FOUND (GPU setup did not install it)` for a GPU workload.


Required ordering rules:

1. Print the repository metadata block immediately after the benchmark command line.
2. Print the header, then the combined Run ID / Status / Samples / Profile / Device line.
3. Print `Command submitted` and `Command fully resolved` next, using `print_benchmark_summary_commands` from `scripts/lib/common.sh` (or the same two `[INFO]` lines). Use the captured argv strings. Hyphenated flags. Do not invent a command. If a string is unknown, print the label with an empty value.
4. Print Start time, Stop time, and Elapsed time next.
5. Print Artifacts and SQLite DB before any metric lines.
6. Print one empty `[INFO]` spacer, then every numbered Metrics line in source order, then one trailing empty `[INFO]` spacer.
7. Do not place metric lines above Artifacts or SQLite DB. Do not omit the empty `[INFO]` spacers around the metric block.

Metric lines are workload-specific and must be derived from the `benchmark_specification.json` field `Metrics`. Do not hardcode workload-specific metric examples in submitted-prompt artifacts or user documentation.

Generated repositories may format each metric line to include the most useful aggregate values for that workload, but the metric names, order, and count must follow the `Metrics` field. Each line must retain its source number, using the form `[INFO] #N: <description>; <column>=<value>`.

## Execution Implementation Requirements

Generated `run_benchmark.sh` must:

1. Begin with `set -euo pipefail`, resolve the repository root, handle `--help` through a `usage()` function, and invoke `bash scripts/ensure_setup.sh` before any benchmark execution. `--help` must print the help page and exit 0 before `ensure_setup.sh` or any install/benchmark work. The guard runs `bash setup.sh --assume-yes` when supported if `.setup_state` is absent, then refuses to run unless setup completes. Reboot-driven setup is not continued by the benchmark process; after reboot/resume completes, the operator reruns `bash run_benchmark.sh`.
2. Load workload settings from `config/benchmark_config.yaml` and supported CLI options; do not hardcode workload-specific sweep or threshold values.
3. Use `.venv/bin/python` when Python is required and add ROCm, compiler, or library paths only when required by the workload.
4. Create a unique `results/raw/<timestamp>_<repo>_<hostname>/` artifact directory and capture masked environment data, end-of-run `journal_warnings.txt` (`journalctl -p warning`, run-window scoped via `capture_journal_warnings`), stdout, stderr, exit status, and elapsed time. Do not write `system_info.txt`. After the end-of-run summary is assembled, write `metrics_summary.txt` in that same per-run directory via `write_metrics_summary_txt` from `scripts/lib/common.sh`. The file is the Benchmark Summary block without `[INFO]` prefixes: header, Run ID / Status / Samples / Profile / Device, both commands, start/stop/elapsed, Artifacts, SQLite DB, a blank line, one `#N:` metric line per `Metrics` item, and a trailing blank line.
5. After workload execution and validation, invoke `scripts/collect_hw_sw_info.sh "${RUN_DIR}"` so the Excel-defined, vendor-filtered inventory is written to `hardware_info.txt`, `software_info.txt`, and `errors_info.txt` in that per-run directory. The collector must run on the local benchmark host, preserve the `DESCRIPTION : Commands To Be Run` sections, record each command's status, and continue collecting when an individual probe is unavailable. A nonzero probe is documented in `errors_info.txt`; it must not hide the benchmark's own exit status.
6. Append exactly one row to `/var/opt/benchmarks/runtime_ledger.csv` for every invocation, including failed invocations, using `scripts/update_runtime_ledger.py`. Immediately after sourcing `scripts/lib/common.sh`, call `capture_benchmark_run_command_submitted "$@"` so the ledger records argv as entered. After argument parsing, call `begin_benchmark_run "${profile}"` so `die()` writes that row when the runner exits early. After `ensure_setup.sh` returns, call `mark_benchmark_measure_start` so the stored elapsed time starts at the benchmark. A setup failure still uses the `begin_benchmark_run` timestamp. After yaml defaults are applied, call `set_benchmark_run_command` with the fully resolved `bash run_benchmark.sh ...` string (submitted flags plus yaml-filled parameters that were not on the command line). Call `finish_benchmark_run` after a successful ledger write so the error path does not append a second row. Pass the workload profile, UTC start time, total runtime (seconds or `mm:ss`), overall `exit_code`, `failure_stage`, `failure_detail`, `raw_run_dir`, `run_benchmark_command_submitted`, `run_benchmark_command_fully_resolved`, effective parameter string, and notes. Do not write `runtime_exit_code`. The helper stores elapsed time in `total_runtime_mm_ss` as `mm:ss`, derives workload metadata, GPU/CPU/OS information, metric definitions/results, and the required `<workload_number>_YYYYMMDD_HHMMSS` `run_id`, and writes columns in the order defined by `LEDGER_COLUMNS` in `scripts/update_runtime_ledger.py`. Host/GPU/OS/CPU fields are `hostname`, `gpu_name`, `gpu_vram`, `gpu_count`, `os_version`, `cpu_model`, then `workload_name` and the metric pairs. After `metric_5_result` the columns are `run_benchmark_command_submitted`, `run_benchmark_command_fully_resolved`, `Parameter_01_Name`/`Parameter_01_Value` through `Parameter_20_Name`/`Parameter_20_Value`, `parameters_set`, `notes`. The helper fills those 40 slots from workbook `Parameter_01`–`Parameter_20` and the effective values after CLI overrides (submitted flags, then the fully resolved command, then `--parameters-set`, then yaml). Unused slots stay blank, not em-dash. `parameters_set` is rebuilt from those slots as `profile=<name>;key=value;...`. `gpu_name` is Card Series / MARKET_NAME, never the ROCm SMI banner; `gpu_vram` is the VRAM total-memory value only. On failure, `failure_stage` must be one of `setup|collection|parse|validation|timeout|integrity|other` and `failure_detail` must be the one-line reason (for example `STREAM did not print Solution Validates`). On success, `failure_stage` is `ok`, `failure_detail` is empty, and `notes` is `validated run`. When `--run-benchmark-command-fully-resolved` is omitted and submitted argv is present, the helper appends yaml defaults that were not already on the command line. When both are omitted, it reconstructs the profile command from `Profile Parameter Values`.
7. Persist an executable `commands_executed.sh` containing replayable, credential-free commands for the run.
8. Execute only the workload-required command, warm-up, monitoring, and collection steps; optional monitoring is conditional on the definition.
9. Parse raw output into the required CSV, JSON/JSONL, SQLite, and summary artifacts, then validate against configured thresholds or baselines.
10. Return zero only for a successful validated run and a nonzero status for setup, execution, parsing, validation, timeout, or integrity failures.
11. For LLM Serving, wait for the local server with `wait_for_server` from `scripts/lib/common.sh`. The default timeout is 600 seconds. Treat HTTP 503 as not ready, not as a crash. Do not hardcode 180 seconds.

The ledger call should be nonfatal if ledger storage itself is unavailable; it must never replace the benchmark's true exit code. A successful run may use:

```bash
.venv/bin/python scripts/update_runtime_ledger.py \
  --profile "${profile}" \
  --start-datetime "${start}" \
  --total-runtime "${elapsed_seconds}" \
  --exit-code 0 \
  --failure-stage ok \
  --failure-detail "" \
  --raw-run-dir "${RUN_DIR}" \
  --runtime-root "${REPO_ROOT}" \
  --run-benchmark-command-submitted "${BENCHMARK_RUN_COMMAND_SUBMITTED}" \
  --run-benchmark-command-fully-resolved "${BENCHMARK_RUN_COMMAND}" \
  --parameters-set "profile=${profile}" \
  --notes "validated run" || printf '[WARN] Runtime ledger update failed\n' >&2
```

## CLI Help Contract

`bash run_benchmark.sh --help` is operator documentation, not a header dump. Generated `run_benchmark.sh` must:

1. Define a `usage()` function and wire `--help` to it. Do not implement help as `sed -n '1,20p' "$0"` or any other fixed line-range print of the file header.
2. Handle `--help` and `--matrix-definition` before `scripts/ensure_setup.sh` and before workload option parsing that can start setup, install, or benchmark work. `--matrix-definition` prints this workload's `benchmark_specification.json` fields as a two-column table and exits 0.
3. Copy and customize `scripts/templates/run_benchmark_help_skeleton.sh`. Keep the script-header `Options:` field as a compact comma-separated inventory.
4. Print this shape, with the first prose line matching the script header `Description` field:

```text
Usage: bash run_benchmark.sh [OPTIONS]

<Description from the run_benchmark.sh header>

Profiles:
  --profile <name>              Run profile: smoke|baseline|extended (default: smoke)
  --smoke                       Run smoke profile
  --baseline                    Run baseline profile
  --extended                    Run extended profile

Execution:
  --device <gpu|cpu>            Execution device (default: gpu)
  --phase <phaseN|N>            Run one phase (phase1|phase2|phase3|phase4, or 1-4)
  --phase1                      Collection
  --phase2                      Collection alias
  --phase3                      Parse only; requires --raw-file <path>
  --phase4                      Validation only
  --raw-file <path>             Existing raw file for --phase3
  --config <file>               Config file (default: config/benchmark_config.yaml)

Validation and logging:
  --validate                    Enable result validation (default)
  --no-validate                 Skip result validation
  --quiet                       Suppress nonessential stdout
  --log-level <level>           ERROR|WARN|INFO|DEBUG (default: INFO)
  --output-format <fmt>         Override config output_format
  --save-options-file <path>    Write resolved CLI options to PATH

Information:
  --specification               Print this workload's specification and exit
  --matrix-definition           Same as --specification
  --help                        Show this help and exit

Examples:
  bash run_benchmark.sh --profile smoke --validate
  bash run_benchmark.sh --baseline --device gpu
  bash run_benchmark.sh --phase3 --raw-file results/raw/<run>/raw.txt
  bash run_benchmark.sh --matrix-definition
```

5. Use CLI default profile `smoke`. For LLM Serving, yaml `sweep.profile` remains `baseline`; pass `--baseline` to start the real model server.
6. Include `Expected environment overrides:` only when the runner accepts `--kernel-version`, `--driver-version`, `--rocm-version`, `--required-packages`, or `--permissions-check`. Those flags take values; they do not mean "enable this check."
7. Include `Workload options:` for every extra parsed flag. Omit the section when there are none.
8. Do not document `-h` unless the parser accepts it. Do not invent `--output-format` enumerations such as `json, text, csv` unless the workload validates those values.
9. `--raw-file` is an input for parse-only phase 3. It is not a custom path for writing new raw logs.

## Numbered metric-item requirement

When `benchmark_specification.json` contains a numbered `Metrics` value, each numbered item is a required end-of-run summary line printed after `bash run_benchmark.sh` completes. The generated harness must:

1. Parse the numbered items in source order.
2. Preserve each item's metric description verbatim in the summary line, including its number and units.
3. Append the measured aggregate value or values for that item from the latest validated run. A generic replacement such as "latency and bandwidth samples captured" is not compliant.
4. Emit exactly one `[INFO]` metric line per numbered item, between the empty `[INFO]` spacer lines in the fixed wrapper (after Artifacts and SQLite DB).
5. Ensure every value shown is present in the SQLite result schema and in `results/summary.json`; do not print values that were not measured and persisted.

For workload 112, the required five summary lines are:

```text
[INFO] #1: Syscall latency null/read/write/stat/open (nsec); <measured values>
[INFO] #2: Context-switch latency (μsec); <measured value>
[INFO] #3: Memory read latency vs working-set size (nsec); <measured values>
[INFO] #4: bw_mem memory bandwidth (MB/sec); <measured value>
[INFO] #5: bw_pipe IPC bandwidth (MB/sec); <measured value>
```

The angle-bracket text is replaced by real aggregate values; it must not be printed literally. If an item names multiple subtests or working-set points, the line must include a labeled value for each required subtest or point.
