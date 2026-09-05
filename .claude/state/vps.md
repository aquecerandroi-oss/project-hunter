# VPS (Contabo) — estado e checklist

Atualizado: 2026-09-05 · Responsável: Sexta-feira · Alvo: rodar o PROJECT
HUNTER 24/7 (market-worker, api, Postgres, Redis, web) e servir de máquina de
desenvolvimento por SSH.

## Estado do acesso

**Acesso confirmado em 2026-09-05.** Máquina reinstalada com Ubuntu 24.04 e a
chave pública do PC do Everton; entrada `hunter-vps` (root@169.58.116.99) no
`~/.ssh/config` dele. Nenhuma senha foi usada em momento algum.

```
$ ssh -o BatchMode=yes hunter-vps 'echo ok; head -1 /etc/os-release; nproc; free -h; df -h /; id'
ok
PRETTY_NAME="Ubuntu 24.04.4 LTS"
12
               total        used        free      shared  buff/cache   available
Mem:            47Gi       812Mi        45Gi       1.0Mi       1.2Gi        46Gi
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1       348G  2.2G  346G   1% /
uid=0(root) gid=0(root) groups=0(root)
```

12 vCPU, 47 GB de RAM, 348 GB de disco — folgado para a stack inteira mais
sessões de desenvolvimento.

## Bootstrap executado

`scp infra/scripts/bootstrap_vps.sh hunter-vps:/tmp/ && ssh hunter-vps 'bash /tmp/bootstrap_vps.sh'`
→ **exit 0**. Log completo em `.claude/state/vps-bootstrap.log`.

**Idempotência provada:** segunda execução (`--no-upgrade`, log em
`.claude/state/vps-bootstrap-rerun.log`) também saiu com 0 e não duplicou
nada — "ja instalado" em Docker/Node/uv, "usuario ja existe", "ja existe
swap", repositório atualizado em vez de clonado.

Verificação na máquina (`ssh hunter-vps`):

```
Docker version 29.8.0, build 88096ef
Docker Compose version v5.5.1          (>= 2.24.4, tag !override disponível)
v22.23.2                                (node)
11.25.0                                 (pnpm)
uv 0.12.9 (x86_64-unknown-linux-gnu)

--- ufw ---
Status: active
Default: deny (incoming), allow (outgoing), deny (routed)
22/tcp (OpenSSH)           ALLOW IN    Anywhere
80/tcp                     ALLOW IN    Anywhere
443/tcp                    ALLOW IN    Anywhere
(+ as três equivalentes em IPv6; nada mais aberto)

--- swap ---
NAME      TYPE SIZE USED PRIO
/swapfile file   4G   0B   -2

--- sshd efetivo ---
permitrootlogin without-password
passwordauthentication no
kbdinteractiveauthentication no

--- fail2ban ---
Status for the jail: sshd   (Total failed: 4 — bots já batendo na porta;
                             senha desligada, então não passa)

--- usuário de deploy ---
uid=1001(hunter) gid=1001(hunter) groups=1001(hunter),988(docker)

--- repositório ---
/opt/project-hunter, dono hunter:hunter, clonado em 33d58d8

--- cron do backup ---
17 3 * * * hunter /opt/project-hunter/infra/vps/backup_postgres.sh >> /opt/backups/backup.log 2>&1

--- rotação de log do daemon ---
{ "log-driver": "json-file", "log-opts": { "max-size": "10m", "max-file": "5" } }
```

## Pré-teste da stack — bloqueado por desenho, não por erro

`docker compose ... config` **exige o `.env`**: o compose de produção usa
`${VAR:?mensagem}` em `POSTGRES_PASSWORD`, `HUNTER_PUBLIC_URL`, `HUNTER_WS_URL`,
`HUNTER_SITE_ADDRESS` e `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`. Sem `.env` ele
recusa com a mensagem certa (verificado localmente), e o `.env` é do Everton —
nenhum agente cria. Logo o `config` e o primeiro `build` na VPS só rodam depois
do passo 8 abaixo.

O YAML em si está validado: `docker compose -f infra/docker/docker-compose.yml
-f infra/vps/docker-compose.prod.yml config` passa no PC do Everton assim que
as variáveis existem.

## Checklist

