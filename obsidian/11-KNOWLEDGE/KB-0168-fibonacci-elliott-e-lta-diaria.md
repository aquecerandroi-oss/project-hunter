---
tags: [knowledge, leitura, analise-tecnica, grafico, fibonacci, elliott, linha-de-tendencia, lta, suporte-resistencia, cripto, hipotese]
tema: "as técnicas das duas figuras do Everton (retração e extensão de Fibonacci, contagem de Elliott, LTA diária) e o artigo do InfoMoney sobre linhas de tendência — o que é calculável no fechamento do dia e o que é desenho em retrospectiva; a evidência aberta sobre níveis de Fibonacci (as viradas do Dow não se agrupam neles mais que o acaso; o resultado favorável que achei é só resumo de preprint), a ausência de teste objetivo da contagem de Elliott e a de estudo revisado da LTA diagonal como regra com custo; origem da H-025 e da H-026"
fonte: "Bruno Nadai, 'O que é uma linha de tendência na análise gráfica?' (InfoMoney, 09/02/2024 — lido na íntegra); Ramyar, 'Essays on technical analysis in financial markets' (tese de doutorado, City University London, 2006 — caps. 2 e 3 lidos, o 3 com o procedimento Batchelor–Ramyar); Gurrib, Nourani & Bhaskaran (Financial Innovation 8:8, 2022 — lido na íntegra); Shanaev & Gibson, 'Can Returns Breed Like Rabbits?' (SSRN 4212430, 2022 — só o resumo); Garzarelli, Cristelli, Pompa, Zaccaria & Pietronero (Scientific Reports 4:4487, 2014 — versão arXiv 1110.5197 lida em parte); Kavajecz & Odders-White (Review of Financial Studies 17(4), 2004 — só o resumo); Chendroyaperumal & Karthikeyan (SSRN 1887789, 2011 — só o resumo); Atsalakis, Dimitrakakis & Zopounidis (ESWA 38, 2011) e Volna, Kotyrba & Jarusek (Computers & Mathematics with Applications, 2013) — só título; Tsinaslanidis, Guijarro & Voukelatos (ESWA 187, 2022) — não abriu"
fonte_url: https://www.infomoney.com.br/guias/o-que-e-uma-linha-de-tendencia-na-analise-grafica/ · https://openaccess.city.ac.uk/id/eprint/18945/1/441530.pdf · https://doi.org/10.1186/s40854-021-00311-8 · https://doi.org/10.2139/ssrn.4212430 · https://arxiv.org/abs/1110.5197 · https://doi.org/10.1093/rfs/hhg057 · https://doi.org/10.2139/ssrn.1887789 · https://doi.org/10.1016/j.eswa.2011.01.068 · https://doi.org/10.1016/j.camwa.2013.01.012 · https://doi.org/10.1016/j.eswa.2021.115893
lido_em: 2026-09-28
evidencia: "mista — uma tese examinada lida nos capítulos relevantes (Ramyar), um artigo revisado lido na íntegra (Gurrib et al., fraco pelo desenho), um artigo revisado lido em parte na versão arXiv (Garzarelli et al.), resumos apenas (Shanaev & Gibson, preprint; Kavajecz & Odders-White; Chendroyaperumal & Karthikeyan), títulos apenas (Atsalakis et al.; Volna et al.), um artigo não aberto (Tsinaslanidis et al., bloqueado); texto de divulgação (InfoMoney) lido na íntegra; nenhuma medição nesta nota — a medição está na KB-0169"
hipotese_testavel: sim
astra: "desenho revisado antes de qualquer desfecho (6 must-fix aceitos numa emenda datada; o contraste incremental ficou fora e a leitura foi restringida) — ver Revisoes-Astra/H-025-H-026-prereg"
status: vivo
owner: sexta-feira
updated: 2026-09-28
confiança: "?"
tipo: leitura
hipotese: H-025, H-026
variavel: —
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: "medição em KB-0169 (R85); a contagem de Elliott não vira hipótese sem uma operacionalização causal publicada que eu possa ler"
classe_de_perda: —
mercado: cripto
---

# KB-0168 — Fibonacci, Elliott e a LTA diária: o que é regra e o que é desenho

