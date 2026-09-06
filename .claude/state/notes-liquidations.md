# Liquidações — correção de semântica `q`/`z`, `p`/`ap` (KB-0017)

Contexto: `obsidian/11-KNOWLEDGE/KB-0017-liquidacoes-o-fluxo-forcado-que-observamos-por-amostragem.md`
(Sexta-feira, 2026-09-06). Parecer da Astra: `.claude/state/astra-review-liquidation-qty.md`.

## O bug

`hunter_exchanges/binance/streams.py::parse_force_order` calculava
`qty = o.q` (quantidade **original** da ordem de liquidação) e `price = o.p`
(preço da ordem), com `notional = q × p`. A Binance distingue isso do que de
fato executou: `o.z` (quantidade executada acumulada) e `o.ap` (preço médio
de execução). Uma ordem original de 10 BTC, executada em 1 BTC
(`X = "PARTIALLY_FILLED"`), virava `notional` de "10 × preço" no nosso banco
contra 1 BTC realmente liquidado — superestimava o fluxo forçado sempre que
a ordem não fechava 100%.

## A correção (`streams.py`, `parse_force_order`)

- `qty = o.z` sempre (nunca `o.q`).
  - `X == "FILLED"`: `z == q`, então o valor não muda para ordens que já
    fechavam 100% (mas o **preço** pode mudar — ver abaixo).
  - Preenchimento parcial: `qty` cai para o executado real, menor que antes.
  - Nada executado ainda (`z == "0"`, `X` != `FILLED`, ex. `X == "NEW"`):
    `qty` fica um `Decimal("0")` explícito. Decisão tomada: **nunca** cair de
    volta para `o.q` nesse caso — uma ordem de liquidação que ainda não
    negociou não é fluxo forçado, é só uma ordem posta.
- `price = o.ap` quando presente e diferente de zero; senão `o.p`.
  - `o.ap` vem `"0"` quando nada executou (mesmo caso do `z == 0` acima) —
    aí não há preço médio para calcular e caímos em `o.p`.
  - Importante: mesmo com `X == "FILLED"`, `o.ap` pode diferir de `o.p`
    (fixture `ws_force_order.json`: `p=79210.50`, `ap=79215.00`) — o preço
    médio de execução é o correto a guardar, não o preço da ordem.
- `notional = qty × price` recalculado com os dois valores corrigidos.
- `event_id`/identidade natural: **não mexi**. `exchange`, `symbol`, `side` e
  `ts` continuam derivados exatamente da mesma forma (`o.s`, `o.S`, `o.T`),
  só `qty`/`price`/`notional` mudam de fonte. Teste
  `test_parse_force_order_identity_fields_are_unaffected_by_the_qty_price_fix`
  em `packages/exchange-adapters/tests/unit/test_streams.py` prova isso para
  os quatro campos que não usam `q`/`z`/`p`/`ap`.

## Fixtures novas

`packages/exchange-adapters/hunter_exchanges/testing/fixtures/`:
- `ws_force_order.json` (já existia, `FILLED`, `p != ap`) — teste atualizado
  para esperar `price == ap`.
- `ws_force_order_partial.json` (novo, `PARTIALLY_FILLED`, `q=10`, `z=1`).
- `ws_force_order_unfilled.json` (novo, `NEW`, `z=0`, `ap=0`).

## Impacto na identidade (`liquidation_id`) — fora do meu escopo, documentado aqui

`services/market-worker/hunter_market_worker/publication.py::liquidation_id`
(arquivo em `services/**`, **não toquei** por estar fora do escopo desta
tarefa) calcula `uuid5` sobre
`(exchange, symbol, side, price, qty, ts_ms)` — ou seja, `price` e `qty`
**fazem parte do hash de identidade**, não só `(id, ts)` como par de chave
primária.

Consequência direta desta correção: o hash muda em relação ao que o parser
antigo teria produzido para o **mesmo** payload sempre que:
- a ordem não é `FILLED` (qty muda de `q` para `z`), **ou**
- `ap != p`, mesmo em ordem `FILLED` (o caso do próprio `ws_force_order.json`).

Ou seja: na prática, quase toda liquidação nova vai gerar um `id` diferente
do que o parser antigo geraria para o mesmo evento cru.

**Por que isso não duplica linhas antigas, na prática:** o `forceOrder` da
Binance não tem recuperação via REST (não há endpoint público de histórico
de liquidação que o adapter chame em reconexão/gap — confirmado: não há
`ingestion_gaps`/recovery para o canal `LIQUIDATIONS` em
`hunter_exchanges/binance/ws.py`). Uma mensagem WS só é parseada **uma vez**,
pela versão de código rodando naquele instante. Não existe um caminho de
reprocessamento que pegue uma mensagem já persistida com o parser antigo e a
reapresente ao parser novo — então não há colisão prática de "linha antiga
reaparecendo com id novo".

**Ressalva da Astra (aceita, não corrigida em código por estar fora do
escopo — `services/**`):** essa conclusão depende de não haver dois
processos/coletores lendo o mesmo frame WS ao mesmo tempo durante uma
sobreposição de deploy (ex.: rolling restart com duas instâncias do
market-worker conectadas ao mesmo stream por um instante). Isso é uma
propriedade do **orquestrador de deploy do market-worker**, não do parser —
fica registrado aqui para quem mexer em `services/market-worker` ou no
runbook de deploy.

