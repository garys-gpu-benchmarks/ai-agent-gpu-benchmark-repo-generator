#!/usr/bin/env python3
# File: scripts/readme_sections.py
# Description: Renders the data-driven sections of the generated README.md.
#   templates/README_TEMPLATE.md names each section with a
#   [[GENERATE: readme.<section>]] marker; fill_generated_docs.py calls
#   render_section() for those markers. Wording that is the same for every
#   workload stays in the template. Everything that depends on the workbook
#   row (benchmark_specification.json) or on the generated tree is built here.
#
#   Sources, per section:
#     title, intro           Workload Name, Main Goal, Execution Domain, bundle identity
#     quickstart_notes       Execution Domain (LLM Serving), Framework (gated Mistral weights)
#     parameters             Parameter_01..20 + Profile Parameter Values, through
#                            workload_option_help.py, the same source as run_benchmark.sh --help
#     metrics                Metrics
#     notes                  Known Runtime Constraints (<=35 Words Each)
#     requirements           OS Version, GPU Vendor, GPU Model, GPU Runtime Version, Python Version, Framework
#     other_bundles          config/ci_contract.yaml suite bundles
#     troubleshooting        setup skeleton (ROCm reboot), Framework (gated Mistral weights)
#     layout                 the generated repository tree at fill time
from __future__ import annotations

import json
import re
from pathlib import Path

EMPTY = {"", "—", "-", "--", "None", "none", "TBD", "n/a", "N/A"}

# Framework entries every workload has. They are not worth listing as requirements.
_COMMON_FRAMEWORK = {"bash", "sqlite", "python", "pyyaml"}

# Main Goal starts with an imperative verb ("Measure ...", "Analyze ...").
_GOAL_VERBS = {
    "measure": "Measures",
    "analyze": "Analyzes",
    "verify": "Verifies",
    "validate": "Validates",
    "check": "Checks",
    "test": "Tests",
    "stress": "Stresses",
    "compare": "Compares",
    "profile": "Profiles",
    "evaluate": "Evaluates",
    "exercise": "Exercises",
    "capture": "Captures",
    "detect": "Detects",
}

# Bundle key from config/ci_contract.yaml -> (display name, workload range).
_BUNDLE_DISPLAY = {
    "amd-ubu2404": ("AMD 24.04", "101–132"),
    "nvidia-ubu2404": ("NVIDIA 24.04", "201–232"),
    "amd-ubu2604": ("AMD 26.04", "301–332"),
    "nvidia-ubu2604": ("NVIDIA 26.04", "401–432"),
}

GATED_MODEL = "mistralai/Mistral-7B-v0.3"


def _value(fields: dict[str, str], name: str) -> str:
    text = str(fields.get(name, "") or "").strip()
    return "" if text in EMPTY else text


def _cell(text: str) -> str:
    """Make text safe inside one Markdown table cell."""
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def _sentence(text: str) -> str:
    text = text.strip()
    if text and text[-1] not in ".!?":
        text += "."
    return text


def _is_cpu_only(fields: dict[str, str]) -> bool:
    return _value(fields, "Execution Domain") == "CPU / System"


def _is_llm_serving(fields: dict[str, str]) -> bool:
    return _value(fields, "Execution Domain") == "LLM Serving"


def _needs_gated_model(fields: dict[str, str]) -> bool:
    return "mistral" in _value(fields, "Framework").lower()


def _uses_rocm_reboot_setup(fields: dict[str, str]) -> bool:
    try:
        from setup_bundle import ROCM, setup_bundle
    except ImportError:
        return False
    try:
        return setup_bundle(fields) == ROCM
    except Exception:  # an unmapped domain/vendor is reported by init, not here
        return False


# --------------------------------------------------------------------------- title / intro


def title(fields: dict[str, str]) -> str:
    name = _value(fields, "Workload Name") or "Workload"
    if "benchmark" in name.lower():
        return f"# {name}"
    return f"# {name} Benchmark"


def _goal_sentence(goal: str) -> str:
    words = goal.split(maxsplit=1)
    if not words:
        return ""
    verb = _GOAL_VERBS.get(words[0].lower())
    if verb:
        goal = verb + (" " + words[1] if len(words) > 1 else "")
    return _sentence(goal)


