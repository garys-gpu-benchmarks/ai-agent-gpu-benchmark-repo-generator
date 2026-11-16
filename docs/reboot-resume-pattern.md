# Reboot + Resume Pattern (Reference)

This template supports two reboot continuation patterns:

1. **Remote reboot + reconnect polling** (operator runs script locally; target is remote via SSH).
2. **On-system reboot + continue after login** (script runs on target host; user logs back in and resumes). For generated setup flows, this may use an enabled systemd oneshot resume unit so execution resumes automatically after boot.

For ROCm runtime/repository/RVS setup flows, `docs/rocm-reboot-install-contract.md` is authoritative and must be followed by generated `run_setup.sh` implementations.

Reference implementation source:

- `setup_rocm_full_28_20260628.sh`
- `wait_for_reboot()` pattern for remote SSH down/up polling.
- phased resume structure (`--phaseN`) for deterministic continuation.

## A) Remote reboot + reconnect polling

Use when issuing `sudo reboot` over SSH.

Pattern:

1. Send reboot command remotely.
2. Poll until SSH **fails** (host down).
3. Poll until SSH **succeeds** (host back up).
4. Add a short settle delay before next step.
5. Continue with next phase automatically.

Use helper library:

- `scripts/lib/remote_reboot_wait.sh`

## B) On-system reboot + continue after login

Use when script is running directly on target host and must reboot locally.

Pattern:

1. Persist resume state to a file (phase/step + timestamp + script path).
2. Issue reboot and exit.
3. Script resumes after reboot (for example via enabled systemd oneshot service) or, if auto-resume is disabled, prompts on next invocation.
4. Script detects resume file and continues from saved phase/step.
5. Clear resume state and service artifacts only after all required setup steps complete successfully.
6. Keep `results/install_status.txt` updated with completed phase/step entries, append bare executed commands to `results/install_commands.txt`, and mirror that status into `/etc/motd`.

Use helper library:

- `scripts/lib/reboot_resume.sh`

## Minimal pseudocode

```bash
# local/on-system script
source scripts/lib/reboot_resume.sh

resume_detect_and_prompt

if [[ "$CURRENT_PHASE" == "phase1" && "$CURRENT_STEP" -eq 2 ]]; then
  save_resume_state "phase1" "3" "$0"
  request_reboot_and_exit "Kernel updates applied; reboot required."
fi
```

## Guardrails

- Auto-resume after reboot is allowed when setup defaults explicitly enable it and the behavior is communicated before reboot.
- Record reboot request/reconnect events in `run.log`.
- Keep resume state idempotent and safe to clear.
