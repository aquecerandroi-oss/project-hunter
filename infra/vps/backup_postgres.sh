#!/usr/bin/env bash
# PROJECT HUNTER - dump diario do Postgres da VPS.
#
# Instalado pelo bootstrap em /etc/cron.d/hunter-backup (03:17, todo dia,
# como o usuario de deploy). Rodar a mao tambem funciona:
#   bash infra/vps/backup_postgres.sh
#
# Formato custom do pg_dump (-Fc): ja vem comprimido, permite restaurar uma
# tabela so e e verificavel sem restaurar (pg_restore --list). O dump sai
# 600, dentro de um diretorio que so o usuario de deploy le.
#
# Restaurar (destrutivo - confirme antes):
#   bash infra/vps/compose.sh exec -T postgres \
#     pg_restore -U hunter -d hunter --clean --if-exists < /opt/backups/<arquivo>.dump
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKUP_DIR="${HUNTER_BACKUP_DIR:-/opt/backups}"
RETENTION_DAYS="${HUNTER_BACKUP_RETENTION_DAYS:-7}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="$BACKUP_DIR/hunter-$STAMP.dump"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

compose() { bash "$ROOT/infra/vps/compose.sh" "$@"; }

umask 077
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR" 2>/dev/null || true
# Dump do banco inteiro num diretorio legivel por outros e o mesmo que
# publicar o banco. Se nao der para fechar, nao escreve.
PERM="$(stat -c '%a' "$BACKUP_DIR" 2>/dev/null || echo '?')"
if [ "$PERM" != "700" ]; then
  log "ERRO: $BACKUP_DIR esta com permissao $PERM (esperado 700) - nenhum dump gravado"
  exit 1
fi

# "postgres parado" e "compose quebrado" precisam ser coisas diferentes: se
# qualquer erro (daemon fora, .env sumido, YAML invalido) virasse "parado", o
# cron passaria semanas sem backup nenhum reportando sucesso.
if ! RUNNING="$(compose ps --status running --services 2>&1)"; then
  log "ERRO: 'compose ps' falhou - nao da para saber se ha banco para copiar:"
  log "$RUNNING"
  exit 1
fi
if ! printf '%s\n' "$RUNNING" | grep -qx postgres; then
  # Manutencao ou maquina recem-subida: sai 0 para nao virar alarme falso.
  log "postgres nao esta rodando - nenhum backup feito"
  exit 0
fi

log "dump -> $TARGET"
if ! compose exec -T postgres pg_dump -U hunter -d hunter -Fc > "$TARGET"; then
  log "ERRO: pg_dump falhou; removendo arquivo parcial e mantendo os antigos"
  rm -f "$TARGET"
  exit 1
fi

# Checagem barata: o pg_restore consegue ler o indice do arquivo? Pega dump
# vazio, truncado no comeco e arquivo que nao e dump nenhum - o suficiente
# para nao apagar por retencao os dumps bons em cima de lixo. NAO garante que
# todos os blocos de dados estejam integros: --list le o indice, nao o dado.
# O unico teste de verdade e restaurar num banco descartavel de tempos em
# tempos (README, secao Backup).
if ! compose exec -T postgres pg_restore --list /dev/stdin < "$TARGET" >/dev/null 2>&1; then
  log "ERRO: dump ilegivel pelo pg_restore; removendo e mantendo os antigos"
  rm -f "$TARGET"
  exit 1
fi

SIZE="$(du -h "$TARGET" | cut -f1)"
log "ok: $TARGET ($SIZE)"

# -mtime +N e "mais de N periodos de 24h", nao "guarde N arquivos": com uma
# execucao por dia sobram 8 dumps, nao 7. Bom o bastante, mas e isso que o
# numero significa.
DELETED="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'hunter-*.dump' -mtime "+$RETENTION_DAYS" -print -delete | wc -l)"
log "retencao ${RETENTION_DAYS}d: $DELETED arquivo(s) removido(s); restam $(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'hunter-*.dump' | wc -l)"
