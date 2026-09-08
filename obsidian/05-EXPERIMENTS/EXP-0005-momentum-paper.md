---
tags: [experimento, momentum, paper-trading, d10]
updated: 2026-09-08
status: aguardando-ativacao
---

# EXP-0005 — momentum v1 em carteira paper (D10)

> Experimento aberto em **2026-09-08** pela decisão delegada **D10** do Everton
> (`.claude/state/decisions-delegated-2026-09-07.md`). A linha paper do `momentum v1`
> nasce como **linha nova e congelada** com `purpose = paper`, ao lado da coorte
> `research_only` do [[EXP-0001-momentum-v1]] — assim o mesmo gatilho fica medido
> pelas barras (EXP-0001) e pela carteira (EXP-0005), e dá para comparar. A
> ativação é ato auditado (`infra/scripts/activate_strategy_version.py --paper-line`)
> e **continua sendo decisão do Everton**: sete condições em `docs/plans/M3.md`
> (D10) precisam ser cumpridas antes. A seção "Hipótese" e a seção "Protocolo"
> são escritas uma vez e **nunca** mudam; as avaliações são **acrescentadas**
> abaixo, datadas. Ver [[Experiments Index]], [[EXP-0001-momentum-v1]],
> [[Risk Engine]] e `docs/plans/M3.md` (D10).

## Hipótese (congelada)

Sobre as **mesmas entradas** do `momentum v1` já medidas pelo Shadow Lab em
[[EXP-0001-momentum-v1]] — mesmo gatilho, mesmos parâmetros, mesmo `code_ref` —,
a execução paper numa carteira real (perfil `paper_v1`, SPOT only, custos SPOT
declarados) produz uma diferença de `R_net` por sinal em relação ao `R_net`
hipotético do Shadow Lab que é **menor que 0,05 R** em mediana, e essa diferença
sobrevive a Holm a 5% sobre a família de contrastes entrada-a-entrada. Se a
diferença for maior, ela é explicável pela geometria da execução real (slippage,
reserva vencida, stop tocado intrabar, funding) e não por defeito do instrumento.

## Protocolo (congelado — nunca editar)

- **Strategy:** `strategies.key = momentum`; versão `v1` com `purpose = paper`
  (linha nova e congelada, ativada por `activate_strategy_version.py --paper-line`;
  a coorte `research_only` do [[EXP-0001-momentum-v1]] permanece viva ao lado,
  intocada).
- **code_ref:** `hunter_core.strategies.momentum_v1@sha256:…` — o mesmo módulo
  do [[EXP-0001-momentum-v1]]; o digest é o da árvore inteira após a normalização
  CRLF→LF (ver [[Open Bugs]], HIGH do `code_ref` não portátil).
- **params_hash / params_format:** `40e1688e…c41ac2f3` / `1` — idêntico ao
  EXP-0001 (`default_parameters` e `parameters_schema` bit a bit os mesmos).
- **Parameters (`default_parameters` congelados, nada implícito):**

```json
{
  "assumed_spread_bps": "2", "atr_bars": "97", "atr_pct_max": "0.05", "atr_pct_min": "0.003",
  "atr_period": "14", "atr_timeframe": "15m", "base_confidence": "0.5", "fee_bps": "4",
  "horizon_s": "14400", "lookback_closes": "20", "max_entry_delay_s": "120", "return_min": "0",
  "rvol_min": "1.5", "rvol_window": "96", "slippage_bps": "5", "stop_atr": "1.5",
  "target2_atr": "3", "target3_atr": "4.5", "target_atr": "1.5"
}
```

- **Carteira:** `portfolio_id = 01a07a1e-f6ae-7366-a7fe-ab3d9c83d488` (org `ever`,
  `type = paper`, `base_currency = USDT`, aberta em 2026-09-07 04:27:24Z com
  R$ 100.000 → 19.333,0111164813 USDT a 5,1725). Ver [[Portfolio]].
- **Risk Engine:** perfil `paper_v1` (contrato v2.2.1, `docs/RISK_ENGINE.md`).
  `evaluate` e `evaluate_exit` com `paper_v1`; kill switch durável com transição
  auditada; participação de 1 % do minuto medida no venue de execução (D2);
  execução no spot, decisão pelo perpétuo, basis registrado por fill (D1).
- **Spot only:** `MARKET_SPOT_ENABLED` e `ENABLE_PAPER_AUTONOMY` permanecem
  `false` até a ativação auditada; SPOT only, sem alavancagem, sem perpétuo na
  execução. A ponte sinal → admissão (T3.14) só cria o grupo de consumo quando
  `ENABLE_PAPER_AUTONOMY = true`, e só admite sinais com `purpose = paper`
  (T3.15b, `56d2dea`); `research_only` e `live` são recusados por nome.
