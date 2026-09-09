# notes-T3.65 — a cadência de funding lê a corrida recente, não a moda da janela inteira

**Data:** 2026-09-09 (UTC; **Brasília = UTC−3** — todo horário desta nota aparece nas duas réguas).
**Owner:** exchange-integration-specialist. **Origem:** plantão de mercado 2026-09-09 17:00 (faixa 1,
item 3, `.claude/state/plantao/2026-09-09-1700-lane1.md`), must-fix da Astra
(`.claude/state/astra-review-plantao-20260909-1700.md`).
**Nada commitado. Nada indexado. Nenhum `.env*` tocado. Nada escrito fora dos arquivos listados
abaixo.** VPS: só leitura, três `SELECT` em transação `repeatable read read only`; nenhuma escrita,
nenhum container tocado.

---

## STATUS

**DONE.**

| # | Entrega do brief | Resultado |
|---|---|---|
| 1 | Reproduzir com teste unitário (histórico 8h depois 4h → cadência errada hoje) | **OK**, §1. Confirmado o falso zero rodando o teste contra o código antigo (moda global) antes de aplicar a correção |
| 2 | Corrigir: cadência da corrida recente consistente, nunca a moda global; registrar a cadência usada no envelope | **OK**, §2. `_CADENCE_RECENT_GAPS = 3`; `interval_s` já era gravado em `meta.funding.interval_s` — a correção o torna correto, não introduz campo novo |
| 3 | Medir na VPS quais símbolos monitorados mudaram de cadência desde 2026-09-01 e quantas funding features seriam mal custadas | **OK**, §3. **Zero** dos nove símbolos do anúncio está em `markets`; **zero** mercado monitorado teve mudança de cadência detectável na janela — impacto medido hoje é **zero**, o risco é para o futuro |
| 4 | Testes, ruff/pyright/check_file_size.py, um testcontainer no máximo; `docs/PIPELINE.md` §1 | **OK**, §4. 24/24 testes verdes, ruff/format/pyright limpos, `check_file_size.py` 0 sobre o teto (funding.py: 350/350 linhas, no limite exato), um testcontainer usado (`test_settle.py`/`test_recompute_funding.py`) |

---

## 1. Reprodução do falso zero

`services/strategy-worker/hunter_strategy_worker/funding.py::_cadence()` tomava a moda de **todos**
os gaps entre settlements observados na janela de `_CADENCE_LOOKBACK` (3 dias, `settle.py:32`). Um
mercado cuja cadência muda de 8h para 4h no meio dessa janela (exatamente o caso da Binance,
2026-09-04 08:15Z) mantém a moda em 8h enquanto os gaps antigos superarem os novos em contagem — na
prática, por quase os 3 dias inteiros da janela.

Cenário reproduzido em `TestCadenceTransition` (`services/strategy-worker/tests/test_funding.py`):
nove settlements de 8h (horas 0–72) seguidos de dois settlements reais de 4h (76, 80) — o mercado já
completou dois períodos inteiros na nova cadência. Entrada às 81h, saída às 85h: a grade real de 4h
diz que a hora 84 estava devida, mas essa linha nunca chegou a `funding_rates` (falha de coleta, gap
de ingestão, o que for). A moda global (9×8h contra 2×4h) continua lendo 8h; a partir da âncora 80h,
o próximo instante nominal de 8h cai em 88h — depois da saída — então nada é sinalizado como faltante
e a leitura volta como **zero pago**, um número fabricado.

Rodei o teste **contra o código antigo** (substitui `_cadence()` temporariamente pela moda global,
sem tocar o resto do arquivo) para confirmar o diagnóstico antes de corrigir — não é hipotético:

```
E       AssertionError: false zero: a settlement the market's *current* 4h cadence predicted at hour 84 is missing from history, got Decimal('0')
E       assert Decimal('0') is None
E        +  where Decimal('0') = FundingReading(per_unit=Decimal('0'), reason=None, settlements=0, interval_s=28800, notes=(), charged_at=()).per_unit
```

