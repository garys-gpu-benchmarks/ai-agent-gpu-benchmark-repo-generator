#!/usr/bin/env bash
# File: setup.sh
# Description: Compatibility wrapper. The setup script is now run_setup.sh (it
#   pairs with run_benchmark.sh); this file runs it with the same options so
#   older instructions, scripts and habits ("bash setup.sh --assume-yes") keep
#   working. It will be removed in a later release.
# Execution: bash setup.sh [OPTIONS]   (same as bash run_setup.sh [OPTIONS])
set -euo pipefail
echo "[INFO] setup.sh is now run_setup.sh; running run_setup.sh" >&2
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/run_setup.sh" "$@"
