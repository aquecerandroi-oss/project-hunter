# T3.84 — lote diário de 11/09/2026: a irmã de 5 minutos da reversão à média

Horários em **BRT (UTC−3)**, com o UTC ao lado quando ele é o que a saída mostra.

## 0. Passo 1 (contexto; não houve nota própria)

Entregue e implantado por outra passada desta mesma tarefa, commit **`e517f69`** (05:27:47 BRT):
`packages/core/hunter_core/strategies/mean_reversion_m5_v1.py` (módulo de fecho próprio,
`code_ref … @sha256:f733467f…`), 724 linhas de teste próprio, `registry.py`,
`constraints_table.py`, `infra/scripts/seed_reference.py`, `context_budget.py`, e o **pré-registro**
`obsidian/05-EXPERIMENTS/EXP-0028-mean-reversion-5-min.md` escrito **antes** de qualquer replay.
Esta nota cobre o **passo 2**.

Prova de que o contrato do passo 1 continua de pé nesta árvore:

```
$ uv run pytest packages/core/tests/unit/strategies/test_mean_reversion_m5_v1.py \
    services/strategy-worker/tests/test_context_budget.py \
    infra/scripts/tests/test_seed_dry_run.py -q
93 passed in 91.86s (0:01:31)

$ uv run pytest packages/core/tests/unit/strategies/test_mean_reversion_m5_v1.py -q \
    -k "look_ahead or antecipa or forming or nao_antecip"
5 passed, 34 deselected in 0.40s
```

Os cinco de não-antecipação são `test_it_ignores_the_future_the_forming_candle_and_a_mutated_future`,
as três parametrizações de `test_mutating_the_candle_still_forming_never_moves_the_decision` e
`test_the_forming_15m_bar_never_reaches_the_trend_gate` — a vela em formação nunca move o envelope,
nem na grade de decisão nem na porta de tendência.

## 1. RESUMO HONESTO DO PASSO 2

| # | O que o brief pediu | Resultado |
|---|---|---|
| 1 | `seed.py --only strategies` ensaio e escrita, só a linha nova | **OK** — exatamente duas linhas `NEW`, nada mais mudaria |
| 2 | ativar `mean_reversion_m5 v1` como `research_only` | **OK** — 2026-09-11T08:32:18Z (05:32:18 BRT), digest idêntico ao pré-registrado |
| 3 | replay 90 d × 16 mercados em 12 fatias via `compose.sh replay` | **BLOQUEADO** — o portão do `replay-worker` recusa **toda** corrida na VPS; causa raiz medida, §3 |
| 4 | estresse na coorte | **não feito** — depende da coorte |
| 5 | análise (blocos de dia, LOMO, 3 janelas, ATR%, pedágio, C5, K1–K6) | **parcial** — tudo o que não depende de decisão foi medido (§4): ATR%(5m), pedágio, C5. K1–K6 e os testes de retorno dependem da coorte |
| 6 | veredito EXP-0028, página da estratégia, Index, aposentar se falhar | **veredito não emitido** (§5); páginas escritas; **não aposentada**, com o motivo dito |
| 7 | notas, SQL, `obsidian_lint` | **OK** — esta nota, dois SQL, `RESULTADO: base limpa` |

**A frase que resume o dia:** o experimento não pôde ser respondido, e a medição que *foi* possível
**derrubou o principal argumento do pré-registro contra a versão**. O prior desta equipe era
`descartar` por custo; o custo medido é quase o da mãe.

## 2. PASSO 1 e 2 DO BRIEF — SEED E ATIVAÇÃO (05:31–05:32 BRT)

### 2.1 Ensaio do seed — só as duas linhas novas

```
$ ssh hunter-vps 'cd /opt/project-hunter && date -u +%FT%TZ && timeout 240 bash infra/vps/compose.sh ops \
    python infra/scripts/seed.py --only strategies --dry-run'
2026-09-11T08:31:29Z
[9 linhas "note: <key> v1 is activated and frozen at ...; this build's registry ships
 hunter_indicators.strategies.<key>_v1. Left untouched: supersede it to move the code."]
strategies.mean_reversion_m5: NEW {'key': 'mean_reversion_m5', 'name': 'Mean Reversion 5m', ...}
strategy_versions.mean_reversion_m5 v1: NEW {'version': 'v1', 'status': 'draft',
   'code_ref': 'hunter_indicators.strategies.mean_reversion_m5_v1', 'purpose': 'research_only', ...}
DRY RUN: nothing written
```

**Duas linhas de diferença, as duas `NEW`, as duas da estratégia nova.** As nove linhas `note:` não
são escritas: são o relatório de que as `v1` já ativadas estão **congeladas** e foram puladas pelo
`WHERE activated_at IS NULL` do upsert (`seed.py::_report_frozen_version`). Nenhuma outra linha
mudaria — a condição de parada do brief não foi atingida.

### 2.2 A escrita

```
$ ... seed.py --only strategies --yes
2026-09-11T08:31:43Z
strategies.mean_reversion_m5: NEW {...}
strategy_versions.mean_reversion_m5 v1: NEW {...}
seeded  14 row(s) into strategies
seeded  14 row(s) into strategy_versions
```

(`--yes` é obrigatório aqui e não é um atalho: por `ssh` sem TTY o `seed_cli` recusa uma escrita com
diff não vazio — "a write is never silent in a pipe", T3.39b MÉDIA-4.)

### 2.3 Ativação `research_only` — ensaio e escrita

```
$ ... activate_strategy_version.py mean_reversion_m5 v1 --changelog "..." --dry-run
2026-09-11T08:32:01Z
would activate mean_reversion_m5 v1 (purpose research_only) with code_ref
  hunter_core.strategies.mean_reversion_m5_v1@sha256:f733467fedc529c661f53cf84653e9c5a514d86767471757ee43679af763734b
  (18 parameters)

$ ... activate_strategy_version.py mean_reversion_m5 v1 --changelog "..."
2026-09-11T08:32:15Z
activated mean_reversion_m5 v1 (purpose research_only) at 2026-09-11T08:32:18.437633+00:00 with code_ref
  hunter_core.strategies.mean_reversion_m5_v1@sha256:f733467fedc529c661f53cf84653e9c5a514d86767471757ee43679af763734b
```

`changelog`: *"T3.84/EXP-0028: irma de 5 min da mean_reversion, research_only; pre-registro preve
descartar (pedagio por R maior na grade curta, KB-0076/KB-0086)"*.

**O digest que o banco congelou é, caractere por caractere, o que a EXP-0028 pré-registrou às
05:20 BRT** (`f733467fedc529c661f53cf84653e9c5a514d86767471757ee43679af763734b`) e são os mesmos 18
parâmetros. A página descreve a versão que existe.

## 3. O BLOQUEIO — O PORTÃO DO REPLAY FICOU CEGO QUANDO O WORKER VIVO FOI SHARDADO

### 3.1 A primeira fatia, recusada

Coorte mintada para a corrida: `replay:92c8d080-6009-4a59-9868-31282b1bd493`. Ensaio primeiro (o
ensaio **pula** o portão, por construção — `run.py`: `if not args.dry_run and (reason := ...)`):

```
$ ssh hunter-vps '... bash infra/vps/compose.sh replay python -m hunter_strategy_worker.replay.run \
    --version mean_reversion_m5:v1 --from 2026-06-12 --to 2026-07-12 \
    --markets ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT --cohort replay:92c8d080-... --dry-run'
{'cohort': 'replay:92c8d080-6009-4a59-9868-31282b1bd493', 'version': 'mean_reversion_m5 v1',
 'markets': 4, 'bars_planned': 34560, 'context_minutes': 1560, 'workers': 3}
```

