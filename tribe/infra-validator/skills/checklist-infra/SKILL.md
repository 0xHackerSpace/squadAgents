---
name: "checklist-infra"
description: "Baseline de segurança, raio de alcance e reversibilidade contra os quais todo plano de infraestrutura é julgado, com as severidades de cada achado"
license: "MIT"
metadata:
  author: "0xhackerspace"
  version: "1.0.0"
allowed-tools: []
---

# Checklist de infraestrutura

## Quando usar

Antes de emitir qualquer veredito.

## Baseline de segurança

Achados aqui são `critica` — reprovam o plano, mesmo que a demanda tenha pedido:

| Sinal no plano | Por quê |
|---|---|
| `0.0.0.0/0` em regra de entrada | expõe o recurso à internet inteira |
| Porta administrativa aberta (22, 3389, 5432, 3306, 6379) sem restrição de origem | é o vetor de invasão mais explorado |
| Armazenamento sem bloqueio de acesso público explícito | o padrão do provedor muda; o explícito não |
| Criptografia em repouso ausente ou desabilitada | exigência de baseline |
| Credencial, chave ou token literal em qualquer passo | vaza no state, no log e no histórico |
| Papel com `*` em ação ou recurso | privilégio ilimitado por omissão |

## Raio de alcance

Achados `alta` — também reprovam:

- Passo com `altera: "destroi"` sem menção a backup ou snapshot.
- Passo que altera recurso compartilhado sem dizer quem mais o usa.
- Mudança em produção sem passo de verificação **antes** da mudança seguinte.
- Recurso sem tag de ambiente — ninguém sabe o que pode ser removido depois.

## Qualidade do plano

Achados `media` — geram ressalva, não reprovação:

- `verificacao` que não é observável: "conferir se está tudo certo" não é
  verificação; "o endpoint responde 200 em /health" é.
- Passo que faz duas coisas — se falhar no meio, ninguém sabe onde parou.
- Premissa declarada que na verdade é decisão do usuário (região, retenção).
  Só vira `alta` se a decisão for irreversível.
- Ordem que não respeita dependência declarada.

Achados `baixa`: nomenclatura fora do padrão, tag opcional ausente, descrição
vaga que não impede a execução.

## Reversibilidade

`reversivel: true` com algum passo `altera: "destroi"` é contradição, e é achado
`critica` — não por segurança, mas porque quem for executar vai confiar no campo
errado.

## O que não é achado

- Escolha de ferramenta ou módulo: não é sua decisão.
- Custo: você não tem os preços.
- Estilo do texto: julgue o plano, não a redação.
- "Poderia ser mais simples" sem dizer o que exatamente está sobrando.

## Quando não dá para julgar

Se o plano não traz `verificacao` em passo algum, ou não diz o que cada passo
altera, o problema não é achado — é `bloqueadores`. Diga o que falta no plano
para que ele possa ser julgado, e emita `reprovado`.
