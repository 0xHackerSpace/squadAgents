---
name: "checklist-suporte"
description: "Ordem obrigatória de um plano de incidente, critérios de sinal observável e reversibilidade de paliativo, com a severidade de cada achado"
license: "MIT"
metadata:
  author: "0xhackerspace"
  version: "1.0.0"
allowed-tools: []
---

# Checklist de suporte

## Quando usar

Antes de emitir qualquer veredito.

## A ordem

Achados `critica` — reprovam:

| Sinal no plano | Por quê |
|---|---|
| Passo de investigação de causa antes do primeiro passo de contenção | o serviço fica parado enquanto alguém entende; entender é depois |
| Nenhum passo de contenção, só causa | é um plano de post-mortem, não de incidente |
| Contenção que depende do resultado da investigação | se depende, não é contenção — é a correção definitiva com outro nome |

## Confirmação

Achados `alta`:

- Confirmação sem sinal específico: "verificar se voltou", "conferir com o
  usuário".
- Sinal sem limiar: "a taxa de erro cai" — cai para quanto?
- Limiar sem janela: "erro abaixo de 1%" — por quanto tempo?

Uma confirmação boa tem os três: métrica, limiar e janela.

## Reversibilidade do paliativo

Achados `alta`:

- Passo de contenção sem declarar como desfazer. Paliativo sem volta vira
  permanente, e o débito fica invisível.
- `reversivel: true` com passo que drena fila, limpa cache, promove réplica ou
  descarta mensagem — todos perdem dado em trânsito.

## Qualidade

Achados `media`:

- Passo de causa não marcado como investigação — quem executa não sabe que pode
  parar ali.
- Contenção e correção definitiva no mesmo passo.
- Plano de dúvida ou acesso sem dizer quem aprova.

Achados `baixa`: falta de referência a runbook existente, ordem entre passos de
causa que não afeta o resultado.

## O que não é achado

- A contenção escolhida ser a melhor possível — julgue se é contenção, não se é
  ótima.
- Tempo estimado de recuperação: você não tem os dados.
- Prioridade do incidente: veio da triagem, não é sua.

## Quando não dá para julgar

Plano que não distingue contenção de causa vai para `bloqueadores` com
`reprovado`. Sem essa distinção, a ordem não é verificável.
