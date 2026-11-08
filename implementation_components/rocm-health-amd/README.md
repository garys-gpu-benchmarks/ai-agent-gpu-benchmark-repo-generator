# rocm-health-amd

Primary collector for AMD ROCm System Validation (102 / 302).

Parameters (`config/benchmark_config.yaml` sweep, or the matching `run_benchmark.sh` flags):

- `monitor_duration_sec`: sample once per second for this long (smoke 5, baseline 200, extended 580). Temperature is the peak over the window.
- `expected_gpu_count`: fewest HSA GPU agents that must stay visible; fewer fails the run.
- `min_pcie_link_width`: narrowest acceptable link on every AMD GPU; narrower fails the run. An unreadable width is skipped and noted.

## Init copies and locks

- `scripts/collect_workload.py`

## Mixins expected

- `harness-self-check`
- `rocm-tool-verify-build`

## Agent leftover

Docs and `requirements.txt`. Do not rewrite the collector.
