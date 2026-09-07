---
tags: [home, hunter, indice]
updated: 2026-09-07
---

# PROJECT HUNTER — Base de Conhecimento

PROJECT HUNTER é uma plataforma SaaS de inteligência quantitativa para criptomoedas: encontra situações de **assimetria + anomalia + contexto + liquidez + controle de risco**, explica o porquê de cada sinal e prova a tese em paper/shadow antes de qualquer dinheiro real. Nenhum agente executa ordens — todo caminho de entrada é AGENTE → PROPOSTA → RISK ENGINE → EXECUÇÃO.

Esta pasta (`obsidian/`) é a base de conhecimento **do projeto**, viva e versionada no git, separada do `vault/` pessoal do Sexta-feira (memória do agente, só por MCP) e de `docs/` (especificação normativa: arquitetura, ADRs, planos, relatórios de milestone). As páginas aqui resumem e linkam para `docs/` em vez de duplicar. Ver [[Architecture Decisions]] → ADR 0003 para a decisão de criar esta estrutura.

## Onde estamos agora

**Atualizado em 2026-09-07.** M0 (fundação: monorepo, auth Clerk, organizações/workspaces,
dashboard, schema de 54 tabelas com RLS, Docker, CI) e **M1 fechados e aprovados**
(`docs/reports/M0.md`, `docs/reports/M1.md`). Hoje, **rodando 24 h por dia na VPS**: o
`market-worker` coletando 200 mercados da Binance, o `scanner-worker` (M2) construindo baselines e
avaliando features/anomalias/regime, e o `strategy-worker` com o **Shadow Lab** — estratégias que
registram "eu entraria aqui" e medem o que teria acontecido, **sem carteira, sem ordem, sem um
centavo**.

**O M2 está entregue em código e NÃO foi aprovado** (`docs/reports/M2.md`, parecer da Sexta-feira em
2026-09-07). O Radar tem linhas reais pela primeira vez — mas **10 de 200 mercados**, score máximo
**11,92**, **estágio nunca publicado** (0 em 299 amostras), **regime `UNKNOWN` em 100 %** das
leituras, **1 de 10** detectores de anomalia disparando e p99 tick→oportunidade em **0,3 %** de
cumprimento. Com 3 de 9 componentes disponíveis, o teto aritmético de score hoje é **25,00 de 100**
contra a linha de 40 do WATCHING: nenhum mercado pode ser HOT. O motor está certo — ele diz o motivo
de cada ausência em vez de inventar número; o que falta é, na maior parte, **tempo de coleta**. As
quatro condições objetivas de aprovação estão no VEREDITO do relatório, e a medição está em
[[EXP-0003-baselines-v1]]. Em andamento: **M3** (carteira virtual e Risk Engine — o núcleo puro do
motor de risco existe e está testado, e a carteira, o ledger e o simulador de execução paper estão
em voo). Nada de execução real existe, e nenhum `ENABLE_*` de autonomia está ligado. Ver
`docs/audit/CURRENT_STATE.md` para o levantamento linha a linha e o [[Changelog]] para o dia a dia.

## O pipeline (visão completa; M1 e M2 existem e rodam)

