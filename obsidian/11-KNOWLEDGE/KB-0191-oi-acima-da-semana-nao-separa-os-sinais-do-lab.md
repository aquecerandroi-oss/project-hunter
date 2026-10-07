---
tags: [knowledge, cripto, open-interest, perpetuos, lab, momentum, segunda-frente, hipotese, pesquisa, retrospectiva]
tema: "nos sinais da momentum do Lab (coorte prospectiva já resolvida, 15 perpétuos, 12/09–04/10/2026), o OI acima ou abaixo da própria mediana semanal não mostrou efeito no R líquido (o tamanho previsto não foi excluído) depois de controlar distância da mínima de 24 h, ATR% e retorno de 4 h: β +0,003 R por desvio robusto, IC por dia [−0,047; +0,059] — o tamanho previsto (+0,05) não é excluído no bootstrap de dia, então NÃO CONFIRMA (não REFUTA); o grupo 'menos lotado' perde −0,25 R (H-033, análise retrospectiva)"
fonte: R90 (`.claude/state/r90/`) — H-033 da Fila de Hipóteses, linha `open_interest em nível` de Próximas Hipóteses (a) e item 14 do Strategy Backlog
fonte_url: —
lido_em: 2026-10-07
evidencia: "medição própria, retrospectiva pré-especificada — 869 unidades (estratégia × mercado × barra) da momentum v3 em 23 dias e 15 mercados, R_net do Lab (custos assumidos + funding); OI reconstruído de open_interest_history com folga de 15 min calibrada no outbox; OLS conjunto com bootstrap por dia e por mercado (10 000); 31 + 3 testes sintéticos (principal e réplica), fumaça com efeito injetado e dois nulos; lista elegível congelada com sha256 antes de ler desfechos; réplica computacional independente (OI cru, equações normais) igual a 7e-15 por sinal"
hipotese_testavel: sim
astra: "pré-registro: 5 must-fix aceitos numa emenda datada (05:15:31Z) antes de qualquer desfecho; resultado: reproduziu tudo, concorda com os três rótulos; 5 must-fix (1 de redação, 4 de instrumento sem efeito nos números) aceitos e corrigidos com teste e saída numericamente idêntica"
status: vivo
owner: sexta-feira
updated: 2026-10-07
confiança: "?"
tipo: pesquisa
hipotese: H-033
variavel: "oi_rel7d = ln(OI corrente) − mediana(ln OI) na janela de 7 d que termina na leitura de maior bucket ≤ obs − 15 min (open_interest_history, OI em contratos); direção low (OI acima da semana = 'lotado' = pior); secundária oi_vol = ln(OI × preço ÷ volume de cotação de 24 h)"
populacao: "coorte prospectiva do Lab, long, perpétuos Binance, terminais com R_net, emitidos 06/09–06/10/2026; momentum 869 unidades em 23 dias e 15 mercados (todas momentum v3); volume_anomaly 0 unidades (emitiu só antes de existir uma semana de OI)"
efeito: "momentum β de −oi_rel7d +0,0026 R por desvio robusto; nível oi_rel7d<0 −0,250 R × ≥0 −0,194 R; volume_anomaly limite de dado; H-033 global nao_confirma (retrospectiva)"
ic: "IC dia [−0,0470, +0,0592]; IC mercado [−0,0381, +0,0350]"
veredito: nao_confirma
proximo_passo: "nenhuma regra, variante ou braço; não trocar folga, janela de 7 d, cortes, covariáveis ou unidade nestes dados; OI em nível só volta com população nova (outra estratégia de continuação com semana de OI, ou sinais emitidos depois de 07/10) ou com o OI gravado com o próprio instante da leitura"
classe_de_perda: —
mercado: cripto
---

# KB-0191 — OI acima da própria semana não separa os sinais da `momentum` do Lab

