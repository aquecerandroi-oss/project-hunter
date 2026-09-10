# notes-T3.65b — o resolver de funding contra os mercados de 4 h reais

**Data:** 2026-09-10, 12:04 → 12:50 BRT (15:04 → 15:50 UTC). **Owner:** quant-engineer.
**VPS:** somente leitura (`ssh hunter-vps` + `docker exec -i hunter-postgres-1 psql`), toda consulta em
`repeatable read read only` com `statement_timeout = 240s`. **Nenhuma escrita na VPS, nenhum container
tocado, nenhum `.env*` lido ou alterado, nada commitado.** Todo comando em primeiro plano com
`timeout 290`. Testcontainers: um arquivo por vez.

---

## STATUS

**DONE_WITH_CONCERNS.**

| # | Entrega do brief | Resultado |
|---|---|---|
| a | Medição na VPS: instantes reais, onde foi a transição, como o resolver classificaria | **OK.** §1–§4. A premissa do brief estava errada (§1) |
| b | Corrigir se houver erro de classificação em linha real | **OK, mas outro erro.** §3–§5. A cadência (T3.65) já classifica certo os 807 desfechos reais; o defeito achado é de **borda de saída**, não de cadência. Corrigido com TDD sobre os carimbos reais de PROM |
| b' | Contagem de `funding_missing` / `funding_ambiguous_exit` / `funding_schedule_unknown` por semana, antes × depois | **OK.** §4 |
| c | `notes-T3.65b.md`, SQL de pesquisa, D-P15 fechada como `medida` | **OK.** §7 |

**Concerns declarados:** (1) restam **207** janelas hipotéticas (0,35 % das de PROM) recusadas nas duas
transições de cadência — recusa **deliberada**, ver §5; (2) `funding_rates` não tem coluna de gravação e
`track_commit_timestamp` está OFF: a hora de chegada de uma linha **não** é recuperável, só a transação
(`xmin`) — §2; (3) o teste "16 ciclos ≤ 0,025 % → volta a 4 h no 17.º" pedido pela D-P15 **não** foi
escrito: o número de ciclos é estado da exchange e não existe na nossa série (§6).

---

## ARQUIVOS (`git status --porcelain`, só os meus)

```
 M obsidian/00-INBOX/Hipoteses-do-plantao.md
 M services/strategy-worker/hunter_strategy_worker/funding.py
 M services/strategy-worker/tests/test_funding.py
?? .claude/state/exp-drafts/t365b/
?? .claude/state/notes-T3.65b.md
?? infra/scripts/sql/research/2026-09-10-t365b-q00-cadencia-real.sql
?? infra/scripts/sql/research/2026-09-10-t365b-q01-desfechos-e-universo.sql
?? infra/scripts/sql/research/2026-09-10-t365b-q02-quando-rodou.sql
?? infra/scripts/sql/research/2026-09-10-t365b-q03-quando-a-linha-chegou.sql
?? infra/scripts/sql/research/2026-09-10-t365b-q04-os-tres-motivos.sql
?? infra/scripts/sql/research/2026-09-10-t365b-q05-antes-depois.sql
```

Raiz em `C:\dev\project-hunter\`. **Não commitei nada.** Não toquei nos módulos de fechamento, nem em
`consumer.py`/`context*.py` (T3.74c), nem nos módulos de portão (T3.77).

Receita das consultas (todas somente leitura):

```bash
timeout 290 ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter \
  -v ON_ERROR_STOP=1 -f -" < infra/scripts/sql/research/2026-09-10-t365b-q00-cadencia-real.sql
