You are backend-specialist (item 1) then quant-engineer (item 2) on PROJECT HUNTER
(repo C:\dev\project-hunter; absolute paths; VPS alias `hunter-vps`, `/opt/project-hunter`).

# Brief T3.74b — o portão de saúde não vê o próprio sintoma; o custo por barra continua N×M

**Contexto (`.claude/state/notes-T3.74.md`, leia primeiro):** T3.74 encontrou e fechou um código
morto real — `live_lane_degraded` (o portão que pausa o replay quando a linha viva está degradada)
existia, era testado e documentado como "checado antes de toda fatia", mas nenhum ponto de
`replay/run.py` o chamava. T3.74 ligou os dois pontos de entrada (`_drain`, `_main`) e provou com
teste que a chamada agora acontece antes de `take_next` (nenhum pedido é consumido e perdido).
**Mas o portão não enxerga o sintoma medido**: `hb:strategy:shadow` (o heartbeat que o portão lê)
publica `outbox_lag_s` e `evaluated_bars`, nunca o atraso decisão-menos-fechamento-de-barra que
T3.73/T3.74 mediram subindo de 2 s para 125 s — no instante da medição (2026-09-10 04:48 UTC =
01:48 BRT) `outbox_lag_s` estava em 0.0 e o heartbeat fresco, ou seja, o portão teria dito "saudável"
durante o pior período já medido. Ligar o portão foi a correção certa (fecha um bug real, documentado
e testado), mas não deve ser reportada como tendo resolvido o atraso.

## Deliver

1. **(backend-specialist) Ensinar o portão a ver o próprio consumidor.** `live_lane_degraded` ganha
   um terceiro motivo, `consumer_lag:<n>`, lendo `XINFO GROUPS` do stream `market.candles.closed`
   grupo `strategy-worker.shadow` (nomes em `hunter_strategy_worker/consumer.py`/`config.py`) — o
   campo `lag` já existe no Redis (medido em T3.74: 69 agora) e é exatamente o número que faltou.
   Limiar novo (`REPLAY_CONSUMER_LAG_MAX` ou similar, no padrão dos outros `REPLAY_*` de
   `budget.py`). TDD: teste com `_FakeRedis` estendido (adicionar `xinfo_groups`), unitário, sem
   banco. Mesma disciplina de `budget.py`: pura, sem side effect além da leitura.
2. **(quant-engineer + backend-specialist, arquitetural — não implementar sem design doc)** O custo
   por barra é N (versões devidas) × M (mercados) e cada avaliação de `evaluate_slot` relê o contexto
   inteiro (`build_market_context`, até `SHADOW_CONTEXT_MAX_MINUTES` = 6000 min) sem cache entre
   versões da mesma família no mesmo (mercado, fechamento de barra) — medido em `context.py`/
   `decide.py` (T3.74 notes §2c). Com 11 versões ativas e 200 mercados perpétuos monitorados, isso é
   até 2200 leituras de candle por fechamento alinhado. Desenhar (doc em `docs/plans/` antes de
   codar): cache de contexto por `(exchange, symbol, source_bar_close, timeframe)` compartilhado
   entre versões da mesma família (mesmos parâmetros de janela), invalidado a cada barra — sem mudar
   nenhuma decisão (mesmo anti-look-ahead, mesmo corte). Astra opina antes da aprovação por tocar o
   caminho que decide.
3. **(devops-engineer, opcional, mais barato de medir que 2)** `docker stats` mostrou
   `hunter-postgres-1` picar a 178 % de CPU num instante sem replay rodando (04:3x UTC 10/09) — a
   linha viva sozinha já pressiona o Postgres. Levantar `pg_stat_statements` (ausente hoje — só
   `plpgsql` instalado) para poder medir custo por query em vez de amostrar `pg_stat_activity` às
   cegas, antes de decidir se o Postgres precisa de mais vCPU ou de índice.

## Regras
Mesmas do T3.74: nunca reiniciar/recriar contêiner, nenhuma escrita na VPS, nenhum parâmetro de
versão viva tocado, `timeout 290` em todo comando remoto, testcontainers um arquivo por vez, não
commitar. `ruff`/`pyright`/`check_file_size.py` limpos nos arquivos tocados.
