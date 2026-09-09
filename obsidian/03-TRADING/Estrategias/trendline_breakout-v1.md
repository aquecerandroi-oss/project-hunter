---
tags: ["estrategia", "catalogo", "trendline_breakout"]
strategy: trendline_breakout
version: v1
purpose: research_only
status: active
code_ref: "hunter_core.strategies.trendline_breakout_v1@sha256:7b83a1ff07946fa743d12c9d098f15b538c2e2b19f5269363203ee0671e19648"
params_hash: f2e8017c7251e22f
activated_at: "2026-09-08T22:29:52.701952+00:00"
deprecated_at: ""
derived_from: ""
cohorts: ["replay:d78c14d1-b4c5-424a-8f31-a43100744bb4", "prospective"]
exp: ["[[EXP-0016-trendline-breakout]]"]
updated: 2026-09-08
---
# trendline_breakout v1 (research_only, active)

<!-- generated:start -->
## Parâmetros

**36 chaves em `default_parameters`** (o brief T3.34b escreveu "37"; é erro de contagem, não de
código — `len(default_parameters) == 36`, confirmado pelo `--dry-run` na VPS). A tabela completa
vive em `.claude/state/brief-T3.34b-trendline-breakout-strategy.md` §5 e não é reproduzida aqui na
íntegra — abaixo, só os valores citados explicitamente no corpo do [[EXP-0016-trendline-breakout]]:

| Parâmetro | Valor | Descrição |
|---|---|---|
| `target_r` | `2,0` | convenção (múltiplo do risco para o alvo informativo) |
| `atr_pct_min` | `0,005` | piso herdado de `breakout_v1` ([[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]]) |
| `stop_atr_max` | `2,0` | teto de distância do stop, em ATR |
| `max_risk_atr` | `3,0` | teto de risco admitido, em ATR |
| `max_violations_breakout` | `1` | corrigido do brief (que pedia `0`, impossível: a barra que rompe é, ela própria, uma violação); prova por teste (`test_max_violations_zero_would_refuse_every_breakout_there_is`) |
| `retire_after_break` | ligado | única regra que a cópia acrescenta à geometria da T3.34 (correção 1 da [[KB-0077-linhas-de-tendencia]]) |

Os 18 parâmetros de geometria restantes (`pivot_k`, `min_swing_atr`, `tolerance_atr`, `break_atr`,
`bounce_atr`, `retest_bars`, `bounce_bars`, `max_anchors`, `max_lines`, `parallel_tol`, dois baldes
de deduplicação, mais `mode`, os dois `max_violations_*` e os seis parâmetros de varredura que
viajam no envelope `pattern_params`) vêm da T3.34 sem medição — congelados **antes** de qualquer
replay, para desenhar figuras, não para render expectancy (ver o portão C2 em
[[EXP-0016-trendline-breakout]]).

**Regra de entrada, elegibilidade e geometria completas:** ver o Protocolo (congelado) de
[[EXP-0016-trendline-breakout]] — não duplicado aqui.

## Origem

**Changelog:** família nova no catálogo de referência (`infra/scripts/seed_reference.py`), digest
`sha256:7b83a1ff…` — os digests das versões vivas não se moveram (`momentum_v1 …ab2e0398…`,
`volume_anomaly_v1 …9b8c14ab…`, `session_orb_v1 …a4d514ad…`). Ativada em
**2026-09-08T22:29:52,701952Z** (19:29:52 Brasília), `params_hash = f2e8017c7251e22f`, 36
parâmetros — o digest previsto pelo protocolo, conferido no `--dry-run` antes da escrita.

## Coortes e sinais

| Coorte | Sinais (`agent_signals`) |
|---|---|
| `replay:d78c14d1-b4c5-424a-8f31-a43100744bb4` | 47 (`EXP-0016`, replay de 31 d × 4 mercados, 11 904 barras, 0 erros) |
| `prospective` | aberta em 2026-09-08T22:29:52Z; contagem exata não relida nesta sessão |

## Avaliações

As avaliações datadas ficam na página de experimento, nunca duplicadas aqui:

- [[EXP-0016-trendline-breakout]] — avaliação de dia um (T3.34c, **REPLAY**): **manter em pesquisa,
  hipótese REENUNCIADA**. No dado real esta versão não é "rompimento de linha de tendência": é
  **repique em suporte ascendente** (89,4 % das decisões; regra dos 60 % dispara), com uma porta de
  rompimento que decidiu 5 vezes em 31 dias e perdeu as 5. `inconclusivo` por régua de maturidade
  (47 avaliáveis < 100; 14 dias < 30).

## Replicação

não iniciada — ver `docs/plans/REPLICATION.md` quando existir (T3.19).

## Ligações

- Família: [[trendline_breakout]]
- Experimento: [[EXP-0016-trendline-breakout]]
- Conhecimento: [[KB-0077-linhas-de-tendencia]] · [[KB-0003-rompimento-de-canal-e-data-snooping]] ·
  [[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]]
<!-- generated:end -->


## Notas

Página criada à mão pela Sexta-feira em 2026-09-08 a partir de [[EXP-0016-trendline-breakout]] — o
host local não alcança o Postgres da VPS (`export_strategies_to_obsidian.py --dry-run` falhou com
`ConnectionRefusedError`). A tabela de parâmetros acima é **parcial por desenho**: só reproduz os
valores citados no corpo do EXP; os 36 valores completos exigem ler `default_parameters` do banco
(ou o brief T3.34b §5, fora do vault).
