# Pull Request

## Description

<!-- Describe the changes in this PR -->

## Type of Change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to change)
- [ ] Documentation update

## Testing

- [ ] I have run `bash run_setup.sh` locally
- [ ] I have run `bash run_benchmark.sh` locally and verified results
- [ ] I have set `.venv` and run `.venv/bin/python scripts/validate_results.py`; all checks passed
- [ ] I have verified my changes do not introduce new `TODO`, `pass`, or `raise NotImplementedError`

## Checklist

- [ ] My code follows the Bash and Python style conventions in `AGENTS.md`
- [ ] I have updated `SPEC.md` and `README.md` if behavior changed
- [ ] I have not modified `benchmark_specification.json`, `README.md`, `docs/AI_AGENT_INSTRUCTIONS.md`, or `*_TEMPLATE.md` files
- [ ] No new secrets, API keys, or credentials are committed
- [ ] All files have proper header blocks with `File`, `Version`, `Author`, `Date`, etc.
- [ ] Sweep parameters are in `config/benchmark_config.yaml`, not hardcoded
- [ ] Baselines or thresholds are in `config/benchmark_config.yaml`, not hardcoded in validation scripts

## Related Issues

<!-- Link to related issues: Fixes #123 -->

## Notes

<!-- Any additional context -->
