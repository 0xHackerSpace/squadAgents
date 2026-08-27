"""The execution trace: a record of what the harness did.

The SDD draws a distinction this module exists to serve. A log an agent writes
about itself is an *assertion* — it can omit an action the agent took, or claim
one it did not. A trace the harness records is *evidence*: an event is in it
because the harness performed the thing.

Scope, stated precisely because a trace that overclaims is worse than none:

    recorded    every agent built, its model, its parent and depth; every
                delegation edge the harness itself wired; the start, end,
                duration and failure of each run the harness invoked.

    not recorded
                delegations a harness backend performs internally. Once an
                Agno Team is running, the leader calls its members inside
                Agno, where this harness is not on the call path. Agno's
                `pre_hooks`/`post_hooks` are where per-member events would
                attach; wiring them needs a live model to verify, so they are
                deliberately left alone rather than shipped untested.

Every event carries a correlation id, so one request's events can be pulled out
of a shared trail.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

#: What a trace event can be.
TraceKind = Literal["build", "delegate", "run-start", "run-end", "error"]

#: Kinds that close something a previous event opened.
TERMINAL_KINDS = frozenset({"run-end", "error"})


def new_correlation() -> str:
    """Mint a correlation id.

    The SDD leaves this to the caller precisely so a run can be reproduced: pass
    your own id and the trace is deterministic apart from timestamps.
    """
    return uuid.uuid4().hex


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class TraceEvent:
    """One thing the harness did."""

    seq: int
    ts: str
    correlacao: str
    kind: TraceKind
    agente: str
    contraparte: str | None = None
    papel: str | None = None
    profundidade: int = 0
    duracao_ms: int | None = None
    detalhe: str | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=False)

    def format(self) -> str:
        """One line, for a terminal."""
        recuo = "  " * self.profundidade
        alvo = f" -> {self.contraparte}" if self.contraparte else ""
        papel = f" ({self.papel})" if self.papel else ""
        duracao = f" {self.duracao_ms}ms" if self.duracao_ms is not None else ""
        detalhe = f" · {self.detalhe}" if self.detalhe else ""
        return f"{recuo}{self.kind:9} {self.agente}{alvo}{papel}{duracao}{detalhe}"


@dataclass
class Trace:
    """An append-only sequence of events for one correlation.

    `clock` is injectable so tests get deterministic timestamps; `seq` is
    monotonic so ordering stays total even when two events land in the same
    millisecond.
    """

    correlacao: str = field(default_factory=new_correlation)
    clock: Callable[[], datetime] = _utc_now
    events: list[TraceEvent] = field(default_factory=list)

    def record(
        self,
        kind: TraceKind,
        agente: str,
        *,
        contraparte: str | None = None,
        papel: str | None = None,
        profundidade: int = 0,
        duracao_ms: int | None = None,
        detalhe: str | None = None,
    ) -> TraceEvent:
        event = TraceEvent(
            seq=len(self.events),
            ts=self.clock().isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            correlacao=self.correlacao,
            kind=kind,
            agente=agente,
            contraparte=contraparte,
            papel=papel,
            profundidade=profundidade,
            duracao_ms=duracao_ms,
            detalhe=detalhe,
        )
        self.events.append(event)
        return event

    # --- reading ---

    def of_kind(self, *kinds: TraceKind) -> list[TraceEvent]:
        return [e for e in self.events if e.kind in kinds]

    def of_agent(self, slug: str) -> list[TraceEvent]:
        return [e for e in self.events if e.agente == slug or e.contraparte == slug]

    @property
    def agents(self) -> list[str]:
        """Every agent the harness built, in build order."""
        return [e.agente for e in self.events if e.kind == "build"]

    @property
    def edges(self) -> list[tuple[str, str]]:
        """Every delegation edge the harness wired."""
        return [
            (e.agente, e.contraparte)
            for e in self.events
            if e.kind == "delegate" and e.contraparte
        ]

    @property
    def failed(self) -> bool:
        return any(e.kind == "error" for e in self.events)

    # --- writing ---

    def to_jsonl(self) -> str:
        return "".join(f"{e.to_json()}\n" for e in self.events)

    def write(self, path: Path) -> Path:
        """Append this trace to a JSON-lines trail.

        Append, never rewrite: a trail whose past can change is not evidence.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(self.to_jsonl())
        return path

    def format(self) -> str:
        return "\n".join(e.format() for e in self.events)

    def __len__(self) -> int:
        return len(self.events)

    def __iter__(self):
        return iter(self.events)


def read_trail(path: Path) -> list[TraceEvent]:
    """Read a JSON-lines trail back into events.

    A malformed line is skipped rather than fatal: a trail is appended to by
    more than one run, and one bad line must not hide the rest.
    """
    events: list[TraceEvent] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        campos = {f for f in TraceEvent.__dataclass_fields__}
        events.append(TraceEvent(**{k: v for k, v in data.items() if k in campos}))
    return events


def group_by_correlation(events: list[TraceEvent]) -> dict[str, list[TraceEvent]]:
    """Split a shared trail into one sequence per request."""
    agrupado: dict[str, list[TraceEvent]] = {}
    for event in events:
        agrupado.setdefault(event.correlacao, []).append(event)
    for sequencia in agrupado.values():
        sequencia.sort(key=lambda e: e.seq)
    return agrupado
