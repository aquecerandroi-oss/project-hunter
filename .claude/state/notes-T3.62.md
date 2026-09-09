# notes-T3.62 — 16 mercados, 806 decisões: a vantagem da `mean_reversion` estava nos quatro mercados que geraram a hipótese

**Data:** 2026-09-09, 16:15 → 17:40 BRT (19:15 → 20:40 UTC).
**Owner:** quant-engineer. **Pedido do Everton (15:55 BRT):** *"está com 100 operações, joga 200 nela"*.
**Base local:** `main @ d450038` (a VPS está no mesmo `d450038`; `hunter-strategy-worker-1` roda a imagem `3c9a8d8`).
**Nada commitado.** **Nenhum container parado ou recriado** (o `ops` é um `run --rm` de um disparo, o caminho auditado do `DEPLOYMENT.md` §"backfill").
**Nenhum `.env*` tocado.** **Nenhum `git pull` na VPS.**
**Escritas na VPS:** só (i) 32 corridas de replay pelo CLI de replay e (ii) **um** `request_backfill.py --days 90 --markets <os 16>` pelo `ops`. Todo o resto foi lido em `repeatable read read only`; as 4 passadas de estresse são `READ ONLY` por construção.

---

## STATUS

**DONE_WITH_CONCERNS.**

| # | Entrega do brief | Resultado |
|---|---|---|
| A | Replay de `v6`, `v10`, `v8`, `v2` em 31 d × **16 mercados**, coortes explícitas, fatias ≤ 4 mercados | **OK.** 32 corridas, 190 464 barras, **806 decisões**, 0 erros, 0 desfecho aberto |
| A | n, expectativa bruta/líquida, PF, pedágio p50, decomposição por mercado (K6), IC por blocos de dia, réplica 4 vs 12, metades, bootstrap, estresse | **OK.** §4–§7 |
| B | `request_backfill.py --days 90 --dry-run`, depois a corrida real se limitada | **OK com ressalva.** Limitada aos 16 mercados: 208 pedidos, todos enfileirados e despachados. **Só entrega 70 d, não 90** — a partição `candles_1m_2026_06` não existe (§8) |
| B | Como acompanhar e quando o replay de 90 d fica possível | **OK.** §8.3–§8.4, `q20` |
| C | ≤ 10 linhas em português | **OK.** §10 |

**O resultado em uma frase:** com 4 mercados a família parecia ter vantagem em toda versão; com 16, **três das quatro versões morrem** e a única que sobrevive ao estresse (`v10`, ATR de 1 h) tem o IC por blocos de dia **cruzando zero** — e nas quatro versões, sem exceção, os 4 mercados originais rendem mais que os 12 novos, que é a assinatura de seleção que 31 dias não conseguem desmentir.

---

## ARQUIVOS

| Arquivo | O quê |
|---|---|
| `infra/scripts/sql/research/2026-09-09-t362-q00-catalogo.sql` | catálogo vivo da família antes de qualquer escrita |
| `infra/scripts/sql/research/2026-09-09-t362-q01-cobertura.sql` | cobertura de velas dos 16 mercados + profundidade real |
| `infra/scripts/sql/research/2026-09-09-t362-q10-populacoes.sql` | populações, pedágio, expectativa, C5 |
| `infra/scripts/sql/research/2026-09-09-t362-q11-dump.sql` | dump por decisão (CSV) |
| `infra/scripts/sql/research/2026-09-09-t362-q12-recibos-isolamento.sql` | recibos das 32 corridas, K5, isolamento |
| `infra/scripts/sql/research/2026-09-09-t362-q20-backfill-progresso.sql` | acompanhamento do backfill (rodar de novo depois) |
| `.claude/state/exp-drafts/t362/analise.py` | K6, réplica 4 vs 12, metades, IC por blocos de dia (NumPy; sem pandas) |
| `.claude/state/exp-drafts/t362-decisoes.csv` | as 801 decisões com R lidas da VPS |
| `.claude/state/notes-T3.62.md` | este arquivo |

Todos com raiz em `C:\dev\project-hunter\`.

---

## 1. O QUE ESTAVA VIVO ANTES DE QUALQUER ESCRITA

```
$ ssh hunter-vps 'date -u; git -C /opt/project-hunter rev-parse --short HEAD; docker ps ...'
Wed Sep  9 19:15:44 UTC 2026            (16:15:44 BRT)
d450038
hunter-web-1               hunter-web:d450038   Up 46 minutes (healthy)
hunter-api-1               hunter-api:d450038   Up 46 minutes (healthy)
hunter-strategy-worker-1   hunter-api:3c9a8d8   Up 57 minutes (healthy)
hunter-scanner-worker-1    hunter-api:d21a11d   Up 4 hours (healthy)
hunter-execution-worker-1  hunter-api:d21a11d   Up 4 hours (healthy)
hunter-market-worker-{1,1-1,2-1,3-1,spot-1}     Up 4 hours (healthy)
hunter-caddy-1 / hunter-postgres-1 / hunter-redis-1   Up 2 days
```

**A faixa de replay estava livre.** A última corrida de outro agente terminou às 18:43 UTC
(`trendline_bounce v1`); a primeira minha começou às 19:19 UTC. Nenhuma corrida minha dividiu a
faixa com outro agente — todas as 32 foram sequenciais, 3 workers cada (o teto do
`REPLAY_CPU_SHARE = 0,33` sobre 12 vCPU).

### 1.1 As quatro versões, como estavam (q00)

| versão | estado | `atr_pct_min` | `stop_atr` | alvos | `atr_timeframe`/`atr_bars` | portão |
|---|---|---|---|---|---|---|
| `v2` | active | 0,008 | **1,0** | 1,5 / 2,5 | 15m / 97 | — |
| `v6` | active | 0,008 | **1,5** | 2,25 / 3,75 | 15m / 97 | — |
| `v8` | active | **0,006** | 1,5 | 2,25 / 3,75 | 15m / 97 | — |
| `v10` | active | 0,008 | 1,5 | 2,25 / 3,75 | **1h / 24** | — |

Nenhuma tem `eligibility_policy`, então **K4 é mensurável** nas quatro (ao contrário das `v11`–`v13`,
que têm portão — `PIPELINE.md` §4b item 12). Todas `research_only`, todas com o mesmo `code_ref`
(sufixo `239dadc3f0bd395f`): a diferença entre elas é **só parâmetro**, o que é a condição para o
contraste ser sobre o parâmetro e não sobre o código.

### 1.2 Os 16 mercados e a janela (q01)

Os 16 da `notes-T3.54.md` q00, conferidos de novo antes de rodar. **Os 16 são idênticos entre si**:
primeira vela em `2026-08-08 03:32 UTC`, 44 428 minutos finais na janela de 31 d = **99,53 %** de
cobertura. Os 212 minutos que faltam são os de `2026-08-08 00:00 → 03:32` — é exatamente isso que
produz os `unavailable: 448` da primeira fatia de cada corrida (aquecimento, não buraco).

```
4 originais (os que geraram a hipótese):  ETHUSDT SOLUSDT XRPUSDT DOGEUSDT
12 novos:  BTCUSDT BNBUSDT ZECUSDT SUIUSDT NEARUSDT UNIUSDT ARBUSDT TAOUSDT
           LINKUSDT DASHUSDT PROMUSDT SAHARAUSDT
