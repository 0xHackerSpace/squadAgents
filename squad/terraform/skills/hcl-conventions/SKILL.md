---
name: "hcl-conventions"
description: "Nomenclatura, estrutura de arquivos e baseline de segurança obrigatório para todo Terraform gerado por este squad"
license: "MIT"
metadata:
  author: "0xhackerspace"
  version: "1.0.0"
allowed-tools: []
---

# Convenções de HCL

## Quando usar

Antes de escrever qualquer arquivo `.tf`.

## Estrutura de arquivos

```
main.tf         recursos
variables.tf    entradas, com type e description obrigatórios
outputs.tf      saídas, com description
versions.tf     required_version e required_providers, sempre fixados
```

Nunca concentre tudo em um `main.tf` só, mesmo em exemplo pequeno.

## Nomenclatura

- Recursos e variáveis em `snake_case`.
- Nome do recurso descreve o **papel**, não o tipo: `resource "aws_s3_bucket" "artifacts"`, nunca `"bucket1"` nem `"my_bucket"`.
- Toda tag obrigatória: `Environment`, `ManagedBy = "terraform"`, `Owner`.

## Baseline de segurança

Não negociável, mesmo que a demanda não mencione:

- Criptografia em repouso habilitada explicitamente.
- Bloqueio de acesso público explícito em armazenamento.
- Versionamento habilitado onde o provedor oferece.
- Logging de acesso habilitado quando existir.
- Nenhum `cidr_blocks = ["0.0.0.0/0"]` em ingress. Egress amplo é aceitável se declarado.

## Variáveis

Toda `variable` carrega `type` e `description`. Segredo carrega `sensitive = true`.
Só use `default` quando o valor for seguro em qualquer ambiente — região e nome
de ambiente não têm padrão seguro.

## Consulte também

`resources/exemplo-s3.tf` traz a forma esperada de um recurso completo.
