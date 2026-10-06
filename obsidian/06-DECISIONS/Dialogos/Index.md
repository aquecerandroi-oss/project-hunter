---
tags: [dialogo, indice]
updated: 2026-09-05
status: registro
owner: sexta-feira
decided_on: 2026-09-05
by: sexta-feira (claude+astra)
---

# Diálogos — índice

Cada diálogo é uma sessão de pensamento da [[Mente da Sexta-feira]]: o Claude escreve uma rodada, a Astra responde no mesmo arquivo, e assim até a DECISÃO CONJUNTA, que vai para o plano e para [[Architecture Decisions]].

- [[M1]] — milestone M1 (4 rodadas)
- [[M2]] — milestone M2 (4 rodadas)
- [[SHADOW]] — Shadow Lab v0: estratégias avaliando o mercado real em modo sombra (3 rodadas, DECISÃO CONJUNTA; plano `docs/plans/SHADOW-LAB.md`)
- [[M3]] — carteira virtual e Risk Engine, a partir da diretiva do Everton de 2026-09-06 (3 rodadas, DECISÃO CONJUNTA; plano `docs/plans/M3.md`, contrato v2, ADR 0005)
- [[Dialogos/2026-09-08-quatro-estrategias|2026-09-08 — quatro estratégias novas]] — os dois motores responderam quatro cada um, **duas coincidem**; a divergência (spot–perp e força relativa contra `session_orb` e `derivatives`) foi resolvida por medição do fecho do `code_ref` e do protocolo de um mercado só
- [[EXP-M26]] — gráfico em moedas maduras, 15–120 min (5 rodadas, DECISÃO CONJUNTA em 26/09; aprovado pelo Everton; seed condicionado aos aceites de R1/J)
- [[wallet-tape-storage]] — armazenamento da fita do H-030 depois da medição: nenhuma opção completa cabe em ~20 GB; fita enxuta no Postgres com poda por dependência, campanha finita, teto pedido ao Everton (3 rodadas, DECISÃO CONJUNTA em 05/10)
- [[wallets-cpu]] — CPU do motor de carteiras 1c-bis (≈ 31–34 h/núcleo): medir antes de reescrever; incremental simples inválido; meta < 2 h em 2 núcleos (rodadas 1–2, 06/10)

Revisões avulsas da Astra: [[Revisoes-Astra/Index|índice de revisões]].
