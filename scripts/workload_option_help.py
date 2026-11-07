#!/usr/bin/env python3
"""Help lines for run_benchmark.sh workload flags.

Each line is the flag, a short description, and the smoke, baseline, and
extended values. A value shared by all three profiles is printed once.
Profile notes are omitted.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import yaml

from generate_workload_parameters import extract_meaning

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "config" / "workload_parameters.yaml"
HELP_COLUMN = 32
EMPTY = {"", "—", "-", "--", "None", "none", "TBD", "n/a", "N/A"}
PLACEHOLDER_MEANING = "Defined by the workload description"


def _parameters(fields: dict[str, str]) -> list[str]:
    names = []
    for index in range(1, 21):
        value = str(fields.get(f"Parameter_{index:02d}", "") or "").strip()
        if value and value not in EMPTY:
            names.append(value)
    return names


def _flag_of(name: str) -> str:
    return "--" + name.replace("_", "-")


def _profile_values(fields: dict[str, str]) -> dict:
    raw = fields.get("Profile Parameter Values", "")
    if not raw or raw in EMPTY:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _profile_triple(values: dict, name: str) -> tuple[str, str, str]:
    smoke = baseline = extended = ""
    if all(key in values for key in ("smoke", "baseline", "extended")) and isinstance(values.get("smoke"), dict):
        smoke = values["smoke"].get(name, "")
        baseline = values["baseline"].get(name, "")
        extended = values["extended"].get(name, "")
    elif isinstance(values.get(name), dict):
        item = values[name]
        smoke = item.get("smoke", "")
        baseline = item.get("baseline", "")
        extended = item.get("extended", "")
    return smoke, baseline, extended


def _display(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, list):
        return ",".join(item for item in (_display(part) for part in value) if item)
    text = str(value).strip()
    return "" if text in EMPTY else text


def _profile_phrase(smoke, baseline, extended) -> str:
    parts = (
        ("smoke", _display(smoke)),
        ("baseline", _display(baseline)),
        ("extended", _display(extended)),
    )
    present = [(label, value) for label, value in parts if value]
    if not present:
        return ""
    if len(present) == 3 and present[0][1] == present[1][1] == present[2][1]:
        return f"smoke/baseline/extended: {present[0][1]}"
    return ", ".join(f"{label} {value}" for label, value in present)


@lru_cache(maxsize=1)
def _catalog() -> dict:
    if not CATALOG_PATH.is_file():
        return {}
    loaded = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8")) or {}
    parameters = loaded.get("parameters") if isinstance(loaded, dict) else {}
    return parameters if isinstance(parameters, dict) else {}


def _placeholder(data_type: str) -> str:
    kind = (data_type or "").strip().lower()
    if kind in {"integer", "number"}:
        return "<n>"
    if kind == "boolean":
        return "<true|false>"
    return "<value>"


def _description(name: str, execution: str) -> tuple[str, str]:
    entry = _catalog().get(name) or {}
    description = str(entry.get("description") or "").strip().rstrip(".")
    meaning = extract_meaning(execution, name).strip().rstrip(".")
    if description:
        text = description
    elif meaning and meaning != PLACEHOLDER_MEANING:
        text = meaning
    else:
        text = name.replace("_", " ")
    return text, _placeholder(str(entry.get("data_type") or ""))


def _line(flag: str, placeholder: str, description: str, phrase: str) -> str:
    left = f"  {flag} {placeholder}"
    gap = "  " if len(left) >= HELP_COLUMN else " " * (HELP_COLUMN - len(left))
    detail = f"{description} ({phrase})" if phrase else description
    return f"{left}{gap}{detail}"


# Knobs a reader can override without learning the workload. Earlier names win
# when several of them produce a small example value.
_PREFERRED_EXAMPLE = (
    "num_threads",
    "batch_size",
    "num_jobs",
    "num_cpus",
    "concurrency",
    "max_concurrency",
    "repetitions",
    "duration",
    "time",
    "runtime",
    "num_prompts",
    "num_images",
    "query_count",
    "num_iterations",
    "image_size",
    "sequence_len",
    "input_len",
    "output_len",
    "chunk_size",
    "M",
    "problem_size_N",
    "array_size",
    "parallel_streams",
    "block_size",
)
# A large count is easier to understand as a small stand-in than as half of 30800.
_TINY_EXAMPLE = {
    "num_iterations",
    "duration",
    "time",
    "runtime",
    "num_prompts",
    "num_images",
    "query_count",
    "num_updates",
    "warmup_iters",
    "output_len",
    "repetitions",
}
# Identity and placement checks do not show what the benchmark measures.
_SKIP_EXAMPLE = {
    "kernel_version",
    "required_packages",
    "driver_version",
    "nvidia_driver_version",
    "cuda_version",
    "rocm_version",
    "model_name",
    "filename",
    "event_list",
    "workload_commands",
    "prompt_source",
    "corpus_dataset",
    "embedding_model",
    "llm_model",
    "reranker_model",
    "thread_affinity",
    "device_id",
    "seed",
    "numa_node",
    "port",
    "source_numa_node",
    "target_numa_node",
    "stride",
    "step_factor",
    "alpha",
    "beta",
    "norm_check",
    "poll_interval",
    "group_count",
    "bandwidth_limit",
    "omit_initial_seconds",
    "warmup_duration_sec",
    "warmup_duration_us",
}
_PARAMETERS_BLOCK = re.compile(
    r"Parameters(?: \(override the profile's value\))?:\n(?:[ \t].*\n)*(?:\n)?"
)
_OVERRIDE_EXAMPLE = re.compile(r"\n  bash run_benchmark\.sh --baseline --\S[^\n]*")
PARAMETERS_HEADING = "Parameters (override the profile's value):"


def option_help_lines(fields: dict[str, str]) -> list[str]:
    """One help line per Parameter_01..Parameter_20."""
    values = _profile_values(fields)
    execution = str(fields.get("Execution Description With Parameters", "") or "")
    lines = []
    for name in _parameters(fields):
        description, placeholder = _description(name, execution)
        phrase = _profile_phrase(*_profile_triple(values, name))
        lines.append(_line(_flag_of(name), placeholder, description, phrase))
    return lines


def _example_number(name: str, baseline: int) -> int:
    if baseline <= 0:
        return 1
    if baseline == 1:
        return 2
    if baseline <= 64:
        half = baseline // 2
        return half if half >= 1 else baseline - 1
    if name in _TINY_EXAMPLE:
        return 4 if baseline == 8 else 8
    half = baseline // 2
    return half if half != baseline else baseline - 1


def override_example(fields: dict[str, str]) -> str | None:
    """One `--baseline --flag value` line, or None when the workload has no parameter to override."""
    names = _parameters(fields)
    if not names:
        return None
    values = _profile_values(fields)
    scored: list[tuple[int, int, str, str]] = []
    boolean_flip: tuple[str, str] | None = None
    for index, name in enumerate(names):
        if name in _SKIP_EXAMPLE:
            continue
        _smoke, baseline, _extended = _profile_triple(values, name)
        shown = _display(baseline)
        if not shown or any(character.isspace() for character in shown):
            continue
        if shown in {"true", "false"}:
            if boolean_flip is None:
                flipped = "false" if shown == "true" else "true"
                boolean_flip = (name, flipped)
            continue
        if not re.fullmatch(r"-?\d+", shown):
            continue
        number = int(shown)
        chosen = _example_number(name, number)
        if chosen == number:
            continue
        preference = _PREFERRED_EXAMPLE.index(name) if name in _PREFERRED_EXAMPLE else 100 + index
        preferred_rank = 0 if name in _PREFERRED_EXAMPLE else 1
        small = 0 if abs(chosen) <= 32 else 1
        scored.append((preferred_rank, small, abs(number), preference, name, str(chosen)))
    if scored:
        scored.sort()
        _preferred, _small, _baseline, _preference, name, value = scored[0]
    elif boolean_flip is not None:
        name, value = boolean_flip
    else:
        return None
    return f"bash run_benchmark.sh --baseline {_flag_of(name)} {value}"


HELP_HEADER_FIELDS = (
    ("Workload Name:", "Workload Name"),
    ("Main Goal:", "Main Goal"),
    ("Command Tools Executed:", "Command Tools Executed"),
)
HELP_HEADER_LABEL_WIDTH = 24
HELP_HEADER_WIDTH = 100
# The help page starts with one blank line before "Usage:".
_USAGE_WITHOUT_BLANK = re.compile(r"(cat <<'USAGE'\n)(Usage: bash run_benchmark\.sh \[OPTIONS\])")
_HELP_HEADER_SLOT = re.compile(
    r"(Usage: bash run_benchmark\.sh \[OPTIONS\]\n\n)(.*?)(\nProfiles \(default)", re.DOTALL
)


def help_header_lines(fields: dict[str, str]) -> list[str]:
    """Workload Name, Main Goal, and Command Tools Executed from the workbook row.

    Labels sit in a 24-column field. Long values wrap at 100 columns with the
    continuation lines under the value. Each value ends with a period.
    """
    import textwrap

    lines: list[str] = []
    for label, field in HELP_HEADER_FIELDS:
        value = " ".join(str(fields.get(field, "") or "").split())
        if value in EMPTY:
            continue
        if not value.endswith((".", "!", "?")):
            value += "."
        wrapped = textwrap.wrap(
            value,
            width=HELP_HEADER_WIDTH - HELP_HEADER_LABEL_WIDTH,
            break_on_hyphens=False,
            break_long_words=False,
        )
        lines.append(f"{label:<{HELP_HEADER_LABEL_WIDTH}}{wrapped[0]}")
        lines.extend(" " * HELP_HEADER_LABEL_WIDTH + part for part in wrapped[1:])
    return lines


def replace_help_header(text: str, fields: dict[str, str]) -> str:
    """Put the workbook header block between the Usage line and Profiles in usage(),
    and start the help page with a blank line before "Usage:"."""
    text = _USAGE_WITHOUT_BLANK.sub(lambda m: m.group(1) + "\n" + m.group(2), text, count=1)
    lines = help_header_lines(fields)
    if not lines or not _HELP_HEADER_SLOT.search(text):
        return text
    block = "\n".join(lines) + "\n"
    return _HELP_HEADER_SLOT.sub(lambda m: m.group(1) + block + m.group(3), text, count=1)


def replace_workload_options(text: str, lines: list[str]) -> str:
    """Replace the usage() Parameters block. Leave runners without that section unchanged."""
    if not _PARAMETERS_BLOCK.search(text):
        return text
    if not lines:
        return _PARAMETERS_BLOCK.sub("", text, count=1)
    block = f"{PARAMETERS_HEADING}\n" + "\n".join(lines) + "\n\n"
    return _PARAMETERS_BLOCK.sub(block, text, count=1)


def replace_override_example(text: str, example: str | None) -> str:
    """Put the workload's fourth example on the help page. Drop it when there is no parameter to override."""
    if example:
        line = f"\n  {example}"
        if _OVERRIDE_EXAMPLE.search(text):
            return _OVERRIDE_EXAMPLE.sub(line, text, count=1)
        needle = "\n  bash run_benchmark.sh --extended"
        if needle in text:
            return text.replace(needle, needle + line, 1)
        return text
    return _OVERRIDE_EXAMPLE.sub("", text, count=1)
