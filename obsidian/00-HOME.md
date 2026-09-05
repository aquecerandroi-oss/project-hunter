---
tags: [home, hunter, indice]
updated: 2026-09-05
---

# PROJECT HUNTER — Base de Conhecimento

PROJECT HUNTER é uma plataforma SaaS de inteligência quantitativa para criptomoedas: encontra situações de **assimetria + anomalia + contexto + liquidez + controle de risco**, explica o porquê de cada sinal e prova a tese em paper/shadow antes de qualquer dinheiro real. Nenhum agente executa ordens — todo caminho de entrada é AGENTE → PROPOSTA → RISK ENGINE → EXECUÇÃO.

Esta pasta (`obsidian/`) é a base de conhecimento **do projeto**, viva e versionada no git, separada do `vault/` pessoal do Sexta-feira (memória do agente, só por MCP) e de `docs/` (especificação normativa: arquitetura, ADRs, planos, relatórios de milestone). As páginas aqui resumem e linkam para `docs/` em vez de duplicar. Ver [[Architecture Decisions]] → ADR 0003 para a decisão de criar esta estrutura.

## Onde estamos agora

**Fim do Milestone 0** (fundação): monorepo, auth real (Clerk), organizações/workspaces/membros/convites, dashboard shell, página de sistema, settings, schema completo do banco (54 tabelas), migrações com RLS, Docker, CI. **Nada de mercado, agentes, risco ou execução está implementado ainda** — essas peças existem só como schema e interface, aguardando M1–M5. Ver `docs/audit/CURRENT_STATE.md` (em elaboração) para o levantamento linha a linha do que existe hoje.

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
| Portfolio | planejado | [[Portfolio]] | M3 |
| Risk Engine | planejado | [[Risk Engine]] | M4 |
| Estratégias / Agentes | planejado | [[Strategies]], [[Agents Overview]] | M4 |
| Analytics / Performance | planejado | [[Performance Overview]] | M5 |

## Como navegar

- [[Mente da Sexta-feira]] — como a assistente pensa (Claude + Astra) e onde cada tipo de memória fica; [[Dialogos/Index|diálogos]] e [[Revisoes-Astra/Index|revisões da Astra]].

- **01-ARCHITECTURE/** — visão de sistema, fluxo de dados, infraestrutura, workers.
- **02-MARKET/** — coleta de mercado, adapters de exchange, WebSockets, features, anomalias (tudo planejado M1–M2).
- **03-TRADING/** — paper trading, risk engine, execução, portfolio, estratégias (tudo planejado M3–M4).
- **04-AGENTS/** — visão geral de agentes e as quatro estratégias do MVP (planejado M4).
- **05-EXPERIMENTS/** — índice de experimentos (`EXP-NNNN`) e template; hoje vazio.
- **06-DECISIONS/** — índice legível das ADRs.
- **07-BUGS/** — bugs abertos e resolvidos, com hash de commit.
- **08-CHANGELOG/** — uma entrada por commit, agrupado por dia.
- **09-OPERATIONS/** — deploy, variáveis de ambiente, monitoramento e o **Diário** (`09-OPERATIONS/Diario/AAAA-MM-DD.md`, uma nota por dia de trabalho: o que foi feito, o que foi decidido, o que ficou em voo) — mais recente: [[2026-09-05]].
- **10-PERFORMANCE/** — visão de performance (hoje sem trades, descreve o que vai alimentar as métricas).

## Fontes

- `docs/ARCHITECTURE.md`
- `docs/PRODUCT.md`
- `docs/ROADMAP.md`
- `docs/PIPELINE.md`
- `docs/decisions/0003-base-de-conhecimento-obsidian.md`
- `docs/audit/CURRENT_STATE.md` (em elaboração)
