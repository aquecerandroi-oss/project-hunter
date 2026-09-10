# notes-T3.62b — 90 dias, 1 643 decisões: **agosto era a história inteira**

**Data:** 2026-09-10, 00:25 → 01:50 BRT (03:25 → 04:50 UTC). Continuação da T3.62b (o agente
anterior foi interrompido) e da T3.62.
**Owner:** quant-engineer.
**Base local:** `main @ 5006646`. **VPS:** `HEAD` andou de `572d3b6` para `3753792` durante a
janela (outros agentes); `hunter-strategy-worker-1` rodou a imagem **`572d3b6`** o tempo todo —
nenhum replay meu usou código não commitado.
**Nada commitado.** **Nenhum container parado, recriado ou reiniciado.** **Nenhum `.env*` tocado.**
**Nenhum `git pull` na VPS.** **Nenhum testcontainer.**
**Escritas na VPS:** só o CLI de replay — 17 corridas minhas (5 da `v1`, 12 da `v2`) e 3 passadas de
`--stress` (que são `READ ONLY` por construção). Todo o resto foi lido em
`repeatable read read only`.

---

## STATUS

**DONE_WITH_CONCERNS.**

| # | Entrega do brief | Resultado |
|---|---|---|
| 1 | Replay de `v1` e `v2` nos 16 mercados, mesma janela limpa, fatias ≤ 4 × ≤ 31 d, `timeout 290`, `--explain-ledger`, coortes explícitas | **OK.** §2 |
| 2 | n, expectativa bruta/líquida, PF, pedágio p50, K1–K6 (K3 com ≥ 30 dias), as três janelas de ~30 d, decomposição por mercado, IC por blocos de dia, estresse da `v10`, C5 acima do teto de 3 % | **OK.** §4–§9 |
| 3 | Veredito pelo funil, ≤ 10 linhas em português | **OK.** §10–§11 |

**O resultado em uma frase:** sobre **90 dias** de fita 100 % completa, a `v10` tem expectativa bruta
(`r_ex_funding`) **−0,0293 R** com PF **0,910** em 798 decisões e 89 dias — **negativa** —, e as duas
janelas anteriores a agosto são **−0,1216 R** e **−0,0919 R** contra **+0,1155 R** da janela de
agosto–setembro, com o Δ (J3 − J1J2) = **+0,2265 R, IC 95 % [+0,0085; +0,4293], que exclui zero**.
**K3 dispara nas três versões.** Agosto não foi *parte* da história: agosto **era** a história.

---

## ARQUIVOS

| Arquivo | O quê |
|---|---|
| `infra/scripts/sql/research/2026-09-10-t362b-q00-coorte-v10.sql` | acha a coorte da `v10` que o agente anterior deixou (recibos + populações + catálogo) |
| `infra/scripts/sql/research/2026-09-10-t362b-q01-janela-e-cobertura.sql` | a janela limpa: profundidade, densidade por recorte de 30 d, dias com buraco |
| `infra/scripts/sql/research/2026-09-10-t362b-q10-populacoes-e-portas.sql` | K1–K6, pooled, as três janelas, por mercado, 4-vs-12, arrasto de funding |
| `infra/scripts/sql/research/2026-09-10-t362b-q11-dump-decisoes.sql` | dump por decisão (CSV) para o bootstrap local |
| `infra/scripts/sql/research/2026-09-10-t362b-q12-recibos-e-isolamento.sql` | recibos das 36 corridas (K4), isolamento, e o que `replay_runs` guardou |
| `.claude/state/exp-drafts/t362b/blocos90.py` | bootstrap de blocos de dia: IC da média, Δ não pareado, Δ pareado por dia |
| `.claude/state/exp-drafts/t362b/test_blocos90.py` | 14 testes com séries sintéticas e valor esperado à mão |
| `.claude/state/exp-drafts/t362b/analise.py` | as oito seções da leitura de 90 d |
| `.claude/state/exp-drafts/t362b-decisoes.csv` | as 1 642 decisões terminais lidas da VPS |
| `.claude/state/notes-T3.62b.md` | este arquivo |

Os dois arquivos `2026-09-09-t362b-q00/q01` que o agente anterior deixou continuam no disco; eu
não os editei — as consultas desta tarefa são as `2026-09-10-*`.

Todos com raiz em `C:\dev\project-hunter\`.

---

## 1. O QUE EU ENCONTREI VIVO ÀS 00:25 BRT — e a decisão que ela forçou

O brief dizia que o agente anterior "foi interrompido ao começar a `v1`". **Ele não foi
interrompido no lugar onde o processo estava.** O `docker exec` sobreviveu à morte do cliente e um
`bash -c` órfão continuou disparando fatias no host da VPS:

```
$ ssh hunter-vps 'ps -eo pid,etimes,args | grep replay'
3197654  245  bash -c R(){ timeout 290 docker exec hunter-strategy-worker-1 python -m
                hunter_strategy_worker.replay.run --version mean_reversion:$1 ... };
                R v1 2026-07-12 2026-08-11 BTCUSDT,BNBUSDT,ZECUSDT,SUIUSDT fa005985-... v1-w2-s2
                R v1 2026-07-12 2026-08-11 NEARUSDT,UNIUSDT,ARBUSDT,TAOUSDT fa005985-... v1-w2-s3
