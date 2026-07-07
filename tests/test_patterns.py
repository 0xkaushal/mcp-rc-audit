"""Tests for the scanner pattern engine and report rendering."""

from pathlib import Path

from mcp_rc_audit.probe import ProbeOutcome, ProbeResult
from mcp_rc_audit.report import render_probe_results
from mcp_rc_audit.scanner import scan_path

# ---------- Existing baseline tests ----------


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


# ---------- Individual pattern tests ----------


class TestTS001:
    """TS001: explicit-session-id-generator."""

    def test_arrow_function_form(self, tmp_path: Path):
        (tmp_path / "index.ts").write_text("sessionIdGenerator: () => randomUUID()\n")
        ids = {f.pattern.id for f in scan_path(tmp_path)}
        assert "TS001" in ids

    def test_undefined_value_no_match(self, tmp_path: Path):
        """Setting sessionIdGenerator: undefined is the correct fix -- no finding."""
        (tmp_path / "index.ts").write_text("sessionIdGenerator: undefined\n")
        ids = {f.pattern.id for f in scan_path(tmp_path)}
        assert "TS001" not in ids

    def test_comment_line_still_matches(self, tmp_path: Path):
        """Regex doesn't exclude comments -- acceptable for a warning tool."""
        (tmp_path / "app.js").write_text("// old: sessionIdGenerator: () => randomUUID()\n")
        ids = {f.pattern.id for f in scan_path(tmp_path)}
        assert "TS001" in ids


class TestTS002:
    """TS002: manual Mcp-Session-Id header handling."""

    def test_double_quotes(self, tmp_path: Path):
        (tmp_path / "handler.ts").write_text('const sid = req.headers["Mcp-Session-Id"];\n')
        ids = {f.pattern.id for f in scan_path(tmp_path)}
        assert "TS002" in ids

    def test_single_quotes(self, tmp_path: Path):
        (tmp_path / "handler.js").write_text("const sid = req.headers['Mcp-Session-Id'];\n")
        ids = {f.pattern.id for f in scan_path(tmp_path)}
        assert "TS002" in ids

    def test_unrelated_header_no_match(self, tmp_path: Path):
        (tmp_path / "handler.ts").write_text('const ct = req.headers["Content-Type"];\n')
        ids = {f.pattern.id for f in scan_path(tmp_path)}
        assert "TS002" not in ids


class TestPY001:
    """PY001: FastMCP without stateless_http=True."""

    def test_no_stateless_kwarg(self, tmp_path: Path):
        (tmp_path / "server.py").write_text(
            "from fastmcp import FastMCP\nmcp = FastMCP('my-server')\n"
        )
        ids = {f.pattern.id for f in scan_path(tmp_path)}
        assert "PY001" in ids

    def test_stateless_true_no_match(self, tmp_path: Path):
        (tmp_path / "server.py").write_text(
            "from fastmcp import FastMCP\nmcp = FastMCP('my-server', stateless_http=True)\n"
        )
        ids = {f.pattern.id for f in scan_path(tmp_path)}
        assert "PY001" not in ids

    def test_multiline_constructor(self, tmp_path: Path):
        """PY001 uses whole-file matching for multi-line constructors."""
        (tmp_path / "server.py").write_text(
            "from fastmcp import FastMCP\n"
            "mcp = FastMCP(\n"
            "    'my-server',\n"
            "    host='0.0.0.0',\n"
            ")\n"
        )
        ids = {f.pattern.id for f in scan_path(tmp_path)}
        assert "PY001" in ids


class TestANY001:
    """ANY001: in-memory session-keyed store."""

    def test_python_dict_literal(self, tmp_path: Path):
        (tmp_path / "state.py").write_text("session_store = {}\n")
        ids = {f.pattern.id for f in scan_path(tmp_path)}
        assert "ANY001" in ids

    def test_typescript_map(self, tmp_path: Path):
        (tmp_path / "state.ts").write_text("const sessions = new Map();\n")
        ids = {f.pattern.id for f in scan_path(tmp_path)}
        assert "ANY001" in ids

    def test_annotated_dict(self, tmp_path: Path):
        (tmp_path / "state.py").write_text("sessions: dict = {}\n")
        ids = {f.pattern.id for f in scan_path(tmp_path)}
        assert "ANY001" in ids

    def test_unrelated_dict_no_match(self, tmp_path: Path):
        (tmp_path / "util.py").write_text("cache = {}\n")
        ids = {f.pattern.id for f in scan_path(tmp_path)}
        assert "ANY001" not in ids


class TestANY003:
    """ANY003: deprecated tasks/list usage."""

    def test_tasks_list_string(self, tmp_path: Path):
        (tmp_path / "client.py").write_text('response = await client.call("tasks/list")\n')
        ids = {f.pattern.id for f in scan_path(tmp_path)}
        assert "ANY003" in ids

    def test_tasks_get_no_match(self, tmp_path: Path):
        """tasks/get is the new approach -- should not trigger."""
        (tmp_path / "client.py").write_text(
            'response = await client.call("tasks/get", task_id=tid)\n'
        )
        ids = {f.pattern.id for f in scan_path(tmp_path)}
        assert "ANY003" not in ids


