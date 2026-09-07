# Notas da T3.6 — kill switch durável

**Autor:** risk-engine-guardian, 2026-09-06/07. **Não commitei.** **Não editei `docs/**`,
`infra/migrations/**`, `packages/risk-core/**`, `packages/core/hunter_core/portfolio/**`,
`services/**`, `apps/web/**`, `.env*`.**

## O que entrou

| Arquivo | O que é |
|---|---|
| `packages/core/hunter_core/risk/daily.py` | Referência diária em `America/Sao_Paulo` e pico monotônico. **Puro** (sem sessão): tabela de casos em `tests/unit/test_risk_daily.py` |
| `packages/core/hunter_core/risk/curve.py` | As duas leituras de `portfolio_equity_snapshots` que o kill switch faz — a âncora do dia e a evidência da retomada — fixadas na resolução `1m` e em pontos que já aconteceram |
| `packages/core/hunter_core/risk/scopes.py` | `EffectiveKillSwitch`, `effective_state(session, portfolio_id, *, system=None, lock=False)`, `load_locked_state` (`SELECT … FOR UPDATE` na linha de trava) |
| `packages/core/hunter_core/risk/transitions.py` | `record_transition(...)` — a **única** via que escreve a transição auditada e move `portfolios.kill_switch_state`, com `evidence` numérica, `risk_events` e (opcionalmente) a outbox |
| `packages/core/hunter_core/risk/kill_switch.py` | `evaluate_and_persist(session, portfolio_id, state, now, …)` |
| `packages/core/hunter_core/risk/resume.py` | `resume(session, portfolio_id, *, actor_id, reason, now, …)` e `ResumeRefused` |
| `apps/api/hunter_api/routers/risk.py`, `schemas/risk.py` | `GET …/portfolios/{id}/risk/kill-switch` (VIEWER) e `POST …/kill-switch/resume` (TRADER) |
| testes | `packages/core/tests/unit/test_risk_daily.py` (12), `packages/core/tests/integration/test_risk_kill_switch.py` (16), `apps/api/tests/integration/test_risk_api.py` (9) |
| guardas atualizadas | `apps/api/tests/integration/test_rbac_matrix.py` e `test_isolation.py` (14 → 16 rotas de tenant) |

Seis módulos em vez dos três do brief: `kill_switch.py` passava de 350 linhas com os escopos e a
retomada dentro (`scopes.py` e `resume.py` são recortes dele, não peças novas), e `curve.py` nasceu
da revisão adversarial — as duas leituras da curva de equity precisavam das mesmas guardas
(resolução operacional, sem carimbo no futuro) e duplicá-las era como elas divergiriam.

## O que a revisão adversarial da Astra mudou (rodada de diff, 2026-09-07)

Transcrição: `.claude/state/astra-review-T3.6-diff.md`. Cinco achados eram meus e estão **corrigidos
com teste**; os outros são os achados 1–4 abaixo, que não são meus para fechar.

