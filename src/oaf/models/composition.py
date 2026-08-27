"""Composition references: skills, packs, weblets, MCP servers, sub-agents.

Field names follow the spec's "Composition Fields (Optional)" tables. Every
reference carries `required` because the resolver treats a missing optional
dependency as a warning and a missing required one as an error.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import Str

LaunchMode = Literal["onDemand", "background", "foreground"]

LOCAL_SOURCE = "local"


class _Ref(BaseModel):
    # Unknown keys are kept rather than dropped: harnesses in the wild add their
    # own, and `oaf inspect` should show the author what is actually in the file.
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class SkillRef(_Ref):
    """A skill reference. `source` is either "local" or a well-known URL."""

    name: Str
    source: Str = LOCAL_SOURCE
    version: Str | None = None
    required: bool = False

    @property
    def is_local(self) -> bool:
        return self.source.strip().lower() == LOCAL_SOURCE

    @property
    def is_well_known(self) -> bool:
        return self.source.startswith(("http://", "https://"))

    @property
    def ref_id(self) -> str:
        return f"skill:{self.name}"


class PackRef(_Ref):
    """A pack: a vendor-published collection of skills."""

    vendor: Str
    pack: Str
    version: Str | None = None
    required: bool = False

    @property
    def ref_id(self) -> str:
        return f"pack:{self.vendor}/{self.pack}"


class WebletRef(_Ref):
    """A weblet: a web-based tool or interface, launched in one of three modes."""

    vendor: Str
    weblet: Str
    version: Str | None = None
    launch: LaunchMode = "onDemand"
    required: bool = False

    @property
    def ref_id(self) -> str:
        return f"weblet:{self.vendor}/{self.weblet}"


class McpServerRef(_Ref):
    """An MCP server reference pointing at a config directory in the agent."""

    vendor: Str | None = None
    server: Str
    version: Str | None = None
    config_dir: Str | None = Field(default=None, alias="configDir")
    required: bool = False

    @property
    def ref_id(self) -> str:
        return f"mcp:{self.vendor}/{self.server}" if self.vendor else f"mcp:{self.server}"


class SubAgentRef(_Ref):
    """A nested agent this agent delegates to."""

    vendor: Str
    agent: Str
    version: Str | None = None
    role: Str | None = None
    delegations: list[Str] = Field(default_factory=list)
    required: bool = False

    @property
    def slug(self) -> str:
        return f"{self.vendor}/{self.agent}"

    @property
    def ref_id(self) -> str:
        return f"agent:{self.slug}"


class Trigger(_Ref):
    """An event-action mapping under `orchestration.triggers`."""

    event: Str
    action: Str


class Orchestration(_Ref):
    """Entrypoint, fallback and triggers.

    The spec nests these under `orchestration:`, but the reference agents
    published with OpenHarness put a bare `entrypoint:` at the top level of the
    frontmatter. The agent model accepts both and normalizes into this object.
    """

    entrypoint: Str | None = None
    fallback: Str | None = None
    triggers: list[Trigger] = Field(default_factory=list)


class ToolPolicy(_Ref):
    """`config.tools.allowed` / `config.tools.denied`."""

    allowed: list[Str] = Field(default_factory=list)
    denied: list[Str] = Field(default_factory=list)

    def permits(self, tool: str) -> bool:
        """Deny wins over allow; an empty allow-list means "no allow-list"."""
        if tool in self.denied:
            return False
        return not self.allowed or tool in self.allowed


class AgentConfig(_Ref):
    """The optional `config:` block."""

    temperature: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, gt=0)
    require_confirmation: bool = False
    tools: ToolPolicy = Field(default_factory=ToolPolicy)


class Memory(_Ref):
    """The optional `memory:` block, for stateful harnesses such as Letta."""

    type: Literal["editable", "read-only"] = "editable"
    blocks: dict[str, Str] = Field(default_factory=dict)


class ModelSpec(_Ref):
    """The full object form of `model:`."""

    provider: Str | None = None
    name: Str | None = None
    embedding: Str | None = None
