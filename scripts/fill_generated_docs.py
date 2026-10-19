#!/usr/bin/env python3
# File: scripts/fill_generated_docs.py
# Description: Official PRD.md / SPEC.md / README.md / GENERATION_REPORT.md filler.
# Substitutes {{Field Name}} and expands [[GENERATE]] from benchmark_specification.json.
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from generated_repo_directory import generated_repo_directory_name
from text_io import write_lf

TOKEN_RE = re.compile(r"\{\{([^}]+)\}\}")
GENERATE_RE = re.compile(r"\[\[GENERATE(?:\s*—\s*OPTIONAL)?[\s\S]*?\]\]")
HTML_COMMENT_RE = re.compile(r"<!--[\s\S]*?-->\s*", re.M)
EMPTY_VALUES = {"", "—", "-", "--", "None", "none", "TBD", "n/a", "N/A"}


def _python_requirement(value: str) -> str:
    """Workbook cells already say 'Python 3.12.3'. A bare version still gets the word."""
    text = str(value or "").strip()
    if text.lower().startswith("python"):
        return text
    if text:
        return f"Python {text}"
    return "Python"


def load_fields(spec_path: Path) -> dict[str, str]:
    data = json.loads(spec_path.read_text(encoding="utf-8"))
    return {
        str(item.get("field_name", "")): str(item.get("value", "") or "")
        for item in data
        if isinstance(item, dict) and item.get("field_name")
    }


def _profile_values(fields: dict[str, str]) -> dict:
    raw = fields.get("Profile Parameter Values", "")
    if not raw or raw in EMPTY_VALUES:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parameters(fields: dict[str, str]) -> list[str]:
    rows = []
    for index in range(1, 21):
        value = str(fields.get(f"Parameter_{index:02d}", "") or "").strip()
        if value in EMPTY_VALUES:
            continue
        rows.append(value)
    return rows


def _sentences(text: str, count: int) -> str:
    parts = re.split(r"(?<=[.!?])\s+", str(text or "").strip())
    kept = [part.strip() for part in parts if part.strip()][:count]
    return " ".join(kept) if kept else "TBD — confirm against tool documentation"


def _cli_flag(name: str) -> str:
    return "--" + re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower()


def _profile_cell(values: dict, name: str) -> tuple[str, str]:
    if not values:
        return "TBD — confirm against tool documentation", "TBD — confirm against tool documentation"
    # Profile Parameter Values is typically {smoke:{name:v}, baseline:{...}, extended:{...}}
    # or {name: {smoke, baseline, extended}}
    smoke = baseline = extended = ""
    if all(key in values for key in ("smoke", "baseline", "extended")) and isinstance(values.get("smoke"), dict):
        smoke = values["smoke"].get(name, "")
        baseline = values["baseline"].get(name, "")
        extended = values["extended"].get(name, "")
    elif name in values and isinstance(values[name], dict):
        smoke = values[name].get("smoke", "")
        baseline = values[name].get("baseline", "")
        extended = values[name].get("extended", "")
    else:
        smoke = values.get(name, "")
    tested = ", ".join(
        f"{label}={item}"
        for label, item in (("smoke", smoke), ("baseline", baseline), ("extended", extended))
        if str(item) not in EMPTY_VALUES
    )
    default = str(baseline or smoke or "")
    if not tested:
        tested = "TBD — confirm against tool documentation"
    if default in EMPTY_VALUES:
        default = "TBD — confirm against tool documentation"
    return tested, default


def _metrics_items(fields: dict[str, str]) -> list[str]:
    text = fields.get("Metrics", "")
    parts = [part.strip() for part in re.split(r"(?=#\d)", text) if part.strip()]
    return parts or ([text] if text.strip() else [])


def _is_matrix_workload(parameters: list[str]) -> bool:
    blob = " ".join(parameters).lower()
    return bool(re.search(r"\b(m|n|k|rows|cols|lda|ldb|ldc)\b", blob))