3202867   50  timeout 290 docker exec ... --markets NEARUSDT,UNIUSDT,ARBUSDT,TAOUSDT ...
```

O `bash -c` continha **exatamente duas** chamadas restantes, e a `v1` já tinha **7 das 12** fatias
gravadas. Duas consequências, as duas decididas antes de eu rodar qualquer coisa:

1. **Não matei o processo.** Ele estava fazendo trabalho legítimo, com a coorte certa; matá-lo
   deixaria uma fatia pela metade. **Esperei** a faixa esvaziar (`LIVRE 03:29:28 UTC`) antes da
   minha primeira corrida — porque duas corridas simultâneas dividem o teto de
   `REPLAY_CPU_SHARE`, e o `timeout 290` de cada uma passaria a medir contenção e não trabalho.
2. **Não refiz nada.** As 7 fatias da `v1` e as 12 da `v10` são delas; eu completei as 5 que
   faltavam da `v1` e rodei as 12 da `v2`.

**A coorte da `v10` do agente anterior**, achada pelo recibo (q00): `replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3`
— 12 fatias, 138 240 barras, **798 decisões**, 0 erro, `markets_digest` cobrindo os 4 recortes dos 16
mercados, janela `2026-06-12 → 2026-09-10`, corridas de 23:26 a 00:06 BRT. É a do brief, dígito a dígito.

### 1.1 As três versões, e a diferença entre elas (q10 §0)

| versão | estado | propósito | `atr_pct_min` | `stop_atr` | alvos | `atr_timeframe`/`bars` | portão |
|---|---|---|---|---|---|---|---|
| `v1` | active | research_only | **0,006** | **1,0** | 1,5 / 2,5 | 15m / 97 | — |
| `v2` | active | research_only | 0,008 | **1,0** | 1,5 / 2,5 | 15m / 97 | — |
| `v10` | active | research_only | 0,008 | 1,5 | 2,25 / 3,75 | **1h / 24** | — |

Mesmo `code_ref` nas três (sufixo `239dadc3f0bd395f`): **o contraste é de parâmetro, não de código**.
Nenhuma tem `eligibility_policy`, então **K4 é mensurável** nas três (`PIPELINE.md` §4b item 12).

### 1.2 A janela limpa é limpa de verdade (q01)

Isto mudou desde a T3.62, e muda tudo. A partição `candles_1m_2026_06` **passou a existir** e o
backfill drenou:

```
16 mercados × 129 600 minutos finais cada = 100,00 % de densidade
J1 06-12→07-12 : 691 200 / 691 200 minutos = 100,00 %
J2 07-12→08-11 : 691 200 / 691 200 minutos = 100,00 %
J3 08-11→09-10 : 691 200 / 691 200 minutos = 100,00 %
dias com qualquer buraco: 0 linhas
```

**Os três recortes de 30 d são feitos do mesmo material.** Uma diferença entre eles não pode ser
diferença de dado — que era a primeira hipótese a excluir antes de chamar qualquer coisa de regime.

---

## 2. AS 36 CORRIDAS (recibos, q12)

Uma coorte por versão; 3 janelas de 30 d × 4 fatias de 4 mercados = 12 fatias cada.

| versão | coorte | quem rodou |
|---|---|---|
| `mean_reversion v10` | `replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3` | agente anterior (12/12) |
| `mean_reversion v1` | `replay:fa005985-0b55-4820-904c-8ada589e441c` | anterior 7/12 + **eu 5/12** |
| `mean_reversion v2` | `replay:da706026-319a-451e-950e-7728ca9ae563` | **eu, 12/12** |

Fatias de mercado (o `markets_digest` de cada uma):

```
s1 cae01bbbb571  ETHUSDT SOLUSDT XRPUSDT DOGEUSDT      <- os 4 que geraram a hipótese
s2 2c3b5ce85b8b  BTCUSDT BNBUSDT ZECUSDT SUIUSDT
s3 386226e9045f  NEARUSDT UNIUSDT ARBUSDT TAOUSDT
s4 9fa6a1946153  LINKUSDT DASHUSDT PROMUSDT SAHARAUSDT
```

O comando, verbatim (uma das 17 minhas; as outras só trocam versão, coorte, mercados e janela):

```
$ timeout 290 docker exec hunter-strategy-worker-1 \
    python -m hunter_strategy_worker.replay.run \
    --version mean_reversion:v2 --from 2026-08-11 --to 2026-09-10 \
    --markets LINKUSDT,DASHUSDT,PROMUSDT,SAHARAUSDT --workers 3 \
    --cohort replay:da706026-319a-451e-950e-7728ca9ae563 \
    --explain-ledger /tmp/t362b-v2-w3-s4.jsonl
{'run_id': 'da706026-...', 'version_label': 'mean_reversion v2',
 'window_from': '2026-08-11T00:00:00+00:00', 'window_to': '2026-09-10T00:00:00+00:00',
 'markets': ['binance:LINKUSDT','binance:DASHUSDT','binance:PROMUSDT','binance:SAHARAUSDT'],
 'market_count': 4, 'markets_digest': '9fa6a1946153...', 'bars_evaluated': 11520,
 'signals': 303, 'outcomes_resolved': 303, 'outcomes_open': 0, 'seconds': 183.116,
 'bars_per_second': 62.91, 'decision_lag_s': 2, 'workers': 3,
 'evaluations_by_state': {'not_triggered': 11423, 'triggered': 97}, 'errors': 0,
 'context_minutes': 1560}
