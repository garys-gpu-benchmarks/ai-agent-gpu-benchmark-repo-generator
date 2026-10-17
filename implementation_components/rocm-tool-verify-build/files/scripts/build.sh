#!/usr/bin/env bash
# File: scripts/build.sh
# Description: Verify required ROCm/system tools are on PATH. No repository source is compiled.
# Execution: bash scripts/build.sh
set -euo pipefail
export PATH="/opt/rocm/bin:${PATH}"
export LD_LIBRARY_PATH="/opt/rocm/lib:/opt/rocm/lib64:${LD_LIBRARY_PATH:-}"
missing=0
# ROCm 10.1 ships amd-smi. The older rocm-smi binary is not in the amdrocm packages.
for cmd in rocminfo amd-smi hipcc; do
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "[FAIL] required command not found: ${cmd}" >&2
    missing=1
  fi
done
if ! command -v rocm-smi >/dev/null 2>&1; then
  echo "[WARN] rocm-smi is not on PATH; continuing with amd-smi."
fi
if [[ "${missing}" -ne 0 ]]; then
  exit 1
fi
echo "[PASS] required ROCm tools are present"
