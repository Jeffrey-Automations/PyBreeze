"""An MCP server already running at a URL: the protocol's Streamable HTTP transport.

Each message the client sends is the body of a ``POST`` to the server's URL.
The server answers a request either with one JSON message or with a stream of
server-sent events (``text/event-stream``) carrying the reply and, before it,
whatever the server has to say meanwhile; a notification or a reply of the
client's own is answered ``202 Accepted`` with nothing. The session the server
names in its first answer (``Mcp-Session-Id``) is sent back with every message,
and so is the protocol revision agreed on (``MCP-Protocol-Version``). Once the
connection is open, a ``GET`` stream carries what the server sends unasked (a
changed list, a ping), when the server offers one. Closing sends ``DELETE``.

Every request goes through ``public_session()``: the address is checked as the
connection is made, redirects are not followed, and an address on this machine
or a private network is reached only when it is among the addresses the user
was shown and allowed (``allowed_local``). A host that needs that answer is
refused at :meth:`HttpTransport.start` with :class:`McpLocalAddressError`, which
names it. The profile's headers (its token) go with every request and nowhere
else: what is logged or shown of a failure is its status line or its kind.

Each message is sent on a thread of its own, so a reply streamed for minutes
never holds up a cancellation; a request that cannot be sent is answered with a
JSON-RPC error in its place, which fails it at once. Nothing here touches Qt.
"""
from __future__ import annotations

import contextlib
import json
import threading
from collections import deque
from collections.abc import Callable, Iterable, Iterator

import requests

from pybreeze.utils.exception.exception_tags import mcp_start_error
from pybreeze.utils.exception.exceptions import McpException
from pybreeze.utils.logging.logger import pybreeze_logger
from pybreeze.utils.mcp.mcp_profile import McpServerProfile
from pybreeze.utils.mcp.mcp_redaction import redact_text
from pybreeze.utils.mcp.mcp_transport import MAX_MESSAGE_BYTES, McpClosed
from pybreeze.utils.network.http_client import (
    CONNECT_TIMEOUT, ResponseTooLargeError, describe_request_error, read_capped_text, succeeded,
)
from pybreeze.utils.network.public_http import approved_local_addresses, public_session
from pybreeze.utils.network.url_validation import LocalAddressNeedsApprovalError, UnsafeURLError, validate_url

SESSION_HEADER = "Mcp-Session-Id"
VERSION_HEADER = "MCP-Protocol-Version"
_JSON = "application/json"
_EVENT_STREAM = "text/event-stream"
# What reading a stream can raise once close() has shut it from another thread: http.client's own
# AttributeError among them, which it raises when its connection is taken away mid-read
_READ_FAILURES = (requests.RequestException, ResponseTooLargeError, UnsafeURLError, ValueError, OSError,
                  AttributeError)
# The JSON-RPC code a request is failed with when it could not be sent: a server error of the client's own
_NOT_SENT = -32000
# A server that offers no stream of its own answers the GET with this
_NO_STREAM = 405
_SESSION_GONE = 404
# The listening stream is given up after this many failures in a row, waiting this long between them
_MAX_LISTEN_FAILURES = 3
_LISTEN_RETRY_SECONDS = 2.0
# How long the listening stream may stay silent before it is opened again
_LISTEN_READ_SECONDS = 300.0
# How long a reply may stay silent beyond the profile's own time, and how long closing may take
_READ_MARGIN_SECONDS = 5.0
_CLOSE_SECONDS = 5.0
_CHUNK_BYTES = 8192
# How an event stream's lines end: LF, or CRLF with the CR taken off after
_LINE_END = b"\n"
_CARRIAGE_RETURN = b"\r"
_KEPT_NOTES = 50


class McpLocalAddressError(McpException):
    """The server's URL names a host on this machine or a private network, which the user has not allowed.

    :param host: the host as the URL names it
    :param addresses: the addresses it resolves to that need the user's yes
    """

    def __init__(self, host: str, addresses: tuple[str, ...]) -> None:
        super().__init__(mcp_start_error.format(reason=", ".join(addresses)))
        self.host = host
        self.addresses = addresses


class _Refused(Exception):
    """The server answered a message with a status that is not success."""

    def __init__(self, response: requests.Response) -> None:
        super().__init__(f"HTTP {response.status_code} {response.reason or ''}".strip())


def _lines(chunks: Iterable[bytes], max_bytes: int) -> Iterator[bytes]:
    """The lines of a stream of *chunks*, without their ends, then an empty one: the stream's end ends an event too.

    :raises ValueError: when a line grows past *max_bytes*
    """
    pending = b""
    for chunk in chunks:
        *lines, pending = (pending + chunk).split(_LINE_END)
        if len(pending) > max_bytes:
            raise ValueError("an event line is longer than the limit")
        yield from (line.rstrip(_CARRIAGE_RETURN) for line in lines)
    if pending:
        yield pending.rstrip(_CARRIAGE_RETURN)
    yield b""


