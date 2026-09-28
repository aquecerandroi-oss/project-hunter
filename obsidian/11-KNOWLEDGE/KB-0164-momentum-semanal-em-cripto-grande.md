---
tags: [knowledge, cripto, momentum, serie-temporal, transversal, leitura, segunda-frente, hipotese]
tema: momentum semanal em cripto grande — o que a literatura aberta sustenta (forte até 2018, bruto de custos, concentrado em BTC e nas maiores), o que a torna frágil depois de 2020, e como a H-024 mediria isso nos pares à vista da Binance sem sobrevivência nem look-ahead
fonte: Liu & Tsyvinski, "Risks and Returns of Cryptocurrency" (NBER w24877, ago/2018; publicado na RFS 34(6), 2021 — da versão publicada só o resumo foi lido); Liu, Tsyvinski & Wu, "Common Risk Factors in Cryptocurrency" (NBER w25882, mai/2019; depois Journal of Finance); Grobys & Sapkota, "Cryptocurrencies and momentum" (Economics Letters 180, 2019); Grobys, Kolari, Sandretto, Shahzad & Äijö, "Cryptocurrency momentum has (not) its moments" (Financial Markets and Portfolio Management 39, 2025); Arefev, "Cross-Sectional Momentum in Cryptocurrency: A Net-of-Costs Replication on Tradable Binance Perpetuals (2020-2026)" (SSRN 7404139, 2026 — só o resumo)
fonte_url: https://www.nber.org/papers/w24877 · https://doi.org/10.1093/rfs/hhaa113 · https://www.nber.org/papers/w25882 · https://osuva.uwasa.fi/bitstreams/ffee5cb1-92a8-443e-a117-cbaacd8a1028/download · https://link.springer.com/article/10.1007/s11408-025-00474-9 · https://doi.org/10.2139/ssrn.7404139
lido_em: 2026-09-28
evidencia: mista — dois estudos revisados lidos na íntegra (Grobys & Sapkota 2019; Grobys et al. 2025), duas versões de working paper NBER lidas na íntegra de estudos depois publicados em revista (as versões publicadas não abriram — RFS/OUP devolve 403; da RFS só o resumo via Crossref), uma nota SSRN não revisada da qual só o resumo foi lido (texto integral 403), um preprint arXiv não revisado (Begušić & Kostanjčar 2019); nenhuma medição nossa
hipotese_testavel: sim
astra: concorda com a primária (D_ts de 14 d contra a cesta sempre comprada) e com o universo ponto-no-tempo; 7 must-fix aceitos antes de qualquer retorno (fórmula, deslistagem executável, contrato de dados, custo, inferência, refutação pelo MRE, síntese da evidência); 1 divergência parcial registrada (o corte de período fica dentro do CONFIRMA)
status: vivo
owner: sexta-feira
updated: 2026-09-28
confiança: "?"
tipo: leitura
hipotese: H-024
variavel: sinal_ts_14d (sinal de C_d/C_(d-14) - 1 com d = ultima vela diaria final ate T - 1 d; compra 1/N se > 0, caixa se <= 0; rebalanceamento semanal); secundaria tercil superior do mesmo retorno
populacao: semanas de rebalanceamento (segunda 00:00 UTC) com universo ponto-no-tempo dos 20 pares USDT a vista mais negociados na Binance nos 30 d anteriores, incluindo deslistados; mapa spot/1 so descritivo
efeito: —
ic: —
veredito: —
proximo_passo: feito — H-024 testada no R84 (28/09/2026), NAO CONFIRMA; resultado em KB-0166-evitar-as-moedas-em-queda-nao-bate-a-cesta (esta nota continua sendo a leitura da literatura, sem veredito proprio)
classe_de_perda: —
mercado: cripto
---

# KB-0164 — Momentum semanal em cripto grande: o que a literatura sustenta

> **Leitura curada, sem medição nossa.** A tese "o retorno das últimas semanas de uma cripto grande prevê o da
> semana seguinte" tem apoio forte **até 2018**, medido **bruto de custos**, concentrado em BTC (série temporal) e
> nas moedas maiores (transversal). Os dois trabalhos que olham depois de 2020 com universo líquido acham o efeito
> **frágil**: instável, dominado por eventos de cauda, ou do tamanho do custo — mas ambos são **comprado/vendido**, e
> parte do pior resultado veio do lado vendido, que uma regra só-compra não tem. Entre as fontes consultadas **não
> encontramos** estudo que teste só compra, à vista, líquido de custo, depois de 2020 — é o buraco que a H-024
> (rascunho abaixo) mede. Nenhum preço nosso foi olhado para escrever esta nota.

