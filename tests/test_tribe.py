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

CATEGORIAS = ("infra", "dados", "suporte")

#: The three prefixes, kept apart on purpose: a coordinator and its specialists
#: do not share a slug stem today. Deriving one from the other would hide that.
COORDENADORES = {f"tribe/coord-{c}" for c in CATEGORIAS}
ORQUESTRADORES = {f"tribe/orq-{c}" for c in CATEGORIAS}
RESPONSE = "tribe/coord-response"


def coordenador(categoria: str) -> str:
    return f"tribe/coord-{categoria}"


def especialista(categoria: str, papel: str) -> str:
    return f"tribe/{categoria}-{papel}"

#: Every squad must field these two roles. The requirement is the squad's shape,
#: not a suggestion — a squad missing either fails to resolve.
PAPEIS_OBRIGATORIOS = ("planner", "validator")


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


def test_the_tribe_holds_every_agent_its_shape_requires(workspace):
    esperado = {"tribe/manager", RESPONSE} | ORQUESTRADORES | COORDENADORES | {
        especialista(c, papel) for c in CATEGORIAS for papel in PAPEIS_OBRIGATORIOS
    }
    assert {a.canonical_slug for a in workspace.agents} == esperado


def test_every_tribe_agent_passes_strict(workspace):
    for agent in workspace.agents:
        bag = validate_agent(agent, profile=Profile.STRICT, environ={})
        assert bag.ok, f"{agent.canonical_slug}: {[d.format() for d in bag.errors]}"


def test_the_manager_routes_to_the_orchestrators_not_the_coordinators(manager):
    """Triage names an orchestrator; the orchestrator carries the category policy."""
    assert {s.ref.slug for s in manager.sub_agents} == ORQUESTRADORES
    for sub in manager.sub_agents:
        assert sub.resolved
        # A missing orchestrator must fail loudly, not silently narrow the routing.
        assert sub.ref.required


def test_each_orchestrator_leads_exactly_its_coordinator(workspace):
    for categoria in CATEGORIAS:
        resolved = resolve_agent(workspace.get(f"tribe/orq-{categoria}"), workspace=workspace)
        refs = [s.ref for s in resolved.sub_agents]
        assert [r.slug for r in refs] == [coordenador(categoria)], categoria
        assert refs[0].required


def test_orchestrators_are_ephemeral(workspace):
    """No memory, and nothing that changes the world on its own."""
    for slug in ORQUESTRADORES:
        manifest = workspace.get(slug).manifest
        assert manifest.memory is None, f"{slug} declares memory"
        assert "bash" in manifest.config.tools.denied
        assert "web_fetch" in manifest.config.tools.denied
        assert manifest.config.temperature == 0.0


def test_every_squad_fields_a_planner_and_a_validator(workspace):
    """The shape every squad must have, asserted per squad rather than in prose."""
    for categoria in CATEGORIAS:
        resolved = resolve_agent(workspace.get(coordenador(categoria)), workspace=workspace)
        por_papel = {s.ref.role: s for s in resolved.sub_agents}

        for papel in PAPEIS_OBRIGATORIOS:
            assert papel in por_papel, f"{categoria} has no {papel}"
            sub = por_papel[papel]
            assert sub.resolved, f"{categoria}'s {papel} does not resolve"
            # A squad missing half its shape must fail, not quietly degrade.
            assert sub.ref.required
            assert sub.ref.slug == especialista(categoria, papel)


def test_the_planner_is_declared_before_the_validator(workspace):
    """Order in `agents:` is the documented reading order: plan, then judge."""
    for slug in COORDENADORES:
        resolved = resolve_agent(workspace.get(slug), workspace=workspace)
        papeis = [s.ref.role for s in resolved.sub_agents]
        assert papeis == ["planner", "validator", "coordenador-resposta"], slug


def test_every_squad_calls_the_response_coordinator(workspace):
    """A squad that finished has to hand the outcome somewhere."""
    for slug in COORDENADORES:
        resolved = resolve_agent(workspace.get(slug), workspace=workspace)
        responder = next(s for s in resolved.sub_agents if s.ref.slug == RESPONSE)
        assert responder.resolved
        assert responder.ref.required


def test_planners_and_validators_are_stateless_leaves(workspace):
    """R6: a specialist holds no state, and does not delegate onward."""
    for categoria in CATEGORIAS:
        for papel in PAPEIS_OBRIGATORIOS:
            agent = workspace.get(especialista(categoria, papel))
            nome = especialista(categoria, papel)
            assert agent.manifest.memory is None, f"{nome} declares memory"
            assert agent.manifest.agents == [], f"{nome} delegates onward"


