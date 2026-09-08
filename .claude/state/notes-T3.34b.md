# Notas T3.34b — `trendline_breakout_v1`: a geometria virou estratégia, e virou cópia

**Quando:** 2026-09-08. **Owner:** quant-engineer. **Base:** `main` em `7b0edeb`.
**Nada foi commitado. Nada foi ativado. A VPS não foi tocada.**
Os três digests vivos **não se moveram** — provado por teste, e os valores estão na §3.

---

## STATUS

**`DONE_WITH_CONCERNS`.** O módulo, os cinco irmãos planos (quatro portados, um de política), a
paridade numérica, as três linhas de catálogo e o rascunho EXP-0016 com o portão C1–C8 estão
entregues; todos os testes de arquivo passam; `ruff`/`pyright`/`check_file_size` limpos nos arquivos
desta task. **Nada foi commitado e a VPS não foi tocada.** São **seis** ressalvas (CONCERNS, no fim);
a que mais pesa é que **o portão C1–C8 devolveu `REVISE`, não `PASS`** (C1, C2 e C3) e que ele foi
escrito **depois** do módulo, pelo mesmo quant — autoavaliação, não revisão.

---

## FILES

| arquivo | o que é |
|---|---|
| `C:\dev\project-hunter\packages\core\hunter_core\strategies\tl_pivots.py` | **novo**, 210 linhas. Escala de ATR por barra (`atr_series`) e pivôs (`find_pivots`). Porte de `hunter_indicators/patterns/{scale,pivots}.py` (`db798b8`) |
| `C:\dev\project-hunter\packages\core\hunter_core\strategies\tl_lines.py` | **novo**, 319 linhas. `TrendLine`, `find_lines`. Porte de `patterns/trendlines.py` |
| `C:\dev\project-hunter\packages\core\hunter_core\strategies\tl_events.py` | **novo**, 302 linhas. `LineEvent`, `detect_events` (repique, rompimento, reteste). Porte de `patterns/events.py` |
| `C:\dev\project-hunter\packages\core\hunter_core\strategies\tl_scan.py` | **novo**, 268 linhas. `TlParams`, `TlScan`, `tl_scan` (o único lugar onde o corte é aplicado), `Channel`/`find_channels`. Porte de `patterns/{scan,channels}.py` **mais** `retire_after_break` |
| `C:\dev\project-hunter\packages\core\hunter_core\strategies\tl_setup.py` | **novo**, 329 linhas. **Não é porte:** camada de política da estratégia (qual evento abre porta, o pivô do stop, o canal da linha, a frase da razão e o envelope) |
| `C:\dev\project-hunter\packages\core\hunter_core\strategies\trendline_breakout_v1.py` | **novo**, 350 linhas. A versão congelada, 37 parâmetros |
| `C:\dev\project-hunter\packages\core\hunter_core\strategies\registry.py` | **+1 import, +6 linhas** no `DEFAULT_REGISTRY` (a tupla passou a multilinha pelo formatador) |
| `C:\dev\project-hunter\packages\core\hunter_core\strategies\constraints_table.py` | **+1 entrada** `trendline_breakout_v1` (faixas, dois `bounded` estruturais, três pares `ordered`) |
| `C:\dev\project-hunter\infra\scripts\seed_reference.py` | **+1 linha** em `STRATEGIES`: `("trendline_breakout", "Trendline Breakout", "trend", …)` |
| `C:\dev\project-hunter\packages\core\tests\unit\strategies\test_tl_parity.py` | **novo**. Paridade numérica exata contra `hunter_indicators.patterns`, 33 testes |
| `C:\dev\project-hunter\packages\core\tests\unit\strategies\tl_builders.py` | **novo**. Cópia do gerador sintético da T3.34 (`packages/indicators/tests/patterns/builders.py`) |
| `C:\dev\project-hunter\packages\core\tests\unit\strategies\test_trendline_breakout_v1.py` | **novo**. 32 testes: dispara, não dispara, indisponível, recusa, aposentadoria, pureza |
| `C:\dev\project-hunter\packages\core\tests\unit\strategies\test_no_lookahead.py` | **+5 testes** no fim do arquivo (bloco `trendline_breakout_v1 (T3.34b)`); nada existente alterado |
| `C:\dev\project-hunter\packages\core\tests\unit\strategies\test_constraints.py` | **+1 classe** `TestTrendlineBreakoutV1Ranges` (15 recusas por nome) e **+1 teste** de autoconsistência |
| `C:\dev\project-hunter\packages\core\tests\unit\strategies\test_registry.py` | **+1 estratégia** nas listas `STRATEGIES`/`CONTEXTS` |
| `C:\dev\project-hunter\services\strategy-worker\tests\test_code_ref.py` | **+1 teste** (`test_the_trendline_closure_covers_the_ported_geometry`) e **+1 asserção** no teste de isolamento |
| `C:\dev\project-hunter\.claude\state\exp-drafts\EXP-0016-trendline-breakout.md` | **novo**. Hipótese e protocolo congelados, portão C1–C8 (`REVISE`), K1–K5 + a regra dos 60 % |
| `C:\dev\project-hunter\.claude\state\notes-T3.34b.md` | este arquivo |

