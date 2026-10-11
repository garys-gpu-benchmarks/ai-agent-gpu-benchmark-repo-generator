# ROCm Reboot Install Contract

This document is the required implementation contract for generated workloads whose `setup.sh` installs ROCm components that can reboot the local host.

The goal is that an operator can run:

```bash
bash setup.sh
```

one time on a fresh Ubuntu target and have setup complete without a reboot when the amdgpu driver can be reloaded, or continue automatically after the one fallback reboot when it cannot.

## When This Contract Applies

Apply this contract when `benchmark_specification.json` indicates any of these installation requirements:

- ROCm runtime installation
- ROCm repository installation
- ROCm Validation Suite installation
- Workload tools whose install path calls functions from `scripts/lib/rocm_install.sh`

The generated repository is local-only. Do not implement SSH orchestration, remote prompts, remote metadata collection, or remote `setup.sh` execution paths.

## Canonical Controller

The template file `scripts/templates/setup_rocm_reboot_skeleton.sh` is the single canonical controller for this contract. ROCm workload generation must materialize that file as the generated repository's `setup.sh`; agents must not create a new reboot controller. It detects Ubuntu and pins ROCm `7.2.1` / `noble` on 24.04 or ROCm `7.14` / `resolute` on 26.04, with GPU target `gfx942`. A workload may change dependency variables or explicitly set `BENCHMARK_SKIP_RVS`, but may not change stage ordering, resume handling, locking, status hooks, or cleanup.

The protected installer owns the numbered operations. The controller owns transaction sequencing: it installs the resume service before calling the installer, processes `.rocm_runtime_stage.env` before any installed-ROCm shortcut, exits while a reboot stage remains, and removes the service only after the final setup verification succeeds.

## Protected Installer Library

Generated `setup.sh` must source and call `scripts/lib/rocm_install.sh`. That file is a dispatcher and sources `scripts/lib/rocm_install_24_04.sh` or `scripts/lib/rocm_install_26_04.sh` from the host Ubuntu release.

Do not duplicate, inline, paraphrase, or replace the ROCm install commands in those libraries. For covered ROCm tasks, no ad-hoc `apt-get`, `amdgpu-install`, repository, or ROCm package install commands may exist outside `scripts/lib/rocm_install.sh`, `scripts/lib/rocm_install_24_04.sh`, and `scripts/lib/rocm_install_26_04.sh`.

Required calls:

| Function | Required when |
|---|---|
| `rocm_install_runtime` | ROCm runtime is needed and `/opt/rocm/bin/rocm-smi` is absent. |
| `rocm_add_repository` | ROCm apt repository is needed and `/etc/apt/sources.list.d/rocm.list` is absent. |
| `rocm_install_rvs` | Workload command/framework references `rvs` or `rocm-validation-suite`. |
| `rocm_compile_rocblas_bench` | Workload explicitly requires compiling `rocblas-bench`. |

## Driver Reload Instead Of Reboot

`rocm_install_runtime` no longer reboots unconditionally. After the driver/firmware install it saves stage `stage3`, then calls `amdgpu_reload_instead_of_reboot` from `scripts/lib/amdgpu_reload.sh` (sourced by `scripts/lib/rocm_install.sh`):

| Ubuntu | Mode | What the reload loads | Extra check |
|---|---|---|---|
| 24.04 | `dkms` | AMD's amdgpu-dkms module built for the running kernel, replacing Ubuntu's in-box amdgpu | `modinfo -n amdgpu` is under `/lib/modules/$(uname -r)/updates/`, and the loaded module's srcversion matches it |
| 26.04 | `firmware` | Ubuntu's in-tree amdgpu again, now reading the `amdgpu-dkms-firmware` files | none (amdgpu-dkms does not build on 26.04) |

The reload runs `update-initramfs -u`, `modprobe -r amdgpu`, `modprobe amdgpu`, and `udevadm settle`, then waits until every AMD GPU PCI device (vendor `0x1002`, class `0x03xx`/`0x12xx`) is a KFD compute node. On success the stage file is cleared, the status log records `sudo modprobe -r amdgpu && sudo modprobe amdgpu`, and setup continues in the same invocation. Firmware errors logged during the reload are printed as warnings; they are not a reason to reboot, because a reboot reads the same files.

It returns failure, and the installer reboots exactly as before, when: `ROCM_RELOAD_INSTEAD_OF_REBOOT=0`; no AMD GPU is on the PCI bus; amdgpu is in use (`refcnt` > 0); (24.04) no DKMS build exists for the running kernel; unload or load fails or exceeds `AMDGPU_UNLOAD_TIMEOUT` (180 s) / `AMDGPU_LOAD_TIMEOUT` (600 s); fewer GPUs than PCI devices appear within `AMDGPU_INIT_WAIT` (300 s); or (24.04) the running module is not the DKMS build. A modprobe stuck in the kernel is left running and the reboot clears it.

## Reboot Postponed Until Everything Is Installed

