---
tags: [astra, revisao, meme-worker, instrumento, exp-m26, guarda, ciclo]
date: 2026-10-07
updated: 2026-10-09
status: fechada
owner: backend-specialist
decided_on: 2026-10-07
by: Astra + backend-specialist
---

# Revisão da Astra — tempo de ciclo da cadeia e do Lab (07/10/2026)

**Por que existe:** a guarda de ciclo do §6.8 do [[EXP-M26-grafico-em-moedas-maduras|EXP-M26]] ("ciclo da cadeia e do
Lab: + 20 % no p95") estava **não mensurável**: nenhum log nem heartbeat guardava tempo de ciclo. O Everton decidiu em
07/10 **instrumentar antes do seed** (item 3 de "Decisões do Everton (07/10/2026)"; "não mensurável" nunca conta como
"passou"). O código está em `services/meme-worker/hunter_meme_worker/cycle_metrics.py`, ligado em `main.py`; os campos
estão documentados em [[03-TRADING/Meme/README|Meme]] (seção "Tempo de ciclo do `meme-worker`"). O bruto da Astra:
`.claude/state/astra-review-meme-cycle-metrics.md`.

**Veredito dela:** REQUEST_CHANGES (3 HIGH, nenhum erro na fórmula do percentil). Os três foram tratados abaixo; o
terceiro é de protocolo e fica com o orquestrador.

| achado | decisão |
|---|---|
| **MF1 (HIGH).** O `HSET` extra roda depois do cronômetro e usa o cliente Redis (5 s de timeout, 3 tentativas): com o Redis degradado o laço espera vários segundos sem aparecer no p95 | **aceito e corrigido.** A publicação tem orçamento próprio de 1 s (`asyncio.timeout`); o estouro é `meme_cycle_metrics_publish_failed` e conta em `<loop>_cycle_publish_failed_total`. Teste com publicação travada (`test_a_publish_that_hangs_costs_the_loop_only_its_budget`). A frase "sem mudança de comportamento" fica **corrigida**: no caminho normal o custo é um `HSET` (~ms) por ciclo; sob Redis degradado, no máximo 1 s por ciclo. A cadeia ganhou uma dependência nova de Redis dentro do laço (o Lab já a tinha em `write_lab_heartbeat`) |
| **MF2 (HIGH).** Sem proveniência: depois de um reinício, `ts` novo do heartbeat geral + p95 do processo anterior parecem medida atual | **aceito e corrigido.** Cada processo publica `<loop>_cycle_run_id` (uuid) e `<loop>_cycle_since` (UTC); `announce` publica a geração vazia no boot, sobrescrevendo os campos antigos; o `ts` geral nunca valida a métrica. Testes `test_every_publication_names_its_generation` e `test_announce_*` |
| **MF3 (HIGH, bloqueia o seed).** Os campos guardam resumos móveis; não permitem recuperar a distribuição. Semear com o processo vivo mistura as fases no anel; o desenho ainda cita "72 h antes de I1", e a instrumentação nova não recupera esse passado | **aceito, fora deste diff** (exige coleta durável e protocolo; ver "Proposta" abaixo). Escrito no README e aqui: a base do "antes" é **prospectiva** |
| Nearest-rank | sem erro encontrado; reaproveitado de `lab_heartbeat.percentile` |
| Ciclo e overrun | ela mantém o passo inteiro (inclui `record_tick` e `write_lab_heartbeat`). **Discorda** de eu ter descrito o overrun como "início do atraso de cadência": a cadência é sempre `duração + período`; overrun é um limiar de trabalho. **Aceito:** docstring e README reescritos; a guarda compara o p95 por si, o contador é alarme (um Lab de 10 s para 13 s piora 30 % sem overrun). "Duas horas" também saiu: são 120/480 ciclos **concluídos** |
| Inteiros | **aceito:** duração por aritmética inteira sobre `monotonic_ns` (arredonda ao ms mais próximo). **Rejeitado:** aplicar o limiar de overrun em ns; a quantização de 1 ms (60 000,4 ms conta como 60 000) é irrelevante para uma guarda de +20 % e o campo publicado é o ms |
| UTC | **aceito:** `record` recusa offset diferente de zero (teste `test_a_non_utc_offset_is_refused`) |
| Throttle sem resumo final | **aceito como está:** `overruns_total` é a referência durante o boot; o log é só alarme |
| Cobertura de teste (publicação lenta, reinício) | **acrescentada** (publicação travada, `announce` com Redis morto, composição com `forever`) |

## Proposta de histórico durável (sem migração) — a opção 2 foi implementada na rodada 2 (ver abaixo)

A Astra mostrou que um `HGETALL` a cada N minutos **não basta**: no Lab (4 ciclos/min) vários `last_cycle_ms` são
sobrescritos entre leituras, e **p95 de p95 não é p95 dos ciclos**. O que a guarda "antes × depois" precisa é a
duração de **cada ciclo**, com a geração (`run_id`) e a sequência (`cycles_total`) para provar que não houve buraco.

1. **Coletor externo supervisionado** (dono sugerido: `devops-engineer`; **não** um processo na máquina do Everton:
   a regra do projeto proíbe estado local e cron em máquina de dev): lê `hb:meme:radar` a cada **5 s** e grava,
   para cada novo `(run_id, loop, cycles_total)`, uma linha em **`system_events`** (tabela que **já existe**:
   `component`, `event`, `data JSONB`; append-only, particionada por mês) com `last_cycle_ms`, `last_cycle_at`, o
   instante da leitura e a fase (`antes`/`depois` do seed). Um salto em `cycles_total` dentro do mesmo `run_id`
   é **buraco declarado**, nunca preenchido; a guarda exige cobertura mínima. Custo: ~7 200 linhas/dia.
   **Atenção:** `system_events` tem retenção de **30 dias** (`docs/DATABASE.md`); a base "antes" e os ≥ 7–21 dias do
   experimento têm de ser **congelados** (exportados) antes de expirarem.
2. **Alternativa dentro do worker:** uma fila limitada que grava a mesma linha em `system_events` por ciclo. Sem
   buraco de amostragem, mas põe escrita no Postgres ao lado dos laços (decisão do `database-architect`).
3. **Futuro, com migração:** uma tabela própria de ciclos (`loop`, `run_id`, `seq`, `ended_at`, `duration_ms`).
   Uma coluna `cycle_ms` em `meme_lab_ticks` **não serve** sozinha: o `record_tick` não consegue incluir a duração da
   própria escrita nem a do heartbeat que vem depois dele (Astra).
4. **Protocolo antes do seed** (para o orquestrador/Everton): (a) registrar na página do EXP que a base do "antes" é
   prospectiva e de qual intervalo; (b) a geração vale a partir do boot (`run_id`): ou reinicia o worker logo antes do
   seed e fecha a base com a geração anterior, ou compara por janelas de ciclos individuais (coleta 1 ou 2), nunca pelo
   anel (que mistura as fases); (c) interrupção é **ausência de evidência**, nunca melhora.

**Divergências:** só o limiar de overrun em ns (rejeitado, acima). **Aprendizado de medição:** o campo "p95" de um
heartbeat é um resumo móvel de um processo; sem `run_id`, sem sequência e sem a distribuição individual ele serve para
alarme, não para uma comparação "antes × depois".

## Rodada 2 (07/10/2026) — revisão do `code-reviewer` + Astra sobre a correção, e a opção 2 implementada

Dois brutos: `.claude/state/astra-review-review-meme-cycle-metrics.md` (a conferência das correções da rodada 1, pelo
`code-reviewer` com a Astra) e `.claude/state/astra-review-meme-cycle-history.md` (o histórico durável implementado
logo depois). Findings que só um dos dois levantou foram conferidos por teste antes de entrar.

**A. Conferência das correções (REQUEST_CHANGES, 2 MEDIUM + 2 LOW; confirmado por inspeção e por teste):**

| achado | decisão |
|---|---|
| **MEDIUM.** Anúncio dentro de `if chain_curves_enabled` / `if lab is not None`: com laço desligado ou radar desligado, os campos do processo anterior continuam no hash (zumbis), e o runtime renova o TTL | **aceito e corrigido.** `build_cycle_instruments` + `announce()` rodam **no topo** de `run_meme`, antes do ramo `MEME_ENABLED`, para os dois laços; campo novo `<loop>_cycle_enabled`. O hash **não** é apagado (outros escritores); o pressuposto de **instância única** ficou escrito no README. Testes com hash pré-preenchido (`test_a_disabled_loop_still_replaces_the_previous_process_fields`, `test_a_boot_with_everything_off_...`) |
| **MEDIUM.** O teste de cancelamento não chega a `_publish`: trocar `except Exception` por `except BaseException` engoliria um cancel durante o `HSET` e nada falharia | **aceito.** Testes em que o publicador sinaliza "entrei" e dorme, cancela-se a tarefa e exige-se `CancelledError` com `publish_failed_total == 0`, para `timed_step` e para `announce`. **Mutação conferida:** com `BaseException` os dois testes falham; restaurado, passam |
| LOW. Teste do orçamento frouxo (aceitava 2 s) | **aceito:** o tempo decorrido tem de ser < 0,5 s com orçamento de 50 ms, e `publish_failed_total == 1` |
| LOW. `started_at` sem validação UTC | **aceito:** recusa ingênuo e offset ≠ 0 |
| Docs: o tempo de publicar fica fora do número medido mas **dentro da cadência** | **aceito:** docstring e README |
| Concorda: o cancel externo propaga (`CancelledError` é `BaseException`; o timeout converte o próprio cancel em `TimeoutError`); o cliente redis-py fecha a conexão cancelada; nenhum campo colide; os leitores da API escolhem campos por nome | registrado |

**B. Revisão do histórico durável (REQUEST_CHANGES; 2 HIGH + 1 MEDIUM; a lógica da fila e do `ack` conferida sem erro):**

| achado | decisão |
|---|---|
| **HIGH.** Retry depois de um COMMIT aplicado com a confirmação perdida duplica o ciclo (outro `id`, outro `created_at`; a PK inclui `created_at`, então UUID determinístico não bastaria) | **aceito como contrato, não como correção de escrita** (sem migração não há índice único). A promessa "uma linha por ciclo" virou "**ao menos** uma"; a identidade é `(loop, run_id, seq)`, deduplicada antes do percentil. `CYCLES_SINCE_SQL` (`DISTINCT ON`) é a consulta oficial e foi provada em Postgres real com um duplicado e um ciclo fora da janela. Teste da perda de confirmação (`test_a_lost_commit_confirmation_...`) |
| **HIGH (bloqueia a guarda).** Sequência contínua não prova cobertura: ciclos 1–100 gravados, 101–110 na fila, o processo morre; a geração seguinte tem outro uuid e a antiga termina "contínua"; uma geração inteira perdida é invisível. E a consulta de exemplo filtrava por `created_at` | **aceito, em parte corrigido.** Novos eventos `generation_start` (todo boot, os dois laços, com `enabled`/`nominal_ms`/`window`) e `generation_end` (só em desligamento limpo, com `cycles_total`/`overruns_total`): geração sem fim = queda, cobertura só até o último `seq` contíguo; laço desligado explica a ausência. Janelas por `data->>'ended_at'`, nunca `created_at`; ordem por `seq` (um lote tem um só `created_at`: o teste de integração mostrou isso na prática). **Continua aberto:** congelar a janela, a cobertura mínima e as caudas desconhecidas — decisão do orquestrador/Everton; sem prova de cobertura a guarda é **não mensurável** |
| **MEDIUM.** O orçamento valia duas vezes (banco + Redis ≈ 20 s por flush, 6 s no close) e um segundo cancel no `close` podia pular os fechamentos seguintes | **aceito:** um orçamento só por flush (`publish_counters` recebe o que sobrou; sem sobra, não publica); `cycles.close()` foi para o **fim** do `finally`, de modo que nada depois dele pode ser pulado. Testes de orçamento único e mutação conferida (publicar com `budget_s` inteiro falha o teste) |
| Nice: `close` só gravava 500 de 4 096 | **aceito:** `drain` grava lote a lote até esvaziar, falhar ou estourar os 3 s (testes) |
| Nice: contadores zerados não eram anunciados no boot | **aceito:** `announce()` publica os contadores com `force` |
| Nice: `dropped_total` pode contar uma linha que ainda foi gravada | **aceito como limite superior**, documentado |
| Nice: proveniência por geração (`code_ref`/deploy) | **parcial:** `generation_start` leva `nominal_ms`, `window`, `enabled` e `started_at`; **não** leva `code_ref` — o worker não expõe a versão de deploy hoje; fica como pendência |
| Teste: o terceiro teste de integração só negava `DELETE` | **corrigido:** `UPDATE` e `DELETE`, para `hunter_worker` e `hunter_app` (4 casos) |
| Poda/dump: sem bloqueante pelo volume; a poda é por mês inteiro (retém mais de 30 dias de linhas); o dump inclui as linhas; leitores filtram por componente/evento; sem partição do mês da escrita o lote espera e pode estourar a fila | registrado no README; **o `database-architect` ainda revisa** |
| Discordou de "sem mudança de comportamento" absoluto | **aceito** (já corrigido na rodada 1: custo de ≤ 1 s por ciclo sob Redis degradado; o hook da fila não espera o banco) |

**Divergências:** nenhuma de fundo. **Aprendizado de medição:** uma série durável "sem migração" numa tabela de eventos não
herda as garantias de uma tabela própria — unicidade, ordem e cobertura passam a ser **contrato do leitor**, e o
teste de integração que escreve e lê de volta achou dois defeitos que o fake não via (parâmetro `timestamptz` sem `CAST` na
consulta; `created_at` único por lote, que desfaz a ordem).

## Rodada 3 (09/10/2026) — revisão do `database-architect` (Astra) do histórico durável: APROVADO no lado do banco

Bruto: `.claude/state/astra-review-db-meme-cycle-history.md` (somente leitura; ela não rodou pytest nem consultou o banco).
Veredito: o uso de `system_events` é compatível com grants, particionamento e RLS (tabela global, `INSERT` do `hunter_worker`, escrita
pela tabela-pai); nenhum vazamento de conexão demonstrado; dois *must-fix* no **ciclo de vida das gerações**. Todos tratados em TDD
(testes: `test_cycle_lifecycle.py` pelo `run_meme` real, `test_cycle_history_contract.py`, `test_cycle_history_integration.py`).

| # | severidade | achado | decisão |
|---|---|---|---|
| 1 | **HIGH** | `cycles.close()` no `finally` gravava `generation_end` mesmo quando um laço caiu: a queda parecia desligamento limpo | **aceito e corrigido.** `generation_end` leva `clean`; `CycleInstruments.supervised()` envolve o `run_meme` inteiro e só marca `clean = true` para saída normal ou `CancelledError` (SIGTERM), `false` para qualquer outra (um `ExceptionGroup` do `TaskGroup`). Teste pelo `run_meme` real com `chain_once` levantando. A recíproca também foi escrita: **ausência de `generation_end` = término não comprovado**, não "queda" (um `kill -9` e um desligamento com o banco fora também o perdem) |
| 2 | **MEDIUM** | `MEME_ENABLED=false`: os `generation_start` entravam na fila e nunca eram gravados (o ramo desligado espera num `Event` sem gravador nem `finally`) | **aceito e corrigido.** O gravador (`meme-cycle-history`) agora é do `supervised()`, nos dois ramos, e o fechamento também. Teste pelo `run_meme` real: as duas linhas aparecem **enquanto o processo roda** e o cancelamento as fecha com `clean = true` |
| 3 | LOW | os 10 s do flush e os 3 s do close não são teto rígido (`asyncio.timeout` espera o cancelamento terminar; o cancelamento fora de banda do asyncpg não tem prazo — mais de 150 s com o banco em `docker pause`, medição do orquestrador) | **aceito e corrigido (o que cabe ao módulo).** A escrita roda numa tarefa que o flush **abandona** ao fim do orçamento (`asyncio.wait(timeout)`), contada em `cycle_history_abandoned_total`; no máximo uma escrita em voo (a seguinte espera a anterior dentro do orçamento, senão falha sem pegar outra conexão). Teste com um par que engole o cancelamento. Uma escrita abandonada que ainda confirma duplica linhas: já coberto pela deduplicação do leitor. O defeito de fundo — o docstring D3 de `hunter_core/db/session.py` diz que `command_timeout` limita o cancelamento e **não limita** — virou entrada em [[Open Bugs]] (dono `database-architect`/backend) |
| 4 | LOW | UUID v4 no `INSERT` contra a regra de v7 da aplicação; o precedente de `meme_decision_tapes` não autoriza em silêncio | **aceito como desvio declarado** em `docs/DATABASE.md` §73. Trocar por v7 não elimina as duplicatas (a PK é `(created_at, id)`), então o custo de gerar na aplicação não compra nada aqui |
| 5 | LOW | o docstring de `CYCLES_SINCE_SQL` dizia que atraso de persistência > 1 dia não exclui a linha, mas só havia limite inferior em `created_at` | **aceito.** Texto corrigido e limite superior `created_at < :until + 1 dia` acrescentado (teste de integração: linha persistida 2 dias depois da janela fica fora; a mesma linha numa janela alcançável é lida). Registrado o caso do relógio do worker adiantado mais de um dia |
| 6 | nit | leitores de `generation_*` | **escrito:** deduplicam por `(event, loop, run_id)` |

**Concorda / sem mudança:** sem índice novo antes de `EXPLAIN (ANALYZE, BUFFERS)` com volume representativo (**não medido**);
o `CancelledError` externo atravessa publicação, flush e esvaziamento (os `except Exception` não o pegam) — propagar não é terminar a
limpeza; fila limitada, `ack` por token e lotes de 500 conferidos. **Divergências:** nenhuma de fundo; escolhi o ramo "abandonar a
tarefa" do item 3 (o que ela preferiu) e a causa explícita (`clean`) em vez de drenar-e-omitir o item 1 (ambas as opções
dela). **Aprendizado de medição:** um certificado de término só vale se a **causa** viajar com ele; e um teste que chama
`close()` direto não prova o ciclo de vida — só o `run_meme` real (com `TaskGroup`) mostrou os dois defeitos.

