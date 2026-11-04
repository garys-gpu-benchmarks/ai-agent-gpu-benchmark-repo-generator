#!/usr/bin/env bash
# File: scripts/remote/prefetch_runner.sh
# Description: Detached runner for host_prefetch.py (started by host_bootstrap.sh).
# Execution: setsid nohup bash prefetch_runner.sh <state-dir> <python3> <spec> ...
set -uo pipefail
STATE="$1"; PY="$2"; shift 2
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -x "${STATE}/prefetch-venv/bin/python" ]]; then
  "${PY}" -m venv "${STATE}/prefetch-venv" || { echo "[WARN] could not create the prefetch venv"; exit 0; }
fi
"${STATE}/prefetch-venv/bin/python" -m pip install --quiet --upgrade huggingface_hub || echo "[WARN] pip install huggingface_hub failed"
export HF_HOME="${HF_HOME:-${HOME}/.cache/huggingface}"
export HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"
export HF_HUB_DOWNLOAD_TIMEOUT="${HF_HUB_DOWNLOAD_TIMEOUT:-60}"
# Lowest CPU and I/O priority: the foreground workload being validated comes first.
PREFIX=()
command -v nice >/dev/null 2>&1 && PREFIX+=(nice -n 19)
command -v ionice >/dev/null 2>&1 && PREFIX+=(ionice -c3)
exec "${PREFIX[@]}" "${STATE}/prefetch-venv/bin/python" "${HERE}/host_prefetch.py" --state-dir "${STATE}" "$@"