def event_data(chunks: Iterable[bytes], max_bytes: int = MAX_MESSAGE_BYTES) -> Iterator[str]:
    """The ``data`` of each server-sent event in a stream of *chunks*, as the events end.

    An event's ``data`` lines are joined with newlines; its ``event`` and ``id``
    fields and comment lines are passed over. An event without data yields
    nothing.

    :raises ValueError: when one line or one event grows past *max_bytes*
    """
    data: list[bytes] = []
    size = 0
    for line in _lines(chunks, max_bytes):
        if not line:
            if data:
                yield _LINE_END.join(data).decode("utf-8", "replace")
            data, size = [], 0
            continue
        field, _colon, value = line.partition(b":")
        if field != b"data":
            continue
        value = value[1:] if value.startswith(b" ") else value
        size += len(value)
        if size > max_bytes:
            raise ValueError("an event is larger than the limit")
        data.append(value)


def messages_in(text: str) -> list[dict]:
    """The JSON-RPC messages *text* holds: one object, or a batch of them; none when it is neither."""
    try:
        found = json.loads(text)
    except (ValueError, RecursionError):
        return []
    if isinstance(found, dict):
        return [found]
    if isinstance(found, list):
        return [message for message in found if isinstance(message, dict)]
    return []


def _arriving(response: requests.Response) -> Iterator[bytes]:
    """The body of *response* as it arrives, however little at a time, until it ends.

    Not ``iter_content``: it waits for a whole chunk, and an event stream that
    sends one short event and then waits held that event back with it.
    """
    while True:
        data = response.raw.read1(_CHUNK_BYTES, decode_content=True)
        if not data:
            return
        yield data


def _media_type(response: requests.Response) -> str:
    return response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()


