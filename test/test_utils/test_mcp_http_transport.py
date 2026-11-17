"""An MCP server at a URL: the profile, the Streamable HTTP transport, and the client over it.

Every server here is on the loopback address, which the transport refuses
until the user has allowed it: the tests that talk to one pass that answer,
``allowed_local={"127.0.0.1"}``, as the tab does after asking.
"""
from __future__ import annotations

import threading
import time

import pytest

from pybreeze.utils.exception.exceptions import McpException
from pybreeze.utils.mcp.mcp_client import McpClient, McpRemoteError
from pybreeze.utils.mcp.mcp_http_transport import (
    SESSION_HEADER, VERSION_HEADER, HttpTransport, McpLocalAddressError, event_data, messages_in,
)
from pybreeze.utils.mcp.mcp_profile import (
    McpServerProfile, discovered_profiles, profile_from_entry, profiles_from_text, profiles_to_text,
)
from pybreeze.utils.mcp.mcp_transport import McpClosed
from test_utils.mcp_http_server import SESSION, FakeHttpMcp

TOKEN = "tok-9d2be41f07"
LOOPBACK = frozenset({"127.0.0.1"})
_WAIT_SECONDS = 10


def _remote(url: str, **more) -> McpServerProfile:
    return McpServerProfile(name="remote", url=url, timeout_seconds=10, **more)


def _until(condition, seconds: float = _WAIT_SECONDS) -> None:
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, "what was waited for did not happen"
        time.sleep(0.02)


@pytest.fixture
def server():
    made = FakeHttpMcp()
    yield made
    made.close()


@pytest.fixture
def streaming():
    made = FakeHttpMcp(streaming=True, listening=True)
    yield made
    made.close()


def _connected(url: str, **more) -> McpClient:
    client = McpClient(_remote(url, **more), "9.9.9", allowed_local=LOOPBACK)
    client.connect()
    return client


# ----------------------------------------------------------------------
# A server at a URL, as a profile
# ----------------------------------------------------------------------

class TestTheProfile:
    def test_a_url_and_its_headers_are_kept_in_the_layout_other_clients_write(self):
        profile = _remote("https://mcp.example/v1", headers={"Authorization": f"Bearer {TOKEN}"})

        entry = profile.to_entry()

        assert entry == {"type": "http", "url": "https://mcp.example/v1",
                         "headers": {"Authorization": f"Bearer {TOKEN}"}, "timeout": 10}
        assert profiles_from_text(profiles_to_text([profile])) == [profile]

    @pytest.mark.parametrize("kind", ["http", "streamable-http", "streamableHttp", None])
    def test_an_entry_another_client_wrote_is_read(self, kind):
        entry = {"url": "http://localhost:3000/mcp"} | ({"type": kind} if kind else {})

        assert profile_from_entry("other", entry).url == "http://localhost:3000/mcp"

    def test_the_older_sse_transport_is_passed_over(self):
        assert profile_from_entry("old", {"type": "sse", "url": "http://localhost:3000/sse"}) is None

    @pytest.mark.parametrize("entry", [
        {"url": "ftp://mcp.example/"}, {"url": "file:///etc/passwd"}, {"url": "mcp.example"},
        {"url": "https://mcp.example/", "headers": {"Bad Name": "x"}},
        {"url": "https://mcp.example/", "headers": {"X-Ok": "line\r\nInjected: yes"}},
    ])
    def test_a_url_or_header_that_cannot_be_sent_is_passed_over(self, entry):
        assert profile_from_entry("bad", entry) is None

    def test_a_server_has_a_command_or_a_url_never_both(self):
        with pytest.raises(McpException):
            McpServerProfile("both", ("server",), url="https://mcp.example/")
        with pytest.raises(McpException):
            McpServerProfile("neither")

    def test_header_values_are_secrets_too(self):
        profile = _remote("https://mcp.example/", headers={"X-Api-Key": TOKEN})

        assert TOKEN in profile.secrets()
        assert profile.is_remote

    @pytest.mark.parametrize(("url", "shown"), [
        ("https://user:pw@mcp.example:8443/v1?key=abc", "https://mcp.example:8443/v1"),
        ("http://[::1]:3000/mcp", "http://[::1]:3000/mcp"),
        ("https://mcp.example", "https://mcp.example"),
    ])
    def test_the_url_is_shown_without_its_credentials_or_query(self, url, shown):
        assert _remote(url).shown_url() == shown

    def test_a_projects_file_may_name_one_and_it_is_trusted_with_nothing(self, tmp_path):
        (tmp_path / ".mcp.json").write_text(
            '{"mcpServers": {"web": {"type": "http", "url": "http://localhost:3000/mcp", '
            '"trustedTools": ["echo"]}}}', encoding="utf-8")

        found = discovered_profiles(tmp_path)

        assert [(profile.url, profile.trusted_tools) for profile in found] == [
            ("http://localhost:3000/mcp", frozenset())]


