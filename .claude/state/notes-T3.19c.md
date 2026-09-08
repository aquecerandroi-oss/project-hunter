# Notas T3.19c — `0012_replication`: a coorte, o carimbo e a linhagem viraram schema

Base: `main` em `6878c8b` (durante a tarefa outro agente commitou `84bc4ec`; nada meu foi commitado).
**Nada commitado.** Caminhos tocados: `infra/migrations/{versions/0012_replication.py,ddl/replication.py}`,
`packages/core/hunter_core/{domain/enums.py,db/models/agents.py}`,
`packages/core/tests/integration/{test_migrations.py,test_schema_privileges.py}`,
`services/strategy-worker/hunter_strategy_worker/{catalogue,decide,replication,replication_derive,replication_stats}.py`,
`services/strategy-worker/tests/{test_replication_cohort.py,test_replicate_strategy_version.py}`,
`infra/scripts/replicate_strategy_version.py`, `docs/DATABASE.md` (§16.3, §17.6, §24 novo),
`docs/plans/REPLICATION.md` (§1.6, §1.7, §4.1, §4.3, §4.4).
Nenhum arquivo de outro agente foi editado (`activate_strategy_version.py`, `activation_db.py`,
`services/execution-worker/**`, `apps/**`, `obsidian/**`, `test_activate_paper_line.py` intocados).

---

## 1. Contrato para a T3.18 (o placar) — a entrega 3 do brief, sem ligar a API

A API **não foi ligada** nesta tarefa, como o brief mandou. O contrato, em três linhas:

```sql
-- o bloco "fora da amostra" conta a partir daqui, e a coluna é a fonte
SELECT promising_at, promising_by FROM strategy_versions WHERE id = :version_id;
```

- **Ler:** `strategy_versions.promising_at` direto. `NULL` significa "a versão nunca foi
  `validada`" → veredito de replicação `none` (REPLICATION.md §5). Nunca inferir o marco de outra
  coisa: `system_events` expira em 30 dias e o `changelog` é texto livre.
- **Compatibilidade:** `hunter_strategy_worker.replication_stats.load_promising_at(conn, id)`
  continua sendo o caminho seguro se a API não puder depender do worker — ele agora lê a **coluna**
  primeiro, depois o `changelog` das irmãs, depois o evento. Uma família replicada antes da `0012`
  (não existe nenhuma em produção) continua legível.
- **Escrever:** só `hunter_strategy_worker.replication.mark_promising(conn, version_id,
  verdict_source)`, na conexão de dono (`DATABASE_URL_MIGRATIONS`). A API **não pode** escrever a
  coluna (`hunter_app` tem só `SELECT`) e isso é deliberado: quem carimba é quem roda a régua, não
  um request handler. Se um dia o placar precisar carimbar sozinho, é rota de operador + a mesma
  função, nunca um `UPDATE` novo.
- **`promising_by`** é a string do veredito que carimbou, 1..64 caracteres. Hoje o único escritor
  grava `replicate_strategy_version:validada`. Se a T3.18 passar a carimbar, use
  `lab_scoreboard:validada` (ou o nome da regra) — a tela pode mostrar isso ao lado da data.
- **Irmãs no placar:** continuam sendo linhas próprias de `strategy_versions`, agora encontráveis
  por **coluna** em vez de `LIKE` no `changelog`:
  `WHERE replication_parent_id = :pai ORDER BY replication_index`. `load_sibling_rows` já faz isso
  (e ainda aceita o rótulo antigo).

O resto do payload do bloco `replication` não mudou: `notes-T3.19.md` §1 e REPLICATION.md §6
continuam válidos palavra por palavra.

---

## 2. O que a migração faz (resumo; a íntegra está em `docs/DATABASE.md` §24)

| # | O quê | Onde |
|---|---|---|
| a | `ck_shadow_episodes_cohort_format` aceita `replication:<uuid>:<k>`, `k` `[1-9][0-9]?` (1..99); `prospective` e `replay:<uuid>` **byte a byte** iguais | §24.1 |
| b | `strategy_versions.promising_at timestamptz NULL` + `promising_by text NULL`, com CHECK bicondicional e 1..64 caracteres | §24.2 |
| c | `strategy_versions.replication_parent_id uuid NULL` (FK para a própria tabela, `NO ACTION`) + `replication_index smallint NULL`, CHECK (bicondicional, 1..99, `parent <> id`) e `UNIQUE (parent, index)` | §24.3 |
| d | trigger de congelamento alargada: a **linhagem** congela depois da ativação, o **carimbo não** (é escrito depois da ativação por definição) | §24.4 |
| e | **nenhum grant** — `0010`/`0011` já deixaram o worker com `SELECT` de tabela e cinco colunas de `UPDATE`, então uma coluna nova nasce ilegível para escrita. Provado como o papel, não declarado | §24.5 |
| f | downgrade recusa em três frentes: `promising_at`, `replication_parent_id`, coorte `replication:%` em `shadow_episodes` | §24.6 |