`bars_planned = 34 560 = 4 × 30 × 288` (a grade de 5 min, confirmada) e `context_minutes = 1560` —
o piso, exatamente como a EXP-0028 previu: os 490 min desta versão não encarecem ninguém.

A corrida de verdade, 05:36:29 BRT:

```
refused: live lane degraded (heartbeat_missing)
```

### 3.2 A causa, medida em vez de suposta

Diagnóstico somente-leitura, rodado no próprio `replay-worker` (nenhuma escrita, nenhuma corrida):

```
heartbeat_key = hb:strategy:shadow
consumer_lag_max = 100
live_lane_degraded = heartbeat_missing
group_lag(default strategy-worker.shadow) = 50000
group_lag(strategy-worker.shadow.0of4) = 0
  live_lane_degraded(hb:strategy:shadow:0of4) = consumer_lag:50000
group_lag(strategy-worker.shadow.1of4) = 0
  live_lane_degraded(hb:strategy:shadow:1of4) = consumer_lag:50000
group_lag(strategy-worker.shadow.2of4) = 0
  live_lane_degraded(hb:strategy:shadow:2of4) = consumer_lag:50000
group_lag(strategy-worker.shadow.3of4) = 0
  live_lane_degraded(hb:strategy:shadow:3of4) = consumer_lag:50000
```

E no Redis:

```
$ redis-cli --scan --pattern "hb:strategy*"
hb:strategy:shadow:0of4  hb:strategy:shadow:1of4  hb:strategy:shadow:2of4  hb:strategy:shadow:3of4
(+ as chaves por instância; `hb:strategy:shadow` NAO existe)

$ redis-cli hgetall hb:strategy:shadow:0of4
ts 2026-09-11T08:37:09.239986+00:00   shard_index 0   shard_total 4   outbox_lag_s 0.0   errors 0

$ redis-cli XINFO CONSUMERS market.candles.closed strategy-worker.shadow
(todo consumidor com idle >= 42 828 070 ms = 11,90 h; o minimo de 57 consumidores)
```

**Dois defeitos, a mesma causa.** A T3.74f shardou o worker vivo (`STRATEGY_SHARDS=4`); a
`shard.py::heartbeat_key` passou a escrever `hb:strategy:shadow:{i}of{N}` e `consumer_group` passou a
ler `strategy-worker.shadow.{i}of{N}`. O portão do replay não foi junto:

1. `replay/budget.py::LIVE_HEARTBEAT_KEY = "hb:strategy:shadow"` — chave que **ninguém escreve** ⇒
   `heartbeat_missing`, sempre. Tem contorno por ambiente (`REPLAY_HEARTBEAT_KEY`), mas ele só
   descobre o segundo defeito.
2. `replay/consumer_lag.py::LIVE_CONSUMER_GROUP = "strategy-worker.shadow"` — o grupo
   **pré-shard, abandonado há 11,9 h**, cujo `lag` cresce sozinho (50 000 e subindo) enquanto os
   quatro grupos vivos estão em **`lag = 0`**. `live_lane_degraded` responde `consumer_lag:50000`
   ⇒ recusa, sempre. **Não há variável de ambiente para o nome do grupo** — só
   `REPLAY_CONSUMER_LAG_MAX`, e o único uso dela aqui seria pôr um número acima de 50 000, isto é,
   **desligar o eixo**.

### 3.3 Por que eu não contornei

O brief é explícito: *"the replay-worker pauses itself when the live lane degrades — never fight
it"*. As duas saídas disponíveis são combater o portão:

- `REPLAY_CONSUMER_LAG_MAX=999999` desliga o eixo de lag de consumidor;
- `REPLAY_PAUSE_ON_DEGRADED=false` desliga o portão inteiro.

E a terceira ideia, apagar o grupo morto (`XGROUP DESTROY`), **não** funcionaria: `group_lag`
responde `None` para um grupo inexistente e o portão trata `None` como degradado por princípio
("quando a saúde não pode ser estabelecida, a resposta que custa um replay é a segura") — viraria
`consumer_lag_unreadable`. Além disso seria escrita não auditada na VPS, que o brief proíbe.

**O conserto é de código, num commit que não é meu para fazer** (não posso commitar nem implantar):

- `replay/budget.py`: derivar a chave de heartbeat de `STRATEGY_SHARDS` e exigir que **todos** os
  shards estejam saudáveis (o pior dos N), não um;
- `replay/consumer_lag.py`: idem para o nome do grupo, `lag` = o **máximo** entre os N;
- e, de quebra, o grupo `strategy-worker.shadow` precisa ser apagado depois disso — ele tem 36
  entradas `pending` desde 10/09 que ninguém vai confirmar.

Sugiro abrir como bug próprio; o efeito é maior do que esta tarefa: **nenhum replay roda na VPS
desde que os 4 shards subiram**, o que inclui toda a fila de pesquisa do Lab.

## 4. O QUE DEU PARA MEDIR SEM UMA ÚNICA DECISÃO

Com a coorte impossível, medi as três previsões que **não** dependem de decisão (P1, P2, P3) e o
portão de desenho C5 — que era o item que o próprio pré-registro marcou como `REVISE`.

### 4.1 Método (e por que ele não é um segundo cálculo)

Dois SQL somente-leitura dobram as velas de 1 min em 5 m e 15 m **no servidor**, com a mesma
exigência de completude do `beta_repo.bar_closes` (`date_bin` desde a época, só `is_final`,
`count(*) = n` e o último minuto exatamente em `bucket + n−1 min`), e o Wilder(14) sobre 97 barras
rolantes sai **fora** do SQL, pelo `hunter_core.strategies.indicators.wilder_atr` congelado — o mesmo
que `mean_reversion_m5_v1` chama. É o método da T3.54, reusado de propósito.

```
$ timeout 290 ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter \
    -v ON_ERROR_STOP=1 -f - | gzip -9 | base64 -w0" \
    < infra/scripts/sql/research/2026-09-11-t384-q01-barras-5m-15m.sql    # 31 d, 19 s
$ ...                                        ...-q02-barras-5m-15m-90d.sql  # 90 d, 47 s
$ uv run python .claude/state/exp-drafts/t384/medir_atr_5m.py <csv>          # 80 s / 215 s
```

Cobertura: **190 464 barras** em 31 d (`5m` 142 848 = 31×288×16, `15m` 47 616) e **552 960** em 90 d
(`5m` 414 720 = 90×288×16, `15m` 138 240) — **100 % dos baldes completos, sem exceção**, nas duas
janelas e nos 16 mercados. Isso confirma de fora a regra de elegibilidade da T3.82.

**Controle de método:** ATR%(15m) p50 na janela da T3.54 = **0,5582 %** contra os **0,5585 %**
publicados. E a EXP-0028 derivou o ATR% realizado da mãe **de trás para frente** (0,0020/0,2169 =
0,922 %); a medição direta na mesma janela dá **0,9223 %**, pedágio **0,2169 R**. Os dois caminhos
se encontram na quarta casa.

### 4.2 Os números (90 d × 16 mercados, a janela do experimento)

