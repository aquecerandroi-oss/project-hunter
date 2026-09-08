# notes-T3.33a — `breakout_v1`: rompimento após compressão de volatilidade (EXP-0008)

**Data:** 2026-09-08 · **Owner:** quant-engineer · **Base:** `main @ 9f1f624` (árvore compartilhada,
com T3.33b/c/d em voo no mesmo checkout) · **Brief:** `.claude/state/brief-T3.33a-breakout_v1.md`
**Nada foi commitado. Nada foi ativado. Nada chegou à carteira.**

## STATUS

**DONE_WITH_CONCERNS.** O módulo `breakout_v1` está escrito, registrado, com faixas declaradas,
36 testes próprios e 14 testes de não-antecipação acrescentados à suíte compartilhada — tudo verde,
com os dois digests vivos (`momentum_v1`, `volume_anomaly_v1`) **byte a byte iguais** aos de
produção. O portão C1–C8 foi aplicado ao EXP-0008 **antes** de o módulo existir e o veredito é
**REVISE** (`confidence_score = 66,0`), com três revisões que são obrigações de relato na primeira
avaliação, não mudanças no contrato congelado — o veredito completo está gravado no próprio EXP.

As duas concerns que valem o rótulo: (1) **o teto de custo declarado pela Astra (20 bps ≤ 25 % da
distância do stop) não vale no piso congelado** — no `atr_pct_min = 0,005` o pedágio é **0,2921 R**,
29,2 % do stop, e só cai a 25 % a partir de `atr_pct = 0,0059238`; (2) **o replay de dia um não foi
executado** e não podia ser: a versão não está ativada (o brief e a minha tarefa proíbem ativar) e o
módulo não está commitado nem implantado na VPS. O RECIBO abaixo diz exatamente o que foi lido lá e
o que falta.

## FILES

| arquivo | o quê |
|---|---|
| `C:\dev\project-hunter\packages\core\hunter_core\strategies\breakout_v1.py` | **novo** — a versão congelada, 350 linhas (orçamento 350) |
| `C:\dev\project-hunter\packages\core\hunter_core\strategies\registry.py` | +2 linhas: import e `DEFAULT_REGISTRY` |
| `C:\dev\project-hunter\packages\core\hunter_core\strategies\constraints.py` | +1 entrada `breakout_v1` (fora do fecho do `code_ref`, por construção) |
| `C:\dev\project-hunter\infra\scripts\seed_reference.py` | `description` da linha `breakout` passa a dizer o que o código faz |
| `C:\dev\project-hunter\packages\core\tests\unit\strategies\test_breakout_v1.py` | **novo** — 36 testes, valores exatos escritos à mão |
| `C:\dev\project-hunter\packages\core\tests\unit\strategies\test_no_lookahead.py` | +4 testes (14 casos) de não-antecipação do `breakout_v1` na suíte compartilhada |
| `C:\dev\project-hunter\packages\core\tests\unit\strategies\test_registry.py` | roster, `params_hash` congelado, contexto por estratégia |
| `C:\dev\project-hunter\packages\core\tests\unit\strategies\test_constraints.py` | +14 casos de faixa da `breakout_v1` |
| `C:\dev\project-hunter\services\strategy-worker\tests\test_code_ref.py` | +2 testes: isolamento do digest das versões vivas |
| `C:\dev\project-hunter\services\strategy-worker\tests\test_constraints_outside_freeze.py` | `FROZEN_DIGESTS` ganha `breakout_v1` |
| `C:\dev\project-hunter\.claude\state\exp-drafts\EXP-0008-breakout-compressao-de-volatilidade.md` | veredito C1–C8 + a conferência do teto de custo (seções **acrescentadas**; hipótese e protocolo intactos) |
| `C:\dev\project-hunter\.claude\state\notes-T3.33a.md` | este arquivo |

