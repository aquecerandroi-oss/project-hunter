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

## As cinco classes, por dia (Dataview)

Desde `infra/scripts/meme_daily_ficha_frontmatter.py` (commit `53a1295e`), cada ficha diária carrega
`perdas_<classe>_n`/`perdas_<classe>_sol` para as cinco classes, mais `dia`, `operacoes`, `ganhos`,
`pnl_sol` e `maior_vazamento` — ver [[Painel da mesa]] para os gráficos do Tracker sobre os mesmos
campos.

```dataview
TABLE
  maior_vazamento AS "maior vazamento",
  perdas_comprou_no_topo_sol AS "comprou_no_topo",
  perdas_golpe_do_criador_sol AS "golpe_do_criador",
  perdas_recompra_sol AS "recompra",
  perdas_custo_sol AS "custo",
  perdas_saida_normal_sol AS "saida_normal"
FROM "03-TRADING/Meme/Fichas"
WHERE dia
SORT dia ASC
```

`WHERE dia` pega só fichas **diárias** (`Ficha-AAAA-MM-DD.md`); as semanais (`Semana-*.md`, mesma
pasta) carregam `semana_inicio`/`semana_fim` em vez de `dia` e ficam fora desta tabela de propósito
— cada classe tem a sua própria consulta e a ressalva de ordem de precedência (`recompra` em
particular) na página irmã. [[Ficha-2026-09-24|24/09]] e [[Ficha-2026-09-25|25/09]] — hoje as duas
únicas fichas diárias — só aparecerão aqui depois de regeradas pelo próximo deploy do
`meme_daily_ficha.py`: o frontmatter delas ainda não tem esses campos. Até lá, a coluna "soma
24–25/09" da tabela acima (copiada à mão de cada página) continua sendo a fonte.

## Relacionado

[[Mapa de Estrategias]] · [[Dicionario de Variaveis]] · [[Fila de Hipoteses]] ·
[[KB-0149-o-que-a-mesa-real-ensinou]] · [[Ficha-2026-09-24]] · [[Ficha-2026-09-25]]
