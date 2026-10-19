#!/usr/bin/env python3
# A locked overlay is a fingerprint. These sources must tell an agent to repair
# a smoke failure in the template, the sibling, and the lock, then --validate-only.
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SOURCES = (
    "scripts/apply_component_gaps.py",
    "scripts/fill_generated_docs.py",
    "AGENTS.md",
    "implementation_components/README.md",
    "docs/AI_AGENT_INSTRUCTIONS.md",
    "docs/generation-workflow.md",
    "docs/IMPLEMENTATION_COMPONENTS.md",
    "docs/TEMPLATE_README.md",
    "docs/repository-template.md",
    ".cursor/rules/generate-workloads.mdc",
)

BANS = (
    "Locked overlay files (do not rewrite)",
    "Do not rewrite locked overlay files",
    "do not rewrite overlay files listed",
    "Do not overwrite files listed in `results/overlay_lock.json`",
    "must not be rewritten after init",
    "after init, do not rewrite `results/overlay_lock.json`",
)


class OverlayRepairInstructionTests(unittest.TestCase):
    def test_agent_sources_describe_the_three_place_repair(self) -> None:
        combined = "\n".join((ROOT / rel).read_text(encoding="utf-8") for rel in SOURCES)
        self.assertIn("create_one_workload.py --validate-only", combined)
        self.assertIn("Locked overlay rewritten", combined)
        self.assertIn("Implementation component mismatch", combined)
        self.assertIn("scripts/metric_contract.py", combined)
        for ban in BANS:
            self.assertNotIn(ban, combined, ban)


if __name__ == "__main__":
    unittest.main()
