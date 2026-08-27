"""Running the tribe: classify a request, then let the manager route it.

    python examples/run_tribe.py "o checkout está fora do ar desde as 14h"

The CLI equivalent is one line:

    oaf run tribe/manager "o checkout está fora do ar desde as 14h"

The manager answers with its JSON classification first, then the reply from the
squad it routed to. This script extracts that JSON so a caller can act on the
classification — route a ticket, set a priority, page someone — instead of
reading prose.

Extraction is on the caller by design: the harness does not validate agent
output against a schema, and the OAF specification has no field to declare one.
`tribe/manager/skills/taxonomia/resources/triagem.schema.json` publishes the
contract for whoever consumes it.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from oaf import Profile, load_agent, resolve_agent, validate_agent
from oaf.resolve import Workspace
from oaf.runtime import get_adapter

TRIBE = Path(__file__).resolve().parent.parent / "tribe"

#: The manager is told to emit its JSON first, in a fenced block.
FENCED_JSON = re.compile(r"```json\s*\n(.*?)\n```", re.S)


def extract_classification(reply: str) -> dict | None:
    """Pull the classification out of the manager's reply.

    Returns None when no JSON block is present or it does not parse — which is
    a real outcome, not an exception: the model was asked for JSON, and asking
    is not the same as getting.
    """
    match = FENCED_JSON.search(reply)
    if match is None:
        return None
    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def main(pedido: str) -> int:
    workspace = Workspace.from_path(TRIBE)
    manager = load_agent(TRIBE / "manager")

    report = validate_agent(manager, profile=Profile.STRICT)
    if not report.ok:
        for diagnostic in report.errors:
            print(diagnostic.format(), file=sys.stderr)
        return 1

    resolved = resolve_agent(manager, workspace=workspace)
    missing = [s.ref.slug for s in resolved.sub_agents if not s.resolved]
    if missing:
        print(f"squads ausentes da tribe: {', '.join(missing)}", file=sys.stderr)
        return 1

    adapter = get_adapter("agno")
    built = adapter.build(resolved)
    for note in built.notes:
        print(f"note: {note}", file=sys.stderr)

    reply = adapter.run(built, pedido)
    print(reply)

    classificacao = extract_classification(reply)
    if classificacao is None:
        print("\naviso: nenhum JSON de classificação na resposta", file=sys.stderr)
        return 1

    # What a caller would actually act on.
    print(
        f"\n[triagem] {classificacao.get('categoria')}"
        f" → {classificacao.get('destino')}"
        f" · prioridade {classificacao.get('prioridade')}"
        f" · confiança {classificacao.get('confianca')}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(" ".join(sys.argv[1:])))