```

---

## 1. A PREMISSA DO BRIEF NÃO É O QUE A SÉRIE DIZ

O brief (e a D-P15) diziam: "PROMUSDT, SAHARAUSDT e TAOUSDT em 4 h; PROM desde 14/08", com a leitura
implícita de uma passagem **8 h → 4 h**. `funding_rates` diz outra coisa. `q00`/`q01`, 12/06 → 10/09:

```
+------------+------+------+------+------+---------+---------+---------+
|   symbol   | gaps | g_1h | g_4h | g_8h | g_outro | gap_min | gap_max |
+------------+------+------+------+------+---------+---------+---------+
| PROMUSDT   |  599 |   78 |  519 |    1 |       1 |    3600 |   28800 |
| SAHARAUSDT |  540 |    0 |  539 |    1 |       0 |   14400 |   28800 |
| TAOUSDT    |  540 |    0 |  539 |    1 |       0 |   14400 |   28800 |
| os 13 de 8 h (ARB BNB BTC DASH DOGE ETH LINK NEAR SOL SUI UNI XRP ZEC):     |
|            |  270 |    0 |    0 |  270 |       0 |   28800 |   28800 |
+------------+------+------+------+------+---------+---------+---------+
```

Três leituras, todas verificáveis na `q00` §3 e na `q01` §2:

1. **PROM nunca esteve em 8 h nos 90 dias.** Já estava em 4 h em 12/06. O que aconteceu foi
   **4 h → 1 h em 2026-08-11 05:00:00.009Z** (78 gaps de 3 600 s, a regra de teto da Binance) e a
   **volta 1 h → 4 h em 14/08**: o último assentamento de 1 h foi `10:00:00.000Z`, o seguinte
   `12:00:00.002Z` (gap de 7 200 s, o único do tipo) e daí em diante 16/20/00/04Z. A volta cai no
   **ponto seguinte da grade de 4 h**, coerente com a regra pública de 02/01/2026 (17.º ciclo).
   Ou seja: a transição de 14/08 é a **volta** que a Astra apontou, não uma aceleração.
2. **SAHARA e TAO não mudaram de cadência.** 539 gaps de 4 h e **um** de 8 h.
3. **O único gap de 8 h dos três é o mesmo instante nos três** — `2026-06-24 00:00:00.005Z →
   08:00:00.005Z`, isto é, o assentamento de `04:00Z` não existe no nosso banco em nenhum dos três.
   Três mercados perdendo o mesmo assentamento é **lacuna de coleta**, não mudança de cadência. É a
   distinção que a D-P15 pedia, e ela sai do dado, não de suposição.

---

## 2. O QUE O BANCO NÃO PODE RESPONDER (declarado, não contornado)

`funding_rates` tem quatro colunas (`market_id, funding_time, rate, mark_price`) e **nenhuma de
gravação**; `show track_commit_timestamp` na VPS devolve `off`. Logo **a hora em que uma linha chegou
não é recuperável**. O que sobra é `xmin` — a transação que inseriu — que dá **ordem e agrupamento**,
nunca relógio (`q03`):

```
| TAOUSDT | 4365098 | 343 | 2026-06-12 08:00:00+00     | 2026-08-08 12:00:00.001+00 |  <- backfill T3.75
| TAOUSDT | 1333598 | 164 | 2026-08-08 16:00:00.002+00 | 2026-09-04 20:00:00+00     |  <- lote anterior
| TAOUSDT | 4463113 |   1 | 2026-09-10 08:00:00.007+00 | ...                        |  <- coletor ao vivo
```

Uma transação com 343 linhas de 12/06 a 08/08 é exatamente o backfill da T3.75; o `xmin` dela
(4365098) fica **entre** os das inserções ao vivo de 09/10 04:00Z (4248212) e 08:00Z (4463113),
compatível com a janela declarada na `notes-T3.75` (04:55–05:35Z). De 06/09 em diante é uma linha por
transação: coletor ao vivo.

---

## 3. COMO O RESOLVER CLASSIFICA AS LINHAS REAIS

Dois experimentos, ambos rodando o **código real** (`resolve_funding` importado, não reimplementado)
sobre as **linhas reais** exportadas da VPS (`.claude/state/exp-drafts/t365b/funding-real.csv`,
1 682 assentamentos).

### 3.1 As janelas dos desfechos REAIS (`replay_outcomes.py`)

807 desfechos terminais perpétuos dos três mercados, re-resolvidos com o código de hoje e as linhas de
hoje. **Nada é escrito** — não é a recomputação.

```
desfechos re-resolvidos: 807
  ok -> ok: 532
  funding_schedule_unknown -> ok: 266
  funding_ambiguous_exit -> ok: 5
  funding_schedule_unknown -> funding_missing: 2
  funding_missing:2026-08-14T17:00:00.002000+00:00 -> ok: 1
  funding_missing:2026-09-09T00:00:00.002000+00:00 -> ok: 1
