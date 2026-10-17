# Sibling workload notes

These notes are for operators comparing AMD 101–132 with NVIDIA 201–232
and AMD Ubuntu 26.04 301–332. 301–332 keep the 101–132 workload names and
use repository slugs with a `-ubu2604` suffix. They do not change the current
00_54 DigitalOcean or Runpod trees.

## 105 vs 205 — PyTorch Tensor Op Correctness

Same sweep knobs are not the same wall-clock work.

- **105 (AMD)** compares GPU output to a **CPU FP32** reference built from
  `left.float().cpu()`. Extended with `num_iterations=100` finishes in minutes.
- **205 (NVIDIA)** compares GPU output to a **CPU FP64** reference and reseeds
  every iteration. The same `8x512x512` case is much slower.

Do not treat 105 elapsed time as a 205 budget. Publish one
`num_iterations` pair: smoke **2**, baseline **50**, extended **100**.

`coverage_count` also differs today:

- 105 writes `float(iterations)` per case, so an extended ledger can look
  like `coverage_count=100` per row and map poorly onto metric #4/#5.
- 205 writes `1` per case.

00_55 documents this. Aligning the collectors is a later scientific change
and is not applied to the live 00_54 VMs.

00_78 NVIDIA 205: the locked collector CSV includes `rc=0` on success.
The generated validator used to treat every numeric `runs` column as
"must be positive," so `run.rc is not positive` failed smoke/baseline/extended
after a 100% pass_rate collect. Validator now skips `rc` / allows zero.
The leftover-DB parser also skips `rc` so `summary.json` metrics start at
`pass_rate_percent`. Ledger mapping uses the same paren-key resolver as
`print_metric_summary.py` so `Test passing rate (pass_rate_percent)` does
not fall back to positional `rc=0`. Setup installs `numpy` so Torch does
not warn `Failed to initialize NumPy`.

## 105 README source

Workbook `Workload_Definitions` Execution Description for 105/205 must
describe the tensor-op suite, not RVS SDC / `rvs_sdc.yaml`. The 00_54 105
README Overview was generated from leftover SDC text.

## 127–131, 227–231, and 327–331 — LLM Serving default

A bare `bash run_benchmark.sh` is **smoke** (tiny local server). It must not
download Mistral. Pass `--baseline` or `--extended` to start the real model.

Yaml `sweep.profile` remains `baseline` so `self_check` still sees a baseline
yaml default.

Do not run 130 and 131 together, 230 and 231 together, 330 and 331
together, or 430 and 431 together (shared port 30000). Sequential runs
in one orchestrator are fine. On Ubuntu 26.04, 430/431 use torch
2.9.1+cu130; do not share that venv with vLLM 2.13.

Ubuntu 26.04 / 327–331 extras: vLLM must install `uvloop`, `fastapi`, and
`aiohttp` even when extra-deps pip is skipped. AITER comes from the AMD
`amd-aiter` wheel (`import aiter`). SGLang setup defaults
`BENCHMARK_COMPILE_SGLANG=1` and must fail if `import sglang` is missing.
Smoke still uses `tiny_sglang_server.py`. vLLM 328/329 must keep
`TOKENIZER_CONTEXT_SLACK` (`input+output+64`); a tight window returns
HTTP 400. See [`AGENTS.md`](../AGENTS.md) §20.2 and
[`rocm-pytorch-install-contract.md`](rocm-pytorch-install-contract.md).

## 131 / 231 metrics

The workbook Metrics field lists five items. 00_54 231 only persisted #1–#3.
00_55 overlays emit and parse #4 Inter-token latency and #5 Request throughput.

## 124 / 224 — SDXL

Smoke is a local tiny Euler denoiser (no Hugging Face download). Baseline and
extended load `stabilityai/stable-diffusion-xl-base-1.0` through Diffusers.
`guidance_scale` stays the workbook value `0.0` (CFG off). First baseline or
extended run prefetches about 7 GB of weights into the repo `HF_HOME`.
00_78 sets AMD `num_images` baseline/extended to **80 / 160** (15×512/30 was
01:44 load-dominated; 7×1024/50 was 01:56).

