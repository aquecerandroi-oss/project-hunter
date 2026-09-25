---
tags: [trading, meme, perda, classe, recompra]
tipo: consolidado
hipotese: H-018
variavel: recompra (nova entrada no mesmo mint <= 300s depois de uma saída com lucro)
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: reabrir H-018 com 20 recompras reais (ETA 4-9 dias ao ritmo de 25/09)
classe_de_perda: recompra
mercado: meme
status: vivo
owner: sexta-feira
updated: 2026-09-25
---

# `recompra` — reentrar no mesmo mint logo depois de uma saída

## Definição exata (T4.92, `infra/scripts/meme_daily_ficha_classify.py`)

Regra 3 de 5 (checada só se `comprou_no_topo` e `golpe_do_criador` não dispararam — ver
[[comprou_no_topo]] e [[golpe_do_criador]]):

> O mesmo mint foi reentrado até **300 s** depois de uma saída **anterior de qualquer operador**
> (a mesma janela da pausa por mint da T4.78).

```python
_RECOMPRA_WINDOW = timedelta(seconds=300)
if inputs.since_prior_exit is not None and inputs.since_prior_exit <= _RECOMPRA_WINDOW:
    return "recompra"
```

**Ordem importa, e ela esconde o tamanho real desta classe na ficha automática.** Como
`comprou_no_topo` é checada primeiro, uma recompra cujo pico nunca passou do custo — o caso mais
comum, porque comprar um mint que acabou de despejar tende a continuar caindo — sai classificada
como `comprou_no_topo`, não como `recompra`, mesmo tendo nascido de uma recompra. É por isso que as
duas fichas existentes ([[Ficha-2026-09-24]], [[Ficha-2026-09-25]]) mostram **0 linhas** na tabela
`## A classe de perda automática` com a etiqueta `recompra`, apesar de a mesa real ter tido
recompras perdedoras nos dois dias (ver abaixo). A classificação por regra de precedência única é
exatamente o desenho do T4.92 (primeira regra que casa vence); o efeito colateral é que **esta
página não pode usar a tabela de classes das fichas como medida do custo da recompra** — usa a
medição direta da H-018.

## O que a H-018 mediu diretamente

Origem: a perda real `Megawatt` (24/09/2026 04:38 BRT) — a mesa vendeu no alvo (+0,0160, 4 s de
posição) e **recomprou o mesmo mint 5 s depois**, 22 % mais caro; a segunda posição perdeu **−0,0519
(−78,7 %)**. A pausa de 300 s da T4.78 só vale depois de **perda**; recompra depois de **ganho**
nunca tinha sido medida.

**Veredito ([[Fila de Hipoteses#H-018 — Recompra do mesmo mint logo depois de um ganho|H-018]],
R78, 25/09/2026): LIMITE DE DADO nas duas populações — registrado, não julgado.**
[[KB-0158-recompra-sem-amostra-e-bundle-sem-filtro]]:

| | reais | papel |
|---|---:|---:|
| recompras encontradas | **10** | 5 |
| perderam | **9** | — |
| soma | **−0,118 SOL** | — |
| D contra as primeiras entradas | **−0,134** [IC −0,305, +0,003] | −0,060 [−0,458, +0,215] |
| perda ≥ 50 % | 1,89× a taxa das primeiras entradas | — |

A refutação da fila (limite superior do IC acima de −0,01 por SOL) **não dispara na leitura
literal** (dispara só na sensibilidade "lucro por qualquer razão"), mas com **10 casos contra o
mínimo de 20**, o resultado é registrado como limite de dado, não julgado. Contrafactual real: uma
pausa de 300 s **depois de qualquer saída** (não só depois de perda, como a T4.78 já faz) bloquearia
9 recompras a mais que a regra atual, **Δ +0,117 SOL**, com 1 vencedora morta (`KODA`).

## O que o diário de 25/09 já registrou como custo do dia

[[09-OPERATIONS/Diario/2026-09-25|Diário de 25/09]]: quatro recompras no mesmo minuto — `CALLS`
(op6 ganha, op5 perde), `007` (op5 ganha, op6 perde), `Calcios` (op5 ganha 07:35, op5 perde 07:38),
`BAGI` (op5 ganha 11:11, op6 perde 11:12) — **as quatro segundas entradas somam −0,041 SOL; sem
elas o dia teria fechado em +0,077 SOL** em vez dos +0,0328 registrados. Duas delas são recompra
**cruzada** entre `operator/5` e `operator/6`, um caso que a pausa por mint de um único operador não
bloquearia.

## Hipóteses que atacaram esta classe

| Hipótese | O que tentou | Veredito |
|---|---|---|
| [[Fila de Hipoteses#H-018 — Recompra do mesmo mint logo depois de um ganho\|H-018]] | medir se a recompra depois de um **ganho** rende menos que as primeiras entradas | **LIMITE DE DADO** (10 casos reais, mínimo é 20) ([[KB-0158-recompra-sem-amostra-e-bundle-sem-filtro]]) |

Precedente já aplicado à mesa (não é hipótese, é regra em produção): R64 mediu **19 recompras em
papel depois de **perda**, 0 acertos, −0,338 SOL**, o que virou a pausa de 300 s da T4.78 — ver
[[KB-0149-o-que-a-mesa-real-ensinou]] item 18. A T4.78 cobre recompra-depois-de-perda; a H-018 é
sobre recompra-depois-de-**ganho**, ainda sem regra.

## Relacionado

[[Mapa de Estrategias]] · [[Dicionario de Variaveis]] · [[Fila de Hipoteses]] · [[Perdas/Index|Perdas]] ·
[[KB-0149-o-que-a-mesa-real-ensinou]] · [[KB-0158-recompra-sem-amostra-e-bundle-sem-filtro]] ·
[[Ficha-2026-09-24]] · [[Ficha-2026-09-25]] · [[09-OPERATIONS/Diario/2026-09-24|Diário 24/09]] ·
[[09-OPERATIONS/Diario/2026-09-25|Diário 25/09]]
