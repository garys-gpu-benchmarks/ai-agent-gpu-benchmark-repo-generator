# Publishing this workload repository to GitHub

This generated workload is designed to be published as its own independent GitHub repository.

GitHub repository name = local folder = `<Workload Number>-<Repo Base Name>` from `benchmark_specification.json` (for example `128-gpu-bench-amd-vllm-throughput-latency`). Keep that same leading workload number on GitHub. Do not publish the unprefixed `Repo Base Name` slug.

## Pre-publish check

Copy the generated workload to a publish tree (do not destroy the only generation copy), then run from that copy:

```bash
bash scripts/prepare_github_publish.sh --dry-run
bash scripts/prepare_github_publish.sh --apply --in-place --github-owner=YOUR_GITHUB_USER
bash scripts/check_github_publish_ready.sh --published
```

`prepare_github_publish.sh` removes generator leftovers (nested copies, template-only docs, generation-only scripts and schemas), converts CRLF to LF, replaces `<org>` clone URLs, and removes superseded workflow files. It does not commit or push.

A finished workload normally no longer contains the nested `*_copy` generation workspace (it is removed once the workload passes). `--apply` refuses to run whenever a nested `*_copy` generation workspace (for example `ai-agent-gpu-benchmark-repo-generator_copy` or `TEMPLATE_00_*_copy`) is present in the current directory — copying the workload elsewhere does **not** remove it, since a plain `cp -a` copies that nested folder too. Pass `--in-place` so `--apply` can delete it. This is safe once you are standing in the publish-tree copy (that is the point of copying first); do not pass `--in-place` while standing in your only generation copy, since it permanently deletes that nested workspace there.

The `--published` readiness check verifies leftover files are gone, README relative links resolve, ignore rules are present, and host-safe syntax checks pass.

## Initialize and publish

Create the remote repository on GitHub using `<Workload Number>-<Repo Base Name>` (same as this folder), then run locally:

```bash
git init
git branch -M main
git add .
git status
git commit -m "Initial benchmark workload"
git remote add origin https://github.com/<OWNER>/<Workload Number>-<Repo Base Name>.git
git push -u origin main
```

Example: `gh repo create 128-gpu-bench-amd-vllm-throughput-latency --public --source=. --remote=origin --push`

Suggested GitHub description: `Workload <number>: <Repo Base Name>`. Add topics such as `amd`, `rocm`, `benchmark`, and the workload family (`perf`, `hipmemcpy`, `babelstream`, and so on).

Before committing, review `git status` carefully. The nested `TEMPLATE_*_copy/` generation workspace, runtime results, virtual environments, downloaded weights, logs, and credentials are intentionally excluded by `.gitignore` and must not be published.

## GitHub Actions

Both workflow files are short callers stamped by the generator. The steps live once, for the whole suite, in the `shared-workflows` repository, pinned at a major tag (`@v1`).

- `.github/workflows/ci.yml` runs on every pull request and push to `main`, on a GitHub-hosted runner: shellcheck, ruff, `bash -n`, `compileall`, `run_benchmark.sh --help`, specification schema, the results validator on a seeded fixture, required files, and actionlint. It never installs GPU software or runs the benchmark.
- `.github/workflows/gpu-smoke.yml` runs only when started by hand (**Actions → GPU Smoke Benchmark → Run workflow**). It targets a self-hosted runner labeled `gpu`, the vendor (`amd` / `nvidia`) and the OS (`ubu2404` / `ubu2604`), verifies the pre-provisioned GPU stack, records `results/environment.json`, runs the chosen profile, and uploads the results. It is never triggered by pull requests, so code from a fork cannot reach the GPU host.

Do not edit these two files by hand; change `config/ci_contract.yaml` or the templates in the generator and regenerate.

## Required legal files

Keep the root `LICENSE` and `legal/NOTICE` with the repository.
