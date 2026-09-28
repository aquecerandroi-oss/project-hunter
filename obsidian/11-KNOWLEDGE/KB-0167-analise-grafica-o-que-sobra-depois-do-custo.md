---
tags: [knowledge, leitura, analise-tecnica, grafico, rompimento, suporte-resistencia, volume, data-snooping, cripto, hipotese]
tema: "análise técnica e gráfica — entre os estudos consultados, a evidência mais favorável depois de custo está em regras de tendência diárias (cripto até 2017–2018, e a melhor regra do Bitcoin falhou fora da amostra); o intradiário publicado paga menos que o nosso pedágio; suporte/resistência é estatística de parada, não regra lucrativa demonstrada; a lição do data snooping; e três candidatas de gráfico para depois do EXP-M26"
fonte: "Brock, Lakonishok & LeBaron (J. Finance 47(5), 1992 — só o resumo); Sullivan, Timmermann & White (J. Finance 54(5), 1999 — versão de trabalho LSE FMG DP 303, out/1998, lida na íntegra); Lo, Mamaysky & Wang (J. Finance 55(4), 2000 — NBER w7613, mar/2000, lida na íntegra); Park & Irwin (J. Economic Surveys 21(4), 2007 — só o resumo; relatório AgMAS 2004-04 aberto em parte; AgMAS 2005-04, resumo); Hudson & Urquhart (Annals of Operations Research 297, 2021 — CC BY, texto e tabelas 6, 8 e 9 lidos); Corbet, Eraslan, Lucey & Sensoy (Finance Research Letters 31, 2019 — preprint SSRN de ago/2020 lido); Grobys, Ahmed & Sapkota (FRL 32, 2020 — lido); Gerritsen, Bouri, Ramezanifar & Roubaud (FRL 34, 2020 — versão do editor no repositório de Utrecht, lida); Shen, Urquhart & Wang (Financial Review 57(2), 2022 — versão aceita, lida); Osler (FRBNY Economic Policy Review 6(2), 2000 — lida); Osler (FRBNY Staff Report 125, 2001 — resumo e introdução); Chung & Bellotti (arXiv 2101.07410, 2021, preprint — resumo e método); Detzel et al. (Financial Management 50, 2021 — só o resumo); Urquhart (Economics Letters 159, 2017 — só o resumo); Zaremba et al. (Int. Review of Financial Analysis 78, 2021 — só o resumo); Schulmeister (Review of Financial Economics 18, 2009 — só o resumo)"
fonte_url: https://ideas.repec.org/a/bla/jfinan/v47y1992i5p1731-64.html · http://eprints.lse.ac.uk/119144/1/dp303.pdf · https://www.nber.org/papers/w7613 · https://ideas.repec.org/a/bla/jecsur/v21y2007i4p786-826.html · https://farmdoc.illinois.edu/assets/marketing/agmas/AgMAS05_04.pdf · https://link.springer.com/article/10.1007/s10479-019-03357-1 · https://doras.dcu.ie/25053/ · https://osuva.uwasa.fi/handle/10024/11192 · https://dspace.library.uu.nl/handle/1874/407735 · https://centaur.reading.ac.uk/100181/ · https://www.newyorkfed.org/medialibrary/media/research/epr/00v06n2/0007osle.pdf · https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr125.pdf · https://arxiv.org/abs/2101.07410 · https://doi.org/10.1111/fima.12310 · https://ideas.repec.org/a/eee/ecolet/v159y2017icp145-148.html · https://ideas.repec.org/a/eee/finana/v78y2021ics1057521921002349.html · https://doi.org/10.1016/j.rfe.2008.10.001
lido_em: 2026-09-28
evidencia: "mista — estudos revisados lidos na íntegra (Hudson & Urquhart; Grobys et al.; Gerritsen et al.; Osler 2000), versões de trabalho ou aceitas de estudos depois publicados (Sullivan et al.; Lo et al.; Shen et al.; Corbet et al. em preprint), resumos apenas (Brock et al.; Park & Irwin 2007; Detzel et al.; Urquhart 2017; Zaremba et al.; Schulmeister), um preprint não revisado (Chung & Bellotti); nenhuma medição nossa"
hipotese_testavel: sim
astra: "concorda com o ranking provisório C1 → C2 → C3 e com não registrar nada; 5 must-fix aceitos (generalizações e ranking suavizados, categorias de custo separadas, contraponto de Corbet com e sem banda, contexto do Lab e grade de 5 min da volume_anomaly corrigidos, C3 rebaixada a extrapolação explícita); recomendação de rever a prontidão da sweep_reclaim_v1 antes de desenvolver C3 registrada como recomendação, fora do escopo desta leitura"
status: vivo
owner: sexta-feira
updated: 2026-09-28
confiança: "?"
tipo: leitura
hipotese: —
variavel: —
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: "nenhuma hipótese registrada; três candidatas em Proximas Hipoteses (seção de 28/09, análise gráfica) — C1 (tendência diária como estado dos sinais de continuação do Lab) só com registro antes de qualquer desfecho, coorte nova e teste incremental junto da pista _low; C2 (memes) só depois do veredito da H-022; C3 só exploratória, depois de rever a prontidão da sweep_reclaim_v1"
classe_de_perda: —
mercado: cripto
---

