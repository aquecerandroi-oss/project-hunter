# notes-T3.54b — o contexto de vela deixa de ser um número do processo e passa a ser da versão

**Tarefa:** T3.54b (`.claude/state/brief-T3.54b-contexto-por-versao.md`). **Papel:** quant-engineer.
**Fechamento desta sessão:** 2026-09-09, 11:49 (Brasília, UTC−3) — 14:49 UTC.
**Estado:** implementação completa e verde nos portões que dão para rodar aqui. **Nada foi commitado**
(árvore compartilhada; T3.52, T3.52b e T3.52c estão descommitados no mesmo diretório).

---

## 1. O problema, em uma frase

`SHADOW_CONTEXT_MINUTES = 1560` era **um** número para todas as versões, todos os mercados e todas as
barras — e, sem ninguém ter decidido isso, virou **um teto sobre o que uma versão podia ser**. A T3.54
derivou duas variantes com `atr_timeframe = 1h` e `atr_bars = 97` (alcance de 5 820 min), ativou-as, e
elas responderam `unavailable: atr_warmup` nas 5 760 barras do replay: nasceram mudas. O único conserto
disponível era subir o botão global, o que multiplicaria por ~3,8 a leitura de velas de **toda** versão
viva de 15 m (notes-T3.54 §3.4 e §6.5).

A correção é conceitual antes de ser técnica: quanto contexto uma versão precisa é uma propriedade da
**versão** — da grade em que ela decide e dos parâmetros congelados que dimensionam a janela mais longa
—, não do ambiente onde ela roda.

## 2. O que ficou de pé

### 2.1 A função pura (item 1 do brief)

`hunter_strategy_worker/context_budget.py` (novo). `required_context_minutes(strategy, params) -> int`:
sem relógio, sem IO, sem ambiente — as mesmas duas entradas que a linha congelada já carrega (o código e
`default_parameters`) sempre dão o mesmo número, que é o que permite a um replay dizer que rodou o mesmo
experimento.

A tabela `WINDOWS` transcreve **os sítios de chamada de `aggregate(...)`** de cada estratégia viva, uma
`WindowClaim` por chamada (`signal`/`atr`/`trend`), com os termos em `(parâmetro, adendo)` e a marca
`aligned` para as janelas que terminam em `align_open_time(cut, tf)` — o alinhamento custa história (uma
barra de 15 m fechando às 12:45 arrasta a janela de 1 h para 12:00) e o orçamento é por versão, então o
que entra é o **pior corte**, não o médio.

Números congelados hoje (`EXPECTED` em `tests/test_context_budget.py`, cada um checado à mão contra os
parâmetros):

| versão | grade | requisito | carregado (piso 1560 / teto 6000) |
|---|---|---|---|
| `breakout_v1`, `mean_reversion_v1`, `momentum_v1`, `session_orb_v1`, `sweep_reclaim_v1`, `trendline_breakout_v1` | 15 m | 1470 (97×15 ATR + 15 de folga) | 1560 |
| `volume_anomaly_v1` | 5 m | 1480 (97×15 + 10 de alinhamento + 15) | 1560 |
| `mean_reversion_h1_v1` | 1 h | **5880** (97×60 + 60) | **5880** |
| variante `v9` da T3.54 (`atr_timeframe=1h`) | 15 m | 5925 (97×60 + 45 + 60) | 5925 |
| variante `v10` da T3.54 (`atr_bars=24`, 1 h) | 15 m | 1545 | 1560 (não se move) |

Duas escolhas que valem registro:

- **A declaração mora no worker, não nas estratégias.** `version_code_ref` congela cada versão pelo
  digest do módulo dela e dos imports transitivos: acrescentar um atributo de classe a `momentum_v1`
  moveria o digest de sete versões ativadas e emudeceria o Lab inteiro atrás de um `/ready` verde. Foi o
  motivo pelo qual os módulos de fecho não podiam ser tocados, e é o motivo pelo qual a tabela está deste
  lado da cerca.
