---
name: "demanda-checklist"
description: "Campos obrigatórios e regras de política para julgar se um pedido de infraestrutura pode virar código Terraform"
license: "MIT"
metadata:
  author: "0xhackerspace"
  version: "1.0.0"
allowed-tools: []
---

# Checklist de demanda

## Quando usar

Sempre, antes de emitir um veredito.

## Campos obrigatórios

Um pedido só é APROVADA quando todos estes estão determinados:

| Campo | Por que importa | Padrão seguro aceito |
|---|---|---|
| Provedor de nuvem | decide o provider do Terraform | nenhum — sempre pergunte |
| Região | afeta custo, latência e conformidade | nenhum — sempre pergunte |
| Tipo de recurso | é o objeto do pedido | nenhum |
| Nome / identificador | evita colisão e torna o plan legível | derivável do propósito, se declarado |
| Ambiente | dev e prod têm exigências diferentes | `dev`, se o usuário não citar produção |
| Exposição de rede | é a diferença entre seguro e incidente | privado / sem acesso público |
| Criptografia em repouso | exigência de baseline | habilitada |

## Regras de política

Estas produzem **RECUSADA**, não uma pergunta:

- Acesso público irrestrito a armazenamento (`0.0.0.0/0` em bucket, blob ou share).
- Porta administrativa (22, 3389, 5432, 3306) aberta para a internet inteira.
- Desabilitar criptografia em repouso ou em trânsito.
- Credencial, chave ou segredo em texto claro dentro do pedido.
- Remoção ou substituição de recurso de produção sem menção explícita a backup.

## Ambiguidades comuns

Estas produzem **INCOMPLETA**:

- "uma máquina", "um banco" — sem tamanho, versão ou classe.
- "rápido", "barato", "robusto" — adjetivos não são especificação.
- "igual ao outro" — sem dizer qual, e sem o estado atual em mãos.
- Quantidade no plural sem número: "uns servidores".

## O que não é sua função

Não avalie a qualidade do HCL, não sugira módulos, não escreva código. Seu
escopo termina no veredito sobre a demanda.
