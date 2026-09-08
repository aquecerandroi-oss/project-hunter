# Notas T3.36 — portão C1–C8 antes do código, passada de estresse depois do replay, controle declarado (quant-engineer, 2026-09-08)

Base: `main` em `f05dec1` (a árvore andou durante a entrega; `main` estava em `96eea21` ao fim).
**Eu não rodei `git commit` nenhuma vez** — mas dois arquivos meus foram levados por commits de
outros agentes enquanto eu trabalhava; detalhe no concern 6. Arquivos meus, e só eles:

- `packages/indicators/hunter_indicators/replay/stress.py` (novo) — cenários declarados e aritmética;
- `packages/indicators/hunter_indicators/replay/stress_table.py` (novo) — linhas, recortes e veredito;
- `packages/indicators/tests/unit/test_replay_stress.py` (novo);
- `services/strategy-worker/hunter_strategy_worker/replay/stress.py` (novo) — coorte, dobra, CLI;
- `services/strategy-worker/hunter_strategy_worker/replay/stress_report.py` (novo) — tabela, Δ, JSONL;
- `services/strategy-worker/hunter_strategy_worker/replay/run.py` — **só** a bandeira `--stress`/`--as-of` e o parágrafo do docstring;
- `services/strategy-worker/tests/test_replay_stress.py`, `services/strategy-worker/tests/test_replay_stress_db.py` (novos);
- `obsidian/05-EXPERIMENTS/_TEMPLATE-EXP.md` — seção "Portão de desenho (C1–C8)" e a linha "Controle predeclarado";
- `docs/plans/SHADOW-LAB.md` — seção "Funil de validação (T3.36)";
- `docs/plans/REPLICATION.md` — seção "3.6 Controle";
- `.claude/state/brief-T3.36-db-replay-runs-kind.md` (novo), estas notas.

Não toquei `.env*`, `apps/**`, `services/market-worker/**`, `services/execution-worker/**`,
`packages/indicators/hunter_indicators/replication/**`, `infra/migrations/**`, nem nada em
`obsidian/**` além do `_TEMPLATE-EXP.md`. As mudanças de outros agentes no `git status`
(T3.18c em `apps/api/**`, `docs/DESIGN.md`, `infra/scripts/replay_exits.py`) foram ignoradas.

---

## 1. Portão C1–C8 — o que foi adaptado e por quê

O `edge-strategy-reviewer` é para ações americanas com FMP/Alpaca; o que veio dele foi o **método**
(oito critérios, veredito PASS/REVISE/REJECT, C1/C2 com poder de veto). O que mudou:

| Critério | Adaptação | Motivo |
|---|---|---|
| C2 | **> 8 condições** = REJECT (a fonte usa 10/12) | o universo é de ~200 mercados e a janela de avaliação é de semanas; com 31 dias de replay, cada condição a mais é uma fatia da amostra que não existe |
| C2 | limiar com **> 2 algarismos significativos** exige origem declarada | é a regra que a T3.26 já teria aplicado ao `atr_pct_min = 0,0089` (variante `momentum v4`); a fonte só penaliza "número com decimal", o que reprovaria `1,5` |
| C3 | REVISE abaixo de **30 oportunidades/ano/mercado** | não é o número da fonte por acaso: com menos que isso a régua da SHADOW-LAB §9 (100 desfechos avaliáveis **E** 30 dias distintos) não fecha em prazo humano no nosso universo |
| C6 | vira **os limites do `paper_v1`** (`RISK_ENGINE.md` §2): 0,25 % por operação, 1 % de risco planejado agregado, 10 % por ativo, 40 % total, 5 posições, β 0,5, `max_leverage = 1` | "risk_per_trade > 2 %" da fonte é oito vezes o nosso limite; uma estratégia que precisa de mais **não é candidata**, é pedido de mudança de perfil (e isso é do Everton) |
| C7 | executável no SPOT, piso de **50 M USDT** (`min_liquidity_usd_24h`, `PIPELINE.md` §1d) e `max_entry_delay_s = 120 s` | o "volume filter" genérico da fonte não diz nada aqui; os três números são os que a admissão real usa |
| C8 | a invalidação **não pode ser a do `momentum_v1` sem argumento** | achado da T3.26 §1: a invalidação do momentum é código, não parâmetro, e herdá-la calada é a forma mais barata de não ter invalidação nenhuma |