| # | O que estava errado | Cenário que a Astra deu | O que passou a valer | Teste |
|---|---|---|---|---|
| A | A virada adotava a **equity do momento** se a avaliação rodasse dentro de uma cadência (60 s) do virar do dia | Patrimônio 20.000 à meia-noite, 19.500 às 00:00:30 → abertura gravada 19.500, perda diária de 2,5 % reportada como 0 %, bloqueio de 2 % nunca dispara | A abertura é o **último ponto da curva observado em ou antes da virada** (`curve.day_opening_observation`), no máximo `DAY_OPENING_MAX_LAG_S = 300 s` antes dela; nada mais ancora o dia. Sem ponto → referência **desconhecida** | `test_an_observation_after_the_turn_may_not_anchor_the_day`, `test_an_observation_too_far_before_the_turn_is_not_a_measurement_of_it` |
| B | `resume(state=...)` deixava o chamador **fornecer** pico e abertura | Pico persistido 20.800, equity 19.968 (drawdown 4 %); um `PortfolioState` com pico 19.968 faz o drawdown ler zero e a trava sair | O estado do chamador é **re-ancorado** no pico e na abertura da linha travada antes de ser avaliado (`_anchored`), e a evidência gravada é o mesmo par | `test_a_caller_supplied_state_cannot_lower_the_durable_peak` |
| C | A evidência da retomada só precisava ser **recente**, não **posterior ao bloqueio** | Snapshot 20.000 às 12:00:00; bloqueio às 12:00:30 com 19.500; retomada às 12:00:31 cita o ponto de 31 s atrás e destrava | A observação tem de ser posterior à transição que está sendo desfeita (`_latched_since`) | `test_evidence_from_before_the_block_is_not_evidence_of_recovery` |
| D | A busca da evidência não fixava resolução nem excluía carimbo no futuro | Linha `1h` com o mesmo `ts` da `1m` e valor divergente vence o `ORDER BY`; linha com `ts` de amanhã tem idade negativa e passa em todo teste de frescura | `curve.py` fixa `resolution = '1m'` e `ts <= now` nas duas leituras | `curve.py` é a única via; coberto pelos testes de retomada |
| E | `evaluate_and_persist` aceitava qualquer `PortfolioState` | Estado das 23:59 entregue com `now=00:00:30`: avalia patrimônio velho e carimba o instante atual | `STATE_MAX_AGE_S = 60` e `marks_complete` — os dois casos degradados respondem como "sem estado": trava preservada, `automatic=None`, proteções intactas | `test_a_stale_or_unmarked_state_keeps_the_latch_instead_of_assessing` |
| F | `record_transition` não adquiria a trava da carteira | Sessão A segura a trava e lê ACTIVE para aplicar uma entrada; sessão B chama `record_transition` direto, escreve TRADING_DISABLED em `portfolios` e commita; a entrada de A passa depois do bloqueio | `record_transition` faz `load_locked_state` antes de escrever (retomar uma trava já detida é no-op) | `test_two_concurrent_evaluations_write_one_transition` |
| G | O `GET` anunciava `blocks_entries=false` com `daily_reference.available=false` | Avaliação sem âncora preserva a trava ACTIVE; a tela diz "entradas liberadas" para uma carteira que o motor não deixa operar | `blocks_entries = switch OR referência indisponível` | lógica de uma linha em `routers/risk.py`; o estado é coberto por `test_a_rollover_with_no_point_before_the_turn_leaves_the_reference_unknown` |

## Achados — cada um com o cenário que o produz

### 1. BLOQUEANTE — nenhum papel implantado escreve as duas metades de uma avaliação

`infra/migrations/ddl/paper.py` (revisão em voo do database-architect, `portfolio_risk_state_guard`,
`RAISE … 'may not be updated by ' || current_user`) recusa o `UPDATE` de `portfolio_risk_state` para
`hunter_app`; `infra/migrations/ddl/tables.py:WORKER_WRITE_TABLES` não inclui `portfolios`, então
`hunter_worker` só tem `SELECT` nela.

**Cenário:** vira o dia em São Paulo com a carteira em AVISO e os dois gatilhos já limpos. A virada
tem de gravar a nova referência diária **e** limpar o AVISO na mesma transação. Como `hunter_app`,
a gravação da referência é recusada e a carteira segue com a âncora de ontem (perda do dia medida
contra o patrimônio errado). Como `hunter_worker`, a limpeza do AVISO é recusada e a carteira segue
com tamanho pela metade num dia em que não perdeu nada. Em duas transações separadas existe uma
janela em que a referência é de hoje e a trava é de ontem.

Prova: `packages/core/tests/integration/test_risk_kill_switch.py::test_no_deployed_role_can_write_both_halves_of_one_evaluation`.

