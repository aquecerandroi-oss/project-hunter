---
tags: [knowledge, nota, shadow-lab, regime, custos, multiplicidade, diagnostico, m3]
tema: onde cada versão do Lab ganha e onde perde — mercado, hora, dia da semana, regime do BTC e faixa de pedágio, com controle de multiplicidade
fonte: dado próprio da VPS — `signal_outcomes`, `agent_signals`, `strategy_versions`, `strategies`, `markets`, `market_regimes` (série horária `regime_hourly_v1`), lido em transações `repeatable read read only`
fonte_url: —
lido_em: 2026-09-08
as_of: 2026-09-09T02:30:00Z
read_at: 2026-09-09T02:51:00Z
evidencia: "4 consultas SQL somente leitura (`infra/scripts/sql/research/2026-09-09-t353-q0{0..3}-*.sql`) sobre 6 187 desfechos terminais + 86 bootstraps de blocos de dia com correção de Holm (reuso de `t342-blocos/blocos.py` como oráculo)"
hipotese_testavel: "sim — o portão de regime de §5 é pré-registrável: `momentum` não decide quando a hora fechada anterior do BTC é `trend=flat` e `vol=normal`"
astra: pendente
status: arquivada
owner: sexta-feira
updated: 2026-09-12
confiança: "?"
---

# Onde ganhamos e onde perdemos: 2 248 fatias, 86 julgáveis, 1 achado

> **Arquivada pela Sexta-feira em 2026-09-09 (T3.53)** a partir do rascunho do `quant-engineer`
> (`.claude/state/exp-drafts/KB-0079-onde-ganha-e-perde.md`). Não editei o conteúdo abaixo além do
> frontmatter e desta seção — nenhum número foi tocado. Nada foi commitado. Nada foi escrito na VPS.
> Proveniência de todo número: `.claude/state/notes-T3.53.md` (tabelas cruas com `read_at`) e
> `infra/scripts/sql/research/2026-09-09-t353-q0{0..3}-*.sql`.
> **Corte (`as_of`):** `agent_signals.emitted_at < 2026-09-09T02:30:00Z` = **2026-09-08 23:30 de
> Brasília**. **Leituras:** 2026-09-08 23:51, 2026-09-09 00:05 e 00:11 BRT (02:51, 03:05 e 03:11
> UTC). Nada aqui é dinheiro real (`ENABLE_LIVE_TRADING=false`).
> **Veredito em uma linha (o que muda de fato):** de 2 248 fatias, sobra **uma célula real** —
> `momentum v8` (replay) perde quando a hora fechada anterior do BTC é `SIDEWAYS`. `HIGH_VOLATILITY`
> é a única célula de regime com expectancy líquida positiva em todo o banco. `UNKNOWN` é artefato de
> aquecimento do classificador, não achado de regime. Hora do dia, dia da semana e mercado são
> **ruído** — nenhuma célula sobrevive a Holm nesses três eixos.
>
> **Nota de vocabulário controlado (lint):** o campo `confiança` do frontmatter aceita só
> `anedótico | backtest do autor | estudo revisado | replicado | ?` (`obsidian_lint_rules.py`). Esta
> KB é diagnóstico de dado próprio com dois níveis de confiança diferentes dentro da mesma nota —
> **alta** no diagnóstico de que quase tudo é ruído e no descarte dos dois artefatos (`UNKNOWN` e o
> par `up/high`), **baixa-média** no único achado que sobrou (36 decisões de replay em 8 dias, sem
> validação prospectiva possível hoje). Essa nuance não cabe no vocabulário de uma palavra e fica
> registrada aqui por extenso, como em [[KB-0076-por-que-perdemos-2026-09-08]] e
> [[KB-0078-o-radar-preve]].

## A pergunta

O Everton, 2026-09-08 às 23:20: *"onde cada versão ganha e onde perde?"*. A resposta preguiçosa é
uma tabela dinâmica de expectancy por hora, por mercado e por dia da semana — e ela **sempre**
encontra algo, porque com 2 248 fatias e um nível de 5 % o acaso entrega ~112 "achados". Esta nota
existe para dar a resposta que sobra depois de descontar o acaso.

## O que afirma

**Quase tudo o que parece padrão neste banco é ruído, e o pouco que sobrevive à multiplicidade
morre no controle de custo — menos um caso.**

- Foram enumeradas **2 248 células** (mercado × hora × dia da semana × regime × `trend`×`vol` ×
  faixa de pedágio, dentro de 16 populações com n ≥ 100).
