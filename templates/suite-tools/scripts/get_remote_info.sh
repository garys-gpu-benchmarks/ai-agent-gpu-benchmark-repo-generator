#!/usr/bin/env bash
# ==============================================================================
# get_remote_info.sh
#
# Collects benchmark results from one remote benchmark machine (any of the four
# platforms) into the current folder:
#
#   RUNTIME_LEDGERS/runtime_ledger_<first>_<last>_<time>.csv  (and .xlsx)
#   DIRECTORIES/<workload>/results/raw/...
#   DIRECTORIES/<workload>/results/parsed/...
#   DIRECTORIES/<workload>/results/runtime_ledger_<first>_<last>_<time>.csv
#   DIRECTORIES/benchmark_suite_log/...         (run_benchmark_suite.sh logs)
#
# Everything comes over ONE ssh connection as ONE compressed tar stream.
# Workloads and the ledger are found on the remote machine; nothing is
# hard-coded per platform.
#
# Usage:   ./get_remote_info.sh [options] HOST [PORT]
# Help:    ./get_remote_info.sh --help
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

declare -a ssh_cmd=()
timestamp="$(date '+%Y%m%d_%H%M%S')"

usage() {
  cat <<EOF
Usage: ${SCRIPT_NAME} [options] HOST [PORT]

Copies from the benchmark machine HOST (port PORT, default 22):
  - the runtime ledger, saved as a timestamped CSV (and an Excel copy)
  - every workload's results/raw and results/parsed folders
  - run_benchmark_suite.sh logs
into RUNTIME_LEDGERS/ and DIRECTORIES/ under the output folder.

HOST can be an IP address or name, optionally with a user: user@host
(default user: root).

Options:
  -i, --identity KEY    SSH private key to use. Default: try your ssh
                        defaults, then each private key in ~/.ssh.
  -o, --output DIR      Output folder. Default: the current folder.
  -r, --remote-root DIR Folder holding the workloads on the remote machine.
                        Default: /opt/benchmarks
  -l, --ledger FILE     Ledger path on the remote machine.
                        Default: the first that exists of
                        ${LEDGER_CANDIDATES[*]}
      --no-xlsx         Do not create the Excel (.xlsx) copy of the ledger.
  -h, --help            Show this help.

Examples:
  ./${SCRIPT_NAME} 203.0.113.10                     # GPU VM, port 22
  ./${SCRIPT_NAME} 203.0.113.20 13178               # cloud pod on port 13178
  ./${SCRIPT_NAME} -i ~/.ssh/id_ed25519 203.0.113.30
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

parse_args() {
  local -a positional=()
  while (($# > 0)); do
    case "$1" in
      -i | --identity)    [[ $# -ge 2 ]] || die_usage "$1 needs a value"; ssh_key=$2; shift 2 ;;
      -o | --output)      [[ $# -ge 2 ]] || die_usage "$1 needs a value"; out_dir=$2; shift 2 ;;
      -r | --remote-root) [[ $# -ge 2 ]] || die_usage "$1 needs a value"; remote_root=$2; shift 2 ;;
      -l | --ledger)      [[ $# -ge 2 ]] || die_usage "$1 needs a value"; remote_ledger=$2; shift 2 ;;
      --no-xlsx)          make_xlsx=false; shift ;;
      -h | --help)        usage; exit 0 ;;
      -*)                 die_usage "unknown option: $1" ;;
      *)                  positional+=("$1"); shift ;;
    esac
  done

  ((${#positional[@]} >= 1 && ${#positional[@]} <= 2)) || die_usage "give HOST and optionally PORT"
  remote_host=${positional[0]}
  if [[ "${remote_host}" == *@* ]]; then
    remote_user=${remote_host%@*}
    remote_host=${remote_host#*@}
  fi
  [[ -n "${remote_host}" ]] || die_usage "HOST is empty"
  if ((${#positional[@]} == 2)); then remote_port=${positional[1]}; fi
  if ! [[ "${remote_port}" =~ ^[0-9]+$ ]] || ((remote_port < 1 || remote_port > 65535)); then
    die_usage "PORT must be a number from 1 to 65535"
  fi
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
  ssh_cmd=(ssh -p "${remote_port}"
    -o ConnectTimeout=15 -o ServerAliveInterval=30 -o StrictHostKeyChecking=accept-new)

  echo "Connecting to ${remote_user}@${remote_host} (port ${remote_port})..."
  if [[ -n "${ssh_key}" ]]; then
    ssh_cmd+=(-i "${ssh_key}" -o IdentitiesOnly=yes)
    try_login || { explain_ssh_error; die "cannot log in with ${ssh_key}"; }
    echo "Logged in with ${ssh_key}"
    return
  fi

  if try_login; then
    echo "Logged in with your default ssh settings"
    return
  fi
  [[ "${probe_error}" == *"Permission denied"* ]] || { explain_ssh_error; die "cannot connect"; }

  local key
  for key in "${HOME}"/.ssh/*; do
    is_private_key "${key}" || continue
    if try_login -i "${key}" -o IdentitiesOnly=yes; then
      ssh_cmd+=(-i "${key}" -o IdentitiesOnly=yes)
      echo "Logged in with ${key}"
      return
    fi
  done
  explain_ssh_error
  die "none of the keys in ${HOME}/.ssh were accepted"
}

# Runs on the remote machine. Writes one gzip-compressed tar stream to stdout
# and progress to stderr. Arguments: workload root, ledger path ('' = search).
read -r -d '' REMOTE_SCRIPT <<'REMOTE'
set -uo pipefail
root=$1
ledger=$2
shift 2
cd "${root}" || { echo "ERROR: cannot open ${root} on the remote machine" >&2; exit 3; }
tmp=$(mktemp -d) || exit 4
trap 'rm -rf "${tmp}"' EXIT
mkdir -p "${tmp}/_meta"
: > "${tmp}/_meta/workloads.txt"

paths=()
for d in [1-4][0-9][0-9]-*/; do
  [ -d "${d}" ] || continue
  d=${d%/}
  echo "${d}" >> "${tmp}/_meta/workloads.txt"
  for sub in raw parsed; do
    if [ -d "${d}/results/${sub}" ]; then paths+=("${d}/results/${sub}"); fi
  done
done
[ -d benchmark_suite_log ] && paths+=(benchmark_suite_log)
echo "  workloads found:  $(wc -l < "${tmp}/_meta/workloads.txt")" >&2
echo "  result folders:   $((${#paths[@]}))" >&2

if [ -z "${ledger}" ]; then
  for candidate in "$@"; do
    if [ -f "${candidate}" ]; then ledger=${candidate}; break; fi
  done
fi
if [ -n "${ledger}" ] && [ -f "${ledger}" ]; then
  cp "${ledger}" "${tmp}/_meta/runtime_ledger.csv"
  echo "${ledger}" > "${tmp}/_meta/ledger_path.txt"
  echo "  runtime ledger:   ${ledger}" >&2
else
  echo "  runtime ledger:   not found" >&2
fi
hostname > "${tmp}/_meta/hostname.txt"

# GNU tar exits 1 when a file changed while it was being read (a benchmark is
# still writing its results). The archive is still complete, so that is only a
# warning; exit codes above 1 are real errors.
tar -cf - "${paths[@]}" -C "${tmp}" _meta | gzip -1
st=("${PIPESTATUS[@]}")
if ((st[0] == 1)); then
  echo "  WARNING: some files changed while they were being copied: a benchmark is" >&2
  echo "           probably still running. Its results are partial; collect again" >&2
  echo "           after it finishes." >&2
  st[0]=0
fi
((st[0] == 0)) || exit "${st[0]}"
exit "${st[1]}"
REMOTE

transfer() {
  local dest="${out_dir}/DIRECTORIES"
  mkdir -p "${dest}" "${out_dir}/RUNTIME_LEDGERS" || die "cannot create folders in ${out_dir}"
  rm -rf "${dest}/_meta"

  echo
  echo "Collecting from ${remote_root} on the remote machine..."
  # ssh joins its arguments into one remote command line, so quote them.
  local remote_args
  remote_args=$(printf '%q ' "${remote_root}" "${remote_ledger}" "${LEDGER_CANDIDATES[@]}")
  # GNU tar warns about every file whose time stamp is a fraction of a second
  # ahead of this computer's clock (files the remote machine just wrote).
  # Those warnings are harmless; hide them.
  local -a untar=(tar -xf - -C "${dest}")
  if tar --version 2>/dev/null | grep -q 'GNU tar'; then untar+=(--warning=no-timestamp); fi
  "${ssh_cmd[@]}" "${remote_user}@${remote_host}" "bash -s -- ${remote_args}" <<<"${REMOTE_SCRIPT}" \
    | gzip -dc \
    | "${untar[@]}"
  local -a status=("${PIPESTATUS[@]}")
  [[ "${status[0]}" -eq 0 ]] || die "the remote collection failed (exit code ${status[0]})"
  [[ "${status[1]}" -eq 0 && "${status[2]}" -eq 0 ]] || die "the transfer was incomplete (unpacking failed)"
  [[ -d "${dest}/_meta" ]] || die "the transfer was incomplete (no metadata received)"
}

# Ledger name label: first and last workload numbers, e.g. 101_132.
workload_label() {
  local file=$1 first last
  first=$(head -n 1 "${file}" | cut -c1-3)
  last=$(tail -n 1 "${file}" | cut -c1-3)
  if [[ -n "${first}" ]]; then echo "${first}_${last}"; else echo "unknown"; fi
}

convert_to_xlsx() {
  local csv=$1 xlsx=$2
  command -v powershell.exe >/dev/null 2>&1 || return 1
  local csv_win xlsx_win
  csv_win=$(cygpath -w "$(cd "$(dirname "${csv}")" && pwd)/$(basename "${csv}")" 2>/dev/null) || return 1
  xlsx_win=$(cygpath -w "$(cd "$(dirname "${xlsx}")" && pwd)/$(basename "${xlsx}")" 2>/dev/null) || return 1
  powershell.exe -NoProfile -Command "
    \$ErrorActionPreference = 'Stop'
    \$excel = New-Object -ComObject Excel.Application
    \$excel.Visible = \$false
    \$excel.DisplayAlerts = \$false
    \$workbook = \$excel.Workbooks.Open('${csv_win}')
    \$workbook.SaveAs('${xlsx_win}', 51)
    \$workbook.Close(\$false)
    \$excel.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject(\$workbook) | Out-Null
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject(\$excel) | Out-Null
  " >/dev/null 2>&1
}

# Prints workload, profile, runtime and exit code for every ledger row.
show_ledger() {
  local csv=$1 rows passed failed
  rows=$(($(wc -l <"${csv}") - 1))
  passed=$(tail -n +2 "${csv}" | awk -F, '$8 == "0"' | wc -l)
  failed=$((rows - passed))
  echo
  echo "Runs in the ledger: ${rows}   passed (exit code 0): ${passed}   other: ${failed}"
  echo
  { echo "workload,profile,runtime,exit_code"
    tail -n +2 "${csv}" | cut -d, -f4,5,7,8 | sed 's#^[^,]*/##'
  } | awk -F, '{ printf "%-60s %-9s %-8s %s\n", $1, $2, $3, $4 }'
}

finish() {
  local dest="${out_dir}/DIRECTORIES" meta="${out_dir}/DIRECTORIES/_meta"
  local label remote_name ledger_csv="" ledger_xlsx="" wl copies=0

  label=$(workload_label "${meta}/workloads.txt")
  remote_name=$(cat "${meta}/hostname.txt" 2>/dev/null || echo "${remote_host}")

  if [[ -f "${meta}/runtime_ledger.csv" ]]; then
    ledger_csv="${out_dir}/RUNTIME_LEDGERS/runtime_ledger_${label}_${timestamp}.csv"
    mv "${meta}/runtime_ledger.csv" "${ledger_csv}" || die "cannot save ${ledger_csv}"
    while read -r wl; do
      [[ -n "${wl}" && -d "${dest}/${wl}" ]] || continue
      mkdir -p "${dest}/${wl}/results" && cp "${ledger_csv}" "${dest}/${wl}/results/" && copies=$((copies + 1))
    done <"${meta}/workloads.txt"
    if [[ "${make_xlsx}" == true ]]; then
      ledger_xlsx="${ledger_csv%.csv}.xlsx"
      convert_to_xlsx "${ledger_csv}" "${ledger_xlsx}" || ledger_xlsx=""
    fi
    show_ledger "${ledger_csv}"
  fi
  rm -rf "${meta}"

  echo
  echo "======================================================================"
  echo "Collected from ${remote_name} (${remote_host}, port ${remote_port})"
  echo "Workload results:  ${dest}/"
  if [[ -n "${ledger_csv}" ]]; then
    echo "Runtime ledger:    ${ledger_csv}"
    [[ -n "${ledger_xlsx}" ]] && echo "Excel copy:        ${ledger_xlsx}"
    [[ "${make_xlsx}" == true && -z "${ledger_xlsx}" ]] && echo "Excel copy:        not created (needs Windows with Excel)"
    echo "Ledger also copied into ${copies} workload results folders"
  else
    echo "Runtime ledger:    not found on the remote machine"
  fi
  echo "Completed: $(date)"
  echo "======================================================================"
}

main() {
  parse_args "$@"
  echo "======================================================================"
  echo "get_remote_info: collecting benchmark results"
  echo "Started: $(date)"
  echo "======================================================================"
  connect
  transfer
  finish
}

main "$@"