**O que eu fiz:** `evaluate_and_persist` continua sendo **uma** transação (é o que o contrato §5 e o
brief exigem). Os testes que precisam escrever as duas metades usam um `AsyncSession` sem
`SET LOCAL ROLE` (o helper `privileged`), declarando no docstring que estão apoiados num privilégio
que nenhum papel implantado tem. **Não corrigi**: `infra/migrations/**` não é meu e está sendo
editado agora. Precisa de decisão do database-architect — o caminho mínimo é `GRANT UPDATE
(kill_switch_state, kill_switch_reason) ON portfolios TO hunter_worker`, ou liberar
`portfolio_risk_state` para `hunter_app` quando a transição acompanha.

### 2. `kill_switch.changed` não é publicável por nenhum papel

`hunter_app` tem `SELECT` só em `outbox_events` (`ddl/analysis.py:ANALYSIS_APP_READ_ONLY_TABLES`);
`hunter_worker` escreve a outbox mas não `portfolios`. Então a transição e o evento não cabem numa
transação. **Cenário:** o operador retoma pela API; nenhum `kill_switch.changed` é enfileirado e os
workers só percebem na releitura seguinte. `record_transition(publish=...)` tem default **False** e
`publish=True` levanta em vez de degradar em silêncio. A garantia do contrato que sobra intacta é a
releitura a cada 10 s, que é a que o §5 usa como base; o "< 1 s" não vale hoje.

### 3. Quem pode retomar: `docs/SECURITY.md` §2 e `docs/plans/M3.md` §5 discordam

SECURITY.md põe "Kill switch de portfolio" em **TRADER+**. A decisão conjunta do M3 §5 diz que sair
de BLOQUEADO exige "ato autenticado **da identidade autorizada do Everton** — não qualquer rótulo
ADMIN". Nada no código nomeia essa identidade. **Cenário:** um TRADER convidado numa organização
retoma uma carteira bloqueada sem o Everton. Implementei o piso documentado (TRADER+) e **registro**
o conflito em vez de inventar uma allowlist ou uma variável de ambiente (`.env*` é proibido para
mim). Fechar isto é decisão do Everton + `security-reviewer`.

### 4. O escopo `system` não tem linha durável

Existe `organizations.kill_switch_state` (`db/models/identity.py:45`) e
`portfolios.kill_switch_state` (`portfolios.py:121`). Para o sistema há apenas
`Settings.system_kill_switch` (`hunter_core/settings.py:125`), configuração de processo — **não** é
travável e dois processos podem discordar. `effective_state` lê a configuração (não assume `ACTIVE`,
que era o meu plano antes da revisão da Astra) e o parâmetro `system=` permite injetar. **Cenário:**
configuração `EMERGENCY` num processo e `ACTIVE` noutro: os dois workers discordam sobre bloquear
entradas, e nenhuma transação serializa a diferença. Implementei só a persistência da carteira,
como o brief manda quando o escopo não existe.

### 5. Reuso de transição histórica pela trigger — **já fechado por outro dono, durante esta tarefa**

A Astra apontou que o `EXISTS` da `portfolios_kill_switch_is_audited` aceitava uma transição
**antiga** com o mesmo par de estados: depois de uma retomada `TRADING_DISABLED → ACTIVE`, todo
`UPDATE … = 'ACTIVE'` posterior passava sem linha nova. Durante a implementação, o database-architect
substituiu o corpo por "a mais recente do escopo **e** escrita nesta transação"
(`xmin = pg_current_xact_id()`) e acrescentou a trigger equivalente em `organizations`. Registro para
a rastreabilidade; não é mais um defeito aberto. Meu `record_transition` já escrevia a linha antes do
`UPDATE`, que é a ordem que a versão nova exige.

## Decisões de projeto que valem revisão

1. **A trava da carteira nunca recebe o estado *efetivo*.** Ela segue só a avaliação **automática**.
   Copiar o efetivo faria a carteira herdar um bloqueio da organização e continuar bloqueada depois
   que a organização retomasse. Teste:
   `test_the_effective_state_is_the_most_restrictive_scope`.