def test_no_planner_or_validator_may_run_shell_commands(workspace):
    for categoria in CATEGORIAS:
        for papel in PAPEIS_OBRIGATORIOS:
            manifest = workspace.get(especialista(categoria, papel)).manifest
            assert "bash" in manifest.config.tools.denied


def test_validators_judge_deterministically(workspace):
    """A verdict that varies between runs is not a verdict."""
    for categoria in CATEGORIAS:
        assert workspace.get(
            especialista(categoria, "validator")
        ).manifest.config.temperature == 0.0


def test_every_validator_carries_its_category_checklist(workspace):
    """The domain knowledge lives in a skill, loaded on demand."""
    for categoria in CATEGORIAS:
        resolved = resolve_agent(
            workspace.get(especialista(categoria, "validator")), workspace=workspace
        )
        skill = next(s for s in resolved.skills if s.ref.name == f"checklist-{categoria}")
        assert skill.ref.required
        assert skill.local is not None


def test_a_validator_does_not_rewrite_the_plan(workspace):
    """Separation of powers: whoever plans does not approve their own plan.

    Whitespace is normalized before matching — the phrase wraps across lines in
    the manifests, and line wrapping is formatting, not behaviour.
    """
    import re

    for categoria in CATEGORIAS:
        prompt = build_system_prompt(resolve_agent(
            workspace.get(especialista(categoria, "validator")), workspace=workspace
        ))
        assert "não corrijo o plano" in re.sub(r"\s+", " ", prompt).lower(), categoria


def test_a_planner_does_not_approve_its_own_plan(workspace):
    """The other half of the same separation."""
    import re

    for categoria in CATEGORIAS:
        prompt = build_system_prompt(resolve_agent(
            workspace.get(especialista(categoria, "planner")), workspace=workspace
        ))
        normalizado = re.sub(r"\s+", " ", prompt).lower()
        assert "não valido meu" in normalizado, categoria
        assert especialista(categoria, "validator") in normalizado, categoria


def test_the_response_coordinator_is_terminal(workspace):
    """This is what keeps the graph acyclic.

    The responder names the next coordinator in its JSON; it does not call one.
    Declaring `agents:` here while the squads declare it there would make the
    pair mutual, and the resolver rejects that — see the test below.
    """
    responder = workspace.get(RESPONSE)
    assert responder.manifest.agents == []
    assert not resolve_agent(responder, workspace=workspace).sub_agents


def test_a_mutual_reference_would_be_rejected(tmp_path, workspace):
    """Pins the reason the responder is terminal, rather than asserting it."""
    template = (TRIBE / "coord-response" / "AGENTS.md").read_text(encoding="utf-8")
    head, _, body = template.partition("\n---\n\n")

    par = tmp_path / "coord-response"
    par.mkdir()
    # Give the responder a reference back to a squad that already points at it.
    (par / "AGENTS.md").write_text(
        head.replace(
            "model:\n  provider:",
            'agents:\n  - vendor: "tribe"\n    agent: "coord-infra"\n    version: "1.0.0"\n'
            '    role: "volta"\n    required: true\n\nmodel:\n  provider:',
            1,
        )
        + "\n---\n\n"
        + body
    )

    mutuo = Workspace.from_path(tmp_path)
    for agent in workspace.agents:
        mutuo.add(agent)
    mutuo.add(load_agent(par))

    resolved = resolve_agent(mutuo.get("tribe/coord-infra"), workspace=mutuo)
    assert "agent.cycle" in {d.code for d in resolved.diagnostics.errors}


def test_the_tribe_is_four_layers_deep(manager):
    """manager → orquestrador → coordenador → especialista."""
    profundidades = []

    def desce(ag, n=1):
        profundidades.append(n)
        for s in ag.sub_agents:
            if s.agent is not None:
                desce(s.agent, n + 1)

    desce(manager)
    assert max(profundidades) == 4


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


