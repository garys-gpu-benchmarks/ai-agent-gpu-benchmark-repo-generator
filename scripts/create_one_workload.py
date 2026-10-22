#!/usr/bin/env python3
# File: scripts/create_one_workload.py
# Description: Official sequential create → remote-validate → record driver.
# Windows host uses Git Bash + OpenSSH. Reboot-safe resume. Cache-preserving retry.
from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from generated_repo_directory import find_generated_repo, generated_repo_directory_name
from host_exec import normalize_remote_root, normalize_ssh_command, run_host_bash, to_git_bash_path
from framework_registry import resolve_flags
from platform_policy import match_policy
from remove_template_copy import remove_template_copy
from text_io import ensure_gitkeep

TEMPLATE_COPY_SUFFIX = "_copy"
SSH_OK = "SSH_OK"
COPY_OK = "COPY_OK"
REMOTE_OK = "REMOTE_OK"
# Where each repository is installed, developed, and run on the validation VM.
# The operator's batch loop runs the same trees from this directory.
REMOTE_ROOT = "/opt/benchmarks"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create, remotely validate, and record workloads one at a time")
    parser.add_argument("--workload", action="append", default=[], help="Workload number; repeat or pass several")
    parser.add_argument("workloads", nargs="*", help="Additional workload numbers")
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--template-root", default=".")
    parser.add_argument("--project-root", default="")
    parser.add_argument(
        "--remote-root",
        default=REMOTE_ROOT,
        help="Directory on the validation VM that holds each <Workload Number>-<Repo Name> (default /opt/benchmarks)",
    )
    parser.add_argument("--skip-remote-refresh", action="store_true", default=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--validate-only", action="store_true", help="Skip create; retry remote validation only")
    parser.add_argument(
        "--reuse-remote-env",
        action="store_true",
        default=True,
        help="Preserve remote .venv/.cache when the remote repo already exists (default)",
    )
    parser.add_argument(
        "--fresh-remote-env",
        action="store_true",
        help="Wipe the remote repo including .venv/.cache before copy",
    )
    parser.add_argument(
        "--keep-template-copy",
        action="store_true",
        help="Keep the nested <template>_copy/ generation workspace after the workload passes "
        "(default: remove it once the workload passes)",
    )
    return parser.parse_args()


def _ssh_target(prompt_path: Path) -> str:
    text = prompt_path.read_text(encoding="utf-8")
    match = re.search(r"(ssh(?:\s+-i\s+\S+)?[^\n]*@\d{1,3}(?:\.\d{1,3}){3})", text, flags=re.I)
    return normalize_ssh_command(match.group(1).strip()) if match else ""


def _duration(started: str, finished: str) -> str:
    start_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(finished.replace("Z", "+00:00"))
    total = max(0, int((end_dt - start_dt).total_seconds()))
    mins, secs = divmod(total, 60)
    return f"{mins}m {secs:02d}s"


def _configure_stdio() -> None:
    """Windows cp1252 consoles crash on remote logs that contain arrows."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue


def _emit(text: str) -> None:
    if not text:
        return
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    safe = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
    print(safe, flush=True)


def record(
    project_root: Path,
    workload: str,
    repo_name: str,
    status: str,
    started: str,
    finished: str,
    note: str,
    return_code: int | None = None,
) -> None:
    path = project_root / "batch_generation_manifest.json"
    batch: dict = {"schema_version": "1.0.0", "repositories": []}
    if path.is_file():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            batch = loaded
    batch.setdefault("schema_version", "1.0.0")
    previous = [row for row in batch.get("repositories", []) if str(row.get("workload")) == workload]
    batch["repositories"] = [row for row in batch.get("repositories", []) if str(row.get("workload")) != workload]
    code = 0 if status == "passed" else 1
    if return_code is not None:
        code = int(return_code)
    # Keep every attempt. The top-level fields describe the latest attempt only.
    attempts: list[dict[str, object]] = []
    for row in previous:
        if isinstance(row.get("attempts"), list):
            attempts.extend(row["attempts"])
        elif row.get("create_start_time"):
            attempts.append(
                {
                    "status": row.get("status"),
                    "return_code": row.get("return_code"),
                    "start": row.get("create_start_time"),
                    "end": row.get("create_end_time"),
                    "total_time": row.get("create_total_time"),
                    "reason": row.get("reason", ""),
                }
            )
    attempts.append(
        {
            "status": status,
            "return_code": code,
            "start": started,
            "end": finished,
            "total_time": _duration(started, finished),
            "reason": note[:300] if note else "",
        }
    )
    entry: dict[str, object] = {
        "workload": workload,
        "status": status,
        "return_code": code,
        "create_start_time": started,
        "create_end_time": finished,
        "create_total_time": _duration(started, finished),
        "attempt_count": len(attempts),
        "attempts": attempts,
    }
    if repo_name and repo_name != "unknown":
        entry["repo_name"] = repo_name
        entry["repo_path"] = (
            generated_repo_directory_name(workload, repo_name)
            if not str(repo_name).startswith(str(workload))
            else repo_name
        )
    if note:
        entry["reason"] = note[:300]
    batch.setdefault("repositories", []).append(entry)
    path.write_text(json.dumps(batch, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"[RECORD] {workload} {status} {_duration(started, finished)} (attempt {len(attempts)})", flush=True)


def ssh_run(ssh: str, script: str, *, timeout: int = 7200) -> subprocess.CompletedProcess[str]:
    quoted = shlex.quote(script)
    return run_host_bash(f"{normalize_ssh_command(ssh)} {quoted}", timeout=timeout)


def wait_for_ssh(ssh: str, *, timeout: int = 900) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            result = ssh_run(ssh, f"echo {SSH_OK}", timeout=30)
        except (subprocess.TimeoutExpired, OSError):
            result = None
        if result is not None and result.returncode == 0 and SSH_OK in (result.stdout or ""):
            print("[INFO] SSH reachable after wait", flush=True)
            return True
        print("[INFO] waiting for SSH after reboot or drop...", flush=True)
        time.sleep(15)
    return False


def remote_exists(ssh: str, name: str) -> bool:
    result = ssh_run(ssh, f"test -d {REMOTE_ROOT}/{shlex.quote(name)} && echo EXISTS || true", timeout=60)
    return result.returncode == 0 and "EXISTS" in (result.stdout or "")


def remote_setup_running(ssh: str, name: str) -> bool:
    result = ssh_run(
        ssh,
        f"pgrep -af 'setup.sh' | grep -F '{REMOTE_ROOT}/{name}' | grep -v grep || true",
        timeout=60,
    )
    return bool((result.stdout or "").strip())


def _copy_excludes(repo_dir: Path, *, prefix: str) -> str:
    """Keep the nested template copy in the VM tree.

    Remote ``self_check_generated_repo.sh`` requires that copy until
    ``template_copy_removed_at`` is recorded. Excluding it fails validation
    after a successful smoke run. ``repo_dir`` and ``prefix`` stay in the
    signature so callers can pass the archive root they are packing.
    """
    del repo_dir, prefix
    return ""


def remote_copy(ssh: str, repo_dir: Path, *, reuse: bool) -> int:
    name = repo_dir.name
    gitkeep = (
        f"mkdir -p {REMOTE_ROOT}/{name}/results/raw {REMOTE_ROOT}/{name}/results/parsed {REMOTE_ROOT}/{name}/tests/fixtures && "
        f"touch {REMOTE_ROOT}/{name}/results/raw/.gitkeep {REMOTE_ROOT}/{name}/results/parsed/.gitkeep "
        f"{REMOTE_ROOT}/{name}/tests/fixtures/.gitkeep"
    )
    if reuse:
        remote = (
            f"mkdir -p {REMOTE_ROOT}/{name} && "
            # Drop a stale nested template copy so the VM mirrors the local tree
            # (tar extraction alone never deletes a folder removed locally).
            f"find {REMOTE_ROOT}/{name} -mindepth 1 -maxdepth 1 -type d -name '*_copy' -exec rm -rf {{}} + && "
            f"tar --no-same-owner "
            f"--exclude=.venv --exclude=.cache --exclude='*.pyc' "
            f"-xf - -C {REMOTE_ROOT}/{name} && "
            f"find {REMOTE_ROOT}/{name} -type d -exec chmod 755 {{}} + && {gitkeep} && echo {COPY_OK}"
        )
        excludes = _copy_excludes(repo_dir, prefix="./")
        command = (
            f"tar -cf - --exclude=.venv --exclude=.cache --exclude=__pycache__{excludes} . | "
            f"{normalize_ssh_command(ssh)} {shlex.quote(remote)}"
        )
        cwd = repo_dir
    else:
        remote = (
            f"rm -rf {REMOTE_ROOT}/{name} && mkdir -p {REMOTE_ROOT} && tar --no-same-owner -xf - -C {REMOTE_ROOT} && "
            f"find {REMOTE_ROOT}/{name} -type d -exec chmod 755 {{}} + && {gitkeep} && echo {COPY_OK}"
        )
        excludes = _copy_excludes(repo_dir, prefix=f"{name}/")
        command = (
            f"tar -cf - --exclude=__pycache__{excludes} {shlex.quote(name)} | "
            f"{normalize_ssh_command(ssh)} {shlex.quote(remote)}"
        )
        cwd = repo_dir.parent
    print(f"[INFO] remote copy reuse={reuse} {name}", flush=True)
    result = run_host_bash(command, cwd=cwd, timeout=1800)
    if result.returncode != 0 or COPY_OK not in (result.stdout or ""):
        print("[FAIL] remote copy failed", flush=True)
        _emit(result.stdout or "")
        _emit(result.stderr or "")
        return result.returncode or 1
    return install_remote_suite_tools(ssh)


# Installed beside the workload trees, not inside them. Bundles already ship both.
REMOTE_SUITE_SCRIPTS = ("show_metrics.sh", "run_benchmark_suite.sh")


def install_remote_suite_script(ssh: str, name: str) -> int:
    """Install one templates/suite-tools/scripts/<name> at /opt/benchmarks/<name>."""
    src = Path(__file__).resolve().parents[1] / "templates" / "suite-tools" / "scripts" / name
    dest = f"{REMOTE_ROOT}/{name}"
    if not src.is_file():
        print(f"[FAIL] {src} is missing; cannot install {dest}", flush=True)
        return 1
    remote = f"mkdir -p {REMOTE_ROOT} && cat > {dest} && chmod 755 {dest} && echo {COPY_OK}"
    # Strip CR in Git Bash, before SSH, so the remote command needs no quotes.
    command = (
        f"tr -d '\\r' < {shlex.quote(to_git_bash_path(str(src)))} | "
        f"{normalize_ssh_command(ssh)} {shlex.quote(remote)}"
    )
    print(f"[INFO] install {dest}", flush=True)
    result = run_host_bash(command, timeout=120)
    if result.returncode != 0 or COPY_OK not in (result.stdout or ""):
        print(f"[FAIL] could not install {dest}", flush=True)
        _emit(result.stdout or "")
        _emit(result.stderr or "")
        return result.returncode or 1
    return 0


def install_remote_suite_tools(ssh: str) -> int:
    """Install show_metrics.sh and run_benchmark_suite.sh at /opt/benchmarks.

    Workload trees live in /opt/benchmarks/<repo>. These two stay beside them,
    where an operator runs `bash show_metrics.sh 101` or `bash run_benchmark_suite.sh`.
    """
    for name in REMOTE_SUITE_SCRIPTS:
        rc = install_remote_suite_script(ssh, name)
        if rc != 0:
            return rc
    return 0


def _connection_dropped(result: subprocess.CompletedProcess[str] | None) -> bool:
    if result is None:
        return True
    text = f"{result.stdout or ''}{result.stderr or ''}".lower()
    if result.returncode in {255, 1} and any(
        token in text for token in ("broken pipe", "connection reset", "closed by remote", "kex_exchange", "reboot")
    ):
        return True
    if result.returncode == 255:
        return True
    return False


def _remote_script(name: str, *, resume: bool, stamp: str) -> str:
    setup = "bash setup.sh --assume-yes"
    if resume:
        setup = "bash setup.sh --assume-yes --resume-auto || bash setup.sh --assume-yes"
    quoted_stamp = shlex.quote(stamp)
    if resume:
        # The reboot resume service may already be inside setup.sh. Wait for that
        # process instead of exiting, then run setup --resume-auto (a no-op when
        # SETUP complete) and continue into smoke.
        guard = """
if pgrep -af 'setup.sh' | grep -F "$REPO" | grep -v grep >/dev/null; then
  echo "[INFO] setup.sh already running after reboot; waiting for it to finish"
  deadline=$((SECONDS + 3600))
  while pgrep -af 'setup.sh' | grep -F "$REPO" | grep -v grep >/dev/null; do
    if [ "$SECONDS" -ge "$deadline" ]; then
      echo "[FAIL] setup.sh still running after wait"
      exit 1
    fi
    sleep 10
  done
fi
"""
    else:
        guard = """
if pgrep -af 'setup.sh' | grep -F "$REPO" | grep -v grep >/dev/null; then
  echo "[FAIL] setup.sh already running; not starting a second copy"
  exit 1
fi
"""
    return f"""
set -euo pipefail
REPO={REMOTE_ROOT}/{name}
cd "$REPO"
{guard}
find "$REPO" -type d -exec chmod 755 {{}} +
find "$REPO" -type f -not -path '*/.venv/*' -not -path '*/.cache/*' -not -path '*/third_party/*' -not -path '*/bin/*' -not -path '*/build/*' -exec chmod 644 {{}} +
export PYTHONDONTWRITEBYTECODE=1
# Rewrite only files that actually contain a CR, so unchanged files keep their mtime.
{{ find "$REPO" -type f \\( -name '*.sh' -o -name '*.py' -o -name '*.md' -o -name '*.yaml' -o -name '*.json' -o -name '*.txt' -o -name '*.toml' \\) ! -path '*/third_party/*' ! -path '*/.venv/*' ! -path '*/.cache/*' -print0 | xargs -0 grep -lZ $'\\r' || true; }} | xargs -0 -r sed -i 's/\\r$//'
find "$REPO" -type f -name '*.sh' ! -path '*/.venv/*' -exec chmod +x {{}} +
chmod +x "$REPO"/*.sh "$REPO"/scripts/*.sh "$REPO"/scripts/lib/*.sh 2>/dev/null || true
mkdir -p "$REPO/results/raw" "$REPO/results/parsed" "$REPO/tests/fixtures"
touch "$REPO/results/raw/.gitkeep" "$REPO/results/parsed/.gitkeep" "$REPO/tests/fixtures/.gitkeep"
{setup}
printf '%s\\n' {quoted_stamp} > "$REPO/.env_reuse_stamp"
if ! command -v rg >/dev/null 2>&1; then
  DEBIAN_FRONTEND=noninteractive apt-get update -y
  DEBIAN_FRONTEND=noninteractive apt-get install -y ripgrep
fi
bash run_benchmark.sh --profile smoke --validate
bash scripts/self_check_generated_repo.sh
bash scripts/check_github_publish_ready.sh
echo {REMOTE_OK}
"""


def _check_platform_policy(ssh: str, repo_dir: Path) -> int:
    spec = repo_dir / "benchmark_specification.json"
    if not spec.is_file():
        return 0
    fields = {str(item.get("field_name", "")): str(item.get("value", "") or "") for item in json.loads(spec.read_text(encoding="utf-8"))}
    os_probe = ssh_run(ssh, ". /etc/os-release; echo \"$VERSION_ID\"", timeout=60)
    os_release = (os_probe.stdout or "").strip().splitlines()[-1] if os_probe.returncode == 0 else ""
    result = match_policy(fields, os_release=os_release)
    for warning in result.get("warnings") or []:
        print(f"[WARN] {warning}", flush=True)
    if result.get("notes"):
        print(f"[INFO] {result['notes']}", flush=True)
    if not result.get("ok"):
        for error in result.get("errors") or []:
            print(f"[FAIL] {error}", flush=True)
        return 1
    print(
        f"[PASS] platform policy {result.get('vendor')} {result.get('os')} "
        f"driver={result.get('driver')} reboots={result.get('reboots')}",
        flush=True,
    )
    return 0


def env_reuse_stamp(repo_dir: Path) -> str:
    """Framework flags plus the CUDA wheel index. A change means the preserved venv is stale."""
    spec = repo_dir / "benchmark_specification.json"
    fields = {
        str(item.get("field_name", "")): str(item.get("value", "") or "")
        for item in json.loads(spec.read_text(encoding="utf-8"))
    }
    vendor_text = fields.get("GPU Vendor", "").lower()
    if "nvidia" in vendor_text:
        vendor = "nvidia"
    elif "amd" in vendor_text:
        vendor = "amd"
    else:
        vendor = "cpu"
    flags = resolve_flags(fields.get("Framework", ""), vendor=vendor)
    active = ",".join(f"{key}={flags[key]}" for key in sorted(flags) if flags[key])
    if vendor == "nvidia":
        # One PyTorch build (torch 2.13.0+cu130) on Ubuntu 24.04 and 26.04.
        wheel = "cu130"
    else:
        wheel = "rocm"
    return f"flags={active};wheel={wheel}"


def reuse_env_allowed(local_stamp: str, remote_stamp: str, setup_log: str) -> bool:
    """Keep a remote venv only when its install inputs match and setup imported the registry."""
    if not remote_stamp.strip() or remote_stamp.strip() != local_stamp.strip():
        return False
    lowered = setup_log.lower()
    registry_failed = "framework_registry" in lowered and (
        "no module named" in lowered or "modulenotfounderror" in lowered
    )
    yaml_failed = "no module named" in lowered and "yaml" in lowered
    return not registry_failed and not yaml_failed


def _drop_stale_remote_env(ssh: str, name: str) -> None:
    script = (
        f"cd {REMOTE_ROOT}/{name} && rm -rf .venv .setup_state && "
        f"rm -f results/install_status.txt && echo ENV_DROPPED"
    )
    result = ssh_run(ssh, script, timeout=120)
    if result.returncode != 0 or "ENV_DROPPED" not in (result.stdout or ""):
        print("[WARN] could not remove the stale remote virtualenv", flush=True)


def _sync_remote_env_stamp(ssh: str, repo_dir: Path) -> None:
    """Rewrite the reuse stamp. A timeout here is bookkeeping, not a failed benchmark."""
    stamp = env_reuse_stamp(repo_dir)
    name = repo_dir.name
    script = f"printf '%s\\n' {shlex.quote(stamp)} > {REMOTE_ROOT}/{name}/.env_reuse_stamp"
    delays = (0, 5, 15)
    for attempt, delay in enumerate(delays, start=1):
        if delay:
            time.sleep(delay)
        try:
            result = ssh_run(ssh, script, timeout=60)
        except (subprocess.TimeoutExpired, OSError) as exc:
            print(f"[WARN] .env_reuse_stamp write attempt {attempt} failed: {exc}", flush=True)
            continue
        if result.returncode == 0:
            return
        print(
            f"[WARN] .env_reuse_stamp write attempt {attempt} exited {result.returncode}",
            flush=True,
        )
    print("[WARN] could not write .env_reuse_stamp after retries", flush=True)


def remote_validate(ssh: str, repo_dir: Path, *, reuse: bool) -> int:
    if not ssh:
        print("[INFO] No SSH target in prompt; skipping remote validation", flush=True)
        return 0
    name = repo_dir.name
    if remote_setup_running(ssh, name):
        print("[FAIL] setup.sh already running on the remote VM; not starting a second copy", flush=True)
        return 1
    if _check_platform_policy(ssh, repo_dir) != 0:
        return 1
    use_reuse = reuse and remote_exists(ssh, name)
    if use_reuse:
        probe = ssh_run(
            ssh,
            f"cat {REMOTE_ROOT}/{name}/.env_reuse_stamp 2>/dev/null || true; echo '---LOG---'; "
            f"cat {REMOTE_ROOT}/{name}/results/install_status.txt 2>/dev/null || true",
            timeout=60,
        )
        probed = probe.stdout or ""
        remote_stamp, _, setup_log = probed.partition("---LOG---")
        local_stamp = env_reuse_stamp(repo_dir)
        if not reuse_env_allowed(local_stamp, remote_stamp, setup_log):
            print("[INFO] remote virtualenv does not match framework flags or the CUDA wheel index", flush=True)
            _drop_stale_remote_env(ssh, name)
    copy_rc = remote_copy(ssh, repo_dir, reuse=use_reuse)
    if copy_rc != 0:
        print("[INFO] retrying remote copy after possible SSH drop", flush=True)
        if not wait_for_ssh(ssh):
            return copy_rc
        copy_rc = remote_copy(ssh, repo_dir, reuse=True)
        if copy_rc != 0:
            return copy_rc
    result = ssh_run(ssh, _remote_script(name, resume=False, stamp=env_reuse_stamp(repo_dir)), timeout=7200)
    if result.returncode == 0 and REMOTE_OK in (result.stdout or ""):
        print("[PASS] remote validation", flush=True)
        _sync_remote_env_stamp(ssh, repo_dir)
        return 0
    if _connection_dropped(result):
        print("[INFO] SSH dropped (likely reboot). Waiting to resume setup.", flush=True)
        if not wait_for_ssh(ssh):
            print("[FAIL] SSH did not return after reboot", flush=True)
            return 1
        result = ssh_run(ssh, _remote_script(name, resume=True, stamp=env_reuse_stamp(repo_dir)), timeout=7200)
        if result.returncode == 0 and REMOTE_OK in (result.stdout or ""):
            print("[PASS] remote validation after reboot resume", flush=True)
            _sync_remote_env_stamp(ssh, repo_dir)
            return 0
    _emit(result.stdout or "")
    _emit(result.stderr or "")
    print("[FAIL] remote validation failed", flush=True)
    return result.returncode or 1


def recheck_first_workload(workload: str, args: argparse.Namespace, project_root: Path, ssh: str) -> int:
    """Rerun the first workload after a multi-workload batch.

    Smoke validation calls the CUDA header probe. A later workload that
    damaged the shared toolkit fails this recheck. This is not a second
    full-model baseline.
    """
    print(f"[START] end-of-batch toolkit recheck for workload {workload}", flush=True)
    repo = find_generated_repo(project_root, workload)
    if repo is None:
        print(f"[FAIL] no repository for end-of-batch recheck of workload {workload}", flush=True)
        return 1
    reuse = args.reuse_remote_env and not args.fresh_remote_env
    rc = remote_validate(ssh, repo, reuse=reuse)
    path = project_root / "batch_generation_manifest.json"
    if path.is_file() and rc != 0:
        batch = json.loads(path.read_text(encoding="utf-8"))
        for row in batch.get("repositories", []):
            if str(row.get("workload")) == workload:
                row["status"] = "failed"
                row["return_code"] = rc
                row["reason"] = "end-of-batch toolkit recheck failed"
                break
        path.write_text(json.dumps(batch, indent=2) + "\n", encoding="utf-8")
    if rc == 0:
        print(f"[PASS] end-of-batch toolkit recheck for workload {workload}", flush=True)
    else:
        print(f"[FAIL] end-of-batch toolkit recheck for workload {workload}", flush=True)
    return rc


def finish_template_copy(repo: Path, args: argparse.Namespace, rc: int) -> None:
    """Remove the nested template copy once the workload has passed.

    A failed workload keeps its copy so it can be debugged or retried with the
    same generator; the copy is removed by the passing retry, or by hand with
    scripts/remove_template_copy.py.
    """
    if getattr(args, "keep_template_copy", False):
        print(f"[INFO] --keep-template-copy: leaving the nested template copy in {repo}", flush=True)
        return
    if rc != 0:
        print(
            f"[INFO] Workload did not pass; keeping the nested template copy in {repo} for debugging. "
            f"Remove it later with: python3 scripts/remove_template_copy.py --repo-root \"{repo}\"",
            flush=True,
        )
        return
    try:
        removed_rc = remove_template_copy(repo)
    except Exception as exc:  # never let cleanup turn a passed workload into a crash
        print(f"[WARN] Template copy cleanup raised: {exc}", flush=True)
        removed_rc = 1
    if removed_rc != 0:
        print(
            f"[WARN] Workload passed, but the nested template copy could not be removed from {repo}. "
            f"Re-run: python3 scripts/remove_template_copy.py --repo-root \"{repo}\"",
            flush=True,
        )


def process_one(workload: str, args: argparse.Namespace, template_root: Path, project_root: Path, ssh: str) -> int:
    started = utc_now()
    repo_name = "unknown"
    print(f"[START] workload {workload} at {started}", flush=True)
    try:
        if not args.validate_only:
            command = [
                sys.executable,
                str(template_root / "scripts" / "create_generated_repo.py"),
                "--prompt-file",
                str(Path(args.prompt_file).resolve()),
                "--workload",
                workload,
                "--template-root",
                str(template_root),
                "--project-root",
                str(project_root),
            ]
            if args.force:
                command.append("--force")
            if args.skip_remote_refresh:
                command.append("--skip-remote-refresh")
            created = subprocess.run(command, cwd=str(template_root), check=False)
            if created.returncode != 0:
                raise RuntimeError(f"create_generated_repo.py exited {created.returncode}")
        repo = find_generated_repo(project_root, workload)
        if repo is None:
            raise RuntimeError(f"no repository directory for workload {workload}")
        ensure_gitkeep(repo)
        spec = json.loads((repo / "benchmark_specification.json").read_text(encoding="utf-8"))
        fields = {str(item.get("field_name", "")): str(item.get("value", "") or "") for item in spec}
        workbook_name = fields.get("Repo Name") or repo.name
        repo_name = workbook_name
        reuse = args.reuse_remote_env and not args.fresh_remote_env
        rc = remote_validate(ssh, repo, reuse=reuse)
        finished = utc_now()
        finish_template_copy(repo, args, rc)
        record(
            project_root,
            workload,
            repo_name,
            "passed" if rc == 0 else "failed",
            started,
            finished,
            "" if rc == 0 else f"remote rc={rc}",
            return_code=rc,
        )
        _stamp_generation_report(repo, started, finished)
        return rc
    except Exception as exc:
        finished = utc_now()
        record(project_root, workload, repo_name, "failed", started, finished, str(exc)[:300], return_code=1)
        print(f"[FAIL] {workload}: {exc}", flush=True)
        return 1


def _stamp_generation_report(repo: Path, started: str, finished: str) -> None:
    start_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(finished.replace("Z", "+00:00"))
    duration = max(0, int((end_dt - start_dt).total_seconds()))
    path = repo / "GENERATION_REPORT.md"
    if path.is_file():
        text = path.read_text(encoding="utf-8")
        block = (
            f"- generation_started_at: {started}\n"
            f"- generation_finished_at: {finished}\n"
            f"- generation_duration_seconds: {duration}\n"
        )
        updated = re.sub(
            r"- generation_started_at:.*\n- generation_finished_at:.*\n- generation_duration_seconds:.*\n",
            block,
            text,
            count=1,
        )
        if updated != text:
            path.write_text(updated, encoding="utf-8", newline="\n")
    manifest_path = repo / "results" / "generation_manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["generation_started_at"] = started
    manifest["generation_finished_at"] = finished
    manifest["generation_duration_seconds"] = duration
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    global REMOTE_ROOT
    _configure_stdio()
    args = parse_args()
    REMOTE_ROOT = normalize_remote_root(args.remote_root)
    template_root = Path(args.template_root).resolve()
    project_root = Path(args.project_root).resolve() if args.project_root else template_root.parent
    prompt = Path(args.prompt_file).resolve()
    workloads = [str(item) for item in (args.workload or []) + list(args.workloads)]
    if not workloads:
        raise SystemExit("usage: create_one_workload.py --prompt-file <file> --workload <N> [<N>...]")
    ssh = _ssh_target(prompt)
    rc = 0
    for workload in workloads:
        item_rc = process_one(str(workload), args, template_root, project_root, ssh)
        if item_rc != 0:
            rc = item_rc
    if rc == 0 and len(workloads) > 1 and ssh:
        rc = recheck_first_workload(str(workloads[0]), args, project_root, ssh)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
