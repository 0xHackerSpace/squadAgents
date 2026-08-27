"""Parsing: frontmatter splitting and the two instruction formats."""

import pytest

from oaf.errors import ParseError
from oaf.parse import parse_agents_md, parse_skill_md, split_frontmatter


def test_splits_frontmatter_from_body():
    front = split_frontmatter('---\nname: "X"\n---\n\n# Body\n')
    assert front.data == {"name": "X"}
    assert front.body.strip() == "# Body"


def test_no_frontmatter_is_not_an_error():
    front = split_frontmatter("# Just markdown\n")
    assert front.data == {}
    assert front.body.startswith("# Just markdown")


def test_unclosed_frontmatter_is_an_error(fixtures):
    with pytest.raises(ParseError, match="never closed"):
        parse_agents_md(fixtures / "invalid" / "unclosed-frontmatter" / "AGENTS.md")


def test_invalid_yaml_reports_a_line(fixtures):
    with pytest.raises(ParseError) as exc:
        parse_agents_md(fixtures / "invalid" / "bad-yaml" / "AGENTS.md")
    assert exc.value.line is not None


def test_missing_required_fields_names_every_one(fixtures):
    with pytest.raises(ParseError) as exc:
        parse_agents_md(fixtures / "invalid" / "missing-required" / "AGENTS.md")
    message = str(exc.value)
    for field in ("vendorKey", "agentKey", "slug", "author", "license"):
        assert field in message


def test_non_semver_version_is_rejected(fixtures):
    with pytest.raises(ParseError, match="semantic version"):
        parse_agents_md(fixtures / "invalid" / "bad-version" / "AGENTS.md")


def test_agents_md_without_frontmatter_is_rejected(fixtures):
    with pytest.raises(ParseError, match="requires YAML frontmatter"):
        parse_agents_md(fixtures / "invalid" / "no-frontmatter" / "AGENTS.md")


def test_structured_format_is_detected(minimal):
    document = parse_agents_md(minimal / "AGENTS.md")
    assert document.instruction_format == "structured"
    assert "Core Responsibilities" in document.sections()


def test_system_prompt_format_is_detected(sub_agent):
    """The spec: a body starting with '#' is structured, otherwise a prompt."""
    document = parse_agents_md(sub_agent / "AGENTS.md")
    assert document.instruction_format == "system-prompt"
    assert document.system_prompt.startswith("You are a code reviewer.")


def test_yaml_float_version_is_read_as_text():
    """`version: 1.0` parses as a float in YAML; it must not become '1.0' silently."""
    with pytest.raises(ParseError, match="semantic version"):
        from oaf.models.agent import AgentManifest
        from pydantic import ValidationError

        try:
            AgentManifest.model_validate(
                {
                    "name": "X", "vendorKey": "a", "agentKey": "b",
                    "version": 1.0, "slug": "a/b", "description": "d" * 60,
                    "author": "@a", "license": "MIT",
                }
            )
        except ValidationError as exc:
            raise ParseError(str(exc)) from exc


def test_skill_without_frontmatter_infers_a_manifest(tmp_path):
    """Several published SKILL.md files carry no frontmatter at all."""
    skill_dir = tmp_path / "travel-planning"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "# Travel Planning Skill\n\nCore knowledge for planning itineraries.\n"
    )
    document = parse_skill_md(skill_dir / "SKILL.md")
    assert document.frontmatter_present is False
    assert document.manifest.name == "travel-planning"
    assert "Core knowledge" in document.manifest.description
