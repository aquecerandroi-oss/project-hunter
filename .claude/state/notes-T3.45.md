# notes-T3.45 — a quarta vaga: contrato da candidata "varredura de mínima e recuperação" (sweep + reclaim)

**Data:** 2026-09-08 (UTC; Brasília = UTC−3). **Owner:** quant-engineer. **Base:** `main @ 2df9f67`.
**Sem código nesta tarefa. Nada commitado. Nada ativado. Nenhuma coorte criada. Nenhum container
tocado. Nenhum replay executado.** VPS **somente leitura** (uma transação `repeatable read read only`,
três execuções da mesma consulta enquanto eu a completava). **Nada tocado** em `.env*`, `apps/**`,
`services/**`, `packages/**`, `obsidian/**`.

---

## STATUS

**DONE_WITH_CONCERNS.** A pré-checagem **passou** — as quatro regras de morte estavam escritas antes
de rodar e nenhuma disparou —, então o brief de implementação foi escrito. Mas ela passou com margem
estreita e trouxe um achado que o dia um não pode ignorar.

| # | Entrega do brief T3.45 | Resultado |
|---|---|---|
| 1 | Contrato EXP-0017 (hipótese e protocolo congelados, geometria argumentada com a identidade do pedágio e tabela de equilíbrio, sem invalidação, parâmetros com faixas, K1–K5 + concentração) | **OK.** `exp-drafts/EXP-0017-sweep-reclaim.md` |
| 2 | Pré-checagem por SQL na VPS, com regra de morte escrita **antes** de rodar, saída colada | **OK.** `infra/scripts/sql/research/2026-09-09-sweep-reclaim-precheck.sql`, `read_at = 2026-09-08T21:59:07Z` |
| 3 | Portão C1–C8 preenchido no EXP, honesto, com as divergências declaradas | **OK.** `confidence_score = 70,5` → **`REVISE`** (há um `fail`: C8) |
| 4 | Brief de implementação, **só se a pré-checagem passar** | **OK, e passou.** `brief-T3.45b-sweep_reclaim_v1.md` |

**Resposta curta em três linhas.** A população **existe**: 57 eventos em 31 dias × 4 mercados, bem
distribuídos (o maior mercado tem 29,8 %), contra um piso de morte de 20. Mas ela vive em **17 dias
distintos de 31**, então **o replay de dia um está condenado a `inconclusivo` por construção** — a
régua de maturidade pede 30 dias distintos e eles não existem nesta janela. E a porta que mais corta
não é a hipótese: é a **porta de custo** (177 → 58, corte de 67 %), o que quer dizer que a varredura
mediana deste mercado **não paga o pedágio** e as 57 decisões são a minoria cara o bastante para
pagá-lo.

---

## CONTRATO (EXP-0017, resumo do que foi congelado)

Detalhe completo em `.claude/state/exp-drafts/EXP-0017-sweep-reclaim.md`. O que importa aqui:

- **Entrada:** numa barra de 15 min, a mínima **fura** a mínima de um pivô de swing **confirmado**
  (k = 3, proeminência ≥ 1 ATR, alcance de 40 barras) em ≥ 0,25 ATR, e o **fechamento volta acima**
  daquela mínima, com RVOL ≥ 1,5.
- **Escala:** ATR de Wilder(14) sobre 97 barras de 15 min, **uma leitura por decisão**, e é ela que
  escala proeminência, varredura, stop e risco. Divergência declarada contra `patterns/pivots.py`
  (lá cada pivô é escalado pelo ATR da própria barra).
- **Geometria:** `stop = low − 0,10 ATR`; `alvo1 = fechamento + 2 × risco`; alvo informativo 3 R.
  **Alvo em R, não em ATR** — é a lição congelada da `session_orb_v1`.
- **Invalidação: NENHUMA**, argumentada (KB-0006): a estrutura já está no stop; uma regra que sai
  acima do stop é um segundo stop sem tese, e é o desenho que custou ≈ −53 R à `momentum v2`.
- **Horizonte:** 4 h (16 barras).
- **A inovação de desenho, e o motivo dela.** Esta versão **não tem faixa de ATR%**. A porta de custo
  é `risk_pct_min = 0,006` — a distância até o stop em fração do preço, que é a grandeza que aparece
  na identidade do pedágio (`custo_R = 0,0020 / risco%`, KB-0076 com a correção da notes-T3.40 §8b).
  A `momentum v5` tentou comprar teto de pedágio com `atr_pct_min = 0,020` e **decidiu zero vezes**;
  aqui o stop é estrutural, então `risco%` é observável na barra e pode ser exigido direto.
  **Teto de pedágio declarado: 0,3333 R por operação** (o mesmo da `mean_reversion_v1`).