## Limitação nova, ainda não existente antes desta correção (achado da Astra)

`o.z` é **acumulado por ordem**, não incremento. Se a mesma ordem de
liquidação aparecer em mais de uma mensagem `forceOrder` ao longo do tempo
(ex.: `z=1` numa janela, depois `z=2` na janela seguinte, mesma ordem ainda
enchendo), cada mensagem tem `qty` diferente ⇒ `id` diferente (o hash inclui
`qty`) ⇒ **duas linhas na tabela** `liquidations`, com `qty` 1 e 2. Somar a
coluna `qty`/`notional` nesse caso dá 3, quando o executado real final da
ordem é 2 — um **novo tipo de overcounting**, desta vez por reaparição da
mesma ordem em snapshots sucessivos, não pela semântica `q` vs `z` que esta
correção resolveu. Isso não foi criado por esta correção (o parser antigo
também tratava cada mensagem como evento independente), mas fica mais visível
porque agora `qty` reflete execução real e cresce entre mensagens da mesma
ordem, em vez de ficar fixo em `q`. **Não implementei correção** (exigiria
mexer em `services/market-worker`, fora do escopo desta tarefa) — registro
como item de auditoria para quem tratar a T2.3/consumo analítico da tabela
`liquidations`: a leitura correta de "quanto uma ordem liquidou" não é somar
todas as linhas com o mesmo `(exchange, symbol, side)` próximas no tempo, é
pegar o `z` mais recente por ordem (que hoje não temos como identificar sem
um id de ordem — `forceOrder` não traz `o.i`).

## Histórico já persistido — não reescrito

As 8.421 linhas já gravadas na VPS até 2026-09-06 (leitura da KB-0017: 3.864
`buy` / 4.557 `sell`, 197 mercados) usam a semântica antiga (`qty = q`,
`price = p`, `notional = q × p`). **Não foram e não devem ser reescritas**
por esta tarefa — não haveria como recuperar `z`/`ap` retroativamente a
partir do que já está no banco (o dado cru `o.z`/`o.ap` do momento não foi
arquivado, só o resultado `q × p`).

Recomendação para quem ativar o detector `LIQUIDATION_CLUSTER`
(`liquidation_pressure_1h`, hoje desarmado com `enabled=False` e motivo
externo `detector_disabled` — `packages/indicators/hunter_indicators/anomalies/detectors.py:185,237`,
contrato de motivo em `anomalies/evaluation.py:154`, conforme já registrado
na KB-0017): **usar só linhas com `ts` a partir do deploy desta correção**
(ver data/commit no `git log` deste arquivo) para qualquer feature ou
threshold calibrado em `qty`/`notional`. Misturar as duas semânticas na
mesma série temporal produziria um degrau artificial na intensidade medida
que não é uma mudança de mercado. Não existe hoje um campo de "versão do
parser" gravado por linha em `liquidations` — se o consumidor da T2.3
precisar diferenciar automaticamente em vez de um corte fixo por data, isso
exigiria um campo novo na tabela (`services/**`/`packages/core` `Liquidation`
model), que também está fora do escopo desta tarefa.

## Parecer da Astra (curto)

`.claude/state/astra-review-liquidation-qty.md`. Concorda com a semântica
(`z` obrigatório, zero preservado como zero explícito, `ap` preferencial com
fallback só para `p`, notional recalculado) e com a leitura de que não há
risco prático de duplicação por não haver replay do mesmo frame WS — sob a
premissa de não haver dois coletores processando o mesmo frame em paralelo
durante um deploy. Sinalizou três pontos incorporados acima: registrar o
corte histórico com commit/horário exatos (não apenas a contagem de 8.421 da
KB-0017, que é uma fotografia anterior), deixar claro que o fallback
`z × p` (sem `ap`) não garante notional efetivamente executado, e o
overcounting por `z` acumulado reaparecendo em mensagens sucessivas da mesma
ordem (seção acima).

## Testes

`packages/exchange-adapters/tests/unit/test_streams.py`:
`test_parse_force_order`, `test_parse_force_order_uses_executed_qty_not_original_qty_on_partial_fill`,
`test_parse_force_order_reports_zero_qty_when_nothing_executed_yet`,
`test_parse_force_order_falls_back_to_order_price_when_ap_key_is_absent`,
`test_parse_force_order_missing_z_raises_malformed_message`,
`test_parse_force_order_identity_fields_are_unaffected_by_the_qty_price_fix`,
mais o existente `test_parse_force_order_still_defaults_notional_to_qty_times_price`
(genérico, continua passando com qualquer fonte de qty/price).

`uv run pytest packages/exchange-adapters -q` — 264 passed, 3 skipped (live,
não roda offline).
`uv run pytest services/market-worker -q -k liquidation` — 8 passed (usam
builders sintéticos, não o parser Binance — confirma que a correção não
quebra a persistência).
`uv run ruff check packages/exchange-adapters` — all checks passed.
`uv run pyright packages/exchange-adapters` — 0 errors, 0 warnings.
