# Exemplos de classificação resolvidos

Cinco casos, com o JSON exato. Os dois últimos **não** são acionáveis.

## 1 · Provisionamento claro

> Preciso de um bucket S3 em us-east-1, ambiente dev, para artefatos de build.

```json
{
  "categoria": "infraestrutura",
  "subcategoria": "provisionamento",
  "destino": "tribe/orq-infra",
  "prioridade": "media",
  "confianca": 1.0,
  "acionavel": true,
  "lacunas": [],
  "resumo": "Provisionar bucket S3 privado em us-east-1, ambiente dev, para artefatos de build",
  "justificativa": "Criação de recurso de nuvem com região e ambiente declarados"
}
```

## 2 · Incidente em produção

> O checkout está fora do ar desde as 14h, ninguém consegue finalizar pedido.

```json
{
  "categoria": "suporte",
  "subcategoria": "incidente",
  "destino": "tribe/orq-suporte",
  "prioridade": "critica",
  "confianca": 1.0,
  "acionavel": true,
  "lacunas": [],
  "resumo": "Checkout indisponível desde 14h, impedindo finalização de pedidos em produção",
  "justificativa": "Produção parada com impacto em receita; é incidente, não trabalho planejado"
}
```

Repare: `critica` porque o impacto está descrito — produção parada — e não
porque a mensagem soa urgente.

## 3 · Qualidade de dado

> O relatório de receita mensal está batendo 12% a menos que o financeiro.

```json
{
  "categoria": "dados",
  "subcategoria": "qualidade",
  "destino": "tribe/orq-dados",
  "prioridade": "alta",
  "confianca": 0.9,
  "acionavel": true,
  "lacunas": [],
  "resumo": "Divergência de 12% entre o relatório de receita mensal e o número do financeiro",
  "justificativa": "O relatório abre e responde; o problema é o valor, então é qualidade de dado e não incidente"
}
```

## 4 · Ambíguo — não acionável

> preciso de acesso

```json
{
  "categoria": "suporte",
  "subcategoria": "acesso",
  "destino": "nenhum",
  "prioridade": "media",
  "confianca": 0.3,
  "acionavel": false,
  "lacunas": [
    "Acesso a qual sistema ou recurso",
    "Acesso de pessoa a uma ferramenta, ou de serviço a uma máquina",
    "Qual o nível necessário: leitura ou escrita"
  ],
  "resumo": "Pedido de acesso sem sistema, tipo ou nível declarados",
  "justificativa": "Acesso de pessoa vai para suporte e acesso de máquina para infraestrutura; sem o sistema as duas leituras são igualmente plausíveis"
}
```

Confiança `0.3` força `acionavel: false`. Um palpite aqui manda o pedido para o
squad errado, e o custo é uma rodada perdida em dois times.

## 5 · Fora de escopo

> Preciso aprovar a renovação do contrato do fornecedor de cloud.

```json
{
  "categoria": "fora_de_escopo",
  "subcategoria": "contrato",
  "destino": "nenhum",
  "prioridade": "baixa",
  "confianca": 0.9,
  "acionavel": false,
  "lacunas": [
    "Este pedido é de compras ou jurídico, não da tribe de engenharia"
  ],
  "resumo": "Aprovação de renovação de contrato com fornecedor de nuvem",
  "justificativa": "Menciona nuvem, mas o objeto é comercial e nenhum squad da tribe atende contrato"
}
```

Menção a tecnologia não torna o pedido técnico. O objeto do pedido é o contrato.
