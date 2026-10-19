# AI Agent Handoff

## Purpose

This document is the durable continuation context for future AI Coding Agents working on this repository.

The repository is an AI-agent-driven generator for complete AMD/ROCm GPU benchmark repositories.

The benchmark matrix workbook is the authoritative source for workload definitions.

The current implementation supports the existing AMD/ROCm generation path.

Live NVIDIA/CUDA/H100 support is intentionally deferred.

## Repository layout

- `README.md` contains the user-facing overview, quick-start process, and supported prompt forms.
- `AGENTS.md` contains the cross-agent operating contract and document priority rules.
- `.claude/CLAUDE.md` contains Claude-specific guidance that supplements `AGENTS.md`. Do not place `CLAUDE.md` at the repository root.
- `docs/AI_AGENT_INSTRUCTIONS.md` contains the authoritative generation instructions attached to an AI Coding Agent.
- `docs/generation-workflow.md` contains the five-phase generation workflow.
- `docs/ARCHITECTURE.md` contains the architecture and document map.
- `docs/TEMPLATE_README.md` contains maintainer-facing template guidance.
- `docs/CHANGELOG.md` contains release notes.
- `BenchmarkSpecDefinitions.xlsx` is the benchmark definition source of truth.
- `config/workload_parameters.yaml` is the generated shared-parameter catalog.
- `scripts/create_generated_repo.py` creates one generated repository.
- `scripts/create_generated_batch.py` is a legacy scaffold helper only; AI Coding Agent chatbox multi-workload generation must use sequential `create_generated_repo.py --workload <N>` instead.
- `scripts/prompt_workflow.py` centralizes prompt parsing and submitted-prompt artifact creation.
- `scripts/generate_workload_parameters.py` regenerates the shared parameter catalog.
- `scripts/verify_generation_workflow.py` runs deterministic prompt, catalog, and Markdown-link checks.
- `scripts/extract_benchmark_definition.py` extracts a workload row from the workbook.
- `scripts/validate_template_inputs.py` validates benchmark definitions and generation manifests.
- `scripts/init_generated_repo.py` initializes the generated repository scaffold.
- `scripts/test_nested_template_copy.sh` tests sibling output placement and nested template-copy behavior.
- `schemas/` contains JSON Schemas for benchmark definitions and generation reports.
- `implementation_components/` contains reusable capability-oriented implementation assets automatically discovered from the benchmark specification.

## Current generation workflow

The user opens the project root containing this template directory and submits a prompt directly to an AI Coding Agent.

The prompt attaches `ai-agent-gpu-benchmark-repo-generator/docs/AI_AGENT_INSTRUCTIONS.md`.

The supported workload forms include:

```text
Generate workload 101.
Generate workloads 101, 104, 108.
Generate workloads 101 and 104.
Generate workloads 101 through 104.
Generate workloads 101 to 104.
Generate workloads ALL.
```

The parser deduplicates and sorts workload numbers and validates them against the workbook.

The agent creates a traceability artifact in the parent project root, never inside the template directory:

```text
AI_AGENT_PROMPT_SUBMITTED_<WORKLOADS>_<UTC_TIMESTAMP>.md
```

Examples:

```text
AI_AGENT_PROMPT_SUBMITTED_101_20260805_080015.md
AI_AGENT_PROMPT_SUBMITTED_104to108_20260805_080015.md
AI_AGENT_PROMPT_SUBMITTED_ALL_20260805_080015.md
```

The artifact preserves the submitted prompt and appends an HTML-comment metadata block containing UTC creation time, workloads, template version, prompt path, and remote-validation status.

Existing artifacts are never overwritten.

Collisions receive a numeric suffix.

Private-key markers are rejected before an artifact is written.

Generated repositories remain siblings of the template directory:

```text
<project-root>/<WORKLOAD_NUMBER>_<Repo Name>/
```

