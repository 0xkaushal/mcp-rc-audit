"""
Intentionally NOT migrated -- this file exists so `mcp-rc-audit scan` has
something real to find. Every pattern below mirrors a bug class described
in the README references (mcp-atlassian's stateless-mode regression,
the Microsoft agent-governance-toolkit RFC, etc.), scaled down to a toy
example.

Run:
    mcp-rc-audit scan examples/
"""

from fastmcp import FastMCP

# PY001: no stateless_http=True -- fine if deliberate, flagged so it's
# a conscious choice rather than an unreviewed default.
mcp = FastMCP("legacy-crystal16-parser")

# ANY001: in-memory dict keyed by session ID. Works on a single instance,
# silently drops data the moment this server runs behind a load balancer
# with more than one replica.
session_store = {}

# ANY004: session ID and bearer token living side by side -- worth a
# manual check that these are actually two different concerns (protocol
# session vs. application auth), not one conflated blob.
auth_sessions = {}


@mcp.tool()
def start_investigation(session_id: str, bearer_token: str) -> dict:
    """Kick off a Crystal16 result investigation, keyed by session_id."""
    auth_sessions[session_id] = {"bearer_token": bearer_token, "step": 0}
    session_store[session_id] = {"raw_files": []}
    return {"status": "started", "session_id": session_id}


@mcp.tool()
def get_investigation_status(session_id: str) -> dict:
    # ANY002: gating logic on notifications/initialized having fired.
    # if last_message == "notifications/initialized": ...
    if session_id not in session_store:
        return {"error": "unknown session -- did you call start_investigation?"}
    return session_store[session_id]


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
