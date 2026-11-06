#!/usr/bin/env bash
# File: scripts/prepare_github_publish.sh
# Version: 1.2.0
# Maintainer: AI Agent GPU Benchmark Repo Generator
# Date: 2026-10-08
# Description: Final cleanup of a generated workload before independent GitHub publication.
# Execution: bash scripts/prepare_github_publish.sh [--dry-run|--apply] [--in-place] [--git-init] [--github-owner=OWNER]
# Options: --dry-run (default), --apply, --in-place, --git-init, --github-owner=OWNER
# Requirements: bash, python3, find, sed
# Environment: Run from a generated workload repository root.
# Dependencies: benchmark_specification.json, setup.sh, run_benchmark.sh
# Variables: none
# Repository: gpu-bench/sys-bench template
# License: Apache-2.0
#
# Stages: prune leftovers, sanitize secrets/paths, normalize LF/gitignore, check CI callers,
# validate clone-safety, optionally git init. Does not commit or push.
set -euo pipefail

MODE="dry-run"
GIT_INIT=0
IN_PLACE=0
GITHUB_OWNER=""
for arg in "$@"; do
  case "${arg}" in
    --dry-run) MODE="dry-run" ;;
    --apply) MODE="apply" ;;
    --git-init) GIT_INIT=1 ;;
    --in-place) IN_PLACE=1 ;;
    --github-owner=*) GITHUB_OWNER="${arg#--github-owner=}" ;;
    --help|-h)
      cat <<'EOF'
Usage: bash scripts/prepare_github_publish.sh [--dry-run|--apply] [--in-place] [--git-init] [--github-owner=OWNER]

Run from a generated workload root. Default is --dry-run.

  --dry-run         Print what would be removed or patched. No writes.
  --apply           Delete generator leftovers (including superseded nightly.yml
                    and dependabot.yml), normalize LF, check the CI callers,
                    tighten .gitignore, replace <org> clone URLs, and strip
                    known dangling doc links.
  --in-place        Required with --apply when a nested *_copy generation
                    workspace is still present. Prefer copying the repo first.
  --git-init        After --apply, git init and git add . (does not commit or push).
  --github-owner=X  Replace https://github.com/<org>/ and <OWNER> in README and
                    docs with the real GitHub user or organization.

Does not rename the local <N>_<Repo Base Name> folder. The GitHub repository name is
the same <N>_<Repo Base Name> string (for example 128_gpu-bench-amd-vllm-throughput-latency).
EOF
      exit 0
      ;;
    *)
      echo "[FAIL] Unknown option: ${arg}" >&2
      exit 1
      ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if [[ ! -f benchmark_specification.json || ! -f setup.sh || ! -f run_benchmark.sh ]]; then
  echo "[FAIL] Run this from a generated workload root (missing benchmark_specification.json, setup.sh, or run_benchmark.sh)." >&2
  exit 1
fi

fail=0
warn() { printf '[WARN] %s\n' "$1" >&2; }
info() { printf '[INFO] %s\n' "$1"; }
pass() { printf '[PASS] %s\n' "$1"; }
err() { printf '[FAIL] %s\n' "$1" >&2; fail=1; }

do_rm() {
  local path="$1"
  if [[ ! -e "${path}" ]]; then
    return 0
  fi
  if [[ "${MODE}" == "dry-run" ]]; then
    info "would remove ${path}"
  else
    rm -rf "${path}"
    info "removed ${path}"
  fi
}

# Generator leftovers that must not ship in a public workload clone.
ROOT_LEFTOVERS=(
  README_TEMPLATE.md
  PRD_TEMPLATE.md
  SPEC_TEMPLATE.md
  AGENTS.md
  GENERATION_REPORT.md
  CLAUDE.md
  benchmark_actual.csv
  benchmark_actual_excel.csv
)

