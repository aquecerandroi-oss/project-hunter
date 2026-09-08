# notes-T3.45b — `sweep_reclaim_v1`: a varredura de uma mínima de swing, recuperada (15 m)

**Data:** 2026-09-08 (UTC; Brasília = UTC−3). **Owner:** quant-engineer.
**Brief:** `.claude/state/brief-T3.45b-sweep_reclaim_v1.md`. **Contrato congelado:** `EXP-0017`.
**Nada commitado. Nada ativado. Nenhuma coorte criada. Nenhum container tocado. Nenhum replay
rodado. VPS não tocada.** Não mexi em `.env*`, `apps/**`, `services/**` (exceto **ler** e **rodar**
`services/strategy-worker/tests/test_code_ref.py`), `obsidian/**`, nem em nenhum dos sete irmãos do
fecho das versões vivas.

---

## STATUS

**DONE_WITH_CONCERNS.** O módulo, os testes, o registro, a tabela de faixas e a linha do catálogo
estão escritos e verdes. Duas coisas ficam declaradas e não maquiadas: (1) o digest da
`trendline_breakout_v1` **já não era** o do §2 do brief antes de eu tocar em nada — a T3.34b o moveu
em paralelo — e por isso a sexta asserção do §2 virou uma prova **estrutural** em vez de um dígito
cravado; (2) `infra/scripts/seed_reference.py` **já estava acima** do orçamento de 350 linhas por
trabalho em voo de outro agente, e a minha linha (obrigatória pelo brief) o deixa mais alto ainda.

| # | Entrega do brief | Resultado |
|---|---|---|
| 1 | Módulo `sweep_reclaim_v1.py`, <= 350 linhas, fecho igual ao da `mean_reversion_v1` | **OK.** 350 linhas exatas; fecho = `aggregate, base, canonical, envelope, indicators, numeric, schema` |
| 2 | Regra por motivo, na ordem congelada, com o vocabulário do §4 | **OK.** 10 ramos, um `return` cada |
| 3 | 20 parâmetros congelados, `parameters_schema` com uma linha por chave | **OK.** `params_hash` fixado em teste |
| 4 | Envelope do §9 (pivô com idade e proeminência, pedágio, `AtrEvidence`) | **OK.** 13 features + ATR + custos |
| 5 | `constraints_table.py` + `registry.py` + `seed_reference.py`, **só a minha linha** | **OK.** |
| 6 | Os 13 grupos de teste do §10 | **OK.** 46 testes no arquivo próprio + 5 casos no `test_no_lookahead.py` |
| 7 | Isolamento do digest (§2) | **OK para as cinco versões estáveis**; a sexta virou prova estrutural (CONCERN 1) |

---

## O QUE FOI CONSTRUÍDO, E AS DECISÕES QUE VALEM SER LIDAS

### O detector de pivô mora dentro do módulo — e a paridade com `tl_pivots` é provada por teste

