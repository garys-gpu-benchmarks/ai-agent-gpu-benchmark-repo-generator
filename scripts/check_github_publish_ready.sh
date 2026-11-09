#!/usr/bin/env bash
# File: scripts/check_github_publish_ready.sh
# Version: 1.2.0
# Maintainer: AI Agent GPU Benchmark Repo Generator
# Date: 2026-10-08
# Description: Validate that a generated workload is ready for independent GitHub publication.
# Execution: bash scripts/check_github_publish_ready.sh [--generation|--published]
# Requirements: Bash, grep, find, python3
# License: Apache-2.0
#
# Default mode auto-detects: if generator leftovers remain, run generation-time
# structural checks. After prepare_github_publish.sh --apply, leftovers are gone
# and the stricter published-clone gate runs.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="auto"
for arg in "$@"; do
  case "${arg}" in
    --generation) MODE="generation" ;;
    --published) MODE="published" ;;
    --help|-h)
      cat <<'EOF'
Usage: bash scripts/check_github_publish_ready.sh [--generation|--published]

  --generation  Structural checks while generator leftovers may still exist.
  --published   Post-cleanup gate: leftovers gone, README links resolve,
                host-safe syntax checks pass.
  (default)     Auto-detect from leftover presence.
EOF
      exit 0
      ;;
    *)
      echo "[FAIL] Unknown option: ${arg}" >&2
      exit 1
      ;;
  esac
done

fail=0
pass() { printf '[PASS] %s\n' "$1"; }
warn() { printf '[WARN] %s\n' "$1" >&2; }
err() { printf '[FAIL] %s\n' "$1" >&2; fail=1; }

PUBLISH_LEFTOVERS=(
  README_TEMPLATE.md
  PRD_TEMPLATE.md
  SPEC_TEMPLATE.md
  AGENTS.md
  GENERATION_REPORT.md
  docs/GENERATION_REPORT.md
  CLAUDE.md
  docs/GITHUB_PUBLISH.md
  docs/GITHUB_WORKLOAD_PUBLISH.md
  docs/GITHUB_PUBLISH_GENERATOR_OPERATIONS.md
  docs/repository-template.md
  docs/generation-workflow.md
  docs/AI_AGENT_INSTRUCTIONS.md
  scripts/self_check_generated_repo.sh
  scripts/create_generated_repo.py
  scripts/init_generated_repo.py
  scripts/prompt_workflow.py
  schemas/generation_report.schema.json
  schemas/batch_generation_report.schema.json
  results/generation_manifest.json
)

# Workbook-vs-implementation bookkeeping. Expected during generation; must
# not ship. Do not use these to auto-detect mode or a published clone that
# only forgot these files would be classified as still-generating.
PUBLISH_ONLY_LEFTOVERS=(
  benchmark_actual.csv
  benchmark_actual_excel.csv
)

leftover_present=0
for leftover in "${PUBLISH_LEFTOVERS[@]}" .claude; do
  if [[ -e "${leftover}" ]]; then
    leftover_present=1
    break
  fi
done

if [[ "${MODE}" == "auto" ]]; then
  if [[ "${leftover_present}" -eq 1 ]]; then
    MODE="generation"
  else
    MODE="published"
  fi
fi
printf '[INFO] Publication check mode: %s\n' "${MODE}"

required=(
  README.md
  LICENSE
  legal/NOTICE
  .gitignore
  .gitattributes
  benchmark_specification.json
  docs/PRD.md
  setup.sh
  run_benchmark.sh
  show_metrics.sh
  list_runs.sh
  .github/CODE_OF_CONDUCT.md
  .github/CONTRIBUTING.md
  .github/SECURITY.md
  .github/PULL_REQUEST_TEMPLATE.md
  .github/copilot-instructions.md
  .github/ISSUE_TEMPLATE/bug_report.md
  .github/ISSUE_TEMPLATE/feature_request.md
  .github/ISSUE_TEMPLATE/config.yml
  .github/workflows/ci.yml
  .github/workflows/gpu-smoke.yml
  docs/GITHUB_PUBLISH_WORKLOAD_REPO.md
  scripts/prepare_github_publish.sh
)

for path in "${required[@]}"; do
  if [[ -s "$path" ]]; then
    pass "Required publish file exists: $path"
  else
    err "Missing or empty required publish file: $path"
  fi
done