**Aritmética de geometria, reproduzida em `Decimal` nesta tarefa** (`a = 6 bps/lado` dentro dos
preços, `f = 4 bps/lado` fora):

```
$ uv run python <scratchpad>/geom_t345.py
== alvo 1,5R / 2R / 3R no piso de custo congelado (risco% = 0,006) ==
alvo 1.5R  risco% 0.600%  R_net alvo 1.0592  R_net stop -1.2112  equilibrio 0.5335  pedagio 0.3333
alvo 2R    risco% 0.600%  R_net alvo 1.5133  R_net stop -1.2112  equilibrio 0.4446  pedagio 0.3333
alvo 3R    risco% 0.600%  R_net alvo 2.4215  R_net stop -1.2112  equilibrio 0.3334  pedagio 0.3333

== teto de pedagio por piso de risco% (identidade custo_R = 0,0020 / risco%) ==
risco%_min   0.30%   teto de pedagio  0.6667 R
risco%_min   0.45%   teto de pedagio  0.4444 R
risco%_min   0.60%   teto de pedagio  0.3333 R
risco%_min   1.00%   teto de pedagio  0.2000 R
risco%_min   3.00%   teto de pedagio  0.0667 R

== comparacao com as versoes vivas (piso de cada uma) ==
             momentum_v1  risco%  0.450%   teto  0.4444 R
       mean_reversion_v1  risco%  0.600%   teto  0.3333 R
             breakout_v1  risco%  0.750%   teto  0.2667 R
  momentum v5 (T3.40 V1)  risco%  3.000%   teto  0.0667 R
```

**Verificação cruzada, e ela importa:** a linha `1,0 ATR / ATR% 0,006 / alvo 2R` desta tabela
(`1.5133 / −1.2112 / 0.4446`) é **dígito a dígito** a linha "risco da faixa 1,0" da tabela de
`session_orb_v1` em `notes-T3.33.md` §4. A minha implementação da fórmula de `R_net` reproduz uma
tabela publicada por outra tarefa; não é aritmética nova.

**Escolha do alvo:** 2R. 3R pediria uma perna de 1,2 % de preço em 4 h, e a `momentum v6` (T3.40) já
está medindo o eixo "alvo mais longe" com contraste pareado — repetir o eixo aqui seria gastar duas
execuções na mesma pergunta (KB-0010).

---

## PRÉ-CHECAGEM — SQL, regra de morte e saída real

**A regra de morte foi escrita antes**, no cabeçalho do arquivo
`infra/scripts/sql/research/2026-09-09-sweep-reclaim-precheck.sql` (linhas 9–17), e o arquivo existia
com ela antes da primeira execução:

```
P1  < 20 eventos sob a regra congelada INTEIRA  -> NÃO escrever o módulo (K1)
P2  > 1 500 eventos                             -> é relógio, não condição (K2)
P3  >= 60 % dos eventos num único mercado       -> não mata; obriga decomposição por mercado (K6)
P4  cobertura de barras de 15 min < 90 %        -> BUG DE DADO, não resultado de estratégia
```

**Como rodou** (somente leitura, primeiro plano, ~20 s):

```bash
ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter -v ON_ERROR_STOP=1 -f -" \
  < infra/scripts/sql/research/2026-09-09-sweep-reclaim-precheck.sql
```

```
BEGIN
+-------------------------------+--------+
|            read_at            |   db   |
+-------------------------------+--------+
| 2026-09-08 21:59:07.337335+00 | hunter |
+-------------------------------+--------+
```

### Q1 — cobertura e a distribuição de ATR% de Wilder (o CONCERN 2 da T3.33d, fechado aqui)

```
+----------+------------+---------------+---------+-------------+-------------+-------------+-------------+-----------------+-----------------+
|  symbol  | barras_15m | pct_da_janela | com_atr | atr_pct_p10 | atr_pct_p50 | atr_pct_p90 | atr_pct_max | pct_atr_ge_0006 | pct_atr_ge_0003 |
+----------+------------+---------------+---------+-------------+-------------+-------------+-------------+-----------------+-----------------+
| DOGEUSDT |       2961 |         99.50 |    2865 |    0.001737 |    0.004368 |    0.008536 |    0.035645 |           28.55 |           65.20 |
| ETHUSDT  |       2961 |         99.50 |    2865 |    0.001253 |    0.003091 |    0.006122 |    0.013310 |           10.68 |           51.52 |
| SOLUSDT  |       2961 |         99.50 |    2865 |    0.001995 |    0.004021 |    0.007686 |    0.025002 |           23.80 |           64.64 |
| XRPUSDT  |       2961 |         99.50 |    2865 |    0.001770 |    0.004139 |    0.010527 |    0.035930 |           32.88 |           63.00 |
+----------+------------+---------------+---------+-------------+-------------+-------------+-------------+-----------------+-----------------+
```