- **Falha fechada.** Uma estratégia sem declaração, ou um parâmetro declarado que a linha congelada não
  carrega, levanta `ContextBudgetUnknown` → o catálogo recusa (`context_budget_unknown`) e a ativação
  recusa. Um chute curto produz exatamente a versão muda que esta tarefa existe para acabar. Um teste
  unitário garante que toda estratégia do `DEFAULT_REGISTRY` está declarada, então o esquecimento custa
  um CI vermelho e não um experimento vazio.

### 2.2 O worker (item 2)

`ActiveVersion.context_minutes(config)` (`roster.py`) devolve
`min(max(requisito, SHADOW_CONTEXT_MINUTES), SHADOW_CONTEXT_MAX_MINUTES)`:

- `SHADOW_CONTEXT_MINUTES` **mantém nome, valor (1560) e significado operacional**, mas agora é o **piso**
  — por isso nenhuma população viva se move: as sete versões de 15 m/5 m pedem menos que 1560 e continuam
  lendo 1560, byte por byte;
- `SHADOW_CONTEXT_MAX_MINUTES` (novo, padrão **6000**) é o **teto** — um orçamento, não uma rede de
  segurança: 6000 é um número redondo logo acima da janela mais larga que este build sabe produzir (5880),
  então admite a irmã de 1 h e recusa a próxima escalada até alguém decidir subir;
- versão acima do teto é **recusada na ativação** (`infra/scripts/activate_strategy_version.py`, com os
  dois números na mensagem). No worker, se o teto for baixado *depois* da ativação, ele **clampa e avisa**
  (`shadow_version_context_truncated`) em vez de emudecer em silêncio.

`decide.evaluate_slot` passa `context_minutes=version.context_minutes(config)` para
`context.build_market_context`, que ganhou o parâmetro (`None` = comportamento pré-T3.54b, para os
chamadores sem versão em mãos — os testes de derivativos).

### 2.3 Replay (item 3)

`RunPlan.context_minutes` deriva pela mesma função e é impresso no `--dry-run`; `config_for` deixou de
dizer que "outro `context_minutes` não é o mesmo experimento" e passou a dizer o que agora é verdade: o
mesmo experimento é **por versão**. `replay/simulate.py` aquece o cache de velas com a janela da versão
(ler o piso faria toda barra de uma versão longa ser cache miss — correta e com uma ida ao banco por
barra). `ReplayRun` carrega `context_minutes` no recibo (`system_events` + JSONL), **não** em
`replay_runs`, cujas colunas são migração e cujo papel não tem `UPDATE`.

### 2.4 Envelope e ledger (item 4)

`Provenance.context_minutes` chega ao envelope ao lado de `bars_in_context`: um diz quantas velas havia,
o outro quantas foram **pedidas**. O par separa "mercado com buraco" de "janela mais curta que a lookback
da versão" — a distinção que custou à T3.54 um experimento inteiro. `ExplainRow` ganhou o mesmo inteiro
como **sexto campo**, anexado ao fim (um leitor escrito contra os cinco continua funcionando).

## 3. O que eu fiz nesta sessão (a T3.54b já estava quase inteira na árvore)

O agente anterior parou ao escrever o teste de integração. Encontrei os itens 1–4 implementados e
verifiquei-os lendo o `git diff` inteiro antes de tocar em qualquer coisa. O que **eu** acrescentei:

1. **O teste que faltava, pela porta certa.** O arquivo `tests/test_context_per_version.py` já provava o
   **construtor de contexto** contra o Postgres (três testes). Faltava provar a **fiação**: acrescentei
   `test_the_worker_gives_each_version_its_own_window_in_the_same_pass`, que chama
   `decide.evaluate_slot` — a mesma função que o consumidor chama quando uma vela fecha — para as duas
   versões na mesma passada, com um espião sobre `load_candles`. Ele exige linhas reais em
   `strategy_versions` (o slot de episódio tem FK), daí a fixture `activated` e o parâmetro opcional
   `version_id` no helper `version_of`.
   As asserções: `start` de 5 m = corte − 1560 min, `start` de 1 h = corte − 5880 min, e o desfecho de
   cada uma — `not_triggered/volume_below_threshold` e `unavailable/atr_warmup`. A segunda é a metade
   interessante: **a irmã de 1 h recebeu os 5 880 min a que tem direito e ainda assim aqueceu**, porque o
   mercado sintético só tem 2 000 minutos persistidos. Antes da T3.54b as duas causas eram a mesma linha
   de log.