def test_every_destination_in_the_schema_is_an_orchestrator(schema):
    """Triage routes to layer 2, never straight into a squad."""
    destinos = set(schema["properties"]["destino"]["enum"]) - {"nenhum"}
    assert destinos == ORQUESTRADORES


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
        '```json\n{"categoria": "suporte", "destino": "tribe/coord-suporte"}\n```\n'
        "\n---\n\nContenção: reiniciar o serviço de checkout.\n"
    )
    assert extract(reply) == {"categoria": "suporte", "destino": "tribe/coord-suporte"}


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
        "Orquestrador de Infraestrutura", "Orquestrador de Dados",
        "Orquestrador de Suporte",
    ]
    assert [getattr(t, "__name__", t) for t in built.agent.tools] == ["load_skill"]

    for orquestrador in built.agent.members:
        # Each orchestrator leads exactly one coordinator.
        assert type(orquestrador).__name__ == "Team"
        assert len(orquestrador.members) == 1

        # And each coordinator is itself a team: planner, validator, responder.
        coordenador = orquestrador.members[0]
        assert type(coordenador).__name__ == "Team"
        nomes = [m.name for m in coordenador.members]
        assert len(nomes) == 3, nomes
        assert any("Planner" in n for n in nomes), nomes
        assert any("Validator" in n for n in nomes), nomes
        assert nomes[-1] == "Coordenador de Resposta"


def test_the_taxonomy_body_stays_out_of_the_initial_prompt(manager, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    built = get_adapter("agno").build(manager)

    assert "Fronteiras que confundem" not in built.system_prompt
    load_skill = next(t for t in built.agent.tools if t.__name__ == "load_skill")
    assert "Fronteiras que confundem" in load_skill("taxonomia")


# --- the response coordinator's contract -------------------------------------

RESP_SKILL = TRIBE / "coord-response" / "skills" / "politica-resposta"
RESP_EXEMPLOS = RESP_SKILL / "resources" / "exemplos.md"

#: Every field the responder's JSON must carry.
RESP_CAMPOS = {
    "correlacao", "decisao", "destino", "handoff_n",
    "motivo", "mensagem_usuario", "contexto_handoff",
}
MAX_HANDOFF = 2


@pytest.fixture(scope="module")
def responder(workspace):
    return resolve_agent(workspace.get(RESPONSE), workspace=workspace)


def _resp_examples() -> list[dict]:
    import re

    text = RESP_EXEMPLOS.read_text(encoding="utf-8")
    return [json.loads(b) for b in re.findall(r"```json\n(.*?)\n```", text, re.S)]


def test_the_responder_prompt_states_every_field(responder):
    prompt = build_system_prompt(responder)
    for field in RESP_CAMPOS:
        assert field in prompt, f"the prompt never mentions {field!r}"
    for decisao in ("notificar", "encaminhar"):
        assert decisao in prompt


def test_the_responder_carries_its_policy_skill(responder):
    skill = next(s for s in responder.skills if s.ref.name == "politica-resposta")
    assert skill.ref.required
    assert skill.local is not None


def test_the_policy_body_stays_out_of_the_initial_prompt(responder):
    prompt = build_system_prompt(responder)
    assert "politica-resposta" in prompt
    assert "O limite de dois encaminhamentos" not in prompt


def test_the_examples_cover_both_decisions():
    examples = _resp_examples()
    assert len(examples) >= 4
    assert any(e["decisao"] == "notificar" for e in examples)
    assert any(e["decisao"] == "encaminhar" for e in examples)
    assert any(e["handoff_n"] == MAX_HANDOFF for e in examples), "no example at the limit"


@pytest.mark.parametrize("example", _resp_examples(), ids=lambda e: e["decisao"])
def test_each_response_example_matches_the_contract(example):
    assert set(example) == RESP_CAMPOS
    assert example["decisao"] in {"notificar", "encaminhar"}
    assert 0 <= example["handoff_n"] <= MAX_HANDOFF
    assert example["motivo"]


@pytest.mark.parametrize("example", _resp_examples(), ids=lambda e: e["decisao"])
def test_each_response_example_obeys_the_invariants(example):
    if example["decisao"] == "notificar":
        assert example["destino"] is None
        assert example["contexto_handoff"] is None
        assert example["mensagem_usuario"], "notifying with no message says nothing"
    else:
        assert example["destino"] in COORDENADORES
        assert example["contexto_handoff"], "a handoff with no context restarts the work"
        assert example["mensagem_usuario"] is None
        # Handing off at the limit is exactly what the limit forbids.
        assert example["handoff_n"] < MAX_HANDOFF


def test_at_the_limit_the_example_notifies():
    """The rule that stops a request circling between teams."""
    no_limite = [e for e in _resp_examples() if e["handoff_n"] == MAX_HANDOFF]
    assert no_limite
    for example in no_limite:
        assert example["decisao"] == "notificar"
        assert example["mensagem_usuario"]


def test_the_user_message_names_no_agent():
    """The user does not know the tribe exists."""
    for example in _resp_examples():
        mensagem = example["mensagem_usuario"] or ""
        for termo in ("agent-", "tribe/", "coordenador", "especialista", "squad"):
            assert termo not in mensagem.lower(), f"{termo!r} leaked into a user message"
