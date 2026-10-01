"""EXP-M26 F — conserto da leitura de pedigree: antes (``_PEDIGREE``) x depois (``_PEDIGREE_COUNTS``).

Renderiza as duas consultas de ``hunter_meme_worker.lab_repo_pedigree`` com os parâmetros de
``pedigree_params`` e os mints de UM minuto fechado fixo (argumento 1, literal de timestamp), para
EXPLAIN (ANALYZE, BUFFERS) e ``\\timing`` numa sessão só de leitura (``q.sh``). Uso:
``uv run --no-sync python f5_pedigree_after.py "2026-10-01 03:25:00+00" explain|time N``.
"""

import sys

from hunter_indicators.meme.pedigree import PEDIGREE_V1
from hunter_meme_worker import lab_repo_pedigree as m

minute, mode = sys.argv[1], sys.argv[2]
rounds = int(sys.argv[3]) if len(sys.argv) > 3 else 1
mints = (
    "ARRAY(SELECT mint FROM meme_features_1m WHERE features_version = 'meme_features_v3' "
    f"AND end_time = TIMESTAMPTZ '{minute}')"
)


def render(statement: object, *, full: bool) -> str:
    sql = str(statement.text)  # type: ignore[attr-defined]
    for key, value in m.pedigree_params(["x"], PEDIGREE_V1, full=full).items():
        if key == "mints":
            continue
        lit = (
            "ARRAY[" + ",".join(f"'{i}'" for i in value) + "]::uuid[]"
            if key == "mature_rule_set_ids"
            else f"'{value}'::uuid"
            if key.endswith("rule_set_id")
            else str(value)
        )
        sql = sql.replace(f"CAST(:{key} AS uuid[])", lit).replace(f":{key}", lit)
    return sql.replace(":mints", mints)


full_sql, light_sql = render(m._PEDIGREE, full=True), render(m._PEDIGREE_COUNTS, full=False)  # noqa: SLF001
print("\\timing on")
if mode == "explain":
    print(f"SELECT count(*) AS mints_do_minuto FROM unnest({mints});")
    for label, sql in (("ANTES (_PEDIGREE, leitura completa)", full_sql), ("DEPOIS (_PEDIGREE_COUNTS, so as duas contagens)", light_sql)):
        print(f"\\echo ===== {label}")
        print(f"EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, SUMMARY ON) {sql};")
else:
    # O externo lê TODAS as colunas que a consulta devolve: o Postgres poda de uma subconsulta as colunas
    # que ninguém referencia, e sem isso o "antes" não executaria as contagens pesadas.
    for _ in range(rounds):
        for label, sql, extra in (
            ("antes", full_sql, ", sum(COALESCE(creator_prior_dump_count,0)) AS s_dump, sum(COALESCE(creator_prior_dead_count,0)) AS s_dead"),
            ("depois", light_sql, ""),
        ):
            print(f"\\echo {label}")
            print(
                "SELECT count(*) AS lidos, sum(COALESCE(creator_prior_mints_1h,0)) AS s1h, "
                "sum(COALESCE(symbol_dup_24h,0)) AS s24h, count(*) FILTER (WHERE creator_prior_mints_1h IS NULL "
                f"OR symbol_dup_24h IS NULL) AS desconhecidos{extra} FROM ({sql}) q;"
            )
