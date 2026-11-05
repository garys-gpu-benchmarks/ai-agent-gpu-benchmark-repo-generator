# Pull Request

## Description

<!-- Describe the workload change and why it is needed. -->

## Validation

- [ ] `bash scripts/check_github_publish_ready.sh` passes
- [ ] `bash -n setup.sh run_benchmark.sh` passes
- [ ] Setup/build changes were tested on an appropriate GPU host when required
- [ ] Smoke benchmark changes were validated with `bash run_benchmark.sh --smoke` when hardware was available

## Contract and safety

- [ ] Benchmark semantics remain consistent with `benchmark_specification.json`, or the contract change is explicitly explained
- [ ] No credentials, tokens, private endpoints, model weights, runtime archives, or sensitive inventory are committed
- [ ] Generated outputs and documentation were updated when behavior changed

## Related issues

<!-- Fixes #123 -->
