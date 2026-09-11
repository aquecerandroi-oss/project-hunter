---
tags: [knowledge, nota, shadow-lab, diagnostico, latencia, instrumento, m3]
tema: a continuação da campanha de latência da KB-0087 — concorrência sozinha parou de comprar vazão porque o teto virou CPU de um processo Python só (GIL), e a correção passou a ser sharding por processo, cache de contexto e redução do próprio universo de decisão
fonte: dado próprio da VPS e local — `docker stats`, `pg_stat_activity`, `cProfile`, benchmark sintético e testcontainer (T3.74e, T3.74f, T3.74g, T3.82)
fonte_url: —
lido_em: 2026-09-11
as_of: "2026-09-11T08:15:00Z"
read_at: "2026-09-11T08:15:00Z"
evidencia: "?"
hipotese_testavel: "não — é diagnóstico de instrumento e a correção do próprio Lab, não candidata de estratégia"
astra: pendente
status: arquivada
owner: sexta-feira
updated: 2026-09-11
confiança: "?"
---

# O teto de CPU de um processo só: por que a concorrência parou de ajudar, e as três correções seguintes

> **Arquivada pela Sexta-feira em 2026-09-11 (plantão de arquivamento)** a partir de
> `.claude/state/notes-T3.74e.md`, `-T3.74f.md`, `-T3.74g.md` e
> `.claude/state/brief-T3.82-universo-de-pesquisa.md`/`obsidian/06-DECISIONS/2026-09-10-universo-de-pesquisa-90-dias.md`.
> Não editei nenhum número abaixo além de organizar a nota nesta forma; toda proveniência está nos
> arquivos de origem. Esta nota é a **continuação** da
> [[KB-0087-o-atraso-de-decisao-e-as-tres-correcoes|KB-0087]]: aquela fechou três causas (despacho
> serial, replay no worker vivo, flush de 1,0 s) medidas até o deploy `e81d53e` (15:25 BRT de
> 2026-09-10); esta cobre o que a releitura pós-deploy achou de **novo** na mesma noite — uma quarta
> causa que a KB-0087 não tinha medido. Nada aqui é dinheiro real (`ENABLE_LIVE_TRADING=false`).
>
> **Veredito em uma linha:** subir a concorrência de um processo `asyncio` só resolve enquanto o
> trabalho é I/O-bound; a partir do ponto em que ele passa a ser CPU-bound (GIL), mais concorrência
> não move o tempo de parede — a correção que funciona é dividir o trabalho entre **processos**
> (sharding) e, separadamente, **cortar o próprio trabalho** (cache de contexto, universo menor). Com
> os três no ar, `decision_lag_p50_s` caiu a **2,2 s** na mesma noite (medido pela T3.84 na manhã
> seguinte — `.claude/state/brief-T3.84-lote-diario-5min.md`).

## O que afirma

1. **A correção da KB-0087 (`BarDispatcher`, concorrência 8) não bastou na prática, mesmo depois de
   implantada.** T3.74e mediu, 14 minutos após o deploy `e81d53e`: uma amostra estreita do heartbeat
   ainda reportava `decision_lag_p50_s 54,1`; uma consulta mais ampla contra `agent_signals` mostrou
   que a "banda fixa de 55 s" da amostra era só a cauda alta de um espalhamento de **4,9 a 61,2 s**
   dentro da mesma barra — o `BarDispatcher` drena só `worker_concurrency` (8) mercados por vez
   contra uma rajada real de ~200 fechando juntos a cada fronteira de 15/30/60 min (~325 s de
   trabalho total por rajada, medido ao vivo). Correção proposta: `worker_concurrency` 8 → 32,
   projetando ≈ 10 s. **Não implantada por esta tarefa.**
2. **A projeção de ~10 s não se confirmou: o teto virou CPU de um processo Python só, não o pool de
   conexões nem o Postgres.** T3.74f mediu duas rajadas reais (16:45 e 17:00 BRT): `hunter-
   strategy-worker-1` preso em **97–100 % de um núcleo** pelos 36–100 s inteiros de cada rajada,
   enquanto `hunter-postgres-1` (12 núcleos) ficava em 20–25 % de uso sustentado, com
   `pg_stat_activity` mostrando 17 backends `active` + 14 `idle in transaction`, **todos esperando o
   cliente** (`wait_event_type=Client`) — só 1 backend de fato executando algo. O custo por estágio
   (inclusive `context_load`, que é I/O) **piorava** com o tamanho da rajada (0,13 s → 0,55 s →
   0,93 s), a assinatura de contenção de CPU sob o GIL, não de um Postgres ficando mais lento.
   Provado em bancada local sem Docker (`test_shard_cpu_benchmark.py`): concorrência 32 sobre carga
   deliberadamente presa a CPU não move o tempo de parede (~1,0×); 4 processos reais batem a mesma
   carga em **2,2–3,8× menos tempo**. Correção: `STRATEGY_SHARDS=N`, a mesma fatia
   `crc32(symbol) % N` que o `market-worker` já usa (movida para `hunter_core.sharding`, nunca
   rederivada), com grupo consumidor e heartbeat por shard. Testcontainer prova decisões
   byte-idênticas e zero duplicatas entre uma topologia de 1 grupo e uma de 4. Deploy usa
   `STRATEGY_SHARDS=4`. Hotfix no mesmo dia: 4 shards × pool 20+20 estourava
   `max_connections=100` do Postgres — cada shard passou a pool 5+5.
