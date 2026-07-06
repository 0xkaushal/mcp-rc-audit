# CLAUDE.md — project context for Claude Code

This file is read automatically by Claude Code. It exists so a fresh
session has full context without needing the conversation history that
produced this codebase.

## What this project is

`mcp-rc-audit` is an open-source CLI that helps MCP server maintainers 
survive the **2026-07-28 MCP spec release**, which removes protocol-level 
sessions (`Mcp-Session-Id`, the `initialize` handshake, sticky routing) in 
favor of a stateless core.

It has two subcommands:
- `mcp-rc-audit scan <path>` — static regex-based scanner over a
  codebase (Python + TS/JS), flags patterns known to break or silently
  reintroduce scaling problems under the new spec.
- `mcp-rc-audit probe <url>` — sends RC-shaped HTTP requests to a
  *running* MCP server and checks whether it degrades gracefully.

## Current state (v0.1, working baseline)

Everything below is implemented, installed, and passing tests as of
this handoff:
- `mcp_rc_audit/scanner/patterns.py` — 8 patterns (TS001, TS002, PY001,
  ANY001–ANY005), each with an id, severity (BLOCKER/WARN/INFO), a
  human message, and a spec/issue reference it's based on.
- `mcp_rc_audit/scanner/code_scanner.py` — walks a directory, applies
  every pattern's regex line-by-line (plus one whole-file pass for
  PY001, which needs multi-line context).
- `mcp_rc_audit/probe/conformance.py` — 3 live HTTP checks using
  `httpx`: `no_session_required`, `meta_protocol_version`,
  `missing_session_header`.
- `mcp_rc_audit/report.py` — rich-based terminal output + JSON export.
- `mcp_rc_audit/cli.py` — click-based CLI, `--fail-on` flag for CI use.
- `examples/vulnerable_server.py` — deliberately broken FastMCP server,
  used as a scan fixture. Running `mcp-rc-audit scan examples/
  --fail-on never` should currently produce exactly 7 findings (2
  blocker, 3 warn, 2 info) — use this as a regression check after any
  scanner change.
- `tests/test_patterns.py` — 3 tests, all passing (`pytest tests/`).

Run `pip install -e ".[dev]"` then `pytest tests/` to confirm the
baseline still holds before making changes.

## Why these specific patterns (don't remove without reading this)

The scanner deliberately does NOT try to catch "any session usage" —
the official SDKs (Python SDK v2, TypeScript SDK) already handle the
mechanical migration (e.g. `stateless_http=True`,
`sessionIdGenerator: undefined`). What's genuinely unaddressed, and
what this tool targets:

1. **In-memory state keyed by session ID** (ANY001) — the exact bug
   class reported in `sooperset/mcp-atlassian#997` (stateless mode
   broke after v0.13.1, "Bad Request: Missing session ID").
2. **Session/auth conflation** (ANY004) — flagged in
   `microsoft/agent-governance-toolkit#2597`, an open RFC where the
   maintainers realized their own session-auth helper needed to be
   reclassified as "application-level" rather than "protocol-level."
   This is a genuinely under-served problem: nobody has tooling that
   helps people see where they've mixed these two concerns.
3. **Deprecated Tasks/Sampling/Roots usage** (ANY003, ANY005) — from
   the actual 2026-07-28 release candidate blog post
   (blog.modelcontextprotocol.io), not guesswork.

If you (Claude Code) are asked to add new patterns, keep this bar: cite
a real GitHub issue, SEP, or the official spec blog — not a generic
"this could theoretically be a problem" pattern. That's what
differentiates this from a generic linter.

## Known gaps / good next tasks, roughly in priority order

1. **TS/JS scanning is regex-only** — real false-positive risk (e.g.
   TS001's regex won't catch `randomUUID` imported under an alias, or
   multi-line arrow functions). An AST-based pass using `ts-morph` or
   similar would be a meaningfully better v2, but don't do this rewrite
   without discussing scope first — it's a bigger dependency footprint
   (Node.js as a runtime dependency for a Python CLI) and needs a
   design decision.
2. **`--fix` mode** for purely mechanical patterns (TS001 in particular
   — rewriting `sessionIdGenerator: () => randomUUID()` to `undefined`
   is close to a pure codemod). PY001 and ANY001 are NOT good `--fix`
   candidates — they need human judgment about where state should live.
3. **GitHub Action wrapper** — thin wrapper around `mcp-rc-audit scan .
   --fail-on blocker --json report.json`, upload report.json as an
   artifact, maybe a PR comment summarizing findings.
4. **Sticky-session detection in the probe** — hit the same URL from
   multiple concurrent connections and diff behavior, to catch cases
   where a server *looks* stateless in a single-request test but
   actually depends on connection affinity under load.

## Things NOT to do without checking first

- Don't rename the PyPI package or the CLI entrypoint without
  confirming — "mcp-rc-audit" vs "statelessly" naming is still an open
  decision.
- Don't treat the 2026-07-28 spec details baked into `patterns.py`
  messages as immutable — it was a **release candidate** at time of
  writing. If the final spec text differs, update the spec_ref/message
  fields, don't just delete the pattern.
- Don't add patterns based on general "MCP best practices" — stay
  scoped to the stateless migration specifically, or this turns into
  an unfocused general-purpose MCP linter and loses its reason to
  exist as a separate project.

## Useful commands

```bash
pip install -e ".[dev]"
pytest tests/ -v
mcp-rc-audit scan examples/ --fail-on never
mcp-rc-audit probe <url>
mcp-rc-audit scan . --json report.json --fail-on warn
```
