#!/usr/bin/env bash
# PROJECT HUNTER - preparacao de uma VPS Ubuntu 22.04/24.04 para rodar a stack
# 24/7 (docs/DEPLOYMENT.md, secao "VPS (Contabo) - operacao 24/7").
#
# Instala Docker Engine + compose plugin, Node 22, pnpm, uv, git, ufw, fail2ban
# e unattended-upgrades; cria swap; abre SOMENTE SSH + 80/443 no firewall;
# clona o repositorio em /opt/project-hunter. NAO cria o .env e NAO sobe a
# stack: os segredos sao do dono da maquina (infra/scripts/setup_env.sh --vps).
#
# Uso (na VPS, como root ou como usuario com sudo):
#   bash bootstrap_vps.sh [--deploy-user hunter] [--dir /opt/project-hunter]
#                         [--repo-url URL] [--branch main]
#                         [--http-port 80] [--https-port 443]
#                         [--no-ssh-harden] [--no-upgrade]
#
# Idempotente: rodar de novo atualiza pacotes e o repositorio, sem duplicar
# nada. Todo download externo vem de repositorio apt oficial assinado; a unica
# excecao e o instalador do uv, baixado com URL de versao fixa para um arquivo
# temporario (inspecionavel) antes de ser executado.
#
# Arquivo unico de proposito, mesmo passando das 350 linhas do orcamento de
# modulo: ele roda ANTES do repositorio existir na maquina (vai por scp
# sozinho), entao nao pode depender de nenhum outro arquivo do projeto.
set -euo pipefail

DEPLOY_USER="hunter"
TARGET_DIR="/opt/project-hunter"
REPO_URL="https://github.com/aquecerandroi-oss/project-hunter.git"
BRANCH="main"
HTTP_PORT="80"
HTTPS_PORT="443"
BACKUP_DIR="/opt/backups"
SSH_HARDEN="yes"
DO_UPGRADE="yes"

UV_VERSION="0.12.9"        # mesma serie usada no desenvolvimento (uv --version)
NODE_MAJOR="22"            # package.json engines: node >=22
PNPM_VERSION="11.25.0"     # package.json packageManager

while [ "$#" -gt 0 ]; do
  case "$1" in
    --deploy-user) DEPLOY_USER="$2"; shift 2 ;;
    --dir) TARGET_DIR="$2"; shift 2 ;;
    --repo-url) REPO_URL="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --http-port) HTTP_PORT="$2"; shift 2 ;;
    --https-port) HTTPS_PORT="$2"; shift 2 ;;
    --no-ssh-harden) SSH_HARDEN="no"; shift ;;
    --no-upgrade) DO_UPGRADE="no"; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "argumento desconhecido: $1" >&2; exit 64 ;;
  esac
done

if [ "$(id -u)" -eq 0 ]; then SUDO=""; else SUDO="sudo"; fi
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a

step() { echo ""; echo "=== $* ==="; }
have() { command -v "$1" >/dev/null 2>&1; }

# Rodar como o usuario de deploy. NAO usar "$SUDO -u ...": quando o script
# roda como root (caso padrao da Contabo) $SUDO e vazio e o "-u" vira o
# comando -> "127 command not found" no meio do clone.
as_deploy() { sudo -u "$DEPLOY_USER" "$@"; }

# Conta chaves publicas utilizaveis num authorized_keys. Um "grep -c" simples
# nao serve: quando o arquivo existe sem nenhuma chave, ele imprime 0 E sai
# com 1, e o "|| echo 0" acaba concatenando um segundo zero - a comparacao
# numerica quebra e o script segue como se houvesse chave, desligando a senha
# de quem so tem senha.
count_ssh_keys() {
  local n
  n="$($SUDO awk '
    /^[[:space:]]*(#|$)/ { next }
    /(^|[[:space:]])(ssh-(rsa|dss|ed25519)|ecdsa-sha2-|sk-(ssh|ecdsa))/ { n++ }
    END { print n + 0 }' "$1" 2>/dev/null)" || n=""
  printf '%s' "${n:-0}"
}

# ---------------------------------------------------------------------------
# 0. Sistema suportado
# ---------------------------------------------------------------------------
step "checando o sistema"
. /etc/os-release
echo "detectado: ${PRETTY_NAME:-desconhecido} (ID=$ID VERSION_ID=${VERSION_ID:-?})"
if [ "$ID" != "ubuntu" ]; then
  echo "este script so foi escrito para Ubuntu 22.04/24.04." >&2
  exit 1
fi
case "${VERSION_ID:-}" in
  22.04|24.04) : ;;
  *) echo "AVISO: versao ${VERSION_ID:-?} nao testada; seguindo mesmo assim." ;;