O brief (§2) proíbe importar `tl_pivots`/`tl_scan`/`tl_lines`: juntar os fechos faria qualquer
conserto futuro numa reta de tendência **re-congelar esta coorte**. A instrução paralela ("se
`tl_pivots` existir, reuse") e o brief se resolvem sem escolher entre eles: a regra é reusada
**semanticamente** e a igualdade é mantida por um teste que vive fora de qualquer fecho —

```
test_the_detector_agrees_digit_for_digit_with_the_tl_pivots_port
```

compara `_latest_pivot_low` com `tl_pivots.find_pivots` (k = 3, proeminência >= 1, ombros excluindo a
própria barra, empate para a barra mais velha) em **cinco** séries sintéticas, com igualdade exata de
`Decimal` no índice **e** na proeminência. Se as duas divergirem um dia, o teste quebra — que é
exatamente o que a duplicação precisa ter para ser honesta. Divergência declarada e intencional: aqui
a escala é **uma** leitura de ATR por decisão; lá é o ATR de cada barra.

### A série sintética: todo número esperado é exato e escrito à mão

120 barras de 15 min. Patamar em 100 com meia-amplitude 0,45 (todo `true_range` = 0,9), um mergulho
`99,6 / 99,2 / 98,75 / 99,2 / 99,6` cujo fundo tem **mínima 98,30**, e a barra de sinal
`open 100 / high 100,3 / low 98 / close 100 / volume 200`, cujo `true_range` vale
`max(2,3; 0,3; 2) = 2,3`. Daí o ATR de Wilder(14) sobre as 97 barras da janela é

```
(0,9 × 13 + 2,3) / 14 = 14/14 = 1   exato, sem arredondamento
```

e a geometria do §10.2 do brief cai redonda **na série real**, não só numa conta ao lado:

```
referência 100 · stop 97,9 · risco 2,1 · alvo1 104,2 · alvo2 106,3
risk_pct 0,021 · risk_atr 2,1 · varredura 0,30 ATR · proeminência 2,15 ATR · rvol 2
```

Assunção numérica que precisei fazer para isso, e é a única do dia: **o brief pede, na mesma bateria,
`low = pivot_low − 0,3 ATR` (§10.1) e `low = 98` com `close = 100` e `ATR = 1` (§10.2)**. Os dois só
fecham juntos se `pivot_low = 98,30`, então foi esse o fundo que construí. Não é escolha estética: um
ATR exatamente 1 com uma barra de sinal cuja `close − low = 2` é **aritmeticamente impossível** se a
barra de sinal entrar na janela (a recursão de Wilder exigiria um ATR anterior de 12/13, que não tem
representação decimal finita); com o piso do patamar em 0,9 e o pivô em 98,30, tudo fecha.

### O teste central: o `k` de confirmação

`test_a_swing_low_two_bars_old_does_not_exist_yet` (e o gêmeo no `test_no_lookahead.py`) usa **as
mesmas velas** em dois cortes: no primeiro o fundo está em `t-2` e a resposta é `no_pivot`; duas
barras depois ele virou `t-4`, fica confirmado e é o pivô da decisão (`pivot_index_back == 4`, stop
97,9). **A diferença é o corte, não o dado** — que é a única forma de provar que a janela de
confirmação não vaza.

### `toll_cap_r` é derivado dos parâmetros, não cravado — divergência declarada

O §4.7 do brief escreve `toll_cap_r = Decimal("0.0020") / risk_pct`. Implementei
`(assumed_spread_bps + 2×slippage_bps + 2×fee_bps) / 10000 / risk_pct`, que com os defaults
congelados vale **exatamente** `0.0020 / risk_pct` (há teste afirmando as duas coisas). Motivo: a
regra de casa proíbe limiar cravado no caminho quente, e o numerador da identidade do pedágio **é** a
hipótese de custo do experimento — uma variante que mexa em `fee_bps` tem de mover o pedágio
publicado junto. Se a revisão preferir o literal, é uma linha.

---

## TESTES — saída real

```
$ uv run pytest packages/core/tests/unit/strategies/test_sweep_reclaim_v1.py -q
..............................................                           [100%]
46 passed in 5.22s

$ uv run pytest packages/core/tests/unit/strategies services/strategy-worker/tests/test_code_ref.py -q
........................................................................ [ 91%]
.............................................                            [100%]
549 passed in 102.28s (0:01:42)

$ uv run ruff check packages/core/hunter_core/strategies/sweep_reclaim_v1.py
All checks passed!

$ uv run pyright packages/core/hunter_core/strategies/sweep_reclaim_v1.py
0 errors, 0 warnings, 0 informations
```

`mypy` **não existe neste ambiente** (`error: Failed to spawn: mypy — program not found`); o
verificador de tipos do repositório é o **pyright estrito** (`CLAUDE.md`), e foi ele que rodou — nos
seis arquivos tocados, `0 errors` em todos os meus. (Há **um** erro de tipo pré-existente em
`packages/core/tests/unit/strategies/test_no_lookahead.py:397`, `_envelope_json` anotado `-> str`
sobre `canonical_json` que devolve `bytes`; ele está idêntico no `HEAD` e **não é meu** — não
corrigi para não colidir com a T3.34b.)

Duas corridas mais largas, para provar que a linha nova no `registry`/`constraints_table` não moveu
nada de ninguém:

```
$ uv run pytest packages/core/tests/unit -q -m unit
952 passed, 144 deselected in 148.97s (0:02:28)

$ uv run pytest services/strategy-worker/tests -q -m unit
236 passed, 186 deselected in 17.61s
```

### Os digests — a prova do §2

```
$ uv run python -c "from hunter_strategy_worker.code_ref import version_code_ref; ..."
momentum_v1              = hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c
volume_anomaly_v1        = hunter_core.strategies.volume_anomaly_v1@sha256:9b8c14ab3390646ac9adb26fbbb90e160a800f1c70f128d873a49ffd1dd19f22
breakout_v1              = hunter_core.strategies.breakout_v1@sha256:4c920b0cc412429c2c4a6a19ca389aca8a215a638f0ff750a8caf61b16264ff1
mean_reversion_v1        = hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f
session_orb_v1           = hunter_core.strategies.session_orb_v1@sha256:a4d514adeb0771d5ae23303878fb4fdac734721d6ac0140801c88d617e878bba
trendline_breakout_v1    = hunter_core.strategies.trendline_breakout_v1@sha256:7b83a1ff07946fa743d12c9d098f15b538c2e2b19f5269363203ee0671e19648
sweep_reclaim_v1         = hunter_core.strategies.sweep_reclaim_v1@sha256:a1150343f436494e9c007a1219c90c1467ecc9359d5ca0fa5e75658f0023556c
```

| versão | §2 do brief | antes de eu tocar | depois | veredito |
|---|---|---|---|---|
| `momentum_v1` | `ab2e0398…` | `ab2e0398…` | `ab2e0398…` | **não moveu** |
| `volume_anomaly_v1` | `9b8c14ab…` | `9b8c14ab…` | `9b8c14ab…` | **não moveu** |
| `breakout_v1` | `4c920b0c…` | `4c920b0c…` | `4c920b0c…` | **não moveu** |
| `mean_reversion_v1` | `a970c9d9…` | `a970c9d9…` | `a970c9d9…` | **não moveu** |
| `session_orb_v1` | `a4d514ad…` | `a4d514ad…` | `a4d514ad…` | **não moveu** |
| `trendline_breakout_v1` | `659087e1…` | **`7b83a1ff…`** | `7b83a1ff…` | **não moveu por mim** (CONCERN 1) |
| `sweep_reclaim_v1` | — | não existia | `a1150343…` | novo |

`params_hash` de `sweep_reclaim_v1` v1: `ba2b91be91f20db40508e5c6295aa3a7a8dd3686af9edabcc21400589f658f3f`
(fixado em teste).

O fecho, provado por `module_closure("sweep_reclaim_v1")`:
`aggregate, base, canonical, envelope, indicators, numeric, schema, sweep_reclaim_v1` — **nenhum
`tl_*`**, nenhuma outra estratégia, e `sweep_reclaim_v1` não aparece no fecho de nenhuma das seis
versões existentes (asserção explícita, uma por versão).

---

## FILES

| arquivo | o quê |
|---|---|
| `C:\dev\project-hunter\packages\core\hunter_core\strategies\sweep_reclaim_v1.py` | **novo**, 350 linhas — a versão congelada |
| `C:\dev\project-hunter\packages\core\tests\unit\strategies\test_sweep_reclaim_v1.py` | **novo** — 46 testes, os 13 grupos do §10 + paridade com `tl_pivots` + `params_hash` |
| `C:\dev\project-hunter\packages\core\tests\unit\strategies\test_no_lookahead.py` | **+109 linhas** (só acréscimo) — as três mutações, o caso do `k`, a vela em formação e o contexto decimal hostil |
| `C:\dev\project-hunter\packages\core\hunter_core\strategies\registry.py` | **+2 linhas** — import e roster |
| `C:\dev\project-hunter\packages\core\hunter_core\strategies\constraints_table.py` | **+18 linhas** — uma entrada `sweep_reclaim_v1` |
| `C:\dev\project-hunter\infra\scripts\seed_reference.py` | **+7 linhas** — a linha `sweep_reclaim` em `STRATEGIES` |
| `C:\dev\project-hunter\.claude\state\notes-T3.45b.md` | este arquivo |

**Não tocados, de propósito:** os sete irmãos do fecho (`aggregate`, `base`, `canonical`, `envelope`,
`indicators`, `numeric`, `schema`), `tl_*`, `schema.py`, `SHADOW_CONTEXT_MINUTES`, `apps/**`,
`services/**`, `obsidian/**`, `.env*`, `test_registry.py`, `test_constraints.py`.

---

## CONCERNS

1. **O digest da `trendline_breakout_v1` já era outro antes de eu começar, e por isso a sexta
   asserção do §2 não pode ser um dígito.** O brief cita `659087e1…`; a medição que fiz **antes de
   criar qualquer arquivo** já dava `7b83a1ff…` — a T3.34b está mexendo naquele fecho em paralelo,
   como o próprio brief previa. Cravar `7b83a1ff` no meu teste faria a minha bateria quebrar por
   trabalho **dela**. Troquei por uma prova estrutural, que é a propriedade que realmente importa:
   nenhum `tl_*` entra no meu fecho e `sweep_reclaim_v1` não entra no fecho de ninguém (inclusive o
   da `trendline_breakout_v1`). As cinco versões estáveis continuam com o dígito cravado.
   **Consequência operacional:** quem for ativar a `trendline_breakout_v1` tem de reler o digest dela
   na hora; o do brief está vencido.

2. **`infra/scripts/seed_reference.py` estoura o orçamento de 350 linhas, e o portão é CI.**
   `uv run python infra/scripts/check_file_size.py` acusa `error 369 > 350`. A conta:
   **349 no `HEAD`** → **362 com o trabalho em voo de outro agente** (T3.44c, não commitado) →
   **369 com a minha linha**. A minha linha é obrigatória pelo brief e ocupa 7 linhas porque a
   descrição congelada tem 95 caracteres e não cabe numa só com `line-length = 100`. **Não encolhi o
   arquivo**: as linhas que sobram não são minhas e mexer nelas colidiria com a T3.44c. O gate também
   acusa `apps/api/hunter_api/services/system_status.py` (349 no `HEAD` → 380 agora), que não é meu de
   forma nenhuma. Decisão de operador: alguém precisa encolher `seed_reference.py` antes do commit,
   ou o CI reprova.

3. **`toll_cap_r` derivado em vez de `Decimal("0.0020")` cravado.** Igual nos defaults, diferente em
   qualquer variante que mexa nos custos. Está no §4.7 do brief como literal; escolhi a forma
   derivada pela regra "nada de limiar cravado" e declarei aqui. Reversível em uma linha se a revisão
   preferir a letra do brief.

4. **A sensibilidade do `no_sweep`/`risk_below_floor` a `Decimal` versus `float8` continua valendo.**
   A pré-checagem mediu em `float8`; o motor decide em `Decimal` de 28 dígitos. Perto do piso
   (`risk_pct_min = 0,006`) e da profundidade (`0,25 ATR`) uma barra pode cair do outro lado. Em
   11 460 barras isso muda contagens em unidades, não em ordem de grandeza — mas **é o replay que
   mede**, não a SQL, e a diferença tem de ser nomeada se aparecer.

5. **`risk_above_cap` é guarda, não condição — e o meu teste dela usa uma barra absurda.** A
   pré-checagem viu **1** recusa em 31 dias × 4 mercados. O teste força `risk_atr = 4,35` com uma
   mínima em 94,9; nenhuma barra plausível desses mercados chega perto. Isso é declarado: o ramo está
   coberto, a *frequência* dele não é evidência de nada.

6. **A guarda de geometria é estruturalmente inalcançável, e o teste dela precisa de dois parâmetros
   absurdos.** `stop < low <= close` sempre, então só um `stop_buffer_atr` da ordem do preço fura o
   zero — e aí o teto de risco morde antes, então o teste também precisa afrouxar `risk_atr_max`. A
   guarda ficou (o brief manda, e a `breakout_v1` custou 14/14 por isso), mas o dia um deve reportar
   `REJECTED / geometry` **esperando zero**; qualquer número diferente de zero é achado, não ruído.

7. **Nada foi validado contra o Postgres.** Não rodei `packages/core/tests/integration/
   test_schema_seed_and_partitions.py` (testcontainers/Docker) — o §12 do brief não o pede e a árvore
   está compartilhada com outros agentes. O teste conta `len(reference.STRATEGIES)`, então ele
   **acompanha** a minha linha em vez de brigar com ela; ainda assim, a única prova que tenho de que
   a linha semeia é que ela tem a mesma forma das dez existentes e que a string bate caractere a
   caractere com o §3 do brief (verificado). **`seed.py` tem de rodar na VPS antes de qualquer
   ativação**, ou `activate_strategy_version.py` não acha a família.

8. **`is_monitored` e o universo continuam sendo os de hoje** (PIPELINE §6c), não os da janela de
   replay. Vale para qualquer coorte, então não enviesa comparações — mas nenhum número do dia um
   descreve o universo de agosto.

9. **A margem de K1 não mudou por eu ter escrito o módulo.** 57 eventos previstos (43 depois da
   barreira de re-arme), piso de morte 20, e a régua de maturidade (100 avaliáveis **e** 30 dias
   distintos) segue **inalcançável no replay por construção**. O dia um responde K1/K2/K4/K6 e a
   guarda de geometria; ele nasce `inconclusivo` e isso tem de ser dito na primeira linha da
   avaliação, não na última.

---

## O QUE EU FARIA A SEGUIR

1. **Revisão** (`code-reviewer`, `risk-engine-guardian`, Astra) com foco em três pontos: o
   `toll_cap_r` derivado (CONCERN 3), a prova estrutural do digest da trendline (CONCERN 1) e a
   asserção de que `_latest_pivot_low` e `tl_pivots` são a mesma regra.
2. **Encolher `seed_reference.py` abaixo de 350** — decisão de quem é dono das linhas em voo, não
   minha (CONCERN 2). Sem isso o CI reprova o commit.
3. **Só então** `seed.py` na VPS, `--dry-run` da ativação conferindo `a1150343…`, e o replay em duas
   fatias contíguas na **mesma** coorte, com a tabela de comparação do §12 do brief
   (57 / 17 dias / 29,8 % / 0 rejeições de geometria / 3,2 % indisponível, tudo aquecimento).
4. **E a pergunta que ultrapassa esta tarefa e continua aberta desde a T3.45:** com quatro mercados a
   coorte prospectiva leva ~2 meses para 100 desfechos. Alargar o universo é a alavanca real, e é
   decisão do Everton **antes** de ativar, não depois.

## Aceite do orquestrador (2026-09-08 ~20:15 BRT)
Revisão de código: APROVAR COM RESSALVAS. Aceito por escrito o `toll_cap_r` derivado de `(spread + 2×slippage + 2×fee)/10000 / risk_pct` em vez do literal `0,0020` — idêntico nos defaults (teste `test_the_published_toll_is_the_identity_of_kb_0076`), campo informativo (não decide nada) e mais fiel numa variante que mude custos. O EXP-0017 não muda. Commit aguarda o encolhimento de `infra/scripts/seed_reference.py` (369 > 350; 13 linhas são da T3.44c em voo).
