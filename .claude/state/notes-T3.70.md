# Notas T3.70 — reprova das nove verificações do Risk Engine em HEAD 572d3b6

**Data:** 2026-09-10 (madrugada, horário de Brasília). **Autor:** test-engineer.
**Escopo:** reprovar V1–V9 (`.claude/state/spec-T3.9-verificacoes.md`), a suíte do
`execution-worker`, a suíte pura de `packages/risk-core` e os testes de admissão da API, em
`572d3b6` — última prova em 2026-09-07 (`eccb648`/`ae25e32`, `.claude/state/notes-T3.9a.md`,
`notes-T3.9b.md`). Desde então: migrações 0015–0018, papel `hunter_runtime`, políticas de
elegibilidade, digest de `replay_runs` e mudanças no strategy-worker. **Não commitado. Nada em
`packages/**`/`services/**`/`infra/**` foi tocado.**

Cada arquivo rodado isoladamente, em primeiro plano, sem `stash`/`reset`/`checkout --`. Nenhum
testcontainer novo foi criado pelas rodadas (a suíte `tests/integration/paper/**` e a de
`execution-worker` usam o Postgres/Redis já em pé do `docker compose` da sessão, banco próprio por
rodada — ver `notes-T3.9a.md` §"Banco próprio"). `docker ps -a --filter label=org.testcontainers=true`
antes e depois mostra os mesmos 8 contêineres `Exited`, todos de 3 dias atrás, nenhum novo — nada
para limpar.

## 1. Comandos e saída real

```
uv run pytest packages/risk-core/tests/unit -q
  → 204 passed in 11.66s

uv run pytest apps/api/tests/unit/test_admission_adapter.py -q
  → 10 passed in 0.67s

uv run pytest tests/integration/paper/test_v1_sizing.py -q
  → 10 passed, 1 xfailed in 103.19s

uv run pytest tests/integration/paper/test_v2_warning_halves.py -q
  → 5 passed, 1 xfailed in 69.93s

uv run pytest tests/integration/paper/test_v3_blocked_keeps_protections.py -q
  → 5 passed in 66.76s

uv run pytest tests/integration/paper/test_v4_concurrent_orders_and_duplicate_fills.py -q
  → 3 passed in 37.26s

uv run pytest tests/integration/paper/test_v5_reconciliation.py -q
  → 3 passed in 129.76s

uv run pytest tests/integration/paper/test_v6_stale_data_reconnect_restart.py -q
  → 7 passed in 64.31s   (era 3 em 2026-09-07 — arquivo cresceu, sem regressão)

uv run pytest tests/integration/paper/test_v7_exchange_minimums.py -q
  → 9 passed, 1 xfailed in 2.00s

uv run pytest tests/integration/paper/test_v8_adverse_gap.py -q
  → 2 passed in 41.01s

uv run pytest tests/integration/paper/test_v9_no_fabricated_fill.py -q
  → 5 passed in 40.50s

uv run pytest tests/integration/paper/test_s10_crash_boundaries.py -q
  → 4 passed in 47.37s

uv run pytest tests/integration/paper/test_s11_concurrent_sessions.py -q
  → 5 passed, 1 xfailed in 67.74s

uv run pytest tests/integration/paper/test_v10_degraded_protection_restart.py -q
  → 1 passed in 34.30s   (extra: T3.29, não é uma das nove; adicionado após 2026-09-07)

uv run pytest services/execution-worker/tests -q
  → 174 passed in 408.63s (0:06:48)
```

Total novo desta rodada: **447 passed, 4 xfailed, 0 failed, 0 error** somando todos os comandos
acima (risk-core 204 + admissão 10 + paper suite 59 passed/4 xfailed + execution-worker 174).

## 2. Tabela V1–V9 → arquivo → resultado em 572d3b6

