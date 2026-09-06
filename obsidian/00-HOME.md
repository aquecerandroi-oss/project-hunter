---
tags: [home, hunter, indice]
updated: 2026-09-05
---

# PROJECT HUNTER — Base de Conhecimento

PROJECT HUNTER é uma plataforma SaaS de inteligência quantitativa para criptomoedas: encontra situações de **assimetria + anomalia + contexto + liquidez + controle de risco**, explica o porquê de cada sinal e prova a tese em paper/shadow antes de qualquer dinheiro real. Nenhum agente executa ordens — todo caminho de entrada é AGENTE → PROPOSTA → RISK ENGINE → EXECUÇÃO.

Esta pasta (`obsidian/`) é a base de conhecimento **do projeto**, viva e versionada no git, separada do `vault/` pessoal do Sexta-feira (memória do agente, só por MCP) e de `docs/` (especificação normativa: arquitetura, ADRs, planos, relatórios de milestone). As páginas aqui resumem e linkam para `docs/` em vez de duplicar. Ver [[Architecture Decisions]] → ADR 0003 para a decisão de criar esta estrutura.

## Onde estamos agora

**Atualizado em 2026-09-06 (noite).** M0 (fundação: monorepo, auth Clerk, organizações/workspaces,
dashboard, schema de 54 tabelas com RLS, Docker, CI) e **M1 fechados**. Hoje, **rodando 24 h por dia
na VPS**: o `market-worker` coletando 200 mercados da Binance, o `scanner-worker` (M2) construindo
baselines e avaliando features/anomalias/regime, e o `strategy-worker` com o **Shadow Lab** —
estratégias que registram "eu entraria aqui" e medem o que teria acontecido, **sem carteira, sem
ordem, sem um centavo**. Em andamento: **M2** (radar e oportunidades; a coleta ainda satura um core
com 200 mercados — [[Open Bugs]]) e **M3** (carteira virtual e Risk Engine: o núcleo puro do motor de
risco já existe e está testado, mas **nada o chama ainda**). Nada de execução real existe, e nenhum
`ENABLE_*` de autonomia está ligado. Ver `docs/audit/CURRENT_STATE.md` para o levantamento linha a
linha e o [[Changelog]] para o dia a dia.

## O pipeline (visão completa; hoje só a fundação existe)

```
Binance/Bybit WS  ──▶  [market-worker]      Market Data          (M1, planejado)
                             │
                             ▼
                       [scanner-worker]      Features → Anomalias
                                             → Regime → Opportunity  (M2, planejado)
                             │
                             ▼
                       [strategy-worker]     Agentes → Sinais
                                             → Propostas → Risk Engine (M4, planejado)
                             │  aprovado
                             ▼
                       [execution-worker]    Paper/Shadow Execution  (M3/M4, planejado)
                             │
                             ▼
                       [analytics-worker]    Estatísticas, outcomes  (M5, planejado)
```

Detalhe completo em [[Data Flow]] e `docs/PIPELINE.md`.

## Status por módulo

| Módulo | Status | Página | Milestone |
|---|---|---|---|
| Auth, tenancy, orgs/workspaces | implementado | [[System Overview]] | M0 |
| Dashboard shell, /system, settings | implementado | [[System Overview]] | M0 |
| Schema de banco (54 tabelas), RLS | implementado | [[System Overview]] | M0 |
| Docker, CI | implementado | [[Infrastructure]] | M0 |
| Workers (papéis reais) | planejado | [[Workers]] | M1+ |
| Market Collector | planejado | [[Market Collector]] | M1 |
| Exchange Adapters (Binance/Bybit) | planejado | [[Exchange Adapters]] | M1 |
| WebSockets de mercado | planejado | [[WebSockets]] | M1 |
| Feature Engine | planejado | [[Features]] | M2 |
| Anomaly Engine | planejado | [[Anomalies]] | M2 |
| Paper Trading / Execution Engine | planejado | [[Paper Trading]], [[Execution Engine]] | M3 |
| Portfolio (carteira permanente em USDT com âncora em BRL) | planejado | [[Portfolio]] | M3 |
| Risk Engine (contrato v2.1, perfil `paper_v1`) | **núcleo puro implementado** (`packages/risk-core`, 204 testes, `bf4924b` → `5f86028`); nada integrado | [[Risk Engine]] | **M3** (era M4; ADR 0005) |
| β contra o BTC (`beta_v1`, com validade) | implementado como pacote puro (`da2fb49`), sem tabela | [[Risk Engine]] | M3 |
| Estratégias / Agentes + ponte sinal → proposta | planejado | [[Strategies]], [[Agents Overview]] | M4 |
| Analytics / Performance | planejado | [[Performance Overview]] | M5 |

