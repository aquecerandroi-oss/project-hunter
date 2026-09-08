# notes-T3.33c — `session_orb_v1`: rompimento da faixa de abertura de sessão (EXP-0010)

**Data:** 2026-09-08 · **Owner:** quant-engineer · **Base:** `main @ 6e9eaa2`
**Brief:** `.claude/state/brief-T3.33c-session_orb_v1.md` · **Contrato congelado:** `EXP-0010`
**Nada foi commitado. Nada foi ativado. Nada chega à carteira.**

## STATUS

**DONE_WITH_CONCERNS.** O módulo, o registro, a regra `bounded` em `constraints.py`, a linha nova
no catálogo de referência e os testes estão entregues e verdes (45 testes próprios + 14 de
não-antecipação e de contexto decimal + 13 de faixa; 360 na pasta inteira). Os digests das versões
vivas **não se moveram**. As duas concerns que mudam a leitura estão em CONCERNS: (1) o portão
C1–C8 dá **REVISE** por C8 (sem invalidação — que aqui *é* a hipótese) e por C2 (penalidade por
limiar decimal); (2) `constraints.py` ficou em **exatamente 350 linhas**, no teto do
`check_file_size.py`, e a quinta entrada (a `derivatives_v1`, em voo em paralelo) não cabe sem
partir a tabela em módulo próprio.

## FILES

| arquivo | o quê |
|---|---|
| `C:\dev\project-hunter\packages\core\hunter_core\strategies\session_orb_v1.py` | **novo** — a versão congelada, 350 linhas exatas |
| `C:\dev\project-hunter\packages\core\hunter_core\strategies\registry.py` | +2 linhas (import + `SESSION_ORB_V1` no roster) |
| `C:\dev\project-hunter\packages\core\hunter_core\strategies\constraints.py` | +regra `bounded` (campo, docstring, laço em `_table_rules`) e +entrada `session_orb_v1` |
| `C:\dev\project-hunter\infra\scripts\seed_reference.py` | +1 linha em `STRATEGIES` (`session_orb`, família nova) |
| `C:\dev\project-hunter\packages\core\tests\unit\strategies\test_session_orb_v1.py` | **novo** — 45 testes |
| `C:\dev\project-hunter\packages\core\tests\unit\strategies\test_no_lookahead.py` | +3 testes (3 poluições, mutação da vela em formação, contexto decimal hostil) |
| `C:\dev\project-hunter\packages\core\tests\unit\strategies\test_constraints.py` | +13 casos da faixa + a classe da regra `bounded` |
| `C:\dev\project-hunter\packages\core\tests\unit\strategies\test_registry.py` | +`SESSION_ORB_V1` no roster/contexto e `params_hash` fixado; a sonda de chave inexistente passou de `session_orb_v1` (agora existe) para `order_flow_v1` |
| `C:\dev\project-hunter\.claude\state\notes-T3.33c.md` | este arquivo |

**Não tocados:** `.env*`, `apps/**`, `services/**`, `obsidian/**`, `derivatives_v1.py` e os sete
módulos do fecho (`aggregate`, `base`, `canonical`, `envelope`, `indicators`, `numeric`, `schema`).
`registry.py`, `constraints.py` e `seed_reference.py` receberam **só** as linhas desta versão, com
releitura do arquivo imediatamente antes de cada edição (outro agente escreve `derivatives_v1`).

## IDENTIDADE CONGELADA

```
strategies.key      session_orb          (linha NOVA no catálogo de referência)
registry key        session_orb_v1  v1   timeframe 15m   LONG   research_only
params_hash         cdb9516b293276095f4a8c2210d60ade0a4448cac46cce827f58bc3f8908d5e0
code_ref            hunter_core.strategies.session_orb_v1@sha256:aae896ee58bea0382c6e5e27c51a8a133932c143f20f84738f66ef90d7e951e9
fecho               aggregate, base, canonical, envelope, indicators, numeric, schema, session_orb_v1
```

O `code_ref` acima vale para a árvore de agora; ele **só congela na ativação** e nenhuma ativação
foi feita.

## PORTÃO C1–C8 APLICADO AO EXP-0010 (antes do módulo)

Critérios: `.claude/skills/edge-strategy-reviewer/references/review_criteria.md`. Condições contadas
como "entrada": posição na sessão, janela da sessão, `close > range_high`, `rvol >= 1,3`,
`ATR% >= 0,006`, `ATR% <= 0,05`, `range_risk >= 1,0`, `range_risk <= 2,5` = **8**; `trend_filter` = 0.