- Só **86** podiam ser julgadas (n ≥ 30, ≥ 7 dias distintos, resto com n ≥ 30). As outras 2 162 são
  impressas e marcadas **"não julgável"** — não somem, mas também não gastam orçamento de teste.
- Das 86, **5 ganharam selo de Holm a 5 %**, e elas são **3 hipóteses distintas** (duas contam
  duas vezes porque a família `volume_anomaly` de replay **é** a `v2`).
- Das 3, **duas morrem** ao serem refeitas sobre o **R bruto** (sem pedágio). **Sobra uma.**

**O achado:** `momentum v8` (replay, 24 dias, 4 mercados) perde **0,3609 R por decisão** quando a
hora fechada anterior do BTC é `flat/normal` (rótulo `SIDEWAYS`) — IC 95 % [−0,654; −0,108],
p = 0,0032 — e perde **0,3556 R também no bruto**, com p idêntico. O pedágio dentro da célula é
0,135 R contra 0,129 R fora: **não é custo, é mercado.**

## Por que 2 162 fatias não podem ser julgadas

Porque o Lab tem **desfechos**, não **calendário**. O bloco de reamostragem é o **dia** (decisões do
mesmo dia, em quatro mercados correlacionados, compartilham choque — [[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]), e as maiores
populações do Lab são prospectivas com **1 a 3 dias**:

| população | n | dias de calendário | células julgáveis |
|---|---:|---:|---:|
| `volume_anomaly v1` prospectiva | 2 079 | **3** | 0 |
| `momentum v1` prospectiva | 929 | **3** | 0 |
| `volume_anomaly v2` prospectiva | 775 | **1** | 0 |
| `momentum v2/v3/v4` prospectivas | 359 / 340 / 133 | **1** | 0 |
| `momentum` família replay | 837 | 24 | 16 |
| `volume_anomaly v2` replay | 339 | 28 | 11 |
| `momentum v2/v6/v7/v8` replay | 248 / 195 / 183 / 181 | 24 | 11 cada |
| `mean_reversion` família replay | 146 | 10 | 4 |

**4 636 dos 6 187 desfechos estão em populações onde nenhuma pergunta desta nota tem resposta.**
Não é limitação do método: reamostrar três blocos não produz intervalo. Isto é a resposta honesta
à pergunta "por que não dá para dizer se a madrugada é melhor que a tarde": porque o Lab
prospectivo ainda não viu uma semana.

## O que é ruído, com números

- **Hora do dia** — em toda a nota apenas **duas** células de hora chegam a n ≥ 30 **e** 7 dias
  (`17h BRT / 20h UTC` na família `momentum` replay, Δ +0,5270 R, p 0,0408; `12h BRT / 15h UTC` na
  `volume_anomaly v2` replay, Δ +0,0064 R, p 0,94). Nenhuma sobrevive a Holm. **Nota de método:**
  hora de Brasília e hora UTC são **a mesma partição** deslocada de 3 h — testar as duas dobraria a
  multiplicidade sem trazer informação, então a hora é testada uma vez e rotulada nos dois relógios.
- **Dia da semana** — **nenhuma** célula julgável em **nenhuma** população: na janela de replay cada
  dia da semana aparece em 3 ou 4 datas distintas.
- **Mercado** — nenhum selo. O melhor é `DOGEUSDT` na família `momentum` replay (Δ +0,1942 R,
  p 0,0394 contra limiar de Holm de 0,0031). Nas coortes prospectivas, **1 mercado em 237** chega a
  n = 30.

## O que é artefato, com a prova do artefato

**`regime = UNKNOWN` na `volume_anomaly v2` de replay** é a célula com o menor p de toda a nota
(Δ −0,5387 R, p 0,0020) e **não é um achado de regime**:

| leitura | Δ | IC 95 % | p |
|---|---:|---|---:|
| R líquido | −0,5387 | [−0,809; −0,206] | 0,0020 |
| **R bruto** (sem pedágio) | **−0,0587** | [−0,342; +0,213] | **0,6919** |
| pedágio médio | +0,4801 (0,873 dentro vs 0,393 fora) | — | — |

E o calendário fecha o caso: os 9 dias de dentro (2026-08-09 a 08-17) têm **um** dia em comum com
os 20 de fora. `UNKNOWN` é o rótulo do **aquecimento do classificador horário** (PIPELINE §4b
item 5) — ou seja, o começo da janela de replay. Filtrar por `UNKNOWN` seria filtrar por data.
Vale o mesmo aviso para `up/high` (BTC subindo com vol alta), que perde 62 % do efeito no bruto
(+0,5582 → +0,2143 R) e cai para p 0,087: **direção plausível, achado não.**

## Regime: a tabela que a T3.52 precisa

Ordem idêntica nas duas famílias com replay, e ela persiste no bruto:

| família | coorte | regime | n | % da pop. | exp. líquida | exp. **bruta** | pedágio |
|---|---|---|---:|---:|---:|---:|---:|
| `momentum` | replay | HIGH_VOLATILITY | 282 | 33,7 % | **+0,1004** | +0,2624 | 0,161 |
| `momentum` | replay | BTC_BULL | 193 | 23,1 % | −0,1409 | +0,0805 | 0,220 |
| `momentum` | replay | SIDEWAYS | 165 | 19,7 % | **−0,3530** | −0,1290 | 0,224 |
| `momentum` | replay | BTC_BEAR | 108 | 12,9 % | −0,0631 | +0,1773 | 0,240 |
| `momentum` | replay | LOW_VOLATILITY | 49 | 5,9 % | −0,4683 | −0,2162 | 0,252 |
| `volume_anomaly` | replay | HIGH_VOLATILITY | 85 | 25,1 % | −0,2772 | +0,0906 | 0,368 |
| `volume_anomaly` | replay | SIDEWAYS | 30 | 8,8 % | **−0,7192** | −0,2949 | 0,425 |
| `momentum` | prospectiva | SIDEWAYS | 1 422 | **77,2 %** | −0,2108 | −0,0694 | 0,141 |
| `momentum` | prospectiva | LOW_VOLATILITY | 382 | 20,7 % | −0,1961 | −0,0398 | 0,156 |

**`HIGH_VOLATILITY` da `momentum` de replay é a única célula de regime com expectancy líquida
positiva e n ≥ 100 em todo o banco.** E a fatia `UNKNOWN`: **0 %** nas coortes prospectivas (o
classificador já está aquecido), 4,8 % na `momentum` de replay, **46 %** na `volume_anomaly` de
replay — sempre entre 2026-08-09 e 2026-08-17.

## O que fazer com isto

1. **Virar variante primeiro:** um portão de regime para `momentum` que **não decide** quando
   `trend = flat` **e** `vol = normal`, tratando `UNKNOWN` como "não operar" (hoje custa zero na
   coorte prospectiva). Insumo direto da T3.52.
2. **Pré-registrar antes de rodar:** a célula tem **36 decisões em 8 dias**. O experimento tem de
   declarar o critério de sucesso antes do replay, senão a T3.53 vira exatamente o que ela
   diagnosticou.
3. **Não mexer em hora, dia da semana nem mercado.** Não há evidência, e testá-los de novo sobre a
   mesma janela só gastaria o orçamento de multiplicidade.
4. **O que destrava tudo é calendário, não volume:** sete dias corridos de Lab prospectivo dariam a
   primeira família de testes prospectiva julgável desta série de notas.

**Fechamento (T3.52, 2026-09-09):** o portão de regime aqui recomendado foi **implementado** —
migração `0017` (`strategy_versions.eligibility_policy`), regra da hora anterior fechada, `UNKNOWN`/
ausente/stale tratados como inelegíveis com motivo. Ver [[EXP-0020-regime-gate]]: derivado e
ativado, **replay ainda pendente** — esta nota continua sendo o insumo, não a confirmação.

## O que continua valendo

**A perda ainda é o custo** ([[KB-0076-por-que-perdemos-2026-09-08]]). Em 6 de 6 famílias×coortes a faixa de pedágio
`> 0,20 R` é a pior, enquanto a expectancy **bruta** por faixa é plana ou até crescente
(`volume_anomaly` prospectiva: +0,0018 / +0,0085 / +0,0292 do menor ao maior pedágio). O mapa de
regime não substitui o piso de ATR% / teto de pedágio das T3.42 e T3.47 — ele é, no melhor caso,
um segundo filtro pequeno em cima daquele.

## Ressalvas que precisam sobreviver ao arquivamento

1. **"Ganhar" aqui é "perder menos".** Nenhuma célula com selo de Holm tem expectancy líquida
   positiva. A única célula "de ganho" com selo (`up/high` da `volume_anomaly v2`) perde 0,16 R por
   decisão.
2. **As sete populações de replay não são sete experimentos.** `momentum v2/v4/v6/v7/v8` de replay
   são **233 decisões distintas `(mercado, barra)` contadas 3,59 vezes** com geometrias diferentes;
   `mean_reversion` replay são **38 pares contados 3,84 vezes**. A repetição do sinal entre versões
   impressiona menos do que parece.
3. **A coorte prospectiva não confirma nem refuta o achado:** lá `flat/normal` dá Δ entre +0,005 e
   +0,046 R (sinal trocado), mas **77 % da população prospectiva já é `flat/normal`** — o contraste
   não existe por construção.
4. **Um dos cinco selos depende de uma casa decimal:** sem fundir `SIDEWAYS` com `flat/normal` (a
   mesma máscara de linhas, dois nomes), a família teria 12 testes e o `up/high` da
   `volume_anomaly v2` não passaria (p 0,0046 contra limiar 0,00417).
5. **A população se move:** 6 187 → 6 189 → 6 192 desfechos em 18 minutos com o `as_of` fixo na
   emissão. Todo bootstrap desta nota vem do snapshot de 6 187 (2026-09-08 23:51 BRT).

## Adendo 2026-09-11 (D-P23) — o eixo que faltava: **onde no tempo**, não só onde no mercado

> **Acrescentado pelo `quant-engineer` em 2026-09-11, 10:20 BRT (13:20 UTC).** Nada acima desta
> linha foi editado — nenhum número da leitura de 2026-09-09 foi tocado. Nada commitado, nada
> escrito na VPS (três consultas em `repeatable read read only`).
> **Proveniência:** `.claude/state/notes-D-P23.md`,
> `infra/scripts/sql/research/2026-09-11-dp23-q0{0,1,2}-*.sql`,
> `.claude/state/exp-drafts/dp23/{curva.py,test_curva.py,analise.py,dp23-curva.csv,saida-*.txt}`.
> **Coorte:** `replay:fa005985-0b55-4820-904c-8ada589e441c` (`mean_reversion v1`, 542 desfechos
> terminais, 16 mercados, 83 dias, EXP-0025) e `replay:92c8d080-6009-4a59-9868-31282b1bd493`
> (`mean_reversion_m5 v1`, 373, 14 mercados, 72 dias, EXP-0028). **Nenhum replay novo.**

Esta KB mapeou **onde** a família ganha e perde por mercado, hora, dia da semana, regime e faixa de
pedágio. Faltava um eixo que nenhuma daquelas células enxerga: **onde, ao longo do próprio período de
manutenção, o movimento bruto acontece.** O D-P23 mede isso como diagnóstico, sem régua causal.

**Método (a régua da Astra, `astra-review-plantao-20260911-0935.md` MUST-FIX 3).** Curva
`(close em t+h − open da barra de entrada) / ATR congelado da decisão`, long-only, **sem stop e sem
alvo**. A base é o **open da barra de entrada** e não `virtual_entry`, que já carrega 6 bps de
spread + slippage (`pricing.py:47`) — conferido: `virtual_entry = open × 1,0006` nas **915** decisões
das duas coortes, a menos de 1e-9. O ponto de `+h` é o `close` da vela que **fecha** em `entry_ts + h`
(`open_time = entry_ts + h − 1 min`), nunca a que abre nele. Velas de 1 min `is_final`. Ausência
sairia do denominador — **não houve nenhuma: 542/542 nos nove horizontes e 373/373 nos seis.**

**A curva da mãe (`mean_reversion v1`, 542 decisões, ATR de 15 m da própria decisão):**

| +min | 5 | 10 | 15 | 30 | 60 | **80** | 120 | 180 | **240** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| média (ATR) | +0,014 | +0,026 | +0,024 | +0,087 | +0,121 | **+0,204** | +0,259 | +0,341 | **+0,505** |
| mediana | 0,000 | 0,000 | 0,000 | +0,066 | +0,120 | +0,094 | +0,208 | +0,153 | +0,274 |
| p25 | −0,182 | −0,226 | −0,304 | −0,345 | −0,485 | −0,525 | −0,741 | −0,923 | −1,122 |
| p75 | +0,204 | +0,316 | +0,342 | +0,509 | +0,707 | +0,840 | +1,069 | +1,323 | +1,492 |
| % > 0 | 47,4 | 49,1 | 49,6 | 52,4 | 56,5 | 54,1 | 54,8 | 53,0 | 55,7 |

**O achado, e a ressalva que é o achado de verdade.** O Δ **pareado por decisão** (a mesma linha nos
dois horizontes; IC 95 % por blocos de dia, 20 000 reamostragens, semente 20260910, `blocos90.py`
reusado):

- **média Δ(240 − 80) = +0,3007 ATR, IC [+0,0071; +0,5820]** — exclui zero, por pouco;
- **mediana do mesmo Δ = +0,0598 ATR, IC [−0,1864; +0,3470]** — **não** exclui zero;
- **51,8 %** dos 542 pares têm Δ > 0.

Isto é: **há** acumulação adicional de movimento bruto entre +80 e +240 min nas entradas da mãe, e ela
é feita por uma **minoria de decisões com movimento tardio grande**, não por um deslocamento da
distribuição inteira. A distinção não é cosmética — "metade anda mais um pouco" pediria alongar o
horizonte de todas; "uma em vinte anda muito mais" pede um gatilho que diga *qual*, porque alongar
todas paga a cauda esquerda das outras dezenove.

**O freio que impede ler isto como expectancy.** A curva é MTM **sem barreiras**; a operação real não
espera. Duração real da mãe: média 85,3 min, **p50 61 min**, p75 127 min; **222 de 542 (41,0 %)** ainda
abertas depois dos 80 min e **só 45 (8,3 %)** chegando aos 240 (os `expired`). 281 saem por stop
(p50 43 min) e 216 por alvo (p50 68 min). **O trecho 80 → 240 min é contrafactual para nove de cada
dez decisões da mãe como ela está configurada hoje.**

**A irmã de 5 min, no horizonte dela** (373 decisões, ATR de 5 m): mesma forma — negativa nos
primeiros 15 min (−0,072 / −0,079 / −0,017 ATR) e positiva depois (+0,112 aos 30, +0,175 aos 60,
+0,226 aos 80). Duração real: p50 **18 min**, máximo 80. **Cuidado com a comparação fácil:** o ATR da
mãe é de 15 m e o da irmã é de 5 m (ATR% p50 0,5585 % contra 0,2714 %, EXP-0028), então "+0,20 ATR"
nas duas **não é o mesmo movimento**. Na única unidade comum (% do preço de entrada), aos 80 min as
entradas da mãe andaram **+0,223 %** e as da irmã **+0,119 %** — cerca de metade. Populações
diferentes, comparação descritiva, nenhum contraste pareado.

**Restrito aos mercados/dias em que a irmã operou** (só comparação; a irmã tocou 14 dos 16 mercados,
72 dias, 200 pares (mercado, dia)): o padrão se repete com Δ médio **maior** e mediana **menor** —
249 pares exatos dão média +0,5311 [+0,1417; +0,9225] e mediana +0,0758 [−0,1927; +0,5067]; os 473 do
recorte largo dão +0,3543 [+0,0385; +0,6517] e +0,0812 [−0,1816; +0,3853]. Os três recortes (cheio,
estrito, largo) estão todos reportados, **sem** correção de multiplicidade, porque nenhum deles é
teste de hipótese aqui.

**O que este adendo acrescenta à KB, em uma linha:** o mapa desta nota é de **células de contexto**
(mercado, hora, regime); este eixo é de **posição no tempo dentro da operação**, e nele o dado diz que
o movimento bruto da família continua chegando depois dos 80 min — **pela cauda** — enquanto a
configuração atual já fechou 6 de cada 10 operações antes dos 61 min. É insumo para um pré-registro,
**não** um pré-registro: o experimento que valeria a pena separa "deslocamento" de "cauda", e este
diagnóstico não os separa.

**O que este adendo explicitamente não diz.** Nada sobre a **causa** da diferença de desempenho entre
a mãe e a irmã de 5 min: a transposição mudou tendência (1 h → 15 min), ATR (15 → 5 min) e horizonte
(14 400 → 4 800 s) de uma vez (`mean_reversion_m5_v1.py:27`). A aposentadoria da
`mean_reversion_m5 v1` (2026-09-11T10:54:08Z, `successor=none`) continua de pé e **nada aqui a
reabre**. E nada aqui contradiz o "a perda ainda é o custo" da seção acima: a curva é **bruta**, e o
resultado líquido da mãe em 90 dias continua sendo `r_ex_funding` **−0,0910 R** (EXP-0025).

## Adendo 2026-09-12 (D-P24) — **de onde** vem aquele Δ: das saídas por **alvo**, e em minutos em que a posição já estava fechada

> **Acrescentado pelo `quant-engineer` em 2026-09-12, 02:50 BRT (05:50 UTC).** Nada acima desta linha
> foi editado — nenhum número do adendo D-P23 nem da leitura de 2026-09-09 foi tocado. Nada
> commitado, nada escrito na VPS (três consultas em `repeatable read read only`).
> **Proveniência:** `.claude/state/notes-D-P24.md`,
> `infra/scripts/sql/research/2026-09-12-dp24-q0{0,1,2}-*.sql`,
> `.claude/state/exp-drafts/dp24/{decomp.py,test_decomp.py,analise.py,dp24-decisoes.csv,dp24-caminho.csv,saida-*.txt}`.
> **Coorte:** a **mesma** do adendo acima — `replay:fa005985-0b55-4820-904c-8ada589e441c`
> (`mean_reversion v1`, 542 desfechos terminais, 16 mercados, 83 dias, EXP-0025). **Nenhum replay
> novo.** **Régua:** `astra-review-plantao-20260911-1030.md`, MUST-FIX 1–3.

O adendo D-P23 deixou uma pergunta aberta: o Δ(240 − 80) de **+0,3007 ATR** é dinheiro que a
estratégia **poderia ter guardado** ou dinheiro que ela **nunca poderia tocar**? A decomposição pelo
**motivo real de saída** responde, e a resposta muda a leitura.

**O número agregado foi reproduzido dígito a dígito por outro caminho de dados** (caminho minuto a
minuto em vez de nove endpoints, motivo de saída lido da coluna `signal_outcomes.result` em vez do
envelope `meta.progress.result`, com **0** discordâncias em 542): média **+0,3007 ATR**
IC [+0,0071; +0,5820], mediana +0,0598 IC [−0,1864; +0,3470]. Cobertura **542/542** com os 240 minutos
`is_final` completos, **0** minutos faltando.

**A tabela (contribuição = `Σ Δ_i do grupo / 542`; as três recompõem o total, erro 5,55e-17):**

| motivo da saída | n | dias | média Δ (ATR) | mediana | **contribuição** | IC 95 % da contribuição | % do total |
|---|---:|---:|---:|---:|---:|---|---:|
| **`target`** | 216 | 65 | +0,6899 | +0,4803 | **+0,2749** | **[+0,0902; +0,4476]** | **91,4 %** |
| `stop` | 281 | 73 | +0,0279 | −0,2448 | +0,0145 | [−0,1457; +0,1791] | 4,8 % |
| `time-stop` | 45 | 26 | +0,1356 | +0,2410 | +0,0113 | [−0,0047; +0,0274] | 3,8 % |
| `context-lost` / `other` | 0 | 0 | — | — | +0,0000 | — | 0 % |
| **todos** | 542 | 83 | **+0,3007** | +0,0598 | +0,3007 | [+0,0071; +0,5820] | 100 % |

Em **% do preço de entrada** a ordem é a mesma e as participações mudam (`target` **82,4 %**, `stop`
13,9 %, `time-stop` 3,7 %) porque o ATR é um denominador **por decisão** e o `time-stop` é o grupo de
ATR mais largo (ATR% p50 1,1134 % contra 0,8308 % e 0,8193 %). **Qualquer citação desta participação
tem de carregar a unidade.**

**O mesmo Δ partido pelo instante da saída real** (`Δ_i = [ret(c) − ret(80)] + [ret(240) − ret(c)]`,
`c = clamp(m_saida, 80, 240)`; telescopa por construção, erro máximo 1,78e-15):

| motivo | contribuição **dentro** da posição | IC 95 % | contribuição **depois** da saída | IC 95 % |
|---|---:|---|---:|---|
| `stop` | **−0,1345** | [−0,1721; −0,0992] | **+0,1490** | [+0,0078; +0,2942] |
| `target` | +0,1840 | [+0,1395; +0,2302] | +0,0910 | [−0,0707; +0,2377] |
| `time-stop` | +0,0113 | [−0,0047; +0,0274] | +0,0000 | (vazio por construção) |
| **todos** | **+0,0607** | [−0,0128; +0,1366] | **+0,2399** | [−0,0136; +0,4768] |

**Três coisas que esta tabela acrescenta à KB:**

1. **79,8 % do Δ agregado acumula em minutos em que a posição já estava fechada** (+0,2399 de
   +0,3007). O trecho dentro da posição soma +0,0607 e o IC dele **não** exclui zero. O "dinheiro
   extra depois dos 80 min" é, na maior parte, dinheiro que a configuração de hoje **não podia
   tocar** — não é lucro deixado na mesa por falta de paciência.
2. **O `stop` some no total por cancelamento, não por imobilidade:** enquanto as 83 posições stopadas
   depois dos 80 min ainda estavam abertas, o preço **caía** (−0,1345, IC excluindo zero pelo lado
   negativo); depois de stopadas, subia (+0,1490, IC excluindo zero pelo lado positivo). Uma coluna
   única esconderia isso.
3. **O grupo em que um horizonte mais longo poderia importar (`time-stop`) responde por 3,8 %** — e
   por aritmética de n (45 de 542), não por ausência de movimento: ele tem a **maior** mediana
   (+0,2410) e o maior `%>0` (62,2 %) dos três. O contraste `time-stop − stop`, pareado por dia, é
   **+0,1077 ATR IC [−0,2452; +0,4734]**: os dois grupos **não** se distinguem. E tirando as saídas
   por alvo, os 326 restantes dão média **+0,0428 ATR** — o achado do adendo anterior desaparece.

**Correção de uma frase do adendo D-P23, com o número que faltava.** Lá está escrito que a acumulação
"é feita por uma **minoria de decisões com movimento tardio grande**, não por um deslocamento da
distribuição inteira". Isso era **leitura a confirmar**, não achado (a Astra: média com IC acima de
zero e mediana com IC cruzando zero não demonstram concentração). Medido agora: o **decil superior**
(55 decisões) contribui **+0,4917**, o **decil inferior −0,3036**, e os **432 do meio +0,1125 —
37,4 % do agregado**. Então **não** é "poucas explicam tudo" nem "a distribuição inteira se deslocou":
são **as duas caudas grandes, com a direita maior**, e o sinal do agregado é a diferença entre elas —
a parte menos estável de qualquer amostra. A frase do adendo anterior fica onde está, por registro; a
leitura que vale é esta.

