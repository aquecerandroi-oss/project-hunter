SET statement_timeout='60s';
SELECT pr.origin||' | '||rs.name||'/'||rs.version||' | '||pr.decided_at||' | '||left(pr.reasons::text, 3000)
FROM meme_proposals pr JOIN meme_rule_sets rs ON rs.id=pr.rule_set_id
WHERE pr.mint IN ('4LnYYatTEqujJJSWCK125RVjxvYP7tvRe2puMnJBpump','61iCGwP3qDw6sbogg7nuLNNWj1epAhhrQ23qUrT9pump','J2q68X3PC3uZFY6ydDGuB1ztDsoawikkqe3yFX3Cpump')
  AND rs.name='operator' ORDER BY pr.decided_at;
