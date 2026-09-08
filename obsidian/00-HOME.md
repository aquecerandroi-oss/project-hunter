---
tags: [home, hunter, indice]
updated: 2026-09-08
status: vivo
owner: sexta-feira
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
[[EXP-0003-baselines-v1]].

**Em andamento: M3 — e desde a madrugada de 2026-09-07 a carteira do Everton existe de verdade.**
Às **04:27:24Z** a carteira paper permanente foi aberta na VPS: **R$ 100.000 → 19.333,0111164813
USDT à taxa 5,1725**, com a observação de câmbio que a converteu gravada e **imutável**
(`portfolio_id 01a07a1e-f6ae-7366-a7fe-ab3d9c83d488`; ver [[Portfolio]]). Junto vieram o schema da
carteira (`0006`, aplicada na VPS), o ledger, o simulador de execução paper, o kill switch
**durável** com transição auditada, o serviço de admissão único, o coletor de câmbio no ar e a tela
`/[org]/portfolio`. **Atualizado na manhã de 2026-09-07: a carteira ganhou quem a faça andar.** O `execution-worker`
(T3.5, `7ecafd2`, com as correções do guardião em `12edda3`) **existe e foi provado** — 30 minutos no
stack local, saída 0, com fill, stop tocado, saída degradada sem fill inventado, patrimônio
19.903,708205 idêntico no heartbeat e na curva, custos contados uma vez só, 0 exceções. Junto vieram
a `0008` (a API perde a escrita em `orders`/`fills`/`positions`/`trades`, e a carteira nasce
auditada), a `0009` (o pedido carrega a própria geometria; o pó vira coluna), o heartbeat do worker
em `/system` e a **ponte sinal → admissão desligada** (T3.14).

**A carteira continua parada, e isso é de propósito.** A ponte tem **duas travas independentes**:
`ENABLE_PAPER_AUTONOMY=false` (com ela falsa a ponte nem cria o grupo de consumo) e, mesmo se ligada,
**todo sinal do Shadow Lab hoje é `research_only`** — propósito que a ponte recusa. Nada é admitido
até existir uma `strategy_version` ativada com propósito de paper. **Em 2026-09-07 o Everton delegou
essa escolha** ("sexta feira pode decider esses 4"): a decisão **D10** escolheu o `momentum`, como
linha nova e congelada, com a coorte `research_only` intocada ao lado — e descobriu, no caminho, que
**o rótulo `paper` não existe no código** (o worker só escreve `research_only`, a ponte só aceita
`live`, e `strategy_versions` não tem coluna `purpose`), o que virou a **T3.15**. **Nada foi
ativado**: a ativação depende de sete condições escritas e continua sendo ato manual, auditado e
anunciado. Ver [[Portfolio]] e `.claude/state/decisions-delegated-2026-09-07.md` (D10–D13: versão
paper, alvo do p99, histerese do piso spot, domínio). Nenhum `ENABLE_*` de autonomia está ligado e o M3 **não** declara modo autônomo. Falta
**T3.5c, T3.0c/T3.0d, T3.9b, T3.10 e o deploy na VPS** — que roda a era do `2688ef1` e ainda não tem
nada disto no ar.

