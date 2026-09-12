#!/usr/bin/env bash
# PROJECT HUNTER - atalho unico para operar a stack na VPS.
#
#   bash infra/vps/compose.sh up        # sobe/atualiza tudo (build incluso)
#   bash infra/vps/compose.sh ps        # estado dos containers
#   bash infra/vps/compose.sh logs      # logs ao vivo (Ctrl-C sai)
#   bash infra/vps/compose.sh logs api  # logs de um servico
#   bash infra/vps/compose.sh update    # git pull + rebuild + up
#   bash infra/vps/compose.sh down      # para tudo (dados ficam nos volumes)
#   bash infra/vps/compose.sh replay python -m hunter_strategy_worker.replay.run \
#     --version <key>:<version> --from ... --to ...   # T3.80: replay em processo proprio,
#                                                       # nunca `docker exec` no worker vivo
#   MARKET_SHARDS=4 bash infra/vps/compose.sh update   # idem, com os shards do coletor
#   MARKET_SPOT=1 MARKET_SHARDS=4 bash infra/vps/compose.sh update   # + o coletor SPOT dedicado (T3.0f)
#   STRATEGY_SHARDS=4 bash infra/vps/compose.sh update   # idem, com os shards do worker de decisao (T3.74f)
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

# Preflight (T3.15e, MEDIUM-D): DATABASE_URL_MIGRATIONS no .env da VPS
# reabriria o HIGH-1 que a T3.15d fechou. `api`/todo worker carregam este
# .env via `env_file:` (infra/docker/docker-compose.yml); a DSN de dono so
# fica de fora do ambiente deles porque nenhum `environment:` a define mais
# la - uma linha aqui a reintroduziria em todo processo de runtime por baixo
# do preflight de qualquer serviço, sem precisar mudar uma linha de compose.
# A DSN de dono pertence só às âncoras `x-owner-env`/`x-prod-owner-env`
# (docker-compose.yml/docker-compose.prod.yml), concedidas só a `migrate` e
# `ops` - nunca ao .env que todo processo lê.
if grep -Eq '^[[:space:]]*(export[[:space:]]+)?DATABASE_URL_MIGRATIONS=' "$ROOT/.env" 2>/dev/null; then
  echo "ERRO: o .env define DATABASE_URL_MIGRATIONS." >&2
  echo "      Essa DSN e do dono do schema e so pertence aos ambientes de" >&2
  echo "      migrate/ops (x-owner-env/x-prod-owner-env nos dois compose files)" >&2
  echo "      - api e todo worker leem este mesmo .env via env_file, entao uma" >&2
  echo "      linha aqui devolveria a credencial a todo processo de runtime" >&2
  echo "      (o achado HIGH-1 que a T3.15d fechou). Apague a linha do .env;" >&2
  echo "      docs/DEPLOYMENT.md secao 3.4 explica onde a DSN de dono e usada." >&2
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

# STRATEGY_SHARDS>1 precisa do perfil `strategy-shards` do compose base
# (strategy-worker-1..3, T3.74f) - mesmo padrao de MARKET_SHARDS acima, mesmo
# motivo: sem isto quem subisse os shards do worker de decisao tinha que
# lembrar de `--profile strategy-shards` na mao. So ate 4 shards por enquanto
# (nao ha um `strategy-worker-4..7`/perfil `strategy-shards8` -- o burst
# medido na T3.74f satura em ~1 nucleo por shard, 4 shards cobrem os ~200
# mercados monitorados hoje; um universo bem maior pediria essa extensao,
# nao adicionada aqui).
STRATEGY_SHARDS="${STRATEGY_SHARDS:-1}"
if [[ "$STRATEGY_SHARDS" =~ ^[0-9]+$ ]]; then
  if [ "$STRATEGY_SHARDS" -gt 1 ]; then
    PROFILE_ARGS+=(--profile strategy-shards)
  fi
  if [ "$STRATEGY_SHARDS" -gt 4 ]; then
    echo "ERRO: STRATEGY_SHARDS='$STRATEGY_SHARDS' > 4, mas so ha strategy-worker-1..3 declarados (perfil strategy-shards)." >&2
    exit 1
  fi