## O que afirma

**Série temporal (o próprio passado de uma moeda).** Liu & Tsyvinski (versão NBER de 2018) regridem o retorno de
BTC no retorno anterior. Na frequência **semanal**, o retorno desta semana prevê o das próximas 1, 2 e 3 semanas com
coeficiente 0,19–0,22 e t de bootstrap 2,17 / 2,73 / 2,47; na 4.ª semana o t de bootstrap cai para 1,40. Em
tamanho: um desvio-padrão a mais de retorno semanal (16,64 %) dá cerca de +3,2 p.p. na semana seguinte. Separando
as semanas em quintis pelo retorno da semana corrente, a semana seguinte ao quintil mais alto rendeu 11,22 % contra
2,60 % no mais baixo (cortes com a amostra toda); com cortes fixados só com os dois primeiros anos (a versão sem
look-ahead do próprio artigo), 7,88 % contra 3,35 % — diferença de 4,53 p.p. Na frequência **diária** o efeito é
bem mais fraco: o coeficiente de 1 dia (0,06) é significativo com erro-padrão comum (t 2,96) mas **não** com bootstrap
(t 1,22); só os dias 5 e 6 à frente passam no bootstrap. Para XRP e ETH o artigo só mostra o diário: XRP positivo
de 1 a 5 dias, ETH positivo em 1 dia e **negativo** em 5 dias; o próprio artigo diz que em ETH o efeito é menos
significativo.

**Transversal (comparar moedas entre si).** Liu, Tsyvinski & Wu (NBER 2019) ordenam toda semana as moedas com
capitalização acima de 1 milhão de US$ (109 em 2014, 1 583 em 2018) pelo retorno de 1 a 4 semanas e compram o
quintil de cima contra o de baixo, ponderado por valor. O spread semanal foi 2,7 % (1 semana, t 1,99), 3,3 % (2
semanas), 4,1 % (3 semanas, t 2,74) e 2,5 % (4 semanas); com 8, 16, 50 e 100 semanas não foi significativo. O efeito
mora nas **maiores daquela amostra**: acima da mediana de tamanho, 4,2 %/semana significativo; abaixo, 0,6 % não
significativo ("acima da mediana" de >1 000 moedas não é o mesmo que o top-20 líquido da Binance). Trocar o lado
vendido por BTC vendido quase não muda o resultado. Tudo **sem custo de transação**.

**Contra, e mais recente.**
- Grobys & Sapkota (2019), 143 moedas de prova de trabalho negociadas desde antes do fim de 2014, 2014–2018, em
  **meses**: nenhuma estratégia transversal (12-1-1, 6-1-1, 1-0-1) teve retorno significativo, e o momentum de série
  temporal de 12, 6 e 1 mês também não foi significativo a 5 % (t 1,65 / 1,84 / 0,41 — os dois primeiros marginais).
  Horizonte mensal, não semanal — conflita com o semanal só em parte.
- Grobys, Kolari, Sandretto, Shahzad & Äijö (2025), as 30 maiores por capitalização em cada virada de ano (89 moedas
  distintas), formação de 30 dias, pula 1 dia, segura 1 semana, quintis igual-ponderados comprado/vendido,
  jan/2016–dez/2023 (416 semanas): **0,90 %/semana, não significativo** no período todo; 1,74 %/semana (só a 10 %) até
  jul/2020; negativo e não significativo depois de ago/2020. Uma única semana (dez/2020, uma moeda que subiu ~1 400 % no
  **lado vendido**) custou −255 %; cortada essa observação, o período todo dá 1,51 %/semana (t 2,63). O índice
  igual-ponderado das mesmas 30 rendeu mais que o momentum nos três recortes. Com gestão de volatilidade, o momentum
  das 30 maiores melhora (alfa de 0,76 a 1,69 %/semana, t 2,00–3,21); a versão ponderada por valor com 2 500 moedas,
  gerida, fica em torno de zero. Leitura justa: evidência de **fragilidade e risco de cauda**, com resultado misto —
  não de que "momentum morreu depois de 2020".