| # | critério | peso | severidade | nota | por quê |
|---|---|---|---|---|---|
| C1 | plausibilidade do edge | 20 | pass | 80 | mecanismo causal declarado (participação chega em blocos horários; a primeira hora fixa a faixa) e refutável |
| C2 | risco de sobreajuste | 20 | pass (contagem) | **30** | 8 condições ≤ 10 → 80, **−50** de penalidade: cinco limiares com casa decimal (1,3 · 0,006 · 0,05 · 1,0 · 2,5) |
| C3 | amostra | 15 | pass | 80 | `252 × 0,8⁸ = 42,3` oportunidades/ano pela fórmula do portão (ver ressalva abaixo) |
| C4 | dependência de regime | 10 | **warn** | 40 | o plano de validação (notes-T3.33 §5.1) estratifica por **sessão**, não por regime do BTC |
| C5 | calibração da saída | 10 | pass | 80 | alvo = 2 R ≥ 1,5; stop máximo possível = `atr_pct_max × range_risk_atr_max` = **12,5 %** < 15 % (tem teste) |
| C6 | concentração de risco | 10 | pass | 80 | não há sizing: `research_only`, um acompanhamento por (versão, mercado, coorte) |
| C7 | realismo de execução | 10 | pass | 80 | há filtro de volume (`rvol >= 1,3`); `export_ready_v1` não se aplica |
| C8 | qualidade da invalidação | 5 | **fail** | 10 | `invalidations = ()` |

**Score ponderado = 62,5 → veredito REVISE** (C1/C2 não falham, então não há REJECT imediato; há um
`fail`, então não há PASS).

**Divergências que eu declaro em vez de consertar:**

1. **C8 é a hipótese, não um esquecimento.** A mínima da faixa *é* o nível estrutural e já é o
   **stop**; uma `close_below` separada ficaria acima do stop (um segundo stop que ninguém declarou)
   ou abaixo dele (código morto). É a mesma forma da `volume_anomaly_v1`, já revisada, e a decisão
   está amarrada à [[KB-0006]]: **não** afirmo que remover invalidação melhora nada.
2. **C2 pune declarar número.** Os cinco "limiares decimais" são exatamente os parâmetros
   congelados que tornam a versão auditável; escondê-los em constantes redondas seria pior. Fica
   registrado que o portão não distingue "limiar ajustado" de "limiar declarado".
3. **C3 mede em dias de pregão.** A fórmula supõe uma barra por dia; aqui são 96 barras de 15 min
   por dia por mercado, em quatro mercados. A frequência de planejamento honesta é a do brief:
   0,3–1 entrada/mercado/dia — e o K1/K2 de `notes-T3.33.md` §5.1 (< 20 decisões mata; > 1500 mata)
   é o teste de verdade, não este 42,3.
4. **C4 fica em warn de propósito.** Há decomposição obrigatória **por sessão** e a regra de morte
   dos 70 % (uma sessão sozinha carregando mais de 70 % das decisões reenuncia a hipótese), mas
   **não** há estratificação por regime do BTC. Não inventei uma para tirar nota.

## O PEDÁGIO DESTA GEOMETRIA (confirmação pedida no brief, contra notes-T3.32)

A T3.32 mostrou que `custo_R × risco%` = **0,0020 constante** nas dez populações — aritmética, não
estatística: 20 bps de ida e volta divididos pela distância percentual ao stop. Aplicado aos pisos
congelados desta versão (reproduzido em `Decimal`, `prec = 28`, e travado em teste):

```
ida e volta            = 2 + 2×5 + 2×4 bps                = 0,002 do preço
risco% no pior caso    = range_risk_atr_min × atr_pct_min = 1,0 × 0,006 = 0,006
pedágio máximo         = 0,002 / 0,006                    = 0,3333 R
risco% no melhor caso  = 2,5 × 0,05                       = 0,125
pedágio mínimo         = 0,002 / 0,125                    = 0,0160 R
```

**O teto de custo desta geometria é 1/3 de R**, contra os **0,6152 R** medidos na coorte de replay
da `volume_anomaly v2` e os **0,1506 R** da `momentum v1` prospectiva (T3.32, tabela da identidade
do custo). É esse piso — `range_risk_atr_min = 1,0` com `atr_pct_min = 0,006` — que impede a versão
de repetir a doença da `volume_anomaly`: lá o risco inicial mediano era 0,41 % do preço e o pedágio
comia mais de meio R antes de o mercado abrir a boca.

Reproduzi também a tabela de geometria do brief §6, e ela fecha nos quatro dígitos:

| risco da faixa | ATR% | R_net no alvo | R_net no stop | equilíbrio |
|---:|---:|---:|---:|---:|
| 1,0 ATR (piso) | 0,006 | 1,5133 | −1,2112 | **0,4446** |
| 1,5 ATR | 0,010 | 1,7929 | −1,0888 | 0,3778 |
| 2,5 ATR (teto) | 0,050 | 1,9725 | −1,0102 | 0,3387 |

