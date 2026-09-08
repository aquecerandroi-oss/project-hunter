# notes-T3.32 — por que as estratégias perdem (diagnóstico com dado real da VPS)

**Data:** 2026-09-08 · **Owner:** quant-engineer · **Base:** `main @ 970c20b`
**Corte dos dados (`as_of`):** `agent_signals.emitted_at < 2026-09-08T15:00:00Z`
**Leitura do banco (`read_at`):** 2026-09-08T15:47Z, as nove consultas numa **única transação**
`begin transaction isolation level repeatable read read only` — um snapshot para todas as tabelas.
**Replays (`read_at`):** 2026-09-08T15:11Z–15:15Z.

## STATUS

**DONE_WITH_CONCERNS.** Os seis itens do brief foram entregues com dado real da VPS. A concern
principal é de escopo: para rodar o item 3 sobre a população que o brief nomeia foi preciso
acrescentar dois seletores a `infra/scripts/replay_exits.py` (`--only-version`, `--cohort`), o que
não é literalmente "um parâmetro de braço de saída que não existia" — está detalhado em CONCERNS.
Nada foi commitado. **Nenhuma coorte nova foi criada** (as quatro corridas de replay abrem a
transação `READ ONLY`; o script `replay_exits.py` não escreve). **Nenhum `UPDATE`/`INSERT`/`DELETE`
foi executado na VPS.** Nenhum container foi parado, recriado ou alterado — o script modificado foi
copiado para `/tmp` **dentro** do container e executado de lá; a imagem e o `/app` continuam
intactos.

## FILES

Escritos (todos dentro do escopo do brief, exceto o item marcado):

| arquivo | o quê |
|---|---|
| `C:\dev\project-hunter\infra\scripts\sql\research\2026-09-08-00-base.sql` | o bloco comum e a álgebra da decomposição do R (documentação do método) |
| `C:\dev\project-hunter\infra\scripts\sql\research\2026-09-08-01-por-motivo-de-saida.sql` | item 1 — por motivo de saída |
| `C:\dev\project-hunter\infra\scripts\sql\research\2026-09-08-02-por-mercado.sql` | item 1 — 10 piores / 10 melhores mercados |
| `C:\dev\project-hunter\infra\scripts\sql\research\2026-09-08-03-custo-vs-edge.sql` | **item 2 — a tabela que responde o brief** |
| `C:\dev\project-hunter\infra\scripts\sql\research\2026-09-08-04-invalidacao-e-excursoes.sql` | itens 3 e 4 — KB-0006 reproduzida + MFE/MAE |
| `C:\dev\project-hunter\infra\scripts\sql\research\2026-09-08-05-decis-de-atr.sql` | item 1 — decil de ATR% |
| `C:\dev\project-hunter\infra\scripts\sql\research\2026-09-08-06-hora-e-dia.sql` | item 1 — hora de Brasília e dia |
| `C:\dev\project-hunter\infra\scripts\sql\research\2026-09-08-07-regime-btc.sql` | item 5 — regime |
| `C:\dev\project-hunter\infra\scripts\sql\research\2026-09-08-08-piso-de-risco.sql` | item 6 — contrafactual do piso (dentro da amostra) |
| `C:\dev\project-hunter\infra\scripts\sql\research\2026-09-08-09-identidade-do-custo.sql` | a identidade do custo + dinheiro por operação + censurados |
| `C:\dev\project-hunter\.claude\state\exp-drafts\KB-0076-por-que-perdemos-2026-09-08.md` | item 7 — página de conhecimento |
| `C:\dev\project-hunter\.claude\state\exp-drafts\EXP-0007-momentum-invalidacao-bracos-INV.md` | item 7 — o EXP dos braços (nome em ASCII) |
| `C:\dev\project-hunter\.claude\state\exp-drafts\t332-replay\*.md`, `*.json`, `t332-sql-transcript.txt` | recibos verbatim das 4 corridas + transcrição das 9 consultas |
| `C:\dev\project-hunter\.claude\state\notes-T3.32.md` | este arquivo |
| **`C:\dev\project-hunter\infra\scripts\replay_exits.py`** | **fora da letra do escopo** — `--only-version` e `--cohort` (ver CONCERNS) |
| `C:\dev\project-hunter\infra\scripts\tests\test_replay_exits_population.py` | 8 testes dos seletores novos |

