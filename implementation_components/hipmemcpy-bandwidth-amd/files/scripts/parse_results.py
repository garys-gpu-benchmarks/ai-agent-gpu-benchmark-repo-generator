#!/usr/bin/env python3
# File: scripts/parse_results.py
# Description: Parse raw collector CSV into SQLite and summary.json.
# Component override (hipmemcpy-bandwidth-amd): adds a peak-per-direction
# bandwidth metric. The base blind mean over "bandwidth_gbps" blends H2D,
# D2H, D2D and every swept transfer size into one number; small transfers
# are latency-dominated, not bandwidth-representative, so the standard
# "sustained bandwidth" figure is the value at the largest swept size, per
# direction. This adds bandwidth_<direction>_gbps (bandwidth at each
# direction's max transfer_size_bytes) and latency_<direction>_us (time per
# copy at each direction's min transfer_size_bytes; the time per 1 GB copy is
# not a latency). The blind-mean "bandwidth_gbps"/"latency_us" summary values
# are still written but are not workbook metrics.
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

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x00")
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


def parse_csv_blocks(text: str) -> tuple[list[dict[str, str]], dict[str, str]]:
    metadata: dict[str, str] = {}
    rows: list[dict[str, str]] = []
    header = None
    for raw_line in text.splitlines():
        line = strip_ansi(raw_line).strip()
        if not line:
            continue
        if line.startswith("#"):
            for match in re.finditer(r"([A-Za-z0-9_]+)=([^\s]+)", line):
                metadata[match.group(1)] = match.group(2)
            continue
        if line.lower().startswith("stats:"):
            line = line.split(":", 1)[1].strip()
        if "," not in line:
            continue
        cells = next(csv.reader(io.StringIO(line)))
        if header is None:
            first = cells[0].strip().lower()
            ident = all(re.match(r"^[A-Za-z_][A-Za-z0-9_\-/]*$", cell.strip()) for cell in cells if cell.strip())
            if first not in {"sample_index", "check_name", "name", "solver", "kind", "step", "batch_size", "benchmark"} and not ident:
                continue
            header = [normalize_header(cell) for cell in cells]
            continue
        if cells and cells[0].lower() in {"name", "solver", "sample_index"}:
            if header and cells[0].lower() == header[0]:
                continue
        row = {header[i]: cells[i] if i < len(cells) else "" for i in range(len(header))}
        rows.append(row)
    if not rows:
        raise SystemExit("[FAIL] No supported raw output rows were parsed.")
    return rows, metadata


_NUMBER_RE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")


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
    if lead in {"peak", "max", "maximum"} and second not in {"percent", "pct"}:
        return max(values)
    if lead in {"min", "minimum"}:
        return min(values)
    return statistics.mean(values)


_PIVOT_GROUP_COLUMNS = {"tier", "benchmark"}
# "benchmark" covers lmbench-style long-format tables: one row per named
# micro-benchmark (lat_ctx, bw_mem, bw_pipe, ...) sharing a single generic
# "value" column, rather than one column per benchmark. When the group
# column's own values already read as a metric name (unlike "tier", which
# needs a "latency_ns_" prefix to stay meaningful), and there is exactly
# one other numeric column to pivot, the bare group value name is used
# directly as the key instead of "<column>_<group>" -- see below.


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
            # with megabyte/sec bandwidths. Drop it now that the honest,
            # per-group replacement keys are being added below.
            summary_metrics.pop(col, None)
            for group_val, mean_val in per_group_means.items():
                slug = re.sub(r"[^A-Za-z0-9]+", "_", group_val).strip("_").lower()
                key = slug if use_bare_group_name else f"{col}_{slug}"
                if key in summary_metrics and use_bare_group_name:
                    # Guard against an accidental collision with a real column
                    # name -- fall back to the disambiguated form rather than
                    # silently overwriting an unrelated metric.
                    key = f"{col}_{slug}"
                summary_metrics[key] = mean_val
    return summary_metrics