## Como navegar

- [[Mente da Sexta-feira]] — como a assistente pensa (Claude + Astra) e onde cada tipo de memória fica; [[Dialogos/Index|diálogos]] e [[Revisoes-Astra/Index|revisões da Astra]]. Mais recente: [[Dialogos/M3]] — carteira virtual e Risk Engine, a partir da diretiva do Everton de 2026-09-06 (ADR 0005; plano `docs/plans/M3.md`; contrato `docs/RISK_ENGINE.md` v2). O M3 **não** declara modo autônomo: as entradas são manuais e a ponte sinal → proposta é do M4.

- **01-ARCHITECTURE/** — visão de sistema, fluxo de dados, infraestrutura, workers.
- **02-MARKET/** — coleta de mercado, adapters de exchange, WebSockets, features, anomalias (tudo planejado M1–M2).
- **03-TRADING/** — paper trading, risk engine, execução, portfolio, estratégias (tudo planejado M3–M4).
- **04-AGENTS/** — visão geral de agentes e as quatro estratégias do MVP (planejado M4).
- **05-EXPERIMENTS/** — índice de experimentos ([[Experiments Index]], `EXP-NNNN`), template e os experimentos do Shadow Lab em andamento desde 2026-09-06: [[EXP-0001-momentum-v1]], [[EXP-0002-volume-anomaly-v1]] e [[EXP-0004-politicas-de-saida]] (replay de oito políticas de saída sobre as entradas já congeladas, `2c6bb2d` — pesquisa que não escreve nada), todos com avaliações **datadas e acrescentadas** e o SQL que produziu cada número.
- **06-DECISIONS/** — índice legível das ADRs.
- **07-BUGS/** — bugs abertos e resolvidos, com hash de commit.
- **08-CHANGELOG/** — uma entrada por commit, agrupado por dia.
- **09-OPERATIONS/** — deploy, variáveis de ambiente, monitoramento e o **Diário** (`09-OPERATIONS/Diario/AAAA-MM-DD.md`, uma nota por dia de trabalho: o que foi feito, o que foi decidido, o que ficou em voo) — mais recente: [[2026-09-06]].
- **10-PERFORMANCE/** — visão de performance (hoje sem trades, descreve o que vai alimentar as métricas).
- **11-KNOWLEDGE/** — conhecimento **externo** curado pela Sexta-feira com revisão da Astra: estratégias, análise técnica, microestrutura, perpétuos, risco, estatística de backtest. Cada nota traz fonte, qualidade da evidência e uma hipótese testável no Lab; as candidatas ficam em [[Strategy Backlog]] e só viram experimento pelo caminho normal (nada é ativado sozinho). Índice: [[11-KNOWLEDGE/Index|Conhecimento]].

## Fontes

- `docs/ARCHITECTURE.md`
- `docs/PRODUCT.md`
- `docs/ROADMAP.md`
- `docs/PIPELINE.md`
- `docs/decisions/0003-base-de-conhecimento-obsidian.md`
- `docs/audit/CURRENT_STATE.md` (em elaboração)
