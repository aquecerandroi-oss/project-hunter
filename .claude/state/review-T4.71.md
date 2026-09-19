# Revisão de risco — T4.71 / commit 7850a89c (migração 0055, `operator/6`)

Revisor: guardião do risk-engine · 2026-09-19 · só leitura, sem edição, sem commit.
Escopo lido: `infra/migrations/ddl/meme_operator_6.py`, `infra/migrations/versions/0055_meme_operator6_desk.py`,
executor (`auto_approve.py`, `entries.py`, `admission.py`, `repo_positions.py`, `exit_common.py`), risk-core
(`checks_wallet.py`, `sizing.py`, `limits.py`, `exits.py`, `inputs.py`), worker (`lab_repo.py`, `lab_fast.py`,
`proposals.py`, `lab_params.py`, `lab_gate_params.py`, `event_gate_eval.py`, `repo_tape.py`),
API (`repositories/meme_desk.py`). Teste 0055: confiei na execução registrada em
`.claude/state/notes-T4.71.md:50` (10 passed, 41 s); não reexecutei.

## Veredito: APROVADO COM RESSALVAS

Nenhum BLOQUEIO. As três afirmações do commit são verdadeiras no código; (4) `operator/6` gera propostas
pelo mesmo caminho de `operator/5`; (5) a pista de evento também propõe para conjuntos operator, com
deduplicação por conjunto (não por mint global) — nascem propostas gêmeas entre os dois conjuntos,
resolvidas no executor, nunca em duas posições reais.

## Achados

1. **Afirmação 1 confirmada — o executor abre qualquer operator ativo; a posição leva a saída do próprio conjunto.**
   - `services/meme-executor/hunter_meme_executor/auto_approve.py:95-101` — `_OPERATOR_PROPOSED` filtra
     `rs.kind = 'operator' AND rs.status = 'active'`, sem nome/versão.
   - `auto_approve.py:201-209` — `decision = {**proposal.suggested, note}`; `suggested` vem do próprio
     conjunto (`services/meme-worker/hunter_meme_worker/lab_models.py:235-256`: size_sol, target_x,
     trailing_pct, max_hold_s).
   - `entries.py:311-317` — `meme_live_positions.params` copia `size_sol/target_x/trailing_pct/max_hold_s`
     de `candidate.decision`; `exit_common.py:65-72` lê esses valores para
     `packages/risk-core/hunter_risk_meme/exits.py:88-98` (target, trailing, time_stop).
   - Nota: o executor **não conhece `trailing_arm_x`** (zero ocorrências em `services/meme-executor`);
     o trailing real é sempre armado desde a entrada. Para `operator/6` (`null`) é exatamente o pedido.
     Para `operator/5` (`"1.5"`) já era assim antes — não é regressão desta T.
   - Nota: `exit_on_line_break: true` também não existe no executor — regra só do loop de papel.
     Sem cenário de falha; só expectativa a alinhar na ficha.

2. **Afirmação 2 confirmada — freios por carteira, sem `rule_set_id`.**
   - `repo_positions.py:65-71` — `_OPEN_POSITIONS` = `WHERE status = 'open'` (todas as posições).
   - `admission.py:255-300` — `wallet_from` monta `MemeWalletState` com todas as posições + intents pendentes.
   - `packages/risk-core/hunter_risk_meme/inputs.py:213-214` — `slots_used = len(positions) + len(pending_intents)`;
     `checks_wallet.py:34-42` compara com `MemeLimits.max_open_positions` (env).
   - `checks_wallet.py:63-71` — `daily_loss_check` usa `wallet.daily_loss_sol` (equity da carteira inteira).
   - Bônus: o teto horário do auto-approve também é global — `auto_approve.py:275,304-305`
     (`auto_approved_last_hour` sem filtro de conjunto). Duas mesas dividem a mesma cota por hora.
   - **Ressalva (média):** o tamanho real é `min(requested, MEME_MAX_SOL_PER_TRADE, …)` —
     `sizing.py:85-86` (`trade_cap`), e `limits.py:340-345` faz `max_exposure_per_mint_sol = per_trade`.
     Se o `.env` da VPS tiver `MEME_MAX_SOL_PER_TRADE` < 0,07, a ficha de `operator/6` sai clipada
     silenciosamente (`binding_constraint = trade_cap`), não recusada.
     Cenário: env em 0,05 → `operator/6` compra 0,05 e a comparação com o papel (0,07) fica enviesada.
     Não li o `.env`; `docs/ACTIVATION.md:998` indica que em 18/09 o teto era ≥ 0,28, então provavelmente OK —
     conferir o `binding_constraint` da primeira admissão.

