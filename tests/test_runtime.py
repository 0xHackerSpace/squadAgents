"""Runtime: model resolution and system-prompt composition."""

import pytest

from oaf.loader import load_agent
from oaf.resolve import Workspace, resolve_agent
from oaf.runtime import build_system_prompt, get_adapter, resolve_model
from oaf.runtime.models import DEFAULT_ALIASES


def test_alias_resolves_to_the_default_table(sub_agent):
    manifest = load_agent(sub_agent).manifest
    model = resolve_model(manifest, environ={})
    assert (model.provider, model.name) == DEFAULT_ALIASES["sonnet"]
    assert model.origin == "alias:sonnet"


def test_object_model_form_wins_over_inference(full_featured):
    model = resolve_model(load_agent(full_featured).manifest, environ={})
    assert model.provider == "openai"
    assert model.name == "gpt-5.2"
    assert model.embedding == "text-embedding-3-large"


def test_alias_table_is_overridable_by_environment(sub_agent):
    manifest = load_agent(sub_agent).manifest
    model = resolve_model(manifest, environ={"OAF_MODEL_SONNET": "openai/gpt-5.2"})
    assert (model.provider, model.name) == ("openai", "gpt-5.2")


def test_explicit_override_beats_the_manifest(full_featured):
    model = resolve_model(
        load_agent(full_featured).manifest, environ={}, override="anthropic/claude-opus-5"
    )
    assert model.name == "claude-opus-5"
    assert model.origin == "override"


def test_agent_with_no_model_gets_the_default(minimal):
    model = resolve_model(load_agent(minimal).manifest, environ={})
    assert model.origin == "default"


def test_progressive_prompt_lists_skills_without_inlining_them(fixtures, full_featured):
    workspace = Workspace.from_path(fixtures / "valid")
    resolved = resolve_agent(load_agent(full_featured), workspace=workspace)
    prompt = build_system_prompt(resolved, skill_mode="progressive")

    assert "### csv-report (required)" in prompt
    assert "load_skill" in prompt
    # The skill's own body must stay out of the prompt until it is asked for.
    assert "Call `scripts/summarize.py`" not in prompt


def test_eager_prompt_inlines_skill_bodies(fixtures, full_featured):
    workspace = Workspace.from_path(fixtures / "valid")
    resolved = resolve_agent(load_agent(full_featured), workspace=workspace)
    prompt = build_system_prompt(resolved, skill_mode="eager")
    assert "Call `scripts/summarize.py`" in prompt


def test_prompt_states_mcp_tools_and_denied_tools(fixtures, full_featured):
    workspace = Workspace.from_path(fixtures / "valid")
    resolved = resolve_agent(load_agent(full_featured), workspace=workspace)
    prompt = build_system_prompt(resolved)
    assert "`read_file`" in prompt
    assert "`network-scan`" in prompt


def test_dry_run_adapter_builds_without_a_model_client(fixtures, full_featured):
    workspace = Workspace.from_path(fixtures / "valid")
    resolved = resolve_agent(load_agent(full_featured), workspace=workspace)
    built = get_adapter("dry-run", environ={}).build(resolved)
    assert built.agent is None
    assert built.model.name == "gpt-5.2"
    assert [s.slug for s in built.sub_agents] == ["acme/code-reviewer"]


def test_dry_run_adapter_refuses_to_execute(fixtures, full_featured):
    from oaf.errors import HarnessError

    workspace = Workspace.from_path(fixtures / "valid")
    resolved = resolve_agent(load_agent(full_featured), workspace=workspace)
    adapter = get_adapter("dry-run", environ={})
    with pytest.raises(HarnessError):
        adapter.run(adapter.build(resolved), "hello")


def test_unknown_harness_is_reported(fixtures):
    with pytest.raises(KeyError, match="unknown harness"):
        get_adapter("nonexistent")


agno = pytest.importorskip("agno", reason="the agno runtime extra is not installed")


def test_agno_builds_a_team_when_sub_agents_exist(fixtures, full_featured, monkeypatch):
    """Sub-agent delegation maps onto an Agno Team led by this agent."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    workspace = Workspace.from_path(fixtures / "valid")
    resolved = resolve_agent(load_agent(full_featured), workspace=workspace)

    built = get_adapter("agno").build(resolved)
    assert type(built.agent).__name__ == "Team"
    assert [m.name for m in built.agent.members] == ["code-reviewer"]
    # Each agent keeps the model its own manifest asked for.
    assert built.agent.model.id == "gpt-5.2"
    assert built.agent.members[0].model.id == "claude-sonnet-5"


def test_agno_team_leader_keeps_its_tools(fixtures, full_featured, monkeypatch):
    """A leader that lost load_skill could no longer reach its own skills."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    workspace = Workspace.from_path(fixtures / "valid")
    resolved = resolve_agent(load_agent(full_featured), workspace=workspace)

    built = get_adapter("agno").build(resolved)
    names = [getattr(t, "__name__", t) for t in (built.agent.tools or [])]
    assert "load_skill" in names


def test_agno_builds_a_plain_agent_without_sub_agents(minimal, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    built = get_adapter("agno").build(resolve_agent(load_agent(minimal)))
    assert type(built.agent).__name__ == "Agent"


def test_load_skill_tool_returns_the_skill_body(fixtures, full_featured, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    workspace = Workspace.from_path(fixtures / "valid")
    resolved = resolve_agent(load_agent(full_featured), workspace=workspace)

    built = get_adapter("agno").build(resolved)
    load_skill = next(
        t for t in built.agent.tools if getattr(t, "__name__", "") == "load_skill"
    )
    assert "Call `scripts/summarize.py`" in load_skill("csv-report")
    assert "No skill named" in load_skill("nope")