**Não tocados**, confirmado por `git status --porcelain`: `.env*`, `apps/**`,
`services/market-worker/**`, `services/execution-worker/**`, `obsidian/**` e os nove módulos do
fecho congelado (`base`, `momentum_v1`, `volume_anomaly_v1`, `schema`, `envelope`, `indicators`,
`numeric`, `canonical`, `aggregate`).

## Decisões de projeto que valem registro

- **O estimador tem nome:** `median_true_range_v1`, gravado no envelope como feature própria
  (`squeeze_estimator`). "Compressão" sem estimador declarado seria a armadilha que a KB-0053 nomeia.
- **As duas janelas terminam em `t−1`.** `prior = bars[:-1]`; a barra do rompimento não entra em
  nenhuma das duas medianas. Medir a contração **com** a expansão dentro dela inverteria a seleção.
- **`_true_ranges` é escrito dentro do módulo**, e não importado de `indicators.py`, porque uma linha
  nova lá re-congelaria `momentum_v1` e `volume_anomaly_v1`. A duplicação é deliberada e está dita no
  docstring. `median`, `relative_volume`, `wilder_atr` e `atr_percent` são **importados** — importar é
  permitido, editar não.
- **A ordem dos motivos é contrato.** Disponibilidade é sempre `UNAVAILABLE`, e as duas guardas de
  geometria são `REJECTED`, nunca `NOT_TRIGGERED`: um mercado não pode re-armar numa barra cuja
  condição nunca foi observada falsa.
- **A guarda `stop < base_low < referência` é o desenho inteiro.** A metade de cima
  (`base_low < referência`) é estruturalmente inalcançável com a regra congelada — `base_low` é a
  mínima de barras cujas máximas são menores que o fechamento do rompimento —, e continua escrita
  para que uma mudança futura de parâmetro não transforme a invalidação num stop disfarçado sem que
  alguém veja.

## TESTS — saída real

```
$ uv run pytest packages/core/tests/unit/strategies/test_breakout_v1.py -q
....................................                                     [100%]
36 passed in 1.43s

$ uv run pytest packages/core/tests/unit/strategies -q
........................................................................ [ 78%]
............................................................             [100%]
276 passed in 10.93s

$ uv run pytest services/strategy-worker/tests/test_code_ref.py services/strategy-worker/tests/test_constraints_outside_freeze.py -q
................................                                         [100%]
32 passed in 4.30s

$ uv run pytest packages/core/tests/unit -q -m unit
706 passed, 144 deselected in 65.63s (0:01:05)

$ uv run pytest services/strategy-worker/tests -q -m unit
220 passed, 152 deselected in 28.21s

$ uv run pytest services/strategy-worker/tests/test_activation.py -q      # 1 arquivo com testcontainers
..............                                                           [100%]
14 passed in 41.36s

$ uv run ruff check packages/core/hunter_core/strategies/breakout_v1.py
All checks passed!

$ uv run ruff format --check <os 7 arquivos de código tocados>
7 files already formatted

$ uv run pyright packages/core/hunter_core/strategies/breakout_v1.py
0 errors, 0 warnings, 0 informations
```

`uv run mypy` **não existe neste repositório** (não está em `[dependency-groups] dev`; o gate de tipos
é `pyright`). `uv run mypy --version` → `error: Failed to spawn: mypy — program not found`. Rodei
`pyright` no lugar e estou declarando a substituição.

### O isolamento do digest, que é o teste que o brief chama de obrigatório

```
$ uv run python -c "from hunter_strategy_worker.code_ref import version_code_ref; ..."
momentum_v1       hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c
volume_anomaly_v1 hunter_core.strategies.volume_anomaly_v1@sha256:9b8c14ab3390646ac9adb26fbbb90e160a800f1c70f128d873a49ffd1dd19f22
breakout_v1       hunter_core.strategies.breakout_v1@sha256:4c920b0cc412429c2c4a6a19ca389aca8a215a638f0ff750a8caf61b16264ff1
```

