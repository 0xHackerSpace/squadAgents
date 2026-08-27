"""Loading an agent directory — the spec's "filesystem as source of truth".

`load_agent` reads one agent directory into memory: the manifest, whatever local
skills and MCP configs are on disk, and the optional companion files. It reads;
it does not judge. Everything questionable is recorded as a diagnostic and
handed to `validate` to decide about.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .errors import DiagnosticBag, OafError, ParseError
from .models.agent import AgentDocument
from .models.mcp import ActiveMcp, McpConfig
from .models.skill import SkillDocument
from .parse import (
    ACTIVE_MCP_JSON,
    AGENTS_MD,
    MCP_CONFIG_YAML,
    SKILL_MD,
    parse_active_mcp,
    parse_agents_md,
    parse_mcp_config,
    parse_skill_md,
)

#: Directory names the spec assigns a meaning inside an agent.
SKILLS_DIR = "skills"
MCP_CONFIGS_DIR = "mcp-configs"
VERSIONS_DIR = "versions"
EXAMPLES_DIR = "examples"
TESTS_DIR = "tests"
DOCS_DIR = "docs"
ASSETS_DIR = "assets"


@dataclass
class LoadedSkill:
    """A local skill directory under `skills/`."""

    name: str
    path: Path
    document: SkillDocument


@dataclass
class LoadedMcp:
    """One MCP server config directory under `mcp-configs/`."""

    name: str
    path: Path
    active: ActiveMcp | None = None
    config: McpConfig | None = None

    def permits(self, tool_name: str) -> bool:
        """Whether a tool reaches the agent. With no ActiveMCP.json, all do."""
        return True if self.active is None else self.active.permits(tool_name)


@dataclass
class LoadedAgent:
    """One agent directory, read into memory."""

    root: Path
    document: AgentDocument
    skills: dict[str, LoadedSkill] = field(default_factory=dict)
    mcp_configs: dict[str, LoadedMcp] = field(default_factory=dict)
    versions: dict[str, Path] = field(default_factory=dict)
    has_readme: bool = False
    has_license: bool = False
    present_dirs: set[str] = field(default_factory=set)
    diagnostics: DiagnosticBag = field(default_factory=DiagnosticBag)

    @property
    def manifest(self):
        return self.document.manifest

    @property
    def slug(self) -> str:
        return self.manifest.slug

    @property
    def canonical_slug(self) -> str:
        return self.manifest.canonical_slug

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<LoadedAgent {self.canonical_slug} v{self.manifest.version} at {self.root}>"


def is_agent_dir(path: Path) -> bool:
    """True when `path` is a directory holding an AGENTS.md."""
    return path.is_dir() and (path / AGENTS_MD).is_file()


def load_agent(path: Path) -> LoadedAgent:
    """Load the agent rooted at `path` (a directory, or its AGENTS.md itself).

    Raises ParseError only when AGENTS.md itself cannot be read or parsed —
    without it there is no agent. A broken skill or MCP config downgrades to a
    diagnostic so the rest of the agent still loads and the author sees every
    problem at once.
    """
    path = Path(path)
    if path.is_file():
        root, manifest_path = path.parent, path
    else:
        root, manifest_path = path, path / AGENTS_MD

    if not manifest_path.is_file():
        raise ParseError(f"no {AGENTS_MD} found", path=root)

    agent = LoadedAgent(root=root, document=parse_agents_md(manifest_path))
    _load_skills(agent)
    _load_mcp_configs(agent)
    _load_versions(agent)
    _inventory(agent)
    return agent


def _load_skills(agent: LoadedAgent) -> None:
    skills_dir = agent.root / SKILLS_DIR
    if not skills_dir.is_dir():
        return
    for child in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        skill_md = child / SKILL_MD
        if not skill_md.is_file():
            agent.diagnostics.warning(
                "skill.missing-manifest",
                f"skills/{child.name}/ has no {SKILL_MD} and will be ignored",
                path=child,
                hint=f"add {SKILL_MD} with 'name' and 'description' frontmatter",
            )
            continue
        try:
            document = parse_skill_md(skill_md)
        except OafError as exc:
            agent.diagnostics.error("skill.unparsable", str(exc), path=skill_md)
            continue
        agent.skills[child.name] = LoadedSkill(child.name, child, document)
        if not document.frontmatter_present:
            agent.diagnostics.warning(
                "skill.no-frontmatter",
                f"skills/{child.name}/{SKILL_MD} has no YAML frontmatter; name and "
                "description were inferred from the directory and body",
                path=skill_md,
                hint="AgentSkills.io requires 'name' and 'description' in frontmatter",
            )
        elif document.manifest.name != child.name:
            agent.diagnostics.warning(
                "skill.name-mismatch",
                f"skill declares name {document.manifest.name!r} but lives in "
                f"skills/{child.name}/",
                path=skill_md,
                field="name",
                hint="a skill referenced with source: local is looked up by directory name",
            )


def _load_mcp_configs(agent: LoadedAgent) -> None:
    mcp_dir = agent.root / MCP_CONFIGS_DIR
    if not mcp_dir.is_dir():
        return
    for child in sorted(p for p in mcp_dir.iterdir() if p.is_dir()):
        loaded = LoadedMcp(name=child.name, path=child)
        active_path = child / ACTIVE_MCP_JSON
        config_path = child / MCP_CONFIG_YAML
        if active_path.is_file():
            try:
                loaded.active = parse_active_mcp(active_path)
            except OafError as exc:
                agent.diagnostics.error("mcp.active-unparsable", str(exc), path=active_path)
        if config_path.is_file():
            try:
                loaded.config = parse_mcp_config(config_path)
            except OafError as exc:
                agent.diagnostics.error("mcp.config-unparsable", str(exc), path=config_path)
        if loaded.active is None and loaded.config is None:
            agent.diagnostics.warning(
                "mcp.empty-config-dir",
                f"{MCP_CONFIGS_DIR}/{child.name}/ has neither {ACTIVE_MCP_JSON} nor "
                f"{MCP_CONFIG_YAML}",
                path=child,
            )
        agent.mcp_configs[child.name] = loaded


def _load_versions(agent: LoadedAgent) -> None:
    versions_dir = agent.root / VERSIONS_DIR
    if not versions_dir.is_dir():
        return
    for child in sorted(p for p in versions_dir.iterdir() if p.is_dir()):
        if (child / AGENTS_MD).is_file():
            # Directories are named `v1.0.0`; the key is the bare version.
            agent.versions[child.name.lstrip("v")] = child
        else:
            agent.diagnostics.warning(
                "versions.missing-manifest",
                f"{VERSIONS_DIR}/{child.name}/ has no {AGENTS_MD}",
                path=child,
            )


def _inventory(agent: LoadedAgent) -> None:
    agent.has_readme = (agent.root / "README.md").is_file()
    agent.has_license = (agent.root / "LICENSE").is_file()
    for name in (SKILLS_DIR, MCP_CONFIGS_DIR, VERSIONS_DIR, EXAMPLES_DIR, TESTS_DIR,
                 DOCS_DIR, ASSETS_DIR):
        if (agent.root / name).is_dir():
            agent.present_dirs.add(name)


def discover_agents(root: Path, *, max_depth: int = 3) -> list[Path]:
    """Find agent directories at or under `root`.

    A package can hold agents flat at the top level or, as the published samples
    do, under a single `package/` directory, so a shallow walk covers both
    without descending into an agent's own `versions/` history.
    """
    root = Path(root)
    if is_agent_dir(root):
        return [root]

    found: list[Path] = []

    def walk(directory: Path, depth: int) -> None:
        if depth > max_depth:
            return
        for child in sorted(p for p in directory.iterdir() if p.is_dir()):
            if child.name in {VERSIONS_DIR, SKILLS_DIR, MCP_CONFIGS_DIR, ".git"}:
                continue
            if is_agent_dir(child):
                found.append(child)
            else:
                walk(child, depth + 1)

    if root.is_dir():
        walk(root, 1)
    return found
