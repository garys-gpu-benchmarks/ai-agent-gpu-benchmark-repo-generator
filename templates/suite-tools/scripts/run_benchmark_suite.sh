#!/usr/bin/env bash
# ==============================================================================
# run_benchmark_suite.sh
#
# Runs the benchmark workloads installed under one directory, one after another,
# for each requested profile (smoke, baseline, extended), and optionally repeats
# the whole set. Prints one short block per run and appends the full output of
# every run to a single log file. Ends with a pass/fail summary.
#
# Works on all four platforms (AMD/NVIDIA, Ubuntu 24.04/26.04): the workloads
# are discovered from the directory, not hard-coded.
#
# Usage:   ./run_benchmark_suite.sh [options]
#          ./run_benchmark_suite.sh --list         (which workloads are ready)
# Help:    ./run_benchmark_suite.sh --help
#
# Exit codes:
#   0  every run passed (--list: every listed workload is ready)
#   1  one or more runs failed (--list: a workload is not fetched)
#   2  usage error (bad option, unknown workload, no workloads found)
#   130 interrupted (Ctrl+C); the summary is still printed
# ==============================================================================

set -uo pipefail

readonly SCRIPT_NAME="${0##*/}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly VALID_PROFILES=(smoke baseline extended)
readonly LOG_SUBDIR="benchmark_suite_log"
readonly RULE_PASS="######################################################################"
readonly RULE_MODE="**********************************************************************"
readonly RULE_RUN="======================================================================"

# ------------------------------------------------------------------------------
# Defaults (each can be changed with an option)
# ------------------------------------------------------------------------------
root_dir=""
profiles_arg="smoke,baseline,extended"
workloads_arg=""
repeat_count=1
log_file=""
fail_fast=false
dry_run=false
list_only=false
show_output=false

# ------------------------------------------------------------------------------
# Run state
# ------------------------------------------------------------------------------
declare -a profiles=()
declare -a workloads=()
declare -a failed_runs=()
runs_total=0
runs_done=0
runs_passed=0
runs_failed=0
suite_start_epoch=0
suite_start_text=""

usage() {
  cat <<EOF
Usage: ${SCRIPT_NAME} [options]

Runs each workload's run_benchmark.sh for every requested profile, in order:
all workloads with the first profile, then all with the next, and so on.
The whole set is repeated --repeat times.

Options:
  -p, --profiles LIST    Profiles to run, comma-separated, in order.
                         Default: smoke,baseline,extended
  -w, --workloads LIST   Workloads to run, by number, comma-separated.
                         Ranges are allowed. Default: every workload found.
                         Examples: 101,107,121   301-310   101-105,120
  -r, --repeat N         Repeat the whole set N times. Default: 1
  -d, --root DIR         Directory holding the workload folders.
                         Default: the first of these that contains workloads:
                         ./benchmarks next to this script, this script's
                         folder, /opt/benchmarks
  -o, --log FILE         Log file for the full output of every run.
                         Default: <root>/benchmark_suite_log/
                                  run_benchmark_suite_<host>_<time>.log
      --fail-fast        Stop at the first failed run.
      --show-output      Also show each run's full output on screen (it is
                         always written to the log file).
  -l, --list             List the workloads with their state, ready or
                         not fetched, and exit. Takes -w and -d.
  -n, --dry-run          Show what would run, without running anything.
  -h, --help             Show this help.

Times are shown in the system time zone. To use another, set TZ, e.g.
  TZ=America/Chicago ./${SCRIPT_NAME}

Examples:
  ./${SCRIPT_NAME}                                  # all workloads, all 3 profiles
  ./${SCRIPT_NAME} -p smoke                         # quick check of everything
  ./${SCRIPT_NAME} -w 101,107,121 -p baseline       # three workloads, baseline only
  ./${SCRIPT_NAME} -w 105 -p smoke --show-output    # one workload, output on screen
  ./${SCRIPT_NAME} -r 20                            # soak test: everything, 20 times
  ./${SCRIPT_NAME} --list                           # every workload should be ready
EOF
}

die_usage() {
  echo "${SCRIPT_NAME}: $*" >&2
  echo "Try '${SCRIPT_NAME} --help'." >&2
  exit 2
}

timestamp() { date '+%a %b %e %H:%M:%S %Z %Y'; }

format_duration() {
  local seconds=$1
  printf '%2dmin %02dsec' $((seconds / 60)) $((seconds % 60))
}

