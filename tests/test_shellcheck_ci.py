# File: tests/test_shellcheck_ci.py
# Description: Runs the generator CI's shellcheck step locally, so a warning
#   stops the test run here instead of failing Template CI after a publish.
#   The CI command is:
#     find scripts templates user_scripts -name "*.sh" -type f \
#       -not -path 'scripts/templates/*' -print0 | xargs -0 shellcheck --severity=warning
#   Skipped when shellcheck is not installed; the SC2100 check below runs anyway.
# License: Apache-2.0

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CI_DIRS = ("scripts", "templates", "user_scripts")


def ci_shell_scripts():
    files = []
    for top in CI_DIRS:
        root = REPO / top
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.sh")):
            rel = path.relative_to(REPO).as_posix()
            if rel.startswith("scripts/templates/") or "__pycache__" in rel:
                continue
            files.append(path)
    return files


# A bare word with a hyphen after "=" (slug=bundle-amd-ubuntu-2404) is read by
# shellcheck as arithmetic (SC2100). Values like that must be quoted.
_UNQUOTED_HYPHEN_ASSIGN = re.compile(r"(?:^|[;\s])[A-Za-z_][A-Za-z0-9_]*=[A-Za-z][A-Za-z0-9_]*-[A-Za-z0-9_-]+(?=\s*(?:;|$))")


class ShellcheckCiTest(unittest.TestCase):
    def test_publish_script_has_no_unquoted_hyphenated_assignments(self):
        script = REPO / "user_scripts" / "publish_benchmarks_to_github.sh"
        problems = []
        for n, line in enumerate(script.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if _UNQUOTED_HYPHEN_ASSIGN.search(line):
                problems.append(f"line {n}: {line.strip()}")
        self.assertEqual(problems, [], "Quote hyphenated values (shellcheck SC2100)")

    def test_ci_shellcheck_step_passes(self):
        shellcheck = shutil.which("shellcheck")
        if not shellcheck:
            self.skipTest("shellcheck is not installed")
        # CI checks out LF files; a Windows copy may have CRLF, so check LF copies.
        with tempfile.TemporaryDirectory() as tmp:
            copies = []
            for path in ci_shell_scripts():
                dest = Path(tmp) / path.relative_to(REPO)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
                copies.append(str(dest.relative_to(tmp)))
            result = subprocess.run(
                [shellcheck, "--severity=warning", *copies],
                cwd=tmp, capture_output=True, text=True, check=False,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
