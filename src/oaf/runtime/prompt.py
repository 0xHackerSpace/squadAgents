"""Composing the system prompt an OAF agent runs with.

The Markdown body is the instructions. Skills, MCP tool subsets and delegation
targets are context the body assumes but does not repeat, so they are appended
here as generated sections.

Skills load in one of two modes:

  eager        every local skill body is inlined into the system prompt.
  progressive  only names and descriptions are listed; the full body arrives
               when the agent calls `load_skill`, which is what
               `harnessConfig.claude-code.progressive-disclosure` asks for.
"""

from __future__ import annotations

from typing import Literal

from ..resolve import ResolvedAgent

SkillMode = Literal["eager", "progressive"]

PROGRESSIVE_NOTE = (
    "Call `load_skill(name)` to read a skill's full instructions before using it."
)


def skill_mode_for(agent: ResolvedAgent, *, default: SkillMode = "progressive") -> SkillMode:
    """Honour `harnessConfig.<harness>.progressive-disclosure` when it is set."""
    for config in agent.manifest.harness_config.values():
        if isinstance(config, dict) and "progressive-disclosure" in config:
            return "progressive" if config["progressive-disclosure"] else "eager"
    return default


def build_system_prompt(
    agent: ResolvedAgent,
    *,
    skill_mode: SkillMode | None = None,
    include_sections: bool = True,
) -> str:
    """Build the full system prompt for `agent`.

    Works for both instruction formats the spec defines: a structured body and a
    bare system prompt are both simply the leading text.
    """
    mode = skill_mode or skill_mode_for(agent)
    parts = [agent.document.system_prompt]
    if include_sections:
        parts.extend(
            section
            for section in (
                _skills_section(agent, mode),
                _mcp_section(agent),
                _delegation_section(agent),
                _tool_policy_section(agent),
            )
            if section
        )
    return "\n\n".join(p for p in parts if p).strip()


def _skills_section(agent: ResolvedAgent, mode: SkillMode) -> str:
    if not agent.skills:
        return ""
    lines = ["## Available Skills"]
    for skill in agent.skills:
        if skill.local is not None:
            manifest = skill.local.document.manifest
            marker = " (required)" if skill.ref.required else ""
            lines.append(f"\n### {manifest.name}{marker}\n{manifest.description}")
            if mode == "eager":
                body = skill.instructions
                if body:
                    lines.append(body)
            extras = _skill_assets(skill)
            if extras:
                lines.append(extras)
        elif skill.deferred:
            lines.append(
                f"\n### {skill.ref.name}\nPublished at {skill.ref.source}; "
                "not bundled with this agent."
            )
        else:
            lines.append(f"\n### {skill.ref.name}\nDeclared but unavailable in this install.")
    if mode == "progressive":
        lines.append(f"\n{PROGRESSIVE_NOTE}")
    return "\n".join(lines)


def _skill_assets(skill) -> str:
    """List a skill's on-disk companions so the agent knows they exist."""
    document = skill.local.document
    groups = (
        ("resources", document.resources),
        ("scripts", document.scripts),
        ("assets", document.assets),
    )
    listed = [
        f"- {label}: " + ", ".join(files)
        for label, files in groups
        if files
    ]
    if not listed:
        return ""
    base = skill.local.path.name
    return f"Files under skills/{base}/:\n" + "\n".join(listed)


def _mcp_section(agent: ResolvedAgent) -> str:
    resolved = [m for m in agent.mcp_servers if m.resolved]
    if not resolved:
        return ""
    lines = ["## Connected MCP Servers"]
    for entry in resolved:
        loaded = entry.loaded
        config = loaded.config
        endpoint = ""
        if config is not None and config.connection.url:
            endpoint = f" at {config.connection.url}"
        lines.append(f"\n### {loaded.name}{endpoint}")
        if entry.tools:
            lines.append("Available tools: " + ", ".join(f"`{t}`" for t in entry.tools))
        if loaded.active is not None and loaded.active.excluded_tools:
            lines.append(
                "Explicitly unavailable: "
                + ", ".join(f"`{t}`" for t in loaded.active.excluded_tools)
            )
    return "\n".join(lines)


def _delegation_section(agent: ResolvedAgent) -> str:
    if not agent.sub_agents:
        return ""
    lines = ["## Delegation"]
    for sub in agent.sub_agents:
        role = f" ({sub.ref.role})" if sub.ref.role else ""
        status = "" if sub.resolved else " — NOT AVAILABLE in this install"
        lines.append(f"\n### {sub.ref.slug}{role}{status}")
        if sub.resolved:
            lines.append(sub.agent.manifest.description)
        if sub.ref.delegations:
            lines.append("Delegate: " + ", ".join(sub.ref.delegations))
    return "\n".join(lines)


def _tool_policy_section(agent: ResolvedAgent) -> str:
    policy = agent.manifest.config.tools
    if not policy.denied:
        return ""
    return "## Tool Restrictions\n\nYou must not use: " + ", ".join(
        f"`{t}`" for t in policy.denied
    )
