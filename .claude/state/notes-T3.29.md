# notes-T3.29 — prova operacional do fluxo autônomo paper (risk-engine-guardian, 2026-09-08)

Base: `main` em `50932ec`, árvore compartilhada. **Nada commitado.** VPS tratada como
**somente leitura** (nenhum `INSERT`/`UPDATE`/`DELETE`, nenhuma flag, nenhum restart).

## 1. O que as medições da VPS dizem

Todas via `ssh hunter-vps` + `docker exec hunter-postgres-1 psql -U hunter -d hunter -c "SELECT ..."`,
2026-09-08 entre 14:03Z e 14:12Z. Números e SQL completos em `docs/ACTIVATION.md` §8.

| Achado | Número |
|---|---|
| `agents` | **0 linhas** — a causa raiz de "154 sinais, 0 propostas" |
| `avgPrice` | 15/15 SPOT monitorados com `applyMinToMarket=true` e `avgPriceMins=5`; **22 de 22** sinais admissíveis de 24 h adiariam |
| β | 200 revisões vigentes, **1 válida** (BTC, identidade). 199 `insufficient_history` com 423 barras contíguas vs. 480. Causa: o **BTC perpétuo** (a referência) só tem 1m desde `2026-08-21 20:32Z` |
| Funil real 24 h | 171 sinais → 121 com par spot → 22 acima do piso D1 → **0** com β válido |
| MTM | último ponto `1m` 36 s antes da leitura, `marks_stale=false`, equity 19.333,0111164813, KS `ACTIVE` |
| Heartbeat | `paper_autonomy=false` (correto antes do aceite); **sem** campo de qualidade de marcação |
| Backup | 3 dumps, último 2026-09-08T01:17Z (387 M), cron `/etc/cron.d/hunter-backup` 03:17 diário com `bash`; `pg_restore --list` → 1730 entradas, tabelas do ledger presentes |
| Perfil de risco | `portfolios.risk_profile_id` é **NULL**; não existe linha `risk_profiles.preset='paper_v1'`. Limites em vigor continuam corretos porque `admit(..., limits=PAPER_V1)` usa o objeto do motor |

**Efeito colateral registrado:** a checagem do dump puxou a imagem `postgres:16` no
Docker da VPS (`docker run --rm -v /opt/backups:/b:ro postgres:16 pg_restore --list`).
Escreveu no store de imagens, não no banco; nenhum container foi parado ou recriado.
Devia ter usado o `hunter-postgres-1` já existente — registrado como desvio.

**Restore real não foi feito.** O brief o permitia num banco separado; a instrução
desta sessão ("na VPS nada de UPDATE/INSERT/DELETE") é mais restritiva e prevaleceu.
`pg_restore --list` é o mínimo que o brief aceita, e é o que ficou.

## 2. Código

### 2.1 `avgPrice` (item 2) — `avg_price.py`, `market_data.py`, `entry_inputs.py`, `main.py`

Endpoint escolhido: **`GET /api/v3/avgPrice`** (spot, peso 2). É a única fonte pública
do número que o filtro `NOTIONAL` de uma ordem MARKET usa: o payload traz o próprio
`mins` que o filtro declara. Os dois sugeridos no brief são recusados por nome:
`/fapi/v1/ticker/price` e `/fapi/v1/premiumIndex` são **USDS-M**, e D1 é "SPOT executa,
o perpétuo decide" — um mark/index de perpétuo não tem autoridade sobre um filtro spot.
`/api/v3/ticker/price` (spot) é o último negócio, que é o que `avgPriceMins == 0`
significa; com `avgPriceMins = 5` em 15 de 15 mercados, substituí-lo seria julgar o
filtro pelo print que a média existe para suavizar.

Dois prazos, declarados: `AVG_PRICE_REFRESH_S = 5` (reuso do cache, controle de custo
sobre o orçamento de 6000 peso/min compartilhado) e `AVG_PRICE_MAX_AGE_S = 30` (limite
duro — a própria vida da reserva). Uma falha de rede reusa a última cotação **enquanto
ela está dentro do limite duro** e depois não reporta nada; relógio que anda para trás é
tratado como vencido. A idade é medida **duas vezes**: no leitor (relógio próprio) e em
`entry_inputs.stale_average` contra o `now` do ciclo — a segunda é a que a *decisão*
pode ser cobrada e pega uma foto montada antes de uma pausa e usada depois.

`SpotSnapshot` ganhou `avg_price_ts`. O `StaticSpotMarketData` (dublê) carimba uma
referência sem data com o `received_at` do próprio livro (`_dated`), porque um fixture
que entrega uma foto entrega **um instante**; um teste que quer referência velha põe o
carimbo à mão.

### 2.2 `mark_quality` (item 4) — `bridge_inputs.py`, `state.py`, `heartbeat.py`, `metrics.py`, `manual_inputs.py`, `bridge.py`

`marks_for_open_positions` passa a devolver `MarkCoverage` (marcas + posições abertas +
`quality`/`complete`). Publicado em `hb:execution:paper` (`mark_quality`,
`marked_positions`) e na métrica `hunter_execution_mark_quality`. Carteira vazia é `1`
por construção — reportar `0` transformaria o estado normal em alarme permanente.

