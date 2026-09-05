# Plantão da Sexta-feira — nota do turno

Atualizado: 2026-09-05, turno da noite (fechamento do M1).

## O que mudou desde o último turno
- **T1.6b commitada** (`b8998cc`): parse leve no adaptador, hot state em lote e sharding do universo
  com eleição de líder (`MARKET_SHARD=i/N`). Processo solo mantém o comportamento do M1.
- **T1.7 commitada** (`66b8eb4`): `tests/integration` (pipeline inteiro, invariantes, recovery,
  supervisão), `tests/e2e/markets.spec.ts` e passo nomeado na CI. 34 passed, 6 skipped (ao vivo).
- **Decisão conjunta do Shadow Lab** (`fc336d9`): contrato fechado em 3 rodadas, tarefa S0 criada,
  `EXP-0001`/`EXP-0002` reservados ao Shadow e `EXP-0003` ao M2, `AGENTS.md` dá à Astra o mesmo
  toolkit dos agentes Claude.
- **Memória atualizada** (etapa 1 deste turno): changelog com os três commits, `Dialogos/SHADOW.md`
  nova com a decisão integral e o aceite S0–S4, contrato do Lab em `Architecture Decisions`,
  `Experiments Index` + `_TEMPLATE-EXP` reescritos (reserva de IDs, protocolo congelado, avaliações
  acrescentadas, carteira não aplicável), `Momentum Agent`/`Volume Agent` em `planejado-sombra`,
  `Market Collector` com sharding e `tracking_hold` previsto, `Mente da Sexta-feira` com o toolkit da
  Astra e duas lições novas, diário do dia com a sessão da noite.

## Em voo (não tocar nos arquivos)
| Tarefa | Dono | Arquivos |
|---|---|---|
| S0 — migração `0002_shadow_lab` | `database-architect` | `infra/migrations/**`, `hunter_core/db/models/agents.py`, `domain/enums.py`, `hunter_core/strategies/canonical.py` |
| S1 — `hunter_core.strategies` | `quant-engineer` | `packages/core/hunter_core/strategies/**` |

## Em curso neste turno
- Etapa 2: prova da T1.6b contra a Binance real com 200 mercados (`.claude/state/t16b-proof.md`).
- Etapa 3: completar `docs/reports/M1.md` e decidir a aprovação do M1 pela delegação do Everton.

## Precisa do Everton
- Nada bloqueante. Opcional: `.env` e logins na VPS (`ssh hunter-vps`); colar o hook `Stop` de voz no
  `.claude/settings.json`.
