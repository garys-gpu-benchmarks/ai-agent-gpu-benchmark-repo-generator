# Machine-Checkable Contracts

Template release: `Project37_TEMPLATE_0_02_20260706a`

This template uses schema-backed contracts to reduce ambiguity and prevent creative reinterpretation by AI agents.

In template mode, validate the extracted Phase 0 `benchmark_specification.json` at `<template-directory>/`, then validate the generation manifest inside the generated repository subdirectory named `<Workload Number>-<Repo Base Name>` at project root (`../<WORKLOAD_NUMBER>-<REPO_NAME>/` when invoked from `<template-directory>/`).

## Contract Files

- `schemas/benchmark_specification.schema.json`
- `schemas/generation_report.schema.json`

## Validator

Use `scripts/validate_template_inputs.py`.

### Validate benchmark definition (Phase 0 gate)

```bash
python3 scripts/validate_template_inputs.py \
  --benchmark-specification benchmark_specification.json \
  --benchmark-schema schemas/benchmark_specification.schema.json
```

### Validate generation manifest (pre-completion gate)

```bash
python3 scripts/validate_template_inputs.py \
  --generation-manifest <REPO_NAME>/results/generation_manifest.json \
  --generation-schema schemas/generation_report.schema.json
```

## Required Generation Manifest

Every generated workload repository must include:

- `<REPO_NAME>/results/generation_manifest.json`

Minimum required fields:

- `source_template_commit`
- `workload_id`
- `workload_name`
- `generated_at`
- `generation_started_at`
- `generation_finished_at`
- `generation_duration_seconds`

This enables deterministic traceability back to the template revision and generation run metadata. `generation_started_at` is captured before Phase 0, `generation_finished_at` is captured only after final verification, and `generation_duration_seconds` is the non-negative wall-clock duration between those events.

## CPU/System Baseline Default Contract

For workloads where `Execution Domain` is `CPU / System` and `Workload Type` is `Benchmark`, generated repositories should default to a `baselines:` block in `config/benchmark_config.yaml`.

Rules:

1. Do not invent pass/fail thresholds unless `benchmark_specification.json` explicitly defines correctness/compliance gates.
2. If no published or hardware-derived numeric references are provided, include placeholder baseline ranges with explicit YAML comments indicating `TBD — no published reference provided`.
3. `scripts/validate_results.py` must remain resilient when `thresholds:` is absent.

## Result Interpretation Notes

Generated repositories should document these validation semantics so operators do not misclassify successful runs:

1. `duration_sec=0` can be valid for very short runs when start/finish timestamps are rounded to whole seconds in summary output.
2. Per-sample compliance values may be `0.0` for non-applicable checks in mixed validation workloads; aggregate compliance and threshold checks are the required gating signals.