O alvo em R constante mantém o equilíbrio entre **33,9 % e 44,5 %** em toda a faixa permitida — que
é a razão de o alvo não ser em ATR.

## TESTS (saída real)

```
$ uv run pytest packages/core/tests/unit/strategies/test_session_orb_v1.py -q
.............................................                            [100%]
45 passed in 2.04s

$ uv run pytest packages/core/tests/unit/strategies -q -k "strategies or constraints or code_ref"
........................................................................ [ 80%]
........................................................................ [100%]
360 passed in 10.21s

$ uv run pytest services/strategy-worker/tests/test_code_ref.py services/strategy-worker/tests/test_constraints_outside_freeze.py -q
................................                                         [100%]
32 passed in 2.43s

$ uv run pytest packages/core -q -m "not integration"
935 passed, 505 deselected in 36.74s

$ uv run pytest services/strategy-worker -q -m "not integration"
220 passed, 152 deselected in 5.30s

$ uv run pytest infra -q -m "not integration"
109 passed, 9 deselected in 15.01s

$ uv run pytest packages/indicators apps/api services/scanner-worker -q -m "not integration"
1522 passed, 412 deselected, 1 xfailed, 1 warning in 163.10s

$ uv run ruff check packages/core/hunter_core/strategies/session_orb_v1.py
All checks passed!

$ uv run ruff format --diff packages/core/hunter_core/strategies/session_orb_v1.py
1 file already formatted

$ uv run mypy packages/core/hunter_core/strategies/session_orb_v1.py
error: Failed to spawn: `mypy`
  Caused by: program not found
$ uv run pyright packages/core/hunter_core/strategies/session_orb_v1.py    # o type-checker do repo
0 errors, 0 warnings, 0 informations

$ uv run python infra/scripts/check_file_size.py
scanned 547 files; 0 over budget, 0 grandfathered
```

**Isolamento do digest (o teste do brief §2, verde):**

```
momentum_v1        hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c
volume_anomaly_v1  hunter_core.strategies.volume_anomaly_v1@sha256:9b8c14ab3390646ac9adb26fbbb90e160a800f1c70f128d873a49ffd1dd19f22
```

— byte a byte os do brief, com o módulo novo dentro da árvore.

**Prova de mutação (o teste que mais importa aqui).** Troquei, na árvore, a fatia da faixa de
abertura por "as últimas `range_bars` barras antes do rompimento" e rodei a suíte; o teste de
ancoragem pegou e o arquivo foi restaurado em seguida:

```
$ sed -i 's|opening = bars[-bars_since_open : -bars_since_open + range_bars]|opening = bars[-range_bars - 1 : -1]  # MUTANT|' ...
>       assert values["range_low"] == RANGE_LOW
E       AssertionError: assert Decimal('99.5') == Decimal('99.75')
1 failed, 44 passed in 1.54s
```

A primeira versão da fixture **não** teria pego isso: com 96 barras idênticas, "as quatro barras da
sessão" e "as últimas quatro barras" são as mesmas quatro. A fixture final põe a faixa de abertura
em `100,75 / 99,75` (TR = 1, para não mexer no ATR) contra `100,5 / 99,5` das vizinhas, e o teste de
ancoragem avalia num corte **oito** barras depois da abertura, onde os dois conjuntos são diferentes.

## SÉRIE SINTÉTICA E NÚMEROS ESPERADOS (escritos à mão, não lidos da implementação)

Corte em **2026-01-02 14:15Z**, cinco barras depois da abertura declarada `us` (13:00Z); 97 barras
de 15 min (a janela inteira de `rvol_window + 1`), todas com `TR = 1`, então o ATR é exatamente 1 —
seed inclusive — e a barra do rompimento também tem `TR = 1`.

```
faixa de abertura   range_high 100,75   range_low 99,75      (as 4 barras de 13:00-14:00)
rompimento          close 101 > 100,75  volume 150 / mediana 100 = 1,5x
ATR 1 · ATR% 1/101 = 0,990099…  ·  range_risk_atr = 1,25 ∈ [1; 2,5]
stop 99,75 · risco 1,25 · alvo1 103,5 (2 R) · alvo2 106 (4 R) · invalidações ()  · horizonte 14400 s
```

Ramos cobertos, um teste cada: `inside_opening_range` (3 e 4 barras — o limite é inclusivo),
`outside_session_window` (21 barras), `no_range_break` (inclusive o fechamento **exatamente** na
máxima), `rvol_low` (inclusive o piso exato 1,3), `atr_out_of_range` (piso e teto), `ineligible`,
`warmup`, `gap`, `atr_warmup` (janela longa demais e aquecimento do indicador), `degenerate_range`,
`rvol_unavailable`, `range_geometry` (faixa mais estreita que 1 ATR **e** mais larga que 2,5 ATR —
esta com razão exata **7,625**) e `geometry` (`target_r = 0`).

