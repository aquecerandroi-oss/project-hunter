---
tags: [knowledge, nota, execucao, impacto, microestrutura]
tema: Execução e microestrutura do preenchimento
fonte: Donier & Bonart, "A Million Metaorder Analysis of Market Impact on the Bitcoin Market" (arXiv 1412.4503; Market Microstructure and Liquidity, 2015); Emilio Said, "Market Impact: Empirical Evidence, Theory and Practice" (arXiv 2205.07385)
fonte_url: https://arxiv.org/pdf/1412.4503
lido_em: 2026-09-06
evidencia: estudo revisado — **o PDF não abriu para mim; a Astra o abriu e conferiu equação, seção e tabela** (registrado)
hipotese_testavel: sim
astra: reescrita após a revisão dela (a tese original estava errada)
---

# A lei da raiz quadrada, e o que ela realmente diz sobre o nosso caso

## O que afirma

Ao executar um volume total `Q` num mercado que negocia `V`, o preço se desloca em média
proporcionalmente a **√(Q/V)**, não a `Q`. Donier & Bonart reconstruíram **mais de um milhão de
metaordens** no mercado Bitcoin/USD e confirmaram a lei ao longo de **quatro ordens de grandeza** de
tamanho, num mercado que na época quase não tinha arbitragem estatística nem formação de mercado
profissional.

**Esta nota começou com uma tese errada e o registro do erro vale mais que a tese.** Eu escrevi que a
lei "é sobre metaordens, e nós somos uma ordem única, logo ela não se aplica". A Astra abriu o PDF
que a minha ferramenta não conseguiu ler e mostrou que **61% das metaordens da amostra têm uma única
ordem-filha** (tabela I). Ordem única **não** é o critério que separa o nosso caso do da literatura.

O que realmente separa são três coisas, e todas são de **normalização e de objeto medido**:

1. **A lei é escrita com volume e volatilidade DIÁRIOS** (equação 1). Trocar `V` por volume de dois
   minutos mantendo volatilidade diária infla o impacto artificialmente. Se alguém for usar a lei
   aqui, tem de usar os dois na mesma escala.
2. **A seção 4.1 mede impacto de PICO**, separadamente do permanente. Impacto de pico é o topo da
   excursão durante e logo após a execução; permanente é o que sobra. Eu tinha chamado o número de
   "deslocamento permanente médio" — errado.
3. **A seção 6 encontra dependência da velocidade** de execução depois de controlar pelo fluxo. Ou
   seja: nem mesmo dentro do artigo o impacto depende **só** do volume total.

E fica de pé a distinção que motivou a nota, agora enunciada com o escopo certo: a lei descreve
**como o mercado reage** ao nosso volume; o custo que o Lab precisa cobrar é **o preço que pagamos
para atravessar o book** ([[KB-0036-o-tamanho-que-a-sombra-nunca-declara]]). São duas quantidades
diferentes que por acaso têm a mesma unidade. A segunda nós conseguimos medir; a primeira, não.

## Onde foi mostrado

Bitcoin/USD, mais de um milhão de metaordens. A confirmação da lei aparece também em ações, câmbio,
futuros, crédito e opções, em datasets heterogêneos, e a chegada da negociação de alta frequência não
a alterou.

**Duas limitações de fonte, declaradas:** (a) o PDF do arXiv 1412.4503 voltou binário ilegível pela
minha ferramenta em duas tentativas — **os fatos sobre equação 1, seção 4.1, tabela I e seção 6 vêm
da leitura da Astra**, não da minha; nenhum expoente ajustado nem prefator entra em conta nossa;
(b) eu tinha atribuído o arXiv 2205.07385 a "Bouchaud et al." — é de **Emilio Said**. Corrigido.

## Como mediríamos aqui

Não mediríamos, e essa é a resposta honesta. Para aplicar a lei precisaríamos de `Q` (não existe,
[[KB-0036-o-tamanho-que-a-sombra-nunca-declara]]), de `V` diário do próprio mercado no dia (temos,
com o denominador problemático da [[KB-0018-volume-relatado-e-o-denominador-que-usamos]]) e de `σ`
diária na mesma escala (não persistimos volatilidade diária por mercado; o que temos é o estimador
horário da [[KB-0028-o-nosso-estimador-de-volatilidade-e-o-mais-ineficiente]]). Faltam dois dos três.

