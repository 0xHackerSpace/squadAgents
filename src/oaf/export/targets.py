"""Exporting an OAF agent to the harness-native formats the spec names.

The spec's Export Compatibility table lists four targets and their destinations,
then says "Export procedures and tooling specifics are implementation-defined".
These are this harness's procedures.

Every exporter takes a `ResolvedAgent` and a destination directory and returns
the paths it wrote, so the CLI can report them and tests can assert on them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..resolve import ResolvedAgent
from ..runtime.models import resolve_model
from ..runtime.prompt import build_system_prompt


@dataclass
class ExportResult:
    """What an export wrote and what it could not carry across."""

    target: str
    destination: Path
    files: list[Path] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _write(path: Path, content: str, result: ExportResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    result.files.append(path)


def _frontmatter(data: dict, body: str) -> str:
    front = yaml.safe_dump(data, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{front}\n---\n\n{body.strip()}\n"


def export_claude_code(agent: ResolvedAgent, destination: Path) -> ExportResult:
    """Write `<dest>/<vendorKey>/<agentKey>/SKILL.md`, plus each local skill.

    Claude Code's skill frontmatter carries only `name`, `description` and
    `allowed-tools`, so the OAF identity block is preserved in the body under a
    provenance heading rather than silently dropped.
    """
    manifest = agent.manifest
    root = Path(destination) / manifest.vendor_key / manifest.agent_key
    result = ExportResult(target="claude-code", destination=root)

    front: dict = {"name": manifest.agent_key, "description": manifest.description}
    allowed = manifest.tools or manifest.config.tools.allowed
    if allowed:
        front["allowed-tools"] = list(allowed)

    body = build_system_prompt(agent, skill_mode="progressive")
    body += (
        "\n\n## Provenance\n\n"
        f"Exported from Open Agent Format: `{manifest.canonical_slug}` "
        f"version {manifest.version}, licensed {manifest.license}, by {manifest.author}.\n"
    )
    _write(root / "SKILL.md", _frontmatter(front, body), result)

    for skill in agent.skills:
        if skill.local is None:
            continue
        skill_manifest = skill.local.document.manifest
        sub_front: dict = {
            "name": skill_manifest.name,
            "description": skill_manifest.description,
        }
        if skill_manifest.allowed_tools:
            sub_front["allowed-tools"] = list(skill_manifest.allowed_tools)
        _write(
            root / "skills" / skill_manifest.name / "SKILL.md",
            _frontmatter(sub_front, skill.local.document.body),
            result,
        )

    if manifest.config.tools.denied:
        result.notes.append(
            "config.tools.denied has no Claude Code equivalent; it is stated in the body"
        )
    result.notes.extend(_shared_notes(agent))
    return result


def export_goose(agent: ResolvedAgent, destination: Path) -> ExportResult:
    """Write `<dest>/<vendorKey>/<agentKey>/AGENTS.md` for Goose.

    Goose reads AGENTS.md, so this is close to a copy; the agent's `harnessConfig.goose`
    block is promoted to top-level keys, which is what it exists for.
    """
    manifest = agent.manifest
    root = Path(destination) / manifest.vendor_key / manifest.agent_key
    result = ExportResult(target="goose", destination=root)

    front: dict = {
        "name": manifest.name,
        "version": manifest.version,
        "description": manifest.description,
    }
    model = resolve_model(manifest)
    front["model"] = {"provider": model.provider, "name": model.name}
    goose_config = manifest.harness_config.get("goose")
    if isinstance(goose_config, dict):
        front.update(goose_config)

    _write(
        root / "AGENTS.md",
        _frontmatter(front, build_system_prompt(agent, skill_mode="eager")),
        result,
    )
    result.notes.extend(_shared_notes(agent))
    return result


def export_deep_agents(agent: ResolvedAgent, destination: Path) -> ExportResult:
    """Write `<dest>/<agentKey>/agent.md` plus `skills/`, per the spec's note."""
    manifest = agent.manifest
    root = Path(destination) / manifest.agent_key
    result = ExportResult(target="deep-agents", destination=root)

    # Deep Agents splits instructions from skills, so the prompt is written
    # without the generated skills section.
    _write(
        root / "agent.md",
        build_system_prompt(agent, skill_mode="progressive", include_sections=False),
        result,
    )
    for skill in agent.skills:
        if skill.local is None:
            continue
        name = skill.local.document.manifest.name
        _write(
            root / "skills" / name / "SKILL.md",
            _frontmatter(
                {
                    "name": name,
                    "description": skill.local.document.manifest.description,
                },
                skill.local.document.body,
            ),
            result,
        )
    result.notes.extend(_shared_notes(agent))
    return result


def export_letta(agent: ResolvedAgent, destination: Path) -> ExportResult:
    """Write `<dest>/<agentKey>.af`, Letta's Agent File JSON.

    Letta is the stateful target, so `memory.blocks` becomes real memory blocks;
    an agent with no `memory:` block gets none.
    """
    manifest = agent.manifest
    root = Path(destination)
    result = ExportResult(target="letta", destination=root)

    model = resolve_model(manifest)
    blocks = []
    if manifest.memory is not None:
        blocks = [
            {
                "label": label,
                "value": "" if value == "default" else value,
                "read_only": manifest.memory.type == "read-only",
            }
            for label, value in manifest.memory.blocks.items()
        ]

    agent_file = {
        "agent_type": "memgpt_agent",
        "name": manifest.name,
        "description": manifest.description,
        "system": build_system_prompt(agent, skill_mode="eager"),
        "llm_config": {"model": model.name, "model_endpoint_type": model.provider},
        "embedding_config": (
            {"embedding_model": model.embedding} if model.embedding else None
        ),
        "core_memory": blocks,
        "tags": list(manifest.tags),
        "metadata": {
            "oaf": {
                "slug": manifest.canonical_slug,
                "version": manifest.version,
                "license": manifest.license,
                "author": manifest.author,
            }
        },
    }
    if agent_file["embedding_config"] is None:
        del agent_file["embedding_config"]

    _write(
        root / f"{manifest.agent_key}.af",
        json.dumps(agent_file, indent=2, ensure_ascii=False) + "\n",
        result,
    )
    if manifest.memory is None:
        result.notes.append("no memory: block, so the exported agent has no memory blocks")
    result.notes.extend(_shared_notes(agent))
    return result


def _shared_notes(agent: ResolvedAgent) -> list[str]:
    """Composition no target format can carry, reported once per export."""
    notes = []
    if agent.packs:
        notes.append(f"{len(agent.packs)} pack reference(s) were not exported")
    if agent.weblets:
        notes.append(f"{len(agent.weblets)} weblet reference(s) were not exported")
    if agent.sub_agents:
        notes.append(
            f"{len(agent.sub_agents)} sub-agent(s) are described in the prompt but "
            "must be exported separately"
        )
    for entry in agent.mcp_servers:
        if entry.resolved:
            notes.append(
                f"MCP server {entry.loaded.name} must be configured in the target harness"
            )
    return notes


EXPORTERS = {
    "claude-code": export_claude_code,
    "goose": export_goose,
    "deep-agents": export_deep_agents,
    "letta": export_letta,
}
