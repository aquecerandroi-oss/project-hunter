# Brief T2.5e — cobertura do tape: "em dia" não pode exigir fila exatamente vazia

**Owner:** exchange-integration-specialist. **Não commitar.** **Regra operacional: nunca Bash em background; comandos em primeiro plano com timeout ≤ 5 min; suítes com testcontainers por arquivo.** Despachar **depois** que a T2.5-backfill (consumidor de `market.backfill.requested`) sair de `services/market-worker/**`.

## Sintoma medido (2026-09-06, VPS e local)
Depois de `4bb2865` (T2.5-adapter), `mkt:coverage:binance` fica vazio/congelado e o market-worker loga `tape_coverage_interval_broken reason=queue_backlog` a cada ~1 min (VPS 21:24–21:40Z, 8 quebras). A T2.5c mediu no local: **100 % das avaliações da janela de 30 min saíram `uncovered`** com o tape fresco. Consequência: `trade_velocity`/`buy_pressure` indisponíveis, nenhum EARLY publica, e o Radar perde os componentes de tape — o oposto do que a T2.5-adapter queria.

## Hipótese a confirmar primeiro
`CoverageTracker` só considera "em dia" quando `enqueued == delivered + evicted` **no instante do stamp**. Sob fluxo contínuo (150 msg/s, 200 mercados), há quase sempre um item entre `append` e `yield`, então a igualdade exata é rara e o tracker quebra por `queue_backlog` o tempo todo. Se confirmada (teste que reproduz com um produtor contínuo e um consumidor que acompanha), a regra passa a ser **atraso limitado**, não fila vazia: em dia = `enqueued − delivered − evicted ≤ N` **e** idade do item mais antigo na fila ≤ `COVERAGE_SAFETY_S` (0,5 s) — o marcador de progresso continua sendo o entregue, e o `covered_until` avança até `delivered` menos a margem, nunca até `enqueued`. Um backlog que cresce sem limite continua quebrando por `queue_backlog`; uma reconexão continua quebrando por `reconnect` e reiniciando a sessão (nada da T2.5-adapter é desfeito).

## Entregar (`packages/exchange-adapters/hunter_exchanges/binance/event_queue.py` só se precisar expor a idade do item mais antigo; `services/market-worker/hunter_market_worker/{coverage,streaming}.py`; testes; `.claude/state/notes-T2.5.md` seção nova)
1. Teste de reprodução: produtor contínuo + consumidor que acompanha → com a regra atual, quebra em quase todo stamp; com a nova, não quebra e `covered_until` avança sem ultrapassar o entregue.
2. Teste de honestidade: consumidor que fica para trás (fila crescendo) → quebra por `queue_backlog`; item parado > 0,5 s → congela.
3. Teste de reconexão inalterado (os da T2.5-adapter continuam verdes).
4. Prova de 15 min contra o stack local: `mkt:coverage:binance` avançando, % de avaliações `covered` no scanner, e no VPS depois do deploy.
Comandos e PATH como nas outras tarefas; Astra antes e depois (`bash infra/scripts/astra.sh ask T2.5e-coverage "..."`). Relatório em português no formato estendido com saída real.
