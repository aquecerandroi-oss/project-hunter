# Notas T3.15d — a DSN de dono só chega a `migrate` e ao novo serviço `ops`

Executado por devops-engineer em 2026-09-08. Base `main` em `7b0edeb`. Não
commitado (instrução do orquestrador). `git status` nos dois compose files
estava limpo antes de eu começar (T3.0f já tinha aterrissado).

## O que mudou

**`infra/vps/docker-compose.prod.yml`** — `x-prod-db-env` perdeu
`DATABASE_URL_MIGRATIONS`; nova âncora `x-prod-owner-env` carrega só essa
variável. `migrate` passou a usar `<<: [*prod-db-env, *prod-owner-env]`
(precisa das duas: `alembic/env.py` constrói um `Settings()` completo, que
lê `DATABASE_URL`/`REDIS_URL`/`HUNTER_ENV` também, não só a DSN de dono).
Novo serviço `ops` (`profiles: ["ops"]`, `entrypoint: []`, `command:
["true"]`, mesmas duas âncoras, `env_file: ../../.env` explícito — sem
contraparte na base para herdar essa lista por concatenação — e
`depends_on: postgres: service_healthy`).

**`infra/docker/docker-compose.yml`** — mesma cirurgia: `x-api-env` perdeu
`DATABASE_URL_MIGRATIONS`; nova âncora `x-owner-env`. `migrate` ganhou
`<<: [*api-env, *owner-env]`. Novo serviço `ops`, mesma forma do da VPS
(`profiles: ["ops"]`, `entrypoint: []`, `command: ["true"]`, `env_file`
próprio, `depends_on: postgres`).

Nenhum outro serviço mudou (o `x-prod-logging`, o `ipam`/`ip_range` fixo do
T3.28a/d, o `cap_drop` dos workers — tudo preservado). `api`, `market-worker`
(e os sete shards/spot), `scanner-worker`, `strategy-worker`,
`execution-worker` continuam com todo o resto do ambiente, só sem
`DATABASE_URL_MIGRATIONS`.

**`docs/DEPLOYMENT.md`** — nova §3.4 explicando a separação, o serviço `ops`
e os dois comandos de invocação (dev: `docker compose ... run --rm ops`; VPS:
`bash infra/vps/compose.sh run --rm ops ...` — o `*)` fallback do
`compose.sh` já repassa qualquer subcomando com `--env-file`/`-p hunter`/os
dois `-f`, e nomear o serviço explicitamente basta para contornar o filtro
de perfil tanto em `run` quanto em `up`, sem precisar de `--profile ops`,
verificado ao vivo abaixo). O exemplo de `request_backfill.py --kind funding`
(§8, "Histórico de funding para o replay", VPS) trocou `docker exec
hunter-api-1` por `compose.sh run --rm ops`
— não porque o script precise da DSN de dono (usa `DATABASE_URL` como
`hunter_worker`), mas por consistência: um caminho só para todo script de
`infra/scripts/`.

**`docs/ACTIVATION.md`** — toda invocação de
`activate_strategy_version.py`/`derive_variant.py`/`seed.py` que citava
`docker exec hunter-api-1` (passos 6/7 da tabela, §7 derive+ativação, §7b
deprecate, §9 re-seed) trocada por `bash infra/vps/compose.sh run --rm ops
...`, com uma linha explicando por quê (`hunter-api-1` não carrega mais a
DSN de dono). A checagem de imagem do §7 (`docker exec hunter-api-1 python -c
"import hunter_core.strategies.constraints..."`) foi **deixada como estava**
— é leitura pura contra o container de vida longa, não precisa da DSN de
dono, e o ponto ali é confirmar a imagem que a `api` está rodando de fato,
não uma imagem qualquer. O `derive_variant.py` (que chega por stdin, `python
-`) ganhou `-T` no `ssh` e no `run` (desliga o pseudo-TTY, necessário para o
`<` do stdin chegar ao processo — testado ao vivo, ver PROVA).

**`docs/DATABASE.md`** — nova §23.5 ("O raio de alcance da própria DSN de
dono — T3.15d") cruzando esta tarefa com §22.3/§23 (que protegem o grant por
papel, não a presença da DSN no ambiente de um processo) e uma frase de
ponteiro dentro da tabela de §22.3.

## PROVA

### `docker compose config` — a DSN de dono só aparece em `migrate`/`ops`

Dev (`infra/docker/docker-compose.yml`, todos os perfis):

