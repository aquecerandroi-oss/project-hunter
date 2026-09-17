# T4.45 — o dado de risco existe no instante da decisão

**Data:** 2026-09-16. **Escopo:** adaptador pump.fun (ingest), `0048`, worker (uma coluna no upsert),
executor (duas leituras sob demanda), `hunter_core` (o escritor compartilhado da linha de risco).
**Nenhum check, nenhum limiar e nenhuma janela de frescor mudaram.** Com as duas leituras falhando, o
comportamento é bit a bit o de ontem.

## 1. As medições em que me apoiei (não refiz nenhuma)

`obsidian/03-TRADING/Meme/Balanco-2026-09-16-mesa-real.md` (R39) e
`obsidian/03-TRADING/Meme/Estudo-2026-09-16-admissao-real-o-que-recusa.md` (R5):

| medição | valor |
|---|---|
| ordens reais do dia | **58**, 29 moedas, **58 recusadas, 0 fills** |
| recusas por **dado ausente** | **28 / 58 (48 %)** — `creator_flow_unknown` 27 + `bundled_share_unmeasurable` 1 |
| ordens com retrato de risco na hora da decisão | **5 / 58 (8,6 %)** |
| `meme_risk_snapshots` do mint × 1ª ordem | mediana **+103 s** (R5) |
| `creator_sold` não-nulo × criação | **+123 a +441 s**; a entrada acontece entre 30 e 300 s |

## 2. O que mudou

### 2.1 Parte A — o executor lê o risco por conta própria

`risk_read.py` (novo): sem linha fresca em `meme_risk_snapshots`, o executor lê o **mesmo**
`GET /in-memory-coin/{mint}` com o **mesmo** cliente do adaptador e persiste pelo **mesmo** escritor,
agora em `hunter_core.db.meme_risk_snapshots` (movido de `hunter_meme_worker.repo_boards`, que passou a
reexportá-lo — um INSERT, duas escritoras). `source = indexer_rest:/in-memory-coin:executor_on_demand`.

Dois caminhos usam a leitura: a **admissão** (cobre o clique do humano, `admission_context.py`) e o
**passe do estágio 1** (`ensure_snapshots`, chamado só para os mints que o planejador *abriria* neste
tique — a leitura não é gasta num mint que o `too_old`/`mint_busy`/`recently_refused` já descartaria).

Freios: prazo duro **1,5 s** (`MEME_RISK_READ_TIMEOUT_S`); no máximo **uma** leitura por mint a cada
**600 s**, contando as que falharam (o livro de tentativas é em memória porque uma falha não deixa linha;
podado pela própria janela); leitura sem `bundled_share` é gravada mas **não** conta como medida.
Falha ⇒ `risk_snapshot_pending` continua sendo o skip e o check 11 continua recusando.
Heartbeat: `risk_reads_on_demand`, `risk_reads_on_demand_failed`.

### 2.2 Parte B — o fluxo do criador pela cadeia, contra a compra registrada do dev

`initialBuy`/`solAmount` do frame `create` → `NormalizedMemeTokenCreated` → `TokenRow` → `meme_tokens`
(`0048`: `creator_initial_tokens` em **tokens**, `creator_initial_sol` em SOL, escrita única, CHECK de
não-negativo, downgrade guardado). **A unidade não é suposição:** `1 073 000 000 − initialBuy ==
vTokensInBondingCurve` fecha ao último dígito na captura ao vivo (linha 6, `HTEqdy7k…`).

Na admissão (`creator_flow.py` + `admission_context.py`): com `creator_sold` do fold ainda `NULL` **e**
base conhecida `> 0`, uma leitura da ATA do criador (`confirmed`, 1,5 s, o `token_account` que o executor
já usa) decide `creator_net_sol = −1` se o saldo < `inicial × (1 − MEME_CREATOR_SELL_TOLERANCE_PCT)`
(padrão 0,02) e `+1` caso contrário; `creator_flow_source = 'chain_ata_vs_initial'` no JSON da admissão,
com a base, o saldo, a tolerância e o instante.

