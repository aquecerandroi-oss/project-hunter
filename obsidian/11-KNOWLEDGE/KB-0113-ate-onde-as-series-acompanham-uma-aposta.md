---
tags: [knowledge, nota, meme, pumpfun, series, cobertura, censura, backtest, instrumentacao, m5]
kb: KB-0113
tema: até onde as séries (15 s, 1 min, fita de pool) acompanham uma moeda depois da entrada — e quanto do R de hoje é censura
data: 2026-09-16
janela_medida: 15/09/2026 00:00–23:59 BRT (um dia, o de maior n)
fonte: banco da VPS (meme_features_15s, meme_features_1m, meme_trades, meme_paper_bets, meme_proposals, meme_tokens), SELECT-only
sql: infra/scripts/sql/research/2026-09-16-r25-q01-cobertura-pos-entrada.sql, ...-r25-q02-apostas-fim-de-serie.sql, ...-r25-q03-custo-de-estender.sql
codigo: services/meme-worker/hunter_meme_worker/fast_lane.py, tracker.py, tracker_types.py, features.py
evidencia: medição própria — 132 entradas da porta atual (REUSE `r20-q01`) e 73 apostas de papel fechadas em 15/09
hipotese_testavel: sim
astra: não consultada (medição de instrumentação)
confiança: ALTA na cobertura medida (é contagem de linhas), MÉDIA na atribuição de motivo
owner: astra-quant
status: vivo
updated: 2026-09-16
---

# KB-0113 — Até onde as séries acompanham uma aposta

