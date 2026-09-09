# notes-T3.57 — `trendline_bounce_v1`: a hipótese que o dado sustentou

**Data:** 2026-09-09, 11:20 → 14:55 de Brasília (UTC−3; 14:20 → 17:55 UTC). **Owner:** quant-engineer.
**Base local:** `main @ 77c6606` (árvore compartilhada, com outras tarefas em voo — §8).
**Nada commitado. Nada semeado. Nada ativado. Nada rodou na VPS além de UMA leitura.**
**Nenhuma linha alterada em `trendline_breakout_v1.py`, em nenhum dos cinco `tl_*.py`, nem em
qualquer dos sete módulos de fecho.** Os seis digests vivos estão pinados por teste e não se moveram.

---

## STATUS

**DONE_WITH_CONCERNS** — a parte local está pronta e verde; a VPS **não** foi tocada para escrita,
porque o passo 1 resolveu-se por **irmão plano**, e nesse caminho o brief manda parar aqui.

| # | Entrega do brief | Resultado |
|---|---|---|
| 1 | Decidir o caminho mais barato e fiel: `derive_variant` **ou** irmão plano | **Irmão plano.** `mode="bounce"` existe, mas **nenhum parâmetro desliga a invalidação estrutural** — prova de código em §1 |
| 1 | `trendline_bounce_v1.py` ≤ 350 linhas, fecho próprio, sem importar `trendline_breakout_v1` | **OK.** 350 linhas exatas; fecho de 13 módulos; `test_the_closure_is_the_geometry_and_not_the_other_experiment` |
| 1 | Testes: não-antecipação, barra em formação, paridade de geometria | **OK.** 52 casos, todos verdes (§4) |
| 1 | Entrada em `constraints`, linha em `seed_reference.py`, `registry.py` (+2), janela em `context_budget.WINDOWS` | **OK.** §3, e `registry.py` é **exatamente +2 linhas** |
| 1 | `test_code_ref.py`: os seis digests vivos permanecem | **OK.** Pinados no teste novo e verificados: `…7b83a1ff…` inclusive |
| 2 | Rascunho congelado `EXP-0022-trendline-bounce.md`, C1–C8, K1–K6, dia um pré-registrado | **OK**, com C4 rebaixado a **FAIL declarado** e C8 marcado **N/A por construção** (§5) |
| 3 | Parar depois da parte local, com a lista exata de arquivos | **OK.** §7 |
| — | Derive/activate/replay na VPS | **NÃO RODADO** — não é o caminho: era condicional a "se `default_parameters` já permitem" |

**Resposta curta em cinco linhas.** A v2 **não** cabia num `derive_variant`: `mode` existe, a
invalidação não é parâmetro. Então saiu um irmão plano de **350 linhas** com **34 parâmetros** — os
36 da mãe menos `mode` e `max_violations_breakout` — e **um único valor movido** (`rvol_min`
1,5 → 1,0). A versão **não tem invalidação**, não tem porta de rompimento e não tem limiar de
inclinação (C4 foi refutado na T3.34c). Antes de congelar o `rvol_min` eu li a VPS **uma vez**, só
para checar K1: **26 decisões** sobreviveriam ao portão nos mesmos 31 d × 4 mercados. A projeção
pré-registrada da v2 nessa janela é **+0,2401 R líquidos por decisão** — número que existe para
poder ser desmentido.

---

## 1. O PASSO 1, DECIDIDO POR LEITURA DE CÓDIGO (antes de qualquer escrita)

O brief autoriza `derive_variant` **se** `default_parameters` já permitirem as duas coisas. Uma
permite, a outra não:

| o que a v2 precisa | há parâmetro? | prova |
|---|---|---|
| **só repique** | **SIM** — `mode` aceita `breakout \| bounce \| both` (`tl_setup.MODE_PARAM`) | `find_trigger(scan, str(params["mode"]))` |
| **sem invalidação estrutural** | **NÃO** | ver abaixo |

