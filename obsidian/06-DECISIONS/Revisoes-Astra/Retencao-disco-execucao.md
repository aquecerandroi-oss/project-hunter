---
tags: [astra, revisao, infra, disco, backup, retencao, radar]
date: 2026-09-27
updated: 2026-09-28
status: fechada
owner: sexta-feira
decided_on: 2026-09-27
by: Astra + database-architect + quant-engineer
---

# Revisão da Astra — execução do plano de disco (27–28/09/2026)

**Tarefa:** a parte de código dos passos 1–5 autorizados em [[2026-09-27-retencao-de-dados-e-backup]]
(proposta `docs/design/retencao-e-disco-2026-09-27.md`, roteiro na §7): backup menor com retenção por
contagem, scanner gravando menos `opportunity_history` (`history_v2`), 14 d para ela, 30 d para as
séries meme (com `board`/`risk` ganhando retenção), outbox em 2 d. Quatro pareceres: três da Astra
(desenho antes de codar, diff, correções) e a revisão do `quant-engineer` sobre o `history_v2`.

**Resultado no código:**
- backup sem os dados de `opportunity_history`, `zstd:3` quando o `pg_config` do container tem zstd,
  retenção pelos N dumps mais novos pelo nome, `.partial` até o `pg_restore --list` passar;
- `history_v2`: 1ª amostra, troca de status ou de estágio, ou `SCANNER_HISTORY_INTERVAL_S` (300 s);
  cada linha continua com `envelope` e `decomposition` e diz por que existe (`history_sample`, com
  `interval_s`);
- `max_score_ever` do Radar = maior entre o histórico e o `peak_score` dos episódios; a ponte loga a
  idade do score que usou;
- cron da outbox com `--retention-days 2` explícito (o padrão do script fica 7).

**Astra — aceito:**
- status/estágio seguem como gatilho (um teto rígido de 1 linha/5 min apagaria uma excursão
  WATCHING→HOT→WATCHING) — **contra a letra** "no máximo 1 linha por 5 min" da decisão, a favor do
  desenho autorizado;
- o episódio guardava a marca da última *avaliação*, não da última amostra *gravada*: cada reinício
  adiava o batimento — corrigido;
- na janela do `VACUUM FULL`, zero posição não impedia o executor de abrir `spot/1` com o coletor spot
  parado (`SPOT1_ENABLED=true` medido): o roteiro para o executor antes e reconta as ordens em voo;
- a nota do web prometia demais: um episódio antigo com `peak_score` NULL e histórico podado é
  invisível — a frase agora diz "entre os picos guardados e as amostras ainda retidas";
- a consequência que eu tinha registrado sobre o pedigree estava errada: `creator_prior_dump_count` só
  olha 7 dias (`PRIOR_WINDOW_S`), 90 → 30 d não o muda.

**Quant-engineer — aplicado (F1–F5):** o teto do Radar subestimava com amostras esparsas; `interval_s`
no envelope; `SCANNER_HISTORY_INTERVAL_S=inf` derrubava todo ciclo (agora limitado, política montada
uma vez); um episódio novo começa em `first_sample`; `score_ts`/`score_age_s` no log da ponte.

**Rejeitado / não adotado:** dump truncado antigo ocupando vaga na contagem (os três dumps de 27/09
têm `ok:` no `backup.log`; a conferência ficou no roteiro); lock contra backup manual concorrente (o
cron roda uma vez por dia; uma listagem que falha poda menos, nunca mais).

**Aberto:** o cabeçalho da faixa do Radar (`buildHeadline`) ainda diz "nenhum mercado passou de
NORMAL desde …", falso com `ANOMALY` abaixo de 40 — fora do escopo pedido.

Brutos: `.claude/state/astra-review-disk-plan-design.md`, `astra-review-disk-plan-code.md`,
`astra-review-disk-plan-fixes.md`. Relacionado: [[2026-09-27]] · [[Prune-partitions-locks]] ·
[[06-DECISIONS/Revisoes-Astra/Index|Revisões da Astra]]