def _hardware_table(fields: dict[str, str], keys: list[str]) -> str:
    config = fields.get("Hardware Config", "")
    rows = ["| Component | Specification |", "| --- | --- |"]
    found = 0
    for key in keys:
        match = re.search(rf"{re.escape(key)}\s*[:=]\s*([^;\n]+)", config, flags=re.I)
        if match:
            rows.append(f"| {key} | {match.group(1).strip()} |")
            found += 1
    if not found:
        rows.append(f"| Hardware Config | {config or 'TBD — confirm against tool documentation'} |")
    return "\n".join(rows)


def expand_generate(instruction: str, fields: dict[str, str]) -> str:
    text = instruction.lower()
    parameters = _parameters(fields)
    profiles = _profile_values(fields)
    repo_name = fields.get("Repo Name", "")
    workload = fields.get("Workload Number", "")
    slug = generated_repo_directory_name(workload, repo_name)
    exec_desc = fields.get("Execution Description With Parameters", "")
    install = fields.get("Installation and Execution Summary", "")
    cmdline = fields.get("Workload Command Line Executable", "")
    metrics = fields.get("Metrics", "")
    framework = fields.get("Framework", "")
    raw_fmt = fields.get("Raw Output Format", "")
    raw_ex = fields.get("Raw Output Example", "")

    if "markdown table" in text and "parameter" in text and "cli flag" in text:
        lines = [
            "| Parameter | CLI Flag | Tested Values | Default | Description |",
            "| --- | --- | --- | --- | --- |",
        ]
        for name in parameters:
            tested, default = _profile_cell(profiles, name)
            lines.append(
                f"| {name} | `{_cli_flag(name)}` | {tested} | {default} | "
                f"From Parameter list; see Execution Description With Parameters. |"
            )
        if len(lines) == 2:
            return "No workbook parameters are populated for this workload."
        return "\n".join(lines)

    if "stride" in text or ("optional" in text and "matrix" in text):
        if not _is_matrix_workload(parameters):
            return ""
        example = parameters[0] if parameters else "N"
        return (
            f"### Derived quantities\n\n"
            f"Matrix extents come from the Parameters table. "
            f"Example: use the tested value of `{example}` from Profile Parameter Values. "
            f"Do not invent a leading dimension that the spec does not state."
        )

    if "2–4 sentences" in instruction or "2-4 sentences" in text or (
        "execution description" in text and "sentences" in text
    ):
        body = _sentences(exec_desc, 4)
        sweep = ", ".join(parameters[:8]) if parameters else "no swept parameters"
        return f"{body} Sweep dimensions: {sweep}."

    if "command line" in text or "invocation" in text:
        command = cmdline or "bash run_benchmark.sh --profile smoke --validate"
        return f"```bash\n{command}\n```"

    if (
        "raw output" in text
        and "numbered list" not in text
        and "pass condition" not in text
        and "bullet list" not in text
    ):
        bits = [item for item in (raw_fmt, raw_ex) if item and item not in EMPTY_VALUES]
        if not bits:
            return (
                "The collector writes `results/raw/<run>/raw_results.csv` and "
                "`raw_results.jsonl`. Column names come from the workload Metrics keys."
            )
        return "\n\n".join(bits)

    if "numbered list" in text and "metric" in text:
        items = _metrics_items(fields)
        lines = []
        for item in items:
            key_match = re.search(r"\(([^)]+)\)", item)
            key = key_match.group(1).split(";")[0].strip() if key_match else "metric"
            lines.append(f"- **{item.split('(')[0].strip() or item}** — stored as `{key}`.")
        return "\n".join(lines) if lines else metrics or "TBD — confirm against tool documentation"

    if "two-column" in text and "framework" in text:
        parts = [part.strip() for part in re.split(r"[,;/]", framework) if part.strip()]
        lines = ["| Component | Role |", "| --- | --- |"]
        for part in parts or ["TBD — confirm against tool documentation"]:
            lines.append(f"| {part} | From Framework / Installation and Execution Summary |")
        return "\n".join(lines)

    if "prerequisites" in text or "mermaid" in text:
        os_ver = fields.get("OS Version", "")
        vendor = fields.get("GPU Vendor", "")
        python = _python_requirement(fields.get("Python Version", ""))
        hf_note = ""
        if any(token in framework.lower() for token in ("vllm", "sglang", "diffusers", "bert", "rag")):
            hf_note = " Set HF_TOKEN when the model license requires a Hugging Face token."
        return (
            f"Prerequisites: {os_ver}; {vendor}; {python}; root or sudo for `setup.sh`. "
            f"Framework: {framework or 'see Installation and Execution Summary'}."
            f"{hf_note} "
            f"This is a host benchmark, not a laptop `pip install` project.\n\n"
            f"```mermaid\nflowchart LR\n  setup.sh --> run_benchmark.sh --> parse_results.py --> results/benchmark.db\n```"
        )

    if "two-column" in text and "hardware config" in text and "gpu" in text:
        return _hardware_table(
            fields,
            ["GPU Count", "GPU Model", "Architecture", "Compute Units", "HBM", "GFX Target", "Peak Power"],
        )

    if "two-column" in text and "hardware config" in text:
        return _hardware_table(
            fields,
            ["Provider", "Droplet", "instance", "vCPUs", "RAM", "Storage", "Network"],
        )

    if "quick-start" in text or "git clone" in text:
        org = "<org>"
        return (
            f"```bash\n"
            f"git clone https://github.com/{org}/{slug}.git\n"
            f"cd {slug}\n"
            f"sudo bash setup.sh --assume-yes\n"
            f"bash run_benchmark.sh --profile smoke --validate\n"
            f"```\n"
            f"Results are written to `results/benchmark.db` and `results/summary.json`."
        )

    if "local-only" in text or "does not support remote ssh" in text:
        return (
            "This workload is executed on the validation host after the repository is copied there. "
            "`setup.sh` and `run_benchmark.sh` do not open an outbound SSH session."
        )

    if "overview" in text or "3–5 sentences" in text or "3-5 sentences" in text:
        chunks = [
            fields.get("Execution Summary (Run and Measure)", ""),
            fields.get("Execution Summary (Run)", ""),
            exec_desc,
        ]
        return _sentences(" ".join(chunk for chunk in chunks if chunk), 5)

    if "pass condition" in text or "validation objective" in text:
        objective = fields.get("Validation Objective", "")
        items = _metrics_items(fields)
        lines = [f"- {objective}"] if objective else []
        lines.extend(f"- {item} is present and physically sensible." for item in items[:8])
        return "\n".join(lines) or "TBD — confirm against tool documentation"

    if "portable requirements" in text:
        return (
            f"- OS: {fields.get('OS Version', '')}\n"
            f"- GPU vendor: {fields.get('GPU Vendor', '')}\n"
            f"- Framework family: {framework or 'see Installation and Execution Summary'}\n"
            f"- Python: {fields.get('Python Version', '')}"
        )

    if "installation commands" in text or ("bash code block" in text and "install" in text):
        return f"```bash\nsudo bash setup.sh --assume-yes\n```\n\n{install or 'TBD — confirm against tool documentation'}"

    if "run_benchmark.sh --help" in text or ("bash code block" in text and "smoke" in text):
        return (
            "```bash\n"
            "bash run_benchmark.sh --help\n"
            "bash run_benchmark.sh --profile smoke --validate\n"
            "bash run_benchmark.sh --profile baseline --validate\n"
            "bash run_benchmark.sh --profile extended --validate\n"
            "```\n"
            "`run_benchmark.sh --help` prints usage and exits. "
            "The harness calls `scripts/ensure_setup.sh` when `.setup_state` is absent."
        )

    if "`runs`" in instruction or "schema tables" in text:
        return (
            "**`runs`** — one row per `run_benchmark.sh` execution: `run_id`, "
            f"`benchmark_id` ({workload or 'workload'}), `status`, `started_at`, `finished_at`.\n\n"
            "**`samples`** — one row per measured point with the Metrics keys as columns."
        )

    if "per-run artifact" in text:
        return (
            f"Each execution writes `results/raw/YYYYMMDD_HHMMSS_{repo_name}_<hostname>/` "
            "containing `run.log`, `commands_executed.sh`, `env_variables.txt`, "
            "`journal_warnings.txt`, `script.sh`, `raw_results.csv`, `raw_results.jsonl`, "
            "`hardware_info.txt`, `software_info.txt`, and `errors_info.txt`."
        )

    if "thresholds" in text or "baselines" in text:
        return (
            "Expected ranges and gates live in `config/benchmark_config.yaml` under "
            "`baselines:` or `thresholds:`. To update them, edit that file — never edit "
            "validation code directly."
        )

    if "failure-mode" in text:
        return (
            "**`setup.sh` missing collector**\n"
            "Create cannot finish without `scripts/collect_workload.py`.\n\n"
            "**`self_check` overlay rewritten**\n"
            "`Locked overlay rewritten` means the sibling file and the `sha256` in "
            "`results/overlay_lock.json` disagree. The repair is to make "
            "`implementation_components/<component-id>/files/<path>`, the sibling path, "
            "and that digest the same bytes, then recheck with "
            "`create_one_workload.py --validate-only`. Do not replace the overlay with a "
            "new collector, and do not regenerate a non-empty sibling.\n\n"
            "**Remote SSH drop during setup**\n"
            "Reconnect and resume `bash setup.sh --assume-yes`. Do not wipe `.venv` or `.cache`."
        )

    if "test file" in text:
        return (
            "- `tests/fixtures/.gitkeep`\n"
            "- `scripts/self_check_generated_repo.sh`\n"
            "- `scripts/check_github_publish_ready.sh`"
        )

    if "integrity" in text:
        return (
            "- `results/overlay_lock.json` matches overlay bytes\n"
            "- `scripts/collect_workload.py` is present\n"
            "- generated docs have no leftover `{{` or `[[GENERATE` tokens"
        )

    if "amd (primary)" in text or "gfx" in text:
        return (
            f"{fields.get('OS Version', '')} / {fields.get('GPU Vendor', '')} / "
            f"{framework or 'see Framework'}"
        )

    referenced = TOKEN_RE.findall(instruction)
    if referenced:
        bits = [fields.get(name.strip(), "") for name in referenced]
        bits = [bit for bit in bits if bit and bit not in EMPTY_VALUES]
        if bits:
            return " ".join(bits)
    if exec_desc:
        return _sentences(exec_desc, 3)
    return "TBD — confirm against tool documentation"