`trendline_breakout_v1._decide`, verbatim (as duas construções são **incondicionais**):

```python
        if not stop < setup.level < close:
            return _rejected("geometry_invalidation", levels)
        ...
            invalidations=(
                Invalidation(kind="close_below", level=setup.level, timeframe=self.timeframe.value),
            ),
```

Não há `if params[...]` em volta de nenhuma das duas. Os `max_violations_*` **não** servem: eles
contam fechamentos *através da linha até o corte* (qualidade da linha, `tl_lines`), e não têm relação
com a saída. Uma varredura confirma que não existe outro botão:

```
$ grep -n "invalidation\|Invalidation" packages/core/hunter_core/strategies/trendline_breakout_v1.py
(só as duas ocorrências acima, mais o comentário que as explica)
$ grep -n "invalid" packages/core/hunter_core/strategies/tl_setup.py
(nenhuma)
```

**Conclusão:** uma derivação entregaria **uma** das duas mudanças e mentiria sobre a outra. E editar
`trendline_breakout_v1.py`/`tl_setup.py` para acrescentar o botão está **proibido** pelo brief e
seria pior: re-congelaria a v1 já ativada na VPS (`…7b83a1ff…`) e o Lab inteiro viraria
`code_ref_mismatch` atrás de um `/ready` verde. O próprio `tl_setup.py` já previu este dia no
docstring: *"a future `trendline_*_v2` … would add its own module, exactly as the strategy versions
do."* Foi o que fiz.

---

## 2. ORDEM DOS ATOS DO `rvol_min` — declarada antes da medição

Registrei isto neste arquivo **antes** de rodar a consulta, e mantenho o texto:

1. **`rvol_min = 1.0` escolhido por princípio:** "a barra de repique negociou ao menos a mediana das
   últimas 96 barras". O 1,5 da mãe é um pedido de **expansão**, e repique é continuação — a v1 dizia
   exatamente isso ao não pedir volume nenhum. 1,0 é a leitura mínima de "com RVOL".
2. **Só então** a consulta, para **uma** pergunta: a população sobrevivente ainda passa K1?

**A única escrita-adjacente na VPS foi esta leitura**, em `repeatable read read only`
(`infra/scripts/sql/research/2026-09-09-t357-q00-rvol-dos-repiques.sql`):

```
$ ssh hunter-vps 'docker exec -i hunter-postgres-1 psql -U hunter -d hunter -f -' \
    < infra/scripts/sql/research/2026-09-09-t357-q00-rvol-dos-repiques.sql
BEGIN
+-------------------------------+
|            read_at            |
+-------------------------------+
| 2026-09-09 17:28:17.279278+00 |     (14:28 de Brasília)
+-------------------------------+

+-------------------+----+------------+----------+-------------+------+
|       faixa       | n  | rvol_medio | rvol_min | r_liq_medio | dias |
+-------------------+----+------------+----------+-------------+------+
| rvol >= 0.8       | 33 |     2.0993 |   0.8023 |      0.1462 |   12 |
| rvol >= 0.9       | 29 |     2.2725 |   0.9185 |      0.2203 |   12 |
| rvol >= 1.0       | 26 |     2.4264 |   1.0127 |      0.1676 |   11 |
| rvol >= 1.1       | 23 |     2.6049 |   1.1719 |      0.2330 |   11 |
| rvol >= 1.25      | 22 |     2.6701 |   1.2836 |      0.2662 |   11 |
| rvol >= 1.5       | 16 |     3.1542 |   1.5718 |      0.1963 |   11 |
| todos os repiques | 42 |     1.7785 |   0.4408 |      0.0177 |   13 |
+-------------------+----+------------+----------+-------------+------+
(7 rows)
COMMIT
```

