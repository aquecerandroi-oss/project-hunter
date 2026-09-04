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
#
# .github/** is deliberately NOT excluded here: workflow files must still be
# scanned for "sqlite" and the live-trading kill switch. Only the "localhost"
# pattern exempts .github/** (see is_localhost_exempt below) — workflows
# routinely reference service containers by localhost.
# ---------------------------------------------------------------------------
is_excluded_path() {
  case "$1" in
    docs/*) return 0 ;;
    tests/*|*/tests/*) return 0 ;;
    .claude/*) return 0 ;;
    *.md) return 0 ;;
    *.lock) return 0 ;;
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

# is_localhost_exempt <path> — path-SEGMENT matching for the "localhost"
# exemption (dev/test/example/compose/config code legitimately hardcodes
# localhost). Deliberately not a substring word list: "configurator.py" must
# not be exempted just because it contains "config", and "backtest/" must
# not be exempted just because it contains "test". Wrapping the path in "/"
# on both ends turns "does this path have a *segment* equal to X" into a
# plain substring check for "/X/", without needing to split on "/".
is_localhost_exempt() {
  path="$1"
  base="${path##*/}"

  case "/$path/" in
    */tests/*|*/test/*|*/dev/*) return 0 ;;
  esac
  case "$base" in
    test_*|conftest*) return 0 ;;
  esac
  case "$path" in
    *packages/config/*|*docker-compose*|*.example*) return 0 ;;
    # Dev-only defaults; production fails fast without real URLs (the
    # WEB_ORIGIN/API_URL prod guard is added in a separate fix). A single
    # named-file exemption, not a directory rule.
    packages/core/hunter_core/settings.py) return 0 ;;
  esac
  return 1
}

# ---------------------------------------------------------------------------
# scan_file <path> — applies every pattern's own file-type / path exemption.
# Shared by the real scan and --self-test so both exercise identical logic.
# ---------------------------------------------------------------------------
scan_file() {
  f="$1"

  # Extension-independent: sqlite/live-trading references are forbidden no
  # matter what kind of file they show up in (Dockerfile, alembic.ini, a CI
  # yaml step, ...), not just recognized source-code extensions.
  report "$f" "sqlite" 'sqlite' -i

  case "$f" in
    infra/scripts/*) : ;; # allowlisted — scripts legitimately write files
    *.py|*.ts|*.tsx|*.yaml|*.yml|*.ini|*.cfg|*Dockerfile*)
      report "$f" "json.dump(" 'json\.dump\('
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
    */smoke.mjs|smoke.mjs) : ;;
    */verify.mjs|verify.mjs) : ;;
    *.ts|*.tsx|*.js|*.jsx|*.mjs|*.cjs)
      report "$f" "console." 'console\.'
      ;;
  esac

  case "$f" in
    *.py|*.ts|*.tsx)
      if ! is_localhost_exempt "$f"; then
        report "$f" "localhost" 'localhost'
      fi
      ;;
  esac

  report "$f" "ENABLE_LIVE_TRADING=true" 'ENABLE_LIVE_TRADING[[:space:]]*=[[:space:]]*true' -i
}