| Verificação | Arquivo | Resultado |
|---|---|---|
| V1 (tamanho/exposição/risco agregado) | `tests/integration/paper/test_v1_sizing.py` | 10 passed, 1 xfailed |
| V2 (multiplicador AVISO) | `tests/integration/paper/test_v2_warning_halves.py` | 5 passed, 1 xfailed |
| V3 (BLOQUEADO não impede saída) | `tests/integration/paper/test_v3_blocked_keeps_protections.py` | 5 passed |
| V4 (fills concorrentes/duplicados) | `tests/integration/paper/test_v4_concurrent_orders_and_duplicate_fills.py` | 3 passed |
| V5 (reconciliação cash/fee/PnL) | `tests/integration/paper/test_v5_reconciliation.py` | 3 passed |
| V6 (dados atrasados/reconexão/restart) | `tests/integration/paper/test_v6_stale_data_reconnect_restart.py` | 7 passed |
| V7 (mínimos/incrementos da exchange) | `tests/integration/paper/test_v7_exchange_minimums.py` | 9 passed, 1 xfailed |
| V8 (gap adverso vs. stop) | `tests/integration/paper/test_v8_adverse_gap.py` | 2 passed |
| V9 (sem fill fabricado) | `tests/integration/paper/test_v9_no_fabricated_fill.py` | 5 passed |
| §10 (crash em fronteira) | `tests/integration/paper/test_s10_crash_boundaries.py` | 4 passed |
| §11 (duas sessões concorrentes) | `tests/integration/paper/test_s11_concurrent_sessions.py` | 5 passed, 1 xfailed |
| extra (V10, T3.29) | `tests/integration/paper/test_v10_degraded_protection_restart.py` | 1 passed |
| suíte execution-worker | `services/execution-worker/tests/**` (18 arquivos, 174 testes) | 174 passed |
| suíte risk-core (núcleo puro) | `packages/risk-core/tests/unit/**` | 204 passed |
| admissão API | `apps/api/tests/unit/test_admission_adapter.py` | 10 passed |

Nenhuma regressão contra `notes-T3.9a.md`/`notes-T3.9b.md`: os mesmos 4 `xfail(strict=True)` de
2026-09-07 continuam `xfail`; nenhum teste que era `passed` virou `failed`; V6 ganhou testes (3→7)
sem mudar nenhum número citado nas notas anteriores.

## 3. Status dos 4 `xfail(strict=True)` (§13/§13b)

Todos os quatro continuam **xfail** (divergência inalterada) — nenhum virou XPASS, nenhum precisa
de remoção de marcador:

1. `test_v1_sizing.py::test_v1_step4_the_cash_ceiling_wins_with_500_of_cash_and_400_reserved` —
   ainda xfail. `available_cash=99,599904` bate; `binding_constraint` medido continua
   `total_exposure`, nunca `cash` (impossibilidade aritmética do ledger com alavancagem 1, notes-T3.9a §1).
2. `test_v2_warning_halves.py::test_v2_the_spec_number_925_900_at_an_equity_of_19_800` — ainda
   xfail. Com equity real em 19.800 o teto é `916,600`, não `925,900` (a spec assumiu equity
   20.000 na fórmula do multiplicador, notes-T3.9a §2).
3. `test_v7_exchange_minimums.py::...::test_v7_step5_the_spec_reason_below_min_qty` — ainda xfail.
   Rótulo medido continua `below_min_notional`, não `below_min_qty` (ordem dos filtros: LOT_SIZE
   passa por igualdade, NOTIONAL barra, notes-T3.9b §2.1).
4. `test_s11_concurrent_sessions.py::test_s11_step5_the_second_session_takes_the_remaining_16_051`
   — ainda xfail. A segunda reserva no mesmo mercado continua recusada por `duplicate_position`
   (D3), nunca chega a disputar o teto de participação (notes-T3.9a §3).

## 4. Falhas

Nenhuma. `0 failed, 0 error` em todos os quinze comandos.

## 5. Docker / limpeza

`docker ps -a --filter "label=org.testcontainers=true"` antes e depois: os mesmos 8 contêineres
`Exited` de 3 dias atrás (`elated_swartz`, `upbeat_solomon`, `frosty_moser`, `elegant_banzai`,
`loving_gauss`, `adoring_rosalind`, `vigorous_taussig`, `bold_poitras`) — nenhum criado por esta
rodada, nada para remover. Stack do `docker compose` da sessão (`postgres`, `redis`, `api`, `web`,
workers) permanece nos mesmos estados de saúde de antes da rodada.

## 6. Observações operacionais

- `test_v5_reconciliation.py` (129,76 s) e a suíte inteira de `services/execution-worker/tests`
  (408,63 s) excederam o timeout de 290 s por invocação e o harness moveu a execução para
  segundo plano automaticamente; aguardei a notificação de conclusão em vez de novas tentativas —
  nenhuma execução ficou de fato "em segundo plano" por escolha, foi o próprio comando que passou
  do teto. Para uma próxima rodada, `services/execution-worker/tests` deve ser dividido por
  arquivo ou por `-k` para caber no teto de 290 s por invocação.
- Nenhuma mutação foi aplicada em código de produção nesta tarefa (só reprova, sem diagnosticar
  falha nenhuma — não havia falha).
