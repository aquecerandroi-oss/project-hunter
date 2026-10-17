---
tags: [knowledge, leitura, momentum, intradiario, condicionamento, volatilidade, volume, cripto, acoes, hipotese]
tema: "o vizinho mais perto da C1 na literatura — momentum intradiário (a primeira meia hora prevê a última) e em que condições ele é mais forte: dias de volatilidade e volume altos, crise e recessão, primeira janela positiva; nenhum estudo achado condiciona um sinal intradiário à tendência diária por média móvel"
fonte: "Gao, Han, Li & Zhou, 'Market intraday momentum' (JFE 129(2), 2018 — só o resumo, RePEc); Li, Sakkas & Urquhart, 'Intraday time series momentum: global evidence and links to market characteristics' (J. Financial Markets 57, 2022 — versão aceita CC BY-NC-ND no repositório de Reading, lida nas seções 1–3); Shen, Urquhart & Wang, 'Bitcoin intraday time series momentum' (Financial Review 57(2), 2022 — versão aceita, seções 3.5–3.7 relidas); Borgards, 'Dynamic time series momentum of cryptocurrencies' (NAJEF 57, 2021 — só o resumo, EconPapers)"
fonte_url: https://ideas.repec.org/a/eee/jfinec/v129y2018i2p394-414.html · https://centaur.reading.ac.uk/95566/ · https://centaur.reading.ac.uk/100181/ · https://econpapers.repec.org/RePEc:eee:ecofin:v:57:y:2021:i:c:s1062940821000590
lido_em: 2026-10-01
evidencia: "estudos revisados — dois em versão aceita lidos nas seções relevantes (Li et al.; Shen et al.), dois só pelo resumo (Gao et al.; Borgards); nenhuma medição nossa"
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

# KB-0176 — Momento intradiário condicionado: o vizinho mais perto

> **Leitura curada, sem medição nossa.** A pergunta da C1 — um sinal de continuação de curto prazo funciona
> melhor quando o diário está em alta? — **não tem estudo direto** nos textos que achei (já dito em
> [[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]] para o "acordo entre tempos gráficos"). O vizinho mais
> perto é o **momentum intradiário**: nos estudos revisados ele é mais forte em dias de **volatilidade e volume
> altos**, em **crise e recessão**, e quando a primeira janela do dia é **positiva**. Nenhuma dessas condições é
> "diário acima da média de 20 dias"; duas delas (crise, recessão) apontam para o lado oposto.

## O que afirma (claim × evidência)

1. **Gao et al. 2018 (resumo).** No ETF do S&P 500, 1993–2013, o retorno da primeira meia hora (desde o fecho
   anterior) prevê o da última meia hora; a previsibilidade é **mais forte** em dias de volatilidade alta, de
   volume alto, em recessões e em dias de notícia macroeconômica importante; aparece em outros dez ETFs.
2. **Li, Sakkas & Urquhart 2022 (versão aceita, lida).** 16 mercados desenvolvidos, 2005–2017: 12 de 16 com
   previsão significativa da primeira para a última meia hora; regressão empilhada com coeficiente 2,86 (t 7,53).
   **Condicionamento:** durante a crise financeira (dez/2007–jun/2009) 12 de 16 mercados têm inclinação maior; na
   regressão empilhada, 3,71 na crise contra 2,09 fora dela, R² ajustado 1,18 % contra 0,63 %; em recessão contra
   expansão, inclinação média 4,05 contra 2,52 e R² 1,72 % contra 0,81 % (12 de 16 maiores na recessão).
3. **Shen, Urquhart & Wang 2022 (versão aceita, relida).** BTC, sessões definidas por volume: a previsão é maior
   quando a primeira janela tem mais volume ou volatilidade; o R² das três regressões é 1,89 %, 2,78 % e 3,19 %
   quando a primeira meia hora é **positiva**, contra 0,11 %, 0,88 % e 0,89 % quando é **negativa** (coeficiente
   significativo nos dois casos). O valor econômico da estratégia comprada/vendida aparece nos anos de **queda**
   do BTC; custo de equilíbrio de 3–10 bps por operação (KB-0167).
4. **Borgards 2021 (resumo).** Em 20 criptos e no mercado de ações americano, os períodos de momentum depois das
   fases de formação são maiores e mais longos nas criptos, em todas as frequências (diária e intradiárias); a
   estratégia supera comprar e segurar, e só nas criptos com risco-retorno melhor. Método e custo não verificados.

## Onde foi mostrado

