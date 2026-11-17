# 0013. MCP servers at a URL, reached like any other request, local ones after a question

- **Status**: Accepted
- **Date**: 2026-11-16
- **Code**: `pybreeze/utils/mcp/mcp_http_transport.py`, `mcp_profile.py` (`url`, `headers`),
  `mcp_client.py`, `pybreeze/pybreeze_ui/mcp_gui/` (`mcp_client_gui.py`, `mcp_profile_dialog.py`),
  `pybreeze/pybreeze_ui/local_endpoint.py`; `test_mcp_http_transport.py`, `test_mcp_client_gui.py`,
  `test_utils/mcp_http_server.py`

## Context

[0011](0011-mcp-client.md) offered the standard transport only and left the protocol's HTTP
transport open: most servers of that kind run on the same machine, and the project's rule for
outbound requests refused loopback and private addresses. [U-20261115-07](../updates/2026-11.md)
then decided that rule for the AI panels: such an address is allowed after a question that names
it. The owner asked for the HTTP transport on 2026-11-16.

## Decision

1. **Streamable HTTP, revision 2025-06-18.** A profile has either a command or a URL. Each message is
   a `POST`; a reply comes as one JSON body or as server-sent events; the session the server names
   (`Mcp-Session-Id`) and the revision agreed on (`MCP-Protocol-Version`) go back with every
   message; a `GET` stream carries what the server sends unasked, when it offers one; closing sends
   `DELETE`. The older SSE transport (`"type": "sse"`) is not spoken, and such an entry is passed
   over.
2. **Like every other request.** The URL is checked by `validate_url` and every request goes through
   `public_session()`: the address is checked again as the connection is made, and redirects are
   not followed.
3. **Local addresses after a question, as for the AI panels.** A host on this machine or a private
   network is refused with `McpLocalAddressError`, which names it; the tab asks
   (`LocalEndpointGate`, its own words: tool calls, their arguments and the headers go there), and on
   a yes connects with exactly those addresses allowed, for as long as the tab is open. Link-local,
   CGNAT and the other addresses that may never be allowed are refused outright.
4. **Headers are the profile's secrets.** A token goes in the profile's request headers, which are
   kept with the environment values (the file only the owner can read, shown as dots, taken out of
   every log, error and exported session). The protocol's own headers cannot be replaced by them. A
   URL is shown and exported without its user, password or query (`shown_url()`).
5. **One thread a message.** Each `POST` runs on a thread of its own, so a reply streamed for minutes
   never holds up a cancellation, and a request that cannot be sent is answered in its place with a
   JSON-RPC error, which fails it at once instead of after its time limit.

## Alternatives considered

- **Loopback without asking.** The servers are mostly local, but a project's `.mcp.json` can name
  a URL as well as a command, and a local address can be a service that was never meant to receive
  tool calls. The question costs one click per tab.
- **The older SSE transport.** Superseded by Streamable HTTP in the protocol, and two transports for
  the same thing double what has to be checked.
- **`iter_content` for event streams.** It waits for a whole chunk, and a stream that sent one short
  event and then waited held it back; the body is read as it arrives (`read1`).

## Consequences

- `McpClient` picks the transport from the profile; a transport given to it still wins.
- The servers file has `type`, `url` and `headers` beside `command`, `args`, `env`, in the layout
  other clients write.
- A changed list (`list_changed`) reaches the tab over the `GET` stream as it does over standard
  output.
