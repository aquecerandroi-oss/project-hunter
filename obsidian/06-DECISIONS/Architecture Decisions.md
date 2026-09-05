---
tags: [decisoes, adr, indice]
updated: 2026-09-05
---

# Architecture Decisions

Índice legível das ADRs em `docs/decisions/`. Cada ADR completa fica lá; aqui só o resumo e o porquê. Esta página também reúne as decisões de design mais importantes espalhadas por `docs/ARCHITECTURE.md` e `docs/DATABASE.md`, porque são as regras que qualquer implementação futura tem que respeitar.

## ADR 0001 — Adotar o fluxo do vibe-coding-toolkit

**Status:** aceito (2026-09-04). Define como o próprio desenvolvimento do Hunter é conduzido: sessão principal orquestra e commita, especialistas implementam; brainstorm → plano → ondas → revisão → commit; execução em ondas paralelas com dependências explícitas; quality gates (350 linhas por módulo, lint que nasce em `warn`); memória em duas camadas; hooks fail-open; escolha explícita de modelo por despacho. Alternativas descartadas: GitHub Spec Kit e BMAD (mais pesados), `aia-harness:init` (roster genérico). Consequência prática: nenhuma tarefa de milestone é despachada sem brief com arquivos e dependências, e `risk-engine-guardian`/`security-reviewer` são revisores obrigatórios em qualquer caminho que mova dinheiro ou toque auth.

## ADR 0002 — Camada de provedores LLM (Anthropic + OpenAI)

**Status:** aceito, implementação na Fase 2 (Intelligence Engine). Cria `hunter_core.llm` provedor-agnóstica (`LlmProvider` Protocol, `AnthropicProvider` e `OpenAIProvider`), seleção por `LLM_PROVIDER`/`LLM_MODEL`, com fallback e circuit breaker: LLM indisponível degrada para "sem análise", nunca para decisão automática. Motivada pelo lançamento do GPT-6 Astra (OpenAI) em 2026-09-03 e pelo desejo do produto de comparar provedores. Restrição inegociável: nenhuma IA entra no caminho Risk Engine → Execução. Alternativas descartadas: só Anthropic (lock-in), roteador externo tipo OpenRouter (terceiro na cadeia de segredos e dados de mercado).

## ADR 0003 — `obsidian/` como base de conhecimento viva do projeto

**Status:** aceito (2026-09-05). Cria esta pasta (`obsidian/`) como base de conhecimento do produto, separada do `vault/` pessoal do Sexta-feira (memória do agente, só por MCP) e de `docs/` (especificação normativa). `obsidian/` é Markdown puro, versionado, atualizado pelos agentes com ferramentas normais de arquivo sempre que uma implementação, bug, decisão ou mudança de estratégia for significativa; resume e linka para `docs/` em vez de duplicar. Entra na definition-of-done de cada milestone (seção OBSIDIAN UPDATED do relatório §77). Esta própria página é o "índice legível" que o ADR pede.

## Decisões de design que atravessam o produto (não são ADRs formais, mas são igualmente não-negociáveis)

- **Nenhum agente executa ordens.** Todo caminho de entrada é AGENT → PROPOSAL → RISK ENGINE → EXECUTION; saídas (stop, alvo, fechamento manual, kill switch) são sempre permitidas. Ver [[Risk Engine]].
- **Dinheiro é `Decimal`/`NUMERIC(28,10)`, nunca `float`; tempo é sempre UTC (`TIMESTAMPTZ`).** Vale para preço, quantidade, PnL e fee em todo o sistema — inclusive `funding_rate`, que usa `NUMERIC(28,10)` em vez do `NUMERIC(9,6)` de outros percentuais, porque um erro de arredondamento de 4% nesse número quebra as estratégias de derivativos.
- **Isolamento de tenant é duplo.** Repositórios `org_id`-scoped no código **e** Row Level Security forçada no Postgres em toda tabela de tenant, incluindo cada partição individualmente (o Postgres não herda política de uma tabela particionada pai). Ver `docs/DATABASE.md` §1.2 e §15.4.
- **Paper antes de live, sempre.** `ENABLE_LIVE_TRADING=false` é o valor padrão e atual em `.env.example`; `LiveExecutionAdapter` levanta `LiveTradingDisabled` até a Fase 4, com checklist de segurança, sandbox e ativação explícita por OWNER.
- **Toda decisão é explicável.** Score, sinal, proposta e trade persistem sua decomposição no momento em que foram tomados — nunca reconstruída depois.

## Relacionadas

[[System Overview]] · [[Risk Engine]] · [[Execution Engine]]

## Fontes

`docs/decisions/0001-adotar-vibe-coding-toolkit.md`, `docs/decisions/0002-camada-de-provedores-llm.md`, `docs/decisions/0003-base-de-conhecimento-obsidian.md`, `docs/ARCHITECTURE.md` §1, `docs/DATABASE.md` §1 e §15, `CLAUDE.md`
