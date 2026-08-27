"""Resolution: turning references into the things they point at.

The spec assigns this to harnesses: "Advanced validation (circular dependencies,
version conflicts, reference resolution) is the responsibility of agent
harnesses and tooling."

A `ResolvedAgent` is the flattened, fully-linked view of an agent — the "no
hidden state" the format promises, made explicit. `oaf inspect` prints it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .errors import DiagnosticBag
from .loader import LoadedAgent, LoadedMcp, LoadedSkill, discover_agents, load_agent
from .models.composition import PackRef, SkillRef, SubAgentRef, WebletRef


@dataclass
class ResolvedSkill:
    """A skill reference paired with the local skill it resolved to, if any."""

    ref: SkillRef
    local: LoadedSkill | None = None

    @property
    def resolved(self) -> bool:
        return self.local is not None or self.ref.is_well_known

    @property
    def deferred(self) -> bool:
        """True for well-known skills, fetched by the harness at install time."""
        return self.local is None and self.ref.is_well_known

    @property
    def instructions(self) -> str:
        """The skill's own body, or an empty string when not local."""
        return self.local.document.body.strip() if self.local else ""


@dataclass
class ResolvedMcp:
    """An MCP server reference paired with its config directory."""

    ref: object
    loaded: LoadedMcp | None = None

    @property
    def resolved(self) -> bool:
        return self.loaded is not None

    @property
    def tools(self) -> list[str]:
        if self.loaded is None or self.loaded.active is None:
            return []
        return self.loaded.active.enabled_tool_names


@dataclass
class ResolvedSubAgent:
    """A sub-agent reference paired with the resolved agent it delegates to."""

    ref: SubAgentRef
    agent: "ResolvedAgent | None" = None

    @property
    def resolved(self) -> bool:
        return self.agent is not None


@dataclass
class ResolvedAgent:
    """An agent with every reference linked and every dependency walked."""

    loaded: LoadedAgent
    skills: list[ResolvedSkill] = field(default_factory=list)
    mcp_servers: list[ResolvedMcp] = field(default_factory=list)
    sub_agents: list[ResolvedSubAgent] = field(default_factory=list)
    #: Packs and weblets have no local on-disk form in the spec, so they are
    #: carried through unresolved for the runtime to handle or report.
    packs: list[PackRef] = field(default_factory=list)
    weblets: list[WebletRef] = field(default_factory=list)
    diagnostics: DiagnosticBag = field(default_factory=DiagnosticBag)

    @property
    def manifest(self):
        return self.loaded.manifest

    @property
    def document(self):
        return self.loaded.document

    @property
    def root(self) -> Path:
        return self.loaded.root

    @property
    def slug(self) -> str:
        return self.manifest.canonical_slug

    def walk(self):
        """Yield this agent and every sub-agent, depth-first, once each."""
        seen: set[str] = set()

        def visit(agent: "ResolvedAgent"):
            if agent.slug in seen:
                return
            seen.add(agent.slug)
            yield agent
            for sub in agent.sub_agents:
                if sub.agent is not None:
                    yield from visit(sub.agent)

        yield from visit(self)

    def summary(self) -> dict:
        """A plain-data view, for `oaf inspect --json`."""
        manifest = self.manifest
        return {
            "slug": manifest.slug,
            "canonicalSlug": manifest.canonical_slug,
            "name": manifest.name,
            "version": manifest.version,
            "root": str(self.root),
            "instructionFormat": self.document.instruction_format,
            "model": manifest.model_alias
            or (manifest.model_spec.model_dump(exclude_none=True) if manifest.model_spec else None),
            "tools": list(manifest.tools),
            "toolPolicy": {
                "allowed": list(manifest.config.tools.allowed),
                "denied": list(manifest.config.tools.denied),
            },
            "orchestration": manifest.orchestration.model_dump(exclude_none=True),
            "skills": [
                {
                    "name": s.ref.name,
                    "source": s.ref.source,
                    "required": s.ref.required,
                    "status": "local" if s.local else ("deferred" if s.deferred else "missing"),
                }
                for s in self.skills
            ],
            "mcpServers": [
                {
                    "server": getattr(m.ref, "server", None),
                    "vendor": getattr(m.ref, "vendor", None),
                    "configDir": getattr(m.ref, "config_dir", None),
                    "status": "resolved" if m.resolved else "missing",
                    "tools": m.tools,
                }
                for m in self.mcp_servers
            ],
            "subAgents": [
                {
                    "slug": s.ref.slug,
                    "role": s.ref.role,
                    "delegations": list(s.ref.delegations),
                    "status": "resolved" if s.resolved else "missing",
                }
                for s in self.sub_agents
            ],
            "packs": [p.model_dump(exclude_none=True) for p in self.packs],
            "weblets": [w.model_dump(exclude_none=True) for w in self.weblets],
        }


