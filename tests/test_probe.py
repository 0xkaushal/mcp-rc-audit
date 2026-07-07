"""Tests for the live probe module (mocked HTTP, no real server needed)."""

from unittest.mock import patch, MagicMock

import httpx

from mcp_rc_audit.probe.conformance import (
    check_no_session_required,
    check_meta_protocol_version,
    check_survives_missing_session_header,
    run_probe,
    ProbeOutcome,
)


def _mock_response(status_code: int = 200, text: str = "{}"):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    return resp


class TestCheckNoSessionRequired:
    """check_no_session_required probe."""

    def test_pass_on_200(self):
        client = MagicMock()
        client.post.return_value = _mock_response(200, '{"result": {}}')
        result = check_no_session_required(client, "http://localhost:8000/mcp")
        assert result.outcome == ProbeOutcome.PASS
        assert result.check_id == "no_session_required"

    def test_fail_on_400_with_session_mention(self):
        client = MagicMock()
        client.post.return_value = _mock_response(
            400, '{"error": "Missing session ID"}'
        )
        result = check_no_session_required(client, "http://localhost:8000/mcp")
        assert result.outcome == ProbeOutcome.FAIL

    def test_fail_on_500(self):
        client = MagicMock()
        client.post.return_value = _mock_response(500, "Internal Server Error")
        result = check_no_session_required(client, "http://localhost:8000/mcp")
        assert result.outcome == ProbeOutcome.FAIL

    def test_pass_on_400_without_session_mention(self):
        """400 that doesn't mention 'session' isn't necessarily a session problem."""
        client = MagicMock()
        client.post.return_value = _mock_response(
            400, '{"error": "Invalid JSON-RPC request"}'
        )
        result = check_no_session_required(client, "http://localhost:8000/mcp")
        assert result.outcome == ProbeOutcome.PASS

    def test_unknown_on_network_error(self):
        client = MagicMock()
        client.post.side_effect = httpx.ConnectError("Connection refused")
        result = check_no_session_required(client, "http://localhost:8000/mcp")
        assert result.outcome == ProbeOutcome.UNKNOWN


class TestCheckMetaProtocolVersion:
    """check_meta_protocol_version probe."""

    def test_pass_on_200(self):
        client = MagicMock()
        client.post.return_value = _mock_response(200)
        result = check_meta_protocol_version(client, "http://localhost:8000/mcp")
        assert result.outcome == ProbeOutcome.PASS

    def test_fail_on_500(self):
        client = MagicMock()
        client.post.return_value = _mock_response(500, "unrecognized field _meta")
        result = check_meta_protocol_version(client, "http://localhost:8000/mcp")
        assert result.outcome == ProbeOutcome.FAIL

    def test_pass_on_400(self):
        """A 400 (non-5xx) means the server parsed it but rejected it -- not a crash."""
        client = MagicMock()
        client.post.return_value = _mock_response(400, "bad request")
        result = check_meta_protocol_version(client, "http://localhost:8000/mcp")
        assert result.outcome == ProbeOutcome.PASS

    def test_unknown_on_timeout(self):
        client = MagicMock()
        client.post.side_effect = httpx.ReadTimeout("timed out")
        result = check_meta_protocol_version(client, "http://localhost:8000/mcp")
        assert result.outcome == ProbeOutcome.UNKNOWN


class TestCheckSurvivesMissingSessionHeader:
    """check_survives_missing_session_header probe."""

    def test_pass_on_200(self):
        client = MagicMock()
        client.post.return_value = _mock_response(200)
        result = check_survives_missing_session_header(client, "http://localhost:8000/mcp")
        assert result.outcome == ProbeOutcome.PASS

    def test_fail_on_400_session_mention(self):
        client = MagicMock()
        client.post.return_value = _mock_response(
            400, "Invalid session: no active session found"
        )
        result = check_survives_missing_session_header(client, "http://localhost:8000/mcp")
        assert result.outcome == ProbeOutcome.FAIL

    def test_fail_on_404_session_mention(self):
        client = MagicMock()
        client.post.return_value = _mock_response(
            404, "Session not found"
        )
        result = check_survives_missing_session_header(client, "http://localhost:8000/mcp")
        assert result.outcome == ProbeOutcome.FAIL

    def test_pass_on_404_no_session_mention(self):
        """404 without 'session' in body is just a routing issue, not a session failure."""
        client = MagicMock()
        client.post.return_value = _mock_response(404, "Not Found")
        result = check_survives_missing_session_header(client, "http://localhost:8000/mcp")
        assert result.outcome == ProbeOutcome.PASS

    def test_unknown_on_network_error(self):
        client = MagicMock()
        client.post.side_effect = httpx.ConnectError("refused")
        result = check_survives_missing_session_header(client, "http://localhost:8000/mcp")
        assert result.outcome == ProbeOutcome.UNKNOWN


class TestRunProbe:
    """Integration: run_probe runs all checks and returns results."""

    @patch("mcp_rc_audit.probe.conformance.httpx.Client")
    def test_returns_three_results(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = _mock_response(200)
        mock_client_cls.return_value = mock_client

        results = run_probe("http://localhost:8000/mcp")
        assert len(results) == 3
        assert all(r.outcome == ProbeOutcome.PASS for r in results)

    @patch("mcp_rc_audit.probe.conformance.httpx.Client")
    def test_mixed_outcomes(self, mock_client_cls):
        """Different checks can produce different outcomes."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        # First call (no_session_required): 400 + session mention = FAIL
        # Second call (meta_protocol_version): 200 = PASS
        # Third call (missing_session_header): 200 = PASS
        mock_client.post.side_effect = [
            _mock_response(400, "Missing session ID"),
            _mock_response(200),
            _mock_response(200),
        ]
        mock_client_cls.return_value = mock_client

        results = run_probe("http://localhost:8000/mcp")
        assert results[0].outcome == ProbeOutcome.FAIL
        assert results[1].outcome == ProbeOutcome.PASS
        assert results[2].outcome == ProbeOutcome.PASS
