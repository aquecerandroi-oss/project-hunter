---
tags: [knowledge, nota, meme, pumpfun, clones, graduacao, pedigree, portao, m5, exp-m6]
tema: memecoin / pump.fun / a assinatura medida dos clones "fundo-instituicao" com preco forjado e o custo de uma regra E2-b
fonte: banco da VPS (meme_tokens, meme_curve_snapshots, meme_features_15s, meme_trades, meme_proposals), criacoes de 14-16/09/2026 (dias BRT)
fonte_url: https://github.com/aquecerandroi-oss/project-hunter/blob/main/infra/scripts/sql/research/2026-09-16-r9-q04-e2b-precisao-recall-e-custo.sql
lido_em: 2026-09-16
evidencia: medicao propria (SQL em infra/scripts/sql/research/2026-09-16-r9-q0{1,2,3,4}-*.sql; 2 877 graduadas em 3 dias, rotulo de fita em 390 delas)
hipotese_testavel: sim
astra: nao consultada nesta nota (pesquisa quant, 16/09 ~19h BRT)
confiança: backtest do autor
owner: astra-quant
updated: 2026-09-16
status: vivo
---

# KB-0103 — Clones "fundo" com preco forjado: a assinatura medida e o custo de uma regra E2-b

**Pergunta (do plantao R2 + KB-0100):** o viveiro de clones `WOTF/WOFI/ECTF/NTDA/KIBA` tem assinatura
mensuravel? Quanto dele o E2 (pedigree) ja recusa? E quanto custaria uma regra E2-b feita sob medida?

**A resposta curta, e ela e' desconfortavel:** a assinatura existe e e' fortissima — mas **nao e' a que
imaginavamos**. Nao e' "sem twitter", nao e' "clone de simbolo", nao e' "criador em serie": esses tres
descrevem a graduacao *organica* quase tao bem quanto a forjada. O que separa e' **velocidade** (a curva
enche no mesmo minuto do mint) e **concentracao** (uma carteira paga um quinto do SOL da subida).

## 0. Universo e rotulo (escritos antes de olhar as regras)
Criacoes de 14, 15 e 16/09 (dias BRT) que **encheram** a curva (`completed_at IS NOT NULL`): **2 877**
moedas, de ~83,7 mil criacoes. Cobertura: 1 413 (49 %) tem serie de 15 s; **701 (24 %) tem fita
(`meme_trades`)**; 2 722 (95 %) tem foto de curva. Entre as com fita e >= 20 SOL comprados ate encher:
- **forjada** = <= 30 compradores unicos distintos na subida (**n = 43**);
- **organica** = >= 100 compradores unicos distintos (**n = 347**);
- a faixa 31-99 fica **cinza**, fora da conta (267 moedas).

O rotulo e' da fita (carteiras distintas comprando), nao das colunas que as regras usam — nenhuma regra
avaliada abaixo le o numero de compradores, salvo onde a nota diz que e' circular.

## 1. A assinatura medida (3 dias)
| eixo | forjadas (n=43) | organicas (n=347) | separa? |
|---|---|---|---|
| mediana de compradores unicos | **19** | **216** | (e' o rotulo) |
| mediana de SOL comprado ate encher | **85,0** (o proprio limiar da curva) | 152 | pouco |
| **fatia do maior comprador** | **25 %** | **5 %** | **muito** |
| **encheu <= 60 s do mint** | **88,4 %** | **0,6 %** | **muito** |
| nunca teve serie de 15 s (o radar nunca a viu subir) | 51,2 % | **0,0 %** | so de um lado |
| sem twitter **e** sem website | 72,1 % | **83,6 %** | **nao — e' ao contrario** |
| >= 2 moedas do mesmo simbolo em 24 h | 37,2 % | 55,0 % | **nao — e' ao contrario** |
| criador com >= 2 moedas em 7 d | 11,9 % | 46,0 % | **nao — e' ao contrario** |
| migrou | 100 % | 98,8 % | nao |

Duas leituras que mudam o mapa:
1. **O viveiro nao e' minoria: e' mais da metade do contador.** Das 2 877 graduadas, **1 595 (55,4 %)**
   tem o carimbo mais cedo de conclusao a **<= 60 s do mint** — e delas **so 9,9 %** chegaram a ter uma
   linha de 15 s (contra 97,4 % das que demoraram mais de 60 s). Elas nascem cheias. Os simbolos mais
   frequentes desse balde sao exatamente a lista do AVISO (`WOFI` 71, `WOTF` 34, `NTDA` 22, `ECTF` 15,
   `KIBA` 15) mais clones de marca (`NVDA` 28, `OPENAI` 26, `SPACEX` 18, `CLAUDE` 16, `ROLEX` 14).
2. **"Sem social" e "clone de simbolo" sao a base, nao a excecao**: 87 % de *todas* as graduadas nao tem
   twitter nem website. Quem usa isso como sinal esta descrevendo o pump.fun inteiro.

**Sobre o eixo (c) do brief (`mcap/volume >= 100`):** nao deu para medir como pedido. `mcap_sol` e' teorico
(KB-0098 §5: em Mayhem le o agente, nao comprador) e o volume 24 h do site nao e' persistido. O substituto
medido — e melhor — e' a **fatia do maior comprador** na fita: >= 20 % separa com 93 % de recall e custo de
3,5 % das organicas. O `pico de real_sol_reserves >= 84` tambem nao serve de eixo: a foto de curva (60
req/min para o universo inteiro) so pegou o pico em 1 211 das 2 877 (42 %) — ausencia nao e' ausencia.

## 2. Quanto o E2 de hoje recusa disso — e quanto ele cobra
Primeiro, o registro: **as recusas de pedigree nao existem em lugar nenhum**. `lab_gate_refusals` nao e'
historico e `meme_proposals.refusal` em 3 d so tem `daily_loss_cap` (153), `exposure_per_mint_cap` (14),
`no_later_snapshot` (6), `migrated_before_fill` (5) e 451 linhas sem `refusal`. O pedigree recusa **antes**
da proposta existir, entao nao ha trilha — a unica forma de medir e' **replicar a regra em SQL**, que e' o
que `2026-09-16-r9-q04` faz (`creator_prior_mints_1h >= 2`, `symbol_dup_24h >= 3`, `PEDIGREE_V1`).

| regra | recall (forjadas) | precisao | **custo: organicas recusadas** |
|---|---|---|---|
| **A. E2 hoje** (`creator_serial` OR `symbol_clone`) | 34,9 % (15/43) | **7,8 %** | **178/347 = 51,3 %** |
| B. so sem twitter/website | 72,1 % | 9,7 % | 290/347 = 83,6 % |
| C. so >= 2 do mesmo simbolo em 24 h | 37,2 % | 7,7 % | 191/347 = 55,0 % |

**O E2 recusa metade das graduacoes organicas para pegar um terco das forjadas.** Nesta amostra ele nao e'
um filtro de viveiro: e' um imposto largo. (Ele pode continuar valendo pelo que EXP-M6 mediu — as 21
apostas de 12/09 —, mas **nao** pelo motivo "ele recusa os clones fundo": disso ele pega 1 em 3.)

