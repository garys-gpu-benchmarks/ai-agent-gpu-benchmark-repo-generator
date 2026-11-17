# AMD ROCm - Ubuntu 24.04 benchmark bundle

2 system and GPU benchmarks for AMD GPU machines running Ubuntu 24.04,
each pinned to its tested v1.0.42 release. Other platforms have their own bundle:
[NVIDIA 24.04](https://github.com/garys-gpu-benchmarks/bundle-nvidia-ubuntu-2404) ·
[AMD 26.04](https://github.com/garys-gpu-benchmarks/bundle-amd-ubuntu-2604) ·
[NVIDIA 26.04](https://github.com/garys-gpu-benchmarks/bundle-nvidia-ubuntu-2604)

## Requirements

- A fresh **Ubuntu 24.04** machine with AMD GPUs, online, with **root** access (`sudo -i`).
- The first run installs ROCm and may restart the machine once; that must be acceptable.
- At least 20 GiB free per benchmark: each one installs its own Python environment on
  first run, and the AI benchmarks also download models.
- For 123 to 132: if a model's Hugging Face license requires it, accept it there and
  `export HF_TOKEN=hf_...`

## Install

```bash
apt-get update && apt-get install -y git tmux
git clone --recurse-submodules https://github.com/garys-gpu-benchmarks/bundle-amd-ubuntu-2404 /opt/benchmarks
cd /opt/benchmarks
./run_benchmark_suite.sh --list      # all 2 should show as ready
```

Clone with git; GitHub's **Download ZIP** leaves the benchmark folders empty.

## Quick check

```bash
./run_benchmark_suite.sh -w 107 --smoke --show-output            # CPU only, about a minute
./run_benchmark_suite.sh -w 101,102,114 --smoke --show-output    # installs ROCm first: 5 to 20 minutes
```

**If the machine restarts.** Installing ROCm may restart the machine once,
which closes your connection. This is planned, not a failure:

1. Log in again as root after a few minutes. Setup continues on its own after
   the restart.
2. To watch it: `tail -f /opt/benchmarks/101-*/results/install_status.txt`
   (Ctrl+C stops watching, not setup).
3. Run the same command again. If it says setup is still running, wait a few
   minutes and run it again. Benchmarks already installed are not installed
   again.

Each run ends with a summary. What matters is `0 failed`; if a run fails, it is listed
under `Failed runs:` and the log file is named on the summary's last line.

Smoke runs are small and only prove each benchmark installs, runs and records results.
Quote `baseline` or `extended` numbers.

## Run benchmarks

```bash
./run_benchmark_suite.sh -w 105 --baseline --show-output   # one benchmark
```

For the full suite (many hours), run the Quick check first on a new machine, then use
`tmux` so it survives a dropped connection (detach **Ctrl+B D**, reattach
`tmux attach -t bench`):

```bash
tmux new -s bench
cd /opt/benchmarks && ./run_benchmark_suite.sh --smoke --baseline --extended
```

| Option | Effect |
|---|---|
| `--smoke` `--baseline` `--extended` | Profiles to run, in that order. Default: `--smoke` |
| `-w 101,107` or `-w 101-110` | Only these benchmarks |
| `-r 20` | Repeat the whole set 20 times |
| `--fail-fast` | Stop at the first failure |
| `--show-output` | Show each run's output on screen (always written to the log) |
| `-n` | Show what would run, without running it |
| `--help` | All options |

## Results

```bash
./show_metrics.sh 107 [--baseline]     # one benchmark's runs and per-profile means
./list_runs.sh [--failed]                # every run on this machine
./get_benchmark_results.sh -o ~/results   # copy ledger, results and logs into one folder
```

| What | Where |
|---|---|
| Suite logs | `/opt/benchmarks/benchmark_suite_log/` |
| Per-benchmark results | `/opt/benchmarks/<benchmark>/results/` |
| Runtime ledger (one line per run) | `/var/opt/benchmarks/runtime_ledger.csv` |
| Installed release | `git -C /opt/benchmarks describe --tags` |

To pull results to your laptop (Git Bash on Windows works), clone
[gpu-bench-suite](https://github.com/garys-gpu-benchmarks/gpu-bench-suite) and run
`./get_benchmark_results.sh --host <address>` (add `--port N` if ssh is not on 22).
`list_runs.sh` and `show_metrics.sh` there accept `--host` too.

## Reading the results

A value of `na (reason)` means not measured on this machine, never an invented number.

| Benchmark | Note |
|---|---|
| 116 | One GPU: bandwidth metrics are `na (requires at least two GPUs)`; the run still passes. |
| 111 | Hardware counters are `na` when `perf` is missing for the running kernel or `perf_event_paranoid` denies access. |
| 106 | Measures a file (`data/fio_target.bin`) on the benchmark's disk, not a raw NVMe device. |
| 108 | Measures loopback (`127.0.0.1`), not a network card. |
| 130, 131 | Every profile, smoke included, starts the real SGLang server: allow about 2 minutes for it to start, and longer on the first run, which downloads the Mistral weights. |

## Update

```bash
cd /opt/benchmarks && git pull && git submodule update --init --recursive
```

Do not use `git submodule update --remote`; it moves benchmarks off their tested release.

## Benchmarks

| # | Repository |
|---|---|
| 101 | [rocm-stack-validation](https://github.com/garys-gpu-benchmarks/101-sys-bench-amd-rocm-stack-validation-ubu2404) |
| 107 | [stream-ddr5-bandwidth](https://github.com/garys-gpu-benchmarks/107-sys-bench-amd-stream-ddr5-bandwidth-ubu2404) |
