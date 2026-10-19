#!/usr/bin/env python3
# File: scripts/materialize_generated_harness.py
# Description: Fill empty generated parse/validate/run_benchmark files after overlays.
# Execution: Called by init_generated_repo.py. Do not write collect_workload.py.
from __future__ import annotations

import json
from pathlib import Path


def _is_empty(path: Path) -> bool:
    return (not path.exists()) or path.stat().st_size == 0


def _fields_of(repo: Path) -> dict[str, str]:
    path = repo / "benchmark_specification.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(item.get("field_name", "")): str(item.get("value", "") or "") for item in data}


def _parameters(fields: dict[str, str]) -> list[str]:
    names = []
    for index in range(1, 21):
        value = fields.get(f"Parameter_{index:02d}", "").strip()
        if value and value not in {"—", "-", "--"}:
            names.append(value)
    return names


def _flag_of(name: str) -> str:
    return "--" + name.replace("_", "-")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
    if path.suffix == ".sh":
        path.chmod(path.stat().st_mode | 0o111)


def write_parser(repo: Path) -> None:
    path = repo / "scripts" / "parse_results.py"
    if not _is_empty(path):
        return
    _write(
        path,
        '''#!/usr/bin/env python3
# File: scripts/parse_results.py
# Description: Parse raw collector CSV into SQLite and summary.json.
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sqlite3
import statistics
from datetime import datetime, timezone
from pathlib import Path

ANSI_RE = re.compile(r"\\x1b\\[[0-9;]*[A-Za-z]|\\x00")
_COL_ALIASES = {
    "rocm-package-mismatch-count": "rocm_package_mismatch_count",
    "kernel-driver-mismatch-count": "kernel_release_mismatch_count",
    "kernel-release-mismatch-count": "kernel_release_mismatch_count",
    "firmware-compliance-percent": "firmware_compliance_percent",
    "driver-compliance-percent": "driver_compliance_percent",
    "permission-error-count": "permission_error_count",
    "transA": "transa",
    "transa": "transa",
    "rocblas-Gflops": "rocblas_gflops",
    "rocblas-gflops": "rocblas_gflops",
    "GB/s": "memory_bandwidth_gb_s",
}


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def load_fields(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(item.get("field_name", "")): str(item.get("value", "") or "") for item in data}


def parameters(fields: dict[str, str]) -> list[str]:
    names = []
    for index in range(1, 21):
        value = fields.get(f"Parameter_{index:02d}", "").strip()
        if value and value not in {"—", "-", "--"}:
            names.append(value)
    return names


def normalize_header(name: str) -> str:
    key = name.strip()
    return _COL_ALIASES.get(key, re.sub(r"[^A-Za-z0-9]+", "_", key).strip("_").lower())


_HEADER_FIRST = {"sample_index", "check_name", "name", "solver", "kind", "step", "batch_size", "benchmark"}
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_\\-/]*$")
# Workload definition fields; filled in by main() before any raw file is parsed.
_SPEC_FIELDS: dict[str, str] = {}


def _is_header(cells: list[str], current: tuple | None) -> bool:
    filled = [cell.strip() for cell in cells if cell.strip()]
    if len(filled) < 2:
        return False
    if cells[0].strip().lower() in _HEADER_FIRST:
        return True
    if not all(_IDENT_RE.match(cell) for cell in filled):
        return False
    # An all-identifier line is a header when nothing is open yet, or when it
    # names columns (underscores) or has a different width than the open table.
    return current is None or len(cells) != len(current) or any("_" in cell for cell in filled)


def parse_csv_tables(text: str) -> tuple[list[list], dict[str, str]]:
    """Every CSV table in the raw text as [header, rows], in order of appearance.

    The old parser kept only the first header it saw and mapped every later row
    onto it. vLLM raw output holds two tables (a concurrency summary, then the
    per-sample CSV), so per-sample values landed under the wrong column names.
    A repeated identical header continues its table instead of starting a new one.
    """
    metadata: dict[str, str] = {}
    tables: list[list] = []
    by_header: dict[tuple, list] = {}
    current = None
    for raw_line in text.splitlines():
        line = strip_ansi(raw_line).strip()
        if not line:
            continue
        if line.startswith("#"):
            for match in re.finditer(r"([A-Za-z0-9_]+)=([^\\s]+)", line):
                metadata[match.group(1)] = match.group(2)
            continue
        if line.lower().startswith("stats:"):
            line = line.split(":", 1)[1].strip()
        if "," not in line:
            continue
        cells = next(csv.reader(io.StringIO(line)))
        if _is_header(cells, current[0] if current else None):
            header = tuple(normalize_header(cell) for cell in cells)
            if header not in by_header:
                by_header[header] = [header, []]
                tables.append(by_header[header])
            current = by_header[header]
            continue
        if current is None:
            continue
        header = current[0]
        current[1].append({header[i]: cells[i] if i < len(cells) else "" for i in range(len(header))})
    return tables, metadata


def _spec_metric_keys(fields: dict[str, str]) -> set[str]:
    """Column names the workload definition asks for: every parenthetical key in
    Metrics plus every token of Output Fields / Metrics to Parse."""
    def slug(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    keys: set[str] = set()
    metrics = fields.get("Metrics", "") or ""
    outputs = fields.get("Output Fields / Metrics to Parse", "") or ""
    for inner in re.findall(r"\\(([^()]*)\\)", metrics + " " + outputs):
        keys.update(slug(part) for part in re.split(r"[/,;]", inner))
    keys.update(slug(part) for part in re.split(r"[,;\\s]+", outputs))
    keys.discard("")
    return keys


def parse_csv_blocks(text: str) -> tuple[list[dict[str, str]], dict[str, str]]:
    """Rows of the one table that best matches this workload's metric keys
    (ties: a sample_index table, then the table with more rows, then the first)."""
    tables, metadata = parse_csv_tables(text)
    tables = [table for table in tables if table[1]]
    if not tables:
        return [], metadata
    keys = _spec_metric_keys(_SPEC_FIELDS)

    def score(table):
        header, rows = table
        return (sum(1 for col in header if col in keys), header[0] == "sample_index", len(rows))

    best = max(tables, key=score)
    return best[1], metadata


def load_rows(raw_path: Path, text: str) -> tuple[list[dict[str, str]], dict[str, str]]:
    """parse_csv_blocks(), with two fallbacks for collectors that do not write
    CSV to --raw-file: a sibling raw_results.csv next to it, then a JSON
    object/array (one row per dict) in the raw file itself. Components that
    already write CSV to --raw-file are unaffected -- this only runs when
    the primary CSV parse finds nothing.
    """
    try:
        rows, metadata = parse_csv_blocks(text)
        if rows:
            return rows, metadata
    except SystemExit:
        pass
    sibling_csv = raw_path.parent / "raw_results.csv"
    if sibling_csv.is_file() and sibling_csv.resolve() != raw_path.resolve():
        try:
            sibling_text = strip_ansi(sibling_csv.read_text(encoding="utf-8", errors="replace"))
            rows, metadata = parse_csv_blocks(sibling_text)
            if rows:
                return rows, metadata
        except SystemExit:
            pass
    try:
        parsed = json.loads(text.strip())
    except (ValueError, json.JSONDecodeError):
        parsed = None
    if parsed is not None:
        records = parsed if isinstance(parsed, list) else [parsed]
        rows = [
            {normalize_header(str(key)): str(value) for key, value in record.items()}
            for record in records
            if isinstance(record, dict)
        ]
        if rows:
            return rows, {}
    raise SystemExit("[FAIL] No supported raw output rows were parsed.")


_NUMBER_RE = re.compile(r"^[+-]?(\\d+\\.?\\d*|\\.\\d+)([eE][+-]?\\d+)?$")


def to_number(value: str):
    if value in {"", None}:
        return None
    text = str(value).strip()
    if not _NUMBER_RE.match(text):
        return value
    try:
        number = float(text)
    except (TypeError, ValueError):
        return value
    if number.is_integer():
        return int(number)
    return number


_NOT_MEASURED_TEXT = {"", "not measured", "not_measured", "n/a", "na", "nan", "none"}
# A collector that cannot measure a metric on this host writes the reason in
# the cell instead of a number, e.g. "na (requires at least two GPUs)". When
# every row of a column holds the same reason, summary.json reports that text
# so the metric prints with its reason instead of disappearing.
_NA_REASON_RE = re.compile(r"^na \\(.+\\)$", re.IGNORECASE)


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def aggregate(col: str, values: list[float]):
    """Summarise one metric column across sample rows by its leading word:
    peak_/max_ -> max, min_ -> min, first_ -> first row, otherwise the mean.
    (Everything used to be the mean, so "peak CPU temperature" was an average.)
    Only the leading word counts: "time_to_first_token" stays a mean, and
    "peak_percent" / "percent_of_peak_*" (a share of theoretical peak) too.
    Per-row percentile columns (iops_p50, batch_latency_ms_p99, ...) are
    averaged across runs, which is the usual practice."""
    if not values:
        return None
    words = col.lower().split("_")
    lead, second = words[0], (words[1] if len(words) > 1 else "")
    if lead == "first":
        return values[0]
    is_observed_peak = (
        lead in {"peak", "max", "maximum"}
        or ("peak" in words and not col.lower().startswith(("percent_of_", "pct_of_")))
    )
    if is_observed_peak and not (lead == "peak" and second in {"percent", "pct"}):
        return max(values)
    if lead in {"min", "minimum"}:
        return min(values)
    return statistics.mean(values)


_PIVOT_GROUP_COLUMNS = {"tier", "benchmark", "direction"}
# "benchmark" covers lmbench-style long-format tables: one row per named
# micro-benchmark (lat_ctx, bw_mem, bw_pipe, ...) sharing a single generic
# "value" column, rather than one column per benchmark. When the group
# column's own values already read as a metric name (unlike "tier", which
# needs a "latency_ns_" prefix to stay meaningful), and there is exactly
# one other numeric column to pivot, the bare group value name is used
# directly as the key instead of "<column>_<group>" -- see below.
# "direction" is the MIOpen convolution table (fwd / bwd_data / bwd_weights).
# The numbered metrics stay on the forward rows; each direction also gets
# <column>_<direction>. tier and benchmark have no headline, so their
# blended mean is still dropped.
_PIVOT_HEADLINE = {"direction": "fwd"}


def _apply_declared_headline(summary_metrics, rows):
    """Pick the row a sweep label names, and keep every other point.

    first_case (fio jobs) copies that job into the singular keys and stores
    every job under <metric>__<configuration>. A hipMemcpy size x direction
    table uses max-size H2D bandwidth and min-size H2D latency. Convolution
    directions (fwd/bwd) have no transfer_size_bytes and stay on the pivot
    above.
    """
    if not rows:
        return summary_metrics
    if any(str(row.get("headline_rule", "")).strip() == "first_case" for row in rows):
        chosen = None
        for row in rows:
            if str(row.get("is_headline", "")).strip() in {"1", "true", "yes"}:
                chosen = row
                break
        if chosen is None:
            chosen = rows[0]
        point = str(chosen.get("headline_configuration") or "first_case").strip()
        skip_keys = {
            "sample_index", "status", "error_message", "headline_rule",
            "is_headline", "headline_configuration",
        }
        for key, raw in chosen.items():
            if key in skip_keys:
                continue
            number = to_number(raw)
            if isinstance(number, (int, float)) and key in summary_metrics:
                summary_metrics[key] = number
        for row in rows:
            config = str(row.get("headline_configuration") or "").strip()
            if not config:
                config = "_".join(
                    str(row.get(part, "")).strip()
                    for part in ("rw", "block_size", "io_depth")
                    if str(row.get(part, "")).strip()
                )
            slug = re.sub(r"[^A-Za-z0-9]+", "_", config).strip("_").lower()
            if not slug:
                continue
            for key, raw in row.items():
                if key in skip_keys or key.startswith("case_"):
                    continue
                number = to_number(raw)
                if isinstance(number, (int, float)):
                    summary_metrics[f"{key}__{slug}"] = number
        summary_metrics["headline_point"] = f"first_case {point}"
        summary_metrics["headline_sample_count"] = len(rows)
    if "transfer_size_bytes" not in rows[0]:
        return summary_metrics
    directions = {str(row.get("direction", "")).strip().lower() for row in rows}
    if not (directions & {"h2d", "d2h", "d2d"}):
        return summary_metrics
    sized = []
    for row in rows:
        size = to_number(row.get("transfer_size_bytes", ""))
        if isinstance(size, (int, float)):
            sized.append((float(size), str(row.get("direction", "")).strip().lower(), row))
    if not sized:
        return summary_metrics
    max_size = max(item[0] for item in sized)
    min_size = min(item[0] for item in sized)
    bw_key = next((key for key in ("bandwidth_gbps",) if any(key in row for row in rows)), "")
    lat_key = "latency_us" if any("latency_us" in row for row in rows) else ""

    def pick(size, direction, key):
        if not key:
            return None
        for item_size, item_dir, row in sized:
            if item_size == size and item_dir == direction:
                number = to_number(row.get(key, ""))
                if isinstance(number, (int, float)):
                    return number
        return None

    h2d_bw = pick(max_size, "h2d", bw_key)
    h2d_lat = pick(min_size, "h2d", lat_key)
    if h2d_bw is not None:
        summary_metrics[bw_key] = h2d_bw
    if h2d_lat is not None:
        summary_metrics[lat_key] = h2d_lat
    summary_metrics["headline_transfer_bytes"] = int(max_size)
    mib = max_size / (1024.0 * 1024.0)
    mib_text = str(int(mib)) if float(mib).is_integer() else f"{mib:.3g}"
    summary_metrics["headline_point"] = f"at {mib_text} MiB H2D"
    for direction in ("h2d", "d2h", "d2d"):
        bandwidth = pick(max_size, direction, bw_key)
        latency = pick(min_size, direction, lat_key)
        if bandwidth is not None:
            summary_metrics[f"{bw_key}_{direction}"] = bandwidth
        if latency is not None:
            summary_metrics[f"{lat_key}_{direction}"] = latency
    return summary_metrics


def build_metrics_summary(metric_cols, rows, aggregates):
    """The "metrics" dict written to results/summary.json. Two changes from
    the raw per-column aggregate map used for the SQLite tables above:

    1. Columns that never held a numeric value for any row (categorical or
       label columns such as tier/kind/name/device) are dropped entirely,
       instead of appearing as a misleading null.
    2. Long-format tables -- one row per named entity rather than one named
       column per entity -- are pivoted so each entity gets its own key.
       The only known real case is a "tier" column (multichase-style NUMA
       latency sweeps: sample_index,status,tier,latency_ns,...,one row per
       yaml tier) where a single blind mean across all rows blends
       unrelated tiers (L1 cache vs remote DRAM) into one meaningless
       number. When a "tier" column is present with 2-20 distinct values,
       each other numeric column that actually varies across those tiers
       (not a constant/parameter smuggled into metric_cols) additionally
       gets one aggregate per tier, keyed "<column>_<tier>".
    """
    summary_metrics = {col: val for col, val in aggregates.items() if val is not None}
    for group_col in _PIVOT_GROUP_COLUMNS:
        if group_col not in metric_cols:
            continue
        groups = {}
        for row in rows:
            group_val = str(row.get(group_col, "")).strip()
            if group_val:
                groups.setdefault(group_val, []).append(row)
        if not (2 <= len(groups) <= 20):
            continue
        # Columns that never held a numeric value anywhere (e.g. lmbench's
        # "units" column, all "raw") are not real metric columns -- they
        # would already be dropped from the top-level summary by the
        # None-filter above, but must ALSO be excluded here so they don't
        # inflate the "how many real columns besides the group column"
        # count used to decide the naming scheme below.
        other_cols = [
            col for col in metric_cols
            if col != group_col and aggregates.get(col) is not None
        ]
        # lmbench-style tables (one generic "value" column) read better keyed
        # by the bare group value itself (e.g. "lat_ctx") since the group
        # values already are the metric names. multichase-style tables
        # (multiple real columns alongside "tier") need the "<column>_"
        # prefix to disambiguate which measurement each per-group key holds.
        use_bare_group_name = len(other_cols) == 1
        for col in other_cols:
            per_group_means = {}
            for group_val, group_rows in groups.items():
                values = []
                for row in group_rows:
                    number = to_number(row.get(col, ""))
                    if isinstance(number, (int, float)):
                        values.append(float(number))
                if values:
                    per_group_means[group_val] = aggregate(col, values)
            if len(per_group_means) < 2:
                continue
            distinct_means = {round(v, 9) for v in per_group_means.values()}
            if len(distinct_means) < 2:
                continue  # constant across groups -- a parameter, not a per-tier metric
            # This column genuinely varies across groups, so its single blind
            # overall mean (already sitting in summary_metrics via the
            # aggregates dict) blends unrelated groups into one meaningless
            # number -- e.g. multichase's L1-cache and remote-DRAM latencies
            # averaged together, or lmbench's nanosecond latencies averaged
            # with megabyte/sec bandwidths, or MIOpen forward GB/s averaged
            # with the two backward passes. Drop that blend. tier and
            # benchmark stay dropped. A headline group restores the base key
            # from that group only (direction=fwd). If the headline value is
            # not in the table, the base key stays unset.
            summary_metrics.pop(col, None)
            headline = _PIVOT_HEADLINE.get(group_col)
            if headline is not None and headline in per_group_means:
                summary_metrics[col] = per_group_means[headline]
            for group_val, mean_val in per_group_means.items():
                slug = re.sub(r"[^A-Za-z0-9]+", "_", group_val).strip("_").lower()
                key = slug if use_bare_group_name else f"{col}_{slug}"
                if key in summary_metrics and use_bare_group_name:
                    # Guard against an accidental collision with a real column
                    # name -- fall back to the disambiguated form rather than
                    # silently overwriting an unrelated metric.
                    key = f"{col}_{slug}"
                summary_metrics[key] = mean_val
            # A group that is present but has no number for this column (a
            # remote_dram tier skipped on a single-NUMA-node host) keeps an
            # na (...) reason from the cell. A blank cell stays "not measured".
            for group_val in groups:
                if group_val in per_group_means:
                    continue
                slug = re.sub(r"[^A-Za-z0-9]+", "_", group_val).strip("_").lower()
                key = slug if use_bare_group_name else f"{col}_{slug}"
                texts = {
                    str(row.get(col, "") or "").strip()
                    for row in groups[group_val]
                }
                texts.discard("")
                reason = next(iter(texts)) if len(texts) == 1 else ""
                if not _NA_REASON_RE.match(reason):
                    reason = ""
                summary_metrics.setdefault(key, reason or "not measured")
    return _apply_declared_headline(summary_metrics, rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-file", required=True)
    parser.add_argument("--db", default=os.environ.get("BENCHMARK_DB", "results/benchmark.db"))
    parser.add_argument("--summary", default="results/summary.json")
    parser.add_argument("--definition", default="benchmark_specification.json")
    parser.add_argument("--run-dir", default="")
    args = parser.parse_args()
    raw_path = Path(args.raw_file)
    fields = load_fields(Path(args.definition))
    _SPEC_FIELDS.update(fields)
    text = strip_ansi(raw_path.read_text(encoding="utf-8", errors="replace"))
    rows, metadata = load_rows(raw_path, text)
    skip = {
        # Sample-identity columns the raw CSV is expected to carry and that
        # are handled specially below (not generic metrics).
        "sample_index", "status", "error_message", "check_name",
        "rc", "command", "check",
        "headline_rule", "is_headline", "headline_configuration",
        # Every column name already hardcoded into the "runs"/"samples"
        # schema below. A collector CSV that happens to emit its own
        # column with one of these exact names (e.g. a per-sample
        # "created_at" timestamp, as sdxl-diffusers' collector does) must
        # not also be treated as a metric_col: SQLite table/column names
        # are case-insensitive, so admitting a second "created_at" (or
        # "host_name", "run_id", etc.) crashes CREATE TABLE with
        # "duplicate column name" instead of silently shadowing it.
        "run_id", "benchmark_id", "benchmark_name", "started_at",
        "finished_at", "host_name", "os_version", "kernel_version",
        "gpu_name", "rocm_version", "framework_version", "git_sha",
        "config_path", "command_line", "created_at", "id", "placeholder",
    }
    param_names = parameters(fields)
    # Compare case-insensitively: a raw CSV header cell is lowercased by
    # normalize_header() before it ever reaches `rows`, but a workload's own
    # Parameter_NN name (e.g. GEMM's "M"/"N"/"K") is taken verbatim from
    # benchmark_specification.json and can be upper/mixed case. Without the
    # .lower() here, a column whose only mention is as an uppercase
    # parameter name (e.g. header cell "M" -> row key "m") slips past this
    # exclusion and gets treated as BOTH a TEXT parameter column and a REAL
    # metric column with the same case-insensitive SQLite identifier ("M"
    # and "m" collide), which crashes table creation with "duplicate column
    # name". Lower-and-dedupe once so every later use (param_sql, run_vals,
    # sample inserts) is consistently keyed the same way.
    param_names_l = [name.lower() for name in param_names]
    param_names = list(dict.fromkeys(param_names_l))
    metric_cols = []
    if rows:
        metric_cols = [
            key for key in rows[0]
            if key not in skip and key.lower() not in param_names and not key.startswith("parameter_")
        ]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    def q(name: str) -> str:
        return '"' + str(name).replace('"', '""') + '"'

    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE IF EXISTS samples")
    conn.execute("DROP TABLE IF EXISTS runs")
    metric_sql = ", ".join(f"{q(col)} REAL" for col in metric_cols)
    param_sql = ", ".join(f"{q(name)} TEXT" for name in param_names)
    conn.execute(
        f"""CREATE TABLE runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            benchmark_id TEXT,
            benchmark_name TEXT,
            status TEXT,
            started_at TEXT,
            finished_at TEXT,
            host_name TEXT,
            os_version TEXT,
            kernel_version TEXT,
            gpu_name TEXT,
            rocm_version TEXT,
            framework_version TEXT,
            git_sha TEXT,
            config_path TEXT,
            command_line TEXT,
            error_message TEXT,
            {metric_sql or "placeholder REAL"}
        )"""
    )
    conn.execute(
        f"""CREATE TABLE samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL REFERENCES runs(run_id),
            sample_index INTEGER,
            status TEXT,
            {param_sql + "," if param_sql else ""}
            {metric_sql or "placeholder REAL"},
            error_message TEXT,
            created_at TEXT
        )"""
    )
    aggregates = {}
    not_measured = []
    for col in metric_cols:
        values = []
        for row in rows:
            number = to_number(row.get(col, ""))
            if isinstance(number, (int, float)):
                values.append(float(number))
        aggregates[col] = aggregate(col, values)
        if not values:
            reasons = {str(row.get(col, "") or "").strip() for row in rows}
            if len(reasons) == 1 and _NA_REASON_RE.match(next(iter(reasons))):
                aggregates[col] = next(iter(reasons))
        if not values and all(
            str(row.get(col, "") or "").strip().lower() in _NOT_MEASURED_TEXT for row in rows
        ):
            not_measured.append(col)
    status = "ok"
    if any(str(row.get("status", "ok")).lower() == "error" for row in rows):
        status = "partial"
    run_cols = [
        "benchmark_id", "benchmark_name", "status", "started_at", "finished_at",
        "host_name", "os_version", "kernel_version", "gpu_name", "rocm_version",
        "framework_version", "git_sha", "config_path", "command_line", "error_message",
        *metric_cols,
    ]
    run_vals = [
        fields.get("Workload Number", ""),
        fields.get("Workload Name", ""),
        status,
        now,
        now,
        os.uname().nodename if hasattr(os, "uname") else "",
        fields.get("OS Version", ""),
        metadata.get("kernel_version", fields.get("Kernel Version", "")),
        metadata.get("gpu_name", ""),
        metadata.get("rocm_version", fields.get("ROCm Version", "")),
        fields.get("Framework", "").split(",")[0].strip(),
        "",
        "config/benchmark_config.yaml",
        metadata.get("command_line", "bash run_benchmark.sh"),
        None,
        *[aggregates.get(col) for col in metric_cols],
    ]
    placeholders = ",".join("?" for _ in run_cols)
    cur = conn.execute(
        f"INSERT INTO runs ({', '.join(q(c) for c in run_cols)}) VALUES ({placeholders})",
        run_vals,
    )
    run_id = cur.lastrowid
    for index, row in enumerate(rows):
        sample_status = row.get("status") or "ok"
        values = [run_id, int(to_number(row.get("sample_index", index)) or index), sample_status]
        for name in param_names:
            values.append(row.get(name, metadata.get(name, "")))
        for col in metric_cols:
            values.append(to_number(row.get(col, "")))
        values.extend([row.get("error_message") or None, now])
        extra = (", " + ", ".join(q(name) for name in param_names)) if param_names else ""
        metric_insert = ", ".join(q(c) for c in metric_cols) if metric_cols else "placeholder"
        conn.execute(
            f"INSERT INTO samples (run_id, sample_index, status{extra}, {metric_insert}, error_message, created_at) VALUES ({','.join('?' for _ in values)})",
            values,
        )
    conn.commit()
    conn.close()
    metrics_summary = build_metrics_summary(metric_cols, rows, aggregates)
    summary = {
        "sample_count": len(rows),
        "status": status,
        "metrics": metrics_summary,
        "run_id": run_id,
        "profile": os.environ.get("BENCHMARK_PROFILE", ""),
    }
    Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
    Path(args.summary).write_text(json.dumps(summary, indent=2) + "\\n", encoding="utf-8")
    if args.run_dir:
        run_dir = Path(args.run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "raw_results.csv").write_text(raw_path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        (run_dir / "raw_results.jsonl").write_text("\\n".join(json.dumps(row) for row in rows) + "\\n", encoding="utf-8")
    print(f"[PASS] parsed {len(rows)} samples into {db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
    )


def write_validator(repo: Path) -> None:
    path = repo / "scripts" / "validate_results.py"
    if not _is_empty(path):
        return
    _write(
        path,
        '''#!/usr/bin/env python3
# File: scripts/validate_results.py
# Description: Validate the latest SQLite run against integrity checks and yaml thresholds.
from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

ZERO_OK_HINTS = (
    "count", "error", "mismatch", "fault", "loss", "miss", "retransmit",
    "compliance",
    "jitter", "permission", "ecc", "throttl", "fail", "util", "second",
    "active", "uncorrected", "corrected", "placeholder", "pcie",
    "rc",
    "cache_hit",
    # cuDNN algorithm ids are zero-based. Algorithm 0 is a successful selection.
    "algo",
)


def load_yaml(path: Path) -> dict:
    if yaml is None:
        raise SystemExit("[FAIL] PyYAML is required in the repository-local .venv.")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def is_iso8601(value: str) -> bool:
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def zero_ok(name: str) -> bool:
    lowered = name.lower()
    return any(token in lowered for token in ZERO_OK_HINTS)


def workload_number() -> int:
    path = Path("benchmark_specification.json")
    if not path.is_file():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    fields = {str(item.get("field_name", "")): str(item.get("value", "") or "") for item in data}
    try:
        return int(float(fields.get("Workload Number") or 0))
    except ValueError:
        return 0


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=os.environ.get("BENCHMARK_DB", "results/benchmark.db"))
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--seed-fixture", action="store_true")
    args = parser.parse_args()
    if args.seed_fixture:
        args.db = str(seed_fixture(Path(args.config)))
    db_path = Path(os.environ.get("BENCHMARK_DB", args.db))
    if args.seed_fixture:
        db_path = Path(args.db)
    if not db_path.is_file():
        print("[FAIL] benchmark database is missing")
        return 1
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    run = conn.execute("SELECT * FROM runs ORDER BY run_id DESC LIMIT 1").fetchone()
    if run is None:
        print("[FAIL] no runs")
        return 1
    samples = conn.execute("SELECT * FROM samples WHERE run_id = ?", (run["run_id"],)).fetchall()
    failures = []
    run_keys = set(run.keys())
    if run["status"] not in {"ok", "stub"}:
        failures.append("latest run status is not ok")
    if "error_message" in run_keys and run["error_message"] not in {None, ""}:
        failures.append("run.error_message is not NULL")
    if not is_iso8601(run["started_at"]) or not is_iso8601(run["finished_at"]):
        failures.append("timestamps are not ISO-8601")
    if len(samples) < 1:
        failures.append("no sample rows")
    wid = workload_number()
    if (101 <= wid <= 123 or 301 <= wid <= 323) and len(samples) < 2:
        failures.append("workloads 101-123 require at least two sample rows")
    skip = {"id", "run_id", "sample_index", "status", "error_message", "created_at",
            "benchmark_id", "benchmark_name", "started_at", "finished_at", "host_name",
            "os_version", "kernel_version", "gpu_name", "rocm_version", "framework_version",
            "git_sha", "config_path", "command_line", "placeholder", "check_name",
            "rc", "command", "check"}
    for column in run.keys():
        if column in skip:
            continue
        value = run[column]
        if value is None:
            continue
        if isinstance(value, (int, float)) and not math.isfinite(float(value)):
            failures.append(f"run.{column} is not finite")
        if isinstance(value, (int, float)) and float(value) < 0 and not zero_ok(column):
            failures.append(f"run.{column} is negative")
        if isinstance(value, (int, float)) and float(value) <= 0 and not zero_ok(column):
            failures.append(f"run.{column} is not positive")
    for sample in samples:
        if sample["status"] not in {"ok", "stub"}:
            failures.append(f"sample {sample['sample_index']} is not ok")
        # A sample with status == "ok" and a non-empty error_message is a
        # collector reporting an optional measurement it honestly could not
        # take (e.g. "perf TLB/L3 not measured") alongside a valid primary
        # score -- not a failed sample. Only a non-"ok" status fails it.
        for column in sample.keys():
            if column in skip:
                continue
            value = sample[column]
            if value in {None, ""}:
                continue
            if isinstance(value, (int, float)) and not math.isfinite(float(value)):
                failures.append(f"sample.{column} is not finite")
            if isinstance(value, (int, float)) and float(value) < 0 and not zero_ok(column):
                failures.append(f"sample.{column} is negative")
    config = load_yaml(Path(args.config))
    thresholds = config.get("thresholds") or {}
    for key, expected in thresholds.items():
        if key.endswith("_min"):
            column = key[:-4]
            direction = "min"
        elif key.endswith("_max"):
            column = key[:-4]
            direction = "max"
        else:
            continue
        if column not in run.keys() or run[column] is None:
            continue
        try:
            measured = float(run[column])
        except (TypeError, ValueError):
            continue  # "na (...)": not measured on this host, nothing to compare
        expected = float(expected)
        if direction == "min" and measured < expected:
            failures.append(f"{column} {measured} < min {expected}")
        if direction == "max" and measured > expected:
            failures.append(f"{column} {measured} > max {expected}")
    conn.close()
    summary_path = Path("results/summary.json")
    publication = "PASS"
    if summary_path.is_file():
        try:
            from metric_contract import publication_status, text_dimension_key
            from print_metric_summary import metric_items, resolve_metrics
        except ImportError:
            publication_status = None
        if publication_status is not None:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
            metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
            definition = Path("benchmark_specification.json")
            items = metric_items(definition) if definition.is_file() else []
            for _number, description in items:
                if text_dimension_key(description):
                    failures.append(f"numbered metric is a text dimension: {description}")
            resolved = resolve_metrics(items, metrics) if items else []
            pairs = [(label, value) for _number, _description, label, value in resolved]
            context = {
                "profile": os.environ.get("BENCHMARK_PROFILE", "") or str(payload.get("profile") or ""),
                "status": payload.get("status", ""),
                "standin": str(payload.get("status", "")).lower() in {"stub", "smoke-standin"},
                "gpu_count": metrics.get("gpu_count", os.environ.get("GPU_COUNT", "")),
                "numa_nodes": metrics.get("numa_nodes", ""),
            }
            publication, _na_count = publication_status(pairs, context)
            if publication == "INCOMPLETE":
                failures.append("required metric missing or unexpected na")
    if failures:
        if not args.quiet:
            print("[FAIL] validation")
            for item in failures:
                print(" -", item)
        return 1
    if not args.quiet:
        if publication == "SMOKE-STANDIN":
            print("STUB stand-in server; numbered serving metrics are na (stub server, smoke only).")
            print(f"[SMOKE-STANDIN] validated {len(samples)} samples")
        elif publication == "N/A-EXPECTED":
            print(f"[N/A-EXPECTED] validated {len(samples)} samples")
        else:
            print(f"[PASS] validated {len(samples)} samples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
    )