2. **`test_replay_explain.py::TestTheRow`**: o agente anterior já havia renomeado
   `test_it_is_the_five_fields_and_nothing_else` → `..._six_fields_...` e acrescentado
   `test_a_row_nobody_sized_says_zero_instead_of_lying`. Conferi que a mudança é honesta (o campo é
   **anexado**, o `0` é "não registrado" e o replay sempre registra) e que passa. Não havia nada a
   corrigir além de verificar.
3. **`docs/PIPELINE.md` §6b**: parágrafo novo "A janela de contexto é da versão, não do processo
   (T3.54b)", inserido antes de "**Escritor único de outcomes.**".
4. **Portões** (`ruff format --check`, `ruff check`, `pyright`, `check_file_size.py`) e as duas suítes.

## 4. Arquivos (lista exata, caminhos absolutos)

**Da T3.54b, criados/alterados pelo agente anterior e mantidos por mim:**

- `C:\dev\project-hunter\services\strategy-worker\hunter_strategy_worker\context_budget.py` (novo)
- `C:\dev\project-hunter\services\strategy-worker\hunter_strategy_worker\config.py`
- `C:\dev\project-hunter\services\strategy-worker\hunter_strategy_worker\context.py` (hunks T3.52 do
  portão de regime preservados intactos)
- `C:\dev\project-hunter\services\strategy-worker\hunter_strategy_worker\catalogue.py` (idem)
- `C:\dev\project-hunter\services\strategy-worker\hunter_strategy_worker\roster.py`
- `C:\dev\project-hunter\services\strategy-worker\hunter_strategy_worker\record.py`
- `C:\dev\project-hunter\services\strategy-worker\hunter_strategy_worker\decide.py`
- `C:\dev\project-hunter\services\strategy-worker\hunter_strategy_worker\replay\plan.py`
- `C:\dev\project-hunter\services\strategy-worker\hunter_strategy_worker\replay\run.py`
- `C:\dev\project-hunter\services\strategy-worker\hunter_strategy_worker\replay\simulate.py`
- `C:\dev\project-hunter\services\strategy-worker\hunter_strategy_worker\replay\explain.py`
- `C:\dev\project-hunter\services\strategy-worker\hunter_strategy_worker\replay\ledger.py`
- `C:\dev\project-hunter\infra\scripts\activate_strategy_version.py`
- `C:\dev\project-hunter\services\strategy-worker\tests\test_context_budget.py` (novo, 35 testes)
- `C:\dev\project-hunter\services\strategy-worker\tests\test_replay_explain.py`

**Escritos nesta sessão:**

- `C:\dev\project-hunter\services\strategy-worker\tests\test_context_per_version.py` (novo; três testes
  do agente anterior + o teste de fiação, a fixture `activated`, o `version_id` em `version_of` e o
  parágrafo novo do docstring)
- `C:\dev\project-hunter\docs\PIPELINE.md` (§6b, um parágrafo)
- `C:\dev\project-hunter\.claude\state\notes-T3.54b.md` (este arquivo)

**Não tocados de propósito:** `packages/core/tests/integration/*`, `infra/scripts/derive_variant.py`,
`services/strategy-worker/tests/test_health_migration_present.py` (outros agentes), os módulos de fecho
(`aggregate, base, canonical, envelope, indicators, numeric, schema`) e qualquer `.env*`.

## 5. Comandos e saída real

Todos em primeiro plano, com `timeout 290`. **Duas** invocações com testcontainers no total (uma antes de
escrever o teste de fiação, para verificar o estado herdado; a outra depois, que é a que vale).

```
$ uv run pytest services/strategy-worker/tests -q -m "not integration"
........................................................................ [ 23%]
........................................................................ [ 46%]
........................................................................ [ 69%]
........................................................................ [ 92%]
........................                                                 [100%]
312 passed, 208 deselected in 9.95s
```

