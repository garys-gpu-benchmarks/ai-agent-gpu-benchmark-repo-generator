# Copilot instructions

Use `benchmark_specification.json` as the authoritative workload contract.

- Keep changes workload-scoped.
- Do not change benchmark semantics, metrics, parameters, or success criteria without an explicit contract change.
- Preserve reproducibility and result validation.
- Never commit credentials, private endpoints, runtime archives, model weights, or sensitive system inventory.
- Run `bash scripts/check_github_publish_ready.sh` and `bash -n run_setup.sh run_benchmark.sh` before considering a change complete.