Não tocados, confirmado por `git status --porcelain`: `.env*`, `apps/**`,
`services/execution-worker/**`, `services/strategy-worker/**`, `packages/**`, `obsidian/**`.
(As modificações que aparecem em `services/execution-worker`, `services/market-worker`,
`tests/integration`, `docs/DESIGN.md` e `docs/PIPELINE.md` já estavam na árvore — são da T3.29 e
companhia, não minhas.)

## COMANDOS E SAÍDA REAL

### Testes e linters (locais)

```
$ uv run pytest infra/scripts/tests/test_replay_exits_population.py -q
........                                                                 [100%]
8 passed in 3.46s

$ uv run ruff check infra/scripts/replay_exits.py infra/scripts/tests/test_replay_exits_population.py
All checks passed!

$ uv run ruff format infra/scripts/replay_exits.py infra/scripts/tests/test_replay_exits_population.py
2 files reformatted

$ uv run pyright infra/scripts/replay_exits.py
0 errors, 0 warnings, 0 informations

$ uv run python infra/scripts/check_file_size.py
error   365 > 350  services/execution-worker/hunter_execution_worker/bridge.py
scanned 532 files; 1 over budget, 0 grandfathered
```

O único arquivo acima do orçamento é `bridge.py`, da T3.29 em voo — não meu.
Meus arquivos: `replay_exits.py` 308 linhas, o teste 145.

### Replays de política de saída (VPS, dentro do container, READ ONLY)

```
$ ssh hunter-vps 'docker exec hunter-strategy-worker-1 sha256sum /app/infra/scripts/replay_exits.py'
64d7e93736cbdd3961289462f8ba76d5fae879ec794d04fcd3b0b9ddb42db3f5  /app/infra/scripts/replay_exits.py
$ sha256sum infra/scripts/replay_exits.py     # antes da minha mudança: idêntico
64d7e93736cbdd3961289462f8ba76d5fae879ec794d04fcd3b0b9ddb42db3f5

$ scp infra/scripts/replay_exits.py hunter-vps:/tmp/replay_exits_t332.py
$ ssh hunter-vps 'docker cp /tmp/replay_exits_t332.py hunter-strategy-worker-1:/tmp/... && docker exec ... sha256sum'
db4877d095a0d15e2d4b43a0651e9ac62fed27c0cbbc48cd51464db175c9e626  /tmp/replay_exits_t332.py
$ sha256sum infra/scripts/replay_exits.py     # o que rodou = o que está no repositório
db4877d095a0d15e2d4b43a0651e9ac62fed27c0cbbc48cd51464db175c9e626
```

```
$ docker exec hunter-strategy-worker-1 sh -c 'cd /app && python /tmp/replay_exits_t332.py \
    --database-url "$DATABASE_URL" --versions momentum --only-version momentum_v2 \
    --cohort replay:f8d8279c-1fba-42ae-95ef-202042f96c60 --as-of 2026-09-08T04:00:00Z \
    --out /tmp/t332-momentum-v2.md'
Tue Sep  8 15:11:53 UTC 2026
2026-09-08 15:12:06 [info ] replay_collected  cases=224 comparable=224 reproduced=224
2026-09-08 15:12:06 [info ] replay_written    json=/tmp/t332-momentum-v2.json out=/tmp/t332-momentum-v2.md
Tue Sep  8 15:12:06 UTC 2026            # 13 s
```

As outras três corridas (mesma forma): `volume_anomaly_v2` / `replay:bac27c12-…` (341 casos, 12 s),
`momentum_v2` / `prospective` (210, 12 s) e `momentum_v1` / `prospective` (963, 45 s).
**Coortes criadas: nenhuma.** Recibos por corrida:

| # | população | `input_digest` | `series_digest` | portão passo 1 |
|---|---|---|---|---|
| P1 | momentum v2 · `replay:f8d8279c-1fba-42ae-95ef-202042f96c60` | `6000867c3df37418` | `3bd45752b9f8bc3d` | 224/224 = 1,0000 |
| P2 | volume_anomaly v2 · `replay:bac27c12-7e50-4dfa-9eee-35fccc4012d7` | `0273c35e2cfb91db` | `e9fa4d96e48b6424` | 341/341 = 1,0000 |
| P3 | momentum v2 · `prospective` | `70b5ee97a59a5bda` | `128d3b1119e36c70` | 202/202 = 1,0000 |
| P4 | momentum v1 · `prospective` | `98a1ffd048090c69` | `dfeb03c4200a41e8` | 915/948 = 0,9652 (trajetória 1,0000; as 33 divergências são só de funding) |

