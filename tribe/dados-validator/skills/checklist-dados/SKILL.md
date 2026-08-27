---
name: "checklist-dados"
description: "Critérios de definição, impacto a jusante e reversibilidade contra os quais um plano de dados é julgado, com a severidade de cada achado"
license: "MIT"
metadata:
  author: "0xhackerspace"
  version: "1.0.0"
allowed-tools: []
---

# Checklist de dados

## Quando usar

Antes de emitir qualquer veredito.

## Definição antes de investigação

Achados `alta` — reprovam:

| Sinal no plano | Por quê |
|---|---|
| Investiga divergência sem estabelecer as definições dos dois lados | a maioria das divergências é definição, não bug; sem isso a investigação persegue código à toa |
| Compara números sem fixar período e fuso | um relatório em UTC e outro em America/Sao_Paulo divergem sempre, e por motivo nenhum |
| Trata a fonte A como verdade sem dizer por quê | escolher o certo antes de comparar é a conclusão precedendo a análise |

## Irreversibilidade

Achados `critica`:

- Backfill que sobrescreve histórico marcado como `altera existente`, e não
  `destroi`. Quem executa vai achar que dá para voltar.
- `reversivel: true` com passo que remove coluna, tabela ou partição.
- Passo que apaga dado sem menção a snapshot, e sem estar em `aprovacao_humana`.

## Impacto a jusante

Achados `alta`:

- Mudança de schema ou de semântica de coluna sem passo que liste os
  consumidores atuais.
- Renomear métrica sem passo de transição — o nome antigo some para quem usa.
- Mudança de granularidade sem dizer o que acontece com os agregados já
  publicados.

## Qualidade da verificação

Achados `media`:

- Verificação sem número: "os valores batem", "o resultado parece correto".
- Verificação sem tolerância declarada, quando envolve ponto flutuante ou moeda.
- Passo que faz extração e transformação juntas — se falhar, ninguém sabe onde.

Achados `baixa`: nomenclatura de tabela fora do padrão, ausência de comentário
de coluna, ordem que funciona mas confunde.

## O que não é achado

- Escolha de ferramenta de pipeline ou de banco.
- O número em si estar certo ou errado — você julga o plano, não o dado.
- Performance da query, a menos que o plano declare uma janela e a viole.

## Quando não dá para julgar

Plano sem `altera` nos passos, ou sem qualquer verificação numérica, vai para
`bloqueadores` com `reprovado`, e `achados` fica vazio.
