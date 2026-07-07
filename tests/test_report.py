"""Tests for the report rendering module."""

import json
from pathlib import Path

from mcp_rc_audit.report import render_scan_findings, render_probe_results, write_json_report
from mcp_rc_audit.scanner import Finding, Severity
from mcp_rc_audit.scanner.patterns import PATTERNS, Pattern
from mcp_rc_audit.probe import ProbeResult, ProbeOutcome


def _make_finding(pattern_id: str = "ANY001", file_name: str = "test.py", line_no: int = 1):
    pattern = next(p for p in PATTERNS if p.id == pattern_id)
    return Finding(
        pattern=pattern,
        file=Path("/project") / file_name,
        line_no=line_no,
        line_text="session_store = {}",
    )


class TestWriteJsonReport:
    """write_json_report serialization."""

    def test_creates_valid_json(self, tmp_path: Path):
        findings = [_make_finding()]
        out = tmp_path / "report.json"
        write_json_report(out, findings, Path("/project"))
        data = json.loads(out.read_text())
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == "ANY001"
        assert data[0]["severity"] == "BLOCKER"
        assert data[0]["line"] == 1

    def test_empty_findings_writes_empty_list(self, tmp_path: Path):
        out = tmp_path / "report.json"
        write_json_report(out, [], Path("/project"))
        data = json.loads(out.read_text())
        assert data == []

    def test_relative_path_in_output(self, tmp_path: Path):
        root = Path("/project")
        finding = Finding(
            pattern=PATTERNS[0],
            file=Path("/project/src/server.ts"),
            line_no=10,
            line_text="sessionIdGenerator: () => randomUUID()",
        )
        out = tmp_path / "report.json"
        write_json_report(out, [finding], root)
        data = json.loads(out.read_text())
        assert data[0]["file"] == "src/server.ts"


class TestRenderScanFindings:
    """render_scan_findings console output (smoke test: no crash)."""

    def test_no_findings_no_crash(self, capsys):
        render_scan_findings([], Path("/project"))
        # Just verifying no exception; rich output goes to its own console

    def test_with_findings_no_crash(self):
        findings = [_make_finding(), _make_finding("PY001", "server.py", 5)]
        render_scan_findings(findings, Path("/project"))


class TestRenderProbeResults:
    """render_probe_results console output (smoke test: no crash)."""

    def test_all_pass(self):
        results = [
            ProbeResult("check1", "Test check", ProbeOutcome.PASS, "OK"),
            ProbeResult("check2", "Test check 2", ProbeOutcome.PASS, "OK"),
        ]
        render_probe_results(results, "http://localhost:8000/mcp")

    def test_mixed_outcomes(self):
        results = [
            ProbeResult("check1", "Test check", ProbeOutcome.PASS, "OK"),
            ProbeResult("check2", "Test check 2", ProbeOutcome.FAIL, "broken"),
            ProbeResult("check3", "Test check 3", ProbeOutcome.UNKNOWN, "timeout"),
        ]
        render_probe_results(results, "http://localhost:8000/mcp")