```

---

## 2. AS 32 CORRIDAS (recibos)

Uma coorte por versão, **quatro fatias de mercado × duas fatias de janela** dentro dela:

| versão | coorte |
|---|---|
| `mean_reversion v6` | `replay:85418f7a-bc4f-4417-ae84-4311ec1d1375` |
| `mean_reversion v10` | `replay:d82356d9-65dd-4d6d-ab7a-5ed3ce28b755` |
| `mean_reversion v8` | `replay:3684ac55-49a8-4ffb-a670-d4c7419d9870` |
| `mean_reversion v2` | `replay:99fdba70-d6a9-452f-950e-324ea35828b0` |

O comando, verbatim (uma das 32; as outras só trocam versão, coorte, mercados e janela):

```
$ timeout 290 ssh hunter-vps "docker exec hunter-strategy-worker-1 \
    python -m hunter_strategy_worker.replay.run \
    --version mean_reversion:v10 --from 2026-08-08 --to 2026-08-23 \
    --markets ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT --workers 3 \
    --cohort replay:d82356d9-65dd-4d6d-ab7a-5ed3ce28b755 \
    --explain-ledger /tmp/t362-v10-s1-a.jsonl"
{'bars_evaluated': 5760, 'signals': 18, 'outcomes_resolved': 18, 'outcomes_open': 0,
 'seconds': 88.623, 'evaluations_by_state': {'unavailable': 448, 'not_triggered': 5277,
 'triggered': 35}, 'errors': 0, 'context_minutes': 1560}