**Conferência da correção (Astra, `code-reviewer`, 09/10/2026; bruto `.claude/state/astra-review-meme-cycle-lifecycle-r3.md`):**
REQUEST_CHANGES com 1 HIGH, 2 MEDIUM e 1 LOW; ela reproduziu três em memória. Decisões:

| achado | decisão |
|---|---|
| **HIGH.** Uma queda seguida de SIGTERM **durante o `finally`** do `_run` (fechando clientes): o `CancelledError` substitui o `ExceptionGroup` em voo e o `supervised()` gravava `clean = true` | **aceito e corrigido.** A causa é lembrada **antes** da limpeza: o `_run` chama `cycles.note_crash()` no `except BaseException` (se não for cancelamento) e o `supervised()` fecha com `clean = not crashed`. Teste `test_a_crash_followed_by_a_sigterm_during_the_cleanup_is_still_a_crash` (vermelho antes: `clean = true`) |
| **MEDIUM.** O gravador (fora do `TaskGroup`) podia morrer com uma exceção inesperada e o worker seguir sem gravar, a fila só descartando | **aceito e corrigido.** O gravador é um laço próprio que loga (`meme_cycle_history_writer_failed`) e tenta de novo, em vez do `collect.forever`. Teste `test_a_writer_that_raises_is_restarted_not_left_dead` (vermelho antes) |
| **MEDIUM.** O limite superior `created_at < until + 1 dia` exclui sem sinal um ciclo válido persistido depois de uma queda do banco > 1 dia (ex.: 26 h), sem `dropped_total` | **mantido como o pedido do `database-architect` (item 5), com a ressalva escrita — decisão do orquestrador.** A exclusão não é silenciosa para um leitor que cumpre o contrato: ela abre um **buraco de `seq`**, que é "buraco declarado" e tira a cobertura (a guarda fica não mensurável, nunca "passou"); só o buraco na **cauda** de uma geração fica invisível, e aí vale a ausência de `generation_end`. Se o orquestrador preferir nunca excluir, basta tirar a linha do limite superior (e o teste de integração que a prova): o custo é varrer as partições mais novas que a janela |
| LOW. O abandono por cancelamento externo não incrementa `abandoned_total` | **rejeitado:** o contador mede "abandonado ao fim do orçamento"; no cancelamento externo (desligamento) a escrita é cancelada e `CycleHistory.writing` mostra se ainda pende — o `drain` já a espera dentro do orçamento |
| Concorda: ACK só após sucesso observado e com o token do lote; commit tardio seguido de retry duplica fisicamente (dentro do contrato do leitor); o `drain` não abre outra escrita enquanto a anterior pende | registrado |

Relacionado: [[EXP-M26-grafico-em-moedas-maduras]] · [[06-DECISIONS/Revisoes-Astra/EXP-M26-unblock|EXP-M26-unblock]] ·
[[03-TRADING/Meme/README|Meme]] · [[06-DECISIONS/Revisoes-Astra/Index|Revisões da Astra]]