```

**Totais por versão** (`signals` é cumulativo por `run_id` — a armadilha de denominador da
T3.33e/T3.40/T3.54; o número real é o `max`):

| versão | fatias | barras | **decisões** | abertos | erros | `unavailable` | **K4** | `triggered` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `v10` | 12 | 138 240 | **798** | 0 | 0 | 1 280 | **0,926 %** | 1 760 |
| `v1` | 12 | 138 240 | **543** | 0 | 0 | 1 280 | 0,926 % | 954 |
| `v2` | 12 | 138 240 | **303** | 0 | 0 | 1 280 | 0,926 % | 522 |
| **total** | **36** | **414 720** | **1 644** | **0** | **0** | | | |

**Nenhuma corrida passou de 205 s**; o `timeout 290` nunca chegou perto de disparar. As 1 280 barras
`unavailable` são idênticas nas três versões e estão todas no aquecimento da primeira fatia de cada
janela (a janela de contexto é de 1 560 min = 26 h e a fita começa exatamente em `2026-06-12 00:00`):
**aquecimento, não buraco**.

### 2.1 Livros-razão: `barras = linhas`, exato

```
$ docker exec hunter-strategy-worker-1 sh -c "ls /tmp/t362b-*.jsonl | wc -l; ..."
39                 <- 36 explain-ledgers + 3 de estresse
276480             <- v1 + v2  = 2 × 138 240
138240             <- v10
```
414 720 = 36 × 11 520. Nenhuma barra avaliada ficou sem linha de livro-razão.

### 2.2 O CONCERN 1 da T3.62 está FECHADO (q12 §4)

A T3.62 registrou que `replay_runs` só guardava a primeira fatia de cada janela, porque
`uq_replay_runs_slice` era `(run_id, window_from, window_to)`. A **T3.67 (`572d3b6`)** acrescentou
`markets_digest` à tabela e à chave única. Medido agora:

```
+---------------------------------------------+-----------------+----------------------------+-----------------+
|                   cohort                    | linhas_duraveis | fatias_de_mercado_duraveis | barras_duraveis |
+---------------------------------------------+-----------------+----------------------------+-----------------+
| replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3 |              12 |                          4 |          138240 |
| replay:da706026-319a-451e-950e-7728ca9ae563 |              12 |                          4 |          138240 |
| replay:fa005985-0b55-4820-904c-8ada589e441c |              12 |                          4 |          138240 |
+---------------------------------------------+-----------------+----------------------------+-----------------+
```

**12 de 12 em cada coorte.** O recibo durável agora conta a verdade; o `system_events` deixou de
ser a única fonte completa.

### 2.3 Isolamento (q12 §3)

```
+------------------+-----------+-----------------------+
| linhas_de_outbox | propostas | fora_de_research_only |
+------------------+-----------+-----------------------+
|                0 |         0 |                     0 |
+------------------+-----------+-----------------------+
```

Nenhuma das 1 644 decisões virou linha de `shadow_outbox` ou de `trade_proposals`, e nenhuma saiu de
`research_only`. (`shadow_outbox` não tem coluna `signal_id`: a identidade viaja em `payload`, e é
sobre `payload->>'signal_id'` que o teste é feito — está no cabeçalho do q12.)

---

## 3. CONCERN 1 (meu, e é o que decide o método) — **`funding_rates` só existe a partir de 2026-08-08 16:00 UTC**

O backfill de 90 dias trouxe **vela**, não **funding**. Medido (probe do q10):

```
+------------+----------+--------+----------------------------+------------------------+
|    mes     | mercados | linhas |          primeiro          |         ultimo         |
+------------+----------+--------+----------------------------+------------------------+
| 2026-08-01 |       16 |   1389 | 2026-08-08 16:00:00.002+00 | 2026-08-31 20:00:00+00 |
| 2026-09-01 |       16 |    532 | 2026-09-01 00:00:00.005+00 | 2026-09-10 04:00:00+00 |
+------------+----------+--------+----------------------------+------------------------+
```

Consequência direta: `signal_outcomes.r_multiple` (o R líquido **com** funding) é **nulo** em

| versão | terminais | com `r_net` | **cobertura K5 de `R_net`** | motivo dos nulos |
|---|---:|---:|---:|---|
| `v10` | 798 | 300 | **37,59 %** | `funding_schedule_unknown` × 498 |
| `v1` | 542 | 253 | **46,59 %** | `funding_schedule_unknown` × 288, `funding_ambiguous_exit` × 1 |
| `v2` | 302 | 175 | **57,76 %** | `funding_schedule_unknown` × 126, `funding_ambiguous_exit` × 1 |

**K5 (cobertura de `R_net` < 70 %) dispara nas três.** K5 não mata — "rebaixa toda leitura futura"
(`SHADOW-LAB.md` linha 160).

**A decisão de método, e por que ela não é uma saída pela tangente.** Se eu filtrasse por
`r_multiple is not null`, estaria medindo **agosto e setembro de novo** e chamando isso de 90 dias —
exatamente o erro que o brief manda desmascarar. Então o eixo desta nota é **`r_ex_funding`** (bruto
menos spread e taxa, **sem** funding), que existe em **100 %** dos desfechos terminais. Três razões:

1. **O funil já usa esse eixo.** `SHADOW-LAB.md` linha 157 define K3 como "expectancy bruta
   (`r_ex_funding`) < 0". A régua congelada pede exatamente este número.
2. **O arrasto do funding é desprezível onde ele é conhecido** (q10 §6): na `v10`, média
   **−0,0011 R** e mediana **0,0000 R** sobre as 300 decisões com funding. `r_exf` e `r_net`
   praticamente coincidem — usar um no lugar do outro custa ~0,1 % de R, não uma conclusão.
3. **Toda a população é `long`** (1 644 de 1 644, conferido), então a reconstrução de `r_bruto`
   é direcionalmente válida e o pedágio sai positivo e limitado em todas as versões
   (`v10` entre 0,0250 e 0,2185 R).

**O que essa escolha *não* conserta:** um regime de funding muito diferente em junho/julho ficaria
invisível. É uma incerteza real e fica declarada — mas ela teria de valer ~0,12 R por operação para
virar o sinal da `v10`, cem vezes o arrasto medido em agosto.

---

## 4. O RESULTADO POOLED — 90 dias (analise.py §1)

Eixo `r_ex_funding`, 16 mercados, 2026-06-12 → 2026-09-10, IC 95 % por bootstrap de **blocos de dia**
(20 000 reamostragens, semente 20260910):

```
versao    n  dias    bruta  pedagio50  ex-funding      PF  acerto%  IC95 da ex-funding
v10     798    89  +0.0728     0.1034     -0.0293   0.910     48.6  [-0.1336; +0.0728]
v1      542    83  +0.1270     0.2169     -0.0910   0.851     45.6  [-0.2129; +0.0311]
v2      302    68  +0.1325     0.1722     -0.0343   0.940     46.4  [-0.1695; +0.0999]
```

**Checagem cruzada de duas implementações independentes:** o q10 §2 (agregação em Postgres, sobre as
linhas do banco) devolve `exp_exfunding_r = −0.0293` e `pf_exfunding = 0.9104` para a `v10`; o
`analise.py` §1 (NumPy, sobre o CSV baixado) devolve `−0.0293` e `0.910`. Mesmo número por dois
caminhos que não compartilham código — é o que dá para fazer no lugar do teste de look-ahead que o
brief proíbe rodar aqui (§9.1).

**As três são negativas depois dos custos.** E o motivo é o mesmo de sempre, agora com 90 dias em
vez de 31: o bruto é positivo nas três (+0,073 a +0,133 R) e **o pedágio come tudo**. A `v1`, que é
a `v2` com o piso de ATR baixado para 0,006, paga **0,2169 R de pedágio mediano** — mais que o dobro
da `v10` — e é a pior das três, o que é a mesma lição do EXP-0019 vista por um terceiro ângulo.

**A `v10` continua sendo a mais barata da família** (pedágio p50 0,1034 R contra 0,1722 e 0,2169) e
continua sendo a menos ruim. Mas "menos ruim" agora quer dizer **negativa**.

Para comparar com a leitura anterior: a T3.62 mediu a `v10` em **+0,1105 R líquido, PF 1,451**, em
31 dias. Aqueles 31 dias são a janela J3 desta nota. **Nada estava errado lá; a janela é que era a
resposta.**

---

## 5. AS TRÊS JANELAS DE 30 DIAS — a pergunta central do brief (analise.py §2)

```
versao janela               n  dias    bruta  pedagio50  ex-funding      PF  acerto%  IC95
v10   J1 jun12-jul12      328    30  -0.0156     0.1065     -0.1216   0.695     43.0  [-0.2907; +0.0398]
v10   J2 jul12-ago11      182    29  +0.0251     0.1164     -0.0919   0.726     46.2  [-0.2091; +0.0185]
v10   J3 ago11-set10      288    30  +0.2037     0.0837     +0.1155   1.483     56.6  [-0.0625; +0.2838]

