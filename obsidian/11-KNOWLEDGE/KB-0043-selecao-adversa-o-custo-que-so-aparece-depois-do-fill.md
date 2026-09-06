---
tags: [knowledge, nota, execucao, microestrutura, selecao-adversa]
tema: Execução e microestrutura do preenchimento
fonte: "Public Trader Identity: Adverse Selection and Return Predictability" (arXiv 2608.04373v3) — Hyperliquid, julho de 2026
fonte_url: https://arxiv.org/html/2608.04373v3
lido_em: 2026-09-06
evidencia: preprint com método declarado, **mas de outra venue** (DEX com casamento por bloco), não da Binance
hipotese_testavel: sim
astra: concorda após correções (recusou a primeira versão)
---

# Seleção adversa: o custo que só aparece depois do fill

## O que afirma

Existe uma quantidade que **nenhum preço de fill mostra**: o que o mercado faz logo **depois** que a
ordem executou. A medida padrão chama-se *markout* — a variação assinada do ponto médio entre o
instante do fill e um horizonte curto depois dele.

**A perspectiva importa e eu a tinha invertido.** Um markout positivo *na direção do agressor*
significa que o preço andou a favor de quem atravessou: isso é **adverso para a contraparte
passiva**, o formador de mercado que estava do outro lado. É o custo de seleção adversa **dele**, não
nosso. E os autores explicitamente **não** equiparam "toxicidade" a informação privada.

O preprint mede isso em perpétuos de cripto com dados de nível 4 (mensagem a mensagem), julho de
2026, dez mercados, 14,3 milhões de ordens agressoras, 84,3 bilhões de dólares em notional de taker.
Números, **da janela de validação de 11 a 20 de julho, em BTC/ETH/SOL** (o universo geral do artigo é
maior): spread cotado médio de **0,20 bps** no BTC, **0,62** no ETH, **0,26** no SOL; o markout de
dez segundos das ordens agressoras vai de **0,27 bps** no decil menos tóxico de carteiras a
**2,20 bps** no mais tóxico, chegando a **3,11 bps** no ventil superior depois de controlar por
mercado, hora, tamanho, volatilidade e spread; tamanho mediano de ordem de **1.201 dólares** no decil
superior contra **59** no inferior.

**Ressalva de venue: o estudo é do Hyperliquid**, um livro com prioridade preço-tempo executado em
ordem de consenso por blocos — não é a Binance, e "por bloco" também não quer dizer leilão uniforme.
Os spreads de 0,20 bps não são comparáveis aos 2,30 bps que eu medi, a estrutura de latência é outra,
e a noção de "carteira identificável" só existe lá. **Transportam-se o conceito e o método como
candidatos a pesquisa** — não os números, e nem a ordem de grandeza relativa.

## Onde foi mostrado

Hyperliquid, julho de 2026, BTC/ETH/SOL na análise principal e mais sete mercados. Horizonte de
markout: dez segundos, do mid do último bloco estritamente anterior ao fill até o mid dez segundos
depois. O artigo não decompõe impacto por notional de taker dentro dos decis — publica o tamanho
mediano por decil, que é outra coisa.

## Como mediríamos aqui

**Nós não medimos nada disso, e é uma lacuna de categoria, não de precisão.** O Shadow Lab avalia
`R_net` a partir do preço de entrada, dos toques e da saída. Um fill "barato" no toque e um fill
"caro" no toque entram na conta pela mesma porta; o que o mercado fez nos dez segundos seguintes ao
`entry_bar_open` não aparece em lugar nenhum — está diluído dentro do resultado de quatro horas.

**Eu tinha escrito aqui um parágrafo inteiro que a Astra derrubou** e que vale registrar como erro:
que as duas estratégias, por comprarem depois de alta e de pico de volume, estariam "do lado
informado", teriam como contraparte um formador de mercado e enfrentariam spread efetivo maior que o
cotado. Nada disso está demonstrado. Comprar depois de uma alta **não** prova que somos informados,
**não** identifica a contraparte, e **não** implica spread efetivo maior. O que sobra é a pergunta
descritiva, que é legítima: *para onde o preço vai logo depois das nossas entradas?*

O que temos para medir sem coletar nada novo: velas de 1 minuto. Com elas dá para construir um
**retorno entre aberturas** — não um markout, que compara mids — numa janela de um minuto, seis
vezes maior que a do artigo. É grosseiro, tem outro nome e mede outra coisa; mas aponta na mesma
**direção** de pergunta.

## Hipótese testável no Lab

**`EXEC-H` — retorno entre aberturas depois da entrada planejada. Descritivo, e não é markout.**
Sobre as entradas já colhidas:

- **medida primária:** `(open[entry_bar + 1min] − open[entry_bar]) / open[entry_bar] × 10000`, em
  bps, assinado, **contra o `open` bruto**;
