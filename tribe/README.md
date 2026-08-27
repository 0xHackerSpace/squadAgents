# Tribe · triagem e roteamento

Uma tribe é um gerente de triagem e os squads que ele aciona. O gerente
**categoriza e classifica o pedido do usuário em JSON**, e em seguida encaminha
ao squad responsável.

| Agente | Papel | Atende |
|---|---|---|
| `tribe/manager` | triagem | classifica em JSON e roteia |
| `tribe/infra` | `squad-infraestrutura` | provisionamento, rede, acesso de máquina, custo |
| `tribe/dados` | `squad-dados` | pipelines, qualidade, modelagem, relatórios |
| `tribe/suporte` | `squad-suporte` | incidentes, dúvidas, acesso de pessoa, bugs |
| `tribe/response` | `coordenador-resposta` | decide se a resposta volta ao usuário ou segue para outra categoria |

Cada squad tem, obrigatoriamente, **um planner e um validator**:

| Squad | Planner | Validator |
|---|---|---|
| `tribe/infra` | `tribe/infra-planner` | `tribe/infra-validator` |
| `tribe/dados` | `tribe/dados-planner` | `tribe/dados-validator` |
| `tribe/suporte` | `tribe/suporte-planner` | `tribe/suporte-validator` |

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

## Rodando

```bash
export OPENAI_API_KEY=...
oaf run tribe/manager "o checkout está fora do ar desde as 14h"
```

Pela API da biblioteca, que já extrai o JSON para o chamador agir sobre ele:

```bash
python examples/run_tribe.py "o checkout está fora do ar desde as 14h"
```

Sem gastar chamada:

```bash
oaf validate tribe --profile strict
oaf inspect  tribe/manager            # os três squads e seus papéis
oaf inspect  tribe/manager --prompt   # o contrato JSON, como o agente o recebe
```

## Planner e validator

Todo squad planeja e julga o plano com **agentes distintos**, e essa é a decisão
que sustenta a camada.

| Papel | Recebe | Emite | Nunca faz |
|---|---|---|---|
| Planner | a demanda normalizada | plano com passos verificáveis | executar, ou aprovar o próprio plano |
| Validator | o plano | veredito com achados | corrigir o plano, ou propor alternativa |

**Por que dois e não um.** Um agente que planeja e se aprova racionaliza as
próprias premissas: escolheu a região porque pareceu razoável, e ao revisar
continua parecendo razoável pelo mesmo motivo. A separação é o que faz a
premissa ser lida por quem não a formulou.

É a mesma razão pela qual o validador **não corrige**. Quem reescreve o passo
passa a ter autoria, e na rodada seguinte julga o próprio trabalho.

**O laço tem teto:** até duas revisões. Na terceira reprovação o problema deixou
de ser o plano — é a demanda, e o validador diz isso em vez de pedir um quarto
plano.

**Ressalva não reprova.** `aprovado_com_ressalvas` segue para execução com os
achados leves junto; parar um plano executável por nomenclatura custa uma rodada
e não compra nada.

O que muda entre as categorias é o critério, e ele mora na skill do validador:

| Categoria | O validador reprova por |
|---|---|
| `infra` | baseline de segurança, raio de alcance, reversibilidade |
| `dados` | definição não estabelecida, backfill dito reversível, impacto a jusante omitido |
| `suporte` | causa antes de contenção, confirmação sem limiar e janela, paliativo sem volta |

## O coordenador de resposta

Quando um squad termina — concluído, parcial ou bloqueado — ele chama
`tribe/response`, que decide uma coisa só: **isto volta ao usuário, ou outra
categoria precisa agir?**

```json
{
  "correlacao": "01JQ8F3K2M4N5P6Q7R8S9T0V1W",
  "decisao": "encaminhar",
  "destino": "tribe/dados",
  "handoff_n": 0,
  "motivo": "Recurso provisionado; configurar a escrita da pipeline é trabalho de dados",
  "mensagem_usuario": null,
  "contexto_handoff": { "ja_feito": "...", "pendente": "..." }
}
```

**Ele nomeia o destino; não o chama.** Se `tribe/response` declarasse os
coordenadores em `agents:` enquanto eles o declaram, o par vira referência mútua
e o harness reprova com `agent.cycle` — corretamente, porque referência mútua
afirma que os dois se delegam sem fim. O encaminhamento é dado que sobe, não
chamada que desce. Há um teste que constrói o par e confirma a rejeição.

| Regra | Consequência |
|---|---|
| `notificar` | `destino` e `contexto_handoff` nulos; `mensagem_usuario` não vazia |
| `encaminhar` | destino real, contexto não vazio, `mensagem_usuario` nula |
| `handoff_n` chegou a 2 | obrigatoriamente `notificar`, dizendo o que ficou de fora |
| — | nunca encaminhar de volta para a categoria que acabou de trabalhar |