esac
[ -n "${VERSION_CODENAME:-}" ] || { echo "sem VERSION_CODENAME em /etc/os-release." >&2; exit 1; }

# ---------------------------------------------------------------------------
# 1. Pacotes base
# ---------------------------------------------------------------------------
step "pacotes base"
$SUDO apt-get update -qq
if [ "$DO_UPGRADE" = "yes" ]; then
  $SUDO apt-get -y -qq upgrade
fi
$SUDO apt-get install -y -qq \
  ca-certificates curl gnupg git ufw fail2ban unattended-upgrades \
  cron jq rsync htop tmux openssl

# ---------------------------------------------------------------------------
# 2. Docker Engine + compose plugin (repositorio oficial assinado)
#    https://docs.docker.com/engine/install/ubuntu/
# ---------------------------------------------------------------------------
step "docker engine + compose plugin"
if docker compose version >/dev/null 2>&1; then
  echo "ja instalado: $(docker --version), $(docker compose version | head -1)"
else
  $SUDO install -m 0755 -d /etc/apt/keyrings
  $SUDO curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  $SUDO chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    | $SUDO tee /etc/apt/sources.list.d/docker.list >/dev/null
  $SUDO apt-get update -qq
  $SUDO apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin
fi
$SUDO systemctl enable --now docker

# infra/vps/docker-compose.prod.yml usa a tag `!override` em `ports`, que so
# existe a partir do Compose 2.24.4. Num plugin mais velho o YAML nem e
# interpretado - melhor descobrir aqui do que na hora de subir a stack.
COMPOSE_VERSION="$(docker compose version --short 2>/dev/null | tr -d 'v')"
if [ -z "$COMPOSE_VERSION" ] || \
   [ "$(printf '2.24.4\n%s\n' "$COMPOSE_VERSION" | sort -V | head -1)" != "2.24.4" ]; then
  echo "docker compose ${COMPOSE_VERSION:-?} e velho demais: infra/vps/docker-compose.prod.yml exige >= 2.24.4 (tag !override)." >&2
  echo "atualize o plugin: sudo apt-get install --only-upgrade docker-compose-plugin" >&2
  exit 1
fi
echo "docker compose $COMPOSE_VERSION (>= 2.24.4, tag !override disponivel)"

# Rotacao de log padrao do daemon: sem isso um worker 24/7 enche o disco com
# /var/lib/docker/containers/*.log. O compose de producao repete o limite por
# servico; este e a rede de seguranca para qualquer container avulso.
if [ ! -f /etc/docker/daemon.json ]; then
  $SUDO mkdir -p /etc/docker
  printf '%s\n' \
    '{' \
    '  "log-driver": "json-file",' \
    '  "log-opts": { "max-size": "10m", "max-file": "5" }' \
    '}' | $SUDO tee /etc/docker/daemon.json >/dev/null
  $SUDO systemctl restart docker
else
  echo "/etc/docker/daemon.json ja existe - nao alterado (confira log-opts a mao)"
fi

# ---------------------------------------------------------------------------
# 3. Usuario de deploy (quando o script roda como root, caso padrao da Contabo)
# ---------------------------------------------------------------------------
step "usuario de deploy: $DEPLOY_USER"
if id "$DEPLOY_USER" >/dev/null 2>&1; then
  echo "usuario ja existe"
else
  $SUDO useradd -m -s /bin/bash "$DEPLOY_USER"
  echo "usuario criado (sem senha: entra so por chave SSH)"
