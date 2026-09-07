# Revisão de segurança — 0007_paper_roles (`2688ef1`) — security-reviewer, 2026-09-07 — NADA BLOQUEIA

Reproduzido como os papéis reais em Postgres próprio, 2 organizações, carteiras abertas pelo caminho real. Grant de coluna preciso; org switch fora do alcance do motor; trigger do pedido honesto recusa 8 disfarces; segunda principal impossível; curva só leitura para o app inclusive nas partições; downgrade nomeia o que perde; RLS cruzada intacta; replay de transição bancada recusado.

## DEVE CORRIGIR → **0008_paper_roles_2** (database-architect)
- **D1 (alta) — `ddl/tables.py:114-117`:** `hunter_app` tem DML completo em `orders`, `fills`, `positions`, `trades`. Reproduzido: fill fabricado, `positions.qty × 1000`, `DELETE FROM trades`, `UPDATE orders` — tudo aceito na org certa. A curva (fechada na 0007) é derivada dessas tabelas: forjar a fonte faz o worker escrever o ponto forjado assinado pelo papel confiável. Nenhuma rota escreve essas tabelas. **Correção:** `REVOKE INSERT, UPDATE, DELETE ON orders, fills, positions, trades FROM hunter_app` (manter SELECT; `trade_proposals` já está certo); mover para `APP_READ_ONLY_TABLES` na classe congelada da 0008; testes como o da curva.
- **D2 (média) — `apps/api/tests/integration/test_rbac_matrix.py:253` e `test_isolation.py:111`:** as guardas de cobertura de rota estão vermelhas (16 declaradas × 23 servidas): as 7 rotas de `routers/portfolio.py` (T3.8a) não entraram nas listas. Corrigir: as 7 operações como VIEWER nas duas listas; `== 16` → `len(ROUTE_LIST)`.
- **D3 (média) — `ddl/paper_roles.py:81-98,149-150`:** o `INSERT` do worker em `portfolios` cria `is_arena=true`, `type='live'`, ou carteira em **outra organização** (BYPASSRLS), sem âncora, sem risk state, sem auditoria. Correção: constraint trigger `portfolios_are_born_audited` (autor só com privilégios do motor → `type='paper' AND NOT is_arena` **e** `audit_logs` na mesma transação, `xmin` corrente), formato da §18.7.
- **D4 (baixa/média) — `ddl/paper.py:804-809` + `paper_roles.py:59`:** `kill_switch_reason` reescrevível sem transição (o `WHEN` da trigger só olha `kill_switch_state`); a tela do OWNER mostra o texto reescrito. Correção: `OR OLD.kill_switch_reason IS DISTINCT FROM NEW.kill_switch_reason` no `WHEN`, ou a API deriva o motivo da última transição.

## SUGESTÕES
- **S1 → T3.5:** `_REQUEST_SHAPE` não cobre `request_digest`/`kill_switch_snapshot`; o motor faz `coalesce(request_digest, :digest)` e confia no digest que a API gravou → **recomputar e comparar** no motor, nunca `coalesce`.
- **S2:** `packages/core/hunter_core/risk/resume.py:100-101` docstring ainda diz TRADER.
- **S3:** `open_paper_wallet.py` como `hunter_worker` atravessa a RLS e `--org` resolve qualquer slug: (a) auditoria nomeia o script, não a pessoa; (b) pós-condição na mesma transação (contar as seis linhas por `organization_id`); (c) confirmação explícita (`--yes` com o slug repetido) antes de um ato permanente.
- **S4:** um único login membro dos dois papéis (`SET LOCAL ROLE`): login separado por processo, o da API só `hunter_app` — decisão de deploy (Everton/devops).
- **S5:** teste do `POST .../resume` cross-org (OWNER de A sobre carteira de B → 404).
- **S6/S7:** `PIPELINE.md` já estava certo antes do commit; `DATABASE.md:2830` lista "travar a organização inteira, ADMIN+" como existente — não há rota; marcar como intenção.