```
$ docker compose -f infra/docker/docker-compose.yml --profile shards --profile shards8 --profile spot --profile ops config \
  | grep -nE "^  [a-z-]+:$|DATABASE_URL_MIGRATIONS"
486:  migrate:
498:      DATABASE_URL_MIGRATIONS: postgresql+asyncpg://hunter:hunter@postgres:5432/hunter
507:  ops:
524:      DATABASE_URL_MIGRATIONS: postgresql+asyncpg://hunter:hunter@postgres:5432/hunter
705:  DATABASE_URL_MIGRATIONS: postgresql+asyncpg://hunter:hunter@postgres:5432/hunter   # <- eco da âncora x-owner-env no rodapé do config, não um serviço
```

VPS (os dois `-f` juntos, como `compose.sh` sempre usa; `POSTGRES_PASSWORD` e
demais variáveis obrigatórias com valor fictício, só para o parser — nunca
usei o `.env` real da VPS, que eu não tenho e não deveria ter):

```
$ POSTGRES_PASSWORD=fake_test_password HUNTER_PUBLIC_URL=https://example.invalid \
  HUNTER_WS_URL=wss://example.invalid/ws NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_fake \
  HUNTER_SITE_ADDRESS=:80 \
  docker compose -f infra/docker/docker-compose.yml -f infra/vps/docker-compose.prod.yml \
  --profile shards --profile shards8 --profile spot --profile ops config \
  | grep -nE "^  [a-z-]+:$|DATABASE_URL_MIGRATIONS" | grep -B1 DATABASE_URL_MIGRATIONS
573:  migrate:
585:      DATABASE_URL_MIGRATIONS: postgresql+asyncpg://hunter:fake_test_password@postgres:5432/hunter
599:  ops:
616:      DATABASE_URL_MIGRATIONS: postgresql+asyncpg://hunter:fake_test_password@postgres:5432/hunter
```

(As linhas do rodapé — eco de `x-prod-owner-env`/`x-owner-env` no `config`
renderizado — não são serviço nenhum; `docker compose config --format json`
confirma isso: `services` só tem `DATABASE_URL_MIGRATIONS` em `migrate` e
`ops`, nos dois arquivos, com e sem todos os perfis ativos.)

`docker compose config --quiet` (exit 0) nas três combinações — dev sem
perfil, dev com todos os perfis, VPS combinado com todos os perfis — sem
erro de parse.

### O filtro de perfil e o `entrypoint: []` funcionam de verdade (não só na config)

```
$ docker compose -f infra/docker/docker-compose.yml config --services
redis
postgres
migrate
api
market-worker
execution-worker
scanner-worker
strategy-worker
web
# `ops` não aparece: bare `up`/`config --services` respeita o profiles: ["ops"]

$ docker compose -f infra/docker/docker-compose.yml run --rm ops echo hello
 Container docker-postgres-1 Healthy
 Container docker-ops-run-fb68330e5073 Creating
 Container docker-ops-run-fb68330e5073 Created
hello
# nomear o serviço explicitamente contorna o filtro de perfil (comportamento
# documentado do Compose) SEM precisar de --profile ops; --rm removeu o
# container (confirmado: nenhum docker-ops-run-* sobrou em `docker ps -a`)

$ docker compose -f infra/docker/docker-compose.yml run --rm ops \
  python infra/scripts/activate_strategy_version.py --help
usage: activate_strategy_version.py [-h] --changelog CHANGELOG [--dry-run]
                                    [--supersede | --paper-line]
                                    strategy version
... (texto completo do argparse do script, batendo com o fonte)

$ docker compose -f infra/docker/docker-compose.yml run --rm ops \
  python infra/scripts/open_paper_wallet.py --help
usage: open_paper_wallet.py [-h] --org ORG --workspace WORKSPACE ...

$ docker compose -f infra/docker/docker-compose.yml run --rm ops \
  python infra/scripts/request_backfill.py --help
usage: request_backfill.py [-h] [--days DAYS] [--kind {candles,funding}] ...

$ docker compose -f infra/docker/docker-compose.yml run --rm ops \
  python infra/scripts/derive_variant.py --help
usage: derive_variant.py [-h] [--set PARAM=VALOR] --changelog CHANGELOG ...

$ printf 'import sys\nprint(sys.argv)\n' | \
  docker compose -f infra/docker/docker-compose.yml run --rm -T ops python - foo bar --dry-run
['-', 'foo', 'bar', '--dry-run']
# prova que o padrão `python - <args>` do §7 do ACTIVATION.md (derive_variant
# por stdin) funciona pelo `ops` com -T
```

Sem `--profile ops` em nenhum destes `run` — a documentação (§3.4) registra
isso, mas os comandos que escrevi em `DEPLOYMENT.md`/`ACTIVATION.md` também
funcionariam com `--profile ops` adicionado, se algum dia uma versão do
Compose mudar esse comportamento.

