---
tags: [knowledge, indice]
updated: 2026-09-06
status: em construção
---

# Conhecimento — índice

Base de conhecimento **externo** do projeto: estratégias de trade, análise técnica, microestrutura de mercado, perpétuos de cripto (funding, open interest, liquidações), gestão de risco e estatística de backtest. Curada pela Sexta-feira com a Astra revisando cada hipótese. Regras em `.claude/agents/sexta-feira.md` (seção "Knowledge acquisition").

Cada nota é uma síntese própria (nunca cópia), com fonte, data, qualidade da evidência e uma **hipótese testável no Lab**. O que vira candidato de estratégia entra em [[Strategy Backlog]]; toda variante que for rodada entra antes em [[Registro de Tentativas]]; o que vira experimento aparece em [[Experiments Index]].

## Temas
| Tema | Notas | Status |
|---|---|---|
| Momentum e rompimentos | KB-0001, KB-0002, KB-0003, KB-0004, KB-0006 | primeira rodada feita (2026-09-06) |
| Volume e fluxo de ordens | KB-0009 | iniciado |
| Perpétuos: funding, OI, liquidações | KB-0008 | iniciado |
| Análise técnica clássica (o que tem evidência e o que não tem) | KB-0003 | iniciado |
| Regime de mercado e volatilidade | KB-0007 | iniciado |
| Gestão de risco e sizing | KB-0005 | iniciado |
| Estatística de backtest (overfitting, look-ahead, custos) | KB-0010 | iniciado |

## Notas
_(uma linha por nota: `[[Título]] — fonte curta — qualidade da evidência — hipótese sim/não)_

| Nota | Tema | Fonte curta | Evidência | Hipótese |
|---|---|---|---|---|
| [[KB-0001-momentum-academico-e-o-que-nao-se-transfere]] | momentum | Jegadeesh & Titman 1993; Moskowitz, Ooi & Pedersen 2012 | estudo revisado | sim — gate de tendência `return_4h > 0` |
| [[KB-0002-momentum-e-reversao-em-cripto]] | momentum em cripto | Dobrynskaya (WP); Wen, Bouri, Xu & Zhao 2022 | estudo revisado / working paper | sim — filtro de impulso recente excessivo |
| [[KB-0003-rompimento-de-canal-e-data-snooping]] | rompimento | Lukac/Brorsen/Irwin 1988; Park & Irwin 2007; Hudson & Urquhart 2021 | revisão de literatura | sim — família 10/20/40 publicada inteira |
| [[KB-0004-proximidade-da-maxima-e-confirmacao-por-volume]] | rompimento | George & Hwang 2004 | estudo revisado | sim — `distance_from_24h_high ≥ −0,005`, após medir redundância |
| [[KB-0005-stops-quando-eles-param-perdas]] | risco / saída | Kaminski & Lo 2014 | estudo revisado | sim — braços `STOP-A/B/C` |
| [[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]] | saída (candidata #1) | síntese própria sobre EXP-0001 + Kaminski & Lo | dado próprio, inconclusivo por limiar | sim — braços `INV-A/B/C/E` |
| [[KB-0007-atr-e-escala-por-volatilidade]] | volatilidade | Wilder 1978; Harvey et al. 2018 | estudo revisado / texto de praticante | sim — análise estratificada por decil de ATR% |
| [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] | perpétuos / custos | documentação da Binance + aritmética própria | documentação + cálculo verificado | sim — piso de custo `atr_pct_min = 0,0089` |
| [[KB-0009-o-efeito-do-quarto-de-hora]] | microestrutura | arXiv 2607.09426 | preprint | sim — H1 diagnóstico de timing, H2 atraso de execução |
| [[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] | estatística de backtest | Bailey, Borwein, López de Prado & Zhu | estudo revisado | não — é regra de protocolo |

## O que esta primeira rodada mudou de fato

Três correções factuais sobre o **nosso** código, achadas ao confrontar a literatura com a
implementação, e que valem mais que qualquer citação: `return_24h` **não existe** (o teto é
`return_4h`); `rvol` usa **mediana**, não média; e a entrada da `momentum_v1` **não** cai na janela
de 10 segundos do quarto de hora — cai no minuto seguinte. As três estão nas notas correspondentes.

## Relacionados

[[Strategy Backlog]] · [[Registro de Tentativas]] · [[Experiments Index]] ·
[[EXP-0001-momentum-v1]] · [[Strategy Performance]] · [[Features]] · [[00-HOME]]