## SQL / TABELAS COM SAÍDA REAL

Transcrição completa e verbatim das nove consultas:
`C:\dev\project-hunter\.claude\state\exp-drafts\t332-replay\t332-sql-transcript.txt`.

### Item 2 — a tabela que responde o brief (`2026-09-08-03-custo-vs-edge.sql`)

```
+-------------------+-----------------+------+-------------+---------+-----------+---------------+---------+------------+------------+------------+----------+---------------------+-------------------------+
|      version      |     coorte      |  n   | exp_bruta_r | custo_r | funding_r | exp_liquida_r | soma_r  | usdt_48_33 | acerto_pct | pf_liquido | pf_bruto | risco_pct_preco_med | risco_pct_preco_mediana |
+-------------------+-----------------+------+-------------+---------+-----------+---------------+---------+------------+------------+------------+----------+---------------------+-------------------------+
| momentum v1       | prospective     |  929 |     -0.0399 |  0.1506 |   0.00005 |       -0.1905 | -176.94 |   -8551.30 |       37.8 |      0.613 |    0.900 |               1.793 |                   1.401 |
| momentum v2       | prospective     |  195 |     -0.0166 |  0.1457 |   0.00048 |       -0.1628 |  -31.75 |   -1534.39 |       37.4 |      0.675 |    0.959 |               1.836 |                   1.436 |
| momentum v2       | replay:7598d6c4 |   23 |     -0.2816 |  0.3248 |   0.00000 |       -0.6064 |  -13.95 |    -674.09 |       30.4 |      0.197 |    0.455 |               0.669 |                   0.659 |
| momentum v2       | replay:f8d8279c |  222 |      0.0811 |  0.2524 |   0.00038 |       -0.1717 |  -38.13 |   -1842.64 |       40.5 |      0.645 |    1.241 |               0.931 |                   0.788 |
| momentum v3       | prospective     |  176 |     -0.0392 |  0.1461 |   0.00053 |       -0.1859 |  -32.72 |   -1581.39 |       35.8 |      0.635 |    0.906 |               1.770 |                   1.429 |
| momentum v4       | prospective     |   25 |      0.1687 |  0.1065 |   0.00000 |        0.0622 |    1.55 |      75.13 |       48.0 |      1.176 |    1.547 |               2.143 |                   1.863 |
| momentum v4       | replay:d9f7a1f8 |   30 |     -0.0185 |  0.1315 |   0.00062 |       -0.1506 |   -4.52 |    -218.38 |       36.7 |      0.722 |    0.960 |               1.675 |                   1.647 |
| volume_anomaly v1 | prospective     | 2079 |      0.0094 |  0.3397 |  -0.00022 |       -0.3301 | -686.21 |  -33164.75 |       26.6 |      0.534 |    1.021 |               1.157 |                   0.904 |
| volume_anomaly v2 | prospective     |  456 |      0.0886 |  0.3185 |   0.00034 |       -0.2302 | -104.98 |   -5073.76 |       33.3 |      0.637 |    1.218 |               1.197 |                   0.867 |
| volume_anomaly v2 | replay:bac27c12 |  337 |      0.0197 |  0.6152 |   0.00027 |       -0.5957 | -200.76 |   -9702.89 |       29.4 |      0.280 |    1.054 |               0.552 |                   0.406 |
+-------------------+-----------------+------+-------------+---------+-----------+---------------+---------+------------+------------+------------+----------+---------------------+-------------------------+
```

**Resposta ao item 2, literal:** a expectancy **bruta** é ≈ 0 em todas as populações (PF bruto entre
0,90 e 1,24 onde n ≥ 175) e o custo vale 0,11–0,62 R. Portanto **não é "bruto positivo comido pelos
custos"** e **não é "só custo"**: é **as duas coisas** — não há edge mensurável **e** existe um
custo determinístico que a torna irrecuperável. A [[KB-0008]] fica confirmada com número próprio.

### A identidade do custo (`2026-09-08-09-identidade-do-custo.sql`)