- **como sensibilidade contábil, não como evidência adicional:** o mesmo contra `P_entry`. Motivo,
  medido pela Astra: num mercado **perfeitamente parado**, essa segunda versão já dá **−5,9964 bps**,
  puro efeito do acréscimo sintético de entrada. Publicá-la como se fosse sinal seria publicar a
  própria hipótese de custo.

Publicar **todas** as entradas com horizonte observado, **incluindo as que encerraram antes de um
minuto** — nelas o retorno posterior é trajetória de mercado, não PnL da posição. Média, mediana,
quartis e cobertura, por estratégia e por decil de liquidez. Cortes por `result` (target/stop)
aparecem como **descrição secundária**, com o aviso de que condicionar ao resultado futuro seleciona
trajetórias.

**Dois critérios que eu tinha escrito e que saem:**

- *"Negativo nos stops significa comprar o topo."* Não significa: entradas **aleatórias** num passeio
  sem tendência também mostram retorno inicial negativo entre as que depois batem no stop.
- *"Mediana próxima de zero encerra a questão."* Não encerra: uma queda de 5 bps nos primeiros dez
  segundos com recuperação até o minuto dá retorno de um minuto igual a zero. E ausência de
  significância não demonstra equivalência a zero.

**O que o `EXEC-H` de fato entrega:** a distribuição do retorno de um minuto após a entrada. Nada
mais. Se ela for materialmente negativa, a próxima pergunta é sobre **timing do sinal**
([[KB-0009-o-efeito-do-quarto-de-hora]]), não sobre custo — e não se soma aos 6 bps.

## Por que pode falhar

- **A fonte é de outra venue.** Hyperliquid, não Binance. Nenhum número dela entra em conta nossa.
- **O que proponho não é markout.** Markout compara **mids**; o `EXEC-H` compara **aberturas de
  vela**, que são negócios, num intervalo que também não são exatamente 60 s entre os dois negócios.
  É um retorno descritivo com o nome certo.
- **Um minuto não é dez segundos.** Seis vezes a janela, com todo o movimento de fundo junto.
- **Causa não sai daqui.** Retorno negativo pode ser preço pago, timing do sinal, notícia pública ou
  ruído. Uma queda após a nossa compra **não** demonstra que o vendedor sabia mais.
- **A sombra não tem contraparte.** A literatura de seleção adversa fala de quem estava do outro
  lado; nós temos um preço sintético.
- **Amostra pequena.** 192 entradas e um dia, abaixo do limiar editorial de 100 outcomes **e**
  30 dias. Isso é limiar editorial, **não** cálculo de poder — não afirmo, sem conta, que o resultado
  será inconclusivo.

## Segunda opinião (Astra)

Leu o preprint original — coisa que eu não fiz — e confirmou os números citados, com a precisão de
que 0,27/2,20 bps e 59/1.201 dólares são da **janela de validação de 11 a 20 de julho** em
BTC/ETH/SOL, não do universo inteiro. **Recusou a primeira versão em dois pontos**, aceitos:

1. **Perspectiva invertida.** Markout positivo na direção do agressor é adverso para a **contraparte
   passiva**, e os autores não equiparam toxicidade a informação privada. E o meu parágrafo sobre
   "estamos do lado informado, a contraparte é formador de mercado, o spread efetivo é maior" não
   tem nada demonstrado — saiu inteiro.
2. **O `EXEC-H` não era markout e o critério estava errado.** Reformulado como retorno descritivo
   entre aberturas, com a medida primária contra o `open` bruto, porque contra `P_entry` um mercado
   parado já produz **−5,9964 bps** (conta dela) — seria publicar a hipótese de custo como se fosse
   achado. Cortados os dois critérios: "negativo nos stops significa comprar o topo" (condicionar ao
   resultado futuro seleciona trajetórias) e "mediana zero encerra" (queda de 5 bps em 10 s com
   recuperação até o minuto dá zero).

Nice-to-have aceito: não afirmar poder insuficiente "quase certamente" sem cálculo — limiar
editorial e poder estatístico são coisas diferentes.

**O que fica registrado como acordo:** o retorno posterior ao fill **não** se soma aos 6 bps. Ele já
está contido no resultado da operação, via `P_exit` e `R_net`. Cobrá-lo de novo seria contar duas
vezes, exatamente como com o deslocamento referência→entrada da
[[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]].

## Relacionados

[[Strategy Backlog]] · [[KB-0013-vpin-e-a-disputa-sobre-toxicidade]] ·
[[KB-0012-ofi-nao-e-o-nosso-orderbook-imbalance]] ·
[[KB-0009-o-efeito-do-quarto-de-hora]] ·
[[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]] ·
[[KB-0036-o-tamanho-que-a-sombra-nunca-declara]] · [[EXP-0001-momentum-v1]] ·
[[EXP-0002-volume-anomaly-v1]]