def write_runner(repo: Path, fields: dict[str, str]) -> None:
    path = repo / "run_benchmark.sh"
    if not _is_empty(path):
        return
    params = _parameters(fields)
    description = (fields.get("Execution Description With Parameters") or "Run the configured benchmark.").split(".")[0] + "."
    option_lines = [f"  {_flag_of(name)} <value>            Override {name}" for name in params] or ["  (none)"]
    parse_cases = "\n".join(f'    {_flag_of(name)}) {name.upper()}="${{2:-}}"; shift 2 ;;' for name in params)
    yaml_assigns = "\n".join(
        f'{name.upper()}="${{{name.upper()}:-$(yaml_get {name})}}"' for name in params
    )
    resolved_parts = "\n".join(
        f'[[ -n "${{{name.upper()}}}" ]] && BENCHMARK_RUN_COMMAND+=" {_flag_of(name)} $(printf %q "${{{name.upper()}}}")"'
        for name in params
    )
    param_inits = "\n".join(f'{name.upper()}=""' for name in params)
    help_flags = "".join(
        f'  grep -q -- \'{_flag_of(name)}\' <<<"${{help}}" && collect_args+=({_flag_of(name)} "${{{name.upper()}}}")\n'
        for name in params
    )
    _write(
        path,
        f"""#!/usr/bin/env bash
# File: run_benchmark.sh
# Description: {description}
# Execution: bash run_benchmark.sh [--profile smoke|baseline|extended] [--validate]
# Options: --profile, --smoke, --baseline, --extended, --device, --phase, --raw-file, --config, --validate, --help
# Requirements: bash, python3, repository-local .venv
# Dependencies: common.sh, collect_workload.py
# License: Apache-2.0
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
REPO_NAME="$(basename "${{REPO_ROOT}}")"
cd "${{REPO_ROOT}}"
# shellcheck disable=SC1091
source scripts/lib/common.sh
capture_benchmark_run_command_submitted "$@"

usage() {{
  cat <<'USAGE'
Usage: bash run_benchmark.sh [OPTIONS]

{description}

Profiles:
  --profile <name>              Run profile: smoke|baseline|extended (default: smoke)
  --smoke                       Run smoke profile
  --baseline                    Run baseline profile
  --extended                    Run extended profile

Execution:
  --device <gpu|cpu>            Execution device (default: gpu)
  --phase <phaseN|N>            Run one phase (phase1|phase2|phase3|phase4, or 1-4)
  --phase1                      Collection
  --phase2                      Collection alias
  --phase3                      Parse only; requires --raw-file <path>
  --phase4                      Validation only
  --raw-file <path>             Existing raw file for --phase3
  --config <file>               Config file (default: config/benchmark_config.yaml)

Validation and logging:
  --validate                    Enable result validation (default)
  --no-validate                 Skip result validation
  --quiet                       Suppress nonessential stdout
  --log-level <level>           ERROR|WARN|INFO|DEBUG (default: INFO)
  --output-format <fmt>         Override config output_format
  --save-options-file <path>    Write resolved CLI options to PATH

Workload options:
{chr(10).join(option_lines)}

Information:
  --specification               Print this workload's specification and exit
  --matrix-definition           Same as --specification
  --help                        Show this help and exit

Examples:
  bash run_benchmark.sh --profile smoke --validate
  bash run_benchmark.sh --baseline --device gpu
  bash run_benchmark.sh --phase3 --raw-file results/raw/<run>/raw_output.txt
USAGE
}}

for _help_arg in "$@"; do
  case "${{_help_arg}}" in
    --help) usage; exit 0 ;;
    --specification|--matrix-definition)
      python3 scripts/print_benchmark_definition.py
      exit 0
      ;;
  esac
done

PROFILE="smoke"
DEVICE="gpu"
PHASE="all"
RAW_FILE=""
CONFIG_FILE="config/benchmark_config.yaml"
VALIDATE=1
QUIET=0
LOG_LEVEL_VALUE="INFO"
OUTPUT_FORMAT=""
SAVE_OPTIONS_FILE=""
{param_inits}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="${{2:-}}"; shift 2 ;;
    --smoke) PROFILE="smoke"; shift ;;
    --baseline) PROFILE="baseline"; shift ;;
    --extended) PROFILE="extended"; shift ;;
    --device) DEVICE="${{2:-}}"; shift 2 ;;
    --phase) PHASE="${{2:-}}"; shift 2 ;;
    --phase1|--phase2) PHASE="1"; shift ;;
    --phase3) PHASE="3"; shift ;;
    --phase4) PHASE="4"; shift ;;
    --raw-file) RAW_FILE="${{2:-}}"; shift 2 ;;
    --config) CONFIG_FILE="${{2:-}}"; shift 2 ;;
    --validate) VALIDATE=1; shift ;;
    --no-validate) VALIDATE=0; shift ;;
    --quiet) QUIET=1; shift ;;
    --log-level) LOG_LEVEL_VALUE="${{2:-}}"; shift 2 ;;
    --output-format) OUTPUT_FORMAT="${{2:-}}"; shift 2 ;;
    --save-options-file) SAVE_OPTIONS_FILE="${{2:-}}"; shift 2 ;;
{parse_cases}
    --help|--specification|--matrix-definition) shift ;;
    *) die "Unknown option: $1" ;;
  esac
done

case "${{PHASE}}" in
  all|phase1|phase2|phase3|phase4|1|2|3|4) ;;
  *) die "Unsupported --phase value: ${{PHASE}}" ;;
esac
if [[ "${{PHASE}}" == phase* ]]; then PHASE="${{PHASE#phase}}"; fi

set_log_level "${{LOG_LEVEL_VALUE}}"
begin_benchmark_run "${{PROFILE}}"
if [[ "${{PHASE}}" != "3" && "${{PHASE}}" != "4" ]]; then
  bash scripts/ensure_setup.sh
fi
mark_benchmark_measure_start
PYTHON_BIN="${{REPO_ROOT}}/.venv/bin/python"
[[ -x "${{PYTHON_BIN}}" ]] || die "Missing ${{PYTHON_BIN}}; run bash setup.sh --assume-yes first."

yaml_get() {{
  "${{PYTHON_BIN}}" - "${{CONFIG_FILE}}" "${{PROFILE}}" "$1" <<'PY'
import sys
from pathlib import Path
import yaml
key = sys.argv[3]
profile = sys.argv[2]
cfg = yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8")) or {{}}
sweep = cfg.get("sweep") or {{}}
raw_value = sweep.get(key, "")
if isinstance(raw_value, dict):
    raw_value = raw_value.get(profile, next(iter(raw_value.values()), ""))
if isinstance(raw_value, list):
    raw_value = ",".join(str(item) for item in raw_value)
print("" if raw_value is None else raw_value)
PY
}}

{yaml_assigns}
OUTPUT_FORMAT="${{OUTPUT_FORMAT:-$(yaml_get output_format)}}"
OUTPUT_FORMAT="${{OUTPUT_FORMAT:-csv}}"

BENCHMARK_RUN_COMMAND="bash run_benchmark.sh --${{PROFILE}}"
[[ "${{VALIDATE}}" -eq 1 ]] && BENCHMARK_RUN_COMMAND+=" --validate"
{resolved_parts}
set_benchmark_run_command "${{BENCHMARK_RUN_COMMAND}}"

HOSTNAME_VALUE="$(hostname -s 2>/dev/null || hostname)"
STAMP="$(date -u +"%Y%m%d_%H%M%S")"
if [[ -z "${{RAW_FILE}}" ]]; then
  RUN_DIR="${{REPO_ROOT}}/results/raw/${{STAMP}}_${{REPO_NAME}}_${{HOSTNAME_VALUE}}"
  mkdir -p "${{RUN_DIR}}"
  RAW_FILE="${{RUN_DIR}}/raw_output.txt"
else
  RUN_DIR="$(cd "$(dirname "${{RAW_FILE}}")" && pwd)"
fi
set_benchmark_run_dir "${{RUN_DIR}}"
COMMAND_LOG="${{RUN_DIR}}/commands_executed.sh"
{{ echo "#!/usr/bin/env bash"; echo "set -euo pipefail"; }} > "${{COMMAND_LOG}}"
chmod +x "${{COMMAND_LOG}}"
[[ -n "${{SAVE_OPTIONS_FILE}}" ]] && printf 'profile=%s\\noutput_format=%s\\n' "${{PROFILE}}" "${{OUTPUT_FORMAT}}" > "${{SAVE_OPTIONS_FILE}}"
printf 'profile=%s\\ndevice=%s\\noutput_format=%s\\n' "${{PROFILE}}" "${{DEVICE}}" "${{OUTPUT_FORMAT}}" > "${{RUN_DIR}}/cli_options.env"
export PYTHONUNBUFFERED=1
export PATH="/opt/rocm/bin:${{PATH}}"
export LD_LIBRARY_PATH="/opt/rocm/lib:/opt/rocm/lib64:${{LD_LIBRARY_PATH:-}}"
cp run_benchmark.sh "${{RUN_DIR}}/script.sh"
mask_environment "${{RUN_DIR}}/env_variables.txt"
: > "${{RUN_DIR}}/run.log"

run_collection() {{
  log_section "Collection"
  local help collect_cmd
  local -a collect_args=(--run-dir "${{RUN_DIR}}" --raw-file "${{RAW_FILE}}" --profile "${{PROFILE}}")
  help="$("${{PYTHON_BIN}}" scripts/collect_workload.py --help 2>&1 || true)"
  grep -q -- '--config' <<<"${{help}}" && collect_args+=(--config "${{CONFIG_FILE}}")
  # A substring grep for '--device' also matches '--device-id' (it's a
  # prefix), which made the harness pass the literal word "gpu"/"cpu" as
  # --device onto a collector that only defines --device-id; argparse then
  # prefix-matched it and int("gpu") crashed before any RESULT/CSV line.
  # Require a standalone --device flag, and fall back to --device-id with a
  # numeric index when only that flag exists.
  if grep -qE -- '(^|[^-])--device([[:space:],]|$)' <<<"${{help}}"; then
    collect_args+=(--device "${{DEVICE}}")
  elif grep -qE -- '(^|[^-])--device-id([[:space:],]|$)' <<<"${{help}}"; then
    collect_args+=(--device-id "${{DEVICE_ID:-0}}")
  fi
  grep -q -- '--output-format' <<<"${{help}}" && collect_args+=(--output-format "${{OUTPUT_FORMAT}}")
{help_flags}
  printf -v collect_cmd '%q ' "${{PYTHON_BIN}}" scripts/collect_workload.py "${{collect_args[@]}}"
  echo "[RUN] ${{collect_cmd}}"
  echo "${{collect_cmd}}" >> "${{COMMAND_LOG}}"
  set +e
  "${{PYTHON_BIN}}" scripts/collect_workload.py "${{collect_args[@]}}" 2>&1 | tee -a "${{RUN_DIR}}/run.log"
  command_status="${{PIPESTATUS[0]}}"
  set -e
  if [[ "${{command_status}}" -ne 0 ]]; then
    die "collection failed with status ${{command_status}}"
  fi
}}

run_parse() {{
  log_section "Parse"
  local parse_cmd
  printf -v parse_cmd '%q ' "${{PYTHON_BIN}}" scripts/parse_results.py --raw-file "${{RAW_FILE}}" --db "${{REPO_ROOT}}/results/benchmark.db" --summary "${{REPO_ROOT}}/results/summary.json" --definition "${{REPO_ROOT}}/benchmark_specification.json" --run-dir "${{RUN_DIR}}"
  echo "[RUN] ${{parse_cmd}}"
  echo "${{parse_cmd}}" >> "${{COMMAND_LOG}}"
  "${{PYTHON_BIN}}" scripts/parse_results.py --raw-file "${{RAW_FILE}}" --db "${{REPO_ROOT}}/results/benchmark.db" --summary "${{REPO_ROOT}}/results/summary.json" --definition "${{REPO_ROOT}}/benchmark_specification.json" --run-dir "${{RUN_DIR}}" || die "parse failed"
}}

run_validate() {{
  log_section "Validation"
  local validate_cmd
  printf -v validate_cmd '%q ' "${{PYTHON_BIN}}" scripts/validate_results.py --db "${{REPO_ROOT}}/results/benchmark.db" --config "${{CONFIG_FILE}}"
  echo "[RUN] ${{validate_cmd}}"
  echo "${{validate_cmd}}" >> "${{COMMAND_LOG}}"
  "${{PYTHON_BIN}}" scripts/validate_results.py --db "${{REPO_ROOT}}/results/benchmark.db" --config "${{CONFIG_FILE}}" || die "validation failed"
}}

case "${{PHASE}}" in
  all|1|2) run_collection; run_parse; [[ "${{VALIDATE}}" -eq 1 ]] && run_validate ;;
  3) [[ -n "${{RAW_FILE}}" && -f "${{RAW_FILE}}" ]] || die "--phase3 requires --raw-file <existing file>"; run_parse ;;
  4) run_validate ;;
esac
record_benchmark_stop
capture_journal_warnings "${{RUN_DIR}}" "${{BENCHMARK_START_DATETIME}}" "${{STOP_TIME}}"
bash scripts/collect_hw_sw_info.sh "${{RUN_DIR}}"
START_EPOCH="$(date -u -d "${{BENCHMARK_START_DATETIME}}" +%s)"
STOP_EPOCH="$(date -u -d "${{STOP_TIME}}" +%s)"  # Ledger keeps whole seconds. The summary prints tenths.
ELAPSED="$((STOP_EPOCH - START_EPOCH))"
(( ELAPSED < 0 )) && ELAPSED=0
if [[ "${{QUIET}}" -eq 0 ]]; then
  bash scripts/print_run_metadata.sh "${{REPO_ROOT}}" || true
  echo "[INFO] ===== Benchmark Summary ====="
  echo "[INFO] Run ID: $(basename "${{RUN_DIR}}") | Status: ok | Samples: $(${{PYTHON_BIN}} -c 'import json; print(json.load(open("results/summary.json"))["sample_count"])') | Profile: ${{PROFILE}} | Device: $(display_device)"
  print_benchmark_summary_commands
  echo "[INFO] Start time: ${{BENCHMARK_START_DATETIME}}"
  echo "[INFO] Stop time: ${{STOP_TIME}}"
  echo "[INFO] Elapsed time: $(benchmark_elapsed_display) sec"
  echo "[INFO] Artifacts: ${{RUN_DIR}}"
  echo "[INFO] SQLite DB: ${{REPO_ROOT}}/results/benchmark.db"
  echo "[INFO]"
  "${{PYTHON_BIN}}" scripts/print_metric_summary.py --definition benchmark_specification.json --summary results/summary.json
  echo "[INFO]"
fi
write_metrics_summary_txt

"${{PYTHON_BIN}}" scripts/update_runtime_ledger.py \\
  --profile "${{PROFILE}}" --start-datetime "${{BENCHMARK_START_DATETIME}}" --total-runtime "${{ELAPSED}}" \\
  --exit-code 0 --failure-stage ok --failure-detail "" --raw-run-dir "${{RUN_DIR}}" \\
  --runtime-root "${{REPO_ROOT}}" \\
  --run-benchmark-command-submitted "${{BENCHMARK_RUN_COMMAND_SUBMITTED}}" \\
  --run-benchmark-command-fully-resolved "${{BENCHMARK_RUN_COMMAND}}" \\
  --notes "validated run" \\
  || printf '[WARN] Runtime ledger update failed\\n' >&2
finish_benchmark_run
""",
    )


def materialize_generated_harness(repo_root: Path) -> None:
    fields = _fields_of(repo_root)
    write_parser(repo_root)
    write_validator(repo_root)
    write_runner(repo_root, fields)
    collector = repo_root / "scripts" / "collect_workload.py"
    if not collector.is_file() or collector.stat().st_size == 0:
        print(
            "[WARN] No scripts/collect_workload.py overlay was copied. "
            "Implement the collector from the benchmark specification; "
            "do not invent a generic collector in the template."
        )
