# Conformance fixtures

- `valid/minimal` — the spec's Quick Start: one `AGENTS.md`, nothing else.
- `valid/sub-agent` — the simplified format: a bare system-prompt body.
- `valid/full-featured` — every optional block the spec defines, exercising local
  skills, an MCP config directory, a sub-agent, packs, weblets, memory, the
  object form of `model`, and `harnessConfig`.
- `invalid/*` — one directory per rejection: bad semver, absent frontmatter, an
  unclosed frontmatter block, missing required fields, malformed YAML.
- `cycles/` — `alpha` and `beta` delegate to each other, to pin cycle detection.
