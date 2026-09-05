# `infra/vps` — PROJECT HUNTER 24/7 numa VPS

Camada de produção enxuta para uma máquina só (Contabo, Ubuntu 22.04/24.04):
o mesmo `infra/docker/docker-compose.yml` do dev, mais um override que fecha
portas, liga `restart: always`, põe um Caddy na frente e roda o backup diário.
Referência completa em `docs/DEPLOYMENT.md`, seção "VPS (Contabo) — operação
24/7".

| Arquivo | O que é |
|---|---|
| `docker-compose.prod.yml` | override do compose de dev (portas, restart, staging, Caddy, logs) |
| `Caddyfile` | borda HTTP: `/api/*` e `/ws` → api, resto → web; TLS automático se houver domínio |
| `compose.sh` | atalho que monta o comando `docker compose` certo (os dois `-f`, o `--env-file`, o nome de projeto) |
| `backup_postgres.sh` | `pg_dump -Fc` diário em `/opt/backups`, retenção 7 dias, instalado em `/etc/cron.d/hunter-backup` |

## Preparar a máquina (uma vez)

```bash
# no PC, com acesso SSH configurado:
scp infra/scripts/bootstrap_vps.sh hunter-vps:/tmp/
ssh hunter-vps 'bash /tmp/bootstrap_vps.sh'
```

O bootstrap instala Docker, Node 22, pnpm, uv, ufw, fail2ban e
unattended-upgrades, cria swap de 4 GB, abre **só** SSH + 80/443, cria o
usuário `hunter` e clona o repositório em `/opt/project-hunter`. Ele **não**
cria o `.env` e **não** sobe a stack.

## Segredos (só o dono da máquina faz isto)

```bash
ssh hunter@<ip>
cd /opt/project-hunter
bash infra/scripts/setup_env.sh --vps
```

Pergunta domínio, e-mail do certificado e as chaves do Clerk com digitação
oculta; gera sozinho a senha do Postgres, o `AUTH_SECRET` e o
`HUNTER_MASTER_KEY`; grava `/opt/project-hunter/.env` com permissão 600.
Nenhuma chave passa por chat, log ou agente.

Rodar de novo preserva o `POSTGRES_PASSWORD` já existente — a senha só é
aplicada quando o volume do Postgres nasce, então trocá-la depois deixaria a
api sem conseguir autenticar no banco que já tem os dados.

## Operação

```bash
cd /opt/project-hunter

bash infra/vps/compose.sh up            # sobe/atualiza tudo (build incluso)
bash infra/vps/compose.sh ps            # estado dos containers
bash infra/vps/compose.sh logs          # logs ao vivo de tudo
bash infra/vps/compose.sh logs api      # logs de um serviço
bash infra/vps/compose.sh update        # git pull + rebuild + up
bash infra/vps/compose.sh down          # para tudo (volumes ficam)
bash infra/vps/compose.sh exec postgres psql -U hunter -d hunter
```

Equivalente escrito à mão (é o que `compose.sh` monta):

```bash
docker compose --env-file /opt/project-hunter/.env -p hunter \
  -f infra/docker/docker-compose.yml \
  -f infra/vps/docker-compose.prod.yml up -d --build
```

O `--env-file` não é opcional: o diretório de projeto do compose é o do
**primeiro** `-f` (`infra/docker/`), então o `.env` da raiz não seria lido para
interpolar `${POSTGRES_PASSWORD}` e companhia.

## Backup

```bash
bash infra/vps/backup_postgres.sh          # manual
ls -lh /opt/backups                        # o que existe
tail -30 /opt/backups/backup.log           # o que o cron fez
```

Restaurar (destrutivo — confirme antes):

```bash
bash infra/vps/compose.sh exec -T postgres \
  pg_restore -U hunter -d hunter --clean --if-exists < /opt/backups/<arquivo>.dump
```

O script recusa gravar um dump cujo índice o `pg_restore --list` não consegue
ler — pega arquivo vazio, truncado no começo ou que não é dump nenhum, o
suficiente para a retenção não apagar dumps bons em cima de lixo. Isso **não**
garante que todos os blocos de dados estejam íntegros (`--list` lê o índice,
não o dado): o único teste de verdade é restaurar de tempos em tempos num
banco descartável.

`/opt/backups` fica no mesmo disco da VPS — é proteção contra erro humano e
corrupção lógica, **não** contra perda da máquina; cópia para fora (`rsync`
para outro host / object storage) ainda não existe.

## Partições diárias

`infra/scripts/create_partitions.py` mantém as partições mensais de `candles`
e companhia três meses à frente (DATABASE.md §1.3); sem isso o primeiro
insert do mês sem partição derruba o flush inteiro (`no partition of relation
"candles_1m" found for row` — docs/plans/M1.md, "Agendamento real das
partições"). A T1.3 já cobre a **detecção** (readiness check + `system_event`
critical quando falta partição para `now + 1 dia`); o agendamento abaixo é a
**prevenção**.

Rodar a mão (mesmo `docker compose run --rm` que `migrate`/`seed` usam —
`compose.sh` não tem um atalho dedicado para isto, mas encaminha qualquer
subcomando):