# KB-0167 — Análise gráfica: o que sobra depois do custo

> **Leitura curada, sem medição nossa, nenhum preço nem desfecho do nosso banco consultado.** Entre os estudos
> consultados, a evidência mais favorável à viabilidade **depois de custo** concentra-se em regras de
> **tendência** em horizonte **diário** (média móvel, rompimento de canal, filtro) — em cripto até 2017–2018,
> quase sempre medida como custo de equilíbrio e não como resultado líquido, e com a melhor regra do Bitcoin
> **perdendo fora da amostra**. A transferência disso para o nosso intradiário **não está demonstrada**: o único
> efeito intradiário em cripto com custo calculado que li (Shen et al.) tem custo de equilíbrio abaixo da taxa
> da corretora. Suporte/resistência é estatística de parada bem documentada, não regra lucrativa demonstrada; os
> dois testes de volume que li (tendência do volume em Lo et al., OBV em Gerritsen et al.) acrescentaram pouco —
> o que não esgota "confirmação por volume"; e não achei estudo revisado sobre distância à VWAP ou acordo entre
> tempos gráficos como sinal.

## O que afirma

1. **A regra técnica simples já foi forte, e o mérito está na tendência.** Brock, Lakonishok & LeBaron (1992)
   testaram médias móveis e rompimento de faixa (`trading range break`) no índice Dow Jones de 1897 a 1986 e, pelo
   resumo, os sinais de compra renderam mais e com menos volatilidade que os de venda, de um jeito que quatro
   modelos nulos (passeio aleatório, AR(1), GARCH-M, EGARCH) não reproduzem. **Só li o resumo**; o texto completo
   não abriu (JF fechado, sem cópia aberta achada).
2. **Escolher a melhor regra de um universo grande fabrica significância, e o tempo a desfaz.** Sullivan,
   Timmermann & White (1999) refizeram a busca com 7.846 regras e o Reality Check de White: na amostra de Brock et
   al. o melhor resultado sobrevive à correção, mas **depois de 1986 some**, e no futuro do S&P 500 (onde custo e
   venda a descoberto são baratos) nenhuma regra supera o caixa.
3. **Padrões gráficos carregam informação estatística, não prova de lucro.** Lo, Mamaysky & Wang (2000)
   automatizaram a detecção de dez figuras clássicas (ombro-cabeça-ombro, fundo duplo, retângulos…) e acharam
   distribuições condicionais de retorno diferentes das incondicionais. Os retornos foram padronizados por ação
   para poder agregar ações em escala comum (isso não apaga diferenças de média condicional); o que falta para
   falar de lucro é uma estratégia executável com custo, que o estudo não tem — e os autores dizem isso.
4. **A literatura inteira tem os mesmos três defeitos.** Park & Irwin (2007): 95 estudos modernos, 56 positivos,
   20 negativos, 19 mistos; a maioria sofre de data snooping, escolha **ex post** das regras e dificuldade em medir
   risco e custo. O mesmo grupo (2005), replicando com dados novos: o lucro técnico de 12 mercados futuros em
   1978–1984 não existe mais em 1985–2003.
5. **Em cripto, a mesma história, um ciclo depois.** Hudson & Urquhart (2021) testaram 14.919 regras em cinco
   classes (média móvel, filtro, suporte/resistência, oscilador, rompimento de canal) em BTC, LTC, XRP e ETH
   diários até 31/12/2017: retorno bruto significativo em todas as classes; custo de equilíbrio muitas vezes acima
   de 50 bps (tabela 6); entre 20,35 % e 33,61 % das regras significativas depois de Bonferroni (tabela 8). As duas
   tabelas são **separadas** — o artigo não mostra quantas regras passam no custo **e** na correção ao mesmo tempo.
   **A melhor regra de dentro da amostra de cada série de Bitcoin perdeu fora dela** (1.º semestre de 2018).
6. **No intradiário, o que li é pequeno ou instável.** Shen, Urquhart & Wang (2022): no Bitcoin a primeira meia hora
   (definida por volume) prevê a última, mas o custo de equilíbrio das três estratégias sem alavancagem é de 3, 7
   e 10 bps, contra taxa de 25 bps da Bitstamp. Corbet et al. (2019), com velas de 1 min do Bitcoin e sem custo:
   o rompimento de faixa de *n* minutos foi seguido, **na média das 20 especificações**, de retorno pior depois do
   rompimento de alta do que depois do de baixa — mas o sinal **depende da banda**: +0,0138 % sem banda, −0,2627 %
   com banda de 1 %. Schulmeister (2009, só o resumo) é o contraponto: no S&P 500 com dados de 30 min, 2.580 modelos
   renderam 7,2 % a.a. **brutos** em 1983–2007, sem tendência clara de queda, embora piores em 2001–2007.