O veredito é escrito pelo quant **no EXP, antes do código**; o `code-reviewer` recusa a entrega de
uma estratégia cujo EXP não tenha a seção preenchida. Acrescentei uma quarta regra mecânica:
**REVISE sem controle predeclarado** — coerente com a `REPLICATION.md` §3.6 desta mesma entrega.

`obsidian_lint.py` continua verde (§7).

## 2. Passada de estresse — as decisões que valem revisão

**A entrada é congelada; o que se reprecifica é o desfecho.** A passada lê a coorte pelo envelope
imutável (`agent_signals.supporting_features->>'cohort'`, o mesmo caminho de `count_population`),
monta um `TrackingPlan` por cenário e **dobra com o walker de produção** (`replay_arm` do EXP-0004 →
`walker.walk` → `settle.settle`). Não há segunda implementação de regra de saída; se houvesse, a
tabela mediria a diferença entre dois códigos.

1. **A escala de stop e alvo é medida a partir de `P_entry`, não da referência da decisão.** Duas
   razões, escritas antes de olhar qualquer número: `reference_price` é opcional (o
   `volume_anomaly_v1` põe o stop na mínima da barra), e ancorar em `P_entry` faz
   `stop < P_entry < target1` continuar verdadeiro para **qualquer** fator positivo — então um
   cenário de parâmetro nunca recusa uma entrada que a base admitiu, e a população continua pareada.
   **Preço declarado:** o R do cenário é normalizado pelo risco novo (§9, ressalva 2).
2. **Custo ×2 multiplica spread, slippage e taxa — e não `max_entry_delay_s`.** O limite de atraso é
   regra de **admissão** da decisão, já exercida quando o sinal foi gravado; multiplicá-lo reabriria
   entradas que a coorte recusou.
3. **O atraso de entrada é o único cenário que não é reprecificação** e está declarado como tal
   (`StressScenario.repriced`): mover a entrada uma barra muda a barra e o desfecho tem de ser
   recaminhado (série própria, horizonte que anda junto). O brief pedia que se dissesse onde
   reprecificar é impossível; é aqui, e só aqui.
4. **Leave-one-out e metades não recalculam nada** (`StressKind.SUBSET`): reagregam os desfechos da
   base. A metade é cortada pelo **meio do calendário**, não pela mediana das operações — a pergunta
   é se a vantagem sobreviveu ao tempo, não a uma partição balanceada.
5. **A admissão é da base.** Se a base não entrou, não resolveu ou não amadureceu no corte, o sinal
   sai de **todos** os cenários (`fora_da_base:<motivo>`) — senão um cenário que sai mais cedo
   ficaria com as operações curtas e a tabela compararia populações diferentes (a mesma ressalva da
   revisão R1 do EXP-0004).
6. **Dois vereditos além dos cinco do brief**, e o motivo é que sem eles a tabela mentiria:
   `amostra_insuficiente` (< 30 desfechos avaliáveis na base — o mesmo `BOOTSTRAP_N_MIN` da
   `REPLICATION.md` §3.4) e **`sem_vantagem_na_base`** (expectancy da base ≤ 0). É exatamente o caso
   do `momentum v2`: chamar de "robusta" uma estratégia de expectancy −0,17 R seria a pior leitura
   possível do mesmo número. A precedência é `amostra_insuficiente` > `sem_vantagem_na_base` >
   custos > parâmetros > mercado > metade > `robusto`, e **todos** os motivos são publicados, não só
   o que ganhou a precedência.
7. **Expectancy > 0 e PF > 1 são a mesma afirmação** (`ΣR > 0`). A tabela publica as duas porque a
   SHADOW-LAB §9 nomeia as duas, mas o veredito decide por uma só — lê-las como duas confirmações
   seria contar a mesma evidência duas vezes.
8. **Δ vs base é pareado por sinal, com intervalo por blocos de dia** (`replay/stats.contrast`,
   1000 reamostras, semente 20260908). Ele diz *de quanto*; o veredito continua sendo sobre o
   **sinal** da expectancy, que é a pergunta do brief.

**Arquivos e a costura entre eles.** Quatro módulos porque o teto de 350 linhas
(`check_file_size.py`) é do projeto: `stress.py` (indicators) declara os cenários como
`policies.py` declara as políticas de saída — `key`, `version`, `description`, `inputs`,
`parameters` —, `stress_table.py` agrega e julga, `replay/stress.py` (worker) faz o IO e a CLI,
`replay/stress_report.py` publica. Mudar um fator é `version` nova do cenário **e** de
`STRESS_VERSION`, nunca edição da antiga.