def _kernel_display(fields: dict[str, str]) -> str:
    """Prefer the profile kernel_version over the workbook Kernel Version string."""
    profiles = _profile_values(fields)
    raw = ""
    entry = profiles.get("kernel_version")
    if isinstance(entry, dict):
        raw = str(entry.get("smoke") or entry.get("baseline") or "")
    elif isinstance(profiles.get("smoke"), dict):
        raw = str(profiles["smoke"].get("kernel_version") or "")
    raw = raw.strip().strip("'\"")
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", raw):
        return f"kernel {raw}"
    return ""


def ci_fields(fields: dict[str, str]) -> dict[str, str]:
    """README tokens derived from config/ci_contract.yaml ({{CI Owner}}, {{CI Bundle Repo}}, ...)."""
    try:
        from ci_contract import ContractError, load_contract, workload_identity
    except ImportError:  # generated workload copy: the contract is generation-only
        return {}
    try:
        contract = load_contract()
        identity = workload_identity(fields, contract)
    except ContractError as exc:
        raise SystemExit(f"[FAIL] CI contract: {exc}") from exc
    return {
        "CI Owner": str(contract["github"]["owner"]),
        "CI GitHub Slug": identity["slug"],
        "CI Vendor": identity["vendor"],
        "CI OS Label": identity["os_label"],
        "CI OS Display": identity["os_display"],
        "CI Bundle Repo": identity["bundle"],
        "CI Shared Workflows Repo": str(contract["shared_workflows"]["repo"]),
        "CI Shared Workflows Ref": str(contract["shared_workflows"]["ref"]),
        "CI Install Root": str(contract["suite"]["install_root"]),
        "CI Suite Tools Repo": str(contract["suite"]["tools_repo"]),
        # The README's bundle example names the same workload in every bundle:
        # 107, 207, 307 or 407, matching this workload's hundreds digit.
        "CI Bundle Example Workload": f"{str(fields.get('Workload Number', '1')).strip()[:1] or '1'}07",
    }