7. **Suporte e resistência são reais como pontos de parada, não como regra lucrativa demonstrada.** Osler (2000):
   taxas de câmbio de 1 min pararam ("bounce") em 60,8 % das vezes nos níveis publicados por seis firmas (bancos e
   provedores de informação) contra 56,2 % em níveis arbitrários. Osler (2001) dá o mecanismo: ordens de
   realização de lucro juntam-se **em** números redondos (a tendência para) e ordens de stop logo **depois** deles
   (a tendência acelera quando o nível é cruzado). No Bitcoin, Urquhart (2017, só o resumo) acha o agrupamento em
   números redondos **sem** padrão de retorno depois deles.

## Onde foi mostrado — um estudo por vez

| estudo | mercado | período | horizonte | custo | o que eu abri |
|---|---|---|---|---|---|
| Brock, Lakonishok & LeBaron 1992 | índice Dow Jones | 1897–1986 | diário; 26 regras (MM e rompimento de faixa) | não aparece no resumo | **só o resumo** (RePEc) + a descrição em Sullivan et al. |
| Sullivan, Timmermann & White 1999 | Dow Jones; futuro do S&P 500 | 1897–1996; futuro 1984–1996 | diário; 7.846 regras | custo de equilíbrio da melhor regra (0,27 % por operação) | versão de trabalho de out/1998, inteira (o PDF tem trechos corrompidos; os números vêm do texto legível) |
| Lo, Mamaysky & Wang 2000 | ações NYSE/AMEX e Nasdaq, 50 sorteadas por quinquênio | 1962–1996 | janela de 38 dias; retorno de 1 dia, 3 dias depois do padrão | nenhum; sem estratégia | NBER w7613, inteira |
| Park & Irwin 2007 | revisão (95 estudos modernos) | 1988–2004 | vários | o problema central apontado | **só o resumo** (RePEc); o relatório AgMAS 2004-04 abriu com 7 páginas (resumo e introdução: 92 estudos, 58/24/10) |
| Park & Irwin 2005 | 12 futuros americanos | 1978–1984 × 1985–2003 | diário | incluído | resumo do AgMAS 2005-04 |
| Hudson & Urquhart 2021 | BTC (CoinDesk desde 18/07/2010; Bitstamp desde 01/12/2012), LTC, XRP, ETH | até 31/12/2017; fora da amostra 1.º sem. 2018 | diário; comprado/vendido/fora | custo de equilíbrio por classe; referência de 50 bps | texto integral + tabelas 6, 8 e 9 (CC BY) |
| Corbet et al. 2019 | BTC/USD na Bitfinex | 01/01/2014–25/06/2018 (2.341.440 min) | 1 min; holding de *n* min | nenhum (os autores pedem para trabalho futuro) | preprint SSRN (ago/2020), inteiro |
| Grobys, Ahmed & Sapkota 2020 | 11 maiores criptos de 03/01/2016 | 2016–2018 | diário; só compra; MM (1,20) a (1,200) | nenhum | artigo inteiro |
| Gerritsen et al. 2020 | BTC | preços desde jul/2010, estratégias avaliadas de fev/2011 a jan/2019 | diário; sete indicadores | nenhum (os autores pedem para trabalho futuro) | versão do editor, inteira |
| Detzel et al. 2021 | BTC; ações "difíceis de avaliar" | — (não li) | diário | o resumo fala de alfa e Sharpe, **não** de custo | **só o resumo** |
| Shen, Urquhart & Wang 2022 | BTC em 5 corretoras (Bitstamp 01/01/2013–31/12/2020) | até 31/12/2020 | meia hora | custo de equilíbrio | versão aceita, inteira |
| Osler 2000 | DEM, JPY, GBP contra USD; níveis de 6 firmas | jan/1996–mar/1998 | 1 min, 9h–16h NY | nenhum; não é estratégia | artigo inteiro |
| Osler 2001 | livro de ordens de um banco de câmbio | — | — | — | resumo e introdução (Staff Report 125) |
| Chung & Bellotti 2021 | EURUSD, ação LLOY, petróleo Brent, em minuto | 2018 | intradiário | nenhum | preprint arXiv, **não revisado** |
| Urquhart 2017 | BTC | — | — | — | **só o resumo** |
| Zaremba et al. 2021 | mais de 3.600 criptos | — | diário, transversal | — | **só o resumo** |
| Schulmeister 2009 | índice e futuro do S&P 500, 2.580 modelos | 1960–2007 | diário × 30 min | retorno **bruto** | **só o resumo** |

**Números que conferi na fonte e que carregam a nota** (a Astra refez a conferência linha a linha nos textos
extraídos, `.claude/state/kb167-fontes/`, e não achou erro de transcrição):

- **Sullivan et al.:** melhor regra em 100 anos de Dow Jones = média móvel de 5 dias, 17,2 % a.a. (comprar e segurar:
  4,3 %), Reality Check p < 0,002; 6.310 operações, custo de equilíbrio 0,27 % por operação. Com o sinal executado
  **um dia depois**, a melhor regra por retorno médio ainda é significativa (7,8 % a.a., p < 0,002), mas a melhor por
  Sharpe cai para p = 0,26. Fora da amostra (1987–1996), a MM de 5 dias rendeu 2,8 % com p nominal 0,322. No futuro
  do S&P 500 (1984–1996), a melhor regra tinha p nominal 0,04 e p **ajustado** 0,90; por Sharpe, < 0,002 contra 0,99.
