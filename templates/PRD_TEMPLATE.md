<!--
====================================================================
AGENT INSTRUCTIONS — DELETE THIS BLOCK FROM THE FINAL OUTPUT
====================================================================
You are generating docs/PRD.md from this template. The output file is docs/PRD.md, not the repository root.

INPUTS:
  1. This file (PRD_TEMPLATE.md)
  2. benchmark_specification.json — an array of {field_name, source_file, value}

RULES:
  A. Every token of the form {{Field Name}} below must be replaced with the
     exact `value` from the JSON object whose `field_name` matches it
     verbatim (case-sensitive, exact string match, including punctuation
     and parentheses). The matching field_name values for this template
     are exactly:
       - "Workload Number"
       - "Workload Name"
       - "Execution Summary (Run and Measure)"
       - "Main Goal"
       - "Validation Objective"
       - "Workload Category"
     Do not fuzzy-match, reformat, or guess at a field_name. If no JSON
     object has a field_name that matches exactly, leave the placeholder
     token unresolved and flag it rather than substituting a different
     field's value.
  B. If a matched value is an empty string, replace with "—".
  C. The "Validation Requirement" and "Non-Functional Requirements"
     sections below are fixed boilerplate, identical across all
     benchmarks. Copy them verbatim — do not alter, regenerate, or
     omit any line in those sections.
  D. Preserve section order and headings exactly as listed. Do not add,
     remove, or reorder sections.
  E. Output raw Markdown only — no commentary, no surrounding prose, no
     code fences wrapping the whole document.
====================================================================
-->

# PRD.md:  "The Why"; Product requirements, benchmark metadata table, high-level requirements, etc.

Product Requirements Document

"The Why"; Product requirements, benchmark metadata table, high-level requirements, etc. Defines the benchmark goal, validation objective, test name, benchmark number, category, and high-level success criteria.

## Benchmark Matrix Document Metadata (via benchmark_specification.json)

This PRD.md section is populated from benchmark_specification.json, which is the structured source of benchmark-specific product requirements.

## Workload Number
{{Workload Number}}

## Workload Name
{{Workload Name}}

## Execution Summary (Run and Measure)
{{Execution Summary (Run and Measure)}}

## Main Goal
{{Main Goal}}

## Validation Objective
{{Validation Objective}}

## Workload Category
{{Workload Category}}


## Validation Requirement

The benchmark must include an automated SQLite-integrated validation layer that verifies persisted results from `results/benchmark.db`. Validation must confirm:

1. The benchmark run completed successfully with no tool errors.
2. Required samples and aggregate metrics were persisted for every swept shape.
3. Metrics are finite and physically sensible (positive, within plausible bounds).
4. Measured values satisfy configured thresholds when the workload defines pass/fail gates.
5. The benchmark fails validation when required data is missing, invalid, or outside bounds.


## Non-Functional Requirements

| Requirement | Target |
|---|---|
| Automation | Runs to completion without manual intervention after `bash run_benchmark.sh` |
| Idempotency | Re-running `run_benchmark.sh` appends a new run; never corrupts existing rows |
| Persistence | All metrics survive script exit; `results/benchmark.db` is the durable record |