| # | Item | Estado |
|---|---|---|
| 1 | `infra/scripts/bootstrap_vps.sh` (Docker, Node 22, pnpm, uv, ufw, fail2ban, unattended-upgrades, swap, usuário de deploy, clone, cron) | **executado na VPS, exit 0, idempotente** |
| 2 | `infra/scripts/setup_env.sh` (perfis `--local` e `--vps`) | feito — na VPS, esperando o Everton (passo 8) |
| 3 | `infra/vps/docker-compose.prod.yml` + `Caddyfile` + `compose.sh` | feito — `docker compose config` válido |
| 4 | `infra/vps/backup_postgres.sh` + cron diário | instalado em `/etc/cron.d/hunter-backup`; só exercitável com a stack de pé |
| 5 | `docs/DEPLOYMENT.md` §9, `infra/vps/README.md`, `obsidian/09-OPERATIONS/Deployment.md` | feito |
| 6 | Acesso SSH (`Host hunter-vps`) | **feito** — chave instalada na reinstalação |
| 7 | Rodar o bootstrap na VPS | **feito** |
| 8 | Criar o `.env` na VPS (`setup_env.sh --vps`) | **só o Everton** — chaves do Clerk |
| 9 | Subir a stack (`compose.sh up`) e conferir `/ready` | pendente (depende do 8) |
| 10 | `claude` e `codex login` na VPS para sessões de dev | **só o Everton** (login no navegador) |

## Pendências conhecidas

- **Sem domínio, sem TLS.** `HUNTER_SITE_ADDRESS=:80` faz o Caddy servir HTTP
  puro em `http://169.58.116.99`. O navegador avisa "não seguro" e o Clerk em
  modo desenvolvimento não gosta de origem sem TLS. Subir a `web` de verdade
  só faz sentido com domínio apontado para o IP; a `api` e o `market-worker`
  já rodam bem assim.
- **Bug latente do `CORS_ALLOWED_ORIGINS`** (achado da Astra, confirmado por
  mim): `ApiSettings.cors_allowed_origins` é `list[str]` e o pydantic-settings
  tenta `json.loads` **antes** do validador que aceita `"a,b"`. Reproduzido:
  `CORS_ALLOWED_ORIGINS=http://localhost:3000 uv run python -c "ApiSettings()"`
  → `SettingsError: error parsing value for field "cors_allowed_origins"`.
  O `setup_env.sh --vps` e o compose de produção contornam **não escrevendo a
  variável** (o fallback `WEB_ORIGIN` dá o valor certo), mas o
  `.env.example:13` ainda traz `CORS_ALLOWED_ORIGINS=http://localhost:3000`:
  quem copiar o exemplo derruba a API no boot. Correção de verdade é anotar o
  campo com `NoDecode` em `apps/api/hunter_api/settings.py`. Não fiz agora
  porque o `.env.example` está em voo na T1.3 e a correção pede revisão de
  API — fica para a próxima onda.
- **Backup só local.** `/opt/backups` mora no mesmo disco da VPS. Cópia externa
  ainda não existe; enquanto não existir, um incidente na máquina leva o banco
  e os dumps juntos.

## Decisões tomadas (registro)

- **Ubuntu 22.04/24.04**, confirmado no bootstrap (`/etc/os-release`); outra
  versão só avisa e segue, outra distro aborta.
- **`HUNTER_ENV=staging`**, não `production`: `Settings._require_settings_in_prod`
  trata os dois igual, então staging já exige a configuração completa do Clerk
  e liga logs JSON e headers de segurança, sem chamar de produção uma máquina
  com Clerk de desenvolvimento e `ENABLE_LIVE_TRADING=false`.
- **Caddy**, não nginx: TLS automático sem certbot nem cron de renovação.
- **Só 22/80/443 públicas.** api e web em `127.0.0.1`, Postgres e Redis sem
  porta publicada. Motivo concreto: porta publicada pelo Docker em `0.0.0.0`
  fura o `ufw`, então a defesa é não publicar.
- **Grupo `docker`**, não rootless: máquina de um dono só, login por chave.
- **`.env` nasce na VPS**, digitado pelo dono; nunca copiado do PC, nunca
  lido por agente.
- **Sudo sem senha** para o usuário de deploy: a conta nasce sem senha
  nenhuma (entra só por chave), então sem `NOPASSWD` ela não conseguiria usar
  `sudo`.

## Segunda opinião (Astra) — `.claude/state/astra-review-vps-bootstrap.md`

Oito must-fix. Sete corrigidos, um rebaixado a ajuste de texto:

