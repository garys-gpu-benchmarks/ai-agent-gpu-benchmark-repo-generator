#!/usr/bin/env bash
# File: scripts/self_check_generated_repo.sh
# Version: 1.7.0
# Maintainer: AI Agent GPU Benchmark Repo Generator
# Date: 2026-10-08
# Description: Standalone generated-repo validation checks run from generated repo root.
# Execution: bash scripts/self_check_generated_repo.sh
# Options: None
# Requirements: bash, python3, rg
# Environment: Run from generated repository root.
# Dependencies: python3, rg, test
# Variables: REPO_ROOT
# Repository: gpu-bench/sys-bench template
# License: Apache-2.0

set -euo pipefail

if ! command -v rg >/dev/null 2>&1; then
    echo "[FAIL] ripgrep is not installed" >&2
    exit 1
fi

if [[ ! -f "benchmark_specification.json" ]]; then
    echo "[FAIL] Run from generated repository root (missing benchmark_specification.json)." >&2
    exit 1
fi

required_paths=(
  "PRD.md"
  "SPEC.md"
  "README.md"
  "setup.sh"
  "run_benchmark.sh"
  "requirements.txt"
  "config/hw_sw_info_commands.xlsx"
  "config/benchmark_config.yaml"
  "scripts/build.sh"
  "scripts/parse_results.py"
  "scripts/validate_results.py"
  "scripts/generate_collect_hw_sw_info.sh"
  "scripts/collect_hw_sw_info.sh"
  "scripts/update_runtime_ledger.py"
  "scripts/print_benchmark_definition.py"
  "scripts/ensure_setup.sh"
  "scripts/lib/common.sh"
  "scripts/lib/hipcc_host_gcc.sh"
  "scripts/lib/rocm_install.sh"
  "scripts/lib/noninteractive_root.sh"
  "scripts/lib/amdgpu_reload.sh"
  "scripts/lib/rocm_install_24_04.sh"
  "scripts/lib/rocm_install_26_04.sh"
  "scripts/lib/keep_running_kernel.sh"
  "results/generation_manifest.json"
  "results/raw/.gitkeep"
  "results/parsed/.gitkeep"
  "tests/fixtures/.gitkeep"
  ".gitattributes"
  ".gitignore"
  "LICENSE"
  "legal/NOTICE"
  ".github/CONTRIBUTING.md"
  ".github/SECURITY.md"
  ".github/PULL_REQUEST_TEMPLATE.md"
  ".github/ISSUE_TEMPLATE/bug_report.md"
  ".github/ISSUE_TEMPLATE/feature_request.md"
  ".github/workflows/ci.yml"
  ".github/workflows/gpu-smoke.yml"
  "docs/GITHUB_PUBLISH_WORKLOAD_REPO.md"
  "scripts/check_github_publish_ready.sh"
  "scripts/prepare_github_publish.sh"
  ".claude/CLAUDE.md"
)

for rel in "${required_paths[@]}"; do
    if [[ ! -e "${rel}" ]]; then
        echo "[FAIL] Missing required generated-repo path: ${rel}" >&2
        exit 1
    fi
done

# Ubuntu 26.04 can install a newer kernel without leaving dpkg half-configured.
# The extra /lib/modules directory is then the only symptom, and the next reboot
# boots that kernel. Skip the check when /lib/modules is absent.
if [[ -d /lib/modules ]]; then
    # shellcheck disable=SC1091
    source scripts/lib/keep_running_kernel.sh
    refuse_foreign_installed_kernel
fi

for stale in ".github/workflows/nightly.yml" ".github/dependabot.yml"; do
    if [[ -e "${stale}" ]]; then
        echo "[FAIL] ${stale} is superseded (GPU runs: gpu-smoke.yml; Dependabot lives in shared-workflows)." >&2
        exit 1
    fi
done
for wf in ci gpu-smoke; do
    if ! grep -Eq "^[[:space:]]+uses:[[:space:]]+[A-Za-z0-9_.-]+/shared-workflows/\.github/workflows/${wf}\.yml@v[0-9]+[[:space:]]*$" ".github/workflows/${wf}.yml"; then
        echo "[FAIL] .github/workflows/${wf}.yml must be the thin caller of shared-workflows ${wf}.yml@v<N>." >&2
        exit 1
    fi
    if ! grep -Eq '^permissions:' ".github/workflows/${wf}.yml"; then
        echo "[FAIL] .github/workflows/${wf}.yml has no top-level permissions block." >&2
        exit 1
    fi
done
if grep -Eq '^[[:space:]]+pull_request(_target)?:' .github/workflows/gpu-smoke.yml; then
    echo "[FAIL] .github/workflows/gpu-smoke.yml must never trigger on pull requests." >&2
    exit 1
fi
if grep -REq 'ruff[^|]*\|\|[[:space:]]*true' .github/workflows; then
    echo "[FAIL] a workflow swallows ruff failures with '|| true'." >&2
    exit 1
fi
echo "[PASS] CI callers match the shared-workflows contract"

readme_lines="$(wc -l < README.md | tr -d ' ')"
if [[ "${readme_lines}" -lt 80 ]]; then
    echo "[FAIL] README.md is a stub (${readme_lines} lines). Generate all template sections through License, a Prerequisites block, and a mermaid setup→run→parse diagram." >&2
    exit 1
fi
if ! grep -Fq 'Prerequisites' README.md; then
    echo "[FAIL] README.md must include a Prerequisites block." >&2
    exit 1
fi
if ! grep -Eq '```[[:space:]]*mermaid' README.md; then
    echo "[FAIL] README.md must include a mermaid setup→run→parse diagram." >&2
    exit 1
fi
for heading in '## 1. Overview' '## 4. Hardware Requirements' '## 6. Installation' '## 7. Running the Benchmark'; do
    if ! grep -Fq "${heading}" README.md; then
        echo "[FAIL] README.md is missing ${heading}." >&2
        exit 1
    fi
done
echo "[PASS] README.md is not a stub"

echo "[INFO] Checking public docs against yaml kernel_version and Workload Number..."
"${PYTHON_BIN:-python3}" - <<'PY'
import json
import re
from pathlib import Path

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
if yaml_kv:
    for name in ("README.md", "SPEC.md"):
        path = Path(name)
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for found in re.findall(r"--kernel-version(?:\s+|\s*\|\s*)([0-9][0-9.]+)", text):
            if found != yaml_kv:
                raise SystemExit(
                    f"[FAIL] {name} uses --kernel-version {found} but "
                    f"config/benchmark_config.yaml is {yaml_kv}"
                )
        for found in re.findall(r"\|\s*Kernel\s*\|\s*kernel\s+([0-9][0-9.]+)", text):
            if found != yaml_kv:
                raise SystemExit(
                    f"[FAIL] {name} Software Requirements kernel {found} but "
                    f"yaml kernel_version is {yaml_kv}"
                )
        for found in re.findall(r"\|\s*kernel_version\s*\|[^|\n]*\|\s*([0-9][0-9.]+)\s+\(", text):
            if found != yaml_kv:
                raise SystemExit(
                    f"[FAIL] {name} Parameters kernel_version {found} but "
                    f"yaml kernel_version is {yaml_kv}"
                )
prd = Path("PRD.md")
if prd.is_file() and workload:
    match = re.search(r"(?m)^## Workload Number\s*\n+(\S+)", prd.read_text(encoding="utf-8"))
    if not match or match.group(1).strip() != workload:
        shown = match.group(1).strip() if match else "(missing)"
        raise SystemExit(f"[FAIL] PRD.md Workload Number is {shown}, expected {workload}")
for name in ("README.md", "SPEC.md", "PRD.md", "benchmark_specification.json"):
    path = Path(name)
    if path.is_file() and "TEMPLATE_00_" in path.read_text(encoding="utf-8"):
        raise SystemExit(f"[FAIL] {name} still contains a TEMPLATE_00_* authoring note")