**Pré-checagem de admissão:** com `quality < 1` a admissão é **adiada**
(`marks_incomplete`), no caminho manual e na ponte. Adiar e não recusar é a mesma regra
que o resto do caminho de entrada já segue ("insumo não pronto → nada escrito, tentativa
não gasta"), e evita queimar um pedido do operador numa fita transitória. O motor puro
continua sendo a última trava (`marks_complete` → `portfolio_status` `unavailable`).

**Não mexi no `/ready`.** Deixar uma marca velha derrubar a prontidão poderia fazer o
healthcheck reiniciar o worker — e um worker reiniciando é um worker que não protege
posição. A qualidade é heartbeat + métrica + trava de admissão, que é onde ela age.

### 2.3 Redis inacessível não derruba o passe (item 5)

`RedisSpotMarketData` deixou de propagar exceção de leitura: `_book`/`_trades` devolvem
`(valor, unreachable)`, e o snapshot carrega `hot_state_unreachable` no `unavailable`.
Antes, um `ConnectionError` numa chave abortava o passe inteiro do ciclo — **inclusive
a proteção das outras carteiras**, o que contradiz a regra 3 da diretiva. O motivo do
adiamento passa a nomear o incidente (`hot_state_unreachable`) em vez do sintoma
(`no_book`).

### 2.4 Divisão de `bridge.py` → `bridge_rank.py`

`bridge.py` estava exatamente no teto de 350 linhas; a pré-checagem de marcação o
estourou. A ordenação D3 (`Ranked`, `entry_cost_r`, `_priority`, `rank_candidates`) saiu
para `bridge_rank.py`, seguindo a costura que o próprio docstring já desenhava e o
padrão `bridge_repo`/`bridge_screen`/`bridge_universe`. `bridge.py` foi de 350 para 263.

### 2.5 Teste com relógio de parede consertado (achado colateral)

`services/execution-worker/tests/test_manual_request_decided.py` estava **vermelho**
desde a virada do dia: `proof/venue.open_wallet` abria a carteira em `utcnow()` enquanto
o teste decide num `NOW` fixo (2026-09-07 12:00Z). A âncora do dia de São Paulo ficava
em 08/09 e a decisão em 07/09, então `build_portfolio_state` devolvia
`unavailable=('daily_reference',)` e **todos** os 23 checks saíam como motivo de recusa.
`seed`/`open_wallet` ganharam `as_of` opcional (default `utcnow()`, `run_proof.py`
intacto) e o teste passa o seu próprio instante. Não é regressão desta tarefa — é a
armadilha 2 da §12 ("sem relógio de parede") num arquivo que a tinha.

## 3. Testes novos

- `services/execution-worker/tests/test_avg_price.py` (18) — leitor, cache, limite duro,
  falha de rede, relógio para trás, média não positiva, cache por mercado, snapshot com
  e sem leitor, e a banda de idade no `entry_inputs`.
- `services/execution-worker/tests/test_mark_quality.py` (9) — aritmética da cobertura,
  carteira vazia = 1, `Decimal` nunca `float`, e o heartbeat publicando os três campos.
- `tests/integration/paper/test_v10_degraded_protection_restart.py` (1, item 3) — parcial
  de 4, depois `pending_degraded` sem livro, depois **restart** (`DegradedRetries` novo,
  sem watermark) e a intenção termina o remanescente: nenhuma unidade vendida duas vezes,
  nenhum `client_order_id` reusado, nenhum `fills` escrito pela tentativa degradada.
- `tests/integration/paper/test_v6_...py` +4 (item 5) — passos 3 e 4 contra Redis **real**
  (`redis_container`) e o `RedisSpotMarketData` real: chave do livro sumida → adia e a
  reserva expira em 30 s com motivo; livro de antes da queda → `book_stale`; conexão
  morta durante a decisão → `hot_state_unreachable`, nada escrito, reserva preservada, e
  a mesma reserva vira **uma** ordem quando o Redis volta.
- `test_manual_request_decided.py` +1 caso (item 4) — posição aberta + fita inutilizável
  ⇒ `coverage.quality == 0` e `manual_request_inputs` devolve `marks_incomplete`.

## 4. Pendências que continuam abertas (não são minhas para fechar sozinho)

1. **β**: sem backfill do **BTC perpétuo** para ≥ 20 dias contíguos de 1m, nenhum mercado
   além do próprio BTC terá β válido, e a carteira não abre nada. É a linha vermelha do
   aceite.
2. **`agents`**: o comando auditado está em `docs/ACTIVATION.md` §8a; **não foi rodado**.
3. **Restore real** do dump num banco descartável.
4. **`risk_profiles.paper_v1`** não semeado na VPS e `portfolios.risk_profile_id` NULL.
5. `DATABASE_URL_MIGRATIONS` no bloco compartilhado do compose (achado HIGH da Astra,
   `infra/**` fora do meu escopo de escrita).
6. `hb:execution:paper` só ganha `mark_quality` **depois do deploy**; hoje a VPS roda
   `9a291d3`.