Restaurei o código imediatamente depois de confirmar (nenhuma versão "quebrada" ficou no disco além
do próprio teste, que documenta o cenário).

## 2. Correção

`_cadence()` agora toma a moda só dos últimos `_CADENCE_RECENT_GAPS = 3` gaps, não de todos os gaps
da janela:

```python
_CADENCE_RECENT_GAPS = 3
"""Gaps ``_cadence()`` reads the mode over: 2 new settlements outvote a retired cadence; 1 stray gap does not (T3.65)."""

def _cadence(times: Sequence[datetime]) -> int | None:
    ...
    recent = gaps[-_CADENCE_RECENT_GAPS:]
    counts = Counter(recent)
    interval = max(reversed(recent), key=lambda gap: counts[gap])
    return interval or None
```

Por quê 3: é a menor janela em que (a) duas liquidações consecutivas da cadência nova já formam
maioria (2 de 3) — reage rápido depois da transição — e (b) uma única liquidação fora de grade (o
mecanismo real da Binance de "liquida de hora em hora enquanto a taxa bate no teto", já coberto por
outro teste do arquivo) continua minoria e não é lida como mudança de cadência permanente. Empate
(nenhum valor estritamente mais comum entre os recentes) é resolvido pelo mais recente — é exatamente
o "ainda não há evidência nova suficiente" que uma transição em andamento produz.

**Testes que provam as duas pontas:**
- `test_a_cadence_change_with_a_missing_settlement_is_not_a_false_zero` — o cenário do falso zero
  agora devolve `per_unit=None`, `reason` começando com `funding_missing`, `interval_s=4h`.
- `test_the_same_transition_charges_a_settlement_that_is_actually_there` — a mesma transição, mas com
  a linha das 84h presente: cobrada sob a cadência correta (4h), não tratada como fora de grade.
- `test_a_lone_off_grid_settlement_does_not_flip_the_cadence` — uma única liquidação isolada fora de
  grade não vira uma "mudança de cadência" (a próxima liquidação real volta para 8h).
- As 21 pré-existentes continuam verdes sem alteração de comportamento esperado.

**Envelope:** `FundingReading.to_jsonable()` já gravava `interval_s`, e `settle.py` já mescla
`reading.to_jsonable()` em `meta["funding"]`, persistido em `signal_outcomes.meta.funding.interval_s`
(`outcomes.py:110`, `record.py`). Não há campo novo a acrescentar — a correção faz esse campo já
existente passar a refletir a cadência real em vez da moda obsoleta.

**Escopo do que eu *não* mudei:** o design de clustering por proximidade temporal
(`_cluster`, `MATCH_TOLERANCE`) e o resto de `resolve_funding` (conflitos, fronteira ambígua,
duplicatas) são anteriores a esta tarefa e não dependem de `_cadence()` estar certo para funcionar —
uma liquidação real dentro de `(entry_ts, exit_ts]` é sempre cobrada, cadência correta ou não; o que a
cadência decide é só o que fica sinalizado como *faltante*, que é exatamente onde o falso zero mora.
Não toquei `packages/exchange-adapters` (não fetcha `fundingIntervalHours`; ver "não implementado"
abaixo) nem `_CADENCE_LOOKBACK` de `settle.py` (a janela de 3 dias que decide quanto histórico é lido
— aumentá-la não resolveria o problema, só mudaria por quanto tempo a moda antiga domina).

## 3. Medição na VPS (somente leitura)

Comandos executados (Brasília; UTC entre parênteses):

```bash
ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter -v ON_ERROR_STOP=1 -f -" \
  < infra/scripts/sql/research/2026-09-09-t365-q00-universo-e-cadencia.sql
ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter -v ON_ERROR_STOP=1 -f -" \
  < infra/scripts/sql/research/2026-09-09-t365-q01-varredura-geral.sql
```