**Fragilidade declarada:** o limite inferior do IC do agregado é **+0,0071**, e tirar **um único dia**
(20/08/2026) move a média de +0,3007 para **+0,2342** (tirar um mercado, no extremo, para +0,3617).
Nenhum dia ou mercado carrega o achado, mas "exclui zero" é aqui uma propriedade **frágil**. A parte
robusta é a **decomposição** (o IC da contribuição do `target` tem limite inferior +0,0902), não a
significância do agregado.

**O que este adendo explicitamente não diz** — e é a armadilha que a
[[KB-0054-a-cauda-direita-e-o-alvo-fixo-que-a-corta]] já registrou: os +0,0910 ATR que o grupo
`target` acumula **depois** da própria saída **não** são dinheiro que uma variante sem alvo
capturaria. Ela herdaria outra trajetória de desfechos — parte das 216 operações que hoje fecham no
alvo viraria stop ou expiração —, e esse líquido é **experimento**, não leitura. Nada aqui propõe
mudar a `mean_reversion v1` viva, nada aqui reabre a `mean_reversion_m5 v1` aposentada, e o motivo de
saída só é conhecido **depois** da operação: ele não é, e não pode virar, seletor de entrada. O
resultado realizado da versão continua sendo `r_ex_funding` **−0,0910 R** em 90 dias (EXP-0025).

