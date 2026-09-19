---
tags: [trading, meme, pumpfun, mesa-real, operator, m19, t4-71]
status: vivo
owner: sexta-feira
updated: 2026-09-19
---

# Mesa `operator/6` — a segunda mesa real (entrada do `flow_v2/1`, saída do Everton)

**Decisão** ([[06-DECISIONS/2026-09-12-teste-pequeno-meme-real|adendo de 19/09 09:5x BRT]]): "vi que o Lab está
dando bom, vamos operar com dinheiro real também". Em 72 h de papel o `flow_v2/1` (EXP-M5, a porta E1 original)
rendeu **+0,054 SOL** (+0,103 nas últimas 24 h, 38 apostas, 45 % de acerto) enquanto a mesa `operator/5` rendeu
**−0,070**. A resposta não é trocar a mesa: é abrir uma **segunda** ao lado, para comparar real × real e real × papel.
Semente `0055_meme_operator6_desk` (T4.71, `docs/DATABASE.md` §62). Expectativa honesta registrada na decisão:
**−0,02 a +0,05 SOL em 3 dias**.

## 1. O que é

`operator/6` = **entrada do `flow_v2/1`** (como o seed da migração `0030` a congelou — nunca a linha viva, que
`--set-param` pode ter editado) **+ saída do Everton + tamanho da mesa**. `kind = operator`, sem `exp_ref`, relógio
de 15 s, ativo. Nada foi aposentado: `operator/5` continua ativo.

| Bloco | Chave | `operator/6` | `operator/5` | `flow_v2/1` |
|---|---|---|---|---|
| Porta | `gate_key/gate_version` | `fluxo_e_holders/1` | `fluxo_e_holders/2` (braço 2) | `fluxo_e_holders/1` |
| Porta | idade | 30–300 s | 30–300 s | 30–300 s |
| Porta | progresso | ≥ 5 % e subindo | ≥ 5 % e subindo **ou mcap subindo** | ≥ 5 % e subindo |
| Porta | fluxo | positivo; ≥ 10 compradores; vendas/compras ≤ 0,6; holders subindo | idem, mas holders **subindo ou estável**; `min_holders 20` | idem |
| Porta | snipers | ≤ **2** | ≤ **10** | ≤ 2 |
| Porta | dev | `dev_share ≤ 0,10`, desconhecido recusa; criador não vendedor líquido | idem + `creator_unknown_allowed_if_dev_measured` | idem |
| Pedigree | exclusões / reincidência | sim / **sim** | sim / sim | sim / não |
| Saída | `target_x` | **1,15×** | 1,15× (editado à mão em 19/09 02:10) | 3× |
| Saída | `trailing_pct` / `trailing_arm_x` | **10 % / null** (armado desde a entrada) | 10 % / "1.0" (lido como null) | 35 % / 1,5× |
| Saída | `max_hold_s` | **300 s** | 300 s | 1 800 s |
| Saída | `max_loss_pct` / linha | 50 % / `exit_on_line_break` | 50 % / idem | 50 % / idem |
| Tamanho | `size_sol` = `max_sol_per_bet` = exposição/mint | **0,07** | 0,07 (VPS; seed 0,05) | 0,05 |
| Tamanho | `max_open_positions` / `ttl_s` | 2 / 180 s | 2 / 180 s | 5 / laço |

Os valores de `operator/5` na coluna acima são os **da VPS** (editados por `meme_rule_set.py --set-param`,
[[03-TRADING/Meme/Estudo-2026-09-16-a-porta-real-versus-a-replica|R27]]); conferir com
`uv run python infra/scripts/meme_rule_set.py --history operator/5` antes de citar. Os de `operator/6` e `flow_v2/1`
são os do seed (o teste `test_migration_0055` prova que `operator/6 − 12 chaves da mesa = flow_v2/1 − as mesmas 12`,
byte a byte).

## 2. Um freio só para as duas mesas

O executor abre proposta de **qualquer** conjunto `operator` ativo (`auto_approve._OPERATOR_PROPOSED`: `kind =
'operator' AND status = 'active'`, sem nome nem versão). Mas `MEME_MAX_OPEN_POSITIONS` (2) e
`MEME_DAILY_LOSS_CAP_SOL` (0,15) são contados pelo motor sobre **todas** as posições reais e sobre a perda do dia
da carteira — o `max_open_positions: 2` do `params` é o teto do laço de **papel**. Kill switch, tesouraria e teto por
operação também são um só (`docs/RISK_ENGINE_MEME.md` §3). Na prática as duas mesas **competem** pelas mesmas duas
vagas: quando as duas propõem a mesma moeda no mesmo tique, a primeira admitida ocupa a vaga e a outra recusa
`duplicate_position`/`max_open_positions` — isso é esperado, não defeito, e conta no balanço.

**Consequência declarada:** a compra **manual** da mesa (`POST …/proposals/manual`) passa a ser arquivada sob a maior
versão ativa, `operator/6` (teto 0,07). Aposentar uma das duas é `meme_rule_set.py --deprecate operator/N --reason …
--apply`; a outra fica.

## 3. Como comparar (3 dias, a partir do deploy)

1. **Real × real** — `infra/scripts/meme_close_day.py` (fechamento diário) e o diário
   ([[09-OPERATIONS/Diario-Meme/README|Diário Meme]]) já quebram por conjunto: ler `operator/5` e `operator/6` lado a
   lado em ordens confirmadas, PnL SOL, R médio, motivo de saída (`target`/`trailing`/`time_stop`/`creator_dump`),
   recusas da admissão por nome. SQL direto: `meme_live_positions JOIN meme_proposals JOIN meme_rule_sets`, por
   `name/version` e dia em Brasília.
2. **Real × papel** — a proposta do `operator/6` é preenchida **em sombra** pelo laço de papel (mesma linha
   `meme_proposals`, `meme_paper_bets` com `rule_set_id` do `operator/6`), e o `flow_v2/1` propõe a mesma moeda no
   mesmo tique (`test_lab_operator_3` é o precedente): a diferença `operator/6` real − `operator/6` papel é o custo de
   execução (latência, taxas, admissão); `operator/6` papel − `flow_v2/1` papel é o custo da **saída** (1,15×/10 %/5 min
   contra 3×/35 %/30 min) sobre a mesma entrada. Vista `meme_lab_scoreboard_v1` por `rule_set_id` × dia.
3. **Régua** — a de [[06-DECISIONS/2026-09-10-validacao-em-um-dia-e-lucro-real|validação em um dia]]: n, blocos de
   hora, IC 95 %; nada vira "a mesa" sem número. Paradas de qualidade da Astra continuam valendo para a carteira
   inteira (perda do dia ≥ 0,12; 3 rugs seguidos), não por mesa.

## 4. O que ler no primeiro dia

- `auto_skipped`/`auto_refused_last_hour` no heartbeat do executor: quanto do `operator/6` morre em
  `mint_busy`/`max_open_positions` por causa do `operator/5` (e vice-versa).
- A fração de propostas do `operator/6` recusadas por `token_too_old`/`progress_above_window` — a porta E1 v1 é mais
  estreita (2 snipers) e a admissão real ainda tem a janela própria de progresso (2–50 %).
- Se a mesa manual for usada, a ficha da compra deve dizer que foi sob `operator/6`.

Relacionados: [[03-TRADING/Meme/Balanco-2026-09-18-estagio-1b|balanço de 18/09]],
[[05-EXPERIMENTS/EXP-M5-fluxo-e-holders|EXP-M5]], [[11-KNOWLEDGE/README-meme|conhecimento meme]].