- **Lo et al.:** na NYSE/AMEX, 5 dos 10 padrões diferem com p entre 0,000 e 0,021, os outros 5 entre 0,104 e 0,393;
  na Nasdaq, os 10 a 5 %. Condicionar à tendência do volume acrescenta pouca informação, segundo os autores (a
  exceção é um par de padrões de topo/fundo) — com a ressalva deles de que as amostras condicionais são pequenas.
- **Hudson & Urquhart, Tabela 6** (custo de equilíbrio médio, bps; % de regras acima de 50 bps): CoinDesk — MM
  54,86 (32,04 %), filtro 66,41 (32,38 %), suporte/resistência 11,42 (0,00 %), oscilador 44,60 (36,06 %), canal
  61,00 (30,18 %); Bitstamp — suporte/resistência 11,89 (0,95 %), canal 54,12 (27,38 %); LTC suporte/resistência
  7,88; XRP 16,16 (3,49 %); ETH 9,89 (0,11 %); ETH oscilador 50,05 (36,74 %). **Tabela 8** (Bonferroni / BH):
  CoinDesk 33,61 % / 50,41 %; Bitstamp 27,11 % / 46,28 %; LTC 23,26 % / 31,84 %; XRP 20,35 % / 27,96 %; ETH 23,37 % /
  32,68 %. **Tabela 9** (melhor regra de dentro da amostra, no 1.º semestre de 2018): as duas séries de Bitcoin,
  ambas com rompimento de canal, retorno anualizado −0,0010 e −0,0091 e Sharpe negativo; LTC, XRP e ETH positivos.
- **Gerritsen et al.:** rompimento de faixa de 50/150/200 dias com Sharpe diário médio ≈ 0,08 e acima de comprar e
  segurar; médias móveis quase nunca diferentes; RSI e Bollinger (contra a tendência) **piores** que comprar e
  segurar; OBV (volume) atrás, sem significância.
- **Grobys et al.:** MM (1,20) diária, só compra, 45,63 % a.a. contra 36,87 % de comprar e segurar nas 10 moedas sem
  o BTC (+8,76 p.p.); significância conjunta só em (1,20), (1,50) e (1,100).
- **Shen et al.:** R² da previsão 1,44 % (3,86 % em dias de volume alto, 1,09 % em dias de volume baixo); custo de
  equilíbrio sem alavancagem 3, 7 e 10 bps por operação, contra taxa de 25 bps na Bitstamp. **Crítica minha à
  comparação econômica dos autores:** eles argumentam que a alavancagem torna a estratégia lucrativa; com custo
  proporcional ao nocional, ganho e custo crescem juntos e a alavancagem não muda o sinal do resultado líquido — o
  número que importa é o de 3–10 bps.
- **Corbet et al.:** rompimento de faixa em minutos (20 testes): diferença média compra − venda de −0,1245 %,
  11 das 16 diferenças negativas significativas; +0,0138 % sem banda e −0,2627 % com banda de 1 %. Para a média
  móvel o preprint relata retorno médio de 0,072 % nas compras; lido como retorno **por minuto**, é difícil de
  interpretar economicamente, e o texto não deixa claros unidade, seleção das observações e alinhamento entre
  sinal e retorno. Não uso esses números para tamanho nem para direção.

**Nada de 15 minutos em perpétuo, nada de moeda de 15–120 minutos numa bonding curve.** O que há de mais perto do
nosso horizonte (minutos e meia hora em BTC) é o que tem o custo de equilíbrio mais baixo ou o sinal mais instável.

## A lição do data snooping (o que muda no nosso protocolo)

1. **A regra famosa é sobrevivente.** Sullivan et al. lembram que o snooping é coletivo: as regras que chegaram
   aos livros são as que funcionaram no passado; testar "a regra clássica" já carrega uma multiplicidade que
   ninguém declarou. Para nós: toda regra da literatura conta como tentativa no [[Registro de Tentativas]] **mais**
   as variantes nossas — e a escolha entre elas não pode ser feita olhando desfecho
   ([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]).
2. **A correção de multiplicidade é necessária e não basta.** Hudson & Urquhart passam em Bonferroni e mesmo assim
   a melhor regra do Bitcoin perde fora da amostra; o Dow Jones passa no Reality Check até 1986 e morre depois.
   Significância corrigida sobre a mesma janela não é validação — só a coorte **prospectiva** decide
   ([[KB-0049-walk-forward-que-nao-temos-e-o-nulo-que-nunca-calculamos]]).
3. **Um dia de atraso bastou para derrubar o melhor Sharpe** (p de < 0,002 para 0,26 em Sullivan et al.; a melhor
   por retorno médio sobreviveu, com menos da metade do retorno). O análogo nosso é o atraso de decisão
   ([[KB-0087-o-atraso-de-decisao-e-as-tres-correcoes]]): qualquer sinal gráfico tem de ser medido com a execução
   que a mesa de fato tem, não no fechamento que o gerou.