- **Custos SPOT declarados (hipóteses, não tarifas verificadas):** spread total
  2 bps, slippage 5 bps por lado, taxa 4 bps por lado, funding assinado.
  `AssumedCosts(spread_bps=2, slippage_bps=5, fee_bps=4)` em `Decimal` —
  `float` é aceito pelo construtor ([[Open Bugs]]) mas não entra no `code_ref`.
- **Timeframe de decisão / de outcome:** 15 min (fechamentos distintos, UTC) /
  1 min — idêntico ao EXP-0001.
- **Entrada:** open da primeira barra de 1 min estritamente posterior a
  `decision_at`, com `entry_bar_open − source_bar_close ≤ 120 s`
  (`max_entry_delay_s`); senão `no_entry: late:*`. Geometria revalidada com
  `P_entry` (`stop < P_entry < target1`), senão `no_entry: geometry`. A entrada
  paper admite reserva viva e slippage real do livro spot; a entrada do Shadow
  Lab é hipotética.
- **Saída:** gap na abertura primeiro, depois toques intrabar; stop e alvo na
  mesma barra → **stop** (convenção pessimista); prioridade `stop > target >
  expired > invalidated`; horizonte **4 h** contado da entrada. A saída paper
  executa no livro spot; a do Shadow Lab é hipotética.
- **Métricas com denominador:** `R_net` por sinal (lucro líquido / risco);
  `taxa_alvo` = `target / (target + stop)`; `taxa_lucro` = `R_net > 0` /
  avaliáveis; `expectancy_R` = média de `R_net`; `profit_factor` = Σ R+ / |Σ R−|;
  `PnL_carteira` e `max_drawdown` **são aplicáveis** aqui (há carteira, ao
  contrário do Shadow Lab).
- **Limiar editorial:** abaixo de **100 outcomes avaliáveis E 30 dias distintos**,
  o campo `Result` só pode ser `inconclusivo`. Acima disso continua sendo
  pesquisa, nunca promessa.
- **Cohort:** `paper` (linha nova, `purpose = paper`; não `prospective`, não
  `replay`). A coorte `prospective` do [[EXP-0001-momentum-v1]] é **outra
  população** e não se soma nem se continua.
- **Universo elegível:** top 50 por volume 24 h do `market-worker`, com a
  composição do instante gravada no envelope de cada sinal; `tracking_hold`
  mantém a coleta de um mercado excluído enquanto houver acompanhamento aberto.
- **Markets:** Binance USDS-M, perpétuos USDT para a **decisão**, spot USDT para
  a **execução** (D1: spot executa, perpétuo decide). LONG apenas.
- **Isolamento:** todo sinal carrega `purpose = paper` e é admitido pela ponte
  (T3.14/T3.15b) quando `ENABLE_PAPER_AUTONOMY = true`. Nada é ordenado antes da
  ativação auditada e da decisão do Everton.
- **Data de início da coleta:** **a definir** — a linha paper nasce quando a
  migração `0010` (`6b837ac`) chegar à VPS no segundo deploy e o Everton ativar
  a versão com `--paper-line`. A data de início da coleta é o `activated_at` da
  linha `purpose = paper` em `strategy_versions`.

## Avaliações (acrescentadas, nunca reescritas)

### Avaliação de <próxima data>

<acrescente uma seção nova; não edite a anterior>

Nenhuma avaliação ainda. A coorte paper não existe no banco até a ativação
auditada pela decisão do Everton (D10, sete condições em `docs/plans/M3.md`).

## Relacionadas

[[Experiments Index]] · [[EXP-0001-momentum-v1]] · [[Risk Engine]] · [[Portfolio]] ·
[[Paper Trading]] · [[Execution Engine]] · [[Open Bugs]] ·
`docs/plans/M3.md` (D10, D1, D2) · `.claude/state/decisions-delegated-2026-09-07.md` ·
`docs/RISK_ENGINE.md` v2.2.1

## Fontes

`docs/plans/M3.md` (D10–D13) · `.claude/state/decisions-delegated-2026-09-07.md` ·
`packages/core/hunter_core/strategies/momentum_v1.py` ·
`infra/scripts/activate_strategy_version.py` ·
`docs/RISK_ENGINE.md` v2.2.1 (contrato) ·
`docs/decisions/0005-carteira-virtual-e-risk-engine-paper-v1.md` (ADR)
