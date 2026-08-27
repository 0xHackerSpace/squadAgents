"""The example gallery under examples/agents/.

Examples that stop working are worse than no examples, so each one's claim to
teach a feature is asserted here rather than trusted.
"""

import json
from pathlib import Path

import pytest

from oaf.loader import load_agent
from oaf.resolve import Workspace, resolve_agent
from oaf.runtime import build_system_prompt, get_adapter
from oaf.validate import Profile, validate_agent

GALLERY = Path(__file__).resolve().parent.parent / "examples" / "agents"

pytestmark = pytest.mark.skipif(not GALLERY.is_dir(), reason="examples/agents/ not present")

#: Directory name → the slug it must declare.
EXPECTED = {
    "01-revisor-pr": "exemplo/revisor-pr",
    "02-tradutor": "exemplo/tradutor-tecnico",
    "03-analista-csv": "exemplo/analista-csv",
    "04-triagem-issues": "exemplo/triagem-issues",
    "05-diario-bordo": "exemplo/diario-bordo",
    "06-portavel": "exemplo/escritor-changelog",
}


@pytest.fixture(scope="module")
def workspace():
    return Workspace.from_path(GALLERY)


def test_the_gallery_holds_the_expected_agents(workspace):
    assert {a.canonical_slug for a in workspace.agents} == set(EXPECTED.values())


def test_every_example_passes_strict(workspace):
    """Examples are copied as starting points, so they must be exemplary."""
    for agent in workspace.agents:
        bag = validate_agent(agent, profile=Profile.STRICT, environ={})
        assert bag.ok, f"{agent.canonical_slug}: {[d.format() for d in bag.errors]}"


def test_every_example_is_listed_in_the_readme():
    readme = (GALLERY / "README.md").read_text(encoding="utf-8")
    for directory in EXPECTED:
        assert f"({directory})" in readme, f"{directory} is not linked from the gallery index"


# --- 01: the minimum ---------------------------------------------------------


def test_minimum_example_is_a_single_file():
    files = [p for p in (GALLERY / "01-revisor-pr").rglob("*") if p.is_file()]
    assert [p.name for p in files] == ["AGENTS.md"]


def test_minimum_example_falls_back_to_the_default_model():
    """It declares no `model:`, which is the point the README makes about it."""
    from oaf.runtime import resolve_model

    manifest = load_agent(GALLERY / "01-revisor-pr").manifest
    assert manifest.model is None
    assert resolve_model(manifest, environ={}).origin == "default"


# --- 02: the simplified format ----------------------------------------------


def test_the_two_instruction_formats_are_both_demonstrated():
    structured = load_agent(GALLERY / "01-revisor-pr")
    direct = load_agent(GALLERY / "02-tradutor")
    assert structured.document.instruction_format == "structured"
    assert direct.document.instruction_format == "system-prompt"


def test_simplified_example_uses_a_spec_model_alias():
    from oaf.models.agent import MODEL_ALIASES

    assert load_agent(GALLERY / "02-tradutor").manifest.model_alias in MODEL_ALIASES


# --- 03: a local skill -------------------------------------------------------


def test_skill_example_ships_resources_and_scripts():
    resolved = resolve_agent(load_agent(GALLERY / "03-analista-csv"))
    skill = resolved.skills[0]
    assert skill.ref.required
    assert skill.local is not None
    assert skill.local.document.resources and skill.local.document.scripts


def test_skill_body_stays_out_of_the_progressive_prompt():
    """The whole point of progressive disclosure, asserted on a real example."""
    resolved = resolve_agent(load_agent(GALLERY / "03-analista-csv"))
    probe = "exportação truncada"  # appears only in the skill body

    progressive = build_system_prompt(resolved, skill_mode="progressive")
    eager = build_system_prompt(resolved, skill_mode="eager")

    assert probe not in progressive
    assert probe in eager
    assert len(progressive) < len(eager)
    # The index is still there, so the agent knows the skill exists.
    assert "perfil-dataset" in progressive
    assert "load_skill" in progressive


# --- 04: MCP tool subsetting -------------------------------------------------


def test_mcp_example_grants_only_read_tools():
    agent = load_agent(GALLERY / "04-triagem-issues")
    mcp = agent.mcp_configs["github"]

    assert mcp.active.enabled_tool_names == ["list_issues", "issue_read", "search_issues"]
    for denied in ("issue_write", "add_issue_comment", "merge_pull_request", "admin.reset"):
        assert not mcp.permits(denied), f"{denied} must not reach the agent"
    # Disabled rather than excluded: still off.
    assert not mcp.permits("get_label")


def test_mcp_example_keeps_its_token_in_the_environment():
    """A credential in the file would be the wrong thing to copy."""
    config = load_agent(GALLERY / "04-triagem-issues").mcp_configs["github"].config
    assert config.auth.token == "${GITHUB_TOKEN}"
    assert config.auth.unresolved_env(environ={}) == ["GITHUB_TOKEN"]


def test_mcp_example_warns_when_the_credential_is_unset():
    agent = load_agent(GALLERY / "04-triagem-issues")
    bag = validate_agent(agent, profile=Profile.STRICT, environ={})
    assert "mcp.unset-credential" in {d.code for d in bag.warnings}
    assert bag.ok, "a missing credential is a warning, not a failure"


# --- 05: memory --------------------------------------------------------------


def test_memory_example_exports_its_blocks_to_letta(tmp_path):
    from oaf.export import EXPORTERS

    resolved = resolve_agent(load_agent(GALLERY / "05-diario-bordo"))
    EXPORTERS["letta"](resolved, tmp_path)

    data = json.loads((tmp_path / "diario-bordo.af").read_text())
    assert [b["label"] for b in data["core_memory"]] == [
        "perfil_projeto", "decisoes", "pendencias"
    ]


# --- 06: portability ---------------------------------------------------------


def test_portable_example_configures_all_four_harnesses():
    manifest = load_agent(GALLERY / "06-portavel").manifest
    assert set(manifest.harness_config) == {
        "claude-code", "goose", "deep-agents", "letta"
    }


def test_goose_export_takes_only_the_goose_keys(tmp_path):
    from oaf.export import EXPORTERS
    from oaf.parse import split_frontmatter

    resolved = resolve_agent(load_agent(GALLERY / "06-portavel"))
    EXPORTERS["goose"](resolved, tmp_path)

    front = split_frontmatter(
        (tmp_path / "exemplo" / "escritor-changelog" / "AGENTS.md").read_text()
    ).data
    assert front["docker-image"] == "python:3.12-slim"
    # Nothing from the other three harnesses may leak in.
    for foreign in ("skills-middleware", "stateful", "progressive-disclosure"):
        assert foreign not in front


def test_portable_example_preserves_its_version_history():
    agent = load_agent(GALLERY / "06-portavel")
    assert list(agent.versions) == ["1.0.0"]
    assert agent.manifest.version == "1.1.0"


# --- every example must actually build --------------------------------------


def test_every_example_builds_on_agno(workspace, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    adapter = get_adapter("agno")

    for agent in workspace.agents:
        built = adapter.build(resolve_agent(agent, workspace=workspace))
        assert built.agent is not None
        assert built.system_prompt.strip()
