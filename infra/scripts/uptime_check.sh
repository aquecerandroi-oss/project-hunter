#!/usr/bin/env bash
# Sonda externa de disponibilidade da VPS (docs/DEPLOYMENT.md, "Alarme externo de disponibilidade").
#
# Roda no GitHub Actions (.github/workflows/uptime.yml) e na mao, contra a borda
# publica (Caddy). Nao usa segredo nenhum e so le: dois GETs.
#
#   1. site : GET /                      -> 200..399 (a raiz responde 307 para /sign-in; 5xx/000 = Caddy ou web fora)
#   2. api  : GET /api/v1/system/info    -> 200 com "git_sha" no corpo (unica rota publica da api atras do Caddy;
#                                           /health e /ready NAO sao expostos de proposito, ver infra/vps/Caddyfile)
#
# Ainda NAO existe checagem de frescor dos dados (ultimo candle / ultimo commit do scanner): nenhum
# endpoint publico traz esse carimbo. Nao inventamos um aqui; ver a secao do DEPLOYMENT.md.
#
# TLS: a borda usa o IP com certificado da CA interna do Caddy (`tls internal`), que nenhum sistema
# confia -> `curl -k`. Aceitavel porque a sonda so mede disponibilidade, nao envia nada sensivel, e o
# corpo da api e conferido; com dominio + Let's Encrypt, remover o -k (CURL_TLS_ARGS="").
#
# Variaveis (todas opcionais):
#   UPTIME_BASE_URL   padrao https://169.58.116.99
#   UPTIME_ATTEMPTS   padrao 3
#   UPTIME_BACKOFF    segundos entre tentativas, separados por espaco; padrao "30 60"
#   UPTIME_REPORT     arquivo onde escrever o resumo em Markdown (padrao: nenhum)
#   CURL_TLS_ARGS     padrao "-k"
#
# Saida: 0 = tudo ok em alguma tentativa; 1 = falhou nas tres.

set -uo pipefail

BASE_URL="${UPTIME_BASE_URL:-https://169.58.116.99}"
ATTEMPTS="${UPTIME_ATTEMPTS:-3}"
read -r -a BACKOFF <<<"${UPTIME_BACKOFF:-30 60}"
REPORT="${UPTIME_REPORT:-}"
read -r -a TLS_ARGS <<<"${CURL_TLS_ARGS--k}"

now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# probe <url> -> escreve o corpo em $BODY e devolve o codigo HTTP em $CODE (000 = sem resposta)
probe() {
  CODE="$(curl -sS "${TLS_ARGS[@]}" --connect-timeout 10 --max-time 20 \
    -o "$BODY" -w '%{http_code}' "$1" 2>"$BODY.err")" || CODE="000"
}

FAILURES=()

check_site() {
  probe "$BASE_URL/"
  if [ "$CODE" -ge 200 ] && [ "$CODE" -le 399 ]; then
    echo "  ok   site  GET / -> $CODE"
  else
    FAILURES+=("site: GET / -> HTTP $CODE (esperado 200-399)$(err_suffix)")
  fi
}

check_api() {
  probe "$BASE_URL/api/v1/system/info"
  if [ "$CODE" = "200" ] && grep -q '"environment"' "$BODY" && grep -q '"git_sha"' "$BODY"; then
    echo "  ok   api   GET /api/v1/system/info -> 200 ($(grep -o '"git_sha":"[^"]*"' "$BODY"))"
  else
    FAILURES+=("api: GET /api/v1/system/info -> HTTP $CODE (esperado 200 com git_sha)$(err_suffix)")
  fi
}

err_suffix() {
  [ "$CODE" = "000" ] && [ -s "$BODY.err" ] && printf ' [%s]' "$(head -c 200 "$BODY.err" | tr '\n' ' ')"
  return 0
}

BODY="$(mktemp)"
trap 'rm -f "$BODY" "$BODY.err"' EXIT

attempt=1
while :; do
  echo "$(now) tentativa $attempt/$ATTEMPTS em $BASE_URL"
  FAILURES=()
  check_site
  check_api
  if [ "${#FAILURES[@]}" -eq 0 ]; then
    [ -n "$REPORT" ] && printf 'Todas as checagens passaram (tentativa %s/%s) em %s.\n' "$attempt" "$ATTEMPTS" "$(now)" >"$REPORT"
    echo "$(now) OK"
    exit 0
  fi
  for f in "${FAILURES[@]}"; do echo "  FAIL $f"; done
  [ "$attempt" -ge "$ATTEMPTS" ] && break
  wait_s="${BACKOFF[$((attempt - 1))]:-${BACKOFF[${#BACKOFF[@]} - 1]}}"
  echo "  nova tentativa em ${wait_s}s"
  sleep "$wait_s"
  attempt=$((attempt + 1))
done

if [ -n "$REPORT" ]; then
  {
    printf 'Falhou em %s tentativas seguidas (ultima em %s UTC), alvo `%s`:\n\n' "$ATTEMPTS" "$(now)" "$BASE_URL"
    for f in "${FAILURES[@]}"; do printf -- '- %s\n' "$f"; done
  } >"$REPORT"
fi
echo "$(now) FALHOU apos $ATTEMPTS tentativas"
exit 1