**É exatamente o que a T4.28g §2.3 dizia faltar** (a base da criação). Com ela, o criador que largou tudo
aos 20 s lê **−1** (`creator_net_seller`), não `+1`. Ordem de precedência: fita > cadeia > nada — um
`creator_sold` conhecido nunca é revisto por um saldo, e sem base nada é derivado.

## 3. A expectativa medida — e o que ela **não** promete

Sobre as 58 ordens de hoje, se as duas leituras existissem **e** as moedas tivessem a base gravada:

| | hoje | com T4.45 |
|---|---:|---:|
| recusadas por **ausência de dado** | **28** (27 + 1) | **0** — as 28 passam a ser decididas por um número |
| ordens com `bundled_share` para julgar | 5 / 58 | até 58 / 58 (o que o endpoint responder em 1,5 s) |
| recusadas por **valor medido** | 30 | 30 + o que as 28 virarem |

**Decidido com dado ≠ aprovado.** Pelo desfecho do R39, 16 das 29 moedas eram recusa **boa** (a curva
perdeu ≥ 50 % do SOL real em 30 min): boa parte das 28 deve continuar recusada — agora por
`creator_net_seller` ou `bundled_share_above_cap`, que são juízos, não silêncios. O ganho desta tarefa é
**a mesa parar de recusar por não perguntar**, não uma tese de que comprá-las dá lucro.

**Três limites honestos:**

1. **Nada disto é retroativo.** `0048` não tem backfill e não deve ter: para as moedas de hoje o dado não
   é recuperável sem mentir (`meme_trades` começa ~100 s depois da criação; o REST só tem a foto
   corrente). Só as moedas **criadas depois do deploy** têm a base, e a mesa propõe moedas de 30–300 s de
   vida, então na prática isso é "a partir do próximo mint".
2. **Isto não toca o defeito do progresso** que o R39 §2c mediu (o admissor lendo −5×10⁵ %, 13 recusas).
   Fora do escopo desta tarefa, continua vivo.
3. **Nada foi medido em produção.** Os números da §3 são aritmética sobre o R39, não medição desta
   mudança. O que medirá: `risk_reads_on_demand{,_failed}` no heartbeat e a distribuição de
   `meme_live_orders.reason` do próximo dia.

## 4. O que fica declarado

- **Orçamento compartilhado do indexador.** O worker gasta ~16 req/min do balde de 60/min do
  `/in-memory-coin`; o executor agora gasta até 1 por proposta aberta, com o teto de 1/mint/600 s. Os dois
  baldes são **independentes** (o `TokenBucketRateLimiter` do worker é em memória, sem Redis), então a
  soma não é coordenada. Bounded, mas não coordenada — se o `429` aparecer, o caminho é dar Redis aos
  dois limitadores, não afrouxar o teto.
- **`test_migrations.py` precisa de um `HEAD_REVISION = "0048_meme_creator_initial_buy"`.** Não o toquei
  (outra tarefa o estava commitando); o teste desta revisão está em
  `packages/core/tests/integration/test_migration_0048.py`, e enquanto a constante não subir as
  asserções de head daquele arquivo ficam vermelhas.
- **Um `to_thread` que estoura o prazo não é cancelado.** A leitura da ATA é síncrona (é o cliente do
  submissor); no timeout a corrotina para de esperar e a admissão segue **sem** o fluxo — a resposta
  atrasada é descartada, nunca aplicada a uma decisão que já aconteceu.
- **A permissão da T4.28h continua como está** (desligada por padrão). Ela deixa de ser necessária no caso
  comum; revogá-la não é decisão minha.

- **Com o kill switch bloqueando, nenhuma leitura é gasta.** A resposta seria descartada pelo check 1
  três linhas depois, e o balde do `/in-memory-coin` é o mesmo do radar, que continua marcando as
  posições abertas que o switch **não** para (`TestTheKillSwitch`).
