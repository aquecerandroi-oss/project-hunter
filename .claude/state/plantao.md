# Plantão da Sexta-feira — nota do turno

Atualizado: 2026-09-05, madrugada (fechamento do M1).

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
**Aprovação SUSPENSA por um item só**, objetivo:
`apps/api/tests/integration/test_webhook.py::test_a_crash_where_even_the_release_never_runs_still_recovers_after_the_stale_window`
falha 3 em 3 com a máquina ociosa — vermelho reprodutível carregado desde a T1.3. Despachado ao
`backend-specialist` com a instrução de decidir com evidência entre defeito de idempotência e teste
que promete o que a implementação nunca prometeu, **sem** alargar timeout até passar.

Assim que a suíte `apps/api` fechar verde: escrever a linha de aprovação no topo de
`docs/reports/M1.md`, mudar `.claude/state/milestone.json` para M2 (`status: planned`, onda 1 =
T2.1 + T2.2, com T2.1 referenciando `0002_shadow_lab`), acrescentar o item ao changelog e ao
diário, commitar e dar push.

## Em voo (não tocar nos arquivos)
| Tarefa | Dono | Arquivos |
|---|---|---|
| S2 — strategy-worker sombra | `backend-specialist` | `services/strategy-worker/**`, `packages/core/hunter_core/events/streams.py` |
| webhook vermelho | `backend-specialist` | `apps/api/hunter_api/services/clerk_webhook.py`, `apps/api/tests/integration/test_webhook.py` |

`ruff check .` no repositório inteiro está vermelho com 5 erros — **todos em
`services/strategy-worker/`**, código da S2 em voo. Nos caminhos do M1 está limpo.

## Primeira dívida a entrar no M2
**Heartbeat por shard com agregação na API.** É o que libera os 200 mercados já provados.

## Precisa do Everton
- Nada bloqueante. Opcional: `.env` e logins na VPS (`ssh hunter-vps`).