```
+-------------------+-----------------+------+---------------------+-----------+-------------+-------------------+-----------------------+----------------------+
|      version      |     coorte      |  n   | custo_r_x_risco_pct |  desvio   | custo_r_med | custo_usdt_por_op | resultado_usdt_por_op | resultado_usdt_total |
+-------------------+-----------------+------+---------------------+-----------+-------------+-------------------+-----------------------+----------------------+
| momentum v1       | prospective     |  929 |            0.002000 | 0.0000166 |      0.1506 |              7.28 |                 -9.20 |             -8551.30 |
| momentum v2       | prospective     |  195 |            0.002000 | 0.0000188 |      0.1457 |              7.04 |                 -7.87 |             -1534.39 |
| momentum v2       | replay:f8d8279c |  222 |            0.002000 | 0.0000081 |      0.2524 |             12.20 |                 -8.30 |             -1842.64 |
| momentum v3       | prospective     |  176 |            0.001999 | 0.0000175 |      0.1461 |              7.06 |                 -8.99 |             -1581.39 |
| momentum v4       | prospective     |   25 |            0.001999 | 0.0000187 |      0.1065 |              5.15 |                  3.01 |                75.13 |
| momentum v4       | replay:d9f7a1f8 |   30 |            0.001998 | 0.0000149 |      0.1315 |              6.35 |                 -7.28 |              -218.38 |
| volume_anomaly v1 | prospective     | 2079 |            0.002000 | 0.0000141 |      0.3397 |             16.42 |                -15.95 |            -33164.75 |
| volume_anomaly v2 | prospective     |  456 |            0.002001 | 0.0000154 |      0.3185 |             15.39 |                -11.13 |             -5073.76 |
| volume_anomaly v2 | replay:bac27c12 |  337 |            0.002000 | 0.0000060 |      0.6152 |             29.73 |                -28.79 |             -9702.89 |
+-------------------+-----------------+------+---------------------+-----------+-------------+-------------------+-----------------------+----------------------+
```

`custo_R × risco%` = **0,0020 constante** (desvio ≤ 1,9×10⁻⁵) nas dez populações. Isto **não é
estatística, é aritmética**: 20 bps de ida e volta divididos pela distância ao stop. E o `−9,20` /
`−15,95` por operação bate **exatamente** com o que a página do Lab mostra ao Everton — a
reconstrução fecha com a fonte.

### Item 1 — por motivo de saída (recorte de `2026-09-08-01`)

```
| momentum v2       | replay:f8d8279c | stop                |  45 | 20.1 |     45 |   -1.1883 |     -53.47 |     -0.9190 |      0.2692 |       0.00011 |          40 |
| momentum v2       | replay:f8d8279c | invalidated         |  82 | 36.6 |     81 |   -0.6462 |     -52.34 |     -0.3956 |      0.2478 |       0.00047 |          27 |
| momentum v2       | replay:f8d8279c | horizonte(timeout)  |   6 |  2.7 |      6 |   -0.1176 |      -0.71 |      0.1530 |      0.2661 |       0.00450 |         240 |
| momentum v2       | replay:f8d8279c | target              |  91 | 40.6 |     90 |    0.7599 |      68.39 |      1.0027 |      0.2477 |       0.00017 |          43 |
| volume_anomaly v2 | replay:bac27c12 | invalidated         | 146 | 42.8 |    146 |   -1.0104 |    -147.53 |     -0.4289 |      0.5810 |       0.00055 |          20 |
| volume_anomaly v2 | replay:bac27c12 | stop                |  77 | 22.6 |     77 |   -1.6151 |    -124.37 |     -0.7361 |      0.8789 |       0.00016 |          17 |
| volume_anomaly v2 | replay:bac27c12 | horizonte(timeout)  |  15 |  4.4 |     15 |   -0.1060 |      -1.59 |      0.2900 |      0.3971 |      -0.00113 |         120 |
| volume_anomaly v2 | replay:bac27c12 | target              |  99 | 29.0 |     99 |    0.7345 |      72.72 |      1.2284 |      0.4937 |       0.00016 |          26 |
```

**As duas células que explicam a maior parte da perda:** `stop` e `invalidação` (−105,81 R em
`momentum`, −271,90 R em `volume_anomaly`). Repare na coluna bruta: um `stop` da `volume_anomaly`
perde **−0,74 R brutos** e é debitado **−1,62 R líquidos**. `censored` = **0** em toda a base;
`no_entry` ≤ 3,3 %.

### Item 1 — mercado, hora, dia, decil (resumo; tabelas completas na transcrição)

