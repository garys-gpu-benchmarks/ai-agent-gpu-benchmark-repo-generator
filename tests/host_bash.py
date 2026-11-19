#!/usr/bin/env python3
# File: tests/host_bash.py
# Description: HOST_BASH, the bash a test starts: Git Bash on Windows, never WSL.
#   Python on Windows looks in System32 before PATH, so subprocess.run(["bash", ...])
#   started WSL's bash.exe, which failed with "execvpe(/bin/bash) failed" on a laptop
#   without a WSL distribution: about 47 of the 71 Windows-only test failures
#   (TEMPLATE_00_147, OPEN_ISSUES T1). The generator's own commands already use
#   host_exec.resolve_host_bash() (TEMPLATE_00_146); tests use the same lookup.
# Usage: sys.path.insert(0, str(Path(__file__).resolve().parent)); from host_bash import HOST_BASH
"""The bash every test starts."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path


def _host_exec():
    path = Path(__file__).resolve().parents[1] / "scripts" / "host_exec.py"
    spec = importlib.util.spec_from_file_location("host_exec_for_tests", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_HOST_EXEC = _host_exec()
HOST_BASH = _HOST_EXEC.resolve_host_bash()


def bash_path(path: object) -> str:
    """A path as Git Bash's tools take it: /c/Users/... on Windows, unchanged elsewhere.

    GNU tar reads "C:" in C:\\Users\\... as a remote host name (TEMPLATE_00_147, T1).
    """
    return _HOST_EXEC.to_git_bash_path(str(path)) if os.name == "nt" else str(path)


def path_first(directory: object) -> str:
    """A script line that puts a test's stand-in tools first on PATH.

    Git for Windows' bash.exe puts /mingw64/bin and /usr/bin in front of the PATH it is
    given, so Git's own curl.exe ran instead of a test's stand-in curl and the tests
    downloaded from the internet (TEMPLATE_00_147, T1 round 2). Setting PATH inside the
    script runs after that. Harmless on Linux.
    """
    return f'export PATH="{bash_path(directory)}:$PATH"\n'