**q00 — os nove símbolos do anúncio contra `markets`** (16:53:34 BRT / 19:53:34Z):

```
 symbol | exchange | status | is_monitored | monitor_rank | first_seen_at | delisted_at
--------+----------+--------+--------------+--------------+---------------+-------------
(0 rows)
```

Nenhum dos nove (`KODEX200USDT`, `NAVERUSDT`, `LGELECTRONICSUSDT`, `HANMIUSDT`, `SAMSUNGELUSDT`,
`CXMTUSDT`, `ZHONGJIUSDT`, `CSOPSAMSUNG2LUSDT`, `CSOPSKHYNIX2LUSDT`) existe em `markets` — nem
monitorado, nem delistado, nem com nome próximo (busca `ILIKE` por fragmento também vazia:
`SAMSUNG`, `NAVER`, `KODEX`, `CSOP`, `HANMI`, `CXMT`, `ZHONGJI`, `LGE`, `HYNIX`). Consequência direta:
`funding_rates` não tem nenhuma linha para eles (a segunda e a terceira consulta de `q00`, sobre
`funding_rates`, também vieram vazias) — nunca foram coletados, então **zero** funding foi calculado
para eles, corretamente ou não.

**q01 — varredura geral: algum dos ~528 perpétuos monitorados mudou de cadência desde 2026-08-25?**
(16:54:44 BRT / 19:54:44Z). Comparei a moda dos gaps (arredondados a 5 min) antes e depois de
2026-09-04 08:15Z, por símbolo, exigindo ≥ 2 observações de cada lado:

```
 symbol | moda_antes | moda_depois | n_antes | n_depois
--------+------------+-------------+---------+----------
(0 rows)
```

Nenhum mercado do nosso universo monitorado mudou de cadência nessa janela.

**Conclusão honesta:** o impacto medido **hoje** na VPS é zero — nenhum funding feature, nenhum
`signal_outcome`, nenhum replay foi mal custado por esta transição específica, porque nenhum dos
nove contratos TradFi jamais entrou em `hunter_exchanges`/`markets` (eles não são "USDT-margined
perpetual" no sentido que o nosso `list_markets` varre por liquidez top-N, e aparentemente não
passaram pelo piso de volume). A correção não é retroativa a um incidente já ocorrido no nosso
universo — é uma correção de instrumento contra um bug real e comprovadamente reproduzível
(§1), que hoje não tem vítima conhecida, mas teria se qualquer um dos ~528 monitorados passasse por
uma mudança de cadência real (o mecanismo já existe do lado da Binance; só não aconteceu com nenhum
símbolo nosso na janela medida).