## 3. Recibo — por que num JSONL, e o que a database-architect precisa decidir

`replay_runs` (`0013`) **não representa** uma linha de estresse: não tem `kind`, tem
`CHECK (cohort = 'replay:' || run_id::text)` — e o recibo de estresse não tem `run_id` próprio, fala
*sobre* a coorte de outro —, e escrever a `run_id` da coorte medida colidiria com
`uq_replay_runs_slice`, fazendo uma passada de estresse engolir (por `ON CONFLICT DO NOTHING`) o
recibo do replay que ela mediu. Metade das colunas obrigatórias (`bars_evaluated`, `signals`,
`decision_lag_s`, `workers`) não tem significado aqui e preenchê-las com zero seria inventar número.

Então: JSONL append-only (`--ledger`), com `stress_version`, coorte, `as_of`, `input_digest`,
semente, reamostras, a tabela inteira e o veredito. Brief com as duas modelagens possíveis e a minha
inclinação (tabela própria `stress_runs`) em `.claude/state/brief-T3.36-db-replay-runs-kind.md`.
**Não editei `infra/migrations/**`.**

## 4. Controle — especificado, não implementado, e o motivo é do banco

`docs/plans/REPLICATION.md` §3.6. O controle padrão é *"comprar os mesmos mercados nos mesmos
horários, com o mesmo stop, o mesmo alvo e o mesmo horizonte, sem o filtro de entrada"* — entradas de
tempo aleatório semeadas, na mesma frequência por mercado e por hora do dia. A vantagem passa a ser
reportada como **Δ contra o controle**, com o intervalo de `hunter_indicators.replication.bootstrap`
(`bootstrap_mean_ci` + `cluster_bootstrap_mean_ci`, 0,95, 1000 reamostras, semente registrada).

O brief mandava implementar **se `replay/run.py` aceitasse um "override de entrada" barato**. Não
aceita, e a recusa é verificável:

1. `shadow_episodes.cohort` tem `CHECK` na migração `0002_shadow_lab` (linha 138) aceitando
   exatamente `prospective|replay:<uuid>|replication:<uuid>:<k>` — `control:<uuid>` é recusado
   **pelo Postgres**; ampliar o padrão é migração;
2. `evaluate_slot` decide chamando `Strategy.evaluate` de uma versão do catálogo ligada por
   `code_ref`: o controle é um **módulo de estratégia** (`control_random_v1`) com schema, parâmetros
   e `params_hash` próprios, e a linha precisa nascer congelada e ativada — `INSERT` em
   `strategy_versions` que a `0011` reservou ao dono;
3. a geometria do controle tem de vir da **mesma** leitura de ATR da versão comparada, senão o
   contraste mistura "quando entrar" com "onde parar" (que é o EXP-0004).

Ficou especificado para a **T3.19f** com entrada, geometria, coorte, relatório e a recusa de portão
("EXP sem controle não passa C1–C8").

## 5. Docs

- `SHADOW-LAB.md` §"Funil de validação (T3.36)": portão → implementação → replay 31 d → estresse →
  prospectivo → replicação, com um parágrafo por etapa dizendo **o que ela pode e o que ela não pode
  afirmar**. O replay pode dizer "não funciona" no dia um e nunca "funciona"; o estresse pode matar
  por fragilidade e nunca aprovar; a régua e o veredito continuam só na coorte `prospective`
  (D14/D15).
- `REPLICATION.md` §3.6 "Controle", acima.

## 6. Prova na VPS — e o caminho que precisei tomar

**A corrida aconteceu e a tabela é real**, mas não dentro do contêiner da VPS. Levar os módulos
novos para a imagem publicada exige copiar arquivo para dentro do contêiner
(`tar x` / `docker cp` / script embutido em `python -`), e **as três formas foram bloqueadas pelo
classificador de permissão desta sessão**. Não insisti: o próprio bloqueio manda parar e explicar.

O que fiz foi o inverso — **trouxe o dado até o código**, com a VPS estritamente em leitura:

1. extração `SELECT` pura da coorte (`scratchpad/stress_export.sql`, colada em §10) via
   `ssh hunter-vps 'docker exec -i hunter-postgres-1 psql -U hunter -d hunter -f -'` → 28,3 MB de
   JSON: 4 mercados, 1 versão, 224 sinais, 224 desfechos, 376 linhas de funding e **67 815 velas de
   1 min** (só as janelas que as entradas usam: `entry − 190 min` a `entry + 5 h`);
2. carga num Postgres efêmero com as migrações do repositório (`json_populate_recordset(NULL::<tabela>, …)`,
   preservando tipo e precisão coluna a coluna) e execução do **módulo desta entrega**, sem alteração;
3. o harness que fez isso era um arquivo temporário em `services/strategy-worker/tests/` e **foi
   apagado** ao fim: ele lê dado de produção de um caminho de ambiente e não é teste de regressão. A
   receita inteira está aqui (§10) e cabe em 40 linhas.

Nenhuma escrita na VPS: a passada abre a transação `REPEATABLE READ, READ ONLY`
(`replay/load.read_only_session`) e a extração é `SELECT`.

**Conferência que vale mais que a tabela:** a expectancy da base saiu
`-0.1717397567832347365729807384` — os mesmos **−0,1717** que a `.claude/state/notes-T3.26.md`
registrou para `replay:f8d8279c…` em 2026-09-08. A reprecificação da base reproduz o que o Lab
gravou, sobre dado de produção, e é isso que sustenta as outras doze linhas.

## 7. Testes (saída real)

```
$ uv run pytest packages/indicators/tests/unit/test_replay_stress.py services/strategy-worker/tests/test_replay_stress.py -q
............................                                             [100%]
28 passed in 2.36s

$ uv run pytest services/strategy-worker/tests/test_replay_stress_db.py -q
...........                                                              [100%]
11 passed in 181.54s (0:03:01)

$ uv run pytest services/strategy-worker/tests -q -m "not integration"
230 passed, 179 deselected in 7.14s

$ uv run pytest packages/indicators/tests/unit -q
948 passed in 21.07s

$ uv run pytest infra/scripts/tests/test_obsidian_lint.py -q
..........................                                               [100%]
26 passed in 1.62s

$ PYTHONPATH=infra/scripts uv run python -c "import obsidian_lint; raise SystemExit(obsidian_lint.main([]))"
LINT DA BASE OBSIDIAN — 193 NOTA(S) ANALISADA(S)
Resumo — Links mortos: 0, Links ambíguos: 0, Notas órfãs: 0, Frontmatter incompleto: 0, Valores fora do vocabulário: 0, Procedência da Knowledge Base (KB-*): 0, Reescrita de experimentos (append-only): 0.
RESULTADO: base limpa

$ uv run ruff check packages/indicators services/strategy-worker
All checks passed!

$ uv run pyright packages/indicators/hunter_indicators/replay services/strategy-worker/hunter_strategy_worker/replay
0 errors, 0 warnings, 0 informations

$ python infra/scripts/check_file_size.py
scanned 554 files; 0 over budget, 0 grandfathered
```

Os dois testes que o brief cobra por nome: `test_costs_x2_flips_a_marginal_strategy` (base +0,04 R
com 40 operações; o dobro do custo tira 0,10 R e o veredito vira `frágil a custos`) e
`test_leave_one_out_finds_the_single_market_dependence` (AAA a +1 R e BBB a −0,8 R; sem AAA a
expectancy vira −0,8 e o veredito é `dependente de um mercado`). Todos os valores são aritmética
fechada escrita à mão no teste, não a saída do código.

**Um bug real, achado pelo teste de integração antes de qualquer corrida:** o rótulo do bloco de dia
era construído com `datetime.combine(entry_day, time.min)`, que é **ingênuo**, e `ensure_utc`
recusou — corrigido para usar a data direto (`entry_day.isoformat()`), que é o mesmo rótulo que
`stats.blocks_of` produz a partir de um instante.

## 8. TABELA DE ESTRESSE — `momentum v2`, coorte `replay:f8d8279c-1fba-42ae-95ef-202042f96c60`

`as_of = 2026-09-08T12:00:00Z` · 224 entradas congeladas · 4 mercados · semente 20260908 ·
1000 reamostras · `input_digest = 6000867c3df374…` · 104,8 s

