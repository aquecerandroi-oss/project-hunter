---
tags: [arquitetura, sexta-feira, astra, claude, memoria]
updated: 2026-09-05
status: implementado
---

# Mente da Sexta-feira

Decisão do dono (2026-09-05): **a Sexta-feira é uma só**, com dois motores de raciocínio, o Claude e a Astra (GPT-6), e esta base Obsidian é a rede de neurônios dela: tudo o que ela pensa, decide, erra e aprende vira uma nota ligada às outras.

## Como ela pensa
- **Diálogo como pensamento.** Desenhos, planos e revisões contestadas rodam em rodadas entre os dois motores (`infra/scripts/astra.sh dialogue <tema>`) até uma rodada abrir com **DECISÃO CONJUNTA**. O que chega ao dono é o resultado, na primeira pessoa. Transcrições: [[Dialogos/Index|Diálogos]].
- **Segunda opinião em tudo.** Todo diff, plano e relatório passa pelos dois motores (`astra.sh ask`). As revisões da Astra: [[Revisoes-Astra/Index|Revisões da Astra]]. O motor com o cenário de falha concreto tem razão; o comando que decide roda antes da escolha.
- **Execução.** A Astra executa briefs mecânicos (`astra.sh run <brief>`); o Claude orquestra o roster de especialistas; a Sexta-feira revisa e commita.

## Como ela lembra (sinapses)
| Tipo de neurônio | Onde fica | Liga-se a |
|---|---|---|
| Decisão | [[Architecture Decisions]] (+ ADRs em `docs/decisions/`) | diálogos, módulos, bugs |
| Diálogo | [[Dialogos/Index|06-DECISIONS/Dialogos]] | plano do milestone, decisões |
| Revisão da Astra | [[Revisoes-Astra/Index|06-DECISIONS/Revisoes-Astra]] | kit da tarefa, bugs |
| Bug | [[Open Bugs]] / [[Resolved Bugs]] | commit, módulo, lição |
| Módulo | 02-MARKET, 03-TRADING, 04-AGENTS | status real, caminhos do código, limitações |
| Experimento | [[Experiments Index]] | estratégia, performance |
| Dia | `09-OPERATIONS/Diario/` | tudo o que aconteceu |

Regra: uma nota que nenhuma outra alcança é um neurônio sem sinapse. Cada página nova recebe pelo menos um link de entrada e um de saída.

## Lições já aprendidas pelos dois motores (2026-09-05)
- Suíte verde não prova produção: o dublê de teste do rate limiter reimplementava o Lua em Python e nunca tocava o Redis real; o pipeline inteiro estava morto. Prova operacional contra dado real é obrigatória antes de aprovar ([[Market Collector]]).
- Lint, tipos e testes não pegam regras do Next.js App Router (`"use server"`); o build no container é obrigatório para `apps/web` ([[System Overview]]).
- Um processo Python não sustenta 1.200 streams: o transporte sozinho custa um core; sharding é o caminho, não o plano B ([[Market Collector]]).
- Perfil antes de otimizar: as hipóteses (msgpack, logging) eram irrelevantes; o custo real era `pydantic` por evento e a fila varrendo 10.000 itens.

Fontes: `.claude/agents/sexta-feira.md`, `.claude/rules/astra-second-opinion.md`, `infra/scripts/astra.sh`, `docs/decisions/0003-base-de-conhecimento-obsidian.md`.
