---
tags: ["estrategia", "catalogo", "mean_reversion_m5", "familia"]
strategy: mean_reversion_m5
updated: 2026-09-11
---
# mean_reversion_m5

<!-- generated:start -->
## Versões

| Versão | Propósito | Status | Veredito | Página |
|---|---|---|---|---|
| `v1` | `research_only` | `deprecated` (ativada 2026-09-11T08:32:18Z / 05:32 BRT, aposentada 2026-09-11T10:54:08Z / 07:54 BRT) | **`descartar`** — 90 d × 16 mkt, 373 desfechos: ex-funding **−0,1940 R** (IC95 [−0,2889; −0,0943]), PF 0,6971; as quatro condições da [[EXP-0028-mean-reversion-5-min]] falham | [[mean_reversion_m5-v1]] |

## Ligações

- Convenção: [[Estrategias/README|Estratégias]]
- Família-mãe (código-fonte, não herança): [[mean_reversion]]
- Irmã de 1 h, o mesmo eixo para cima: [[mean_reversion_h1]]
- Eixo "timeframe": [[EXP-0021-timeframe]] · Experimento próprio: [[EXP-0028-mean-reversion-5-min]]
<!-- generated:end -->


## Notas

**Família nova, criada em 2026-09-11 (T3.84).** `mean_reversion_m5_v1` é a irmã **plana** de
`mean_reversion_v1` que decide em barras de **5 min** — o eixo de timeframe da
[[EXP-0021-timeframe]] percorrido para **baixo**, exatamente como a T3.54 o percorreu para cima com
[[mean_reversion_h1]]. Não é herdeira: não importa a mãe, não herda a classe dela, tem fecho de
digest isolado e `params_hash` próprio. Três parâmetros diferem da mãe, e são **os mesmos três
nomes** que a irmã de 1 h moveu — o eixo é um só.

**O que já se sabe, sem uma única decisão** (medido em 2026-09-11, ver a página da versão e
[[EXP-0028-mean-reversion-5-min]]): o ATR% mediano da grade de 5 min é **0,27–0,30 %**, metade do de
15 min, e o piso `atr_pct_min = 0,006` herdado da mãe deixa passar **8,85 %** das barras de 5 min
contra 33,04 % das de 15 min. A consequência que ninguém tinha previsto: como o piso seleciona a
cauda volátil, o pedágio por operação sobe apenas **+0,0086 R** sobre o da mãe — e não os +0,05 a
+0,12 R que o pré-registro apostou. **O argumento de custo contra esta versão não sobreviveu à
medição**; o que decide passou a ser a expectativa bruta, que só o replay mede.

**Estado operacional em 2026-09-11:** semeada e ativada como `research_only` às 05:32 BRT e
**aposentada às 07:54 BRT do mesmo dia** — a regra do Everton ("versão ruim morre no mesmo dia")
aplicada à primeira medição que existiu. O replay bloqueado pela manhã (o portão do `replay-worker`
lia a topologia pré-shard) foi destravado pela **T3.87**, e a coorte de 90 d
`replay:92c8d080-6009-4a59-9868-31282b1bd493` rodou em 23 fatias, **414 720 barras, zero erro**.

**O que a medição disse, e ela contradiz o próprio pré-registro em cima do motivo:** a família de
5 min **não perde por custo**. O pedágio subiu apenas **+0,0105 R** sobre o da mãe (0,2285 R contra
0,2180 R, pela identidade `bruta − líquida`), e não os +0,05 a +0,12 R previstos. Quem desapareceu foi
a **vantagem bruta**: **+0,0346 R** a 5 min contra **+0,1270 R** a 15 min, com IC de blocos de dia
`[−0,0625; +0,1387]` — indistinguível de zero. **89,8 % da piora é sinal, 10,2 % é custo.**

**Consequência para quem pensar em voltar aqui:** não há versão de custo a escrever nesta grade
(maker, alvo maior, `atr_pct_min` mais alto). Sem vantagem bruta, mexer em custo não tem de onde
tirar ganho — e dois dos 16 mercados elegíveis (BTC e BNB, os dois mais líquidos) não produziram
**nenhuma** decisão em 90 dias, porque o piso de ATR% herdado corta a grade curta deles inteira.