v1    J1 jun12-jul12      196    28  +0.0012     0.2337     -0.2382   0.656     39.3  [-0.4271; -0.0500]
v1    J2 jul12-ago11       95    29  +0.0791     0.2457     -0.1600   0.760     41.1  [-0.3607; +0.0788]
v1    J3 ago11-set10      251    26  +0.2434     0.1871     +0.0502   1.096     52.2  [-0.1241; +0.2182]

v2    J1 jun12-jul12       93    25  +0.0285     0.1870     -0.1639   0.750     40.9  [-0.3743; +0.0755]
v2    J2 jul12-ago11       36    19  -0.1998     0.1549     -0.3661   0.507     30.6  [-0.7032; +0.0332]
v2    J3 ago11-set10      173    24  +0.2576     0.1540     +0.1044   1.208     52.6  [-0.0469; +0.2625]
```

**Nas três versões, sem exceção: J1 negativa, J2 negativa, J3 positiva.** E não é pouco — na `v10` a
diferença é de **0,23 R por operação** entre J3 e as duas anteriores.

**Duas leituras que o número exige e que não são a mesma coisa:**

- **A taxa de acerto muda junto**: 43,0 % → 46,2 % → **56,6 %** na `v10`. Não é só o tamanho dos
  ganhos; a estratégia **acerta mais** em agosto. Isso é a assinatura de um mercado em que reversão
  à média funciona (lateral), e não a de uma cauda que salvou a média.
- **O pedágio também melhora em J3** (0,1065 → 0,1164 → **0,0837** na `v10`). Parte da vantagem de
  agosto é volatilidade maior dando stop maior em preço, e portanto custo fixo menor em R. Isso
  **não** é vantagem de estratégia; é vantagem de regime, e some quando o regime some.

### 5.1 O Δ (J3 − J1J2) exclui zero (analise.py §3)

Bootstrap **não pareado** — J1/J2 e J3 não têm um único dia em comum, então parear seria inventar
um par:

```
versao  n(J3)  n(J1J2)   media J3   media J1J2         D  IC95 do D
v10       288      510    +0.1155      -0.1110   +0.2265  [+0.0085; +0.4293]
v1        251      291    +0.0502      -0.2127   +0.2629  [+0.0328; +0.4873]
v2        173      129    +0.1044      -0.2203   +0.3247  [+0.0706; +0.5715]
```

**Os três IC excluem zero.** Este é o resultado mais forte da nota: a diferença entre a janela de
agosto e as duas anteriores **não** é ruído amostral, nas três versões.

**A ressalva antes da conclusão, como na T3.62:** as três versões **não são independentes** — `v2` e
`v10` têm o mesmo `atr_pct_min = 0,008` e a `v1` só afrouxa o piso; elas decidem sobre barras que se
sobrepõem muito. "Três de três" não é um teste com p = 1/8; é **um** resultado visto por três lentes
correlacionadas. O que ele autoriza a dizer é: *a vantagem que a T3.62 mediu vive na janela de
agosto–setembro e não sobrevive fora dela* — e isso basta.

**O que ele não autoriza a dizer:** que a J3 é "o regime lateral". Eu não classifiquei regime por
`market_regimes` nesta leitura; J3 é um recorte de **calendário**. A frase honesta é "a janela de
agosto", não "o regime de agosto". Cruzar com `market_regimes` é a tarefa seguinte, e ela é barata.

---

## 6. DECOMPOSIÇÃO POR MERCADO E A VISTA DE REPLICAÇÃO (analise.py §4–§5)

**K6 não dispara em lugar nenhum:** maior fatia de mercado 10,5 % (`v10`, ZEC), 13,1 % (`v1`),
20,5 % (`v2`) — longe dos 60 %.

`v10`, 16 mercados, `r_ex_funding` médio:

```
SOLUSDT  orig  46  +0.1307   |  DASHUSDT   novo  55  -0.0052
BNBUSDT  novo  10  +0.1224   |  PROMUSDT   novo  62  -0.0187
SAHARA   novo  63  +0.0528   |  LINKUSDT   novo  47  -0.0225
UNIUSDT  novo  73  +0.0501   |  TAOUSDT    novo  65  -0.0881
BTCUSDT  novo   8  +0.0326   |  NEARUSDT   novo  79  -0.0902
ZECUSDT  novo  84  +0.0296   |  DOGEUSDT   orig  37  -0.0989
ETHUSDT  orig  30  +0.0119   |  XRPUSDT    orig  25  -0.1072
                             |  ARBUSDT    novo  67  -0.1634
                             |  SUIUSDT    novo  47  -0.1707
