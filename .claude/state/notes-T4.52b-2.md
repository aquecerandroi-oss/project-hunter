# Notas T4.52b-2 — estado em memória por mint e a guarda de queda (puro)

Data: 2026-09-18. Escopo: `services/meme-worker/hunter_meme_worker/{event_state,event_book}.py`,
`packages/indicators/hunter_indicators/meme/{drawdown,rules,rules_criteria,rules_validation}.py`,
`services/meme-worker/hunter_meme_worker/lab_models.py`. Nada de I/O, nada de relógio: todo instante é
argumento; todo número monetário é `Decimal`. Nenhum arquivo acima de 350 linhas.

## 1. `MintEventState` (`event_state.py`) e `EventBook` (`event_book.py`)

- `points` (deque ≤ 120 s de `CurvePoint(observed_at, received_at, mcap_sol, real_sol, real_token,
  mayhem, slot, source)`) alimentada por `apply_trade(NormalizedCurveTrade)` (reservas pós-trade do
  `TradeEvent`), `apply_account(BondingCurveAccount, slot=, received_at=)` (bytes da conta; sem block time,
  `observed_at = received_at` como o `rpc_curves` já faz) e `apply_photo(CurvePoint)` (foto da via rápida).
- `trades` (deque ≤ 60 s de `TapeTrade` — **o mesmo tipo que `features_tape.tape_for` lê**). `tape_minute(as_of)`
  chama `tape_for(...)` literalmente, com `covered_since = subscribed_at`, e devolve `(TapeMinute | None, reason)`;
  cobertura < 60 s ⇒ `(None, "event_feed_warming")`. Os booleanos do criador vêm de `creator_flow()` (Σ desde a
  assinatura, nunca da deque de 60 s): `True` na primeira venda do criador; `False` só se a assinatura cobre o
  mint desde ≤ 5 s após `first_seen_at` (`COVERAGE_GRACE_S`); senão `None` — a regra do plano §2.
- `mark_gap(at)` (frame descartado/reconexão): `covered_since` avança, `trades` zera, a fita volta a aquecer por
  60 s (fail closed, plano §4). Teto duro `MAX_TRADES = 4000` — estourar é gap, nunca subcontagem silenciosa.
- `peaks`: `PeakDeque` monotônica de `real_sol` (cabeça = pico), podada no mesmo horizonte dos `points` (120 s).
  `recent_drawdown(as_of, window_s, max_gap_s)`: O(1) amortizado quando `as_of ≥` último recebimento (o caso
  do portão de evento); para `as_of` anterior recai na dobra exata sobre `points` (não-antecipação exata).
- `mcap_sol` de um trade só existe com `total_supply` conhecido (vem do `accountNotification` ou do construtor —
  a linha-base do `snapshot.total_supply`); sem ele, o ponto entra com `mcap_sol = None` e `compute_fast` responde
  `no_snapshot` (fail closed, como o plano manda).
- `EventBook(max_mints)`: `touch(mint, at=, first_seen_at=, total_supply=)` cria (assina) ou devolve; cheio ⇒
  `None` + `refused += 1` (quem chama decide o que derrubar); `evict(mint)`; `evict_older_than(at=, max_idle_s=)`
  por `last_event_at or subscribed_at`.

## 2. `hunter_indicators.meme.drawdown`

`recent_drawdown(points, as_of, window_s=60, max_gap_s=30) -> RecentDrawdown(dd_pct, peak_age_s, reason)`
(NamedTuple, desempacota como tupla). `points` é `PeakDeque` (O(1) amortizado; `ValueError` se a deque tem
ponto recebido depois de `as_of`, em vez de contar o futuro) ou `Sequence[ReservePoint]` (filtra
`received_at ≤ as_of`, O(n)). `dd = 1 − atual/pico` sobre **`real_sol_reserves`** (nunca mcap, KB-0115),
quantizado a 1e-6; `peak_age_s` em segundos com 3 casas. Razões: `no_observation`, `stale` (observação mais nova
com > 30 s). A consulta na deque **não consome** (`peak_since`): duas janelas podem ler a mesma deque; a retenção
é do dono (`expire`). Registrado como `DRAWDOWN_DEFINITION` (`recent_drawdown_pct` v1, params
`{window_s: 60, max_gap_s: 30}`).

## 3. Portão

- `EntryGate.max_recent_drawdown_pct: Decimal | None = None` (**fração**, `0.50` = metade — a unidade do plano
  e da KB-0118, diferente de `min_progress_pct` que é 0–100), `recent_drawdown_window_s = 60`,
  `recent_drawdown_max_gap_s = 30`. `as_parameters()` só lista os três quando o teto está ligado: um set congelado
  lê exatamente como antes (provado pelos 131 testes de porta existentes, intocados).