**Excursões (auxiliares, e são de FECHAMENTOS — OHLC não revela ordem intrabar).** Medianas em ATR:
o `stop` tem MAE de closes **−1,8100** na janela de 240 min **e** na janela depois da saída (o preço
seguiu caindo depois do stop, na mediana); o `target` tem MAE de closes **+0,3442** depois da saída
(na mediana o preço nunca voltou à entrada depois do alvo); para o `time-stop` a janela depois é
**vazia** (`m_saida = 240` em todas as 45).

## Proveniência

| arquivo | o que produz |
|---|---|
| `infra/scripts/sql/research/2026-09-09-t353-q00-catalogo.sql` | catálogo por versão×coorte, famílias, cobertura de regime |
| `infra/scripts/sql/research/2026-09-09-t353-q01-populacao-csv.sql` | a população, uma linha por desfecho, em CSV pelo stdout |
| `infra/scripts/sql/research/2026-09-09-t353-q02-regime-e-celulas.sql` | regime por família, fatia `UNKNOWN`, hora, dia da semana, pedágio, tamanho de célula |
| `infra/scripts/sql/research/2026-09-09-t353-q03-juncao-de-regime.sql` | robustez da junção de regime (3,54 % de divergência entre as duas convenções) |
| `.claude/state/exp-drafts/t353/celulas.py` + `test_celulas.py` | bootstrap de blocos de dia por célula, Holm, deduplicação; 11 testes com valor esperado (+ 12 pré-existentes dos módulos reusados) |
| `.claude/state/exp-drafts/t353/mapa.py` | as tabelas A–E da nota |
| `.claude/state/exp-drafts/t353/celulas.csv` | as 2 248 células com n, dias, Δ, IC 95 %, p, selo, julgabilidade |
| `.claude/state/notes-T3.53.md` | as tabelas cruas e as seis CONCERNs |
| `infra/scripts/sql/research/2026-09-11-dp23-q00-catalogo.sql` | **(adendo D-P23)** catálogo das duas coortes: n, `entry_ts`, ATR, direção, horizonte, vela de entrada, recortes de comparação |
| `infra/scripts/sql/research/2026-09-11-dp23-q01-curva-mtm.sql` | **(adendo D-P23)** a curva pós-entrada em CSV, uma linha por (decisão, horizonte) — 7 116 linhas |
| `infra/scripts/sql/research/2026-09-11-dp23-q02-duracao-real.sql` | **(adendo D-P23)** duração real de cada operação — o que torna o trecho 80→240 min contrafactual |
| `.claude/state/exp-drafts/dp23/curva.py` + `test_curva.py` | **(adendo D-P23)** curva, resumo por horizonte, Δ pareado por decisão, IC da mediana por blocos de dia, escolha do endpoint; **22 testes** com valor esperado à mão, 5 deles de anti-antecipação |
| `.claude/state/exp-drafts/dp23/analise.py` + `saida-analise.txt` | **(adendo D-P23)** as seis seções da leitura e a saída verbatim |
| `.claude/state/notes-D-P23.md` | **(adendo D-P23)** a nota inteira, com as oito assunções numéricas |
| `infra/scripts/sql/research/2026-09-12-dp24-q00-motivos.sql` | **(adendo D-P24)** catálogo dos motivos reais de saída; `result` **contra** o envelope `meta.progress.result` (0 discordâncias em 542); `m_saida` por grupo; cobertura dos 240 minutos |
| `infra/scripts/sql/research/2026-09-12-dp24-q01-decisoes.sql` | **(adendo D-P24)** uma linha por decisão (542): motivo, `m_saida`, ATR, ATR%, os dois pontos do Δ nas duas unidades, os fechamentos extremos das quatro janelas |
| `infra/scripts/sql/research/2026-09-12-dp24-q02-caminho.sql` | **(adendo D-P24)** o caminho minuto a minuto — 130 080 linhas (542 × 240), o que põe a aritmética no módulo testado |
| `.claude/state/exp-drafts/dp24/decomp.py` + `test_decomp.py` | **(adendo D-P24)** motivo canônico, Δ pareado, partição dentro/depois da saída, contribuição e decis, bootstrap de blocos de dia **conjunto**, excursões de closes; **41 testes** com valor esperado à mão, 5 de anti-antecipação |
| `.claude/state/exp-drafts/dp24/analise.py` + `saida-analise.txt` | **(adendo D-P24)** as sete seções da leitura e a saída verbatim |
| `.claude/state/notes-D-P24.md` | **(adendo D-P24)** a nota inteira, com os quatro CONCERNs e as dez assunções numéricas |

**Sem antecipação:** o relógio de toda a nota é `meta->'entry_plan'->>'source_bar_close'` (a última
vela fechada que a estratégia leu), e a linha de regime usada é a última com
`end_time <= source_bar_close` — a hora inteira que **já fechou** antes da barra, nunca a hora em
curso. A convenção alternativa do PIPELINE §4b (a janela que contém a barra) diverge em 3,54 % das
linhas e não muda conclusão nenhuma.

## Relacionadas

[[11-KNOWLEDGE/Index|Index]] · [[Strategy Backlog]] · [[Registro de Tentativas]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] ·
[[KB-0076-por-que-perdemos-2026-09-08]] · [[KB-0078-o-radar-preve]] ·
[[EXP-0020-regime-gate]] ·
[[EXP-0025-mean-reversion-90-dias]] · [[EXP-0028-mean-reversion-5-min]] ·
[[KB-0082-reversao-de-15-minutos-o-sinal-e-o-fluxo]]