```bash
bash infra/vps/compose.sh run --rm --no-deps -e HUNTER_COMMAND=partitions api
```

**`--no-deps` não é opcional aqui.** `api` declara `depends_on: migrate:
condition: service_completed_successfully` no `docker-compose.yml`, e `docker
compose run` sobe os `depends_on` a menos que se mande não subir. Sem
`--no-deps`, este comando dispara `alembic upgrade head` (com
`DATABASE_URL_MIGRATIONS`, a credencial dona do schema) toda vez que roda —
inclusive às 04:07 sem ninguém olhando. Um `git pull`/`update` que deixou uma
revisão nova sem release faria essa migração aplicar sozinha; e se a migração
falhar, `compose run` aborta na dependência e a partição — o motivo do job
existir — nunca chega a rodar. `--no-deps` faz este comando fazer só uma
coisa: criar partição, exatamente como o nome do job promete.

Agendamento (instalar uma vez, à mão — `bootstrap_vps.sh` só instala o cron do
backup, não este; segue o mesmo padrão de `/etc/cron.d/hunter-backup`):

```bash
printf '%s\n' \
  'SHELL=/bin/bash' \
  'PATH=/usr/local/bin:/usr/bin:/bin' \
  '7 4 * * * hunter cd /opt/project-hunter && bash infra/vps/compose.sh run --rm --no-deps -e HUNTER_COMMAND=partitions api >> /opt/backups/partitions.log 2>&1' \
  | sudo tee /etc/cron.d/hunter-partitions >/dev/null
sudo chmod 644 /etc/cron.d/hunter-partitions
```

Todo dia às 04:07 (hora da máquina, depois do backup das 03:17 — mesmo
horário de menor uso, sem disputar o mesmo minuto), saída anexada em
`/opt/backups/partitions.log` (mesmo diretório do backup, já criado e fechado
em 700 pelo `backup_postgres.sh`; não é um segundo local de estado, é o mesmo
diretório operacional).

O script é idempotente e o próprio processo distingue "pulou uma partição por
`lock_timeout` de 3 s" (não fatal — sai com código **75**, `EX_TEMPFAIL` de
`sysexits.h`, só para aparecer no log; tenta de novo amanhã) de qualquer outro
erro de banco (`DBAPIError` não tratado, código **1** — esse sim propaga e
teria que investigar). Os dois códigos são diferentes de propósito: um
`grep`/cron-mail que aprendesse "saída != 0 é sempre o skip de rotina"
pararia de ler `partitions.log`, e uma falha real (privilégio de `CREATE`
revogado, disco cheio) se repetiria sem ninguém notar até a virada do mês.
Quando falhar:

```bash
tail -30 /opt/backups/partitions.log     # o que o cron viu
bash infra/vps/compose.sh run --rm --no-deps -e HUNTER_COMMAND=partitions api  # rodar a mão para ver o erro na tela
```

Se falhar dias seguidos perto da virada do mês, o readiness check da T1.3 já
teria soado `system_event` critical antes disso virar um insert perdido de
verdade — mas não espere por ele: um `lock_timeout` isolado é normal (gap
detection ou outra query concorrente segurando o parent), vários dias seguidos
não é.

## O que fica exposto

| Porta | Onde escuta | Quem alcança |
|---|---|---|
| 22 | `0.0.0.0` | SSH, só com chave (senha desligada pelo bootstrap) |
| 80 / 443 | `0.0.0.0` | Caddy |
| 8000 (api) | `127.0.0.1` | só de dentro da VPS ou por túnel SSH |
| 3000 (web) | `127.0.0.1` | idem |
| 5432 / 6379 | nenhuma | só a rede interna do compose |

**Armadilha conhecida:** portas publicadas pelo Docker em `0.0.0.0` furam o
`ufw` (o Docker escreve as regras dele antes). É por isso que api e web são
publicadas só em `127.0.0.1` e que Postgres e Redis não publicam porta
nenhuma. Depois de subir, confira:

```bash
sudo ss -ltnp | grep -v 127.0.0.1
```

Só devem aparecer 22, 80 e 443.

## Túnel para depurar sem expor nada

```bash
ssh -L 8000:127.0.0.1:8000 -L 3000:127.0.0.1:3000 hunter@<ip>
# no PC: http://127.0.0.1:8000/health, http://127.0.0.1:8000/ready
```

## Limitações conhecidas

- `HUNTER_ENV=staging`, não `production`: staging já liga logs JSON, headers de
  segurança e a exigência de todos os segredos do Clerk, sem prometer as
  garantias de produção (Fase 4, `ENABLE_LIVE_TRADING` continua `false`).
- Clerk continua no plano/instância de desenvolvimento (`pk_test_`/`sk_test_`).
- Sem domínio o Caddy serve HTTP puro pelo IP e o sign-in do Clerk
  provavelmente não funciona — serve para ver a stack de pé, não para usar.
- Uma máquina só: sem alta disponibilidade, sem réplica de banco, sem backup
  fora do host.
- `/metrics` continua fechado (`METRICS_TOKEN` vazio ⇒ 404) e não é roteado
  pelo Caddy.
