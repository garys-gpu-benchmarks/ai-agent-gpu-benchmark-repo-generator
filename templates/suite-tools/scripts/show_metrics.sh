#!/usr/bin/env bash
# ==============================================================================
# show_metrics.sh
#
# Prints a fixed-width summary of the metrics recorded in the runtime ledger
# for one workload number, either from this machine or from a remote
# benchmark machine over ssh.
#
# Usage:   ./show_metrics.sh WORKLOAD [options]
# Help:    ./show_metrics.sh --help
#
# Every workload prints with the same column layout and the output never
# exceeds 93 characters:
#
#   WL  Name         Profile    Idx  Exit E2E_ms TTFT_ms  Ret_ms GenTk/s EmbDc/s FAISS_N
#   332 RAG Sweep    smoke       32     0 269.017  41.308 0.09230  62.754  63.522     217
#
# The Name column (12 characters max) is the workload's short name from the
# built-in table in workload_name_table() below (or a --labels file line
# name:WORKLOAD,Short Name); without one, the first 12 characters of the
# workload name.
#
# Short metric labels (7 characters max) are taken from, in order:
#   1. a metric_N_short column in the ledger, if the ledger has one
#   2. a --labels CSV file (lines: key,label  or  workload:key,label)
#   3. the built-in table in short_label_table() below
#   4. an automatic abbreviation of the metric key
# The "key" is the text in parentheses at the end of metric_N_def, e.g.
#   E2E, ms (end_to_end_query_latency_retrieval_generation_ms)
#
# Both built-in tables are generated. Their sources are the
# Metric_Short_Labels and Workload_Short_Names sheets of
# BenchmarkSpecDefinitions.xlsx in the repository generator; change a label
# or name there, then run  python3 scripts/generate_show_metrics.py  in the
# generator. The master copy of this script is
# templates/suite-tools/scripts/show_metrics.sh.
#
# Exit codes:
#   0  metrics shown
#   1  file/connection problem, or no rows for the workload
#   2  usage error
# ==============================================================================

set -uo pipefail

readonly SCRIPT_NAME="${0##*/}"
readonly DEFAULT_LEDGER="/var/opt/benchmarks/runtime_ledger.csv"
readonly MAX_WIDTH=93

# ------------------------------------------------------------------------------
# Defaults (each can be changed with an option)
# ------------------------------------------------------------------------------
workload=""
profile=""            # empty = all profiles
ledger_file="${DEFAULT_LEDGER}"
remote_host=""        # empty = read the file on this machine
remote_port=""        # empty = 22 when --host is given
remote_user="root"
ssh_key=""
labels_file=""
show_legend=true
show_means=true

declare -a ssh_cmd=()
tmp_labels=""
tmp_rows=""

usage() {
  cat <<EOF
Usage: ${SCRIPT_NAME} WORKLOAD [options]

Shows the metrics from the runtime ledger for workload number WORKLOAD
(for example 332), one line per run, in fixed-width columns.

Options:
  --baseline | --smoke | --extended
                        Show only runs of that profile. Default: all profiles.
  --profile NAME        Same as above, for any profile name.
  --file FILE           Ledger CSV path (on the remote machine with --host).
                        Default: ${DEFAULT_LEDGER}
  --host HOST           Read the ledger from HOST over ssh (IP or name,
                        optionally user@host; default user: root).
                        Default: read the file on this machine.
  --port PORT           ssh port on HOST. Default: 22.
  -i, --identity KEY    SSH private key. Default: try your ssh defaults,
                        then each private key in ~/.ssh.
  --labels FILE         CSV of short labels that override the built-in ones:
                          key,label           e.g.  ttft_ms,TTFT_ms
                          workload:key,label  e.g.  332:faiss_index_ntotal,Vectors
                          name:workload,name  e.g.  name:332,RAG Sweep
  --no-legend           Do not print the label legend.
  --no-mean             Do not print the per-profile mean lines.
  -h, --help            Show this help.

Examples:
  ./${SCRIPT_NAME} 332
  ./${SCRIPT_NAME} 332 --baseline
  ./${SCRIPT_NAME} 332 --host 203.0.113.10 --port 2222
  ./${SCRIPT_NAME} 328 --extended --file /opt/benchmarks/runtime_ledger.csv
EOF
}