> **H-033 `NÃO CONFIRMA` (global) · `momentum` `NÃO CONFIRMA` · `volume_anomaly` `LIMITE DE DADO`.**
> **Análise retrospectiva pré-especificada** sobre a coorte prospectiva do Lab já resolvida (773 dos 869 sinais já
> tinham desfecho lido no R86, sem OI) — **não** é validação independente.
>
> Nos 869 sinais (unidades) da `momentum v3` em 15 perpétuos, de 12/09 a 04/10/2026, estar com o open interest abaixo da
> própria mediana semanal ("menos lotado") **não** melhorou o R líquido do Lab, depois de controlar distância da mínima
> de 24 h, ATR% e retorno de 4 h: **β = +0,0026 R por desvio robusto**, IC 95 % por dia **[−0,0470; +0,0592]** e por
> mercado **[−0,0381; +0,0350]**. O ganho previsto (+0,05 R) **fica dentro** do IC por dia (por 0,009) → o protocolo
> não refuta o tamanho; também não há nada a confirmar: o grupo "menos lotado" perde **−0,250 R** (IC por dia
> [−0,335; −0,176]) e o "mais lotado" **−0,194 R**.
>
> Pré-registro e emenda em [[Fila de Hipoteses]] § H-033 · revisões [[H-033-prereg]] e [[H-033-resultado]] · código e
> saídas em `.claude/state/r90/` (`h033.txt`, sha256 `29ac13b1…`; `replica/out_replica.txt`, `out_compare.txt`;
> `smoke_synth.txt`; `freeze.txt`).

## O que afirma

1. **No recorte medido, o OI relativo à semana não há evidência de que acrescente (o IC por dia vai de −0,047 a +0,059 R por desvio) aos sinais de rompimento de 15 min.** A estimativa
   é praticamente zero (+0,003 R por desvio), estável nas duas metades (+0,002 / +0,003), nas folgas de 30 e 60 min
   (+0,002 / +0,005), sem a guarda das velas tardias (−0,000) e com `r_ex_funding` (+0,003).
2. **"Menos lotado" não deixa a `momentum` lucrativa.** O grupo favorável perde −0,25 R com o intervalo inteiro abaixo
   de zero — perde até um pouco **mais** que o grupo "lotado" (−0,19 R). Não há filtro aqui que transforme o Lab em
   lucro, e a leitura folclórica ("lotado de comprados rende menos") não aparece.
3. **A secundária (OI relativo ao volume de 24 h) também não:** β −0,012 (sinal contrário ao previsto), IC dia
   [−0,062; +0,037], mercado [−0,080; +0,032]; os dois grupos de `oi_vol` perdem (−0,21 R em 808 unidades × −0,34 R em
   61). Não é pista ([[H-033-resultado]]).

## Onde foi mostrado

| estratégia | n (dias, mercados) | oi_rel7d < 0 / ≥ 0 | β de −oi_rel7d (R/desvio) | IC dia | IC mercado | Holm | nível oi_rel7d < 0 | rótulo |
|---|---|---|---|---|---|---|---|---|
| **momentum** | 869 (23, 15) | 399 / 470 | **+0,0026** | [−0,0470; +0,0592] | [−0,0381; +0,0350] | 0,972 | −0,250 R | **NÃO CONFIRMA** |
| volume_anomaly | 0 | — | — | — | — | (p = 1) | — | **LIMITE DE DADO** |

**Cláusula a cláusula (momentum).** Dado: 869 ≥ 150, 23 ≥ 15 dias, 399 ≥ 30 no grupo menor → ok. Instrumento: valores
finitos, posto completo nos cinco cortes e nas metades, MAD > 0 nas metades, 0 % de réplicas inválidas → ok.
**REFUTA exige IC superior < +0,05 nos dois bootstraps:** mercado +0,0350 sim, **dia +0,0592 não** → não refuta.
Confirmação: β < MRE, IC inferior < 0 nos dois, Holm 0,972, nível favorável < 0, patamar ausente (cortes
oi_rel7d < +0,04/+0,02/0/−0,02/−0,04: β −0,006/−0,025/−0,046/−0,019/+0,087, sequência positiva 1) → falha. Metades
e folgas 30/60 positivas, sem efeito no rótulo. **Global:** `volume_anomaly` em limite → **NÃO CONFIRMA**.

**Modelo conjunto (z robusto):** intercepto −0,238 · −oi_rel7d +0,003 · `distance_from_24h_low` +0,029 [−0,034; +0,090]
· ATR% +0,019 [−0,055; +0,127] · retorno 4 h −0,001 [−0,065; +0,048]. Secundária 1[oi_rel7d < 0] ajustada −0,046
[−0,160; +0,085]. Diagnósticos: número de condição 4,40; 93 % da variação de x não é explicada pelos controles
(redundância medida às cegas: |Spearman| ≤ 0,257); maior mercado 8,2 %, maior dia 9,3 %; β sem cada mercado de
−0,005 a +0,013, sem cada dia de −0,012 a +0,017.

