"""The AGENTS.md manifest: the one required file in an OAF agent."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .common import Str, VersionStr
from .composition import (
    AgentConfig,
    McpServerRef,
    Memory,
    ModelSpec,
    Orchestration,
    PackRef,
    SkillRef,
    SubAgentRef,
    WebletRef,
)

# The three aliases the spec names for the simplified `model:` string form.
MODEL_ALIASES = ("sonnet", "opus", "haiku")

InstructionFormat = Literal["structured", "system-prompt"]

# Frontmatter keys the spec places at the top level. Anything outside this set
# is surfaced by the validator as an unknown key, which is how typos get caught
# without the parser refusing the file.
KNOWN_KEYS = frozenset(
    {
        "name", "vendorKey", "agentKey", "version", "slug",
        "description", "author", "license", "tags",
        "skills", "packs", "weblets", "mcpServers", "agents",
        "orchestration", "tools", "config", "memory", "model", "harnessConfig",
        # tolerated top-level spellings of orchestration fields, see below
        "entrypoint", "fallback", "triggers",
    }
)


class AgentManifest(BaseModel):
    """The parsed YAML frontmatter of an AGENTS.md file.

    Required identity and metadata fields are required here too, so a document
    missing them fails to construct. Everything the spec marks optional defaults
    to empty, which keeps the minimal one-file agent from the spec's Quick Start
    valid with no further ceremony.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    # --- Identity (required) ---
    name: Str
    vendor_key: Str = Field(alias="vendorKey")
    agent_key: Str = Field(alias="agentKey")
    version: VersionStr
    slug: Str

    # --- Metadata (required) ---
    description: Str
    author: Str
    license: Str
    tags: list[Str] = Field(default_factory=list)

    # --- Composition (optional) ---
    skills: list[SkillRef] = Field(default_factory=list)
    packs: list[PackRef] = Field(default_factory=list)
    weblets: list[WebletRef] = Field(default_factory=list)
    mcp_servers: list[McpServerRef] = Field(default_factory=list, alias="mcpServers")
    agents: list[SubAgentRef] = Field(default_factory=list)

    # --- Orchestration / tools / config (optional) ---
    orchestration: Orchestration = Field(default_factory=Orchestration)
    tools: list[Str] = Field(default_factory=list)
    config: AgentConfig = Field(default_factory=AgentConfig)
    memory: Memory | None = None

    # --- Model (optional, two shapes) ---
    model: Str | ModelSpec | None = None

    # --- Harness escape hatch (optional, free-form by design) ---
    harness_config: dict[str, Any] = Field(default_factory=dict, alias="harnessConfig")

    #: Orchestration keys that were written bare at the top level and lifted into
    #: `orchestration`. Populated by the validator below; the validator module
    #: reports them, since the spec nests them. Excluded from serialization.
    lifted_orchestration_keys: list[str] = Field(default_factory=list, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def _lift_bare_orchestration_keys(cls, data: Any) -> Any:
        """Accept `entrypoint:`/`fallback:`/`triggers:` at the top level.

        The spec nests these under `orchestration:`, but every reference agent
        shipped with OpenHarness writes a bare `entrypoint: structured`. Refusing
        those files would make the harness useless against the only real corpus
        that exists, so they are lifted into `orchestration` here and flagged by
        the validator as a non-canonical spelling.
        """
        if not isinstance(data, dict):
            return data
        bare = {k: data[k] for k in ("entrypoint", "fallback", "triggers") if k in data}
        if not bare:
            return data
        data = dict(data)
        nested = dict(data.get("orchestration") or {})
        for key, value in bare.items():
            # An explicit `orchestration:` block wins over the bare key.
            nested.setdefault(key, value)
            data.pop(key, None)
        data["orchestration"] = nested
        data["lifted_orchestration_keys"] = sorted(bare)
        return data

    # --- Derived views ---

    @property
    def canonical_slug(self) -> str:
        """`vendorKey/agentKey`, which is what the spec says `slug` must be."""
        return f"{self.vendor_key}/{self.agent_key}"

    @property
    def model_alias(self) -> str | None:
        """The alias when `model:` is the simplified string form."""
        return self.model if isinstance(self.model, str) else None

    @property
    def model_spec(self) -> ModelSpec | None:
        """The object when `model:` is the full form."""
        return self.model if isinstance(self.model, ModelSpec) else None

    def all_refs(self):
        """Every composition reference, in the order the spec lists them."""
        yield from self.skills
        yield from self.packs
        yield from self.weblets
        yield from self.mcp_servers
        yield from self.agents

    def unknown_keys(self) -> list[str]:
        extra = self.model_extra or {}
        return sorted(k for k in extra if k not in KNOWN_KEYS)


class AgentDocument(BaseModel):
    """An AGENTS.md file as a whole: frontmatter plus the Markdown body."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    manifest: AgentManifest
    body: str
    #: Line number in the source file where the body starts (1-indexed), so
    #: diagnostics about instructions can point at a real line.
    body_line: int = 1

    @property
    def instruction_format(self) -> InstructionFormat:
        """Per the spec: a body starting with `#` is structured, else a prompt.

        Leading blank lines are ignored; the spec's rule is about the first
        piece of content, not the first byte.
        """
        stripped = self.body.lstrip()
        return "structured" if stripped.startswith("#") else "system-prompt"

    @property
    def system_prompt(self) -> str:
        """The body as a system prompt, whichever format it is written in."""
        return self.body.strip()

    def sections(self) -> dict[str, str]:
        """`##`-level sections of a structured body, keyed by heading text."""
        found: dict[str, str] = {}
        current: str | None = None
        buffer: list[str] = []
        for line in self.body.splitlines():
            if line.startswith("## "):
                if current is not None:
                    found[current] = "\n".join(buffer).strip()
                current = line[3:].strip()
                buffer = []
            elif current is not None:
                buffer.append(line)
        if current is not None:
            found[current] = "\n".join(buffer).strip()
        return found
