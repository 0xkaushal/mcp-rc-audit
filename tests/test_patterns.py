from pathlib import Path

from mcp_rc_audit.scanner import scan_path


def test_scan_finds_expected_patterns_in_example(tmp_path: Path):
    example = Path(__file__).parent.parent / "examples" / "vulnerable_server.py"
    target_dir = tmp_path / "examples"
    target_dir.mkdir()
    (target_dir / "vulnerable_server.py").write_text(example.read_text())

    findings = scan_path(target_dir)
    ids_found = {f.pattern.id for f in findings}

    # ANY001 (in-memory session-keyed dict) must be caught.
    assert "ANY001" in ids_found
    # ANY004 (session_id near bearer/token) must be caught.
    assert "ANY004" in ids_found


def test_clean_file_produces_no_findings(tmp_path: Path):
    clean = tmp_path / "clean_server.py"
    clean.write_text(
        "from fastmcp import FastMCP\n\n"
        "mcp = FastMCP('clean', stateless_http=True)\n\n"
        "@mcp.tool()\n"
        "def add(a: int, b: int) -> int:\n"
        "    return a + b\n"
    )
    findings = scan_path(tmp_path)
    assert findings == []


def test_ts_session_id_generator_pattern(tmp_path: Path):
    ts_file = tmp_path / "server.ts"
    ts_file.write_text(
        "const transport = new NodeStreamableHTTPServerTransport({\n"
        "  sessionIdGenerator: () => randomUUID(),\n"
        "});\n"
    )
    findings = scan_path(tmp_path)
    ids_found = {f.pattern.id for f in findings}
    assert "TS001" in ids_found