3. **Mesmo com 4 shards, uma barra ainda levava 37–43 s — o problema seguinte era o custo por
   avaliação, não mais o paralelismo.** T3.74g perfilou uma barra (50 mercados × 10 versões,
   `cProfile`, sem Docker): **59 % do tempo era Pydantic revalidando `NormalizedCandle`** a cada
   `StrategyContext` construído — 1 182 000 execuções por barra, porque cada versão remontava o
   contexto sobre a **mesma** janela do mesmo mercado; 39 % era `strategies/aggregate.py` repetido
   por versão. Correção: `bar_context.py` faz uma leitura, uma montagem e uma validação por
   (mercado, barra), servindo a cada versão uma fatia já validada. Medido: **13,1 → 8,6 ms** de CPU
   por avaliação (~1,3–1,9×) e **12 → 3** idas ao banco/Redis por barra. Decisões idênticas provadas
   por igualdade de objeto em unidade e Postgres real; `code_ref` dos módulos congelados e o replay
   ficaram intocados.
4. **O que sobrava depois das três correções de mecanismo era o próprio tamanho do universo — e essa
   foi resolvida separadamente, por decisão de produto, não de engenharia.** A T3.74g nomeou:
   `aggregate` repetido entre variantes que compartilham parâmetros (exigiria família nova) e "o
   universo do sombra decidindo sobre 200 mercados quando só 16 têm 90 dias de histórico real
   (~8× de custo evitável)". O Everton aprovou (T3.82, "boaaa perfeito", ~19:1x BRT de 2026-09-10):
   o universo de pesquisa do Shadow Lab passa a ser "mercados com ≥ 90 dias de `candles_1m`" — 16 de
   200 hoje. Redução projetada de avaliações por fechamento de 15 min: ~2.000 → ~160 (~92 %). Não
   muda versão, `code_ref`, limite de risco nem o universo executável da carteira.
5. **Com os quatro deploys da noite no ar (concorrência 32 supersedida por sharding, `STRATEGY_
   SHARDS=4`, cache de contexto — não confirmado se já implantado nesta janela — e o universo de 90
   dias), o `decision_lag_p50_s` caiu a 2,2 s**, medido pela T3.84 na madrugada seguinte
   (`.claude/state/brief-T3.84-lote-diario-5min.md`) — o número que satisfez a condição que o
   Everton tinha posto em 09/09 para liberar o experimento de 5 minutos ("decisão em menos de 5 s").
   Nenhuma das quatro tarefas releu a produção isoladamente após seu próprio deploy — o número de
   2,2 s é a leitura conjunta, não a atribuição de quanto cada correção contribuiu.

## Onde foi mostrado

VPS de produção (`hunter-vps`), `strategy-worker`/Postgres, medições entre 2026-09-10 18:42Z e
2026-09-10 21:02Z (15:42–18:02 BRT) para T3.74e/f, perfil local (sem Docker) para T3.74g, e a
releitura de `hb:strategy:shadow` pela T3.84 na madrugada de 2026-09-11.

## Como mediríamos aqui (já sabemos o quê; falta decompor)

`hb:strategy:shadow:{i}of{N}` por shard, agregado em `GET /api/v1/system/latency`
(`decision_lag_p50_s`/`p95_s`); `hunter_shadow_stage_seconds{stage}` para separar quanto do ganho
veio do sharding contra quanto veio do cache de contexto; contagem de avaliações por fechamento
(`heartbeat.universe_size` × versões vivas) para confirmar a redução de ~92 % da T3.82.

## Hipótese testável no Lab

Nenhuma — é correção de instrumento (o Lab decide mais rápido, não decide diferente).

## Por que pode falhar

- **32 é calibrado pelo trabalho medido numa rajada, não uma constante universal** — se o roster de
  versões crescer, o cálculo `trabalho_total / concorrência` (ou `/ shards`) precisa ser refeito
  (já registrado como risco pela própria T3.74e).
- **O ganho do `bar_context.py` não foi medido na VPS real** (Postgres em carga real, 200 mercados
  antes da T3.82, janelas de até 6.000 min) — só local, sem Docker.
- **O número de 2,2 s soma quatro correções sem decompor a contribuição de cada uma** — se uma
  regredir (por exemplo, o TTL de 1 h do cache de universo deixando um mercado novo entrar tarde),
  não há como saber, só por este número, qual causa voltou.

## Segunda opinião (Astra)

Não registrada em nenhuma das notas de origem (T3.74e/f/g) — nenhuma delas cita revisão da Astra
sobre o mecanismo em si. Fica como lacuna declarada, não como "concorda"/"discorda" fabricado.

## Relacionados

[[KB-0087-o-atraso-de-decisao-e-as-tres-correcoes]] · [[06-DECISIONS/2026-09-10-universo-de-pesquisa-90-dias]] ·
[[Diario/2026-09-10]] · [[Diario/2026-09-11]] · [[07-BUGS/Open Bugs|Open Bugs]] ·
`docs/PIPELINE.md` §6b (Shadow Lab) · `docs/DEPLOYMENT.md` §3.1b/§5.2

## Fontes

`.claude/state/notes-T3.74e.md` · `.claude/state/notes-T3.74f.md` · `.claude/state/notes-T3.74g.md` ·
`.claude/state/brief-T3.82-universo-de-pesquisa.md` ·
`obsidian/06-DECISIONS/2026-09-10-universo-de-pesquisa-90-dias.md` ·
`.claude/state/brief-T3.84-lote-diario-5min.md` (o número de 2,2 s)
