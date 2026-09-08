#!/usr/bin/env bash
# Sexta-feira's Hermes home — create/refresh the `sexta-feira` profile (a Bot in the
# desktop app) from the files versioned in infra/hermes/, without touching the
# default profile. Idempotent: run it again after editing SOUL.md, the memory
# seeds or the skills.
#
# What this script reads and writes, exactly: it never reads the repository's
# own `.env` (nothing here touches project-hunter's secrets). The first run
# does `hermes profile create --clone`, which clones the *active* Hermes
# profile's own `.env` — a second copy of whatever keys that profile already
# has, living under $HERMES_HOME/profiles/sexta-feira/. Security review T3.15
# MEDIUM 6: rotate the active profile's keys and this clone goes stale, silent
# and forgotten; if that risk matters more than the convenience, create the
# profile without `--clone` and set its keys explicitly instead, so there is
# one place to rotate from.
#
#   bash infra/hermes/install.sh              # create or refresh
#   bash infra/hermes/install.sh --routine    # also (re)register the hourly plantão routine
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HERMES_HOME="${HERMES_HOME:-$LOCALAPPDATA/hermes}"
HERMES_BIN="${HERMES_BIN:-$HERMES_HOME/bin/hermes.exe}"
PROFILE="sexta-feira"
PROFILE_DIR="$HERMES_HOME/profiles/$PROFILE"
SRC="$REPO/infra/hermes"
REPO_WIN="$(cygpath -w "$REPO" 2>/dev/null || echo "$REPO")"

[ -x "$HERMES_BIN" ] || { echo "hermes CLI not found at $HERMES_BIN (set HERMES_BIN)"; exit 1; }

if ! "$HERMES_BIN" profile list 2>/dev/null | grep -Eq "^ *[^A-Za-z]*$PROFILE( |$)"; then
  echo "== creating profile $PROFILE (clone of the active profile: config, .env, skills)"
  "$HERMES_BIN" profile create "$PROFILE" --clone \
    --description "Sexta-feira: Everton's personal agent and orchestrator of PROJECT HUNTER (crypto paper-trading lab). Portuguese. Owns briefs, reviews, commits, the Obsidian base and the plantão."
fi
[ -d "$PROFILE_DIR" ] || { echo "profile dir $PROFILE_DIR not found after create"; exit 1; }

echo "== SOUL.md"
cp "$SRC/SOUL.md" "$PROFILE_DIR/SOUL.md"

echo "== memory seeds (only when the profile has none yet; Hermes owns them afterwards)"
mkdir -p "$PROFILE_DIR/memories"
for f in MEMORY.md USER.md; do
  if [ ! -s "$PROFILE_DIR/memories/$f" ]; then
    cp "$SRC/memories/$f" "$PROFILE_DIR/memories/$f"; echo "   seeded $f"
  else
    echo "   kept existing $f"
  fi
done

echo "== skills (project-hunter/*)"
mkdir -p "$PROFILE_DIR/skills/project-hunter"
cp -R "$SRC/skills/project-hunter/." "$PROFILE_DIR/skills/project-hunter/"

echo "== config: terminal cwd = repo, timeout 300 s, obsidian MCP server"
"$HERMES_BIN" -p "$PROFILE" config set terminal.cwd "$REPO_WIN" >/dev/null
"$HERMES_BIN" -p "$PROFILE" config set terminal.timeout 300 >/dev/null
# Same Obsidian MCP server the Claude runtime uses (.mcp.json): vault/ inside the repo.
#
# Pinned to an exact version, not a floating "@2" range (security review T3.15
# HIGH 3): `npx -y` installs and runs whatever that range resolves to on every
# profile boot, with no lockfile and no integrity pin — a `2.x` published from
# a compromised maintainer account (or a same-named package that is not the
# one this was audited against) would run with Everton's own OS rights,
# including `~/.ssh` (push to `main`, `ssh hunter-vps`) and the Hermes
# profile's `.env`. To bump after auditing the new release:
#   npm view obsidian-mcp version   # current published version
#   npm diff obsidian-mcp@<old> obsidian-mcp@<new>   # what changed, before trusting it
# then edit OBSIDIAN_MCP_VERSION below to the exact `major.minor.patch`.
OBSIDIAN_MCP_VERSION="2.0.1"
(cd "$REPO" && uv run python - "$PROFILE_DIR/config.yaml" "$REPO_WIN" "$OBSIDIAN_MCP_VERSION" <<'PY'
import sys
path, repo, mcp_version = sys.argv[1], sys.argv[2].replace("\\", "/"), sys.argv[3]
text = open(path, encoding="utf-8").read()
block = (
    "mcp_servers:\n  obsidian:\n    command: npx\n"
    f"    args: [\"-y\", \"obsidian-mcp@{mcp_version}\", \"serve\", \"--vault\", \"hunter={repo}/vault\"]\n"
)
if "mcp_servers:" in text:
    if "obsidian:" not in text:
        text = text.replace("mcp_servers:\n", block, 1)
else:
    text = text.rstrip("\n") + "\n" + block
open(path, "w", encoding="utf-8").write(text)
print("   mcp_servers.obsidian ok")
PY
)

if [ "${1:-}" = "--routine" ]; then
  echo "== routine: plantão every hour, inside the repo, delivered to the Bot chat"
  "$HERMES_BIN" -p "$PROFILE" cron create "every 1h" \
    "Você é a Sexta-feira de plantão no PROJECT HUNTER. Rode a skill sexta-feira-plantao do começo ao fim e termine com a tabela feito / rodando / bloqueado / precisa de você." \
    --name "[bot:$PROFILE] plantão" --workdir "$REPO_WIN" --skill sexta-feira-plantao --deliver "bot-chat:$PROFILE"
fi

echo
"$HERMES_BIN" profile show "$PROFILE" 2>/dev/null || true
echo "done. Bots tab in Hermes Desktop: the profile IS the Bot. Pin its model there (Edit Profile) if you want one different from the default."
