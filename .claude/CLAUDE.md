# CLAUDE.md: "The Claude How"; Claude-specific AI/developer instructions,
# repository conventions, guardrails, and related guidance.
Guidance for **Claude Code** when working inside this repository. This file defines *Claude-specific operational behavior* — things unique to how Claude reads, reasons, and decides in this repository.

This file lives at `.claude/CLAUDE.md`, not the repository root. Claude Code loads project instructions from either `./CLAUDE.md` or `./.claude/CLAUDE.md`. Do not recreate a root `CLAUDE.md`.

For coding standards, SQLite schema rules, raw output parsing rules, execution-loop validation contract, and CI workflow contract, see **AGENTS.md** — those rules apply identically to Claude and are not repeated here.

This file is generic across all `gpu-bench-*` / `sys-bench-*` benchmark repositories. Workload-specific details (tool/binary names, build steps, sweep parameters, raw output format, etc.) are never hardcoded here — they are always read from `benchmark_specification.json` for the repository Claude is currently working in.

---

## 1. Document Priority Order

The authoritative document priority order — including the conflict resolution rules and the complete ordered table — is defined in **`AGENTS.md` → "Document Priority Order"**. That section applies to all agents and is not duplicated here.

Claude-specific notes that supplement (but do not override) the shared order:

- **`.claude/CLAUDE.md` is priority 4**, immediately after `AGENTS.md`. It contains only Claude Code integration notes and does not override the shared operating contract.
- **`README.md` contains the supported workload prompt forms**, while **`docs/AI_AGENT_INSTRUCTIONS.md`** contains the full agent operating instructions. The five-phase generation workflow and contract gates are in **`docs/generation-workflow.md`** and **`docs/machine-checkable-contracts.md`**.
- **`docs/PRD.md` / `SPEC.md` / `README.md` (priority 8)** — when these generated outputs exist from a prior run, Claude may read them for already-populated benchmark context, but must never hand-edit around a template/JSON mismatch. Fix the mismatch at the template or `benchmark_specification.json` level instead. `PRD.md` is `docs/PRD.md`. `SPEC.md` stays at the repository root.
- If any document not listed in the AGENTS.md priority table appears in the repository (e.g., a one-off notes file), treat it as informational only — it cannot override any document in the priority table.

---

## 2. Claude-Specific Integration Notes

All shared generation, execution, protected-file, and verification rules are defined in `AGENTS.md` and apply to Claude Code without duplication here.

- Claude Code must follow the shared operating contract in `AGENTS.md`.
- The five-phase generation workflow and machine-checkable gates are defined in `docs/generation-workflow.md` and `docs/machine-checkable-contracts.md`.
- When generated outputs from a prior run exist, Claude may read them for context, but must resolve template or JSON mismatches at the authoritative source rather than hand-editing around them.
- Workload-specific tool names, build steps, sweep parameters, and output formats must be read from `benchmark_specification.json`; they must not be invented from this file.

Before reporting completion, Claude must execute the full `docs/SUBMISSION_CHECKLIST.md` in the order specified by `AGENTS.md`.
