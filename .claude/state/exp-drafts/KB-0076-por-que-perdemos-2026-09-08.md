---
tags: [knowledge, nota, custos, estrategias, shadow-lab, diagnostico]
tema: "Custos, edge e o R que sobra: por que as versões do Lab perdem"
fonte: "Dado próprio da VPS (`signal_outcomes`, `agent_signals`, `candles`), lido numa única transação REPEATABLE READ / READ ONLY; SQL verbatim em `infra/scripts/sql/research/2026-09-08-*.sql`; replays de política de saída com `infra/scripts/replay_exits.py`"
fonte_url: ""
lido_em: 2026-09-08
as_of: 2026-09-08T15:00:00Z
read_at: 2026-09-08T15:47:00Z
evidencia: "medição própria sobre 4 472 desfechos hipotéticos em 10 populações (2 estratégias, 6 versões, 5 coortes) + 4 corridas de replay de política de saída"
hipotese_testavel: sim
astra: pendente
status: rascunho
owner: sexta-feira
updated: 2026-09-08
confiança: "?"
---

# Por que perdemos: o custo em R é praticamente toda a perda

> **Rascunho da T3.32 para arquivamento pela Sexta-feira.** Nada aqui é dinheiro real
> (`ENABLE_LIVE_TRADING=false`, autonomia desligada). As cifras em USDT são a conversão declarada do
> Lab: 0,25 % de risco sobre 19 333 USDT = **48,33 USDT por 1 R**.
> **Corte (`as_of`): `agent_signals.emitted_at < 2026-09-08T15:00:00Z`**, embutido em cada consulta;
> **leitura (`read_at`): 2026-09-08T15:47Z**, as nove consultas numa transação só
> (`begin transaction isolation level repeatable read read only`) para que todas as tabelas desta
> nota compartilhem **um** snapshot. O corte fixa a **emissão**, não a **resolução**: o Lab continua
> resolvendo acompanhamentos abertos, então uma releitura devolve `n` maiores.

## O que afirma

**Todas as versões perdem por um motivo aritmético antes de perderem por um motivo de mercado.**
Em cada uma das dez populações medidas a expectancy **bruta** (antes de qualquer custo, com o mesmo
denominador de risco) fica entre **−0,282 R e +0,169 R** — e entre **−0,040 R e +0,089 R** se
excluídas as duas populações com n < 30 —, enquanto o **custo assumido por operação** vale entre
**0,107 R e 0,615 R**. A perda líquida é, com boa aproximação, o custo.

E o custo não é uma correlação: é uma **identidade**, verificada linha a linha
(`2026-09-08-09-identidade-do-custo.sql`):

```
custo_R = 0,0020 / (risco_inicial / preço_de_entrada)
```

porque a hipótese de custo do Lab (`spread 2 bps` + `slippage 5 bps/lado` + `fee 4 bps/lado`) soma
**20 bps de ida e volta** e o R é medido em `P_entry − stop`. O produto `custo_R × risco%` deu
**0,001998 a 0,002001** nas dez populações, com desvio-padrão entre 5,2×10⁻⁶ e 1,9×10⁻⁵.

A frase que resume a nota: **um stop de 1 % do preço custa 0,20 R por operação; um stop de 0,25 %
do preço custa 0,80 R por operação.** A `volume_anomaly` põe o stop na mínima da barra do pico, sem
piso (`volume_anomaly_v1.py:183`) — mediana de risco **0,406 % do preço** na janela de replay — e
por isso paga **0,615 R de custo por operação**, mais do que perde no total.

## Os números (cada tabela com a consulta que a produziu)

### 1. Bruto contra líquido — `2026-09-08-03-custo-vs-edge.sql`