print("[PASS] public docs match yaml kernel_version and Workload Number")
PY

if [[ -e "CLAUDE.md" ]]; then
    echo "[FAIL] CLAUDE.md must live at .claude/CLAUDE.md, not the repository root." >&2
    exit 1
fi

# hipcc on Ubuntu 26.04 / Clang 23 needs a GCC 15 host toolchain for <cstdlib>.
# The pin must stay off CXXFLAGS: host g++ (sgl-kernel) rejects --gcc-install-dir.
if [[ -f scripts/lib/hipcc_host_gcc.sh ]]; then
    if rg -n '_hipcc_append_flag CXXFLAGS|CXXFLAGS.*gcc-install-dir' scripts/lib/hipcc_host_gcc.sh >/dev/null 2>&1; then
        echo "[FAIL] scripts/lib/hipcc_host_gcc.sh must not put --gcc-install-dir on CXXFLAGS (g++ / sgl-kernel setup_rocm.py dies)." >&2
        exit 1
    fi
    echo "[PASS] hipcc host-GCC pin is not leaked into CXXFLAGS"
fi
# common.sh also exports the pin, but build.sh must be safe when invoked directly.
if rg -n '\bhipcc\b' scripts/build.sh Makefile >/dev/null 2>&1; then
    if ! rg -n 'hipcc_host_gcc|gcc-install-dir|HIPCC_COMPILE_FLAGS_APPEND' \
        scripts/build.sh Makefile >/dev/null 2>&1; then
        echo "[FAIL] scripts/build.sh or Makefile invokes hipcc without pinning a host GCC. Source scripts/lib/hipcc_host_gcc.sh or pass --gcc-install-dir=/usr/lib/gcc/x86_64-linux-gnu/15 (Ubuntu 26.04 Clang 23 otherwise misses <cstdlib>)." >&2
        exit 1
    fi
    echo "[PASS] hipcc host-GCC pin is present"
fi

python3 - <<'PY'
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, "scripts/lib")
import nvcc_glibc_throw as repair

helper = Path("scripts/lib/nvcc_glibc_throw.sh")
patcher = Path("scripts/lib/nvcc_glibc_throw.py")
for path in (helper, patcher):
    if not path.is_file():
        continue
    if repair.broad_appender_present(path.read_text(encoding="utf-8")):
        raise SystemExit(
            f"[FAIL] {path} appends __THROW to rsqrt lines without checking _NV_RSQRT_SPECIFIER"
        )
stamp = Path("results/nvcc_glibc_throw.sha256")
if Path("results/generation_manifest.json").is_file():
    if not stamp.is_file():
        raise SystemExit("[FAIL] results/nvcc_glibc_throw.sha256 is missing")
    expected = {}
    for line in stamp.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, _, rel = line.partition("  ")
        expected[rel.strip()] = digest.strip()
    for path in (helper, patcher):
        rel = path.as_posix()
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if expected.get(rel) != actual:
            raise SystemExit(f"[FAIL] {rel} does not match results/nvcc_glibc_throw.sha256")
    print("[PASS] nvcc glibc helper matches its stamp")
elif helper.is_file():
    print("[PASS] nvcc glibc helper does not use the unguarded rsqrt appender")
PY

[[ -x "scripts/collect_hw_sw_info.sh" ]] || {
    echo "[FAIL] HW/SW inventory collector is not executable." >&2
    exit 1
}
grep -Fq "DESCRIPTION : Commands To Be Run" scripts/collect_hw_sw_info.sh || {
    echo "[FAIL] HW/SW inventory collector lacks command-list sections." >&2
    exit 1
}
grep -Fq "scripts/update_runtime_ledger.py" run_benchmark.sh || {
    echo "[FAIL] run_benchmark.sh does not update /var/opt/benchmarks/runtime_ledger.csv." >&2
    exit 1
}
grep -Fq "capture_benchmark_run_command_submitted" run_benchmark.sh || {
    echo "[FAIL] run_benchmark.sh must capture submitted argv for the ledger." >&2
    exit 1
}
grep -Fq "print_benchmark_summary_commands" run_benchmark.sh || {
    echo "[FAIL] run_benchmark.sh must print Command submitted and Command fully resolved in the Benchmark Summary." >&2
    exit 1
}
grep -Fq -- "--run-benchmark-command-submitted" run_benchmark.sh || {
    echo "[FAIL] run_benchmark.sh must pass --run-benchmark-command-submitted to the ledger." >&2
    exit 1
}
grep -Fq -- "--run-benchmark-command-fully-resolved" run_benchmark.sh || {
    echo "[FAIL] run_benchmark.sh must pass --run-benchmark-command-fully-resolved to the ledger." >&2
    exit 1
}
grep -Fq 'collect_hw_sw_info.sh "${RUN_DIR}"' run_benchmark.sh || {
    echo "[FAIL] run_benchmark.sh must write HW/SW inventory into the per-run directory." >&2
    exit 1
}
if grep -Fq 'system_info.txt' run_benchmark.sh; then
    echo "[FAIL] run_benchmark.sh must not write system_info.txt." >&2
    exit 1
fi
"${PYTHON_BIN:-python3}" - <<'PY'
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "update_runtime_ledger", Path("scripts/update_runtime_ledger.py")
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
expected = [
    "table_index_number",
    "run_id",
    "workload_number",
    "runtime_root_dir",
    "benchmark_profile",
    "start_datetime",
    "total_runtime_mm_ss",
    "exit_code",
    "failure_stage",
    "failure_detail",
    "raw_run_dir",
    "hostname",
    "gpu_name",
    "gpu_vram",
    "gpu_count",
    "os_version",
    "cpu_model",
    "workload_name",
]
expected.extend(module.metric_slot_column_names())
expected.extend(["run_benchmark_command_submitted", "run_benchmark_command_fully_resolved"])
expected.extend(module.parameter_slot_column_names())
expected.extend(["parameters_set", "notes"])
if list(module.LEDGER_COLUMNS) != expected:
    raise SystemExit("[FAIL] scripts/update_runtime_ledger.py LEDGER_COLUMNS order is incorrect.")
if module.format_total_runtime_mm_ss("75") != "01:15":
    raise SystemExit("[FAIL] total_runtime_mm_ss must store elapsed time as mm:ss.")
if module.infer_failure_stage(0, "validated run") != "ok":
    raise SystemExit("[FAIL] failure_stage must be ok when exit_code is 0.")
if module.infer_failure_stage(1, "collection failed with status 1") != "collection":
    raise SystemExit("[FAIL] failure_stage must classify collection failures.")
if module.infer_failure_stage(1, "parse failed") != "parse":
    raise SystemExit("[FAIL] failure_stage must classify parse failures.")
recon = module.reconstruct_run_benchmark_command(
    {
        "Parameter_01": "kernel_version",
        "Parameter_02": "cuda_version",
        "Profile Parameter Values": '{"kernel_version":{"smoke":"6.8.0"},"cuda_version":{"smoke":"12.6"}}',
    },
    "smoke",
    "",
)
if recon != "bash run_benchmark.sh --smoke --validate --kernel-version 6.8.0 --cuda-version 12.6":
    raise SystemExit("[FAIL] run_benchmark_command reconstruction is incorrect.")
if module.reconstruct_run_benchmark_command({}, "baseline", "bash run_benchmark.sh --baseline --validate") != (
    "bash run_benchmark.sh --baseline --validate"
):
    raise SystemExit("[FAIL] explicit run_benchmark_command must win over reconstruction.")
