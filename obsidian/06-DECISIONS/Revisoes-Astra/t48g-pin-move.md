---
tags: [revisao-astra, meme, pumpfun, executor, guarda, pino]
date: 2026-10-08
updated: 2026-10-08
status: registro
owner: sexta-feira
decided_on: 2026-10-08
by: risk-engine-guardian + astra
tarefa: mover o pino da identidade dos três programas para o redeploy de 08/10 (pump 454596459, PumpSwap 454596406, taxas 454596501)
veredito: APPROVE com condições — o pino pode subir; reabrir compras pump/launch, não
---

# Pino da T4.8g — aprovado, entradas continuam presas pelo escopo

**O que muda:** `EXPECTED_PUMP_PROGRAM` vai para o slot 454596459 e a vigia da PumpSwap e das taxas para 454596406 e 454596501. A IDL é a mesma pela quarta vez. A mensagem de upgrade vira "regravar T4.8h". O executor sai do modo só-saídas no próximo reinício, porque a divergência fica guardada em memória.

**Guardião (APPROVE):**
- O diff é idêntico ao patch preparado.
- Os slots e a autoridade foram relidos ao vivo na cadeia (slot 454650403): não houve novo redeploy.
- A vigia segue estrita nos três programas, e nenhuma saída lê o bloqueio.
- Testes: `2191 passed`.
- **Fato novo:** o teste Postgres de fechamento único (curva) rodou verde pela primeira vez: `1 passed`. Falta a variante PumpSwap.
- Nos 13 trades reais depois do redeploy, a variação de lamports da curva bate com ±`sol_amount` (resíduo 0).
- Nenhum detentor foi achado para simular a venda numa curva antiga de 151 B.

**C1, vale agora:** o pino só se sustenta com `small_test_below_min=full` e `launch_lane_mode=off`. Depois do deploy, conferir no heartbeat: `program_mode=normal` e `program_block` vazio.

**C2, antes de subir o escopo ou reabrir compras pump/launch:**
1. A reserva de compra precisa incluir o crescimento da curva (+76 200 lamports), com teste de fronteira (`scope.py:96`).
2. A variante PumpSwap do teste de fechamento único precisa ser vista verde.
3. Decisão do Everton sobre compras cashback. Ou elas ficam recusadas, ou é preciso simular a venda numa curva cashback de 151 B.
4. Simular a venda de curva de token SPL clássico.

**Astra:** aprova o pino restrito sem must-fix. Corrigiu dois raciocínios do guardião: o `min_sol_output` é o líquido depois da taxa, e o piso da tesouraria não é uma reserva garantida. O docstring do cashback foi corrigido neste commit.

Fonte: `.claude/state/astra-review-t48g-pin-move.md`.

[[T4.8g-upgrade-08-10]] · [[t48f-pin-move]] · [[Open Bugs]] · [[2026-10-08]]
