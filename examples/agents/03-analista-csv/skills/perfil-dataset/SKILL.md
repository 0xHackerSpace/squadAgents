---
name: "perfil-dataset"
description: "Ordem das checagens de perfilamento e as anomalias de CSV que costumam invalidar a análise seguinte"
license: "MIT"
metadata:
  author: "exemplo"
  version: "1.0.0"
allowed-tools: ["python", "read"]
---

# Perfilamento de dataset

## Quando usar

Antes de qualquer afirmação sobre o conteúdo de um CSV.

## Ordem das checagens

1. **Forma** — linhas, colunas, tamanho em disco.
2. **Cabeçalho** — nomes duplicados, vazios, com espaço nas pontas.
3. **Tipos** — o inferido por coluna, e quantas células destoam dele.
4. **Ausentes** — contagem e proporção por coluna.
5. **Cardinalidade** — únicos por coluna; 1 único é coluna constante, N únicos em N linhas é identificador.
6. **Anomalias** — a tabela abaixo.

## Anomalias que importam

| Sinal | Costuma significar |
|---|---|
| Coluna numérica lida como texto | separador decimal misturado, ou milhar com ponto |
| Datas em mais de um formato | concatenação de fontes diferentes |
| Ausentes concentrados nas últimas linhas | exportação truncada |
| Ausentes concentrados em um período | falha de coleta, não fenômeno real |
| Coluna constante | filtro já aplicado na origem — a variação foi perdida antes de você |
| `-1`, `999`, `0000-00-00` | sentinela de ausente que ninguém converteu |
| Linhas exatamente duplicadas | junção sem deduplicação a montante |

## Como relatar

Uma tabela por coluna: nome, tipo, ausentes, únicos, exemplo. Depois as
anomalias, cada uma com a coluna e a leitura provável.

Diga o que **não** dá para concluir do dataset. Um perfil que só descreve o que
está lá deixa quem lê achando que o resto está bem.

## Não é sua função

Não limpe, não impute, não descarte. `scripts/perfil.py` mostra a forma esperada
do relatório.
