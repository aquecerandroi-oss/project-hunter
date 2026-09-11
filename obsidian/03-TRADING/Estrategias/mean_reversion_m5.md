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
| `v1` | `research_only` | `active` (ativada em 2026-09-11T08:32:18Z / 05:32 BRT) | sem avaliação — replay bloqueado pelo portão do `replay-worker`, ver [[EXP-0028-mean-reversion-5-min]] | [[mean_reversion_m5-v1]] |

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

**Estado operacional em 2026-09-11:** semeada e ativada como `research_only` na VPS; decide na faixa
viva do Lab desde 05:32 BRT; **sem coorte de replay** — o portão do `replay-worker` recusa toda
corrida na VPS desde que o worker vivo foi shardado (lê `hb:strategy:shadow` e o grupo
`strategy-worker.shadow`, que com `STRATEGY_SHARDS=4` ninguém escreve e ninguém consome). Detalhes e
conserto em `.claude/state/notes-T3.84.md`.