numa_fields = {
    "Parameter_01": "num_numa_nodes",
    "Parameter_02": "num_threads",
    "Parameter_03": "stride",
    "Parameter_04": "num_iterations",
    "Profile Parameter Values": (
        '{"num_numa_nodes":{"baseline":"1"},"num_threads":{"baseline":"4"},'
        '"stride":{"baseline":"64"},"num_iterations":{"baseline":"350000000"}}'
    ),
}
resolved = module.resolve_run_benchmark_command_fully_resolved(
    numa_fields,
    "baseline",
    submitted="bash run_benchmark.sh --num-numa-nodes 1 --num-threads 4",
    explicit="",
)
if resolved != (
    "bash run_benchmark.sh --num-numa-nodes 1 --num-threads 4 "
    "--stride 64 --num-iterations 350000000"
):
    raise SystemExit("[FAIL] fully resolved command must add yaml defaults not already submitted.")
migrated = module.migrate_row(
    {
        "run_benchmark_command": "bash run_benchmark.sh --baseline --validate --stride 64",
        "exit_code": "0",
        "notes": "validated run",
    }
)
if migrated["run_benchmark_command_submitted"]:
    raise SystemExit("[FAIL] old run_benchmark_command must not become submitted.")
if migrated["run_benchmark_command_fully_resolved"] != (
    "bash run_benchmark.sh --baseline --validate --stride 64"
):
    raise SystemExit("[FAIL] old run_benchmark_command must migrate to fully_resolved.")
if migrated["Parameter_01_Name"] != "stride" or migrated["Parameter_01_Value"] != "64":
    raise SystemExit("[FAIL] old command flags must migrate into Parameter_01 Name/Value.")
if migrated["Parameter_02_Name"] or migrated["Parameter_02_Value"]:
    raise SystemExit("[FAIL] unused Parameter_* slots must stay blank.")
if module.parameter_slot_column_names()[:4] != [
    "Parameter_01_Name",
    "Parameter_01_Value",
    "Parameter_02_Name",
    "Parameter_02_Value",
]:
    raise SystemExit("[FAIL] Parameter_* columns must be interleaved Name/Value pairs.")
if len(module.parameter_slot_column_names()) != 40:
    raise SystemExit("[FAIL] ledger must add 20 Parameter_* names and 20 values.")
slots = module.resolve_parameter_slots(
    {
        "Parameter_01": "num_iterations",
        "Parameter_02": "dtype",
        "Parameter_03": "—",
        "Profile Parameter Values": (
            '{"num_iterations":{"baseline":"17300"},"dtype":{"baseline":"bfloat16"}}'
        ),
    },
    "baseline",
    submitted="bash run_benchmark.sh --baseline --validate --num-iterations 100",
    resolved_command=(
        "bash run_benchmark.sh --baseline --validate --num-iterations 100 --dtype bfloat16"
    ),
    parameters_set="profile=baseline;num_iterations=17300;dtype=bfloat16",
)
if slots[0] != ("num_iterations", "100"):
    raise SystemExit("[FAIL] submitted CLI must win over yaml for Parameter_* values.")
if slots[1] != ("dtype", "bfloat16"):
    raise SystemExit("[FAIL] Parameter_* values must fill from the resolved command.")
if slots[2] != ("", ""):
    raise SystemExit("[FAIL] empty Parameter_* workbook slots must stay blank, not em-dash.")
if module.format_parameters_set("baseline", slots) != (
    "profile=baseline;num_iterations=100;dtype=bfloat16"
):
    raise SystemExit("[FAIL] parameters_set must be rebuilt from Parameter_* slots.")
rocm_product = """
============================ ROCm System Management Interface ============================
====================================== Product Info ======================================
GPU[0]\t\t: Card Series: \t\tAMD Instinct MI300X VF
GPU[0]\t\t: Card SKU: \t\tM3000100
==========================================================================================
================================== End of ROCm SMI Log ===================================
"""
rocm_mem = """
============================ ROCm System Management Interface ============================
================================== Memory Usage (Bytes) ==================================
GPU[0]\t\t: VRAM Total Memory (B): 205822885888
GPU[0]\t\t: VRAM Total Used Memory (B): 299687936
==========================================================================================
================================== End of ROCm SMI Log ===================================
"""
amd_smi = """
GPU: 0
    ASIC:
        MARKET_NAME: AMD Instinct MI300X VF
        DEVICE_ID: 0x74b5
"""
if module.parse_gpu_name_text(rocm_product=rocm_product) != "AMD Instinct MI300X VF":
    raise SystemExit("[FAIL] gpu_name must parse Card Series and skip the ROCm SMI banner.")
if module.parse_gpu_name_text(amd_smi=amd_smi) != "AMD Instinct MI300X VF":
    raise SystemExit("[FAIL] gpu_name must parse amd-smi MARKET_NAME.")
if module.parse_gpu_vram_text(rocm_mem=rocm_mem) != "205822885888":
    raise SystemExit("[FAIL] gpu_vram must parse VRAM Total Memory (B) only.")
print("[PASS] runtime_ledger.csv column order, total_runtime_mm_ss format, and GPU field parsers")
PY
grep -Fq "scripts/ensure_setup.sh" run_benchmark.sh || {
    echo "[FAIL] run_benchmark.sh does not perform automatic setup-on-demand." >&2
    exit 1
}
"${PYTHON_BIN:-python3}" - <<'PY'
from pathlib import Path

text = Path("run_benchmark.sh").read_text(encoding="utf-8", errors="replace")
if "sed -n '1,20p'" in text or 'sed -n "1,20p"' in text:
    raise SystemExit("[FAIL] run_benchmark.sh --help must not dump the file header with sed -n '1,20p'.")
if "usage()" not in text and "usage ()" not in text:
    raise SystemExit("[FAIL] run_benchmark.sh is missing a usage() help function.")
required = (
    "Usage: bash run_benchmark.sh",
    "Run smoke profile",
    "Run baseline profile",
    "Run extended profile",
    "Existing raw file",
)
missing = [token for token in required if token not in text]
if missing:
    raise SystemExit("[FAIL] run_benchmark.sh usage() is missing required help text: " + ", ".join(missing))
help_idx = text.find("--help)")
setup_idx = text.find("scripts/ensure_setup.sh")
if help_idx < 0:
    raise SystemExit("[FAIL] run_benchmark.sh does not handle --help.")
if setup_idx < 0 or help_idx > setup_idx:
    raise SystemExit("[FAIL] run_benchmark.sh must handle --help before scripts/ensure_setup.sh.")
def_idx = text.find("--matrix-definition")
if def_idx < 0:
    raise SystemExit("[FAIL] run_benchmark.sh must handle --matrix-definition.")
if def_idx > setup_idx:
    raise SystemExit("[FAIL] run_benchmark.sh must handle --matrix-definition before scripts/ensure_setup.sh.")
if "print_benchmark_definition.py" not in text:
    raise SystemExit("[FAIL] run_benchmark.sh must invoke scripts/print_benchmark_definition.py.")
print("[PASS] run_benchmark.sh --help uses usage() before setup")
print("[PASS] run_benchmark.sh --matrix-definition prints the matrix row before setup")
PY
"${PYTHON_BIN:-python3}" - <<'PY'
import json
import re
from pathlib import Path

fields = {
    item.get("field_name", ""): str(item.get("value", ""))
    for item in json.loads(Path("benchmark_specification.json").read_text(encoding="utf-8"))
}
domain = fields.get("Execution Domain", "").lower()
framework = fields.get("Framework", "").lower()
runner = Path("run_benchmark.sh").read_text(encoding="utf-8", errors="replace")
yaml_text = Path("config/benchmark_config.yaml").read_text(encoding="utf-8", errors="replace")
if "begin_benchmark_run" not in runner:
    raise SystemExit("[FAIL] run_benchmark.sh must call begin_benchmark_run so die() writes a ledger row.")
common = Path("scripts/lib/common.sh").read_text(encoding="utf-8", errors="replace")
if "benchmark_run_err_trap" not in common or "trap" not in common:
    raise SystemExit(
        "[FAIL] scripts/lib/common.sh must install an ERR trap that writes the "
        "runtime ledger and still exits 1 (do not mask the failure)."
    )
