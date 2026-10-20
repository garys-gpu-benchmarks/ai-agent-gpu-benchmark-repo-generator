#!/usr/bin/env python3
# File: scripts/metric_contract.py
# Description: Shared blank / zero / positive metric rules and percentile-key helpers.
from __future__ import annotations

import re

NOT_MEASURED = ""
MASHED_PERCENTILE_RE = re.compile(r"^(?P<stem>.+)_p50_p95_p99(?P<suffix>_[A-Za-z0-9]+)?$")


def is_blank(value: object) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return text == "" or text.lower() in {"none", "null", "nan", "not measured", "not_measured"}


def coerce_metric_value(value: object, *, zero_ok: bool = False) -> object:
    """Blank is omitted. Do not coerce empty string to 0.0."""
    if is_blank(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return NOT_MEASURED
    if number != number or number in (float("inf"), float("-inf")):
        return NOT_MEASURED
    if number == 0.0 and not zero_ok:
        # A recorded 0 is still a number; callers decide whether 0 is valid.
        return number
    return number


def unmash_p50_key(key: str) -> str:
    """D2: a mashed p50_p95_p99 display key is the p50 key."""
    match = MASHED_PERCENTILE_RE.match(str(key or ""))
    if not match:
        return str(key or "")
    return f"{match.group('stem')}_p50{match.group('suffix') or ''}"


def split_percentile_keys(key: str) -> list[str]:
    """D3: expand mashed p50_p95_p99 into the three real keys."""
    match = MASHED_PERCENTILE_RE.match(str(key or ""))
    if not match:
        return [str(key or "")]
    stem = match.group("stem")
    suffix = match.group("suffix") or ""
    return [f"{stem}_p50{suffix}", f"{stem}_p95{suffix}", f"{stem}_p99{suffix}"]


def percentile_triplet(values: list, pct_fn) -> dict[str, object]:
    """Return p50/p95/p99 for a value list. Blanks stay blank."""
    cleaned = [item for item in values if not is_blank(item)]
    return {
        "p50": pct_fn(cleaned, 0.50) if cleaned else "",
        "p95": pct_fn(cleaned, 0.95) if cleaned else "",
        "p99": pct_fn(cleaned, 0.99) if cleaned else "",
    }


def emit_percentile_metrics(stem: str, suffix: str, values: list, pct_fn) -> dict[str, object]:
    """Emit the split p50, p95, and p99 keys. The mashed alias is not published."""
    triplet = percentile_triplet(values, pct_fn)
    return {
        f"{stem}_p50{suffix}": triplet["p50"],
        f"{stem}_p95{suffix}": triplet["p95"],
        f"{stem}_p99{suffix}": triplet["p99"],
    }


def itl_must_not_copy_tpot(itl_value: object, tpot_value: object) -> object:
    """D4: ITL is blank when it was not measured. Never copy TPOT."""
    if is_blank(itl_value):
        return ""
    if not is_blank(tpot_value) and str(itl_value) == str(tpot_value):
        return ""
    return itl_value


ITL_TPOT_PAIRS_MSEC = (
    ("inter_token_latency_itl_p50_msec", "time_per_output_token_tpot_p50_msec"),
    ("inter_token_latency_itl_p95_msec", "time_per_output_token_tpot_p95_msec"),
    ("inter_token_latency_itl_p99_msec", "time_per_output_token_tpot_p99_msec"),
)


def apply_itl_contract(metrics: dict, pairs: tuple[tuple[str, str], ...] = ITL_TPOT_PAIRS_MSEC) -> dict:
    """Blank every ITL column that repeats the paired TPOT column."""
    for itl_key, tpot_key in pairs:
        if itl_key in metrics:
            metrics[itl_key] = itl_must_not_copy_tpot(metrics.get(itl_key, ""), metrics.get(tpot_key, ""))
    return metrics


# ---------------------------------------------------------------------------
# Publication contract
#
# Numbered metrics are comparable only when the name, unit, statistic, and
# hardware they claim are the ones that were actually measured. The helpers
# below are the single registry for that rule. Generated repos copy this
# module to scripts/metric_contract.py.
# ---------------------------------------------------------------------------

STUB_NA = "na (stub server, smoke only)"
SMOKE_STANDIN_STATUS = "SMOKE-STANDIN"
NA_EXPECTED_STATUS = "N/A-EXPECTED"
INCOMPLETE_STATUS = "INCOMPLETE"
PASS_STATUS = "PASS"

P99_MIN_SAMPLES = 100
P95_MIN_SAMPLES = 20
CACHE_LLC_MULTIPLE = 4

NA_REASON_RE = re.compile(r"^na \(.+\)$", re.IGNORECASE)

# stored key -> (canonical key, multiply stored value to get canonical units)
STORAGE_ALIASES: dict[str, tuple[str, float]] = {
    "first_image_latency_sec": ("first_image_latency_ms", 1000.0),
    "first_image_latency_s": ("first_image_latency_ms", 1000.0),
    "gpu_mem_gb": ("peak_gpu_memory_gb", 1.0),
    "hbm3_coverage_gb": ("allocated_verification_buffer_gb", 1.0),
    "achieved_tflops": ("modeled_tflops", 1.0),
    "gflops": ("modeled_gflops_per_s", 1.0),
    "memory_bandwidth_gb_s": ("min_operand_traffic_gb_s", 1.0),
    "memory_bandwidth_gbps": ("min_operand_traffic_gb_s", 1.0),
    # 2026-10-18 key renames: the old stored key still resolves to the new
    # numbered-metric key, so earlier summary.json files keep printing.
    # fp16_tflops (221/421), tflops_fwd (218/418) and achieved_compute_tflops
    # (GEMM 117/217/317/417, exact 2*M*N*K FLOPs) are now the numbered keys
    # themselves, so their old modeled_* aliases were removed. Keys that stay
    # canonical for a sibling workload are not aliased: gpu_system_ecc_error_count
    # (203/403), peak_gpu_junction_temp_c (103/303) and latency_us (114/314).
    "kernel_driver_mismatch_count": ("kernel_release_mismatch_count", 1.0),
    "even_word_store_pass_rate": ("loop_verification_pass_pct", 1.0),
    "algbw_gb_s": ("allreduce_algbw_gb_s", 1.0),
    "busbw_gb_s": ("allreduce_busbw_gb_s", 1.0),
    "walking_1s_moving_inversion_pass_rate": ("fixed_pattern_fill_verify_pass_rate", 1.0),
    "sustained_decode_throughput_under_cache_pressure_tokens_sec": ("decode_throughput_tokens_sec", 1.0),
}

# Reviewed device peaks. A percent-of-peak or HBM label is published only when
# the detected GPU matches one of these rows. MI300X FP64 matrix peak is the
# packed matrix rate (163.4); the vector rate is 81.7. H100 figures are the
# published NVIDIA product rates, keyed by the SXM / NVL / PCIe form.
DEVICE_SPECS: dict[str, dict[str, float | str]] = {
    "MI300X": {
        "fp64_matrix_tflops": 163.4,
        "fp64_vector_tflops": 81.7,
        "hbm_gbps": 5300.0,
        "memory_type": "HBM3",
        "gpu_cache_bytes": 256 * 1024**2,
        "llc_bytes": 32 * 1024**2,
    },
    "H100 SXM": {
        "fp64_matrix_tflops": 67.0,
        "fp64_vector_tflops": 33.5,
        "hbm_gbps": 3350.0,
        "memory_type": "HBM3",
        "gpu_cache_bytes": 50 * 1024**2,
        "llc_bytes": 32 * 1024**2,
    },
    "H100 NVL": {
        "fp64_matrix_tflops": 67.0,
        "fp64_vector_tflops": 34.0,
        "hbm_gbps": 3900.0,
        "memory_type": "HBM3",
        "gpu_cache_bytes": 50 * 1024**2,
        "llc_bytes": 32 * 1024**2,
    },
    "H100 PCIe": {
        "fp64_matrix_tflops": 51.0,
        "fp64_vector_tflops": 26.0,
        "hbm_gbps": 2000.0,
        "memory_type": "HBM2e",
        "gpu_cache_bytes": 50 * 1024**2,
        "llc_bytes": 32 * 1024**2,
    },
}

_SERVING_TOKENS = (
    "ttft", "tpot", "itl", "latency", "throughput", "token",
    "radix", "completed_request",
)
_DEVICE_BANDWIDTH_KEYS = (
    "bandwidth_gb_s_",
    "copy_bandwidth_gb_s",
    "scale_bandwidth_gb_s",
    "add_bandwidth_gb_s",
    "triad_bandwidth_gb_s",
)


def is_explicit_na(value: object) -> bool:
    return bool(NA_REASON_RE.match(str(value).strip())) if value is not None else False


def is_standin_text(text: str) -> bool:
    lowered = (text or "").lower()
    if "tiny_sglang_server" in lowered or "tiny-sglang" in lowered:
        return True
    if "server_identity" in lowered and "stub" in lowered:
        return True
    if "x-benchmark-server" in lowered and "stub" in lowered:
        return True
    return False


def apply_storage_aliases(metrics: dict) -> dict:
    """Copy aliased storage keys onto the canonical key, converting units."""
    out = dict(metrics)
    for stored, (canonical, scale) in STORAGE_ALIASES.items():
        if stored not in out or canonical in out:
            continue
        raw = out[stored]
        if is_explicit_na(raw) or is_blank(raw):
            out[canonical] = raw
            continue
        try:
            out[canonical] = float(raw) * scale
        except (TypeError, ValueError):
            continue
    return out


def units_compatible(requested: str, stored: str) -> bool:
    """Reject a fuzzy key match whose unit suffix disagrees."""
    requested_n = re.sub(r"[^a-z0-9]+", "_", requested.lower()).strip("_")
    stored_n = re.sub(r"[^a-z0-9]+", "_", stored.lower()).strip("_")
    suffixes = ("_msec", "_ms", "_sec", "_us", "_ns", "_gb_s", "_gbps")
    req = next((item for item in suffixes if requested_n.endswith(item)), "")
    got = next((item for item in suffixes if stored_n.endswith(item)), "")
    if not req or not got:
        return True
    same = {("_ms", "_msec"), ("_msec", "_ms"), ("_sec", "_s"), ("_s", "_sec")}
    return req == got or (req, got) in same or (got, req) in same


def guarded_percentile(values: list, q: float, statistic: str) -> object:
    """Publish p99 only for n>=100 and p95 only for n>=20. Otherwise na."""
    cleaned: list[float] = []
    for item in values:
        if is_blank(item) or is_explicit_na(item):
            continue
        try:
            cleaned.append(float(item))
        except (TypeError, ValueError):
            continue
    n = len(cleaned)
    if statistic == "p99" and n < P99_MIN_SAMPLES:
        return f"na (p99 requires at least {P99_MIN_SAMPLES} samples; n={n})"
    if statistic == "p95" and n < P95_MIN_SAMPLES:
        return f"na (p95 requires at least {P95_MIN_SAMPLES} samples; n={n})"
    if not cleaned:
        return ""
    ordered = sorted(cleaned)
    if statistic == "max":
        return ordered[-1]
    pos = (len(ordered) - 1) * q
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def sample_max(values: list) -> object:
    cleaned: list[float] = []
    for item in values:
        try:
            cleaned.append(float(item))
        except (TypeError, ValueError):
            continue
    return max(cleaned) if cleaned else ""


def finalize_serving_publication(metrics: dict, identity_text: str) -> tuple[dict, str]:
    """Stand-in servers must not publish sleep timings under SGLang metric names."""
    if not is_standin_text(identity_text):
        return dict(metrics), "ok"
    redacted: dict = {}
    for key, value in metrics.items():
        lowered = str(key).lower()
        if lowered.startswith("stub_") or lowered in {"workload_kind", "server_identity"}:
            redacted[key] = value
            continue
        if any(token in lowered for token in _SERVING_TOKENS):
            if not is_explicit_na(value):
                redacted[f"stub_{key}"] = value
            redacted[key] = STUB_NA
            continue
        redacted[key] = value
    redacted["workload_kind"] = "standin"
    redacted["server_identity"] = "stub"
    return redacted, "stub"


def gpu_form_tokens(name: str) -> set[str]:
    text = (name or "").lower().replace("_", " ").replace("-", " ")
    tokens: set[str] = set()
    if "mi300" in text:
        tokens.add("mi300x")
    if "h100" in text:
        tokens.add("h100")
    if "sxm" in text:
        tokens.add("sxm")
    if "nvl" in text:
        tokens.add("nvl")
    if "pcie" in text or "pci e" in text:
        tokens.add("pcie")
    return tokens


def same_gpu(detected: str, spreadsheet: str) -> bool:
    """H100 SXM, H100 NVL, and H100 PCIe are different devices."""
    left = gpu_form_tokens(detected)
    right = gpu_form_tokens(spreadsheet)
    if not left or not right:
        return True
    if "mi300x" in left or "mi300x" in right:
        return "mi300x" in left and "mi300x" in right
    if "h100" in left or "h100" in right:
        if "h100" not in left or "h100" not in right:
            return False
        form_left = left & {"sxm", "nvl", "pcie"}
        form_right = right & {"sxm", "nvl", "pcie"}
        if form_left and form_right and form_left != form_right:
            return False
        return True
    return left == right


def gpu_model_note(detected: str, spreadsheet: str) -> str:
    if not str(detected or "").strip() or not str(spreadsheet or "").strip():
        return ""
    if same_gpu(detected, spreadsheet):
        return ""
    return f"detected GPU {detected} differs from spreadsheet GPU Model {spreadsheet}"


def lookup_device(gpu_name: str) -> tuple[str, dict]:
    tokens = gpu_form_tokens(gpu_name)
    if "mi300x" in tokens:
        return "MI300X", dict(DEVICE_SPECS["MI300X"])
    if "h100" in tokens:
        if "nvl" in tokens:
            return "H100 NVL", dict(DEVICE_SPECS["H100 NVL"])
        if "pcie" in tokens:
            return "H100 PCIe", dict(DEVICE_SPECS["H100 PCIe"])
        if "sxm" in tokens:
            return "H100 SXM", dict(DEVICE_SPECS["H100 SXM"])
        # nvidia-smi names the SXM part "NVIDIA H100 80GB HBM3" with no form word.
        # PCIe and NVL always name their form ("H100 PCIe", "H100 NVL").
        compact = (gpu_name or "").lower().replace(" ", "")
        if "hbm3" in compact or "80gb" in compact:
            return "H100 SXM", dict(DEVICE_SPECS["H100 SXM"])
    return "", {}


def detect_gpu_name() -> str:
    """One line naming GPU 0, from nvidia-smi, amd-smi, or rocminfo. Empty when none answers.

    summary.json carries no GPU name, so callers that annotate metrics probe here
    instead of passing "" (which fell back to generic cache sizes and skipped the
    peak-bandwidth check).
    """
    import subprocess

    def run(command: list[str]) -> str:
        try:
            completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return completed.stdout or ""

    for line in run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"]).splitlines():
        if line.strip() and "fail" not in line.lower():
            return line.strip()
    for command, label in (
        (["amd-smi", "static", "--asic"], "market_name"),
        (["amd-smi", "static"], "market_name"),
        (["rocminfo"], "marketing name"),
    ):
        for line in run(command).splitlines():
            key, sep, value = line.partition(":")
            value = value.strip()
            if sep and key.strip().lower() == label and value and value.upper() != "N/A":
                if command[0] != "rocminfo" or "instinct" in value.lower() or "mi" in value.lower():
                    return value
    return ""


def cache_resident_note(metrics: dict, gpu_name: str = "") -> str:
    """Ledger note for a working set that fits in the GPU (or CPU) cache, else ""."""
    if not metrics.get("cache_resident"):
        return ""
    size = _as_float(metrics.get("working_set_bytes"))
    label, _spec = lookup_device(gpu_name)
    domain = str(metrics.get("memory_domain") or "hbm")
    cache = _cache_bytes(domain, gpu_name)
    where = label or "unrecognized GPU, generic size"
    shown = f"{size / 1024**2:.0f} MiB" if size is not None else "working set"
    return (
        f"cache-resident at smoke size: {shown} working set is under {CACHE_LLC_MULTIPLE}x "
        f"the {cache // 1024**2} MiB cache ({where})"
    )


def fp64_matrix_peak(gpu_name: str) -> object:
    """Matrix-peak TFLOPS for the detected GPU, or an explicit na reason."""
    label, spec = lookup_device(gpu_name)
    if not spec:
        shown = gpu_name.strip() or "unresolved GPU"
        return f"na (no reviewed FP64 matrix peak for {shown})"
    return float(spec["fp64_matrix_tflops"])


def _cache_bytes(domain: str, gpu_name: str) -> int:
    _label, spec = lookup_device(gpu_name)
    if domain == "hbm":
        if spec:
            return int(spec["gpu_cache_bytes"])
        return 50 * 1024**2
    if spec:
        return int(spec["llc_bytes"])
    return 32 * 1024**2


def cache_resident(working_set_bytes: float, domain: str, gpu_name: str = "") -> bool:
    cache = _cache_bytes(domain, gpu_name)
    return float(working_set_bytes) < CACHE_LLC_MULTIPLE * cache


def _as_float(value: object) -> float | None:
    if is_blank(value) or is_explicit_na(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_device_bandwidth_key(key: str) -> bool:
    lowered = key.lower()
    if lowered.startswith("bandwidth_gb_s"):
        return True
    if lowered.endswith("_bandwidth_gb_s"):
        return True
    return any(token in lowered for token in _DEVICE_BANDWIDTH_KEYS)


def annotate_metrics(metrics: dict, gpu_name: str = "") -> dict:
    """Apply aliases, cache-resident headlines, and peak-bandwidth checks."""
    out = apply_storage_aliases(metrics)
    size = _as_float(out.get("working_set_bytes"))
    domain = str(out.get("memory_domain") or "")
    if not domain:
        if any(str(key).startswith("bandwidth_gb_s") for key in out):
            domain = "hbm"
        elif any(str(key).endswith("_bandwidth_gb_s") for key in out):
            domain = "dram"
    if size is not None and domain and cache_resident(size, domain, gpu_name):
        out["cache_resident"] = 1
        point = str(out.get("headline_point") or "")
        qualifier = "(cache-resident at smoke size)"
        if qualifier not in point:
            out["headline_point"] = (point + " " + qualifier).strip()
    _label, spec = lookup_device(gpu_name)
    peak = float(spec["hbm_gbps"]) if spec and domain == "hbm" else None
    if peak:
        for key, value in list(out.items()):
            if not _is_device_bandwidth_key(str(key)):
                continue
            number = _as_float(value)
            if number is not None and number > peak * 1.05:
                out[key] = (
                    f"na (bandwidth {number:.4g} GB/s exceeds { _label } "
                    f"{spec['memory_type']} peak {peak:.4g} GB/s)"
                )
    return out


def classify_na(metric_key: str, reason: str, context: dict) -> str:
    """Return 'expected' or 'unexpected' for one explicit na value.

    A collector reports a counter the host does not have as ``na (expected: <reason>)``,
    which is accepted below. Do not add new string matches here for a new reason; make
    the collector emit that form instead (AGENTS.md, Batch Generation).
    """
    text = reason.lower()
    if "stub server" in text:
        return "expected"
    if text.startswith("na (expected:") or "na (expected:" in text:
        return "expected"
    if "second numa" in text or "at least two gpus" in text or "fewer than 2" in text:
        return "expected"
    if "perf_event_paranoid" in text or "pmu access denied" in text:
        return "expected"
    if "llc load counters unavailable" in text:
        return "expected"
    if "timed loop too short" in text or "timed loop shorter" in text:
        if str(context.get("profile") or "").lower() == "smoke" or "expected:" in text:
            return "expected"
        return "unexpected"
    if "cache-resident" in text or "exceeds" in text and "peak" in text:
        return "expected"
    if "requires at least" in text and "sample" in text:
        return "expected"
    lowered_key = metric_key.lower()
    gpu_count = context.get("gpu_count")
    try:
        gpus = int(gpu_count) if gpu_count not in (None, "") else None
    except (TypeError, ValueError):
        gpus = None
    if gpus is not None and gpus < 2 and any(token in lowered_key for token in ("busbw", "algbw", "allreduce", "all_reduce", "nccl", "rccl")):
        return "expected"
    numa = context.get("numa_nodes")
    try:
        nodes = int(numa) if numa not in (None, "") else None
    except (TypeError, ValueError):
        nodes = None
    if nodes is not None and nodes < 2 and "remote" in lowered_key:
        return "expected"
    return "unexpected"


def publication_status(pairs: list[tuple[str, object]], context: dict | None = None) -> tuple[str, int]:
    """PASS only when every numbered metric is a finite number.

    Expected na (hardware the profile cannot measure, or a declared smoke
    stand-in) is N/A-EXPECTED or SMOKE-STANDIN, never PASS. Any other gap is
    INCOMPLETE.
    """
    context = context or {}
    na_count = 0
    unexpected = 0
    expected = 0
    standin = bool(context.get("standin")) or str(context.get("status") or "").lower() in {"stub", "smoke-standin"}
    for key, value in pairs:
        if is_standin_text(str(value)) or (is_explicit_na(value) and "stub server" in str(value).lower()):
            standin = True
        if is_explicit_na(value):
            na_count += 1
            if classify_na(str(key), str(value), context) == "expected":
                expected += 1
            else:
                unexpected += 1
            continue
        if value == "NOT FOUND" or is_blank(value):
            na_count += 1
            unexpected += 1
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            na_count += 1
            unexpected += 1
            continue
        if number != number or number in (float("inf"), float("-inf")):
            na_count += 1
            unexpected += 1
    if standin:
        return SMOKE_STANDIN_STATUS, na_count
    if unexpected:
        return INCOMPLETE_STATUS, na_count
    if expected:
        return NA_EXPECTED_STATUS, na_count
    return PASS_STATUS, na_count


def text_dimension_key(description: str) -> bool:
    """A numbered metric whose only key is a text dimension fails validation."""
    match = re.search(r"\(([^()]*)\)\s*$", description.strip())
    if not match:
        return False
    key = re.sub(r"[^a-z0-9]+", "_", match.group(1).lower()).strip("_")
    return key in {"direction", "tier", "benchmark", "rw", "pinned_memory"}
