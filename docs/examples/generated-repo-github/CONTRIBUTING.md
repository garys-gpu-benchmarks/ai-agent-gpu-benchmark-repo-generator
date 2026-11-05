# Contributing

Thank you for improving this GPU benchmark workload repository.

## Before opening a pull request

1. Read `benchmark_specification.json`; it is the authoritative workload contract.
2. Keep changes workload-scoped and do not silently change benchmark semantics, metrics, parameters, or success criteria.
3. Never commit credentials, tokens, private keys, real SSH endpoints, downloaded model weights, or runtime result archives.
4. Run the publication-readiness and host-safe syntax checks:

```bash
bash scripts/check_github_publish_ready.sh
bash -n setup.sh run_benchmark.sh
```

5. When a compatible GPU system is available, validate setup and the smoke profile:

```bash
bash setup.sh
bash run_benchmark.sh --smoke
```

## Benchmark contract changes

Changes to `benchmark_specification.json` should originate from the benchmark-definition source used to generate this repository. If benchmark intent changes, regenerate or deliberately version the workload rather than silently editing the generated contract.

## Pull requests

Describe the benchmark behavior affected, hardware/software used for validation, commands executed, and any expected result changes. Do not attach private runtime inventories or secrets.
