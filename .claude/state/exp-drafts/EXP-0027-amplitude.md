---
tags: [experimento, amplitude, breadth, elegibilidade, populacao, mean-reversion, pre-registro]
updated: 2026-09-11
status: rascunho
owner: quant-engineer
exp: EXP-0027
strategy: "mean_reversion v10 (pai sem portão) + dois braços com portão"
version: "a derivar de mean_reversion v10 — nenhuma variante existe"
result: pendente
evaluable: 0
days: 0
last_eval: "—"
---

# EXP-0027 — a amplitude do universo como estado: `breadth_v2` em 90 dias de replay

> Rascunho para a Sexta-feira arquivar em `obsidian/05-EXPERIMENTS/`. Nada aqui é dinheiro real
> (`ENABLE_LIVE_TRADING=false`).
>
> **Reescrito em 2026-09-11 (T3.88), ANTES de qualquer derivação, backfill ou replay.** A versão de
> 2026-09-10 declarava este experimento **prospectivo-só** por um motivo aritmético: a série
> `breadth_v1` mede a fração de **~200** perpétuas monitoradas que caíram, e num dia em que 16 delas
> têm velas de 1 min a cobertura é 8 % — `insufficient_coverage` em **87 dos últimos 91 dias**. A
> T3.88 não relaxou o piso; declarou **outra série**. `breadth_v2` mede os **16 mercados com ≥ 90
> dias de velas de 1 min** (o universo sombra da T3.82, e exatamente a população de onde sai toda
> coorte de replay), com a mesma janela de 5 min, o mesmo `<` estrito e o mesmo piso de 80 % — agora
> sobre um denominador que **pode** ser coberto. Com isso os 90 dias passam a ser dobráveis e este
> experimento vira o que a EXP-0025/0026/0028 já são: um teste histórico com régua congelada.
>
> **Ainda não medido:** o backfill (`infra/scripts/backfill_breadth.py --days 90`) não rodou na VPS,
> nenhuma variante existe, nenhuma coorte foi replayada. Tudo abaixo é desenho, previsão e régua.

## De onde veio a hipótese (H-P8)

`.claude/state/notes-D-P9.md` §4 / KB-0083, sobre a pior hora da família (09/09, 21:00Z, −34,02 R em
39 decisões, 0 % de acerto):

- o estouro tem minuto e nome: **19:08 BRT / 22:08Z**, quando **194 dos 200 perpétuos monitorados
  caíram no mesmo minuto** (média −3,71 %, mediana −1,76 %, LABUSDT −35,8 %) e repicaram no minuto
  seguinte. Ali saíram 15 das 39 apostas (−14,77 R, 43 % da hora);
- o **BTC não explica**: no mesmo minuto ele caiu −0,204 % (amplitude 0,246 %);
- a hora inteira já estava rotulada `BTC_BEAR` com **58–76 % do universo caindo** antes do estouro —
  o estado era observável *antes* das decisões.

> **Hipótese (congelada):** a fração do universo que caiu nos 5 minutos completos antes do
> fechamento da barra (`breadth_5m`) **separa a expectancy** das decisões de reversão à média:
> comprar reversão com 70 % do universo caindo não é a mesma aposta que comprar reversão com 30 %.

**Isto é uma hipótese sobre um minuto.** Escolher o estado presente no pior minuto do mês e depois
"confirmar" que ele é ruim é o erro que este documento existe para não cometer (a armadilha que a
EXP-0023 registrou para a hora 12 UTC, melhor-de-24 com n ≤ 16). Daí a régua abaixo, e daí o braço
de falseamento ser o braço que a KB-0083 diz que deveria ser o **pior**.

## O que mudou de universo, e por que isso não é um ajuste de conveniência

| | `breadth_v1` (T3.77) | `breadth_v2` (T3.88) |
|---|---|---|
| universo | ~200 perpétuas monitoradas | as **16** com ≥ 90 d de velas de 1 min |
| janela / regra | 5 min, `<` estrito | **idênticas** |
| piso de cobertura | 80 % de ~200 (160 densos) | 80 % de 16 (**13** densos) |
| dias dobráveis nos últimos 90 | **4 de 91** (medido, VPS 2026-09-10) | a medir pelo relatório do backfill |
| linhas já gravadas | imutáveis, nada é reescrito | série nova, chave única inclui a versão |