Três estudos de hoje bateram no mesmo teto:
[[11-KNOWLEDGE/KB-0110-saida-por-drawdown-20-na-serie-de-15s|KB-0110]] §1b ("a série de 15 s dura 162 s
medianos depois da entrada; 0 de 291 chegam a 30 min"),
[[11-KNOWLEDGE/KB-0107-celula-lenta-como-porta-da-mesa|KB-0107]] §6–7 (horizonte de 30 min sobre 4–5 barras de
1 min) e [[11-KNOWLEDGE/KB-0099-por-que-a-mesa-nao-propoe-e-quanto-custa-cada-criterio|KB-0099]] §3. Esta nota
mede **por que** a série para, **quando** para, e **o que custaria** medir 30 minutos de verdade.

> **Unidades.** `curve_progress_pct` é fração 0–1; `mayhem_mode` é texto. Horários BRT.
> Coorte = as **132 entradas da porta atual em 15/09**, reaproveitando literalmente os blocos
> `foto`/`universo`/`entrada` do `2026-09-16-r20-q01-entradas-porta-atual.sql` (mesma porta, mesmo `ew = 5`).
> As 11 sem nenhuma foto de 15 s depois da entrada são justamente as que a KB-0110 descartou: 132 − 11 = **121**,
> o `n` de 15/09 da tabela §4 dela. A coorte é a mesma, linha por linha.

## 1. Cobertura pós-entrada das três séries (n = 132, 15/09)

Duração = último instante da série dentro de 60 min depois de `t_in`, menos `t_in`.

| série | mediana | p75 | p90 | máx | ≥ 5 min | ≥ 10 min | ≥ 30 min |
|---|---|---|---|---|---|---|---|
| **15 s** (`meme_features_15s`) | **150 s** | 204 s | 241 s | 1 856 s | **4 (3,0 %)** | 2 (1,5 %) | 1 (0,8 %) |
| **1 min** (`meme_features_1m`) | **240 s** | 420 s | 720 s | 3 060 s | **61 (46,2 %)** | 22 (16,7 %) | **4 (3,0 %)** |
| 1 min **com `mcap_sol`** | 240 s | 420 s | 720 s | 3 060 s | 60 (45,5 %) | 21 (15,9 %) | 4 (3,0 %) |
| **fita de pool** (`meme_trades`, `program = 'pump_amm'`) | **0 s** | 0 s | 0 s | **0 s** | **0** | 0 | 0 |

Três leituras diretas:

1. **A série de 15 s é 2,5 minutos.** 150 s medianos — o número de 162 s da KB-0110 (média de 5 dias) se
   confirma no dia de maior `n`. Um horizonte de 30 min medido sobre ela é **97 % censura**.
2. **A série de 1 min é 4 barras.** Ela dura 1,6× mais que a de 15 s, e ainda assim só **3 %** das entradas
   têm as 30 barras que a regra "saída por tempo em 30 min" pressupõe.
3. **A fita de pool não cobre esta coorte: zero.** Ela existe (15/09: 14 965 trades `pump_amm` em 130 mints),
   mas **nenhuma** das 132 entradas registra um único trade de pool nos 60 min seguintes — inclusive as 6 cuja
   curva completou. Marca de pool hoje **não** é continuação de série para quem a porta admite; é outro
   universo de moedas.

### Por que a série de 15 s para

| motivo | n | mediana de cobertura | idade mediana na entrada | idade mediana da última foto |
|---|---|---|---|---|
| **teto da via rápida (`age_s` → 300 s)** | **88 (66,7 %)** | 171 s | 122 s | **292 s** |
| parou antes do teto | 32 (24,2 %) | 145 s | 130 s | **268 s** |
| sem nenhuma foto depois da entrada | 11 (8,3 %) | 0 s | **314 s** | — |
| curva completou / migrou | 1 (0,8 %) | 13 s | 93 s | 105 s |

O motivo é **um só, e é de código, não de mercado**. `fast_lane.young_mints()` seleciona
`timedelta(0) <= now - t.created_at < fast_lane_max_age_s` com `fast_lane_max_age_s = 300`
(`services/meme-worker/hunter_meme_worker/fast_lane.py`) — a moeda sai da via rápida **aos 300 s de vida**,
haja aposta ou não. As 88 do teto param com a última foto aos **292 s**; as 32 "antes do teto" param aos
**268 s** (o mesmo teto, com uma leitura perdida antes). Somadas: **91 % das paradas são o `age_s` 300**.
As 11 sem série entraram aos **314 s** medianos — a via rápida já as havia largado antes do preenchimento.
Nada disso é morte da moeda, retenção, nem migração.

**O corolário que interessa:** a entrada acontece com `age_s` mediano de ~122 s e o teto é 300 s, logo
**a janela máxima observável de qualquer entrada da porta atual é 178 s medianos (≤ 270 s no melhor caso)**.
Alvo 3×, trailing 35 % e tempo 30 min são, por construção do instrumento, **não observáveis** nesta porta.

### Por que a série de 1 min para

| motivo | n | mediana de cobertura | com `mcap_sol` | com fita de pool |
|---|---|---|---|---|
| **saiu do rastreador** | **120 (90,9 %)** | 240 s | 240 s | **0** |
| curva completou / migrou | 6 (4,5 %) | 120 s | 60 s | **0** |
| sem série depois da entrada | 6 (4,5 %) | — | — | 0 |
| ainda viva aos 60 min | 0 | — | — | — |

Aqui o motivo é o **teto do rastreador**: `MintTracker.prune` derruba o excedente de `MEME_TRACKED_MINTS_MAX`
(120) por menor prioridade, e com ~40 mil descobertas/dia a expulsão chega em minutos — 240 s medianos depois
da entrada, exatamente o que a tabela mostra. Retenção **não** é causa hoje (15 s = 7 d, 1 min = 90 d; a série
de 15 s só existe desde 12/09 19:35 UTC, o deploy da T4.16).

**E aqui está a distinção que muda a leitura de tudo:** `prune` **nunca expulsa um mint fixado** (`pin`), e são
fixados os mints com **aposta de papel aberta, posição viva ou proposta esperando decisão** (T4.16b, docstring
do `tracker.py`). A coorte das 132 é **simulada** — nenhuma virou aposta, nenhuma foi fixada, todas foram
expulsas. **A censura de 240 s é artefato da coorte de backtest, não do instrumento vivo** — o §2 mostra o
instrumento vivo funcionando. Para a via rápida, porém, o pin **não ajuda**: `young_mints` filtra por idade e
**ignora o pin**. Esse é o único buraco estrutural.

## 2. As apostas de papel fechadas em 15/09 (n = 73)

| motivo de saída | n | R médio | duração mediana | fechou na última barra existente | `indeterminate` |
|---|---|---|---|---|---|
| `line_broken` | 30 | +0,026 | 93 s | 2 | **0** |
| `creator_dump` | 23 | −0,105 | 139 s | 10 | **0** |
| **`time_stop`** | **11** | **−0,340** | **7 223 s** | **8 (72,7 %)** | **0** |
| `trailing` | 5 | +1,821 | 260 s | 4 | **0** |
| `max_loss` | 4 | −0,549 | 97 s | 1 | **0** |
| **total** | **73** | +0,021 | 139 s | **25 (34,2 %)** | **0** |

"Fechou na última barra existente" = nenhuma observação com preço mais de 90 s **depois** do fecho, olhando
até `exit_at + 35 min`. **8 das 11 saídas por `time_stop` são fim de série disfarçado de saída por tempo.**

**Resposta direta à pergunta do brief: não, o fechamento diário não marca esses casos como `indeterminate`.**
Todas as 73 apostas de 15/09 estão `outcome_quality = 'measured'`, sem exceção. O rótulo `indeterminate`
existe (`0028`, DATABASE.md §41) mas só cobre `rug_no_snapshot` — *"o fecho não pôde ser precificado"*. O caso
desta nota é diferente e **não tem rótulo**: o fecho **foi** precificado, numa observação que por acaso era a
última que existiria. Quanto isso dói:

| motivo de saída | idade mediana da última obs. de 1 min no fecho | p90 | máx |
|---|---|---|---|
| `creator_dump` / `trailing` / `line_broken` | 22–33 s | 38–54 s | 59 s |
| **`time_stop`** | **22 s** | **1 904 s** | **1 930 s** |

O corpo do instrumento vivo está **saudável** (marca de 22 s: o pin funciona). A cauda do `time_stop` está
precificada num retrato de **até 32 minutos antes** — e é essa cauda que paga −0,340 R médio. Duas apostas,
não trinta; mas são as de maior duração, e portanto as que carregam mais R.

## 3. O que precisaria mudar, e o custo em linhas/dia

Base de 15/09: **`meme_features_15s` = 497 360 linhas/dia** (33 580 mints, 14,8 linhas/mint) ·
**`meme_features_1m` = 208 390 linhas/dia** (35 300 mints, 5,9 linhas/mint). Custo por linha medido na
partição de setembro (com índices): **514 B** na de 15 s, **573 B** na de 1 min. Apostas abertas em 15/09: 78
(47 mints); propostas: 261 (**83 mints distintos** — o teto do conjunto fixado).

| # | mudança | onde | custo/dia | Δ |
|---|---|---|---|---|
| **1** | **`young_mints` admitir o conjunto fixado** (aposta/posição/proposta) além da idade < 300 s, até o fecho ou 30 min | `fast_lane.py:72` | 83 mints × 4/min × 30 min ≈ **+9 960 linhas** (≈ 5,1 MB) | **+2,0 %** |
| 1b | idem, mas até 60 min | idem | ≈ **+19 900 linhas** (≈ 10 MB) | +4,0 % |
| **2** | `fast_lane_max_age_s` 300 → 1 800 s para **todos** | `config.py` | teto = 120 mints × 4/min × 1 440 = **691 200 linhas** (≈ 355 MB/dia) | **+39 %** |
| **3** | 1 min seguir a moeda **enquanto houver aposta/proposta** | já existe (pin, T4.16b) | **0** para apostas reais; para medir a coorte simulada seria preciso fixar candidatas | 0 |
| 3b | `MEME_TRACKED_MINTS_MAX` 120 → 240 (para a coorte simulada caber) | `config.py` | teto 240 × 1 440 = **345 600 linhas** (≈ 198 MB/dia) **+ dobro do orçamento de RPC/REST** | +66 % |
| **4** | marcas de pool para as migradas | já existe (`mark_source = 'pool_tape'`) | 0 linhas novas | 0 — **e não resolve nada aqui**: 0 de 132 tiveram fita de pool em 60 min |

**A mudança que paga é a nº 1: +2 % de linhas e nenhum custo de RPC.** A via rápida lê o conjunto rastreado
inteiro (cap 120) com **um `getMultipleAccounts` por 100 mints**: alargar o subconjunto por ~80 mints custa,
no pior caso, uma segunda chamada por leitura — ≤ 16 chamadas/min, dentro do orçamento já declarado na
docstring do `fast_lane.py`. A nº 2 é o inverso: +39 % de linhas para observar 30 min de **toda** moeda
descoberta, incluindo as ~33 mil/dia que ninguém vai negociar.

**Uma trava que ninguém mediu ainda:** a retenção de 15 s é de **7 dias em partição mensal**, então a partição
`2026_09` inteira cai por volta de **08/10**. Qualquer "replay de 90 dias" sobre a série de 15 s é
**impossível por construção** — o protocolo de validação em um dia precisa disso resolvido antes, não depois.

## 4. Conclusão — 4 linhas

1. **O teto é de código e tem nome:** `fast_lane.young_mints` larga a moeda aos **300 s de vida** e ignora o
   pin, então **91 %** das séries de 15 s param aí (última foto aos 292 s), e o rastreador expulsa a moeda
   simulada em **240 s** medianos. Nenhuma saída de horizonte > ~3 min foi observada nesta porta — ela foi
   **imputada**.
2. **O que cai por causa disso:** as tabelas de R da **KB-0110** (S0–S4; "tempo 30 min" é "fim da série" em 226
   de 291) e o "alvo 3×/trailing 35 %" da **KB-0099** §3 e da **KB-0107** §6 medem, em mediana, **2,5–4 min**.
   Releia todo R dessas notas como **"R de uma janela de 2,5–4 min com saída a mercado no fim"** — a ordenação
   entre braços sobrevive (mesma coorte, comparação pareada), **o nível não**.
3. **O que NÃO cai:** as notas que não dependem de horizonte — **KB-0102** (snipers → graduação), **KB-0109**
   (top-10/bundle na foto de entrada) e o diagnóstico da **KB-0108** (dd20 como *detector*, lead de 70 s, todo
   dentro da janela observada). E o instrumento **vivo** está são: apostas reais são fixadas e marcadas com
   22 s de atraso mediano — só a cauda de `time_stop` (p90 = 1 904 s) herda o problema.
4. **Um rótulo está faltando e é barato:** 8 das 11 saídas por `time_stop` de 15/09 são fim de série, e as 73
   apostas do dia saíram **todas** como `measured`. Antes de qualquer conjunto novo de saída (o `dd20_after_15x`
   da KB-0110 §6), duas coisas: **(a)** `young_mints` respeitar o pin (+2 % de linhas), **(b)** um
   `outcome_quality` — ou um motivo dentro dele — para *"fechado por tempo sem observação posterior"*, que hoje
   se apresenta como medida e não é.

## Ligações

[[11-KNOWLEDGE/KB-0110-saida-por-drawdown-20-na-serie-de-15s|KB-0110 (S0–S4, §1b é a origem desta nota)]] ·
[[11-KNOWLEDGE/KB-0107-celula-lenta-como-porta-da-mesa|KB-0107 (horizonte de 30 min na série de 1 min)]] ·
[[11-KNOWLEDGE/KB-0099-por-que-a-mesa-nao-propoe-e-quanto-custa-cada-criterio|KB-0099 (metodologia de R)]] ·
[[11-KNOWLEDGE/KB-0108-anatomia-da-morte-depois-da-porta|KB-0108 (dd20 como detector — sobrevive)]] ·
[[11-KNOWLEDGE/KB-0102-snipers-pagam-em-R-ou-so-em-graduacao|KB-0102]] ·
[[11-KNOWLEDGE/KB-0109-top10-e-bundle-onde-o-teto-deveria-estar|KB-0109]] ·
`infra/scripts/sql/research/2026-09-16-r25-q0{1,2,3}-*.sql` ·
`services/meme-worker/hunter_meme_worker/fast_lane.py` · `tracker.py`
