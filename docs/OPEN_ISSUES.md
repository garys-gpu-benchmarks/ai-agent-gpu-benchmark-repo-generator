# Open issues

Every finding from a batch or suite review goes here once, with the template that found
it. It leaves this list only when a template fixes it; the fix moves to the Fixed table
with its CHANGELOG entry. Start each review by checking this list against the new
batch, so a finding cannot drop out between templates.

Found in: the template whose batches or runs showed the problem.

## Open

| ID | Found in | Area | Problem | Next step |
|---|---|---|---|---|
| S1 | 00_131 | Suite | `run_benchmark_suite.sh` traps only INT and TERM. A dropped SSH session sends SIGHUP, which killed the extended runs on all four VMs (118, 226, 319, 426). | Design review, then detach or trap HUP. |
| S2 | 00_131 | Suite | No `--resume`. The hand restarts repeated passed runs and lost `-r 3`. | Design review with S1. |
| S3 | 00_131 | Ledger | New columns approved but not built: `suite_id`, `suite_repeat_index`/`_total`, `workload_repeat_index`/`_total`, `runtime_total/setup/benchmark_mm_ss`, `gpu_driver_version`, `kernel_version`, `network_download_mb_s`. Needs `migrate_row()` and the positional reads in `get_benchmark_results.sh` fixed. | Separate template; review the diff on its own. |
| S4 | 00_131 | Suite | A killed run leaves a raw directory and no ledger row. | With S1–S3. |
| S5 | 00_131 | Suite | No suite lock or one-line status file; no heartbeat inside long collectors. | With S1–S3. |
| S6 | 00_131 | Suite | The suite summary counts N/A-EXPECTED as passed. | With S1–S3. |
| S7 | 00_131 | Suite | `run_benchmark.sh --repeat N` (one workload N times) does not exist; the suite's `-w N -r N` does it today. | Add in `run_profiles_in_order`. |
| H1 | 00_131 | Host | x16 runs on one-GPU hosts and publishes three `na` metrics; x09 remote DRAM needs two NUMA nodes; x13 needs LLC counters. | Skip with a SKIPPED-HOST row before launch. |
| H2 | 00_131 | Host (NVIDIA) | 211/411 `perf` missing for the kernel or blocked by `perf_event_paranoid`; 202/402 Xid unreadable without `dmesg`; 209/409 `numactl` cannot bind the second node. | Host bootstrap fixes or explicit skips. |
| H3 | 00_131 | Profiles | Several extended runs take 11–14 min; the 588,000-iteration JAX run (226/426) has no checkpoint; vLLM/SGLang start a server per profile. | Workbook retune and server reuse. |
| M1 | 00_131 | Metric | 120/320 percent of FP64 matrix peak is rocSOLVER LU at N ≤ 32768, not rocHPL; reads as 10% next to NVIDIA's 50%. | Measured DGEMM ceiling, or rename. |
| M2 | 00_131 | Metric | x22 "per-image latency" is batch time ÷ batch size (the inverse of throughput). | Publish mean batch latency. |
| M3 | 00_131 | Metric | 309/409 smoke L3 working set is 2 MB (an 8568Y+ core's L2), so smoke "L3" reads 7–10 ns. | Raise smoke L3 size to ≥ 8 MB. |
| M4 | 00_131 | Metric | x10 "payload rate" is 8 B × threads ÷ latency, not a bandwidth; x10 cache misses count the whole process, including buffer setup. | Measured read pass; misses per access for the DRAM tier. |
| M5 | 00_131 | Metric | x21 FLOP/s is images/s × a constant; "peak GPU memory" is PyTorch's allocation. | FlopCounterMode; rename memory metric. |
| M6 | 00_131 | Metric | 203/403 fail at 75 °C core temperature (403 extended failed at 76 °C with no throttling). | Use the card's slowdown temperature, or ~85 °C. |
| P1 | 00_133 | Parameters | 222/422 and 223/423 hard-code bf16/fp16 and ignore `dtype` (correct today because the workbook asks for the same types). | Map `dtype` onto the model dtype. |
| P2 | 00_133 | Parameters | 126/226/326/426 accept `--device-id` and never use it. | Select `jax.devices()[device_id]`. |
| P3 | 00_133 | Parameters | 216 discards `max_bytes`, `step_factor`, `warmup_iters`, `num_iterations` on one GPU. | Covered by H1. |
| G1 | 00_133 | Generation | After a hand `--validate-only` retry, the manifest keeps the stale finish time and durations, and the retried workload moves to the end of the list. | Recompute on record; keep workload order. |
| C1 | 00_133 | CUDA 13.3 | 220 cuSOLVER LU smoke (N=4096) is about 20% slower on CUDA 13.3 than 12.8 (0.70 vs 0.87 TFLOP/s). | Run 220 `--baseline`; compare with 27.6 TFLOP/s (TEMPLATE_00_131). |
| Q1 | 00_133 | Smoke | Smoke sizes are too small for what some labels claim (64 px images, N=4096, 1-layer model, 2 MB "L3"). | Per-metric review. |
| D1 | 00_133 | Docs | `docs/github-profile-README.md` has no System Requirements section; the live profile README does (network speed, ROCm 10.1.0, CUDA 13.3). | Copy the live README back. |

## Fixed

| ID | Found in | Problem | Fixed in |
|---|---|---|---|
| F1 | 00_131 | Ruff E741 in `tests/test_template_00_131_changes.py`. | 00_132 (`61ec3eb`) |
| F2 | 00_131 | 114/214/314/414 published GB/s under `*_gbps` keys. | 00_132 |
| F3 | 00_132 | Ubuntu 24.04 NVIDIA used CUDA 12.8 while 26.04 used 13.3. | 00_133 |
| F4 | 00_133 | No retry for a temporary remote failure (127, 128, 326 rerun by hand); reasons cut at 300 characters. | 00_134 |
| F5 | 00_133 | The batch console passed 1 MB (specification printed twice per workload; remote output held until SSH returned). | 00_134 |
| F6 | 00_131 | A fresh AMD host was reported as "GPU workloads will fail" and estimated against the NVIDIA table. | 00_134 |
| F7 | 00_131 | Estimates 2–4× too high: whole download-heavy workloads scaled by an unmeasured 100 MB/s. | 00_134 |
| F8 | 00_115 | Preflight exited 1 under Git Bash's `python3` even after finding a working Python. | 00_134 |