A `mensagem_usuario` não nomeia agente, camada nem squad: o usuário não sabe que
a tribe existe. E um parcial é apresentado **como parcial** — maquiar parcial de
sucesso é a única forma de errar aqui que o usuário não consegue detectar.

## O contrato JSON

O gerente emite a classificação **primeiro**, sozinha, em um bloco ` ```json `,
e só depois a resposta do squad, separada por `---`.

```json
{
  "categoria": "suporte",
  "subcategoria": "incidente",
  "destino": "tribe/suporte",
  "prioridade": "critica",
  "confianca": 1.0,
  "acionavel": true,
  "lacunas": [],
  "resumo": "Checkout indisponível desde 14h, impedindo finalização de pedidos",
  "justificativa": "Produção parada com impacto em receita; é incidente, não trabalho planejado"
}
```

O contrato completo está em
[`manager/skills/taxonomia/resources/triagem.schema.json`](manager/skills/taxonomia/resources/triagem.schema.json),
publicado para quem consome a saída.

### Invariantes

| Regra | Consequência |
|---|---|
| `acionavel: false` | `destino` é `"nenhum"` e `lacunas` não está vazio |
| `acionavel: true` | `lacunas` é `[]` e há um destino real |
| `confianca` < `0.6` | não é acionável — baixa confiança é lacuna, não palpite |
| `categoria: "fora_de_escopo"` | `destino` é `"nenhum"` e não é acionável |

> **O que garante isso.** As invariantes vivem nas instruções e nos exemplos
> resolvidos, não em código: o harness não valida a saída de um agente, e a spec
> do OAF não tem campo para declarar schema de saída. Os testes verificam que os
> exemplos que ensinam o contrato o obedecem, e que o prompt menciona todo campo
> e todo valor de enum — mas o cumprimento em execução depende do modelo.
> `examples/run_tribe.py` mostra a extração do lado do chamador, incluindo o
> caso em que o JSON não veio.

## Como a triagem decide

A skill `taxonomia` traz as fronteiras que confundem. A regra que resolve a
maioria dos empates:

> **Está quebrado agora → `suporte`. É trabalho novo → `infraestrutura` ou `dados`.**

| Pedido | Vai para |
|---|---|
| "o banco está lento" | `suporte` |
| "quero um banco novo" | `infraestrutura` |
| "o relatório está com número errado" | `dados` |
| "o relatório não abre" | `suporte` |
| "preciso de acesso ao cluster" | `infraestrutura` |
| "preciso de acesso ao dashboard" | `suporte` |

Prioridade vem do **impacto declarado**, não da urgência com que foi escrito.
"URGENTE!!!" sem impacto descrito não é `critica`.

## Para onde isto vai

[`docs/SDD.md`](../docs/SDD.md) especifica uma evolução desta tribe em quatro
camadas: a triagem passa a rotear para **orquestradores efêmeros**
(`agent-orq-<categoria>`, uma instância por pedido), que delegam a
**coordenadores** (`agent-coord-<categoria>`) que registram em log tudo o que
recebem e tudo o que acionam, e que por sua vez chamam **especialistas**
(`agent-spec-<categoria>-<especialidade>`).

Os especialistas — camada que ainda não existe — são **stateless** e conversam
**bidirecionalmente** com os coordenadores: podem pedir esclarecimento, entregar
parcial ou declarar bloqueio, em turnos com teto. Isso é contrato de mensagens,
não referência mútua no manifesto: declarar `agents:` nos dois lados faz o
harness reprovar com `agent.cycle`.

O `tribe/response` já é a primeira peça desse desenho em código.

## Adaptando

**Novo squad na tribe** — crie o diretório com `AGENTS.md`, acrescente uma
entrada em `agents:` do gerente, e some a categoria em três lugares: o enum de
`categoria` e o de `destino` no schema, e a tabela de fronteiras da skill. Os
testes reprovam se um deles ficar para trás.

**Mudar a taxonomia** é editar `manager/skills/taxonomia/SKILL.md`. As regras
moram em Markdown, não em código.

**Ligar a tribe ao squad de Terraform** em [`squad/`](../squad): o `tribe/infra`
é hoje terminal. Para fazê-lo delegar, acrescente `squad/orchestrador` ao
`agents:` dele e monte um workspace com os dois diretórios:

```python
ws = Workspace.from_path(Path("tribe"))
for agente in Workspace.from_path(Path("squad")).agents:
    ws.add(agente)
```

Pelo CLI isso exige que os dois estejam sob a mesma raiz, porque
`oaf run tribe/infra` só enxerga os irmãos de `tribe/`.
