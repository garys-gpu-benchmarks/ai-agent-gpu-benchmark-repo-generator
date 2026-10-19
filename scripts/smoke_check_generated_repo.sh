#!/usr/bin/env bash
# File: scripts/smoke_check_generated_repo.sh
# Version: 1.1.0
# Maintainer: AI Agent GPU Benchmark Repo Generator
# Date: 2026-07-07
# Description: Template-mode smoke checks for generated repository completeness and phase markers.
# Execution: bash scripts/smoke_check_generated_repo.sh [repo_root]
# Options: repo_root (optional) — defaults to <workload>-<Repo Name>
# Requirements: bash, python3
# Environment: Run from template root after generation.
# Dependencies: python3, test, rg
# Variables: None
# Repository: gpu-bench/sys-bench template
# License: Apache-2.0

set -euo pipefail

extract_identity() {
    python3 - <<'PY'
import json
from pathlib import Path

path = Path("benchmark_specification.json")
if not path.exists():
    raise SystemExit("benchmark_specification.json not found in template root")
data = json.loads(path.read_text(encoding="utf-8"))
workload = None
repo_name = None
for item in data:
    if item.get("field_name") == "Workload Number":
        workload = str(item.get("value", "")).strip()
    elif item.get("field_name") == "Repo Name":
        repo_name = str(item.get("value", "")).strip()
if not workload or not repo_name:
    raise SystemExit("Workload Number or Repo Name missing in benchmark_specification.json")
print(f"{workload}|{repo_name}")
PY
}

identity="$(extract_identity)"
WORKLOAD_NUMBER="${identity%%|*}"
REPO_NAME="${identity#*|}"
TARGET_REPO="${1:-${WORKLOAD_NUMBER}-${REPO_NAME}}"
# shellcheck disable=SC2034  # kept for log lines and future use
TARGET_REPO_NAME="$(basename "${TARGET_REPO}")"

if [[ ! -d "${TARGET_REPO}" ]]; then
    echo "[FAIL] Generated repository directory missing: ${TARGET_REPO}" >&2
    exit 1
fi

echo "[INFO] Checking generated repository root: ${TARGET_REPO}"

python3 - "${TARGET_REPO}" <<'PY_COMPONENT_CHECK'
import pathlib, sys
repo = pathlib.Path(sys.argv[1]).resolve()
template = pathlib.Path.cwd().resolve()
sys.path.insert(0, str(template / "scripts"))
from resolve_implementation_components import resolve_components, validate_overlay_conflicts

resolved = resolve_components(repo / "benchmark_specification.json", template / "implementation_components")
validate_overlay_conflicts(resolved)
for item in resolved:
    component_id = str(item["component_id"])
    root = pathlib.Path(item["component_root"])
    manifest = item["component"]
    for rel in manifest["overlay"]:
        src, dst = root / "files" / str(rel), repo / str(rel)
        if not src.is_file() or not dst.is_file() or src.read_bytes() != dst.read_bytes():
            raise SystemExit(f"[FAIL] Implementation component mismatch: {component_id}:{rel}")
if resolved:
    print("[PASS] Automatically discovered implementation component files match generated files: " + ", ".join(str(x["component_id"]) for x in resolved))
PY_COMPONENT_CHECK

required_paths=(
  "PRD.md"
  "SPEC.md"
  "README.md"
  "setup.sh"
  "run_benchmark.sh"
  "requirements.txt"
  "config/benchmark_config.yaml"
  "scripts/build.sh"
  "scripts/parse_results.py"
  "scripts/validate_results.py"
  "scripts/self_check_generated_repo.sh"
  "results/generation_manifest.json"
  "results/raw/.gitkeep"
  "results/parsed/.gitkeep"
  "tests/fixtures/.gitkeep"
  ".gitattributes"
  ".claude/CLAUDE.md"
)

for rel in "${required_paths[@]}"; do
    if [[ ! -e "${TARGET_REPO}/${rel}" ]]; then
        echo "[FAIL] Missing required path: ${TARGET_REPO}/${rel}" >&2
        exit 1
    fi