fi
$SUDO usermod -aG docker "$DEPLOY_USER"
# sudo sem senha: a conta nasce sem senha nenhuma, entao sem isto ela nao
# consegue usar sudo. O acesso continua sendo so por chave SSH.
printf '%s ALL=(ALL) NOPASSWD:ALL\n' "$DEPLOY_USER" | $SUDO tee "/etc/sudoers.d/90-$DEPLOY_USER" >/dev/null
$SUDO chmod 440 "/etc/sudoers.d/90-$DEPLOY_USER"
$SUDO visudo -cf "/etc/sudoers.d/90-$DEPLOY_USER" >/dev/null

# Copia as chaves autorizadas de quem esta rodando o script (tipicamente root)
# para o novo usuario - sem isso ninguem consegue entrar como ele.
SRC_KEYS="${HOME:-/root}/.ssh/authorized_keys"
DST_KEYS="/home/$DEPLOY_USER/.ssh/authorized_keys"
if [ -s "$SRC_KEYS" ] && [ ! -s "$DST_KEYS" ]; then
  $SUDO install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
  $SUDO cp "$SRC_KEYS" "$DST_KEYS"
  $SUDO chown "$DEPLOY_USER:$DEPLOY_USER" "$DST_KEYS"
  $SUDO chmod 600 "$DST_KEYS"
  echo "authorized_keys copiado para $DEPLOY_USER"
fi
KEY_COUNT="$(count_ssh_keys "$DST_KEYS")"
echo "chaves autorizadas para $DEPLOY_USER: $KEY_COUNT"

# ---------------------------------------------------------------------------
# 4. Node 22 + pnpm (repositorio NodeSource assinado, sem curl | sh)
# ---------------------------------------------------------------------------
step "node ${NODE_MAJOR} + pnpm ${PNPM_VERSION}"
if have node && node --version | grep -q "^v${NODE_MAJOR}\."; then
  echo "ja instalado: $(node --version)"
else
  $SUDO install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
    | $SUDO gpg --dearmor --yes -o /etc/apt/keyrings/nodesource.gpg
  $SUDO chmod a+r /etc/apt/keyrings/nodesource.gpg
  echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_${NODE_MAJOR}.x nodistro main" \
    | $SUDO tee /etc/apt/sources.list.d/nodesource.list >/dev/null
  $SUDO apt-get update -qq
  $SUDO apt-get install -y -qq nodejs
fi
$SUDO corepack enable
$SUDO corepack prepare "pnpm@${PNPM_VERSION}" --activate >/dev/null
echo "node $(node --version), pnpm $(pnpm --version 2>/dev/null || echo '?')"

# ---------------------------------------------------------------------------
# 5. uv (instalador oficial, URL de versao fixa, baixado antes de executar)
# ---------------------------------------------------------------------------
step "uv ${UV_VERSION}"
if have uv && uv --version | grep -q "${UV_VERSION}"; then
  echo "ja instalado: $(uv --version)"
else
  # Diretorio privado (700, nome imprevisivel): em /tmp com nome fixo, qualquer
  # conta da maquina poderia plantar o arquivo antes e ver ele ser executado
  # como root. Continua sendo codigo remoto executado com privilegio - o que a
  # URL de versao fixa garante e que e sempre o MESMO codigo, nao "o ultimo".
  UV_TMP="$(mktemp -d)"
  UV_INSTALLER="$UV_TMP/uv-install-${UV_VERSION}.sh"
  curl -fsSL "https://astral.sh/uv/${UV_VERSION}/install.sh" -o "$UV_INSTALLER"
  echo "instalador baixado em $UV_INSTALLER ($(wc -c <"$UV_INSTALLER") bytes) - inspecione com 'less' se quiser"
  $SUDO env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh "$UV_INSTALLER"
  rm -rf "$UV_TMP"
  echo "$(uv --version)"
fi