```
mercado     n(5m/15m)   ATR%5m  ATR%15m  5m/15m  custoR5m  custoR15m  %>=0,6%  %<=0,3%  %>3%
ARBUSDT     25824/8544  0.2999  0.5560   0.539   0.6669    0.3597     12.58    50.03    0.00
BNBUSDT     25824/8544  0.1245  0.2371   0.525   1.6063    0.8434      0.15    96.52    0.00
BTCUSDT     25824/8544  0.1250  0.2379   0.525   1.6001    0.8407      0.15    95.39    0.00
DASHUSDT    25824/8544  0.2951  0.5389   0.548   0.6777    0.3711     13.55    51.10    0.03
DOGEUSDT    25824/8544  0.1975  0.3677   0.537   1.0128    0.5440      1.85    80.77    0.01
ETHUSDT     25824/8544  0.1713  0.3264   0.525   1.1677    0.6128      0.53    88.02    0.00
LINKUSDT    25824/8544  0.2153  0.4059   0.530   0.9291    0.4928      1.48    78.23    0.00
NEARUSDT    25824/8544  0.3704  0.6625   0.559   0.5400    0.3019     12.33    32.16    0.00
PROMUSDT    25824/8544  0.5437  1.0133   0.537   0.3679    0.1974     45.64    18.65    1.71
SAHARAUSDT  25824/8544  0.3235  0.5888   0.549   0.6182    0.3397      7.02    41.02    0.00
SOLUSDT     25824/8544  0.2086  0.3813   0.547   0.9587    0.5245      1.55    77.93    0.00
SUIUSDT     25824/8544  0.2476  0.4571   0.542   0.8076    0.4376      4.13    63.65    0.04
TAOUSDT     25824/8544  0.2978  0.5391   0.552   0.6715    0.3710      7.75    50.60    0.00
UNIUSDT     25824/8544  0.3665  0.6723   0.545   0.5457    0.2975     14.60    31.69    0.00
XRPUSDT     25824/8544  0.1839  0.3365   0.547   1.0876    0.5944      3.39    81.31    0.01
ZECUSDT     25824/8544  0.3792  0.6886   0.551   0.5274    0.2904     15.13    27.63    0.00

mediana das medianas (16 mercados):
  ATR%(5m) p50 = 0.2714 %   custo_R(stop_atr=1) = 0.7370 R
  ATR%(15m) p50 = 0.4980 %  custo_R(stop_atr=1) = 0.4016 R
  razao 5m/15m = 0.5449   (previsto 3^-0,571 = 0,534)
  razao 5m/15m por mercado: min 0.525 p50 0.545 max 0.559

P2 -- o piso de ATR% como definidor da versao (todas as leituras dos 16 mercados):
  5m:  n=413184  fracao em [0,6 %; 5 %] =  8.85 %  ATR% p50 CONDICIONAL = 0.7875 %  pedagio 0.2540 R
  15m: n=136704  fracao em [0,6 %; 5 %] = 33.04 %  ATR% p50 CONDICIONAL = 0.8149 %  pedagio 0.2454 R

C5 -- banda de stop do paper_v1 [0,3 %; 3 %] com stop_atr = 1:
  5m:  incondicional <= 0,3 % = 60.29 %  > 3 % = 0.11 % || condicional 0.00 % / 1.11 %
  15m: incondicional <= 0,3 % = 21.51 %  > 3 % = 0.63 % || condicional 0.00 % / 1.69 %

mercados cuja MEDIANA de 5 m cai sob o piso de risco de 0,3 %:
  11/16: ARB BNB BTC DASH DOGE ETH LINK SOL SUI TAO XRP
```

Na janela de 31 d da T3.54 (a que gerou a previsão): ATR%(5m) p50 = **0,2984 %**, razão **0,5345**,
portão passa **15,73 %**, ATR% condicional **0,8211 %**, pedágio condicional **0,2436 R**.

### 4.3 O veredito das previsões

| Previsão | Resultado | Número |
|---|---|---|
| **P1** ATR%(5m) p50 ≈ 0,30 % | **confirmada** | 0,2984 % (31 d) / 0,2714 % (90 d); o gatilho de falsificação era > 0,40 % |
| **P2** o piso define a versão; condicional 0,60–0,75 % | **mecanismo sim, número não** | portão passa 8,85 % contra 33,04 % da mãe; condicional **0,7875 %**, fora da banda |
| **P3** pedágio p50 0,267–0,333 R, Δ +0,05…+0,12 R | **falsificada** | **0,2540 R**, Δ **+0,0086 R** — uma ordem de grandeza menor |
| **P4** ex-funding −0,25 a −0,09 R | **não mensurável** | precisa da coorte |
| **P5** 160–810 decisões | **reestimada em ≈ 436** | `542 × 3 × 0,0885/0,3304`, assumindo independência entre o portão de ATR e as outras três condições |
| **C5** (`REVISE`) | **as duas metades confirmadas** | 0,00 % dos stops abaixo do piso de 0,3 % e 1,11 % acima do teto (a mãe: 1,69 %); e o preço é 91,15 % das barras fora, com 11/16 mercados de mediana abaixo do próprio piso de risco |

**O que isso significa, dito contra o prior desta equipe.** O pré-registro apostou em `descartar`
por **custo**, aplicando a identidade da KB-0076 à mediana **incondicional** da grade. A medição
mostra que o piso `atr_pct_min = 0,006` não encarece a filha: ele **seleciona a cauda volátil** da
grade de 5 min, e o que sobra paga 0,2540 R contra os 0,2454 R que a mãe paga na mesma janela. O
argumento de custo **não sobrevive**. O veredito passa a depender inteiramente da expectativa
**bruta** a 5 min — exatamente o que o replay mediria, e exatamente o que o portão cego impediu.

## 5. VEREDITO: NENHUM. E POR QUE A VERSÃO NÃO FOI APOSENTADA

A regra de sucesso congelada da EXP-0028 exige **quatro** condições, todas sobre desfechos. Zero
desfechos existem. A régua editorial da própria página (≥ 100 avaliáveis **e** ≥ 30 dias) não é
alcançada nem de longe. **Emitir `descartar` aqui seria inventar um resultado** — e seria inventá-lo
justamente no dia em que a evidência disponível enfraqueceu o motivo do descarte.

A regra do Everton ("versão ruim morre no mesmo dia") vale para versão **medida** ruim. Esta não foi
medida. `--deprecate` congelaria a linha sem resposta e jogaria fora a única coisa que o replay ainda
pode dar; e uma linha `deprecated` não volta a ser `active` (a `v1` está congelada pelo gatilho da
`0002_shadow_lab` — a sucessora seria uma `v2`, com coorte nova e sem comparabilidade com este
pré-registro).

**Custo declarado de deixá-la ativa:** a faixa viva passa a avaliar mais uma versão **por fechamento
de 5 min** (288/dia/mercado contra 96 das versões de 15 min), em 4 shards. Com o universo de 90 d
(56 mercados, 6 por shard na leitura de hoje) são ~1 728 avaliações/dia/shard a mais. É pequeno, mas
não é zero, e o `decision_lag` é o sinal a vigiar — foi ele que habilitou este experimento
(p50 2,2 s em 10/09). Se o conserto do §3.3 demorar, aposentar por **custo operacional** é uma
decisão legítima; aposentar por **veredito** não é.

## 6. ARQUIVOS DESTA PASSADA

```
$ git -C C:/dev/project-hunter status --porcelain -- <os arquivos desta passada>
 M obsidian/03-TRADING/Estrategias/mean_reversion.md
 M obsidian/05-EXPERIMENTS/EXP-0028-mean-reversion-5-min.md
 M "obsidian/05-EXPERIMENTS/Experiments Index.md"
?? .claude/state/exp-drafts/t384/
?? .claude/state/notes-T3.84.md
?? infra/scripts/sql/research/2026-09-11-t384-q01-barras-5m-15m.sql
?? infra/scripts/sql/research/2026-09-11-t384-q02-barras-5m-15m-90d.sql
?? obsidian/03-TRADING/Estrategias/mean_reversion_m5-v1.md
?? obsidian/03-TRADING/Estrategias/mean_reversion_m5.md
```

A árvore é compartilhada: a `git status` sem pathspec mostra também arquivos de **outras** tarefas
(`.claude/launch.json`, `notes-T3.83.md`, `docs/DESIGN.md`, consumidores do scanner, capturas de
tela). Nada disso é meu e nada disso foi tocado. **Nenhum commit foi feito.**