done

read -r template_copy_name template_copy_removed_at < <(python3 - "${TARGET_REPO}/results/generation_manifest.json" <<'PY'
import json
import sys

manifest = json.loads(open(sys.argv[1], encoding="utf-8").read())
print(manifest.get("template_copy_path") or "-", manifest.get("template_copy_removed_at") or "-")
PY
) || true
if [[ -z "${template_copy_name:-}" || -z "${template_copy_removed_at:-}" ]]; then
    echo "[FAIL] Could not read template copy fields from ${TARGET_REPO}/results/generation_manifest.json." >&2
    exit 1
fi
if [[ -e "${TARGET_REPO}/CLAUDE.md" ]]; then
    echo "[FAIL] CLAUDE.md must live at .claude/CLAUDE.md, not the repository root." >&2
    exit 1
fi
if [[ "${template_copy_name}" != "-" && -d "${TARGET_REPO}/${template_copy_name}" ]]; then
    for rel in "AGENTS.md" ".claude/CLAUDE.md" "BenchmarkSpecDefinitions.xlsx" \
      "docs/generation-workflow.md" "scripts/create_generated_repo.py"; do
        if [[ ! -e "${TARGET_REPO}/${template_copy_name}/${rel}" ]]; then
            echo "[FAIL] Active template copy is incomplete: ${rel}" >&2
            exit 1
        fi
    done
    echo "[PASS] Complete active template copy is present: ${TARGET_REPO}/${template_copy_name}"
elif [[ "${template_copy_removed_at}" != "-" ]]; then
    echo "[PASS] Nested template copy was removed after generation at ${template_copy_removed_at}"
else
    echo "[FAIL] Complete active template copy is missing from ${TARGET_REPO}, and the manifest does not record template_copy_removed_at." >&2
    exit 1
fi

execution_domain="$(python3 - "${TARGET_REPO}/benchmark_specification.json" <<'PY'
import json
import sys

data = json.loads(open(sys.argv[1], encoding="utf-8").read())
for item in data:
    if item.get("field_name") == "Execution Domain":
        print(item.get("value", ""))
        break
PY
)"

if [[ "${execution_domain}" == *"ROCm"* ]]; then
    os_version="$(python3 - "${TARGET_REPO}/benchmark_specification.json" <<'PY'
import json
import sys

data = json.loads(open(sys.argv[1], encoding="utf-8").read())
for item in data:
    if item.get("field_name") == "OS Version":
        print(item.get("value", ""))
        break
PY
)"
    pin_patterns=("ROCM_VERSION=.*10.1.0" "UBUNTU_CODENAME=.*noble")
    if [[ "${os_version}" == *"26.04"* ]]; then
        pin_patterns=("ROCM_VERSION=.*10.1.0" "UBUNTU_CODENAME=.*resolute")
    fi
    for pattern in "install_resume_service" "systemctl enable" "resume-from-service" "rocm_runtime_stage" "install_status_log_phase" "install_status_log_step" "flock" "cleanup_resume_service" "${pin_patterns[@]}" "GFX_TARGET=.*gfx942"; do
        if ! rg -n "${pattern}" "${TARGET_REPO}/setup.sh" >/dev/null; then
            echo "[FAIL] ROCm setup.sh is missing reboot-resume contract element: ${pattern}" >&2
            exit 1
        fi
    done
    for pattern in "TimeoutStartSec=0" "TimeoutStopSec=0" "KillMode=process" "systemctl show" "systemctl is-enabled"; do
        if ! rg -n "${pattern}" "${TARGET_REPO}/setup.sh" >/dev/null; then
            echo "[FAIL] ROCm setup.sh is missing systemd timeout safeguard: ${pattern}" >&2
            exit 1
        fi
    done
fi

python3 - "${TARGET_REPO}" <<'PY_CONTRACTS'
import json
import pathlib
import re
import sys

repo = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(pathlib.Path.cwd() / "scripts"))
from resolve_implementation_components import merged_contracts, resolve_components