def add_peak_direction_bandwidth(rows, metrics_summary):
    """Peak per-direction bandwidth at the largest swept transfer size.

    hip_memcpy_bw.cpp sweeps min_bytes..max_bytes for each direction and
    reports a real, independently-timed bandwidth_gbps for every (direction,
    transfer_size_bytes) pair. The base aggregate above blind-means all of
    that together, which both blends the three directions and averages in
    small, latency-dominated transfer sizes that are not representative of
    sustained bandwidth. This isolates the standard sustained-bandwidth
    figure instead: for each direction, the mean bandwidth_gbps among rows
    at that direction's own max transfer_size_bytes (normally a single row).
    Keys: bandwidth_h2d_gbps, bandwidth_d2h_gbps, bandwidth_d2d_gbps.
    """
    by_direction: dict[str, list[dict]] = {}
    for row in rows:
        direction = str(row.get("direction", "")).strip().upper()
        if direction:
            by_direction.setdefault(direction, []).append(row)
    for direction, direction_rows in by_direction.items():
        sizes = [to_number(row.get("transfer_size_bytes", "")) for row in direction_rows]
        sizes = [s for s in sizes if isinstance(s, (int, float))]
        if not sizes:
            continue
        max_size = max(sizes)
        peak_values = []
        for row in direction_rows:
            size = to_number(row.get("transfer_size_bytes", ""))
            bw = to_number(row.get("bandwidth_gbps", ""))
            if size == max_size and isinstance(bw, (int, float)):
                peak_values.append(bw)
        if peak_values:
            slug = re.sub(r"[^A-Za-z0-9]+", "_", direction).strip("_").lower()
            metrics_summary[f"bandwidth_{slug}_gbps"] = statistics.mean(peak_values)

def add_min_size_direction_latency(rows, metrics_summary):
    """Per-direction latency at the smallest swept transfer size.

    latency_us is the time per copy. At 1 GB that is milliseconds of data
    movement, not latency, so the blind mean over every size and direction
    was dominated by the largest copies. The standard small-transfer latency
    is the time per copy at the smallest size: for each direction, the mean
    latency_us among rows at that direction's own min transfer_size_bytes
    (normally a single row). Keys: latency_h2d_us, latency_d2h_us, latency_d2d_us.
    """
    by_direction: dict[str, list[dict]] = {}
    for row in rows:
        direction = str(row.get("direction", "")).strip().upper()
        if direction:
            by_direction.setdefault(direction, []).append(row)
    for direction, direction_rows in by_direction.items():
        sizes = [to_number(row.get("transfer_size_bytes", "")) for row in direction_rows]
        sizes = [s for s in sizes if isinstance(s, (int, float))]
        if not sizes:
            continue
        min_size = min(sizes)
        values = []
        for row in direction_rows:
            size = to_number(row.get("transfer_size_bytes", ""))
            latency = to_number(row.get("latency_us", ""))
            if size == min_size and isinstance(latency, (int, float)):
                values.append(latency)
        if values:
            slug = re.sub(r"[^A-Za-z0-9]+", "_", direction).strip("_").lower()
            metrics_summary[f"latency_{slug}_us"] = statistics.mean(values)


def apply_h2d_headlines(rows, metrics_summary):
    """Numbered hipMemcpy metrics are the H2D point, not a blend of every size.

    bandwidth_GBps is H2D at the largest transfer. latency_us is H2D at the
    smallest transfer. headline_transfer_bytes is that largest size.
    """
    sizes = []
    for row in rows:
        size = to_number(row.get("transfer_size_bytes", ""))
        if isinstance(size, (int, float)):
            sizes.append(float(size))
    if not sizes:
        return
    max_size = max(sizes)
    metrics_summary["headline_transfer_bytes"] = int(max_size)
    if "bandwidth_h2d_gbps" in metrics_summary:
        metrics_summary["bandwidth_gbps"] = metrics_summary["bandwidth_h2d_gbps"]
    if "latency_h2d_us" in metrics_summary:
        metrics_summary["latency_us"] = metrics_summary["latency_h2d_us"]
    mib = max_size / (1024.0 * 1024.0)
    mib_text = str(int(mib)) if float(mib).is_integer() else f"{mib:.3g}"
    metrics_summary["headline_point"] = f"at {mib_text} MiB H2D"


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
    text = strip_ansi(raw_path.read_text(encoding="utf-8", errors="replace"))
    rows, metadata = parse_csv_blocks(text)
    skip = {
        # Sample-identity columns the raw CSV is expected to carry and that
        # are handled specially below (not generic metrics).
        "sample_index", "status", "error_message", "check_name",
        "rc", "command", "check",
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
    add_peak_direction_bandwidth(rows, metrics_summary)
    add_min_size_direction_latency(rows, metrics_summary)
    apply_h2d_headlines(rows, metrics_summary)
    summary = {"sample_count": len(rows), "status": status, "metrics": metrics_summary, "run_id": run_id}
    Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
    Path(args.summary).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if args.run_dir:
        run_dir = Path(args.run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "raw_results.csv").write_text(raw_path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        (run_dir / "raw_results.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    print(f"[PASS] parsed {len(rows)} samples into {db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