4. **Custo de equilíbrio antes de significância, e na mesma base.** O Lab carrega cerca de **20 bps de ida e volta**
   ([[KB-0076-por-que-perdemos-2026-09-08]]). Os 3–10 bps de Shen et al. são custo de equilíbrio **por operação** de
   estratégias intradiárias; os 7,88–16,16 bps de suporte/resistência de Hudson & Urquhart são de regras **diárias**.
   Qualquer comparação com o nosso pedágio tem de pôr os dois números na mesma base (por lado ou ida e volta, por
   operação) — é a mesma conta de [[KB-0150-a-proxima-vela-e-menor-que-o-pedagio]] e
   [[KB-0086-ic-positivo-nao-paga-o-pedagio-btc-perp-5-min]].
5. **O efeito costuma decair com o tempo e com a publicação, mas não sempre.** Futuros (1978–84 → 1985–2003), Dow
   Jones (→ 1987–96), Bitcoin (→ 2018) decaíram; o resumo de Schulmeister não acha tendência clara de queda no
   S&P 500 em 30 min (bruto), só um trecho final pior. Uma hipótese nossa deve esperar **menos** que o número
   publicado, nunca o número publicado.

## O estado da evidência por sinal de gráfico

"Resultado líquido", "custo de equilíbrio", "resultado bruto", "estatística sem estratégia" e "não achei estudo"
são **estados diferentes**, não degraus de uma escala. A tabela diz em que estado cada sinal está, nos estudos que
li, e só a primeira linha fica **na frente** por ter o melhor estado; as demais não estão ordenadas entre si.

| sinal | estado da evidência (nos estudos lidos) | onde falha |
|---|---|---|
| **Tendência em horizonte diário** (razão preço/média móvel, rompimento de canal de 20–200 dias, filtro) — **na frente** | custo de equilíbrio alto: 18–50 % das regras de MM/filtro/canal acima de 50 bps em cripto (17,97 % no canal do LTC a 49,52 % no filtro do ETH, Hudson & Urquhart); bruto favorável em Grobys e Gerritsen; previsão fora da amostra na razão preço/MM do BTC (Detzel et al., pelo resumo, sem custo visto) | até 2017–2018; a melhor regra do BTC perdeu em 2018; frágil depois de 2020 ([[KB-0164-momentum-semanal-em-cripto-grande]]); quase o mesmo objeto que momentum de série temporal (correlação > 0,80 citada por Hudson & Urquhart) |
| **Osciladores** (RSI, Bollinger, famílias de oscilador) | **misto**: custo de equilíbrio de 44,60 bps (36,06 % > 50 bps) no CoinDesk e 50,05 bps no ETH (Hudson & Urquhart), mas RSI e Bollinger piores que comprar e segurar no BTC diário (Gerritsen et al.) | definições diferentes entre os estudos; nada intradiário |
| **Momento intradiário** (primeira janela prevê a última) | custo de equilíbrio **abaixo** da taxa: 3–10 bps por operação contra 25 bps (Shen et al.) | a defesa pela alavancagem não muda o custo por nocional |
| **Rompimento de faixa de minutos** | bruto, sem custo, e **instável**: média negativa, sinal que muda com a banda (Corbet et al.) | preprint; números da MM de interpretação difícil |
| **Suporte/resistência** | estatística de parada sem estratégia (Osler; Chung & Bellotti, preprint); como a família "suporte/resistência" de Hudson & Urquhart (regra de rompimento de máximo/mínimo local), custo de equilíbrio baixo — 7,88–16,16 bps, 0–3,5 % das regras acima de 50 bps | essa família não representa toda forma de suporte/resistência (o artigo separa "rompimento de canal"); o agrupamento em números redondos no BTC veio sem padrão de retorno (Urquhart 2017) |
| **Figuras clássicas** (ombro-cabeça-ombro, fundo duplo) e **candles** | estatística sem estratégia (Lo et al.); candles já em [[KB-0080-candlestick-evidencia]] / [[KB-0081-candlestick-no-nosso-dado]] | ações de 1962–96; sem custo |
| **Confirmação por volume** | os dois testes que li acrescentaram pouco: tendência do volume em Lo et al., OBV em Gerritsen et al. — isso **não** esgota a ideia | no nosso banco: H-006 não confirma, H-007 refuta, `volume_anomaly` perde ([[KB-0014-taker-buy-volume-o-que-temos-medido]], [[KB-0015-volume-relativo-e-o-pico-como-exaustao]]) |
| **Acordo entre tempos gráficos** | **não achei estudo revisado aberto** que o teste como sinal; o mais perto é a tendência diária usada como estado (C1) | a `mean_reversion_v1` já usa tendência de 1 h como portão |
| **Distância à VWAP** | **não achei estudo revisado** que a use como preditor; nos textos que encontrei a VWAP é referência de execução | ausência de evidência achada, não evidência de ausência |

## Como mediríamos aqui

