#!/usr/bin/env bash
# PROJECT HUNTER - cria o .env pedindo as chaves na tela (entrada oculta).
# Versao bash do infra/scripts/setup_env.ps1, para Linux/VPS.
#
# Uso:
#   bash infra/scripts/setup_env.sh          # perfil local (dev)
#   bash infra/scripts/setup_env.sh --vps    # perfil VPS (HUNTER_ENV=staging)
#
# As chaves nunca passam por chat, log ou agente: voce digita, o arquivo e
# gravado com permissao 600, fim. Nada e ecoado na tela alem de prefixo e
# tamanho. Arquivo mantido em ASCII puro.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_PATH="$ROOT/.env"
PROFILE="local"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --vps) PROFILE="vps"; shift ;;
    --local) PROFILE="local"; shift ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    *) echo "argumento desconhecido: $1" >&2; exit 64 ;;
  esac
done

echo ""
echo "PROJECT HUNTER - configuracao do .env (perfil: $PROFILE)"
echo "Arquivo: $ENV_PATH"
echo "Pegue as chaves em clerk.com -> sua aplicacao -> Configure -> API keys."
echo ""

# ---------------------------------------------------------------------------
# read_existing <NOME> - le o valor de uma variavel de um .env ja existente.
# Serve para preservar segredos gerados, POSTGRES_PASSWORD sobretudo: essa
# senha so e aplicada quando o volume do Postgres e inicializado; regerar uma
# senha nova num .env novo deixa a api sem conseguir conectar no banco que ja
# existe (autenticacao falha em todo boot, e o dado esta la dentro).
# ---------------------------------------------------------------------------
read_existing() {
  [ -f "$ENV_PATH" ] || return 0
  sed -n "s/^$1=//p" "$ENV_PATH" | head -1
}

OLD_PG_PASSWORD="$(read_existing POSTGRES_PASSWORD)"
OLD_AUTH_SECRET="$(read_existing AUTH_SECRET)"
OLD_MASTER_KEY="$(read_existing HUNTER_MASTER_KEY)"

if [ -f "$ENV_PATH" ]; then
  printf 'Ja existe um .env. Sobrescrever? (s/N) '
  read -r answer
  case "$answer" in
    s|S) : ;;
    *) echo "Nada alterado."; exit 0 ;;
  esac
  if [ -n "$OLD_PG_PASSWORD" ]; then
    echo "  (POSTGRES_PASSWORD atual preservado - o volume do Postgres ja nasceu com ela)"
  fi
fi

# ---------------------------------------------------------------------------
# extract_key <texto> <prefixo> - aceita o valor puro ou "NOME=valor" (o
# formato que o Clerk copia), com ou sem aspas, e devolve o primeiro token com
# o prefixo esperado. Uma linha por vez: o prompt le uma linha (read), entao
# colar o bloco inteiro do Clerk faz a segunda linha cair no prompt seguinte.
# ---------------------------------------------------------------------------
extract_key() {
  local raw="$1" prefix="$2" token candidate
  for token in $(printf '%s' "$raw" | tr -d "\"'" | tr -s '[:space:]' ' '); do
    # Tira "NOME=" so quando o token e mesmo uma atribuicao, e so ate o
    # PRIMEIRO "=". Cortar ate o ultimo (${token##*=}) engolia o proprio
    # segredo quando ele termina em padding base64: whsec_...== virava vazio
    # e o prompt recusava para sempre uma chave correta.
    candidate="$token"
    case "$candidate" in
      "$prefix"*) : ;;
      [A-Za-z_]*=*) candidate="${token#*=}" ;;
    esac
    case "$candidate" in
      "$prefix"*)
        if [ "${#candidate}" -gt $(( ${#prefix} + 10 )) ]; then
          printf '%s' "$candidate"
          return 0
        fi
        ;;
    esac
  done
  return 1
}

# read_secret <label> <prefixo> - digitacao oculta, valida o prefixo, repete.
# Todo texto de tela vai para stderr: o valor lido sai por stdout e e o unico
# conteudo que o chamador captura com $( ).
read_secret() {
  local label="$1" prefix="$2" value="" plain=""
  while [ -z "$value" ]; do
    printf '%s (comeca com %s; digitacao oculta): ' "$label" "$prefix" >&2
    read -rs plain; echo "" >&2
    value="$(extract_key "$plain" "$prefix" || true)"
    plain=""
    if [ -z "$value" ]; then
      echo "  valor invalido: precisa conter uma chave que comeca com $prefix. Tente de novo." >&2
    fi
  done
  printf '%s' "$value"
}

read_optional_secret() {
  local plain=""
  printf '%s (opcional, Enter para pular; digitacao oculta): ' "$1" >&2
  read -rs plain; echo "" >&2
  printf '%s' "$(printf '%s' "$plain" | tr -d '[:space:]')"
}

# gen_secret - 32 bytes aleatorios em hex. openssl vem no Ubuntu; /dev/urandom
# e o plano B para qualquer imagem minima que nao o tenha.
gen_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'
  fi
}

# HUNTER_MASTER_KEY e documentado em .env.example como "base64 de 32 bytes"
# (em producao vira KMS) - gerar hex aqui deixaria um valor que o dia em que
# alguem der base64-decode nele nao vai aceitar.
gen_b64_key() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 32
  else
    head -c 32 /dev/urandom | base64
  fi
}

mask() { printf '%s... (%s caracteres)' "$(printf '%s' "$1" | cut -c1-8)" "${#1}"; }

# ---------------------------------------------------------------------------
# Perguntas
# ---------------------------------------------------------------------------
ISSUER_DEFAULT="https://measured-stingray-3890.clerk.accounts.dev"
printf 'CLERK_ISSUER (Enter para usar %s): ' "$ISSUER_DEFAULT"
read -r ISSUER
[ -n "$ISSUER" ] || ISSUER="$ISSUER_DEFAULT"
# Uma chave colada aqui por engano viraria CLERK_ISSUER/CLERK_JWKS_URL invalidos e
# derrubaria toda a autenticacao (aconteceu na VPS em 2026-09-06): so aceita URL.
case "$ISSUER" in
  https://*) ;;
  *) echo "CLERK_ISSUER precisa ser uma URL https:// (ex.: $ISSUER_DEFAULT); recebido algo que nao e URL. Nada foi gravado." >&2; exit 64 ;;