Os dois primeiros são **idênticos** aos do brief §2 e aos que as linhas ativadas na VPS carregam
(inclusive a linha `paper`, `momentum v3`). O terceiro é o digest que a ativação vai congelar — está
fixado em `test_constraints_outside_freeze.py::FROZEN_DIGESTS` e em
`test_code_ref.py::test_a_new_strategy_module_does_not_move_the_live_versions`.

### A série sintética, e por que os números são exatos

96 barras anteriores + a barra do rompimento, todas fechando em 100:

| bloco | barras | true range | por quê |
|---|---:|---|---|
| base larga | 88 | `2,475789056 = 1 + 14⁸/10⁹` | faz a recursão de Wilder **terminar** em decimal |
| compressão | 8 | `1` | a menor corrida que move `mtr_short` sem mover `mtr_long` |
| rompimento | 1 | `1,675730721 = 1,815730721 − 14 × 0,01` | o último passo de suavização cai em número redondo |

Daí: `ATR` após a compressão `= 1 + 13⁸/10⁹ = 1,815730721`; `ATR` final **= 1,805730721** exato.
`mtr_short = 1`, `mtr_long = 2,475789056`, `squeeze_ratio = 0,40391…`, `max das 20 máximas
anteriores = 101,237894528`, `referência = 101,675730721`, `stop = 99,41856731975`,
`alvo1 = 106,1900575235`, `alvo2 = 108,898653605`, `base_low = 99,5`, `RVOL = 2`,
`ATR% = 1,7760 %`. Todos escritos à mão no teste, nenhum lido da implementação.

**Cobertura de ramos, um por linha:** `not_compressed`, `no_breakout`, `rvol_low`,
`atr_out_of_range` (nos dois lados da faixa), `ineligible`; `warmup`, `gap`, `atr_warmup` (janela
curta **e** ATR em aquecimento), `squeeze_baseline_unavailable`, `rvol_unavailable`; `geometry`
(alvo na referência e stop abaixo de zero) e `geometry_invalidation`. Mais: a fronteira inclusiva de
`squeeze_max`, a prova de que o nível é a **máxima** e não o fechamento (um fechamento de 100,5
dispararia a regra do `momentum_v1` e não dispara esta), pureza, ausência de relógio/IO por leitura
do próprio fonte e o orçamento de janela (1455 min ≤ 1560).

**Não-antecipação (4 testes, 14 casos):** o mesmo `Decision` e o **mesmo JSON canônico do envelope**
com (a) vela não-final dentro da janela, (b) vela final fechando depois do corte, (c) um futuro
diferente, (d) as três juntas; a vela em formação mutada em três formas (absurda, plana, plausível);
`bootstrap == contínuo` barra a barra; e invariância a `prec`/`rounding` do contexto decimal
ambiente (9 combinações). O teste de vazamento deliberado
(`test_a_cheating_strategy_is_caught_by_the_context`) já existia e continua passando.

## RECIBO do replay — **não executado**, e por quê

Leitura **somente-leitura** do catálogo na VPS (`hunter-strategy-worker-1`, transação
`repeatable read read only`, 2026-09-08). Nenhuma escrita, nenhuma coorte criada, nenhum container
tocado:

```
$ ssh hunter-vps 'docker exec -i hunter-strategy-worker-1 python -' < vps_readonly.py
---- strategies ----
('breakout', 'Breakout', 'trend', 'Range break confirmed by volume and order flow.')
...
---- strategy_versions ----
('breakout', 'v1', 'draft', 'research_only', 'hunter_indicators.strategies.breakout_v1')
('momentum', 'v2', 'active', 'research_only', 'hunter_core.strategies.momentum_v1@sha256:ab2e')
('momentum', 'v3', 'active', 'paper',         'hunter_core.strategies.momentum_v1@sha256:ab2e')
('momentum', 'v4', 'active', 'research_only', 'hunter_core.strategies.momentum_v1@sha256:ab2e')
('volume_anomaly', 'v2', 'active', 'research_only', 'hunter_core.strategies.volume_anomaly_v1@sha25')
...
```

