---
tags: [knowledge, leitura, decaimento, pos-publicacao, regime, sobrevivencia, cauda-pesada, cripto, hipotese]
tema: "modos de falha conhecidos de efeitos de tendência/momentum — decaimento fora da amostra e depois da publicação, dependência de regime (2014–2018 × 2018–2019 × 2020+), sobrevivência e caudas pesadas que tornam média e variância pouco informativas"
fonte: "McLean & Pontiff, 'Does Academic Research Destroy Stock Return Predictability?' (J. Finance 71(1), 2016 — só o resumo); Deprez & Frömmel (IREF 2024 — versão de autor lida, seção de subperíodos); Hudson & Urquhart 2021 (resumo e tabela 9 já conferidos em KB-0167); Grobys, Kolari, Sandretto, Shahzad & Äijö 2025 (já em KB-0164); Anghel, 'A reality check on trading rule performance in the cryptocurrency market' (Finance Research Letters 39, 2021 — só o resumo, RePEc); Grobys & Shahzad, 'Cryptocurrency Momentum: Is It an Illusion?' (Int. J. Finance & Economics 31(2), 2026 — só o resumo, RePEc)"
fonte_url: https://doi.org/10.1111/jofi.12365 · https://biblio.ugent.be/publication/01HY3C3S169G1N6QNYR55NZMFB · https://link.springer.com/article/10.1007/s10479-019-03357-1 · https://ideas.repec.org/a/eee/finlet/v39y2021ics1544612320304414.html · https://ideas.repec.org/a/wly/ijfiec/v31y2026i2p2180-2193.html
lido_em: 2026-10-01
evidencia: "estudos revisados — um lido na íntegra em versão de autor (Deprez & Frömmel), números já conferidos em KB-0164/KB-0167 (Hudson & Urquhart; Grobys et al. 2025), três só pelo resumo (McLean & Pontiff; Anghel; Grobys & Shahzad); nenhuma medição nossa"
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

# KB-0177 — Decaimento e regime: o que a literatura de cripto mostra

> **Leitura curada, sem medição nossa.** Quatro modos de falha aparecem de forma consistente: (1) o retorno de
> um preditor publicado cai **fora da amostra** e cai mais **depois da publicação** (McLean & Pontiff, em ações);
> (2) em cripto, as regras técnicas que funcionaram até 2017 **não** funcionaram no BTC em 2018 e, em 2018–2019,
> no máximo perderam menos; (3) o momentum de cripto depois de 2020 é frágil e dominado por **caudas**; (4)
> testar só as moedas que sobreviveram ou que têm histórico longo infla o resultado. A H-027 tem versões
> pequenas de (3) e (4).

## O que afirma (claim × evidência)

1. **McLean & Pontiff 2016 (resumo).** 97 preditores do corte transversal de ações: retorno 26 % menor fora da
   amostra e 58 % menor depois da publicação; a queda fora da amostra é um limite superior para o efeito de
   mineração de dados; o que é maior dentro da amostra cai mais depois. Mensal, ações.
2. **Hudson & Urquhart 2021 (KB-0167).** A melhor regra de dentro da amostra das duas séries de BTC teve retorno
   anualizado negativo no 1.º semestre de 2018 (LTC, XRP e ETH ainda positivos).
3. **Deprez & Frömmel 2024 (lido).** Subperíodos de 2 anos de 2014 a 2021: nas quedas as carteiras de regras
   superam comprar e segurar (sem significância depois da correção); em 2018–2019 a maioria só perdeu menos; nas
   altas, no máximo empatam; as classes vencedoras mudam de período a período
   ([[KB-0174-o-filtro-de-tendencia-corta-queda-nao-acrescenta-alta]]).
4. **Anghel 2021 (resumo).** Com controle de mineração (reality check e teste em etapas) e fricções, retornos em
   excesso positivos e significativos são raros, qualquer que seja a frequência, o tipo de posição ou o nível de
   significância; o que aparece é prêmio de risco de mercado.
5. **Grobys et al. 2025 (KB-0164).** Momentum transversal das 30 maiores: positivo até jul/2020 (só a 10 %),
   negativo e não significativo depois; uma semana com uma moeda do lado vendido que subiu ~1.400 % custou −255 %.
6. **Grobys & Shahzad 2026 (resumo).** As variâncias realizadas de seis estratégias de momentum em cripto seguem
   leis de potência; média e variância populacionais podem não ser definidas, e medidas de desempenho baseadas
   em variância deixam de ser informativas.

A magnitude de McLean & Pontiff (ações, mensal) **não** calibra esta população; a lição é só a direção: um
efeito publicado tende a ser menor depois.

## Onde foi mostrado — e onde a H-027 se encaixa

| modo de falha | evidência | versão dele na H-027 ([[Fila de Hipoteses]]) |
|---|---|---|
| decaimento fora da amostra | McLean & Pontiff; BTC 2018 | a C1 vem de literatura até 2018; esperar menos que o publicado |
| regime | 2014–15/2018–19 × 2016–17/2020–21 (Deprez & Frömmel) | coorte de **23 dias** de set/2026: poucos dias para representar regimes (quantos couberam não foi medido) |
| sobrevivência / seleção por dado | Hudson & Urquhart e Grobys et al. com moedas que já eram grandes | só os **16 perpétuos** com 20 dias completos de vela de 1 min entram (a seleção é por data de início da coleta, não por desfecho — mas são mercados que a coleta já seguia em 30/08) |
| caudas | Grobys & Shahzad; a semana de −255 % de Grobys et al. | R_net limitado pelo stop e pelo alvo de 1,5 ATR, mas o atraso e a derrapagem podem gerar perdas além de −1 R; o OLS da H-027 é sensível a pontos extremos |
| reuso das mesmas unidades | — | quase todas as unidades já estavam no R83 (H-023); o registro da H-027 reconhece |

## Como mediríamos aqui

Sem medida nova. Para ler o resultado da H-027 sem cair nestes modos de falha (descritivos, **sem** mudar o
rótulo): β sem cada dia e sem cada mercado (a emenda da H-027 já os publica); β com R_net aparado em ±3 R —
que trata extremos do desfecho, **não** alavancagem nas covariáveis; a fatia pós-R83 que o próprio registro já
prevê.

## Por que pode falhar (esta leitura)

- McLean & Pontiff é ações, transversal, mensal; os números de decaimento não se transferem, só a direção.
- Anghel e Grobys & Shahzad só pelo resumo: não sei amostra nem regras.

## Segunda opinião (Astra)

Revisada junto da síntese — ver [[KB-0179-o-que-um-resultado-da-c1-pode-e-nao-pode-dizer]] §Segunda opinião.

## Relacionados

[[KB-0179-o-que-um-resultado-da-c1-pode-e-nao-pode-dizer]] · [[KB-0174-o-filtro-de-tendencia-corta-queda-nao-acrescenta-alta]] ·
[[KB-0173-tendencia-diaria-em-cripto-o-tamanho-publicado]] · [[KB-0164-momentum-semanal-em-cripto-grande]] ·
[[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]] · [[KB-0163-perto-da-maxima-de-24h-nao-separa-os-sinais-do-lab]] ·
[[KB-0178-data-snooping-e-poucos-clusters-o-que-vale-para-a-h-027]] · [[Fila de Hipoteses]]