else
  echo "AVISO: STRATEGY_SHARDS='$STRATEGY_SHARDS' nao e um numero; ignorando (nenhum perfil de shard ativado)." >&2
fi
# T3.87: exportado explicitamente (nao so herdado do prefixo do comando) para
# que o `docker compose run --rm replay-worker` do subcomando `replay` abaixo
# sempre repasse esta variavel ao container - o portao de pausa do replay
# (`replay/budget.py::live_lane_degraded`) deriva dela o conjunto de chaves de
# heartbeat/grupos consumidores de TODOS os shards vivos
# (`hunter_strategy_worker.shard.heartbeat_keys`/`consumer_groups`, a mesma
# formula que cada shard ja usa para se nomear - nunca uma segunda formula).
# Quem rodar `replay` precisa passar o MESMO STRATEGY_SHARDS que o `update`/
# `up` mais recente usou - do contrario o portao le a topologia errada (ex.:
# `STRATEGY_SHARDS=1` contra 4 shards vivos volta a olhar so o grupo/chave
# orfaos pre-shard, exatamente o bug que a T3.84/T3.87 mediram).
export STRATEGY_SHARDS

# T3.0f - MARKET_SPOT=1 adiciona o perfil `spot` (market-worker-spot, o
# coletor SPOT dedicado). Mora no ambiente do comando, como MARKET_SHARDS -
# nunca no .env - para que a decisao de ligar o spot fique visivel em cada
# deploy, nunca implicita num arquivo que ninguem esta olhando.
MARKET_SPOT="${MARKET_SPOT:-0}"
if [ "$MARKET_SPOT" = "1" ]; then
  PROFILE_ARGS+=(--profile spot)
fi

# T4.2 - MEME=1 adiciona o perfil `meme` (meme-worker, o radar da pump.fun).
# Mesmo padrao e mesmo motivo do MARKET_SPOT acima: mora no ambiente do
# comando, nunca no .env, para que ligar um coletor que fala com dois
# endpoints de terceiros fique visivel em cada deploy.
#
# Sem isto NAO daria para so subir na mao uma vez: `up`/`update` rodam com
# `--remove-orphans`, entao um `compose.sh update` sem o perfil DERRUBARIA o
# meme-worker que alguem tinha subido com `docker compose --profile meme up`.
# O interruptor e o que torna "o radar sobrevive ao proximo deploy" verdade.
#
#   MEME=1 MEME_ENABLED=true bash infra/vps/compose.sh update
#
# `MEME=1` sozinho sobe o container com o coletor DESLIGADO (MEME_ENABLED
# default false): /health, /ready e /metrics no ar, nada coletado.
MEME="${MEME:-0}"
if [ "$MEME" = "1" ]; then
  PROFILE_ARGS+=(--profile meme)
fi

