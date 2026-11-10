# Changelog (archived)

> This file stopped at 2026-10-08. Current release notes are in the root [`CHANGELOG.md`](../CHANGELOG.md).

## 2026-10-08 — TEMPLATE_00_103 shared, versioned CI

- Workloads get two thin callers (`ci.yml`, `gpu-smoke.yml`) rendered from `config/ci_contract.yaml` and `templates/workload/`; the logic lives in `templates/shared-workflows/`, emitted once by `scripts/emit_shared_workflows.py` and tagged `v1`. `nightly.yml` and per-workload Dependabot are gone. Full notes in the root `CHANGELOG.md`.

## 2026-09-25 — TEMPLATE_00_87 official create contracts and metrics D1–D4

- Local directory and GitHub repository name are `<Workload Number>-<Repo Name>`. Workbook `Repo Name` stays unprefixed.
- Official Windows driver is Git Bash + OpenSSH. Create fails without a collector. Locked overlay YAML is merged. Official docs are `scripts/fill_generated_docs.py`.
- Framework flags and OS/vendor/driver policy are registry/policy files. Metrics D1–D4: paren key, unmash p50, split percentiles, ITL is not TPOT.

## 2026-09-22 — Numbered GitHub slugs and finish publish-doc rename

- Local directory and GitHub repository name are the same: `<Workload Number>-<Repo Name>` (example `128-gpu-bench-amd-vllm-throughput-latency`). Workbook `Repo Name` stays unprefixed.
- `docs/GITHUB_PUBLISH.md` → `docs/GITHUB_PUBLISH_WORKLOAD_REPO.md`. `docs/GITHUB_WORKLOAD_PUBLISH.md` → `docs/GITHUB_PUBLISH_GENERATOR_OPERATIONS.md`. Per-workload copy is `docs/examples/generated-repo-github/GITHUB_PUBLISH_WORKLOAD_REPO.md`, installed as `docs/GITHUB_PUBLISH_WORKLOAD_REPO.md`. Stale old names are leftovers and must not remain in the generator tree.

## 2026-09-22 — Template holes found on the 00_84 GitHub/VM pass

- `init_generated_repo.py` writes `config/pyproject.toml` with LF (`TEXT_SUFFIXES` includes `.toml`; `write_text(..., newline="\n")`). `prepare_github_publish.sh` and the remote `create_one_workload.py` CRLF strip now include `*.toml`.
- ROCm `setup.sh` defaults `SKIP_RVS=0` when Framework lists RVS; `BENCHMARK_SKIP_RVS` still wins.
- `apply_component_gaps.py` adds `numpy>=1.26` for `gups-amd` / `gups-nvidia`.
- `hip_memcpy_bw.cpp` checks `hipError_t` on timed `hipMemcpy` / sync / free so hipcc `nodiscard` stays clean.
- Extract no longer strips trailing `()` from Metrics slugs (`(failure_count)`, `(bandwidth_gbps_h2d)`, `(e2e_ms)`). Workbook cells were already balanced; `_strip_template_notes()` was dropping the closer.
- vLLM sitecustomize requires `scripts/templates/vllm_rocm_sitecustomize.py` and no longer falls back to a nested `*_copy/`.
- `prepare_github_publish.sh` deletes leftover `scripts/dir.txt` and `scripts/templates/dir.txt`. Removed the stray `ls` dump from the generator `scripts/templates/` tree so it is not copied into new repos.

## 2026-09-21 — Rename the two GitHub-publish docs for clarity