- **Mercado** (`-02`): na coorte de replay da `volume_anomaly`, ETHUSDT tem risco inicial de
  **0,232 % do preço** → **custo 1,138 R por operação**, bruto +0,014 R, líquido **−1,124 R** em 36
  operações. Na prospectiva, `XAUTUSDT` (risco 0,115 %) custa **1,83 R** e `TRXUSDT` (0,155 %)
  custa **1,44 R**. O ranking de "piores mercados" é, com uma exceção, o ranking de **stop mais
  apertado** — não o de pior previsão.
- **Hora de Brasília** (`-06`): `volume_anomaly v2 / replay` é negativa em **24 das 24 horas**.
- **Dia** (`-06`): `volume_anomaly` perde em **25 dos 28 dias**; `momentum` em 21 de 24.
- **Decil de ATR%** (`-05`): os 5 decis de menor ATR da `volume_anomaly / replay` somam **−155,75 R
  de −200,76 R (78 %)**; os 5 menores da `momentum v2 / prospective` somam **−32,56 R** — mais que a
  perda inteira (−31,75 R).

### Item 3 — invalidação: KB-0006 reproduzida, e o remédio testado

Descritivo (`-04`): a invalidação encerra 26–43 % dos desfechos com **0 ganhadores** em
`momentum v2/v3/v4` e `volume_anomaly v2` (6 em 341 na `momentum v1`); MFE médio na hora da morte
0,19–0,46 R.

Braços (EXP-0007), **Δ contra a base, em R, pareado por sinal**:

| contraste | P1 replay mom v2 (222 pares, 24 blocos) | P2 replay va v2 (337, 29) | P3 prosp mom v2 (141, 1) | P4 prosp mom v1 (932, 3) |
|---|---:|---:|---:|---:|
| INV-B − base (sem invalidação) | −0,0062 | +0,0316 | −0,0697 | −0,0382 |
| INV-C − base (dois fechamentos) | +0,0065 | +0,0253 | −0,0468 | −0,0313 |
| INV-E − base (buffer 0,25 ATR) | +0,0198 | +0,0014 | −0,0619 | −0,0091 |
| TGT-3 − base | +0,1036 | sem pares | +0,0082 | −0,0184 |
| TGT-4.5 − base | +0,1136 | sem pares | −0,1380 | −0,0125 |
| **EXIT-NOTGT − base** | **+0,1635** | +0,1654 | **−0,2255** | **−0,1020** |
| EXIT-CHAN − EXIT-NOTGT | −0,0133 | +0,0153 | +0,0036 | +0,0107 |

**Nenhum contraste rejeita** (Holm ≥ 0,83 em todos). Os três braços INV ficam abaixo do efeito
mínimo de 0,05 R e **trocam de sinal** entre populações. O único Δ grande (`EXIT-NOTGT`) é
**+0,163 R no replay e −0,226 R / −0,102 R nas prospectivas**, com o IC de blocos da P4 inteiramente
negativo. Em P1 o braço `EXIT-NOTGT` levaria a expectancy de −0,1717 para **−0,0054 R** (PF 0,645 →
0,991) — e é justamente esse o número que **não** se reproduz na população viva.

**Consequência formal:** o item 0 do brief T3.27 dizia "se os três contrastes forem indistinguíveis
de zero nessa população, a versão de código não vale a tentativa". **São.** Recomendo **não**
escrever `momentum_v2` com `invalidation_mode`.

### Item 4 — geometria (`-04`)

| população | lado | n | MFE p50 | p60 | p75 | p90 | MAE p50 | p75 | p90 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| mom v2 prosp | ganhador | 74 | 0,775 | 0,872 | 0,964 | 1,197 | 0,233 | 0,485 | 0,612 |
| mom v2 prosp | perdedor | 121 | 0,214 | 0,332 | 0,441 | 0,718 | 0,773 | 0,905 | 0,957 |
| mom v2 replay | ganhador | 92 | 0,691 | 0,776 | 0,944 | 1,234 | 0,266 | 0,498 | 0,680 |
| mom v2 replay | perdedor | 130 | 0,121 | 0,177 | 0,300 | 0,568 | 0,737 | 0,899 | 0,952 |
| va v2 replay | ganhador | 94 | 0,927 | 1,088 | 1,254 | 1,797 | 0,347 | 0,499 | 0,668 |
| va v2 replay | perdedor | 243 | 0,125 | 0,232 | 0,431 | 0,887 | 0,732 | 0,843 | 0,912 |