# CI callers: two thin files that call the shared-workflows repository.
# The steps live there (templates/shared-workflows in the generator).
ci_callers_ok=1
for wf in .github/workflows/*.yml .github/workflows/*.yaml; do
  [[ -e "${wf}" ]] || continue
  case "${wf##*/}" in
    ci.yml|gpu-smoke.yml) ;;
    *) err "Unexpected workflow ${wf}; workloads carry only ci.yml and gpu-smoke.yml"; ci_callers_ok=0 ;;
  esac
done
for wf in ci gpu-smoke; do
  path=".github/workflows/${wf}.yml"
  [[ -f "${path}" ]] || continue
  if ! grep -Eq "^[[:space:]]+uses:[[:space:]]+[A-Za-z0-9_.-]+/shared-workflows/\.github/workflows/${wf}\.yml@v[0-9]+[[:space:]]*$" "${path}"; then
    err "${path} must call <owner>/shared-workflows/.github/workflows/${wf}.yml@v<N>"
    ci_callers_ok=0
  fi
  if ! grep -Eq '^permissions:' "${path}"; then
    err "${path} has no top-level permissions block"
    ci_callers_ok=0
  fi
  if grep -Eq '^[[:space:]]+run:' "${path}"; then
    err "${path} has its own run: steps; CI logic belongs in shared-workflows"
    ci_callers_ok=0
  fi
done
if [[ -f .github/workflows/gpu-smoke.yml ]] && grep -Eq '^[[:space:]]+pull_request(_target)?:' .github/workflows/gpu-smoke.yml; then
  err ".github/workflows/gpu-smoke.yml must never trigger on pull requests (fork code would reach the GPU runner)"
  ci_callers_ok=0
fi
if [[ "${ci_callers_ok}" -eq 1 ]]; then
  pass "CI callers point at shared-workflows; GPU workflow is manual-only"
fi

if [[ -f README.md ]]; then
  if grep -Eq '\[\[GENERATE:|\{\{[^}]+\}\}|TODO|TBD: GENERATE' README.md; then
    err "README.md contains unresolved generation/template markers"
  else
    pass "README.md contains no known generation/template markers"
  fi
  readme_lines="$(wc -l < README.md | tr -d ' ')"
  if [[ "${readme_lines}" -lt 60 ]]; then
    err "README.md is a stub (${readme_lines} lines); generate all template sections before publish"
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
fi

if ! python3 - <<'PY'
import json
import re
import sys
from pathlib import Path

def fail(msg):
    print(f"[FAIL] {msg}", file=sys.stderr)
    sys.exit(1)

fields = {
    item.get("field_name", ""): str(item.get("value", ""))
    for item in json.loads(Path("benchmark_specification.json").read_text(encoding="utf-8"))
}
workload = fields.get("Workload Number", "").strip()
yaml_kv = ""
cfg = Path("config/benchmark_config.yaml")
if cfg.is_file():
    match = re.search(r"(?m)^  kernel_version:\s*(\S+)", cfg.read_text(encoding="utf-8"))
    if match:
        yaml_kv = match.group(1).strip().strip("'\"")
if yaml_kv and re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", yaml_kv):
    for name in ("README.md", "SPEC.md"):
        path = Path(name)
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for found in re.findall(r"--kernel-version(?:\s+|\s*\|\s*)([0-9][0-9.]+)", text):
            if found != yaml_kv:
                fail(f"{name} uses --kernel-version {found} but config/benchmark_config.yaml is {yaml_kv}")
        for found in re.findall(r"\|\s*Kernel\s*\|\s*kernel\s+([0-9][0-9.]+)", text):
            if found != yaml_kv:
                fail(f"{name} Software Requirements kernel {found} but yaml kernel_version is {yaml_kv}")
        for found in re.findall(r"\|\s*kernel_version\s*\|[^|\n]*\|\s*([0-9][0-9.]+)\s+\(", text):
            if found != yaml_kv:
                fail(f"{name} Parameters kernel_version {found} but yaml kernel_version is {yaml_kv}")
        # README Profiles and Parameters row: | `kernel_version` | `--kernel-version` | smoke | baseline | extended |
        for row in re.findall(r"\|\s*`kernel_version`\s*\|\s*`--kernel-version`\s*\|([^\n]*)", text):
            for value in re.findall(r"[0-9]+(?:\.[0-9]+)+", row):
                if value != yaml_kv:
                    fail(f"{name} Profiles and Parameters kernel_version {value} but yaml kernel_version is {yaml_kv}")