```
$ uv run pytest services/strategy-worker/tests/test_context_per_version.py -q -m integration
....                                                                     [100%]
4 passed in 34.87s
```

(a mesma invocação antes do teste novo dava `3 passed in 34.84s` — o estado herdado já estava verde.)

```
$ uv run ruff format --check services/strategy-worker infra/scripts/activate_strategy_version.py
115 files already formatted

$ uv run ruff check services/strategy-worker infra/scripts/activate_strategy_version.py
All checks passed!
```

```
$ uv run pyright
... 15 errors, 0 warnings, 0 informations   # nenhum nos arquivos da T3.54b
```

Os 15 erros do `pyright` no repositório inteiro estão em cinco arquivos, **todos fora do escopo desta
tarefa** e nenhum tocado por ela:

```
apps\api\tests\integration\test_lab_signals_pagination_api.py
infra\scripts\tests\test_render_operations.py
packages\core\tests\unit\strategies\test_mean_reversion_v1.py
packages\core\tests\unit\strategies\test_no_lookahead.py
services\strategy-worker\tests\test_replay_stress.py   (reportPrivateUsage, arquivo intocado no HEAD)
```

```
$ uv run python infra/scripts/check_file_size.py
scanned 584 files; 0 over budget, 0 grandfathered
```

Sonda de apoio (fora do repositório, para não asseverar um desfecho que eu não tivesse medido antes de
gastar a última invocação de contêiner):

```
5m/1560 volume_anomaly_v1    not_triggered volume_below_threshold {'volume_ratio_5m': '1'}
1h/2000 mean_reversion_h1_v1 unavailable   atr_warmup {'window_start': '2026-09-01T13:00:00Z',
                                                      'first_candle': '2026-09-04T04:40:00Z'}
```

Também rodei, por causa da mudança em `activate_strategy_version.py`:

```
$ uv run pytest infra/scripts/tests -q -m "not integration"
1 failed, 125 passed, 2 skipped, 27 deselected in 21.08s
FAILED infra/scripts/tests/test_render_operations.py::test_two_operations_mapping_to_one_file_name_fail_loud
  E   ModuleNotFoundError: No module named 'matplotlib'
```

A falha é **ambiental e alheia**: `matplotlib` não está no `pyproject` de propósito (PIPELINE §9b manda
rodar aquele script com `uv run --with matplotlib`), e o arquivo é de outra tarefa. Os testes da ativação
propriamente dita passam.

## 6. Não-antecipação

A mudança só pode mover a **borda esquerda** da janela: `build_context` continua descartando toda vela
não final e tudo que fecha depois de `source_bar_close`, e o `end` de `load_candles` continua sendo o
corte. Três provas específicas:

- `test_a_wider_window_never_moves_a_decision` (unidade): a mesma barra avaliada com 4× mais história
  devolve a mesma avaliação, campo por campo;
- `test_the_minute_still_forming_never_enters_the_window` (unidade): a vela em formação continua sem
  existir para a decisão, com a janela larga;
- `test_the_wider_window_still_ends_at_the_cut` (integração): a última vela das duas versões é a mesma, a
  janela larga é a estreita com mais passado na frente (`wide[-len(narrow):] == narrow`) e nenhuma vela
  fecha depois do corte.

## 7. Números que eu tive de assumir

1. **Folga de uma barra da própria grade** por janela (15 min nas de 15 m, 60 min na de 1 h). Não é
   necessidade aritmética — um contexto do tamanho exato do alcance faz `aggregate` achar o primeiro
   minuto —, é a margem que mantém um warm-up sendo warm-up e não um truncamento. É o menor incremento
   que significa alguma coisa na grade em que é medido. Herdado do agente anterior; conferi que os
   `EXPECTED` batem com essa regra.
2. **Teto padrão 6000 min.** Escolha operacional, não derivada: número redondo logo acima de 5880. Quem
   quiser a próxima versão mais larga tem de subir o teto **deliberadamente**, ciente de que ele custa
   leitura de vela.
