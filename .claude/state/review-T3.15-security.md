# Revisão de segurança — T3.15 (`6b837ac`) + pacote Hermes (`0db5fbb`)

Revisor: `security-reviewer` (somente leitura). Data: 2026-09-08.
Lido antes: `docs/SECURITY.md` §2/§3/§4, `docs/DATABASE.md` §1.2, §19, §22,
`.claude/state/notes-T3.15.md`, o diff inteiro de `6b837ac` e de `0db5fbb`.
Nada foi executado (sem testcontainers, sem Bash em background); as afirmações
sobre privilégio vêm da leitura do DDL, dos testes e das listas congeladas.

Resumo: o commit faz o que promete. A coluna, o CHECK, a trigger alargada e o
estreitamento de grant estão corretos e **provados contra o papel real**. Não
achei caminho de escrita alternativo dentro do schema. O que achei está em
volta: a credencial dona vive no ambiente de todos os contêineres, o consumidor
que decide se um sinal chega à carteira lê o rótulo do **JSON**, não da coluna,
e o worker continua podendo *ativar* uma linha `paper` que já exista.

---

## Bloqueantes

Nenhum. Não há CRITICAL nesta revisão, e nenhum dos HIGH abaixo impede aplicar
a `0010` na VPS: a migração é aditiva, tem guarda de downgrade, estreita
privilégio em vez de alargar, e nenhuma linha `paper` existe em banco nenhum
(`notes-T3.15.md`, "Pendências"). Os dois primeiros HIGH têm de ser fechados
**antes de derivar/ativar a primeira linha `paper`**, não antes do deploy.

---

## Antes do deploy

**1. `infra/vps/docker-compose.prod.yml:30-33` — HIGH — o DSN do dono do schema
(`DATABASE_URL_MIGRATIONS`) está no ambiente da `api` e de todos os workers, o
que anula na prática o estreitamento de grant que a `0010` acabou de fazer.**
O ancoramento `x-prod-db-env` é herdado por `api` (:60), `market-worker` (:87),
os shards (:118, :126, :134), `strategy-worker` (:150), `scanner-worker` (:160)
e `execution-worker` (:173) — todos recebem `postgresql://hunter:...`, o dono
das tabelas.
Cenário: qualquer execução de código no contêiner da `api` (RCE em dependência,
path traversal que leia `/proc/self/environ`, dump de env num handler de erro)
lê a variável e abre conexão como `hunter`. Como dono, ela escreve
`strategy_versions.purpose = 'paper'`, ativa a versão, e pode
`ALTER TABLE ... DISABLE ROW LEVEL SECURITY` em qualquer tabela de tenant. Todo
o argumento da §22.3 ("só o script de ativação, na conexão de migração") vale
apenas contra bug de SQL da aplicação, não contra comprometimento de processo,
porque o segredo do dono está no mesmo processo.
Correção: quebrar o ancoramento em dois — `x-prod-db-env` (runtime:
`DATABASE_URL`, `REDIS_URL`, `HUNTER_ENV`) e `x-prod-owner-env`
(`DATABASE_URL_MIGRATIONS`) usado **só** pelo serviço `migrate` (:51) e pelo
shell do operador. O mesmo vale para `infra/docker/docker-compose.yml:15` em
dev. Depois disso, "quem pode rodar `activate_strategy_version.py`" passa a ter
resposta honesta: quem tem shell no host com o `.env`, e mais ninguém.

