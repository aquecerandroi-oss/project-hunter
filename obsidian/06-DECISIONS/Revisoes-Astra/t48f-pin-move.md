---
tags: [revisao-astra, meme, pumpfun, executor, guarda, pino]
date: 2026-10-05
updated: 2026-10-05
status: registro
owner: sexta-feira
decided_on: 2026-10-05
by: risk-engine-guardian + astra
tarefa: mover o pino da identidade do programa pump para o deploy de 02/10 (slot 452654932)
veredito: APPROVE com condições — o pino pode subir; religar entradas pump/launch, não
---

# Pino da T4.8f — aprovado, entradas continuam presas pelo escopo

**O que muda:** `EXPECTED_PUMP_PROGRAM` passa para o deploy de 02/10 15:47:21Z (slot 452654932). O hash da IDL fica igual ao da T4.8c pela terceira vez, porque a conta da IDL não mudou. A mensagem de upgrade vira "regravar T4.8g". Depois do deploy, o executor sai do modo só-saídas.

**Guardião (APPROVE):**
- O diff é idêntico ao patch preparado na [[T4.8f-pumpswap-guard]].
- As fixtures citadas existem e foram decodificadas de novo.
- A guarda de PumpSwap e `pfeeUx` segue ativa (`watched_divergence`, pegajosa, relida pelo `pre_sign_gate`).
- Nenhum módulo de saída lê o bloqueio de programa.
- Testes: `1922 passed, 130 skipped` (adapters + executor).

**Condições (F1, MÉDIA):** o deploy do pino só vale enquanto o escopo pump estiver esgotado. Lido na VPS em 05/10 23:55Z: `small_test_below_min=full`, `launch_lane_mode=off`. Para subir o escopo é preciso:
1. o teste Postgres de fechamento único **visto verde** e com variante PumpSwap. Hoje ele nunca rodou: o Docker local está fora e o `python-test` do CI está vermelho desde 01/10;
2. a decisão do Everton sobre compras cashback.

**Abertos (LOW):**
- A simulação mainnet citada no docstring não tem artefato versionado (F2).
- Comentários de teste desatualizados ("Both older deploys").

**Astra:**
- **Concorda:** pino consistente com as fixtures (decodificou cabeçalho, horário e IDL por conta própria); saídas intactas; guarda das três contas válida.
- **MUST-FIX (ALTA):** a prova Postgres antes de novas entradas. Foi reconciliado como condição do religamento, não do pino. Ela mesma escreve que o pino "não equivale a aprovar religamento irrestrito".

Fonte: `.claude/state/astra-review-t48f-pin-move.md`.

[[Open Bugs]] · [[T4.8e-decoders]] · [[T4.8f-pumpswap-guard]] · [[2026-10-05]]

Seguido pelo redeploy de 08/10: [[T4.8g-upgrade-08-10]] (o pino de 05/10 vale até esse patch ser aplicado; as condições de religamento continuam e ganharam uma).