- **Que múltiplo de alvo o MFE sustenta?** O p60 do MFE dos ganhadores é **0,78–0,87 R** na
  `momentum` (alvo atual ≈ 1,0 R de bruto) e **1,09 R** na `volume_anomaly`. Não há cauda direita
  grossa nesta janela: o p90 dos ganhadores da `momentum` é 1,20–1,23 R. Ou seja, **o alvo de 1,5
  ATR não está cortando um lucro grande** — o que o braço TGT-3/TGT-4.5 mostra em P1 (+0,10 R) é a
  cauda de poucas operações, e ela some em P3/P4.
- **Que stop o MAE dos ganhadores pede?** p75 = 0,48–0,50 R e p90 = 0,61–0,68 R nas três
  populações: **um stop 30–35 % mais curto sobreviveria a 3 em cada 4 ganhadores**. Isso é
  interessante e perigoso ao mesmo tempo: encurtar o stop **aumenta** o custo em R na mesma
  proporção (identidade acima), então só serve acompanhado de um alvo proporcionalmente menor —
  e o custo continua sendo pago duas vezes.
  **Advertência:** `meta.excursions.mfe_complete_bars` é uma leitura **conservadora** (barras
  completas; a barra da saída pode ficar de fora quando o extremo é ambíguo). Os percentis acima
  são portanto **limites inferiores**, e o `bounds` em `meta.excursions` guarda o intervalo honesto.

### Item 5 — regime (`-07`)

```
== 7a. o que market_regimes tem ==
| regime  | n |              de               |              ate              |
| UNKNOWN | 1 | 2026-09-06 18:18:05.716851+00 | 2026-09-06 18:18:05.716851+00 |
| regimes_distintos_referenciados | sinais_com_regime | sinais_total |
|                               1 |              3040 |         5330 |
```

**O classificador de regime do `PIPELINE` §4 nunca produziu série.** Existe **uma** linha,
`UNKNOWN`, e os 3 040 sinais com `regime_id` apontam todos para ela. Não existe hoje filtro de
regime para ligar — é um achado de infraestrutura, não de estratégia.

Reconstruindo o regime das velas do BTC (perpétuo Binance, só desde 2026-08-21 20:32Z — declarado):

```
| momentum v2       | prospective     | BTC cai (<-0,15%)  |  60 |  -0.090 |   -5.37 |   43.3 |
| momentum v2       | prospective     | BTC lateral        |  63 |   0.043 |    2.71 |   47.6 |
| momentum v2       | prospective     | BTC sobe (>+0,15%) |  72 |  -0.404 |  -29.08 |   23.6 |
| momentum v2       | replay:f8d8279c | BTC sobe (>+0,15%) | 132 |  -0.342 |  -45.18 |   31.8 |
| volume_anomaly v2 | prospective     | BTC cai (<-0,15%)  | 209 |  -0.027 |   -5.58 |   41.6 |
| volume_anomaly v2 | prospective     | BTC lateral        | 152 |  -0.402 |  -61.18 |   26.3 |
| volume_anomaly v2 | prospective     | BTC sobe (>+0,15%) |  95 |  -0.402 |  -38.23 |   26.3 |
```

`momentum` (long-only) perde **mais quando o BTC sobe** — contraintuitivo, n pequeno, sem tercil de
volatilidade consistente entre coortes. **Não há regime a excluir**: a perda é uniforme.

### Item 6 (suporte) — contrafactual do piso, dentro da amostra (`-08`)

```
| momentum v2       | prospective     |        0.000 | 195 |  100.0 | -0.0166 | 0.1457 | -0.1628 | -31.75 |
| momentum v2       | prospective     |        0.010 |  88 |   45.1 |  0.0952 | 0.0956 | -0.0006 |  -0.05 |
| momentum v2       | replay:f8d8279c |        0.000 | 222 |  100.0 |  0.0811 | 0.2524 | -0.1717 | -38.13 |
| momentum v2       | replay:f8d8279c |        0.010 |  20 |    9.0 | -0.2197 | 0.1156 | -0.3356 |  -6.71 |
| volume_anomaly v2 | prospective     |        0.000 | 456 |  100.0 |  0.0886 | 0.3185 | -0.2302 | -104.98 |
| volume_anomaly v2 | prospective     |        0.020 |  95 |   20.8 | -0.2441 | 0.1431 | -0.3875 |  -36.81 |
```

