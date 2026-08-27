# Registro de Decisões de Arquitetura — harness OAF

**Projeto:** squadAgents
**Escopo:** o harness sob `src/oaf/`, que implementa o [Open Agent Format](https://openagentformat.com/) 0.8.0 (Draft)
**Status:** aceito e implementado
**Última revisão:** 2026-08-27

Este documento registra *por que* o harness tem a forma que tem, e reúne todos os
diagramas de fluxo do projeto. Para *o que* ele cobre da spec e o que deixa de
fora deliberadamente, veja [`docs/CONFORMANCE.md`](docs/CONFORMANCE.md).

## Índice

| ADR | Decisão |
|---|---|
| [001](#adr-001--o-carregamento-lê-a-validação-julga) | O carregamento lê; a validação julga |
| [002](#adr-002--diagnóstico-é-dado-não-exceção) | Diagnóstico é dado, não exceção |
| [003](#adr-003--dois-perfis-de-validação-não-um) | Dois perfis de validação, não um |
| [004](#adr-004--leitura-permissiva-escrita-canônica) | Leitura permissiva, escrita canônica |
| [005](#adr-005--adapters-de-harness-plugáveis-com-import-tardio) | Adapters de harness plugáveis, com import tardio |
| [006](#adr-006--sub-agentes-viram-um-team-cada-um-com-seu-próprio-modelo) | Sub-agentes viram um Team, cada um com seu modelo |
| [007](#adr-007--skills-carregam-progressivamente-via-tool) | Skills carregam progressivamente, via tool |
| [008](#adr-008--a-tabela-de-aliases-de-modelo-é-dado-não-lógica) | A tabela de aliases é dado, não lógica |
| [009](#adr-009--ciclos-e-ambiguidades-são-reportados-nunca-adivinhados) | Ciclos e ambiguidades são reportados, nunca adivinhados |
| [010](#adr-010--duas-capacidades-ficaram-de-fora-e-isso-é-uma-decisão) | Duas capacidades ficaram de fora, e isso é uma decisão |
| [011](#adr-011--export-é-lossy-e-diz-o-que-perdeu) | Export é lossy, e diz o que perdeu |
| [012](#adr-012--fixtures-são-a-spec-o-corpus-real-é-a-realidade) | Fixtures são a spec; o corpus real é a realidade |
| [013](#adr-013--o-contrato-da-linha-de-comando) | O contrato da linha de comando |
| [014](#adr-014--documentação-é-travada-por-teste) | Documentação é travada por teste |
| [015](#adr-015--três-camadas-de-exemplo-com-públicos-diferentes) | Três camadas de exemplo, com públicos diferentes |
| [016](#adr-016--no-squad-o-portão-vem-antes-do-gerador) | No squad, o portão vem antes do gerador |
| [017](#adr-017--na-tribe-a-classificação-é-um-documento-json) | Na tribe, a classificação é um documento JSON |

Os diagramas estão distribuídos pelos ADRs que os justificam; a
[seção 3](#3-fluxos-completos) reúne os seis fluxos completos.

---

## 1. Contexto

O OAF define um agente como um **diretório no sistema de arquivos**: um
`AGENTS.md` obrigatório com frontmatter YAML e corpo Markdown, mais diretórios
opcionais de skills, configs de MCP, versões e exemplos. A promessa do formato é
portabilidade — a mesma definição rodando em Claude Code, Goose, Deep Agents,
Letta e outros harnesses.

Duas restrições moldaram tudo o que segue:

1. **A spec delega validação ao harness.** A seção *Validation (Informative)*
   diz explicitamente que checagem de ciclos, conflitos de versão e resolução de
   referências são responsabilidade das ferramentas, não do formato.
2. **A spec e os agentes publicados junto com ela discordam.** Os 9 agentes de
   referência do repositório `OpenHarness` violam a spec em quatro pontos. Um
   harness que só aceitasse a spec literal seria inútil contra o único corpus
   real que existe; um que só aceitasse o corpus real não serviria para autorar
   agentes corretos.

Essa tensão — *ler o mundo real, escrever o formato correto* — é a decisão de
fundo que aparece em quase todos os ADRs abaixo.

> **Nota de proveniência.** `openagentformat.com` está bloqueado pela política de
> egresso deste ambiente. A spec foi lida do repositório que a publica
> (`jeffrschneider/OpenAgentFormat`, cujo `docs/CNAME` aponta para o domínio), e
> o corpus de referência veio do `OpenHarness`, do mesmo autor. É por isso que
> `CONFORMANCE.md` fala em "agentes de referência" com tanta especificidade: eles
> são arquivos reais, não hipóteses.

---

## 2. Visão geral da arquitetura

O harness é um **pipeline unidirecional**. Cada camada só conhece a anterior, e
nenhuma volta atrás. Isso é o que permite testar validação sem tocar em runtime,
e trocar de harness sem tocar em parsing.

```mermaid
flowchart TD
    CLI["cli.py · o comando oaf"]
    FS[("diretório do agente<br/>AGENTS.md + skills/ + mcp-configs/")]
    ZIP[(".zip + PACKAGE.yaml")]

    subgraph nucleo["Núcleo · depende só de pydantic + pyyaml"]
        direction TB
        P["parse/<br/>frontmatter → dict + corpo"]
        M["models/<br/>tipagem + normalização de dialetos"]
        L["loader.py<br/>lê o diretório, não julga"]
        R["resolve.py<br/>liga referências, anda no grafo"]
        P --> M --> L --> R
    end

    V["validate.py<br/>aplica as regras · 2 perfis"]
    RT["runtime/<br/>adapters de harness"]
    EX["export/<br/>claude-code · goose · deep-agents · letta"]
    PK["packaging/<br/>.zip"]

    CLI --> FS
    FS --> P
    ZIP --> PK
    PK --> FS
    L -.->|diagnósticos| V
    R --> V
    R --> RT
    R --> EX

    style nucleo fill:none,stroke:#888,stroke-dasharray:4 3
```

As três estruturas de dados que atravessam o pipeline:

| Estrutura | Produzida por | O que é |
|---|---|---|
| `AgentDocument` | `parse/` | frontmatter tipado + corpo Markdown + linha de início do corpo |
| `LoadedAgent` | `loader.py` | o diretório inteiro em memória: manifesto, skills locais, configs MCP, versões |
| `ResolvedAgent` | `resolve.py` | tudo acima, com cada referência ligada ao que ela aponta e sub-agentes percorridos |
| `BuildResult` | `runtime/` | o agente instanciado + as decisões que o produziram (modelo, prompt, tools) |

---

## ADR-001 — O carregamento lê; a validação julga

**Contexto.** É tentador rejeitar arquivos problemáticos na hora de ler. Mas um
agente com uma skill quebrada ainda é um agente inspecionável, e um autor que
recebe um erro por vez precisa de N execuções para consertar N problemas.

**Decisão.** `load_agent()` lê o diretório e **não emite juízo**. Ele constrói o
`LoadedAgent` e acumula diagnósticos em um `DiagnosticBag`. `validate_agent()` é
quem aplica as regras. A única exceção que o loader levanta é quando o
`AGENTS.md` em si não pode ser lido ou parseado — sem ele não existe agente.

**Consequências.**
- Uma passada reporta *todos* os problemas do agente, não o primeiro.
- `oaf inspect` funciona em agentes inválidos, que é justamente quando se precisa dele.
- O custo: duas etapas onde ingenuamente haveria uma.

```mermaid
flowchart LR
    A["load_agent(path)"] --> B{"AGENTS.md<br/>parseia?"}
    B -->|não| C["ParseError<br/>(única falha dura)"]
    B -->|sim| D["lê skills/, mcp-configs/, versions/"]
    D --> E["problema em um<br/>arquivo secundário?"]
    E -->|sim| F["diagnóstico no bag<br/>segue carregando"]
    E -->|não| G["LoadedAgent"]
    F --> G
    G --> H["validate_agent()<br/>aplica as regras"]
```

---

## ADR-002 — Diagnóstico é dado, não exceção

**Contexto.** Erros precisam ser: agregáveis, serializáveis para JSON, apontáveis
a arquivo e linha, e classificáveis por severidade que *varia conforme o perfil*.
Exceções não fazem nada disso bem.

**Decisão.** Um `Diagnostic` é uma dataclass congelada com `severity`, `code`,
`message`, `path`, `line`, `field` e `hint`. `DiagnosticBag` os coleta e expõe
`.errors`, `.warnings` e `.ok`. **Warnings nunca reprovam** — só `ERROR` afeta
`.ok` e o código de saída.

**Consequências.**
- `oaf validate --json` cai direto em CI sem tradução.
- O `code` (`identity.slug-not-canonical`) é estável e suprimível; a `message` pode mudar.
- A severidade de uma regra é decidida no ponto de emissão, pelo perfil — não está fixa no tipo.

---

## ADR-003 — Dois perfis de validação, não um

**Contexto.** Esta é a decisão central. Os agentes publicados *junto com a spec*
a violam em quatro pontos:

| Spec diz | Corpus de referência faz |
|---|---|
| `slug` é `vendorKey/agentKey` | um nome solto: `recipe-finder-agent` |
| `entrypoint` fica sob `orchestration:` | `entrypoint:` no nível superior |
| `ActiveMCP.json` usa `selectedTools`/`excludedTools` | usa `enabled_tools`/`disabled_tools` |
| `SKILL.md` exige frontmatter com `name` e `description` | vários não têm frontmatter algum |

Um harness rígido reprova 9 de 9 agentes reais. Um harness permissivo deixa
autores novos escreverem os mesmos desvios para sempre.

**Decisão.** Duas posturas sobre o **mesmo conjunto de regras**:

- **`lenient`** (padrão) — para *consumir* agentes do mundo real. Os desvios
  listados no conjunto `NEGOTIABLE` viram warnings.
- **`strict`** — para *autorar* agentes novos. Toda regra da spec é erro.

`NEGOTIABLE` é um conjunto explícito e pequeno em `validate.py`. Regras fora dele
têm a mesma severidade nos dois perfis.

**Consequências.**
- Os 9 agentes de referência passam em `lenient` e, em `strict`, acusam exatamente os desvios documentados — isso é um teste (`test_reference_corpus.py`).
- Um desvio novo entra pelo `NEGOTIABLE` com uma linha e um comentário dizendo qual agente real o exibe.
- O risco: `NEGOTIABLE` crescer sem disciplina até virar "aceita tudo". Mitigação: cada entrada aponta um agente real observado.

```mermaid
flowchart TD
    R["regra violada"] --> N{"código está<br/>em NEGOTIABLE?"}
    N -->|não| E["ERROR<br/>nos dois perfis"]
    N -->|sim| P{"perfil"}
    P -->|strict| E2["ERROR<br/>reprova"]
    P -->|lenient| W["WARNING<br/>não reprova"]
```

---

## ADR-004 — Leitura permissiva, escrita canônica

**Contexto.** Três arquivos do formato existem em mais de um dialeto no mundo
real: `ActiveMCP.json` (2), `config.yaml` (2) e `PACKAGE.yaml` (**3** — o da spec,
o do pacote multi-agente publicado, e o gerado dentro dos zips de amostra).
Ramificar em cada ponto de uso multiplicaria a complexidade por todo o código.

**Decisão.** A normalização acontece **uma vez, na fronteira do modelo**, em um
`@model_validator(mode="before")` do pydantic. Cada modelo aceita qualquer
dialeto e expõe uma visão única. O dialeto de origem fica registrado no campo
`dialect`, para diagnóstico e para `oaf inspect`.

Na direção oposta, **`oaf package` sempre escreve o dialeto da spec**.

**Consequências.**
- Nenhum código acima de `models/` sabe que existem dialetos.
- Um zip publicado no dialeto *toolkit* desempacota, re-empacota no dialeto *spec* e desempacota de novo — verificado ponta a ponta.
- Curiosidade que essa camada resolve: os exemplos escrevem `admin.*` em `disabled_tools`. Como nome literal de tool isso não significa nada, então `ActiveMcp.permits()` trata `*` final como prefixo.

```mermaid
flowchart LR
    subgraph in["Leitura — permissiva"]
        D1["dialeto spec<br/>selectedTools"]
        D2["dialeto referência<br/>enabled_tools"]
    end
    NORM["model_validator(before)<br/>normaliza + registra dialect"]
    UNI["visão única<br/>enabled_tool_names / permits()"]
    OUT["Escrita — canônica<br/>oaf package → dialeto spec"]

    D1 --> NORM
    D2 --> NORM
    NORM --> UNI --> OUT
```

---

## ADR-005 — Adapters de harness plugáveis, com import tardio

**Contexto.** A spec existe para que um agente rode em vários harnesses. Amarrar
o harness a um framework de agentes contradiria o propósito. Além disso,
validar e empacotar um agente não deveria exigir um SDK de LLM instalado.

**Decisão.** `HarnessAdapter` é uma ABC com dois métodos: `build()` e `run()`. O
método concreto `plan()` centraliza as três decisões que todo adapter toma
(modelo, prompt, modo de skills). Registro em `ADAPTERS`, obtido por
`get_adapter(name)`.

O núcleo depende só de `pydantic` e `pyyaml`. **`agno` é importado dentro da
função**, não no topo do módulo, e o `ImportError` vira uma `HarnessError` com a
instrução de instalação.

Dois adapters hoje:
- **`dry-run`** — resolve, compõe prompt e escolhe modelo, sem instanciar cliente algum. É o que `oaf inspect` e os testes usam.
- **`agno`** — constrói `Agent` e `Team` de verdade.

**Consequências.**
- A suíte inteira de parsing, validação, resolução, packaging e export roda sem chave de API e sem rede.
- Adicionar um harness é uma classe e uma entrada no dicionário.
- `dry-run` levanta `HarnessError` se alguém tentar executá-lo — ele constrói, não roda.

```mermaid
classDiagram
    class HarnessAdapter {
        <<abstract>>
        +name: str
        +plan(agent) tuple
        +harness_config(agent) dict
        +build(agent)* BuildResult
        +run(built, message)* str
    }
    class DryRunAdapter {
        +name = "dry-run"
        +build() sem cliente
        +run() levanta HarnessError
    }
    class AgnoAdapter {
        +name = "agno"
        +build() Agent ou Team
        +run() executa
    }
    HarnessAdapter <|-- DryRunAdapter
    HarnessAdapter <|-- AgnoAdapter
```

---

## ADR-006 — Sub-agentes viram um Team, cada um com seu próprio modelo

**Contexto.** O campo `agents:` do OAF descreve delegação: papel (`role`) e
tarefas (`delegations`). Agno tem `Team`, cuja semântica é exatamente essa.

**Decisão.** Um agente com sub-agentes resolvidos constrói um `Team` liderado por
ele; sem sub-agentes, um `Agent` simples. **Cada membro é construído
recursivamente pelo mesmo `build()`**, então cada um recebe o modelo que o seu
próprio manifesto pede.

**Consequências.**
- Um `data-analyst` em `gpt-5.2` lidera um `code-reviewer` em `claude-sonnet-5`, na mesma execução — que é o que os manifestos dizem.
- **Um bug que isso já produziu:** a primeira versão criava o `Team` sem passar `tools`, e o líder perdia acesso às próprias skills. Hoje há um teste travando isso (`test_agno_team_leader_keeps_its_tools`).

```mermaid
flowchart TD
    A["ResolvedAgent<br/>acme/data-analyst"] --> B{"tem sub-agentes<br/>resolvidos?"}
    B -->|não| C["agno.Agent"]
    B -->|sim| D["build() recursivo<br/>em cada sub-agente"]
    D --> E["acme/code-reviewer<br/>→ Claude(claude-sonnet-5)"]
    E --> F["agno.Team<br/>líder: OpenAIChat(gpt-5.2)<br/>members: [code-reviewer]<br/>tools: [load_skill]"]
```

---

## ADR-007 — Skills carregam progressivamente, via tool

**Contexto.** Inlinar o corpo de toda skill no system prompt queima contexto com
instruções que talvez nunca sejam usadas. A spec prevê isso: o
`harnessConfig.claude-code.progressive-disclosure` existe exatamente para essa
escolha.

**Decisão.** Dois modos, com `progressive` como padrão:

- **`progressive`** — o prompt lista só nome e descrição de cada skill, mais os arquivos em `resources/`, `scripts/` e `assets/`. Uma tool `load_skill(name)` devolve o corpo completo sob demanda.
- **`eager`** — todo corpo entra no prompt.

O modo vem de `harnessConfig.<harness>.progressive-disclosure` quando presente,
e pode ser forçado por `--skills`.

**Consequências.**
- O prompt inicial fica proporcional ao *número* de skills, não ao tamanho delas.
- `load_skill` com nome inexistente devolve a lista de skills disponíveis, em vez de erro — o modelo se recupera sozinho.
- Skills `source: local` não resolvidas não geram tool alguma.

```mermaid
sequenceDiagram
    participant U as Usuário
    participant A as Agente
    participant T as load_skill
    participant FS as skills/csv-report/

    Note over A: prompt inicial contém só<br/>nome + descrição + lista de arquivos
    U->>A: "resuma esse dataset"
    A->>T: load_skill("csv-report")
    T->>FS: lê SKILL.md
    FS-->>T: corpo completo
    T-->>A: instruções da skill
    A-->>U: resposta
```

---

## ADR-008 — A tabela de aliases de modelo é dado, não lógica

**Contexto.** A spec define `"sonnet"`, `"opus"` e `"haiku"` como "o mais recente
daquele nível". "Mais recente" muda; a spec não. Uma tabela hardcoded fica
desatualizada e obriga a editar código.

**Decisão.** `DEFAULT_ALIASES` é um dicionário em `runtime/models.py`, sobrescrevível
em três níveis, do mais fraco ao mais forte:

1. o padrão da tabela;
2. `OAF_MODEL_SONNET=openai/gpt-5.2` no ambiente, por alias;
3. `--model` na linha de comando, que vence tudo.

Um alias desconhecido não é erro: é tratado como id literal de modelo (o autor
pode ter digitado um id direto), com um warning. O `ResolvedModel` carrega
`origin`, dizendo qual dos caminhos decidiu.

**Consequências.**
- Qualquer agente roda em qualquer modelo sem editar o `AGENTS.md` dele.
- `oaf inspect` mostra o modelo resolvido *e a origem* — sem adivinhação.

```mermaid
flowchart TD
    S["resolve_model()"] --> O{"--model?"}
    O -->|sim| OV["origin: override"]
    O -->|não| M{"model é objeto<br/>com name?"}
    M -->|sim| MM["origin: manifest.model"]
    M -->|não| AL{"model é alias?"}
    AL -->|sim, na tabela| T{"OAF_MODEL_X<br/>no ambiente?"}
    T -->|sim| TE["origin: alias:X<br/>valor do env"]
    T -->|não| TD["origin: alias:X<br/>valor padrão"]
    AL -->|sim, fora da tabela| LI["origin: alias:literal<br/>+ warning"]
    AL -->|não há model| DF["origin: default"]
```

---

## ADR-009 — Ciclos e ambiguidades são reportados, nunca adivinhados

**Contexto.** Delegação entre agentes é um grafo, e grafos escritos à mão têm
ciclos. Além disso, o `Workspace` registra agentes também pelo `agentKey` puro
(conveniência para pacotes cujos agentes omitem o prefixo do vendor) — e dois
vendors podem reivindicar o mesmo `agentKey`.

**Decisão.** Duas regras:

1. **Ciclo é diagnóstico, não exceção.** `_resolve_sub_agent` carrega a cadeia de
   slugs; ao reencontrar um, emite `agent.cycle` nomeando o caminho inteiro
   (`acme/alpha -> acme/beta -> acme/alpha`) e para a recursão ali. Há também um
   teto de profundidade (`max_depth=8`) com o seu próprio código.
2. **Ambiguidade não é resolvida por sorteio.** Se dois vendors reivindicam o
   mesmo `agentKey` puro, `Workspace.get()` devolve `None` para essa chave e a
   resolução emite `agent.ambiguous`. Os slugs canônicos de cada um continuam
   resolvendo normalmente.

**Consequências.**
- Um pacote com ciclo é inspecionável: você vê o ciclo, e o resto do agente.
- **Isto foi um bug real corrigido em revisão:** o fallback por `agentKey` puro ligava silenciosamente `acme/x` a `other/x`. Um sub-agente errado é pior do que um sub-agente ausente, porque não falha — só age errado.

```mermaid
flowchart TD
    S["resolver sub-agente<br/>ref = vendor/agent"] --> C{"ref já está<br/>na cadeia?"}
    C -->|sim| CY["agent.cycle<br/>nomeia o caminho, para"]
    C -->|não| D{"profundidade<br/>> max_depth?"}
    D -->|sim| TD["agent.too-deep"]
    D -->|não| L{"slug canônico<br/>no workspace?"}
    L -->|sim| OK["resolve, recursão"]
    L -->|não| AMB{"agentKey puro é<br/>ambíguo entre vendors?"}
    AMB -->|sim| AE["agent.ambiguous<br/>recusa adivinhar"]
    AMB -->|não| UN["agent.unresolved"]
```

---

## ADR-010 — Duas capacidades ficaram de fora, e isso é uma decisão

**Contexto.** A spec descreve duas coisas que um harness "faz" e que não foram
implementadas. Isso precisa estar registrado como escolha, não como pendência
esquecida.

**Decisão e razões.**

**Skills well-known não são baixadas.** A spec manda buscar
`https://…/.well-known/skills/{name}/SKILL.md` no momento do install. Isso é
buscar instruções remotas que **entram direto num system prompt** — ou seja,
conteúdo de terceiro virando comportamento do agente. Isso pertence a um passo
de instalação explícito e auditável, não ao interior de `load_agent()`. Skills
assim são marcadas `deferred`, aparecem em `oaf inspect` e são nomeadas no
prompt como não empacotadas.

**Servidores MCP são descritos, não conectados.** Conectar significa abrir uma
sessão viva por servidor, com um ciclo de vida que alguém precisa possuir. Um
`build()` síncrono é o lugar errado. O que *é* feito: o subset de tools do
`ActiveMCP.json` é computado e aplicado — `ActiveMcp.permits()` é o ponto de
aplicação — e o prompt descreve os servidores e suas tools. O `BuildResult.notes`
diz explicitamente que a conexão não foi feita.

**Weblets não são implementados.** A spec define os campos e os três modos de
launch, mas não o que um weblet *é* em runtime.

**Consequências.** Cada lacuna aparece em `BuildResult.notes` e em
`docs/CONFORMANCE.md`. Nenhuma falha em silêncio.

---

## ADR-011 — Export é lossy, e diz o que perdeu

**Contexto.** A tabela *Export Compatibility* da spec nomeia quatro alvos, cada
um com um formato mais pobre que o OAF. Claude Code não tem `config.tools.denied`;
nenhum alvo carrega packs ou weblets.

**Decisão.** Todo exporter devolve um `ExportResult` com `files` e **`notes`**. As
notas dizem, item a item, o que não atravessou. Identidade que o formato-alvo
não comporta é preservada no corpo, sob uma seção de proveniência, em vez de
sumir.

**Consequências.** Um export nunca finge ser fiel. O usuário vê a lista do que
precisa reconfigurar no harness de destino.

```mermaid
flowchart LR
    RA["ResolvedAgent"] --> CC["claude-code<br/>SKILL.md + skills/"]
    RA --> GO["goose<br/>AGENTS.md<br/>+ harnessConfig.goose promovido"]
    RA --> DA["deep-agents<br/>agent.md + skills/ separados"]
    RA --> LE["letta<br/>.af JSON + memory blocks"]
    CC & GO & DA & LE --> N["notes[]<br/>o que não atravessou"]
```

---

## ADR-012 — Fixtures são a spec; o corpus real é a realidade

**Contexto.** Testar um parser de formato contra exemplos que você mesmo escreveu
prova pouco.

**Decisão.** Duas camadas de teste:

1. **Fixtures próprias** (`tests/fixtures/`) — uma por regra. `valid/minimal` é o
   Quick Start da spec; `valid/full-featured` exercita *todo* bloco opcional;
   `invalid/*` tem um diretório por motivo de rejeição; `cycles/` trava a
   detecção de ciclo.
2. **Corpus de referência** (`test_reference_corpus.py`) — os 9 agentes
   publicados junto com a spec. Ele fixa dois fatos: todos passam em `lenient`, e
   sob `strict` os erros são **exatamente** os desvios documentados, nada além.
   É pulado quando o corpus não está clonado; `OAF_REFERENCE_CORPUS` aponta para
   outro clone.

**Consequências.**
- Se a spec evoluir e o corpus for corrigido, o teste de corpus quebra — e deve mesmo.
- A suíte roda sem rede e sem chave de API — parsing, validação, resolução,
  packaging, export e construção de agente, tudo offline.
- A terceira camada, a galeria de exemplos, veio depois e está no ADR-015.

---

## ADR-013 — O contrato da linha de comando

**Contexto.** O harness é rodado por gente e por CI. Um CLI que mistura resultado
com aviso na mesma saída, ou que usa o mesmo código de erro para "seu agente
reprovou" e "você digitou o comando errado", é inútil dentro de um script.

**Decisão.** Três compromissos, iguais em todos os comandos:

1. **Três códigos de saída, com significados distintos.** `0` sucesso; `1` falha
   de conteúdo — validação reprovou, agente não encontrado, arquivo ilegível,
   execução falhou; `2` uso incorreto — comando ausente, desconhecido, argumento
   obrigatório faltando. **Aviso nunca afeta o código de saída.**
2. **stdout carrega o resultado; stderr carrega notas, avisos e erros.** É o que
   torna `oaf inspect X --json > def.json` seguro em pipe, mesmo quando o agente
   emite avisos.
3. **`oaf run` valida antes de construir qualquer coisa**, no perfil `lenient`, e
   **recusa executar** se houver erro. Não há flag para desligar.

**Consequências.**
- `oaf validate squad --profile strict --quiet || exit 1` é um portão de CI completo.
- Rodar um agente com definição quebrada produziria comportamento inexplicável, e
  gastaria tokens fazendo isso. Para inspecionar um agente quebrado sem executá-lo
  existe `oaf inspect`, que funciona em agente inválido por construção (ADR-001).
- Onde há `--json`, ele **substitui** a saída humana inteira em vez de acrescentar.
  `--prompt` vence `--json`: pedir os dois imprime o prompt.

```mermaid
flowchart TD
    C["oaf COMANDO ..."] --> P{"argparse"}
    P -->|"comando ausente<br/>ou desconhecido<br/>ou falta obrigatório"| E2["exit 2<br/>uso incorreto"]
    P -->|"ok"| H["handler do comando"]
    H --> R{"resultado"}
    R -->|"tudo certo"| E0["exit 0"]
    R -->|"validação reprovou · agente ausente<br/>arquivo ilegível · execução falhou"| E1["exit 1<br/>falha de conteúdo"]
    H -.->|"notas, avisos, erros"| SE[["stderr<br/>nunca afeta o código"]]
    R -.->|"resultado, JSON, prompt"| SO[["stdout"]]
```

---

## ADR-014 — Documentação é travada por teste

**Contexto.** `docs/CLI.md` é escrito à mão. Nada impede que uma flag nova seja
adicionada sem entrar na referência, ou que um default mude e a doc siga
afirmando o antigo. Documentação que mente é pior que documentação ausente,
porque é seguida.

**Decisão.** Onde uma doc afirma algo verificável, um teste verifica.

- `tests/test_cli_docs.py` **introspecciona o argparse** e exige: todo subcomando
  tem seção, todo argumento tem texto de ajuda, toda flag, posicional e valor de
  `choices` aparece na referência, os defaults documentados batem com o parser, e
  os códigos de saída estão listados.
- `tests/test_example_agents.py` fixa cada afirmação do índice da galeria — que o
  exemplo mínimo é um arquivo só, que os dois formatos de instrução estão de fato
  demonstrados, que o corpo da skill fica fora do prompt `progressive`.
- `tests/test_squad.py` fixa o cabeamento descrito em `docs/USE_CASE.md`.

**Prática que acompanha a decisão:** um guarda de divergência é verificado
*quebrando-o de propósito*. O de CLI foi checado adicionando uma flag sem ajuda e
outra não documentada, e confirmando que a suíte fica vermelha. Guarda que nunca
falha não guarda nada.

**Consequências.**
- Escrever a referência de CLI expôs um defeito real: **onze argumentos não tinham
  texto de ajuda nenhum**. O teste que impede a regressão nasceu junto com a
  correção.
- Uma afirmação verificada pelo motivo errado é tão ruim quanto uma não
  verificada. A primeira sonda do teste de progressive disclosure buscava uma
  frase que também abria a *descrição* da skill, e casava sem que o corpo
  estivesse no prompt. A sonda hoje usa texto que só existe no corpo.
- O custo: a doc não pode ser reorganizada livremente sem olhar os testes.

---

## ADR-015 — Três camadas de exemplo, com públicos diferentes

**Contexto.** ADR-012 estabeleceu as duas camadas de *teste*. Exemplo é outra
coisa: fixture de teste é escrito para cobrir regra, não para ser copiado.
`full-featured` usa vendor falso e um `template.csv` sem conteúdo — copiá-lo
como ponto de partida seria péssimo conselho, e ele está enterrado em `tests/`.

**Decisão.** Três camadas, cada uma com um público:

| Camada | Onde | Para quem | Critério |
|---|---|---|---|
| Fixtures | `tests/fixtures/` | a suíte | uma por regra; inclui os inválidos |
| Galeria | `examples/agents/` | quem vai escrever um agente | um recurso do formato por exemplo, real e copiável |
| Caso de uso | `squad/` | quem vai montar um time | um fluxo completo, ponta a ponta |

A galeria existe porque nada fora dos fixtures exercitava `mcpServers`, `memory`,
`versions/` ou um `harnessConfig` completo — e fixture não é material didático.

**Consequências.**
- Os seis exemplos da galeria passam em `--profile strict`, não só em `lenient`:
  são copiados como ponto de partida, então precisam ser exemplares.
- Redundância aceita: `minimal` existe como fixture e `01-revisor-pr` como
  exemplo. Servem a propósitos diferentes e mudam por motivos diferentes.

---

## ADR-016 — No squad, o portão vem antes do gerador

Decisões do fluxo em `squad/`. Ele é **consumidor** do harness, não parte dele —
a arquitetura dos ADRs anteriores não pressupõe nada sobre este fluxo — mas as
escolhas aqui são de arquitetura e pertencem a este registro.

**Contexto.** Um pedido de infraestrutura em linguagem natural quase nunca chega
completo. Falta região, ambiente, exposição de rede. Um squad que gera primeiro e
valida depois produz HCL sobre premissa inventada.

**Decisão.**

1. **O validador julga a demanda, não o código, e roda primeiro.** O orquestrador
   sempre delega ao portão antes de acionar o gerador, e passa o pedido
   *inalterado*. Só o veredito `APROVADA` libera a geração; `INCOMPLETA` e
   `RECUSADA` param o fluxo sem mostrar HCL parcial.
2. **Ambos os membros são `required: true`.** Um membro ausente falha alto, em vez
   de degradar em silêncio para um fluxo de um agente só que pula a validação.
3. **A política mora em Markdown, não em código.** As regras que produzem recusa
   estão no `SKILL.md` do validador. Mudar política é editar um arquivo.
4. **Nenhum agente pode `bash`.** Nada no squad aplica infraestrutura: sem
   `plan`, sem `apply`, sem credencial de nuvem. O que sai é código para revisão
   humana.

**Consequências.**
- Perguntar antes custa uma rodada. Gerar em cima de pedido ambíguo custa um
  recurso errado provisionado, ou uma revisão humana gasta em algo que nunca
  deveria ter sido escrito.
- O gerador carrega a mesma barreira do lado dele: se a demanda parecer exigir
  `0.0.0.0/0` em ingress, ele para e devolve ao validador. Duas barreiras, de
  propósito.
- Os três usam o mesmo provedor hoje para que **uma** chave rode tudo. O harness
  não exige isso (ADR-006): trocar o bloco `model:` de cada `AGENTS.md` já dá
  modelos diferentes por agente.

---

## ADR-017 — Na tribe, a classificação é um documento JSON

Decisões do fluxo em `tribe/`, o segundo consumidor do harness. Uma tribe é um
gerente de triagem e os squads que ele aciona.

**Contexto.** Um pedido que chega em linguagem natural precisa ser roteado antes
de ser atendido, e o roteamento precisa ser legível por máquina: um chamador quer
abrir chamado, definir prioridade e acionar plantão a partir dele, não ler prosa.

**Decisão.**

1. **O gerente emite um JSON de classificação e depois delega.** O JSON vem
   primeiro, sozinho, em bloco cercado; a resposta do squad vem abaixo, separada
   por `---`. Assim há roteamento automático *e* um artefato extraível.
2. **A taxonomia mora na skill, não nas instruções.** Categorias, fronteiras,
   escala de prioridade e cinco exemplos resolvidos ficam em
   `skills/taxonomia/`, carregada sob demanda (ADR-007).
3. **Confiança baixa não é palpite.** Abaixo de `0.6` a classificação é
   `acionavel: false` e devolve lacunas. Um palpite manda o pedido ao squad
   errado, e custa uma rodada em dois times.
4. **Todo squad planeja e julga com agentes distintos.** Um planner emite o
   plano; um validator o julga e **não o corrige**. Um agente que se aprova
   racionaliza as próprias premissas — escolheu a região porque pareceu
   razoável, e ao revisar continua parecendo, pelo mesmo motivo. Um validador
   que reescreve o passo passa a ter autoria e, na rodada seguinte, julga o
   próprio trabalho. O laço tem teto de duas revisões: na terceira reprovação o
   problema deixou de ser o plano.
5. **O encaminhamento é dado, não chamada.** Quando um squad termina, ele chama
   `tribe/response`, que decide entre notificar o usuário e encaminhar a outra
   categoria — e no segundo caso **nomeia** o destino em vez de chamá-lo. Se o
   responder declarasse os coordenadores em `agents:` enquanto eles o declaram,
   o par vira referência mútua e o resolvedor reprova com `agent.cycle`
   (ADR-009). O teto de dois encaminhamentos impede que um pedido circule entre
   times sem retorno a quem pediu.

**Alternativas descartadas.** Um classificador puro — sem sub-agentes, saída
100% JSON — seria mais fácil de validar na borda, mas exigiria um segundo passo
para atender o pedido. A escolha foi por roteamento em uma execução só,
aceitando que o JSON passa a ser a primeira parte da resposta e não a resposta
inteira.

**Consequências.**
- O JSON precisa ser **extraído** do texto. `examples/run_tribe.py` faz isso e
  trata o caso em que ele não veio — que é resultado possível, não exceção.
- **O contrato não é aplicado em runtime.** O harness não valida saída de agente,
  e a spec do OAF não tem campo para declarar schema de saída. O que os testes
  fixam é o que dá para fixar sem executar modelo: que o schema publicado é
  autoconsistente, que todo destino nele é um agente real, que o prompt menciona
  todo campo e todo valor de enum, e que os exemplos que ensinam o contrato o
  obedecem. O cumprimento em execução depende do modelo.
- `resources/triagem.schema.json` existe para quem **consome** a saída, não para
  o harness. É documentação executável do contrato, publicada junto do agente.

---

## 3. Fluxos completos

### 3.1 `oaf run` — do diretório à resposta

```mermaid
sequenceDiagram
    autonumber
    participant U as usuário
    participant CLI as cli.py
    participant LD as loader
    participant WS as Workspace
    participant RS as resolve
    participant VL as validate
    participant AD as AgnoAdapter
    participant AG as agno

    U->>CLI: oaf run ./meu-agente "pergunta"
    CLI->>LD: load_agent(path)
    LD-->>CLI: LoadedAgent (+ diagnósticos)
    CLI->>WS: from_path(pai) — irmãos viram sub-agentes
    CLI->>RS: resolve_agent(agent, workspace)
    RS-->>CLI: ResolvedAgent
    CLI->>VL: validate_agent(profile=lenient)
    alt tem erros
        VL-->>U: imprime erros, sai 1
    else limpo
        CLI->>AD: build(resolved)
        AD->>AD: plan() → modelo, prompt, modo de skills
        AD->>AG: Agent(...) ou Team(...)
        AD-->>CLI: BuildResult (+ notes)
        CLI-->>U: notes em stderr
        CLI->>AD: run(built, mensagem)
        AD->>AG: executa
        AG-->>U: resposta em stdout
    end
```

Detalhe deliberado: `oaf run` valida em `lenient` e **recusa executar** se houver
erro. Rodar um agente cuja definição está quebrada produz comportamento
inexplicável.

### 3.2 Composição do system prompt

O corpo Markdown é a instrução; o resto é contexto que o corpo pressupõe mas não
repete. `build_system_prompt()` monta nesta ordem:

```mermaid
flowchart TD
    B["corpo do AGENTS.md<br/>(estruturado ou prompt direto)"] --> S
    S["## Available Skills<br/>nome + descrição + arquivos<br/>(+ corpos, se eager)"] --> M
    M["## Connected MCP Servers<br/>endpoint + tools habilitadas<br/>+ tools explicitamente bloqueadas"] --> D
    D["## Delegation<br/>sub-agentes, papéis, tarefas"] --> T
    T["## Tool Restrictions<br/>config.tools.denied"] --> P["system prompt final"]
```

A detecção do formato de instrução segue a regra da spec: corpo começando com
`#` é *estruturado*; qualquer outra coisa é *prompt direto*. Linhas em branco
iniciais são ignoradas — a regra é sobre o primeiro conteúdo, não o primeiro byte.

### 3.3 Ciclo de vida de um pacote

```mermaid
flowchart LR
    A["diretório<br/>de agentes"] -->|"oaf package"| Z["arquivo .zip<br/>PACKAGE.yaml no dialeto spec"]
    Z -->|"oaf unpack"| B["extração<br/>+ guarda contra path traversal"]
    B --> C["read_package()<br/>cross-check manifesto × disco"]
    C --> D{"divergências"}
    D --> E["package.missing-agent (erro)<br/>package.version-mismatch (aviso)<br/>package.unlisted-agent (aviso)"]
    C --> F["agentes carregáveis"]
```

`extract_package` recusa membros com caminho absoluto ou `..` antes de extrair
qualquer coisa — um zip é conteúdo de terceiro.

### 3.4 O fluxo do squad, e os três caminhos

O fluxo que o ADR-016 descreve, com os três desfechos possíveis. Este diagrama
também abre [`docs/USE_CASE.md`](docs/USE_CASE.md).

```mermaid
flowchart TD
    U(["pedido do usuário<br/>em linguagem natural"]) --> O["squad/orchestrador"]
    O -->|"1. delega o pedido inalterado"| V["squad/validador<br/>carrega demanda-checklist"]
    V --> D{"veredito"}
    D -->|"RECUSADA"| R["para · motivo em uma frase<br/>+ alternativa que passaria na política"]
    D -->|"INCOMPLETA"| Q["para · até 3 perguntas objetivas<br/>nenhum HCL é mostrado"]
    D -->|"APROVADA"| N["demanda normalizada"]
    N -->|"2. delega a demanda normalizada,<br/>nunca o texto original"| T["squad/terraform<br/>carrega hcl-conventions"]
    T --> S["main.tf · variables.tf<br/>outputs.tf · versions.tf<br/>+ decisões + antes de aplicar"]
    R --> U
    Q --> U
    S --> U
```

### 3.5 Como o squad vira um Team

A recursão do ADR-006 aplicada a um caso concreto: o `agents:` do orquestrador
vira um `Team`, e cada membro é construído pelo mesmo `build()`.

```mermaid
sequenceDiagram
    autonumber
    participant CLI as oaf run
    participant WS as Workspace(squad/)
    participant B as AgnoAdapter.build
    participant TM as agno.Team

    CLI->>WS: descobre os 3 agentes irmãos
    CLI->>B: build(orchestrador resolvido)
    B->>B: build(validador) → Agent + tool load_skill
    B->>B: build(terraform) → Agent + tool load_skill
    B->>TM: Team(líder=orchestrador, members=[validador, terraform])
    Note over TM: cada worker carrega sua skill<br/>sob demanda, não no prompt inicial
    CLI->>TM: run(demanda)
```

O `Workspace` é o que faz a delegação funcionar: `oaf run squad/orchestrador`
carrega o **diretório pai** como workspace, então os irmãos ficam visíveis.

### 3.6 Triagem e roteamento na tribe

O fluxo do ADR-017, já com o coordenador de resposta. Este diagrama também
abre [`tribe/README.md`](tribe/README.md).

```mermaid
flowchart TD
    U(["pedido do usuário"]) --> M["tribe/manager<br/>carrega a skill taxonomia"]
    M --> J[/"JSON de classificação<br/>categoria · destino · prioridade<br/>confiança · acionável · lacunas"/]
    J --> A{"acionavel?"}
    A -->|"false"| P["para · devolve as lacunas<br/>nenhum squad é acionado"]
    A -->|"true"| D{"destino"}
    D -->|"tribe/infra"| I["Squad de Infraestrutura"]
    D -->|"tribe/dados"| DA["Squad de Dados"]
    D -->|"tribe/suporte"| S["Squad de Suporte"]

    I & DA & S --> PL["planner da categoria<br/>emite o plano"]
    PL --> VA["validator da categoria<br/>julga, não corrige"]
    VA -->|"reprovado · até 2 revisões"| PL
    VA -->|"aprovado ou com ressalvas"| RC["tribe/response<br/>carrega politica-resposta"]
    RC -->|"decisao: encaminhar<br/>nomeia a categoria, não a chama"| D
    RC -->|"decisao: notificar"| R["mensagem ao usuário"]
    P --> U
    R --> U
```

---

## 4. Decisões menores, registradas

| Decisão | Razão |
|---|---|
| `argparse`, não Typer/Click | mantém o núcleo em duas dependências |
| `extra="allow"` nos modelos | chaves desconhecidas são preservadas e reportadas como aviso, não descartadas em silêncio |
| Regex oficial do semver.org | `version: 1.0` é rejeitado; YAML o entregaria como float |
| Números coeridos para texto antes de validar | `version: 1.0` chega como `float` e viraria `"1.0"` silenciosamente |
| SPDX como conjunto de reconhecimento, não portão | a lista completa tem ~600 entradas; desconhecido vira aviso |
| `Workspace` indexa por slug canônico, slug do arquivo e `agentKey` | agentes reais discordam sobre qual usar (ver ADR-009 para o limite disso) |
| `--prompt` vence `--json` no `inspect` | pedir os dois só faz sentido querendo o prompt |
| `--mode referenced` hoje só grava o campo | o harness não busca skills well-known (ADR-010); com skills locais os dois modos produzem o mesmo conteúdo |
| Metavars legíveis no CLI (`PATH`, `FILE`, `DIR`) | o default do argparse grita o `dest`, e `DESTINATION` não diz que é diretório |
| Sub-agentes exportam um comando cada | nenhum formato de destino carrega delegação (ADR-011) |

---

## 5. O que este documento não decide

**Como um servidor MCP é conectado.** O ADR-010 registra por que não é feito
aqui, não como fazer. Quem for implementar precisa decidir de quem é o ciclo de
vida da sessão, e isso muda conforme o harness hospedeiro.

**O que é um weblet em runtime.** A spec define os campos e os três modos de
launch, e para aí. Não dá para decidir a implementação sem que o formato decida o
conceito.

**Qual passo instala uma skill well-known.** O ADR-010 diz que buscar instrução
remota pertence a um passo explícito e auditável. Qual é esse passo — comando
próprio, verificação de assinatura, cache local — está em aberto.

**A arquitetura de quatro camadas com orquestradores efêmeros.** Está
especificada em [`docs/SDD.md`](docs/SDD.md), como proposta, não como decisão
tomada: ela introduz uma camada que não existe, exige duas coisas que o harness
ainda não faz — um traço de execução e uma delegação multi-turno — e depende de
uma escolha de taxonomia ainda em aberto. Quando for aceita, vira ADR.

Uma restrição do harness que esse desenho já encontrou vale registrar aqui,
porque é do harness e não da proposta: **a conversa bidirecional entre
coordenador e especialista não pode ser declarada como `agents:` nos dois
lados.** O resolvedor rejeita o par com `agent.cycle` (ADR-009), e está certo —
referência mútua diz "estes dois se delegam mutuamente", que é um grafo sem fim.
Multi-turno é outra afirmação: uma delegação com mais de uma ida e volta. É
contrato de mensagens, não topologia.

**Se o harness deve implementar a OpenHarness API.** O `OpenHarness`, do mesmo
autor da spec, define uma API REST de harness em 4056 linhas. É a camada natural
acima desta, e nada aqui a impede — os adapters do ADR-005 já são a fronteira
certa. Mas é escopo próprio, e merece o seu próprio ADR quando for encarado.

---

## 6. Onde está cada coisa

| Documento | Responde |
|---|---|
| `adr.md` (este) | por que a arquitetura é assim; todos os fluxos |
| [`docs/CONFORMANCE.md`](docs/CONFORMANCE.md) | o que da spec está coberto, e onde spec e realidade divergem |
| [`docs/CLI.md`](docs/CLI.md) | todo argumento, código de saída e variável de ambiente |
| [`docs/USE_CASE.md`](docs/USE_CASE.md) | como rodar o squad, com os três desfechos |
| [`tribe/README.md`](tribe/README.md) | a triagem, o contrato JSON e as fronteiras entre squads |
| [`docs/SDD.md`](docs/SDD.md) | o desenho proposto de quatro camadas: efêmeros, coordenadores, log |
| [`examples/agents/README.md`](examples/agents/README.md) | um exemplo por recurso do formato |
