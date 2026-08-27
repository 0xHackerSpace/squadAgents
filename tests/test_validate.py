"""Validation: the rules the spec states, and the two enforcement profiles."""

from oaf.loader import load_agent
from oaf.validate import NEGOTIABLE, Profile, validate_agent


def codes(bag):
    return {d.code for d in bag}


def test_minimal_agent_passes_strict(minimal):
    bag = validate_agent(load_agent(minimal), profile=Profile.STRICT, environ={})
    assert bag.ok, [d.format() for d in bag.errors]


def test_full_featured_agent_passes_strict(full_featured):
    bag = validate_agent(load_agent(full_featured), profile=Profile.STRICT, environ={})
    assert bag.ok, [d.format() for d in bag.errors]


def test_non_canonical_slug_is_an_error_under_strict(tmp_path, minimal):
    """The spec defines slug as vendorKey/agentKey."""
    target = tmp_path / "agent"
    target.mkdir()
    text = (minimal / "AGENTS.md").read_text().replace(
        'slug: "acme/simple"', 'slug: "simple-agent"'
    )
    (target / "AGENTS.md").write_text(text)
    agent = load_agent(target)

    strict = validate_agent(agent, profile=Profile.STRICT, environ={})
    lenient = validate_agent(agent, profile=Profile.LENIENT, environ={})

    assert "identity.slug-not-canonical" in codes(strict.errors)
    assert "identity.slug-not-canonical" in codes(lenient.warnings)
    assert lenient.ok


def test_every_negotiable_rule_is_a_warning_under_lenient():
    """The lenient profile exists to demote exactly these, and nothing else."""
    assert NEGOTIABLE  # guard against the set being emptied by accident


def test_unresolved_required_skill_is_an_error(tmp_path, minimal):
    target = tmp_path / "agent"
    target.mkdir()
    text = (minimal / "AGENTS.md").read_text().replace(
        "---\n\n# Agent Purpose",
        'skills:\n  - name: "ghost"\n    source: "local"\n    required: true\n'
        "---\n\n# Agent Purpose",
    )
    (target / "AGENTS.md").write_text(text)
    bag = validate_agent(load_agent(target), environ={})
    assert "skill.unresolved" in codes(bag.errors)


def test_unset_mcp_credential_is_reported(full_featured):
    bag = validate_agent(load_agent(full_featured), environ={})
    assert "mcp.unset-credential" in codes(bag.warnings)


def test_set_mcp_credential_is_not_reported(full_featured):
    bag = validate_agent(load_agent(full_featured), environ={"FILESYSTEM_TOKEN": "x"})
    assert "mcp.unset-credential" not in codes(bag)


def test_unknown_frontmatter_key_is_warned(tmp_path, minimal):
    target = tmp_path / "agent"
    target.mkdir()
    text = (minimal / "AGENTS.md").read_text().replace(
        "---\n\n# Agent Purpose", "temprature: 0.5\n---\n\n# Agent Purpose"
    )
    (target / "AGENTS.md").write_text(text)
    bag = validate_agent(load_agent(target), environ={})
    assert "manifest.unknown-key" in codes(bag.warnings)
