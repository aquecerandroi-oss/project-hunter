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
updated: 2026-09-09
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

**Sem antecipação:** o relógio de toda a nota é `meta->'entry_plan'->>'source_bar_close'` (a última
vela fechada que a estratégia leu), e a linha de regime usada é a última com
`end_time <= source_bar_close` — a hora inteira que **já fechou** antes da barra, nunca a hora em
curso. A convenção alternativa do PIPELINE §4b (a janela que contém a barra) diverge em 3,54 % das
linhas e não muda conclusão nenhuma.

## Relacionadas

[[11-KNOWLEDGE/Index|Index]] · [[Strategy Backlog]] · [[Registro de Tentativas]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] ·
[[KB-0076-por-que-perdemos-2026-09-08]] · [[KB-0078-o-radar-preve]] ·
[[EXP-0020-regime-gate]]