3. **`pivot_k = 4` dobrado na constante de `sweep_reclaim_v1`** (o termo real é
   `pivot_lookback_bars + pivot_k + 1`, com `pivot_k` congelado em 3 em todas as linhas vivas). É a única
   dobra da tabela, e o teste-espião sobre `aggregate` é o que a protege: uma variante que mexesse em
   `pivot_k` morreria em CI.
4. **`PERSISTED = 2000` minutos** no teste de integração: a única faixa em que 1560 e 5880 se distinguem
   pelo que **recebem**, e não só pelo que pedem.
5. **Os desfechos assertados no teste de fiação** (`volume_below_threshold`, `atr_warmup`) foram medidos
   pela sonda do §5 antes de virarem asserção — não são expectativa, são observação.

## 8. Limites honestos desta entrega

- **Não rodei a suíte de integração inteira do `strategy-worker`.** A regra operacional desta sessão é de
  no máximo duas invocações com testcontainers, e as duas foram para `test_context_per_version.py`. Os
  arquivos que exercitam `evaluate_slot` contra o banco (`test_shadow_decisions`, `test_replay_engine`,
  `test_replay_reproduce`, `test_replication_cohort`, `test_regime_gate`, `test_shadow_outcomes`,
  `test_consumer_isolation`, `test_guards`, `test_regime_stamp`) atravessam código alterado por T3.52
  **e** por T3.54b e não foram executados aqui. O caminho por onde eles passam é o de todas as versões de
  15 m/5 m, cujo `context_minutes` continua sendo exatamente 1560 — a mudança é desenhada para não movê-los
  —, mas isso é um argumento, não uma medição. **Recomendo ao revisor rodar a faixa de integração inteira
  antes do commit.**
- **A tabela `WINDOWS` é uma transcrição.** O teste-espião prova que ela cobre o que o código pede *para
  os parâmetros congelados de hoje*; um parâmetro novo em uma estratégia futura sem entrada na tabela é
  recusado (bom), mas um sítio de `aggregate` novo dentro de uma estratégia já declarada só é pego se o
  espião o vir sob os parâmetros do teste. É a razão de o espião rodar a estratégia real sobre uma série
  desenhada para não degenerar (onda de período 37, primo com 5, 15 e 60).
- **`SHADOW_CONTEXT_MAX_MINUTES` não foi documentado em `docs/DEPLOYMENT.md` nem posto no compose** — o
  padrão de 6000 vale sem declarar nada, e mexer nesses arquivos está fora do escopo desta tarefa (e
  ambos são território de outros agentes nesta janela). Fica registrado como pendência de uma linha.
- **Nada foi commitado**, conforme a regra da árvore compartilhada.

## T3.54c

**Fechamento:** 2026-09-09 (Brasília, UTC−3). **Papel:** backend-specialist. Fecha as três
ressalvas deixadas em aberto por esta sessão e por T3.52b, sobre o diff ainda descommitado
acima. **Nada foi commitado.**

### 1. `_refuse_unbudgeted_context` não roda mais numa reativação idempotente

O bug: a chamada em `activate()` (`infra/scripts/activate_strategy_version.py`) rodava
incondicionalmente, **antes** de qualquer um dos dois ramos que respondem "já ativada; nada a
fazer" (o caminho simples e `activate_derived`). Se alguém baixasse `SHADOW_CONTEXT_MAX_MINUTES`
depois de uma versão já ativada, o no-op esperado virava uma recusa — exatamente o
comportamento que o próprio worker se recusa a ter (ele clampa e loga
`shadow_version_context_truncated`, nunca emudece). Correção: `_refuse_unbudgeted_context` só é
chamada quando `row.activated_at is None`. Testada por
`TestUnbudgetedContextRefusal::test_an_already_activated_row_stays_a_no_op_under_a_lowered_ceiling`
(abaixo).

### 2. Estratégias sintéticas de teste: `context_budget.declare()`

A recusa por janela não declarada (`ContextBudgetUnknown` → `context_budget_unknown`) quebrava
`test_derive_variant.py` porque `NamedStrategy` (`tests/builders.py`) registra a estratégia real
`volume_anomaly_v1` sob uma chave descartável (`variant_activate_dry_v1`, etc.) — chave que nunca
está em `WINDOWS`, a tabela transcrita das estratégias vivas.