# ---------------------------------------------------------------------------
# --self-test: build one fixture per pattern (plus a clean fixture) and one
# negative fixture per exemption in a temp dir, cd'd into so fixture paths
# can use the same repo-relative shape (packages/config/x.py, tests/test_x.py,
# ...) that path-segment matching actually keys off. Asserts each positive
# fixture hits exactly its own pattern and each negative fixture hits nothing.
# ---------------------------------------------------------------------------
run_self_test() {
  orig_dir="$PWD"
  tmp="$(mktemp -d)"
  trap 'cd "$orig_dir" 2>/dev/null; rm -rf "$tmp"' EXIT
  cd "$tmp"

  failures=0

  # check_path <path> — mirrors main()'s real per-file logic: is_excluded_path
  # first, scan_file only if it wasn't excluded. Fixtures that rely on the
  # tests/*-style blanket exclusion (rather than a scan_file-level exemption)
  # need this to actually exercise that path.
  check_path() {
    p="$1"
    if is_excluded_path "$p"; then
      printf ''
    else
      scan_file "$p"
    fi
  }

  assert_hit() {
    path="$1"
    label="$2"
    out="$(check_path "$path")"
    # scan_file runs inside this command substitution's own subshell, so a
    # reset-and-reread of the global $HITS here would never see its
    # increments (that was the previous, no-op "HITS=0" — dead code that
    # asserted nothing). Count hits from $out itself instead: that's what
    # actually lets us assert "exactly its own pattern, nothing else".
    hit_count="$(printf '%s\n' "$out" | grep -c . || true)"
    if printf '%s\n' "$out" | grep -qF ": $label"; then
      if [ "$hit_count" -eq 1 ]; then
        echo "ok    - $label detected in $path (exactly one hit)"
      else
        echo "ok    - $label detected in $path (note: $hit_count total hits)"
      fi
    else
      echo "FAIL  - $label NOT detected in $path"
      failures=$((failures + 1))
    fi
  }

  assert_no_hit() {
    path="$1"
    out="$(check_path "$path")"
    if [ -z "$out" ]; then
      echo "ok    - no hit for $path"
    else
      echo "FAIL  - unexpected hit(s) for $path:"
      printf '%s\n' "$out"
      failures=$((failures + 1))
    fi
  }

  # --- one positive fixture per pattern ---
  printf 'import sqlite3\n' > db_thing.py
  assert_hit "db_thing.py" "sqlite"

  printf 'def save(data):\n    json.dump(data, open("state.json", "w"))\n' > exporter.py
  assert_hit "exporter.py" "json.dump("

  printf 'export function save(data: string) {\n  writeFileSync("state.json", data);\n}\n' > exporter.ts
  assert_hit "exporter.ts" "writeFileSync("

  printf 'def handler():\n    print("debug")\n' > handler.py
  assert_hit "handler.py" "print("

  printf 'export function onClick() {\n  console.log("clicked");\n}\n' > button.ts
  assert_hit "button.ts" "console."

  printf 'BASE_URL = "http://localhost:8000"\n' > settings_module.py
  assert_hit "settings_module.py" "localhost"

  printf 'ENABLE_LIVE_TRADING=true\n' > flags.py
  assert_hit "flags.py" "ENABLE_LIVE_TRADING=true"

  printf 'def add(a, b):\n    return a + b\n' > clean.py
  assert_no_hit "clean.py"

  # --- negative fixtures: path-segment exemptions must not be substring traps ---
  printf 'BASE_URL = "http://localhost:8000"\n' > configurator.py
  assert_hit "configurator.py" "localhost"      # "config" substring, not the packages/config/ segment

  mkdir -p backtest
  printf 'BASE_URL = "http://localhost:8000"\n' > backtest/engine.py
  assert_hit "backtest/engine.py" "localhost"   # "test" substring, not the tests/ segment

  mkdir -p packages/config
  printf 'BASE_URL = "http://localhost:8000"\n' > packages/config/x.py
  assert_no_hit "packages/config/x.py"

  mkdir -p tests
  printf 'def handler():\n    print("debug")\n' > tests/test_x.py
  assert_no_hit "tests/test_x.py"

  printf '[alembic]\nsqlalchemy.url = sqlite:///local.db\n' > alembic.ini
  assert_hit "alembic.ini" "sqlite"             # extension-independent

  printf 'console.log("hi");\n' > foo.mjs
  assert_hit "foo.mjs" "console."               # widened console. extensions

  mkdir -p eslint
  printf 'console.log("hi");\n' > eslint/smoke.mjs
  assert_no_hit "eslint/smoke.mjs"

  printf 'console.log("hi");\n' > smoke.mjs
  assert_no_hit "smoke.mjs"                     # **/smoke.mjs exemption, outside eslint/ too

  if [ "$failures" -eq 0 ]; then
    echo "self-test: all patterns detected, clean/exempt fixtures pass"
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

  # -z / -d '' so filenames with spaces, newlines or non-ASCII bytes round-trip.
  while IFS= read -r -d '' f; do
    [ -z "$f" ] && continue
    is_excluded_path "$f" && continue
    [ -f "$f" ] || continue
    scan_file "$f"
  done < <(git ls-files -z)

  if [ "$HITS" -gt 0 ]; then
    echo "forbidden-patterns: $HITS hit(s)"
    exit 1
  fi
  echo "forbidden-patterns: clean"
  exit 0
}

main "$@"