**A coluna de R está publicada de propósito, e ela prova a ordem dos atos melhor que a minha
palavra:** 1,0 é um **mínimo local** entre os vizinhos (0,9 → +0,2203; 1,1 → +0,2330;
1,25 → +0,2662). Quem estivesse garimpando teria congelado 1,25. O que a consulta autorizou foi só
**26 ≥ 20 ⇒ K1 não dispara**. A distribuição inteira dos 42 repiques (rvol, mercado, motivo, R) está
na segunda consulta do mesmo arquivo e foi impressa na íntegra.

### A projeção pré-registrada (aritmética, não previsão)

Dos 26 repiques com RVOL ≥ 1,0: soma **+4,3588 R**, média **+0,1676 R**, 11 dias, e por motivo
`{invalidated: 10, expired: 6, target: 6, stop: 4}`. Aplicando o Δ por episódio invalidado que a
T3.34c mediu com o braço `INV-B` (**+0,188462 R**):

```
projeção v2 = (4,3588 + 10 × 0,188462) / 26 = +0,2401 R líquidos por decisão
```

**Não é uma previsão — é o valor que a aritmética da v1 implica se nada mais mudar.** E algo *vai*
mudar: **a população da v2 não é subconjunto da da v1** (KB do T3.52d). Três fontes de divergência,
todas pré-registradas no EXP-0022:

- barras em que a v1 achou **rompimento primeiro** (`find_trigger` testa rompimento antes) e que aqui
  podem devolver um repique ⇒ a v2 pode ter decisões que a v1 **não** tem;
- a única barra que a v1 recusou por `geometry_invalidation` (DOGEUSDT), que aqui não é recusada;
- os 16 repiques com RVOL < 1,0, que a v1 tinha e a v2 não.

**Por isso o pareamento do replay tem de ser por `(mercado, barra)`, nunca por "a v2 é um recorte".**

---

## 3. O QUE FOI ESCRITO (e o que deliberadamente não foi)

### `packages/core/hunter_core/strategies/trendline_bounce_v1.py` — 350 linhas

| propriedade | valor |
|---|---|
| `key` / `version` / `timeframe` | `trendline_bounce_v1` / `v1` / 15 min |
| `code_ref` previsto | `hunter_core.strategies.trendline_bounce_v1@sha256:fb7263ce5f06956f6d57c86f2a0790c62644b3f453904d83546674de4dabdb75` |
| `params_hash` previsto | `9b1e882f169c89ca` (a mãe: `f2e8017c7251e22f`) |
| parâmetros | **34** = os 36 da mãe − `mode` − `max_violations_breakout` |
| valores movidos | **um só**: `rvol_min` 1,5 → 1,0 (teste: `test_only_the_rvol_floor_differs_in_value_from_the_mother`) |
| fecho | 13 módulos: `aggregate, base, canonical, envelope, indicators, numeric, schema, tl_events, tl_lines, tl_pivots, tl_scan, tl_setup, trendline_bounce_v1` |
| janela de contexto | **1 470 min** (cabe no piso de 1 560 já implantado ⇒ nenhuma população viva se move) |
| recusas | **duas**: `geometry`, `risk_too_wide`. A terceira da mãe (`geometry_invalidation`) **não existe** |
| invalidações | **`()`** — nunca |

**Três mudanças, e só três.** (i) uma porta, e ela é **identidade, não parâmetro** — sem `mode`,
nenhum `derive_variant --set` transforma esta versão de volta na outra; (ii) sem invalidação e sem o
guarda que a protegia; (iii) `rvol_min = 1,0` aplicado ao repique.

**O que deliberadamente NÃO mudou, com o motivo:**

- **`horizon_s` continua 28 800 s** embora a T3.34c mostre as saídas por expiração **positivas**
  (+0,6074 R em 9 casos), o que diz que 8 h é *curto*. Mexer é uma quarta mudança e tornaria o
  contraste pareado ilegível. Registrado no docstring e no EXP como a próxima variante candidata;
