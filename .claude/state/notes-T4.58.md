# T4.58 — janela de progresso do executor configurável pelo `.env`

**Data:** 2026-09-18. **Motivo:** o portão `operator/5` da mesa foi para `max_progress_pct = 100`
(Proposta A, `obsidian/06-DECISIONS/2026-09-12-teste-pequeno-meme-real.md`), mas o check 9 do
executor recusava `progress_above_window` acima de `MemeLimits.curve_progress_max_pct = 0.50`
(`MEME_PAPER_V0`), sem forma de sobrescrever. JAYCAT (11:06 BRT, 61,7 %) foi a primeira recusa.

## O que mudou

- `packages/risk-core/hunter_risk_meme/limits.py`: `limits_from_env` lê as opcionais
  `MEME_CURVE_PROGRESS_MIN_PCT` / `MEME_CURVE_PROGRESS_MAX_PCT` (frações 0–1, `Decimal`).
  Ausentes ⇒ valores da base; ilegível, fora de `[0, 1]` ou `min ≥ max` ⇒ `MemePolicyMissing`
  nomeando a(s) variável(is) e, no caso da janela vazia, o detalhe
  `curve_progress window is empty (min=… >= max=…)`. `MEME_PAPER_V0` intocado (2 %–50 %).
- `services/meme-executor/hunter_meme_executor/heartbeat.py`: `policy_fields(limits)` (pura) monta o
  blob `policy`; ganhou `curve_progress_min_pct` / `curve_progress_max_pct`.
- Docs: `docs/ACTIVATION.md` §9b item 9c-bis; `docs/RISK_ENGINE_MEME.md` §3.1 (tabela de
  parâmetros + linha do check 9).

## A linha do `.env` para 100 %

```
MEME_CURVE_PROGRESS_MAX_PCT=1.0
```

Depois: `MEME_LIVE=1 MEME=1 MEME_ENABLED=true bash infra/vps/compose.sh update`. Conferir em
`hb:meme:executor` → `policy.curve_progress_max_pct == "1.0"`.

## Observações

- Em modo papel (`ENABLE_MEME_LIVE_TRADING` desligada) `_base_limits` cai para `MEME_PAPER_V0` se
  as cinco de política faltarem — nesse caso a janela do `.env` também é ignorada (comportamento
  pré-existente; a VPS roda live, então não afeta o caso do Everton).
- Um `max` de `1.0` só afasta o veto do executor; `curve_complete` (curva 100 % / migrada) continua
  recusando, e o `operator/5` da mesa continua sendo o primeiro filtro.