Um piso de ATR% em 1 % zera a expectancy da `momentum v2` prospectiva (−0,163 → −0,0006 R) e
**piora** a de replay (−0,172 → −0,336 R). Na `volume_anomaly`, subir o piso corta o custo e
**derruba o bruto junto** (+0,089 → −0,244 R). **Cortar custo não cria edge.**

## VEREDITO (em português simples, para o Everton)

1. **A gente não está perdendo por errar o mercado. Está perdendo por pagar pedágio.** Cada operação
   simulada paga cerca de **0,2 % do preço** em taxa, spread e escorregão (ida e volta).
2. **O tamanho desse pedágio depende de uma coisa só: a distância até o stop.** Se o stop está a 1 %
   do preço, o pedágio come 20 % do risco (0,20 R). Se está a 0,25 %, come 80 %. Isso é conta, não
   opinião: o número deu 0,0020 nas dez medições, sempre.
3. **Em dinheiro:** a `volume_anomaly v1` perdeu **15,95 USDT por operação** e pagou **16,42 USDT de
   pedágio por operação**. A `momentum v1` perdeu 9,20 e pagou 7,28. **O pedágio é a perda.**
4. **Sem o pedágio, as estratégias empatam — não ganham.** O resultado "bruto" (antes de custo) ficou
   entre −0,04 e +0,09 R, com fator de lucro entre 0,90 e 1,24. É cara ou coroa. Então não adianta
   só reduzir custo: **falta vantagem de verdade na entrada**.
5. **Não é a invalidação.** Ela mata 26 % a 43 % das operações e quase nenhuma ia dar lucro — a
   suspeita antiga estava certa na descrição. Mas quando refizemos as **mesmas** operações sem ela,
   o resultado praticamente não mudou (entre −0,07 e +0,03 R, e trocando de sinal). Ela adianta a
   perda; não a cria. **Não vale escrever código novo para mudá-la.**
6. **Não é a hora, não é o dia, não é o BTC.** A `volume_anomaly` perde nas 24 horas do dia e em 25
   dos 28 dias. Não existe um "horário ruim" a desligar.
7. **O que sugere melhora, e o quanto:** tirar o alvo fixo (deixar correr até o horizonte) levaria a
   `momentum` de −0,17 R para **−0,005 R** na janela de replay — quase zero. **Mas** o mesmo teste na
   operação viva de hoje deu **pior** (−0,23 R e −0,10 R). Duas medições, sinais opostos: **não
   prometo nada**, e mexer nisso agora seria decidir pela janela que gerou a ideia — o erro clássico.
8. **O que eu mudaria primeiro:** proibir a operação quando o pedágio passar de um teto declarado
   (por exemplo, 0,10 R ⇒ stop de pelo menos 2 % do preço). Na `momentum` isso é só um parâmetro
   (`atr_pct_min`) — e é exatamente o que a **v4** já está medindo desde ontem à tarde. Na
   `volume_anomaly` **não existe parâmetro** para isso: o stop é a mínima da barra do pico, então
   seria código novo.
9. **O que isso não promete:** um teto de custo **não cria** vantagem — só para de destruí-la. No
   contrafactual dentro da amostra ele zera a `momentum` em uma população e piora em outra, e na
   `volume_anomaly` derruba o bruto junto. Qualquer variante nova só vale com **30 dias** de janela
   reservada, para a frente, como a regra manda.
10. **A conta que falta fazer, e é a que decide tudo:** achar uma entrada cujo resultado **bruto**
    passe de **+0,25 R**. Enquanto nenhuma passar de +0,09, nenhuma saída, filtro de hora ou regime
    inverte o sinal.
11. **Um achado de bastidor que precisa entrar na fila:** o classificador de regime nunca gerou
    dado (uma linha `UNKNOWN` no banco). Enquanto isso não existir, "só perde no regime X" não é
    sequer verificável pelo caminho de produção.
12. **Nada disso é dinheiro real** e nada foi ligado. O Lab existe para descobrir isto antes de
    qualquer carteira — e descobriu.

**Variantes exatas a derivar a seguir** (só por `derive_variant.py`, sem tocar em código de
estratégia, e todas `research_only`):

