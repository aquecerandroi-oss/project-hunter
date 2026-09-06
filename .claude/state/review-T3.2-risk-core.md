# Revisão adversarial — T3.2 risk-core (`bf4924b`) — REQUEST_CHANGES (code-reviewer, 2026-09-06)

Reproduções em scripts isolados (scratchpad do orquestrador): `repro_daily_loss.py`, `repro_rest.py`, `repro_entryref.py`, `check_ties_and_min.py`, `check_float.py`, `mutant_round_up.py`, `mutant_no_multiplier.py`. Mutação: arredondar para cima → 20 falhas; multiplicador do AVISO = 1 → 8 falhas (os testes reprovam pelo motivo certo).

## BLOQUEIA
1. **`exposure.py:104-149` — perda diária lida de `daily_realized_pnl + daily_unrealized_pnl − daily_costs`, campos opcionais com default 0**, não de `1 − equity/day_start_equity` (v2 §5). Cenário: abertura 20.000, agora 19.500 (−2,5 %), pico 20.000, PnL do dia vazio → `daily_loss PASSED value=0`, kill switch ACTIVE, entrada aprovada em tamanho cheio (1.805,5). Corrigir: derivar do patrimônio (a diretiva proíbe aporte e reset, então a identidade vale) ou recusar no `model_validator` estado em que os campos discordam do patrimônio.
2. **`inputs.py:92` + `sizing.py:250-251` + `evaluate.py:80-107` — `entry_ref` da proposta nunca é confrontado com o mercado; `last_price` é obrigatório e nunca lido.** Cenário: `entry_ref=100`, stop 97,5, mercado em 110 → aprovado, notional registrado 1.851,80, real 2.036,98, perda real no stop 235,55 = 1,18 % do patrimônio (teto 0,25 %); e LONG com stop acima do mercado (90) aprovado. Corrigir: check que confronta `entry_ref` com `last_price`/mid dentro de banda declarada (v2 §3.1 "entrada fora da zona", ±0,5 %), stop tem de estar abaixo do preço observado, e o sizing/caixa/exposição usam o pior entre `entry_ref` e preço observado (ou o observado) — declarar no contrato.
3. **`limits.py:81` + `inputs.py:117,163-174` — `max_volume_age_s` (120 s no `PAPER_V1`) nunca usado; `volume_ts` nunca validado.** Cenário: volume do minuto de 45 min atrás → participação calculada sobre a foto velha e aprovada. Corrigir: idade do volume do minuto e do 24 h contra o limite → `unavailable` → recusa.

## DEVE CORRIGIR
4. **`exposure.py:98` + `sizing.py:228-233` + `confirmations.py:56,95-101` — caixa não desconta entradas pendentes** (único limite que não conta reservas). Cenário: caixa 500, pendente 400 → aprova 499,5 → 900 contra 500. Corrigir: `available_cash = cash − Σ reserved_notional × entry_cash_multiplier`.
5. **`kill_switch.py:169-194` — `resume(assessment)` nunca usa `assessment`**; parâmetro morto numa função de destravamento; sem chamador; T3.6 é a dona da retomada persistida. Remover o parâmetro ou usá-lo (recusar retomada enquanto os gatilhos automáticos ainda mordem) e declarar o dono.
6. **`sizing.py:262-268` — `tied_limits` sem teste** (aceite da T3.2 nomeia empates). Verificado manualmente correto; fixar com teste (desempate estável por `CAP_ORDER`).

## SUGESTÕES (fazer junto, são baratas)
7. `sizing.py:231` — teto de caixa publica `limit=limits.max_leverage`; devia ser `portfolio.cash`/`available_cash`.
8. `checks.py:118-120,193-195` — estados `unavailable` de `spread` (sem bid/ask) e `stop_distance` (geometria inválida) sem teste.
9. `tests/unit/test_properties.py:22-27` — geradores só com carteira vazia e β = 1; gerar posições/reservas e β ∈ [−3, 3] para que `beta_exposure` e `aggregate_risk` sejam limitantes em algumas amostras.
10. `packages/core/.../envelope.py:45` — `AssumedCosts` aceita `float` (converte via str); registrar (core está fora do escopo do guardião; pedir ao dono do core).
11. `kill_switch.py:93-128` — teste "sem latch, `assess` volta a ACTIVE — por isso o latch é obrigatório na T3.6".

## Conferido e correto
Arredondamento sempre para baixo; multiplicador depois dos nove tetos com mínimo revalidado; `requested_notional` no `min`; `|β|` e β desconhecido → agregado `None` → recusa; β = 0 sem divisão por zero; BLOQUEADO só cancela pendentes; `evaluate_exit` aprovado sob TRADING_DISABLED/EMERGENCY com clamp; `resume` casado; ordenação por dicionário; dia SP em 02:00/03:00 UTC com âncora validada; pico monotônico; JSON canônico determinístico; nenhum módulo > 350 (maior `sizing.py` 334).