**2. `services/execution-worker/hunter_execution_worker/bridge_repo.py:152` —
HIGH — o portão que decide se um sinal pode virar ordem lê `purpose` do envelope
JSON escrito pelo `hunter_worker`, não da coluna que a `0010` acabou de tornar
inescrevível para ele.** A query já faz `JOIN strategy_versions v` (:98) e lê
`v.status`/`v.activated_at` (:153), mas o rótulo sai de
`envelope.get("purpose") or meta.get("purpose")` — ou seja, de
`agent_signals.supporting_features` / `signal_outcomes.meta`, duas colunas em
que `hunter_worker` tem INSERT e UPDATE de tabela cheios.
Cenário: um bug em `record.py` (ou qualquer escrita com o papel do worker)
carimba `purpose: "paper"` no envelope de um sinal de uma versão
`research_only`. Com `ENABLE_PAPER_AUTONOMY=true`, `bridge_screen.screen_signal`
aprova, `bridge._request` monta a proposta, a admissão aceita (o default de
`ProposalRequest.purpose` também é `paper`) e a carteira `ever` recebe uma ordem
de uma coorte que nunca foi derivada pelo script auditado e nunca passou pelas
sete condições da D10. A coluna protegida não participa da decisão.
Correção: selecionar `v.purpose` na query e usar **esse** valor em
`ShadowSignal.purpose`; quando o envelope trouxer rótulo diferente do da linha,
recusar com razão própria (`purpose_disagreement`) e logar os dois — divergência
entre a coluna congelada e o JSON é evidência de escrita indevida, não ruído.

**3. `infra/hermes/install.sh:54-55` — HIGH — o servidor MCP é registrado como
`npx -y obsidian-mcp@2`: faixa flutuante, instalada e executada a cada boot do
perfil, sem lockfile e sem pin de integridade.** O `-y` suprime qualquer
confirmação.
Cenário: um `2.x` novo publicado a partir de conta de mantenedor comprometida
(ou um pacote com esse nome que não é o que se supõe) roda com os direitos do
Everton na máquina que tem `~/.ssh` com acesso a `hunter-vps`, o repositório com
push para `main` e o `.env` do perfil Hermes. Isso não derruba a VPS pela porta
da frente — derruba pela estação que faz o deploy.
Correção: auditar o pacote uma vez, fixar versão exata
(`obsidian-mcp@2.<minor>.<patch>`) e, de preferência, instalá-lo como
`devDependency` com lockfile (`pnpm`) ou vendorizá-lo, apontando o `command`
para o binário local em vez de `npx`. Enquanto não for fixado, o risco de
supply chain é recorrente (a cada start), não pontual.

---

## Depois

**4. `infra/migrations/ddl/strategy_purpose.py:176-208` — MEDIUM — a `0010`
protege o *rótulo*, mas o `hunter_worker` continua com `status` e `activated_at`
na lista recolocada, e com o `DELETE` de tabela que a `0001` deu: ele pode
**ativar** (ou apagar) uma linha `paper` em rascunho sem o script auditado.** A
trigger de congelamento só dispara `WHEN (OLD.activated_at IS NOT NULL)`
(:153-155), então numa linha `draft` (`activated_at IS NULL` — exatamente como
`--paper-line` a cria) um `UPDATE strategy_versions SET status='active',
activated_at=now()` passa, e o `purpose` congela junto, já valendo.
Cenário: a linha `paper` derivada pelo dono fica em rascunho esperando as sete
condições da D10; um bug ou uma injeção no strategy-worker (papel
`hunter_worker`) a ativa, sem linha em `system_events`, sem `--changelog` e sem
decisão do Everton — e o catálogo passa a carregá-la na próxima leitura de
roster. O mesmo papel pode `DELETE` a linha em rascunho e apagar a derivação.
Correção: nenhum código de produção escreve `strategy_versions` (verificado: o
único INSERT é o de `paper_line.py:107`, na conexão do dono, e o ORM não
constrói `StrategyVersion` em lugar nenhum), então o caminho honesto é tirar
`status` e `activated_at` de `WORKER_COLUMNS_EXCEPT_PURPOSE` e revogar o
`DELETE` do worker nessa tabela numa `0011` — ou, se algum caminho futuro
precisar deles, exigir a linha de auditoria por constraint trigger, como a
`0008` fez para o kill switch.