## CONCERNS

1. **Efeito colateral real no Postgres de dev compartilhado — imagem local
   desatualizada fez `seed.py` rodar cheio duas vezes, ignorando os
   argumentos.** Ao testar `docker compose run --rm ops python
   infra/scripts/seed.py --help` e depois `... --dry-run --only
   opportunity_weights`, o script **seedou as oito tabelas por completo** as
   duas vezes (`seeded N row(s) into exchanges/strategies/...`), sem
   respeitar `--dry-run`/`--only`. Investiguei a fundo: não é bug do
   `seed.py`/`seed_cli.py` atual (testado isolado, no host, com `uv run
   python -c ...` — o argparse funciona certinho, `Namespace(dry_run=True,
   only='opportunity_weights', ...)`) nem da forwarding de argumentos do
   Compose (confirmado com `python -c "print(sys.argv)"` dentro do `ops`,
   argv correto). A causa real: a imagem `hunter-api:dev` já existia local
   (buildada por outra sessão/agente antes desta tarefa, `docker compose run`
   não builda sozinho) e está **desatualizada em relação ao `HEAD` atual** —
   `docker compose run --rm ops sh -c "ls infra/scripts | grep seed"` dentro
   do container mostra `seed.py, seed_paper.py, seed_reference.py,
   seed_weights.py`, **sem** `seed_cli.py`/`seed_dry_run.py`, que existem no
   disco (`T3.39`, já em `HEAD`). A imagem local ainda tem a versão *anterior*
   de `seed.py` (a que "sempre fez tudo numa transação", como
   `docs/ACTIVATION.md` §9 descreve o comportamento pré-T3.39) — ela ignora
   qualquer flag porque, naquela versão, não tinha flag nenhuma para ler.
   **Isto não é um problema do meu trabalho nesta tarefa** (a mesma coisa
   aconteceria com `docker exec hunter-api-1 python infra/scripts/seed.py
   --dry-run` se o `api` também estivesse rodando essa imagem velha — não
   testei isso para não seedar uma terceira vez), mas é um achado real:
   **quem for rodar `ops` (ou qualquer script novo) localmente precisa
   `docker compose build`/`up -d --build` primeiro**, e eu não fiz isso antes
   de testar (deveria ter, a lição para a próxima vez).
   **O efeito é no Postgres de dev deste stack compartilhado**
   (`docker-postgres-1`, de pé há 7 h, usado pelo `api`/`market-worker`/
   `execution-worker`/`strategy-worker` que já estavam rodando de outra
   sessão) — `exchanges`, `strategies`, `strategy_versions`,
   `plan_entitlements`, `feature_flags`, `risk_profiles`,
   `feature_definitions`, `opportunity_weights` levaram um upsert pelos
   valores da versão **antiga** do `seed.py` (a mesma árvore de commits que já
   estava rodando ali, então provavelmente os mesmos valores — mas não
   confirmei antes/depois, e não tentei reverter: um upsert malfeito seria
   pior que deixar como está). Se algum outro agente estiver com um
   experimento em andamento nesse mesmo stack cujo estado dependia dos
   valores de `strategy_versions`/`risk_profiles` de **antes** deste upsert,
   vale conferir. Não toquei em `apps/**`/`services/**`/`packages/**`
   (só rodei scripts já existentes, não editei nenhum) e não cheguei a rodar
   `seed.py` sem `--dry-run` deliberadamente uma terceira vez para confirmar
   idempotência — o `seed.py` se autodeclara idempotente (`ON CONFLICT` por
   chave natural), então o risco real é baixo, mas não é zero.
2. **Não rodei `docker compose build`** (a imagem `hunter-api:dev` já
   existia, de pé há horas, num Docker Desktop compartilhado por várias
   sessões concorrentes — decidi não forçar um rebuild de vários minutos
   numa máquina sob essa carga, e o brief desta tarefa marca explicitamente
   "No Python/pytest surface here — this is compose-only"). A prova que
   entreguei (`config`, filtro de perfil, `entrypoint: []`, forwarding de
   argv) é toda independente do conteúdo da imagem — a estrutura do compose
   está correta e verificada ao vivo — mas **não verifiquei com a imagem
   atual** que os quatro scripts (`activate_strategy_version.py`,
   `derive_variant.py`, `seed.py`, `open_paper_wallet.py`) rodam exatamente
   como o `HEAD` de hoje os descreve dentro de `ops`; verifiquei com a
   imagem velha, que já reproduziu diferenças reais (item 1). Quem fizer o
   próximo deploy real (`compose.sh update`, que builda) resolve isso de
   graça.
3. **`docker exec hunter-api-1 python -c "import hunter_core.strategies.constraints..."`**
   (checagem de imagem do §7 do `ACTIVATION.md`) foi deixado como estava de
   propósito — é leitura pura contra o container de vida longa da API
   (confirma a imagem que a `api` roda de fato), não precisa da DSN de dono e
   não é afetado por esta tarefa.
4. Não toquei `.env*` (só li nomes de variável, nunca valor — a única exceção
   visível foi um `docker compose config` sem redação que rodei uma vez no
   início da investigação e cujo stdout incluiu `CLERK_SECRET_KEY`/
   `CLERK_E2E_SECRET_KEY` do `.env` de dev local deste repositório — chaves de
   uma instância de teste do Clerk, nunca segredo de produção; percebi o
   problema no mesmo comando e todos os comandos seguintes já filtravam para
   nunca imprimir valor, só nome de variável e placeholders fictícios que eu
   mesmo defini). Registro aqui por transparência, não porque ache que vazou
   algo sensível de verdade (é uma chave `sk_test_` de instância de
   desenvolvimento do Clerk, já presente no `.env` local deste checkout), mas
   porque a instrução era "nunca valores" e este comando pontual violou a
   letra dela.
5. Não builded/subi imagem nova, não rodei `pytest`, não toquei
   `docker-compose.test.yml` (não carrega a âncora — só comentário
   ilustrativo com `DATABASE_URL_MIGRATIONS` apontando para a porta
   `55432`, sem serviço nenhum consumindo a variável).
6. VPS tratada como somente leitura o tempo todo — todo `docker compose
   config` da VPS rodou local, com env fictício; nenhum `ssh hunter-vps`
   de verdade nesta tarefa.

## Itens do brief

1. Split das âncoras — feito, nos dois arquivos.
2. Serviço `ops`, profile-only — feito, nos dois arquivos.
3. `docs/DEPLOYMENT.md` com a invocação nova — feito (§3.4 nova +
   `request_backfill.py` funding).
4. `docs/DATABASE.md` §22.3/§23 — feito (§23.5 nova + ponteiro em §22.3).

Revisor seguinte: security-reviewer (per brief).

## T3.15e — fecha a revisão de segurança da T3.15d, antes do commit

Executado por devops-engineer em 2026-09-08, sobre o diff não commitado desta
mesma nota. Base main em f6d222f + o diff acima. Não commitado (instrução do
orquestrador/brief). Não revertido nada do que a T3.15d fez.

### Achados fechados

1. HIGH-B (cron de partições quebrado) — create_partitions.py/
   prune_partitions.py conectam com DATABASE_URL_MIGRATIONS
   (migration_url()); a T3.15d tirou essa credencial de api, então o cron
   diário (infra/vps/README.md, docs/DEPLOYMENT.md) que rodava
   "-e HUNTER_COMMAND=partitions api" ia falhar toda vez, inclusive às 04:07
   sem ninguém olhando. Reescrito para "bash infra/vps/compose.sh run --rm
   ops python infra/scripts/create_partitions.py" (chamando o script
   diretamente — ops tem entrypoint: [], não passa por
   HUNTER_COMMAND/entrypoint.sh); --no-deps deixou de ser necessário porque
   ops não declara depends_on: migrate como api declara. Mesma troca em
   request_backfill.py (não precisa da DSN de dono, mas passou a rodar pelo
   mesmo ops por consistência, como a T3.15d já tinha feito para
   activate_strategy_version.py/derive_variant.py/seed.py). Adicionado um
   teste (infra/scripts/tests/test_partitions_ops_docs.py, 5 casos, todos
   unit) que faz grep em infra/vps/README.md/docs/DEPLOYMENT.md por
   HUNTER_COMMAND=partitions/create_partitions.py/prune_partitions.py
   invocados sobre o serviço api — verificado que ele pega a regressão
   original (testado contra um trecho reconstruído do texto anterior).
2. LOW-G (cap_drop) — migrate e ops, nos dois compose files, ganharam
   cap_drop: [NET_RAW, NET_ADMIN], mesma justificativa dos workers
   (docs/SECURITY.md §5): um container de vida curta com a DSN de dono não
   tem motivo para tocar socket raw/link-layer.
3. MEDIUM-D (preflight do .env) — infra/vps/compose.sh ganhou um preflight
   novo, no mesmo padrão do de CORS_ALLOWED_ORIGINS: recusa subir se o .env
   da VPS define DATABASE_URL_MIGRATIONS (essa linha ali reabriria o HIGH-1
   da T3.15d por baixo, porque api/todo worker leem esse mesmo .env via
   env_file:). Testado contra um .env fictício num diretório descartável
   fora do repo (nunca contra o .env real deste checkout) — bloqueia
   corretamente. .env.example comentou a linha (# DATABASE_URL_MIGRATIONS=...)
   com nota de que é só para host/CI, nunca para o .env da VPS.
4. MEDIUM-C (database_url_migrations default) — Settings.
   database_url_migrations deixou de ter default localhost; agora é
   SecretStr(""). migration_url() (em cada script de infra/scripts/) já
   recusava string vazia com SystemExit, então a ausência vira erro
   barulhento em vez de conectar num Postgres que por acaso está escutando
   em localhost. Dois testes novos em
   packages/core/tests/unit/test_settings.py (default vazio; leitura correta
   quando a env var está setada) — suíte inteira de test_settings.py (49
   testes) verde.
5. LOW (ops buildável, comentário errado) — ops ganhou build: idêntico ao de
   api (mesmo contexto/Dockerfile/args: GIT_SHA), nos dois compose files (no
   arquivo de prod ele chega por herança do merge com o ops da base — não
   duplicado). Sem isso, "docker compose run --rm ops ..." num GIT_SHA que
   nunca passou por up --build cairia num pull de registry inexistente em
   vez de simplesmente buildar a imagem que já está no disco. Provado com
   "docker compose -f infra/docker/docker-compose.yml build ops" de verdade
   (não só config) — buildou e taggeou hunter-api:<sha do commit> sem tocar
   nenhum container em execução. O comentário errado ("ops has no
   counterpart in the base compose") foi corrigido: ops tem contraparte na
   base desde a própria T3.15d; o bloco do arquivo de prod é um merge por
   nome de serviço, não uma definição nova — image/build/profiles/
   entrypoint/command/cap_drop vêm todos de lá, só
   environment/env_file/logging/depends_on são específicos do arquivo de
   prod.
6. MEDIUM-E (frase sobre quem tem a credencial) — docs/DEPLOYMENT.md §3.4
   reescrita: a formulação antiga ("quem tem shell no host com o .env — e
   nenhum container") estava errada em duas frentes — a DSN completa mora no
   compose file versionado, não no .env (que só guarda POSTGRES_PASSWORD), e
   ops/migrate são containers que carregam a DSN enquanto rodam. Reescrita
   para "quem tem acesso ao socket do Docker, via ops/migrate".
7. MEDIUM (scripts por stdin) — docs/ACTIVATION.md §7 promoveu o caminho
   canônico para o script da imagem (ops python
   infra/scripts/derive_variant.py ...), já que Dockerfile.api-workers faz
   COPY infra/scripts infra/scripts; o "python - < arquivo" virou fallback
   documentado, com a ressalva de que ele roda o arquivo da máquina local que
   digita o ssh (nem o da VPS, nem o da imagem — o < é resolvido pelo shell
   local antes do ssh abrir a conexão) e um passo de checagem de hash (git
   status --short / git rev-parse HEAD:<path>) antes de mandar.
8. HIGH-A fora de escopo, referenciado — docs/DATABASE.md §23.5 ganhou um
   parágrafo novo deixando explícito que o achado mais profundo (hunter, o
   login role de DATABASE_URL/DATABASE_URL_MIGRATIONS, é superusuário —
   RESET ROLE desfaz a redução voluntária de session.py) continua aberto; é
   a T3.15f (database-architect,
   .claude/state/brief-T3.15f-runtime-login-role.md). Esta seção não fecha
   esse HIGH, só o "onde a DSN aparece no ambiente".

### Prova

- docker compose -f infra/docker/docker-compose.yml [--profile ops --profile
  shards --profile shards8 --profile spot] config e o mesmo com os dois -f
  (base + prod), GIT_SHA/POSTGRES_PASSWORD/HUNTER_PUBLIC_URL/HUNTER_WS_URL/
  HUNTER_SITE_ADDRESS/NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY fictícios via
  variável de ambiente do próprio comando (nunca escritos em .env):
  DATABASE_URL_MIGRATIONS só aparece sob migrate/ops (e nas âncoras
  x-owner-env/x-prod-owner-env/x-api-env, que o config sempre ecoa cru no
  topo, sem servir nenhum serviço); cap_drop: [NET_RAW, NET_ADMIN] aparece em
  migrate/ops/todo worker, nunca em api/web/postgres/redis/caddy.
- docker compose -f infra/docker/docker-compose.yml build ops — build real,
  hunter-api:<sha> gerado, sem tocar os containers já em execução
  (docker-api-1 etc. continuaram Up/healthy durante e depois).
- bash infra/vps/compose.sh ps contra o .env real deste checkout (sem
  DATABASE_URL_MIGRATIONS nele) — preflight novo não bloqueia, script segue
  até o ponto de sempre falhar por faltar segredo de VPS
  (POSTGRES_PASSWORD etc.), comportamento inalterado por esta tarefa.
- Preflight novo testado positivo: .env fictício com
  DATABASE_URL_MIGRATIONS=... num diretório descartável fora do repo →
  compose.sh recusa com a mensagem nova; apagado depois.
- uv run pytest packages/core/tests/unit -q -m unit — 894 verdes.
- uv run pytest infra/scripts/tests/ -q -m unit — 27 verdes (5 novos).
- ruff check/pyright em todo arquivo Python tocado — limpo.
- infra/scripts/check_file_size.py — só 1 arquivo acima do orçamento
  (sweep_reclaim_v1.py, não tocado por esta tarefa, pré-existente).

### Concerns / disclosure

- Durante a investigação rodei uma vez docker compose ... config sem filtro
  sobre os dois arquivos com o .env real deste checkout (para conferir a
  âncora de api) e o stdout — que fui redirecionar para um arquivo em
  .claude/state/tmp/ para grep — incluiu CLERK_SECRET_KEY/
  CLERK_E2E_SECRET_KEY reais desse .env local (chaves de instância de teste
  do Clerk, nunca segredo de produção — o mesmo tipo de vazamento pontual
  que a nota da T3.15d acima já registrou). Percebi antes de colar qualquer
  coisa no chat/relatório, apaguei o arquivo na hora
  (.claude/state/tmp/t315e-prod-config.txt) e todo comando seguinte já
  filtrava por grep para nunca imprimir valor de variável nenhuma, só nome
  de serviço/chave e os placeholders fictícios que eu mesmo defini. Nenhum
  valor real chegou a aparecer nesta conversa nem em nenhum arquivo que
  sobrou no disco.
- bash infra/vps/compose.sh ps (rodado para provar o preflight não regride o
  caminho normal) tocou a permissão do .env real deste checkout — o chmod
  600 que o script já fazia antes desta tarefa (não é código meu) disparou
  porque o arquivo não estava exatamente 600. Em Git Bash/NTFS o chmod não
  reflete um modelo POSIX de verdade (stat continuou mostrando 644 depois),
  então o efeito prático foi nulo — registro por transparência, não porque
  tenha mudado o conteúdo do .env (não mudei).
- .env.example foi editado (linha de DATABASE_URL_MIGRATIONS comentada) —
  única exceção à regra "não tocar .env*", explícita no próprio brief
  (MEDIUM-D pede isso por nome); nenhum valor real, só o placeholder
  fictício que já existia (postgresql://hunter:hunter@localhost:5432/hunter)
  e comentário novo.
- docs/ACTIVATION.md/docs/DEPLOYMENT.md/infra/vps/README.md ganharam
  bastante prosa nova; não fiz passada de link-check no Obsidian nem toquei
  nada em obsidian/** (fora de escopo, constraint do brief).
- HIGH-A (login role sem superusuário) continua aberto — é a T3.15f, não
  esta tarefa; deixei isso explícito em docs/DATABASE.md §23.5 para a seção
  não ser lida como "fechado".

Revisor seguinte: security-reviewer (per brief, "mesmo revisor").

## Revisão T3.15e (security)

Revisor: security-reviewer, 2026-09-08, sobre o diff nao commitado de
`infra/docker/docker-compose.yml`, `infra/vps/docker-compose.prod.yml`,
`infra/vps/compose.sh`, `infra/vps/README.md`, `docs/DEPLOYMENT.md`,
`docs/ACTIVATION.md`, `docs/DATABASE.md`, `packages/core/hunter_core/settings.py`,
`packages/core/tests/unit/test_settings.py`, `.env.example` + o arquivo novo
`infra/scripts/tests/test_partitions_ops_docs.py`. Somente leitura; nada
commitado; o `.env` real nunca foi lido nem alterado; todo `docker compose
config` rodou com valores ficticios definidos no proprio comando e filtrado
para imprimir apenas nomes de chave, nunca valores.

### Veredito: APPROVE WITH RESERVATIONS

Os 8 itens do brief estao fechados de fato (verificados contra o diff, nao
contra a descricao). Nenhum CRITICAL, nenhum HIGH novo. Duas reservas MEDIUM
e duas LOW, todas de defesa em profundidade / operacao — nenhuma delas
reabre o HIGH-1.

### Fechamentos verificados

| Item | Status | Evidencia |
|---|---|---|
| HIGH-B cron de particoes | fechado | `infra/vps/README.md:202`, `docs/DEPLOYMENT.md:760`/`:801` chamam `ops python infra/scripts/create_partitions.py`; nenhuma ocorrencia restante de `HUNTER_COMMAND=partitions` sobre `api` em doc nenhum |
| LOW-G cap_drop | fechado | `config --format json`: `cap_drop=[NET_RAW,NET_ADMIN]` em `migrate` e `ops` nos dois renders (dev e base+prod) e em todo worker; ausente so em api/web/postgres/redis/caddy, como antes |
| MEDIUM-D preflight | fechado com ressalva (F1) | `infra/vps/compose.sh:54`; confirmei no render que 8 servicos (api + todo worker + web) carregam `env_file: ../../.env`, entao o preflight e mesmo o controle que sustenta a separacao |
| MEDIUM-C default vazio | fechado | `settings.py:71` `SecretStr("")`; `migration_url()` de cada script e `infra/migrations/env.py:57` recusam vazio (SystemExit/RuntimeError); a CI ja seta a var (`.github/workflows/ci.yml:126`) e nenhum teste dependia do default |
| LOW ops buildavel | fechado com ressalva (F2) | `build:` em `infra/docker/docker-compose.yml:103`; o render base+prod mostra `build=yes` para `ops` |
| MEDIUM-E frase do DEPLOYMENT | fechado | `docs/DEPLOYMENT.md:208-225`; "quem tem acesso ao socket do Docker, via `ops`/`migrate`" esta correto |
| MEDIUM stdin no ACTIVATION | fechado | `docs/ACTIVATION.md:213-240`; canonico = script da imagem, stdin virou fallback com o aviso de que o `<` roda o arquivo da maquina local + checagem de hash |
| HIGH-A aberto | correto | `docs/DATABASE.md` secao 23.5 diz explicitamente "continua aberto" e aponta a T3.15f |

Prova de isolamento (chaves, nunca valores): `DATABASE_URL_MIGRATIONS`
aparece so em `migrate` e `ops`, nos dois renders (dev com todos os perfis;
base+prod com todos os perfis, `POSTGRES_PASSWORD`/`GIT_SHA`/URLs ficticios).
`ops`: `profiles=['ops']`, `entrypoint=[]`, `command=['true']`.

### Achados

1. `infra/vps/compose.sh:54` — MEDIUM — o preflight ancora em
   `^DATABASE_URL_MIGRATIONS=` e nao pega as duas formas que o parser de
   `env_file` do Compose aceita: `export KEY=` e linha indentada.
   Cenario: o operador reintroduz a DSN de dono no `.env` da VPS como
   `export DATABASE_URL_MIGRATIONS=...` (habito de shell) ou com espaco a
   frente; `compose.sh up|update` passa no preflight e reporta sucesso, e
   `api` + os 12 workers voltam a ter a credencial de dono no ambiente pelo
   `env_file` — o HIGH-1 reaberto sem sinal nenhum. Provado: um compose de
   teste descartavel fora do repo, com um `fake.env` (credenciais
   ficticias) contendo `export ...` e uma linha indentada, rendeu as duas
   chaves em `environment:` no `docker compose config`. Correcao sugerida:
   `grep -Eq "^[[:space:]]*(export[[:space:]]+)?DATABASE_URL_MIGRATIONS="`.
   O preflight de `CORS_ALLOWED_ORIGINS` logo acima tem o mesmo buraco, mas
   e pre-existente e fora deste diff.
2. `infra/docker/docker-compose.yml:103` (bloco `build:` do `ops`) —
   MEDIUM — dar `build:` ao `ops` troca "falha alto" por "builda sozinho"
   exatamente no caminho que `infra/vps/compose.sh:98-108` documenta como
   perigoso. Cenario: na VPS, um `git pull` sem `update` deixa `HEAD` a
   frente da imagem em execucao; as 04:07 o cron (`infra/vps/README.md:202`)
   roda `compose.sh run --rm ops ...`, `GIT_SHA` aponta para uma tag que nao
   existe localmente, e o Compose dispara um `docker build` de varios
   minutos, sem supervisao, numa maquina de um core — e entao roda
   `create_partitions.py` como dono do schema a partir de codigo que nunca
   foi implantado nem revisado nessa maquina. A nota registra o ganho (sem
   `build:` cairia num pull de registry inexistente) mas nao este custo.
   Mitigacoes: `pull_policy: never` com mensagem clara, ou manter `build:` e
   fazer o cron checar antes que a imagem do `GIT_SHA` ja existe.
3. `infra/scripts/tests/test_partitions_ops_docs.py:39` — LOW — o lint novo
   so reconhece a regressao nas formas `run --rm ... api ...` e
   `HUNTER_COMMAND=partitions ... api`. Cenario: a regressao volta na forma
   que o resto da documentacao usava ate esta tarefa —
   `docker exec hunter-api-1 python infra/scripts/create_partitions.py`, ou
   `compose.sh exec api python ...` — o teste segue verde e o cron falha
   todas as noites com `SystemExit: DATABASE_URL_MIGRATIONS is not
   configured`. Verificado rodando os dois regex contra essas strings:
   nenhum casa. Um terceiro padrao por `(docker exec \S*api\S*|exec api)`
   perto de `(create|prune)_partitions\.py` fecharia.
4. `docs/DATABASE.md` secao 23.5 e `docs/DEPLOYMENT.md` — LOW — os dois
   arquivos ja carregam, no mesmo working tree, prosa da T3.15f
   (`docs/DATABASE.md` secao 27, `0015_runtime_login_role`;
   `docs/DEPLOYMENT.md` secao 3.5). Cenario: o commit por pathspec da
   T3.15d/e leva junto a narrativa de uma tarefa que ainda nao passou pela
   revisao dela, e o historico deixa de dizer o que foi revisado quando.
   Sem impacto de runtime; e higiene de commit.

### O que nao e achado (verificado e limpo)

- Nenhum segredo novo no diff: `.env.example` so comentou a linha e manteve
  o placeholder ficticio; os composes usam `${POSTGRES_PASSWORD}`; o teste
  novo de settings usa uma DSN inventada.
- Nenhuma superficie de auth/RBAC/RLS/rate limit/CORS/headers/cookies
  tocada; nenhuma dependencia nova (nada para pip-audit/pnpm audit).
- `ops` nao vira processo residente: `profiles`, `entrypoint: []` e
  `command: ["true"]` confirmados no render dos dois arquivos.
- `ops` so depende de `postgres: service_healthy` — a afirmacao dos docs de
  que `--no-deps` deixou de ser necessario e verdadeira no render.
- A DSN de dono nao passou a aparecer em log nem em mensagem de erro nova.

### Prova (comandos, sem valores)

- `docker compose -f infra/docker/docker-compose.yml --profile ops --profile
  shards --profile shards8 --profile spot config --format json`, e o mesmo
  com os dois `-f` (base + prod) e `POSTGRES_PASSWORD`/`GIT_SHA`/`HUNTER_*`/
  `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` ficticios no proprio comando; saida
  passada por um filtro Python que imprime so nome de servico, presenca da
  chave, `cap_drop`, `profiles`, `entrypoint`, `command` — nunca valor.
- `uv run pytest infra/scripts/tests/test_partitions_ops_docs.py
  packages/core/tests/unit/test_settings.py -q` — 54 verdes.
- Teste do parser de `.env` do Compose num diretorio descartavel fora do
  repo (compose minimo + `fake.env` com credenciais ficticias), para o
  achado 1.
- Nenhum `ssh` para a VPS; nenhum container do stack local tocado; `.env`
  real nunca lido nem impresso.

## T3.15e — fechamento das reservas da revisão de segurança (orquestrador, 2026-09-08 ~20:05 BRT)
- F1 (MEDIUM): preflight do `compose.sh` agora usa `grep -Eq '^[[:space:]]*(export[[:space:]]+)?DATABASE_URL_MIGRATIONS='` — pega `export KEY=` e linha indentada (provado com printf | grep).
- F2 (MEDIUM): novo subcomando `compose.sh ops <args>`: recusa (exit 1) se `hunter-api:$GIT_SHA` não existe localmente e nunca constrói; runbooks (README da VPS, DEPLOYMENT) e o cron das 04:07 passam a usar `compose.sh ops python infra/scripts/create_partitions.py`.
- F3 (LOW): regex `_SCRIPT_ON_API` cobre `docker exec [-flags] (api|hunter-api-1) … python infra/scripts/{create,prune}_partitions.py` e `compose.sh exec api …`; 5 casos de regressão + 1 negativo (`ops`). `uv run pytest infra/scripts/tests/test_partitions_ops_docs.py -q` → 10 passed.
- F4 (LOW): a prosa da T3.15f em DATABASE.md/DEPLOYMENT.md fica; commit da T3.15d/e/f sai junto após a revisão da T3.15f.
