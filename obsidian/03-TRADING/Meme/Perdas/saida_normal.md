---
tags: [trading, meme, perda, classe, saida_normal]
tipo: consolidado
hipotese: —
variavel: —
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: nenhuma hipótese ativa mira esta classe (ela é, por definição, o que sobra)
classe_de_perda: saida_normal
mercado: meme
status: vivo
owner: sexta-feira
updated: 2026-09-25
---

# `saida_normal` — perda de mercado comum, sem padrão detectado

## Definição exata (T4.92, `infra/scripts/meme_daily_ficha_classify.py`)

Regra 5 de 5 — o que **sobra** depois de `comprou_no_topo`, `golpe_do_criador`, `recompra` e
`custo` não terem disparado (ver as quatro páginas irmãs em [[Perdas/Index|Perdas]]):

```python
return "saida_normal"
```

Uma posição cai aqui quando: o preço **subiu** depois da entrada (não é `comprou_no_topo`) mas
**devolveu** o suficiente para fechar no vermelho, o motivo de saída não foi `creator_dump` nem
houve despejo coordenado (não é `golpe_do_criador`), não foi uma reentrada em até 300 s (não é
`recompra`) e a perda é **maior** que o custo de ida e volta (não é `custo`). É a classe residual —
não tem regra própria, e por isso não tem hipótese própria: qualquer hipótese que reduza uma das
outras quatro classes desloca posições **para** ou **para fora** de `saida_normal`, nunca a ataca
diretamente.

## Custo medido, pelas fichas existentes

| dia | n | SOL |
|---|---:|---:|
| [[Ficha-2026-09-24\|24/09]] | 2 | −0,0012 |
| [[Ficha-2026-09-25\|25/09]] | 8 | −0,0561 |
| **soma dos 2 dias** | **10** | **−0,0573** |

Nos dois dias existentes, `saida_normal` é a segunda maior fonte de perda depois de
[[comprou_no_topo]], mas por uma margem grande (−0,0573 contra −0,2642 SOL de `comprou_no_topo` na
soma dos mesmos 2 dias) — coerente com o achado de longa data de que a saída da mesa (alvo 1,15× /
trailing 10 % / 300 s) **já é a melhor de 52 variantes testadas** ([[KB-0149-o-que-a-mesa-real-ensinou]]
item 6, R64) e que mexer nela (recuo mais largo, segurar mais tempo) piora — não a entrada.

**Consulta viva (Dataview), desde `infra/scripts/meme_daily_ficha_frontmatter.py`
(commit `53a1295e`):**

```dataview
TABLE
  perdas_saida_normal_n AS "n",
  perdas_saida_normal_sol AS "SOL"
FROM "03-TRADING/Meme/Fichas"
WHERE dia
SORT dia ASC
```

`WHERE dia` restringe a fichas **diárias** — as semanais (`Semana-*.md`) carregam
`semana_inicio`/`semana_fim` em vez de `dia`. [[Ficha-2026-09-24|24/09]] e [[Ficha-2026-09-25|25/09]]
só aparecerão aqui depois de regeradas pelo próximo deploy — o frontmatter delas ainda não tem
`perdas_saida_normal_n`/`_sol`; a tabela estática acima continua sendo a fonte até lá.

## Por que esta classe não tem, e talvez não deva ter, uma hipótese própria

A saída já foi extensamente testada e nada bateu a regra atual: recuo 15 %/20 %/30 % perde mais
(−0,176/−0,188/−0,148), armar só depois de +10 %/+20 % também perde, e "segurar 5 minutos" teria
dado −0,40 SOL nas mesmas 24 operações medidas no R64 ([[KB-0149-o-que-a-mesa-real-ensinou]] itens
7–8). A tensão que continua **sem resposta**, e que é o motivo de `saida_normal` continuar existindo
como classe residual: **o mesmo recuo apertado que protege das drenagens custa as explosões** — o
dinheiro ficou em cima da mesa em pelo menos três casos (`XCrypto`, `NARKY#1`, `FЕРЕ`, que foram a
+139 %, +139 % e +55 % depois de o recuo tirar a mesa a −2…−14 %). Nenhuma hipótese pré-registrada
ataca essa tensão hoje.

## Relacionado

[[Mapa de Estrategias]] · [[Dicionario de Variaveis]] · [[Fila de Hipoteses]] · [[Perdas/Index|Perdas]] ·
[[KB-0149-o-que-a-mesa-real-ensinou]] · [[comprou_no_topo]] · [[golpe_do_criador]] · [[recompra]] ·
[[custo]] · [[Ficha-2026-09-24]] · [[Ficha-2026-09-25]]
