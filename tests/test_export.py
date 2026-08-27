"""Export: the four harness targets the spec's compatibility table names."""

import json

from oaf.export import EXPORTERS
from oaf.loader import load_agent
from oaf.parse import split_frontmatter
from oaf.resolve import Workspace, resolve_agent


def _resolved(fixtures, full_featured):
    workspace = Workspace.from_path(fixtures / "valid")
    return resolve_agent(load_agent(full_featured), workspace=workspace)


def test_every_named_target_has_an_exporter():
    assert set(EXPORTERS) == {"claude-code", "goose", "deep-agents", "letta"}


def test_claude_code_export_writes_skill_md(fixtures, full_featured, tmp_path):
    result = EXPORTERS["claude-code"](_resolved(fixtures, full_featured), tmp_path)
    skill = tmp_path / "acme" / "data-analyst" / "SKILL.md"
    assert skill.is_file()
    front = split_frontmatter(skill.read_text())
    assert front.data["name"] == "data-analyst"
    assert "allowed-tools" in front.data
    # Identity the target format cannot hold must survive in the body.
    assert "acme/data-analyst" in front.body
    assert (tmp_path / "acme/data-analyst/skills/csv-report/SKILL.md").is_file()
    assert result.notes


def test_goose_export_promotes_its_harness_config(fixtures, full_featured, tmp_path):
    EXPORTERS["goose"](_resolved(fixtures, full_featured), tmp_path)
    front = split_frontmatter((tmp_path / "acme/data-analyst/AGENTS.md").read_text())
    assert front.data["docker-image"] == "python:3.12"
    assert front.data["model"]["name"] == "gpt-5.2"


def test_deep_agents_export_splits_instructions_from_skills(
    fixtures, full_featured, tmp_path
):
    EXPORTERS["deep-agents"](_resolved(fixtures, full_featured), tmp_path)
    agent_md = (tmp_path / "data-analyst" / "agent.md").read_text()
    assert "Available Skills" not in agent_md
    assert (tmp_path / "data-analyst/skills/csv-report/SKILL.md").is_file()


def test_letta_export_writes_agent_file_json(fixtures, full_featured, tmp_path):
    EXPORTERS["letta"](_resolved(fixtures, full_featured), tmp_path)
    data = json.loads((tmp_path / "data-analyst.af").read_text())
    assert data["llm_config"]["model"] == "gpt-5.2"
    assert {b["label"] for b in data["core_memory"]} == {"personality", "user_context"}
    assert data["metadata"]["oaf"]["slug"] == "acme/data-analyst"


def test_export_reports_what_it_could_not_carry(fixtures, full_featured, tmp_path):
    result = EXPORTERS["letta"](_resolved(fixtures, full_featured), tmp_path)
    joined = " ".join(result.notes)
    assert "pack" in joined and "weblet" in joined
