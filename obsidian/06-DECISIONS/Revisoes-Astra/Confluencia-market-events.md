---
tags: [revisao-astra, spot, eventos, spec]
date: 2026-09-23
updated: 2026-09-23
status: registro
owner: sexta-feira
decided_on: 2026-09-23
by: astra
tarefa: desenho de confluência entre eventos de mercado e recusas/ordens da mesa spot
veredito: opinião de arquitetura — market_events separado, ±15 min de foco, spot_orders como fonte
---

# Revisão da Astra — confluência de eventos de mercado (spot)

A Astra defendeu uma tabela `market_events` separada (em vez de reaproveitar uma existente), janela de
±15 minutos como foco inicial com ±60 minutos visível para contexto, e `spot_orders` como fonte das
recusas efetivamente registradas — não uma reconstrução paralela. Pediu que a especificação distinga
três coisas: o que aconteceu, o que a mesa sabia naquele instante, e o que se descobriu depois — as
três não podem ser misturadas numa única tabela sem carimbo de quando cada uma ficou conhecida.

**Bruto:** `.claude/state/astra-review-confluencia.md`
**Relacionado:** [[03-TRADING/Spot/Mesa-spot-1|Mesa spot/1]]