**Não toquei:** `base.py`, `aggregate.py`, `indicators.py`, `schema.py`, `envelope.py`,
`canonical.py`, `numeric.py`, `momentum_v1.py`, `volume_anomaly_v1.py`, `breakout_v1.py`,
`mean_reversion_v1.py`, `session_orb_v1.py`, `hunter_indicators/patterns/**`, `.env*`, `apps/**`,
`services/**` (exceto o teste de `code_ref` acima), `obsidian/**`.

---

## 1. A decisão do orquestrador, executada — e o que ela custou

**Opção C: portar.** `hunter_core.strategies` não pode importar `hunter_indicators.patterns` (ciclo
de distribuição **e**, pior, `code_ref.module_closure` só segue irmãos planos, então a geometria
ficaria fora do digest que congela a versão). Os cinco `tl_*` são irmãos planos e o fecho os cobre:

```
module_closure("trendline_breakout_v1") ==
  ('aggregate', 'base', 'canonical', 'envelope', 'indicators', 'numeric', 'schema',
   'tl_events', 'tl_lines', 'tl_pivots', 'tl_scan', 'tl_setup', 'trendline_breakout_v1')
```

**Cinco módulos, não três.** O brief pediu `tl_pivots`, `tl_lines`, `tl_events`; o orçamento de 350
linhas do mesmo brief não deixa: `trendlines.py + channels.py` dá 388 linhas e `events.py +
scan.py` dá 491. O corte ficou: `tl_scan.py` recebeu o ponto de entrada, os canais e o `TlParams`;
`tl_setup.py` recebeu o que **não** é porte (a política da estratégia e o envelope), porque
`trendline_breakout_v1.py` sozinho dava 537 linhas. Os dois estão dentro do fecho, que é o ponto.

**O custo declarado do `tl_setup.py`, para ninguém descobrir depois:** uma futura
`trendline_*_v2` que precise de outra política de gatilho **não pode editá-lo** — editar re-congela
a `v1`. Ela abre módulo próprio, exatamente como as versões de estratégia fazem. Está escrito no
docstring dele.

### 1.1 Uma divergência deliberada do original, declarada e testada

Algumas divisões do pacote de pesquisa rodam sob o contexto decimal **ambiente**
(`patterns/pivots.py` escala a proeminência fora do `localcontext`; dois ramos de
`patterns/events.py` idem). **Na cópia, toda operação roda dentro de `CONTEXT`**, porque uma versão
congelada cujos números dependem do que alguma biblioteca fez com `decimal.getcontext()` não está
congelada. Sob o contexto padrão (28 dígitos, `ROUND_HALF_EVEN`) as duas dão valores **idênticos** —
é o que a paridade afirma; sob um contexto hostil, só a cópia continua dando. Provado por
`test_the_copy_survives_an_ambient_decimal_context_the_upstream_does_not`, que afirma as duas metades
(a cópia não se move **e** o original se move).

### 1.2 `retire_after_break` — a única regra que a cópia acrescenta

Correção 1 da KB-0077. Uma linha cujo rompimento é mais velho que `retest_bars` deixa de ser
desenhada: não é gatilho, não é lado de canal, não é número no envelope. **Aplicada depois de
`find_lines`**, e o custo está declarado no docstring de `tl_scan.py`: a vaga que a linha aposentada
ocupou entre as `max_lines` **não** vai para a próxima candidata. Fazê-lo dentro da seleção mudaria
`find_lines` e quebraria a paridade — e com `retire_after_break = False` as duas implementações são
idênticas, que é a configuração em que a paridade roda.