> **Leitura curada, sem medição nesta nota.** O Everton trouxe duas figuras (28/09/2026) — o BTC/USD diário de
> nov/2024 a mai/2025 com retração de Fibonacci da máxima de ~109 mil à mínima de ~74,4 mil, o rótulo "retraiu 50 %",
> "rompeu diretamente", a extensão 1,618 como alvo (~109,3 mil), uma contagem de Elliott 1–5 e uma média de ~20
> períodos; e uma LTA diária por fundos ascendentes — mais o artigo do InfoMoney sobre linha de tendência. **Eu não vi
> as imagens:** a descrição é a do orquestrador. O que dá para testar honestamente virou a **H-025** (retração de
> Fibonacci) e a **H-026** (LTA diária, braços A e B) na [[Fila de Hipoteses]], pré-registradas antes de qualquer
> desfecho; o resultado está em [[KB-0169-fibonacci-e-lta-diaria-no-dado]].

## O que afirma

1. **Tudo nas figuras depende de onde começa e termina a "perna".** Retração, extensão e contagem de ondas são
   calculadas sobre topos e fundos; num gráfico já pronto o olho escolhe os extremos que "funcionaram". No fechamento
   do dia, o topo só é topo depois de alguns dias sem ser superado — a regra honesta paga esse atraso.
2. **Os níveis de Fibonacci não se mostraram especiais nas viradas de um índice longo.** Nas 430 fases de alta e
   baixa do Dow Jones de 1915 a 2003 (Ramyar, cap. 3, procedimento Batchelor–Ramyar), as razões entre fases não se
   agrupam em 0,382/0,5/0,618/1,618 mais que o acaso de um bootstrap do próprio índice. O único resultado favorável
   que achei é o **resumo** de um preprint (Shanaev & Gibson, 2022).
3. **A contagem de Elliott não tem, nos textos que abri, uma versão objetiva e causal testada.** Não criei estratégia
   com ela (ver abaixo).
4. **A LTA diagonal como regra de compra com custo não tem estudo revisado que eu tenha achado.** O que existe é
   evidência de que **níveis horizontais** seguram o preço mais que o acaso e que a chance de repique cresce com os
   repiques anteriores (Garzarelli et al.; Osler e Chung & Bellotti na [[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]])
   — estatística de parada, não lucro — e a nossa própria medição de 15 min ([[EXP-0016-trendline-breakout]]).

## O artigo do InfoMoney (síntese minha)

Bruno Nadai (09/02/2024) define tendência por topos e fundos e dá as regras da linha:

- **LTA** liga dois fundos ascendentes, do mais baixo ao mais alto; **LTB**, dois topos descendentes.
- O **terceiro toque** sem rompimento confirma a linha; mais toques, mais significativa — nas palavras dele, "quanto
  mais toques tiverem na linha, mais significativa se torna essa linha de tendência".
- Operar a favor da tendência, de preferência no início dela e em tempos gráficos maiores.
- **Compra A — retorno na LTA:** o preço sobe, volta à LTA, testa e se mantém acima → compra.
- **Compra B — rompimento de topo:** depois de testar a LTA, o preço sobe e rompe o topo anterior → compra.
- **Canal:** linha de retorno paralela passando pelo pivô oposto; operação contra a tendência na linha de retorno
  (venda no canal de alta), para perfil "mais agressivo".
- **Aviso de reversão:** topo mais alto que falha e perda da LTA.

**O que o artigo não dá:** evidência, stop, alvo, tamanho, volume, custo, nem regra para escolher entre as várias
linhas possíveis. As figuras dele (dólar futuro de 5 min, USIM e PETR4 diários, índice futuro) são exemplos
escolhidos, não amostra.

## Onde foi mostrado — um estudo por vez

| estudo | mercado | período | o que mede | custo | o que eu abri |
|---|---|---|---|---|---|
| Ramyar 2006, cap. 3 (procedimento Batchelor–Ramyar) | Dow Jones diário | jan/1915–jun/2003 | razões de retração e projeção entre 430 fases (preço, log-preço, % e duração) contra 10 razões redondas e de Fibonacci ± 0,025 | não se aplica (não é estratégia) | tese aberta (City Research Online), caps. 2–3 |
| Shanaev & Gibson 2022 | índices, câmbio, ações do S&P 500 | — (não li) | teste econométrico da capacidade preditiva das retrações | resumo fala de alfa em modelos de fatores | **só o resumo** (preprint SSRN) |
| Gurrib, Nourani & Bhaskaran 2022 | 10 ações de energia do S&P 1500 e 4 criptos de energia | nov/2017–jan/2020, diário | estratégia: compra ao cruzar 23,6 % em alta, sai abaixo de 61,8 % | **nenhum** | artigo inteiro (acesso aberto) |
| Garzarelli et al. 2014 | 9 ações da Bolsa de Londres, tique a tique | 2002 (251 pregões) | P(repique \| repiques anteriores) em máximos/mínimos locais contra retornos embaralhados | não se aplica | versão arXiv, seções 1–3 |
| Kavajecz & Odders-White 2004 | livro de ordens | — | suporte/resistência × profundidade do livro | não se aplica | **só o resumo** |
| Chendroyaperumal & Karthikeyan 2011 | ações da Índia | — | Elliott | — | **só o resumo** |