class TestANY005:
    """ANY005: deprecated sampling/roots."""

    def test_create_message(self, tmp_path: Path):
        (tmp_path / "sampler.ts").write_text("const result = await client.createMessage(params);\n")
        ids = {f.pattern.id for f in scan_path(tmp_path)}
        assert "ANY005" in ids

    def test_list_roots(self, tmp_path: Path):
        (tmp_path / "roots.js").write_text("const roots = await client.listRoots();\n")
        ids = {f.pattern.id for f in scan_path(tmp_path)}
        assert "ANY005" in ids


# ---------- Scanner edge cases ----------


class TestScannerEdgeCases:
    """Edge cases for the file-walking / scanning engine."""

    def test_empty_directory(self, tmp_path: Path):
        """An empty directory should return zero findings, not crash."""
        findings = scan_path(tmp_path)
        assert findings == []

    def test_binary_file_skipped(self, tmp_path: Path):
        """Binary files should not crash the scanner."""
        bin_file = tmp_path / "data.py"
        bin_file.write_bytes(b"\x00\x01\x02\x03\x89PNG\r\n" * 50)
        findings = scan_path(tmp_path)
        # Should not raise; result doesn't matter as long as no crash
        assert isinstance(findings, list)

    def test_deeply_nested_file(self, tmp_path: Path):
        """Files deep in the tree should still be scanned."""
        deep = tmp_path / "a" / "b" / "c" / "d"
        deep.mkdir(parents=True)
        (deep / "nested.py").write_text("session_store = {}\n")
        ids = {f.pattern.id for f in scan_path(tmp_path)}
        assert "ANY001" in ids

    def test_node_modules_ignored(self, tmp_path: Path):
        """node_modules should be skipped entirely."""
        nm = tmp_path / "node_modules" / "some-pkg"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("sessionIdGenerator: () => randomUUID()\n")
        findings = scan_path(tmp_path)
        assert findings == []

    def test_venv_ignored(self, tmp_path: Path):
        """.venv directories should be skipped."""
        venv = tmp_path / ".venv" / "lib"
        venv.mkdir(parents=True)
        (venv / "server.py").write_text("session_store = {}\n")
        findings = scan_path(tmp_path)
        assert findings == []

    def test_file_glob_filtering(self, tmp_path: Path):
        """A .txt file should not trigger TS patterns."""
        (tmp_path / "notes.txt").write_text("sessionIdGenerator: () => randomUUID()\n")
        findings = scan_path(tmp_path)
        assert findings == []

    def test_findings_sorted_by_file_and_line(self, tmp_path: Path):
        """Findings must be sorted by (file, line_no)."""
        (tmp_path / "a.py").write_text("session_store = {}\n")
        (tmp_path / "b.py").write_text("sessions = {}\n")
        findings = scan_path(tmp_path)
        files = [str(f.file) for f in findings]
        assert files == sorted(files)

    def test_multiple_findings_same_file(self, tmp_path: Path):
        """Multiple patterns can fire in the same file."""
        (tmp_path / "combo.py").write_text(
            "from fastmcp import FastMCP\nmcp = FastMCP('srv')\nsession_store = {}\n"
        )
        findings = scan_path(tmp_path)
        ids = {f.pattern.id for f in findings}
        assert "PY001" in ids
        assert "ANY001" in ids


# ---------- Report rendering: probe summary line ----------


def _make_result(outcome: ProbeOutcome) -> ProbeResult:
    return ProbeResult(
        check_id="test_check",
        name="test check",
        outcome=outcome,
        detail="detail",
    )


class TestRenderProbeResultsSummary:
    """Verify the summary line printed after the probe table."""

    def _capture(self, results: list[ProbeResult]) -> str:
        """Run render_probe_results and return everything printed to the console."""
        from io import StringIO

        from rich.console import Console

        import mcp_rc_audit.report as report_module

        buf = StringIO()
        original = report_module.console
        report_module.console = Console(file=buf, highlight=False)
        try:
            render_probe_results(results, "http://fake")
        finally:
            report_module.console = original
        return buf.getvalue()

    def test_all_pass_prints_all_checks_passed(self):
        out = self._capture([_make_result(ProbeOutcome.PASS)] * 3)
        assert "All checks passed" in out
        assert "could not complete" not in out
        assert "failed" not in out

    def test_any_fail_prints_failed_count(self):
        results = [
            _make_result(ProbeOutcome.PASS),
            _make_result(ProbeOutcome.FAIL),
            _make_result(ProbeOutcome.FAIL),
        ]
        out = self._capture(results)
        assert "2 check(s) failed" in out
        assert "All checks passed" not in out

    def test_all_unknown_does_not_print_all_checks_passed(self):
        """Regression: all-UNKNOWN results must NOT produce 'All checks passed'."""
        out = self._capture([_make_result(ProbeOutcome.UNKNOWN)] * 3)
        assert "All checks passed" not in out
        assert "could not complete" in out

    def test_mixed_pass_and_unknown_prints_partial_success(self):
        results = [
            _make_result(ProbeOutcome.PASS),
            _make_result(ProbeOutcome.UNKNOWN),
        ]
        out = self._capture(results)
        assert "All reachable checks passed" in out
        assert "could not complete" in out
        assert "All checks passed" not in out  # must not use the unqualified wording

    def test_fail_takes_priority_over_unknown(self):
        results = [
            _make_result(ProbeOutcome.FAIL),
            _make_result(ProbeOutcome.UNKNOWN),
        ]
        out = self._capture(results)
        assert "failed" in out
        assert "All checks passed" not in out
