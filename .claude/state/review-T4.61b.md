# Revisão de risco — T4.61b (`9b4d9174`, tamanho por convicção no executor real)

**Revisor:** guardião do risk engine. **Data:** 18/09/2026. Só leitura; nada editado, VPS/.env intocados.
**Provas:** `uv run pytest services/meme-executor/tests/test_conviction.py -q` → `30 passed in 2.33s`;
sonda no scratchpad (`probe_t461b.py`) com a saída citada em cada achado.

**Veredito: SAFE_TO_DEPLOY(off) com uma ressalva (A1) · NÃO ligar (`MEME_CONVICTION_SIZING=on`) antes de A2, A4, A5, A9.**

## 1. Flag OFF — o caminho de compra é o de antes?

Sim, byte a byte no que decide dinheiro: `apply_ladder` devolve o **mesmo objeto** quando não aplicada
(`conviction_read.py:127-128`); `ladder.refusal` é `None` com `enabled=False` (`conviction.py:229-230`; sonda D:
`refusal None, ladder_refusal entry_after_drop, applied False, requested_sol 0.28`); `chain.read_entry`
(`chain.py:210-218`) faz as mesmas três leituras na mesma ordem do antigo `_read_chain`, e `not account.exists` ≡
`creates_ata()`; a ordem das recusas em `entries.py:97-201` não mudou. Diferenças: (i) a consulta de sombra entre
`proposal_from` e `admit` (`entries.py:167`); (ii) o bloco `conviction` no JSON de `admission`/`intent`.

- **A1 — `conviction_read.py:111-112` / `entries.py:167` — MÉDIO — a consulta de sombra é limitada mas não é
  guardada.** Limitada: índices `ix_meme_curve_snapshots_mint_observed` (`infra/migrations/ddl/meme_radar.py:298`) e
  `ix_meme_features_15s_mint_as_of` (`meme_gate_v2.py:176`), `LIMIT 1` no lateral, janelas de 60/120 s com poda de
  partição, `statement_timeout` 15 s do `hunter_worker` + `command_timeout` 30 s. **Não recusa** com a flag
  desligada (evidência ausente vira desconto só na sombra). Mas uma exceção (timeout, pool, partição girando à
  meia-noite) sobe sem `try` por `conviction_for → handle_candidate → entries_once → forever`, que re-lança
  (`main.py:93-95`), e o `TaskGroup` (`main.py:257-274`) derruba **também o loop de saídas** até o processo
  reiniciar. Cenário: posição aberta com trailing armado, `meme_curve_snapshots` travada 15 s → tick de entradas
  levanta → loop `exits` cancelado junto → nenhuma saída de proteção até o restart. Mesma classe do
  `token_context` já existente, mas é custo **novo com a flag desligada**. Fix: `try/except` em `conviction_for`
  devolvendo evidência toda `None` + `extras["conviction_read_failed"]`, no molde de `read_creator_flow`
  (`admission_context.py:100-107`). Alternativa de custo zero: curto-circuitar quando `enabled=False`.

## 2. Flag ON — tamanho, tetos, auditoria, pó

- **Nunca sobe.** Multiplicadores em `(0, 1]` por construção (`conviction.py:82`), `cap = min(pedido, trade_cap)`,
  `sized = cap × Π` (`conviction.py:331-332`); o motor então toma o mínimo dos tetos (`sizing.py:173`) ⇒
  `sol_final ≤ sized ≤ cap`. Check 19 (`fee_caps_check`, `checks_wallet.py:86`) usa `proposal.requested_sol` = o
  dimensionado (mais estrito); `daily_cap`, `participation`, `impact`, `available` são tetos independentes do
  pedido (`sizing.py:75-141`); checks 21–25 medem `final`; `max_sol_cost_sol = final × (1+slip)` (`sizing.py:201`).
- **A4 — `conviction_read.py:129-131` + `sizing.py:73,171-175` — MÉDIO (auditoria) — `binding_constraint`
  esconde a política.** Com ON e produto 1,0, `requested_sol` vira `min(pedido, trade_cap)`: mesa pede 0,5, teto
  0,28 ⇒ o limitante muda de `trade_cap` para `requested` (empate, `tied_limits=[trade_cap]`); com desconto, diz
  `requested` quando foi a escada. Sonda B: `applied True, requested_sol handed to engine 0.28`. A coluna
  `binding_constraint` do desk (`apps/api/hunter_api/services/meme_live.py:186`) e qualquer R-study agrupando por
  ela atribuem à mesa um clamp que é da política. Fix: novo `LimitCap("conviction", sol=sol_sized)` em
  `CAP_ORDER` depois de `trade_cap`, mantendo `requested_sol` original — limitante honesto, `sizing.requested_sol`
  intacto. (Isso empurra a escada para `hunter_risk_meme`; ela já é pura, a evidência entra como argumento —
  contrato preservado.)
