---
tags: [decisao, obsidian, processo, conhecimento]
date: 2026-09-28
updated: 2026-09-28
owner: sexta-feira
status: vigente
decided_on: 2026-09-28
by: Everton
---

# Decisão — o Obsidian é o núcleo do projeto; toda tarefa passa por ele (28/09/2026)

**Everton:** "eu quero que o projeto inteiro adquira o conhecimento e sempre passe pelo obsidian — porque o obsidian é o núcleo de tudo".

## O que passou a valer

1. **Toda tarefa, de todo agente** (código, banco, operação, pesquisa, interface, documentação) **lê antes**: [[00-HOME]], a página do módulo, as notas `KB-*` do assunto, os bugs abertos e as decisões; e, para o que muda compra ou venda, [[KB-0149-o-que-a-mesa-real-ensinou]], [[Fila de Hipoteses]], [[Mapa de Estrategias]] e a página EXP. O relatório cita o que leu e o que isso mudou no plano.
2. **Escreve de volta no mesmo commit** o que aprendeu (lição, bug, decisão, avaliação datada, síntese da Astra), com links nos dois sentidos e o `obsidian_lint.py` em "base limpa".
3. **Estratégia continua com portão duro**: as ferramentas auditadas recusam mudança sem `--note obsidian/...` que cite o alvo ([[2026-09-26-mesa-meme-real-pausada-no-escopo]] foi a primeira decisão já nesse regime).
4. **Os robôs nunca leem notas ao decidir** — nota é texto humano, não entrada de laço ao vivo; o conhecimento chega a eles por código revisado e parâmetros com nota.

## Onde está escrito

`.claude/rules/obsidian-first.md` (regra completa) · `CLAUDE.md` (item 7 e o item 0 da leitura obrigatória) · os 14 cartões de agente em `.claude/agents/` · a memória do projeto (`.claude/memory/estrategia-passa-pelo-obsidian.md`) · a rotina da madrugada (lint e changelog todo dia).

## Relacionado

[[00-HOME]] · [[Proximas Hipoteses]] · [[06-DECISIONS/Revisoes-Astra/Index|Revisões da Astra]]