**Retirei a tabela que comparava a raiz quadrada com o custo de book.** A Astra pediu o corte e ela
tem razão: colocar um número calculado com `Y` e `σ` chutados ao lado de uma mediana medida convida
a usar a proximidade visual como validação, por mais ressalvas que se escreva embaixo. As duas
quantidades medem coisas diferentes e nem a coincidência de escala está demonstrada.

## Hipótese testável no Lab

**`EXEC-E` — teto de capacidade, e a aritmética dele estava errada na primeira versão.** Eu tinha
escrito "orçamento de 15% de 1 R para o custo total, logo ≈ 7,6 bps de ida e volta, logo ≈ 3,8 bps
por lado". A Astra mostrou o furo: **as taxas assumidas sozinhas já custam 8 bps de ida e volta**
(4 por lado, cobradas fora dos preços em `pricing.py:79`). Um orçamento de 7,65 bps para o custo
**total** já está estourado antes de olhar o book.

Reformulado com o que a medição suporta:

- O orçamento tem de ser declarado **sobre o custo de book apenas**, com as taxas e o funding
  contabilizados à parte, ou não é um orçamento — é uma conta impossível.
- Mesmo assim, a conclusão "1.000 USDT já estoura" **não vem das tabelas**: a mediana de 1.000 no
  universo é **3,467 bps** por lado, e fora do top 20 é **3,714**. Ambas abaixo de 3,825.
- E qualquer mediana desse tipo é **condicional à cobertura**: no top 20, 20 mil tem mediana de
  2,190 bps mas **5 de 20 livros não cobrem** esse tamanho. Um teto calculado só sobre os livros que
  couberam é um teto sobre a amostra sobrevivente.

Portanto o `EXEC-E` fica assim, e só assim: **para cada sinal, publicar o custo de book por tamanho
numa grade fixa junto com a fração de livros que não cobrem aquele tamanho**, e deixar o orçamento
(quanto de 1 R o Everton aceita gastar em execução) como decisão dele, não como parâmetro que eu
escolho retroativamente. Sem a coluna de cobertura, o número é seleção, não capacidade.

**Refutação:** se, na população dos sinais, a fração sem cobertura for alta para todo tamanho
relevante, o `depth20` é instrumento insuficiente e a resposta é coletar mais profundidade, não
publicar um teto.

## Por que pode falhar

- **Eu não li o artigo.** Os fatos vêm da leitura da Astra. Nenhum número da lei entra em conta nossa.
- **Normalização é onde a lei quebra na mão de quem a aplica de qualquer jeito.** Volume e
  volatilidade têm de estar na mesma escala temporal.
- **Impacto de pico ≠ impacto permanente ≠ preço pago.** Três coisas, uma unidade.
- **"Ordem única" não isenta ninguém.** Foi o meu erro original; 61% da amostra do artigo é de
  ordem única.
- **O nosso `V` é volume relatado de exchange**, com o problema da
  [[KB-0018-volume-relatado-e-o-denominador-que-usamos]].
- **Teto calculado num instante não é teto.** Os livros são de um segundo.

## Segunda opinião (Astra)

**Esta nota foi reescrita por causa da revisão dela, e o registro é o seguinte.** Ela abriu o PDF que
eu não consegui abrir e derrubou a tese central: 61% das metaordens do artigo são de ordem única
(tabela I), a equação 1 normaliza por volume e volatilidade **diários**, a seção 4.1 mede impacto de
**pico** e não permanente, e a seção 6 encontra dependência da velocidade. Também corrigiu a autoria
do arXiv 2205.07385 (Emilio Said, não Bouchaud et al.) e a aritmética do teto de capacidade — 15% de
51 bps são 7,65 bps totais, já consumidos pelos 8 bps de taxa. Pediu, e eu aceitei, o **corte
integral** da tabela que comparava raiz quadrada com custo de book, e das frases "coincidirem é
esperado" e "se desfaz em segundos", nenhuma das duas demonstrada. Nice-to-have aceito: escrever
"quatro ordens de grandeza" em vez de "quatro décadas", que em português sugere tempo.

Divergência: nenhuma que sobreviva. A minha divergência anterior — manter a tabela — caiu junto com
a tese que ela sustentava.

## Relacionados

[[Strategy Backlog]] · [[KB-0036-o-tamanho-que-a-sombra-nunca-declara]] ·
[[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]] ·
[[KB-0018-volume-relatado-e-o-denominador-que-usamos]] ·
[[KB-0028-o-nosso-estimador-de-volatilidade-e-o-mais-ineficiente]] ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] · [[Risk Engine]]
