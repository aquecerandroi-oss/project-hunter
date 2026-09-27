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

## Relacionado

[[2026-09-27]] · [[2026-09-26-mesa-meme-real-pausada-no-escopo]] · [[Open Bugs]]