if "llm serving" in domain:
    if re.search(r"profile:\s*smoke\b", yaml_text):
        raise SystemExit("[FAIL] LLM Serving yaml default profile must be baseline, not smoke.")
    if "profile: baseline" not in yaml_text:
        raise SystemExit("[FAIL] LLM Serving yaml must seed sweep.profile as baseline.")
    if "wait_for_server" not in runner:
        raise SystemExit("[FAIL] LLM Serving run_benchmark.sh must call wait_for_server.")
    if re.search(r"wait_for_server[^\n]*\b180\b", runner):
        raise SystemExit("[FAIL] LLM ready-wait must not hardcode 180 s; use wait_for_server default 600 s.")
    if "sglang" in framework and "600" not in runner and "BENCHMARK_READY_WAIT_SEC" not in runner:
        # default lives in common.sh; an explicit 600 or the helper default is enough
        pass
print("[PASS] runtime ledger-on-error and LLM default/ready-wait contracts")
PY

echo "[INFO] Validating STREAM checksum and leftover-DB parse contracts..."
"${PYTHON_BIN:-python3}" - <<'PY'
import json
from pathlib import Path

fields = {
    item.get("field_name", ""): str(item.get("value", ""))
    for item in json.loads(Path("benchmark_specification.json").read_text(encoding="utf-8"))
}
workload = fields.get("Workload Number", "").strip()
repo = fields.get("Repo Name", "")
stream = Path("src/stream.c")
if stream.is_file() or workload in {"107", "207"}:
    if not stream.is_file():
        raise SystemExit("[FAIL] STREAM workloads 107/207 must ship src/stream.c.")
    compact = "".join(stream.read_text(encoding="utf-8", errors="replace").split())
    if "fabs((double)(a[j]-aj))" not in compact:
        raise SystemExit(
            "[FAIL] STREAM src/stream.c must use official per-element "
            "fabs((double)(a[j] - aj)); do not sum raw array values."
        )
    if "aAvgErr/aj" not in compact:
        raise SystemExit(
            "[FAIL] STREAM src/stream.c must compare relative error "
            "(aAvgErr / aj), not an absolute residual against 1e-13."
        )
    if "aSumErr+=a[j]" in compact and "STREAM_ARRAY_SIZE" in compact:
        raise SystemExit(
            "[FAIL] STREAM checksum must not sum raw a[j] then treat the "
            "array-scale residual as an absolute 1e-13 error."
        )
    if "Solution Validates" not in stream.read_text(encoding="utf-8", errors="replace"):
        raise SystemExit("[FAIL] STREAM src/stream.c must print Solution Validates.")
    print("[PASS] STREAM official per-element relative checksum")
chase = Path("src/multichase.c")
if chase.is_file() or "multichase" in fields.get("Workload Name", "").lower():
    if not chase.is_file():
        raise SystemExit("[FAIL] multichase workloads must ship src/multichase.c.")
    text = chase.read_text(encoding="utf-8", errors="replace")
    if "void * volatile" not in text:
        raise SystemExit(
            "[FAIL] src/multichase.c must chase through void * volatile so gcc -O2 "
            "cannot dead-code-eliminate baseline 1.33e9 iterations to latency_ns 0.000000."
        )
    if "(void)p;" in text and "void * volatile" not in text:
        raise SystemExit("[FAIL] src/multichase.c (void)p; is not enough to keep the chase live.")
    print("[PASS] multichase volatile pointer-chase")
rochpl = Path("src/rochpl.cpp")
if rochpl.is_file() or workload in {"120", "320"}:
    if not rochpl.is_file():
        raise SystemExit("[FAIL] rocHPL workloads 120/320 must ship src/rochpl.cpp.")
    text = rochpl.read_text(encoding="utf-8", errors="replace")
    compact = "".join(text.split())
    if "host_a(n*n)" in compact or "host_a(n * n)" in text:
        raise SystemExit(
            "[FAIL] src/rochpl.cpp must not allocate host_a(n * n). "
            "Signed 32-bit n*n overflows at N=65536 (extended). Use size_t nn = n64 * n64."
        )
    if "size_t nn" not in text and "(size_t)n * (size_t)n" not in text and "n64 * n64" not in compact:
        raise SystemExit(
            "[FAIL] src/rochpl.cpp must compute the host matrix length with 64-bit sizes "
            "(size_t nn or (size_t)n * (size_t)n)."
        )
    print("[PASS] rocHPL host allocation uses 64-bit sizes")
    collect = Path("scripts/collect_workload.py")
    if collect.is_file():
        collect_text = collect.read_text(encoding="utf-8", errors="replace")
        if "repeats = max(2, int(args.num_iterations" in collect_text:
            raise SystemExit(
                "[FAIL] 120/320 collect_workload.py must not set "
                "repeats = max(2, int(args.num_iterations...))."
            )
        if "32768" not in collect_text or "65536" not in collect_text:
            raise SystemExit(
                "[FAIL] 120/320 collect_workload.py must clamp N>=65536 to 32768 "
                "and cap timed repeats at 16 when N>=32768."
            )
        if "min(requested, 16)" not in collect_text and "min(requested,16)" not in collect_text.replace(" ", ""):
            raise SystemExit(
                "[FAIL] 120/320 collect_workload.py must allow up to 16 timed repeats at N=32768."
            )
        if '== "extended"' not in collect_text and "== 'extended'" not in collect_text:
            raise SystemExit(
                "[FAIL] 120/320 collect_workload.py must apply the 16-repeat cap only for extended."
            )
        print("[PASS] rocHPL N=65536 clamp and 16-repeat cap at N=32768")
nvhpl = Path("src/nvhpl.cu")
if nvhpl.is_file() or workload in {"220", "420"}:
    if not nvhpl.is_file():
        raise SystemExit("[FAIL] NVIDIA HPL workloads 220/420 must ship src/nvhpl.cu.")
    text = nvhpl.read_text(encoding="utf-8", errors="replace")
    if "cusolverDnDgetrf" not in text:
        raise SystemExit("[FAIL] src/nvhpl.cu must call cusolverDnDgetrf.")
    if "size_t nn" not in text and "n64 * n64" not in "".join(text.split()):
        raise SystemExit("[FAIL] src/nvhpl.cu must use size_t host matrix length.")
    print("[PASS] NVIDIA HPL uses cuSOLVER and 64-bit host sizes")
nccl = Path("src/nccl_bw.cu")
if nccl.is_file() or workload in {"216", "416"}:
    if not nccl.is_file():
        raise SystemExit("[FAIL] NCCL workloads 216/416 must ship src/nccl_bw.cu.")
    text = nccl.read_text(encoding="utf-8", errors="replace")
    if "ncclAllReduce" not in text or "#include <nccl.h>" not in text:
        raise SystemExit("[FAIL] src/nccl_bw.cu must include nccl.h and call ncclAllReduce.")
    print("[PASS] NCCL overlay links libnccl")
gups = Path("src/gups.c")
if gups.is_file() or workload in {"213", "413"}:
    if not gups.is_file():
        raise SystemExit("[FAIL] GUPS workloads 213/413 must ship src/gups.c.")
    text = gups.read_text(encoding="utf-8", errors="replace")
    if "omp" not in text.lower():
        raise SystemExit("[FAIL] src/gups.c must be an OpenMP random-update kernel.")
    print("[PASS] NVIDIA GUPS is OpenMP C")
collect = Path("scripts/collect_workload.py")
if collect.is_file():
    collect_text = collect.read_text(encoding="utf-8", errors="replace")
    if "def value_for(" in collect_text and "return 10.0" in collect_text:
        raise SystemExit("[FAIL] collect_workload.py must not invent TFLOPS/bandwidth from column names.")
    if workload in {"216", "416"} and "bin/nccl_bw" not in collect_text:
        raise SystemExit("[FAIL] 216/416 collect_workload.py must run bin/nccl_bw.")
    if workload in {"220", "420"} and "bin/nvhpl" not in collect_text:
        raise SystemExit("[FAIL] 220/420 collect_workload.py must run bin/nvhpl.")