When the reload fails, generated `setup.sh` does not reboot in the middle of setup. It exports `ROCM_DEFER_REBOOT=1` before calling `rocm_install_runtime`; on a failed reload the installer then keeps stage `stage3`, appends `ROCM_REBOOT_BOOT_ID=<boot id>` (from `/proc/sys/kernel/random/boot_id`) to `.rocm_runtime_stage.env`, sets `ROCM_REBOOT_PENDING=1`, and returns 0 instead of rebooting.

| Run | What happens |
|---|---|
| First run (reboot pending) | Status `PHASE amdgpu could not be reloaded in place; installing everything now and rebooting once at the end`. Repository, RVS build, venv and requirements, framework wheels (vLLM, SGLang, AITER, JAX, FAISS), model prefetch, and the rocBLAS clients build (it names `GFX_TARGET`) all run. Checks that need a working GPU are not fatal (`gpu_check` / `gpu_check_failed` warn); PyTorch is checked for a ROCm build only. `scripts/build.sh` does not run: plain `hipcc` builds pick the GPU architecture from the GPU they can see, and there is none yet. Then `PHASE All software installed. Rebooting once ...`, a `wall` message, and one reboot. |
| After the reboot (systemd resume) | `rocm_install_runtime` sees `stage3` in a new boot, logs `STEP 10` (26.04) / `STEP 12` (24.04) `sudo reboot`, and clears the stage. The rest of setup runs as usual; installs are already present, so it mainly runs `scripts/build.sh` and the GPU checks (`torch.zeros(1, device="cuda")`, `jax.devices()`, vLLM/SGLang/AITER imports, RAG `torch.cuda.is_available()`), then `SETUP complete` and service cleanup. |
| Rerun in the same boot (first run stopped on an error) | The boot ID still matches, so the reboot stays pending (`ROCM_REBOOT_PENDING=1`); setup continues installing and reboots at its end. |

`BENCHMARK_GPU_CHECKS_AFTER_REBOOT=1` is exported to helpers during the first run (for example `install_rag_amd.sh` then checks `torch.version.hip` instead of `torch.cuda.is_available()`).

`ROCM_DEFER_REBOOT=0` restores the earlier behavior: reboot right after the driver install, exit, and continue the whole setup after the reboot.

Step 02 runs `apt-get upgrade -y`, not `apt upgrade -y`. `apt-get upgrade` never installs new packages, so a new kernel is kept back and the running kernel stays the one the driver was built or reloaded for. Kernel updates are installed separately when wanted.

Because a reload does not start a new login, generated `setup.sh` calls `grant_gpu_access_this_session` after `rocm_add_repository`: a non-root user who was just added to `render`/`video` gets an ACL on `/dev/kfd` and `/dev/dri/*` for the current boot (setup installs `acl`). If `setfacl` fails, setup warns to log out and back in or run `newgrp render`.

## Required CLI Flags

Generated `setup.sh` must support:

| Flag | Behavior |
|---|---|
| `--assume-yes` | Suppress interactive first-run notice. Used by systemd resume service. |
| `--resume-auto` | Enable automatic systemd resume after reboot. This is the default. |
| `--no-resume-auto` | Disable automatic resume; operator must rerun `bash setup.sh` after reboot. |
| `--resume-from-service` | Internal flag used only by the systemd oneshot service. Implies `--assume-yes`. |
| `--skip-rocm` or more granular skip flags | Advanced override to skip workload-inherent ROCm setup. |
| `--skip-rvs` | Advanced override when RVS is not required or already managed externally. |
| legacy remote flags | Fail fast with a clear local-only error. |

The help text must describe auto-resume behavior and identify `--resume-from-service` as internal.

## First-Run Operator Notice

On an interactive first run, before any reboot-capable ROCm step, `setup.sh` must print a clear notice stating:

- the amdgpu driver is reloaded in place of a reboot, and setup reboots once only if the reload cannot be verified (`ROCM_RELOAD_INSTEAD_OF_REBOOT=0` always reboots),
- systemd auto-resume is enabled by default,
- status is written to `results/install_status.txt`,
- executed install commands are appended to `results/install_commands.txt` as bare command lines,
- status is mirrored into `/etc/motd`,
- completion is announced with `wall` message `setup.sh now complete`,
- pressing Enter starts the reboot-capable installation.

Do not prompt when running with `--assume-yes` or `--resume-from-service`.

## Systemd Auto-Resume Service

Before calling `rocm_install_runtime`, generated `setup.sh` must install and enable a local systemd oneshot service.

Recommended naming:

```text
<repo-name>-setup-resume.service
```

Recommended service shape:

```ini
[Unit]
Description=Resume <repo-name> setup.sh after reboot
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
# ROCm/PyTorch installation can exceed systemd's default startup timeout.
TimeoutStartSec=0
TimeoutStopSec=0
KillMode=process
WorkingDirectory=/opt/benchmarks/<repo-name>
ExecStart=/bin/bash /opt/benchmarks/<repo-name>/setup.sh --assume-yes --resume-auto --resume-from-service
StandardOutput=append:/opt/benchmarks/<repo-name>/results/reboot_resume.log
StandardError=append:/opt/benchmarks/<repo-name>/results/reboot_resume.log

[Install]
WantedBy=multi-user.target
```

Implementation requirements:

