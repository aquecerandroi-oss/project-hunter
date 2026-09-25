---
tags: [trading, meme, perda, classe, custo]
tipo: consolidado
hipotese: —
variavel: round_trip_cost_sol (taxas + rede - reembolso de aluguel de ATA)
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: confirmar que MEME_CLOSE_ATA_ON_FULL_SELL está de fato ligado em produção (pendência aberta em 24-25/09)
classe_de_perda: custo
mercado: meme
status: vivo
owner: sexta-feira
updated: 2026-09-25
---

# `custo` — a posição empatou no mercado e perdeu só de taxa

## Definição exata (T4.92, `infra/scripts/meme_daily_ficha_classify.py`)

Regra 4 de 5 (checada só se `comprou_no_topo`, `golpe_do_criador` e `recompra` não dispararam — ver
as três páginas irmãs):

> A perda, em módulo, é **menor** que o custo de ida e volta (taxas de compra e venda + rede, menos
> qualquer reembolso de aluguel de ATA registrado). O mercado ficou aproximadamente no zero a
> zero; foi só o custo que virou a operação vermelha.

```python
if inputs.round_trip_cost_sol is not None and -inputs.pnl_sol < inputs.round_trip_cost_sol:
    return "custo"
```

`round_trip_cost_sol` ausente pula esta checagem sem presumir — a posição cai para `saida_normal`.

## Por que esta classe é o achado mais antigo e mais barato de corrigir

[[KB-0149-o-que-a-mesa-real-ensinou]] (item 1, R65, 22/09/2026) já tinha decomposto o problema antes
do classificador automático existir: **72 % do prejuízo dos primeiros 7 dias era custo, não
mercado** — o preço tirou −0,0952 SOL; taxas e aluguel tiraram −0,2492. Composição por operação:
**4,09 % do tamanho** (pump.fun 1,59 % + criador 0,50 % + rede 0,13 % + **aluguel de ATA 1,86 %**).
Sem o aluguel: 2,23 %. **O aluguel sozinho era 33 % de todo o prejuízo** (−0,1135 SOL): 75 contas
abertas, **0 das 87 vendas** pediu reembolso porque a flag `MEME_CLOSE_ATA_ON_FULL_SELL` nasceu
desligada por cautela em 16/09 (T4.46) e ninguém a ligou por 7 dias.

**Ponto de equilíbrio medido:** com alvo +15 %, o acerto necessário para empatar é **27 % com
aluguel, 19 % sem** — a mesa fazia 26 %, ou seja, o vazamento de aluguel era a diferença entre
perder e empatar (item 4 do KB-0149).

## A pendência que ainda não foi confirmada em produção

O diário de [[09-OPERATIONS/Diario/2026-09-22|22/09]] registrou o vazamento e a correção
(`MEME_CLOSE_ATA_ON_FULL_SELL=1`); o de [[09-OPERATIONS/Diario/2026-09-23|23/09]] marcou como
"pendente de verificação" (a primeira venda cheia depois da recriação ainda saiu com
`closes_ata: false`). Esta página **não encontrou**, nas fichas de 24/09 e 25/09, nenhuma linha
classificada como `custo` — o que é compatível com o reembolso já estar funcionando (as perdas que
sobram são maiores que o custo, então caem em outras classes) **ou** com a amostra ser pequena
demais para o caso "perda pequena, só de taxa" aparecer. As duas fichas existentes não trazem uma
coluna de aluguel reembolsado; **não dá para decidir isto por Dataview hoje**.

## Custo medido, pelas fichas existentes

| dia | n | SOL |
|---|---:|---:|
| [[Ficha-2026-09-24\|24/09]] | 0 | — |
| [[Ficha-2026-09-25\|25/09]] | 0 | — |

Zero em ambos os dias. **O que faltaria para o Dataview confirmar isto sozinho:** um campo no
frontmatter da ficha com o aluguel de ATA reembolsado por dia (ex.: `ata_reembolsado_sol`) e a
contagem de vendas com `closes_ata=true` — nenhum dos dois existe hoje no gerador
(`infra/scripts/meme_daily_ficha.py`); não alterado aqui.

## Hipóteses que atacaram esta classe

Nenhuma hipótese formal da [[Fila de Hipoteses]] mira `custo` diretamente — o achado do R65 (item 1
do KB-0149) foi tratado como **correção operacional imediata** (P0, "ligar o fecho da ATA já"), não
como hipótese a testar, porque a aritmética do custo não depende de amostra (só o **efeito** de
corrigir dependeria, e a correção já foi decidida).

## Relacionado

[[Mapa de Estrategias]] · [[Dicionario de Variaveis]] · [[Fila de Hipoteses]] · [[Perdas/Index|Perdas]] ·
[[KB-0149-o-que-a-mesa-real-ensinou]] · [[Ficha-2026-09-24]] · [[Ficha-2026-09-25]] ·
[[09-OPERATIONS/Diario/2026-09-22|Diário 22/09]] · [[09-OPERATIONS/Diario/2026-09-23|Diário 23/09]]