Medido no teste (série com o rompimento 19 barras antes do corte): com a regra desligada sobram
5 linhas, 3 canais e 22 eventos; com ela ligada, 3 linhas, 2 canais e **0** eventos, e as duas linhas
rompidas aparecem em `scan.retired`.

---

## 2. Duas correções ao contrato do brief (declarar, não esconder)

1. **`max_violations = 0` no rompimento é impossível.** `TrendLine.violations` conta os fechamentos
   através da linha **até o corte**, e a linha sobrevive de propósito ao próprio rompimento para que
   o rompimento possa ser reportado (`notes-T3.34.md` §2.4) — a barra que rompe **é** uma violação.
   Com 0, a versão responderia `line_weak` a todo rompimento que existe: uma coorte que só sabe
   dizer uma palavra. **Congelado em 1**, que diz o que o brief queria dizer (*nenhuma violação antes
   desta barra*); o repique mantém o 2 do brief, porque uma barra de repique não é violação. Provado
   por `test_max_violations_zero_would_refuse_every_breakout_there_is`. **Foi encontrado pelo teste**,
   não por leitura: a primeira execução da série sintética devolveu
   `not_triggered line_weak {'line_touches': '8', 'line_violations': '1'}`.
2. **O `min` do brief §4 está certo, e a leitura ingênua estava errada.**
   `stop = min(pivô de baixa, C − stop_atr_max·ATR)` faz de `stop_atr_max` um **teto sobre o preço do
   stop**, isto é, um **piso de 2 ATR sobre a distância** — folga mínima, para que um pivô impresso
   duas velas atrás não vire um stop que o ruído leva. `max_risk_atr` (3 ATR) é o outro lado do par.
   Com essa leitura os dois parâmetros trabalham (risco fica entre 2 e 3 ATR) e o par ordenado
   `stop_atr_max < max_risk_atr` do `constraints_table` é **carga**, não decoração: invertido, toda
   barra sairia `risk_too_wide`. Cheguei a escrever `max` antes de reler; o `min` fica.

Nenhum outro parâmetro do brief foi mexido. Os dois `max_violations_*` e o `mode` são chaves novas
porque o brief pedia um par de valores e uma escolha de porta.

---

## 3. Digests — nada vivo se moveu

```
momentum_v1              hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c
volume_anomaly_v1        hunter_core.strategies.volume_anomaly_v1@sha256:9b8c14ab3390646ac9adb26fbbb90e160a800f1c70f128d873a49ffd1dd19f22
breakout_v1              hunter_core.strategies.breakout_v1@sha256:4c920b0cc412429c2c4a6a19ca389aca8a215a638f0ff750a8caf61b16264ff1
mean_reversion_v1        hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f
session_orb_v1           hunter_core.strategies.session_orb_v1@sha256:a4d514adeb0771d5ae23303878fb4fdac734721d6ac0140801c88d617e878bba
trendline_breakout_v1    hunter_core.strategies.trendline_breakout_v1@sha256:7b83a1ff07946fa743d12c9d098f15b538c2e2b19f5269363203ee0671e19648
```

Os dois exigidos pelo §2 do brief (`…ab2e0398…` e `…9b8c14ab…`) batem, e o
`session_orb_v1 …a4d514ad…` é o mesmo que a `notes-T3.33g` registrou na ativação da VPS.
**O digest da `trendline_breakout_v1` só é válido enquanto ninguém editar nenhum dos 13 módulos do
fecho** — conferir no `--dry-run` antes de ativar.

---

## 4. A série sintética, e por que os números são conferíveis à mão

```
low(i)  = 1000 − 0,5·i + offset(i)   offset = onda triangular, amplitude 3, período 10
high    = low + 20                   close = low + 10
```

Daí: os picos caem **exatamente** sobre `resistance(i) = 1035 − 0,5·i` e as cavas sobre
`support(i) = 1000 − 0,5·i` — duas paralelas a 35 de distância, descendo meio ponto por barra. E o
true range de **toda** barra é `high − low = 20`, então o ATR de Wilder é **exatamente 20** até a
barra que quebra o padrão. A barra do rompimento tem amplitude 37,5, logo
`ATR = (20·13 + 37,5)/14 = 21,25`, à mão.

