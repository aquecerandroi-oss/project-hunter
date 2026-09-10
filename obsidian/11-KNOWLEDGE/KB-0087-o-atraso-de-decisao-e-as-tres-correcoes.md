---
tags: [knowledge, nota, shadow-lab, diagnostico, latencia, instrumento, m3]
tema: o atraso decisão-menos-barra (2 s → 125 s) tinha três causas independentes — despacho serial de ~200 velas/minuto, o replay disputando CPU/pool com a linha viva, e o lote de flush de vela esperando 1,0 s fixo — e as três já têm correção medida
fonte: dado próprio da VPS e local — `hb:strategy:shadow`, `docker stats`, `pg_stat_activity`, benchmark sintético e testcontainer
fonte_url: —
lido_em: 2026-09-10
as_of: "2026-09-10T18:53:00Z"
read_at: "2026-09-10T18:53:00Z"
evidencia: "?"
hipotese_testavel: "não — é diagnóstico de instrumento e a correção do próprio Lab, não candidata de estratégia"
astra: pendente
status: arquivada
owner: sexta-feira
updated: 2026-09-10
confiança: "?"
---

# O atraso de decisão: de onde vinham os segundos, e as três correções

> **Arquivada pela Sexta-feira em 2026-09-10 (plantão de arquivamento, tarde)** a partir de
> `.claude/state/notes-T3.74c.md` (+ §8, T3.74d), `.claude/state/notes-T3.80.md`,
> `.claude/state/notes-T3.81.md` e `.claude/state/notes-T3.79.md`. Não editei nenhum número abaixo
> além de organizar a nota nesta forma; toda proveniência está nos arquivos de origem. Nenhuma das
> três correções tinha sido relida em produção no momento em que estas notas foram escritas — o
> "antes" é medição real da VPS, o "depois" é benchmark sintético/testcontainer local até alguém
> reler a mesma janela depois do deploy `e81d53e` (15:25 BRT, ver [[Diario/2026-09-10]] §6–§7). Nada
> aqui é dinheiro real (`ENABLE_LIVE_TRADING=false`).
>
> **Veredito em uma linha:** o atraso decisão-menos-barra que a [[KB-0083-uma-hora-de-34-r-deriva-e-impulso|KB-0083]]
> media crescendo (2,0 s no início de setembro → 107,9 s em 09/09 → 125,1 s em 10/09) tinha **três**
> causas medidas independentemente, nenhuma delas o preço fugindo da zona de entrada — e as três já
> têm correção com prova local, implantadas juntas no deploy `e81d53e`.

## O que afirma

1. **Causa dominante: despacho serial de ~200 mercados fechando a vela quase no mesmo segundo, um
   por vez, num processo `asyncio` de um núcleo só.** Medido na VPS (T3.74c, 2026-09-10 15:01–15:04
   BRT): CPU do `strategy-worker` em rajada de **92,7 %** de um núcleo (caindo a 16 % pouco depois),
   `lag=303` entradas atrás do próprio grupo consumidor do Redis (`strategy-worker.shadow`), sem
   nenhum replay concorrente rodando naquele instante — a linha viva sozinha já produzia o sintoma.
   Correção: `BarDispatcher` (`services/strategy-worker/hunter_strategy_worker/dispatch.py`) —
   mercados diferentes em paralelo (`SHADOW_WORKER_CONCURRENCY=8`), barras do **mesmo** mercado
   sempre em série. Benchmark sintético local (11 versões-equivalente × 200 mercados, 10 ms/barra):
   mais de **4×** de vazão contra o despacho serial. Decisões byte-idênticas serial vs. concorrente
   provadas contra Postgres real (testcontainer, 15 combinações de mercado × versão). T3.74d fechou
   um achado HIGH da revisão: sem uma guarda de deduplicação, a reentrega automática do Redis
   (`XAUTOCLAIM`, disparada por `SHADOW_CLAIM_IDLE_MS`) reprocessava a mesma barra em paralelo com
   ela mesma durante a rajada — corrigido com `already_in_flight` e um `claim_idle_ms` derivado de
   `concorrência × custo por barra`.
2. **Segunda causa, medida em paralelo: o replay de pesquisa rodava dentro do mesmo contêiner e
   processo da linha viva, disputando o mesmo núcleo e o mesmo pool de conexões Postgres.** O T3.76
   mediu, com três variantes novas `active` (14 versões avaliadas por barra em vez de 11), o
   `consumer_lag` do replay chegando a **653** contra o teto de 100 do portão que o pausa — um fator
   de 6 acima do limite, em parte pelo próprio replay da tarefa disputando o único núcleo. Correção
   (T3.80): `replay-worker` como **serviço próprio** (mesma imagem, `profiles: ["replay"]`, sem
   `HUNTER_ROLE`, pool de **2** conexões contra 5+5 do worker vivo, 3 vCPU/2 GB); `run.py` recusa
   rodar dentro do worker vivo (`role_guard`, checado antes de qualquer parsing de argumento); o
   portão de pausa do replay ganhou o motivo `decision_lag` (lido do heartbeat, p50 > 10 s ou p95 >
   30 s, com histerese de 5 min de leituras sãs). Prova local (processo do SO separado, mesmo
   Postgres do testcontainer, 3 conexões de contenção real): dreno vivo com replay concorrente rodou
   em p95 **3,33 s** — bem abaixo do teto de 20 s.
