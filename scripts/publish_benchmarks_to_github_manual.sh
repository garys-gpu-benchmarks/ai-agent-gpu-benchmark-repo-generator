#!/usr/bin/env bash
if grep -q $'\r' "$0"; then echo "This file has Windows (CRLF) line endings. Fix it with:  sed -i 's/\r\$//' \"$0\"   then run it again."; exit 1; fi
#
# publish_benchmarks_to_github_manual.sh
#
# The same as publish_benchmarks_to_github.sh, except that it never copies
# anything into the run folder. You fill the run folder by hand before the
# run; step 0 only checks what you copied (every batch complete, no duplicate
# or out-of-range workload numbers, the generator present).
#
# Publishes one generated run of the GPU benchmark suite to the GitHub
# organization garys-gpu-benchmarks:
#
#   128 workload repositories   101-132 AMD ROCm    Ubuntu 24.04
#                               201-232 NVIDIA CUDA Ubuntu 24.04
#                               301-332 AMD ROCm    Ubuntu 26.04
#                               401-432 NVIDIA CUDA Ubuntu 26.04
#   4 bundle repositories       bundle-<vendor>-ubuntu-<2404|2604>, each holding
#                               its 32 workloads as pinned git submodules
#   shared-workflows            the CI every workload calls (@v1)
#   gpu-bench-suite             operator tools (run_benchmark_suite.sh,
#                               get_remote_info.sh)
#   the generator               ai-agent-gpu-benchmark-repo-generator
#
# Folder layout (one dated folder per publish run, holding a copy of this
# script):
#
#   Z:\ServersProcsMemory\Github_Garys_GPU_Repos\Publishing\
#   └── 20261013_03\
#       ├── publish_benchmarks_to_github_manual.sh   copy of this script
#       ├── src_352_353_354_355\                     RUN_FOLDER: filled by hand
#       │   ├── 101-...\                             the 128 generated workloads
#       │   ├── ...
#       │   ├── 432-...\
#       │   └── ai-agent-gpu-benchmark-repo-generator\ the generator
#       ├── src_352_353_354_355_PubTree\             created by this script (logs in _logs\)
#       ├── src_352_353_354_355_Bundles\             created by this script
#       ├── shared-workflows\                        created/updated by this script
#       └── gpu-bench-suite\                         created/updated by this script
#
# Procedure (Git Bash):
#   1. Create the run folder and copy in the generator and the workloads.
#      Take the generator from the same template as the workloads.
#        P=/z/ServersProcsMemory/Projects
#        R=/z/ServersProcsMemory/Github_Garys_GPU_Repos/Publishing/20261013_03
#        mkdir -p $R/src_352_353_354_355
#        cp -a $P/Project351_TEMPLATE_00_105_20261010/TEMPLATE_00_105/ai-agent-gpu-benchmark-repo-generator $R/src_352_353_354_355/
#        cp -a $P/Project352_101_to_132_TEMPLATE_00_106_20261013/TEMPLATE_00_106/1[0-9][0-9]-* $R/src_352_353_354_355/
#        cp -a $P/Project353_201_to_232_TEMPLATE_00_106_20261013/TEMPLATE_00_106/2[0-9][0-9]-* $R/src_352_353_354_355/
#        cp -a $P/Project354_301_to_332_TEMPLATE_00_106_20261013/TEMPLATE_00_106/3[0-9][0-9]-* $R/src_352_353_354_355/
#        cp -a $P/Project355_401_to_432_TEMPLATE_00_106_20261013/TEMPLATE_00_106/4[0-9][0-9]-* $R/src_352_353_354_355/
#   2. Copy this script into the dated folder and run it from there:
#        cd $R
#        ./publish_benchmarks_to_github_manual.sh src_352_353_354_355
#   3. Check: the run ends with FINISHED (no STOPPED); then on GitHub, green CI.
#
# Do not repeat the cp commands for a run that has already started: cp -a
# overwrites any fixes made in the run folder. To replace one workload, delete
# it from the run folder (and from the _PubTree if step 1 already copied it),
# copy it in again, and run again.
#
# shared-workflows and gpu-bench-suite are built next to RUN_FOLDER from the
# generator inside it; change them in the generator, never by hand.
#
# Usage:    ./publish_benchmarks_to_github_manual.sh RUN_FOLDER
# Help:     ./publish_benchmarks_to_github_manual.sh --help
# Runs on:  Git Bash on Windows (also Linux and macOS), with gh logged in.
#
# The run is resumable: if a step finds a problem it prints STOPPED and the
# reason, and exits. Fix the problem and run the same command again; finished
# work is skipped. Everything printed is also saved in
# <RUN_FOLDER>_PubTree/_logs/run-<date>-<time>.log.
#
# Exit codes:
#   0  everything published
#   1  stopped on a problem (see the STOPPED line)
#   2  usage error
#
# Revision: 2026-10-14 (step 0 and step 9 run the generator's own ruff lint
#           before anything is pushed; step 9 removes __pycache__ and other
#           Python caches from the generator copy)
#           2026-10-13 (manual variant of publish_benchmarks_to_github.sh
#           2026-10-10b: the run folder is filled by hand; step 0 checks it)

set -uo pipefail
set +H

# ------------------------------------------------------------------------------
# Settings you may change
# ------------------------------------------------------------------------------

readonly ORG="garys-gpu-benchmarks"
readonly GENREPO="ai-agent-gpu-benchmark-repo-generator"
# The generator's earlier GitHub name (renamed on 2026-10-10). If GitHub still
# has it under this name, step 9 renames it to $GENREPO.
readonly OLD_GENREPO="999-ai-agent-gpu-benchmark-repo-generator"
readonly PERSONAL_GENERATOR="garymichaelbass/ai-agent-gpu-benchmark-repo-generator"

# Only matters the first time the generator is published, and only if GitHub
# already has it under the personal account ($PERSONAL_GENERATOR):
#   ask  stop and ask (default)
#   yes  move that repository into the organization, keeping its history
#   no   leave it alone and publish a fresh copy in the organization
readonly TRANSFER_PERSONAL_GENERATOR="ask"

# Workloads per batch (x01 to x32).
readonly BATCH_SIZE=32
# What step 0 does when a batch is incomplete or missing:
#   yes  stop unless all four batches have all ${BATCH_SIZE} workloads (default)
#   no   only print a note, and publish what is there
readonly REQUIRE_FULL_RUN="yes"

# Run the generator's own ruff lint (the "ruff check" lines in its
# .github/workflows/*.yml) in step 0 and again in step 9, so a lint error
# stops the run here instead of failing the generator's CI on GitHub:
#   yes  stop if ruff is not installed or the lint fails (default)
#   no   skip the lint
readonly LINT_GENERATOR="yes"

# The run folder name used in the examples and messages.
readonly RUN_FOLDER_NAME="src_352_353_354_355"

# ------------------------------------------------------------------------------
# Usage
# ------------------------------------------------------------------------------

readonly SCRIPT_NAME="${0##*/}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR

usage() {
  cat <<EOF
Usage: ${SCRIPT_NAME} RUN_FOLDER

Publishes one generated run of the GPU benchmark suite to github.com/${ORG}.

RUN_FOLDER must already hold the generated workload folders (101-...,
201-..., 301-..., 401-...) and ${GENREPO}, copied in by hand.
This script never copies anything into it, and never changes it; step 0
checks that every batch has all ${BATCH_SIZE} workloads, with no duplicate or
out-of-range numbers. Next to it the script creates RUN_FOLDER_PubTree and
RUN_FOLDER_Bundles, and in the folder that holds RUN_FOLDER it builds
shared-workflows and gpu-bench-suite from the generator.

Example (Git Bash; use "/" in paths):
  cd /z/ServersProcsMemory/Github_Garys_GPU_Repos/Publishing/20261013_03
  ./${SCRIPT_NAME} ${RUN_FOLDER_NAME}

Steps:
  0  Preflight: tools, check the run folder, version
  1  Copy the workloads into RUN_FOLDER_PubTree
  2  Dry run of each workload's prepare script
  3  Prepare and check each workload
  4  Remove generation leftovers; check what will be published
  5  Publish shared-workflows (CI) and gpu-bench-suite (operator tools)
  6  Publish the workloads
  7  Build and publish the 4 bundles in RUN_FOLDER_Bundles
  8  Test one bundle the way an end user would
  9  Publish the generator

Versions are chosen from GitHub: v1.0.0 on the first run, then the next
patch number (v1.0.8 -> v1.0.9). The choice is kept in
RUN_FOLDER_PubTree/_logs/version.txt; edit that file before step 6 to
choose another version.

If a run stops, fix the problem and run the same command again with the same
RUN_FOLDER; finished work is skipped. Do not repeat the cp commands that
filled the run folder: they overwrite fixes made there.

To publish one workload again after fixing it: fix it in the _PubTree copy,
delete its line from RUN_FOLDER_PubTree/_logs/published.txt, and run again.
EOF
}

