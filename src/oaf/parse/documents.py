"""Turning files on disk into typed documents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..errors import ParseError
from ..models.agent import AgentDocument, AgentManifest
from ..models.mcp import ActiveMcp, McpConfig
from ..models.package import PackageManifest
from ..models.skill import SkillDocument, SkillManifest
from .frontmatter import load_yaml_file, read_text, split_frontmatter

AGENTS_MD = "AGENTS.md"
SKILL_MD = "SKILL.md"
PACKAGE_YAML = "PACKAGE.yaml"
ACTIVE_MCP_JSON = "ActiveMCP.json"
MCP_CONFIG_YAML = "config.yaml"


def _validation_message(exc: ValidationError) -> str:
    """Render pydantic's errors as one line per offending field."""
    parts = []
    for error in exc.errors():
        location = ".".join(str(p) for p in error["loc"]) or "<root>"
        parts.append(f"{location}: {error['msg']}")
    return "; ".join(parts)


def parse_agents_md(path: Path) -> AgentDocument:
    """Parse an AGENTS.md file into a manifest plus its instruction body."""
    front = split_frontmatter(read_text(path), path=path)
    if not front.data:
        raise ParseError(
            f"{AGENTS_MD} requires YAML frontmatter with the identity and metadata fields",
            path=path,
            line=1,
        )
    try:
        manifest = AgentManifest.model_validate(front.data)
    except ValidationError as exc:
        raise ParseError(_validation_message(exc), path=path, line=front.front_line) from exc
    return AgentDocument(manifest=manifest, body=front.body, body_line=front.body_line)


def parse_skill_md(path: Path) -> SkillDocument:
    """Parse a SKILL.md file and inventory its sibling resource directories.

    AgentSkills.io requires `name` and `description` in frontmatter, but several
    skills published with the reference agents have no frontmatter at all. Rather
    than reject them, the manifest is inferred from the directory name and the
    body's opening prose; `frontmatter_present` records that this happened so the
    validator can report it.
    """
    skill_dir = path.parent
    front = split_frontmatter(read_text(path), path=path)
    present = bool(front.data)

    if present:
        try:
            manifest = SkillManifest.model_validate(front.data)
        except ValidationError as exc:
            raise ParseError(_validation_message(exc), path=path, line=front.front_line) from exc
    else:
        manifest = SkillManifest(
            name=skill_dir.name,
            description=_infer_description(front.body) or f"Skill {skill_dir.name}",
        )

    return SkillDocument(
        manifest=manifest,
        body=front.body,
        frontmatter_present=present,
        resources=_list_files(skill_dir / "resources"),
        scripts=_list_files(skill_dir / "scripts"),
        assets=_list_files(skill_dir / "assets"),
    )


def _infer_description(body: str) -> str | None:
    """The first non-heading, non-empty line of a body, used as a description."""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(("#", ">", "-", "*", "|", "`")):
            return stripped
    return None


def parse_active_mcp(path: Path) -> ActiveMcp:
    """Parse an ActiveMCP.json tool-subset file."""
    try:
        data: Any = json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        raise ParseError(f"invalid JSON: {exc.msg}", path=path, line=exc.lineno) from exc
    if not isinstance(data, dict):
        raise ParseError(f"expected a JSON object, got {type(data).__name__}", path=path)
    try:
        return ActiveMcp.model_validate(data)
    except ValidationError as exc:
        raise ParseError(_validation_message(exc), path=path) from exc


def parse_mcp_config(path: Path) -> McpConfig:
    """Parse an MCP server config.yaml."""
    try:
        return McpConfig.model_validate(load_yaml_file(path))
    except ValidationError as exc:
        raise ParseError(_validation_message(exc), path=path) from exc


def parse_package_manifest(path: Path) -> PackageManifest:
    """Parse a PACKAGE.yaml package manifest."""
    try:
        return PackageManifest.model_validate(load_yaml_file(path))
    except ValidationError as exc:
        raise ParseError(_validation_message(exc), path=path) from exc


def _list_files(directory: Path) -> list[str]:
    """Relative paths of every file under `directory`, sorted, or [] if absent."""
    if not directory.is_dir():
        return []
    return sorted(
        str(p.relative_to(directory))
        for p in directory.rglob("*")
        if p.is_file()
    )
