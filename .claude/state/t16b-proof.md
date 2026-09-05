# T1.6b — prova operacional contra a Binance real (2026-09-05, 21:00–22:50 UTC)

**Meta do plano (`.claude/state/review-T1.6.md`, item T1.6b):** 200 mercados com
`markets_ok ≥ 95%` e **CPU < 70% de um core por shard**.

**Veredito em uma linha: a meta é alcançável e foi alcançada — com 4 shards × 50 mercados
(`markets_ok` 198/200 = 99,0%, CPU média por shard 36,6%–64,2%) — mas essa topologia NÃO é a
que fica configurada**, porque com mais de um shard todos os processos escrevem a mesma chave
de heartbeat e a página System passa a mentir (§6.1). O que fica no ar é **um processo sobre os
50 maiores mercados**, medido em §5: `markets_ok` 50/50 = 100%. O caminho para 200 está provado
e escrito; falta o heartbeat por shard, que é follow-up do M2.

Como ler a métrica de CPU: a meta é sobre a **média** por processo em regime estável. Picos no
fecho do minuto (gravação do lote de velas) passam de 100% em todas as topologias, inclusive na
aprovada — isso está nos números abaixo e não é escondido.

Imagem usada: `hunter-api:dev` construída de `b8998cc` (e reconstruída após o conserto do §0).
Stack: `infra/docker/docker-compose.yml` + override; Postgres e Redis do Compose; Binance
USDS-M pública, sem chave.
---

## 0. O que a prova encontrou antes de conseguir medir qualquer coisa

### CRITICAL-2 — um símbolo em chinês cegava os 200 mercados

Ao subir a imagem nova com `MARKET_UNIVERSE_SIZE=200`, o worker não monitorou **nenhum**
mercado. Um traceback por ciclo de retry:

```
$ docker logs docker-market-worker-1 2>&1 | grep -A 8 Traceback | head -12
Traceback (most recent call last):
  File "/app/services/market-worker/hunter_market_worker/universe.py", line 240, in run_universe
    universe.set(shard_symbols(monitored, settings.shard_index, settings.shard_total))
  File "/app/services/market-worker/hunter_market_worker/universe.py", line 79, in shard_symbols
    return sorted(s for s in symbols if zlib.crc32(s.encode("ascii")) % shard_total == shard_index)
UnicodeEncodeError: 'ascii' codec can't encode characters in position 0-3: ordinal not in range(128)

$ docker logs docker-market-worker-1 2>&1 | grep -c market_universe_refresh_failed
(um por ciclo, ~12 s, durante 6 minutos; /ready 503 o tempo todo)
```

Causa: a Binance USDS-M lista perpétuos com **símbolo escrito em chinês**. Consultado ao vivo:

```
$ docker exec docker-market-worker-1 python -c "... exchangeInfo + ticker/24hr ..."
perp usdt trading: 526
rank 19 牛来USDT 239433470
rank 42 龙虾USDT 57304070
rank 63 币安人生USDT 30245422
rank 81 我踏马来了USDT 21477332
top200 cutoff volume: 3974512
```

Os quatro estão **dentro do top 100** por volume 24 h. `s.encode("ascii")` levanta
`UnicodeEncodeError` dentro do `try` de `run_universe`, que captura, loga e deixa o universo
vazio — ou seja, **um símbolo não-ASCII derruba os 200**, não só ele. O resto do pipeline já
lidava bem com esses símbolos desde antes:

```
$ psql -c "select m.symbol, count(*) from candles c join markets m on m.id=c.market_id
           where m.symbol !~ '^[ -~]*$' group by 1 order by 2 desc"
牛来USDT|1773
龙虾USDT|1773
我踏马来了USDT|1627
币安人生USDT|1625
```

