---
tags: [experimento, amplitude, breadth, elegibilidade, populacao, mean-reversion, pre-registro]
updated: 2026-09-11
status: avaliado
owner: quant-engineer
exp: EXP-0027
strategy: "mean_reversion v10 (pai sem portão) + dois braços com portão"
version: "v18 (braço A) e v19 (braço B), derivadas de v10"
result: reprovada
evaluable: 856
days: 84
last_eval: "2026-09-11"
---

# EXP-0027 — a amplitude do universo como estado: `breadth_v2` em 90 dias de replay

> **Cópia do pré-registro `.claude/state/exp-drafts/EXP-0027-amplitude.md` (reescrito na T3.88),
> arquivada aqui em 2026-09-11 às 09:52 BRT (12:52 UTC), ANTES de derivar qualquer variante e
> ANTES de qualquer replay.** A régua abaixo é a da T3.88, congelada; nada nesta página é dinheiro
> real (`ENABLE_LIVE_TRADING=false`) e nenhuma versão é promovida por ela.
>
> O que esta página acrescenta ao rascunho, e só isto: a **distribuição medida** de `breadth_v2`
> nos 90 dias (a medição somente-leitura do passo 1 do brief T3.89), os **tercis congelados** e as
> **previsões numéricas** que saem dessa distribuição — todas escritas antes da primeira derivação.

## Hipótese (congelada)

**A fração do universo que caiu nos 5 minutos completos antes do fechamento da barra
(`breadth_v2`) separa a expectancy das decisões de reversão à média** — comprar reversão com 70 %
do universo caindo não é a mesma aposta que comprar reversão com 30 %. Origem: H-P8 /
[[KB-0083-uma-hora-de-34-r-deriva-e-impulso|KB-0083]], a pior hora da família (09/09, 21:00Z,
−34,02 R em 39 decisões), cujo estouro tem minuto e nome (22:08Z, 194 dos 200 perpétuos caindo no
mesmo minuto, BTC em −0,204 %) e cuja hora inteira já estava com 58–76 % do universo caindo
**antes** das decisões.

**Isto é uma hipótese sobre um minuto**, e escolher o estado presente no pior minuto do mês para
depois "confirmá-lo" é o erro que esta página existe para não cometer. Daí a régua, e daí o braço de
falseamento ser o que a KB-0083 diz que deveria ser o **pior**.

## Por que `breadth_v2` e não `breadth_v1`

| | `breadth_v1` (T3.77) | `breadth_v2` (T3.88) |
|---|---|---|
| universo | ~200 perpétuas monitoradas | as **16** com ≥ 90 d de velas de 1 min |
| janela / regra | 5 min, `<` estrito | **idênticas** |
| piso de cobertura | 80 % de ~200 (160 densos) | 80 % de 16 (**13** densos) |
| dias dobráveis nos últimos 90 | **4 de 91** (medido, VPS 2026-09-10) | **90 de 90** (medido aqui) |
| linhas já gravadas | imutáveis, nada é reescrito | série nova, a chave única inclui a versão |

Duas coisas que ficam no pré-registro. (i) **O universo de v2 é o universo das decisões**: a coorte
cortada aqui é um replay de 90 d sobre 16 mercados ([[EXP-0025-mean-reversion-90-dias|EXP-0025]]),
e medir a amplitude sobre 200 mercados dos quais 184 nunca entram numa decisão seria cortar a coorte
por um estado que ela não habita. (ii) **A política nomeia a série**: o corpo gravado é
`{"breadth": {"window_m": 5, "min": "0.10", "max": "0.60", "version": "breadth_v2"}}`, e uma
política sem `version` é **recusada** em vez de completada com o padrão do build
(`breadth_policy.py`, T3.88).

## Os braços

Pai: **`mean_reversion v10`** sem portão — coorte `replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3`,
**798 decisões terminais em 89 dias × 16 mercados**, expectativa ex-funding **−0,0293 R**, PF 0,910,
IC 95 % [−0,1336; +0,0728] (indistinguível de zero). Decisão em 15 min, outcome em 1 min, horizonte
de 4 h.

| braço | versão | política | o que afirma | previsão do rascunho |
|---|---|---|---|---|
| **A** (célula de dentro) | `v18` | `breadth=0.10-0.60@breadth_v2` | a reversão compradora vive na amplitude intermediária | Δ > 0 contra o pai, mas **< +0,05 R** (isto é: A **não** aprova) |
| **B** (falseamento) | `v19` | `breadth=0.60-1.00@breadth_v2` | a venda generalizada é o pior lugar para comprar reversão (KB-0083) | Δ < 0, **pior** que o pai |