if workload in {"130", "230", "330"} or "sglang-prompt-response" in repo:
    parse = Path("scripts/parse_results.py")
    text = parse.read_text(encoding="utf-8", errors="replace")
    if "ADD COLUMN" not in text and "rebuilding" not in text:
        raise SystemExit(
            "[FAIL] 130/230/330 parse_results.py must migrate or rebuild leftover "
            "results/benchmark.db (ADD COLUMN or rebuild on INSERT failure)."
        )
    if workload in {"130", "330"} and "rocm_version" not in text:
        raise SystemExit("[FAIL] 130/330 parse_results.py must record rocm_version.")
    if workload in {"230", "430"} and "cuda_version" not in text:
        raise SystemExit("[FAIL] 230/430 parse_results.py must record cuda_version.")
    print("[PASS] leftover-DB parse migrate/rebuild contract")
if workload in {"131", "231", "331"} or "sglang-serving-latency" in repo:
    runner = Path("run_benchmark.sh").read_text(encoding="utf-8", errors="replace")
    if "tiny_sglang_server.py" not in runner:
        raise SystemExit("[FAIL] 131/231/331 smoke must be able to start scripts/tiny_sglang_server.py.")
    if "sglang.launch_server" not in runner:
        raise SystemExit("[FAIL] 131/231/331 baseline/extended must start python -m sglang.launch_server.")
    if workload in {"131", "331"} and "isolate_repo_python" not in runner:
        raise SystemExit("[FAIL] 131/331 run_benchmark.sh must call isolate_repo_python.")
    client = Path("scripts/bench_serving.py")
    if client.is_file():
        client_text = client.read_text(encoding="utf-8", errors="replace")
        compact = client_text.replace(" ", "")
        if "num_prompts=min(" in compact or "num_prompts=min(num_prompts,concurrency)" in compact:
            raise SystemExit(
                "[FAIL] 131/231/331 bench_serving.py must not assign "
                "num_prompts = min(num_prompts, concurrency)."
            )
    if workload == "231":
        setup = Path("setup.sh").read_text(encoding="utf-8", errors="replace")
        if "install_sglang_nvidia.sh" not in setup:
            raise SystemExit("[FAIL] 231 setup.sh must call scripts/install_sglang_nvidia.sh.")
        if "ninja" not in setup and "ninja-build" not in setup:
            if not Path("scripts/install_sglang_nvidia.sh").is_file():
                raise SystemExit("[FAIL] 231 must install ninja / ninja-build.")
        if "prepend_venv_nvidia_libs" not in runner:
            raise SystemExit("[FAIL] 231 run_benchmark.sh must prepend venv nvidia/*/lib.")
        if 'bash -c "${server_cmd}"' not in runner and "bash -c " not in runner:
            raise SystemExit("[FAIL] 231 must launch SGLang with bash -c, not bash -lc.")
    if workload in {"131", "331"}:
        if 'import sglang' not in runner:
            raise SystemExit("[FAIL] 131/331 run_benchmark.sh must check import sglang before launch_server.")
        ensure = Path("scripts/ensure_setup.sh")
        if ensure.is_file():
            ensure_text = ensure.read_text(encoding="utf-8", errors="replace")
            if "tiny_sglang_server.py" not in ensure_text or "smoke" not in ensure_text:
                raise SystemExit(
                    "[FAIL] 131/331 scripts/ensure_setup.sh must skip full SGLang "
                    "compile checks when the profile is smoke."
                )
    if workload == "331":
        if "--disable-cuda-graph" not in runner:
            raise SystemExit("[FAIL] 331 run_benchmark.sh must launch with --disable-cuda-graph.")
        if "--watchdog-timeout" not in runner:
            raise SystemExit("[FAIL] 331 run_benchmark.sh must launch with --watchdog-timeout (first AITER JIT exceeds 300s).")
        if "lock_module_" not in runner:
            raise SystemExit("[FAIL] 331 run_benchmark.sh must delete leftover AITER lock_module_* files before launch.")
        ensure = Path("scripts/ensure_setup.sh")
        if ensure.is_file():
            ensure_text = ensure.read_text(encoding="utf-8", errors="replace")
            if "import sglang" not in ensure_text or "launch_server --help" not in ensure_text:
                raise SystemExit(
                    "[FAIL] 331 scripts/ensure_setup.sh must re-run setup when "
                    "import sglang or launch_server --help fails."
                )
            if "tiny_sglang_server.py" not in ensure_text or "smoke" not in ensure_text:
                raise SystemExit(
                    "[FAIL] 331 scripts/ensure_setup.sh must skip full SGLang "
                    "compile checks when the profile is smoke."
                )
    print("[PASS] 131/231/331 SGLang smoke-vs-real launch contract")
if workload in {"127", "128", "129", "227", "228", "229", "327", "328", "329"}:
    runner = Path("run_benchmark.sh").read_text(encoding="utf-8", errors="replace")
    if "scripts/tiny_kv_server.py --host" in runner:
        raise SystemExit(
            "[FAIL] 127-129/227-229/327-329 must launch real vLLM for every profile, including smoke."
        )
    if "vllm.entrypoints.openai.api_server" not in runner:
        raise SystemExit(
            "[FAIL] 127-129/227-229/327-329 must start "
            "python -m vllm.entrypoints.openai.api_server for every profile."
        )
    if workload in {"128", "129", "228", "229", "327", "328", "329"}:
        if "TOKENIZER_CONTEXT_SLACK" not in runner:
            raise SystemExit(
                "[FAIL] 128/129/228/229/327/328/329 run_benchmark.sh must set TOKENIZER_CONTEXT_SLACK "
                "so max_model_len is at least input+output+64 (BOS). Tight input+output returns HTTP 400."
            )
        client = Path("scripts/benchmark_serving.py")
        if client.is_file():
            client_text = client.read_text(encoding="utf-8", errors="replace")
            if "HTTPError" not in client_text:
                raise SystemExit("[FAIL] 128/129/228/229/327/328/329 benchmark_serving.py must surface HTTP 400 bodies.")
            if "TOKENIZER_BOS_SLACK" not in client_text and "clamp_max_tokens" not in client_text:
                raise SystemExit("[FAIL] 128/129/228/229/327/328/329 client must clamp max_tokens for tokenizer/BOS slack.")
        print("[PASS] 128/129/228/229/327/328/329 vLLM tokenizer context slack")
    print("[PASS] 127-129/227-229/327-329 vLLM smoke-vs-real launch contract")
