# notes-T3.86 — o volume de 24 h do check 9 passa a sair da mesma leitura que o carimba

**Data:** 2026-09-11 (Brasília, UTC−3; UTC como detalhe). **Owner:** risk-engine-guardian.
**Origem:** achado MÉDIO da D-P19 (`.claude/state/notes-D-P19.md` §9.6) — `bridge_inputs.py:171`
preenchia `quote_volume_24h` de `markets.volume_24h_usd` (foto do ticker, refrescada por
`services/market-worker/hunter_market_worker/universe_repo.py:90`) enquanto `volume_ts` vinha de
`volume_window(...)` sobre `candles`; `packages/risk-core/hunter_risk/observations.py:99` declara
**um** carimbo para os dois números.
**Base:** `main` em `464dedf` — árvore compartilhada, **nada commitado**, nada de `git stash`/
`checkout --`/`restore`/`reset`/`clean`/`commit -a`. **Nenhum limite do Everton mudou de valor.**
**VPS estritamente somente leitura**: toda consulta dentro de
`begin transaction isolation level repeatable read read only; … commit;` pelo stdin do `psql`,
nenhum container tocado, nenhum `.env*` lido ou escrito. Nenhum shell em segundo plano; tudo em
primeiro plano com `timeout 290`, um de cada vez. `apps/api/hunter_api/routers/**` intocado.

---

## STATUS

**DONE_WITH_CONCERNS** (§6: o pré-filtro da ponte e o `run_proof.py` continuam na coluna do ticker;
a divergência que a D-P19 relatou **não** se reproduz como divergência de valor hoje — §1.2).

| # | Entrega do brief | Resultado |
|---|---|---|
| 1 | Medição na VPS: coluna × velas, com idade e razão | **OK** — §1, `q00`, 37 linhas (16 perp do Lab + 16 SPOT monitorados + gêmeos) |
| 2 | Correção no contrato, a menor correta | **OK** — velas na mesma leitura (§2 diz por que, e por que **não** foi um `volume_24h_ts` novo) |
| 3 | `docs/RISK_ENGINE.md` v2.5 (§2, §3.1, §7.1 item 4, §9.6) + esta nota | **OK** — §5 |
| 4 | Testes: tabela pura + um arquivo de testcontainer no caminho do worker | **OK** — §4, vermelho antes e verde depois |

---

## 0. LEITURA PRÉVIA

`docs/RISK_ENGINE.md` v2.4 inteiro (§1 insumos, §2 o perfil, §3.1 checks 9/19 e o parágrafo "Idade
do volume", §4 a janela de referência, §7 falhar fechado, §7.1 as três pré-checagens do worker, §8 as
garantias), `docs/PIPELINE.md` §7–§8, `docs/ARCHITECTURE.md` §6 (`RiskEngine` puro, `ExecutionAdapter`
como único lugar com efeito), `.claude/state/notes-D-P19.md`.

---

## 1. A medição (somente leitura, VPS)

`infra/scripts/sql/research/2026-09-11-t386-q00-volume24h-ticker-vs-velas.sql`, corte
**05:37:50 BRT** (08:37:50Z), minuto de referência 08:37Z:

```bash
timeout 290 ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter \
  -v ON_ERROR_STOP=1 -f -" < infra/scripts/sql/research/2026-09-11-t386-q00-volume24h-ticker-vs-velas.sql
```

### 1.1 Não existe coluna de carimbo do volume

```
== 1. a coluna de carimbo que existe em markets ==
  column_name   |        data_type
----------------+--------------------------
 volume_24h_usd | numeric
 first_seen_at  | timestamp with time zone
 last_seen_at   | timestamp with time zone
 delisted_at    | timestamp with time zone
```

`last_seen_at` é o instante do **upsert**, não do número: `universe_repo.upsert_markets` grava
`volume_24h_usd = coalesce(excluded.volume_24h_usd, Market.volume_24h_usd)`, então um símbolo ausente
da leitura de tickers mantém o valor **antigo** debaixo de um `last_seen_at` **novo**. Não há de onde
tirar um `volume_24h_ts` honesto sem coluna nova — é o primeiro motivo da escolha da §2.

### 1.2 Ticker × velas, 24 h terminando no mesmo minuto (37 linhas; extrato)

