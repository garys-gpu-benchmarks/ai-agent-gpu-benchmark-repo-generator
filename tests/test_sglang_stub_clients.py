#!/usr/bin/env python3
# File: tests/test_sglang_stub_clients.py
# Description: Run each SGLang client overlay against scripts/tiny_sglang_server.py on
# this machine and check the CSV it writes. Smoke on the VM is the first place these
# clients used to meet a server, so a server_identity or CSV regression cost a full
# remote setup to find. No GPU, SGLang, or network access is needed.
from __future__ import annotations

import csv
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "implementation_components"
METRIC_CONTRACT = ROOT / "scripts" / "metric_contract.py"
STUB_NA = "na (stub server, smoke only)"

PROMPT_RESPONSE = ("sglang-prompt-response-amd", "sglang-prompt-response-nvidia")
SERVING = ("sglang-serving-amd", "sglang-serving-nvidia")
PROMPT_METRICS = (
    "end_to_end_latency_ms",
    "ttft_ms",
    "output_tokens_per_s",
    "completed_request_rate_pct",
    "radixattention_cache_hit_rate_pct",
)
SERVING_METRICS = (
    "end_to_end_request_latency_p50_msec",
    "ttft_p50_msec",
    "time_per_output_token_tpot_p50_msec",
    "inter_token_latency_itl_p50_msec",
    "request_throughput_requests_sec",
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_port(port: int, proc: subprocess.Popen, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise AssertionError(f"stub server exited early with {proc.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise AssertionError(f"stub server did not listen on {port} within {timeout}s")


class _Workspace:
    """A temporary scripts/ folder holding one component's client, the stub, and metric_contract.py."""

    def __init__(self, component: str, client: str) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix=f"{component}-"))
        self.scripts = self.tmp / "scripts"
        self.scripts.mkdir()
        source = COMPONENTS / component / "files" / "scripts"
        for name in (client, "tiny_sglang_server.py"):
            shutil.copy2(source / name, self.scripts / name)
        shutil.copy2(METRIC_CONTRACT, self.scripts / "metric_contract.py")
        self.client = self.scripts / client
        self.run_dir = self.tmp / "results" / "raw" / "run"
        self.env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(self.scripts))
        self.env.pop("BENCHMARK_SERVER_KIND", None)
        self.server: subprocess.Popen | None = None

    def start_server(self) -> int:
        port = _free_port()
        self.server = subprocess.Popen(
            [sys.executable, str(self.scripts / "tiny_sglang_server.py"), "--host", "127.0.0.1", "--port", str(port)],
            cwd=self.tmp,
            env=self.env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _wait_for_port(port, self.server)
        return port

    def run_client(self, port: int, *extra: str) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            str(self.client),
            "--run-dir",
            str(self.run_dir),
            "--base-url",
            f"http://127.0.0.1:{port}",
            "--input-len",
            "16",
            "--output-len",
            "4",
            "--num-prompts",
            "3",
            *extra,
        ]
        return subprocess.run(command, cwd=self.tmp, env=self.env, capture_output=True, text=True, timeout=120)

    def rows(self) -> list[dict[str, str]]:
        path = self.run_dir / "raw_results.csv"
        if not path.is_file():
            raise AssertionError(f"{path} was not written")
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def close(self) -> None:
        if self.server is not None and self.server.poll() is None:
            self.server.terminate()
            try:
                self.server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.server.kill()
        shutil.rmtree(self.tmp, ignore_errors=True)


class PromptResponseClientAgainstStub(unittest.TestCase):
    def test_writes_stub_csv(self) -> None:
        for component in PROMPT_RESPONSE:
            with self.subTest(component=component):
                ws = _Workspace(component, "prompt_response_client.py")
                try:
                    port = ws.start_server()
                    result = ws.run_client(port, "--streaming", "true")
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    rows = ws.rows()
                    self.assertEqual(len(rows), 3)
                    for row in rows:
                        self.assertEqual(row["status"], "stub", row)
                        self.assertEqual(row["server_identity"], "stub", row)
                        for key in PROMPT_METRICS:
                            self.assertEqual(row[key], STUB_NA, (key, row))
                    self.assertEqual(
                        (ws.run_dir / "raw_output.csv").read_text(encoding="utf-8"),
                        (ws.run_dir / "raw_results.csv").read_text(encoding="utf-8"),
                    )
                    self.assertTrue((ws.run_dir / "raw_results.jsonl").is_file())
                finally:
                    ws.close()

    def test_no_server_still_writes_csv_and_fails(self) -> None:
        ws = _Workspace(PROMPT_RESPONSE[1], "prompt_response_client.py")
        try:
            result = ws.run_client(_free_port())
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            rows = ws.rows()
            self.assertEqual(len(rows), 3)
            self.assertTrue(all(row["status"] == "error" for row in rows), rows)
            self.assertIn("[FAIL] all 3 requests failed", result.stdout)
        finally:
            ws.close()


class WarmupRequests(unittest.TestCase):
    """2026-10-20: the first request after server start waited 94-136 s for one-time
    compilation and was averaged into TTFT. Each client now sends untimed warm-up
    requests first; they never appear in the CSV."""

    def test_prompt_client_warms_up_untimed(self) -> None:
        ws = _Workspace(PROMPT_RESPONSE[1], "prompt_response_client.py")
        try:
            port = ws.start_server()
            result = ws.run_client(port)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("[INFO] warm-up request 1/1 (untimed)", result.stdout)
            self.assertEqual([row["request_id"] for row in ws.rows()], ["1", "2", "3"])
            off = ws.run_client(port, "--warmup-requests", "0")
            self.assertNotIn("warm-up", off.stdout)
        finally:
            ws.close()

    def test_warmup_prompt_shares_no_words_with_timed_prompts(self) -> None:
        sys.path.insert(0, str(COMPONENTS / PROMPT_RESPONSE[1] / "files" / "scripts"))
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            import prompt_response_client as client  # noqa: PLC0415
        finally:
            sys.path.pop(0)
            sys.path.pop(0)
        warm = set(client.warmup_prompt(64).split())
        timed = set(client.prompt_text(64, 42).split())
        self.assertFalse(warm & timed)
        self.assertEqual(len(client.warmup_prompt(64).split()), 64)

    def test_serving_client_warms_up_at_full_concurrency(self) -> None:
        ws = _Workspace(SERVING[0], "bench_serving.py")
        try:
            port = ws.start_server()
            result = ws.run_client(port, "--max-concurrency", "2")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("[INFO] warm-up: 2 untimed request(s)", result.stdout)
            self.assertEqual([row["check_name"] for row in ws.rows()], ["req_0", "req_1", "req_2", "summary"])
        finally:
            ws.close()


class ServingClientAgainstStub(unittest.TestCase):
    def test_writes_stub_csv(self) -> None:
        for component in SERVING:
            with self.subTest(component=component):
                ws = _Workspace(component, "bench_serving.py")
                try:
                    port = ws.start_server()
                    result = ws.run_client(port, "--max-concurrency", "2")
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    rows = ws.rows()
                    self.assertEqual([row["check_name"] for row in rows], ["req_0", "req_1", "req_2", "summary"])
                    for row in rows:
                        self.assertEqual(row["status"], "stub", row)
                        self.assertIn("stub", row["server_identity"], row)
                        for key in SERVING_METRICS:
                            self.assertTrue(row[key].startswith("na ("), (key, row[key]))
                    self.assertTrue((ws.run_dir / "raw_output.txt").is_file())
                finally:
                    ws.close()


if __name__ == "__main__":
    unittest.main()
