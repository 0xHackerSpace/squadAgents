"""Running an OAF agent on Agno.

The mapping the spec's fields imply:

    Markdown body          -> the agent's system message
    model / model alias    -> an Agno model client
    config.temperature     -> model temperature
    config.max_tokens      -> model max output tokens
    skills (local)         -> either inlined instructions or a `load_skill` tool
    agents (sub-agents)    -> an Agno Team, with this agent as the leader
    mcpServers             -> reported, see the note in `_mcp_notes`

Agno is imported lazily so that parsing, validation, resolution and inspection
all work with only the core dependencies installed.
"""

from __future__ import annotations

import time
from typing import Any

from ..errors import HarnessError
from ..resolve import ResolvedAgent
from .base import BuildResult, HarnessAdapter


class AgnoAdapter(HarnessAdapter):
    """Builds Agno `Agent` objects, and an Agno `Team` when sub-agents exist."""

    name = "agno"

    def build(self, agent: ResolvedAgent, *, depth: int = 0) -> BuildResult:
        model, prompt, mode = self.plan(agent)
        self._record_build(agent, model, depth)
        agno = _import_agno()

        client = _build_model_client(agno, model, agent)
        tools = _build_tools(agent, mode)

        sub_results = [
            self.build(sub.agent, depth=depth + 1)
            for sub in agent.sub_agents
            if sub.agent is not None
        ]

        kwargs: dict[str, Any] = {
            "name": agent.manifest.name,
            "model": client,
            "instructions": prompt,
        }
        if tools:
            kwargs["tools"] = [t["fn"] for t in tools]

        if sub_results:
            # Sub-agent delegation maps onto an Agno Team led by this agent. The
            # leader keeps its own tools: a team leader that can no longer read
            # its skills is not the same agent.
            kwargs["members"] = [r.agent for r in sub_results]
            built = agno["Team"](**kwargs)
        else:
            built = agno["Agent"](**kwargs)

        result = BuildResult(
            agent=built,
            slug=agent.slug,
            model=model,
            system_prompt=prompt,
            skill_mode=mode,
            tools=[t["name"] for t in tools],
            sub_agents=sub_results,
        )
        result.notes.extend(_mcp_notes(agent))
        result.notes.extend(_unsupported_notes(agent))
        return result

    def run(self, built: BuildResult, message: str, *, stream: bool = False) -> str:
        if built.agent is None:
            raise HarnessError(f"{built.slug} was not built with a runnable adapter")

        inicio = time.monotonic()
        if self.trace is not None:
            self.trace.record("run-start", built.slug, detalhe=str(built.model))
        try:
            if stream:
                built.agent.print_response(message, stream=True)
                reply = ""
            else:
                response = built.agent.run(message)
                reply = getattr(response, "content", None) or str(response)
        except Exception as exc:
            # A failure is evidence too, and the one most worth having.
            if self.trace is not None:
                self.trace.record(
                    "error",
                    built.slug,
                    duracao_ms=_ms_since(inicio),
                    detalhe=f"{type(exc).__name__}: {exc}",
                )
            raise
        if self.trace is not None:
            self.trace.record("run-end", built.slug, duracao_ms=_ms_since(inicio))
        return reply


def _ms_since(inicio: float) -> int:
    return int((time.monotonic() - inicio) * 1000)


def _import_agno() -> dict[str, Any]:
    """Import Agno, turning the ImportError into an actionable message."""
    try:
        from agno.agent import Agent
        from agno.team import Team
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise HarnessError(
            "the agno harness needs the 'runtime' extra: "
            "uv pip install -e '.[runtime]'"
        ) from exc
    return {"Agent": Agent, "Team": Team}


def _build_model_client(agno: dict[str, Any], model, agent: ResolvedAgent):
    """Instantiate the provider client Agno needs for `model`."""
    config = agent.manifest.config
    kwargs: dict[str, Any] = {"id": model.name}
    if config.temperature is not None:
        kwargs["temperature"] = config.temperature
    if config.max_tokens is not None:
        kwargs["max_tokens"] = config.max_tokens

    provider = model.provider.lower()
    try:
        if provider == "anthropic":
            from agno.models.anthropic import Claude

            return Claude(**kwargs)
        if provider == "openai":
            from agno.models.openai import OpenAIChat

            return OpenAIChat(**kwargs)
        if provider == "google":
            from agno.models.google import Gemini

            return Gemini(**kwargs)
        if provider == "ollama":
            from agno.models.ollama import Ollama

            return Ollama(**kwargs)
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise HarnessError(
            f"agno has no client installed for provider {model.provider!r}"
        ) from exc

    raise HarnessError(
        f"provider {model.provider!r} is not mapped to an agno model client"
    )


def _build_tools(agent: ResolvedAgent, mode: str) -> list[dict[str, Any]]:
    """Build the callable tools this agent gets.

    In progressive mode the agent gets one tool, `load_skill`, which returns a
    local skill's full instructions on demand. That is the whole mechanism
    behind `progressive-disclosure`: names up front, bodies when asked for.
    """
    if mode != "progressive":
        return []
    local = {s.ref.name: s for s in agent.skills if s.local is not None}
    if not local:
        return []

    def load_skill(name: str) -> str:
        """Load the full instructions for one of this agent's skills.

        Args:
            name: The skill name, as listed under "Available Skills".
        """
        skill = local.get(name)
        if skill is None:
            available = ", ".join(sorted(local)) or "none"
            return f"No skill named {name!r}. Available skills: {available}."
        document = skill.local.document
        return f"# {document.manifest.name}\n\n{document.body.strip()}"

    return [{"name": "load_skill", "fn": load_skill}]


def _mcp_notes(agent: ResolvedAgent) -> list[str]:
    """MCP servers are described to the model but not dialed.

    Connecting means opening a live session per server, which belongs to a
    caller that can manage its lifetime, not to a synchronous `build`. The tool
    subset from ActiveMCP.json is reported so the gap is visible rather than
    silent.
    """
    notes = []
    for entry in agent.mcp_servers:
        if not entry.resolved:
            continue
        tools = ", ".join(entry.tools) if entry.tools else "all advertised tools"
        notes.append(
            f"mcp: {entry.loaded.name} declared ({tools}); "
            "described in the prompt, not connected"
        )
    return notes


def _unsupported_notes(agent: ResolvedAgent) -> list[str]:
    """Composition the spec defines but this adapter does not implement."""
    notes = []
    for pack in agent.packs:
        notes.append(f"pack: {pack.vendor}/{pack.pack} declared; no pack registry configured")
    for weblet in agent.weblets:
        notes.append(
            f"weblet: {weblet.vendor}/{weblet.weblet} declared "
            f"(launch={weblet.launch}); weblets are not implemented"
        )
    for skill in agent.skills:
        if skill.deferred:
            notes.append(
                f"skill: {skill.ref.name} is a well-known URL and is not fetched "
                "at build time"
            )
    return notes