Duas coisas que valem estar no pré-registro. (i) **O universo de v2 é o universo das decisões.** A
coorte que este experimento corta é um replay de 90 dias sobre 16 mercados (EXP-0025: `v10`, 12
fatias, 138 240 barras, **798 decisões em 89 dias**); medir a amplitude sobre 200 mercados dos quais
184 nunca entram numa decisão seria cortar a coorte por um estado de um mercado que ela não habita.
(ii) **A política nomeia a série.** O corpo gravado é `{"breadth": {"window_m": 5, "min": "0.10",
"max": "0.60", "version": "breadth_v2"}}`; uma política sem `version` é recusada em vez de
completada com o padrão do build, que é exatamente como uma célula pré-registrada podia ser
reapontada para outro universo entre dois deploys.

## Os braços (nenhum existe)

Pai: **`mean_reversion v10`** sem portão — a coorte de 90 d × 16 mercados da EXP-0025 (798 decisões,
89 dias, expectativa ex-funding **−0,0293 R**, PF 0,910, IC 95 % [−0,1336; +0,0728], ou seja
indistinguível de zero). Decisão em 1 h, outcome em 1 min.

| braço | política | o que afirma | previsão |
|---|---|---|---|
| **A** (célula de dentro) | `breadth=0.10-0.60@breadth_v2` | a reversão compradora vive na amplitude intermediária | Δ > 0 contra o pai |
| **B** (falseamento) | `breadth=0.60-1.00@breadth_v2` | a venda generalizada é o pior lugar para comprar reversão (KB-0083) | Δ < 0, **pior** que o pai |

As faixas são as **da T3.77**, escritas antes de qualquer leitura desta série — não saem dos tercis
e não são ajustadas por eles. Meia-abertas no topo (`min <= valor < max`), então A e B ladrilham
[0,10; 1,00) sem sobreposição e sem buraco; `[0; 0,10)` fica deliberadamente fora dos dois (é o
"nada está caindo", e uma faixa que ninguém pré-registrou não ganha braço).

**Se B aprovar e A não**, a hipótese "a vantagem vive no meio" está **refutada** e o que sobra — "a
vantagem vive na venda generalizada" — nasce como candidata da EXP seguinte, com pré-registro
próprio. Não pode ser declarada vencedora nesta página.

## Os tercis, fixados em junho–julho (e só para a leitura descritiva)

**Regra de corte, congelada agora:** os dois limiares de tercil de `breadth_v2` são calculados sobre
as linhas `usable` de **2026-06-13 a 2026-07-31** (a janela de calibração), sobre **todos os
minutos**, não só os de decisão, e **nunca são recalculados**. A janela é **descartada** da leitura
descritiva: as três células são medidas sobre as decisões de **2026-08-01 a 2026-09-11**.

Por que assim: tercis recalculados sobre a amostra lida garantem células de tamanho igual e fazem o
corte depender do que se quer medir — o limiar viraria função do período e duas leituras sucessivas
não seriam comparáveis. Limiar fixo deixa as células desbalanceadas de propósito, e **o
desbalanceamento é informação**.

E por que isto é **descritivo e não a régua**: os braços A e B não usam tercil nenhum (as faixas são
da T3.77), então eles podem ser lidos sobre os **90 dias inteiros** — que é o que dá n e as três
janelas de 30 d que a régua exige. A leitura por célula existe para responder duas perguntas que a
régua não responde: **onde** as faixas caem na distribuição, e se o efeito é **monótono** nos tercis
(um efeito que aparece só na faixa pré-registrada e não ordena os tercis é um efeito de faixa, não
de estado).

`t1` = ______ · `t2` = ______ (preencher com os números medidos **antes** de olhar agosto–setembro).

## Regra de sucesso — congelada, mesma da EXP-0026/0028

**A quantidade pareada por (mercado, barra) mede zero por construção e isso está aqui, não no
rodapé do resultado.** Um portão de elegibilidade **não muda a decisão** numa barra elegível — ele
só **remove barras**. Sobre as barras elegíveis compartilhadas, filha e pai leem o mesmo contexto, o
mesmo `code_ref` congelado e os mesmos parâmetros, então o Δ pareado é **0 R** exceto pela
divergência de máquina de estados do slot (`docs/PIPELINE.md` §4b item 11: `INELIGIBLE` não arma a
barreira, logo a filha pode abrir um episódio numa barra que o pai nunca considerou). Essa
divergência é um **artefato de contabilidade**, não vantagem.

