# T4.2 — storage + coletor + features por minuto do pump.fun (migração `0021_meme_radar`)

Execução de 12/09/2026, a partir das 04:4x BRT (UTC−3). Papel: database-architect.
Sem commit. Migração **0021** (a `0020_market_dispersion` é da T3.90 e não foi tocada).

---

## contrato — o modelo de leitura congelado para a T4.3

**Esta seção é o contrato.** Foi escrita antes da implementação e é o que a T4.3
(API + web) pode assumir sem esperar por mim. O que mudar depois de escrito aqui
aparece como linha nova em "§contrato — emendas", nunca reescrito no lugar.

Cinco tabelas, **todas globais** (`docs/DATABASE.md` §1.1: dado de mercado
on-chain não é dado de tenant): **sem `organization_id`, sem RLS, sem política**.
Privilégios: `hunter_app` **só `SELECT`**; `hunter_worker` escreve.
Nenhuma delas é alcançável por `hunter_runtime` sem `SET ROLE` (§27.1).

### 1. `meme_tokens` — a dimensão, uma linha por mint

PK `mint text`. **Não particionada** (a chave é o mint, não o tempo).
Identidade é **escrita uma vez**: `NULL` → valor é permitido uma única vez, e
qualquer alteração de um valor já conhecido é recusada por trigger
(`meme_tokens_identity_is_written_once`), para **todo** papel, dono incluído.

| coluna | tipo | nulo | significado |
|---|---|---|---|
| `mint` | text | não | PK, a chave natural |
| `name`, `symbol`, `uri`, `creator` | text | **sim** | identidade do evento de criação. `NULL` = ainda não observada (uma migração pode chegar antes da criação — cenário obrigatório da T4.1) |
| `created_at` | timestamptz | **sim** | criação. **Não é block time** para linha vinda do WS: o frame do PumpPortal não carrega timestamp nenhum (T4.1 `models.py`), então vale o `received_at` do frame — está declarado, não disfarçado |
| `bonding_curve` | text | sim | conta da curva |
| `initial_virtual_sol_reserves`, `initial_virtual_token_reserves` | numeric(28,10) | sim | reservas virtuais do evento de criação |
| `initial_real_token_reserves` | numeric(28,10) | sim | **o denominador do progresso** (§3 do plano). Escrito uma vez, a partir da primeira observação cujo `real_sol_reserves = 0` (curva que ninguém comprou ainda) — observado, nunca a constante 793,1 M de blog |
| `total_supply` | numeric(28,10) | sim | oferta reportada |
| `pool` | text | sim | launchpad na criação (`pump`) |
| `mayhem_enabled` | boolean | **sim** | `NULL` = desconhecido. **Nunca `false` por default** (MUST-FIX 2 da Astra) |
| `mayhem_mode` | text | sim | `auto` \| `manual` \| `unknown` — eixo separado do estado (A4.1b §6) |
| `mayhem_state` | text | sim | `active` \| `paused` \| `completed` \| `unknown`. Proibido não-nulo quando `mayhem_enabled IS FALSE` |
| `completed_at` | timestamptz | sim | primeira observação de curva concluída (`complete = true`) |
| `migrated_at`, `migrated_pool` | timestamptz / text | sim | migração para o PumpSwap — **evento separado** da conclusão (§3 do plano). `migrated_at` não nulo exige `migrated_pool` |
| `first_seen_source` | text | não | `pumpportal_ws` \| `pumpfun_rest` \| `solana_rpc` |
| `first_seen_at`, `last_seen_at` | timestamptz | não | procedência e frescor |
| `updated_at` | timestamptz | não | |

Índices: PK(`mint`); `ix_meme_tokens_created_at`; `ix_meme_tokens_first_seen_at`.
**Não há índice de Mayhem**: o filtro do screener pega carona na varredura por
`created_at` enquanto nenhuma consulta medida pedir outra coisa (§26.4).

### 2. `meme_curve_snapshots` — a série da curva (RANGE mensal por `observed_at`)

PK `(observed_at, mint, source)` — coluna de partição primeiro (§15.2). Índice
`ix_meme_curve_snapshots_mint_observed (mint, observed_at)` na pai, propagado a
toda partição.

`mint`, `observed_at`, `source` (`pumpfun_rest` \| `solana_rpc` \| `pumpportal_ws`),
`received_at` (quando **nós** tivemos o dado — o par `observed_at`/`available_at`
do §18.2), `virtual_sol_reserves`, `virtual_token_reserves`, `real_sol_reserves`,
`real_token_reserves`, `total_supply` (todos `numeric(28,10)`, não nulos),
`complete boolean`, `slot bigint NULL`, `commitment text NULL`,
`mayhem_enabled/mayhem_state/mayhem_mode` como a fonte os reportou **naquele
instante** (estado mutável precisa de histórico — A4.1b §6).

