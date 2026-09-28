## MUST-FIX

**O must-fix 2 ainda não está fechado como garantia geral. A fronteira específica da rodada 2 foi corrigida para sessões comuns, com atividade habilitada e privilégios efetivos.** Restam condições em que o export aceita uma prova incompleta.

**1. `MEMBER` não garante acesso efetivo às estatísticas.**

A checagem usa `pg_has_role(..., 'MEMBER')` ([export_h022.sql:30](C:/dev/project-hunter/infra/research/exp_m26/export_h022.sql:30)). No PG 16, associação ao papel pode existir sem herdar seus privilégios; o teste adequado aqui é `USAGE`. A implementação de `pg_stat_activity` verifica privilégios efetivos e oculta, entre outros campos, `xact_start` e `backend_type`. **O XID pode continuar exposto; isso não salva o filtro.** [Documentação de `pg_has_role`](https://www.postgresql.org/docs/16/functions-info.html), [implementação PG 16](https://raw.githubusercontent.com/postgres/postgres/REL_16_STABLE/src/backend/utils/adt/pgstatfuncs.c).

Cenário concreto: exportador não superusuário, membro de `pg_read_all_stats` com herança desabilitada, consultando uma escritora de outro papel:

1. Escritora carimba a mudança em **L−1s**, permanecendo dentro do commit.
2. Em **L**, a consulta de `pg_stat_activity` não recebe seu `backend_type`; o filtro a elimina. A meta declara `ve_toda_atividade=true` e mínimo nulo.
3. O snapshot dos dados ainda não vê a mudança; **export aceito**.
4. Em **L+1s**, a mudança fica visível.
5. Em **L+2s**, outro export aceito incorpora o carimbo ≤ L.

**Correção:** testar privilégios efetivos com `USAGE` e acrescentar a regressão sem herança. Isso não afeta o caso superusuário, mas quebra uma modalidade expressamente aceita pelo SQL.

**2. `min(xact_start)` confunde atividade desconhecida com ausência de escritoras antigas.**

O agregado ignora nulos, e `provar_visibilidade(None, ve_toda_atividade=True, ...)` aceita o export ([export_h022.sql:27](C:/dev/project-hunter/infra/research/exp_m26/export_h022.sql:27), [estado_token.py:50](C:/dev/project-hunter/infra/research/exp_m26/estado_token.py:50)).

No PG 16, uma sessão com `track_activities=off` deixa de atualizar o início da transação e pode apresentá-lo nulo, embora tenha XID. Isso ocorre mesmo quando o exportador é superusuário. [Fonte PG 16, `pgstat_report_activity` e `pgstat_report_xact_timestamp`](https://raw.githubusercontent.com/postgres/postgres/REL_16_STABLE/src/backend/utils/activity/backend_status.c).

Cenário concreto:

1. Escritora com atividade desabilitada carimba em **L−1s** e fica retida antes da visibilidade.
2. Em **L**, `pg_stat_activity` fornece XID, mas `xact_start=NULL`; `min` ignora essa escritora.
3. Snapshot dos dados anterior à visibilidade: **export aceito sem a mudança**.
4. Visibilidade em **L+1s**.
5. Export em **L+2s**: **aceito com a mudança**.

**Correção:** registrar separadamente escritoras cujo início seja desconhecido e recusar essa situação. Conferir apenas `track_activities` na sessão exportadora não comprova a configuração das outras sessões.

**3. A resistência ao recuo do relógio ainda não cobre o corte temporal.**

Ordenar por `id` corrige a escolha da última mudança, mas o filtro continua sendo `registrado_em <= leitura` ([estado_token.py:90](C:/dev/project-hunter/infra/research/exp_m26/estado_token.py:90)).

Cenário, em ordem real dos acontecimentos:

1. Um primeiro export após L consulta a atividade, tira o snapshot e é aceito.
2. Depois dele começa uma escritora, com `xact_start=L+2s`.
3. O relógio recua; o gatilho carimba **L−1s**.
4. Quando o relógio volta a L, outro export consulta a atividade. A escritora continua aberta, mas seu `xact_start=L+2s` **não bloqueia**.
5. Esse snapshot ainda não vê a mudança; depois vem a visibilidade.
6. Um export posterior aceita e inclui o carimbo ≤ L.

Portanto, a prova pressupõe que **não surjam novos carimbos ≤ L depois da consulta de atividade**, inclusive por recuo do relógio. A garantia incondicional escrita em [DATABASE.md:8747](C:/dev/project-hunter/docs/DATABASE.md:8747) precisa dessa restrição ou de outro mecanismo de corte.

## NICE-TO-HAVE

**(b) O argumento sobre ProcArray vale com condições, não como equivalência irrestrita.**

Para uma transação comum que já carimbou antes da consulta, continua em andamento e permanece invisível no snapshot posterior, o raciocínio está correto: o PG mantém seu XID ativo até a conclusão; `ProcArrayEndTransaction` ocorre depois de registrar o commit. A leitura de atividade é armazenada localmente por transação, e a separação dos comandos evita reutilizar essa leitura entre as duas transações. [Finalização no PG 16](https://raw.githubusercontent.com/postgres/postgres/REL_16_STABLE/src/backend/access/transam/xact.c), [remoção do XID ativo](https://raw.githubusercontent.com/postgres/postgres/REL_16_STABLE/src/backend/storage/ipc/procarray.c).

Os casos pedidos:

| Caso | Parecer |
|---|---|
| **Subtransação** | Não identifiquei furo próprio: atribuir XID ao filho também atribui aos ancestrais. O commit do filho não torna suas alterações visíveis externamente. |
| **XID apenas no commit** | Não contorna a prova para este histórico: a alteração de `meme_tokens` já exige XID antes do gatilho adiado. |
| **2PC** | **Furo se estiver habilitado.** `PREPARE TRANSACTION` executa os gatilhos adiados; depois a transação fica preparada sem continuar associada ao backend cliente. |
| **Backend diferente de `client backend`** | O filtro exclui um background worker que faça DML e execute esse gatilho. Não comprovei tal escritor no ambiente atual; a garantia precisa restringir ou abranger essa possibilidade. |

As regras de atribuição de XID e a execução dos gatilhos durante `PrepareTransaction` estão na [fonte PG 16](https://raw.githubusercontent.com/postgres/postgres/REL_16_STABLE/src/backend/access/transam/xact.c).

**Sequência exata do 2PC:** carimbo durante `PREPARE` em L−1s → preparação termina e a sessão desconecta → consulta de `pg_stat_activity` em L não encontra aquela escritora → snapshot dos dados não vê a alteração → export aceito → `COMMIT PREPARED` em L+1s dá visibilidade → export seguinte aceita outro estado. A transação preparada continua existindo; **estar no ProcArray não implica aparecer como cliente em `pg_stat_activity`**. [PREPARE TRANSACTION](https://www.postgresql.org/docs/16/sql-prepare-transaction.html).

Se `max_prepared_transactions=0` estiver comprovado, esse contraexemplo fica excluído; é o padrão do PG, mas não consultei o servidor para confirmá-lo. Preferiria comprovar essa restrição a ampliar informalmente o argumento. [Configuração de 2PC](https://www.postgresql.org/docs/16/runtime-config-resource.html#GUC-MAX-PREPARED-TRANSACTIONS).

**(d) Sim, há risco operacional de perder toda a janela.** Uma transação iniciada antes de L, com XID, pode bloquear os exports mesmo escrevendo outra tabela. Se permanecer aberta até L+1h, acaba a janela permitida ([export_h022.sql:27](C:/dev/project-hunter/infra/research/exp_m26/export_h022.sql:27), [leitura.py:273](C:/dev/project-hunter/infra/research/exp_m26/leitura.py:273)).

Por outro lado, **tráfego contínuo de transações novas não causa necessariamente recusa perpétua**: com relógio regular e L fixo, transações iniciadas depois de L não bloqueiam. Recomendo tentativas limitadas pela janela, diagnóstico dos bloqueadores sem texto de consultas e desfecho operacional explícito quando a prova não chega.

## O QUE FARIA DIFERENTE

Manteria os dois comandos e corrigiria a prova para falhar quando a observação estiver incompleta: `USAGE`, início desconhecido, restrição comprovada de 2PC e definição dos tipos de escritor admitidos. Acrescentaria regressões para essas condições.

**(c) Aceito “carimbado até L” como convenção própria da H-022, desde que ela seja assumida como tal.** Ela permite usar posteriormente um valor cujo gatilho executou antes de L, mas que nenhum leitor externo conseguia consultar em L. Não equivale a disponibilidade operacional em L.

Com relógio regular, um valor recebido e registrado somente depois de L fica fora pelo filtro atual. Porém, a frase **“nada ocorrido depois de L entra”** é excessiva: o sucesso final da transação pode ocorrer depois de L, e o recuo do relógio permite até carimbar dados posteriores abaixo do corte. Eu substituiria essa afirmação por uma definição precisa e suas premissas ([protocolo_h022.txt:63](C:/dev/project-hunter/infra/research/exp_m26/protocolo_h022.txt:63), [DATABASE.md:8752](C:/dev/project-hunter/docs/DATABASE.md:8752)).

## CONCORDO COM

- **A regressão da fronteira está bem direcionada:** afirma carimbo ≤ L, ausência no snapshot intermediário, recusa desse export e aceitação posterior ([test_migration_0067_visibility.py:172](C:/dev/project-hunter/packages/core/tests/integration/test_migration_0067_visibility.py:172)).
- **Ordenar por `id`** corrige a divergência artificial causada pela ordenação por relógio ([estado_token.py:90](C:/dev/project-hunter/infra/research/exp_m26/estado_token.py:90)).
- **Ignorar o evento quando o token já foi apagado** resolve o cenário apontado da FK; há regressão específica ([meme_token_state_history.py:118](C:/dev/project-hunter/infra/migrations/ddl/meme_token_state_history.py:118), [test_migration_0067.py:289](C:/dev/project-hunter/packages/core/tests/integration/test_migration_0067.py:289)).
- **Recusar antes da inferência** é o comportamento adequado quando falta prova ([leitura.py:278](C:/dev/project-hunter/infra/research/exp_m26/leitura.py:278)).

**Verificação:** revisão estática dos arquivos e da fonte oficial do PG 16; não executei testes nem migrações. Nenhum arquivo modificado, nenhum commit e nenhuma leitura de `.env`.

## OBSIDIAN

- **EXP-M26 — gráfico em moedas maduras:** registrar a fronteira corrigida e as condições ainda necessárias para fechar o must-fix 2.
- **Diálogo — EXP-M26:** distinguir “carimbado até L” de “visível em L” e explicitar a premissa de relógio.
- **Revisões-Astra — token-state-history, rodada 3:** registrar os contraexemplos de privilégios, atividade desabilitada, 2PC e recuo do relógio.