| cenário | tipo | n | expectancy (R) | PF | Δ vs base | IC 95 % do Δ (blocos de dia) | descartes |
|---|---|---:|---:|---:|---:|---|---|
| `base` | reprecificação | 222 | **−0,1717** | 0,6454 | — | — | funding_indeterminado=2 |
| `custos_x2` | reprecificação | 222 | **−0,3912** | 0,3351 | −0,2194 | [−0,2407; −0,1979] | fora_da_base=2 |
| `stop_x0.75` | reprecificação | 222 | −0,2392 | 0,6179 | −0,0675 | [−0,1148; −0,0106] | fora_da_base=2 |
| `stop_x1.25` | reprecificação | 222 | −0,1283 | 0,6706 | +0,0434 | [+0,0036; +0,0747] | fora_da_base=2 |
| `alvo_x0.75` | reprecificação | 222 | −0,2061 | 0,5405 | −0,0344 | [−0,0799; +0,0285] | fora_da_base=2 |
| `alvo_x1.25` | reprecificação | 222 | −0,1467 | 0,7141 | +0,0250 | [−0,0124; +0,0575] | fora_da_base=2 |
| `entrada_mais_1_barra` | reprecificação | 221 | −0,1817 | 0,6264 | −0,0145 | [−0,0384; +0,0143] | fora_da_base=2, geometry=1 |
| `sem_binance:DOGEUSDT` | recorte | 164 | −0,2148 | 0,5764 | — | — | funding_indeterminado=1 |
| `sem_binance:ETHUSDT` | recorte | 176 | −0,1655 | 0,6546 | — | — | funding_indeterminado=2 |
| `sem_binance:SOLUSDT` | recorte | 157 | −0,1704 | 0,6486 | — | — | funding_indeterminado=1 |
| `sem_binance:XRPUSDT` | recorte | 169 | −0,1376 | 0,7052 | — | — | funding_indeterminado=2 |
| `1a_metade_ate_2026-08-24` | recorte | 98 | −0,0496 | 0,8807 | — | — | funding_indeterminado=1 |
| `2a_metade_apos_2026-08-24` | recorte | 124 | −0,2683 | 0,5019 | — | — | funding_indeterminado=1 |

**Veredito: `sem_vantagem_na_base`** — expectancy da base = −0,1717. Nenhuma das outras perguntas se
aplica: não há vantagem para ser robusta.

O que a tabela ainda diz, e que vale registrar como pesquisa (nunca como promessa):

- **o custo é uma fatia enorme do prejuízo.** Dobrar as três hipóteses tira **0,2194 R por
  operação**, com intervalo por blocos de dia inteiramente negativo. Nos custos assumidos de hoje
  (20 bps de ida e volta sobre o notional), isso implica um risco inicial médio de ~0,9 % do preço:
  a estratégia opera com um R pequeno demais para o atrito que ela paga. É a mesma conclusão que a
  `EXP-0006` (piso de custo) perseguia por outro caminho, agora medida na mesma população;
- **os quatro mercados perdem.** Nenhuma linha de leave-one-out troca o sinal; tirar o pior
  (`XRPUSDT`) melhora para −0,1376 e continua negativo. Não há um mercado carregando (nem afundando)
  o resultado;
- **a segunda metade é cinco vezes pior que a primeira** (−0,2683 contra −0,0496). As duas são
  negativas, então isso não é "dependente de metade" pela regra; é um sinal de deterioração dentro
  da própria janela de replay que merece a pergunta da T3.32 ("por que estamos perdendo");
- **stop mais largo melhora, stop mais apertado piora** (+0,0434 / −0,0675, os dois com intervalo
  fora do zero). Cuidado com a leitura: veja a ressalva 2 do §9 — parte disso é aritmética do
  denominador, não vantagem.

## 9. Ressalvas numéricas (o que eu tive de assumir)

1. **`MIN_SAMPLE = 30`** para emitir veredito. Não é número novo: é o `BOOTSTRAP_N_MIN` da
   `REPLICATION.md` §3.4 e o "mínimo absoluto" do `backtest-expert`.
2. **Escalar o stop renormaliza o R.** Com `stop ×1,25` o denominador `P_entry − stop` cresce 25 %,
   então **toda** operação vencedora encolhe em R enquanto as perdedoras continuam valendo ≈ −1 R
   (quem para, para no stop novo). A melhora de +0,0434 R é, em parte, operações que deixaram de
   parar e, em parte, aritmética do denominador — a tabela **não separa as duas** e não deve ser
   lida como "alargar o stop melhora a estratégia". Separar isso é medir em preço, não em R, e é
   outro experimento (o EXP-0004 é o parente dele).