die_usage() {
  echo "${SCRIPT_NAME}: $*" >&2
  echo "Try '${SCRIPT_NAME} --help'." >&2
  exit 2
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

parse_args() {
  while (($# > 0)); do
    case "$1" in
      --baseline | --smoke | --extended) profile=${1#--}; shift ;;
      --profile)     [[ $# -ge 2 ]] || die_usage "$1 needs a value"; profile=$2; shift 2 ;;
      --file)        [[ $# -ge 2 ]] || die_usage "$1 needs a value"; ledger_file=$2; shift 2 ;;
      --host)        [[ $# -ge 2 ]] || die_usage "$1 needs a value"; remote_host=$2; shift 2 ;;
      --port)        [[ $# -ge 2 ]] || die_usage "$1 needs a value"; remote_port=$2; shift 2 ;;
      -i | --identity) [[ $# -ge 2 ]] || die_usage "$1 needs a value"; ssh_key=$2; shift 2 ;;
      --labels)      [[ $# -ge 2 ]] || die_usage "$1 needs a value"; labels_file=$2; shift 2 ;;
      --no-legend)   show_legend=false; shift ;;
      --no-mean)     show_means=false; shift ;;
      -h | --help)   usage; exit 0 ;;
      -*)            die_usage "unknown option: $1" ;;
      *)
        [[ -z "${workload}" ]] || die_usage "only one WORKLOAD number, got '${workload}' and '$1'"
        workload=$1; shift ;;
    esac
  done

  [[ -n "${workload}" ]] || die_usage "give a WORKLOAD number, e.g. 332"
  [[ "${workload}" =~ ^[0-9]+$ ]] || die_usage "WORKLOAD must be a number, e.g. 332"
  [[ -z "${profile}" || "${profile}" =~ ^[A-Za-z0-9_-]+$ ]] || die_usage "bad profile name: ${profile}"

  if [[ "${remote_host}" == *@* ]]; then
    remote_user=${remote_host%@*}
    remote_host=${remote_host#*@}
  fi
  if [[ -n "${remote_port}" && -z "${remote_host}" ]]; then die_usage "--port needs --host"; fi
  if [[ -n "${remote_host}" ]]; then
    remote_port=${remote_port:-22}
    if ! [[ "${remote_port}" =~ ^[0-9]+$ ]] || ((remote_port < 1 || remote_port > 65535)); then
      die_usage "--port must be a number from 1 to 65535"
    fi
  fi
  if [[ -n "${ssh_key}" && ! -f "${ssh_key}" ]]; then die_usage "--identity: no such file: ${ssh_key}"; fi
  if [[ -n "${labels_file}" && ! -f "${labels_file}" ]]; then die_usage "--labels: no such file: ${labels_file}"; fi
}

# ------------------------------------------------------------------------------
# ssh connection (same approach as get_remote_info.sh)
# ------------------------------------------------------------------------------
probe_error=""
try_login() {
  probe_error=$("${ssh_cmd[@]}" -o BatchMode=yes "$@" "${remote_user}@${remote_host}" true 2>&1 >/dev/null)
}

is_private_key() {
  [[ -f "$1" && "$1" != *.pub ]] && head -n 1 "$1" 2>/dev/null | grep -q 'PRIVATE KEY'
}

explain_ssh_error() {
  case "${probe_error}" in
    *"IDENTIFICATION HAS CHANGED"*)
      echo "The machine at ${remote_host} has a new host key (for example, it was reinstalled)." >&2
      echo "If you expected that, remove the old key and run this again:" >&2
      echo "  ssh-keygen -R '[${remote_host}]:${remote_port}'; ssh-keygen -R ${remote_host}" >&2 ;;
    *"Connection refused"* | *"timed out"* | *"No route"* | *"Could not resolve"*)
      echo "Cannot reach ${remote_host} on port ${remote_port}. Check the address, the port, and that the machine is running." >&2 ;;
    *"Permission denied"*)
      echo "No SSH key was accepted for ${remote_user}@${remote_host}. Give the right one with -i KEY." >&2 ;;
  esac
  [[ -n "${probe_error}" ]] && echo "ssh said: ${probe_error}" >&2
  return 0
}

connect() {
  ssh_cmd=(ssh -p "${remote_port}"
    -o ConnectTimeout=15 -o ServerAliveInterval=30 -o StrictHostKeyChecking=accept-new)

  if [[ -n "${ssh_key}" ]]; then
    ssh_cmd+=(-i "${ssh_key}" -o IdentitiesOnly=yes)
    try_login || { explain_ssh_error; die "cannot log in with ${ssh_key}"; }
    return
  fi
  try_login && return
  [[ "${probe_error}" == *"Permission denied"* ]] || { explain_ssh_error; die "cannot connect"; }

  local key
  for key in "${HOME}"/.ssh/*; do
    is_private_key "${key}" || continue
    if try_login -i "${key}" -o IdentitiesOnly=yes; then
      ssh_cmd+=(-i "${key}" -o IdentitiesOnly=yes)
      return
    fi
  done
  explain_ssh_error
  die "none of the keys in ${HOME}/.ssh were accepted"
}

# Writes the ledger header plus this workload's rows to stdout. Columns 1-3
# (index, run_id, workload_number) never contain commas, so a plain split is
# safe for this pre-filter; the real CSV parsing happens in format_table.
fetch_rows() {
  local filter='NR == 1 || $3 == wl'
  if [[ -z "${remote_host}" ]]; then
    [[ -f "${ledger_file}" ]] || die "no such file: ${ledger_file}"
    awk -F, -v wl="${workload}" "${filter}" "${ledger_file}"
    return
  fi
  connect
  local remote_cmd
  remote_cmd=$(printf 'f=%q; [ -f "$f" ] || { echo "no such file on remote machine: $f" >&2; exit 3; }; awk -F, -v wl=%q %q "$f"' \
    "${ledger_file}" "${workload}" "${filter}")
  "${ssh_cmd[@]}" "${remote_user}@${remote_host}" "${remote_cmd}" \
    || die "could not read ${ledger_file} on ${remote_host}"
}

# ------------------------------------------------------------------------------
# Built-in short labels, keyed by the metric key in parentheses.
#   key              label   used for every workload that reports this key
#   WORKLOAD:key     label   used only for that workload (wins over key)
# Generated from the Metric_Short_Labels sheet; do not edit between the markers.
# ------------------------------------------------------------------------------
short_label_table() {
  # BEGIN GENERATED SHORT LABELS
  # 162 labels from the Metric_Short_Labels sheet of BenchmarkSpecDefinitions.xlsx
  # (scripts/generate_show_metrics.py in the repository generator)
  cat <<'EOF'
rocm_package_mismatch_count                              PkgMis
kernel_release_mismatch_count                            KrnMis
driver_compliance_percent                                DrvCmp%
permission_error_count                                   PermErr
dmesg_gpu_fault_count                                    GPUFlt
gpu_temperature_c                                        Temp_C
pcie_link_width_lanes                                    PCIe_x
pcie_link_speed_gt_s                                     PCIeGTs
hsa_agents_visible_count                                 HSAAgt
peak_gpu_junction_temp_c                                 PkJct_C
sustained_gpu_power_w                                    Pwr_W
ras_uncorrectable_ecc_delta_count                        UECC
thermal_throttle_event_count                             Thrttl
uncorrected_ecc_errors_count                             UECC
corrected_ecc_errors_count                               CECC
test_wall_clock_completion_time_s                        Wall_s
allocated_verification_buffer_gb                         Buf_GB
loop_verification_pass_pct                               Pass%
max_abs_error                                            MaxAbsE
max_rel_error                                            MaxRelE
tolerance_compliance                                     Tol%
coverage_count                                           Cases
failure_count                                            Fails
iops_mean                                                IOPS
bandwidth_mb_s                                           BW_MB/s
clat_p50_us                                              Lat50us
copy_bandwidth_gb_s                                      CpyGB/s
scale_bandwidth_gb_s                                     SclGB/s
add_bandwidth_gb_s                                       AddGB/s
triad_bandwidth_gb_s                                     TrdGB/s
tcp_loopback_gbps                                        TCPGbps
udp_throughput_gbps                                      UDPGbps
udp_jitter_ms                                            Jit_ms
packet_loss_rate                                         Loss%
tcp_retransmit_count                                     Retrans
latency_ns_l1                                            L1_ns
latency_ns_l2                                            L2_ns
latency_ns_l3                                            L3_ns
latency_ns_local_dram                                    DRAM_ns
latency_ns_remote_dram                                   Rmt_ns
cache_latency_nsec                                       LLC_ns
local_numa_node_latency_nsec                             DRAM_ns
local_dram_pointer_chase_bandwidth_gb_s                  PC_GB/s
cache_miss_counters_misses_sec                           Miss/s
instructions_per_cycle_ipc                               IPC
branch_misprediction_rate                                BrMis%
cache_misses_per_1000_instructions                       MPKI
pipeline_stall_pct                                       Stall%
context_switches_during_workload_switches_s              CSw/s
lat_syscall_null_us                                      Sys_us
context_switch_latency_us                                CSw_us
lat_mem_rd_16mb_stride128_ns                             MemRdns
bw_mem_mb_s                                              MemMB/s
bw_pipe_mb_s                                             PipMB/s
giga_updates_score                                       GUPS
updates_sec                                              Upd/s
payload_update_gb_s                                      UpdGB/s
tlb_miss_rate                                            TLBMiss
l3_miss_rate                                             L3Miss
bandwidth_GBps                                           BW_GB/s
latency_us                                               Lat_us
headline_transfer_bytes                                  Bytes
bandwidth_gb_s_copy                                      CpyGB/s
bandwidth_gb_s_mul                                       MulGB/s
bandwidth_gb_s_add                                       AddGB/s
bandwidth_gb_s_triad                                     TrdGB/s
bandwidth_gb_s_dot                                       DotGB/s
allreduce_busbw_gb_s                                     BusGB/s
allreduce_algbw_gb_s                                     AlgGB/s
allreduce_latency_at_min_bytes_us                        Lat_us
achieved_compute_tflops                                  TFLOPS
kernel_time_msec                                         Krn_ms
minimum_operand_traffic_gb_s                             OpGB/s
relative_l1_checked_columns                              RelL1
cpu_gflops                                               CPU_GF
kernel_time_ms                                           Krn_ms
modeled_gflops_per_s                                     GF/s
min_operand_traffic_gb_s                                 MinGB/s
flopCnt                                                  FLOPs
gemm_time_usec                                           GEMM_us
gemm_tflops                                              GEMM_TF
gemm_bandwidth_gb_s                                      GEMMGBs
conv_time_usec                                           Conv_us
conv_tflops                                              Conv_TF
conv_bandwidth_gb_s                                      ConvGBs
sustained_fp64_performance_across_problem_size_n_tflops  FP64_TF
time_to_solution_across_problem_size_n_s                 Solve_s
percent_of_gpu_fp64_matrix_peak                          MtxPk%
step_time_ms                                             Step_ms
images_per_sec                                           Img/s
modeled_tflops                                           ModlTF
peak_gpu_memory_GB                                       PkMemGB
modeled_param_input_traffic_gb_s                         TrfGB/s
images_sec                                               Img/s
per_image_latency_ms                                     ImLatms
batch_latency_max_msec                                   Max_ms
gpu_util_percent                                         GPU%
sequences_per_sec                                        Seq/s
mean_latency_ms                                          Lat_ms
tokens_per_sec                                           Tok/s
peak_gpu_memory_gb                                       PkMemGB
per_image_latency_sec                                    ImLat_s
first_image_latency_ms                                   Cold_ms
samples_per_sec                                          Smp/s
forward_latency_msec                                     Fwd_ms
tflops                                                   TFLOPS
jit_compile_msec                                         JIT_ms
peak_hbm_gb                                              HBM_GB
output_tokens_per_sec                                    OutTk/s
ttft_msec                                                TTFT_ms
tpot_msec                                                TPOT_ms
kv_cache_peak_gb                                         KV_GiB
kv_cache_usage_peak_pct                                  KV%
output_token_throughput_tokens_sec                       OutTk/s
ttft_p50_msec                                            TTFT_ms
time_per_output_token_tpot_p50_msec                      TPOT_ms
inter_token_latency_itl_p50_msec                         ITL_ms
end_to_end_request_latency_msec                          E2E_ms
end_to_end_latency_ms                                    E2E_ms
ttft_ms                                                  TTFT_ms
output_tokens_per_s                                      OutTk/s
radixattention_cache_hit_rate_pct                        Radix%
completed_request_rate_pct                               Done%
end_to_end_request_latency_p50_msec                      E2E_ms
request_throughput_requests_sec                          Req/s
end_to_end_query_latency_retrieval_generation_ms         E2E_ms
generation_phase_time_to_first_token_ms                  TTFT_ms
retrieval_latency_vector_search_ms                       Ret_ms
generation_throughput_output_tokens_s                    GenTk/s
embedding_throughput_docs_s                              EmbDc/s
faiss_index_ntotal                                       FAISS_N
cuda_package_version_mismatches_count                    PkgMis
nvidia_kernel_module_driver_version_mismatches_count     KrnMis
vbios_string_present                                     VBIOS
required_library_path_device_permission_errors           PermErr
dmesg_nvidia_gpu_fault_xid_count                         XidFlt
cuda_devices_visible                                     CUDADev
peak_gpu_temperature_c                                   PkTmp_C
gpu_system_ecc_error_count                               ECCErr
hbm3_coverage_gb                                         Buf_GB
fixed_pattern_fill_verify_pass_rate                      Pass%
bandwidth_h2d_gbps                                       H2DGB/s
bandwidth_d2h_gbps                                       D2HGB/s
bandwidth_d2d_gbps                                       D2DGB/s
latency_h2d_us                                           H2D_us
latency_d2h_us                                           D2H_us
latency_d2d_us                                           D2D_us
pinned_vs_pageable_bandwidth_ratio                       PinRat
norm_error_2                                             L2Err
tflops_fwd                                               TFLOPS
solver_search_msec                                       Srch_ms
percent_of_fp64_vector_peak                              VecPk%
step_time_msec                                           Step_ms
fp16_tflops                                              ModlTF
modeled_weight_feature_traffic_gb_s                      TrfGB/s
per_image_latency_msec                                   ImLatms
gpu_utilization_percent                                  GPU%
peak_vram_gb                                             VRAM_GB
first_image_latency_s                                    Cold_s
decode_throughput_tokens_sec                             DecTk/s
124:peak_gpu_memory_gb                                   VRAM_GB
324:peak_gpu_memory_gb                                   VRAM_GB
EOF
  # END GENERATED SHORT LABELS
}

# ------------------------------------------------------------------------------
# Built-in workload short names (12 characters max), shown in the Name column.
# Format: WORKLOAD<spaces>Short Name. A workload not listed shows the first 12
# characters of its workload name.
# Generated from the Workload_Short_Names sheet; do not edit between the markers.
# ------------------------------------------------------------------------------
workload_name_table() {
  # BEGIN GENERATED WORKLOAD NAMES
  # 128 workload short names from the Workload_Short_Names sheet of BenchmarkSpecDefinitions.xlsx
  # (scripts/generate_show_metrics.py in the repository generator)
  cat <<'EOF'
101   System Cfg
102   ROCm Health
103   CPU Stress
104   SDC Check
105   Tensor Ops
106   FIO NVMe
107   STREAM CPU
108   iPerf3 Net
109   multichase
110   NUMA Cache
111   perf PMU
112   lmbench
113   GUPS
114   hipMemcpy BW
115   BabelStream
116   RCCL BW
117   rocBLAS GEMM
118   MIOpen Conv
119   Torch Kernel
120   rocHPL FP64
121   ResNet50 Trn
122   ResNet50 Inf
123   BERT Infer
124   SDXL Infer
125   DistilBERT
126   JAX XLA Fwd
127   KV Cache
128   vLLM Thruput
129   vLLM TokGen
130   SGLang Prmpt
131   SGLang Serve
132   RAG Sweep
201   System Cfg
202   NVIDIA Hlth
203   CPU Stress
204   SDC Check
205   Tensor Ops
206   FIO NVMe
207   STREAM CPU
208   iPerf3 Net
209   multichase
210   NUMA Cache
211   perf PMU
212   lmbench
213   GUPS
214   CUDA Memcpy
215   BabelStream
216   NCCL BW
217   cuBLAS GEMM
218   cuDNN Conv
219   TorchBench
220   NVIDIA HPL
221   ResNet50 Trn
222   ResNet50 Inf
223   BERT Infer
224   SDXL Infer
225   DistilBERT
226   JAX XLA Fwd
227   KV Cache
228   vLLM Thruput
229   vLLM TokGen
230   SGLang Prmpt
231   SGLang Serve
232   RAG Sweep
301   System Cfg
302   ROCm Health
303   CPU Stress
304   SDC Check
305   Tensor Ops
306   FIO NVMe
307   STREAM CPU
308   iPerf3 Net
309   multichase
310   NUMA Cache
311   perf PMU
312   lmbench
313   GUPS
314   hipMemcpy BW
315   BabelStream
316   RCCL BW
317   rocBLAS GEMM
318   MIOpen Conv
319   Torch Kernel
320   rocHPL FP64
321   ResNet50 Trn
322   ResNet50 Inf
323   BERT Infer
324   SDXL Infer
325   DistilBERT
326   JAX XLA Fwd
327   KV Cache
328   vLLM Thruput
329   vLLM TokGen
330   SGLang Prmpt
331   SGLang Serve
332   RAG Sweep
401   System Cfg
402   NVIDIA Hlth
403   CPU Stress
404   SDC Check
405   Tensor Ops
406   FIO NVMe
407   STREAM CPU
408   iPerf3 Net
409   multichase
410   NUMA Cache
411   perf PMU
412   lmbench
413   GUPS
414   CUDA Memcpy
415   BabelStream
416   NCCL BW
417   cuBLAS GEMM
418   cuDNN Conv
419   TorchBench
420   NVIDIA HPL
421   ResNet50 Trn
422   ResNet50 Inf
423   BERT Infer
424   SDXL Infer
425   DistilBERT
426   JAX XLA Fwd
427   KV Cache
428   vLLM Thruput
429   vLLM TokGen
430   SGLang Prmpt
431   SGLang Serve
432   RAG Sweep
EOF
  # END GENERATED WORKLOAD NAMES
}

# Combines the built-in table with the --labels file (file wins) into
# "key<TAB>label" lines for the formatter.
label_lines() {
  short_label_table | awk '!/^[[:space:]]*#/ && NF >= 2 { print $1 "\t" $NF }'
  # Workload short names may contain spaces: number, then the rest of the line.
  workload_name_table | awk '!/^[[:space:]]*#/ && NF >= 2 {
    n = $1; sub(/^[[:space:]]*[^[:space:]]+[[:space:]]+/, ""); sub(/[[:space:]]+$/, "")
    print "@name:" (n + 0) "\t" $0 }'
  if [[ -n "${labels_file}" ]]; then
    tr -d '\r' <"${labels_file}" | awk -F, '
      /^[[:space:]]*#/ || NF < 2 { next }
      { k = $1; l = $2; gsub(/^[ \t]+|[ \t]+$/, "", k); gsub(/^[ \t]+|[ \t]+$/, "", l)
        if (k ~ /^name:[0-9]+$/) k = "@name:" (substr(k, 6) + 0)
        if (k != "" && l != "") print k "\t" l }'
  fi
}

# ------------------------------------------------------------------------------
# Formatter: parses the CSV properly (quoted fields with commas) and prints
# the fixed-width table.
#   Column layout (identical for every workload):
#     WL(3) Name(12) Profile(8) Idx(5: run index, * if it failed)
#     Exit(5: ledger exit_code) then up to 7 metrics of 7 chars each, every
#     column separated by one space
#     ->  at most 37 + 7*8 = 93 chars.
# ------------------------------------------------------------------------------
read -r -d '' FORMAT_AWK <<'AWK'
function parse_csv(line, out,    n, i, c, field, inq) {
  n = 0; field = ""; inq = 0
  for (i = 1; i <= length(line); i++) {
    c = substr(line, i, 1)
    if (inq) {
      if (c == "\"") {
        if (substr(line, i + 1, 1) == "\"") { field = field "\""; i++ }
        else inq = 0
      } else field = field c
    } else if (c == "\"") inq = 1
    else if (c == ",") { out[++n] = field; field = "" }
    else field = field c
  }
  out[++n] = field
  return n
}
function trim(s) { gsub(/^[ \t]+|[ \t]+$/, "", s); return s }
function is_num(s) { return s ~ /^[ \t]*[-+]?([0-9]+\.?[0-9]*|\.[0-9]+)([eE][-+]?[0-9]+)?[ \t]*$/ }
# Metric key = text inside the last (...) of the definition.
# Falls back to the first "(snake_case_word)" when text follows the key.
function metric_key(def,    k) {
  if (match(def, /\([^()]*\)[ \t]*$/)) { k = substr(def, RSTART + 1, RLENGTH - 2); return trim(k) }
  if (match(def, /\([A-Za-z0-9_]+\)/))   { k = substr(def, RSTART + 1, RLENGTH - 2); return trim(k) }
  return trim(def)
}
function auto_label(key,    s) {
  s = key; gsub(/[^A-Za-z0-9%\/]/, "", s)
  return substr(s, 1, VW)
}
# Fits any value into VW (7) characters.
function fmt(v,    a, x, s, u) {
  v = trim(v)
  if (v == "") return "-"
  if (!is_num(v)) {
    if (tolower(v) ~ /^na/) return "na"
    return substr(v, 1, VW)
  }
  x = v + 0; a = (x < 0) ? -x : x
  if (a == 0) return "0"
  if (a >= 1e7) {
    u = "K"; x = x / 1e3
    if (a >= 1e9)  { u = "M"; x = x / 1e3 }
    if (a >= 1e12) { u = "G"; x = x / 1e3 }
    if (a >= 1e15) { u = "T"; x = x / 1e3 }
    s = sprintf("%.1f%s", x, u)
    if (length(s) > VW) s = sprintf("%.0f%s", x, u)
    if (length(s) > VW) s = sprintf("%.0e", v + 0)
    return s
  }
  if (x == int(x)) return sprintf("%d", x)
  if (a >= 1e5)   return sprintf("%.0f", x)
  if (a >= 1e4)   return sprintf("%.1f", x)
  if (a >= 1e3)   return sprintf("%.2f", x)
  if (a >= 1)     return sprintf("%.3f", x)
  if (a >= 1e-3)  return sprintf("%.5f", x)
  return sprintf("%.1e", x)
}
function clip(s) { return (length(s) > W) ? substr(s, 1, W) : s }
# Exit codes are 0 or 1. A mean of mixed codes still has to fit the 5-character column.
function exit_cell(v,    x, s) {
  v = trim(v)
  if (v == "") return "-"
  if (!is_num(v)) return substr(v, 1, 5)
  x = v + 0
  if (x == int(x)) return sprintf("%d", x)
  s = sprintf("%.3f", x)
  if (length(s) > 5) s = sprintf("%.2f", x)
  if (length(s) > 5) s = sprintf("%.1f", x)
  if (length(s) > 5) s = sprintf("%.0f", x)
  return s
}

BEGIN { VW = 7; NW = 12; MAXM = 7 }

# First input: the label table (key<TAB>label).
FILENAME == labels {
  split($0, kv, "\t")
  if (kv[1] ~ /^@name:/) wshort[substr(kv[1], 7)] = substr(kv[2], 1, NW)
  else short[kv[1]] = substr(kv[2], 1, VW)
  next
}

{ sub(/\r$/, "") }
$0 == "" { next }

# Ledger header: locate columns by name.
!hdr_done {
  nh = parse_csv($0, h)
  for (i = 1; i <= nh; i++) col[trim(h[i])] = i
  hdr_done = 1
  if (!("workload_number" in col) || !("benchmark_profile" in col)) {
    print "ERROR: the file does not look like a runtime ledger (missing workload_number/benchmark_profile)" > "/dev/stderr"
    bad = 1; exit 1
  }
  next
}

{
  n = parse_csv($0, f)
  if (trim(f[col["workload_number"]]) + 0 != wl + 0) next
  matched_wl++
  p = trim(f[col["benchmark_profile"]])
  if (prof != "" && p != prof) next

  r = ++nrows
  R_prof[r] = p
  R_idx[r]  = ("table_index_number" in col) ? trim(f[col["table_index_number"]]) : r
  R_exit[r] = ("exit_code" in col) ? trim(f[col["exit_code"]]) : "0"
  if (wname == "" && ("workload_name" in col)) wname = trim(f[col["workload_name"]])

  for (m = 1; m <= MAXM; m++) {
    dc = "metric_" m "_def"; rc = "metric_" m "_result"; sc = "metric_" m "_short"
    if (!(dc in col)) continue
    d = trim(f[col[dc]])
    if (d != "" && !(m in M_def)) {
      M_def[m] = d
      k = metric_key(d)
      M_key[m] = k
      if ((sc in col) && trim(f[col[sc]]) != "") M_lab[m] = substr(trim(f[col[sc]]), 1, VW)
      else if ((wl ":" k) in short) M_lab[m] = short[wl ":" k]
      else if (k in short)          M_lab[m] = short[k]
      else                          M_lab[m] = auto_label(k)
      if (m > nmet) nmet = m
    }
    if (d != "" || (rc in col && trim(f[col[rc]]) != "")) { if (m > nmet) nmet = m }
    R_val[r, m] = (rc in col) ? trim(f[col[rc]]) : ""
  }
}

END {
  if (bad) exit 1
  if (nrows == 0) {
    if (matched_wl) printf "No %s runs for workload %s in the ledger.\n", prof, wl > "/dev/stderr"
    else            printf "Workload %s is not in the ledger.\n", wl > "/dev/stderr"
    exit 1
  }

  title = "Workload " wl " - " wname
  if (prof != "") title = title " (" prof " only)"
  print clip(title)
  print clip("Ledger: " src)
  print ""

  hfmt = "%-3s %-12s %-8s %5s %5s"
  line = sprintf(hfmt, "WL", "Name", "Profile", "Idx", "Exit")
  for (m = 1; m <= nmet; m++) line = line sprintf(" %" VW "s", (m in M_lab) ? M_lab[m] : "M" m)
  print line
  dash = sprintf(hfmt, "---", "------------", "--------", "-----", "-----")
  for (m = 1; m <= nmet; m++) dash = dash " -------"
  print dash

  sname = ((wl + 0) "" in wshort) ? wshort[(wl + 0) ""] : substr(wname, 1, NW)
  fails = 0
  for (r = 1; r <= nrows; r++) {
    idx = R_idx[r]
    if (R_exit[r] != "" && R_exit[r] != "0") { idx = idx "*"; fails++ }
    line = sprintf(hfmt, substr(wl, 1, 3), sname, substr(R_prof[r], 1, 8), substr(idx, 1, 5), exit_cell(R_exit[r]))
    for (m = 1; m <= nmet; m++) line = line sprintf(" %" VW "s", fmt(R_val[r, m]))
    print line

    # running sums for the per-profile means (numeric values only)
    p = R_prof[r]
    if (!(p in P_n)) { P_order[++np] = p }
    P_n[p]++
    if (is_num(R_exit[r])) { P_esum[p] += R_exit[r]; P_ecnt[p]++ }
    for (m = 1; m <= nmet; m++) if (is_num(R_val[r, m])) { P_sum[p, m] += R_val[r, m]; P_cnt[p, m]++ }
  }

  if (means) {
    printed = 0
    for (i = 1; i <= np; i++) {
      p = P_order[i]
      if (P_n[p] < 2) continue
      if (!printed) { print dash; printed = 1 }
      ecell = (P_ecnt[p] > 0) ? exit_cell(P_esum[p] / P_ecnt[p]) : "-"
      line = sprintf(hfmt, substr(wl, 1, 3), "mean", substr(p, 1, 8), "n=" P_n[p], ecell)
      for (m = 1; m <= nmet; m++)
        line = line sprintf(" %" VW "s", (P_cnt[p, m] > 0) ? fmt(P_sum[p, m] / P_cnt[p, m]) : "-")
      print line
    }
  }

  if (legend) {
    print ""
    print clip(sprintf("%-7s %s", "Exit", "Exit Code (0 is pass)"))
    for (m = 1; m <= nmet; m++) if (m in M_lab) print clip(sprintf("%-7s %s", M_lab[m], M_def[m]))
  }
  if (fails) print clip("* run did not exit 0 (" fails " run" (fails > 1 ? "s" : "") ")")
}
AWK

main() {
  parse_args "$@"

  local src="${ledger_file}"
  [[ -n "${remote_host}" ]] && src="${remote_user}@${remote_host}:${remote_port} ${ledger_file}"

  tmp_labels=$(mktemp) || die "cannot create a temporary file"
  tmp_rows=$(mktemp) || { rm -f "${tmp_labels}"; die "cannot create a temporary file"; }
  trap 'rm -f "${tmp_labels}" "${tmp_rows}"' EXIT

  label_lines >"${tmp_labels}"
  fetch_rows >"${tmp_rows}" || exit 1
  [[ -s "${tmp_rows}" ]] || die "the ledger is empty: ${src}"

  awk -v wl="${workload}" -v prof="${profile}" -v src="${src}" \
      -v labels="${tmp_labels}" -v W="${MAX_WIDTH}" \
      -v legend="$([[ ${show_legend} == true ]] && echo 1 || echo 0)" \
      -v means="$([[ ${show_means} == true ]] && echo 1 || echo 0)" \
      "${FORMAT_AWK}" "${tmp_labels}" "${tmp_rows}"
}

main "$@"
