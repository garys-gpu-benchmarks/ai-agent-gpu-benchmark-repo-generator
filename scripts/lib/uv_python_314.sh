#!/usr/bin/env bash
# File: scripts/lib/uv_python_314.sh
# Description: Install a uv-managed CPython 3.14 for benchmark virtualenvs.
#              Ubuntu 24.04 keeps its system Python 3.12 for apt and setup scripts.
#              Ubuntu 26.04 keeps its system Python 3.14 for apt and setup scripts.
#              Both use this same uv build inside each repository .venv.
# Execution: source scripts/lib/uv_python_314.sh && ensure_uv_python_314

ensure_uv_python_314() {
  export PATH="${HOME}/.local/bin:${PATH}"
  if ! command -v uv >/dev/null 2>&1; then
    command -v curl >/dev/null 2>&1 || return 1
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="${HOME}/.local/bin:${PATH}"
  fi
  command -v uv >/dev/null 2>&1 || return 1
  uv python install 3.14
  UV_PYTHON="$(uv python find 3.14)"
  [[ -n "${UV_PYTHON}" && -x "${UV_PYTHON}" ]] || return 1
  export UV_PYTHON
}
