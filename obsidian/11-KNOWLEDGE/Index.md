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
| Volume e fluxo de ordens | KB-0009, KB-0011, KB-0012, KB-0013, KB-0014, KB-0015, KB-0016, KB-0018 | **segunda rodada feita (2026-09-06)** |
| Perpétuos: funding, OI, liquidações | KB-0008, KB-0017 | ampliado na segunda rodada |
| Análise técnica clássica (o que tem evidência e o que não tem) | KB-0003 | iniciado |
| Regime de mercado e volatilidade | KB-0007, KB-0016 | iniciado |
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
| [[KB-0011-volume-magnitude-e-a-ponte-para-direcao]] | volume | Karpoff 1987; Gervais, Kaniel & Mingelgrin 2001 | estudo revisado (associação **contemporânea**) | sim — H-KB0011, retorno de preço a horizonte fixo com grupo `not_triggered` |
| [[KB-0012-ofi-nao-e-o-nosso-orderbook-imbalance]] | microestrutura / book | Cont, Kukanov & Stoikov 2014; Cont, Cucuringu & Zhang 2023 | estudo revisado | sim, **só diagnóstica** — a candidata de filtro foi retirada na própria nota |
| [[KB-0013-vpin-e-a-disputa-sobre-toxicidade]] | fluxo / risco | Easley-LdP-O'Hara 2012; Andersen & Bondarenko 2013–2014; réplica | **disputada** (4 textos) | sim — diagnóstico do denominador de 288 barras |
| [[KB-0014-taker-buy-volume-o-que-temos-medido]] | volume / fluxo | documentação de klines da Binance + medição própria na VPS | documentação + SQL colado | sim — filtro de desequilíbrio agressor, **após observar sem decidir** |
| [[KB-0015-volume-relativo-e-o-pico-como-exaustao]] | volume / falso positivo | Gervais et al. (versão de trabalho 1998) + dado próprio | versão de trabalho + dado inconclusivo | sim — H-KB0015a associação; teto `volume_mult_max` exploratório |
| [[KB-0016-quando-o-fluxo-importa-dependencia-de-estado]] | fluxo / regime | arXiv 2607.09230; arXiv 2602.00776 | preprint (dois) | sim — requisito de proveniência + auditoria de spread |
| [[KB-0017-liquidacoes-o-fluxo-forcado-que-observamos-por-amostragem]] | perpétuos / liquidações | documentação `forceOrder` da Binance; arXiv 2607.27070 | documentação + preprint + SQL próprio | sim — auditoria de observabilidade da série já coletada |
| [[KB-0018-volume-relatado-e-o-denominador-que-usamos]] | volume / qualidade do dado | Cong, Li, Tang & Yang (arXiv 2021 / MS 2023); Bitwise 2019 | estudo revisado (lido com página) | sim — auditoria de cobertura no instante da decisão |

## O que a primeira rodada mudou de fato

Três correções factuais sobre o **nosso** código, achadas ao confrontar a literatura com a
implementação, e que valem mais que qualquer citação: `return_24h` **não existe** (o teto é
`return_4h`); `rvol` usa **mediana**, não média; e a entrada da `momentum_v1` **não** cai na janela
de 10 segundos do quarto de hora — cai no minuto seguinte. As três estão nas notas correspondentes.

## O que a segunda rodada mudou de fato

O tema era volume e fluxo de ordens, e o saldo mais útil de novo **não** foram as citações — foram
seis fatos sobre o nosso próprio sistema, todos verificados com comando ou com linha de código:

1. **`taker_buy_volume` tem cobertura de 100%** no banco da VPS (519.422 velas de 1 min, 222
   mercados, zero linhas inconsistentes) — fecha a pendência que a [[KB-0009-o-efeito-do-quarto-de-hora]]
   tinha deixado aberta. O campo **chega** ao `StrategyContext` e é **descartado no `_fold`** da
   agregação (`aggregate.py:40,77`): faltam um campo num dataclass e uma linha de soma, não coleta.
2. **Nós já coletamos liquidações.** 8421 eventos em 197 mercados na VPS
   (`ingest.py:62` → `persist_rows.py:217`). Eu tinha escrito uma nota inteira supondo que não.
3. **E o parser delas tem um defeito de semântica:** usa `q × p` (quantidade **original** × preço da
   ordem) em vez do executado (`z`, `ap`), então a soma de `notional` **não é** limite inferior do
   executado. Vai para [[Open Bugs]].
4. **`covered_until` deixou de ser o bloqueio** de `buy_pressure_5m` / `trade_velocity_1m`: o
   publicador e o consumidor existem na árvore (`market-worker/coverage.py:153`,
   `scanner-worker/context.py:96`). A disponibilidade operacional continua **não medida**.
5. **O ranking do mercado no instante da decisão NÃO está no envelope do sinal.** Isso torna
   inexecutável qualquer estratificação retrospectiva por faixa de liquidez, e vira requisito de
   proveniência para coleta futura.
6. **`volume_ratio_5m` e `relative_volume_5m` diferem por 288 (24 h) contra 23 (115 min)** e pelo
   alinhamento — não por "contígua contra disjunta", como eu tinha escrito. E a *baseline* sazonal da
   T2.3 é uma terceira camada, não um terceiro denominador.

E um saldo de método: **a Astra derrubou duas entregas inteiras** desta rodada (o filtro de book da
KB-0012 e a estratificação retrospectiva da KB-0016) e reformulou a hipótese central de outras três.
Todas as correções estão na seção "Segunda opinião (Astra)" de cada nota.

## Relacionados

[[Strategy Backlog]] · [[Registro de Tentativas]] · [[Experiments Index]] ·
[[EXP-0001-momentum-v1]] · [[EXP-0002-volume-anomaly-v1]] · [[Strategy Performance]] ·
[[Features]] · [[00-HOME]]