# T4.14 - MEME_LIVE=1 adiciona o perfil `meme-live` (meme-executor, o unico
# processo que le a chave da carteira Solana). Mesmo padrao e mesmo motivo do
# MEME acima, e a mesma consequencia: sem MEME_LIVE=1 um `compose.sh update`
# DERRUBA o executor (--remove-orphans) - o que e exatamente "como desligar":
#
#   MEME_LIVE=1 MEME=1 MEME_ENABLED=true bash infra/vps/compose.sh update   # ligar
#   MEME=1 MEME_ENABLED=true bash infra/vps/compose.sh update              # desligar
#
# A flag ENABLE_MEME_LIVE_TRADING NUNCA e passada aqui: vive so no .env da VPS.
MEME_LIVE="${MEME_LIVE:-0}"
if [ "$MEME_LIVE" = "1" ]; then
  PROFILE_ARGS+=(--profile meme-live)
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
    # T4.9 (12/09/2026 07:33-07:47 BRT): `up -d --build` recreates every
    # service and only THEN waits for `migrate`; when migration 0023 failed on
    # production rows, the old containers were already gone and the whole
    # stack sat in `Created` for 14 minutes (200 markets without candles).
    # Build, then run the migration ALONE, then bring the services up: a
    # migration that fails now fails with the previous release still running,
    # and `set -e` stops here before anything is recreated.
    # Only `api` and `web` have a build context; every other service reuses
    # `hunter-api:$GIT_SHA`. A bare `build` also tries to *pull* that tag for
    # them first and logs "pull access denied" six times (deploy eeb566c) --
    # harmless, but noise that looks like a failure in the log.
    "${COMPOSE[@]}" "${PROFILE_ARGS[@]}" build api web
    "${COMPOSE[@]}" "${PROFILE_ARGS[@]}" run --rm migrate
    "${COMPOSE[@]}" "${PROFILE_ARGS[@]}" up -d --remove-orphans
    "${COMPOSE[@]}" "${PROFILE_ARGS[@]}" ps
    check_up_status
    ;;
  logs)
    "${COMPOSE[@]}" logs -f --tail 200 "$@"
    ;;
  ops)
    # Trabalho de dono do schema (particoes, seeds, scripts auditados) na
    # imagem JA implantada. Nunca constroi: um `git pull` sem `update` deixa
    # o HEAD a frente da imagem viva, e `docker compose run` construiria
    # sozinho, as 04:07, codigo nunca implantado - rodando como dono do banco
    # (revisao de seguranca da T3.15e, achado F2). Sem imagem, falha alto.
    if ! docker image inspect "hunter-api:${GIT_SHA:-dev}" >/dev/null 2>&1; then
      echo "ERRO: imagem hunter-api:${GIT_SHA:-dev} nao existe nesta maquina." >&2
      echo "      \`ops\` roda so a imagem implantada; rode \`compose.sh update\`" >&2
      echo "      (ou \`up\`) antes, nunca deixe \`run\` construir sozinho." >&2
      exit 1
    fi
    "${COMPOSE[@]}" "${PROFILE_ARGS[@]}" run --rm ops "$@"
    ;;
  replay)
    # T3.80: same rule as `ops` above, same reason -- the replay lane runs
    # the already-deployed image, never builds. A drain kicked off from a
    # stale working tree must not silently build and run undeployed code
    # against the same Postgres a replay's smaller DB pool still shares.
    # This is also the reason a replay must never run via `docker exec
    # hunter-strategy-worker-1 ...` again (measured 2026-09-10: the live
    # lane's own decision lag climbed from a 26 s to a 90 s median while
    # sharing that container) -- `replay-worker` is its own container, with
    # its own (smaller) DB pool and its own CPU/memory ceiling, and
    # `replay/run.py`'s own guard refuses outright if `HUNTER_ROLE=strategy`
    # is ever set on it by mistake.
    if ! docker image inspect "hunter-api:${GIT_SHA:-dev}" >/dev/null 2>&1; then
      echo "ERRO: imagem hunter-api:${GIT_SHA:-dev} nao existe nesta maquina." >&2
      echo "      \`replay\` roda so a imagem implantada; rode \`compose.sh update\`" >&2
      echo "      (ou \`up\`) antes, nunca deixe \`run\` construir sozinho." >&2
      exit 1
    fi
    # T3.87: visivel a cada corrida - o portao de pausa deste container deriva
    # sua topologia de STRATEGY_SHARDS; se isto nao bater com o `update`/`up`
    # mais recente (ex.: a stack viva tem 4 shards e ninguem passou
    # STRATEGY_SHARDS=4 aqui), o portao olha a topologia errada.
    echo "replay-worker: STRATEGY_SHARDS=$STRATEGY_SHARDS (deve bater com o update/up mais recente)" >&2
    "${COMPOSE[@]}" "${PROFILE_ARGS[@]}" run --rm replay-worker "$@"
    ;;
  *)
    "${COMPOSE[@]}" "$cmd" "$@"
    ;;
esac
