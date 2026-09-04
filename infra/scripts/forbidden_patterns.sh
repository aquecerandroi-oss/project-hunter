#!/usr/bin/env bash
# Forbidden-patterns gate (CLAUDE.md, docs/DEPLOYMENT.md §4 item 10).
#
# Scans tracked files for patterns that must never reach the default branch:
# sqlite, ad-hoc JSON/file state writes, print()/console.* in production code,
# localhost outside dev/test config, and the live-trading kill switch flipped
# to true. Prints "file:line: pattern" per hit and exits 1 if anything hit.
#
# Usage:
#   bash infra/scripts/forbidden_patterns.sh              # scan git-tracked files
#   bash infra/scripts/forbidden_patterns.sh --self-test   # exercise every pattern
#
# This is a detector, not a fixer, and it does not judge intent: a
# json.dump()/writeFileSync() hit is reported for a human reviewer to decide
# (it might be a legitimate export, not forbidden local state) — see
# CLAUDE.md "No local state".

set -euo pipefail

SCRIPT_PATH="infra/scripts/forbidden_patterns.sh"
HITS=0

# ---------------------------------------------------------------------------
# Path exclusions (apply to the tracked-file scan only; --self-test bypasses
# git entirely and scans the temp files it creates directly).
# ---------------------------------------------------------------------------
is_excluded_path() {
  case "$1" in
    docs/*) return 0 ;;
    tests/*|*/tests/*) return 0 ;;
    .claude/*) return 0 ;;
    *.md) return 0 ;;
    *.lock) return 0 ;;
    .github/*) return 0 ;;
    "$SCRIPT_PATH") return 0 ;;
  esac
  return 1
}

# ---------------------------------------------------------------------------
# report <file> <label> <grep-pattern> [-i]
# Emits one "file:line: label" line per match and bumps HITS.
# ---------------------------------------------------------------------------
report() {
  file="$1"
  label="$2"
  pattern="$3"
  ci_flag="${4:-}"
  grep_flags="-nE"
  [ "$ci_flag" = "-i" ] && grep_flags="-niE"

  # grep exits 1 on no-match; that's not a script error here.
  matches="$(grep $grep_flags -- "$pattern" "$file" 2>/dev/null || true)"
  [ -z "$matches" ] && return 0

  while IFS= read -r line; do
    [ -z "$line" ] && continue
    ln="${line%%:*}"
    printf '%s:%s: %s\n' "$file" "$ln" "$label"
    HITS=$((HITS + 1))
  done <<EOF
$matches
EOF
}

# path_contains_any <path> <word> [<word> ...] — substring match, case-sensitive,
# against the whole path (used for the localhost dev/test/example/compose/config
# exemption, which is deliberately substring-based: "packages/config" and
# "apps/web/lib/dev-utils.ts" both count).
path_contains_any() {
  path="$1"
  shift
  for word in "$@"; do
    case "$path" in
      *"$word"*) return 0 ;;
    esac
  done
  return 1
}

# ---------------------------------------------------------------------------
# scan_file <path> — applies every pattern's own file-type / path exemption.
# Shared by the real scan and --self-test so both exercise identical logic.
# ---------------------------------------------------------------------------
scan_file() {
  f="$1"

  case "$f" in
    *.py|*.ts|*.tsx|*.toml|*.yml)
      report "$f" "sqlite" 'sqlite' -i
      ;;
  esac

  case "$f" in
    infra/scripts/*) : ;; # allowlisted — scripts legitimately write files
    *.py)
      report "$f" "json.dump(" 'json\.dump\('
      ;;
  esac
  case "$f" in
    infra/scripts/*) : ;;
    *.ts|*.tsx)
      report "$f" "writeFileSync(" 'writeFileSync\('
      ;;
  esac

  case "$f" in
    infra/scripts/*) : ;;
    *.py)
      report "$f" "print(" 'print\('
      ;;
  esac

  case "$f" in
    */lib/logger.ts|lib/logger.ts) : ;;
    */instrumentation*.ts|instrumentation*.ts) : ;;
    *.config.*) : ;;
    */eslint/*|eslint/*) : ;;
    *.ts|*.tsx)
      report "$f" "console." 'console\.'
      ;;
  esac

  case "$f" in
    *.py|*.ts|*.tsx)
      if ! path_contains_any "$f" test dev example compose config; then
        report "$f" "localhost" 'localhost'
      fi
      ;;
  esac

  report "$f" "ENABLE_LIVE_TRADING=true" 'ENABLE_LIVE_TRADING[[:space:]]*=[[:space:]]*true' -i
}

# ---------------------------------------------------------------------------
# --self-test: build one fixture per pattern (plus one clean fixture) in a
# temp dir, assert each fixture hits exactly its own pattern, and assert the
# clean fixture hits nothing.
# ---------------------------------------------------------------------------
run_self_test() {
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT

  failures=0

  assert_hit() {
    fixture="$1"
    label="$2"
    HITS=0
    out="$(scan_file "$fixture")"
    if printf '%s\n' "$out" | grep -qF ": $label"; then
      echo "ok    - $label detected in $fixture"
    else
      echo "FAIL  - $label NOT detected in $fixture"
      failures=$((failures + 1))
    fi
  }

  printf 'import sqlite3\n' > "$tmp/db_thing.py"
  assert_hit "$tmp/db_thing.py" "sqlite"

  printf 'def save(data):\n    json.dump(data, open("state.json", "w"))\n' > "$tmp/exporter.py"
  assert_hit "$tmp/exporter.py" "json.dump("

  printf 'export function save(data: string) {\n  writeFileSync("state.json", data);\n}\n' > "$tmp/exporter.ts"
  assert_hit "$tmp/exporter.ts" "writeFileSync("

  printf 'def handler():\n    print("debug")\n' > "$tmp/handler.py"
  assert_hit "$tmp/handler.py" "print("

  printf 'export function onClick() {\n  console.log("clicked");\n}\n' > "$tmp/button.ts"
  assert_hit "$tmp/button.ts" "console."

  printf 'BASE_URL = "http://localhost:8000"\n' > "$tmp/settings_module.py"
  assert_hit "$tmp/settings_module.py" "localhost"

  printf 'ENABLE_LIVE_TRADING=true\n' > "$tmp/flags.py"
  assert_hit "$tmp/flags.py" "ENABLE_LIVE_TRADING=true"

  printf 'def add(a, b):\n    return a + b\n' > "$tmp/clean.py"
  HITS=0
  out="$(scan_file "$tmp/clean.py")"
  if [ -z "$out" ]; then
    echo "ok    - clean fixture has no hits"
  else
    echo "FAIL  - clean fixture unexpectedly hit:"
    printf '%s\n' "$out"
    failures=$((failures + 1))
  fi

  if [ "$failures" -eq 0 ]; then
    echo "self-test: all patterns detected, clean file passes"
    return 0
  else
    echo "self-test: $failures failure(s)"
    return 1
  fi
}

main() {
  if [ "${1:-}" = "--self-test" ]; then
    run_self_test
    exit $?
  fi

  files="$(git ls-files)"
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    is_excluded_path "$f" && continue
    [ -f "$f" ] || continue
    scan_file "$f"
  done <<EOF
$files
EOF

  if [ "$HITS" -gt 0 ]; then
    echo "forbidden-patterns: $HITS hit(s)"
    exit 1
  fi
  echo "forbidden-patterns: clean"
  exit 0
}

main "$@"
