# GPU Performance Benchmarking & Platform Validation Matrix

A standardized matrix of 32 hardware, compute, and AI inference validation workloads, run on AMD (ROCm) and NVIDIA (CUDA) accelerators under Ubuntu 24.04 and Ubuntu 26.04 LTS: four platform bundles, 128 workload repositories.

**Lab technicians: start with [Install on a GPU Host](#install-on-a-gpu-host).** Pick your platform, copy one block, paste it into a root shell.

---

## Install on a GPU Host

**1. Find your platform.** On the GPU host:

```bash
. /etc/os-release && echo "Ubuntu $VERSION_ID"   # 24.04 or 26.04
lspci | grep -iE 'vga|3d|display'               # AMD (Instinct MI-series) or NVIDIA
```

**2. Become root** (`sudo -i`), then paste the block for your platform. It installs `git`, downloads all 32 workloads into `/opt/benchmarks`, lists them (every line should say `ready`), and runs three short smoke tests: the GPU software stack, GPU health, and HBM memory bandwidth.

### AMD · Ubuntu 24.04 — workloads 101–132

```bash
apt-get update && apt-get install -y git tmux
git clone --recurse-submodules https://github.com/garys-gpu-benchmarks/bundle-amd-ubuntu-2404 /opt/benchmarks
cd /opt/benchmarks && ./run.sh list
./run_benchmark_suite.sh -w 101,102,115 -p smoke
```

### NVIDIA · Ubuntu 24.04 — workloads 201–232

```bash
apt-get update && apt-get install -y git tmux
git clone --recurse-submodules https://github.com/garys-gpu-benchmarks/bundle-nvidia-ubuntu-2404 /opt/benchmarks
cd /opt/benchmarks && ./run.sh list
./run_benchmark_suite.sh -w 201,202,215 -p smoke
```

### AMD · Ubuntu 26.04 — workloads 301–332

```bash
apt-get update && apt-get install -y git tmux
git clone --recurse-submodules https://github.com/garys-gpu-benchmarks/bundle-amd-ubuntu-2604 /opt/benchmarks
cd /opt/benchmarks && ./run.sh list
./run_benchmark_suite.sh -w 301,302,315 -p smoke
```

### NVIDIA · Ubuntu 26.04 — workloads 401–432

```bash
apt-get update && apt-get install -y git tmux
git clone --recurse-submodules https://github.com/garys-gpu-benchmarks/bundle-nvidia-ubuntu-2604 /opt/benchmarks
cd /opt/benchmarks && ./run.sh list
./run_benchmark_suite.sh -w 401,402,415 -p smoke
```

The first run takes much longer than later ones: it installs the ROCm or CUDA stack and each workload's software. **On AMD, setup may restart the machine once.** If it does, log back in, wait a few minutes for setup to finish on its own, then run the same `./run_benchmark_suite.sh` line again.

> Use `git clone` exactly as shown. GitHub's **Download ZIP** leaves the workload folders empty.
>
> For the AI model workloads (x23–x31), if a model's Hugging Face license requires it, accept the license there and run `export HF_TOKEN=hf_...` first.

### After the install

All commands run from `/opt/benchmarks`. Each command prints full usage with `--help`.

| Task | Command |
|---|---|
| Smoke test every workload (installs each on first use) | `./run_benchmark_suite.sh -p smoke` |
| One workload, baseline profile (example: 107) | `./run_benchmark_suite.sh -w 107 -p baseline` |
| A range of workloads | `./run_benchmark_suite.sh -w 101-110 -p smoke` |
| One workload with its output on screen | `./run.sh 105` · `./run.sh 105 --baseline` |
| Everything, all three profiles (many hours) | `tmux new -s bench` then `./run_benchmark_suite.sh` |
| Soak test: everything, 20 times | `./run_benchmark_suite.sh -r 20` |
| Preview what would run | `./run_benchmark_suite.sh --dry-run` |
| Update to the newest release | `git pull && git submodule update --init --recursive` |

Swap the workload numbers for your platform (107 → 207, 307 or 407). Logs go to `/opt/benchmarks/benchmark_suite_log/`, and the suite ends with a pass/fail summary. Inside `tmux`, detach with **Ctrl+B** then **D** and reattach with `tmux attach -t bench`.

### Collecting results on your laptop

[`gpu-bench-suite`](https://github.com/garys-gpu-benchmarks/gpu-bench-suite) has two operator scripts that run on your laptop (Git Bash on Windows) and reach the host over SSH:

```bash
git clone https://github.com/garys-gpu-benchmarks/gpu-bench-suite && cd gpu-bench-suite
GPU_HOST=203.0.113.10                              # replace with your GPU host's IP
./scripts/get_remote_info.sh root@$GPU_HOST        # copy ledgers, raw and parsed results, suite logs
./scripts/show_metrics.sh 115 --host $GPU_HOST     # one workload's runs, per-profile means
```

---

## Benchmark Suites

| Bundle repository | GPU Platform | Operating System | Workloads |
|---|---|---|---:|
| [`bundle-amd-ubuntu-2404`](https://github.com/garys-gpu-benchmarks/bundle-amd-ubuntu-2404) | AMD / ROCm | Ubuntu 24.04 | 101–132 |
| [`bundle-nvidia-ubuntu-2404`](https://github.com/garys-gpu-benchmarks/bundle-nvidia-ubuntu-2404) | NVIDIA / CUDA | Ubuntu 24.04 | 201–232 |
| [`bundle-amd-ubuntu-2604`](https://github.com/garys-gpu-benchmarks/bundle-amd-ubuntu-2604) | AMD / ROCm | Ubuntu 26.04 | 301–332 |
| [`bundle-nvidia-ubuntu-2604`](https://github.com/garys-gpu-benchmarks/bundle-nvidia-ubuntu-2604) | NVIDIA / CUDA | Ubuntu 26.04 | 401–432 |

Each bundle holds its 32 workload repositories as git submodules pinned to a tested release. Workload *x*NN is the same test on every platform: 115, 215, 315 and 415 are all BabelStream HBM bandwidth.

**128 total benchmark workloads**

---

## Benchmark Categories

The workload suites cover seven primary areas:

- **Memory, Bandwidth & Data Movement** — HBM, fabric, host/device transfers, cache, and bandwidth stress
- **AI Training & Inference** — CNN, Transformer, diffusion, and JAX model training and inference
- **Compute & Math Kernels** — BLAS, LINPACK, microbenchmarks, and mathematical compute kernels
- **LLM Inference & Serving** — vLLM throughput and latency, KV cache, token generation, and SGLang serving
- **System Validation & Reliability** — correctness testing and hardware/software health validation
- **System Profiling & Performance Analysis** — telemetry, counters, and timing characterization
- **End-to-End Application Pipelines** — full-stack application paths such as FAISS-based RAG

---

## Execution Profiles

Where applicable, workloads support three execution profiles:

| Profile | Typical Runtime | Purpose |
|---|---:|---|
| **Smoke** | ≤ 1 minute | Quick installation and functionality validation |
| **Baseline** | 3–5 minutes | Standard benchmark execution |
| **Extended** | 8–15 minutes | Longer performance characterization |

Runtimes are per workload, after its one-time install.

---

## 📊 Workload Repository Matrix

| # | Workload Domain & Description | AMD (Ubuntu 24.04) | NVIDIA (Ubuntu 24.04) | AMD (Ubuntu 26.04) | NVIDIA (Ubuntu 26.04) |
| :-: | :--- | :---: | :---: | :---: | :---: |
| **01** | System Config Verification | [101](https://github.com/garys-gpu-benchmarks/101-sys-bench-amd-rocm-stack-validation-ubu2404) | [201](https://github.com/garys-gpu-benchmarks/201-sys-bench-nvidia-cuda-stack-validation-ubu2404) | [301](https://github.com/garys-gpu-benchmarks/301-sys-bench-amd-rocm-stack-validation-ubu2604) | [401](https://github.com/garys-gpu-benchmarks/401-sys-bench-nvidia-cuda-stack-validation-ubu2604) |
| **02** | System Validation (Clocks, Temp, Health) | [102](https://github.com/garys-gpu-benchmarks/102-sys-bench-amd-rocm-health-validation-ubu2404) | [202](https://github.com/garys-gpu-benchmarks/202-sys-bench-nvidia-gpu-health-validation-ubu2404) | [302](https://github.com/garys-gpu-benchmarks/302-sys-bench-amd-rocm-health-validation-ubu2604) | [402](https://github.com/garys-gpu-benchmarks/402-sys-bench-nvidia-gpu-health-validation-ubu2604) |
| **03** | CPU + System Stress Stability | [103](https://github.com/garys-gpu-benchmarks/103-sys-bench-amd-system-stress-stability-ubu2404) | [203](https://github.com/garys-gpu-benchmarks/203-sys-bench-nvidia-system-stress-stability-ubu2404) | [303](https://github.com/garys-gpu-benchmarks/303-sys-bench-amd-system-stress-stability-ubu2604) | [403](https://github.com/garys-gpu-benchmarks/403-sys-bench-nvidia-system-stress-stability-ubu2604) |
| **04** | Silent Data Corruption (SDC / ECC) | [104](https://github.com/garys-gpu-benchmarks/104-gpu-bench-amd-sdc-ecc-integrity-ubu2404) | [204](https://github.com/garys-gpu-benchmarks/204-gpu-bench-nvidia-sdc-ecc-integrity-ubu2404) | [304](https://github.com/garys-gpu-benchmarks/304-gpu-bench-amd-sdc-ecc-integrity-ubu2604) | [404](https://github.com/garys-gpu-benchmarks/404-gpu-bench-nvidia-sdc-ecc-integrity-ubu2604) |
| **05** | PyTorch Tensor Op Correctness Suite | [105](https://github.com/garys-gpu-benchmarks/105-gpu-bench-amd-pytorch-tensor-correctness-ubu2404) | [205](https://github.com/garys-gpu-benchmarks/205-gpu-bench-nvidia-pytorch-tensor-correctness-ubu2404) | [305](https://github.com/garys-gpu-benchmarks/305-gpu-bench-amd-pytorch-tensor-correctness-ubu2604) | [405](https://github.com/garys-gpu-benchmarks/405-gpu-bench-nvidia-pytorch-tensor-correctness-ubu2604) |
| **06** | FIO NVMe Storage Sweep | [106](https://github.com/garys-gpu-benchmarks/106-sys-bench-amd-fio-nvme-sweep-ubu2404) | [206](https://github.com/garys-gpu-benchmarks/206-sys-bench-nvidia-fio-nvme-sweep-ubu2404) | [306](https://github.com/garys-gpu-benchmarks/306-sys-bench-amd-fio-nvme-sweep-ubu2604) | [406](https://github.com/garys-gpu-benchmarks/406-sys-bench-nvidia-fio-nvme-sweep-ubu2604) |
| **07** | STREAM CPU DDR5 Bandwidth | [107](https://github.com/garys-gpu-benchmarks/107-sys-bench-amd-stream-ddr5-bandwidth-ubu2404) | [207](https://github.com/garys-gpu-benchmarks/207-sys-bench-nvidia-stream-ddr5-bandwidth-ubu2404) | [307](https://github.com/garys-gpu-benchmarks/307-sys-bench-amd-stream-ddr5-bandwidth-ubu2604) | [407](https://github.com/garys-gpu-benchmarks/407-sys-bench-nvidia-stream-ddr5-bandwidth-ubu2604) |
| **08** | iPerf3 Network Performance Sweep | [108](https://github.com/garys-gpu-benchmarks/108-sys-bench-amd-iperf3-network-performance-ubu2404) | [208](https://github.com/garys-gpu-benchmarks/208-sys-bench-nvidia-iperf3-network-performance-ubu2404) | [308](https://github.com/garys-gpu-benchmarks/308-sys-bench-amd-iperf3-network-performance-ubu2604) | [408](https://github.com/garys-gpu-benchmarks/408-sys-bench-nvidia-iperf3-network-performance-ubu2604) |
| **09** | multichase NUMA Latency (Pointer-Chase) | [109](https://github.com/garys-gpu-benchmarks/109-sys-bench-amd-multichase-numa-latency-ubu2404) | [209](https://github.com/garys-gpu-benchmarks/209-sys-bench-nvidia-multichase-numa-latency-ubu2404) | [309](https://github.com/garys-gpu-benchmarks/309-sys-bench-amd-multichase-numa-latency-ubu2604) | [409](https://github.com/garys-gpu-benchmarks/409-sys-bench-nvidia-multichase-numa-latency-ubu2604) |
| **10** | NUMA Cache Latency Sweep | [110](https://github.com/garys-gpu-benchmarks/110-sys-bench-amd-numa-cache-performance-ubu2404) | [210](https://github.com/garys-gpu-benchmarks/210-sys-bench-nvidia-numa-cache-performance-ubu2404) | [310](https://github.com/garys-gpu-benchmarks/310-sys-bench-amd-numa-cache-performance-ubu2604) | [410](https://github.com/garys-gpu-benchmarks/410-sys-bench-nvidia-numa-cache-performance-ubu2604) |
| **11** | Linux perf PMU Analysis Harness | [111](https://github.com/garys-gpu-benchmarks/111-sys-bench-amd-linux-perf-pmu-ubu2404) | [211](https://github.com/garys-gpu-benchmarks/211-sys-bench-nvidia-linux-perf-pmu-ubu2404) | [311](https://github.com/garys-gpu-benchmarks/311-sys-bench-amd-linux-perf-pmu-ubu2604) | [411](https://github.com/garys-gpu-benchmarks/411-sys-bench-nvidia-linux-perf-pmu-ubu2604) |
| **12** | lmbench OS Microbench Suite | [112](https://github.com/garys-gpu-benchmarks/112-sys-bench-amd-lmbench-microbench-suite-ubu2404) | [212](https://github.com/garys-gpu-benchmarks/212-sys-bench-nvidia-lmbench-microbench-suite-ubu2404) | [312](https://github.com/garys-gpu-benchmarks/312-sys-bench-amd-lmbench-microbench-suite-ubu2604) | [412](https://github.com/garys-gpu-benchmarks/412-sys-bench-nvidia-lmbench-microbench-suite-ubu2604) |
| **13** | GUPS Random Memory Access | [113](https://github.com/garys-gpu-benchmarks/113-sys-bench-amd-gups-random-memory-ubu2404) | [213](https://github.com/garys-gpu-benchmarks/213-sys-bench-nvidia-gups-random-memory-ubu2404) | [313](https://github.com/garys-gpu-benchmarks/313-sys-bench-amd-gups-random-memory-ubu2604) | [413](https://github.com/garys-gpu-benchmarks/413-sys-bench-nvidia-gups-random-memory-ubu2604) |
| **14** | Host/Device Memcpy (H2D, D2H, D2D) | [114](https://github.com/garys-gpu-benchmarks/114-gpu-bench-amd-hipmemcpy-transfer-bandwidth-ubu2404) | [214](https://github.com/garys-gpu-benchmarks/214-gpu-bench-nvidia-memcpy-transfer-bandwidth-ubu2404) | [314](https://github.com/garys-gpu-benchmarks/314-gpu-bench-amd-hipmemcpy-transfer-bandwidth-ubu2604) | [414](https://github.com/garys-gpu-benchmarks/414-gpu-bench-nvidia-memcpy-transfer-bandwidth-ubu2604) |
| **15** | BabelStream HBM Bandwidth | [115](https://github.com/garys-gpu-benchmarks/115-gpu-bench-amd-babelstream-hbm-bandwidth-ubu2404) | [215](https://github.com/garys-gpu-benchmarks/215-gpu-bench-nvidia-babelstream-hbm-bandwidth-ubu2404) | [315](https://github.com/garys-gpu-benchmarks/315-gpu-bench-amd-babelstream-hbm-bandwidth-ubu2604) | [415](https://github.com/garys-gpu-benchmarks/415-gpu-bench-nvidia-babelstream-hbm-bandwidth-ubu2604) |
| **16** | Collective Fabric Bandwidth (RCCL / NCCL) | [116](https://github.com/garys-gpu-benchmarks/116-gpu-bench-amd-rccl-bandwidth-test-ubu2404) | [216](https://github.com/garys-gpu-benchmarks/216-gpu-bench-nvidia-nccl-bandwidth-test-ubu2404) | [316](https://github.com/garys-gpu-benchmarks/316-gpu-bench-amd-rccl-bandwidth-test-ubu2604) | [416](https://github.com/garys-gpu-benchmarks/416-gpu-bench-nvidia-nccl-bandwidth-test-ubu2604) |
| **17** | GEMM Microbenchmark (rocBLAS / cuBLAS) | [117](https://github.com/garys-gpu-benchmarks/117-gpu-bench-amd-gemm-rocblas-micro-ubu2404) | [217](https://github.com/garys-gpu-benchmarks/217-gpu-bench-nvidia-gemm-cublas-micro-ubu2404) | [317](https://github.com/garys-gpu-benchmarks/317-gpu-bench-amd-gemm-rocblas-micro-ubu2604) | [417](https://github.com/garys-gpu-benchmarks/417-gpu-bench-nvidia-gemm-cublas-micro-ubu2604) |
| **18** | Convolution Solver (MIOpen / cuDNN) | [118](https://github.com/garys-gpu-benchmarks/118-gpu-bench-amd-miopen-convolution-micro-ubu2404) | [218](https://github.com/garys-gpu-benchmarks/218-gpu-bench-nvidia-cudnn-convolution-micro-ubu2404) | [318](https://github.com/garys-gpu-benchmarks/318-gpu-bench-amd-miopen-convolution-micro-ubu2604) | [418](https://github.com/garys-gpu-benchmarks/418-gpu-bench-nvidia-cudnn-convolution-micro-ubu2604) |
| **19** | PyTorch / TorchBench Microkernel Suite | [119](https://github.com/garys-gpu-benchmarks/119-gpu-bench-amd-torch-micro-suite-ubu2404) | [219](https://github.com/garys-gpu-benchmarks/219-gpu-bench-nvidia-torch-micro-suite-ubu2404) | [319](https://github.com/garys-gpu-benchmarks/319-gpu-bench-amd-torch-micro-suite-ubu2604) | [419](https://github.com/garys-gpu-benchmarks/419-gpu-bench-nvidia-torch-micro-suite-ubu2604) |
| **20** | High Performance Linpack (HPL FP64) | [120](https://github.com/garys-gpu-benchmarks/120-gpu-bench-amd-linpack-rochpl-fp64-ubu2404) | [220](https://github.com/garys-gpu-benchmarks/220-gpu-bench-nvidia-linpack-hpl-fp64-ubu2404) | [320](https://github.com/garys-gpu-benchmarks/320-gpu-bench-amd-linpack-rochpl-fp64-ubu2604) | [420](https://github.com/garys-gpu-benchmarks/420-gpu-bench-nvidia-linpack-hpl-fp64-ubu2604) |
| **21** | ResNet-50 FP16 Training Step | [121](https://github.com/garys-gpu-benchmarks/121-gpu-bench-amd-resnet50-pytorch-training-ubu2404) | [221](https://github.com/garys-gpu-benchmarks/221-gpu-bench-nvidia-resnet50-pytorch-training-ubu2404) | [321](https://github.com/garys-gpu-benchmarks/321-gpu-bench-amd-resnet50-pytorch-training-ubu2604) | [421](https://github.com/garys-gpu-benchmarks/421-gpu-bench-nvidia-resnet50-pytorch-training-ubu2604) |
| **22** | ResNet-50 BF16 Inference Throughput | [122](https://github.com/garys-gpu-benchmarks/122-gpu-bench-amd-resnet50-pytorch-inference-ubu2404) | [222](https://github.com/garys-gpu-benchmarks/222-gpu-bench-nvidia-resnet50-pytorch-inference-ubu2404) | [322](https://github.com/garys-gpu-benchmarks/322-gpu-bench-amd-resnet50-pytorch-inference-ubu2604) | [422](https://github.com/garys-gpu-benchmarks/422-gpu-bench-nvidia-resnet50-pytorch-inference-ubu2604) |
| **23** | BERT Base Inference Sweep | [123](https://github.com/garys-gpu-benchmarks/123-gpu-bench-amd-bert-base-inference-ubu2404) | [223](https://github.com/garys-gpu-benchmarks/223-gpu-bench-nvidia-bert-base-inference-ubu2404) | [323](https://github.com/garys-gpu-benchmarks/323-gpu-bench-amd-bert-base-inference-ubu2604) | [423](https://github.com/garys-gpu-benchmarks/423-gpu-bench-nvidia-bert-base-inference-ubu2604) |
| **24** | Stable Diffusion XL Latency Baseline | [124](https://github.com/garys-gpu-benchmarks/124-gpu-bench-amd-sdxl-diffusers-latency-ubu2404) | [224](https://github.com/garys-gpu-benchmarks/224-gpu-bench-nvidia-sdxl-diffusers-latency-ubu2404) | [324](https://github.com/garys-gpu-benchmarks/324-gpu-bench-amd-sdxl-diffusers-latency-ubu2604) | [424](https://github.com/garys-gpu-benchmarks/424-gpu-bench-nvidia-sdxl-diffusers-latency-ubu2604) |
| **25** | DistilBERT NLP Classification Baseline | [125](https://github.com/garys-gpu-benchmarks/125-gpu-bench-amd-distilbert-hf-classification-ubu2404) | [225](https://github.com/garys-gpu-benchmarks/225-gpu-bench-nvidia-distilbert-hf-classification-ubu2404) | [325](https://github.com/garys-gpu-benchmarks/325-gpu-bench-amd-distilbert-hf-classification-ubu2604) | [425](https://github.com/garys-gpu-benchmarks/425-gpu-bench-nvidia-distilbert-hf-classification-ubu2604) |
| **26** | JAX XLA Transformer Forward Pass | [126](https://github.com/garys-gpu-benchmarks/126-gpu-bench-amd-jax-xla-forwardpass-ubu2404) | [226](https://github.com/garys-gpu-benchmarks/226-gpu-bench-nvidia-jax-xla-forwardpass-ubu2404) | [326](https://github.com/garys-gpu-benchmarks/326-gpu-bench-amd-jax-xla-forwardpass-ubu2604) | [426](https://github.com/garys-gpu-benchmarks/426-gpu-bench-nvidia-jax-xla-forwardpass-ubu2604) |
| **27** | vLLM KV Cache Stress Test | [127](https://github.com/garys-gpu-benchmarks/127-gpu-bench-amd-vllm-kvcache-stress-ubu2404) | [227](https://github.com/garys-gpu-benchmarks/227-gpu-bench-nvidia-vllm-kvcache-stress-ubu2404) | [327](https://github.com/garys-gpu-benchmarks/327-gpu-bench-amd-vllm-kvcache-stress-ubu2604) | [427](https://github.com/garys-gpu-benchmarks/427-gpu-bench-nvidia-vllm-kvcache-stress-ubu2604) |
| **28** | vLLM Throughput & Latency Sweep | [128](https://github.com/garys-gpu-benchmarks/128-gpu-bench-amd-vllm-throughput-latency-ubu2404) | [228](https://github.com/garys-gpu-benchmarks/228-gpu-bench-nvidia-vllm-throughput-latency-ubu2404) | [328](https://github.com/garys-gpu-benchmarks/328-gpu-bench-amd-vllm-throughput-latency-ubu2604) | [428](https://github.com/garys-gpu-benchmarks/428-gpu-bench-nvidia-vllm-throughput-latency-ubu2604) |
| **29** | vLLM Mistral Token Generation | [129](https://github.com/garys-gpu-benchmarks/129-gpu-bench-amd-vllm-mistral-rocm-ubu2404) | [229](https://github.com/garys-gpu-benchmarks/229-gpu-bench-nvidia-vllm-mistral-cuda-ubu2404) | [329](https://github.com/garys-gpu-benchmarks/329-gpu-bench-amd-vllm-mistral-rocm-ubu2604) | [429](https://github.com/garys-gpu-benchmarks/429-gpu-bench-nvidia-vllm-mistral-cuda-ubu2604) |
| **30** | SGLang Prompt-Response Benchmark | [130](https://github.com/garys-gpu-benchmarks/130-gpu-bench-amd-sglang-prompt-response-ubu2404) | [230](https://github.com/garys-gpu-benchmarks/230-gpu-bench-nvidia-sglang-prompt-response-ubu2404) | [330](https://github.com/garys-gpu-benchmarks/330-gpu-bench-amd-sglang-prompt-response-ubu2604) | [430](https://github.com/garys-gpu-benchmarks/430-gpu-bench-nvidia-sglang-prompt-response-ubu2604) |
| **31** | SGLang Serving Latency Benchmark | [131](https://github.com/garys-gpu-benchmarks/131-gpu-bench-amd-sglang-serving-latency-ubu2404) | [231](https://github.com/garys-gpu-benchmarks/231-gpu-bench-nvidia-sglang-serving-latency-ubu2404) | [331](https://github.com/garys-gpu-benchmarks/331-gpu-bench-amd-sglang-serving-latency-ubu2604) | [431](https://github.com/garys-gpu-benchmarks/431-gpu-bench-nvidia-sglang-serving-latency-ubu2604) |
| **32** | End-to-End FAISS RAG Pipeline | [132](https://github.com/garys-gpu-benchmarks/132-gpu-bench-amd-rag-faiss-end2end-ubu2404) | [232](https://github.com/garys-gpu-benchmarks/232-gpu-bench-nvidia-rag-faiss-end2end-ubu2404) | [332](https://github.com/garys-gpu-benchmarks/332-gpu-bench-amd-rag-faiss-end2end-ubu2604) | [432](https://github.com/garys-gpu-benchmarks/432-gpu-bench-nvidia-rag-faiss-end2end-ubu2604) |

---

## Repository Layout & Execution Model

Every one of the 128 repositories follows the same structure, so once you have run one, you know how to run all of them:

```text
<NNN>-<repo>/
├── setup.sh              # installs the ROCm/CUDA + Python stack (run_benchmark.sh calls it on first use)
├── run_benchmark.sh      # bash run_benchmark.sh --profile smoke|baseline|extended [--validate]
├── config/               # benchmark_config.yaml, hardware profiles
├── scripts/              # parse_results.py, validate_results.py, ...
├── tests/                # correctness thresholds
└── results/
    ├── raw/              # per-run logs, metrics, artifacts
    ├── parsed/           # SQLite + CSV
    ├── benchmark.db      # all runs (SQLite)
    └── summary.json      # latest run summary
```

### Running a single workload without a bundle

```bash
git clone https://github.com/garys-gpu-benchmarks/115-gpu-bench-amd-babelstream-hbm-bandwidth-ubu2404
cd 115-gpu-bench-amd-babelstream-hbm-bandwidth-ubu2404
bash setup.sh --assume-yes
bash run_benchmark.sh --profile smoke --validate   # ~1 min
bash run_benchmark.sh --baseline                   # 3–5 min
bash run_benchmark.sh --extended                   # 8–15 min
```

Each run records latency, throughput or GFLOPS, and memory high-water marks under `results/raw/`, then persists SQLite and CSV under `results/parsed/` for cross-node aggregation.

---

## How These Repositories Are Built

Every repository in this matrix is generated, not hand-written, by
[`ai-agent-gpu-benchmark-repo-generator`](https://github.com/garymichaelbass/ai-agent-gpu-benchmark-repo-generator) —
a spec-driven framework that turns one row of a workload spreadsheet into a
complete, execution-ready benchmark repo: setup script, README, PRD/SPEC,
CI workflows, parsing/validation logic, and a smoke test, with zero manual
scaffolding. See that repo for the ten-minute quickstart to generate your own.
