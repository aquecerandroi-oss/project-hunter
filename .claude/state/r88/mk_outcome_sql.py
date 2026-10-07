import csv
from pathlib import Path
here = Path(__file__).resolve().parent
ids = sorted({r["bet_id"] for r in csv.DictReader(open(here / "cache" / "eligible.csv", encoding="utf-8"))})
arr = ",".join(f"'{i}'" for i in ids)
sql = f"""-- R88 passo 3c — DESFECHOS das apostas da lista congelada (eligible.csv sha256 18dcd185…), lidos depois do congelamento
BEGIN READ ONLY;
SET LOCAL statement_timeout='600s';
COPY (
SELECT b.id AS bet_id, b.status, b.exit_at, b.pnl_sol::text AS pnl_sol, b.entry->>'sol_spent' AS sol_spent,
       COALESCE(b.exit->>'reason', b.exit_intent->>'reason') AS exit_reason, b.outcome_quality,
       b.entry->>'fee_pct' AS fee_pct, b.r_multiple::text AS r_multiple, now() AS read_at
FROM meme_paper_bets b WHERE b.id = ANY(ARRAY[{arr}]::uuid[])
ORDER BY b.id
) TO STDOUT WITH (FORMAT csv, HEADER);
COMMIT;
"""
(here / "q_outcomes.sql").write_text(sql, encoding="utf-8")
print(len(ids))