DOC_LEFTOVERS=(
  docs/GENERATION_REPORT.md
  docs/AI_AGENT_INSTRUCTIONS.md
  docs/AI_AGENT_HANDOFF.md
  docs/SUBMISSION_CHECKLIST.md
  docs/generation-workflow.md
  docs/TEMPLATE_README.md
  docs/CHANGELOG.md
  docs/repository-template.md
  docs/SIBLING_WORKLOAD_NOTES.md
  docs/nvidia-sglang-install-contract.md
  docs/amd-developer-cloud-getting-started.md
  docs/IMPLEMENTATION_COMPONENTS.md
  docs/ARCHITECTURE.md
  docs/machine-checkable-contracts.md
  docs/repository-local-root-policy.md
  docs/reboot-resume-pattern.md
  docs/remote-execution-pattern.md
  docs/GITHUB_PUBLISH.md
  docs/GITHUB_PUBLISH.md.bak
  docs/GITHUB_WORKLOAD_PUBLISH.md
  docs/GITHUB_PUBLISH_GENERATOR_OPERATIONS.md
)

SCRIPT_LEFTOVERS=(
  scripts/create_generated_repo.py
  scripts/create_generated_batch.py
  scripts/create_one_workload.py
  scripts/init_generated_repo.py
  scripts/materialize_generated_harness.py
  scripts/extract_benchmark_definition.py
  scripts/generate_benchmark_config.py
  scripts/generate_workload_parameters.py
  scripts/prompt_workflow.py
  scripts/resolve_implementation_components.py
  scripts/apply_component_gaps.py
  scripts/validate_template_inputs.py
  scripts/generation_host_preflight.py
  scripts/remote_host_preflight.py
  scripts/remote_host_bootstrap.py
  scripts/verify_generation_workflow.py
  scripts/sync_matrix_profile_commands.py
  scripts/matrix_profile_values.py
  scripts/refresh_remote_vm.sh
  scripts/test_nested_template_copy.sh
  scripts/remove_template_copy.py
  scripts/smoke_check_generated_repo.sh
  scripts/self_check_generated_repo.sh
  scripts/dir.txt
  scripts/templates/dir.txt
  scripts/ci_contract.py
  scripts/emit_shared_workflows.py
)

# Superseded CI files. GPU runs moved to the gpu-smoke.yml caller; Dependabot
# lives in the shared-workflows repository; the CI contract is generation-only.
CI_LEFTOVERS=(
  .github/workflows/nightly.yml
  .github/dependabot.yml
  config/ci_contract.yaml
)

SCHEMA_LEFTOVERS=(
  schemas/generation_report.schema.json
  schemas/batch_generation_report.schema.json
  results/generation_manifest.json
  results/component_gates.json
  results/component_leftover_work.md
)

DIR_LEFTOVERS=(
  ai-agent-gpu-benchmark-repo-generator_copy
  scripts/remote
  docs/examples/generated-repo-github
  docs/examples/generated-repo-workflows
  .cache
  models
  .claude
)

info "Repository: ${ROOT}"
info "Mode: ${MODE}"
if [[ -n "${GITHUB_OWNER}" ]]; then
  info "GitHub owner: ${GITHUB_OWNER}"
fi

if [[ "${MODE}" == "apply" && "${IN_PLACE}" -eq 0 ]]; then
  if find . -maxdepth 1 -type d \( -name 'TEMPLATE_00_*_copy' -o -name 'ai-agent-gpu-benchmark-repo-generator_copy' \) -print -quit | grep -q .; then
    err "Nested generation *_copy is present. Copy this repo to a publish tree first, or pass --in-place if you intend to destroy the generation workspace."
    exit 1
  fi
fi

info "Removing generator leftovers..."
for rel in "${ROOT_LEFTOVERS[@]}" "${DOC_LEFTOVERS[@]}" "${SCRIPT_LEFTOVERS[@]}" "${SCHEMA_LEFTOVERS[@]}" "${CI_LEFTOVERS[@]}"; do
  do_rm "${rel}"