| Arquivo | O quê |
|---|---|
| `infra/scripts/sql/research/2026-09-11-t384-q01-barras-5m-15m.sql` | velas de 5 m e 15 m dos 16 mercados na janela de 31 d da T3.54 — a comparação pareada com a previsão |
| `infra/scripts/sql/research/2026-09-11-t384-q02-barras-5m-15m-90d.sql` | as mesmas, na janela de 90 d do experimento |
| `.claude/state/exp-drafts/t384/medir_atr_5m.py` | ATR% por grade com o `wilder_atr` congelado, pedágio, portão de ATR e C5 |
| `obsidian/05-EXPERIMENTS/EXP-0028-mean-reversion-5-min.md` | avaliação parcial **acrescentada** (133 linhas, 0 remoções) |
| `obsidian/03-TRADING/Estrategias/mean_reversion_m5.md` / `-v1.md` | páginas de família e de versão |
| `obsidian/05-EXPERIMENTS/Experiments Index.md`, `…/mean_reversion.md` | índices |

```
$ uv run python infra/scripts/obsidian_lint.py
LINT DA BASE OBSIDIAN — 252 NOTA(S) ANALISADA(S)
Resumo — Links mortos: 0, Links ambíguos: 0, Notas órfãs: 0, Frontmatter incompleto: 0,
Valores fora do vocabulário: 0, Procedência da Knowledge Base (KB-*): 0,
Reescrita de experimentos (append-only): 0.
RESULTADO: base limpa
```

## 7. ASSUNÇÕES NUMÉRICAS QUE EU TIVE DE FAZER

1. **A janela de 31 d (2026-08-08 → 2026-09-08) é a comparação correta para P1**, porque é dela que
   a previsão foi extrapolada. Medi as duas janelas para não ter de escolher.
2. **"ATR% condicional ao portão" é condicional só ao portão de ATR**, não às outras três condições
   de entrada (tendência de 15 m, `z ≤ −1`, fechamento acima do meio da barra). Se elas
   correlacionarem com volatilidade, o pedágio real das decisões difere do medido aqui. Só o replay
   resolve.
3. **A reestimativa de P5 (≈ 436 decisões) assume a mesma independência.**
4. **Coorte de replay: uma só, não uma por fatia.** O protocolo da EXP-0028 diz "uma por fatia", mas
   a EXP-0025 e a EXP-0026 usaram **uma por versão** nas 12 fatias, e a página cita as coortes delas
   como um id único; além disso `--stress` recebe **uma** coorte, e os braços "metades" e
   "sem-mercado" da regra de sucesso nº 4 só fazem sentido sobre a população inteira. Mintei
   `replay:92c8d080-6009-4a59-9868-31282b1bd493` para as 12 fatias. **Nada foi escrito com ela** (o
   portão recusou antes), então a decisão pode ser revista sem custo por quem retomar.
5. **11,9 h para a idade do grupo abandonado** é `idle = 42 828 070 ms` do consumidor **menos
   ocioso** dos 57 — isto é, um limite inferior.

---

# PASSO 3 — a coorte existiu, e o veredito é `descartar` (11/09/2026, 06:25 → 08:05 BRT)

Horários em **BRT (UTC−3)**; o UTC aparece ao lado quando é o que a saída mostra.
Esta seção é **acrescentada**; nada do passo 2 acima foi reescrito.

## 8. RESUMO HONESTO DO PASSO 3

| # | O que o brief pediu | Resultado |
|---|---|---|
| 1 | replay 90 d × 16 mercados via `compose.sh replay`, uma fatia por vez | **OK** — 23 fatias, **414 720 barras**, **0 erros**, nenhuma recusa do portão |
| 2 | estresse na coorte | **OK** — `sem_vantagem_na_base` |
| 3 | análise (blocos de dia, LOMO, 3 janelas, K1–K6, C5, pedágio medido vs 0,254 R) | **OK** — tudo medido, §11 e §12 |
| 4 | veredito na EXP-0028 (append-only) | **OK** — **`descartar`**, seção nova de 200 linhas, 0 remoções |
| 5 | páginas de estratégia e `Experiments Index` | **OK** |
| 6 | aposentar se falhar a regra pré-registrada | **OK** — `deprecated` às **07:54:08 BRT**, 13 min depois do último número |
| 7 | notas, SQL, `obsidian_lint` | **OK** — esta seção, 2 SQL novos, `RESULTADO: base limpa` |

**A frase que resume o dia:** a versão morreu como o pré-registro previu — **e pelo motivo oposto ao
que ele deu**. O custo a 5 min é praticamente o mesmo da mãe (+0,0105 R); o que não existe a 5 min é
o **sinal** (vantagem bruta +0,1270 R → +0,0346 R). **89,8 % da piora é sinal, 10,2 % é custo.**

## 9. PRÉ-VOO — O QUE ENCONTREI ÀS 06:25 BRT (E NÃO É MEU)

`HEAD` implantado `283a904` (T3.87, o conserto do portão). Mas a pilha estava assim:

```
$ ssh hunter-vps 'docker ps --format "{{.Names}}\t{{.Status}}" | sort'      # 06:25 BRT / 09:25Z
hunter-market-worker-1        Restarting (1) 2 seconds ago
hunter-market-worker-1-1      Restarting (1) 2 seconds ago
hunter-market-worker-2-1      Restarting (1) 3 seconds ago
hunter-market-worker-3-1      Restarting (1) 2 seconds ago
hunter-market-worker-spot-1   Restarting (1) 2 seconds ago
hunter-redis-1                Up About a minute (healthy)
...
$ docker logs --tail 15 hunter-market-worker-1
redis.exceptions.BusyLoadingError: Redis is loading the dataset in memory
```

**Causa: o Redis reiniciou e estava carregando o dump**; os cinco coletores entravam em *crash-loop*
contra ele. Não é desta tarefa, **não toquei em nada** e não recriei container nenhum: esperei em
primeiro plano, medindo.

```
$ ssh hunter-vps 'for i in $(seq 1 28); do r=$(docker exec hunter-redis-1 redis-cli PING 2>&1); \
    echo "$(date -u +%T) $r"; [ "$r" = "PONG" ] && break; sleep 10; done'
09:25:44 LOADING Redis is loading the dataset in memory
... (10 leituras) ...
09:27:25 PONG
```

Às 08:01 BRT os cinco estavam `Up 2 hours (healthy)` sozinhos. **Custo declarado:** ~2 min de
ingestão perdidos por volta de 06:25 BRT — quem for olhar `ingestion_gaps` de hoje vai achar isso, e
a causa está aqui.

Estado do portão do replay depois que o Redis voltou (leitura, nenhuma escrita):

```
hb:strategy:shadow:0of4 … 3of4   (as quatro existem; `hb:strategy:shadow` continua não existindo)
XINFO GROUPS market.candles.closed:
  strategy-worker.shadow        consumers 57  pending 36  lag 50004   <- o ORFAO pre-shard
  strategy-worker.shadow.{0..3}of4  consumers 7  pending 0  lag 0     <- os quatro vivos
decision_lag_p50_s = 3.0 … 4.2 s (shards 0 e 3)
```

É exatamente o quadro que bloqueou o passo 2 — e é exatamente o que a **T3.87** ensinou o portão a
ler. A prova de que o conserto funciona aparece uma vez por corrida, no log do `replay-worker`:

```
2026-09-11 09:28:50 [warning  ] orphan_consumer_group          name=strategy-worker.shadow
```

O grupo morto é **nomeado e ignorado**, os quatro vivos são consultados, e a corrida segue.
**Nenhuma recusa `live lane degraded` nas 23 fatias.**

## 10. AS 23 FATIAS — E POR QUE NÃO SÃO 12

Ensaio primeiro (o ensaio pula o portão por construção):