esac
ISSUER="${ISSUER%/}"

PUBLIC_URL="http://127.0.0.1:3000"
WS_URL="ws://127.0.0.1:3000/ws"
SITE_ADDRESS=""
ACME_EMAIL=""

if [ "$PROFILE" = "vps" ]; then
  echo ""
  echo "Dominio publico do HUNTER nesta VPS (ex.: hunter.seudominio.com)."
  echo "Sem dominio, deixe vazio: o Caddy serve em HTTP na porta 80 pelo IP"
  echo "(sem TLS; o Clerk costuma recusar sign-in fora de um dominio real)."
  printf 'DOMINIO (Enter para nenhum): '
  read -r DOMAIN
  DOMAIN="$(printf '%s' "$DOMAIN" | tr -d '[:space:]' | sed 's#^https\{0,1\}://##; s#/.*$##')"
  if [ -n "$DOMAIN" ]; then
    PUBLIC_URL="https://$DOMAIN"
    WS_URL="wss://$DOMAIN/ws"
    SITE_ADDRESS="$DOMAIN"
    # Obrigatorio quando ha dominio: e o endereco que recebe o aviso de
    # certificado prestes a expirar se a renovacao automatica parar.
    while [ -z "$ACME_EMAIL" ]; do
      printf 'E-mail para o certificado TLS (Lets Encrypt): '
      read -r ACME_EMAIL
      case "$ACME_EMAIL" in
        ?*@?*.?*) : ;;
        *) echo "  e-mail invalido, tente de novo."; ACME_EMAIL="" ;;
      esac
    done
  else
    printf 'IP publico da VPS (para as URLs do frontend): '
    read -r VPS_IP
    VPS_IP="$(printf '%s' "$VPS_IP" | tr -d '[:space:]')"
    [ -n "$VPS_IP" ] || { echo "sem dominio e sem IP nao da para montar as URLs publicas." >&2; exit 64; }
    PUBLIC_URL="http://$VPS_IP"
    WS_URL="ws://$VPS_IP/ws"
    SITE_ADDRESS=":80"
  fi
fi

echo ""
PK="$(read_secret NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY pk_test_)"
SK="$(read_secret CLERK_SECRET_KEY sk_test_)"

WHSEC=""
if [ "$PROFILE" = "vps" ]; then
  echo ""
  echo "CLERK_WEBHOOK_SECRET e obrigatorio em HUNTER_ENV=staging (o processo se"
  echo "recusa a subir sem ele). Clerk -> Configure -> Webhooks -> seu endpoint"
  echo "($PUBLIC_URL/api/webhooks/clerk) -> Signing Secret."
  WHSEC="$(read_secret CLERK_WEBHOOK_SECRET whsec_)"
