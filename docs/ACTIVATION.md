# Ligar o fluxo paper — runbook de ativação (decisão do Everton, 2026-09-08: "bora ativar tudo")

Este é o caminho, na ordem, para a carteira `ever` passar a receber sinais do Lab por conta própria. Cada passo tem quem faz, o que prova e o que **não** muda. Nada aqui é automático: os passos 6, 7 e 8 são atos do Everton, auditados. A diretiva de origem (`.claude/state/directive-risk-engine-2026-09-06.md`) continua inteira; nenhum limite foi alterado.

## Por que não é uma flag só

| Fato medido | Consequência |
|---|---|
| Ligar o coletor spot no shard 0 com 200 perpétuos derrubou o socket perpétuo (1011, 8 reconexões em 6 min — `t30-proof.md` §1) | o spot precisa de um **processo próprio** (T3.0f); sem fita spot no hot state a admissão devolve `unavailable` e recusa tudo |
| `market_betas` vazia na VPS (2026-09-08 03:40Z): o job horário de β nunca foi escrito; a VPS tem 11 dias de velas e o `beta_v1` exige 20 contíguos numa janela de 30 | precisa do **produtor de β** (T3.7b) e de **backfill de 31 dias** nos 20 mercados que importam; sem β válido a admissão recusa ("sem β validado só shadow") |
| O rótulo `paper` só existe com a `0010` | o **segundo deploy** vem antes da linha `paper` |

## Os passos

| # | Passo | Quem | Prova |
|---|---|---|---|
| 1 | T3.0f: `market-worker-spot` como serviço próprio; revisão; commit | agentes / orquestrador | 30 min local: perpétuo sem reconexão, spot com 19 fitas, `hb:market:spot:binance` vivo (`t30f-proof.md`) |
| 2 | T3.7b: job horário de β no scanner + `request_backfill.py --days 31`; revisão do guardian; commit | agentes / orquestrador | revisões em `market_betas` com `valid_until > now()` para os mercados com ≥ 20 dias contíguos; motivos para os outros (`notes-T3.7b.md`) |
| 3 | Revisões da `0010` (database-architect, guardian, security) — feitas em 2026-09-08: nada bloqueia o **deploy**; o guardian **bloqueia ligar a ponte** até a T3.15c (a ponte passa a julgar a coluna `purpose`, não o envelope; o worker perde o poder de ativar um rascunho) e a T3.15e (ativação da linha derivada mantém o conteúdo copiado; uma coorte só pela ponte) | agentes | `.claude/state/review-T3.15-{db,risk,security}.md`, `notes-T3.15c.md`, `notes-T3.15e.md` |
| 4 | **Segundo deploy** (traz `0010`, T3.15b, T3.0f, T3.7b) | **Everton** | `ssh hunter-vps 'cd /opt/project-hunter && MARKET_SPOT=1 MARKET_SHARDS=4 bash infra/vps/compose.sh update'` (a flag `MARKET_SPOT=1` nasce na T3.0f) — depois: alembic em `0010`, `hb:market:spot:binance`, perpétuos intactos, `/ready` 200 |
| 5 | Backfill de 31 dias na VPS e primeira rodada de β | orquestrador (leitura) / script no container da API | `market.candles.backfilled` para os 20 mercados; `hb:scanner` com `beta_valid ≥ 1` |
| 6 | **Linha `paper` do momentum** | **Everton** (ou orquestrador com o seu "vai") | no container da API: `uv run python infra/scripts/activate_strategy_version.py momentum v1 --paper-line --dry-run --changelog "D10"`; sem `--dry-run` cria `momentum v2` `draft`, `purpose=paper`, `system_events` |
| 7 | **Ativação auditada** da linha `paper` | **Everton** | `activate_strategy_version.py momentum v2 --changelog "D10: coorte paper"` → `activated_at`, congelada; o strategy-worker passa a emitir sinais `purpose=paper` para essa coorte (a `research_only` continua ao lado) |
| 8 | **`ENABLE_PAPER_AUTONOMY=true`** no `.env` da VPS + `compose.sh update` — **só depois** de T3.15c e T3.15e implantadas (passo 3) | **Everton** | log `execution_worker_starting paper_autonomy=true`; `hb:execution:paper` com `pending_requests` variando; primeira proposta em `trade_proposals` com `proposal_source=agent` |
| 9 | Primeira avaliação datada do EXP-0005 depois do primeiro fill | Sexta-feira | SQL colado na página |

## O que continua igual depois do passo 8
- Só ordens a mercado, só SPOT, sem alavancagem; fill pelo livro elegível após a latência declarada; sem fill fabricado.
- Risco 0,25 % por operação incluindo custos, soma ≤ 1 %, participação ≤ 1 % do minuto, β-BTC ≤ 0,5×, total ≤ 40 %, por moeda ≤ 10 %, máx. 5 posições, pendentes contam.
- Kill switch AVISO/BLOQUEADO como na diretiva; BLOQUEADO só sai com o Everton (OWNER).
- Uma proposta por ciclo (D3), `research_only` nunca vira ordem, `live` recusado por nome, `ENABLE_LIVE_TRADING=false`.

## Como desligar
`ENABLE_PAPER_AUTONOMY=false` + `compose.sh update` para a ponte parar de consumir (posições abertas continuam protegidas pelo worker). `activate_strategy_version.py momentum v2 --deprecate` não existe: deprecar é um `UPDATE status='deprecated'` auditado pelo dono do banco — registrar na T3.10 se virar rotina.

## Onde acompanhar
`/ever/portfolio` (patrimônio, kill switch, curva), `/ever/system` (worker, `autonomy`, pendências, proteções), `hb:execution:paper` no Redis, `obsidian/05-EXPERIMENTS/EXP-0005-momentum-paper.md`.