- Arefev (SSRN 2026, **nota não revisada, só o resumo lido**): perpétuos USDⓈ-M da Binance, 2020–2026, 832 símbolos
  com tratamento de sobrevivência, parâmetros pré-registrados: o spread bruto de 1 semana/1 semana foi +0,573 %/semana
  contra ~0,40 p.p./semana de custo realista; líquido, nenhuma das duas especificações se distingue de zero, e a de
  2/2 semanas troca de sinal conforme o dia da semana do rebalanceamento.
- Begušić & Kostanjčar (arXiv 2019, preprint): momentum de 2 semanas forte só nas moedas mais líquidas (2015–2019).
- Já na base: [[KB-0002-momentum-e-reversao-em-cripto]] (Dobrynskaya: momentum até 2–4 semanas, reversão acima de ~1
  mês, puxada pelas antigas perdedoras).

## Onde foi mostrado

| estudo | mercado | período | horizonte | custos | tipo |
|---|---|---|---|---|---|
| Liu & Tsyvinski (NBER 2018) | BTC (CoinDesk); XRP, ETH só diário | 2011–05/2018 (BTC) | 1–7 d; 1–4 sem | não | série temporal, 1 ativo por vez |
| Liu, Tsyvinski & Wu (NBER 2019) | 109 → 1 583 moedas > US$ 1 M | 2014–2018 | formação 1–100 sem, segura 1 sem | não | transversal comprado/vendido |
| Grobys & Sapkota (2019) | 143 moedas PoW | 2014–2018 | 1–12 meses | não | transversal + série temporal |
| Grobys et al. (2025) | top-30 por capitalização | 2016–2023 | 30 d → 1 sem | não | transversal comprado/vendido |
| Arefev (2026, resumo) | perpétuos Binance | 2020–2026 | 1–2 sem | **sim** | transversal comprado/vendido |

Nenhum dos consultados testa **só compra à vista** contra **segurar a mesma cesta** e contra **segurar BTC**, líquido
de custo, depois de 2020. O único com custo e depois de 2020 não é revisado e é comprado/vendido em perpétuo.

**O que não consegui abrir e por isso não cito com número:** a versão publicada na RFS (2021) de Liu & Tsyvinski
(OUP devolve 403; o resumo via Crossref confirma que a versão final mantém um "strong time-series momentum effect",
mas amostra e números da versão final não foram verificados — tudo acima vem da versão NBER de 2018, que abriu); o
texto integral de Arefev (SSRN 403); Grobys, Sandretto & Äijö, "On survivor cryptocurrency momentum" (Finance
Research Letters 2026, sem acesso aberto) — o título interessa à cláusula de sobrevivência, mas não li.

## Como mediríamos aqui

- **Dado que existe hoje: nenhum.** Consulta única de cobertura na VPS (28/09/2026, só contagens): `candles` com
  `timeframe = '1d'` e `is_final` tem **0 linhas** (0 mercados, nenhuma data). `spot_desk_markets` tem 56 linhas, 38
  habilitadas. Não verifiquei `1h`/`4h` (a regra da tarefa era uma consulta só).
- **Dado a obter (público, sem chave):** velas diárias dos pares USDT à vista da Binance desde o lançamento (BTCUSDT
  em ago/2017), pelo arquivo público `data.binance.vision` (`data/spot/monthly/klines/<PAR>/1d/<PAR>-1d-AAAA-MM.zip`;
  checado só com `HEAD`, sem baixar preço) ou por `GET /api/v3/klines` com `interval=1d` (público, peso 2, até 1 000
  velas por chamada — o adaptador `hunter_exchanges/binance_spot/rest.py` já usa o endpoint para `1m`). A condição dura
  é a **lista de todos os pares USDT que existiram**, incluindo deslistados: o `exchangeInfo` de hoje não basta.
  Onde gravar (partição `candles_1d`, retenção sem limite, ou artefato de pesquisa) é decisão do orquestrador.