E do lado do código: `ActiveVersion.cohort(process_cohort)` carimba o braço quando a versão tem
linhagem; `decide.py` calcula a coorte **uma vez** por decisão e a usa nos quatro lugares (slot,
identidade do sinal, envelope, episódio); `replicate()` grava a linhagem no mesmo `INSERT` que ativa
a irmã e chama `mark_promising` antes de escrever as irmãs (elas citam o carimbo).

---

## 3. Decisões que tive de tomar (não vinham do brief)

| Decisão | Valor | Por quê |
|---|---|---|
| Teto de `k` | 99, escrito como `[1-9][0-9]?` | o brief pediu 1..99. Escrever a **forma** e não a contagem de dígitos recusa `:0` e `:01` — `:01` seria uma segunda grafia do braço 1, isto é, uma segunda população sob um nome que o relatório já usa |
| Replay de uma irmã | continua `replay:<run>` | coortes separam populações da **mesma** versão; um replay nunca é a avaliação prospectiva reservada dela (SHADOW-LAB.md §1), e colapsar os dois poria um replay no slot que `uq_shadow_episodes_slot` guarda para a corrida para a frente |
| `promising_at` congelado? | **não** | é escrito depois da ativação por definição; congelá-lo tornaria a coluna inescrevível em toda linha que poderia ganhá-la. A linhagem **é** congelada, porque a irmã nasce com ela |
| `ON DELETE` da FK do pai | `NO ACTION` (padrão) | `RESTRICT` quebraria `DELETE FROM strategies` (a cascata leva pai e irmãs no mesmo statement, e `RESTRICT` dispara imediatamente). `NO ACTION` é verificada no fim do statement: a família cai junta, o pai sozinho não. Precedente: `participation_consumptions` (§18.5) |
| `promising_by` obrigatório junto do carimbo | CHECK bicondicional, 1..64 | um carimbo que ninguém atribui é uma data. O `NOT NULL` sozinho aceitaria string vazia (argumento do §16.2) |
| Índice para a FK | nenhum novo | `UNIQUE (replication_parent_id, replication_index)` já começa pela coluna da FK — é o índice que o §1 exige |
| Nenhum `REVOKE` na `0012` | afirmação + teste | um `REVOKE` no-op *pareceria* garantia; é o erro que o §15.6 registra sobre `ALTER DEFAULT PRIVILEGES`. A garantia é `test_the_worker_cannot_write_any_of_the_replication_columns` |
| `mark_promising` mora em `replication.py` | sim (o brief pediu ali) | e `Sibling`/`derive_siblings`/`sibling_changelog` saíram para `replication_derive.py` porque o módulo passou de 350 linhas (`check_file_size.py`). A costura é real: aquilo **deriva**, isto **conduz a rodada** |
| `load_sibling_rows` lê coluna **ou** rótulo | as duas | a coluna é a verdade; o `LIKE` cobre uma irmã derivada antes da `0012`. Só uma delas faria dessa irmã ou uma órfã (só coluna) ou uma linha sem constraint (só rótulo) |

---

## 4. Desvios em relação ao que os documentos diziam (os dois estão reescritos)

1. **`docs/plans/REPLICATION.md` §4.3 dizia "o pai não é tocado — nenhum UPDATE, nenhum campo".**
   Passa a ser falso por desenho: `promising_at`/`promising_by` são do pai. A frase valia enquanto
   o carimbo morava no `changelog` das irmãs, que era exatamente o problema da CONCERN 1. §4.3 e
   §4.4 reescritas; o resto do pai continua intocado (nem `changelog`, nem `status`, nem
   parâmetros), e o carimbo nunca se move depois de escrito.