```

**7 mercados positivos, 9 negativos.** Não há um mercado carregando o resultado, e não há um mercado
matando: a `v10` é uniformemente medíocre em 90 dias.

**4 originais vs 12 novos, Δ pareado por dia** (a mesma reamostragem de dias alimenta os dois lados):

```
versao  n orig  n novos      orig     novos  D(orig-novos)  IC95
v10        138      660   +0.0002   -0.0354        +0.0356  [-0.1056; +0.1793]
v1          51      491   +0.0265   -0.1032        +0.1296  [-0.3165; +0.5350]
v2          20      282   +0.2245   -0.0527        +0.2772  [-0.3220; +0.7955]
```

**A assinatura de seleção da T3.62 sobreviveu em sinal e encolheu em conteúdo.** Os 4 originais
continuam rendendo mais que os 12 novos nas três versões, nenhum Δ exclui zero — mas na `v10` o
grupo original agora entrega **+0,0002 R**, isto é, **exatamente zero**. Em 31 dias a leitura era
"a vantagem estava nos 4 que geraram a hipótese"; em 90 dias a leitura é **"não há vantagem em
nenhum dos dois grupos"**. É um achado mais simples e mais duro que o anterior.

---

## 7. ESTRESSE (§7 do brief) — e o seu limite, que é grande

Três passadas, `--stress replay:<coorte>`, `READ ONLY` por construção.

### 7.1 `v10` (a que o brief pede), coorte `c7d138eb`, 798 entradas congeladas, 16 mercados

| cenário | n | expectancy (R) | PF | Δ vs base | IC 95 % do Δ |
|---|---:|---:|---:|---:|---|
| `base` | 300 | 0,1025 | 1,4177 | — | — |
| `custos_x2` | 300 | **0,0128** | 1,0454 | −0,0896 | [−0,0979; −0,0803] |
| `stop_x0.75` | 300 | 0,1131 | 1,3341 | +0,0106 | [−0,0691; +0,0715] |
| `stop_x1.25` | 300 | 0,0922 | 1,4829 | −0,0103 | [−0,0430; +0,0246] |
| `alvo_x0.75` | 300 | 0,0770 | 1,3212 | −0,0255 | [−0,0517; +0,0063] |
| `alvo_x1.25` | 299 | 0,0992 | 1,4025 | +0,0010 | [−0,0226; +0,0252] |
| `entrada_mais_1_barra` | 300 | 0,1198 | 1,4936 | +0,0173 | [−0,0067; +0,0477] |
| pior recorte por mercado | 289 | `sem ETHUSDT` **+0,0917** | 1,3617 | — | — |
| `1a_metade_ate_2026-07-26` | **0** | — | `no_evaluable_outcomes` | — | — |
| `2a_metade_apos_2026-07-26` | 300 | 0,1025 | 1,4177 | — | — |

**Veredito do motor: `dependente de metade`.** Os das outras duas: `v1` **`frágil a custos`**
(`custos_x2` → −0,1482, PF 0,751; e ainda frágil a parâmetros em `stop_x0.75` e `alvo_x1.25`, e
dependente de UNIUSDT); `v2` **`frágil a custos`** (`custos_x2` → −0,0706, PF 0,875).

### 7.2 CONCERN 2 — **o `--stress` só enxerga a janela em que há funding, e o `n = 0` na primeira metade é artefato**

Repare no `base`: **n = 300**, não 798, com `descartes: funding_indeterminado=498`. O motor
reprecifica a partir de `r_multiple`, e `r_multiple` só existe de 2026-08-08 16:00 UTC em diante.
Então:

- **o `base` do estresse da `v10` é a janela J3**, não os 90 dias — é o mesmo +0,1025 R da T3.62;
- **`1a_metade_ate_2026-07-26 → n = 0` não quer dizer "a estratégia não decidiu em junho e julho"**
  (ela decidiu 510 vezes); quer dizer que **nenhuma daquelas decisões é reprecificável**. O veredito
  `dependente de metade` está tecnicamente certo e substantivamente vazio;
- portanto **o estresse desta coorte não diz nada sobre junho e julho.** A leitura de 90 dias tem
  de vir do §4/§5, e o estresse serve só para o que ele consegue ver.

*Sugestão para quem mexer no motor:* `stress.py` poderia cair para `r_ex_funding` quando o funding é
indeterminado, marcando o cenário — hoje ele descarta a decisão inteira, e o custo disso é que a
passada de estresse fica muda justamente na parte da janela que interessa. **Não mexi:** o brief
desta tarefa é medir, e `stress.py` é código de produção fora do meu escopo.

### 7.3 O custo dobrado sobre os 90 dias, de primeira ordem (analise.py §7)

Como o estresse não alcança J1/J2, a conta equivalente feita à mão, com a aproximação declarada
(`r_exf_x2 = r_exf − pedágio`; ela **subestima** o estrago, porque supõe que o caminho até a saída
não muda quando o custo dobra):

```
versao    n  ex-funding  pedagio med  custo x2 (1a ordem)    PF x2
v10     798     -0.0293       0.1021              -0.1313    0.658
v1      542     -0.0910       0.2180              -0.3090    0.578
v2      302     -0.0343       0.1668              -0.2012    0.699
```

**As três são frágeis a custos nos 90 dias**, e por uma margem que não é discutível.

---

## 8. C5 — a fatia acima do teto de risco de 3 % (analise.py §6)

A banda `paper_v1` é `[0,003; 0,03]` — `min_stop_distance_pct` / `max_stop_distance_pct` em
`packages/risk-core/hunter_risk/limits.py:151-152`. O número medido aqui é
`initial_risk / p_entry`, que é exatamente **a distância até o stop como fração da entrada**, então
a comparação é com a grandeza certa e não com um proxy.

| versão | janela | n | acima do teto | % | risco % p50 |
|---|---|---:|---:|---:|---:|
| **`v10`** | **(todas)** | **798** | **134** | **16,8 %** | 0,01939 |
| `v10` | J1 jun12-jul12 | 328 | 30 | 9,1 % | 0,01872 |
| `v10` | J2 jul12-ago11 | 182 | 11 | 6,0 % | 0,01723 |
| `v10` | **J3 ago11-set10** | 288 | **93** | **32,3 %** | 0,02412 |
| `v1` | (todas) | 542 | 12 | 2,2 % | 0,00924 |
| `v2` | (todas) | 302 | 12 | 4,0 % | 0,01158 |

**Os 29,9 % que a T3.62 mediu eram os 32,3 % da J3.** Sobre 90 dias a `v10` fica em **16,8 %** —
metade. E o motivo é o mesmo eixo de sempre: J3 é a janela de ATR% mais alto (risco p50 0,02412
contra 0,01723 em J2), e um stop de 1,5 × ATR de 1 h sobre ela estoura o teto de 3 % com o dobro da
frequência. **C5 não é uma propriedade da versão; é uma propriedade da versão × regime** — e isso é
uma informação nova que 31 dias não podiam dar.

Continua valendo o que a T3.62 disse: 16,8 % (e 32,3 % num regime como o de agosto) das decisões
seriam recusadas pelo sizing, e uma população recortada pelo teto é uma população diferente da
medida aqui. **A `v10` como está não é candidata a `paper` neste universo** — e agora nem sequer
por esse motivo, porque ela não tem vantagem para levar.

---

## 9. O FUNIL K1–K6, com 90 dias (analise.py §8, q10 §1)

Régua congelada, `docs/plans/SHADOW-LAB.md` linhas 153–162.

| critério | limiar | `v10` | `v1` | `v2` |
|---|---|---|---|---|
| **K1** população mínima | < 20 decisões | 798 ✔ | 543 ✔ | 303 ✔ |
| **K2** população saturada | > 1 500 | 798 ✔ | 543 ✔ | 303 ✔ |
| **K3** ≥ 100 desfechos **e** ≥ 30 dias **e** bruta (`r_ex_funding`) < 0 | — | 798 / **89 d** / **−0,0293** → **DISPARA** | 542 / 83 d / −0,0910 → **DISPARA** | 302 / 68 d / −0,0343 → **DISPARA** |
| **K4** `unavailable` > 40 % das barras | 40 % | 0,926 % ✔ | 0,926 % ✔ | 0,926 % ✔ |
| **K5** cobertura de `R_net` < 70 % | 70 % | **37,59 %** ✘ | **46,59 %** ✘ | **57,76 %** ✘ |
| **K6** ≥ 60 % das decisões num mercado | 60 % | 10,5 % ✔ | 13,1 % ✔ | 20,5 % ✔ |

**K3 é o portão que 31 dias nunca conseguiam medir e 90 dias medem — e ele dispara nas três.**
Na T3.62 nenhuma versão chegava a 30 dias distintos com folga (a `v10` tinha exatamente 30 e as
outras 23–25), então a terceira cláusula nunca era alcançada. Agora as três têm 68–89 dias
distintos e centenas de desfechos, e as três têm **bruta negativa**.

Pela régua, K3 disparado é **"deprecar ou declarar"** (linha 161–162), e **K1 não está sozinho** —
K5 também disparou. **O funil manda depreciar as três.**

**A ressalva de honestidade sobre K5, que é minha e não da régua:** K5 dispara por **ausência de
`funding_rates` histórico**, não por desfecho escondido. É uma limitação de dado, não um resultado
mascarado — e o eixo que eu usei (`r_ex_funding`) é o eixo que o próprio K3 pede. K5 aqui **rebaixa
a confiança na precificação final**, mas não é o que mata: o que mata é o K3, e o K3 é medido no
eixo certo com 100 % de cobertura.

---

## 9.1 TESTES

Esta tarefa **não escreveu código de produção**: o que ela produz é evidência, SQL de pesquisa e um
módulo de leitura local com testes próprios.

O módulo novo (bootstrap de blocos de dia), TDD, séries sintéticas com valor esperado calculado à mão:

```
$ cd .claude/state/exp-drafts/t362b && uv run --with numpy --with pytest pytest test_blocos90.py -q -p no:randomly
..............                                                           [100%]
14 passed in 2.43s
```

O código de produção de que a leitura depende:

```
$ uv run pytest packages/core/tests/unit/strategies/test_mean_reversion_v1.py \
                packages/core/tests/unit/strategies/test_mean_reversion_h1_v1.py -q -p no:randomly
