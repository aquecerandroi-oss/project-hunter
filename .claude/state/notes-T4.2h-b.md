# Notas T4.2h-b — a vigilância do criador nas posições reais, no heartbeat e na tela (15/09/2026, 16:2x–17:0x BRT)

**Por quê:** a T4.2h entregou a vigilância só para o papel. Em 15/09 às 16:13 BRT havia 27 vendas do criador vistas
na cadeia e a saída acontecia em média **149 s** depois da venda; a posição **real** (`meme_live_positions`) nem
sequer olhava para a coluna — continuava aprendendo do dump pela fita do minuto.

## 1. Os 149 s, medidos e explicados

O laço da Lab já roda a cada 15 s (`lab_cycle_s = 15`), então a cadência do tique **não** era a causa. A causa é a
forma do motor de papel: `decide_exit` roda **por fotografia**, e a venda precisava de **duas** — uma para a regra
disparar (gravando `exit_intent`) e a seguinte para precificar a venda. Como a venda do criador é uma observação com
**relógio próprio** (ela tem instante: `creator_sold_seen_at`), tratá-la como o `sell_now` do operador remove a
primeira: o `exit_intent` nasce com `decided_at = creator_sold_seen_at`, `trigger = "creator_watch"`, e a **primeira**
fotografia posterior fecha. `lab_bets._observed_intent` é o helper compartilhado pelos dois gatilhos "fora da foto";
o `exit_on_creator_dump` do conjunto continua sendo respeitado (hoje `True` para todos, mas o gate é lido).

**A outra metade fica declarada, não escondida:** a faixa rápida de 15 s só cobre moedas com menos de
`fast_lane_max_age_s = 300` s. Uma moeda mais velha é fotografada uma vez por minuto, então a "primeira fotografia
posterior" pode estar a até 60 s. Pôr os mints com venda vista na faixa rápida é orçamento de RPC — tarefa própria.

## 2. O que foi entregue

- **`0038_meme_creator_watch_live`** (`ddl/meme_creator_watch.py` refatorado para gerar os dois conjuntos de uma
  função): as **mesmas três colunas** e os **mesmos três CHECKs** em `meme_live_positions`. Nomes iguais de propósito
  — um laço escreve os dois livros, uma consulta mede `exit_at − creator_sold_seen_at` em qualquer um. Modelo ORM
  atualizado com os três `CheckConstraint` (sem isso o `alembic check` acusa drift — foi o que a T4.23 achou na
  metade de `meme_paper_bets`). Downgrade recusa sob venda vista. **Nenhum grant se move.**
- **`creator_watch.py`**: `_WATCHED` virou a união de apostas de papel abertas e posições reais abertas, com
  `bool_or(live)` para o heartbeat contar o dinheiro real apartado; a marca e o `creator_ata_missing` vão para as duas
  tabelas na mesma transação.
- **Executor**: `OpenPosition.creator_sold_seen_at` + `OpenPosition.creator_dump_seen(fita)` (predicado puro,
  testável) lido no tique de 5 s de `exits.py`. A precedência da §6 não muda: `sell_now` e emergência continuam acima.
- **`creator_stats.py`** (módulo novo; `sources.py` está no teto de 350): gauges, dois `RollingCounter` e a latência
  **medida das linhas** (`sale_to_exit_samples`, percentil por posto de `lab_heartbeat.percentile`, 200 saídas mais
  novas de papel **e** de posição real). `RadarContext.creator` entra por `default_factory` — `main.py` ficou intacto
  (e voltou de 353 para 350 linhas); o `enabled` é lido da config no instante da escrita, em `wiring.heartbeat_once`.
- **API/tela**: 9 campos em `MemeSources`, `creatorWatchLine` em `meme-sources-format.ts`, a linha nas duas variantes
  do painel, `pnpm gen:types`.

## 3. Provas (saídas reais)

`test_creator_watch_persistence.py` **4 passed** (testcontainer) · worker unit **232 passed** (61 deselecionados;
`test_creator_stats.py` 6) · executor unit **30 passed** (`test_exits_creator_watch.py` 5) · executor integração
**10 passed** (a venda vista fecha a posição real com `exit_reason = creator_dump`) · core unit **1 333 passed** ·
`test_migrations -k "0036 or 0037 or 0038 or alembic_check or upgrade_head"` **11 passed** (68 s) ·
API `test_meme_sources_service.py` **13 passed** · Vitest 3 arquivos **116 passed** · `pnpm typecheck`/`pnpm lint` sem
erro · ruff/format/pyright 0 · `check_file_size` 0 acima.

## 4. Coordenação com a T4.23 (concorrente)

A `0037` não existia no disco quando escrevi a `0038`; escrevi `down_revision = "0037_meme_e1_arms_3_4"` como o brief
mandou e a `0037` apareceu antes de eu rodar os testes, então **toda saída acima é contra a cadeia real**, sem
remendo. `HEAD_REVISION` já estava em `0038` (a T4.23 a subiu ao ver o meu arquivo) e os `test_0037_*` já estagiam em
`E1_ARMS_3_4_REVISION`; não editei nada dela.

## 5. Prova na VPS depois do deploy

`hb:meme:radar` com `creator_watch_live_mints > 0` quando houver posição real aberta;
`creator_watch_sale_to_exit_s_p50` caindo de ~149 s para a casa dos 15–60 s conforme as vendas novas forem saindo
(as saídas antigas continuam na amostra até rolarem para fora das 200 mais novas);
`select count(*) from meme_live_positions where creator_sold_seen_at is not null`.

## 6. Fora (declarado)

Faixa rápida de 15 s para os mints com venda vista (orçamento de RPC); alarme/limiar sobre
`creator_watch_sale_to_exit_s_p95` (hoje é só publicação); nada real foi tocado — `sendTransaction` não aparece em
nenhum caminho novo e nenhuma flag de live mudou de valor.