components_root = None
manifest = repo / "results" / "generation_manifest.json"
if manifest.is_file():
    copy_name = json.loads(manifest.read_text(encoding="utf-8")).get("template_copy_path") or ""
    if copy_name and (repo / copy_name / "implementation_components").is_dir():
        components_root = repo / copy_name / "implementation_components"
if components_root is None:
    components_root = pathlib.Path("implementation_components")
resolved = resolve_components(repo / "benchmark_specification.json", components_root)
contracts = merged_contracts(resolved)
ids = [str(item["component_id"]) for item in resolved]
print("[INFO] Resolved components: " + (", ".join(ids) if ids else "(none)"))

def has(path: pathlib.Path, pattern: str) -> bool:
    return path.is_file() and re.search(pattern, path.read_text(encoding="utf-8"), re.M) is not None

build = repo / "scripts" / "build.sh"
if contracts.get("compile_rocblas_bench"):
    if not has(build, r"ROCBLAS_SOURCE_DIR|rocm_compile_rocblas_bench"):
        raise SystemExit("[FAIL] compile_rocblas_bench contract requires the protected compiler in scripts/build.sh.")
    if not has(build, r"REPO_ROOT=|ROCM_SOURCE_ROOT=|ROCBLAS_SOURCE_DIR="):
        raise SystemExit("[FAIL] compile_rocblas_bench contract requires repository-local source paths in scripts/build.sh.")
    if not has(build, r"LD_LIBRARY_PATH=.*LD_LIBRARY_PATH"):
        raise SystemExit("[FAIL] compile_rocblas_bench contract requires LD_LIBRARY_PATH initialization in scripts/build.sh.")
    if "third_party/rocBLAS" not in build.read_text(encoding="utf-8") and "ROCBLAS_SOURCE_DIR" not in build.read_text(encoding="utf-8"):
        raise SystemExit("[FAIL] rocblas-bench path must be repository-local staging, not /opt/rocm/bin.")
if contracts.get("gemm_per_point"):
    runner = repo / "run_benchmark.sh"
    parser = repo / "scripts" / "parse_results.py"
    for pattern in (r"set \+e", r"command_status"):
        if not has(runner, pattern):
            raise SystemExit(f"[FAIL] gemm_per_point contract missing in run_benchmark.sh: {pattern}")
    if not has(parser, r"transa|rocblas-gflops|\\x1b"):
        raise SystemExit("[FAIL] gemm_per_point contract missing versioned-header handling in parse_results.py.")
elif any("rocblas" in cid for cid in ids) and not contracts.get("gemm_per_point"):
    print("[PASS] rocBLAS is install/verify only; GEMM per-point runner tokens are not required.")
PY_CONTRACTS

python3 scripts/validate_template_inputs.py \
  --generation-manifest "${TARGET_REPO}/results/generation_manifest.json" \
  --generation-schema schemas/generation_report.schema.json

if rg -n "\{\{.+\}\}|\[\[GENERATE:" "${TARGET_REPO}/PRD.md" "${TARGET_REPO}/SPEC.md" "${TARGET_REPO}/README.md" > /dev/null; then
    echo "[FAIL] Unresolved template tokens found in generated docs." >&2
    exit 1
fi

# Same shell lint the shared CI runs on push: warnings and errors fail.
if command -v shellcheck >/dev/null 2>&1; then
    if ! (
        cd "${TARGET_REPO}" || exit 1
        find scripts -name '*.sh' -type f -not -path 'scripts/templates/*' -print0 \
          | xargs -0 -r shellcheck --severity=warning
    ); then
        echo "[FAIL] shellcheck --severity=warning failed; the shared CI would fail on push." >&2
        exit 1
    fi
    echo "[PASS] shellcheck --severity=warning"
else
    echo "[WARN] shellcheck not installed; skipped the shell lint the shared CI runs on push." >&2
fi

(
    cd "${TARGET_REPO}"
    bash scripts/self_check_generated_repo.sh
)

echo "[PASS] Generated repository smoke checks succeeded for ${TARGET_REPO}"