RUN_ARG=""
while (($# > 0)); do
  case "$1" in
    -h | --help) usage; exit 0 ;;
    -*) echo "${SCRIPT_NAME}: unknown option: $1" >&2; echo "Try '${SCRIPT_NAME} --help'." >&2; exit 2 ;;
    *)
      [[ -z "${RUN_ARG}" ]] || { echo "${SCRIPT_NAME}: give only one run folder" >&2; exit 2; }
      RUN_ARG=$1 ;;
  esac
  shift
done

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

# Git for Windows refuses paths over 260 characters unless core.longpaths is
# on. Bundle submodules have long paths (.git/modules/<workload>/objects/...),
# so turn it on for every git command this script runs, without changing the
# global git settings.
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.longpaths GIT_CONFIG_VALUE_0=true

START_TIME=$(date)
START_EPOCH=$(date +%s)
readonly START_TIME START_EPOCH

# Prints the start time, the time now (labelled $1) and the run time.
print_times() {
  local secs=$(($(date +%s) - START_EPOCH))
  echo "Start time:     ${START_TIME}"
  echo "$1 $(date)"
  echo "Total runtime:  $((secs / 3600)) hours $(((secs % 3600) / 60)) minutes"
}

stop() {
  echo
  echo "STOPPED: $*"
  echo "Fix the problem above, then run the same command again. Finished work is skipped."
  print_times "Stopped time:  "
  exit 1
}

step() {
  echo
  echo "======================================================================"
  echo "STEP $1: $2"
  echo "======================================================================"
}

# Steps that are expensive to repeat leave a marker file when finished.
mark_done() { date >"${PUB}/_logs/done-$1"; }
is_done()   { [[ -e "${PUB}/_logs/done-$1" ]]; }
skipped()   { echo; echo "STEP $1: already done, skipped"; }

in_list() { grep -qxF "$1" "$2" 2>/dev/null; }

# Runs a command up to 4 times, 5 seconds apart.
again() {
  local i
  for i in 1 2 3 4; do
    "$@" && return 0
    ((i < 4)) && { echo "  (failed, trying again in 5 seconds)"; sleep 5; }
  done
  return 1
}

# Platform name from a workload number or its first digit.
platform() {
  case ${1:0:1} in
    1) echo "AMD ROCm - Ubuntu 24.04" ;;
    2) echo "NVIDIA CUDA - Ubuntu 24.04" ;;
    3) echo "AMD ROCm - Ubuntu 26.04" ;;
    4) echo "NVIDIA CUDA - Ubuntu 26.04" ;;
  esac
}

# If GitHub already has history for this repository, put the new commit on
# top of it, so a later run is a normal update.
attach_history() {
  if ! git rev-parse -q --verify HEAD >/dev/null &&
     GIT_TERMINAL_PROMPT=0 git ls-remote -q --exit-code origin refs/heads/main >/dev/null 2>&1; then
    git fetch -q origin main && git reset -q --soft FETCH_HEAD
  fi
}

# Reads a list of problems on stdin, prints its count and first 10 lines,
# and adds the count to $problems.
check_zero() {
  local found n
  found=$(cat)
  n=$(printf '%s' "${found}" | grep -c .)
  echo "--- $1 (must be 0): ${n}"
  ((n > 0)) && printf '%s\n' "${found}" | head -n 10
  problems=$((problems + n))
}

# Points origin of the repository in the current folder at $ORG/$1, creating
# the GitHub repository (public, description $2) if it does not exist.
use_github_repo() {
  git remote remove origin 2>/dev/null
  git remote add origin "https://github.com/${ORG}/$1.git"
  gh repo view "${ORG}/$1" >/dev/null 2>&1 || gh repo create "${ORG}/$1" --public --description "$2" >/dev/null
}

# Attaches GitHub's history, stages everything, marks shell scripts executable
# (Git for Windows otherwise stores them as not executable), and commits when
# anything changed: with message $1 for a repository's first commit, $2 for a
# later one. Returns 1 on failure.
commit_all() {
  local msg=$1
  attach_history </dev/null || return 1
  git rev-parse -q --verify HEAD >/dev/null && msg=$2
  again git add -A || return 1
  git ls-files -z -- '*.sh' | xargs -0 -r git update-index --chmod=+x
  git diff --cached --quiet || again git commit -q -m "${msg}"
}

# Tags HEAD with this run's version ($VERSION, message $1) and pushes the tag.
# A tag already on GitHub from an interrupted earlier attempt is reused when
# it points at the same commit.
tag_version() {
  git fetch -q origin "refs/tags/${VERSION}:refs/tags/${VERSION}" </dev/null >/dev/null 2>&1
  if git rev-parse -q --verify "refs/tags/${VERSION}" >/dev/null; then
    if [[ "$(git rev-parse "${VERSION}^{commit}")" != "$(git rev-parse HEAD)" ]]; then
      echo "The ${VERSION} tag already on GitHub points at a different commit than this run made."
      return 1
    fi
  else
    again git tag -a "${VERSION}" -m "$1" || return 1
  fi
  git push origin "refs/tags/${VERSION}" </dev/null
}

# Adds one workload to a bundle as a submodule at path $2. A half-added
# submodule left by an interrupted attempt (for example "Permission denied"
# on Windows) is removed first. Tries 4 times.
add_submodule() {
  local dir=$1 path=$2 i
  for i in 1 2 3 4; do
    if git config -f .gitmodules --get "submodule.${path}.path" >/dev/null 2>&1 &&
       [[ -e "${path}/.git" ]] && git ls-files --error-unmatch "${path}" >/dev/null 2>&1; then
      return 0
    fi
    rm -f .git/index.lock
    git update-index -q --force-remove "${path}" >/dev/null 2>&1
    git config -f .gitmodules --remove-section "submodule.${path}" >/dev/null 2>&1
    [[ -f .gitmodules ]] && git add .gitmodules >/dev/null 2>&1
    git config --remove-section "submodule.${path}" >/dev/null 2>&1
    rm -rf "${path}" ".git/modules/${path}"
    git submodule add -q -b main --name "${path}" "../${dir}.git" "${path}" && return 0
    ((i < 4)) && { echo "  (failed, cleaning up and trying again in 5 seconds)"; sleep 5; }
  done
  return 1
}

# Publishes one workload copy. "fresh" first deletes its local .git folder
# (used when retrying a failure). Runs in a subshell.
publish_workload() (
  dir=$1
  cd "${PUB}/${dir}" || exit 1
  if [[ "$2" == fresh ]]; then rm -rf .git || exit 1; fi
  [[ -d .git ]] || git init -q -b main || exit 1
  use_github_repo "${dir}" "$(platform "${dir}") - benchmark ${dir:0:3}" || exit 1
  commit_all "Initial benchmark workload" "Update benchmark workload to ${VERSION}" || exit 1
  git push -u origin main || exit 1
  tag_version "${dir} ${VERSION}" || exit 1
  vendor=amd; stack=rocm
  case ${dir:0:1} in 2 | 4) vendor=nvidia; stack=cuda ;; esac
  os=2404
  case ${dir:0:1} in 3 | 4) os=2604 ;; esac
  gh repo edit "${ORG}/${dir}" --add-topic gpu-benchmark --add-topic "${vendor}" --add-topic "${stack}" --add-topic "ubuntu-${os}" >/dev/null 2>&1
  true
)