1. Write the unit to `/etc/systemd/system/<repo-name>-setup-resume.service`.
2. Run `systemctl daemon-reload`.
3. Run `systemctl enable <repo-name>-setup-resume.service`.
4. Continue setup normally until `rocm_install_runtime` triggers reboot.
5. After boot, systemd reruns setup with `--resume-from-service`.
6. Leave the service installed through all expected reboot stages.
7. Remove and disable the service only after full setup success.

If `systemctl` is unavailable, log a warning and continue in manual-resume mode.

## Resume State

The ROCm installer library persists its own runtime stage in:

```text
.rocm_runtime_stage.env
```

Generated `setup.sh` must not delete this file until setup is fully complete.

Generated `setup.sh` may also write a separate resume log:

```text
results/reboot_resume.log
```

The resume log should include:

- service installation,
- service invocation,
- detected runtime stage,
- service cleanup,
- completion status.

## Install Status And MOTD

Generated `setup.sh` must provide these hook functions before sourcing or calling ROCm install functions:

```bash
install_status_log_phase() { ...; }
install_status_log_step() { ...; }
```

These hooks are consumed by `scripts/lib/rocm_install.sh`.

Status requirements:

- append chronological phase and completed-step entries to `results/install_status.txt`,
- append each executed install command to `results/install_commands.txt` as a bare command line (no timestamp, step number, or trailing comment),
- format each status timestamp as `YYYY-MM-DD HH:MM:SS` followed by two spaces before `PHASE`, `STEP`, or `SETUP`,
- preserve the status log across systemd resume invocations,
- mirror the complete accumulated contents of `results/install_status.txt` into `/etc/motd` after every phase and step, so a fresh login shows all completed steps rather than only the latest event,
- if `.rocm_runtime_stage.env` exists, call `rocm_install_runtime` before any "ROCm already present" shortcut so the protected installer library can log its numbered resume step (for example, step 12 after the post-driver reboot),
- log generated-wrapper status messages such as "ROCm runtime already present" or "ROCm apt repository already present" as `PHASE` entries, not as unnumbered `STEP rocm-runtime` / `STEP rocm-repo` entries,
- include the exact MOTD guidance lines:

```text
To see latest status on install, execute the following:
cat /opt/benchmarks/<repo-name>/results/install_status.txt
```

with a blank line before and after the two guidance lines.

After successful completion, perform one final MOTD sync so the complete step history and `SETUP complete` marker are visible on the next login. The MOTD/status should indicate completion and the script must emit:

```bash
echo "setup.sh now complete" | wall
```

when `wall` is available.

## Completion Cleanup

Only after all required setup steps complete successfully:

1. Disable the resume service.
2. Remove `/etc/systemd/system/<repo-name>-setup-resume.service`.
3. Run `systemctl daemon-reload`.
4. Remove `.rocm_runtime_stage.env`.
5. Preserve `results/install_status.txt` and `results/install_commands.txt`.
6. Leave a completion marker in the status log or MOTD.

It is correct for `systemctl status <repo-name>-setup-resume.service` to report `Unit ... could not be found` after successful cleanup.

## Verification Commands

After setup completes on a fresh VM, these commands should succeed or have the noted expected result:

```bash
cat results/install_status.txt
cat results/install_commands.txt
test ! -f /etc/systemd/system/<repo-name>-setup-resume.service
source ~/.bashrc
which rvs
rvs --version
bash run_benchmark.sh --profile smoke --validate
```

Expected setup markers:

- auto-resume service enabled before `rocm_install_runtime`,
- `STEP 10` (26.04) or `STEP 12` (24.04) shows either `sudo modprobe -r amdgpu && sudo modprobe amdgpu` (no reboot) or `sudo reboot` (fallback),
- after a fallback, every install step is logged before the reboot; only `scripts/build.sh`, GPU checks and `SETUP complete` are logged after it,
- after a fallback reboot, setup starts again automatically,
- ROCm runtime steps complete,
- RVS install steps complete when required,
- setup complete,
- auto-resume service removed.

Expected benchmark markers:

- RVS executes rather than falling back because `/opt/rocm/bin` is on `PATH`,
- raw RVS output is saved under `results/raw/<run-id>/rvs_output.txt`,
- parser writes `results/benchmark.db`,
- validation reports `PASS`.

## Common Failure Modes

| Symptom | Likely cause | Required fix |
|---|---|---|
| User must rerun `bash setup.sh` after reboot | systemd resume service was not installed/enabled before `rocm_install_runtime`. | Install the oneshot service before reboot-capable steps. |
| Status log starts over after reboot | setup truncates `results/install_status.txt` or `results/install_commands.txt` on resume. | Preserve both files when `.rocm_runtime_stage.env` or `--resume-from-service` is present. |
| Setup loops after completion | resume service was not removed after success. | Disable/remove the service only after full success. |
| `rvs` missing in noninteractive shell | `/opt/rocm/bin` not on `PATH`. | Export `/opt/rocm/bin:$PATH` in scripts that invoke ROCm tools. |
| Parser fails on real RVS output | RVS output contains ANSI color codes or summary table format. | Strip ANSI codes and parse the RVS summary table. |
