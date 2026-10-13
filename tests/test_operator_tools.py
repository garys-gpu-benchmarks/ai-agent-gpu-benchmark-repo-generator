#!/usr/bin/env python3
# File: tests/test_operator_tools.py
# Description: create_generated_repo.install_operator_tools puts get_remote_info.sh and
#              show_metrics.sh in the project folder (the parent of the folder holding the
#              workloads), keeps an existing copy that differs, and never puts them inside
#              a workload.
from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from create_generated_repo import OPERATOR_TOOLS, install_operator_tools  # noqa: E402
from init_generated_repo import SHARED_DIRS  # noqa: E402


class OperatorToolTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name) / "Project347_101_to_132"
        self.batch = self.project / "TEMPLATE_00_105"
        self.batch.mkdir(parents=True)
        self.dst = self.project / "get_remote_info.sh"
        self.dsts = [self.project / Path(rel).name for rel in OPERATOR_TOOLS]

    def tearDown(self):
        self._tmp.cleanup()

    def _install(self) -> tuple[list[Path], str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            installed = install_operator_tools(ROOT, self.batch)
        return installed, out.getvalue()

    def test_master_copy_is_an_operator_tool_not_a_workload_file(self):
        self.assertIn("templates/suite-tools/scripts/get_remote_info.sh", OPERATOR_TOOLS)
        self.assertIn("templates/suite-tools/scripts/show_metrics.sh", OPERATOR_TOOLS)
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


if __name__ == "__main__":
    unittest.main()