# ---------------------------------------------------------------------------
# 6. Swap de 4 GB (Postgres + build do Next.js em 8 GB de RAM sem swap morre
#    por OOM no meio do 'next build')
# ---------------------------------------------------------------------------
step "swap"
if [ -n "$(swapon --show --noheadings 2>/dev/null || true)" ]; then
  echo "ja existe swap: $(swapon --show --noheadings | tr '\n' ' ')"
else
  $SUDO fallocate -l 4G /swapfile || $SUDO dd if=/dev/zero of=/swapfile bs=1M count=4096 status=none
  $SUDO chmod 600 /swapfile
  $SUDO mkswap /swapfile >/dev/null
  $SUDO swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | $SUDO tee -a /etc/fstab >/dev/null
  echo 'vm.swappiness=10' | $SUDO tee /etc/sysctl.d/99-hunter-swap.conf >/dev/null
  $SUDO sysctl -q -w vm.swappiness=10
  echo "swap de 4G criado"
fi

# ---------------------------------------------------------------------------
# 7. Firewall (ufw): so SSH e as portas do Caddy
# ---------------------------------------------------------------------------
step "firewall (ufw)"
$SUDO ufw --force default deny incoming >/dev/null
$SUDO ufw --force default allow outgoing >/dev/null
$SUDO ufw allow OpenSSH >/dev/null
$SUDO ufw allow "${HTTP_PORT}/tcp" >/dev/null
$SUDO ufw allow "${HTTPS_PORT}/tcp" >/dev/null
$SUDO ufw --force enable >/dev/null
$SUDO ufw status verbose | head -20
echo ""
echo "ATENCAO: portas publicadas pelo Docker em 0.0.0.0 furam o ufw (o Docker"
echo "escreve suas proprias regras antes das do ufw). Por isso o compose de"
echo "producao publica api/web SO em 127.0.0.1 e postgres/redis em porta"
echo "nenhuma; so o Caddy publica ${HTTP_PORT}/${HTTPS_PORT}. Confira depois de subir a stack:"
echo "  sudo ss -ltnp | grep -v '127.0.0.1'"

# ---------------------------------------------------------------------------
# 8. fail2ban + atualizacoes automaticas de seguranca
# ---------------------------------------------------------------------------
step "fail2ban + unattended-upgrades"
if [ ! -f /etc/fail2ban/jail.local ]; then
  printf '%s\n' \
    '[sshd]' \
    'enabled = true' \
    'backend = systemd' \
    'maxretry = 5' \
    'findtime = 10m' \
    'bantime = 1h' | $SUDO tee /etc/fail2ban/jail.local >/dev/null
fi
# reload-or-restart, nao so "enable --now": num daemon que ja estava ativo o
# --now nao releria o jail.local recem-escrito, e a jail ficaria desligada
# ate o proximo reboot.
$SUDO systemctl enable fail2ban
$SUDO systemctl reload-or-restart fail2ban
$SUDO fail2ban-client status sshd 2>/dev/null | head -3 || echo "AVISO: jail sshd nao respondeu (confira 'sudo fail2ban-client status')"
printf '%s\n' \
  'APT::Periodic::Update-Package-Lists "1";' \
  'APT::Periodic::Unattended-Upgrade "1";' \
  | $SUDO tee /etc/apt/apt.conf.d/20auto-upgrades >/dev/null
$SUDO systemctl enable --now unattended-upgrades || true

# ---------------------------------------------------------------------------
# 9. SSH: so chave, sem senha (com trava: nao faz isso se nao ha chave alguma,
#    senao a proxima conexao fica de fora da propria maquina)
# ---------------------------------------------------------------------------
step "endurecimento do SSH"
ROOT_KEYS="$(count_ssh_keys /root/.ssh/authorized_keys)"
if [ "$SSH_HARDEN" != "yes" ]; then
  echo "pulado (--no-ssh-harden)"
elif [ "$KEY_COUNT" -eq 0 ] && [ "$ROOT_KEYS" -eq 0 ]; then
  echo "PULADO: nenhuma chave publica em authorized_keys. Desligar a senha agora"
  echo "trancaria voce para fora. Instale a chave e rode de novo."