class HttpTransport:
    """One MCP server at a URL.

    :param profile: where it is and the headers it is sent
    :param on_message: called with each message the server sends, on the thread that read it
    :param on_closed: called once, when the session ends or the connection is closed
    :param allowed_local: the addresses on this machine or a private network the user allowed for its host
    """

    def __init__(self, profile: McpServerProfile, on_message: Callable[[dict], None],
                 on_closed: Callable[[], None], allowed_local: frozenset[str] = frozenset()) -> None:
        self._profile = profile
        self._on_message = on_message
        self._on_closed = on_closed
        self._allowed_local = allowed_local
        self._session: requests.Session | None = None
        self._session_id: str | None = None
        self._protocol_version: str | None = None
        self._initialize_id: object = None
        self._closed = threading.Event()
        self._told_closed = False
        self._guard = threading.Lock()
        self._open_responses: set[requests.Response] = set()
        self._notes: deque[str] = deque(maxlen=_KEPT_NOTES)

    # ------------------------------------------------------------------
    # The connection
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Check the URL and open the session; nothing is sent yet.

        :raises McpLocalAddressError: when the host needs the user's yes
        :raises McpException: when the URL is refused outright
        """
        try:
            validate_url(self._profile.url, self._allowed_local)
        except LocalAddressNeedsApprovalError as error:
            raise McpLocalAddressError(error.host, error.addresses) from None
        except UnsafeURLError as error:
            raise McpException(mcp_start_error.format(reason=str(error))) from None
        self._session = public_session()

    def log_tail(self) -> list[str]:
        """What went wrong talking to the server, oldest first: status lines and kinds of failure."""
        return list(self._notes)

    def close(self) -> None:
        """End the session: the server is told (``DELETE``), and every stream still open is closed."""
        if self._closed.is_set():
            return
        self._closed.set()
        session, session_id = self._session, self._session_id
        if session is not None and session_id is not None:
            try:
                with approved_local_addresses(self._allowed_local):
                    session.delete(self._profile.url, headers=self._headers(_JSON),
                                   timeout=(CONNECT_TIMEOUT, _CLOSE_SECONDS), allow_redirects=False).close()
            except requests.RequestException as error:
                pybreeze_logger.debug("mcp_http_transport.py %s not told of the end: %s",
                                      self._profile.name, type(error).__name__)
        with self._guard:
            responses = list(self._open_responses)
        for response in responses:
            response.close()
        if session is not None:
            session.close()
        self._tell_closed()

    def _lost(self) -> None:
        """The server ended the session: nothing more will be answered."""
        self._closed.set()
        self._tell_closed()

    def _tell_closed(self) -> None:
        with self._guard:
            if self._told_closed:
                return
            self._told_closed = True
        self._on_closed()

    def _note(self, text: str) -> None:
        self._notes.append(redact_text(text, self._profile.secrets()))

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    def send(self, message: dict) -> None:
        """Send *message* to the server on a thread of its own; what it answers comes to ``on_message``.

        :raises McpClosed: when the connection is closed
        """
        if self._closed.is_set() or self._session is None:
            raise McpClosed
        if message.get("method") == "initialize":
            self._initialize_id = message.get("id")
        threading.Thread(target=self._post, args=(message,), name="pybreeze-mcp-http-post", daemon=True).start()
        if message.get("method") == "notifications/initialized":
            threading.Thread(target=self._listen, name="pybreeze-mcp-http-listen", daemon=True).start()

    def _headers(self, accept: str) -> dict[str, str]:
        """The profile's headers, then the protocol's own, which they may not replace."""
        headers = {**self._profile.headers, "Accept": accept}
        if self._session_id is not None:
            headers[SESSION_HEADER] = self._session_id
        if self._protocol_version is not None:
            headers[VERSION_HEADER] = self._protocol_version
        return headers

    def _post(self, message: dict) -> None:
        """Send one message and hand on what the server answers; a request that fails is answered with an error."""
        body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {**self._headers(f"{_JSON}, {_EVENT_STREAM}"), "Content-Type": _JSON}
        read_seconds = self._profile.timeout_seconds + _READ_MARGIN_SECONDS
        try:
            with approved_local_addresses(self._allowed_local):
                response = self._session.post(self._profile.url, data=body, headers=headers,
                                              timeout=(CONNECT_TIMEOUT, read_seconds), allow_redirects=False,
                                              stream=True)
                self._answered(response, read_seconds)
        except (*_READ_FAILURES, _Refused) as error:
            self._not_sent(message, error)

    def _not_sent(self, message: dict, error: Exception) -> None:
        """Say why *message* did not get through; a request is answered with that, so it fails at once."""
        if self._closed.is_set():
            return
        reason = str(error) if isinstance(error, _Refused) else describe_request_error(error)
        self._note(reason)
        pybreeze_logger.info("mcp_http_transport.py %s: %s not sent: %s",
                             self._profile.name, message.get("method", "reply"), reason)
        if "method" in message and "id" in message:
            self._on_message({"jsonrpc": "2.0", "id": message["id"],
                              "error": {"code": _NOT_SENT, "message": reason}})

    def _answered(self, response: requests.Response, read_seconds: float) -> None:
        """Take the session the server named, then the messages its answer holds."""
        with self._kept_open(response):
            named = response.headers.get(SESSION_HEADER)
            if named and self._session_id is None:
                self._session_id = named
            if response.status_code == _SESSION_GONE and self._session_id is not None:
                self._note(str(_Refused(response)))
                self._lost()
                return
            if not succeeded(response):
                raise _Refused(response)
            self._deliver(response, read_seconds)

    def _deliver(self, response: requests.Response, read_seconds: float) -> None:
        """Hand on each message *response* carries: a JSON body, or a stream of events."""
        kind = _media_type(response)
        if kind == _EVENT_STREAM:
            texts: Iterable[str] = event_data(_arriving(response))
        elif kind == _JSON:
            texts = [read_capped_text(response, max_bytes=MAX_MESSAGE_BYTES, max_seconds=read_seconds)]
        else:
            return
        for text in texts:
            for message in messages_in(text):
                self._take_version(message)
                self._on_message(message)

    def _take_version(self, message: dict) -> None:
        """Keep the protocol revision the server agreed to in its reply to ``initialize``."""
        if self._initialize_id is None or message.get("id") != self._initialize_id:
            return
        result = message.get("result")
        version = result.get("protocolVersion") if isinstance(result, dict) else None
        if isinstance(version, str) and version:
            self._protocol_version = version

    # ------------------------------------------------------------------
    # What the server sends unasked
    # ------------------------------------------------------------------

    def _listen(self) -> None:
        """Keep a ``GET`` stream open for what the server sends unasked, while it offers one."""
        failures = 0
        while not self._closed.is_set() and failures < _MAX_LISTEN_FAILURES:
            try:
                if not self._listen_once():
                    return
                failures = 0
            except (*_READ_FAILURES, _Refused) as error:
                failures += 1
                pybreeze_logger.debug("mcp_http_transport.py %s stream ended: %s",
                                      self._profile.name, type(error).__name__)
            self._closed.wait(_LISTEN_RETRY_SECONDS)

    def _listen_once(self) -> bool:
        """Read one ``GET`` stream to its end; whether it is worth opening again."""
        with approved_local_addresses(self._allowed_local):
            response = self._session.get(self._profile.url, headers=self._headers(_EVENT_STREAM),
                                         timeout=(CONNECT_TIMEOUT, _LISTEN_READ_SECONDS), allow_redirects=False,
                                         stream=True)
            with self._kept_open(response):
                if response.status_code == _NO_STREAM:
                    return False
                if response.status_code == _SESSION_GONE and self._session_id is not None:
                    self._lost()
                    return False
                if not succeeded(response) or _media_type(response) != _EVENT_STREAM:
                    raise _Refused(response)
                self._deliver(response, _LISTEN_READ_SECONDS)
        return True

    @contextlib.contextmanager
    def _kept_open(self, response: requests.Response) -> Iterator[requests.Response]:
        """Keep *response* where :meth:`close` finds it while it is read, and close it after."""
        with self._guard:
            self._open_responses.add(response)
        try:
            yield response
        finally:
            with self._guard:
                self._open_responses.discard(response)
            response.close()
