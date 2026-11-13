#!/usr/bin/env bash
# File: scripts/lib/apt_mirror_fallback.sh
# Description: Switch a cloud image's Ubuntu apt mirror to the official archive
#              when the image's mirror cannot be reached (TEMPLATE_00_135).
#              On 2026-11-11 fresh AMD images pointed apt at a provider mirror that
#              was IPv6-only on Ubuntu 24.04 and answered 503 on 26.04, so setup
#              failed before any workload step. apt-get update can also exit 0 with
#              "W: Failed to fetch ...", which only fails later at apt-get install.
# Execution: source scripts/lib/apt_mirror_fallback.sh; ensure_ubuntu_apt_mirror
# Returns: 0 apt-get update ran and the Ubuntu archive answered (after a switch, if one
#          was needed); 1 apt-get update still fails; 2 skipped (disabled, not Ubuntu,
#          no third-party Ubuntu mirror, or checked within the last 6 h).
# Environment:
#   BENCHMARK_APT_MIRROR_FALLBACK=0   never check or switch.
#   BENCHMARK_APT_FALLBACK_ARCHIVE    replacement URI (default http://archive.ubuntu.com/ubuntu/,
#                                     or http://ports.ubuntu.com/ubuntu-ports/ off amd64/i386).
#   BENCHMARK_HOST_STATE_DIR          state and backups (default /var/lib/gpu-benchmark-host).
#   BENCHMARK_APT_INDEX_MAX_AGE_SEC   how long a check stays valid (default 21600).
#   APT_MIRROR_SOURCES_FILES, APT_MIRROR_OS_RELEASE   test overrides.
# What changes: only URIs of the Ubuntu archive itself, in /etc/apt/sources.list.d/ubuntu.sources
# and /etc/apt/sources.list. security.ubuntu.com, ports.ubuntu.com, archive.ubuntu.com and
# third-party repositories (NVIDIA, ROCm, PPAs) are never touched. The original files are
# copied to ${BENCHMARK_HOST_STATE_DIR}/apt-sources-backup/ first.

[[ -n "${_APT_MIRROR_FALLBACK_SH:-}" ]] && return 0
_APT_MIRROR_FALLBACK_SH=1

_apt_mirror_root() {
  if declare -f run_noninteractive_root >/dev/null 2>&1; then
    run_noninteractive_root "$@"
  elif [[ "${EUID:-$(id -u)}" -ne 0 ]] && command -v sudo >/dev/null 2>&1; then
    sudo -n env DEBIAN_FRONTEND=noninteractive "$@"
  else
    DEBIAN_FRONTEND=noninteractive "$@"
  fi
}

_apt_mirror_log() {
  if declare -f log_status >/dev/null 2>&1; then
    log_status "$1"
  else
    printf '%s  %s\n' "$(date -u +'%Y-%m-%d %H:%M:%S')" "$1"
  fi
}

_apt_mirror_sources_files() {
  local f
  for f in ${APT_MIRROR_SOURCES_FILES:-/etc/apt/sources.list.d/ubuntu.sources /etc/apt/sources.list}; do
    [[ -f "${f}" ]] && printf '%s\n' "${f}"
  done
}

# Prints each distinct Ubuntu-archive URI (scheme://host/.../ubuntu or ubuntu-ports)
# that is not an official Canonical host, from deb822 "URIs:" fields and one-line
# "deb" entries. Third-party repositories (repo.radeon.com, NVIDIA, PPAs) do not end
# in /ubuntu, so they are never listed.
ubuntu_mirror_uris() {
  local f
  while IFS= read -r f; do
    awk '
      /^[[:space:]]*#/ { next }
      /^[[:space:]]*URIs:/ { for (i = 2; i <= NF; i++) print $i; next }
      /^[[:space:]]*deb(-src)?[[:space:]]/ {
        for (i = 2; i <= NF; i++) { if ($i ~ /^\[/) { while (i <= NF && $i !~ /\]$/) i++; continue } print $i; break }
      }
    ' "${f}"
  done < <(_apt_mirror_sources_files) |
    grep -E '^(https?|mirror\+https?)://[^/]+(/[^[:space:]]*)?/ubuntu(-ports)?/?$' |
    grep -vE '^[a-z+]+://(archive|security|ports|[a-z]{2}\.archive)\.ubuntu\.com(/|$)' |
    sort -u
}

_apt_mirror_host() {
  local uri=$1
  uri="${uri#*://}"
  printf '%s\n' "${uri%%/*}"
}

_apt_mirror_fallback_uri() {
  if [[ -n "${BENCHMARK_APT_FALLBACK_ARCHIVE:-}" ]]; then
    printf '%s\n' "${BENCHMARK_APT_FALLBACK_ARCHIVE}"
    return 0
  fi
  case "$(dpkg --print-architecture 2>/dev/null || echo amd64)" in
    amd64|i386) printf '%s\n' "http://archive.ubuntu.com/ubuntu/" ;;
    *) printf '%s\n' "http://ports.ubuntu.com/ubuntu-ports/" ;;
  esac
}