## 3. E2-b proposta, com precisao/recall e custo
| regra | recall | precisao | custo em organicas |
|---|---|---|---|
| D. so `encheu <= 60 s do mint` | 88,4 % (38/43) | **95,0 %** | **2/347 = 0,6 %** |
| E. so `maior comprador >= 20 % do SOL da subida` | 93,0 % (40/43) | 76,9 % | 12/347 = 3,5 % |
| F. so `nunca teve serie de 15 s` | 51,2 % | **100 %** | **0/347 = 0,0 %** |
| **G. E2-b = D OR (maior comprador >= 35 %)** | **100 % (43/43)** | **86,0 %** | **7/347 = 2,0 %** |
| H. E2-b estreita = D OR F | 88,4 % | 95,0 % | 2/347 = 0,6 % |

**E2-b (versao G), em palavras:** *forjada* = a curva encheu a <= 60 s do mint **OU** uma unica carteira
pagou >= 35 % de todo o SOL comprado na subida. `N` (compradores) e `Y` (volume/mcap) do brief sumiram do
enunciado de proposito: medidos, os dois sao piores que a concentracao — `ub <= 10` na serie de 15 s da
16,7 % de recall com 29 % de precisao, e "SOL por comprador >= 2" e' **circular** com o rotulo (e' a razao
entre as duas quantidades que o definem) e por isso nao entra.

**O custo real, honesto:** 7 organicas em 347 (2,0 %) — e as 2 que a perna D recusa sozinha sao moedas que o
radar so viu depois de cheias, ou seja, **moedas que a mesa nao poderia comprar de qualquer jeito**
(`curve_complete` ja as recusa). A perna que traz vantagem nova e' a da **concentracao**, e ela e' legivel
ao vivo pela fita; a perna D e' sobretudo **contabilidade**: ela limpa o denominador de "graduacoes por
dia", que hoje conta 55 % de moedas que ninguem comprou.

## 4. Recomendacao (3 linhas)
1. **Braco de pesquisa, nunca ligado a mao:** registrar `exclusoes_de_pedigree v2` com a perna de
   concentracao (`top_buyer_share_on_rise >= 0,35`) como criterio novo e `forged_fill` como recusa nomeada,
   atras do proprio interruptor do conjunto (como `pedigree_repeat_dumper`), com a perna D so como rotulo.
2. **Reabrir o custo do E2 v1:** ele cobra 51 % das graduacoes organicas por 35 % das forjadas — isso
   merece um braco de falsificacao proprio antes de continuar cobrando (EXP-M6, braco 3).
3. **Corrigir o placar antes da regra:** todo numero de "graduacao por dia" (KB-0098, KB-0101) esta inflado
   em ~2x por moedas que nascem cheias; `encheu <= 60 s` e' o rotulo pronto para separa-las.

## 5. O que fica em aberto (nao mascarar)
- **Cobertura enviesada:** o rotulo so existe nas 24 % com `meme_trades`, e o radar segue preferencialmente
  quem ele achou cedo — as forjadas sem cobertura (metade delas, sem serie de 15 s) estao sub-representadas.
- **`completed_at` e' carimbo de observacao**, o mais cedo de quatro (`graduation.earliest_completion`),
  e em 42,7 % das graduadas ele cai <= -1 s do `created_at` (mesmo bloco, arredondamento). "Encheu <= 60 s"
  le *no maximo* o mesmo minuto — nao e' tempo on-chain de preenchimento, e a nota nao o chama assim.
- **3 dias.** Sem replicacao, e' anedota com n grande, nao taxa (mesmo aviso de KB-0100).

## Ligacoes
[[11-KNOWLEDGE/KB-0100-evento-move-moeda-primeira-medida-16-09|KB-0100]] ·
[[11-KNOWLEDGE/KB-0098-quantos-bums-reais-ha-por-dia-e-quanto-tempo-temos|KB-0098]] §5 ·
[[11-KNOWLEDGE/KB-0101-snipers-e-graduacao-a-medida-com-n-grande|KB-0101]] ·
[[05-EXPERIMENTS/EXP-M6-exclusoes-de-pedigree]] · [[02-MARKET/Eventos/2026-09-16]]