```

- **266 `funding_schedule_unknown` → `ok`**: cobertura que o backfill da T3.75 criou. As coortes
  `c7d138eb`/`fa005985`/`da706026` rodaram em 10/09 **02:35–04:28Z**, antes de o backfill terminar
  (05:35Z) — por isso ficaram sem cadência legível. É o que a `recompute_funding.py` resolveria.
- **2 `funding_schedule_unknown` → `funding_missing`**: ambos em `2026-06-24T04:00:00.005` — a lacuna
  de coleta do §1. **Recusa correta**: a cobrança existiu e o dado não a tem.
- **As duas únicas recusas por `funding_missing` já gravadas se explicam, e nenhuma é erro do código
  de hoje:**
  - `PROMUSDT`, `replay:d82356d9`, 14/08 15:46→19:42Z, `funding_missing:2026-08-14T17:00:00.002`,
    `interval_s = 3600`. É **pré-T3.65** (`updated_at` 09/09 19:44Z). A **mesma janela** na coorte v10
    (`replay:c7d138eb`, `updated_at` 10/09 03:03Z) lê `interval_s = 14400` e resolve. A moda dos 3
    últimos gaps da T3.65 **já corrigiu esse caso real** (`q02` §2).
  - `TAOUSDT`, prospective, 08/09 20:02 → 09/09 00:02Z, `funding_missing:2026-09-09T00:00:00.002`,
    `interval_s = 14400`, `updated_at` 09/09 00:03:07Z. A linha real é `00:00:00.005` — **3 ms** do
    instante cobrado, dentro da tolerância de 2 s, e **dentro** da janela. Se estivesse no banco teria
    sido cobrada. É **atraso de coleta**, não cadência.
- **5 `funding_ambiguous_exit` → `ok`** é limite do script, não do resolver: `ambiguous_from` (a barra
  de uma saída intrabar) não está no CSV. O caso é PROM 23/08 23:01 → 24/08 00:01Z e existe mesmo um
  assentamento em `2026-08-24 00:00:00.001` dentro da barra de saída (`q04`): o guarda é por desenho.
- Os 5 `funding_schedule_unknown` de 09/09 em PROM são de mercado **spot** (`q04`: 5 de 5 spot,
  0 de 194 perpétuos) — assunto da T3.73, não do funding.

**Conclusão de (a): sob o código de hoje, nenhum desfecho real dos três mercados está mal classificado
por causa de cadência.**

### 3.2 A varredura sistemática (`replay_resolver.py`)

Para não depender de as 807 janelas terem calhado nos lugares certos, varri **175 416** janelas
hipotéticas sobre as mesmas linhas reais: entradas de 15 em 15 min ao longo dos 90 dias × sete
durações (15 m, 30 m, 1 h, 2 h, 4 h, 8 h, 12 h), com a **mesma janela de histórico de `settle()`**
(`[entry − 3 d, exit + 2 s]`). A verdade de comparação é a grade real de cada mercado, lida das eras
do §1, mais o buraco de 24/06. Janelas cuja borda cai a menos de 2 s de um assentamento **que não
temos** ficam em `indeterminado_ms` (o ms de uma linha ausente não é reconstruível) e não contam como
defeito.

**Antes da correção:**

```
janelas avaliadas: 175416
  PROMUSDT|cobrado_certo: 56921        PROMUSDT|falso_missing_borda_saida: 1226
  PROMUSDT|falso_missing_grade: 207    PROMUSDT|indeterminado_ms: 14
  PROMUSDT|lacuna_de_coleta_detectada: 104
  SAHARAUSDT|cobrado_certo: 57279      SAHARAUSDT|falso_missing_borda_saida: 1075
  SAHARAUSDT|indeterminado_ms: 14      SAHARAUSDT|lacuna_de_coleta_detectada: 104
  TAOUSDT|cobrado_certo: 57279         TAOUSDT|falso_missing_borda_saida: 1075
  TAOUSDT|indeterminado_ms: 14         TAOUSDT|lacuna_de_coleta_detectada: 104