| versão | coorte | n | expect. **bruta** (R) | **custo** (R) | funding (R) | expect. **líquida** (R) | Σ R | USDT | PF líq. | PF **bruto** | risco % do preço (mediana) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| momentum v1 | prospective | 929 | −0,0399 | 0,1506 | 0,00005 | −0,1905 | −176,94 | −8 551,30 | 0,613 | 0,900 | 1,401 |
| momentum v2 | prospective | 195 | −0,0166 | 0,1457 | 0,00048 | −0,1628 | −31,75 | −1 534,39 | 0,675 | 0,959 | 1,436 |
| momentum v2 | replay:7598d6c4 | 23 | −0,2816 | 0,3248 | 0 | −0,6064 | −13,95 | −674,09 | 0,197 | 0,455 | 0,659 |
| momentum v2 | replay:f8d8279c | 222 | **+0,0811** | 0,2524 | 0,00038 | −0,1717 | −38,13 | −1 842,64 | 0,645 | 1,241 | 0,788 |
| momentum v3 (paper) | prospective | 176 | −0,0392 | 0,1461 | 0,00053 | −0,1859 | −32,72 | −1 581,39 | 0,635 | 0,906 | 1,429 |
| momentum v4 (piso 0,0089) | prospective | **25** | +0,1687 | 0,1065 | 0 | **+0,0622** | +1,55 | +75,13 | 1,176 | 1,547 | 1,863 |
| momentum v4 | replay:d9f7a1f8 | 30 | −0,0185 | 0,1315 | 0,00062 | −0,1506 | −4,52 | −218,38 | 0,722 | 0,960 | 1,647 |
| volume_anomaly v1 | prospective | 2 079 | +0,0094 | 0,3397 | −0,00022 | −0,3301 | −686,21 | −33 164,75 | 0,534 | 1,021 | 0,904 |
| volume_anomaly v2 | prospective | 456 | +0,0886 | 0,3185 | 0,00034 | −0,2302 | −104,98 | −5 073,76 | 0,637 | 1,218 | 0,867 |
| volume_anomaly v2 | replay:bac27c12 | 337 | +0,0197 | **0,6152** | 0,00027 | −0,5957 | −200,76 | −9 702,89 | 0,280 | 1,054 | 0,406 |

Leitura: **PF bruto entre 0,90 e 1,24** nas populações com n ≥ 175 — cara ou coroa. **PF líquido
entre 0,28 e 0,68** — a mesma moeda com uma taxa por arremesso. `momentum v4` prospective é o único
positivo e tem **25 desfechos**: `inconclusivo` por contrato ([[SHADOW-LAB]] §9), e o **mesmo v4**
dá −0,1506 R no replay de 30. A coorte `replay:7598d6c4` é a corrida gêmea de `f8d8279c` **antes**
do backfill de funding (201 das 224 sem `R_net`): entra na tabela para mostrar que 23 sobreviventes
não são população, não como resultado.

O funding **não é a causa**: entre −0,0002 R e +0,0006 R por operação em todas as populações, mil
vezes menor que o custo de execução. [[KB-0019]]/[[KB-0021]] ficam confirmadas na direção "funding é
pequeno nesta janela", não refutadas.

### 2. O dinheiro por operação — `2026-09-08-09-identidade-do-custo.sql`

| versão | coorte | n | `custo_R × risco%` | desvio | custo USDT/op | resultado USDT/op | resultado USDT total |
|---|---|---:|---:|---:|---:|---:|---:|
| momentum v1 | prospective | 929 | 0,002000 | 1,7e−5 | 7,28 | **−9,20** | −8 551,30 |
| momentum v2 | prospective | 195 | 0,002000 | 1,9e−5 | 7,04 | −7,87 | −1 534,39 |
| momentum v2 | replay:f8d8279c | 222 | 0,002000 | 8,1e−6 | 12,20 | −8,30 | −1 842,64 |
| momentum v3 | prospective | 176 | 0,001999 | 1,8e−5 | 7,06 | −8,99 | −1 581,39 |
| momentum v4 | prospective | 25 | 0,001999 | 1,9e−5 | 5,15 | +3,01 | +75,13 |
| momentum v4 | replay:d9f7a1f8 | 30 | 0,001998 | 1,5e−5 | 6,35 | −7,28 | −218,38 |
| volume_anomaly v1 | prospective | 2 079 | 0,002000 | 1,4e−5 | **16,42** | **−15,95** | −33 164,75 |
| volume_anomaly v2 | prospective | 456 | 0,002001 | 1,5e−5 | 15,39 | −11,13 | −5 073,76 |
| volume_anomaly v2 | replay:bac27c12 | 337 | 0,002000 | 6,0e−6 | 29,73 | −28,79 | −9 702,89 |