**Números que conferi na fonte:**

- **Ramyar, tabela 3-6:** Kolmogorov–Smirnov entre a distribuição real de cada uma das 16 razões e a de 2 000 réplicas
  de bootstrap estacionário (bloco médio de 20 pregões) — p de **0,298 a 0,940**, nenhum abaixo de 0,10. **Tabela 3-7:**
  descontada a razão 4,236 (pouquíssimas ocorrências), **15 de 144** células ficam acima do percentil 90 do bootstrap,
  contra **14,4** esperadas sob o nulo, sem padrão por tipo de razão; blocos de 10 e 40 pregões e bandas de 0,01 e 0,05
  não mudam o resultado. Conclusão do autor: a ideia de que frações redondas e razões de Fibonacci ocorrem no Dow
  "pode ser descartada". É uma tese de doutorado examinada, não artigo de periódico; é índice, não cripto, e mede
  **onde as viradas acontecem**, não se comprar num nível paga.
- **Gurrib et al.:** a perna é "a diferença entre a máxima e a mínima **durante** a tendência anterior" — escolhida
  sobre a tendência já inteira, portanto **retrospectiva**; tendência pela inclinação de uma regressão de 50 dias;
  nenhum custo, nenhum teste de significância; nas criptos, 0 a 5 posições por moeda, índices de Sharpe de **24,10**,
  **17,34** e **16 568,33** (poucas operações, desvio perto de zero) e compra-e-segura de −93,8 % a −98,7 %. Não serve
  como evidência de vantagem; serve como exemplo do problema do desenho retrospectivo.
- **Shanaev & Gibson (resumo):** retrações "proeminentes" em índices internacionais e câmbio, com os níveis 0,0 %,
  38,1 %, 50,0 %, 61,2 % e 100,0 % (assim no resumo) como os mais importantes, e incluir 14,6/23,6/76,4/78,6/85,4 %
  **piora** o modelo; uma carteira de ações do S&P 500 comprada perto do suporte e vendida perto da resistência tem alfa
  positivo. Não li o método; o número não entra em nenhuma decisão.
- **Garzarelli et al.:** a probabilidade de repique nos níveis fica "bem acima de 0,5" nos dados e perto de 0,5 nos
  retornos embaralhados, e cresce com o número de repiques anteriores (teste χ²). Tique a tique, horizontal, sem
  estratégia — é o análogo mais próximo da frase "mais toques, mais significativa", e é sobre **nível**, não sobre
  linha inclinada.

## Elliott: por que não virou hipótese

Ramyar (cap. 2) resume o problema: a contagem de ondas é talvez o caso mais extremo de subjetividade na análise
técnica; Mandelbrot (1999) a descartou por isso, e os programas que a automatizam (EWaves, Advanced GET) em geral **não
concordam entre si** sobre a contagem; qualquer exame objetivo das proporções tem de ser **independente** da estrutura
de ondas que alguém enxerga. O resumo de Chendroyaperumal & Karthikeyan diz o mesmo (subjetividade alta, sem acordo
sobre utilidade). As duas tentativas de automação que achei (Atsalakis et al. 2011, sistema neuro-fuzzy; Volna et al.
2013, classificadores) estão atrás de paywall — **só título**, nada delas entrou aqui.

O que seria objetivo: um zigue-zague confirmado causalmente (pivôs como os da H-025) e as três regras duras da contagem
(onda 2 não retrocede mais que 100 % da 1; a 3 não é a menor; a 4 não invade a 1). Mas, no fechamento do dia, várias
contagens satisfazem as regras ao mesmo tempo, o "grau" da onda é livre e a contagem é revista depois — a previsão
depende da contagem escolhida. A parte proporcional (onda 3 ≈ 1,618 × onda 1) é exatamente o que o Ramyar testou nas
projeções do Dow, sem agrupamento acima do acaso. **Sem uma operacionalização causal publicada que eu possa ler, não
crio estratégia nem hipótese de Elliott**; o que dele é mensurável (pivôs, retração, extensão) já está na H-025.