- `EntryFeatures.recent_drawdown_pct / _peak_age_s / _reason` (todos `None` por padrão).
- `rules_criteria.drawdown_refusals`: `recent_drawdown_unknown` se a feature é `None`; `recent_drawdown` se
  `dd > X` **e** pico ≤ janela. Estrito (`atual/pico < X`) como a definição congelada da EXP-M13; pico mais velho
  que a janela é queda que parou, nunca recusa. Avaliado por último em `evaluate_entry`.
- `_age/_progress/_participation_refusals` e `participation_pct` migraram de `rules.py` (343 → 324 linhas) para
  `rules_criteria.py` (agora públicos, `rules.py` reexporta `participation_pct`). Mesmo código, mesmos nomes.
- `rules_validation._validate_drawdown`: teto em (0, 1]; janela e gap positivos.
- `lab_models._gate_from_params` lê as três chaves (`optional_decimal` / `int_or`); ausentes = como antes.

## 4. Testes (`test_event_state.py`, 9 casos; `test_meme_drawdown.py`, 18 casos)

Replay das fixtures da T4.52b-1 (8 `TradeEvent` em 5 mints; `received_at = block_time + 0,5 s`) ⇒ por mint,
`buys/sells/unique_buyers/net/volume` iguais à contagem direta e ao `tape_for` à mão; a venda do criador em
`HMfRWjo6…` aparece no `creator_flow` e em `tape.creator_net_seller`. Não-antecipação: o mint com 3 fills julgado
1 ms antes do 3º recebimento tem 2 na fita e 2 fotos usáveis. Aquecimento: 59 s ⇒ `event_feed_warming`; gap ⇒
reaquece. Casos KB-0118: TAXCOIN (pico 67 s, 6 SOL a 55 s, 5,252 agora) ⇒ `dd = 0,124667` com N = 60 (não corta),
`0,822795` com N = 120 (corta, como a KB mediu); pico a 40 s ⇒ `0,822795` corta; observação a 31 s ⇒ `stale`;
30 s inclusive ainda vale. Deque × dobra completa idênticas em 200 instantes de uma serra (e com janela de 30 s
na mesma deque). Portão sem a chave: `as_parameters()` e veredito inalterados.

## 5. Premissas numéricas declaradas

1. `max_recent_drawdown_pct` é fração (0–1), não percentual, seguindo o plano ("0,50") e a EXP-M13.
2. Recusa estrita `dd > X` (⇔ `atual/pico < X`), como a definição congelada; `dd == X` passa.
3. `accountNotification` sem block time ⇒ `observed_at = received_at` (mesma escolha do `rpc_curves`).
4. `TradeEvent.block_time` ausente (nunca aconteceu na fixture) ⇒ `received_at`, contado em `block_time_missing`.
5. `creator_net_seller` na pista de evento = "qualquer venda do criador vista" (plano §2), não `Σ vendas > Σ compras`;
   `creator_flow()` expõe as duas somas para quem quiser a outra leitura.
6. Retenção da `PeakDeque` = 120 s (a dos `points`): uma janela de drawdown > 120 s não é exata neste estado.

## 6. Comandos

- `pytest packages/indicators/tests -m "not live"`: 1400 passed. `pytest services/meme-worker/tests -m "not live
  and not integration"`: 355 passed. Integração (Docker) em duas levas por causa do teto de 590 s: 43 + 51 passed.
- `ruff check`/`format --check` limpos nos arquivos tocados (o repo tem 10 erros pré-existentes em
  `infra/scripts/research/2026-09-16-r20-*.py`/`r3-*.py`, fora do escopo). `pyright`: 0 erros nos 9 arquivos.
  `check_file_size.py`: 954 arquivos, 0 acima do orçamento.

## 7. O que a T4.52b-3 consome

`EventBook.touch(mint, at=now, first_seen_at=row.first_seen_at, total_supply=row.snapshot.total_supply)`;
`state.apply_trade(normalized_curve_trade(...))` / `state.apply_account(decode_bonding_curve_account(...), slot=,
received_at=)`; na avaliação: `compute_fast(state.fast_points(), as_of=, initial_real_token_reserves=)`,
`tape, tape_reason = state.tape_minute(as_of)` → `tape_columns(tape, tape_reason or ...)`,
`dd, age, reason = state.recent_drawdown(as_of, window_s=gate.recent_drawdown_window_s,
max_gap_s=gate.recent_drawdown_max_gap_s)` → `EntryFeatures.recent_drawdown_*`. Ao sair de `young_mints`:
`book.evict(mint)`; frame descartado: `state.mark_gap(now)`.
