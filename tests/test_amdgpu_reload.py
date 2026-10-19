#!/usr/bin/env python3
# File: tests/test_amdgpu_reload.py
# Description: Stubbed tests for scripts/lib/amdgpu_reload.sh and the reload-or-reboot
#              branch of rocm_install_runtime (24.04 and 26.04). No real modprobe,
#              sysfs, or reboot is touched: commands are shell stubs on PATH and
#              sysfs is a temporary directory tree.
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "scripts" / "lib"
BASH = shutil.which("bash")

# Fake modprobe: unload removes /sys/module/amdgpu; load creates it plus one KFD GPU
# node per PCI GPU (or FAKE_KFD_NODES nodes). FAKE_UNLOAD=fail|hang, FAKE_LOAD=fail.
MODPROBE = r'''#!/usr/bin/env bash
echo "modprobe $*" >> "${FAKE_LOG}"
if [[ "$1" == "-r" ]]; then
  case "${FAKE_UNLOAD:-ok}" in
    fail) exit 1 ;;
    hang) sleep 8; exit 0 ;;
  esac
  rm -rf "${FAKE_SYS}/module/amdgpu" "${FAKE_SYS}/class/kfd/kfd/topology/nodes"
  exit 0
fi
[[ "${FAKE_LOAD:-ok}" == fail ]] && exit 1
mkdir -p "${FAKE_SYS}/module/amdgpu"
echo 0 > "${FAKE_SYS}/module/amdgpu/refcnt"
echo "${FAKE_LOADED_SRC:-AAA}" > "${FAKE_SYS}/module/amdgpu/srcversion"
mkdir -p "${FAKE_SYS}/class/kfd/kfd/topology/nodes/0"
echo "simd_count 0" > "${FAKE_SYS}/class/kfd/kfd/topology/nodes/0/properties"
for ((i = 1; i <= ${FAKE_KFD_NODES:-2}; i++)); do
  mkdir -p "${FAKE_SYS}/class/kfd/kfd/topology/nodes/${i}"
  printf 'cpu_cores_count 0\nsimd_count 1216\n' > "${FAKE_SYS}/class/kfd/kfd/topology/nodes/${i}/properties"
done
'''

MODINFO = r'''#!/usr/bin/env bash
if [[ "$1" == "-n" ]]; then echo "${FAKE_MODPATH:-/lib/modules/6.8.0-1-generic/updates/dkms/amdgpu.ko.zst}"; exit 0; fi
if [[ "$1" == "-F" && "$2" == "srcversion" ]]; then echo "${FAKE_DISK_SRC:-AAA}"; exit 0; fi
exit 0
'''

LOGGING_STUB = r'''#!/usr/bin/env bash
echo "$(basename "$0") $*" >> "${FAKE_LOG}"
'''


def _pci(sys_root: Path, count: int) -> None:
    for i in range(count):
        dev = sys_root / "bus" / "pci" / "devices" / f"0000:{i + 0x10:02x}:00.0"
        dev.mkdir(parents=True)
        (dev / "vendor").write_text("0x1002\n")
        (dev / "class").write_text("0x120000\n")
    audio = sys_root / "bus" / "pci" / "devices" / "0000:99:00.1"
    audio.mkdir(parents=True)
    (audio / "vendor").write_text("0x1002\n")
    (audio / "class").write_text("0x040300\n")