Do not compare 00_54 TinyDenoiser ledgers (315000 / 1010000 steps, ~0.4 GB
VRAM) to 00_55 real-SDXL runs.

## DistilBERT 125 / 225 LOAD REPORT

`UNEXPECTED` `vocab_*` and `MISSING` classifier heads are expected when
loading `distilbert-base-uncased` MLM weights into
`DistilBertForSequenceClassification`. That report is not a failure.

## 114 / 314, 115 / 315, 116 / 316 — hipcc on Ubuntu 26.04

These workloads compile a HIP binary from `scripts/build.sh` on every
collection. On Ubuntu 26.04 / ROCm 10.1.0, hipcc is Clang 24. The GCC 15
host pin still supplies `<cstdlib>` to
`__clang_hip_runtime_wrapper.h`, so a bare `hipcc -O2` fails in about one
second on smoke, baseline, and extended. Generation smoke can still pass
if that session's hipcc happened to see GCC 15.

Generated `scripts/build.sh` must `source scripts/lib/hipcc_host_gcc.sh`
or pass `--gcc-install-dir=/usr/lib/gcc/x86_64-linux-gnu/15`. Keep the
`hipmemcpy-bandwidth-amd`, `babelstream-hbm-amd`, and `rccl-bandwidth-amd`
overlays, including `src/hip_memcpy_bw.cpp`, `src/hip_stream.cpp`, and
`src/rccl_perf.cpp`. hipMemcpy `direction: all` must run H2D+D2H+D2D; do
not invent stub CSV rows. Also export `LD_LIBRARY_PATH=/opt/rocm/lib:/opt/rocm/lib64` so
`libamdhip64.so.7` is found at run time.

## 115 / 315 — BabelStream extended under 15 min

00_78 sets extended `num_iterations` to **60000** (70300 at 512M elements
was 17:12 on MI300X). Printed `Copy:` lines are GB/s; do not divide by 1000.

## 116 / 316 — RCCL duration restore

00_78 sets baseline/extended `num_iterations` to **660000 / 1500000** and
`max_bytes` to **64MiB**. Single-rank 200000/16MiB finished in 01:30 because
each collective is a local copy (~4 µs at 16MiB). This VM has one GPU, so
these are still not official multi-rank rccl-tests.

## 120 / 320 — rocHPL extended is N=32768 × 16, not N=65536

Do **not** run extended `N=65536`. Loop 1 hung 228:22 (host fill) and was
SIGTERM’d. Loop 2 died in 2:16 with `hipErrorIllegalAddress` / Tensile
`unordered_map::at`. 00_66 clamps `N>=65536` to 32768 and sets extended
`num_iterations=16` (~12 min; baseline 90 s / 2 repeats × 16). Keep
`size_t nn = n64 * n64` in `src/rochpl.cpp`.

## 117 / 317 — GEMM iteration scale

The locked AMD overlay is a PyTorch `torch.matmul` loop, not `rocblas-bench`.
00_78 sets `num_iterations` baseline/extended to **200000 / 480000**
(72000/201000 was 01:33/04:10 at 4096³).

## 128 / 129 / 328 / 329 — vLLM extended output_len

00_78 sets extended `output_len` to **18600**. 37200 was clamped to ~31744
by `max_model_len=32768`, then the client submitted 16 seqs at concurrency 8
twice (~23 min). Baseline 18600 stays unchanged.

## 130 / 131 — sequential only; isolate each venv

The ten-repeat driver runs 130 then 131. That is not concurrent. Both bind
port 30000, so do not start them together. 131 `server.log` importing
`/root/130_.../third_party/sglang` is a leftover PYTHONPATH / editable
install, not two servers. Runners call `isolate_repo_python`. Setup dies if
`sglang.__file__` is outside this repo or if nanobind/CUTLASS double-registers.

00_78: setup extras must install `jsonschema`. `sglang.launch_server --help`
can succeed while `from sglang.srt.entrypoints.http_server import launch_server`
still raises `No module named 'jsonschema'`. Keep CSV in `raw_output.txt`
for the leftover-DB parser.

