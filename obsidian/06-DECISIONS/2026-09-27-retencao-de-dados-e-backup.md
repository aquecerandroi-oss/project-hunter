---
tags: [decisao, infra, disco, backup, retencao]
date: 2026-09-27
updated: 2026-09-27
owner: sexta-feira
status: vigente
decided_on: 2026-09-27
by: Everton
---

# Decisão — retenção de dados e backup para o disco da VPS (27/09/2026)

**Decidido pelo Everton ("autorizado", 27/09/2026)**, sobre a proposta `docs/design/retencao-e-disco-2026-09-27.md` do `database-architect` (revisada pela Astra).

## O fato

Banco com **129 G** crescendo ~8 G/dia; `opportunity_history_2026_09` com **63 G** (65 % de cada dump) de um scanner de perpétuos que nunca operou (`orders` = 0); `outbox_events` 33 G nunca podada; crons de outbox e partições nunca instalados. Sem mudança: backup falharia em ~01/10 e o disco encheria em ~06/10 ([[2026-09-27]]).

## Autorizado (passos 1–5 da proposta)

1. Backup sem os dados de `opportunity_history` (esquema mantido), compressão melhor, retenção por quantidade de dumps.
2. Instalar as podas previstas no contrato (outbox 7 d; partições), depois da correção de trava do podador (uma transação por partição, `lock_timeout`, nunca durante o dump).
3. `TRUNCATE opportunity_history_2026_09` e retenção de 14 d; scanner de perpétuos gravando no máximo 1 linha por mercado a cada 5 min, mantendo o `envelope`.
4. Outbox em 2 d + `VACUUM FULL`, com a mesa parada e zero posição aberta.
5. Séries de memes com 30 d (15 s segue 7 d) e retenção para `meme_board_observations`/`meme_risk_snapshots`.

## Previsão

Com os cinco: **sem falha em 150 dias**, pico do banco ~169 G, mínimo ~55 G livres. Backup fora da VPS continua pendente (serviço pago — decisão do Everton).

## Execução

Código pelos especialistas (revisado antes do commit); os comandos que apagam dado são rodados pelo Everton na VPS a partir do roteiro da §7 da proposta.

- **28/09 — o que o código faz agora (database-architect, sem commit ainda):** backup sem os dados de `opportunity_history`, `zstd:3`, os 3 dumps válidos mais novos pelo nome; scanner com `history_v2` (1ª amostra, status/estágio ou 300 s; toda linha com `envelope`) e `opportunity_history` a 14 d; `MEME_RETENTION_DAYS` = 30 para as cinco séries meme (`board`/`risk` incluídas, 15 s segue 7 d); cron da outbox com `--retention-days 2`; Radar com o teto de score corrigido para amostras esparsas. **Diferença da letra do item 3:** status/estágio continuam gravando linha fora do intervalo de 5 min (senão uma excursão HOT entre dois batimentos some). Revisões: [[Retencao-disco-execucao]]. O que apaga dado (`TRUNCATE`, poda de 2 d, `VACUUM FULL`) segue no roteiro da §7, para o Everton.

## Relacionado

[[2026-09-27]] · [[2026-09-26-mesa-meme-real-pausada-no-escopo]] · [[Open Bugs]]

- **28/09/2026 ~04:40Z — passo 3 executado:** `TRUNCATE opportunity_history_2026_09` (sessão com `lock_timeout = 15000`) → a partição foi de **65 GB para 16 kB**; disco **72 % → 53 %** (248 → 183 G usados, 166 G livres). Rodado pela Sexta-feira na VPS sob a autorização do Everton de 27/09 (a tentativa dele não chegou à VPS). Antes: deploy `d8dda658` com a `0067` e `MEME_RETENTION_DAYS=30` conferido no contêiner; nenhum `pg_dump` ativo (o dump de 28/09 terminou 04:52 hora da máquina, 29 GB).

- **28/09/2026 — passo 4a executado (poda da outbox a 2 d):** `infra/scripts/prune_outbox.py --retention-days 2` na VPS, em segundo plano, sem parar nada → **35.725.398 linhas despachadas apagadas em 7.146 lotes**. O disco não muda (53 %): o espaço fica livre dentro da tabela e é reaproveitado pelas gravações novas. Devolver ~29 GB ao disco é o passo 4b (`VACUUM FULL outbox_events`, §7.4), que exige parar o executor — fica para um momento escolhido pelo Everton, com a NEAR da `spot/1` fechada. Rotinas automáticas (`infra/vps/cron/hunter-partitions`, `hunter-outbox`) aguardam o `sudo install` do Everton (mexe no agendador do sistema da VPS).