```

Duas famílias de recusa indevida, com causas diferentes:

- **`falso_missing_borda_saida` (3 376 = 1,9 %)** — nada a ver com cadência. A âncora da grade nominal
  é a última linha real antes da entrada, e ela carrega os **milissegundos daquela linha**. Quando a
  âncora tem ms zero (`2026-08-14 20:00:00.000`) e a saída é um minuto redondo
  (`2026-08-15 00:00:00`), o instante nominal cai **dentro** de `(entry, exit]` enquanto a linha real
  caiu **3 ms depois** da saída (`2026-08-15 00:00:00.003`). O assentamento **existe** e a posição saiu
  antes dele: não foi pago e não está ausente — mas o resolver recusava a janela inteira.
- **`falso_missing_grade` (207, só PROM)** — a família que a Astra previu: a grade inferida projetada
  sobre a era anterior, nas duas transições (10/08 18:00Z → 14/08 15:30Z). SAHARA e TAO, que não
  mudaram de cadência, têm **zero**.

**Depois da correção (§5):**

```
janelas avaliadas: 175416
  PROMUSDT|cobrado_certo: 58147    PROMUSDT|falso_missing_grade: 207
  PROMUSDT|indeterminado_ms: 14    PROMUSDT|lacuna_de_coleta_detectada: 104
  SAHARAUSDT|cobrado_certo: 58354  SAHARAUSDT|indeterminado_ms: 14
  SAHARAUSDT|lacuna_de_coleta_detectada: 104
  TAOUSDT|cobrado_certo: 58354     TAOUSDT|indeterminado_ms: 14
  TAOUSDT|lacuna_de_coleta_detectada: 104
```

3 376 → 0 na família de borda; as 104 detecções da lacuna real de 24/06 **continuam** detectadas em
cada mercado; nenhum veredito dos 807 desfechos reais muda (`outcomes-out.txt` e
`outcomes-out-depois.txt` são idênticos).

---

## 4. OS TRÊS MOTIVOS POR SEMANA, ANTES × DEPOIS (`q01` §3, `q05`)

Só perpétuos, os três mercados (o spot está fora — §3.1). Fases: `antes` = entrada antes de
2026-08-11 05:00Z; `na janela 1h` = entre 11/08 05:00Z e 14/08 12:00Z; `depois` = a partir daí.

```
+------------+--------------+-----------+-----------+-----------------+----------------+------------------+-----+
|   symbol   |     fase     |  codigo   | terminais | funding_missing | ambiguous_exit | schedule_unknown | ok  |
+------------+--------------+-----------+-----------+-----------------+----------------+------------------+-----+
| PROMUSDT   | antes        | pos-T3.65 |       118 |               0 |              0 |              110 |   8 |
| PROMUSDT   | antes        | pre-T3.65 |         9 |               0 |              0 |                0 |   9 |
| PROMUSDT   | na janela 1h | pos-T3.65 |         2 |               0 |              0 |                0 |   2 |
| PROMUSDT   | na janela 1h | pre-T3.65 |         3 |               0 |              0 |                0 |   3 |
| PROMUSDT   | depois       | pos-T3.65 |        77 |               0 |              2 |                0 |  75 |
| PROMUSDT   | depois       | pre-T3.65 |       132 |               1 |              3 |                0 | 128 |
| SAHARAUSDT | (tres fases) |   ambos   |       197 |               0 |              0 |               86 | 111 |
| TAOUSDT    | (tres fases) |   ambos   |       269 |               1 |              0 |               72 | 196 |
+------------+--------------+-----------+-----------+-----------------+----------------+------------------+-----+
```

Por semana ISO, entradas a partir de 03/08 (os três mercados somados):

```
|   semana   | terminais | funding_missing | ambiguous_exit | schedule_unknown |
| 2026-08-03 |        57 |               0 |              0 |               37 |
| 2026-08-10 |        29 |               1 |              0 |                0 |   <- a semana da transicao
| 2026-08-17 |       113 |               0 |              5 |                0 |
| 2026-08-24 |       134 |               0 |              0 |                0 |
| 2026-08-31 |       120 |               0 |              0 |                0 |
| 2026-09-07 |       123 |               1 |              0 |                0 |
```

Leitura honesta: a semana da transição tem **um** `funding_missing`, e ele é o desfecho **pré-T3.65**
do §3.1; a de 07/09 tem **um**, e é o atraso de coleta do TAO. Os `funding_schedule_unknown` de 03/08
e antes são **cobertura**, não cadência: as coortes rodaram antes de o backfill da T3.75 terminar. A
divisão `pre`/`pos-T3.65` por `updated_at < 2026-09-10 02:00Z` só é válida para coortes de replay; o
caminho `prospective` roda a imagem implantada e está anotado como tal na consulta.

---

## 5. A CORREÇÃO (TDD, com carimbos REAIS de PROMUSDT)

**Teste primeiro, vermelho sobre dado real** (`services/strategy-worker/tests/test_funding.py`,
`TestRealPromUsdtAroundTheCadenceReversion`): sete linhas de PROMUSDT copiadas literalmente do banco
(14/08 09:00:00.007 … 15/08 04:00:00.000), mais quatro de 23–24/06 para o buraco de coleta.

```
E  AssertionError: a linha de 2026-08-15 00:00:00.003 existe e ficou FORA da janela: nao e ausencia,
   got 'funding_missing:2026-08-15T00:00:00+00:00'
