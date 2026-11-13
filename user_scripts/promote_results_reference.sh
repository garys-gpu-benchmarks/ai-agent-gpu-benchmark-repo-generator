#!/usr/bin/env bash
# ==============================================================================
# promote_results_reference.sh
#
# Replaces each workload repository's committed RESULTS_REFERENCE.md (written at
# generation from a smoke run) with the results of a full run you collected,
# so the published page shows real baseline numbers (TEMPLATE_00_135).
#
#   1. Run the suite on the benchmark machine:   ./run_benchmark_suite.sh --baseline
#   2. Collect it on your PC:                     ./get_benchmark_results.sh --host HOST
#      (copies DIRECTORIES/<workload>/results/RESULTS_ACTUAL.md)
#   3. Promote it into the repositories you are about to publish (the publish
#      run folder, or a project's TEMPLATE_00_NNN folder):
#        ./promote_results_reference.sh --results <collection folder> --repos <folder>
#   4. Review the changes it lists, then publish as usual.
#
# Only sections whose run exited 0 are promoted. A workload with no passed run
# of the chosen profile keeps its current RESULTS_REFERENCE.md. Each repository's
# own scripts/results_markdown.py writes the page, so the format always matches
# that repository's version.
#
# Usage:   ./promote_results_reference.sh --results DIR --repos DIR [options]
# Help:    ./promote_results_reference.sh --help
# Runs on: Git Bash on Windows, Linux, macOS. Needs Python 3.
# ==============================================================================
set -uo pipefail

SCRIPT_NAME=$(basename "$0")
results_dir=""
repos_dir=""
profiles="baseline"
template_version=""
dry_run=false

usage() {
  cat <<EOF
Usage: ${SCRIPT_NAME} --results DIR --repos DIR [options]

Copies the collected results of a full run into each workload repository's
committed RESULTS_REFERENCE.md.

Required:
  --results DIR          Output folder of get_benchmark_results.sh (the folder that
                         holds DIRECTORIES/), or that DIRECTORIES folder itself.
  --repos DIR            Folder holding the workload repositories to publish
                         (<NNN>-<name>/ folders): the publish run folder or a
                         project's TEMPLATE_00_NNN folder.

Options:
  --profiles LIST        Profiles to publish, comma-separated (default: baseline).
                         Example: --profiles baseline,extended
  --template-version V   Generator version shown on the page (default: taken from
                         a TEMPLATE_00_NNN folder in the --repos path).
  --dry-run              Show what would change; write nothing.
  -h, --help             Show this help.

Example:
  ./${SCRIPT_NAME} --results ~/results_20261112 --repos /z/Publishing/20261112_01/src_490_491_492_493
EOF
}

die() { echo "ERROR: $*" >&2; exit 2; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --results) results_dir="${2:-}"; shift 2 ;;
    --results=*) results_dir="${1#*=}"; shift ;;
    --repos) repos_dir="${2:-}"; shift 2 ;;
    --repos=*) repos_dir="${1#*=}"; shift ;;
    --profiles) profiles="${2:-}"; shift 2 ;;
    --profiles=*) profiles="${1#*=}"; shift ;;
    --template-version) template_version="${2:-}"; shift 2 ;;
    --template-version=*) template_version="${1#*=}"; shift ;;
    --dry-run) dry_run=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown option: $1" ;;
  esac
done

[[ -n "${results_dir}" ]] || { usage >&2; die "give --results DIR"; }
[[ -n "${repos_dir}" ]] || { usage >&2; die "give --repos DIR"; }
[[ -d "${repos_dir}" ]] || die "--repos folder not found: ${repos_dir}"
if [[ -d "${results_dir}/DIRECTORIES" ]]; then
  directories="${results_dir}/DIRECTORIES"
elif [[ -d "${results_dir}" ]]; then
  directories="${results_dir}"
else
  die "--results folder not found: ${results_dir}"
fi
[[ "${profiles}" =~ ^(smoke|baseline|extended)(,(smoke|baseline|extended))*$ ]] \
  || die "--profiles takes smoke, baseline and/or extended, comma-separated"

if [[ -z "${template_version}" ]]; then
  template_version=$(cd "${repos_dir}" && pwd -P | tr '/' '\n' | grep -E '^TEMPLATE_[0-9]+_[0-9]+$' | tail -n 1 || true)
fi

python_bin=""
for candidate in python3 python py; do
  if command -v "${candidate}" >/dev/null 2>&1 && "${candidate}" -c 'import sys; sys.exit(sys.version_info < (3, 8))' >/dev/null 2>&1; then
    python_bin="${candidate}"
    break
  fi
done
[[ -n "${python_bin}" ]] || die "Python 3 is needed (python3, python or py on PATH)"

today=$(date -u +%Y-%m-%d)
promoted=0 kept=0 missing=0
tmp=$(mktemp -d) || die "cannot create a temporary folder"
trap 'rm -rf "${tmp}"' EXIT

shopt -s nullglob
for repo in "${repos_dir}"/[1-4][0-9][0-9]-*/; do
  repo=${repo%/}
  name=$(basename "${repo}")
  actual="${directories}/${name}/results/RESULTS_ACTUAL.md"
  writer="${repo}/scripts/results_markdown.py"
  if [[ ! -f "${actual}" ]]; then
    printf '%-62s no collected RESULTS_ACTUAL.md; kept\n' "${name}"
    missing=$((missing + 1))
    continue
  fi
  if [[ ! -f "${writer}" ]]; then
    printf '%-62s repository has no scripts/results_markdown.py (older than TEMPLATE_00_135); kept\n' "${name}"
    kept=$((kept + 1))
    continue
  fi
  out="${tmp}/${name}.md"
  message=$("${python_bin}" "${writer}" --reference-from "${actual}" --out "${out}" \
    --profiles "${profiles}" --require-pass --template-version "${template_version}" --generated "${today}" 2>&1)
  if [[ ! -f "${out}" ]]; then
    printf '%-62s %s; kept\n' "${name}" "${message#SKIP: }"
    kept=$((kept + 1))
    continue
  fi
  target="${repo}/RESULTS_REFERENCE.md"
  if [[ -f "${target}" ]] && cmp -s "${out}" "${target}"; then
    printf '%-62s unchanged\n' "${name}"
    continue
  fi
  if ${dry_run}; then
    printf '%-62s would promote %s\n' "${name}" "${profiles}"
  else
    cp "${out}" "${target}" || die "cannot write ${target}"
    printf '%-62s promoted %s\n' "${name}" "${profiles}"
  fi
  promoted=$((promoted + 1))
done

echo
if ${dry_run}; then
  echo "Dry run: ${promoted} would change, ${kept} kept (no passed ${profiles} run), ${missing} not collected."
else
  echo "Promoted: ${promoted}   kept: ${kept} (no passed ${profiles} run)   not collected: ${missing}"
  [[ ${promoted} -gt 0 ]] && echo "Review with: git -C <repo> diff RESULTS_REFERENCE.md   (then publish as usual)"
fi
exit 0
