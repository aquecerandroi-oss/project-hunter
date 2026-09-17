# T4.47 — byte nulo no nome da moeda derruba o radar (17/09/2026 00:11:48Z)

Sintoma: `CharacterNotInRepertoireError: invalid byte sequence for encoding "UTF8": 0x00` no upsert de `meme_tokens`; 6 tentativas do mesmo quadro (00:11:48Z → 00:12:41Z); worker reiniciado 00:13:07Z (RestartCount 18).
Quadro: mint 71CeThH29G5SuXy6BrRP2RAeTULJdV8VUshFit9vpump, name "spaceX链游"+NUL, symbol SpaceX-Wor, fonte trenches_ws.
Correção: services/meme-worker/hunter_meme_worker/repo_rows.py — `clean_text` + `TokenRow.__post_init__` (frozen+slots → object.__setattr__). Teste: services/meme-worker/tests/test_repo_rows_nul.py (25 verdes com os vizinhos).
Commit d1b0b40d (pushed). Deploy: no pacote do Everton.
Pendente: outras linhas de texto vindas do upstream (meme_events? social REST em outra tabela?) — R45 lista as outras causas de queda.
