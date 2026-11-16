"""A small MCP server over the Streamable HTTP transport, on the loopback address, for the tests.

It answers in JSON or, with ``streaming=True``, as server-sent events with a
log notification before each reply. It hands out a session on ``initialize``
and wants it back, wants the bearer token when given one, offers a ``GET``
stream for what it sends unasked when ``listening=True``, and ends the session
on ``DELETE``. What it was sent is kept in ``requests``.
"""
from __future__ import annotations

import json
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOOLS = [
    {"name": "echo", "description": "Give back the text it is given.",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "slow", "description": "Answer after some seconds.", "inputSchema": {"type": "object"}},
    {"name": "change", "description": "Say the tools changed, on the listening stream.",
     "inputSchema": {"type": "object"}},
]
SESSION = "session-7c1e"
_STREAM_POLL_SECONDS = 0.1


class FakeHttpMcp:
    """The server, started on a free loopback port; ``url`` is where it answers."""

    def __init__(self, *, streaming: bool = False, listening: bool = False, token: str | None = None,
                 protocol: str | None = None) -> None:
        self.streaming = streaming
        self.listening = listening
        self.token = token
        self.protocol = protocol
        self.requests: list[dict] = []
        self.session_open = False
        self.deleted = threading.Event()
        self._pushed: queue.Queue = queue.Queue()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}/mcp"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self.deleted.set()
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(5)

    def push(self, message: dict) -> None:
        """Send *message* on the listening stream."""
        self._pushed.put(message)

    def seen(self, method: str) -> list[dict]:
        """What was sent for *method*: each request's headers and body."""
        return [request for request in self.requests if request["body"].get("method") == method]

    def answer(self, message: dict) -> dict | None:
        """The reply to *message*; ``None`` for a notification or a reply of the client's own."""
        method, request_id = message.get("method"), message.get("id")
        if method is None or request_id is None:
            return None
        result = self._result(method, message.get("params") or {})
        if result is None:
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "no " + method}}
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _result(self, method: str, params: dict) -> dict | None:
        if method == "initialize":
            return {"protocolVersion": self.protocol or params.get("protocolVersion"),
                    "capabilities": {"tools": {"listChanged": True}},
                    "serverInfo": {"name": "fake-http", "version": "0.1"}}
        if method == "tools/list":
            return {"tools": TOOLS}
        if method == "tools/call":
            return self._call(params.get("name"), params.get("arguments") or {})
        if method == "ping":
            return {}
        return None

    def _call(self, name: str, arguments: dict) -> dict | None:
        if name == "echo":
            return {"content": [{"type": "text", "text": arguments.get("text", "")}]}
        if name == "slow":
            time.sleep(float(arguments.get("seconds", 5)))
            return {"content": [{"type": "text", "text": "done"}]}
        if name == "change":
            self.push({"jsonrpc": "2.0", "method": "notifications/tools/list_changed"})
            return {"content": [{"type": "text", "text": "changed"}]}
        return None

    def _handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args) -> None:
                """Keep the test output quiet."""

            def _refused(self) -> int | None:
                if server.token is not None and self.headers.get("Authorization") != f"Bearer {server.token}":
                    return 401
                return None

            def _send(self, status: int, body: bytes = b"", kind: str = "application/json",
                      session: bool = False) -> None:
                self.send_response(status)
                if session:
                    self.send_header("Mcp-Session-Id", SESSION)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self) -> None:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                server.requests.append({"headers": dict(self.headers), "body": body})
                refused = self._refused()
                if refused is not None:
                    self._send(refused, b"no")
                    return
                starting = body.get("method") == "initialize"
                if not starting and (not server.session_open or self.headers.get("Mcp-Session-Id") != SESSION):
                    self._send(404 if server.deleted.is_set() else 400)
                    return
                reply = server.answer(body)
                if starting:
                    server.session_open = True
                if reply is None:
                    self._send(202)
                elif server.streaming:
                    self._stream(reply, starting)
                else:
                    self._send(200, json.dumps(reply).encode(), session=starting)

            def _stream(self, reply: dict, starting: bool) -> None:
                note = {"jsonrpc": "2.0", "method": "notifications/message", "params": {"level": "info",
                                                                                       "data": "working"}}
                events = (": a comment\n\n" + f"event: message\ndata: {json.dumps(note)}\n\n"
                          + f"id: 1\ndata: {json.dumps(reply)}\n\n").encode()
                self._send(200, events, kind="text/event-stream", session=starting)

            def do_GET(self) -> None:
                if not server.listening:
                    self._send(405)
                    return
                if self.headers.get("Mcp-Session-Id") != SESSION or not server.session_open:
                    self._send(404 if server.deleted.is_set() else 400)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                while not server.deleted.is_set():
                    try:
                        message = server._pushed.get(timeout=_STREAM_POLL_SECONDS)
                    except queue.Empty:
                        continue
                    try:
                        self.wfile.write(f"data: {json.dumps(message)}\n\n".encode())
                        self.wfile.flush()
                    except OSError:
                        return

            def do_DELETE(self) -> None:
                server.requests.append({"headers": dict(self.headers), "body": {"method": "DELETE"}})
                server.session_open = False
                server.deleted.set()
                self._send(200)

        return Handler
