#!/usr/bin/env bash
# File: scripts/ensure_setup.sh
# Description: Setup-on-demand guard for AMD SGLang run_benchmark.sh.
# Execution: bash scripts/ensure_setup.sh [--profile smoke|baseline|extended]
# Note: Reboot-driven setup must finish after reboot before run_benchmark.sh is rerun.
# Every profile starts the real SGLang server, so every profile re-runs setup
# when import sglang, import aiter, or launch_server --help fails.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

PROFILE="${BENCHMARK_PROFILE:-}"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --profile) PROFILE="${2:-}"; shift 2 ;;
        --smoke) PROFILE="smoke"; shift ;;
        --baseline) PROFILE="baseline"; shift ;;
        --extended) PROFILE="extended"; shift ;;
        *) shift ;;
    esac
done
PROFILE="${PROFILE:-smoke}"

if [[ -f .setup_state ]]; then
    if [[ ! -x "${REPO_ROOT}/.venv/bin/python" ]]; then
        printf '[WARN] .setup_state exists but .venv python is missing; re-running setup.\n'
        rm -f .setup_state
    elif ! "${REPO_ROOT}/.venv/bin/python" -c "import sglang" >/dev/null 2>&1; then
        printf '[WARN] .setup_state exists but sglang import failed; re-running setup.\n'
        rm -f .setup_state
    elif ! "${REPO_ROOT}/.venv/bin/python" -c "import aiter" >/dev/null 2>&1; then
        printf '[WARN] .setup_state exists but aiter import failed; re-running setup.\n'
        rm -f .setup_state
    elif ! "${REPO_ROOT}/.venv/bin/python" -m sglang.launch_server --help >/dev/null 2>&1; then
        printf '[WARN] .setup_state exists but sglang.launch_server --help failed; re-running setup.\n'
        rm -f .setup_state
    elif ! "${REPO_ROOT}/.venv/bin/python" -c "from sglang.srt.entrypoints.http_server import launch_server" >/dev/null 2>&1; then
        printf '[WARN] .setup_state exists but http_server.launch_server import failed; re-running setup.\n'
        rm -f .setup_state
    else
        printf '[PASS] Setup already complete: %s\n' "${REPO_ROOT}"
        exit 0
    fi
fi

[[ -f setup.sh ]] || {
    printf '[ERROR] setup.sh is missing; cannot start automatic setup.\n' >&2
    exit 1
}

if [[ -f "${REPO_ROOT}/scripts/lib/disk_space.sh" ]]; then
    # shellcheck disable=SC1091
    source "${REPO_ROOT}/scripts/lib/disk_space.sh"
    if reuse_completed_venv; then
        printf '[PASS] Setup already complete via reused install: %s\n' "${REPO_ROOT}"
        if [[ -f "${REPO_ROOT}/scripts/lib/nvcc_glibc_throw.sh" ]]; then
            # shellcheck disable=SC1091
            source "${REPO_ROOT}/scripts/lib/nvcc_glibc_throw.sh"
            nvcc_recheck_for_run
        fi
        exit 0
    fi
    require_free_kib "${REPO_ROOT}" $((20 * 1024 * 1024)) \
        "Automatic setup needs 20 GiB free before it creates a virtual environment."
fi

printf '[INFO] .setup_state is absent; starting automatic setup.\n'
setup_args=()
if grep -Fq -- "--assume-yes" setup.sh; then
    setup_args+=(--assume-yes)
fi

if ! bash setup.sh "${setup_args[@]}"; then
    printf '[ERROR] Automatic setup failed; benchmark will not run.\n' >&2
    exit 1
fi

if [[ ! -f .setup_state ]]; then
    if command -v systemctl >/dev/null 2>&1 &&
       systemctl list-unit-files --type=service --no-legend 2>/dev/null |
       grep -Eq '[^[:space:]]+-setup-resume\.service'; then
        printf '[WARN] Setup is awaiting reboot-resume completion. Rerun bash run_benchmark.sh after setup completes.\n' >&2
    else
        printf '[ERROR] setup.sh returned successfully without creating .setup_state; benchmark will not run.\n' >&2
    fi
    exit 1
fi

printf '[PASS] Automatic setup completed: %s\n' "${REPO_ROOT}"