**Robustez pré-registrada (não decide; IC por blocos de calendário, 2 000 réplicas):** FE mercado −0,006 [−0,035;
+0,037] · **FE dia −0,005 [−0,040; +0,0501]** · FE mercado+dia −0,013 [−0,050; +0,038] · blocos de 3 d [−0,028;
**+0,0512**] · 5 d [−0,024; +0,035] · 7 d [−0,023; +0,017]. **FE dia e blocos de 3 d passam (de pouco) de +0,05**: pela
regra da emenda, nem uma generalização de "refuta o tamanho" seria publicável — e o protocolo nem refutou.

**Sensibilidades (não decidem):** pré-R86 773 unidades β −0,006 [−0,060; +0,055]; pós-R86 96 unidades em 4 dias
(abaixo do piso; média −0,39 R); leitura corrente provada pós-commit 252 unidades em 9 dias e janela inteira provada 28
unidades em 2 dias (as duas abaixo do piso; médias −0,26 e −0,29 R). `mean_reversion` (descritivo, reversão): 264
unidades, β +0,030 [−0,128; +0,151], nível oi_rel7d < 0 +0,013 R (IC por dia, calculado pela Astra, [−0,206; +0,228])
× ≥ 0 −0,128 — compatível com ruído; não justifica, sozinho, um bloco novo.

## Como mediríamos aqui (e o que o dado ensinou)

- **O OI durável não tem o instante da leitura.** `open_interest_history.ts` é o piso de 5 min do **início** da rodada
  de leitura (o coletor lê os mercados um a um por REST), não o instante em que o número foi lido
  ([[Market Collector]]; `hunter_strategy_worker/derivatives.py` já recusa usá-lo ao vivo por isso). Pesquisa que use
  essa tabela precisa de folga: no outbox (26/09 → 07/10) a maior distância bucket → inserção foi **325 s** (p99 diário
  13–155 s), e o R90 usou 15 min. **Antes de 26/09 não existe prova**: o resultado é condicionado à folga.
- **Prova pós-commit existe, mas curta.** O outbox (`outbox_events`, retido ~11 dias) guarda o instante real da leitura
  (`payload.ts`) e o `dispatched_at` do relay — que só lê linha comitada, então `dispatched_at ≤ obs` prova
  disponibilidade; `created_at` é o `now()` da transação e **não** prova. Com 7 dias de janela, só 28 unidades tiveram a
  janela inteira provada.
- **Sem antecipação:** leitura corrente = maior bucket ≤ obs − 15 min; janela (B − 7 d, B]; qualquer amostra da janela
  com inserção no outbox depois de obs recusa o sinal (nenhuma recusada). Testes: leituras dentro da folga e futuras
  mudam e o valor não; **uma trapaça sem folga (bucket ≤ obs) é pega pela sonda de vazamento**; janela curta, leitura
  velha ou ausente → indisponível, nunca zero.
- **Congelamento:** lista de 2 291 sinais elegíveis (869 da momentum) gravada com sha256 `e597cabf…` às 05:18:27Z, antes
  da leitura dos desfechos (05:19:52Z); IDs únicos e 0 divergências de disponibilidade de R_net.
- **Réplica computacional independente** (não importa o código principal): OI cru exportado por SELECT simples,
  `oi_rel7d` recalculado com busca binária (diferença máxima 7,1e-15 nos 869 sinais), OLS por equações normais,
  bootstrap próprio: β +0,0026, IC dia [−0,0463; +0,0594]. Compartilha a lista, as covariáveis e os desfechos — não
  audita a seleção.
- **Fumaça sintética** (`smoke_synth.txt`, rotulada SINTÉTICA, x e covariáveis reais): efeito injetado +0,25 R/desvio →
  CONFIRMA (β +0,217); dois nulos → NÃO CONFIRMA.

## Por que pode falhar (e o que não concluir)

- **Recorte estreito:** 15 mercados (os únicos onde a `momentum` emite desde ~10/09) e 23 dias de um só mês; a
  `volume_anomaly` nem entrou (parou em 09/09, antes de existir uma semana de OI). Nada aqui vale para os 275 mercados,
  para outras estratégias ou para "OI" como família.
