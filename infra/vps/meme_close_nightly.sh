#!/usr/bin/env bash
# T4.15 — o fechamento diário do Lab meme, à noite, sem sujar a árvore da VPS.
#
# O script `infra/scripts/meme_close_day.py` escreve no vault (`obsidian/`) e em
# `.claude/state/` — registos que só o orquestrador commita, por pathspec, a partir
# do clone local. Para o cron nunca deixar a árvore de /opt/project-hunter suja
# (um `git pull` do `compose.sh update` conflitaria no dia em que a mesma página
# fosse editada dos dois lados), o job roda numa CÓPIA dos dois diretórios em
# /opt/hunter-close e deixa um patch (`diff -ruN`, aplicável com `patch -p0` na
# raiz do repositório) que o orquestrador puxa de manhã, aplica e commita.
#
# Uso: meme_close_nightly.sh [YYYY-MM-DD]   (sem dia: ontem, no relógio de Brasília)
# Cron (docs/DEPLOYMENT.md §3.6b): 10 5 * * * na hora local do host (Europe/Berlin): 00:10 BRT no CEST, 01:10 BRT no CET.
set -euo pipefail

ROOT=/opt/project-hunter
OUT=/opt/hunter-close
DAY="${1:-}"

mkdir -p "$OUT"
rsync -a --delete "$ROOT/obsidian/" "$OUT/obsidian/"
rsync -a --delete "$ROOT/.claude/state/" "$OUT/state/"

cd "$ROOT"
GIT_SHA="$(git rev-parse --short HEAD)"
export GIT_SHA
args=(--apply)
if [ -n "$DAY" ]; then args=(--day "$DAY" --apply); fi

stamp="$(date -u +%Y%m%d-%H%M)"
log="$OUT/run-$stamp.log"
set +e
docker compose --env-file .env -p hunter \
  -f infra/docker/docker-compose.yml -f infra/vps/docker-compose.prod.yml \
  run --rm --user "$(id -u):$(id -g)" \
  -v "$OUT/obsidian:/app/obsidian" \
  -v "$OUT/state:/app/.claude/state" \
  ops python infra/scripts/meme_close_day.py "${args[@]}" > "$log" 2>&1
rc=$?
set -e

# O patch, com caminhos relativos à raiz do repositório (patch -p0).
{
  diff -ruN obsidian "$OUT/obsidian" || true
  diff -ruN .claude/state "$OUT/state" || true
} > "$OUT/patch-$stamp.diff"

echo "meme_close_day exit=$rc log=$log patch=$OUT/patch-$stamp.diff ($(wc -l < "$OUT/patch-$stamp.diff") linhas)"
# exit 2 = dia já fechado; exit 3 = dia sem aposta fechada — ambos esperados, não são falha do cron.
case "$rc" in 0|2|3) exit 0 ;; *) tail -20 "$log"; exit "$rc" ;; esac
