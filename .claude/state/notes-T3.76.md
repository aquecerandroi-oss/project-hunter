# notes-T3.76 — o portão de regime é um portão, e um portão não devolve calendário

**Data:** 2026-09-10, 12:00 → 15:35 BRT (15:00 → 18:35 UTC). **Owner:** quant-engineer.
**Base local:** árvore compartilhada, **nada commitado**. **VPS:** os workers rodam
`hunter-api:223cbff`; o HEAD do checkout foi para `60f3fe6` às 13:45 BRT **por outra tarefa**, e é
isso que bloqueia o §7.
**Nenhum container parado, recriado ou reiniciado. Nenhum `.env*` tocado. Nenhum `git pull` na VPS
por mim. Nenhuma escrita SQL à mão.**
**Escritas na VPS, todas por caminho auditado:** 3 passadas de `regime_hourly --once
--repair-days N` via `compose.sh ops` (§1), 3 `derive_variant.py` + 3
`activate_strategy_version.py` via `compose.sh ops` (§3), 48 fatias de
`hunter_strategy_worker.replay.run` via `docker exec hunter-strategy-worker-1` (§4) e 4 passadas de
`--stress` (sessão `READ ONLY`).
**Testcontainers:** um arquivo de cada vez (`test_regime_deep_repair.py`, depois
`test_regime_job.py`).

---

## STATUS

**DONE_WITH_CONCERNS** — as quatro medições estão feitas e provadas; o que não deu para fazer é
**uma permissão de deploy**, não uma dúvida técnica, e está no §7.

| # | Entrega do brief | Resultado |
|---|---|---|
| 1 | Backfill de regime de 90 d, idempotente, cobertura re-contada | **OK.** §1–§2. 784 → **2 161/2 161 (100 %)**; terceira passada escreve **0** |
| 2 | Pré-registro **antes** do replay (`EXP-0026` + Index) | **OK.** §3. Escrito 12:20–12:45 BRT; regra de sucesso **corrigida** e o porquê declarado |
| 3 | Derivar, ativar `research_only`, replay 90 d × 16 mercados, estresse, análise | **OK.** §3–§6. 48 fatias, 552 960 barras, **0 erros** |
| 4 | Vereditos, páginas de estratégia, notas, SQL, **aposentar quem falhou** | **PARCIAL.** Vereditos e documentação OK; **as 4 aposentadorias estão bloqueadas** — §7 |

**Veredito de uma linha:** o portão de regime funciona exatamente como portão (Δ pareado por
(mercado, barra) contra o pai = **0,0000 R**), move o ponto de −0,0293 R para +0,036…+0,061 R, e
**nenhum IC de blocos de dia exclui zero** — ele compra expectativa pagando em **dias**. Os quatro
braços são `descartar`.

---

## ARQUIVOS (`git status --porcelain`, só os meus)

```
?? .claude/state/brief-T3.76-validacao-em-um-dia.md
?? .claude/state/notes-T3.76.md
?? .claude/state/exp-drafts/t376/analise.py
?? .claude/state/exp-drafts/t376-decisoes.csv
?? obsidian/05-EXPERIMENTS/EXP-0026-regime-como-estrategia.md
?? infra/scripts/sql/research/2026-09-10-t376-q00-cobertura-regime-e-velas.sql
?? infra/scripts/sql/research/2026-09-10-t376-q01-custo-da-leitura-do-universo.sql
?? infra/scripts/sql/research/2026-09-10-t376-q02-cobertura-depois-do-backfill.sql
?? infra/scripts/sql/research/2026-09-10-t376-q03-coorte-v10-por-regime.sql
?? infra/scripts/sql/research/2026-09-10-t376-q04-dump-decisoes-bracos.sql
?? infra/scripts/sql/research/2026-09-10-t376-q05-funil-k-e-cobertura.sql
?? services/scanner-worker/tests/test_regime_deep_repair.py
?? services/scanner-worker/tests/test_regime_hourly_cli.py
 M obsidian/05-EXPERIMENTS/Experiments Index.md
 M obsidian/03-TRADING/Estrategias/mean_reversion.md
 M obsidian/03-TRADING/Estrategias/momentum.md
```