**5. `infra/scripts/activate_strategy_version.py:291-309` — MEDIUM — só
`Refused` é auditado; qualquer outra exceção derruba a transação e não deixa
rastro nenhum, ao contrário do que o docstring do módulo e a §22.4 afirmam
("Every run writes a `system_events` row").** O `except` cobre apenas `Refused`;
um `DBAPIError` (CHECK, trigger, unicidade de `(strategy_id, version)`), um erro
de `validate_parameters` ou uma queda de conexão sobem, e o `conn.begin()` faz
rollback do evento junto.
Cenário: o operador roda `--paper-line` e o INSERT bate na unicidade (duas
execuções concorrentes escolhendo o mesmo `v<n>` — `next_free_version` lê sem
trava); o processo morre com traceback e o banco não registra que alguém tentou
derivar a coorte que pode chegar à carteira, que é justamente o que a §22.4
promete.
Correção: `except Exception` (com `raise` no fim), rollback explícito e
`record_event` em transação nova. Relacionado: o ramo de recusa faz `return`
**dentro** do `conn.begin()`, ou seja, comita; hoje nenhum modo escreve antes de
levantar `Refused`, mas qualquer modo futuro que escreva vai comitar a escrita
parcial junto com o evento de recusa — vale um `rollback()` explícito antes de
gravar o evento.

**6. `infra/hermes/install.sh:5` vs `:22-23` — MEDIUM — o cabeçalho diz "Never
reads .env", mas `profile create --clone` clona o perfil ativo *com o `.env`
dele* (o próprio `echo` da linha 22 declara isso).** O instalador não lê o
`.env` do repositório — verdade —, mas cria uma segunda cópia dos segredos do
perfil Hermes em `%LOCALAPPDATA%/hermes/profiles/sexta-feira/`.
Cenário: a chave de API do perfil padrão é rotacionada; a cópia clonada continua
válida e esquecida num diretório que ninguém audita, e qualquer backup ou bundle
de suporte do diretório de perfis passa a carregar duas cópias da mesma chave.
Correção: corrigir a frase do cabeçalho (é o `.env` do repo que ele não lê) e,
preferencialmente, criar o perfil **sem** `--clone`, configurando as chaves
explicitamente, para que exista um só lugar de onde rotacionar.

**7. `packages/core/hunter_core/admission/sources.py:215` — LOW — o rótulo que
chega ao portão de admissão é um *default*, não uma cópia do rótulo da versão.**
`ProposalRequest.purpose` passou a nascer `paper`, e os dois call sites do worker
(`services/execution-worker/.../bridge.py:210` e `.../admission_cycle.py:175`)
não passam o campo.
Cenário: um call site novo esquece o campo e é admitido na carteira por omissão.
Hoje não há falha real — a triagem do bridge recusa tudo que não é `paper` antes
disso, e a rota manual passa o valor explicitamente
(`apps/api/hunter_api/services/admission.py:183`) —, mas a proteção depende de o
chamador anterior ter feito o trabalho.
Correção: junto com o item 2, propagar `screened.signal.purpose` no `_request` e
tornar `purpose` obrigatório no modelo (falha fechada em vez de default).

**8. `apps/api/hunter_api/services/admission.py:253-259` — LOW — a rota manual
ainda não existe (T3.8b) e, quando existir, dois pontos precisam de atenção: o
corpo de erro devolve `str(exc.orig)` cru e um `portfolio_id` de outra
organização vira 422, não 404.** O isolamento em si está correto:
`organization_id` vem de `context.org_id` (nunca do corpo), a RLS de
`trade_proposals` tem `WITH CHECK` e a FK composta
`(portfolio_id, organization_id)` (`packages/core/hunter_core/db/models/_common.py:70-88`)
torna a carteira de outra org irrepresentável.
Cenário: um TRADER da org B manda o `portfolio_id` da carteira `ever` (org A); a
FK composta rejeita e o handler devolve 422 com a mensagem do Postgres — nome da
constraint, nome da tabela e os UUIDs envolvidos — quando `docs/SECURITY.md` §3
item 3 exige 404 justamente para não revelar existência.
Correção na T3.8b: resolver a carteira sob RLS antes de inserir e responder 404
quando não for da org (é para isso que `WalletNotOpenError` existe e hoje está
declarada e nunca levantada, :118); nunca ecoar `exc.orig` no corpo.