2. **A âncora e o pico persistidos vencem os do `PortfolioState` do chamador.** Sob a trava, o estado
   é reconstruído (`model_copy`) com o pico durável e a `equity_day_start` da linha. Um chamador que
   leu o pico um segundo antes subestimaria o drawdown exatamente quando o pico acabou de subir.
3. **Virada tardia não inventa a meia-noite.** A tolerância é a cadência declarada da própria linha
   (`peak_sampling_interval_s`, 60 s por padrão). Fora dela a referência fica **desconhecida**
   (`equity_day_start IS NULL`), o `automatic` sai `None`, a trava é preservada e as proteções
   continuam. **Cenário que isso fecha (Astra):** abertura 20.000, restart às 03:17 com 19.500 —
   gravar 19.500 como abertura apagaria uma perda diária de 2,5 % e o bloqueio que ela merecia.
4. **`state: PortfolioState | None`** em vez do obrigatório do brief: `None` é como o chamador diz
   "não consegui marcar a carteira". Obrigar um estado forçaria o chamador a inventar um patrimônio.
5. **`resume` nunca escreve `portfolio_risk_state`** — é assim que "não redefine pico nem perdas"
   é garantia e não promessa. Sem `PortfolioState` fresco, a evidência é o ponto mais novo de
   `portfolio_equity_snapshots`, recusado acima de `RESUME_EVIDENCE_MAX_AGE_S = 120 s`. **Cenário:**
   sem observação fresca não há prova de que o gatilho parou de morder, e a recusa é o padrão do §7.
6. **AVISO manual não se desfaz sozinho:** na virada, se a última transição foi de `actor_type='user'`,
   a limpeza automática não acontece.
7. **`evaluate_and_persist` foi pensado para rodar numa sessão `hunter_app` com `app.current_org`
   setado** (é o papel que a nova trigger designa para mover a trava). O execution-worker da T3.5 vai
   precisar abrir essa sessão por organização em vez de usar `hunter_worker` — **interface a
   combinar com a T3.5**, e depende do achado 1.

## Segunda rodada da Astra (`.claude/state/astra-review-T3.6-fixes.md`)

Ela confirmou D e F fechados e B fechado no essencial, e achou brecha nos outros quatro. Todos
corrigidos, com teste:

| # | Brecha que sobrou | Cenário | Correção |
|---|---|---|---|
| A2 | 300 s antes da virada não é medição da meia-noite | Último ponto 23:55 = 19.500; patrimônio real à meia-noite 20.000; 19.500 às 00:00:30. A abertura aceita vira 19.500 e a perda de 2,5 % lê zero | `DAY_OPENING_MAX_LAG_S` caiu de 300 s para **60 s** — exatamente uma amostra da curva de 1 min. A aproximação residual é um período de amostragem e é **publicada** (`DayReference.anchored_on`); tolerância zero não existe porque a curva é amostrada e a meia-noite não é uma amostra |
| C2 | `resume(state=...)` não era comparado com o instante do bloqueio | Estado das 12:00:00 com 20.000; bloqueio 12:00:30 com 19.500; retomada 12:00:31 entrega o estado antigo — 31 s de idade, dentro da janela | `_anchored` aplica a **mesma** condição às duas fontes: `state.as_of > blocked_at` |
| C3 | Carimbos **iguais** passavam (`<`) | Snapshot favorável e avaliação bloqueante com o mesmo carimbo de ciclo | `<=`: "empate conta como antes — duas leituras do mesmo ciclo não são uma sequência" |
| E2 | `abs()` aceitava estado no **futuro** dentro da janela | Agora 12:00, carteira valendo 19.500; o chamador entrega estado carimbado 12:01 com 20.000 | Checagem direcional nos dois lugares (`_usable_state` e `_anchored`): futuro é recusa, não frescura |
| E3 | A retomada não olhava `marks_complete` | Estado posterior ao bloqueio, equity 20.000, mas com posição sem preço atualizado | `_anchored` recusa marcação incompleta: "uma equity que é palpite não prova que o gatilho parou de morder" |
| G2 | Referência **de ontem** era publicada como disponível hoje | Worker parado na virada; trava ACTIVE; `equity_day_start` de ontem preenchido → o GET diz `available=true`, `blocks_entries=false` | `available` exige `trading_day_start_utc == sao_paulo_day_start_utc(agora)` |
| — | O docstring prometia que a evidência gravada era o mesmo par que a avaliação usou | Pico durável 20.000, equity recuperada 21.000: a avaliação usa 21.000 e a transição gravava 20.000 | A transição publica os dois: `peak_equity` (durável) e `assessed_against_peak_equity`, mais `evidence_observed_at` |