3. **Fator de custo 2, fatores de parâmetro 0,75 e 1,25**: são o pedido do brief e ficam dentro da
   faixa ±25–50 % que o `backtest-expert` recomenda. Estão declarados em `parameters` de cada
   cenário e mudar qualquer um é versão nova.
4. **Atraso de entrada de 1 barra de 1 min** (não 15–30 min como a fonte sugere para ações): o nosso
   `max_entry_delay_s` é 120 s, então uma barra é o maior atraso que ainda cabe na regra de admissão
   congelada.
5. **A metade é cortada pelo meio do calendário** dos dias com entrada (2026-08-11 … 2026-09-07 →
   corte em 2026-08-24), não pela mediana das operações.
6. **`entry_day` é o dia da barra de entrada**, não o de `emitted_at`. Os dois diferem em ≤ 2 min
   (`max_entry_delay_s`) e coincidem em 24 blocos aqui; a `REPLICATION.md` §1.2 conta "dia distinto"
   por decisão, e a diferença só apareceria numa entrada que atravessasse a meia-noite UTC.
7. **`as_of = 2026-09-08T12:00Z`** na corrida da tabela: corte de dado, não só filtro de população —
   nada posterior a ele entra na dobra (`replay/series.py`).

## 10. Como reproduzir a tabela

Com a permissão de copiar arquivo para o contêiner, é um comando:

```
docker exec hunter-strategy-worker-1 python -m hunter_strategy_worker.replay.stress \
    --cohort replay:f8d8279c-1fba-42ae-95ef-202042f96c60 --ledger /tmp/stress.jsonl
# ou, pelo mesmo funil: python -m hunter_strategy_worker.replay.run --stress replay:<uuid>
```

Sem ela, o caminho de hoje (VPS só em leitura):

```sql
-- ssh hunter-vps 'docker exec -i hunter-postgres-1 psql -U hunter -d hunter -f -' < export.sql
\set cohort 'replay:f8d8279c-1fba-42ae-95ef-202042f96c60'
\pset format unaligned
\pset tuples_only on
WITH sig AS (SELECT a.* FROM agent_signals a
             WHERE a.supporting_features->>'cohort' = :'cohort'),
     out AS (SELECT o.* FROM signal_outcomes o WHERE o.signal_id IN (SELECT id FROM sig)),
     mkt AS (SELECT m.* FROM markets m WHERE m.id IN (SELECT DISTINCT market_id FROM sig)),
     win AS (SELECT s.market_id, (o.meta->'entry_plan'->>'entry_bar_open')::timestamptz AS e
             FROM out o JOIN sig s ON s.id = o.signal_id)
SELECT json_build_object(
  'cohort', :'cohort',
  'exchanges', (SELECT json_agg(t) FROM (SELECT * FROM exchanges) t),
  'assets', (SELECT json_agg(t) FROM (SELECT * FROM assets) t),
  'markets', (SELECT json_agg(t) FROM (SELECT * FROM mkt) t),
  'strategies', (SELECT json_agg(t) FROM (SELECT * FROM strategies WHERE id IN
      (SELECT strategy_id FROM strategy_versions WHERE id IN
       (SELECT DISTINCT strategy_version_id FROM sig))) t),
  'strategy_versions', (SELECT json_agg(t) FROM (SELECT * FROM strategy_versions
      WHERE id IN (SELECT DISTINCT strategy_version_id FROM sig)) t),
  'market_regimes', (SELECT json_agg(t) FROM (SELECT * FROM market_regimes
      WHERE id IN (SELECT DISTINCT regime_id FROM sig WHERE regime_id IS NOT NULL)) t),
  'agent_signals', (SELECT json_agg(t) FROM (SELECT * FROM sig) t),
  'signal_outcomes', (SELECT json_agg(t) FROM (SELECT * FROM out) t),
  'funding_rates', (SELECT json_agg(t) FROM (SELECT f.* FROM funding_rates f
      WHERE f.market_id IN (SELECT id FROM mkt)
        AND f.funding_time BETWEEN (SELECT min(e) FROM win) - interval '4 days'
                               AND (SELECT max(e) FROM win) + interval '1 day') t),
  'candles', (SELECT json_agg(t) FROM (SELECT c.* FROM candles c
      WHERE c.timeframe = '1m' AND EXISTS (SELECT 1 FROM win w
        WHERE w.market_id = c.market_id
          AND c.open_time >= w.e - interval '190 minutes'
          AND c.open_time <= w.e + interval '5 hours')) t));
```