if workload in {"130", "230", "330"} or "sglang-prompt-response" in repo:
    runner = Path("run_benchmark.sh").read_text(encoding="utf-8", errors="replace")
    if "tiny_sglang_server.py" not in runner:
        raise SystemExit("[FAIL] 130/230/330 smoke must be able to start scripts/tiny_sglang_server.py.")
    if "sglang.launch_server" not in runner:
        raise SystemExit("[FAIL] 130/230/330 baseline/extended must start python -m sglang.launch_server.")
    if "prompt_response_client.py" not in runner:
        raise SystemExit("[FAIL] 130/230/330 must use scripts/prompt_response_client.py.")
    if workload in {"130", "330"} and "isolate_repo_python" not in runner:
        raise SystemExit("[FAIL] 130/330 run_benchmark.sh must call isolate_repo_python.")
    if workload == "230":
        setup = Path("setup.sh").read_text(encoding="utf-8", errors="replace")
        if "install_sglang_nvidia.sh" not in setup:
            raise SystemExit("[FAIL] 230 setup.sh must call scripts/install_sglang_nvidia.sh.")
        if "prepend_venv_nvidia_libs" not in runner:
            raise SystemExit("[FAIL] 230 run_benchmark.sh must prepend venv nvidia/*/lib.")
    if workload in {"130", "330"}:
        if 'import sglang' not in runner:
            raise SystemExit("[FAIL] 130/330 run_benchmark.sh must check import sglang before launch_server.")
        ensure = Path("scripts/ensure_setup.sh")
        if ensure.is_file():
            ensure_text = ensure.read_text(encoding="utf-8", errors="replace")
            if "tiny_sglang_server.py" not in ensure_text or "smoke" not in ensure_text:
                raise SystemExit(
                    "[FAIL] 130/330 scripts/ensure_setup.sh must skip full SGLang "
                    "compile checks when the profile is smoke."
                )
    if workload == "330":
        if "--disable-cuda-graph" not in runner:
            raise SystemExit("[FAIL] 330 run_benchmark.sh must launch with --disable-cuda-graph.")
        if "--watchdog-timeout" not in runner:
            raise SystemExit("[FAIL] 330 run_benchmark.sh must launch with --watchdog-timeout (first AITER JIT exceeds 300s).")
        if "lock_module_" not in runner:
            raise SystemExit("[FAIL] 330 run_benchmark.sh must delete leftover AITER lock_module_* files before launch.")
        if "--mem-fraction-static" not in runner:
            raise SystemExit("[FAIL] 330 run_benchmark.sh must launch with --mem-fraction-static (same as 430).")
        ensure = Path("scripts/ensure_setup.sh")
        if ensure.is_file():
            ensure_text = ensure.read_text(encoding="utf-8", errors="replace")
            if "import sglang" not in ensure_text or "launch_server --help" not in ensure_text:
                raise SystemExit(
                    "[FAIL] 330 scripts/ensure_setup.sh must re-run setup when "
                    "import sglang or launch_server --help fails."
                )
            if "tiny_sglang_server.py" not in ensure_text or "smoke" not in ensure_text:
                raise SystemExit(
                    "[FAIL] 330 scripts/ensure_setup.sh must skip full SGLang "
                    "compile checks when the profile is smoke."
                )
    print("[PASS] 130/230/330 SGLang sequential smoke-vs-real launch contract")
if workload in {"430", "431"} or ("ubu2604" in repo and "sglang" in repo and "nvidia" in repo):
    setup = Path("setup.sh").read_text(encoding="utf-8", errors="replace")
    for rel in (
        "scripts/install_sglang_nvidia.sh",
        "scripts/install_sglang_launch_deps.py",
        "scripts/sglang_py314_patch.py",
        "scripts/sglang_py314.pth",
    ):
        if not Path(rel).is_file():
            raise SystemExit(f"[FAIL] 430/431 must keep overlay {rel}.")
    helper = Path("scripts/install_sglang_nvidia.sh").read_text(encoding="utf-8", errors="replace")
    if "2.13.0+cu130" not in helper or "0.4.6.post1" not in helper or "0.5.10.post1" not in helper or "--no-deps" not in helper or "uvicorn" not in helper:
        raise SystemExit("[FAIL] 430/431 install_sglang_nvidia.sh must pin torch 2.13.0+cu130, sglang-kernel 0.4.6.post1, sglang --no-deps, and uvicorn.")
    if "moe_fused_gate" not in Path("scripts/sglang_py314_patch.py").read_text(encoding="utf-8", errors="replace"):
        raise SystemExit("[FAIL] 430/431 sglang_py314_patch.py must define sgl_kernel::moe_fused_gate.")
    runner = Path("run_benchmark.sh")
    if runner.is_file() and "attention-backend flashinfer" not in runner.read_text(encoding="utf-8", errors="replace"):
        raise SystemExit("[FAIL] 430/431 run_benchmark.sh must launch SGLang with --attention-backend flashinfer.")
    if "install_sglang_nvidia.sh" not in setup:
        raise SystemExit("[FAIL] 430/431 setup.sh must call scripts/install_sglang_nvidia.sh.")
    sampler_sources = setup + "\n" + helper
    if "create_sampler" not in sampler_sources and "install_sglang_launch_deps.py" not in sampler_sources:
        raise SystemExit("[FAIL] 430/431 setup must verify the SGLang sampler or run install_sglang_launch_deps.py.")
    print("[PASS] 430/431 Ubuntu 26.04 SGLang cu130 contract")
if workload in {"130", "131", "230", "231", "330", "331", "430", "431"} or ("sglang" in repo and ("nvidia" in repo or "amd" in repo)):
    runner_path = Path("run_benchmark.sh")
    if runner_path.is_file():
        runner_text = runner_path.read_text(encoding="utf-8", errors="replace")
        if "prefetch_sglang_model.py" not in runner_text or "--model-path ${sglang_model_path}" not in runner_text:
            raise SystemExit(
                "[FAIL] 130/131/230/231/330/331/430/431 run_benchmark.sh must run scripts/prefetch_sglang_model.py "
                "and pass the snapshot directory to sglang.launch_server."
            )
        if "tiny_sglang_server.py" not in runner_text:
            raise SystemExit("[FAIL] 130/131/230/231/330/331/430/431 smoke must still start scripts/tiny_sglang_server.py.")
    if not Path("scripts/prefetch_sglang_model.py").is_file():
        raise SystemExit("[FAIL] 130/131/230/231/330/331/430/431 must keep overlay scripts/prefetch_sglang_model.py.")
    print("[PASS] SGLang shard prefetch contract")
if workload in {"132", "232", "332", "432"} or "rag-faiss" in repo:
    runner = Path("scripts/gpu-bench-rag-faiss-end2end.py")
    if not runner.is_file():
        raise SystemExit("[FAIL] 132/232/332/432 must keep overlay scripts/gpu-bench-rag-faiss-end2end.py.")
    text = runner.read_text(encoding="utf-8", errors="replace")
    if "AutoModelForCausalLM" not in text or "rajpurkar/squad_v2" not in text:
        raise SystemExit("[FAIL] 132/232/332/432 RAG runner must load squad_v2 and Mistral, not a Linear stub.")
    if "transformers_weight_source" in text or ".transformers-alias-" in text:
        raise SystemExit("[FAIL] 132/232/332/432 must not alias consolidated.safetensors to model.safetensors.")
    if "output_loading_info=True" not in text or "reject_missing_causal_weights" not in text or "ensure_mistral" not in text:
        raise SystemExit(
            "[FAIL] 132/232/332/432 must prefetch Hugging Face shards and fail when causal-LM weights are missing."
        )
    if "nn.Linear" in text and "AutoModelForCausalLM" not in text:
        raise SystemExit("[FAIL] 132/232/332/432 must not ship a synthetic Linear encoder/generator.")
    setup = Path("setup.sh").read_text(encoding="utf-8", errors="replace")
    path_file = Path("scripts/rag_model_paths.py")
    if path_file.is_file():
        path_text = path_file.read_text(encoding="utf-8", errors="replace")
        if "tokenizer.json" not in path_text or '"tokenizer.model"' not in path_text:
            raise SystemExit(
                "[FAIL] 132/232/332/432 scripts/rag_model_paths.py must require tokenizer.json "
                "or tokenizer.model. tokenizer.model.v3 is not a Transformers tokenizer."
            )
        if "is not a Transformers checkpoint" not in path_text or "model.safetensors.index.json" not in path_text:
            raise SystemExit(
                "[FAIL] 132/232/332/432 scripts/rag_model_paths.py must require Hugging Face weights. "
                "consolidated.safetensors is not a Transformers checkpoint."
            )
    if workload in {"232", "432"} or "nvidia" in repo:
        for rel in ("scripts/prefetch_rag_models.py", "scripts/rag_model_paths.py", "scripts/install_rag_nvidia.sh"):
            if not Path(rel).is_file():
                raise SystemExit(f"[FAIL] 232/432 must keep overlay {rel}.")
        if "install_rag_nvidia.sh" not in setup and "prefetch_rag_models.py" not in setup:
            raise SystemExit("[FAIL] 232/432 setup.sh must call install_rag_nvidia.sh or prefetch_rag_models.py.")
        rag_install = Path("scripts/install_rag_nvidia.sh")
        if rag_install.is_file() and "sentencepiece" not in rag_install.read_text(encoding="utf-8", errors="replace"):
            raise SystemExit("[FAIL] 232/432 scripts/install_rag_nvidia.sh must install sentencepiece (Mistral tokenizer.model).")
        print("[PASS] 232/432 NVIDIA RAG overlay contract")
    if workload in {"132", "332"} or ("rag-faiss" in repo and "amd" in repo):
        for rel in ("scripts/prefetch_rag_models.py", "scripts/rag_model_paths.py", "scripts/install_rag_amd.sh"):
            if not Path(rel).is_file():
                raise SystemExit(f"[FAIL] 132/332 must keep overlay {rel}.")
        if "install_rag_amd.sh" not in setup and "prefetch_rag_models.py" not in setup:
            raise SystemExit("[FAIL] 132/332 setup.sh must call install_rag_amd.sh or prefetch_rag_models.py.")
        rag_install = Path("scripts/install_rag_amd.sh")
        if rag_install.is_file() and "sentencepiece" not in rag_install.read_text(encoding="utf-8", errors="replace"):
            raise SystemExit("[FAIL] 132/332 scripts/install_rag_amd.sh must install sentencepiece (Mistral tokenizer.model).")
        print("[PASS] 132/332 AMD RAG overlay contract")