Tabela de fronteira de sessão, parametrizada sobre `_session_open`: 00:00 → asia 00:00 (o corte da
meia-noite pertence ao dia **novo**, com zero barras desde a abertura), 06:45 → asia, 07:00 → europe,
12:45 → europe, 13:00 → us, 23:45 → us.

## CONCERNS

1. **`constraints.py` está em exatamente 350 linhas — no teto do gate.** A entrada da
   `derivatives_v1`, que outro agente escreve agora, **não cabe**: `check_file_size.py` vai falhar
   para quem entrar depois de mim. O conserto certo é partir `CONSTRAINTS` num módulo de tabela
   (`constraints_table.py`) e deixar `constraints.py` só com as regras — refatoração fora deste
   brief, que eu **não** fiz para não mexer no arquivo que o outro agente está editando. Quem
   fechar as duas entregas precisa decidir isso antes do commit.
2. **Compactei duas linhas do meu próprio bloco em `constraints.py`** para caber no gate: o
   conjunto `positive` está como `frozenset("a b c …".split())` em vez do literal com um nome por
   linha, e as três horas viram uma constante `_SESSION_HOURS` reaproveitada por `non_negative`,
   `bounded` e `ordered`. **Os nomes e as faixas são exatamente os do brief §9** — só a escrita
   mudou. Se a revisão preferir o literal, ele volta assim que a tabela sair deste arquivo.
3. **Um ramo a mais do que o brief enumera: `NOT_TRIGGERED / "no_session_open"`.** Com os padrões
   congelados ele é **inalcançável** (a abertura da asia às 00:00 cobre o dia inteiro), mas
   `_session_open` é total por assinatura (`| None`) e um conjunto de parâmetros cuja primeira
   sessão abre mais tarde deixaria as primeiras horas do dia descobertas. Preferi um estado
   declarado e testado a um `assert` implícito. É `NOT_TRIGGERED` e não `UNAVAILABLE` porque "o dia
   ainda não tem sessão" é um fato observável do relógio, não um dado que faltou.
4. **`mypy` não existe neste repositório** (o brief §13 pede). O type-checker do gate é `pyright`
   em modo `strict`, e é o que rodei: 0 erros nos meus arquivos.
5. **Um erro de `pyright` pré-existente continua lá:** em `test_no_lookahead.py`, o auxiliar
   `_envelope_json(...) -> str` devolve os `bytes` de `canonical_json`. É da T3.33a, não meu, e
   **não** o corrigi para manter a pegada mínima num arquivo que o outro agente também edita; a
   comparação que ele faz é válida nos dois tipos. Fica registrado como uma linha de conserto.
6. **A sonda de "chave não registrada" de `test_registry.py` usava literalmente `session_orb_v1`.**
   Agora que a chave existe, troquei por `order_flow_v1` (família semeada, sem módulo neste build).
   Se alguém implementar `order_flow` depois, esse teste precisa de outra chave — o padrão é frágil
   e vai reaparecer.
7. **O relógio na regra é uma escolha de calendário, e ela pode ser o efeito inteiro.** Se uma única
   sessão carregar mais de 70 % das decisões, a hipótese não é "sessões", é "uma hora específica", e
   o EXP-0010 obriga a reenunciá-la **antes** de qualquer avaliação seguinte. A decomposição por
   sessão é obrigatória já na primeira leitura.
8. **O horizonte de 4 h transborda de sessão.** É custo declarado, não suposto: a primeira avaliação
   tem de publicar a fração de desfechos cuja saída cai numa sessão posterior.
9. **`session_window_bars = 20` deixa buracos declarados no dia:** a regra é silenciosa entre 05:00
   e 07:00, entre 12:00 e 13:00 e depois das 18:00 UTC. Isso é o preço de não deixar as três
   sessões se sobreporem, e é o que a faixa `bounded (1..24)` protege.
10. **Nada disso é evidência.** Não rodei replay: a validação de dia um (31 dias, 4 mercados, coorte
    `replay:<uuid>`) depende de deploy + seed + ativação pelo operador, nesta ordem — a família é
    nova, então **`infra/scripts/seed.py` roda antes** de `activate_strategy_version.py`, ou a
    ativação não acha a linha. Critérios de morte K1–K5 em `notes-T3.33.md` §5.1, mais a regra dos
    70 % acima.

## PRÓXIMO PASSO (só o operador, na VPS)

```bash
docker exec -i hunter-api-1 python - < infra/scripts/seed.py          # a família é nova: primeiro
docker exec -i hunter-api-1 python - session_orb v1 --dry-run \
  --changelog 'T3.33c: session opening-range breakout, research cohort (research_only, no wallet)' \
  < infra/scripts/activate_strategy_version.py
```