Decisão (documentada no docstring do módulo, "Test strategies are declared too"): a recusa
continua **honesta e incondicional** — se aplica a toda estratégia, registrada ou não; a
alternativa (isentar chaves não registradas) foi rejeitada porque transformaria silenciosamente
qualquer lacuna de **produção** em `WINDOWS` (uma estratégia viva que ninguém transcreveu) num
passe silencioso — o mesmo modo de falha que esta tarefa existe para fechar, só que disfarçado.
Em vez disso, `context_budget.py` ganhou um hook público `declare(key, version, windows)` que
grava num dicionário mutável `_DECLARED`, consultado por `declared_windows()` **depois** da
tabela `WINDOWS` (que nunca pode ser sobrescrita por um `declare()` de teste). `NamedStrategy`
chama `declare(self.key, self.version, WINDOWS[("volume_anomaly_v1", "v1")])` no `__init__` —
as janelas reais do contrato que ela de fato executa, não um número inventado.

### 3. Teste do ponto de entrada real, sem Docker

`services/strategy-worker/tests/test_activation.py::TestUnbudgetedContextRefusal` (2 testes,
`@pytest.mark.unit`, sem testcontainer): usa a mesma costura que
`test_it_refuses_when_the_migration_is_missing` já usava (`script.migration_applied`,
`script.purpose_column_present`, `script.load_row` são nomes de módulo importados com `from ...
import`, então dão para trocar por fakes) para chamar `script.activate(None, ...)` de verdade,
com `conn=None` — nada toca o `conn` antes da recusa disparar.

- `test_the_message_names_both_the_requirement_and_the_ceiling`: `SHADOW_CONTEXT_MAX_MINUTES=100`
  via `monkeypatch.setenv`, uma linha ainda não ativada (`activated_at=None`); a mensagem carrega
  os dois números (`needs {required} minutes` e `SHADOW_CONTEXT_MAX_MINUTES is 100`), calculados
  pela própria `required_context_minutes` para não travar num número mágico.
- `test_an_already_activated_row_stays_a_no_op_under_a_lowered_ceiling`: a prova do item 1 pelo
  ponto de entrada real — linha já ativada, `code_ref` batendo, teto baixado para `1`; a resposta
  continua sendo "was already activated ...; nothing to do".

### 4. `docs/DEPLOYMENT.md`

Duas linhas novas na tabela de orçamento do replay (§5.2), ao lado de `REPLAY_*`:
`SHADOW_CONTEXT_MINUTES` (piso, padrão `1560`) e `SHADOW_CONTEXT_MAX_MINUTES` (teto, padrão
`6000`), com link para `docs/PIPELINE.md` §6b para o conceito.

### 5. `migration_ddl` põe `infra/migrations` no `sys.path` por conta própria

Concern 1 da T3.52b: `test_0012_and_the_domain_constant_agree_on_the_cohort_grammar` não usa
nenhuma fixture (nem `upgraded`), só chama `migration_ddl("replication")` direto — então, isolado
(`pytest -k cohort_grammar`), nunca havia rodado `alembic_config` antes, e o `sys.path` não tinha
`infra/migrations`. `migration_ddl` (`packages/core/tests/integration/conftest.py`) agora insere
o diretório em `sys.path` ela mesma, antes do `import_module`. Verificado **sem** container (o
teste não abre conexão nenhuma):

```
$ timeout 120 uv run pytest packages/core/tests/integration/test_migrations.py -q -k cohort_grammar
.                                                                        [100%]
1 passed, 110 deselected in 1.50s
```

### 6. Arquivos (lista exata, caminhos absolutos)

- `C:\dev\project-hunter\infra\scripts\activate_strategy_version.py` — guarda de idempotência em
  `activate()` + docstring de `_refuse_unbudgeted_context` atualizada
- `C:\dev\project-hunter\services\strategy-worker\hunter_strategy_worker\context_budget.py` —
  `declare()`, `_DECLARED`, `declared_windows()` consultando os dois, parágrafo novo no docstring
  do módulo ("Test strategies are declared too")
