---
tags: [knowledge, nota, meme, pumpfun, clones, graduacao, pedigree, portao, replicacao, m5, exp-m6]
tema: memecoin / pump.fun / replicacao da E2-b em 12 e 13/09 (fora da amostra do R9) e o efeito dela no R das apostas de papel medidas
fonte: banco da VPS (meme_tokens, meme_trades, meme_features_15s, meme_paper_bets), criacoes e apostas de 12 e 13/09/2026 (dias BRT)
fonte_url: https://github.com/aquecerandroi-oss/project-hunter/blob/main/infra/scripts/sql/research/2026-09-16-r13-q02-e2-e-e2b-matriz.sql
lido_em: 2026-09-16
evidencia: medicao propria (SQL em infra/scripts/sql/research/2026-09-16-r13-q0{1,2,3,4,5}-*.sql; 1 828 graduadas em 2 dias, rotulo de fita em 307 delas, 103 apostas medidas)
hipotese_testavel: sim
astra: nao consultada nesta nota (pesquisa quant, 16/09 ~20h BRT)
confiança: replicado
owner: astra-quant
updated: 2026-09-16
status: vivo
---

# KB-0105 — A E2-b replicada em 12 e 13/09, e o que ela teria feito com o R

**Pergunta:** o resultado de [[11-KNOWLEDGE/KB-0103-clones-fundo-com-preco-forjado-assinatura-e-custo|KB-0103]]
(14-16/09) se repete em dois dias que nao entraram naquela amostra? E se a E2-b estivesse ligada em
12-13/09, quanto R as apostas de papel **medidas** teriam perdido ou deixado de perder?

**Resposta curta:** a **direcao** replica nos dois dias e com folga — a E2-b domina a E2 de hoje em recall
e em custo, sempre. O **nivel** nao replica: o custo em organicas sobe de 2,0 % (R9) para **3,9 % em 13/09 e
11,4 % em 12/09**, e a precisao cai. E o efeito em R e' grande e de um lado so: nos dois dias a E2-b marcaria
**41 das 103 apostas medidas**, que somam **-14,2 R de -18,9 R** — mas os dois dias sao dias perdedores, entao
o que se mede e' *prejuizo evitado*, nunca ganho.

## 0. Metodo e rotulo (reuso, nao reinvencao)
Identico ao R9 (`2026-09-16-r9-q03/q04`): entre as graduadas do dia com cobertura de `meme_trades` e
**>= 20 SOL comprados ate encher**, **forjada** = <= 30 compradores unicos distintos na subida,
**organica** = >= 100; 31-99 fica cinza. O rotulo vem da fita; as regras nunca leem o numero de compradores.

**Correcao de fuso (vale para o R9 tambem).** `date 'X' AT TIME ZONE 'America/Sao_Paulo'` devolve um
`timestamp` *sem* fuso, comparado depois no fuso da sessao (UTC): as janelas do R9 estao **deslocadas em 3 h**
(o "dia BRT" dele comeca as 18h BRT do dia anterior). As consultas R13 usam
`timestamptz '2026-09-12 00:00:00-03'`. Os numeros do KB-0103 nao mudam de sinal, mas nao sao dias BRT — a
nota antiga merece essa errata.

| dia BRT | criacoes | graduadas | com fita | com serie 15 s | encheu <= 60 s | elegiveis | forjadas | organicas | cinza |
|---|---|---|---|---|---|---|---|---|---|
| **12/09** | 23 640 | 861 | 188 (21,8 %) | 183 (21,3 %) | **459 (53,3 %)** | 122 | **51** | 44 | 27 |
| **13/09** | 25 131 | 967 | 240 (24,8 %) | 470 (48,6 %) | **507 (52,4 %)** | 185 | **13** | 102 | 70 |
| 14-16/09 (R9) | ~83,7 mil | 2 877 | 701 (24 %) | 1 413 (49 %) | 1 595 (55,4 %) | 390 | 43 | 347 | 267 |

Dois avisos que mudam a leitura: (1) **a prevalencia de forjadas na amostra rotulada oscila muito** — 54 %
em 12/09, 11 % em 13/09, 11 % no R9 —, e precisao anda com prevalencia; (2) em 12/09 o radar so viu 21 % das
graduadas (metade da cobertura de 13/09), entao a perna "nunca teve serie de 15 s" mede o radar, nao a moeda.
`twitter`/`website` estao **vazios em 100 % das duas amostras** — a regra B e' degenerada nesses dias.
O contador de graduacoes por dia repete o vicio do KB-0103: **~53 % nascem cheias** (<= 60 s do mint).

## 1. A assinatura, dia a dia (replica)
| eixo | 12/09 forjadas (51) | 12/09 organicas (44) | 13/09 forjadas (13) | 13/09 organicas (102) |
|---|---|---|---|---|
| mediana de compradores | 5 | 207,5 | 20 | 253 |
| mediana de SOL comprado | 85,0 | 150,0 | 387,8 | 202,5 |
| **mediana da fatia do maior comprador** | **0,970** | 0,066 | **0,771** | 0,056 |
| **encheu <= 60 s do mint** | **94,1 %** | 4,5 % | **92,3 %** | 1,0 % |
| nunca teve serie de 15 s | 100 % | 50,0 % | 92,3 % | 1,0 % |
| >= 2 do mesmo simbolo em 24 h | 41,2 % | 27,3 % | 61,5 % | 39,2 % |
| criador com >= 2 moedas em 1 h | 2,0 % | 11,4 % | 0,0 % | 16,7 % |

