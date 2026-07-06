from __future__ import annotations

import sys
from pathlib import Path

import click

from .scanner import scan_path, Severity
from .probe import run_probe
from .report import render_scan_findings, render_probe_results, write_json_report


@click.group()
@click.version_option(version="0.1.0", prog_name="mcp-rc-audit")
def main():
    """
    mcp-rc-audit: static scanner + live conformance probe for the
    MCP 2026-07-28 stateless migration.
    """


@main.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--fail-on",
    type=click.Choice(["blocker", "warn", "info", "never"]),
    default="blocker",
    help="Exit non-zero if a finding at or above this severity is found. "
    "Use 'never' for report-only mode (e.g. first run on a large repo).",
)
@click.option("--json", "json_out", type=click.Path(path_type=Path), default=None,
              help="Also write findings to a JSON file.")
def scan(path: Path, fail_on: str, json_out: Path | None):
    """Scan a codebase for MCP RC-migration risk patterns."""
    findings = scan_path(path)
    render_scan_findings(findings, path)

    if json_out:
        write_json_report(json_out, findings, path)

    if fail_on == "never":
        return

    threshold = {"blocker": Severity.BLOCKER, "warn": Severity.WARN, "info": Severity.INFO}[fail_on]
    order = [Severity.INFO, Severity.WARN, Severity.BLOCKER]
    if any(order.index(f.severity) >= order.index(threshold) for f in findings):
        sys.exit(1)


@main.command()
@click.argument("url")
def probe(url: str):
    """Send RC-shaped requests to a running MCP server and report how it behaves."""
    results = run_probe(url)
    render_probe_results(results, url)

    from .probe import ProbeOutcome
    if any(r.outcome == ProbeOutcome.FAIL for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