Três leituras, e duas delas ultrapassam esta candidata:

1. **P4 não dispara** (99,50 %). E `com_atr = 2 961 − 96` nos quatro: 96 é **exatamente** o
   aquecimento da janela de 97 barras, ou seja **zero** janelas perdidas por buraco interno. As 15
   barras que faltam nos 31 dias estão numa borda, não espalhadas.
2. **O CONCERN 2 da T3.33d fica respondido com número.** Um `atr_pct_min = 0,006` recusa **67 % a
   89 %** das barras destes mercados (ETHUSDT: só 10,68 % chegam lá). Até o piso de 0,003 da
   `momentum_v1` recusa 35 % a 48 %. **`breakout_v1` e `mean_reversion_v1` congelaram 0,006** — o
   piso delas morde muito mais do que se sabia quando foi congelado, e isso é um recado para as duas,
   não para esta.
3. `atr_pct_max` chega a **3,59 %** (XRPUSDT), bem acima do 1,62 % que a T3.40 mediu como máximo
   observado **nas decisões** da `momentum v2` — a diferença é que aquele número é condicionado às
   barras em que a `momentum` decide, e este é a distribuição inteira.

### Q2 — o funil da regra congelada, porta a porta

```
+----------+-------------------+----------+----------+-------------+-----------+-----------------+---------+-----------------+-----------------+
|  symbol  | barras_avaliaveis | com_pivo | varreram | recuperaram | mais_rvol | mais_piso_risco | eventos | dias_com_evento | pos_barreira_lb |
+----------+-------------------+----------+----------+-------------+-----------+-----------------+---------+-----------------+-----------------+
| DOGEUSDT |              2865 |     2851 |      387 |          80 |        35 |              15 |      15 |              11 |              12 |
| ETHUSDT  |              2865 |     2856 |      378 |          93 |        52 |               9 |       9 |               8 |               9 |
| SOLUSDT  |              2865 |     2855 |      425 |         102 |        46 |              16 |      16 |               7 |              10 |
| XRPUSDT  |              2865 |     2836 |      420 |          93 |        44 |              18 |      17 |              10 |              12 |
| ZTOTAL   |             11460 |    11398 |     1610 |         368 |       177 |              58 |      57 |              17 |              43 |
```

### Q3 — onde cai a porta de custo

```
+-----------------------------------+------+---------------+---------------+---------------+---------------+---------------+---------------+-------------+-------------------+
|              estagio              |  n   | risco_pct_p10 | risco_pct_p50 | risco_pct_p90 | risco_atr_p10 | risco_atr_p50 | risco_atr_p90 | pct_no_piso | pedagio_mediano_r |
+-----------------------------------+------+---------------+---------------+---------------+---------------+---------------+---------------+-------------+-------------------+
| A varreu                          | 1610 |       0.00063 |       0.00228 |       0.00744 |         0.213 |         0.640 |         1.356 |        15.4 |            0.8764 |
| B varreu+recuperou                |  368 |       0.00143 |       0.00372 |       0.01005 |         0.602 |         1.026 |         1.585 |        27.2 |            0.5381 |
| C varreu+recuperou+rvol           |  177 |       0.00159 |       0.00398 |       0.01210 |         0.722 |         1.206 |         1.984 |        32.8 |            0.5026 |
| D controle: varreu, NAO recuperou |  732 |       0.00065 |       0.00244 |       0.00752 |         0.215 |         0.659 |         1.445 |        17.1 |            0.8199 |
```

### Q4 — sensibilidade **diagnóstica** (o contrato já estava congelado; isto não escolheu nada)

