# Brief T3.41 — fim do dia no Obsidian: session_orb avaliada, variantes do momentum, estresse, aposentadorias, Changelog

**Dona:** sexta-feira. **Não commitar.** **Regra operacional: nunca shell em background; comandos em primeiro plano ≤ 5 min; árvore compartilhada — nunca `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a` (git-guard bloqueia); não tocar `.env*`.** Só `obsidian/**`. Base: `main` em `1926e53`.

## Fontes
`.claude/state/notes-T3.33g.md` + `exp-drafts/EXP-0010-*.md` (session_orb: 20 decisões, −0,19 R líquida, sessões indistinguíveis, inconclusivo tendendo a descartar; ativada 19:42:56Z; concerns: rótulo `us` nas 6 h mortas, digest de fecho compartilhado muda entre commits). `.claude/state/notes-T3.40.md` + `exp-drafts/EXP-0012-*.md`, `EXP-0013-*.md` (momentum v5 = 0 decisões → aposentada; v6 alvos 3/6/9 → −0,05 R, PF 0,91, mantida; correção da identidade de custo: risco% = stop_atr × ATR%). `.claude/state/stress-mean-reversion-v1-2026-09-08.md` e `notes-T3.36.md` (passada de estresse: momentum v2 sem_vantagem_na_base; mean_reversion frágil a custos). `notes-T3.33f.md` (breakout v2: 8 decisões, −0,08 R; aposentada). Aposentadorias auditadas hoje: breakout v1 (19:35:34Z), breakout v2 (19:35:36Z), momentum v5 (19:39:00Z). `seed.py --only strategies` rodado (19:3xZ). Revisões: T3.38 (identidade inclui stop), T3.39 (trava de posições da linha paper olhava coluna nunca preenchida → T3.39b em voo). `git log --since='2026-09-08' --format='%h %s'` para o Changelog.

## Entregar
1. `EXP-0010`: avaliação datada (REPLAY), tabela de estresse com "amostra insuficiente", variantes recusadas, `result: inconclusivo`; `Registro de Tentativas` T-037 com início 19:42:56Z.
2. `EXP-0012` (momentum v5, teto de pedágio): arquivar como **descartada por construção** (0 decisões; o universo nunca passa de ATR% 1,76 %), aposentada 19:39Z; `EXP-0013` (momentum v6, alvo 3 ATR): avaliação pareada, `inconclusivo`, mantida; ambas no índice e no Registro (T-039/T-040, início = ativação 18:57:05Z / 19:04:56Z).
3. `EXP-0008`: aposentadorias v1/v2 datadas; `EXP-0009`: tabela de estresse da mean_reversion (frágil a custos, dependente de metade) na seção datada; `EXP-0006`/`KB-0076`: nota de rodapé da identidade de custo (risco% = stop_atr × ATR%; v4 ≈ 0,15 R, v5 ≤ 0,067 R).
4. `Strategy Backlog`: fechar B1 (breakout v2 testada e descartada), atualizar as próximas: mean_reversion variante por teto de pedágio (não stop/alvo), session_orb variante só se K3 não disparar, trendline_breakout (T3.34b) pendente de decisão de módulo, regime producer, patterns v2.
5. `09-OPERATIONS/Diario/2026-09-08.md`: bloco final do dia (deploys até 1926e53 com todos os serviços alinhados; o "placar" das quatro novas; o que o operador ainda tem: SQL da linhagem v4, SQL de reabertura de gaps, vínculo agents, backfill BTC, flag).
6. `08-CHANGELOG`: os commits de hoje (uma linha cada, do `git log`), dívida apontada pela T3.33h.
7. `Open Bugs`: abrir "trava de posições da linha paper via positions.agent_id nunca preenchido (T3.39b em voo)", "outside_session_window rotula as 6 h mortas como us", "deriva de imagem entre api e strategy-worker nos deploys parciais (corrigida hoje com compose.sh update; regra: alinhar sempre)".
8. `uv run python infra/scripts/obsidian_lint.py` verde.

## Provar
Relatório em português, formato estendido; `.claude/state/notes-T3.41.md`.
