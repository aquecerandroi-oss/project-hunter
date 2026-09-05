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