```
+--------------------------------+---------+----------------+----------+----------------------+
|              nome              | eventos | dias_distintos | mercados | pct_do_maior_mercado |
+--------------------------------+---------+----------------+----------+----------------------+
| 0 CONGELADA 0,25 / 1,5 / 0,006 |      57 |             17 |        4 |                 29.8 |
| 1 sweep_atr 0,10               |      61 |             17 |        4 |                 31.1 |
| 2 sweep_atr 0,50               |      45 |             17 |        4 |                 28.9 |
| 3 sem RVOL                     |      99 |             18 |        4 |                 33.3 |
| 4 risk_pct_min 0,004           |      86 |             23 |        4 |                 31.4 |
| 5 risk_pct_min 0,003           |     112 |             25 |        4 |                 28.6 |
| 6 sem piso de custo            |     176 |             30 |        4 |                 29.5 |
+--------------------------------+---------+----------------+----------+----------------------+
```

### Veredito das regras de morte

| regra | limiar | leitura | disparou? |
|---|---|---|---|
| P1 | < 20 eventos | **57** (43 depois da barreira de re-arme, limite inferior) | **não** |
| P2 | > 1 500 | 57 | não |
| P3 | ≥ 60 % de um mercado | **29,8 %** (XRPUSDT); os quatro entre 9 e 17 | não |
| P4 | cobertura < 90 % | 99,50 % | não |

**Nenhuma disparou → o brief de implementação foi escrito.** O que a mesma tabela diz e que eu não
vou maquiar:

- **a cadência real é 0,046 evento por mercado-dia.** A estimativa da `notes-T3.33.md` §2 para esta
  candidata era **~0,3/mercado-dia**: errou por um fator de ~6. A coluna "freq./mercado-dia" daquela
  shortlist não vale nada sem consulta, e isso vale para as outras nove linhas dela também;
- **17 dias distintos de 31.** A régua de maturidade (100 avaliáveis **E** 30 dias distintos) é
  **inalcançável no replay**. O dia um serve para K1, K2, K4, K6 e para a guarda de geometria, e o
  resultado dele já nasce `inconclusivo`. Quem pode amadurecer esta versão é a coorte prospectiva;
- **a porta do pivô não é uma porta:** 99,46 % das barras têm um pivô confirmado nas 40 anteriores.
  Com k = 3, proeminência de 1 ATR e 10 h de alcance, quase sempre há um "suporte recente". O portão
  C2 contou 6 condições; ativas são 5;
- **o `risk_atr_max = 3` recusou exatamente 1 evento em 31 dias.** É guarda, não condição;
- **a porta que a hipótese depende corta bem:** só 368 de 1 610 varreduras (22,9 %) recuperam. O
  grupo de controle pré-registrado ("varreu, não recuperou, com RVOL") tem **732 barras**, 12,8× o
  grupo tratado — contraste largo e barato, e ele existe antes de a versão rodar;
- **e a porta que mais corta é a de custo:** 177 → 58 (67 %). O `risco%` mediano de uma varredura
  recuperada com volume é **0,398 %**, isto é **0,50 R de pedágio**. Traduzindo: **a varredura típica
  destes mercados não paga a operação**, e o que a estratégia faz é escolher a minoria que paga.

---

## PORTÃO C1–C8 (`edge-strategy-reviewer`), aplicado antes do módulo

| C1 | C2 | C3 | C4 | C5 | C6 | C7 | C8 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 80 | **50** | 80 | 80 | 80 | 80 | 80 | **10** |

`confidence_score = 70,5` → **`REVISE`**. Não é `REJECT` (C1 e C2 não são `fail`); **não é `PASS`
apesar de 70,5 ≥ 70**, porque a regra 3 exige "≥ 70 **e** nenhum `fail`", e C8 é `fail`.

- **C8 = 10 — `invalidations = ()`. Recusado, e é o desenho.** Sem esse `fail` o escore seria 74,0 e
  o veredito `PASS`. Divergência declarada, não conserto.
- **C2 = 50** — três limiares com casa decimal nas condições (`0,25`, `1,5`, `0,006`). Aceito como
  custo: dois são convenções herdadas de versões existentes e o terceiro é derivado da identidade do
  pedágio. Arredondá-los para agradar ao portão seria ajustar o contrato à régua.
- **C4 = 80** — o plano de validação **menciona regime** (decomposição por regime de BTC obrigatória
  na primeira avaliação). É a correção do que a `derivatives_v1` só prometeu (C4 = 40 lá).
- **C7 = 80** — há filtro de volume (`rvol_min`), ao contrário da `derivatives_v1` (C7 = 50).
- **O portão errou de novo no C3, e desta vez dá para mostrar:** ele estimou ~66 oportunidades/ano
  pela fórmula de barra diária em ações; a medida é **~14/ano por mercado**. Erro de 4×. Na
  `derivatives_v1` ele errou para o infinito (deu 80 sobre uma população inexistente). **O C1–C8
  pontua a forma do rascunho e não substitui a consulta ao dado** — por isso a pré-checagem é o
  portão que decide.