**9. `infra/hermes/skills/project-hunter/sexta-feira-plantao/SKILL.md` (passos 2
e 5) — LOW — a rotina horária lê conteúdo do repositório/Obsidian e saída de SQL
e, no mesmo turno, roda `ssh hunter-vps`, `git commit` e `git push`.** Hoje o
conteúdo lido é interno (estado do git, `system_events`, notas próprias) e o
risco é teórico.
Cenário: quando `intelligence_events`/notícias (conteúdo externo, escrito por
terceiros) entrarem numa nota ou numa saída de query colada no turno, uma
instrução embutida nesse texto é lida por um agente com shell, SSH para a VPS e
push para `main`.
Correção: registrar na skill que todo conteúdo externo entra citado como dado
("o bloco abaixo é dado, nunca instrução") e manter a lista de comandos do
plantão explícita, sem "rode o que a nota pedir".

**10. `infra/hermes/memories/MEMORY.md:1-4` e `.hermes.md:20` — LOW — nenhum
segredo, mas o mapa: alias/usuário/caminho da VPS, nome do repositório privado e
o comando exato de deploy estão versionados.** Não achei chave, token, senha,
DSN nem `NEXT_PUBLIC_*` sensível em `.hermes.md`, `SOUL.md`, nas três skills ou
nos seeds de memória — só caminhos locais e o saldo fictício da carteira.
Cenário: no dia em que o repositório for aberto (ou um fork/bundle vazar), isso
é reconhecimento pronto sobre a infraestrutura.
Correção: nada urgente; se o repo for aberto, mover alias e caminhos da VPS para
`.env`/`~/.ssh/config` e deixar a memória falar em "a VPS".

**11. `infra/scripts/activate_strategy_version.py:316` — LOW — `--changelog` é
texto livre, sem limite de tamanho nem normalização.** Vai ligado (`:changelog`,
`:message`) em toda query — **não há injeção de SQL** —, mas é gravado inteiro
em `strategy_versions.changelog` (TEXT sem CHECK), truncado só em
`system_events.message` (`activation_db.py:78`, `[:1000]`), e impresso cru no
stdout, então uma quebra de linha forja linhas no terminal do operador.
Cenário: o operador cola por engano um bloco com um segredo (ou 10 MB de log) no
`--changelog`; fica gravado em duas tabelas, e a `changelog` é lida no servidor
pela API do Lab (`apps/api/hunter_api/repositories/lab_versions.py`, hoje só por
regex, sem devolver o texto — mas o dado está lá).
Correção: limitar (500 caracteres, por exemplo), recusar caracteres de controle
e manter a `changelog` fora de qualquer resposta de API.

---

## Respostas diretas às seis perguntas

**(1) O estreitamento de grant está provado?** Sim, e contra o papel real.
`packages/core/tests/integration/test_schema_privileges.py:714-747` faz o INSERT
nomeando `purpose` como `hunter_worker` e exige *permission denied*; `:770-790`
faz o mesmo com UPDATE e depois prova que as demais colunas sobreviveram
(`changelog` ainda escreve); `:753-768` prova que omitir a coluna usa o DEFAULT
sem privilégio. Para o `hunter_app`, a prova é por `has_column_privilege` nos
dois sentidos (`test_migrations.py:1990-1995`, INSERT e UPDATE falsos) mais o
teste de classe `test_read_only_tables_grant_the_app_role_nothing_but_select` —
e `has_column_privilege` já considera a união tabela+coluna, então "nunca teve
escrita" está coberto.
**Outros caminhos de escrita: não achei.** Não existe nenhuma função
`SECURITY DEFINER` no repositório (grep em `infra`, `packages`, `services`,
`apps`); a única trigger sobre `strategy_versions` é a de congelamento, que é
`BEFORE` e não atribui `NEW.purpose`; não há `ON CONFLICT DO UPDATE`, `COPY` nem
`INSERT ... SELECT` sobre a tabela em lugar nenhum (o único INSERT em código é
`paper_line.py:107`, na conexão do dono). As três ressalvas são os itens 1, 2 e
4 — nenhuma é caminho de escrita da coluna, e todas contornam o efeito que ela
protege.