- **Universo (sem sobrevivência):** "cripto grande" vira **mais negociada na Binance** — os 20 pares USDT à vista de
  maior volume em USDT nos 30 dias anteriores, com dados anteriores apenas, incluindo os depois deslistados. Volume
  alto não garante capitalização alta; não temos capitalização ponto-no-tempo e o volume é o que mede se dá para
  negociar. O mapa `spot/1` foi escolhido em 09/2026 entre os que existem hoje com rota na Jupiter — sobrevivente por
  construção, só entra como leitura descritiva.
- **Sem look-ahead:** o sinal usa só velas finais com fechamento até T − 1 dia (uma barra de folga entre o último
  preço lido e a ordem); a execução é na abertura da vela que começa em T. Ranking de volume, idade de listagem e
  exclusões seguem a mesma regra, e a classificação de um ativo é a que ele tinha em T (uma moeda desenhada para
  paridade com o dólar fica fora mesmo depois de desancorar).
- **Custo:** 0,15 % por perna, proporcional, sobre a mudança de peso contra o **peso efetivo** antes do rebalanceamento
  (depois da valorização da semana, inclusive a venda de quem saiu do universo) — ≈ 0,30 % ida e volta, a hipótese de
  papel de [[KB-0145-binance-como-sinal-solana-como-execucao]] para a Jupiter em tier A. A mesma nota assume ainda
  **0,001 SOL fixo por perna**, que o teste **não** inclui: numa ficha de 0,05 SOL isso seria 2 % por perna. Portanto o
  teste não demonstra viabilidade na Jupiter em ficha pequena; isso fica para a porta de papel.
- **Controles:** a carteira igual-ponderada **sempre comprada** no mesmo universo, BTC comprado-e-segurado, e caixa.
  Bater o caixa num mercado que subiu não prova nada; bater a própria cesta é a pergunta. Sem custo e com caixa a zero,
  D_ts = −(1/N)·Σ dos retornos das moedas com sinal ≤ 0: mede o resultado de **evitar** essas moedas (com mudança de
  exposição), não previsibilidade ajustada a risco.

## Hipótese testável — rascunho da H-024 (o orquestrador registra na fila)