Os dois eixos do R9 (**velocidade** e **concentracao**) replicam com a mesma magnitude. E o achado incomodo
tambem replica: **`creator_serial` e' mais comum nas organicas que nas forjadas** (11,4 % x 2,0 % e
16,7 % x 0,0 %) — o criador em serie continua sendo sinal ao contrario.

## 2. E2 de hoje x E2-b, dia a dia
| regra | 12/09 recall | 12/09 prec | 12/09 custo | 13/09 recall | 13/09 prec | 13/09 custo | R9 recall/custo |
|---|---|---|---|---|---|---|---|
| **A. E2 hoje** (`cr1h>=2` OR `sd24>=3`) | 35,3 % | 58,1 % | **29,5 %** | 53,8 % | 14,6 % | **40,2 %** | 34,9 % / 51,3 % |
| C. so `sd24>=2` | 41,2 % | 63,6 % | 27,3 % | 61,5 % | 16,7 % | 39,2 % | 37,2 % / 55,0 % |
| D. so encheu <= 60 s | 94,1 % | 96,0 % | 4,5 % | 92,3 % | 92,3 % | 1,0 % | 88,4 % / 0,6 % |
| E. so maior comprador >= 20 % | 100 % | 91,1 % | 11,4 % | 100 % | 68,4 % | 5,9 % | 93,0 % / 3,5 % |
| F. so nunca teve serie de 15 s | 100 % | 69,9 % | 50,0 % | 92,3 % | 92,3 % | 1,0 % | 51,2 % / 0,0 % |
| **G. E2-b = D OR maior >= 35 %** | **100 %** | 91,1 % | **11,4 %** | **92,3 %** | 75,0 % | **3,9 %** | 100 % / 2,0 % |
| H. E2-b estreita = D OR F | 100 % | 68,9 % | 52,3 % | 92,3 % | 92,3 % | 1,0 % | 88,4 % / 0,6 % |

**Replica:** nos tres blocos a E2-b pega >= 92 % das forjadas cobrando <= 11,4 % das organicas, enquanto a
E2 de hoje pega 35-54 % cobrando 30-51 %. **Nao replica:** o custo de 2 % vira 11,4 % em 12/09 (5 organicas),
e a variante H (que no R9 empatava com G) desaba em 12/09 (52,3 % de custo) porque naquele dia o radar nao
via metade das organicas. **H nao e' candidata**: ela mede cobertura de radar, nao vicio da moeda.

## 3. Sensibilidade dos dois limiares
| regra | 12/09 recall / prec / custo | 13/09 recall / prec / custo |
|---|---|---|
| so encheu <= 30 s | 94,1 / 98,0 / **2,3** | 92,3 / 92,3 / **1,0** |
| so encheu <= 60 s | 94,1 / 96,0 / 4,5 | 92,3 / 92,3 / 1,0 |
| so encheu <= 120 s | 96,1 / 96,1 / 4,5 | **100** / 76,5 / 3,9 |
| so maior comprador >= 25 % | 82,4 / 91,3 / 9,1 | 69,2 / 75,0 / 2,9 |
| so maior comprador >= 35 % | 66,7 / 91,9 / 6,8 | 69,2 / 75,0 / 2,9 |
| so maior comprador >= 45 % | 64,7 / 91,7 / 6,8 | 61,5 / 80,0 / 2,0 |
| **<= 30 s OR >= 35 %** | 100 / **92,7** / **9,1** | 92,3 / 75,0 / 3,9 |
| **<= 60 s OR >= 35 %** (G do R9) | 100 / 91,1 / 11,4 | 92,3 / 75,0 / 3,9 |
| <= 60 s OR >= 45 % | 100 / 91,1 / 11,4 | 92,3 / **80,0** / **2,9** |
| <= 120 s OR >= 25 % | 100 / 89,5 / 13,6 | **100** / 65,0 / 6,9 |

Leitura: **o limiar de tempo manda** (ele sozinho ja da 92-94 % de recall a custo 1-4,5 %); a concentracao
sozinha fica em 62-82 %. Entre 35 % e 45 % quase nao ha diferenca (1 organica de cada lado); **25 % e' pior
nos dois dias** (custo sobe sem recall novo em 12/09). O par mais estavel entre os tres blocos e'
**`<= 60 s` OR `>= 35 %`**; `<= 30 s` melhora 12/09 e empata em 13/09, e merece entrar como variante.