The AI Coding Agent (ie, Cursor) project-root sibling is the created repository only. It is a sibling of `ai-agent-gpu-benchmark-repo-generator`. Develop the code in the local directory, and copy it to the remote VM for testing. After extract, set every directory under `/opt/benchmarks/<Workload Number>-<Repo Name>` to `0755` (`find … -type d -exec chmod 755 {} +`); a Windows `tar` copy is typically `0777` and shows lime green in `ls`. Do not copy anything from the VM back to the local directory, including `.venv/`, `.cache/`, or other setup/smoke runtime state.

Each generated repository holds a nested active template copy named `<template-name>_copy` during generation. It is removed once the workload passes (`scripts/create_one_workload.py`, or `scripts/remove_template_copy.py --repo-root <repo>`).

No generated repository may be created inside `ai-agent-gpu-benchmark-repo-generator/`.

## Remote validation behavior

An SSH command containing an IPv4 address in the prompt identifies a mandatory external validation target. For every workload, load the completed repository onto that VM, install it there, run its self-check, and run its smoke benchmark there before reporting completion. The generated repository remains local-runtime only.

It does not authorize a destructive VM rebuild.

The default behavior is validation without refresh.

Destructive refresh requires explicit user confirmation and the appropriate flags:

```bash
python3 scripts/create_generated_repo.py \
  --prompt-file <SUBMITTED_PROMPT_FILE> \
  --refresh-remote \
  --confirm-remote-refresh
```

For multi-workload generation, refresh is performed at most once before the first workload. Create each repository sequentially with:

```bash
python3 scripts/create_generated_repo.py \
  --prompt-file <SUBMITTED_PROMPT_FILE> \
  --workload <WORKLOAD_NUMBER>
```

Do not use `create_generated_batch.py` on the AI Coding Agent chatbox path. Finish checklist, local smoke, and remote smoke for the current workload before creating the next directory. On failure, abandon-by-judgment, or 60-minute timeout, notify the user, record the result in `batch_generation_manifest.json`, and continue. A user status question is not a stop signal: answer briefly and continue the current unfinished workload in the same turn. After a workload is recorded, immediately start the next remaining requested workload in the same turn.

The low-level refresh script also requires `--confirm`:

```bash
bash scripts/refresh_remote_vm.sh <REMOTE_IPV4> --confirm
```

Without refresh confirmation, use the supplied VM only for external validation.

Remote commands, IP addresses, credentials, and remote execution paths must never be written into generated repositories.

## Parameter catalog

`config/workload_parameters.yaml` is generated from `BenchmarkSpecDefinitions.xlsx::Workload_Definitions`.

It contains shared parameters used by at least two workloads, including descriptions, data types, units, valid ranges, workload usage, workload-specific overrides, CLI/config keys, interaction/precedence information, and constraints.

Regenerate the catalog with:

```bash
python3 scripts/generate_workload_parameters.py
```

Check that `config/workload_parameters.yaml` matches the workbook, without writing it:

```bash
python3 scripts/generate_workload_parameters.py --check
```

The generator also lists active workbook parameters that their workload's execution description does not name. The descriptions say what each workload's code actually does, and some leave out parameters the code does not use (107: "numactl is not used"), so these are a `[WARN]`. Add `--strict` to make them a failure. Unused `Parameter_NN` slots hold `-` and are not parameters.

The generator currently requires `openpyxl` and `PyYAML`.

## Important implementation details

`scripts/prompt_workflow.py` is the shared parser used by the single and batch generation paths.

The parser supports comma-separated lists, `and`, `ALL`, `through`, `to`, hyphen ranges, duplicate removal, sorting, invalid workload detection, and collision-safe artifact naming.

`create_generated_repo.py` can read the newest timestamped project-root artifact when `--prompt-file` is omitted.

Sequential multi-workload generation appends each finished workload to `batch_generation_manifest.json` as it completes.

After every requested workload directory is recorded, delete generation-time scratch from the local project root and the remote validation host home (`*_create_start_time.txt`, helper `.py`/`.sh` files, `batch_process*.log`, `*.stdout`). Keep the generated repositories, the submitted-prompt artifact, and the local `batch_generation_manifest.json`. Then remove the VM-root duplicate of that manifest and leftover helpers.

