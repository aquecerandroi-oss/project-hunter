# T3.0 — prova de execução do caminho de dados SPOT (T3.0c)

**Data:** 2026-09-07. **Onde:** stack local (`infra/docker/docker-compose.yml`), Binance
pública real, sem chave. **Máquina:** 22 vCPU / 7,5 GiB, **compartilhada com outros agentes
durante toda a medição** (`execution-worker`, `scanner-worker`, `strategy-worker`, `postgres`,
mais containers de testcontainers de outras tarefas).

Imagem `hunter-api:dev` reconstruída a partir da árvore de trabalho antes de cada arm.

---

## 0. Resumo em uma linha

**O caminho spot funciona e está provado. O que não passou foi conviver com 200 perpétuos no
mesmo processo `MARKET_SHARD=0/1`** — e isso foi medido em A/B, não suposto. Por causa disso
`MARKET_SPOT_ENABLED` nasce **`false`**.

---

## 1. A/B controlado: spot ligado vs. desligado, mesmo processo, 6 min cada

Mesma máquina, arms consecutivos, universo perpétuo cheio (200) nos dois.

| | **A — spot OFF** (07:53:45→07:59:27) | **B — spot ON** (08:00:03→08:06:01) |
|---|---|---|
| `hb:market:binance` `ws_state` | `connected` | `connected` |
| `last_event_at` na hora da leitura | **28 s de idade** | **5 min de idade** |
| velas perpétuas nos últimos 5 min | **600** | **0** |
| `reconnects` no arm | 2 | **8** |
| erro de WS no log | `no close frame received` | `sent 1011 (internal error) **keepalive ping timeout**` |
| CPU do processo | 119 % | 99,7 % |
| `hb:market:spot:binance` | ausente (correto: switch off) | `connected`, `last_event_at` 18 s |

**Leitura:** o coletor perpétuo com 200 mercados já satura um core (achado da T2.5g). Somar o
laço de parse do spot no **mesmo event loop** faz o socket perpétuo perder o orçamento de
keepalive — a Binance derruba a conexão com `1011`, ele reconecta 1 200 streams, entra em
backlog e o ciclo se repete. Não é bug do spot: é falta de folga de event loop no shard.

---

## 2. Prova de 15 min do caminho SPOT (com folga de event loop)

Para medir o **spot** e não a saturação do vizinho, este arm rodou com o universo perpétuo
reduzido (`MARKET_UNIVERSE_SIZE=20` → 36 monitorados com os holds do Lab). É um **diagnóstico
declarado**, não uma mudança de configuração do perpétuo: a stack foi restaurada ao default do
repositório ao fim (§4).

**Janela: 08:28:41Z → 08:44:22Z = 15 min 41 s.**

| Critério do brief | Medido | ✔ |
|---|---|---|
| `hb:market:spot:binance` vivo | `ws_state=connected`, `last_event_at` 2 s de idade, `ts` 08:44:20Z, `shard_total=1`, `rest_gate=ok` | ✔ |
| ≥ 15 pares com **livro** no hot state | **16** chaves `mkt:binance:spot:*:book` (universo monitorado = 16), estável em 5 amostras de 25 s | ✔ |
| ≥ 15 pares com **último negócio** spot | **19** ring buffers `mkt:binance:spot:*:trades` (`LLEN mkt:binance:spot:BTCUSDT:trades = 971`) | ✔ |
| velas spot em `candles` | 7 235 → 7 373 linhas sob `market_id` spot; `+122` em 8 min para 17 mercados (≈ 1/min/mercado) | ✔ |
| 0 exceções | `docker logs --since 15m \| grep -ciE "traceback\|[error"` → **0** | ✔ |
| perpétuo intocado | `hb:market:binance` `connected`, `last_event_at` 1 s, **0 reconnects** no arm | ✔ *neste arm* |
| `spot` como status detail em `/ready` | ver §3 | ✔ |

Amostra do hot state spot (o preço de execução que a D1 pede):

```
mkt:binance:spot:BTCUSDT:ticker
  ts=2026-09-07T08:33:33.438853+00:00
  last=79495.48000000
  bid=79495.48000000   bid_qty=1.34102000
  ask=79495.49000000   ask_qty=2.30740000
```

Cobertura spot publicada em `mkt:binance:spot:coverage`, com `sym:{símbolo}` por par
(`sym:SUIUSDT`, `sym:SOLUSDT`, `sym:USDCUSDT`, `sym:UNIUSDT`, `sym:USD1USDT`, `sym:BTCUSDT`,
`sym:XRPUSDT`, `sym:DASHUSDT`, …) e **nada** escrito em `mkt:binance:coverage` pelo coletor spot.

Universo spot ao vivo: **16–19 pares** acima do piso de 50 M USDT/24 h, oscilando na borda
(`PROMUSDT` entrou e saiu entre dois refreshes). A fixture gravada às 03:36Z dá **19 de 740**
pares USDT.

**Ressalva desta janela:** `covered_until` do spot congelou em 08:37:04Z enquanto o
`dropped_events` continuava subindo (93 486 no arm). É o comportamento correto e desenhado —
um descarte quebra o intervalo e a prova congela em vez de reivindicar fita que não foi
coletada — mas significa que, **com descarte contínuo, o scanner recusaria janelas spot**. Numa
máquina com folga de verdade o descarte não existe; nesta, existe para os dois produtos.

---

## 3. Readiness

Com o default (`MARKET_SPOT_ENABLED` não definido), `/ready` do market-worker:

```json
{"database": true, "redis": true, "ingestion": true, "persistence": true,
 "partitions": true, "outbox": true, "rest_gate": "ok", "spot": "absent", "fx": "ok"}
```

`spot` é *status detail*, ao lado de `rest_gate`, e **não** altera o veredito — `absent` aqui
significa "este processo não coleta spot", não "está quebrado". Com o switch ligado e o socket
saudável o valor é `connected`; reconectando, `degraded`.

---

## 4. Estado em que a stack ficou

Restaurada ao **default do repositório** (`docker compose -f infra/docker/docker-compose.yml up
-d --force-recreate market-worker`, sem override): universo perpétuo 200, `MARKET_SPOT_ENABLED`
ausente ⇒ `false`. Verificado depois da restauração:

```
hb:market:binance  ws_state=connected  subscriptions=1200  markets_monitored=200
                   reconnects=0        open_gaps=0         rest_gate=ok
/ready             {"...": true, "rest_gate": "ok", "spot": "absent", "fx": "ok"}
```

Nenhum arquivo do repositório ficou com override; os dois arquivos de override usados
(`/tmp/spot-on.yml`, `/tmp/spot-headroom.yml`) são temporários e fora da árvore.

---

## 5. O que ligar o spot exige, na prática

1. **medir a folga do event loop do shard 0** antes. Um processo já em ~100 % de CPU não tem
   nenhuma: foi exatamente o arm B do §1;
2. `MARKET_SPOT_ENABLED=true` no ambiente do market-worker do shard 0 (nenhum outro shard
   reage à variável);
3. conferir, nos primeiros minutos: `hb:market:spot:{ex}` presente e `reconnects=0`;
   `hb:market:{ex}` com `last_event_at` fresco e `reconnects` **não** subindo; velas perpétuas
   continuando a entrar.

Na VPS o shard 0 carrega ~50 perpétuos (4 shards), ou seja ~¼ da carga que satura um core
aqui, e o spot acrescenta ~800 ev/s contra ~10 k ev/s do perpétuo — a folga provavelmente
existe. **Provavelmente não é medido**: a checagem acima é obrigatória.