- **Não é lotação de comprados:** todo contrato aberto tem um comprado e um vendido; `oi_rel7d` é **desvio do OI em
  relação à semana** e, numa trajetória monotônica, se comporta como a variação acumulada de ~meia semana. O teste
  diz "esse desvio não separa", não "lotação não importa".
- **Retrospectiva e reuso:** 773/869 sinais já tinham desfecho lido no R86; Holm entre duas estratégias não corrige a
  sequência H-023 → H-027 → H-033 sobre os mesmos desfechos.
- **Folga presumida antes de 26/09** e `received_at` das velas = início da transação (sensibilidade sem velas tardias
  publicada, igual).
- **Custo:** R_net do Lab é líquido dos custos **assumidos** (com funding), não execução real
  ([[KB-0171-custo-real-da-spot-1]]).
- **Não concluir:** que o efeito é zero, que o OI é inútil, que o tamanho +0,05 está refutado, nem que "menos lotado"
  é pior (as duas médias perdem e a diferença não foi testada como contraste).

## Segunda opinião (Astra)

**Pré-registro** ([[H-033-prereg]]): cinco must-fix aceitos numa emenda datada (05:15:31Z) antes de qualquer desfecho
— folga como suposição com sensibilidades de 30/60 min e subpopulações provadas, guarda da janela inteira pelo outbox e
prova por `dispatched_at`, FE de dia e de mercado+dia com consequência fixada, falha fechada no caminho inteiro com a
regra global corrigida, filtro de exchange e unicidade. **Resultado** ([[H-033-resultado]]): reproduziu a corrida, a
lista e a réplica; concorda com os três rótulos; um must-fix de redação (FE dia +0,0501 e blocos de 3 d +0,0512 **não**
ficam abaixo de +0,05 — eu tinha escrito "≤ 0,0501") e quatro de instrumento sem efeito nos números (rótulo dos grupos
de `oi_vol`, prova da janela pelos buckets usados, MAD zero numa metade, folgas 30/60 ligadas ao CONFIRMA), cada um com
teste que falhou antes; saída numericamente idêntica depois.

## Relacionados

[[Fila de Hipoteses]] · [[Proximas Hipoteses]] · [[Mapa de Estrategias]] · [[Strategy Backlog]] ·
[[Dicionario de Variaveis]] · [[KB-0024-open-interest-como-posicionamento-evidencia-e-folclore]] ·
[[KB-0020-funding-change-8h-nunca-calcula]] · [[KB-0025-o-nosso-detector-de-open-interest-so-olha-para-cima]] ·
[[KB-0170-tendencia-diaria-nao-separa-os-sinais-do-lab]] · [[KB-0163-perto-da-maxima-de-24h-nao-separa-os-sinais-do-lab]] ·
[[KB-0171-custo-real-da-spot-1]] · [[KB-0149-o-que-a-mesa-real-ensinou]] · [[Market Collector]] · [[EXP-0005-momentum-paper]]

## Advogado de Jesus e Defensor (07/10/2026)

- **Antecipação fechada estruturalmente:** o laço de OI é sequencial e, nas 869 unidades, o bucket seguinte do mesmo mercado começa até obs − 5 min; logo a leitura usada aconteceu antes de obs (pressupõe o `sampling.py` do repositório em produção e sem laços concorrentes; o instante de commit segue sem prova).
- **CR1 com t(G−1):** dia [−0,053; +0,058], mercado [−0,035; +0,040]. Operações duram no máximo 4 h, sem sobreposição no mesmo mercado. O grupo favorável é negativo em 14 de 15 mercados; o contraste de nível muda de sinal por semana (descritivo).
- **CONFIRMA inalcançável no MRE:** com a base em −0,22 R, o grupo favorável só fica lucrativo com β ≳ 0,27 R/desvio.
- **Custo:** os 20 pb do Lab valem ~0,17 R na mediana de ATR, mais que a Binance real (0,02–0,10 %). Boa parte da perda da base é custo assumido; a ~10 pb a base ficaria em ~−0,13 R, ainda negativa.
- **Não testado:** a leitura de profundidade → menos volatilidade (proposta H-035 na [[Fila de Hipoteses]]).