```markdown
## H-024 — Momentum semanal de série temporal em cripto grande (à vista, só compra)

- **origem:** [[KB-0164-momentum-semanal-em-cripto-grande]] — Liu & Tsyvinski (NBER w24877): em BTC 2011–05/2018 o retorno de uma semana prevê o das 1–3 seguintes (t de bootstrap 2,17–2,73), sem custo e só num ativo; Liu, Tsyvinski & Wu (NBER w25882): momentum transversal de 1–4 semanas em 2014–2018, bruto, concentrado nas maiores (4,2 %/sem acima da mediana de tamanho); frágil depois: Grobys et al. (2025, top-30, 2016–2023, comprado/vendido) 0,90 %/sem não significativo, negativo depois de jul/2020, uma semana de −255 % vinda do lado vendido; Arefev (SSRN 2026, só resumo) some depois de custo nos perpétuos da Binance 2020–2026; [[KB-0002-momentum-e-reversao-em-cripto]] (momentum até 2–4 semanas, reversão depois de ~1 mês). [[KB-0149-o-que-a-mesa-real-ensinou]] §7: nunca medimos vantagem acima de 5 min; [[KB-0163-perto-da-maxima-de-24h-nao-separa-os-sinais-do-lab]]: a 1.ª hipótese da segunda frente não confirmou e não testa regra semanal. Everton, 28/09/2026: "momentum semanal em cripto grande"
- **variável:** `sinal_ts_14d` = m(i,T) = C(i,d) ÷ C(i,d−14) − 1, com T = segunda-feira 00:00 UTC, d = a última vela diária final com fechamento ≤ T − 1 dia (a de sábado; uma barra de folga entre o sinal e a ordem) e d−14 = a vela **14 dias de calendário** antes (faltando qualquer das duas, a moeda não é elegível naquela semana); regra só-compra w(i,T) = 1[m > 0] ÷ N_T, o resto em caixa USDT a 0 %; execução na abertura da vela que começa em T; segura até a abertura de T + 7 d. **Primária** D_ts = média da série semanal **pareada** d_t = r_TS,t − r_EW,t, retornos líquidos, EW = a mesma cesta sempre comprada a 1/N_T com o mesmo custo — mede o resultado de evitar as moedas com sinal ≤ 0, não previsibilidade ajustada a risco. **Secundária** (mesma família, Holm sobre os dois p unilaterais): D_cs = carteira só-compra igual-ponderada nas ⌈N_T/3⌉ moedas de maior m (desempate pelo volume de 30 d) − EW. 7 e 28 dias entram só como patamar, fora da família. Descritivo: TS contra BTC comprado-e-segurado e contra caixa (média, Sharpe, drawdown máximo)
- **população:** T de toda segunda-feira desde a primeira em que N_T ≥ 20 (determinada só por datas de listagem, sem preço) até a última semana completa antes da execução; universo **ponto-no-tempo** em cada T: os 20 pares USDT à vista da Binance de maior soma de `quote_volume` nas velas diárias com abertura em [T − 30 d, T − 1 d] (vela ausente = volume zero; desempate por símbolo), listados há ≥ 35 dias em T − 1 d, **incluindo pares depois deslistados**; fora, pelo **desenho do ativo** conhecido em T: moedas desenhadas para paridade com moeda fiduciária (mesmo depois de desancorar), tokens alavancados (UP/DOWN/BULL/BEAR) e embrulhos/derivados de ativo já no universo (regras congeladas antes de baixar preço); cada símbolo da Binance é uma série, e troca de ticker ou redenominação sem continuidade oficial documentada é deslistagem + listagem nova; semana avaliável = N_T ≥ 15 (entre 15 e 19 usa 1/N_T); lacuna de dados depois da compra não tira a moeda da carteira (preço carregado do último fechamento até voltar); custo 0,15 % por perna, proporcional, sobre |peso novo − peso efetivo depois da valorização|, inclusive saídas do universo, sem taxa fixa (o teste não demonstra viabilidade na Jupiter em ficha pequena); série que acaba com posição aberta (deslistagem ou suspensão) é medida em **dois limites** — otimista (sai no último fechamento) e pessimista (perda total da posição). O mapa `spot/1` (`spot_desk_markets`) é sobrevivente de 09/2026 e entra só como leitura descritiva
- **previsão:** D_ts ≥ **+0,25 p.p./semana** na estimativa pontual (≈ metade do spread bruto comprado/vendido de 0,57 %/sem de Arefev — escolha, não derivação); IC 95 % **marginal** (percentil) por bootstrap de blocos móveis contíguos de 8 semanas sobre d_t (10 000 reamostras, semente 20260928, as mesmas semanas para todos os braços, blocos concatenados até n e truncados) com limite inferior > 0; p unilateral do bootstrap centrado sob H0: D ≤ 0 abaixo do limiar de Holm (α 0,05, dois testes); carteira TS **lucrativa em nível** (média semanal líquida > 0); **patamar** — D_ts > 0 também com 7 e 28 dias; **corte de período** — D_ts > 0 em cada um dos dois períodos, antes de 2022-01-01 e a partir dele (o trecho que a literatura aponta como fraco); todas as condições valem nos **dois limites** de deslistagem. Secundária: D_cs com as mesmas cláusulas. Sensibilidade reportada, que não decide: blocos de 4 e 16 semanas. **Porta para papel** (só avaliada depois de CONFIRMA; falhar nela não é refutação, é não promover): D_ts > 0 com custo de 0,50 % por perna; D_ts > 0 com a convenção alternativa de execução (sinal até o fechamento ≤ T e execução no fechamento da vela que começa em T, todas as execuções deslocadas e as posições anteriores carregadas até a execução seguinte); D_ts > 0 em ≥ 5 dos 7 dias da semana usados como dia de rebalanceamento (diagnóstico: as fases são dependentes, não são 7 réplicas); Sharpe da TS ≥ Sharpe do BTC comprado-e-segurado na mesma janela
- **refutação:** limite superior do IC 95 % de D_ts < +0,25 p.p./semana → REFUTA o tamanho previsto (não qualquer efeito; se o limite superior também ficar < 0, registra-se que evitar as moedas de sinal ≤ 0 piorou); qualquer outra falha da previsão → NÃO CONFIRMA, inclusive quando os dois limites de deslistagem dão conclusões diferentes (identificação parcial); **limite de dado** se não for possível reconstruir a lista de pares USDT à vista existentes em cada data, incluindo deslistados (nunca rodar só com os sobreviventes de hoje), ou se houver menos de 200 semanas avaliáveis; **poder declarado antes:** sob independência e desvio-padrão semanal de d_t estimado a priori em ~5 p.p. (não medido), com ~350–400 semanas o meio-IC fica em ~±0,5 p.p./semana e 80 % de poder só existe para efeitos de ~0,7–0,8 p.p./semana; +0,25 pediria ~3 000 semanas independentes. Sem efeito grande, o desfecho esperado é NÃO CONFIRMA, e isso não autoriza mudar janela, lookback, N, bloco ou custo depois de ver
- **registro:** 28/09/2026, antes de baixar qualquer vela diária ou olhar qualquer retorno; a única consulta aos nossos dados foi uma contagem de cobertura (`candles` `1d` final: 0 linhas; `spot_desk_markets`: 56 linhas, 38 habilitadas)
- **status:** aberta
```

