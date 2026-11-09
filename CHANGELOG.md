# Changelog

## 2026-11-09 — TEMPLATE_00_129: x20 named dense LU; AMD memcpy publishes three directions; fio qd8 case and disk guard; SGLang x31 labels and warm-up; vLLM extended max_num_seqs

From the review of the TEMPLATE_00_128 overnight runs (Project460–463, `run_benchmark_suite.sh --smoke --baseline --extended -r 3`).

- **x20 is named for what it runs (120/220/320/420).** Workload Name `rocSOLVER FP64 Dense LU Solve (single GPU)` / `cuSOLVER FP64 Dense LU Solve (single GPU)` (was `rocHPL FP64 (High Performance Linpack)` / `NVIDIA HPL FP64 (High Performance Linpack)`), short names `rocSOLVER LU` / `cuSOLVER LU`, Main Goal and runtime-language text, on every workbook sheet; `linpack-rochpl-amd` and `linpack-hpl-nvidia` selectors match the new names. Not changed: metric keys and labels (they already said rocSOLVER/cuSOLVER LU), `bin/rochpl` and `bin/nvhpl`, repository names, `mpirun -np 1` on AMD (a timing change, left for a separate before/after run), and the percent-of-peak denominators (MI300X FP64 matrix peak; H100 FP64 tensor-core peak, since the vector peak read 101–102%).
- **114/314 publish H2D, D2H and D2D like 214/414.** Metrics are bandwidth at each direction's largest transfer size (`bandwidth_h2d_gbps`, `bandwidth_d2h_gbps`, `bandwidth_d2d_gbps`) and latency at its smallest (`latency_h2d_us`, `latency_d2h_us`, `latency_d2d_us`), the keys the AMD parser already wrote. The three numbered metrics had been H2D only, so a run that measured D2D at about 1,990 GB/s published 55 GB/s. D2D stays at the largest size, not its about 3.4 TB/s peak at 16 MiB (cache-assisted). `hipmemcpy-bandwidth-amd` `parse_results.py`: `headline_point` is `at <N> MiB` (it now tags the D2H and D2D lines too); `bandwidth_gbps`, `latency_us` and `headline_transfer_bytes` stay in `summary.json`. The pinned-over-pageable ratio (214/414 #7) is not added: it needs a second pass. **Ledger note:** 114/314 #1 is still H2D bandwidth at the largest size; #2 and #3 change meaning and #4–#6 are new.
- **fio x06 (106/206/306/406).** New metric #4 `iops_mean__randread_4k_qd8` (4k random read, iodepth 8 x 4 jobs = 32 in flight), the harness's existing per-case key; that job runs on smoke, baseline and extended, so it compares across profiles. #1–#3 stay the first case (qd1) so older rows keep their meaning. On the overnight runs #1 was 50,405 IOPS and #4 146,968 (106 smoke), 46,300 and 383,932 (406 extended). Both collectors write `fio_target.txt` and print `[INFO] fio target:` (path, filesystem source, type, mount point, disk, model, rotational, size from sysfs, which also works in a container). A `/dev/` target is refused when it or a partition on it is mounted (checked with lsblk and the mount table), and a write sweep on an unmounted raw device needs `FIO_ALLOW_DEVICE_WRITE=1`; a file target (the default `data/fio_target.bin`) is never refused. `print_metric_summary.py` does not add the `first_case` tag to a per-case key (`<metric>__<case>`).
- **SGLang x31 (131/231/331/431).** Metrics #1/#2 read "client-observed from send" (was "includes queue wait"): concurrency equals `max_running_requests`, TTFT stays in the tens of ms, and E2E equals output length x TPOT. The runner prints a `[WARN]` when `max_concurrency` exceeds `max_running_requests`, the case where requests do queue. `bench_serving.py` (identical AMD/NVIDIA) repeats the existing untimed warm-up round until its slowest TTFT is at or under `SGLANG_WARMUP_SETTLE_TTFT_MS` (default 1000), at most `SGLANG_WARMUP_MAX_ROUNDS` (default 4), each round with new negative seeds. A warm server settles in round 1. On a fresh 231 the single round took 66.5 s and the timed TTFT p50 was still 4,921 ms (53 ms on the next smoke). The x30 warm-up is unchanged.
- **vLLM x28/x29 extended `max_num_seqs` 16 -> 8 (128/129/228/229/328/329/428/429).** `max_concurrency` is 8 on every profile, so slots 9–16 never filled. Commands re-synced.
- **Not changed:** the profiles' problem shapes. Baseline and extended scale the job on purpose (x26 BF16 -> FP32; x07 and x15 array size; x28–x31 token lengths), and the resolved command with every shape parameter is already in each run's `metrics_summary.txt` header and in the ledger's `run_benchmark_command_fully_resolved` and `Parameter_NN` columns. STREAM's thread count is not capped either: a cap tuned to the 20-vCPU VM would understate a bare-metal server.
- **Checks:** new `tests/test_template_00_129_changes.py` (12 tests: names and selectors, memcpy metrics and parser, x31 labels, max_num_seqs parity, fio qd8 availability on every profile, the target guard on AMD and NVIDIA, the per-case tag, warm-up rounds against the stub server); all 45 test files pass; `sync_matrix_profile_commands.py --check`, `generate_workload_parameters.py --check`, `generate_show_metrics.py --check` and `verify_generation_workflow.py` pass (the 215 parameter-description warnings are unchanged). ruff was not available on the editing machine; run the CI ruff step before publishing. Workbook edited with openpyxl: four sheets, frozen top rows, column widths and data validation unchanged; `Metric_Short_Labels` gains ten rows (filter range updated). Originals of every changed file are in `../_backup_20261109_claude_129/`.

## 2026-11-08 — TEMPLATE_00_128: `list_runs.sh` in every workload; `run_benchmark.sh --help` starts with "Usage:"

- **`list_runs.sh` at the top of every workload.** `create_generated_repo.py` `WORKLOAD_TOOLS` now installs `user_scripts/list_runs.sh` next to `show_metrics.sh` and `run_benchmark.sh`, so a single cloned workload can print the ledger's run table (`bash list_runs.sh`). It is the same master copy that goes to the project folder, `/opt/benchmarks`, the bundles and `gpu-bench-suite`. `publish_benchmarks_to_github.sh` refreshes both tools in every workload of the publish tree (workloads generated before TEMPLATE_00_128 get `list_runs.sh` there). `readme_sections.py` lists it in the workload README layout; `check_github_publish_ready.sh` requires it and checks it with `bash -n`. The generator README no longer says the user scripts are never copied into a workload. New test `test_workload_gets_show_metrics_and_list_runs` in `tests/test_operator_tools.py`.
- **No blank line before "Usage:" in `run_benchmark.sh --help`.** The help page opened with an empty line (added on purpose earlier); GNU tools, argparse and git print the usage line first. `workload_option_help.replace_help_header` now removes blank lines between `cat <<'USAGE'` and `Usage:` in template and overlay runners instead of adding one, and the generated harness in `materialize_generated_harness.py` no longer has the blank line. `docs/run-output-contract.md` shows the new first line, and its "each value ends with a period" text now matches the code (no trailing period). `tests/test_workload_option_help.py` expects the new shape and adds `test_help_page_has_no_leading_blank_line` (zero, one, two and whitespace-only blank lines). The other help pages already started with "Usage:": `setup.sh` in all 32 workloads, `show_metrics.sh`, `list_runs.sh`, `get_benchmark_results.sh`, `run_benchmark_suite.sh`, `publish_benchmarks_to_github.sh`, `check_github_publish_ready.sh` and `prepare_github_publish.sh`.
- **README quickstart matches how generation runs.** "Generate Your First Benchmark Repository" now uses a two-level workspace (`~/gpu-bench/workspace`; the operator tools land in `~/gpu-bench/`), says to open the folder that contains the generator in the agent, adds an SSH login check, `-p <port>` and Git Bash, names the real flow (`generation_host_preflight.py`, `run_from_prompt.py`, `create_one_workload.py`; it named `create_generated_repo.py --workload`), gives run times, and says that with a server in the prompt every workload is already installed in `/opt/benchmarks`. The generated-tree example shows the real repository name and `show_metrics.sh`/`list_runs.sh`. Requirements and "Limitations and prerequisites" list all four platforms and the NVIDIA GPU (they listed 101–232/301–332 and only the MI300X). Dropped a stale `TEMPLATE_00_72` note.

## 2026-11-08 — TEMPLATE_00_127: SGLang x30/x31 start on a fresh VM; AITER wheel only; smaller smoke server

On four freshly installed VMs (TEMPLATE_00_126 repos copied to `/opt/benchmarks`, x30 run first), 130, 230 and 430 smoke finished setup and the model download, then `sglang.launch_server` exited: `Should have a model_type key in its config.json`. 330 never left setup: `import aiter` spun for 49 minutes. Earlier runs hid both because the vLLM workloads had already downloaded `config.json` and an earlier workload had already done the AMD reboot.

- **`config.json` in the SGLang snapshot (130/131, 230/231, 330/331, 430/431).** `scripts/prefetch_sglang_model.py` (identical in the four SGLang components) downloads `config.json` by name and `generation_config.json` when the repo has one, refuses to print the snapshot unless `config.json` has a `model_type` key, and loads `AutoConfig` and `AutoTokenizer` from the snapshot offline before printing it. It does not sweep every `*.json` in the repo.
- **AMD AITER from the pinned wheel only (130/131/330/331, `scripts/templates/setup_rocm_reboot_skeleton.sh`).** On a fresh 26.04 MI300X VM the amdgpu reboot is postponed to the end of setup. The AITER step ran `import aiter` before that reboot, discarded the error, then cloned unpinned `ROCm/aiter` HEAD and ran `setup.py develop`, which also replaced torch's ROCm 10.1 Triton with a ROCm 7.2 build; the next import spun. Setup now decides from the installed `amd-aiter` version (not an import), installs `amd-aiter==${AITER_VERSION}` when missing or different, skips the import while `GPU_CHECKS_AFTER_REBOOT=1` (the run after the reboot checks it), and otherwise runs `import aiter, torch` under `timeout` (`AITER_IMPORT_TIMEOUT_SEC`, default 300 s) with its output in `results/aiter_import.log`. A failure or timeout stops setup. The source fallback, `AITER_SOURCE_DIR` and `AITER_REPO_URL` are removed. The vLLM AITER block (non-fatal) is unchanged. The AMD SGLang `ensure_setup.sh` import checks run under `timeout` (`SETUP_CHECK_TIMEOUT_SEC`, default 300 s).
- **Smaller smoke server.** Workbook `Parameters_SmokeBaselineExtend`: smoke `max_total_tokens` is 1024 (was 16384) for the eight SGLang workloads; baseline 16384 and extended 32768 are unchanged; command columns re-synced (8 cells). Two smoke prompts of 64+16 tokens need 160. NVIDIA smoke adds `--disable-cuda-graph` to the same `launch_server` command; baseline and extended still capture CUDA graphs, and FlashInfer stays on. AMD already passed it on every profile. No extra warm-up request.
- **SGLang download outside the published time.** The four SGLang runners call `mark_benchmark_measure_start` after the prefetch returns and before `launch_server`, as the vLLM runners do. Server start and the requests stay on the clock; wall time is unchanged.
- **NVIDIA 26.04 runtime deps keep torch (430/431).** `install_sglang_nvidia.sh` starts from the Project453 copy that got 431 through setup (NCCL restored before the first torch import; torch reinstalled only when it moved). `install_sglang_runtime_deps` pins the installed torch, torchvision, torchaudio, triton and `nvidia-nccl-cu13` with a pip constraints file, and installs `timm`, `torchao`, `cuda-python==12.9` and `cuda-bindings~=12.9.0` with `--no-deps` (the 12.9 bindings are what the passing 431 venv had). On 431 that unconstrained install had swapped torch 2.13.0+cu130 for torch 2.10 (915 MB) and back (526 MB). If the constrained install fails it retries unpinned and the existing checks restore torch. The 24.04 path (230/231) is unchanged. Both NVIDIA copies stay byte-identical.
- **Checks.** `self_check_generated_repo.sh` now requires the pinned wheel and `AITER_IMPORT_TIMEOUT_SEC`, and fails a setup that still builds AITER from source (it used to require `github.com/ROCm/aiter.git`). `tests/test_sglang_smoke_real_server.py` allows one smoke branch, NVIDIA's `--disable-cuda-graph`. New `tests/test_template_00_127_sglang.py` (16 tests): prefetch refuses a missing config or `model_type` and fetches config into the 2026-11-08 snapshot; the AITER block installs without importing before the reboot, replaces a different version, and stops on an import failure or hang (run under bash with a fake Python); clock restart order; workbook smoke values; NVIDIA constraints and `--no-deps`.
- **Docs.** `AGENTS.md`, `docs/rocm-pytorch-install-contract.md`, `docs/host-prerequisite-contract.md`, `docs/nvidia-sglang-install-contract.md`.
- **Not changed:** baseline and extended commands, prompts and metrics; per-repo venvs; the AMD SGLang source build (ROCm 10.1 has no SGLang wheel); the AMD reboot itself; x09/x10 smoke sizes; the BLIS download retry (separate change).
- Originals of every changed file are in `../_backup_20261108_sglang_127/`.

## 2026-11-08 — SGLang tokenizer prefetch, x10 DRAM tier, vLLM download outside the timed run

Overnight GitHub-clone runs of 101–132, 201–232, 301–332 and 401–432 (`run_benchmark_suite.sh --smoke --baseline --extended --repeat 3`, TEMPLATE_00_125).

- **SGLang first smoke (130/131, 230/231, 330/331, 430/431).** All eight failures were the first smoke: `sglang.launch_server` exited before ready with transformers' generic "You need to have sentencepiece or tiktoken installed". The runner passes the prefetched snapshot directory to `--model-path`, and that snapshot held the weights and only `tokenizer.model.v3`. `tokenizer.json`, `tokenizer.model`, `tokenizer_config.json` and `special_tokens_map.json` appeared 1–2 minutes after the second smoke died on every host, downloaded by the x32 RAG setup; that is why baseline and extended passed. `sentencepiece` was already installed. `scripts/prefetch_sglang_model.py` (all four SGLang components, identical bytes) now downloads those four files into the shard snapshot, refuses to print the path unless `tokenizer_config.json` and `tokenizer.json` or `tokenizer.model` are non-empty, and loads `AutoTokenizer.from_pretrained(snapshot, local_files_only=True)` first (`--skip-tokenizer-load` skips only the load). `tokenizer.model.v3` does not count. The four runners' failure message now names the tokenizer.
- **x10 NUMA cache sweep (110/210/310/410, `numa-cache-collector`).** The DRAM tier is at least 1 GiB and at least 4x the detected LLC (was 256 MB and 2x). The MI300X VMs hide L3 from sysfs and `lscpu`, so the detected LLC was 0 and the 256 MB buffer sat mostly in the Xeon 8568Y+ 300 MB L3: 110/310 reported 72–97 ns "DRAM" while 109/309 (1 GiB) measured ~120 ns. When `numactl` is refused, the collector now tries `taskset -c <source node cpulist>` before an unpinned launch; on the 2-socket 401 container the unpinned run let threads float between sockets (410 DRAM 134 ns baseline, 162 ns extended). The remote target runs only at the DRAM size, and only when a second node exists and `--membind` worked; the other remote runs fed no metric. This roughly halves the run on one-node hosts, which pays for the larger buffer.
- **vLLM model download outside the published time (127–129, 227–229, 327–329, 427–429).** The first vLLM smoke on each fresh VM spent 111 s of 3:26 downloading weights; the cached smoke takes about 30 s, so the smoke itself was already short. New `prefetch_vllm_model_weights` in `scripts/lib/common.sh` downloads the files vLLM loads (`consolidated*.safetensors`, `*.json`, `tokenizer.model*` for a Mistral-format repo, otherwise the Hugging Face weights). The six vLLM runners call it after the model name is resolved and then call `mark_benchmark_measure_start` again, so the ledger times the benchmark, not the download. Best effort: a failure prints `[WARN]` and vLLM downloads as before. `VLLM_SKIP_PREFETCH=1` skips it. The host bootstrap prefetch only runs during generation, so a GitHub clone never had it.
- **Not changed:** smoke/baseline/extended parameters, metric names, the `na` strings, and the SGLang/RAG model download (two Mistral formats stay on disk).
- Originals of every changed file are in `../_backup_20261108_fix_1_4_7/`. Full suite: 459 tests pass.

## 2026-11-07 — gpu-bench-suite tools at the top of the repository

- `gpu-bench-suite` now has `run_benchmark_suite.sh`, `get_benchmark_results.sh`, `list_runs.sh`, and `show_metrics.sh` at its top level instead of in `scripts/`, the same place the four bundle repositories put them. Commands become `./list_runs.sh --host <address>` instead of `./scripts/list_runs.sh --host <address>`.
- `scripts/emit_shared_workflows.py` writes the tools to the top of the suite folder. `user_scripts/publish_benchmarks_to_github.sh` checks and reads them there, and before committing removes any old `scripts/` copies (the emit step leaves files it no longer writes), so the next publish records the move as four renames.
- `templates/suite-tools/README.md` links and commands use the new paths and start the laptop section with the `git clone`. The bundle README, `docs/github-profile-README.md`, both getting-started guides, and `README.md` use the new paths. `scripts/verify_generation_workflow.py` accepts the suite README's top-level tool links.
- `tests/test_ci_contract.py` expects the tools at the top and no `scripts/` folder; `tests/test_bundle_readme_tools.py` expects `./get_benchmark_results.sh --host` and no `./scripts/` in the bundle README.
- Links to `gpu-bench-suite/.../scripts/<tool>.sh` from v1.0.30 and earlier stop resolving after the next publish.

## 2026-11-07 — Hugging Face token is a fallback, not a requirement

- On 2026-11-07, three hosts with no Hugging Face token (two new AMD Developer Cloud servers and one Runpod Pod) downloaded `mistralai/Mistral-7B-v0.3` in the bootstrap prefetch, and all 128 workloads passed. The download passes no token.
- `scripts/remote_host_preflight.py`: the no-token warning now reads "mistralai/Mistral-7B-v0.3 may be gated; if its download fails, set HF_TOKEN" (was "is gated").
- `scripts/readme_sections.py`: the vLLM/SGLang README note no longer says to set `HF_TOKEN` before setup; it says the model may be gated and to set `HF_TOKEN` if its download is refused. The Troubleshooting entry for a 401/403 says "may be gated" and keeps the `export HF_TOKEN` / `sudo -E bash setup.sh --assume-yes` fix.

## 2026-11-07 — `--help` header values have no trailing period

- `run_benchmark.sh --help` prints Workload Name, Main Goal, and Command Tools Executed without a period at the end. `help_header_lines` (`scripts/workload_option_help.py`) used to add one to any value that lacked it; it now drops a trailing period instead.
- `BenchmarkSpecDefinitions.xlsx`, Workload_Definitions, Command Tools Executed: the trailing period is removed from all 128 cells. The four SDXL rows (124/224/324/424) were two sentences and are now one: "Run scripts/infer_sdxl.py --backend sdxl with real SDXL in every profile; smoke uses reduced resolution and steps" (`collect_sdxl.py` on 224/424). The 28 cells that join two clauses with a semicolon stay one sentence.
- `tests/test_workload_option_help.py` expects no period, and checks that a period in the cell is dropped.

## 2026-11-07 — 102/202/302/402 health checks take three parameters

These four workloads used to take one reading with no parameters, so smoke, baseline, and extended did the same thing and nothing was checked against an expected value. They now take:

| Parameter | smoke / baseline / extended | Effect |
|---|---|---|
| `monitor_duration_sec` | 5 / 200 / 580 | Sample once per second for this long (never fewer than two samples). `gpu_temperature_c` is the peak over the window. |
| `expected_gpu_count` | 1 / 1 / 1 | Fewest GPUs (HSA agents on AMD, CUDA devices on NVIDIA) that must stay visible. Fewer fails the run; more is allowed. |
| `min_pcie_link_width` | 16 / 16 / 16 | Narrowest acceptable PCIe link on every GPU. A narrower (downtrained) link fails the run. A width that cannot be read is skipped and noted in `error_message`, not failed. |

- Workbook: Parameter_01–03 and the Parameters_SmokeBaselineExtend rows for the four workloads; Validation Objective, Command Execution Details, Command Methodology, Execution Description With Parameters, Raw Output Format/Example, Record Granularity, Output Fields, Success Criteria, Parser Notes, and Known Runtime Constraints rewritten to match; command columns regenerated with `scripts/sync_matrix_profile_commands.py`. Baseline 200 s and extended 580 s match the 3–5 and 8–15 minute profile targets (same as 103).
- `implementation_components/rocm-health-amd` and `gpu-health-nvidia` collectors: one-second sampling loop; window results (peak temperature, narrowest/slowest link, fewest GPUs) repeated on every row so the harness mean equals them; per-sample readings in new `sample_*` columns; `window_new_dmesg_fault_count` / `window_new_xid_count` for faults logged during the run. The five metric keys and their meanings are unchanged except that temperature is now the window peak. The fault counts still cover dmesg since boot.
- AMD reads every AMD GPU's sysfs link (vendor 0x1002, `cardN` only) instead of the first `card*` entry, so a VM's virtual VGA or a connector entry is no longer read as the GPU link, and multi-GPU hosts report the narrowest link. The hottest GPU's temperature is reported.
- NVIDIA reads every GPU line of `nvidia-smi --query-gpu` and keeps only the first and last `nvidia-smi -q` (`health_first.txt`, `health_last.txt`) instead of one per sample.
- Both collectors accept `--monitor-duration-sec`, `--expected-gpu-count`, and `--min-pcie-link-width`, so `run_benchmark.sh` overrides reach them (it forwards a flag only when the collector's `--help` names it).
- `scripts/generate_workload_parameters.py` CATALOG_METADATA and `config/workload_parameters.yaml` describe the three parameters.
- New `tests/test_health_monitor_params.py` (18 tests).

## 2026-11-07 — NVIDIA rows no longer name a GPU model; Runpod guide passes the publish scan

- `BenchmarkSpecDefinitions.xlsx`, Workload_Definitions, NVIDIA rows 201–232 and 401–432: **GPU Model** is now blank (was `H100 SXM 80GB`). The NVIDIA GPU varies by provider, and the 2026-11-07 runs were on an H100 NVL, so every ledger row carried "detected GPU … differs from spreadsheet GPU Model H100 SXM 80GB" and every README said "validated on H100 SXM 80GB". With the cell blank, `gpu_model_note` writes no note and the README requirement reads "NVIDIA GPU with CUDA <version>". The GPU that ran is still recorded per run in `gpu_name`, `gpu_vram` and `gpu_count`.
- Same rows, **Hardware Config** is now "Cloud GPU host such as a RunPod Pod (20+ vCPUs, 128+ GB RAM, local NVMe), 1x NVIDIA data-center GPU (80+ GB HBM; model varies by provider)" (was an H100 SXM host and GPU).
- AMD rows keep `MI300X`: the ROCm packages, rocBLAS clients, FAISS and SGLang/AITER builds all target gfx942, so that model is a real requirement.
- `docs/runpod-getting-started.md`: Git Bash paths are now `~/.ssh/…` instead of the Windows home-folder form. That placeholder matched the Windows-home pattern in `prepare_github_publish.sh`'s secrets scan and failed the dry run for all 128 workloads.

## 2026-11-07 — `--help` parameter lines wrap at 100 columns

- `run_benchmark.sh --help` no longer prints parameter lines hundreds of characters long (411 `--workload-commands` and `--event-list`, 409/410 `--working-set-size`, 405 `--shape`, `--rtol`, `--atol`). An entry that fits in 100 columns keeps the one-line form. A wider one prints the description on the flag's line, then one indented line per group of profiles that share a value (`smoke:`, `baseline/extended:`, `all profiles:`), wrapped after commas or semicolons where possible so each list item starts its own line, and at spaces inside a long item.
- A flag too long for the 30-column flag field (`--omit-initial-seconds <value>`, `--warmup-duration-sec <value>`) puts its description on the next line, aligned, instead of pushing it out of the column.
- All 2,014 parameter help lines across the 128 workloads are now at most 100 columns. `scripts/workload_option_help.py`; tests in `tests/test_workload_option_help.py`; `docs/run-output-contract.md` rule 7 and AGENTS.md updated.
- Still open: 95 of the 133 shared parameters have only the placeholder description "Shared workload parameter." (no entry in `CATALOG_METADATA`, `scripts/generate_workload_parameters.py`).

## 2026-11-07 — Runpod Getting Started guide

- New `docs/runpod-getting-started.md`, built on the AMD Developer Cloud guide's layout, for NVIDIA workloads 201–232 and 401–432: account and funds (prepaid; a $0 balance stops Pods and deletes the data of Pods without a network volume), MFA, an SSH key (passphrase plus agent; a separate no-passphrase key only for remote validation from a PC), adding the public key, a bare `ubuntu:24.04` / `ubuntu:26.04` template with a 500 GB container disk, TCP port 22 and Runpod's documented SSH start command, deploying a 1-GPU Pod, "SSH over exposed TCP", installing the NVIDIA bundle, `scp` and remote-command examples from Git Bash, Docker Hub pull limits (registry credential), and teardown (copy results with `get_benchmark_results.sh --port`, then terminate; stopping wipes the container disk).
- It lists what a Pod, being a container, cannot measure: `dmesg` (x02), the NVMe drives (x06), NUMA policy (x09, x10), CPU performance counters (x11), and a second GPU (x16).
- `README.md` links both guides; the AMD guide links the Runpod guide. Like the AMD guide, it is stripped from the published workload repositories (`prepare_github_publish.sh`).

## 2026-11-07 — AMD Developer Cloud guide refreshed

- `docs/amd-developer-cloud-getting-started.md` is now "AMD Developer Cloud — Getting Started" and covers the whole path from account to teardown.
- Corrected: GPU droplets bill per second with a 5-minute minimum (not hourly), and a powered-off droplet is billed in full until destroyed. Credits come from the AMD AI Developer Program or the request banner on the Create GPU Droplet page, take up to three business days, and expire; running out can remove the droplet and its data.
- The no-passphrase key is now a separate key pair, used only for remote validation from a PC. The old steps stripped the passphrase from a copy of the main key, which left the main key unencrypted on disk. Lab technicians who run on the droplet don't need it.
- Added: the Ubuntu 26.04 image for 301–332; the single-MI300X droplet's size; a GPU check that lists only AMD devices (`lspci -d 1002:`); `amd-smi`; macOS/Linux paths; a section that installs the suite (the bundle clone replaces the old `<script-name>` placeholder); and a teardown checklist that copies results off first.

## 2026-11-07 — SGLang smoke starts the real server (no stub)

- **x30 and x31 (130, 131, 230, 231, 330, 331, 430, 431):** smoke now starts `python -m sglang.launch_server` with Mistral-7B-v0.3, the same as baseline and extended, instead of `scripts/tiny_sglang_server.py`. A smoke pass now shows that SGLang installs, starts and answers on the machine; before, every smoke metric was `na (stub server, smoke only)` and a broken SGLang only showed up at baseline (as on 330/331 in 00_70). Smoke still sends the smallest requests (2 prompts, 64-token input, 16-token output).
- **Runners:** the four `sglang-*` `run_benchmark.sh` overlays have one launch path for every profile, with the model prefetch, AITER checks (AMD) and FlashInfer setup (NVIDIA) on smoke too. The two AMD `ensure_setup.sh` scripts no longer skip the SGLang install checks on smoke.
- **Workbook:** the 48 text cells for those 8 workloads that described the stub now say every profile starts the real server. Smoke `max_total_tokens` is 16384 (was 2048), the KV-token budget baseline already starts with; smoke request sizes are unchanged. Command columns re-synced.
- **Smoke time:** expect about 2 to 2.5 minutes per SGLang workload, mostly server start-up (CUDA-graph capture), and longer on a fresh install because the first smoke downloads the Mistral weights. The smoke target is now under 1 minute after setup, except workloads that start a model server on every run (vLLM x27 to x29, SGLang x30 and x31, SDXL x24), which may take up to about 6 minutes (AGENTS.md section 20.2, profile README).
- **Follow-up (same day):** the workbook Parser and Normalization Notes for 130/230/330/430 no longer say a missing cache count means the "smoke server"; 230/231/430/431 Known Runtime Constraints give the ready-wait the runners actually use (up to 1800 s). The bundle README's results note for x30/x31 no longer says smoke uses a stand-in server, and `tiny_sglang_server.py` describes itself as a local test server that no profile starts. AGENTS.md ready-wait rule updated.
- **AMD 130/330 ready-wait:** the runner's early `BENCHMARK_READY_WAIT_SEC` default is 1800 s (was 600 s, which also overrode the 1800 s default later in the script), so all eight SGLang workloads wait up to 1800 s for the server. A crashed server still fails at once.
- **104/304 Main Goal:** "…integrity via a PyTorch pattern verifier" (was "…with a PyTorch SDC stub"; the test is a real write/verify, not a placeholder).
- **Checks:** `self_check_generated_repo.sh` now fails an SGLang runner or AMD `ensure_setup.sh` that still uses the stub. `tiny_sglang_server.py` stays in the overlays only for the local client tests (`tests/test_sglang_stub_clients.py`), and the stand-in guard that keeps stub numbers out of the ledger is unchanged. New `tests/test_sglang_smoke_real_server.py`; AGENTS.md, SIBLING_WORKLOAD_NOTES, SUBMISSION_CHECKLIST, generation-workflow and nvidia-sglang-install-contract updated.

## 2026-11-07 — Organization diagram published to the profile repository

- New `docs/images/github-organization.png`: the garys-gpu-benchmarks organization diagram (4 bundles, 128 benchmark repositories, 3 suite repositories, lab technician and maintainer access).
- Publish step 10 copies it onto `garymichaelbass/garymichaelbass` as `images/github-organization.png`, next to `BenchmarkSpecDefinitions.xlsx`. Only those two files are staged; the profile README and sample folders are untouched. A publish with an unchanged diagram makes no commit for it; a changed diagram alone commits as "Update organization diagram". If the generator has no diagram, step 10 publishes the workbook only and prints a note.
- `docs/github-profile-README.md` shows the diagram under Benchmark Suites. Add the same image line (pointing at `images/github-organization.png`) to the profile README by hand once.
- `.gitattributes` marks `*.png` and `*.xlsx` binary. Tests: `tests/test_publish_profile_spec.py` covers the diagram (add, unchanged, diagram-only update, missing file).

## 2026-11-07 — `show_ledger_runs.sh` renamed `list_runs.sh`

- The suite tool that prints the runtime ledger's run table is now `user_scripts/list_runs.sh`. Each of the four tools in `/opt/benchmarks` now has its own first letter (`get_`, `list_`, `run_`, `show_`), so one letter and Tab completes the name, and `sho<Tab>` completes `show_metrics.sh`. Behaviour and options are unchanged; `--help` shows the new name.
- Renamed everywhere the tool is named: the generated workloads, the gpu-bench-suite repository (`scripts/list_runs.sh`), the bundle copies and README, `templates/suite-tools/README.md`, `templates/README_TEMPLATE.md`, `README.md`, CI, `ci_contract.py`, `create_generated_repo.py`, `create_one_workload.py`, `emit_shared_workflows.py`. Test file renamed `tests/test_list_runs.py`.
- The publish script removes the old `show_ledger_runs.sh` from the gpu-bench-suite folder and from each bundle, so a re-used publish folder does not publish both names.

## 2026-11-07 — Publish script passes shellcheck (SC2100)

- `user_scripts/publish_benchmarks_to_github.sh` quotes the bundle slugs in the bundle README links (`slug="bundle-amd-ubuntu-2404"`). Unquoted, shellcheck read the hyphens as subtraction (SC2100), and the generator's Template CI "Lint shell scripts" step failed after the v1.0.29 publish. Bash ran the old lines correctly; only the lint failed.
- New `tests/test_shellcheck_ci.py`: runs the CI shellcheck command on LF copies of the same files (skipped when shellcheck is not installed), and checks the publish script for unquoted hyphenated assignments without needing shellcheck.

## 2026-11-06 — `--help` header: blank first line, no Validation Objective

- `run_benchmark.sh --help` starts with a blank line before `Usage:`, and the header lists Workload Name, Main Goal, and Command Tools Executed (Validation Objective is no longer shown; `--specification` still prints it). `help_header_lines` and `replace_help_header` in `scripts/workload_option_help.py` apply this to the runner template and the 12 overlay runners. Docs (`run-output-contract.md`, help skeleton, checklist 3.29b) and `tests/test_workload_option_help.py` updated.
- TEMPLATE_00_124 workbook: Command Tools Executed now follows Main Goal, and Validation Objective follows the three run-command columns. Column order only; no values changed, and every script reads these columns by name.

## 2026-11-06 — NVIDIA SDXL and SGLang runners start with `RAW_FILE` unset

- `implementation_components/sdxl-diffusers-nvidia` and `sglang-prompt-response-nvidia` `run_benchmark.sh` test `"${RAW_FILE:-}"`. With `set -u`, the bare `"${RAW_FILE}"` stopped every smoke run of 224/424 and 230/430 before the run folder was created. This is the repair the 201-232 and 401-432 batches made in their generator copies (`results/generator_repairs.md`); the published workloads already carry it. New test: no runner reads an unset `RAW_FILE`.

## 2026-11-06 — Fixes from the 96-run VM review

- **Several profiles in one command.** `bash run_benchmark.sh --smoke --baseline --extended` used to run extended only (each profile flag replaced the last). `run_profiles_in_order` (new, `scripts/lib/common.sh`) now runs the script once per profile, in the order given, with the other options unchanged, keeps going after a failed profile, prints `[INFO] Profiles: smoke ok, baseline ok, extended ok`, and exits with the first non-zero status. Each profile is a normal run with its own `results/raw` folder and ledger row. Called right after `--help` handling in the runner template and the 12 overlay runners.
- **AMD banner.** `scripts/print_run_metadata.sh` read the pre-10.x `rocm-core` and `rocblas` packages, so ROCm 10.1 machines printed `NOT FOUND`. It now reads `/opt/rocm[/core-*]/.info/version`, then the `amdrocm-base*` packages, then the `/opt/rocm/core-<ver>` folder; rocBLAS comes from the `rocblas` package, then the `librocblas.so.<ver>` file, then the named `amdrocm-blas*` package (whose version is the ROCm release).
- **First venv message.** `setup_rocm_reboot_skeleton.sh` printed `[WARN] Existing Python venv is incomplete; recreating it` on every fresh install. With no `.venv` yet it now prints `[INFO] Creating Python venv`; the warning stays for a real broken venv.
- **JAX x26 iterations.** 126/326 baseline and extended asked for 2,630,000 and 7,180,000 iterations and stopped at the 120 s / 330 s limits after about 210,000 and 420,000. `Parameters_SmokeBaselineExtend` now asks for 190,000 and 390,000 (commands re-synced). `update_runtime_ledger.py` adds `completed N of M requested iterations (stopped at the profile time limit)` to `notes` whenever `raw_results.csv` shows fewer completed than requested iterations.
- **RAG x32 retrieval is labelled CPU.** Both RAG scripts build a CPU `faiss.IndexFlatIP` on every platform. Metric #3 is now "CPU FAISS retrieval latency, ms" (Metrics and `Metric_Short_Labels`, short label `CPURtms`), and the script prints `[INFO] FAISS retrieval runs on the CPU (IndexFlatIP)`.
- **vLLM AMD and amd-aiter (127–129, 327–329).** Setup installs the pinned `amd-aiter` with `--no-deps` after vLLM's extra dependencies (which skip it so pip cannot replace the ROCm torch). If it still does not import, setup logs a warning and an `install_status.txt` step, and each run prints `[WARN] amd-aiter is not installed; vLLM runs without its AITER kernels...`. Neither fails the run.
- **One GPU, x16 collectives.** With `num_gpus` 1, the RCCL and NCCL collectors run one smallest-message call (to show the library initializes) instead of the full size sweep, then publish the documented `na (requires at least two GPUs)` row. Previously 116 spent up to 2 min 19 s and 216 up to 49 s on that sweep.
- Tests: `tests/test_vm_review_20261106.py` (new); `tests/test_metric_fixes_20261019.py` NCCL one-GPU test now expects one call.

## 2026-11-06 — Parameter notes removed; sync script emits `--validate`

- **`BenchmarkSpecDefinitions.xlsx` `Parameters_SmokeBaselineExtend`:** column G `notes` is deleted (286 internal tuning notes). The sheet is now Workload Number, Workload Name, Parameter, smoke, baseline, extended.
- **Not published any more.** `extract_benchmark_definition.py` and `matrix_profile_values.py` no longer read a `notes` column or write a `notes` key into Profile Parameter Values, so `benchmark_specification.json` and `--specification` carry only the smoke, baseline, and extended values. Nothing else in any workload's specification changes; `config/workload_parameters.yaml` and `user_scripts/show_metrics.sh` regenerate unchanged.
- **`scripts/sync_matrix_profile_commands.py`** builds `bash run_benchmark.sh --<profile> --validate ...`, matching the workbook command columns. Before this, `--check` reported every workload as stale and a write would have removed `--validate` from all 384 commands; `--check` now passes for all 128 workloads.
- Removed `test_workbook_still_has_tagged_notes_so_the_strip_is_exercised` (it required the notes column). The TEMPLATE_00_ tag strip on smoke, baseline, and extended cells is unchanged and still tested.

## 2026-11-06 — Shorter bundle README

- **`bundle_readme()` in `user_scripts/publish_benchmarks_to_github.sh`** writes a README about half as long for all four bundles: Requirements, Install, Quick check, Run benchmarks, Results, Reading the results, Update, Benchmarks. Same commands and warnings; the three sample summary blocks, the quiet-mode install variant, the separate "Smoke is a wiring check" section, and the duplicate results table are gone (smoke is now two sentences under Quick check).
- **Corrections.** x20 is no longer called HPL (it is a cuSOLVER/rocSOLVER LU solve). x06 and x08 sit under "Reading the results" with the `na` notes instead of a table titled "expected to be na". The pre-v1.0.5 migration note is gone. Each bundle links to the other three bundles, not to itself.
- **AMD.** The ROCm restart instructions (24.04 may restart, 26.04 restarts once, with the expected last lines) stay under Quick check. NVIDIA says the first run installs CUDA and never installs the driver or restarts.
- **Benchmarks list** is a table of workload numbers with short repository names (for example 207 links as `stream-ddr5-bandwidth`).
- `tests/test_bundle_readme_tools.py` checks the new section order, quick check, restart text per platform, other-bundle links, and short names.

## 2026-11-06 — `[RUN]` lines appear only at `--log-level DEBUG`

- **Quieter default output.** `[RUN] <command>` lines no longer print on the terminal at the default `--log-level INFO`. `--log-level DEBUG` prints them again. Section headers, collector CSV rows, `[PASS]`/`[WARN]`/`[FAIL]` lines, and the end-of-run summary and metrics are unchanged.
- **Nothing is lost.** `log_run` (new, `scripts/lib/common.sh`) always appends the `[RUN]` line to `run.log` in the run directory, which the runner-level lines never reached before; `commands_executed.sh` is unchanged. `hide_run_lines` (new) filters `[RUN]` lines from collector output on the terminal while `tee` still writes them to `run.log`, so `update_runtime_ledger.py` still finds the last command for `failure_detail`. `run_cmd` and `run_logged` use `log_run`.
- **Where.** The runner template in `scripts/materialize_generated_harness.py` and the 12 overlay runners (SDXL, SGLang, vLLM; AMD and NVIDIA) call `log_run` instead of `echo "[RUN] ..."` and pipe collector output through `hide_run_lines`. A failing collector still fails the run.
- **Help and docs.** `--help` reads `--log-level <level> ERROR|WARN|INFO|DEBUG (default: INFO; DEBUG also prints [RUN] commands)`. Updated `docs/run-output-contract.md`, `AGENTS.md`, checklist 3.30, and the help skeleton. New `tests/test_run_line_log_level.py`.
- **Not covered.** Setup-time scripts (`setup.sh`, `ensure_setup.sh`, `build.sh`, and `probe_setup.sh` run during setup) still print their own `[RUN]` lines. Existing generated repositories change after they are regenerated.

## 2026-11-06 — Workbook column order

- **`BenchmarkSpecDefinitions.xlsx` `Workload_Definitions`:** `Validation Objective` and `Command Tools Executed` now sit right after `Parameter_20`, before the three `run_benchmark Command Plus Options` columns (were after them). Values, formatting, and column widths move with them, including the repeated header rows. Scripts look columns up by name, so nothing else changes; `--specification` and `benchmark_specification.json` list the fields in the new order.

## 2026-11-06 — `run_benchmark.sh --help` opens with the workbook description

- **Help header.** Between `Usage:` and `Profiles`, `--help` now prints four labeled lines from the workbook row: `Workload Name`, `Main Goal`, `Validation Objective`, and `Command Tools Executed`. Labels fill a 24-column field, long values wrap at 100 columns with continuation lines under the value, and each value ends with a period. This replaces the single prose line (the first sentence of Execution Description, or the hand-written text in overlay runners).
- **Where.** `scripts/workload_option_help.py` adds `help_header_lines` and `replace_help_header`. `write_runner` in `scripts/materialize_generated_harness.py` writes the header, and `_refresh_workload_option_help` puts it into the 12 overlay runners (SDXL, SGLang, vLLM; AMD and NVIDIA), so all 128 workloads share one layout.
- **Docs and tests.** `docs/run-output-contract.md`, `scripts/templates/run_benchmark_help_skeleton.sh`, and checklist 3.29b describe the header. `tests/test_workload_option_help.py` covers labels, periods, wrapping, and the overlay replacement.
- Existing generated repositories show the new help after they are regenerated.

## 2026-11-06 — Workbook objectives say what runs; runner leftovers removed

- **`BenchmarkSpecDefinitions.xlsx` Main Goal, Validation Objective, Command Tools Executed.** All 128 rows take the reviewed text (merged from four review passes plus Gary's choices). Every cell is within its limit (72 / 120 / 120), and Ubuntu 24.04 and 26.04 rows match for each vendor. Objectives state what is validated; "does not run X" sentences are gone. Notable corrections: 103/303 name the rocblas-bench GEMM load; 106 says latency (the metric is clat p50); 107 STREAM uses one line on all four rows; 116/316 say AllReduce only; 119/219/319/419 share one Main Goal; 120/220/320/420 name rocSOLVER LU / cuSOLVER LU and TFLOPS (the metric unit); 102/302 list the five health metrics.
- **Other columns.** Removed leftover disclaimers (not pytest/test_ops.py, not TorchBench, not TensorFlow, not test_bench.py, not a five-minute server loop, lmbench not-run lists, sibling *_perf, HPL.dat). STREAM 107/207/307/407 description and Known Runtime Constraints now say numactl binds to numa_node when the host accepts it, and thread_affinity core sets OMP_PROC_BIND=close. 122/322 Output Fields list metric #3 `batch_latency_max_msec`; 122/322 no longer claim p50/p95/p99 equal the mean. 120/320 Raw Output Format no longer says "not mpirun".
- **219/419 rename.** Workload Name is `PyTorch Microkernel Suite` (was `TorchBench Microkernels`) on every sheet, and the short name is `Torch Kernel`, matching 119/319. `torch-micro-nvidia/component.json` selects the new name. Repo names were already `torch-micro-suite`.
- **Components.** `rccl-bandwidth-amd/files/scripts/build.sh` builds only `bin/all_reduce_perf` (the four copies under other collective names could only exit). `linpack-rochpl-amd` no longer ships or rewrites `HPL.dat`, which `bin/rochpl` never read. `lmbench-amd` no longer runs `lat_syscall write`, so AMD and NVIDIA run the same lmbench subset; 112/312 text matches.
- **Regenerated** `config/workload_parameters.yaml` and `user_scripts/show_metrics.sh` from the workbook.

## 2026-11-06 — results/raw run directories use WORKLOAD/SYSTEM labels

- **New name.** Each run directory under `results/raw/` is `YYYYMMDD_HHMMSSZ_WORKLOAD-<NNN>_SYSTEM-<hostname>`, for example `20261106_100212Z_WORKLOAD-101_SYSTEM-ubuntu-gpu-mi300x1-192gb-devcloud-atl1`. It replaces `YYYYMMDD_HHMMSS_<repo_name>_<hostname>`. The timestamp is UTC and now says so with a `Z`. `<NNN>` is the leading workload number of the repository directory (`<Workload Number>-<Repo Name>`), zero-padded to 3 digits. `_` separates fields only; any `_` in the workload or hostname value becomes `-`.
- **One builder.** `benchmark_raw_run_dir_name <repo_name> <hostname>` in `scripts/lib/common.sh` prints the name. The harness template in `scripts/materialize_generated_harness.py` and all 12 `implementation_components/*/files/run_benchmark.sh` runners call it instead of assembling `${STAMP}_${REPO_NAME}_${HOSTNAME_VALUE}`.
- **Docs.** `AGENTS.md`, `docs/run-output-contract.md`, `docs/repository-template.md`, `docs/SUBMISSION_CHECKLIST.md` (3.34), `templates/README_TEMPLATE.md`, `templates/SPEC_TEMPLATE.md`, the `fill_generated_docs.py` per-run artifact text, and the `update_runtime_ledger.py --raw-run-dir` help describe the new name.
- **Compatibility.** Existing run directories keep their old names. The self-check's latest-run lookup sorts by name, and both formats start with the date and time, so it still picks the newest run. Ledger rows written before this change keep the old `raw_run_dir` values.

## 2026-11-05 — README.md uses the short workload format

- **`templates/README_TEMPLATE.md`** is rewritten to the short format: title, one-line description, Quick Start, Profiles and Parameters, Metrics with Notes, Output, Requirements, Run the Whole Bundle, Troubleshooting, Repository Layout, Continuous Integration. The numbered sections 1–11, the Download as a Bundle and Suite Tools blocks, the placeholder Installation/Running code blocks, the fixture CSV samples, the generator-only troubleshooting entries, the empty NVIDIA section, and the mermaid diagram are gone.
- **`scripts/readme_sections.py` (new)** renders every data-driven section from `benchmark_specification.json` and the generated tree. It is called from `scripts/fill_generated_docs.py` for `[[GENERATE: readme.<section>]]` markers; PRD and SPEC rendering is unchanged.
  - Description from Main Goal ("Measure …" → "Measures …"), plus the bundle, and a CPU-only note for the CPU / System domain.
  - Profiles and Parameters table from Parameter_01..20 and Profile Parameter Values through `workload_option_help.py`, the same source as `run_benchmark.sh --help`. Values longer than 40 characters are shown as item counts. Override example is the `--help` example.
  - Metrics table from Metrics, including keys written in the middle of a label. Notes from Known Runtime Constraints, one bullet per sentence.
  - Requirements from OS Version, GPU Vendor, GPU Model, GPU Runtime Version, Python Version, and Framework (Bash, SQLite, Python, and PyYAML are not listed).
  - Troubleshooting by rule: the ROCm reboot/resume entry for workloads on the ROCm setup skeleton, the Hugging Face token entry when Framework names Mistral, an SSH-drop entry, and an `na` entry for every workload.
  - Repository Layout from the files present when docs are filled (SPEC.md at the root, PRD under docs/, single-file src/ shown by name).
- **Checks.** `self_check_generated_repo.sh`, `check_github_publish_ready.sh`, and `prepare_github_publish.sh` require the six new headings and at least 60 lines, and no longer require Prerequisites or mermaid. The kernel_version cross-check also reads the new Parameters row and is skipped when the yaml value is per-profile.
- **`create_generated_repo.py`** requires `scripts/readme_sections.py`, `scripts/workload_option_help.py`, `scripts/generate_workload_parameters.py`, and `config/workload_parameters.yaml` in the template.
- **Tests.** `tests/test_readme_bundle_sections.py` covers the new layout for one workload in each bundle, the no-parameter case, and an unknown section marker.

## 2026-11-05 — generated PRD and generation report leave the repository root

- **`docs/PRD.md` and `docs/GENERATION_REPORT.md`.** `scripts/fill_generated_docs.py` writes both under `docs/`. `scripts/create_one_workload.py` stamps timing into `docs/GENERATION_REPORT.md`. `SPEC.md` stays at the repository root. Self-check, smoke check, and the publish-ready check fail if either moved file is still at the root. `prepare_github_publish.sh` still deletes the generation report, from `docs/` and from the root if a copy is left there. `docs/PRD.md` is published.

## 2026-11-05 — run_benchmark.sh --help uses Profiles, Parameters, and General options

- **`run_benchmark.sh --help` uses one layout for every workload.** `Profiles (default: --smoke)`, then `Parameters (override the profile's value)` when the workload has parameters, then `General options` (`--config`, `--quiet`, `--log-level`, `--specification`, `--help`). The fourth example is `bash run_benchmark.sh --baseline` plus one simple parameter override, such as `--num-threads 8`. Workloads with no parameters omit that line.

## 2026-11-05 — help labels workbook parameters as Parameters

- **`run_benchmark.sh --help` names that section `Parameters:`.** The flags under it are still Parameter_01..Parameter_20. The heading is no longer `Workload options:`.

## 2026-11-05 — benchmark_config.yaml has no profile seed

- **`config/benchmark_config.yaml` no longer contains `sweep.profile`.** Smoke, baseline, and extended still come from `--smoke`, `--baseline`, and `--extended`. `scripts/generate_benchmark_config.py` does not write the key, and a locked overlay loses a leftover `profile: smoke` or `profile: baseline` when its sweep is merged. LLM Serving self-check no longer requires `profile: baseline`.

## 2026-11-05 — run_benchmark.sh always validates

- **`run_benchmark.sh` no longer documents `--validate` or `--no-validate`.** Result validation always runs after parse. `--no-validate` is rejected. `--validate` is still accepted and ignored, so a published GPU smoke workflow or an older command that passes it does not stop before the measurement.
- **Callers:** `gpu-smoke.yml`, generation smoke, README and help examples, profile command reconstruction, and the runtime-ledger command now use `bash run_benchmark.sh --<profile>`. `create_one_workload.py --validate-only` is unchanged.

## 2026-11-05 — ROCm reboot warning repeats the suite command

- **`scripts/templates/setup_rocm_reboot_skeleton.sh`:** thirty seconds before the amdgpu reboot, setup prints the warning with the local reboot time. If `run_benchmark_suite.sh` started this setup, the rerun line is that command (`--baseline`, `-w`, and the rest), not a fixed `--smoke`. The command is saved for the post-boot `SETUP COMPLETE` banner. The same warning is used when `ROCM_DEFER_REBOOT=0` reboots from the 24.04 or 26.04 installer.

## 2026-11-05 — ROCm setup warns once when the AMD driver is not yet loaded

- **`scripts/templates/setup_rocm_reboot_skeleton.sh`:** at the start of every AMD workload, setup prints the reboot notice only when `amdgpu-dkms` is not the module now running. The workload that installs the driver prints it. Later workloads, and the resume after the reboot, do not. The suite's hidden stdout is copied to `/dev/tty` when that is a different destination.

## 2026-11-05 — ROCm setup prints a completion banner after the reboot

- **`scripts/templates/setup_rocm_reboot_skeleton.sh`:** when setup is the systemd resume after the postponed reboot, the last lines of `results/reboot_resume.log` name the repository, the local finish time, and the suite command to run next. A run that reloads amdgpu in place still ends at `[PASS] setup.sh now complete` and does not claim a reboot. No `wall`.

## 2026-11-04 — TEMPLATE_00_120: run_benchmark.sh profile flags only

- **`run_benchmark.sh --help` lists each workload parameter with a short description and its smoke, baseline, and extended values.** A value shared by all three profiles is printed once. Profile notes are omitted. `materialize_generated_harness.py` fills the section for a new runner and for an overlay runner.
- **`run_benchmark.sh` no longer accepts `--permissions-check`, `--matrix-definition`, `--save-options-file`, or `--output-format`.** `--specification` still prints the workload specification and exits before setup. Output format comes from `config/benchmark_config.yaml`. The harness still writes `cli_options.env` and still passes that format to a collector that accepts `--output-format`.
- **`run_benchmark.sh` no longer accepts `--profile`, `--device`, `--phase`, `--phase1` through `--phase4`, or an operator `--raw-file`.** Profiles are `--smoke`, `--baseline`, and `--extended`. Every run creates its own raw file, runs setup, then collection, parse, and validation. Collectors, parsers, and the runtime ledger still receive the profile name and the raw path the harness created. `list_runs.sh` and `show_metrics.sh` still filter with `--profile NAME`.

## 2026-11-04 — TEMPLATE_00_120: generator CI lint fixes

- **Removed the truncated `templates/suite-tools/scripts/get_ledger_info.sh`.** It ended mid-line at line 214 and failed the generator's Template CI shell lint (shellcheck SC1072/SC1073). It was already superseded by `user_scripts/get_benchmark_results.sh` and no longer published to `gpu-bench-suite`; nothing referenced it. The now-empty `templates/suite-tools/scripts/` folder is removed too.
- **Removed the unused `import shlex` from `scripts/remote_host_preflight.py`** (ruff F401), which stopped `publish_benchmarks_to_github.sh` at its preflight lint.

## 2026-11-03 — TEMPLATE_00_119: 401-432 host robustness; remote preflight and one-time host bootstrap

**Finding.** The same 401-432 bundle took 1h48m on TEMPLATE_00_117 (2026-10-22, 64.247.201.37) and 3h16m on TEMPLATE_00_118 (2026-11-03, 103.207.149.92). The installers were byte-identical. About 15 minutes came from three TEMPLATE_00_118 collector edits (not in that changelog) that failed on the Nov 3 container: the 401 kernel comparison, iperf3 `-l 128K` on UDP, and GUPS under `numactl` with no NUMA policy. The rest was the slower, cold VM: every bucket was slower (light workloads 1.4x, CUDA toolkit 1.9x, vLLM 2.1x, RAG 4.8x). Both hosts ran kernel `6.8.0-147-generic`, so the 401 failure is the code change, not the VM.

- **Collector fixes ported from Project413 into the template** (they existed only in that batch's copy): `iperf3-nvidia` clamps a UDP `-l` above 65507 bytes (iperf3 3.20 rejects it; TCP keeps the workbook `buffer_length`); `gups-nvidia` reruns without `numactl` when the host prints "does not support NUMA", and reports PMU counters it cannot read as `na (expected: PMU access denied)`.
- **Same guards in the siblings:** `iperf3-amd` gets the UDP clamp. `stream-collect-nvidia`, `stream-collect-amd` and `gups-amd` get `numactl_or_plain()`, which probes the exact bind on `/bin/true` and runs unbound, with a `[WARN]`, when the host rejects it.
- **401/201 kernel mismatch is recorded, not a failure (`system-config-nvidia`).** `status` no longer depends on `uname -r`. The collector writes `kernel_release_mismatch_count` (same column as `system-config-amd`) and `kernel_check.txt`, and prints a `[WARN]`. A container cannot change its host kernel, and the kernel is not one of the five published metrics.
- **Ledger:** a run whose runner exit code is nonzero now records `result_status` `FAIL` (`metric_contract.RUN_FAILED_STATUS`). Before, 401 on Nov 3 showed `exit_code=1` beside `PASS`.
- **Remote host preflight (`scripts/remote_host_preflight.py`), warnings only.** Before workload 1 of a multi-workload batch, `create_one_workload.py` probes the VM: OS, kernel against every workbook `kernel_version` in the range, vendor and GPU, `nvcc`, DCGM, `numactl` binding, iperf3, free disk, Hugging Face token, a 100 MB ranged download from huggingface.co and from download.pytorch.org, and the time of one SSH call. It prints a rough batch-time estimate from the reference runs (Project408/410/411/412) scaled by the measured speeds, and records everything as `remote_host_preflight` in `batch_generation_manifest.json`. Nothing in it can stop, pause, or fail generation; any error becomes a `[WARN]`.
- **One-time host bootstrap (`scripts/remote_host_bootstrap.py`, `scripts/remote/`), timed apart from the workloads.** Copies `scripts/remote/` and two `scripts/lib/` helpers to `/var/lib/gpu-benchmark-host/bootstrap` on the VM and runs `host_bootstrap.sh`: apt index, `python3-venv`, and on NVIDIA the CUDA toolkit and DCGM through the same `install_nvidia_cuda_toolkit` every `setup.sh` calls, so 401 and later setups find them already present. It then starts a detached (`setsid nohup`, `nice`/`ionice`) Hugging Face prefetch of the batch's models (bert-base-uncased, SDXL fp16 files, distilbert-base-uncased, Mistral-7B-v0.3, bge-small-en-v1.5, bge-reranker-base, chosen by workload suffix) into `~/.cache/huggingface`, the cache `scripts/lib/common.sh` already points every workload at, using the same repo ids and file subsets the workloads request. The prefetch overlaps the light workloads; huggingface_hub file locks make a workload wait for a file in flight instead of fetching it twice. Recorded as `host_bootstrap`; the prefetch result is read at the end as `host_prefetch`. `run_from_prompt.py` prints the bootstrap time on its own line. The bootstrap always exits 0. `--skip-host-prep` turns preflight and bootstrap off.
- **apt index refreshed once per host (`nvidia_apt_update_once` in `scripts/lib/nvidia_cuda_toolkit.sh`).** The NVIDIA skeleton and the vLLM/SGLang `setup.sh` overlays skip `apt-get update` when `/var/lib/gpu-benchmark-host/apt_updated_epoch` is under 6 h old and apt lists exist (`BENCHMARK_APT_INDEX_MAX_AGE_SEC`). With no stamp (any host outside batch generation) they refresh as before. `install_nvidia_cuda_toolkit` still refreshes after adding the CUDA repository.
- **Hugging Face xet off by default.** `scripts/lib/common.sh` and both `install_rag_*.sh` export `HF_HUB_DISABLE_XET=1` unless it is set (432 spent most of 23 minutes on `bge-small-en-v1.5` through the xet range client). The RAG installers also default `HF_HOME` to `~/.cache/huggingface`, matching `common.sh`.
- **SGLang 430 on Ubuntu 26.04 installs torch once.** `sglang-prompt-response-nvidia/files/setup.sh` installs `torch==2.13.0+cu130` and `torchvision==0.28.0+cu130` on both releases (26.04 used to install 2.9.1+cu130 first, which `install_sglang_nvidia.sh` then replaced). In both copies of `install_sglang_nvidia.sh`, the two unconditional `sglang-kernel` force-reinstalls on the cu130 path now run only when `cu130_stack_ok` fails (torch 2.13.0+cu130, sglang-kernel 0.4.6.post1, `import sgl_kernel`). The repair path after a failed `launch_server` import is unchanged.
- **Schema / publish:** `schemas/batch_generation_report.schema.json` allows `remote_host_preflight`, `host_bootstrap`, `host_prefetch`, and the existing `generation_successful_seconds` and `generation_seconds_including_failed_attempts`. `prepare_github_publish.sh` strips the new generator-only files from published workloads.
- **Not changed:** per-repo venvs, and the number of SSH calls per workload.
- **Tests:** new `tests/test_template_00_119_host_robustness.py` (30 tests): every collector that builds a `numactl` command has a fallback; both iperf3 collectors clamp UDP; vendor guard parity; kernel mismatch does not set `status`; nonzero exit is `FAIL`; the preflight parses, warns on the Nov 3 host profile, estimates it as slow, reads 401's `kernel_version` 7.0.0 from the workbook, and records instead of raising when SSH is down; bootstrap model selection, SDXL patterns match the installer, scripts parse, bootstrap always exits 0, the driver runs host prep before the loop and catches every error; `nvidia_apt_update_once` skips on a fresh stamp and refreshes otherwise; xet defaults; SGLang single torch and conditional kernel reinstalls. Full suite: 36 files pass.
- **CUDA toolkit installs without Nsight or documentation (`install_nvidia_cuda_toolkit`).** Instead of the `cuda-toolkit-X-Y` metapackage, setup installs `cuda-compiler-X-Y`, `cuda-libraries-dev-X-Y`, `cuda-command-line-tools-X-Y` and `cuda-nvml-dev-X-Y` (`nvidia_cuda_packages`). That keeps `nvcc`, every CUDA library and header, CUPTI, NVTX, `cuda-gdb`, `compute-sanitizer` and NVML headers, and drops `cuda-visual-tools` (Nsight Systems, Nsight Compute, nvvp), `cuda-documentation` and `cuda-demo-suite`, which no workload uses. On the refreshed 26.04 RunPod VM (Nov 3), `apt-get install cuda-toolkit-13-3` took 15m48s of 401's 19m54s (`/usr/local/cuda-13.3` is 4.7 GB); 201's `cuda-toolkit-12-8` took 1m55s. If NVIDIA's repository lacks any of the four, setup prints a `WARN` and installs the full metapackage. The install also passes `-o Dpkg::Options::=--force-unsafe-io` so dpkg does not fsync each unpacked file on the container's overlay filesystem; `nvidia_dpkg_consistent` and the `nvcc` release check still run. `collect_workload.py` already accepts `cuda-nvcc-X-Y` as the installed toolkit. `tests/test_nvidia_cuda_toolkit.py` covers 24.04, 26.04 and the fallback.
- **Publish script, generator cache cleanup (`scripts/publish_benchmarks_to_github.sh`).** The `*.py[co]` cleanup combined `-prune` with `-delete`; GNU find refuses that ("-delete ... turns on -depth"), so it deleted nothing and still reported `removed: 0`. It now skips `.git` with `-not -path './.git/*'`. The never-publish check after it was unaffected and still blocks any cache file.
- **Workbook parameter alignment across the four OS/vendor siblings (`BenchmarkSpecDefinitions.xlsx`).** Each change applies to both Ubuntu releases; `Parameter_NN`, the descriptions, the command columns (`sync_matrix_profile_commands.py`) and `config/workload_parameters.yaml` (`generate_workload_parameters.py`) follow.
  - **209:** adds `num_threads` (1/4/4) and `thread_affinity` (0-3), as 109/309/409 have. The shared multichase collector already used them; without the rows 209 ran 1 unpinned thread while 409 ran 4 pinned to CPUs 0-3. `tests/test_nvidia_sibling_parity.py` drops the x09 exception.
  - **203/403:** remove `throttle_check` and `ecc_check`. `system-stress-nvidia` hardcodes both to true, so the rows did nothing; the AMD twin always records both as well.
  - **103/303:** add `poll_interval` (1). `system-stress-amd` sleeps `poll_interval` seconds between amd-smi samples (0.5 s floor, as in 203/403) instead of a fixed 1 s.
  - **217/417:** remove `function`. The cuBLAS harness accepts only `true`, which is also its default; rocBLAS 117/317 derives `gemm` or `gemm_strided_batched` from `batch_count`.
  - **221/421:** remove `num_workers`, `optimizer` and `gradient_accumulation`. Their values (0 / sgd / 1) equal the trainer's defaults for a missing key, so the measurement does not change; the transcript now shows `true` for the three.
  - **124/324:** add `prompt_len` (32) and `batch_size` (1). `sdxl-diffusers-amd/run_benchmark.sh` parses `--prompt-len` and `--batch-size`, reads them from yaml, and passes them to `infer_sdxl.py`, which already accepted both (a config without them still sends `true`, the old behavior).
  - **125/325:** add `gradient_accumulation` (1) and `warmup_iters` (1/2/5). `distilbert-amd` now runs untimed forward/backward warmup passes before the timer and steps the optimizer every `gradient_accumulation` passes, the same loops as `distilbert-nvidia` 225/425. Without the keys it behaves as before (no warmup, one pass per step). Expect 125/325 throughput slightly above earlier AMD runs, since the first step is no longer timed.
- **Parameter review across the ten families flagged by the four Cursor sessions.** Each family now lists the same parameters on 1xx/2xx/3xx/4xx, and every listed parameter is used. Workbook rows, `Parameter_NN`, descriptions, command columns and `config/workload_parameters.yaml` follow.
  - **Removed (never read by either vendor's collector):** x02 `pcie_check`, `temperature_check`, `dmesg_check` (each could only switch off one of the workload's own metrics; every profile was true); x12 `parallel_jobs` (the metrics are single-thread by definition); x18 `input_source` (always synthetic; cuDNN only echoed it and still records `synthetic`); x19 `batch_size` (the conv batch is the first number of `input_shape`).
  - **x02 has no parameters now.** `sync_matrix_profile_commands.py` writes the bare `--<profile> --validate` command when a workload's `Parameter_NN` slots are all `-`, and `generate_benchmark_config.py` writes an empty sweep instead of failing on missing Profile Parameter Values. Checked with a local `create_generated_repo.py` build of 102 and 202, whose self-check stops at the same point (no GPU run yet) as 112.
  - **x12 lmbench (both collectors):** `warmup_duration_us` is passed as `-W` (microseconds, confirmed in lmbench `lib_timing.c`) to lat_syscall, lat_ctx, lat_mem_rd, bw_mem and bw_pipe. Baseline/extended lowered from 1000000 to 10000: lat_mem_rd 16 128 warms up once per array size, so 1 s would have added about a minute per repetition to runs already near the 5-minute baseline target.
  - **214/414 `cuda-memcpy-nvidia`:** honors `direction` (all or H2D,D2H,D2D; unselected columns blank) and `pinned_memory` (false copies through malloc host buffers via the new `D2H_pageable` kind in `cuda_memcpy.cu`). Pinned and pageable H2D both run whenever H2D is selected, for the ratio metric. The workbook values (all, true) run the same four copies as before.
  - **115/315 `babelstream-hbm-amd`:** `hip_stream.cpp` takes `--block-size` (1-1024) and `--warmup` (untimed launches per kernel, default 1 as before); the Dot kernel's shared tile is sized at launch. **215/415:** `babelstream.cu` also sizes the Dot tile at launch and rejects a block size that is not a power of two from 32 to 1024 (a value above 256 used to overflow the fixed 256-entry tile).
  - **118/318 `miopen-convolution-amd`:** `warmup_iters` runs an untimed MIOpenDriver pass of that many iterations before each timed pass; `search_strategy` takes the cuDNN values: `find` keeps MIOpenDriver's default Find, `heuristic`/`get`/`fixed`/`none` set `MIOPEN_FIND_MODE=FAST`, anything else fails.
  - **x20 HPL (120/220/320/420): removed `num_gpus`, `process_grid_P`, `process_grid_Q`, `block_size` and `panel_factorization`.** `bin/rochpl` and `bin/nvhpl` are single-GPU rocSOLVER/cuSOLVER LU solves that only printed those values; the solver libraries choose their own blocking and factorization. On AMD, `num_gpus` above 1 made `mpirun -np` start competing copies on GPU 0. The AMD collector now always runs `mpirun -np 1`; both binaries take only `--N` (the old flags are accepted and ignored) and print `RESULT problem_size_N=... time_s=... gflops=...` instead of the HPL WR table, which showed settings that were never applied. Both parsers read the new line and still read the old one. Remaining parameters: `problem_size_N`, `warmup_iters`, `num_iterations`. Real multi-GPU HPL would mean switching to upstream rocHPL and NVIDIA HPC Benchmarks, where these parameters would return.
  - **122/322 `resnet50-inference-amd`:** honors `device_id` (`torch.cuda.set_device`) and gains `use_channels_last` (true, as on 222/422), which converts the model and inputs to channels-last.
  - Needs GPU runs: 112-412, 115-415, 118/318, 120-420 (rebuilt binaries), 214/414, 122/322 (channels-last may change AMD throughput).
- **`Workload_Definitions` gains a "Repo Directory Name" column (after Repo Name).** Plain text, kept by hand, filled with today's `<Workload Number>-<Repo Name>` for all 128 rows (for example `107-sys-bench-amd-stream-ddr5-bandwidth-ubu2404`). It is informational: the generator still builds folder and GitHub names from Workload Number and Repo Name (`generated_repo_directory.py`), so editing this column renames nothing and a mismatch is not checked. Extraction copies it into each repo's `benchmark_specification.json` like any other column.
- **`get_remote_info.sh` renamed `get_benchmark_results.sh`, and it runs locally without `--host`.** With `--host` it works exactly as before (one ssh connection, one tar stream). Without `--host` it runs the same collection script on this machine with `bash`, so the folders, ledger copies and run table are identical; it reports "No --host given: collecting from this machine" and "Collected from <hostname> (this machine)". `--port`, `--user` and `-i` without `--host` are usage errors (they usually mean `--host` was forgotten), and a missing workload folder says to give `--host` or `-r`. It is now installed at `/opt/benchmarks` beside `show_metrics.sh` and `run_benchmark_suite.sh` (`create_one_workload.py` and every bundle, whose `.gitignore` gains `DIRECTORIES/` and `RUNTIME_LEDGERS/`), and the bundle README shows `./get_benchmark_results.sh -o ~/results`. References updated in `create_generated_repo.py` (operator tools in the project folder), `emit_shared_workflows.py`, both READMEs, the README template, `docs/github-profile-README.md` and CI. `tests/test_get_benchmark_results_options.py` (renamed) adds a real local collection against a sample folder. Existing project folders keep their old `get_remote_info.sh` copy; generation adds the new one beside it.
- **New suite tool `templates/suite-tools/scripts/list_runs.sh`: the run table, nothing copied.** Prints only the runtime ledger's run table: a header line, then one line per run (workload, profile, runtime, exit code), in the same columns as the table `get_benchmark_results.sh` prints. Errors go to stderr. Without `--host` it reads this machine's ledger (`/var/opt/benchmarks/runtime_ledger.csv`, then `/opt/benchmarks/runtime_ledger.csv`); with `--host` it reads the remote ledger over one ssh login (same connection options and key search as `get_benchmark_results.sh`). `--smoke`/`--baseline`/`--extended`/`--profile NAME` and `--failed` narrow the list; `--file` reads another path, including a saved `RUNTIME_LEDGERS/` copy. It prints no connection or summary lines, so the output can be piped or saved as is. Installed at `/opt/benchmarks`, in every bundle, in the project folder and in `gpu-bench-suite` alongside the other suite tools; documented in both READMEs, the README template and the bundle README. `tests/test_list_runs.py` covers this machine, the filters, Windows line endings, a missing ledger, usage errors and `--host` through a stand-in ssh.
- **All user-run scripts in one folder: `user_scripts/`.** Moved (not copied) the master copies of `run_benchmark_suite.sh`, `show_metrics.sh`, `list_runs.sh` and `get_benchmark_results.sh` (from `templates/suite-tools/scripts/`) and `publish_benchmarks_to_github.sh` (from `scripts/`). `user_scripts/` sits at the generator root, outside `init_generated_repo.py` SHARED_DIRS, so it is never copied into a workload (checked with a local build of 107); the publish script's old exclusion entry is removed. `ci_contract.py` gains `USER_SCRIPTS_REL` and `SUITE_TOOL_SCRIPTS`; `emit_shared_workflows.py` now builds `gpu-bench-suite` from `templates/suite-tools/README.md` plus exactly those four scripts, so the truncated `templates/suite-tools/scripts/get_ledger_info.sh` is no longer published. Updated `create_generated_repo.py` (project-folder tools), `create_one_workload.py` (`/opt/benchmarks` install), `generate_show_metrics.py`, the publish script's master-copy check, CI (`shellcheck` now covers `user_scripts/`), the README (new "User scripts" table) and the tests. `verify_generation_workflow.py` resolves the suite README's `scripts/<name>` links against `user_scripts/`. Refresh the copy of `publish_benchmarks_to_github.sh` in `Publishing\` from `user_scripts/`.
- **Every workload repository ships `show_metrics.sh` at its top level** (next to `run_benchmark.sh`), so a single downloaded repository can show its own runs with `./show_metrics.sh <number>`. `create_generated_repo.py` (`WORKLOAD_TOOLS`, `install_workload_tools`) copies `user_scripts/show_metrics.sh` into each new workload right after regenerating its tables, always replacing an older copy. `publish_benchmarks_to_github.sh` step 1 replaces each workload's copy with the master from the generator in the run folder, so all published copies match it and workloads generated earlier get it on their next publish. `check_github_publish_ready.sh` requires the file and runs `bash -n` on it. The README template says the script is in the repository (and that four suite tools, not three, ship with the bundles). The master copy stays in `user_scripts/`; this is a deliberate duplicate.

## 2026-10-31 — Publish BenchmarkSpecDefinitions.xlsx to the GitHub profile repository

- **`scripts/publish_benchmarks_to_github.sh` step 10:** after the generator is published, the script clones `garymichaelbass/garymichaelbass`, copies `BenchmarkSpecDefinitions.xlsx` from the generator in the run folder, and commits that file only. `git add -A` is not used, so the profile README and the sample workload folders stay. An unchanged file is not committed again. Step 0 stops if the workbook is missing from the run folder. The download address is `https://github.com/garymichaelbass/garymichaelbass/raw/main/BenchmarkSpecDefinitions.xlsx`.
- **Tests:** `tests/test_publish_profile_spec.py` runs the step against a local repository that already has a README and a sample folder. Both survive an add and an update of the workbook.

## 2026-10-22 — TEMPLATE_00_117: workbook notes no longer fail generation; x09/x10/x14 smoke sizes and x01 driver wording match what runs

- **Authoring notes stripped from every profile cell (`scripts/extract_benchmark_definition.py`).** In the TEMPLATE_00_116 batches, 207 (Project401) and 416 (Project403) failed `self_check_generated_repo.sh` because a `TEMPLATE_00_116` note in `Parameters_SmokeBaselineExtend` was copied into `benchmark_specification.json`; Cursor patched each batch's copy of the extractor, but the template was not. The smoke, baseline, extended and notes cells now go through `_strip_profile_cell()`, which removes `TEMPLATE_00_<n>` notes (including dated ones such as `2026-10-22 TEMPLATE_00_117: ...`) and returns any cell without the tag unchanged. All 128 workloads now extract with no `TEMPLATE_00_` text; before this, the 00_117 notes on x15, x20, x21, 130/330 and others would have failed the same way.
- **x09 multichase (109/209/309/409) smoke `working_set_size`:** `local_dram` and `remote_dram` 16777216 -> 268435456. 16 MiB fits in the host L3 (48 MiB on the 401-432 Xeon), so smoke published a 32-34 ns L3 hit as local DRAM latency. Baseline and extended are unchanged.
- **x10 NUMA cache sweep (110/210/310/410) smoke `working_set_size`:** DRAM tier 16777216 -> 268435456. The collector already raised a DRAM tier below max(256 MiB, 2x LLC) to that size, so smoke measured 256 MiB while the workbook said 16 MiB; the workbook now states the size that runs.
- **x14 memcpy bandwidth (114/214/314/414) smoke:** `max_bytes` 4096 -> 268435456 and `num_iterations` 3 -> 10. Both collectors already raised these to `BANDWIDTH_SIZE_FLOOR` (256 MiB) and `BANDWIDTH_ITERATION_FLOOR` (10) without saying so, so smoke bandwidth was measured at 256 MiB, not 4 KiB, while the workbook, ledger and metric labels implied 4 KiB. The floors stay as a safety net; a test now fails if any profile value falls below them, so they can no longer silently change a run. Smoke duration is unchanged.
- **x01 NVIDIA driver compliance (201/401):** the workbook described `nvidia_driver_version` as a substring of the nvidia-smi Driver Version, while the collector scores the share of the three driver components (kernel module, nvidia-smi, libcuda) at or above that minimum, so driver 595.91.07 scored 100% against 580. The collector's minimum-version rule is kept (a newer driver is compliant); `Execution Description With Parameters` and `config/workload_parameters.yaml` now describe it.
- **Synced:** `sync_matrix_profile_commands.py` (12 command cells for x09/x10/x14) and `generate_workload_parameters.py`; both `--check` runs pass. New workbook notes use "(00_117)" rather than a `TEMPLATE_00_` tag.
- **Tests:** new `tests/test_template_00_117_cursor_review_fixes.py` (11 tests). Full suite: 359 tests pass.

## 2026-10-22 — TEMPLATE_00_117: x30 publishes medians; 207/407 and 130/330 baseline fit 5:00; every run records its release

- **x30 SGLang prompt-response (130/230/330/430) publishes the median (p50) of its timed requests** for end-to-end latency, TTFT and output tokens/s, in `prompt_response_client.py` (both vendors) and both parsers (`sglang-prompt-response-nvidia/.../parse_results.py`, `sglang-prompt-parser-amd/.../parse_results.py`, `MEDIAN_METRICS`). Finding (v1.0.21 fresh clone, Project401): the single warm-up did not absorb all of 230's compilation, so the first timed request had TTFT 9156 ms while the other seven took ~29 ms; the mean published 1170 ms TTFT and 6524 ms end-to-end (median 5409 ms). On 130/330/430 mean and median agree within 1 ms / 0.1%. Completed-request rate and cache hit rate are unchanged (rates over all requests). Metric keys are unchanged; the three labels now say p50 (`Workload_Definitions` Metrics and `Metric_Short_Labels`), and the parser note says so. Every request's own value stays in `raw_results.csv`.
- **207/407 baseline `num_iterations` 14800 -> 10000.** 207 took 6:27 on a Xeon 8452Y host (STREAM Triad 94 GB/s); 407 took 2:02 on a Xeon 8470 host. 10000 is about 4:20 and 1:25. Extended stays 22600 (about 9:50 on the slow host).
- **130/330 baseline `num_prompts` 8 -> 5.** 130 took 5:15 (start-up ~55 s, warm-up 148 s, 8 timed requests 112 s). Five requests keep each request identical and trim ~42 s: about 4:33 (330 about 4:14). `output_len` is unchanged.
- **Release recorded in every run:** `config/hw_sw_info_commands.xlsx` adds 139.1 "Workload release" (`git -C "${COLLECTOR_REPO_ROOT:-.}" describe --tags --always`) and 139.2 "Bundle release" (the same one folder up), each printing a plain message when there is no git metadata (a copied, not cloned, workload). `scripts/generate_collect_hw_sw_info.sh` exports `COLLECTOR_REPO_ROOT` so the child bash that runs each command sees it; `scripts/collect_hw_sw_info.sh` regenerated. Checked by running the collector in a tagged fake bundle (workload v9.9.9, bundle v9.9.8 recorded) and in a copied folder (the no-git messages recorded).
- **Tests:** new `tests/test_template_00_117_fixes.py`; `tests/test_nvidia_sibling_parity.py` already holds 207 = 407 and 130 = 330. `sync_matrix_profile_commands.py --check` passes.

## 2026-10-22 — TEMPLATE_00_117: x15 BabelStream smoke reads HBM, not cache

- **Finding (v1.0.21 fresh GitHub clone, Project403):** 415 smoke published Add and Triad as `na (bandwidth 3982 GB/s exceeds H100 SXM HBM3 peak 3350 GB/s)` and its other kernels as cache-resident. Smoke used `array_size` 1048576 FP64 values: 8 MiB per array, 24 MiB for BabelStream's three arrays, which fits in the H100 L2 (50 MB) and the MI300X Infinity Cache (256 MB). Smoke measured cache bandwidth on every platform.
- **Fix (`BenchmarkSpecDefinitions.xlsx`, 115/215/315/415, smoke only):** `array_size` 1048576 -> 67108864 (512 MiB per array, 1.5 GiB working set) and `num_iterations` 2 -> 20. `metric_contract.cache_resident()` treats a working set under 4x the GPU cache as cache-resident (`CACHE_LLC_MULTIPLE`); 1.5 GiB clears 4x the MI300X's 256 MiB (1 GiB) and 4x the H100's 50 MiB. 33554432 (768 MiB) would still be cache-resident on the MI300X. Twenty iterations steady the result; GPU time stays a few tens of milliseconds, and the estimated smoke runtime is 2.5-3.5 s (was 1-2 s), mostly BabelStream's CPU result check. Baseline and extended are unchanged. `sync_matrix_profile_commands.py` updated the four smoke command cells; the notes cells record the change.
- **Bundle README (`scripts/publish_benchmarks_to_github.sh`):** the "smoke is a wiring check" example no longer says x15 smoke arrays fit in GPU cache; it names x20 HPL smoke's 4096 x 4096 system and x15 smoke's 20 iterations instead.
- **Tests:** `tests/test_nvidia_sibling_parity.py` checks that x15's working set in every profile clears the cache-resident rule on MI300X, H100 SXM, H100 NVL, H100 PCIe and an unrecognized GPU, and that 115/215/315/415 share one value.

## 2026-10-22 — TEMPLATE_00_117: AMD system stress (103/303) samples only after its GPU load is running

- **Finding (v1.0.21 fresh GitHub clone, Project400):** 103 smoke published both GPU metrics as `na (timed loop too short: ... GPU utilization peaked at 4%)`. `rocblas-bench` spent 3.2-4.2 s initializing the rocBLAS library before its first GEMM, and smoke samples for only 5 s, so all five samples were idle (1-4% utilization, 175-199 W, 39 C). In 103 baseline the GPU reached 98% and 739 W at second 5, so baseline and extended also averaged five idle seconds into sustained power. NVIDIA 203 uses its own CUDA kernel, which loads the GPU within the first second.
- **Fix (`implementation_components/system-stress-amd/files/scripts/collect_workload.py`):** the GPU load starts first; `wait_for_gpu_load()` polls utilization every 0.5 s until it reaches 10% (`UTIL_THRESHOLD_PCT`), the load fails, or 30 s pass (`LOAD_WAIT_MAX_S`). The load's deadline is then reset so it runs through the whole window, and only then do `stress-ng` and the timed sampling start. Smoke keeps its 5 samples, now all under load; the run log records the wait (`[INFO] GPU load reached N% utilization after X s; the S s timed window starts now`). The 10% threshold is unchanged: lowering it would publish idle readings (0-4% utilization is idle noise) as power and temperature under load, the defect the threshold was added to prevent.
- **na wording:** if utilization never reaches 10% within 30 s, both GPU metrics are `na (GPU load did not run: GPU utilization peaked at N% after waiting up to 30 s for it to reach 10%)` in every profile. The smoke-only "timed loop too short" form is removed, because a load that never starts is a real failure, and `classify_na` counts it as one (INCOMPLETE).
- **Tests:** new `tests/test_system_stress_amd_load_wait.py` (wait stops at 10%, on a failed load, when the load thread ends, and after the time limit; unreadable utilization counts as 0; the na reason in every profile is classified unexpected; order: GPU load, wait, deadline reset, CPU stress, sampling).
- **Not changed:** NVIDIA 203/403 (its load starts at once), smoke durations in `BenchmarkSpecDefinitions.xlsx`, and the metrics themselves.

## 2026-10-22 — TEMPLATE_00_117: vLLM and SGLang setups check PyTorch's NCCL, not a system libnccl.so

- **Finding (TEMPLATE_00_116, fresh 24.04 copy, Project401):** `./run_benchmark_suite.sh -w 201,205,218,221,222,226,232,230 --smoke` failed 230 at the end of setup with `[FAIL] Required framework item failed verification: NCCL`, after torch 2.13.0+cu130, SGLang 0.5.19, `sgl_kernel` and `launch_server` had all verified. The check required `/usr/lib/x86_64-linux-gnu/libnccl.so` or `/usr/local/cuda/lib64/libnccl.so`, which only the NCCL bandwidth workload (x16) installs (`libnccl2 libnccl-dev`). Full-suite runs passed only because x16 runs before x27-x30; this run skipped 216. In the same `.venv`, `torch.cuda.nccl.version()` returned `(2, 29, 7)`.
- **Fix:** the NCCL check in `implementation_components/sglang-prompt-response-nvidia`, `vllm-kvcache-nvidia`, `vllm-throughput-nvidia` and `vllm-token-generation-nvidia` (`files/setup.sh`) is now `verify_cmd "NCCL" .venv/bin/python -c "import torch; assert torch.cuda.nccl.version()"`: the NCCL PyTorch ships (`nvidia-nccl-cu13`), which vLLM and SGLang use. It still fails when PyTorch has no working NCCL. Nothing new is installed, the check keeps its name, and x16's own system-NCCL checks are unchanged (it compiles against libnccl).
- **Tests:** `tests/test_nvidia_cuda_toolkit.py` checks all four setups use the PyTorch check, and runs it against a `.venv` that reports NCCL and one that does not.
- **Already generated:** workloads 227-230 and 427-430 generated from TEMPLATE_00_116 still have the old check; regenerate them, or apply the same one-line change to their `setup.sh` before publishing.

## 2026-10-21 — TEMPLATE_00_116: x20 NVIDIA extended N matches what runs; preflight finds a working Python

- **x20 NVIDIA HPL (220/420) extended:** `BenchmarkSpecDefinitions.xlsx` said `problem_size_N` 65536, but the cuSOLVER collector clamps N >= 65536 to 32768 (`clamp_problem_n`), so every extended run used N=32768 while the ledger and metrics recorded 65536. Extended N is now 32768, the size that ran (and the AMD 120/320 value, kept after N=65536 hung). Runtime does not change. The notes cells record why; `sync_matrix_profile_commands.py` updated the two extended command cells. `tests/test_nvidia_sibling_parity.py` now fails if any 220/420 profile N would be clamped.
- **Generation-host preflight picks the interpreter:** in all four TEMPLATE_00_115 batches, Git Bash's `python3` (3.12, no PyYAML, no pip) failed preflight, and preflight printed the start command with that same interpreter, so each agent searched for `C:\Python\python.exe` by hand. `scripts/generation_host_preflight.py` now, when its own interpreter lacks Python 3.10+ or PyYAML, tries `GENERATOR_PYTHON` (if set), `python3`, `python` and `py -3` on `PATH`, then `/c/Python/python.exe`, `/c/Python3*/python.exe` and `%LOCALAPPDATA%\Programs\Python\Python3*\python.exe`, runs `-c "import sys, yaml; assert sys.version_info >= (3, 10)"` on each, and prints the start command with the first that passes. If none passes it says so, lists what it tried, and prints `<python> -m pip install pyyaml` for an interpreter that has pip (or the python.org install step).
- **Docs:** `AGENTS.md`, `docs/AI_AGENT_INSTRUCTIONS.md`, `docs/generation-workflow.md` and `.cursor/rules/generate-workloads.mdc` no longer give a bare `MSYS_NO_PATHCONV=1 python3 scripts/run_from_prompt.py ...` start command. They say to run `python3 scripts/generation_host_preflight.py --prompt-file ../AI_AGENT_PROMPT_SUBMITTED_<WORKLOADS>_<UTC_TIMESTAMP>.md` first, then the command it prints (`MSYS_NO_PATHCONV=1 <python> scripts/run_from_prompt.py ...`) exactly as printed. `tests/test_batch_generation_tooling.py` checks both lines in all four documents and covers the candidate order, the printed command, and the none-found message.

## 2026-10-21 — TEMPLATE_00_116: 24.04 and 26.04 NVIDIA siblings run the same test; one PyTorch build; inventory records the workload's Python packages

- **Finding (TEMPLATE_00_115, v1.0.19 fresh-install runs, Projects 395–398):** all 292 runs passed and the ledgers matched every `metrics_summary.txt`, but the NVIDIA 24.04 and 26.04 results were not comparable. (1) `BenchmarkSpecDefinitions.xlsx` gave 2xx and 4xx different values in 21 `Parameters_SmokeBaselineExtend` rows, because the 4xx rows had been retuned separately from their own runtime ledgers; for example x29 baseline `output_len` 18600 vs 12300 gave end-to-end latencies of 280 s vs 160 s at nearly the same per-token speed. AMD 1xx/3xx differed only in x01 `kernel_version`. (2) 24.04 PyTorch workloads installed `torch 2.7.1+cu128` (Python 3.12) while 26.04 installed `2.13.0+cu130` (Python 3.14); x32 RAG generation ran 34.8 vs 14.5 tokens/s on identical H100 PCIe hosts. (3) `software_info.txt` probed Python packages with the system `python3`, so the PyTorch version lookup failed in 280 of 292 runs (only the vLLM runners had `.venv` on `PATH`).
- **Parameters (36 cells, `BenchmarkSpecDefinitions.xlsx`):** each differing 2xx/4xx row now holds one value. The value is the larger of the two when ledger runtimes predict at most 4:30 (baseline) and 13:30 (extended) on both releases, otherwise the smaller, otherwise a lower value that fits. Predictions scale the slowest comparable ledger run (other parameters equal to today's) from Projects 386–398 and the 2026-10-19/20 aggregate ledgers. Reduced below both old values: x16 baseline 65000 / extended 200000 (when the NCCL sweep actually runs, 157000/113000 took 6:32/7:44 and 382000/319000 took 17:20/21:00; on one GPU it is skipped in ~45 s), x23 extended 52000 (26.04 took 14:29 at 56400), x30 baseline output_len 860 (26.04 took 4:49 at 930). Each changed row's notes cell records the change and its predicted runtimes. `scripts/sync_matrix_profile_commands.py` rewrote the matching 36 `Workload_Definitions` command cells (`--check` passes). Now 2xx/4xx differ only in x01 `kernel_version`/`cuda_version`, like 1xx/3xx.
- **PyTorch:** `scripts/install_pytorch_nvidia.sh` installs `torch==2.13.0+cu130` / `torchvision==0.28.0+cu130` on Ubuntu 24.04 too, as do `install_rag_nvidia.sh` (232), the SGLang 230 pre-install (which `install_sglang_nvidia.sh` already moved to 2.13.0+cu130) and the vLLM fallback (cu130 index). The CUDA-13 cuDNN wheel (`nvidia-cudnn-cu13==9.23.2.1`) and `jax[cuda13]` follow `torch.version.cuda`, so 24.04 now receives them. x18 (`cudnn-convolution-nvidia`) does not use PyTorch and keeps choosing cuDNN by `nvcc` major (24.04: system `libcudnn9-cuda-12`). `create_one_workload.py` stamps NVIDIA venvs as `wheel=cu130` on both releases, so an old cu128 venv is not reused. The spreadsheet's PyTorch/torchvision columns for 205, 219, 221–225 and 232 now match their 4xx siblings. Python itself still follows the OS (24.04: 3.12, 26.04: 3.14).
- **Software inventory:** `scripts/generate_collect_hw_sw_info.sh` (and the regenerated `scripts/collect_hw_sw_info.sh`) put `<repo>/.venv/bin` first on `PATH` when that virtualenv exists, so `software_info.txt` records the workload's torch, torchvision, transformers, JAX, vLLM, SGLang, faiss and diffusers versions.
- **Checks:** new `tests/test_nvidia_sibling_parity.py` (parameter parity for 2xx/4xx and 1xx/3xx, matching PyTorch columns, no 2.7.1+cu128 pin in NVIDIA installers, collector uses the venv). `AGENTS.md` records the parity rule, the 5:00/15:00 limits for retunes, and the single PyTorch build.
- **Validate before publishing:** these are the first 24.04 runs of the PyTorch workloads (205, 219, 221–226, 232) on torch 2.13.0+cu130. Run them on a clean 24.04 image, including x21/x22 on a host where x18 already installed the system `libcudnn9-cuda-12`, and confirm baseline/extended runtimes against the predictions in the notes column.

## 2026-10-21 — TEMPLATE_00_115: NVIDIA setup installs CUDA from NVIDIA's repository on Ubuntu 24.04; no Ubuntu nvidia-cuda-toolkit; a broken dpkg stops setup

- **Finding (TEMPLATE_00_114, Project391 fresh install):** all 32 Ubuntu 24.04 workloads failed setup from a fresh clone, although generation had passed on the development VM. That VM already had `nvcc` 12.6, so the 24.04 branch never ran. On a fresh image the branch asked for `cuda-nvcc-12-8`, `-12-6` and `-13-1` without adding NVIDIA's CUDA repository ("Unable to locate package"), then installed Ubuntu's `nvidia-cuda-toolkit` 12.0. That package pulled `libnvidia-compute-580`, which could not unpack over the bind-mounted 595 driver library (`Invalid cross-device link`). `|| true` inside `apt_install` hid the error, about 215 packages were left unpacked and unconfigured, CUDA 12.0 `nvcc` rejected GCC 13 (`unsupported GNU version`), and workloads 202–232 stopped at `dpkg is not consistent`. Ubuntu 26.04 passed because its branch adds the `ubuntu2604` repository and installs `cuda-toolkit-13-3`.
- **`scripts/lib/nvidia_cuda_toolkit.sh` (new):** `install_nvidia_cuda_toolkit` installs one toolkit per Ubuntu release from NVIDIA's CUDA repository (24.04: `cuda-toolkit-12-8`, 26.04: `cuda-toolkit-13-3`), adding `cuda-keyring` with `curl` when apt does not know the package. It checks `/usr/local/cuda-<ver>/bin/nvcc`, not just any `nvcc` on `PATH`, so a leftover Ubuntu 12.0 `nvcc` cannot skip the install, and points `/usr/local/cuda` at that release. `nvidia_pin_host_driver` writes `/etc/apt/preferences.d/benchmark-host-nvidia-driver` (Pin-Priority -1 for `nvidia-cuda-toolkit`, `libnvidia-compute-*`, `nvidia-driver-*`, `nvidia-utils-*`) only when no dpkg package owns `libnvidia-ml.so.1`; a host whose driver came from packages gets no pin. `nvidia_dcgm_package` returns `datacenter-gpu-manager-4-cuda12` or `-cuda13` (`datacenter-gpu-manager-4` is a virtual package apt cannot install).
- **`scripts/templates/setup_nvidia_skeleton.sh` and the overlays `vllm-kvcache-nvidia`, `vllm-throughput-nvidia`, `vllm-token-generation-nvidia`, `sglang-prompt-response-nvidia`:** all call `install_nvidia_cuda_toolkit`; `nvidia-cuda-toolkit` is gone from every install. The vLLM overlays had no 26.04 branch and installed CUDA only when `nvcc` was missing, so they passed only after an earlier workload installed CUDA; they now install the same release as the skeleton. The vLLM fallback torch index moves from cu126 to cu128. The SGLang keyring download uses `curl`, like the skeleton.
- **vLLM torchaudio (227/228/229 overlays):** one install, `torchaudio==2.11.0+${AUDIO_TAG}` with `--force-reinstall --no-deps`, where `AUDIO_TAG` comes from the installed torch (cu130 under vLLM 0.31's torch 2.13.0). torchaudio 2.11.0 is the last release and is built against PyTorch's stable ABI, so it supports torch 2.11 and later. The old fallback installed `torchaudio==2.11.0+cu126` with `--no-deps` next to a cu130 torch, and the import-only `TorchAudio-CUDA` check would have passed it. `--no-deps` keeps a reinstall from moving torch.
- **SDXL runner (`sdxl-diffusers-nvidia/files/run_benchmark.sh`):** `PATH` starts with `/usr/local/cuda/bin`. It put `/usr/local/cuda-12.6/bin` first, so on a host that still has 12.6 (the development VM) workload 224 ran a different `nvcc` than the one setup installed and recorded.
- **`apt_install`:** returns 1 when apt fails (an explicit return; bash ignores `set -e` inside a function on the left of `||`), so `apt_install fio libaio-dev || apt_install fio` can now fall back and a bare call stops setup. After every install it runs `dpkg --audit` and exits on a non-empty result, even for an optional package such as DCGM. Optional packages log a `WARN|SETUP` line instead of `|| true`. **Behaviour change:** a package in the skeleton's base list that apt cannot install now stops setup instead of being skipped.
- **`scripts/lib/nvcc_glibc_throw.sh`:** when the header probe fails with `unsupported GNU version`, setup fails with that reason and does not write the rsqrt header repair, which cannot fix a compiler mismatch.
- **Checks:** `scripts/self_check_generated_repo.sh` requires `scripts/lib/nvidia_cuda_toolkit.sh` and fails an NVIDIA `setup.sh` that installs `nvidia-cuda-toolkit` or does not call `install_nvidia_cuda_toolkit`. New `tests/test_nvidia_cuda_toolkit.py`. `docs/AI_AGENT_INSTRUCTIONS.md` adds clean-image acceptance before publishing an NVIDIA batch; `AGENTS.md` records the 24.04 toolkit rule.
- **Existing hosts and bundles:** a host that already has CUDA 12.6 gets 12.8 installed beside it and `/usr/local/cuda` moves to 12.8; repositories set up there earlier refuse to run (`nvcc release changed`) until their setup runs again. Published bundles (v1.0.17, v1.0.18) keep the old setup until republished. A host left broken by the old setup still needs its dpkg repaired (`apt-get remove --purge nvidia-cuda-toolkit libnvidia-compute-580 libnvidia-compute-535; dpkg --configure -a; apt-get -f install`) or a fresh image.

## 2026-10-20 — TEMPLATE_00_115: run_benchmark_suite.sh names profiles with --smoke, --baseline, --extended; -p removed

- **Why:** each workload's `run_benchmark.sh` and `show_metrics.sh` already take `--smoke`/`--baseline`/`--extended`; only the suite runner wanted `-p baseline`, and `-p` was hard to remember. Operators mixed the two forms.
- **`templates/suite-tools/scripts/run_benchmark_suite.sh`:** profiles are chosen with `--smoke`, `--baseline` and `--extended`, run in the order typed (`--baseline --extended` runs baseline, then extended). With none, the shared script runs all three; a bundle's copy runs smoke only, as before. `-p`/`--profiles` is removed: an old command stops with exit 2 and `-p was removed; name the profiles instead: --smoke, --baseline, --extended`. `--help` and its examples use the flags.
- **Breaking for operators:** commands, scripts and notes that use `-p` stop working once a host pulls a release built from this template. Bundles already on GitHub (v1.0.17, v1.0.18) keep `-p` until then.
- **Docs:** the generator README, `templates/README_TEMPLATE.md` (each workload's README), `templates/suite-tools/README.md` and `docs/github-profile-README.md` use the flags. The profile README's "Everything, all three profiles" row now gives `--smoke --baseline --extended`; a bare `./run_benchmark_suite.sh` in a bundle runs smoke only.
- **Publish (`bundle_suite_script`, `check_bundle_suite_script`, step 8, `bundle_readme()`):** the bundle copy's `--help` default line becomes `Default: --smoke   (full run: --smoke --baseline --extended)`; step 7 and step 8 check for that line. The bundle README's commands and options table use the flags.
- **Checks:** new tests: the flags choose the profiles (and the default), run in the order typed, and `-p`/`--profiles` is refused with the pointer to the flags; the bundle edits of the suite script are run on the real script for all four platforms (before, a missed sed was only caught at publish step 7). README and suite tests updated; all test files pass.

## 2026-10-20 — 3xx: why 26.04 still restarts; no unload of a half-started amdgpu; README back to "restarts once"

- **Finding (TEMPLATE_00_114 batch, Project392):** 301 still restarted. The previous boot's kernel log shows why: the fresh Ubuntu 26.04 image (kernel 7.0.0-31) boots without the MI300X firmware (`Direct firmware load for amdgpu/psp_13_0_6_ta.bin`, `gc_9_4_3_rlc.bin`, `sdma_4_4_2.bin`, `vcn_4_0_3.bin` failed; `Fatal error during GPU init`; `Doesn't get msg:1 from pf`). During 301's setup, `modprobe -r` of that half-started driver crashed in the kernel (`UBSAN: invalid-load` in `kfd_device.c`, fault in `amdgpu_fence_driver_sw_fini`), the 180 s deadline expired, and setup rebooted. The Ubuntu 24.04 image (kernel 6.8.0-142) starts the GPU at boot, so its in-place reload works. The console release added earlier today only helps a healthy driver; it is kept but does not apply here. One restart is required on a fresh 26.04 image; a snapshot taken after the first install avoids it on later VMs.
- **`scripts/lib/amdgpu_reload.sh` 1.2.0:** when amdgpu is loaded but has fewer KFD compute nodes than AMD GPUs on the PCI bus (the driver never started the GPU), the unload is skipped and setup goes straight to its single restart: no kernel crash and no 3-minute wait. The last reason the reload was refused is kept in `AMDGPU_RELOAD_REASON`.
- **`scripts/templates/setup_rocm_reboot_skeleton.sh`:** the `install_status.txt` phase line now includes that reason, for example `amdgpu could not be reloaded in place (amdgpu is loaded but started only 0 of 1 AMD GPU(s) at boot ...)`. Before, the reason only went to the screen, and generation discards successful remote output.
- **AMD 26.04 bundle README (`bundle_readme()`):** back to "The machine restarts once", now with the reason (the image cannot start the MI300X until ROCm's firmware is installed). "Before you start" says the first run restarts the machine once. The "If the machine restarts" wording from earlier today is withdrawn.
- **Checks:** new `test_half_started_driver_is_not_unloaded` (no `modprobe` call, reason kept, console untouched); the reload test fixture now gives a healthy driver one KFD node per GPU; README test updated; all test files pass.

## 2026-10-20 — 3xx: release the framebuffer console so amdgpu reloads without a reboot

- **Cause found on the Ubuntu 26.04 MI300X VM:** setup's in-place driver reload logged `modprobe -r amdgpu failed (rc=137); rebooting instead.` rc=137 is setup's own 180 s deadline: the unload never finished. Nothing held the driver (`refcnt` 0, no process on `/dev/kfd` or `/dev/dri/*`, no GPU service). The text console was bound to a framebuffer (`vtcon0: (M) frame buffer device`). After `echo 0 > /sys/class/vtconsole/vtcon0/bind`, the same `modprobe -r amdgpu` finished in 0.48 s.
- **`scripts/lib/amdgpu_reload.sh` 1.1.0:** before `modprobe -r amdgpu`, every bound framebuffer console is unbound (the console falls back to the dummy device). They are bound again after the reload, whether it succeeded or failed. Nothing changes when amdgpu is in use (the reload is skipped as before) or when no framebuffer console is bound. If the reload still fails, setup reboots once, exactly as before.
- **Expected effect:** 301–332 on Ubuntu 26.04 install without the restart. 24.04 already reloaded in place; the change is harmless there.
- **AMD 26.04 bundle README (`bundle_readme()`):** "The machine restarts once" becomes "If the machine restarts": setup reloads the driver in place and restarts only if the reload cannot be verified. The restart sample and the log-in-again steps stay, as the fallback. "Before you start" says the first run *may* restart the machine once, as for 24.04.
- **Checks:** three new tests in `tests/test_amdgpu_reload.py` (the console is released during the unload and bound again; bound again after a failed unload; untouched when amdgpu is in use); all test files pass; shellcheck passes. Not yet run on a VM.

## 2026-10-20 — Publish: complete bundle .gitmodules entries, and test every bundle

- **What happened in v1.0.17:** `bundle-nvidia-ubuntu-2604` was published with a `.gitmodules` entry for 417 that had `path` but no `url`. Windows refused one write during `git submodule add` (`error: could not write config file .gitmodules: Permission denied`, after the path and before the url). The retry in `add_submodule` saw the path and the gitlink and counted the entry as done. A fresh lab install (`git clone --recurse-submodules`) stopped at `fatal: No url found for submodule path '417-gpu-bench-nvidia-gemm-cublas-micro-ubu2604' in .gitmodules`. Step 8 only cloned `bundle-amd-ubuntu-2404`, so the publish reported FINISHED. Repaired by hand on GitHub (url restored, bundle tag moved).
- **`add_submodule`:** an entry counts as done only with both `path` and `url`.
- **Step 7:** before each bundle commit, restores any missing `url` (always `../<workload>.git`) and stops unless `.gitmodules` has exactly one complete entry per workload.
- **Step 8:** clones all four bundles from GitHub at the release tag (it cloned only AMD 24.04) and checks each one: suite scripts executable, no `run.sh`, no `branch =` lines, smoke default, the README's scripts present, and every workload `ready`.
- **Checks:** new `tests/test_publish_gitmodules.py` (missing url restored, wrong entry count stops, `add_submodule` requires the url, step 8 covers all four bundles); all test files pass; shellcheck and ruff pass.

## 2026-10-20 — TEMPLATE_00_114: runtime retune from the v1.0.17 baselines (Project385–388)

TEMPLATE_00_114 starts as a copy of TEMPLATE_00_113 (2026-10-20). Workbook changes only (`Parameters_SmokeBaselineExtend`, then `sync_matrix_profile_commands.py`; 9 command cells):

| Workload | Profile | Setting | Old → new | Measured | Expected |
|---|---|---|---|---|---|
| 230 | baseline | `output_len` | 1650 → 1200 | 5:17 cold at 1650; 1:50 warm at 800 | ~4:50 cold, ~2:15 warm |
| 231 | baseline | `output_len` | 3250 → 1350 | 5:14 at 3250 (8 × 3378 tokens overflowed the 16,384-token KV cache: 3 of 8 requests waited 22 s, TTFT p50 2,320 ms); 1:40 warm at 1350, TTFT p50 78 ms | ~4:05 cold |
| 231 | extended | `output_len`, `num_prompts` | 7000 → 3900, 48 → 144 | 3:59 warm at 3900 / 48 (TTFT p50 76 ms) | ~9:40 warm, ~12:10 cold |
| 431 | extended | `output_len`, `num_prompts` | 7000 → 3900, 48 → 112 | 5:42 warm at 3900 / 48 (TTFT p50 71 ms); 112 prompts also gives the 100 samples p99 needs | ~11:10 warm, ~12:45 cold |
| 207 | baseline | `num_iterations` | 23280 → 18600 | 4:24, 5:19, 5:37, 4:47 | slowest ~4:30 |
| 232 | baseline / extended | `query_count` | 13 → 70 / 40 → 220 | 0:27 / 1:35 (2.5 s per query); 0:48 on the slower 2xx host | ~3:00–4:20 / ~9:00–13:30 |
| 432 | baseline / extended | `query_count` | 13 → 45 / 40 → 140 | 0:52 / 3:10 (5.1 s per query) | ~3:50 / ~11:55 |

- **Cold and warm SGLang on the NVIDIA 24.04 VM:** the first server start on a VM captures prefill CUDA graphs for 117–164 s; later starts reuse `/root/.cache/sglang` (14–17 s). Baselines are sized so the cold first run (the one a fresh install's first baseline gets) stays under 5:00; warm repeats run shorter.
- **Not changed: 223.** Its 6:01 baseline (3:18 the day before, same settings) came from a slower 2xx host: the CPU-sensitive results on host `3e563c` were 27–46% lower than on `3c30b2` (207 STREAM, 208 iperf3, 222/223 small-batch inference), while GPU-bound results (215, 217–219, 226–229) matched. Recheck after the VM refresh.
- **Checks:** all 28 test files pass; `generate_workload_parameters.py --check` and `generate_show_metrics.py` pass; 207, 230, 231, 232, 431 and 432 generated locally with the new values and self-checked (only the expected "No benchmark run artifact directory exists").

## 2026-10-20 — Batch repairs from Project385–388 brought into the template; publish retry; 3xx README fix

The four TEMPLATE_00_113 batches (Project385–388) logged their generator repairs in `results/generator_repairs.md`. They are reconciled here.

- **Remote self-check (`scripts/create_one_workload.py`):** the 2026-10-19 change that left the nested `*_copy/` folder out of the copy sent to the VM is reversed. `self_check_generated_repo.sh` on the VM requires that copy until `template_copy_removed_at` is recorded, so x01–x03 (x01–x04 on 4xx) passed smoke and then failed self-check in every batch (12 retries, about 33 minutes). The four agents repaired it four ways; this keeps the 1xx repair (send the copy again), which is the generator in the v1.0.17 publish run folder. `self_check_generated_repo.sh` is unchanged, with no host exception. Only the copy rule changed; `__pycache__` is still left out and the CR strip still touches only files with a CR.
- **Reboot resume (`create_one_workload.py`, from the 3xx batch):** after the ROCm reboot, the resume service can still be inside `setup.sh`. The resume path now waits for it (up to an hour) and then continues into smoke, instead of failing with "setup.sh already running" (301). A first run still refuses to start a second `setup.sh`.
- **Generation times (`create_one_workload.py`, from the 4xx batch):** `results/generation_manifest.json` in each repository gets the same start, finish and duration as `GENERATION_REPORT.md`. Before, it kept the initializer's times (duration 0) in every bundle except where an agent fixed it by hand.
- **Publish retry (`scripts/publish_benchmarks_to_github.sh`):** 404 and 405 stopped step 3 of the v1.0.17 publish with Git Bash process errors (`fork: retry: Resource temporarily unavailable`, `Bad address`, `Win32 error 299`), which say nothing about the workload. When a workload's log shows one of these, step 3 deletes its half-prepared copy, copies it fresh from the run folder and tries once more; step 2 (dry run) simply tries again. A failed check is never retried, so a fix made by hand in the publish tree is not overwritten. If the retry also fails, the message says it is a Windows/Git Bash problem and what to do.
- **3xx bundle README (`bundle_readme()`):** `` `--show-output` `` inside a double-quoted bash string ran as a command, so the AMD 26.04 README read "With , the output ends like this". Escaped. `tests/test_bundle_readme_tools.py` now fails on any stderr from rendering (which is how bash reports this) and checks the sentence.
- **Checks:** `tests/test_batch_generation_tooling.py` (resume wait, first-run refusal, manifest times, the copy kept in the archive, self-check without a host exception) and new `tests/test_publish_windows_retry.py` (a fork error is retried from a fresh copy; a failed check is not); all 28 test files pass; ruff and shellcheck pass; 8 workloads across the four series generated and self-checked locally, each with a real generation duration.

## 2026-10-20 — From the v1.0.16 overnight runs (Project380–383): warm-up, AMD SGLang concurrency, one-GPU NCCL, runtime retune

The four overnight ledgers (1,025 runs, TEMPLATE_00_112) had no failures and no unexpected `na`. Four changes:

- **x30/x31 warm-up (`sglang-prompt-response-*` `prompt_response_client.py`, `sglang-serving-*` `bench_serving.py`):** the first request after the server reported ready waited 94–136 s for one-time kernel compilation, and it was averaged in: 130/330/430 baseline published TTFT 17,048 / 16,440 / 11,826 ms against ~40–50 ms for every later request, with end-to-end inflated the same way; the 131/331 baseline first wave carried ~110 s. Each client now sends untimed warm-up requests first (x30: one, with a prompt that shares no words with the timed prompts so the cache hit rate is unchanged; x31: one per concurrent slot). `--warmup-requests 0` disables it. The compilation still costs time on a first run; it is no longer in the metrics.
- **131/331 server concurrency (`sglang-serving-amd` / `-nvidia` `run_benchmark.sh`):** `max_running_requests` defaulted to 2 when the workbook row has none (131/331), while the client sent 8, so requests were served in pairs and TTFT p50 was 89 s (131) / 82 s (331) of queue wait (NVIDIA 231 sets 8 and measured 787 ms). The default is now `max_concurrency`.
- **x16 with one GPU (`nccl-bandwidth-nvidia`):** after the first round on one GPU every metric is `na (requires at least two GPUs)`, so the remaining rounds are skipped (216/416 extended took 17:20/21:00, baseline 6:32/7:44, for the same `na`). RCCL (116/316) runs once per collective already and is unchanged.
- **Runtime retune (`Parameters_SmokeBaselineExtend`, then `sync_matrix_profile_commands.py`; 14 command cells):** sized from the per-request times in each run folder (timed waves × time per wave, plus the measured fixed start-up) to land near 4:00 baseline / 12:00 extended. One run each, so these are first estimates.

| Workload | Profile | Measured | Setting | Old → new |
|---|---|---|---|---|
| 228 | extended | 17:35 | `output_len` | 35700 → 23300 |
| 229 | extended | 17:05 | `output_len` | 38100 → 26000 |
| 428 | extended | 17:26 | `output_len` | 27500 → 18300 |
| 429 | extended | 19:03 | `output_len` | 29100 → 17600 |
| 230 | baseline / extended | 5:56 / 15:24 | `output_len` | 3870 → 1650 / 15890 → 12000 |
| 430 | baseline | 6:33 | `output_len` | 2400 → 930 (start-up plus first compilation is ~3.6 min of a first run) |
| 431 | baseline | 5:58 | `output_len` | 3250 → 1350 |
| 427 | extended | 15:04 | `num_prompts` | 768 → 592 |
| 413 | extended | 15:12 | `num_iterations` | 1240 → 980 |
| 131, 331 | baseline | 5:51, 5:34 | `output_len` | 840 → 1400 (estimate: concurrency is now 8, not 2) |
| 131, 331 | extended | 12:55, 11:59 | `output_len`, `num_prompts` | 1700 → 3900, 48 → 56 (estimate; 8 × (128 + 3900) tokens fits `max_total_tokens` 32768) |

- **Not changed:** 207/209 baseline. Each had one run over 5:00 (5:19, 6:09) and one well under (4:24, 3:23) with the same settings; in the slow 209 run every latency was 1.6–2× higher (L1 2.64 ns vs 1.65 ns), so the host itself was slow at that time.
- **Checks:** new tests in `tests/test_sglang_stub_clients.py` (warm-up, untimed, no shared prompt words) and `tests/test_metric_fixes_20261019.py` (server concurrency default; one-GPU NCCL stops after round 1 with a stand-in `nccl_bw`); all test files pass; ruff passes; `generate_workload_parameters.py --check` passes; the 16 affected workloads generated locally and self-checked (only the expected "No benchmark run artifact directory exists").

## 2026-10-19 — Bundle README "Getting started": what success looks like

From the technician review of the v1.0.16 AMD 24.04 bundle README (`bundle_readme()` in `scripts/publish_benchmarks_to_github.sh`).

- **Success samples:** steps 1 and 2 end with the suite's closing summary (`SUMMARY: 1 of 1 …` and `SUMMARY: 3 of 3 …`) in fenced `text` blocks, so the `=====` rules do not render as Markdown headings. The host name in the log path is `<host>`. A lead paragraph says times and names differ, `0 failed` is what matters, and failures are listed under `Failed runs:` with the log file on the last line.
- **Step 2:** two commands, `--show-output` (shows progress while the stack installs) and quiet (prints nothing for 5 to 20 minutes), with the `tail -f …/install_status.txt` tip for quiet mode. "5 to 20 minutes" everywhere.
- **Restart, by platform:** AMD 24.04 "If the machine restarts" (may restart once); AMD 26.04 "The machine restarts once", with the last lines before the connection closes (`[WARN] Setup is awaiting reboot-resume completion…`, `Connection to <your-machine-address> closed by remote host.`) and the post-restart 3-of-3 sample; NVIDIA: setup installs CUDA only and never restarts. The restart steps sit inside step 2, before its success sample.
- **NVIDIA "Before you start":** the NVIDIA driver must already be installed (`nvidia-smi` lists the GPUs); setup installs CUDA, not the driver (`setup_nvidia_skeleton.sh` only verifies `nvidia-smi`). The stack name is now "CUDA" instead of "the NVIDIA driver and CUDA".
- **Steps 3 and 4:** "Smoke is a wiring check, not a measurement" (adds that the AI benchmarks download models on their first smoke run); "Run one benchmark" is its own step. Step 1 points to `./show_metrics.sh x07`.
- **Checks:** new `test_getting_started_shows_success_and_restart` in `tests/test_bundle_readme_tools.py` renders all four READMEs; all test files pass.

## 2026-10-19 — Metric fixes from the v1.0.16 review (204/404, x15, 203/403, 202/402, 201/401, 226/426)

- **204/404 ECC counts (`sdc-ecc-nvidia`):** with ECC disabled, `nvidia-smi -q -d ECC` prints every counter as `N/A`, so the integer sum was 0 and the workload published "0 errors" for a check that measured nothing. When no counter is a number, all ECC fields are `na (expected: ECC disabled)` (or `na (expected: nvidia-smi reports no ECC counters)` when the mode line is missing too). The before/after `nvidia-smi` text is saved as `ecc_before.txt` / `ecc_after.txt`.
- **x15 BabelStream / shared GPU lookup (`scripts/metric_contract.py`):** `lookup_device` recognizes the SXM name `NVIDIA H100 80GB HBM3` (no form word). New `detect_gpu_name()` (nvidia-smi, `amd-smi static` `MARKET_NAME`, rocminfo) is used where `summary.json` has no GPU name: `print_metric_summary.py`, the runtime ledger (`update_runtime_ledger.py` now passes its detected GPU), and the AMD BabelStream collector's `peak_percent` (it called `lookup_device("")`, so it was always blank). The smoke `metrics_summary.txt` already showed `(cache-resident at smoke size)` through the generic 50 MiB fallback; the ledger did not, and now adds a note such as `cache-resident at smoke size: 24 MiB working set is under 4x the 256 MiB cache (MI300X)`. The note goes in `notes`, not `metric_N_def`, so `show_metrics.sh` still finds each key in the parentheses.
- **203/403 throttle events (`system-stress-nvidia`):** every sample carries the run's total `thermal_throttle_event_count`; the summary averaged running totals, so a late event showed as a fraction.
- **202/402 Xid count (`gpu-health-nvidia`):** counts only `NVRM: Xid` lines, not every "xid" word in `dmesg`. When `dmesg` cannot be read (a container), the metric is `na (expected: dmesg not readable)` instead of 0.
- **201/401 (`system-config-nvidia`):** #1 now reads installed packages (`dpkg-query` status `install ok installed`): `cuda-toolkit` is an installed `cuda-toolkit*` / `cuda-nvcc-*` / `nvidia-cuda-toolkit` package with the workbook CUDA major; `nvidia-smi` is the dpkg package that owns the binary at or above the workbook driver (a host-mounted binary that runs counts); any other name must be installed. Findings are saved to `package_check.txt`. #3 driver compliance is now the share of the three driver components (kernel module, nvidia-smi/NVML, libcuda) at or above the workbook driver; agreement between them stays in #2. With the stacks on the v1.0.16 VMs (CUDA 12.6 vs workbook 12.8 on 24.04, 13.3 vs 13.3 on 26.04, driver 580+) both still read 0 and 100.
- **226/426 peak HBM fallback (`jax-xla-nvidia`, same function in `jax-xla-amd`):** the `nvidia-smi` fallback converts MiB to decimal GB (`× 1024² / 1e9`), matching the JAX path, instead of dividing by 1024 (GiB under a GB label).
- **Checks:** new `tests/test_metric_fixes_20261019.py`; `test_metric_feedback_updates.py` updated for the package check; all 27 test files pass; ruff (CI config) passes. Workloads 115, 126, 201–204, 215, 226, 301, 315, 401–404, 415, 426 generated locally and self-checked (only the expected "No benchmark run artifact directory exists").

## 2026-10-19 — Batch-generation fixes from the TEMPLATE_00_112 runs

- **ECC (203/403):** the `system-stress-nvidia` collector already carries the 403 fix (`na (expected: ECC disabled)`); it is byte-identical to the 203 and 403 repositories that were published in v1.0.16.
- **Generator repair log:** new `scripts/log_generator_repair.py` appends `UTC | workload | file | reason` to `results/generator_repairs.md` in the generator (ignored by git). `AGENTS.md`, `docs/AI_AGENT_INSTRUCTIONS.md` (rule 13) and `.cursor/rules/generate-workloads.mdc` require a line for every generator file changed during a batch. `scripts/run_from_prompt.py` ends its summary with the repairs added during that batch, or `none`.
- **SGLang clients against the stub:** new `tests/test_sglang_stub_clients.py` starts `tiny_sglang_server.py` on a free local port and runs `prompt_response_client.py` (x30) and `bench_serving.py` (x31), AMD and NVIDIA, then checks `raw_results.csv`: rows, `status=stub`, `server_identity`, and the stub na values. It found that `bench_serving.py` detected the stub only when `BENCHMARK_SERVER_KIND=stub` was exported (it joined bare `stub` words, which `is_standin_text` does not match). It now labels each value `server_identity=stub`. Smoke on the VM was unaffected because `run_benchmark.sh` exports that variable.
- **SDXL prefetch (x24):** `install_sdxl_python.sh` (AMD and NVIDIA) runs each download attempt under `timeout` (`SDXL_PREFETCH_TIMEOUT_SEC`, default 1800 s), fails a stalled read after `HF_HUB_DOWNLOAD_TIMEOUT` (default 60 s), and retries once (`SDXL_PREFETCH_ATTEMPTS`, default 2). Partial `*.incomplete` files are kept and resumed; the script reports how much was kept. Smoke still prefetches.
- **One start command:** `MSYS_NO_PATHCONV=1 python3 scripts/run_from_prompt.py --prompt-file ../AI_AGENT_PROMPT_SUBMITTED_<WORKLOADS>_<UTC_TIMESTAMP>.md`, from the generator directory, in `AGENTS.md`, `docs/AI_AGENT_INSTRUCTIONS.md`, `docs/generation-workflow.md` and the Cursor rule. `scripts/generation_host_preflight.py` prints it, with the full path of the interpreter it ran under, when it fails (and on success when given `--prompt-file`).
- **Every attempt kept:** `create_one_workload.py` `record()` keeps `attempts` (status, return code, start, end, total, reason) and `attempt_count` per workload; an older entry without `attempts` becomes the first attempt. `run_from_prompt.py` prints a status/attempts table and both **Successful time** and **Time including failed attempts**, and writes `generation_successful_seconds` and `generation_seconds_including_failed_attempts` to `batch_generation_manifest.json`.
- **Expected na guidance:** `AGENTS.md`, the instructions (rule 14), the Cursor rule and the `classify_na` docstring say a collector reports a counter the host does not have as `na (expected: <reason>)`; do not add new `classify_na` matches. `classify_na` is unchanged.
- **Remote copy:** the nested `*_copy/` folder and `__pycache__` are left out of the tar sent to the VM (both full and reuse copies). The remote CR strip runs `sed -i` only on files that contain a CR, so unchanged files keep their timestamps.
- **No bytecode:** `run_from_prompt.py` runs its children with `PYTHONDONTWRITEBYTECODE=1` (the remote validation script exports it too) and, at the end of the batch, removes `__pycache__`, `.pytest_cache`, `.ruff_cache` and `.mypy_cache` from the generator and the generated repositories (never `.venv` or `.cache`). A stray `implementation_components/sglang-prompt-response-nvidia/files/scripts/__pycache__` was moved out of the generator.
- **Checks:** new `tests/test_batch_generation_tooling.py` (14 tests) and `tests/test_sglang_stub_clients.py` (3 tests); all 26 test files pass; ruff (CI config) passes; `verify_generation_workflow.py` passes. All 128 workloads generated locally through `run_from_prompt.py` (four batches) and self-checked: the only failure is the expected "No benchmark run artifact directory exists" (no benchmark run locally).

## 2026-10-19 — 203/403: ECC disabled is an expected na

- **`implementation_components/system-stress-nvidia/files/scripts/collect_workload.py`:** when `nvidia-smi` reports ECC as `[N/A]` / not supported on every GPU (ECC disabled), the ECC metric is `na (expected: ECC disabled)` instead of a blank that failed validation. Fixed in workload 403 by the 401–432 generation session (its H100 has ECC off); brought into the generator and, before publishing v1.0.16, into workload 203 (collector plus the `results/overlay_lock.json` checksum). 203 passed `check_github_publish_ready.sh --published` with it; the identical code passed smoke on 403.

## 2026-10-19 — Fixes made during the TEMPLATE_00_112 generation runs (recorded afterwards)

Made in the publish run folder's generator copy at about 12:30 local time while generating 101–432 from TEMPLATE_00_112; brought into TEMPLATE_00_113 so the next generation keeps them.

- **`implementation_components/sglang-prompt-response-amd` / `-nvidia` `prompt_response_client.py`, `sglang-serving-amd` / `-nvidia` `bench_serving.py`:** the CSV header and rows include `server_identity`; without it x30/x31 crashed while writing results.
- **`implementation_components/linpack-rochpl-amd/files/scripts/collect_workload.py`:** GPU name probe tries `amd-smi static --asic` and `rocminfo` (ROCm), not only `nvidia-smi`, with a 20 s timeout, and accepts only text that names a GPU (an MI300X VF reports "AMD Instinct MI300X VF").
- **`implementation_components/hipmemcpy-bandwidth-amd/files/scripts/parse_results.py`:** `add_h2d_headline` publishes the numbered H2D metrics: `bandwidth_gbps` at the largest size, `latency_us` at the smallest, `headline_transfer_bytes` and `headline_point`.
- **`scripts/materialize_generated_harness.py`:** `summary.json` records the profile, and the ledger falls back to it when `BENCHMARK_PROFILE` is not set.
- **`scripts/metric_contract.py`:** `na (LLC load counters unavailable)` (x13 `l3_miss_rate`) is an expected na; new test in `tests/test_metric_renames_20261018.py`.
- **Checks:** all 24 test files pass (252 tests); `verify_generation_workflow.py` passes.

## 2026-10-19 — One publish script: the manual variant, named `publish_benchmarks_to_github.sh`

- **`scripts/publish_benchmarks_to_github.sh`:** now the former `publish_benchmarks_to_github_manual.sh` (renamed; `_manual.sh` removed). It has no source folders built in: the run folder is filled by hand and step 0 only checks it. The variant that copied workloads and the generator in from `WORKLOAD_SOURCES` / `GENERATOR_SOURCE` (still pointing at Project341–345) is removed. Header, `--help` example and `RUN_FOLDER_NAME` show the layout in use: the script in `Publishing\`, run as `./publish_benchmarks_to_github.sh 20261019_02/src_380_381_382_383`.
- **`README.md` (Commands):** describes the hand-filled run folder and that command.
- **`tests/test_bundle_readme_tools.py`, `test_run_benchmark_suite_list.py`:** check the one script. These and `test_operator_tools`, `test_readme_bundle_sections`, `test_generation_creation_fixes`, and `verify_generation_workflow.py` pass.

## 2026-10-19 — x11: a missing kernel-matched perf is an expected na; setup warns instead of stopping

Supersedes two points of the earlier 2026-10-19 entry "111/211/311/411: a missing kernel-matched perf stops setup".

- **Why:** on the NVIDIA Ubuntu 26.04 VM the workload runs in a container on the host's `6.8.0-136-generic` kernel, and the 26.04 archive has no `linux-tools` for it, so no correct `perf` can come from apt. Even with one installed by hand, that container cannot count (`perf_event_paranoid=4`, read-only `/proc/sys`, no `CAP_PERFMON`). Stopping setup made 411 fail on a host that can never produce counters.
- **`scripts/templates/setup_cpu_system_skeleton.sh`, `setup_nvidia_skeleton.sh`:** `fail_missing_kernel_perf` → `warn_missing_kernel_perf`. When the kernel-matched `perf` is missing, setup logs a warning naming the two `linux-tools` packages to install for counters, then continues to `.setup_state`.
- **`implementation_components/linux-perf-pmu-amd` / `-nvidia` `collect_workload.py`:** the four PMU metrics are `na (expected: perf not installed for kernel <release>)`, which `classify_na` treats as expected (its `na (expected:` rule; `classify_na` itself unchanged). The workload passes with empty counters, as 211 does when PMU access is denied. Context switches per second is still measured (getrusage).
- **Where perf exists** (a normal 24.04 or 26.04 machine running its own kernel), nothing changes: setup installs `linux-tools-$(uname -r)` and the counters are measured.
- **Tests:** `test_linux_perf_pmu.test_perf_missing` expects the new reason; `test_linux_perf_pmu`, `test_amdgpu_reload`, `test_nvidia_build_contracts`, `test_deferred_reboot`, `test_generation_checks`, `test_metric_feedback_updates` pass.

## 2026-10-19 — Publish scripts: bundle README and suite copy from the lab-technician review

`scripts/publish_benchmarks_to_github_manual.sh` is now the script that published v1.0.15 (from `Publishing\publish_benchmarks_to_github.sh`), plus the README line below; `scripts/publish_benchmarks_to_github.sh` carries the same changes. Both scripts' `bundle_readme()`, `bundle_suite_script()`, `add_submodule()` and steps 7–8 are identical.

- **`.gitmodules`:** no `branch = main` (it let `git submodule update --remote` leave the pinned release); existing bundles have the line removed in step 7.
- **Bundle copy of `run_benchmark_suite.sh`:** runs smoke only when no `-p` is given; `--help` examples and the bad-number message use the bundle's own workload numbers. Step 7 stops if these edits did not apply.
- **Bundle README:** Getting started begins with x07 (STREAM, CPU only, no GPU install), then x01, x02, x14; the GPU command says the first run is quiet for 5–20 minutes while it installs and how to watch it (`--show-output` or `install_status.txt`); smoke is a wiring check; restart steps; results that are expected to be `na`; full run is `-p smoke,baseline,extended`; Hugging Face range x23–x32; `git describe --tags`; do not use `--remote`; `show_metrics.sh` examples use x07.
- **Step 8:** the test clone also fails on a `branch` line, on a suite copy that does not default to smoke, and on any `./script.sh` the README names that is not in the bundle.
- **`tests/test_bundle_readme_tools.py`:** the results-section check expects `./show_metrics.sh 307 --baseline`.

## 2026-10-19 — Metric review, second pass: labels say what is measured; four measurement fixes

From the 32-workload metric review on the four FreshInstall VMs. Earlier ledgers are not comparable for the keys and labels below.

**Measurement fixes**
- **111/211/311/411 `linux-perf-pmu-amd` / `-nvidia` `collect_workload.py` (identical):** with several stress commands the parser averaged each ratio across commands (a 25–33% "branch misprediction rate" no command had). The collector now publishes one row whose ratios come from summed counts (total misses / total branches, total instructions / total cycles); a metric that is `na` on any command stays `na`. Per-command rows are in `per_command_results.csv` in the run directory. New test `test_combined_row_is_ratio_of_summed_counts`. Labels end in ", all commands combined".
- **123/323 `bert-inference-amd`, 125/325 `distilbert-amd`:** peak GPU memory reset after the model load. 123/323 published 485951488 bytes on every profile: the FP32 → FP16 conversion peak at load, not inference. The NVIDIA collectors already reset.
- **220/420 `linpack-hpl-nvidia`:** percent of peak divides by the FP64 tensor-core peak `nvhpl` prints as `peak_fp64_tflops` (cuSOLVER Dgetrf runs on tensor cores; the vector peak gave 101–102%). Key `percent_of_fp64_vector_peak` → `percent_of_fp64_tensor_peak`, label "Mean percent of FP64 tensor-core peak", override `BENCHMARK_PEAK_FP64_TFLOPS`. `nvhpl.cu` prints seconds with four decimals (two rounded smoke times to 0.08 s).
- **104/304 `sdc-ecc-amd`:** honors `memory_size` (it was raised to 5% of the GPU: `--memory-size 1` allocated about 10 GB on an MI300X) and emits `allocated_verification_buffer_gb` directly.
- **109/209/309/409 `multichase-numa-amd/collect_multichase.py`:** when `numactl --hardware` reports no NUMA but `/sys/devices/system/node` shows two or more nodes, or `--membind` is refused, remote DRAM is `na (expected: host has 2+ NUMA nodes but numactl cannot bind memory to a remote node here)` instead of "requires a second NUMA node".

**Key renames (collector and workbook)**
- 204/404 #4 `hbm3_coverage_gb` → `device_buffer_gib` (`sdc-ecc-nvidia`); test `test_metric_renames_20261018` updated.
- 132/232/332/432 #5 `embedding_throughput_docs_s` → `embedding_throughput_chunks_s`, label "Embedding throughput, chunks/s" (the value was always chunks/s).

**Label-only changes (keys unchanged)**
- x12 #3 "16 MB stride-128 sequential-read latency, cache- and prefetch-assisted, ns"; #4 "Single-thread memory read bandwidth, MB/s".
- 214/414 #7 "Pinned-over-pageable H2D bandwidth ratio".
- x27 #2 "Time To First Token p50, ms", #3 "TPOT p50, ms"; 228/229/428/429 #5 "End-to-end request latency p50, ms" (matching 128/129/328/329).
- 217/417 #5 "Relative L2 error of checked columns".
- x31 #1 "E2E latency p50, includes queue wait, ms", #2 "TTFT p50, includes queue wait, ms" (request rate inf with a small running-request limit, so most of the p50 is queueing).

**Run output**
- **`scripts/print_metric_summary.py`:** the bandwidth headline tag (for example `[at 1024 MiB H2D]`) is no longer appended to latency metrics, which are measured at the minimum transfer size.

**Workbook and checks:** `Workload_Definitions` Metrics (60 metric entries) and `Metric_Short_Labels` (60 rows) updated together; `show_metrics.sh` regenerated (`generate_show_metrics.py --check` passes). Sync, parameter and workflow checks pass; all 24 test files pass (251 tests). Backup: `../BenchmarkSpecDefinitions_before_20261019_metric_labels.xlsx`.

## 2026-10-19 — Run header: GPU stack lines match the vendor and say why a stack is missing

- **`scripts/print_run_metadata.sh`:** reads `GPU Vendor` and `Execution Domain` from `benchmark_specification.json`. AMD workloads print rocBLAS and ROCm versions as before; NVIDIA workloads now print `CUDA Version` (nvcc release) and `NVIDIA Driver Version` (nvidia-smi) instead of rocBLAS/ROCm lines that always read NOT FOUND. A missing stack prints `not installed (not used by this CPU benchmark)` for a `CPU / System` workload (technician test: 107 printed `ROCm Version: NOT FOUND` before any GPU benchmark had installed ROCm) and `NOT FOUND (GPU setup did not install it)` for a GPU workload. The `dmidecode` pipeline now ends in `|| true`: under `set -o pipefail` a host without dmidecode stopped the script after three lines.
- **`docs/run-output-contract.md`:** header block and missing-stack wording updated.
- **Checks:** `bash -n`; run against stand-in specifications for AMD/NVIDIA × CPU/GPU and with no specification.

## 2026-10-19 — Setup uses Ubuntu's Python even when the image activates a virtualenv

- **Problem (technician test, v1.0.15, NVIDIA 24.04 VM):** 207 setup failed on `apt-get install python3.11-venv`. The image ships no distro Python and activates `/root/.venv` (Python 3.11) in every shell (`VIRTUAL_ENV=/root/.venv`). Setup installed the distro Python only when no `python3` was on PATH, so it skipped that; it pins `BENCHMARK_PYTHON=/usr/bin/python3` only when that file exists, so the version probe ran on the venv's 3.11 and asked for a package Ubuntu does not publish. Rerunning worked, because the failed run had installed `python3` by then.
- **`scripts/templates/setup_cpu_system_skeleton.sh`, `setup_nvidia_skeleton.sh`, `setup_rocm_reboot_skeleton.sh`:** install the distro Python when `/usr/bin/python3` is missing (was: when no `python3` is on PATH). The ROCm skeleton now also pins `BENCHMARK_PYTHON=/usr/bin/python3` when it is unset, as the other two already did, so AMD GPU workloads on such an image do not build their `.venv` from the image's interpreter.
- **Checks:** `bash -n` on the three skeletons; `tests/test_amdgpu_reload`, `test_deferred_reboot`, `test_nvidia_build_contracts` pass.

## 2026-10-19 — Metric review: x03 AMD GPU load, x09 DRAM tier, x08 UDP cap

From the 32-workload `metrics_summary.txt` review on the four FreshInstall VMs. Only metrics that were wrong in every profile were changed; smoke-only artifacts are left (the bundle README calls smoke a wiring check).

- **103/303 `implementation_components/system-stress-amd/files/scripts/collect_workload.py`:** "Peak GPU junction temperature" and "Sustained GPU power" were idle readings (303 extended: 42 °C, 159.6 W over 580 s at 0% GPU utilization) under a 50% GPU-load request. Two causes: the load was `python -c "import torch ..."` and torch is not installed in the workload environment, so the child died with its stderr sent to /dev/null; and the utilization parser matched `gfx activity` while `amd-smi metric` prints `GFX_ACTIVITY` (underscore), so utilization always read 0. The load is now the repository-local `rocblas-bench` that setup already compiles (FP32 8192³ GEMMs, duty-cycled to `gpu_load_percent`, output in `gpu_load.log`), the parser also matches `gfx_activity`, and when the load never runs or activity never reaches 10% the two metrics are `na (GPU load did not run: <reason>)` (smoke: the `timed loop too short` form, which is an expected na). Component README updated. Tested locally with stand-in `rocblas-bench` / `amd-smi` (load runs: 58% mean for 50% requested; missing or failing `rocblas-bench`: na with the reason). Not yet run on an MI300X.
- **109/309 `Parameters_SmokeBaselineExtend` `working_set_size`:** baseline/extended `local_dram`/`remote_dram` 256 MiB → 1 GiB. On the MI300X VMs (Xeon Platinum 8568Y+, very large unified L3) the 256 MiB chase measured 44.6–46.5 ns, a cache latency published as local DRAM; the same code measures 118–148 ns at 256 MiB on the H100 hosts, so 209/409 are unchanged. `num_iterations` 2900000000/8800000000 → 1500000000/4500000000 to hold ~4 / ~11.5 minutes (estimate; per-iteration latency sum ~78 → ~150 ns).
- **108/208/308/408 UDP cap removed:** `bandwidth_limit` 10G → 0 in the workbook, and `DEFAULT_UDP_RATE` "10G" → "0" in `implementation_components/iperf3-amd` and `iperf3-nvidia` (`-b 0` is iperf3's unlimited rate). `udp_throughput_gbps` reported the cap (9.99 Gbit/s on every profile on MI300X while TCP loopback reached 55 Gbit/s). Packet loss is now measured at the unlimited send rate and will be higher than with the cap.
- **Not changed — 120/320 "rocSOLVER LU" labels are correct.** `bin/rochpl` is this component's own `src/rochpl.cpp`, which calls `rocsolver_dgetrf` + `rocsolver_dgetrs` and prints HPL-style output; it is not AMD's rocHPL. (One reviewer reading the binary name proposed renaming the metrics to rocHPL.)
- **Workbook:** `Workload_Definitions` command columns regenerated (`sync_matrix_profile_commands.py`, 16 cells). Backup before these edits: `../BenchmarkSpecDefinitions_before_20261019_metric_fixes.xlsx`.
- **Checks:** sync `--check`, `generate_workload_parameters.py --check`, `verify_generation_workflow.py` pass; `tests/test_generation_creation_fixes`, `test_metric_pair_parity`, `test_metric_renames_20261018`, `test_metric_feedback_updates`, `test_template_87_contracts`, `test_system_stress_nvidia` pass (92 tests).

## 2026-10-19 — 111/211/311/411: a missing kernel-matched perf stops setup; the PMU collector lowers perf_event_paranoid

Recorded after the fact; the change was made by a Cursor session at about 08:00 local time.

- **Problem:** on the Ubuntu 26.04 NVIDIA VM (kernel `6.8.0-136-generic`, whose 26.04 archive only has `linux-tools` for 7.0.0) setup warned and continued without `perf`. The collector then published the four PMU metrics as `na (perf not installed for kernel …)`, which `classify_na` treats as unexpected, so 411 failed validation on smoke, baseline and extended. 211 passed only because its host had perf and reported the expected `na (PMU access denied: perf_event_paranoid=4)`.
- **`scripts/templates/setup_cpu_system_skeleton.sh` and `setup_nvidia_skeleton.sh`:** new `kernel_perf_bin` uses the collector's rule (a kernel-matched `/usr/lib/linux-tools…/perf` over 10000 bytes, following the symlink with `stat -L`). When it is missing or its version text says `not found`, a workload whose perf is required exits before `.setup_state` with `fail_missing_kernel_perf`, which names `uname -r`, the OS version and the `linux-tools-<kernel>` packages to install; where perf is optional (`perf_is_optional`, e.g. 110's cache-miss counter) setup still warns and continues.
- **`implementation_components/linux-perf-pmu-amd` and `linux-perf-pmu-nvidia` `collect_workload.py`:** `_lower_perf_event_paranoid` drops `kernel.perf_event_paranoid` to 2 for the timed section and restores the previous value on exit, including a failed run. Where `/proc/sys` is read-only (containers without `CAP_PERFMON`) the write fails and the metrics stay the expected `na (PMU access denied: …)`.
- **`classify_na` unchanged:** a missing perf stays an unexpected `na`; a paranoid denial stays expected.
- **Operator note:** on a host like that VM, x11 setup now stops with the package names instead of passing setup and failing validation. Install the two `linux-tools-<kernel>` debs from the Ubuntu release that built the kernel (do not add that release's apt suite), then rerun.

## 2026-10-19 — Baseline and extended retimed toward 5 / 15 minutes

Targets: baseline under 5 minutes, extended under 15 minutes, aimed at about 4:00 and 12:00 for margin. Measured times come from `runtime_ledger_Aggregate_375_376_377_378_20261019a_845am.xlsx` (the four FreshInstall VMs: MI300X VF for 1xx/3xx, H100 NVL for 2xx, H100 PCIe for 4xx).

- **`BenchmarkSpecDefinitions.xlsx` `Parameters_SmokeBaselineExtend`:** 40 baseline/extended values changed (table below). Each cell was first checked against the value the ledger shows the run used; all matched. New value = old × (target − fixed start) / (measured − fixed start), where the fixed start is the workload's own smoke time (SGLang x30/x31, whose smoke is a stand-in: 60 s assumed) and the measured time is the slower run. Each row's notes cell has a `2026-10-19 GARY_LEDGER` entry with the numbers. Unconfirmed by a fresh run.
- **Not changed, first-run SGLang start:** 131, 230, 231 and 331 baseline went over 5:00 only on the first baseline after install (for example 230: 6:54, then 4:05); 431 has only its first run (6:06), about 3:17 once the cold start is removed. SGLang smoke is a stand-in, so the first baseline is the first real server start and pays a one-time cost of about 2½ minutes that fewer tokens cannot remove. 430 baseline, which had only that first run, was retimed from the first run minus the 2:49 measured on 230.
- **`Workload_Definitions` command columns:** regenerated with `scripts/sync_matrix_profile_commands.py` (46 stale cells: the 40 above plus 103/303 smoke/baseline/extended, whose display text still showed `--temp-threshold 75 --power-threshold 500`; the sheet already held 100 / 1000).
- **Checks:** `sync_matrix_profile_commands.py --check`, `generate_workload_parameters.py --check`, `verify_generation_workflow.py`, and `tests/test_generation_creation_fixes.py`, `test_metric_pair_parity.py`, `test_metric_renames_20261018.py` pass. The workbook before this change is `../BenchmarkSpecDefinitions_before_20261019_runtime_retune.xlsx` (outside the generator folder).

| Workload | Profile | Parameter | Old → new | Measured | Predicted |
|---|---|---|---|---|---|
| 120 | baseline | `num_iterations` | 6 → 5 | 5:24/4:19 | ~4:30 |
| 214 | baseline | `num_iterations` | 750 → 563 | 5:05/5:08 | ~3:59 |
| 216 | baseline | `num_iterations` | 295000 → 157000 | 7:18/7:30 | ~3:59 |
| 216 | extended | `num_iterations` | 620000 → 382000 | 19:28 | ~11:59 |
| 218 | baseline | `num_iterations` | 85000 → 64200 | 5:17/5:17 | ~4:00 |
| 218 | extended | `num_iterations` | 250000 → 194000 | 15:26 | ~11:59 |
| 219 | baseline | `num_iterations` | 1140000 → 501000 | 8:57/8:53 | ~3:59 |
| 219 | extended | `num_iterations` | 2750000 → 1390000 | 23:33 | ~11:57 |
| 222 | baseline | `num_iterations` | 13350 → 8030 | 6:24/6:33 | ~3:59 |
| 223 | baseline | `num_iterations` | 37100 → 27400 | 5:20/4:57 | ~4:00 |
| 228 | extended | `output_len` | 50800 → 35700 | 16:47 | ~12:00 |
| 229 | extended | `output_len` | 52600 → 38100 | 16:16 | ~11:59 |
| 320 | baseline | `num_iterations` | 6 → 5 | 5:05/4:25 | ~4:14 |
| 407 | baseline | `num_iterations` | 23280 → 14800 | 6:16/6:01 | ~3:59 |
| 413 | baseline | `num_iterations` | 880 → 617 | 4:44/5:42 | ~4:00 |
| 414 | baseline | `num_iterations` | 750 → 489 | 5:41/5:46 | ~3:59 |
| 414 | extended | `num_iterations` | 2200 → 1720 | 15:07 | ~11:58 |
| 415 | baseline | `num_iterations` | 30000 → 17600 | 6:48/6:48 | ~3:59 |
| 415 | extended | `num_iterations` | 35550 → 26500 | 16:05 | ~11:59 |
| 416 | baseline | `num_iterations` | 244000 → 113000 | 8:39/8:37 | ~4:00 |
| 416 | extended | `num_iterations` | 620000 → 319000 | 23:19 | ~11:59 |
| 418 | baseline | `num_iterations` | 85000 → 57600 | 5:51/5:52 | ~3:59 |
| 418 | extended | `num_iterations` | 250000 → 175000 | 17:06 | ~11:59 |
| 419 | baseline | `num_iterations` | 1140000 → 556000 | 8:04/8:03 | ~4:00 |
| 419 | extended | `num_iterations` | 2750000 → 1520000 | 21:38 | ~12:01 |
| 421 | baseline | `num_iterations` | 3100 → 2170 | 5:22/5:37 | ~4:00 |
| 421 | extended | `num_iterations` | 8800 → 6750 | 15:35 | ~12:00 |
| 422 | baseline | `num_iterations` | 13350 → 4420 | 11:44/11:29 | ~3:59 |
| 422 | extended | `num_iterations` | 16200 → 10500 | 18:28 | ~12:01 |
| 423 | baseline | `num_iterations` | 37100 → 15000 | 7:56/9:26 | ~4:00 |
| 423 | extended | `num_iterations` | 102000 → 56400 | 21:27 | ~12:00 |
| 424 | extended | `num_images` | 120 → 72 | 19:33 | ~11:57 |
| 425 | baseline | `num_iterations` | 4130 → 2880 | 5:20/5:35 | ~3:59 |
| 425 | extended | `num_iterations` | 12300 → 9420 | 15:34 | ~12:00 |
| 426 | extended | `num_iterations` | 760000 → 588000 | 15:24 | ~11:59 |
| 428 | extended | `output_len` | 50800 → 27500 | 21:34 | ~11:58 |
| 429 | baseline | `output_len` | 18600 → 12300 | 5:40 | ~4:00 |
| 429 | extended | `output_len` | 52600 → 29100 | 21:05 | ~11:59 |
| 430 | baseline | `output_len` | 3870 → 2400 | 8:39 | ~3:59 |
| 430 | extended | `output_len` | 15890 → 8100 | 22:34 | ~11:59 |

## 2026-10-18 — A locked overlay is a fingerprint, and a smoke failure is repaired in place

- **`results/component_leftover_work.md`, `AGENTS.md` §20.25, `implementation_components/README.md`, `docs/AI_AGENT_INSTRUCTIONS.md`, `docs/generation-workflow.md`, `docs/IMPLEMENTATION_COMPONENTS.md`, `docs/TEMPLATE_README.md`, `docs/repository-template.md`, and the failure-mode text in `scripts/fill_generated_docs.py`:** “do not rewrite” after init now means do not replace an overlay with a new collector. A smoke failure inside a locked file is fixed by writing the same bytes in the template source, the sibling, and that path’s `sha256` in `results/overlay_lock.json`, then `create_one_workload.py --validate-only`. `scripts/metric_contract.py` has no lock entry and is repaired in the generator copy and the sibling copy. `self_check_generated_repo.sh` and `smoke_check_generated_repo.sh` are unchanged: an unrecorded rewrite still fails, and a sibling that differs from the template still fails.

## 2026-10-18 — `run_benchmark_suite.sh` is installed at `/opt/benchmarks`

- **`scripts/create_one_workload.py`:** after a workload is copied onto the VM, `templates/suite-tools/scripts/run_benchmark_suite.sh` is installed at `/opt/benchmarks/run_benchmark_suite.sh` (LF, mode 755), beside the existing `show_metrics.sh` install. It is not placed inside the workload tree. Published bundles already ship this script.

## 2026-10-18 — Generation unblocked; checks fixed; 24.04/26.04 metric wording matches

- **Generation blocker — `scripts/self_check_generated_repo.sh`:** the ledger-column check expected the list from before `update_runtime_ledger.py` added `metrics_na_count`, `result_status` and `gpu_model_note` (2026-10-17), so every generated workload failed its self-check. The three columns are now expected. New `tests/test_self_check_ledger_columns.py` runs that embedded check against the real module.
- **`tests/test_amdgpu_reload.py`:** both ROCm installers must be LF (the test required CRLF for 26.04, which bash cannot run). Its newest-kernel check now tests behaviour (no `${newest}`, no `/lib/modules/` scan, no `linux-modules-extra` install) instead of a comment marker.
- **`scripts/lib/rocm_install_26_04.sh`:** removed the dead step-8 branch (it called `_rocm_install_linux_modules_extra`, which only the 24.04 file defines); 26.04 only logs that `linux-modules-extra` is folded into `linux-modules`.
- **`scripts/verify_generation_workflow.py`:** links in `templates/*_TEMPLATE.md` resolve in the generated-repo layout (generator root and `templates/workload/`), so `LICENSE` and `.github/workflows/*.yml` no longer fail. The whole check now passes, in about a second.
- **`scripts/generate_workload_parameters.py`:** an unused `Parameter_NN` slot (`-`) is no longer treated as a parameter (only `—` was skipped). The workbook is read once (the check took 2 min 22 s, now under 1 s). `--check` compares `config/workload_parameters.yaml` with the workbook. Parameters a description does not name are a `[WARN]` (descriptions say what the code does, and some leave out unused parameters); `--strict` makes them a failure. `config/workload_parameters.yaml` regenerated: 33 shared parameters it was missing.
- **`BenchmarkSpecDefinitions.xlsx` — 24.04/26.04 pairs now identical:** 117/217/317/417 "Achieved compute throughput, TFLOP/s (`achieved_compute_tflops`)" (exact 2·M·N·K FLOPs); 121/321 "Modeled training throughput, 3x forward FLOPs, TFLOP/s (`modeled_tflops`)" (321 named `achieved_TFLOPS`, which nothing writes), and their Output Fields, Raw Output Example and parser notes now name what the collector writes (`modeled_tflops`, `min_operand_traffic_gb_s`); 421 matches 221; 328 says p50 like 128; 409/410/412 drop the fixed "cache-resident below 4x LLC" text (the run-time annotation still applies); 132/232/332 say "E2E mean over queries" like 432. Metric_Short_Labels updated, `show_metrics.sh` regenerated. The `achieved_compute_tflops → modeled_tflops` alias is removed. New `tests/test_metric_pair_parity.py`.
- **Docs:** `docs/AI_AGENT_HANDOFF.md` describes `--check` and `--strict`.

## 2026-10-18 — Bundle README explains `show_metrics.sh` and `get_remote_info.sh`

- **`scripts/publish_benchmarks_to_github.sh` and `_manual.sh` (bundle README):** new "See your results" section after "Getting started" with `./show_metrics.sh NNN`, `--baseline` and `--help`; a `show_metrics.sh` row in the Results table; and a worked `get_remote_info.sh --host` example (clone `gpu-bench-suite`, where it writes `RUNTIME_LEDGERS/` and `DIRECTORIES/`, `--port` for a non-22 ssh port, and `show_metrics.sh --host`). Before, the bundle shipped `show_metrics.sh` without mentioning it and gave `get_remote_info.sh` one line.
- **`tests/test_bundle_readme_tools.py`:** new. Renders the bundle README with the real `bundle_readme()` for all four platforms and checks that it shows every script step 7 copies into the bundle, the `get_remote_info.sh --host` example, no unfilled `@...@` placeholder and no `./run.sh`.

## 2026-10-18 — Bundle `run.sh` folded into `run_benchmark_suite.sh`

`/opt/benchmarks` had both `run.sh` and `run_benchmark_suite.sh`, so `run<Tab>` did not complete. Everything `run.sh` did is now in the suite runner, and bundles no longer ship `run.sh`.

- **`templates/suite-tools/scripts/run_benchmark_suite.sh`:** new `-l, --list` prints every workload (folders and `.gitmodules` entries) as `ready` or `not fetched`, with a count and the `git submodule update` command when something is missing; exit 0 when all are ready, 1 otherwise; honours `-w` and `-d`; finds a bundle root even before any submodule is fetched. New `--show-output` also streams each run's output to the screen (it always goes to the log); the exit code is kept. `-w NNN` for a folder that is not fetched says so and how to fetch it. `-w` parsing moved into the main shell, so a bad value always stops the script.
- **`scripts/publish_benchmarks_to_github.sh` and `_manual.sh`:** step 7 no longer writes `run.sh` and removes it from existing bundle repositories (`git rm`); it stops if `run_benchmark_suite.sh` is missing (the bundle cannot list or run without it). It now also copies `show_metrics.sh` into every bundle, as the README already said. Step 8 checks the test clone with `./run_benchmark_suite.sh --list`, checks both scripts are executable, and fails if `run.sh` is still there. The bundle README uses `--list` and `-w NN -p smoke --show-output`, and its options table lists both.
- **Docs:** `templates/README_TEMPLATE.md` (every workload README: the bundle install chain now uses `--list`, which stops the chain when a workload is missing), `README.md`, `templates/suite-tools/README.md`, `docs/github-profile-README.md`.
- **Tests:** new `tests/test_run_benchmark_suite_list.py` (`--list` states, `.gitmodules`, `-w` filter, unfetched and missing workloads, `--show-output` on screen and in the log, exit code kept, `--help`; no `./run.sh` left in the publish scripts or READMEs). `tests/test_operator_tools.py` checks the bundle copies `show_metrics.sh`; it now passes.

## 2026-10-18 — `get_remote_info.sh` takes `--host` and `--port`

- **`templates/suite-tools/scripts/get_remote_info.sh`:** new `--host HOST`, `-p, --port PORT` and `--user USER` options, the same names `show_metrics.sh` uses: `./get_remote_info.sh --host 203.0.113.10 --port 39116`. The positional form `HOST [PORT]` still works. Every option that takes a value also accepts `--option=VALUE`. A host, port or user given twice with different values, a port outside 1-65535, a missing value, or an option followed by another option instead of its value is a usage error (exit 2) before any ssh connection. `--help` lists the connection options first.
- **Docs:** README.md, templates/README_TEMPLATE.md, templates/suite-tools/README.md and docs/github-profile-README.md show the `--host`/`--port` form.
- **`tests/test_get_remote_info_options.py`:** new. Runs the script against a stand-in `ssh` that records its arguments and refuses the connection: checks that every form reaches ssh as `-p PORT user@host`, and that bad input exits 2 without running ssh.

## 2026-10-18 — Metric keys and labels match what the collectors measure

Reviewed against the code. Old keys still resolve through `STORAGE_ALIASES`, so earlier `summary.json` files keep printing.

- **101/301 `system-config-amd`:** `kernel_driver_mismatch_count` → `kernel_release_mismatch_count` (it counts the kernel release only). Collector, `gate.json` thresholds, and the `kernel-*-mismatch-count` column maps in `materialize_generated_harness.py` and the 114/115 `parse_results.py`.
- **103/303 `system-stress-amd`:** `gpu_system_ecc_error_count` → `ras_uncorrectable_ecc_delta_count` (collector and `gate.json`). When amd-smi prints no throttle counter, `thermal_throttle_event_count` is `na (expected: throttle counter not exposed)` instead of blank, so the run publishes N/A-EXPECTED rather than INCOMPLETE. 203/403 keep `gpu_system_ecc_error_count`; 103/303 keep `peak_gpu_junction_temp_c` (amd-smi reads junction/hotspot).
- **104/304 `sdc-ecc-amd`:** `even_word_store_pass_rate` → `loop_verification_pass_pct` (percent of clean loops; even and odd indexes are checked).
- **109/309, 209/409:** label says `latency_ns_remote_dram` is na on a host with fewer than two NUMA nodes (the collector and `classify_na()` already did this).
- **116/316, 216/416:** all-reduce only, so `busbw_gb_s`, `algbw_gb_s`, `latency_us` → `allreduce_busbw_gb_s`, `allreduce_algbw_gb_s`, `allreduce_latency_at_min_bytes_us` in both vendors, labels say "na on single GPU". `classify_na()` also recognizes `allreduce` keys. `nccl_bw.cu` uses (n-1)/n busbw for all_gather/reduce_scatter and 1 for broadcast/reduce (the published all_reduce headline is unchanged). 216/416 baseline/extended `max_bytes` 16 MiB → 1 GiB. 116/316 Known Runtime Constraints corrected: `rccl_perf` is multi-rank; `num_gpus` is 1 in every profile, which is why the metrics are na.
- **120/320:** metric label stays "Mean rocSOLVER LU FP64". `bin/rochpl` is built from `src/rochpl.cpp` (`rocsolver_dgetrf`/`dgetrs`), not upstream rocHPL, so the collector's comments and log lines now say rocSOLVER LU.
- **203/403 `system-stress-nvidia`:** `peak_gpu_junction_temp_c` → `peak_gpu_temperature_c` (nvidia-smi `temperature.gpu` is the core sensor, not junction).
- **204/404 `sdc-ecc-nvidia`:** Metrics #4 key is `hbm3_coverage_gb` (the emitted key, GiB); `walking_1s_moving_inversion_pass_rate` → `fixed_pattern_fill_verify_pass_rate`.
- **218/418:** "Achieved convolution throughput, forward (`tflops_fwd`)" and "Minimum forward operand traffic (`min_operand_traffic_gb_s`)". The `tflops_fwd → modeled_tflops_fwd` alias is removed.
- **221:** "Modeled FP16 training throughput, 3x forward FLOPs (`fp16_tflops`)". The `fp16_tflops → modeled_fp16_tflops` alias is removed.
- **227/427 `vllm-kvcache-nvidia`:** `sustained_decode_throughput_under_cache_pressure_tokens_sec` → `decode_throughput_tokens_sec`, "Aggregate decode throughput".
- **`BenchmarkSpecDefinitions.xlsx`:** Metrics, Output Fields, Raw Output Example, parser notes, 216/416 run commands and parameters, and Metric_Short_Labels updated; `show_metrics.sh` regenerated.
- **`tests/test_metric_renames_20261018.py`:** new. Every renamed metric resolves from the workbook to the emitted key, old keys resolve through the aliases, gates use the new keys, the throttle na is expected, and the busbw factors and 1 GiB `max_bytes` are in place.

## 2026-10-18 — Reliable cleanup of generation copies; empty copy shells removed

Project370 (101–132) could not be copied to the publish folder: 103 still held its 454-file `ai-agent-gpu-benchmark-repo-generator_copy` (paths up to 286 characters), and 126, `.ai-agent-gpu-benchmark-repo-generator_109_*` and `_123_*` were left as empty folder skeletons by deletes that stopped partway.

- **`scripts/remove_template_copy.py` (1.1.0):** new `rmtree_reliable()` deletes a tree, keeps going past individual errors (read-only files, files briefly held on the Z: share or by antivirus, "directory not empty"), retries up to 5 times with a growing delay (0.5, 1, 2, 4 s), and confirms the path is gone; otherwise it prints a `[WARN]` naming the path. New `reliable_temp_dir()` is `tempfile.TemporaryDirectory` with that cleanup, and it reports a leftover instead of ignoring it.
- **Empty copy shells:** `remove_template_copy.py` now also removes a generator `*_copy` folder that holds no files (named `ai-agent-gpu-benchmark-repo-generator_copy` or `TEMPLATE_00_<n>_copy`), and the copy named in `results/generation_manifest.json` even after a partial delete removed its marker files. It records `template_copy_removed_at` as for a full copy. Other folders that merely end in `_copy`, and generator-named folders that still hold files but are not the manifest's copy, are left alone. Previously such shells got "No nested template copy found; nothing to remove".
- **`scripts/create_generated_repo.py` (1.5.0):** the discovery folder `.<generator>_<workload>_*` uses `reliable_temp_dir()` instead of `TemporaryDirectory(ignore_cleanup_errors=True)`, which silently left those folders in the project root. `--force` and the template-copy refresh delete with `rmtree_reliable()` and stop with a clear message if something is still in the way.
- **`tests/test_remove_template_copy.py`:** 8 new tests (empty shell, partial copy, unrelated folder kept, retry until gone, failure reported, missing path, temp folder removed, leftover reported).

## 2026-10-18 — Guarded rocBLAS `cd` (shellcheck SC2164 failed CI on push)

- **`scripts/lib/rocm_install_24_04.sh`, `scripts/lib/rocm_install_26_04.sh`:** `rocm_compile_rocblas_bench` now runs `cd "${ROCBLAS_SOURCE_DIR}" || _rocm_die "Cannot cd to ${ROCBLAS_SOURCE_DIR}"`. These libraries are sourced without `set -e`, so the bare `cd` was a shellcheck warning (SC2164), and the shared CI lint (`--severity=warning`) failed every one of the 128 workloads on push. A failed `cd` would also have run `./install.sh` from the wrong folder.
- **`tests/test_shell_cd_guarded.py`:** new. Fails when a `.sh` under `scripts/`, `templates/` or `implementation_components/` that does not run under `set -e` has a `cd` without `||`/`&&` (heredoc text is skipped). It needs no shellcheck install.
- **`scripts/smoke_check_generated_repo.sh`:** runs the same `shellcheck --severity=warning` command as the shared CI on the generated repository, and fails if it reports anything; prints a `[WARN]` and skips when shellcheck is not installed.

## 2026-10-18 — AMD system stress ceilings match MI300X operating range

- **103/303 `system-stress-amd`:** `sweep.temp_threshold` and `thresholds.peak_gpu_junction_temp_c_max` are 100. `sweep.power_threshold` and `thresholds.sustained_gpu_power_w_max` are 1000. Thermal-throttle and ECC maxima stay 0. The old 75 °C and 500 W ceilings failed a normal Instinct MI300X reading (junction on the 75 °C line, board power about 730 W). The gate in `implementation_components/system-stress-amd/gate.json` and the 103/303 rows on `Parameters_SmokeBaselineExtend` are the sources the next generation writes into `config/benchmark_config.yaml`.

## 2026-10-17 — NVIDIA values checked against Project365/367 runs

- **vLLM (227–229, 427–429):** `requirements.txt` and `setup.sh` pin `vllm==0.31.0`, the version every passing run installed (it pulls torch `2.13.0+cu130`).
- **`BenchmarkSpecDefinitions.xlsx`:** Container Base Image is the provider-supplied container on both Ubuntu releases (overlay root, no systemd; the generator builds no image). 2xx GPU Runtime is CUDA 12.6 (nvcc 12.6.85 preinstalled; setup installs 12.8 only when nvcc is missing); 4xx is CUDA 13.3 (nvcc 13.3.73). Driver is 580.159.04 on both, so `--nvidia-driver-version 580` is correct. vLLM rows record vLLM 0.31.0 and PyTorch 2.13.0+cu130.

## 2026-10-17 — NVIDIA spec corrections and ROCm 10.1 inventory package names

- **`BenchmarkSpecDefinitions.xlsx` (NVIDIA rows):** values now match the install scripts. 419 and 421–425: PyTorch `2.13.0+cu130` (was `2.7.1+cu128`, which has no Python 3.14 wheel); 421/422 torchvision `0.28.0+cu130`. 430/431: PyTorch `2.13.0+cu130`, torchvision `0.28.0+cu130`, `sglang-kernel==0.4.6.post1`. 227–229 and 427–429: PyTorch is whatever unpinned `pip install vllm` pulls. 232: torchvision `0.22.1+cu128`. g++ is the distro compiler (13.3.0 on 24.04, 15.2.0 on 26.04); 4xx CMake is 4.2.3. Container Base Image for 2xx is host-native (the generator has no container step). Label fixes: `N/A - g++ not used`, `N/A - cuBLAS not used`. 201/401 `nvidia_driver_version` and `cuda_version` are stored as text. Schema Last Updated is 2026-10-17 on every AMD and NVIDIA row.
- **`scripts/install_pytorch_nvidia.sh`, `rag-faiss-end2end-nvidia/files/scripts/install_rag_nvidia.sh`:** Ubuntu 24.04 torchvision pinned to `0.22.1+cu128` (it was unpinned).
- **`config/hw_sw_info_commands.xlsx`:** ROCm 7 package queries replaced with ROCm 10.1 names (`amdrocm-base10.1`, `amdrocm-dnn-host10.1`, `amdrocm-rccl-host10.1`, `amdrocm-blas10.1`, `amdrocm-solver-host10.1`); RVS is called from PATH; the installed-package list matches `amdrocm|amdgpu`. `scripts/collect_hw_sw_info.sh` regenerated.
- **`config/machines.yaml`:** `rocm_version` 10.1.0 (was 7.2.4).

## 2026-10-17 — amd-smi replaces rocm-smi (ROCm 10.x)

ROCm 10.x does not ship `rocm-smi`. Every AMD probe now uses `amd-smi`. Originals are in `../_backup_rocmsmi_20261017/`.

- **`system-config-amd` (101/301):** the `rocm-smi` probe is now `amd-smi version` (still seven probes; transcript `amd-smi-version.txt`). Each row has a new `rc` column with that probe's own exit code (127 = tool missing); `rc` is not a metric and is not gated. Firmware lookup no longer falls back to `rocm-smi`. Default `required_packages` is `amdrocm-base10.1,amdrocm-amdsmi10.1`; the old `rocm-core`/`rocm-smi` aliases still resolve. `component.json` verifies `amd-smi version` instead of `rocm-smi`.
- **`rocm-health-amd` (102/302), `system-stress-amd` (103/303), `sdc-ecc-amd` (104/304), `resnet50-inference-amd` (122/322), `vllm-kvcache-amd` (127/327), `jax-xla-amd`/`jax-xla-nvidia`:** removed the `rocm-smi` calls; `amd-smi metric`/`static` and sysfs were already the working sources. The 122 utilization note now says `na (amd-smi gave no utilization reading)`.
- **`rocm-tool-verify-build`:** no longer warns that `rocm-smi` is missing.
- **`config/hw_sw_info_commands.xlsx`:** `rocm-smi --showmeminfo vram` → `amd-smi static --vram`, `rocm-smi --showproductname` → `amd-smi static --asic`, `rocm-smi` → `amd-smi metric`, `rocm-smi --version` → `amd-smi firmware`. `scripts/collect_hw_sw_info.sh` regenerated; its vendor fallback checks `amd-smi`/`rocminfo`.
- **`scripts/update_runtime_ledger.py`, `templates/shared-workflows/.github/workflows/gpu-smoke.yml`, `config/workload_parameters.yaml`:** `rocm-smi` calls and examples replaced with `amd-smi` and the ROCm 10.1 package names.
- **`BenchmarkSpecDefinitions.xlsx`:** ROCm 10.1 corrections (Python 3.14.8, g++ label, 101/301 `driver_version` 7.1.9 and `required_packages amdrocm-base10.1,amdrocm-amdsmi10.1`) and 50 AMD description cells changed from `rocm-smi` to `amd-smi`. Changed cells are yellow with the old value in a comment.

## 2026-10-16 — ROCm 10.1.0 and amdgpu 31.60

- **Software levels** come from `Tmp_ROC_10_1_0_Migration_NewSoftwareLevels_20261016a.xlsx`, which supersedes the version cells in `BenchmarkSpecDefinitions.xlsx`. AMD rows now pin ROCm 10.1.0, PyTorch `2.13.0+rocm10.1.0`, torchvision `0.28.0+rocm10.1.0`, torchaudio `2.11.0.2+rocm10.1.0`, vLLM `0.29.1.dev0+rocm10.1.0` (cp314), SGLang 0.5.18 at commit `71de97b264b04dcd514cf904003028aefe9775c8`, JAX 0.11.1 with `jax_rocm10_plugin`, rocBLAS 5.7.0, and uv-managed CPython 3.14 for every benchmark virtualenv.
- **Installers:** `scripts/lib/rocm_install_24_04.sh` and `scripts/lib/rocm_install_26_04.sh` register `https://repo.radeon.com/amdgpu/31.60/ubuntu` and install `amdgpu-dkms`, then register `https://stable.repo.amd.com/rocm/core/packages/` and install `amdrocm10.1-gfx942` plus `amdrocm-core-dev10.1-gfx942`. RVS is apt package `amdrocm10-rvs` 1.6.131-844. Distro CMake is kept; the Kitware repository is not added. The reload-or-one-reboot contract is unchanged. Both Ubuntu releases reload the DKMS module.
- **Setup skeleton:** wheel index `https://stable.repo.amd.com/rocm/whl-next/`. `scripts/lib/uv_python_314.sh` creates the benchmark venv. AMD CPU workloads use that interpreter too. NVIDIA skeletons are unchanged.

## 2026-10-14 — Publish scripts lint the generator before pushing

- **`tests/test_readme_bundle_sections.py`:** removed the `f` prefix from a string with no placeholders (ruff F541). This failed the generator's `Lint Python scripts` CI step after the v1.0.12 publish.
- **`scripts/publish_benchmarks_to_github.sh`, `scripts/publish_benchmarks_to_github_manual.sh`:** new `lint_generator` runs the `ruff check` commands read from the generator's `.github/workflows/*.yml`, with `--no-cache`, in step 0 (on the run folder's generator) and again in step 9 (on the `_PubTree` copy that is pushed). A lint error stops the run before anything is pushed. `LINT_GENERATOR="no"` near the top skips it. Needs ruff on the publishing machine (`python -m pip install ruff`; CI pins 0.16.8).
- **Step 9:** removes `__pycache__`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache` and `*.pyc`/`*.pyo` from the generator copy, and its never-publish check now also flags `__pycache__` and `*.pyc`.
- **`scripts/publish_benchmarks_to_github_manual.sh`:** added to the generator as the master copy of the manual variant.

## 2026-10-13 — show_metrics.sh is installed at /opt/benchmarks

- **`scripts/create_one_workload.py`:** after a workload is copied onto the VM, `templates/suite-tools/scripts/show_metrics.sh` is installed at `/opt/benchmarks/show_metrics.sh` (LF, mode 755). It is not placed inside the workload tree.
- **`scripts/publish_benchmarks_to_github.sh`:** every bundle includes `show_metrics.sh` next to `run.sh` and `run_benchmark_suite.sh`. Cloning a bundle into `/opt/benchmarks` leaves it there. Publish stops if the script is missing.

## 2026-10-13 — show_metrics.sh Exit column

- **`templates/suite-tools/scripts/show_metrics.sh`:** each run row has an Exit column (ledger `exit_code`, 5 characters) after Idx. The legend line is `Exit    Exit Code (0 is pass)`. A per-profile mean includes the mean exit code. Widest line, 7 metrics: 93 characters. A non-zero exit still marks Idx with `*`.

## 2026-10-13 — Keep the running kernel; vLLM smoke starts the real server

- **`scripts/lib/keep_running_kernel.sh`:** before apt work, hold `linux-image-generic`, `linux-image-virtual`, `linux-headers-generic`, `linux-headers-virtual`, `linux-generic`, `linux-virtual`, `linux-tools-generic`, and the Ubuntu 24.04 and 26.04 HWE generic and virtual metapackages. `apt-cache show` is inside an `if`, so a name that does not exist on that release is skipped and does not abort setup under `set -e`. If `dpkg --audit` is not empty, setup exits and, when the text names `linux-image` or `linux-headers`, says the running kernel. If `/lib/modules` contains any kernel other than `uname -r`, setup and `scripts/self_check_generated_repo.sh` exit. That extra directory is the Ubuntu 26.04 symptom: workload 311's `linux-tools-generic` install moved the virtual and generic kernel metapackages to `7.0.0-38` while dpkg stayed healthy, and the next reboot would boot it. Setup does not remove kernels.
- **Perf packages:** `setup_cpu_system_skeleton.sh`, `setup_nvidia_skeleton.sh`, and `setup_rocm_reboot_skeleton.sh` are the only setup skeletons, shared by the 24.04 and 26.04 repos. They no longer install `linux-tools-generic`. That metapackage depends on the newest kernel image and headers. On 24.04, configuring kernel `6.8.0-147` fails `amdgpu` DKMS `6.16.13` (`pci_resize_resource` needs a fourth argument). On 26.04 the same install leaves the new kernel ready for the next boot. Perf workloads install `linux-tools-common` and `linux-tools-$(uname -r)` and fail if that package is missing. `stress-ng` no longer selects the perf install. NVIDIA installs those tools only when `BENCHMARK_INSTALL_PERF=1`.
- **`scripts/lib/rocm_install_24_04.sh`:** `linux-modules-extra` is installed only for `uname -r`. **`scripts/lib/rocm_install_26_04.sh`:** does not install `linux-modules-extra` (it is folded into `linux-modules` on 26.04) and has no newest-`/lib/modules` branch. Both Ubuntu installers call `keep_running_kernel` at the start of stage 1.
- **`scripts/self_check_generated_repo.sh`:** workloads 127–129, 227–229, and 327–329 fail when `run_benchmark.sh` contains `scripts/tiny_kv_server.py --host`. Every profile must start `vllm.entrypoints.openai.api_server`.
- **Docs:** `docs/rocm-reboot-install-contract.md`, `AGENTS.md`, `docs/SUBMISSION_CHECKLIST.md`.

## 2026-10-13 — setup.sh: no wall broadcast or terminal bell

- **`scripts/templates/setup_rocm_reboot_skeleton.sh`, `setup_nvidia_skeleton.sh`, `setup_cpu_system_skeleton.sh`:** removed the `wall` calls (the `setup.sh now complete` broadcast, and on ROCm the "rebooting once" broadcast). `wall` rang the terminal bell and printed a "Broadcast message from root@<host>" banner on every logged-in terminal after each install, which is noisy when the suite installs 32 workloads. All four bundles (101–132, 201–232, 301–332, 401–432) are built from these templates. Completion is still printed by setup (`[PASS] setup.sh complete` / `setup.sh now complete`), logged to `results/install_status.txt` and mirrored to `/etc/motd`. The ROCm first-run notice no longer says completion is announced with `wall`.
- **Docs:** `templates/README_TEMPLATE.md`, `docs/rocm-reboot-install-contract.md`, `docs/SUBMISSION_CHECKLIST.md` (3.40i), `docs/generation-workflow.md` and `AGENTS.md` no longer ask for a `wall` message.

## 2026-10-13 — README: Download as a Bundle block installs git and shows next steps

- **`templates/README_TEMPLATE.md`:** the Download as a Bundle block now starts with `apt-get update && apt-get install -y git` and says to run it as root (or with `sudo`). The clone, `./run.sh list`, this workload's smoke run and a closing `echo` are joined with `&&`, so the chain stops at the first failure and the "Done" message appears only on success. The chain ends back in `/opt/benchmarks`, where `run_benchmark_suite.sh` is. After the block, a short paragraph and three `run_benchmark_suite.sh` examples (`-p smoke`, `-w N07 -p baseline`, `--help`), with a note that each workload sets itself up on first run (`scripts/ensure_setup.sh`). No trailing whitespace.
- **`scripts/fill_generated_docs.py`:** new README token `{{CI Bundle Example Workload}}`: 107, 207, 307 or 407, from the workload's hundreds digit, so each bundle's example names one of its own workloads.
- **Tests:** `tests/test_readme_bundle_sections.py` checks the git install line, the `&&` chain ending in `/opt/benchmarks`, the per-bundle example workload and that the section has no trailing whitespace.

## 2026-10-13 — README: Download as a Bundle and Suite Tools sections

- **`templates/README_TEMPLATE.md`:** two new unnumbered sections between Quick Start and `## 1. Overview`, filled for every workload (128): **Download as a Bundle** (`git clone --recurse-submodules https://github.com/<owner>/<bundle> /opt/benchmarks`, using the workload's own bundle from `config/ci_contract.yaml`, then `./run.sh list` and a smoke run of this workload, how to update to the newest release, and a table of all four bundles) and **Suite Tools** (one line plus example commands each for `run_benchmark_suite.sh`, `get_remote_info.sh` and `show_metrics.sh`, with this workload's number filled in). The old "Running it as part of the … bundle" subsection under Continuous Integration is now a one-line pointer to these sections. Rule D in the template's agent block names the unnumbered sections.
- **`scripts/fill_generated_docs.py`:** new README token `{{CI Suite Tools Repo}}` (from `suite.tools_repo`, `gpu-bench-suite`).
- **Tests:** `tests/test_readme_bundle_sections.py` renders the README for one workload per platform and checks the bundle clone line, section order and the three script names.

## 2026-10-11 — Workload short names for show_metrics.sh (Workload_Short_Names sheet)

- **`BenchmarkSpecDefinitions.xlsx`:** new last sheet `Workload_Short_Names`, one row per workload (128): Workload Number, Workload Name, GPU Vendor, Short Name (at most 12 characters, Excel length validation), Name Length, Name Note. A full name has one short name in every batch (101 and 301 are both `System Cfg`); NVIDIA rows differ where the full name does (`rocBLAS GEMM`/`cuBLAS GEMM`, `RCCL BW`/`NCCL BW`). Before this the Name column was the first 8 characters of the workload name, which made 121/122 both `ResNet-5` and 105/119 both `PyTorch `.
- **`scripts/generate_show_metrics.py` 1.1.0:** also reads `Workload_Short_Names` and checks it against `Workload_Definitions` (every workload has one row, the full name matches, at most 12 characters, letters, digits, single spaces and `( ) + & / . _ -` only, no short name used twice in a batch, one short name per full name), then writes a second block, `# BEGIN/END GENERATED WORKLOAD NAMES`, in `workload_name_table()`. `--add-missing` adds workload rows too (short name from the same full name elsewhere, else its first 12 characters, noted `auto: review`).
- **`templates/suite-tools/scripts/show_metrics.sh`:** Name column 12 characters (short name from the table or a `--labels` line `name:WORKLOAD,Short Name`; otherwise the first 12 characters of the workload name). Idx column 5 characters so a failed run with a 4-digit index keeps its `*` (it was cut to 4). Widest line, 7 metrics: 87 characters.
- **Tests:** `tests/test_show_metrics.py` checks the name sheet is valid and complete, that validation catches a long name, a duplicate in a batch, two short names for one full name, a stale full name and a missing row, and that the script prints `RAG Sweep`. **Docs:** `README.md`, `templates/suite-tools/README.md`.

## 2026-10-11 — show_metrics.sh generated from a new Metric_Short_Labels sheet

- **`BenchmarkSpecDefinitions.xlsx`:** new last sheet `Metric_Short_Labels`, one row per workload metric (594 rows, workloads 101–432): Workload Number, Workload Name, GPU Vendor, Metric No, Metric Key (the text in parentheses, parsed as `update_runtime_ledger.py` does), Metric Description, Short Label (at most 7 characters, Excel length validation), Label Length, Label Note. It is after `Workload_Definitions` because `extract_benchmark_definition.py` uses the first sheet that holds a workload's row.
- **Labels changed from the earlier hand-kept table** (reason in Label Note): `Peak%` became `MtxPk%` (120/320, % of FP64 matrix peak) and `VecPk%` (220/420, % of vector peak), so AMD and NVIDIA no longer share a heading for different measures; `Img_s`/`Img_ms` became `ImLat_s`/`ImLatms` (too close to `Img/s`); `1stImms`/`1stIm_s` became `Cold_ms`/`Cold_s`; `TCPGb/s`/`UDPGb/s` became `TCPGbps`/`UDPGbps` (gigabits); `RDRAMns` became `Rmt_ns`; `Cach_ns` became `LLC_ns`; `FP16_TF` (221/421) became `TFLOPS` to match 121/321.
- **`scripts/generate_show_metrics.py` (new):** checks the sheet against the `Metrics` column of `Workload_Definitions` (every metric has exactly one row, keys match, labels at most 7 characters with no spaces, commas or colons, no label used twice in a workload, at most 7 metrics per workload) and rewrites the label table between `# BEGIN/END GENERATED SHORT LABELS` in `templates/suite-tools/scripts/show_metrics.sh`. One line per key; a `WORKLOAD:key` line only where a workload's label differs from the key's usual one (none today). `--check` writes nothing and exits 1 on drift; `--add-missing` adds rows for new metrics (label from the same key elsewhere, else an automatic abbreviation noted `auto: review`).
- **`templates/suite-tools/scripts/show_metrics.sh` (new):** prints one workload's runs from the runtime ledger, local or over SSH, in fixed 7-character metric columns with per-profile means and a legend; label order is ledger `metric_N_short` column, `--labels` CSV, generated table, automatic abbreviation. Example host is `203.0.113.10`. Emitted to `gpu-bench-suite` with the other suite scripts.
- **`scripts/create_generated_repo.py`:** `show_metrics.sh` added to `OPERATOR_TOOLS`, so it is installed in the project folder beside `get_remote_info.sh` (an existing copy that differs is kept). New `refresh_show_metrics` regenerates the label table first; a problem in the sheet is reported as a warning and does not stop generation.
- **CI:** `.github/workflows/ci.yml` runs `generate_show_metrics.py --check` and requires both new files. **Docs:** `README.md`, `templates/suite-tools/README.md`.
- **Tests:** new `tests/test_show_metrics.py` (sheet valid and complete, sheet order, template up to date, bad labels rejected, key parsing, override lines, script run against a sample ledger, no lab IPs or template placeholders); `tests/test_operator_tools.py` covers both operator tools.

## 2026-10-11 — Generation puts get_remote_info.sh in the project folder

- **`scripts/create_generated_repo.py`:** new `install_operator_tools` (list `OPERATOR_TOOLS`). After each generated workload it copies `templates/suite-tools/scripts/get_remote_info.sh` (LF line endings, executable) into the project folder: the parent of the folder holding the generator and the workloads, where the operator runs it and where it writes `DIRECTORIES/` and `RUNTIME_LEDGERS/`. A copy already there that differs is kept, with a message; an identical one is left alone. Before this the operator copied it by hand (Project340, Project342).
- **Not moved:** the master copy stays in `templates/suite-tools/scripts/` beside `run_benchmark_suite.sh` (published as `gpu-bench-suite`). It is not placed in `scripts/` beside `publish_benchmarks_to_github.sh`, because `init_generated_repo.py` copies `scripts/` into every workload, and not into workloads or bundles (it runs on the laptop, not the GPU host).
- **`README.md`:** "From your laptop" says where the copy appears.
- **Tests:** new `tests/test_operator_tools.py` (installs in the project folder, not in the workload folder; second workload leaves it alone; a different existing copy is kept; master copy is outside the folders copied into workloads).

## 2026-10-10 — get_remote_info.sh no longer fails while a benchmark is running

- **Failure:** `bash get_remote_info.sh 134.199.207.112` (Project342, 18:09:24 CDT) stopped with `ERROR: the remote collection failed (exit code 1)`. Workload 108 was writing a new run folder (`20261010_230924_...`) at that second; GNU tar on the remote machine reported `file changed as we read it` and exited 1, which the script treated as fatal. The archive had arrived complete, but the ledger was not saved and `DIRECTORIES/_meta` was left behind. The `time stamp ... in the future` lines were the local tar noting files about 0.5 s ahead of this computer's clock.
- **`templates/suite-tools/scripts/get_remote_info.sh`:** on the remote side, tar exit 1 is now a warning ("a benchmark is probably still running ... collect again after it finishes"); exit codes above 1 still fail. Locally, GNU tar extracts with `--warning=no-timestamp`.
- **Checked:** shellcheck 0.11.0; a run with a stub ssh/tar: normal (rc 0), tar exit 1 (warning, rc 0, ledger saved, `_meta` removed), tar exit 2 (error, rc 1). `tests/test_ci_contract.py` passes.

## 2026-10-10 — ROCm setup installs everything before its one reboot

**Failure:** on a fresh Ubuntu 26.04 MI300X VM (workload 301, 2026-10-10 22:00 UTC) the driver reload failed (`modprobe -r amdgpu` segfaulted, rc=139), so `rocm_install_runtime` rebooted right after step 09. The RVS clone/build, the venv, and the rest of setup then ran after the reboot: the operator logged back in to an install still running (`SETUP complete` at 22:16:50, about 11 minutes later).

- **`scripts/lib/rocm_install_26_04.sh` (step 10) and `rocm_install_24_04.sh` (step 12):** with `ROCM_DEFER_REBOOT=1`, a failed reload no longer reboots. The function keeps `stage3`, appends `ROCM_REBOOT_BOOT_ID` (the Linux boot ID) to `.rocm_runtime_stage.env`, sets `ROCM_REBOOT_PENDING=1` and returns 0. At `stage3` in the same boot (setup stopped on an error and was run again) the reboot stays pending; in a new boot the stage completes as before. Without `ROCM_DEFER_REBOOT` the behavior is unchanged. 26.04 file keeps CRLF line endings.
- **`scripts/templates/setup_rocm_reboot_skeleton.sh`:** exports `ROCM_DEFER_REBOOT=1` (override with `ROCM_DEFER_REBOOT=0`). When the reboot is pending it installs everything (repository, RVS, venv, framework wheels, AITER/SGLang builds, RAG extras, and the rocBLAS clients build, which names `GFX_TARGET`), then logs `PHASE All software installed. Rebooting once ...`, sends a `wall` message, and reboots. GPU checks before the reboot go through new `gpu_check` / `gpu_check_failed` (warning instead of `die`); PyTorch is checked for a ROCm build only. `scripts/build.sh` runs after the reboot, because plain `hipcc` builds (BabelStream, hipMemcpy, RCCL, rocHPL) take the GPU architecture from the visible GPU. The systemd resume run then builds, runs all GPU checks, and reports `SETUP complete`. `--help` and the first-run notice describe this.
- **`implementation_components/rag-faiss-end2end-amd/files/scripts/install_rag_amd.sh`:** with `BENCHMARK_GPU_CHECKS_AFTER_REBOOT=1` (exported by setup before the reboot) it checks `torch.version.hip` instead of `torch.cuda.is_available()`.
- **Docs:** `docs/rocm-reboot-install-contract.md` (new "Reboot Postponed Until Everything Is Installed" section and verification marker), `docs/generation-workflow.md`, `AGENTS.md`.
- **Tests:** new `tests/test_deferred_reboot.py`: installer branch on 24.04 and 26.04 (postponed, same-boot rerun, `ROCM_DEFER_REBOOT=0` rerun, first run after reboot, no-defer reboot, reload success) and the template's order (defer before `rocm_install_runtime`, reboot after all installs and before `scripts/build.sh`, GPU checks not fatal before the reboot). `shellcheck --severity=warning` 0.11.0 passes on both libraries and the template.
- **Not yet run on a real VM.** Already generated workloads (including the published `bundle-amd-ubuntu-2604`) keep the old order until regenerated.

## 2026-10-10 — publish_benchmarks_to_github.sh moved into the generator; run folder filled from Projects 341-345

- **`scripts/publish_benchmarks_to_github.sh` (new here):** the publish script, previously kept only in `Github_Garys_GPU_Repos\Publishing\`, now has its master copy in this repository. Copy it into `Publishing\` before a run; it prints a NOTE if the running copy differs from the one in the generator being published.
- **Paths:** `Z:\ServersProcessorsMemoryEtc` is now `Z:\ServersProcsMemory` throughout.
- **Sources:** new settings `PROJECTS_ROOT`, `GENERATOR_SOURCE` (Project341 generator) and `WORKLOAD_SOURCES` (the `DIRECTORIES` folders of Project342 101-132, Project343 201-232, Project344 301-332, Project345 401-432). Step 0 creates the run folder if needed and copies in each workload and the generator it does not have yet; it stops if a source folder is missing or has no workloads for its batch, and notes a batch with fewer than 32. The run folder is now `Publish_<YYYYMMDD>_<NN>/src_342_343_344_345` instead of `.../SourceRepositories`, so the script creates `src_342_343_344_345_PubTree` and `src_342_343_344_345_Bundles`.
- **Step 0 order:** gh checks and the log start before the run folder is filled, so the copy is logged. A run folder argument that names a `_PubTree`, `_Bundles` or workload folder is refused before anything is created.
- **`scripts/init_generated_repo.py`:** `scripts/publish_benchmarks_to_github.sh` added to `COPY_EXCLUSIONS`, so workloads never carry it.
- **`README.md`:** "Commands" describes the new sources, run folder and procedure.
- **Checked:** `bash -n` and `shellcheck --severity=warning` (0.11.0) pass. A dry run against a mock tree (four batches, one with 31 workloads, stub `gh`) filled the run folder with 127 workloads and the generator, printed the per-batch counts and the 31-workload note, and on a second run copied nothing; a `_PubTree` argument stopped without creating a folder.

## 2026-10-10 — Generator repository renamed to ai-agent-gpu-benchmark-repo-generator; publishing folder layout

- **GitHub:** `garys-gpu-benchmarks/999-ai-agent-gpu-benchmark-repo-generator` is now `garys-gpu-benchmarks/ai-agent-gpu-benchmark-repo-generator` (history, tags, Actions runs kept; GitHub redirects the old name). In a publish run folder the generator is copied as `ai-agent-gpu-benchmark-repo-generator` (no `999-` prefix).
- **`README.md`:** CI badge and clone URL use the new name. "Commands" describes the current publishing layout (`Publishing/Publish_<YYYYMMDD>_<NN>/SourceRepositories`) and that `publish_benchmarks_to_github.sh` builds and releases `shared-workflows` and `gpu-bench-suite`; the old manual `Repos_To_Github` steps are removed.
- **`templates/shared-workflows/README.md`:** "Releasing a change" uses `<publish folder>` and notes the publish script does it. This changes the shared-workflows repository, so the next publish releases `v1.1.0` and moves `v1` (after its Self-test).
- **`scripts/emit_shared_workflows.py`:** comments and `--output-root` help text name the publish folder; behavior unchanged.
- **`.github/SECURITY.md`, `.github/ISSUE_TEMPLATE/config.yml`:** private security reports go to the organization repository instead of `garymichaelbass/ai-agent-gpu-benchmark-repo-generator`.
- **Outside this repository:** `publish_benchmarks_to_github.sh` expects `ai-agent-gpu-benchmark-repo-generator`, requires the run folder argument, stops with a rename hint if the run folder holds `999-ai-agent-gpu-benchmark-repo-generator`, and renames the GitHub repository from the old name if it still has it.

## 2026-10-10 — Template CI: junk-file check no longer trips on the unit tests' __pycache__

- **Failure:** the generator's own "Template CI" (`.github/workflows/ci.yml`, job lint-and-validate) failed on every push (run #3, commit 56eb3dd, v1.0.7/v1.0.8) with "Process completed with exit code 1". Every step passed except the last: "Unit tests" runs `pytest`, which creates `__pycache__` folders on the runner, and "Check for leftover personal paths, secrets, or lock files" then ran `find . -name '__pycache__'` and failed on them. The repository has no committed `__pycache__` (`.gitignore` excludes it). Only the generator runs this check; the workloads use the shared ci.yml, which does not.
- **Fix:** the check now looks at committed files only: `git ls-files | grep -qE '(^|/)(__pycache__/|~\$)'`. A committed `__pycache__` file or Office lock file (`~$...`) still fails the job.
- **Checked:** on a clone of 56eb3dd after `pytest` (23 `__pycache__` folders on disk) the step passes; a force-added `__pycache__/a.pyc` and a `~$lock.xlsx` are both caught; actionlint 1.7.12 with shellcheck 0.9.0 passes. All other Template CI steps passed locally on that clone (135 tests).

## 2026-10-09 — shared-workflows Self-test: actionlint SC2015 in gpu-smoke.yml

- **Failure:** the first publish of `shared-workflows` (commit 1e190b7, Self-test run 37946198959) failed in "lint reusable workflows". actionlint runs every `run:` script through the runner's shellcheck, and Ubuntu runner shellcheck 0.9/0.10 reports `command -v rocm-smi >/dev/null && rocm-smi --showproductname || true` in the "Verify pre-provisioned GPU stack" step as SC2015 ("A && B || C is not if-then-else"). actionlint fails on any finding, so v1 was not moved and no workload was pushed. shellcheck 0.11 no longer reports it, which is why it passed on a newer local install.
- **`templates/shared-workflows/.github/workflows/gpu-smoke.yml`:** now `if command -v rocm-smi >/dev/null; then rocm-smi --showproductname || true; fi`. Same behavior: print the product name when rocm-smi exists, never fail on it.
- **Checked:** actionlint 1.7.12 on the published tree with this line changed passes with shellcheck 0.9.0, 0.10.0 and 0.11.0 (0.9.0 and 0.10.0 reproduce the failure without it).

## 2026-10-08 — TEMPLATE_00_103: one shared, versioned CI for every workload

Workloads no longer carry their own CI logic. Already generated repositories are unchanged until they are regenerated.

- **Contract.** New `config/ci_contract.yaml` (generation-only) holds the GitHub owner (`garys-gpu-benchmarks`), the `shared-workflows` repo and tag (`v1`), the caller inputs (`vendor`, `os_label`, `profile`), runner labels, timeouts, and pinned tool versions (ruff 0.16.8, actionlint 1.7.12). `scripts/ci_contract.py` derives each workload's vendor/OS/bundle and renders templates.
- **Callers.** `init_generated_repo.py` renders `.github/workflows/ci.yml` and `gpu-smoke.yml` from `templates/workload/.github/workflows/` instead of copying `docs/examples/generated-repo-workflows/*.example`, and fails generation when a caller does not match the contract. `nightly.yml` and the workload `.github/dependabot.yml` are no longer emitted; `prepare_github_publish.sh` removes them from older trees and no longer patches workflow files.
- **Shared workflows.** `templates/shared-workflows/` (emitted once by `scripts/emit_shared_workflows.py --output-root <Repos_To_Github>`): hosted `ci.yml` (shellcheck `--severity=warning`, strict ruff, syntax, spec schema, seeded-fixture validation, required files, actionlint, per-check job summary; every check runs), self-hosted `gpu-smoke.yml` (runner `[self-hosted, gpu, <vendor>, <os_label>]`, OS check, stack verification without installs, `results/environment.json`, `run_benchmark.sh --profile <p> --validate`, headline metrics, artifact upload), `self-test.yml` against a sample workload, Dependabot, README with the versioning and fork-safety policy. Least-privilege `permissions` and `actions/checkout@v7`, `setup-python@v7`, `upload-artifact@v7` throughout.
- **Fixed in the old CI.** The published `ci.yml` called `scripts/validate_template_inputs.py`, which `prepare_github_publish.sh` deletes, and swallowed ruff with `|| true`. The GPU job reinstalled the stack with `setup.sh --assume-yes` every run and could land on any vendor's runner.
- **Lint backlog.** Explicit ruff rules (`E4,E7,E9,F`) in `config/pyproject.toml`; 63 findings fixed across `scripts/` and `implementation_components/` (unused imports and variables, intentional late imports marked). Shellcheck warnings fixed in `collect_hw_sw_info.sh` (and its generator), `lib/nvcc_glibc_throw.sh`, `lib/hipcc_host_gcc.sh`, `smoke_check_generated_repo.sh`. `validate_results.py` (from `materialize_generated_harness.py`) drops an unused variable; workloads without a compile step get a real no-op `scripts/build.sh` instead of an empty file.
- **Suite tools.** `templates/suite-tools/` holds `run_benchmark_suite.sh` and `get_remote_info.sh` (example hosts replaced with documentation addresses), emitted to `gpu-bench-suite/`.
- **README and checks.** `README_TEMPLATE.md` gets a live CI badge, a "Continuous Integration" section, and the `git clone --recurse-submodules` bundle command. `self_check_generated_repo.sh`, `check_github_publish_ready.sh`, the submission checklist, `AGENTS.md` (CI Workflow Contract) and the generator README ("Continuous Integration") describe and enforce the new contract. Template CI pins permissions, runs the unit tests, and renders and actionlints the shared templates. New `tests/test_ci_contract.py`.

## 2026-10-06 — Three-line generation prompt

The chatbox entry point is `scripts/run_from_prompt.py`. It reads a `Generate workloads ...` line and an optional `ssh` line, writes repositories in the parent of this generator, and calls `create_one_workload.py` without a `--remote-root` argument. `docs/AI_AGENT_INSTRUCTIONS.md` states the minimal prompt and the defaults that no longer need to be pasted. An always-on `.cursor/rules/generate-workloads.mdc` rule keeps that contract in force. A trailing `inclusive` on a range is ignored. Git Bash rewriting `/opt/benchmarks` to `C:/Program Files/Git/opt/benchmarks` is undone, and `/root` or `/opt/workloads` is rejected.

## 2026-10-06 — NCCL baseline fits under 5 minutes

`Parameters_SmokeBaselineExtend` baseline `num_iterations` for 216 and 416 were scaled from the slower overnight run so baseline lands near 4:00 (under 5 min). Overlay rounds stay 10. Smoke stays 2 and extended stays 620000. Command columns were regenerated.

- **216:** 480000 → 295000 (measured 6:12 and 6:30).
- **416:** 480000 → 244000 (measured 6:13 and 7:53). The 2026-09-28 note named 330000, but the cell that ran was 480000.

## 2026-10-05 — NUMA pointer hops fit 4 and 12 minutes

`Parameters_SmokeBaselineExtend` `num_iterations` for 110, 210, 310, and 410 were scaled from the slower run in `Aggregate_Project322_100_200_300_400_20261005a` so baseline lands near 4:00 (3–5 min) and extended near 12:00 (8–15 min). Smoke stays 20000. Command columns were regenerated.

- **110:** 2500000000 / 7400000000 → 890000000 / 2600000000 (measured 11:13 and 33:58).
- **210:** 780000000 / 2300000000 → 460000000 / 1670000000 (measured 6:47 and 16:34).
- **310:** 1800000000 / 4000000000 → 950000000 / 2750000000 (measured 7:36 and 17:27).
- **410:** 780000000 / 2300000000 → 580000000 / 1760000000 (measured 5:23 and 15:43).

## 2026-10-05 — Mistral consolidated.safetensors is not a finished checkpoint

These are generator overlays. The next `create_one_workload.py` run picks them up. Already generated repositories are unchanged.

- **132/232/332/432 RAG.** `has_causal_lm_weights` no longer accepts `consolidated.safetensors`. A snapshot counts only with `model.safetensors`, `pytorch_model.bin`, or a complete `model.safetensors.index.json` shard set. `prefetch_rag_models.py` downloads those Hugging Face files and leaves the consolidated file for vLLM. The runner calls `ensure_mistral` before `local_files_only` and exits when Transformers reports missing causal-LM weights. Do not alias `consolidated.safetensors` to `model.safetensors`: the original key names initialize a random Mistral and still exit 0.
- **130/131/330/331 SGLang.** Baseline and extended run `scripts/prefetch_sglang_model.py` and pass the printed snapshot directory to `sglang.launch_server`. Smoke still uses `scripts/tiny_sglang_server.py`. A repo id against a consolidated-only cache makes SGLang fetch the index, ignore the consolidated file, and exit before the shards exist. Extended was passing only because a later run found the shards already downloaded.

## 2026-10-04 — 418 convolution length and setup-excluded runtime

- **418 iterations.** Baseline `num_iterations` is 100000 (was 168000) and extended is 320000 (was 514000). On the Ubuntu 26.04 H100 those previous counts ran 7:50 and 23:50. The new counts scale to about 4:40 and 14:50. Smoke stays 2. Workloads 118, 218, and 318 are unchanged.
- **Runtime clock.** `mark_benchmark_measure_start` runs after `ensure_setup.sh` returns, so `total_runtime_mm_ss` is the benchmark. `begin_benchmark_run` still starts first, and a setup failure still writes a ledger row from that earlier timestamp.

## 2026-10-04 — ResNet labels name the largest batch

- **122/222/322/422.** Each of the five headline labels now says the largest batch. The keys are unchanged. Per-batch values stay in the `case_*` columns, and `headline_batch_size` names the copied batch.

## 2026-10-04 — rocSOLVER LU labels for 120 and 320

- **120/320 #1 and #2.** The labels are "Mean rocSOLVER LU FP64, TFLOPS" and "Mean rocSOLVER LU time, s." The keys stay `sustained_fp64_performance_across_problem_size_n_tflops` and `time_to_solution_across_problem_size_n_s`. The binary remains single-GPU `dgetrf` and `dgetrs` at one N.

## 2026-10-04 — NUMA latency uses a random pointer chase

- **110/210/310/410 pattern.** Smoke, baseline, and extended set `access_pattern` to `random`. The sweep default is random as well. Sequential remains available with `--pattern sequential`.
- **Labels.** #1 is "Largest cache-tier pointer-chase latency, ns." #2 is "Local DRAM pointer-chase latency, ns." #3 is "Pointer-chase payload rate, GB/s." #4 is "DRAM-tier cache misses/s." The keys are unchanged.

## 2026-10-04 — STREAM Best Rate label and AMD parse failure

- **107/307 parse failure.** Copy, Scale, Add, and Triad no longer default to 1.0 GB/s. A missing kernel line prints `[FAIL] STREAM did not report <name>` and returns 1 before the CSV, matching 207/407.
- **107/207/307/407 labels.** Each bandwidth label now starts with "Best". The keys stay `copy_bandwidth_gb_s`, `scale_bandwidth_gb_s`, `add_bandwidth_gb_s`, and `triad_bandwidth_gb_s`. The parsed number is still Best Rate MB/s divided by 1000.

## 2026-10-04 — Tensor-op GPU check, L2 label, and suite tolerance

- **105/305 device.** The collector exits `[FAIL] no ROCm GPU` when `torch.cuda.is_available()` is false. A missing GPU no longer runs the case on CPU and compares it with a CPU reference.
- **105/205/305/405 relative error.** The label is "Maximum relative L2 error." The key stays `max_rel_error`, and the value stays `||difference|| / ||reference||`.
- **205/405 tolerance.** Every row, including the summary, stores the suite pass percentage in `tolerance_compliance`. The mean is that percentage.

## 2026-10-04 — SDC labels match the buffer check

- **104/304 ECC.** `uncorrected_ecc_errors_count` and `corrected_ecc_errors_count` stay the rocm-smi before/after delta. A RAS table's last two integers on each data row are correctable, then uncorrectable. A table that names those columns and yields no counts is `na (RAS table not parsed)`. The labels are "RAS uncorrectable counter delta" and "RAS correctable counter delta."
- **104/304 buffer size.** `hbm3_coverage_gb` is the allocated int32 buffer in decimal GB, and it is blank when the tensor is on CPU. The label is "Allocated verification buffer, GB."
- **204/404 buffer size.** The label is "Device buffer size, GiB." The key stays `hbm3_coverage_gb` and is still one `cudaMalloc` buffer.
- **Pass rate.** 104/304 is "Even-index int32 verification pass rate" (`even_word_store_pass_rate`). 204/404 is "Fixed-pattern fill/verify pass rate" (`walking_1s_moving_inversion_pass_rate`). Both values stay on a 0–100 scale.

## 2026-10-04 — Stress power, ECC interval, and NVIDIA temperature label

- **103/303 power.** A line counts as GPU power only when it is package power or the watt unit is its own word. The letter `w` inside `power` no longer matches. Each sample keeps the highest draw across GPUs, and the `sustained_` prefix still averages those samples.
- **103/203/303/403 ECC.** `gpu_system_ecc_error_count` is the last numeric sample minus the first, written on every row. A RAS table that says "Uncorrectable Error" without a captured count is `na (RAS table not parsed)`, not 0.
- **203/403 temperature.** The label is "Peak GPU temperature." The key stays `peak_gpu_junction_temp_c`. The reading is still `temperature.gpu`, and `peak_` still publishes the maximum.

## 2026-10-04 — System config labels match the checks

- **101/301 kernel count.** `kernel_driver_mismatch_count` is `uname -r` against `kernel_version` only. The label is "Kernel mismatch count." The amdgpu version stays in driver compliance.
- **101/301 driver compliance.** No `modinfo` version writes `na (in-tree amdgpu has no version)`. A real 0 is allowed by the `compliance` zero-ok hint. The `6` prefix match is unchanged.
- **201/401 package count.** `nvidia-smi` is counted missing only when the command fails. `cuda-toolkit` uses the existing CUDA-major check. Other names still use `dpkg-query`. The key `cuda_package_version_mismatches_count` is unchanged.
- **201/401 permissions.** Only character devices under `/dev/nvidia*` are checked. `/dev/nvidia-caps` is not a permission error. The label is "Device permission error count." The key is unchanged.

## 2026-10-04 — Fresh-VM fixes for 427, 428, 429, 430, and 432

These are generator overlays. The next `create_one_workload.py` run picks them up. Already generated repositories are unchanged.

- **427 / NVIDIA vLLM.** `run_benchmark.sh` for KV-cache, throughput, and token generation prepends `${REPO_ROOT}/.venv/bin` to `PATH`. FlashInfer's sampler JIT runs `ninja`, and `setup.sh` installs that binary into the venv. A CUDA-only `PATH` exited smoke with `FileNotFoundError: ninja` until a later SGLang setup installed apt `ninja-build`.
- **428 / 429 streaming.** A long greedy completion can put two logprob tokens in one SSE event while `usage.completion_tokens` still matches the sum. `record_stream_choice` counts N logprob tokens, including one token whose text is empty, and splits the gap since the previous stamp into N samples. The run fails when the summed count differs from usage, or when a chunk has text and no logprob tokens. The same client change is in the AMD throughput and token-generation overlays.
- **430 / NVIDIA SGLang.** Baseline is the first real `sglang.launch_server`. A cache that only has `consolidated.safetensors` makes SGLang download `model.safetensors.index.json` and then ignore the consolidated file, so the weight list is empty. Baseline and extended run `scripts/prefetch_sglang_model.py` and pass the snapshot directory as `--model-path`. Smoke still uses `scripts/tiny_sglang_server.py`. The same prefetch is on the serving overlay (231/431).
- **432 / RAG.** `find_local_causal_lm` accepts a snapshot only when weights and a non-empty `tokenizer.json` or `tokenizer.model` are present. `tokenizer.model.v3` does not count. If weights are cached without those files, prefetch downloads the tokenizer files instead of skipping the repo. The AMD RAG overlay has the same check.

## 2026-10-03 — vLLM token generation verifies server, model, and tokens

Workloads 129, 229, 329, and 429 now launch real vLLM in every profile and use one unreported request of up to four output tokens before throughput timing. The client verifies `/v1/models` against the configured model, saves `loaded_model_id.txt`, and records that identity in ledger notes. Streaming ITL requires exactly one logprob token per timed SSE chunk and a final count matching `usage.completion_tokens`; ambiguous chunk timing fails instead of being labeled token latency. Equal measured ITL and TPOT values remain valid. Total request completion time now publishes p50 rather than an unstated arithmetic mean. All five metric labels and keys are unchanged.

## 2026-10-03 — vLLM throughput smoke and token-level ITL

Workloads 128, 228, 328, and 428 now launch the configured real vLLM server in every profile; smoke reduces request dimensions rather than substituting `tiny_kv_server.py`. One request of up to four output tokens warms the server before the aggregate throughput timer starts. Streaming requests ask vLLM for logprobs and accept ITL only when every timed SSE chunk maps to exactly one reported output token and the count matches `usage.completion_tokens`; ambiguous inter-chunk timing fails instead of being labeled ITL. Measured ITL is no longer blanked merely because it equals TPOT. End-to-end request latency now publishes p50 instead of an unstated arithmetic mean.

## 2026-10-03 — KV-cache stress uses real vLLM and measured occupancy

Workloads 127, 227, 327, and 427 now launch the configured real vLLM server in every profile; smoke reduces request dimensions instead of substituting `tiny_kv_server.py`. Each sweep sends one unreported warmup request, reports median TTFT/TPOT, and computes decode throughput as all completed post-first tokens divided by one wall-clock decode window from the earliest first token to the latest completion. KV occupancy is sampled every 50 ms while requests are active and the run fails when GiB or percentage remains unavailable. Documented vLLM utilization gauges are accepted only as 0–1 ratios before conversion to percent, preventing a value such as 1.2 from becoming 120%.

## 2026-10-03 — SDXL smoke measures real SDXL

Stable Diffusion XL workloads now load the real SDXL pipeline in every benchmark profile. Smoke retains a short run but enforces at least 256×256 resolution, two denoising steps, and two timed images; TinyDenoiser remains only an explicit setup self-test and the NVIDIA collector refuses to publish it as SDXL. Cold latency starts before pipeline import/loading and ends after the first generated image. Peak memory uses the larger of PyTorch peak allocated and reserved memory and real-SDXL results below 5 GB are rejected. NVIDIA summary throughput is total images divided by total timed image seconds, and peak VRAM is the maximum across passes.

## 2026-10-03 — Memcpy bandwidth regime and seven-slot ledger

Workloads 114, 214, 314, and 414 retain their existing metric labels and keys but now enforce a 256 MiB maximum-transfer floor and at least 10 timed copies, so their maximum-size values measure sustained transfer bandwidth instead of expressing 4 KiB latency as GB/s. NVIDIA's pageable ratio is published only at the maximum transfer size rather than averaged across the sweep. The runtime ledger now has seven metric definition/result pairs, preserving D2D latency (#6) and NVIDIA pageable ratio (#7); existing five-slot ledgers migrate by column name with the two new pairs blank on older rows.

## 2026-10-03 — AMD GUPS L3 miss rate

Workloads 113 and 313 keep metric #5 as `L3 cache miss rate (l3_miss_rate)`, but now compute it from `LLC-load-misses / LLC-loads` rather than generic `cache-misses / cache-references`. The table is at least four times the detected last-level cache, with a 256 MiB fallback floor. Hosts that do not expose both LLC load events report `na (LLC load counters unavailable)` instead of relabeling generic cache events as L3.

## 2026-10-03 — NUMA cache and DRAM measurements

Workloads 110, 210, 310, and 410 keep their existing metric labels and keys. Cache latency now comes from the largest configured non-DRAM tier instead of the smallest working set. The DRAM tier is expanded beyond the detected last-level cache (with a 256 MiB floor), and latency, pointer-chase bandwidth, and cache misses all come from that configured tier and access pattern rather than a separate hardcoded random run. The native harness now honors `num_threads`, builds a complete dependent pointer chain, and computes aggregate useful-load bandwidth instead of multiplying accesses by stride. `per_size.csv` includes cache misses for every measured tier.

## 2026-10-03 — AMD KV-cache GiB from the engine log

Workloads 127 and 327 publish KV-cache GiB as the measured percent times `Available KV cache memory` in `server.log` when the server exports a percent and no byte gauge. A byte gauge still wins. A percent with neither bytes nor that log line is `na (server reported a percent and no byte count)`. No reading at all stays `na (server reported no KV-cache usage)`. Workloads 227 and 427 use the same fallback reason.

## 2026-10-03 — rocBLAS GEMM drops the unpublished L2

Workloads 117 and 317 no longer publish L2 norm error. rocBLAS does not print `norm_error_2`, so that slot was always `na`. CPU reference GFLOPS is slot 5. Workloads 217 and 417 still publish the L2 their collector computes.

## 2026-10-03 — Remote DRAM latency reason

Workloads 109, 209, 309, and 409 print `na (requires a second NUMA node)` for remote DRAM latency when the host has one NUMA node. A blank skipped tier still prints `not measured`.

## 2026-10-03 — Runtime windows for 218, 412, 126/326, and 432

Baseline stays inside 3–5 minutes and extended inside 8–15 minutes. Targets from the latest measured runs are about 4:00 and 11:30.

- **412:** `repetitions` baseline 5 → 1, extended 14 → 3. Measured 17:19 and 52:40.
- **218:** `num_iterations` baseline 168000 → 85000, extended 514000 → 250000. Measured 7:50 and 23:48.
- **126/326:** iteration counts stay. The AMD forward pass stops at 120 seconds baseline and 330 seconds extended (was 300 and 900). The collector still runs two passes, which is why both baselines were about 10:21.
- **432:** `query_count` baseline 220 → 75, extended 680 → 190. Measured 11:44 and about 41:00. Baseline 75 builds the 400-context corpus.

## 2026-10-03 — Prerequisites Python label

The prerequisites paragraph uses the `Python Version` cell as written when that cell already starts with `Python`. A bare version still receives the prefix. Workbook cells stay `Python 3.12.3` and `Python 3.14.4`.

## 2026-10-03 — HPL headline order

Workloads 120, 220, 320, and 420 put time to solution in slot 2 and percent of peak in slot 3. Slot 1 stays sustained FP64 TFLOPS. The peak keys stay `percent_of_gpu_fp64_matrix_peak` on 120/320 and `percent_of_fp64_vector_peak` on 220/420. The 220/420 output-field list and raw-example header now name `percent_of_fp64_vector_peak`.

## 2026-10-03 — Convolution headline order

Workloads 218 and 418 use the same first three roles as 118 and 318. Slot 1 is forward kernel time (`kernel_time_msec`). Slot 2 is forward achieved throughput in TFLOP/s (`tflops_fwd`). Slot 3 is forward memory bandwidth (`memory_bandwidth_gb_s`). Slot 4 stays solver search time (`solver_search_msec`), the sum of `cudnnFind` wall time across the directions run. Keys and collectors are unchanged. 118 and 318 slot 4 remains the forward flop count (`flopcnt`).

## 2026-10-03 — Memcpy key order

Workloads 114, 214, 314, and 414 use `bandwidth_<direction>_gbps` and `latency_<direction>_us`. Directions stay `h2d`, `d2h`, and `d2d`. The pageable ratio key is unchanged.

## 2026-10-03 — Creation fixes from workloads 101–432

The four TEMPLATE_00_97 batches passed after mid-run repairs. Those repairs are now in the generator.

- **Docs.** Missing workbook columns `Execution Summary (Run and Measure)`, `nVidia Porting Instructions (Reference Only)`, `AMD nVidia Applicable`, and `Model Context Protocols` are filled during extraction. Prerequisites and the mermaid diagram are written before any hardware table. `{{Kernel Version}}` uses the profile `kernel_version` when that value is set. Remote logs are printed with replacement characters, and Git Bash path conversion is disabled on Windows.
- **Self-check.** A missing `rg` fails as `ripgrep is not installed`. The remote run installs ripgrep before self-check. A helper named only inside `[[ -f scripts/... ]]` is optional.
- **Remote tree.** `chmod 644` skips `third_party`, `bin`, and `build`. Shell scripts keep the execute bit. An existing `rocblas-bench` is treated as built, and `install.sh` is made executable before it runs. STREAM restores `+x` after `cp`. `.env_reuse_stamp` is written when setup finishes, including when smoke fails later.
- **101/301.** `rocm-smi` and `rocm-core` match Ubuntu 26.04 package names and an `/opt/rocm/bin/rocm-smi` executable. A missing in-tree `amdgpu` version is left blank with mismatch 0.
- **111/211/311/411.** `yaml_get` reads `config/benchmark_config.yaml` with PyYAML, so a folded `stress-ng` command keeps both the `--cpu` and `--cache` invocations.
- **116/316.** The RCCL binary accepts one visible GPU and is rebuilt when `src/rccl_perf.cpp` is newer than `bin/all_reduce_perf`. A one-GPU profile still publishes `na (requires at least two GPUs)`.
- **126/326.** Ubuntu 24.04 installs `jax-rocm7-plugin==0.10.0`. Ubuntu 26.04 keeps the `+rocm7.14.0` wheel. Setup exits unless `jax.devices()` contains a non-CPU device.
- **201/401.** A driver CUDA major newer than the workbook major is not a package mismatch.
- **206 and NVIDIA setup.** `python3` is installed before the interpreter probe on the NVIDIA, CPU/system, vLLM, and SGLang setup paths.
- **205/405 and other locked YAML.** A locked sweep that already matches after numeric normalization is left byte-identical. A real merge refreshes the overlay hash from the file in the repo.
- **327–331.** Ubuntu 26.04 accepts the AMD CDNA vLLM index as well as `wheels.vllm.ai/rocm/`. `sgl-kernel` compiles with `/opt/rocm/bin` first and `/opt/rocm/include` on the include path.
- **Records.** Batch rows use `return_code` and `reason`. `GENERATION_REPORT.md` receives the start, finish, and duration after validation.

## 2026-10-03 — Align AMD and NVIDIA headline metrics

Workbook metric order and keys now match across each vendor pair where the measurement is already the same. Collector columns were renamed with the workbook so a new key still resolves. Rows not listed here were left unchanged.

- **201/401:** driver compliance is slot 3 and VBIOS presence is slot 4. 101/301 are unchanged.
- **102/202/302/402:** the device-visibility count moves to slot 5. Temperature, PCIe width, and PCIe speed occupy slots 2–4.
- **104/304:** ECC keys gain the `_count` suffix. Wall-clock time moves to slot 3 on 104/204/304/404. Coverage bytes and the two pass-rate patterns are unchanged.
- **112/212/312/412:** null-syscall time is microseconds (`lat_syscall_null_us`). Context switch is `context_switch_latency_us`. The 16 MB latency row is selected by size. Memory read is `bw_mem 512m rd`.
- **105/205/305/405:** 205/405 slots 1 and 2 say "across correctness cases". Reference dtype is unchanged.
- **115/215/315/415:** BabelStream keys are `bandwidth_gb_s_copy`, `bandwidth_gb_s_mul`, `bandwidth_gb_s_add`, `bandwidth_gb_s_triad`, and `bandwidth_gb_s_dot`.
- **113/313:** order is giga-updates, update rate, payload GB/s, TLB miss rate, L3 miss rate. The score key is `giga_updates_score`. 213/413 stay at three metrics and publish `updates_sec`.
- **117/317:** headline metrics are achieved TFLOPS, kernel time in milliseconds, minimum operand traffic, rocBLAS `norm_error_1` as `relative_l1_checked_columns`, and `norm_error_2`. rocBLAS does not print an L2 norm, so that cell is `na (rocblas-bench does not report norm_error_2)`. `cpu_gflops` remains slot 6.
- **121/221/321/421:** slot 4 is peak GPU memory and slot 5 is the traffic estimate.
- **122/322:** slot 3 is the nearest-rank p99 (`batch_p99_latency_msec`). Throughput and per-image latency use the mean step time.
- **223/423:** slot 2 publishes the mean step time already used for throughput (`mean_latency_ms`).
- **124/324:** per-image latency key is `per_image_latency_sec`. Peak memory keys are unchanged.
- **125/225/325/425:** step time is `step_time_ms` and token throughput uses one label.
- **127/227/327/427:** shared keys are `output_tokens_per_sec`, `ttft_msec`, `tpot_msec`, `kv_cache_peak_gb`, and `kv_cache_usage_peak_pct`.
- **128/228/328/428 and 129/229/329/429:** the p50 keys use the `*_msec` names.
- **130/330:** the printed list drops completed-request percentage and slot 1 is "E2E latency, ms". The client still records the percentage.

## 2026-10-03 — One-GPU collectives publish na; JAX budget is a warning; H100 stress power limit is 700 W

- **116/216/316/416:** `all_reduce` still runs. On one GPU the three metrics are `na (requires at least two GPUs)` and the run exits 0. A missing binary, non-zero exit, or empty size table still fails. A profile that asks for two or more GPUs and initializes fewer still fails.
- **126/226/326/426 JAX/XLA:** hitting the profile time budget prints `[WARN]` and records the iterations that finished. `requested_iterations` and `completed_iterations` stay in the result. The run fails when the process exits non-zero, emits no RESULT line, or completes zero iterations. Workbook iteration counts are unchanged.
- **203/403:** `power_threshold` is 700 W, the H100 SXM board limit. Mean power above that limit still fails validation. `gpu_load_percent` stays 50. Temperature, thermal slowdown, ECC, and the GPU-load check are unchanged. 103/303 stay at 500 W.
- **Tests:** `tests/test_metric_feedback_updates.py` covers the na string, the two-GPU shortfall failure, and the JAX budget warning.

## 2026-10-02 — Metric feedback follow-up: ten additional correctness improvements

- **104/204/304/404 ECC:** corrected and uncorrected metrics are pre/post deltas. AMD parses exact counter names; NVIDIA records failed loops. Pass rates are passed checks divided by attempted checks, and coverage counts only the verified device buffer.
- **201/301/401 stack validation:** package counts no longer include tool-probe or CUDA-major failures. AMD exposes kernel and driver diagnostics separately, leaves unavailable driver compliance blank, and counts each missing device independently. NVIDIA reports CUDA-major mismatch separately and scores a three-check minimum-driver/userspace/kernel compliance checklist.
- **106/206/306/406 FIO:** the first declared rw/block-size/queue-depth case is the recorded headline. Every matrix result remains available under `case_*` columns, avoiding a mean across incompatible cases.
- **122/222/322/422 ResNet inference:** the largest declared batch is the recorded operating point; every batch retains its own `case_*` metrics. Throughput and latency now describe the same batch.
- **110/210/310/410 NUMA:** unavailable or denied cache-miss counters emit `na (...)`, never zero.
- **126/226/326/426 JAX/XLA:** compilation is timed with `lower(...).compile()` separately from execution, incomplete iteration profiles fail, and output records the analytic FLOP method plus requested/completed iteration counts.
- **220/420 NVIDIA dense LU:** identifies the cuSOLVER Dgetrf/Dgetrs implementation, records requested/actual N and repeats, and uses the FP64 vector peak rather than tensor-core peak.
- **127/227/327/427 vLLM KV:** decode throughput excludes TTFT/prefill; AMD requires byte telemetry for the GiB metric instead of estimating it from utilization and total VRAM.
- **131/231/331/431 SGLang:** ITL percentiles pool individual token gaps across requests instead of taking percentiles over per-request means.
- **Tests:** expanded metric-feedback regression coverage for all ten follow-up changes.

## 2026-10-02 — Metric feedback: preserve keys while correcting collection and aggregation

- **116/216/316/416 collective bandwidth:** RCCL now initializes the requested GPU ranks and both vendors require at least two GPUs. The headline metrics use one defined all-reduce operating point instead of averaging unlike collectives; one-rank runs fail rather than publishing `na` as a measurement.
- **105/205/305/405 tensor correctness:** relative error is a whole-tensor norm ratio, compliance remains elementwise `atol + rtol*abs(reference)`, maxima cover every iteration, failed cases carry error status, and `failure_count` is the integer suite total.
- **112/312 lmbench:** long-form benchmark names now equal the unit-suffixed contract keys, the 16 MB latency row is selected by size, and memory bandwidth uses a 512 MB working set instead of an 8 MB cache-resident buffer.
- **124/224/324/424 SDXL parsing:** run latency is the mean across timed images, throughput is completed images divided by total timed duration, peak VRAM uses `max`, and step time uses all samples instead of the first/last row.
- **106/206/306/406 FIO:** explicit operation mapping prevents `randwrite` from selecting read statistics. Missing IOPS, bandwidth, or failed FIO execution now fails instead of inventing 1 IOPS, 4096-byte bandwidth, or latency percentiles.
- **202/402 NVIDIA health:** emits the exact `pcie_link_speed_gt_s` contract key. **302:** missing temperature remains unmeasured and zero HSA GPU agents is retained as a failed sample.
- **Peak aggregation:** generated parsers apply `max` to observed metric names containing `peak` (except theoretical `percent_of_*peak`). The NVIDIA vLLM KV collector separately takes the maximum `kv_cache_peak_gb` and `kv_cache_usage_peak_pct` across sweeps instead of their mean.
- **Metric binding:** resolution examines later parentheticals, so labels such as `(decode) ... (output_tokens_per_s)` bind to the real key without changing the label.
- **Tests:** added coverage for later-parenthetical key binding and non-leading peak aggregation.

## 2026-10-02 — 111/211/311/411 Linux perf PMU: one collector, same five metrics on AMD and NVIDIA

- **Problem:** the four rows share a workload name, parameters, and run commands, but each vendor had its own collector. 111/311 (`linux-perf-pmu-amd`) published IPC, branch misprediction, cache misses per 1,000 instructions, pipeline stall %, and context switches/s, left them blank with status ok when perf was blocked, and profiled `sleep` when stress-ng was missing. 211/411 (`linux-perf-pmu-nvidia`) published elapsed TSC-or-PMU cycles, child CPU time, CPU utilization, and bogo-ops/s instead; its #1 was PMU cycles summed over every CPU on one host and wall time x TSC frequency on another (not the same unit), its CSV column was `cycles` while the metric key was `elapsed_tsc_or_pmu_cycles`, its optional IPC columns used other names, and it counted a missing branch-misses or stall event as 0. The stall events also differed: AMD asked for `cycle_activity.stalls_total`, which exists only on Intel CPUs (the MI300X VM has an Intel Xeon 8568Y+), NVIDIA asked for `stalled-cycles-frontend/backend`, which Intel does not implement.
- **One `scripts/collect_workload.py`, identical in both components:**
  - Runs each yaml `workload_commands` entry (`{num_cpus}`, `{duration}` substituted) under `perf stat -x, -o <run>/perf_N.csv`, counting cycles, instructions, branches, branch-misses, cache-misses, context-switches, the stall event, and the yaml `event_list` (names perf does not know are dropped and listed in `pmu_events.txt`; it used to be ignored).
  - Metrics: `instructions_per_cycle_ipc` = instructions / cycles; `branch_misprediction_rate` = 100 x branch-misses / branches; `cache_misses_per_1000_instructions`; `pipeline_stall_pct` = 100 x stall cycles / cycles; `context_switches_during_workload_switches_s` = context switches / elapsed seconds (perf, else getrusage).
  - Stall event by CPU vendor: `cycle_activity.stalls_total` (GenuineIntel), `stalled-cycles-backend` (AuthenticAMD and others); `BENCHMARK_PMU_STALL_EVENT` overrides. If it does not count, `pipeline_stall_pct` is `na (no stall-cycle event counted on this CPU ...)`.
  - No PMU: when perf cannot open its events it never starts the workload, so the command runs bare and the four PMU metrics read `na (PMU access denied: perf_event_paranoid=N)`, `na (hardware PMU counters not available on this host)`, or `na (perf not installed for kernel ...)`. Generated `parse_results.py` reports that text in summary.json and the metric summary prints it.
  - Extra columns: raw counts, `pipeline_stall_event`, `pmu_counter_running_pct` (below 100 means perf multiplexed and scaled counters), `context_switches`, `cpu_time_sec`, `cpu_utilization_percent`, `stress_ng_bogo_ops_s`, `pmu_source` (`perf` / `unavailable` / `perf_missing`).
  - Accepts `--num-cpus`, `--workload-commands`, `--event-list`, `--duration` (yaml values when absent), so `run_benchmark.sh` now passes them.
  - Fails the run if stress-ng is missing or a workload exits non-zero.
- **Workbook (111/211/311/411, 14 cells each, 56 total):** the same Metrics on all four (#2 label now "Branch misprediction rate, pct"; keys unchanged for 111/311). Execution Description, Main Goal, Validation Objective, Command Tools, Command Methodology, Command Execution Details, Raw Output Format, Record Granularity, Raw Output Example, Output Fields, Success Criteria, Parser Notes, and Known Runtime Constraints rewritten to match the code (111 said workload_commands was ignored and only `--cpu 1` / `--cache 1` ran; 111/311 said missing counts were floored at 1.0). Parameters sheet and run commands unchanged; `sync_matrix_profile_commands.py --check` passes.
- **`component.json` descriptions, AGENTS.md, `docs/SIBLING_WORKLOAD_NOTES.md`** describe the shared collector.
- **Expect different numbers:** 211/411 results are not comparable with earlier rows (different metrics). 111/311 #4 now uses the vendor-correct stall event, and on an AMD EPYC host may read na where it used to be blank.
- **Tests:** `tests/test_linux_perf_pmu.py` (11, stand-in perf and stress-ng): both components identical; spec keys present; Intel (hybrid `cpu_core/cycles/` name), AMD stall event, missing stall event is na, no PMU, permission denied (workload rerun bare), perf missing, runner flags override yaml, failed workload and missing stress-ng fail. Full suite 88 tests pass. End to end through the generated parser, validator, and metric summary for 211/311/411 with PMU and with na. Real perf on a host with `perf_event_paranoid=4`: denied path, `na (PMU access denied: perf_event_paranoid=4)`, unknown event dropped. **Not yet run on the MI300X or H100 VMs.**

## 2026-10-02 — 203/403 NVIDIA system stress applies real GPU load (cuBLAS GEMM at gpu_load_percent) and its thresholds

- **Problem:** the `system-stress-nvidia` collector started only `stress-ng --cpu` and accepted none of the runner's flags, so `gpu_load_percent`, `cpu_load_percent`, `temp_threshold`, `power_threshold`, `throttle_check`, `ecc_check`, and `poll_interval` were dropped (`run_benchmark.sh` passes a flag only when the collector's `--help` lists it), while the ledger's resolved command still showed them. On the 26.04 H100 SXM VM, 403 baseline (`20261002_134110`) read 0% `utilization.gpu`, ~73 W, and 36-37 C for 200 s: an idle GPU was published as the stress result. Each poll also made two `nvidia-smi` calls and then slept a full second, so polls drifted (seconds 17, 34, 50, ... missing).
- **New `src/gpu_stress.cu` (bin/gpu_stress):** cuBLAS `cublasGemmEx` FP16 GEMM, n=8192, FP32 accumulate, non-zero inputs. Runs GEMMs back to back for `load_percent` of each 100 ms window and idles for the rest, so `utilization.gpu` follows the request. Prints `GPU_LOAD_READY` after warm-up, `GPU_LOAD` per second, and `GPU_LOAD_DONE seconds= gemms= busy_pct= tflops_busy=`. Every CUDA/cuBLAS call is checked; any error exits 2 with the message.
- **New `scripts/build.sh`:** nvcc with `nvcc_arch_flags` (native SASS) and `-lcublas`. 403's `scripts/build.sh` was empty before. **New `scripts/probe_setup.sh`:** setup fails unless `bin/gpu_stress 2 50` reports GEMMs.
- **`scripts/collect_workload.py`:**
  - Accepts `--num-threads`, `--cpu-load-percent`, `--gpu-load-percent`, `--temp-threshold`, `--power-threshold`, `--throttle-check`, `--ecc-check`, `--poll-interval`, `--duration` (yaml values when a flag is absent).
  - Starts `bin/gpu_stress <duration+2> <gpu_load_percent>` and waits for `GPU_LOAD_READY` (120 s limit) before starting `stress-ng --cpu <num_threads> --cpu-load <cpu_load_percent>`, so every sample is inside the load window. Output goes to `gpu_stress.txt`.
  - One `nvidia-smi` call per poll (ECC field included when `ecc_check`), on a fixed `poll_interval` schedule.
  - Fails the run if `bin/gpu_stress` is missing, never reaches READY, exits non-zero, or reports no GEMMs, or if mean `utilization.gpu` is below half of `gpu_load_percent` (minimum 10%).
  - Peak temperature above `temp_threshold`, mean power above `power_threshold`, or a hardware thermal slowdown with `throttle_check` marks every sample `status=error` with the reason; the run parses as `partial` and `--validate` fails. CSV columns and the three metrics are unchanged.
- **`component.json`:** overlays `src/gpu_stress.cu`, `scripts/build.sh`, `scripts/probe_setup.sh`; completeness `closed`.
- **`setup_nvidia_skeleton.sh`:** fails when `src/gpu_stress.cu` is present but `bin/gpu_stress` was not built. **`self_check_generated_repo.sh`:** `src/gpu_stress.cu` must be compiled by `scripts/build.sh`.
- **Workbook (203 row 40, 403 row 112, 16 cells):** Validation Objective, Command Tools Executed, Command Methodology, Command Execution Details, Raw Output Format, Software Framework (cuBLAS-bench removed), Runtime Language; 203 also Execution Description and Main Goal. 403 text no longer promises DCGM, `sensors`, or Xid monitoring, which are not run. No other cell changed.
- **Expect different numbers:** 403 power and temperature now reflect ~50% GEMM load and are not comparable with earlier rows. The default `power_threshold` 500 W and `temp_threshold` 75 C now gate the result. An H100 SXM at 50% duty is expected to stay under both, but that has not been measured.
- **Tests:** `tests/test_system_stress_nvidia.py` runs the collector with stand-in `nvidia-smi`, `stress-ng`, and `bin/gpu_stress`: loaded run ok and `--cpu-load 50` passed; idle GPU, missing binary, and a binary that fails with the PTX error each fail the run; temperature, power, and thermal-slowdown breaches mark samples error. Full suite 77 tests pass. `gpu_stress.cu` compiles and links against CUDA 12 runtime and cuBLAS headers with `-Wall -Wextra`, no warnings, and exits 2 with a message on a host without a GPU. **Not yet run on a GPU.**

## 2026-10-02 — 418 cuDNN convolution builds on CUDA 13.3; 404/415/418 compile native SASS; 404 checks kernel launches

- **Failure (418, Ubuntu 26.04, H100, CUDA 13.3 nvcc only):** smoke/baseline/extended all exited 1 in setup at `run_benchmark.sh` line 163 (`ensure_setup.sh`). Three faults were stacked; each hid the next.
  1. Setup installed the CUDA 12 system cuDNN while nvcc was CUDA 13. Fixed earlier in this template: the skeleton picks cuDNN after nvcc is on `PATH` and pip-installs `nvidia-cudnn-cu13==9.23.2.1` for CUDA 13.
  2. `build.sh` looked for `.venv/.../nvidia/cudnn/lib/libcudnn.so`. The wheel ships only `libcudnn.so.9` (plus `cudnn.h` under `nvidia/cudnn/include`), so the build stopped with "CUDA 13 nvcc requires the venv cu13 cuDNN" even with the wheel installed. The include directory was never passed either, and `-lcudnn` needs the unversioned name.
  3. With those fixed, `bin/cudnn_conv` stopped at its first fill kernel: "the provided PTX was compiled with an unsupported toolchain". Without `-gencode`, nvcc emits an old default arch plus PTX the driver must JIT; this driver is older than the 13.3 toolkit and refuses it.
- **`cudnn-convolution-nvidia/files/scripts/build.sh`:** on CUDA 13 the venv cuDNN is the directory that has `lib/libcudnn.so.9` and `include/cudnn.h`. Build adds `-I<wheel>/include`, links `lib/libcudnn.so -> libcudnn.so.9` in the venv, and passes rpath with `-Xlinker -rpath -Xlinker`. CUDA 12 path unchanged.
- **`scripts/templates/setup_nvidia_skeleton.sh`:** the "is the cu13 wheel installed" check looks for `libcudnn.so.9` (it looked for `libcudnn.so` and reinstalled the wheel on every setup).
- **`scripts/lib/nvcc_glibc_throw.sh`: new `nvcc_arch_flags`.** Fills `NVCC_ARCH_FLAGS` with `-gencode arch=compute_XX,code=[sm_XX,compute_XX]` from `nvidia-smi --query-gpu=compute_cap`, falling back to the `/proc/driver/nvidia` model (B200/GB200, H100/H200/GH200, L40/Ada, A100/A800). `BENCHMARK_CUDA_ARCH` overrides. Unknown GPU: no flags and a `[WARN]`. This is the block 415 already carried inline.
- **Build scripts using it:** `cudnn-convolution-nvidia` (418), `sdc-ecc-nvidia` (404, previously had no arch flags), `babelstream-hbm-nvidia` (415, inline copy removed). cuBLAS, memcpy, NCCL, and HPL launch no kernels of their own and are unchanged.
- **404 false pass:** `src/ecc_walk.cu` checked only `cudaDeviceSynchronize`, which does not report a rejected launch. On the 26.04 VM the 20 s walk could loop with no kernel running and publish 0 mismatches / 100% pass (ledger `404_20261002_125642`, 20.7 s). Each launch is now followed by `cudaGetLastError()`; a rejected launch exits 2 before the `loops=` line. `collect_workload.py` reports that exit code and ecc_walk's error text (it said "host RAM was not used").
- **Tests:** `tests/test_nvidia_build_contracts.py` (no GPU needed): every component `src/*.cu` with `__global__` kernels has a `build.sh` that calls `nvcc_arch_flags` and passes `NVCC_ARCH_FLAGS` to every nvcc line; every kernel launch is followed by `cudaGetLastError` within 5 lines; the cuDNN build looks for `libcudnn.so.9` and `cudnn.h`; the skeleton check uses `libcudnn.so.9`; `nvcc_arch_flags` output for a stub `nvidia-smi` (9.0 -> sm_90), the override, and the unknown-GPU warning.
- **Checked:** the 418 build and `probe_setup.sh` on the H100 VM with the equivalent inline flags: `-gencode arch=compute_90,code=[sm_90,compute_90]`, fwd / bwd_data / bwd_weights `status=ok`. Full unit suite passes (68 tests). Not yet run on the VM: the shared-helper build scripts, the 404 and 415 rebuilds, and a full smoke pass from a fresh generation.

## 2026-10-01 — 130/230/330/430 SGLang prompt-response: real cache-hit rate, completed-request rate, decode rate, server token counts

- **Server launch (`sglang-prompt-response-amd` and `-nvidia` `run_benchmark.sh`):** baseline/extended add `--enable-cache-report`, so SGLang returns `usage.prompt_tokens_details.cached_tokens` on each completion. Neither script started SGLang with `--enable-metrics` either, so the old `/metrics` fallback found nothing and real runs published a "measured" 0.0% hit rate.
- **`scripts/prompt_response_client.py` (one file, now identical on both vendors):**
  - RadixAttention hit rate = total cached prompt tokens / total prompt tokens over successful requests. The `/metrics` scrape is removed (it summed label series, multiplied values <= 1.5 by 100, and returned 0.0 when nothing was found). No cached counts (e.g. smoke's stand-in server) -> `na (server reported no cached-token counts)`. Prompts share a common first half by design, so about 50% is expected once the cache is warm.
  - Completed request percentage = successful / attempted requests. Each request is wrapped in try/except: a failed request becomes a `status=error` row with the error message instead of stopping the run. It was hard-coded to 100.0. The client exits 1 only if every request fails.
  - Output token rate is the decode rate, (output tokens - 1) / (end-to-end - TTFT); it was output tokens / end-to-end, which charged prefill and TTFT to generation. Without streaming, TTFT and the rate read `na (requires streaming)` (TTFT was blank).
  - Output tokens come from the server's `usage.completion_tokens` (streaming requests now send `stream_options.include_usage`), else the streamed text-chunk count. Streamed responses carried no usage, so the count fell back to `max_tokens` (3870 at baseline) and overstated the rate when a reply stopped early. TTFT now starts at the first chunk that contains text.
  - New columns `prompt_tokens`, `cached_tokens`, `error_message`.
- **SGLang `parse_results.py` overlay (`sglang-prompt-parser-amd`, `sglang-prompt-response-nvidia`):** means, percentiles, and statistics use successful requests only; client-recorded failures lower the completed percentage without failing the run (the run fails if no request succeeded or a successful row is invalid). A metric with no number reads its `na (...)` text in summary.json (it used to become 0.0 or disappear) and NULL in SQLite.
- **Workbook (130/230/330/430):** #3 label "Output token generation rate (decode), tokens/s"; methodology, raw format, granularity, example, fields, success, and parser-notes cells rewritten (130/330 said the hit rate was hard-coded 1.0); 430 objective/tools no longer mention bench_serving (35 cells).
- **Not changed:** metric keys, prompts, request count, run duration.
- **Checked:** against the smoke server and a stand-in that reports cached tokens and fails one request, through the parser and metric summary: 75% completed, 33.3% hit rate (0 + 32 + 32 of 3 x 64 prompt tokens), na texts for no-cache / no-streaming, client exit 1 and run status error when every request fails. Not run on real SGLang.

## 2026-10-01 — 228/229/428/429 vLLM serving: summary-only raw_results.csv, real percentiles, server token counts (and 128/129/328/329)

- **`vllm-throughput-nvidia` and `vllm-token-generation-nvidia` `scripts/benchmark_serving.py` (228/229/428/429):** per-request rows now go to `requests.csv` (`request_index`, `status`, `output_tokens`, `request_output_tokens_per_sec`, `ttft_msec`, `tpot_msec`, `itl_mean_msec`, `end_to_end_request_latency_msec`). `raw_results.csv` holds only the run summary, twice (the harness needs two rows). Before, the per-request rows (each with its own single-request rate, and its single TTFT/TPOT/ITL copied into p50/p95/p99) were averaged together with the summary row, so throughput came out about 4-5x low (smoke test: 1130 tok/s published vs a true 4760) and "p50" was a mean.
- **ITL percentiles (all four collectors):** taken over every inter-token gap of every request, not over each request's mean gap.
- **Output token count (all four collectors):** requests set `stream_options.include_usage` and use the server's `usage.completion_tokens`, else the number of text chunks, else the requested length. A chunk can carry several tokens, so counting chunks undercounts.
- **`vllm-throughput-amd` and `vllm-token-generation-amd` (128/129/328/329):** TPOT = (end-to-end - TTFT) / (output tokens - 1); it divided by all output tokens. NVIDIA already used tokens - 1. Their `raw_results.csv` layout was already summary-only and is unchanged.
- **Workbook:** 228/229/428/429 Raw Output Format, Record Granularity, and Parser Notes describe the two summary rows, `requests.csv`, the percentile definitions, and TPOT; 128/129/328/329 Parser Notes drop the stale "non-streaming" / "itl duplicates ttft" text (16 cells).
- **Not changed:** metric keys and labels, server launch flags, run duration.
- **Checked:** all four collectors against the smoke server end to end through the generated parser and metric summary; the NVIDIA published throughput equals the run summary (5599 tok/s on the test host) and p50 values are true percentiles.

## 2026-10-01 — 127/327 KV cache stress: standard TPOT, GiB, na instead of blank

- **`vllm-kvcache-amd/scripts/benchmark_serving.py`:** same TPOT and unit fixes as 227/427: TPOT = (end-to-end - TTFT) / max(output tokens - 1, 1) with output tokens from `usage.completion_tokens` (`stream_options.include_usage`), not the mean gap between stream chunks; KV bytes, block-based KV size, and rocm-smi total VRAM in bytes are divided by 1024^3 (GiB) instead of 1e9. With no KV reading (smoke's stand-in server has no KV gauges), #4/#5 read `na (server reported no KV-cache usage)` instead of blank.
- **Workbook (127/327):** #4 label "KV-cache HBM usage, GiB"; Output Fields lists the real metric keys and the TPOT/GiB/smoke notes (4 cells).
- **Checked:** against the AMD smoke server end to end through the generated parser and metric summary.

## 2026-10-01 — 227/427 KV cache stress: no fake smoke KV numbers, standard TPOT, GiB, #3 renamed

- **`vllm-kvcache-nvidia/scripts/tiny_kv_server.py` (smoke only):** no longer serves constant `vllm:kv_cache_usage_perc 0.12` / `kv_cache_usage_bytes 128849018` gauges or prints "GPU KV cache usage: 12%" / "Available KV cache memory: 1.0 GiB" log lines. Smoke #4 and #5 now read `na (server reported no KV-cache usage)` instead of 12% and 0.129 GB.
- **`benchmark_serving.py`:** TPOT = (end-to-end - TTFT) / max(output tokens - 1, 1), with output tokens from the server's `usage.completion_tokens` (requested via `stream_options.include_usage`), else the chunk count. It used to be the mean gap between stream chunks (per chunk, not per token; the whole post-TTFT time with fewer than two chunks). Peak KV bytes are divided by 1024^3 (GiB, the unit of vLLM's "Available KV cache memory" that the log-based path multiplies by) instead of 1e9. A missing KV reading is the na text, not blank; the summary row carries `kv_cache_usage_peak_pct`.
- **#3 renamed:** key `time_per_output_token_tpot_under_high_kv_pressure_msec` -> `tpot_msec` (the run never forces high KV occupancy; #5 shows what it reached). #4 label is "GiB".
- **Workbook (227/427):** Metrics, raw examples, output fields, methodology, and constraints cells updated (8 cells).
- **Not changed:** run duration, server launch flags, and AMD 127/327 (its own collector; same chunk-gap TPOT and 1e9 division, no fake smoke gauges).
- **Checked:** collector against the real smoke server end to end through the generated parser and metric summary (TPOT 1.23 ms for 16 tokens at ~1 ms/chunk; #4/#5 print the na reason).

## 2026-10-01 — 126/326 JAX XLA: vocab_size parameter (32000, as 226/426)

- **Workbook:** 126 and 326 gain `vocab_size` as Parameter_11 (Workload_Definitions BD27/BD99) and a `vocab_size` row (32000 smoke/baseline/extended) in Parameters_SmokeBaselineExtend (rows 1258-1259). Smoke/baseline/extended commands end with `--vocab-size 32000`; `sync_matrix_profile_commands.py --check` passes for all 128 workloads. E27/E99 describe it and the AS27/AS99 "vocab_size is 128 here" note is removed. Generated 126 config now has `vocab_size: 32000`, which `collect_jax_xla.py` passes to the shared forward-pass script, so all four JAX workloads run the same model.
- **Not changed:** `config/workload_parameters.yaml`. `generate_workload_parameters.py` already fails against the current workbook (it treats "-" Parameter cells as parameters), independent of this change.

## 2026-10-01 — 126/226/326/426 JAX XLA: one real transformer on both vendors

- **`jax-xla-amd` (126/326):** now ships the same `gpu-bench-jax-xla-forwardpass.py` and `collect_jax_xla.py` as `jax-xla-nvidia`; `collect_workload.py` is a thin adapter that copies `raw_results.csv` to the harness raw file. The old AMD collector timed a `tanh(x @ W)` stack (no embedding, attention, MLP, or output projection), reported its positions as tokens and its FLOPs as transformer TFLOPS, ignored dtype and num_heads, and fell back to PyTorch (still labeled JAX, `rocm:0`) when JAX failed.
- **`gpu-bench-jax-xla-forwardpass.py` (all four):** TFLOPS now includes the output projection (2·b·s·h·vocab). Each timed chunk size is compiled before timing (the first chunk's JIT compile used to land in the timed window: smoke latency 105 ms -> 0.085 ms on a CPU test). Peak memory falls back to nvidia-smi or rocm-smi, then `na (peak memory not reported)` instead of the output tensor size + 0.01 GB. `collect_jax_xla.py` accepts `peak_hbm_gb=na` with a `PEAK_NA` reason line.
- **Workbook:** the same five Metrics on all four (`forward_latency_msec`, `tokens_per_sec`, `tflops` "full forward pass", `jit_compile_msec`, `peak_hbm_gb`); description, objective, tools, methodology, format, example, fields, success, notes, and constraints cells rewritten (47 cells). 126/326 note that vocab_size is 128 there (226/426 pass 32000).
- **Not changed:** Software Framework cells; attention is single-head over the full hidden size (num_heads only sets head_dim), as before.
- **Checked on CPU JAX 0.10.2** (GPU lookup shimmed): AMD adapter -> collector -> generated parser/validator/printer prints all five; FLOPs match the formula. Not run on a GPU.

## 2026-10-01 — 124/224/324/424 SDXL: real denoising step time and cold first-image latency

- **#4 `step_time_ms` (`sdxl-diffusers-amd` and `-nvidia` `scripts/infer_sdxl.py`):** timed with diffusers `callback_on_step_end` (GPU-synchronized timestamp at the end of every step); the value is (last - first) / (steps - 1) per batch call, averaged over batches. It used to be pipeline time / steps (text encoders, VAE decode, and PIL conversion charged to every step), and on AMD also divided by the batch size. The real-model path needs `num_inference_steps` >= 2 (baseline 30, extended 50); smoke's tiny stand-in already timed only its denoising loop and is unchanged.
- **#5 `first_image_latency_s`:** the warmup call is now one full image at the yaml step count and is timed (cold: includes one-time kernel compile / autotune). It used to be an untimed 2-step warmup, after which AMD timed an extra already-warm image and NVIDIA used the first timed image. AMD no longer runs that extra image; NVIDIA's warmup grows from 2 steps to the full count.
- **Workbook:** #4 "Denoising step time per batch, ms", #5 "First-image latency, cold" on all four; Output Fields cells describe the timing.
- **Checked with a fake diffusers pipeline (batch 2, 10 steps):** step time 20 ms (old formula: 12.6), first image 0.20 s, warmup is a single full image, AMD runs no extra solo image. Callback signature checked against diffusers 0.40.0. Not run on a GPU.

## 2026-10-01 — 122/222/322/422 ResNet-50 inference: GPU utilization sampled during the timed loop

#4 GPU utilization was read once, after the timed loop had finished and synchronized, so it reported an idle GPU (about 0%). NVIDIA returned 0.0 when nvidia-smi failed.

- **`resnet50-inference-amd/scripts/collect_workload.py` (122/322) and `resnet50-inference-nvidia/scripts/gpu-bench-resnet50-pytorch-inference.py` (222/422):** new `UtilSampler` reads utilization every 0.1 s on a background thread during the timed iterations; a reading counts only if it finished before the loop ended. The metric is the mean of those readings, or `na (timed loop too short to sample)` / `na (<tool> gave no utilization reading)`. AMD reads amdgpu `gpu_busy_percent` from sysfs (highest AMD card) with rocm-smi / amd-smi as fallback; NVIDIA uses nvidia-smi `utilization.gpu`.
- **`collect_resnet50_infer.py` (222/422):** accepts `gpu_utilization_percent=na` in the RESULT line plus a `UTIL_NA batch_size=... reason=na (...)` line; the summary averages only batches with a number.
- **122/322 #5 peak GPU memory:** `torch.cuda.reset_peak_memory_stats()` before each batch size (every later batch reported the largest peak so far). NVIDIA already reset it.
- **Workbook:** 122/222/322/422 notes and tools cells describe the sampling (122 had said util is hard-coded 1.0; 322/422 described an "inference server and training for 5min"). Raw output examples left as recorded.
- **Checked:** sampler with fast, slow, and failing readers (mean / too-short / no-reading); NVIDIA wrapper with an na batch and a numeric batch. Not run on a GPU.

## 2026-10-01 — 119/219/319/419 PyTorch microkernels: shared scripts, six separate GEMM/Conv2d metrics

- **`torch-micro-amd` (119/319):** now ships the same `gemm.py`, `conv2d.py`, and `collect_torch_micro.py` as `torch-micro-nvidia`; `collect_workload.py` is a thin adapter that runs `collect_torch_micro.py` and copies its `raw_results.csv` to the harness raw file. The old AMD collector wrote 1.0 with status ok when a value was missing or a script failed, averaged GEMM and Conv2d into one latency/TFLOPS/traffic value (e.g. 108 and 1.4 TFLOPS -> ~55), counted Conv2d FLOPs without the x2 and bytes as input only, and ignored yaml dtype.
- **`collect_torch_micro.py` (all four):** metrics are `gemm_time_usec`, `gemm_tflops`, `gemm_bandwidth_gb_s`, `conv_time_usec`, `conv_tflops`, `conv_bandwidth_gb_s`. Removed `mean_minimum_traffic_gb_s` (averaged GEMM and Conv2d bandwidth) and `gemm_throughput_tflops` (duplicate of `gemm_tflops`). A missing value now fails with a message instead of a KeyError.
- **Workbook:** the same six Metrics on 119/219/319/419; format, granularity, example, fields, success, and notes cells rewritten for all four; 119 description/methodology (hard-coded fp16 and batch size) and 419 description/tools/details ("PyTorch-ROCm TorchBench", "Git provided TorchBench scripts") corrected.
- **Checked with stub kernels:** AMD adapter -> collector -> generated parser/validator/printer prints all six; a missing value exits 1. Not run on a GPU.

## 2026-10-01 — 117/317 run rocblas-bench; 217/417 achieved_compute_tflops found

- **`rocblas-gemm-amd/scripts/collect_workload.py` (117/317):** now runs the repository-local `rocblas-bench` (built by the rocblas-clients-build mixin, `third_party/rocBLAS/build/release/clients/staging`, or `ROCBLAS_BENCH`) with the yaml dtype, M/N/K, transposes, alpha/beta, lda/ldb/ldc, `warmup_iters` -> `--cold_iters`, `num_iterations` -> `-i`, `norm_check` -> `-v`, and `-f gemm` (`gemm_strided_batched` when batch_count > 1). Values are read by name from its `rocblas-Gflops` CSV header. It fails if rocblas-bench is missing, exits non-zero, or prints no row. Before, it timed `torch.matmul` in float32 and wrote it under rocblas-bench-like names; rocblas-bench was compiled but never run.
- **117/317 metrics:** #1 rocBLAS GEMM throughput, GFLOPS (`rocblas_gflops`); #2 Time per GEMM call, us (`rocblas_gemm_us`, rocblas-bench's `us`); #3 CPU reference GFLOPS (`cpu_gflops`); #4 Relative error vs CPU reference (`norm_error_1`). #2 used to be NOT FOUND (column `us`). With norm_check=0, #3/#4 read `na (norm_check is 0)`.
- **`cublas-gemm-nvidia/scripts/collect_cublas_gemm.py` (217/417):** CSV column `tflops` renamed `achieved_compute_tflops`, so #1 is found (it was NOT FOUND). Value unchanged; the harness RESULT line still prints `tflops=`.
- **Workbook:** 117/317 Metrics and description/objective/tools/methodology/format/example/fields/success/notes/constraints cells rewritten for rocblas-bench (117 had said "This does not execute rocblas-bench"). 217 raw example header and execution details use `achieved_compute_tflops`; 417 raw example RESULT lines now show the binary's real field names (`memory_bandwidth_gb_s=`, `norm_error_1=`). Workload names unchanged.
- **Not changed:** Software Framework cells (117/317 still list PyTorch-ROCm, so setup still installs PyTorch, now unused by this collector).
- **Checked with a fake rocblas-bench:** command line, CSV, generated parser, and metric summary (`rocblas_gflops=101361`, `rocblas_gemm_us=1355.93`, ...; na text with norm_check=0). Not run on a real MI300X.

## 2026-10-01 — 116/216/316/416 RCCL/NCCL: "na (requires at least two GPUs)" on one GPU

On one GPU nothing crosses a GPU-to-GPU link: bus bandwidth is meaningless, algorithm bandwidth is a local copy, and latency is library call overhead. These metrics now read `na (requires at least two GPUs)` instead of a number or a blank.

- **Generated `parse_results.py` (`scripts/materialize_generated_harness.py`):** a metric column with no numbers whose rows all hold the same `na (<reason>)` text is reported in summary.json as that text (it used to vanish). `print_metric_summary.py` prints it. Generated `validate_results.py` skips thresholds on such a value instead of crashing on `float()`.
- **`nccl-bandwidth-nvidia/scripts/collect_workload.py` (216/416):** busbw, algbw, and latency are the na text when the communicator has fewer than two GPUs (the count `nccl_bw` actually used). Before, busbw was blank and algbw/latency were reported. Unchanged at two or more GPUs.
- **`rccl-bandwidth-amd/scripts/collect_workload.py` (116/316):** `rccl_perf.cpp` always uses a one-rank communicator on GPU 0, so all three metrics are the na text on every host. The five collectives still run, and the run now fails if a binary is missing, exits non-zero, or prints no size line (it used to write 1.0 with status ok). If the program gains multiple ranks, bandwidth is taken at the largest size and latency at the smallest (it used to keep only the last line). Transcripts go to `rccl_<collective>.txt`; new columns `num_gpus`, `bytes`. `rccl_perf.cpp` unchanged.
- **Workbook:** 116/316 Metrics now match 216/416 (`... at max message size`, `Latency at min message size`). Description, objective, methodology, format, example, fields, success, notes, and constraints cells for all four rows rewritten to match the code (they claimed every AMD binary runs all-reduce, a 1.0 fallback, last-line parsing, NVIDIA "min_bytes only", and nccl-tests/MPI on 416).
- **Correction to the findings list:** the five AMD binaries are copies, but each runs the collective named by its file name (argv[0]), not all-reduce.
- **Checked:** stubbed AMD and NVIDIA runs, generated parser/validator/printer end to end (prints `busbw_gb_s=na (requires at least two GPUs)`, validation passes), NVIDIA with 2 fake GPUs still reports numbers, AMD failure path exits 1.

## 2026-10-01 — 114/214/314/414 memcpy: latency at min size, bandwidth at max size, per direction

#4 Transfer latency was the mean time per copy over every transfer size (1 KB to 1 GB), so the 1 GB copies (milliseconds) swamped it; 214/414 also kept H2D only. 214/414 #1–#3 were means over every size, so small, latency-bound copies pulled the bandwidth down.

- **`hipmemcpy-bandwidth-amd/scripts/parse_results.py` (114/314):** new `add_min_size_direction_latency` writes `latency_us_h2d`, `latency_us_d2h`, `latency_us_d2d` = time per copy at each direction's smallest transfer size (the twin of the existing max-size `bandwidth_gbps_<dir>`). Collector and `hip_memcpy_bw.cpp` unchanged.
- **`cuda-memcpy-nvidia/scripts/collect_workload.py` (214/414):** `h2d/d2h/d2d_bandwidth_gb_s` are written on the max_bytes row only and new `h2d/d2h/d2d_latency_us` on the min_bytes row only; other rows are blank, so the parser's mean (which skips blanks) is that one measurement. `transfer_latency_us` is removed. Per-size output stays in `memcpy_<kind>_<size>.txt`. `cuda_memcpy.cu` unchanged.
- **Workbook:** Metrics for 114/314 are #1–#3 bandwidth at max size and #4–#6 H2D/D2H/D2D latency at min size; 214/414 the same plus #7 pageable ratio (bandwidth labels "at max transfer size", not "Mean"). Output Fields, Parser Notes (114/314 also drop the stale "falls back to 1024-byte rows"), 214/414 Raw Output Example and 214 Execution Description updated.
- **Checked with stubs:** NVIDIA 1 KB–1 GB sweep: H2D bandwidth 16.5 -> 25.0 GB/s, latency 14,333 -> 2.04 us (fake device). AMD parser: `latency_us` blind mean 4,774 us vs `latency_us_h2d/d2h/d2d` 10.0/11.0/6.0 us.

## 2026-10-01 — 110/210/310/410 NUMA cache sweep: same four metrics on all four

- **Workbook Metrics, 210 (I47) and 410 (I119):** now the same as 110/310: #1 Cache-tier latency, #2 Local DRAM latency, #3 Local DRAM pointer-chase bandwidth, #4 Cache misses/sec. 210 drops #5 Remote NUMA node latency and #6 Cross-socket NUMA ratio; 410 gains #4.
- **Not changed:** `numa-cache-collector` still writes `remote_numa_node_latency_nsec` and `cross_socket_numa_penalty_ratio` to the raw file on all four; they are just not listed metrics. Other 210/410 description cells were left as they are.

## 2026-10-01 — 208/408 iperf3: jitter, packet loss and retransmits no longer halved

- **`iperf3-nvidia/files/scripts/collect_workload.py`:** `udp_jitter_ms` and `packet_loss_rate` are written on the UDP row only and `tcp_retransmit_count` on the TCP row only; the other row is blank. They were written on both rows (0.0 on the protocol that does not measure them), and the parser's mean over a TCP row and a UDP row halved #3, #4, and #5. Blanks are skipped by the mean. This matches `iperf3-amd` (108/308), which already did this.
- **Workbook:** #4 label is now `Packet loss, percent (packet_loss_rate)` in I9, I45, I81, I117 (the value is iperf3 `lost_percent`, so 1.5 means 1.5%). The key is unchanged. 208/408 Parser and Normalization Notes (Y45, Y117) no longer say "TCP fields may be copied onto UDP rows".
- **Workbook, stale text:** Validation Objective for 308 (K81) and 408 (K117) said "NIC ... between VMs"; they now match 108 and 208 (loopback on one host; 408 notes `BENCHMARK_IPERF_PEER`). K9/K81 reworded to "over loopback (127.0.0.1) on one host. This is not a NIC or VM-to-VM test." Parser and Normalization Notes for 108 (Y9) and 308 (Y81) drop "UDP throughput may be floored at 1e-6 Gb/s" (the collector has no floor) and say which row each metric is on.

## 2026-10-01 — 108/208/308/408 iperf3: #2 labeled as loopback

- **Workbook (Metrics, cells I9, I45, I81, I117):** `#2: UDP throughput (udp_throughput_gbps)` is now `#2: UDP loopback throughput (udp_throughput_gbps)`. The client connects to 127.0.0.1 (AMD always; NVIDIA unless `BENCHMARK_IPERF_PEER` is set), so #2, like #1 TCP loopback throughput, measures the host's loopback path, not the NIC. The key is unchanged, so no column, collector, or parser changes.

## 2026-10-01 — ROCm setup reloads the amdgpu driver instead of rebooting

First-time ROCm setup used to reboot once after the driver/firmware install. It now reloads the driver in place and reboots only when the reload cannot be verified.

- **Step 02 is `apt-get upgrade -y`** (was `apt upgrade -y`) in `scripts/lib/rocm_install_24_04.sh` and `rocm_install_26_04.sh`. `apt-get upgrade` never installs new packages, so a new Linux kernel is kept back and the running kernel stays the one in use. Install kernel updates separately when wanted.
- **New `scripts/lib/amdgpu_reload.sh` (`amdgpu_reload_instead_of_reboot dkms|firmware`),** sourced by `scripts/lib/rocm_install.sh`. It runs `update-initramfs -u`, `modprobe -r amdgpu`, `modprobe amdgpu`, waits until every AMD GPU PCI device is a KFD compute node, and on 24.04 checks that the loaded amdgpu is the DKMS build under `/lib/modules/$(uname -r)/updates/`. modprobe runs with a deadline, so a stuck unload cannot hang setup. Protected file.
- **`rocm_install_runtime` (24.04 step 12, 26.04 step 10):** saves `stage3`, tries the reload, and on success clears the stage and returns (status step `sudo modprobe -r amdgpu && sudo modprobe amdgpu`). On failure it reboots exactly as before and the systemd resume service continues setup. 24.04 reloads onto AMD's DKMS driver; 26.04 reloads the in-tree driver so it loads the new `amdgpu-dkms-firmware` files.
- **Fallback to reboot when:** `ROCM_RELOAD_INSTEAD_OF_REBOOT=0`, no AMD GPU on PCI, amdgpu in use, (24.04) no DKMS build for the running kernel, modprobe fails or times out (`AMDGPU_UNLOAD_TIMEOUT` 180 s, `AMDGPU_LOAD_TIMEOUT` 600 s), fewer GPUs than PCI devices within `AMDGPU_INIT_WAIT` (300 s), or (24.04) the loaded module is not the DKMS build.
- **`scripts/templates/setup_rocm_reboot_skeleton.sh`:** first-run notice and `--help` describe the reload. New `grant_gpu_access_this_session` after `rocm_add_repository`: a non-root user just added to `render`/`video` (groups apply at next login, which a reload no longer forces) gets an ACL on `/dev/kfd` and `/dev/dri/*` for the current boot; `acl` added to the base package list. If that fails, setup says to log out and back in or run `newgrp render`.
- **Not changed:** the `wall` completion message (`setup.sh now complete`) and the systemd resume service, both still needed for the fallback reboot and for loops that redirect output. `config/platform_policy.yaml` keeps `reboots: 1` as the upper bound.
- **Docs:** `docs/rocm-reboot-install-contract.md` (new "Driver Reload Instead Of Reboot" section), AGENTS.md, `docs/generation-workflow.md` (also drops the stale "two expected reboots"), `config/platform_policy.yaml` notes.
- **`scripts/self_check_generated_repo.sh`:** `scripts/lib/noninteractive_root.sh` and `scripts/lib/amdgpu_reload.sh` are required files (both are sourced by `rocm_install.sh`).
- **Tests:** new `tests/test_amdgpu_reload.py` (15 stubbed tests: success paths, every fallback, and the install branch on both Ubuntu versions).
- **Not yet run on a real VM.** Supersedes the operator note in the entry below: when the reload works, first-time 26.04 setup no longer reboots.

## 2026-10-01 — Setup no longer hangs on sudo's pty when output is redirected (26.04 loop hang)

`bash run_benchmark.sh --smoke >> log 2>&1` on a fresh Ubuntu 26.04 VM stopped forever in workload 301's automatic setup: `sudo amdgpu-install` -> `apt-get` ran on a pty that sudo created (`Defaults use_pty`, stdin still the SSH terminal), apt-get restored that terminal after installing, the kernel stopped it with SIGTTOU, and nothing resumed it. Ctrl-C did not reach it.

- **New `scripts/lib/noninteractive_root.sh` (`run_noninteractive_root`):** runs the command directly when root, through `sudo` otherwise; replaces a terminal stdin with `/dev/null` (pipes and heredocs kept); ignores SIGTTOU/SIGTTIN in the command; defaults `DEBIAN_FRONTEND=noninteractive`; accepts leading `VAR=value` arguments like sudo. Sourced by `scripts/lib/rocm_install.sh` and the ROCm setup skeleton. Protected file.
- **`scripts/lib/rocm_install_26_04.sh` (21) and `rocm_install_24_04.sh` (29):** every executed `sudo` is now `run_noninteractive_root` (amdgpu-install, apt/apt-get, tee/gpg/apt-key pipelines, depmod, usermod, mkdir, make install, reboot). Status-log text is unchanged. Line endings preserved (26.04 file is CRLF).
- **`scripts/templates/setup_rocm_reboot_skeleton.sh`:** `run_privileged` calls `run_noninteractive_root`; the bare `apt-get` installs for lmbench, fio, iperf3, stress-ng, and linux-tools go through `run_privileged`.
- **`scripts/ensure_setup.sh`:** automatic setup runs `bash setup.sh --assume-yes </dev/null`, so nothing under it can inherit the caller's terminal.
- **Resume service:** `.setup_state` is written (after `scripts/build.sh`) before `cleanup_resume_service`. When setup runs as the resume service (`--resume-from-service`), cleanup disables the unit with `--no-reload` and removes the file without `systemctl daemon-reload`. The reload had reloaded the running unit without `TimeoutStartSec=infinity`, and systemd SIGTERMed setup.sh before `.setup_state` (26.04 VM, 13:53:13).
- **Docs:** AGENTS.md, `docs/host-prerequisite-contract.md`, `docs/generation-workflow.md`, and checklist 3.27 require `run_privileged` / `run_noninteractive_root` instead of raw `sudo DEBIAN_FRONTEND=noninteractive apt-get`.
- **Operator note:** first-time ROCm setup on 26.04 reboots once (firmware). Run `bash setup.sh --assume-yes` in each repo before starting a multi-workload loop; otherwise the loop's first workload triggers that reboot. Loops should also pass `</dev/null` to `run_benchmark.sh`.
- **Not changed:** `/etc/sudoers`; NVIDIA/CPU skeletons (no sudo); `sglang-*-nvidia` overlays (`SUDO=sudo` only when not root).

## 2026-10-01 — 109/209/309/409 multichase: #5 Remote DRAM latency kept on all four, shown when not measured

All four workloads use the same `multichase-numa-amd` collector. #5 was missing from the 409 row only, and the 209 row still described an older harness that bound every tier, including remote_dram, to NUMA node 0.

- **`multichase-numa-amd/files/scripts/collect_multichase.py`:** when remote_dram cannot run (fewer than two NUMA nodes from `numactl --hardware`, or `--membind=1` not permitted) it writes a `remote_dram` row with blank `latency_ns` and the reason in `error_message`, instead of dropping the tier. The "at least two samples" check counts measured tiers only. On two or more nodes remote_dram still runs with `--cpunodebind=0 --membind=1`.
- **`scripts/materialize_generated_harness.py` (generated `parse_results.py`):** when a pivoted tier/benchmark/direction group has no value for a column that is pivoted, `summary.json` records that key as `"not measured"` instead of omitting it.
- **`scripts/print_metric_summary.py`:** `not measured` values are printed (e.g. `#5: Remote DRAM latency, ns (latency_ns_remote_dram); latency_ns_remote_dram=not measured`) instead of the line being omitted. A metric with no column at all (NOT FOUND) is still not printed.
- **Workbook rows 109 (10), 209 (46), 309 (82), 409 (118):** 409 Metrics gains #5, so all four Metrics cells are identical. Execution Description, Validation Objective, Command Methodology/Execution Details, Parser Notes, and Known Runtime Constraints now say remote_dram uses the detected NUMA node count (not `num_numa_nodes`, which is metadata only) and is reported as not measured on a single-node host. 209/409 Raw Output Example shows the current CSV (the old 409 `SUMMARY {...}` line and the 209 remote_dram 75.7 ns row, measured on node 0, are gone).
- **Not changed:** the `num_numa_nodes` parameter and `--num-numa-nodes` flag remain (metadata only).

## 2026-10-01 — 108/208/308/408 iperf3: received throughput, real UDP rate

#1 TCP loopback throughput and #2 UDP throughput reported what the sender pushed, and UDP was capped at 1 Mbit/s (about 0.001 Gb/s), so #2 echoed the configured cap rather than a measured rate.

- **`iperf3-amd` and `iperf3-nvidia` `collect_workload.py`:** #1 and #2 (and `bits_per_second`) now come from `end.sum_received.bits_per_second`, the receiver side. For older iperf3 UDP output with no `sum_received`, the sender rate in `end.sum` is scaled by `(packets - lost_packets) / packets`. TCP retransmits still come from `sum_sent`. AMD records an error (blank value) instead of 0 when the JSON has no receiver figure, as NVIDIA already did.
- **UDP rate:** default `-b` is 10G (was 1M); an empty or 0 `bandwidth_limit` uses the default instead of 1M. **AMD 108/308 now reads `bandwidth_limit`**; it previously looked only for `bandwidth`/`udp_bandwidth`, so the workbook parameter was ignored and UDP always ran at 1M.
- **Workbook:** `bandwidth_limit` is 10G for smoke/baseline/extended (Parameters_SmokeBaselineExtend rows 72, 366, 700, 994) and in all twelve run-command cells (F/G/H of rows 108, 208, 308, 408). Execution Description, Command Methodology, Known Runtime Constraints, and 308/408 Output Fields describe the new rate and receiver-side fields.
- **Not changed:** the peer is still loopback 127.0.0.1 (NVIDIA can use `BENCHMARK_IPERF_PEER`; AMD cannot), so #1/#2 measure host CPU/kernel loopback, not the NIC. Metric names and keys are unchanged. A high UDP rate on loopback can raise #3 jitter and #4 packet loss; no limits exist for these metrics.

## 2026-10-01 — 201/401: VBIOS revision match metric removed

`#6: VBIOS revision match when a required revision is configured (vbios_revision_match)` is deleted from NVIDIA System Config Verification (201/401). It had a value only when `vbios_inforom_versions` named a specific VBIOS version; the default is `present`, so it was always blank and `print_metric_summary.py` omitted its line. Output Fields and Success Criteria already described five metrics.

- **`system-config-nvidia/files/scripts/collect_workload.py`:** no `vbios_revision_match` column; the `vbios_inforom_versions` comparison is removed. The detected VBIOS version is written to `<run-dir>/vbios_version.txt` for information only. Metric #3 (`vbios_string_present`) still requires a VBIOS Version string.
- **Workbook rows 201 (38) and 401 (110):** Metrics end at #5; Raw Output Example drops the column. 201 Execution Description says `vbios_inforom_versions` is accepted but not compared.
- **Not changed:** the `vbios_inforom_versions` parameter (Parameter_04) and its `--vbios-inforom-versions` run-command flag remain, so existing commands still work; the value no longer affects any metric.

## 2026-10-01 — 201/401: driver compliance column renamed to the spec key

- **`system-config-nvidia/files/scripts/collect_workload.py`:** CSV column `driver_version_compliance` is now `driver_compliance_percent`, the key in metric #4 "Driver version compliance percent". The summary printed #4 as NOT FOUND because neither the key nor the label matched the old column name. No `gate.json` exists for this component, so no limit was affected.
- **Workbook rows 201 (38) and 401 (110):** Raw Output Example now matches the collector's actual header (adds `vbios_revision_match`, uses `driver_compliance_percent`) and shows `vbios_string_present` as 1.0 (the collector writes 1/0, not 100). 401 Raw Output Format now says one aggregate row duplicated as two samples, as 201 already did.

## 2026-10-01 — 101/301: firmware compliance metric removed

`#3: Firmware compliance percent (firmware_compliance_percent)` is deleted from System Config Verification (101/301). It had a value only when the yaml named an expected firmware version, which nothing supplied, so it was always blank and its 100% gate was skipped without a message.

- **Workbook rows 101 (2) and 301 (74):** Metrics now #1 ROCm package mismatch count, #2 Kernel/driver mismatch count, #3 Driver compliance percent, #4 Permission error count. Raw Output Example and Output Fields / Metrics to Parse drop the column (301's Output Fields now lists the four metric keys instead of stale names). 301 Success Criteria says 4 metrics; Command Methodology no longer lists firmware version.
- **`system-config-amd/files/scripts/collect_workload.py`:** no `firmware_compliance_percent` column; `declared_firmware()` and `firmware_percent()` removed. The detected firmware/VBIOS revision is written to `<run-dir>/firmware_version.txt` for information only (no pass/fail).
- **`system-config-amd/gate.json`:** removed `firmware_compliance_percent_min`/`_max` and the `firmware-compliance` entry in `required_metric_lines`.
- **Not changed:** 201/401 `#6 vbios_revision_match` has the same configured-only design. `driver_compliance_percent` (101/301 #3) is 100 exactly when the amdgpu half of `kernel_driver_mismatch_count` is 0.

## 2026-10-01 — 203/403 use the same three metrics as 103/303

NVIDIA CPU + System Stress (203/403) now reports exactly the AMD metrics: #1 Peak GPU junction temperature (`peak_gpu_junction_temp_c`), #2 Sustained GPU power (`sustained_gpu_power_w`), #3 GPU ECC error count (`gpu_system_ecc_error_count`).

- **`system-stress-nvidia/files/scripts/collect_workload.py`:** writes one CSV row per second with the same columns as `system-stress-amd` (was one aggregate row duplicated as two samples). Temperature is the hottest GPU's `temperature.gpu`, power the highest per-GPU `power.draw`; `parse_results.py` takes the max of `peak_*` and the mean of `sustained_*`. ECC is `ecc.errors.uncorrected.volatile.total` summed over GPUs (was a count of non-zero correctable/uncorrectable lines) and is blank when ECC is `[N/A]`. All GPUs are read (was the last line only). Peak CPU temperature (`peak_cpu_package_temp_c`) and its `/sys/class/thermal` polling are removed; `thermal_throttle_event_count` stays as a non-metric column, counted as entries into `hw_thermal_slowdown`.
- **Workbook rows 203 (40) and 403 (112):** Metrics, Output Fields / Metrics to Parse, Raw Output Format, Raw Output Example, and Validation Objective match the new output; 203 Execution Description, Command Tools, Command Methodology, and Command Execution Details no longer mention host thermal zones or `nvidia-smi -q -d ECC`. Removed the `*` on "Thermal throttle events" and the stale 'Not Active' notes.
- **Not changed:** on NVIDIA, `temperature.gpu` is the GPU core temperature, not a junction/hotspot reading; the shared label "Peak GPU junction temperature" is accurate for AMD only. NVIDIA still has no `gate.json`, so no temperature/power/ECC limits are applied for 203/403. Neither collector applies GPU load (`gpu_load_percent` is unused on NVIDIA), so sustained GPU power is measured under CPU-only stress.

## 2026-10-01 — Remove the nested template copy once a workload passes

Generated repositories no longer keep `ai-agent-gpu-benchmark-repo-generator_copy/` after generation. Its ~830 duplicated files put the deepest paths at 267–303 characters, so copying a finished batch on Windows failed with path-too-long errors.

- **New `scripts/remove_template_copy.py --repo-root <repo>`:** saves each resolved component's `gate.json` to `results/component_gates.json`, deletes the nested `*_copy/` (Windows long-path safe; read-only files handled), and records `template_copy_removed_at` in `results/generation_manifest.json`. `template_copy_path` and `template_copy_sha256` stay as the provenance record. It refuses to run from inside the copy, only deletes top-level `*_copy` folders that contain generator markers, and is safe to re-run. `--dry-run` lists what it would delete.
- **`scripts/create_one_workload.py`:** removes the copy after a workload passes validation. A failed workload keeps its copy for debugging. `--keep-template-copy` opts out. In reuse mode the VM copy step first deletes a stale `*_copy` folder under `/opt/benchmarks/<repo>`, so the VM mirrors the local tree.
- **`self_check_generated_repo.sh` / `smoke_check_generated_repo.sh`:** a present copy must still be complete. A missing copy passes only when the manifest records `template_copy_removed_at`. The component-gate `forbidden_cli` check reads `results/component_gates.json` when the copy is gone, and prints `NOT EVALUATED` instead of skipping silently when neither source exists.
- **`schemas/generation_report.schema.json`:** adds `template_copy_removed_at` (date-time).
- **`prepare_github_publish.sh`:** strips `scripts/remove_template_copy.py` and `results/component_gates.json`.
- **Tests:** `tests/test_remove_template_copy.py`; `scripts/test_nested_template_copy.sh` now checks removal and the manifest record.
- **Docs:** AGENTS.md, AI_AGENT_INSTRUCTIONS.md (Completion gates, root cleanup), generation-workflow.md, repository-template.md, README.md, AI_AGENT_HANDOFF.md, SUBMISSION_CHECKLIST.md item 4.9.
- **Not changed:** `create_generated_repo.py` still creates the copy and leaves it in place, because generation steps run from it. The legacy `create_generated_batch.py` (not for agent use) does not remove it; run the new script afterward if you use it.

## 2026-09-29 — Fresh-VM fixes from the /opt/benchmarks loop (Project277–280)

A refreshed VM with all 32 repos installed together exposed setup steps that had only worked because earlier development had already configured the machine. Each fix is the smallest change that removes that dependency.

- **201–232 host Python:** the CPU and NVIDIA setup skeletons and the four NVIDIA vLLM/SGLang overlay `setup.sh` files use `/usr/bin/python3` unless `BENCHMARK_PYTHON` is set. An interactive root `PATH` put the image's uv Python 3.11 first, and Ubuntu 24.04 has no `python3.11-venv`, so strict setups (206–213, 227–230) exited in apt.
- **301–332 ROCm firmware:** `setup_rocm_reboot_skeleton.sh` no longer treats `/opt/rocm/bin/rocm-smi` alone as a ready runtime. When `/lib/firmware/updates/amdgpu` and `/lib/firmware/amdgpu` are both empty it runs `rocm_install_runtime`, which installs `amdgpu-dkms-firmware` and reboots once. The refreshed 26.04 image had ROCm userspace but no GPU firmware, so the MI300X never initialized.
- **401–426 CUDA toolkit:** on Ubuntu 26.04 the NVIDIA skeleton installs `cuda-toolkit-13-3` (same check as the SGLang setups) instead of `cuda-nvcc-13-1`. Repos set up at 13.1 refused to run after 430 installed 13.3 and moved `/usr/local/cuda`. Other Ubuntu versions are unchanged.
- **427–429 ninja:** the three vLLM NVIDIA setups `pip install ninja` into the venv before the FlashInfer warmup, and `flashinfer_warmup.py` puts the venv `bin` first on `PATH`. The setup-time warmup (new in TEMPLATE_92) needed `ninja`, which a fresh VM lacks until another setup installs it.
- **430–431 ZeroMQ path:** `nvcc_flashinfer_workspace` keeps nvcc temp files in the repo cache but exports `TMPDIR` as a short `/tmp/fi-<8 hex>` symlink to it. The repo-cache path exceeded the 107-byte Unix socket limit for SGLang's IPC sockets.
- **407 STREAM timeout:** the per-iteration allowance in both STREAM collectors scales with `array_size / 10M` (+120 s). Extended (40M × 32000) was killed at the old 1660 s limit.
- **124/224/324/424 SDXL load:** with `HF_HUB_OFFLINE=1`, `infer_sdxl.py` loads the cached fp16 snapshot directory instead of the repo id. Newer `huggingface_hub` rejects the fp16-only prefetch by repo id (`IncompleteSnapshotError`).
- **VM install location:** `scripts/create_one_workload.py` copies, sets up, and validates each repo in `/opt/benchmarks/<Workload Number>-<Repo Name>` (`--remote-root`, default `/opt/benchmarks`) instead of `/root/<...>`. Docs and the ROCm `/etc/motd` hint follow `REPO_ROOT`/`/opt/benchmarks`.
- **Runtime ledger location:** `scripts/update_runtime_ledger.py` writes `/var/opt/benchmarks/runtime_ledger.csv` by default (override with `BENCHMARK_RUNTIME_LEDGER` or `--ledger`) and prints `Runtime entry added to /var/opt/benchmarks/runtime_ledger.csv.` after each row, including failure rows. The seven overlay runners that wrote the ledger before the Metrics block (SDXL AMD/NVIDIA, SGLang NVIDIA ×2, vLLM NVIDIA ×3) now write it after, so that line follows the metrics as in every other repo.
- **Not changed:** the `vllm_rocm_sitecustomize.py` device-count recursion only occurs when the GPU is already down. Originals of every edited file are in `Project281_TEMPLATE_93_20260928/_backup_before_claude_20260929`.

## 2026-09-29 — Convolution bandwidth and cuDNN solver search

- **118/318:** CSV header `GB/s` is aliased to `memory_bandwidth_gb_s`. The substring fallback is removed from `resolve_metrics` (it reported batch size `n`=32). Headline metrics are the forward rows, with per-direction keys `<metric>_<direction>`. MIOpenDriver uses `kernel_width`, stride, groups, dtype (`convfp16` / `convbfp16` / `conv`), and same padding `k/2`.
- **218/418:** the harness honors dtype (FP16 and BF16 use tensor-op math), `conv_direction` (timed fwd, bwd-data, and bwd-weights), and `search_strategy` (timed `cudnnFind`; `solver_search_msec` is that wall time summed across directions, and was the constant 0.05). Fabricated 0.9×/0.8× backward TFLOPS are removed. Same padding `k/2` matches MIOpen. Expected runtime is about 3× per pass because three directions run; `num_iterations` is unchanged. The collector subprocess timeout is the direction count times the per-iteration allowance, plus 120 s for Find. `run_benchmark.sh` has no separate timeout. At the historical ~0.5 ms/iter, baseline 168000 × 2 passes is about 8 minutes and extended 514000 × 2 passes is about 26 minutes, plus three cold Finds per pass.

## 2026-09-28 — Honest metric names and a few measurement fixes

Source: `MetricsUpdates_for_TEMPLATE_00_92_20260928a.xlsx`, column “Cursor Instructions for TEMPLATE_00_92 updates”. Rows that say to leave the item for later (MIOpen bandwidth, cuDNN solver-search time) are unchanged. Rows with an empty instruction cell are unchanged.

- **Workbook `Workload_Definitions` Metrics** now name what the collectors actually record: GPU temperature, IOPS mean, TCP loopback gigabits/s, UDP gigabits/s, local DRAM pointer-chase bandwidth, cache misses per 1,000 instructions, 16 MB stride-128 read latency, 8-byte payload update rate, PyTorch matmul GFLOPS, sum of absolute residuals, minimum operand traffic, relative L1 of the checked columns, mean minimum-traffic estimate, MI300X FP64 matrix peak, FP64 tensor-core peak, modeled ResNet traffic, tanh matmul-stack tokens/s, decode throughput and TPOT at measured KV occupancy, peak KV-cache GB, VBIOS string present, even-word store pass rate, and peak GPU power. STREAM DDR5-efficiency `#5` is removed (107/207/307/407). SGLang completed-request percentage `#4` is removed on 230/430 and RadixAttn becomes `#4`. 304 uses the same even-word name as 104 because they share the AMD collector.
- **System config:** AMD mismatch count is uname `-r` versus `kernel_version` plus the amdgpu `version:` field versus `driver_version`. Firmware compliance is one 0/100 compare against `firmware_version` in the config, or blank when that version is not named. Driver compliance is that same amdgpu version compare, once per run. NVIDIA mismatch count compares the loaded nvidia module, `nvidia-smi`, and the libcuda SONAME. VBIOS presence is 0/1; a required revision in `vbios_inforom_versions` is a separate 0/100.
- **Health and stress:** PCIe width is the current link width and is blank when absent (102/202/302/402). AMD PCIe speed is sysfs `current_link_speed` and is blank when that file is missing (102/302). NVIDIA stress stores the max one-second power sample as `peak_gpu_power_w` (203/403).
- **ECC and correctness:** NVIDIA uncorrected and corrected counts are sums of the integer counters, with volatile and aggregate kept apart. AMD tensor cases are compliant when absolute error is within atol or the true relative error is within rtol (105/305).
- **NCCL:** `busbw_gb_s` is blank when `num_gpus` is less than 2; `algbw_gb_s` is still written (216/416).
- **FIO:** the mean job IOPS is `iops_mean`. Synthetic p95 and p99 copies are left blank.

## 2026-09-28 — Retune baseline and extended durations from the 2026-09-28 ledgers

- **Parameters:** `Parameters_SmokeBaselineExtend` duration knobs were rescaled from `aggregated_runtime_ledgers_101_201_301_401_20260928_9am.xlsx`, aiming at ~4:00 baseline (3–5 min) and ~12:00 extended (8–15 min). Where baseline and extended differ only in the knob, a two-point fit removed server start and load time before scaling. Smoke values are unchanged. Command columns were regenerated with `scripts/sync_matrix_profile_commands.py`.
- **multichase:** 109 and 309 `num_iterations` 1.33e9/3.73e9 → 2.9e9/8.8e9 (measured 1:46–2:00 and 4:46–5:24). 209 and 409 are unchanged.
- **lmbench `repetitions`:** 112 2/5 → 5/14 (1:26–1:33, 3:48–4:17). 312 baseline 3 → 5 (2:11–2:20); extended 9 is unchanged. 412 3/10 → 5/14 (2:14–2:16, 7:15–7:25).
- **KV cache `num_prompts`:** 127 397/1320 → 200/800 (6:14–7:14, 18:58). 327 397/1320 → 208/880 (5:40–6:40, 17:04–17:10). 427 450/1320 → 192/920 (6:39–7:04, 16:13).
- **NCCL `num_iterations`:** 216 1.1e6/1.52e6 → 480000/850000 (7:45–7:51, 19:49–21:02). 416 600000/1.52e6 → 330000/880000 (5:52, 19:08–19:29).
- **Torch micro `num_iterations`:** 219 420000/1230000 → 1140000/2750000 (1:38, 5:29–5:31). 419 → 860000/2000000 (2:04–2:05, 7:31).
- **JAX `num_iterations`:** 226 101450/424800 → 380000/760000 (1:08–1:10, 6:07–6:17). 426 101450/515850 → 380000/780000 (1:09, 7:25).
- **STREAM `num_iterations`:** 207 extended 25000 → 36000 (6:39–9:05). 407 14500/15600 → 24000/32000 (1:51–2:11, 4:44–4:49). Today's 407 rate is about half the 2026-09-24 rate, so 407 is aimed low.
- **ResNet-50 inference:** 422 `num_iterations` 6400/16200 → 4500/4600 (5:33–5:37, 45:11).
- **RAG:** 432 `query_count` 100/250 → 220/680 (1:57–2:09, 4:35).
- **Left unchanged:** 227, 228, and 229 are overlay-locked. `vllm-kvcache-nvidia`, `vllm-throughput-nvidia`, and `vllm-token-generation-nvidia` ship `config/benchmark_config.yaml`, and `generate_benchmark_config.py` does not write over it. The measured runtimes follow that yaml (227: 96/224 prompts at output_len 128; 228/229: output_len 16000/24000), not this sheet. Workbook edits do not reach those repos. 205 and 405 (overlay-locked), 105/305 correctness, and x01/x02 config/health checks are short by design.

## 2026-09-27 — Retune baseline and extended durations from the 2026-09-27 ledgers

- **Parameters:** `Parameters_SmokeBaselineExtend` duration knobs were scaled from `AggregatedRuntimeLedgers_20260927` so a linear repeat lands near 4:00 baseline (inside 3–5 min) and near 12:00 extended (inside 8–15 min). Smoke values are unchanged. Command columns were regenerated from that sheet.
- **NUMA pointer hops:** 110 `num_iterations` 6.3e9/1.85e10 → 2.5e9/7.4e9 (measured 9:56–10:00 and 29:57). 210 and 410 → 7.8e8/2.3e9 (measured ~27 min and 96 min / 78 min). 310 → 1.8e9/4.0e9 so the 10:46 and 17:09 baselines both fall inside 3–5 min, and the 55:59 extended falls near 12:00.
- **GUPS:** 113 and 313 `num_iterations` → 1600/1900. Measured baselines were 0:25–0:31 and extended 0:34–0:43. Table size and update count stay the same.
- **SGLang output length:** 131 → 840/1700 (baselines 6:36 and 9:17, extended 34:31). 331 → 890/1900 (15:11 and 33:09). 231 and 431 → 3250/7000 (baselines 9:50 and 9:20; 231 extended 23:27). Prompt counts stay 24/48.
- **Left unchanged:** 312 lmbench. The same `repetitions=3` baseline was 11:15 and 2:15, and extended was 12:44, so the long run is not a repetition-count problem. 112, 212, 213, 412, and 413 were already inside the windows.

## 2026-09-27 — FIO metric #1 label for 206/406 is IOPS p50

- **Workbook:** workloads 206 and 406 Metrics `#1` is now `IOPS p50 (iops_p50)`. The previous label said `IOPS aggregate, duplicated p50/95/99`. The collector column is unchanged.

## 2026-09-27 — SGLang serving metrics for 231/431 match 131

- **Workbook:** workloads 231 and 431 `Metrics` and `Output Fields / Metrics to Parse` now use the same p50 keys as 131 (`end_to_end_request_latency_p50_msec`, `ttft_p50_msec`, `time_per_output_token_tpot_p50_msec`, `inter_token_latency_itl_p50_msec`, `request_throughput_requests_sec`). The serving collector writes those columns. The old p99 names were calculated and then left out of the results file, so `#1` and `#2` (and 431's `#3` and `#4`) were skipped. Raw-output examples for 231 and 431 cite the p50 columns.

## 2026-09-27 — CUDA 13 convolution libraries, version-gated tensor_ir, component probes

- **cuDNN pin:** convolution components on CUDA 13 install `nvidia-cudnn-cu13==9.23.2.1` into that repo's virtualenv. `torch==2.13.0+cu130` pulls `nvidia-cudnn-cu13==9.20.0.48`, which does not ship `libcudnn_engines_tensor_ir.so.9`. Ubuntu 24.04 stays on `torch==2.7.1+cu128` and does not receive the CUDA 13 package. vLLM, SGLang, DistilBERT, BERT, and RAG are unchanged.
- **Host libraries:** a system `tensor_ir` is moved to `/opt/cudnn-host-extra` only when its version differs from the virtualenv `nvidia-cudnn` package. Setup wraps only the current repo's `bin/cudnn_conv`, and skips the wrap when the virtualenv already ships `tensor_ir`. `collect_cudnn_conv.py` prepends `/opt/cudnn-host-extra` only when the library file is there. `align_nvidia_userspace()` is unchanged.
- **Build:** `cudnn-convolution-nvidia` keeps a CUDA 12 nvcc when `cuda-12.8` or `cuda-12.6` exists, and links the venv cu13 cuDNN with rpath only when the nvcc it invokes is CUDA 13 (superseded 2026-10-02: the wheel is found by `libcudnn.so.9` and `cudnn.h`, see that entry). The glibc `__THROW` override is passed only to `ecc_walk.cu` and `cudnn_conv.cu`, and only when that nvcc is CUDA 13 and glibc is 2.41 or newer. memcpy, NCCL, and HPL build scripts are unchanged.
- **Setup gate:** the NVIDIA skeleton runs `scripts/probe_setup.sh` when the component overlaid it. PyTorch convolution components run one fp16 `conv2d`. The cuDNN component runs `bin/cudnn_conv`. The probe fails setup; it does not repair the library.
- **JAX:** `jax[cuda13]` when `torch.version.cuda` major is 13, otherwise `jax[cuda12]`. A missing extra fails the install. The post-install check is a JIT matmul and runs only when JAX was requested.

## 2026-09-27 — cuDNN tensor_ir remains loadable by every convolution harness

- **Host libraries:** a pip cuDNN wheel that lacks `libcudnn_engines_tensor_ir` still causes that newer system sublibrary to be moved to `/opt/cudnn-host-extra`. The move is host-global, so setup wraps every existing `bin/cudnn_conv` (the repo being installed, sibling repos, and `/root/*/bin/cudnn_conv`). A later PyTorch, vLLM, or SGLang setup no longer leaves an earlier `cudnn_conv` binary unable to load `tensor_ir`. Superseded the same day by the version-gated move above.

## 2026-09-25 — TEMPLATE_00_88 NVIDIA harness and host-library contracts

- **Collector gate:** `scripts/collect_workload.py` is the harness entry. Create writes an adapter when the overlay ships `collect_*.py` under another name, and fails if the runner still calls `collect_workload.py` and neither the overlay nor the adapter provided it. `entry_point` is no longer inferred as the first overlay path. NVIDIA STREAM uses `stream-collect-nvidia` (same role as `stream-collect-amd`).
- **Framework flags:** `framework_registry.py` loads its YAML without PyYAML when the system interpreter has none. The NVIDIA skeleton evaluates the registry with `.venv/bin/python` after PyYAML is installed. NVIDIA flags install `fio`, `iperf3`, and, for NCCL workloads, `libnccl-dev` from the distro CUDA repository.
- **Host libraries:** if `nvidia-smi` fails and `libcuda` / `libnvidia-ml` for the loaded kernel module exist, setup pins those sonames and moves only the mismatched copies aside. A working `nvidia-smi` is left unchanged, so a matched Ubuntu 24.04 image is not rewritten. A pip cuDNN wheel that lacks `libcudnn_engines_tensor_ir` causes that newer system sublibrary to be moved to `/opt/cudnn-host-extra`; `bin/cudnn_conv` is wrapped to load it. `/dev/nvidiactl` does not replace a working `nvidia-smi`.
- **Container NUMA:** multichase and the NUMA-cache collector retry unbound when `numactl` reports that the NUMA policy is not permitted or not supported.
- **Blank metrics:** vLLM KV and SGLang prompt-response averages skip blank cells. Validator `cache_hit` columns may be zero. Serving clients blank inter-token latency when it copies time-per-output-token. The end-of-run summary prints p50, p95, and p99 as separate values.
- **Remote retry:** `--validate-only --reuse-remote-env` keeps `.venv` only when `.env_reuse_stamp` matches the framework flags and CUDA wheel index, and `results/install_status.txt` does not show a failed framework-registry import. A mismatch removes `.venv` and `.setup_state`.
- **Docs:** `fill_generated_docs.py` remains the only writer for PRD, SPEC, and README. Leftover `{{Field}}` tokens still fail the run, and the README kernel version still comes from the yaml.

## 2026-09-25 — TEMPLATE_00_87 official create contracts and metrics D1–D4

Source: authorized Cursor-101 generator work for Project245 / TEMPLATE_00_87. D5 (streaming TTFT) is out of scope.

- **Dash directory naming:** local folder and GitHub slug are `<Workload Number>-<Repo Name>` (example `101-sys-bench-amd-rocm-stack-validation-ubu2404`). Workbook `Repo Name` stays unprefixed. Legacy `_` folders are still found.
- **Windows-to-VM driver:** `scripts/create_one_workload.py` uses Git Bash + OpenSSH (`scripts/host_exec.py`), not WSL `bash -lc`. After a setup reboot it waits for SSH and resumes. `--validate-only --reuse-remote-env` retries without wiping `.venv`/`.cache`.
- **Create gates:** missing `scripts/collect_workload.py` (or component `entry_point`) fails create. Locked overlay `config/benchmark_config.yaml` is merged, not replaced. Official docs come from `scripts/fill_generated_docs.py`. Text writes are LF. `tests/fixtures/.gitkeep` and results gitkeeps are restored after copy.
- **Contracts:** `config/framework_registry.yaml` + `scripts/framework_registry.py` own Framework install flags. `config/platform_policy.yaml` owns OS/vendor/driver (one ROCm reboot). Shared blank/0/positive rules live in `scripts/metric_contract.py`. Fixture tests: `tests/test_template_87_contracts.py`.
- **Metrics D1–D4:** `print_metric_summary.py` prints the first parenthetical key and unmashes `p50_p95_p99` to p50. SGLang/vLLM serving collectors emit real p50/p95/p99. SGLang ITL is blank (not copied from TPOT).

## 2026-09-24 — remaining metrics_summary alignments (115/205/224/203)

Source: leftover cross-vendor closer gaps after the NOT FOUND / `not measured` pass. Checked against current collectors and live `nvidia-smi` on Ubuntu 24.04 and 26.04 NVIDIA hosts (both Driver 580, `Not Active` / `Active`).

- **115/315 BabelStream Metrics:** cite the five per-kernel keys the AMD parser already writes (`bandwidth_gb_s_copy` … `bandwidth_gb_s_dot`), matching 215/415's five-kernel set. Blind mean / peak% stay in `summary.json` but are no longer numbered Metrics.
- **224/424 SDXL Metrics:** add `#4` `step_time_ms` and `#5` `first_image_latency_s`. `infer_sdxl.py` now prints those keys on the RESULT line; `collect_sdxl.py` copies them into METRICS_CSV. NVIDIA `parse_results.py` no longer estimates step time from per-image latency, and no longer substitutes first-image with mean image time.
- **205/405 tensor correctness:** `tolerance_compliance` is now percent of cases (same meaning as 105/305), not a 1/0 flag. Workbook Metrics order matches AMD: max abs, max rel, % in tolerance, coverage, failures. Gate `tolerance_compliance_min` is 100. Overlay now ships `scripts/collect_workload.py` (forwards to `collect_tensor_ops.py`) so `run_benchmark.sh` finds the harness entry; `--raw-file` / `--profile` are accepted and ignored.
- **NVIDIA 26.04 setup:** `setup_nvidia_skeleton.sh` accepts Debian `libcudart` (`/usr/lib/x86_64-linux-gnu`), tries `cuda-nvcc-13-1` / `nvidia-cuda-toolkit` when 12.6/12.8 packages are absent, and continues when `nvidia-smi` has a driver/library mismatch if `/dev/nvidiactl` is present (RunPod host-injected driver). BabelStream `build.sh` treats a failed `nvidia-smi` as non-fatal (`|| true` under `pipefail`) and infers `sm_90`/`sm_80` from `/proc/driver/nvidia/gpus`. NVIDIA BabelStream and tensor overlays now ship `scripts/collect_workload.py` wrappers so `run_benchmark.sh` finds the harness entry.
- **203/403 throttle:** `nvidia-smi` field `clocks_throttle_reasons.hw_thermal_slowdown` is `Active` or `Not Active`. The old substring `Active` matched `Not Active` every poll. The collector now requires an exact `Active` token and counts 0→1 transitions. Confirmed the same wording on both NVIDIA 24.04 and 26.04 hosts. Validator `zero_ok` now matches `throttl` so `thermal_throttling_events=0` is accepted (`throttle` is not a substring of `throttling`). When NVML is unusable (`Failed to initialize NVML` / driver mismatch), GPU temp and power are left blank instead of parsing the library version (e.g. `580.178`) as a temperature.

## 2026-09-24 — metrics_summary.txt: correct values, honest placeholders, consistent headers

Source: review of the newest `metrics_summary.txt` for all 128 workloads (Projects 236–239). Pre-change copies: `archive/20260924_before_gary_ledger_retune/metrics_summary_fixes/`. Checked by replaying the old and new parser/printer on those 128 runs' raw output; hardware collectors were compile/unit-tested only.

**Summary values (generated `parse_results.py`, `print_metric_summary.py`)**
- Raw output with more than one CSV table is no longer merged under the first header. The table whose columns best match the workload's Metrics is used. This fixes scrambled vLLM summaries (e.g. 128 TPOT 62.6 ms → 8.3 ms, E2E 68.5 s → 137 s; 129 TPOT 515.6 ms → 7.8 ms; 127 TTFT 607 ms → 27 ms).
- Aggregation follows the column's leading word: `peak_`/`max_` → max, `min_` → min, `first_` → first row, otherwise mean (was always mean; e.g. 103 "peak" temperature 39.0 → 45).
- A metric column that is blank on every row is reported as `not measured` (was dropped and printed as NOT FOUND, or turned into 0.0 by the SGLang parsers).
- Printed values are rounded (whole numbers without `.0`; ≥1 to 3 decimals; <1 to 4 significant digits). summary.json keeps full precision.

**Collectors**
- 202/402 `gpu-health-nvidia`: PCIe width/speed read from the `--query-gpu` CSV (width was the temperature, speed 0); speed reported in GT/s like AMD.
- 112/212/312/412 lmbench: each tool's result parsed from its own position (bw_mem was the 8.39 MB buffer size, lat_ctx the process count 2, AMD lat_mem_rd the array size); 212/412 syscall latency converted to ns to match its column name.
- 216/416 NCCL: sweeps min_bytes..max_bytes (was 8-byte messages only, ~0.001 GB/s); bus/alg bandwidth reported at the largest message, latency at the smallest; per-size data in `nccl_sweep.csv`; rounds halved (baseline 10 / extended 24) to hold duration — re-time on next run.
- 103/303 `system-stress-amd`: CPU temperature read from hwmon/thermal zone (was a copy of the GPU temperature); ECC from `amd-smi` when reported; throttle, CPU utilisation and unreadable sensors left blank instead of fixed 0/1.0.
- Fixed/estimated values replaced by blank ("not measured") or a real computation: 104/304 ECC; 117/317 CPU-Gflops and L1 norm; 118/318 GB/s (now computed from tensor sizes); 121/321 TFLOPS (model-FLOPs formula, same as NVIDIA twin) and memory bandwidth; 122/322 GPU utilisation; 126/326 TFLOPS (exact matmul FLOPs), compile time and peak HBM (from JAX); 130/230/330/430 TTFT fallback and RadixAttention hit rate; 131/231/331/431 TTFT (was 0.4 × E2E); 127/327 and 227/427 KV-cache figures (were formulas); 113/313 TLB/L3; 110–410 cache misses without perf, and remote latency/ratio on single-NUMA-node hosts; 111/311 perf floors (0.001 / 1.0).
- 105/305 relative error uses max(|ref|, atol) as denominator (was 1e-6, giving ~517 with 100% compliance).

**Header**
- Run ID = run folder name (was the SQLite row id: 1, blank or leftover 12–17).
- Device = `cpu` for CPU / System workloads (was always `gpu`); collectors still receive `--device` unchanged.
- Elapsed = printed Stop − Start (was 3–8 s longer: taken after the hardware/software inventory). The ledger `total_runtime` uses the same value.
- SDXL/SGLang/vLLM overlay run folders now use the repo folder name (they omitted `<N>_` and the `-ubu2404`/`-ubu2604` suffix) and no longer print a hard-coded Run ID such as `124_…` in 324.

**Workbook (`Workload_Definitions` › Metrics)**
- Labels no longer describe removed placeholders ("always 0", "fixed 1.0", "= TTFT", "est. 0.4x E2E"); blank labels filled (201/401 #2, 227/427 #4); units added (lmbench, PCIe, NCCL).
- 114/314 now report H2D, D2H and D2D bandwidth at the largest transfer plus latency, like 214/414 (was one blended "combined" figure, 369 GB/s).
- 107/307 metric order aligned with 207/407 (Copy, Scale, Add, Triad, efficiency).
- 225/425 "Status code, fixed 1.0" removed (4 metrics, like 125/325).
- Ledger note: metric positions change for 107/307, 114/314 and 225/425.

**Not changed:** Artifacts/SQLite paths remain the server paths; "Command submitted" vs "fully resolved" kept as-is (intentional); cross-vendor metric-set differences that need new measurements (111 vs 211, 115 vs 215, 124 vs 224) remain.

## 2026-09-24 — Retime Gary-question workloads; fix NVIDIA GUPS/BabelStream collectors

Source: `runtime_ledger_101_132_20260924_071518_Excel_ALL_FOUR.xlsx` (sheet `runtime_ledge_ALL_FOUR_Edit3`). Targets: baseline ~4:00 (3–5 min), extended ~11:30 (8–15 min). Each changed row's `notes` cell records the measured times, rate and arithmetic. All values are unconfirmed until the next loop run.

- `Parameters_SmokeBaselineExtend` (baseline/extended): 112 repetitions 4/13→2/5; 312 repetitions 5/7→3/9; 412 repetitions 5/13→3/10; 213 num_iterations 3160/1600→880/1240; 413 200/125→800/980; 220 13/34→3/10; 420 20/74→3/10; 310 5e4/1e5→6.3e9/1.85e10 (copied from 110); 410 1.5e9/3e9→5.3e9/1.5e10; 407 23280/37560→14500/15600; 424 num_images 32/7→72/130. `Workload_Definitions` command columns regenerated with `scripts/sync_matrix_profile_commands.py` (22 cells).
- `gups-nvidia`: iteration safety cap raised from 200 baseline / 500 extended to 5000 / 10000. The old cap silently truncated the workbook values, which is why earlier 213/413 retunes had no effect.
- `linpack-hpl-nvidia` (220/420, no code change): timed repeats are `min(num_iterations, 6)` baseline and `min(num_iterations, 16)` extended, and `problem_size_N` 65536 is clamped to 32768. Each repeat costs ~70 s of CPU matrix setup and residual work. The new values sit inside those caps.
- `babelstream-hbm-nvidia` (415 ran 5–7 s and reported ~42,000,000 GB/s): `build.sh` now compiles native SASS for the detected `compute_cap`. `babelstream.cu` checks `cudaGetLastError()` after every launch loop and exits 2 when bandwidth is implausible (>20 TB/s). 415 parameter values unchanged; re-measure before retuning.
- Not changed (recommendation only): 203 `system-stress-nvidia` throttle parser counts `Not Active` as a throttle event.
- `linpack-hpl-nvidia` percent-of-peak (220/420 reported 165–185%): `nvhpl.cu` computed peak as SMs × 64 × clock, which ignores FMA (2 flops) and Hopper's FP64 tensor cores used by cuSOLVER `DGETRF` (H100 NVL 15.1 TF instead of 60 TF). Peak is now SMs × FP64 flops/clock/SM × clock from `cudaDevAttrClockRate` with a per-arch table (sm_90 256 tensor / 128 vector; sm_80 128 / 64), and the vector peak is printed alongside. Unknown archs print 0; `collect_workload.py` then leaves percent-of-peak blank (NULL) instead of 0, which validation would reject. `BENCHMARK_PEAK_FP64_TFLOPS` overrides the peak. Expected on H100 NVL: ~41% (220) / ~47% (420).
- Removed metrics that always printed `NOT FOUND` in `metrics_summary.txt` (`Workload_Definitions` › `Metrics`; remaining metrics renumbered): 106/206/306/406 "Queue-depth scaling: not emitted" (4→3); 117/317 "L2/bandwidth: not emitted" (5→4); 213/413 "TLB miss rate" and "L3 cache miss rate", perf counters unavailable on the NVIDIA hosts (5→3; also dropped from `Output Fields / Metrics to Parse`). The ledger pads missing metric slots with blanks. For 213/413, ledger `metric_2`/`metric_3` now hold update rate and memory-controller throughput (previously `metric_4`/`metric_5`).
- Pre-change copies: `archive/20260924_before_gary_ledger_retune/`.

## 2026-09-24 — ROCm first-time setup reboots once (24.04 and 26.04)

- `rocm_install_runtime` in `scripts/lib/rocm_install_24_04.sh` and `scripts/lib/rocm_install_26_04.sh` no longer reboots after `apt upgrade`. It installs the stack in the same invocation and reboots once after the driver/firmware step.
- On 24.04, `linux-modules-extra` is installed for the running kernel and any newer pending kernel so extras exist after that single reboot.
- `setup.sh` operator notice, `docs/rocm-reboot-install-contract.md`, `templates/README_TEMPLATE.md`, and `AGENTS.md` now say one reboot. systemd auto-resume is unchanged.

## 2026-09-22 — Numbered GitHub slugs and finish publish-doc rename

- Publish GitHub repos as `<Workload Number>_<Repo Name>` (same as the local folder). Finished the `GITHUB_PUBLISH.md` / `GITHUB_WORKLOAD_PUBLISH.md` rename, including the per-workload installed copy.

## 2026-09-22 — Template holes found on the 00_84 GitHub/VM pass

- LF-write `config/pyproject.toml` and include `*.toml` in publish/remote CRLF cleanup.
- Default `SKIP_RVS` from Framework (RVS listed → 0) unless `BENCHMARK_SKIP_RVS` is set.
- Inject `numpy>=1.26` for GUPS overlays; check hipcc `hipError_t` in `hip_memcpy_bw.cpp`.
- Keep Metrics parenthetical closers during extract; drop nested-copy sitecustomize fallback; prune `scripts/dir.txt` at publish.

## 2026-09-12 — Remove workbook Implementation Pack column (TEMPLATE_00_84)

- Deleted the `Workload_Definitions` Implementation Pack column from `BenchmarkSpecDefinitions.xlsx`. Generated `benchmark_specification.json` no longer includes that field.
- Component overlays are selected only from `config/implementation_packs.yaml` using Workload Number and GPU Vendor. `scripts/implementation_pack.py` no longer reads a spec field.
- Extract and validate no longer require Implementation Pack. Extract skips the field if an old workbook still has it.
- Removed `scripts/populate_implementation_pack_column.py`, which existed only to write that column.

## 2026-09-11 — 108/208 iperf3 baseline/extended no longer SIGKILL at seconds+30

- `iperf3-amd` and `iperf3-nvidia` collectors timed out `iperf3 -t N -J` at `N+30`. Baseline TCP (`-t 100`) on localhost exceeded 130s (JSON wrap-up), Python SIGKILLed the client (exit 137), and `run_benchmark.sh --profile baseline` died. Extended (`-t 290`) would fail the same way.
- Client timeout is now `max(N+180, N*3)`. Collectors pass `-i 0` so `-J` is a summary, not ~N interval objects. `TimeoutExpired` and invalid JSON are caught and the one-shot server is stopped.

## 2026-09-11 — Remove parameter_overrides.yaml

- Deleted `config/parameter_overrides.yaml`. Smoke/baseline/extended numbers now come only from `BenchmarkSpecDefinitions.xlsx` `Parameters_SmokeBaselineExtend`. Override values were not copied into the workbook.
- `scripts/matrix_profile_values.py`, `scripts/extract_benchmark_definition.py`, and `scripts/generate_benchmark_config.py` no longer load or apply a sidecar override file.
- Live agent instructions (`docs/AI_AGENT_INSTRUCTIONS.md`, `AGENTS.md` §20.2) no longer tell generators to apply that file.

## 2026-09-10 — Remote validation copies must be 0755, not 0777

- Windows `tar` extract onto the Ubuntu validation VM left `/root/<N>_<Repo Name>/` as `drwxrwxrwx` (lime-green / other-writable in `ls`). After extract, `create_one_workload.py` now runs `find … -type d -exec chmod 755 {} +` and sets regular files to `0644` before restoring `+x` on `.sh` helpers. Agent instructions, generation workflow, AGENTS.md § 29.1, and SUBMISSION_CHECKLIST 3.11e1 require the same `chmod` on any manual copy.

## 2026-09-10 — Setup bundle from Domain+Vendor; Implementation Pack; create_one_workload.py

- **300_1 / setup.sh**: `init_generated_repo.py` no longer greps Framework/Domain for `rocm`/`vllm`/`amd-smi`. It keys `Execution Domain` first (`CPU / System` → `cpu-system` skeleton) then `GPU Vendor` (`AMD` → ROCm skeleton, `NVIDIA` → NVIDIA skeleton). Empty `touch()` of `setup.sh` is a hard fail. New `scripts/templates/setup_cpu_system_skeleton.sh` covers 106–113-class host workloads.
- **200_2 / overlays**: `Workload_Definitions` has an `Implementation Pack` column (populated for 128 rows from `config/implementation_packs.yaml`). `resolve_implementation_components.py` copies those component ids; it does not match `Workload Name`. `linpack-rochpl-amd` now overlays `HPL.dat`. `entry_point` is inferred or declared on the component.
- **200_3 / driver**: `scripts/create_one_workload.py` is the chatbox path: create → optional remote setup/smoke/self_check/publish-ready → record. Per-workload errors are `RuntimeError`, not `SystemExit`, so a 124-class miss cannot skip the rest of the batch. Do not call `create_generated_batch.py` from chat.

## 2026-09-10 — 211/411 host-counter fallback when PMU cycles are denied

- **211/411 linux-perf-pmu-nvidia**: the workbook Metrics column is now
  elapsed TSC/PMU `cycles`, child CPU time, CPU utilization, stress-ng
  bogo-ops/s, and context-switch rate. The overlay collector still
  required `perf stat` `cycles`/`instructions` and hard-failed on
  `perf_event_paranoid=4` containers. It now prefers PMU cycles when
  `perf_event_open` works, otherwise persists TSC/rusage/bogo-ops host
  counters and leaves IPC-family columns empty. Still does not invent IPC.

## 2026-09-10 — Root-cause fixes for the 101-132/201-232 TEMPLATE_00_80 batch failures (104/105, 205, 209, 212, 213, 218, 221, 227-229, 230/231, 232)

Traced every failure from the 00_80 101-132 and 201-232 generation batches back
to the generator/template code (not the VM) and fixed the ones that were
fixable without touching a locked overlay file's runtime contract. Each item
below is a repo change, not a one-off repair of an already-generated repo.

- **205/221/226 `--device` vs `--device-id`**: `materialize_generated_harness.py`'s
  generated `run_benchmark.sh` decided whether to forward `--device` with a
  bare `grep -q -- '--device'`, which also matches `--device-id` (a prefix).
  That passed the literal word "gpu"/"cpu" onto collectors that only define
  `--device-id`; argparse prefix-matched it and `int("gpu")` crashed before
  any RESULT/CSV line. Now requires a standalone `--device` flag and falls
  back to `--device-id "${DEVICE_ID:-0}"` when only that flag exists.
- **227-229 JSON raw_output.txt**: the generic `parse_results.py` template
  (`write_parser()`) only ever understood CSV and raised
  `[FAIL] No supported raw output rows were parsed.` on the vLLM components'
  JSON summaries. Added a `load_rows()` fallback: CSV (unchanged) -> sibling
  `raw_results.csv` -> JSON object/array. Existing CSV-emitting components are
  unaffected.
- **213 GUPS validator**: the generic `validate_results.py` template failed
  any sample with a non-empty `error_message` regardless of `status`, so
  GUPS's honest `status=ok, error_message="perf TLB/L3 not measured"`
  (an optional measurement it correctly declined to invent) failed the run.
  Now only a non-"ok" `status` fails a sample.
- **205 `_ensure_thresholds`**: `apply_component_gaps.py` unconditionally
  appended a `thresholds:` block to `config/benchmark_config.yaml`, including
  when that exact path was a component's own locked overlay file -- which is
  what made self_check report "locked overlay rewritten" for 205. Also fixed
  the "already has thresholds" check, which was a bare `"thresholds:" in
  text` substring match that a YAML *comment* containing that word would
  satisfy, silently skipping real injection (the original 101-132 bug).
  Both are now lock-aware / key-aware.
- **104/105 ROCm torch cache**: `setup_rocm_reboot_skeleton.sh` defaulted
  `PIP_CACHE_DIR` to `<repo>/.cache/pip` -- per-repo, not shared -- so 104 and
  105 each cold-downloaded the same ~6.2 GB `torch==2.11.0+rocm7.2` wheel and
  both hit the 60-minute setup/smoke gate before smoke ran. Default is now a
  shared `<parent-of-repo-root>/.shared_pip_cache`, and `install_rocm_pytorch()`
  honors `PYTORCH_FIND_LINKS` when set.
- **218 cuDNN SIGABRT**: `setup_nvidia_skeleton.sh` apt-installed both
  `libcudnn9-cuda-12` and `libcudnn9-cuda-13` whenever `src/cudnn_conv.cu` was
  present (added in the 2026-09-07 00_78 pass, ported from 00_77). `build.sh`
  only ever puts `/usr/local/cuda(-12.8|-12.6)` on PATH -- never cuda-13 -- so
  nvcc there always resolves to a CUDA 12 toolkit; the two ABI-incompatible
  cuDNN builds on the linker path made `bin/cudnn_conv` abort at runtime.
  Now installs only the cuda-12 variant.
- **230/231 torchaudio pin**: `install_sglang_nvidia.sh` (in both
  `sglang-serving-nvidia` and `sglang-prompt-response-nvidia`) pinned
  `torchaudio==2.13.0+cu130`, which has never been published on the cu130
  wheel index (tops out at 2.11.0+cu130) -- added in the same 2026-09-07
  00_78 pass as a version-drift fix, never checked against the live index.
  `setup.sh` died before smoke ran for both workloads every time. Re-pinned
  to `torchaudio==2.11.0+cu130`; torch/torchvision unchanged.
- **212 stale authoring notes**: `extract_benchmark_definition.py` had no
  handling for `TEMPLATE_00_<n>` authoring notes left in workbook cells, so
  they flowed straight into `benchmark_specification.json`/README/SPEC/PRD
  and tripped self_check's `"TEMPLATE_00_" in text` scan. Added
  `_strip_template_notes()` (sentence-level, with a bare-tag fallback so the
  forbidden substring is always gone) inside `_clean_value()`; real
  parameter values are untouched.
- **232 missing collector**: `rag-faiss-end2end-nvidia`/`-amd` were marked
  `completeness: thin` with no `scripts/collect_workload.py` in their
  overlay, so a generated 232/432/132/332 repo had no entry point for
  `run_benchmark.sh` to call. Added a real `scripts/collect_workload.py` to
  both components (resolves `config/benchmark_config.yaml`'s `sweep:` section
  for the active profile and forwards it to `gpu-bench-rag-faiss-end2end.py`)
  and flipped both to `completeness: closed`.
- **209 multichase numactl**: `collect_multichase.py` always bound with
  `numactl --cpunodebind=0 --membind=<N>` and failed the whole collect if
  that `numactl` call itself failed (missing binary, or a requested NUMA
  node that doesn't exist on a single-socket host) -- a host/binding
  problem, not a real zero/failed latency sample. Added `numactl --hardware`
  detection: clamps a requested node to one that actually exists, and drops
  the `numactl` prefix entirely when the binary isn't installed. The "every
  tier must report a positive latency" requirement is unchanged -- a
  genuinely failed chase still fails the run. Also promoted the previously
  ad-hoc, per-generation `scripts/collect_workload.py` wrapper (it existed
  in generated repos but not in this component's overlay) to a real overlay
  file, so future generations get it automatically instead of an agent
  re-authoring it each time.
- **211 perf PMU**: confirmed this is a host permission gap
  (`perf_event_paranoid`/missing `CAP_PERFMON`), not a repo bug -- the
  collector is already doing the right thing by refusing to invent an IPC
  number. No code change.

## 2026-09-09 — 130/131/330/331 real-SGLang duration retune and gluon TensorDescriptor fallback

Ported from the TEMPLATE_00_79 MI300X Ubuntu 24.04 130/131 baseline that
actually started `python -m sglang.launch_server` (not tiny_sglang).

- **Triton gluon gfx1250**: the 2026-09-08 wrap of `gluon/amd/__init__.py`
  was not enough. JIT imports `triton.experimental.gluon.amd.gfx1250`
  directly; an empty except left that package as a stub and crashed the
  scheduler with `AttributeError: ... no attribute TensorDescriptor`.
  `scripts/patch_triton_gluon_gfx1250_optional.py` in
  `sglang-prompt-response-amd` and `sglang-serving-amd` now loads sibling
  `gfx1250.py` by path and exports `TensorDescriptor`. Shared by
  130/330 and 131/331.
- **output_len** (num_prompts unchanged: 8 / 24 / 48): 130 and 330
  baseline **1560** / extended **6100**; 131 and 331 baseline **3370** /
  extended **5480**. 130/131 measured on Ubuntu 24.04 MI300X at 4:13 and
  3:51 (operator later 4:22 / 3:50). 330/331 are the Ubuntu 26.04 AMD
  twins and inherit the same knobs; retune on that host if wall time
  leaves 3-5 / 12-15 min. Written to `Parameters_SmokeBaselineExtend`,
  command columns, and `config/parameter_overrides.yaml`.
- **Setup extras**: `soundfile` and `python-multipart` on the SGLang
  launch pip lines in `setup_rocm_reboot_skeleton.sh`, and the same pins
  in `apply_component_gaps.py` for AMD SGLang `requirements.txt`.

## 2026-09-08 — Ported today's TEMPLATE_00_78 fixes (SGLang gluon patch, duration retunes) ahead of the next AMD/NVIDIA deploy

Gary is deploying the next AMD/NVIDIA VM batch from this template
(`Project215_TEMPLATE_00_79_20260908`), so today's fixes made against the
separate TEMPLATE_00_78 lineage (`Project211_101_to_132_TEMPLATE_78_20260906`
/ `Project212_201_to_232_TEMPLATE_78_20260906`) needed porting over here
first. This template forked from that lineage before today's work (its
`config/parameter_overrides.yaml` and `BenchmarkSpecDefinitions_ORIGINAL.xlsx`
are byte-identical to that pre-fix snapshot) and has since evolved
independently — most visibly the ongoing metrics rewrite and 26-tag
metric-deletion pass — so nothing was copied wholesale; each change was
checked against this template's current state first.

- **130/330, 131/331 SGLang Triton gluon gfx1250 crash fix**: confirmed
  `sglang-prompt-response-amd/files/run_benchmark.sh` and
  `sglang-serving-amd/files/run_benchmark.sh` (and both `component.json`)
  were byte-identical here to their TEMPLATE_00_78 pre-fix versions, so the
  fix ports cleanly. Added `scripts/patch_triton_gluon_gfx1250_optional.py`
  to both components, wired into `run_benchmark.sh` immediately after the
  existing `patch_aiter_gfx1250_optional.py` call, and added to both
  `component.json` `overlay`/`provides` arrays. See the TEMPLATE_00_78
  changelog entry for the full root-cause writeup (Triton's gluon package
  eagerly importing an unrelated gfx1250 backend that references a missing
  symbol on this ROCm/Triton wheel).
- **Duration retunes for 110, 128, 210, 223, 227, 232**: same 2026-09-08
  remote-VM measurements as the TEMPLATE_00_78 pass. Checked each of these
  6 workloads' current `baseline`/`extended` values here first — all 6
  still matched the pre-fix TEMPLATE_00_78 baseline exactly (no independent
  changes on this lineage), so the same values were safe to fold straight
  into both `config/parameter_overrides.yaml` and
  `BenchmarkSpecDefinitions.xlsx` (`Parameters_SmokeBaselineExtend` cell +
  notes, plus the matching `Workload_Definitions` command-column text so
  the spreadsheet doesn't contradict itself).
- **212/412 (lmbench repetitions): found and fixed a live bug, did NOT
  apply my 212 measurement as-is.** This template's own history already
  retuned 212 on 2026-09-07 ("Aligned to match 112/312", baseline=5,
  extended=13), separately from and superseding the original H100
  duration-based retune. But `config/parameter_overrides.yaml` here was
  never updated to match — it still said baseline=300/extended=750 (the
  pre-alignment value) for both 212 and its 412 sibling. Since overrides
  apply after the spreadsheet is read, **that stale entry was silently
  overriding the correct 5/13 at generation time**, meaning a generated
  212/412 repo would actually run the old ~4-hour lmbench loop instead of
  the intended ~4 min / ~12 min runs. Fixed conservatively: corrected the
  override to 5/13 for both, matching what `Parameters_SmokeBaselineExtend`
  already says, rather than asserting the different value (5/14) that
  today's own remote-VM measurement found for 212 specifically. Left a note
  on both explaining the discovery and fix.
  - **Open question for Gary**: today's independent 212 measurement
    (lmbench reps run at ~47-53s each on the actual remote VM) found
    extended=14 targets 212's own ~12 min duration slightly more precisely
    than the 112/312-matched value of 13. Left at 13 here since matching
    siblings was the deliberate 09-07 call on this template — not
    overridden without confirmation. Flagged in both the override notes
    and the spreadsheet notes; a one-line change to `212`/`412` in
    `config/parameter_overrides.yaml` and the two rows' `extended` cells if
    Gary wants 14 instead.
- **Verification**: full cell-by-cell diff of both `BenchmarkSpecDefinitions.xlsx`
  sheets against the pre-edit workbook confirmed exactly 22 cells changed
  (9 in `Workload_Definitions`, 13 in `Parameters_SmokeBaselineExtend` —
  12 for the 6 value+notes pairs, 1 for 212's notes-only update), nothing
  from the metrics-rewrite work touched. Systematically checked all 41
  pre-existing override entries (not just the 7 in scope) against this
  template's live spreadsheet before touching anything, to catch exactly
  this kind of independent-lineage drift; 212/412 were the only two that
  diverged.

## 2026-09-08 — New #3 metrics for babelstream-hbm-amd / hipmemcpy-bandwidth-amd (114/314, 115/315)

Gary's call: workloads 114/314 (hipMemcpy Bandwidth Test) and 115/315
(BabelStream HBM Bandwidth) had dropped to 2 real metrics each once their old
#3 entries -- 114/314's "Pinned/pageable: sweep flag only" (no key at all) and
115/315's "Kernel time, fixed 1.0 (runtime_ms)" (a hardcoded-1.0 constant,
never a real measurement) -- are removed per the pending 26-tag metric-
deletion review. Both components previously relied entirely on the generic
auto-generated `scripts/parse_results.py` (no component-specific parser
existed for either), which only ever exposes a single blind mean per raw CSV
column. Added a dedicated `scripts/parse_results.py` to each component so a
real, code-grounded #3 could be added instead of leaving both workloads at 2
metrics:

- `babelstream-hbm-amd`: `hip_stream.cpp` genuinely times Copy/Mul/Add/Triad/
  Dot independently (`time_kernel()` per kernel), but the generic parser's
  blind mean across all 5 rows only ever surfaced `bandwidth_gb_s` (#1) and
  `peak_percent` (#2) as one number each, discarding the real per-kernel
  spread. The new parser adds `"kernel"` to `_PIVOT_GROUP_COLUMNS`, giving
  every kernel its own `bandwidth_gb_s_<kernel>` / `peak_percent_<kernel>` /
  `runtime_ms_<kernel>` key; #3 cites `bandwidth_gb_s_triad` specifically,
  since Triad is the workload's namesake combined-bandwidth kernel. Unlike
  the base template's tier/benchmark pivot (which drops the blind mean once
  real per-group keys exist), this component's copy keeps the blind mean in
  place, since #1/#2 already cite it and must keep resolving unchanged.
- `hipmemcpy-bandwidth-amd`: `hip_memcpy_bw.cpp` sweeps min_bytes..max_bytes
  per direction (H2D/D2H/D2D), but the generic parser's blind mean over
  `bandwidth_gbps` blends all three directions and every swept size --
  including small, latency-dominated transfers -- into one number. The new
  parser adds `add_peak_direction_bandwidth()`, which isolates the standard
  sustained-bandwidth figure per direction: the mean `bandwidth_gbps` among
  rows at that direction's own largest swept `transfer_size_bytes`. #3 cites
  `bandwidth_gbps_h2d`; `bandwidth_gbps_d2h`/`bandwidth_gbps_d2d` are computed
  the same way for consistency but not currently cited as metrics.
- Necessary companion fix (not scope creep): 115/315's existing #2 cited the
  bare numeral `(100)` -- not a real column -- and only ever resolved via
  `print_metric_summary.py`'s last-resort position-fallback (exact-count
  match between unresolved metrics and unused numeric keys). Adding ~10 new
  per-kernel keys via the pivot broke that fallback's exact-count condition,
  which would have made #2 unresolvable ("NOT FOUND") the moment #3 was
  added. Fixed by changing #2's parenthetical to cite the real `peak_percent`
  key directly, restoring exact-name resolution. Verified via
  `print_metric_summary.py`'s actual `resolve_metrics()` against real test
  data that all three metrics (#1/#2/#3) now resolve by name for both 115
  and 315.
- Also corrected a stale Parser Notes claim for 115/315 ("hardcoded 53 GB/s
  reference") to the real value used by `collect_workload.py`
  (`peak_percent = min(100, bandwidth_gb_s/5300*100)` -- 5300 GB/s, not 53),
  and corrected 315's "Output Fields / Metrics to Parse" cell, which had
  described an entirely different, non-matching CSV schema (`kernel_name,
  array_size, best_time_ms, ...`) left over from an earlier design; it now
  matches 115's (and the actual collector's) real columns.
- Updated both components' `component.json` to add `scripts/parse_results.py`
  to `overlay` and `provides`, since both previously relied entirely on the
  materializer's generic fallback parser (`_is_empty()` check in
  `materialize_generated_harness.py`) and had no parser of their own.
- No change to either collector's raw CSV output (`hip_stream.cpp`,
  `hip_memcpy_bw.cpp`, and both `collect_workload.py` wrappers are untouched)
  -- only the parsing/summarization step changed, so `Raw Output Example`
  cells were left as-is.
- Scope note: this pass only applied the #3 addition (and its required #2
  fix) for 114/314/115/315, per Gary's explicit "let's go with #3 for both of
  them and not worry about #4 or anything else." The other 22 tags in the
  pending 26-tag metric-deletion review, the 28-row p50/p95/p99 rename batch,
  the AMD vLLM Inference-Throughput (128/328) `METRIC_COLUMNS` rename, and
  the 129-4/329-4 (and parallel 229-4/429-4) ITL/TPOT label fixes remain
  separately pending and were not touched here.

## 2026-09-07 — Metrics column compressed to <=70 chars/metric

Gary's call: the 9/6 audit's per-metric disclosure sentences (often 150-250+
chars, explaining exactly why a percentile wasn't independently measured)
were too long for a metric-and-a-value summary line, and risked repeating the
same rationale in every run's log forever. Rewrote all `Metrics` column
entries across all 128 workload rows so each numbered entry -- "#N: label
(key);" -- is <=70 characters including the leading "#N: " and trailing ";".

- Where a percentile claim was fake (synthesized, duplicated across p50/p95/
  p99, or actually just a mean), the label now states what is really being
  reported (e.g. "IOPS aggregate", "Batch latency, mean step time") instead
  of spelling out the discrepancy -- matching Gary's stated principle: if you
  can't get p50, but you can get the mean, say "mean" and give the value.
  Short fabrication markers are kept where a value is estimated rather than
  measured (e.g. workload 131/231's TTFT: "TTFT, est. 0.4x E2E").
- Multi-key parentheticals (e.g. "(iops_p50, iops_p95, iops_p99)") were
  reduced to the one key `print_metric_summary.py` actually resolves and
  prints -- `resolve_metrics()` only ever uses the first candidate that
  matches a real column, so the other listed keys were never printed under
  the old text either; nothing was lost by dropping them.
- A handful of workloads (201, 227, and their 401/427 siblings) have
  auto-generated collector column names 50+ characters long on their own
  (e.g. `kv_cache_hbm_utilization_gb_and_percentage_of_capacity`), leaving no
  room for any descriptive label under the 70-char cap -- those entries cite
  the bare key with no label. Shortening those column names themselves is a
  collector-code change, out of scope for this spreadsheet-only pass; see
  Gary's review table for the full list.
- The 100-series/300-series (AMD) and 200-series/400-series (NVIDIA) rows
  were confirmed byte-identical before this pass, so only 64 unique blocks
  needed authoring; both siblings in each pair received the same text.
- No code or parser changes were required for the length limit itself --
  `print_metric_summary.py`'s masking/splitting logic is length-agnostic and
  resolves metrics by name, not position, so a short, clean parenthetical is
  if anything easier for it to match than the old prose-heavy asides.
- As with the 9/6 pass and the NUMA-cache fix earlier today, this only
  updates the generator's spreadsheet -- already-generated repos (the
  101-132/201-232 TEMPLATE_00_78 batch currently running) keep their
  baked-in `benchmark_specification.json` Metrics text until regenerated.

## 2026-09-07 — AMD NUMA-cache metrics wiring fix (110/310)

Root-caused why workloads 110/310's `metrics_summary.txt` printed NOT FOUND for
metrics #3-#5 (cross-socket ratio, NUMA bandwidth, cache-miss counters) despite
the 2026-09-06 metrics-accuracy pass: those three values were always correctly
computed by the `numa-cache-collector` overlay (`collect_numa_cache.py`) and
present in `overlay.csv`/`run.log`'s embedded METRICS_CSV block, but the locked
`numa-cache-wrapper-amd` component's `scripts/collect_workload.py` hardcoded a
10-column header when projecting the overlay's output into the harness's
`raw_results.csv` -- silently dropping `cross_socket_numa_penalty_ratio`,
`numa_local_vs_remote_bandwidth_gb_sec`, and `cache_miss_counters_misses_sec`
before `parse_results.py`/`print_metric_summary.py` ever saw them. The NVIDIA
sibling (210/410) never had this bug: its per-repo `collect_workload.py` is a
thin dispatcher that copies the overlay's raw output verbatim, no projection.

- Fixed `implementation_components/numa-cache-wrapper-amd/files/scripts/collect_workload.py`:
  `header` now includes all 5 real metric columns, matching what the overlay
  already produces (no parser change needed -- `parse_results.py` already
  treats any non-parameter, non-skip-listed CSV column as a metric).
- Rewrote the 110/310 `Metrics`, `Output Fields / Metrics to Parse`, `Parser
  and Normalization Notes`, and `Raw Output Example` columns in
  `BenchmarkSpecDefinitions.xlsx` to drop the now-inaccurate "overlay only,
  not in the harness raw file" language and cite the real keys, matching the
  style already used for #1/#2.
- Repos already generated from `numa-cache-wrapper-amd` (e.g. the 101-132
  TEMPLATE_00_78 batch) predate this fix and will keep printing NOT FOUND for
  #3-#5 until regenerated/rematerialized against the patched component.

## 2026-09-07 — TEMPLATE_00_78 NVIDIA 201–232 runtime findings (00_77 H100)

Ported the 00_77 201–232 REPEAT/generation failures so the next NVIDIA batch does not rediscover them.

- **205 tensor correctness**: generated validator no longer requires `run.rc > 0`. Parser/ledger skip process columns (`rc`, `command`, `check`). Ledger metric fill uses `print_metric_summary.resolve_metrics` so `(pass_rate_percent)` is not replaced by positional `rc=0`. Setup installs `numpy`.
- **211 perf PMU**: setup installs `linux-tools-$(uname -r)` when available. Collector prefers the versioned `perf` binary and explains wrapper-miss vs PMU-permission failures. Still refuses to invent IPC.
- **212 lmbench**: per-command timeouts 30/60/120 → 120/180/180; catch `TimeoutExpired`; read last `lat_mem_rd` table line. AMD sibling timeouts raised to match.
- **218 cuDNN**: NVIDIA skeleton apt-installs `libcudnn9-*-cuda-12/13` before `scripts/build.sh` when `src/cudnn_conv.cu` is present.
- **230/231 SGLang**: Ubuntu 24.04 pins `sglang==0.5.19`, `torch==2.13.0+cu130`, `sglang-kernel==0.4.6.post1` (cu130 wheel index). Setup verifies `import sgl_kernel` and `http_server.launch_server`.

## 2026-09-07 — TEMPLATE_00_78 MI300X duration and correctness pass

Ported the 00_77 generation/runtime findings into this template so the next 101–132 batch does not rediscover them.

- **114 hipMemcpy**: overlay now ships `src/hip_memcpy_bw.cpp`. `direction: all` runs H2D+D2H+D2D; `--pinned-memory true` is a boolean; `--help` works. Collector no longer invents 1024-byte stub rows.
- **115 BabelStream**: overlay ships `src/hip_stream.cpp`. Collector keeps printed GB/s (no `/1000`). Extended `num_iterations` 70300 → 60000 so wall clock stays under 15 min.
- **116 RCCL**: overlay ships `src/rccl_perf.cpp`. Iterations 200000/500000 → 660000/1500000 and `max_bytes` 16MiB → 64MiB so baseline/extended are minutes, not 90s/3min local copies.
- **117 rocBLAS GEMM**: `num_iterations` 72000/201000 → 200000/480000 (~4 / ~10 min of the locked torch.matmul loop).
- **124 SDXL**: `num_images` 15/7 → 80/160 so generate time is not buried under model load.
- **128/129 vLLM**: extended `output_len` 37200 → 18600. The locked client still does 16 seqs / conc 8 / two repeats; 37200 ran ~23 min.
- **130/131 SGLang**: setup extras install `jsonschema` (and requests/ipython). Setup and `ensure_setup.sh` require `from sglang.srt.entrypoints.http_server import launch_server`. Prompt-response client keeps CSV in `raw_output.txt`. Compile extras restore ROCm torch after PyPI pulls CUDA wheels.
- **Other**: hyphen-insensitive overlay selectors; `gpu_memory_utilization: 0.9` dumped as a float; generated-repo CRLF scan skips `third_party/`, `results/raw/`, and `.cache/`.

## 2026-09-06 — Metrics accuracy and parser correctness pass

This pass tracked down why several workloads' generated `results/summary.json` didn't
line up with what the spreadsheet's **Metrics** column promised, fixed the root causes
in the shared parsing code, and then used that fix to audit and rewrite the Metrics
column for all 128 workload rows (32 workload slots × AMD/NVIDIA × Ubuntu 24.04/26.04).

### Fixed (shared parser / print-summary code)

- **Paren-unaware text splitting** in `scripts/print_metric_summary.py` was fragmenting
  Metrics spec text on every comma/semicolon, including ones inside parentheses —
  now parenthetical content is masked before splitting and restored after.
- **Silent positional-index fallback** could mislabel a metric with the wrong key
  when counts didn't line up — replaced with unique-prefix matching and an
  unambiguous-count-only positional fallback.
- **Underscore-grouped numeric strings** (e.g. `"0_32768"`) were accepted by a bare
  `float()` call and treated as real numeric metrics — `to_number()` now requires a
  real numeric-literal shape.
- **Case-sensitive column exclusion** let a workload's own uppercase `Parameter_NN`
  name (e.g. GEMM's `"M"`) collide with a same-named lowercase raw CSV column,
  crashing SQLite table creation — comparisons are now case-insensitive.
- **Missing schema-reserved-column exclusions** caused the same class of SQLite
  crash when a collector emitted its own column matching a hardcoded schema name
  (e.g. sdxl-diffusers' own `created_at`).
- **Long-format ("one row per named entity") raw tables** were blended into one
  meaningless mean instead of one value per entity. `build_metrics_summary()` now
  pivots on a `tier` or `benchmark` grouping column into per-entity keys (e.g.
  multichase's `latency_ns_l1/l2/l3/local_dram/remote_dram`, lmbench's
  `lat_ctx`/`bw_mem`/`bw_pipe`/...), and drops the now-superseded blended mean so it
  can't be mistaken for a real aggregate.

### Changed (spreadsheet)

- Rewrote the **Metrics** column (and, where the underlying behavior needed
  explaining, the **Parser and Normalization Notes** column) for all 128 rows in
  `BenchmarkSpecDefinitions.xlsx`, applying one consistent standard: every numbered
  entry cites the literal `summary.json` key it resolves against, including
  placeholder/hardcoded/formula-derived values (with the caveat stated inline);
  bundled p50/p95/p99-style entries are collapsed to one honest entry where the
  collector only ever produces one real aggregate; wording is kept consistent
  between AMD and NVIDIA siblings for conceptually equivalent metrics even where the
  underlying key names differ; and the 300/400 (Ubuntu 26.04) rows — previously
  written in a different, looser convention — now mirror their corrected 100/200
  counterpart, since the underlying collector commands were confirmed identical.
- Result: of the 62 workloads with usable, freshly re-collected real data, all 62
  now resolve every real, measurable metric declared in their Metrics column
  (up from roughly 3 of 64 at the start of this effort). 6 of those 62 additionally
  carry one or more deliberate "this column is not emitted here" disclosure entries,
  which correctly resolve to "not found," since no such key exists.

### Known limitations / recommended follow-ups

- **Fabricated TTFT (workloads 131/231, mirrored at 331/431)**: Time-To-First-Token
  is computed as `0.4 × end-to-end latency`, not independently measured, for both
  the AMD and NVIDIA SGLang serving-latency collectors. This is now honestly
  disclosed in the Metrics/Notes text, but the right long-term fix is a real
  streaming TTFT measurement, mirroring the fix already applied to vLLM.
- **NVIDIA thermal-throttle counter (203/403)**: the substring match for `"Active"`
  also matches the literal text `"Not Active"`, inflating the throttle-event count —
  it is not a reliable throttle indicator today.
- **AMD rocBLAS GEMM micro (117/317)**: the binary is never executed; throughput is
  formula-derived and the CPU-side comparison numbers are hardcoded placeholders,
  unlike the NVIDIA cuBLAS sibling (217/417), which measures real throughput, memory
  bandwidth, and L2 error.
- **AMD hipMemcpy (114/314)**: H2D and D2H bandwidth are not measured independently —
  one shared value stands in for both directions, unlike the NVIDIA sibling
  (214/414), which measures H2D/D2H/D2D independently.
- **Workload 132/332 (RAG+FAISS, AMD)**: the currently retained sample run's
  `raw_results.csv` holds only a bare summary line with no data rows — a
  pre-existing environment/run defect unrelated to this pass. Its NVIDIA sibling
  (232/432) already has clean data and confirmed-matching key names; a clean AMD
  re-run should verify against those directly.
- **Workload 211/411 (linux-perf-pmu, NVIDIA)**: every captured run on this host
  failed with `perf_event_open` permission denied ("No permission to enable cycles
  event") — a host/environment permissions gap, not a spec or parser defect.
- A few constant, per-run configuration values (e.g. multichase's `thread_count`,
  GUPS' `num_iterations_ran`) still leak into the metrics dict rather than being
  excluded as parameters. Harmless today — they're never cited in the Metrics
  column — but worth a follow-up code fix for full hygiene.

## 2026-09-06 — GUPS cross-vendor standardization and parameter_overrides.yaml reconciliation

This pass closed out the remaining gaps between `config/parameter_overrides.yaml` and
`BenchmarkSpecDefinitions.xlsx`, so the spreadsheet alone is now authoritative for every
workload's smoke/baseline/extended parameter values -- no override-file lookup required
to get the currently-intended numbers.

### Changed (spreadsheet)

- **GUPS Random Memory (113/213/313/413)**: `num_iterations` standardized to
  baseline=200/extended=125 across both AMD (MI300X) and NVIDIA (H100) so `num_updates`,
  `table_size`, `num_threads`, and `num_iterations` are now identical cross-vendor for
  this workload. Previously AMD and NVIDIA disagreed on scaling direction (AMD's
  baseline exceeded extended; NVIDIA's did not) purely because each was independently
  tuned to hit a wall-clock duration target on hardware that runs the same total work
  at very different speeds (AMD's collector is single-threaded Python/numpy; NVIDIA's
  is a compiled multi-threaded OpenMP C binary). Both baseline and extended values are
  now empirically confirmed on real hardware (AMD: 4:35 baseline, ~15 min extended
  target calibrated from a real 20-iteration sample; NVIDIA: 0:50 baseline, ~1:12
  extended at the shared iteration count).
- **132/332 RAG Pipeline `query_count`**: raised from a stale 100/250 hang-risk cap to
  200/500. Traced the actual mechanism in the AMD/NVIDIA RAG-FAISS collector: per-query
  cost is linear (~1.18s/query, one embed+retrieve+rerank+generate pass, no retry/repeat
  construct), so the documented hang risk was from an earlier, unrelated bug (a
  duration-target formula that produced query counts in the tens of millions) and does
  not apply to this 2-5x increase.
- **124/324 Stable Diffusion XL `num_images`**: baseline raised from 7 to 15
  (extended unchanged at 7), per the MI300X VF timing note (7 images was 1:54; 15 images
  targets 3-5 min).
- **Ten remaining AMD-side override rows folded into the spreadsheet directly**: 110
  (NUMA cache `num_iterations`), 116/316 (RCCL bandwidth), 119/319 (PyTorch microkernel),
  120/320 (rocHPL `problem_size_N` and `num_iterations` -- clamps N to 32768 after a
  documented 228-minute hang at 65536), 123/323 (BERT inference), 126/326 (JAX XLA
  transformer). All were previously only correct if `config/parameter_overrides.yaml`
  was actually consulted at generation time; they are now correct directly in the
  spreadsheet regardless.
- **Six twin-gap workloads resolved** (313, 319, 323, 324, 326, 332): these AMD Ubuntu
  26.04 siblings previously carried byte-identical stale pre-retune values (and notes)
  copied from their 1xx AMD siblings' old state, with no override entry to correct them.
  All six now mirror their sibling's current, retuned value.
- All 28 entries in `config/parameter_overrides.yaml` now match `BenchmarkSpecDefinitions.xlsx`
  exactly (verified programmatically).

### Fixed (docs)

- `docs/AI_AGENT_INSTRUCTIONS.md` had a stale instruction limiting automatic
  `config/parameter_overrides.yaml` application to "116/316 and 120/320 only" -- a
  leftover from when the override file had two entries; it now has 28. Corrected to
  state the override applies to every workload it names, matching what
  `scripts/generate_benchmark_config.py` actually does in code.

### Known follow-ups

- `config/parameter_overrides.yaml` itself has not been deleted. It is now fully
  redundant with the spreadsheet (every entry matches), but removing it, along with the
  override-loading code in `matrix_profile_values.py` / `generate_benchmark_config.py` /
  `extract_benchmark_definition.py`, is a separate, not-yet-started cleanup step.
