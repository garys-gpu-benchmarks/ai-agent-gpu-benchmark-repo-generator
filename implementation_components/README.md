# Implementation Components

Reusable, capability-oriented implementation assets selected from `config/implementation_packs.yaml` by **Workload Number** and **GPU Vendor** (directory names such as `linpack-rochpl-amd`). The workbook has no Implementation Pack column. Users do not select components in `BenchmarkSpecDefinitions.xlsx`.

Each primary `component.json` is a file manifest: `overlay`, optional `entry_point`, and `gate.json`. Selectors may remain as documentation. Mixins still apply via `apply_when`.

A workload may resolve to zero, one, or multiple compatible components, plus mixins. Zero primary matches means the AI Coding Agent must implement `scripts/collect_workload.py` from the spec; the template will not invent a generic collector. Multiple matches are allowed only when overlay destinations do not conflict.

Mixin components (`role: mixin`) use `apply_when` and skip destinations a primary already owns:

- `harness-self-check` — no-op RAG stubs
- `rocm-tool-verify-build` — verify-only `scripts/build.sh` when `build_policy=verify_tools`
- `rocblas-clients-build` — protected `rocm_compile_rocblas_bench` when `compile_rocblas_bench=true`

After copy, `results/overlay_lock.json` records path → component_id → sha256 of the copied bytes. That digest is a fingerprint. A smoke failure inside a locked file is repaired by writing the same bytes in the template source, the sibling, and that `sha256`, then rechecking with `create_one_workload.py --validate-only`. Read `results/component_leftover_work.md` for the file list and for what the agent may still edit freely.

The benchmark specification remains authoritative for workload identity, parameters, metrics, runtime requirements, software/framework requirements, and success criteria. Components contribute deterministic implementation assets only.

Example manifest selector:

```json
{
  "component_id": "sdxl-diffusers-amd",
  "selectors": [
    {"field": "Workload Name", "operator": "equals", "value": "Stable Diffusion XL Inference Baseline"},
    {"field": "GPU Vendor", "operator": "equals", "value": "AMD"}
  ],
  "overlay": ["run_benchmark.sh", "run.py"]
}
```

For Workload 124 the yaml maps slot 24 / AMD to `sdxl-diffusers-amd`. Init copies that folder. The harness calls `scripts/collect_workload.py` only when `run_benchmark.sh` names that file. An overlay runner that launches the workload itself stays in place.

## Overlay copy and immutability

`scripts/init_generated_repo.py` copies each listed overlay from
`implementation_components/<component-id>/files/<path>` onto
`<generated-repo>/<path>`. The lock is a fingerprint of that copy, not a ban on
a later repair. Do **not** throw the overlay away and write a new collector or
parser. A defect that makes smoke exit 1 is fixed by writing the same bytes in
`implementation_components/<component-id>/files/<path>`, the sibling path, and
the path's `sha256` in `results/overlay_lock.json`, then
`create_one_workload.py --validate-only`. Do not run `create_generated_repo.py`
again on a non-empty sibling. `scripts/metric_contract.py` is copied from the
generator `scripts/` tree and has no lock entry: repair both copies, then use
the same recheck. The overlay remains the known-good implementation (STREAM
checksum, leftover-`benchmark.db` parse, vLLM/SGLang smoke-vs-real launch,
AMD vLLM tokenizer slack including KV-cache, AMD SGLang import guards,
multichase `void * volatile` chase,
hipcc host-GCC `build.sh`, SDXL Diffusers path, NVIDIA `ninja` /
`LD_LIBRARY_PATH` helpers, the Ubuntu 26.04 SGLang cu130 helpers,
NVIDIA/AMD RAG runners, cuDNN timeout, AMD rocHPL 64-bit host allocations
and large-N repeat cap).

`scripts/smoke_check_generated_repo.sh` byte-compares generated overlay
destinations to the component files. `scripts/self_check_generated_repo.sh`
also asserts STREAM per-element relative checksum tokens and leftover-DB
`ADD COLUMN` / rebuild tokens.

`init_generated_repo.py` may replace overlay `setup.sh` with the canonical
ROCm setup skeleton when `GPU Vendor` is AMD. When that happens, `setup.sh`
must still call the component install helpers after the venv exists
(`scripts/install_sglang_nvidia.sh` is NVIDIA-only; AMD uses
`scripts/install_rag_amd.sh` and the matching AMD helpers).

When `GPU Vendor` is NVIDIA, init copies `scripts/templates/setup_nvidia_skeleton.sh`
as `setup.sh` **before** overlays and does **not** recopy it afterward. NVIDIA
vLLM/SGLang overlay `setup.sh` therefore wins. The NVIDIA skeleton calls
`scripts/install_pytorch_nvidia.sh`, then `install_sglang_nvidia.sh` /
`install_rag_nvidia.sh` / `install_sdxl_python.sh` when those files exist,
then `scripts/build.sh`. Do not call `install_pytorch_nvidia.sh` from the
ROCm skeleton.

When `GPU Vendor` is NVIDIA, the 12 previously unmatched host/CUDA names
(`system-config-nvidia`, `gpu-health-nvidia`, `system-stress-nvidia`,
`sdc-ecc-nvidia`, `fio-nvme-nvidia`, `iperf3-nvidia`, `linux-perf-pmu-nvidia`,
`lmbench-nvidia`, `gups-nvidia`, `cuda-memcpy-nvidia`, `nccl-bandwidth-nvidia`,
`linpack-hpl-nvidia`) own `scripts/collect_workload.py` (and the matching
`src/` + `scripts/build.sh` where a binary is required). Those overlays fail
closed: no invented TFLOPS, no D2D-as-NCCL, no host RAM labeled as HBM.

When `GPU Vendor` is AMD, matching `*-amd` collectors own `scripts/collect_workload.py`
(and 105/119 helpers). After overlays, `scripts/materialize_generated_harness.py`
fills empty `parse_results.py`, `validate_results.py`, and `run_benchmark.sh` only.
`scripts/apply_component_gaps.py` then writes `--seed-fixture`, `requirements.txt` PyYAML, and `gate.json` thresholds.
Do not add a generic `collect_workload.py` to template `scripts/`.
`smoke_check_generated_repo.sh` applies GEMM per-point tokens only when `contracts.gemm_per_point` is true.
