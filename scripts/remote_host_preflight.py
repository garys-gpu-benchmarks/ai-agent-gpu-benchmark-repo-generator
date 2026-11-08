#!/usr/bin/env python3
# File: scripts/remote_host_preflight.py
# Description: Probe the validation VM once, before workload 1, and report what
#              will slow or fail the batch. Warnings only: this never stops
#              generation (TEMPLATE_00_119).
# Execution: called by scripts/create_one_workload.py; also runnable alone:
#   python3 scripts/remote_host_preflight.py --prompt-file <prompt> --workload 401 ... --workload 432
#
# Why: on 2026-11-03 the 401-432 bundle took 3h16m on 103.207.149.92 and 1h48m on
# 64.247.201.37 (2026-10-22) with byte-identical installers. Downloads were 2-5x
# slower, every SSH call was slower, the kernel was 6.8 against a workbook 7.0.0,
# and the container had no NUMA policy. Each of these is visible in a minute here.
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

# Per-workload create time (seconds, passing attempt) from the reference runs:
# amd-24.04 Project410 (118), nvidia-24.04 Project411 (118),
# amd-26.04 Project412 (118), nvidia-26.04 Project408 (117, 64.247.201.37).
REFERENCE_SECONDS: dict[str, dict[str, int]] = {
    "amd-24.04": {"01": 473, "02": 49, "03": 290, "04": 70, "05": 108, "06": 67, "07": 47, "08": 40, "09": 107, "10": 69, "11": 58, "12": 103, "13": 75, "14": 57, "15": 56, "16": 56, "17": 312, "18": 119, "19": 109, "20": 61, "21": 127, "22": 146, "23": 136, "24": 182, "25": 147, "26": 144, "27": 390, "28": 213, "29": 209, "30": 395, "31": 410, "32": 235},
    "nvidia-24.04": {"01": 404, "02": 64, "03": 76, "04": 79, "05": 143, "06": 82, "07": 55, "08": 55, "09": 67, "10": 69, "11": 95, "12": 136, "13": 76, "14": 112, "15": 79, "16": 91, "17": 73, "18": 86, "19": 195, "20": 86, "21": 184, "22": 145, "23": 167, "24": 210, "25": 136, "26": 166, "27": 361, "28": 280, "29": 269, "30": 463, "31": 358, "32": 232},
    "amd-26.04": {"01": 381, "02": 38, "03": 272, "04": 57, "05": 94, "06": 65, "07": 42, "08": 31, "09": 77, "10": 46, "11": 58, "12": 105, "13": 42, "14": 58, "15": 46, "16": 44, "17": 310, "18": 99, "19": 104, "20": 51, "21": 112, "22": 129, "23": 128, "24": 172, "25": 126, "26": 133, "27": 340, "28": 181, "29": 278, "30": 357, "31": 349, "32": 237},
    "nvidia-26.04": {"01": 919, "02": 93, "03": 126, "04": 119, "05": 151, "06": 123, "07": 109, "08": 102, "09": 81, "10": 74, "11": 95, "12": 125, "13": 79, "14": 128, "15": 123, "16": 165, "17": 122, "18": 106, "19": 181, "20": 96, "21": 182, "22": 188, "23": 180, "24": 234, "25": 201, "26": 156, "27": 356, "28": 276, "29": 265, "30": 551, "31": 469, "32": 287},
}
# Workloads whose time is mostly package and model downloads.
DOWNLOAD_HEAVY = {"01"} | {f"{n:02d}" for n in range(21, 33)}
# Assumed speeds of the reference hosts. They were not measured at the time;
# every preflight now records its own numbers in the batch manifest, so these
# can be replaced with measured values later.
REFERENCE_DOWNLOAD_MB_S = 100.0
REFERENCE_SSH_CALL_S = 1.0
# Warning thresholds.
SLOW_DOWNLOAD_MB_S = 30.0
SLOW_SSH_CALL_S = 3.0
LOW_DISK_GB = 150.0
SLOW_ESTIMATE_RATIO = 1.5

PROBE_MARK = "PREFLIGHT_KV"

