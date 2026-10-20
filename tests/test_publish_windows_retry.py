#!/usr/bin/env python3
# File: tests/test_publish_windows_retry.py
# Description: Step 3 of the publish script retries a workload once, from a fresh
#   copy, when Git Bash could not start a process (2026-10-20: 404 and 405 stopped
#   with "fork: Resource temporarily unavailable" / "Bad address"). A failed check
#   is not retried, so a fix made by hand in the publish tree is never overwritten.
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "publish_benchmarks_to_github.sh"
BASH = shutil.which("bash")

# prepare fails once with a Windows fork error (a marker file remembers the first call).
PREPARE_FLAKY = """#!/usr/bin/env bash
if [[ ! -f ../.flaky_seen ]]; then
  touch ../.flaky_seen
  echo "scripts/prepare_github_publish.sh: fork: retry: Resource temporarily unavailable"
  rm -f README.md
  exit 1
fi
[[ -f README.md ]] || { echo "README.md missing: half-prepared copy"; exit 1; }
echo prepared
"""
PREPARE_BROKEN = """#!/usr/bin/env bash
echo "[FAIL] README.md has an unfilled placeholder"
exit 1
"""
CHECK_OK = "#!/usr/bin/env bash\necho checked\n"


def step3_program(text: str) -> str:
    start = text.index("readonly WINDOWS_PROCESS_ERROR=")
    helpers = text[start:text.index("# Platform name from a workload number", start)]
    loop_start = text.index(": >_logs/not-ready.txt\nprepare_and_check()")
    loop = text[loop_start:text.index("not_ready=$(wc -l <_logs/not-ready.txt)", loop_start)]
    return "\n".join([
        "set -u",
        'in_list() { grep -qxF "$1" "$2" 2>/dev/null; }',
        "sleep() { :; }",
        'ORG=example-org',
        helpers,
        'cd "${PUB}"',
        loop,
    ])


def workload(root: Path, name: str, prepare: str) -> None:
    scripts = root / name / "scripts"
    scripts.mkdir(parents=True)
    (root / name / "README.md").write_text("readme\n", encoding="utf-8")
    (scripts / "prepare_github_publish.sh").write_text(prepare, encoding="utf-8")
    (scripts / "check_github_publish_ready.sh").write_text(CHECK_OK, encoding="utf-8")


@unittest.skipIf(BASH is None, "bash is not installed")
class PublishWindowsRetry(unittest.TestCase):
    def run_step3(self, prepare: str) -> tuple[subprocess.CompletedProcess[str], Path]:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        gen, pub = tmp / "run", tmp / "run_PubTree"
        workload(gen, "404-x", prepare)
        (pub / "_logs").mkdir(parents=True)
        shutil.copytree(gen / "404-x", pub / "404-x")
        program = f'GEN="{gen}"\nPUB="{pub}"\n' + step3_program(SCRIPT.read_text(encoding="utf-8"))
        result = subprocess.run([BASH, "-c", program], capture_output=True, text=True, timeout=60)
        return result, pub

    def test_windows_error_retries_from_a_fresh_copy(self) -> None:
        result, pub = self.run_step3(PREPARE_FLAKY)
        self.assertIn("RETRY      404-x", result.stdout, result.stderr)
        self.assertIn("READY      404-x", result.stdout)
        self.assertEqual((pub / "_logs" / "ready.txt").read_text().split(), ["404-x"])
        self.assertTrue((pub / "_logs" / "404-first-attempt.log").is_file())

    def test_a_failed_check_is_not_retried(self) -> None:
        result, pub = self.run_step3(PREPARE_BROKEN)
        self.assertNotIn("RETRY", result.stdout)
        self.assertIn("NOT READY  404-x", result.stdout)
        self.assertNotIn("Windows could not start a process", result.stdout)
        self.assertFalse((pub / "_logs" / "ready.txt").exists())


if __name__ == "__main__":
    unittest.main()
