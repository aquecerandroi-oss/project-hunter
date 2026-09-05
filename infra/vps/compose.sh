#!/usr/bin/env bash
# PROJECT HUNTER - atalho unico para operar a stack na VPS.
#
#   bash infra/vps/compose.sh up        # sobe/atualiza tudo (build incluso)
#   bash infra/vps/compose.sh ps        # estado dos containers
#   bash infra/vps/compose.sh logs      # logs ao vivo (Ctrl-C sai)
#   bash infra/vps/compose.sh logs api  # logs de um servico
#   bash infra/vps/compose.sh update    # git pull + rebuild + up
#   bash infra/vps/compose.sh down      # para tudo (dados ficam nos volumes)
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

cmd="${1:-ps}"
[ "$#" -gt 0 ] && shift

case "$cmd" in
  up)
    "${COMPOSE[@]}" up -d --build --remove-orphans "$@"
    echo ""
    "${COMPOSE[@]}" ps
    ;;
  update)
    git -C "$ROOT" pull --ff-only
    GIT_SHA="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || true)"
    export GIT_SHA
    "${COMPOSE[@]}" up -d --build --remove-orphans
    "${COMPOSE[@]}" ps
    ;;
  logs)
    "${COMPOSE[@]}" logs -f --tail 200 "$@"
    ;;
  *)
    "${COMPOSE[@]}" "$cmd" "$@"
    ;;
esac