# ----------------------------------------------------------------------
# Reading what the server sends
# ----------------------------------------------------------------------

class TestEventStreams:
    def test_each_events_data_comes_when_the_event_ends(self):
        chunks = [b": hello\n\nevent: message\nda", b"ta: {\"a\": 1}\n\nid: 2\r\ndata: {\"b\":\r\n",
                  b"data: 2}\r\n\r\n"]

        assert list(event_data(chunks)) == ['{"a": 1}', '{"b":\n2}']

    def test_a_last_event_without_its_blank_line_still_counts(self):
        assert list(event_data([b"data: x"])) == ["x"]

    def test_an_event_without_data_is_nothing(self):
        assert list(event_data([b"event: ping\nid: 3\n\n"])) == []

    @pytest.mark.parametrize("chunks", [[b"data: " + b"x" * 100 + b"\n\n"], [b"x" * 100]])
    def test_an_event_or_a_line_past_the_limit_ends_the_stream(self, chunks):
        with pytest.raises(ValueError):
            list(event_data(chunks, max_bytes=50))

    @pytest.mark.parametrize(("text", "found"), [
        ('{"id": 1}', [{"id": 1}]), ('[{"id": 1}, 2, {"id": 3}]', [{"id": 1}, {"id": 3}]),
        ("not json", []), ("7", []),
    ])
    def test_a_body_holds_one_message_or_a_batch(self, text, found):
        assert messages_in(text) == found


# ----------------------------------------------------------------------
# Reaching the server
# ----------------------------------------------------------------------

class TestWhereItMayConnect:
    def test_a_loopback_server_needs_the_users_yes_and_is_named(self, server):
        client = McpClient(_remote(server.url), "9.9.9")

        with pytest.raises(McpLocalAddressError) as refused:
            client.connect()

        assert (refused.value.host, refused.value.addresses) == ("127.0.0.1", ("127.0.0.1",))
        assert server.requests == []

    def test_with_it_the_server_is_reached(self, server):
        client = _connected(server.url)
        try:
            assert client.server.name == "fake-http"
        finally:
            client.close()

    def test_an_address_that_may_never_be_allowed_is_refused_outright(self):
        client = McpClient(_remote("http://169.254.169.254/mcp"), "9.9.9", allowed_local=frozenset({"169.254.169.254"}))

        with pytest.raises(McpException) as refused:
            client.connect()

        assert not isinstance(refused.value, McpLocalAddressError)

    def test_nothing_is_sent_before_start_or_after_close(self, server):
        transport = HttpTransport(_remote(server.url), lambda _message: None, lambda: None, LOOPBACK)

        with pytest.raises(McpClosed):
            transport.send({"jsonrpc": "2.0", "method": "ping", "id": 1})
        transport.start()
        transport.close()
        with pytest.raises(McpClosed):
            transport.send({"jsonrpc": "2.0", "method": "ping", "id": 1})


