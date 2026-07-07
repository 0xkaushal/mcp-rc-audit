"""
Pattern definitions for the MCP 2026-07-28 stateless-migration scanner.

Each Pattern describes one specific way a server's code can depend on
behavior that the 2026-07-28 spec removes, deprecates, or reshapes:

  - protocol-level sessions (Mcp-Session-Id, the initialize handshake)
  - the old blocking Tasks API (superseded by the Tasks extension, SEP-2663)
  - Sampling / Roots as core features (moved to client-direct calls / SEP-2577)
  - in-memory state keyed by session ID (breaks under horizontal scaling)
  - session state entangled with application auth (the "AGT problem" --
    see modelcontextprotocol servers conflating protocol sessions with
    their own login/token state)

Severity guide:
  BLOCKER  - will error/break the moment the server sees an RC-shaped request
  WARN     - works today but silently reintroduces the exact scaling problem
             the spec change was meant to fix
  INFO     - not broken, but worth a conscious decision before July 28
"""

import re
from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    BLOCKER = "BLOCKER"
    WARN = "WARN"
    INFO = "INFO"


class Language(str, Enum):
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    ANY = "any"


@dataclass(frozen=True)
class Pattern:
    id: str
    name: str
    language: Language
    regex: re.Pattern
    severity: Severity
    message: str
    spec_ref: str
    file_globs: tuple


def _rx(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


PATTERNS: list[Pattern] = [
    Pattern(
        id="TS001",
        name="explicit-session-id-generator",
        language=Language.TYPESCRIPT,
        regex=_rx(r"sessionIdGenerator\s*:\s*\(\)\s*=>\s*randomUUID"),
        severity=Severity.BLOCKER,
        message=(
            "Server explicitly mints a session ID via sessionIdGenerator. "
            "The RC removes the protocol-level session and the "
            "Mcp-Session-Id header entirely -- clients built against the "
            "RC will never send one back. Set sessionIdGenerator to "
            "`undefined` (stateless mode) unless you deliberately need "
            "the legacy compatibility path."
        ),
        spec_ref="SEP-2567 (session removal)",
        file_globs=("*.ts", "*.js", "*.mts"),
    ),
    Pattern(
        id="TS002",
        name="manual-session-id-header-handling",
        language=Language.TYPESCRIPT,
        regex=_rx(r"[\"']Mcp-Session-Id[\"']"),
        severity=Severity.WARN,
        message=(
            "Code manually reads/writes the Mcp-Session-Id header. Under "
            "the RC this header is optional and unrecognized by "
            "RC-compliant clients. Confirm this path has a stateless "
            "fallback rather than assuming the header is always present."
        ),
        spec_ref="SEP-2567 (session removal)",
        file_globs=("*.ts", "*.js", "*.mts"),
    ),
    Pattern(
        id="PY001",
        name="fastmcp-stateless-http-not-enabled",
        language=Language.PYTHON,
        regex=_rx(r"FastMCP\((?![^)]*stateless_http\s*=\s*True)[^)]*\)"),
        severity=Severity.WARN,
        message=(
            "FastMCP server instantiated without stateless_http=True. "
            "This isn't necessarily wrong -- some deployments genuinely "
            "need the stateful/legacy path -- but confirm it's a "
            "deliberate choice, not a default nobody revisited."
        ),
        spec_ref="python-sdk v2 migration guide",
        file_globs=("*.py",),
    ),
    Pattern(
        id="ANY001",
        name="in-memory-session-keyed-store",
        language=Language.ANY,
        regex=_rx(
            r"(sessions|session_store|SESSIONS)\s*(:\s*\w+)?\s*=\s*(\{\}|dict\(\)|new Map\(\))"
        ),
        severity=Severity.BLOCKER,
        message=(
            "In-memory dict/Map keyed by session ID. Under horizontal "
            "scaling any pod can now receive any request, so per-process "
            "session dictionaries silently lose data whenever a request "
            "lands on a different instance than the one that created the "
            "entry -- exactly the failure mode reported against "
            "mcp-atlassian's stateless mode. Move this to an explicit "
            "handle (basket_id / job_id) backed by Redis/Postgres, "
            "returned to and threaded back by the model."
        ),
        spec_ref="MCP blog: 'Removing the protocol-level session does not "
        "mean your application has to be stateless'",
        file_globs=("*.py", "*.ts", "*.js"),
    ),
    Pattern(
        id="ANY002",
        name="notifications-initialized-lifecycle-dependency",
        language=Language.ANY,
        regex=_rx(r"notifications/initialized"),
        severity=Severity.WARN,
        message=(
            "Code branches on the notifications/initialized message as a "
            "lifecycle trigger. Under the RC's stateless core this "
            "notification is a legacy/compat-path concept, not a "
            "guaranteed signal -- don't gate required setup logic on it."
        ),
        spec_ref="2026-07-28 release candidate blog",
        file_globs=("*.py", "*.ts", "*.js"),
    ),
    Pattern(
        id="ANY003",
        name="deprecated-tasks-list",
        language=Language.ANY,
        regex=_rx(r"tasks/list"),
        severity=Severity.BLOCKER,
        message=(
            "tasks/list is removed in the RC's Tasks extension (SEP-2663) "
            "-- it can't be scoped safely without sessions. If you shipped "
            "against the 2025-11-25 experimental Tasks API, migrate to "
            "the tasks/get + tasks/update + tasks/cancel polling lifecycle."
        ),
        spec_ref="SEP-2663 (Tasks extension)",
        file_globs=("*.py", "*.ts", "*.js"),
    ),
    Pattern(
        id="ANY004",
        name="conflated-auth-and-protocol-session",
        language=Language.ANY,
        regex=_rx(
            r"(session_id|sessionId).{0,120}(bearer|access_token|oauth|jwt)"
            r"|(bearer|access_token|oauth|jwt).{0,120}(session_id|sessionId)"
        ),
        severity=Severity.INFO,
        message=(
            "session_id and an auth/token concept appear close together. "
            "This is the exact pattern flagged in Microsoft's "
            "agent-governance-toolkit RC migration RFC: protocol-level "
            "MCP sessions and your application's own auth/session state "
            "are two different things, and the RC only removes the "
            "former. Worth a manual read to confirm they're not "
            "conflated -- if your auth relies on the MCP session surviving, "
            "that's now your responsibility to preserve explicitly (see "
            "gitlab-mcp's sealed-token stateless-auth pattern for one "
            "working approach)."
        ),
        spec_ref="microsoft/agent-governance-toolkit#2597",
        file_globs=("*.py", "*.ts", "*.js"),
    ),
    Pattern(
        id="ANY005",
        name="deprecated-sampling-or-roots",
        language=Language.ANY,
        regex=_rx(r"\bcreateMessage\s*\(|\blistRoots\s*\("),
        severity=Severity.INFO,
        message=(
            "Sampling (createMessage) and Roots (listRoots) are marked "
            "deprecated as of 2026-07-28 (SEP-2577), remaining functional "
            "for at least a 12-month deprecation window. No immediate "
            "break, but plan to migrate: sampling -> calling LLM provider "
            "APIs directly; roots -> passing paths via tool parameters, "
            "resource URIs, or configuration."
        ),
        spec_ref="SEP-2577 (deprecated features registry)",
        file_globs=("*.py", "*.ts", "*.js"),
    ),
]