if Path("PRD.md").is_file():
    fail("PRD.md belongs at docs/PRD.md, not the repository root")
prd = Path("docs/PRD.md")
if prd.is_file() and workload:
    match = re.search(r"(?m)^## Workload Number\s*\n+(\S+)", prd.read_text(encoding="utf-8"))
    if not match or match.group(1).strip() != workload:
        shown = match.group(1).strip() if match else "(missing)"
        fail(f"docs/PRD.md Workload Number is {shown}, expected {workload}")
for name in ("README.md", "SPEC.md", "docs/PRD.md", "benchmark_specification.json"):
    path = Path(name)
    if path.is_file() and "TEMPLATE_00_" in path.read_text(encoding="utf-8"):
        fail(f"{name} still contains a TEMPLATE_00_* authoring note")
print("[PASS] README/SPEC kernel_version, PRD workload number, and public docs match the spec")
PY
then
  err "Public docs do not match benchmark_specification.json / yaml defaults"
else
  pass "Public docs match yaml kernel_version and Workload Number"
fi

for leftover in README_TEMPLATE.md PRD_TEMPLATE.md SPEC_TEMPLATE.md AGENTS.md; do
  if [[ -e "${leftover}" ]]; then
    if [[ "${MODE}" == "published" ]]; then
      err "Generator leftover must not be published: ${leftover} (run scripts/prepare_github_publish.sh --apply)"
    else
      warn "Generator leftover present (expected until --apply): ${leftover}"
    fi
  else
    pass "No leftover ${leftover}"
  fi
done

if [[ "${MODE}" == "published" ]]; then
  for leftover in "${PUBLISH_LEFTOVERS[@]}" "${PUBLISH_ONLY_LEFTOVERS[@]}" .claude ai-agent-gpu-benchmark-repo-generator_copy; do
    if [[ -e "${leftover}" ]]; then
      err "Published clone still contains generator leftover: ${leftover}"
    fi
  done
  if grep -Fq 'docs/repository-template.md' README.md 2>/dev/null; then
    err "README.md still points at docs/repository-template.md (deleted at publish time)"
  else
    pass "README.md does not point at the deleted repository-template doc"
  fi
  if grep -Eq 'github.com/<org>/|github.com/<OWNER>/' README.md docs/GITHUB_PUBLISH_WORKLOAD_REPO.md 2>/dev/null; then
    warn "Clone URL still contains <org> or <OWNER>. Re-run prepare with --github-owner=YOUR_GITHUB_USER"
  else
    pass "README/docs clone URLs do not contain <org>/<OWNER> placeholders"
  fi
fi

for pattern in 'results/' '.venv/' '*.zip' 'runtime_ledger.csv' 'benchmark_actual.csv' 'TEMPLATE_00_*_copy/'; do
  if grep -Fq "$pattern" .gitignore; then
    pass ".gitignore protects $pattern"
  else
    err ".gitignore is missing required publication exclusion: $pattern"
  fi
done

for forbidden in \
  runtime_ledger.csv \
  credentials.json \
  secrets.yaml \
  .env.local; do
  if [[ -e "$forbidden" ]]; then
    err "Local-only/sensitive artifact exists at repository root: $forbidden"
  fi
done

if find . -maxdepth 2 -type f \( -name '*.pem' -o -name 'id_rsa' -o -name 'id_ed25519' -o -name '*.zip' \) -print -quit | grep -q .; then
  err "Potential private key or archive found in publishable repository tree"
else
  pass "No obvious private-key/archive artifacts found near repository root"
fi

if [[ -d .git ]]; then
  ignored_copy="$(find . -maxdepth 1 -type d -name 'TEMPLATE_00_*_copy' -print -quit || true)"
  if [[ -n "$ignored_copy" ]]; then
    if git check-ignore -q "$ignored_copy"; then
      pass "Nested generation template copy is ignored by Git"
    else
      err "Nested generation template copy is not ignored by Git: $ignored_copy"
    fi
  fi
fi