PY

echo "[INFO] Validating workload setup contract..."
"${PYTHON_BIN:-python3}" - <<'PY'
import json
from pathlib import Path

fields = {
    item.get("field_name", ""): str(item.get("value", ""))
    for item in json.loads(Path("benchmark_specification.json").read_text(encoding="utf-8"))
}
domain = fields.get("Execution Domain", "").lower()
framework = fields.get("Framework", "").lower()
vendor = fields.get("GPU Vendor", "").strip().lower()
rocm_required = vendor != "nvidia" and any(
    token in domain or token in framework for token in ("rocm", "llm serving", "vllm", "amd-smi")
)
if vendor == "nvidia":
    setup = Path("setup.sh").read_text(encoding="utf-8", errors="replace")
    if "rocm_install_runtime" in setup and not setup.split("rocm_install_runtime", 1)[0].rstrip().endswith("#"):
        # Comment tokens for historical self_check are allowed; live ROCm install is not.
        live = [line for line in setup.splitlines() if "rocm_install_runtime" in line and not line.lstrip().startswith("#")]
        if live:
            raise SystemExit("[FAIL] NVIDIA setup.sh must not execute rocm_install_runtime.")
    needs_torch = any(token in framework for token in ("pytorch", "torchvision", "jax", "transformers", "bert", "distilbert"))
    serving = "vllm" in framework or "sglang" in framework
    if needs_torch and not serving:
        if "install_pytorch_nvidia.sh" not in setup and "download.pytorch.org/whl/cu" not in setup:
            raise SystemExit("[FAIL] NVIDIA PyTorch/JAX/Transformers setup must call install_pytorch_nvidia.sh or a CUDA wheel index.")
    for src, binary in (
        ("src/cublas_gemm.cu", "bin/cublas_gemm"),
        ("src/cudnn_conv.cu", "bin/cudnn_conv"),
        ("src/numa_sweep.cpp", "bin/numa_sweep"),
        ("src/babelstream.cu", "bin/babelstream"),
        ("src/ecc_walk.cu", "bin/ecc_walk"),
        ("src/gups.c", "bin/gups"),
        ("src/cuda_memcpy.cu", "bin/cuda_memcpy"),
        ("src/nccl_bw.cu", "bin/nccl_bw"),
        ("src/nvhpl.cu", "bin/nvhpl"),
        ("src/gpu_stress.cu", "bin/gpu_stress"),
    ):
        if Path(src).is_file():
            build = Path("scripts/build.sh").read_text(encoding="utf-8", errors="replace") if Path("scripts/build.sh").is_file() else ""
            if binary.split("/")[-1] not in build and src.split("/")[-1] not in build:
                raise SystemExit(f"[FAIL] NVIDIA {src} is present but scripts/build.sh does not compile it.")
            if "cuda_stack_probe.cu" in build and "elif" in build:
                raise SystemExit("[FAIL] NVIDIA scripts/build.sh must not prefer cuda_stack_probe.cu over the overlay source.")
    print("[PASS] NVIDIA setup contract is vendor-gated and compile-aware")
if rocm_required:
    setup = Path("setup.sh").read_text(encoding="utf-8", errors="replace")
    required_tokens = (
        "source scripts/lib/rocm_install.sh",
        "rocm_install_runtime",
        "rocm_add_repository",
    )
    missing = [token for token in required_tokens if token not in setup]
    if missing:
        raise SystemExit("[FAIL] ROCm setup contract missing: " + ", ".join(missing))
    if "rocm_install_runtime" not in setup or "rocm_add_repository" not in setup:
        raise SystemExit("[FAIL] ROCm setup must call runtime and repository logic")
    if "vllm" in framework:
        for token in ("wheels.vllm.ai/rocm/", "import vllm"):
            if token not in setup:
                raise SystemExit(f"[FAIL] vLLM ROCm contract missing: {token}")
    if "sglang" in framework:
        for token in ("import aiter", "SGLANG_USE_AITER", "github.com/ROCm/aiter.git"):
            if token not in setup:
                raise SystemExit(f"[FAIL] SGLang AITER contract missing: {token}")
        if "BENCHMARK_INSTALL_AITER_WAS_SET" not in setup:
            raise SystemExit("[FAIL] SGLang setup must auto-enable AITER from Framework.")
        if "BENCHMARK_COMPILE_SGLANG_WAS_SET" not in setup:
            raise SystemExit("[FAIL] SGLang setup must default BENCHMARK_COMPILE_SGLANG=1 when Framework includes sglang.")
        if 'log_warn "SGLang source compile skipped' in setup:
            raise SystemExit("[FAIL] SGLang setup must die if sglang is not importable; do not warn-and-continue.")
        for token in ("pyzmq", "orjson", "starlette", "openai", "dill", "exist_ok=True"):
            if token not in setup:
                raise SystemExit(
                    f"[FAIL] SGLang setup must install launch extras and patch "
                    f"qwen3_asr AutoConfig.register(..., exist_ok=True). Missing: {token}"
                )
    if "amd-smi" in framework and "import amdsmi" not in setup:
        raise SystemExit("[FAIL] Workload requires amdsmi verification")
    print("[PASS] ROCm setup contract is canonical and workload-aware")
else:
    print("[PASS] CPU/System setup contract does not require ROCm")
PY

referenced_paths="$("${PYTHON_BIN:-python3}" - <<'PY'
import re
from pathlib import Path

pattern = re.compile(r"(scripts/[A-Za-z0-9_.:/-]+\.(?:py|sh))")
optional = re.compile(r"\[\[\s+-f\s+(scripts/[A-Za-z0-9_.:/-]+\.(?:py|sh))\s+\]\]")
for path in (Path("setup.sh"), Path("run_benchmark.sh")):
    if path.exists():
        text = path.read_text(encoding="utf-8", errors="replace")
        guarded = set(optional.findall(text))
        for match in sorted(set(pattern.findall(text))):
            if match in guarded:
                continue
            print(match)
PY
)"
while IFS= read -r referenced; do
  referenced="${referenced//$'\r'/}"
  [[ -z "${referenced}" ]] && continue
  if [[ ! -f "${referenced}" ]]; then
    echo "[FAIL] Referenced workload helper is missing: ${referenced}" >&2
    exit 1
  fi
done <<< "${referenced_paths}"

for helper in timestamp_utc iso_utc_now set_log_level run_cmd run_logged_cmd capture_journal_warnings begin_benchmark_run mark_benchmark_measure_start capture_benchmark_run_command_submitted set_benchmark_run_command print_benchmark_summary_commands append_runtime_ledger_on_error wait_for_server isolate_repo_python benchmark_run_err_trap; do
  if ! rg -n "^[[:space:]]*${helper}[[:space:]]*\\(\\)" scripts/lib/common.sh >/dev/null; then
    echo "[FAIL] Canonical common.sh is missing helper: ${helper}" >&2
    exit 1
  fi