---

## TESTES — saída real

Nenhum teste novo (não há código nesta tarefa). O que rodei é a prova de que a árvore continua
intacta e de que nenhum `code_ref` se moveu por minha mão:

```
$ uv run pytest packages/core/tests/unit/strategies services/strategy-worker/tests/test_code_ref.py -q
........................................................................ [ 14%]
........................................................................ [ 29%]
........................................................................ [ 44%]
........................................................................ [ 58%]
........................................................................ [ 73%]
........................................................................ [ 88%]
.........................................................                [100%]
489 passed in 50.44s

$ uv run python -c "from hunter_strategy_worker.code_ref import version_code_ref; ..."
momentum_v1              = hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c
volume_anomaly_v1        = hunter_core.strategies.volume_anomaly_v1@sha256:9b8c14ab3390646ac9adb26fbbb90e160a800f1c70f128d873a49ffd1dd19f22
breakout_v1              = hunter_core.strategies.breakout_v1@sha256:4c920b0cc412429c2c4a6a19ca389aca8a215a638f0ff750a8caf61b16264ff1
mean_reversion_v1        = hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f
session_orb_v1           = hunter_core.strategies.session_orb_v1@sha256:a4d514adeb0771d5ae23303878fb4fdac734721d6ac0140801c88d617e878bba
trendline_breakout_v1    = hunter_core.strategies.trendline_breakout_v1@sha256:659087e19daa6f8d5bc71f4c64d47ea4026f720bcd1576d8a0b620b448aef449
```

Os quatro primeiros são **idênticos** aos publicados pela `notes-T3.33d.md` — os irmãos do fecho não
foram tocados por ninguém desde então.

---

## FILES

| arquivo | o quê |
|---|---|
| `C:\dev\project-hunter\.claude\state\exp-drafts\EXP-0017-sweep-reclaim.md` | **novo** — contrato congelado, geometria, teto de pedágio, K1–K6, portão C1–C8, avaliação datada da pré-checagem |
| `C:\dev\project-hunter\infra\scripts\sql\research\2026-09-09-sweep-reclaim-precheck.sql` | **novo** — a pré-checagem, com P1–P4 no cabeçalho, escritas antes de rodar |
| `C:\dev\project-hunter\.claude\state\brief-T3.45b-sweep_reclaim_v1.md` | **novo** — brief de implementação (módulo, regra por motivo, parâmetros, `constraints`, envelope, 13 grupos de teste, arquivos, sequência de replay) |
| `C:\dev\project-hunter\.claude\state\notes-T3.45.md` | este arquivo |

**Não criados, de propósito:** `packages/core/hunter_core/strategies/sweep_reclaim_v1.py` e o teste
dele — o brief T3.45 diz "sem código nesta tarefa", e o próximo passo é a T3.45b.

**Não tocados:** `packages/**`, `services/**`, `apps/**`, `obsidian/**`, `.env*`,
`infra/scripts/seed_reference.py`, `registry.py`, `constraints_table.py`. As linhas modificadas
nessas pastas em `git status` **já estavam lá** (T3.34b/trendline e a faixa de tempo real em voo) e
**não são minhas** — confirmei que os quatro digests publicados pela T3.33d não se moveram.

---

## CONCERNS

1. **A margem de K1 é estreita e o número que eu publico é o teto, não o piso.** 57 eventos contra um
   piso de 20; depois da barreira de re-arme do slot (horizonte de 4 h = 16 barras), o limite
   inferior é **43**. A conta da barreira ancora no evento **anterior**, não no aceito, então a
   gulosa real fica entre 43 e 57. Se o replay devolver menos de 20, K1 dispara e a candidata morre —
   e nesse caso a diferença entre o SQL e o motor tem de ser **nomeada**, não arredondada.

2. **17 dias distintos: o dia um não pode amadurecer, e isso não é um detalhe.** Toda leitura do
   replay sai `inconclusivo` pela régua (100 avaliáveis **E** 30 dias). O valor do replay aqui é
   **operacional** (K1, K2, K4, K6, guarda de geometria, cobertura), não estatístico. Se o operador
   quiser evidência, o caminho é a coorte prospectiva, e ela leva ~2 meses nesta cadência para 100
   desfechos com quatro mercados. **Alargar o universo é a alavanca real** — e é uma decisão dele.

