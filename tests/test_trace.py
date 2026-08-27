"""The execution trace: evidence of what the harness did.

The SDD's §5.5 separates a log an agent writes about itself — an assertion —
from a trace the harness records — evidence. These tests hold the evidence side
to what it claims, including the boundary of what it does not capture.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from oaf.loader import load_agent
from oaf.resolve import Workspace, resolve_agent
from oaf.runtime import get_adapter
from oaf.runtime.trace import (
    Trace,
    TraceEvent,
    group_by_correlation,
    new_correlation,
    read_trail,
)

TRIBE = Path(__file__).resolve().parent.parent / "tribe"


@pytest.fixture
def relogio():
    """A clock that advances one second per read, so ordering is observable."""
    estado = {"t": datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)}

    def tick():
        agora = estado["t"]
        estado["t"] = agora + timedelta(seconds=1)
        return agora

    return tick


@pytest.fixture
def trace(relogio):
    return Trace(correlacao="K", clock=relogio)


# --- the event itself ---------------------------------------------------------


def test_an_event_carries_its_correlation(trace):
    event = trace.record("build", "tribe/manager")
    assert event.correlacao == "K"
    assert event.kind == "build"
    assert event.seq == 0


def test_timestamps_are_iso_utc_with_milliseconds(trace):
    event = trace.record("build", "a")
    assert event.ts == "2026-08-27T12:00:00.000Z"


def test_seq_is_monotonic_even_within_one_millisecond():
    """Two events in the same millisecond must still have a total order."""
    fixo = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)
    trace = Trace(correlacao="K", clock=lambda: fixo)
    eventos = [trace.record("build", f"a{i}") for i in range(3)]

    assert [e.seq for e in eventos] == [0, 1, 2]
    assert len({e.ts for e in eventos}) == 1


def test_absent_fields_are_omitted_from_json(trace):
    data = json.loads(trace.record("build", "a").to_json())
    assert "contraparte" not in data
    assert "duracao_ms" not in data


def test_a_correlation_id_is_unique():
    assert new_correlation() != new_correlation()


# --- tracing a build ----------------------------------------------------------


@pytest.fixture
def tribe_traced(relogio):
    workspace = Workspace.from_path(TRIBE)
    resolved = resolve_agent(load_agent(TRIBE / "manager"), workspace=workspace)
    trace = Trace(correlacao="K", clock=relogio)
    get_adapter("dry-run", environ={}, trace=trace).build(resolved)
    return trace, resolved


@pytest.mark.skipif(not TRIBE.is_dir(), reason="tribe/ not present")
def test_the_trace_records_every_agent_built(tribe_traced):
    trace, resolved = tribe_traced
    # tribe/response is built once per coordinator, so builds exceed unique agents.
    assert set(trace.agents) == {a.slug for a in resolved.walk()}
    assert len(trace.agents) > len(set(trace.agents)), "response is built per caller"


@pytest.mark.skipif(not TRIBE.is_dir(), reason="tribe/ not present")
def test_the_trace_records_every_delegation_edge(tribe_traced):
    trace, resolved = tribe_traced

    esperado = set()
    for agent in resolved.walk():
        for sub in agent.sub_agents:
            if sub.agent is not None:
                esperado.add((agent.slug, sub.agent.slug))

    assert set(trace.edges) == esperado


@pytest.mark.skipif(not TRIBE.is_dir(), reason="tribe/ not present")
def test_depth_matches_the_layer(tribe_traced):
    """manager at 0, orchestrator at 1, coordinator at 2, specialist at 3."""
    trace, _ = tribe_traced
    profundidade = {
        e.agente: e.profundidade for e in trace.of_kind("build")
    }
    assert profundidade["tribe/manager"] == 0
    assert profundidade["tribe/orq-infra"] == 1
    assert profundidade["tribe/infra"] == 2
    assert profundidade["tribe/infra-planner"] == 3


@pytest.mark.skipif(not TRIBE.is_dir(), reason="tribe/ not present")
def test_the_delegation_role_is_recorded(tribe_traced):
    trace, _ = tribe_traced
    papeis = {
        (e.agente, e.contraparte): e.papel for e in trace.of_kind("delegate")
    }
    assert papeis[("tribe/infra", "tribe/infra-planner")] == "planner"
    assert papeis[("tribe/infra", "tribe/infra-validator")] == "validator"
    assert papeis[("tribe/manager", "tribe/orq-infra")] == "orquestrador-infraestrutura"


def test_tracing_is_opt_in(minimal):
    """An adapter with no trace records nothing and behaves as before."""
    adapter = get_adapter("dry-run", environ={})
    assert adapter.trace is None
    assert adapter.build(resolve_agent(load_agent(minimal))).slug == "acme/simple"


# --- tracing a run ------------------------------------------------------------


def test_a_failed_run_is_recorded_as_evidence(minimal, relogio):
    """A failure is the event most worth having."""
    from oaf.errors import HarnessError

    trace = Trace(correlacao="K", clock=relogio)
    adapter = get_adapter("dry-run", environ={}, trace=trace)
    built = adapter.build(resolve_agent(load_agent(minimal)))

    with pytest.raises(HarnessError):
        adapter.run(built, "oi")

    # dry-run refuses before running, so nothing is recorded by the adapter —
    # which is itself the honest outcome: no run happened.
    assert trace.of_kind("run-start", "run-end", "error") == []


@pytest.mark.skipif(not TRIBE.is_dir(), reason="tribe/ not present")
def test_agno_run_records_start_end_and_duration(minimal, relogio, monkeypatch):
    pytest.importorskip("agno")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    trace = Trace(correlacao="K", clock=relogio)
    adapter = get_adapter("agno", trace=trace)
    built = adapter.build(resolve_agent(load_agent(minimal)))

    class Resposta:
        content = "ok"

    monkeypatch.setattr(built.agent, "run", lambda *a, **k: Resposta())
    assert adapter.run(built, "oi") == "ok"

    assert [e.kind for e in trace.of_kind("run-start", "run-end")] == [
        "run-start", "run-end"
    ]
    assert trace.of_kind("run-end")[0].duracao_ms is not None
    assert not trace.failed


@pytest.mark.skipif(not TRIBE.is_dir(), reason="tribe/ not present")
def test_agno_run_records_the_error_and_reraises(minimal, relogio, monkeypatch):
    pytest.importorskip("agno")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    trace = Trace(correlacao="K", clock=relogio)
    adapter = get_adapter("agno", trace=trace)
    built = adapter.build(resolve_agent(load_agent(minimal)))

    def explode(*a, **k):
        raise RuntimeError("provider down")

    monkeypatch.setattr(built.agent, "run", explode)
    with pytest.raises(RuntimeError):
        adapter.run(built, "oi")

    erro = trace.of_kind("error")[0]
    assert "provider down" in erro.detalhe
    assert erro.duracao_ms is not None
    assert trace.failed


# --- the trail ----------------------------------------------------------------


def test_a_trail_is_appended_not_rewritten(tmp_path, relogio):
    """A trail whose past can change is not evidence."""
    trilha = tmp_path / "sub" / "trilha.jsonl"

    for cid in ("A", "B"):
        trace = Trace(correlacao=cid, clock=relogio)
        trace.record("build", "x")
        trace.write(trilha)

    linhas = trilha.read_text(encoding="utf-8").strip().splitlines()
    assert len(linhas) == 2
    assert {json.loads(linha)["correlacao"] for linha in linhas} == {"A", "B"}


def test_a_trail_round_trips(tmp_path, relogio):
    trace = Trace(correlacao="K", clock=relogio)
    trace.record("build", "a", detalhe="openai/gpt-5.2")
    trace.record("delegate", "a", contraparte="b", papel="planner", profundidade=1)
    trilha = trace.write(tmp_path / "t.jsonl")

    lidos = read_trail(trilha)
    assert [e.to_dict() for e in lidos] == [e.to_dict() for e in trace.events]


def test_one_malformed_line_does_not_hide_the_rest(tmp_path):
    trilha = tmp_path / "t.jsonl"
    bom = TraceEvent(seq=0, ts="2026-08-27T12:00:00.000Z", correlacao="K",
                     kind="build", agente="a")
    trilha.write_text(f"{bom.to_json()}\n{{ nao e json\n\n{bom.to_json()}\n")

    assert len(read_trail(trilha)) == 2


def test_unknown_fields_in_a_trail_are_ignored(tmp_path):
    """A trail written by a newer version must still be readable."""
    trilha = tmp_path / "t.jsonl"
    trilha.write_text(json.dumps({
        "seq": 0, "ts": "2026-08-27T12:00:00.000Z", "correlacao": "K",
        "kind": "build", "agente": "a", "campo_do_futuro": 42,
    }) + "\n")

    eventos = read_trail(trilha)
    assert len(eventos) == 1 and eventos[0].agente == "a"


def test_a_shared_trail_splits_by_correlation(tmp_path, relogio):
    trilha = tmp_path / "t.jsonl"
    for cid in ("A", "B", "A"):
        trace = Trace(correlacao=cid, clock=relogio)
        trace.record("build", "x")
        trace.write(trilha)

    grupos = group_by_correlation(read_trail(trilha))
    assert set(grupos) == {"A", "B"}
    assert len(grupos["A"]) == 2
    assert [e.seq for e in grupos["A"]] == sorted(e.seq for e in grupos["A"])