fi

OPENAI="$(read_optional_secret OPENAI_API_KEY)"

PG_PASSWORD="${OLD_PG_PASSWORD:-$(gen_secret)}"
AUTH_SECRET="${OLD_AUTH_SECRET:-$(gen_secret)}"
MASTER_KEY="${OLD_MASTER_KEY:-$(gen_b64_key)}"

# ---------------------------------------------------------------------------
# Escrita atomica: monta um temporario 600 no mesmo diretorio e so entao
# substitui o .env. Escrever direto por cima truncaria o arquivo antes de
# terminar - disco cheio ou Ctrl-C no meio deixaria um .env pela metade, sem
# o POSTGRES_PASSWORD, que e a unica copia que existe da senha do banco com
# os dados dentro. O umask tambem nao conserta permissao de arquivo que ja
# existe; nascendo novo, nasce 600.
# ---------------------------------------------------------------------------
if [ -L "$ENV_PATH" ]; then
  echo "$ENV_PATH e um link simbolico - recusando escrever (aponte para onde?)." >&2
  exit 1
fi
umask 077
# mktemp, nao "$ENV_PATH.tmp.$$": nome de PID e previsivel, e quem adivinhar
# pode plantar um symlink ali e fazer os segredos serem escritos em outro
# lugar. mktemp cria o arquivo de verdade, 600, no mesmo diretorio.
ENV_TMP="$(mktemp "$ENV_PATH.XXXXXX")"
trap 'rm -f "$ENV_TMP"' EXIT
{
  echo "# PROJECT HUNTER - gerado por infra/scripts/setup_env.sh (perfil: $PROFILE)."
  echo "# NUNCA commitar. Regerar: bash infra/scripts/setup_env.sh --$PROFILE"
  echo "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=$PK"
  echo "CLERK_SECRET_KEY=$SK"
  echo "CLERK_ISSUER=$ISSUER"
  echo "CLERK_JWKS_URL=$ISSUER/.well-known/jwks.json"
  [ -n "$WHSEC" ] && echo "CLERK_WEBHOOK_SECRET=$WHSEC"
  echo "AUTH_SECRET=$AUTH_SECRET"
  echo "HUNTER_MASTER_KEY=$MASTER_KEY"
  if [ "$PROFILE" = "vps" ]; then
    echo "HUNTER_ENV=staging"
    echo "SENTRY_ENVIRONMENT=staging"
    echo "POSTGRES_PASSWORD=$PG_PASSWORD"
    echo "HUNTER_PUBLIC_URL=$PUBLIC_URL"
    echo "HUNTER_WS_URL=$WS_URL"
    echo "HUNTER_SITE_ADDRESS=$SITE_ADDRESS"
    echo "HUNTER_ACME_EMAIL=$ACME_EMAIL"
    echo "WEB_ORIGIN=$PUBLIC_URL"
    # CORS_ALLOWED_ORIGINS de proposito ausente: ApiSettings declara list[str]
    # e o pydantic-settings tenta json.loads no valor ANTES do validador que
    # aceita "a,b" - uma URL simples derruba a api no boot com SettingsError.
    # Sem a variavel, _default_cors_from_web_origin usa WEB_ORIGIN, que e
    # exatamente o valor que queremos. (Bug do .env.example, ver relatorio.)
    echo "API_URL=$PUBLIC_URL"
    echo "NEXT_PUBLIC_API_URL=$PUBLIC_URL"
    echo "NEXT_PUBLIC_WS_URL=$WS_URL"
  fi
  if [ -n "$OPENAI" ]; then
    echo "OPENAI_API_KEY=$OPENAI"
    echo "OPENAI_MODEL=gpt-6-astra"
  fi
} > "$ENV_TMP"
chmod 600 "$ENV_TMP"
mv -f "$ENV_TMP" "$ENV_PATH"
trap - EXIT

echo ""
echo "OK: .env gravado ($(grep -c '^[A-Z]' "$ENV_PATH") variaveis, valores nao exibidos, permissao 600)."
echo "  publishable key: $(mask "$PK")"
echo "  secret key:      $(mask "$SK")"
if [ "$PROFILE" = "vps" ]; then
  echo "  URL publica:     $PUBLIC_URL"
  echo "  senha do Postgres: gerada/preservada, so dentro do .env"
  echo ""
  echo "Proximo passo: bash infra/vps/compose.sh up"
else
  echo ""
  echo "Proximo passo: docker compose -f infra/docker/docker-compose.yml up -d --build"
fi