```

Fatias de mercado: `s1` = os 4 originais · `s2` = BTC/BNB/ZEC/SUI · `s3` = NEAR/UNI/ARB/TAO ·
`s4` = LINK/DASH/PROM/SAHARA. Fatias de janela: `a` = 08-08→08-23 (5 760 barras),
`b` = 08-23→09-08 (6 144 barras). **Nenhuma corrida passou de 113 s**; o `timeout 290` nunca
chegou perto de disparar.

**Totais por versão** (`sig` é cumulativo por `run_id` — a armadilha do denominador da T3.33e/T3.40/T3.54):

| versão | barras | decisões | desfechos | abertos | erros | `triggered` |
|---|---:|---:|---:|---:|---:|---:|
| `v6` | 47 616 | **147** | 147 | 0 | 0 | 283 |
| `v10` | 47 616 | **282** | 282 | 0 | 0 | 591 |
| `v8` | 47 616 | **215** | 215 | 0 | 0 | 425 |
| `v2` | 47 616 | **162** | 162 | 0 | 0 | 283 |
| **família** | **190 464** | **806** | 806 | 0 | 0 | — |

**O pedido do Everton está atendido com folga:** 806 decisões na família, 282 só na `v10`.

### 2.1 A replicação exata das corridas antigas (a prova de que o motor é determinístico)

A fatia `s1` é **os mesmos 4 mercados e as mesmas janelas** da T3.47 e da T3.54. Os números batem
dígito a dígito:

| | T3.47/T3.54 | T3.62 `s1` |
|---|---|---|
| `v6` 08-08→08-23 | 11 decisões, `triggered` 22 | **11**, `triggered` **22** |
| `v6` 08-23→09-08 | 15 (cum.), `triggered` 8 | **15**, `triggered` **8** |
| `v10` 08-08→08-23 | 18 decisões, `triggered` 35 | **18**, `triggered` **35** |
| `v10` 08-23→09-08 | 54 (cum.), `triggered` 73 | **54**, `triggered` **73** |

E a `v2` reproduz o `triggered` da `v6` (22 e 8) — as duas têm o mesmo `atr_pct_min = 0,008`, então
**a porta de entrada é a mesma e o stop só muda o que acontece depois**, exatamente como a T3.47
mediu. Isto não é decoração: significa que a diferença entre esta leitura e as anteriores é **só**
os 12 mercados novos, não uma mudança de motor, de dado ou de custo.

### 2.2 Livros-razão

`bars = lines` nos 32 arquivos `/tmp/t362-*.jsonl`: 16 × 5 760 + 16 × 6 144 = **190 464** linhas,
mais 4 linhas de recibo de estresse = 190 468 (`wc -l` verbatim na saída da tarefa).

### 2.3 CONCERN 1 — `replay_runs` só guardou 8 das 32 corridas

`ledger._INSERT_SLICE` tem `ON CONFLICT (run_id, window_from, window_to) DO NOTHING`. A chave
**não inclui os mercados**. Como esta tarefa usou *uma coorte por versão* com *quatro fatias de
mercado dentro da mesma janela*, só a **primeira** fatia de cada janela deixou linha durável:
`replay_runs` mostra `mkts = 4, bars = 5760, signals = 11` para a `v6`, quando o trabalho real foi
16 mercados, 47 616 barras e 147 decisões.

O recibo completo existe — em `system_events` (`replay_engine` / `replay_run_finished`, **32 linhas**,
com `market_count`, `bars_evaluated`, `errors` e a lista de mercados no `data`) e nos 32 JSONL. A
consulta `q12` §2 lê de lá, e o cabeçalho do arquivo SQL registra o motivo.

**Por que não usei uma coorte por fatia de mercado (que não teria o problema):** o `--stress` recebe
**uma** coorte e é ele que produz o veredito (`robusto` / `frágil a custos` / `dependente de
mercado`). Quatro coortes por versão dariam quatro estresses de 4 mercados cada e **nenhum** estresse
sobre os 16 — que é justamente o que o brief pede. O custo (o recibo durável ficar incompleto) é
menor que o benefício, mas é um custo real e fica declarado. *Sugestão para quem mexer no motor:*
`uq_replay_runs_slice` deveria incluir um digest dos mercados, ou `record_slice` deveria somar em vez
de recusar.

### 2.4 Isolamento (q12 §4)

```
+------------------+-----------+
| linhas_de_outbox | propostas |
+------------------+-----------+
|                0 |         0 |
+------------------+-----------+
```

Nenhuma das 806 decisões virou linha de `shadow_outbox` ou de `trade_proposals`. Tudo
`research_only`, tudo em coorte `replay:` — que a ponte de execução recusa pelo nome
(`cohort_not_live`) e que, desde a T3.19b, nem chega a ganhar linha de outbox para ser recusada.

### 2.5 CONCERN 4 — a árvore é compartilhada e dois dos meus arquivos foram commitados por outro agente

**Eu não commitei nada.** Mas a VPS/árvore andou muito durante a janela: `HEAD` saiu de `d450038`
(quando comecei) para `d45d879` (quando terminei), passando por `973e1ac`, `c6c5fdb`, `d96c7f1`. O
commit `973e1ac` (T3.59c/T3.57b, de outro agente) **varreu para dentro dele os meus dois primeiros
arquivos de pesquisa** — `2026-09-09-t362-q00-catalogo.sql` e `2026-09-09-t362-q01-cobertura.sql` —
que estavam no disco como untracked quando aquele agente fez um `add` de diretório. Eles aparecem
hoje como *tracked e não modificados*, com o conteúdo certo; o efeito é só que a autoria da T3.62
ficou dentro de um commit da T3.59c. É exatamente o incidente que a regra "commit por pathspec,
nunca `add` de diretório" existe para evitar.

**Outro agente mediu a mesma família na mesma janela.** O commit `d96c7f1` (T3.66) diz *"v10 a 1 dia
da régua (335 decisões, 29 dias)"* e *"621 decisões recaminhadas"*. Isso é uma coorte **diferente**
da minha (as minhas são filtradas por UUID de coorte e a `v10` tem 282 decisões em 16 mercados);
nada se mistura. Mas vale como oportunidade de checagem cruzada: duas medidas independentes da
`v10` no mesmo dia, com universos diferentes, deveriam concordar no sinal. **As 32 corridas minhas
não dividiram a faixa de replay com ninguém** — todas terminaram entre 86 e 113 s, com 0 erro.

---

## 3. OS PORTÕES K1–K6 (régua congelada do EXP-0017/0018/0019)

| critério | limiar | `v6` | `v10` | `v8` | `v2` |
|---|---|---|---|---|---|
| **K1** população mínima | < 20 decisões | 147 ✔ | 282 ✔ | 215 ✔ | 162 ✔ |
| **K2** população saturada | > 1 500 | 147 ✔ | 282 ✔ | 215 ✔ | 162 ✔ |
| **K3** ≥ 100 desfechos **e** ≥ 30 dias | — | 146 desf., **23 d** ✘ | 281 desf., **30 d** ✔ | 214 desf., **25 d** ✘ | 160 desf., **23 d** ✘ |
| **K4** `unavailable` > 40 % das barras | 40 % | **0,94 %** ✔ | 0,94 % ✔ | 0,94 % ✔ | 0,94 % ✔ |
| **K5** cobertura de `R_net` < 70 % | 70 % | **99,32 %** ✔ | **99,65 %** ✔ | **99,53 %** ✔ | **98,77 %** ✔ |
| **K6** ≥ 60 % das decisões num mercado | 60 % | 17,1 % (PROM) ✔ | **10,7 %** (ZEC) ✔ | 12,6 % (ZEC) ✔ | 18,8 % (PROM) ✔ |

**K3 dispara em três das quatro** por dias distintos (23, 25, 23 contra os 30 exigidos) — a `v10` é a
única que cobre 30 dias distintos, porque é a que decide mais. Isto **não** mata: é o portão que a
janela de 70 d do §8 fecha sozinho.

**K4 = 0,94 %** nas quatro (448 barras `unavailable` de 47 616), e todas as 448 estão na primeira
fatia, no aquecimento de 2026-08-08 00:00→03:32. Não há buraco de janela em lugar nenhum.

**K5:** as 5 decisões sem `R` são 4 `funding_indeterminado` (o desfecho cai numa fronteira de
liquidação de funding e a perna não é determinável — `meta.funding.reason = funding_ambiguous_exit`)
e 1 `no_entry` da `v2` em ZECUSDT (o sinal existiu, a entrada não confirmou em 120 s). Nenhuma é
resultado escondido.

**K6 não dispara em lugar nenhum, e a melhora é grande:** com 4 mercados os recortes ficavam em
29–41 %; com 16, o maior mercado de qualquer versão é **18,8 %**. A concentração era artefato do
universo, e agora não é mais.

---

## 4. O RESULTADO POOLED (q10, `read_at = 2026-09-09T20:17:30,894655Z` = 17:17:30 BRT)

```
+--------------------+----------+-----+------+-------------+---------------+-----------------+---------------+-------------+---------------+--------+--------+------------+------------+--------------+--------------+
|       versao       |  coorte  |  n  | dias | atr_pct_p50 | risco_pct_p50 | pedagio_medio_r | pedagio_p50_r | exp_bruta_r | exp_liquida_r |  dp_r  | soma_r | pf_liquido | acerto_pct | fora_piso_c5 | fora_teto_c5 |
+--------------------+----------+-----+------+-------------+---------------+-----------------+---------------+-------------+---------------+--------+--------+------------+------------+--------------+--------------+
| mean_reversion v10 | d82356d9 | 281 |   30 |     0.01512 |       0.02334 |          0.0900 |        0.0860 |      0.2016 |        0.1105 | 0.7521 |  31.04 |     1.4512 |       55.5 |            0 |           84 |
| mean_reversion v2  | 99fdba70 | 160 |   23 |     0.01280 |       0.01313 |          0.1509 |        0.1515 |      0.2285 |        0.0776 | 1.1452 |  12.41 |     1.1513 |       51.9 |            0 |           10 |
| mean_reversion v6  | 85418f7a | 146 |   23 |     0.01290 |       0.02015 |          0.1059 |        0.0987 |      0.1276 |        0.0233 | 1.0211 |   3.40 |     1.0518 |       51.4 |            1 |           32 |
| mean_reversion v8  | 3684ac55 | 214 |   25 |     0.00983 |       0.01535 |          0.1317 |        0.1300 |      0.1289 |       -0.0027 | 1.0322 |  -0.57 |     0.9944 |       50.9 |            1 |           32 |
+--------------------+----------+-----+------+-------------+---------------+-----------------+---------------+-------------+---------------+--------+--------+------------+------------+--------------+--------------+
```

Com o IC 95 % por bootstrap de blocos de dia (20 000 reamostragens, semente 20260909; o bloco é o
**dia inteiro**, porque é assim que a dependência intradiária entre mercados aparece):

| versão | n | bruta (R) | **líquida (R)** | PF | pedágio p50 | IC 95 % da líquida | dias |
|---|---:|---:|---:|---:|---:|---|---:|
| `v10` (ATR 1 h) | 281 | +0,2016 | **+0,1105** | **1,451** | **0,0860 R** | **[−0,0754; +0,2839]** | 30 |
| `v2` (stop 1,0) | 160 | +0,2285 | +0,0776 | 1,151 | 0,1515 R | [−0,0988; +0,2539] | 23 |
| `v6` (stop 1,5) | 146 | +0,1276 | +0,0233 | 1,052 | 0,0987 R | [−0,1722; +0,2175] | 23 |
| `v8` (piso 0,006) | 214 | +0,1289 | **−0,0027** | 0,994 | 0,1300 R | [−0,2325; +0,2034] | 25 |

**Três leituras que valem registrar:**

1. **O pedágio é a metade da história, e a `v10` continua ganhando dele.** O eixo de timeframe da
   T3.54 se confirma em 16 mercados: pedágio p50 **0,0860 R** na `v10` contra **0,1515 R** na `v2`
   — 1,76× mais barato, pelo mesmo motivo de sempre (um ATR de 1 h dá um stop maior em preço, e o
   custo fixo de ida-e-volta pesa menos sobre ele). O bruto da `v2` é **maior** (+0,2285 contra
   +0,2016) e o líquido é **menor**: a `v10` não acha movimentos melhores, ela paga menos por eles.
2. **Nenhum IC exclui zero.** Nem o da `v10`. Com 30 dias e blocos de dia, 281 decisões não bastam:
   o IC é [−0,0754; +0,2839] e a metade inferior é negativa. A leitura honesta é *"positiva e ainda
   não distinguível de zero"*, não *"tem vantagem"*.
3. **A `v8` (piso de ATR mais baixo, 0,006) morre.** Bruto +0,1289 — o mesmo da `v6` — e pedágio
   0,1300 R, o mais caro depois da `v2`: baixar o piso de ATR admite justamente as barras em que o
   custo fixo come tudo. Líquido −0,0027, PF 0,994. É a confirmação, em 16 mercados, do que o
   EXP-0019 já dizia com 4.

---

## 5. A VISTA DE REPLICAÇÃO — 4 originais vs 12 novos (o coração da tarefa)

Os 4 mercados originais (ETH/SOL/XRP/DOGE) são os que **geraram** a hipótese: a `mean_reversion`
nasceu do EXP-0009 olhando para eles. Os 12 novos nunca participaram de nenhuma escolha de
parâmetro. Se a vantagem for real, ela aparece nos dois grupos; se for seleção, ela fica nos 4.

| versão | 4 originais | 12 novos | Δ (novos − originais) e IC 95 % |
|---|---|---|---|
| `v6` | n=15, **+0,2861 R**, PF 2,282 | n=131, **−0,0068 R**, PF 0,986 | **−0,3361** [−0,9519; +0,0354] |
| `v10` | n=54, **+0,2013 R**, PF 2,496 | n=227, **+0,0888 R**, PF 1,328 | **−0,1058** [−0,2935; +0,0696] |
| `v8` | n=33, +0,0855 R, PF 1,226 | n=181, −0,0187 R, PF 0,962 | −0,0978 [−0,5218; +0,3237] |
| `v2` | n=17, +0,2998 R, PF 1,748 | n=143, +0,0511 R, PF 1,097 | −0,2468 [−0,9010; +0,4479] |

(o Δ é pareado **por dia**: o bootstrap reamostra os mesmos dias para os dois grupos, senão estaria
comparando dois calendários diferentes.)

**Quatro versões, quatro vezes o mesmo sinal: os originais rendem mais.** Nenhum Δ individual exclui
zero — todos os quatro IC contêm zero, e nos dois com n pequeno do lado original (`v6` n=15, `v2`
n=17) o IC é largo demais para dizer qualquer coisa. Mas o **sinal** é o mesmo nas quatro, e a
magnitude é grande: na `v6`, os 12 novos entregam **−0,0068 R**, ou seja, **zero**, contra +0,2861 R
dos 4 originais.

**A ressalva estatística, escrita antes da conclusão:** as quatro versões **não são independentes** —
`v2`, `v6` e `v10` têm o mesmo `atr_pct_min = 0,008` e portanto a mesma porta de entrada, e a `v8`
só afrouxa o piso. Elas decidem em cima de barras que se sobrepõem muito. Então "4 de 4 com o mesmo
sinal" **não** é um teste de sinal com p = 1/16; é um resultado só, visto por quatro lentes
correlacionadas. O que ele autoriza a dizer é: **a vantagem medida com 4 mercados não replicou nos 12
que não participaram da escolha**, e é isso.

**O caso da `v10` é o menos ruim da família:** os 12 novos ainda entregam **+0,0888 R com PF 1,328**
em 227 decisões — positivo, não zero. A `v10` é a única versão da família em que o grupo de
replicação, sozinho, é positivo.

---

## 6. AS METADES, E O EIXO QUE DE FATO EXPLICA O RESULTADO

| versão | 1ª metade (até 23/08) | 2ª metade (23/08 → 08/09) |
|---|---|---|
| `v6` | n=51, **+0,2056 R**, PF 1,583 | n=95, **−0,0746 R**, PF 0,851 |
| `v10` | n=111, **+0,2454 R**, PF 2,272 | n=170, **+0,0224 R**, PF 1,080 |
| `v8` | n=69, **+0,2795 R**, PF 1,918 | n=145, **−0,1369 R**, PF 0,751 |
| `v2` | n=58, **+0,2485 R**, PF 1,590 | n=102, **−0,0196 R**, PF 0,965 |

**Nas quatro versões a primeira metade é forte e a segunda é ~zero ou negativa** — e a queda é
**maior** que a diferença entre os grupos de mercado. Este é o achado que a T3.54 já tinha visto na
`v6` com 4 mercados ("primeira metade ~zero, segunda −0,0668" na `momentum`; aqui o padrão da
`mean_reversion` é o inverso e mais nítido) e que agora aparece nas quatro versões e nos 16 mercados
ao mesmo tempo.

**Interpretação, com a incerteza que ela merece:** duas metades de ~15 dias cada não separam "o
regime mudou" de "a primeira metade teve sorte". O que dá para dizer é que **o eixo temporal explica
mais da variação do que o eixo de mercado** — e que qualquer decisão de promoção tomada com a
primeira metade estaria tomando 15 dias de fita por evidência. É exatamente o buraco que a janela de
70 dias do §8 existe para tapar.

---

## 7. AS QUATRO PASSADAS DE ESTRESSE (16 mercados, `READ ONLY`)

Comando: `docker exec hunter-strategy-worker-1 python -m hunter_strategy_worker.replay.run --stress replay:<uuid> --ledger /tmp/t362-stress-<v>.jsonl`.

| versão | veredito | `custos_x2` | `entrada_mais_1_barra` | pior recorte por mercado | 2ª metade |
|---|---|---|---|---|---|
| **`v10`** | **`robusto`** | **+0,0202** (PF 1,072) | +0,1292 | `sem ETHUSDT` **+0,0992** | **+0,0409** |
| `v6` | `frágil a custos` + dependente de mercado + de metade | −0,0772 (PF 0,841) | +0,0409 | `sem NEARUSDT` **−0,0032** | −0,0606 |
| `v2` | `frágil a custos` + dependente de metade | −0,0683 (PF 0,878) | +0,0723 | `sem XRPUSDT` +0,0588 | −0,0000 |
| `v8` | `sem_vantagem_na_base` | −0,1271 (PF 0,754) | +0,0052 | `sem ETHUSDT` −0,0190 | −0,1404 |

**A `v10` é a primeira versão da família a sair `robusto` de um estresse.** Ela sobrevive a custo
dobrado (mal: +0,0202 R, PF 1,072 — sobra pouco), a entrada atrasada (melhora, +0,1292), aos 16
recortes de mercado (o pior é +0,0992, ainda positivo) e às duas metades (a pior é +0,0409, ainda
positiva). Nenhuma outra versão da família chega perto.

**A `v6` mostra o que 16 mercados fazem com um resultado de 4:** na T3.47/T3.54 ela era a coorte de
`mean_reversion` mais bem-comportada que já tínhamos (+0,2664 e +0,1452 nas duas metades, positiva
nos quatro recortes). Aqui ela sai frágil a custos, dependente de um mercado (`sem NEARUSDT` já a
leva a **−0,0032**) e dependente de metade. Não foi o método que mudou; foi o universo.

**Nota de leitura:** o estresse corta as metades por **instante de entrada** e a minha análise local
por **data de emissão**, então os n das metades diferem um pouco (`v10`: 120/161 no estresse,
111/170 na minha). Os dois cortes concordam no sinal e na ordem de grandeza; a diferença é de
fronteira, não de conteúdo.

### 7.1 CONCERN 2 — C5: a `v10` põe 29,9 % das decisões acima do teto de risco

A banda `paper_v1` é `[0,003; 0,03]` (`packages/risk-core/hunter_risk/limits.py:151-152`).

| versão | abaixo do piso | acima do teto | risco % p50 |
|---|---:|---:|---:|
| `v10` | 0 | **84 (29,9 %)** | 0,02334 |
| `v6` | 1 | 32 (21,9 %) | 0,02015 |
| `v8` | 1 | 32 (15,0 %) | 0,01535 |
| `v2` | 0 | 10 (6,2 %) | 0,01313 |

A T3.54 mediu **11,1 %** para a `v10` com 4 mercados; com 16 são **29,9 %**. Os 12 novos são, em
mediana, mais voláteis que os 4 originais (a tabela de ATR% da T3.54 §2 já dizia isso: PROM 1,86 %,
DASH 0,75 %, ZEC 0,75 % contra ETH 0,31 % e XRP 0,41 %), e um stop de 1,5 × ATR de 1 h sobre eles
estoura o teto de 3 %. **Consequência prática: a `v10` como está não é candidata a `paper` no
universo de 16 mercados** — quase um terço das decisões dela seria recusada pelo sizing, e uma
população recortada pelo teto de risco é uma população diferente da que foi medida aqui. Baixar
`stop_atr` ou subir o teto são as duas saídas, e as duas são **versão nova**, não ajuste.

---

## 8. PARTE B — MAIS HISTÓRICO PARA OS 16 MERCADOS

### 8.0 A ordem dos atos importou, e deu certo por pouco

Os 32 replays terminaram às **20:16:58 UTC**; o backfill foi enfileirado às **20:24 UTC**. Isso não
é detalhe: o backfill traz velas **anteriores** a `2026-08-08 03:32`, e a janela de contexto de uma
avaliação é de 1 560 min (26 h). Depois que o dreno passar, **repetir exatamente os mesmos 32
comandos não daria exatamente os mesmos 806 números** — as ~26 primeiras horas da janela, que hoje
saem em aquecimento (`unavailable: 448`), passariam a ter contexto completo e poderiam produzir
decisões que hoje não existem.

As coortes desta tarefa estão **congeladas** (as decisões estão persistidas e o `--stress`
reprecifica o que está gravado), e elas são comparáveis dígito a dígito com a T3.47 e a T3.54 —
§2.1 prova isso. Quem repetir o replay de 31 d **depois** do dreno tem de tratar o resultado como
uma coorte **nova**, não como a mesma. O caminho certo, e o que este backfill existe para permitir,
é refazer em **70 d**, o que já é outra pergunta.

### 8.1 O que o script permite (lido antes de rodar)

`infra/scripts/request_backfill.py` **aceita `--markets`** (`backfill_targets.targets_for`: uma lista
nomeada é usada exatamente como dada, sem acrescentar o BTC por conta própria — e o BTC já está nos
16). Então **não** foi preciso pedir o universo inteiro: o pedido foi restrito aos 16, como o brief
pediu. Três propriedades do contrato que decidem o formato (`DEPLOYMENT.md` §"Profundidade de
histórico para o β", `PIPELINE.md` §1b):

- **7 dias por pedido.** Uma janela maior é *truncada silenciosamente* para os 7 dias mais recentes,
  então o script corta a faixa em janelas inteiras de 7 d e publica **da mais nova para a mais antiga**.
- **A identidade é a janela** (`uuid5` sobre `(stream, market_id, gap_start, gap_end)`): pedir duas
  vezes é um pedido só.
- **O script não chama REST.** Ele enfileira na outbox; quem busca é o `market-worker`, sob o
  orçamento que já é dele (`MAX_HISTORY_GAPS_PER_CYCLE = 6` pedaços de 240 min por ciclo de 60 s,
  **por shard**, e só com o que a coleta viva deixou).

### 8.2 O `--dry-run` e a corrida real

```
$ timeout 290 ssh hunter-vps "cd /opt/project-hunter && bash infra/vps/compose.sh ops \
    python infra/scripts/request_backfill.py --days 90 \
    --markets BTCUSDT,ETHUSDT,ZECUSDT,SOLUSDT,XRPUSDT,BNBUSDT,DOGEUSDT,SUIUSDT,\
NEARUSDT,UNIUSDT,ARBUSDT,TAOUSDT,LINKUSDT,DASHUSDT,PROMUSDT,SAHARAUSDT --dry-run"
kind    candles
window  2026-06-11T19:23:00+00:00 -> 2026-09-09T20:23:00+00:00
markets 16: ARBUSDT, BNBUSDT, BTCUSDT, DASHUSDT, DOGEUSDT, ETHUSDT, LINKUSDT, NEARUSDT,
            PROMUSDT, SAHARAUSDT, SOLUSDT, SUIUSDT, TAOUSDT, UNIUSDT, XRPUSDT, ZECUSDT