- **nenhum limiar de inclinação.** O C4 do EXP-0016 prometia `line_slope_per_bar` como substituto de
  regime e a T3.34c o refutou: o decil 1 de slope/ATR era *exatamente* o conjunto dos 5 rompimentos,
  por construção. Fechar a porta de rompimento **já é** esse filtro; acrescentar o limiar seria contar
  a mesma seleção duas vezes;
- **os 18 parâmetros de geometria são herança verbatim**, não reescolhidos aqui.

**Uma função nova, e a razão dela:** `_reason` é local em vez de reusar `tl_setup.decision_reason`,
porque aquela só menciona volume quando o evento é *rompimento* — e aqui o volume é o portão do
repique. Uma frase que omite o número que decidiu descreve outra decisão. `decision_envelope` da
`tl_setup` **é** reusada, exatamente para que o envelope das duas versões tenha a mesma forma e o
pareamento seja possível.

### Os quatro pontos de fiação

| arquivo | mudança | linhas |
|---|---|---|
| `packages/core/hunter_core/strategies/registry.py` | import + entrada no roster | **+2** (exatamente o que o brief autorizou) |
| `packages/core/hunter_core/strategies/constraints_table.py` | entrada `trendline_bounce_v1`, escrita **por extenso** e não compartilhada com a da mãe (a linha da mãe descreve um contrato já congelado e não pode ser tocada nem para refatorar) | +29 |
| `infra/scripts/seed_reference.py` | família `trendline_bounce` em `STRATEGIES` | +7 |
| `services/strategy-worker/hunter_strategy_worker/context_budget.py` | `_TRENDLINE` (claim compartilhada) + a linha da v2 em `WINDOWS` | +10 −8 |

Duas decisões destas merecem registro:

1. **`rvol_min` ficou em `non_negative`, não em `positive`.** `rvol_min = 0` é "sem porteiro de
   volume" — que é exatamente a contrafactual que o EXP-0022 pré-registra (recupera o repique da mãe).
   Recusá-la na tabela mataria o experimento que a própria versão pede. Teste:
   `test_turning_the_volume_gate_off_is_a_legitimate_variant`;
2. **`_TRENDLINE` é uma claim compartilhada pelas duas versões da família**, do mesmo jeito que `_ATR`
   já é compartilhada pelas oito. Motivo honesto: **o teto de 350 linhas do
   `check_file_size.py`** — a linha nova pôs `context_budget.py` em 362. Compartilhar é defensável
   (é literalmente o mesmo *call site*, herdado verbatim) e o teste-espião é quem notaria se as duas
   divergissem. Está escrito no docstring da constante, inclusive o custo: no dia em que divergirem, é
   uma mudança de duas linhas.

---

## 4. OS TESTES — recibos verbatim

Suíte nova: `packages/core/tests/unit/strategies/test_trendline_bounce_v1.py`, **52 casos**. As
séries **não** foram reescritas: são as duas ondas que `test_trendline_breakout_v1.py` já documenta
fórmula a fórmula, importadas — é isso que permite *asseverar* a paridade em vez de asseverá-la sobre
um sósia.

```
$ uv run pytest packages/core/tests/unit/strategies/test_trendline_bounce_v1.py -q -p no:randomly
....................................................                     [100%]
52 passed in 4.42s
```

E a suíte que importa, incluindo tudo o que o roster novo toca:

```
$ uv run pytest packages/core/tests/unit/strategies \
      services/strategy-worker/tests/test_context_budget.py \
      services/strategy-worker/tests/test_code_ref.py \
      services/strategy-worker/tests/test_constraints_outside_freeze.py \
      services/strategy-worker/tests/test_activation.py -q -p no:randomly
........................................................................ [ 83%]
........................................................................ [ 93%]
............................................                             [100%]
692 passed in 85.66s (0:01:25)
```