@unittest.skipIf(BASH is None or os.name == "nt", "needs Linux bash")
class AmdgpuReloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.sys = self.tmp / "sys"
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.log = self.tmp / "calls.log"
        self.log.write_text("")
        for name, body in {
            "modprobe": MODPROBE,
            "modinfo": MODINFO,
            "update-initramfs": LOGGING_STUB,
            "udevadm": LOGGING_STUB,
            "journalctl": "#!/usr/bin/env bash\nexit 0\n",
        }.items():
            path = self.bin / name
            path.write_text(body)
            path.chmod(0o755)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _loaded(self, refcnt: int = 0) -> None:
        mod = self.sys / "module" / "amdgpu"
        mod.mkdir(parents=True)
        (mod / "refcnt").write_text(f"{refcnt}\n")

    def _run(self, script: str, **env) -> subprocess.CompletedProcess:
        full_env = {
            **os.environ,
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "FAKE_SYS": str(self.sys),
            "FAKE_LOG": str(self.log),
            "_AMDGPU_RELOAD_SYS": str(self.sys),
            "AMDGPU_INIT_WAIT": "0",
            **env,
        }
        prelude = textwrap.dedent(f'''
            set -euo pipefail
            run_noninteractive_root() {{ while [[ "${{1:-}}" == *=* ]]; do shift; done; "$@"; }}
            source "{LIB / "amdgpu_reload.sh"}"
        ''')
        return subprocess.run([BASH, "-c", prelude + script], env=full_env,
                              capture_output=True, text=True, timeout=60)

    def _reload(self, mode: str, **env) -> int:
        result = self._run(f'if amdgpu_reload_instead_of_reboot {mode}; then echo RC=0; else echo RC=1; fi', **env)
        self.assertIn("RC=", result.stdout, result.stderr)
        return 0 if "RC=0" in result.stdout else 1

    def calls(self) -> str:
        return self.log.read_text()

    # ---- success paths -------------------------------------------------
    def test_firmware_reload_succeeds_when_all_gpus_return(self):
        _pci(self.sys, 2)
        self._loaded()
        self.assertEqual(self._reload("firmware"), 0)
        self.assertIn("modprobe -r amdgpu", self.calls())
        self.assertIn("modprobe amdgpu", self.calls())
        self.assertIn("update-initramfs -u", self.calls())

    def test_module_not_loaded_is_just_loaded(self):
        _pci(self.sys, 2)
        self.assertEqual(self._reload("firmware"), 0)
        self.assertNotIn("modprobe -r", self.calls())

    def test_dkms_reload_succeeds_when_dkms_module_is_running(self):
        _pci(self.sys, 2)
        self._loaded()
        self.assertEqual(self._reload("dkms"), 0)

    def test_partitioned_gpu_more_kfd_nodes_than_pci_is_ok(self):
        _pci(self.sys, 2)
        self._loaded()
        self.assertEqual(self._reload("firmware", FAKE_KFD_NODES="8"), 0)

    # ---- fall back to reboot -------------------------------------------
    def test_disabled_by_env(self):
        _pci(self.sys, 2)
        self._loaded()
        self.assertEqual(self._reload("firmware", ROCM_RELOAD_INSTEAD_OF_REBOOT="0"), 1)
        self.assertEqual(self.calls(), "")

    def test_no_amd_gpu_on_pci(self):
        _pci(self.sys, 0)
        self.assertEqual(self._reload("firmware"), 1)
        self.assertNotIn("modprobe", self.calls())

    def test_module_in_use(self):
        _pci(self.sys, 2)
        self._loaded(refcnt=3)
        self.assertEqual(self._reload("firmware"), 1)
        self.assertNotIn("modprobe", self.calls())

    def test_unload_fails(self):
        _pci(self.sys, 2)
        self._loaded()
        self.assertEqual(self._reload("firmware", FAKE_UNLOAD="fail"), 1)
        self.assertNotIn("modprobe amdgpu", self.calls())

    def test_unload_hangs_gives_up_at_deadline(self):
        _pci(self.sys, 2)
        self._loaded()
        self.assertEqual(self._reload("firmware", FAKE_UNLOAD="hang", AMDGPU_UNLOAD_TIMEOUT="2"), 1)

    def test_load_fails(self):
        _pci(self.sys, 2)
        self._loaded()
        self.assertEqual(self._reload("firmware", FAKE_LOAD="fail"), 1)

    def test_missing_gpu_after_reload(self):
        _pci(self.sys, 8)
        self._loaded()
        self.assertEqual(self._reload("firmware", FAKE_KFD_NODES="7"), 1)

    def test_dkms_not_built_skips_unload(self):
        _pci(self.sys, 2)
        self._loaded()
        self.assertEqual(self._reload("dkms", FAKE_MODPATH="/lib/modules/6.8.0-1-generic/kernel/drivers/gpu/drm/amd/amdgpu/amdgpu.ko.zst"), 1)
        self.assertNotIn("modprobe", self.calls())

    def test_dkms_loaded_module_is_not_the_dkms_build(self):
        _pci(self.sys, 2)
        self._loaded()
        self.assertEqual(self._reload("dkms", FAKE_LOADED_SRC="INBOX", FAKE_DISK_SRC="DKMS"), 1)