## Por que pode falhar

- **Sobrevivência do universo.** Escolher hoje as moedas do mapa `spot/1` ou o top-20 de hoje e voltar no tempo é
  comprar só as que sobreviveram — viés para cima em qualquer estratégia comprada. Por isso o universo é ponto-no-tempo
  com deslistados, e sem a lista completa a hipótese para em limite de dado.
- **Look-ahead de calendário e de disponibilidade.** A vela diária fecha às 23:59:59.999 UTC; ler esse fechamento e
  receber o primeiro negócio de 00:00 sem latência é idealização. Daí a barra de folga no sinal. Ranking de volume,
  idade de listagem e classificação (stablecoin, embrulho) só com o que se sabia em T.
- **Deslistagem vista só depois.** "Último fechamento" só se sabe em retrospecto; uma suspensão abrupta pode prender a
  posição. Os dois limites (último fechamento e perda total) cercam o erro; se a conclusão muda entre eles, não
  confirma.
- **Custo e giro.** A literatura favorável é toda bruta, e o único estudo líquido depois de 2020 (resumo de Arefev) viu
  o efeito sumir. O custo proporcional pesa pelo capital que gira, não por posição; a taxa fixa por perna da Jupiter é
  o que mata em ficha pequena e fica fora do teste.
- **Fragilidade depois de 2020.** Grobys et al. (2025) acham o momentum das 30 maiores sem significância e negativo
  depois de jul/2020 (comprado/vendido). A janela útil da Binance (≈ 2018/2019–2026) é quase toda esse período — daí o
  corte em 2022.
- **Cauda de uma moeda.** Nos estudos comprado/vendido o crash veio de uma moeda disparando no lado vendido; só compra
  não tem esse lado, mas tem o espelho: entrar numa moeda que acabou de subir e devolve tudo, ou ficar presa numa
  deslistagem.
- **Mercado que só sobe.** Na amostra de Liu & Tsyvinski até o quintil mais baixo teve semana seguinte positiva
  (3,35 %). Ir para o caixa nas semanas ruins pode render **menos** que segurar — por isso o controle é a cesta sempre
  comprada, e a comparação com BTC é por Sharpe, na porta de papel.
- **Pouco poder.** Algumas centenas de semanas, com moedas muito correlacionadas: a amostra efetiva é de semanas, não
  de moeda-semanas, e um painel moeda-semana não resolve isso sozinho (muda o estimando e ainda exige tratar a
  dependência no tempo). O desenho só detecta efeito grande.
- **Preço da Binance ≠ preço da Jupiter.** O teste é em preço da Binance; a execução do `spot/1` é na Solana, com
  cotação ~9 bp acima e representações de baixa capitalização que podem desancorar
  ([[KB-0145-binance-como-sinal-solana-como-execucao]]). Uma confirmação aqui ainda precisa de papel à frente na mesa.
- **Importação de horizonte.** A literatura de meses ([[KB-0001-momentum-academico-e-o-que-nao-se-transfere]]) não vale
  para semanas por analogia; a evidência citada aqui é semanal, mas de outra época e sem custo.

## Segunda opinião (Astra)

Consulta de 28/09/2026 (`.claude/state/astra-review-KB-momentum-semanal.md`), sobre o primeiro rascunho desta nota.

