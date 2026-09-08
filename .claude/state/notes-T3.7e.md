# notes-T3.7e — HOTFIX: `earliest_known` obsoleto dentro do ciclo retirava janelas legítimas como `before_listing`

Data: 2026-09-08. Autor: exchange-integration-specialist. Base: `main` em `50932ec` (T3.7d).
Escopo tocado: `services/market-worker/hunter_market_worker/{recovery,recovery_drain}.py`,
`services/market-worker/tests/test_recovery_contracts.py`, `docs/PIPELINE.md` §1b (item 11),
`infra/scripts/sql/2026-09-08-reopen-false-unrecoverable.sql` (criado, **não executado**).
`recovery_lifecycle.py` não foi tocado — nada no defeito exigia mudar `earliest()`,
`history_candidates()` ou `reopen_stale_failed()`. Nenhum arquivo em `infra/migrations/**` foi
tocado. Nenhum commit feito. Nenhum container local parado/recriado.

## O defeito (revisão do code-reviewer, confirmado em produção)

`check_gaps` lê `market_earliest` (o mínimo persistido por mercado) **uma vez por ciclo**
(`recovery.py:147`, antes desta correção). Quando `backfill_priority.interleave` concede a um
mercado mais de um slot do estrato histórico no mesmo ciclo — o que ele faz sempre que poucos
mercados disputam os seis slots, exatamente o cenário de
`test_a_market_with_a_small_backlog_is_never_starved_by_a_bigger_one` —, um pedaço mais novo
(`gap_end` maior, processado primeiro por `history_candidates`' `ORDER BY gap_end DESC`) podia ser
recuperado com sucesso e revelar que o mercado tem histórico mais antigo do que aquele mínimo
snapshot dizia. Um pedaço mais antigo do **mesmo mercado**, processado depois no mesmo ciclo, era
então comparado (`recovery_drain.py:109` e `:260`, antes) contra o valor **já obsoleto** e virava
`unrecoverable`/`before_listing` por engano — um estado terminal que a T3.7d deliberadamente nunca
reabre. Na VPS, às 14:00Z: BTCUSDT 5 `unrecoverable`, UNIUSDT 5 `unrecoverable`, ambos listados há
anos — janelas legítimas de agosto perdidas. Os market-workers foram revertidos para `385dac6` às
14:10Z até este hotfix.

## A correção (item 1) — por que "adiar", não "atualizar o mínimo em memória"

O brief oferecia duas formas: (a) atualizar `market_earliest[market_id]` em memória após cada
recuperação bem-sucedida, ou (b) a "regra mais simples": classificar `before_listing` só quando
nenhum pedaço daquele mercado foi recuperado neste ciclo, senão adiar a decisão para o próximo.
Escolhi uma variante **refinada** de (b), não a leitura mais literal — e registro por quê, porque
a leitura literal quebra um contrato já existente e válido:

- **Por que não (a).** Reconstruir "o novo mínimo verdadeiro" a partir de uma recuperação parcial
  exigiria confiar no `gap_start` (possivelmente estreitado pela lógica M2) do pedaço que acabou de
  recuperar, ou reler `earliest()` do Postgres por lacuna — o primeiro é frágil (o M2 só estreita
  para *dentro* do próprio intervalo pedido, nunca revela histórico além dele), o segundo custa uma
  ida ao banco por lacuna. Adiar para o próximo ciclo é simples e exato porque `check_gaps` já relê
  `earliest()` do zero a cada ciclo (60s) — o atraso é de no máximo um ciclo de detecção, aceitável
  para algo que, no incidente, já vinha acumulando havia horas.
- **Por que não a leitura literal de (b).** "Nenhum pedaço deste mercado foi recuperado neste
  ciclo" é ampla demais: no teste de contrato já existente
  (`test_check_gaps_classifies_pre_listing_history_and_recovers_post_listing_history`), a lacuna
  **pós**-listagem é recuperada primeiro (maior `gap_end`) e a lacuna **pré**-listagem, de fato
  `before_listing`, é processada depois — mas recuperar a pós-listagem não prova nada sobre a
  pré-listagem (seu `gap_start` está *depois* de `earliest_known`, não antes). Adiar cegamente
  nesse caso faria esse teste (uma classificação genuinamente correta) regredir para `open`/`failed`
  em vez de `unrecoverable`. A regra implementada é mais estreita e correta: o adiamento
  (`earliest_known_stale=True`) só se aplica quando um pedaço recuperado neste ciclo tem seu
  próprio `gap_start` **anterior** ao `earliest_known` do início do ciclo — a única situação em que
  esse pedaço prova que o mínimo real é mais antigo do que o snapshot diz. `recovery.check_gaps`
  agora carrega um `earliest_stale_markets: set[market_id]` por ciclo, populado a cada
  `recover_one` bem-sucedido cujo `gap_start` retornado é `< known`, e passado como
  `earliest_known_stale` para toda chamada seguinte daquele mercado no mesmo ciclo (estrato vivo e
  histórico, pelo mesmo helper interno `_recover_and_track`).

## A correção (item 3, MEDIUM do revisor) — exige a resposta vazia real da exchange

Antes desta task, `earliest_known` sozinho bastava para concluir `before_listing`
**antes de qualquer chamada REST**. O revisor apontou o caso em que isso é falso: um mercado com
velas recentes que acaba de receber `request_backfill.py --days 90` tem `earliest_known` igual ao
início da coleta *ao vivo*, não à listagem real — uma janela mais antiga que isso pode muito bem
ter dados de verdade. `recover_registered` não short-circuita mais antes do fetch: a janela é
buscada **exatamente uma vez**, e só uma resposta vazia real (`closed == []` após o filtro pela
própria janela) combinada com `gap_end < earliest_known` (e sem `earliest_known_stale`) conclui
`unrecoverable`/`before_listing`. Uma resposta não vazia segue o caminho normal (recupera ou
estreita via M2, item existente). Isso custa exatamente uma chamada REST por janela genuinamente
antes da listagem — nunca zero (como antes), nunca infinitas (a lacuna sai de `open`/`failed` assim
que classificada, e a classificação nunca reabre).

`recover_one` agora tem **um único caminho de fetch** (o antigo `if earliest_known is not None and
gap_end < earliest_known: <pula fetch>` foi removido) e retorna `(recovered: bool, gap_start:
datetime | None)` em vez de `None`, para que `check_gaps` saiba se e onde atualizar
`earliest_stale_markets`.

## Testes novos (`test_recovery_contracts.py`)

1. `test_a_window_older_than_earliest_known_is_still_fetched_and_recovered_if_data_exists` —
   item 3: uma janela mais antiga que `earliest_known`, mas com dados reais na exchange, é buscada
   uma vez e recuperada normalmente (nunca `before_listing`).
2. `test_check_gaps_does_not_misclassify_an_older_chunk_after_a_newer_one_moves_the_true_minimum` —
   item 2, reprodução exata do cenário do revisor via `recovery.check_gaps` fim a fim: mesmo
   mercado, dois pedaços do estrato histórico concedidos no mesmo ciclo; o mais novo recupera e
   revela histórico mais antigo que `earliest_known`; o mais antigo, cuja própria resposta REST
   nesse ciclo é vazia, **não** vira `unrecoverable` — fica `open` (uma tentativa gasta,
   `attempts=1`), sem nenhum `system_events` de `market_gap_unrecoverable` para aquele mercado.
   Confirmei que este teste falha sem a correção (a checagem de staleness sozinha) e também
   falharia com só a correção do item 3 (sem o adiamento) — a resposta vazia do pedaço antigo
   ainda satisfaria `gap_end < earliest_known` e cairia em `unrecoverable`.

Também atualizei `test_a_window_entirely_before_the_market_listing_becomes_unrecoverable` (T3.7d):
a asserção `adapter.fetch_candles_calls == []` virou `len(...) == 1` (a mudança do item 3 é
deliberada — zero REST deixou de ser a garantia; "no máximo uma vez, nunca infinita" é a nova),
e `gap.attempts == 0` continua válido (a resposta conclusiva desconta o `+= 1` do topo, igual ao
padrão já usado para outage de coordenação logo abaixo no mesmo arquivo).

## `docs/PIPELINE.md` §1b — nota sobre qual item foi editado

O brief pede "item 7"; a regra `before_listing` de fato vive no **item 11** (item 7 é a prioridade
vivo-antes-de-histórico, que só cita `before_listing` de passagem). Editei o item 11 — o primeiro
sub-bullet ("Sinal mais barato...") — por ser onde a regra está realmente descrita. Interpreto o
número do brief como referência solta ao mesmo tema, não um pedido literal de editar o item errado;
sinalizado como concern abaixo para confirmação.

## SQL do operador — não executado

`infra/scripts/sql/2026-09-08-reopen-false-unrecoverable.sql`: reabre `unrecoverable` cujo mercado
tem qualquer vela final anterior ao próprio `gap_start` da lacuna (prova estrutural de que o
mercado já existia, sem depender de `reason` — `ingestion_gaps` não guarda motivo). Idempotente
(WHERE só pega `status = 'unrecoverable'`, then/before counts). **Não rodei.**

## Provas

Todos os comandos abaixo rodaram em primeiro plano, um arquivo de teste por invocação de pytest
(a suíte usa testcontainers). Saída real de cada um está na mensagem de entrega ao agente
orquestrador. Resumo:

- `uv run ruff check` (arquivos tocados e o pacote inteiro `services/market-worker`): **all checks
  passed**.
- `uv run pyright` nos três arquivos tocados: **0 errors**. `pyright` sem escopo (rodado da raiz do
  pacote) reporta ~2417 erros pré-existentes em `packages/indicators/tests/**`, nenhum em
  `hunter_market_worker`/`recovery` — não relacionados a esta task, não tocados.
- `uv run python infra/scripts/check_file_size.py`: **0 arquivos acima do orçamento**.
  `recovery_drain.py` foi de 302 para 343 linhas (docstrings novas). `recovery.py`, de 346, passou
  por um pico de 365 depois das primeiras mudanças e teve que ser podado de volta a exatamente 350
  (o teto) — extraí `_recover_and_track` como helper interno para eliminar a duplicação entre o
  estrato vivo e o histórico, o que também deixou o código mais limpo, não só mais curto.
- As 46 suítes de `services/market-worker/tests/*.py`, uma invocação por arquivo: **todas
  passaram** (`test_backfill_lane.py` teve um `ConnectionResetError` de rede do Docker na primeira
  tentativa — reexecutada isoladamente, passou; não relacionado ao código tocado).

## Concern fora do escopo declarado — não corrigido

`tests/integration/test_market_recovery.py::test_five_failed_backfills_mark_the_gap_failed_and_it_reopens_after_cooldown`
falha (`assert reopened.attempts == 1` mas o valor real é `6`) porque o teste ainda espera o
comportamento **pré-T3.7d** ("`_reopen_stale_failed` reseta `attempts` a 0 ao reabrir" — o
comentário do próprio teste, linha 225). A T3.7d mudou deliberadamente esse comportamento
(`attempts` nunca mais é resetado num reopen). Este arquivo está fora do escopo declarado desta
task (`tests/integration/**`, não `services/market-worker/**`) e não foi tocado; provavelmente
quebrou já na T3.7d e ninguém atualizou este teste até agora. Reportado, não corrigido.

---

# T3.7f — re-revisão do hotfix acima: HIGH (staleness só em recuperação parcial),
# MEDIUM (SQL restrito ao incidente), e o `attempts` desatualizado do item anterior

Data: 2026-09-08. Autor: exchange-integration-specialist.
Base: a T3.7e acima, ainda não commitada — trabalhei sobre o mesmo diff, sem reverter nada.
Escopo tocado: `services/market-worker/hunter_market_worker/{recovery,recovery_drain}.py`,
`services/market-worker/tests/test_recovery_contracts.py`, `docs/PIPELINE.md` §1b (item 11),
`infra/scripts/sql/2026-09-08-reopen-false-unrecoverable.sql`,
`tests/integration/test_market_recovery.py` (item 3 do brief, exatamente o concern acima).
Nenhum outro arquivo tocado. Nenhum commit feito. Nenhum container local parado/recriado.

## Achado 1 (HIGH) — a checagem de staleness só olhava `gap.status == "recovered"`

A correção da T3.7e (`_recover_and_track` em `recovery.py`) só adicionava um mercado a
`earliest_stale_markets` quando o `recover_one` daquele pedaço retornava `recovered=True` — ou
seja, quando **100% dos minutos esperados** da lacuna já estavam persistidos. Isso deixava um
buraco real: uma recuperação **parcial** (o adaptador Binance, `rest.py:254`, para de paginar numa
página vazia no meio da janela — uma pausa de negociação genuína) insere velas mais antigas que
`earliest_known` mas não fecha a lacuna inteira (`gap.status` continua `open`). Sem contar isso, um
pedaço mais antigo do mesmo mercado, processado depois no mesmo ciclo com resposta vazia, ainda
virava `unrecoverable`/`before_listing` — exatamente o defeito que a T3.7e pretendia fechar,
sobrevivendo em um caso mais estreito.

**Correção:** `recover_registered` agora devolve o `open_time` mínimo que **realmente inseriu**
nesta chamada (`None` se não inseriu nada, inclusive em todo caminho de retorno antecipado —
`before_listing`, outage de coordenação), calculado só depois que a transação aninhada
(`session.begin_nested()`) confirma sem levantar exceção, para nunca contar uma inserção que acabou
sendo revertida. `collected=newly_inserted` passou a ser passado incondicionalmente para
`upsert_candles` (antes só no estrato `history`) — isso não muda o que é anunciado (`announce`
continua o parâmetro que decide isso), só o que essa lista recebe, para o estrato `live` também
alimentar o cálculo do mínimo. `recover_one` propaga esse valor em vez de `gap.gap_start`, e
`recovery.check_gaps._recover_and_track` marca `earliest_stale_markets` a partir dele
(`min_open_time is not None and min_open_time < known`), não mais de `recovered and gap_start <
known`.

Teste novo (`test_recovery_contracts.py`,
`test_check_gaps_marks_staleness_from_a_partial_recovery_not_only_a_full_one`): mesmo esqueleto do
teste irmão da T3.7e, mas o pedaço mais novo devolve todos os minutos esperados **exceto um** (uma
pausa real) — a lacuna fica `open`, nunca `"recovered"`, mas ainda persiste uma vela em
`newer_start` (< `earliest_known`). Confirmo que a vela foi persistida (`count == 1` em
`newer_start`) e que o pedaço mais antigo, cuja própria resposta REST é vazia, fica `open`
(`attempts=1`), nunca `unrecoverable` — sem `system_events`. Sem a correção este teste falha (o
pedaço antigo vira `unrecoverable`/`before_listing`).

## Achado 2 (MEDIUM) — o SQL de reabertura não distinguia `before_listing` de `exhausted`

A prova estrutural do SQL (mercado já tem vela final anterior ao `gap_start` da lacuna) é
correta **em si**, mas sozinha reabre **qualquer** lacuna `unrecoverable`, de qualquer
mercado/motivo, que por coincidência satisfaça essa condição — inclusive uma lacuna `exhausted`
(T3.7d item 3: `MAX_REOPEN_PER_CYCLE` excedido, sem nenhuma relação com `before_listing`) de um
mercado fora do incidente. `ingestion_gaps` não guarda `reason` (só `system_events` guarda) e o
modelo não tem `updated_at` (`IngestionGap` usa só `UUIDPrimaryKeyMixin`, sem o mixin de timestamp —
`packages/core/hunter_core/db/models/market_data.py:134-150`), então usei `detected_at` como pediu
o brief. Adicionei `JOIN markets m ON m.id = g.market_id` e, nas três consultas (antes/UPDATE/
depois), `AND m.symbol IN ('BTCUSDT', 'UNIUSDT') AND g.detected_at >= '2026-09-08 13:40'`, mantendo
a prova de vela-antes-do-`gap_start`, o antes/depois e a nota de idempotência. Cabeçalho novo
explica por que o filtro de escopo existe (não confiei só no texto do commit anterior).

Não executei o SQL (nem antes nem depois da mudança) — nenhum Postgres de VPS acessível daqui, e o
próprio arquivo diz "NÃO EXECUTAR sem revisão do operador".

## Achado 3 — `tests/integration/test_market_recovery.py:226` desatualizado

Exatamente o concern que a T3.7e já tinha reportado sem corrigir (fora do escopo dela). A asserção
`reopened.attempts == 1` datava de antes da T3.7d, que parou de zerar `attempts` num reopen. Troquei
para `reopened.attempts == recovery.MAX_ATTEMPTS + 1` (a constante já é acessada como
`recovery.MAX_ATTEMPTS` no mesmo arquivo, sem import novo) com um comentário explicando a mecânica:
o loop anterior já gasta exatamente `MAX_ATTEMPTS` tentativas antes de `failed`, e a chamada bem-
sucedida pós-reopen soma mais uma em cima disso, nunca reinicia de 1.

## `docs/PIPELINE.md`

Sub-bullet novo sob o item 11 (depois do sub-bullet da T3.7e), explicando o achado 1 e apontando
para o SQL do incidente. A frase da T3.7e que dizia "já recuperou candles que alcançam antes de
`earliest_known`" também foi ajustada para "já *persistiu* uma vela" — o texto antigo já sugeria
(incorretamente) que só uma recuperação completa contava.

## Orçamento de linhas — os dois arquivos já estavam/ficaram no teto

`recovery_drain.py` estava em 344 linhas (só T3.7e, ainda sob o teto de 350) antes desta task; as
mudanças de código + docstring desta rodada levaram a 373. Podei a prosa das docstrings
(`earliest_known`, `earliest_known_stale`, `recover_one`) sem tirar nenhuma explicação essencial até
349. `recovery.py` a T3.7e já tinha deixado em exatamente 350 (o teto); minhas mudanças (renomear
`recovered`→`_recovered`, reescrever a condição de staleness, os dois comentários) levaram a 354;
podei os dois comentários de bloco até 350 de novo. `check_file_size.py` confirma **0 arquivos acima
do orçamento** no repo inteiro depois da poda.

## Provas

Todos os comandos rodaram em primeiro plano, um arquivo de teste por invocação de pytest (testcontainers
compartilhado com outros agentes), exatamente os arquivos tocados mais `test_recovery.py` como pedido.

- `uv run ruff check` (os quatro arquivos tocados + `services/market-worker` inteiro): **all checks
  passed**.
- `uv run pyright` nos quatro arquivos tocados: **0 errors, 0 warnings**. `uv run pyright
  services/market-worker` (pacote inteiro, para garantir que nenhum outro chamador de
  `recover_registered`/`recover_one` quebrou com a mudança de assinatura de retorno): **0 errors**.
- `uv run python infra/scripts/check_file_size.py` (repo inteiro): **0 arquivos acima do
  orçamento, 0 grandfathered** (543 arquivos escaneados).
- `services/market-worker/tests/test_recovery_contracts.py`: **16 passed** (inclui o teste novo do
  achado 1), 2 `SAWarning` de conexão não fechada explicitamente — pré-existentes, não relacionados.
- `services/market-worker/tests/test_recovery.py` (pedido pela regra operacional, não tocado):
  **8 passed**.
- `tests/integration/test_market_recovery.py`: **2 passed** (inclui a asserção corrigida do
  achado 3).

## Concerns

1. Não executei o SQL corrigido contra Postgres real (nem sintaticamente, via `psql --dry-run` ou
   equivalente) — só revisão visual. Sintaxe `UPDATE ... FROM ...` é PostgreSQL padrão, mas
   recomendo o operador rodar as duas primeiras `SELECT` (antes/depois) manualmente antes do
   `UPDATE` de qualquer forma, como o próprio cabeçalho já pede.
2. Não verifiquei se `BTCUSDT`/`UNIUSDT` existem em mais de uma exchange na tabela `markets` (o
   incidente foi especificamente Binance, mas o filtro do brief não pediu restrição por
   `exchange_id`, e adicioná-la unilateralmente divergiria do que foi pedido). Se houver mais de uma
   exchange com esses símbolos monitorados, o SQL reabriria lacunas de ambas — o operador deveria
   confirmar isso antes de rodar.
3. Não toquei `recovery_lifecycle.py` nem `backfill_priority.py` — nada nos três achados exigia
   mudar `earliest()`, `history_candidates()` ou `interleave()`.