done
for rel in "${DIR_LEFTOVERS[@]}"; do
  do_rm "${rel}"
done
while IFS= read -r copy_dir; do
  [[ -n "${copy_dir}" ]] || continue
  do_rm "${copy_dir}"
done < <(find . -maxdepth 1 -type d \( -name 'TEMPLATE_00_*_copy' -o -name '*_copy' \) -print)

do_rm .venv
do_rm .venvs
if [[ -d results/raw ]]; then
  while IFS= read -r run_dir; do
    [[ -n "${run_dir}" ]] || continue
    do_rm "${run_dir}"
  done < <(find results/raw -mindepth 1 -maxdepth 1 -type d -print)
fi

# FAISS builder is only used by RAG workloads. Do not ship it in perf/lmbench/etc.
if ! grep -qiE 'faiss|rag-faiss|end-to-end rag' benchmark_specification.json setup.sh run_benchmark.sh 2>/dev/null; then
  do_rm scripts/build_faiss_rocm.sh
fi

info "Scanning for secrets and private host data..."
# Patterns live in variables so this file is excluded from the tree scan and
# so a literal grep of the script cannot match its own -e arguments.
_secret_begin="BEGIN"
_secret_openssh="${_secret_begin} OPENSSH PRIVATE KEY"
_secret_rsa="${_secret_begin} RSA PRIVATE KEY"
_secret_key_hint="gmb-amd-ssh"
_secret_win_home="/c/Users/"
_secret_mac_home="/Users/gary"
if grep -RIn --binary-files=without-match \
  -e "${_secret_openssh}" \
  -e "${_secret_rsa}" \
  -e "${_secret_key_hint}" \
  -e "${_secret_win_home}" \
  -e "${_secret_mac_home}" \
  --include='*.md' --include='*.sh' --include='*.py' --include='*.yml' \
  --include='*.yaml' --include='*.json' --include='*.txt' --include='*.toml' \
  --exclude-dir='.venv' --exclude-dir='.git' --exclude-dir='ai-agent-gpu-benchmark-repo-generator_copy' \
  --exclude='prepare_github_publish.sh' --exclude='prompt_workflow.py' --exclude='check_github_publish_ready.sh' \
  . >/tmp/prepare_github_publish_secrets.txt 2>/dev/null; then
  err "Possible private path or key material remains. Review /tmp/prepare_github_publish_secrets.txt"
  if [[ "${MODE}" == "dry-run" ]]; then
    head -n 20 /tmp/prepare_github_publish_secrets.txt || true
  fi
else
  pass "No obvious private-key or operator-home paths in publishable text"
fi

# Lab IPv4 literals are assembled so this script itself is not a hit.
_lab_a="165.245.141"
_lab_b="129.212.180"
_lab_c="205.196.17"
if grep -RIn --binary-files=without-match \
  -E "${_lab_a}\\.159|${_lab_b}\\.31|${_lab_c}\\.122" \
  --include='*.md' --include='*.sh' --include='*.py' --include='*.yml' \
  --include='*.yaml' --include='*.json' --include='*.txt' --include='*.toml' \
  --exclude-dir='.venv' --exclude-dir='.git' \
  --exclude='prepare_github_publish.sh' --exclude='check_github_publish_ready.sh' \
  . >/dev/null 2>&1; then
  warn "A lab IPv4 address is still present in text files. Remove it before push."
  fail=1
fi

info "Checking README for public-download completeness..."
if [[ ! -s README.md ]]; then
  err "README.md is missing or empty"