```
$ ssh hunter-vps 'cd /opt/project-hunter && timeout 240 env STRATEGY_SHARDS=4 MARKET_SPOT=1 MARKET_SHARDS=4 \
    bash infra/vps/compose.sh replay python -m hunter_strategy_worker.replay.run \
    --version mean_reversion_m5:v1 --from 2026-06-12 --to 2026-07-12 \
    --markets ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT --cohort replay:92c8d080-6009-4a59-9868-31282b1bd493 --dry-run'
replay-worker: STRATEGY_SHARDS=4 (deve bater com o update/up mais recente)
{'cohort': 'replay:92c8d080-6009-4a59-9868-31282b1bd493', 'version': 'mean_reversion_m5 v1',
 'markets': 4, 'bars_planned': 34560, 'context_minutes': 1560, 'workers': 3}
```

**A primeira fatia de verdade estourou o relógio, e isso é um dado, não um acidente.** 4 mercados ×
30 d = 34 560 barras levaram **495,1 s** — o `timeout 265` do cliente matou o `docker compose run`,
**mas o container continuou** (o `timeout` mata o cliente, não o processo lá dentro), terminou os
quatro mercados e gravou o recibo. Conferi o desfecho pelo banco em vez de supor:

```
$ psql -c "select mk.symbol, e.last_bar_close, e.created_at, e.updated_at from shadow_episodes e ..."
 DOGEUSDT | 2026-06-23 12:35:00+00 | 09:33:14 | 09:34:39     <- ainda andando quando o cliente morreu
 ETHUSDT  | 2026-07-11 23:55:00+00 | 09:28:53 | 09:33:12     <- fim da janela
 SOLUSDT  | 2026-07-11 23:55:00+00 | 09:28:53 | 09:33:12
 XRPUSDT  | 2026-07-11 23:55:00+00 | 09:28:53 | 09:33:13
$ ssh hunter-vps 'for i in ...; do docker ps | grep -c replay-worker-run; sleep 10; done'
09:35:29 replay_containers=1  ...  09:37:11 replay_containers=0      <- ele terminou sozinho
$ psql -x -c "select ... from system_events where component='replay_engine' ..."
 bars_evaluated 34560 · seconds 495.062 · errors 0 · evaluations_by_state {triggered 2, unavailable 184,
 not_triggered 34374}
```

**Medida de taxa:** 3 mercados em paralelo (3 CPUs do `replay-worker`) fazem ~100 barras/s; um
mercado sozinho, ~37 barras/s. Logo **o relógio de uma fatia é o tamanho do maior mercado dela**, e
30 dias de um mercado (8 640 barras) custam ~250 s — colado no teto de 290 s do brief.

**A saída que o brief autorizou:** `4 mercados × 15 d`. Com `--workers 4` (1 acima do que
`workers_for` escolhe; sobreinscrição contida pelo *cgroup* de 3 CPUs do próprio `replay-worker`,
nunca disputa com a faixa viva, que é outro container) cada fatia ficou em **~156 s**, 108–112
barras/s. As 22 fatias seguintes são assim. Comando, verbatim (só mudam janela e mercados):

```
$ timeout 290 ssh hunter-vps 'cd /opt/project-hunter && date -u +%FT%TZ && timeout 260 \
    env STRATEGY_SHARDS=4 MARKET_SPOT=1 MARKET_SHARDS=4 bash infra/vps/compose.sh replay \
    python -m hunter_strategy_worker.replay.run --version mean_reversion_m5:v1 \
    --from 2026-07-12 --to 2026-07-27 --markets ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT \
    --workers 4 --explain-ledger /tmp/t384-m5-s1-w2a.jsonl \
    --cohort replay:92c8d080-6009-4a59-9868-31282b1bd493 ...'
2026-09-11 09:41:38 [info  ] replay_explain_ledger  bars=17280 lines=17280 path=/tmp/t384-m5-s1-w2a.jsonl
{'run_id': '92c8d080-...', 'bars_evaluated': 17280, 'signals': 1, 'outcomes_resolved': 1,
 'outcomes_open': 0, 'seconds': 160.24, 'bars_per_second': 107.84, 'workers': 4,
 'evaluations_by_state': {'not_triggered': 17280}, 'errors': 0, 'context_minutes': 1560}
```

O recibo das 23, lido do banco (`system_events`, `component = 'replay_engine'`) e não da minha
transcrição:

```
 fim_utc  |     de     |    ate     |               mercados                | barras | trig | unav |   s   | w | sinais_acum
----------+------------+------------+---------------------------------------+--------+------+------+-------+---+------------
 09:37:06 | 2026-06-12 | 2026-07-12 | ETHUSDT+SOLUSDT+XRPUSDT+DOGEUSDT      |  34560 | 2    | 184  | 495.1 | 3 |           1
 09:41:38 | 2026-07-12 | 2026-07-27 | ETHUSDT+SOLUSDT+XRPUSDT+DOGEUSDT      |  17280 | 0    | 0    | 160.2 | 4 |           1
 09:44:35 | 2026-07-27 | 2026-08-11 | ETHUSDT+SOLUSDT+XRPUSDT+DOGEUSDT      |  17280 | 0    | 0    | 159.7 | 4 |           1
 09:47:28 | 2026-08-11 | 2026-08-26 | ETHUSDT+SOLUSDT+XRPUSDT+DOGEUSDT      |  17280 | 31   | 0    | 159.3 | 4 |          24
 09:50:18 | 2026-08-26 | 2026-09-10 | ETHUSDT+SOLUSDT+XRPUSDT+DOGEUSDT      |  17280 | 2    | 0    | 154.6 | 4 |          25
 09:53:10 | 2026-06-12 | 2026-06-27 | BTCUSDT+BNBUSDT+ZECUSDT+SUIUSDT       |  17280 | 8    | 184  | 155.9 | 4 |          32
 09:56:01 | 2026-06-27 | 2026-07-12 | BTCUSDT+BNBUSDT+ZECUSDT+SUIUSDT       |  17280 | 10   | 0    | 156.0 | 4 |          38
 09:58:51 | 2026-07-12 | 2026-07-27 | BTCUSDT+BNBUSDT+ZECUSDT+SUIUSDT       |  17280 | 1    | 0    | 156.3 | 4 |          39
 10:01:46 | 2026-07-27 | 2026-08-11 | BTCUSDT+BNBUSDT+ZECUSDT+SUIUSDT       |  17280 | 0    | 0    | 158.8 | 4 |          39
 10:04:42 | 2026-08-11 | 2026-08-26 | BTCUSDT+BNBUSDT+ZECUSDT+SUIUSDT       |  17280 | 34   | 0    | 160.0 | 4 |          58
 10:07:34 | 2026-08-26 | 2026-09-10 | BTCUSDT+BNBUSDT+ZECUSDT+SUIUSDT       |  17280 | 29   | 0    | 156.3 | 4 |          76
 10:10:26 | 2026-06-12 | 2026-06-27 | NEARUSDT+UNIUSDT+ARBUSDT+TAOUSDT      |  17280 | 41   | 184  | 156.4 | 4 |         102
 10:13:15 | 2026-06-27 | 2026-07-12 | NEARUSDT+UNIUSDT+ARBUSDT+TAOUSDT      |  17280 | 25   | 0    | 155.0 | 4 |         116
 10:16:06 | 2026-07-12 | 2026-07-27 | NEARUSDT+UNIUSDT+ARBUSDT+TAOUSDT      |  17280 | 1    | 0    | 155.8 | 4 |         117
 10:18:57 | 2026-07-27 | 2026-08-11 | NEARUSDT+UNIUSDT+ARBUSDT+TAOUSDT      |  17280 | 3    | 0    | 156.4 | 4 |         119
 10:21:50 | 2026-08-11 | 2026-08-26 | NEARUSDT+UNIUSDT+ARBUSDT+TAOUSDT      |  17280 | 40   | 0    | 157.8 | 4 |         141
 10:24:42 | 2026-08-26 | 2026-09-10 | NEARUSDT+UNIUSDT+ARBUSDT+TAOUSDT      |  17280 | 99   | 0    | 156.4 | 4 |         202
 10:27:33 | 2026-06-12 | 2026-06-27 | LINKUSDT+DASHUSDT+PROMUSDT+SAHARAUSDT |  17280 | 35   | 184  | 154.2 | 4 |         221
 10:30:28 | 2026-06-27 | 2026-07-12 | LINKUSDT+DASHUSDT+PROMUSDT+SAHARAUSDT |  17280 | 2    | 0    | 158.9 | 4 |         223
 10:33:18 | 2026-07-12 | 2026-07-27 | LINKUSDT+DASHUSDT+PROMUSDT+SAHARAUSDT |  17280 | 28   | 0    | 156.5 | 4 |         239
 10:36:09 | 2026-07-27 | 2026-08-11 | LINKUSDT+DASHUSDT+PROMUSDT+SAHARAUSDT |  17280 | 38   | 0    | 156.2 | 4 |         261
 10:39:01 | 2026-08-11 | 2026-08-26 | LINKUSDT+DASHUSDT+PROMUSDT+SAHARAUSDT |  17280 | 84   | 0    | 156.4 | 4 |         312
 10:41:56 | 2026-08-26 | 2026-09-10 | LINKUSDT+DASHUSDT+PROMUSDT+SAHARAUSDT |  17280 | 84   | 0    | 158.2 | 4 |         373
```

