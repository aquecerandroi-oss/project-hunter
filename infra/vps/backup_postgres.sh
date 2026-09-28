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
# O que o dump NAO tem (decisao do Everton, 27/09/2026 -
# docs/design/retencao-e-disco-2026-09-27.md §4): os DADOS de
# opportunity_history (65 % do dump; explicacao historica do radar de
# perpetuos, nenhuma FK aponta para ela). O esquema vai: num restore a tabela
# volta vazia. A outbox continua no dump - o reconcile republica os payloads
# da propria outbox_events, entao tira-la perderia as publicacoes pendentes.
#
# Restaurar (destrutivo - confirme antes):
#   bash infra/vps/compose.sh exec -T postgres \
#     pg_restore -U hunter -d hunter --clean --if-exists < /opt/backups/<arquivo>.dump
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKUP_DIR="${HUNTER_BACKUP_DIR:-/opt/backups}"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

compose() { bash "$ROOT/infra/vps/compose.sh" "$@"; }

# Quantos dumps validos manter (os mais novos, pelo carimbo UTC do nome). O cron
# (/etc/cron.d/hunter-backup) nao carrega o .env: o numero vem do ambiente,
# senao da linha HUNTER_BACKUP_RETENTION_DAYS do .env (so essa linha, nunca o
# arquivo inteiro), senao 3. O nome da variavel ficou "DAYS" por compatibilidade
# (3771a020); desde 27/09/2026 ela conta DUMPS, nao dias: `find -mtime +N`
# guardava N+1 e deixava sobreviver um dump antigo quando o novo terminava mais
# cedo que ele (Astra, 27/09).
retention_count() {
  local raw="${HUNTER_BACKUP_RETENTION_DAYS:-}"
  if [ -z "$raw" ] && [ -f "$ROOT/.env" ]; then
    raw="$(sed -n 's/^HUNTER_BACKUP_RETENTION_DAYS=\([0-9][0-9]*\)[[:space:]]*$/\1/p' "$ROOT/.env" | tail -n 1)"
  fi
  raw="${raw:-3}"
  if ! [[ "$raw" =~ ^[0-9]+$ ]]; then
    log "AVISO: HUNTER_BACKUP_RETENTION_DAYS='$raw' nao e numero; usando 3" >&2
    raw=3
  fi
  # Zero apagaria o dump que acabou de ser feito: o minimo e 1.
  if [ "$raw" -lt 1 ]; then
    raw=1
  fi
  echo "$raw"
}

# Apaga os dumps validos alem dos KEEP mais novos. So olha hunter-<carimbo>.dump
# (o nome final, que so existe depois do pg_restore --list), nunca .partial nem
# archive-*. Chamado so depois de o dump desta noite passar na checagem: uma
# noite que falha nao apaga nada, e o ultimo dump bom sempre fica.
prune_dumps() {
  local dir="$1" keep="$2" name deleted=0
  while IFS= read -r name; do
    rm -f -- "$dir/$name"
    deleted=$((deleted + 1))
  done < <(find "$dir" -maxdepth 1 -type f -name 'hunter-*.dump' -printf '%f\n' \
    | sort -r | tail -n +"$((keep + 1))")
  log "retencao: $keep dump(s); $deleted removido(s); restam $(find "$dir" -maxdepth 1 -type f -name 'hunter-*.dump' | wc -l)"
}

# zstd:3 quando o pg_dump do container foi compilado com zstd (o postgres:16
# da VPS e: pg_config mostra --with-zstd, 16.15 aceita -Z zstd:N); senao a
# compressao padrao do -Fc (gzip), dita no log.
compression_args() {
  local configure
  # Capturado antes de comparar: `| grep -q` com pipefail pode ler um SIGPIPE
  # do compose como "sem zstd".
  configure="$(compose exec -T postgres pg_config --configure 2>/dev/null || true)"
  if [[ "$configure" == *--with-zstd* ]]; then
    echo "-Z zstd:3"
  else
    log "AVISO: pg_dump do container sem zstd; usando a compressao padrao do -Fc (gzip)" >&2
  fi
}

main() {
  local keep stamp target partial compress perm running size
  keep="$(retention_count)"
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  target="$BACKUP_DIR/hunter-$stamp.dump"
  partial="$target.partial"

  umask 077
  mkdir -p "$BACKUP_DIR"
  chmod 700 "$BACKUP_DIR" 2>/dev/null || true
  # Dump do banco inteiro num diretorio legivel por outros e o mesmo que
  # publicar o banco. Se nao der para fechar, nao escreve.
  perm="$(stat -c '%a' "$BACKUP_DIR" 2>/dev/null || echo '?')"
  if [ "$perm" != "700" ]; then
    log "ERRO: $BACKUP_DIR esta com permissao $perm (esperado 700) - nenhum dump gravado"
    exit 1
  fi

  # "postgres parado" e "compose quebrado" precisam ser coisas diferentes: se
  # qualquer erro (daemon fora, .env sumido, YAML invalido) virasse "parado", o
  # cron passaria semanas sem backup nenhum reportando sucesso.
  if ! running="$(compose ps --status running --services 2>&1)"; then
    log "ERRO: 'compose ps' falhou - nao da para saber se ha banco para copiar:"
    log "$running"
    exit 1
  fi
  if ! printf '%s\n' "$running" | grep -qx postgres; then
    # Manutencao ou maquina recem-subida: sai 0 para nao virar alarme falso.
    log "postgres nao esta rodando - nenhum backup feito"
    exit 0
  fi

  # Sobra de uma noite que morreu no meio (reboot, kill): lixo, nunca um dump.
  find "$BACKUP_DIR" -maxdepth 1 -type f -name 'hunter-*.dump.partial' -mmin +360 -delete

  compress="$(compression_args)"
  log "dump -> $target (${compress:-compressao padrao}; sem dados de opportunity_history)"
  # shellcheck disable=SC2086  # $compress e "-Z zstd:3" ou vazio, de proposito sem aspas
  if ! compose exec -T postgres pg_dump -U hunter -d hunter -Fc $compress \
    --exclude-table-data-and-children=opportunity_history > "$partial"; then
    log "ERRO: pg_dump falhou; removendo arquivo parcial e mantendo os antigos"
    rm -f "$partial"
    exit 1
  fi

  # Checagem barata: o pg_restore consegue ler o indice do arquivo? Pega dump
  # vazio, truncado no comeco e arquivo que nao e dump nenhum - o suficiente
  # para nao apagar por retencao os dumps bons em cima de lixo. NAO garante que
  # todos os blocos de dados estejam integros: --list le o indice, nao o dado.
  # O unico teste de verdade e restaurar num banco descartavel de tempos em
  # tempos (README, secao Backup).
  # Sem nome de arquivo: dentro do container "/dev/stdin" nao aponta para o pipe do
  # docker exec e o pg_restore respondia "did not find magic string" para dumps
  # perfeitamente validos (o backup nunca gravou nada ate 2026-09-06 por isso).
  if ! compose exec -T postgres pg_restore --list < "$partial" >/dev/null 2>&1; then
    log "ERRO: dump ilegivel pelo pg_restore; removendo e mantendo os antigos"
    rm -f "$partial"
    exit 1
  fi
  # So um dump que passou na checagem ganha o nome que a retencao conta.
  mv -- "$partial" "$target"

  size="$(du -h "$target" | cut -f1)"
  log "ok: $target ($size)"

  prune_dumps "$BACKUP_DIR" "$keep"
}

# `source` (os testes) so carrega as funcoes; rodar o arquivo faz o backup.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  main "$@"
fi