# Sets PY to a Python that has PyYAML (the generator's emit script needs it).
PY=()
find_python() {
  local p
  local -a cand
  ((${#PY[@]} > 0)) && return 0
  for p in python3 python py; do
    command -v "${p}" >/dev/null 2>&1 || continue
    if [[ "${p}" == py ]]; then cand=(py -3); else cand=("${p}"); fi
    "${cand[@]}" -c "import yaml" >/dev/null 2>&1 && { PY=("${cand[@]}"); return 0; }
  done
  stop "Python with PyYAML is needed to build the suite-level repositories. Install it with:  python -m pip install pyyaml"
}

# Builds one suite-level repository from the generator into the workspace
# (the folder that holds the run folder). $1 = emit_shared_workflows.py
# --only value, $2 = target folder. An existing folder is updated; its .git
# and any other files are kept. PYTHONDONTWRITEBYTECODE keeps the run folder
# unchanged (no __pycache__).
emit_repo() {
  local only=$1 dir=$2
  local -a args=(--output-root ../.. --only "${only}")
  find_python
  [[ -f "${GEN}/${GENREPO}/scripts/emit_shared_workflows.py" ]] || stop "${GENREPO} has no scripts/emit_shared_workflows.py, so $(basename "${dir}") cannot be built"
  [[ -d "${dir}" ]] && args+=(--update)
  (cd "${GEN}/${GENREPO}" && PYTHONDONTWRITEBYTECODE=1 "${PY[@]}" scripts/emit_shared_workflows.py "${args[@]}") </dev/null >"${PUB}/_logs/emit-${only}.log" 2>&1 \
    || { tail -n 20 "${PUB}/_logs/emit-${only}.log"; stop "building $(basename "${dir}") from the generator failed (see above and ${PUB}/_logs/emit-${only}.log)"; }
  echo "Built ${dir} from the generator"
}

# Runs the same ruff lint as the generator's CI, in the generator folder $1,
# without writing a .ruff_cache or __pycache__ there. The commands are read
# from the "ruff check" lines in its .github/workflows/*.yml, so they stay in
# step with CI. Stops the run if a command fails.
lint_generator() {
  local dir=$1 cmds cmd n=0
  [[ "${LINT_GENERATOR}" == yes ]] || { echo "Lint of ${GENREPO}: skipped (LINT_GENERATOR=\"${LINT_GENERATOR}\")"; return 0; }
  cmds=$(cat "${dir}"/.github/workflows/*.yml "${dir}"/.github/workflows/*.yaml 2>/dev/null | tr -d '\r' |
         sed -nE 's/^[[:space:]]*(-[[:space:]]+)?(run:[[:space:]]*)?(ruff[[:space:]]+check([[:space:]].*)?)$/\3/p' | sort -u)
  if [[ -z "${cmds}" ]]; then
    echo "Lint of ${GENREPO}: its CI runs no ruff check, nothing to do"
    return 0
  fi
  local -a RUFF=()
  if command -v ruff >/dev/null 2>&1; then
    RUFF=(ruff)
  else
    local p
    for p in python3 python py; do
      command -v "${p}" >/dev/null 2>&1 || continue
      if [[ "${p}" == py ]]; then RUFF=(py -3 -m ruff); else RUFF=("${p}" -m ruff); fi
      "${RUFF[@]}" --version >/dev/null 2>&1 && break
      RUFF=()
    done
  fi
  ((${#RUFF[@]} > 0)) || stop "ruff is needed to lint ${GENREPO} the way its CI does. Install it with:  python -m pip install ruff   (or set LINT_GENERATOR=\"no\" near the top of this file)"
  echo "Lint of ${GENREPO} in ${dir} with $("${RUFF[@]}" --version 2>/dev/null)"
  while IFS= read -r cmd; do
    [[ -n "${cmd}" ]] || continue
    n=$((n + 1))
    echo "  ${cmd}"
    # Replace the leading "ruff check" with this machine's ruff, keep CI's
    # arguments, and add --no-cache so nothing is written into the folder.
    if ! (cd "${dir}" && PYTHONDONTWRITEBYTECODE=1 eval "\"\${RUFF[@]}\" check --no-cache ${cmd#ruff*check}") </dev/null; then
      stop "the generator fails its own ruff lint (above), so its CI on GitHub would fail. Fix it in the generator source and in ${dir}, then run again. Many problems are fixed by running the same command with --fix."
    fi
  done <<<"${cmds}"
  echo "Lint of ${GENREPO}: ${n} ruff command(s) passed"
}

# Waits for the Self-test workflow run of commit $1 in $SHARED_REPO and
# returns its result. Waits up to 3 minutes for the run to start.
wait_self_test() {
  local sha=$1 id="" i
  for i in $(seq 1 18); do
    id=$(gh run list -R "${ORG}/${SHARED_REPO}" --workflow self-test.yml --commit "${sha}" --limit 1 --json databaseId -q '.[0].databaseId' 2>/dev/null)
    [[ -n "${id}" ]] && break
    sleep 10
  done
  if [[ -z "${id}" ]]; then echo "No Self-test run started for commit ${sha:0:7} within 3 minutes."; return 1; fi
  echo "Waiting for the Self-test run: https://github.com/${ORG}/${SHARED_REPO}/actions/runs/${id}"
  gh run watch "${id}" -R "${ORG}/${SHARED_REPO}" --exit-status --interval 15 >/dev/null
}

# Writes run.sh for a bundle to $1.
write_bundle_run_sh() {
  cat >"$1" <<'RUNSH'
#!/usr/bin/env bash
# run.sh - list, fetch and run the benchmarks in this bundle.
#   ./run.sh list | ./run.sh <NNN> [--baseline|--extended] | ./run.sh all
set -uo pipefail
cd "$(dirname "$0")"
find_dir() { local d; for d in "$1"-*/; do [ -d "$d" ] && { echo "${d%/}"; return; }; done; }
ensure() {
  if [ ! -e "$1/.git" ]; then
    echo ">> fetching $(basename "$1")"
    git submodule update --init -- "$1" || return 1
  fi
}
run_one() {
  local n=$1; shift
  local d; d=$(find_dir "$n")
  [ -n "$d" ] || { echo "No benchmark $n in this bundle (try ./run.sh list)"; return 2; }
  ensure "$d" || return 1
  mkdir -p results
  local logf="results/$(basename "$d")-$(date +%Y%m%d-%H%M%S).log"
  echo ">> $(basename "$d"): setup"
  ( cd "$d" && bash ./setup.sh ) 2>&1 | tee "$logf"; [ "${PIPESTATUS[0]}" -eq 0 ] || return 1
  echo ">> $(basename "$d"): run"
  ( cd "$d" && bash ./run_benchmark.sh "$@" ) 2>&1 | tee -a "$logf"; [ "${PIPESTATUS[0]}" -eq 0 ] || return 1
  echo ">> log: $logf"
}
case "${1:-}" in
  list)
    git config -f .gitmodules --get-regexp '^submodule\..*\.path$' | while read -r key p; do
      name=$(basename "$p")
      state="not fetched"; [ -e "$p/.git" ] && state="ready"
      printf '%-4s %-60s %s\n' "${name%%-*}" "$name" "$state"
    done ;;
  all)
    pass=0; fail=0; failed=()
    for d in [1-4][0-9][0-9]-*/; do
      n=$(basename "$d"); n=${n%%-*}
      if run_one "$n"; then pass=$((pass+1)); else fail=$((fail+1)); failed+=("$n"); fi
    done
    echo "== $pass passed, $fail failed ${failed[*]:-}" ;;
  ''|-h|--help) sed -n '2,3p' "$0" | sed 's/^# //' ;;
  *) n=$1; shift; run_one "$n" "$@" ;;
esac
RUNSH
}

