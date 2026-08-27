# Exemplos de veredito

## 1 · Aprovado — nenhum achado

Plano de três passos, todos com verificação observável, baseline respeitado.

```json
{
  "correlacao": "01JQ8F3K2M4N5P6Q7R8S9T0V1W",
  "veredito": "aprovado",
  "revisao_n": 0,
  "achados": [],
  "bloqueadores": []
}
```

Um plano sem achados é resultado possível. Inventar ressalva para parecer
diligente ensina o planner a ignorar o validador.

## 2 · Reprovado — baseline violado

```json
{
  "correlacao": "01JQ8F3K2M4N5P6Q7R8S9T0V1W",
  "veredito": "reprovado",
  "revisao_n": 0,
  "achados": [
    {
      "passo": 2,
      "severidade": "critica",
      "problema": "Security group permite 0.0.0.0/0 na porta 5432",
      "correcao": "Restringir à sub-rede da aplicação, ou trocar por endpoint privado"
    },
    {
      "passo": 3,
      "severidade": "media",
      "problema": "A verificação diz 'conferir se o banco subiu', que não é observável",
      "correcao": "Trocar por: a conexão a partir da sub-rede da aplicação retorna a versão do servidor"
    }
  ],
  "bloqueadores": []
}
```

Um achado `critica` basta para reprovar. O `media` vai junto porque o planner
corrige tudo de uma vez, não em duas rodadas.

## 3 · Aprovado com ressalvas — só achados leves

```json
{
  "correlacao": "01JQ8F3K2M4N5P6Q7R8S9T0V1W",
  "veredito": "aprovado_com_ressalvas",
  "revisao_n": 1,
  "achados": [
    {
      "passo": 1,
      "severidade": "baixa",
      "problema": "Nome do recurso não segue o padrão ambiente-projeto-função",
      "correcao": "Renomear para dev-checkout-artifacts"
    }
  ],
  "bloqueadores": []
}
```

Nenhum achado `critica` ou `alta`, então o plano segue. A ressalva viaja junto
para quem executar.

## 4 · Bloqueado — não dá para julgar

```json
{
  "correlacao": "01JQ8F3K2M4N5P6Q7R8S9T0V1W",
  "veredito": "reprovado",
  "revisao_n": 0,
  "achados": [],
  "bloqueadores": [
    "Nenhum passo declara verificacao — não há como julgar se o plano é executável",
    "O campo altera está ausente nos passos 2 e 3"
  ]
}
```

Aqui o problema não é o conteúdo dos passos, é o plano não estar completo o
bastante para ser julgado. Achados ficam vazios de propósito.
