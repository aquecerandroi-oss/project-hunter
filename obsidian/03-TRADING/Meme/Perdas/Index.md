---
tags: [trading, meme, perda, indice]
tipo: consolidado
mercado: meme
status: vivo
owner: sexta-feira
updated: 2026-09-25
---

# Perdas — as cinco classes do classificador automático (T4.92)

Toda posição real perdedora da mesa de memes recebe **uma** classe, pela primeira regra que casar,
em `infra/scripts/meme_daily_ficha_classify.py` — ver cada página para a regra exata, o custo medido
nas fichas existentes e as hipóteses que já a atacaram.

| classe | ordem | regra (resumo) | soma 24–25/09 (2 fichas) |
|---|---:|---|---:|
| [[comprou_no_topo]] | 1 | o pico da posição nunca subiu acima do custo | 20 op, **−0,2642 SOL** |
| [[golpe_do_criador]] | 2 | saída = `creator_dump` **ou** ≥10 vendedores no mesmo slot | 2 op, **−0,0142 SOL** |
| [[recompra]] | 3 | reentrada no mesmo mint ≤ 300 s depois de uma saída | 0 op na ficha (ver ressalva de ordem na página) |
| [[custo]] | 4 | a perda é menor que o custo de ida e volta | 0 op |
| [[saida_normal]] | 5 | nenhuma das anteriores — perda de mercado comum | 10 op, **−0,0573 SOL** |

`comprou_no_topo` é, disparado, o maior vazamento medido: mais do que o prejuízo líquido de uma
semana inteira segundo a origem da [[Fila de Hipoteses|H-019]]. Nenhuma variável medida até
25/09/2026 prevê essa classe antes da compra.

## Relacionado

[[Mapa de Estrategias]] · [[Dicionario de Variaveis]] · [[Fila de Hipoteses]] ·
[[KB-0149-o-que-a-mesa-real-ensinou]] · [[Ficha-2026-09-24]] · [[Ficha-2026-09-25]]
