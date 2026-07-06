"""
Walks a codebase and applies every pattern in scanner.patterns, producing
a flat list of Finding objects that report.py turns into human output.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import fnmatch

from .patterns import PATTERNS, Pattern, Severity

DEFAULT_IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".mypy_cache", ".pytest_cache", "site-packages",
}


@dataclass
class Finding:
    pattern: Pattern
    file: Path
    line_no: int
    line_text: str

    @property
    def severity(self) -> Severity:
        return self.pattern.severity


def _iter_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in DEFAULT_IGNORE_DIRS for part in path.parts):
            continue
        yield path


def _matches_glob(path: Path, globs: tuple) -> bool:
    return any(fnmatch.fnmatch(path.name, g) for g in globs)


def scan_path(root: Path) -> list[Finding]:
    """Scan every file under `root` against all applicable patterns."""
    findings: list[Finding] = []
    files = list(_iter_files(root))

    for pattern in PATTERNS:
        for path in files:
            if not _matches_glob(path, pattern.file_globs):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except (OSError, UnicodeDecodeError):
                continue

            for line_no, line in enumerate(text.splitlines(), start=1):
                if pattern.regex.search(line):
                    findings.append(
                        Finding(
                            pattern=pattern,
                            file=path,
                            line_no=line_no,
                            line_text=line.strip(),
                        )
                    )

            # Some patterns (e.g. the FastMCP() constructor check) span
            # multiple lines / need the whole-file view rather than a
            # single line. Run those against the full text too, reporting
            # against line 1 if only a whole-text match is found and no
            # per-line match already captured it.
            if pattern.id == "PY001":
                whole_match = pattern.regex.search(text)
                if whole_match and not any(
                    f.pattern.id == "PY001" and f.file == path for f in findings
                ):
                    line_no = text[: whole_match.start()].count("\n") + 1
                    findings.append(
                        Finding(
                            pattern=pattern,
                            file=path,
                            line_no=line_no,
                            line_text=whole_match.group(0).splitlines()[0].strip(),
                        )
                    )

    return sorted(findings, key=lambda f: (str(f.file), f.line_no))