```
Binance/Bybit WS  ──▶  [market-worker]      Market Data          (M1, no ar 24 h)
                             │
                             ▼
                       [scanner-worker]      Features → Anomalias
                                             → Regime → Opportunity  (M2, no ar; não aprovado)
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
| Workers (papéis reais) | implementado — `market`, `scanner`, `strategy` no ar 24 h | [[Workers]] | M1+ |
| Market Collector | implementado — 200 mercados, 4 shards com heartbeat por shard (`9ceb389`); na VPS ainda 1 shard | [[Market Collector]] | M1 |
| Exchange Adapters (Binance USDS-M) | implementado; Bybit continua planejado (M1b) | [[Exchange Adapters]] | M1 |
| WebSockets de mercado | implementado | [[WebSockets]] | M1 |
| Feature Engine | implementado — 28 calculadoras, 108.688 snapshots na VPS; **12 de 27 features com baseline utilizável** | [[Features]] | M2 |
| Anomaly Engine | implementado — 10 detectores (8 armados); **1 disparou** até agora (`VOLUME_SPIKE`) | [[Anomalies]] | M2 |
| Regime v0 + Opportunity Score + Radar | implementado; **regime `UNKNOWN` em 100 %** das leituras e estágio nunca publicado — M2 **não aprovado** (`docs/reports/M2.md`) | [[Features]], [[Anomalies]] | M2 |
| Paper Trading / Execution Engine | planejado | [[Paper Trading]], [[Execution Engine]] | M3 |
| Portfolio (carteira permanente em USDT com âncora em BRL) | planejado | [[Portfolio]] | M3 |
| Risk Engine (contrato v2.1, perfil `paper_v1`) | **núcleo puro implementado** (`packages/risk-core`, 204 testes, `bf4924b` → `5f86028`); nada integrado | [[Risk Engine]] | **M3** (era M4; ADR 0005) |
| β contra o BTC (`beta_v1`, com validade) | implementado como pacote puro (`da2fb49`), sem tabela | [[Risk Engine]] | M3 |
| Estratégias / Agentes + ponte sinal → proposta | planejado | [[Strategies]], [[Agents Overview]] | M4 |
| Analytics / Performance | planejado | [[Performance Overview]] | M5 |

## Como navegar

- [[Mente da Sexta-feira]] — como a assistente pensa (Claude + Astra) e onde cada tipo de memória fica; [[Dialogos/Index|diálogos]] e [[Revisoes-Astra/Index|revisões da Astra]]. Mais recente: [[Dialogos/M3]] — carteira virtual e Risk Engine, a partir da diretiva do Everton de 2026-09-06 (ADR 0005; plano `docs/plans/M3.md`; contrato `docs/RISK_ENGINE.md` v2). O M3 **não** declara modo autônomo: as entradas são manuais e a ponte sinal → proposta é do M4.

- **01-ARCHITECTURE/** — visão de sistema, fluxo de dados, infraestrutura, workers.
- **02-MARKET/** — coleta de mercado, adapters de exchange, WebSockets, features, anomalias — **tudo implementado e rodando** (M1 aprovado; M2 entregue e não aprovado, ver [[Features]] e [[Anomalies]] para os números de produção e as limitações medidas).
- **03-TRADING/** — paper trading, risk engine, execução, portfolio, estratégias (tudo planejado M3–M4).
- **04-AGENTS/** — visão geral de agentes e as quatro estratégias do MVP (planejado M4).
- **05-EXPERIMENTS/** — índice de experimentos ([[Experiments Index]], `EXP-NNNN`), template e os quatro experimentos abertos: [[EXP-0001-momentum-v1]] e [[EXP-0002-volume-anomaly-v1]] (coortes prospectivas do Shadow Lab desde 2026-09-06), [[EXP-0004-politicas-de-saida]] (replay de oito políticas de saída sobre as entradas já congeladas, `2c6bb2d` — pesquisa que não escreve nada) e [[EXP-0003-baselines-v1]] (2026-09-07, o **instrumento** de baselines do M2: quanto do arquivo amadurece, e o que isso destrava rio abaixo). Todos com avaliações **datadas e acrescentadas** e o SQL que produziu cada número.
- **06-DECISIONS/** — índice legível das ADRs.
- **07-BUGS/** — bugs abertos e resolvidos, com hash de commit.
- **08-CHANGELOG/** — uma entrada por commit, agrupado por dia.
- **09-OPERATIONS/** — deploy, variáveis de ambiente, monitoramento e o **Diário** (`09-OPERATIONS/Diario/AAAA-MM-DD.md`, uma nota por dia de trabalho: o que foi feito, o que foi decidido, o que ficou em voo) — mais recente: [[2026-09-07]].
- **10-PERFORMANCE/** — visão de performance (hoje sem trades, descreve o que vai alimentar as métricas).
- **11-KNOWLEDGE/** — conhecimento **externo** curado pela Sexta-feira com revisão da Astra: estratégias, análise técnica, microestrutura, perpétuos, risco, estatística de backtest. Cada nota traz fonte, qualidade da evidência e uma hipótese testável no Lab; as candidatas ficam em [[Strategy Backlog]] e só viram experimento pelo caminho normal (nada é ativado sozinho). Índice: [[11-KNOWLEDGE/Index|Conhecimento]].

## Fontes

- `docs/ARCHITECTURE.md`
- `docs/PRODUCT.md`
- `docs/ROADMAP.md`
- `docs/PIPELINE.md`
- `docs/decisions/0003-base-de-conhecimento-obsidian.md`
- `docs/audit/CURRENT_STATE.md` (em elaboração)
