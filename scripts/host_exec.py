#!/usr/bin/env python3
# File: scripts/host_exec.py
# Description: Official Windows host shell is Git Bash + OpenSSH, never WSL bash.
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path


def resolve_host_bash() -> str:
    if os.name != "nt":
        return shutil.which("bash") or "bash"
    env = os.environ.get("GIT_BASH") or ""
    candidates = [
        env,
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        str(Path.home() / "AppData/Local/Programs/Git/bin/bash.exe"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        lowered = str(path).lower().replace("\\", "/")
        if "windowsapps" in lowered or "system32" in lowered or "wsl" in lowered:
            continue
        if path.is_file() and ("git" in lowered or env):
            return str(path)
    found = shutil.which("bash") or ""
    lowered = found.lower().replace("\\", "/")
    if found and "git" in lowered and "windowsapps" not in lowered and "wsl" not in lowered:
        return found
    raise SystemExit(
        "[FAIL] Git Bash not found. The official Windows driver requires "
        "Git for Windows bash.exe, not WSL bash. Set GIT_BASH to the Git bash.exe path."
    )


def to_git_bash_path(path: str) -> str:
    text = str(path or "").strip().strip('"').strip("'")
    match = re.match(r"^([A-Za-z]):[\\/](.*)$", text)
    if match:
        return f"/{match.group(1).lower()}/{match.group(2).replace(chr(92), '/')}"
    return text.replace("\\", "/")


def normalize_remote_root(value: str) -> str:
    """Return the VM install directory, undoing Git Bash's /opt rewrite.

    MSYS converts a ``/opt/benchmarks`` argument into
    ``C:/Program Files/Git/opt/benchmarks`` before Python sees it. Installs
    belong at ``/opt/benchmarks`` on the Ubuntu VM, never under ``/root`` or
    ``/opt/workloads``.
    """
    text = str(value or "").strip().strip('"').strip("'").replace("\\", "/")
    rewritten = re.search(r"/Program Files/Git(?P<opt>/opt(?:/.*)?)$", text, flags=re.IGNORECASE)
    if rewritten:
        text = rewritten.group("opt")
    text = text.rstrip("/") or "/opt/benchmarks"
    forbidden = ("/root", "/opt/workloads")
    if text in forbidden or any(text.startswith(prefix + "/") for prefix in forbidden):
        raise SystemExit(
            "[FAIL] Remote install path must stay /opt/benchmarks. "
            f"Refusing {text}."
        )
    return text


def normalize_ssh_command(ssh: str) -> str:
    """Rewrite Windows drive-letter key paths so Git Bash OpenSSH can read -i."""
    parts = re.split(r"(\s+)", ssh.strip())
    out: list[str] = []
    take_path = False
    for part in parts:
        if take_path and part.strip():
            out.append(to_git_bash_path(part))
            take_path = False
            continue
        out.append(part)
        if part.strip() == "-i":
            take_path = True
    return "".join(out)


def _stream_to_log(
    argv: list[str],
    *,
    cwd: Path | None,
    timeout: int | None,
    env: dict[str, str],
    log_path: Path,
    label: str,
    heartbeat_s: float,
) -> subprocess.CompletedProcess[str]:
    """Run argv, append its output to log_path as it arrives, and print a heartbeat.

    The console gets one line every heartbeat_s seconds instead of the output itself:
    a ROCm or CUDA setup log is larger than the 1 MB console capture (TEMPLATE_00_134).
    The returned CompletedProcess still holds the full stdout and stderr.
    """
    import threading
    import time

    log_path.parent.mkdir(parents=True, exist_ok=True)
    out: list[str] = []
    err: list[str] = []
    last = [""]
    # monotonic time of the last non-empty output line, for the heartbeat
    last_output = [time.monotonic()]
    lock = threading.Lock()
    proc = subprocess.Popen(
        argv,
        cwd=str(cwd) if cwd else None,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    def pump(stream, sink: list[str], prefix: str) -> None:
        for line in iter(stream.readline, ""):
            sink.append(line)
            with lock:
                with log_path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(prefix + line if line.endswith("\n") else prefix + line + "\n")
                if line.strip():
                    last[0] = line.strip()
                    last_output[0] = time.monotonic()
        stream.close()

    readers = [
        threading.Thread(target=pump, args=(proc.stdout, out, ""), daemon=True),
        threading.Thread(target=pump, args=(proc.stderr, err, "[stderr] "), daemon=True),
    ]
    for reader in readers:
        reader.start()
    started = time.monotonic()
    next_beat = started + heartbeat_s
    while True:
        try:
            proc.wait(timeout=1.0)
            break
        except subprocess.TimeoutExpired:
            pass
        now = time.monotonic()
        if timeout is not None and now - started > timeout:
            proc.kill()
            proc.wait()
            for reader in readers:
                reader.join(timeout=5)
            raise subprocess.TimeoutExpired(argv, timeout, output="".join(out), stderr="".join(err))
        if now >= next_beat:
            elapsed = int(now - started)
            with lock:
                quiet = int(now - last_output[0])
                tail = last[0][:100]
            # The same "last:" line repeated for minutes looked like a hang (330, 332 and
            # 431 in TEMPLATE_00_140); say how long the output has been unchanged instead.
            if quiet >= heartbeat_s:
                print(
                    f"[{label}] still running {elapsed // 60}m{elapsed % 60:02d}s; "
                    f"no new output for {quiet // 60}m{quiet % 60:02d}s (last: {tail})",
                    flush=True,
                )
            else:
                print(f"[{label}] still running {elapsed // 60}m{elapsed % 60:02d}s; last: {tail}", flush=True)
            next_beat = now + heartbeat_s
    for reader in readers:
        reader.join(timeout=30)
    return subprocess.CompletedProcess(argv, proc.returncode, "".join(out), "".join(err))


def run_host_bash(
    command: str,
    *,
    cwd: Path | None = None,
    timeout: int | None = None,
    check: bool = False,
    stream_log: Path | None = None,
    heartbeat_label: str = "remote",
    heartbeat_s: float = 60.0,
) -> subprocess.CompletedProcess[str]:
    """Run a Git Bash command and return its output.

    With stream_log, the output is also appended to that file as it arrives and the
    console gets a heartbeat line every heartbeat_s seconds (TEMPLATE_00_134).
    """
    bash = resolve_host_bash()
    env = os.environ.copy()
    # Git Bash rewrites /opt/... into C:/Program Files/Git/opt/... before ssh.
    if os.name == "nt":
        env["MSYS_NO_PATHCONV"] = "1"
        env["MSYS2_ARG_CONV_EXCL"] = "*"
    if stream_log is not None:
        result = _stream_to_log(
            [bash, "-lc", command], cwd=cwd, timeout=timeout, env=env,
            log_path=Path(stream_log), label=heartbeat_label, heartbeat_s=heartbeat_s,
        )
        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)
        return result
    return subprocess.run(
        [bash, "-lc", command],
        cwd=str(cwd) if cwd else None,
        check=check,
        timeout=timeout,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )


def ssh_argv(ssh: str) -> list[str]:
    import shlex

    return shlex.split(normalize_ssh_command(ssh))
