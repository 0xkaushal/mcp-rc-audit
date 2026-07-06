# mcp-rc-audit

Static scanner + live conformance probe for the **MCP 2026-07-28
stateless migration**.

On July 28, 2026 the Model Context Protocol specification removes the
protocol-level session (`Mcp-Session-Id`, the `initialize` handshake,
sticky routing requirements) in favor of a stateless core where every
request is self-contained. This is good for horizontal scaling, but it
means every MCP server currently in production needs to be checked
against the new model before that date.

The official SDKs already handle most of the *mechanical* migration
(e.g. the TypeScript SDK's `sessionIdGenerator: undefined`, the Python
SDK's `stateless_http=True`). What they don't do is tell you **where
your specific codebase secretly depends on the old session model** —
especially where that dependency is tangled up with your own
authentication/session logic rather than the MCP protocol itself. That
confusion is a real, documented problem (see
[microsoft/agent-governance-toolkit#2597](https://github.com/microsoft/agent-governance-toolkit/issues/2597)),
and real servers are already breaking because of it (see
[sooperset/mcp-atlassian#997](https://github.com/sooperset/mcp-atlassian/issues/997)).

This tool has two parts:

1. **`mcp-rc-audit scan`** — walks a codebase (Python + TS/JS) and
   flags specific patterns that are known to break, or silently
   reintroduce the scaling problem the spec change was meant to fix.
2. **`mcp-rc-audit probe`** — sends RC-shaped requests to a *running*
   MCP server (no session header, `_meta`-carried protocol version) and
   reports whether the server actually degrades gracefully.

## Install

```bash
pip install -e ".[dev]"
```

## Usage

### Scan a codebase

```bash
mcp-rc-audit scan ./my-mcp-server
```

```bash
mcp-rc-audit scan ./my-mcp-server --json report.json --fail-on warn
```

`--fail-on` controls the exit code, so this drops straight into CI:

```yaml
# .github/workflows/mcp-rc-audit.yml
- run: pip install mcp-rc-audit
- run: mcp-rc-audit scan . --fail-on blocker
```

### Probe a running server

```bash
mcp-rc-audit probe https://my-server.example.com/mcp
```

This sends three checks against the live endpoint:

| Check | What it tests |
|---|---|
| `no_session_required` | Calls `tools/list` with no prior `initialize` and no session header — the exact shape an RC-compliant client will use. |
| `meta_protocol_version` | Sends protocol version inside `_meta` instead of relying on a remembered handshake. |
| `missing_session_header` | Confirms the server doesn't hard-fail when `Mcp-Session-Id` is absent or empty. |

## Try it on the bundled example

`examples/vulnerable_server.py` is a deliberately non-migrated FastMCP
server included as a fixture — every finding it produces maps to a real
bug class described above.

```bash
mcp-rc-audit scan examples/ --fail-on never
```

## What it checks for (v0.1)

| ID | Pattern | Severity |
|---|---|---|
| TS001 | Explicit `sessionIdGenerator` still minting UUIDs | BLOCKER |
| TS002 | Manual `Mcp-Session-Id` header handling | WARN |
| PY001 | `FastMCP()` without `stateless_http=True` | WARN |
| ANY001 | In-memory dict/Map keyed by session ID | BLOCKER |
| ANY002 | Lifecycle logic gated on `notifications/initialized` | WARN |
| ANY003 | Deprecated `tasks/list` usage (removed, SEP-2663) | BLOCKER |
| ANY004 | Session ID and auth/token state living together (conflation risk) | INFO |
| ANY005 | Deprecated `createMessage`/`listRoots` (Sampling/Roots, SEP-2577) | INFO |

Full pattern definitions with spec references live in
`mcp_rc_audit/scanner/patterns.py` — it's a plain list, so adding a new
pattern is a ~10-line PR.

## Caveats

- The RC is a **release candidate**, not the shipped spec. Confirm
  final wording against the official MCP specification before
  re-architecting around any single finding here.
- Regex-based scanning has false positives and false negatives by
  nature. Treat findings as "worth a look," not ground truth — this is
  a triage tool, not a certifier.
- The live probe tests *behavior under RC-shaped requests*, not full
  spec conformance. It complements, not replaces, the official SDK
  conformance tests (SEP-1730) once those are published for
  third-party servers.

## Roadmap ideas

- TS/JS AST-based scanning (currently regex) to cut false positives.
- `--fix` mode for the purely mechanical patterns (e.g. rewriting
  `sessionIdGenerator: () => randomUUID()` to `undefined`).
- A GitHub Action wrapper for one-line CI adoption.
- Expand the probe to detect sticky-session assumptions by hitting the
  same URL from multiple concurrent connections and diffing behavior.

## License

MIT