# Each line prints KEY=VALUE. Every probe is guarded so one failure never hides the rest.
PROBE_SCRIPT = r"""
set +e
kv() { printf '%s %s=%s\n' PREFLIGHT_KV "$1" "$2"; }
. /etc/os-release 2>/dev/null; kv os_version_id "${VERSION_ID:-}"
kv kernel "$(uname -r)"
kv nproc "$(nproc 2>/dev/null)"
kv mem_gb "$(awk '/MemTotal/ {printf "%.0f", $2/1048576}' /proc/meminfo 2>/dev/null)"
if command -v nvidia-smi >/dev/null 2>&1; then
  kv vendor nvidia
  kv gpu "$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -n1)"
  kv gpu_count "$(nvidia-smi -L 2>/dev/null | wc -l)"
  kv driver "$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -n1)"
elif command -v amd-smi >/dev/null 2>&1 || command -v rocminfo >/dev/null 2>&1 || [ -e /dev/kfd ]; then
  kv vendor amd
else
  kv vendor none
fi
nv=""; for c in /usr/local/cuda/bin/nvcc /usr/local/cuda-*/bin/nvcc; do [ -x "$c" ] && nv="$("$c" --version 2>/dev/null | sed -n 's/.*release \([0-9.]*\).*/\1/p' | head -n1)" && break; done
kv nvcc "${nv:-missing}"
if command -v dcgmi >/dev/null 2>&1; then kv dcgmi present; else kv dcgmi missing; fi
if command -v numactl >/dev/null 2>&1; then
  out="$(numactl --cpunodebind=0 --membind=0 true 2>&1)"; rc=$?
  kv numactl_bind "rc=${rc} $(printf '%s' "$out" | head -n1)"
else
  kv numactl_bind "not installed"
fi
if command -v iperf3 >/dev/null 2>&1; then kv iperf3 "$(iperf3 --version 2>&1 | head -n1)"; else kv iperf3 "not installed"; fi
mkdir -p /opt/benchmarks 2>/dev/null
kv disk_free_gb_opt "$(df -Pk /opt/benchmarks 2>/dev/null | awk 'NR==2 {printf "%.0f", $4/1048576}')"
kv disk_free_gb_home "$(df -Pk "$HOME" 2>/dev/null | awk 'NR==2 {printf "%.0f", $4/1048576}')"
kv hf_cache_gb "$(du -sk "${HF_HOME:-$HOME/.cache/huggingface}" 2>/dev/null | awk '{printf "%.1f", $1/1048576}')"
kv pip_cache_gb "$(du -sk "$HOME/.cache/pip" 2>/dev/null | awk '{printf "%.1f", $1/1048576}')"
if [ -f "$HOME/.cache/huggingface/token" ] || [ -n "${HF_TOKEN:-}" ]; then kv hf_token present; else kv hf_token missing; fi
if command -v curl >/dev/null 2>&1; then
  # 100 MB ranged reads, 25 s cap each. speed_download is bytes/s.
  hf="$(curl -sL -r 0-104857599 --max-time 25 -o /dev/null -w '%{speed_download}' https://huggingface.co/google-bert/bert-base-uncased/resolve/main/model.safetensors 2>/dev/null)"
  kv download_huggingface_bps "${hf:-0}"
  whl="$(curl -s --max-time 15 https://download.pytorch.org/whl/cu130/torch/ 2>/dev/null | grep -o 'torch-[0-9][^"#<]*-cp312-cp312-manylinux[^"#<]*x86_64\.whl' | tail -n1)"
  if [ -n "$whl" ]; then
    pt="$(curl -sL -r 0-104857599 --max-time 25 -o /dev/null -w '%{speed_download}' "https://download.pytorch.org/whl/cu130/${whl}" 2>/dev/null)"
  else
    pt=0
  fi
  kv download_pytorch_bps "${pt:-0}"
else
  kv download_huggingface_bps 0
  kv download_pytorch_bps 0
fi
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_probe(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line.startswith(PROBE_MARK + " ") or "=" not in line:
            continue
        key, _, value = line[len(PROBE_MARK) + 1 :].partition("=")
        values[key.strip()] = value.strip()
    return values


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def kernel_matches(expected: str, uname_r: str) -> bool:
    expected = (expected or "").strip()
    uname_r = (uname_r or "").strip()
    if not expected or not uname_r:
        return True
    return uname_r == expected or uname_r.startswith(expected + "-") or uname_r.startswith(expected + ".")


def workbook_values(workbook: Path, workloads: list[str], name: str) -> dict[str, str]:
    """Smoke value of one parameter for each requested workload (empty when absent)."""
    try:
        from openpyxl import load_workbook
    except ImportError:
        return {}
    wanted = {str(w) for w in workloads}
    found: dict[str, str] = {}
    try:
        book = load_workbook(workbook, read_only=True, data_only=True)
        rows = book["Parameters_SmokeBaselineExtend"].iter_rows(values_only=True)
        next(rows, None)
        for row in rows:
            if not row or row[0] is None or len(row) < 4:
                continue
            raw = str(row[0]).strip()
            number = str(int(float(raw))) if re.fullmatch(r"\d+(\.0+)?", raw) else raw
            if number in wanted and str(row[2]).strip() == name and row[3] not in (None, ""):
                found[number] = str(row[3]).strip()
    except Exception:  # a workbook problem must not stop generation
        return found
    return found


def platform_key(values: dict[str, str]) -> str:
    vendor = values.get("vendor", "")
    os_id = values.get("os_version_id", "")
    key = f"{vendor}-{os_id}"
    return key if key in REFERENCE_SECONDS else ""


def estimate_minutes(values: dict[str, str], workloads: list[str], ssh_call_s: float) -> dict[str, float]:
    """Rough batch time: reference times, download-heavy workloads scaled by measured speed."""
    key = platform_key(values)
    table = REFERENCE_SECONDS.get(key) or REFERENCE_SECONDS["nvidia-26.04"]
    speeds = [
        _float(values.get("download_huggingface_bps")) / 1e6,
        _float(values.get("download_pytorch_bps")) / 1e6,
    ]
    measured = [s for s in speeds if s > 0]
    download_mb_s = min(measured) if measured else 0.0
    download_factor = REFERENCE_DOWNLOAD_MB_S / download_mb_s if download_mb_s else 2.0
    download_factor = max(0.5, min(download_factor, 6.0))
    ssh_factor = 1.0 if ssh_call_s <= 0 else max(1.0, min(0.7 + 0.3 * ssh_call_s / REFERENCE_SSH_CALL_S, 2.5))
    reference = 0.0
    estimate = 0.0
    for workload in workloads:
        suffix = f"{int(workload) % 100:02d}" if str(workload).isdigit() else ""
        base = float(table.get(suffix, 150))
        reference += base
        estimate += base * (download_factor if suffix in DOWNLOAD_HEAVY else ssh_factor)
    return {
        "reference_minutes": round(reference / 60.0, 1),
        "estimated_minutes": round(estimate / 60.0, 1),
        "download_factor": round(download_factor, 2),
        "ssh_factor": round(ssh_factor, 2),
        "download_mb_s": round(download_mb_s, 1),
        "reference_platform": key or "nvidia-26.04 (fallback)",
    }


def evaluate(values: dict[str, str], workloads: list[str], kernels: dict[str, str], ssh_call_s: float) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    notes: list[str] = []
    uname_r = values.get("kernel", "")
    mismatched = sorted(w for w, k in kernels.items() if not kernel_matches(k, uname_r))
    if mismatched:
        wanted = sorted({kernels[w] for w in mismatched})
        warnings.append(
            f"kernel {uname_r} does not match workbook kernel_version {', '.join(wanted)} for workload(s) "
            f"{', '.join(mismatched)}. A container cannot change its host kernel; system-config records "
            "kernel_release_mismatch_count=1 and continues."
        )
    vendor = values.get("vendor", "")
    if vendor == "nvidia" and values.get("nvcc", "missing") == "missing":
        notes.append("No CUDA toolkit on the VM. The host bootstrap installs it once before workload 1 (15-30 minutes on a cold host).")
    if vendor == "nvidia" and values.get("dcgmi") == "missing":
        notes.append("DCGM is not installed. The host bootstrap installs it once before workload 1.")
    if vendor == "none":
        warnings.append("No nvidia-smi, amd-smi, rocminfo or /dev/kfd on the VM. GPU workloads will fail.")
    bind = values.get("numactl_bind", "")
    if bind.startswith("rc=") and not bind.startswith("rc=0"):
        warnings.append(f"numactl cannot bind on this host ({bind}). GUPS and STREAM run unbound.")
    for key, label in (("disk_free_gb_opt", "/opt/benchmarks"), ("disk_free_gb_home", "$HOME (pip and Hugging Face caches)")):
        free = _float(values.get(key), -1.0)
        if 0 <= free < LOW_DISK_GB:
            warnings.append(f"Only {free:.0f} GB free on {label}; the model workloads need about {LOW_DISK_GB:.0f} GB.")
    if values.get("hf_token") == "missing" and any(str(w)[-2:] in {"27", "28", "29", "30", "31", "32"} for w in workloads):
        warnings.append("No Hugging Face token on the VM (~/.cache/huggingface/token or HF_TOKEN). mistralai/Mistral-7B-v0.3 may be gated; if its download fails, set HF_TOKEN.")
    for key, label in (("download_huggingface_bps", "huggingface.co"), ("download_pytorch_bps", "download.pytorch.org")):
        speed = _float(values.get(key)) / 1e6
        if speed <= 0:
            warnings.append(f"Download speed from {label} could not be measured.")
        elif speed < SLOW_DOWNLOAD_MB_S:
            warnings.append(f"Download from {label} is {speed:.1f} MB/s (below {SLOW_DOWNLOAD_MB_S:.0f} MB/s). Model and wheel installs will be slow.")
    if ssh_call_s > SLOW_SSH_CALL_S:
        warnings.append(f"One SSH call takes {ssh_call_s:.1f} s (above {SLOW_SSH_CALL_S:.0f} s). Every workload makes many calls.")
    return warnings, notes


def measure_ssh_call(run: Callable[[str], object], attempts: int = 3) -> float:
    timings = []
    for _ in range(attempts):
        started = time.monotonic()
        try:
            result = run("true")
        except Exception:
            continue
        if getattr(result, "returncode", 1) == 0:
            timings.append(time.monotonic() - started)
    return round(sorted(timings)[len(timings) // 2], 2) if timings else 0.0


def run_preflight(
    ssh_run: Callable[..., object],
    ssh: str,
    workloads: list[str],
    template_root: Path,
    project_root: Path,
) -> dict[str, object]:
    """Probe the VM, print a report, and record it. Never raises."""
    report: dict[str, object] = {"started_at": _utc_now(), "status": "ok", "warnings": [], "notes": []}
    try:
        print("[START] remote host preflight (warnings only; generation always continues)", flush=True)
        ssh_call_s = measure_ssh_call(lambda script: ssh_run(ssh, script, timeout=60))
        result = ssh_run(ssh, PROBE_SCRIPT, timeout=240)
        values = parse_probe(getattr(result, "stdout", "") or "")
        if not values:
            report["status"] = "probe_failed"
            report["warnings"] = ["The remote preflight probe returned nothing; continuing without it."]
        kernels = workbook_values(template_root / "BenchmarkSpecDefinitions.xlsx", workloads, "kernel_version")
        warnings, notes = evaluate(values, workloads, kernels, ssh_call_s)
        estimate = estimate_minutes(values, workloads, ssh_call_s)
        if estimate["reference_minutes"] and estimate["estimated_minutes"] > SLOW_ESTIMATE_RATIO * estimate["reference_minutes"]:
            warnings.append(
                f"This host looks slow: estimated {estimate['estimated_minutes']:.0f} min against "
                f"{estimate['reference_minutes']:.0f} min on the reference {estimate['reference_platform']} host. "
                "Generation continues; consider a faster VM for the next batch."
            )
        report.update(
            values=values,
            ssh_call_seconds=ssh_call_s,
            workbook_kernel_version=kernels,
            estimate=estimate,
            warnings=list(report["warnings"]) + warnings,  # type: ignore[arg-type]
            notes=notes,
        )
        print(
            "[INFO] remote host: "
            f"Ubuntu {values.get('os_version_id', '?')}, kernel {values.get('kernel', '?')}, "
            f"{values.get('vendor', '?')} {values.get('gpu', '')} x{values.get('gpu_count', '?')}, "
            f"nvcc {values.get('nvcc', '?')}, disk free {values.get('disk_free_gb_opt', '?')} GB",
            flush=True,
        )
        print(
            f"[INFO] download {estimate['download_mb_s']} MB/s (slowest of huggingface.co, download.pytorch.org); "
            f"SSH call {ssh_call_s} s",
            flush=True,
        )
        print(
            f"[INFO] estimated batch time {estimate['estimated_minutes']} min "
            f"(reference {estimate['reference_minutes']} min on {estimate['reference_platform']}). Rough.",
            flush=True,
        )
        for note in notes:
            print(f"[INFO] {note}", flush=True)
        for warning in report["warnings"]:  # type: ignore[union-attr]
            print(f"[WARN] {warning}", flush=True)
    except Exception as exc:  # the preflight must never stop generation
        report["status"] = "error"
        report["warnings"] = list(report.get("warnings") or []) + [f"remote preflight raised {exc!r}; continuing"]  # type: ignore[arg-type]
        print(f"[WARN] remote preflight raised {exc!r}; continuing", flush=True)
    report["finished_at"] = _utc_now()
    _record(project_root, "remote_host_preflight", report)
    print("[DONE] remote host preflight", flush=True)
    return report


def _record(project_root: Path, key: str, payload: dict[str, object]) -> None:
    try:
        path = project_root / "batch_generation_manifest.json"
        batch: dict = {}
        if path.is_file():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                batch = loaded
        batch[key] = payload
        path.write_text(json.dumps(batch, indent=2) + "\n", encoding="utf-8", newline="\n")
    except Exception as exc:
        print(f"[WARN] could not record {key} in the batch manifest: {exc!r}", flush=True)


def main() -> int:
    import argparse

    from create_one_workload import _ssh_target, ssh_run

    parser = argparse.ArgumentParser(description="Probe the validation VM (warnings only)")
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--workload", action="append", default=[])
    parser.add_argument("--template-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--project-root", default="")
    args = parser.parse_args()
    template_root = Path(args.template_root).resolve()
    project_root = Path(args.project_root).resolve() if args.project_root else template_root.parent
    ssh = _ssh_target(Path(args.prompt_file).resolve())
    if not ssh:
        print("[INFO] No SSH target in the prompt; nothing to probe.")
        return 0
    run_preflight(ssh_run, ssh, args.workload, template_root, project_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
