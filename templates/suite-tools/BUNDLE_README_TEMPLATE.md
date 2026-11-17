# @PLATFORM@ benchmark bundle

@WANT@ system and GPU benchmarks for @VENDOR@ GPU machines running Ubuntu @OS@,
each pinned to its tested @VERSION@ release. Other platforms have their own bundle:
@OTHERS@

## Requirements

- A fresh **Ubuntu @OS@** machine with @VENDOR@ GPUs, online, with **root** access (`sudo -i`).
@PREREQ@
- At least 20 GiB free per benchmark: each one installs its own Python environment on
  first run, and the AI benchmarks also download models.
- For @S@23 to @S@32: if a model's Hugging Face license requires it, accept it there and
  `export HF_TOKEN=hf_...`

## Install

```bash
apt-get update && apt-get install -y git tmux
git clone --recurse-submodules https://github.com/@ORG@/@BUNDLE@ /opt/benchmarks
cd /opt/benchmarks
./run_benchmark_suite.sh --list      # all @WANT@ should show as ready
```

Clone with git; GitHub's **Download ZIP** leaves the benchmark folders empty.

## Quick check

```bash
./run_benchmark_suite.sh -w @S@07 --smoke --show-output            # CPU only, about a minute
./run_benchmark_suite.sh -w @S@01,@S@02,@S@14 --smoke --show-output    # installs @STACK@ first: 5 to 20 minutes
```

@RESTART@

Each run ends with a summary. What matters is `0 failed`; if a run fails, it is listed
under `Failed runs:` and the log file is named on the summary's last line.

Smoke runs are small and only prove each benchmark installs, runs and records results.
Quote `baseline` or `extended` numbers.

## Run benchmarks

```bash
./run_benchmark_suite.sh -w @S@05 --baseline --show-output   # one benchmark
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
| `-w @S@01,@S@07` or `-w @S@01-@S@10` | Only these benchmarks |
| `-r 20` | Repeat the whole set 20 times |
| `--fail-fast` | Stop at the first failure |
| `--show-output` | Show each run's output on screen (always written to the log) |
| `-n` | Show what would run, without running it |
| `--help` | All options |

## Results

```bash
./show_metrics.sh @S@07 [--baseline]     # one benchmark's runs and per-profile means
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
[gpu-bench-suite](https://github.com/@ORG@/gpu-bench-suite) and run
`./get_benchmark_results.sh --host <address>` (add `--port N` if ssh is not on 22).
`list_runs.sh` and `show_metrics.sh` there accept `--host` too.

## Reading the results

A value of `na (reason)` means not measured on this machine, never an invented number.

| Benchmark | Note |
|---|---|
| @S@16 | One GPU: bandwidth metrics are `na (requires at least two GPUs)`; the run still passes. |
| @S@11 | Hardware counters are `na` when `perf` is missing for the running kernel or `perf_event_paranoid` denies access. |
| @S@06 | Measures a file (`data/fio_target.bin`) on the benchmark's disk, not a raw NVMe device. |
| @S@08 | Measures loopback (`127.0.0.1`), not a network card. |
| @S@30, @S@31 | Every profile, smoke included, starts the real SGLang server: allow about 2 minutes for it to start, and longer on the first run, which downloads the Mistral weights. |

## Update

```bash
cd /opt/benchmarks && git pull && git submodule update --init --recursive
```

Do not use `git submodule update --remote`; it moves benchmarks off their tested release.

## Benchmarks

| # | Repository |
|---|---|
@ROWS@