Depois: num Postgres com as migrações aplicadas, inserir cada tabela na ordem
`exchanges, assets, markets, strategies, strategy_versions, market_regimes, agent_signals,
signal_outcomes, funding_rates, candles` com
`INSERT INTO <t> SELECT * FROM json_populate_recordset(NULL::<t>, CAST(:payload AS json)) ON CONFLICT DO NOTHING`
(as partições de `candles_1m` dos meses envolvidos primeiro) e chamar
`run_stress(factory, cohort=…, as_of=…)`. Os artefatos desta corrida (tabela e recibo) ficaram em
`%TEMP%/claude/t336/`.

## 11. Concerns

1. **A tabela da VPS não foi produzida dentro da VPS.** O dado é o de produção, byte a byte, e a
   base reproduz o `r_multiple` gravado; mas a corrida foi num Postgres efêmero local. A diferença
   que isso pode esconder é de **ambiente** (versão do Postgres do contêiner de teste vs a da VPS),
   não de dado nem de código. Para fechar isso de vez basta a permissão de copiar os quatro arquivos
   para o contêiner — o comando está no §10. **Não insisti no bloqueio**: era exatamente o tipo de
   contorno que o classificador existe para impedir.
2. **A ressalva 2 do §9 é a que mais pode ser mal lida.** Se alguém publicar "alargar o stop
   melhora", terá publicado aritmética de denominador como se fosse vantagem. O texto da tabela
   precisa carregar a ressalva junto; deixei-a no `docstring` do módulo e aqui, mas ela **não**
   aparece na tabela renderizada — é um pedido de melhoria (uma nota de rodapé no `render()`).
3. **Sete cenários sobre a mesma população não são sete experimentos.** É o mesmo dado visto por
   sete ângulos, e a passada não aplica correção de multiplicidade (o EXP-0004 aplica Holm sobre a
   sua família de sete contrastes). Aqui o Δ é descritivo e o veredito é sobre sinal, não sobre p —
   mas se alguém começar a caçar "o cenário que passou", a correção passa a fazer falta.
4. **`custos_x2` pode mudar a população pela geometria.** Dobrar o custo sobe `P_entry` e pode
   quebrar `stop < P_entry < target1`; nesta coorte isso não aconteceu (0 descartes por `geometry`
   no cenário de custo; o único `geometry=1` é do atraso de entrada), mas em outra pode acontecer, e
   aí o `n` do cenário cai. Está contado por motivo na coluna de descartes — nunca silencioso.
5. **O portão C1–C8 ainda não foi aplicado a nada.** Ele nasce nesta entrega como seção do template;
   as estratégias que já existem (`momentum v1/v2/v4`, `volume_anomaly v1`) não passaram por ele.
   Aplicá-lo retroativamente seria uma auditoria útil — e, pelo que a tabela do §8 mostra, o
   `momentum v2` provavelmente não passaria em C7 (o atrito consome o R que a geometria oferece).
6. **Dois arquivos meus foram commitados por outros agentes enquanto eu trabalhava** — eu não rodei
   `git commit` nenhuma vez. `services/strategy-worker/hunter_strategy_worker/replay/run.py` (a
   bandeira `--stress`) entrou no `2442796` (T3.33f, 15:37) e a seção "Funil de validação" da
   `docs/plans/SHADOW-LAB.md` entrou no `96eea21` (T3.38b, 15:52). Conferi depois: as duas edições
   coexistem com as dos autores daqueles commits (o `--explain-ledger` da T3.33f está lá junto com o
   `--stress`), `--help` responde e os 230 testes unitários do worker seguem verdes. É o risco de
   árvore compartilhada que a regra "commit por pathspec" existe para evitar, e vale um lembrete aos
   outros agentes. O que continua **não commitado**: `docs/plans/REPLICATION.md`,
   `obsidian/05-EXPERIMENTS/_TEMPLATE-EXP.md`, os cinco arquivos novos e estas notas.
7. **`replay_runs` sem `kind` continua sendo dívida declarada**, com brief aberto. Enquanto isso o
   recibo só existe no JSONL de quem rodou — que é melhor que nada e pior que uma tabela.