# Prints a bundle's README.md. $1 = platform digit (1-4), $2 = bundle name,
# $3 = number of workloads, $4 = list of workload rows (Markdown).
bundle_readme() {
  local s=$1 bundle=$2 want=$3 rows=$4 text
  local plat vendor stack os
  plat=$(platform "$s")
  case $s in 1 | 3) vendor=AMD; stack="ROCm" ;; *) vendor=NVIDIA; stack="the NVIDIA driver and CUDA" ;; esac
  case $s in 1 | 2) os=24.04 ;; *) os=26.04 ;; esac
  text=$(cat <<'README'
# @PLATFORM@ benchmark bundle

@WANT@ system and GPU benchmarks for @VENDOR@ GPU machines running Ubuntu @OS@,
each pinned to its tested @VERSION@ release.

Use this bundle only on that platform. The others have their own bundle:
[AMD 24.04](https://github.com/@ORG@/bundle-amd-ubuntu-2404) ·
[NVIDIA 24.04](https://github.com/@ORG@/bundle-nvidia-ubuntu-2404) ·
[AMD 26.04](https://github.com/@ORG@/bundle-amd-ubuntu-2604) ·
[NVIDIA 26.04](https://github.com/@ORG@/bundle-nvidia-ubuntu-2604)

## Before you start

- A freshly installed **Ubuntu @OS@** machine with @VENDOR@ GPUs, connected to the internet.
- **root** access: log in as root, or run `sudo -i` first.
- Plenty of free disk space. Each benchmark installs its own software the first
  time it runs, and checks for at least 20 GiB free before it does. The AI
  benchmarks also download models.
- For the AI model benchmarks (@S@23 to @S@31): if a model's license on Hugging
  Face requires it, accept the license there and set a token first:
  `export HF_TOKEN=hf_...`

## Install

```bash
apt-get update && apt-get install -y git tmux
git clone --recurse-submodules https://github.com/@ORG@/@BUNDLE@ /opt/benchmarks
cd /opt/benchmarks
./run.sh list
```

`./run.sh list` should show all @WANT@ benchmarks as `ready`.
Do not use GitHub's **Download ZIP**: it leaves the benchmark folders empty.

## Getting started: three quick benchmarks

```bash
cd /opt/benchmarks
./run_benchmark_suite.sh -w @S@01,@S@02,@S@15 -p smoke
```

This runs the short `smoke` profile of three benchmarks:

| Benchmark | What it checks |
|---|---|
| @S@01 | the GPU software stack is installed and working |
| @S@02 | GPU health |
| @S@15 | GPU memory (HBM) bandwidth |

The first run takes much longer than later ones: it installs @STACK@ and each
benchmark's software. The install may restart the machine once. If it does,
log in again after the restart, wait a few minutes for setup to finish on its
own, and run the same command again.

Each run prints a short block, and the suite ends with a pass/fail summary.
The full output is in `/opt/benchmarks/benchmark_suite_log/`.

To run a single benchmark with its output on screen:

```bash
./run.sh @S@05                # setup, then the smoke profile of benchmark @S@05
./run.sh @S@05 --baseline     # the standard profile
```

## Run everything

Run the full suite inside `tmux`, so it keeps running if your connection drops.
It takes many hours.

```bash
tmux new -s bench
cd /opt/benchmarks
./run_benchmark_suite.sh
```

This runs all @WANT@ benchmarks with the `smoke` profile, then all with
`baseline`, then all with `extended`. Detach with **Ctrl+B** then **D**;
reattach later with `tmux attach -t bench`.

Run "Getting started" first on a new machine, so the one-time install (and any
restart) happens before the long run.

| Option | What it does |
|---|---|
| `-p smoke` | profiles to run, in order (`smoke`, `baseline`, `extended`; comma-separated) |
| `-w @S@01,@S@07,@S@21` | only these benchmarks; ranges work too: `-w @S@01-@S@10` |
| `-r 20` | repeat the whole set 20 times (soak test) |
| `--fail-fast` | stop at the first failed run |
| `-n` | show what would run, without running it |
| `--help` | all options |

## Results

| What | Where |
|---|---|
| Summary of the suite | end of the screen output |
| Full output of every run | `/opt/benchmarks/benchmark_suite_log/` |
| Each benchmark's results | `/opt/benchmarks/<benchmark>/results/` (`raw/` and `parsed/`) |
| One line per run (time, exit code) | `/var/opt/benchmarks/runtime_ledger.csv` |

To copy everything to a Windows laptop, use `get_remote_info.sh` from
[gpu-bench-suite](https://github.com/@ORG@/gpu-bench-suite).

## Update to a newer release

```bash
cd /opt/benchmarks
git pull && git submodule update --init --recursive
```

Copies made before v1.0.5 keep their benchmarks in a `benchmarks/` subfolder;
delete those and clone again as shown under Install.

## Benchmarks

@ROWS@
README
)
  text=${text//@PLATFORM@/"${plat}"}
  text=${text//@VENDOR@/"${vendor}"}
  text=${text//@STACK@/"${stack}"}
  text=${text//@OS@/"${os}"}
  text=${text//@ORG@/"${ORG}"}
  text=${text//@BUNDLE@/"${bundle}"}
  text=${text//@WANT@/"${want}"}
  text=${text//@VERSION@/"${VERSION}"}
  text=${text//@S@/"${s}"}
  text=${text//@ROWS@/"${rows}"}
  printf '%s\n' "${text}"
}


# ==============================================================================
# STEP 0: PREFLIGHT
# ==============================================================================

[[ -n "${RUN_ARG}" ]] || { usage; echo; echo "${SCRIPT_NAME}: give the run folder, for example ${RUN_FOLDER_NAME}" >&2; exit 2; }
not_a_run_folder() {
  case "/${1%/}" in
    *_PubTree* | *_Bundles* | */[1-4][0-9][0-9]-* | */999-* | */"${GENREPO}") return 0 ;;
  esac
  return 1
}
not_a_run_folder "${RUN_ARG}" && stop "${RUN_ARG} is not a run folder (it is a _PubTree, _Bundles or workload folder). Give the run folder, for example ${RUN_FOLDER_NAME}."
# This script never creates or fills the run folder: that is done by hand.
[[ -d "${RUN_ARG}" ]] || stop "the run folder ${RUN_ARG} does not exist (looked from $(pwd)). Create it and copy in the generator and the workloads first (see the top of this file), then run again. Use \"/\" in the path, not \"\\\"."
cd "${RUN_ARG}" || stop "cannot open the run folder ${RUN_ARG} (from $(pwd)). Use \"/\" in the path, not \"\\\"."
GEN="${PWD}"
PUB="${GEN}_PubTree"
WORK="${GEN}_Bundles"
WORKSPACE="$(dirname "${GEN}")"
readonly GEN PUB WORK WORKSPACE
not_a_run_folder "${GEN}" && stop "${GEN} is not a run folder (it is a _PubTree, _Bundles or workload folder). Give the run folder, the one holding the workloads and ${GENREPO}."
command -v gh >/dev/null || stop "the gh command (GitHub CLI) is not installed"
gh auth status >/dev/null 2>&1 || stop "gh is not logged in to GitHub. Run: gh auth login"
mkdir -p "${PUB}/_logs" || stop "cannot create ${PUB}"
touch "${PUB}/_logs/ready.txt" "${PUB}/_logs/published.txt"
LOG="${PUB}/_logs/run-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "${LOG}") 2>&1

step 0 "Preflight"

# Check what was copied into the run folder by hand. Nothing is copied or
# changed here.
echo "Checking the run folder ${GEN} (this script copies nothing into it)"
errors=""
gaps=""
for digit in 1 2 3 4; do
  nums=""
  count=0
  for d in "${GEN}/${digit}"[0-9][0-9]-*/; do
    [[ -d "${d}" ]] || continue
    name=$(basename "${d}")
    nums="${nums}${name:0:3}"$'\n'
    count=$((count + 1))
  done
  dups=$(printf '%s' "${nums}" | sort | uniq -d | tr '\n' ' ')
  [[ -z "${dups}" ]] || errors="${errors}  ${digit}xx: more than one folder for workload ${dups}(for example a leftover *_copy folder)"$'\n'
  outside=$(printf '%s' "${nums}" | awk -v lo=$((digit * 100 + 1)) -v hi=$((digit * 100 + BATCH_SIZE)) 'NF && ($1 + 0 < lo || $1 + 0 > hi)' | sort -u | tr '\n' ' ')
  [[ -z "${outside}" ]] || errors="${errors}  ${digit}xx: workload numbers outside ${digit}01-${digit}$(printf '%02d' "${BATCH_SIZE}"): ${outside}"$'\n'
  missing=""
  for ((i = 1; i <= BATCH_SIZE; i++)); do
    num=$(printf '%d%02d' "${digit}" "${i}")
    grep -qx "${num}" <<<"${nums}" || missing="${missing} ${num}"
  done
  if ((count == 0)); then
    gaps="${gaps}  ${digit}xx ($(platform "${digit}")): no workloads at all"$'\n'
  elif [[ -n "${missing}" ]]; then
    gaps="${gaps}  ${digit}xx ($(platform "${digit}")): missing${missing}"$'\n'
  fi
  printf '%sxx: %2d workload folders   (%s)\n' "${digit}" "${count}" "$(platform "${digit}")"
done
# Anything else at the top of the run folder is not published (step 1 copies
# only workload folders), but may be a sign of a wrong cp command.
others=$(find "${GEN}" -mindepth 1 -maxdepth 1 \
           ! \( -type d -name '[1-4][0-9][0-9]-*' \) ! -name "${GENREPO}" ! -name "${OLD_GENREPO}" -printf '%f\n' | sort)
if [[ -n "${others}" ]]; then
  echo "NOTE: the run folder also holds these, which will not be published:"
  printf '%s\n' "${others}" | head -n 20 | sed 's/^/        /'
fi
[[ -z "${errors}" ]] || { printf '%s' "${errors}"; stop "the run folder ${GEN} has the problems listed above. Remove the extra folders from it and run again."; }
if [[ -n "${gaps}" ]]; then
  printf '%s' "${gaps}"
  if [[ "${REQUIRE_FULL_RUN}" == yes ]]; then
    stop "the run folder ${GEN} is missing the workloads listed above. Copy them in, or set REQUIRE_FULL_RUN=\"no\" near the top of this file to publish only what is there, and run again."
  fi
  echo "NOTE: publishing only the workloads that are there (REQUIRE_FULL_RUN=\"no\")"
fi

N=$(find "${GEN}" -mindepth 1 -maxdepth 1 -type d -name '[1-4][0-9][0-9]-*' | wc -l)
((N > 0)) || stop "no workload folders (101-..., 201-... and so on) in ${GEN}. Copy them in first (see the top of this file)."
if [[ ! -d "${GEN}/${GENREPO}" ]]; then
  [[ -d "${GEN}/${OLD_GENREPO}" ]] && stop "the generator folder in ${GEN} has the old name ${OLD_GENREPO}. Rename it to ${GENREPO} and run again."
  stop "${GENREPO} not found in ${GEN}. Copy the generator into the run folder first (see the top of this file)."
fi
# The generator being published should hold the master copy of this script.
if [[ ! -f "${GEN}/${GENREPO}/scripts/${SCRIPT_NAME}" ]]; then
  echo "NOTE: ${GENREPO}/scripts/ has no ${SCRIPT_NAME}. Consider adding this script there as the master copy."
elif ! cmp -s "${SCRIPT_DIR}/${SCRIPT_NAME}" "${GEN}/${GENREPO}/scripts/${SCRIPT_NAME}"; then
  echo "NOTE: this script differs from ${GENREPO}/scripts/${SCRIPT_NAME} in the run folder."
  echo "      The generator holds the master copy; copy it over this one if it is newer."
fi
# The generator's CI runs ruff; catch a lint error now, before hours of
# publishing, instead of on GitHub after step 9.
lint_generator "${GEN}/${GENREPO}"
# Git for Windows refuses a repository folder ($GIT_DIR) longer than 220
# characters (PATH_MAX 260 minus 40), even with core.longpaths. The longest
# one this run creates is a bundle's submodule store:
#   <RUN_FOLDER>_Bundles/bundle-nvidia-ubuntu-2604/.git/modules/<longest workload>
# Step 7 would fail there with "fatal: '$GIT_DIR' too big", so check it now.
case "$(uname -s)" in
  MINGW* | MSYS* | CYGWIN*)
    longest=$(find "${GEN}" -mindepth 1 -maxdepth 1 -type d -name '[1-4][0-9][0-9]-*' -printf '%f\n' | awk '{ if (length($0) > n) { n = length($0); w = $0 } } END { print w }')
    probe="${WORK}/bundle-nvidia-ubuntu-2604/.git/modules/${longest}"
    ((${#probe} <= 220)) || stop "the run folder path is too long for Git on Windows: ${#probe} characters in ${probe} (the limit is 220). Use a shorter run folder name (for example src) or a shorter publish folder path, and run again."
    ;;
esac
if [[ -s "${PUB}/_logs/version.txt" ]]; then
  VERSION=$(cat "${PUB}/_logs/version.txt")
  vnote="already chosen for this run"
else
  first=$(basename "$(find "${GEN}" -mindepth 1 -maxdepth 1 -type d -name '[1-4][0-9][0-9]-*' | sort | head -n 1)")
  last=""
  if gh repo view "${ORG}/${first}" >/dev/null 2>&1; then
    tags=$(gh api "repos/${ORG}/${first}/tags?per_page=100" --jq '.[].name') || stop "could not read the version tags of ${ORG}/${first} from GitHub"
    last=$(printf '%s\n' "${tags}" | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -n 1)
  fi
  if [[ -z "${last}" ]]; then
    VERSION="v1.0.0"
  else
    IFS=. read -r major minor patch <<<"${last#v}"
    VERSION="v${major}.${minor}.$((patch + 1))"
  fi
  echo "${VERSION}" >"${PUB}/_logs/version.txt"
  vnote="newest already on GitHub: ${last:-none}"
fi
[[ ${VERSION} =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || stop "the version \"${VERSION}\" in ${PUB}/_logs/version.txt is not like v1.2.3"
readonly VERSION
echo "Run folder:    ${GEN}"
echo "Publish tree:  ${PUB}"
echo "Bundles:       ${WORK}"
echo "Workspace:     ${WORKSPACE} (shared-workflows and gpu-bench-suite are kept here)"
echo "Workloads:     ${N}"
echo "Version:       ${VERSION} (${vnote})"
echo "Log file:      ${LOG}"
echo "Repositories already in ${ORG}: $(gh repo list "${ORG}" --limit 300 --json name -q '.[].name' | wc -l)"


# ==============================================================================
# STEP 1: COPY THE WORKLOADS INTO THE PUBLISH TREE
# ==============================================================================
# The prepare step deletes files, so it works on copies. Folders already
# copied are left as they are.

step 1 "Copy the workloads into the publish tree"
cd "${GEN}" || stop "cannot open ${GEN}"
copied=0
for dir in [1-4][0-9][0-9]-*; do
  [[ -d "${dir}" ]] || continue
  [[ -e "${PUB}/${dir}" ]] && continue
  cp -a "${dir}" "${PUB}/" || stop "copying ${dir} failed"
  rm -rf "${PUB}/${dir}/.git"
  echo "copied  ${dir}"
  copied=$((copied + 1))
done
cd "${PUB}" || stop "cannot open ${PUB}"
copies=$(find . -mindepth 1 -maxdepth 1 -type d -name '[1-4][0-9][0-9]-*' | wc -l)
echo "Copied now: ${copied}   Workload folders in the publish tree: ${copies}"
((copies == N)) || stop "the publish tree has ${copies} workload folders but the run folder has ${N}. Remove the extra folders from ${PUB}."
bad=""
for d in [1-4][0-9][0-9]-*/; do
  d=${d%/}
  if [[ -d "${d}/.git" ]] && ! in_list "${d}" _logs/ready.txt; then bad="${bad} ${d}"; fi
done
[[ -z "${bad}" ]] || stop "these copies have an old .git folder although this run has not prepared them yet:${bad}. Delete those folders from ${PUB} so they are copied fresh, and run again."


# ==============================================================================
# STEP 2: DRY RUN OF EACH WORKLOAD'S PREPARE SCRIPT
# ==============================================================================
# Workloads already on the ready list (step 3 done) are skipped.

step 2 "Dry run of prepare_github_publish.sh"
fails=0
for dir in [1-4][0-9][0-9]-*; do
  in_list "${dir}" _logs/ready.txt && continue
  if (cd "${dir}" && bash scripts/prepare_github_publish.sh --dry-run) >"_logs/${dir:0:3}-dry-run.log" 2>&1 </dev/null; then
    echo "OK    ${dir}"
  else
    echo "FAIL  ${dir}   (see ${PUB}/_logs/${dir:0:3}-dry-run.log)"
    fails=$((fails + 1))
  fi
done
((fails == 0)) || stop "${fails} workloads failed the dry run. Read their logs, fix them in ${PUB}, and run again."


# ==============================================================================
# STEP 3: PREPARE AND CHECK EACH WORKLOAD
# ==============================================================================
# In every copy not yet ready:
#   prepare_github_publish.sh --apply --in-place --github-owner=<ORG>
#   check_github_publish_ready.sh --published
# A copy is prepared only once: after it passes, it is on the ready list.

step 3 "Prepare and check each workload"
: >_logs/not-ready.txt
for dir in [1-4][0-9][0-9]-*; do
  in_list "${dir}" _logs/ready.txt && continue
  if (cd "${dir}" && bash scripts/prepare_github_publish.sh --apply --in-place --github-owner="${ORG}" &&
      bash scripts/check_github_publish_ready.sh --published) >"_logs/${dir:0:3}.log" 2>&1 </dev/null; then
    echo "${dir}" >>_logs/ready.txt
    echo "READY      ${dir}"
  else
    echo "${dir}" >>_logs/not-ready.txt
    echo "NOT READY  ${dir}   (see ${PUB}/_logs/${dir:0:3}.log)"
  fi
done
not_ready=$(wc -l <_logs/not-ready.txt)
ready=$(sort -u _logs/ready.txt | wc -l)
echo "Ready: ${ready}   Not ready: ${not_ready}"
((not_ready == 0)) || stop "${not_ready} workloads are not ready. Read their logs, fix them in ${PUB}, and run again."
((ready == N)) || stop "${ready} workloads are on the ready list, expected ${N}"


# ==============================================================================
# STEP 4: CLEAN UP AND CHECK WHAT WILL BE PUBLISHED
# ==============================================================================
# Removes TEMPLATE_*_copy, .venv and __pycache__ folders from the copies, then
# checks them for:
# - files over 95 MB (GitHub rejects files over 100 MB)
# - leftover *_copy folders
# - clone links still pointing at github.com/<org>/ or <OWNER>/ (scripts/ is
#   skipped because it contains "<org>" on purpose)
# - the publish doc's "Never publish" list
# - files in results/raw other than .gitkeep or manifest placeholders

if is_done cleanup; then skipped 4; else
  step 4 "Clean up and check what will be published"
  removed=0
  for dir in [1-4][0-9][0-9]-*; do
    r=$({ find "${dir}" -mindepth 1 -maxdepth 1 -type d \( -name 'TEMPLATE_*_copy' -o -name .venv \) -print -exec rm -rf {} +
          find "${dir}" -name .git -prune -o -type d -name __pycache__ -prune -print -exec rm -rf {} +; } | wc -l)
    removed=$((removed + r))
  done
  echo "--- leftover folders removed: ${removed}"
  problems=0
  check_zero "files over 95 MB" < <(find . \( -path ./_logs -o -name .git \) -prune -o -type f -size +95M -print)
  check_zero "leftover *_copy folders" < <(find . \( -path ./_logs -o -name .git \) -prune -o -type d -name '*_copy' -print)
  check_zero "unreplaced <org> clone links" < <(grep -rlE --exclude-dir=_logs --exclude-dir=scripts --exclude-dir=.git 'github\.com/(<org>|<OWNER>)/' .)
  check_zero "never-publish items" < <(find . \( -path ./_logs -o -name .git \) -prune -o \( -name RESULTS -o -name runtime_ledger.csv -o -name '*.zip' -o -name .env -o -name .claude -o -name .venv -o -name '*.pyc' \) -print)
  check_zero "unexpected files in results/raw" < <(find . \( -path ./_logs -o -name .git \) -prune -o -path '*/results/raw/*' -type f -not -name .gitkeep -not -iname '*manifest*' -print)
  echo "--- results/raw placeholders (one per workload is normal): $(find . \( -path ./_logs -o -name .git \) -prune -o -path '*/results/raw/*' -name .gitkeep -print | wc -l)"
  ((problems == 0)) || stop "${problems} problems listed above. Delete those files from the copies in ${PUB} (never from the run folder) and run again."
  mark_done cleanup
fi


# ==============================================================================
# STEP 5: PUBLISH THE SUITE-LEVEL REPOSITORIES
# ==============================================================================
# Both are built from the generator into the workspace (the folder holding the
# run folder) and kept there between runs. Change their content in the
# generator, not in these folders.
#
# shared-workflows: the workloads' .github/workflows/ci.yml and gpu-smoke.yml
#   only call the reusable workflows in this repository at a major tag (@v1).
#   It must exist before step 6 pushes the workloads, or every workload's CI
#   fails with "workflow was not found". After a push, the repository's
#   Self-test must pass before the tag moves: the first release of a major
#   tag is vN.0.0, each later change the next vN.x.0, and vN is moved to it.
#
# gpu-bench-suite: operator tools (scripts/run_benchmark_suite.sh for the GPU
#   host, scripts/get_remote_info.sh for the laptop). Tagged with this run's
#   version. Step 7 copies its run_benchmark_suite.sh into every bundle.
#
# Runs every time; nothing is pushed or tagged when nothing changed.

step 5 "Publish the suite-level repositories"
cd "${PUB}" || stop "cannot open ${PUB}"

# --- 5a. shared-workflows -----------------------------------------------------
# Every "uses: owner/repo/.github/workflows/<file>@<ref>" in the workloads.
calls=$(cat [1-4][0-9][0-9]-*/.github/workflows/*.yml 2>/dev/null | tr -d '\r' |
        grep -oE 'uses:[[:space:]]*[^[:space:]]+/\.github/workflows/[^[:space:]@]+@[^[:space:]]+' |
        sed -E 's/^uses:[[:space:]]*//' | sort -u)
SHARED_REPO=""
MAJOR=""
if [[ -z "${calls}" ]]; then
  echo "The workloads do not call shared workflows: nothing to publish"
else
  targets=$(printf '%s\n' "${calls}" | sed -E 's#^([^/]+/[^/]+)/\.github/workflows/[^@]+@(.*)$#\1@\2#' | sort -u)
  (($(printf '%s\n' "${targets}" | wc -l) == 1)) || stop "the workloads call more than one shared-workflows repository or tag:"$'\n'"${targets}"$'\n'"Regenerate them so they all agree."
  shared_full=${targets%@*}
  MAJOR=${targets#*@}
  SHARED_REPO=${shared_full#*/}
  [[ "${shared_full%%/*}" == "${ORG}" ]] || stop "the workloads call ${shared_full}, which is outside ${ORG}"
  [[ ${MAJOR} =~ ^v[0-9]+$ ]] || stop "the workloads call ${shared_full} at \"${MAJOR}\"; this script only releases major tags like v1"
  called=$(printf '%s\n' "${calls}" | sed -E 's#^.*/\.github/workflows/([^@]+)@.*$#\1#' | sort -u)
  echo "The workloads call ${shared_full}@${MAJOR} for: $(tr "\n" " " <<<"${called}")"

  SHARED_DIR="${WORKSPACE}/${SHARED_REPO}"
  emit_repo shared-workflows "${SHARED_DIR}"
  for f in ${called} self-test.yml; do
    [[ -f "${SHARED_DIR}/.github/workflows/${f}" ]] || stop "the generator did not write .github/workflows/${f} in ${SHARED_DIR}"
  done

  cd "${SHARED_DIR}" || stop "cannot open ${SHARED_DIR}"
  [[ -d .git ]] || git init -q -b main || stop "git init failed in ${SHARED_DIR}"
  use_github_repo "${SHARED_REPO}" "Reusable GitHub Actions workflows called by every GPU benchmark workload repository" || stop "could not create ${ORG}/${SHARED_REPO}"
  visibility=$(gh repo view "${ORG}/${SHARED_REPO}" --json visibility -q .visibility)
  [[ "${visibility}" == PUBLIC ]] || stop "${ORG}/${SHARED_REPO} is ${visibility}. Public workload repositories can only call a public repository. Make it public (Settings, General, Danger Zone) and run again."
  commit_all "Initial shared workflows from ${GENREPO} ${VERSION}" "Update from ${GENREPO} ${VERSION}" || stop "committing ${SHARED_REPO} failed"
  git push -u origin main </dev/null || stop "pushing ${SHARED_REPO} failed"
  again git fetch -q --tags --force origin </dev/null || stop "could not read the tags of ${ORG}/${SHARED_REPO}"

  head=$(git rev-parse HEAD)
  current=$(git rev-parse -q --verify "refs/tags/${MAJOR}^{commit}" 2>/dev/null)
  if [[ "${current}" == "${head}" ]]; then
    echo "${MAJOR} already points at the newest commit: no new release needed"
  else
    wait_self_test "${head}" </dev/null || stop "the Self-test of ${SHARED_REPO} did not pass, so ${MAJOR} was not moved and no workload was pushed. Open the run above, fix templates/shared-workflows in the generator, and run again (or re-run that Self-test on GitHub if it failed by chance)."
    latest=$(git tag -l "${MAJOR}.*" | grep -E "^${MAJOR}\.[0-9]+\.[0-9]+$" | sort -V | tail -n 1)
    if [[ -z "${latest}" ]]; then
      release="${MAJOR}.0.0"
    elif [[ "$(git rev-parse "${latest}^{commit}")" == "${head}" ]]; then
      release=${latest}  # released by an interrupted earlier attempt
    else
      IFS=. read -r _ minor _ <<<"${latest#v}"
      release="${MAJOR}.$((minor + 1)).0"
    fi
    git rev-parse -q --verify "refs/tags/${release}" >/dev/null ||
      again git tag -a "${release}" -m "${SHARED_REPO} ${release} (from ${GENREPO} ${VERSION})" || stop "tagging ${SHARED_REPO} with ${release} failed"
    git push origin "refs/tags/${release}" </dev/null || stop "pushing the ${release} tag of ${SHARED_REPO} failed"
    git tag -f "${MAJOR}" "${release}^{commit}" >/dev/null || stop "moving ${MAJOR} failed"
    git push -f origin "refs/tags/${MAJOR}" </dev/null || stop "pushing the ${MAJOR} tag of ${SHARED_REPO} failed"
    echo "Released ${SHARED_REPO} ${release} and moved ${MAJOR} to it"
  fi
  gh repo edit "${ORG}/${SHARED_REPO}" --add-topic gpu-benchmark --add-topic github-actions >/dev/null 2>&1

  # The check GitHub itself makes when a workload runs CI.
  for f in ${called}; do
    gh api "repos/${ORG}/${SHARED_REPO}/contents/.github/workflows/${f}?ref=${MAJOR}" --silent </dev/null ||
      stop "${ORG}/${SHARED_REPO} has no .github/workflows/${f} at ${MAJOR}, so the workloads' CI would fail"
  done
  echo "Workload CI can reach ${shared_full} at ${MAJOR}"
fi

# --- 5b. gpu-bench-suite ------------------------------------------------------
TOOLS_REPO=$(sed -nE 's/^[[:space:]]*tools_repo:[[:space:]]*([A-Za-z0-9_.-]+).*/\1/p' "${GEN}/${GENREPO}/config/ci_contract.yaml" 2>/dev/null | head -n 1)
TOOLS_DIR=""
echo
if [[ -z "${TOOLS_REPO}" ]]; then
  echo "The generator's config/ci_contract.yaml names no tools_repo: no operator tools to publish"
else
  TOOLS_DIR="${WORKSPACE}/${TOOLS_REPO}"
  emit_repo suite-tools "${TOOLS_DIR}"
  [[ -f "${TOOLS_DIR}/scripts/run_benchmark_suite.sh" ]] || stop "the generator did not write scripts/run_benchmark_suite.sh in ${TOOLS_DIR}"
  cd "${TOOLS_DIR}" || stop "cannot open ${TOOLS_DIR}"
  [[ -d .git ]] || git init -q -b main || stop "git init failed in ${TOOLS_DIR}"
  use_github_repo "${TOOLS_REPO}" "Operator tools for the GPU benchmark suite: run every workload on a GPU host, collect the results to your laptop" || stop "could not create ${ORG}/${TOOLS_REPO}"
  commit_all "Initial operator tools from ${GENREPO} ${VERSION}" "Update from ${GENREPO} ${VERSION}" || stop "committing ${TOOLS_REPO} failed"
  git push -u origin main </dev/null || stop "pushing ${TOOLS_REPO} failed"
  # A tag this run left on an older commit is kept (with a note) rather than
  # stopping the run: these are tools, not pinned benchmarks.
  git fetch -q origin "refs/tags/${VERSION}:refs/tags/${VERSION}" </dev/null >/dev/null 2>&1
  if ! git rev-parse -q --verify "refs/tags/${VERSION}" >/dev/null; then
    tag_version "${TOOLS_REPO} ${VERSION} (from ${GENREPO})" || stop "tagging ${TOOLS_REPO} with ${VERSION} failed"
  elif [[ "$(git rev-parse "${VERSION}^{commit}")" != "$(git rev-parse HEAD)" ]]; then
    echo "NOTE: ${TOOLS_REPO} already has a ${VERSION} tag on an older commit; the newest commit is on main, untagged."
  fi
  gh repo edit "${ORG}/${TOOLS_REPO}" --add-topic gpu-benchmark --add-topic benchmark-suite >/dev/null 2>&1
  echo "${TOOLS_REPO} is published: https://github.com/${ORG}/${TOOLS_REPO}"
fi

# Where the bundles get run_benchmark_suite.sh: the generator's copy, or, for
# a generator without suite tools, a copy next to this script.
SUITE_SCRIPT="${TOOLS_DIR:+${TOOLS_DIR}/scripts/run_benchmark_suite.sh}"
[[ -n "${SUITE_SCRIPT}" && -f "${SUITE_SCRIPT}" ]] || SUITE_SCRIPT="${SCRIPT_DIR}/run_benchmark_suite.sh"
cd "${PUB}" || stop "cannot open ${PUB}"


# ==============================================================================
# STEP 6: PUBLISH THE WORKLOADS
# ==============================================================================
# - Creates each repository on the first run; a later run puts a new commit on
#   top of the existing history.
# - Tags each repository with this run's version.
# - Each git step is tried 4 times (Windows antivirus or indexing can briefly
#   lock files in .git). Workloads that still fail are retried twice from a
#   fresh .git folder before the script stops.
# - Workloads already published by this run are skipped.

step 6 "Publish the workloads (${VERSION})"
newly=0
: >_logs/publish-failed.txt
# shellcheck disable=SC2013  # workload names have no spaces
for dir in $(sort -u _logs/ready.txt); do
  in_list "${dir}" _logs/published.txt && continue
  echo "=================================================="
  echo "Publishing ${dir}"
  if publish_workload "${dir}" keep </dev/null; then
    echo "${dir}" >>_logs/published.txt
    echo "OK      ${dir}"
    newly=$((newly + 1))
  else
    echo "${dir}" >>_logs/publish-failed.txt
    echo "FAILED  ${dir}"
  fi
  sleep 2
done
for round in 1 2; do
  [[ -s _logs/publish-failed.txt ]] || break
  echo
  echo "Retrying $(wc -l <_logs/publish-failed.txt) failed workloads from a fresh .git folder (round ${round} of 2), in 30 seconds"
  sleep 30
  mv _logs/publish-failed.txt _logs/retry.txt
  : >_logs/publish-failed.txt
  while read -r dir; do
    [[ -n "${dir}" ]] || continue
    echo "=================================================="
    echo "Retrying ${dir}"
    if publish_workload "${dir}" fresh </dev/null; then
      echo "${dir}" >>_logs/published.txt
      echo "OK      ${dir}"
      newly=$((newly + 1))
    else
      echo "${dir}" >>_logs/publish-failed.txt
      echo "FAILED  ${dir}"
    fi
    sleep 2
  done <_logs/retry.txt
done
published=$(sort -u _logs/published.txt | wc -l)
echo "Published now: ${newly}   Published by this run in total: ${published} of ${N}"
if [[ -s _logs/publish-failed.txt ]]; then
  cat _logs/publish-failed.txt
  stop "the workloads above could not be published. The error is printed above each FAILED line. If it says a tag already exists, that version was used before: put a new one in ${PUB}/_logs/version.txt."
fi
((published == N)) || stop "${published} workloads published, expected ${N}"
if ((newly > 0)); then rm -f _logs/done-bundles _logs/done-enduser-test _logs/done-generator; fi


# ==============================================================================
# STEP 7: BUILD AND PUBLISH THE 4 BUNDLE REPOSITORIES
# ==============================================================================
# Each bundle holds its 32 workloads as git submodules pinned to this run's
# version, at the top level under their full repository names, plus run.sh,
# run_benchmark_suite.sh and a README for the technician. Cloning a bundle
# into /opt/benchmarks puts the workloads straight into /opt/benchmarks.

if is_done bundles; then skipped 7; else
  step 7 "Build and publish the 4 bundle repositories"
  mkdir -p "${WORK}" || stop "cannot create ${WORK}"
  write_bundle_run_sh "${WORK}/run.sh.template"
  if [[ -f "${SUITE_SCRIPT}" ]]; then echo "run_benchmark_suite.sh for the bundles: ${SUITE_SCRIPT}"; else echo "NOTE: no run_benchmark_suite.sh found; the bundles will not include it"; fi
  for spec in "amd-ubuntu-2404:1" "nvidia-ubuntu-2404:2" "amd-ubuntu-2604:3" "nvidia-ubuntu-2604:4"; do
    IFS=: read -r name s <<<"${spec}"
    bundle="bundle-${name}"
    want=$(sort -u "${PUB}/_logs/published.txt" | grep -c "^${s}")
    ((want > 0)) || continue
    echo "=================================================="
    echo "Building ${bundle} at ${VERSION} (${want} benchmarks)"
    mkdir -p "${WORK}/${bundle}"
    cd "${WORK}/${bundle}" || stop "cannot open ${WORK}/${bundle}"
    [[ -d .git ]] || git init -q -b main || stop "git init failed in ${WORK}/${bundle}"
    use_github_repo "${bundle}" "All ${want} $(platform "${s}") benchmarks, pinned as git submodules" || stop "could not create ${ORG}/${bundle}"
    rows=""
    # shellcheck disable=SC2013  # workload names have no spaces
    for dir in $(sort -u "${PUB}/_logs/published.txt" | grep "^${s}"); do
      add_submodule "${dir}" "${dir}" </dev/null || stop "could not add ${dir} to ${bundle}"
      if ! git -C "${dir}" rev-parse -q --verify "refs/tags/${VERSION}" >/dev/null; then
        again git -C "${dir}" fetch -q --tags origin </dev/null || stop "could not fetch the tags of ${dir}"
      fi
      git -C "${dir}" -c advice.detachedHead=false checkout -q "${VERSION}" || stop "${dir} has no ${VERSION} tag on GitHub"
      again git add "${dir}" || stop "git add failed for ${dir} in ${bundle}"
      rows="${rows}- **${dir:0:3}** - [${dir}](https://github.com/${ORG}/${dir})"$'\n'
    done
    cp "${WORK}/run.sh.template" run.sh
    suite_files=""
    if [[ -f "${SUITE_SCRIPT}" ]]; then
      tr -d '\r' <"${SUITE_SCRIPT}" >run_benchmark_suite.sh
      suite_files="run_benchmark_suite.sh"
    fi
    printf 'results/\nbenchmark_suite_log/\n' >.gitignore
    bundle_readme "${s}" "${bundle}" "${want}" "${rows}" >README.md
    # shellcheck disable=SC2086  # suite_files is empty or one name
    again git add .gitmodules .gitignore README.md run.sh ${suite_files} || stop "git add failed in ${bundle}"
    # shellcheck disable=SC2086
    git update-index --chmod=+x run.sh ${suite_files}
    attach_history </dev/null || stop "could not read the history of ${ORG}/${bundle}"
    git diff --cached --quiet || again git commit -q -m "Pin $(platform "${s}") benchmarks at ${VERSION}" || stop "git commit failed in ${bundle}"
    git push -u origin main </dev/null || stop "pushing ${bundle} failed"
    tag_version "${bundle} ${VERSION}" || stop "tagging ${bundle} with ${VERSION} failed"
    gh release view "${VERSION}" -R "${ORG}/${bundle}" >/dev/null 2>&1 ||
      gh release create "${VERSION}" -R "${ORG}/${bundle}" --title "${bundle} ${VERSION}" \
        --notes "Clone with: git clone --recurse-submodules --branch ${VERSION} https://github.com/${ORG}/${bundle}.git (the Source code downloads below do not include the submodules)." ||
      stop "creating the ${VERSION} release of ${bundle} failed"
    gh repo edit "${ORG}/${bundle}" --add-topic gpu-benchmark --add-topic benchmark-suite >/dev/null 2>&1
    got=$(git submodule status | wc -l)
    echo "${bundle}: ${got} submodules"
    ((got == want)) || stop "${bundle} has ${got} submodules, expected ${want}"
  done
  cd "${PUB}" || stop "cannot open ${PUB}"
  mark_done bundles
fi


# ==============================================================================
# STEP 8: TEST ONE BUNDLE LIKE AN END USER
# ==============================================================================

if is_done enduser-test; then skipped 8; else
  step 8 "Test bundle-amd-ubuntu-2404 like an end user"
  want=$(sort -u "${PUB}/_logs/published.txt" | grep -c '^1')
  if ((want > 0)); then
    rm -rf "${WORK}/_test_clone"
    git -c advice.detachedHead=false clone -q --recurse-submodules --branch "${VERSION}" \
      "https://github.com/${ORG}/bundle-amd-ubuntu-2404.git" "${WORK}/_test_clone" </dev/null ||
      stop "cloning bundle-amd-ubuntu-2404 at ${VERSION} failed"
    got=$(cd "${WORK}/_test_clone" && ./run.sh list | grep -c ' ready$')
    (cd "${WORK}/_test_clone" && ./run.sh list | head -n 3)
    echo "Benchmarks ready in the test clone: ${got} of ${want}"
    for f in run.sh run_benchmark_suite.sh; do
      [[ ! -f "${WORK}/_test_clone/${f}" || -x "${WORK}/_test_clone/${f}" ]] || stop "${f} in the bundle is not executable"
    done
    rm -rf "${WORK}/_test_clone"
    ((got == want)) || stop "only ${got} of ${want} benchmarks came down with the bundle"
  fi
  cd "${PUB}" || stop "cannot open ${PUB}"
  mark_done enduser-test
fi


# ==============================================================================
# STEP 9: PUBLISH THE GENERATOR
# ==============================================================================
# Rules from the publish doc:
# - Keep root LICENSE, legal/NOTICE, .gitattributes and .gitignore.
# - Do not publish generated workload folders, RESULTS/, runtime_ledger.csv,
#   *.zip, operator logs, credentials, downloaded weights, or live machine
#   inventories, nor a nested TEMPLATE_*_copy/ generation workspace.
# Works on a copy in the _PubTree. If the checks list anything, delete it from
# that copy (${PUB}/${GENREPO}) and run again; the copy is kept between runs
# so deletions stay deleted.

if is_done generator; then skipped 9; else
  step 9 "Publish the generator (${GENREPO})"
  cd "${GEN}/${GENREPO}" || stop "cannot open ${GEN}/${GENREPO}"
  big=$(find . -path ./.git -prune -o -type f -size +95M -print)
  [[ -z "${big}" ]] || stop "files over 95 MB in the generator (GitHub rejects over 100 MB): ${big}"
  # Real tokens, and real private keys (a "BEGIN ... PRIVATE KEY" line followed
  # by a line of key data). A file that only names the BEGIN line as a search
  # pattern is not flagged.
  tokens=$({ grep -rIlE --exclude-dir=.git '(ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|hf_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16})' .
             grep -rIl --exclude-dir=.git -e '-----BEGIN [A-Z ]*PRIVATE KEY-----' . | while read -r f; do
               awk '/-----BEGIN [A-Z ]*PRIVATE KEY-----/ { if ((getline n) > 0) { sub(/\r$/, "", n); if (length(n) >= 40 && n ~ /^[A-Za-z0-9+\/=]+$/) { print FILENAME; exit } } }' "${f}"
             done; } | sort -u | head)
  [[ -z "${tokens}" ]] || stop "files that contain what looks like a real token or private key in the generator: ${tokens}"

  # GitHub answers for an old repository name with the renamed repository, so
  # compare the name it reports, not just whether the lookup succeeds.
  if [[ "$(gh repo view "${ORG}/${GENREPO}" --json name -q .name 2>/dev/null)" != "${GENREPO}" ]] &&
     [[ "$(gh repo view "${ORG}/${OLD_GENREPO}" --json name -q .name 2>/dev/null)" == "${OLD_GENREPO}" ]]; then
    echo "Renaming ${ORG}/${OLD_GENREPO} to ${GENREPO} (history, tags and Actions runs are kept)"
    gh repo rename "${GENREPO}" -R "${ORG}/${OLD_GENREPO}" --yes || stop "renaming ${ORG}/${OLD_GENREPO} to ${GENREPO} failed. Rename it under Settings, General, Repository name, and run again."
  fi
  if gh repo view "${ORG}/${GENREPO}" >/dev/null 2>&1; then
    echo "${ORG}/${GENREPO} already exists: adding ${VERSION} on top of its history"
  elif gh repo view "${PERSONAL_GENERATOR}" >/dev/null 2>&1; then
    case "${TRANSFER_PERSONAL_GENERATOR}" in
      yes)
        echo "Moving ${PERSONAL_GENERATOR} into ${ORG} as ${GENREPO}"
        gh api -X POST "repos/${PERSONAL_GENERATOR}/transfer" -f new_owner="${ORG}" -f new_name="${GENREPO}" --jq .full_name || stop "moving ${PERSONAL_GENERATOR} failed"
        for _ in 1 2 3 4 5 6; do gh repo view "${ORG}/${GENREPO}" >/dev/null 2>&1 && break; sleep 10; done
        gh repo view "${ORG}/${GENREPO}" >/dev/null 2>&1 || stop "the move was requested but ${ORG}/${GENREPO} is not there yet. Wait a minute and run again."
        ;;
      no)
        echo "Leaving ${PERSONAL_GENERATOR} alone; publishing a fresh copy"
        ;;
      *)
        stop "GitHub already has ${PERSONAL_GENERATOR}. Near the top of this file, set TRANSFER_PERSONAL_GENERATOR=\"yes\" to move it into ${ORG} with its history, or \"no\" to leave it and publish a fresh copy." ;;
    esac
  fi

  if [[ ! -d "${PUB}/${GENREPO}" ]]; then
    cp -a "${GEN}/${GENREPO}" "${PUB}/" || stop "copying the generator failed"
    rm -rf "${PUB}/${GENREPO}/.git"
    echo "copied  ${GENREPO}"
  fi
  cd "${PUB}/${GENREPO}" || stop "cannot open ${PUB}/${GENREPO}"
  # Python caches come along with cp -a whenever the generator's scripts or
  # tests were run before the copy. They are never published.
  removed=$(find . -path ./.git -prune -o -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache -o -name .mypy_cache \) -prune -print -exec rm -rf {} + | wc -l)
  removed=$((removed + $(find . -path ./.git -prune -o -type f -name '*.py[co]' -print -delete | wc -l)))
  echo "--- Python cache folders and files removed: ${removed}"
  # The copy is kept between runs, so lint it too: it is what gets pushed.
  lint_generator "${PUB}/${GENREPO}"
  problems=0
  check_zero "nested *_copy and .git folders" < <(find . -mindepth 1 \( -path ./.git -prune \) -o -type d \( -name '*_copy' -o -name .git \) -print)
  check_zero "never-publish items and generated workload folders" < <(find . -path ./.git -prune -o \( -name RESULTS -o -name runtime_ledger.csv -o -name '*.zip' -o -name .env -o -name .venv -o -name __pycache__ -o -name '*.py[co]' -o -type d -name '[1-4][0-9][0-9]-*' \) -print)
  missing=""
  for f in LICENSE legal/NOTICE .gitattributes .gitignore; do [[ -e "${f}" ]] || missing="${missing} ${f}"; done
  echo "--- files the publish doc says to keep, missing (must be none):${missing:- none}"
  [[ -z "${missing}" ]] || problems=$((problems + 1))
  ((problems == 0)) || stop "fix the generator copy in ${PUB}/${GENREPO} (delete what is listed, or restore missing files) and run again"

  [[ -d .git ]] || git init -q -b main || stop "git init failed in the generator copy"
  use_github_repo "${GENREPO}" "Spec-driven generator that builds the GPU benchmark workload repositories" || stop "could not create ${ORG}/${GENREPO}"
  commit_all "Initial import of the benchmark repository generator" "Update generator to ${VERSION}" || stop "committing the generator failed"
  git push -u origin main </dev/null || stop "pushing the generator failed"
  tag_version "${GENREPO} ${VERSION}" || stop "tagging the generator with ${VERSION} failed"
  gh repo edit "${ORG}/${GENREPO}" --add-topic gpu-benchmark --add-topic code-generation --add-topic ai-agents >/dev/null 2>&1
  if [[ -d "${GEN}/${GENREPO}/.git" ]]; then git -C "${GEN}/${GENREPO}" remote set-url origin "https://github.com/${ORG}/${GENREPO}.git" 2>/dev/null; fi
  cd "${PUB}" || stop "cannot open ${PUB}"
  mark_done generator
fi


# ==============================================================================
# FINISHED
# ==============================================================================

echo
echo "======================================================================"
echo "FINISHED: ${N} workloads, the bundles and the generator are published as ${VERSION}"
[[ -n "${SHARED_REPO}" ]] && echo "Shared CI:      ${ORG}/${SHARED_REPO}, called by the workloads at ${MAJOR}"
[[ -n "${TOOLS_REPO}" ]] && echo "Operator tools: ${ORG}/${TOOLS_REPO} at ${VERSION}"
echo "Repositories in ${ORG}: $(gh repo list "${ORG}" --limit 300 --json name -q '.[].name' | wc -l)"
echo "Log file: ${LOG}"
print_times "Completed time:"
echo "======================================================================"