```
$ uv run python infra/scripts/check_file_size.py
scanned 587 files; 0 over budget, 0 grandfathered

$ uv run ruff check <os 7 arquivos>          → All checks passed!
$ uv run ruff format --check <os 7 arquivos> → 7 files already formatted
$ uv run pyright <os 6 módulos>              → 0 errors, 0 warnings, 0 informations
```

### As provas que o brief nomeou, uma a uma

| exigência do brief | teste | o que ele faz |
|---|---|---|
| **não-antecipação** (`test_no_lookahead.py` pattern) | `test_bars_after_the_cut_cannot_change_the_decision` | duas poluições depois do corte (uma absurda: high 9999, low 0,01, volume 999 999) não movem a decisão |
| **barra em formação** | `test_the_candle_still_forming_never_moves_the_decision` (3 casos) | um minuto `is_final=False` no corte, com preço e **volume** capazes de mover a mediana do RVOL, não muda a decisão **nem os bytes canônicos do envelope** |
| — (acréscimo meu, a outra metade da mesma regra) | `test_a_non_final_candle_inside_the_window_is_a_gap_not_an_input` | virar para `is_final=False` um minuto **de dentro** da janela vira `UNAVAILABLE`, não uma decisão sobre uma barra que não se pode ver |
| **paridade de geometria** | `TestGeometryParityWithTheMother` (4 casos) | na mesma barra em que as duas decidem: níveis idênticos, `atr` idêntico, e **todo** campo `line_* / event_* / pivot_* / pattern_* / channel_*` do envelope igual dígito a dígito — inclusive `pattern_params`. E as duas diferenças, isoladas: a mãe emite 1 invalidação, esta emite 0 |
| **os seis digests vivos** | `test_the_six_live_digests_did_not_move` | `momentum …ab2e0398…`, `volume_anomaly …9b8c14ab…`, `breakout …4c920b0c…`, `mean_reversion …a970c9d9…`, `session_orb …a4d514ad…`, **`trendline_breakout …7b83a1ff…`** |
| não importar a mãe | `test_the_closure_is_the_geometry_and_not_the_other_experiment` | fecho == os 13 módulos; `trendline_breakout_v1 not in closure` |

Mais três que valem citar porque medem a mudança em vez de a descreverem:

- `test_a_bounce_at_exactly_the_median_passes` — a onda congelada tem volume 10 em **todas** as
  barras, logo RVOL do repique é **exatamente 1,0**: a série é a prova de que o portão é inclusivo;
- `test_a_quiet_bounce_is_refused_with_its_number` / `test_the_same_quiet_bounce_is_a_signal_for_the_mother`
  — a **mesma** fita com o volume da barra de decisão em 9: a v2 responde `rvol_low` com `0.9` no
  detalhe, a mãe **dispara**. A diferença medida numa barra só, e é o portão, não a geometria;
- `test_there_is_no_invalidation_guard_left_to_refuse_anything` — `geometry_invalidation` não aparece
  em nenhum dos três caminhos testados.

**Nota de método, sem maquiagem:** o brief pede TDD e eu escrevi o módulo **antes** dos testes, não
depois — o que os testes têm de TDD-honesto é que **todo valor esperado é derivado das duas fórmulas
que a onda declara** (documentadas no cabeçalho do arquivo), nunca lido de uma execução. `params_hash`
e o `code_ref` são a exceção: são digests, e um digest só pode ser lido do código.

---

## 5. O EXP-0022, e o que ele custou de honestidade

`.claude/state/exp-drafts/EXP-0022-trendline-bounce.md`, **congelado** (hipótese, portão e protocolo;
avaliações são acrescentadas). Não toquei em `obsidian/**`.

**O portão saiu `REVISE`**, com dois vereditos que valem ser lidos:

- **C4 = `FAIL` declarado.** O EXP-0016 tinha `PASS por herança` prometendo a inclinação como
  substituto de regime; a T3.34c refutou isso. Esta versão **não tem** substituto de regime e diz que
  não tem. Mentir menos custa um `FAIL` a mais;