Três fatos que saem daí:

1. a linha `breakout / v1` **já existe**, `status = draft`, `purpose = research_only`,
   `default_parameters` vazio e `code_ref` com o **placeholder** `hunter_indicators.strategies.breakout_v1`
   (módulo que não existe — é o texto que `seed.py` escreve). É exatamente a linha que o caminho de
   pesquisa de `activate_strategy_version.py` sabe ativar: `carries_own_content` é falso (purpose
   `research_only`, changelog nulo) e `refuse_rewriting_own_content` retorna cedo porque não há
   parâmetros próprios. **A ativação vai funcionar; ela não foi feita.**
2. a `description` na VPS ainda é a antiga. `seed.py` faz `on_conflict_do_update` da descrição, então
   ela só muda quando o operador rodar o seed depois do deploy;
3. **o replay é impossível hoje**, e não por escolha: `replay.run --version breakout:v1` resolve a
   versão pela tabela (`status = active`) e executa o **código da imagem**, que não contém
   `breakout_v1.py` — nada foi commitado nem implantado. Rodar um replay agora produziria
   `no active version` ou, pior, uma coorte contra código que não é este.

**Tabela de resultados do replay: vazia, e assim declarada.** `decisões = —`, `sinais = —`,
`desfechos = —`, `unavailable% = —`, `geometry_invalidation% = —`, `expectancy = —`. Os critérios de
morte K1–K5 (`notes-T3.33` §5.1) e o específico desta versão (`geometry_invalidation` acima de 20 %
das barras que disparariam) estão **congelados antes** da corrida, no EXP-0008.

### Sequência para o operador — nesta ordem, e só ela

```bash
# 0. commit por pathspec exato + deploy (fora do meu escopo; nada aqui foi commitado)

# 1. atualizar a descrição do catálogo (idempotente; não toca linha ativada)
ssh hunter-vps 'docker exec -i hunter-api-1 python -' < infra/scripts/seed.py

# 2. ativação — SEMPRE o dry-run primeiro; congela code_ref, schema e parâmetros, e é irreversível
ssh hunter-vps 'docker exec -i hunter-api-1 python - breakout v1 --dry-run \
  --changelog "T3.33a: volatility-compression breakout, research cohort (research_only, no wallet)"' \
  < infra/scripts/activate_strategy_version.py
ssh hunter-vps 'docker exec -i hunter-api-1 python - breakout v1 \
  --changelog "T3.33a: volatility-compression breakout, research cohort (research_only, no wallet)"' \
  < infra/scripts/activate_strategy_version.py
# o dry-run tem de citar code_ref hunter_core.strategies.breakout_v1@sha256:4c920b0c…64ff1
# se citar outro digest, o deploy não é este código — pare aí.

# 3. replay de dia um, DUAS fatias contíguas com a MESMA coorte (uuid gerado uma vez)
COHORT=replay:$(uuidgen)
ssh hunter-vps "docker exec hunter-strategy-worker-1 python -m hunter_strategy_worker.replay.run \
  --version breakout:v1 --from 2026-08-08 --to 2026-08-23 \
  --markets ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT --workers 3 \
  --cohort \$COHORT --ledger /tmp/replay-breakout-v1-a.jsonl"
ssh hunter-vps "docker exec hunter-strategy-worker-1 python -m hunter_strategy_worker.replay.run \
  --version breakout:v1 --from 2026-08-23 --to 2026-09-08 \
  --markets ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT --workers 3 \
  --cohort \$COHORT --ledger /tmp/replay-breakout-v1-b.jsonl"
```