Soma: **414 720 barras** = 16 × 90 × 288, **597 `triggered`**, **736 `unavailable` (0,1775 %)**,
**0 erros**. `sinais_acum` é cumulativo por coorte (o `count_population` conta a coorte inteira, não
a fatia) — por isso ele fecha em **373**.

**As 184 barras `unavailable` aparecem só nas quatro fatias que começam em 2026-06-12**: é o
aquecimento de contexto na borda esquerda da janela, uma vez por mercado, não um buraco de dado.

**Cobertura conferida mercado a mercado** (`…-q04…sql`, bloco 8): **25 920 barras para cada um dos
16**, sem exceção. Nenhum mercado ficou de fora, nenhum foi contado duas vezes.

## 11. O ESTRESSE (07:42 BRT / 10:42Z)

```
$ ... bash infra/vps/compose.sh replay python -m hunter_strategy_worker.replay.run \
    --stress replay:92c8d080-6009-4a59-9868-31282b1bd493
coorte replay:92c8d080-... · as_of 2026-09-11T10:42:26.326179+00:00 · 373 entradas congeladas
· 14 mercados · axis: r_ex_funding, funding_indeterminado: 1
| cenário | tipo | n | expectancy (R) | PF | Δ vs base | IC 95 % do Δ |
| base                    | reprecificacao | 371 | -0.1937 | 0.6977 |    —    | — |
| custos_x2               | reprecificacao | 371 | -0.3899 | 0.4637 | -0.1962 | [-0.2116, -0.1818] |
| stop_x0.75              | reprecificacao | 371 | -0.3448 | 0.5725 | -0.1511 | [-0.2279, -0.0748] |
| stop_x1.25              | reprecificacao | 371 | -0.1411 | 0.7429 | +0.0526 | [-0.0045, +0.1186] |
| alvo_x0.75              | reprecificacao | 371 | -0.2265 | 0.6246 | -0.0328 | [-0.0737, +0.0078] |
| alvo_x1.25              | reprecificacao | 371 | -0.1947 | 0.7095 | -0.0010 | [-0.0656, +0.0507] |
| entrada_mais_1_barra    | reprecificacao | 366 | -0.2065 | 0.6835 | -0.0238 | [-0.0692, +0.0304] |
| sem ARBUSDT   343 -0.1816 | sem DASHUSDT  335 -0.1937 | sem DOGEUSDT 358 -0.1797 | sem ETHUSDT 370 -0.1966
| sem LINKUSDT  362 -0.1890 | sem NEARUSDT  344 -0.1546 | sem PROMUSDT 268 -0.2679 | sem SAHARAUSDT 350 -0.1973
| sem SOLUSDT   369 -0.2013 | sem SUIUSDT   363 -0.1831 | sem TAOUSDT  346 -0.1679 | sem UNIUSDT 325 -0.1931
| sem XRPUSDT   362 -0.1964 | sem ZECUSDT   328 -0.2281
| 1a_metade_ate_2026-07-26  | recorte |  92 | -0.2387 | 0.6363 |
| 2a_metade_apos_2026-07-26 | recorte | 279 | -0.1788 | 0.7186 |
**Veredito:** sem_vantagem_na_base
- expectancy da base = -0.1937018205162866619411394157
```

O estresse reprecifica 371 das 373 (duas saem por funding: `funding_ambiguous_exit`,
`funding_missing`). **Não há vantagem para estressar** — e mesmo assim toda a grade é negativa, nas
duas metades da janela e sem qualquer um dos 14 mercados.

## 12. A ANÁLISE — SQL, BOOTSTRAP E A DECOMPOSIÇÃO QUE INVERTE O ARGUMENTO

Dois SQL somente-leitura (`repeatable read read only`, `statement_timeout 240s`):

```
$ timeout 280 ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter \
    -v ON_ERROR_STOP=1 -f -" < infra/scripts/sql/research/2026-09-11-t384-q03-dump-decisoes-m5.sql
(915 rows)   # 373 da filha + 542 da mae (o controle pre-declarado, NAO re-rodado)
$ ... < infra/scripts/sql/research/2026-09-11-t384-q04-funil-k-c5-pedagio.sql
```

*(Nota de método: o `q04` nasceu com `create temporary view` e o Postgres recusou —
`cannot execute CREATE VIEW in a read-only transaction`. A recusa está certa e é a prova de que o
contrato "somente leitura" destes arquivos vale; a CTE passou a ser repetida em cada consulta, com o
texto idêntico nas seis, e o motivo ficou escrito no cabeçalho do arquivo.)*

### 12.1 População, K1–K6 e as duas expectativas

```
        versao        | desfechos | avaliaveis | dias | exp_exf | exp_bruta | pf_exf | cobertura_rnet | maior_mkt
 mean_reversion v1    |       542 |        542 |   83 | -0.0910 |    0.1270 | 0.8509 |         46.68% |    13.10%
 mean_reversion_m5 v1 |       373 |        373 |   72 | -0.1940 |    0.0346 | 0.6971 |         99.20% |    28.15%
```

| K | filha | dispara? |
|---|---|---|
| K1 (< 20) | 373 | não |
| K2 (> 1 500) | 373 | não |
| **K3** (≥ 100 **e** ≥ 30 d **e** bruta < 0) | 373 · 72 d · **+0,0346** | **não, pela letra** |
| K4 (`unavailable` > 40 %) | **0,1775 %** | não |
| K5 (cobertura `R_net` < 70 %) | **99,20 %** | não (a mãe **dispara**: 46,68 %) |
| K6 (≥ 60 % num mercado) | 28,15 % (PROM 105/373) | não |

**Nenhum critério de morte dispara e a versão morre assim mesmo** — pela regra de sucesso, que é mais
exigente e foi escrita antes. K4 é mensurável de verdade aqui (esta versão não tem
`eligibility_policy`, logo não há o falso verde da T3.52d). **K5 saltando de 46,68 % para 99,20 % é
geometria, não qualidade de dado**: o horizonte de 80 min atravessa uma liquidação de funding muito
mais raramente que as 4 h da mãe.

