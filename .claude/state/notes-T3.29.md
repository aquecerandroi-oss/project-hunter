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


---

# T3.29b — fecha a revisão REQUEST_CHANGES da T3.29 (risk-engine-guardian, 2026-09-08)

Base: `main` em `56038a8`, árvore compartilhada. **Nada commitado.** VPS somente leitura
(nenhuma leitura nova foi necessária nesta rodada; nada foi escrito).

## 1. Achado 1 (HIGH) — a corrida de relógios no `avgPrice`

**O que era.** `Cycles.entries()` lê o seu `now` (`cycles.py:206`) e **só depois** monta a
foto do mercado; `ExchangeAvgPrice.read()` carimba `observed_at` com o **seu** relógio, que
é lido dentro desse `data.snapshot(...)` — sempre depois. A cada expiração do cache de 5 s a
idade medida em `entry_inputs.stale_average` saía **negativa**, e a regra antiga
(`if age < 0 or age > 30: "avg_price_stale"`) recusava como vencida uma cotação recebida
milissegundos antes. Com o adiamento repetindo a cada passo, a reserva de 30 s expirava e a
entrada nunca acontecia.

**Reproduzido, não deduzido.** Com a regra antiga restaurada de propósito, o teste de ciclo
completo (Postgres real, `RedisSpotMarketData` real, `utcnow` real no leitor) devolveu:

```
>       assert [(o.status, o.reason) for o in outcomes] == [("filled", "")], [
E       AssertionError: [('deferred', 'avg_price_stale')]
```

**O que passou a valer.** `AVG_PRICE_MAX_SKEW_S = 2.0` (`avg_price.py`): um carimbo à frente
do `now` do ciclo até 2 s é **fresco** e o evento é contado
(`hunter_execution_avg_price_clock_skew_total{outcome="tolerated"}`); acima disso os dois
relógios de fato discordam e a entrada adia com **`avg_price_clock_skew`**, contado como
`refused`. O nome é novo de propósito: "velho demais" e "à frente do ciclo" mandam o
operador a lugares diferentes (endpoint lento × NTP do host), e chamar os dois de
`avg_price_stale` era proveniência mentindo. O limite duro de 30 s e o `avg_price_undated`
não mudaram.

**Um relógio, não dois (`main.py`).** `run_execution` passa a **mesma** callable para o
leitor e para os ciclos (`_avg_price_reader(runtime, clock=clock)` e
`Cycles(..., clock=clock)`). Hoje isso **não muda comportamento** — os dois já eram
`utcnow` — e é dito assim para não parecer correção do bug: o que corrige o bug é a
tolerância acima. O que a injeção fecha é a divergência futura: um `Cycles` dirigido por
relógio de teste/replay com o leitor ainda em `utcnow` produziria uma diferença de anos, e
**toda** entrada adiaria por `avg_price_clock_skew`.

**Por que 2 s.** Uma ordem de grandeza abaixo do limite duro (30 s) e muito acima de
qualquer atraso de agendamento dentro de um passo — absorve a ordem que o ciclo cria sem
nunca admitir uma referência de outro minuto.

## 2. Achado 2 (HIGH) — a pré-checagem `marks_incomplete` da ponte, com a volta

`test_bridge_cycle.py::test_a_wallet_it_cannot_price_defers_the_slot_and_admits_it_back_when_marks_return`:
carteira com **uma posição preenchida**; a fita do mercado dela para (negócio de 1 h antes,
fora do orçamento da política de marcação) ⇒ cobertura 0 de 1 ⇒ o candidato de **outro**
mercado é `deferred == "marks_incomplete"`, `submitted is None`, e a contagem de
`trade_proposals` continua 1 (nada escrito, slot não gasto). No passo seguinte a fita volta
⇒ cobertura 1 de 1 ⇒ o **mesmo** sinal é submetido e aprovado, contagem 2. Sem intervenção.

**O teste refuta de verdade.** Com o bloco `if not coverage.complete: _defer(...)` removido
de `bridge.py` de propósito:

```
>       assert deferred.submitted is None
E       AssertionError: assert AdmissionResult(... unavailable=('marks',)) is None
```

— isto é: sem a pré-checagem a ponte **escreve** uma proposta decidida (recusada pelo motor
puro por `marks`), queimando o sinal numa fita transitória em vez de adiá-lo.

## 3. Achado 3 (MEDIUM) — as regras no documento-fonte

`docs/RISK_ENGINE.md` vira **v2.3** com uma seção nova, §7.1 "Insumos do caminho de execução
— as três pré-checagens do worker", e uma §9.4 dizendo o que mudou. **Nenhum limite do
Everton mudou de valor e o motor puro não ganhou insumo nenhum**: as três regras são do
`execution-worker` e estão no contrato porque são a aplicação literal da R-OPS-2 e da regra
3 da diretiva ao caminho que gasta dinheiro — e porque o código as citava contra "§7,
R-OPS-2" sem que elas existissem aqui.

1. **`avgPrice`** como referência do filtro `NOTIONAL`, com os dois prazos publicados numa
   tabela (reuso 5 s = custo; limite duro 30 s = a vida da reserva) mais a tolerância de
   relógio de 2 s, e os cinco motivos de adiamento distintos (`avg_price_not_collected`,
   `_unavailable`, `_undated`, `_stale`, `_clock_skew`).
