# Galeria de agentes

Um agente por recurso do formato. Cada um é pequeno o bastante para ser lido de
uma vez e útil o bastante para ser copiado como ponto de partida.

Todos passam em `oaf validate --profile strict`.

| # | Agente | Ensina | Arquivos |
|---|---|---|---|
| 01 | [`revisor-pr`](01-revisor-pr) | o mínimo absoluto: **um arquivo** | 1 |
| 02 | [`tradutor`](02-tradutor) | formato simplificado, alias de modelo, `tools` | 1 |
| 03 | [`analista-csv`](03-analista-csv) | skill local com `resources/` e `scripts/` | 4 |
| 04 | [`triagem-issues`](04-triagem-issues) | MCP com subsetting de tools e credencial por env | 3 |
| 05 | [`diario-bordo`](05-diario-bordo) | `memory` com blocos, para harness com estado | 1 |
| 06 | [`portavel`](06-portavel) | `harnessConfig` dos 4 alvos e `versions/` | 2 |

Para **delegação entre agentes** — `agents:`, `orchestration:`, sub-agentes
virando um time — veja [`squad/`](../../squad) e
[`docs/USE_CASE.md`](../../docs/USE_CASE.md).

---

## 01 · revisor-pr — o mínimo

Um `AGENTS.md`, nada mais. É o menor agente OAF válido: as nove chaves de
identidade e metadados obrigatórias, e um corpo estruturado.

Repare no que **não** tem: sem `model:`. Sem ele o harness cai no padrão, e
`oaf inspect 01-revisor-pr` mostra `origin: default`. Comece por aqui e
acrescente só o que precisar.

```bash
oaf inspect examples/agents/01-revisor-pr
```

## 02 · tradutor — formato simplificado

O corpo **não começa com `#`**, então o harness o trata como system prompt
direto, e não como documento estruturado — é a regra de detecção da spec. É o
formato para agentes de propósito único.

Traz também o alias `model: "haiku"` e a lista `tools:`. Compare:

```bash
oaf inspect examples/agents/01-revisor-pr --json | jq .instructionFormat  # "structured"
oaf inspect examples/agents/02-tradutor   --json | jq .instructionFormat  # "system-prompt"
```

## 03 · analista-csv — skill local

Uma skill em `skills/perfil-dataset/`, com `SKILL.md`, um `resources/` e um
`scripts/`. Declarada `required: true`, então se o diretório sumir o
`validate` reprova em vez de degradar em silêncio.

Como o agente pede `progressive-disclosure`, o prompt inicial carrega só nome,
descrição e a lista de arquivos da skill. O corpo dela chega por
`load_skill("perfil-dataset")`. Veja a diferença:

```bash
oaf inspect examples/agents/03-analista-csv --prompt              # só o índice
oaf run     examples/agents/03-analista-csv "..." --skills eager  # corpo inteiro no prompt
```

## 04 · triagem-issues — MCP com subsetting

O par de arquivos que o formato define por servidor:

- `ActiveMCP.json` escolhe **quais tools** chegam ao agente. Aqui: três de
  leitura habilitadas, uma desligada, e as de escrita explicitamente excluídas.
- `config.yaml` traz conexão, autenticação e limites. O token vem de
  `${GITHUB_TOKEN}` — nunca literal no arquivo.

A decisão que este exemplo ilustra: o agente **não tem** as tools de escrita.
Uma instrução dizendo "não feche issues" depende do modelo obedecer; uma tool
ausente não depende.

```bash
oaf inspect examples/agents/04-triagem-issues --json | jq '.mcpServers[0].tools'
# ["list_issues", "issue_read", "search_issues"]
```

Sem `GITHUB_TOKEN` no ambiente, o `validate` avisa `mcp.unset-credential`. É
aviso, não erro: a definição está correta, falta a credencial.

> Os servidores MCP são **descritos ao modelo, não conectados** por este
> harness. O porquê está em [`CONFORMANCE.md`](../../docs/CONFORMANCE.md).

## 05 · diario-bordo — memória

Três blocos de memória declarados em `memory:`, com o bloco
`harnessConfig.letta` correspondente. É o exemplo para harness com estado.

Os blocos atravessam para o formato do Letta:

```bash
oaf export examples/agents/05-diario-bordo --target letta -d /tmp/out
jq '.core_memory[].label' /tmp/out/diario-bordo.af
```

As instruções carregam a regra que importa em agente com memória: **nunca gravar
credencial nem dado pessoal**. Memória persiste, e persistir segredo é vazá-lo
mais devagar.

## 06 · portavel — quatro harnesses, um arquivo

O mesmo `AGENTS.md` carrega configuração de `claude-code`, `goose`,
`deep-agents` e `letta` ao mesmo tempo. Cada harness lê só a sua chave e ignora
o resto — é para isso que `harnessConfig` é livre de forma.

O export para Goose promove `docker-image` e `environment` a chaves de topo do
frontmatter; nenhuma chave dos outros três aparece:

```bash
oaf export examples/agents/06-portavel --target goose -d /tmp/out
head -14 /tmp/out/exemplo/escritor-changelog/AGENTS.md
```

Traz também `versions/v1.0.0/`, com o manifesto anterior preservado. A nota
dentro dele diz o que mudou e por quê — histórico sem o motivo é só um arquivo
antigo.

---

## Usando

```bash
oaf validate examples/agents --profile strict   # os seis
oaf inspect  examples/agents/03-analista-csv    # um deles, resolvido

export OPENAI_API_KEY=...
oaf run examples/agents/01-revisor-pr "revise: $(git diff HEAD~1)"
```

Para começar um agente seu, copie o exemplo mais próximo e troque
`vendorKey`, `agentKey` e `slug` — os três precisam concordar: `slug` é
`vendorKey/agentKey`, e o `validate --profile strict` reprova se não for.