- `C:\dev\project-hunter\services\strategy-worker\tests\builders.py` — import de
  `context_budget.WINDOWS`/`declare` e chamada em `NamedStrategy.__init__`
- `C:\dev\project-hunter\services\strategy-worker\tests\test_activation.py` — classe
  `TestUnbudgetedContextRefusal` (2 testes novos, unit)
- `C:\dev\project-hunter\packages\core\tests\integration\conftest.py` — `migration_ddl` põe
  `infra/migrations` em `sys.path`
- `C:\dev\project-hunter\docs\DEPLOYMENT.md` — tabela `SHADOW_CONTEXT_*` em §5.2
- `C:\dev\project-hunter\.claude\state\notes-T3.54b.md` — esta seção

**Não tocados:** os módulos de fecho, `activate_derived.py` (sua própria checagem de no-op já
era correta e não precisou mudar), qualquer `.env*`.

### 7. Comandos e saída real

Em primeiro plano, `timeout 290`. **Uma** invocação com testcontainer no total (a de
`test_derive_variant.py`, exigida pela tarefa); o item 5 não precisou de container.

```
$ timeout 120 uv run pytest services/strategy-worker/tests/test_activation.py -q -m "not integration"
.......                                                                  [100%]
7 passed, 9 deselected in 4.65s

$ timeout 120 uv run pytest services/strategy-worker/tests -q -m "not integration"
........................................................................ [ 22%]
........................................................................ [ 45%]
........................................................................ [ 68%]
........................................................................ [ 91%]
..........................                                               [100%]
314 passed, 208 deselected in 12.55s   # era 312 antes desta sessão; +2 testes novos

$ timeout 290 uv run pytest services/strategy-worker/tests/test_derive_variant.py -q -p no:randomly
................                                                         [100%]
16 passed in 57.65s

$ timeout 120 uv run pytest packages/core/tests/integration/test_migrations.py -q -k cohort_grammar
.                                                                        [100%]
1 passed, 110 deselected in 1.50s

$ timeout 60 uv run ruff format --check services/strategy-worker infra/scripts/activate_strategy_version.py packages/core/tests/integration/conftest.py docs/DEPLOYMENT.md
117 files already formatted

$ timeout 60 uv run ruff check services/strategy-worker infra/scripts/activate_strategy_version.py packages/core/tests/integration/conftest.py
All checks passed!

$ timeout 200 uv run pyright
... 15 errors, 0 warnings, 0 informations   # os mesmos 15 pré-existentes da nota acima, em
                                             # arquivos fora do escopo — nenhum nos tocados aqui
                                             # (confirmado também com pyright isolado nos 5
                                             # arquivos desta seção: 0 errors)

$ timeout 60 uv run python infra/scripts/check_file_size.py
scanned 584 files; 0 over budget, 0 grandfathered   # context_budget.py bateu 354/350 na primeira
                                                     # versão do docstring; cortado para caber

$ timeout 120 uv run pytest infra/scripts/tests -q -m "not integration"
1 failed, 125 passed, 2 skipped, 27 deselected in 20.40s
FAILED infra/scripts/tests/test_render_operations.py::test_two_operations_mapping_to_one_file_name_fail_loud
  ModuleNotFoundError: No module named 'matplotlib'   # ambiental, alheia, já registrada na
                                                       # sessão anterior (PIPELINE §9b manda
                                                       # `uv run --with matplotlib`)
```

### 8. Limites honestos

- Não rodei a suíte de integração inteira do `strategy-worker` (mesma restrição operacional desta
  janela: no máximo dois testcontainers, e um só foi usado aqui). Os arquivos que exercitam
  `evaluate_slot`/ativação contra o banco além de `test_derive_variant.py` e
  `test_context_per_version.py` (já cobertos por T3.54b) não foram re-executados nesta sessão.
- `context_budget.declare()` é um registro global de processo (`_DECLARED`, mutável, nunca
  limpo entre testes); inofensivo porque toda chave de teste é descartável e única por cenário,
  mas vale registrar que é estado compartilhado dentro da suíte, não por design de produção.