- **C8 = `N/A por construção`** — não há invalidação, e é essa a tese. O que substitui o critério é
  uma medição **de mão dupla** (item 5 do dia um): se a cauda esquerda da v2 for **pior** que a da v1
  pareada por barra, a tese está errada e isso tem de aparecer com a mesma clareza;
- **C2 = `REVISE`, e é o risco dominante**, declarado sem eufemismo: a porta foi escolhida **depois
  de ver o resultado** da v1, sobre a mesma janela. É [[KB-0010]] em estado puro. A única leitura que
  vale como confirmação é **prospectiva**.

O dia um pré-registra sete itens, e três deles são novos em relação à v1: (1) por que a população
**não** é subconjunto e o pareamento é por `(mercado, barra)`; (4) expectancy por **tercil de RVOL**
— se o tercil baixo não for pior, o portão não selecionou nada e o `rvol_min` é decoração, o que é um
resultado; (5) o contraste pareado com **quatro** números obrigatórios (n pareado, n só-v2, n só-v1,
Δ com IC por bloco de dia + Holm + a cauda esquerda das duas).

---

## 6. CONCERNS

**CONCERN 1 — a UI do Lab e o `render_operations.py` sabem uma versão só, e isso vira falso na
ativação.** Três lugares afirmam, hoje corretamente, que **só** `trendline_breakout_v1` lê linhas
para decidir:

- `apps/web/components/lab/lab-signal-detail.tsx:121` — *"Esta versão não lê linhas de tendência (só
  `trendline_breakout v1` persiste geometria de linha)"*. A `trendline_bounce_v1` **persiste a mesma
  geometria** (mesmo `decision_envelope`), então a UI dirá o contrário do que o envelope traz;
- `apps/web/lib/lab-trendline.ts:4` — o parser cita a v1 pelo nome;
- `infra/scripts/render_operations.py:175` — `reads_lines = first.strategy == "trendline_breakout"`,
  e o dicionário `EXPERIMENT` (linha 59) não tem chave `trendline_bounce-v1`.
- `docs/PIPELINE.md` §9b item 4 — *"Só `trendline_breakout_v1` **lê** linha para decidir"*.

**Não corrigi nenhum dos quatro**: estão fora da lista de arquivos que o brief autoriza, a árvore é
compartilhada, e a afirmação só fica falsa quando o orquestrador ativar a versão. É trabalho de uma
tarefa própria (front + a ferramenta + a linha do doc), e o texto sugerido para o doc é *"`…_breakout_v1`
e `…_bounce_v1` leem linha para decidir"*.

**CONCERN 2 — a projeção de +0,2401 R é in-sample duas vezes.** Ela vem dos mesmos 26 episódios da
v1 que sugeriram a porta, e o Δ da invalidação vem do mesmo replay. Está no EXP como "o valor que a
aritmética implica", nunca como expectativa. **Ninguém deve ler o replay de 31 d como confirmação:**
o rótulo é `REPLAY` e serve para matar.

**CONCERN 3 — o `rvol_min` continua sem evidência.** A tabela do §2 é in-sample e não-monótona; a
pergunta "o volume seleciona?" só é respondida pelo item 4 do dia um. Se o tercil baixo não for pior,
o portão é decoração — e nesse caso a versão certa é `rvol_min = 0`, que a tabela de constraints
deliberadamente permite.

**CONCERN 4 — `_TRENDLINE` compartilhada em `context_budget.py` foi forçada pelo teto de 350
linhas**, não escolhida por desenho. É defensável (mesmo *call site*, herdado verbatim) e o
teste-espião pega uma divergência, mas registro que a alternativa "cada versão com a sua linha" foi
descartada por orçamento de arquivo, não por argumento. O comentário no código diz isso.