00_70: 24.04 130/131 baseline never reached `launch_server`. `ensure_setup`
re-ran `setup.sh` every loop because `import sglang` failed. `sgl-kernel`
`setup_rocm.py` invoked host `g++` with Clang `--gcc-install-dir` from
`CXXFLAGS` (`unrecognized command-line option`). Do not put that flag on
`CXXFLAGS`. Smoke must not require a full SGLang compile when
`tiny_sglang_server.py` is present. NVIDIA 230/231 install CUDA wheels and
do not hit that `g++` line.

00_78 NVIDIA 230/231: Ubuntu 24.04 must pin `sglang==0.5.19`,
`torch==2.13.0+cu130`, and `sglang-kernel==0.4.6.post1` from the SGLang
cu130 index. Unpinned sglang plus force-reinstall torchvision left
`torch 2.14.0+cu130`; baseline `launch_server` then died on
`sgl_kernel` `common_ops.abi3.so` (`c10_cuda_check_implementation`).
Smoke still uses `tiny_sglang_server.py`. Verify `import sgl_kernel`
and `from sglang.srt.entrypoints.http_server import launch_server`.

## 111 / 211 / 311 / 411 — Linux perf PMU

All four use the same `scripts/collect_workload.py` (linux-perf-pmu-amd and
-nvidia ship identical files) and the same five Metrics: IPC, branch
misprediction %, cache misses per 1,000 instructions, pipeline stall %,
and context switches/s. Until 2026-10-02, 211/411 published TSC cycles,
CPU time, utilization, and bogo-ops/s instead, so the vendors were not
comparable. Each yaml stress-ng command runs under `perf stat -x,`. The
stall event is picked by CPU vendor (`cycle_activity.stalls_total` on
Intel, `stalled-cycles-backend` on AMD; `BENCHMARK_PMU_STALL_EVENT`
overrides). When `perf_event_open` is denied or the VM hides the PMU, the
command runs without perf and the four PMU metrics read
`na (<reason>)`; CPU time, utilization, and bogo-ops/s stay as extra
columns. Do not invent IPC or count a missing counter as 0.

`/usr/bin/perf` is often an Ubuntu wrapper that requires
`linux-tools-$(uname -r)`. Setup installs that package when apt has it
and the collector prefers the versioned binary.

## 212 / 412 — lmbench

00_78 NVIDIA: `lat_mem_rd 16 128` is a 16 MB / stride-128 walk. The
old per-command timeouts (smoke 30s / baseline 60s) were too short on
the 00_77 H100 host; `TimeoutExpired` was uncaught so no CSV and empty
ledger metrics. Timeouts are now 120/180/180 (yaml `command_timeout_sec`
overrides). Catch timeout with a one-line fail. Parse the last table
line for `memory_read_latency_ns`, not the first float (`0.00049`).

## 218 / 418 — cuDNN convolution

00_78 NVIDIA: canonical `setup.sh` never installed cuDNN headers.
`scripts/build.sh` is `nvcc ... src/cudnn_conv.cu -lcudnn` and fails
with `cudnn.h: No such file or directory`. Setup now apt-installs
`libcudnn9-*-cuda-12` and `libcudnn9-*-cuda-13` when `src/cudnn_conv.cu`
is present (packages are `|| true` per-name). Do not rewrite locked
`build.sh` / `cudnn_conv.cu`.

## 132 / 332 — AMD RAG Linear stub

Generation defaulted `BENCHMARK_RAG_REAL_MODELS=0` and used hash-embed plus
`torch.nn.Linear`. Baseline finished in about 15 s with exit 0 while the
banner still named MiniLM/Mistral/bge. Use `rag-faiss-end2end-amd` (same
squad_v2 + FAISS + BGE + Mistral path as 232/432). Setup calls
`scripts/install_rag_amd.sh` and must not install a CUDA torch wheel.

00_70: after the real-model overlay, 132 collection still died with
`sentencepiece` missing while loading Mistral's `tokenizer.model`.
`install_rag_amd.sh` (and the NVIDIA sibling) must pip-install
`sentencepiece`. NVIDIA 232 passed because that venv already had a usable
tokenizer path.

## 327 — AMD KV-cache slack

Yaml `max_model_len=8192` has room for 4096+256, but keep the
`vllm-kvcache-amd` slack/HTTPError overlay so 327 matches 328/329.
