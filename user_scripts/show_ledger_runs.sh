#!/usr/bin/env bash
# ==============================================================================
# show_ledger_runs.sh
#
# Prints one line per run recorded in the runtime ledger of a benchmark
# machine: workload, profile, runtime and exit code, under a header line.
# Nothing else goes to stdout (errors go to stderr), and it copies nothing. With --host it reads the ledger of
# that remote machine over ssh; without --host it reads this machine's ledger.
#
# To copy the ledger and every workload's results as well, use
# get_benchmark_results.sh (same options), which also prints this table.
#
# Usage:   ./show_ledger_runs.sh --host HOST [--port PORT] [options]   (remote)
#          ./show_ledger_runs.sh [options] HOST [PORT]   (remote, positional)
#          ./show_ledger_runs.sh [options]               (this machine)
# Help:    ./show_ledger_runs.sh --help
#
# Exit codes:
#   0  the table was printed
#   1  connection failed, or no ledger was found
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
local_mode=false
ledger_file=""
profile=""
failed_only=false

declare -a ssh_cmd=()
tmp_file=""
csv_file=""
# Remove the temporary copies of the ledger however the script ends.
trap 'rm -f "${tmp_file}" "${csv_file}"' EXIT

usage() {
  cat <<EOF
Usage: ${SCRIPT_NAME} --host HOST [--port PORT] [options]    remote machine
       ${SCRIPT_NAME} [options] HOST [PORT]                 remote machine
       ${SCRIPT_NAME} [options]                             this machine

Prints every run in the runtime ledger, one line each (workload, profile,
runtime, exit code), under a header line. Nothing is copied; to copy the
ledger and the results as well, use get_benchmark_results.sh.

Connection (remote machine only):
      --host HOST       Benchmark machine: IP address or name, optionally
                        with a user (user@host). HOST may instead be given
                        as the first argument. Leave it out to read this
                        machine's ledger.
  -p, --port PORT       SSH port, 1-65535. Default: 22. PORT may instead be
                        given as the second argument.
      --user USER       Remote user. Default: the user in user@host, else root.
  -i, --identity KEY    SSH private key to use. Default: try your ssh
                        defaults, then each private key in ~/.ssh.

Which runs:
  --smoke | --baseline | --extended
                        Only runs of that profile. Default: every profile.
  --profile NAME        Same as above, for any profile name.
  --failed              Only runs whose exit code is not 0.

Ledger:
  -l, --file FILE       Ledger CSV path (on the remote machine with --host).
                        Default: the first that exists of
                        ${LEDGER_CANDIDATES[*]}
                        Also reads a copy saved by get_benchmark_results.sh,
                        e.g. RUNTIME_LEDGERS/runtime_ledger_101_132_<time>.csv
  -h, --help            Show this help.

Options that take a value also accept --option=VALUE.

Examples:
  ./${SCRIPT_NAME}                                         # this machine
  ./${SCRIPT_NAME} --failed                                # this machine, failed runs only
  ./${SCRIPT_NAME} --host 203.0.113.10                     # GPU VM, port 22
  ./${SCRIPT_NAME} --host 203.0.113.20 --port 13178 --baseline
  ./${SCRIPT_NAME} --file RUNTIME_LEDGERS/runtime_ledger_101_132_<time>.csv
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
      --host=* | --port=* | --user=* | --identity=* | --file=* | --profile=*)
        set -- "${1%%=*}" "${1#*=}" "${@:2}"
        continue ;;
      --failed=* | --help=* | --smoke=* | --baseline=* | --extended=*) die_usage "${1%%=*} takes no value" ;;
      --host)             need_value "$@"; host_opt=$2; shift 2 ;;
      -p | --port)        need_value "$@"; port_opt=$2; shift 2 ;;
      --user)             need_value "$@"; user_opt=$2; shift 2 ;;
      -i | --identity)    need_value "$@"; ssh_key=$2; shift 2 ;;
      -l | --file)        need_value "$@"; ledger_file=$2; shift 2 ;;
      --smoke | --baseline | --extended)
        [[ -z "${profile}" || "${profile}" == "${1#--}" ]] || die_usage "give one profile (got ${profile} and ${1#--})"
        profile=${1#--}; shift ;;
      --profile)
        need_value "$@"
        [[ -z "${profile}" || "${profile}" == "$2" ]] || die_usage "give one profile (got ${profile} and $2)"
        profile=$2; shift 2 ;;
      --failed)           failed_only=true; shift ;;
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
  if [[ -z "${remote_host}" ]]; then
    # No host: read this machine's ledger. Connection options without a host
    # usually mean --host was forgotten, so say so instead of ignoring them.
    [[ -z "${port_opt}" ]] || die_usage "--port needs --host HOST (without --host, this machine's ledger is read)"
    [[ -z "${user_opt}" ]] || die_usage "--user needs --host HOST (without --host, this machine's ledger is read)"
    [[ -z "${ssh_key}" ]] || die_usage "--identity needs --host HOST (without --host, this machine's ledger is read)"
    local_mode=true
    return 0
  fi

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

