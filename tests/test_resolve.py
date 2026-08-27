"""Resolution: linking references, walking sub-agents, catching cycles."""

from oaf.loader import load_agent
from oaf.resolve import Workspace, resolve_agent


def test_local_skill_resolves_to_its_directory(full_featured):
    resolved = resolve_agent(load_agent(full_featured))
    csv = next(s for s in resolved.skills if s.ref.name == "csv-report")
    assert csv.local is not None
    assert csv.local.document.manifest.name == "csv-report"
    assert "template.csv" in csv.local.document.resources


def test_well_known_skill_is_deferred_not_missing(full_featured):
    resolved = resolve_agent(load_agent(full_featured))
    web = next(s for s in resolved.skills if s.ref.name == "web-search")
    assert web.deferred
    assert web.local is None


def test_mcp_config_dir_resolves_and_subsets_tools(full_featured):
    resolved = resolve_agent(load_agent(full_featured))
    entry = resolved.mcp_servers[0]
    assert entry.resolved
    # stat_file is present but disabled, so it must not reach the agent.
    assert entry.tools == ["read_file", "list_directory"]
    assert entry.loaded.permits("read_file")
    assert not entry.loaded.permits("stat_file")
    assert not entry.loaded.permits("delete_file")


def test_excluded_tool_wildcard_is_a_prefix_match(full_featured):
    """The reference agents write `admin.*`, which is meaningless as a literal."""
    resolved = resolve_agent(load_agent(full_featured))
    assert not resolved.mcp_servers[0].loaded.permits("admin.reset")


def test_sub_agent_resolves_through_the_workspace(fixtures, full_featured):
    workspace = Workspace.from_path(fixtures / "valid")
    resolved = resolve_agent(load_agent(full_featured), workspace=workspace)
    sub = resolved.sub_agents[0]
    assert sub.resolved
    assert sub.agent.slug == "acme/code-reviewer"
    assert [a.slug for a in resolved.walk()] == ["acme/data-analyst", "acme/code-reviewer"]


def test_sub_agent_outside_the_workspace_is_reported(full_featured):
    """Resolved alone, the sibling agent is not in scope."""
    resolved = resolve_agent(load_agent(full_featured), workspace=Workspace())
    assert not resolved.sub_agents[0].resolved
    assert "agent.unresolved" in {d.code for d in resolved.diagnostics}


def test_delegation_cycle_is_reported_not_hung(fixtures):
    workspace = Workspace.from_path(fixtures / "cycles")
    resolved = resolve_agent(workspace.get("acme/alpha"), workspace=workspace)
    cycles = [d for d in resolved.diagnostics if d.code == "agent.cycle"]
    assert cycles, "a cycle must be detected"
    assert "acme/alpha -> acme/beta -> acme/alpha" in cycles[0].message


def test_summary_is_json_serializable(full_featured):
    import json

    json.dumps(resolve_agent(load_agent(full_featured)).summary())


def test_bare_agent_key_claimed_by_two_vendors_is_not_guessed(tmp_path, fixtures):
    """Resolving `acme/x` must never silently land on `other/x`."""
    template = (fixtures / "valid" / "sub-agent" / "AGENTS.md").read_text()
    for vendor in ("acme", "other"):
        directory = tmp_path / vendor
        directory.mkdir()
        (directory / "AGENTS.md").write_text(
            template.replace('vendorKey: "acme"', f'vendorKey: "{vendor}"')
            .replace('slug: "acme/code-reviewer"', 'slug: "code-reviewer"')
        )

    workspace = Workspace.from_path(tmp_path)
    assert workspace.is_ambiguous("code-reviewer")
    assert workspace.get("code-reviewer") is None
    # Each canonical slug still resolves to its own agent.
    assert workspace.get("acme/code-reviewer").manifest.vendor_key == "acme"
    assert workspace.get("other/code-reviewer").manifest.vendor_key == "other"


def test_ambiguous_sub_agent_reference_is_reported(tmp_path, fixtures):
    template = (fixtures / "valid" / "sub-agent" / "AGENTS.md").read_text()
    for vendor in ("acme", "other"):
        directory = tmp_path / vendor
        directory.mkdir()
        (directory / "AGENTS.md").write_text(
            template.replace('vendorKey: "acme"', f'vendorKey: "{vendor}"')
            .replace('slug: "acme/code-reviewer"', 'slug: "code-reviewer"')
        )
    caller = tmp_path / "caller"
    caller.mkdir()
    (caller / "AGENTS.md").write_text(
        (fixtures / "valid" / "minimal" / "AGENTS.md").read_text().replace(
            "---\n\n# Agent Purpose",
            'agents:\n  - vendor: "ghost"\n    agent: "code-reviewer"\n'
            '    version: "1.0.0"\n    required: true\n---\n\n# Agent Purpose',
        )
    )

    workspace = Workspace.from_path(tmp_path)
    resolved = resolve_agent(load_agent(caller), workspace=workspace)
    assert "agent.ambiguous" in {d.code for d in resolved.diagnostics.errors}
