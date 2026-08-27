# Exemplos de decisão de resposta

## 1 · Concluído, nada pendente → notificar

Entrada: `agent-coord-infra` provisionou o bucket, sem pendências.

```json
{
  "correlacao": "01JQ8F3K2M4N5P6Q7R8S9T0V1W",
  "decisao": "notificar",
  "destino": null,
  "handoff_n": 0,
  "motivo": "Trabalho concluído dentro da categoria; nada pendente em outro squad",
  "mensagem_usuario": "O bucket foi criado em us-east-1, privado, com versionamento e criptografia ativados. Nada é necessário da sua parte.",
  "contexto_handoff": null
}
```

## 2 · Resultado abre trabalho em outra categoria → encaminhar

Entrada: o bucket foi criado, e o pedido original mencionava que a pipeline de
build precisa escrever nele.

```json
{
  "correlacao": "01JQ8F3K2M4N5P6Q7R8S9T0V1W",
  "decisao": "encaminhar",
  "destino": "tribe/coord-dados",
  "handoff_n": 0,
  "motivo": "Recurso provisionado; configurar a escrita da pipeline é trabalho de dados",
  "mensagem_usuario": null,
  "contexto_handoff": {
    "recurso": "s3://dev-checkout-artifacts",
    "regiao": "us-east-1",
    "ja_feito": "Bucket criado, privado, versionado",
    "pendente": "Apontar a pipeline de build para o novo bucket"
  }
}
```

O `contexto_handoff` carrega o que a próxima categoria precisa. Sem ele, o squad
de dados recomeçaria pelo começo.

## 3 · Bloqueio que depende de humano → notificar

Entrada: `agent-coord-infra` bloqueou — a mudança exige aprovação de rede.

```json
{
  "correlacao": "01JQ8F3K2M4N5P6Q7R8S9T0V1W",
  "decisao": "notificar",
  "destino": null,
  "handoff_n": 0,
  "motivo": "O bloqueio depende de aprovação humana, não de outra categoria",
  "mensagem_usuario": "A configuração está pronta, mas abrir a porta 5432 para a sub-rede de aplicação precisa da aprovação do time de rede. Assim que aprovarem, o restante segue sem novo pedido.",
  "contexto_handoff": null
}
```

Bloqueio não é automaticamente encaminhamento. Aqui não há outra categoria que
resolva — há uma pessoa que precisa decidir.

## 4 · No limite de encaminhamentos → notificar obrigatoriamente

Entrada: o pedido já passou por infra e por dados. O squad de dados sugere que
suporte configure o alerta.

```json
{
  "correlacao": "01JQ8F3K2M4N5P6Q7R8S9T0V1W",
  "decisao": "notificar",
  "destino": null,
  "handoff_n": 2,
  "motivo": "Limite de dois encaminhamentos atingido; o alerta fica para um pedido novo",
  "mensagem_usuario": "O bucket foi criado e a pipeline já escreve nele. Falta configurar o alerta de falha de escrita — abra um pedido para isso e ele vai direto para o time certo.",
  "contexto_handoff": null
}
```

A mensagem diz o que ficou de fora e o que fazer. Continuar seria um pedido
circulando entre três times sem retorno a quem pediu.