2. **`docs/DATABASE.md` §16.3** descrevia o CHECK da coorte com dois ramos. Ganhou um ponteiro para
   §24.1 (a revisão `0002` continua descrevendo o que a `0002` fez — o padrão de §16.5/§17.1).
3. **`.claude/state/notes-T3.19.md` §2, pendências 1 e 2:** fechadas. A 3 (custo operacional de dez
   irmãs) e a 4 (PBO/CSCV, Deflated Sharpe, Reality Check) continuam abertas e **não** são desta
   tarefa.

---

## 5. Concerns

1. **`services/strategy-worker/tests/test_shadow_decisions.py` está vermelho no head, e não fui
   eu.** Os 15 testes erram no fixture com *permission denied for table strategy_versions*:
   `builders.isolate_catalogue()` faz `UPDATE strategy_versions SET status = ...` dentro de um
   `role_session(db_role="hunter_worker")`, e a `0011_strategy_activation_owner` (T3.15c, já
   commitada) revogou `UPDATE (status)` desse papel. Reproduzido com a árvore limpa desses arquivos
   (nenhum deles está no meu diff). **O conserto é uma linha** — chamar `isolate_catalogue` na
   conexão de dono, como fiz no meu próprio fixture (`test_replication_cohort.py`) —, mas
   `.claude/state/brief-T3.15d-owner-dsn.md` sugere que a T3.15d é dona exatamente desse assunto,
   então não toquei. Quem pegar: `test_shadow_decisions.py::shadow_db` e qualquer outro fixture que
   chame `isolate_catalogue` como worker.
2. **A `0012` toma `ACCESS EXCLUSIVE` em duas relações e uma delas é validante.** O
   `DROP`/`ADD CONSTRAINT` do CHECK da coorte varre `shadow_episodes` (uma linha por versão ×
   mercado × coorte). Na VPS de hoje são milhares de linhas — mesma ordem da janela de ~15 s que a
   `0010` abriu (§15.6), não uma classe nova de risco. Se algum dia `shadow_episodes` crescer uma
   ordem de grandeza, a saída é `ADD CONSTRAINT ... NOT VALID` + `VALIDATE CONSTRAINT`, que não foi
   feita agora porque o custo não justifica a complexidade.
3. **A coorte da irmã muda o `signal_id` dela.** `identity.signal_id` inclui a coorte, então uma
   irmã que já tivesse emitido como `prospective` passaria a emitir com identidade nova para a mesma
   barra. **Não existe família replicada em produção** (`notes-T3.19.md` §4: nenhuma das duas
   versões ativas é candidata), então o efeito hoje é zero — mas se alguém replicar antes de
   aplicar a `0012` em um ambiente e depois aplicar, aquela irmã terá duas populações. A recusa que
   `replicate()` faz sem a `0012` aplicada existe para tornar isso impossível daqui para a frente.
4. **`apps/api/hunter_api/routers/lab.py` usa `SHADOW_COHORT_PATTERN` como `pattern` de query.**
   Alargar o padrão faz a rota aceitar `replication:<uuid>:<k>` como filtro de coorte — o
   comportamento desejado, e é só filtro (nenhuma escrita). Não editei `apps/**`; registro aqui
   porque o efeito é real e não passou por revisão de front.
5. **`--force-research` continua sem carimbo**, então um pai forçado não tem `promising_at` e o
   bloco 1 do protocolo fica sem marco para ele — por desenho (REPLICATION.md §4.1). Quem quiser
   avaliar fora da amostra um pai forçado tem de carimbá-lo explicitamente com `mark_promising`,
   nomeando a fonte, e isso é um ato auditado.

---

## 6. O que revisar depois de mim

- **risk-engine-guardian:** o isolamento da coorte — que a terceira barreira de fato morde
  (`bridge_screen` recusa `cohort_not_live`) e que nada no caminho `replicate` → `strategy_versions`
  → sinal pode virar entrada. A irmã continua `research_only`, sem linha em `agents`, e agora com
  coorte própria.
- **security-reviewer:** os grants — a afirmação da §24.5 é que a `0012` não emite `GRANT`/`REVOKE`
  nenhum e que isso basta por subtração das ACLs da `0010`/`0011`. A prova está em
  `test_schema_privileges.py`; vale reproduzir como o papel.
- **Sexta-feira:** o texto de REPLICATION.md §4.3/§4.4 (a frase "o pai não é tocado" mudou) e uma
  `EXP-` quando a primeira replicação de verdade rodar.
