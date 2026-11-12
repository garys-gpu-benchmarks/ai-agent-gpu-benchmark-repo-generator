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

# Per-workload create time (seconds, passing attempt) from the TEMPLATE_00_131 batches
# (2026-11-10, no retries): amd-24.04 Project475, nvidia-24.04 Project476,
# amd-26.04 Project477, nvidia-26.04 Project478. Updated by hand, never by a batch, so
# one slow VM cannot become the reference (TEMPLATE_00_134). The TEMPLATE_00_133 AMD
# x01 times (30 and 35 min: slow apt mirror and reboot) were left out on purpose.
REFERENCE_SECONDS: dict[str, dict[str, int]] = {
    "amd-24.04": {"01": 331, "02": 79, "03": 292, "04": 149, "05": 129, "06": 106, "07": 73, "08": 63, "09": 69, "10": 83, "11": 64, "12": 125, "13": 63, "14": 74, "15": 78, "16": 63, "17": 318, "18": 126, "19": 123, "20": 79, "21": 130, "22": 126, "23": 156, "24": 152, "25": 131, "26": 144, "27": 393, "28": 346, "29": 331, "30": 586, "31": 569, "32": 356},
    "nvidia-24.04": {"01": 94, "02": 87, "03": 81, "04": 101, "05": 134, "06": 121, "07": 76, "08": 78, "09": 76, "10": 71, "11": 101, "12": 124, "13": 82, "14": 135, "15": 92, "16": 95, "17": 91, "18": 100, "19": 130, "20": 78, "21": 144, "22": 124, "23": 138, "24": 169, "25": 151, "26": 146, "27": 302, "28": 257, "29": 248, "30": 419, "31": 375, "32": 154},
    "amd-26.04": {"01": 412, "02": 63, "03": 279, "04": 136, "05": 112, "06": 96, "07": 61, "08": 55, "09": 57, "10": 49, "11": 61, "12": 98, "13": 61, "14": 64, "15": 56, "16": 74, "17": 307, "18": 136, "19": 105, "20": 56, "21": 117, "22": 130, "23": 110, "24": 131, "25": 117, "26": 126, "27": 355, "28": 311, "29": 303, "30": 546, "31": 502, "32": 331},
    "nvidia-26.04": {"01": 116, "02": 102, "03": 101, "04": 108, "05": 193, "06": 120, "07": 83, "08": 96, "09": 116, "10": 101, "11": 94, "12": 155, "13": 100, "14": 135, "15": 94, "16": 103, "17": 84, "18": 100, "19": 148, "20": 79, "21": 162, "22": 152, "23": 166, "24": 200, "25": 155, "26": 155, "27": 379, "28": 308, "29": 294, "30": 636, "31": 637, "32": 184},
}
# Download speed (MB/s, slowest of huggingface.co and download.pytorch.org) that the
# same batches' preflight measured. The estimate scales against these, not an assumed 100.
REFERENCE_DOWNLOAD_MB_S_BY_PLATFORM: dict[str, float] = {
    "amd-24.04": 48.8, "nvidia-24.04": 71.2, "amd-26.04": 63.6, "nvidia-26.04": 59.0,
}
# Model workloads. Only a share of their time is download: the host bootstrap prefetches
# the models in the background. Fitted from TEMPLATE_00_131 vs 133, where the download
# speed fell 2-3x: NVIDIA x21-x32 did not change and AMD grew 17-20% (about 15%).
DOWNLOAD_HEAVY = {f"{n:02d}" for n in range(21, 33)}
DOWNLOAD_SHARE: dict[str, float] = {"amd": 0.15, "nvidia": 0.05}
# x01 is apt and the ROCm or CUDA install, not Hugging Face: it is not scaled by the probe.
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
# PCI vendor IDs of display (0x03) and processing-accelerator (0x12) devices. Works
# before ROCm or CUDA userspace exists and needs no lspci (TEMPLATE_00_134).
pci=""; for d in /sys/bus/pci/devices/*; do
  c="$(cat "$d/class" 2>/dev/null)"
  case "$c" in 0x03*|0x12*) pci="$pci $(cat "$d/vendor" 2>/dev/null)" ;; esac
done
kv pci_gpu_vendors "$(printf '%s\n' $pci | sort -u | tr '\n' ' ' | sed 's/ *$//')"
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
# 100 MB ranged read, 25 s cap. Prints "<http_code> <bytes> <bytes_per_s>". The
# speed counts only for a 2xx answer that moved at least 1 MiB; anything else
# (an error page, a redirect loop, no route) is 0 = not measured. TEMPLATE_00_131:
# the pytorch probe used to time a short 4xx error page and report ~3 KB/s.
probe_speed() {
  set -- $(curl -sL -r 0-104857599 --max-time 25 -o /dev/null -w '%{http_code} %{size_download} %{speed_download}' "$1" 2>/dev/null) 0 0 0
  case "$1" in 2??) ;; *) printf '%s %d 0' "$1" "${2%.*}"; return ;; esac
  awk -v c="$1" -v n="$2" -v s="$3" 'BEGIN { if (n + 0 >= 1048576) printf "%s %d %s", c, n, s; else printf "%s %d 0", c, n }'
}
if command -v curl >/dev/null 2>&1; then
  set -- $(probe_speed https://huggingface.co/google-bert/bert-base-uncased/resolve/main/model.safetensors)
  kv download_huggingface_http "$1"; kv download_huggingface_bytes "$2"; kv download_huggingface_bps "$3"
  # Take the wheel path from href, which is URL-encoded (%2B), not from the link
  # text, whose literal "+" the download host does not accept.
  idx="https://download.pytorch.org/whl/cu130/torch/"
  href="$(curl -s --max-time 15 "$idx" 2>/dev/null | grep -o 'href="[^"]*torch-[0-9][^"]*-cp312-cp312-manylinux[^"]*x86_64\.whl' | tail -n1)"
  href="${href#href=\"}"
  case "$href" in
    "") whl="" ;;
    http*) whl="$href" ;;
    /*) whl="https://download.pytorch.org${href}" ;;
    *) whl="${idx}${href}" ;;
  esac
  whl="$(printf '%s' "$whl" | sed 's/+/%2B/g')"
  kv download_pytorch_url "${whl:-none}"
  if [ -n "$whl" ]; then
    set -- $(probe_speed "$whl")
  else
    set -- none 0 0
  fi
  kv download_pytorch_http "$1"; kv download_pytorch_bytes "$2"; kv download_pytorch_bps "$3"
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


PCI_VENDORS = {"0x1002": "amd", "0x10de": "nvidia"}


def series_vendor(workloads: list[str]) -> str:
    """Vendor the workload numbers call for: 1xx/3xx AMD, 2xx/4xx NVIDIA ("" if mixed or other)."""
    found = set()
    for workload in workloads:
        text = str(workload).strip()
        if text[:1] in {"1", "3"} and len(text) == 3:
            found.add("amd")
        elif text[:1] in {"2", "4"} and len(text) == 3:
            found.add("nvidia")
        else:
            return ""
    return found.pop() if len(found) == 1 else ""


def resolve_vendor(values: dict[str, str], workloads: list[str]) -> tuple[str, str, list[str], list[str]]:
    """Return (vendor, source, warnings, notes) for the batch (TEMPLATE_00_134).

    The tool probe wins when it finds nvidia-smi, amd-smi, rocminfo or /dev/kfd. On a
    fresh AMD image none of those exist yet (workload x01 installs ROCm), so the probe
    says "none"; then the PCI vendor ID, and last the workload series, decide. Before,
    that case warned "GPU workloads will fail" and estimated against the NVIDIA table.
    """
    probe = values.get("vendor", "")
    expected = series_vendor(workloads)
    pci = {PCI_VENDORS[v] for v in values.get("pci_gpu_vendors", "").split() if v in PCI_VENDORS}
    warnings: list[str] = []
    notes: list[str] = []
    if probe in {"amd", "nvidia"}:
        vendor, source = probe, "tools"
    elif len(pci) == 1:
        vendor, source = next(iter(pci)), "pci"
    elif expected:
        vendor, source = expected, "workload series"
    else:
        vendor, source = "none", "none"
    if probe not in {"amd", "nvidia"} and not pci and "pci_gpu_vendors" in values:
        warnings.append("No GPU tools and no AMD or NVIDIA PCI device are visible on the VM. "
                        "Unless workload x01 setup finds the GPU, GPU workloads will fail.")
    if expected and vendor in {"amd", "nvidia"} and vendor != expected:
        span = f"{workloads[0]}-{workloads[-1]}" if len(workloads) > 1 else str(workloads[0])
        names = {"amd": "AMD", "nvidia": "NVIDIA"}
        warnings.append(f"The VM has an {names[vendor]} GPU ({source}), but workloads {span} are {names[expected]} workloads.")
    if probe not in {"amd", "nvidia"} and vendor == "amd":
        notes.append("ROCm is not installed yet; workload x01 setup installs it (5-35 minutes, mostly the apt mirror and one reboot).")
    if probe not in {"amd", "nvidia"} and vendor == "nvidia":
        warnings.append("nvidia-smi is missing. The NVIDIA driver must come from the host image; setup installs only the CUDA toolkit.")
    return vendor, source, warnings, notes


def platform_key(values: dict[str, str], workloads: list[str] | None = None) -> str:
    vendor = values.get("vendor_resolved") or values.get("vendor", "")
    if workloads is not None and not values.get("vendor_resolved"):
        vendor = resolve_vendor(values, workloads)[0]
    os_id = values.get("os_version_id", "")
    key = f"{vendor}-{os_id}"
    return key if key in REFERENCE_SECONDS else ""


def estimate_minutes(values: dict[str, str], workloads: list[str], ssh_call_s: float) -> dict[str, float]:
    """Rough batch time from measured per-workload reference times (TEMPLATE_00_134).

    Only the download share of x21-x32 is scaled by the measured download speed, against
    the speed measured on the reference host. x01 (apt and the ROCm or CUDA install) and
    every other workload are scaled only by the SSH round-trip time.
    """
    key = platform_key(values, workloads)
    table = REFERENCE_SECONDS.get(key) or REFERENCE_SECONDS["nvidia-26.04"]
    vendor = key.split("-", 1)[0] if key else "nvidia"
    reference_mb_s = REFERENCE_DOWNLOAD_MB_S_BY_PLATFORM.get(key or "nvidia-26.04", 59.0)
    speeds = [
        _float(values.get("download_huggingface_bps")) / 1e6,
        _float(values.get("download_pytorch_bps")) / 1e6,
    ]
    measured = [s for s in speeds if s > 0]
    download_mb_s = min(measured) if measured else 0.0
    download_factor = reference_mb_s / download_mb_s if download_mb_s else 1.0
    download_factor = max(0.5, min(download_factor, 4.0))
    share = DOWNLOAD_SHARE.get(vendor, 0.15)
    ssh_factor = 1.0 if ssh_call_s <= 0 else max(1.0, min(0.7 + 0.3 * ssh_call_s / REFERENCE_SSH_CALL_S, 2.5))
    reference = 0.0
    estimate = 0.0
    for workload in workloads:
        suffix = f"{int(workload) % 100:02d}" if str(workload).isdigit() else ""
        base = float(table.get(suffix, 150))
        reference += base
        if suffix in DOWNLOAD_HEAVY:
            estimate += base * ((1.0 - share) * ssh_factor + share * download_factor)
        else:
            estimate += base * ssh_factor
    return {
        "reference_minutes": round(reference / 60.0, 1),
        "estimated_minutes": round(estimate / 60.0, 1),
        "download_factor": round(download_factor, 2),
        "download_share": share,
        "reference_download_mb_s": reference_mb_s,
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
    vendor, source, vendor_warnings, vendor_notes = resolve_vendor(values, workloads)
    values["vendor_resolved"] = vendor
    values["vendor_source"] = source
    warnings.extend(vendor_warnings)
    notes.extend(vendor_notes)
    if vendor == "nvidia" and values.get("nvcc", "missing") == "missing":
        notes.append("No CUDA toolkit on the VM. The host bootstrap installs it once before workload 1 (15-30 minutes on a cold host).")
    if vendor == "nvidia" and values.get("dcgmi") == "missing":
        notes.append("DCGM is not installed. The host bootstrap installs it once before workload 1.")
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
            http = values.get(key.replace("_bps", "_http"), "")
            why = f" (HTTP {http}, {values.get(key.replace('_bps', '_bytes'), '0')} bytes)" if http else ""
            warnings.append(f"Download speed from {label} could not be measured{why}; the batch estimate ignores it.")
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
            f"{values.get('vendor_resolved') or values.get('vendor', '?')} (from {values.get('vendor_source', 'tools')}) "
            f"{values.get('gpu', '')} x{values.get('gpu_count', '?')}, "
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
            f"(reference {estimate['reference_minutes']} min on {estimate['reference_platform']} "
            f"at {estimate['reference_download_mb_s']} MB/s). Rough; a slow apt mirror is not predicted.",
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