Na madrugada os 4 shards do coletor foram implantados na VPS e **a cobertura do tape voltou a
andar**; de manhã o portão foi provado: às **06:28:46Z**, **42 minutos contínuos** de cobertura
avançando com 1,1 s de atraso e zero descartes — **a condição nº 1 de aprovação do M2 está
satisfeita** (`e5e57d1`). Ver `docs/audit/CURRENT_STATE.md` para o levantamento linha a linha e o
[[Changelog]] para o dia a dia.

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
| Market Collector | implementado — 200 mercados em **4 shards na VPS** desde 2026-09-07 04:33Z, heartbeat por shard (`9ceb389`), cobertura do tape a 0,7 s do relógio, chave compartilhada extinta | [[Market Collector]] | M1 |
| Exchange Adapters (Binance USDS-M) | implementado; Bybit continua planejado (M1b) | [[Exchange Adapters]] | M1 |
| WebSockets de mercado | implementado | [[WebSockets]] | M1 |
| Feature Engine | implementado — 28 calculadoras, 108.688 snapshots na VPS; **12 de 27 features com baseline utilizável** | [[Features]] | M2 |
| Anomaly Engine | implementado — 10 detectores (8 armados); **1 disparou** até agora (`VOLUME_SPIKE`) | [[Anomalies]] | M2 |
| Regime v0 + Opportunity Score + Radar | implementado; **regime `UNKNOWN` em 100 %** das leituras e estágio nunca publicado — M2 **não aprovado** (`docs/reports/M2.md`) | [[Features]], [[Anomalies]] | M2 |
| Paper Trading / Execution Engine | **`execution-worker` implementado e provado** (`7ecafd2`, `12edda3`) — ciclo de admissão, ordem, proteção, MTM antes do kill switch e recuperação; 30 min de prova com saída 0. **Não está na VPS**, e não sobe lá antes da T3.9 | [[Paper Trading]], [[Execution Engine]] | M3 |
| Portfolio (carteira permanente em USDT com âncora em BRL) | **aberta em produção em 2026-09-07 04:27Z** — R$ 100.000 → 19.333,0111164813 USDT a 5,1725, âncora imutável, 0 posições. O pó (resíduo de taxa em ativo base) tem coluna própria e **não é posição**; falta o assentamento | [[Portfolio]] | M3 |
| Risk Engine (contrato **v2.2.1**, perfil `paper_v1`) | **completo e em execução:** núcleo, schema (`0006`→`0009`), ledger, kill switch durável publicando `kill_switch.changed`, admissão e o worker que chama `evaluate`. Falta T3.5c, T3.0c/T3.0d, T3.9b, T3.10 e o deploy | [[Risk Engine]] | **M3** (era M4; ADR 0005) |
| Ponte sinal → admissão (T3.14) | **implementada e desligada** (`12edda3`) — `ENABLE_PAPER_AUTONOMY=false` **e** todo sinal do Lab é `research_only`; nada é admitido até uma versão com propósito paper ser ativada, e isso é decisão do Everton | [[Risk Engine]], [[Strategies]] | M3 |
| Câmbio USDTBRL (coletor T3.11a) | **implementado e no ar na VPS** (`09eb6de`) — uma observação por minuto no shard 0, idempotente | [[Portfolio]] | M3 |
| Adaptador SPOT da Binance (T3.0a/T3.0b) | adaptador (`078d6ef`) e **`market_type` em toda identidade fora do banco** (`cefad8c`, com as chaves do perpétuo byte por byte inalteradas); **a ingestão spot (T3.0c) está em voo**, e a T3.0d tem um item bloqueante: o `event_id` do candle não inclui o tipo | [[Exchange Adapters]] | M3 |
| β contra o BTC (`beta_v1`, com validade) | implementado como pacote puro (`da2fb49`); `market_betas` **existe no banco e está vazia** (0 linhas na VPS) | [[Risk Engine]] | M3 |
| Estratégias / Agentes + ponte sinal → proposta | planejado | [[Strategies]], [[Agents Overview]] | M4 |
| Analytics / Performance | planejado | [[Performance Overview]] | M5 |

## Vistas e mapas

Duas **Bases** nativas do Obsidian (arquivos `.base`, tabela dinâmica lida do frontmatter — elas não
calculam nada, só mostram e ordenam o que as páginas já declaram) e dois **canvases**:

| Vista | O que mostra |
|---|---|
| [[Experimentos.base]] | um experimento por linha: `EXP`, estratégia, versão, resultado, avaliáveis e dias contra o limiar editorial de **100 E 30**, última avaliação. Tem uma view "Abaixo do limiar editorial" e cartões. |
| [[Estratégias.base]] | uma versão de estratégia por linha: versão, propósito, status, o EXP onde mora o veredito, de qual versão foi replicada, coortes, `activated_at`. Views "Ativas" e "Linha paper". |
| [[Fluxo sinal → carteira.canvas]] | o caminho completo `market-worker → scanner → strategy-worker (Lab) → ponte → admissão → execution-worker → carteira`, cada caixa ligada à página do módulo, com as **duas travas** desenhadas onde elas estão. |
| [[Família momentum.canvas]] | a linhagem do `momentum`: `v1` depreciada → `v2` em pesquisa → `v3` paper (não ativada), com os EXP que medem cada uma. |

As convenções da base — frontmatter obrigatório por pasta, os quatro callouts, o linter — estão em
`docs/OBSIDIAN.md`. O linter roda com `uv run python infra/scripts/obsidian_lint.py`.

## Como navegar

- [[Mente da Sexta-feira]] — como a assistente pensa (Claude + Astra) e onde cada tipo de memória fica; [[Dialogos/Index|diálogos]] e [[Revisoes-Astra/Index|revisões da Astra]]. Mais recente: [[Dialogos/M3]] — carteira virtual e Risk Engine, a partir da diretiva do Everton de 2026-09-06 (ADR 0005; plano `docs/plans/M3.md`; contrato `docs/RISK_ENGINE.md` v2). O M3 **não** declara modo autônomo: as entradas são manuais e a ponte sinal → proposta é do M4.

