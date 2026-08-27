"""The adapter contract every harness backend implements.

The spec's whole point is that one agent definition runs on many harnesses, so
the harness is a pluggable backend rather than a hardwired dependency. An
adapter turns a `ResolvedAgent` into something runnable and runs it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..errors import HarnessError
from ..resolve import ResolvedAgent
from .models import ResolvedModel, resolve_model
from .prompt import SkillMode, build_system_prompt, skill_mode_for


@dataclass
class BuildResult:
    """A built agent plus the decisions that produced it."""

    agent: Any
    slug: str
    model: ResolvedModel
    system_prompt: str
    skill_mode: SkillMode
    tools: list[str] = field(default_factory=list)
    sub_agents: list["BuildResult"] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class HarnessAdapter(ABC):
    """Base class for harness backends."""

    #: Identifier matching the `harnessConfig` key this adapter reads.
    name: str = "base"

    def __init__(
        self,
        *,
        model_override: str | None = None,
        skill_mode: SkillMode | None = None,
        environ: dict[str, str] | None = None,
    ):
        self.model_override = model_override
        self.skill_mode = skill_mode
        self.environ = environ

    def harness_config(self, agent: ResolvedAgent) -> dict[str, Any]:
        """This adapter's slice of the agent's free-form `harnessConfig`."""
        config = agent.manifest.harness_config.get(self.name)
        return config if isinstance(config, dict) else {}

    def plan(self, agent: ResolvedAgent) -> tuple[ResolvedModel, str, SkillMode]:
        """The three decisions every adapter makes before instantiating."""
        model = resolve_model(
            agent.manifest, environ=self.environ, override=self.model_override
        )
        mode = self.skill_mode or skill_mode_for(agent)
        prompt = build_system_prompt(agent, skill_mode=mode)
        return model, prompt, mode

    @abstractmethod
    def build(self, agent: ResolvedAgent) -> BuildResult:
        """Instantiate `agent` on this harness."""

    @abstractmethod
    def run(self, built: BuildResult, message: str, *, stream: bool = False) -> str:
        """Send `message` to a built agent and return its reply."""


class DryRunAdapter(HarnessAdapter):
    """An adapter that builds everything but instantiates no model client.

    This is what `oaf inspect` and the test suite use: it exercises resolution,
    prompt composition and model selection end to end without a network call or
    an API key.
    """

    name = "dry-run"

    def build(self, agent: ResolvedAgent) -> BuildResult:
        model, prompt, mode = self.plan(agent)
        result = BuildResult(
            agent=None,
            slug=agent.slug,
            model=model,
            system_prompt=prompt,
            skill_mode=mode,
            tools=list(agent.manifest.tools),
            notes=["dry run: no model client was instantiated"],
        )
        result.sub_agents = [
            self.build(sub.agent) for sub in agent.sub_agents if sub.agent is not None
        ]
        return result

    def run(self, built: BuildResult, message: str, *, stream: bool = False) -> str:
        raise HarnessError(
            "the dry-run adapter cannot execute an agent; use --harness agno to run one"
        )