As faixas são as da T3.77, escritas antes de qualquer leitura desta série; são meia-abertas no topo
(`min <= valor < max`), ladrilham [0,10; 1,00) sem sobreposição e sem buraco, e `[0; 0,10)` fica
deliberadamente **fora dos dois** — é o "nada está caindo", e uma faixa que ninguém pré-registrou
não ganha braço.

**Se B aprovar e A não**, a hipótese "a vantagem vive no meio" está **refutada**; o que sobra ("a
vantagem vive na venda generalizada") nasce como candidata da EXP seguinte, com pré-registro
próprio, e **não** pode ser declarada vencedora aqui.

## Regra de sucesso — congelada, a mesma da EXP-0026/0028

A quantidade que a hipótese afirma é **condicional contra incondicional**:

> **Δ = média de `r_ex_funding` das decisões do braço − média de `r_ex_funding` das decisões do pai
> na janela inteira**, por natureza **não pareada** (as duas populações não compartilham barras),
> com IC 95 % por **bootstrap de blocos de dia inteiro, não pareado**
> (`.claude/state/exp-drafts/t362b/blocos90.py`, 20 000 reamostragens, semente **20260912**).

**Aprova** o braço que cumprir **todas**:

1. Δ ≥ **+0,05 R** e o IC 95 % por blocos de dia **acima de zero**;
2. **n ≥ 100** desfechos avaliáveis **e** ≥ 30 dias distintos;
3. média de `r_ex_funding` **positiva em ao menos 2 das 3 janelas** de 30 dias;
4. **leave-one-market-out nunca negativo** (16 reajustes, um por mercado retirado);
5. o Δ **pareado** por (mercado, barra) sobre as barras elegíveis compartilhadas fica **dentro de
   ±0,02 R de zero** — não como prova de vantagem, e sim como **prova de que o portão é só um
   portão** (`docs/PIPELINE.md` §4b item 11: `INELIGIBLE` não arma a barreira, logo a filha pode
   abrir um episódio numa barra que o pai nunca considerou; um Δ pareado grande só poderia ser essa
   divergência de slot ou bug).

**Qualquer coisa a menos = `descartar`**, com aposentadoria pela via auditada
(`activate_strategy_version.py --deprecate`) **no mesmo dia**. Um braço mudo (n < 100) é `descartar
por população`, nunca "negativo".

**Cláusula de falsificação adicional (controle de identidade):** a mesma leitura é repetida com as
decisões do pai cortadas por `regime_hourly_v1` em vez de `breadth_v2`. Se o corte por regime
produzir Δ **igual ou maior**, `breadth_v2` não é estado novo — é o regime horário reamostrado por
minuto — e o veredito é `descartar` mesmo que os cinco itens passem.

**K4 e K5.** K4 (`unavailable`) **não é mensurável num braço com portão** (`docs/PIPELINE.md` §4b
item 12): é lido no **pai**, na mesma janela, e a fração `ineligible` da filha é reportada como
número próprio. K5: a cobertura de `R_net` da coorte de 90 d da `v10` é **37,59 %** (300 de 798),
então o eixo primário é **`r_ex_funding`** (798 de 798) e **toda tabela declara o eixo**.

## Distribuição de `breadth_v2` — medida em 2026-09-11 às 09:35–09:48 BRT, antes de derivar

Somente leitura (`infra/scripts/sql/research/2026-09-11-t389-q01-breadth-distribuicao.sql` e
`-q02-breadth-nas-barras-de-15m.sql`). A série tinha **128 348 linhas, 128 347 usáveis**
(2026-06-14 00:00Z → 2026-09-11 12:36Z; o brief T3.89 citou 128 343/128 342 às 09:31 BRT — a
diferença são os cinco minutos que o produtor vivo gravou entre as duas leituras). Uma única linha
inutilizável em toda a série: 2026-09-11 12:30Z, `insufficient_coverage`, 10 de 16 cobertos — a
faixa viva, não o histórico. **Cobertura de 100 % (16/16) em cada um dos 90 dias completos**, que é
o fato que fazia falta: `breadth_v1` reprovava 87 dos últimos 91.

| quantil | valor |
|---|---|
| mínimo / p05 | 0,000000 / 0,000000 |
| p10 / p25 | 0,062500 / 0,187500 |
| **p50** | **0,500000** |
| p75 / p90 | 0,750000 / 0,937500 |
| p95 / p99 | 0,937500 / 1,000000 |
| média | 0,480429 |

Histograma dos 17 degraus possíveis (16 mercados ⇒ passos de 0,0625): a distribuição é **em U**, não
unimodal — `0,0000` 6,57 %, `0,0625` 8,35 %, cai até `0,5625` 4,74 % e sobe de novo até `0,9375`
7,06 % e `1,0000` 4,65 %.

**Share de minutos usáveis (série inteira, 128 347):** A `[0,10; 0,60)` **44,50 %**; B
`[0,60; 1,00]` **40,57 %**; abaixo de 0,10 (sem braço) **14,93 %**.

**Share de barras elegíveis por braço — o número que o brief pede.** O portão lê a linha cujo
`end_time` é **exatamente** o `source_bar_close`, e a grade de decisão da `v10` é de 15 min, então o
denominador honesto são os **8 448 fechamentos de 15 min** da janela de replay (2026-06-14 →
2026-09-10), não todos os minutos:

| braço | barras de 15 min na faixa | share das 8 448 |
|---|---|---|
| **A** `[0,10; 0,60)` | 3 970 | **46,99 %** |
| **B** `[0,60; 1,00)` | 2 976 | **35,23 %** |
| sem braço `[0; 0,10)` | 1 182 | 13,99 % |
| sem braço, degrau `= 1,0000` (16 de 16 caindo) | 320 | 3,79 % |
| sem linha usável | 0 | **0,00 %** |

**Correção medida às 09:55 BRT, antes do primeiro replay e depois de derivar as versões
(`-q04-faixa-b-meia-aberta.sql`):** a faixa é **meia-aberta no topo** (`breadth_policy.py`:
`min <= valor < max`), então `0.60-1.00` é `[0,60; 1,00)` e o degrau **exato** 1,0000 — o universo
inteiro caindo, 3,79 % das barras — **não pertence a nenhum braço**. A primeira leitura desta página
mediu B com `<= 1,00` (3 296 barras, 39,02 %) e o número correto é **2 976 barras, 35,23 %**; as duas
contagens ficam aqui de propósito, porque a diferença **é** a regra. O próprio pré-registro já
declarava o ladrilho como `[0,10; 1,00)`, logo isto não muda a régua nem a faixa — muda a previsão de
população e acrescenta um terceiro buraco declarado: **17,78 % das barras não têm braço** (13,99 %
abaixo de 0,10 mais 3,79 % no degrau cheio).

Por janela de 30 dias (a régua exige as três): A 42,75 % / 50,28 % / 47,67 % e B (fechada, o número
da primeira leitura) 39,14 % / 37,57 % / 40,35 % — nenhuma janela emudece nenhum braço.

**Tercis congelados (só para a leitura descritiva).** Sobre as linhas usáveis da janela de
calibração, **todos os minutos**, e **nunca recalculados**: `t1` = **0,250000** e `t2` =
**0,687500** (n = 69 120). Ressalva de honestidade: o rascunho manda calibrar em **2026-06-13 →
07-31** e a série **começa em 06-14 00:00Z**, então a calibração efetiva é 2026-06-14 → 07-31 (48
dias × 1 440 min = os 69 120 exatos). A janela de calibração é descartada da leitura descritiva, que
é medida sobre as decisões de 2026-08-01 em diante.

## Previsões numéricas registradas antes da primeira derivação

As quatro do rascunho, e o que a distribuição medida já diz sobre elas:

1. **Distribuição — FALSIFICADA na medição, antes de qualquer replay.** Previsão: "menos de 2 % dos
   minutos acima de 0,90". Medido: **11,71 %** (`0,9375` 7,06 % + `1,0000` 4,65 %). O próprio
   rascunho declarou o mecanismo ("16 é um denominador pequeno, espera-se mais massa nos extremos")
   e errou a magnitude por ~6×: com 17 degraus, "acima de 0,90" são **dois degraus inteiros**. A
   distribuição é em U e a mediana (0,50) caiu no meio da faixa prevista (0,40–0,60).
2. **Direção** (do rascunho, mantida): Δ do braço **B negativo** e Δ do braço **A positivo mas
   pequeno (< +0,05 R)**, isto é, previsão de que **A não aprova**.
3. **Autocorrelação com o regime**: `breadth_v2` alto e `BTC_BEAR` coincidem com frequência — se a
   faixa alta for só o `BTC_BEAR` com outro nome, a hipótese não acrescenta nada (é o que a cláusula
   de identidade testa).
4. **População**: `breadth_unavailable` **abaixo de 1 %** das barras. Medição prévia: **0,00 %** dos
   8 448 fechamentos de 15 min da janela ficam sem linha usável, então a previsão só pode falhar por
   barra fora da janela do replay.

E duas previsões **novas**, minhas, feitas antes da primeira derivação e a partir do share medido
(elas podem estar erradas e é para isso que estão aqui):

5. **n esperado por braço**, projetando as 798 decisões do pai pelas células medidas: **A ≈ 400** e
   **B ≈ 195** desfechos (B com a faixa meia-aberta correta), ambos acima do piso de 100 — nenhum
   braço deve morrer por população.
6. **Sinal do Δ, e ele contradiz a previsão 2 do rascunho.** A leitura descritiva das decisões **do
   pai** por célula (abaixo) dá A = **−0,0682 R** e B = **−0,0162 R** contra o incondicional
   −0,0293 R. Se o portão for só um portão (condição 5), o replay deve reproduzir
   **Δ_A ≈ −0,039 R** e **Δ_B ≈ +0,013 R** — ou seja: **o braço "de dentro" deve sair pior que o
   pai e o braço de falseamento um pouco melhor**, o oposto do que a hipótese H-P8 afirma. Previsão
   de veredito: **`descartar` nos dois** (A falha a condição 1 por sinal; B falha por magnitude e
   IC).

## Leitura descritiva por célula — medida sobre as decisões do PAI antes do replay dos braços

Esta é a leitura que o rascunho prevê ("célula descritiva ao lado"), feita sobre a coorte do pai
(`replay:c7d138eb…`, 798 terminais) juntando cada decisão à linha de `breadth_v2` do seu
`source_bar_close`. **Não é o resultado do experimento** — a população dos braços difere pela
divergência de máquina de estados do slot (`docs/PIPELINE.md` §4b item 11) — e não move a régua:

| célula | n | dias | `r_ex_funding` médio | soma R |
|---|---|---|---|---|
| **A** `[0,10; 0,60)` | 403 | 82 | **−0,0682** | −27,4878 |
| **B** `[0,60; 1,00)` (a faixa do portão, meia-aberta) | 195 | 69 | **−0,0162** | −3,1549 |
| degrau `= 1,0000` (sem braço, órfão pelo ladrilho) | 17 | 10 | **+0,1178** | +2,0023 |
| `[0; 0,10)` (sem braço) | 174 | 56 | **+0,0327** | +5,6904 |
| sem linha usável (barras de 06-12 e 06-13, antes da série) | 9 | 2 | −0,0446 | −0,4017 |

`[0,60; 1,00]` fechada — a leitura errada da primeira versão desta página — daria 212 decisões e
−0,0054 R: os 17 desfechos do degrau cheio valem **+0,1178 R** e sozinhos moviam a célula B em
+0,0108 R. É mais um motivo para a correção estar escrita e não corrigida em silêncio.

Tercis congelados, decisões de 2026-08-01 em diante (a janela de calibração descartada): **T1 baixo
[0; 0,25) +0,1330 R (n = 125) · T2 meio [0,25; 0,6875) +0,0889 R (n = 138) · T3 alto [0,6875; 1]
+0,0172 R (n = 87)**. O efeito **é monótono**, e é monótono **decrescente**: quanto menos gente
caindo, melhor a reversão compradora. Isso é evidência a favor de "a amplitude é um estado" e
**contra** "a vantagem vive no meio" — a célula de dentro não é a melhor, é o meio de um gradiente
cuja ponta boa está **abaixo** de 0,10, justamente a faixa que ninguém pré-registrou.

## A janela do replay, e a única coisa que ela muda

A coorte do pai vai de **2026-06-12T21:00Z** a **2026-09-09T20:15Z** (12 fatias: 06-12→07-12,
07-12→08-11, 08-11→09-10, quatro grupos de quatro mercados). `breadth_v2` **começa em
2026-06-14T00:00Z**, então os braços são replayados de **2026-06-14 a 2026-09-10** (88 dias) e a
população do pai usada no Δ é **cortada no mesmo início** — as 9 decisões do pai em 06-12/06-13
saem das duas leituras, nomeadas aqui, em vez de virarem `breadth_unavailable` num braço e barra
válida no outro. É a única diferença de calendário entre pai e filhas, e ela está declarada antes da
corrida.

Fatias: **12 por braço** (≤ 4 mercados × ≤ 31 d), coorte explícita por braço, `--explain-ledger`,
via `STRATEGY_SHARDS=4 MARKET_SPOT=1 MARKET_SHARDS=4 bash infra/vps/compose.sh replay python -m
hunter_strategy_worker.replay.run`, uma por vez, `timeout 290` por fatia. Ritmo medido do pai:
11 520 barras em 180–204 s (62,7 barras/s).

## Não-antecipação (o que está provado e o que custa)

A série dobra, para o minuto `T`, apenas velas com `open_time + 1 min <= T` — seis velas, de
`T−6min` a `T−1min` — e um mercado sem as seis não é contado
(`packages/indicators/tests/unit/test_breadth_series.py`, inclusive a prova de que mudar a vela que
**abre** no corte não move o número). O universo de v2 é resolvido **uma vez por passada**, com
`universe_as_of`/`universe_rule` gravados em `inputs`. O portão lê a linha cujo `end_time` é
**exatamente** o `source_bar_close`, **na série que a política nomeia** — sem tolerância, sem "a
mais recente antes" —, e uma linha de `breadth_v1` no mesmo minuto **não** responde por uma versão
presa a `breadth_v2`
(`services/strategy-worker/tests/test_breadth_gate.py::TestASerieEParteDaChave`). O custo declarado:
um produtor atrasado **emudece** a versão com `breadth_unavailable` em vez de deixá-la decidir com
valor velho.

## H-P18 (dispersão BTC × alts) não cabe nesta série

`compute_breadth` conta "caindo" comparando **o próprio** close de cada mercado em duas pontas de 5
min com `<` estrito. H-P18 precisa de horizonte de 24 h, de um **mercado de referência** (o BTC)
dentro do fold e de comparação de **retornos**, não de sinal. Reinterpretar `breadth_v2` para isso
seria exatamente o erro que `hunter_indicators.breadth` e `hunter_indicators.regime.breadth` existem
separados para evitar. O que falta é uma série nova (`dispersion_24h`), reusando sem mudança
`hunter_core.universe` e a forma de `market_breadth`/`BreadthSpec` — **lote posterior, nenhum braço
aqui**.

## Protocolo (congelado na primeira ativação — nunca editar)

- **Strategy:** `mean_reversion` — `v18` (braço A) e `v19` (braço B), derivadas de `v10`
- **code_ref:** o **do pai, byte a byte** (`hunter_core.strategies.mean_reversion_v1@sha256:a970c9d9…`) — nenhum parâmetro muda, só o envelope de elegibilidade
- **params_hash / params_format:** `d4fcf66f94497742d82527bfe5980bfd1f1dd630187e289b9c5cca8f1458409b` / `1`
- **Parameters:** os de `v10`, byte a byte (`atr_bars 24`, `atr_period 14`, `atr_timeframe 1h`, `stop_atr 1.5`, `target_atr 2.25`, `target2_atr 3.75`, `zscore_bars 20`, `trend_sma_bars 20`, `trend_timeframe 1h`, `atr_pct_min 0.008`, `atr_pct_max 0.05`, `horizon_s 14400`, `fee_bps 4`, `slippage_bps 5`, `assumed_spread_bps 2`, `max_entry_delay_s 120`, `base_confidence 0.5`, `zscore_depth_min 1`)
- **Política de elegibilidade:** A `{"breadth": {"window_m": 5, "min": "0.10", "max": "0.60", "version": "breadth_v2"}}` · B `{"breadth": {"window_m": 5, "min": "0.60", "max": "1.00", "version": "breadth_v2"}}`
- **Timeframe de decisão / de outcome:** 15 min / 1 min, UTC
- **Entrada / saída / custos:** os do pai (open da primeira barra de 1 min após `decision_at`, com `entry_bar_open − source_bar_close ≤ 120 s`; gap na abertura, depois toques intrabar, stop vence empate; horizonte 4 h; 2 bps de spread, 5 bps de slippage por lado, 4 bps de taxa por lado, funding assinado)
- **Cohort:** uma por braço, `replay:<uuid>`, registrada na avaliação abaixo
- **Controle predeclarado:** o **pai já medido** (`v10`, coorte `replay:c7d138eb…`, EXP-0025), que **não** será re-rodado; mais o braço de falseamento B
- **Universo elegível:** os 16 mercados com ≥ 90 d de velas de 1 min (ARB BNB BTC DASH DOGE ETH LINK NEAR PROM SAHARA SOL SUI TAO UNI XRP ZEC), `markets.is_monitored` de hoje — a limitação declarada do método (`docs/PIPELINE.md` §6c: não há histórico de pertencimento por barra)
- **Janela:** 2026-06-14 → 2026-09-10 (88 dias), contra o pai cortado no mesmo início
- **Data de início:** 2026-09-11

## Avaliações (acrescentadas, nunca reescritas)

### Avaliação de 2026-09-11 — pré-registro arquivado, nenhuma corrida ainda

**Cobertura:** nenhuma decisão. As variantes não existiam no instante em que esta página foi escrita
(`mean_reversion` ia de `v1` a `v17`). **Result:** `nao-iniciado`. **Next Action:** derivar
`v18`/`v19` com `--dry-run` primeiro, ativar como `research_only`, replayar 12 fatias por braço e
aplicar a régua acima — o que falhar é aposentado no mesmo dia.

### Avaliação de 2026-09-11 — `as_of = 2026-09-12T01:16:02Z` (22:16 BRT de 2026-09-11)

**Corridas:** 24 fatias de replay (`v18` e `v19`, 12 cada), **270 336 barras**, **0 erros**, coortes
`replay:f2c44f18-5f63-435f-97bb-5f5aaf31cea7` (A) e `replay:a94701c9-3459-463e-8922-c1403e91d60a`
(B), janela **2026-06-14 → 2026-09-10** (88 d, o início de `breadth_v2`), 4 fatias de 4 mercados por
janela de ~30 d. O controle pré-declarado (`v10`, `replay:c7d138eb…`, EXP-0025) **não foi
re-rodado**; a sua população foi cortada no mesmo início de calendário (798 → **789** decisões, as 9
de 06-12/06-13 saem das duas leituras). Cohort redundante `replay:a42c888d-e0c7-40fa-9536-ed2378d59493`
(4 fatias de `v18` de um loop quebrado) **confirmada e ignorada** — não entra em nenhuma soma desta
página. Comandos e saídas verbatim em `.claude/state/notes-T3.89.md`.

**Cobertura (eixo `r_ex_funding`, presente em 100 % da população; K4 só é mensurável no pai):**

| versão | decisões | dias | `ineligible` (do recibo) | K4 (do pai, mesma janela) | erros |
|---|---:|---:|---:|---:|---:|
| `v10` (pai, cortado em 06-14) | 789 | 87 | 0 % | **0,93 %** (`replay:c7d138eb…`, 90 d completos) | 0 |
| `v18` (A) | 540 | 84 | 71 648/135 168 = **53,00 %** | ler no pai | 0 |
| `v19` (B) | 316 | 75 | 87 552/135 168 = **64,79 %** | ler no pai | 0 |

Nenhum braço morreu por população (previsão 5 do pré-registro: A ≈ 400, B ≈ 195 — o medido, 540 e
316, veio **acima** da projeção nos dois, porque a faixa fecha barras extras via o degrau `1,0000`
órfão do lado de fora, e o corte por 15 min amostra mais barras `ineligible` do que a projeção linear
sobre minutos previa).

**A régua, condição por condição (Δ NÃO pareado braço−pai, blocos de dia inteiro, 20 000
reamostragens, semente **20260912** — a semente do pré-registro, diferente da semente-padrão
20260910 usada nas EXP-0025/0026):**

| braço | 1. Δ ≥ +0,05 e IC > 0 | 2. n ≥ 100 e ≥ 30 d | 3. 2 de 3 janelas | 4. LOMO nunca negativo | 5. Δ pareado ≈ 0 | estresse | falsificação (regime ≥ breadth?) | **veredito** |
|---|---|---|---|---|---|---|---|---|
| `v18` (A) | **FALHA** — **−0,0184**, IC [−0,1692; +0,1350] (sinal errado) | PASSA (540/84) | **FALHA** (1/3) | **FALHA** (16 de 16 negativos, pior sem ZECUSDT −0,0633) | PASSA (**+0,0000**, 393/540 barras compartilhadas) | `sem_vantagem_na_base` (custos ×2 −0,0978; 1ª metade −0,1497 × 2ª +0,0621) | **SIM** — regime +0,0017 ≥ breadth −0,0184 | **`descartar`** |
| `v19` (B) | **FALHA** — +0,0372, IC [−0,1574; +0,2232] (abaixo do piso e IC cruza zero) | PASSA (316/75) | **FALHA** (1/3) | **FALHA** (1 de 16, sem DASHUSDT −0,0042) | PASSA (**+0,0000**, 192/316 barras compartilhadas) | frágil a custos (×2 −0,0935); dependente de 4 mercados isolados e de metade (1ª −0,0858 × 2ª +0,0953) | **SIM** — regime +0,1456 ≥ breadth +0,0372 | **`descartar`** |

**Expectativa (eixo `r_ex_funding`, IC 95 % por blocos de dia, semente 20260912):**

| versão | n | dias | média | soma R | PF | IC 95 % da média |
|---|---:|---:|---:|---:|---:|---|
| `v10` (pai, cortado) | 789 | 87 | −0,0291 | −22,95 | 0,911 | [−0,1344; +0,0734] |
| `v18` (A) | 540 | 84 | **−0,0475** | −25,63 | 0,851 | [−0,1559; +0,0620] |
| `v19` (B) | 316 | 75 | **+0,0081** | +2,55 | 1,024 | [−0,1553; +0,1629] |

**Por janela de 30 d (condição 3):** pai −0,1248 (n=328) / −0,0822 (n=181) / +0,1174 (n=280) · `v18`
−0,1696 (n=226) / −0,0936 (n=131) / +0,1364 (n=183) · `v19` −0,1096 (n=130) / −0,0097 (n=63) /
+0,1416 (n=123). **As três séries só são positivas em agosto–setembro** — a mesma assinatura de
calendário da EXP-0025/0026, e o portão de amplitude não muda essa assinatura.

**Clausula de falsificação (controle de identidade), medida como partição dentro do pai (permitido
− proibido, pareada por dia, mesmo método do §2b da T3.76), rótulos permitidos = os que dominam
(≥ 50 % das decisões) cada braço:** para `v18` (BTC_BEAR, BTC_BULL, HIGH_VOLATILITY, 524 decisões do
pai) o corte por regime dá **+0,0017 R**; para `v19` (HIGH_VOLATILITY, SIDEWAYS, 377 decisões do
pai) dá **+0,1456 R**. Os dois números são **maiores ou iguais** ao Δ de `breadth_v2` medido na
condição 1 (−0,0184 e +0,0372) — **a cláusula dispara nos dois braços**: cortar pelo regime horário
do BTC já vencido produz tanta ou mais separação do que cortar pela amplitude do universo. `breadth_v2`
não é um estado novo na leitura desta coorte; é consistente com ser o regime horário reamostrado por
minuto, como a própria hipótese avisou que poderia ser.

**Estresse (sessão somente-leitura, `--stress`, 2026-09-12T01:12–01:14Z / 22:12–22:14 BRT, eixo
`r_net`):** `v18` base −0,0509 R (n=538, 2 `funding_missing`), `custos_x2` −0,1487 (Δ −0,0978, IC
[−0,1025; −0,0933]), 1ª metade (até 07-27) −0,1497 (n=287) × 2ª metade +0,0621 (n=251) → **`sem_vantagem_na_base`**.
`v19` base +0,0033 R (n=315), `custos_x2` −0,0902 (Δ −0,0935, IC [−0,1007; −0,0866]), dependente de
4 mercados isolados (BNB/DASH/SAHARA/XRP viram negativos ao serem excluídos) e de metade (1ª −0,0858
× 2ª +0,0953) → **`frágil a custos`**.

**K1–K6 e C5 (medidos nas decisões, pedágio = 0,0020 / (stop_atr × ATR%), `stop_atr = 1,5` — o do
pai/braços byte a byte):** nenhum dispara K1 ou K2; **K3 dispara no pai e em `v18`** (n ≥ 100, ≥ 30
dias, `r_ex_funding` médio < 0) e **não dispara em `v19`** (média positiva, ainda que ínfima); K6
(concentração ≥ 60 % num mercado) não dispara em nenhum (maior fatia: 10,5 %/10,7 %/12,0 %); C5
(risco/entrada acima de 3 %) fica em 16,9 % (pai) / 15,0 % (`v18`) / 19,6 % (`v19`), sem outlier.
Pedágio p50: 0,1064 R (pai) / 0,1092 R (`v18`) / 0,0988 R (`v19`) — praticamente idêntico entre as
três, o que é esperado: nenhum parâmetro de ATR muda.

**Result:** **refutou os dois braços, e refutou a hipótese principal duas vezes.** A previsão
numérica 6 do pré-registro (Δ_A ≈ −0,039 R, Δ_B ≈ +0,013 R, "o braço de dentro sai pior que o pai e
o braço de falseamento um pouco melhor") acertou a **direção** dos dois sinais e errou a magnitude
por um fator de ~2× em ambos (medido: −0,0184 e +0,0372) — o mesmo sentido, mais fraco. **O braço A
(a célula "de dentro", a que a hipótese H-P8 afirma que é onde vive a vantagem) saiu pior que o pai**,
o oposto do que "a reversão compradora vive na amplitude intermediária" precisaria para ser
verdadeira. **O braço B (falseamento) saiu melhor que o pai**, na mesma direção da leitura descritiva
pré-replay (T1 baixo > T2 meio > T3 alto, monótona decrescente) — mas abaixo do piso de aprovação e
com IC que cruza zero. **A condição 5 prova o instrumento**: Δ pareado por (mercado, barra) é
0,0000 R nos dois braços, então a divergência de população vem só do §4b item 11 (a filha não arma a
barreira nas barras que pula), não de um bug de leitura. **A cláusula de identidade fecha o caso**:
em ambos os braços, cortar o pai por `regime_hourly_v1` produz separação igual ou maior do que
`breadth_v2` produziu de fato — a amplitude do universo, nesta coorte, não é um estado que a
`mean_reversion` deveria pagar por vigiar além do que o portão de regime (já descartado na EXP-0026,
pelos mesmos motivos de calendário) já vigiava.

**Conclusion:** `descartar` nos dois braços, pela regra pré-registrada. **Aposentados no mesmo dia**
pela via auditada: `v18` deprecated em **2026-09-12T01:15:24Z** (22:15:24 BRT de 2026-09-11),
`v19` deprecated em **2026-09-12T01:16:02Z** (22:16:02 BRT), ambos `successor=none`, changelog com o
número medido embutido. Nenhuma coorte `prospective` foi aberta — nenhum braço passou.

**Next Action:** nenhuma sobre `breadth_v2` nesta forma. Se a leitura descritiva monótona (T1 > T2 >
T3, a ponta boa **abaixo** de 0,10) for perseguida, é uma EXP nova com pré-registro e prospectivo
próprios, sabendo de antemão que a cláusula de identidade provavelmente também dispara ali — H-P18
(dispersão BTC × alts, §"não cabe nesta série" acima) continua como candidata separada, com série
própria (`dispersion_24h`) ainda não escrita.

## Variantes tentadas

| Variante | Quando | Por quê | Onde ficou registrada |
|---|---|---|---|
| `v18` (A, `breadth=0.10-0.60@breadth_v2`) | 2026-09-11 | célula de dentro, a faixa pré-registrada da T3.77 | esta página — `descartar`, aposentada 2026-09-12T01:15:24Z |
| `v19` (B, `breadth=0.60-1.00@breadth_v2`) | 2026-09-11 | falseamento: a venda generalizada deveria ser o pior lugar | esta página — `descartar`, aposentada 2026-09-12T01:16:02Z |

## Relacionadas

[[Experiments Index]] · [[Strategies]] · [[Strategy Performance]] · [[Dialogos/SHADOW]] ·
[[EXP-0025-mean-reversion-90-dias]] · [[EXP-0026-regime-como-estrategia]] ·
[[KB-0083-uma-hora-de-34-r-deriva-e-impulso]]

## Fontes

- pré-registro: `.claude/state/exp-drafts/EXP-0027-amplitude.md` (T3.88); brief: `.claude/state/brief-T3.89-exp-0027-amplitude.md`
- série e portão: `docs/PIPELINE.md` §4b itens 14–15, `docs/ACTIVATION.md` §7c, `packages/indicators/hunter_indicators/breadth/`, `services/strategy-worker/hunter_strategy_worker/breadth_gate.py`, `breadth_policy.py`
- SQL desta página: `infra/scripts/sql/research/2026-09-11-t389-q00-catalogo.sql`, `-q01-breadth-distribuicao.sql`, `-q02-breadth-nas-barras-de-15m.sql`, `-q03-variantes-derivadas.sql`, `-q04-faixa-b-meia-aberta.sql`, `-q10-recibos-replay.sql`, `-q11-dump-decisoes-bracos.sql`, `-q12-k4-pai.sql`
- análise: `.claude/state/exp-drafts/t389/analise.py` sobre `.claude/state/exp-drafts/t389-decisoes.csv` (1 645 linhas), bootstrap `.claude/state/exp-drafts/t362b/blocos90.py`
- notas: `.claude/state/notes-T3.89.md`
