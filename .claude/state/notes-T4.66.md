# Notas T4.66 — EXP-M19 "subida com gente atrás" (retenção dos snipers, carteiras novas, vendas rápidas)

Data: 2026-09-19. Escopo: `packages/indicators/hunter_indicators/meme/{crowd,rules_crowd,rules,rules_validation}.py`,
`packages/exchange-adapters/hunter_exchanges/pumpfun/{models,trade_event}.py` (um campo opcional),
`services/meme-worker/hunter_meme_worker/{event_state,event_state_values,event_gate_rows,proposals,proposals_row,
gate_refusal_trail,lab_models,lab_gate_params,lab_params}.py`, migração `0054`, docs. `services/meme-executor/` não
tocado. Nenhum arquivo acima de 350 linhas.

## 1. A lógica pura — `hunter_indicators.meme.crowd`

- `CrowdTrade(block_time, received_at, trader, side, tokens, slot)`; `CrowdLedger(covered_since, creator, create_slot,
  early_slots=3, early_buyers=10, window_s=30, quick_flip_s=20)`; `push(trade)` O(1) amortizado; `mark_gap(at)`;
  `features(as_of, covered_from_birth=) -> CrowdFeatures(early_retention_pct, early_age_s, new_wallets_30s,
  quick_flip_share_30s, early_wallets, early_reason, window_reason)`.
- Carteiras iniciais: compradores (nunca o criador) com `slot − create_slot < 3` quando `create_slot` é conhecido;
  senão os 10 primeiros compradores distintos na ordem de chegada. As fills dessas carteiras ficam numa deque própria
  (`MAX_EARLY_FILLS = 2000`, estourar = gap), dobrada na avaliação com `received_at ≤ as_of` (não-antecipação exata).
- Retenção = Σ max(comprado − vendido, 0) ÷ Σ comprado, quantizada a 1e-6; idade em segundos com 3 casas.
- Janela: deque dos últimos 30 s por `block_time` relativo ao último `received_at` (`MAX_RECENT = 4000`); `new_wallets`
  conta traders com primeiro trade (dicionário por carteira, `MAX_WALLETS = 20000`) dentro da janela; `quick_flip`
  = vendas de carteira com primeira compra há < 20 s ÷ todos os trades da janela.
- Razões de `None` (`CROWD_REASONS`): `not_covered_from_birth`, `coverage_gap`, `no_early_wallets`, `tokens_unknown`,
  `window_not_covered`, `no_trades_in_window`, `wallets_overflow`. Quatro `FeatureDefinition` v1 em `CROWD_DEFINITIONS`.

## 2. Portão

- `EntryGate.min_early_retention_pct` (fração, (0, 1]), `min_early_age_s` (≥ 0), `min_new_wallets_30s` (≥ 0),
  `max_quick_flip_share_30s` (fração, [0, 1]) — todos `None` por padrão; `as_parameters()` só os lista quando ligados.
- `EntryFeatures.early_retention_pct / early_age_s / new_wallets_30s / quick_flip_share_30s` (`None` por padrão).
- `rules_crowd.crowd_refusals` (módulo novo, o `rules_criteria` está em 335 linhas): `early_retention_unknown` (uma
  só para retenção e idade — a mesma medição), `early_retention_below_min`, `early_age_below_min`,
  `new_wallets_unknown`, `new_wallets_below_min`, `quick_flip_unknown`, `quick_flip_above_max` (estrito `>`).
  Avaliado por último em `evaluate_entry`.
- `lab_models._gate_from_params` **mudou de casa**: o corpo é `lab_gate_params.gate_from_params` (o `lab_models` estava
  em 348 linhas); `lab_models._gate_from_params` continua existindo como alias (as docstrings das migrações e
  `test_event_state` o citam). `lab_params.optional_int` novo.

## 3. Fiação na pista de evento

- `NormalizedCurveTrade.token_amount: Decimal | None = None` (subunidades cruas, como `lamports`), preenchido por
  `normalized_curve_trade` a partir de `TradeEvent.token_amount`. Sem ele a retenção é `tokens_unknown`.
- `MintEventState.crowd: CrowdLedger` (criado em `__post_init__` com `covered_since = subscribed_at`); `apply_trade`
  empurra um `CrowdTrade` por fill e mantém `crowd.creator = self.creator`; `mark_gap` propaga;
  `crowd_features(as_of)` passa `covered_from_birth` (a regra dos 5 s que já existia). `CurvePoint`/`CreatorFlow`
  foram para `event_state_values.py` (reexportados) para caber no orçamento.
- `GateRow` ganhou os quatro campos (`None` por padrão); `build_event_row` os preenche; `entry_features_of` os copia;
  `gate_refusal_trail._NUMERIC_REFUSALS` decodifica as quatro recusas numéricas. A pista de 15 s/minuto não muda.

## 4. Semente

`0054_meme_gate_crowd_arm` (24 caracteres) sobre `0053_meme_launch_lane_arm`: `flow_v2/10` (`…0018`) = `flow_v2/6` +
`CROWD_OVERRIDES`; §17.7 nas quatro tabelas com FK; `HEAD_REVISION` e contagem de ativos (19 → 20) em
`test_migrations.py`; `test_migration_0054.py` no formato da `0052`. Os testes da `0053` já se posicionavam em
`REVISION` (não em `head`) — nada a mudar lá.

## 5. Premissas numéricas declaradas

1. "3 primeiros slots" = slots `create_slot`, `+1`, `+2` (blocos 1–3 contando o do `create` como o 1º). Hoje o
   `create_slot` nunca chega ao estado (o tracker não guarda slot do `create`), então vale a regra dos 10 compradores.
2. O criador nunca é carteira inicial (a venda dele já é `creator_net_seller`); os trades dele **contam** no
   denominador de `quick_flip_share_30s` e em `new_wallets_30s` como qualquer carteira.
3. Retenção/idade só com `covered_from_birth` (assinatura ≤ 5 s do `first_seen_at`); senão `early_retention_unknown`.
4. "Carteira nova" = primeiro trade visto pela cobertura; a janela exige `covered_since ≤ as_of − 30 s`, então os
   primeiros 30 s de cobertura (em que todo mundo parece novo) nunca são julgados. Após um gap os dicionários de
   primeiro trade/compra **não** são zerados (uma carteira vista antes do gap continua "velha" — subcontagem
   conservadora de novas), mas a retenção fica `coverage_gap` para sempre naquele mint.
5. `quick_flip_share_30s` sem trade na janela é `None` (`no_trades_in_window`), não 0; `new_wallets_30s` sem trade
   é 0 (a cobertura existe, o zero é real).
6. Pisos inclusivos (`0.70` passa, `60` passa, `5` passa); teto estrito (`0.20` passa, `0.21` recusa).
7. Um fill de carteira inicial recebido depois de `as_of` não conta (dobra na avaliação); um fill fora de ordem com
   `block_time` anterior só pode envelhecer uma carteira (conservador).

## 6. Comandos

- `uv run pytest packages/indicators/tests -m "not live"` → 1428 passed (era 1400 + 13 novos + 15 de outras tarefas).
- `uv run pytest services/meme-worker/tests -m "not live and not integration"` → 446 passed.
- `uv run pytest services/meme-worker/tests/test_event_gate_crowd_integration.py` → 1 passed (17 s).
- `uv run pytest packages/core/tests/integration/test_migration_0054.py` → 8 passed (30 s);
  `test_migration_0053.py` → 8 passed; `test_migrations.py -k "0022 or head or autogenerate or reverses"` → 45 passed
  (296 s).
- `uv run pytest services/meme-executor/tests -m "not live and not integration"` → 443 passed (o campo novo do modelo
  não quebra o executor); `packages/exchange-adapters/tests/unit -k "pumpfun or trade_event or rpc_ws"` → 303 passed.
- `ruff check`/`format --check`, `pyright` (0 erros nos arquivos tocados), `check_file_size.py` — ver o relatório.

## 7. Concerns

- **Cobertura desde o nascimento.** A sincronização das assinaturas do portão de evento roda a cada 5 s sobre
  `young_mints`; os snipers compram em ~1–2 s. Se a maioria dos mints entra fora da graça de 5 s, o braço recusa
  `early_retention_unknown` e mede cegueira. P0 na página da EXP-M19: fração de `early_retention_unknown` ≤ 20 %
  nas primeiras 24 h. Saídas possíveis (fora do escopo): assinar no instante do `create` (a pista de lançamento já o
  recebe em ~100 ms) ou preencher os primeiros slots com `getSignaturesForAddress` na assinatura.
- O `create_slot` não chega ao estado — a regra dos "3 slots" está implementada e testada mas hoje nunca é usada.
- A trilha grava só o quase-passa (uma recusa); um mint que falha `early_retention_unknown` **e** outra coisa não
  deixa linha — a leitura de P0 vem de `meme_lab_ticks.refusals` por nome, não da trilha.
