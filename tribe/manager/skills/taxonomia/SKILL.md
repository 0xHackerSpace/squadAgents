---
name: "taxonomia"
description: "Categorias da tribe, regras de fronteira entre elas, escala de prioridade e exemplos de classificação já resolvidos"
license: "MIT"
metadata:
  author: "0xhackerspace"
  version: "1.0.0"
allowed-tools: []
---

# Taxonomia da tribe

## Quando usar

Sempre, antes de emitir qualquer classificação.

## As três categorias

| Categoria | Destino | É sobre |
|---|---|---|
| `infraestrutura` | `tribe/orq-infra` | recursos de nuvem, rede, acesso de máquina, custo de infra |
| `dados` | `tribe/orq-dados` | pipelines, qualidade de dados, modelagem, relatórios, métricas |
| `suporte` | `tribe/orq-suporte` | algo quebrado agora, dúvida de uso, acesso de pessoa, bug |
| `fora_de_escopo` | `nenhum` | jurídico, RH, compras, ou qualquer coisa que a tribe não atende |

## Fronteiras que confundem

A maioria dos erros de triagem acontece nestes quatro pares:

| Pedido | Vai para | Porque |
|---|---|---|
| "o banco está lento" | `suporte` | há impacto agora; o squad decide se é infra ou consulta |
| "quero um banco novo" | `infraestrutura` | é provisionamento, não incidente |
| "o relatório está com número errado" | `dados` | qualidade do dado, não indisponibilidade |
| "o relatório não abre" | `suporte` | está quebrado; o conteúdo não é a questão |
| "preciso de acesso ao cluster" | `infraestrutura` | acesso de máquina ou serviço |
| "preciso de acesso ao dashboard" | `suporte` | acesso de pessoa a ferramenta |
| "a pipeline falhou de madrugada" | `suporte` | falhou agora, tem impacto |
| "a pipeline precisa de uma coluna nova" | `dados` | é mudança planejada |

Regra que resolve o empate: **está quebrado agora → `suporte`. É trabalho novo →
`infraestrutura` ou `dados`.**

## Prioridade

| Nível | Critério |
|---|---|
| `critica` | produção parada, perda de dados em curso, ou exposição de segurança ativa |
| `alta` | produção degradada, ou bloqueio de uma equipe inteira |
| `media` | trabalho planejado com prazo, ou bloqueio de uma pessoa |
| `baixa` | melhoria, dúvida, ou pedido sem prazo declarado |

Prioridade vem do **impacto declarado**, não da urgência com que foi escrito.
"URGENTE!!!" sem impacto descrito não é `critica`. Se o impacto não estiver
claro, `media` e uma lacuna perguntando quem está bloqueado.

## Confiança

| Faixa | Significa |
|---|---|
| `0.9`–`1.0` | o pedido nomeia o recurso e a ação; sem leitura alternativa |
| `0.7`–`0.8` | a categoria é clara, a subcategoria é inferida |
| `0.6` | há uma segunda leitura plausível, mas uma domina |
| abaixo de `0.6` | duas leituras igualmente plausíveis → `acionavel: false` |

## Exemplos resolvidos

Veja `resources/exemplos.md`. Ele traz cinco casos com o JSON completo, incluindo
os dois que **não** são acionáveis.

## Não é sua função

Não estime esforço, não sugira solução, não escolha ferramenta. A classificação
diz para onde vai e com que urgência — o resto é do squad que atende.