else
  readme_lines="$(wc -l < README.md | tr -d ' ')"
  if [[ "${readme_lines}" -lt 60 ]]; then
    err "README.md is a stub (${readme_lines} lines). Regenerate it from templates/README_TEMPLATE.md before publish."
  else
    pass "README.md has ${readme_lines} lines"
  fi
  for heading in '## Quick Start' '## Profiles and Parameters' '## Metrics' '## Output' '## Requirements' '## Troubleshooting'; do
    if grep -Fq "${heading}" README.md; then
      pass "README has ${heading}"
    else
      err "README.md is missing ${heading}"
    fi
  done
  if grep -Eq '\[\[GENERATE:|\{\{[^}]+\}\}|TODO|TBD: GENERATE' README.md; then
    err "README.md still contains generation markers"
  fi
fi

info "Normalizing CRLF to LF on text files..."
if [[ "${MODE}" == "apply" ]]; then
  find . -type f \
    \( -name '*.sh' -o -name '*.py' -o -name '*.md' -o -name '*.yml' -o -name '*.yaml' \
       -o -name '*.json' -o -name '*.txt' -o -name '*.csv' -o -name '*.toml' \) \
    ! -path './.venv/*' ! -path './.git/*' \
    -exec sed -i 's/\r$//' {} +
  pass "Converted CRLF to LF"
else
  if grep -RIl $'\r' --include='*.sh' --include='*.py' --include='*.md' --include='*.toml' . >/dev/null 2>&1; then
    warn "CRLF line endings are present; --apply will convert them to LF"
  else
    pass "No CRLF detected in a quick scan"
  fi
fi

info "Ensuring .gitignore publication exclusions..."
GITIGNORE_NEEDLES=(
  'results/'
  '.venv/'
  '*.zip'
  'runtime_ledger.csv'
  'benchmark_actual.csv'
  'benchmark_actual_excel.csv'
  'TEMPLATE_00_*_copy/'
  'ai-agent-gpu-benchmark-repo-generator_copy/'
  '.cache/'
  '*.safetensors'
)
if [[ "${MODE}" == "apply" ]]; then
  touch .gitignore
  for needle in "${GITIGNORE_NEEDLES[@]}"; do
    if ! grep -Fq "${needle}" .gitignore; then
      printf '%s\n' "${needle}" >> .gitignore
      info "appended ${needle} to .gitignore"
    fi
  done
  pass ".gitignore publication exclusions are present"
else
  for needle in "${GITIGNORE_NEEDLES[@]}"; do
    if grep -Fq "${needle}" .gitignore 2>/dev/null; then
      pass ".gitignore has ${needle}"
    else
      warn ".gitignore missing ${needle} (added on --apply)"
    fi
  done
fi

info "Checking GitHub Actions callers..."
# The CI workflows are thin callers of the shared-workflows repository,
# rendered by init_generated_repo.py from config/ci_contract.yaml. This script
# no longer rewrites them; it only removes superseded files (above) and checks.
for wf in ci gpu-smoke; do
  path=".github/workflows/${wf}.yml"
  if [[ ! -f "${path}" ]]; then
    err "${path} is missing; regenerate the workload with the current generator"
  elif grep -Eq "^[[:space:]]+uses:[[:space:]]+[A-Za-z0-9_.-]+/shared-workflows/\.github/workflows/${wf}\.yml@v[0-9]+[[:space:]]*$" "${path}"; then
    pass "${path} calls shared-workflows"
  else
    err "${path} is not a shared-workflows caller; regenerate the workload with the current generator"
  fi
done

info "Rewriting clone URLs and stripping known dangling links..."
if [[ "${MODE}" == "apply" ]]; then
  if [[ -f README.md ]]; then
    if grep -Fq 'docs/repository-template.md' README.md; then
      sed -i '/For full repository layout, see `docs\/repository-template\.md`\./d' README.md
      info "removed dead docs/repository-template.md pointer from README.md"
    fi
  fi
  if [[ -n "${GITHUB_OWNER}" ]]; then
    python3 - "${GITHUB_OWNER}" <<'PY'
import sys
from pathlib import Path