Com isso, cada nível da decisão sai de uma conta, não de uma execução do detector:

| grandeza | conta | valor |
|---|---|---|
| referência | `resistance(119) + 12` | 987,5 |
| linha na barra da decisão | `resistance(119)` | 975,5 |
| pivô de baixa (último confirmado) | `support(115)` | 942,5 |
| stop | `min(942,5; 987,5 − 2·21,25)` | **942,5** (a estrutura vence) |
| risco | | 45 = 2,1176 ATR |
| alvo1 | `987,5 + max(35; 2·45)` | **1077,5** (2 R vence o canal) |
| toques | picos locais 16…86 | **8** (os dois primeiros da janela caem no aquecimento do ATR — sem escala não há pivô) |

A série do **repique** é a espelhada (inclinação +0,5) e existe para provar o **outro** lado da regra
do stop: ali a última cava está a só 1 ATR do fechamento, então `C − 2·ATR = 1032,5` é o menor dos
dois e vira o stop, com risco de exatamente 2 ATR. Uma série prova o stop estrutural, a outra o piso
em ATR.

**A série `geometry_invalidation` foi a mais difícil e vale registro.** Num rompimento comum a última
cava fica mais de 2 ATR abaixo da linha, então o stop **sempre** fica abaixo dela e a guarda nunca
dispara. O único formato em que ela dispara é o que o brief §4 descreve sem nomear: o mercado
consolida colado à linha enquanto ela continua descendo, a última mínima confirmada (977) termina
**acima** da linha no corte (975,5), e um rompimento de quase 3 ATR leva `C − 2·ATR` para cima dela
também. A recusa é então correta e estrutural — uma invalidação abaixo do stop é código morto.

---

## 5. TESTS — saída real

### 5.1 Paridade numérica (a prova de que a cópia é a cópia)

```
$ uv run pytest packages/core/tests/unit/strategies/test_tl_parity.py -q
.................................                                        [100%]
33 passed in 32.53s
```

Seis séries (a onda sintética em dois tamanhos e quatro passeios pseudoaleatórios de 240 barras,
sementes 1/7/42/2026), e para cada uma: `atr_series`, `find_pivots`, `find_lines` (inclusive o
`line_id`, que é um sha256 sobre a geometria canônica — igualdade ali prova `origin`, `through`,
inclinação e âncoras até o último dígito), `find_channels`, `detect_events` e a **varredura inteira
a cada oitava barra** (~30 cortes por série), tudo em igualdade **exata** de `Decimal`.
Mais: os defaults dos dois `PatternParams` são comparados chave a chave — `retire_after_break` é a
única que a cópia acrescenta, e acrescentar outra não pode ser silencioso.

**Substituto declarado:** o brief pedia "uma série real exportada (`.claude/state/design/trendlines/`
CSV se tiver sido guardado; senão os builders)". Os CSV **não** ficaram na árvore (só os seis PNG),
então a segunda série é o passeio pseudoaleatório dos mesmos builders — que é o que o brief nomeia
como alternativa e que produz **muito mais** geometria (pivôs dos dois lados, rompimentos e
retestes) do que a onda limpa.

### 5.2 A estratégia

```
$ uv run pytest packages/core/tests/unit/strategies/test_trendline_breakout_v1.py -q
................................                                         [100%]
32 passed in 4.52s
```

Cobre: dispara no rompimento (direção, referência, stop, alvo, invalidação, razão, ATR, canal e o
envelope inteiro); dispara no repique; `no_line`, `no_event`, `rvol_low`, `line_weak`,
`atr_out_of_range`, `ineligible`; `warmup`, `gap` (um minuto removido do meio), `atr_warmup`,
`rvol_unavailable`; `geometry`, `geometry_invalidation`, `risk_too_wide`; a aposentadoria e a
fronteira exata da janela de reteste (`76 + 10 == 86` ainda vale, 87 já não); pureza; orçamento de
janela.

### 5.3 Antecipação

```
$ uv run pytest packages/core/tests/unit/strategies/test_no_lookahead.py -q
................................................................         [100%]
64 passed in 12.62s
```