O `−9,20` e o `−15,95` são exatamente os números que a página do Lab mostra ao Everton — a
reconstrução fecha com a fonte. E ao lado de cada um está o custo: 7,28 e 16,42 USDT.
**A `volume_anomaly v1` pagou mais de custo por operação (16,42) do que perdeu (15,95).**

### 3. Onde o dinheiro vai, por motivo de saída — `2026-09-08-01-por-motivo-de-saida.sql`

`momentum v2`, coorte `replay:f8d8279c` (222 avaliáveis):

| motivo | n | % | R líq. médio | Σ R | R **bruto** médio | custo R | duração (min) |
|---|---:|---:|---:|---:|---:|---:|---:|
| stop | 45 | 20,1 | −1,1883 | −53,47 | −0,9190 | 0,2692 | 40 |
| invalidação | 82 | 36,6 | −0,6462 | −52,34 | −0,3956 | 0,2478 | 27 |
| horizonte (timeout) | 6 | 2,7 | −0,1176 | −0,71 | +0,1530 | 0,2661 | 240 |
| alvo | 91 | 40,6 | +0,7599 | +68,39 | +1,0027 | 0,2477 | 43 |

`volume_anomaly v2`, coorte `replay:bac27c12` (337 avaliáveis):

| motivo | n | % | R líq. médio | Σ R | R bruto médio | custo R | duração (min) |
|---|---:|---:|---:|---:|---:|---:|---:|
| invalidação | 146 | 42,8 | −1,0104 | −147,53 | −0,4289 | **0,5810** | 20 |
| stop | 77 | 22,6 | −1,6151 | −124,37 | −0,7361 | **0,8789** | 17 |
| horizonte | 15 | 4,4 | −0,1060 | −1,59 | +0,2900 | 0,3971 | 120 |
| alvo | 99 | 29,0 | +0,7345 | +72,72 | +1,2284 | 0,4937 | 26 |

**As duas células que explicam a perda são `stop` e `invalidação`**: juntas somam −105,81 R em
`momentum` (o alvo devolve +68,39 e o líquido fica −38,13) e −271,90 R em `volume_anomaly` (o alvo
devolve +72,72; líquido −200,76). Repare na coluna bruta: um stop da `volume_anomaly` perde
**−0,74 R brutos** e é debitado **−1,62 R líquidos** — o preço não andou 1 R contra nós, o custo é
que empurrou o resultado para lá. Um alvo rende +1,23 R brutos e credita +0,73 R.

Não há **nenhum** desfecho `censored` em toda a base, e `no_entry` fica ≤ 3,3 % em qualquer
população: a perda é de operações que aconteceram, não de acompanhamento perdido.

### 4. O decil de ATR — `2026-09-08-05-decis-de-atr.sql`

- `volume_anomaly v2 / replay:bac27c12`: os **cinco decis de menor ATR%** (ATR ≤ 0,346 % do preço,
  risco 0,22–0,41 %) somam **−155,75 R de −200,76 R — 78 % da perda** — com custo entre 0,64 e
  1,07 R por operação. Os cinco maiores somam −45,01 R.
- `momentum v2 / prospective`: os cinco decis de menor ATR (≤ 0,971 %) somam **−32,56 R**, ou seja
  **mais do que a perda inteira** (−31,75 R): a metade superior devolve +0,80 R no conjunto.
- Nenhum decil é consistentemente positivo entre as duas coortes: o melhor de `momentum v2`
  prospective é o decil 6 (+2,44 R em 19), o melhor de `volume_anomaly` replay é o decil 7
  (+8,07 R em 34), e eles não coincidem em faixa de ATR.

### 5. Não é hora, não é dia, não é regime

- **Hora de Brasília** (`2026-09-08-06`): `volume_anomaly v2 / replay` é negativa em **24 das 24
  horas**. `momentum v2 / replay` é negativa em 16 de 24, e nenhuma hora tem n ≥ 25.
- **Dia** (`2026-09-08-06`): `volume_anomaly` perde em **25 dos 28 dias**; `momentum` em 21 de 24.
  O pior dia da `momentum` (2026-08-24, −15,02 R em 24 operações) sozinho é 39 % da perda da coorte.
