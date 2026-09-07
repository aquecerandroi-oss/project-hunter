#!/usr/bin/env bash
# PROJECT HUNTER - atalho unico para operar a stack na VPS.
#
#   bash infra/vps/compose.sh up        # sobe/atualiza tudo (build incluso)
#   bash infra/vps/compose.sh ps        # estado dos containers
#   bash infra/vps/compose.sh logs      # logs ao vivo (Ctrl-C sai)
#   bash infra/vps/compose.sh logs api  # logs de um servico
#   bash infra/vps/compose.sh update    # git pull + rebuild + up
#   bash infra/vps/compose.sh down      # para tudo (dados ficam nos volumes)
#   MARKET_SHARDS=4 bash infra/vps/compose.sh update   # idem, com os shards do coletor
#   bash infra/vps/compose.sh <qualquer subcomando do docker compose>
#
# Existe para nao errar os quatro detalhes que quebram a stack quando alguem
# digita o comando a mao: os dois -f na ordem certa, o --env-file (o compose
# nao le o .env da raiz sozinho, porque o diretorio de projeto e o do primeiro
# -f), o nome de projeto fixo e o cwd.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [ ! -f "$ROOT/.env" ]; then
  echo "sem .env em $ROOT - crie primeiro:" >&2
  echo "  bash infra/scripts/setup_env.sh --vps" >&2
  exit 1
fi
if [ "$(stat -c '%a' "$ROOT/.env")" != "600" ]; then
  echo "AVISO: $ROOT/.env nao esta 600; corrigindo." >&2
  chmod 600 "$ROOT/.env"
fi

# Preflight: CORS_ALLOWED_ORIGINS com URL simples derruba a api no boot -
# ApiSettings declara list[str] e o pydantic-settings tenta json.loads ANTES
# do validador que aceita "a,b". Quem copiou o .env.example (que ainda traz
# CORS_ALLOWED_ORIGINS=http://localhost:3000) sobe uma stack que entra em
# restart loop com SettingsError. Melhor descobrir aqui, em uma linha.
if grep -q '^CORS_ALLOWED_ORIGINS=[^[]' "$ROOT/.env" 2>/dev/null; then
  echo "ERRO: o .env define CORS_ALLOWED_ORIGINS com um valor que nao e lista JSON." >&2
  echo "      A api nao sobe assim (SettingsError). Apague a linha: WEB_ORIGIN ja e o padrao;" >&2
  echo '      se precisar de varias origens, use o formato ["https://a","https://b"].' >&2
  exit 1
fi

COMPOSE=(docker compose --env-file "$ROOT/.env" -p hunter
  -f "$ROOT/infra/docker/docker-compose.yml"
  -f "$ROOT/infra/vps/docker-compose.prod.yml")

# MARKET_SHARDS>1 precisa do perfil `shards` do compose base (market-worker-1..3);
# >4 tambem precisa de `shards8` (market-worker-4..7). Sem isto quem quisesse
# subir os shards tinha que lembrar de `--profile shards` na mao, junto com o
# GIT_SHA - foi digitar isso a mao, sem o GIT_SHA, que deixou a api na tag
# antiga `hunter-api:dev` e o `migrate` falhou com "Can't locate revision"
# (2026-09-07). Com isto, `MARKET_SHARDS=4 bash infra/vps/compose.sh update` e
# o deploy inteiro num comando so.
MARKET_SHARDS="${MARKET_SHARDS:-1}"
PROFILE_ARGS=()
if [[ "$MARKET_SHARDS" =~ ^[0-9]+$ ]]; then
  if [ "$MARKET_SHARDS" -gt 1 ]; then
    PROFILE_ARGS+=(--profile shards)
  fi
  if [ "$MARKET_SHARDS" -gt 4 ]; then
    PROFILE_ARGS+=(--profile shards8)
  fi
else
  echo "AVISO: MARKET_SHARDS='$MARKET_SHARDS' nao e um numero; ignorando (nenhum perfil de shard ativado)." >&2