# Same login order as get_benchmark_results.sh: the given key, then your ssh
# defaults, then each private key in ~/.ssh. It prints nothing unless the
# login fails, so stdout is only the table.
connect() {
  ssh_cmd=(ssh -p "${remote_port}"
    -o ConnectTimeout=15 -o ServerAliveInterval=30 -o StrictHostKeyChecking=accept-new)

  if [[ -n "${ssh_key}" ]]; then
    ssh_cmd+=(-i "${ssh_key}" -o IdentitiesOnly=yes)
    try_login || { explain_ssh_error; die "cannot log in with ${ssh_key}"; }
    return
  fi
  if try_login; then
    return
  fi
  [[ "${probe_error}" == *"Permission denied"* ]] || { explain_ssh_error; die "cannot connect"; }

  local key
  for key in "${HOME}"/.ssh/*; do
    is_private_key "${key}" || continue
    if try_login -i "${key}" -o IdentitiesOnly=yes; then
      ssh_cmd+=(-i "${key}" -o IdentitiesOnly=yes)
      return
    fi
  done
  explain_ssh_error
  die "none of the keys in ${HOME}/.ssh were accepted"
}

# Runs on the benchmark machine (over ssh, or locally). Prints the ledger path
# on the first line, then the ledger. Arguments: ledger path ('' = search),
# then the default candidates. Exit 3 when no ledger is found.
read -r -d '' FIND_LEDGER <<'FIND'
ledger=$1
shift
if [ -z "${ledger}" ]; then
  for candidate in "$@"; do
    if [ -f "${candidate}" ]; then ledger=${candidate}; break; fi
  done
fi
if [ -z "${ledger}" ] || [ ! -f "${ledger}" ]; then
  echo "${ledger:-$*}"
  exit 3
fi
echo "${ledger}"
cat "${ledger}"
FIND

# Prints the header line and, for every ledger row that matches --profile and
# --failed, workload, profile, runtime and exit code: ledger fields 4 (workload
# path, shown without its folder), 5, 7 and 8. Same columns and widths as the
# table get_benchmark_results.sh prints.
show_runs() {
  local csv=$1
  { echo "workload,profile,runtime,exit_code"
    tail -n +2 "${csv}" | awk -F, -v p="${profile}" -v f="${failed_only}" \
      'NF && (p == "" || $5 == p) && (f != "true" || $8 != "0")' |
      cut -d, -f4,5,7,8 | sed 's#^[^,]*/##'
  } | awk -F, '{ printf "%-60s %-9s %-8s %s\n", $1, $2, $3, $4 }'
}

main() {
  parse_args "$@"
  tmp_file=$(mktemp) || die "cannot create a temporary file"
  local tmp=${tmp_file}

  local status
  if [[ "${local_mode}" == true ]]; then
    bash -s -- "${ledger_file}" "${LEDGER_CANDIDATES[@]}" <<<"${FIND_LEDGER}" >"${tmp}"
    status=$?
  else
    connect
    local remote_args
    # ssh joins its arguments into one remote command line, so quote them.
    remote_args=$(printf '%q ' "${ledger_file}" "${LEDGER_CANDIDATES[@]}")
    "${ssh_cmd[@]}" "${remote_user}@${remote_host}" "bash -s -- ${remote_args}" <<<"${FIND_LEDGER}" >"${tmp}"
    status=$?
  fi
  if ((status == 3)); then
    if [[ "${local_mode}" == true ]]; then
      die "no runtime ledger on this machine (looked for: $(head -n 1 "${tmp}")). To read a benchmark machine's ledger, give --host HOST; for a saved copy, give --file FILE."
    fi
    die "no runtime ledger on ${remote_host} (looked for: $(head -n 1 "${tmp}"))"
  fi
  ((status == 0)) || die "reading the ledger failed (exit code ${status})"

  csv_file="${tmp}.csv"
  local csv=${csv_file}
  tail -n +2 "${tmp}" | tr -d '\r' >"${csv}"
  [[ -s "${csv}" ]] || die "the ledger is empty: $(head -n 1 "${tmp}")"
  show_runs "${csv}"
}

main "$@"