A quantidade que a hipótese afirma é **condicional contra incondicional**:

> **Δ = média de `r_ex_funding` das decisões do braço − média de `r_ex_funding` das decisões do pai
> na janela inteira**, por natureza **não pareada** (as duas populações não compartilham barras),
> com IC 95 % por **bootstrap de blocos de dia inteiro, não pareado**
> (`.claude/state/exp-drafts/t362b/blocos90.py`, 20 000 reamostragens, semente **20260912**).

**Aprova** o braço que cumprir **todas**:

1. Δ ≥ **+0,05 R** e o IC 95 % por blocos de dia **acima de zero**;
2. **n ≥ 100** desfechos avaliáveis **e** ≥ 30 dias distintos (régua editorial do Lab);
3. média de `r_ex_funding` **positiva em ao menos 2 das 3 janelas** de 30 dias;
4. **leave-one-market-out nunca negativo** (16 reajustes, um por mercado retirado);
5. o Δ **pareado** por (mercado, barra) sobre as barras elegíveis compartilhadas fica **dentro de
   ±0,02 R de zero** — não como prova de vantagem, e sim como **prova de que o portão é só um
   portão**: um Δ pareado grande significaria que a filha decide diferente do pai numa barra em que
   ambos são elegíveis, o que só pode ser divergência de slot (item 11) ou bug.

**Qualquer coisa a menos = `descartar`**, e a versão é aposentada pela via auditada
(`activate_strategy_version.py --deprecate`) no mesmo dia. **Um braço mudo** (n < 100) é `descartar
por população`, nunca "negativo": é ausência de amostra, não ausência de vantagem.

**Cláusula de falsificação adicional (o controle de identidade):** a mesma leitura é repetida com as
decisões do pai cortadas por `regime_hourly_v1` em vez de `breadth_v2`. Se o corte por regime
produzir um Δ **igual ou maior**, `breadth_v2` não é um estado novo — é o regime horário reamostrado
por minuto — e o veredito é `descartar` mesmo que os cinco itens passem.

**K4 e K5.** K4 (`unavailable`) **não é mensurável num braço com portão** (§4b item 12: `ineligible`
não é `unavailable`, e um portão que recusa muito faz `unavailable ≈ 0` parecer verde): é lido no
**pai**, na mesma janela, e a fração `ineligible` da filha é reportada como número próprio. K5: a
cobertura de `R_net` da coorte de 90 d da `v10` é **37,59 %** (o backfill de funding não alcança
junho–julho), então o eixo primário é **`r_ex_funding`** e toda tabela **declara o eixo**; `R_net` é
leitura secundária sobre agosto–setembro, onde o funding é conhecido.

## Previsões registradas antes da corrida (para poderem estar erradas)

1. **Distribuição.** `breadth_v2` não é simétrica em torno de 0,5; em janela calma a mediana fica
   entre 0,40 e 0,60 e a cauda alta (> 0,90) é rara. **Previsão: menos de 2 % dos minutos acima de
   0,90.** Com 16 mercados o valor é granular (16 passos de 0,0625), então espera-se **mais** massa
   nos extremos que a v1 mostraria — e isso é o principal risco de desenho desta série, declarado
   aqui: 16 é um denominador pequeno.
2. **Direção.** Δ do braço **B negativo** (o braço que deveria ser o pior), com a maior parte do dano
   em poucos minutos (o padrão do KB-0083), o que faz o IC de blocos de dia ser largo mesmo com o
   sinal presente. Δ do braço **A positivo mas pequeno** (< +0,05 R), isto é: **previsão de que A
   não aprova** pela régua, e o valor do experimento estará em B.
3. **Autocorrelação com o regime.** `breadth_v2` alto e `regime_hourly_v1 = BTC_BEAR` coincidem com
   frequência. **Se a faixa alta for só o `BTC_BEAR` com outro nome, a hipótese não acrescenta
   nada** — é o que a cláusula de identidade acima testa.
4. **População.** Com a série backfillada, `breadth_unavailable` no replay deve ficar **abaixo de
   1 %** das barras (só os minutos das pontas da janela e os dias que o relatório de cobertura
   reprovar). Acima de 5 %, o problema é a cobertura de velas dos 16 mercados, não a estratégia, e o
   EXP para até isso ser resolvido.