- **Onde o dado vive.** Cripto: `candles` de 1 min `is_final` — a coleta padrão é de 1 min e o `backfill` recusa
  outro timeframe (`services/market-worker/hunter_market_worker/backfill.py:199`); a retenção padrão do 1 min é de
  90 dias (`packages/core/hunter_core/settings.py:123`, aplicada por `infra/scripts/partition_retention.py`), o
  que **não** prova cobertura completa desses dias. Features do Radar em
  `packages/indicators/hunter_indicators/features/` ([[Dicionario de Variaveis]] §A); sinais em `agent_signals` ×
  `signal_outcomes` (a população da [[KB-0163-perto-da-maxima-de-24h-nao-separa-os-sinais-do-lab]]). Memes:
  `meme_features_1m` (bloco `line`: `higher_lows`, `breakout_15m`, `distance_to_support_pct`) e, quando o EXP-M26
  existir, o registro `meme_mature_opportunities` (R1 de `docs/design/exp-m26-grafico-moedas-maduras.md`).
- **Contexto do Lab.** O contexto é dimensionado **por versão**: `SHADOW_CONTEXT_MINUTES` (1.560) é o **piso** e
  `SHADOW_CONTEXT_MAX_MINUTES` (6.000) o teto (`services/strategy-worker/hunter_strategy_worker/context_budget.py:310`,
  `config.py:299`). Uma tendência de 20 dias pede 28.800 min de velas de 1 min — acima do teto — ou uma janela
  diária nova. Medir retrospectivamente das velas do banco é possível (como o R83 fez com 1.440 velas); pôr no
  envelope é código novo (`FeatureDefinition` nova, v1) com revisão do orçamento de contexto.
- **Grades diferentes.** `momentum_v1` decide em **15 min** (`momentum_v1.py:74`); `volume_anomaly_v1` decide em
  **5 min** (`volume_anomaly_v1.py:66`). Qualquer população de "sinais de continuação" é analisada **por
  estratégia**.
- **O que já existe e cobre parte disto.** `momentum_v1` já é rompimento de canal de 20 fechamentos de 15 min
  ([[KB-0003-rompimento-de-canal-e-data-snooping]]); `breakout_strength_20` mede o tamanho do rompimento em ATR;
  `mean_reversion_v1` já tem portão de tendência (média de 20 fechamentos **horários**); `sweep_reclaim_v1`
  (implementada, sem coorte — [[EXP-0017-sweep-reclaim]]) é motivada pelo mecanismo de stops de Osler do lado do
  suporte, mas mede a **forma da barra**, não caça a stops (a própria EXP diz isso); `trendline_breakout_v1` e as
  linhas de [[KB-0077-linhas-de-tendencia]] cobrem a geometria.

## Hipóteses candidatas (não registradas) — por ordem

Nenhuma destas é bloco da [[Fila de Hipoteses]]; estão em [[Proximas Hipoteses]] (seção de 28/09, análise
gráfica). A ordem é: estado da evidência × custo de medir × distância das variáveis esgotadas. **Nenhuma é, por
definição, uma variável esgotada disfarçada — o risco é empírico** (C1 reproduzir a pista `_low`, C2 reproduzir
progresso ou "já está subindo", C3 renomear a geometria do rompimento), e o registro tem de mostrar a diferença,
não só trocar o nome ou o comprimento da janela (regras 1 e 2 da Fila). Estudar sinais de versões aposentadas
**não** autoriza reativá-las para obter coorte nova.

### C1 — Tendência diária como estado dos sinais de continuação do Lab (cripto)

- **Variável:** `razao_mm20d = C_d / média(C_{d−19}, …, C_d) − 1`, com `C_d` o fechamento da **última vela diária
  UTC completa antes da decisão** (dia de calendário, 00:00–24:00 UTC), dobrada de velas de 1 min `is_final` com
  os **1.440 minutos presentes** em cada um dos 20 dias — dia com minuto faltando torna a medida **indisponível**,
  nunca interpolada (a agregação existente já recusa minuto faltante, `hunter_core/strategies/aggregate.py:128`);
  nunca a vela do dia corrente. Secundária: só o sinal (`> 0`).
- **Onde vive:** não existe como feature; reconstrói-se de `candles` 1 min — mesma técnica do R83. Covariáveis
  que entram juntas: `distance_from_24h_low` (a pista do R83), ATR% e `return_4h`.
- **Mercado / tempo:** perpétuos da Binance no Lab, sinais de continuação, **por estratégia** (`momentum` em
  15 min, `volume_anomaly` em 5 min); a `spot/1` só descritiva.
- **Previsão (direção):** sinais com `razao_mm20d > 0` têm expectancy líquida em R maior que com `≤ 0`, **e** o
  grupo favorável é lucrativo em nível.
- **Classe de perda:** — (cripto).
- **Colisões verificadas:** não é a H-008 (4 h, estudo inválido por censura, continua aberta), nem a H-023 (24 h;
  a pista `_low` não morreu), nem a H-024 (outra política: carteira semanal à vista). Mudar a janela não prova
  informação nova: só vale com **teste incremental conjunto** contra `_low`, ATR% e `return_4h`, em **coorte
  futura**.
