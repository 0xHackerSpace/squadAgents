"""The infrastructure squad shipped in `squad/`.

This is the repository's own use case, so its wiring is pinned like any other
contract: the gate runs before the generator, each agent carries the skill it
needs, and the whole thing builds as one team.
"""

from pathlib import Path

import pytest

from oaf.loader import load_agent
from oaf.resolve import Workspace, resolve_agent
from oaf.runtime import build_system_prompt, get_adapter
from oaf.validate import Profile, validate_agent

SQUAD = Path(__file__).resolve().parent.parent / "squad"

pytestmark = pytest.mark.skipif(not SQUAD.is_dir(), reason="squad/ not present")


@pytest.fixture(scope="module")
def workspace():
    return Workspace.from_path(SQUAD)


@pytest.fixture(scope="module")
def orchestrador(workspace):
    return resolve_agent(load_agent(SQUAD / "orchestrador"), workspace=workspace)


def test_the_squad_has_three_agents(workspace):
    assert {a.canonical_slug for a in workspace.agents} == {
        "squad/orchestrador", "squad/validador", "squad/terraform"
    }


def test_every_squad_agent_passes_strict(workspace):
    """The squad is authored here, so it is held to the spec as written."""
    for agent in workspace.agents:
        bag = validate_agent(agent, profile=Profile.STRICT, environ={})
        assert bag.ok, f"{agent.canonical_slug}: {[d.format() for d in bag.errors]}"


def test_both_members_resolve_and_are_required(orchestrador):
    by_role = {s.ref.role: s for s in orchestrador.sub_agents}
    assert set(by_role) == {"gate", "gerador"}
    for sub in orchestrador.sub_agents:
        assert sub.resolved, sub.ref.slug
        # A missing member must fail loudly rather than degrade into a
        # single-agent flow that silently skips validation.
        assert sub.ref.required


def test_the_gate_is_declared_before_the_generator(orchestrador):
    """Order in `agents:` is the documented reading order of the flow."""
    assert [s.ref.agent for s in orchestrador.sub_agents] == ["validador", "terraform"]


def test_orchestration_triggers_describe_the_flow(orchestrador):
    triggers = {t.event: t.action for t in orchestrador.manifest.orchestration.triggers}
    assert triggers == {
        "demanda-recebida": "validar-demanda",
        "demanda-aprovada": "gerar-hcl",
    }
    assert orchestrador.manifest.orchestration.fallback == "validador"


def test_each_worker_carries_its_required_skill(workspace):
    expected = {"squad/validador": "demanda-checklist", "squad/terraform": "hcl-conventions"}
    for slug, skill_name in expected.items():
        resolved = resolve_agent(workspace.get(slug), workspace=workspace)
        skill = next(s for s in resolved.skills if s.ref.name == skill_name)
        assert skill.ref.required
        assert skill.local is not None, f"{slug} cannot reach {skill_name}"


def test_no_squad_agent_may_run_shell_commands(workspace):
    """Nothing in this squad applies infrastructure, so nothing needs a shell."""
    for agent in workspace.agents:
        assert "bash" in agent.manifest.config.tools.denied, agent.canonical_slug


def test_orchestrador_prompt_states_the_delegation(orchestrador):
    prompt = build_system_prompt(orchestrador)
    assert "squad/validador (gate)" in prompt
    assert "squad/terraform (gerador)" in prompt
    assert "validar-demanda" in prompt


def test_squad_builds_as_one_agno_team(orchestrador, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    built = get_adapter("agno").build(orchestrador)

    assert type(built.agent).__name__ == "Team"
    assert [m.name for m in built.agent.members] == [
        "Validador de Demanda", "Gerador Terraform"
    ]
    # Each worker gets load_skill; the leader has no skills of its own.
    for member in built.agent.members:
        assert [getattr(t, "__name__", t) for t in member.tools] == ["load_skill"]


def test_workers_can_read_their_own_skill_bodies(orchestrador, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    built = get_adapter("agno").build(orchestrador)

    validador = built.agent.members[0]
    load_skill = next(t for t in validador.tools if t.__name__ == "load_skill")
    body = load_skill("demanda-checklist")
    assert "Campos obrigatórios" in body
    assert "0.0.0.0/0" in body
