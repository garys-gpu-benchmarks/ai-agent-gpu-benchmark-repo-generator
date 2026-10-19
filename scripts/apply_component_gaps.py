#!/usr/bin/env python3
"""Fill self-check gaps from resolved component contracts after init/config generation."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
import sys

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from resolve_implementation_components import (  # noqa: E402
    definition_fields,
    resolve_components,
    validate_component_vs_spec,
    validate_overlay_conflicts,
)


def _write_lf(path: Path, text: str, exe: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.replace("\r\n", "\n").replace("\r", "\n")
    if not data.endswith("\n"):
        data += "\n"
    path.write_bytes(data.encode("utf-8"))
    if exe or path.suffix == ".sh":
        path.chmod(path.stat().st_mode | 0o111)


def _load_gate(component_root: Path) -> dict:
    path = component_root / "gate.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _ensure_requirements(repo: Path, resolved: list[dict] | None = None) -> None:
    path = repo / "requirements.txt"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    extras = ["PyYAML>=6.0"]
    ids = {str(item.get("component_id") or "") for item in (resolved or [])}
    if ids & {"gups-amd", "gups-nvidia"}:
        extras.append("numpy>=1.26")
    if ids & {"sglang-prompt-response-amd", "sglang-serving-amd"}:
        extras.extend(
            [
                "soundfile>=0.12",
                "jsonschema>=4.0",
                "numpy>=1.26",
                "python-multipart>=0.0.9",
            ]
        )
    needed = [line for line in extras if line.split(">", 1)[0].split("=", 1)[0] not in text]
    if needed:
        _write_lf(path, (text.rstrip() + "\n" if text.strip() else "") + "\n".join(needed) + "\n")


_THRESHOLDS_KEY_RE = re.compile(r"(?m)^thresholds\s*:")


def _ensure_thresholds(repo: Path, resolved: list[dict]) -> None:
    yaml_path = repo / "config" / "benchmark_config.yaml"
    if not yaml_path.is_file():
        return
    overlay_rel = "config/benchmark_config.yaml"
    if any(overlay_rel in (item["component"].get("overlay") or []) for item in resolved):
        # A resolved component already claims this exact path as one of its
        # locked overlay files. _write_overlay_lock() (below) hashes the
        # pristine source file for that lock entry; appending a thresholds
        # block here would make the repo's copy diverge from that hash, and
        # self_check would then report "locked overlay rewritten". A
        # component that owns this file is responsible for its own
        # thresholds (via gate.json, baked into the overlay file itself).
        return
    text = yaml_path.read_text(encoding="utf-8")
    if _THRESHOLDS_KEY_RE.search(text):
        # A real top-level `thresholds:` key already exists. (A bare
        # substring check here previously also matched the word appearing
        # inside a comment, which silently skipped real injection.)
        return
    thresholds: dict[str, object] = {}
    for item in resolved:
        gate = _load_gate(Path(item["component_root"]))
        thresholds.update(gate.get("thresholds") or {})
    if not thresholds:
        return
    lines = ["", "thresholds:"]
    for key, value in thresholds.items():
        lines.append(f"  {key}: {value}")
    _write_lf(yaml_path, text.rstrip() + "\n" + "\n".join(lines) + "\n")


def _ensure_seed_fixture(repo: Path) -> None:
    path = repo / "scripts" / "validate_results.py"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    if "--seed-fixture" in text:
        return
    helper = '''
def seed_fixture(config_path: Path) -> Path:
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    fixture = Path("tests/fixtures/benchmark.db")
    fixture.parent.mkdir(parents=True, exist_ok=True)
    if fixture.exists():
        fixture.unlink()
    conn = sqlite3.connect(fixture)
    conn.execute("""CREATE TABLE runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            benchmark_id TEXT, benchmark_name TEXT, status TEXT,
            started_at TEXT, finished_at TEXT, error_message TEXT)""")
    conn.execute("""CREATE TABLE samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER,
            sample_index INTEGER, status TEXT, error_message TEXT)""")
    conn.execute(
        "INSERT INTO runs (benchmark_id, benchmark_name, status, started_at, finished_at, error_message) VALUES (?, ?, 'ok', ?, ?, NULL)",
        ("fixture", "seed-fixture", now, now),
    )
    run_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    for index in range(2):
        conn.execute(
            "INSERT INTO samples (run_id, sample_index, status, error_message) VALUES (?, ?, 'ok', NULL)",
            (run_id, index),
        )
    conn.commit()
    conn.close()
    return fixture

'''
    if "from datetime import datetime" not in text:
        text = text.replace("from pathlib import Path", "from datetime import datetime\nfrom pathlib import Path")
    text = text.replace(
        'parser.add_argument("--quiet", action="store_true")\n    args = parser.parse_args()',
        'parser.add_argument("--quiet", action="store_true")\n    parser.add_argument("--seed-fixture", action="store_true")\n    args = parser.parse_args()\n    if args.seed_fixture:\n        args.db = str(seed_fixture(Path(args.config)))',
    )
    if "def seed_fixture" not in text:
        text = text.replace("def main() -> int:", helper + "def main() -> int:")
    _write_lf(path, text, exe=True)


def _write_overlay_lock(repo: Path, resolved: list[dict]) -> None:
    lock = {}
    for item in resolved:
        cid = str(item["component_id"])
        root = Path(item["component_root"])
        for rel in item["component"].get("overlay") or []:
            src = root / "files" / str(rel)
            repo_copy = repo / str(rel)
            blob = repo_copy.read_bytes() if repo_copy.is_file() else src.read_bytes()
            digest = hashlib.sha256(blob).hexdigest()
            lock[str(rel)] = {"component_id": cid, "sha256": digest}
    _write_lf(repo / "results" / "overlay_lock.json", json.dumps(lock, indent=2) + "\n")


def _write_resolution_report(repo: Path, resolved: list[dict], fields: dict[str, str]) -> None:
    errors, warnings = validate_component_vs_spec(fields, resolved)
    locked = []
    materialize_filled = []
    agent_may_edit = [
        "PRD.md",
        "SPEC.md",
        "README.md",
        "requirements.txt",
        "config/benchmark_config.yaml",
        "GENERATION_REPORT.md",
    ]
    for item in resolved:
        cid = str(item["component_id"])
        for rel in item["component"].get("overlay") or []:
            locked.append(f"{cid}:{rel}")
        gate = _load_gate(Path(item["component_root"]))
        if gate.get("agent_may_edit"):
            agent_may_edit = list(dict.fromkeys(agent_may_edit + list(gate["agent_may_edit"])))
        if str(item["component"].get("role")) == "mixin":
            materialize_filled.extend(str(rel) for rel in item["component"].get("overlay") or [])
    payload = {
        "implementation_component_resolution": "automatic",
        "discovered": [
            {
                "component_id": item["component_id"],
                "role": item["component"].get("role"),
                "completeness": item["component"].get("completeness"),
                "reasons": item["reasons"],
                "overlay": item["component"].get("overlay"),
                "provides": item["component"].get("provides"),
                "does_not_provide": item["component"].get("does_not_provide"),
                "contracts": item["component"].get("contracts"),
            }
            for item in resolved
        ],
        "overlay_locked": locked,
        "mixin_or_materialized": materialize_filled,
        "agent_may_edit": agent_may_edit,
        "spec_warnings": warnings,
        "spec_errors": errors,
        "collector_present": _collector_present(repo, resolved),
        "collector_entry_points": _collector_entry_points(resolved),
    }
    _write_lf(repo / "results" / "component_resolution.json", json.dumps(payload, indent=2) + "\n")
    lines = [
        "# Component resolution leftover work",
        "",
        "Locked overlay files (recorded fingerprint):",
        "",
        "Each path below was copied from `implementation_components/<component-id>/files/<path>`.",
        "`self_check_generated_repo.sh` fails with `Locked overlay rewritten` when the sibling file and the `sha256` in `results/overlay_lock.json` differ. It does not open the template.",
        "`smoke_check_generated_repo.sh` fails with `Implementation component mismatch` when the sibling bytes differ from that template source.",
        "A smoke failure inside one of these files is repaired by writing the same bytes in three places: the template source, the sibling path, and that path's `sha256` in `results/overlay_lock.json`.",
        "Do not replace the overlay with a new collector or parser. Do not leave the workload failed when those three copies can be made identical. Do not run `create_generated_repo.py` again on a non-empty sibling (`--force` discards it). After the three copies match, recheck with `create_one_workload.py --validate-only`.",
        "`scripts/metric_contract.py` is not in this lock. Repair the generator `scripts/metric_contract.py` and the sibling copy, then use the same `--validate-only` recheck.",
        "",
    ]
    lines.extend(f"- `{item}`" for item in locked or ["(none)"])
    lines.extend(["", "Mixin / materialized files:", ""])
    lines.extend(f"- `{item}`" for item in materialize_filled or ["(none)"])
    lines.extend(["", "Agent may edit:", ""])
    lines.extend(f"- `{item}`" for item in agent_may_edit)
    entry_points = _collector_entry_points(resolved)
    if entry_points:
        lines.extend(["", "Collector entry points:", ""])
        lines.extend(f"- `{item}`" for item in entry_points)
    elif not (repo / "scripts" / "collect_workload.py").is_file():
        lines.extend(
            [
                "",
                "**No implementation-component collector matched.** Implement the measurement entry point from the benchmark specification. Do not invent a generic collector in the template.",
            ]
        )
    for warning in warnings:
        lines.append(f"- WARN: {warning}")
    _write_lf(repo / "results" / "component_leftover_work.md", "\n".join(lines) + "\n")
    print("[INFO] Wrote results/component_resolution.json and results/overlay_lock.json")
    if payload["collector_present"]:
        print("[INFO] Collector entry points:", ", ".join(payload.get("collector_entry_points") or []))
    else:
        print("[WARN] No implementation-component collector; agent must implement the measurement entry point.")


def _named_collectors(resolved: list[dict]) -> list[str]:
    names: list[str] = []
    for item in resolved:
        component = item.get("component") or {}
        if str(component.get("role")) == "mixin":
            continue
        for rel in component.get("overlay") or []:
            text = str(rel)
            if text.startswith("scripts/collect_") and text.endswith(".py") and text != "scripts/collect_workload.py":
                name = Path(text).name
                if name not in names:
                    names.append(name)
    return names


def _overlay_replaces_runner(resolved: list[dict]) -> bool:
    for item in resolved:
        component = item.get("component") or {}
        if str(component.get("role")) == "mixin":
            continue
        if "run_benchmark.sh" in [str(path) for path in (component.get("overlay") or [])]:
            return True
    return False


def _write_collector_adapter(repo: Path, resolved: list[dict]) -> None:
    """Harness always calls scripts/collect_workload.py unless the overlay runner does not."""
    dest = repo / "scripts" / "collect_workload.py"
    if dest.is_file() and dest.stat().st_size > 0:
        return
    names = _named_collectors(resolved)
    if not names:
        return
    listed = ",\n".join(f"    {name!r}," for name in names)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        f'''#!/usr/bin/env python3
"""Harness adapter. run_benchmark.sh calls scripts/collect_workload.py."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HELPER_NAMES = (
{listed}
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--raw-file", required=True)
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--device", default="gpu")
    parser.add_argument("--output-format", default="csv")
    args, extra = parser.parse_known_args()
    here = Path(__file__).resolve().parent
    helper = next((here / name for name in HELPER_NAMES if (here / name).is_file()), None)
    if helper is None:
        raise SystemExit("[FAIL] component collector not found beside collect_workload.py")
    Path(args.run_dir).mkdir(parents=True, exist_ok=True)
    probed = subprocess.run([sys.executable, str(helper), "--help"], capture_output=True, text=True)
    help_text = (probed.stdout or "") + (probed.stderr or "")
    cmd = [sys.executable, str(helper), "--profile", args.profile, "--config", args.config]
    wants_run_dir = "--run-dir" in help_text
    wants_raw = "--raw-file" in help_text
    wants_output = "--output" in help_text
    if wants_output and not wants_run_dir:
        cmd.extend(["--output", args.raw_file])
    else:
        if wants_run_dir:
            cmd.extend(["--run-dir", args.run_dir])
        if wants_raw:
            cmd.extend(["--raw-file", args.raw_file])
        if wants_output:
            cmd.extend(["--output", args.raw_file])
    if "--output-format" in help_text:
        cmd.extend(["--output-format", args.output_format])
    # Workbook model_config is display text ("custom"). Collectors that take
    # the flag want the harness token. Real shapes stay in --config.
    if "--model-config" in help_text and "--model-config" not in extra:
        cmd.extend(["--model-config", "true"])
    cmd.extend(extra)
    return subprocess.run(cmd, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
''',
        encoding="utf-8",
        newline="\n",
    )
    print(f"[INFO] Wrote harness adapter {dest.relative_to(repo)} -> {', '.join(names)}")


def _collector_entry_points(resolved: list[dict]) -> list[str]:
    rows: list[str] = []
    for item in resolved:
        component = item.get("component") or {}
        if str(component.get("role")) == "mixin":
            continue
        entry = str(component.get("entry_point") or "").strip()
        cid = str(item.get("component_id") or "")
        if entry:
            rows.append(f"{cid}:{entry}")
    return rows


def _collector_present(repo: Path, resolved: list[dict]) -> bool:
    """True when the file run_benchmark.sh actually executes is present."""
    runner = repo / "run_benchmark.sh"
    if _overlay_replaces_runner(resolved) and runner.is_file():
        text = runner.read_text(encoding="utf-8", errors="replace")
        if "collect_workload.py" not in text:
            return True
    collect = repo / "scripts" / "collect_workload.py"
    return collect.is_file() and collect.stat().st_size > 0


def apply_component_gaps(repo_root: Path, components_root: Path | None = None) -> int:
    repo = Path(repo_root).resolve()
    spec = repo / "benchmark_specification.json"
    if components_root is None:
        copy_name = ""
        manifest = repo / "results" / "generation_manifest.json"
        if manifest.is_file():
            copy_name = str(json.loads(manifest.read_text(encoding="utf-8")).get("template_copy_path") or "")
        if copy_name and (repo / copy_name / "implementation_components").is_dir():
            components_root = repo / copy_name / "implementation_components"
        else:
            components_root = Path(__file__).resolve().parents[1] / "implementation_components"
    try:
        resolved = resolve_components(spec, Path(components_root))
    except ValueError as exc:
        print(f"[FAIL] {exc}")
        return 1
    validate_overlay_conflicts(resolved)
    fields = definition_fields(spec)
    errors, warnings = validate_component_vs_spec(fields, resolved)
    for warning in warnings:
        print(f"[WARN] {warning}")
    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        return 1
    _ensure_requirements(repo, resolved)
    _ensure_thresholds(repo, resolved)
    _ensure_seed_fixture(repo)
    _write_overlay_lock(repo, resolved)
    _write_collector_adapter(repo, resolved)
    _write_resolution_report(repo, resolved, fields)
    if not _collector_present(repo, resolved):
        print(
            "[FAIL] Missing collector: run_benchmark.sh calls scripts/collect_workload.py "
            "and no overlay or adapter provided it. Create cannot continue."
        )
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply component contract gaps to a generated repository")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--components-root", default="")
    args = parser.parse_args()
    components = Path(args.components_root) if args.components_root else None
    return apply_component_gaps(Path(args.repo_root), components)


if __name__ == "__main__":
    raise SystemExit(main())