## 4. O efeito em R das apostas de papel medidas
Universo: `meme_paper_bets` com `status='closed'` e `outcome_quality='measured'`, `entry_at` no dia BRT.
Como a mesa entra **antes** de a curva encher (idade mediana na entrada: **171 s** em 12/09, **129 s** em
13/09), a perna do tempo nunca dispara ali — a unica perna legivel na decisao e' a **concentracao ate a
entrada** (`flag_live`). Os dois carimbos (retrospectivo e ao vivo) particionam identicamente: so 1/37 e
10/66 das moedas apostadas chegaram a graduar, nenhuma em <= 60 s.

| dia | apostas medidas | R total | E2-b marca | R das marcadas | ficam | **R do que fica** | ganhadoras marcadas |
|---|---|---|---|---|---|---|---|
| **12/09** | 37 | **-9,450 R** | **20** | **-5,746 R** | 17 | **-3,704 R** | 0 de 20 |
| **13/09** | 66 | **-9,497 R** | **21** | **-8,411 R** | 45 | **-1,086 R** | 1 de 21 (+0,66 R) |
| soma | 103 | -18,947 R | 41 (39,8 %) | -14,157 R | 62 | -4,790 R | 1 |

Sensibilidade do limiar no R (recusadas / R recusado):

| limiar de `fatia do maior ate a entrada` | 12/09 | 13/09 |
|---|---|---|
| >= 25 % | 23 / **-6,488 R** | 23 / **-8,719 R** |
| >= 35 % | 20 / -5,746 R | 21 / -8,411 R |
| >= 45 % | 18 / -4,772 R | 19 / -8,251 R |

**Tres ressalvas que impedem de chamar isso de +14 R:**
1. **Os dois dias sao perdedores** (-0,26 R e -0,14 R por aposta). Recusar 40 % das apostas num dia perdedor
   melhora o placar quase por construcao; nao ha prova de que a E2-b preserve ganhadoras num dia bom.
2. **A fatia do maior comprador aos 2 minutos e' alta por natureza** — mediana **0,428** em 12/09 com
   **21 compradores** na fita. Um limiar de 35 % nessa idade nao e' o mesmo estatistico do rotulo (fatia
   sobre a subida inteira). Exigir tambem `>= 10 compradores` ja muda muito: em 12/09 recusaria 14
   (-5,174 R) em vez de 20; em 13/09, 15 (-7,955 R) em vez de 21.
3. **Ausencia de fita nao marca.** 4 apostas nao tinham fita ate a entrada (1 em 12/09, 3 em 13/09) e
   somam **+4,68 R** — inclui a melhor do periodo (**+3,76 R**). Elas escapam da E2-b por falta de dado,
   nao por merito; se a cobertura melhorar, a regra pode passar a recusa-las. **Isso e' risco, nao credito.**

## 5. Conclusao (4 linhas)
1. **Replica na direcao, nao no nivel:** em 12 e 13/09 a E2-b pega 92-100 % das forjadas cobrando 3,9-11,4 %
   das organicas, contra 35-54 % de recall a 30-40 % de custo da E2 de hoje — mesma ordem do R9, com custo
   ate 5x maior que os 2,0 % daquela amostra.
2. **Recomendo sim virar braco de pesquisa pre-registrado** (EXP-M6, braco novo), nunca ligado a mao:
   `forged_fill` como recusa nomeada, atras do interruptor do conjunto, com decisao so apos 5 dias de sombra.
3. **Limiar:** `encheu <= 60 s do mint` **OU** `maior comprador >= 35 % do SOL da subida`, com **guarda de
   `>= 10 compradores na fita`** na leitura ao vivo (sem a guarda a regra recusa por juventude, nao por vicio);
   variante a medir em paralelo: `<= 30 s OR >= 45 %`, a mais barata nos dois dias.
4. **O que a medida de R diz e nao diz:** a E2-b teria evitado **-14,2 R de -18,9 R** em 103 apostas medidas —
   mas em dois dias perdedores e com as tres ganhadoras maiores escapando por falta de fita; e' motivo para
   pre-registrar, **nao** para creditar vantagem.

## 6. O que fica em aberto
- **Cobertura enviesada** (21-25 % das graduadas tem fita) e **n = 13 forjadas** em 13/09: o intervalo de
  recall desse dia e' largo (92,3 % = 12 de 13).
- **Errata no KB-0103/R9:** janelas deslocadas em 3 h pelo `AT TIME ZONE` sobre `date`; refazer aquelas
  tabelas com `timestamptz` antes de citar os numeros como "dia BRT".
- **Dias bons nao foram testados:** falta um dia com R total positivo para saber se a E2-b corta ganhadoras.
- `completed_at` continua sendo carimbo de observacao (KB-0103 §5): "encheu <= 60 s" le *no maximo* o mesmo
  minuto do mint, nao o tempo on-chain de preenchimento.

## Ligacoes
[[11-KNOWLEDGE/KB-0103-clones-fundo-com-preco-forjado-assinatura-e-custo|KB-0103]] ·
[[11-KNOWLEDGE/KB-0098-quantos-bums-reais-ha-por-dia-e-quanto-tempo-temos|KB-0098]] ·
[[11-KNOWLEDGE/KB-0101-snipers-e-graduacao-a-medida-com-n-grande|KB-0101]] ·
[[05-EXPERIMENTS/EXP-M6-exclusoes-de-pedigree]]
