---
tags: [knowledge, nota, analise-tecnica, candlestick, padroes, literatura, data-snooping, m3]
tema: padrões de candlestick — o que a evidência publicada diz (ações diárias, cripto diário, cripto horário) antes de medirmos no nosso dado
fonte: Marshall, Young & Rose (2006, J. Banking & Finance 30, 2303–2323 — lido na versão working paper "Market Timing with Candlestick Technical Analysis", mesmos autores e dados); Caginalp & Laurent (1998, Applied Mathematical Finance 5, 181–205); Park & Irwin (2004, AgMAS 2004-04, versão longa do artigo de 2007 no J. Economic Surveys 21, 786–826); Ho, Chan, Pan & Li (2021, IEEE Big Data); Cohen (2021, Rev. Quant. Finance & Accounting 57); Kuna (2025, tese de bacharelado, Charles University); Moser & Brauneis (2026, Int. Review of Economics & Finance 108, 105158 — NÃO aberto); Shanaev, Vasenin & Stepanov (2023, Heliyon); Jönsson (2016, tese, Lund); Vahidpour et al. (2024, Romanian J. Inf. Tech. & Automatic Control 34); Uzun et al. (2024, Computation 12); código-fonte do TA-Lib
fonte_url: ver §Fontes — cada URL com o que foi de fato aberto e o que devolveu 403
lido_em: 2026-09-09
evidencia: estudos revisados (Marshall; Caginalp; Park & Irwin; Cohen; Ho et al.) + duas teses (Kuna 2025; Jönsson 2016) + um artigo revisado citado só pelo resumo indireto (Moser & Brauneis 2026) + código (TA-Lib); nenhuma medição própria — a medição é a T3.55b
hipotese_testavel: sim (T3.55b — lista de padrões e definições na §7)
astra: pendente
status: rascunho em exp-drafts (a Sexta-feira arquiva como KB-0080)
owner: sexta-feira
updated: 2026-09-09
confiança: "?"
---

# KB-0080 — padrões de candlestick: o que a evidência publicada diz (e o que ela não diz sobre perps a 15 m / 1 h)

> Rascunho da parte (a) da T3.55 (`.claude/state/brief-T3.55-candlestick.md`), escrito pelo agente de
> literatura em 2026-09-09 entre 00:00 e 00:30 (Brasília; 03:00–03:30Z). **Nada aqui é medição nossa.**
> Toda fonte listada foi aberta nesta sessão, exceto uma, que está marcada como não aberta em três
> lugares (frontmatter, §2.7 e §Fontes). Nenhum número foi citado de memória. A resposta ao "já estudou
> sobre o candlestick?" do Everton (2026-09-08 23:40) é a §6; a lista para a T3.55b é a §7.

## 1. O que afirma (a literatura, nas minhas palavras)

Padrões de candlestick são regras de uma a três barras sobre a relação entre abertura, máxima, mínima e
fechamento, com um contexto de tendência. A literatura séria diz três coisas, e elas se contradizem
menos do que parece:

1. **Em ações diárias, o único resultado positivo forte não sobreviveu a um teste melhor.** Caginalp &
   Laurent (1998) acharam, em todas as ações do S&P 500 de 1992–96, que oito padrões de três dias
   acertam a direção 71% das vezes contra 45% do acaso e rendem 0,56–0,76% líquidos em ~2 dias.
   Marshall, Young & Rose (2006), com bootstrap sobre os componentes do DJIA de 1992–2002 e 28 regras
   (inclusive as de três barras do Caginalp), não acharam **nenhuma** regra melhor do que o acaso — e as
   cinco significâncias que o t-test mostrou tinham **o sinal errado**.
2. **A literatura de "padrões gráficos" é a que menos trata data snooping** (Park & Irwin 2004/2007), e
   os lucros de análise técnica em ações desaparecem depois dos anos 1980.
3. **Em cripto**, os dois estudos diários abertos (Ho et al. 2021; Kuna 2025) não acham nada nas moedas
   grandes; o único estudo intradiário (Moser & Brauneis 2026, horário, ~400 moedas, com correção de
   snooping) reporta que um punhado de padrões — harami de alta/baixa, hikkake, enforcado — sobrevive.
   Esse é também o único que **não consegui abrir**; o que sei dele é o resumo.

## 2. Onde foi mostrado — um estudo por vez

A tabela tem o que o brief pediu: amostra, timeframe, padrões, período de manutenção, resultado líquido
de custos, e se sobrevive a teste múltiplo. O detalhe está abaixo dela.