- **Honestidade sobre o tamanho:** a deriva diária publicada, espalhada por um holding de horas, é minúscula perto
  de 20 bps. Se houver efeito, será por **menos rompimentos falhados** em tendência, não pela deriva — e a
  literatura não mostra isso diretamente. É a primeira porque é a única com evidência no melhor estado, não porque
  se espere muito dela.

### C2 — Fundos mais altos sem rompimento de 15 min, depois da H-022 (memes)

- **Variável:** dentro da 1.ª oportunidade do controle `grafico_ctrl_v1/1`, separar `higher_lows ∧ ¬breakout_15m`
  de `higher_lows ∧ breakout_15m`, com linha **coberta** e a mesma banda de distância.
- **Onde vive:** `meme_features_1m` (colunas da linha, `hunter_indicators/meme/lines.py` v1) e o registro R1
  `meme_mature_opportunities` do [[EXP-M26-grafico-em-moedas-maduras]] (em construção).
- **Mercado / tempo:** memes de 15–120 min ainda na curva, via de 1 min.
- **Previsão (direção):** comprar o rompimento da máxima de 15 min é comprar o topo local; a estrutura de fundos
  sem o rompimento deve render mais. O apoio externo é **fraco e indireto**: a vantagem da tendência sobre o
  rompimento curto nos estudos diários, as realizações de lucro em níveis (Osler) e um rompimento de minutos no BTC
  cujo sinal depende da banda (Corbet et al.) — nenhum mede `breakout_15m`.
- **Classe de perda:** `comprou_no_topo` ([[comprou_no_topo]]).
- **Por que não é variável esgotada:** o bloco `line` nunca foi isolado; a H-021 parou por limite de dado, não por
  refutação; a H-022 testa só a **conjunção** dos três critérios.
- **Guardas herdadas da H-022:** cobertura da linha (a guarda de I1), controle de `curve_progress_pct` declarado
  antes e a cláusula de identidade contra `mcap_slope_15m` do desenho (`docs/design/exp-m26-grafico-moedas-maduras.md`
  §3).
- **Portão:** só depois do veredito da H-022, numa coorte que não seja a da inferência dela. Se a H-022 fechar
  **por instrumento**, C2 fica bloqueada junto; se fechar **economicamente**, retirar um critério da conjunção
  precisa de justificativa própria registrada antes — nunca a escolha do pedaço que ganhou. Se o orquestrador
  quiser o contraste antes do seed do EXP-M26, só como **descritivo** pré-registrado, nunca como hipótese.

### C3 — Geometria do nível antes do rompimento (cripto, exploratória)

- **Variável:** duas medidas separadas, entre as 20 barras de 15 min anteriores ao rompimento da `momentum_v1`:
  `rejeicoes_nivel` = número de **visitas distintas** ao nível (máxima a ≤ 0,25·ATR do máximo dos 20 fechamentos,
  sem fechar acima, separadas por pelo menos uma barra que se afastou mais que isso) e `barras_perto_nivel` =
  número total de barras nessa faixa (a aproximação prolongada). O 0,25 é convenção, não medida; teria de ser
  registrado como tal.
- **Onde vive:** reconstrói-se de `candles` 1 min; o nível e o ATR já estão no envelope da `momentum_v1`.
- **Previsão:** **bicaudal, e é extrapolação minha, não previsão dos artigos.** Osler documenta agrupamento de
  ordens e aceleração ao cruzar certos níveis, não que mais visitas produzam mais continuação; Chung & Bellotti
  estimam a chance de um novo "bounce" ao chegar ao nível, não o retorno depois de selecionar só os casos que já
  romperam.
- **Classe de perda:** — (cripto).
- **Por que não é variável esgotada:** `breakout_strength_20` mede **quanto** o preço passou do nível, não a
  história do nível; nunca medido.
- **Por que é a última:** nenhuma evidência líquida, previsão extrapolada. **Antes de desenvolvê-la**, rever a
  prontidão da `sweep_reclaim_v1` ([[EXP-0017-sweep-reclaim]]), que já existe e é a aposta do Lab no mesmo
  mecanismo — com os aceites pendentes daquela EXP verificados antes de qualquer proposta de ativação.

### Não recomendados agora (e por quê)

- **Confirmação por volume do rompimento** — os testes externos que li acrescentam pouco e há três resultados
  nossos contra (H-006, H-007, `volume_anomaly`); outra variante de volume sem medida nova seria girar o mesmo botão
  (regra 2 da [[Fila de Hipoteses]]).
- **Distância à VWAP** — nenhum estudo revisado achado; seria hipótese sem literatura e sem prior.
- **Cruzamento de número redondo** — o único estudo em BTC que li (pelo resumo) acha agrupamento **sem** padrão de
  retorno depois.
- **Rompimento de canal diário como estratégia própria na `spot/1`** — é quase o mesmo objeto da H-024 (momentum
  de série temporal); esperar o veredito dela. Se a H-024 falhar, um canal diário **não** é um teste independente.
- **Momento intradiário de primeira/última janela** — o custo de equilíbrio publicado (3–10 bps por operação) não
  passa pelo nosso pedágio.