Referência de custo (EXP-0006, mesma forma): ~11 904 barras a ~65 barras/s com 3 workers ≈ **3 min
por fatia** — dentro da janela de 4 min. O recibo do livro-razão (barras, segundos, barras/s,
contagem por estado, sinais, desfechos, erros) vai para o EXP-0008, junto com a decomposição
obrigatória por `squeeze_ratio` e os cortes por regime, mercado e decil de ATR% que o portão C4
exige.

## CONCERNS

1. **O teto de custo de 25 % não vale no piso congelado.** `custo_R = 0,0020 / (risco/preço)`
   (identidade da T3.32, desvio ≤ 1,9×10⁻⁵) com `risco/preço = (a + 1,25·ATR%)/(1+a)` dá **0,2921 R**
   em `atr_pct = 0,005` — 29,2 % da distância do stop, contra o teto de 25 % que a Astra propôs. O
   teto só passa a valer em `atr_pct ≥ 0,0059238`. **Não mudei o parâmetro** (congelado no brief;
   mudá-lo é versão nova) e não o considero um bloqueio: a assimetria 1,25/2,5 já derruba o
   equilíbrio de 72,2 % (`momentum_v1` no piso dele) para 44,0 %, que é o que a versão existe para
   testar. A obrigação que fica é publicar, na primeira avaliação, quantas decisões caem em
   `0,0050 ≤ ATR% < 0,0059` e qual a expectancy delas.
2. **O portão C1–C8 devolveu REVISE (66,0), não PASS.** As três revisões (C2 limiares decimais não
   medidos, C4 sem corte por regime no plano, C8 uma invalidação só) estão respondidas no EXP como
   obrigações de relato; nenhuma delas muda o contrato congelado, e a de C8 é uma **divergência
   declarada** contra o critério, apoiada na KB-0006 (política de saída só se compara pareada).
   Implementei mesmo assim porque o brief congela o contrato e a alternativa — mexer em parâmetro
   para melhorar a nota — seria ajustar o experimento ao seu próprio revisor.
3. **Replay não executado.** Descrito no RECIBO. Sem ele, tudo nesta entrega é contrato e teste
   sintético: **nenhuma evidência de mercado foi produzida**, e a frequência de disparo é
   desconhecida (K1/K2 continuam abertos).
4. **`atr_warmup` tem dois significados.** `f"atr_{reason}"` com `reason = "warmup"` e o aquecimento
   do próprio indicador produzem a **mesma** string. Está testado nas duas formas e documentado, mas
   um leitor do log de avaliação não distingue "a janela não alcança" de "Wilder ainda não soltou
   leitura". Não corrigi porque a fórmula do prefixo vem do `momentum_v1` e mudá-la mudaria o
   vocabulário de motivos das versões vivas.
5. **A metade de cima da guarda de invalidação é inalcançável** com a regra congelada
   (`base_low < referência` é sempre verdade quando há rompimento). Mantida de propósito; dito no
   código e aqui para não ser lida como cobertura de teste faltando.
6. **Árvore compartilhada.** T3.33b (`mean_reversion_v1`) escreveu nos mesmos arquivos
   (`registry.py`, `constraints.py`, `test_registry.py`, `test_constraints.py`,
   `test_no_lookahead.py`) enquanto eu trabalhava. Deixei as três asserções de roster
   **tolerantes a novos membros** (ordem + subconjunto, em vez de tupla literal) para que as duas
   tarefas não se derrubem. `packages/core/hunter_core/db/models/agents.py` aparece **371 > 350** no
   `check_file_size.py`: são +25 linhas de outra tarefa, não minhas (`git diff --stat` confirma), e
   por isso o gate de tamanho fecha com 1 arquivo fora do orçamento que não é meu.
7. **`mypy` não existe no repositório** — usei `pyright`, que é o gate real. Declarado acima.
8. **Nada commitado**, conforme a ordem. A ativação e o replay são do operador.