| estudo | amostra | timeframe | padrões | manutenção | resultado (custos?) | teste múltiplo? |
|---|---|---|---|---|---|---|
| Caginalp & Laurent 1998 | S&P 500 (lista de 1996), 02/01/1992–14/06/1996; + 54 fundos fechados mundiais 1992–96 | diário | 8 reversões de 3 barras (TWS, TBC, TIU, TID, TOU, TOD, MS, ES), **sem** condições de magnitude | ~2 dias (compra no fechamento, vende ⅓ em cada um dos 3 dias seguintes) | +0,9% bruto por trade comprado, **+0,56 a +0,76% líquido** de comissão + spread de 0,1–0,3%; +0,27% bruto vendido | **não**; Z = 36 admitido como superestimado por dependência (cai a 6,6 com n/30) |
| Marshall, Young & Rose 2006 | 35 componentes do DJIA, 01/01/1992–31/12/2002 | diário | 14 linhas simples + 14 reversões (martelo, engolfo, harami, três dentro/fora, estrela cadente, enforcado, doji, marubozu…) | 10 dias (2 e 5 "muito parecidos") | **nada significativo** no bootstrap (500 séries/ação, RW, AR(1), GARCH-M, EGARCH); custos nem precisaram ser descontados | não formal; argumento de fora-da-amostra (regras japonesas de arroz testadas em ações americanas) |
| Park & Irwin 2004 (rel.) / 2007 (JES) | revisão de 92 (2004) / 95 (2007) estudos "modernos" | vários | todas as classes; candlestick só via Caginalp | — | 58/24/10 (2004) e 56/20/19 (2007) positivos/negativos/mistos | **é o ponto**: "data snooping, seleção ex post das regras, dificuldade de estimar risco e custos" |
| Ho, Chan, Pan & Li 2021 | 23 maiores criptos por capitalização, até 08/07/2021 | diário | 68 padrões | ? (não aberto além do resumo) | "de pouca utilidade"; muitos com acurácia baixa | ? |
| Cohen 2021 | BTC, 2012 – jul/2020 | não dito no resumo | engolfo, harami, kicker + versões "invertidas" | sistema de trading (saídas próprias) | engolfo PF 3,54; harami invertido e kicker invertido lucrativos (PP 74,36%, PF 6,92) | **não** — as formações foram alteradas *para* melhorar o resultado (snooping por construção) |
| Kuna 2025 (tese) | 589 criptos (Yahoo/CoinMarketCap), até 20/12/2024; 5 conjuntos (top 17; top 300; 589; 589 − top 17; 23 stablecoins) | diário | 41 padrões, definições do TradingView (Pine v5) | 1, 2, 3, 5, 10 dias, saída Caginalp–Laurent | **custos ignorados de propósito**; top 17: **nenhum** padrão passa; 589: 8 de 41 passam em algum horizonte, 2 deles com sinal invertido | não (binomial + t ajustado por assimetria, p < 0,05, sem correção) |
| Moser & Brauneis 2026 — **não aberto** | ~400 criptos, ~2000 pares, 36 corretoras, 07/2018–01/2022 | **horário** | 55 padrões de reversão | ? | harami de alta e hikkake → retorno positivo; harami de baixa e enforcado → negativo; robusto a corretora, período, volume, volatilidade | **sim**: teste stepwise SPA (superior predictive ability) |
| Shanaev, Vasenin & Stepanov 2023 | BTC em 7 corretoras, 1 min, até 31/12/2021; fora-da-amostra jan–ago/2022 | 1 min | não é padrão — é a **virada da vela de 15 m** | por minuto | +0,58 bps/min nos minutos 0/15/30/45; outros minutos negativos; **líquido** de taxa e spread da Bitfinex com US$ 5 k | OLS, quantílica, TGARCH-M, Chow; efeito nasce em meados de 2020 |
| Jönsson 2016 (tese, Lund) | 29 ações do OMXS30, 19/10/2007–30/12/2015 | diário | candlesticks (método de Marshall) | curto | "pouco valor"; suporte à hipótese fraca de eficiência | bootstrap GARCH-M |

### 2.1 Caginalp & Laurent (1998) — o "sim" mais forte, e por que ele é frágil