windows 208 (13 per market, newest first)
WARNING partition candles_1m_2026_06 does not exist — those minutes will be refused
[dry-run] 208 request(s) would be queued on the outbox

$ ... (sem --dry-run)
208 request(s) queued on outbox_events
```

**Por que rodei a corrida real sem voltar ao orquestrador:** o brief autoriza *"depois a corrida real
se limitada"*. Ela é limitada em três sentidos verificáveis: 208 eventos (não o universo de 217
mercados, que seriam ~2 800), idempotentes por `uuid5`, e drenados pelo orçamento que o coletor já
tem — nada aqui pode roubar ciclo da faixa viva, por construção (`recovery.py`: o estrato histórico
gasta *o que sobrou* de `MAX_GAPS_PER_CYCLE`, com deadline de 30 s).

### 8.3 CONCERN 3 — a partição de junho não existe: o pedido entrega 70 d, não 90

As partições de `candles_1m` na VPS vão de `2026_07` a `2026_12`. **`candles_1m_2026_06` não
existe.** O consumidor trata minuto sem partição como *bloqueado*: ele não entra no plano, e um
pedido cujos minutos são **todos** de junho é recusado com `no_partition`. Medido depois da corrida
— os 16 mercados ficaram com **224 a 229 pedaços abertos cada, todos começando em
`2026-07-01 00:00 UTC`**:

```
| ARBUSDT    | open      |     228 | 2026-07-01 00:00:00+00 | 2026-08-07 20:23:00+00 |
| BTCUSDT    | open      |     228 | 2026-07-01 00:00:00+00 | 2026-08-07 20:23:00+00 |
| ...        |           |         |                        |                        |
| ZECUSDT    | open      |     229 | 2026-07-01 00:00:00+00 | 2026-08-08 00:23:00+00 |
```

**O que isso custa e o que não custa.** A janela que este backfill entrega é
**2026-07-01 → 2026-09-09 = 70 dias**, não 90. E o que falta de junho **não é perdido**: por desenho
(`backfill.py`, docstring "*An acknowledgement is not always a mark*"), uma recusa que depende do
estado do mundo — *a partição não existe **ainda*** — é `XACK`ada **sem** marcar o `event_id` como
processado, então republicar a mesma identidade depois de a partição existir é avaliado do zero.
Nenhuma linha `unrecoverable` foi criada para junho.

**A decisão que NÃO é minha e fica com o orquestrador:** criar a partição de junho é
`create_partitions.py --months-behind 3` (ou 4), que é **escrita de esquema** pelo dono do banco — o
meu brief autoriza `request_backfill` e o CLI de replay, não DDL. Se o orquestrador quiser os 90 d
completos, a sequência é:

```bash
# 1. (decisão do orquestrador) criar as partições de junho
bash infra/vps/compose.sh ops python infra/scripts/create_partitions.py --months-behind 3
# 2. repetir o MESMO comando do §8.2 — os 32 pedidos de junho são reavaliados do zero
bash infra/vps/compose.sh ops python infra/scripts/request_backfill.py --days 90 --markets <os 16>
```

Sem o passo 1, o passo 2 é um no-op caro para junho e um no-op barato para o resto (identidade já
processada).

### 8.4 Como acompanhar o dreno, e quando o replay longo fica possível

Três leituras, todas em `infra/scripts/sql/research/2026-09-09-t362-q20-backfill-progresso.sql`
(`repeatable read read only`):

1. **A outbox esvaziou?** — já esvaziou: `pendentes 0, despachados 208` às 20:28 UTC.
2. **Quanto falta?** — `ingestion_gaps` com `status = 'open'` e `detected_at > 2026-09-09 20:20 UTC`.
   O total planejado é **~3 680 pedaços** (16 × 230), cada um de 240 min.
3. **A profundidade real** — `min(open_time)` por mercado em `candles`. **É este o número que libera
   o replay**, não a fila: o replay lê velas, não lacunas.

O heartbeat dá a mesma coisa em tempo real, por shard (`hb:market:binance:{i}of4`, campo `open_gaps`;
o irmão `unrecoverable_gaps` é o que **não** vai voltar):

```
$ ssh hunter-vps "docker exec hunter-redis-1 redis-cli HMGET 'hb:market:binance:0of4' ts open_gaps unrecoverable_gaps"
hb:market:binance:0of4  2026-09-09T20:28:43Z  1368  0
hb:market:binance:1of4  2026-09-09T20:28:42Z   448  38
hb:market:binance:2of4  2026-09-09T20:28:49Z   678   3
hb:market:binance:3of4  2026-09-09T20:28:52Z  1138 221
```

**Estimativa de quando — e ela é medida, não estimada.** Duas leituras do heartbeat separadas por
5,02 min (20:28:43 → 20:33:44 UTC) mostram **exatamente 30 pedaços drenados em cada um dos 4 shards**:

```
shard   20:28:43   20:33:44   Δ
0of4      1368       1338    -30
1of4       448        418    -30
2of4       678        648    -30
3of4      1138       1108    -30
```

São **5,98 pedaços por minuto por shard** — ou seja, o estrato histórico está recebendo o orçamento
**inteiro** (`MAX_HISTORY_GAPS_PER_CYCLE = 6` por ciclo de 60 s), e não as sobras. Taxa agregada:
**24 pedaços/min = 5 760 min de histórico por minuto de relógio**. Com **3 512 pedaços abertos** às
20:34 UTC, faltam **~146 minutos**: a janela de 70 d fica completa por volta de
**2026-09-09 23:00 UTC = 20:00 BRT de hoje**. Com margem para a coleta viva reclamar o orçamento em
algum ciclo: **entre 20:00 e 21:30 BRT**. Já dá para ver o dreno chegando —
`min(open_time)` do BTCUSDT saiu de `2026-08-08 03:32` para `2026-08-05 20:24` em 10 minutos.

**Terceira leitura, 20:38:08 UTC (17:38 BRT), confirmando a taxa:** cada shard drenou mais 24
pedaços em 4,4 min (5,45/min/shard; agregado ~22/min), restam **3 416** — faltam ~155 min, ou seja,
**~23:15 UTC = 20:15 BRT**. E a profundidade já andou: `min(open_time)` dos 16 mercados saiu de
`2026-08-08 03:32` para **`2026-08-02 16:24`** em 14 minutos — **5,7 dias de histórico ganhos**. Os
13 contêineres seguem `healthy`, `ws_state = connected` e `rest_gate = ok` nos 4 shards: o backfill
não está machucando a coleta viva.

O critério de pronto não é o relógio, é a leitura 3: `min(open_time)` = `2026-07-01` nos 16, com
densidade ≥ 99 %.

**O que a janela de 70 d compra.** Projetando linearmente as populações de 31 d
(`n × 70/31`): `v10` ~635 decisões, `v8` ~483, `v2` ~361, `v6` ~330 — e **K3 (≥ 30 dias distintos)
deixa de disparar nas quatro**. Mais importante que o n: 70 dias dão **quatro** metades de ~17 dias
em vez de duas, que é a única forma de separar "a primeira metade foi boa" de "o regime era outro".

---

## 8.5 TESTES

Esta tarefa **não escreveu código de produção** — o que ela produz é evidência, SQL de pesquisa e um
script de leitura local. Ainda assim, o recibo do código de que a leitura depende:

```
$ uv run pytest packages/core/tests/unit/strategies/test_mean_reversion_v1.py \
                packages/core/tests/unit/strategies/test_mean_reversion_h1_v1.py -q