class Workspace:
    """A set of agent directories that can resolve sub-agent references.

    A multi-agent package is the spec's own example of this: `trip-coordinator`
    delegating to `flight-researcher` only works when both are in scope.
    """

    def __init__(self, agents: dict[str, LoadedAgent] | None = None):
        self._by_slug: dict[str, LoadedAgent] = dict(agents or {})
        #: Bare agent keys claimed by more than one vendor. Looking one of these
        #: up returns nothing: guessing a vendor would silently wire an agent to
        #: the wrong sub-agent.
        self._ambiguous: set[str] = set()

    @classmethod
    def from_path(cls, root: Path) -> "Workspace":
        """Load every agent at or under `root` into one workspace."""
        workspace = cls()
        for directory in discover_agents(Path(root)):
            workspace.add(load_agent(directory))
        return workspace

    def add(self, agent: LoadedAgent) -> None:
        # Registered under both spellings: the canonical vendorKey/agentKey and
        # whatever the file's own `slug` says, since real agents disagree.
        self._by_slug[agent.canonical_slug] = agent
        self._by_slug.setdefault(agent.slug, agent)

        # The bare agentKey is a convenience for packages whose agents omit the
        # vendor prefix. It is only safe while one vendor claims it.
        key = agent.manifest.agent_key
        existing = self._by_slug.get(key)
        if existing is None:
            self._by_slug[key] = agent
        elif existing.canonical_slug != agent.canonical_slug:
            self._ambiguous.add(key)

    def get(self, slug: str) -> LoadedAgent | None:
        if slug in self._ambiguous:
            return None
        return self._by_slug.get(slug)

    def is_ambiguous(self, key: str) -> bool:
        """True when `key` is a bare agentKey claimed by several vendors."""
        return key in self._ambiguous

    @property
    def agents(self) -> list[LoadedAgent]:
        """Each agent once, in insertion order.

        The same agent is registered under several keys, so dedupe by identity
        rather than by value — LoadedAgent is a mutable dataclass and unhashable.
        """
        unique: dict[int, LoadedAgent] = {}
        for agent in self._by_slug.values():
            unique.setdefault(id(agent), agent)
        return list(unique.values())

    def __len__(self) -> int:
        return len(self.agents)


def resolve_agent(
    agent: LoadedAgent,
    *,
    workspace: Workspace | None = None,
    max_depth: int = 8,
) -> ResolvedAgent:
    """Resolve `agent` and, transitively, the sub-agents it delegates to.

    A reference cycle is reported as a diagnostic and the recursion stops there,
    rather than raising: a cyclic delegation graph is a real thing an author can
    write, and the useful response is to name the cycle, not to crash.
    """
    return _resolve(agent, workspace or Workspace(), chain=[], depth=0, max_depth=max_depth)


def _resolve(
    agent: LoadedAgent,
    workspace: Workspace,
    *,
    chain: list[str],
    depth: int,
    max_depth: int,
) -> ResolvedAgent:
    resolved = ResolvedAgent(loaded=agent)
    manifest = agent.manifest
    resolved.packs = list(manifest.packs)
    resolved.weblets = list(manifest.weblets)

    for ref in manifest.skills:
        local = agent.skills.get(ref.name) if ref.is_local else None
        resolved.skills.append(ResolvedSkill(ref=ref, local=local))

    for ref in manifest.mcp_servers:
        key = Path(ref.config_dir).name if ref.config_dir else ref.server
        resolved.mcp_servers.append(ResolvedMcp(ref=ref, loaded=agent.mcp_configs.get(key)))

    chain = [*chain, manifest.canonical_slug]
    for ref in manifest.agents:
        resolved.sub_agents.append(
            _resolve_sub_agent(ref, workspace, chain=chain, depth=depth, max_depth=max_depth,
                               diagnostics=resolved.diagnostics, root=agent.root)
        )
    return resolved


def _resolve_sub_agent(
    ref: SubAgentRef,
    workspace: Workspace,
    *,
    chain: list[str],
    depth: int,
    max_depth: int,
    diagnostics: DiagnosticBag,
    root: Path,
) -> ResolvedSubAgent:
    if ref.slug in chain:
        cycle = " -> ".join([*chain, ref.slug])
        diagnostics.error(
            "agent.cycle",
            f"delegation cycle: {cycle}",
            path=root,
            hint="an agent cannot delegate to itself, directly or transitively",
        )
        return ResolvedSubAgent(ref=ref)

    if depth + 1 > max_depth:
        diagnostics.error(
            "agent.too-deep",
            f"delegation nested deeper than {max_depth} levels at {ref.slug}",
            path=root,
        )
        return ResolvedSubAgent(ref=ref)

    target = workspace.get(ref.slug) or workspace.get(ref.agent)
    if target is None:
        severity = diagnostics.error if ref.required else diagnostics.warning
        if workspace.is_ambiguous(ref.agent):
            severity(
                "agent.ambiguous",
                f"sub-agent {ref.slug!r} did not match any agent, and the bare key "
                f"{ref.agent!r} is claimed by more than one vendor",
                path=root,
                hint="make the referenced agent's own `slug` canonical (vendorKey/agentKey)",
            )
        else:
            severity(
                "agent.unresolved",
                f"sub-agent {ref.slug!r} is not in the workspace",
                path=root,
                hint="point `oaf` at the package root so sibling agents are discoverable",
            )
        return ResolvedSubAgent(ref=ref)

    child = _resolve(target, workspace, chain=chain, depth=depth + 1, max_depth=max_depth)
    diagnostics.extend(child.diagnostics)
    return ResolvedSubAgent(ref=ref, agent=child)


def resolve_path(path: Path, *, workspace_root: Path | None = None) -> ResolvedAgent:
    """Convenience: load one agent, resolving sub-agents against its package."""
    path = Path(path)
    agent = load_agent(path)
    root = Path(workspace_root) if workspace_root else path.parent
    workspace = Workspace.from_path(root)
    workspace.add(agent)
    return resolve_agent(agent, workspace=workspace)