**O que eu não consegui verificar:** o brief pede para abrir o anúncio da Binance eu mesmo via
WebFetch para confirmar a lista de símbolos e o timestamp. **Esta sessão não tem ferramenta de
WebFetch nem acesso de rede pelo Bash** (tentei `curl` contra a URL do anúncio; sem saída, sem erro —
rede bloqueada no sandbox). Apoiei-me na citação já registrada no plantão
(`.claude/state/plantao/2026-09-09-1700-lane1.md`, item 3) e na conferência que a própria Astra já fez
na revisão do plantão (`.claude/state/astra-review-plantao-20260909-1700.md`: "O item (3) está fiel ao
anúncio da Binance... nove contratos TradFi específicos, sem generalização para todos os perps"). Não
é uma verificação de primeira mão minha — é uma concordância com duas fontes internas que já abriram
o anúncio.

## 4. Testes, lint, tamanho

```
$ cd services/strategy-worker && uv run pytest tests/test_funding.py -q
........................                                                 [100%]
24 passed in 1.85s

$ cd services/strategy-worker && uv run pytest tests/test_funding.py tests/test_settle.py tests/test_recompute_funding.py -q
.............................                                            [100%]
29 passed in 69.78s (0:01:09)
```
(a segunda rodada usa testcontainer Postgres — o único testcontainer desta tarefa.)

```
$ uv run ruff check services/strategy-worker/hunter_strategy_worker/funding.py services/strategy-worker/tests/test_funding.py
All checks passed!

$ uv run ruff format --check services/strategy-worker/hunter_strategy_worker/funding.py services/strategy-worker/tests/test_funding.py
2 files already formatted

$ uv run pyright services/strategy-worker/hunter_strategy_worker/funding.py services/strategy-worker/tests/test_funding.py
0 errors, 0 warnings, 0 informations

$ uv run python infra/scripts/check_file_size.py
scanned 587 files; 0 over budget, 0 grandfathered
```

`funding.py` foi de 344 para **350** linhas — exatamente no teto (`check_file_size.py` usa `>`, não
`>=`, então 350 passa). Precisei condensar a prosa nova (docstring do módulo, da constante e de
`_cadence()`) várias vezes para caber; o código de `_cadence()` também ficou mais compacto do que a
minha primeira versão (`max(reversed(recent), key=lambda gap: counts[gap])` em vez de um `best`/
`winners`/`next` de três linhas) — mesma semântica de desempate por recência, menos linhas.

## 5. Arquivos

- `services/strategy-worker/hunter_strategy_worker/funding.py` — `_cadence()` corrigida;
  `_CADENCE_RECENT_GAPS = 3`; docstrings do módulo e da função atualizadas.
- `services/strategy-worker/tests/test_funding.py` — `TestCadenceTransition` (3 testes novos), um
  ajuste de `_at(25)` → `_at(21) + timedelta(hours=4)` no teste novo (o helper `_at` não aceita hora
  ≥ 24).
- `docs/PIPELINE.md` — uma frase no item 10 do §1, citando o T3.65 e esta nota.
- `infra/scripts/sql/research/2026-09-09-t365-q00-universo-e-cadencia.sql`,
  `infra/scripts/sql/research/2026-09-09-t365-q01-varredura-geral.sql` — as duas consultas do §3.
- `.claude/state/notes-T3.65.md` — esta nota.

## 6. Concerns

1. Não consegui abrir o anúncio da Binance eu mesmo (sem WebFetch, sem rede no Bash desta sessão) —
   apoiei-me em duas fontes internas já conferidas (plantão + Astra). Se alguém tiver acesso de rede,
   vale confirmar a lista de nove símbolos e o timestamp 08:15Z diretamente na fonte.
2. `_CADENCE_RECENT_GAPS = 3` é uma escolha de engenharia (a menor janela que reage a 2 liquidações
   novas sem virar refém de 1 liquidação isolada fora de grade), não derivada de nenhum dado real de
   transição no nosso universo — porque nenhuma aconteceu ainda. Se um mercado nosso passar por uma
   mudança de cadência real no futuro, vale reconferir se 3 continua certo (por exemplo, se a Binance
   tiver o hábito de fazer 1 settlement de transição "estranho" antes de estabilizar na nova grade,
   o que exigiria 4 ou 5).
3. Não toquei `packages/exchange-adapters` para buscar `fundingIntervalHours` de `premiumIndex`/
   `exchangeInfo` — o brief permitia essa alternativa só "se o adaptador já buscar isso", e não busca.
   Ler a cadência declarada da própria exchange seria mais robusto que inferir por gaps observados,
   mas é uma mudança de escopo maior (novo campo em `NormalizedFunding` ou `NormalizedMarket`,
   persistência, e ainda assim precisaria de um fallback para quando o campo vier ausente ou a
   exchange mudar de esquema) — registro como trabalho futuro, não fiz.
4. `funding.py` está agora exatamente no teto de 350 linhas — qualquer adição futura (mesmo uma
   linha de comentário) precisa cortar de outro lugar do arquivo primeiro.