3. **Afirmação 3 confirmada — o seed carrega no loader do Lab (sem crash-loop).**
   - `ddl/meme_operator_6.py:96-102` — decimais como string; `trailing_arm_x: null`; inteiros em
     `max_hold_s`, `max_open_positions`, `ttl_s`; nenhum float.
   - `lab_params.py:48-50` recusa float; `lab_params.py:58-69` (`arm_multiple_or_none`) dobra `null`/≤ 1
     para `None`; `lab_params.py:164` é o ponto de entrada.
   - `lab_repo.py:43-51` — `_RULE_SETS` carrega todo `status = 'active'` com `clock <> 'event'`;
     `operator/6` tem `clock "15s"` e `gate_key`/`gate_version` (herdados de `FLOW_V2_PARAMS`,
     `ddl/meme_gate_v2_seed.py:38-40`), que `lab_gate_params.py:29-30` exigem.
   - `line_break_snapshots: 2` vem de `FLOW_V2_PARAMS` (`meme_gate_v2_seed.py:49`), então
     `exit_on_line_break` não fica órfão.
   - `packages/core/tests/integration/test_migration_0055.py:251-304` exercita `RuleSetSpec.from_params`
     + `effective_params(...).exit_rules()`; execução registrada: 10 passed.

4. **Item 4 confirmado — `operator/6` gera propostas pelo mesmo caminho de `operator/5`.**
   - `lab_fast.py:87` — `fast = [spec for spec in specs if spec.clock == "15s"]`; ambos são `15s`.
     `operator/5` = `FLOW_V2_PARAMS` + `OPERATOR_4_OVERRIDES` (`ddl/meme_creator_repeat.py:78-79`,
     `ddl/meme_gate_e1_arm2.py:39-52`): muda `gate_version` para 2 e critérios, **não** muda `gate_key`
     nem `clock`. O gate é montado só pelos parâmetros (`lab_gate_params.py:26-56`); `gate_key` é rótulo,
     não há registro por chave que possa faltar.
   - `proposals.py:266-269` — `spec.kind == "operator"` → `suggested["manual_plan"]`, idêntico para 5 e 6.
   - `lab_repo.py:97-101` — `open_mints_for` é **por `rule_set_id`**: um mint já proposto por `operator/5`
     não bloqueia `operator/6` (ver achado 5).
   - `repo_tape.py:232` — `pending_operator_mints` também lê qualquer operator ativo.
   - Sem razão estrutural para zero propostas.

5. **Item 5 — a pista de evento propõe para conjuntos operator; dedupe é por conjunto, logo há propostas gêmeas entre 5 e 6 (baixa).**
   - `event_gate_eval.py:253-262` — itera `caches.specs` (os mesmos `fast`, `lab_fast.py:141-149`);
     `already_open = open_mints[spec.id] | recently_proposed_mints(spec.id)`; inserção por `spec.id`.
   - Dentro de um conjunto: uma proposta por mint (reserva em `lab_fast.py:132-136` e
     `event_gate_eval.py:280-283`) — sem proposta dupla por mint para `operator/6`.
   - Entre conjuntos: o mesmo mint passando nos dois gates gera **duas** propostas (uma de cada). O executor
     resolve: `auto_approve.py:196-199` (`mint_repeated` no mesmo tick), `:169-171` (`mint_busy` com posição
     aberta/intent pendente), e a admissão recusa `duplicate_position` (`checks_wallet.py:28-32`).
     Nunca duas posições reais no mesmo mint.
   - Cenário de falha (não financeiro): a proposta perdedora fica `proposed` até o TTL de 180 s e é preenchida
     em papel; vence a primeira em `ORDER BY proposed_at, id` (`auto_approve.py:101`). Como `operator/5` tem
     gate mais permissivo (`max_snipers 10` vs 2), tende a propor antes/mais — `operator/6` pode perder
     disputas de mint e a comparação "5 vs 6 em real" fica enviesada para o 5. Métrica: `skipped.mint_repeated`
     / `mint_busy` no heartbeat.

6. **Consequência declarada (informativa):** `apps/api/hunter_api/repositories/meme_desk.py:194-203` —
   compra manual da mesa é arquivada em `operator/6` (versão ativa mais alta), teto 0,07. Documentado em
   `ddl/meme_operator_6.py:72-77`. Sem cenário de falha novo.

7. **Downgrade (§17.7) OK:** `ddl/meme_operator_6.py:151-214` recusa com posições/ordens reais via
   `proposal_id` e com as quatro tabelas diretas; slug 24 chars.

## Primeira hora após o deploy

No heartbeat do executor: (a) `binding_constraint` da primeira admissão de `operator/6` deve ser `requested`
(0,07), não `trade_cap`; (b) `auto_approve.skipped` — se `mint_repeated`/`mint_busy` crescerem, as duas mesas
disputam os mesmos mints e o 5 está levando; (c) saídas por `trailing` em < 60 s serão frequentes com 10 %
armado desde a entrada num curve do pump.fun (custos de 2–3 % já comem parte da folga) — não é defeito, é a
regra escolhida, mas confirme que `time_stop` (300 s) e `target` (1,15×) também aparecem.