@unittest.skipIf(BASH is None or os.name == "nt", "needs Linux bash")
class RuntimeInstallBranchTests(unittest.TestCase):
    """rocm_install_runtime: reload success returns with no reboot; failure reboots at stage3."""

    def _run(self, lib: str, reload_rc: int) -> tuple[str, str]:
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp) / "stage.env"
            script = textwrap.dedent(f'''
                set -euo pipefail
                cd "{tmp}"
                export ROCM_RUNTIME_STAGE_FILE="{stage}" REPO_ROOT="{tmp}"
                run_noninteractive_root() {{ while [[ "${{1:-}}" == *=* ]]; do shift; done; echo "ROOT $*" >> calls; }}
                wget() {{ touch "${{2}}"; }}
                apt-cache() {{ return 0; }}
                source <(tr -d '\\r' < "{LIB / lib}")
                amdgpu_reload_instead_of_reboot() {{ echo "RELOAD $1" >> calls; return {reload_rc}; }}
                rocm_install_runtime
                echo "STAGE=$( [[ -f "{stage}" ]] && cat "{stage}" | head -1 || echo none)"
                cat calls
            ''')
            result = subprocess.run([BASH, "-c", script], capture_output=True, text=True, timeout=60)
            return result.stdout, result.stderr

    def _check(self, lib: str, mode: str):
        out, err = self._run(lib, 0)
        self.assertIn(f"RELOAD {mode}", out, err)
        self.assertIn("STAGE=none", out)
        self.assertNotIn("ROOT reboot", out)
        self.assertIn("ROOT apt-get upgrade -y", out)
        self.assertNotIn("ROOT apt upgrade", out)

        out, err = self._run(lib, 1)
        self.assertIn(f"RELOAD {mode}", out, err)
        self.assertIn("STAGE=ROCM_RUNTIME_STAGE=stage3", out)
        self.assertIn("ROOT reboot", out)

    def test_24_04(self):
        self._check("rocm_install_24_04.sh", "dkms")

    def test_26_04(self):
        self._check("rocm_install_26_04.sh", "dkms")


