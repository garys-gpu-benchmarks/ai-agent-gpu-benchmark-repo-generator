<!--
====================================================================
AGENT INSTRUCTIONS — DELETE THIS BLOCK FROM THE FINAL OUTPUT
====================================================================
You are generating SPEC.md from this template.

INPUTS:
  1. This file (SPEC_TEMPLATE.md)
  2. benchmark_specification.json — an array of {field_name, source_file, value}
  3. AGENTS.md — for the canonical SQLite schema rules, raw-output parsing
     rules, and Execution-Loop Validation Contract (this template's validation section
     must stay consistent with AGENTS.md; do not contradict it)

RULES:
  A. Every token of the form {{Field Name}} must be replaced with the exact
     `value` from the JSON object whose `field_name` matches it verbatim
     (case-sensitive, exact string match). The matching field_name values
     for this template are exactly:
       - "Execution Description With Parameters"
       - "Parameter_01" through "Parameter_20"
       - "Metrics"
       - "Framework"
       - "Runtime Language"
       - "Workload Command Line Executable"
       - "Installation and Execution Summary""
       - "AMD nVidia Applicable"
       - "nVidia Porting Instructions (Reference Only)"
       - "Model Context Protocols"
     Do not fuzzy-match or guess at a field_name. If no JSON object has a
     field_name that matches exactly, leave the token unresolved and flag
     it rather than substituting a different field's value.
  B. Parameter_01..20 are frequently sparse — many benchmarks use far
     fewer than 20 parameters. Skip any Parameter_NN whose JSON value is
     "—": omit its row from the Parameters table entirely
     (do not render empty rows, do not renumber the remaining ones).
  C. Every block of the form [[GENERATE: ...]] is NOT a literal JSON
     field. Derive its content using the JSON fields referenced in that
     instruction. Do not invent values that contradict
     Execution Description With Parameters, Installation and Execution Summary, or
     Metrics. Where a concrete default/flag/value isn't stated in
     the source fields, write "TBD — confirm against tool documentation"
     rather than fabricating a plausible-looking number.
  D. Preserve section order exactly as listed. Do not add, remove, or
     reorder top-level sections.
  E. The "Execution-Loop Validation Contract" section is fixed boilerplate and
     must be copied verbatim except for the two [[GENERATE]] sub-blocks
     explicitly marked within it (test file list, integrity-check list).
     It must remain consistent with AGENTS.md's "Execution-Loop Validation
     Contract" and "Canonical SQLite Schema" sections — do not invent a
     different fixture set, table name, or column-naming convention.
  F. Output raw Markdown only — no commentary, no surrounding prose, no
     code fences wrapping the whole document.
====================================================================
-->

# SPEC.md: "The Human How"; Exact technical requirements, environment setup, implementation details, etc.


## Execution Description

[[GENERATE: 2–4 sentences derived from {{Execution Description With Parameters}}. State what is run, the core formula/operation if one is given, and the sweep dimensions (which non-empty Parameter_NN values are varied vs. held fixed) — without yet re-listing every parameter individually; that detail belongs in the Parameters table below.]]


## Parameters

[[GENERATE: A Markdown table with columns
| Parameter | CLI Flag | Tested Values | Default | Description |
with exactly one row per non-empty Parameter_01..Parameter_20 value, in that order. Parameter name = the JSON value verbatim. CLI Flag is `--` plus the parameter name with underscores changed to hyphens. Tested Values and Default must come from `Profile Parameter Values` (smoke / baseline / extended). Do not invent numbers. If a profile value is a comma/semicolon sweep list, say that the command-column flags are documentary and yaml expands the cases. Description = a one-line explanation, consistent with how that parameter is described (if at all) in Execution Description With Parameters.]]

[[GENERATE — OPTIONAL, only if this is a matrix/tensor-shape workload (i.e. parameters include dimension-like names such as M/N/K, rows/cols, or similar): a "Stride values" or equivalent derived-quantities subsection, following the same pattern as the GEMM example — formula plus one worked numeric example using a tested value from the Parameters table. Omit this subsection entirely for non-matrix workloads (e.g. LLM serving, network, storage benchmarks).]]


## Invocation

[[GENERATE: The exact command line or API/script invocation used by run_benchmark.sh for one sweep point, as a fenced bash (or appropriate language) code block. Build it from the CLI Flag column above and any flags explicitly named in Installation and Execution Summary (e.g. a required correctness flag). Follow with one sentence noting any flag whose omission would silently degrade results (e.g. produce NULL output columns), only if such a flag is identifiable from the source fields — otherwise omit this closing sentence rather than inventing a caveat.]]


## Raw Output Format