3. **Terceira causa, menor mas real e uniforme: o lote de flush da vela esperava 1,0 s fixo desde o
   primeiro item do lote, e quem chegava depois do corte pagava outro segundo inteiro sozinho.**
   Medido por shard na VPS (T3.81, 4 shards do `market-worker`, 200 mercados perpétuos): p50 ≈
   **1,03 s** / p95 **3,5–4,1 s** em todos os quatro shards e em todos os minutos-da-hora — não é
   desbalanceamento de shard nem pico do refresh de universo de 15 min. A distribuição de chegada por
   segundo (60–75 % em T+1s, cauda até T+6/7s) confirma a assinatura "lote fixo de 1 s + straggler
   pagando de novo". Correção: `MARKET_CANDLE_FLUSH_MS` (padrão **200 ms**, mesma cadência do
   `tick_coalesce_ms`) substitui o piso fixo em `persist.py::drain_loop`. A contribuição do outbox
   (`created_at → dispatched_at`) é separada e tipicamente pequena (0,1–0,3 s, picos de 1–4 s só em
   minutos com rajada de recovery/backfill).
4. **O orçamento de ponta a ponta publicado (T3.79, `GET /api/v1/system/latency`) mediu as três
   causas antes de qualquer correção estar no ar**: `flush` `critical` (p50 1,03 s / p95 3,90 s
   contra alvo p95 < 1 s), `decisão` `critical` (p50 45 s / p95 180 s contra alvo mediana < 5 s / p95
   < 20 s), `ingest`/`admissão`/`fill` `unknown` (instrumentação nova sem histórico / `trade_
   proposals`/`orders`/`fills` com 0 linhas — a ponte de autonomia está desligada em produção).
5. **As três correções foram implantadas juntas no deploy `e81d53e` (15:25 BRT)**, mas nenhuma foi
   relida em produção por nenhuma destas tarefas — o "depois" ao vivo é o próximo passo declarado por
   todas as três (T3.74c §7, T3.80 §1.3, T3.81 §5).

## Onde foi mostrado

VPS de produção (`hunter-vps`), `strategy-worker`/`market-worker`/Redis/Postgres, universo de 200
perpétuos USDT monitorados na Binance, medições de 2026-09-10 entre 12:01 e 16:34 UTC (09:01–13:34
BRT). Nenhuma escrita na VPS por nenhuma das três tarefas; as correções existem só localmente
(unit + testcontainer + benchmark sintético) até a leitura pós-deploy.

## Como mediríamos aqui (já sabemos o quê; falta reler)

`hb:strategy:shadow` → `decision_lag_p50_s`/`p95_s` (campo novo do T3.74c, ainda não existia nas
leituras "antes"); a mesma consulta de `flush` por `candles.received_at` filtrada por `source='ws'`
(T3.79/T3.81); `GET /api/v1/system/latency` inteiro, na mesma janela horária do dia anterior ao
deploy, para comparar `status` trecho a trecho.

## Hipótese testável no Lab

Nenhuma — é correção de instrumento (o Lab decide mais rápido, não decide diferente). O que fica
como pergunta em aberto, registrada pelas próprias tarefas: se `decision_lag_p95_s` não cair para
< 20 s mesmo com o `BarDispatcher` em produção, o próximo corte é CPU pura dentro da rajada
(sharding em múltiplos processos, análogo ao `MARKET_SHARDS` do `market-worker` — T3.74c §4).

## Por que pode falhar

- O benchmark de vazão do T3.74c (4× de ganho) é **sintético** (custo simulado de 10 ms/barra), não
  2 200 avaliações reais contra Postgres — o ganho real depende de quanto do custo por barra é E/S
  (que o dispatcher explora) contra CPU pura (que ele não resolve).
- A prova do T3.80 (p95 3,33 s com replay concorrente) não reproduz o teto de CPU/memória do cgroup
  real da VPS (`deploy.resources.limits` do `replay-worker`) — é o cenário **mais** desfavorável que
  a produção real terá, não uma simulação exata dela.
- `SHADOW_LATE_DELAY_BACKLOG_MAX_S=120` (a válvula que já existia, T3.74c) pode disparar uma rajada
  curta de `late_delay_backlog` logo após o próprio deploy/restart do worker, sem que haja rajada de
  mercado nenhuma — não é um sinal de que o `BarDispatcher` está saturado, é esperado nesse instante
  (documentado no T3.74c §5 item 5).
- O ganho do `MARKET_CANDLE_FLUSH_MS=200ms` só foi provado com relógio falso (unit) e um caso de
  testcontainer — o número real de produção depende do padrão de chegada real, que pode diferir do
  medido antes da correção.

## Segunda opinião (Astra)

Não registrada em nenhuma das três notas de origem (T3.74c/d, T3.80, T3.81) — nenhuma delas cita uma
revisão da Astra sobre o mecanismo em si. Fica como lacuna declarada, não como "concorda"/"discorda"
fabricado.

## Relacionados

[[KB-0083-uma-hora-de-34-r-deriva-e-impulso]] · [[EXP-0026-regime-como-estrategia]] ·
[[Diario/2026-09-10]] · [[07-BUGS/Open Bugs|Open Bugs]] ·
`docs/PIPELINE.md` §6b (Shadow Lab) e §6c (replay) · `docs/DEPLOYMENT.md` §5.2 · `docs/ACTIVATION.md` §7

## Fontes

`.claude/state/notes-T3.74c.md` (+ §8 T3.74d) · `.claude/state/notes-T3.80.md` ·
`.claude/state/notes-T3.81.md` · `.claude/state/notes-T3.79.md` · `.claude/state/notes-T3.76.md` §4
(o `consumer_lag` de 653 medido durante o replay do dia)