done
if ! rg -n 'SERVER_PID' scripts/lib/common.sh >/dev/null || ! rg -n 'kill -0' scripts/lib/common.sh >/dev/null; then
    echo "[FAIL] wait_for_server must fail fast when SERVER_PID has exited." >&2
    exit 1
fi

if rg -l 'Raw Output Format|Raw Output Example' scripts/parse_results.py >/dev/null 2>&1; then
  "${PYTHON_BIN:-python3}" - <<'PY'
import json
from pathlib import Path
fields = {item["field_name"]: item.get("value", "") for item in json.loads(Path("benchmark_specification.json").read_text())}
missing = [name for name in ("Raw Output Format", "Raw Output Example") if not str(fields.get(name, "")).strip()]
if missing:
    raise SystemExit(f"[FAIL] benchmark_specification.json lacks raw-output contract fields: {', '.join(missing)}")
PY
fi

# The nested template copy exists while a workload is generated and is removed
# by scripts/remove_template_copy.py once the workload passes. A present copy
# must be complete; an absent copy must be recorded as removed in the manifest.
read -r template_copy_name template_copy_removed_at < <("${PYTHON_BIN:-python3}" - <<'PY'
import json

manifest = json.loads(open("results/generation_manifest.json", encoding="utf-8").read())
print(manifest.get("template_copy_path") or "-", manifest.get("template_copy_removed_at") or "-")
PY
) || true
if [[ -z "${template_copy_name:-}" || -z "${template_copy_removed_at:-}" ]]; then
    echo "[FAIL] Could not read template copy fields from results/generation_manifest.json." >&2
    exit 1
fi
if [[ "${template_copy_name}" != "-" && -d "${template_copy_name}" ]]; then
    if [[ -e "${template_copy_name}/CLAUDE.md" ]]; then
        echo "[FAIL] Nested template copy must keep Claude guidance at .claude/CLAUDE.md, not CLAUDE.md." >&2
        exit 1
    fi
    for rel in "AGENTS.md" ".claude/CLAUDE.md" "BenchmarkSpecDefinitions.xlsx" \
      "docs/generation-workflow.md" "scripts/create_generated_repo.py"; do
        [[ -e "${template_copy_name}/${rel}" ]] || {
            echo "[FAIL] Active template copy is incomplete: ${template_copy_name}/${rel}" >&2
            exit 1
        }
    done
    echo "[PASS] Complete active template copy is present: ${template_copy_name}"
elif [[ "${template_copy_removed_at}" != "-" ]]; then
    echo "[PASS] Nested template copy was removed after generation at ${template_copy_removed_at}"
else
    echo "[FAIL] Complete active template copy is missing, and results/generation_manifest.json does not record template_copy_removed_at." >&2
    exit 1
fi

VENV_ROOT="$(pwd)/.venv"
PYTHON_BIN="${VENV_ROOT}/bin/python"
[[ -x "${PYTHON_BIN}" ]] || {
    echo "[FAIL] Missing ${PYTHON_BIN}; run setup.sh first." >&2
    exit 1
}

"${PYTHON_BIN}" scripts/validate_template_inputs.py \
  --generation-manifest results/generation_manifest.json \
  --generation-schema schemas/generation_report.schema.json

echo "[INFO] Running fixture seed validation check..."
"${PYTHON_BIN}" scripts/validate_results.py --seed-fixture --quiet

latest_run_dir="$("${PYTHON_BIN}" - <<'PY'
from pathlib import Path

runs = sorted(
    (path for path in Path("results/raw").iterdir() if path.is_dir()),
    key=lambda path: path.name,
)
print(runs[-1] if runs else "")
PY
)"
[[ -n "${latest_run_dir}" ]] || {
    echo "[FAIL] No benchmark run artifact directory exists." >&2
    exit 1
}
[[ -s "${latest_run_dir}/commands_executed.sh" ]] || {
    echo "[FAIL] Missing or empty ${latest_run_dir}/commands_executed.sh." >&2
    exit 1
}
[[ -x "${latest_run_dir}/commands_executed.sh" ]] || {
    echo "[FAIL] ${latest_run_dir}/commands_executed.sh is not executable." >&2
    exit 1
}
for inventory_file in hardware_info.txt software_info.txt errors_info.txt; do
  [[ -s "${latest_run_dir}/${inventory_file}" ]] || {
    echo "[FAIL] Missing or empty ${latest_run_dir}/${inventory_file}." >&2
    exit 1
  }
done
if [[ -e "${latest_run_dir}/system_info.txt" ]]; then
    echo "[FAIL] ${latest_run_dir}/system_info.txt must not be written; use hardware_info.txt, software_info.txt, and errors_info.txt." >&2
    exit 1
fi

if [[ -f results/overlay_lock.json ]]; then
    python3 - <<'PY'
import hashlib, json
from pathlib import Path
lock = json.loads(Path("results/overlay_lock.json").read_text(encoding="utf-8"))
for rel, meta in lock.items():
    path = Path(rel)
    if not path.is_file():
        raise SystemExit(f"[FAIL] Locked overlay missing: {rel} ({meta.get('component_id')})")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != meta.get("sha256"):
        raise SystemExit(f"[FAIL] Locked overlay rewritten: {rel} ({meta.get('component_id')})")
print("[PASS] overlay_lock.json matches generated overlay bytes")
PY
fi

python3 - <<'PY'
import json, re
from pathlib import Path
lock = Path("results/overlay_lock.json")
if not lock.is_file():
    raise SystemExit(0)
meta = json.loads(lock.read_text(encoding="utf-8"))
component_ids = {item.get("component_id") for item in meta.values()}
copy = ""
manifest = Path("results/generation_manifest.json")
if manifest.is_file():
    copy = str(json.loads(manifest.read_text(encoding="utf-8")).get("template_copy_path") or "")
root = Path(copy) / "implementation_components" if copy else Path("implementation_components")
gates = {}
if root.is_dir():
    for cid in component_ids:
        gate = root / str(cid) / "gate.json"
        if gate.is_file():
            gates[cid] = json.loads(gate.read_text(encoding="utf-8"))
elif Path("results/component_gates.json").is_file():
    # Saved by scripts/remove_template_copy.py before the nested copy was deleted.
    saved = json.loads(Path("results/component_gates.json").read_text(encoding="utf-8"))
    gates = {cid: saved[cid] for cid in component_ids if cid in saved}
elif component_ids:
    print("[WARN] component gate files unavailable (no template copy and no results/component_gates.json); "
          "forbidden_cli checks NOT EVALUATED")
    raise SystemExit(0)
text_blobs = []
for path in ("run_benchmark.sh", "scripts/collect_workload.py", "scripts/build.sh"):
    target = Path(path)
    if target.is_file():
        text_blobs.append(target.read_text(encoding="utf-8", errors="replace"))
joined = "\n".join(text_blobs)
for cid, data in gates.items():
    for token in data.get("forbidden_cli") or []:
        if token and token in joined:
            raise SystemExit(f"[FAIL] forbidden CLI {token!r} found for {cid}")
print("[PASS] component gate forbidden_cli checks")
PY

if rg -n "\r$" . \
  --glob "*.sh" \
  --glob "*.py" \
  --glob "*.md" \
  --glob "*.yml" \
  --glob "*.yaml" \
  --glob "*.json" \
  --glob "*.txt" \
  --glob "!.venv/**" \
  --glob "!**/implementation_components/**" \
  --glob "!third_party/**" \
  --glob "!**/third_party/**" \
  --glob "!results/raw/**" \
  --glob "!.cache/**" >/dev/null; then
    echo "[FAIL] CRLF line endings detected in generated text files." >&2
    exit 1
fi

echo "[PASS] Generated repository self-check succeeded."
