---
name: "politica-resposta"
description: "Critérios para decidir entre notificar o usuário e encaminhar a outra categoria, o limite de encaminhamentos, e como escrever a mensagem final"
license: "MIT"
metadata:
  author: "0xhackerspace"
  version: "1.0.0"
allowed-tools: []
---

# Política de resposta

## Quando usar

Sempre, antes de decidir entre `notificar` e `encaminhar`.

## O critério

A pergunta é uma só: **o pedido original do usuário está atendido?**

| Situação | Decisão |
|---|---|
| O squad concluiu e nada ficou pendente | `notificar` |
| O squad concluiu, e o resultado abriu trabalho em outra categoria | `encaminhar` |
| O squad entregou parcial, e a parte que falta é de outra categoria | `encaminhar` |
| O squad entregou parcial, e a parte que falta depende do usuário | `notificar` — com as pendências |
| O squad bloqueou por dependência de outra categoria | `encaminhar` |
| O squad bloqueou por decisão humana ou permissão | `notificar` — dizendo quem decide |
| O squad recusou por escopo e sugeriu quem atende | `encaminhar` para a sugestão |
| `handoff_n` já é 2 | `notificar`, obrigatoriamente |

Regra que resolve a dúvida: **encaminhe quando o trabalho continua sem o
usuário; notifique quando ele precisa saber ou decidir algo.**

## O limite de dois encaminhamentos

Um pedido pode legitimamente atravessar duas categorias — provisionar e depois
liberar acesso, por exemplo. Três é quase sempre sinal de que a triagem errou a
categoria de origem, e o custo de continuar é um pedido circulando entre times
sem ninguém dar retorno.

No limite, `notificar` com honestidade: o que foi feito, o que não foi, e qual
categoria seria a próxima. O usuário decide se abre um pedido novo — o que
também dá à triagem a chance de classificar melhor da segunda vez.

## Escrevendo para o usuário

O usuário não conhece a tribe. Ele não sabe o que é um coordenador, um
especialista, ou qual squad atendeu.

| Não escreva | Escreva |
|---|---|
| "O agent-spec-infra-terraform concluiu" | "O bucket foi criado" |
| "Resultado parcial do squad de dados" | "Encontrei a origem da divergência; corrigir depende de uma decisão sua" |
| "Bloqueio por dependência" | "Isto precisa da aprovação de rede antes de seguir" |
| "Encaminhado para agent-coord-suporte" | "Passei para o time de suporte, que responde em seguida" |

Três frases costumam bastar: **o que foi feito**, **o que precisa de você**, **o
que vem a seguir**. Se não houver nada que precise do usuário, omita a linha —
não invente uma pendência para ter três frases.

## O que nunca fazer

- Apresentar um resultado parcial como se fosse completo.
- Encaminhar sem `contexto_handoff` — a próxima categoria recomeçaria do zero.
- Encaminhar de volta para a categoria que acabou de trabalhar. Se ela devolveu,
  é porque terminou o que podia; devolver é loop.
- Escrever o nome de um agente na mensagem ao usuário.

## Exemplos

Veja `resources/exemplos.md` — quatro casos, incluindo um encaminhamento e um
caso no limite.