else
  # 00- porque o sshd usa o PRIMEIRO valor obtido e o Include fica no topo do
  # sshd_config: um 50-cloud-init.conf com PasswordAuthentication yes venceria
  # um arquivo 99-.
  printf '%s\n' \
    '# PROJECT HUNTER - infra/scripts/bootstrap_vps.sh' \
    'PasswordAuthentication no' \
    'KbdInteractiveAuthentication no' \
    'PermitRootLogin prohibit-password' \
    'X11Forwarding no' \
    | $SUDO tee /etc/ssh/sshd_config.d/00-hunter-hardening.conf >/dev/null
  if $SUDO sshd -t; then
    $SUDO systemctl reload ssh 2>/dev/null || $SUDO systemctl restart ssh
    echo "efetivo agora: $($SUDO sshd -T | grep -i '^passwordauthentication')"
  else
    $SUDO rm -f /etc/ssh/sshd_config.d/00-hunter-hardening.conf
    echo "sshd -t reprovou a configuracao; arquivo removido, nada alterado." >&2
  fi
fi

# ---------------------------------------------------------------------------
# 10. Repositorio
# ---------------------------------------------------------------------------
step "repositorio em $TARGET_DIR"
$SUDO mkdir -p "$TARGET_DIR" "$BACKUP_DIR"
$SUDO chown "$DEPLOY_USER:$DEPLOY_USER" "$TARGET_DIR" "$BACKUP_DIR"
if [ -d "$TARGET_DIR/.git" ]; then
  as_deploy git -C "$TARGET_DIR" fetch --quiet origin "$BRANCH"
  as_deploy git -C "$TARGET_DIR" checkout --quiet "$BRANCH"
  as_deploy git -C "$TARGET_DIR" pull --ff-only --quiet origin "$BRANCH"
  echo "atualizado: $(as_deploy git -C "$TARGET_DIR" log --oneline -1)"
else
  as_deploy git clone --quiet --branch "$BRANCH" "$REPO_URL" "$TARGET_DIR"
  echo "clonado: $(as_deploy git -C "$TARGET_DIR" log --oneline -1)"
fi
$SUDO chmod +x "$TARGET_DIR/infra/vps/"*.sh "$TARGET_DIR/infra/scripts/"*.sh 2>/dev/null || true

# ---------------------------------------------------------------------------
# 11. Backup diario do Postgres (o script sai limpo enquanto a stack nao subiu)
# ---------------------------------------------------------------------------
step "cron do backup do Postgres"
printf '%s\n' \
  'SHELL=/bin/bash' \
  'PATH=/usr/local/bin:/usr/bin:/bin' \
  "17 3 * * * $DEPLOY_USER $TARGET_DIR/infra/vps/backup_postgres.sh >> $BACKUP_DIR/backup.log 2>&1" \
  | $SUDO tee /etc/cron.d/hunter-backup >/dev/null
$SUDO chmod 644 /etc/cron.d/hunter-backup
$SUDO systemctl enable --now cron
echo "diario as 03:17 (hora da maquina) -> $BACKUP_DIR, retencao 7 dias"

# ---------------------------------------------------------------------------
# Fim
# ---------------------------------------------------------------------------
cat <<FIM

=== bootstrap concluido ===

O que NAO foi feito de proposito (e do dono da maquina, nao do agente):

  1) entrar como o usuario de deploy:
       ssh $DEPLOY_USER@<ip-da-vps>

  2) criar o .env (as chaves sao digitadas na tela, nunca passam por chat):
       cd $TARGET_DIR && bash infra/scripts/setup_env.sh --vps

  3) subir a stack:
       bash infra/vps/compose.sh up

  4) sessoes de desenvolvimento por SSH (opcional, uma vez cada):
       npm i -g @anthropic-ai/claude-code @openai/codex
       claude          # login no navegador
       codex login     # login no navegador

Verificacoes uteis:
  docker compose ls
  bash infra/vps/compose.sh ps
  bash infra/vps/compose.sh logs
  sudo ufw status verbose
  sudo ss -ltnp | grep -v 127.0.0.1
FIM
