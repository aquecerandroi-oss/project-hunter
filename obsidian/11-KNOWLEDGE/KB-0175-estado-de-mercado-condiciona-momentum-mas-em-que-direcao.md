---
tags: [knowledge, leitura, momentum, estado-de-mercado, regime, crash, condicionamento, cripto, acoes, hipotese]
tema: "estado de mercado como condicionante de momentum — depois de mercado em alta o momentum transversal de ações rende mais; os crashes de momentum vêm depois de quedas, em alta volatilidade, junto com o repique; e o fator de tendência de cripto se diz robusto a estados — o que isso prevê (e não prevê) para a C1"
fonte: "Cooper, Gutierrez & Hameed, 'Market States and Momentum' (J. Finance 59(3), 2004 — só o resumo, OpenAlex); Daniel & Moskowitz, 'Momentum crashes' (JFE 122(2), 2016 — só o resumo, OpenAlex; já em KB-0035); Fieberg et al. (JFQA 60, 2025 — só o resumo); Hudson & Urquhart 2021 e Shen, Urquhart & Wang 2022 (versões já lidas em KB-0167; aqui o trecho sobre anos de queda, relido na versão aceita de Shen et al. no repositório de Reading)"
fonte_url: https://doi.org/10.1111/j.1540-6261.2004.00665.x · https://doi.org/10.1016/j.jfineco.2015.12.002 · https://doi.org/10.1017/S0022109024000747 · https://centaur.reading.ac.uk/100181/
lido_em: 2026-10-01
evidencia: "estudos revisados — dois só pelo resumo (Cooper et al.; Daniel & Moskowitz), um só pelo resumo (Fieberg et al.), um em versão aceita lida na íntegra (Shen et al.); nenhuma medição nossa"
hipotese_testavel: não
astra: "discorda em parte — revisada junto da síntese KB-0179; as correções que atingem esta nota foram aceitas (ver KB-0179 §Segunda opinião)"
status: vivo
owner: sexta-feira
updated: 2026-10-01
confiança: estudo revisado
tipo: leitura
hipotese: H-027
variavel: razao_mm20d (contexto; nenhuma medição aqui)
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: "nenhum; alimenta a leitura do resultado da H-027 em KB-0179"
classe_de_perda: —
mercado: cripto
---

# KB-0175 — Estado de mercado condiciona momentum, mas em que direção?

> **Leitura curada, sem medição nossa.** Que o lucro de momentum depende do estado do mercado é um resultado
> antigo e revisado. **A direção depende do que se chama de momentum e de estado:** o momentum transversal de
> ações rende mais **depois de alta** do mercado (Cooper et al.) e quebra **depois de queda**, quando o mercado
> repica (Daniel & Moskowitz); já as regras técnicas e o momentum intradiário em BTC entregam seu valor econômico
> **nos anos de queda** (Hudson & Urquhart; Shen et al.). A C1 prevê "melhor em tendência de alta" — a literatura
> apoia isso só por analogia com o momentum transversal de ações, e tem resultados vizinhos no sentido oposto.

## O que afirma (claim × evidência)

1. **Cooper, Gutierrez & Hameed 2004 (resumo).** Testam teorias de sobrerreação: o lucro de momentum depende do
   estado do mercado. Em ações americanas, 1929–1995, o lucro médio mensal de momentum foi de **0,93 %** depois de
   retornos de mercado positivos e de **−0,37 %** depois de negativos; o momentum de mercado em alta **reverte** no
   longo prazo; o resultado resiste a fatores macroeconômicos. *O resumo não diz a janela que define o estado;
   não a cito.*
2. **Daniel & Moskowitz 2016 (resumo; [[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]]).** Os
   crashes de momentum são em parte previsíveis: acontecem em estados de pânico, **depois de quedas** do mercado e
   com volatilidade alta, ao mesmo tempo que o repique. Uma estratégia dinâmica que prevê média e variância do
   momentum dobra, mais ou menos, alfa e Sharpe da estática.
3. **Fieberg et al. 2025 (resumo; [[KB-0173-tendencia-diaria-em-cripto-o-tamanho-publicado]]).** O fator de
   tendência transversal de cripto (CTREND) se diz robusto a subperíodos e **estados de mercado** — robusto quer
   dizer que o efeito persiste nos estados testados, **não** que seja igual entre eles (o resumo não afirma
   invariância); e é outro objeto (ordenar moedas entre si).
4. **Hudson & Urquhart 2021 e Shen et al. 2022 (já em [[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]]).**
   As regras técnicas diárias protegem nas quedas longas; o momentum intradiário de BTC (comprado e vendido) dá seu
   valor nos anos em que comprar e segurar perde (2014, 2015, 2018) e perde para ele nos anos de alta extrema
   (2013, 2016, 2017).

## Onde foi mostrado

| estudo | mercado | horizonte | estado | direção |
|---|---|---|---|---|
| Cooper et al. | ações EUA 1929–1995 | mensal, transversal | retorno passado do mercado | momentum ↑ depois de alta |
| Daniel & Moskowitz | ações EUA + outras classes | mensal, transversal | queda + volatilidade alta | crash no repique depois de queda |
| Fieberg et al. | >3.000 criptos | transversal | vários | sem dependência relevante (resumo) |
| Hudson & Urquhart / Shen et al. | BTC (e LTC, XRP, ETH) | diário / meia hora | ano de queda × de alta | valor econômico nos anos de queda |

## O que isso prevê para a C1

- **Pelo lado de Cooper et al.:** sinais de continuação em mercado acima da média de 20 dias deveriam render
  mais — a previsão registrada da H-027.
- **Pelo lado de Daniel & Moskowitz:** o perigo está nos **repiques depois de queda**. Hipótese nossa, por
  analogia (não testada por eles nem por ninguém que li para estas entradas): um sinal de continuação de alta
  disparado com `razao_mm20d ≤ 0` pode ser um repique que continua no curtíssimo prazo. Isso daria sinal
  **negativo** para β na H-027 sem contradizer a literatura — "compatível" no sentido de "não contradiz", não de
  "previsto".
- **Pelo lado das regras técnicas de BTC:** a vantagem das regras de tendência é estar **fora** na queda, não
  ganhar mais na alta ([[KB-0174-o-filtro-de-tendencia-corta-queda-nao-acrescenta-alta]]).
- **Leitura justa:** a literatura sustenta que **o estado importa**, não o sinal do efeito para sinais de 5–15 min
  em perpétuos. Um β próximo de zero, ou de qualquer sinal com IC largo, é compatível com ela.

## Como mediríamos aqui

Já no desenho da H-027 ([[Fila de Hipoteses]]): o estado é a razão de 20 dias de **cada mercado**, não o do
mercado agregado. Como os perpétuos andam juntos (fator BTC,
[[KB-0034-btc-como-fator-e-o-regime-global-que-e-so-o-btc]]), o estado por mercado é em boa parte o estado do
mercado inteiro naquele dia — e a coorte tem 23 dias. Um descritivo útil, sem rótulo: o mesmo β com o estado do
BTC no lugar do estado do mercado.

## Por que pode falhar

- Cooper et al. e Daniel & Moskowitz são mensais, transversais, em ações, lidos pelo resumo.
- "Estado" na literatura é medido em meses ou anos; a coorte tem 23 dias. Quantos estados de mercado couberam
  nela e quanto da variação da razão vem de **quais mercados** × **quando** não foi medido — a emenda da H-027
  publica a concentração por dia e por mercado como diagnóstico.

## Segunda opinião (Astra)

Revisada junto da síntese — ver [[KB-0179-o-que-um-resultado-da-c1-pode-e-nao-pode-dizer]] §Segunda opinião.

## Relacionados

[[KB-0179-o-que-um-resultado-da-c1-pode-e-nao-pode-dizer]] · [[KB-0176-momento-intradiario-condicionado-o-vizinho-mais-perto]] ·
[[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]] · [[KB-0034-btc-como-fator-e-o-regime-global-que-e-so-o-btc]] ·
[[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]] · [[KB-0174-o-filtro-de-tendencia-corta-queda-nao-acrescenta-alta]] ·
[[Fila de Hipoteses]]
