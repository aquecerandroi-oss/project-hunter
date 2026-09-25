---
tags: [trading, meme, mesa-real, painel, tracker]
status: vivo
owner: sexta-feira
updated: 2026-09-25
---

# Painel da mesa — memes (mesa real)

Gráficos do plugin **Tracker** sobre as fichas diárias automáticas de
`03-TRADING/Meme/Fichas/` (`infra/scripts/meme_daily_ficha.py`, T4.92). Cada ficha
`Ficha-AAAA-MM-DD.md` carrega, no frontmatter, os totais em decimal puro que os gráficos leem —
`docs/OBSIDIAN.md` §1 explica o padrão de frontmatter da base; os nomes exatos dos campos vêm
de `infra/scripts/meme_daily_ficha_frontmatter.py` (`dia`, `operacoes`, `ganhos`, `pnl_sol`,
`perdas_<classe>_n`, `perdas_<classe>_sol` para as cinco classes de
`meme_daily_ficha_classify.LOSS_CLASSES` — `comprou_no_topo`, `golpe_do_criador`, `recompra`,
`custo`, `saida_normal` —, e `maior_vazamento`).

> [!alerta] Pontos vazios até a próxima geração
> Em 25/09/2026 as duas únicas fichas em `Fichas/` (`Ficha-2026-09-24.md`, `Ficha-2026-09-25.md`)
> **ainda não têm** esses campos no frontmatter — outro agente está adicionando o
> `day_dataview_lines` ao gerador agora mesmo. Até essas duas fichas serem regeradas (próximo
> deploy do `meme_daily_ficha.py`) os gráficos abaixo aparecem **vazios**, não quebrados. Dias
> gerados a partir do deploy já nascem com o campo e aparecem sozinhos.

## Como ler

- **Resultado líquido por dia** é o `pnl_sol` de cada ficha, em barras — um dia vermelho é dia de
  prejuízo líquido, não uma perda isolada.
- **Resultado acumulado** é a mesma série somada (`accum` do Tracker), a mesma conta que a linha
  "Acumulado (todo o histórico até o fim do dia)" de cada ficha — se divergirem, o gerador da ficha
  está errado, não o gráfico.
- **Taxa de acerto por dia**: o Tracker instalado não teve a sintaxe de expressão
  (`ganhos ÷ operacoes` num único gráfico) confirmada nesta revisão — sem acesso à rede para checar
  a versão instalada contra a documentação, o caminho seguro é plotar `ganhos` e `operacoes` como
  duas linhas separadas; a proporção exata do dia já sai calculada na tabela de 14 dias abaixo. Se
  Everton confirmar que a versão instalada aceita expressão, o gráfico pode ser trocado por um único
  `dvField` — ver `docs/plans/` antes de mexer, é mudança cosmética, não estrutural.
- **SOL perdido por classe por dia** é uma linha por classe de perda — a série que mais sobe é o
  maior vazamento sustentado, mesmo em dias em que `maior_vazamento` (o pior do dia isolado) aponta
  para outra classe.
- Nenhum gráfico soma `Ficha-2026-09-23-mesa-real.md` (ficha manual antiga, fora de `Fichas/`) nem
  `Semana-*.md` (fichas semanais, mesma pasta futura): o `dateFormatPrefix: Ficha-` exige que o
  nome do arquivo *comece* por `Ficha-` seguido direto da data — um arquivo cujo nome não bate esse
  prefixo não tem data extraível e o Tracker o ignora em silêncio, sem precisar de exclusão manual.
  A tabela Dataview usa o mesmo efeito por outra via: só ficha diária tem o campo `dia`.

## Resultado líquido por dia (SOL)

```tracker
searchType: frontmatter
searchTarget: pnl_sol
folder: 03-TRADING/Meme/Fichas
dateFormat: YYYY-MM-DD
dateFormatPrefix: Ficha-
bar:
    title: "Resultado líquido por dia (SOL)"
    yAxisLabel: SOL
    barColor: '#3a86ff'
```

## Resultado acumulado (SOL)

```tracker
searchType: frontmatter
searchTarget: pnl_sol
folder: 03-TRADING/Meme/Fichas
dateFormat: YYYY-MM-DD
dateFormatPrefix: Ficha-
line:
    title: "Resultado acumulado (SOL)"
    yAxisLabel: "SOL acumulado"
    accum: true
    lineColor: '#8338ec'
```

## Taxa de acerto por dia

```tracker
searchType: frontmatter
searchTarget: ganhos, operacoes
folder: 03-TRADING/Meme/Fichas
dateFormat: YYYY-MM-DD
dateFormatPrefix: Ficha-
line:
    title: Ganhos, Operações
    yAxisLabel: contagem
    lineColor: '#2a9d8f', '#e76f51'
```

## SOL perdido por classe, por dia

```tracker
searchType: frontmatter
searchTarget: perdas_comprou_no_topo_sol, perdas_golpe_do_criador_sol, perdas_recompra_sol, perdas_custo_sol, perdas_saida_normal_sol
folder: 03-TRADING/Meme/Fichas
dateFormat: YYYY-MM-DD
dateFormatPrefix: Ficha-
line:
    title: comprou no topo, golpe do criador, recompra, custo, saída normal
    yAxisLabel: "SOL perdido"
    lineColor: '#e63946', '#f4a261', '#e9c46a', '#adb5bd', '#457b9d'
```

## Últimos 14 dias

```dataview
TABLE
  dia AS "Dia",
  operacoes AS "Operações",
  ganhos AS "Ganhos",
  pnl_sol AS "PnL (SOL)",
  maior_vazamento AS "Maior vazamento",
  choice(operacoes > 0, round(ganhos / operacoes * 100, 1) + "%", "—") AS "Taxa de acerto"
FROM "03-TRADING/Meme/Fichas"
WHERE dia
SORT dia DESC
LIMIT 14
```

## Relacionados

[[03-TRADING/Meme/README|Meme — o que uma "estratégia" é aqui]] · pasta `03-TRADING/Meme/Fichas/`