| symbol | tipo | ticker (M USD) | velas (M USD) | razão | minutos | last_seen (s) | idade da vela (s) |
|---|---|---|---|---|---|---|---|
| BTCUSDT | perp | 10.156,65 | 10.171,14 | 1,00 | 1440 | 296 | 0 |
| PROMUSDT | perp | 14,18 | 14,19 | 1,00 | 1440 | 296 | 0 |
| SAHARAUSDT | perp | 16,49 | 16,36 | 0,99 | 1440 | 296 | 0 |
| ZECUSDT | perp | 2.843,06 | 2.848,45 | 1,00 | 1440 | 296 | 0 |
| BTCUSDT | spot | 1.178,42 | 1.178,11 | 1,00 | 1440 | 320 | 0 |
| SAHARAUSDT | spot | 89,07 | 89,67 | 1,01 | 1440 | 320 | 0 |
| UNIUSDT | spot | 45,86 | 45,84 | 1,00 | 1440 | 320 | 0 |
| **ARBUSDT** | spot | 21,40 | **9,88** | **0,46** | **467** | 320 | **58.380** |
| **PROMUSDT** | spot | 2,62 | **0,08** | **0,03** | **76** | 320 | **81.840** |
| **DASHUSDT** | spot | 14,54 | — | — | **0** | 320 | — |
| **LINKUSDT** | spot | 22,16 | — | — | **0** | 320 | — |
| **TAOUSDT** | spot | 24,88 | — | — | **0** | 320 | — |

Universo: **16 perpétuos do Lab** + **16 SPOT monitorados** (não 18 — `is_monitored AND status='active'`
dá 16 hoje, e cinco deles não são do Lab: `RLUSDUSDT`, `THEUSDT`, `USD1USDT`, `USDCUSDT`, `牛来USDT`)
+ os gêmeos SPOT não monitorados dos 16.

**Três leituras honestas:**

1. **Onde as velas cobrem a janela inteira (1.440 min), as duas fontes concordam dentro de 1 %.** A
   divergência de até 7× que a D-P19 §9.6 registrou (PROM 106 M × 14,4 M; SAHARA 5,4 M × 16,8 M) **não
   se reproduz** como divergência de valor: lá o número das velas era a **média de 30 dias**
   (ADV), aqui é a **soma das últimas 24 h** — é comparação de janelas diferentes, não duas medidas do
   mesmo fato. Hoje PROM perp mede 14,18 × 14,19 e SAHARA perp 16,49 × 16,36.
2. **A divergência real é de cobertura e de instante, não de valor.** ARB SPOT: a coluna diz 21,40 M
   e a vela mais nova tem **16 h**; PROM SPOT: 2,62 M com a vela mais nova de **22 h**; DASH, LINK e
   TAO SPOT não têm vela nenhuma e a coluna continua publicando 14–25 M.
3. **A idade da coluna já viola o prazo do próprio perfil.** Todas as 216 linhas monitoradas foram
   escritas no mesmo upsert: 296 s (perpétuos) e 320 s (SPOT) atrás do minuto de referência — contra
   `max_volume_age_s = 120` — e o refresh roda a cada `market_universe_refresh_s` (**900 s** por
   padrão, `packages/core/hunter_core/settings.py:130`), 7,5× o orçamento de idade. Enquanto isso o
   `volume_ts` entregue ao motor dizia sempre ~60 s.

---

## 2. A correção escolhida, e por que **não** foi a outra

O brief oferecia duas: (A) o número de 24 h ganha `volume_24h_ts` próprio, validado em separado, com
`stale_volume_reason` nomeando `volume_24h_stale` × `volume_1m_stale`; (B) o número de 24 h é somado
das **velas na mesma leitura**, e aí um carimbo só é honesto. **Escolhi (B).**

1. **(A) não tem carimbo para carregar.** `markets` não tem coluna de carimbo do volume (§1.1) e
   `last_seen_at` mente por construção (o `coalesce`). Publicar `volume_24h_ts = last_seen_at` seria
   fabricar idade — exatamente o que a §7 proíbe ("um insumo sem idade não é insumo").
2. **(A) com a cadência de hoje recusaria tudo.** 900 s de refresh contra 120 s de idade máxima: o
   check 9 sairia `unavailable` na quase totalidade dos ciclos. Seria "fechado", mas fechado por um
   número que nunca poderia caber — e mudar o prazo é mudar limite do Everton, que está proibido.
3. **O contrato já declarava a fonte das velas.** A coluna "Insumo" do check 9 dizia **"velas 24 h"**
   desde a v2; era o código que lia outra coisa. (B) faz o código obedecer o contrato, e não o
   contrário.
4. **(B) não acrescenta insumo ao motor puro.** `MarketLiquidity` não ganhou campo, `evaluate` não
   ganhou argumento, `stale_volume_reason` não mudou de comportamento — a v2.3 e a v2.4 se orgulham
   dessa mesma frase. (A) exigiria campo novo, motivo novo, produtor novo em cada caminho e cirurgia
   no parágrafo "um carimbo" da §3.1.
5. **A mesma leitura resolve um segundo defeito que (A) deixaria de pé:** `volume_ts` era cunhado do
   `now` do ciclo (`last_open + 1min`), **existisse ou não** a vela. Com a coleta parada há uma hora o
   motor media 60 s e acreditava. Agora o carimbo é o fechamento da **vela mais nova encontrada**.

