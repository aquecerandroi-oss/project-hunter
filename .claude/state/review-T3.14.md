# Revisão adversarial — T3.14 ponte shadow → admissão + T3.5b (`12edda3`) — NADA BLOQUEIA (code-reviewer, 2026-09-07)

79 testes rodados. Flag lida uma vez no boot; com `false` nenhum caminho cria grupo nem submete. `purpose != "live"` recusa (nulo/desconhecido inclusive). β válido = 3 condições. Score da barra fonte (`opportunities.last_updated_at <= source_bar_close`), sem look-ahead; ordem total com desempate por `signal_id`. Ordem de travas idêntica nos três ciclos. Sem float/now()/sleep; módulos ≤ 332.

## DEVE CORRIGIR antes de ligar `ENABLE_PAPER_AUTONOMY` (→ T3.14b, depois da T3.5c)
1. `bridge_screen.py:104-112` — `bridge_candidate_refused` (log + contador) em toda passada para o mesmo sinal dentro dos 240 s de lookback (~240 incrementos por sinal recusado): deduplicar por (sinal, motivo), mesmo padrão de `report_unreadable`.
2. `bridge.py::_submit` — teste com 2+ candidatos em que o topo é deferido por `spot_book_unavailable` e o vice **não** é promovido.
3. `bridge_screen.py:130-140` — teste do caminho `agent_unavailable` (agente existente não `enabled`).
4. `bridge_universe.py:57-83 spot_pair_for` — teste do mapeamento `1000SHIBUSDT` perp → `SHIBUSDT` spot por `base_asset_id` **e** prova de que um `entry_ref` ~1000× fora de banda é recusado pelo Risk Engine (`signal_validity`/`max_entry_deviation_pct`) antes de qualquer reserva.

## SUGESTÕES
5. `ENABLE_PAPER_AUTONOMY` lida por dois caminhos (`settings.py` e `execution-worker/config.py`): teste que trave os dois defaults.
6. `coin_commitment` escopado por carteira — depende de "uma principal por organização"; registrar.
7. Corrida consumidor × laço na mesma carteira só "por construção": replicar o padrão de `test_wallet_lock.py`.