| # | Achado | O que fiz |
|---|---|---|
| 1 | `$SUDO -u "$DEPLOY_USER"` vira `-u ...` como comando quando o script roda como root (caso padrão da Contabo) — bootstrap morre no clone | função `as_deploy()` com `sudo -u`, que funciona nos dois casos |
| 2 | `grep -c '^ssh-' \|\| echo 0` produz `"0\n0"` quando o arquivo existe sem chave; a comparação quebra e a senha é desligada de quem só tem senha | `count_ssh_keys()` com `awk`, que também reconhece `ecdsa-sha2-*` e `sk-*` |
| 3 | `CORS_ALLOWED_ORIGINS` como URL simples derruba a api no boot (`list[str]` + `json.loads` antes do validador) | variável removida do `.env` e do compose; `WEB_ORIGIN` já é o fallback. **Reproduzido**, ver `docs/DEPLOYMENT.md` §9.5 |
| 4 | `${token##*=}` engolia segredo terminado em `==` (padding base64 do `whsec_`) | corta só `NOME=` e só até o primeiro `=`; testado com `whsec_...==` |
| 5 | escrita não atômica do `.env` podia deixar o arquivo pela metade, sem a única cópia do `POSTGRES_PASSWORD` | temporário 600 no mesmo diretório + `mv`; recusa symlink |
| 6 | plugin do Compose < 2.24.4 não entende `!override` | bootstrap aborta com instrução de upgrade |
| 7 | `compose ps` falhando virava "postgres parado" e o backup saía 0 | erro de comando agora é exit 1 com a saída no log |
| 8 | `pg_restore --list` não prova integridade dos dados, só do índice | promessa corrigida em `README.md` e `DEPLOYMENT.md` §9.4 |

Nice-to-have aceitos: `reload-or-restart` no fail2ban (o `enable --now` não
releria o `jail.local` num daemon já ativo), instalador do uv em `mktemp -d`
privado, `-type f` e diretório `0700` no backup, filtro do parâmetro `token`
no log do Caddy (o link de convite é `/accept-invite?token=...`).

Recusado com motivo: **Docker rootless** e **conta de dev separada sem sudo**.
Máquina de um dono só, login apenas por chave; a própria Astra registra que
rootless não protege contra o comprometimento da conta que tem `NOPASSWD`.
Revisar se algum dia mais alguém tiver conta na máquina.

### Segunda rodada, só sobre as correções — `.claude/state/astra-review-vps-fixes.md`

Quatro must-fix, todos aplicados (commit `9690369` + este):

| Achado | O que fiz |
|---|---|
| temporário do `.env` com `$$` é nome previsível: dá para plantar symlink e desviar os segredos | `mktemp "$ENV_PATH.XXXXXX"` |
| `chmod 700` do `/opt/backups` era best-effort e engolia o erro — dump do banco inteiro em diretório legível por outros | recusa gravar se não estiver `700`; e o bootstrap já cria assim |
| `.env.example:13` ainda traz `CORS_ALLOWED_ORIGINS=http://localhost:3000`, e o compose base importa o `.env` — quem copiar o exemplo derruba a api | preflight no `compose.sh` que aborta com a explicação; correção de verdade é em `apps/api`, fora deste escopo |
| o comentário prometia colar várias linhas de uma vez, mas o prompt lê uma linha por vez | promessa corrigida no comentário |

Confirmou como corretos: `as_deploy`, `count_ssh_keys`, checagem de versão do
Compose, `mktemp -d` do uv, `reload-or-restart` do fail2ban, `exit 1` no
backup, sintaxe do filtro de log do Caddy.

### Verificação independente na máquina (2026-09-05, `ssh hunter-vps`)

```
Docker 29.8.0 · docker compose 5.5.1 · node v22.23.2 · pnpm 11.25.0 · uv 0.12.9
ufw active — 22/tcp, 80/tcp, 443/tcp (v4 e v6); default deny incoming
sshd -T → passwordauthentication no · kbdinteractiveauthentication no
fail2ban active — jail sshd viva (5 tentativas de bot já barradas)
swap 4G · usuário hunter no grupo docker · /opt/backups 700 hunter
ss -ltnp → só 22 público (53 é o resolver local); nada mais escutando fora
/opt/project-hunter em 9690369, dono hunter
bash -n limpo nos quatro scripts sob o bash 5.2.21 da própria VPS
backup_postgres.sh sem stack de pé → ERRO explícito + exit 1 (não finge sucesso)
```

## Depois que a VPS estiver de pé

Sessões de desenvolvimento por SSH (o sandbox do Codex funciona em Linux, ao
contrário do Windows):

```bash
ssh hunter
cd /opt/project-hunter
npm i -g @anthropic-ai/claude-code @openai/codex   # uma vez
claude        # login no navegador
codex login   # login no navegador
```

Rodar dentro de `tmux` para a sessão sobreviver à queda do SSH:
`tmux new -s hunter` / `tmux attach -t hunter`.