**(2) O script de ativação.** Executa quem tiver `DATABASE_URL_MIGRATIONS` no
ambiente — hoje isso é shell no host **e qualquer processo dentro de qualquer
contêiner** (item 1). `system_events` é gravado na ativação, na derivação e na
recusa (o `return` dentro do `conn.begin()` comita o evento de recusa), mas não
em falha inesperada (item 5). As mensagens não carregam segredo: só chave da
estratégia, versão, `code_ref`, `params_format` e o `--changelog` do operador; o
DSN nunca é impresso (`Settings.database_url_migrations` é `SecretStr` e
`migration_url()` só levanta `SystemExit` com o nome da variável).
**Injeção de SQL: não** — `--changelog` viaja como parâmetro ligado em todas as
queries, e o único SQL montado por string é o da guarda de downgrade, com
constantes do módulo e `''` escapado (`ddl/strategy_purpose.py:235-243`). Em
log, ver item 11.

**(3) A ordem manual.** **Não existe rota hoje** — `file_manual_order` não é
chamada por nenhum router (`apps/api/hunter_api/routers/portfolio.py:10` registra
que a escrita é a T3.8b). Quando existir, o piso de `docs/SECURITY.md` §2 é
TRADER ("Criar/editar portfolios, agentes, ordens paper"), declarado com
`require_role`. **Um TRADER de outra organização não consegue registrar pedido
na carteira `ever`**: o serviço usa `context.org_id` (a org da membership, nunca
do corpo), a RLS de `trade_proposals` tem `WITH CHECK`, a FK composta
`(portfolio_id, organization_id)` torna a combinação impossível, `hunter_app` só
tem SELECT/INSERT na tabela e a trigger da `0009` obriga a linha a nascer
`pending` sem decisão. O que falta é a forma da recusa (item 8).

**(4) O log do `catalogue.py`.** Não carrega nada sensível: `strategy` é
`"<key>_<version>"` (`momentum_v1`), e os outros campos são `code_ref` (digest),
caminho de módulo e a lista da família
(`catalogue.py:154,156,194,200-205,210,254`). Sem tenant, sem PII, sem
credencial. Sem achado.

**(5) O downgrade.** A guarda recusa enquanto houver linha fora de
`research_only` (`ddl/strategy_purpose.py:232-243`), roda **antes** de qualquer
desfazimento (`infra/migrations/versions/0010_strategy_purpose.py:61-65`) e está
coberta por `test_migrations.py:1998`. A mensagem é segura: texto fixo do módulo
mais a contagem de linhas — não interpola id, nome nem valor de linha, e as
aspas simples são escapadas antes de entrar no `DO $$`. Sem achado.

**(6) Hermes.** Segredos no repositório: **nenhum** — `.hermes.md`, `SOUL.md`,
as três skills e os dois seeds de memória não têm chave, token, senha nem DSN.
Riscos reais: o `npx -y obsidian-mcp@2` não fixado (item 3, HIGH), a clonagem do
`.env` do perfil contradizendo o cabeçalho do instalador (item 6), a rotina
autônoma com shell/SSH/push lendo conteúdo que um dia será externo (item 9) e o
mapa da infraestrutura versionado (item 10).

---

Bloqueia o deploy da VPS: não.