| estudo | mercado | horizonte | condição em que o efeito é maior | custo |
|---|---|---|---|---|
| Gao et al. | ETF S&P 500 + 10 ETFs, 1993–2013 | meia hora | volatilidade, volume, recessão, notícia | não verificado |
| Li et al. | 16 índices, 2005–2017 | meia hora | crise, recessão | não nesta parte |
| Shen et al. | BTC, 5 corretoras, até 2020 | meia hora | volume/volatilidade da 1.ª janela; 1.ª janela positiva; valor econômico em anos de queda | equilíbrio 3–10 bps |
| Borgards | 20 criptos + ações EUA | diário e intradiário | — | não verificado |

## O que isso prevê para a C1

- O que melhora o momentum intradiário nos estudos é **atividade** (volatilidade, volume) e **estresse** — a
  H-027 já controla ATR% e `return_4h`, os parentes mais próximos dessas condições no nosso envelope. O que
  sobrar para `razao_mm20d` depois disso é, pela literatura, **de sinal não previsto**.
- O resultado de Shen et al. "mais forte quando a primeira janela é positiva" é sobre o **sinal do próprio
  gatilho**, não sobre o diário; não apoia a C1 diretamente.
- **Sem estudo direto, a prioridade de C1 vem da força da tendência diária sozinha** (KB-0167, KB-0173), não de
  evidência de condicionamento.

## Como mediríamos aqui

Nada novo além da H-027 ([[Fila de Hipoteses]]). Um descritivo possível, sem rótulo: β de `razao_mm20d`
separado por tercil de ATR%. Ele **não identifica mecanismo** — um efeito concentrado em ATR% alto pode ser
interação tendência × volatilidade, ou tercis compostos de dias e mercados diferentes (correção da Astra,
[[KB-0179-o-que-um-resultado-da-c1-pode-e-nao-pode-dizer]]).

## Por que pode falhar

- Ações e ETFs têm abertura e fechamento; cripto não — Shen et al. resolvem isso com sessões por volume, e o
  nosso Lab não tem esse conceito.
- Comprado/vendido em meia hora ≠ só comprado com stop e alvo de 1,5 ATR em 15 min.
- Gao et al. e Borgards só pelo resumo.

## Segunda opinião (Astra)

Revisada junto da síntese — ver [[KB-0179-o-que-um-resultado-da-c1-pode-e-nao-pode-dizer]] §Segunda opinião.

## Relacionados

[[KB-0179-o-que-um-resultado-da-c1-pode-e-nao-pode-dizer]] · [[KB-0175-estado-de-mercado-condiciona-momentum-mas-em-que-direcao]] ·
[[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]] · [[KB-0163-perto-da-maxima-de-24h-nao-separa-os-sinais-do-lab]] ·
[[KB-0007-atr-e-escala-por-volatilidade]] · [[Fila de Hipoteses]]

## Mercado tradicional (17/10/2026)

Esta nota virou a base da **H-038** (momento intradiário de mercado no WIN, B3), rascunho de pré-registro em
`docs/plans/MERCADO-TRADICIONAL.md` §1, decisão em [[2026-10-17-pausar-memes-e-cripto-ir-para-mercado-tradicional]]. Três coisas distintas, que não se confundem (Astra,
[[Dialogos/mercado-tradicional|diálogo mercado-tradicional]]): (1) o **efeito externo** desta nota (SPY e 12 de 16
mercados desenvolvidos; o Brasil não está na amostra); (2) a **hipótese local** no Ibovespa, sem replicação conhecida;
(3) o **modelo executável** no WIN, com stop, custo condicionado e fonte de dado limitada. A escala de ~2,5 bp por
operação usada no poder é suposição, não teto medido.

**Congelada (17/10/2026 17:56:30Z):** [[Fila de Hipoteses#H-038 — Momento intradiário de mercado no WIN, coorte prospectiva (o sinal da 1.ª meia hora do Ibovespa prevê o WIN entre C−30 e C?)|H-038]] (prospectiva, consulta final em 825 pregões de calendário, futilidade em 125) e H-038r (retrospectiva no histórico do MT5, primário 80 % + holdout 20 %), revisadas pela Astra em [[Revisoes-Astra/H-038-prereg|H-038-prereg]]. A regra virou o módulo puro `packages/indicators/hunter_indicators/b3/intraday_momentum.py` (r1 = `ibov_r1_open30` v1) e o cartão do dia `infra/scripts/b3_signal_card.py`. Nenhum dado intradiário do Ibovespa foi lido até o congelamento.