class RunningKernelGuardTests(unittest.TestCase):
    """Kernel-guard contract for both Ubuntu installers. Holds and module dirs are faked."""

    HOLD_NAMES = (
        "linux-image-generic",
        "linux-image-virtual",
        "linux-headers-generic",
        "linux-headers-virtual",
        "linux-generic",
        "linux-virtual",
        "linux-tools-generic",
        "linux-generic-hwe-24.04",
        "linux-image-generic-hwe-24.04",
        "linux-headers-generic-hwe-24.04",
        "linux-virtual-hwe-24.04",
        "linux-image-virtual-hwe-24.04",
        "linux-headers-virtual-hwe-24.04",
        "linux-generic-hwe-26.04",
        "linux-image-generic-hwe-26.04",
        "linux-headers-generic-hwe-26.04",
        "linux-virtual-hwe-26.04",
        "linux-image-virtual-hwe-26.04",
        "linux-headers-virtual-hwe-26.04",
    )

    def test_helper_holds_known_names_and_stops_on_any_audit(self):
        text = (LIB / "keep_running_kernel.sh").read_text(encoding="utf-8")
        for name in self.HOLD_NAMES:
            self.assertIn(name, text)
        self.assertIn("if ! apt-cache show", text)
        self.assertIn("apt-mark hold", text)
        self.assertIn("dpkg --audit", text)
        self.assertIn("refuse_foreign_installed_kernel", text)
        self.assertNotIn("Pin-Priority", text)
        self.assertNotIn("apt-get remove", text)
        self.assertNotIn("apt-get purge", text)

    def test_both_installers_follow_every_kernel_rule(self):
        for name in ("rocm_install_24_04.sh", "rocm_install_26_04.sh"):
            raw = (LIB / name).read_bytes()
            # Both installers are sourced by bash on Ubuntu, so LF only
            # (.gitattributes: *.sh eol=lf). A CRLF copy fails with
            # "$'\\r': command not found" and the generated repo's CRLF scan.
            self.assertNotIn(b"\r", raw, f"{name} has CR (Windows) line endings")
            text = raw.decode("utf-8").replace("\r\n", "\n")
            executable = "\n".join(
                line for line in text.splitlines() if not line.lstrip().startswith("#")
            )
            self.assertIn("source \"${_rocm_kernel_guard}\"", executable, name)
            call_at = executable.find("\n            keep_running_kernel\n")
            upgrade_at = executable.find("apt-get upgrade -y")
            self.assertGreaterEqual(call_at, 0, name)
            self.assertLess(call_at, upgrade_at, name)
            self.assertLess(call_at, executable.find("apt update"), name)
            self.assertNotIn("sort -V", executable, name)
            self.assertNotIn("linux-modules-extra-${newest}", text, name)
        text24 = (LIB / "rocm_install_24_04.sh").read_text(encoding="utf-8")
        executable24 = "\n".join(
            line for line in text24.splitlines() if not line.lstrip().startswith("#")
        )
        self.assertIn('linux-modules-extra-${running}', executable24)
        self.assertNotIn("linux-modules-extra-${newest}", text24)
        text26 = (LIB / "rocm_install_26_04.sh").read_bytes().decode("utf-8").replace("\r\n", "\n")
        executable26 = "\n".join(
            line for line in text26.splitlines() if not line.lstrip().startswith("#")
        )
        self.assertNotIn("apt-get install -y linux-modules-extra", executable26)
        self.assertNotIn("apt install -y linux-modules-extra", executable26)
        # No newest-kernel branch on 26.04: nothing looks for a newer kernel
        # under /lib/modules or installs modules for one.
        self.assertNotIn("${newest}", executable26)
        self.assertNotIn("/lib/modules/", executable26)
        self.assertNotIn("_rocm_install_linux_modules_extra", executable26)

    def test_unknown_hold_names_are_skipped_and_foreign_module_fails(self):
        if BASH is None:
            self.skipTest("needs bash")
        helper = (LIB / "keep_running_kernel.sh").as_posix()
        script = textwrap.dedent(r'''
            set -euo pipefail
            running=$1
            extra=$2
            known=$3
            moddir=$(mktemp -d)
            mkdir -p "$moddir/$running"
            if [[ -n "$extra" ]]; then mkdir -p "$moddir/$extra"; fi
            export KEEP_RUNNING_KERNEL_MODULES_DIR="$moddir"
            export FAKE_UNAME="$running"
            export FAKE_KNOWN=" $known "
            hold_log=$(mktemp)
            export HOLD_LOG="$hold_log"
            uname() { printf '%s\n' "$FAKE_UNAME"; }
            apt-cache() {
              local name="${2:-}"
              [[ "$FAKE_KNOWN" == *" $name "* ]]
            }
            apt-mark() { printf '%s\n' "$2" >> "$HOLD_LOG"; }
            dpkg() { return 0; }
            # shellcheck disable=SC1090
            source "$4"
            set +e
            keep_running_kernel
            rc=$?
            set -e
            printf 'RC=%s\n' "$rc"
            cat "$HOLD_LOG"
        ''')
        known = "linux-image-generic linux-virtual linux-image-virtual linux-headers-generic linux-headers-virtual"
        clean = subprocess.run(
            [BASH, "-c", script, "bash", "7.0.0-31-generic", "", known, helper],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(clean.returncode, 0, clean.stderr)
        self.assertIn("RC=0", clean.stdout)
        held = [line.strip() for line in clean.stdout.splitlines() if line.strip() and not line.startswith("RC=")]
        self.assertIn("linux-image-generic", held)
        self.assertIn("linux-virtual", held)
        self.assertNotIn("linux-generic-hwe-24.04", held)
        self.assertNotIn("linux-generic-hwe-26.04", held)
        foreign = subprocess.run(
            [BASH, "-c", script, "bash", "7.0.0-31-generic", "7.0.0-38-generic", known, helper],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(foreign.returncode, 0, foreign.stderr)
        self.assertIn("RC=1", foreign.stdout)
        self.assertIn("7.0.0-38-generic", foreign.stdout + foreign.stderr)

    def test_self_check_fails_on_a_foreign_module_directory(self):
        text = (ROOT / "scripts" / "self_check_generated_repo.sh").read_text(encoding="utf-8")
        self.assertIn("scripts/lib/keep_running_kernel.sh", text)
        self.assertIn("refuse_foreign_installed_kernel", text)
        self.assertIn("[[ -d /lib/modules ]]", text)

    def test_setup_does_not_install_linux_tools_generic(self):
        skeletons = (
            ROOT / "scripts" / "templates" / "setup_cpu_system_skeleton.sh",
            ROOT / "scripts" / "templates" / "setup_nvidia_skeleton.sh",
            ROOT / "scripts" / "templates" / "setup_rocm_reboot_skeleton.sh",
        )
        for path in skeletons:
            executable = [
                line
                for line in path.read_text(encoding="utf-8").splitlines()
                if not line.lstrip().startswith("#")
            ]
            joined = "\n".join(executable)
            self.assertNotIn("linux-tools-generic", joined, path.name)
            self.assertIn("keep_running_kernel", joined, path.name)
            self.assertTrue(
                "linux-tools-$(uname -r)" in joined or 'linux-tools-${KERNEL_RELEASE}' in joined,
                path.name,
            )
        nvidia = (ROOT / "scripts" / "templates" / "setup_nvidia_skeleton.sh").read_text(encoding="utf-8")
        self.assertIn('BENCHMARK_INSTALL_PERF', nvidia)
        rocm = (ROOT / "scripts" / "templates" / "setup_rocm_reboot_skeleton.sh").read_text(encoding="utf-8")
        self.assertNotIn("linux pmu|perf |stress-ng", rocm)

    def test_perf_flag_is_not_selected_by_stress_ng(self):
        registry = (ROOT / "config" / "framework_registry.yaml").read_text(encoding="utf-8")
        amd = registry.split("  amd:", 1)[1].split("  cpu:", 1)[0]
        nvidia = registry.split("  nvidia:", 1)[1].split("  amd:", 1)[0]
        self.assertNotIn("stress-ng", amd[amd.find("BENCHMARK_INSTALL_PERF"):])
        self.assertIn("BENCHMARK_INSTALL_PERF:", nvidia)
        self.assertNotIn("stress-ng", nvidia[nvidia.find("BENCHMARK_INSTALL_PERF"):])

    def test_vllm_self_check_requires_real_server_for_every_profile(self):
        text = (ROOT / "scripts" / "self_check_generated_repo.sh").read_text(encoding="utf-8")
        self.assertIn('scripts/tiny_kv_server.py --host', text)
        self.assertNotIn("smoke must be able to start scripts/tiny_kv_server.py", text)
        self.assertIn("vllm.entrypoints.openai.api_server", text)


if __name__ == "__main__":
    unittest.main()