- **00-INBOX/** — pendências **operacionais** datadas: uma escrita em produção, um ajuste de
  ferramenta ou uma correção que espera decisão. Não é bug (isso é `07-BUGS/`) nem decisão de
  arquitetura (isso é `06-DECISIONS/`); é o que está pendurado, com a correção proposta e quem
  decide. Sai da pasta quando for aplicada ou descartada, com a data e o motivo. Hoje:
  [[2026-09-08-linhagem-de-momentum-v4-no-changelog-da-vps|a linhagem de `momentum v4` perdida no `changelog` da VPS]].
- **01-ARCHITECTURE/** — visão de sistema, fluxo de dados, infraestrutura, workers.
- **02-MARKET/** — coleta de mercado, adapters de exchange, WebSockets, features, anomalias — **tudo implementado e rodando** (M1 aprovado; M2 entregue e não aprovado, ver [[Features]] e [[Anomalies]] para os números de produção e as limitações medidas).
- **03-TRADING/** — paper trading, risk engine, execução, portfolio, estratégias. **Deixou de ser
  "planejado" em 2026-09-07:** [[Portfolio]] traz a carteira real aberta na VPS com os números
  medidos, e [[Risk Engine]] traz o que existe peça a peça e o que falta — hoje **T3.5c, T3.0c/T3.0d,
  T3.9b, T3.10 e o deploy**, depois que o `execution-worker` passou a existir e ser provado.
  Estratégias e agentes continuam M4.
- **04-AGENTS/** — visão geral de agentes e as quatro estratégias do MVP (planejado M4).
- **05-EXPERIMENTS/** — índice de experimentos ([[Experiments Index]], `EXP-NNNN`), template e os quatro experimentos abertos: [[EXP-0001-momentum-v1]] e [[EXP-0002-volume-anomaly-v1]] (coortes prospectivas do Shadow Lab desde 2026-09-06), [[EXP-0004-politicas-de-saida]] (replay de oito políticas de saída sobre as entradas já congeladas, `2c6bb2d` — pesquisa que não escreve nada) e [[EXP-0003-baselines-v1]] (2026-09-07, o **instrumento** de baselines do M2: quanto do arquivo amadurece, e o que isso destrava rio abaixo). Todos com avaliações **datadas e acrescentadas** e o SQL que produziu cada número. Desde
  2026-09-08 são **seis**: [[EXP-0005-momentum-paper]] (a linha `purpose = paper` do `momentum`, D10)
  e [[EXP-0006-momentum-piso-de-custo]] (`momentum v4` — a primeira **variante de parâmetro** do Lab,
  mesmo `code_ref` do pai; o replay de abertura é `inconclusivo` e mostra que **o piso corta 86% das
  decisões**).
- **06-DECISIONS/** — índice legível das ADRs.
- **07-BUGS/** — bugs abertos e resolvidos, com hash de commit.
- **08-CHANGELOG/** — uma entrada por commit, agrupado por dia.
- **09-OPERATIONS/** — deploy, variáveis de ambiente, monitoramento e o **Diário** (`09-OPERATIONS/Diario/AAAA-MM-DD.md`, uma nota por dia de trabalho: o que foi feito, o que foi decidido, o que ficou em voo) — [[Diario/2026-09-08|2026-09-08]] · [[Diario/2026-09-07|2026-09-07]] · [[Diario/2026-09-06|2026-09-06]] · [[Diario/2026-09-05|2026-09-05]].
- **10-PERFORMANCE/** — visão de performance (hoje sem trades, descreve o que vai alimentar as métricas).
- **11-KNOWLEDGE/** — conhecimento **externo** curado pela Sexta-feira com revisão da Astra: estratégias, análise técnica, microestrutura, perpétuos, risco, estatística de backtest. Cada nota traz fonte, qualidade da evidência e uma hipótese testável no Lab; as candidatas ficam em [[Strategy Backlog]] e só viram experimento pelo caminho normal (nada é ativado sozinho). Índice: [[11-KNOWLEDGE/Index|Conhecimento]].

## Fontes

- `docs/ARCHITECTURE.md`
- `docs/PRODUCT.md`
- `docs/ROADMAP.md`
- `docs/PIPELINE.md`
- `docs/decisions/0003-base-de-conhecimento-obsidian.md`
- `docs/audit/CURRENT_STATE.md` (em elaboração)
