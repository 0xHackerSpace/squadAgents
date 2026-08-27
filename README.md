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

## Examples

`examples/agno-quickstarts/` holds the plain Agno starter agents this repository
began with. They are not OAF agents and are kept only for reference.