### 12.2 O bootstrap de blocos de dia (20 000 reamostragens, semente 20260910)

```
$ uv run python .claude/state/exp-drafts/t384/analise.py \
    .claude/state/exp-drafts/t384/decisoes-m5-e-mae.csv

-- 1. REGRA No 1
mean_reversion_m5 v1 | r_ex_funding n= 373 dias= 72 media=-0.1940 IC95=[-0.2889; -0.0943] (abaixo de zero)  PF=0.6971
mean_reversion v1    | r_ex_funding n= 542 dias= 83 media=-0.0910 IC95=[-0.2129; +0.0311] (cruza zero)      PF=0.8509
-- expectativa BRUTA
mean_reversion_m5 v1 | r_bruto      n= 373 dias= 72 media=+0.0346 IC95=[-0.0625; +0.1387] (cruza zero)      PF=1.0687
mean_reversion v1    | r_bruto      n= 542 dias= 83 media=+0.1270 IC95=[+0.0047; +0.2500] (acima de zero)   PF=1.2595

-- 2. REGRA No 2 (PF por janela de 30 d)
filha J1 n= 75 dias=22 media=-0.3168 IC95=[-0.4780; -0.1622]  PF=0.5278
filha J2 n= 42 dias=21 media=+0.0925 IC95=[-0.2458; +0.4174]  PF=1.1657
filha J3 n=256 dias=29 media=-0.2050 IC95=[-0.3252; -0.0812]  PF=0.6821

-- 3. REGRA No 3 (leave-one-market-out, 16 reajustes) — TODOS negativos, IC inteiro abaixo de zero:
sem ARBUSDT -0.1820 · sem BNBUSDT -0.1940 (sem decisao: populacao inteira) · sem BTCUSDT -0.1940 (idem)
sem DASHUSDT -0.1941 · sem DOGEUSDT -0.1802 · sem ETHUSDT -0.1969 · sem LINKUSDT -0.1894
sem NEARUSDT -0.1551 · sem PROMUSDT -0.2676 · sem SAHARAUSDT -0.1972 · sem SOLUSDT -0.2016
sem SUIUSDT -0.1834 · sem TAOUSDT -0.1684 · sem UNIUSDT -0.1935 · sem XRPUSDT -0.1967 · sem ZECUSDT -0.2282

-- 4. filha contra a mae, Delta PAREADO POR DIA
filha n=373 media=-0.1940 | mae n=542 media=-0.0910 | Delta=-0.1030 IC95=[-0.2670; +0.0686]

-- 5. DE ONDE VEM A PIORA (identidade: custo = media(bruta) - media(liquida))
mean_reversion_m5 v1   bruta=+0.0346  liquida=-0.1940  custo=0.2285 R | 0,0020/ATR% p50 = 0.2518 R (ATR% p50 0.7943 %)
mean_reversion v1      bruta=+0.1270  liquida=-0.0910  custo=0.2180 R | 0,0020/ATR% p50 = 0.2354 R (ATR% p50 0.8495 %)
Delta liquida (filha - mae) = -0.1030 R  =  Delta bruta -0.0925 R  -  Delta custo +0.0105 R
fracao da piora explicada pela vantagem BRUTA = 89.8 % | pelo CUSTO = 10.2 %

-- 6. C5 (banda [0,3 %; 3 %])
mean_reversion_m5 v1   n= 373 p50=0.8892 % abaixo de 0,3 % = 1 (0.27 %) acima de 3 % = 7 (1.88 %)
mean_reversion v1      n= 542 p50=0.9242 % abaixo de 0,3 % = 2 (0.37 %) acima de 3 % = 12 (2.21 %)
```

### 12.3 O pedágio medido contra os 0,254 R previstos no passo 2

| fonte | número |
|---|---|
| previsto no passo 2 (distribuição de **barras** condicionada ao portão de ATR) | **0,2540 R** |
| medido agora nas **decisões**, `0,0020/ATR%` com o ATR% realizado de cada uma | **0,2518 R** (p50) |
| medido agora pela **identidade** `bruta − líquida` (não depende de nenhuma fórmula de custo) | **0,2285 R** |

A assunção nº 2 do passo 2 (independência entre o portão de ATR e as outras três condições) **se
sustenta**: 0,2518 contra 0,2540 é **0,9 % de diferença**. A identidade fica 0,023 R abaixo das duas
porque `0,0020/ATR%` é uma aproximação dos custos assumidos e o custo real por decisão varia com a
geometria da entrada — as três concordam na segunda casa, o que é o que importa aqui.

**E o número que decide:** o pedágio da filha é **+0,0105 R** acima do da mãe. O pré-registro previu
**+0,05 a +0,12 R**. P3 está falsificada pela segunda vez, agora sobre decisões reais.

### 12.4 Por mercado e por saída

```
filha:  PROM 105 -0.0060 | UNI 46 -0.1971 | ZEC 43 +0.0688 | DASH 36 -0.1924 | ARB 28 -0.3418
        NEAR 27 -0.6915 | TAO 25 -0.5503 | SAHARA 21 -0.1391 | DOGE 13 -0.5763 | XRP 9 -0.0850
        LINK 9 -0.3805 | SUI 8 -0.6744 | SOL 2 +1.2131 | ETH 1 +0.8879 | BNB 0 | BTC 0
funil de saida: filha stop 197 (52,82 %, -1,1696) · target 142 (38,07 %, +1,1106) · expired 34 (9,12 %, +0,0106)
                mae   stop 281 (51,85 %, -1,1575) · target 216 (39,85 %, +1,2183) · expired 45 (8,30 %, +0,2844)
```

**BTC e BNB não produziram uma única decisão em 90 dias** (ATR% de 5 min p50 0,1250 % e 0,1245 %;
passam o piso em 0,15 % das barras): o universo **efetivo** é de **14 mercados**, e os dois ausentes
são os dois mais líquidos. A forma do funil é praticamente a mesma da mãe — a filha não perde por
sair diferente, perde porque 38,07 % de acerto não paga um R/R de 1,5 depois do pedágio.

## 13. O VEREDITO E A APOSENTADORIA

A regra congelada exige **as quatro**; **as quatro falham**. A régua editorial (≥ 100 avaliáveis
**e** ≥ 30 dias) é alcançada com folga — 373 e 72 —, então a página **pode** e **deve** decidir.

```
$ ... compose.sh ops python infra/scripts/activate_strategy_version.py mean_reversion_m5 v1 \
    --deprecate --changelog "T3.84/EXP-0028: descartada pela regra de sucesso pre-registrada. ..." --dry-run
2026-09-11T10:53:50Z
would deprecate mean_reversion_m5 v1 (purpose research_only), code_ref hunter_core.strategies.
  mean_reversion_m5_v1@sha256:f733467f..., params_hash 5eaf76a71880, successor=none: ...

$ ... (sem --dry-run)
2026-09-11T10:54:05Z
deprecated mean_reversion_m5 v1 (purpose research_only) at 2026-09-11T10:54:08.545106+00:00, successor=none

$ psql -c "select s.key, sv.version, sv.status, sv.purpose, sv.activated_at, sv.deprecated_at ..."
 mean_reversion_m5 | v1 | deprecated | research_only | 2026-09-11 08:32:18.437633+00 | 2026-09-11 10:54:08.545106+00
```

**Aposentada 13 minutos depois do último número.** A avaliação parcial das 05:50 BRT havia recusado
aposentar com o argumento de que "a regra do Everton vale para versão **medida** ruim"; agora ela é
uma. O `changelog` gravado na auditoria carrega os **números** (coorte, 373 desfechos, IC, PF por
janela, LOMO, veredito do estresse, decomposição bruta/custo), não a conclusão.

Contrato do passo 1 reconferido nesta árvore antes de escrever qualquer página:

