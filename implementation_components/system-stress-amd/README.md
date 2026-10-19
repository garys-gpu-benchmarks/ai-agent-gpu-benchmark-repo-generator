# system-stress-amd

Primary collector for AMD CPU + System Stress (103 / 303).

## Init copies and locks

- `scripts/collect_workload.py` (stress-ng + amd-smi / sysfs telemetry). When `gpu_load_percent` > 0 it drives the GPU with the
  repository-local `rocblas-bench` (FP32 8192³ GEMMs, duty-cycled to the requested percent; log in `gpu_load.log`). If that load
  never runs or GPU activity never reaches 10%, peak junction temperature and sustained GPU power are published as `na (GPU load
  did not run: …)` instead of idle readings. (Until 2026-10-19 the load was `python -c "import torch …"`, which died silently
  because torch is not installed, so these two metrics were idle values.)

## Mixins expected

- `harness-self-check`
- `rocblas-clients-build` (protected `rocm_compile_rocblas_bench`, staging PATH)

## Does not provide

A GEMM sweep. Framework still requires install+verify of `rocblas-bench`. Smoke-check must not apply `transa` / `command_status` GEMM runner rules.

## Agent leftover

Docs and `requirements.txt`. Do not rewrite the collector. Troubleshooting must name the staging binary path.