- `docs/GITHUB_PUBLISH.md` (the generator's own top-level doc) renamed to `docs/GITHUB_PUBLISH_WORKLOAD_REPO.md`. `docs/GITHUB_WORKLOAD_PUBLISH.md` (the generator-internal operator note) renamed to `docs/GITHUB_PUBLISH_GENERATOR_OPERATIONS.md`. The two names were easy to transpose in conversation and in scripts.
- Updated every in-repo cross-reference: `docs/repository-template.md`, `docs/TEMPLATE_README.md`, `scripts/check_github_publish_ready.sh` (`PUBLISH_LEFTOVERS`), `scripts/prepare_github_publish.sh` (`DOC_LEFTOVERS`), `.github/workflows/ci.yml`, and the cross-links inside the two renamed files themselves.
- Not renamed (different file, out of scope): the per-workload template that ships inside every generated repo, `docs/examples/generated-repo-github/GITHUB_PUBLISH.md`, and the workload-local copy it becomes after `init_generated_repo.py` installs it as `docs/GITHUB_PUBLISH.md` inside each generated repo. Those keep their existing name.

## 2026-09-12 — Remove workbook Implementation Pack column (TEMPLATE_00_84)

- `BenchmarkSpecDefinitions.xlsx` no longer has an Implementation Pack column. Future generated repositories do not extract or require that field.
- Init resolves overlays from `config/implementation_packs.yaml` by Workload Number and GPU Vendor.

## 2026-09-11 — Remove parameter_overrides.yaml

- Generation no longer applies a sidecar override file. `Parameters_SmokeBaselineExtend` is the only smoke/baseline/extended contract. The deleted yaml was not folded into the workbook.

## 2026-09-07 — TEMPLATE_00_78 NVIDIA 201–232 runtime findings (00_77 H100)

- Validator/parser/ledger: `rc=0` is a success return code, not a missing metric. 205 no longer fails validation or writes `0.0` into the pass-rate ledger slot.
- 211: matching `linux-tools-$(uname -r)` plus a versioned `perf` resolver.
- 212: lmbench `lat_mem_rd` timeouts and last-line parse.
- 218: install cuDNN headers/libs before `nvcc -lcudnn`.
- 230/231: pin 24.04 torch/sglang/sglang-kernel so Hopper `common_ops` loads.

## 2026-09-07 — TEMPLATE_00_78 duration retunes and overlay holes

- hipMemcpy/BabelStream/RCCL overlays now include the HIP/RCCL sources that generation previously had to invent. hipMemcpy treats `direction=all` as all three copies and does not stub bandwidth rows.
- `config/parameter_overrides.yaml` retunes 115/315, 116/316, 117/317, 124/324, and 128/129/328/329 from the 2026-09-07 MI300X VF batch (too-short 116/117/124; too-long 115/128/129).
- SGLang setup installs `jsonschema` and verifies `sglang.srt.entrypoints.http_server.launch_server`. 130 client keeps CSV for the leftover-DB parser.
- Overlay selectors fold Unicode hyphens. Yaml writes `0.9` as a float. Self-check CRLF skips third-party clones.

## 2026-09-06 — Created-repository location and runtime-artifact filter

- The AI Coding Agent (ie, Cursor) project-root sibling is the created repository only. It is a sibling of `ai-agent-gpu-benchmark-repo-generator`. Do not pass `--project-root /root` or treat a validation VM home as the deliverable.
- Develop the code in the local directory, and copy it to the remote VM for testing. Do not copy anything from the VM back to the local directory. `.venv/`, `.cache/`, and other validation-host runtime state stay on the VM.
- If a remote test fails, edit the local sibling and copy that local tree to the VM again.
- Checklist items 3.11e and 3.11f fail `passed` when the local sibling is missing, was populated from the VM, or contains validation-host runtime state.

## 2026-09-06 — Post-generation root cleanup

- After every requested workload directory is recorded, agents must delete generation-time scratch from the local project root and the remote validation host home: `*_create_start_time.txt`, `workload_identities.txt`, `rocm_pip_constraints.txt`, `_fill_generated_docs.py`, `patch_generated_repo.py`, `finish_one_workload.sh`, `process_range.sh`, `_generation_helpers/`, `batch_process*.log`, `batch_process*.stdout`, `retry*.stdout`, and root-level `*_setup.log`.
- Keep the source template, each `<Workload Number>-<Repo Name>/` directory, `AI_AGENT_PROMPT_SUBMITTED_*.md`, and the local `batch_generation_manifest.json`. After that local manifest is authoritative, also remove the VM-root copy of the manifest and leftover helpers. Do not delete generated repositories or `/root/runtime_ledger.csv`.

## 2026-09-05 — TEMPLATE_00_73 spec-aligned 101–132 and 201–232 workbook

- Forked from `TEMPLATE_00_72`. Collectors and `implementation_components/` are unchanged. The live `BenchmarkSpecDefinitions.xlsx` now describes what those 00_72 collectors actually run for workloads 101–132 (AMD) and 201–232 (NVIDIA).
- Narrative fields rewritten to match generated implementations: tools, methodology, execution details (Run/Compile/Build/Launch), metrics, raw-output contract, software framework, and ≤35-word constraints. `Parameters_SmokeBaselineExtend` values are unchanged. Command columns are rebuilt display from that sheet plus `config/parameter_overrides.yaml`.
- 301–332 and 401–432 rows are unchanged. The pre-update 00_72 workbook is `archive/BenchmarkSpecDefinitions_ORIGINAL_00_72.xlsx`.
- Schema Last Updated is `2026-09-05` on the 64 revised rows.

## 2026-09-04 — TEMPLATE_00_72 generator uses richer implementation components

- `component.json` now records `role`, `completeness`, `provides` / `does_not_provide`, `verifies`, `contracts`, `also_applies_to`, and mixin `apply_when`. Selectors accept `in` and `prefix`.
- Mixins: `harness-self-check` (no-op RAG stubs), `rocm-tool-verify-build`, `rocblas-clients-build`. Init writes `results/overlay_lock.json` and `results/component_leftover_work.md`. `apply_component_gaps.py` adds `--seed-fixture`, PyYAML, and `gate.json` thresholds after yaml generation.
- `smoke_check_generated_repo.sh` keys rocBLAS GEMM tokens off `contracts.gemm_per_point`, not Framework containing `rocBLAS`. 103 / `system-stress-amd` is install+verify + clients compile only.
- `generation_host_preflight.py` runs from `create_generated_repo.py`. Batch validator allows null `generation_finished_at` while repositories are still being appended.
- Ubuntu 24.04 `rocm_compile_rocblas_bench` skips when `<repo>/third_party/rocBLAS/build/release/clients/staging/rocblas-bench` exists and exports that PATH. Generated-repo CRLF scan skips unused nested `implementation_components/`.

## 2026-09-02 — NVIDIA lock overlays for the 12 IDs that had no component

- Added NVIDIA `implementation_components` so 201/401, 202/402, 203/403, 204/404, 206/406, 208/408, 211/411, 212/412, 213/413, 214/414, 216/416, and 220/420 no longer resolve to zero overlays: `system-config-nvidia`, `gpu-health-nvidia`, `system-stress-nvidia`, `sdc-ecc-nvidia`, `fio-nvme-nvidia`, `iperf3-nvidia`, `linux-perf-pmu-nvidia`, `lmbench-nvidia`, `gups-nvidia`, `cuda-memcpy-nvidia`, `nccl-bandwidth-nvidia`, `linpack-hpl-nvidia`.
- Collectors fail closed. HPL is cuSOLVER GETRF/GETRS (`src/nvhpl.cu`), NCCL links libnccl (`ncclAllReduce`), GUPS is OpenMP C, memcpy reports H2D/D2H/D2D separately, SDC walks GPU memory only. No column-name stub (`return 10.0` TFLOPS).
- `setup_nvidia_skeleton.sh` and `self_check_generated_repo.sh` require the new binaries when those sources are present.

## 2026-09-02 — TEMPLATE_00_70 AMD 130/131/132 loop fixes and serving overlay hole

- `hipcc_host_gcc.sh` no longer writes Clang `--gcc-install-dir` into `CXXFLAGS`. 130/131 baseline on Ubuntu 24.04 / ROCm 7.2.1 died in `sgl-kernel` `setup_rocm.py` when host `g++` rejected that flag. The pin stays on `HIPCC_COMPILE_FLAGS_APPEND` and `HIPFLAGS` for Ubuntu 26.04 hipcc. The SGLang compile subshell also `unset CXXFLAGS`.
- AMD `sglang-*-amd` `ensure_setup.sh` skips `import sglang` / `launch_server --help` when the profile is smoke and `tiny_sglang_server.py` is present. Baseline/extended still re-run setup when those checks fail. Runners pass `--profile`.
- `install_rag_amd.sh` and `install_rag_nvidia.sh` install `sentencepiece` (and `tiktoken`). 132 collection died converting Mistral's SentencePiece tokenizer; tiktoken alone was not enough.
- NVIDIA/AMD vLLM and SGLang overlays now ship `tiny_kv_server.py` / `tiny_sglang_server.py` / `prompt_response_client.py` (the 00_69 hole that broke 227–231 generate). `self_check_generated_repo.sh` gates the hipcc `CXXFLAGS` leak, smoke-aware `ensure_setup`, and RAG `sentencepiece`.

## 2026-09-01 — TEMPLATE_00_69 AMD overlays on the 00_68 factory

- Factory is the 00_68 tree (NVIDIA vendor path kept) plus AMD collectors so 101–126 create no longer depends on unofficial `_generation_tools` stubs.
- New AMD-only overlays write spec CSV to `--raw-file` with at least two rows and `lineterminator=chr(10)`: 101–123 and 125–126. hipmemcpy / BabelStream / RCCL overlays now include collectors with a 3600 s timeout. 108 UDP uses a `1M` rate floor (`-b 0` is refused).
- `init_generated_repo.py` calls `scripts/materialize_generated_harness.py` after overlays: empty `parse_results.py` DROPs leftover SQLite tables, strips `stats:`, and quotes identifiers; empty `run_benchmark.sh` / `validate_results.py` are filled. Overlay `run_benchmark.sh` / leftover-DB parsers still win.
- ROCm setup installs torch from Workload Name for SDC / tensor / GEMM / MIOpen / ResNet / BERT / DistilBERT / JAX when Framework omits `pytorch`. Adds transformers (not vLLM/SGLang), numpy for GUPS, and lmbench when named. Never calls `install_pytorch_nvidia.sh`.
- rocHPL N=32768 smoke/baseline cap is 6 (~3–5 min); extended stays 16. `parameter_overrides.yaml` sets 120/320 baseline `num_iterations=6`.

## 2026-09-01 — TEMPLATE_00_68 NVIDIA creation path

- `init_generated_repo.py` keys setup off `GPU Vendor`. NVIDIA workloads get `scripts/templates/setup_nvidia_skeleton.sh` and never receive the ROCm skeleton, including when Framework contains `vllm` or `llm serving`.
- NVIDIA overlay `setup.sh` (vLLM / SGLang) is kept: the NVIDIA skeleton is copied **before** overlays and is not recopied afterward. ROCm still recopies its skeleton after overlays.
- New `scripts/install_pytorch_nvidia.sh` and `docs/nvidia-pytorch-install-contract.md` install CUDA wheels (cu128 on 24.04, cu130 on 26.04). Do not list `torch`/`jax` in `requirements.txt`. Do not call this helper from the ROCm skeleton.
- Completed NVIDIA overlays so generation no longer depends on a probe-first stub `build.sh`: cuBLAS `scripts/build.sh`, cuDNN `src/cudnn_conv.cu` + build, NVIDIA BabelStream, Torch micro GEMM/Conv2d, ResNet train/infer collectors, BERT, DistilBERT, JAX, and tensor-correctness `collect_tensor_ops.py`.
- Shared vendorless overlays now ship real builds: `stream-reference` `scripts/build.sh` (gcc OpenMP, no nvcc) and `numa-cache-collector` `src/numa_sweep.cpp` + g++ `build.sh`. These also apply to AMD 107/110.
- `self_check_generated_repo.sh` skips the ROCm token contract when `GPU Vendor` is NVIDIA and asserts NVIDIA compile/torch setup instead.
- Agents must invoke overlay collectors and must not write a dummy `collect_workload.py` or a `cuda_stack_probe.cu`-first `build.sh`.

## 2026-08-31 — 430/431 lessons applied to AMD SGLang 330/331

- NVIDIA 430/431 stay green because setup proves `launch_server --help`, `ensure_setup` re-runs when `import sglang` fails, and launch always uses `--tp 1 --mem-fraction-static 0.8`. They do not hit AITER JIT locks. AMD 331 already had extras / qwen3_asr / watchdog / lock cleanup. 330 still launched without TP, mem-fraction, `--disable-cuda-graph`, or watchdog.
- `sglang-prompt-response-amd` now launches with the same TP/mem-fraction as 430 plus AMD `--disable-cuda-graph --watchdog-timeout 1800` and `lock_module_*` cleanup. Both AMD SGLang overlays ship `scripts/ensure_setup.sh` that re-runs setup when `import sglang`, `import aiter`, or `launch_server --help` fails. Self-check requires those 330 launch flags.

## 2026-08-31 — GitHub publish: kernel/PRD accuracy and actual-csv leftovers

- `self_check_generated_repo.sh` and `check_github_publish_ready.sh` fail when README/SPEC advertise a `--kernel-version` (or kernel table default) that disagrees with `config/benchmark_config.yaml`, when `PRD.md` Workload Number disagrees with `benchmark_specification.json`, or when public docs still contain a `TEMPLATE_00_*` authoring note. 301 docs copied from 101 had `6.8.0` and PRD `101` while yaml/JSON were `7.0.0` / `301`.
- `prepare_github_publish.sh` 1.1.1 treats `benchmark_actual.csv` and `benchmark_actual_excel.csv` as generator leftovers (same as generation schemas). `.gitignore` and generated CI `test ! -f` those files. They stay in the generation tree as workbook-vs-implementation bookkeeping and must not ship.
- `init_generated_repo.py` rewrites copied `config/pyproject.toml` `[project]` name/description to the workload repo name so a published clone does not claim to be `ai-agent-gpu-benchmark-repo-generator`.

## 2026-08-31 — Workbook drops TEMPLATE_00_51 leftover notes

- `BenchmarkSpecDefinitions.xlsx` `Command Execution Details and Purpose` (101/105/106/110/112/117/118 and 301/305/306/310/312/317/318), matching `Parser and Normalization Notes` (106/110/306/310), and `Parameters_SmokeBaselineExtend` notes that still said `00_51` no longer cite `TEMPLATE_00_51`, `00_50` yaml overrides, verified 20260815 run IDs, or `docs/TEMPLATE_00_51_WORKLOAD_DELTAS.md`. Still-true runner rules stay in those cells (errors_info vs exit code, FP32 atol pointer, fio/numa sweep flags, lmbench timeouts, rocBLAS `--cold_iters`/`-v`, MIOpen omit `-S`).

## 2026-08-31 — 309 DCE zeros and 330/331 launch_server import failures

- New overlay `multichase-numa-amd` ships `src/multichase.c` that chases through `void * volatile`. gcc `-O2` was deleting the old `(void)p;` loop, so baseline `num_iterations=1330000000` printed `latency_ns 0.000000` and validate failed. Collector now exits 1 on a zero/failed sample.
- AMD SGLang setup always installs `orjson` / `pybase64` / `starlette` / `pyzmq` / `openai` / `uvloop` / `gguf` / `dill` and patches `AutoConfig.register("qwen3_asr", ..., exist_ok=True)`. The already-importable path used to skip extras, so 330 baseline died at `import zmq` and 331 died on a Transformers `qwen3_asr` double-register. Both paths now run `python -m sglang.launch_server --help`. AMD serving (`sglang-serving-amd`) adds `--disable-cuda-graph` and `--watchdog-timeout 1800`, and deletes leftover AITER `lock_module_*` files before launch. A stale `lock_module_rmsnorm_quant` made the first decode hang until the 300 s watchdog killed the server; the client then saw `RemoteDisconnected`.

## 2026-08-29 — GitHub publish gate (self-scan, leftovers, clone URL, post-apply check)

- `prepare_github_publish.sh` 1.1.0 no longer fails a clean repo by grepping its own secret-scan patterns. Leftovers now include `.claude/`, `docs/GITHUB_WORKLOAD_PUBLISH.md`, `scripts/self_check_generated_repo.sh`, generation schemas, and unused `scripts/build_faiss_rocm.sh`. `--apply` strips the dead `docs/repository-template.md` README line, replaces `<org>` when `--github-owner` is set, patches CI off generation-only checks, and runs `check_github_publish_ready.sh --published`.
- `check_github_publish_ready.sh` 1.1.0 auto-detects generation vs published trees. Published mode requires leftovers gone, README relative links to resolve, and host-safe `bash -n` / `compileall`.
- Generated CONTRIBUTING / Copilot / PR templates no longer point at `AGENTS.md` or `self_check_generated_repo.sh`. README template splits supported vs reference hardware and ships a layout section instead of a deleted-doc link.

## 2026-08-29 — TEMPLATE_00_66 loop-review fixes (ledger trap, 116/120, 130/131)

- `scripts/lib/common.sh` installs an `ERR` trap in `begin_benchmark_run` and enables `set -E` (errtrace). Without errtrace, bash does not inherit ERR into functions, so 102's `validate_phase` exited 1 under `set -e` and never wrote a ledger row. The trap still exits 1 and does not mask the failure.
- Operator retunes live in `config/parameter_overrides.yaml` and are applied after `Parameters_SmokeBaselineExtend`. 116/316 `num_iterations` baseline/extended are 200000 / 500000. 120/320 extended `problem_size_N` is 32768 and `num_iterations` is 16. 110 / 113 / 119 / 123 / 124 / 126 / 132 duration retunes from the 2026-09-05 MI300X VF batch are also overridden.
- `linpack-rochpl-amd` clamps `N>=65536` to 32768, allows up to 16 timed repeats at `N=32768` (~12 min), and times out a stuck solve at 180 s. Loop-2 extended `N=65536` died in 2:16 with `hipErrorIllegalAddress` / Tensile `unordered_map::at`.
- AMD SGLang runners call `isolate_repo_python` and default `HF_HOME` to `$HOME/.cache/huggingface`. Setup refuses a `sglang` import from another repo tree, uninstalls CUDA CUTLASS wheels, and dies on the nanobind `DiagnosticSeverity` collision.

## 2026-08-28 — Remaining 00_64 loop fixes (320/332/327/314–316/README)

- rocHPL `linpack-rochpl-amd` now overlays `scripts/collect_workload.py`, `scripts/build.sh`, and `Makefile`. Timed repeats are **2** when `N>=32768`. Workbook extended `num_iterations=84` at `N=65536` is days per solve; validation only needs two samples. Self-check rejects `repeats = max(2, int(args.num_iterations`.
- New `rag-faiss-end2end-amd` replaces the 132/332 `torch.nn.Linear` stub with the same squad_v2 + FAISS + BGE + Mistral path as 232/432. `install_rag_amd.sh` reuses ROCm torch (no CUDA wheel). The ROCm setup skeleton calls that helper when present.
- New `vllm-kvcache-amd` (327) adds tokenizer slack and HTTP 400 bodies. Yaml `max_model_len=8192` already has room for 4096+256; slack is still applied.
- New hipcc `scripts/build.sh` overlays `hipmemcpy-bandwidth-amd`, `babelstream-hbm-amd`, and `rccl-bandwidth-amd` source `scripts/lib/hipcc_host_gcc.sh` instead of hardcoding GCC 15 only.
- `self_check_generated_repo.sh` now fails generate-time stub READMEs (under 80 lines, missing Prerequisites, mermaid, or template headings). `prepare_github_publish.sh` remains the post-generate publish gate.

## 2026-08-28 — AMD vLLM context slack and SGLang compile-by-default

- AMD 128/129/328/329 had no overlays, so generation wrote `max_model_len=$((INPUT_LEN + OUTPUT_LEN))`. Mistral tokenizes `("token " * N)` as N+1 (BOS). Baseline 512+18600 became 19112 vs 19113 and vLLM returned HTTP 400 in under a minute. New overlays `vllm-throughput-amd` and `vllm-token-generation-amd` set `TOKENIZER_CONTEXT_SLACK=64`, cap at 32768, clamp client `max_tokens` with `TOKENIZER_BOS_SLACK`, and print HTTP 400 bodies. NVIDIA 228/229 overlays use the same slack.
- AMD 130/131/330/331 setup skipped SGLang compile (`BENCHMARK_COMPILE_SGLANG=0`). Smoke used `tiny_sglang_server.py`, so generation passed; baseline died with `No module named 'sglang'`. Setup now defaults `BENCHMARK_COMPILE_SGLANG=1` when Framework includes sglang and **dies** if `import sglang` still fails. New `sglang-prompt-response-amd` runner and updated `sglang-serving-amd` check `import sglang` / `import aiter` before `launch_server`.

## 2026-08-28 — GitHub publish prep

- Operator note for the five publish steps, dry-run, four-flavor mapping, and naming: `docs/GITHUB_WORKLOAD_PUBLISH.md`.
- Added `scripts/prepare_github_publish.sh` for a final cleanup before an independent GitHub push: strip generator leftovers, LF-normalize, clone-safe CI, secret/README gates. `--apply` refuses a nested `*_copy` unless `--in-place`.
- `init_generated_repo.py` no longer copies `AGENTS.md` or `*TEMPLATE.md` onto the generated root. Generated CI no longer runs generation-time `self_check_generated_repo.sh`. `check_github_publish_ready.sh` rejects stub READMEs and leftover templates.
- README template requires a Prerequisites block and a mermaid setup→run→parse diagram.

## 2026-08-28 — hipcc GCC 15 pin and rocHPL 64-bit host allocations

- Added `scripts/lib/hipcc_host_gcc.sh`. `scripts/lib/common.sh` sources it so setup and collect export `HIPCC_COMPILE_FLAGS_APPEND=--gcc-install-dir=/usr/lib/gcc/x86_64-linux-gnu/15` (then 14, then 13). Ubuntu 26.04 / ROCm 7.14 hipcc (Clang 23) prefers GCC 16, which does not expose `<cstdlib>` to the HIP wrapper; a bare `hipcc -O2` fails with `'cstdlib' file not found` (314/315/316 loop failures).
- Generated `scripts/build.sh` that invokes `hipcc` must source that helper or pass `--gcc-install-dir`. `self_check_generated_repo.sh` enforces it. Ubuntu 26.04 setup installs `g++-15`. Also export `LD_LIBRARY_PATH=/opt/rocm/lib:/opt/rocm/lib64` so HIP binaries find `libamdhip64.so.7`.
- New overlay `linpack-rochpl-amd` (`src/rochpl.cpp`) for Workload Name `rocHPL FP64 (High Performance Linpack)`. Host matrix length is `size_t nn = n64 * n64`. Signed 32-bit `n * n` overflows at workbook extended `N=65536`. Self-check rejects `host_a(n * n)`. Open MPI `help-prun.txt` misses are secondary.

## 2026-08-27 — NVIDIA 26.04 SGLang / RAG contract

- NVIDIA SGLang overlay `install_sglang_nvidia.sh` branches: Ubuntu 26.04 / Python 3.14 pins `torch 2.9.1+cu130` and `sglang==0.5.10.post1 --no-deps`; 24.04 keeps the 230/231 recipe. Added `install_sglang_launch_deps.py`, `sglang_py314_patch.py`, and `sglang_py314.pth` to both NVIDIA SGLang components.
- Workbook 430/431 pin those versions. Sequential 130/230/330/430 baseline and extended `num_prompts` is 8. 232/432 model IDs are `rajpurkar/squad_v2`, `BAAI/bge-small-en-v1.5`, `faiss`, `mistralai/Mistral-7B-v0.3`, `BAAI/bge-reranker-base`, `dense`. 432 PyTorch is `2.13.0+cu130`.
- New `rag-faiss-end2end-nvidia` overlay replaces the Linear stub with a real HF + FAISS + Mistral runner. Setup must call `scripts/install_rag_nvidia.sh`.
- Collector stdout no longer prints `Failed commands:` (failures stay in `errors_info.txt`). Documented in `docs/nvidia-sglang-install-contract.md` and `AGENTS.md` §20.2.

## 2026-08-27 — Fold overlay contracts into the framework

- Removed `docs/TEMPLATE_00_53_WORKLOAD_DELTAS.md`, `TEMPLATE_00_54_WORKLOAD_DELTAS.md`, `TEMPLATE_00_55_WORKLOAD_DELTAS.md`, `TEMPLATE_00_62_WORKLOAD_DELTAS.md`, and `TEMPLATE_00_64_WORKLOAD_DELTAS.md`.
- Overlay copy/immutability lives in `implementation_components/README.md` and `AGENTS.md` §20.25. Current runner rules stay in `AGENTS.md` §20.2. Ubuntu 26.04 / ROCm 7.14 extras live in `docs/rocm-pytorch-install-contract.md`. History remains in this changelog.

## 2026-08-27 — TEMPLATE_00_64

- Seed copied from TEMPLATE_00_63 with NVIDIA 401–432 Ubuntu 26.04 / CUDA 13.3 workbook pins, 405 `PyTorch 2.13.0+cu130`, `ensure_setup.sh` missing-venv rebuild, `HF_HOME`/`PIP_CACHE_DIR` overlay-root defaults, and the cuDNN height>32 timeout (10.0 ms/iter).
- AMD 301–332 `Repo Name` suffixes are now `-ubu2604` (same form as 401–432), not `-2604`. Example: `301_sys-bench-amd-rocm-stack-validation-ubu2604`.

## 2026-08-27 — Baseline loop fixes (418 timeout, ensure_setup, HF cache)

- `scripts/ensure_setup.sh` re-runs `setup.sh` when `.setup_state` exists but `.venv/bin/python` is missing (stale state after a failed or quota-killed venv).
- `scripts/lib/common.sh` defaults `HF_HOME` and `PIP_CACHE_DIR` to `$HOME/.cache/...` so overlay runners that use `${HF_HOME:-${REPO_ROOT}/.cache/huggingface}` keep 7B+ snapshots off quotaed `/workspace`.
- cuDNN overlay `collect_cudnn_conv.py` raises the height>32 per-iteration timeout from 3.0 ms to 10.0 ms (baseline 168000-iter 224 Find/all-dirs timed out at 684s / exit 124 on H100).

## 2026-08-27 — Per-run metrics_summary.txt

- Successful `run_benchmark.sh` writes `metrics_summary.txt` in the per-run `results/raw/<timestamp>_<repo>_<hostname>/` directory via `write_metrics_summary_txt` in `scripts/lib/common.sh`.
- The file is the Benchmark Summary block without `[INFO]` prefixes (header, run identity, commands, timing, artifacts, `#1`–`#N` metrics).
- AMD and NVIDIA overlay runners call the helper so 101–132, 201–232, 301–332, and 401–432 all emit the same artifact.

## 2026-08-26 — TEMPLATE_00_62 Ubuntu 26.04 install contract

- Setup skeleton installs `torch` plus `amd-torch-device-gfx942` from the AMD multi-arch index. Do not use `torch[device-all]`.
- vLLM on 26.04 keeps the `wheels.vllm.ai/rocm/` prefix check, then installs the AMD cp314 wheel, flash-attn wheel, and `uvloop` / `fastapi` / `aiohttp`. Extra-deps pip is non-fatal.
- AITER prefers the AMD `amd-aiter` wheel (`import aiter`). SGLang source compile is opt-in via `BENCHMARK_COMPILE_SGLANG=1`.
- Added `docs/TEMPLATE_00_62_WORKLOAD_DELTAS.md`. Self-check now includes leftover-DB 330, serving 331, and tiny_kv 327–329.

## 2026-08-26 — Ubuntu 26.04 / ROCm 7.14 workload series (301–332)

- Added workloads 301–332 as the Ubuntu 26.04 MI300X siblings of 101–132. Repo names use a `-2604` suffix (for example `301_sys-bench-amd-rocm-stack-validation-2604`).
- `scripts/lib/rocm_install.sh` is now a dispatcher that sources `rocm_install_24_04.sh` (ROCm 7.2.1 / noble) or `rocm_install_26_04.sh` (ROCm 7.14 / resolute) from the host Ubuntu release.
- Workbook version columns for 301–332 pin kernel 7.0.0, Python 3.14.4, ROCm 7.14, and host-native Ubuntu 26.04 (no container image).
- Extractor aliases map `GPU Runtime Version (was ROCm Version)` → `ROCm Version` and `BLAS Version (was rocBLAS version)` → `rocBLAS Version`.
- Remote validation accepts an Ubuntu 26.04 login banner when the workload `OS Version` is Ubuntu 26.04.

## 2026-08-23 — GitHub-ready generated workload repositories

- Generated workloads now receive workload-specific GitHub community files instead of inheriting generator-specific `.github/` guidance.
- Added `scripts/check_github_publish_ready.sh` as the final publication gate for completed workloads.
- Generated CI now verifies GitHub publication readiness without installing GPU stacks or running the benchmark on GitHub-hosted runners.
- Added workload-specific `docs/GITHUB_PUBLISH.md` with independent repository initialization/push instructions.
- Completion contracts now require a finalized README, root LICENSE, `legal/NOTICE`, GitHub community files/workflows, safe ignore rules, and no runtime dependence on the nested `TEMPLATE_*_copy/` generation workspace.

- Relocated `NOTICE` from the repository root to `legal/NOTICE`; updated generation, CI, and documentation references accordingly.

- Repository tooling configuration moved from root `pyproject.toml` to `config/pyproject.toml`; CI, contributor guidance, and installation commands now reference the relocated file explicitly.

## 2026-08-23 — Automatic implementation-component discovery

- Removed the user-maintained `Implementation Components` column from `BenchmarkSpecDefinitions.xlsx`.
- Added semantic selector metadata to every implementation component manifest.
- Added `scripts/resolve_implementation_components.py` for deterministic automatic discovery and conflict validation.
- `scripts/init_generated_repo.py` now applies discovered components and records resolution details in `generation_manifest.json`.
- Updated agent instructions, workflow documentation, smoke checks, and CI to treat component selection as an internal generator responsibility.

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Full release identifiers (including the internal template-release tag) are recorded in [`TEMPLATE_README.md`](TEMPLATE_README.md).

## [Unreleased]

### Changed

- 124/224 baseline and extended now load real Diffusers SDXL (`stabilityai/stable-diffusion-xl-base-1.0`). Smoke stays a local tiny denoiser and does not download weights. Workbook `num_inference_steps` is 2 / 30 / 50. Overlays live under `implementation_components/sdxl-diffusers-amd` and `implementation_components/sdxl-diffusers-nvidia`. Live 00_54 trees are unchanged.
- TEMPLATE_00_55 renames the runtime workbook to `BenchmarkSpecDefinitions.xlsx` and the generated contract to `benchmark_specification.json` (schema `schemas/benchmark_specification.schema.json`). `--specification` and `--benchmark-specification` are canonical; `--matrix-definition` and `--benchmark-definition` remain aliases. Live 00_54 trees are unchanged.

### Added

- TEMPLATE_00_55 publish readiness: `NOTICE`; generated-repo CI that does not run `setup.sh` on `ubuntu-latest`; `.gitignore` excludes `ai-agent-gpu-benchmark-repo-generator_copy/`; `docs/GITHUB_PUBLISH.md` and `docs/SIBLING_WORKLOAD_NOTES.md`.
- 131/231 overlays persist Metrics #4 Inter-token latency and #5 Request throughput. CLI default for 131/227–231 is smoke.
- 00_54 launch overlays so the next generate cannot keep tiny/stub servers for baseline/extended: 131/231 SGLang, 227/228/229 vLLM, 230 real SGLang plus leftover-DB parse. 231/230 prepend venv `nvidia/*/lib` and install `ninja`. `wait_for_server` fails if `SERVER_PID` has exited. Documented in `docs/TEMPLATE_00_54_WORKLOAD_DELTAS.md`.
- Public-preview identity `0.9.0` (`TEMPLATE_00_54`): `pyproject.toml` declares `jsonschema`, `openpyxl`, and `PyYAML`; `.github/SECURITY.md` and README badges use `github.com/garymichaelbass/ai-agent-gpu-benchmark-repo-generator`.
- Example HW/SW inventory files are synthetic (RFC 5737 documentation addresses). Live lab IPs, serials, UUIDs, and MACs were removed.
- Operator retune scripts and the dated SSH ROCm installer moved under `archive/` (skipped by generate copy). Do not re-run `archive/operator/overnight_align_profiles.py` or `retime_baseline_profiles.py` against the current workbook.
- Benchmark Summary prints `Command submitted` and `Command fully resolved` immediately after the Run ID line, via `print_benchmark_summary_commands` in `scripts/lib/common.sh`. Values are the captured argv strings (hyphenated flags). Empty if unknown; do not invent a command. Documented in `docs/run-output-contract.md`.
- `/root/runtime_ledger.csv` adds `Parameter_01_Name`/`Parameter_01_Value` through `Parameter_20_Name`/`Parameter_20_Value` after `run_benchmark_command_fully_resolved` and before `parameters_set`. Slots follow workbook `Parameter_01`–`Parameter_20` order. Values are the effective map after CLI overrides (submitted flags, then the fully resolved command, then `--parameters-set`, then yaml). Unused slots stay blank, not em-dash. `parameters_set` is rebuilt from those slots as `profile=<name>;key=value;...`. Existing ledgers fill the 40 columns on the next append from the old command and `parameters_set` blob.
- `/root/runtime_ledger.csv` keeps the command column in its current position and splits it into `run_benchmark_command_submitted` (argv as entered) plus `run_benchmark_command_fully_resolved` immediately to its right (submitted flags plus yaml defaults that were not already on the command line). Existing `run_benchmark_command` values migrate into `run_benchmark_command_fully_resolved`; submitted stays empty when unknown. `scripts/lib/common.sh` captures submitted argv via `capture_benchmark_run_command_submitted`.
- `implementation_components/` overlays for the 00_51/00_52 loop failures that remained after first-pass generation: official STREAM `src/stream.c` for 107 and 207, leftover-`benchmark.db` migrate/rebuild `scripts/parse_results.py` for 130 and 230. Documented in `docs/TEMPLATE_00_53_WORKLOAD_DELTAS.md`. The generating agent must not rewrite those overlay files.
- `scripts/self_check_generated_repo.sh` fails STREAM checksums that sum raw array values or omit relative `aAvgErr / aj`, and fails 130/230 parsers that cannot migrate or rebuild a leftover SQLite file.

### Changed

- `LICENSE` copyright is Gary Bass (2026). The AMD-specific Licensor line is removed. Script headers use `Maintainer: AI Agent GPU Benchmark Repo Generator` instead of AMD/NVIDIA authorship claims.
- README states that the workbook is the 64-row catalog and `implementation_components/` ships known-fix overlays, not 64 pre-generated repositories.

- 125/225 `Workload_Definitions` now list `num_iterations` in `Parameter_*` so the generated command columns include `--num-iterations 2 / 17300 / 50900`.
- 125/225 `num_iterations` retimed from measured 11.4 ms/step to 17300 / 50900. 131/231 baseline `num_prompts` set to 24 (three concurrency-8 waves). Applied on both VMs and copied AMD→NVIDIA.
- `Parameters_SmokeBaselineExtend` 2026-08-18 retune: 109/125/131/132 baselines ≥3 min and extended ≥10 min; 107/113/115/122 extended ~15 min; matching 2xx knobs copied from AMD. 125/225 gained `num_iterations` because steps were previously hardcoded.
- `Parameters_SmokeBaselineExtend` overnight align (2026-08-17): AMD 105/112/127/128/129 baselines lengthened past three minutes from ledger `20260817_183903`; 130/131 `dtype` changed from `bf16` to `bfloat16` so SGLang will start; 201–232 shared knobs copied from 101–132 for MI300X vs H100 comparison. `archive/operator/overnight_align_profiles.py` applied the sheet edits; `scripts/sync_matrix_profile_commands.py` refreshes command columns. Do not re-run the align script.
- `Parameters_SmokeBaselineExtend` retimes selected baseline knobs toward 3–4 minutes from the 2026-08-17 AMD 101–132 and NVIDIA 201–232 ledger runs. Extended values keep the prior extended/baseline ratio. Inventory/correctness workloads 101/102/105/201/202 and stub RAG 132/232 are unchanged. LLM serving 127/227 `num_prompts` and 128/129/131/228/229/231 `output_len` are scaled for real vLLM/SGLang, not tiny_kv. `archive/operator/retime_baseline_profiles.py` applied the sheet edits; `scripts/sync_matrix_profile_commands.py` refreshes command columns. Do not re-run the retime script.
- Removed `docs/TEMPLATE_00_50_WORKLOAD_DELTAS.md` and `docs/TEMPLATE_00_51_WORKLOAD_DELTAS.md` from the generate-time read list. Current runner rules live in `AGENTS.md` §20.2. Smoke, baseline, and extended timings come only from the workbook `Parameters_SmokeBaselineExtend` sheet. Historical 1.04/1.05 changelog entries remain as history.
- Workbook sheet names are `Workload_Definitions` (workload rows and generated command columns) and `Parameters_SmokeBaselineExtend` (smoke/baseline/extended authoring). Older `Sheet4` / `ProfileValues` names remain as fallbacks in scripts and as history in 1.04/1.05 changelog entries.
- `/root/runtime_ledger.csv` drops `runtime_exit_code`. After `exit_code` the columns are `failure_stage`, `failure_detail`, and `raw_run_dir`. `failure_stage` is `ok` on success or `setup|collection|parse|validation|timeout|integrity|other` on failure. `failure_detail` is the one-line reason for a nonzero `exit_code`. `raw_run_dir` is the per-invocation `results/raw/...` directory. After `metric_5_result` the columns are `run_benchmark_command`, `parameters_set`, `notes`. `run_benchmark_command` is the effective `bash run_benchmark.sh --<profile> --validate ...` string; when omitted it is reconstructed from `Profile Parameter Values`. Existing ledgers with the previous header are rewritten on the next append; old `notes` values are used to infer `failure_stage` when needed.
- `scripts/matrix_profile_values.py` skips repeated `Workload_Definitions` header rows so `sync_matrix_profile_commands.py` can write 201–232 command columns in the same workbook as 101–132.

## [1.05] - 2026-08-15

### Added

- Workbook `ProfileValues` sheet is the authoring source for smoke/baseline/extended parameter values. `Parameter_01`–`Parameter_20` remain the name list.
- `scripts/sync_matrix_profile_commands.py` regenerates Sheet4 `run_benchmark Command Plus Options for * Run` cells from `ProfileValues`.
- `scripts/generate_benchmark_config.py` writes the initial `config/benchmark_config.yaml` `sweep:` block from `Profile Parameter Values`. `scripts/create_generated_repo.py` invokes it after scaffold init.
- `scripts/extract_benchmark_definition.py` emits `Profile Parameter Values` and `Profile Command Authorship`.
- `docs/TEMPLATE_00_51_WORKLOAD_DELTAS.md` records the verified 106/110/128/129 extended execution contract plus 101/112/117/118 runner maps, 130 five-metric rule, ledger-on-`die`, and 600 s `wait_for_server`.
- `scripts/lib/common.sh` `begin_benchmark_run` / `die()` append a ledger row on failed runs, and `wait_for_server` defaults to 600 s while treating HTTP 503 as not ready.
- `scripts/templates/setup_rocm_reboot_skeleton.sh` auto-enables SGLang and AMD AITER when `Framework` names SGLang.

### Changed

- Generation must not invent profile sweep numbers. Command columns are generated display; sweep/list flags in those cells are documentary.
- 105 FP32 `8x512x512` `atol` is `1e-3` on baseline and extended in `ProfileValues`.
- 106 extended `runtime` is 8s and `warmup_duration_sec` is 1s (48-job sweep was ~56 min at 60s+10s). Verified 444s / 48 samples. Documented in `docs/TEMPLATE_00_51_WORKLOAD_DELTAS.md`.
- 110 extended `num_iterations` is 40000 (256MB DRAM at 400000 iters ran 19–39 min). Verified 271s / 5 samples. Documented in `docs/TEMPLATE_00_51_WORKLOAD_DELTAS.md`.
- 128/129 `dtype` is `bfloat16` on all profiles. vLLM 0.26 rejects `bf16`. Verified extended: 128 100s / 2 samples (`128_20260815_172659`); 129 64s / 2 samples (`129_20260815_172735`).
- 130/131 setup must install and verify AMD AITER before baseline/extended. 00_50 defaulted `BENCHMARK_INSTALL_AITER=0`. Verified extended: 130 357s / 32 samples (`130_20260815_180118`); 131 165s / 64 samples (`131_20260815_180721`). Ready-wait must be at least 600 s.
- `scripts/sync_matrix_profile_commands.py` defaults to `BenchmarkMatrixDefinitions.xlsx`. Historical `_1_0` / `_1_1` workbooks are not runtime sources.
- `scripts/generate_benchmark_config.py` seeds `sweep.profile` as `baseline` for LLM Serving and `smoke` otherwise.
- Claude Code guidance lives at `.claude/CLAUDE.md`. A root `CLAUDE.md` is not used and fails generation checks.
- 101 uses `rvs --version` or `rvs -g`, not `rvs -l`. 112 uses 30s/60s/120s subtest timeouts plus retry. 117 maps to `--cold_iters` / `-v`. 118 omits `-S` unless a solution id is explicit. 130 keeps five metrics.

## [1.04] - 2026-08-15

### Added

- Forked this generator to sibling `TEMPLATE_00_51`. Generated repositories belong beside this generator, not inside `TEMPLATE_00_50`. TEMPLATE_00_50 remains the frozen source of the 101–132 generation batch.

### Changed

- `/root/runtime_ledger.csv` host/GPU/OS/CPU fields are now contiguous after the exit codes: `hostname`, `gpu_name`, `gpu_vram`, `gpu_count`, `os_version`, `cpu_model`, `workload_name`, then the five metric pairs. TEMPLATE_00_50 had inserted `gpu_count` between `metric_2_def` and `metric_2_result` and `cpu_model` between `metric_2_result` and `metric_3_def`. Existing ledgers with the previous header are rewritten on the next append; values move by column name.
- `gpu_name` parses `rocm-smi --showproductname` Card Series (fallback Card SKU, then `amd-smi` MARKET_NAME) and skips the ROCm SMI banner. TEMPLATE_00_50 stored the banner line `============================ ROCm System Management Interface ============================`.
- `gpu_vram` stores the VRAM total-memory value only (for example `205822885888`), not the reconstructed `GPU[0] VRAM Total Memory (B) ...` line.
- `scripts/self_check_generated_repo.sh` now asserts the 1.04 column order and the banner-safe GPU parsers.

## [1.03] - 2026-08-14

### Added

- Forked this generator to sibling `TEMPLATE_00_50`. Generated repositories belong beside this generator, not inside `TEMPLATE_00_49`.
- Canonical runtime workbook `BenchmarkMatrixDefinitions.xlsx` (no `Updated` / `Plus119` / `ChatGPT` / `Aggregated` runtime aliases).
- `docs/TEMPLATE_00_50_WORKLOAD_DELTAS.md` for the 119 / 130 / 131 generation contracts.
- `scripts/extract_benchmark_definition.py` matches table rows by the Workload Number column so prose that mentions another workload number cannot steal the extract.

- `scripts/templates/run_benchmark_help_skeleton.sh` and a `usage()` contract for `bash run_benchmark.sh --help`. Help prints grouped options with accurate value-taking flags, exits before `scripts/ensure_setup.sh`, and keeps the script-header `Options:` field as a compact inventory. Documented in `AGENTS.md` § 20.4, `docs/run-output-contract.md`, checklist 3.29b, generation workflow, SPEC/README templates, and `scripts/self_check_generated_repo.sh`.
- `bash run_benchmark.sh --matrix-definition` prints this workload's `benchmark_definition.json` field/value table and exits before setup. Implemented by `scripts/print_benchmark_definition.py`. Documented in `AGENTS.md` § 20.4, `docs/run-output-contract.md`, checklist 3.29c, and the help skeleton.
- `bash setup.sh` writes `results/install_commands.txt`: one bare executed install command per line, without timestamps, step numbers, or comments. `results/install_status.txt` remains the commented phase/step log. Documented in `docs/rocm-reboot-install-contract.md`, checklist 3.9c, and the setup skeleton.
- `run_benchmark.sh` no longer writes `system_info.txt`. After each run, `scripts/collect_hw_sw_info.sh "${RUN_DIR}"` writes `hardware_info.txt`, `software_info.txt`, and `errors_info.txt` into the per-run artifact directory.
- End-of-run `journal_warnings.txt` capture via `capture_journal_warnings` in `scripts/lib/common.sh` (`journalctl -p warning`, scoped to the run start/stop window when available, otherwise current boot). Documented in `AGENTS.md`, checklist, generation workflow, run-output contract, and SPEC/README templates.
- Strict sequential multi-workload generation contract: one `create_generated_repo.py --workload <N>` at a time; no next directory until the current workload finishes, fails with user notification, is abandoned by agent judgment, or times out after 60 minutes of calendar time; incremental `batch_generation_manifest.json` updates with statuses `passed`, `failed`, `abandoned`, and `timed_out`.

### Changed

- Workload 119 name is `PyTorch Microkernel Suite` and repo slug is `gpu-bench-amd-torch-micro-suite`. The row describes repository-local GEMM/Conv2D microkernels, not official TorchBench.
- Workload 130 is sequential prompt-response via `scripts/prompt_response_client.py`. RadixAttention cache hit rate is kept as metric #5.
- Workload 131 is concurrent or rate-controlled serving via `sglang.bench_serving` or a pinned equivalent.
- Smoke may use `scripts/tiny_sglang_server.py`; baseline and extended must launch SGLang with Mistral-7B-v0.3.
- Benchmark schema version remains 1.2.0 for every row.
- Trimmed non-sweep Parameter_* names from workloads 112, 121, 125, 126, 130, 131, and 132. Remaining named parameters are the knobs generation must expose as `run_benchmark.sh` flags. Identity (model IDs, SGLang backend, 1-GPU tensor parallel) stays in metadata columns, not Parameter_*.
- `/root/runtime_ledger.csv` column order is now `table_index_number`, `run_id`, `workload_number`, `runtime_root_dir`, `benchmark_profile`, `start_datetime`, `total_runtime_mm_ss`, `exit_code`, `runtime_exit_code`, then host/GPU/OS/workload, metrics, parameters, and notes. `total_runtime` is renamed `total_runtime_mm_ss` and stored as `mm:ss`. Existing ledgers with the previous header are rewritten on the next append. Documented in `scripts/update_runtime_ledger.py`, `docs/repository-template.md`, `docs/run-output-contract.md`, `AGENTS.md`, and checklist 3.40c4.
- Sequential multi-workload timeout is **60 minutes of calendar time** from when work on that workload started, not "60 minutes of wall-clock effort." Idle time, status questions, waiting, and conversation pauses all count. Documented in `docs/AI_AGENT_INSTRUCTIONS.md`, `AGENTS.md`, `docs/generation-workflow.md`, and `docs/SUBMISSION_CHECKLIST.md`.
- Sequential multi-workload generation must not stop for status questions. The agent answers briefly and continues the current unfinished workload in the same turn; the user does not have to say "resume." Documented in `docs/AI_AGENT_INSTRUCTIONS.md` rule 11, `AGENTS.md`, `docs/generation-workflow.md`, `docs/AI_AGENT_HANDOFF.md`, and `docs/SUBMISSION_CHECKLIST.md`.
- Finishing one workload is not permission to end the turn. After recording the current workload, the agent immediately starts the next remaining requested workload in the same turn (rule 12). The user does not have to prompt again between workloads.
- Updated `docs/run-output-contract.md` so the Benchmark Summary prints Artifacts and SQLite DB before the Metrics block, with empty `[INFO]` spacer lines before and after the Metrics lines. Reinforced the same ordering in `AGENTS.md`, `docs/AI_AGENT_INSTRUCTIONS.md`, `docs/generation-workflow.md`, and `docs/SUBMISSION_CHECKLIST.md` so every newly generated workload follows it.
- AI Coding Agent chatbox multi-workload path now forbids `create_generated_batch.py` (legacy scaffold helper only) and requires sequential completion gates per workload before scaffolding the next repository.

### Deprecated

- Agent use of `scripts/create_generated_batch.py` for chatbox multi-workload generation.

## [1.02] - 2026-07-06

### Added

- `scripts/create_generated_repo.py` to create a complete active template copy and bootstrap generated-repo scaffolding deterministically.
- `scripts/create_generated_batch.py` for comma-separated, `and`, `ALL`, and range prompts; creates sibling repositories, refreshes a shared remote VM once only after explicit confirmation, continues after individual failures, and writes `batch_generation_manifest.json`.
- `schemas/batch_generation_report.schema.json` and batch-manifest validation.
- `scripts/self_check_generated_repo.sh` for standalone generated-repo checks.
- CPU/System baseline default contract in `docs/machine-checkable-contracts.md`.
- Reboot continuation guidance and helpers: `docs/reboot-resume-pattern.md`, `scripts/lib/remote_reboot_wait.sh`, `scripts/lib/reboot_resume.sh`.
- Reusable `implementation_components/` overlays and profile-aware generated-repo initialization so workload-specific implementations can be reproduced from template source rather than untracked agent output.

### Changed

- Consolidated supported AI-agent prompt forms into `README.md` and moved the authoritative agent instructions to `docs/AI_AGENT_INSTRUCTIONS.md`.
- `scripts/init_generated_repo.py` now accepts explicit active-template and generated-repository roots for safe reinitialization without recursive copying.
- Extended `scripts/smoke_check_generated_repo.sh` with phase-marker checks.
- Updated `docs/generation-workflow.md` with minimum file matrix and copy exclusions.
- Updated `docs/SUBMISSION_CHECKLIST.md` placeholder grep guidance to reduce false positives from template docs.
- Removed remote execution requirements from generation contracts.
- Switched harness guidance to local-only execution (no SSH prompts/default files).
- Clarified generated `setup.sh` behavior for fresh Ubuntu images: auto-install Python venv prerequisites before creating the external `.venv` environment.
- Documented one isolated VENV per repository by default, with `.venv` available for operators managing multiple repositories on the same machine.
- Clarified that workload-inherent ROCm setup tasks (for example ROCm repo and RVS install) should run by default via `scripts/lib/rocm_install.sh`, with explicit skip flags for advanced use.
- Updated `scripts/lib/rocm_install.sh` to the staged reboot-safe runtime flow and robust ROCm/RVS install behavior used by current generated repositories (including step 1-23 phase/step status hooks).
- Added template guidance that generated reboot-driven setup flows must maintain `results/install_status.txt`, mirror status into `/etc/motd`, include operator guidance lines in MOTD, and emit `wall` completion notification.
- Clarified local-only reboot-resume behavior as the single supported setup path.

### Deprecated

- `docs/remote-execution-pattern.md`, marked as a deprecated historical reference.
