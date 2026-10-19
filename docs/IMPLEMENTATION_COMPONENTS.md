# Implementation Components Architecture

## Goal

Keep `BenchmarkSpecDefinitions.xlsx` focused on **what** a workload must benchmark while keeping reusable implementation knowledge in `implementation_components/`. The workbook contains no `Implementation Components` column and the user does not select component IDs.

## Resolution Model

1. The workload row is extracted to `benchmark_specification.json`.
2. `scripts/resolve_implementation_components.py` enumerates `implementation_components/*/component.json`.
3. Every manifest declares semantic selectors using benchmark field names. All selectors must match for that component to apply.
4. Compatible components are validated for safe overlay paths and destination conflicts.
5. `scripts/init_generated_repo.py` copies each discovered component overlay into the generated workload repository.
6. If no component matches, the AI Coding Agent implements the workload normally from the benchmark specification and shared repository contracts.

Components are not keyed by workload number or repository name. This allows a capability to be reused by future workloads whose semantic requirements match.

## Manifest Contract

Each `component.json` contains:

- `component_id` — stable component identifier.
- `description` — human-readable purpose.
- `role` — `collector` | `parser` | `runner` | `source` | `build` | `mixin`.
- `completeness` — `thin` (collector only) or `closed` (collector plus build/source).
- `provides` / `does_not_provide` — ownership, including `rocblas-bench invocation` when the overlay does not run GEMM.
- `verifies` — Framework tools this overlay actually checks.
- `contracts` — `skip_rvs_default`, `compile_rocblas_bench`, `gemm_per_point`, `build_policy`, `forbidden_cli`.
- `also_applies_to` — documented workload numbers (101/301). A name match with a number outside this list is a warning.
- `selectors` — `{field, operator, value}`; operators are `equals`, `contains`, `in`, and `prefix`. Primary components require selectors. Mixins use `apply_when` instead.
- `overlay` — destination-relative files under the component's `files/` directory.

Primary collectors are discovered from workbook fields. Mixins (`harness-self-check`, `rocm-tool-verify-build`, `rocblas-clients-build`) apply afterward when `apply_when` matches and the destination is not already owned. `scripts/init_generated_repo.py` then writes `results/overlay_lock.json` and `results/component_resolution.json`. The lock records the SHA-256 of the copied overlay bytes. A later smoke-breaking repair updates the template source, the sibling file, and that digest together. `scripts/apply_component_gaps.py` fills `--seed-fixture`, `PyYAML`, and `thresholds:` from `gate.json`.

Smoke-check keys off resolved `contracts`, not `Framework` substrings. Framework remains install-and-verify. `gemm_per_point` is only for GEMM sweeps such as `rocblas-gemm-amd`, not `system-stress-amd`.

The benchmark specification remains authoritative. A component may supply implementation files, but it may not redefine workload identity, parameters, metrics, success criteria, or required behavior.

## Workload 124 Example

Workload 124 specifies `Workload Name = Stable Diffusion XL Inference Baseline` and `GPU Vendor = AMD`. The `sdxl-diffusers-amd` manifest declares those semantic selectors, so the resolver discovers it automatically. SDXL parameters, commands, metrics, software framework, and runtime constraints stay in `BenchmarkSpecDefinitions.xlsx`; only deterministic implementation files live in the component.

## Auditability

`results/generation_manifest.json` records `implementation_component_resolution`, `implementation_components_discovered`, and `implementation_component_reasons`. This preserves reproducibility without exposing component selection as a user-maintained spreadsheet field.