Testes novos: `test_a_caller_supplied_state_from_before_the_block_is_refused_too`,
`test_evidence_stamped_in_the_future_or_half_marked_is_refused`,
`test_an_observation_too_far_before_the_turn_is_not_a_measurement_of_it` (limiar de 60 s).

**O que a Astra continua não aprovando e eu não fecho:** TRADER ≠ identidade autorizada do Everton
(achado 3), a parede de privilégios (achado 1), a outbox (achado 2) e o DML completo da API sobre
`portfolio_equity_snapshots` — os quatro são decisão do Everton ou arquivo de outro dono.

## Para a T3.5 e a T3.12

- `effective_state(session, pf, lock=True)` adquire na ordem sistema → organização → portfolio:
  `FOR SHARE` na linha da organização, `FOR UPDATE` na linha de trava da carteira. Use **essa**
  chamada na mesma transação do efeito de entrada.
- `load_locked_state` é a trava única da carteira; a T3.12 (FIFO) e a T3.5 (expiração) devem usá-la
  em vez de abrir uma segunda.
- `ConcurrentTransition` é levantada quando o `UPDATE` condicional não afeta exatamente uma linha:
  trate como "outra sessão já moveu" e não repita a transição.

## Pendências que eu não fecho

- Achados 1, 2, 3 e 4 acima (papéis, outbox, autorização do resume, escopo `system`).
- **`portfolio_equity_snapshots` é DML completo para `hunter_app`** (`ddl/tables.py:APP_WRITE_TABLES`).
  A curva é agora a evidência de que a carteira se recuperou, e a RLS não protege a **integridade**
  dos números dentro do próprio tenant. **Cenário (Astra):** uma escrita indevida como `hunter_app`
  na organização certa muda o ponto recente de 19.500 para 20.000 e a próxima retomada aceita uma
  recuperação fabricada. Não achei rota HTTP que edite snapshots; o caminho é o privilégio SQL.
  Mitigado em parte pelos achados A/C acima (o ponto tem de ser posterior ao bloqueio e da resolução
  operacional), **não fechado** — é grant, não é meu arquivo.
- `packages/core/hunter_core/execution/paper.py` está com 359 linhas (`check_file_size` acusa 1 acima
  do orçamento). É arquivo da T3.4, em voo nesta mesma janela; não toquei.
- `apps/api/tests/integration/test_radar_api.py` está fora de formatação (`ruff format --check`) —
  não é meu arquivo, não toquei.
- `apps/api/tests/unit/test_system_workers_status.py` tem 3 falhas
  (`'_StaticHgetallRedis' object has no attribute 'scan_iter'`),
  `packages/core/tests/unit/execution/**` tem 2 (`test_paper_entry`, `test_paper_exit`, faixa de
  preço), `packages/core/tests/integration/test_admission.py` está fora de formatação e o `pyright`
  acusa 50 erros só em `hunter_core/admission/**` e `tests/unit/execution/**`: trabalho em voo de
  outras tarefas nesta mesma janela, não desta.
