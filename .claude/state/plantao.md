# Plantão da Sexta-feira — nota do turno

Atualizado: 2026-09-06, madrugada. M1 fechado e aprovado.

## O que mudou neste turno
- **Memória** (`e254145`): changelog dos três commits, `Dialogos/SHADOW.md` com a decisão conjunta
  integral e o aceite S0–S4, contrato do Lab em `Architecture Decisions`, `Experiments Index` e
  `_TEMPLATE-EXP` reescritos, agentes em `planejado-sombra`, `Market Collector` e
  `Mente da Sexta-feira` atualizadas, diário do dia.
- **CRITICAL corrigido** (`4f9ab28`): `shard_symbols` com `encode("ascii")` cegava os 200 mercados
  (a Binance lista perpétuos com símbolo em chinês, quatro no top 100). Mais dois HIGH e dois
  MEDIUM que as revisões dessa correção trouxeram.
- **Prova da T1.6b** (`3167360`, `fa24346`): três topologias medidas contra a Binance ao vivo.
  200 mercados são alcançáveis (4 shards × 50 → `markets_ok` 198/200 = 99,0%), mas **não foram
  entregues**: com N > 1 shards o heartbeat é compartilhado e a página System mente. No ar ficou
  **um processo × 50 mercados, `markets_ok` 50/50 = 100%**.
- **Relatório do M1** (`fc3e56f`): formato estendido, todo número com comando colado.

## Estado do M1
**APROVADO** pela Sexta-feira em 2026-09-06 em nome do Everton (`3d47a9e`). O bloqueio — o teste de
webhook vermelho 3 em 3 — foi investigado com medição, corrigido em `27a0598` sem tocar código de
produção, e revisado adversarialmente por `code-reviewer` e Astra, que responderam PRESERVADO
independentemente. `milestone.json` está em **M2, onda 1 a despachar: T2.1 + T2.2**.

Ressalva registrada com a aprovação: o M1 entrega **50 mercados**, não os 200 do plano. Os 200 estão
provados (4 shards × 50 → `markets_ok` 198/200) e não entregues, porque essa topologia compartilha a
chave de heartbeat e faria a página System mentir.

## Em voo (não tocar nos arquivos)
| Tarefa | Dono | Arquivos |
|---|---|---|
| S2 — strategy-worker sombra | `backend-specialist` | `services/strategy-worker/**`, `packages/core/hunter_core/events/streams.py` |
| webhook vermelho | `backend-specialist` | `apps/api/hunter_api/services/clerk_webhook.py`, `apps/api/tests/integration/test_webhook.py` |

`ruff check .` no repositório inteiro está vermelho com 5 erros — **todos em
`services/strategy-worker/`**, código da S2 em voo. Nos caminhos do M1 está limpo.

## Próximo passo
Despachar a onda 1 do M2: **T2.1** (`database-architect`, opus — schema de análise; a migração passa
a depender de `0002_shadow_lab` e vira `0003`) e **T2.2** (`quant-engineer`, opus — Feature Engine),
em paralelo, com os kits de revisão prontos antes das entregas. A decisão conjunta do M2 já está
fechada, então não há etapa de diálogo a repetir.

## Dívidas do M1 que entram no M2, por prioridade
1. **Heartbeat por shard com agregação na API** — é o que libera os 200 mercados já provados.
2. **`dataclass(slots=True)` nos tipos normalizados do caminho quente** — `model_construct` do
   pydantic é 15% do tempo amostrado pelo py-spy, resolvendo defaults a cada evento.
3. Gaps de mercados não monitorados que nunca fecham; rebalanceamento na morte de um shard.

## Achado no fecho, corrigido à mão e registrado
O worker foi recriado por outro fluxo **sem o override** e voltou silenciosamente a 200 mercados:
`markets_ok` 0, tudo `degraded`, hot state completo em 7,0% — o colapso que a prova mediu. Causa: o
`docker-compose.override.yml` só entra na descoberta padrão de arquivos, e o comando documentado no
`CLAUDE.md` usa `-f` explícito. Restaurado à mão às 23:39 UTC (`markets_ok` 49/50, hot state 98%) e
registrado como HIGH operacional em [[Open Bugs]]. **A correção certa é mover `MARKET_UNIVERSE_SIZE:
"50"` para o próprio `docker-compose.yml`**, deixando o override só para aumentar — não foi feita
agora porque `infra/docker/docker-compose.yml` está sendo editado pela S2. É o primeiro item do M2,
junto do heartbeat por shard.

## Precisa do Everton
- Nada bloqueante. Opcional: `.env` e logins na VPS (`ssh hunter-vps`).
