"""Error and diagnostic types for the OAF harness.

The spec's "Validation (Informative)" section states that validation is
implementation-defined: harnesses decide what to enforce.  This module draws the
line the harness uses everywhere: a *hard failure* (raise) means the document
could not be turned into a model at all; anything else is a *diagnostic* that
gets collected and reported, so a single run surfaces every problem in a file
rather than only the first one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class OafError(Exception):
    """Base class for every error this package raises."""


class ParseError(OafError):
    """The file could not be parsed at all (bad YAML, missing frontmatter)."""

    def __init__(self, message: str, path: Path | None = None, line: int | None = None):
        self.path = path
        self.line = line
        super().__init__(_where(message, path, line))


class HarnessError(OafError):
    """The runtime could not build or execute an agent."""


def _where(message: str, path: Path | None, line: int | None) -> str:
    location = ""
    if path is not None:
        location = str(path)
        if line is not None:
            location = f"{location}:{line}"
    return f"{location}: {message}" if location else message


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class Diagnostic:
    """One validation finding, addressed to a specific place in a specific file."""

    severity: Severity
    code: str
    message: str
    path: Path | None = None
    line: int | None = None
    field: str | None = None
    hint: str | None = None

    def format(self, *, relative_to: Path | None = None) -> str:
        path = self.path
        if path is not None and relative_to is not None:
            try:
                path = path.relative_to(relative_to)
            except ValueError:
                pass
        head = _where(f"{self.severity.value}[{self.code}]", path, self.line)
        parts = [head, self.message]
        if self.field:
            parts.insert(1, f"({self.field})")
        line = " ".join(parts)
        if self.hint:
            line = f"{line}\n    hint: {self.hint}"
        return line


@dataclass
class DiagnosticBag:
    """Collects diagnostics so one pass reports every problem, not just the first."""

    items: list[Diagnostic] = field(default_factory=list)

    def add(self, diagnostic: Diagnostic) -> None:
        self.items.append(diagnostic)

    def error(self, code: str, message: str, **kw) -> None:
        self.add(Diagnostic(Severity.ERROR, code, message, **kw))

    def warning(self, code: str, message: str, **kw) -> None:
        self.add(Diagnostic(Severity.WARNING, code, message, **kw))

    def info(self, code: str, message: str, **kw) -> None:
        self.add(Diagnostic(Severity.INFO, code, message, **kw))

    def extend(self, other: "DiagnosticBag | list[Diagnostic]") -> None:
        self.items.extend(other.items if isinstance(other, DiagnosticBag) else other)

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.items if d.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.items if d.severity is Severity.WARNING]

    @property
    def ok(self) -> bool:
        """True when nothing blocking was found. Warnings do not fail a run."""
        return not self.errors

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self):
        return iter(self.items)
