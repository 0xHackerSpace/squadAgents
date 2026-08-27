# Referência da linha de comando

Todo comando do `oaf` recebe um **diretório contendo `AGENTS.md`**, ou um
diretório que contenha vários deles. Nenhum comando recebe o `AGENTS.md`
diretamente como argumento — a unidade do formato é o diretório.

```
oaf [--version] COMANDO [argumentos]
```

| Comando | Faz | Precisa de chave de API |
|---|---|---|
| [`validate`](#oaf-validate) | confere os agentes contra a spec | não |
| [`inspect`](#oaf-inspect) | mostra a definição resolvida | não |
| [`run`](#oaf-run) | executa um agente | **sim** |
| [`package`](#oaf-package) | empacota agentes em um `.zip` | não |
| [`unpack`](#oaf-unpack) | extrai um `.zip` e inventaria | não |
| [`trail`](#oaf-trail) | lê uma trilha de execução | não |
| [`export`](#oaf-export) | converte para o formato de outro harness | não |

## Códigos de saída

Iguais em todos os comandos, e verificados:

| Código | Significa |
|---|---|
| `0` | sucesso |
| `1` | falha — validação reprovou, agente não encontrado, arquivo ilegível, execução falhou |
| `2` | uso incorreto — comando ausente, comando desconhecido, argumento obrigatório faltando |

Avisos **nunca** afetam o código de saída. Só `error` reprova.

Um **pipe fechado** não é erro: `oaf trail x | head` sai `0` sem imprimir
traceback por cima da saída do usuário.

## Convenções

- **stdout** carrega o resultado; **stderr** carrega notas, avisos e erros. Isso
  torna `oaf inspect X --json > def.json` seguro em pipe.
- Argumentos marcados **obrigatório** não têm padrão; sua ausência é saída `2`.
- Onde há `--json`, ele substitui a saída humana inteira, não a acrescenta.

---

## `oaf validate`

Confere cada agente encontrado contra as regras da spec. Este é o comando de CI.

```
oaf validate [PATH] [--profile {strict,lenient}] [--json] [--quiet]
```

| Argumento | Padrão | Descrição |
|---|---|---|
| `PATH` | `.` | Diretório do agente, ou diretório com vários. **Todos** os agentes encontrados são conferidos. |
| `--profile` | `lenient` | `strict` aplica toda regra como escrita; `lenient` rebaixa a aviso os desvios que os agentes de referência exibem. |
| `--json` | — | Emite os diagnósticos como JSON em vez do relatório humano. |
| `--quiet` | — | Imprime só erros, omitindo avisos e notas. |

### Qual perfil usar

Esta é a única escolha real do comando:

- **`lenient`** — para *consumir* agentes de terceiros. Os quatro desvios documentados em [`CONFORMANCE.md`](CONFORMANCE.md) viram avisos.
- **`strict`** — para *autorar* agentes seus. Toda regra da spec é erro. Use em CI sobre código que você escreve.

Regras fora do conjunto `NEGOTIABLE` têm a mesma severidade nos dois perfis — o
perfil não afeta erro de YAML, semver inválido ou skill obrigatória ausente.

### Forma do JSON

```json
{
  "profile": "lenient",
  "agents": [
    {
      "slug": "squad/validador",
      "root": "squad/validador",
      "ok": true,
      "diagnostics": [
        {
          "severity": "warning",
          "code": "identity.slug-not-canonical",
          "message": "slug 'x' is not 'vendorKey/agentKey' ...",
          "path": "squad/validador/AGENTS.md",
          "line": 2,
          "field": "slug"
        }
      ]
    }
  ]
}
```

O `code` é estável e serve para suprimir regra específica; a `message` pode mudar
entre versões. `severity` é `error`, `warning` ou `info`.

### Exemplos

```bash
oaf validate                                  # o diretório atual
oaf validate squad --profile strict           # CI sobre agentes próprios
oaf validate ./baixados --quiet               # só o que reprova
oaf validate . --json | jq '.agents[] | select(.ok == false)'
```

---

## `oaf inspect`

Imprime a definição **totalmente resolvida** — o "sem estado escondido" que o
formato promete, tornado explícito. Não precisa de chave de API.

```
oaf inspect PATH [--json] [--prompt] [--harness {agno,dry-run}]
```

| Argumento | Padrão | Descrição |
|---|---|---|
| `PATH` | obrigatório | Diretório do agente. **Os irmãos dele viram o workspace**, então referências a sub-agentes resolvem. |
| `--json` | — | Emite a definição resolvida como JSON. |
| `--prompt` | — | Imprime o system prompt composto, em vez do resumo. |
| `--trace` | — | Imprime o **traço de construção** — cada agente e cada aresta de delegação, na ordem em que o harness as monta — em vez do resumo. |
| `--harness` | `dry-run` | Qual adapter resolve o modelo. `dry-run` não instancia cliente nem exige chave. |

`--prompt` vence `--json`: pedir os dois imprime o prompt. Para os prompts de
uma árvore inteira de uma vez, veja [`PROMPTS.md`](PROMPTS.md) e o gerador que o
produz.

### `--trace` sem executar nada

`oaf inspect PATH --trace` monta o grafo e imprime o que o harness faria, sem
chamar modelo algum. É a forma barata de conferir a topologia de uma tribe
inteira:

```
build     tribe/manager · openai/gpt-5.2
  delegate  tribe/manager -> tribe/orq-infra (orquestrador-infraestrutura)
  build     tribe/orq-infra · openai/gpt-5.2
    delegate  tribe/orq-infra -> tribe/infra (coordenador)
```

### Por que os irmãos importam

`oaf inspect squad/orchestrador` carrega `squad/` como workspace. Inspecionar o
mesmo agente copiado para fora do squad mostraria os sub-agentes como
`missing` — não é bug, é o workspace ter ficado vazio.

### Exemplos

```bash
oaf inspect squad/orchestrador                  # membros, papéis, modelo resolvido
oaf inspect squad/validador --prompt            # exatamente o que o agente recebe
oaf inspect squad/terraform --json | jq '.skills'
oaf inspect ./agente --json | jq -r '.resolvedModel.origin'   # de onde veio o modelo
```

---

## `oaf run`

Executa o agente. **É o único comando que precisa de chave de API.**

```
oaf run PATH MESSAGE... [--harness {agno,dry-run}] [--model MODEL]
                        [--skills {eager,progressive}] [--stream]
```

| Argumento | Padrão | Descrição |
|---|---|---|
| `PATH` | obrigatório | Diretório do agente. Os irmãos viram o workspace. |
| `MESSAGE...` | obrigatório | A mensagem. Múltiplas palavras são juntadas com espaço — aspas são opcionais, mas evitam que o shell interprete `?`, `*` e `&`. |
| `--harness` | `agno` | Backend de execução. `dry-run` constrói e **recusa executar** (sai `1`). |
| `--model` | — | Sobrescreve o modelo de **todos** os agentes desta execução. |
| `--skills` | do `harnessConfig` | Como as skills locais chegam ao agente. |
| `--stream` | — | Imprime a resposta conforme ela é produzida. |
| `--trace` | — | Acrescenta um traço de execução a um arquivo, em linhas JSON. |
| `--correlation` | um novo | Identificador desta execução. Passe o seu para amarrar o traço a um pedido que você já rastreia. |

### `run` valida antes de executar

Antes de construir qualquer coisa, `run` valida em `lenient` e **recusa executar
se houver erro** — sai `1` imprimindo os erros. Um agente com definição quebrada
produz comportamento inexplicável, e gasta tokens fazendo isso.

Isso é deliberado e não tem flag para desligar. Para inspecionar um agente
quebrado sem executá-lo, use `oaf inspect`, que funciona em agente inválido.

### `--model`

Aceita três formas:

| Forma | Exemplo | Vira |
|---|---|---|
| `provider/nome` | `anthropic/claude-sonnet-5` | exatamente isso |
| um alias da spec | `sonnet` | o que a tabela de aliases mapear |
| um id solto | `gpt-5.2` | provider inferido pelo prefixo do nome |

Vence tudo: o bloco `model:` do manifesto e as variáveis de ambiente. Serve para
rodar qualquer agente em qualquer modelo sem editar o `AGENTS.md` dele.

Para conferir o que foi escolhido sem gastar chamada:
`oaf inspect PATH --json | jq .resolvedModel`.

### `--skills`

| Valor | Efeito |
|---|---|
| `progressive` | O prompt lista nome, descrição e arquivos de cada skill. Uma tool `load_skill(nome)` devolve o corpo sob demanda. |
| `eager` | Todo corpo de skill entra no prompt inicial. |

Sem a flag, vale o que `harnessConfig.<harness>.progressive-disclosure` disser;
sem isso, `progressive`. Use `eager` para depurar um comportamento que dependa da
skill — assim ela está no contexto desde o primeiro token.

### O traço

`--trace FILE` acrescenta ao arquivo, nunca reescreve — uma trilha cujo passado
pode mudar não é evidência. O arquivo é criado se não existir, e vários pedidos
convivem nele, separados por `--correlation`.

O que ele registra:

| Evento | Quando |
|---|---|
| `build` | cada agente construído, com modelo e profundidade |
| `delegate` | cada aresta de delegação que o harness monta |
| `run-start` / `run-end` | início e fim da execução, com duração |
| `error` | falha da execução, com o tipo e a mensagem |

**O que ele não registra:** as delegações que um backend faz internamente.
Depois que um `Team` do Agno começa a rodar, o líder chama os membros dentro do
Agno, onde este harness não está no caminho. O traço diz o que foi montado e o
que foi invocado — não cada passo interno.

A trilha é escrita **mesmo quando a execução falha**: o evento de erro é o mais
importante de ter.

### Exemplos

```bash
export OPENAI_API_KEY=...
oaf run squad/orchestrador "preciso de um bucket para artefatos de build"
oaf run ./agente "resuma isso" --model anthropic/claude-sonnet-5
oaf run ./agente "explique" --skills eager --stream
oaf run ./agente oi --harness dry-run     # só constrói; sempre sai 1
oaf run ./tribe/manager "..." --trace trilha.jsonl --correlation pedido-42
```

---

## `oaf package`

Empacota todo agente encontrado em um `.zip` distribuível, com `PACKAGE.yaml` na
raiz. **Sempre escreve o dialeto da spec**, mesmo tendo lido outro.

```
oaf package PATH -o FILE [--name NAME] [--package-version VERSION]
                         [--mode {bundled,referenced}]
```

| Argumento | Padrão | Descrição |
|---|---|---|
| `PATH` | obrigatório | Diretório com os agentes. Todos os encontrados entram. |
| `-o`, `--output` | **obrigatório** | O arquivo `.zip` a escrever. Diretórios pais são criados. |
| `--name` | nome do diretório de origem | Nome do pacote registrado no `PACKAGE.yaml`. |
| `--package-version` | `0.1.0` | Versão **do pacote**, não de nenhum agente. Os agentes mantêm as suas. |
| `--mode` | `bundled` | `contents.mode` no `PACKAGE.yaml`. |

### `--mode`

| Valor | Significa |
|---|---|
| `bundled` | Autocontido. Funciona offline. |
| `referenced` | Skills com URL well-known devem ser buscadas na instalação. Pacote menor, sempre atualizado. |

Hoje **a flag só grava o campo** — ela não altera o que entra no zip, porque este
harness não busca skills well-known (o porquê está em [`CONFORMANCE.md`](CONFORMANCE.md)).
Com skills só locais, os dois modos produzem o mesmo conteúdo e `bundled` é a
declaração honesta.

### O que não entra

`.git`, `.venv`, `__pycache__`, `.pytest_cache`, `.DS_Store` e arquivos `.pyc`/`.pyo`.

### Exemplos

```bash
oaf package squad -o dist/squad-1.0.0.zip --name squad --package-version 1.0.0
oaf package ./meu-agente -o /tmp/x.zip
```

---

## `oaf unpack`

Extrai um `.zip` e inventaria o que ele traz, cruzando o manifesto com o disco.

```
oaf unpack ARCHIVE -d DIR
```

| Argumento | Padrão | Descrição |
|---|---|---|
| `ARCHIVE` | obrigatório | O `.zip` a extrair. |
| `-d`, `--destination` | **obrigatório** | Diretório de destino. Criado se não existir. |

Lê os três dialetos de `PACKAGE.yaml` encontrados no mundo real e informa qual
era. Antes de extrair qualquer byte, **recusa membros com caminho absoluto ou
`..`** — um zip é conteúdo de terceiro.

### O que o cruzamento reporta

| Código | Severidade | Quando |
|---|---|---|
| `package.missing-agent` | erro | o manifesto lista um agente que não está no pacote |
| `package.no-agents` | erro | nenhum `AGENTS.md` encontrado |
| `package.version-mismatch` | aviso | o manifesto e o `AGENTS.md` discordam da versão |
| `package.unlisted-agent` | aviso | há agente no pacote fora do manifesto |
| `package.no-manifest` | aviso | não há `PACKAGE.yaml` na raiz |

Sai `1` se houver erro.

### Exemplo

```bash
oaf unpack dist/squad-1.0.0.zip -d ./instalados
oaf validate ./instalados          # confira antes de rodar
```

---

## `oaf trail`

Lê uma trilha escrita por `run --trace` e a apresenta agrupada por pedido.

```
oaf trail FILE [--correlation ID] [--json]
```

| Argumento | Padrão | Descrição |
|---|---|---|
| `FILE` | obrigatório | A trilha em linhas JSON. |
| `--correlation` | todos | Mostra só os eventos deste pedido. |
| `--json` | — | Emite os eventos como JSON, agrupados por correlação. |

Uma linha malformada é **pulada, não fatal**: a trilha é acrescentada por várias
execuções, e uma linha ruim não pode esconder o resto. Campos desconhecidos
também são ignorados, para que uma trilha escrita por uma versão mais nova
continue legível.

Sai `1` se o arquivo não existir, ou se `--correlation` não casar com nada.

### Exemplos

```bash
oaf trail trilha.jsonl                          # todos os pedidos
oaf trail trilha.jsonl --correlation pedido-42  # um só
oaf trail trilha.jsonl --json | jq '.[] | map(select(.kind == "error"))'
```

---

## `oaf export`

Converte um agente para o formato nativo de outro harness.

```
oaf export PATH --target {claude-code,deep-agents,goose,letta} -d DIR
```

| Argumento | Padrão | Descrição |
|---|---|---|
| `PATH` | obrigatório | O agente a exportar. |
| `--target` | **obrigatório** | O formato de destino. |
| `-d`, `--destination` | **obrigatório** | Diretório raiz. O layout abaixo dele é a convenção do alvo. |

### Os alvos

| `--target` | Escreve | Observação |
|---|---|---|
| `claude-code` | `DIR/<vendorKey>/<agentKey>/SKILL.md` + `skills/` | A identidade OAF vai para uma seção de proveniência no corpo. |
| `goose` | `DIR/<vendorKey>/<agentKey>/AGENTS.md` | O bloco `harnessConfig.goose` é promovido a chaves de topo. |
| `deep-agents` | `DIR/<agentKey>/agent.md` + `skills/` | Instruções e skills ficam separadas. |
| `letta` | `DIR/<agentKey>.af` | JSON Agent File; `memory.blocks` vira memory block de verdade. |

### Export é lossy, e diz o que perdeu

Nenhum formato de destino é tão expressivo quanto o OAF. Todo export imprime em
**stderr** o que não atravessou: packs, weblets, servidores MCP a reconfigurar e
sub-agentes — que precisam ser exportados **separadamente**, um comando cada.

```bash
oaf export squad/orchestrador --target letta -d ./out
oaf export squad/validador    --target letta -d ./out
oaf export squad/terraform    --target letta -d ./out
```

---

## Variáveis de ambiente

| Variável | Lida por | Efeito |
|---|---|---|
| `OAF_MODEL_SONNET` | `run`, `inspect` | Redefine o alias `sonnet`. Aceita `provider/nome` ou um id solto. |
| `OAF_MODEL_OPUS` | idem | Redefine `opus`. |
| `OAF_MODEL_HAIKU` | idem | Redefine `haiku`. |
| `OPENAI_API_KEY` | `run` | Credencial, quando o modelo resolvido for OpenAI. |
| `ANTHROPIC_API_KEY` | `run` | Credencial, quando for Anthropic. |
| `OAF_REFERENCE_CORPUS` | `pytest` | Onde está o corpus de referência; a suíte é pulada se não existir. |

Configs de MCP podem referenciar variáveis próprias por `${VAR}` em `auth.token`
ou por `auth.env_var`. Elas não são lidas pelo CLI — uma não definida vira o aviso
`mcp.unset-credential` no `validate`.

### Precedência do modelo

Do mais forte ao mais fraco:

```
--model  >  model: do AGENTS.md  >  OAF_MODEL_<ALIAS>  >  tabela padrão  >  fallback
```

`oaf inspect PATH --json | jq -r '.resolvedModel.origin'` diz qual desses decidiu:
`override`, `manifest.model`, `alias:sonnet`, `alias:literal` ou `default`.

---

## Receitas

**Portão de CI sobre agentes próprios:**

```bash
oaf validate squad --profile strict --quiet || exit 1
```

**Conferir um agente de terceiro antes de rodar:**

```bash
oaf unpack baixado.zip -d ./tmp
oaf validate ./tmp                        # lenient: aceita os desvios conhecidos
oaf inspect ./tmp/agente --prompt         # leia o prompt antes de executar
```

**Comparar dois modelos no mesmo agente:**

```bash
for m in openai/gpt-5.2 anthropic/claude-sonnet-5; do
  echo "── $m"; oaf run ./agente "mesma pergunta" --model "$m"
done
```

**Listar tudo que reprova em uma árvore, como JSON:**

```bash
oaf validate . --profile strict --json \
  | jq -r '.agents[] | select(.ok==false) | .slug'
```
