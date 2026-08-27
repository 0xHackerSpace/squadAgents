# Conformance notes

This harness implements **Open Agent Format 0.8.0** (Draft).

The specification and the agents published alongside it disagree in four places.
Both are supported: parsing accepts either form, and the `strict` validation
profile reports each deviation while `lenient` (the default) demotes it to a
warning.

| # | Rule as specified | What the reference agents do | Diagnostic |
|---|---|---|---|
| 1 | `slug` is `vendorKey/agentKey` | A bare name — `recipe-finder-agent` | `identity.slug-not-canonical` |
| 2 | `entrypoint` nests under `orchestration:` | Bare `entrypoint: structured` at the top level | `orchestration.bare-key` |
| 3 | `ActiveMCP.json` uses `selectedTools` / `excludedTools` / `contextStrategy` | `enabled_tools` / `disabled_tools` / `tool_config` | normalized silently, dialect recorded |
| 4 | `SKILL.md` requires `name` and `description` frontmatter (AgentSkills.io) | Several carry no frontmatter at all | `skill.no-frontmatter` |

Two further shapes are accepted without complaint because no single form is
canonical in practice:

- **`config.yaml`** — the spec's `auth` / `rate_limit` / top-level `server`, and
  the reference form's `authentication` / `rate_limiting` / `server:` mapping.
- **`PACKAGE.yaml`** — three dialects: the spec's (`format: oaf-package` plus
  `contents.mode`), the toolkit form used by the published multi-agent package,
  and the generated form found inside the published sample zips (`contents_mode`
  flat, agents keyed by `vendorKey`/`agentKey` rather than `slug`).

`oaf package` always *writes* the spec dialect. Reading is permissive, writing is
canonical.

## What is implemented

| Spec area | Status |
|---|---|
| `AGENTS.md` frontmatter, every documented field | full |
| Both instruction formats (structured / direct system prompt) | full |
| Identity, metadata, semver, kebab-case, SPDX checks | full |
| `skills` — local resolution | full |
| `skills` — well-known URLs | recorded as deferred; **not fetched** |
| `packs` | parsed and reported; no pack registry exists to resolve against |
| `weblets` | parsed and reported; **not implemented** |
| `mcpServers` + `ActiveMCP.json` + `config.yaml` | parsed, subsetted, described to the model; **not dialed** |
| `agents` (sub-agents) | resolved, cycle-checked, mapped to an Agno `Team` |
| `orchestration` | parsed; `entrypoint` / `fallback` / `triggers` are not yet dispatched on |
| `tools`, `config.tools.allowed` / `.denied` | parsed; `denied` is stated in the prompt |
| `memory` | parsed; carried into the Letta export |
| `model` — both the alias and object forms | full |
| `harnessConfig` | free-form, read by adapters and by the Goose export |
| `versions/` | inventoried |
| Packaging (`.zip` + `PACKAGE.yaml`) | full, both directions |
| Export to Claude Code / Goose / Deep Agents / Letta | full |

### Deliberate gaps

**Well-known skills are not fetched.** The spec has the harness fetch
`https://…/.well-known/skills/{name}/SKILL.md` at install time. That is a network
fetch of remote instructions that then enter a system prompt, so it belongs
behind an explicit, auditable install step rather than inside `load_agent`.
Deferred skills are reported by `oaf inspect` and named in the prompt.

**MCP servers are described, not connected.** Connecting means opening a live
session per server with a lifetime the caller must own; a synchronous `build()`
is the wrong place for it. The tool subset from `ActiveMCP.json` is computed and
honoured — `ActiveMcp.permits()` is the enforcement point, and it treats a
trailing `*` as a prefix pattern because the reference agents write `admin.*`.

**Weblets are not implemented.** The spec defines the reference fields and the
three launch modes but not what a weblet *is* at runtime.

## Model aliases

The spec's `"sonnet"` / `"opus"` / `"haiku"` mean "latest of that tier", which
moves. The table lives in `oaf.runtime.models.DEFAULT_ALIASES` and is overridable
per alias without touching code:

```bash
OAF_MODEL_SONNET=openai/gpt-5.2 oaf run ./my-agent "hello"
```

`--model` overrides everything, so any agent can run on any model without editing
its `AGENTS.md`.
