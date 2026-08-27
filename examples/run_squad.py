"""Running the infrastructure squad through the library API.

The CLI equivalent is one line:

    oaf run squad/orchestrador "preciso de um bucket para artefatos de build"

This script does the same thing explicitly, which is what you want when the
squad is a step inside a larger program rather than something a person types.

    python examples/run_squad.py "preciso de um bucket para artefatos de build"
"""

from __future__ import annotations

import sys
from pathlib import Path

from oaf import Profile, load_agent, resolve_agent, validate_agent
from oaf.resolve import Workspace
from oaf.runtime import get_adapter

SQUAD = Path(__file__).resolve().parent.parent / "squad"


def main(demanda: str) -> int:
    # The whole squad directory is the workspace, so the orchestrador can see
    # its siblings. Resolving the agent alone would leave both members missing.
    workspace = Workspace.from_path(SQUAD)
    orchestrador = load_agent(SQUAD / "orchestrador")

    report = validate_agent(orchestrador, profile=Profile.STRICT)
    if not report.ok:
        for diagnostic in report.errors:
            print(diagnostic.format(), file=sys.stderr)
        return 1

    resolved = resolve_agent(orchestrador, workspace=workspace)
    for sub in resolved.sub_agents:
        if not sub.resolved:
            print(f"membro ausente: {sub.ref.slug}", file=sys.stderr)
            return 1

    built = get_adapter("agno").build(resolved)
    for note in built.notes:
        print(f"note: {note}", file=sys.stderr)

    print(get_adapter("agno").run(built, demanda))
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(" ".join(sys.argv[1:])))
