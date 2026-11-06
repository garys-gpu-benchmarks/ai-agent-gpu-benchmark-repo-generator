<!--
====================================================================
README_TEMPLATE.md — rendered by scripts/fill_generated_docs.py
====================================================================
- {{Field Name}} tokens come from benchmark_specification.json and
  config/ci_contract.yaml (the CI * tokens).
- [[GENERATE: readme.<section>]] markers are rendered by
  scripts/readme_sections.py from the workbook row and the generated tree.
  Edit shared wording here; edit data-driven sections there.
- Keep these headings. self_check_generated_repo.sh,
  check_github_publish_ready.sh and prepare_github_publish.sh require:
  ## Quick Start, ## Profiles and Parameters, ## Metrics, ## Output,
  ## Requirements, ## Troubleshooting.
- Do not hand-edit a generated README.md; regenerate it from here.
====================================================================
-->

[[GENERATE: readme.title]]

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![CI](https://github.com/{{CI Owner}}/{{CI GitHub Slug}}/actions/workflows/ci.yml/badge.svg)](https://github.com/{{CI Owner}}/{{CI GitHub Slug}}/actions/workflows/ci.yml)

[[GENERATE: readme.intro]]

## Quick Start

On an {{OS Version}} host, as root or with sudo:

```bash
git clone https://github.com/{{CI Owner}}/{{CI GitHub Slug}}.git
cd {{CI GitHub Slug}}
sudo bash setup.sh --assume-yes
bash run_benchmark.sh --smoke
```

`run_benchmark.sh` runs setup by itself if it has not been run yet. Each run prints its metrics when it finishes.

[[GENERATE: readme.quickstart_notes]]

## Profiles and Parameters

[[GENERATE: readme.parameters]]

## Metrics

[[GENERATE: readme.metrics]]

### Notes

[[GENERATE: readme.notes]]

## Output

| Path | Contents |
|---|---|
| `results/raw/<timestamp>_<repo>_<host>/` | Raw tool output, `metrics_summary.txt`, and `hardware_info.txt`, `software_info.txt`, `errors_info.txt` |
| `results/benchmark.db` | SQLite history of every run |
| `results/summary.json` | Metrics from the most recent run |
| `/var/opt/benchmarks/runtime_ledger.csv` | One row per run, shared by every workload on the host |

Every run is checked for completeness and against any `thresholds:` or `baselines:` in `config/benchmark_config.yaml`. A run that fails the checks exits non-zero.

## Requirements

[[GENERATE: readme.requirements]]

## Run the Whole Bundle

This workload is also part of [`{{CI Bundle Repo}}`](https://github.com/{{CI Owner}}/{{CI Bundle Repo}}), which holds all 32 {{GPU Vendor}} {{CI OS Display}} workloads as submodules:

```bash
git clone --recurse-submodules https://github.com/{{CI Owner}}/{{CI Bundle Repo}} {{CI Install Root}}
cd {{CI Install Root}}
./run_benchmark_suite.sh -w {{Workload Number}} --smoke     # just this workload
./run_benchmark_suite.sh --smoke            # all 32 workloads
./show_metrics.sh {{Workload Number}}                       # this workload's runs from the ledger
```

The suite tools (`run_benchmark_suite.sh`, `get_benchmark_results.sh`, `show_ledger_runs.sh`, `show_metrics.sh`) are documented in [`{{CI Suite Tools Repo}}`](https://github.com/{{CI Owner}}/{{CI Suite Tools Repo}}).

[[GENERATE: readme.other_bundles]]

## Troubleshooting

[[GENERATE: readme.troubleshooting]]

## Repository Layout

[[GENERATE: readme.layout]]

## Continuous Integration

- [CI](.github/workflows/ci.yml) runs lint and static checks on every pull request and push to `main`. It does not run the benchmark.
- [GPU Smoke Benchmark](.github/workflows/gpu-smoke.yml) runs a profile on a self-hosted runner labeled `gpu`, `{{CI Vendor}}`, `{{CI OS Label}}`. It only starts by hand (**Actions → GPU Smoke Benchmark → Run workflow**), so pull requests and forks cannot run it.

Both workflows call shared steps in [`{{CI Shared Workflows Repo}}@{{CI Shared Workflows Ref}}`](https://github.com/{{CI Owner}}/{{CI Shared Workflows Repo}}).
