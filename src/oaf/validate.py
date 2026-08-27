"""Validation.

The spec's "Validation (Informative)" section leaves enforcement to the harness
and suggests four checks: required fields, valid formats, YAML validity, and at
least one `##` heading. Required fields and YAML validity are already enforced
by the parser, which cannot build a model without them. This module covers the
formats and structure, plus the reference-resolution checks the spec explicitly
assigns to harnesses.

Two profiles exist because the spec and the agents published alongside it
disagree:

  STRICT   every rule the spec states, as stated. Use it to author new agents.
  LENIENT  the deviations the reference agents actually exhibit are demoted to
           warnings. Use it to consume agents from the wild.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from .errors import Diagnostic, DiagnosticBag, Severity
from .loader import AGENTS_MD, LoadedAgent
from .models.agent import MODEL_ALIASES, AgentDocument
from .models.common import (
    COMMON_SPDX,
    is_canonical_slug,
    is_kebab_case,
    is_semver,
    is_version_constraint,
)

DESCRIPTION_MIN = 50
DESCRIPTION_MAX = 500
NAME_MAX = 100


class Profile(str, Enum):
    STRICT = "strict"
    LENIENT = "lenient"


#: Rules the spec states but the reference agents break. Under LENIENT these
#: report as warnings; under STRICT they are errors. Each entry is a deviation
#: observed in the agents published with the OpenHarness samples.
NEGOTIABLE = {
    # `slug` is defined as `vendorKey/agentKey`; every sample writes a bare name.
    "identity.slug-not-canonical",
    # `description` is specified as 50-500 chars; several samples fall short.
    "metadata.description-length",
    # `entrypoint` belongs under `orchestration:`; the samples put it top level.
    "orchestration.bare-key",
    # The spec's structured body should carry `##` sections.
    "instructions.no-sections",
}


def validate_agent(
    agent: LoadedAgent,
    *,
    profile: Profile = Profile.LENIENT,
    environ: dict[str, str] | None = None,
) -> DiagnosticBag:
    """Validate one loaded agent, returning every finding.

    Diagnostics collected during loading (unparsable skills, empty config dirs)
    are included, so a caller gets one complete report.
    """
    bag = DiagnosticBag()
    bag.extend(agent.diagnostics)
    path = agent.root / AGENTS_MD
    manifest = agent.manifest

    def report(code: str, message: str, **kw) -> None:
        """Emit at the severity this profile assigns the rule."""
        severity = (
            Severity.WARNING
            if code in NEGOTIABLE and profile is Profile.LENIENT
            else Severity.ERROR
        )
        bag.add(Diagnostic(severity, code, message, **kw))

    _check_identity(manifest, path, report, bag)
    _check_metadata(manifest, path, report, bag)
    _check_model(manifest, path, bag)
    _check_orchestration(agent.document, path, report)
    _check_instructions(agent.document, path, report, bag)
    _check_composition(agent, path, bag, environ=environ)
    _check_layout(agent, bag)
    return bag


def _check_identity(manifest, path: Path, report, bag: DiagnosticBag) -> None:
    if len(manifest.name) > NAME_MAX:
        bag.error(
            "identity.name-too-long",
            f"name is {len(manifest.name)} chars, the spec allows 1-{NAME_MAX}",
            path=path, field="name",
        )
    for field_name, value in (("vendorKey", manifest.vendor_key), ("agentKey", manifest.agent_key)):
        if not is_kebab_case(value):
            bag.error(
                "identity.not-kebab-case",
                f"{field_name} {value!r} is not kebab-case",
                path=path, field=field_name,
                hint="use lowercase words joined by single hyphens, e.g. 'code-reviewer'",
            )
    if not is_canonical_slug(manifest.slug):
        report(
            "identity.slug-not-canonical",
            f"slug {manifest.slug!r} is not 'vendorKey/agentKey' "
            f"(expected {manifest.canonical_slug!r})",
            path=path, field="slug",
            hint="the spec defines slug as the unique identifier vendorKey/agentKey",
        )
    elif manifest.slug != manifest.canonical_slug:
        bag.error(
            "identity.slug-mismatch",
            f"slug {manifest.slug!r} disagrees with vendorKey/agentKey "
            f"({manifest.canonical_slug!r})",
            path=path, field="slug",
        )


def _check_metadata(manifest, path: Path, report, bag: DiagnosticBag) -> None:
    length = len(manifest.description)
    if not DESCRIPTION_MIN <= length <= DESCRIPTION_MAX:
        report(
            "metadata.description-length",
            f"description is {length} chars, the spec calls for "
            f"{DESCRIPTION_MIN}-{DESCRIPTION_MAX}",
            path=path, field="description",
        )
    if manifest.license not in COMMON_SPDX:
        bag.warning(
            "metadata.license-not-spdx",
            f"license {manifest.license!r} is not a recognized SPDX identifier",
            path=path, field="license",
            hint="see https://spdx.org/licenses/ — e.g. 'MIT', 'Apache-2.0'",
        )
    if not manifest.tags:
        bag.warning(
            "metadata.no-tags",
            "tags is empty; the spec lists tags among the required metadata fields",
            path=path, field="tags",
        )
    for key in manifest.unknown_keys():
        bag.warning(
            "manifest.unknown-key",
            f"unknown top-level frontmatter key {key!r}",
            path=path, field=key,
            hint="harness-specific settings belong under harnessConfig",
        )


def _check_model(manifest, path: Path, bag: DiagnosticBag) -> None:
    alias = manifest.model_alias
    if alias is not None and alias not in MODEL_ALIASES:
        bag.warning(
            "model.unknown-alias",
            f"model alias {alias!r} is not one of {', '.join(MODEL_ALIASES)}",
            path=path, field="model",
            hint="use the object form {provider, name} for a specific model",
        )
    spec = manifest.model_spec
    if spec is not None and not spec.name:
        bag.error(
            "model.missing-name",
            "model is an object but has no 'name'",
            path=path, field="model.name",
        )


def _check_orchestration(document: AgentDocument, path: Path, report) -> None:
    lifted = document.manifest.lifted_orchestration_keys
    if not lifted:
        return
    names = ", ".join(repr(k) for k in lifted)
    report(
        "orchestration.bare-key",
        f"{names} set at the top level; the spec nests these under 'orchestration'",
        path=path, field=lifted[0],
        hint="orchestration:\n      entrypoint: main",
    )


def _check_instructions(document: AgentDocument, path: Path, report, bag: DiagnosticBag) -> None:
    line = document.body_line
    if not document.body.strip():
        bag.error(
            "instructions.empty",
            "the Markdown body is empty; an agent needs instructions",
            path=path, line=line,
        )
        return
    if document.instruction_format == "structured" and not document.sections():
        report(
            "instructions.no-sections",
            "structured instructions have no '##' section headings",
            path=path, line=line,
            hint="the spec suggests validating for at least one '##' heading",
        )


def _check_composition(
    agent: LoadedAgent, path: Path, bag: DiagnosticBag, *, environ: dict[str, str] | None
) -> None:
    manifest = agent.manifest

    for ref in manifest.all_refs():
        version = getattr(ref, "version", None)
        if version and not is_version_constraint(version):
            bag.warning(
                "composition.bad-version",
                f"{ref.ref_id} has version {version!r}, which is neither a semantic "
                "version nor a recognized constraint",
                path=path, field="version",
            )

    seen: set[str] = set()
    for ref in manifest.all_refs():
        if ref.ref_id in seen:
            bag.warning(
                "composition.duplicate-ref",
                f"{ref.ref_id} is referenced more than once",
                path=path,
            )
        seen.add(ref.ref_id)

    for skill in manifest.skills:
        if skill.is_local:
            if skill.name not in agent.skills:
                severity = bag.error if skill.required else bag.warning
                severity(
                    "skill.unresolved",
                    f"skill {skill.name!r} declares source: local but "
                    f"skills/{skill.name}/ does not exist",
                    path=path, field="skills",
                )
        elif not skill.is_well_known:
            bag.warning(
                "skill.bad-source",
                f"skill {skill.name!r} has source {skill.source!r}, expected "
                "'local' or a well-known URL",
                path=path, field="skills",
            )

    for server in manifest.mcp_servers:
        directory = server.config_dir
        if not directory:
            bag.warning(
                "mcp.no-config-dir",
                f"MCP server {server.server!r} has no configDir",
                path=path, field="mcpServers",
            )
            continue
        key = Path(directory).name
        if key not in agent.mcp_configs:
            severity = bag.error if server.required else bag.warning
            severity(
                "mcp.unresolved",
                f"MCP server {server.server!r} points at {directory!r}, which does not exist",
                path=path, field="mcpServers",
            )

    # An MCP config directory nobody references is dead weight; the spec says
    # mcp-configs/ exists only when MCP servers are referenced.
    referenced = {Path(s.config_dir).name for s in manifest.mcp_servers if s.config_dir}
    for name in agent.mcp_configs:
        if name not in referenced:
            bag.warning(
                "mcp.orphan-config",
                f"mcp-configs/{name}/ is not referenced by any mcpServers entry",
                path=agent.mcp_configs[name].path,
            )
    for name, skill in agent.skills.items():
        if name not in {s.name for s in manifest.skills if s.is_local}:
            bag.warning(
                "skill.orphan",
                f"skills/{name}/ is not referenced by any skills entry",
                path=skill.path,
            )

    for loaded in agent.mcp_configs.values():
        if loaded.config is None or loaded.config.auth is None:
            continue
        for missing in loaded.config.auth.unresolved_env(environ=environ):
            bag.warning(
                "mcp.unset-credential",
                f"{loaded.name} needs environment variable {missing} to authenticate",
                path=loaded.path,
                hint=f"export {missing} before running this agent",
            )


def _check_layout(agent: LoadedAgent, bag: DiagnosticBag) -> None:
    if not agent.has_readme:
        bag.info(
            "layout.no-readme",
            "no README.md; the spec says one is generated from AGENTS.md if absent",
            path=agent.root,
        )
    if not agent.has_license:
        bag.info(
            "layout.no-license",
            f"no LICENSE file for declared license {agent.manifest.license!r}",
            path=agent.root,
        )
    for version in agent.versions:
        if not is_semver(version):
            bag.warning(
                "versions.bad-name",
                f"versions/v{version}/ is not named after a semantic version",
                path=agent.root / "versions",
            )