**Concorda** com: D_ts de 14 dias como primária (BTC como primária misturaria timing com seleção de moedas; nada na
literatura promove 7 ou 28 d); a cesta sempre comprada como controle, BTC e caixa como referências; Holm sobre D_ts e
D_cs; universo ponto-no-tempo com deslistados e parada por limite de dado sem eles; o mapa `spot/1` só descritivo; não
confundir falta de poder com refutação; e abrir uma frente semanal, porque a H-023 não a testa. Conferiu no texto
integral os números de Grobys & Sapkota, de Grobys et al. (2025) e de Liu, Tsyvinski & Wu (por uma cópia dos autores
em Yale); o PDF da NBER de Liu & Tsyvinski deu 403 para ela (abriu para mim) — não achou erro demonstrável nos números.

**Must-fix aceitos, todos antes de qualquer retorno:**
1. Fórmula completa do retorno (`− 1`) e 14 dias **de calendário** — sem isso, a leitura literal compra todas as moedas
   (TS = EW), e lacunas esticam o horizonte.
2. Deslistagem executável: "sai no último fechamento" só se sabe depois; o −30 % arbitrário não era conservador. Troquei
   por dois limites (último fechamento / perda total), com NÃO CONFIRMA se divergirem.
3. Contrato de dados ponto-no-tempo: classificação pelo desenho do ativo em T (a stablecoin que desancorou não entra
   depois), volume com janela e desempate definidos, lacuna depois da compra não apaga a perda, e uma barra de folga
   entre o fechamento lido e a ordem.
4. Custo: a KB-0145 assume também 0,001 SOL fixo por perna, que eu tinha omitido; giro contado contra o peso efetivo,
   não contra o alvo anterior; e "o giro de 20 posições soma" estava errado (custo proporcional pesa por capital).
5. Inferência congelada: série pareada d_t, blocos móveis contíguos de 8 semanas, mesmas semanas para todos os braços,
   IC marginal, p unilateral centrado; blocos de 4 e 16 só como sensibilidade.
6. Refutação pelo MRE, como manda o `docs/RESEARCH.md` (IC superior < +0,25 → REFUTA o tamanho previsto); o piso de
   +0,10 que eu tinha posto divergia da convenção da casa.
7. Síntese equilibrada: "não encontramos entre as fontes consultadas" em vez de "não há"; os estudos recentes são
   comprado/vendido e mostram fragilidade e cauda, não refutação da regra só-compra; faltava a melhora com gestão de
   volatilidade nas 30 maiores.

Também absorvidos: Grobys & Sapkota "não significativo a 5 %" (dois t marginais); "grandes" em Liu, Tsyvinski & Wu é
acima da mediana daquela amostra; o universo chama-se "mais negociadas", não "maiores"; tercil com arredondamento e
desempate definidos; o atraso de execução desloca todas as execuções em vez de encurtar a posse para seis dias; as
sete fases são diagnóstico dependente, não réplicas. Contas de poder dela (normal, independente, σ = 5 p.p.): meio-IC
0,49–0,52 p.p. para 400–350 semanas; 80 % de poder para 0,70–0,82 p.p.; +0,25 pediria 3 140–3 802 semanas. Mantive o
MRE econômico em +0,25 e declarei o poder, como ela recomendou.

**Divergência (parcial), com decisão:** ela sugeriu tirar da confirmação o corte de período, a fase, o Sharpe contra
BTC e os estresses. Tirei fase, Sharpe, custo de 0,50 % e a convenção alternativa de execução para uma **porta de
papel** separada (falhar nela não é refutação). **Mantive o corte de período (antes/depois de 2022) dentro do
CONFIRMA**, porque o `docs/RESEARCH.md` faz do split parte do CONFIRMA e porque a queda depois de 2020 é o principal
aviso da literatura — confirmar só pelo trecho 2018–2021 seria confirmar a época que já sabemos que era boa. Mantive
também os dois limites de deslistagem dentro do CONFIRMA: são validade da medida, não operação.

## Relacionados

[[Proximas Hipoteses]] · [[Fila de Hipoteses]] · [[KB-0001-momentum-academico-e-o-que-nao-se-transfere]] ·
[[KB-0002-momentum-e-reversao-em-cripto]] · [[KB-0145-binance-como-sinal-solana-como-execucao]] ·
[[KB-0149-o-que-a-mesa-real-ensinou]] · [[KB-0163-perto-da-maxima-de-24h-nao-separa-os-sinais-do-lab]] ·
[[Strategy Backlog]]
