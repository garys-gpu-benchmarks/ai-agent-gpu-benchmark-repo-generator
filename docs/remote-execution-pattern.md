# Remote Execution Pattern (Deprecated)

This template has moved to local-only workload generation. Keep this file only as historical context; do not generate remote SSH execution paths from this pattern.

**Scope note:** this deprecation applies to the *generated repository's runtime* — a finished repo must never ship remote-mode flags or SSH-orchestrated execution paths (see rules below). It does not apply to an AI coding agent's own use of a remote host for generation-time development, debugging, and validation, which is a separate, still-current pattern documented in `docs/generation-workflow.md` (Phase 0) and `AGENTS.md` § 29.1. See `ARCHITECTURE.md` → "Two execution contexts" for the full distinction.

Use this local-only baseline instead:

```bash
#!/usr/bin/env bash
set -euo pipefail

EXEC_MODE="local"
echo "[INFO] Mode=${EXEC_MODE}"
bash run_benchmark.sh --smoke
```

Notes:

- Do not add remote mode flags (`--exec-mode=remote`, `--remote-ip`, `--ssh-key`).
- Do not persist SSH key/IP defaults in repository files.
- Keep reboot handling local using `scripts/lib/reboot_resume.sh`.
