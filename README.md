# squadAgents

An [Open Agent Format](https://openagentformat.com/) (OAF) harness: it parses,
validates, resolves and runs OAF agents, and exports them to other harnesses.

Implements **OAF 0.8.0** (Draft). See [docs/CONFORMANCE.md](docs/CONFORMANCE.md)
for exactly what is covered, what is deliberately not, and where the spec and the
agents published alongside it disagree, and [adr.md](adr.md) for the architecture
and the decisions behind it.

## Setup

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e '.[runtime,dev]'
```

The core package needs only `pydantic` and `pyyaml` — parsing, validation,
resolution, packaging and export all work without any model provider installed.
The `runtime` extra adds `agno` and the model clients needed to actually run an
agent.

## Usage

```bash
oaf validate ./my-agent                    # check against the spec
oaf validate ./my-agent --profile strict   # enforce every rule as written
oaf inspect  ./my-agent                    # print the fully resolved definition
oaf inspect  ./my-agent --prompt           # print the composed system prompt
oaf run      ./my-agent "summarize this"   # run it
oaf package  ./agents -o dist/agents.zip   # pack for distribution
oaf unpack   dist/agents.zip -d ./out      # unpack and inspect
oaf export   ./my-agent --target letta -d ./out
```

Every command takes a directory containing `AGENTS.md`, or a directory of them.
`run` is the only one that needs an API key. Full reference for every argument,
exit code and environment variable: [docs/CLI.md](docs/CLI.md).

### As a library

```python
from oaf import load_agent, resolve_agent, validate_agent
from oaf.runtime import get_adapter

agent = load_agent("./my-agent")
report = validate_agent(agent)
if not report.ok:
    for diagnostic in report.errors:
        print(diagnostic.format())

resolved = resolve_agent(agent)
built = get_adapter("agno").build(resolved)
print(built.system_prompt)
```

## The two validation profiles

The spec calls validation "informative" and leaves enforcement to the harness.
This one draws the line twice:

- **`lenient`** (default) — for consuming agents from the wild. The four
  deviations the published reference agents exhibit are warnings.
- **`strict`** — for authoring new agents. Every rule the spec states is an error.

All nine reference agents published with the spec pass `lenient`; under `strict`
they surface exactly the deviations documented in `docs/CONFORMANCE.md`.

## Layout

```
src/oaf/
├── models/      typed models for every file the spec defines
├── parse/       frontmatter splitting and document parsing
├── loader.py    reads one agent directory off disk
├── resolve.py   links references, walks sub-agents, catches cycles
├── validate.py  the rules, and the two profiles
├── runtime/     model resolution, prompt composition, harness adapters
├── packaging/   the .zip format
├── export/      Claude Code, Goose, Deep Agents, Letta
└── cli.py       the `oaf` command
```

## Tests

```bash
pytest
```

The suite includes a conformance run against the agents published alongside the
specification. It is skipped when that corpus is not checked out; point
`OAF_REFERENCE_CORPUS` at your own clone to run it elsewhere.

## The squad

`squad/` holds a working three-agent squad that takes an infrastructure request
written in plain language and produces Terraform for review — or an objective
question when the request cannot become code yet.

```bash
export OPENAI_API_KEY=...
oaf run squad/orchestrador "preciso de um bucket para artefatos de build"
```

`squad/orchestrador` delegates to `squad/validador` (a gate that judges the
*request*, not the code) and then, only on approval, to `squad/terraform`. See
[docs/USE_CASE.md](docs/USE_CASE.md) for the flow, the three outcomes, and how to
adapt it.

## The tribe

`tribe/` holds a triage manager and the three squads it routes to. The manager
classifies a request into JSON — category, destination, priority, confidence,
whether it is actionable at all — and then delegates to the squad that owns it.

```bash
export OPENAI_API_KEY=...
oaf run tribe/manager "o checkout está fora do ar desde as 14h"
```

See [tribe/README.md](tribe/README.md) for the JSON contract, the routing rules,
and what does and does not enforce them. [docs/SDD.md](docs/SDD.md) specifies a
proposed four-layer evolution of it — ephemeral per-request orchestrators, squad
coordinators that log every action received and taken, and specialist agents.

## Examples

- [`examples/agents/`](examples/agents) — a gallery of six example agents, one
  per feature of the format: the bare minimum, the simplified instruction
  format, a local skill, MCP tool subsetting, memory blocks, and one agent
  configured for all four harnesses at once. Copy the closest one to start.
- `examples/run_squad.py` — the squad through the library API, for when it is a
  step inside a larger program rather than something a person types.
- `examples/agno-quickstarts/` — the plain Agno starter agents this repository
  began with. They are not OAF agents and are kept only for reference.