## Não-antecipação (o que está provado e o que custa)

A série dobra, para o minuto `T`, apenas velas com `open_time + 1 min <= T` — seis velas, de
`T−6min` a `T−1min` — e um mercado sem as seis não é contado
(`packages/indicators/tests/unit/test_breadth_series.py`, inclusive a prova de que mudar a vela que
**abre** no corte não move o número). O universo de v2 é resolvido **uma vez por passada**, com
`universe_as_of` e `universe_rule` gravados em `inputs`: a pertinência é uma propriedade do fold,
não uma afirmação sobre o minuto histórico (e perguntá-la a cada corte antigo responderia "ninguém",
porque nenhum mercado tinha 90 dias de velas retidas 90 dias atrás). O portão lê a linha cujo
`end_time` é **exatamente** o `source_bar_close`, **na série que a política nomeia**: sem
tolerância, sem "a mais recente antes", e uma linha de `breadth_v1` no mesmo minuto **não** responde
por uma versão presa a `breadth_v2` (`services/strategy-worker/tests/test_breadth_gate.py::
TestASerieEParteDaChave`). O custo declarado é que um produtor atrasado **emudece** a versão com
`breadth_unavailable` em vez de deixá-la decidir com um valor velho.

## H-P18 (dispersão BTC × alts): **não cabe nesta série** — lote posterior

A pergunta da Astra no plantão de 11/09 é se "a mediana dos 16 caindo −3,85 % com o BTC em −1,31 %"
é um estado que separa expectancy. Ela **não** é expressável em `breadth_v2`, e a razão é a própria
definição do fold: `compute_breadth` conta um mercado como "caindo" comparando **o próprio** close
dele em duas pontas de uma janela de 5 min com `<` estrito. H-P18 precisa de três coisas que não
existem ali: (i) horizonte de **24 h**, não 5 min; (ii) um **mercado de referência** (o BTC) dentro
do fold; (iii) comparação de **retornos**, não de sinal. Somar ou reinterpretar `breadth_v2` para
isso seria o erro que `hunter_indicators.regime.breadth` e `hunter_indicators.breadth` já existem
separados para evitar.

O que H-P18 custaria, para o lote que a pegar: uma série nova — `dispersion_24h`, "fração dos 16
cujo retorno de 24 h ficou abaixo do retorno de 24 h do BTC", ancorada no minuto, imutável, com o
mesmo formato de tabela e o mesmo piso de cobertura — reusando **sem mudança** duas peças que a
T3.88 já entregou: `hunter_core.universe` (o universo é o mesmo) e a forma do
`market_breadth`/`BreadthSpec` (versão = aritmética + universo). Estimativa honesta: a série e o
produtor são o trabalho de uma tarefa; o portão (`dispersion=`) é uma quarta regra do mesmo
envelope. **Nenhum braço de H-P18 nesta página.**

## Passos (nenhum executado)

1. commit + deploy da T3.88 (`breadth_v2`, `hunter_core.universe`, a política com `version`);
2. `backfill_breadth.py --days 90` **em modo relatório** na VPS via `compose.sh run --rm ops`, e
   **escrever a tabela de cobertura aqui** — é ela que diz se os 90 dias existem de verdade;
3. se o relatório passar, `--apply --reason "EXP-0027"` (129 600 minutos; ~3,5 min medidos em
   testcontainer local — a medida da VPS entra aqui);
4. fixar `t1`/`t2` sobre junho–julho e **escrever os números** antes de olhar agosto–setembro;
5. `derive_variant.py mean_reversion v10 --policy breadth=0.10-0.60 --changelog
   EXP-0027_amplitude_010_060 --dry-run` e o mesmo para `0.60-1.00`; ativar as duas como
   `research_only`;
6. replay de 90 d × 16 mercados por braço (~138 240 barras cada, ~25 min por braço no ritmo medido
   na T3.84), leitura pela régua acima, célula descritiva ao lado;
7. veredito por braço no mesmo dia; o que falhar é aposentado pela via auditada;
8. ≤ 10 linhas em português para o Everton.

## Registro de conferência (preencher depois da corrida, append-only)

| data | braço/célula | faixa | n | dias | `r_ex_funding` | Δ vs pai | IC 95 % (blocos de dia) | Δ pareado | eixo | veredito |
|---|---|---|---|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — | — | — | — | — |
