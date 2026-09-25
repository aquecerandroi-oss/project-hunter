---
tags: [experimento, meme, pumpfun, paper, pre-registro, carteiras, smart-money, porta, m5, rascunho]
updated: 2026-09-18
status: rascunho
owner: astra-quant
exp: EXP-M15
strategy: "meme/pumpfun - seguir carteiras vencedoras: entrar quando >= 2 carteiras do top-30 do dia anterior (PnL realizado na fita) compram o mesmo mint em <= 60 s; clone do conjunto vivo em todo o resto"
version: "criterio novo smart_wallets (min_smart_buyers 2, smart_window_s 60, placar diario) sobre o portao de evento + exit alvo_3x_trailing_35_apos_1_5x_tempo_30m v1"
result: nao-iniciado
evaluable: 0
days: 0
last_eval: ""
tipo: pesquisa
hipotese: —
variavel: —
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: —
classe_de_perda: —
mercado: meme
---

# EXP-M15 — seguir carteiras vencedoras ("smart entry"), como braço `research_only`

**Rascunho de pré-registro escrito em 2026-09-18 (14:36 BRT), depois da análise R57 (72 h de fita) e antes de existir placar de carteiras, critério ou conjunto no banco.** Vira pré-registro quando a Astra fechar os dois pré-requisitos da seção "O que falta antes de semear". Previsão registrada: **`descartar`**.

Protocolo congelado ao ser promovido; avaliações acrescentadas pelo fechamento diário, nunca reescritas. Régua e disciplina: KB-0092 e decisão de 10/09.

## Diretiva de origem

Everton (18/09): "parece que nunca mudamos, ficamos sempre na mesma estratégia" — a mesa filtra saúde da moeda, nunca *quem* está comprando. R57 mediu na fita (`meme_trades`, 15–18/09): o PnL realizado por carteira **persiste** dia a dia (Spearman ρ = 0,61 e 0,65; o top-30 de um dia ganha em média 2,9 SOL/carteira no dia seguinte contra 0,14 da base), mas o sinal "≥ 2 do top-30 compraram em ≤ 60 s" **não rende** com a saída da mesa: R médio −0,06 a 20 s de atraso (controle −0,06), +0,03 a 3 s (controle −0,04), IC95 da diferença cruzando zero nos dois. A única fresta foi segurar 15 min sem stop (Δ R +0,18 a 20 s, IC [+0,00; +0,39]; +0,27 a 3 s, IC [+0,08; +0,48]) — cauda, mediana negativa. 43 % dos sinais são duas carteiras no mesmo segundo (mesmo operador). O experimento existe para fechar a pergunta com o feed de evento (< 3 s), que a fita de hoje (26 s p50) não consegue.

## Hipótese (congelada ao promover)

H1: uma compra disparada por ≥ 2 carteiras persistentemente lucrativas (top-30 do dia anterior por PnL realizado, ≥ 8 pares fechados, sem criador, sem bots, sem snipers, sem pares de mesmo segundo) comprando o mesmo mint em ≤ 60 s, vista pelo portão de evento em < 3 s, tem R médio maior que o do conjunto vivo, porque essas carteiras selecionam moedas com continuação nos 15 min seguintes. **H0 (previsão): o lucro dessas carteiras é velocidade e pacote; a 3 s ele já foi consumido, e o R do braço é indistinguível do controle (Δ em [−0,10; +0,10]).**

## Definição (criterio novo, nao um parametro existente)

Nenhum parâmetro de `meme_rule_sets` expressa "quem comprou". O braço exige:

1. **Placar diário `meme_wallet_scores`** (a criar; escrita pelo meme-worker às 00:00 BRT): por carteira e dia, PnL realizado (pares (carteira, mint) fechados: `tok_out ≥ 0,95·tok_in`, `sol_out − sol_in`), n fechados, acerto, hold mediano, idade mediana da moeda na compra, máx. trades/dia. Fonte: `meme_trades` das 24 h anteriores, `program = pump`. Exclusões congeladas: criador do mint (`meme_tokens.creator`); carteiras com > 200 trades num dia; carteiras com idade mediana na compra ≤ 5 s (snipers de bloco). **Top-30** = as 30 maiores por PnL realizado com ≥ 8 pares fechados.
2. **Critério `smart_wallets`** no portão de evento (`hunter_meme_worker.event_gate_rows`): dispara quando ≥ `min_smart_buyers` (2) carteiras **distintas** do top-30 do dia anterior compraram o mint com intervalo ≤ `smart_window_s` (60) **e** as duas compras não estão no mesmo segundo (`min_pair_gap_s` 2; pares de mesmo segundo são um operador). Entrada = o evento da 2.ª compra, `features_end_time = as_of` do evento, `reasons[0].series = meme_event_gate_v1`.
3. **Conjunto** `smart_v0/1`, `kind = research_only`, `exp_ref = EXP-M15`: clone byte a byte de `flow_v2/6` (holders ≥ 20, buyers ≥ 10, progress 5–50 %, dev ≤ 0,10, snipers 21–1000, `pedigree_e2b`, `exclude_mayhem`, participação ≤ 1 %, fluxo > 0) **mais** o critério `smart_wallets`. Saídas idênticas: alvo 3×, trailing 35 % após 1,5×, piso −50 %, tempo 30 min. Size 0,05 SOL, taxa 1,75 % por perna. R = (múltiplo líquido − 1)/0,5.
4. **Segunda leitura (secundária, só para fechar a fresta da R57):** R de "hold 15 min sem stop" calculado da mesma trajetória, para o braço e para o controle B.

Controles: **A** = `flow_v2/6` no mesmo período (o que a mesa faz hoje). **B** = entradas aleatórias do mesmo feed na mesma faixa de idade (a régua da R57, recomputada por dia no fechamento) — é o controle que responde "o sinal em si vale algo?", enquanto A responde "vale mais que a porta atual?".

## Portão de desenho (C1–C8) — rascunho

| C | Critério | Veredito | Justificativa |
|---|---|---|---|
| C1 | Plausibilidade | REVISE | Mecanismo proposto (seleção por carteiras informadas) contradiz a medição da R57 (lucro consumido em ≤ 3 s). Quem perde do outro lado é quem chega depois — o braço. Falsificável, e a previsão é que seja falso. |
| C2 | Sobreajuste | PASS | Quatro limiares (top-30, ≥ 8 fechados, 2 carteiras, 60 s), todos vindos do enunciado da R57, nenhum ajustado ao resultado. |
| C3 | Amostra | REVISE | R57 achou ~170 sinais/dia na fita (5 % dos mints); no feed de evento (todos os mints jovens) o número é desconhecido — pode ser 10× maior e a maioria em pacotes. Meta: ≥ 500 propostas do braço. |
| C4 | Regime | REVISE | 72 h de uma semana; a persistência ρ ≈ 0,6 pode ser um artefato de bots estáveis. O placar diário mede a própria persistência (P4). |
| C5 | Saídas | PASS | Idênticas ao controle A. |
| C6 | Concentração | PASS | 0,05 SOL, ≤ 1 % de volume, mesmo teto do vivo. |
| C7 | Execução | REVISE | O braço só faz sentido com < 3 s entre evento e proposta; medir `latency_ms` da proposta em cada linha e descartar propostas > 5 s **antes** de olhar o R (senão mede-se a fita, não a tese). |
| C8 | Invalidação | PASS | Gatilhos abaixo; régua geral (≥ 100 apostas, 30 dias, IC 95 %). |

## Previsões (congeladas ao promover, numéricas)

- P1: Δ R médio (braço − controle A, saída da mesa) em [−0,10; +0,10], ponto **0,00**.
- P2: Δ R médio (braço − controle B, saída da mesa) em [−0,10; +0,10], ponto **+0,03** (o valor a 3 s da R57).
- P3: hold 15 min sem stop: Δ R (braço − B) em [0; +0,30], ponto +0,15, **mediana ≤ 0** (é cauda).
- P4: Spearman do PnL realizado dia a dia no placar ≥ 0,5 em ≥ 5 de 7 dias (a persistência é real, mesmo sem vantagem seguível).
- P5: ≥ 40 % dos disparos brutos são pares de mesmo segundo (excluídos pelo `min_pair_gap_s`); cadência líquida do braço entre 50 % e 200 % do controle A.
- P6: taxa de ruína (R ≤ −0,5) do braço em [25 %; 40 %] (R57: 31–35 %).

## Gatilhos de descarte

1. Δ R (braço − A) ≤ +0,05 com IC95 contendo 0 depois de 500 propostas — **descartar** (é a previsão).
2. Latência mediana evento → proposta > 5 s em qualquer semana: o braço não está medindo a tese; **pausar**, não avaliar.
3. Ruína > 3 pp acima do controle A.
4. P4 falha (ρ < 0,5 em ≥ 3 dias): o placar não persiste e o critério fica sem base; descartar.

## Régua e prazo

Leitura ÚNICA ao fim: mínimo **500 propostas** do braço **e** 10 dias corridos, o que vier por último; LOO obrigatório por dia. Tamanho de amostra: com SD ≈ 1,2 R (R57) e Δ alvo 0,15, 80 % de poder unilateral a 5 % pede ≈ 790 por braço; 500 é o piso para não decidir cedo, não a potência plena. Veredito de vida (dinheiro real) só pela régua do lab: ≥ 100 apostas e 30 dias — e este braço, pela previsão, não chega lá.

## O que NÃO fazer

Ranquear por PnL marcado (posições abertas na última cota da fita são otimistas: a cota de 100 s é antes do colapso); usar o top do próprio dia (look-ahead); contar pares de mesmo segundo como duas carteiras; baixar `min_smart_buyers` para 1; ajustar top-N/janela olhando os primeiros dias; ligar dinheiro real.

## O que falta antes de semear

1. `meme_wallet_scores` (tabela + job diário + teste de não-antecipação: o placar de D só usa trades com `received_at` < 00:00 BRT de D+1).
2. Critério `smart_wallets` no portão de evento, com `latency_ms` gravado na proposta.
3. Confirmar no feed de evento a cadência bruta de disparos e a fração de pacotes (C3, P5) — se > 90 % forem pacotes, o braço não tem amostra e o experimento não nasce.

## Avaliação

(append-only; fechamento diário acrescenta seção datada)

## Fontes

R57 (`.claude/state/notes-R57.md`: análise bruta, SQL, caveats — cobertura da fita 5,3 % dos mints / ~100 s por mint; atraso 26 s p50)
EXP-M14 (régua de R, clone de `flow_v2/6`, forma do pré-registro)
docs/DATABASE.md § 33 (`meme_trades`), § 43.2 (portão de evento lê `meme_features_15s`, `meme_event_gate_v1`)
docs/RISK_ENGINE_MEME.md § 9 (desenho do portão de evento)
