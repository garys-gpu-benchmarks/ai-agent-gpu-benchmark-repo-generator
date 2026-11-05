#!/usr/bin/env bash
# File: scripts/templates/run_benchmark_help_skeleton.sh
# Version: 1.0.0
# Maintainer: AI Agent GPU Benchmark Repo Generator
# Date: 2026-08-14
# Description: Copy-this usage() and early --help handler for generated run_benchmark.sh.
# Execution: Not a standalone entrypoint; copy usage() and the --help loop into run_benchmark.sh.
# Options: --help, --specification
# Requirements: bash
# Environment: Local generated repository.
# Dependencies: None
# Variables: None
# Repository: gpu-bench/sys-bench template
# License: Apache-2.0
#
# Copy usage() and the early --help loop into generated run_benchmark.sh.
# Do not source this file unchanged.
# Replace the description line with this workload's header Description field.
# Use default CLI profile smoke.
# Immediately after sourcing common.sh, call
# capture_benchmark_run_command_submitted "$@" so the ledger records argv as
# entered. After argument parsing, call begin_benchmark_run "${profile}" so
# die() writes a ledger row on failure, including a failed ensure_setup.sh.
# After ensure_setup.sh returns, call mark_benchmark_measure_start so
# total_runtime_mm_ss starts at the benchmark. After yaml defaults are applied, call
# set_benchmark_run_command with the fully resolved
# `bash run_benchmark.sh ...` string (submitted flags plus yaml-filled
# parameters that were not on the command line). After RUN_DIR is created,
# call set_benchmark_run_dir "${RUN_DIR}" so the failure row records
# raw_run_dir.
# LLM Serving runners must call wait_for_server
# (default 600 s; HTTP 503 is not ready). Do not hardcode a 180 s wait.
# Keep the script-header Options: field as a compact comma-separated inventory.
# Document -h only if the parser accepts it.
# Include Parameters only for flags this runner actually parses.
# materialize_generated_harness.py fills that section from Parameter_01..Parameter_20:
# flag, short description, and the smoke, baseline, and extended values.
# A value shared by all three profiles is printed once. Profile notes are omitted.
# The fourth example is one --baseline override of a single parameter.
# Omit that line when the workload has no parameters.
# If the runner parses an expected-environment flag, list it under General options.

usage() {
  cat <<'USAGE'
Usage: bash run_benchmark.sh [OPTIONS]

Run the configured benchmark and persist validated results.

Profiles (default: --smoke):
  --smoke                       Run smoke profile
  --baseline                    Run baseline profile
  --extended                    Run extended profile

Parameters (override the profile's value):
  --<flag> <n>                  Short description (smoke <v>, baseline <v>, extended <v>)

General options:
  --config <file>               Config file (default: config/benchmark_config.yaml)
  --quiet                       Suppress nonessential stdout
  --log-level <level>           ERROR|WARN|INFO|DEBUG (default: INFO)
  --specification               Print this workload's specification and exit
  --help                        Show this help and exit

Examples:
  bash run_benchmark.sh --smoke
  bash run_benchmark.sh --baseline
  bash run_benchmark.sh --extended
  bash run_benchmark.sh --baseline --num-threads 8
USAGE
}

for _help_arg in "$@"; do
  case "${_help_arg}" in
    --help)
      usage
      exit 0
      ;;
    --specification)
      python3 scripts/print_benchmark_definition.py
      exit 0
      ;;
  esac
done