......................................................................   [100%]
70 passed in 6.50s

$ uv run pytest services/strategy-worker/tests/test_replay_stress.py \
                services/strategy-worker/tests/test_replay_contract.py \
                services/strategy-worker/tests/test_replay_arms.py -q -p no:randomly -m "not integration"
E       AssertionError: assert 'heartbeat_stale:3429811s' is None
services\strategy-worker\tests\test_replay_contract.py:322: AssertionError
FAILED services/strategy-worker/tests/test_replay_contract.py::TestRefuseDirectRun::test_a_healthy_lane_returns_no_reason_and_closes_the_client
1 failed, 69 passed in 4.40s
```

### CONCERN 3 — **a falha não é minha, é uma bomba-relógio de outro agente em voo**

`git status` mostra `services/strategy-worker/tests/test_replay_contract.py`,
`replay/run.py` e `replay/budget.py` **modificados e não commitados** (+42, +17, +19 linhas), e o
`git diff` mostra que a classe `TestRefuseDirectRun` inteira é dessas linhas novas — é a T3.74, de
outro agente. O teste fixa `ts = "2026-08-01T11:59:55+00:00"` e espera faixa saudável, **sem
congelar o relógio**: hoje é 2026-09-10, a diferença é 3 429 811 s ≈ 39,7 dias, e o portão de
`heartbeat_stale` recusa. **O teste passa perto de 2026-08-01 e falha para sempre depois disso.**
Eu **não toquei** no arquivo (árvore compartilhada). Fica registrado para o dono da T3.74.

**Nota importante para a validade desta nota:** `hunter-strategy-worker-1` roda a imagem
**`572d3b6`** (commitada). As modificações não commitadas de `run.py`/`budget.py` **não** estavam
dentro do container — nenhuma das 36 corridas usou código em voo.

**O que eu NÃO rodei, e por quê.** `services/strategy-worker/tests/test_replay_lookahead.py` — a
prova de que uma decisão replayada na barra `t` não lê vela que fecha depois de `t`, com o
contra-teste do motor que trapaceia de propósito — é `@pytest.mark.integration` e precisa de
Postgres por testcontainer, proibido pelo brief. Não foi tocado por esta tarefa.

A prova empírica que **esta** tarefa produz no lugar: as 12 fatias da `v10` do agente anterior e as
12 da `v2` minhas passam pelas mesmas 11 520 barras por fatia com `bars = lines` exato e
`unavailable` idêntico (1 280) nas três versões — o motor é determinístico sobre a mesma fita, e as
1 280 barras de aquecimento estão exatamente onde o `context_minutes = 1560` prevê.

---

## 10. VEREDITOS

| versão | veredito pelo funil | por quê |
|---|---|---|
| `mean_reversion v10` | **K3 disparado → depreciar** | 798 decisões, 89 dias, bruta `r_ex_funding` **−0,0293 R**, PF 0,910. A vantagem da T3.62 (+0,1105 R, PF 1,451) é a janela J3 inteira e só ela; J1 −0,1216 e J2 −0,0919, com Δ(J3−J1J2) = +0,2265 [+0,0085; +0,4293] excluindo zero. Custo dobrado sobre 90 d ≈ −0,1313 R |
| `mean_reversion v1` | **K3 disparado → depreciar** | 542 decisões, 83 dias, **−0,0910 R**, PF 0,851, o pior pedágio da família (0,2169 R p50). Piso de ATR 0,006 admite as barras em que o custo come o movimento — EXP-0019 confirmado por um terceiro caminho. Estresse: `frágil a custos` |
| `mean_reversion v2` | **K3 disparado → depreciar** | 302 decisões, 68 dias, **−0,0343 R**, PF 0,940. Estresse: `frágil a custos` (−0,0706 sob custo dobrado) |

**Qual versão deveria ser a linha de paper: nenhuma das três.** A `v10` continua sendo a melhor da
família por pedágio e a única com um regime em que funciona, mas "funciona num regime que eu não sei
detectar em tempo real" não é uma linha de paper — é uma hipótese para um portão de regime (que é
**versão nova**, `eligibility_policy` sobre `market_regimes`, não ajuste).

**Nenhuma versão foi promovida, depreciada ou ativada nesta tarefa.** Eu não escrevi nada em
`strategy_versions`; as depreciações acima são recomendação para o orquestrador, não ato.

---

## 11. AS 10 LINHAS PARA O EVERTON

> **`mean_reversion` em 90 dias — 1 644 operações. A resposta mudou.**
> 1. Rodei as versões `v10`, `v1` e `v2` em **90 dias × 16 mercados**: 1 644 operações, 36 corridas, **zero erro**. A fita está **100 % completa** nos três meses — sem um buraco.
> 2. **A resposta é não: a `v10` não se sustenta fora de agosto.** Em 90 dias ela dá **−0,03 R por operação** e PF **0,91**. Negativa.
> 3. **Agosto era a história inteira.** Junho–julho **−0,12 R**, julho–agosto **−0,09 R**, agosto–setembro **+0,12 R**. Os +0,11 R que eu te mostrei ontem eram esse último mês, e só ele.
> 4. **E isso não é sorte:** a diferença entre agosto e os dois meses anteriores é de **+0,23 R por operação**, com intervalo de confiança de **+0,01 a +0,43** — não passa por zero. As três versões mostram o mesmo.
> 5. A taxa de acerto conta a mesma história: **43 % → 46 % → 57 %**. A estratégia acerta mais em agosto porque agosto era o mercado dela, não porque ela é boa.
> 6. **A régua de morte do laboratório (K3) dispara nas três versões** — foi a primeira vez que ela pôde ser medida, porque ela exige 30 dias e antes só tínhamos 31 no total.
> 7. Ontem eu disse "a vantagem estava nos 4 mercados originais". Com 90 dias, **nem eles**: os 4 originais dão **0,00 R** na `v10`. Não há vantagem em grupo nenhum.
> 8. **Uma limitação que preciso declarar:** o banco só tem taxa de *funding* a partir de 08/08. Medi tudo pelo R **sem funding**, que existe em 100 % das operações — e onde dá para comparar, o funding pesa **0,001 R**, ou seja, nada. A conclusão não depende disso.
> 9. **Qual deveria ser a linha de paper: nenhuma das três.** Depreciar as três é o que a régua manda.
> 10. **O que sobra de valioso:** a `v10` funciona *num tipo de mercado*. O caminho não é ajustá-la — é construir um **portão de regime** que só a deixe operar nesse mercado, e isso é versão nova, medida do zero.

---

## 12. ASSUNÇÕES NUMÉRICAS QUE EU TIVE DE FAZER

1. **O eixo é `r_ex_funding`, não `r_multiple`.** Forçado pela ausência de `funding_rates` antes de
   2026-08-08 16:00 UTC (§3). Justificado por três coisas: K3 é definido nesse eixo
   (`SHADOW-LAB.md` linha 157); o arrasto medido do funding onde ele existe é −0,0011 R na `v10`
   (mediana 0,0000); e a cobertura é 100 %. **Risco residual:** um regime de funding radicalmente
   diferente em junho/julho ficaria invisível — teria de valer ~0,12 R/operação para virar o sinal.
2. **O corte das três janelas é de calendário**, `2026-06-12 / 2026-07-12 / 2026-08-11 / 2026-09-10`,
   por `emitted_at` em UTC — as mesmas fronteiras que o agente anterior usou no replay da `v10`, para
   que as populações e os recortes coincidam. J3 tem 30 dias, J2 tem 29 dias com decisão na `v10`.
   **"J3" é um recorte de calendário, não um rótulo de regime**; eu não cruzei com `market_regimes`.
3. **O bootstrap usa blocos de DIA inteiro, 20 000 reamostragens, semente 20260910.** O bloco é o dia
   porque decisões do mesmo dia em 16 mercados correlacionados dividem fita. Δ entre janelas é **não
   pareado** (não há dia em comum); Δ entre grupos de mercado é **pareado por dia** (dividem o
   calendário). Confundir os dois estreitaria o IC artificialmente — há teste para os dois casos.
4. **`r_bruto` = `(exit_base − p_entry/1,0006) / initial_risk`** e `pedágio = r_bruto − r_ex_funding`,
   idêntico à T3.62 q10 / T3.54 q10 / T3.47 q01 (KB-0076 com a correção da `notes-T3.40` §8b). O
   1,0006 é o slippage de entrada, desfeito. **Válido porque toda a população é `long`** — conferido:
   1 644 de 1 644 — e o pedágio sai positivo e limitado em todas (`v10`: 0,0250 a 0,2185 R).
5. **O custo dobrado sobre 90 d (§7.3) é de primeira ordem**: `r_exf_x2 = r_exf − pedágio`. Ela
   **subestima** o estrago, porque supõe que o caminho até a saída não muda quando o custo dobra.
   Serve para a ordem de grandeza. O número exato só sai de um `--stress` que saiba cair para
   `r_ex_funding`, que hoje ele não sabe (§7.2).
6. **O teto de C5 é 3 %** e o piso 0,3 %, lidos de `packages/risk-core/hunter_risk/limits.py:151-152`
   (banda `paper_v1`), não inventados.

---

## 13. O QUE EU DELIBERADAMENTE NÃO FIZ

- **Não refiz a `v10`.** A coorte `c7d138eb` é do agente anterior, íntegra (12/12, 0 erro), e é dela
  que sai toda a análise da `v10`.
- **Não matei o processo órfão** do agente anterior (§1). Esperei ele terminar as duas fatias que
  faltavam e só então comecei — para que nenhuma corrida minha dividisse a faixa de replay.
- **Não toquei em `stress.py`** apesar do CONCERN 2, nem em `test_replay_contract.py` apesar do
  CONCERN 3. Os dois são código de outra tarefa em voo numa árvore compartilhada.
- **Não criei nem alterei partição, nem pedi backfill de `funding_rates`.** Trazer o histórico de
  funding de junho/julho é o que fecharia K5 e é a única coisa que faria esta leitura subir de
  categoria. É decisão do orquestrador; o meu brief autoriza o CLI de replay e leitura.
- **Não cruzei com `market_regimes`.** É a próxima pergunta óbvia — "J3 é mesmo o regime lateral?" —
  e ela é barata, mas é outra tarefa.
- **Não depreciei nada** em `strategy_versions`. Depreciar é escrita por script auditado.