The batch manifest records the submitted prompt artifact, requested workloads, remote validation IP, whether refresh was requested, whether refresh was confirmed, refresh status, and per-workload results (`passed`, `failed`, `abandoned`, or `timed_out`).

`extract_benchmark_definition.py` adds compatibility aliases for the validator's stable fields when the workbook uses the newer command-oriented columns:

- `Command Execution Details and Purpose` → `Installation and Execution Summary`
- `Command Tools Executed` → `Workload Command Line Executable`

Do not remove these aliases without updating the validator, schema contracts, workbook, and regression tests together.

## Verification commands

Run the deterministic workflow checks from the repository root:

```bash
python3 scripts/verify_generation_workflow.py
python3 scripts/generate_workload_parameters.py --check
python3 -m py_compile scripts/*.py
bash -n scripts/*.sh
bash scripts/test_nested_template_copy.sh
```

The verification script checks prompt parsing, catalog freshness, and repository Markdown links.

The nested-copy test checks output placement, active template copying, non-forced overwrite refusal, and forced rerun behavior.

The repository has also been checked with the IDE linter; no linter errors were present at the time of this handoff.

## Completed recent changes

- Added `scripts/templates/run_benchmark_help_skeleton.sh` and a `usage()` contract so generated `run_benchmark.sh --help` prints grouped options and exits before setup. Existing workloads 101–132 were left unchanged.
- Added `scripts/print_benchmark_definition.py` and `bash run_benchmark.sh --matrix-definition` so a generated repository prints its extracted matrix row as a two-column field/value table and exits before setup.
- Reworked generation from a copy-and-edit prompt workflow to direct prompt submission.
- Added timestamped project-root prompt artifacts.
- Centralized workload prompt parsing.
- Added `ALL`, `to`, and duplicate/sorting support.
- Added collision-safe prompt artifact creation.
- Added private-key protection for prompt artifacts.
- Added explicit remote-refresh confirmation.
- Updated single and batch generation orchestration.
- Added remote action fields to the batch manifest and schema.
- Corrected parameter-catalog workbook column offsets.
- Added active-parameter description validation.
- Regenerated `config/workload_parameters.yaml`.
- Consolidated user prompt guidance into `README.md`.
- Removed `AI_AGENT_PROMPT_TEMPLATE.md`.
- Moved `AI_AGENT_INSTRUCTIONS.md` to `docs/AI_AGENT_INSTRUCTIONS.md`.
- Updated documentation, CI checks, test prompts, and internal references.
- Preserved sibling output layout and nested template-copy behavior.
- Kept NVIDIA/H100 implementation deferred.

## Rules for future changes

Do not edit the benchmark workbook-derived values casually.

When changing workbook columns or parameter names, update the extractor, catalog generator, validation logic, schemas, documentation, and tests together.

Do not create generated repositories inside the template directory.

Do not reintroduce a fixed-name `AI_AGENT_PROMPT_SUBMITTED.md` workflow.

Do not reintroduce `AI_AGENT_PROMPT_TEMPLATE.md` unless there is a clear new purpose that cannot be served by `README.md`.

Keep `docs/AI_AGENT_INSTRUCTIONS.md` authoritative and synchronized with the executable scripts and `docs/generation-workflow.md`.

Do not implement NVIDIA/CUDA/H100 functionality in this workstream unless the user explicitly starts a new NVIDIA implementation project.

Do not commit private keys, credentials, API tokens, remote secrets, or prompt artifacts containing secret material.

Do not create commits unless the user explicitly requests a commit.

## Suggested continuation prompt

When opening this repository in a new Cursor workspace, begin with:

```text
Read AGENTS.md, README.md, docs/AI_AGENT_HANDOFF.md, docs/AI_AGENT_INSTRUCTIONS.md, and docs/ARCHITECTURE.md. Treat docs/AI_AGENT_HANDOFF.md as the continuation context, verify the current files before making assumptions, and continue the user's requested work without reintroducing the removed copy-and-edit prompt workflow.
```
