# Contrato — API `/api/v1/lab/shadow/*` (S3a)

Fixado antes da implementação (brief `.claude/state/brief-S3-lab-api.md`). Exemplos de JSON
abaixo vêm de consultas SQL reais contra o Postgres local (`docker-postgres-1`, dados produzidos
pelo `strategy-worker` em 2026-09-06), não de dado inventado; os números finais no relatório vêm
do endpoint de verdade, não desta prévia manual.

## Restrição de dado descoberta ao desenhar o contrato

`Evaluation.state` (`packages/core/hunter_core/strategies/base.py`) só existe **em memória** do
`strategy-worker` — vira métrica Prometheus (`health.record`) e nunca uma linha durável. Só o
resultado `TRIGGERED` persiste, como `agent_signals` — e nem todo `TRIGGERED` vira sinal: um
episódio desarmado ou já acompanhando uma entrada absorve a decisão sem emitir nada
(`episodes.py`, achado da Astra na revisão do contrato). Logo:

- Não existe `decisions` (nem por `Evaluation.state`, nem por `TRIGGERED`) — vem `null` com
  `reason: "evaluation_state_not_persisted"` em vez de reaproveitar `signals_emitted` como se
  fosse a mesma coisa. `signals_emitted = count(agent_signals)` é reportado à parte, como o que
  ele é: sinais persistidos, não avaliações.
- `coverage.unavailable` foi **removido**: `censored.by_reason.gap:*` conta gaps que
  interromperam um **acompanhamento já aberto** (depois de um sinal existir), não avaliações que
  nunca chegaram a gerar sinal por causa de um gap — chamar isso de "cobertura do universo" seria
  enganoso (Astra, must-fix 1). `warmup`/`ineligible` não têm fonte durável nenhuma. `coverage`
  guarda só o que é honesto de afirmar: mercados e dias **com sinal** (`markets_with_signals`,
  não "avaliados") e os custos assumidos.

Astra revisou o contrato (`.claude/state/astra-review-S3-lab-api-contract.md`) com dois must-fix
adicionais, reconciliados abaixo antes da implementação:

1. **Confusão avaliação/outcome** (acima) — corrigida.
2. **`as_of` e maturação de horizonte não aplicados à população financeira.** Um sinal recente
   pode fechar `stop` rápido enquanto um par emitido no mesmo minuto ainda não chegou aos 4 h do
   horizonte de `expired` — contar só os `terminal` de uma janela recente super-representa saídas
   rápidas. Toda métrica financeira (`target_rate`, `net_profit_rate`, `expectancy`, `PF`,
   `sum_of_hypothetical_r`, bloco `r_ex_funding`) agora exige, além de `tracking_state='terminal'`,
   que o horizonte tenha **maturado até `as_of`**: `meta.entry_plan.entry_bar_open + meta.horizon_s
   <= as_of` (ambos duráveis em `signal_outcomes.meta`, sempre presentes), e `exit_ts <= as_of`
   como cinto de segurança contra vazamento de futuro quando `as_of` é passado. **Declarado
   também:** isto não é uma fotografia histórica — o `tracking_state`/`result`/`r_multiple` lidos
   são os **atuais** do banco, só a *seleção* de quais sinais entram é que respeita `as_of`; uma
   consulta com `as_of` no passado reflete o que se sabe **hoje** sobre decisões daquele período,
   não o que se sabia então.

## Convenções gerais

- Toda métrica derivada (taxas, expectancy, PF, soma de R) é `Decimal` quantizado a 4 casas
  (`ROUND_HALF_UP`), nunca `float`.
- Nulo sempre vem com um campo-irmão `..._reason` (padrão já usado em `signal_outcomes.meta.r_net_reason`).
- `as_of` é UTC, aparece em toda resposta de `summary`.
- `label` fixo: `"SOMBRA — hipotético, sem capital, custos assumidos"`.
- Autorização: `PrincipalSession` (qualquer usuário autenticado, sem organização — pesquisa é
  global). Sem organização = sem RLS a configurar; `agent_signals`/`signal_outcomes`/
  `strategy_versions`/`shadow_episodes` não têm `organization_id` (DATABASE.md §16).
- Postgres fora → `503` problem+json (`type` termina em `lab-unavailable`), nunca 500 genérico.
- Lista vazia é `200 {"items": [], "next_cursor": null}` (ou `"versions": []` no summary), nunca 404.

