---
tags: [trading, meme, perda, classe, comprou_no_topo]
tipo: consolidado
hipotese: H-019
variavel: aceleracao_compra (não separa a classe: R79)
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: nenhuma hipótese ativa ataca esta classe hoje (H-016, H-017, H-019 tentaram e não fecharam a favor)
classe_de_perda: comprou_no_topo
mercado: meme
status: vivo
owner: sexta-feira
updated: 2026-09-25
---

# `comprou_no_topo` — o maior vazamento da mesa real

## Definição exata (T4.92, `infra/scripts/meme_daily_ficha_classify.py`)

Regra 1 de 5, primeira a ser checada — **se ela dispara, nenhuma das outras é avaliada** (uma
posição só recebe uma classe, a primeira que casar):

> `high_water_sol` (o pico de valor da posição, em SOL) **nunca subiu acima** de `cost_sol` (o
> custo de entrada). A entrada em si já foi o topo local — não houve, em nenhum instante, um
> "estava ganhando e devolveu"; a posição só perdeu, do primeiro segundo ao último.

Em código:

```python
if inputs.high_water_sol is not None and inputs.high_water_sol <= inputs.cost_sol:
    return "comprou_no_topo"
```

Quando `high_water_sol` é `None` (a marcação a mercado não foi registrada), a regra é **pulada**,
nunca presumida — a posição cai para a próxima regra da ordem (`golpe_do_criador` →
`recompra` → `custo` → `saida_normal`). "Subiu depois da compra?" é a mesma pergunta, ao contrário
(`rose_after_buy`), usada como coluna informativa da ficha diária ("subiu depois?").

## Por que é o maior vazamento

[[KB-0149-o-que-a-mesa-real-ensinou]] (item 16, anatomia das 96 posições reais de 16–23/09) já
tinha achado que **34 das 67 perdas nunca passaram do custo** — a porta compra quando o fluxo está
no auge, que é quando o preço está no topo local. A [[Fila de Hipoteses|H-019]] (origem: a ficha
automática mostrou **46 operações e −0,58 SOL em 19–25/09**, mais do que o prejuízo líquido da
semana inteira) tentou achar a variável que prevê essa classe **antes** da compra
(`aceleracao_compra`, o ritmo dos últimos 10 s contra o minuto) e **refutou pela cláusula (c)**: o
piso no tercil baixo mataria 34,7 % das vencedoras, e o sinal saiu **ao contrário** da tese
(desacelerar rendeu mais, não menos) — ver [[KB-0159-a-desaceleracao-nao-avisa-o-topo]].

## Custo medido, pelas fichas existentes

Só existem duas fichas diárias automáticas até agora ([[Ficha-2026-09-24]],
[[Ficha-2026-09-25]] — o gerador (`infra/scripts/meme_daily_ficha.py`) nasceu na T4.92, 24/09/2026;
não há histórico anterior a classificar).

| dia | n | SOL | fração do prejuízo líquido do dia |
|---|---:|---:|---|
| [[Ficha-2026-09-24\|24/09]] | 10 | **−0,1550** | dia fechou em −0,1194 (líquido); a classe sozinha é maior que o prejuízo do dia — os ganhos do dia (3) compensaram parte dela |
| [[Ficha-2026-09-25\|25/09]] | 10 | **−0,1092** | dia fechou em **+0,0328** (primeiro dia verde) — apesar da classe continuar a maior fonte de perda bruta |
| **soma dos 2 dias** | **20** | **−0,2642** | maior classe de perda em ambos os dias |

Não há uma "média semanal" defensável com 2 dias de amostra — a tabela acima é a soma exata, sem
extrapolação.

**Consulta viva (Dataview), desde `infra/scripts/meme_daily_ficha_frontmatter.py`
(commit `53a1295e`):**

```dataview
TABLE
  perdas_comprou_no_topo_n AS "n",
  perdas_comprou_no_topo_sol AS "SOL"
FROM "03-TRADING/Meme/Fichas"
WHERE dia
SORT dia ASC
```

`WHERE dia` restringe a fichas **diárias** (`Ficha-AAAA-MM-DD.md`) — as semanais (`Semana-*.md`,
mesma pasta) carregam `semana_inicio`/`semana_fim` em vez de `dia` e ficam fora desta tabela de
propósito. As duas fichas de [[Ficha-2026-09-24|24/09]] e [[Ficha-2026-09-25|25/09]] só aparecerão
aqui depois de regeradas pelo próximo deploy do `meme_daily_ficha.py`: o frontmatter delas ainda não
tem `perdas_comprou_no_topo_n`/`_sol` — a tabela estática acima continua sendo a fonte até lá.

## Hipóteses que atacaram esta classe

| Hipótese | O que tentou | Veredito |
|---|---|---|
| [[Fila de Hipoteses#H-016 — Entrar no recuo, não no pico (esperar a primeira correção depois do sinal)\|H-016]] | esperar um recuo de X % depois do sinal antes de comprar, para não comprar exatamente no pico | **REFUTA** — as moedas que não recuam são as vencedoras; não entrar custa mais do que comprar no topo ([[KB-0157-esperar-o-recuo-nao-paga]]) |
| [[Fila de Hipoteses#H-017 — Recuo pequeno como melhora de preço (coorte nova, braço de papel)\|H-017]] | recuo pequeno (3 %/60 s) como melhora de **preço** de entrada, não como filtro | **LIMITE DE DADO** (R79, 25/09): 39 decisões emparelhadas contra o mínimo de 150; braço `recuo_v1/1` seguindo em papel ([[EXP-M24-entrada-no-recuo]]) |
| [[Fila de Hipoteses#H-019 — Fluxo desacelerando na hora da compra (o topo local visto pela fita de 10 s)\|H-019]] | prever a classe pela forma do minuto (`aceleracao_compra`) antes da compra | **REFUTA** pela cláusula (c) — piso mataria vencedoras demais, sinal ao contrário ([[KB-0159-a-desaceleracao-nao-avisa-o-topo]]) |

**O que continua sem resposta:** nenhuma variável medida até 25/09/2026 separa, antes da compra, a
moeda que vai virar `comprou_no_topo` da que vai subir. As 13 variáveis de decisão do R65 já estavam
esgotadas ([[KB-0149-o-que-a-mesa-real-ensinou]] §3), e as três tentativas específicas contra esta
classe (H-016, H-017, H-019) ou refutaram ou ainda não têm amostra.

## Relacionado

[[Mapa de Estrategias]] · [[Dicionario de Variaveis]] · [[Fila de Hipoteses]] · [[Perdas/Index|Perdas]] ·
[[KB-0149-o-que-a-mesa-real-ensinou]] · [[KB-0157-esperar-o-recuo-nao-paga]] ·
[[KB-0159-a-desaceleracao-nao-avisa-o-topo]] · [[Ficha-2026-09-24]] · [[Ficha-2026-09-25]]