format_long_duration() {
  local seconds=$1
  printf '%d hours %d minutes %d seconds' \
    $((seconds / 3600)) $(((seconds % 3600) / 60)) $((seconds % 60))
}

# Prints to the console and appends the same text to the log file.
say() {
  printf '%s\n' "$*"
  [[ -n "${log_file}" && "${dry_run}" == false ]] && printf '%s\n' "$*" >>"${log_file}"
  return 0
}

has_workloads() {
  compgen -G "$1/[1-4][0-9][0-9]-*/run_benchmark.sh" >/dev/null
}

# A bundle clone without --recurse-submodules has its workload folders (or
# only .gitmodules) but no run_benchmark.sh in them yet.
has_workload_folders() {
  compgen -G "$1/[1-4][0-9][0-9]-*/" >/dev/null || [[ -f "$1/.gitmodules" ]]
}

parse_args() {
  while (($# > 0)); do
    case "$1" in
      -p | --profiles)  [[ $# -ge 2 ]] || die_usage "$1 needs a value"; profiles_arg=$2; shift 2 ;;
      -w | --workloads) [[ $# -ge 2 ]] || die_usage "$1 needs a value"; workloads_arg=$2; shift 2 ;;
      -r | --repeat)    [[ $# -ge 2 ]] || die_usage "$1 needs a value"; repeat_count=$2; shift 2 ;;
      -d | --root)      [[ $# -ge 2 ]] || die_usage "$1 needs a value"; root_dir=$2; shift 2 ;;
      -o | --log)       [[ $# -ge 2 ]] || die_usage "$1 needs a value"; log_file=$2; shift 2 ;;
      --fail-fast)      fail_fast=true; shift ;;
      --show-output)    show_output=true; shift ;;
      -l | --list)      list_only=true; shift ;;
      -n | --dry-run)   dry_run=true; shift ;;
      -h | --help)      usage; exit 0 ;;
      *)                die_usage "unknown option: $1" ;;
    esac
  done

  [[ "${repeat_count}" =~ ^[1-9][0-9]*$ ]] || die_usage "--repeat must be a whole number of 1 or more"
}

resolve_root() {
  if [[ -n "${root_dir}" ]]; then
    [[ -d "${root_dir}" ]] || die_usage "--root: no such directory: ${root_dir}"
  else
    local candidate
    for candidate in "${SCRIPT_DIR}/benchmarks" "${SCRIPT_DIR}" /opt/benchmarks; do
      if has_workloads "${candidate}"; then
        root_dir=${candidate}
        break
      fi
    done
    if [[ -z "${root_dir}" && "${list_only}" == true ]]; then
      for candidate in "${SCRIPT_DIR}/benchmarks" "${SCRIPT_DIR}" /opt/benchmarks; do
        if has_workload_folders "${candidate}"; then
          root_dir=${candidate}
          break
        fi
      done
    fi
    [[ -n "${root_dir}" ]] || die_usage "no workloads found; give the folder that holds them with --root DIR"
  fi
  root_dir=$(cd "${root_dir}" && pwd)
}

resolve_profiles() {
  local item valid ok
  IFS=',' read -r -a profiles <<<"${profiles_arg}"
  ((${#profiles[@]} > 0)) || die_usage "--profiles is empty"
  for item in "${profiles[@]}"; do
    ok=false
    for valid in "${VALID_PROFILES[@]}"; do [[ "${item}" == "${valid}" ]] && ok=true; done
    [[ "${ok}" == true ]] || die_usage "unknown profile '${item}' (use: ${VALID_PROFILES[*]})"
  done
}

# Fills $wl_numbers with the workload numbers named by -w (numbers and
# ranges), and $wl_single with "1" where the number was given on its own.
# Runs in the main shell, so its usage errors stop the script.
declare -a wl_numbers=() wl_single=()
expand_workload_numbers() {
  local -a wanted=()
  local item first last n
  wl_numbers=(); wl_single=()
  IFS=',' read -r -a wanted <<<"${workloads_arg}"
  for item in "${wanted[@]}"; do
    if [[ "${item}" =~ ^([0-9]{3})-([0-9]{3})$ ]]; then
      first=$((10#${BASH_REMATCH[1]})); last=$((10#${BASH_REMATCH[2]}))
      ((first <= last)) || die_usage "bad range '${item}'"
    elif [[ "${item}" =~ ^[0-9]{3}$ ]]; then
      first=$((10#${item})); last=${first}
    else
      die_usage "bad workload '${item}' (use numbers like 101, or ranges like 101-110)"
    fi
    for ((n = first; n <= last; n++)); do
      wl_numbers+=("${n}")
      if ((first == last)); then wl_single+=(1); else wl_single+=(0); fi
    done
  done
  ((${#wl_numbers[@]} > 0)) || die_usage "--workloads is empty"
}

# --list: one line per workload folder (from the folder and .gitmodules), with
# its state. "ready" means the folder holds run_benchmark.sh.
list_workloads() {
  local -a names=()
  local dir name path state ready=0 missing=0
  for dir in "${root_dir}"/[1-4][0-9][0-9]-*/; do
    [[ -d "${dir}" ]] && names+=("$(basename "${dir}")")
  done
  if [[ -f "${root_dir}/.gitmodules" ]] && command -v git >/dev/null 2>&1; then
    while read -r _key path; do
      name=$(basename "${path}")
      [[ "${name}" =~ ^[1-4][0-9][0-9]- ]] || continue
      [[ " ${names[*]} " == *" ${name} "* ]] || names+=("${name}")
    done < <(git config -f "${root_dir}/.gitmodules" --get-regexp '^submodule\..*\.path$' 2>/dev/null)
  fi
  ((${#names[@]} > 0)) || die_usage "no workloads (NNN-*) in ${root_dir}"
  mapfile -t names < <(printf '%s\n' "${names[@]}" | sort)
  if [[ -n "${workloads_arg}" ]]; then
    expand_workload_numbers
    local -a kept=()
    for name in "${names[@]}"; do
      [[ " ${wl_numbers[*]} " == *" $((10#${name:0:3})) "* ]] && kept+=("${name}")
    done
    ((${#kept[@]} > 0)) || die_usage "none of the requested workloads are in ${root_dir}"
    names=("${kept[@]}")
  fi
  for name in "${names[@]}"; do
    if [[ -f "${root_dir}/${name}/run_benchmark.sh" ]]; then
      state="ready"; ready=$((ready + 1))
    else
      state="not fetched"; missing=$((missing + 1))
    fi
    printf '%-4s %-60s %s\n' "${name:0:3}" "${name}" "${state}"
  done
  echo "${#names[@]} workloads in ${root_dir}: ${ready} ready, ${missing} not fetched"
  if ((missing > 0)); then
    echo "Fetch the rest with:  git -C ${root_dir} submodule update --init --recursive"
    return 1
  fi
  return 0
}

# Fills $workloads with folder names, in numeric order.
resolve_workloads() {
  local -a found=()
  local dir n match

  for dir in "${root_dir}"/[1-4][0-9][0-9]-*/; do
    [[ -f "${dir}run_benchmark.sh" ]] && found+=("$(basename "${dir}")")
  done
  ((${#found[@]} > 0)) || die_usage "no workloads (NNN-*/run_benchmark.sh) in ${root_dir}"

  if [[ -z "${workloads_arg}" ]]; then
    workloads=("${found[@]}")
    return
  fi

  expand_workload_numbers
  # A number given on its own that is not installed is an error; a range
  # keeps the workloads that exist.
  local i
  for ((i = 0; i < ${#wl_numbers[@]}; i++)); do
    n=${wl_numbers[i]}
    match=""
    for dir in "${found[@]}"; do [[ "${dir}" == "${n}-"* ]] && match=${dir}; done
    if [[ -n "${match}" ]]; then
      [[ " ${workloads[*]} " == *" ${match} "* ]] || workloads+=("${match}")
    elif [[ "${wl_single[i]}" == 1 ]]; then
      if compgen -G "${root_dir}/${n}-*/" >/dev/null; then
        die_usage "workload ${n} is not fetched yet; run: git -C ${root_dir} submodule update --init --recursive"
      fi
      die_usage "workload ${n} is not installed in ${root_dir}"
    fi
  done
  ((${#workloads[@]} > 0)) || die_usage "none of the requested workloads are installed in ${root_dir}"
  mapfile -t workloads < <(printf '%s\n' "${workloads[@]}" | sort)
}

print_summary() {
  local elapsed=$(($(date +%s) - suite_start_epoch))
  say ""
  say "${RULE_RUN}"
  say "SUMMARY: ${runs_done} of ${runs_total} runs finished: ${runs_passed} passed, ${runs_failed} failed"
  if ((runs_failed > 0)); then
    say "Failed runs:"
    local entry
    for entry in "${failed_runs[@]}"; do say "  ${entry}"; done
  fi
  say "Started:       ${suite_start_text}"
  say "Completed:     $(timestamp)"
  say "Total runtime: $(format_long_duration "${elapsed}")"
  say "Log file:      ${log_file}"
  say "${RULE_RUN}"
}

on_interrupt() {
  trap - INT TERM
  say ""
  say "Interrupted."
  print_summary
  exit 130
}

# Runs one workload with one profile; updates the counters.
run_one() {
  local workload=$1 profile=$2 pass=$3
  local start end exit_code
  local run_number=$((runs_done + 1))

  say ""
  say "${RULE_RUN}"
  say "Starting: ${workload}"
  say "\"bash run_benchmark.sh --${profile}\" (repeat ${pass} of ${repeat_count}, run ${run_number} of ${runs_total})"
  say "$(timestamp)"
  printf '\n%s\n%s: bash run_benchmark.sh --%s\n' "${RULE_RUN}" "${workload}" "${profile}" >>"${log_file}"

  start=$(date +%s)
  if [[ "${show_output}" == true ]]; then
    (cd "${root_dir}/${workload}" && bash run_benchmark.sh "--${profile}") </dev/null 2>&1 | tee -a "${log_file}"
    exit_code=${PIPESTATUS[0]}
  else
    (cd "${root_dir}/${workload}" && bash run_benchmark.sh "--${profile}") </dev/null >>"${log_file}" 2>&1
    exit_code=$?
  fi
  end=$(date +%s)
  runs_done=${run_number}

  say "Completed \"bash run_benchmark.sh --${profile}\" with exit code ${exit_code}"
  say "Total runtime: $(format_duration $((end - start)))"

  if ((exit_code == 0)); then
    runs_passed=$((runs_passed + 1))
  else
    runs_failed=$((runs_failed + 1))
    failed_runs+=("${workload} --${profile} (repeat ${pass}): exit code ${exit_code}")
    if [[ "${fail_fast}" == true ]]; then
      say ""
      say "Stopping at the first failure (--fail-fast)."
      print_summary
      exit 1
    fi
  fi
}

main() {
  parse_args "$@"
  resolve_root
  if [[ "${list_only}" == true ]]; then
    list_workloads
    exit $?
  fi
  resolve_profiles
  resolve_workloads

  runs_total=$((repeat_count * ${#profiles[@]} * ${#workloads[@]}))
  [[ -n "${log_file}" ]] || log_file="${root_dir}/${LOG_SUBDIR}/run_benchmark_suite_$(hostname -s)_$(date '+%Y%m%d_%H%M%S').log"

  if [[ "${dry_run}" == true ]]; then
    echo "Dry run: nothing will be executed."
    echo "Root:      ${root_dir}"
    echo "Profiles:  ${profiles[*]}"
    echo "Repeat:    ${repeat_count}"
    echo "Workloads: ${#workloads[@]}"
    printf '  %s\n' "${workloads[@]}"
    echo "Total runs: ${runs_total}"
    echo "Log file would be: ${log_file}"
    exit 0
  fi

  if ! { mkdir -p "$(dirname "${log_file}")" && : >>"${log_file}"; }; then
    echo "${SCRIPT_NAME}: cannot write log file ${log_file}" >&2
    exit 2
  fi
  trap on_interrupt INT TERM

  suite_start_epoch=$(date +%s)
  suite_start_text=$(timestamp)
  say "Root:       ${root_dir}"
  say "Workloads:  ${#workloads[@]}"
  say "Profiles:   ${profiles[*]}"
  say "Repeat:     ${repeat_count}"
  say "Total runs: ${runs_total}"
  say "Log file:   ${log_file}"
  say "Started:    ${suite_start_text}"

  local pass profile workload
  for ((pass = 1; pass <= repeat_count; pass++)); do
    say ""
    say "${RULE_PASS}"
    say "Repeat pass ${pass} of ${repeat_count}"
    say "${RULE_PASS}"
    for profile in "${profiles[@]}"; do
      say ""
      say "${RULE_MODE}"
      say "Mode: --${profile}  (repeat ${pass} of ${repeat_count})"
      say "${RULE_MODE}"
      for workload in "${workloads[@]}"; do
        run_one "${workload}" "${profile}" "${pass}"
      done
    done
  done

  print_summary
  ((runs_failed == 0))
}

main "$@"