owner = sys.argv[1]
replacements = (
    "https://github.com/<org>/",
    "https://github.com/<OWNER>/",
)
for rel in ("README.md", "docs/GITHUB_PUBLISH_WORKLOAD_REPO.md"):
    path = Path(rel)
    if not path.is_file():
        continue
    text = path.read_text(encoding="utf-8")
    updated = text
    for old in replacements:
        updated = updated.replace(old, f"https://github.com/{owner}/")
    if updated != text:
        path.write_text(updated, encoding="utf-8", newline="\n")
        print(f"[INFO] replaced GitHub owner placeholders in {rel}")
PY
  else
    if grep -RIn --binary-files=without-match -e 'github.com/<org>/' -e 'github.com/<OWNER>/' \
      --include='*.md' --exclude-dir='.git' . >/dev/null 2>&1; then
      warn "Clone URLs still contain <org> or <OWNER>. Re-run with --github-owner=YOUR_GITHUB_USER"
    fi
  fi
fi

if [[ "${MODE}" == "apply" ]]; then
  info "Checking for dangling references to removed generator files..."
  REMOVED_TARGETS=(
    "${ROOT_LEFTOVERS[@]}" "${DOC_LEFTOVERS[@]}" "${SCRIPT_LEFTOVERS[@]}" "${SCHEMA_LEFTOVERS[@]}"
    ai-agent-gpu-benchmark-repo-generator_copy .claude
  )
  dangling_found=0
  for target in "${REMOVED_TARGETS[@]}"; do
    base="$(basename "${target}")"
    hits="$(grep -RIl --binary-files=without-match -F -e "${base}" \
      --include='*.md' --include='*.sh' --include='*.py' --include='*.yml' --include='*.yaml' \
      --exclude-dir='.venv' --exclude-dir='.git' \
      --exclude='prepare_github_publish.sh' --exclude='check_github_publish_ready.sh' --exclude='ci.yml' \
      . 2>/dev/null || true)"
    if [[ -n "${hits}" ]]; then
      warn "'${target}' was removed but is still mentioned by name in: $(echo "${hits}" | tr '\n' ' ')"
      dangling_found=1
    fi
  done
  if [[ "${dangling_found}" -eq 1 ]]; then
    warn "Update the references above (they will point at files that no longer exist in the published clone)."
  else
    pass "No surviving references to removed generator files"
  fi
else
  info "Dangling-reference check runs on --apply (after removal), not on --dry-run."
fi

if [[ ! -s LICENSE || ! -s legal/NOTICE ]]; then
  err "LICENSE or legal/NOTICE is missing"
fi

if [[ "${GIT_INIT}" -eq 1 ]]; then
  if [[ "${MODE}" != "apply" ]]; then
    err "--git-init requires --apply"
  else
    if [[ ! -d .git ]]; then
      git init
      git branch -M main
      info "initialized git repository on branch main"
    fi
    git add .
    info "staged files. Review with: git status"
    info "This script does not commit or push."
  fi
fi

if [[ "${fail}" -ne 0 ]]; then
  echo "[FAIL] Publication prep found blocking issues. Fix README/secrets, then rerun." >&2
  exit 1
fi

if [[ "${MODE}" == "apply" && -x scripts/check_github_publish_ready.sh ]]; then
  info "Running post-cleanup publication gate..."
  # check_github_publish_ready.sh --published prints the full "GitHub
  # Publication Readiness" summary (local folder, repo name, suggested
  # description, ready-to-push line) itself on success, so nothing further
  # is printed here — avoids printing that summary twice.
  if ! bash scripts/check_github_publish_ready.sh --published; then
    err "Post-cleanup publication gate failed"
    echo "[FAIL] Publication prep found blocking issues. Fix README/secrets, then rerun." >&2
    exit 1
  fi
fi

if [[ "${MODE}" == "dry-run" ]]; then
  echo "[PASS] Dry run complete. Re-run with --apply to modify this repository."
fi