def intro(fields: dict[str, str]) -> str:
    parts = []
    goal = _goal_sentence(_value(fields, "Main Goal"))
    if goal:
        parts.append(goal)
    number = _value(fields, "Workload Number")
    vendor = _value(fields, "GPU Vendor")
    os_display = _value(fields, "CI OS Display") or _value(fields, "OS Version")
    if number:
        parts.append(f"Workload {number} of the {vendor} {os_display} bundle.".replace("  ", " "))
    if _is_cpu_only(fields):
        parts.append("This is a CPU benchmark: no GPU is used.")
    return " ".join(parts)


def quickstart_notes(fields: dict[str, str]) -> str:
    notes = []
    if _is_llm_serving(fields):
        notes.append(
            "For this LLM serving workload, `--baseline` and `--extended` start the real model server, "
            "wait for it to be ready, run the client, and stop the server."
        )
    if _needs_gated_model(fields):
        notes.append(
            f"The model `{GATED_MODEL}` may be gated on Hugging Face. "
            "If its download is refused, set `HF_TOKEN` (see [Troubleshooting](#troubleshooting))."
        )
    return "\n\n".join(notes)


# --------------------------------------------------------------------------- parameters


_LONG_VALUE = 40


def _short_value(value: str) -> str:
    if len(value) <= _LONG_VALUE:
        return value
    items = [item for item in value.split(",") if item.strip()]
    return f"{len(items)} items" if len(items) > 1 else "see config"


def parameters(fields: dict[str, str]) -> str:
    import workload_option_help as woh

    names = woh._parameters(fields)
    if not names:
        return (
            "This workload has no tunable parameters. Pick a profile with `--smoke` (default), "
            "`--baseline` or `--extended`:\n\n"
            "```bash\nbash run_benchmark.sh --baseline\nbash run_benchmark.sh --help        # every option\n```"
        )
    values = woh._profile_values(fields)
    lines = [
        "| Parameter | Flag | smoke | baseline | extended |",
        "|---|---|---|---|---|",
    ]
    shortened = False
    for name in names:
        triple = [woh._display(item) or "—" for item in woh._profile_triple(values, name)]
        if any(len(item) > _LONG_VALUE for item in triple):
            triple = [_short_value(item) for item in triple]
            shortened = True
        lines.append(
            f"| `{name}` | `{woh._flag_of(name)}` | {_cell(triple[0])} | {_cell(triple[1])} | "
            f"{_cell(triple[2])} |"
        )
    example = woh.override_example(fields) or "bash run_benchmark.sh --baseline"
    footnote = (
        "\n\nLong list values are shown as item counts; the full lists are in `config/benchmark_config.yaml`."
        if shortened
        else ""
    )
    return (
        "\n".join(lines)
        + footnote
        + "\n\nPick a profile with `--smoke` (default), `--baseline` or `--extended`. "
        "Any flag in the table overrides that profile's value:\n\n"
        f"```bash\n{example}\nbash run_benchmark.sh --help        # every option\n```\n\n"
        "Profile values live in `config/benchmark_config.yaml`."
    )


# --------------------------------------------------------------------------- metrics


_METRIC_RE = re.compile(r"^#\s*(\d+)\s*:\s*(.*)\(([^()]+)\)\s*$")
_METRIC_INNER_KEY_RE = re.compile(r"^#\s*(\d+)\s*:\s*(.*?)\s*\(([a-z][a-z0-9_]*)\)(.*)$")


def _metric_rows(fields: dict[str, str]) -> list[tuple[str, str, str]]:
    text = _value(fields, "Metrics")
    rows = []
    for item in re.split(r";\s*(?=#\s*\d+\s*:)", text):
        item = item.strip().rstrip(";").strip()
        if not item:
            continue
        match = _METRIC_RE.match(item)
        inner = _METRIC_INNER_KEY_RE.match(item)
        if match:
            rows.append((match.group(1), match.group(2).strip().rstrip(","), match.group(3).strip()))
        elif inner:  # "#4: Label (key), more label text"
            label = (inner.group(2).strip() + inner.group(4)).strip().rstrip(",")
            rows.append((inner.group(1), label, inner.group(3)))
        else:
            rows.append((str(len(rows) + 1), item, ""))
    return rows


