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
