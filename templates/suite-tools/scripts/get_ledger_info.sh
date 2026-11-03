#!/usr/bin/env bash
# ==============================================================================
# get_ledger_info.sh
#
# Collects benchmark results from one remote benchmark machine (any of the four
# platforms) into the current folder, OR from the local machine when no host
# is given:
#
#   RUNTIME_LEDGERS/runtime_ledger_<first>_<last>_<time>.csv  (and .xlsx)
#   DIRECTORIES/<workload>/results/raw/...
#   DIRECTORIES/<workload>/results/parsed/...
#   DIRECTORIES/<workload>/results/runtime_ledger_<first>_<last>_<time>.csv
#   DIRECTORIES/benchmark_suite_log/...         (run_benchmark_suite.sh logs)
#
# When a host is given, everything comes over ONE ssh connection as ONE
# compressed tar stream. When no host is given, the same collection runs
# locally against --remote-root (default /opt/benchmarks).
# Workloads and the ledger are found automatically; nothing is hard-coded
# per platform.
#
# Usage:   ./get_ledger_info.sh --host HOST [--port PORT] [options]
#          ./get_ledger_info.sh [options] HOST [PORT]      (same, positional)
#          ./get_ledger_info.sh [options]                  (local mode)
# Help:    ./get_ledger_info.sh --help
#
# Exit codes:
#   0  results collected
#   1  connection or transfer failed
#   2  usage error
# ==============================================================================

set -uo pipefail

readonly SCRIPT_NAME="${0##*/}"
readonly LEDGER_CANDIDATES=(/var/opt/benchmarks/runtime_ledger.csv /opt/benchmarks/runtime_ledger.csv)

# ------------------------------------------------------------------------------
# Defaults (each can be changed with an option)
# ------------------------------------------------------------------------------
remote_user="root"
remote_host=""
remote_port="22"
ssh_key=""
out_dir="."
remote_root="/opt/benchmarks"
remote_ledger=""
make_xlsx=true
local_mode=false

declare -a ssh_cmd=()
timestamp="$(date '+%Y%m%d_%H%M%S')"

usage() {
  cat <<EOF
Usage: ${SCRIPT_NAME} --host HOST [--port PORT] [options]
       ${SCRIPT_NAME} [options] HOST [PORT]
       ${SCRIPT_NAME} [options]                          # local mode (no host)

Copies from the benchmark machine HOST (ssh port PORT, default 22), or from
the local machine when no host is given:
  - the runtime ledger, saved as a timestamped CSV (and an Excel copy)
  - every workload's results/raw and results/parsed folders
  - run_benchmark_suite.sh logs
into RUNTIME_LEDGERS/ and DIRECTORIES/ under the output folder.

Connection (ignored in local mode):
      --host HOST       Benchmark machine: IP address or name, optionally
                        with a user (user@host). HOST may instead be given
                        as the first argument. Omit for local collection.
  -p, --port PORT       SSH port, 1-65535. Default: 22. PORT may instead be
                        given as the second argument.
      --user USER       Remote user. Default: the user in user@host, else root.
  -i, --identity KEY    SSH private key to use. Default: try your ssh
                        defaults, then each private key in ~/.ssh.

Output:
  -o, --output DIR      Output folder. Default: the current folder.
  -r, --remote-root DIR Folder holding the workloads on the remote (or local)
                        machine. Default: /opt/benchmarks
  -l, --ledger FILE     Ledger path on the remote (or local) machine.
                        Default: the first that exists of
                        ${LEDGER_CANDIDATES[*]}
      --no-xlsx         Do not create the Excel (.xlsx) copy of the ledger.
  -h, --help            Show this help.

Options that take a value also accept --option=VALUE.

Examples:
  ./${SCRIPT_NAME} --host 203.0.113.10                     # GPU VM, port 22
  ./${SCRIPT_NAME} --host 203.0.113.20 --port 13178        # cloud pod on port 13178
  ./${SCRIPT_NAME} --host ubuntu@203.0.113.30 -i ~/.ssh/id_ed25519 -o ~/results
  ./${SCRIPT_NAME} 203.0.113.20 13178                      # positional form
  ./${SCRIPT_NAME}                                         # collect locally from /opt/benchmarks
  ./${SCRIPT_NAME} -r /opt/benchmarks -o ~/local-results   # local, custom paths
EOF
}

