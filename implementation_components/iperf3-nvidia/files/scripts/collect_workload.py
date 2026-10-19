#!/usr/bin/env python3
# File: scripts/collect_workload.py
# Description: Real iperf3 JSON. Loopback is labeled; BENCHMARK_IPERF_PEER overrides.
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import yaml


def pv(params, key, profile, default=""):
    raw = params.get(key, default)
    if isinstance(raw, dict):
        return raw.get(profile, raw.get("smoke", default))
    return default if raw is None else raw


def as_list(value):
    return [p.strip() for p in str(value or "").replace(";", ",").split(",") if p.strip()]


# "0" is iperf3's unlimited rate. A fixed cap (10G until 2026-10-19) made the UDP
# throughput metric report the cap: 9.99 Gbit/s on every profile while TCP on
# the same loopback reached 55 Gbit/s.
DEFAULT_UDP_RATE = "0"


def udp_rate(raw) -> str:
    """UDP -b target rate. iperf3 itself defaults UDP to 1 Mbit/s, which made the
    UDP metric report that cap instead of throughput. Empty or 0 uses DEFAULT_UDP_RATE,
    which is "0": unlimited, so the receiver-side rate is the loopback UDP throughput."""
    text = str(raw or "").strip()
    if text in {"", "0", "0M", "0K", "0G"}:
        return DEFAULT_UDP_RATE
    return text


def received_bps(end: dict, protocol: str) -> float:
    """Receiver-side bits/s: what actually arrived, not what the sender pushed.
    iperf3 reports end.sum_received for TCP and, in current versions, for UDP.
    Older iperf3 UDP output has only end.sum (sender rate) with the receiver's
    packet counts; scale it by the packets that arrived. 0.0 when neither exists."""
    received = end.get("sum_received")
    if isinstance(received, dict) and received.get("bits_per_second") is not None:
        return float(received["bits_per_second"])
    if protocol == "udp":
        total = end.get("sum") or {}
        packets = float(total.get("packets") or 0)
        lost = float(total.get("lost_packets") or 0)
        bits = float(total.get("bits_per_second") or 0)
        if packets > 0 and bits > 0:
            return bits * max(packets - lost, 0.0) / packets
    return 0.0


def client_timeout(seconds: int) -> int:
    # -t N is transfer time. Localhost TCP plus -J wrap-up overruns seconds+30
    # on baseline (100s) and extended (290s).
    return max(int(seconds) + 180, int(seconds) * 3)


def _stop(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def iperf(protocol: str, port: int, seconds: int, streams: int, reverse, bandwidth: str, peer: str):
    last_error = ""
    budget = client_timeout(seconds)
    for candidate in (port, port + 1, port + 2):
        server = None
        if peer in {"127.0.0.1", "localhost"}:
            server = subprocess.Popen(
                ["iperf3", "-s", "-1", "-p", str(candidate)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            time.sleep(0.3)
            if server.poll() is not None:
                last_error = server.stderr.read() if server.stderr else "iperf3 server exited"
                continue
        cmd = [
            "iperf3", "-c", peer, "-p", str(candidate),
            "-t", str(seconds), "-P", str(streams), "-i", "0", "-J",
        ]
        if protocol == "udp":
            cmd += ["-u", "-b", bandwidth]
        if str(reverse).lower() in {"true", "1", "yes"}:
            cmd.append("-R")
        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=budget)
        except subprocess.TimeoutExpired:
            _stop(server)
            last_error = f"iperf3 {protocol} client exceeded {budget}s"
            continue
        _stop(server)
        try:
            payload = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError:
            last_error = (completed.stderr or "iperf3 produced invalid JSON")[-300:]
            continue
        end = payload.get("end") or {}
        sum_sent = end.get("sum_sent") or end.get("sum") or {}
        bits = received_bps(end, protocol)
        jitter = float((end.get("sum") or {}).get("jitter_ms") or 0.0)
        lost = float((end.get("sum") or {}).get("lost_percent") or 0.0)
        retr = float(sum_sent.get("retransmits") or 0.0)
        if bits <= 0:
            last_error = (completed.stderr or completed.stdout or "iperf3 reported 0 bits/s")[-300:]
            continue
        return bits, jitter, lost, retr, ""
    return 0.0, 0.0, 0.0, 0.0, last_error or "iperf3 failed"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--raw-file", required=True)
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--config", default="config/benchmark_config.yaml")
    parser.add_argument("--device", default="gpu")
    parser.add_argument("--output-format", default="csv")
    args = parser.parse_args()
    if not shutil.which("iperf3"):
        raise SystemExit("[FAIL] iperf3 is required")
    params = (yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}).get("sweep") or {}
    seconds = max(1, int(float(pv(params, "time", args.profile, 2) or 2)))
    port = int(float(pv(params, "port", args.profile, 5201) or 5201))
    streams = int(float(pv(params, "parallel_streams", args.profile, 1) or 1))
    reverse = pv(params, "reverse_mode", args.profile, False)
    protocols = as_list(pv(params, "protocol", args.profile, "tcp,udp"))
    bandwidth = udp_rate(pv(params, "bandwidth_limit", args.profile, pv(params, "bandwidth", args.profile, "")))
    peer = os.environ.get("BENCHMARK_IPERF_PEER", "127.0.0.1")
    Path(args.run_dir).mkdir(parents=True, exist_ok=True)
    header = [
        "sample_index", "status", "protocol", "iperf_endpoint", "parallel_streams",
        "tcp_loopback_gbps", "udp_throughput_gbps", "udp_jitter_ms", "packet_loss_rate",
        "tcp_retransmit_count", "bits_per_second", "error_message",
    ]
    rows = []
    for proto in protocols or ["tcp"]:
        bits, jitter, lost, retr, error = iperf(proto.lower(), port, seconds, streams, reverse, bandwidth, peer)
        if bits <= 0:
            raise SystemExit(f"[FAIL] iperf3 {proto} produced no throughput: {error}")
        rows.append({
            "status": "ok",
            "protocol": proto,
            "iperf_endpoint": "loopback" if peer in {"127.0.0.1", "localhost"} else peer,
            "parallel_streams": streams,
            "tcp_loopback_gbps": (bits / 1e9) if proto.lower() == "tcp" else "",
            "udp_throughput_gbps": (bits / 1e9) if proto.lower() != "tcp" else "",
            # Each metric only on the row of the protocol that measures it. A 0.0 on
            # the other row was averaged in and halved jitter, loss and retransmits.
            "udp_jitter_ms": jitter if proto.lower() != "tcp" else "",
            "packet_loss_rate": lost if proto.lower() != "tcp" else "",
            "tcp_retransmit_count": retr if proto.lower() == "tcp" else "",
            "bits_per_second": bits,
            "error_message": "",
        })
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=header, extrasaction="ignore", lineterminator=chr(10))
    writer.writeheader()
    if len(rows) == 1:
        rows.append(dict(rows[0]))
    for index, row in enumerate(rows):
        writer.writerow({"sample_index": index, **row})
    Path(args.raw_file).write_text(buf.getvalue(), encoding="utf-8")
    print(buf.getvalue(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