`mcap_sol numeric(28,10)` é **coluna gerada pelo banco**
(`GENERATED ALWAYS AS ((virtual_sol_reserves / NULLIF(virtual_token_reserves,0)) * total_supply) STORED`):
a API **lê**, nenhum produtor escreve, e não existe linha em que o mcap discorde
das reservas ao lado. O `NULLIF` é o que mantém a regra do §15.8 (um feed emite
zero de vez em quando, e um CHECK ali transformaria dado estranho em falha de
ingestão): reserva zero vira `mcap_sol NULL`, não `division by zero`.
`mcap_sol` é **sempre teórico** (§4 do plano) — preço marginal × oferta, nunca o
que uma venda realizaria.

### 3. `meme_trades` — **sem produtor hoje** (RANGE mensal por `block_time`)

PK `(block_time, signature, event_index)`. `event_index smallint` é o ordinal do
**evento de trade decodificado dentro da transação** — é ele que fecha o MUST-FIX
2 da Astra (`(signature, ts)` perdia dois trades da mesma tx); `outer_ix_index` e
`inner_ix_index` ficam ao lado como procedência. `mint`, `slot bigint`,
`block_time`, `received_at`, `trader`, `side` (`buy`/`sell`),
`sol_lamports bigint` (unidade-base inteira, exata), `token_amount numeric(28,10)`,
`price numeric(28,10)`, `quote_mint`, `token_decimals smallint`,
`commitment text` (`confirmed`/`finalized` — finalidade explícita),
`is_mayhem_agent boolean NULL` (`NULL` = atribuição incompleta; `false` só depois
de atribuir a outro trader — A4.1b §6), `source`.
Índice `ix_meme_trades_mint_block_time (mint, block_time)`.

**A tabela nasce vazia e permanece vazia nesta fatia**: o feed de trades do
PumpPortal é pago e o decodificador on-chain é a T4.2b. A T4.3 tem de tratar
"nenhuma linha" como **ausência de fonte**, não como "ninguém negociou" — e as
colunas de `meme_features_1m` que dependem dela já dizem isso por si (abaixo).

### 4. `meme_features_1m` — o minuto fechado (RANGE mensal por `end_time`)

PK `(end_time, mint, features_version)`. A coluna de partição é também a
**líder** da PK de propósito: a leitura da lista do Radar é
`WHERE end_time = :ultimo_minuto ORDER BY curve_progress_pct DESC LIMIT n`, que é
varredura por prefixo de índice, não `SELECT *`. Índice
`ix_meme_features_1m_mint_end_time (mint, end_time)` serve o gráfico de um mint.

| coluna | tipo | hoje | motivo quando nulo |
|---|---|---|---|
| `features_version` | text | `meme_features_v1` | protocolo congelado; mudar a conta é versão nova, nunca reescrita |
| `curve_progress_pct` | numeric(9,6) | `1 − real_token_reserves/initial_real_token_reserves` | `progress_reason` |
| `mcap_sol` | numeric(28,10) | do snapshot de onde a linha saiu | `curve_reason` |
| `unique_buyers` | integer | **sempre `NULL`** | `no_trade_feed` |
| `buy_sell_ratio` | numeric(18,8) | **sempre `NULL`** | `no_trade_feed` |
| `top10_share` | numeric(9,6) | **sempre `NULL`** | `no_holders_reader` |
| `creator_sold` | boolean | **sempre `NULL`** | `no_holders_reader` |
| `age_minutes` | integer | `end_time − meme_tokens.created_at` | nulo **sem** coluna de motivo: a única causa é `meme_tokens.created_at` desconhecido, e a linha do token já diz isso — uma segunda cópia do motivo seria a segunda verdade do §19.3 |
| `coverage` | numeric(9,6) | fração do minuto de fato observada | não nulo nunca |
| `snapshot_observed_at`, `snapshot_source` | timestamptz / text | procedência do número da curva | nulo quando não houve observação |
| `computed_at` | timestamptz | relógio da conta | — |

Seis colunas de motivo (`progress_reason`, `curve_reason`, `unique_buyers_reason`,
`buy_sell_ratio_reason`, `top10_share_reason`, `creator_sold_reason`), cada uma
com **CHECK bicondicional**: o valor é nulo **se e somente se** o motivo é não
nulo (precedente `no_entry_reason`, §16.2). Não existe linha com valor ausente e
sem motivo, e não existe linha com valor **e** motivo.

**Vocabulário congelado de motivo** (a T4.3 renderiza estes, e só estes):
`no_trade_feed`, `no_holders_reader`, `denominator_unknown`, `not_polled`,
`rate_limited`, `insufficient_coverage`, `unsupported_quote`.

### 5. `meme_ingest_gaps` — a lacuna como fato, append-only

`id uuid` (uuid7), `stream` (`pumpportal_ws` \| `curve_poll` \| `features_1m`),
`mint text NULL` (nulo = lacuna do stream inteiro), `gap_start`, `gap_end`
(`gap_end > gap_start`), `detected_at`, `reason text`, `generation integer NULL`
(a geração de conexão do WS, `ws.py`), `detail jsonb`.
Índice `ix_meme_ingest_gaps_stream_gap_start (stream, gap_start)`.
**Sem `recovered_at`**: não existe caminho de recuperação nesta fatia (não há
fonte histórica de curva nem feed de trades), e uma coluna que ninguém escreve
alegaria que existe. Quando a T4.2b trouxer backfill, ela traz a coluna com a
sua revisão.

