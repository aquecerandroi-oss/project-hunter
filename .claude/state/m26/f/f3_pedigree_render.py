"""EXP-M26 F — 3/3: o custo da leitura de pedigree do minuto que volta com C/L/H ativos (DATABASE §69).

Renderiza ``lab_repo_fast._PEDIGREE`` com os parâmetros de ``pedigree_for`` e os mints de um minuto
fechado de ``meme_features_1m`` (subconsulta), para cronometrar com ``\timing`` numa sessão só de
leitura. O worker corta essa leitura em 8 s (``SET LOCAL statement_timeout = 8000``).
"""

from hunter_meme_worker import lab_repo_fast as m
from hunter_meme_worker.lab_opportunities import MATURE_CHART_RULE_SET_IDS

sql = str(m._PEDIGREE.text)  # noqa: SLF001
lit = {
    ":creator_window_s": "3600", ":symbol_window_s": "86400", ":prior_window_s": str(m.PRIOR_WINDOW_S),
    ":probe_rule_set_id": f"'{m.PROBE_RULE_SET_ID}'::uuid",
    ":pullback_rule_set_id": f"'{m.PULLBACK_ARM_RULE_SET_ID}'::uuid",
    ":pullback_control_rule_set_id": f"'{m.PULLBACK_CONTROL_RULE_SET_ID}'::uuid",
    "CAST(:mature_rule_set_ids AS uuid[])": "ARRAY[" + ",".join(f"'{i}'" for i in MATURE_CHART_RULE_SET_IDS) + "]::uuid[]",
}
for k, v in lit.items():
    sql = sql.replace(k, v)
import sys
lo, hi = (int(a) for a in sys.argv[1:3]) if len(sys.argv) > 2 else (2, 14)
for offset in range(lo, hi):
    mints = (f"ARRAY(SELECT mint FROM meme_features_1m WHERE features_version = 'meme_features_v3' "
             f"AND end_time = date_trunc('minute', now()) - interval '{offset} minutes')")
    print(f"SELECT count(*) AS mints_do_minuto FROM unnest({mints});")
    print(f"SELECT count(*) AS lidos, sum(COALESCE(creator_prior_mints_1h,0) + COALESCE(symbol_dup_24h,0) + COALESCE(creator_prior_dump_count,0) + COALESCE(creator_prior_dead_count,0)) AS soma, count(*) FILTER (WHERE creator_prior_mints_1h IS NULL OR symbol_dup_24h IS NULL) AS desconhecidos FROM ({sql.replace(':mints', mints)}) q;")
