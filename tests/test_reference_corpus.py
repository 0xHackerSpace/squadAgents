"""Conformance against the agents published alongside the specification.

These are the only real OAF agents that exist, and they deviate from the spec in
four documented ways. The suite pins both facts: every one of them must load and
pass the lenient profile, and each deviation must be the specific diagnostic the
harness claims it is.

Skipped when the corpus is not checked out on this machine.
"""

import os
from pathlib import Path

import pytest

from oaf.resolve import Workspace, resolve_agent
from oaf.validate import Profile, validate_agent

#: Where the agents published with the specification are checked out. Point
#: OAF_REFERENCE_CORPUS at your own clone to run this suite elsewhere.
REFERENCE_CORPUS = Path(
    os.environ.get(
        "OAF_REFERENCE_CORPUS", "/home/user/jeffrschneider/openharness/examples"
    )
)

pytestmark = pytest.mark.skipif(
    not REFERENCE_CORPUS.is_dir(), reason="reference corpus not available"
)

EXPECTED_AGENTS = 9


@pytest.fixture(scope="module")
def corpus():
    return Workspace.from_path(REFERENCE_CORPUS)


def test_every_reference_agent_is_discovered(corpus):
    assert len(corpus.agents) == EXPECTED_AGENTS


def test_every_reference_agent_passes_lenient(corpus):
    for agent in corpus.agents:
        bag = validate_agent(agent, profile=Profile.LENIENT, environ={})
        assert bag.ok, f"{agent.canonical_slug}: {[d.format() for d in bag.errors]}"


def test_strict_flags_only_the_known_deviations(corpus):
    """Under strict, nothing unexpected should surface."""
    known = {"identity.slug-not-canonical", "orchestration.bare-key"}
    for agent in corpus.agents:
        bag = validate_agent(agent, profile=Profile.STRICT, environ={})
        assert {d.code for d in bag.errors} <= known, agent.canonical_slug


def test_bare_slug_deviation_is_detected(corpus):
    agent = corpus.get("openharness/recipe-finder")
    assert agent.manifest.slug == "recipe-finder-agent"
    assert agent.manifest.canonical_slug == "openharness/recipe-finder"


def test_top_level_entrypoint_is_lifted(corpus):
    agent = corpus.get("openharness/recipe-finder")
    assert agent.manifest.lifted_orchestration_keys == ["entrypoint"]
    assert agent.manifest.orchestration.entrypoint == "structured"


def test_reference_dialect_mcp_files_are_normalized(corpus):
    agent = corpus.get("openharness/recipe-finder")
    mcp = agent.mcp_configs["recipe-api"]
    assert mcp.active.dialect == "reference"
    assert mcp.config.dialect == "reference"
    assert mcp.active.enabled_tool_names == [
        "recipes.search", "recipes.get", "recipes.random"
    ]
    assert not mcp.permits("recipes.delete")
    assert not mcp.permits("admin.anything")
    assert mcp.config.auth.env_var == "RECIPE_API_KEY"


def test_frontmatterless_skill_is_accepted_with_a_warning(corpus):
    agent = corpus.get("openharness/trip-coordinator")
    skill = agent.skills["travel-planning"]
    assert skill.document.frontmatter_present is False
    assert "skill.no-frontmatter" in {d.code for d in agent.diagnostics}


def test_multi_agent_package_resolves_as_one_workspace(corpus):
    resolved = resolve_agent(corpus.get("openharness/trip-coordinator"), workspace=corpus)
    assert not resolved.diagnostics.errors


def test_every_reference_agent_builds_a_prompt(corpus):
    from oaf.runtime import get_adapter

    adapter = get_adapter("dry-run", environ={})
    for agent in corpus.agents:
        built = adapter.build(resolve_agent(agent, workspace=corpus))
        assert built.system_prompt.strip()
        assert built.model.name
