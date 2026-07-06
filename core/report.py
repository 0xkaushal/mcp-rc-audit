from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .scanner import Finding, Severity
from .probe import ProbeResult, ProbeOutcome

console = Console()

_SEVERITY_STYLE = {
    Severity.BLOCKER: "bold red",
    Severity.WARN: "bold yellow",
    Severity.INFO: "cyan",
}

_OUTCOME_STYLE = {
    ProbeOutcome.PASS: "bold green",
    ProbeOutcome.FAIL: "bold red",
    ProbeOutcome.UNKNOWN: "dim",
}


def render_scan_findings(findings: list[Finding], root: Path) -> None:
    if not findings:
        console.print(
            "[bold green]No RC-migration risk patterns found.[/bold green] "
            "This isn't a compliance guarantee -- pair it with the live "
            "probe against a running instance."
        )
        return

    blockers = [f for f in findings if f.severity == Severity.BLOCKER]
    warns = [f for f in findings if f.severity == Severity.WARN]
    infos = [f for f in findings if f.severity == Severity.INFO]

    console.print(
        f"\n[bold]{len(findings)} finding(s):[/bold] "
        f"[red]{len(blockers)} blocker(s)[/red], "
        f"[yellow]{len(warns)} warning(s)[/yellow], "
        f"[cyan]{len(infos)} info[/cyan]\n"
    )

    for finding in findings:
        rel = finding.file.relative_to(root) if root in finding.file.parents else finding.file
        style = _SEVERITY_STYLE[finding.severity]
        console.print(
            f"[{style}]{finding.severity.value}[/{style}] "
            f"[bold]{finding.pattern.id}[/bold] {finding.pattern.name}"
        )
        console.print(f"  {rel}:{finding.line_no}")
        console.print(f"  [dim]{finding.line_text}[/dim]")
        console.print(f"  {finding.pattern.message}")
        console.print(f"  [dim]Spec ref: {finding.pattern.spec_ref}[/dim]\n")


def render_probe_results(results: list[ProbeResult], url: str) -> None:
    table = Table(title=f"RC conformance probe: {url}")
    table.add_column("Check")
    table.add_column("Outcome")
    table.add_column("Detail")

    for r in results:
        style = _OUTCOME_STYLE[r.outcome]
        table.add_row(r.name, f"[{style}]{r.outcome.value}[/{style}]", r.detail)

    console.print(table)

    failed = [r for r in results if r.outcome == ProbeOutcome.FAIL]
    if failed:
        console.print(
            f"\n[bold red]{len(failed)} check(s) failed.[/bold red] "
            "This server will likely break for RC-compliant clients "
            "before the July 28, 2026 deadline unless addressed."
        )
    else:
        console.print("\n[bold green]All checks passed.[/bold green]")


def write_json_report(path: Path, findings: list[Finding], root: Path) -> None:
    data = [
        {
            "id": f.pattern.id,
            "name": f.pattern.name,
            "severity": f.severity.value,
            "file": str(f.file.relative_to(root) if root in f.file.parents else f.file),
            "line": f.line_no,
            "line_text": f.line_text,
            "message": f.pattern.message,
            "spec_ref": f.pattern.spec_ref,
        }
        for f in findings
    ]
    path.write_text(json.dumps(data, indent=2))
    console.print(f"[dim]JSON report written to {path}[/dim]")
