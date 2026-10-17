# rocm-tool-verify-build

Mixin applied when a primary component sets `contracts.build_policy=verify_tools` and does not already overlay `scripts/build.sh`.

## Provides

- verify-only `scripts/build.sh` for `rocminfo`, `amd-smi`, `hipcc` (`rocm-smi` optional on ROCm 10.1)

Used by 101 / 102 style inventory workloads.