**O que fica declarado como consequência (e está no contrato):** cobertura parcial da janela só
**diminui** a soma, então só pode reprovar — nunca aprova o que não deveria — e um buraco não
recuperado já é `open_gap` (check 5). Um mercado SPOT com menos de 24 h de série (ARB, PROM hoje) vai
reprovar o piso de 50 M por falta de prova, que é o comportamento correto para uma carteira que só
pode gastar contra o que observou.

---

## 3. O que mudou no código

| Arquivo | Mudança |
|---|---|
| `services/execution-worker/hunter_execution_worker/bridge_inputs.py` | `volume_window` soma `quote_volume_24h` das velas de 1 min do mercado SPOT em `[t−1440min, t)` (agregado no Postgres, uma linha de volta), devolve `day_minutes` e carimba `volume_ts` com o **fechamento da vela mais nova encontrada** (`None` quando não há nenhuma); `liquidity_for` passa `volumes.quote_volume_24h` no lugar de `spot.volume_24h_usd` |
| `packages/risk-core/hunter_risk/inputs.py` | docstrings de `quote_volume_24h` e `volume_ts`: a dupla é **uma observação**, e o carimbo é dever do produtor |
| `packages/risk-core/hunter_risk/observations.py` | `stale_volume_reason`: declara que o motor puro **não pode** verificar a procedência, e nomeia o defeito que a T3.86 fechou |
| `docs/RISK_ENGINE.md` | v2.5: cabeçalho, §2 (linha `min_liquidity_usd_24h`), §3.1 (check 9 + parágrafo novo "Um carimbo só é um carimbo…"), §7.1 item 4, §9.6 |

`manual_inputs.py` **já** chega ao motor por `liquidity_for`, então o caminho manual foi corrigido
pela mesma linha — não havia o que duplicar. `entry_inputs.py` não monta `MarketLiquidity` (só decide
se o livro/`avgPrice` estão prontos) e não precisou de mudança. **`apps/api/hunter_api/services/
orders_derive.py` (T3.68) não passa volume nenhum**: ele deriva `entry_ref` e `assumed_costs` do
ticker SPOT do hot state e arquiva o pedido; quem monta a foto de liquidez do pedido manual é o
worker, um segundo depois. O brief supunha o contrário; não editei `apps/api/hunter_api/routers/**`
nem nada em `apps/api/`.

**Custo da medida, medido antes de entrar** (`q01`, VPS, somente leitura):

```
Aggregate (actual time=1.739..1.740 rows=1 loops=1)   Buffers: shared hit=408
  ->  Append (actual time=0.339..1.516 rows=1440)     Subplans Removed: 6
      ->  Bitmap Heap Scan on candles_1m_2026_09      Heap Blocks: exact=383
          ->  Bitmap Index Scan on candles_1m_2026_09_pkey (rows=1440)
Execution Time: 1.986 ms
```

1,99 ms, poda de partição, tudo em cache — cabe num ciclo de 1 s sem discussão.

---

## 4. Testes — saída real

**Vermelho primeiro** (o teste novo contra o código antigo; o log do worker é a própria falha):

```
$ timeout 290 uv run pytest services/execution-worker/tests/test_volume_24h_source.py -x -q
2026-09-11 05:42:14 [info  ] proposal_decided  admission_seq=1 approved=True
  binding_constraint=risk_per_trade ... rejection_reasons=[] reservation_state=held source=manual
2026-09-11 05:42:14 [info  ] request_admitted  approved=True idempotency_key=manual:t386-thin-1 ...
FAILED services/execution-worker/tests/test_volume_24h_source.py::test_the_ticker_column_does_not_decide_the_fifty_million_floor
1 failed in 22.01s
```

Isto é o achado em dinheiro: 31 M/24 h nas velas, coluna do ticker em 120 M, **reserva `held`** contra
um piso de 50 M.

**Verde depois:**

```
$ timeout 290 uv run pytest services/execution-worker/tests/test_volume_24h_source.py -q
..                                                                       [100%]
2 passed in 27.46s

$ timeout 290 uv run pytest packages/risk-core/tests/unit/test_volume_provenance.py -q
..........                                                               [100%]
10 passed in 0.55s

$ timeout 290 uv run pytest packages/risk-core/tests -q
221 passed in 5.15s
```

**Nenhuma regressão no worker** (a suíte inteira, em quatro levas de primeiro plano porque ela passa
de 290 s de uma vez):

