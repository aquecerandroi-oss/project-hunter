# R68 — pré-registo (congelado antes de qualquer teste)

Pergunta (Everton, 23/09/2026 12:1x BRT): "tentamos prever o futuro da próxima vela,
comprando antes e vendendo na alta". Duas partes, nesta ordem.

## 0. Dados e universos

Fonte: VPS, `candles`, `timeframe='1m'`, **só `is_final = true`**, 10,39 M linhas,
481 mercados, 2026-06-11 19:42 → 2026-09-23 14:58 UTC. Leitura read-only
(`COPY TO STDOUT`); nada escrito na VPS.

Constatação que condiciona o desenho (medida antes de escolher método):
a profundidade **não** é uniforme. Só **16 mercados** têm os 104 dias
(149 478 velas); 126 têm ~25 dias (desde 29/08); 339 têm menos.

- **U2 "profundo"** (universo primário da parte B): os 16 mercados com 11/06–23/09 —
  BTC, ETH, XRP, LINK, DASH, ZEC, BNB, DOGE, SOL, UNI, NEAR, ARB, SUI, TAO, PROM, SAHARA
  (perpétuas). É o único universo onde cabe um walk-forward com ≥ 10 dobras.
- **U1 "mesa"**: os mercados perpétuos correspondentes aos `spot_desk_markets` com
  `enabled = true` (35 linhas, 34 com velas). Só 8 deles estão em U2
  (ETH, LINK, ZEC, BNB, DOGE, UNI, ARB, TAO). Reportado como subgrupo em B e
  como universo próprio em A (onde 25 dias bastam para distribuições).
- **U3 "amplo"**: todos os mercados monitorados com ≥ 20 000 velas (janela 29/08–23/09).
  Só parte A + uma dobra de B como verificação.

## 1. Construção das barras e anti-look-ahead (a regra que matou a v1 do R66)

- Barra de horizonte `h` = agregação de `h` velas de 1 m numa grelha alinhada à época
  (bucket `b` cobre `[t, t+h)`), `open = open` da primeira, `close = close` da última,
  `high = max`, `low = min`, `volume/quote_volume/trade_count/taker_buy_volume = soma`.
- **Uma barra só existe se tiver as `h` velas, todas `is_final`.** Bucket incompleto é
  descartado (não interpolado) e o ponto de decisão que dependeria dele desaparece.
- **Instante de decisão** de um ponto = `close_time` da última barra usada como feature,
  isto é `bucket_start + h` minutos. Nenhuma feature pode ler uma linha cujo
  `close_time > decision_instant`.
- **Guarda no carregador:** `assert_causal(source_close_times, decision_instant)` levanta
  `LookAheadError` se alguma fonte fechar depois do instante de decisão. Testada com um
  caso que falha (a "estratégia batoteira" que lê a barra seguinte) e um que passa.
- Alvo: retorno close-to-close da barra que fecha **em** `decision_instant` para a barra
  que fecha em `decision_instant + h` min. Excursão favorável: `max(high)` das `h` velas
  seguintes sobre o `close` de decisão.

## 2. Parte A — o muro do custo

Horizontes `h ∈ {1, 5, 15, 60, 240}` minutos.

- Distribuição de `|retorno close-to-close|`: mediana, p25, p75, p90 (por mercado e agregado).
- Distribuição da excursão favorável (MFE) dentro do horizonte: mediana, p75, p90.
- **Taxa de acerto de equilíbrio** para uma regra long-only com payoff simétrico de
  magnitude `m` (= mediana de `|r|`, com p75 como sensibilidade) e custo de ida-e-volta `c`:
  `p* = 0,5 + c / (2m)`. Se `p* ≥ 1`, o custo come o movimento típico inteiro —
  nenhuma taxa de acerto empata.
- Custos: `c ∈ {0,14 %, 0,30 %, 0,50 %}` (0,14 % = ida-e-volta Jupiter medida no R63).
  **Mais** o custo fixo de rede: 0,0002 SOL num bilhete de 0,05 SOL = **0,40 %** do bilhete
  (suposição declarada: os 0,0002 SOL são o total da ida-e-volta, não por perna).
  Linha extra `c = 0,14 % + 0,40 % = 0,54 %`.

**Um horizonte "sobrevive a A"** se `p*` com `c = 0,54 %` e `m` = mediana de `|r|` ficar
**abaixo de 0,70**. Acima disso a regra teria de acertar 7 em 10 e não vale a pena
procurar preditor. (Limiar escolhido agora, antes de ver os números.)

## 3. Parte B — preditores pré-registados

Só informação disponível no instante de decisão. Em barras de horizonte `h`
(o preditor e o alvo vivem na mesma escala).

| id | preditor | regra long |
|---|---|---|
| P1 | `mom_prev` — sinal do retorno da barra anterior | `r_{-1} > θ` |
| P2 | `revert_z` — z-score do último retorno vs. 20 anteriores | `z < −θ` |
| P3 | `vol_surge` — `trade_count` da última barra / mediana das 60 anteriores | `> θ` |
| P4 | `taker_imb` — `taker_buy_volume / volume` da última barra | `> θ` |
| P5 | `hour_utc` — hora do dia | hora no subconjunto escolhido no treino |
| P6 | `breakout_20` — fecho acima da máxima das 20 barras anteriores (a regra do `momentum v3`) | booleano |

Grelha de limiares fixada agora: P1 `θ ∈ {0, 0.25σ, 0.5σ, 1σ}`; P2 `θ ∈ {1, 1.5, 2, 2.5}`;
P3 `θ ∈ {1.5, 2, 3, 5}`; P4 `θ ∈ {0.5, 0.55, 0.6, 0.65}`; P5 as k melhores horas do treino
com `k ∈ {3, 6, 12}`; P6 sem limiar.

## 4. Walk-forward

Rolante sobre 11/06–23/09: **treino 14 dias / teste 7 dias, passo 7 dias** (~12 dobras
em U2). O limiar é escolhido **no treino** maximizando o retorno líquido médio por
operação (custo 0,14 %); é avaliado **só na janela de teste seguinte**. Operações de
todas as dobras de teste são empilhadas. Nenhum ajuste depois de ver o teste.

## 5. Estatística

- Métrica primária: **retorno líquido médio por operação após custo** (0,14 %;
  sensibilidade 0,30 % e 0,54 %).
- Baselines: (i) **sempre long** no mesmo horizonte, em todos os pontos de decisão;
  (ii) **moeda ao ar** (seleção aleatória com a mesma taxa de entrada).
- Bootstrap de cluster **por mercado** (16 clusters em U2 — poucos, é ressalva declarada),
  5 000 reamostragens, IC 95 %.
- Teste de permutação: baralhar o rótulo do sinal dentro de blocos (mercado, dia),
  2 000 permutações.
- Correção de múltiplos testes: **Benjamini-Hochberg** sobre a grelha
  preditores × horizontes sobreviventes.

## 6. Regra de confirmação (congelada)

Uma célula (preditor × horizonte) **confirma** se e só se, na janela de teste empilhada:

1. retorno líquido médio por operação **> 0** com custo 0,14 %;
2. IC 95 % de bootstrap de cluster **inteiramente > 0**;
3. p de permutação ajustado por BH **< 0,05**;
4. **bate o "sempre long"** no mesmo horizonte, com IC 95 % da diferença > 0;
5. sobrevive ao custo 0,30 % com média ainda > 0 (robustez, não confirmação).

Falhar qualquer um dos 1–4 = **não confirmado** (que não é o mesmo que refutado).

## 7. Reconciliação obrigatória

R63 §3a mediu, em 7 dias nos 10 mercados da mesa: `momentum v3` **Σ R −42,87**
(223 sinais) e `mean_reversion` v14/v6 **+14,90** (23 sinais cada).
P6/P1 são a família momentum; P2 é a família reversão. O walk-forward tem de dizer
se reproduz a direcção (momentum perde, reversão ganha) ou a contradiz.

---

# EMENDA 1 — depois da revisão de desenho da Astra, ANTES de qualquer teste

Revisão em `.claude/state/astra-review-r68.md`. Nove must-fix; aceito oito inteiros e
um parcialmente. O protocolo congelado é **esta emenda**, não o texto acima.

**E1.1 (Astra #1, aceite).** `p* = 0,5 + c/(2m)` só vale para uma aposta que paga
exactamente `±m`. Com saída por tempo, o equilíbrio correcto é
`p* = (b + c) / (a + b)` com `a = E[r | r > 0]` e `b = −E[r | r < 0]` **médias
condicionais**, não medianas. A parte A passa a reportar as três coisas, rotuladas:
(i) o `p*` do modelo `±m` (didáctico, marcado como modelo); (ii) o `p*` correcto com
`a`/`b` incondicionais medidos; (iii) **`P(r_h > c)`** — a fracção de barras cujo
retorno futuro bate o custo, que é o número directo que Everton pediu. Retirada a frase
"nenhuma taxa de acerto empata": em `p* = 1` acertar sempre **empata**, não lucra.

**E1.2 (Astra #2, aceite).** **Cai o portão `p* < 0,70`.** A parte A é descritiva e não
elimina horizonte nenhum; a parte B testa **os cinco horizontes**. Uma mediana pequena
não impede que o sinal seleccione episódios raros que pagam o custo. MFE é oportunidade
retrospectiva, nunca saída realizável — fica rotulado como tal.

**E1.3 (Astra #3, aceite).** O bootstrap primário passa a ser **de blocos temporais
conjuntos**: blocos contíguos de **3 dias** de calendário, reamostrados com reposição,
**carregando todos os mercados do bloco juntos** (preserva o choque comum). O estimador
reamostrado é `Σ retorno / Σ operações` (por operação), nunca a média das médias.
3 dias fixado agora: o horizonte máximo é 240 min e a persistência dos sinais é intra-dia,
logo 3 dias é > 10× a escala de dependência, e 104 dias dão ~35 blocos. O bootstrap por
mercado (16 clusters) fica como **diagnóstico secundário**, com a ressalva da Astra.

**E1.4 (Astra #4, aceite).** **Cai o teste de permutação como p-valor.** Baralhar o sinal
dentro do dia destrói a autocorrelação em rajada que é exactamente o que o sinal apanha,
e o nulo resultante é fácil demais. O p-valor passa a ser **de bootstrap de blocos
centrado sob o nulo** (p = fracção de reamostragens cuja estatística centrada excede a
observada, bilateral). A selecção aleatória com a mesma taxa de entrada fica como
**diagnóstico**, sem p-valor.

**E1.5 (Astra #5, aceite).** **Análise primária = limiares fixos**, congelados agora;
a escolha no treino passa a análise secundária pré-especificada (e o objecto testado
nesse caso é o algoritmo inteiro). Limiares fixos: P1 `r_{-1} > 0`; P2 `z < −2`
(z sobre as 20 barras anteriores, warm-up 21 barras); P3 `trade_count / mediana(60
anteriores) > 2`, warm-up 61 barras, denominador 0 → ponto descartado;
P4 `taker_buy_volume / volume > 0,55`, `volume = 0` → descartado;
P5 as horas UTC — **sem limiar fixo possível**, por isso P5 **só existe na análise
secundária** e é reportado como exploratório (em h = 240 min só há 6 fatias horárias,
`k ∈ {1,2,3}`); P6 `close > max(high das 20 barras anteriores)`, warm-up 21 barras.
Limiar **comum ao painel**, nunca por mercado. σ estimado na janela de treino.
Mínimo **30 operações** numa célula para ela ser avaliável; abaixo disso →
`sem_potencia`, nunca "não confirma". Empate na grelha → o limiar mais conservador
(menos entradas).

**E1.6 (Astra #6, aceite).** (a) **Purga/embargo:** a janela de treino termina `h` minutos
**antes** da fronteira, para que nenhum rótulo usado no ajuste termine dentro do teste.
(b) A entrada ao `close` da barra de decisão é **proxy de retorno**, não execução
demonstrada — dito assim no relatório. (c) Sensibilidade obrigatória: **entrada
atrasada uma barra** (decide no fecho de `b`, entra no fecho de `b+1`, sai em `b+1+h`).
Se a vantagem morre com um atraso de uma barra, ela não é da mesa.

**E1.7 (Astra #7, aceite).** **Numerário.** A mesa quer acabar com mais **SOL**. Além do
retorno token/USDT, reporto o retorno **token/SOL** = `(1+r_token) / (1+r_SOL) − 1`
usando o SOLUSDT perpétuo do mesmo minuto (existe em U2). Custo: o teste primário
reporta `c = 0,14 %` (medido, R63) **e** `c = 0,54 %` (0,14 % + 0,40 % de rede:
0,0002 SOL num bilhete de 0,05 SOL, suposição declarada, ida-e-volta total).
**Confirmar para a mesa exige lucro a 0,54 %**; a 0,14 % é "vantagem no proxy".
U2 são **perpétuos** — a conclusão máxima possível é "vantagem no proxy de perpétuos";
a transferência para spot Solana não fica demonstrada por este estudo.

**E1.8 (Astra #8, aceite).** Sem filtro de A: as células ficam **congeladas em
5 horizontes × 5 preditores fixos (P1–P4, P6) = 25**. Correcção de multiplicidade:
reporto **BH** (como o brief pediu) **e Holm**; a **confirmação exige Holm**, porque o
objectivo aqui é "existe pelo menos uma vantagem" e isso é controlo familiar, não FDR.
U1/U3 não são replicações independentes de U2 (partilham mercados e datas) — entram
como subgrupo descritivo e **não podem confirmar sozinhos**.

**E1.9 (Astra #9, aceite).** (a) Baselines calculados **na mesma população elegível**
do sinal (mesmas barras, mesmo warm-up). (b) Censura publicada: quantos pontos de decisão
perderam o rótulo por falta de barra de saída, e a média com esses pontos marcados a
zero como sensibilidade. (c) **Ganho mínimo economicamente relevante (MRE) = +0,10 %
líquido por operação**, fixado agora. Regra de encerramento:
- limite inferior do IC 95 % **> 0** (e Holm < 0,05) → **evidência favorável** no escopo;
- limite superior do IC 95 % **< MRE** → **evidência contra** uma vantagem útil à mesa;
- intervalo a atravessar → **inconclusivo / sem potência**.

**E1.10 (nice-to-have aceites).** Reportar contribuição por mercado e por dobra,
concentração nas maiores operações, estabilidade entre limiares vizinhos (sem escolher
outro vencedor depois), e frequência/exposição ao lado da média por operação.
Seeds fixadas: bootstrap `seed = 68`.

**Rejeito (parcialmente) uma coisa.** A Astra sugere reservar uma avaliação **prospectiva**
com prazo fixo para concluir sobre a mesa. Concordo com o princípio e **não** o faço neste
estudo: o R68 tem de responder hoje se vale a pena continuar. Fica escrito que qualquer
"confirma" deste estudo é **candidato a sombra**, nunca parâmetro de mesa real — que é
exactamente o que o R67 decidiu para o `buys_1m`.