Lido inteiro (PDF de 25 páginas). Dois conjuntos: 54 fundos fechados mundiais (Barron's) de 04/01/1992
a 07/06/1996, e **todas** as ações do S&P 500 (lista de 1996) de 02/01/1992 a 14/06/1996, OHLC diário.
Oito padrões de reversão de **três dias**, definidos só com desigualdades entre abertura e fechamento —
os autores **retiraram** de propósito toda condição de magnitude ("dia longo") para manter o teste
não-paramétrico. A tendência é a média móvel de 3 fechamentos caindo por 6 dias com no máximo uma
violação (Definição 3.1).

O teste central não é de retorno, é de **direção**: entre os pontos em tendência de baixa, a fração em
que `P(t+3) < média(P(t+4), P(t+5), P(t+6))` é 45,05% sem padrão e **71,22% com padrão** (n = 4.688);
para reversões de alta para baixa, 52,78% contra 67,33% (n = 8.391). O Z de 36 desvios que dá manchete
é reconhecido no próprio texto como superestimado por correlação entre ações e sobreposição temporal;
eles reduzem n por 30 e chegam a Z = 6,58 e 4,88. O lucro: comprar no fechamento do terceiro dia e
vender um terço em cada um dos três dias seguintes rende **0,9% bruto** por trade nos quatro padrões de
alta (média de ~2 dias em posição), 0,27% nos vendidos; **líquido** de comissão e spread de 0,1–0,3%,
**0,56 a 0,76%**. Sem bootstrap, sem correção de múltiplas hipóteses, sem risco. O padrão mais forte
é o *three inside up* (81% de acerto em 16 casos no conjunto pequeno).

### 2.2 Marshall, Young & Rose (2006) — o "não" com o teste certo

A página do artigo no ScienceDirect devolveu 403 (a entrada do EconPapers abriu, sem resumo). Li a
versão working paper dos mesmos autores, mesmos dados e mesmas tabelas ("Market Timing with Candlestick
Technical Analysis", Massey University), que remete ao JBF 2006 "para resultados mais detalhados".
Dados: as ações componentes do DJIA entre 01/01/1992 e 31/12/2002 (35 ações), preços da Reuters e
dividendos do CRSP. **Escolha explícita contra data snooping**: regras desenvolvidas com arroz japonês
testadas em ações americanas.

Universo: 14 linhas simples (long white/black, marubozus, doji libélula/lápide, guarda-chuva, estrela
cadente) e 14 padrões de reversão (martelo, engolfo de alta/baixa, piercing, harami de alta/baixa, três
dentro/fora para cima e para baixo, pinça, enforcado, dark cloud cover). Tendência prévia: **EMA de 10
dias** (Morris), com robustez ao comprimento. Entrada no fechamento do dia **seguinte** ao sinal
(entrar no próprio fechamento do sinal exige adivinhar o fechamento — argumento de anti-antecipação
que é exatamente o nosso). Manutenção de 10 dias; 2 e 5 dão "resultados muito parecidos".

Resultado no t-test (Tabela 1): nenhuma linha ou padrão de alta é significativo; quase todos os t são
**negativos** (retorno condicional menor que o incondicional); *opening white marubozu* é negativo a
1%; *long black* e *black marubozu* — supostamente baixistas — têm retorno **positivo** a 5%.
Martelo (57 sinais), engolfo de alta (252), harami de alta (115), três dentro para cima (17): t
positivos, nenhum significativo. Resultado no bootstrap (Tabela 2, 500 séries por ação com nulos RW,
AR(1), GARCH-M e EGARCH, estendidos para gerar OHL): p-valores das compras entre 0,35 e 0,70 — **nada**.
Conclusão deles: "candlestick trading rules are not profitable when applied to DJIA component stocks".
Custos não são descontados porque não há o que descontar. Dois sub-períodos dão o mesmo.

Um detalhe importante para nós: 17 ocorrências de *three inside up* em 35 ações × 11 anos. Os padrões
de três barras com contexto são **raros** no diário; a 15 m nós teremos milhares, e é aí que a
inferência muda de natureza (§5).

### 2.3 Park & Irwin (2004 / 2007) — o enquadramento

Li o relatório AgMAS 2004-04 inteiro (65 páginas), que é a versão longa do artigo do *Journal of
Economic Surveys* (2007), cuja página de resumo abri em experts.illinois.edu. Contagem: 92 estudos
modernos no relatório (58 positivos, 24 negativos, 10 mistos); 95 no artigo (56/20/19). Frase que
importa: a maioria "sofre de problemas de procedimento: data snooping, seleção ex post das regras ou
das tecnologias de busca, e dificuldade de estimar risco e custos". Sobre a categoria "padrões
gráficos", onde Caginalp & Laurent está: "a maioria dos estudos nesta categoria não fez otimização de
parâmetros nem teste fora-da-amostra, nem deu muita atenção a data snooping". Em ações americanas, os
lucros técnicos existem até o fim dos anos 1980 e não depois (a melhor regra de Sullivan, Timmermann &
White 1999 rende 2,8% ao ano, insignificante, em 1987–96). Isto já está em
[[KB-0003-rompimento-de-canal-e-data-snooping]]; aqui só acrescento que candlestick é o caso extremo
da família: muitas regras, poucas ocorrências cada, nenhuma correção.

### 2.4 Ho, Chan, Pan & Li (2021) — cripto diário, 68 padrões, nada

Só o resumo (via API do Semantic Scholar; ResearchGate e IEEE Xplore devolveram 403/vazio). Dados
diários das 23 maiores criptos por capitalização; 68 padrões "comumente usados"; conclusão: "os
padrões estudados são de pouca utilidade em cripto", com muitos de acurácia baixa e alerta de sinais
falsos. Método, custos e correção múltipla: não sei — não li.

### 2.5 Cohen (2021) — o "sim" que não conta

Resumo aberto na página da Springer. BTC de 2012 a julho de 2020, três padrões clássicos (engolfo,
harami, kicker); engolfo com *profit factor* 3,54; harami clássico falha; harami e kicker
**invertidos** dão lucro (kicker invertido: 74,36% de trades vencedores, PF 6,92); "todos os padrões
preveem melhor tendências longas do que curtas". É um sistema de trading otimizado sobre a própria
amostra, sem teste estatístico e sem custos no resumo. Vale como **anedótico** e como aviso: um
padrão que só funciona invertido é um padrão sem informação.

### 2.6 Kuna (2025) — cripto diário em escala, sem custos, e o problema do gap

Tese de bacharelado (Charles University), lida inteira. Yahoo Finance (agregado do CoinMarketCap) até
20/12/2024, cinco conjuntos: A = top 17 (37.065 dias), B = top 300, C = 589 criptos (782.172 dias),
D = C sem o top 17, E = 23 stablecoins. 41 padrões com as definições **exatas do TradingView** (Pine
v5, traduzidas para R). Tendência = fechamento acima/abaixo da SMA50. Saída Caginalp–Laurent em 1, 2,
3, 5 e 10 dias. **Custos ignorados de propósito** (§3.5 da tese). Quatro condições: média > 0, acerto
> 50%, binomial p < 0,05, t ajustado por assimetria p < 0,05 — sem correção por 41 × 5 testes.

Resultados: **no top 17, nenhum padrão passa em nenhum horizonte.** No conjunto de 589: martelo (3
dias), harami-cruz de alta (10 dias), *on neck*, *rising window* e — com o sinal **invertido** —
estrela cadente e sombra superior longa. Oito de 41 "úteis" em algum horizonte, dois deles
reclassificáveis. O próprio autor: "esses achados sublinham a inconfiabilidade inerente" e admite
viés de sobrevivência, dado agregado não negociável e sensibilidade às escolhas. Nas stablecoins,
doji star "funciona" porque a paridade volta ao peg — o artefato que mostra por que o **baseline
pareado** importa.

Duas observações operacionais que levo para a §7: (i) *kicking* e *abandoned baby* tiveram **zero**
ocorrências em 782 mil dias — mercado 24/7 não tem gap; (ii) o pipeline "definição do TradingView →
tradução → teste" é reproduzível e é o que faz a comparação entre estudos falhar quando as definições
divergem (a última limitação listada por ele).

### 2.7 Moser & Brauneis (2026) — o único intradiário, e o único que não abri

**Não aberto.** ScienceDirect (página e PDF "open access") e ResearchGate devolveram 403; o
Semantic Scholar não tem o resumo; o Crossref confirma só os metadados: *International Review of
Economics & Finance*, vol. 108, art. 105158, DOI `10.1016/j.iref.2026.105158`, junho de 2026, autores
Stefanie Moser (Klagenfurt) e Alexander Brauneis (Klagenfurt/NTU). O que segue vem de trechos do
resumo devolvidos por buscas, não de leitura: OHLC **horário** de 07/2018 a 01/2022, ~400 criptos,
~2.000 pares, 36 corretoras (~200 milhões de observações), 55 padrões de reversão; harami de alta e
hikkake precedem retornos positivos significativos, harami de baixa e enforcado precedem quedas;
lucratividade avaliada com **teste stepwise SPA** contra data snooping; resultados estáveis no tempo,
entre regimes, moedas e corretoras, e não explicados por volume nem volatilidade. **Não sei** o
horizonte, o tamanho do efeito em bps, nem se é líquido de custos. É a fonte que a Sexta-feira mais
precisa abrir depois (biblioteca, autor, ou versão working paper) antes de a T3.55b se apoiar nela.

### 2.8 Shanaev, Vasenin & Stepanov (2023) — não é padrão, mas mora na nossa barra

Aberto no PMC. BTC em sete corretoras, velas de 1 min até 31/12/2021, fora-da-amostra jan–ago/2022.
Retorno médio de **+0,58 bps por minuto** concentrado nos minutos 0, 15, 30 e 45 de cada hora; os
outros minutos têm média negativa; t > 9 em 2021; robusto em regressão quantílica e TGARCH-M; nasce em
meados de 2020; **líquido** de taxa e spread da Bitfinex a partir de US$ 5 k. Os autores atribuem a
algoritmos que reagem ao fechamento da vela de 15 m. Para nós isto é uma **variável de confusão
conhecida**: detectamos no fechamento da barra de 15 m, exatamente onde esse efeito vive. Como o
baseline da T3.55b é "mesmo mercado, mesma hora, barras sem padrão", e toda barra de 15 m fecha em
:00/:15/:30/:45, o efeito entra igual no padrão e no baseline — mas a magnitude dele (bps) é a régua
do que um "efeito de padrão" intradiário pode ter de tamanho.

### 2.9 Os que só servem de contexto

- **Jönsson (2016, Lund)** — 29 ações do OMXS30 de 2007–2015 com o método de Marshall (GARCH-M +
  bootstrap): "pouco valor". Lido o resumo em sueco e inglês. É a replicação independente do "não".
- **Vahidpour, Daneshvar, Amini Khouzani & Homayounfar (2024)** — 20 criptos da Binance, 2022–23,
  diário **e horário**, 48 padrões (118.674 ocorrências horárias) como entrada de LSTM. Lido o resumo
  e a seção de dados. Não testa os padrões sozinhos; os autores mesmos escrevem que "a eficácia
  isolada deles é limitada". Serve só para dizer que 48 padrões a 1 h em 2 anos × 20 moedas dão ~120
  mil ocorrências — a nossa escala.
- **Uzun, Lobachev et al. (2024, Computation)** — ferramenta de reconhecimento em BTC/ETH/LTC; resumo
  via Crossref; não testa poder preditivo.
- **Hudson & Urquhart (2021)** — já em [[KB-0003-rompimento-de-canal-e-data-snooping]]: ~15 mil regras
  em cripto, significância corrigida que vira desempenho **negativo** fora-da-amostra. Não reaberto.

## 3. Como mediríamos aqui

É a T3.55b, e o brief já fixa quase tudo: barras de 15 m e 1 h dobradas do 1 m com completude (`count
= 15`/`60`), 31 dias, os 20 perps mais líquidos + 4 mercados de replay; detecção **só no fechamento da
última barra do padrão** (a regra de Marshall: quem entra no fechamento do sinal está adivinhando o
fechamento); retorno futuro em 1/4/16 barras contra baseline pareado (mesmo mercado, mesma hora do
dia, barras sem o padrão); IC por bootstrap de blocos de dia (`t342-blocos/blocos.py` sem alteração);
Holm sobre padrões × timeframes. O que a literatura acrescenta ao desenho:

- **direção antes de retorno.** O teste de Caginalp (fração em que o fechamento futuro fica do lado
  previsto) é barato, não-paramétrico e menos sensível a cauda do que média de retorno; vale reportar
  as duas coisas;
- **baseline pareado é a única defesa contra o artefato das stablecoins de Kuna** e contra o
  turn-of-the-candle de Shanaev: o efeito de "hora" e de "minuto da hora" tem de estar igual nos dois
  lados;
- **contexto de tendência é parte da definição, não filtro opcional** (Caginalp §2.1: "um padrão de
  três dias sem a tendência certa é irrelevante"). Mas Kuna usa SMA50 e Marshall EMA10 — a escolha
  muda o n por uma ordem de grandeza. A §7 fixa uma e declara a outra como sensibilidade;
- **sem gap.** Padrões que exigem gap têm zero ocorrências em 24/7 (Kuna). Estrela da manhã/noite e
  harami são redefinidos por **não-sobreposição de corpos com igualdade permitida**, porque
  `open[t] = close[t−1]` é o caso normal aqui;
- **a lente do pedágio** ([[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]],
  [[KB-0076-por-que-perdemos-2026-09-08]]): cada padrão tem uma invalidação natural (a mínima do
  martelo, a máxima da estrela cadente, a mínima da estrela…) e ela fica a uma fração de ATR do
  fechamento. A §7 lista a invalidação de cada um para a T3.55b converter em `custo_R`.

## 4. Hipótese testável no Lab

Sem `Strategy` ainda — a T3.55 é explícita: **antes de qualquer estratégia**. A hipótese da T3.55b:

> H1: para pelo menos um padrão da §7, em pelo menos um timeframe, o retorno futuro médio em 4 barras
> (direção prevista) menos o do baseline pareado tem IC de 95% por blocos de dia inteiramente acima de
> zero **depois de Holm** sobre (padrões × timeframes).
> H1' (direcional): a fração de acertos de direção em 4 barras difere da do baseline com o mesmo IC.
> Refutação: nenhum IC cruza zero para o lado certo → "painel", e a nota vira registro.

Se H1 sobreviver, o candidato a contrato é o padrão vencedor **condicionado a linha**
(`tl_scan` congelado, [[KB-0077-linhas-de-tendencia]]) e a regime do BTC, com stop na invalidação
natural e alvo em múltiplo dela — e só então se olha `custo_R`. O que a literatura permite prever: se
existir, o efeito bruto por barra a 15 m é de **poucos bps**, o que a régua de KB-0008 transforma em
`custo_R` desconfortável.

## 5. Por que pode falhar

- **Múltiplas hipóteses por construção.** 11 famílias × 2 lados × 2 timeframes × 3 horizontes é 132
  testes antes de qualquer condicional. Holm é o mínimo; a versão SPA stepwise (Moser & Brauneis) é a
  correta quando os testes compartilham a mesma série. Sem isso a T3.55b repete o erro que Park &
  Irwin apontam há vinte anos.
- **Ocorrências dependentes.** A 15 m um martelo em 20 perps no mesmo minuto é **um** evento de
  mercado, não vinte. O bloco de dia carrega todos os mercados juntos — é o que resolve isto, e é por
  isso que `blocos.py` não pode ser alterado.
- **Definição decide o resultado.** Marshall (EMA10), Caginalp (MA3 caindo 6 dias), Kuna (SMA50) e
  TA-Lib (médias de corpo/amplitude em 10 barras) são quatro régua diferentes para "tendência" e
  "longo". A §7 fixa uma em ATR — que é a régua do resto do sistema — e a sensibilidade fica para
  depois do resultado, nunca antes (regra de
  [[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]).
- **31 dias é um regime.** Kuna vê os mesmos padrões passarem em C e D e falharem em A; Shanaev vê o
  efeito de 15 m nascer em 2020. Um mês diz o que aconteceu num mês.
- **Sinal invertido é sinal de ruído.** Estrela cadente "bullish" (Kuna), marubozu preto com retorno
  positivo (Marshall), harami que só funciona ao contrário (Cohen). Se a T3.55b achar um padrão
  significativo **contra** a direção clássica, a leitura default é artefato, não descoberta.
- **Custos.** Nenhum estudo de cripto aberto desconta custos de perpétuo (funding, taker, spread);
  Caginalp desconta 0,1–0,3% de spread em ações de 1996. O único resultado "líquido" intradiário é o
  de Shanaev, e é de fração de bp por minuto.

## 6. Veredito (≤ 10 linhas)

1. **Ações diárias:** o "sim" de Caginalp & Laurent (1998: 8 padrões de 3 barras, +0,56–0,76% líquido em ~2 dias, S&P 500 1992–96, sem correção múltipla) **não sobreviveu** ao bootstrap de Marshall, Young & Rose (2006: 28 regras, DJIA 1992–2002, nada acima do acaso, cinco significâncias com o sinal errado). Jönsson (2016) replica o "não" na Suécia.
2. **Enquadramento:** Park & Irwin — padrões gráficos são a categoria que menos trata data snooping; lucros técnicos em ações somem depois dos anos 80.
3. **Cripto diário:** Ho et al. (2021, 68 padrões, 23 moedas) e Kuna (2025, 41 padrões, 589 moedas, sem custos) — **nada nas grandes**; um punhado nas pequenas, dois com sinal invertido, sem correção. Cohen (2021, engolfo PF 3,54 em BTC) é otimização in-sample: anedótico.
4. **Cripto horário:** Moser & Brauneis (2026, ~400 moedas, 2018–22, SPA stepwise) — harami de alta/baixa, hikkake e enforcado sobrevivem. É a única evidência intradiária com correção de snooping **e eu não a li** (403 em todos os hosts); tamanho do efeito e custos desconhecidos.
5. **Prior honesto para perps a 15 m / 1 h:** se existe efeito, é de poucos bps por barra (a régua é o turn-of-the-candle de 0,58 bps/min de Shanaev 2023), ou seja, **abaixo do pedágio** de KB-0008 para um stop de fração de ATR. A única família com alguma sustentação intradiária é **harami / engolfo / martelo-enforcado em contexto de tendência**, mais plausível a 1 h do que a 15 m. O resto entra na T3.55b como painel, não como candidato.
6. Padrões que dependem de gap não existem em 24/7: definir sem gap (§7).

## 7. Os padrões a medir na T3.55b — definições determinísticas, em ATR e frações de amplitude

Notação por barra `t`: `O, H, L, C`; `corpo = |C − O|`; `amp = H − L`; `sup = H − max(O, C)`;
`inf = min(O, C) − L`; barra **de alta** ⇔ `C > O`; **de baixa** ⇔ `C < O`. Tudo é `Decimal`: só
comparações e multiplicação por constantes decimais; nenhuma divisão, nenhum float.

**Escala.** `atr_ref = ATR14 de Wilder (wilder_v1, o mesmo do sistema) fechado na barra anterior à
primeira barra do padrão` (`t0 − 1`). A barra não é a própria régua (mesma razão da regra 2 de
[[KB-0077-linhas-de-tendencia]]). Sem 15 barras de aquecimento, ou com `atr_ref = 0` ou `amp = 0`
em qualquer barra do padrão, **não há padrão**.

**Contexto de tendência** (avaliado em `t0 − 1`, a barra antes do padrão; `EMA10` de fechamentos):
`baixa(t0) := C[t0−1] < EMA10[t0−1] e EMA10[t0−1] < EMA10[t0−4]`; `alta(t0)` é o espelho. É a régua
de Marshall (EMA10) com uma condição de inclinação para não chamar de tendência uma fita lateral.
**Sensibilidade declarada, a rodar só depois do resultado:** MA3 monótona por 6 barras com ≤ 1
violação (Caginalp) e fechamento vs SMA50 (Kuna).

**Detecção só no fechamento da última barra do padrão** (`t0 + k − 1`); o retorno futuro começa na
barra seguinte. Padrões de 1 barra: `t0` é a barra; de 2: `t0, t0+1`; de 3: `t0, t0+1, t0+2`.
**Sem gap** em nenhuma definição: onde o clássico pede gap, pede-se não-sobreposição de corpos com
igualdade permitida, porque `O[t] = C[t−1]` é a regra em 24/7 (Kuna: zero *kicking* em 782 mil dias).

| # | padrão (direção) | barras | contexto | definição (todas as condições, E) | invalidação natural |
|---|---|---|---|---|---|
| P1 | **Martelo** (alta) | 1 | `baixa(t0)` | `amp ≥ 0.8·atr_ref`; `corpo ≤ 0.35·amp`; `inf ≥ 2·corpo`; `sup ≤ 0.1·amp`; cor livre | `L` |
| P2 | **Enforcado** (baixa) | 1 | `alta(t0)` | forma idêntica a P1 | `H` |
| P3 | **Estrela cadente** (baixa) | 1 | `alta(t0)` | `amp ≥ 0.8·atr_ref`; `corpo ≤ 0.35·amp`; `sup ≥ 2·corpo`; `inf ≤ 0.1·amp`; cor livre | `H` |
| P4 | **Martelo invertido** (alta) | 1 | `baixa(t0)` | forma idêntica a P3 | `L` |
| P5 | **Doji** (reversão do contexto) | 1 | `baixa(t0)` → mede alta; `alta(t0)` → mede baixa | `corpo ≤ 0.1·amp`; `amp ≥ 0.5·atr_ref` | `L` (se mede alta) / `H` (se mede baixa) |
| P6 | **Marubozu** de alta / de baixa (continuação) | 1 | nenhum | `corpo ≥ 1.0·atr_ref`; `sup ≤ 0.1·amp`; `inf ≤ 0.1·amp`; direção = cor | `O` da barra |
| P7 | **Engolfo** de alta | 2 | `baixa(t0)` | barra 1 de baixa; barra 2 de alta; `O2 ≤ C1` e `C2 ≥ O1` com pelo menos uma desigualdade estrita; `corpo2 > corpo1`; `corpo2 ≥ 0.5·atr_ref` | `min(L1, L2)` |
| P7' | **Engolfo** de baixa | 2 | `alta(t0)` | espelho: barra 1 de alta; barra 2 de baixa; `O2 ≥ C1` e `C2 ≤ O1` (uma estrita); `corpo2 > corpo1`; `corpo2 ≥ 0.5·atr_ref` | `max(H1, H2)` |
| P8 | **Harami** de alta | 2 | `baixa(t0)` | barra 1 de baixa com `corpo1 ≥ 1.0·atr_ref`; `max(O2, C2) < O1` e `min(O2, C2) > C1` (corpo 2 estritamente dentro do corpo 1); `corpo2 ≤ 0.5·corpo1`; cor da barra 2 livre. Sub-rótulo **harami-cruz** se `corpo2 ≤ 0.1·amp2` | `L1` |
| P8' | **Harami** de baixa | 2 | `alta(t0)` | espelho: barra 1 de alta com `corpo1 ≥ 1.0·atr_ref`; `max(O2, C2) < C1` e `min(O2, C2) > O1`; `corpo2 ≤ 0.5·corpo1` | `H1` |
| P9 | **Estrela da manhã** (alta) | 3 | `baixa(t0)` | barra 1 de baixa, `corpo1 ≥ 1.0·atr_ref`; barra 2 `corpo2 ≤ 0.3·corpo1` e `max(O2, C2) ≤ C1` (corpo da estrela não acima do fechamento da barra 1 — sem gap); barra 3 de alta, `corpo3 ≥ 0.5·atr_ref`, `C3 ≥ C1 + 0.5·corpo1` (fecha acima do meio do corpo 1 — o "midpoint" de Caginalp; TA-Lib usa 0,3) | `min(L1, L2, L3)` |
| P9' | **Estrela da noite** (baixa) | 3 | `alta(t0)` | espelho: barra 1 de alta, `corpo1 ≥ 1.0·atr_ref`; `corpo2 ≤ 0.3·corpo1` e `min(O2, C2) ≥ C1`; barra 3 de baixa, `corpo3 ≥ 0.5·atr_ref`, `C3 ≤ C1 − 0.5·corpo1` | `max(H1, H2, H3)` |
| P10 | **Três soldados brancos** (alta) | 3 | `baixa(t0)` | três barras de alta; `C3 > C2 > C1`; `O1 ≤ O2 ≤ C1` e `O2 ≤ O3 ≤ C2` (cada uma abre dentro do corpo anterior — Caginalp); `corpo_i ≥ 0.5·atr_ref` para i = 1..3; `sup_i ≤ 0.2·amp_i` (sombras superiores curtas — TA-Lib) | `L1` |
| P10' | **Três corvos negros** (baixa) | 3 | `alta(t0)` | espelho: três de baixa; `C3 < C2 < C1`; `C1 ≤ O2 ≤ O1` e `C2 ≤ O3 ≤ O2`; `corpo_i ≥ 0.5·atr_ref`; `inf_i ≤ 0.2·amp_i` | `H1` |
| P11 | **Três dentro para cima** (alta) — o mais forte de Caginalp | 3 | `baixa(t0)` | P8 nas barras 1–2 **e** barra 3 de alta com `C3 > O1` (fecha acima da abertura da barra 1) | `min(L1, L2, L3)` |
| P11' | **Três dentro para baixo** (baixa) | 3 | `alta(t0)` | P8' nas barras 1–2 **e** barra 3 de baixa com `C3 < O1` | `max(H1, H2, H3)` |

Onze famílias, 18 rótulos direcionais. **Todas as constantes (0,8; 0,35; 2; 0,1; 0,5; 1,0; 0,3; 0,2)
são suposições declaradas, nenhuma é medida** — vêm de Nison via Marshall ("sombra inferior com o
dobro do corpo"), de Caginalp (aberturas dentro do corpo anterior, fechamento acima do meio) e dos
padrões do TA-Lib (`ShadowVeryShort = 0,1 × amplitude média`, `Near = 0,2`, `BodyDoji = 0,1`,
penetração 0,3 da estrela), trocando as médias de 10 barras do TA-Lib pelo ATR14 do sistema. A T3.55b
**reporta a frequência de cada rótulo por timeframe antes de qualquer retorno**: um rótulo com menos
de ~30 ocorrências em blocos distintos não recebe IC, recebe "raro".

O que fica de fora, e por quê: *piercing / dark cloud cover* (dependem de abertura com gap contra o
fechamento anterior — inexistente aqui); *pinça* (igualdade de extremos é frágil em `Decimal` com
tick de 0,1 USDT); *kicking, abandoned baby, tasuki, janelas* (gap); *hikkake* (é um padrão de
*inside bar* + falso rompimento, mais próximo de [[KB-0077-linhas-de-tendencia]] do que de
candlestick — anotado no [[Strategy Backlog]] porque Moser & Brauneis o listam entre os que
sobrevivem).

## 8. Segunda opinião (Astra)

Pendente. Três perguntas para ela: (1) Holm ou SPA stepwise, dado que os 132 testes compartilham a
mesma série; (2) se o contexto EMA10 + inclinação é defensável ou se é uma quinta régua inventada;
(3) se a invalidação natural como stop faz sentido para a lente do pedágio ou se subestima a
distância real (o stop clássico fica um tick **além** do extremo).

## Relacionadas

[[11-KNOWLEDGE/Index|Index]] · [[Strategy Backlog]] · [[Registro de Tentativas]] ·
[[KB-0003-rompimento-de-canal-e-data-snooping]] · [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] ·
[[KB-0076-por-que-perdemos-2026-09-08]] · [[KB-0077-linhas-de-tendencia]] ·
[[KB-0078-o-radar-preve]] · KB-0081 (T3.55b, a escrever)

## Fontes — o que foi de fato aberto nesta sessão (2026-09-09, 00:00–00:30 Brasília)

| fonte | URL | o que abriu / o que foi lido |
|---|---|---|
| Marshall, Young & Rose — working paper "Market Timing with Candlestick Technical Analysis" (Massey) | https://c.mql5.com/forextsd/forum/211/Market%20Timing%20with%20Candlestick%20Technical%20Analysis.pdf | **PDF de 18 páginas lido inteiro** (texto, Tabelas 1 e 2). O próprio texto remete ao JBF 2006 para "resultados mais detalhados" |
| Marshall, Young & Rose (2006), JBF 30(8) 2303–2323 | https://www.sciencedirect.com/science/article/abs/pii/S0378426605002116 | **403** (WebFetch e curl devolvem só a casca JS). Entrada bibliográfica confirmada em https://econpapers.repec.org/RePEc:eee:jbfina:v:30:y:2006:i:8:p:2303-2323 (aberta, sem resumo) |
| Caginalp & Laurent (1998), AMF 5(3–4) 181–205 | https://tradingwithrayner.com/wp-content/uploads/2014/11/The-Predictive-Power-of-Price-Patterns.pdf | **PDF de 25 páginas lido inteiro** (definições, Tabelas 1–5, conclusões). Resumo confirmado em https://econpapers.repec.org/RePEc:taf:apmtfi:v:5:y:1998:i:3-4:p:181-205 (aberta); SSRN devolveu 403 |
| Park & Irwin (2004), "The Profitability of Technical Analysis: A Review", AgMAS 2004-04 | https://farmdoc.illinois.edu/assets/marketing/agmas/AgMAS04_04.pdf | **PDF de 65 páginas**: resumo, seção de padrões gráficos (menções a Caginalp), "Summary and Conclusion" lidos |
| Park & Irwin (2007), J. Economic Surveys 21(4) 786–826 | https://experts.illinois.edu/en/publications/what-do-we-know-about-the-profitability-of-technical-analysis/ | **página de resumo aberta** (95 estudos: 56/20/19). Wiley e SSRN devolveram 403/429 |
| Park & Irwin (2005), "…US Futures Markets: A Data Snooping Free Test" | https://farmdoc.illinois.edu/assets/marketing/agmas/AgMAS05_04.pdf | baixado (65 p.); só o cabeçalho lido — não é sobre candlestick, não usado |
| Ho, Chan, Pan & Li (2021), IEEE Big Data, DOI 10.1109/bigdata52589.2021.9671826 | https://api.semanticscholar.org/graph/v1/paper/DOI:10.1109/bigdata52589.2021.9671826?fields=title,abstract,authors,year,venue | **resumo aberto via API**; metadados confirmados no Crossref. ResearchGate 403, IEEE Xplore vazio. Texto **não lido** |
| Cohen (2021), RQFA 57, DOI 10.1007/s11156-021-00973-6 | https://link.springer.com/article/10.1007/s11156-021-00973-6 | **página aberta via curl**: `dc.description` (resumo completo) e metadados de citação. Texto não lido |
| Kuna (2025), "Candlesticks and graph patterns in cryptocurrencies", tese, Charles University | https://dspace.cuni.cz/bitstream/handle/20.500.11956/197060/130412926.pdf?sequence=1&isAllowed=y | **PDF lido**: §2.3, §3.1–3.6, cap. 4, §5.2–5.5, cap. 6 |
| Moser & Brauneis (2026), IREF 108, 105158, DOI 10.1016/j.iref.2026.105158 | https://www.sciencedirect.com/science/article/pii/S1059056026002716 | **NÃO ABERTO**: 403 na página e no PDF; ResearchGate 403; Semantic Scholar sem resumo; Crossref só metadados (https://api.crossref.org/works/10.1016/j.iref.2026.105158). Tudo o que está na §2.7 vem de trechos de resumo em resultados de busca |
| Shanaev, Vasenin & Stepanov (2023), Heliyon, "Turn-of-the-candle effect in bitcoin returns" | https://pmc.ncbi.nlm.nih.gov/articles/PMC10015199/ | **artigo aberto** (resumo, dados, métodos, custos, conclusão) |
| Jönsson (2016), tese, Lund | https://lup.lub.lu.se/luur/download?func=downloadFile&recordOId=8877738&fileOId=8877838 | **PDF baixado**; resumo (sueco e inglês) lido |
| Vahidpour et al. (2024), Romanian J. Inf. Tech. & Automatic Control 34(1) 109–122 | https://journals.indexcopernicus.com/api/file/viewByFileId/1938845 | **PDF baixado**; resumo e seção de dados lidos |
| Uzun et al. (2024), Computation 12(7) 132 | https://api.crossref.org/works/10.3390/computation12070132 | **resumo via Crossref**; página do MDPI devolveu 403 |
| Kapur et al. (2024), IJQRM 41(8) | https://www.emerald.com/ijqrm/article-abstract/41/8/2055/1217341/ | resumo aberto; é ML sobre BTC/ETH, repete os números de Cohen — não usado além de contexto |
| TA-Lib — `ta_global.c` (TA_CandleDefaultSettings) | https://raw.githubusercontent.com/TA-Lib/ta-lib/main/src/ta_common/ta_global.c | **lido**: BodyLong 1,0×corpo médio(10); BodyDoji 0,1×amplitude(10); ShadowVeryShort 0,1×amplitude(10); ShadowLong 1,0×corpo; ShadowVeryLong 2,0×corpo; Near 0,2 e Far 0,6 ×amplitude(5); Equal 0,05 |
| TA-Lib — `ta_CDLHAMMER.c`, `ta_CDLENGULFING.c`, `ta_CDLMORNINGSTAR.c`, `ta_CDLSHOOTINGSTAR.c`, `ta_CDLHARAMI.c`, `ta_CDL3WHITESOLDIERS.c`, `ta_CDLMARUBOZU.c` | https://raw.githubusercontent.com/TA-Lib/ta-lib/main/src/ta_func/ | **lidos** os blocos de regra e as condições `if` de cada um |
| Hudson & Urquhart (2021) | — | **não reaberto**; usado como já está em KB-0003 |

Arquivos baixados ficaram no scratchpad da sessão (`caginalp1998.pdf`, `mql5_markettiming.pdf`,
`parkirwin_review.pdf`, `cuni_thesis.pdf`, `lund_thesis.pdf`, `copernicus_crypto.pdf` e os `.txt`
extraídos com `pdftotext`); nada foi copiado para o repositório.