1 failed, 26 passed in 1.58s
```

**A correção** (`funding.py`, +35 linhas, uma função e uma condição):

```python
def _fulfilled(instant: datetime, times: Sequence[datetime]) -> bool:
    """``True`` if some real row of the history is this nominal instant. ..."""
    return any(abs(t - instant) <= MATCH_TOLERANCE for t in times)
...
    items.extend(
        (instant, None)
        for instant in nominal
        if instant not in claimed and not _fulfilled(instant, times)
    )
```

É a própria regra do módulo levada até o fim: *identity, not proximity* — e identidade não depende do
lado da fronteira em que a linha caiu. Um instante nominal que **qualquer** linha real responde não é
uma ausência; se ela caiu fora de `(entry, exit]`, simplesmente **não foi paga**. Não pode esconder
ausência verdadeira: um nominal só é silenciado quando existe linha real para ele — dentro da janela
ela é cobrada pelo laço de clusters, fora dela a posição não estava aberta quando assentou. **Nenhum
zero é fabricado**: a janela do teste devolve `per_unit = 0` com `settlements = 0`, que é o mesmo
caminho já existente de "nenhum assentamento na janela".

Três testes novos, todos sobre linhas reais: (i) o assentamento carimbado depois da saída não é
ausência; (ii) o assentamento **exatamente** na saída continua cobrado
(`-0,00093182 × 2,31375333`); (iii) o buraco real de `2026-06-24 04:00Z` — que é a janela de um
desfecho real, `replay:c7d138eb` 01:31→05:31Z — **continua** recusado.

**O que eu deliberadamente NÃO mudei: as 207 janelas das transições.** Nelas o resolver lê a cadência
antiga e nomeia como ausente um instante que nunca existiu (ex.: `2026-08-14T15:00:00.002` com
`interval_s = 3600`). O veredito — `r_multiple = NULL`, sem cobrança — é **seguro**; só o diagnóstico
é impreciso. As duas "correções" tentadoras são piores:

- trocar por `funding_schedule_unknown` mandaria essas operações para o eixo `r_ex_funding` da T3.75
  (é o **único** motivo com essa queda, `replay/stress.py:101`), e ali há cobrança real de até
  **−0,045 por unidade** (janela 10/08 18:00 → 11/08 06:00Z) — seria fabricar o zero que a regra proíbe;
- aceitar a grade local (não emitir ausência quando o ritmo muda) trocaria uma recusa conservadora por
  uma **cobrança silenciosamente subcontada** na transição, que é exatamente o erro que o módulo
  existe para evitar.

Nenhum desfecho real caiu nessas 207. Fica registrado como comportamento medido e declarado; se algum
dia custar cobertura de verdade, o caminho é um motivo próprio no vocabulário (com o efeito no eixo de
estresse desenhado junto), não um afrouxamento da grade.

---

## 6. O QUE A D-P15 PEDIA E NÃO FOI ENTREGUE

- **Teste "16 ciclos ≤ 0,025 % → volta a 4 h no 17.º".** Não escrito. O contador de ciclos é estado da
  exchange; a nossa série tem os assentamentos, não a decisão dela. O que dá para afirmar do dado é o
  **efeito**: a volta de PROM caiu no ponto seguinte da grade de 4 h (§1). Um teste que "verificasse" a
  regra com a nossa série estaria testando a minha reconstrução, não a Binance.
- **Teste "dois gaps novos iguais vencem".** Já existe desde a T3.65
  (`test_funding.py::TestCadenceTransition`, três testes); não dupliquei.
- **Diferença de custo das apostas na janela, recontadas com a grade real.** Não há o que recontar:
  nenhum desfecho real dos três mercados teve cobrança errada (§3.1). A diferença é **zero por
  construção**, não por medição de valor.

---

## 7. COMANDOS E SAÍDAS

```
$ timeout 290 ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter \
    -v ON_ERROR_STOP=1 -f -" < infra/scripts/sql/research/2026-09-10-t365b-q00-cadencia-real.sql
  -> read_at 2026-09-10 15:05:28Z; §1 (saidas completas em .claude/state/exp-drafts/t365b/)

$ ... q01 ... -> q01-out.txt   $ ... q02 ... -> q02-out.txt   $ ... q03 ... -> q03-out.txt
$ ... q04 ... -> q04-out.txt   $ ... q05 ... -> q05-out.txt

$ timeout 280 uv run python .claude/state/exp-drafts/t365b/replay_resolver.py    # §3.2
$ timeout 280 uv run python .claude/state/exp-drafts/t365b/replay_outcomes.py    # §3.1

$ timeout 280 uv run pytest services/strategy-worker/tests/test_funding.py -q
27 passed in 1.18s

$ timeout 280 uv run pytest services/strategy-worker/tests/test_funding.py \
    services/strategy-worker/tests/test_settle.py \
    services/strategy-worker/tests/test_derivatives.py \
    services/strategy-worker/tests/test_recompute_funding.py -q
41 passed in 38.38s

$ timeout 280 uv run pytest services/strategy-worker/tests -q -m unit
341 passed, 375 deselected in 15.29s

$ timeout 280 uv run pytest services/strategy-worker/tests/test_replay_engine.py -q
16 passed in 206.35s (0:03:26)

$ timeout 280 uv run pytest services/strategy-worker/tests/test_shadow_outcomes.py -q
16 passed in 127.89s (0:02:07)

$ timeout 280 uv run ruff check <os dois arquivos>            -> All checks passed!
$ timeout 200 uv run ruff format --check <os dois arquivos>   -> 2 files already formatted
$ timeout 280 uv run pyright <os dois arquivos>               -> 0 errors, 0 warnings, 0 informations
```

Os arquivos de trabalho (CSV das linhas reais, CSV das janelas dos desfechos, scripts e saídas) estão
em `.claude/state/exp-drafts/t365b/`.

---

## 8. SUPOSIÇÕES NUMÉRICAS QUE PRECISEI FAZER

1. **A grade-verdade das eras** (§1) foi reconstruída **do nosso próprio dado** (histograma de gaps),
   não de um arquivo da Binance: 4 h até 11/08 04:00Z, 1 h até 14/08 10:00Z, 4 h a partir de 12:00Z.
   O `fundingInfo` de hoje concorda com o estado final, mas é estado atual e não reconstrói 90 dias.
2. **O assentamento ausente de 24/06 04:00Z** é tratado como cobrança que **existiu**, porque os três
   mercados perdem o mesmo instante e a cadência dos dois lados é 4 h. Não há prova independente.
3. **A geometria das janelas hipotéticas** (15 em 15 min × sete durações) é escolha minha para cobrir
   os 90 dias com custo viável; as porcentagens de §3.2 são dessa grade, não da distribuição real de
   durações do Lab.
4. **O corte `pre`/`pos-T3.65` por `updated_at < 2026-09-10 02:00Z`** vale para coortes de replay; o
   caminho `prospective` roda a imagem implantada e não é datável por esse corte.
