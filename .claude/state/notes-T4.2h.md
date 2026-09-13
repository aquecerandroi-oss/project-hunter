# Notas T4.2h — a vigilância da conta do criador pela cadeia (13/09/2026, 02:1x–03:0x BRT, orquestrador; agentes no limite semanal)

**Por quê:** 22 das 35 apostas medidas de 12/09 saíram por `creator_dump` (−6,2 R), em média 14 min depois da entrada; a fita
por lote não traz vendas por carteira. Pedido do Everton: "então aprimore essa parte".

**Entregue (papel):**
- `services/meme-worker/hunter_meme_worker/creator_watch.py` (257 linhas): `ata_targets` (ATAs clássica e Token-2022 via
  `associated_token_address`), `parse_token_amounts` (`jsonParsed`), `balances_by_mint` (soma por mint; `None` = sem conta),
  `detect_drops` (só o decréscimo entre duas leituras é venda), `creator_watch_once` (um `getMultipleAccounts` por ≤ 100
  contas pelo `ctx.chain.call` — um `ChainSource` sem `call` faz o laço avisar uma vez e não fazer nada), marca
  `creator_sold_seen_at`/`creator_sold_fraction` nas apostas abertas do mint, `creator_balance_reason = creator_ata_missing`
  quando o criador não tem conta; estado em memória (um reinício começa cego e espera duas leituras);
  `spawn_creator_watch` (a tarefa `meme-creator-watch`, `MEME_CREATOR_WATCH_ENABLED`, `MEME_CREATOR_WATCH_CYCLE_S` ≥ 5, padrão 15).
- Migração `0036_meme_creator_watch` (`ddl/meme_creator_watch.py`): três colunas em `meme_paper_bets` + 3 CHECKs; downgrade
  recusa com venda vista. Modelo `MemePaperBet` com as colunas (o CHECK do rótulo fica só na migração — teto de 350 linhas).
- `lab_repo_bets._OPEN_BETS`: `creator_sold = CASE WHEN b.creator_sold_seen_at IS NOT NULL THEN true ELSE (fita do minuto) END`
  → `creator_dump` do motor de papel dispara na fotografia seguinte. Latência medível: `exit_at − creator_sold_seen_at`.
- Docs: `DATABASE.md` §48, plano §T4.2h, `RISK_ENGINE_MEME.md` §10.12.

**Provas (saídas reais):** `test_creator_watch.py` 5; worker unit **226**; core unit **1 332**; `test_migrations -k "0035 or 0036
or alembic_check or upgrade_head"` **6 passed (41 s)**; `test_lab_persistence` + `test_lab_operator_3` **16 passed (160 s)**;
ruff/format/pyright 0; `check_file_size` 0 acima (`meme_lab.py` 350, `main.py` 350).

**Prova na VPS após o deploy:** log `meme-creator-watch` sem `meme_loop_failed`; ao surgir aposta aberta, evento
`meme_creator_balance_dropped` quando o dev vender; `select count(*) from meme_paper_bets where creator_sold_seen_at is not null`.

**Fora (declarado):** `meme_live_positions` (executor real — mesma leitura no tique de saídas, T4.2h-b); heartbeat e rótulos
web `creator_watch_*`; teste de persistência do laço com um `FakeChain.call` (a marca é SQL simples coberta pela migração).
