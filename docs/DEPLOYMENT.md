# Deploy e operação

## 1. Ambientes

| Ambiente | Web | API + workers | Postgres | Redis |
|---|---|---|---|---|
| Local | `pnpm dev` ou compose | compose (`HUNTER_ROLE=all`) | compose | compose |
| Preview (PR) | Vercel preview | Railway PR environment (opcional) | Neon branch | Upstash dev |
| Staging | Vercel | Railway (api, market, scanner, strategy, execution, analytics) | Neon branch `staging` | Redis Railway |
| Produção | Vercel | Railway ou Fly.io | Neon `main` (pooler) | Redis Railway / Upstash fixo |

Nada em produção lê arquivo local. Configuração só por env — a lista completa
de variáveis está no §7.

## 2. Imagens

- `infra/docker/Dockerfile.api-workers`: Python 3.12 slim, `uv sync --frozen`, usuário não-root, `ENTRYPOINT infra/docker/entrypoint.sh`: `HUNTER_COMMAND=migrate|seed` executa Alembic ou o seed e sai; caso contrário `HUNTER_ROLE=api` sobe o uvicorn e os papéis de worker (`market|scanner|strategy|execution|analytics|all`) imprimem que ainda não têm entrypoint e saem com 0 até o M1 (sem processo falso).
- `infra/docker/Dockerfile.web`: Next.js standalone (usado só se o web não for na Vercel). `NEXT_PUBLIC_*` são baked no bundle em build time — passar os reais via `--build-arg` num deploy de verdade.
- Tag = SHA do commit; `release` do Sentry = mesmo SHA.

## 3. docker-compose (dev)

Serviços: `postgres:16`, `redis:7`, `migrate` (`HUNTER_COMMAND=migrate`, roda uma vez), `api` (depende do `migrate` concluído), `market-worker` (`HUNTER_ROLE=market`, processo contínuo com `restart: unless-stopped`), `web`. Volumes só para os bancos. `docker-compose.test.yml` sobe Postgres (porta 55432) e Redis (porta 56379) efêmeros para testes de integração locais.

Funciona sem nenhum `.env` (usa defaults de dev embutidos no compose para as chaves do Clerk — build/boot não falham, mas o sign-in real não funciona); um `.env` na raiz (gerado por `infra/scripts/setup_env.ps1`, nunca commitado) sobrepõe esses defaults.

- API: `http://localhost:8000` (`/health` = vivo, `/ready` = Postgres + Redis alcançáveis, 200 só quando ambos respondem, `/metrics` atrás de `METRICS_TOKEN`).
- Web: `http://localhost:3000` (redireciona para o sign-in do Clerk).
- `market-worker` reutiliza a imagem construída pelo serviço `api` e executa `python -m hunter_market_worker`, após Postgres e Redis saudáveis e `migrate` concluído com sucesso. O healthcheck consulta `http://localhost:8001/ready` dentro do container, sem publicar porta no host.
- Um `HUNTER_ROLE` por container no M1: `market`, `scanner`, `strategy`, `execution` e `analytics` executam seus respectivos módulos `hunter_<role>_worker`. Os quatro últimos falham enquanto não tiverem `__main__.py`; `all` não é suportado e sai com código 64.

Comandos reais (instalação, `.env`, subir a stack, migrar/seedar manualmente,
rodar o web fora do compose) estão no §8.

### 3.1 Coletor em N shards (T2.5g)

Um processo com 200 mercados satura um core: medido em 2026-09-07 no stack
local (CPU 99,4 %, 8,3 M eventos descartados) e na VPS (101 %, 1,2 M
descartados), com `market.ticks` publicado **25,8 s** depois do carimbo do
payload e `covered_until` congelado em `session_since` desde o boot — o
coletor, corretamente, não conseguia provar continuidade nenhuma. A saída é
dividir o universo entre N processos (`MARKET_SHARD=i/N`, fatia estável
`crc32(symbol) % N`, T1.6b-C2).

```powershell
# 4 shards x ~50 mercados, dev
$env:MARKET_SHARDS=4
docker compose -f infra/docker/docker-compose.yml --profile shards up -d
```

- os três shards extras (`market-worker-1..3`) vivem no perfil `shards`, então
  um `up` normal continua subindo **um** coletor;
- `MARKET_SHARDS` é lido pelos quatro serviços (`0/$MARKET_SHARDS` …
  `3/$MARKET_SHARDS`). Esquecer a variável **não** duplica a coleta em
  silêncio: os extras receberiam `1/1`, que `Settings` recusa no boot
  (`MARKET_SHARD index must satisfy 0 <= index < total`), e o container fica
  em restart loop visível;
- cada shard escreve `hb:market:{exchange}:{i}of{N}` e a API agrega
  (`/api/v1/system/market-status`, `shards_expected`/`shards_reporting`;
  `ws_state = "stale"` se faltar shard). O `/markets` mostra "N shards, M
  mercados"; a página System deixa de receber patch por `rt:system` em modo
  sharded — ver PIPELINE.md §1 item 8;
- ordem de subida é irrelevante (a liderança do universo é um lock em Redis) e
  nenhum `/ready` depende dos irmãos;
- **mudar N deixa grupos de consumidor órfãos** do backfill
  (`market-worker.backfill.{exchange}.{i}of{N}`) e uma chave
  `hunter:processed:` por grupo. Remover à mão, depois de conferir que não há
  pendência (`XINFO GROUPS market.backfill.requested`).

### 3.2 `execution-worker` (T3.5/T3.13)

O que é: `HUNTER_ROLE=execution` (`services/execution-worker/`), o motor da
carteira de papel — seis laços (`admissão`, `entradas`, `proteção`, `expiração`
de reserva, `kill switch`, `mark-to-market`) sob a trava da carteira, mais o
heartbeat. Nada em memória é fonte de verdade: todo laço relê posições,
intenções e reservas do Postgres a cada passada.

Como sobe: mesma imagem `hunter-api:${GIT_SHA:-dev}` dos demais workers, papel
selecionado por `entrypoint.sh` (`case "$role" in ... scanner | strategy |
execution | analytics) exec python -m "hunter_${role}_worker"`). No compose de
dev (`infra/docker/docker-compose.yml`) e no override de produção
(`infra/vps/docker-compose.prod.yml`) já existe o serviço `execution-worker`
desde a T3.5, com `restart: unless-stopped`/`always`, `*prod-db-env` na VPS e
healthcheck em `http://localhost:8001/ready` (cinco checks:
`paper_schema`, `kill_switch_legible`, `mtm_fresh`, `protection_prompt`,
`outbox_not_lagging`, além dos genéricos `database`/`redis`). Depende de
`migrate` concluído e de Postgres/Redis saudáveis; depende do `market-worker`
só com `service_started` (não `service_healthy`) — sem book utilizável uma
proteção fica pendente **com alerta** em vez de fabricar um fill.

O que **não** faz nesta tarefa (T3.13 é só integração operacional, nenhuma
ativação de produção):

- **nunca movimenta dinheiro real.** `ENABLE_LIVE_TRADING` é lido uma vez no
  boot (`hunter_execution_worker/config.py: load_config`) e, se `true`, o
  processo recusa subir (`LiveTradingRefused`) — não existe adaptador live
  (`LiveExecutionAdapter` levanta em toda chamada). Os dois composes fixam
  `ENABLE_LIVE_TRADING: "false"` explicitamente, para que a variável nunca
  dependa de um `.env` esquecido;
- **não decide pedidos sozinho por padrão.** `ENABLE_PAPER_AUTONOMY` (default
  `false`) é o portão da ponte sinal→proposta que a T3.14 constrói; com ele
  desligado (o estado de todo ambiente hoje, inclusive a VPS) o worker só
  decide os pedidos que a API arquivou manualmente (`decide_requests`,
  `source="manual"`). Ligá-lo é o dia em que o worker passa a decidir pedidos
  que ninguém digitou — mudança de comportamento, não de infraestrutura, e
  fora do escopo desta tarefa;
- **não expõe HTTP além do `/health`/`/ready`/`/metrics` do `HEALTH_PORT`**
  (ARCHITECTURE.md §4: "é o único processo que, no futuro, terá acesso a
  chaves descriptografadas de exchange... não expõe HTTP além de `/health`").

Deploy na VPS: o mesmo comando único que já sobe os shards do coletor sobe o
`execution-worker` junto, porque ambos vivem no mesmo par de arquivos de
compose que `compose.sh` sempre passa para o Docker:

```bash
MARKET_SHARDS=4 bash infra/vps/compose.sh update
```

### 3.3 Coletor SPOT dedicado (`market-worker-spot`, T3.0f)

Por quê: com 200 perpétuos num só `MARKET_SHARD=0/N`, ligar
`MARKET_SPOT_ENABLED=true` fez o socket perpétuo perder o keepalive — código
`1011`, 8 reconnects em 6 min, 0 velas persistidas (`.claude/state/t30-proof.md`
§1, `docs/PIPELINE.md` §1d). A saída é rodar o spot como processo próprio, nunca
como um modo de um shard perpétuo.

`hunter_core.settings.Settings.market_role` (`MARKET_ROLE`) escolhe o caminho de
dados de cada processo `market-worker`:

- `perpetual` — hoje's shards; `MARKET_SPOT_ENABLED` não tem efeito nenhum
  neste papel, seja qual for o valor;
- `spot` — só o coletor spot (universo, fitas/livros/velas, heartbeat
  `hb:market:spot:{ex}`, cobertura); nunca sharded (`Settings` recusa no boot
  um `MARKET_ROLE=spot` com `MARKET_SHARD` fatiado — não há leitura válida
  para essa combinação);
- `both` — o comportamento de hoje do shard único do stack local (perpétuo +,
  se `MARKET_SPOT_ENABLED=true`, spot no mesmo processo).

Default quando `MARKET_ROLE` não é definido: `perpetual` se `shard_total > 1`
(topologia de shards), `both` caso contrário (`MARKET_SHARD=0/1`, o stack local
de processo único). Um `MARKET_ROLE=both` explícito sob `MARKET_SHARD` fatiado
também é recusado no boot — é exatamente a combinação que satura o event loop.
`MARKET_ROLE=spot` com `MARKET_SPOT_ENABLED=false` **não** é recusado: o
processo loga e fica ocioso, nunca em crash loop.

Serviço novo `market-worker-spot` (perfil `spot`), com `MARKET_ROLE=spot`,
`MARKET_SPOT_ENABLED=true` e `MARKET_SHARD=0/1` fixados **no serviço do
compose**, nunca no `.env` — para que a decisão de ligar o spot compartilhado
fique explícita e revisável em `infra/docker/docker-compose.yml`/
`infra/vps/docker-compose.prod.yml`, e para que a flag nunca alcance por
acidente um shard perpétuo através de um `.env` compartilhado.

```bash
# stack local
docker compose -f infra/docker/docker-compose.yml --profile spot up -d

# VPS — adiciona o perfil `spot` ao mesmo comando que já sobe os shards
MARKET_SPOT=1 MARKET_SHARDS=4 bash infra/vps/compose.sh update
```

Verificar depois de subir: `hb:market:spot:{exchange}` vivo (Redis, ou
`GET /api/v1/system/workers` — aparece com `role: "market-spot"`, sua própria
linha, nunca como um shard perpétuo faltando ou uma linha ilegível — T3.0f
corrigiu `hunter_api.services.system_status.parse_heartbeat_key`, que antes
lia essa chave como `role="market"`/`instance="spot:{exchange}"` e
anonimizava o `instance` por conter `:`); `docker logs market-worker-spot`;
e que os heartbeats perpétuos (`hb:market:{exchange}:{i}of{N}`) continuam com
`reconnects` parado e `last_event_at` fresco — a checagem que
`docs/PIPELINE.md` §1d já pedia antes de considerar o ambiente estável, agora
sobre um processo que nunca compartilha event loop com eles.

### 3.4 A DSN de dono e o serviço `ops` (T3.15d)

`DATABASE_URL_MIGRATIONS` é a conexão do **dono do schema** — a mesma que
`infra/scripts/activate_strategy_version.py`, `derive_variant.py`, `seed.py`
e `open_paper_wallet.py` usam para escrever (docs/DATABASE.md §22.3/§23).
Até esta tarefa ela vivia na âncora (`x-api-env`/`x-prod-db-env`) que **todo**
serviço herdava — `api` e cada worker (`market`, `scanner`, `strategy`,
`execution`) tinham a credencial de dono no próprio ambiente, mesmo sem
nenhum código de produção jamais construir uma conexão com ela. Achado
HIGH-1 de `.claude/state/review-T3.15-security.md`: um RCE em qualquer um
desses processos (uma CVE de dependência, um path traversal lendo
`/proc/self/environ`, um handler de erro que despeja o ambiente) podia abrir
conexão como dono e escrever `strategy_versions.purpose = 'paper'`, ativar
uma versão sem passar pelo script, ou `ALTER TABLE ... DISABLE ROW LEVEL
SECURITY` em qualquer tabela de tenant.

Os dois composes (`infra/docker/docker-compose.yml`,
`infra/vps/docker-compose.prod.yml`) agora separam a âncora em duas:

- `x-api-env`/`x-prod-db-env` — só o que todo processo de runtime precisa
  (`DATABASE_URL`, `REDIS_URL`, `HUNTER_ENV`, ...). `api` e cada worker
  continuam recebendo exatamente isto, sem `DATABASE_URL_MIGRATIONS`.
- `x-owner-env`/`x-prod-owner-env` — só `DATABASE_URL_MIGRATIONS`. Concedida
  a exatamente dois serviços: `migrate` (o job de `alembic upgrade head` que
  já corre em todo `up`/`update`) e o novo `ops`.

`ops` é **só perfil** (`profiles: ["ops"]`): nunca sobe com um `docker
compose up` normal (nem com `compose.sh up|update`, que não adiciona esse
perfil sozinho) — existe para ser `run --rm`, nunca `up`d. Não roda processo
nenhum por padrão (`entrypoint: []` + `command: ["true"]`, que só importa se
alguém o nomear explicitamente, o único jeito de contornar o filtro de
perfil): sobe, executa `true`, sai. É a mesma imagem `hunter-api:${GIT_SHA:-dev}`
de `api`/todo worker — só o ambiente Python, nunca um processo residente
segurando a conexão de dono aberta.

**Onde cada script roda agora.** O container de vida longa `hunter-api-1` não
tem mais `DATABASE_URL_MIGRATIONS` no ambiente — `docker exec hunter-api-1
python infra/scripts/activate_strategy_version.py ...` (o padrão que
`docs/ACTIVATION.md` documentava até esta tarefa) já não teria a credencial.
O caminho novo:

```bash
# dev/local
docker compose -f infra/docker/docker-compose.yml run --rm ops \
  python infra/scripts/activate_strategy_version.py momentum v1 --paper-line --dry-run --changelog "..."

# VPS (compose.sh já resolve --env-file, -p hunter e os dois -f; nenhum
# --profile é preciso: nomear o serviço explicitamente basta para contornar
# o filtro de perfil, tanto para `run` quanto para `up`)
ssh hunter-vps "cd /opt/project-hunter && bash infra/vps/compose.sh run --rm ops \
  python infra/scripts/activate_strategy_version.py momentum v2 --changelog 'D10: coorte paper'"
```

`docs/ACTIVATION.md` tem os comandos completos de cada passo do runbook,
atualizados para este padrão. Depois desta tarefa, "quem consegue rodar
`activate_strategy_version.py`" tem uma resposta honesta (T3.15e, MEDIUM-E —
a formulação anterior desta seção, "quem tem shell no host com o `.env` — e
nenhum container", estava errada em duas frentes): **quem tem acesso ao
socket do Docker na VPS** (grupo `docker` ou `root`) — via `ops`/`migrate`,
hoje os dois únicos lugares onde a DSN de dono existe (`x-prod-owner-env`).
Isso não é o mesmo que "shell no host com o `.env`": o `.env` guarda só
`POSTGRES_PASSWORD` (e os outros segredos) — a string de conexão inteira
(usuário, host, porta, banco) mora no template `x-prod-owner-env`, versionado
em `infra/vps/docker-compose.prod.yml`, não no `.env`; ter o socket do Docker
já basta para montar esse `.env` em qualquer container próprio e completar a
DSN lendo o compose file do repositório, sem precisar de `ops`/`migrate` nem
de shell de verdade na máquina. E "nenhum container" não é verdade: `ops` e
`migrate` carregam a DSN, por design, enquanto rodam — o que deixou de
carregá-la foi todo processo de **vida longa** (`api`, todo worker); a frase
certa é essa, não "nenhum container". `request_backfill.py` não
precisa da DSN de dono (conecta como `hunter_worker` via `DATABASE_URL`,
`packages/core/hunter_core/db/session.py::role_session`) mas passou a rodar
pelo mesmo `ops`, por consistência operacional — um único caminho auditável
para todo script de `infra/scripts/`, em vez de dois a lembrar.

Prova (`docker compose ... config`, valores redigidos):
`.claude/state/notes-T3.15d.md`.

### 3.5 Trocar o runtime para `hunter_runtime` (T3.15f)

A §3.4 tirou a **segunda** cópia da credencial de dono do ambiente dos
processos de runtime. A que ficou — `DATABASE_URL` — **era a mesma
credencial**: `hunter`, superusuário, `BYPASSRLS`. `hunter_app`/`hunter_worker`
são papéis `NOLOGIN` concedidos a ela, então o `SET LOCAL ROLE` do
`hunter_core.db.session` sempre foi uma redução voluntária que um `RESET ROLE`
desfaz (docs/DATABASE.md §23.5). A migração `0015_runtime_login_role` cria o
login que substitui essa DSN: `hunter_runtime`, sem superusuário, sem
`BYPASSRLS`, sem herança, membro de `hunter_app` e `hunter_worker` e de mais
nada (docs/DATABASE.md §27).

**A migração sozinha não fecha nada.** Ela cria o papel — **sem senha**, porque
senha no repositório não é senha. Quem troca a credencial é o deploy, nesta
ordem.

#### Pré-requisito

`services/scanner-worker` tem quatro conexões que abrem transação **sem**
`SET LOCAL ROLE` (`main.py::_warm`, `refresh.py` ×3): hoje elas funcionam
porque o login é o dono, e sob `hunter_runtime` respondem *permission denied
for table feature_baselines*. Elas precisam do `SET LOCAL ROLE hunter_worker`
como primeiro statement da transação **antes** do passo (d)
(docs/DATABASE.md §27.5). Os passos (a)–(c) podem ser feitos a qualquer
momento; nada muda até o (d).

#### (a) aplicar a `0015` — deploy normal

```bash
ssh hunter-vps "cd /opt/project-hunter && git pull && bash infra/vps/compose.sh update"
```

O serviço `migrate` roda `alembic upgrade head` em todo `update`. Depois disso
o papel existe e não consegue conectar (não tem senha). Nada mais mudou: o
`api` e os workers continuam com o `DATABASE_URL` de dono.

#### (b) o operador define a senha, na VPS

Gere a senha na própria VPS e aplique-a com uma conexão de dono. Ela **não**
passa por chat, por log de agente nem pelo repositório — e, desde a revisão de
segurança da T3.15f (MÉDIA 3), **não passa por `argv` nenhum**.

**A forma preferida é `\password`, e ela é a única que não põe a senha em lugar
nenhum além da sua digitação:** o `psql` faz o hash SCRAM-SHA-256 do lado do
cliente e manda para o servidor `ALTER ROLE … PASSWORD 'SCRAM-SHA-256$…'`. O
texto puro não entra na linha de comando, não entra no `~/.psql_history` (o
metacomando `\password` é gravado sem o valor) e não entra num eventual
`log_statement = 'all'` do servidor.

```bash
ssh hunter-vps
cd /opt/project-hunter

# gere a senha e ponha-a no .env primeiro (passo (c)); depois cole-a aqui
bash infra/vps/compose.sh exec postgres psql -U hunter -d hunter
# no prompt do psql (ele pede duas vezes, e não ecoa):
#   \password hunter_runtime
#   \q
```

**Sem TTY (script, sessão não interativa), o SQL vai por stdin — nunca por
`-c`/`-v`:**

```bash
{ printf "ALTER ROLE hunter_runtime PASSWORD '"
  sed -n 's/^HUNTER_RUNTIME_DB_PASSWORD=//p' .env | head -1 | tr -d '\n'
  printf "';\n"
} | bash infra/vps/compose.sh exec -T postgres psql -U hunter -d hunter -q
```

Por que isto e não `psql -v pw="$RUNTIME_PW"`, que é o que esta seção mandava
até 2026-09-08: um argumento de linha de comando é legível em
`/proc/<pid>/cmdline` por **qualquer** usuário da máquina enquanto o comando
roda — o aviso sobre o histórico do shell (que continua valendo) cobria a
metade errada do problema. A forma por stdin lê o valor que já está no `.env`
(600, do dono), então não há segunda cópia a limpar; ela pressupõe uma senha
sem aspas simples, que é o caso de `openssl rand -hex` e do
`infra/scripts/setup_env.sh`.

Se preferir gerar aqui em vez de no `setup_env.sh`, gere **direto no `.env`**
(`printf 'HUNTER_RUNTIME_DB_PASSWORD=%s\n' "$(openssl rand -hex 24)" >> .env`)
e siga com o bloco de stdin acima: a senha nunca fica numa variável de sessão.

#### (c) a chave no `.env`

```bash
# no .env da VPS (600, nunca commitado)
HUNTER_RUNTIME_DB_PASSWORD=<a mesma senha do passo (b)>
```

`bash infra/scripts/setup_env.sh --vps` gera a chave quando o `.env` é criado ou
regerado, e **preserva** a existente numa reexecução, exatamente como faz com
`POSTGRES_PASSWORD`. Se o `.env` foi gerado antes desta tarefa, acrescente a
linha à mão — e use no passo (b) o mesmo valor.

**(b) e (c) podem trocar de ordem; o que não pode é os dois valores
diferirem.** A forma por stdin do passo (b) lê a senha *do `.env`*, então nesse
caminho o (c) vem primeiro; a forma `\password` a lê da sua digitação, e aí
tanto faz. Nada acontece até o (d) de qualquer jeito: enquanto o `DATABASE_URL`
nomear o dono, a senha do `hunter_runtime` não é usada por processo nenhum.

#### (d) subir com a DSN nova

```bash
ssh hunter-vps "cd /opt/project-hunter && bash infra/vps/compose.sh update"
```

`x-prod-db-env` passa a montar o `DATABASE_URL` a partir de
`HUNTER_RUNTIME_DB_PASSWORD`; `migrate` e `ops` continuam com
`x-prod-owner-env` (a DSN de dono), que é o único lugar onde ela ainda existe.

#### (e) verificar de dentro do `api`

```bash
bash infra/vps/compose.sh exec -T api python -c "
import asyncio, os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def main() -> None:
    engine = create_async_engine(os.environ['DATABASE_URL'],
                                 connect_args={'statement_cache_size': 0})
    async with engine.connect() as c:
        print((await c.execute(text(
            'SELECT current_user, r.rolsuper, r.rolbypassrls, r.rolcreaterole, r.rolinherit '
            'FROM pg_roles r WHERE r.rolname = current_user'))).one())
    await engine.dispose()

asyncio.run(main())
"
```

Esperado: `('hunter_runtime', False, False, False, False)`. Qualquer `True` ali,
ou qualquer outro `current_user`, quer dizer que o passo (d) não pegou — o
achado continua aberto e o `.env`/compose precisam ser conferidos antes de
declarar o contrário.

**`bash infra/vps/compose.sh exec …`, nunca `docker compose -p hunter exec …`**
(revisão de segurança da T3.15f, BAIXA 6). Não há `docker-compose.yml` na raiz
do repositório: o stack de produção é a soma dos **dois** arquivos, na ordem
certa, mais o `--env-file` — que é a razão de existir do wrapper. `exec` cai no
catch-all dele e recebe os dois `-f` de graça. Improvisar isso no meio de uma
troca de credencial é o pior momento para descobrir que faltava um `-f`.

Duas verificações de recusa, opcionais e baratas, **e nenhuma delas precisa da
senha**: elas rodam pela conexão que o `api` já tem aberta, que é justamente o
que se quer provar.

```bash
bash infra/vps/compose.sh exec -T api python -c "
import asyncio, os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

REFUSALS = [
    ('hunter_app',    'ALTER TABLE portfolios DISABLE ROW LEVEL SECURITY'),
    ('hunter_worker', \"UPDATE strategy_versions SET purpose = 'paper'\"),
]

async def main() -> None:
    engine = create_async_engine(os.environ['DATABASE_URL'],
                                 connect_args={'statement_cache_size': 0})
    for role, statement in REFUSALS:
        async with engine.begin() as c:
            await c.execute(text(f'SET LOCAL ROLE {role}'))
            try:
                await c.execute(text(statement))
                print('FALHOU (aceito!):', statement)
            except Exception as exc:                      # noqa: BLE001
                print('recusado, como esperado:', str(exc).splitlines()[0])
    await engine.dispose()

asyncio.run(main())
"
```

As duas têm de recusar (`must be owner of table portfolios` e *permission
denied*), e são as mesmas duas do teste de integração
(`packages/core/tests/integration/test_runtime_login_role.py`). A forma antiga
desta verificação abria um `psql` com a senha **na URL de conexão, em `argv`** —
pelo mesmo motivo do passo (b), não faça isso; e aqui não é sequer necessário,
porque provar a recusa *pela conexão do `api`* é uma prova mais forte do que
prová-la por uma conexão que o operador montou à mão.

#### Rollback

**Volte a DSN, não a migração.** Reverter a `0015` com o `DATABASE_URL` ainda
nomeando `hunter_runtime` deixa `api` e todo worker sem alcançar tabela
nenhuma. O caminho seguro é o inverso do passo (d):

1. no `.env`, comente/remova `HUNTER_RUNTIME_DB_PASSWORD` e devolva o
   `DATABASE_URL` de dono no compose (ou faça `git checkout` do compose para o
   commit anterior);
2. `bash infra/vps/compose.sh update`;
3. só então, e só se houver motivo, `alembic downgrade -1` pelo `migrate`.

O papel pode ficar de pé sem problema: sem a senha em uso e — depois do
downgrade — sem membership nenhuma, ele não alcança nada (docs/DATABASE.md
§27.4).

**Depois de qualquer downgrade da `0015`, refaça o passo (b) antes de voltar à
DSN nova.** Na VPS (um banco só, papel sem objetos) o downgrade **derruba** o
papel, e a senha vai junto; o `alembic upgrade head` que todo `compose.sh
update` roda o recria **sem senha**, enquanto o `HUNTER_RUNTIME_DB_PASSWORD`
continua no `.env`, com a cara de estar certo. O sintoma é `api` e **todos** os
workers falhando autenticação no boot, com um `.env` e um compose que parecem
corretos. Refazer o passo (b) é `ALTER ROLE` com o valor que já está no `.env`
— não gere uma senha nova, senão o (c) também tem de mudar. O downgrade avisa
disso na saída da migração desde a revisão de segurança da T3.15f (MÉDIA 2),
mas um `NOTICE` no meio de um log de deploy não é o controle; esta linha é.

## 4. CI (GitHub Actions)

`ci.yml` em cada PR e push na `main`:

1. `python-lint` — ruff, ruff format --check, pyright, file-size gate.
2. `python-lint-strict` — tier estrito (`packages/config/ruff.strict.toml`), não bloqueia; conta de violações no job summary.
3. `python-test` — pytest (`unit` + `integration`) com testcontainers.
4. `migrations` — `alembic upgrade head` em banco limpo, `alembic check` (sem drift entre models e migrações), `alembic downgrade -1 && upgrade head`, `create_partitions.py --dry-run`.
5. `node` — eslint, `tsc --noEmit`, vitest, `next build`.
6. `types-drift` — gera `packages/shared-types` do OpenAPI e falha se houver diff não commitado.
7. `e2e` — Playwright contra `docker compose`; sempre roda (`signup-onboarding.spec.ts` se autoexclui sem `CLERK_E2E_*`).
8. `security` — `gitleaks`, `pip-audit --skip-editable`, `bandit`, `pnpm audit --audit-level high`.
9. `forbidden-patterns` — falha se aparecer `sqlite`, `localhost` fora de config de dev/testes, escrita de JSON de estado, `print(` em código de produção.
10. `docker-build` — build das duas imagens (guardado até `infra/docker/Dockerfile.*` existir — já existe desde o M0).
11. `gate` — status obrigatório; verde só se todo job acima, exceto o `-strict`, passou.

Deploy só roda se o `gate` passou. `deploy-api.yml` faz `railway up` por serviço (ou `fly deploy`); `deploy-web.yml` é a integração nativa da Vercel — os dois existem hoje só como esboço (T10), sem execução real documentada. Migrações rodam como job separado **antes** dos serviços novos subirem (`alembic upgrade head` com lock em Redis, quando o deploy automático existir).

## 5. Operação

- Escala: market-worker por número de mercados (1 processo por ~400 mercados); scanner por CPU; strategy e execution 1 réplica cada no MVP (consumer groups permitem N depois); api por conexões WS.
- Health: `/health` (processo vivo), `/ready` (Postgres e Redis alcançáveis). Railway/Fly usam `/ready`.
- Alarmes mínimos: worker `stale` > 60 s; lag de stream > 5 000; erro de exchange > 10/min; partição faltando; Sentry error rate.
- Backups: Neon PITR (7 dias no plano padrão); exportação semanal de `trades`, `audit_logs`, `risk_events` para object storage (Fase 2).

### 5.1 Monitoração (`/metrics`, por processo — T3.13)

Cada processo expõe `hunter_*` no seu próprio `HEALTH_PORT` (`api` usa a
própria `API_PORT`), registro compartilhado `hunter_core.observability.registry`
(Prometheus, atrás de `METRICS_TOKEN` na `api`; sem porta publicada no host nos
demais papéis — só a rede interna do compose alcança). Confirmado ao vivo no
stack local (`docker exec <container> ... /metrics`):

**`execution-worker`** (`hunter_execution_worker/metrics.py`):

| Métrica | Tipo | Rótulos | O que mede |
|---|---|---|---|
| `hunter_execution_orders_total` | Counter | `kind` (entry/exit), `outcome` | tentativas de execução |
| `hunter_execution_protection_delay_seconds` | Gauge | — | segundos desde que a proteção degradada mais antiga passou a esperar um livro — o "atraso de proteção" |
| `hunter_execution_mtm_age_seconds` | Gauge | — | segundos desde o último ponto gravado da curva de equity — o "atraso do MTM" |
| `hunter_execution_pending_degraded_total` | Counter | `reason` | tentativas de proteção sem livro utilizável |
| `hunter_execution_reservations_total` | Counter | `state` | ciclos de reserva fechados, por estado terminal |
| `hunter_execution_pending_requests` | Gauge | `readable` | pedidos arquivados aguardando decisão |

O atraso de outbox **não** tem métrica própria hoje: só o booleano
`outbox_not_lagging` de `/ready` (abaixo) e o heartbeat `hb:execution:paper`
(sem um campo de contagem/atraso do outbox — ver `apps/api/hunter_api/schemas/
system.py`, seção "o que deliberadamente não está aqui"). Registrado como
lacuna para quem tocar `hunter_execution_worker/heartbeat.py` a seguir
(T3.14 em voo).

`/ready` do `execution-worker` (5 checks + `database`/`redis`, confirmado ao
vivo): `{"database":true,"redis":true,"paper_schema":true,
"kill_switch_legible":true,"mtm_fresh":true,"protection_prompt":true,
"outbox_not_lagging":true}`.

**Coletor de câmbio USDTBRL** (`hunter_market_worker/fx.py`, T3.11a, roda
dentro do `market-worker` shard 0):

| Métrica | Tipo | Rótulos | O que mede |
|---|---|---|---|
| `hunter_fx_observations_total` | Counter | `outcome` (ok/duplicate/malformed/rate_limited/network_error/error) | coletas da cotação, por desfecho |
| `hunter_fx_implausible_total` | Counter | — | cotação gravada fora da banda `[1, 100]` |
| `hunter_fx_age_seconds` | Gauge | — | idade da última coleta bem-sucedida |

`WorkerRuntime.status_details["fx"]` no `/ready` do `market-worker` (shard 0)
é `"ok"`/`"stale"`/`"unknown"` — **detalhe, nunca check de prontidão**: uma
cotação velha não derruba `/ready` (a carteira pode não abrir; a coleta de
mercado continua).

**Fonte SPOT** (`hunter_market_worker/spot.py`, T3.0c): sem família de
métrica própria (`hunter_spot_*` não existe hoje — os contadores de
persistência/backfill que o SPOT usa são os genéricos, sem rótulo por
mercado). A visibilidade operacional de hoje é o *status detail*
`WorkerRuntime.status_details["spot"]` no `/ready` do `market-worker`:
`"connected"` | `"degraded"` (socket spot reconectando com o perpétuo saudável)
| `"absent"` (shard != 0, ou `MARKET_SPOT_ENABLED=false`) — nunca um check de
prontidão, pelo mesmo motivo do `fx`: o caminho perpétuo é o que o M2 inteiro
depende, e um socket spot reconectando não pode derrubar o coletor inteiro.
Registrado como lacuna (sem métrica numérica de idade/erro do SPOT) para quem
continuar a T3.0/T3.M.

### 5.2 Replay histórico — como rodar e quanto custa (T3.19b)

Job, não serviço. Contrato em `docs/PIPELINE.md` §6c; nada aqui ativa nada nem chega à carteira.

```bash
# uma corrida, direto (a partir do repo, com o .env da máquina)
uv run python -m hunter_strategy_worker.replay.run \
    --version volume_anomaly:v2 --from 2026-08-08 --to 2026-09-08 \
    --markets all --workers 3 --ledger /opt/hunter/replay.jsonl

# o que seria feito, sem escrever nada
uv run python -m hunter_strategy_worker.replay.run --version momentum:v2 \
    --from 2026-08-08 --to 2026-09-08 --markets all --dry-run

# drenar a fila que o plantão enfileirou (replay:queue no Redis)
uv run python -m hunter_strategy_worker.replay.run --drain-queue --max-runs 1
```

Janelas longas devem ser **fatiadas** (`--from/--to` em pedaços, mesmo `--cohort`): a janela é
semiaberta, o `signal_id` é `uuid5` e o INSERT é `ON CONFLICT DO NOTHING`, então repetir uma fatia
não duplica nada — mas cada comando termina, grava seu recibo e libera a máquina.

**Orçamento (`REPLAY_*`, todos opcionais):**

| Variável | Padrão | O que faz |
|---|---|---|
| `REPLAY_CPU_SHARE` | `0.33` | fração das vCPU que o pool pode usar. `floor(12 × 0,33) = 3` processos na VPS, deixando nove para coleta/scanner/estratégia/execução |
| `REPLAY_MAX_WORKERS` | `4` | teto absoluto, para uma máquina maior não virar um experimento maior sem alguém decidir |
| `REPLAY_MAX_CONCURRENT_RUNS` | `1` | duas corridas entrelaçadas tornam o número de throughput das duas ininterpretável |
| `REPLAY_PAUSE_ON_DEGRADED` | `true` | lê `hb:strategy:shadow` antes de cada corrida e pausa com motivo (`heartbeat_missing`, `heartbeat_stale:<s>`, `outbox_lag:<s>`, `heartbeat_unreadable`) |
| `REPLAY_HEARTBEAT_MAX_AGE_S` | `60` | o worker vivo escreve a cada 10 s com TTL 60 |
| `REPLAY_OUTBOX_LAG_MAX_S` | `60` | espelha `SHADOW_OUTBOX_LAG_ALERT_S` |
| `REPLAY_QUEUE_KEY` | `replay:queue` | lista Redis, `LPUSH`/`RPOP` |

**Contexto por versão (`SHADOW_CONTEXT_*`, opcionais; `hunter_strategy_worker/config.py`, T3.54b/c — conceito em `docs/PIPELINE.md` §6b):**

| Variável | Padrão | O que faz |
|---|---|---|
| `SHADOW_CONTEXT_MINUTES` | `1560` | piso de minutos de 1m carregados por avaliação — nenhuma versão lê menos que isto, mesmo pedindo menos |
| `SHADOW_CONTEXT_MAX_MINUTES` | `6000` | teto sobre o mesmo requisito — uma versão acima dele é recusada na ativação, nunca ativada muda |

**Custo medido (2026-09-08, prova real; detalhes e ressalvas em `.claude/state/notes-T3.19b.md`):**

| Medida | Valor |
|---|---|
| Round trip até o Postgres, PC de dev (Docker Desktop/Windows, loopback) | **44,88 ms** |
| Statements SQL por barra replayada | **11,25** (≈ 14,5 round trips com BEGIN/COMMIT) |
| CPU por barra (cache de janela quente): `build_context` + `explain` | **4,04 + 2,62 = 6,7 ms** |
| Corrida real: momentum v2 (15 m), 31 dias × 3 mercados | **8 928 barras, 1 820 s, 4,90 barras/s** com 3 processos |
| Linhas de `shadow_outbox` produzidas por cinco coortes de replay | **0** |

O número do PC é **latência de rede**, não algoritmo: 14,5 × 44,88 ms ≈ 651 ms dos 654 ms medidos
por barra. Na VPS o Postgres é um contêiner na mesma máquina (§9), com round trip da ordem de
0,3 ms, e a barra passa a ser limitada por CPU:

```
barra_vps ≈ 15 ms de CPU (6,7 ms medidos, com margem de 2x para a vCPU da Contabo)
          + 14,5 × 0,3 ms de round trip
          ≈ 20 ms  →  ~50 barras/s por processo  →  ~150 barras/s com 3 processos
```

**~10,8 milhões de barras avaliadas por dia** com 20 h/dia de replay — 21 × a meta de 500 mil. Em
*operações simuladas com entrada e desfecho* a densidade medida é 1,2 % (5 m) a 1,8 % (15 m) dos
bars avaliados, o que dá **~160 mil/dia**: a meta de 500 mil operações fechadas por dia exigiria
~3,2 × este orçamento (≈ 10 vCPU dedicadas, o que faminta a faixa viva). Ver `docs/plans/REPLICATION.md`
§9 e as notas para a aritmética completa e as alavancas.

**Regra de convívio:** o replay nunca compete com a coleta. Se `/ready` do `strategy-worker` ou do
`market-worker` estiver vermelho, ou o heartbeat estiver velho, o job pausa sozinho; se for preciso
parar à mão, basta não drenar a fila — nada fica pela metade (cada fatia commita a sua).

## 6. Playbook de incidente

| Sintoma | Ação |
|---|---|
| Exchange offline | Nada automático além de `data_degraded`; entradas bloqueadas por check 3; posições geridas com último preço; se > 60 s em posição → risk event |
| Redis fora | Workers pausam consumo, mantêm buffer 60 s, marcam `degraded`; api serve REST do Postgres, WS envia `degraded`; ao voltar, hot state reconstrói do Postgres (candles) e das exchanges (book) |
| Postgres lento | Escritas de market data em lote com fila limitada; propostas não são decididas sem persistir (bloqueia entradas); alarme |
| Execution-worker morto | Nenhuma ordem nova; ao subir, reconstrói posições abertas; propostas aprovadas antigas expiram |
| Perda súbita anormal | OWNER aciona kill switch da org (`TRADING_DISABLED`); operador pode acionar `SYSTEM_KILL_SWITCH` |
| Suspeita de vazamento de tenant | Revogar sessão no Clerk; auditar `audit_logs` por `request_id`; RLS é a barreira final |

## 7. Variáveis de ambiente

Fonte da verdade: `packages/core/hunter_core/settings.py` (`Settings`, lido por
`api` e por todo worker) e `apps/api/hunter_api/settings.py` (`ApiSettings`,
estende `Settings` só para `HUNTER_ROLE=api`). `.env.example` espelha os dois
1:1. `Settings._require_settings_in_prod` recusa subir (`ValueError` na
construção) em `HUNTER_ENV=staging|production` se faltar qualquer variável
marcada **obrigatória** abaixo — as demais têm default de dev seguro.

### Ambiente e processo (api + todo worker)

| Variável | Obrigatória em prod? | Default | Propósito |
|---|---|---|---|
| `HUNTER_ENV` | não | `development` | `development \| test \| staging \| production`; só `production` ativa `is_production` (ex.: fecha `/docs`) |
| `HUNTER_ROLE` | não | `all` | `api \| market \| scanner \| strategy \| execution \| analytics \| all` — escolhe o processo no `entrypoint.sh`. Workers ainda saem com 0 no M0 (`RoleRegistry` vazio até M1) |
| `LOG_LEVEL` | não | `INFO` | nível do `structlog` |
| `WEB_ORIGIN` | **sim** | `http://localhost:3000` | origem(ns) do web, separadas por vírgula; base do CORS quando `CORS_ALLOWED_ORIGINS` não é setado |
| `API_URL` | **sim** | `http://localhost:8000` | usado pelo web server-side (`lib/server/api.ts`) |
| `NEXT_PUBLIC_API_URL` | **sim** | `http://localhost:8000` | base da API para o browser |
| `NEXT_PUBLIC_WS_URL` | **sim** | `ws://localhost:8000/ws` | endpoint do WebSocket para o browser |
| `HEALTH_PORT` | não | `8001` | porta de `/health`, `/ready`, `/metrics` nos processos `HUNTER_ROLE != api` (a `api` expõe os três na própria `API_PORT`) |

### Só `apps/api` (`ApiSettings`)

| Variável | Obrigatória em prod? | Default | Propósito |
|---|---|---|---|
| `API_PORT` | não | `8000` | porta HTTP do uvicorn |
| `CORS_ALLOWED_ORIGINS` | não | cai para `WEB_ORIGIN` | allowlist exata do middleware CORS, uma ou mais origens separadas por vírgula |
| `RATE_LIMIT_PER_MINUTE` | não | `120` | limite por endereço, antes do roteamento — cobre a superfície não autenticada |
| `RATE_LIMIT_PER_MINUTE_PRINCIPAL` | não | `600` | limite por principal autenticado, checado após verificar o token |
| `RATE_LIMIT_PER_MINUTE_INTERNAL` | não | `6000` | limite por endereço para um peer listado em `INTERNAL_PEER_IPS` (T3.28a) — ver nota abaixo |
| `INTERNAL_PEER_IPS` | não | vazio | endereços TCP separados por vírgula que recebem `RATE_LIMIT_PER_MINUTE_INTERNAL` em vez de `RATE_LIMIT_PER_MINUTE`; setado direto no compose (IP fixo do `web`), nunca no `.env` — ver nota abaixo |
| `ENABLE_OPENAPI_DOCS` | não | `false` | em `HUNTER_ENV=production`, reabre `/docs`, `/redoc`, `/openapi.json` se `true`; em dev/staging ficam sempre abertos |
| `READY_CHECK_TIMEOUT_S` | não | `3.0` | timeout por dependência (Postgres/Redis) em `/ready` |
| `FORWARDED_ALLOW_IPS` | não | `127.0.0.1` | em produção, apontar para o ingress da plataforma — só esse IP tem `X-Forwarded-For` confiado pelo uvicorn |
| `METRICS_TOKEN` | não | vazio | se setado, `/metrics` exige `Authorization: Bearer <token>`; vazio em staging/produção desativa `/metrics` (404) |
| `MAX_REQUEST_BODY_BYTES` | não | `1048576` | limite de corpo em `/api/*`, checado no `Content-Length` e nos bytes efetivamente recebidos |
| `JWKS_REFRESH_COOLDOWN_S` | não | `60.0` | intervalo mínimo entre dois refetches do JWKS disparados por um `kid` desconhecido |
| `JWKS_MAX_STALE_S` | não | `86400.0` | por quanto tempo o JWKS em cache continua valendo enquanto todo refetch falha; depois disso a auth responde 503 |
| `WEBHOOK_CLAIM_STALE_S` | não | `300.0` | tempo que um claim em `processed_events` pode ficar inacabado antes de uma redelivery poder retomá-lo |
| `WS_HANDSHAKES_PER_MINUTE` | não | `30` | handshakes `/ws` por endereço por minuto, checado antes do `accept()`; excedente → 4429 |
| `WS_MAX_CONNECTIONS_PER_PRINCIPAL` | não | `5` | conexões `/ws` vivas por principal neste processo; excedente fecha com 4429 |
| `WS_REVALIDATE_INTERVAL_S` | não | `60.0` | de quanto em quanto tempo um WS aberto revalida a associação do principal; perda de acesso fecha com 4403 |

### Banco e cache

| Variável | Obrigatória em prod? | Default | Propósito |
|---|---|---|---|
| `DATABASE_URL` | **sim** | `postgresql+asyncpg://hunter:hunter@localhost:5432/hunter` | engine assíncrono (SQLAlchemy 2 + asyncpg) |
| `DATABASE_URL_MIGRATIONS` | não | `postgresql://hunter:hunter@localhost:5432/hunter` | conexão direta (sem pooler) só para o Alembic |
| `HUNTER_RUNTIME_DB_PASSWORD` | **sim** a partir da T3.15f | vazio | senha do login `hunter_runtime` que o `DATABASE_URL` de `api`/workers usa. Gerada por `setup_env.sh --vps`; aplicada no banco pelo operador (`ALTER ROLE`), nunca pela migração — §3.5 e docs/DATABASE.md §27 |
| `REDIS_URL` | **sim** | `redis://localhost:6379/0` | Streams + pub/sub |
| `DB_POOL_SIZE` | não | `5` | tamanho do pool do engine assíncrono |
| `DB_MAX_OVERFLOW` | não | `5` | conexões extras além do pool sob carga |

### Auth (Clerk)

| Variável | Obrigatória em prod? | Default | Propósito |
|---|---|---|---|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | web precisa para funcionar (não validado pelo `Settings` do backend) | vazio | chave pública do Clerk, para o browser |
| `CLERK_SECRET_KEY` | **sim** | vazio | chamadas server-side ao Clerk (provisioning just-in-time) |
| `CLERK_WEBHOOK_SECRET` | **sim** — só quando a API é pública (webhook `user.created/updated/deleted` do Clerk chega por HTTP) | vazio | verificação Svix do webhook |
| `CLERK_JWKS_URL` | **sim** | vazio | `https://<instance>.clerk.accounts.dev/.well-known/jwks.json`, cache de chaves para verificar JWT |
| `CLERK_ISSUER` | **sim** | vazio | `iss` esperado no JWT |

### Segredos de aplicação (reservados — nenhum código de produto os lê ainda)

| Variável | Obrigatória em prod? | Default | Propósito |
|---|---|---|---|
| `AUTH_SECRET` | não (ainda) | vazio | assinatura de tokens internos (tickets de WS, convites) — reservado, nenhum caminho de código o usa no M0 |
| `HUNTER_MASTER_KEY` | não (ainda) | vazio | dev: base64 de 32 bytes; prod: KMS. Reservado |
| `KMS_KEY_ID` | não (ainda) | vazio | Fase 3. Reservado |

### Observabilidade e produto

| Variável | Obrigatória em prod? | Default | Propósito |
|---|---|---|---|
| `SENTRY_DSN` | não | vazio | sem DSN = Sentry desligado |
| `SENTRY_ENVIRONMENT` | não | `development` | tag de ambiente no Sentry |
| `NEXT_PUBLIC_POSTHOG_KEY` | não | vazio | sem chave = PostHog desligado |
| `NEXT_PUBLIC_POSTHOG_HOST` | não | `https://us.i.posthog.com` | host do PostHog |

### LLM (Fase 2 — ADR `docs/decisions/0002-camada-de-provedores-llm.md`)

Nenhuma destas alimenta o produto no M0 (`hunter_core.llm` ainda não existe;
`ENABLE_LLM_ANALYSIS=false`). `OPENAI_API_KEY`/`OPENAI_MODEL` já têm um
consumidor hoje, mas é **ferramenta de desenvolvimento**, não o produto: o
executor Astra (`infra/scripts/ask_astra.py`, Codex CLI) os lê para pedir uma
segunda opinião fora do fluxo de execução do Claude Code — nunca no caminho
AGENT → PROPOSAL → RISK → EXECUTION (`CLAUDE.md`).

| Variável | Obrigatória em prod? | Default | Propósito |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | não | vazio | reservado para `hunter_core.llm.AnthropicProvider` (Fase 2); não lido por nenhum código no M0 |
| `ANTHROPIC_MODEL` | não | `claude-opus-5` | idem |
| `OPENAI_API_KEY` | não | vazio | **hoje:** só `infra/scripts/ask_astra.py` (dev tooling, opcional, pedido pelo `setup_env.ps1`). **Fase 2:** `hunter_core.llm.OpenAIProvider` |
| `OPENAI_MODEL` | não | `gpt-6-astra` | idem |
| `LLM_PROVIDER` | não | `anthropic` | seleção de provedor (`anthropic \| openai`) para a Fase 2; nenhum código o lê no M0 |
| `LLM_MODEL` | não | vazio (usa o default do provedor) | idem |

### Exchanges (opcionais no MVP)

| Variável | Obrigatória em prod? | Default | Propósito |
|---|---|---|---|
| `BINANCE_API_KEY` / `BINANCE_API_SECRET` | não | vazio | só elevam rate limit de dados públicos; nunca com permissão de saque; usados a partir do M1 |
| `BYBIT_API_KEY` / `BYBIT_API_SECRET` | não | vazio | idem |

### Feature flags de sistema

| Variável | Obrigatória em prod? | Default | Propósito |
|---|---|---|---|
| `ENABLE_LIVE_TRADING` | não | `false` | live trading; `LiveExecutionAdapter` levanta `LiveTradingDisabled` enquanto for `false` (sempre, até a Fase 4) |
| `ENABLE_SOCIAL_INTELLIGENCE` | não | `false` | Fase 2 |
| `ENABLE_ONCHAIN` | não | `false` | Fase 3 |
| `ENABLE_STRIPE` | não | `false` | Fase 3 |
| `ENABLE_LLM_ANALYSIS` | não | `false` | Fase 2 |
| `ENABLE_ARENA` | não | `false` | M6 |
| `ENABLE_BACKTESTS` | não | `false` | M6 |
| `SYSTEM_KILL_SWITCH` | não | `ACTIVE` | `ACTIVE \| WARNING \| TRADING_DISABLED \| EMERGENCY` — estado inicial do kill switch de sistema (o motor que o transiciona chega no M4) |

### Dimensionamento

| Variável | Obrigatória em prod? | Default | Propósito |
|---|---|---|---|
| `MARKET_UNIVERSE_SIZE` | não | `200` | tamanho do universo de mercados monitorados (M1) |
| `MARKET_SHARD` | não | `0/1` | fatia do universo deste processo, `i/N` (T1.6b-C, T2.5g) |
| `MARKET_SHARDS` | não | `1` | só no compose: quantos shards o perfil `shards` sobe (§3.1) |
| `BOOK_DEPTH` | não | `25` | níveis de book capturados (M1) |
| `TICK_COALESCE_MS` | não | `250` | janela de coalescência de ticks (M1) |
| `FEATURE_THROTTLE_MS` | não | `1000` | cadência de cálculo de features (M2) |
| `RADAR_PUSH_MS` | não | `1000` | cadência de push do Radar (M2) |
| `RETENTION_CANDLES_1M_DAYS` | não | `90` | retenção de candles de 1 minuto |
| `RETENTION_FEATURE_SNAPSHOTS_DAYS` | não | `14` | retenção de snapshots de features |

## 8. Comandos locais reais

Do zero, nesta ordem (`docs/plans/M0.md` tem os pré-requisitos de máquina —
Node 22, pnpm, uv, Docker Desktop):

```powershell
# 1. dependências
pnpm install
uv sync --all-packages

# 2. .env local — pede as chaves do Clerk na tela (nunca aparecem em chat/log)
powershell -ExecutionPolicy Bypass -File infra\scripts\setup_env.ps1

# 3. stack (postgres, redis, migrate, api, worker, web) via Docker
docker compose -f infra/docker/docker-compose.yml up -d --build

# variante: só a infraestrutura de dados, para rodar api/web fora do compose
docker compose -f infra/docker/docker-compose.yml up -d postgres redis migrate api
```

`migrate` roda uma vez (`HUNTER_COMMAND=migrate`, ver abaixo) e sai; `api`
espera `service_completed_successfully` dele. `worker` (`HUNTER_ROLE=all`)
sobe e sai com 0 de propósito — sem entrypoint real até o M1.

### Web fora do compose (`pnpm dev`)

Para desenvolver o Next.js com hot reload real (o compose builda uma imagem
`standalone`, sem watch):

```bash
cd apps/web
API_URL=http://localhost:8000 \
NEXT_PUBLIC_API_URL=http://localhost:8000 \
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws \
WEB_ORIGIN=http://localhost:3000 \
pnpm dev
```

As chaves do Clerk (`NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`)
vêm do `.env` da raiz — o Next.js já o lê automaticamente (`dotenv` embutido).
`apps/api` precisa estar de pé (compose, passo 3, serviços `postgres redis
migrate api`) para o `api-client` e o SSR terem o que chamar.

### Migrate e seed manuais (`HUNTER_COMMAND`)

`migrate`/`seed` não são valores de `HUNTER_ROLE` (que só aceita os papéis
reais de processo) — são acionados pela variável separada `HUNTER_COMMAND`,
lida primeiro pelo `entrypoint.sh`:

```bash
# upgrade head dentro da rede do compose (reaproveita a imagem hunter-api:dev)
docker compose -f infra/docker/docker-compose.yml run --rm migrate

# comando explícito também funciona (um argumento sempre vence o dispatch de role)
docker compose -f infra/docker/docker-compose.yml run --rm migrate \
  alembic -c infra/migrations/alembic.ini check

docker compose -f infra/docker/docker-compose.yml run --rm \
  -e HUNTER_COMMAND=seed migrate
```

Rodar o Alembic direto do host (`uv run alembic -c infra/migrations/alembic.ini
upgrade head`) só funciona se `DATABASE_URL_MIGRATIONS` apontar para um
Postgres alcançável do host — o `postgres` do `docker-compose.yml` **não**
publica a porta 5432 no host de propósito (só os serviços do próprio compose
o alcançam). Para isso, ou use `docker-compose.test.yml` (expõe
`localhost:55432`, ver `infra/docker/docker-compose.test.yml`), ou rode via
`docker compose run --rm migrate` acima.

### Partições diárias (serviço `ops`)

`infra/scripts/create_partitions.py` mantém as partições mensais três meses à
frente (DATABASE.md §1.3); sem um agendamento real, em 2027-01 o primeiro
insert falharia com `no partition of relation "candles_1m" found for row`
(docs/plans/M1.md, pendência "Agendamento real das partições"). O script
conecta com `DATABASE_URL_MIGRATIONS`, a DSN de dono (`migration_url()`) —
desde a T3.15d/T3.15e ela só existe no ambiente de `migrate` e do serviço
`ops` (§3.4), nunca no de `api`. Roda pelo `ops`, chamando o script
diretamente (não por `HUNTER_COMMAND=partitions`/`infra/docker/entrypoint.sh`
— `ops` tem `entrypoint: []`, então o comando depois do nome do serviço já é
o processo, sem passar pelo dispatch de papel):

```bash
bash infra/vps/compose.sh ops python infra/scripts/create_partitions.py
```

(equivalente em dev, sem `compose.sh`: `docker compose -f
infra/docker/docker-compose.yml run --rm ops python
infra/scripts/create_partitions.py`.) `ops` não declara `depends_on: migrate`
como `api` declara — só `postgres: condition: service_healthy` — então este
comando nunca dispara `alembic upgrade head` de lado, com ou sem `--no-deps`;
a antiga necessidade de `--no-deps` (evitar que `docker compose run` subisse
o `depends_on` de `api` e rodasse a migração dona do schema junto, todo dia,
sem release nem supervisão) não existe mais no `ops` porque a única
dependência dele é o Postgres estar de pé.

Idempotente (`CREATE TABLE IF NOT EXISTS ... PARTITION OF`): rodar de novo sem
nada de novo para criar não faz nada. Cada `CREATE`/`ALTER` roda dentro de uma
transação com `SET LOCAL lock_timeout = '3s'` e `SET LOCAL TimeZone = 'UTC'`
(docs/plans/M1.md, "D4 —" e "D12 —"): um grupo que não consegue o lock
`ACCESS EXCLUSIVE` em 3 s é logado (structlog) e pulado, não derruba o run
inteiro, e o processo sai com código **75** (`EX_TEMPFAIL` de `sysexits.h`) se
algo foi pulado — a rodada seguinte, agendada, tenta de novo. Um `DBAPIError`
não tratado (qualquer outro erro de banco) propaga e termina o processo com o
código **1** padrão do Python; os dois nunca compartilham código, exatamente
para que o status de saída sozinho, sem ler o log, já diga "skip de rotina"
de "erro real". O agendamento real (cron diário na VPS) está documentado em
`infra/vps/README.md`, seção "Partições diárias".

### Profundidade de histórico para o β (`request_backfill.py`)

`beta_v1` mede 30 dias de retornos horários e só é válido com **20 dias
ininterruptos** terminando no corte (`docs/PIPELINE.md` §2b). Em 2026-09-08 a
VPS tinha 11 dias distintos de `candles`, então toda linha de `market_betas`
sairia `insufficient_history` e a admissão responderia `unavailable` para todo
candidato. Quem fecha essa lacuna é o **coletor** — o scanner e este script
nunca chamam REST (decisão conjunta do M2): o script publica
`market.backfill.requested` pela outbox e o `market-worker` planeja e busca sob
o orçamento que já é dele (§1b do `PIPELINE.md`).

```bash
# 1. as partições dos meses para trás têm de existir, ou o pedido é recusado
#    com `no_partition` (o consumidor diz o motivo, não aborta) — pelo `ops`
#    (T3.15e; --months-behind 2 é o default)
docker compose -f infra/docker/docker-compose.yml run --rm ops python infra/scripts/create_partitions.py

# 2. o que seria pedido, sem escrever nada — request_backfill.py não precisa
#    da DSN de dono (conecta como hunter_worker via DATABASE_URL), mas roda
#    pelo mesmo `ops` por consistência operacional (§3.4)
docker compose -f infra/docker/docker-compose.yml run --rm ops python infra/scripts/request_backfill.py --days 31 --dry-run

# 3. de verdade: enfileira na outbox; o dispatcher de qualquer worker publica
#    em ~1 s (use --publish só se nenhum worker estiver de pé)
docker compose -f infra/docker/docker-compose.yml run --rm ops python infra/scripts/request_backfill.py --days 31
```

Sem `--markets` a lista é derivada do banco: todo perpétuo monitorado que tem
**par spot** da mesma venue e mesmo `base/quote` (D1 — o β é medido no
perpétuo, a carteira executa no spot), mais o `BTCUSDT`, que entra sempre —
sem a série da referência todo o universo sai `btc_missing`. `--markets
BTCUSDT,ETHUSDT,SOLUSDT` fixa a lista.

O que o script garante e por quê importa: o teto do coletor é **7 dias por
pedido** e uma janela maior é *truncada para os sete dias mais recentes*
dizendo isso só no log dele — pedir 31 dias numa mensagem só entregaria um
quarto do que se pediu parecendo ter funcionado. Então a faixa vira janelas
inteiras de 7 dias publicadas **da mais nova para a mais antiga** (a ponta
recente é a que a regra de contiguidade precisa), a identidade do evento é a
janela (`uuid5`, igual à do scanner: pedir duas vezes é um pedido só) e a ponta
recente é cortada em 2 min (`DETECTION_GRACE` do coletor) para o pedido não
ficar eternamente parcial.

Acompanhar o dreno (o estrato histórico gasta só o que sobra do ciclo,
`MAX_HISTORY_GAPS_PER_CYCLE = 6` pedaços de 240 min por minuto de relógio — 31
dias de 3 mercados levam ~1 h):

```sql
SELECT m.symbol, g.status, count(*) AS pedacos,
       min(g.gap_start) AS mais_antigo, max(g.gap_end) AS mais_novo
  FROM ingestion_gaps g JOIN markets m ON m.id = g.market_id
 WHERE g.detected_at > now() - interval '2 hours'
 GROUP BY 1, 2 ORDER BY 1, 2;
```

**Lendo `unrecoverable_gaps` (T3.7d).** Um pedido em lote sobre um mercado
listado há pouco (ou o próprio `--markets` sem checar data de listagem, o que
aconteceu na VPS em 2026-09-08 com `MARSCOINUSDT` — `.claude/state/notes-T3.7b-diag.md`)
nomeia janelas que a exchange nunca vai ter: `status = 'unrecoverable'` é o
destino delas, não `'open'`/`'failed'`, e **nunca** volta a ser reaberto —
`open_gaps` (no heartbeat `hb:market:{exchange}` e em `/api/v1/system/market-status`)
não inclui essas linhas, então um `open_gaps` que não zera sozinho depois de um
lote grande é sinal real de trabalho pendente, não de listagens novas
misturadas no meio. `hb:market:{exchange}` (ou `:{i}of{N}` sob sharding) ganha
o campo irmão `unrecoverable_gaps`; um valor crescendo é esperado logo após um
`request_backfill.py --days N` que incluiu um mercado listado recentemente, e
estável depois disso — se ele continuar subindo, o candidato é a raiz nova de
`reason=exhausted` (uma janela que não é antes da listagem mas falha sempre por
outro motivo), não `before_listing`. Motivo e contagem, por mercado:

```sql
SELECT m.symbol, count(*) AS lacunas,
       min(g.gap_start) AS mais_antigo, max(g.gap_end) AS mais_novo
  FROM ingestion_gaps g JOIN markets m ON m.id = g.market_id
 WHERE g.status = 'unrecoverable'
 GROUP BY 1 ORDER BY 2 DESC;

-- o motivo em si não é uma coluna de ingestion_gaps (não há migração nesta
-- tarefa) -- fica em system_events, uma linha por classificação:
SELECT created_at, data->>'reason' AS motivo, data->>'market_id', message
  FROM system_events
 WHERE event = 'market_gap_unrecoverable'
 ORDER BY created_at DESC LIMIT 50;
```

### Histórico de funding para o replay (`request_backfill.py --kind funding`, T3.7c)

O motor de replay (`docs/PIPELINE.md` §6c) não precifica a perna de funding de
um outcome sem histórico de liquidação anterior à entrada
(`hunter_strategy_worker.funding`, `_CADENCE_LOOKBACK` de 3 dias): dois replays
de 31 dias em 2026-09-08 produziram só 23+2 outcomes avaliáveis de 224+341
porque `funding_rates` só tinha o período coletado ao vivo (desde ~2026-09-05)
enquanto os candles já iam até 2026-08-08 (T3.7b). O consumidor do
`market-worker` (`hunter_market_worker/funding_backfill.py`) atende esse pedido
com **uma** chamada REST por mercado — `fetch_realized_funding` já pagina até
~333 dias — em vez do plano por lacunas de 240 min dos candles; nunca
sobrescreve uma liquidação que a coleta ao vivo já gravou (`ON CONFLICT
(market_id, funding_time) DO NOTHING`) e não precisa de partição
(`funding_rates` não é particionada, §1 acima).

```bash
# depois de um deploy, para os 19 mercados monitorados + BTC (referência do β)
# T3.15d: docker exec hunter-api-1 não tem mais DATABASE_URL_MIGRATIONS no
# ambiente (§3.4); request_backfill.py não precisa dela (conecta como
# hunter_worker via DATABASE_URL), mas roda pelo mesmo `ops` por consistência.
bash infra/vps/compose.sh ops python infra/scripts/request_backfill.py \
  --kind funding --days 31 --publish \
  --markets BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT,<...os demais 14>
```

Sem `--publish` o pedido só enfileira na outbox (algum worker publica em ~1 s);
`--dry-run` mostra o que seria pedido sem gravar nada. Acompanhar o resultado:

```sql
SELECT m.symbol, count(*) AS liquidacoes,
       min(f.funding_time) AS mais_antiga, max(f.funding_time) AS mais_nova
  FROM funding_rates f JOIN markets m ON m.id = f.market_id
 WHERE m.symbol = ANY(ARRAY['BTCUSDT','ETHUSDT','SOLUSDT'])
 GROUP BY 1 ORDER BY 1;
```

### O β no heartbeat do scanner (`hb:scanner:{instance}`)

O produtor horário roda dentro do `scanner-worker` (papel `scanner`), um por
exchange por hora. Dois campos no heartbeat dizem o estado dele:

| Campo | O que é |
|---|---|
| `beta_last_run` | ISO-8601 da última passada **deste processo**. Vazio = ainda não rodou nele (um scanner de cinco minutos de vida é isso, honestamente) |
| `beta_valid` | quantos mercados ficaram com β **válido** no último corte. Elegível pelo protocolo, nunca uma alegação de precisão |

```bash
docker exec docker-redis-1 sh -c   'redis-cli --scan --pattern "hb:scanner:*" | xargs -I{} redis-cli hmget {} beta_last_run beta_valid'
```

No `/ready` o β é **status detail**, nunca readiness check: aparece como
`beta: "ok (12/200 valid, 0.3h ago)"` ou `beta: "stale (1/200 valid, 3.4h ago)"`
ao lado do veredito e **não** muda o status code. Um produtor parado há 2 h
significa que a carteira para de abrir posição — o operador tem de ver — e não
significa nada para o Radar, as baselines ou o regime, que é o que o `/ready`
do scanner protege. Métricas: `hunter_beta_revisions_total{outcome}` e
`hunter_beta_valid_markets`.

Reparar uma hora perdida (depois de um backfill, por exemplo) é uma passada à
mão, idempotente, sem trava:

```bash
docker compose -f infra/docker/docker-compose.yml run --rm --no-deps api   python -m hunter_scanner_worker.beta --once
```

```sql
-- quais revisões estão em vigor agora (as três condições da RISK_ENGINE.md §6)
SELECT m.symbol, b.beta, b.n, b.contiguous_bars, b.reason, b.valid_until
  FROM market_betas b JOIN markets m ON m.id = b.market_id
 WHERE b.superseded_at IS NULL AND b.available_at <= now()
   AND b.window_end <= now() AND b.valid_until > now()
 ORDER BY b.valid DESC, m.symbol;
```

### Testes de integração locais sem testcontainers

```bash
docker compose -f infra/docker/docker-compose.test.yml up -d   # Postgres em 55432, Redis em 56379
DATABASE_URL_MIGRATIONS=postgresql://hunter:hunter@localhost:55432/hunter_test \
  uv run alembic -c infra/migrations/alembic.ini upgrade head
uv run pytest -m integration
docker compose -f infra/docker/docker-compose.test.yml down -v
```

CI usa testcontainers direto (`tests/integration/README.md`,
`apps/api/tests/integration/conftest.py`); isto é só a conveniência local.

## 9. VPS (Contabo) — operação 24/7

Ambiente que existe de fato hoje, ao lado do dev local: **uma** VPS Ubuntu
22.04/24.04 rodando a mesma stack do `infra/docker/docker-compose.yml` mais um
override de produção. Serve para o `market-worker` ficar coletando mercado sem
o PC ligado e para sessões de desenvolvimento por SSH (Claude Code e Codex
rodam em Linux; o sandbox do Codex funciona lá, ao contrário do Windows).

Não substitui o §1 (Railway/Vercel/Neon continuam o alvo de produção da Fase
4); é a máquina de trabalho contínuo do MVP.

### 9.1 Arquivos

| Arquivo | O que faz |
|---|---|
| `infra/scripts/bootstrap_vps.sh` | prepara a máquina do zero (Docker, Node 22, pnpm, uv, ufw, fail2ban, unattended-upgrades, swap, usuário de deploy, clone do repo, cron do backup). Idempotente. |
| `infra/scripts/setup_env.sh` | cria o `.env` com digitação oculta (`--vps` para o perfil da VPS). Versão bash do `setup_env.ps1`. |
| `infra/vps/docker-compose.prod.yml` | override: `restart: always`, portas fechadas, `HUNTER_ENV=staging`, Caddy, logs com rotação. |
| `infra/vps/Caddyfile` | borda HTTP: `/api/*` e `/ws` → api; resto → web; TLS automático com domínio. |
| `infra/vps/compose.sh` | atalho que monta o `docker compose` certo (dois `-f`, `--env-file`, nome de projeto). |
| `infra/vps/backup_postgres.sh` | `pg_dump -Fc` diário em `/opt/backups`, retenção 7 dias. |

`infra/vps/README.md` tem os comandos de operação do dia a dia.

### 9.2 Ordem de instalação

```bash
# 1. do PC (SSH já configurado — ver .claude/state/vps.md)
scp infra/scripts/bootstrap_vps.sh hunter-vps:/tmp/
ssh hunter-vps 'bash /tmp/bootstrap_vps.sh'

# 2. na VPS, como o usuário de deploy — só o dono da máquina faz isto
ssh hunter@<ip>
cd /opt/project-hunter
bash infra/scripts/setup_env.sh --vps

# 3. subir
bash infra/vps/compose.sh up
bash infra/vps/compose.sh ps
```

O bootstrap **nunca** cria o `.env` e **nunca** sobe a stack: as chaves são
digitadas pelo dono na própria máquina, e nenhum agente as vê.

### 9.3 Decisões e por quê

**`HUNTER_ENV=staging`, não `production`.** `Settings._require_settings_in_prod`
trata os dois igual (`staging|production` exigem `CLERK_SECRET_KEY`,
`CLERK_WEBHOOK_SECRET`, `CLERK_JWKS_URL`, `CLERK_ISSUER`, `WEB_ORIGIN`,
`API_URL`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_WS_URL`), então staging já
obriga a configuração completa e liga logs JSON e headers de segurança. O que
`production` muda a mais é semântico — `is_production` fecha o OpenAPI e é a
palavra que a Fase 4 usa para "dinheiro real". Enquanto o Clerk está em
instância de desenvolvimento e `ENABLE_LIVE_TRADING=false`, chamar isto de
produção seria mentira. O `setup_env.sh --vps` pede o `CLERK_WEBHOOK_SECRET`
justamente porque staging não sobe sem ele.

**Caddy, não nginx.** TLS automático (ACME) sem escrever configuração de
certificado, sem cron de renovação e sem um segundo container de ACME client;
o `Caddyfile` inteiro tem 40 linhas contra o par nginx.conf + certbot. Com um
domínio só e uma máquina só, é menos coisa para dar errado. Se algum dia
existir load balancing sério ou cache, nginx volta à mesa.

**Uma origem só.** O navegador fala com `https://<domínio>` e ponto: o Caddy
manda `/api/*` e `/ws` para a api e todo o resto para o Next.js. Isso mata
CORS e cookie cross-site, e mantém `/health`, `/ready` e `/metrics` fora do
alcance externo — eles só existem na porta 8000 da rede interna do compose.

**`FORWARDED_ALLOW_IPS` com IP fixo do Caddy.** O peer TCP da api passa a ser
o container do Caddy, não `127.0.0.1`. Sem esse IP na lista, o uvicorn ignora
o `X-Forwarded-For` e todo request vira "o mesmo cliente" para o rate limit
por endereço — um visitante abusivo derrubaria o limite de todos. Por isso a
rede do compose tem sub-rede fixa (`172.28.0.0/24`) e o Caddy tem
`ipv4_address: 172.28.0.10`; os dois valores andam juntos.

**`INTERNAL_PEER_IPS` com IP fixo do `web` (T3.28a).** O `web` fala com a
`api` direto pela rede do compose (`API_URL=http://api:8000`), nunca pelo
Caddy — então toda chamada SSR do Next.js (Server Components) chega na `api`
com o mesmo peer TCP, o do container `web`, não o do navegador. Esse peer
**não** entra em `FORWARDED_ALLOW_IPS` (o `web` hoje não repassa o endereço
real do navegador nessa chamada — faria isso lendo `headers()` dentro do
Server Component e mandando um cabeçalho que a api só confiasse vindo desse
peer, mudança que fica em `apps/web`, fora do escopo desta tarefa) — sem
`INTERNAL_PEER_IPS`, esse único endereço do `web` compartilha
`RATE_LIMIT_PER_MINUTE` (120/min) entre o SSR do site inteiro, e é
exatamente isso que a auditoria de design de 2026-09-08 mediu: 7 telas
navegadas duas vezes em ~25 s bastaram para 24 respostas 429 em
`/api/v1/me` e cinco telas caindo no "Application error" do Next
(`.claude/state/notes-T3.28a.md`). A correção não pede um cabeçalho novo
para confiar: `INTERNAL_PEER_IPS` é uma lista de peers que o próprio
deployment já sabe que são internos (o IP fixo do `web` no compose, igual ao
pin do Caddy) e que por isso recebem `RATE_LIMIT_PER_MINUTE_INTERNAL`
(6000/min por padrão) em vez do limite estreito — o limite por principal
(`RATE_LIMIT_PER_MINUTE_PRINCIPAL`, depois da autenticação) continua
aplicando por trás dele, sem mudança. `infra/docker/docker-compose.yml`
fixa o `web` em `172.29.0.10` (rede própria, sem Caddy); o overlay de
produção (`infra/vps/docker-compose.prod.yml`) fixa o `web` em
`172.28.0.11`, ao lado do `172.28.0.10` do Caddy, na mesma sub-rede — os
dois valores (a `api` e o `web`) andam juntos, como o par
`FORWARDED_ALLOW_IPS`/Caddy acima.

**Incidente 2026-09-07 e correção (`ip_range`).** Um IP fixo baixo (`.10`) na
mesma sub-rede que o alocador dinâmico do Docker usa está sujeito a colisão:
o alocador preenche a partir do menor endereço livre, então qualquer
container comum recriado sem endereço fixo pode receber `.10` antes do Caddy
conseguir subir de novo. Foi o que aconteceu ao recriar containers com o
perfil `shards` (4 market-workers, commit `9ceb389`) por um comando manual —
o `scanner-worker` recebeu `172.28.0.10` primeiro e o Caddy morreu com
`failed to set up container networking: Address already in use` (site fora
até recriar o scanner). `infra/vps/docker-compose.prod.yml` agora reserva
`ipam.config.ip_range: 172.28.0.128/25` na mesma rede: o alocador dinâmico só
distribui endereços dentro dessa faixa, e o `.10` estático do Caddy (fora do
`ip_range`, dentro do `subnet` — válido para o IPAM do Docker) deixa de ser
alcançável por acidente. O pin continua em `.10`; detalhe da decisão e das
alternativas descartadas em `infra/vps/README.md`.

O mesmo incidente teve uma segunda causa, independente da rede: o comando
manual usado não exportava `GIT_SHA` antes do `docker compose ... up`, então
a imagem caiu no default `hunter-api:${GIT_SHA:-dev}` — uma tag velha, sem a
migração nova — e o `migrate` falhou com `Can't locate revision 0006`.
`infra/vps/compose.sh` já resolvia `GIT_SHA` sozinho para `up`/`update`; agora
ele também aceita `MARKET_SHARDS` e ativa `--profile shards` (e, acima de 4,
`--profile shards8`) sozinho nesses dois subcomandos, então o deploy com
shards passa a ser um comando só: `MARKET_SHARDS=4 bash
infra/vps/compose.sh update`. Depois do `up`, o script verifica se algum
serviço ficou em `created`/`exited`/`dead` e, se sim, imprime `docker compose
ps` e as últimas linhas de log de quem falhou — sem tentar contornar.

**Portas.** Só 22, 80 e 443 em `0.0.0.0`. api (8000) e web (3000) publicam em
`127.0.0.1` (túnel SSH para depurar); Postgres e Redis não publicam porta
nenhuma. Isso importa porque **portas publicadas pelo Docker furam o `ufw`**:
o daemon escreve as regras dele antes das do firewall. A defesa não é a regra
de firewall, é não publicar. Verificação: `sudo ss -ltnp | grep -v 127.0.0.1`.

**Grupo `docker`, não rootless.** Quem está no grupo `docker` é root na
prática — é o custo aceito para uma máquina de um dono só, com login apenas
por chave SSH. Docker rootless complicaria bind de 80/443 e o acesso aos
volumes sem ganho real neste cenário. Revisar se um dia mais alguém tiver
conta na máquina.

**Redis com AOF.** O hot state é reconstruível (§6), mas um restart limpo
custa um ciclo inteiro de reconexão de streams; `appendfsync everysec` encurta
isso de minutos para segundos.

### 9.4 Backup

`pg_dump -Fc` diário às 03:17 (hora da máquina) para `/opt/backups`, retenção
de 7 dias, via `/etc/cron.d/hunter-backup`. Antes de aplicar a retenção o
script confere se o `pg_restore --list` consegue ler o índice do arquivo novo
— checagem barata, que pega dump vazio, truncado no começo ou que não é dump
nenhum, e impede que a retenção apague os dumps bons em cima de lixo. Ela
**não** prova integridade dos blocos de dados (`--list` lê o índice, não o
dado); para isso só existe restaurar num banco descartável de tempos em
tempos. `compose ps` falhando é tratado como erro (exit 1), não como "banco
parado" — senão uma configuração quebrada viraria semanas sem backup com o
cron reportando sucesso.

Os arquivos ficam no **mesmo disco**: é proteção contra erro humano e
corrupção lógica, não contra perda da máquina. Cópia para fora do host ainda
não existe.

### 9.5 Bug encontrado ao configurar (fora desta seção)

`CORS_ALLOWED_ORIGINS` **não pode** ser definida como no `.env.example`
(`CORS_ALLOWED_ORIGINS=http://localhost:3000`): `ApiSettings` declara o campo
como `list[str]`, e o `pydantic-settings` tenta `json.loads` no valor antes de
chegar ao `field_validator(mode="before")` que aceita `"a,b"`. Reproduzido:

```
$ CORS_ALLOWED_ORIGINS=https://hunter.exemplo.com uv run python -c "from hunter_api.settings import ApiSettings; ApiSettings()"
SettingsError: error parsing value for field "cors_allowed_origins" from source "EnvSettingsSource"
```

Efeito se alguém seguir o `.env.example` num deploy: a api não sobe, entra em
restart loop e o Caddy fica sem upstream saudável. A configuração da VPS
contorna simplesmente **não definindo** a variável — `_default_cors_from_web_origin`
usa `WEB_ORIGIN`, que é o valor desejado. A correção de verdade
(`NoDecode`/`json` no `.env.example`, ou aceitar string) é de `apps/api` e
`.env.example`, fora do escopo desta seção.

### 9.6 Limitações conhecidas

- Uma máquina só: sem alta disponibilidade, sem réplica, sem backup off-site.
- Clerk em instância de desenvolvimento (`pk_test_`/`sk_test_`).
- Sem domínio, o Caddy serve HTTP puro pelo IP e o sign-in do Clerk
  provavelmente não funciona — serve para ver a stack de pé, não para usar.
- `ENABLE_LIVE_TRADING=false` e `SYSTEM_KILL_SWITCH=ACTIVE`: nada nesta
  máquina executa ordem real (regra dura do `CLAUDE.md`; live trading só na
  Fase 4).
- Sem monitoramento externo: `restart: always` cobre queda de processo, nada
  avisa se a VPS inteira cair.

## Rollback — nota obrigatória a partir de `cefad8c` (2026-09-07)

A partir do commit `cefad8c` (T3.0b) a linha msgpack de vela no hot state (`mkt:*:candles:1m`) e o payload de `market.candles.closed` carregam o campo `market_type`. O código **anterior** a esse commit valida os eventos com `extra="forbid"` e **não lê** a linha nova: uma única linha nova envenena a decodificação da lista inteira (o scanner esvazia o Radar; o strategy-worker avalia com histórico vazio) até a lista rolar por completo (~25 h). Portanto, **qualquer rollback para antes de `cefad8c`, ou deploy parcial em que só o market-worker suba**, exige limpar o hot state de velas antes de subir o código antigo:

```bash
docker exec hunter-redis-1 sh -c 'redis-cli --scan --pattern "mkt:*:candles:1m" | xargs -r redis-cli DEL'
```

O hot state é reconstruível (§6); o durável em Postgres não é afetado.
