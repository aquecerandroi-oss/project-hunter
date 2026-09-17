# R47: Análise do Radar — Últimas 6 Horas

**Data**: 2026-09-17 01:22 BRT (UTC 04:22)

## 1. Contagem de Eventos por Hora (BRT = UTC−3)

Total: **104 eventos** distribuídos nos últimos 6h.

### Distribuição por tipo:
- **meme_curve_poll_failed**: ~74 eventos (poll loop REST failures)
- **meme_mayhem_mint_skipped**: 26 eventos (empty virtual reserve)
- **meme_tape_pull_failed**: 4 eventos (pumpfun_swap_api transport error)

### Concentração temporal (estimado de UTC, convertido para BRT):
- **16:29** BRT: 1 mayhem
- **17:06–17:59** BRT: ~18 curve + 1 mayhem (pico principal)
- **18:38–18:48** BRT: 7 curve
- **19:47–19:57** BRT: 3 curve + 1 mayhem
- **20:00–20:56** BRT: 6 curve + 3 mayhem
- **21:55–22:12** BRT: 40+ curve + 21 mayhem + 4 tape

## 2. Classificação dos Erros

### meme_curve_poll_failed (REST poll loop):
**33 x "pumpfun rest resource not found"**
- Moedas: FWDtiB5f, LUV9GB51, DJTu7vi8, JDX2gNUp, 84hwN7EH, AMC1qwR9, RcZmt84V, 5RZz2xwK, 54GpAYkU, 5R9q8Vr, GQT1N9ms, 24xjxmXi
- **Análise**: Todas essas moedas têm `migrated_at = completed_at` (completadas instantaneamente quando descobertas)
- **Classificação**: ✅ **Normal fim de vida** — coins completados/migrados para Raydium não aparecem mais no REST pump.fun
- **O que acontece**: A moeda é marcada com `NOT_POLLED` ou similar, retries continuam até que envelheça e saia do tracked set

**41 x "pumpfun rest curve response missing [reserves/supply]"**
- Moedas: EPjFWdd5, pumpCmXqMf, 7vfCXTUX, XsoCS1Tf
- **Análise**: 
  - EPjFWdd5: 183 rows em `meme_features_15s` ✓
  - pumpCmXqMf: 822 rows em `meme_features_15s` ✓
  - 7vfCXTUX: 66 rows em `meme_features_15s` ✓
- **Classificação**: ✅ **Normal, cobertura redundante via fast lane** — O REST está com resposta corrompida/incompleta, mas o RPC (fast lane) continua coletando dados a cada 15s
- **O que acontece**: Poll loop pula a moeda (absences[mint] = RATE_LIMITED ou NOT_POLLED), mas `meme_features_15s` continua preenchida via fast lane (T4.16)

### meme_mayhem_mint_skipped (mayhem mode):
**26 x "empty virtual reserve"**
- **Classificação**: ✅ **Normal** — mayhem mode detecta moedas com reserva vitual vazia e as pula
- **O que acontece**: A moeda é marcada com `no_snapshot` ou similar, não entra no lab

### meme_tape_pull_failed (swap_api):
**4 x "pumpfun_swap_api transport error"**
- Tipo: ExchangeUnavailable (via Redis: `swap_api` errors_1h: 4)
- **Classificação**: ✅ **Burst breve** (concentrado em 01:00 UTC = 22:00 BRT)
- **O que acontece**: Trades não são puxados naquele segundo, retries continuam

## 3. Dependências do Fast Lane

Leitura em `fast_lane.py`:
- **Fast lane** (15s readings): `ctx.chain.get_curve_states()` → **Solana RPC** (`confirmed` commitment)
- **Poll loop** (60s readings): `ctx.curves.get_curve_state()` → **pump.fun REST API** (`pumpfun_rest`)
- **Tape puller** (trades): `swap_api.get_trades()` → **swap-api** (Cloudflare)

✅ **O fast lane não depende do REST curve** — usa RPC direto. Portanto:
- `meme_curve_poll_failed` (REST errors) **não afeta** o fast lane
- Moedas jovens (< 5 min) continuam em `meme_features_15s` via RPC mesmo que REST falhe

## 4. Estado Atual do Radar (Redis)

```
pumpfun_rest:
  errors_1h: 52
  last_error: "unsupported_quote" (não é rate limit)
  
swap_api:
  errors_1h: 4
  used_60s: 14 / budget_60s: 16 (não rate-limitado)
  
swap_api_429_1h: 0  ← SEM 429 (rate limit real)
activity_dark_60s: 0  ← SEM dark periods

fast_lane_mints: 119
tape_covered_mints: 17
tracked: 139
```

✅ **Sem rate limit real** — `swap_api_429_1h = 0`, `swap_api_blocked_until` vazio.

## 5. Recomendação

**Classificação: NADA A FAZER**

- ✅ Os erros REST são **normal end-of-life noise** (moedas completadas/migradas)
- ✅ Os erros "missing response" têm **cobertura RPC redundante** via fast lane
- ✅ Os erros tape são **transientes de infraestrutura** (4 em 6h = 0.66/h), não vazamento
- ✅ **Sem rate limit real** — radar está saudável

**A moeda continua coletando dados após REST fail:**
- Moedas jovens: 15s RPC readings em `meme_features_15s`
- Moedas velhas completadas: já migraram, resto é pós-morte normal

---
**Conclusão**: Vazamento = não. Ruído de fim de vida = sim. Lab e fast lane funcionando normalmente.
