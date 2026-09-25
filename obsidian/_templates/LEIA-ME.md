---
tags: [knowledge, templater, meta]
status: vivo
owner: sexta-feira
updated: 2026-09-25
---

# `_templates/` — modelos do Templater

Modelos de texto para o plugin **Templater** (instalado em 2026-09-25, Everton). Cada um evita
reescrever à mão a estrutura que um leitor automático (`infra/research/queue.py`, o linter de
frontmatter, o Dataview de [[Mapa de Estrategias]]) já exige por convenção.

## Ajuste único de configuração

Settings → **Templater** → **Template folder location** → digite `_templates` (relativo à raiz do
vault, que é `obsidian/`, não a raiz do repositório — `docs/OBSIDIAN.md` já avisa disso para os
canvases). Sem esse ajuste, o comando "Insert Template" não encontra estes três arquivos.

## Como inserir um modelo

Paleta de comandos (Ctrl/Cmd+P) → **Templater: Insert Template** (ou **Create new note from
template**, se preferir gerar o arquivo já com o nome certo) → escolher o modelo pelo nome. Um
atalho de teclado pode ser configurado em Settings → Hotkeys, procurando por "Templater".

## Os três modelos

| Modelo | Onde colar o resultado | O que preencher depois |
|---|---|---|
| `Nova hipotese.md` | No **fim** de [[Fila de Hipoteses]], depois do último bloco `## H-0nn` | Trocar `H-0XX` pelo próximo id livre (olhar o último bloco do arquivo — id repetido é erro do moinho), o título, e os seis campos comentados. Nasce `status: aberta` |
| `Nova ideia do Everton.md` | No fim de `Ideias do Everton.md` (arquivo ainda não existe no repositório — crie-o na primeira vez que usar este modelo, uma linha por ideia) | Só a frase da ideia; data e status (`em aberto`) já vêm prontos |
| `Nova nota de pesquisa.md` | Um arquivo novo, depois renomeado para `KB-NNNN-<slug>.md` em `obsidian/11-KNOWLEDGE/` (próximo número livre, nunca reaproveitado) | `tema`, `fonte`, `fonte_url`, `lido_em`, `evidencia`, `hipotese_testavel`, `astra`, `confiança` e os dez campos padronizados (`tipo`, `hipotese`, `variavel`, `populacao`, `efeito`, `ic`, `veredito`, `proximo_passo`, `classe_de_perda`, `mercado`) — a própria nota explica cada um na tabela logo abaixo do frontmatter |

## Por que não há mais automação aqui

Numeração de `H-0nn` e de `KB-NNNN` fica manual de propósito: um modelo Templater não lê o conteúdo
de outro arquivo sem um script de usuário (`tp.user.*`), e escrever esse script para economizar
contar até o último número é complexidade que a Regra 2 de `CLAUDE.md` ("simplicidade primeiro")
não justifica hoje. Se a fila crescer a ponto de colisão de id virar problema real, isso é uma
tarefa própria, não um efeito colateral deste conjunto de modelos.
