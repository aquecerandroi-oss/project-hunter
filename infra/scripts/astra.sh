#!/usr/bin/env bash
# PROJECT HUNTER — canal único Claude ⇄ Astra (OpenAI GPT-6 via Codex CLI).
#
#   infra/scripts/astra.sh ask      <topic> "<pergunta>"      # opinião (não modifica nada; verificado por git)
#   infra/scripts/astra.sh run      <brief.md>                # execução de um brief (sem sandbox; autorizado 2026-09-05)
#   infra/scripts/astra.sh dialogue <topic> "<mensagem>"      # rodada de diálogo: Claude escreve, Astra responde no mesmo arquivo
#   infra/scripts/astra.sh show     <topic>                   # imprime a transcrição do diálogo
#
# Transcrições: .claude/state/dialogue-<topic>.md   Opiniões: .claude/state/astra-review-<topic>.md
# Relatório da última execução: .claude/state/astra-last.md
#
# Por que sem sandbox: no Windows o sandbox do Codex (read-only/workspace-write) bloqueia até
# a leitura de arquivos ("blocked by policy"). Controles compensatórios: sempre -C no repositório,
# instrução explícita de não modificar (ask/dialogue) verificada com `git status` antes/depois,
# um brief por execução, revisão do diff antes de qualquer commit. Nunca lê .env.

set -euo pipefail

# Repo root = two levels above this script, wherever the clone lives (Windows dev box or the VPS).
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STATE="$REPO/.claude/state"
MODEL="${ASTRA_MODEL:-gpt-6-astra}"
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)  # Everton's Windows box: toolchain is not on the Git Bash PATH by default
    export PATH="/c/Program Files/nodejs:/c/Users/evert/AppData/Roaming/npm:/c/Users/evert/AppData/Local/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe:/c/Users/evert/.local/bin:$PATH" ;;
  *)                     # Linux (VPS): user-level npm prefix from the bootstrap
    export PATH="$HOME/.npm-global/bin:$HOME/.local/bin:$PATH" ;;
esac

GUARD="Regras fixas: AGENTS.md na raiz do repositório é o seu toolkit (mesmo do Claude: CLAUDE.md, roster em .claude/agents, regras em .claude/rules) e vale integralmente. Você é a Astra, um dos dois motores de raciocínio da Sexta-feira (o outro é o Claude) no PROJECT HUNTER; juntos vocês são uma só assistente. Antes de responder leia obsidian/00-HOME.md e as páginas do Obsidian dos módulos envolvidos (obsidian/ é a memória compartilhada; os diálogos anteriores estão em obsidian/06-DECISIONS/Dialogos e as suas revisões em obsidian/06-DECISIONS/Revisoes-Astra). Nunca leia .env. Nunca toque em nada fora de C:/dev/project-hunter. Nunca faça commit. Responda em português, de forma concreta, citando arquivo e linha quando afirmar algo sobre o código, e termine com uma seção OBSIDIAN listando quais páginas da base deveriam ser atualizadas por causa desta resposta (título da página + 1 linha)."

usage() { sed -n '2,12p' "$0"; exit 64; }

snapshot() { git -C "$REPO" status --porcelain | sort; }

check_unchanged() {
  local before="$1" after
  after="$(snapshot)"
  if [ "$before" != "$after" ]; then
    echo "AVISO: a Astra alterou a árvore de trabalho num modo que não permite alterações:" >&2
    diff <(echo "$before") <(echo "$after") >&2 || true
    return 1
  fi
}

run_codex() {
  local out="$1" prompt="$2"
  codex exec -m "$MODEL" --dangerously-bypass-approvals-and-sandbox -C "$REPO" --ephemeral -o "$out" "$prompt" </dev/null >/dev/null 2>"$STATE/astra-stderr.log" || {
    echo "codex falhou (veja $STATE/astra-stderr.log)" >&2; return 1; }
}

cmd_ask() {
  local topic="$1" question="$2" before
  local out="$STATE/astra-review-$topic.md"
  before="$(snapshot)"
  run_codex "$out" "$GUARD Modo OPINIÃO: leia os arquivos que precisar, mas NÃO crie nem modifique nenhum arquivo. Pergunta: $question"
  check_unchanged "$before" || true
  cat "$out"
}

cmd_run() {
  local brief="$1"
  [ -f "$brief" ] || { echo "brief não encontrado: $brief" >&2; exit 66; }
  run_codex "$STATE/astra-last.md" "$GUARD Modo EXECUÇÃO: leia o arquivo $brief e execute-o exatamente: só os arquivos que ele lista, rode os comandos de verificação que ele lista, corrija falhas e termine com o formato de relatório que ele pede."
  cat "$STATE/astra-last.md"
  echo; echo "--- git status após a execução:"; git -C "$REPO" status --short
}

cmd_dialogue() {
  local topic="$1" message="$2" round before
  local file="$STATE/dialogue-$topic.md"
  mkdir -p "$STATE"
  if [ ! -f "$file" ]; then
    printf '# Diálogo Claude ⇄ Astra — %s\n\nRegras: rodadas numeradas; cada uma responde à anterior ponto a ponto; discordância vem com cenário de falha ou comando que decide; a rodada final começa com "DECISÃO CONJUNTA" e é copiada para o plano/ADR pelo Claude.\n' "$topic" > "$file"
  fi
  round=$(( $(grep -c '^## Claude' "$file" || true) + 1 ))
  printf '\n## Claude (rodada %s)\n%s\n' "$round" "$message" >> "$file"
  before="$(snapshot)"
  run_codex "$STATE/astra-dialogue-last.md" "$GUARD Modo DIÁLOGO. Leia o arquivo $file inteiro (é a conversa entre você e o Claude sobre '$topic') e os arquivos do repositório que ele mencionar. Responda à última rodada do Claude ponto a ponto. Depois APPEND ao final de $file (sem apagar nada) uma seção '## Astra (rodada $round)' com a sua resposta. Não modifique nenhum outro arquivo. Se você e o Claude já convergiram, comece a seção com 'DECISÃO CONJUNTA' e liste os pontos acordados."
  local after; after="$(git -C "$REPO" status --porcelain | sort | grep -v "dialogue-$topic.md" || true)"
  before="$(echo "$before" | grep -v "dialogue-$topic.md" || true)"
  [ "$before" = "$after" ] || echo "AVISO: arquivos além da transcrição mudaram; confira git status." >&2
  echo "--- última seção da Astra:"; awk -v r="## Astra (rodada $round)" 'index($0,r){p=1} p' "$file"
}

cmd_show() { cat "$STATE/dialogue-$1.md"; }

[ $# -ge 1 ] || usage
case "$1" in
  ask)      [ $# -eq 3 ] || usage; cmd_ask "$2" "$3" ;;
  run)      [ $# -eq 2 ] || usage; cmd_run "$2" ;;
  dialogue) [ $# -eq 3 ] || usage; cmd_dialogue "$2" "$3" ;;
  show)     [ $# -eq 2 ] || usage; cmd_show "$2" ;;
  *) usage ;;
esac