### 6. A visão que a API lê

```sql
CREATE VIEW meme_radar_features_v1 AS
SELECT f.mint, f.end_time, f.features_version, f.curve_progress_pct, f.progress_reason,
       f.mcap_sol, f.curve_reason, f.unique_buyers, f.unique_buyers_reason, f.buy_sell_ratio,
       f.buy_sell_ratio_reason, f.top10_share, f.top10_share_reason, f.creator_sold,
       f.creator_sold_reason, f.age_minutes, f.coverage, f.snapshot_observed_at,
       f.snapshot_source, t.name, t.symbol, t.creator, t.created_at AS token_created_at,
       t.pool, t.mayhem_enabled, t.mayhem_mode, t.mayhem_state, t.completed_at,
       t.migrated_at, t.migrated_pool, t.first_seen_source, t.last_seen_at
FROM meme_features_1m f JOIN meme_tokens t ON t.mint = f.mint;
```

`SELECT` para `hunter_app` e `hunter_worker`. A visão **não filtra tempo nem
ordena**: quem pagina é o chamador, e os predicados descem para a partição do mês
(`end_time`) ou para a PK (`mint`). Uma visão que embutisse `max(end_time)` viraria
varredura a cada requisição — por isso o "último minuto" é parâmetro da API, não
mágica da visão.

### 7. O que a T4.3 pode e não pode assumir

- **pode**: paginar por `end_time` (lista) e por `(mint, end_time)` (série); ler
  `meme_tokens` por PK; mostrar `first_seen_source`/`snapshot_source` como fonte,
  `observed_at` vs. `received_at` como atraso, `coverage` e
  `meme_ingest_gaps` como buraco declarado (critério de aceite da T4.3);
- **não pode**: somar volume, contar compradores ou afirmar "dev não vendeu" —
  as quatro colunas dependentes de trade/holders são `NULL` com motivo **hoje e
  em toda linha**, e um zero renderizado no lugar delas é exatamente o MUST-FIX 1
  da Astra;
- **não pode** ler `meme_trades` esperando linha: a tabela existe para o schema
  ficar inteiro, sem produtor nesta fatia;
- **não pode** escrever nada: `hunter_app` tem `SELECT` e mais nada nas cinco
  tabelas — um `INSERT` da API responde *permission denied*.

### §contrato — emendas

1. **`curve_reason` virou dois motivos** (`curve_reason` para o `mcap_sol`,
   `progress_reason` para o `curve_progress_pct`), descoberto ao escrever o
   produtor: com um motivo só, um mint cujo snapshot chegou mas cujo
   `initial_real_token_reserves` nunca foi observado tinha **mcap conhecido** e
   **progresso desconhecido**, e a bicondicional única obrigaria o coletor a
   jogar o mcap fora para caber no CHECK. Duas ausências com duas causas ganham
   dois motivos. A T4.3 renderiza os dois; o vocabulário não muda
   (`denominator_unknown` só aparece em `progress_reason`).
2. **(T4.2c, `0023_meme_boards_trades`) `meme_trades` tem produtor: `swap-api`** (`source =
   'swap_api'`). O que a resposta não traz fica **NULL**: `commitment` (a coluna passou a ser anulável
   — a `0021` escreveu `NOT NULL` para um decodificador on-chain que declara finalidade; o `swap-api`
   não declara), `outer_ix_index`, `inner_ix_index`, `is_mayhem_agent`. `slot` = os 12 primeiros
   dígitos do `slotIndexId` (verificado contra `getTransaction`); `event_index` = ordinal do trade
   entre os da mesma tx no lote gravado (0 em 230/230 linhas capturadas); `quote_mint` = SOL nativo
   (só entra linha `program = pump` com `quoteAmount == amountSol` exato em lamports);
   `token_decimals` = 6; `price` = `fillPriceSol` (a coluna `numeric(28,10)` arredonda a 10 casas —
   recompute de `sol_lamports/token_amount` quando a precisão importar).
3. **(T4.2c) `creator_sold` passou a ser coluna da fita**: *qualquer* venda de `meme_tokens.creator`
   na fita coberta até `end_time`; sua ausência é `no_trade_feed` (era `no_holders_reader`).
   `creator_net_seller` (nova, `Σ vendas − Σ compras > 0` em SOL) é o insumo da EXP-M1.
   `top10_share` vem do `t10` do board ou do `/in-memory-coin` (procedência em `holders_source`).
4. **(T4.2c) vocabulário de motivo ganha `no_sells`** (razão compra/venda sem vendas). Oito motivos.
5. **(T4.2c) `first_seen_source` ganha `trenches_ws`**: mint visto primeiro no board `new`/`graduating`
   do site; `created_at` dessa linha é `serverTs − age` (o contador do próprio site) e `creator` é o
   `dw` (dev wallet) da entrada — declarado, como o `received_at` do PumpPortal.
6. **(T4.2c) `meme_ingest_gaps.stream` ganha `trenches_ws`** (`reason = ws_reconnected`, `generation`
   = reconexões + ressincronizações do board): a janela cujas linhas de exposição são censuradas.