if [[ "${MODE}" == "published" ]]; then
  if bash -n setup.sh && bash -n run_benchmark.sh && bash -n show_metrics.sh && bash -n list_runs.sh; then
    pass "setup.sh, run_benchmark.sh, show_metrics.sh and list_runs.sh parse with bash -n"
  else
    err "setup.sh, run_benchmark.sh, show_metrics.sh or list_runs.sh failed bash -n"
  fi
  if python3 -m compileall -q scripts >/dev/null 2>&1; then
    pass "Python files under scripts/ compile"
  else
    err "python3 -m compileall scripts failed"
  fi
  if python3 -c "import json; json.load(open('benchmark_specification.json', encoding='utf-8'))"; then
    pass "benchmark_specification.json parses"
  else
    err "benchmark_specification.json is not valid JSON"
  fi
  if [[ -f config/benchmark_config.yaml ]]; then
    yaml_rc=0
    python3 - <<'PY' >/dev/null 2>&1 || yaml_rc=$?
try:
    import yaml
except ImportError:
    raise SystemExit(2)
yaml.safe_load(open("config/benchmark_config.yaml", encoding="utf-8"))
PY
    if [[ "${yaml_rc}" -eq 0 ]]; then
      pass "config/benchmark_config.yaml parses"
    elif [[ "${yaml_rc}" -eq 2 ]]; then
      warn "PyYAML is not installed; skipped YAML parse of config/benchmark_config.yaml"
    else
      err "config/benchmark_config.yaml failed to parse"
    fi
  fi
  if python3 - <<'PY'
from pathlib import Path
import re
import sys

root = Path(".")
text = Path("README.md").read_text(encoding="utf-8")
fail = 0
seen = set()
for raw in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
    target = raw.strip()
    if target.startswith(("http://", "https://", "mailto:", "#")):
        continue
    target = target.split("#", 1)[0].split("?", 1)[0]
    if not target or target in seen:
        continue
    seen.add(target)
    path = (root / target).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        print(f"[FAIL] README link escapes repository: {raw}")
        fail = 1
        continue
    if not path.exists():
        print(f"[FAIL] README relative link is missing: {raw}")
        fail = 1
sys.exit(fail)
PY
  then
    pass "README relative Markdown links resolve"
  else
    err "README.md has broken relative Markdown links"
  fi
  if bash run_benchmark.sh --help >/dev/null 2>&1; then
    pass "run_benchmark.sh --help succeeds without a GPU"
  else
    warn "run_benchmark.sh --help did not succeed in this environment"
  fi
fi

if [[ "$fail" -ne 0 ]]; then
  printf '[FAIL] GitHub publication readiness check failed.\n' >&2
  exit 1
fi
if [[ "${MODE}" == "published" ]]; then
  printf '[PASS] Published workload tree is ready for GitHub.\n'
  printf '[PASS] Post-cleanup publication gate passed\n'

  REPO_NAME="$(python3 - <<'PY'
import json
from pathlib import Path
data = json.loads(Path("benchmark_specification.json").read_text(encoding="utf-8"))
fields = {str(item.get("field_name", "")): str(item.get("value", "")) for item in data if isinstance(item, dict)}
print((fields.get("Repo Base Name") or fields.get("Repo Name", "")).strip())
PY
)"
  WORKLOAD_NUMBER="$(python3 - <<'PY'
import json
from pathlib import Path
data = json.loads(Path("benchmark_specification.json").read_text(encoding="utf-8"))
fields = {str(item.get("field_name", "")): str(item.get("value", "")) for item in data if isinstance(item, dict)}
print(fields.get("Workload Number", "").strip())
PY
)"
  if [[ -n "${WORKLOAD_NUMBER}" && -n "${REPO_NAME}" && "${REPO_NAME}" != "${WORKLOAD_NUMBER}-"* && "${REPO_NAME}" != "${WORKLOAD_NUMBER}_"* ]]; then
    GITHUB_SLUG="${WORKLOAD_NUMBER}-${REPO_NAME}"
  else
    GITHUB_SLUG="${REPO_NAME:-${ROOT##*/}}"
  fi

  echo "============================================================"
  echo "GitHub Publication Readiness"
  echo "============================================================"
  echo "Local folder               ${ROOT##*/}"
  echo "GitHub repository name     ${GITHUB_SLUG:-"(missing Workload Number / Repo Base Name)"}"
  echo "Suggested description      Workload ${WORKLOAD_NUMBER}: ${REPO_NAME}"
  echo "Ready for git commit/push  YES"
  echo "============================================================"
  echo "[PASS] Repository is cleaned for GitHub publication."
  echo "[INFO] Next: review git status, commit, and push ${GITHUB_SLUG}"
  echo "[INFO]       (same as the numbered local folder; do not drop the workload prefix)."
else
  printf '[PASS] Generated workload repository is structurally ready for GitHub publication.\n'
fi