......................................................................   [100%]
70 passed in 7.84s

$ uv run pytest services/strategy-worker/tests/test_replay_stress.py \
                services/strategy-worker/tests/test_replay_contract.py \
                services/strategy-worker/tests/test_replay_arms.py -q -p no:randomly -m "not integration"
...................................................................      [100%]
67 passed in 5.86s
```

**O que eu NÃO rodei, e por quê.** `services/strategy-worker/tests/test_replay_lookahead.py` — a
prova de que uma decisão replayada na barra `t` não lê vela que fecha depois de `t`, com o
**contra-teste** do motor que trapaceia de propósito (o corte movido 30 min para o futuro **tem** que
ser pego, senão o teste é decoração) — é `@pytest.mark.integration` e precisa de Postgres por
testcontainer. O brief desta tarefa proíbe testcontainers (incidente de 2026-09-07: 6 concorrentes
derrubaram o Docker Desktop). Ele não foi tocado por esta tarefa e está verde no `main`.

A prova empírica equivalente que **esta** tarefa produz é o §2.1: as fatias dos 4 mercados originais
reproduzem dígito a dígito as decisões e os `triggered` da T3.47 e da T3.54, rodadas em outro dia,
em outra imagem e com outra coorte.

---

## 9. VEREDITOS

| versão | veredito | por quê |
|---|---|---|
| `mean_reversion v10` | **sobrevive, não promove** | única `robusto` no estresse dos 16; líquida +0,1105 R, PF 1,451, pedágio p50 0,086 R; **mas** IC [−0,0754; +0,2839] cruza zero, `custos_x2` deixa só +0,0202 R, e 29,9 % das decisões furam o teto de risco de 3 % (C5). Refazer em 70 d antes de qualquer conversa sobre `paper` |
| `mean_reversion v2` | **descartar como está** | frágil a custos (−0,0683 sob custo dobrado), 2ª metade exatamente zero, pedágio p50 0,1515 R — o mais caro da família |
| `mean_reversion v6` | **descartar** | era a melhor coorte da família com 4 mercados e vira +0,0233 R / PF 1,052 com 16; frágil a custos, dependente de um mercado e de metade. É o caso didático de vantagem que não replicou |
| `mean_reversion v8` | **deprecar** | `sem_vantagem_na_base`: −0,0027 R, PF 0,994 em 214 decisões. Baixar o piso de ATR para 0,006 admite as barras em que o custo come o movimento — o bruto é igual ao da `v6` e o pedágio é 32 % maior |

**Nenhuma versão foi promovida, depreciada ou ativada nesta tarefa.** Eu não escrevi nada em
`strategy_versions` — as depreciações sugeridas acima são recomendação para o orquestrador, não ato.

---

## 10. AS ≤ 10 LINHAS PARA O EVERTON

> **Família `mean_reversion` em 16 mercados — 806 operações (você pediu 200).**
> 1. Rodei as 4 versões (`v6`, `v10`, `v8`, `v2`) em 31 dias × 16 mercados: **806 decisões**, zero erro.
> 2. **A família não sobrevive inteira.** Três das quatro morrem: `v8` fica em zero (PF 0,99), `v6` e `v2` quebram quando dobro os custos.
> 3. **Uma sobrevive: a `v10`** (a do ATR de 1 hora). 282 operações, **+0,11 R por operação**, PF 1,45, e passou no teste de estresse — a primeira da família a passar.
> 4. **O que mudou dos 4 para os 16:** com 4 mercados toda versão parecia boa; com 16, a vantagem some. Nas **quatro** versões os 4 mercados antigos rendem mais que os 12 novos — sinal clássico de que a vantagem estava na escolha dos mercados, não no mercado.
> 5. A `v10` é a exceção parcial: nos 12 mercados novos ela ainda dá **+0,09 R com PF 1,33**. É a única.
> 6. **Ainda não dá para promover nada.** O intervalo de confiança da `v10` vai de −0,08 a +0,28: positivo, mas ainda não distinguível de zero. E 30 % das operações dela ficariam acima do nosso teto de risco de 3 % — isso é versão nova, não ajuste.
> 7. **Pedi mais histórico** para os 16 mercados: 208 pedidos enfileirados, tudo dentro do orçamento do coletor.
> 8. **Vem 70 dias, não 90** — falta a partição de junho no banco (é um comando de esquema, deixei a decisão com o orquestrador). Os 70 dias já mais que dobram a amostra.
> 9. **Quando fica pronto:** medi a velocidade do download — a janela de 70 dias fica completa **entre 20:00 e 21:30 de hoje** (Brasília). Aí refaço as quatro versões.
> 10. Resumo em uma frase: **a `v10` é a única candidata viva da família, e ela precisa dos 70 dias para deixar de ser "positiva por sorte possível".**

---

## 11. ASSUNÇÕES NUMÉRICAS QUE EU TIVE DE FAZER

1. **O corte das metades é `2026-08-23`** (o mesmo da T3.47/T3.54), por data de emissão. O estresse
   corta por instante de entrada e chega a n ligeiramente diferentes; os dois concordam no sinal.
2. **O bootstrap usa blocos de dia, 20 000 reamostragens, semente 20260909.** O bloco é o dia inteiro
   porque as decisões do mesmo dia em mercados diferentes não são independentes (fita comum). Um
   bootstrap i.i.d. por decisão daria IC ~40 % mais estreitos e mentiria.
3. **A estimativa de tempo do backfill não é assunção: é medida** (24 pedaços/min agregados, duas
   leituras do heartbeat separadas por 5 min, §8.4). A única assunção é que a taxa **se mantém** —
   ela cai se a coleta viva passar a gastar o ciclo inteiro. Por isso o critério de pronto é a
   leitura 3 do §8.4 (`min(open_time)`), não o relógio.
4. **`r_bruto` = `(exit_base − p_entry/1,0006) / initial_risk`** e `pedágio = r_bruto − r_ex_funding`,
   idêntico à T3.47 q01 e à T3.54 q10 (KB-0076 com a correção aritmética da `notes-T3.40` §8b). O
   1,0006 é o slippage assumido de entrada, desfeito para chegar ao preço "sem custo".
5. **A projeção de população para 70 d é linear** (`n × 70/31`). Ela ignora que a densidade de
   oportunidade varia com o regime; serve para dizer "a ordem de grandeza dobra", não para prometer
   um n exato.

---

## 12. O QUE EU DELIBERADAMENTE NÃO FIZ

- **Não criei a partição de junho.** É DDL pelo dono do banco e o meu brief autoriza `request_backfill`
  e o CLI de replay. §8.3 tem o comando exato para quem decidir.
- **Não depreciei a `v8`** nem nenhuma outra, apesar do `sem_vantagem_na_base`. Depreciar é escrita em
  `strategy_versions` por script auditado, e o brief desta tarefa é medir.
- **Não rodei estresse cruzando coortes** (por exemplo, os 12 novos como coorte própria). O `--stress`
  recebe uma coorte; o recorte por mercado dele (`sem_binance:X`) já dá a decomposição, e o contraste
  4-vs-12 foi feito no dump local, onde ele é auditável linha a linha.
- **Não mexi na faixa viva, no paper, nem em nenhuma versão que a T3.61 esteja movendo.** As quatro
  versões desta tarefa são `research_only` e nenhuma tem `eligibility_policy`.
