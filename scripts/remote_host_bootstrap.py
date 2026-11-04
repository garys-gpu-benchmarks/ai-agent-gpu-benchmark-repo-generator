#!/usr/bin/env python3
# File: scripts/remote_host_bootstrap.py
# Description: One-time host bootstrap before workload 1, timed on its own
#              (TEMPLATE_00_119). Copies scripts/remote/ and two scripts/lib/
#              helpers to the VM, runs host_bootstrap.sh in the foreground (CUDA
#              toolkit and DCGM on NVIDIA), and leaves a Hugging Face prefetch of
#              this batch's models running in the background. Warnings only:
#              nothing here stops generation.
from __future__ import annotations

import json
import shlex
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

STATE_DIR = "/var/lib/gpu-benchmark-host"
REMOTE_DIR = f"{STATE_DIR}/bootstrap"
COPY_OK = "BOOTSTRAP_COPY_OK"
FILES = (
    "remote/host_bootstrap.sh",
    "remote/prefetch_runner.sh",
    "remote/host_prefetch.py",
    "lib/nvidia_cuda_toolkit.sh",
    "lib/keep_running_kernel.sh",
)

SDXL_PATTERNS = ";".join(
    (
        "model_index.json",
        "scheduler/*",
        "tokenizer/*",
        "tokenizer_2/*",
        "text_encoder/config.json",
        "text_encoder/model.fp16.safetensors",
        "text_encoder_2/config.json",
        "text_encoder_2/model.fp16.safetensors",
        "unet/config.json",
        "unet/diffusion_pytorch_model.fp16.safetensors",
        "vae/config.json",
        "vae/diffusion_pytorch_model.fp16.safetensors",
    )
)
TRANSFORMERS_PATTERNS = "*.json;*.txt;*.safetensors"
# Workload suffix -> Hugging Face repos it reads, with the same repo ids and
# file subsets the workloads request, so their own download is a cache hit.
# Listed in the order the batch first needs them.
MODELS_BY_SUFFIX: dict[str, tuple[str, ...]] = {
    "23": (f"bert-base-uncased|{TRANSFORMERS_PATTERNS}",),
    "24": (f"stabilityai/stable-diffusion-xl-base-1.0|{SDXL_PATTERNS}",),
    "25": (f"distilbert-base-uncased|{TRANSFORMERS_PATTERNS}",),
    "27": ("mistralai/Mistral-7B-v0.3",),
    "28": ("mistralai/Mistral-7B-v0.3",),
    "29": ("mistralai/Mistral-7B-v0.3",),
    "30": ("mistralai/Mistral-7B-v0.3",),
    "31": ("mistralai/Mistral-7B-v0.3",),
    "32": ("mistralai/Mistral-7B-v0.3", "BAAI/bge-small-en-v1.5", "BAAI/bge-reranker-base"),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def models_for(workloads: list[str]) -> list[str]:
    specs: list[str] = []
    for workload in sorted(workloads, key=lambda w: int(w) if str(w).isdigit() else 0):
        suffix = f"{int(workload) % 100:02d}" if str(workload).isdigit() else ""
        for spec in MODELS_BY_SUFFIX.get(suffix, ()):
            if spec not in specs:
                specs.append(spec)
    return specs


def guess_vendor(workloads: list[str], preflight: dict | None) -> str:
    values = (preflight or {}).get("values") or {}
    vendor = str(values.get("vendor") or "")
    if vendor in {"nvidia", "amd"}:
        return vendor
    hundreds = {int(w) // 100 for w in workloads if str(w).isdigit()}
    if hundreds and hundreds <= {2, 4}:
        return "nvidia"
    if hundreds and hundreds <= {1, 3}:
        return "amd"
    return ""


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


def copy_bootstrap(run_host_bash: Callable[..., object], ssh_command: str, scripts_dir: str) -> bool:
    remote = (
        f"mkdir -p {REMOTE_DIR} && tar --no-same-owner -xf - -C {REMOTE_DIR} && "
        f"find {REMOTE_DIR} -type f \\( -name '*.sh' -o -name '*.py' \\) -exec sed -i 's/\\r$//' {{}} + && "
        f"chmod 755 {REMOTE_DIR}/remote/*.sh && echo {COPY_OK}"
    )
    files = " ".join(shlex.quote(item) for item in FILES)
    command = f"tar -cf - -C {shlex.quote(scripts_dir)} {files} | {ssh_command} {shlex.quote(remote)}"
    result = run_host_bash(command, timeout=300)
    return getattr(result, "returncode", 1) == 0 and COPY_OK in (getattr(result, "stdout", "") or "")


def run_bootstrap(
    ssh_run: Callable[..., object],
    run_host_bash: Callable[..., object],
    ssh: str,
    ssh_command: str,
    scripts_dir: str,
    workloads: list[str],
    project_root: Path,
    preflight: dict | None = None,
) -> dict[str, object]:
    """Run the host bootstrap. Never raises; always returns a report."""
    started_at = _utc_now()
    started = time.monotonic()
    report: dict[str, object] = {"started_at": started_at, "status": "ok", "warnings": []}
    warnings: list[str] = []
    try:
        vendor = guess_vendor(workloads, preflight)
        models = models_for(workloads)
        report.update(vendor=vendor, prefetch_models=[spec.partition("|")[0] for spec in models])
        print(
            f"[START] host bootstrap (vendor={vendor or 'unknown'}; "
            f"{len(models)} model repo(s) to prefetch in the background)",
            flush=True,
        )
        if not copy_bootstrap(run_host_bash, ssh_command, scripts_dir):
            warnings.append("could not copy the bootstrap scripts to the VM; each setup.sh installs what it needs")
            report["status"] = "copy_failed"
        else:
            command = (
                f"bash {REMOTE_DIR}/remote/host_bootstrap.sh --vendor {shlex.quote(vendor)} "
                f"--models {shlex.quote(' '.join(models))}"
            )
            result = ssh_run(ssh, command, timeout=5400)
            text = getattr(result, "stdout", "") or ""
            values = {}
            for line in text.splitlines():
                if line.startswith("BOOTSTRAP_WARN "):
                    warnings.append(line[len("BOOTSTRAP_WARN ") :].strip())
                elif line.startswith("BOOTSTRAP_KV ") and "=" in line:
                    key, _, value = line[len("BOOTSTRAP_KV ") :].partition("=")
                    values[key.strip()] = value.strip()
            report["values"] = values
            if "BOOTSTRAP_OK" not in text:
                report["status"] = "incomplete"
                tail = ((getattr(result, "stderr", "") or "") + text)[-600:]
                warnings.append(f"host bootstrap did not finish (rc={getattr(result, 'returncode', '?')}): {tail.strip()}")
    except Exception as exc:  # never stop generation
        report["status"] = "error"
        warnings.append(f"host bootstrap raised {exc!r}")
    seconds = int(time.monotonic() - started)
    report.update(finished_at=_utc_now(), seconds=seconds, warnings=warnings)
    for warning in warnings:
        print(f"[WARN] {warning}", flush=True)
    print(
        f"[DONE] host bootstrap in {seconds // 60}m {seconds % 60:02d}s "
        "(reported apart from the per-workload create times)",
        flush=True,
    )
    _record(project_root, "host_bootstrap", report)
    return report


def collect_prefetch_status(ssh_run: Callable[..., object], ssh: str, project_root: Path) -> dict[str, object]:
    """Read the background prefetch status at the end of the batch. Never raises."""
    report: dict[str, object] = {}
    try:
        result = ssh_run(ssh, f"cat {STATE_DIR}/prefetch_status.json 2>/dev/null || true", timeout=60)
        text = (getattr(result, "stdout", "") or "").strip()
        if text:
            report = json.loads(text)
    except Exception as exc:
        report = {"error": f"could not read prefetch status: {exc!r}"}
    if report:
        models = report.get("models") or {}
        if isinstance(models, dict):
            for repo, row in models.items():
                if isinstance(row, dict):
                    print(f"[INFO] prefetch {repo}: {row.get('status')} {row.get('seconds', '')}", flush=True)
        _record(project_root, "host_prefetch", report)
    return report
