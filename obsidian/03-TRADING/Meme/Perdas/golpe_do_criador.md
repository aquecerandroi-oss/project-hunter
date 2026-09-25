---
tags: [trading, meme, perda, classe, golpe_do_criador]
tipo: consolidado
hipotese: H-015
variavel: sol_no_slot_de_criacao (refutada como filtro)
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: nenhuma medida aprovada até 25/09; H-014 e H-015 refutaram as duas tentativas feitas
classe_de_perda: golpe_do_criador
mercado: meme
status: vivo
owner: sexta-feira
updated: 2026-09-25
---

# `golpe_do_criador` — a saída por despejo do criador ou por venda coordenada em bloco

## Definição exata (T4.92, `infra/scripts/meme_daily_ficha_classify.py`)

Regra 2 de 5 (checada só se a `comprou_no_topo` não disparou — ver [[comprou_no_topo]]). Dispara por
**qualquer um** dos dois motivos:

> 1. O motivo de saída registrado **é** `creator_dump` (o executor identificou a venda do criador e
>    saiu por evento).
> 2. **Ou** a cadeia mostra **10 ou mais vendedores distintos** pousando **no mesmo slot** enquanto a
>    posição estava aberta — um despejo coordenado, não venda orgânica, mesmo que o motivo de saída
>    registrado tenha sido outro (ex.: `trailing` tocou primeiro).

```python
if inputs.exit_reason == "creator_dump":
    return "golpe_do_criador"
if (
    inputs.distinct_sellers_one_slot is not None
    and inputs.distinct_sellers_one_slot >= _CREATOR_DUMP_SELLERS_THRESHOLD  # = 10
):
    return "golpe_do_criador"
```

`distinct_sellers_one_slot` ausente (`None`) pula a segunda checagem sem presumir — a posição só
recebe esta classe pelo `exit_reason` nesse caso.

## Origem e o que já se mediu

O caso de origem da linha de pesquisa é a perda real `SIMFTR` (23/09/2026 19:05 BRT, −0,0284 SOL,
−40,2 %): **73 carteiras distintas venderam no mesmo slot** e o preço caiu à metade num bloco só,
com o criador entre elas. A [[Fila de Hipoteses|H-014]] testou se essas vendedoras compartilhavam um
financiador comum (`rede_financiadora_pct`) — **NÃO CONFIRMA**: os 4 casos de origem (`SIMFTR`,
`CITIZEN`, `WAVECOREE`, `RHOS`) têm rede de 0–1,4 %, e a medida de primeiro financiador comum não
sustentou a previsão ([[KB-0156-o-despejo-em-bloco-nao-e-uma-rede-de-financiamento]]). A pista
exploratória que sobrou — SOL comprado no **slot de criação** — virou a
[[Fila de Hipoteses|H-015]], testada em população nova e **REFUTA**: o teto no tercil alto mataria
36,5 % das vencedoras ([[KB-0158-recompra-sem-amostra-e-bundle-sem-filtro]]).

## Custo medido, pelas fichas existentes

Só existem duas fichas diárias automáticas até agora ([[Ficha-2026-09-24]],
[[Ficha-2026-09-25]]; o gerador nasceu na T4.92, 24/09/2026).

| dia | n | SOL |
|---|---:|---:|
| [[Ficha-2026-09-24\|24/09]] | 1 (`FREAKY`) | −0,0072 |
| [[Ficha-2026-09-25\|25/09]] | 1 (`PUMPAGENT`) | −0,0070 |
| **soma dos 2 dias** | **2** | **−0,0142** |

Amostra pequena demais para qualquer leitura de tendência — só a soma exata dos dois dias existentes,
sem extrapolação.

**Consulta viva (Dataview), desde `infra/scripts/meme_daily_ficha_frontmatter.py`
(commit `53a1295e`):**

```dataview
TABLE
  perdas_golpe_do_criador_n AS "n",
  perdas_golpe_do_criador_sol AS "SOL"
FROM "03-TRADING/Meme/Fichas"
WHERE dia
SORT dia ASC
```

`WHERE dia` restringe a fichas **diárias** — as semanais (`Semana-*.md`) carregam
`semana_inicio`/`semana_fim` em vez de `dia` e ficam fora de propósito. [[Ficha-2026-09-24|24/09]] e
[[Ficha-2026-09-25|25/09]] só aparecerão aqui depois de regeradas pelo próximo deploy — o
frontmatter delas ainda não tem `perdas_golpe_do_criador_n`/`_sol`; a tabela estática acima continua
sendo a fonte até lá.

## Hipóteses que atacaram esta classe

| Hipótese | O que tentou | Veredito |
|---|---|---|
| [[Fila de Hipoteses#H-014 — Rede coordenada de compradores (o golpe em um bloco só)\|H-014]] | achar se as vendedoras do despejo compartilham financiador (`rede_financiadora_pct`) | **NÃO CONFIRMA** — nos 4 casos de origem, rede 0–1,4 % ([[KB-0156-o-despejo-em-bloco-nao-e-uma-rede-de-financiamento]]) |
| [[Fila de Hipoteses#H-015 — Compra no slot de criação (o "bundle" do lançamento)\|H-015]] | usar SOL comprado no slot da criação como filtro de entrada | **REFUTA** pela cláusula (c) — teto mataria 36,5 % das vencedoras ([[KB-0158-recompra-sem-amostra-e-bundle-sem-filtro]]) |

**O que continua sem resposta:** nenhuma medida pré-decisão prevê o despejo coordenado. O teto de
concentração (`max_top10_share`) existe no código e nunca foi configurado nas mesas reais — ver
[[Fila de Hipoteses#H-010 — Concentração do maior comprador (o dono que pode afundar)|H-010]], que
morreu por limite de dado antes mesmo de chegar ao contrafactual do teto.

## Relacionado

[[Mapa de Estrategias]] · [[Dicionario de Variaveis]] · [[Fila de Hipoteses]] · [[Perdas/Index|Perdas]] ·
[[KB-0149-o-que-a-mesa-real-ensinou]] · [[KB-0156-o-despejo-em-bloco-nao-e-uma-rede-de-financiamento]] ·
[[KB-0158-recompra-sem-amostra-e-bundle-sem-filtro]] · [[Ficha-2026-09-24]] · [[Ficha-2026-09-25]]