- **A5 — `conviction.py:336` + `limits.py:178,305-321` — MÉDIO — `MEME_MIN_TRADE_SOL` não existe.**
  `min_trade_sol` é o 0,001 do preset e `limits_from_env` não lê variável nenhuma para ele;
  `docs/ACTIVATION.md:937` cita uma variável inexistente. Com o clamp do escopo (`entries.py:162`,
  `requested_cap_sol`) um restante de 0,07 × 0,25 = **0,0175 SOL é enviado** (sonda C: `mult 0.25 sized 0.0175
  refusal None applied True`); custos fixos (rent 0,00204 + taxas) ≈ 12 % da ordem; check 19 relativo
  (0,000875) ≫ piso da fee (0,00002) ⇒ passa. Fix: recusar `conviction_too_low` quando
  `sized < max(min_trade_sol, k × fixed_costs)` e/ou um `min_trade_sol` de verdade no perfil live (número do
  Everton, não nosso).

## 3. `entry_after_drop`

- **Fonte e unidade.** `real_sol_now` = leitura RPC `confirmed` desta admissão (`admission.py:126`,
  `chain.py:111`), lamports/1e9; pico = `meme_curve_snapshots.real_sol_reserves` `numeric` em SOL
  (`hunter_exchanges/pumpfun/normalize.py:252,309` `raw_lamports_to_sol`). Unidades consistentes — verificado.
- **Pico velho recusando errado.** Janela por `observed_at ≤ now` (`conviction_read.py:54`); uma linha REST com
  `observed_at` = hora do fetch mas reservas em cache coloca um máximo velho "dentro" dos 60 s ⇒ recusa falsa.
  Direção conservadora (perde a célula +0,566 R da KB-0118), limitada ao atraso do REST. Aceitável.
- **A2 — `conviction.py:291-301` — ALTO (para ligar) — uma foto só, depois da queda, passa a × 1,0.** O pico é
  `max` das fotos na janela; se a única foto (`peak_points=1`) é pós-queda, `peak ≈ now`, `dd ≈ 0` ⇒
  `within_window`. Sonda A: `within_window mult 1 sized 0.28`. É exatamente a borda da KB-0118 (soly/COVER/Punch:
  −94/−97 % com o radar chegando tarde). A feature registrada `recent_drawdown_pct` v1
  (`hunter_indicators/meme/drawdown.py:16-25`; `lab_repo_drawdown.py:32-35`) nomeia isso `too_few_points` e a
  porta lê como `recent_drawdown_unknown` fechado; o executor reimplementa a mesma regra congelada com modo de
  falha mais fraco — duas definições de uma feature. Fix mínimo: `peak_points < 2 ⇒ peak_unknown`; certo:
  reutilizar `recent_drawdown` com lookback 120 s e recusar quando idade do pico ≤ 60 s.
- **A3 — `peak_unknown` × 0,5 (`conviction.py:292-296`) — minha posição.** Só é fail-closed em combinação (precisa
  de mais um desconhecido para bater no piso). Um mint com linha de 15 s ≤ 120 s mas sem foto de curva em 60 s é
  um mint que a via rápida **largou** no último minuto — isso é sinal, não ausência. Ligada, deveria recusar
  (`drop_unknown`), coerente com a porta; × 0,5 só se o Everton decidir assim, e então com A2 fechado.
- **Laço quente?** Não no tick de 1 s: `_CANDIDATES` (`repo.py:106-107`) exclui proposta com linha de ordem e
  `reject_if_auto` marca a proposta rejeitada; reavaliar exige proposta nova da mesa (~20 s) ⇒ ≤ 3 admissões/min/
  mint, cada uma com 3 RPC + ATA do criador + leitura on-demand de risco + 5 consultas. Carência de 30 s para
  `entry_after_drop` é barata e fica abaixo dos 60 s da KB-0118 (não 120 s).

## 4. Auditoria: `approved = true` com recusa da escada

- **A9 — `apps/api/hunter_api/services/meme_live.py:183-184` + `entries.py:199-201` — MÉDIO.** A linha sai
  `status=refused, reason=entry_after_drop, admission_approved=true, first_refusal=null`. O desk mostra uma recusa
  "aprovada pelo motor sem recusa"; um R-study que classifica por `first_refusal`/`checks[].refusal` (o próprio
  vocabulário da API, `schemas/meme_live.py:79`) conta a ordem como aprovada pelo motor ou a descarta. Onde a flag
  deve viver: **dentro da decisão**, como check 26 `conviction` (`refusal = entry_after_drop |
  conviction_too_low`), para `approved=false` por construção e `first_refusal` nomear — isto é, a escada entra em
  `hunter_risk_meme` como insumo + check + teto (junta com A4). Remendo mínimo aceitável: em `entries.py:199`,
  `admission["approved"] = False` e anexar um check sintético antes de `_refuse`.

## 5. Fixes, em ordem

1. A1 `conviction_read.py:111` — guardar a leitura (ou curto-circuitar com flag off). Antes de qualquer deploy.
2. A2 `conviction.py:291` — `peak_points < 2 ⇒ peak_unknown` / reutilizar `recent_drawdown`. Antes de ligar.
3. A4+A9 — escada como check 26 + teto `conviction` em `hunter_risk_meme` (`sizing.py:33`, `evaluate.py:64`);
   `entries.py:199-201` some. Antes de ligar.
4. A5 `conviction.py:336` — piso contra custos fixos; corrigir `docs/ACTIVATION.md:937`. Antes de ligar.
5. A3 — decisão do Everton (recusa × desconto); carência 30 s para `entry_after_drop` em `refusal_cooldown.py:40`.