3. **Assunção numérica declarada: o ATR do SQL é `float8`, o do motor é `Decimal` de 28 dígitos.**
   Usei a forma fechada equivalente à recursão de Wilder (semente = média dos 14 primeiros TRs da
   janela de 97, mais 82 passos de suavização, peso residual da semente ≈ 0,23 %). Perto de um
   limiar, uma barra pode cair do outro lado. Em 11 460 barras isso muda contagens em unidades, não
   em ordem de grandeza — mas o replay é a medida, não esta consulta.

4. **Assunção numérica declarada: `sweep_atr = 0,25`, `rvol_min = 1,5` e `stop_buffer_atr = 0,10` são
   convenções**, não medições. As duas primeiras são herdadas de versões existentes justamente para
   não inventar eixo novo; a terceira é a menor folga que ainda tira o stop do tick exato do extremo.
   A Q4 mostra que `sweep_atr` quase não muda a população (61 / 57 / 45 entre 0,10 e 0,50), o que é
   uma boa notícia para a robustez e uma má notícia para quem quiser explicar a população por ela.

5. **`risk_pct_min = 0,006` é o parâmetro que decide esta candidata, e a tentação de baixá-lo tem de
   ser recusada por escrito — está no EXP e no brief.** A Q4 mostra 176 eventos e 30 dias distintos
   com o piso desligado, isto é, **a maturidade estatística está à venda por 0,88 R de pedágio
   mediano**. Comprá-la seria fabricar exatamente a perda que a KB-0076 diagnosticou. Quem quiser
   testar um piso menor abre EXP novo, com portão e contraste pareado.

6. **O grupo tratado e o de controle não têm a mesma geometria.** Recuperar obriga o fechamento a
   estar longe da mínima, então o grupo tratado tem `risco%` mediano maior (0,372 % contra 0,244 %).
   Qualquer comparação de `R` entre os dois mistura "a recuperação prevê" com "o risco é outro". O
   dia um tem de comparar `R` normalizado **e** declarar a confusão; sem isso o contraste vira o
   mesmo tipo de atribuição contábil que a KB-0006 proibiu.

7. **A objeção original da T3.33 (sobreposição com a `mean_reversion_v1`) continua não resolvida por
   argumento.** Escrevi por que as populações deveriam ser diferentes (esta não exige tendência de
   alta em 1 h e exige estrutura confirmada), mas **isso é hipótese, não medição**. A interseção por
   `(mercado, barra)` com a coorte da `mean_reversion` está pré-registrada como obrigação do dia um.

8. **`is_monitored` e o universo são os de hoje**, não os da janela (PIPELINE §6c). Vale igualmente
   para qualquer coorte que venha, então não enviesa comparações — mas nenhum número aqui descreve o
   universo de agosto.

9. **Multiplicidade.** Esta é a quinta versão de pesquisa aberta na mesma semana (KB-0010). O
   `Registro de Tentativas` precisa da linha, e a régua de maturidade não pode ser relaxada porque
   "já esperamos muito".

10. **Nada foi ativado, e não ative sem o módulo.** A linha `sweep_reclaim` **nem existe** no
    catálogo da VPS ainda (é família nova, e `seed.py` precisa rodar antes). Ativar congela
    `code_ref` e é irreversível; hoje não há módulo para congelar.

---

## O QUE EU FARIA A SEGUIR

1. **Executar a T3.45b** (módulo + testes), com o teste de confirmação de pivô (`k`) como o teste
   central de não-antecipação: é o único lugar onde um vazamento poderia se esconder nesta versão.
2. **Rodar o dia um sabendo o que ele é**: um teste do módulo contra a previsão da pré-checagem
   (57 / 17 / 29,8 % / 0 rejeições de geometria), não uma medida de edge.
3. **Decidir o universo antes da prospectiva.** Com quatro mercados, 100 desfechos levam ~2 meses.
   Essa é a conversa que vale ter com o Everton **antes** de ativar, não depois.
4. **E uma coisa que ultrapassa esta tarefa:** a Q1 mostra que `atr_pct_min = 0,006` recusa 67–89 %
   das barras de ETH/SOL/XRP/DOGE. `breakout_v1` e `mean_reversion_v1` carregam esse piso. Vale medir
   quanto dele explica a população magra das duas **antes** de gastar mais corridas com elas — é o
   CONCERN 2 da T3.33d, agora com o número que faltava.