die_usage() {
  echo "${SCRIPT_NAME}: $*" >&2
  echo "Try '${SCRIPT_NAME} --help'." >&2
  exit 2
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

# Fails with a usage error unless option $1 is followed by a value.
need_value() {
  [[ $# -ge 2 && -n "$2" && "$2" != -* ]] || die_usage "$1 needs a value"
}

parse_args() {
  local -a positional=()
  local host_opt="" port_opt="" user_opt=""
  while (($# > 0)); do
    case "$1" in
      # --option=VALUE is split into --option VALUE.
      --host=* | --port=* | --user=* | --identity=* | --output=* | --remote-root=* | --ledger=*)
        set -- "${1%%=*}" "${1#*=}" "${@:2}"
        continue ;;
      --no-xlsx=* | --help=*) die_usage "${1%%=*} takes no value" ;;
      --host)             need_value "$@"; host_opt=$2; shift 2 ;;
      -p | --port)        need_value "$@"; port_opt=$2; shift 2 ;;
      --user)             need_value "$@"; user_opt=$2; shift 2 ;;
      -i | --identity)    need_value "$@"; ssh_key=$2; shift 2 ;;
      -o | --output)      need_value "$@"; out_dir=$2; shift 2 ;;
      -r | --remote-root) need_value "$@"; remote_root=$2; shift 2 ;;
      -l | --ledger)      need_value "$@"; remote_ledger=$2; shift 2 ;;
      --no-xlsx)          make_xlsx=false; shift ;;
      -h | --help)        usage; exit 0 ;;
      --)                 shift; positional+=("$@"); break ;;
      -*)                 die_usage "unknown option: $1" ;;
      *)                  positional+=("$1"); shift ;;
    esac
  done

  ((${#positional[@]} <= 2)) || die_usage "too many arguments: ${positional[*]}"
  local pos_host=${positional[0]:-} pos_port=${positional[1]:-}

  # The host and port can each be given once: as an option or as an argument.
  if [[ -n "${host_opt}" && -n "${pos_host}" && "${host_opt}" != "${pos_host}" ]]; then
    die_usage "the host is given twice (--host ${host_opt} and ${pos_host}); give it once"
  fi
  if [[ -n "${port_opt}" && -n "${pos_port}" && "${port_opt}" != "${pos_port}" ]]; then
    die_usage "the port is given twice (--port ${port_opt} and ${pos_port}); give it once"
  fi
  remote_host=${host_opt:-${pos_host}}
  remote_port=${port_opt:-${pos_port:-22}}

  # No host => local mode
  if [[ -z "${remote_host}" ]]; then
    local_mode=true
    remote_host="localhost"
    remote_user="${USER:-$(whoami)}"
  else
    local_mode=false
    if [[ "${remote_host}" == *@* ]]; then
      local host_user=${remote_host%@*}
      remote_host=${remote_host#*@}
      if [[ -n "${user_opt}" && "${user_opt}" != "${host_user}" ]]; then
        die_usage "the user is given twice (--user ${user_opt} and ${host_user}@); give it once"
      fi
      remote_user=${host_user}
    fi
    [[ -n "${user_opt}" ]] && remote_user=${user_opt}
    [[ -n "${remote_user}" ]] || die_usage "the user is empty"
    [[ -n "${remote_host}" ]] || die_usage "HOST is empty"
    [[ "${remote_host}" != *[[:space:]/]* ]] || die_usage "HOST is not an address or name: ${remote_host}"
  fi

  if ! [[ "${remote_port}" =~ ^[0-9]+$ ]] || ((10#${remote_port} < 1 || 10#${remote_port} > 65535)); then
    die_usage "PORT must be a number from 1 to 65535 (got: ${remote_port})"
  fi
  remote_port=$((10#${remote_port}))
  if [[ -n "${ssh_key}" && ! -f "${ssh_key}" ]]; then die_usage "--identity: no such file: ${ssh_key}"; fi
}

# Tries one ssh login without prompting. Extra arguments are ssh options.
# Leaves ssh's error text in $probe_error.
probe_error=""
try_login() {
  probe_error=$("${ssh_cmd[@]}" -o BatchMode=yes "$@" "${remote_user}@${remote_host}" true 2>&1 >/dev/null)
}

is_private_key() {
  [[ -f "$1" && "$1" != *.pub ]] && head -n 1 "$1" 2>/dev/null | grep -q 'PRIVATE KEY'
}

explain_ssh_error() {
  case "${probe_error}" in
    *"IDENTIFICATION HAS CHANGED"*)
      echo "The machine at ${remote_host} has a new host key (for example, it was reinstalled)." >&2
      echo "If you expected that, remove the old key and run this again:" >&2
      echo "  ssh-keygen -R '[${remote_host}]:${remote_port}'; ssh-keygen -R ${remote_host}" >&2 ;;
    *"Connection refused"* | *"timed out"* | *"No route"* | *"Could not resolve"*)
      echo "Cannot reach ${remote_host} on port ${remote_port}. Check the address, the port, and that the machine is running." >&2 ;;
    *"Permission denied"*)
      echo "No SSH key was accepted for ${remote_user}@${remote_host}. Give the right one with -i KEY." >&2 ;;
  esac
  [[ -n "${probe_error}" ]] && echo "ssh said: ${probe_error}" >&2
  return 0
}

connect() {
  [[ "${local_mode}" == true ]] && return 0
  ssh_cmd=(ssh -p "${remote_port}"
    -o ConnectTimeout=15 -o ServerAliveInterval=30 -o StrictHostKeyChecking=accept-new)

  echo "Connecting to ${remote_user}@${remote_host} (port ${remote_port})..."
  if [[ -n "${ssh_key}" ]]; then
    ssh_cmd+=(-i "${ssh_key}" -o IdentitiesOnly=yes)
    try_login || { explain_ssh_error; die "cannot 