- **Regime** (`2026-09-08-07`): **`market_regimes` tem uma única linha, `UNKNOWN`**, e os 3 040
  sinais com `regime_id` apontam todos para ela. O classificador do [[PIPELINE]] §4 nunca produziu
  série — hoje **não existe** filtro de regime para ligar. Reconstruindo do BTC 1 h,
  `momentum v2` perde mais quando o BTC **sobe** (−0,404 R prospective em 72; −0,342 R replay em
  132) e fica perto de zero quando o BTC está lateral; `volume_anomaly` perde nos três estados. Por
  tercil de volatilidade realizada do BTC, nenhum tercil é positivo nas duas coortes ao mesmo tempo.

Ou seja: **não há um recorte a excluir**. A perda é uniforme, como um imposto é uniforme.

### 6. A invalidação: a [[KB-0006]] acerta a descrição e erra o remédio

Descrição reproduzida (`2026-09-08-04`): a invalidação encerra **26 % a 43 %** dos desfechos, com
**0 ganhadores** em `momentum v2` (68 casos), `momentum v3` (64), `momentum v4` (8) e
`volume_anomaly v2` (166 e 146), e 6 em 341 na `momentum v1`. MFE médio no instante da morte:
0,19–0,46 R; só 1,2 % a 11,4 % chegaram a ver 1 R.

Remédio testado ([[EXP-0007]], replay de braços sobre as **mesmas** entradas congeladas): **remover a
invalidação não muda nada.** `INV-B − base` = −0,006 R (replay `momentum v2`, 222 pares), +0,032 R
(`volume_anomaly v2`, 337), −0,070 R (`momentum v2` prospective), −0,038 R (`momentum v1`
prospective, 932 pares). Nenhum passa o efeito mínimo declarado de 0,05 R nem o Holm, e dois dos
quatro têm sinal negativo. Os trades que a invalidação mata **iriam perder de qualquer forma**: ela
adianta a perda, não a cria.

### 7. A geometria do alvo: o maior contraste — e ele troca de sinal

`momentum` usa alvo 1,5 ATR e stop 1,5 ATR — cerca de 1 R contra 1 R, com acerto de 40 %. O braço
`EXIT-NOTGT` (sem alvo; stop, invalidação e horizonte intactos) sobre as 224 entradas congeladas do
replay levaria a expectancy de **−0,172 R para −0,005 R (PF 0,645 → 0,991)**: Δ = **+0,163 R**.
Sobre a população prospectiva do mesmo código, o **mesmo braço** dá Δ = **−0,226 R** (`momentum v2`,
1 bloco) e **−0,102 R** (`momentum v1`, 932 pares, IC de blocos [−0,116; −0,049] inteiramente
negativo).

**Duas populações, sinais opostos.** É a [[KB-0010]] em estado puro: a janela 2026-08-08→09-08 sobre
quatro majors gerou a hipótese e a população viva a contradiz. A distribuição de MFE sustenta a
dúvida em vez de resolvê-la: entre os ganhadores de `momentum v2` o MFE p90 é 1,23 R (replay) e
1,20 R (prospective) — **não há cauda direita grossa** que um alvo mais distante capturasse nesta
janela — e entre os perdedores o MAE p50 é 0,74 R, isto é, o stop é tocado de raspão.

## Onde foi mostrado

Só aqui, sobre dado nosso. Nenhuma destas dez populações é confirmação de nada: `momentum v2`
prospective tem 2 dias distintos, `momentum v2` replay 24, `volume_anomaly v2` replay 28 — todas
abaixo dos 30 dias e/ou dos 100 desfechos que o [[SHADOW-LAB]] §9 exige. **Veredito de toda variante
individual: `inconclusivo`.** O que **não** é inconclusivo é a identidade do custo: ela é
aritmética, não estatística, e vale para qualquer n.

## Como mediríamos aqui

Três medições, nesta ordem de barateza:

1. **Orçamento de custo explícito na decisão.** Uma versão que recuse decidir quando
   `0,0020 / (risco/preço) > c`, com `c` declarado (ex.: `c = 0,10 R` ⇒ risco ≥ 2 % do preço). Em
   `momentum` isso é derivável por **parâmetro** (`atr_pct_min`, via `derive_variant.py`); em
   `volume_anomaly` **não existe parâmetro nenhum** que faça isso — o stop é a mínima da barra do
   pico e o `default_parameters` não tem piso —, então é **código novo**, com o protocolo de versão.
   **Aviso registrado antes do teste** (`2026-09-08-08-piso-de-risco.sql`, contrafactual *dentro da
   amostra*): o piso leva `momentum v2` prospective de −0,163 R a −0,0006 R (piso 1 %, n = 88) e
   piora `momentum v2` replay de −0,172 R para −0,336 R (piso 1 %, n = 20); em `volume_anomaly` o
   bruto **desaba junto** com o custo (+0,020 → −0,233 R). **Cortar o custo não cria edge — só deixa
   de destruí-la.** Um piso é **necessário e não suficiente**, e é exatamente o que a `momentum v4`
   já está medindo desde 2026-09-08 13:05Z.
2. **Existe alguma entrada com bruto > 0,25 R?** É o teste que falta. Nenhuma das dez populações
   passou de +0,089 R bruto com n ≥ 175. Enquanto nenhuma família de entrada mostrar expectancy
   bruta acima do custo típico, nenhuma política de saída, filtro de hora ou regime inverte o sinal
   — a [[KB-0008]] já dizia isso e agora tem o número desta base.
3. **O classificador de regime precisa existir** antes que "perde só no regime X" seja verificável
   pelo caminho de produção. Hoje `market_regimes` tem uma linha `UNKNOWN`.

## Contra-argumentos e limites

- **A hipótese de custo pode estar pessimista.** 20 bps de ida e volta é hipótese declarada do Lab,
  não tarifa medida ([[KB-0008]]). Se o custo real for metade, a expectancy líquida melhora
  exatamente `custo_R/2` e continua negativa em 8 das 10 populações, porque o bruto é ~0. Medir o
  custo real (execução paper contra o book) mudaria a **magnitude**, não o sinal.
- **`volume_anomaly` pode estar operando exaustão como se fosse continuação.** Bruto positivo
  (+0,009 a +0,020 R) com acerto de 27–33 % e alvo a 1,5 ATR é compatível com [[KB-0015]]; esta nota
  **não** testou direção invertida e não deve ser lida como se tivesse testado.
- **A elegibilidade do replay é a de hoje**, não a da janela ([[PIPELINE]] §6c): ETH/SOL/XRP/DOGE é
  escolha da corrida, e as populações prospectivas correm sobre um universo muito maior e mais
  volátil (risco mediano 1,44 % contra 0,79 %). As duas não são comparáveis entrada a entrada — foi
  por isso que os contrastes foram computados **dentro** de cada uma.
- **Os `p` são exploratórios.** 1 a 29 blocos de dia; com poucos blocos o menor `p` atingível já
  passa do limiar de Holm.
- **O `as_of` fixa a emissão, não a resolução.** Números desta nota só são comparáveis com outra
  leitura se o `input_digest`/`series_digest` das corridas de replay bater.

## Relacionadas

[[KB-0006]] · [[KB-0008]] · [[KB-0010]] · [[KB-0015]] · [[KB-0019]] · [[KB-0021]] ·
[[EXP-0001]] · [[EXP-0002]] · [[EXP-0004]] · [[EXP-0005]] · [[EXP-0006]] · [[EXP-0007]] ·
[[Strategy Backlog]]

## Fontes

- `infra/scripts/sql/research/2026-09-08-00-base.sql` … `-09-identidade-do-custo.sql` — as consultas
  exatas, com o corte `as_of` embutido; transcrição completa da execução única em
  `.claude/state/exp-drafts/t332-replay/t332-sql-transcript.txt`.
- Recibos de replay: `.claude/state/exp-drafts/t332-replay/*.md|.json`
  (`input_digest`/`series_digest` de cada corrida).
- Contrato numérico: `services/strategy-worker/hunter_strategy_worker/pricing.py` (o `R_net`),
  `settle.py` (funding), `excursions.py` (MFE/MAE);
  `packages/core/hunter_core/strategies/momentum_v1.py` e `volume_anomaly_v1.py` (stop, alvo,
  invalidação, horizonte).
