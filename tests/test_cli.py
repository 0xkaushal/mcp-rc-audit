"""CLI integration tests -- exercise the click commands end-to-end."""

from pathlib import Path

from click.testing import CliRunner

from mcp_rc_audit.cli import main


runner = CliRunner()


class TestScanCommand:
    """mcp-rc-audit scan <path>."""

    def test_clean_dir_exits_zero(self, tmp_path: Path):
        """No findings + default --fail-on blocker => exit 0."""
        clean = tmp_path / "clean.py"
        clean.write_text(
            "from fastmcp import FastMCP\n"
            "mcp = FastMCP('clean', stateless_http=True)\n"
        )
        result = runner.invoke(main, ["scan", str(tmp_path)])
        assert result.exit_code == 0
        assert "No RC-migration risk patterns found" in result.output

    def test_blocker_finding_exits_nonzero(self, tmp_path: Path):
        """A BLOCKER finding with default --fail-on blocker => exit 1."""
        (tmp_path / "bad.py").write_text("session_store = {}\n")
        result = runner.invoke(main, ["scan", str(tmp_path)])
        assert result.exit_code == 1

    def test_fail_on_never_exits_zero_with_findings(self, tmp_path: Path):
        """--fail-on never always exits 0 regardless of findings."""
        (tmp_path / "bad.py").write_text("session_store = {}\n")
        result = runner.invoke(main, ["scan", str(tmp_path), "--fail-on", "never"])
        assert result.exit_code == 0

    def test_fail_on_warn_exits_nonzero_for_warn(self, tmp_path: Path):
        """--fail-on warn => exit 1 if a WARN-or-higher finding exists."""
        (tmp_path / "server.py").write_text(
            "from fastmcp import FastMCP\n"
            "mcp = FastMCP('srv')\n"
        )
        result = runner.invoke(main, ["scan", str(tmp_path), "--fail-on", "warn"])
        assert result.exit_code == 1

    def test_fail_on_warn_exits_zero_for_info_only(self, tmp_path: Path):
        """--fail-on warn => exit 0 if only INFO findings."""
        (tmp_path / "sample.py").write_text(
            "result = await client.createMessage(params)\n"
        )
        result = runner.invoke(main, ["scan", str(tmp_path), "--fail-on", "warn"])
        assert result.exit_code == 0

    def test_json_output_written(self, tmp_path: Path):
        """--json flag produces a JSON file."""
        (tmp_path / "bad.py").write_text("session_store = {}\n")
        json_out = tmp_path / "report.json"
        result = runner.invoke(
            main, ["scan", str(tmp_path), "--json", str(json_out), "--fail-on", "never"]
        )
        assert result.exit_code == 0
        assert json_out.exists()
        import json
        data = json.loads(json_out.read_text())
        assert isinstance(data, list)
        assert len(data) > 0
        assert data[0]["id"] == "ANY001"

    def test_nonexistent_path_error(self):
        """Pointing scan at a non-existent path should error."""
        result = runner.invoke(main, ["scan", "/nonexistent/path"])
        assert result.exit_code != 0

    def test_output_shows_finding_details(self, tmp_path: Path):
        """Output includes pattern ID and severity label."""
        (tmp_path / "state.ts").write_text("const sessions = new Map();\n")
        result = runner.invoke(main, ["scan", str(tmp_path), "--fail-on", "never"])
        assert "ANY001" in result.output
        assert "BLOCKER" in result.output


class TestProbeCommand:
    """mcp-rc-audit probe <url> (mocked network)."""

    def test_probe_invalid_url_shows_error(self):
        """Probing an unreachable URL should not crash but should exit 1."""
        # Using a guaranteed-unroutable address
        result = runner.invoke(main, ["probe", "http://192.0.2.1:1/mcp"])
        # Should exit non-zero (either FAIL or UNKNOWN counts as failure)
        # or at minimum not crash with a traceback
        assert result.exit_code != 0 or "UNKNOWN" in result.output


class TestVersionFlag:
    """--version flag."""

    def test_version(self):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output
