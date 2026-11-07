#!/usr/bin/env python3
"""[RUN] lines: always in run.log, on the terminal only at --log-level DEBUG."""
from __future__ import annotations

import glob
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCRIPT = r"""
set -euo pipefail
source "{root}/scripts/lib/common.sh"
set_log_level "$1"
set_benchmark_run_dir "$2"
: > "$2/run.log"
log_run "python scripts/collect_workload.py --profile smoke"
printf '[RUN] inner build\nsample_index,status\n0,ok\n' | tee -a "$2/run.log" | hide_run_lines
run_cmd echo hello
set +e
( printf '[RUN] failing step\nboom\n'; exit 3 ) 2>&1 | tee -a "$2/run.log" | hide_run_lines
echo "status=${{PIPESTATUS[0]}}"
"""


def run(level: str) -> tuple[str, str]:
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "t.sh"
        script.write_text(SCRIPT.format(root=ROOT), encoding="utf-8")
        run_dir = Path(tmp) / "run"
        run_dir.mkdir()
        out = subprocess.run(["bash", str(script), level, str(run_dir)], capture_output=True, text=True, check=True)
        return out.stdout, (run_dir / "run.log").read_text(encoding="utf-8")


class RunLineLogLevelTests(unittest.TestCase):
    def test_info_hides_run_lines_but_run_log_keeps_them(self) -> None:
        screen, log = run("INFO")
        self.assertNotIn("[RUN]", screen)
        self.assertIn("0,ok", screen)
        self.assertIn("hello", screen)
        for command in ("collect_workload.py", "inner build", "echo hello", "failing step"):
            self.assertIn(command, log)
        self.assertIn("status=3", screen)  # a failing step still reports its own status

    def test_debug_prints_run_lines(self) -> None:
        screen, _log = run("DEBUG")
        self.assertIn("[RUN] python scripts/collect_workload.py --profile smoke", screen)
        self.assertIn("[RUN] inner build", screen)
        self.assertIn("[RUN] echo hello", screen)

    def test_runners_do_not_echo_run_lines_directly(self) -> None:
        template = (ROOT / "scripts" / "materialize_generated_harness.py").read_text(encoding="utf-8")
        self.assertNotIn('echo "[RUN]', template)
        self.assertIn("| hide_run_lines", template)
        for runner in glob.glob(str(ROOT / "implementation_components" / "*" / "files" / "run_benchmark.sh")):
            text = Path(runner).read_text(encoding="utf-8")
            self.assertNotIn('echo "[RUN]', text, runner)


if __name__ == "__main__":
    unittest.main()