## `GET /api/v1/lab/shadow/versions`

Sem query params (catálogo completo; é pequeno — 10 linhas hoje). Cada item:

```json
{
  "strategy_version_id": "098b060c-cdc0-46a6-b88b-70d4a5472b97",
  "strategy_key": "momentum",
  "version": "v2",
  "status": "active",
  "code_ref": "hunter_core.strategies.momentum_v1@sha256:c012f75c...",
  "activated_at": "2026-09-06T02:08:13.332014Z",
  "deprecated_at": null,
  "superseded_by": null,
  "params_hash": "<sha do params_hash>",
  "default_parameters": {"fee_bps": "4", "assumed_spread_bps": "2", "slippage_bps": "5",
                          "max_entry_delay_s": "120", "...": "..."}
}
```

Para a linha `momentum v1` (deprecated): `"superseded_by": "098b060c-...-v2-id"`. **Limitação
declarada:** não existe coluna `superseded_by`; `infra/scripts/activate_strategy_version.py`
grava a relação só como texto livre no `changelog` da linha antiga
(`"superseded by v2 (code_ref ...)"`) e em `system_events`. O repositório extrai a versão sucessora
com uma regex (`^superseded by (\S+)`) e resolve o id via `(strategy_id, version)`; sem esse padrão
(depreciação comum, sem `--supersede`) o campo é `null`. Anotado como pendência para
`database-architect` — uma coluna durável seria mais robusta que regredir texto de changelog.

## `GET /api/v1/lab/shadow/summary?window=7d|30d|all&as_of=&cohort=prospective`

`window` (default `30d`) e `as_of` (default: agora) definem `[as_of - window, as_of]` sobre
`decision_at` (extraído de `agent_signals.supporting_features->>'decision_at'` — não há coluna
própria; `emitted_at` é o timestamp de insert e não o mesmo instante semântico). `cohort` (default
`prospective`) filtra por `agent_signals.supporting_features->>'cohort'`.

Exemplo real (SQL manual contra `docker-postgres-1`, `momentum`/`v2`, `window=all`):

```json
{
  "as_of": "2026-09-06T12:00:00Z",
  "window": "all",
  "cohort": "prospective",
  "label": "SOMBRA — hipotético, sem capital, custos assumidos",
  "versions": [
    {
      "strategy_version_id": "098b060c-cdc0-46a6-b88b-70d4a5472b97",
      "strategy_key": "momentum",
      "version": "v2",
      "code_ref": "hunter_core.strategies.momentum_v1@sha256:c012f75c...",
      "status": "active",
      "activated_at": "2026-09-06T02:08:13.332014Z",
      "deprecated_at": null,
      "counts": {
        "decisions": null,
        "decisions_reason": "evaluation_state_not_persisted",
        "signals_emitted": 18,
        "pending_entry": 4,
        "entered": 11,
        "no_entry": {"total": 3, "by_reason": {"late:delay": 3, "late:missed_open": 0, "late:unconfirmed": 0, "geometry": 0}},
        "active": 2,
        "terminal": {"total": 9, "by_result": {"target": 2, "stop": 2, "expired": 0, "invalidated": 5}},
        "censored": {"total": 0, "by_reason": {}},
        "funding_not_settleable": 0
      },
      "metrics": {
        "target_rate_among_resolved_touches": {"value": "0.5000", "reason": null},
        "net_profit_rate": {"value": "0.2222", "reason": null},
        "hypothetical_net_expectancy_r": {"value": "-0.4362", "reason": null},
        "profit_factor": {"value": "0.2461", "reason": null, "sum_positive": "1.2809",
                           "sum_negative_abs": "5.2068", "sample_size": 9},
        "sum_of_hypothetical_r": {"value": "-3.9258", "reason": null, "count": 9, "ordered_by": "exit_ts"}
      },
      "r_ex_funding": {
        "net_profit_rate": {"value": "0.2222", "reason": null},
        "hypothetical_net_expectancy_r": {"value": "-0.4361", "reason": null},
        "profit_factor": {"value": "0.2462", "reason": null, "sum_positive": "1.2816",
                           "sum_negative_abs": "5.2059", "sample_size": 9},
        "sum_of_hypothetical_r": {"value": "-3.9251", "reason": null, "count": 9},
        "coverage": {"evaluable_outcomes": 9, "r_net_evaluable_outcomes": 9}
      },
      "portfolio_pnl": null,
      "portfolio_pnl_reason": "not_applicable",
      "portfolio_max_drawdown": null,
      "portfolio_max_drawdown_reason": "not_applicable",
      "maturity": {"evaluable_outcomes": 9, "distinct_days": 1, "inconclusive": true},
      "coverage": {
        "markets_with_signals": 18,
        "distinct_days": 1,
        "note": "counts markets/days that produced at least one signal — evaluations that never triggered are not observable (see 'Restrição de dado')",
        "assumed_costs": {"assumed_spread_bps": "2", "slippage_bps": "5", "fee_bps": "4",
                           "max_entry_delay_s": 120}
      }
    }
  ]
}
```

