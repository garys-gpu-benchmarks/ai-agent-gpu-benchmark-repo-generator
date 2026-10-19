#!/usr/bin/env python3
"""Smoke-only OpenAI-compatible completions server for SGLang workloads.

Baseline and extended must launch python -m sglang.launch_server.
"""
from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tiny OpenAI-compatible SGLang smoke server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=30000)
    parser.add_argument("--model-name", default="mistralai/Mistral-7B-v0.3")
    parser.add_argument("--max-model-len", default="2048")
    parser.add_argument("--gpu-memory-utilization", default="0.8")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    model_name = str(args.model_name)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *log_args) -> None:
            print(f"[tiny-sglang] {self.address_string()} {fmt % log_args}", flush=True)

        def _json(self, code: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Benchmark-Server", "tiny-sglang-stub")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                return {}
            return data if isinstance(data, dict) else {}

        def do_GET(self) -> None:  # noqa: N802
            if self.path.split("?", 1)[0] in {"/v1/models", "/health", "/get_model_info"}:
                self._json(
                    200,
                    {
                        "object": "list",
                        "server_identity": "stub",
                        "data": [{"id": model_name, "object": "model", "owned_by": "tiny-sglang"}],
                    },
                )
                return
            self._json(404, {"error": {"message": "not found"}})

        def do_POST(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path not in {"/v1/completions", "/v1/chat/completions"}:
                self._json(404, {"error": {"message": "not found"}})
                return
            req = self._read_json()
            max_tokens = max(1, int(req.get("max_tokens") or req.get("max_new_tokens") or 16))
            prompt = req.get("prompt") or ""
            if isinstance(req.get("messages"), list) and req["messages"]:
                prompt = str(req["messages"][-1].get("content") or prompt)
            text = ("ok " * max_tokens).strip()
            created = int(time.time())
            usage = {
                "prompt_tokens": max(1, len(str(prompt).split())),
                "completion_tokens": max_tokens,
                "total_tokens": max(1, len(str(prompt).split())) + max_tokens,
            }
            if req.get("stream"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("X-Benchmark-Server", "tiny-sglang-stub")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                words = text.split()
                for index, word in enumerate(words):
                    chunk = {
                        "id": "tiny-sglang-cmpl",
                        "server_identity": "stub",
                        "object": "text_completion",
                        "created": created,
                        "model": str(req.get("model") or model_name),
                        "choices": [{"index": 0, "text": word + (" " if index + 1 < len(words) else ""), "finish_reason": None}],
                    }
                    self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    time.sleep(0.001)
                done = {
                    "id": "tiny-sglang-cmpl",
                    "server_identity": "stub",
                    "object": "text_completion",
                    "created": created,
                    "model": str(req.get("model") or model_name),
                    "choices": [{"index": 0, "text": "", "finish_reason": "stop"}],
                    "usage": usage,
                }
                self.wfile.write(f"data: {json.dumps(done)}\n\n".encode("utf-8"))
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
                return
            self._json(
                200,
                {
                    "id": "tiny-sglang-cmpl",
                    "server_identity": "stub",
                    "object": "text_completion",
                    "created": created,
                    "model": str(req.get("model") or model_name),
                    "choices": [{"index": 0, "text": text, "finish_reason": "stop"}],
                    "usage": usage,
                },
            )

    server = ThreadingHTTPServer((args.host, int(args.port)), Handler)
    print(
        "STUB stand-in server (not SGLang); numbered serving metrics must not be published as SGLang results.",
        flush=True,
    )
    print(f"[tiny-sglang] listening on http://{args.host}:{args.port} model={model_name}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
