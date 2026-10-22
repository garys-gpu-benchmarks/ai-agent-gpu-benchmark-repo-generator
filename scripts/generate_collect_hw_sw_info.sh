#!/usr/bin/env bash
# File: scripts/generate_collect_hw_sw_info.sh
# Description: Generate the standalone post-run HW/SW inventory collector from Excel.
# Requirements: Bash, Python 3 standard library.
# Execution: bash scripts/generate_collect_hw_sw_info.sh
# Outputs: scripts/collect_hw_sw_info.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
XLSX_FILE="${1:-${REPO_ROOT}/config/hw_sw_info_commands.xlsx}"
OUTPUT_SCRIPT="${2:-${SCRIPT_DIR}/collect_hw_sw_info.sh}"

if [[ ! -f "$XLSX_FILE" ]]; then
    echo "ERROR: Excel file not found: $XLSX_FILE" >&2
    echo "Usage: $0 [hw_sw_info_commands.xlsx] [collect_hw_sw_info.sh]" >&2
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 is required to read the XLSX file." >&2
    exit 1
fi

python3 - "$XLSX_FILE" "$OUTPUT_SCRIPT" <<'PY'
import base64
import os
import re
import stat
import sys
import zipfile
import xml.etree.ElementTree as ET

xlsx_path = sys.argv[1]
out_path = sys.argv[2]

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL_DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_REL_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"

REQUIRED = {"Save Sequence", "Vendor", "Info Domain", "Command", "Description"}


def col_index(cell_ref: str) -> int:
    letters = re.match(r"[A-Z]+", cell_ref or "")
    if not letters:
        return 0
    n = 0
    for ch in letters.group(0):
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n - 1


def get_shared_strings(zf):
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    out = []
    for si in root.findall(f"{{{NS_MAIN}}}si"):
        parts = [t.text or "" for t in si.iter(f"{{{NS_MAIN}}}t")]
        out.append("".join(parts))
    return out


def cell_value(cell, shared):
    ctype = cell.attrib.get("t")
    if ctype == "inlineStr":
        is_node = cell.find(f"{{{NS_MAIN}}}is")
        if is_node is None:
            return ""
        return "".join((t.text or "") for t in is_node.iter(f"{{{NS_MAIN}}}t"))
    v = cell.find(f"{{{NS_MAIN}}}v")
    if v is None or v.text is None:
        return ""
    if ctype == "s":
        try:
            return shared[int(v.text)]
        except (ValueError, IndexError):
            return ""
    return v.text


def sheet_paths(zf):
    wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
    rel_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rels = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rel_root.findall(f"{{{NS_REL_PKG}}}Relationship")
    }
    for sheet in wb_root.findall(f".//{{{NS_MAIN}}}sheet"):
        name = sheet.attrib.get("name", "")
        rid = sheet.attrib.get(f"{{{NS_REL_DOC}}}id")
        target = rels.get(rid, "")
        if not target:
            continue
        if target.startswith("/"):
            path = target.lstrip("/")
        else:
            path = "xl/" + target.lstrip("/")
        yield name, path


def read_sheet(zf, path, shared):
    root = ET.fromstring(zf.read(path))
    rows = []
    for row in root.findall(f".//{{{NS_MAIN}}}row"):
        vals = {}
        for cell in row.findall(f"{{{NS_MAIN}}}c"):
            idx = col_index(cell.attrib.get("r", "A1"))
            vals[idx] = cell_value(cell, shared)
        if vals:
            max_idx = max(vals)
            rows.append([vals.get(i, "") for i in range(max_idx + 1)])
        else:
            rows.append([])
    return rows


def normalized_header(row):
    return [str(x).strip() for x in row]


def as_number(value):
    s = str(value).strip()
    try:
        return float(s)
    except ValueError:
        return float("inf")


def b64(text):
    return base64.b64encode(str(text).encode("utf-8")).decode("ascii")

with zipfile.ZipFile(xlsx_path, "r") as zf:
    shared = get_shared_strings(zf)
    command_rows = None
    source_sheet = None

    for sheet_name, path in sheet_paths(zf):
        rows = read_sheet(zf, path, shared)
        if not rows:
            continue
        headers = normalized_header(rows[0])
        if REQUIRED.issubset(set(headers)):
            idx = {h: headers.index(h) for h in REQUIRED}
            parsed = []
            for row in rows[1:]:
                def field(name):
                    i = idx[name]
                    return row[i].strip() if i < len(row) and row[i] is not None else ""

                seq = field("Save Sequence")
                vendor = field("Vendor")
                domain = field("Info Domain").lower()
                command = field("Command")
                description = field("Description")
                if not command or domain not in {"hardware", "software"}:
                    continue
                parsed.append((as_number(seq), seq, vendor, domain, command, description))

            if parsed:
                command_rows = sorted(parsed, key=lambda x: (x[0], x[1]))
                source_sheet = sheet_name
                break

if not command_rows:
    raise SystemExit(
        "ERROR: Could not find a worksheet containing headers: "
        + ", ".join(sorted(REQUIRED))
    )

