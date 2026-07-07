"""
Sends RC-shaped requests to a *running* MCP server over Streamable HTTP
and reports whether it degrades gracefully -- i.e. whether it actually
behaves the way an RC-compliant client will expect on and after
2026-07-28, rather than assuming a session that will never arrive.

This deliberately does not require the target server to already speak
the final spec. Every check is phrased as "what happens when a
stateless-shaped request arrives", which is exactly what will start
happening in production once RC-compliant clients roll out, regardless
of whether the server itself has been updated yet.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum

import httpx


class ProbeOutcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"  # network error, non-MCP endpoint, etc.


@dataclass
class ProbeResult:
    check_id: str
    name: str
    outcome: ProbeOutcome
    detail: str


def _jsonrpc(method: str, params: dict | None = None, meta: dict | None = None) -> dict:
    body: dict = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": method,
        "params": params or {},
    }
    if meta:
        body["params"].setdefault("_meta", {}).update(meta)
    return body


def _post(client: httpx.Client, url: str, payload: dict, headers: dict | None = None):
    all_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if headers:
        all_headers.update(headers)
    return client.post(url, json=payload, headers=all_headers)


def check_no_session_required(client: httpx.Client, url: str) -> ProbeResult:
    """
    RC clients will call tools/list without ever having sent an
    initialize handshake and without an Mcp-Session-Id header. A server
    that hard-requires a prior session will reject this -- the exact
    failure mode reported against mcp-atlassian's stateless mode.
    """
    try:
        resp = _post(client, url, _jsonrpc("tools/list"))
    except httpx.HTTPError as exc:
        return ProbeResult(
            "no_session_required",
            "tools/list without prior session",
            ProbeOutcome.UNKNOWN,
            f"Request failed: {exc}",
        )

    if resp.status_code == 400 and "session" in resp.text.lower():
        return ProbeResult(
            "no_session_required",
            "tools/list without prior session",
            ProbeOutcome.FAIL,
            f"Server returned 400 referencing session state: {resp.text[:200]!r}. "
            "This will break for RC-compliant clients that never send a "
            "session header.",
        )
    if resp.status_code >= 500:
        return ProbeResult(
            "no_session_required",
            "tools/list without prior session",
            ProbeOutcome.FAIL,
            f"Server returned {resp.status_code} instead of a JSON-RPC error or valid response.",
        )
    return ProbeResult(
        "no_session_required",
        "tools/list without prior session",
        ProbeOutcome.PASS,
        f"Server responded with {resp.status_code} without demanding a session.",
    )


def check_meta_protocol_version(client: httpx.Client, url: str) -> ProbeResult:
    """
    RC clients send protocol version and client info inside a per-request
    _meta object rather than relying on a remembered initialize handshake.
    A server that only reads protocolVersion from the old initialize
    payload will silently ignore or mishandle this.
    """
    try:
        resp = _post(
            client,
            url,
            _jsonrpc("tools/list", meta={"protocolVersion": "2026-07-28"}),
        )
    except httpx.HTTPError as exc:
        return ProbeResult(
            "meta_protocol_version",
            "_meta.protocolVersion on a bare request",
            ProbeOutcome.UNKNOWN,
            f"Request failed: {exc}",
        )

    if resp.status_code >= 500:
        return ProbeResult(
            "meta_protocol_version",
            "_meta.protocolVersion on a bare request",
            ProbeOutcome.FAIL,
            f"Server errored ({resp.status_code}) on a _meta-bearing request "
            "instead of handling or ignoring the unfamiliar field.",
        )
    return ProbeResult(
        "meta_protocol_version",
        "_meta.protocolVersion on a bare request",
        ProbeOutcome.PASS,
        f"Server responded with {resp.status_code}; did not crash on _meta.",
    )


def check_survives_missing_session_header(client: httpx.Client, url: str) -> ProbeResult:
    """
    Explicitly omit Mcp-Session-Id (some servers key auth/middleware off
    its mere presence, independent of the tools/list check above).
    """
    try:
        resp = _post(
            client,
            url,
            _jsonrpc("ping"),
            headers={"Mcp-Session-Id": ""},
        )
    except httpx.HTTPError as exc:
        return ProbeResult(
            "missing_session_header",
            "empty Mcp-Session-Id header",
            ProbeOutcome.UNKNOWN,
            f"Request failed: {exc}",
        )

    if resp.status_code in (400, 404) and "session" in resp.text.lower():
        return ProbeResult(
            "missing_session_header",
            "empty Mcp-Session-Id header",
            ProbeOutcome.FAIL,
            f"Server treats an absent/empty session header as fatal "
            f"({resp.status_code}): {resp.text[:200]!r}",
        )
    return ProbeResult(
        "missing_session_header",
        "empty Mcp-Session-Id header",
        ProbeOutcome.PASS,
        f"Server responded with {resp.status_code}.",
    )


ALL_CHECKS = [
    check_no_session_required,
    check_meta_protocol_version,
    check_survives_missing_session_header,
]


def run_probe(url: str, timeout: float = 10.0) -> list[ProbeResult]:
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        return [check(client, url) for check in ALL_CHECKS]