def render_template(template_text: str, fields: dict[str, str]) -> str:
    text = HTML_COMMENT_RE.sub("", template_text)

    def replace_token(match: re.Match[str]) -> str:
        name = match.group(1).strip()
        if name == "Kernel Version":
            displayed = _kernel_display(fields)
            if displayed:
                return displayed
        if name not in fields:
            return match.group(0)
        return fields[name]

    text = TOKEN_RE.sub(replace_token, text)
    text = GENERATE_RE.sub(lambda match: expand_generate(match.group(0), fields), text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    leftovers = []
    if "{{" in text:
        leftovers.append("unresolved {{Field}} tokens")
    if "[[GENERATE" in text:
        leftovers.append("unresolved [[GENERATE]] blocks")
    if leftovers:
        raise SystemExit("[FAIL] fill_generated_docs.py leftover markers: " + ", ".join(leftovers))
    return text


def write_generation_report(repo_root: Path, fields: dict[str, str], template_root: Path) -> str:
    workload = fields.get("Workload Number", "")
    repo_name = fields.get("Repo Name", "")
    directory = generated_repo_directory_name(workload, repo_name)
    now = datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    resolution = repo_root / "results" / "component_resolution.json"
    components = []
    if resolution.is_file():
        payload = json.loads(resolution.read_text(encoding="utf-8"))
        components = [str(item.get("component_id") or "") for item in payload.get("discovered") or []]
    return (
        f"# GENERATION_REPORT.md\n\n"
        f"- Workload Number: {workload}\n"
        f"- Workbook Repo Name: {repo_name}\n"
        f"- Local directory / GitHub slug: `{directory}`\n"
        f"- generation_started_at: pending\n"
        f"- generation_finished_at: pending\n"
        f"- generation_duration_seconds: 0\n"
        f"- Generated at (UTC): {now}\n"
        f"- Template: `{template_root}`\n"
        f"- Official docs: `scripts/fill_generated_docs.py`\n"
        f"- Collector present: "
        f"{'yes' if (repo_root / 'scripts' / 'collect_workload.py').is_file() else 'NO'}\n"
        f"- Resolved components: {', '.join(components) or '(none)'}\n"
    )


def fill_generated_docs(repo_root: Path, template_root: Path | None = None) -> int:
    repo = Path(repo_root).resolve()
    spec = repo / "benchmark_specification.json"
    if not spec.is_file():
        raise SystemExit(f"[FAIL] missing {spec}")
    fields = load_fields(spec)
    fields.update(ci_fields(fields))
    template_dir = Path(template_root).resolve() if template_root else None
    if template_dir is None:
        for candidate in (repo / "templates", Path(__file__).resolve().parents[1] / "templates"):
            if (candidate / "PRD_TEMPLATE.md").is_file():
                template_dir = candidate
                break
    if template_dir is None:
        raise SystemExit("[FAIL] templates/PRD_TEMPLATE.md not found")
    mapping = {
        "PRD.md": "PRD_TEMPLATE.md",
        "SPEC.md": "SPEC_TEMPLATE.md",
        "README.md": "README_TEMPLATE.md",
    }
    for dest_name, source_name in mapping.items():
        source = template_dir / source_name
        if not source.is_file():
            raise SystemExit(f"[FAIL] missing template {source}")
        write_lf(repo / dest_name, render_template(source.read_text(encoding="utf-8"), fields))
        print(f"[PASS] wrote {dest_name}")
    report = write_generation_report(repo, fields, template_dir)
    write_lf(repo / "GENERATION_REPORT.md", report)
    print("[PASS] wrote GENERATION_REPORT.md")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Fill official generated-repo documents")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--template-root", default="")
    args = parser.parse_args()
    template = Path(args.template_root) / "templates" if args.template_root else None
    return fill_generated_docs(Path(args.repo_root), template)


if __name__ == "__main__":
    raise SystemExit(main())
