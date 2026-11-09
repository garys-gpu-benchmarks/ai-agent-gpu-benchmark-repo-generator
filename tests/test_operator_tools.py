#!/usr/bin/env python3
# File: tests/test_operator_tools.py
# Description: create_generated_repo.install_operator_tools puts get_benchmark_results.sh and
#              show_metrics.sh in the project folder (the parent of the folder holding the
#              workloads) and keeps an existing copy that differs. install_workload_tools
#              puts show_metrics.sh and list_runs.sh at the top of each workload.
from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from create_generated_repo import OPERATOR_TOOLS, WORKLOAD_TOOLS, install_operator_tools, install_workload_tools  # noqa: E402
from init_generated_repo import SHARED_DIRS  # noqa: E402
import create_one_workload  # noqa: E402


class OperatorToolTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name) / "Project347_101_to_132"
        self.batch = self.project / "TEMPLATE_00_105"
        self.batch.mkdir(parents=True)
        self.dst = self.project / "get_benchmark_results.sh"
        self.dsts = [self.project / Path(rel).name for rel in OPERATOR_TOOLS]

    def tearDown(self):
        self._tmp.cleanup()

    def _install(self) -> tuple[list[Path], str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            installed = install_operator_tools(ROOT, self.batch)
        return installed, out.getvalue()

    def test_master_copy_is_an_operator_tool_not_a_workload_file(self):
        self.assertIn("user_scripts/get_benchmark_results.sh", OPERATOR_TOOLS)
        self.assertIn("user_scripts/show_metrics.sh", OPERATOR_TOOLS)
        for rel in OPERATOR_TOOLS:
            self.assertTrue((ROOT / rel).is_file(), rel)
        self.assertNotIn("templates", SHARED_DIRS)

    def test_installs_in_project_folder(self):
        installed, out = self._install()
        self.assertEqual(installed, self.dsts)
        self.assertIn("Installed operator tool", out)
        for rel, dst in zip(OPERATOR_TOOLS, self.dsts):
            expected = (ROOT / rel).read_bytes().replace(b"\r\n", b"\n")
            self.assertEqual(dst.read_bytes(), expected)
            if os.name != "nt":
                self.assertTrue(os.access(dst, os.X_OK))
            self.assertFalse((self.batch / dst.name).exists())

    def test_second_workload_leaves_identical_copy_alone(self):
        self._install()
        installed, out = self._install()
        self.assertEqual(installed, [])
        self.assertEqual(out, "")

    def test_existing_different_copy_is_kept(self):
        self.dst.write_text("#!/usr/bin/env bash\necho mine\n", encoding="utf-8")
        installed, out = self._install()
        self.assertEqual(installed, self.dsts[1:])
        self.assertIn("Kept existing", out)
        self.assertEqual(self.dst.read_text(encoding="utf-8"), "#!/usr/bin/env bash\necho mine\n")


class RemoteShowMetricsInstallTests(unittest.TestCase):
    def test_remote_copy_installs_suite_tools_at_opt_benchmarks(self) -> None:
        calls: list[str] = []

        def fake_run(command: str, cwd=None, timeout=None):
            calls.append(command)

            class Result:
                returncode = 0
                stdout = create_one_workload.COPY_OK + "\n"
                stderr = ""

            return Result()

        with patch.object(create_one_workload, "run_host_bash", side_effect=fake_run):
            rc = create_one_workload.remote_copy(
                "ssh -i /path/to/.ssh/<amd_ssh_key> root@203.0.113.10",
                Path("/tmp/101-sample"),
                reuse=True,
            )
        self.assertEqual(rc, 0)
        self.assertEqual(len(calls), 5)  # the workload copy plus the four suite tools
        for name in ("show_metrics.sh", "run_benchmark_suite.sh", "get_benchmark_results.sh", "list_runs.sh"):
            install = next(command for command in calls if f"/opt/benchmarks/{name}" in command)
            self.assertIn(f"chmod 755 /opt/benchmarks/{name}", install)
            self.assertIn(f"user_scripts/{name}", install.replace("\\", "/"))
        publish = (ROOT / "user_scripts" / "publish_benchmarks_to_github.sh").read_text(encoding="utf-8")
        self.assertIn('tr -d \'\\r\' <"${METRICS_SCRIPT}" >show_metrics.sh', publish)
        self.assertIn("for f in run_benchmark_suite.sh show_metrics.sh", publish)
        self.assertNotIn("write_bundle_run_sh", publish)

    def test_workload_gets_show_metrics_and_list_runs(self):
        # TEMPLATE_00_128: list_runs.sh joins show_metrics.sh at the top of every workload.
        self.assertEqual(WORKLOAD_TOOLS, ("user_scripts/show_metrics.sh", "user_scripts/list_runs.sh"))
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "107-sys-bench-amd-stream-ddr5-bandwidth-ubu2404"
            repo.mkdir()
            with contextlib.redirect_stdout(io.StringIO()):
                installed = install_workload_tools(ROOT, repo)
            self.assertEqual([path.name for path in installed], ["show_metrics.sh", "list_runs.sh"])
            for rel in WORKLOAD_TOOLS:
                dst = repo / Path(rel).name
                self.assertEqual(dst.read_bytes(), (ROOT / rel).read_bytes().replace(b"\r\n", b"\n"))
                if os.name != "nt":
                    self.assertTrue(os.access(dst, os.X_OK))
        publish = (ROOT / "user_scripts" / "publish_benchmarks_to_github.sh").read_text(encoding="utf-8")
        self.assertIn("for WORKLOAD_TOOL in show_metrics.sh list_runs.sh; do", publish)


if __name__ == "__main__":
    unittest.main()
