# Sentinelas de ausente

Valores que significam "sem dado" mas não são nulos, e por isso passam batido
em `isna()`:

| Valor | Onde aparece |
|---|---|
| `-1`, `-999`, `9999` | exportação de sistema legado, campo numérico |
| `0000-00-00`, `1900-01-01`, `1970-01-01` | data zero de MySQL, ou epoch usado como padrão |
| `""`, `" "` | CSV escrito sem tratamento de vazio |
| `N/A`, `NA`, `null`, `NULL`, `nan`, `-` | texto digitado por humano ou serializado sem cuidado |
| `0` em coluna que não admite zero | preço, idade, área — zero ali é ausente disfarçado |

Reporte-os como ausentes suspeitos, separados dos nulos de verdade. Não
converta.