| # | de | mudança | por quê | o que a mede |
|---|---|---|---|---|
| V1 | `momentum v2` | `atr_pct_min: 0,003 → 0,020` | teto de custo em 0,10 R; a v4 (0,0089) já testa 0,22 R | 30 dias prospectivos reservados |
| V2 | `momentum v2` | `target_atr: 1,5 → 3,0` (mantém `stop_atr 1,5`) | é o braço TGT-3, o maior Δ positivo pareado (+0,104 R em P1) e o mais barato de testar prospectivamente | 30 dias, **nunca** avaliada na janela 08-08→09-08 |
| — | `volume_anomaly` | **nada derivável** | não existe parâmetro de piso de risco; exigiria versão de código nova (brief próprio) | — |
| — | `momentum_v2` com `invalidation_mode` | **não fazer** | item 0 do T3.27 satisfeito: os três contrastes INV são indistinguíveis de zero | EXP-0007 |

Veredito por variante individual, como o brief manda: **`inconclusivo`** em todas.

## CONCERNS

1. **Escopo — `infra/scripts/replay_exits.py` foi alterado.** O brief permitia mexer nele "only if
   an exit-policy arm needs a parameter that does not exist yet". O que faltava não era parâmetro de
   braço, era **seletor de população**: `--versions` nomeia *chave de estratégia*, então
   `--versions momentum` dobra as quatro versões e as cinco coortes num contraste só — e as duas
   coortes de replay da `momentum v2` (`f8d8279c` e `7598d6c4`) guardam **as mesmas 224 entradas**
   sob `signal_id` diferentes, o que contaria cada par duas vezes e estreitaria o erro-padrão sem
   uma observação nova. Sem os seletores, o item 3 do brief (que nomeia a coorte `f8d8279c`) não é
   executável. Acrescentei `--only-version` e `--cohort`, ambos **inertes quando ausentes**
   (a corrida R1 original é bit a bit a mesma), com 8 testes e `ruff`/`pyright` limpos. **Decisão de
   revisor, não minha:** se isso for julgado fora de escopo, o caminho é reverter o arquivo e
   reexecutar com um brief próprio — os números do item 3 não mudam, só o meio de obtê-los.
2. **`momentum v2 / prospective` tem 1 dia distinto e `momentum v1` tem 3.** Os `p` de P3/P4 são
   `1,000` **por construção** (1 e 3 blocos), não por equivalência. O único contraste com IC
   informativo fora do replay é `EXIT-NOTGT − base` em P4 ([−0,116; −0,049]) — e mesmo esse é 3
   blocos.
3. **O `as_of` fixa a emissão, não a resolução.** Consultas rodadas em instantes diferentes viam
   populações com ±1–2 linhas de diferença; refiz as nove **numa transação `REPEATABLE READ`** para
   que a nota fosse coerente. As tabelas deste arquivo e da KB-0076 são todas desse snapshot; se
   alguém reler amanhã, os `n` sobem.
4. **`replay:cd0d5584` e `replay:7598d6c4` são corridas gêmeas anteriores ao backfill de funding**
   (335 de 337 e 201 de 224 sem `R_net`). Ficaram fora de tudo, menos de uma linha ilustrativa. Se o
   Lab reportar essas coortes em algum lugar, os números de lá **não** são comparáveis.
5. **A cobertura de velas do BTC começa em 2026-08-21 20:32Z.** O corte de regime da `volume_anomaly`
   replay tem 241 de 337 operações **sem** vela de BTC (a coluna `sem_vela_btc` declara isso). O
   item 5 é, para essa coorte, uma leitura parcial.
6. **A hipótese de custo (20 bps ida e volta) é declarada, não medida.** Toda a conclusão principal
   escala linearmente com ela. Medir o custo real contra o book é a próxima verificação óbvia, e
   mudaria a magnitude — não o sinal, porque o bruto é ~0.
7. **`meta.excursions.mfe_complete_bars` é limite inferior** (ver item 4). Os percentis de MFE
   subestimam; os `bounds` estão gravados e não foram usados nesta passada.
8. **Nada foi arquivado no `obsidian/`.** As duas páginas estão em `.claude/state/exp-drafts/` como
   rascunho para a Sexta-feira, e o número **KB-0076** é a próxima vaga livre em 2026-09-08T15:47Z —
   se outra tarefa tomar o número antes, renumerar.
9. **Um arquivo acima do orçamento de linhas** no repositório (`bridge.py`, 365 > 350) é da T3.29 em
   voo; não é meu e não foi tocado.