A suíte não pegava porque `test_universe_sharding.py` constrói um universo sintético só de
ASCII — e o docstring do arquivo justificava isso ("este módulo não pode depender de uma
exchange ao vivo"). É a mesma lição da T1.6 (`EXPIRE` com float no Lua): **um dublê que não
reproduz a fronteira real esconde o defeito**.

Conserto e prova de que o teste pega o defeito (commit `4f9ab28`):

```
$ sed -i 's/utf-8/ascii/' universe.py && uv run pytest services/market-worker/tests/test_universe_sharding.py -q
5 failed, 10 passed in 1.42s
$ sed -i 's/ascii/utf-8/' universe.py && uv run pytest services/market-worker/tests/test_universe_sharding.py -q
15 passed in 1.15s
```

Depois do conserto, `market_universe_refresh_failed` = **0** e `/ready` = 200.

### HIGH e MEDIUM que vieram das revisões desta prova

Estão no mesmo commit `4f9ab28`, com o cenário de falha de cada um na mensagem: gramática de
canal WS recusando os símbolos unicode que o worker publica (preço congelado no detalhe de um
mercado top-20); segmentos de rota interpolados sem escape em `apps/web/lib/api/markets.ts`
(travessia de caminho até endpoints internos com o bearer do próprio usuário); estado por
canal nunca podado no `RealtimeHub` (memória do processo da API); e a comparação de URL crua
no e2e da T1.7.

---

## 1. Método

Três topologias, mesma imagem, mesmo universo (top 200 perpétuos USDT por volume 24 h),
medidas em sequência na mesma noite contra a Binance ao vivo:

| Corrida | Topologia | Janela UTC | Amostras |
|---|---|---|---|
| A | 1 processo, 200 mercados, 1.200 assinaturas | 21:06 → 21:28 | `docker stats` a cada 30 s (33) + 4 sondas |
| B | 2 shards × 100 mercados (`MARKET_SHARD=0/2`, `1/2`), 600 assinaturas cada | 21:30 → 21:48 | 33 amostras por shard + 4 sondas |
| C | 4 shards × 50 mercados (`0/4`…`3/4`), 300 assinaturas cada | 21:50 → 22:12 | 30 amostras por shard + 3 sondas + 12 amostras de regime estável |

A sonda (`.claude/state/tmp/measure_t16b.py`) roda **dentro do container `api`**, no mesmo
caminho de serviço que os handlers autenticados executam (`build_market_status`,
`MarketRepository.list_markets`, `build_market_list_page`, `scan_heartbeats`) contra o Postgres
e o Redis reais — as rotas exigem token Clerk e não há sessão de navegador aqui, exatamente
como na prova da T1.6.

Ela reporta **dois eixos separados**, porque falham por motivos diferentes:

- **hot state**: qualidade por componente (`ticker`, `book`, `mark`) e quantos mercados têm os
  três `ok` — é o que a T1.6b ataca;
- **`markets_ok`**: a métrica do plano, que também vira `degraded` com `ingestion_gap` aberto —
  ou seja, mistura capacidade com backlog de recovery.

## 2. Corrida A — um processo, 200 mercados: o hot state colapsa

`docker stats`, 33 amostras: **mín 98,4% · média 103,2% · máx 163,2%** de um core (195–292 MiB).

Sondas:

| as_of | ticker ok/stale/ausente | book ok/stale/ausente | mark ok/stale | 3 componentes ok |
|---|---|---|---|---|
| 21:11 | 127 / 72 / 1 | 122 / 57 / 21 | 21 / 177 | **8 (4,0%)** |
| 21:16 | 150 / 47 / 3 | 107 / 11 / 82 | 23 / 177 | **15 (7,5%)** |
| 21:21 | 0 / 0 / **200** | 0 / 0 / **200** | 0 / 200 | **0 (0,0%)** |
| 21:26 | 0 / 0 / **200** | 0 / 0 / **200** | 0 / 200 | **0 (0,0%)** |

Aos 15 minutos o hot state **desapareceu inteiro**: `ticker` e `book` ausentes nos 200 mercados
(as chaves expiraram porque o escritor não conseguia acompanhar), `mark` stale nos 200, idade
máxima 723 s. Idade do `mark` p50/p95/máx na sonda anterior: 52 s / 338 s / 540 s.

Pior: a série durável também ficou atrás. Velas persistidas na janela: 335.207 → 338.169 em
15,8 min = **188 velas/min**, abaixo das **200/min** que a exchange fecha. Gaps abertos caíram só
de 3.656 para 3.494.

**Veredito da corrida A: reprovada.** É o mesmo colapso da T1.6, agora medido com a
decomposição por componente.

## 3. Corrida B — 2 shards × 100 mercados: melhora, ainda insuficiente

CPU: shard 0 **média 107,2%** (mín 30,7 · máx 180,3); shard 1 **média 100,2%** (mín 65,7 · máx
142,9). Cada processo continua saturando um core.

Mercados com os três componentes `ok`: **26,5% → 44,5% → 5,0% → 30,5%** ao longo da janela —
oscilando, nunca perto da meta.

O que melhorou de verdade foi a vazão: velas 339.176 → 345.366 em 16,3 min = **380/min** (200 ao
vivo + ~180 de backfill) contra 188/min da corrida A, e gaps abertos 3.487 → 2.196. Duplicar os
processos multiplicou por ~8 a velocidade de recuperação, porque no processo único o recovery
disputa o mesmo event loop da ingestão.

**Veredito da corrida B: reprovada** na meta, aprovada como direção.

## 4. Corrida C — 4 shards × 50 mercados: a meta é cumprida

### 4.1 Convergência

| as_of | 3 componentes ok | gaps abertos | velas acumuladas |
|---|---|---|---|
| 21:50 | 155 (77,5%) | 1.867 | 346.392 |
| 21:56 | 177 (88,5%) | 981 | 358.454 |
| 22:01 | 194 (97,0%) | 203 | 373.834 |
| 22:11 | **198 (99,0%)** | 95 | 375.943 |

### 4.2 Estado final medido (22:11:44 UTC), a métrica do plano

```
"markets_monitored": 200, "ws_state": "connected"
"markets_ok": 198, "markets_stale": 0, "markets_degraded": 2, "markets_unavailable": 0
"components": {"ticker": {"ok": 198, "stale": 2}, "book": {"ok": 198, "absent": 2}}
"component_age_ms_p50...": ticker p50 850 ms
"hot_state_ok_all_three_components": 198  -> 99,0%
```

**`markets_ok` = 198/200 = 99,0% ≥ 95%.** Meta cumprida.

**Quem são os mercados que não ficam `ok`.** Numa medição anterior da mesma corrida (22:05, com
`markets_ok` em 189/200) rodei uma sonda que devolve o `monitor_rank` de cada ticker não-`ok`:

```
$ docker exec docker-api-1 python /tmp/stale_rank.py     # .claude/state/tmp/stale_rank.py
{"stale_count": 11,
 "stale_ranks": [71, 141, 144, 158, 165, 166, 168, 170, 175, 179, 197],
 "stale_examples": [[71, "ZORAUSDT", 11192], [141, "ELSAUSDT", null], [144, "AZTECUSDT", 10025],
                    [158, "SIGNUSDT", 17834], [165, "ENSUSDT", 10660], [166, "ZESTUSDT", 12266]],
 "ok_rank_max": 200, "monitor_rank_median_stale": 166}
```

Leitura honesta e o seu limite: os não-`ok` estão na cauda do ranking (mediana `monitor_rank`
166) e o mercado de rank **200 estava `ok`**, o que exclui "o worker abandona o fim da lista".
A explicação compatível é inatividade da fonte — `bookTicker` só emite quando o melhor bid/ask
muda, e `stale_after_s` é 10 s. **Isto não é prova**: provar exigiria comparar o instante de
recepção na fonte com o instante de escrita do worker, e essa medição não foi feita. Fica como
hipótese com evidência circunstancial, não como fato. Note que o veredito **não depende dela**:
às 22:11 o número medido foi 198/200 = 99,0%, com `markets_stale` = 0.

**Cobertura durável**, seis minutos seguidos — linhas, mercados distintos e velas finais:

```
$ psql -c "select open_time, count(*) as linhas, count(distinct market_id) as mercados,
           count(*) filter (where is_final) as finais from candles
           where open_time between '2026-09-05 22:05:00+00' and '2026-09-05 22:10:00+00'
           group by 1 order by 1"
       open_time        | linhas | mercados | finais
 2026-09-05 22:05:00+00 |    202 |      202 |    202
 2026-09-05 22:06:00+00 |    202 |      202 |    202
 2026-09-05 22:07:00+00 |    202 |      202 |    202
 2026-09-05 22:08:00+00 |    202 |      202 |    202
 2026-09-05 22:09:00+00 |    202 |      202 |    202
 2026-09-05 22:10:00+00 |    202 |      202 |    202
```

`linhas = mercados` (nenhuma duplicata) e `finais = linhas` (nenhuma vela parcial). São 202 e não
200 porque duas trocas de universo aconteceram dentro da janela e os mercados que saíram ainda
tiveram o minuto coletado.

**Gaps**: `recovered` 8.407 · `open` **95**, e os 95 são de mercados que já não são monitorados —
com a consulta discriminada, não por inferência:

```
$ psql -c "select m.is_monitored, count(*) from ingestion_gaps g join markets m on m.id=g.market_id
           where g.status='open' group by 1"
 is_monitored | count
 f            |    95
```

Para o universo monitorado o backlog zerou. Os 95 são o defeito 2 do §6.

### 4.3 CPU em regime estável (backlog drenado), 12 amostras de 22:06 a 22:11

| Shard | mín | **média** | máx |
|---|---|---|---|
| `market-worker` (0/4) | 35,2% | **64,2%** | 96,7% |
| `market-worker-b` (1/4) | 15,4% | **36,6%** | 56,2% |
| `market-worker-c` (2/4) | 34,9% | **54,6%** | 100,2% |
| `market-worker-d` (3/4) | 39,5% | **61,2%** | 95,8% |

**Média por shard entre 36,6% e 64,2% de um core — abaixo dos 70% da meta.** Ressalva explícita:
os **picos** chegam a 100,2%, no fecho do minuto, quando o lote de velas é gravado. Leio a meta
como média por processo em regime estável; se ela for lida como teto instantâneo, **nenhuma
topologia a cumpre**, nem esta.

Durante a drenagem do backlog (21:50–22:05) as médias foram 78,4% a 100,2% — o recovery é caro e
compete com a ingestão. Isso importa para o dimensionamento: **um shard precisa de folga para
## 5. A configuração que fica no ar: 1 processo × 50 mercados

O §6.1 explica por que a topologia de 4 shards, apesar de cumprir a meta, **não** é a que fica
configurada. Então a configuração entregue também precisa da sua própria medição — não vale
"provei outra coisa e deixei esta".

Um worker, `MARKET_UNIVERSE_SIZE=50`, `MARKET_SHARD=0/1`, recriado às 22:39 UTC.

```
$ docker exec docker-api-1 python /tmp/measure_t16b.py     # 22:46:53 UTC
"markets_monitored": 50, "ws_state": "connected"
"markets_ok": 50, "markets_stale": 0, "markets_degraded": 0, "markets_unavailable": 0
"hot_state_ok_pct": 100.0
```

**50/50 = 100% `markets_ok`**, zero stale, zero degraded, zero unavailable, hot state completo
nos três componentes. É o número mais limpo da noite inteira, e é o que o Everton vê na tela.

CPU, 18 amostras de 30 s (22:39 → 22:46, inclui o bootstrap): **mín 1,1% · média 77,7% · máx
122,3%** de um core. Nas 12 amostras de regime estável: **média 71,3%**. Ou seja: um processo com
50 mercados fica **na fronteira** dos 70% da meta — cumpre o produto (100% de `markets_ok`) mas
não sobra folga. É exatamente a razão pela qual o sharding existe, e o motivo de o heartbeat por
shard virar prioridade do M2 em vez de "um dia".

Comparação com o perfil pré-T1.6b no mesmo tamanho (`.claude/state/t16b-profile.md`): **95,1%**
de um core a 50 mercados. A T1.6b tirou ~24 pontos percentuais no mesmo trabalho.

recuperar**, não só para ingerir.

## 6. Onde a CPU realmente vai (py-spy, não hipótese)

`py-spy record` anexado ao PID 1 do shard de 100 mercados a partir de um sidecar no mesmo
namespace de PID, 90 s a 120 Hz, **11.110 amostras**:

```
docker run --rm --pid=container:docker-market-worker-b-1 --cap-add SYS_PTRACE --cap-add SYS_ADMIN \
  -v "C:/dev/project-hunter/.claude/state/profile:/out" python:3.12-slim \
  sh -c "pip install --quiet py-spy; py-spy record --pid 1 --duration 90 --rate 120 --format raw --output /out/raw-shard100.txt"
```

Self time por subsistema: `pydantic model __init__` **12,14%** · ssl read 8,33% · websockets
deflate+frames 7,91% · sqlalchemy 6,17% · redis client 4,24% · normalize (Decimal/datetime)
3,78% · idle/epoll **1,15%**.

Cumulativo por função: `_handle_raw_message` **34,1%** (`parse_book_ticker` 16,4%,
`parse_depth20` 13,0%, `parse_agg_trade` 2,2%, `parse_kline_ws` 0,8%) · `model_construct`
**15,0%** · `handle_event` 6,6% · **`run_recovery` só 4,4%** · `run_heartbeat` 0,8% ·
`run_universe` 0,03%.

Duas leituras, ambas com número:

1. **O gargalo é o caminho quente do WS, não o recovery.** O recovery é 4,4% do tempo, mesmo com
   3.200 gaps na fila — o que ele consome é *latência de rede* (uma chamada REST por gap),
   não CPU. Por isso 4 shards drenaram 3.135 gaps em 20 minutos: paralelismo de I/O.
2. **`model_construct` do pydantic é hoje o maior custo de aplicação (15%).** A T1.6b já trocou
   validação por `model_construct` nos parsers quentes, e ainda assim ele aparece com
   `resolve_default_value` (2,49%) e `inspect._signature_from_callable` + genexpr (2,75%)
   pendurados: `model_construct` continua percorrendo `model_fields` e resolvendo defaults **a
   cada evento**. O próximo passo óbvio é trocar os tipos normalizados do caminho quente por
   `dataclass(slots=True)` — fica registrado como follow-up do M2, não é bloqueio do M1.

Comparação com o perfil pré-T1.6b (`.claude/state/t16b-profile.md`): a 50 mercados o processo já
usava **95,1%** de um core, com `pydantic/main.py:__init__` em 10,83% de self. Depois da T1.6b, o
mesmo tamanho de shard roda em **média 36,6%–64,2%**. A T1.6b entregou a redução; o sharding
entregou a escala.

## 7. Defeitos que esta prova encontrou (além do CRITICAL do §0)

1. **Heartbeat compartilhado entre shards (HIGH, aberto).** Todos os shards escrevem a mesma
   chave `hb:market:binance`. Durante a corrida B o `/system/market-status` mostrou
   `subscriptions: 636` (um shard só) com `markets_monitored: 200`. Cenário concreto: um shard
   morre, o outro continua reescrevendo a chave, e o painel do operador segue verde — a métrica
   que existe para detectar worker morto fica cega justamente na topologia que a T1.6b
   introduziu. **Foi este defeito que decidiu o que fica no ar:** o M1 promete "página System com
   heartbeats reais", então a topologia com shards não é entregue (§5, §8). Follow-up do M2: chave
   por shard (`hb:market:{exchange}:{shard}`), agregação na API e o total de shards esperado vindo
   da configuração, para que a ausência de um shard seja detectável.
2. **Gaps de mercados não monitorados nunca fecham (MEDIUM, aberto).** `run_recovery` itera
   `universe.symbols`; um mercado que sai do top-N com gap aberto fica `open` para sempre e
   continua contado em `open_gaps`. Medido: dos 95 gaps abertos no fim, **95 são de mercados não
   monitorados**. Efeito: o número que o operador olha nunca chega a zero. (A decisão SHADOW já
   exige o oposto para acompanhamentos do Lab: `tracking_hold`.)
3. **`markets_ok` mistura capacidade com backlog.** Um `ingestion_gap` aberto força `degraded`
   qualquer que seja o frescor do hot state. Nas corridas A e B, `markets_ok` foi 0 o tempo todo
   — mesmo quando 122 mercados tinham book fresco. É honesto (há buraco na série), mas não serve
   sozinho como meta de capacidade; por isso esta prova mede os dois eixos.
4. **Teste de integração com orçamento de 2 s de relógio (MEDIUM, aberto).**
   `tests/integration/test_market_invariants.py::test_a_fresh_open_interest_write_never_rejuvenates_a_stale_mark`
   falhou com `assert 2323 < 2000` enquanto a máquina rodava quatro shards a ~100% de CPU. Com a
   máquina mais folgada o arquivo inteiro passou (`uv run pytest tests/integration/test_market_invariants.py -q`
   → **20 passed in 49.96s**), o que confirma a leitura: não é defeito de produto, é um teste que
   assume folga de CPU e vai piscar na CI. Registrado para o M2.

## 8. Conclusão

| Meta / questão | Resultado medido | Veredito |
|---|---|---|
| 200 mercados com `markets_ok ≥ 95%` | **198/200 = 99,0%** (0 stale, 0 unavailable, 2 degraded), com 4 shards × 50 | **alcançável e alcançada** |
| CPU < 70% de um core por processo | médias **36,6% / 54,6% / 61,2% / 64,2%** por shard em regime estável; **picos até 100,2%** | cumprida como média, **não** como teto |
| Um processo × 200 mercados | hot state a **0%** em 15 min, 188 velas/min contra 200/min | impossível, agora medido |
| Cobertura durável (4 shards) | **202 linhas = 202 mercados distintos = 202 finais** por minuto, seis minutos seguidos | completa |
| Backlog de recovery | 3.230 → 95 gaps abertos em ~20 min; os 95 são todos de mercados não monitorados | drenado |
| **Topologia entregue** | **1 processo × 50 mercados: `markets_ok` 50/50 = 100%**, CPU média 71,3% | **é esta que fica no ar** |

**A T1.6b faz o que prometeu.** O caminho quente ficou ~24 pontos percentuais de CPU mais barato
no mesmo tamanho de universo (95,1% → 71,3% a 50 mercados) e o sharding entrega a escala: 200
mercados com 99,0% de `markets_ok` é um resultado real, reproduzível pelo §4.

**E mesmo assim não entrego 200.** Com N > 1 shards, todos escrevem `hb:market:{exchange}` e o
`/system/market-status` passa a mostrar as assinaturas de **um** shard como se fossem da exchange
inteira; um shard morto fica invisível atrás dos vivos que continuam reescrevendo a chave. O M1
promete "página System com heartbeats reais". Entregar uma topologia cuja página System mente
seria trocar um número bonito por uma mentira operacional, então o override fica em **um processo
sobre os 50 maiores mercados**, onde tudo o que o M1 promete é verdade (§5). Habilitar 200 é
mudar quatro linhas do compose, depois que o heartbeat por shard existir (M2).

**O que esta prova NÃO cobre:** corrida de 24–48 h; morte de um shard com os outros vivos
(rebalanceamento não existe — a fatia do shard morto simplesmente para de ser coletada até ele
voltar); apagão externo longo atravessando reinícios; a afirmação de que os tickers `stale` são
inatividade da fonte (evidência circunstancial, não prova — §4.2); e a Bybit.

## 9. Segunda opinião (Astra)

Perguntei à Astra se o veredito se sustenta nos números do próprio arquivo, se algum dos defeitos
abertos deveria **bloquear** a aprovação do M1, e se havia afirmação sem número colado
(`.claude/state/astra-review-T1.6b-veredito.md`). Ela respondeu **"BLOQUEIA a aprovação do M1
pelo heartbeat compartilhado"**. Ponto a ponto, e o que fiz:

| Apontamento da Astra | Decisão |
|---|---|
| **Heartbeat compartilhado bloqueia**: um shard morre, o outro renova a chave e mascara a perda daquela fatia; o M1 exige heartbeats reais. | **Aceito integralmente.** Não conserto o heartbeat de madrugada (exige decidir a semântica da agregação, e o `services/market-worker` tem outra tarefa em voo): **deixo de entregar a topologia com shards**. O override volta a um processo, onde o defeito não se manifesta, e o heartbeat por shard vira item do M2. Foi este apontamento que mudou o que fica no ar. |
| A abertura dizia "NÃO CUMPRIDA", contradizendo a conclusão. | **Correto e corrigido.** Eu havia escrito o cabeçalho antes da corrida C e não o revisei. |
| Os 11 mercados `stale` e seus ranks não estavam no arquivo. | **Correto e corrigido** (§4.2, saída colada). Aceito também a ressalva: rank por volume **não prova** ausência de evento na origem; agora está escrito como hipótese com evidência circunstancial, e o veredito não depende dela. |
| `COUNT(*) = 200` não prova 200 mercados distintos com velas finais. | **Correto e corrigido**: a consulta agora traz `count(distinct market_id)` e `count(*) filter (where is_final)`. |
| "95 gaps todos fora do universo" sem a consulta discriminada. | **Correto e corrigido** (§4.2). |
| CPU: os números não sustentam "sempre abaixo de 70%", há picos de 100,2%. | **Aceito.** O texto agora diz explicitamente que leio a meta como média em regime estável e que, como teto instantâneo, nenhuma topologia a cumpre. |
| Teste de 2 s: `2323 < 2000` sozinho não comprova flakiness. | **Aceito.** Rodei a suíte inteira depois: `tests/integration/test_market_invariants.py` → **20 passed**. Está no relatório do M1 como execução verde, e o orçamento de 2 s continua registrado como item do M2. |
| Perfil de uma corrida não isola causalmente recovery vs ingestão. | **Aceito como limitação.** O py-spy mostra distribuição de tempo, não causalidade; o que sustento é o número (`run_recovery` 4,4% do tempo amostrado), não uma prova causal. |

Divergência residual: nenhuma. O bloqueio dela foi acatado mudando a entrega, não o texto.