data_lines = []
for _, seq, vendor, domain, command, description in command_rows:
    data_lines.append("\t".join([seq, vendor, domain, b64(command), b64(description)]))
embedded_data = "\n".join(data_lines)

collector = r'''#!/usr/bin/env bash
# Generated by generate_collect_hw_sw_info.sh from __SOURCE_FILE__ (sheet: __SOURCE_SHEET__).
# Stand-alone VM inventory collector: the XLSX file is NOT required at runtime.
set -u
set -o pipefail

OUTPUT_DIR="${1:-.}"
HARDWARE_FILE="$OUTPUT_DIR/hardware_info.txt"
SOFTWARE_FILE="$OUTPUT_DIR/software_info.txt"
ERRORS_FILE="$OUTPUT_DIR/errors_info.txt"
SEP="================================================================================"
SUBSEP="--------------------------------------------------------------------------------"

mkdir -p "$OUTPUT_DIR"

# Python package probes (torch, transformers, jax, vllm, sglang, ...) must see
# the workload's own virtualenv. The system python3 has none of those packages,
# so without this the probes record FAILED instead of the installed versions.
# The collector lives in <repo>/scripts/, so the virtualenv is <repo>/.venv.
COLLECTOR_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)"
# Exported so the release commands (git describe) in each child bash see it.
export COLLECTOR_REPO_ROOT
if [[ -n "$COLLECTOR_REPO_ROOT" && -x "$COLLECTOR_REPO_ROOT/.venv/bin/python3" ]]; then
    export VIRTUAL_ENV="$COLLECTOR_REPO_ROOT/.venv"
    export PATH="$VIRTUAL_ENV/bin:$PATH"
fi

trim() {
    local s="$1"
    s="${s#"${s%%[![:space:]]*}"}"
    s="${s%"${s##*[![:space:]]}"}"
    printf '%s' "$s"
}

b64decode() {
    printf '%s' "$1" | base64 --decode 2>/dev/null
}

detect_vendor() {
    local pci nvidia_name
    pci="$(lspci -nn 2>/dev/null || true)"

    if grep -qiE 'NVIDIA|\[10de:' <<<"$pci"; then
        DETECTED_VENDOR="nVidia"
        nvidia_name="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || true)"
        nvidia_name="$(trim "$nvidia_name")"
        if [[ -n "$nvidia_name" ]]; then
            VENDOR_LABEL="nVidia ($nvidia_name detected)"
        else
            VENDOR_LABEL="nVidia (detected via PCI)"
        fi
        return
    fi

    if grep -qiE 'AMD/ATI|Advanced Micro Devices|\[1002:' <<<"$pci"; then
        DETECTED_VENDOR="AMD"
        if grep -qiE 'MI300X|\[1002:74b5\]|Device 74b5' <<<"$pci"; then
            VENDOR_LABEL="AMD (MI300X detected via PCI)"
        else
            VENDOR_LABEL="AMD (detected via PCI)"
        fi
        return
    fi

    # Fallbacks for environments where lspci is missing or restricted.
    if command -v nvidia-smi >/dev/null 2>&1; then
        DETECTED_VENDOR="nVidia"
        VENDOR_LABEL="nVidia (nvidia-smi detected)"
    elif command -v amd-smi >/dev/null 2>&1 || command -v rocminfo >/dev/null 2>&1; then
        DETECTED_VENDOR="AMD"
        VENDOR_LABEL="AMD (AMD SMI / rocminfo detected)"
    else
        DETECTED_VENDOR="Unknown"
        VENDOR_LABEL="Unknown (no AMD/nVidia GPU detected)"
    fi
}

vendor_applies() {
    local rule="${1,,}"
    case "$DETECTED_VENDOR" in
        AMD)
            [[ "$rule" == *"amd"* && "$rule" != *"nvidia-only"* ]] || [[ "$rule" == *"amd-only"* ]]
            ;;
        nVidia)
            [[ "$rule" == *"nvidia"* && "$rule" != *"amd-only"* ]] || [[ "$rule" == *"nvidia-only"* ]]
            ;;
        *)
            # If vendor cannot be detected, run only rows explicitly shared by both vendors.
            [[ "$rule" == *"amd"* && "$rule" == *"nvidia"* && "$rule" != *"only"* ]]
            ;;
    esac
}

write_file_header() {
    local file="$1" title="$2"
    {
        echo "$SEP"
        printf 'TITLE       : %s\n' "$title"
        printf 'FILE        : %s\n' "$(basename "$file")"
        printf 'HOST        : %s\n' "$(hostname 2>/dev/null || echo UNKNOWN)"
        printf 'VENDOR      : %s\n' "$VENDOR_LABEL"
        echo "$SUBSEP"
        date
        echo "$SEP"
        echo
    } > "$file"
}

write_commands_section() {
    local domain="$1" file="$2"
    {
        echo "$SEP"
        echo "DESCRIPTION : Commands To Be Run # Description"
        echo "$SUBSEP"
        while IFS=$'\t' read -r _seq vendor row_domain cmd_b64 desc_b64; do
            [[ "$row_domain" == "$domain" ]] || continue
            vendor_applies "$vendor" || continue
            cmd="$(b64decode "$cmd_b64")"
            desc="$(b64decode "$desc_b64")"
            printf '%s  # %s\n' "$cmd" "$desc"
        done <<< "$COMMAND_DATA"
        echo
        echo "$SEP"
        echo
    } >> "$file"
}

write_error_header() {
    {
        echo "$SEP"
        echo "TITLE       : Workload Inventory Run - Errors"
        echo "FILE        : errors_info.txt"
        printf 'HOST        : %s\n' "$(hostname 2>/dev/null || echo UNKNOWN)"
        printf 'VENDOR      : %s\n' "$VENDOR_LABEL"
        echo "$SUBSEP"
        date
        echo "$SEP"
        echo
        echo "$SEP"
        echo "DESCRIPTION : Failed Commands"
        echo "$SUBSEP"
        echo "Only commands returning a non-zero exit status are listed below."
        echo "$SEP"
        echo
    } > "$ERRORS_FILE"
}

run_one() {
    local domain="$1" cmd="$2" desc="$3" outfile="$4"
    local ts rc tmp
    ts="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
    tmp="$(mktemp)"

    bash -o pipefail -c "$cmd" >"$tmp" 2>&1
    rc=$?

    {
        echo "$SEP"
        printf 'DESCRIPTION : %s\n' "$desc"
        printf 'COMMAND     : %s\n' "$cmd"
        printf 'TIMESTAMP   : %s\n' "$ts"
        if [[ $rc -eq 0 ]]; then
            echo "STATUS      : SUCCESS"
        else
            printf 'STATUS      : FAILED (exit code %d)\n' "$rc"
        fi
        echo "$SUBSEP"
        cat "$tmp"
        echo "$SEP"
        echo
    } >> "$outfile"

    if [[ $rc -ne 0 ]]; then
        {
            echo "$SEP"
            printf 'DESCRIPTION : %s\n' "$desc"
            printf 'DOMAIN      : %s\n' "$domain"
            printf 'COMMAND     : %s\n' "$cmd"
            printf 'TIMESTAMP   : %s\n' "$ts"
            printf 'STATUS      : FAILED (exit code %d)\n' "$rc"
            echo "$SUBSEP"
            cat "$tmp"
            echo "$SEP"
            echo
        } >> "$ERRORS_FILE"
        ((ERROR_COUNT+=1))
    fi

    rm -f "$tmp"
}

COMMAND_DATA=$(cat <<'__COMMAND_DATA__'
__EMBEDDED_DATA__
__COMMAND_DATA__
)

ERROR_COUNT=0
detect_vendor

write_file_header "$HARDWARE_FILE" "Workload Inventory Run - Hardware"
write_file_header "$SOFTWARE_FILE" "Workload Inventory Run - Software"
write_error_header
write_commands_section "hardware" "$HARDWARE_FILE"
write_commands_section "software" "$SOFTWARE_FILE"

while IFS=$'\t' read -r _seq vendor domain cmd_b64 desc_b64; do
    vendor_applies "$vendor" || continue
    cmd="$(b64decode "$cmd_b64")"
    desc="$(b64decode "$desc_b64")"
    case "$domain" in
        hardware) run_one "$domain" "$cmd" "$desc" "$HARDWARE_FILE" ;;
        software) run_one "$domain" "$cmd" "$desc" "$SOFTWARE_FILE" ;;
    esac
done <<< "$COMMAND_DATA"

{
    echo "$SEP"
    echo "DESCRIPTION : Collection Summary"
    echo "$SUBSEP"
    printf 'Completed    : %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
    printf 'Vendor       : %s\n' "$VENDOR_LABEL"
    printf 'Failed       : %d command(s)\n' "$ERROR_COUNT"
    echo "$SEP"
} >> "$ERRORS_FILE"

printf 'Created: %s\n' "$HARDWARE_FILE"
printf 'Created: %s\n' "$SOFTWARE_FILE"
printf 'Created: %s\n' "$ERRORS_FILE"
printf 'Detected vendor: %s\n' "$VENDOR_LABEL"

# Inventory collection itself completed even when individual probe commands fail.
# Failed probe details stay in errors_info.txt only; do not print a failure count.
exit 0
'''

collector = collector.replace("__SOURCE_FILE__", os.path.basename(xlsx_path))
collector = collector.replace("__SOURCE_SHEET__", source_sheet)
collector = collector.replace("__EMBEDDED_DATA__", embedded_data)

with open(out_path, "w", encoding="utf-8", newline="\n") as f:
    f.write(collector)

mode = os.stat(out_path).st_mode
os.chmod(out_path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

hw = sum(1 for r in command_rows if r[3] == "hardware")
sw = sum(1 for r in command_rows if r[3] == "software")
print(f"Created: {out_path}")
print(f"Source sheet: {source_sheet}")
print(f"Embedded commands: {len(command_rows)} ({hw} hardware, {sw} software)")
PY

chmod +x "$OUTPUT_SCRIPT"
echo "Generator complete: $OUTPUT_SCRIPT"