Os cinco novos: as três poluições do brief §8.7 comparadas no **JSON canônico do envelope** (vela não
final dentro da janela, vela final que fecha depois do corte, futuro adulterado, e as duas juntas);
a vela em formação mutada de três formas (absurda, chapada, plausível) sem mover nada; a decisão
avaliada uma barra antes do rompimento (é `None` — nada tinha acontecido); bootstrap contra execução
contínua barra a barra sobre as 120 barras, com decisão **só** na última; e nove combinações de
contexto decimal hostil (`prec` 2/6/28 × três arredondamentos).

**Foi aqui que apareceu um defeito real,** introduzido por mim ao comprimir o módulo:
`_display(atr_pct * _PERCENT)` fazia a multiplicação **fora** do `localcontext`, e com
`getcontext().prec = 2` a frase saía "ATR% 2.20%" em vez de "2.15%". O `scale` passou para dentro
de `_display`. É exatamente o defeito que a Astra achou no diff da S1 e o motivo de o teste existir.

### 5.4 Faixas, registro e congelamento

```
$ uv run pytest packages/core/tests/unit/strategies/test_constraints.py -q
77 passed in 1.05s
$ uv run pytest packages/core/tests/unit/strategies/test_registry.py -q
36 passed in 1.11s
$ uv run pytest services/strategy-worker/tests/test_code_ref.py -q
27 passed in 5.99s
```

As recusas exigidas pelo brief §8.11 estão nas 15 parametrizações de
`TestTrendlineBreakoutV1Ranges`: `min_touches = 1` (fora de [2, 20] — abaixo de 2 `find_lines`
**levanta**, então a variante não ficaria fraca, ficaria quebrada a cada barra), `break_atr = 0`,
`target_r = 0`, `atr_pct_min > atr_pct_max`, `base_confidence = 42` e `stop_atr_max > max_risk_atr`
(mais o caso de igualdade, que também é recusado).

### 5.5 Suítes inteiras (nenhuma regressão)

```
$ uv run pytest packages/core/tests/unit -q                       -> 1038 passed in 95.67s
$ uv run pytest services/strategy-worker/tests -q -m "not integration"
                                                                  -> 236 passed, 186 deselected in 7.53s
$ uv run pytest packages/indicators/tests/patterns -q             -> 31 passed in 10.40s
$ uv run pytest infra -q -m "not integration"                     -> 109 passed, 24 deselected in 15.38s
```

### 5.6 Qualidade

```
$ uv run ruff check packages/core infra/scripts/seed_reference.py services/strategy-worker/tests/test_code_ref.py
All checks passed!
$ uv run ruff format --check packages/core/tests/unit/strategies packages/core/hunter_core/strategies \
    infra/scripts/seed_reference.py services/strategy-worker/tests/test_code_ref.py
40 files already formatted
$ uv run pyright packages/core/hunter_core/strategies <os 5 arquivos de teste desta task>
0 errors, 0 warnings, 0 informations
$ uv run python infra/scripts/check_file_size.py
error   359 > 350  packages/core/hunter_core/settings.py
scanned 569 files; 1 over budget, 0 grandfathered
```

O único arquivo acima do orçamento **não é desta task** (`settings.py`, 359, de outro trabalho em
voo; durante a sessão `apps/api/hunter_api/realtime/endpoint.py` apareceu e sumiu da lista — a
árvore é compartilhada). Os seis arquivos novos: 210 / 319 / 302 / 268 / 329 / **350**.

---

## 6. Sequência exata para o brief seguinte (VPS) — **não executada**

A VPS é somente leitura nesta task. A sequência congelada, para quem tiver a palavra do operador:

```bash
# 1. catálogo: a chave `trendline_breakout` ainda não existe em `strategies`
docker exec hunter-api-1 python infra/scripts/seed.py --only strategies --dry-run
docker exec hunter-api-1 python infra/scripts/seed.py --only strategies --yes

# 2. a imagem tem de carregar o módulo novo (deploy primeiro; sem isso o passo 3 mente)
docker exec hunter-strategy-worker-1 python -c \
  "import hunter_core.strategies.trendline_breakout_v1 as m; print('import ok', m.TRENDLINE_BREAKOUT_V1.key, m.TRENDLINE_BREAKOUT_V1.version)"

# 3. ativação, DRY-RUN primeiro, conferindo o digest da §3
docker exec -i hunter-api-1 python - trendline_breakout v1 --dry-run \
  --changelog 'T3.34b: rompimento e repique de linha de tendencia, coorte de pesquisa (research_only, sem carteira)' \
  < infra/scripts/activate_strategy_version.py
# esperado: hunter_core.strategies.trendline_breakout_v1@sha256:7b83a1ff07946fa743d12c9d098f15b538c2e2b19f5269363203ee0671e19648

# 4. ativação de verdade (sem --dry-run), depois 10 min de vigia de capacidade

# 5. replay em DUAS fatias com a MESMA coorte
docker exec hunter-strategy-worker-1 python -m hunter_strategy_worker.replay.run \
  --version trendline_breakout:v1 --from 2026-08-08 --to 2026-08-23 \
  --markets ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT --workers 3 \
  --cohort replay:<uuid> --ledger /tmp/replay-trendline-v1.jsonl
# segunda fatia 2026-08-23 -> 2026-09-08, MESMA coorte
```