class TestTheSession:
    def test_tools_are_listed_and_called(self, server):
        client = _connected(server.url)
        try:
            assert [tool.name for tool in client.list_tools()] == ["echo", "slow", "change"]
            assert client.call_tool("echo", {"text": "over http"}).text == "over http"
        finally:
            client.close()

    def test_the_session_and_the_protocol_revision_go_back_with_every_message(self, server):
        client = _connected(server.url)
        try:
            client.list_tools()
        finally:
            client.close()

        listed = server.seen("tools/list")[0]["headers"]
        assert listed[SESSION_HEADER] == SESSION
        assert listed[VERSION_HEADER] == client.server.protocol_version
        assert VERSION_HEADER not in server.seen("initialize")[0]["headers"]

    def test_the_profiles_headers_go_with_every_message_and_the_protocols_cannot_be_replaced(self):
        server = FakeHttpMcp(token=TOKEN)
        headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "text/plain"}
        try:
            client = _connected(server.url, headers=headers)
            client.list_tools()
            client.close()
        finally:
            server.close()

        for request in server.requests[:-1]:
            assert request["headers"]["Authorization"] == f"Bearer {TOKEN}"
            assert "text/event-stream" in request["headers"]["Accept"]

    def test_closing_ends_the_session_on_the_server(self, server):
        client = _connected(server.url)

        client.close()

        assert server.requests[-1]["body"] == {"method": "DELETE"}
        assert server.requests[-1]["headers"][SESSION_HEADER] == SESSION

    def test_a_session_the_server_ended_closes_the_connection(self, server):
        client = _connected(server.url)
        server.session_open = False
        server.deleted.set()

        with pytest.raises(McpClosed):
            client.list_tools()

        assert client.closed

    def test_a_refusal_fails_the_request_with_its_status_and_never_the_token(self):
        server = FakeHttpMcp(token="the-right-one")
        try:
            client = McpClient(_remote(server.url, headers={"Authorization": f"Bearer {TOKEN}"}), "9.9.9",
                               allowed_local=LOOPBACK)
            with pytest.raises(McpRemoteError) as refused:
                client.connect()
        finally:
            server.close()

        assert "HTTP 401" in str(refused.value)
        assert TOKEN not in str(refused.value)
        assert TOKEN not in str(client.log_tail())

    def test_a_server_that_does_not_answer_fails_the_request_at_once(self):
        server = FakeHttpMcp()
        url = server.url
        server.close()
        client = McpClient(_remote(url), "9.9.9", allowed_local=LOOPBACK)
        started = time.monotonic()

        with pytest.raises(McpRemoteError):
            client.connect()

        assert time.monotonic() - started < _WAIT_SECONDS


class TestStreamedAnswers:
    def test_a_reply_streamed_as_events_arrives_after_what_the_server_said_first(self, streaming):
        heard: list[str] = []
        client = McpClient(_remote(streaming.url), "9.9.9", allowed_local=LOOPBACK)
        client.on_notification = lambda method, _params: heard.append(method)
        try:
            client.connect()
            assert client.call_tool("echo", {"text": "streamed"}).text == "streamed"
        finally:
            client.close()

        assert "notifications/message" in heard

    def test_what_the_server_sends_unasked_comes_on_the_listening_stream(self, streaming):
        heard: list[str] = []
        client = McpClient(_remote(streaming.url), "9.9.9", allowed_local=LOOPBACK)
        client.on_notification = lambda method, _params: heard.append(method)
        try:
            client.connect()
            client.call_tool("change", {})
            _until(lambda: "notifications/tools/list_changed" in heard)
        finally:
            client.close()

    def test_a_slow_call_is_given_up_at_once_when_cancelled(self, streaming):
        client = _connected(streaming.url)
        cancel = threading.Event()
        threading.Timer(0.3, cancel.set).start()
        started = time.monotonic()
        try:
            with pytest.raises(McpException):
                client.call_tool("slow", {"seconds": 5}, cancel)
            assert time.monotonic() - started < 3
        finally:
            client.close()