## Causal × retrospectivo — o que cada elemento das figuras vira no fechamento do dia

| elemento | versão causal (o que a H-025/H-026 usam) | o que só existe olhando para trás |
|---|---|---|
| topo/fundo da perna | pivô com 5 velas de cada lado, **conhecido 5 dias depois** | o topo "óbvio" do gráfico pronto |
| retração 50–61,8 % | primeiro fechamento na faixa **depois** da confirmação do topo, vindo de cima | a faixa onde o preço "parou" |
| alvo na extensão 1,618 | alvo L + 1,618·(H − L) congelado na entrada, com stop abaixo do fundo e teto de 60 d | o alvo que "bateu" |
| LTA | reta por dois fundos confirmados, nasce 5 dias depois do 2.º, morre no fechamento abaixo | a linha redesenhada a cada fundo novo |
| 3.º toque | primeiro toque distinto depois do nascimento, com afastamento de 1 ATR entre toques | o toque "limpo" escolhido entre vários |
| rompimento do topo | fechamento acima da máxima entre os dois últimos toques, em até 20 dias | o rompimento que "foi" |
| contagem 1–5 de Elliott | — (não operacionalizada) | a contagem inteira |
| média de ~20 períodos | calculável, mas é tendência diária — objeto da C1 ([[Proximas Hipoteses]]) e vizinha da H-024 | — |

## Como mediríamos aqui

No painel diário do R84 ([[KB-0166-evitar-as-moedas-em-queda-nao-bate-a-cesta]]): 750 pares USDT à vista da Binance
com deslistados, universo ponto-no-tempo dos 20 de maior volume, compra na abertura seguinte ao sinal, 0,15 % por
perna, contra as moedas do mesmo universo, no mesmo dia, na mesma estrutura sem o gatilho. Parâmetros e leitura
congelados na [[Fila de Hipoteses]] (H-025, H-026, com a emenda datada depois da revisão da Astra); geometria herdada
da [[KB-0077-linhas-de-tendencia]] (pivô conhecido k velas depois) com as regras literais do artigo.

## Por que pode falhar

- **Retrospectiva:** qualquer versão que escolha a perna ou a linha olhando o gráfico inteiro fabrica vantagem — é o
  defeito de Gurrib et al. e o motivo de a guarda de prefixo ser obrigatória ([[KB-0149-o-que-a-mesa-real-ensinou]] §5
  item 24).
- **Controle, não mecanismo:** superar moedas sem recuo no mesmo dia pode ser reversão ou momentum transversal, não
  Fibonacci; a especificidade só aparece se a faixa 50–61,8 % bater as faixas vizinhas.
- **Transferência:** Ramyar é índice americano, Garzarelli é tique a tique em Londres, Gurrib são 4 criptos minúsculas;
  nada disso é top-20 da Binance no diário.
- **Leitura parcial:** Shanaev & Gibson, Kavajecz & Odders-White e Chendroyaperumal & Karthikeyan só no resumo;
  Atsalakis et al. e Volna et al. só no título; Tsinaslanidis et al. (identificação automática de retrações em três
  mercados de ações, ESWA 2022) **não abriu** (bloqueio do editor e do repositório), e nada dele entrou na síntese.

## Segunda opinião (Astra)

Revisou o **desenho** das H-025/H-026 antes de qualquer desfecho ([[06-DECISIONS/Revisoes-Astra/H-025-H-026-prereg|H-025-H-026-prereg]]):
seis must-fix aceitos numa emenda datada na Fila (início da busca da retração, toques distintos e P congelado,
significado do controle, inferência por dia, venda só em abertura real, relógio da saída estrutural). O contraste
incremental que ela propôs (placebos e pareamento por retorno prévio/ATR%) **não** foi congelado — ficou como limite
escrito da leitura. A revisão do resultado está na KB-0169.

## Relacionados

[[KB-0169-fibonacci-e-lta-diaria-no-dado]] · [[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]] ·
[[KB-0077-linhas-de-tendencia]] · [[KB-0003-rompimento-de-canal-e-data-snooping]] · [[EXP-0016-trendline-breakout]] ·
[[KB-0166-evitar-as-moedas-em-queda-nao-bate-a-cesta]] · [[Fila de Hipoteses]] · [[Proximas Hipoteses]] ·
[[Mapa de Estrategias]] · [[KB-0149-o-que-a-mesa-real-ensinou]]