# Prints the hosts among "$@" that apt-get update output (file $1 is the log) reports as failed.
_apt_mirror_failed_hosts() {
  local log=$1 host
  shift
  for host in "$@"; do
    if grep -E '^(Err:|W: Failed to fetch|E: Failed to fetch|W: Some index files failed|E: The repository)' "${log}" |
      grep -qF "${host}"; then
      printf '%s\n' "${host}"
    fi
  done
}

_apt_mirror_update() {
  local log=$1
  _apt_mirror_root apt-get update -y >"${log}" 2>&1
  local rc=$?
  cat "${log}"
  return "${rc}"
}

ensure_ubuntu_apt_mirror() {
  [[ "${BENCHMARK_APT_MIRROR_FALLBACK:-1}" == "0" ]] && return 2
  local os_release="${APT_MIRROR_OS_RELEASE:-/etc/os-release}"
  grep -qE '^ID=("?)ubuntu\1$' "${os_release}" 2>/dev/null || return 2
  local state="${BENCHMARK_HOST_STATE_DIR:-/var/lib/gpu-benchmark-host}"
  local stamp="${state}/apt_mirror_checked_epoch" max_age="${BENCHMARK_APT_INDEX_MAX_AGE_SEC:-21600}"
  local now last
  now="$(date +%s)"
  if [[ -r "${stamp}" ]]; then
    last="$(cat "${stamp}" 2>/dev/null || true)"
    if [[ "${last}" =~ ^[0-9]+$ ]] && (( now - last >= 0 && now - last < max_age )); then
      return 2
    fi
  fi
  local -a uris=() hosts=() failed=()
  mapfile -t uris < <(ubuntu_mirror_uris)
  if (( ${#uris[@]} == 0 )); then
    return 2
  fi
  local uri log rc
  for uri in "${uris[@]}"; do hosts+=("$(_apt_mirror_host "${uri}")"); done
  log="$(mktemp)"
  _apt_mirror_log "STEP|SETUP apt-get update (checking Ubuntu mirror ${hosts[*]})"
  _apt_mirror_update "${log}"
  rc=$?
  mapfile -t failed < <(_apt_mirror_failed_hosts "${log}" "${hosts[@]}")
  if (( rc == 0 && ${#failed[@]} == 0 )); then
    rm -f "${log}"
    { mkdir -p "${state}" && printf '%s\n' "${now}" > "${stamp}" && printf '%s\n' "${now}" > "${state}/apt_updated_epoch"; } 2>/dev/null || true
    return 0
  fi
  if (( ${#failed[@]} == 0 )); then
    # apt failed, but not because of the Ubuntu mirror (a lock, a third-party repo):
    # leave the sources alone and let the caller report it.
    rm -f "${log}"
    return 1
  fi
  local target backup_dir f h
  target="$(_apt_mirror_fallback_uri)"
  backup_dir="${state}/apt-sources-backup/$(date -u +%Y%m%dT%H%M%SZ)"
  _apt_mirror_log "WARN|SETUP Ubuntu mirror ${failed[*]} failed; switching to ${target}"
  mkdir -p "${backup_dir}" 2>/dev/null || _apt_mirror_root mkdir -p "${backup_dir}"
  while IFS= read -r f; do
    _apt_mirror_root cp -p "${f}" "${backup_dir}/$(basename "${f}")"
    for uri in "${uris[@]}"; do
      h="$(_apt_mirror_host "${uri}")"
      printf '%s\n' "${failed[@]}" | grep -qxF "${h}" || continue
      _apt_mirror_root sed -i "s#${uri%/}/\?\([[:space:]]\|\$\)#${target%/}/\1#g" "${f}"
    done
  done < <(_apt_mirror_sources_files)
  { printf 'switched %s -> %s (backup %s)\n' "${failed[*]}" "${target}" "${backup_dir}" > "${state}/apt_mirror_fallback.txt"; } 2>/dev/null || true
  echo "[WARN] apt sources changed: ${failed[*]} -> ${target}. Originals: ${backup_dir}" >&2
  _apt_mirror_update "${log}"
  rc=$?
  mapfile -t failed < <(_apt_mirror_failed_hosts "${log}" "$(_apt_mirror_host "${target}")")
  rm -f "${log}"
  if (( rc == 0 && ${#failed[@]} == 0 )); then
    { mkdir -p "${state}" && printf '%s\n' "${now}" > "${stamp}" && printf '%s\n' "${now}" > "${state}/apt_updated_epoch"; } 2>/dev/null || true
    return 0
  fi
  echo "[FAIL] apt-get update still fails after switching to ${target}. Check the network (DNS, IPv4 route) of this machine." >&2
  return 1
}