Raiz em `C:\dev\project-hunter\`. **Não commitei nada.** Nenhum módulo de produção mudou — os dois
arquivos novos em `services/scanner-worker/tests/` são testes.

---

## 1. O BACKFILL DE REGIME — a ferramenta existia, o botão certo é `--repair-days`

**Não precisou de código novo.** `python -m hunter_scanner_worker.regime_hourly --once
[--backfill-days N] [--repair-days N]` é a manivela de operador declarada em `docs/PIPELINE.md` §4b
item 8, e roda dentro da imagem publicada (`Dockerfile.api-workers` copia `services/scanner-worker`).
Não há script em `infra/scripts/*regime*`; o brief supôs um que não existe, como a T3.75 já tinha
achado para o funding.

**E `--backfill-days` sozinho não teria resolvido.** As duas regras que decidem quais horas uma
passada produz (`regime_window.py`) são *backfill* ("toda hora da janela **sem linha**") e *reparo*
("toda hora das últimas 72 h, tenha linha ou não"). As 205 horas `UNKNOWN` de agosto **têm linha** —
foram escritas em 2026-09-08, quando `candles` só ia até 2026-08-08 e o classificador respondia
`trend_warmup` honestamente. A primeira regra nunca mais olharia para elas e a segunda não alcança
30 dias. **`--repair-days 90` é o único caminho**, e `main()` faz `days = max(backfill_days,
repair_days)` e `repair_hours = repair_days * 24`.

### 1.1 Medida antes (q00, 14:59Z)

```
+--------+------------------+--------+------------------------+------------------------+---------+
| scope  |  classificador   | linhas |        primeira        |         ultima         | abertas |
+--------+------------------+--------+------------------------+------------------------+---------+
| btc    | regime_hourly_v1 |    784 | 2026-08-08 23:00:00+00 | 2026-09-10 14:00:00+00 |       0 |
| global | regime_v0        |     38 | 2026-09-06 18:18:05+00 | 2026-09-10 11:47:21+00 |       1 |
+--------+------------------+--------+------------------------+------------------------+---------+

+-----------------+-----------+-----------+-------------+
| horas_da_janela | com_linha | sem_linha | pct_coberto |
+-----------------+-----------+-----------+-------------+
|            2161 |       784 |      1377 |        36,3 |
+-----------------+-----------+-----------+-------------+
```

Vela de 1 min do BTC perpétuo, horas **completas** (60 minutos `is_final`, a última em `bucket+59`):
**2026-06-11 19:00Z → 2026-09-10 13:00Z, 2 178 horas, ZERO buracos**. Universo monitorado: 200
mercados; 16 têm vela em junho/julho, 153 em agosto, 200 em setembro.

### 1.2 Custo da leitura, medido antes de escrever (q01)

A fase cara de uma passada de 90 dias é ler o universo (`hourly_closes`, lotes de 25 mercados). Medi
a consulta **idêntica** à de produção, somente leitura:

```
um lote de 25 mercados, 90 d + 25 h  ->  7 883 horas completas   Time: 783,692 ms
referencia BTC, 90 d + 745 h         ->  2 179 horas completas   Time: 196,447 ms
```

8 lotes ≈ **6,3 s**. A passada inteira cabe folgadamente em `timeout 290`.

### 1.3 As três passadas (15:12–15:13Z)

```
$ ssh hunter-vps 'cd /opt/project-hunter && bash infra/vps/compose.sh ops \
    python -m hunter_scanner_worker.regime_hourly --once --repair-days 35'
{"cut": "2026-09-10T15:00:00+00:00", "due": 841, "repair_hours": 840, "written": 841,
 "markets": 200, "reference_hours": 1585, "outcomes": {"inserted": 56, "updated": 785},
 "duration_s": 17.79, "event": "scanner_regime_pass"}

$ ... --once --repair-days 90
{"cut": "2026-09-10T15:00:00+00:00", "due": 2161, "repair_hours": 2160, "written": 1320,
 "markets": 200, "reference_hours": 2179, "outcomes": {"unchanged": 841, "inserted": 1320},
 "duration_s": 29.494, "event": "scanner_regime_pass"}

$ ... --once --repair-days 90        # a prova de idempotencia
{"cut": "2026-09-10T15:00:00+00:00", "due": 2161, "repair_hours": 2160, "written": 0,
 "markets": 200, "reference_hours": 2179, "outcomes": {"unchanged": 2161},
 "duration_s": 27.353, "event": "scanner_regime_pass"}
```

**Segunda passada da mesma janela: `written: 0`, `unchanged: 2161`.** A idempotência é da chave e do
digest, não da disciplina de quem chama.

**Consequência declarada, e ela é real:** as **785 linhas que já existiam foram `updated` na
primeira passada** — o digest cobre a decomposição inteira, e ela mudou porque a breadth passou a ser
lida sobre 200 mercados com história mais funda e porque as horas de aquecimento de agosto passaram a
ter as 224 horas de BTC que lhes faltavam. Atualizar **no lugar** preserva o `id` (é o que
`agent_signals.regime_id`, `trade_proposals.regime_id` e `paper_trades.regime_id` apontam com
`ON DELETE SET NULL`), mas o **rótulo** de horas já usadas por decisões vivas mudou. Quem tem portão
guarda o rótulo observado no envelope (`provenance.regime_gate.label`) e está imune; quem não tem
guarda só o `regime_id`, então uma leitura retroativa "por regime" dessas decisões passa a ver a
série corrigida. Isso é correção, não perda — mas é um fato, e fica escrito.

## 2. COBERTURA DEPOIS (q02, 15:14Z) — e as 205 horas que continuam `UNKNOWN`

```
+-----------------+-----------+-----------+-------------+     +------------------+
| horas_da_janela | com_linha | sem_linha | pct_coberto |     | horas_duplicadas |
+-----------------+-----------+-----------+-------------+     +------------------+
|            2161 |      2161 |         0 |       100,0 |     |                0 |
+-----------------+-----------+-----------+-------------+     +------------------+
```

| janela | horas | SIDEWAYS | LOW_VOL | HIGH_VOL | BTC_BULL | BTC_BEAR | UNKNOWN |
|---|---:|---:|---:|---:|---:|---:|---:|
| J1 06-12→07-12 | 705 | 92 | 43 | 121 | 145 | 99 | **205** |
| J2 07-12→08-11 | 720 | 221 | 59 | 40 | 264 | 136 | 0 |
| J3 08-11→09-10 | 720 | 192 | 50 | 176 | 118 | 184 | 0 |

**As 205 `UNKNOWN` são propriedade do dado, não do produtor.** Todas antes de 2026-06-21 04:00Z, o
motivo declarado é `trend_warmup` nas 205 (`reasons` também traz `insufficient_components` e
`insufficient_coverage` nas mesmas 205, `vol_warmup` em 174 e `drawdown_warmup` em 149). A conta
fecha exatamente: a vela do BTC começa em **2026-06-11 19:00Z** e a tendência precisa de **224 horas
contíguas** atrás (`sma_slow_hours 200 + slope_lookback_hours 24`) → 2026-06-21 03:00Z é a última
hora impossível e **04:00Z é a primeira classificada**, que é o que a base mostra. Nenhum backfill
de regime pode consertar isso; só um backfill de **vela** mais fundo.

## 2b. TDD — dois arquivos de teste novos, e o que eles fixam

Nenhum módulo de produção mudou; o que faltava era **prova** de que a manivela alcança esta forma de
buraco. O irmão que já existia (`test_regime_job.py::
test_a_historical_hour_written_unknown_is_repaired_after_the_candle_arrives`) prova a outra forma —
hora esburacada por minuto faltante **dentro** da janela de 72 h.

- `services/scanner-worker/tests/test_regime_hourly_cli.py` (5 testes, sem banco): a aritmética da
  manivela, que **não tinha teste nenhum** — `--repair-days 90` vira `repair_hours = 2160` (e não
  90) e levanta `--backfill-days` para 90; os padrões são 31 d / 72 h; sem `--once` não roda passada.
- `services/scanner-worker/tests/test_regime_deep_repair.py` (3 testes, testcontainer): mesma
  semente nos três, só o botão muda — com a janela de reparo padrão as horas de aquecimento
  **continuam `UNKNOWN`** depois de a vela chegar; com a janela tão funda quanto a de backfill elas
  são **atualizadas no lugar** (mesmos `id`s, e as horas cujo digest não mexeu mantêm o `xmin`); e a
  segunda passada funda escreve **nada**.

**A discriminação é por construção, não por mutação:** os testes 1 e 2 partem do mesmo fixture e da
mesma extensão de vela e diferem **só** em `repair_hours`, produzindo resultados opostos. Não mutei
código de produção para provar que o teste falha — a árvore é compartilhada.

```
$ uv run pytest services/scanner-worker/tests/test_regime_hourly_cli.py -q
.....                                                                    [100%]
5 passed in 2.15s

$ uv run pytest services/scanner-worker/tests/test_regime_deep_repair.py -q
...                                                                      [100%]
3 passed in 41.63s

$ uv run pytest services/scanner-worker/tests/test_regime_job.py -q      # nao quebrei o irmao
..........                                                               [100%]
10 passed in 75.82s (0:01:15)

$ uv run pytest services/scanner-worker/tests/test_regime_window.py services/scanner-worker/tests/test_regime_hourly_cli.py -q
.............                                                            [100%]
13 passed in 2.29s

$ uv run ruff check <os dois arquivos>      -> All checks passed!
$ uv run ruff format <os dois arquivos>     -> 2 files left unchanged
$ uv run pyright <os dois arquivos>         -> 0 errors, 0 warnings, 0 informations
```

## 3. PRÉ-REGISTRO — e a correção que a regra de sucesso do brief exigiu

`obsidian/05-EXPERIMENTS/EXP-0026-regime-como-estrategia.md`, escrito 12:20–12:45 BRT, **antes** de
derivar qualquer variante. Duas coisas nele merecem estar aqui também.

**(a) A condição 1 do brief, como escrita, mede zero por construção.** Um portão de elegibilidade
**não muda a decisão** numa barra elegível — ele só remove barras. Sobre as barras elegíveis
compartilhadas, filha e pai leem o mesmo contexto, o mesmo código congelado e os mesmos parâmetros,
então o "Δ pareado por (mercado, barra)" é 0 R por definição, tirando a divergência de máquina de
estados do slot do `docs/PIPELINE.md` §4b item 11 — que é ruído de contabilidade, não vantagem. O
pré-registro trocou o **critério** para o contraste que a hipótese realmente afirma (condicional
contra incondicional, não pareado, IC por blocos de dia) e **manteve** o Δ pareado como a
**condição 5**: prova de que o portão é só um portão. Ele veio **+0,0000 R** nos três braços — a
correção estava certa e a checagem valeu a pena.

**(b) O corte in-sample do pai foi feito e declarado antes do replay** (q03, 15:20Z): das 798
decisões da `v10` nos mesmos 90 d, 218 caem em `HIGH_VOLATILITY` (+0,0568 R), 159 em `SIDEWAYS`
(+0,0335), 43 em `LOW_VOLATILITY` (−0,0122), 166 em `BTC_BULL` (−0,1239), 140 em `BTC_BEAR`
(−0,0481) e **72 em `UNKNOWN` (−0,1837)**. Isso deu a expectativa de `n` de cada braço (202/159/218)
— que o replay confirmou em 209/169/222, dentro de 5 % — e mostrou, **antes de rodar**, que o braço
de falseamento já era o melhor. Está escrito na página como exploratório, não confirmatório.

### 3.1 Derivação e ativação (15:25–15:27Z, ensaio primeiro)

```
$ bash infra/vps/compose.sh ops python infra/scripts/derive_variant.py mean_reversion v10 \
    --policy regime=btc:SIDEWAYS,LOW_VOLATILITY --changelog "..." [--dry-run]
derivada mean_reversion v15 de v10 (purpose research_only, draft, nada ativado) em code_ref
  hunter_core.strategies.mean_reversion_v1@sha256:a970c9...395f: policy -> btc:LOW_VOLATILITY,SIDEWAYS
  [params_hash d4fcf66f9449]
... v16 ... policy -> btc:SIDEWAYS         [params_hash d4fcf66f9449]
... v17 ... policy -> btc:HIGH_VOLATILITY  [params_hash d4fcf66f9449]

$ ... activate_strategy_version.py mean_reversion v1{5,6,7} --changelog "..." [--dry-run]
activated mean_reversion v15 (purpose research_only) at 2026-09-10T15:26:45Z
activated mean_reversion v16 (purpose research_only) at 2026-09-10T15:26:52Z
activated mean_reversion v17 (purpose research_only) at 2026-09-10T15:26:59Z
```

`params_hash` idêntico ao do pai nas três: **o contraste é de portão, não de parâmetro**.

## 4. AS 48 FATIAS DE REPLAY — e o portão do replay, que não se combate

Comando por fatia (uma de cada vez, primeiro plano, `timeout` explícito):

```
timeout 285 ssh hunter-vps "timeout 250 docker exec hunter-strategy-worker-1 \
  python -m hunter_strategy_worker.replay.run --version mean_reversion:v15 \
  --from 2026-06-12 --to 2026-07-12 --markets ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT \
  --cohort replay:3271f431-10f3-4fad-81f5-8fb96fa6bfac --explain-ledger /tmp/t376-v15-w1-s1.jsonl"
```

Coortes: `v15` `replay:3271f431-10f3-4fad-81f5-8fb96fa6bfac` · `v16`
`replay:309144d2-c89b-4f1a-b417-c04f1c49df3c` · `v17` `replay:095d4772-d133-47de-82cb-189dc78bbade` ·
`momentum v11` `replay:70f55430-2752-48d8-93db-3941d3b31bf8`. Janelas `06-12/07-12/08-11/09-10`;
recortes `s1` ETH/SOL/XRP/DOGE (os 4 originais), `s2` BTC/BNB/ZEC/SUI, `s3` NEAR/UNI/ARB/TAO,
`s4` LINK/DASH/PROM/SAHARA. Recibo de fechamento:

```
version | cohort            | fatias | recortes | de         | ate        | barras | erros
v15     | replay:3271f431.. |     12 |        4 | 2026-06-12 | 2026-09-10 | 138240 |     0
v16     | replay:309144d2.. |     12 |        4 | 2026-06-12 | 2026-09-10 | 138240 |     0
v17     | replay:095d4772.. |     12 |        4 | 2026-06-12 | 2026-09-10 | 138240 |     0
v11     | replay:70f55430.. |     12 |        4 | 2026-06-12 | 2026-09-10 | 138240 |     0
```

**O portão do replay se pausou sozinho três vezes, e eu esperei — nunca o contorne.** A recusa é
`refused: live lane degraded (consumer_lag:165)` / `:251` / `:639` (T3.74b,
`REPLAY_CONSUMER_LAG_MAX=100`). Medi o comportamento do sinal em vez de supor:

```
16:01:14 pending=4 lag=341   16:02:38 pending=6 lag=467   16:04:03 pending=0 lag=0
16:01:42 pending=5 lag=311   16:03:06 pending=9 lag=653   16:04:31 pending=0 lag=0
16:02:10 pending=5 lag=497   16:03:35 pending=0 lag=0     16:04:59 pending=0 lag=0
```

**O lag é um dente de serra do topo do minuto**: os ~200 candles de um minuto chegam juntos, o
consumidor leva ~30–40 s para mastigá-los e volta a 0. Um replay que largue durante o pico é
recusado; um que largue depois dele passa. O driver das fatias passou a esperar `lag == 0` antes de
largar e a repetir uma vez a fatia recusada. **Concern honesto:** com as três variantes novas
`active` o consumidor passou a avaliar **14 versões por barra** em vez de 11, e o pico de lag que eu
medi (até 653) é maior do que o `REPLAY_CONSUMER_LAG_MAX` por um fator de 6 — parte disso é o meu
próprio replay disputando o único núcleo, mas parte é o custo permanente das três ativações. Elas
precisam ser aposentadas (§7) também por isso.

## 5. K1–K5, cobertura e C5 (q05, 18:10Z)

```
versao             | barras | unavailable | k4_pct | ineligible | inelig_pct | triggered | erros
mean_reversion v10 | 138240 |        1280 |   0,93 |          0 |       0,00 |      1760 |     0
mean_reversion v15 | 138240 |           - |   0,00 |      96192 |      69,58 |       438 |     0
mean_reversion v16 | 138240 |           - |   0,00 |     105920 |      76,62 |       344 |     0
mean_reversion v17 | 138240 |           - |   0,00 |     116672 |      84,40 |       495 |     0
momentum v11       | 138240 |           - |   0,00 |      82944 |      60,00 |      2961 |     0

versao             | decisoes | terminais | dias | com_r_net | cob_rnet | media_r_exf | media_r_net
mean_reversion v10 |      798 |       798 |   89 |       300 |    37,6% |     -0,0293 |     +0,1025
mean_reversion v15 |      209 |       209 |   35 |       209 |   100,0% |     +0,0359 |     +0,0347
mean_reversion v16 |      169 |       169 |   30 |       169 |   100,0% |     +0,0451 |     +0,0438
mean_reversion v17 |      222 |       222 |   21 |       222 |   100,0% |     +0,0613 |     +0,0600
momentum v11       |     1167 |      1167 |   47 |      1163 |    99,7% |     -0,0595 |     -0,0588
```

- **K1** (< 20): não dispara em nenhum. **K2** (> 1 500): não dispara (`momentum v11` a 1 167).
- **K3**: dispara **só** em `momentum v11` (1 167 ≥ 100, 47 ≥ 30, bruta −0,0595 < 0).
- **K4**: `0,93 %` **lido no pai**, que é a leitura honesta para versão com portão (§4b item 12); o
  `0,00 %` das filhas é o falso verde documentado. A fração `ineligible` (69,6 / 76,6 / 84,4 /
  60,0 %) é outro número e não substitui K4.
- **K5**: **100 %** nos braços, **37,6 %** no pai. As coortes de hoje nasceram depois do backfill de
  funding da T3.75; a do pai é anterior e `signal_outcomes` é append-honesto. **Isso torna
  `media_r_net` do pai (+0,1025 em 300 de 798) inutilizável para comparação** — é o artefato de
  cobertura da T3.62b §7.2, e é exatamente por isso que o eixo pré-registrado é `r_ex_funding`, que
  existe em 100 % das cinco populações. Nos braços os dois eixos coincidem em 0,001 R.
- **C5** (risco/entrada > 3 %, teto do `paper_v1`): `v15` 14,4 % · `v16` 14,2 % · `v17` **22,5 %** ·
  `momentum v11` 14,9 % · pai 16,8 %.

## 6. A ANÁLISE (`.claude/state/exp-drafts/t376/analise.py`, blocos de dia, semente 20260910)

```
== 1. populacao e expectativa (eixo r_exf, IC por blocos de dia) ==
versao                     n  dias     media     soma     PF  IC95
mean_reversion v10       798    89   -0.0293   -23.35  0.910  [-0.1336; +0.0728]
mean_reversion v15       209    35   +0.0359    +7.50  1.134  [-0.1211; +0.1810]
mean_reversion v16       169    30   +0.0451    +7.62  1.175  [-0.1528; +0.2140]
mean_reversion v17       222    21   +0.0613   +13.60  1.223  [-0.2346; +0.2999]
momentum v11            1167    47   -0.0595   -69.43  0.815  [-0.1518; +0.0402]

== 2. condicao 1: delta = braco - pai (janela inteira), mesmos dias ==
braco                  n_braco  media_br  media_pai    delta  IC95                veredito
mean_reversion v15         209   +0.0359    -0.0293  +0.0651  [-0.0832; +0.2024]  FALHA
mean_reversion v16         169   +0.0451    -0.0293  +0.0744  [-0.1135; +0.2362]  FALHA
mean_reversion v17         222   +0.0613    -0.0293  +0.0905  [-0.1540; +0.2763]  FALHA

== 2b. apoio: particao DENTRO do pai (permitido - proibido), pareado por dia ==
conjunto                n_perm n_proib   media_p   media_x    delta  IC95
mean_reversion v15         202     596   +0.0238   -0.0473  +0.0711  [-0.1207; +0.2508]
mean_reversion v16         159     639   +0.0335   -0.0449  +0.0784  [-0.1529; +0.2836]
mean_reversion v17         218     580   +0.0568   -0.0616  +0.1183  [-0.2102; +0.3851]

== 3. condicao 3: media por janela de 30 d (positivo em >= 2 de 3) ==
mean_reversion v10   -0.1216 (n=328)  -0.0919 (n=182)  +0.1155 (n=288)   1/3 FALHA
mean_reversion v15   +0.1121 (n= 41)  -0.0668 (n= 67)  +0.0730 (n=101)   2/3 PASSA
mean_reversion v16   +0.1542 (n= 33)  -0.0383 (n= 51)  +0.0528 (n= 85)   2/3 PASSA
mean_reversion v17   -0.1091 (n= 94)  +0.0288 (n= 15)  +0.2073 (n=113)   2/3 PASSA
momentum v11         -0.1101 (n=342)  -0.2137 (n=354)  +0.0931 (n=471)   1/3 FALHA

== 4. condicao 4: leave-one-market-out (nunca negativo) ==
mean_reversion v10   mercados=16  pior: sem SOLUSDT    -0.0390  negativos=16  FALHA
mean_reversion v15   mercados=14  pior: sem DOGEUSDT   +0.0211  negativos= 0  PASSA
mean_reversion v16   mercados=14  pior: sem DOGEUSDT   +0.0256  negativos= 0  PASSA
mean_reversion v17   mercados=16  pior: sem SAHARAUSDT +0.0402  negativos= 0  PASSA
momentum v11         mercados=16  pior: sem PROMUSDT   -0.0694  negativos=16  FALHA

== 5. condicao 5: delta pareado por (mercado, barra) contra o pai ==
braco                  n_braco  compart so_do_braco    delta  veredito
mean_reversion v15         209      202           7  +0.0000  PASSA
mean_reversion v16         169      159          10  +0.0000  PASSA
mean_reversion v17         222      216           6  +0.0000  PASSA

== 6. C5 e 4 originais x 12 novos (pareado por dia) ==
versao               C5 %  orig n  orig media  novos n  novos media    delta  IC95
mean_reversion v10  16.8%     138     +0.0002      660      -0.0354  +0.0356  [-0.1056; +0.1793]
mean_reversion v15  14.4%      33     +0.2104      176      +0.0031  +0.2073  [-0.0415; +0.4629]
mean_reversion v16  14.2%      27     +0.2293      142      +0.0101  +0.2192  [-0.0576; +0.4837]
mean_reversion v17  22.5%      52     +0.0315      170      +0.0704  -0.0389  [-0.2185; +0.1258]
momentum v11        14.9%     254     -0.0853      913      -0.0523  -0.0330  [-0.1528; +0.0914]

== 7. rotulo das decisoes de cada braco (prova de que o portao pegou) ==
mean_reversion v10   HIGH_VOLATILITY=218, BTC_BULL=166, SIDEWAYS=159, BTC_BEAR=140, UNKNOWN=72, LOW_VOLATILITY=43
mean_reversion v15   SIDEWAYS=166, LOW_VOLATILITY=43
mean_reversion v16   SIDEWAYS=169
mean_reversion v17   HIGH_VOLATILITY=222
momentum v11         BTC_BULL=664, HIGH_VOLATILITY=503
```

### 6.1 Estresse (sessão `READ ONLY`, `--stress`, 18:08–18:11Z)

| coorte | base | custos ×2 | 1ª metade | 2ª metade | veredito |
|---|---:|---:|---:|---:|---|
| `v15` (209, 14 mercados) | +0,0347 | **−0,0691** | −0,0293 (n=92) | +0,0850 (n=117) | **frágil a custos**; dependente de metade |
| `v16` (169, 14 mercados) | +0,0438 | **−0,0599** | +0,0072 (n=69) | +0,0691 (n=100) | **frágil a custos** |
| `v17` (222, 16 mercados) | +0,0600 | **−0,0278** | **−0,0960** (n=105) | **+0,2000** (n=117) | **frágil a custos**; dependente de metade |
| `momentum v11` (1 163) | **−0,0588** | −0,1695 | −0,1551 (n=588) | +0,0398 (n=575) | **`sem_vantagem_na_base`** |

### 6.2 O que estes números dizem, em três frases

1. **O portão é um portão.** Δ pareado **+0,0000 R** nos três braços, 202/209, 159/169 e 216/222
   barras compartilhadas com o pai; as 7/10/6 decisões restantes são a divergência de slot do §4b
   item 11 (a filha não arma a barreira nas barras que pula). E cada braço decide **só** dentro do
   rótulo pedido (§6 item 7). O instrumento está correto.
2. **O portão compra expectativa pagando em dias.** −0,0293 → +0,0359 / +0,0451 / +0,0613 é uma
   melhora real do ponto, e o preço é a população **em blocos de dia**: 35, 30 e **21** blocos. Com
   21 blocos, o IC nasce com ±0,25 R de largura, e **nenhum dos três exclui zero**. Não há corte de
   rótulo que devolva calendário: cortar horas remove dias inteiros.
3. **O braço de falseamento venceu, e é o mais suspeito.** `HIGH_VOLATILITY` (+0,0613, PF 1,223)
   bate os dois de consolidação — a hipótese do brief está refutada. E ele tem 176 das suas 337
   horas em agosto–setembro, 1ª metade −0,0960 contra 2ª metade +0,2000, e o maior C5 (22,5 %): é
   candidato a disfarce de calendário, exatamente a assinatura da EXP-0025. **Nada aqui autoriza
   dizer "a vantagem vive na volatilidade alta"** — seria EXP nova, com pré-registro e prospectivo
   próprios.

### 6.3 O controle do `momentum` não existe, e isso é um fato sobre o roster

`momentum v11` deriva de **`v8`**, `deprecated` desde 2026-09-09T19:21Z, e o replay recusa:
`version 'momentum:v8' is not one runnable version`. Sem coorte de 90 d do pai não há Δ contra o
controle pré-registrado. Não precisou: a população própria da `v11` já é `descartar` por três
caminhos independentes (K3, `sem_vantagem_na_base`, 16 de 16 LOO negativos).

### 6.4 Réplica (regra da T3.62): os 12 mercados que não escolheram a `v10`

Nos dois braços de consolidação **toda** a expectativa está nos 4 mercados originais (+0,2104 e
+0,2293) e os 12 novos medem praticamente zero (+0,0031 e +0,0101). O Δ não exclui zero, mas a
direção é a mesma da T3.62 — e é o oposto do que uma vantagem replicável mostraria.

---

## 7. O QUE FICOU BLOQUEADO — as quatro aposentadorias

**Veredito pré-registrado: `descartar` nos quatro.** A regra permanente do Everton ("as que estão
dando ruim pode matar") manda aposentar hoje. **Não consegui**, e o motivo não é técnico:

```
$ bash infra/vps/compose.sh ops python infra/scripts/activate_strategy_version.py \
    mean_reversion v15 --deprecate --changelog '...' --dry-run
ERRO: imagem hunter-api:60f3fe6 nao existe nesta maquina.
      `ops` roda so a imagem implantada; rode `compose.sh update` (ou `up`) antes,
      nunca deixe `run` construir sozinho.
```

Às **13:45 BRT de 2026-09-10** o HEAD de `/opt/project-hunter` foi para **`60f3fe6`** (T3.79, web) —
por **outra tarefa**, não por mim. `compose.sh` deriva `GIT_SHA` do HEAD e recusa rodar `ops` quando
não existe imagem daquele SHA; a guarda é da T3.15e (achado F2) e existe para nunca construir código
não implantado rodando como dono do banco. Os workers continuam em `hunter-api:223cbff`, e não há
build em curso.

**Não contornei.** Rodar `compose.sh update` seria **implantar o trabalho de outra tarefa**, o que
não é meu. Tentei uma invocação equivalente pinada em `hunter-api:223cbff` (os dois arquivos de
compose são **idênticos** entre `223cbff` e `60f3fe6`, `git diff` vazio) e o sistema de permissões
recusou — corretamente, na minha leitura.

**O orquestrador precisa rodar, depois de `compose.sh update` (ou de voltar o checkout para o commit
implantado):**

```bash
bash infra/vps/compose.sh ops python infra/scripts/activate_strategy_version.py mean_reversion v15 \
  --deprecate --changelog 'T3.76/EXP-0026: descartada. Delta vs pai +0,0651 R mas IC 95 por blocos de dia [-0,0832; +0,2024] contem zero (n=209, 35 dias, eixo r_ex_funding); estresse fragil a custos (custos_x2 -0,0691) e dependente de metade. O portao funciona (delta pareado por mercado-barra 0,0000 em 202 barras compartilhadas); o que nao passa e a evidencia.'

bash infra/vps/compose.sh ops python infra/scripts/activate_strategy_version.py mean_reversion v16 \
  --deprecate --changelog 'T3.76/EXP-0026: descartada. Delta vs pai +0,0744 R, IC [-0,1135; +0,2362] contem zero (n=169, 30 dias); estresse fragil a custos (custos_x2 -0,0599). Toda a expectativa esta nos 4 mercados originais (+0,2293 contra +0,0101 nos 12 novos).'

bash infra/vps/compose.sh ops python infra/scripts/activate_strategy_version.py mean_reversion v17 \
  --deprecate --changelog 'T3.76/EXP-0026: descartada. Braco de falseamento; melhor ponto (+0,0613 R, PF 1,223) e mesmo assim IC [-0,1540; +0,2763] contem zero, e falha a regua editorial por DIAS (222 desfechos em apenas 21 dias). Estresse fragil a custos e dependente de metade (1a -0,0960 contra 2a +0,2000); C5 22,5 por cento, o maior dos quatro.'

bash infra/vps/compose.sh ops python infra/scripts/activate_strategy_version.py momentum v11 \
  --deprecate --changelog 'T3.76/EXP-0026: descartada por veredito medido em 90 d x 16 mercados (as_of 2026-09-10T18:11Z). Expectancy ex-funding -0,0595 R em n=1167 e 47 dias (soma -69,43 R), PF 0,815; K3 dispara; estresse sem_vantagem_na_base; positiva em 1 de 3 janelas de 30 d; leave-one-market-out negativo nos 16. O controle pre-declarado (momentum v8) esta deprecated e o replay recusa versao nao executavel, entao nao ha Delta contra o pai - o veredito e da populacao propria.'
```

**Custo de não fazer, medido:** as quatro versões continuam `active` e o `strategy-worker` avalia
**14 versões por barra** em vez de 11; o pico de `consumer_lag` do topo do minuto que eu medi chegou
a **653** contra o teto de 100 do portão do replay (§4). Elas também estão abrindo coorte
`prospective` de versões já descartadas.

---

## 8. CONCERNS HONESTOS

1. **O reparo profundo reescreveu 785 linhas de regime já usadas por decisões vivas** (§1.3). É
   correção — as horas de aquecimento de agosto agora têm as 224 horas de BTC que lhes faltavam —
   mas quem tiver cortado uma coorte por regime antes de hoje vai achar números diferentes. Quem tem
   portão está imune (o rótulo viaja no envelope); quem não tem, não.
2. **`EXP-0026` conheceu o corte in-sample do pai antes de rodar.** Está declarado como exploratório
   na própria página, e as cinco condições foram fixadas no brief às 12:10 BRT, antes de eu ler
   qualquer número. Mesmo assim, o par "hipótese e dado que a gerou" é o mesmo — a prova
   confirmatória de verdade seria o prospectivo de 30 d, e ele não foi aberto porque nenhum braço
   passou.
3. **`unavailable` não aparece no `evaluations_by_state` das filhas** (vem vazio, não zero) — é o
   falso verde do §4b item 12 e está tratado, mas vale como lembrete de que a coluna não distingue
   "nenhum" de "não medido".
4. **A `momentum v11` não tem controle** e nunca terá sem reviver a `momentum v8`. Registrei o
   caminho; a decisão é de quem cuida do roster.
5. **`--explain-ledger` gravou 48 JSONL dentro do container** (`/tmp/t376-*.jsonl`) e eles somem no
   próximo recreate. Não os trouxe para cá: são ~552 mil linhas e o que eu precisava deles (o funil
   por estado) está agregado em `replay_runs.evaluations_by_state`, que é durável.

## 9. SQL DE PESQUISA

| arquivo | o que responde |
|---|---|
| `2026-09-10-t376-q00-cobertura-regime-e-velas.sql` | a linha de base antes do backfill: cobertura de `market_regimes`, vela do BTC por mês, maior buraco, universo |
| `2026-09-10-t376-q01-custo-da-leitura-do-universo.sql` | quanto custa a fase de leitura de uma passada de 90 d, medido antes de escrever |
| `2026-09-10-t376-q02-cobertura-depois-do-backfill.sql` | cobertura depois (100 %), horas por rótulo por mês e por janela, horas elegíveis por braço, onde ficou o aquecimento e por quê |
| `2026-09-10-t376-q03-coorte-v10-por-regime.sql` | a coorte do pai cortada pelo rótulo que o portão usaria — a expectativa de `n` de cada braço, sem gastar CPU |
| `2026-09-10-t376-q04-dump-decisoes-bracos.sql` | dump por decisão (CSV) dos quatro braços e do controle, com `source_bar_close` e rótulo, para o bootstrap local |
| `2026-09-10-t376-q05-funil-k-e-cobertura.sql` | K1–K5, K4 lido no pai, fração `ineligible` da filha, cobertura de `R_net`, funil de saída |

Receita de leitura (somente leitura, `repeatable read read only`, `statement_timeout = 240s`):

```bash
timeout 290 ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter \
  -v ON_ERROR_STOP=1 -f -" < infra/scripts/sql/research/2026-09-10-t376-q02-cobertura-depois-do-backfill.sql
```