**CONCERN 5 — a árvore estava (e está) compartilhada durante a minha janela.** Outras tarefas
mexeram, ao vivo, em `catalogue.py`, `regime_gate.py`, `context.py`, `record.py`, `roster.py`,
`variant.py`, `derive_variant.py`, `builders.py`, `test_regime_gate_policy.py` e criaram
`gate_policy.py`/`hours_gate*.py`. Consequência visível: `services/strategy-worker/tests/test_regime_gate_policy.py`
**não coleta** (`ImportError: cannot import name 'parse_policy'`), e por isso a suíte do worker foi
rodada com `--ignore` nesse arquivo. **Não é meu e não toquei.** Os cinco arquivos que eu modifiquei
têm `git diff --numstat` compatível com exatamente as minhas mudanças (7/0, 2/0, 29/0, 10/8, 5/3).

**CONCERN 6 — TDD invertido.** Ver a nota de método no fim do §4.

**CONCERN 7 — não rodei nada na VPS além de uma leitura.** O `seed.py --dry-run`, a ativação e o
replay dependem do commit+deploy que é do orquestrador. Isso significa que o `code_ref`
`…fb7263ce…` e o `params_hash` `9b1e882f169c89ca` acima são **calculados na minha árvore**, não
confirmados por um `--dry-run` na imagem. **Se o `--dry-run` imprimir outro digest, PARE** — é sinal
de que a árvore da imagem não é esta.

---

## 7. ARQUIVOS — a lista exata para o orquestrador commitar

**Novos (4):**

```
packages/core/hunter_core/strategies/trendline_bounce_v1.py
packages/core/tests/unit/strategies/test_trendline_bounce_v1.py
infra/scripts/sql/research/2026-09-09-t357-q00-rvol-dos-repiques.sql
.claude/state/exp-drafts/EXP-0022-trendline-bounce.md
```

**Modificados (5) — `git diff --numstat`, para conferência antes do `git commit -- <pathspec>`:**

```
 7  0  infra/scripts/seed_reference.py
 2  0  packages/core/hunter_core/strategies/registry.py
29  0  packages/core/hunter_core/strategies/constraints_table.py
10  8  services/strategy-worker/hunter_strategy_worker/context_budget.py
 5  3  services/strategy-worker/tests/test_context_budget.py
```

**Mais este arquivo:** `.claude/state/notes-T3.57.md`.

**NÃO commitar** (de outras tarefas em voo, §8): `derive_variant.py`, `catalogue.py`,
`regime_gate.py`, `gate_policy.py`, `hours_gate.py`, `context.py`, `record.py`, `roster.py`,
`variant.py`, `builders.py`, `test_regime_gate_policy.py`, `test_hours_gate*.py`,
`test_seed_dry_run.py`, `test_schema_seed_and_partitions.py`, `docs/DESIGN.md`, `.claude/launch.json`.

---

## 8. O QUE VEM DEPOIS (para quando o orquestrador me chamar de volta)

1. `docker exec hunter-api-1 python infra/scripts/seed.py --only strategies --dry-run` — tem de
   mostrar **exatamente duas** linhas `NEW` (`strategies.trendline_bounce` e
   `strategy_versions.trendline_bounce v1`) e mais nada; depois `--yes`;
2. `activate_strategy_version.py trendline_bounce v1 --dry-run` — tem de imprimir
   `…trendline_bounce_v1@sha256:fb7263ce…` e `(34 parameters)`. **Digest diferente ⇒ PARAR**;
3. replay 31 d × 4 mercados (ETH, SOL, XRP, DOGE), `--explain-ledger`, `--cohort` explícita, duas
   fatias (~48 barras/s medidas na T3.34c ⇒ ~130 s por fatia de 6 000 barras);
4. o pareamento contra `replay:d78c14d1-b4c5-424a-8f31-a43100744bb4` **por `(mercado, barra)`**, com
   os quatro números obrigatórios do item 5 do EXP — e nunca supondo subconjunto (§2);
5. os sete itens do "o que o dia um tem de publicar" do EXP-0022, na ordem em que estão lá.
