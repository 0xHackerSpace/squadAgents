"""The tribe in `tribe/`: a triage manager that classifies into JSON and routes.

The JSON contract is stated in the prompt, not enforced by the harness — the OAF
specification has no output-schema field. What can be pinned is pinned here: the
contract's own consistency, the wiring, and the extraction the caller relies on.
"""

import json
import sys
from pathlib import Path

import pytest

from oaf.loader import load_agent
from oaf.resolve import Workspace, resolve_agent
from oaf.runtime import build_system_prompt, get_adapter
from oaf.validate import Profile, validate_agent

ROOT = Path(__file__).resolve().parent.parent
TRIBE = ROOT / "tribe"
SKILL = TRIBE / "manager" / "skills" / "taxonomia"
SCHEMA = SKILL / "resources" / "triagem.schema.json"
EXEMPLOS = SKILL / "resources" / "exemplos.md"

pytestmark = pytest.mark.skipif(not TRIBE.is_dir(), reason="tribe/ not present")

SQUADS = {"tribe/infra", "tribe/dados", "tribe/suporte"}


@pytest.fixture(scope="module")
def workspace():
    return Workspace.from_path(TRIBE)


@pytest.fixture(scope="module")
def manager(workspace):
    return resolve_agent(load_agent(TRIBE / "manager"), workspace=workspace)


@pytest.fixture(scope="module")
def schema():
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


# --- wiring ------------------------------------------------------------------


def test_the_tribe_is_a_manager_and_three_squads(workspace):
    assert {a.canonical_slug for a in workspace.agents} == {"tribe/manager"} | SQUADS


def test_every_tribe_agent_passes_strict(workspace):
    for agent in workspace.agents:
        bag = validate_agent(agent, profile=Profile.STRICT, environ={})
        assert bag.ok, f"{agent.canonical_slug}: {[d.format() for d in bag.errors]}"


def test_the_manager_routes_to_all_three_squads(manager):
    assert {s.ref.slug for s in manager.sub_agents} == SQUADS
    for sub in manager.sub_agents:
        assert sub.resolved
        # A missing squad must fail loudly, not silently narrow the routing.
        assert sub.ref.required


def test_the_squads_are_terminal(workspace):
    """Only the manager delegates; a squad routing onward would loop the tribe."""
    for slug in SQUADS:
        assert not resolve_agent(workspace.get(slug), workspace=workspace).sub_agents


def test_no_tribe_agent_may_run_shell_commands(workspace):
    for agent in workspace.agents:
        assert "bash" in agent.manifest.config.tools.denied, agent.canonical_slug


def test_the_manager_classifies_deterministically(manager):
    """Classification is not a place for sampling variety."""
    assert manager.manifest.config.temperature == 0.0


# --- the JSON contract -------------------------------------------------------


def test_the_schema_is_valid_json_and_self_consistent(schema):
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])


def test_every_destination_in_the_schema_is_a_real_agent(schema):
    destinos = set(schema["properties"]["destino"]["enum"]) - {"nenhum"}
    assert destinos == SQUADS


def test_the_prompt_states_every_field_of_the_contract(manager, schema):
    """A field in the schema that the prompt never mentions will not be emitted."""
    prompt = build_system_prompt(manager)
    for field in schema["properties"]:
        assert field in prompt, f"the prompt never mentions {field!r}"


def test_the_prompt_states_every_enum_value(manager, schema):
    prompt = build_system_prompt(manager)
    for field in ("categoria", "destino", "prioridade"):
        for value in schema["properties"][field]["enum"]:
            assert value in prompt, f"{field}={value!r} is absent from the prompt"


def test_the_taxonomy_covers_every_category(schema):
    """Each category needs a routing rule, or the manager has to guess."""
    taxonomy = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    for categoria in schema["properties"]["categoria"]["enum"]:
        assert categoria in taxonomy


# --- the worked examples must obey the contract they teach -------------------


def _examples() -> list[dict]:
    import re

    blocks = re.findall(r"```json\n(.*?)\n```", EXEMPLOS.read_text(encoding="utf-8"), re.S)
    return [json.loads(b) for b in blocks]


def test_the_examples_parse_and_cover_both_outcomes():
    examples = _examples()
    assert len(examples) >= 5
    assert any(e["acionavel"] for e in examples)
    assert any(not e["acionavel"] for e in examples), "no non-actionable example"


@pytest.mark.parametrize("example", _examples(), ids=lambda e: e["subcategoria"])
def test_each_example_matches_the_schema(example, schema):
    assert set(example) == set(schema["required"])
    for field in ("categoria", "destino", "prioridade"):
        assert example[field] in schema["properties"][field]["enum"]
    assert 0.0 <= example["confianca"] <= 1.0
    assert isinstance(example["acionavel"], bool)


@pytest.mark.parametrize("example", _examples(), ids=lambda e: e["subcategoria"])
def test_each_example_obeys_the_invariants(example):
    """The rules the manifest calls invariants, checked on the material that teaches them."""
    if example["acionavel"]:
        assert example["destino"] != "nenhum"
        assert example["lacunas"] == []
    else:
        assert example["destino"] == "nenhum"
        assert example["lacunas"], "a non-actionable classification must say what is missing"

    if example["confianca"] < 0.6:
        assert not example["acionavel"], "low confidence must not be actionable"

    if example["categoria"] == "fora_de_escopo":
        assert example["destino"] == "nenhum"
        assert not example["acionavel"]


# --- extraction, which the caller depends on ---------------------------------


@pytest.fixture(scope="module")
def extract():
    sys.path.insert(0, str(ROOT / "examples"))
    from run_tribe import extract_classification

    return extract_classification


def test_extraction_finds_the_leading_json_block(extract):
    reply = (
        '```json\n{"categoria": "suporte", "destino": "tribe/suporte"}\n```\n'
        "\n---\n\nContenção: reiniciar o serviço de checkout.\n"
    )
    assert extract(reply) == {"categoria": "suporte", "destino": "tribe/suporte"}


def test_extraction_reports_absence_rather_than_raising(extract):
    """The model was asked for JSON; asking is not the same as getting."""
    assert extract("Classifiquei como suporte, prioridade alta.") is None
    assert extract("```json\n{nao e json}\n```") is None
    assert extract('```json\n"apenas uma string"\n```') is None


def test_extraction_survives_prose_before_the_block(extract):
    """Instructed not to, models still preamble. Extraction must not break on it."""
    reply = 'Segue a classificação:\n\n```json\n{"categoria": "dados"}\n```\n'
    assert extract(reply) == {"categoria": "dados"}


# --- it must actually build --------------------------------------------------


def test_the_tribe_builds_as_one_agno_team(manager, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    built = get_adapter("agno").build(manager)

    assert type(built.agent).__name__ == "Team"
    assert [m.name for m in built.agent.members] == [
        "Squad de Infraestrutura", "Squad de Dados", "Squad de Suporte"
    ]
    assert [getattr(t, "__name__", t) for t in built.agent.tools] == ["load_skill"]


def test_the_taxonomy_body_stays_out_of_the_initial_prompt(manager, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    built = get_adapter("agno").build(manager)

    assert "Fronteiras que confundem" not in built.system_prompt
    load_skill = next(t for t in built.agent.tools if t.__name__ == "load_skill")
    assert "Fronteiras que confundem" in load_skill("taxonomia")