```
$ timeout 290 uv run pytest services/execution-worker/tests/test_bridge_cycle.py services/execution-worker/tests/test_bridge_consumer.py -q -p no:randomly
12 passed in 127.67s (0:02:07)
$ timeout 290 uv run pytest .../test_manual_request_decided.py .../test_bridge_eligibility.py .../test_bridge_refusal_dedupe.py -q -p no:randomly
24 passed in 84.92s (0:01:24)
$ timeout 290 uv run pytest .../test_order_cycle.py .../test_concurrency.py .../test_restart_recovery.py -q -p no:randomly
6 passed in 59.49s
$ timeout 290 uv run pytest services/execution-worker/tests -q -p no:randomly --ignore=<os oito acima>
154 passed in 152.78s (0:02:32)
```

**Portões:**

```
$ uv run ruff check packages/risk-core services/execution-worker  →  All checks passed!
$ uv run ruff format --check ...                                  →  formatado
$ uv run pyright <os cinco arquivos>                              →  0 errors, 0 warnings, 0 informations
$ uv run python infra/scripts/check_file_size.py                  →  scanned 629 files; 0 over budget, 0 grandfathered
```

`bridge_inputs.py` fica em **316** linhas (teto 350).

**O que cada teste prova.** `test_volume_24h_source.py`: (1) a coluna do ticker não decide o piso — 31
M de velas com 120 M na coluna **reprova** `liquidity_24h`; (2) coleta parada há 10 min → `volume_ts`
é o fechamento da vela real, idade 600 s, `liquidity_24h` **`unavailable`** com a idade na mensagem.
`test_volume_provenance.py`: tabela pura com caso que passa e caso que reprova para o check 9 (no
piso, um centavo abaixo, sem número, carimbo vencido, no limite exato, sem carimbo, carimbo no
futuro), mais a cascata (`participation` + `sizing is None`) e a mensagem que nomeia a idade.

---

## 5. Arquivos (meus, do `git status --porcelain`; árvore compartilhada — o resto é de outros agentes)

```
 M docs/RISK_ENGINE.md
 M packages/risk-core/hunter_risk/inputs.py
 M packages/risk-core/hunter_risk/observations.py
 M services/execution-worker/hunter_execution_worker/bridge_inputs.py
?? infra/scripts/sql/research/2026-09-11-t386-q00-volume24h-ticker-vs-velas.sql
?? packages/risk-core/tests/unit/test_volume_provenance.py
?? services/execution-worker/tests/test_volume_24h_source.py
?? .claude/state/notes-T3.86.md
```

**Nada commitado.** `git diff --stat` dos quatro modificados: 149 inserções, 13 remoções.

---

## 6. CONCERNs e residuais (cada um com o cenário que o torna real)

1. **`bridge_screen.py:297-300` continua peneirando pela coluna do ticker**
   (`spot.volume_24h_usd < SPOT_VOLUME_FLOOR_USDT`), antes de a proposta existir. É um pré-filtro que
   só **recusa**, então nenhum dinheiro sai por ele; mas o falso negativo é real: se a coluna congelar
   em 45 M (símbolo ausente da leitura de tickers → `coalesce`) num mercado que negocia 60 M, a ponte
   recusa `spot_volume_below_floor` para sempre e o operador lê um motivo de liquidez sobre um mercado
   líquido. Unificar o pré-filtro com a soma das velas é uma tarefa própria (ela toca o roster, não o
   contrato de risco).
2. **`services/execution-worker/proof/run_proof.py:127-131` fabrica `quote_volume_24h=100 M` e
   `volume_ts=utcnow()`.** É a bancada rotulada da prova de 30 minutos, com venue sintético — os dois
   números são inventados juntos, então não há descasamento; fica registrado para que ninguém a use
   como exemplo de produtor.
3. **Mercado SPOT com menos de 24 h de velas reprova o piso por falta de prova** (ARB e PROM SPOT
   hoje; DASH/LINK/TAO SPOT não têm vela nenhuma e viram `unavailable`). É o comportamento correto e
   está declarado na §3.1, mas muda o conjunto elegível na prática: a carteira passa a exigir 24 h de
   série do próprio mercado onde compra. Vale medir de novo depois que a cobertura SPOT amadurecer
   (a D-P19 §9.1 já registrava 4 dias contra 30).
4. **A divergência que motivou a tarefa não é divergência de valor** (§1.2, leitura 1). O defeito real
   era de **instante e de procedência**, e é esse que foi fechado. Quem ler a D-P19 §9.6 esperando um
   fator de 7× entre as duas fontes não o encontra hoje.
5. **Uma leitura a mais por candidato por ciclo** (o agregado de 24 h): 1,99 ms medidos com cache
   quente num mercado de 1.440 velas. Num ciclo com muitos candidatos e cache frio isso soma; não
   medi cache frio, e o `EXPLAIN` acima é de uma execução única.
6. **Não medi a idade da coluna ao longo do tempo**, só no corte. O 296–370 s é uma amostra; o limite
   superior estrutural é o `market_universe_refresh_s` (900 s), lido do código, não do ambiente da VPS
   (não li `.env*`).
