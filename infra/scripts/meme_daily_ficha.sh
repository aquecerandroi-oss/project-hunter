#!/usr/bin/env bash
# T4.92 — a ficha diária automática: roda `meme_daily_ficha.py` (SELECT-only)
# na imagem já implantada da VPS pelo serviço `ops` (mesmo padrão de
# `bash infra/vps/compose.sh ops ...`, docs/DEPLOYMENT.md §3.4 / infra/vps/README.md)
# e grava a saída localmente — nada é escrito na árvore da VPS.
#
# Uso:
#   bash infra/scripts/meme_daily_ficha.sh                     # ontem (Brasília)
#   bash infra/scripts/meme_daily_ficha.sh 2026-09-24           # um dia específico
#   bash infra/scripts/meme_daily_ficha.sh --week               # resumo dos últimos 7 dias
#   bash infra/scripts/meme_daily_ficha.sh --week 2026-09-25    # semana terminando nesse dia
#
# Requer acesso SSH já configurado ao host `hunter-vps` (infra/vps/README.md).
# Grava em obsidian/03-TRADING/Meme/Fichas/Ficha-<dia>.md
# (ou Ficha-semanal-<dia final>.md no modo --week); sobrescreve se já existir —
# a ficha é um relatório derivado do banco, não um diário editado à mão.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="$ROOT/obsidian/03-TRADING/Meme/Fichas"

week=0
day=""
for arg in "$@"; do
  case "$arg" in
    --week) week=1 ;;
    -*) echo "opção desconhecida: $arg" >&2; exit 64 ;;
    *) day="$arg" ;;
  esac
done

# O dia é sempre resolvido aqui (nunca deixado implícito no remoto): garante que
# o nome do arquivo local bate exatamente com o dia que o script gerou, mesmo
# que o relógio do host remoto e o daqui discordem por alguns segundos perto da
# virada da meia-noite de Brasília.
if [ -z "$day" ]; then
  day="$(TZ=America/Sao_Paulo date -d yesterday +%Y-%m-%d)"
fi

# Astra (T4.92 review, MEDIUM): "$day" vira texto de comando remoto via ssh
# (linha abaixo) e nome de arquivo local — um argumento tipo "2026-09-24; rm -rf
# /" executaria no host remoto antes desta checagem. AAAA-MM-DD estrito, nada
# além disso passa.
case "$day" in
  [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) ;;
  *)
    echo "ERRO: dia '$day' não é AAAA-MM-DD" >&2
    exit 64
    ;;
esac

if [ "$week" = "1" ]; then
  target="$OUT_DIR/Ficha-semanal-$day.md"
  remote_cmd="cd /opt/project-hunter && bash infra/vps/compose.sh ops python infra/scripts/meme_daily_ficha.py --week --day $day"
else
  target="$OUT_DIR/Ficha-$day.md"
  remote_cmd="cd /opt/project-hunter && bash infra/vps/compose.sh ops python infra/scripts/meme_daily_ficha.py --day $day"
fi

mkdir -p "$OUT_DIR"
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

echo "gerando $target via hunter-vps ..." >&2
ssh hunter-vps "$remote_cmd" > "$tmp"

if [ ! -s "$tmp" ]; then
  echo "ERRO: a saída remota veio vazia; nada gravado em $target" >&2
  exit 65
fi

mv "$tmp" "$target"
trap - EXIT
echo "gravado: $target"
