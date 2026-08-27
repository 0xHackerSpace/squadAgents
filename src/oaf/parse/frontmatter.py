"""Splitting a Markdown file into YAML frontmatter and body.

The spec puts machine-readable metadata in frontmatter and human-readable
instructions in the body, so this split is the entry point for AGENTS.md,
SKILL.md and any other document the format defines.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..errors import ParseError

DELIMITER = "---"


@dataclass(frozen=True)
class Frontmatter:
    """The result of splitting a document."""

    data: dict[str, Any]
    body: str
    #: 1-indexed line where the body begins, so diagnostics can point at it.
    body_line: int
    #: 1-indexed line where the frontmatter block begins.
    front_line: int


def split_frontmatter(text: str, *, path: Path | None = None) -> Frontmatter:
    """Split `text` into its YAML frontmatter mapping and Markdown body.

    A document with no frontmatter is not an error here — SKILL.md bodies and
    plain instruction files are legitimate — it simply yields an empty mapping.
    Malformed YAML, or an opened block that is never closed, is an error.
    """
    # A UTF-8 BOM before the opening `---` would otherwise hide the delimiter.
    if text.startswith("﻿"):
        text = text[1:]

    lines = text.splitlines()
    if not lines or lines[0].strip() != DELIMITER:
        return Frontmatter(data={}, body=text, body_line=1, front_line=0)

    closing = None
    for index in range(1, len(lines)):
        if lines[index].strip() == DELIMITER:
            closing = index
            break
    if closing is None:
        raise ParseError(
            "frontmatter block opened with '---' but never closed", path=path, line=1
        )

    raw = "\n".join(lines[1:closing])
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        line = _yaml_error_line(exc, offset=1)
        raise ParseError(f"invalid YAML in frontmatter: {exc}", path=path, line=line) from exc

    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ParseError(
            f"frontmatter must be a YAML mapping, got {type(data).__name__}",
            path=path,
            line=2,
        )

    body = "\n".join(lines[closing + 1 :])
    return Frontmatter(data=data, body=body, body_line=closing + 2, front_line=2)


def _yaml_error_line(exc: yaml.YAMLError, *, offset: int = 0) -> int | None:
    mark = getattr(exc, "problem_mark", None)
    return None if mark is None else mark.line + 1 + offset


def read_text(path: Path) -> str:
    """Read a file as UTF-8, reporting an unreadable file as a ParseError."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ParseError("file not found", path=path) from exc
    except UnicodeDecodeError as exc:
        raise ParseError(f"file is not valid UTF-8: {exc}", path=path) from exc


def load_yaml_file(path: Path) -> dict[str, Any]:
    """Load a standalone YAML file (config.yaml, PACKAGE.yaml) as a mapping."""
    try:
        data = yaml.safe_load(read_text(path))
    except yaml.YAMLError as exc:
        raise ParseError(f"invalid YAML: {exc}", path=path, line=_yaml_error_line(exc)) from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ParseError(f"expected a YAML mapping, got {type(data).__name__}", path=path)
    return data