fi

# GIT_SHA resolvido para TODO subcomando, nao so up/update: docker-compose.yml
# usa `image: hunter-api:${GIT_SHA:-dev}`, e `up`/`update` sao o unico lugar
# que builda e taggeia a imagem com o SHA do commit deployado. Qualquer outro
# subcomando (`run`, `logs`, `exec`, `ps`...) que nao exportasse GIT_SHA cairia
# no default `dev` - uma tag que nao existe na VPS - e o compose reagiria
# buildando a imagem na hora a partir do working tree (nao do commit
# deployado), um `docker build` de vários minutos e sem supervisão numa
# maquina de um core so. `|| true` porque um checkout sem `.git` (nao deveria
# acontecer aqui, mas nao e motivo pra este script quebrar) so deve deixar
# GIT_SHA vazio - ai o `${GIT_SHA:-dev}` do compose file assume o default, tal
# qual antes desta mudanca.
GIT_SHA="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || true)"
export GIT_SHA

# HUNTER_DEFAULT_SNI: o host de HUNTER_SITE_ADDRESS sem esquema/porta (IP ou
# dominio). O Caddy precisa dele para servir o certificado a clientes que nao
# mandam SNI - todo navegador, quando o endereco e um IP.
HUNTER_DEFAULT_SNI="$(sed -n "s#^HUNTER_SITE_ADDRESS=##p" "$ROOT/.env" | head -1 | sed "s#^https\{0,1\}://##; s#[:/].*##")"
export HUNTER_DEFAULT_SNI="${HUNTER_DEFAULT_SNI:-localhost}"

# Depois de um `up`, um servico em `created` ou `exited` (ou `dead`) e um
# deploy que falhou pela metade - por exemplo o `migrate` batendo em revisao
# desconhecida e nunca chegando a `service_completed_successfully`, deixando
# `api` parada em `created`. Isto so reporta (ps + as ultimas linhas de log de
# quem falhou); nao tenta reiniciar nem contornar - quem decide o proximo
# passo e quem esta rodando o deploy.
check_up_status() {
  local status svc
  local -a failed=()
  for status in created exited dead; do
    while IFS= read -r svc; do
      [ -n "$svc" ] && failed+=("$svc")
    done < <("${COMPOSE[@]}" "${PROFILE_ARGS[@]}" ps --filter "status=$status" --services 2>/dev/null || true)
  done
  if [ "${#failed[@]}" -eq 0 ]; then
    return 0
  fi
  echo "" >&2
  echo "ERRO: servico(s) nao subiram (status created/exited/dead): ${failed[*]}" >&2
  "${COMPOSE[@]}" "${PROFILE_ARGS[@]}" ps
  for svc in "${failed[@]}"; do
    echo "" >&2
    echo "--- logs: $svc (ultimas 50 linhas) ---" >&2
    "${COMPOSE[@]}" "${PROFILE_ARGS[@]}" logs --tail 50 "$svc" || true
  done
  return 1
}

cmd="${1:-ps}"
[ "$#" -gt 0 ] && shift

case "$cmd" in
  up)
    "${COMPOSE[@]}" "${PROFILE_ARGS[@]}" up -d --build --remove-orphans "$@"
    echo ""
    "${COMPOSE[@]}" "${PROFILE_ARGS[@]}" ps
    check_up_status
    ;;
  update)
    git -C "$ROOT" pull --ff-only
    GIT_SHA="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || true)"
    export GIT_SHA
    "${COMPOSE[@]}" "${PROFILE_ARGS[@]}" up -d --build --remove-orphans
    "${COMPOSE[@]}" "${PROFILE_ARGS[@]}" ps
    check_up_status
    ;;
  logs)
    "${COMPOSE[@]}" logs -f --tail 200 "$@"
    ;;
  *)
    "${COMPOSE[@]}" "$cmd" "$@"
    ;;
esac