## Por que pode falhar

- **Transferência de horizonte e mercado.** Quase toda a evidência é diária, em índice ou em BTC/ETH até 2018; o
  Lab decide em 5 e 15 min com dezenas de perpétuos e a mesa de memes vive em minutos numa curva.
- **Decaimento.** A maior parte dos efeitos que olhei encolhe depois da amostra de quem os publicou.
- **Redundância.** C1 anda com a pista `_low` do R83 e com a H-024; C2 é parte da `linha_ok` da H-022. Sem teste
  incremental conjunto, um "efeito" novo pode ser o velho com outro nome.
- **Leitura parcial.** Brock et al., Park & Irwin (2007), Detzel et al., Urquhart (2017), Zaremba et al. e
  Schulmeister: só resumo. Corbet et al. e Chung & Bellotti: preprints. Nenhum número desta nota vem de fonte que
  eu não abri, mas os resumos não mostram custo nem período completo.
- **Não abri:** Anghel (FRL 2021, "reality check" em cripto — fechado, sem resumo disponível); Zarattini, Pagani &
  Barbon (SSRN 2025, canal de Donchian em cripto — o SSRN bloqueou o acesso automático); Kavajecz & Odders-White
  (RFS 2004); Han, Zhou & Zhu (JFE 2016, fator de tendência multi-horizonte); Wen et al. (NAJEF 2022); Blume,
  Easley & O'Hara (1994, papel do volume). Nada deles entrou na síntese.

## Segunda opinião (Astra)

`.claude/state/astra-review-KB-analise-grafica.md` (síntese em [[06-DECISIONS/Revisoes-Astra/KB-analise-grafica|KB-analise-grafica]]).
Conferiu os números contra os textos extraídos e não achou erro de transcrição. **Cinco must-fix, todos aceitos:**

1. **Generalização demais.** "Evidência séria em um lugar", "o intradiário não paga" e "volume quase não
   acrescenta" passavam do que os estudos testaram; osciladores resistem a custo em Hudson & Urquhart e o resumo de
   Schulmeister não mostra queda clara no intradiário. Cenário de falha dela: a base transformar ausência de
   validação local em refutação de famílias inteiras. Corrigido no resumo, no item 6 e na tabela de estado.
2. **"Líquido de custo" misturava estados.** Os 3–16 bps juntavam custo de equilíbrio intradiário (Shen) com regra
   diária (Hudson); Detzel estava como evidência líquida sem custo no resumo; as tabelas 6 e 8 não mostram a
   interseção custo × correção. Corrigido: tabela por estado, e a lição 4 exige mesma base.
3. **Corbet com e sem banda.** A média negativa do rompimento de minutos esconde +0,0138 % sem banda e −0,2627 % com
   banda; o apoio a C2 ficou rebaixado a fraco e indireto, e a MM do preprint deixou de ser usada até para direção.
4. **Dado e contexto.** 1.560 min é o piso, não a janela; o teto é 6.000; a retenção de 90 d não prova cobertura; e
   a `volume_anomaly` decide em 5 min, não em 15. Corrigido em "Como mediríamos" e em C1.
5. **C3 atribuía aos artigos uma previsão que eles não estimaram.** Agora está como extrapolação minha, com as
   duas medidas separadas (visitas distintas × aproximação prolongada).

Também aceitos: a padronização em Lo et al. não apaga média condicional; o atraso de um dia derrubou o Sharpe mas
não o retorno médio em Sullivan et al.; Gerritsen avalia desde fev/2011; causalidade diária com cobertura integral;
guardas da H-022 herdadas por C2. **Recomendação dela registrada, não executada aqui:** rever a prontidão da
`sweep_reclaim_v1` antes de desenvolver C3 (está em C3 e em [[Proximas Hipoteses]]); atualizar o
[[Dicionario de Variaveis]] com a medida diária e a [[EXP-0017-sweep-reclaim]] com pendências fica para o
orquestrador — não criei variável nem mexi em experimento numa leitura. **Divergência:** nenhuma de conteúdo.

## Relacionados

[[Proximas Hipoteses]] · [[Mapa de Estrategias]] · [[Dicionario de Variaveis]] · [[Fila de Hipoteses]] ·
[[Registro de Tentativas]] · [[KB-0003-rompimento-de-canal-e-data-snooping]] ·
[[KB-0004-proximidade-da-maxima-e-confirmacao-por-volume]] · [[KB-0014-taker-buy-volume-o-que-temos-medido]] ·
[[KB-0015-volume-relativo-e-o-pico-como-exaustao]] · [[KB-0077-linhas-de-tendencia]] ·
[[KB-0080-candlestick-evidencia]] · [[KB-0161-o-grafico-de-5-minutos-nao-existe-na-porta]] ·
[[KB-0163-perto-da-maxima-de-24h-nao-separa-os-sinais-do-lab]] · [[KB-0164-momentum-semanal-em-cripto-grande]] ·
[[EXP-M26-grafico-em-moedas-maduras]] · [[EXP-0017-sweep-reclaim]]