Notas de cálculo (SHADOW-LAB.md §9, decisão conjunta, reconciliadas com a revisão da Astra):
- `entered` = `entry_ts IS NOT NULL` (inclui trackings depois censuradas enquanto ativas — "entrou"
  é fato passado, independente do fim). Não passa pelo portão de maturação abaixo — é contagem
  operacional, não financeira.
- **população avaliável** (financeira: `target_rate`, `net_profit_rate`, `expectancy`, `PF`,
  `sum_of_hypothetical_r`, bloco `r_ex_funding`) = `tracking_state='terminal'` **E** horizonte
  maturado até `as_of` (`meta.entry_plan.entry_bar_open + meta.horizon_s <= as_of`) **E**
  `exit_ts <= as_of`. Dentro dela, `net_profit_rate`/`expectancy`/PF/soma usam `r_multiple IS NOT
  NULL`; funding não apurável (`r_multiple NULL` com amostra madura) conta em
  `funding_not_settleable`, não em "indisponível" (uma liquidação zero comprovada também produz
  `r_multiple` válido — `settle.py`).
- `r_ex_funding.*` usa a mesma população madura, mas com `meta.r_ex_funding` no lugar de
  `r_multiple` (nunca é `NULL` quando houve entrada, porque não depende de funding) — cobertura
  maior ou igual à de `r_net`; `coverage.r_net_evaluable_outcomes` é o subconjunto que também tem
  `r_multiple`.
- `profit_factor` carrega `sum_positive`/`sum_negative_abs`/`sample_size` sempre (mesmo quando
  `value` é nulo, exceto `no_sample` onde as somas são `"0"`); nulo com `reason: "no_losses"`
  quando `Σ R_net⁻ = 0` com amostra > 0, ou `reason: "no_sample"` quando a população madura é
  vazia (só perdas, sem ganhos, produz PF = 0, não nulo). Mesmo padrão em `target_rate`
  (`reason: "no_resolved_touches"`), `net_profit_rate`/`expectancy`/`sum_of_hypothetical_r`
  (`reason: "no_sample"`).
- `censored.by_reason` preserva o prefixo: `gap:failed`, `gap:unregistered`, `gap:stalled`,
  `gap:unknown` (dado local tem casos sem o sufixo — worker rodando imagem anterior à correção do
  §16 das notas-S2 — caem em `gap:unknown` para não se perderem), `blocked` (soma de todo
  `blocked:<symbol>`, símbolos distintos disponíveis à parte se precisar). `late:*` nunca aparece
  aqui — é `no_entry`.
- `maturity.inconclusive = true` enquanto `evaluable_outcomes < 100 OU distinct_days < 30`
  (`evaluable_outcomes`/`distinct_days` = população madura acima, não `coverage.distinct_days`
  que é sobre decisões, não sobre outcomes maduros — os dois números podem divergir e é esperado).
- **Não é fotografia histórica:** `as_of` no passado seleciona decisões daquele período, mas lê o
  estado **atual** de `tracking_state`/`result`/`r_multiple` — nunca reconstrói o que era sabido
  naquele instante.

## `GET /api/v1/lab/shadow/signals?strategy_version_id=&market=&tracking_state=&result=&cohort=&cursor=&limit=&include=`

Cursor estável por `(decision_at, id)` (mesmo `decision_at` extraído do envelope). `market` filtra
por símbolo (`markets.symbol`, exchange implícito por join). `include=envelope` inclui
`supporting_features` completo (omitido por padrão — pode ser grande e é redundante para a maior
parte dos usos da tela).