[[GENERATE — OPTIONAL: only include this section if the benchmark tool emits parseable stdout/CSV output, as implied by Installation and Execution Summary (e.g. "parse stdout", "structured CSV"). If so, describe: the header/column layout if inferable, the unit of each output field, and any column-name aliasing the parser must tolerate across tool versions — consistent with AGENTS.md's "Raw Output Parsing Rules". Use the `Raw Output Example` field from `benchmark_specification.json` as the primary reference for actual column names, header row format, and representative values; use the `Raw Output Format` field for parsing rules, unit definitions, and success/failure indicators. If the benchmark's output mechanism isn't a parseable CLI tool (e.g. it queries an HTTP server, a Python client object, or a structured log), describe that mechanism instead under this same heading rather than omitting it silently.]]


## Metrics

[[GENERATE: A numbered list, one entry per item in {{Metrics}} (items are typically delimited by "#N)" markers in the source value — preserve that numbering). For each: **metric name** — one-line description — the derivation/formula if stated in `Raw Output Format` or `Raw Output Example` or Installation and Execution Summary — the column name it is stored as in `samples` (and, if it is a peak/aggregate value, its corresponding column in `runs`), following AGENTS.md's "Canonical SQLite Schema" naming conventions (e.g. `latency_ms`, `tokens_per_s`, `gb_per_s`, `error_norm`).]]


## Framework

[[GENERATE: A two-column Markdown table (Component | Role) parsed from the comma-separated {{Framework}} value — one row per component, with a brief role description inferred from Execution Description With Parameters / Installation and Execution Summary (e.g. "GPU runtime", "sweep orchestration", "output parsing"). Do not omit any component listed in the source field.]]


## Installation and Execution Summary

{{Installation and Execution Summary}}


## Platform Portability

- **AMD (primary):** [[GENERATE: one line stating the target GFX architecture, ROCm version, and primary library/tool version, drawn from the benchmark's hardware/software context as established elsewhere in this document (Framework, Invocation). If {{AMD nVidia Applicable}} indicates AMD-only, state that explicitly here instead of providing a portability line.]]
- **NVIDIA:** {{nVidia Porting Instructions (Reference Only)}}


## Model Context Protocols

- **Active:** {{Model Context Protocols}}


## Execution-Loop Validation Contract

EXECUTION CHAIN: `run_benchmark.sh` ➔ raw output ➔ `scripts/parse_results.py` ➔ `results/benchmark.db` ➔ `scripts/validate_results.py`

This benchmark uses a lightweight, SQLite-integrated execution loop for result validation. All validation is performed by `scripts/validate_results.py`.

### Validation script usage

```bash
export BENCHMARK_PYTHON=/usr/bin/python3.13  # optional; select the installed interpreter

# After a live run:
".venv/bin/python" scripts/validate_results.py --db results/benchmark.db

# CI / no-GPU path (seeds fixture and validates it):
".venv/bin/python" scripts/validate_results.py --seed-fixture --quiet

# Override DB path via environment variable:
BENCHMARK_DB=tests/fixtures/benchmark.db \
  ".venv/bin/python" scripts/validate_results.py
```

### Run artifact contract

[[GENERATE: Describe the per-run artifact directory naming contract: `results/raw/YYYYMMDD_HHMMSSZ_WORKLOAD-<NNN>_SYSTEM-<hostname>/` (UTC timestamp, `<NNN>` = zero-padded workload number). List required artifacts generated by `run_benchmark.sh`: `run.log` (full transcript with ANSI stripped in file), `commands_executed.sh` (replayable command log), masked `env_variables.txt`, `journal_warnings.txt` (`journalctl -p warning`, run-window scoped), `script.sh` (executed harness copy), raw output text, dual raw exports (`raw_results.csv`, `raw_results.jsonl`), per-run samples CSV/JSON exports, and Excel-sourced `hardware_info.txt`, `software_info.txt`, and `errors_info.txt` in that same per-run directory. Do not write `system_info.txt`.]]

[[GENERATE: Document that `bash run_benchmark.sh --help` prints the `usage()` page and exits before setup, and that `bash run_benchmark.sh --specification` prints this workload's `benchmark_specification.json` field/value table and exits before setup. Profiles are `--smoke`, `--baseline`, and `--extended`. A run always creates its own raw file and then collects, parses, and validates.]]

### Required integrity checks (built into `validate_results.py`)

1. Latest run exists and `runs.status = 'ok'`.
2. `run.error_message` is NULL.
3. `started_at` and `finished_at` are valid ISO-8601 UTC strings.
4. All required aggregate metrics in `runs` are non-NULL and finite.
5. All required aggregate metrics are physically sensible (positive values). [[GENERATE: one line naming the specific per-sample columns (derived from Metrics above) that must be finite/positive for every row, e.g. "Per-sample `tflops`, `exec_time_ms`, and `bandwidth_gb_s` are positive for every row."]]
6. At least 2 sample rows exist for the latest `run_id` (sweep coverage).
7. No sample has `status = 'error'`.
8. [[GENERATE: Include this check only if `dtype` is a swept parameter in `benchmark_specification.json`. If present: "`dtype` is a known precision token (`f16_r`, `bf16_r`, `f32_r`, `f64_r`, etc.)." Otherwise omit this line entirely.]]

### Baseline / Threshold configuration (`config/benchmark_config.yaml`)

[[GENERATE: If the workload is measurement-only, provide a fenced YAML block under a `baselines:` key with expected ranges for metrics where a defensible reference exists. If the workload defines correctness, compliance, health, or explicit pass/fail gates, provide a fenced YAML block under a `thresholds:` key with one entry per gated metric. Threshold key names must use `_min` / `_max` suffixes per AGENTS.md convention. Each baseline or threshold value must cite its derivation basis in a trailing YAML comment (e.g. "# ~54% of <hardware> <dtype> peak <value>"). Where no numeric basis is available from the source fields, write a placeholder value with a comment "# TBD — no published reference provided" instead of fabricating a number.]]

Threshold key suffixes encode comparison direction when `thresholds:` is present: `_min` → observed value must be ≥ threshold. `_max` → observed value must be ≤ threshold. Informational `baselines:` ranges are not pass/fail gates.