2. **`mark_quality`** como pré-checagem de admissão, com a consequência escrita em vez de
   escondida: *uma única posição ilíquida adia todas as admissões novas daquela carteira até
   as marcas voltarem* — e é reversível sozinha. **Saídas de proteção nunca são afetadas.**
3. **`hot_state_unreachable`**: Redis ilegível adia a entrada e **não** derruba o passe —
   antes um `ConnectionError` numa chave abortava o passe inteiro, inclusive a proteção das
   outras carteiras, que é o que a regra 3 proíbe.

`docs/ACTIVATION.md` §8 ganha a mesma nota em forma operacional: uma tabela
`nome no log → o que aconteceu → o que o operador faz`, com a métrica de skew (`refused`
tem de ficar em zero; `tolerated` sobe de propósito, ~1 por janela de reuso por mercado).

## 4. Achado 4 (LOW) — `avg_price_undated` provado fim a fim

`StaticSpotMarketData` ganhou `stamp_avg_price: bool = True`. O default é o de sempre (uma
foto entregue por fixture é **um** instante, então o dublê carimba com o recibo do livro);
`False` é a **recusa explícita de carimbar**, que é a única maneira de um fixture alcançar
`avg_price_undated`. O par de testes em `test_entry_guards.py` usa a **mesma** foto nos dois
lados: com carimbo ⇒ `filled`; sem carimbo ⇒ `("deferred", "avg_price_undated")`, zero
`orders` e zero `positions`. Antes disso a regra do §7 ("preço sem idade não é insumo") só
era exercitável contra um snapshot montado à mão, e um teste futuro podia ser enganado pelo
carimbo silencioso do dublê.

## 5. Arquivos

Produção: `services/execution-worker/hunter_execution_worker/{avg_price,entry_inputs,market_data,metrics,main}.py`.
Testes: `services/execution-worker/tests/{test_avg_price,test_entry_guards,test_bridge_cycle}.py`.
Docs: `docs/RISK_ENGINE.md` (v2.3, §7.1 e §9.4), `docs/ACTIVATION.md` (§8).
`cycles.py` e `bridge.py` **não** mudaram (foram tocados só nas reversões temporárias que
provaram os dois testes, e restaurados byte a byte — `git diff` limpo nos dois).

## 6. Testes (saída real)

```
uv run pytest services/execution-worker/tests/test_avg_price.py -q              -> 23 passed in 3.13s
uv run pytest services/execution-worker/tests/test_entry_guards.py -q           ->  7 passed in 55.01s
uv run pytest services/execution-worker/tests/test_bridge_cycle.py -q           ->  8 passed in 99.09s
uv run pytest services/execution-worker/tests/test_mark_quality.py -q           ->  9 passed in 2.94s
uv run pytest services/execution-worker/tests/test_manual_request_decided.py -q ->  1 passed in 25.57s
uv run pytest services/execution-worker/tests/test_order_cycle.py -q            ->  2 passed in 28.30s
uv run ruff check .                                                             -> All checks passed!
uv run ruff format --check services/execution-worker                            -> 64 files already formatted
uv run pyright services/execution-worker                                        -> 0 errors, 0 warnings
uv run python infra/scripts/check_file_size.py                                  -> 1 over budget (não é meu, §7)
```

`test_order_cycle.py` é um arquivo a mais do que o brief listou: mexi em `entry_inputs.py` e
`market_data.py`, que **todo** o caminho de entrada usa, e uma invocação extra pareceu barata
perto de entregar uma mudança de caminho de dinheiro sem nenhum vizinho verde. Declarado como
desvio, não escondido.

## 7. Pendências e ressalvas

1. **`check_file_size.py` está vermelho por mudança de outro agente**, não desta tarefa:
   `packages/core/hunter_core/db/models/agents.py` tem 371 linhas na árvore de trabalho e
   **346 em `HEAD`** (`git show HEAD:... | wc -l`). Não toquei `packages/**`. Quem commitar
   aquele arquivo precisa fechar o orçamento antes.
2. **A tolerância de 2 s é um relaxamento real da §7** ("carimbo no futuro é `unavailable`"),
   e por isso está escrita no contrato e contada numa métrica em vez de embutida em
   silêncio. Se `outcome="refused"` sair de zero em produção, é relógio do host, não mercado.
3. `stale_average` deixou de ser função sem efeito colateral: ela incrementa o contador de
   skew. É módulo do worker, não do motor puro (`packages/risk-core` continua sem rede, sem
   banco, sem relógio e sem métrica). O caminho de expiração (`_deferral_reason`) chama
   `missing_inputs` de novo, então um mesmo passo pode contar duas observações de skew — é
   contador de diagnóstico, não de dinheiro.
4. `test_entry_guards.py::TestTheCycleClockAndTheReadersStampDoNotRace` roda no **relógio
   real** (é o único jeito de o carimbo do leitor cair depois do `now` do ciclo). Ele abre a
   carteira e decide em `utcnow() - 1 s`, então uma execução que atravessasse exatamente a
   meia-noite de São Paulo dentro dessa janela de 1 s veria `daily_reference` indisponível.
   Janela de falha: ~1 s por dia. Registrado em vez de escondido.
5. As pendências 1 a 6 da T3.29 (β do BTC, `agents`, restore real, `risk_profiles.paper_v1`,
   `DATABASE_URL_MIGRATIONS`, deploy) continuam **todas abertas** — nada nesta tarefa as tocou.