```
$ uv run pytest packages/core/tests/unit/strategies/test_mean_reversion_m5_v1.py -q \
    -k "look_ahead or antecipa or forming or nao_antecip"
5 passed, 34 deselected in 0.62s

$ uv run pytest packages/core/tests/unit/strategies/test_mean_reversion_m5_v1.py \
    services/strategy-worker/tests/test_context_budget.py -q
75 passed in 3.58s

$ uv run pytest .claude/state/exp-drafts/t362b/test_blocos90.py -q      # o bootstrap que a analise usa
14 passed in 1.28s

$ uv run ruff check . && uv run ruff format --check .
All checks passed!
10 files would be reformatted, 1506 files already formatted
   # os 10 sao de OUTRAS tarefas nao commitadas (backfill_funding.py, request_backfill.py,
   # funding_announce.py, quatro notas do Obsidian, tres testes); nenhum e meu, conferido um a um.
   # `.claude/**` nao e varrido pelo ruff (diretorio oculto), como o irmao `t362b/analise.py` ja mostra.

$ uv run python infra/scripts/check_file_size.py
scanned 629 files; 0 over budget, 0 grandfathered
```

## 14. AS PÁGINAS

```
$ uv run python infra/scripts/obsidian_lint.py
LINT DA BASE OBSIDIAN — 252 NOTA(S) ANALISADA(S)
Resumo — Links mortos: 0, Links ambíguos: 0, Notas órfãs: 0, Frontmatter incompleto: 0,
Valores fora do vocabulário: 0, Procedência da Knowledge Base (KB-*): 0,
Reescrita de experimentos (append-only): 0.
RESULTADO: base limpa
```

- **`EXP-0028`**: seção **acrescentada** (`### Avaliação de 2026-09-11 — as_of = 10:42:26Z`), 201
  linhas, **0 remoções**; frontmatter passa a `status: avaliado`, `result: reprovada`,
  `evaluable: 373`, `days: 72`, `last_eval: 2026-09-11`. (`reprovada` é o vocabulário do linter para
  o que a página chama de `descartar` — `ENUM_VOCAB` em `obsidian_lint_rules.py` aceita
  `inconclusivo|validada|reprovada|nao-iniciado`.) As duas seções de avaliação anteriores ficaram
  intactas, inclusive a que dizia "a versão não foi aposentada" — o append-only existe para que o
  erro do meio-dia continue legível depois da correção da tarde.
- **`mean_reversion_m5.md`** e **`mean_reversion_m5-v1.md`**: veredito, coorte, decomposição,
  `deprecated_at`, e a substituição da nota "segue `active`" pela explicação do que mudou.
- **`Experiments Index`**: as duas linhas da EXP-0028 (catálogo e placar).
- **`mean_reversion.md`**: a linha da irmã de 5 min.

## 15. ARQUIVOS DESTA PASSADA

```
$ git -C C:/dev/project-hunter status --porcelain -- <os arquivos desta passada>
 M obsidian/03-TRADING/Estrategias/mean_reversion.md
 M obsidian/03-TRADING/Estrategias/mean_reversion_m5-v1.md
 M obsidian/03-TRADING/Estrategias/mean_reversion_m5.md
 M obsidian/05-EXPERIMENTS/EXP-0028-mean-reversion-5-min.md
 M "obsidian/05-EXPERIMENTS/Experiments Index.md"
 M .claude/state/notes-T3.84.md
?? .claude/state/exp-drafts/t384/analise.py
?? .claude/state/exp-drafts/t384/analise.out
?? .claude/state/exp-drafts/t384/decisoes-m5-e-mae.csv
?? .claude/state/exp-drafts/t384/q04-funil-k-c5-pedagio.out
?? infra/scripts/sql/research/2026-09-11-t384-q03-dump-decisoes-m5.sql
?? infra/scripts/sql/research/2026-09-11-t384-q04-funil-k-c5-pedagio.sql
```

A árvore é compartilhada: uma `git status` sem pathspec mostra dezenas de arquivos de **outras**
tarefas. Nada disso é meu e nada disso foi tocado. **Nenhum commit foi feito.**

| Arquivo | O quê |
|---|---|
| `…/2026-09-11-t384-q03-dump-decisoes-m5.sql` | dump por decisão (CSV) da coorte da filha **e** do controle pré-declarado, com `atr_pct` e o desfecho da saída |
| `…/2026-09-11-t384-q04-funil-k-c5-pedagio.sql` | K1–K6, por janela, por mercado, C5, pedágio medido, funil de saída, K4 pelo recibo do replay e cobertura de barras por mercado |
| `.claude/state/exp-drafts/t384/analise.py` | blocos de dia (semente 20260910), LOMO, 3 janelas, Δ pareado filha × mãe, decomposição bruta/custo, C5 |
| `…/analise.out`, `…/q04-funil-k-c5-pedagio.out` | as saídas, gravadas para não depender da minha transcrição |
| `…/decisoes-m5-e-mae.csv` | 915 decisões (373 + 542) |

## 16. ASSUNÇÕES NUMÉRICAS QUE EU TIVE DE FAZER NESTE PASSO

1. **Fatias de 15 d, não de 30 d.** Medido: 4 × 30 d = 495 s, acima do teto de 290 s do brief. A
   saída autorizada era "4 mercados × 15 d" e foi a usada. **Efeito declarado:** em cada fronteira
   nova (06-27, 07-27, 08-26) um acompanhamento aberto é liquidado pelo `drain_cohort` no fim da
   fatia — com velas **reais** até o horizonte dele, nunca truncado — e a fatia seguinte encontra o
   slot já rearmado. O horizonte é de 80 min, logo o efeito vive em **3 × 80 min por mercado = 4 h de
   2 160 h (0,19 %)** e só pode **adicionar** entradas perto da fronteira. É a única diferença de
   método contra a EXP-0025.
2. **`--workers 4` num container de 3 CPUs**, 1 acima do que `workers_for` escolheria. Sobreinscrição
   contida pelo *cgroup* do `replay-worker`; não disputa com a faixa viva (outro container, outro
   limite) e não altera número nenhum — o paralelismo é por mercado e cada mercado é uma máquina de
   estados independente.
3. **Uma coorte para as 23 fatias** (a assunção nº 4 do passo 2, mantida). O CLI **aceitou** reusar a
   coorte entre fatias: `--cohort` é repassado sem verificação de unicidade, `count_population` conta
   a coorte inteira (por isso `signals` é cumulativo no recibo) e `--stress` recebeu **uma** coorte,
   como os braços "metades" e "sem-mercado" exigem.
4. **A primeira fatia foi contada como válida**, mesmo com o cliente morto pelo `timeout`: o container
   terminou os quatro mercados, gravou `bars_evaluated 34560` e `errors 0` no recibo, e os quatro
   `last_bar_close` batem no fim da janela. Não houve reexecução — reexecutar teria reavaliado barras
   já decididas.
5. **`r_bruto`** é `(exit_base − entry/1,0006) / initial_risk`, a mesma fórmula da T3.76 q04 e da
   EXP-0025 — o `1,0006` é o meio-spread assumido, removido para chegar ao preço "sem custo". Trocar
   essa fórmula mudaria a decomposição do §12.2 item 5; usei a existente de propósito.
6. **O explain-ledger não sobreviveu.** 23 JSONL (414 720 linhas) foram escritos em `/tmp` dentro de
   containers `docker compose run --rm` — o `replay-worker` não declara volume — e morreram com eles.
   O funil por estado que eu precisava está **durável** no recibo de cada corrida
   (`evaluations_by_state`), e é dele que as linhas `unavailable`/`triggered` desta nota saem. Se
   alguém quiser os JSONL, o conserto é um `volumes:` no serviço, e é commit de outra tarefa.
