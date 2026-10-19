#!/usr/bin/env python3
"""Print numbered end-of-run metric lines from the workload definition.

2026-09-06 rewrite: the previous version had two independent bugs that,
combined, silently mislabeled the end-of-run summary for the large majority
of workloads (only 3 of 64 came out fully correct):

1. The "Metrics" spec text was split into per-metric fragments on every
   semicolon/comma, including ones that appear *inside* a metric's own
   parenthetical aside (e.g. "(thermal_throttle_event_count; often 0)").
   That fragmented a single 5-metric spec into 6-8 bogus pieces with
   duplicate/skipped numbers.
2. When a metric's slugified description didn't exactly match a key in the
   run's summary.json (the overwhelmingly common case, since collectors use
   short internal names like "tier"/"kind"/"step" while descriptions are
   long human-readable phrases), the code silently fell back to grabbing
   the Nth value *by raw dict position* and printing it next to the wrong
   label -- with no indication anything had gone wrong.

This version: (a) only splits at top-level punctuation (paren-aware), so an
aside inside parens never fragments the metric list; (b) tries several
honest, name-based ways to find the real value for each metric before ever
falling back to position, and even then only when it is unambiguous (the
count of still-unresolved definitions exactly equals the count of
still-unused numeric values). The name-based candidates tried, in order:

  - every key candidate named in the metric's own first top-level
    parenthetical, including slash-separated alternatives inside it
    (e.g. "(a / b)" tries both "a" and "b");
  - the full-phrase slug (legacy behavior);
  - the slug of just the text before the first parenthetical;
  - when that leading phrase itself ends in a slash-separated list sharing
    a common prefix (e.g. "IOPS p50/p95/p99"), each expansion in turn
    ("IOPS p50", "IOPS p95", "IOPS p99");
  - a couple of literal-constant idioms the spec text uses ("always 0",
    "hardcoded 1.0");
  - finally, for any metric still unresolved, a unique-prefix match tried
    against *every* candidate generated for it (a candidate slug that is an
    unambiguous prefix of exactly one still-unused real key, e.g.
    "local_numa_node_latency" -> "local_numa_node_latency_nsec").

Header aliases (for example CSV "GB/s" -> memory_bandwidth_gb_s) are applied
by the generated parser before this resolver runs. Resolution order is:
exact normalized name, parenthetical key, literal constant, unique prefix
plus "_", then NOT FOUND. A column is never selected because its name is a
substring of the metric name. That containment match reported MIOpen batch
size n as memory_bandwidth_gb_s.

A metric that cannot be resolved, or whose value is blank, is omitted.
A spec that names p50, p95, and p99 together prints the p50 value only.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from metric_contract import (
    annotate_metrics,
    apply_storage_aliases,
    is_blank,
    is_explicit_na,
    split_percentile_keys,
    units_compatible,
    unmash_p50_key,
)


def _mask_parens(text: str) -> str:
    """Replace ';' and ',' that appear *inside* parentheses with sentinel
    tokens so a later naive split on ';'/',' never treats them as a
    metric-boundary. Restored by _unmask after splitting."""
    out = []
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if depth > 0 and ch == ";":
            out.append("\x00SEMI\x00")
            continue
        if depth > 0 and ch == ",":
            out.append("\x00COMMA\x00")
            continue
        out.append(ch)
    return "".join(out)


def _unmask(text: str) -> str:
    return text.replace("\x00SEMI\x00", ";").replace("\x00COMMA\x00", ",")


def metric_items(definition: Path) -> list[tuple[str, str]]:
    fields = json.loads(definition.read_text(encoding="utf-8"))
    metrics = next(
        str(item.get("value", ""))
        for item in fields
        if item.get("field_name") == "Metrics"
    )
    masked = _mask_parens(metrics)
    parts = [_unmask(p) for p in re.split(r";\s*|,\s*(?=#\d)|\n", masked)]
    result: list[tuple[str, str]] = []
    for index, part in enumerate(parts, start=1):
        text = part.strip()
        if not text:
            continue
        match = re.match(r"^#(\d+)\s*:\s*(.*)$", text)
        number = match.group(1) if match else str(index)
        description = match.group(2).strip() if match else text
        result.append((number, description))
    return result


def column_name(description: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", description).strip("_").lower() or "value"


def normalize_key(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", str(name)).strip("_").lower()


def extract_paren_keys(description: str) -> list[str]:
    """Pull literal key candidates out of a metric description's
    top-level parentheticals, e.g. 'Peak CPU package temperature
    (peak_cpu_temp_c)' -> ['peak_cpu_temp_c']. Stops at the first
    explanatory aside inside the parens so '(gups)' -> ['gups'] but
    '(rocblas-Gflops from 2*M*N*K/elapsed)' -> ['rocblas-Gflops'] and
    '(ttft_ms; estimated if non-streaming)' -> ['ttft_ms']. When the
    surviving text is itself a slash-separated list of alternative names,
    e.g. '(end_to_end_latency_ms / prompt_response_end_to_end_latency_msec)'
    or '(sustained_decode_throughput_under_cache_pressure_tokens_sec /
    output_token_throughput)', each alternative is returned as its own
    candidate so callers can try them in turn. As a lower-priority pool,
    also yields every comma/semicolon-separated token found anywhere in the
    full parenthetical (not just the first, cut-off fragment), so an aside
    like '(collector copies the same aggregate IOPS into iops_p50,
    iops_p95, and iops_p99)' still surfaces 'iops_p50', 'iops_p95', and
    'iops_p99' as candidates even though the primary cut lands on
    non-key prose."""
    inners = re.findall(r"\(([^()]*)\)", description)
    if not inners:
        return []
    candidates: list[str] = []
    for inner in inners:
        cut = re.split(r";|,| from | when | if | equals | still |=", inner, maxsplit=1)
        candidate = cut[0].strip()
        primary: list[str] = []
        if candidate:
            if "/" in candidate:
                primary = [p.strip() for p in candidate.split("/") if p.strip()]
            else:
                primary = [candidate]
        candidates.extend(item for item in primary if item not in candidates)
        for token in re.split(r"[;,]", inner):
            token = re.sub(r"^\s*(and|or)\s+", "", token.strip(), flags=re.IGNORECASE)
            token = re.split(r" from | when | if | equals | still |=", token, maxsplit=1)[0].strip()
            if token and token not in candidates:
                candidates.append(token)
    return candidates


def phrase_before_paren(description: str) -> str | None:
    """The human-readable phrase preceding the first parenthetical, e.g.
    'TLB miss rate (always 0)' -> 'TLB miss rate' -> slug 'tlb_miss_rate',
    which is often the collector's real column name even when the
    parenthetical itself holds an aside rather than a key."""
    idx = description.find("(")
    if idx <= 0:
        return None
    return description[:idx].strip() or None


def distribute_slash_list(phrase: str) -> list[str]:
    """A phrase like 'IOPS p50/p95/p99' names three related metrics that
    share a common leading label, one per slash-separated token. Expand it
    into ['IOPS p50', 'IOPS p95', 'IOPS p99'] so each can be tried as its
    own candidate name. Only fires when there are at least two tokens after
    the last space before the slash list and every token looks like a short
    identifier fragment (not a full alternate phrase, which is already
    handled by extract_paren_keys' own '/' split)."""
    match = re.match(r"^(.*\s)?([A-Za-z0-9_.]+(?:/[A-Za-z0-9_.]+)+)$", phrase.strip())
    if not match:
        return []
    prefix = (match.group(1) or "").strip()
    tokens = match.group(2).split("/")
    if len(tokens) < 2:
        return []
    if not prefix:
        return []
    return [f"{prefix} {tok}".strip() for tok in tokens]


def extract_constant(description: str) -> float | None:
    """Recognize the small set of literal-constant idioms this spec text
    uses when a metric is a known, deliberately-fixed value rather than
    something computed per run (e.g. 'always 0', 'hardcoded 1.0')."""
    if re.search(r"\balways\s+0\b", description, re.IGNORECASE):
        return 0.0
    match = re.search(r"hardcoded\s+([0-9.eE+-]+)", description, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def _unique_prefix_match(slug: str, remaining_keys: list[str]) -> str | None:
    """If exactly one still-unused real key starts with '<slug>_', return it.
    Catches near-misses like candidate 'local_numa_node_latency' against
    real key 'local_numa_node_latency_nsec', or 'tcp_throughput' against
    'tcp_throughput_gb_s' -- fires only when unambiguous."""
    if not slug:
        return None
    prefix = slug + "_"
    matches = [
        k for k in remaining_keys
        if normalize_key(k).startswith(prefix) and units_compatible(slug, k)
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def _build_candidates(description: str) -> list[str]:
    """All the honest name candidates worth trying for one metric
    description, most-specific first."""
    candidates: list[str] = list(extract_paren_keys(description))
    candidates.append(description)  # full-phrase slug (legacy behavior)
    before = phrase_before_paren(description)
    if before:
        candidates.append(before)
        candidates.extend(distribute_slash_list(before))
    else:
        candidates.extend(distribute_slash_list(description))
    # de-duplicate while preserving order; expand mashed p50_p95_p99 to split keys (D3)
    seen: set[str] = set()
    ordered: list[str] = []
    for c in candidates:
        extras = [c, *split_percentile_keys(c)]
        for item in extras:
            if item and item not in seen:
                seen.add(item)
                ordered.append(item)
    return ordered


def display_label(description: str, resolved_key: str) -> str:
    """Prefer the parenthetical that actually names the resolved metric key."""
    paren = extract_paren_keys(description)
    resolved_normalized = normalize_key(resolved_key)
    for candidate in paren:
        if normalize_key(candidate) == resolved_normalized:
            return unmash_p50_key(candidate)
    if paren:
        return unmash_p50_key(paren[0])
    return unmash_p50_key(resolved_key)


def resolve_metrics(items: list[tuple[str, str]], metrics: dict) -> list[tuple[str, str, object]]:
    """Return, for each (number, description) in items, a (label, value)
    resolved as honestly as possible. Never reuses the same dict key for two
    different metrics, and never guesses a value across a position mismatch."""
    metrics = apply_storage_aliases(metrics)
    norm_lookup: dict[str, str] = {}
    for key in metrics:
        norm_lookup.setdefault(normalize_key(key), key)

    used_keys: set[str] = set()
    resolved: dict[int, tuple[str, object]] = {}
    unresolved_idx: list[int] = []
    candidates_by_idx: dict[int, list[str]] = {}

    for idx, (_number, description) in enumerate(items):
        candidates = _build_candidates(description)
        candidates_by_idx[idx] = candidates
        found_key = None
        for candidate in candidates:
            key = norm_lookup.get(normalize_key(candidate))
            if key is not None and key not in used_keys:
                found_key = key
                break
        if found_key is not None:
            used_keys.add(found_key)
            resolved[idx] = (found_key, metrics[found_key])
            continue
        constant = extract_constant(description)
        if constant is not None:
            resolved[idx] = (column_name(description), constant)
            continue
        unresolved_idx.append(idx)

    # Unique-prefix-match pass: try every candidate generated for a still-
    # unresolved metric (not just the first), and only accept a match when
    # exactly one unused real key is an unambiguous extension of it.
    still_unresolved = set(unresolved_idx)
    for idx in list(unresolved_idx):
        if idx not in still_unresolved:
            continue
        for candidate in candidates_by_idx.get(idx, []):
            remaining_keys = [k for k in metrics if k not in used_keys and metrics[k] is not None]
            match = _unique_prefix_match(normalize_key(candidate), remaining_keys)
            if match is not None:
                used_keys.add(match)
                resolved[idx] = (match, metrics[match])
                still_unresolved.discard(idx)
                break

    output = []
    for idx, (number, description) in enumerate(items):
        if idx in resolved:
            label, value = resolved[idx]
        else:
            label, value = column_name(description), "NOT FOUND"
        output.append((number, description, label, value))
    return output


def _printable(value: object) -> bool:
    """Print real values and "not measured" (the metric's column or tier exists
    but holds no value on this host), so a skipped metric shows as a line
    instead of vanishing. A metric with no column at all (NOT FOUND) stays hidden."""
    text = str(value).strip().lower() if value is not None else ""
    if text in {"not measured", "not_measured"}:
        return True
    if is_blank(value):
        return False
    return text not in {"not found", "n/a"}


def metric_print_fields(description: str, label: str, value: object, metrics: dict) -> list[tuple[str, object]]:
    """Print one value. A mashed p50/p95/p99 spec prints the p50 key only."""
    paren = extract_paren_keys(description)
    source = paren[0] if paren else label
    parts = split_percentile_keys(source)
    if len(parts) >= 3:
        lookup = {normalize_key(key): item for key, item in metrics.items()}
        found = lookup.get(normalize_key(parts[0]))
        if _printable(found):
            return [(display_label(description, parts[0]), found)]
        return []
    if not _printable(value):
        return []
    return [(display_label(description, label), value)]


def format_value(value: object) -> str:
    """Display form: whole numbers without ".0", values >= 1 to 3 decimals, smaller
    values to 4 significant digits; text ("not measured", "NOT FOUND") unchanged.
    summary.json keeps full precision."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return str(value)
    if number.is_integer() and abs(number) < 1e15:
        return str(int(number))
    if abs(number) >= 1:
        return f"{number:.3f}".rstrip("0").rstrip(".")
    return f"{number:.4g}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--definition", type=Path, default=Path("benchmark_specification.json"))
    parser.add_argument("--summary", type=Path, default=Path("results/summary.json"))
    args = parser.parse_args()

    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    metrics = summary.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
    gpu_name = str(summary.get("gpu_name") or metrics.get("gpu_name") or "")
    metrics = annotate_metrics(metrics, gpu_name)
    status = str(summary.get("status") or metrics.get("workload_kind") or "")
    if status.lower() in {"stub", "smoke-standin", "standin"} or any(
        is_explicit_na(value) and "stub server" in str(value).lower() for value in metrics.values()
    ):
        print("STUB stand-in server; numbered serving metrics are na (stub server, smoke only).")

    items = metric_items(args.definition)
    unresolved = 0
    point = str(metrics.get("headline_point") or "").strip()
    for number, description, label, value in resolve_metrics(items, metrics):
        shown = description
        if point and point not in shown:
            shown = f"{shown} [{point}]"
        if str(value) == "NOT FOUND":
            unresolved += 1
            print(f"[INFO] #{number}: {shown}; na (unresolved metric)")
            continue
        fields = metric_print_fields(shown, label, value, metrics)
        if not fields:
            if is_explicit_na(value):
                print(f"[INFO] #{number}: {shown}; {value}")
                continue
            unresolved += 1
            print(f"[INFO] #{number}: {shown}; na (unresolved metric)")
            continue
        rendered = "; ".join(f"{name}={format_value(item)}" for name, item in fields)
        print(f"[INFO] #{number}: {shown}; {rendered}")
    return 1 if unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())
