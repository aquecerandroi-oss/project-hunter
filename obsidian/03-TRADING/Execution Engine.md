---
tags: [trading, execucao, m3, m4]
updated: 2026-09-05
status: planejado
---

# Execution Engine

## Status

**Planejado, principalmente M3 (paper/shadow) e M4 (integração completa com Risk Engine).** `hunter_core.execution` e o `execution-worker` não têm implementação hoje.

## Interface (definida, sem código)

```python
class ExecutionAdapter(Protocol):
    mode: ExecutionMode                # PAPER | SHADOW | LIVE
    async def submit(self, order: OrderIntent, market: MarketState) -> ExecutionResult: ...
    async def cancel(self, order_id) -> None: ...
    async def mark_to_market(self, positions, prices) -> list[PositionUpdate]: ...
```

`ExecutionAdapter` é o único lugar do sistema com efeitos de execução.

## Três modos planejados

- **Paper** (M3): fill simulado contra o book real (walk do book), com slippage, fee e latência simulados. Ver [[Paper Trading]].
- **Shadow** (M3/M6): grava ordens e fills com `simulated=true`, sem alterar cash — idêntico ao paper em tudo o mais; serve para comparar estratégias sem comprometer capital virtual.
- **Live** (Fase 4 — **não antes**): `LiveExecutionAdapter` existe só como interface e levanta `LiveTradingDisabled` enquanto `ENABLE_LIVE_TRADING=false` (valor atual em `.env.example`) ou o entitlement da organização não permite. **Não há UI para live trading e não deve haver antes da Fase 4** (regra explícita de `CLAUDE.md`).

## Fluxo planejado (execution-worker)

1. Entrada: `ExecutionAdapter.submit(OrderIntent)` a partir de `proposals.decided` (approved).
2. Cria `orders`, `fills`, `positions`; ordens filhas `stop`/`target` como registros `pending` (não há exchange para segurá-las em paper).
3. Gestão a cada 1 s: marcação a mercado, verificação de stop/alvos/invalidações/expiração, limites de portfolio.
4. Saída: fecha posição → `trades` com `exit_reason`, snapshots de entrada/saída, `r_multiple`.
5. Equity: snapshot por minuto em `portfolio_equity_snapshots`.

**Falha planejada:** worker reinicia → relê posições `open` do Postgres e retoma; propostas `approved` sem ordem após 30 s expiram e nunca são executadas tarde; se o mercado ficar `degraded`, o worker não abre posição nova mas continua gerenciando saídas com o último preço válido.

## Relacionadas

[[Paper Trading]] · [[Risk Engine]] · [[Portfolio]] · [[Workers]]

## Fontes

`docs/PIPELINE.md` §8, `docs/ARCHITECTURE.md` §6, `CLAUDE.md` ("Hard rules"), `docs/ROADMAP.md` (Milestones 3–4)