def metrics(fields: dict[str, str]) -> str:
    rows = _metric_rows(fields)
    if not rows:
        return "This workload publishes no numbered metrics."
    lines = ["| # | Metric | Key |", "|---|---|---|"]
    for number, label, key in rows:
        lines.append(f"| {number} | {_cell(label)} | {f'`{key}`' if key else '—'} |")
    return "\n".join(lines)


def notes(fields: dict[str, str]) -> str:
    lines = [
        "- The smoke profile is a quick check with reduced sizes and iteration counts. "
        "Use `--baseline` or `--extended` for representative numbers."
    ]
    constraints = _value(fields, "Known Runtime Constraints (<=35 Words Each)")
    for sentence in re.split(r"(?<=[.!?])\s+", constraints):
        sentence = sentence.strip()
        if sentence:
            lines.append(f"- {_sentence(sentence)}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- requirements


def _python_display(text: str) -> str:
    match = re.search(r"Python\s+(\d+\.\d+)", text)
    if not match:
        return text
    return f"Python {match.group(1)}" + (" (uv-managed)" if "uv" in text.lower() else "")


def _runtime_display(text: str) -> str:
    if not text or text.lower().startswith("n/a"):
        return ""
    return re.split(r"\s+\(|\.\s", text, maxsplit=1)[0].strip().rstrip(".")


def requirements(fields: dict[str, str]) -> str:
    bullets = [f"- {_value(fields, 'OS Version') or 'Ubuntu'}, root or sudo for `setup.sh`"]
    if not _is_cpu_only(fields):
        vendor = _value(fields, "GPU Vendor")
        runtime = _runtime_display(
            _value(fields, "GPU Runtime Version")
            or _value(fields, "GPU Runtime Version (was ROCm Version)")
            or _value(fields, "ROCm Version")
        )
        model = _value(fields, "GPU Model")
        gpu = f"- {vendor} GPU" + (f" with {runtime}" if runtime else "")
        if model:
            gpu += f" (validated on {model})"
        bullets.append(gpu)
    tools = []
    for part in re.split(r",\s*", _value(fields, "Framework")):
        part = re.sub(r"\s*\(not C\+\+\)", "", part).strip()  # workbook note, not a requirement
        if part and part.lower() not in _COMMON_FRAMEWORK and part not in tools:
            tools.append(part)
    python = _python_display(_value(fields, "Python Version"))
    software = ", ".join(tools + ([python] if python else []))
    if software:
        bullets.append(
            f"- {software}. `setup.sh` installs what is missing; Python packages go into a repo-local `.venv`."
        )
    if _needs_gated_model(fields):
        bullets.append(f"- A Hugging Face token with access to `{GATED_MODEL}`")
    return "\n".join(bullets)


# --------------------------------------------------------------------------- bundles


def other_bundles(fields: dict[str, str]) -> str:
    try:
        from ci_contract import load_contract
        contract = load_contract()
    except Exception:
        return ""
    owner = str(contract["github"]["owner"])
    own = _value(fields, "CI Bundle Repo")
    links = []
    for key, repo in (contract.get("suite", {}).get("bundles") or {}).items():
        if repo == own:
            continue
        display, numbers = _BUNDLE_DISPLAY.get(key, (key, ""))
        suffix = f" ({numbers})" if numbers else ""
        links.append(f"[{display}](https://github.com/{owner}/{repo}){suffix}")
    return ("Other platforms: " + ", ".join(links) + ".") if links else ""


# --------------------------------------------------------------------------- troubleshooting


def troubleshooting(fields: dict[str, str]) -> str:
    entries = []
    if _uses_rocm_reboot_setup(fields):
        entries.append(
            "- **The SSH session closed during setup:** the first AMD workload on a fresh host may reboot once "
            "to load the AMD GPU driver. Setup prints a 30-second warning first and resumes by itself after boot. "
            "SSH back in and run `tail -f results/reboot_resume.log`; when it prints `SETUP COMPLETE`, run your "
            "command again. Do not start `setup.sh` again while it is resuming."
        )
        entries.append(
            "- **SSH dropped for another reason:** reconnect and run `sudo bash setup.sh --assume-yes` again. "
            "It resumes; do not delete `.venv` or `.cache`."
        )
    else:
        entries.append(
            "- **SSH dropped during setup:** reconnect and run `sudo bash setup.sh --assume-yes` again. "
            "It resumes; do not delete `.venv` or `.cache`."
        )
    if _needs_gated_model(fields):
        entries.append(
            f"- **Model download refused (401 or 403):** `{GATED_MODEL}` may be gated. Accept its license on "
            "Hugging Face, then `export HF_TOKEN=<token>` and run setup with `sudo -E bash setup.sh --assume-yes` "
            "so the token reaches it."
        )
    entries.append(
        "- **A metric reads `na`:** the run could not measure it on this host. The reason is in the run's "
        "`metrics_summary.txt` and `errors_info.txt`; see also [Notes](#notes)."
    )
    return "\n".join(entries)


# --------------------------------------------------------------------------- layout


def layout(fields: dict[str, str], repo: Path | None) -> str:
    def exists(rel: str) -> bool:
        return repo is None or (repo / rel).exists()

    src_label = "src/"
    if repo is not None and (repo / "src").is_dir():
        files = sorted(p.name for p in (repo / "src").iterdir() if p.is_file() and not p.name.startswith("."))
        if len(files) == 1:
            src_label = f"src/{files[0]}"
    entries = [
        ("setup.sh", "installs dependencies and builds the benchmark", True),
        ("run_benchmark.sh", "runs one profile, parses, validates", True),
        ("show_metrics.sh", "prints this workload's ledger rows", True),
        ("list_runs.sh", "prints every run in the ledger", True),
        ("SPEC.md", "engineering specification", exists("SPEC.md")),
        ("benchmark_specification.json", "workload definition", True),
        ("config/", "profile values and thresholds", exists("config")),
        (src_label, "benchmark source", exists("src")),
        ("scripts/", "build, collect, parse, validate", exists("scripts")),
        ("docs/", "PRD and contracts" if exists("docs/PRD.md") else "contracts", exists("docs")),
        ("tests/", "", exists("tests")),
        ("results/", "run outputs", True),
        ("LICENSE", "", exists("LICENSE")),
    ]
    shown = [(name, note) for name, note, keep in entries if keep]
    width = max(len(name) for name, _ in shown) + 6
    lines = [".", *(
        f"{'└──' if index == len(shown) - 1 else '├──'} {name}".ljust(width) + (f"# {note}" if note else "")
        for index, (name, note) in enumerate(shown)
    )]
    return "```text\n" + "\n".join(line.rstrip() for line in lines) + "\n```"


# --------------------------------------------------------------------------- dispatch


SECTIONS = {
    "title": title,
    "intro": intro,
    "quickstart_notes": quickstart_notes,
    "parameters": parameters,
    "metrics": metrics,
    "notes": notes,
    "requirements": requirements,
    "other_bundles": other_bundles,
    "troubleshooting": troubleshooting,
}

MARKER_RE = re.compile(r"^\[\[GENERATE:\s*readme\.([a-z_]+)\s*\]\]$")


def render_section(name: str, fields: dict[str, str], repo: Path | None = None) -> str:
    if name == "layout":
        return layout(fields, repo)
    if name not in SECTIONS:
        raise SystemExit(f"[FAIL] README_TEMPLATE.md names unknown section readme.{name}")
    return SECTIONS[name](fields)


if __name__ == "__main__":  # quick manual preview: python3 scripts/readme_sections.py <repo>/benchmark_specification.json
    import sys

    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    spec_fields = {str(item.get("field_name")): str(item.get("value") or "") for item in data if isinstance(item, dict)}
    for section in [*SECTIONS, "layout"]:
        print(f"--- {section}\n{render_section(section, spec_fields, Path(sys.argv[1]).parent)}\n")