E o dia um **tem** de publicar, além do recibo padrão: linhas válidas por barra avaliada;
distribuição de `touches`; fração de rompimentos com reteste; taxa de `risk_too_wide` e de
`geometry_invalidation` (acima de 20 % das barras que de outro modo dispararam, o par
pivô/teto está errado, e isso é **versão nova**); e `pattern_retired_lines` por barra.

---

## CONCERNS

1. **O portão C1–C8 devolveu `REVISE`, não `PASS`, e foi autoavaliação.** Três `REVISE`: **C1**
   (o mecanismo é o mesmo do `breakout_v1`, que deu 0 decisões em 31 d, e do `session_orb_v1`, que
   deu −0,19 R — a inclinação da linha nunca foi medida como informação); **C2** (dezoito
   parâmetros de geometria congelados de uma vez, nenhum medido: é a versão com mais graus de
   liberdade desta casa); **C3** (não sei estimar a frequência de decisão, e **K1 é risco real** —
   as figuras da T3.34 dão 4 a 9 eventos por mercado em 14 dias, mas numa varredura retrospectiva,
   que não é a mesma contagem). Além disso, o brief pedia o portão **antes** do módulo e ele foi
   escrito **depois**, na mesma sessão, pelo mesmo quant: é autoavaliação, e a revisão da Astra
   sobre as **regras de decisão** (não sobre a geometria, que ela já revisou na T3.34) está
   **pendente**.
2. **Cinco módulos `tl_*`, não os três do brief, e um deles não é porte.** O orçamento de 350 linhas
   não deixava três (`trendlines + channels` = 388; `events + scan` = 491). `tl_setup.py` é camada
   de política e envelope, e o preço está declarado: uma `v2` que precise de outra política de
   gatilho não pode editá-lo sem re-congelar a `v1`.
3. **A paridade não cobre uma série real.** Os CSV exportados da VPS na T3.34 não ficaram na árvore
   (só os PNG), então a segunda série é o passeio pseudoaleatório dos builders — o que o brief nomeia
   como alternativa, mas **não** é uma fatia de ETHUSDT. Quem quiser a prova sobre dado real precisa
   reexportar (consulta somente leitura, `psql` pelo stdin, CSV pelo stdout, como a T3.34 fez).
4. **`geometry_invalidation` só é alcançável num formato estreito.** Está testado, com série própria
   e o porquê escrito no docstring dela, mas o caminho é o de consolidação colada à linha: num
   rompimento comum a última cava fica mais de 2 ATR abaixo da linha e a guarda **nunca** dispara.
   Se o replay do dia um vier com 0 % de `geometry_invalidation`, isso é o esperado, não um defeito —
   e a taxa que importa medir é a de `risk_too_wide`.
5. **Três erros de `pyright` pré-existentes na árvore**, não introduzidos aqui e não corrigidos por
   mim (são linhas de outra gente em arquivos compartilhados): `test_mean_reversion_v1.py:421,425`
   (`append`/`decision` parcialmente desconhecidos) e `test_no_lookahead.py:392`
   (`_envelope_json` devolve `bytes` mas está anotado `-> str`, idêntico ao que está em `HEAD`).
   `pyright` sobre os arquivos **desta** task dá 0 erros.
6. **A distância do stop (2 a 3 ATR) fura o `max_stop_distance_pct` de 3 % do `paper_v1`.**
   Irrelevante enquanto a versão for `research_only` — nada chega à carteira —, e **impeditivo** se
   alguém quiser promovê-la a `paper` sem antes mexer no limite ou no stop. Está declarado no
   C5 do EXP-0016.
