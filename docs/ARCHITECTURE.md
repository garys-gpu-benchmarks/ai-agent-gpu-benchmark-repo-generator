# Architecture & Doc Map

This template ships a substantial documentation and contract set across `AGENTS.md` and `docs/`. That's deliberate — the rules are written to be machine-followed by an AI coding agent, not skimmed by a human once — but it means a first-time human reader needs a map. Start here.

## The core idea

One workload row in `BenchmarkSpecDefinitions.xlsx` becomes one generated benchmark repository. An AI coding agent does the generating, governed by a strict document read-order so that Claude, Copilot, Cursor, etc. all produce the same repository from the same workload row.

```
BenchmarkSpecDefinitions.xlsx
        │  (Phase 0: scripts/extract_benchmark_definition.py)
        ▼
benchmark_specification.json  ──────► single source of truth
        │
        │  (Phase 1-4: docs/generation-workflow.md)
        ▼
generated workload repository
  ├── docs/PRD.md / SPEC.md / README.md   (from *_TEMPLATE.md + benchmark_specification.json)
  ├── setup.sh / run_benchmark.sh    (ROCm install, reboot-resume, benchmark harness)
  ├── src/, tests/, config/
  └── results/                       (validated against schemas/generation_report.schema.json)
```

## Two execution contexts

This is the single most common point of confusion in the docs, so it gets its own section: there are two separate uses of "remote Ubuntu host" in this template, and they never overlap.

**Generation-time (agent-only, optional).** While an AI coding agent is generating and validating a workload repository — Phase 0 in `generation-workflow.md` — it may SSH into a remote Ubuntu/MI300X host to rebuild the environment, install ROCm, and smoke-test the output before handing it back to you. This is a development/debug tool for the agent. It is never part of the generated repository itself, and the SSH details used to reach that host are never written into generated files. See `../AGENTS.md` → "Remote Host Execution" and § 29.1.

**Runtime (end user, always local).** Once a repository is generated, you always run it the same way: `bash setup.sh` and `bash run_benchmark.sh`, executed locally on the Ubuntu target — never from Windows, never over SSH, never with a remote-mode flag. This template intentionally does not support deploying and orchestrating a finished repo from a remote host; that capability existed early in this template's history and was removed. `remote-execution-pattern.md` documents that removal and why generated harnesses must fail fast if legacy remote options are ever supplied.

If you're reading a doc that mentions SSH or a remote IP and aren't sure which context it's in, check whether the surrounding text is talking about *building* the repo (generation-time, agent-only) or *running* it (runtime, always local).

## Document priority order

An agent (and a human maintainer) should read these in order and treat a lower number as authoritative over a higher one on any conflict. This is the same table in `AGENTS.md` — reproduced here as the entry point.

| # | File | Role |
|---|---|---|
| 1 | `benchmark_specification.json` | Single source of truth for benchmark metadata. Created in Phase 0. |
| 1a | `implementation_components/<component-id>/component.json` and `files/` | Reusable implementation assets automatically matched to benchmark specification fields; cannot override the definition. |
| 2 | Directly submitted generation prompt (`docs/AI_AGENT_INSTRUCTIONS.md` plus workload request) and timestamped `AI_AGENT_PROMPT_SUBMITTED_<WORKLOADS>_<UTC_TIMESTAMP>.md` artifact | The input that kicks off generation and the traceability record created in the project root. |
| 3 | `AGENTS.md` | Cross-agent coding rules, schema, CI contract, MCP configuration. |
| 4 | `.claude/CLAUDE.md` | Claude-specific integration notes. |
| 5-7 | `templates/PRD_TEMPLATE.md`, `templates/SPEC_TEMPLATE.md`, `templates/README_TEMPLATE.md` | Source templates copied to the generated repo root. |
| 8 | Generated `docs/PRD.md` / `SPEC.md` / `README.md` | Context once they exist; never authoritative over their templates. |
| 9 | `docs/repository-template.md` | Canonical directory layout. |
| 10 | `docs/generation-workflow.md` | Authoritative Phase 0-4 workflow. |
| 11 | `docs/machine-checkable-contracts.md` | Schema contracts and validator usage. |
| 12 | `docs/host-prerequisite-contract.md` | Host package derivation/installation/verification. |
| 13 | `docs/run-output-contract.md` | Required end-of-run summary format and `run_benchmark.sh --help` `usage()` contract. |
| 14 | `docs/raw-output-parser-contract.md` | Required parser behavior for real tool output. |
| 15 | `docs/rocm-reboot-install-contract.md` | ROCm reboot + systemd auto-resume architecture. |
| 16 | `docs/rocm-pytorch-install-contract.md` | ROCm PyTorch wheel selection and verification. |
| 17 | `config/hardware_profile.*.yaml` | GPU chip specs for threshold/baseline derivation. |
| 18 | `docs/SUBMISSION_CHECKLIST.md` | Completion gate before reporting a generated repo done. |

Full text and conflict-resolution rules: [`AGENTS.md`](../AGENTS.md#document-priority-order).

## Where to look for...

- **"How do I generate a repo?"** → [`README.md`](../README.md) quickstart, then [`AI_AGENT_INSTRUCTIONS.md`](AI_AGENT_INSTRUCTIONS.md).
- **"Why does this doc mention SSH/remote IPs — is that allowed?"** → [Two execution contexts](#two-execution-contexts), above.
- **"What does the agent actually do, step by step?"** → [`generation-workflow.md`](generation-workflow.md).
- **"What must a generated repo contain?"** → [`repository-template.md`](repository-template.md).
- **"What's the JSON shape of `benchmark_specification.json`?"** → [`benchmark_specification.schema.json`](../schemas/benchmark_specification.schema.json).
- **"How does ROCm install survive a reboot?"** → [`rocm-reboot-install-contract.md`](rocm-reboot-install-contract.md) and [`reboot-resume-pattern.md`](reboot-resume-pattern.md).
- **"What changed between template versions?"** → [`TEMPLATE_README.md`](TEMPLATE_README.md).
- **"I want to contribute a change."** → [`CONTRIBUTING.md`](../.github/CONTRIBUTING.md).