```json
{
  "items": [
    {
      "signal_id": "07984643-a085-5ec1-b38b-ea0c325aa758",
      "strategy_version_id": "098b060c-...",
      "market": "AAAAUSDT",
      "decision_at": "2026-09-06T00:25:01.939152Z",
      "source_bar_close": "2026-09-06T00:25:00Z",
      "reference_price": "27453.1200000000",
      "stop": "27100.0000000000",
      "target1": "27950.0000000000",
      "entry_plan": {"source_bar_close": "...", "decision_at": "...", "entry_bar_open": "...",
                      "delay_s": 60, "max_entry_delay_s": 120, "late_reason": null},
      "virtual_entry": "27460.0000000000",
      "entry_ts": "2026-09-06T00:26:00Z",
      "exit_price": "27100.0000000000",
      "exit_ts": "2026-09-06T03:41:00Z",
      "result": "stop",
      "tracking_state": "terminal",
      "no_entry_reason": null,
      "censored_reason": null,
      "r_multiple": "-1.0421",
      "r_multiple_reason": null,
      "r_ex_funding": "-1.0400",
      "excursions": {
        "unit": "price", "method": "ohlc_complete_bars_v1", "available": true,
        "coverage": {"bars_known": 12, "bars_total": 15},
        "mfe": null, "mae": "0.8000", "mfe_ts": null, "mae_ts": null,
        "mfe_bar": null, "mae_bar": "2026-09-06T02:10:00Z",
        "mfe_complete_bars": "0", "mae_complete_bars": "0.8000",
        "bounds": {"mfe": [0, 4.2], "mae": [0.8, 0.8]},
        "bar_windows": {"first_open": "...", "last_open": "...", "exit_bar_open": "..."},
        "ambiguous": true, "initial_risk": "353.1200000000", "reference_price": "27453.1200000000"
      },
      "purpose": "research_only",
      "supporting_features": null
    }
  ],
  "next_cursor": null
}
```

`excursions` é sempre o `signal_outcomes.meta.excursions` inteiro, sem recorte — o consumidor
nunca deve inferir a unidade (é `price`, nunca R) nem descartar `coverage`/`bar_windows`.
`supporting_features` é um campo **sempre presente** no schema; vem `null` por padrão e só é
preenchido com `?include=envelope` (nunca omitido do JSON — mais fácil pro cliente checar do que
tratar ausência de chave).

## Erros

- `401` sem `Authorization`.
- `422` cursor inválido (`type` `.../invalid-cursor`), `window`/`cohort`/enum inválidos (validação
  de query do FastAPI).
- `503` Postgres fora (`type` `.../lab-unavailable`), simulado no teste via `OperationalError`
  injetado no repositório (matar o Postgres compartilhado do container de teste quebraria toda a
  suíte de integração — a mesma razão pela qual `test_system_workers_api.py` usa `WRONGTYPE` real
  em vez de desligar o Redis).

## Divergências e pendências (para a revisão)

1. `decisions` (por `Evaluation.state`) não é observável — sai `null` com motivo; `signals_emitted`
   é o que existe de fato. `coverage` não afirma nada sobre avaliações que nunca viraram sinal.
2. `superseded_by` reconstruído por regex sobre `changelog` (Astra concorda: não há fonte melhor;
   `system_events` também é texto livre) — a relação não é garantida por FK e o `changelog`
   continua mutável, então o campo é best-effort, nunca tratado como identidade.
3. `decision_at`/`cohort` vêm de JSONB (`supporting_features->>'...'`), sem índice dedicado —
   aceitável no volume atual (centenas de linhas), mas um índice de expressão seria trabalho de
   `database-architect` se o volume crescer.
4. A população financeira madura depende de `meta.entry_plan.entry_bar_open` + `meta.horizon_s`
   lidos e comparados em Python (não em SQL) após uma busca inicial por `strategy_version_id` +
   janela de `decision_at` — aceitável no volume atual; se crescer, dá para mover para uma
   expressão SQL gerada (`(meta->'entry_plan'->>'entry_bar_open')::timestamptz + (meta->>'horizon_s')::int * interval '1 second'`).
5. `as_of` não reconstrói uma fotografia histórica de `tracking_state`/`result`/`r_multiple` —
   documentado explicitamente para não ser lido como um backtest point-in-time.

Segunda opinião da Astra sobre este contrato em `.claude/state/astra-review-S3-lab-api-contract.md`
(REQUEST_CHANGES com 2 must-fix HIGH + 1 MEDIUM, todos incorporados acima).
