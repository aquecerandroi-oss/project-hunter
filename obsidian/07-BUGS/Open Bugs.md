---
tags: [bugs, abertos]
updated: 2026-09-10
status: aberto
owner: sexta-feira
severity: misto
opened: 2026-09-05
closed: ""
---

# Open Bugs

Levantado de `.claude/state/milestone.json` (histórico de M0) e `docs/SECURITY.md`. Nenhum destes bloqueia o fechamento do M0 — foram conscientemente registrados como conhecidos em vez de resolvidos, mas continuam abertos.

## Abertos na T3.73 (2026-09-10, medição na VPS; achado do D-P9)

Consultas em `infra/scripts/sql/research/2026-09-10-t373-q0{0..4}-*.sql`, todas dentro de
`repeatable read read only`; leitura de 2026-09-10 01:07 BRT (04:07Z). Notas:
`.claude/state/notes-T3.73.md`.

- **~~O Lab decidia sobre a linha `spot` com o modelo de custo do perpétuo~~ — corrigido na T3.73,
  aguardando deploy.** `markets` tem duas linhas por símbolo (528 perpétuas, 490 spot; 200 e 18
  monitoradas) e o consumidor do `strategy-worker` avaliava a vela que chegasse. Números: **340
  sinais** em linha spot (93 em 08/09, 247 em 09/09, nenhum antes — o caminho spot subiu em 08/09),
  **133 desfechos terminais e os 133 com `r_multiple` NULL**, todos por `funding_schedule_unknown`
  — `funding_rates` tem 8 235 linhas e **zero** para mercado spot, por construção. Contra 6 557
  terminais perpétuos com só 76 sem R. **179 trios (versão, símbolo, barra) foram decididos nas
  duas linhas**, o que duplica qualquer contagem de aposta única (NEAR e ZEC de 09/09 são os casos
  do D-P9). Duas versões `paper` participaram (`momentum v3`: 44 sinais spot; `mean_reversion v14`:
  7). Correção: `hunter_strategy_worker/consumer.py` recusa toda vela que não seja `perpetual`
  antes de resolver o mercado, contando em `hunter_shadow_bars_skipped_total{reason}`
  (`DECISION_MARKET_TYPE`, T3.73). **Não há reprocessamento**: as 340 linhas antigas ficam na base
  e toda leitura de pesquisa precisa filtrar `markets.market_type = 'perpetual'`.
- **HIGH — o Lab está perdendo metade das entradas por atraso de processamento, não por mercado.**
  `no_entry` com `late:delay` foi de 18 (06/09) e 10 (07/09) para **105 (08/09), 1 637 (09/09) e 73
  nas primeiras horas de 10/09** — **47,2 %** de todos os sinais prospectivos de 09/09 e **53,7 %**
  dos de 10/09. `late:delay` não é o preço fugindo da zona: `plan.py::plan_entry` marca assim
  quando `entry_bar_open − source_bar_close > max_entry_delay_s` (120 s), e `entry_bar_open` é o
  minuto seguinte à decisão — ou seja, é o **worker chegando tarde à barra**. O atraso mediano
  decisão-menos-barra saiu de **2,0 s** (01 a 05/09) para **11,8 s** (07/09), **21,8 s** (08/09),
  **107,9 s** (09/09) e **125,1 s** (10/09), com p95 de 263,8 s em 09/09. Acima de
  `eligibility_max_lag_s` (300 s) a barra nem vira sinal (`unavailable`), então o denominador real
  é ainda maior e **não está na base**. Sem dono nesta tarefa (T3.73 é só medição); o candidato
  natural é o custo por barra do roster (21 versões decidindo em 232 mercados em 09/09, contra 14
  versões e 12 mercados em 01/09).
  **Atualização T3.74 (2026-09-10, 01:48 BRT / 04:48Z):** o atraso continua alto (mediana 94–207 s
  hora a hora entre 09/09 23:00Z e 10/09 04:00Z) e **começou a subir na noite de 08/09, antes dos
  dois deploys do dia** (`d21a11d` 09/09 12:19 BRT, `572d3b6` 18:36 BRT) — às 08/09 00:00Z a mediana
  já era 11,9 s e fechou o dia em 87–110 s, então os dois deploys não são a causa isolada. **Achado
  novo, confirmado por grep**: o portão que existe para exatamente este cenário —
  `replay/budget.py::live_lane_degraded`, escrito, testado e documentado como "checado antes de toda
  fatia" — **nunca era chamado** por `replay/run.py` (nem no dreno da fila nem na invocação direta),
  então um replay/backfill continuava fatiando no orçamento cheio mesmo com a linha viva agonizando.
  `replay_runs` mostra o dreno praticamente sem folga (93,7 % de uma hora ocupada às 10/09 03:00Z) e
  `docker stats` pegou `hunter-postgres-1` em 178 % de CPU num instante *sem* replay rodando — a
  linha viva sozinha, com 11 versões ativas sobre 200 mercados perpétuos monitorados e sem cache de
  contexto entre versões da mesma barra (`context.py`/`decide.py`), já pressiona o Postgres que
  qualquer replay concorrente satura. **Corrigido nesta tarefa**: `_drain` e o caminho direto de
  `replay/run.py` agora chamam o portão antes de consumir a fila/rodar a fatia (testes cobrindo os
  dois ramos). **Ressalva importante**: o portão só lê `outbox_lag_s` e o heartbeat, nunca o atraso
  decisão-menos-barra — no instante da medição `outbox_lag_s` estava em 0,0 com heartbeat fresco, ou
  seja, o portão teria dito "saudável" durante o pior período já visto. A causa dominante do atraso
  segue sem correção: custo N×M por barra e um portão cego ao próprio sintoma — plano em
  `.claude/state/brief-T3.74b-consumer-lag-e-custo-por-barra.md`.
  **Atualização T3.74b (2026-09-10):** dois avanços parciais, nenhum fecha o item sozinho.
  (1) `live_lane_degraded` ganhou um terceiro motivo, `consumer_lag:<n>`, lendo `XINFO GROUPS` de
  `market.candles.closed`/`strategy-worker.shadow` (`replay/consumer_lag.py`, novo;
  `REPLAY_CONSUMER_LAG_MAX = 100`, provisório — Astra, revisão do diff: "um blip de 13 observado
  durante degradação confirmada não estabelece uma distribuição saudável"). **Medido ao vivo às
  05:52–05:56Z do mesmo dia**: esse `lag` ficou em 0 quase o tempo todo (um blip de 13 num burst de
  5m) **enquanto o atraso decisão-menos-barra medido por SQL no mesmo intervalo continuava em
  97,8–185,0 s** (mesma barra de 05:45Z, `agent_signals.emitted_at` escalonado por até 148 s entre
  mercados) — ou seja, este terceiro motivo é um sinal real e independente (pega um consumidor
  travado/morto), mas **não captura o sintoma medido**: o atraso é hipoteticamente do lado do
  publicador (candles da mesma barra chegando escalonados ao longo de ~3 min), não um backlog do
  grupo consumidor, e isso é hipótese, não causa estabelecida (Astra: `consume()` entrega lotes de
  até 10 e marca como lidas antes de cada uma ser processada e confirmada, então trabalho já
  entregue e ainda não terminado também não apareceria neste `lag`). (2) Desenho aprovado e
  implementado do cache de contexto por família: `hunter_strategy_worker/context_cache.py` agrupa as
  versões devidas por `strategy_key` e reaproveita `replay/candles.py::WindowCache` (já provado
  byte-idêntico a `load_candles`) para pré-carregar uma vez o teto do grupo — reduzindo, no
  benchmark de 11 versões (8+3) × 16 mercados, as chamadas a `load_candles` de 176 para 32 (uma por
  família por mercado). Prova de equivalência (`test_context_cache_engine.py::TestEquivalence`):
  cada versão de uma família de 4 (duas janelas distintas, 1560 e 1570 min) decide byte a byte igual
  com e sem o cache. Benchmark (mesmo arquivo, `TestBenchmark`, testcontainer local, 2026-09-10):
  **176 → 32 chamadas a `load_candles`** (11 versões × 16 mercados → 2 famílias × 16 mercados, exato,
  como desenhado) e **128,4 s → 116,3 s (1,4 → 1,5 avaliações/s, ~9,5 %)** de tempo total nesta
  execução local (revalidado com relógio determinístico após a revisão da Astra apontar que o teste
  original dependia do relógio real) — **a hipótese é que custos por versão que o cache não afeta
  (`slots.lock_slot`, `load_regime_asof`,
  `persist_decision`, `slots.advance`) limitem o ganho, mas a composição desse tempo não foi
  decomposta nesta tarefa, e o efeito na VPS real (Postgres já em 178 % de CPU, 200 mercados,
  janelas de até 6000 min) não foi medido aqui** (Astra, revisão final do diff: "esse diagnóstico
  orienta a próxima otimização para um custo não estabelecido"). Benchmark completo:
  `.claude/state/notes-T3.74b.md` §2.
  Desenho, com as duas ressalvas que a Astra levantou (semântica de fotografia do candle, isolamento
  de falha por família): `docs/plans/T3.74b-CONTEXT-CACHE.md`.
- **LOW — a sonda de elegibilidade divide a janela de 50 entradas com o universo spot.**
  `eligibility.universe_changed_after` lê as `PROBE_ENTRIES = 50` entradas mais recentes de
  `market.universe.changed` e casa por `envelope.key`. O spot publica com chave própria
  (`binance:spot`, `durable.enqueue_universe_changed` + `keys.market_slug`), então **não** rotula o
  perpétuo errado — verificado no código, era a suspeita natural e está descartada. O que resta é
  diluição: eventos spot ocupam lugares da janela e podem empurrar o último evento **perpétuo**
  para fora dela, caso em que a sonda responde "nada mudou" (a direção otimista já declarada no
  módulo). Sem medição; só vale registrar antes que alguém aperte `PROBE_ENTRIES`.

## Abertos pela revisão da Astra "o Lab está pronto?" (2026-09-08)

Origem: [[2026-09-08-shadow-lab-pronto]] (transcrição em
`.claude/state/astra-review-lab-pronto-2026-09-08.md`). **Nenhum destes foi reproduzido por medição
nesta revisão** — são leitura de código com arquivo:linha e cenário de falha; onde houver número
operacional, ele vem de leitura já registrada, não de consulta nova. Estado de todos: **aberto
2026-09-08 (Astra)**.

### Caminho de replicação (dono: **T3.18c**) — **os quatro fechados em `c8c9dc6`**

Os quatro achados desta seção (CLI que torna o pai promissor com replay, duas definições de
"avaliável", maturidade/PF divergentes entre placar e replicação, irmã amadurecendo duas vezes com a
mesma evidência) foram corrigidos pela **T3.18c** e movidos para [[Resolved Bugs]]. Ficou **dívida**
declarada, aberta abaixo: o contrato é um só, mas continua com **duas implementações**.

### Autonomia paper — as cinco etapas sem prova (dono: **T3.29**, `.claude/state/brief-T3.29-autonomy-acceptance-run.md`)

Contexto medido e já registrado: **154 sinais paper, 0 propostas, 0 posições, 0 trades** — o caminho
autônomo nunca rodou de ponta a ponta ([[Diario/2026-09-08]]). A linha `momentum v3` já está ativa
desde **02:57 de Brasília**; a ativação **não** é pendência. Os sete itens com o estado de cada um
estão em [[Execution Engine]], [[Paper Trading]] e [[Risk Engine]].

- **HIGH (admissão) — ativar a versão não basta: falta o vínculo em `agents`, e agora está medido.**
  Sem vínculo habilitado para a **versão e a carteira corretas** o sinal nem pertence àquela fila;
  com agente pausado, `agent_unavailable`.
  `services/execution-worker/hunter_execution_worker/bridge_repo.py:130`,
  `services/execution-worker/hunter_execution_worker/bridge_screen.py:215`.
  **Medido na VPS em 2026-09-08 entre 14:03Z e 14:12Z (T3.29): a tabela `agents` tem 0 linhas** — é a
  causa raiz de "154 sinais paper, 0 propostas". O funil de 24 h fecha assim: 171 sinais → 121 com
  par spot → 22 acima do piso D1 → **0** com β válido. Estado: **aberto — deixa de ser "a medir" e
  passa a ser pendência do operador**, com o comando auditado em `docs/ACTIVATION.md` §8a, que
  **não** foi rodado. Ver [[Diario/2026-09-08]].

- **MEDIUM (risco, VPS) — `portfolios.risk_profile_id` é NULL e não existe
  `risk_profiles.preset='paper_v1'` na VPS.** Medido em 2026-09-08 (T3.29). Os limites em vigor
  continuam **corretos** porque `admit(..., limits=PAPER_V1)` usa o objeto do motor, não a linha do
  banco — mas o banco não sabe declarar sob que perfil a carteira opera. **Cenário:** um segundo
  perfil (ou uma auditoria do que estava valendo numa data) não tem de onde ser lido, e o produto
  passa a depender de uma constante em código para explicar uma decisão de risco já tomada.
  Estado: **aberto 2026-09-08 (T3.29, medido)**.

- **HIGH (segurança, pré-requisito da autonomia) — o compose entrega `DATABASE_URL_MIGRATIONS` aos
  serviços de runtime pelo bloco compartilhado.** `infra/vps/docker-compose.prod.yml:30` e `:59`.
  **Cenário:** execução de código comprometida em qualquer serviço de runtime usa a conexão de
  **dono** para contornar os grants de ativação e de isolamento — o risco permanece mesmo com a
  conexão normal rodando sob papel restrito. Dono: `devops-engineer` (**T3.15d**,
  `.claude/state/brief-T3.15d-owner-dsn.md`). Estado: **aberto 2026-09-08 (Astra)** — e a Astra o
  trata como condição **anterior** a ligar `ENABLE_PAPER_AUTONOMY`.

**Backup restaurável não é bug — é prova que falta.** Os registros ainda relatam ausência de dumps
(`docs/reports/M3.md:261`) e o bootstrap já invoca o script com `bash`
(`infra/scripts/bootstrap_vps.sh:346`): sem uma verificação atual não se pode chamar o incidente
antigo de vigente **nem** de resolvido. Registrado como **"a comprovar em T3.29" (item 6)**, não
como bug aberto.

### Limite de requisições (dono: **T3.28a-seguimento**)

- **MEDIUM — negação de serviço compartilhada no bucket do `web`.** Uma conta dispara SSR
  repetidamente e **cada** chamada gasta primeiro o bucket de IP do `web`, inclusive as que o limite
  de principal recusaria depois; passando de 6.000/min, **outras contas recebem 429**.
  `apps/api/hunter_api/middleware/rate_limit.py:133`.
  **Cenário:** um usuário com uma aba em laço derruba o site para os demais sem nunca ultrapassar o
  próprio limite de principal. Aumentar o teto reduz a incidência normal e **não elimina a falha**.
  A Astra não achou bypass direto por XFF de peer externo no caminho implementado (`apps/web/lib/server/api.ts:7`,
  `infra/vps/docker-compose.prod.yml:66`, `apps/api/hunter_api/auth/rbac.py:116`) — o desenho da
  T3.28a está de pé; o que falta é este cenário. Estado: **aberto 2026-09-08 (Astra)**.
  **Acréscimo de 2026-09-08 (noite):** a T3.28b (`42ec146`) tirou o **pior sintoma** — um 429 no
  `/me` não derruba mais a tela, o shell degrada com banner e *retry* com backoff — e a T3.28c
  (`036b7d9`) fez as Server Actions verificarem a sessão **antes** de chamar a API, o que reduz a
  superfície. **A causa continua aberta:** uma conta autenticada em laço ainda gasta o balde
  compartilhado do `web` e as outras contas recebem 429. Não fechar.

- **LOW (texto do brief, já contornado) — `FORWARDED_ALLOW_IPS` não resolve nome por DNS.** O Uvicorn
  instalado transforma valores não reconhecidos como IP em literais, então `web` como **nome** nunca
  casa com o peer numérico (`.venv/Lib/site-packages/uvicorn/middleware/proxy_headers.py:128`). A
  implementação da T3.28a escolheu IP fixo, então não há defeito em produção — fica registrado para
  que ninguém "simplifique" de volta para o nome. Estado: **aberto 2026-09-08 (Astra)**.

### Correção de texto (dono: **orquestrador**) — **fechada em `c8c9dc6`**

A linguagem estatística de `docs/plans/REPLICATION.md` §46/§78 (√2 em vez de ~2×; "quatro repetições
independentes" que reutilizam dados) foi corrigida pela T3.18c. Movida para [[Resolved Bugs]].

## Aberto na tarde de 2026-09-08 (revisão do commit `50932ec`, fora da revisão da Astra)

- **CRITICAL — `earliest_known` obsoleto dentro do ciclo: código corrigido em `1ca7cf5`, o dado ainda
  não.** O defeito (o mínimo conhecido lido uma vez por ciclo transformava janelas legítimas em
  `unrecoverable/before_listing`, sem reabertura possível) está fechado no código pela **T3.7e+T3.7f**
  — `before_listing` agora exige resposta vazia real da exchange **E** `gap_end` abaixo do mínimo
  conhecido **E** nenhum pedaço do mesmo mercado ter persistido vela mais antiga naquele ciclo — e os
  `market-worker` voltaram à imagem nova. **O que continua aberto é a reparação do dado:** as
  **5 janelas de BTCUSDT e 5 de UNIUSDT** marcadas falsamente terminais em 2026-09-08 continuam
  fechadas no banco da VPS. O SQL idempotente e restrito ao incidente
  (`infra/scripts/sql/2026-09-08-reopen-false-unrecoverable.sql`) **não foi executado**. Estado:
  **aberto — pendência do operador**, depois do deploy do `1ca7cf5`. Ver [[Diario/2026-09-08]].

## Abertos no plantão da noite de 2026-09-08 (T3.32b)

- **MEDIUM (dívida de contrato) — o veredito do placar tem um contrato só e duas implementações.**
  A T3.18c (`c8c9dc6`) unificou a *regra* — imaturo → `inconclusivo`; maduro com
  `expectancy_r > 0` **e** profit factor passando → `validada`; o resto → `reprovada`, com PF nulo
  por `sem_perdas` contando como "passa" —, mas ela continua escrita em dois lugares:
  `apps/api/hunter_api/services/lab_scoreboard_metrics.py:51` (`compute_verdict`) e
  `packages/indicators/hunter_indicators/replication/stats.py:240` (`profit_factor_passes`) e `:251`
  (`scoreboard_verdict`). O docstring do segundo diz textualmente que é "**a mesma regra**, aqui como
  função pura" — o que documenta a duplicação, não a resolve.
  **Cenário concreto:** o Everton pede para o PF passar a exigir `> 1,1`. Quem mexer no placar e não
  no pacote (ou vice-versa) reintroduz exatamente o MEDIUM que a Astra achou e a T3.18c fechou —
  **a mesma população `validada` de um lado e `reprovada` do outro, sem nenhuma mudança de
  evidência**. E a divergência só aparece quando alguma versão amadurecer, que é o pior momento
  possível para descobri-la. **Correção:** uma implementação só (a do pacote, que é pura e testável
  sem banco) e o serviço da API chamando-a. Estado: **aberto 2026-09-08 (Sexta-feira, leitura de
  código)** — dívida, não regressão: hoje as duas concordam.

- **MEDIUM (produto, VPS, tela) — a topbar mostra "sem tempo real": o socket do navegador para o
  gateway não abre.** `apps/web/components/system/live-status.tsx:154` define
  `liveFeedDown = socketStatus !== "open"` (`useMarketChannels`, canal `rt:system`) e a topbar
  (`apps/web/components/layout/topbar.tsx:121`) renderiza a variante compacta com esse flag.
  **Observado no navegador contra a VPS em 2026-09-08 pela Sexta-feira; não reproduzido por medição
  nesta tarefa** — não há SQL, log de Caddy nem contagem de assinaturas anexados aqui, e isso está
  dito de propósito. **Cenário:** os pontos e o `ws_state` continuam mostrando o **último estado
  conhecido pelo servidor**, então a tela parece viva enquanto o navegador está desconectado; só a
  idade "há Ns", que continua correndo, e o texto "sem tempo real" denunciam. **Próximo passo (o que
  fecha ou reclassifica este item):** confirmar no navegador se o `status` do socket é `connecting`,
  `closed` ou `error`; se a assinatura de `rt:system` atravessa o Caddy da VPS; e se o token de auth
  do socket está sendo obtido. Estado: **aberto 2026-09-08 (Sexta-feira, observação de tela)**.

- **MEDIUM (produto, VPS, tela) — o painel "Execução paper" do System aparece inteiro como
  "indisponível", e a tela não distingue "sem worker" de "worker sem dado".**
  `apps/web/components/system/execution-paper-card.tsx` recebe `worker: WorkerHeartbeat | null` e
  imprime `indisponível` em cada linha quando o valor é nulo — o que é a regra certa (nunca fabricar
  um `0`). O problema é a montagem a montante:
  `apps/api/hunter_api/services/system_status.py:193` devolve **`None` para a linha inteira** quando
  o `ts` do heartbeat falta ou não parseia, e o próprio hash `hb:execution:paper` tem `EXPIRE`
  (`services/execution-worker/hunter_execution_worker/heartbeat.py:40`). **Cenário:** o
  `execution-worker` parado, reiniciando num deploy, ou com a chave expirada produz **exatamente a
  mesma tela** que um worker vivo que não conseguiu montar os campos — e a diferença entre as duas
  é a diferença entre "não tem o que mostrar" e "a carteira está desprotegida agora".
  **Observado no navegador contra a VPS em 2026-09-08 pela Sexta-feira; não reproduzido por leitura
  do Redis nesta tarefa.** **Próximo passo:** ler `hb:execution:paper` na VPS (existe? qual a idade
  do `ts`?) e, independentemente do resultado, dar ao card um estado explícito de "nenhum heartbeat"
  distinto de "heartbeat sem estes campos". Estado: **aberto 2026-09-08 (Sexta-feira, observação de
  tela)**.

## Abertos pelo dia um das quatro estratégias novas (2026-09-08, T3.33d/T3.33e, arquivados na T3.33h)

Os três abaixo **bloquearam medição declarada como obrigatória** nas páginas de experimento — não são
suspeitas de código, são instrumentos que faltaram na hora de ler o dado. Estado de todos: **aberto
2026-09-08 (Sexta-feira, a partir das notas do `quant-engineer`)**.

- **HIGH (instrumento de pesquisa) — o replay não persiste o *motivo* de cada barra, só o estado.**
  `services/strategy-worker/hunter_strategy_worker/replay/simulate.py` conta
  `evaluations_by_state` (`unavailable`/`not_triggered`/`triggered`/`rejected`/`ineligible`) e
  **descarta a razão** (`atr_gap`, `trend_gap`, `not_compressed`, `no_breakout`, `rvol_low`,
  `atr_out_of_range`, `geometry_invalidation`). **Cenário concreto, já ocorrido:** a
  [[EXP-0008-breakout-compressao-de-volatilidade]] exige (obrigação C2) a distribuição de
  `squeeze_ratio` em barras que disparam e que não disparam, e a
  [[EXP-0009-mean-reversion-pullback-em-tendencia]] exige a fatia `atr_gap`/`trend_gap` — **nenhuma
  das duas foi obtível** no replay de 31 dias. O que se conseguiu foi por **diferença** entre duas
  versões sobre as mesmas barras (`trend_gap = 0`) e por **construção** (as 14 rejeições são a segunda
  porta de geometria) — dois contornos que só funcionaram porque duas versões rodaram as mesmas
  11 904 barras no mesmo dia. **Correção proposta e já em voo:** `--explain-ledger` no `replay.run`
  gravando `(bar_close, market, state, reason, detail)` em JSONL — só arquivo, sem tabela nova, sem
  mudar uma linha da avaliação (**T3.33f**,
  `.claude/state/brief-T3.33f-breakout-v2-explain-ledger-session-orb.md`).

- **HIGH (dado ausente) — `market_regimes` tem UMA linha no banco inteiro, e por isso o corte C4 é
  impossível em replay.** A única linha começa em `2026-09-06 18:18:05`; não há regime gravado para
  agosto. **Cenário:** o portão C1–C8 marcou **C4 = warn** nas quatro estratégias novas justamente
  porque o plano de validação não estratificava por regime, e a correção prometida ("a primeira
  avaliação quebra o resultado por regime de BTC") **não pôde ser cumprida em nenhuma das duas
  avaliações do dia um** — o SQL existe
  (`infra/scripts/sql/research/2026-09-08-07-regime-btc.sql`) e não tem o que ler. Consequência: toda
  obrigação de regime só é cumprível **prospectivamente**, e dizer "quebramos por regime" antes disso
  seria inventar corte. A causa raiz é o warm-up do classificador, já rastreado em
  [[KB-0031-o-classificador-de-regime-esta-mudo-por-warm-up]]; o que este item acrescenta é o **efeito
  medido**: duas avaliações publicadas com uma obrigação de portão declarada como não cumprida.

- **MEDIUM (teste) — `test_isolation` não cobre `/risk/limits`** (achado 3 da revisão da T3.37c).
  `apps/api/tests/integration/test_isolation.py` enumera à mão as rotas que um intruso tenta
  (`kill-switch`, `kill-switch/resume`, as sete leituras de portfólio da T3.8a…), e
  **`GET .../risk/limits`, que `apps/api/hunter_api/routers/risk.py` serve, não está na lista**
  — conferido nesta tarefa por leitura dos dois arquivos. **Cenário:** alguém acrescenta um filtro por organização errado (ou o
  remove num refactor) em `/risk/limits` e a suíte inteira continua verde — a regressão só apareceria
  com dois tenants em produção, que é exatamente o cenário que o teste existe para impedir. Não é
  vazamento observado: hoje a rota filtra certo. É **cobertura ausente**, e a diferença entre as duas
  coisas está dita de propósito. **Correção:** incluir `/risk/limits` na tabela de rotas do
  `test_isolation` e travar o conjunto com uma asserção de completude, para que a próxima rota nova
  não entre calada.

## Abertos no plantão da noite de 2026-09-08 (T3.41 — fecho do dia no Lab)

Os três abaixo saíram das notas T3.33g, T3.39 e T3.40. **Nenhum foi reproduzido por medição nova
nesta tarefa**: os números vêm das leituras já registradas naquelas notas, com o arquivo:linha ou o
recibo citado. Estado de todos: **aberto 2026-09-08 (Sexta-feira)**.

- **HIGH (autonomia paper, com correção em voo) — a trava que impede aposentar a linha `paper` com
  posições abertas olha uma coluna que nunca é preenchida.** O `--deprecate` da T3.39
  (`services/strategy-worker/hunter_strategy_worker/deprecate.py`) recusa depreciar uma versão
  `purpose = paper` se houver posição aberta, e faz essa checagem por **`positions.agent_id`**. Mas
  `positions.agent_id` **nunca é escrito pelo execution-worker**: o caminho real da linhagem é
  `positions.metadata->>'proposal_id' → orders.proposal_id → trade_proposals.agent_id →
  agents.strategy_version_id`. **Cenário concreto:** com `ENABLE_PAPER_AUTONOMY` ligado e a
  `momentum v3` (a linha `paper`) com posição aberta, um `--deprecate momentum v3` **passaria a trava
  em silêncio** — a consulta devolveria zero linhas —, o roster descartaria a versão na recarga
  seguinte e a posição ficaria órfã de versão viva. Não é vazamento observado: hoje a flag está
  desligada e não há posição. É **a trava certa lendo o campo errado**, que é pior que trava
  ausente, porque parece protegida. **Correção em voo:** T3.39b
  (`.claude/state/brief-T3.39b-deprecate-review-fixes.md`), achado ALTA-1 da revisão da T3.39.

- **MEDIUM (instrumento de pesquisa) — `outside_session_window` rotula as 6 horas mortas do dia como
  sessão `us`.** No livro-razão da `session_orb v1`, **2 852 das 4 092** recusas por janela caem no
  rótulo `us` — contra 372 em `europe` — só porque `_session_open` devolve a **última abertura ≤
  corte** e não existe abertura declarada depois das 13:00 UTC. As barras de 18:00–24:00 UTC não
  pertencem a sessão nenhuma e mesmo assim são contadas como americanas. **Cenário:** qualquer painel
  ou consulta que plote "recusas por sessão" a partir do livro-razão vai afirmar que a sessão
  americana rejeita 7,7× mais que a europeia, o que é artefato de rótulo, não fato de mercado.
  **Não contamina nenhum número publicado** em [[EXP-0010-session-orb-faixa-de-abertura]]: a
  decomposição das decisões é pela sessão da barra que decidiu. **Correção honesta:** um rótulo
  `fora_de_sessao` distinto — e isso é **versão nova** da estratégia, não ajuste, porque muda o que a
  regra grava. Origem: `.claude/state/notes-T3.33g.md`, CONCERN 7.

- **MEDIUM (deploy) — deploys parciais deixam os serviços em imagens diferentes, e o modo de falha
  que isso arma é o Lab emudecer atrás de um `/ready` verde.** Medido às 19:37Z: `hunter-api-1` e
  `hunter-web-1` em `c86ed19`, `hunter-strategy-worker-1` em **`c29cbef`** (quatro commits atrás),
  `execution-worker` e `scanner-worker` em `b5d4f9b`, `market-worker` em `1ca7cf5` — **cinco imagens
  ao mesmo tempo**. Naquela corrida foi inofensivo (conferido: o worker calculava o **mesmo** digest
  `a4d514ad…` que o `hunter-api-1` imprimia no dry-run), mas o cenário é claro e é exatamente o que o
  `code_ref` por versão existe para evitar: **um dia a `api` ativa uma versão cujo `code_ref` o worker
  não reconhece, a versão entra no roster como `unrunnable` e o Lab para de avaliar sem que nada fique
  vermelho.** Um segundo efeito já ocorreu no mesmo dia: um redeploy alheio às 19:12Z **apagou os
  livros-razão em `/tmp`** de outra tarefa em execução (CONCERN 4 da T3.40), destruindo diagnóstico
  que não pôde ser regenerado sem destruir a medição. **Corrigido nesta noite pelo procedimento** —
  `compose.sh update` passou a alinhar todos os serviços —, e a **regra fica**: deploy alinha todos os
  serviços, ou não é deploy. Origem: `.claude/state/notes-T3.33g.md` CONCERN 1 e 9,
  `.claude/state/notes-T3.40.md` CONCERN 4.

### Duas dívidas de instrumento que continuam abertas e ganharam evidência hoje

- **`replay_runs` não tem `kind`, então a passada de estresse não tem recibo durável.** O recibo vive
  só no JSONL de quem rodou (`--ledger`). A tabela não pode representar uma linha de estresse: não há
  `run_id` próprio (a passada fala *sobre* a coorte de outro) e escrever a `run_id` da coorte medida
  colidiria com `uq_replay_runs_slice`, fazendo uma passada engolir por `ON CONFLICT DO NOTHING` o
  recibo do replay que ela mediu. Brief com as duas modelagens em
  `.claude/state/brief-T3.36-db-replay-runs-kind.md`. **Dono: `database-architect`.**
- **`mfe` é limite inferior em metade das linhas** (98 de 196 na `momentum v6`, 136 de 224 no pai,
  `ambiguous = true`), e os `bounds` gravados em `meta.excursions` continuam sem uso. É por isso que
  "1,0 % com MFE ≥ 2 R" convive com "53 alvos de 2 R atingidos" na mesma coorte — os dois números
  estão certos e medem coisas diferentes. Qualquer leitura de cauda a partir de MFE hoje é
  conservadora por construção. Mesma pendência que a T3.32 deixou.

## Abertos na T3.21 (higiene da base)

- **LOW (base de conhecimento) — 32 das 75 notas de `11-KNOWLEDGE` estão com
  `confiança: "?"`.** O rótulo só é preenchido quando o campo `evidencia` começa
  por exatamente um dos quatro valores; evidência mista (documentação + medição
  própria + preprint) fica `?`. **Cenário:** uma nota em `?` não pode ser filtrada
  por qualidade de evidência, então uma busca por "o que aqui é replicado" devolve
  menos do que a base realmente tem, e uma hipótese fraca pode passar por forte
  no [[Strategy Backlog]] por falta do rótulo. Não é dado errado — é dado ausente,
  e adivinhar seria pior. Dono: Sexta-feira, em passes de curadoria, uma nota por
  vez, lendo a fonte.

## Abertos no plantão do meio-dia de 2026-09-08 (backfill e deploy)

- **HIGH (produto, VPS) — o backfill histórico é uma fila global *newest-first*, e
  isso deixou o BTC em 14 dias enquanto ETH/SOL/XRP/DOGE têm 32: o β espera o
  BTC.** Medido na VPS em 2026-09-08 12:35Z sobre `candles` de 1 min (287 mercados,
  3.294.363 barras):

  ```
   dias | mercados |                                       quais
  ------+----------+------------------------------------------------------------------------------------
     32 |       10 | BNBUSDT,DOGEUSDT,ETHUSDT,LINKUSDT,PROMUSDT,SOLUSDT,SUIUSDT,TAOUSDT,XRPUSDT,ZECUSDT
     14 |        5 | ARBUSDT,BTCUSDT,DASHUSDT,NEARUSDT,UNIUSDT
     11 |      156 |
     10 |       16 |
  ```

  Dez mercados já têm os 32 dias pedidos (desde 2026-08-08 03:32Z); o **BTC** — que
  é o mercado de **referência** de todo β — parou em 14 (desde 2026-08-26 04:32Z),
  ao lado de ARB, DASH, NEAR e UNI. O restante nem começou.
  **Cenário, medido, não hipotético:** o produtor horário de β roda e escreve
  (1.800 revisões, 200 por corte, nove cortes de 04:00Z a 12:00Z), mas **199 de 200
  revisões por corte saem `valid = false` com `reason = insufficient_history`**. A
  única `valid = true` de cada corte é o **próprio BTCUSDT**, com `beta = 1.0000`,
  `n = 0` e `contiguous_bars = 0` — a referência contra si mesma, que é β = 1 por
  definição e não mede nada. Ou seja: **nenhum mercado tem β de verdade hoje**, o
  Risk Engine não pode validar correlação, e a ponte recusa por `beta_unavailable`.
  Um segundo efeito já visível: os replays históricos (T3.19b) cobriram **4
  mercados** (ETH, SOL, XRP, DOGE) em vez do universo, porque são os únicos com
  janela — ver [[EXP-0001-momentum-v1]] e [[EXP-0002-volume-anomaly-v1]].
  **Causa provável:** a fila de backfill é global e ordenada do mais novo para o
  mais antigo, então mercados que entraram na fila depois são servidos antes de o
  mais importante terminar; não há prioridade para o mercado de referência.
  **Sugestão (não implementada):** priorizar o `reference_market` do `beta_v1` na
  fila e só então distribuir o resto. Dono: `exchange-integration-specialist` +
  `quant-engineer` (T3.7b, seguimento). Sucede o bug "candles só 11 dias na VPS"
  do plantão da madrugada, que estava com o número errado e foi fechado — ver
  [[Resolved Bugs]].

- **MEDIUM (deploy, ferramental) — `compose.sh update` não sobe serviço novo de
  perfil (tenta *pull* antes do *build*), e o aviso do `migrate` é falso
  positivo.** No primeiro `MARKET_SPOT=1 MARKET_SHARDS=4 bash infra/vps/compose.sh update`
  com a T3.0f (`0451066`), o `market-worker-spot` **não subiu**: o compose tentou
  **puxar** `hunter-api:<sha>` para o serviço novo do perfil antes de a imagem ser
  construída ("pull access denied"), enquanto os demais serviços subiram.
  `bash infra/vps/compose.sh up market-worker-spot` em seguida resolveu.
  **Cenário:** um deploy que "termina bem" deixa um serviço novo de perfil parado
  sem que ninguém veja — e nesse caso o serviço parado era o coletor spot, isto é,
  o lado da **execução** da carteira paper. Segundo achado no mesmo comando: o
  aviso `ERRO: migrate nao subiu` para um contêiner de execução única que saiu com
  `exit 0` é **falso positivo** — `migrate` é job, não serviço; o script tem de
  checar o código de saída, não a presença do contêiner. **Correção proposta:**
  `build` antes do `up` quando há perfis (ou `up --build` com `--pull never` para
  imagens locais), e tratar `migrate` pelo exit code. Registrado no adendo de
  2026-09-08 do brief `.claude/state/brief-T3.15d-owner-dsn.md`. Dono:
  `devops-engineer` (T3.15d).

## Abertos no plantão da manhã de 2026-09-07 (M3 ondas 3–4: T3.5, T3.13, T3.14, `0008`/`0009`)

Nada aqui bloqueia o que está no `main`, e nada aqui pode custar dinheiro ao Everton: a carteira é
paper, a ponte está desligada e nenhum sinal do Lab é admissível hoje. Os quatro primeiros são
**condições para ligar a autonomia**, não defeitos do que roda.

### Condições para ligar `ENABLE_PAPER_AUTONOMY` (de `.claude/state/review-T3.14.md`, dono: T3.14b, depois da T3.5c)

- **MEDIUM (ruído que vira cegueira) — a ponte grita a mesma recusa ~240 vezes por sinal.**
  `bridge_screen.py:104-112` emite `bridge_candidate_refused` (log **e** contador) a cada passada
  para o mesmo sinal, durante os 240 s da janela de lookback. **Cenário:** com a autonomia ligada, um
  punhado de sinais recusados por um motivo banal enterra o log de operação e infla
  `hunter_bridge_candidates_total` a ponto de o desfecho deixar de significar "quantos sinais foram
  recusados" e passar a significar "quantas voltas o laço deu" — a métrica que existe para explicar
  a ponte passa a mentir sobre ela. **Correção:** deduplicar por (sinal, motivo), o mesmo padrão que
  `report_unreadable` já usa.

- **MEDIUM (teste ausente sobre caminho que decide dinheiro) — o vice não é promovido, e ninguém
  provou.** `bridge.py::_submit` escolhe um candidato e, quando o livro ainda não é elegível, ele
  **adia** em vez de ceder o lugar — comportamento correto e deliberado (evita trocar a decisão por
  quem chegou depois). **Falta o teste com 2+ candidatos** em que o topo é deferido por
  `spot_book_unavailable` e o vice **não** é promovido. Sem ele, uma refatoração futura inverte isso
  em silêncio.

- **MEDIUM (teste ausente) — o caminho `agent_unavailable` nunca foi exercitado.**
  `bridge_screen.py:130-140`: agente existente porém **não habilitado**. É uma das seis recusas
  nomeadas e a única sem teste.

- **HIGH se a autonomia for ligada antes disto (mapeamento de par) — `1000SHIBUSDT` perp →
  `SHIBUSDT` spot.** `bridge_universe.py:57-83 spot_pair_for` casa perpétuo e spot pelo
  `base_asset_id`, e nos mercados com multiplicador de 1.000 no nome o **preço do perpétuo é ~1000×
  o do spot**. Falta o teste do mapeamento **e** a prova de que um `entry_ref` mil vezes fora da
  banda é recusado pelo Risk Engine (`signal_validity` / `max_entry_deviation_pct`) **antes de
  qualquer reserva**. **Cenário:** sem essa prova escrita, uma mudança no cálculo do `entry_ref`
  passaria a dimensionar uma ordem com o preço errado por três ordens de grandeza, e a defesa está a
  uma linha de distância de ninguém a estar vigiando.

### Da revisão da T3.0b (`.claude/state/review-T3.0b.md`, dono: T3.0d, junto/depois da T3.0c)

- **HIGH (bloqueante para a T3.0c, `services/market-worker/.../durable.py:74-86`) — o `event_id` do
  candle não inclui `market_type`, e o segundo candle do minuto é descartado em silêncio.** O
  `candle_event_id` e a `key` do envelope são derivados sem o tipo; com a ingestão spot ligada, o
  candle spot e o perpétuo do **mesmo minuto** computam o mesmo uuid5 e o `ON CONFLICT (event_id)` do
  outbox **joga o segundo fora sem erro**. É um dado que some sem log. A T3.0c está mexendo
  exatamente nesse arquivo — é para fechar antes de a ingestão spot ser ligada, não depois.

- **MEDIUM — `market_ids.py:47`: o filtro por tipo não tem teste.** Duas linhas no banco (spot e
  perpétuo do mesmo símbolo) e a asserção de que cada uma volta na consulta certa. Foi um dos dois
  bugs latentes que a T3.0b fechou; sem teste, ele volta.

- **MEDIUM — o hash `mkt:*:ticker` **não** contém `market_type`, e isso é deliberado (KB-0044):
  falta o teste que registra a exceção.** Sem ele, alguém "conserta" a exceção achando que é
  esquecimento.

- **LOW — as docstrings de `binance_spot/identity.py:23-33,78` ficaram falsas.** Elas descrevem um
  segmento na chave do perpétuo que não existe; o gap foi fechado pela própria T3.0b. Documentação
  que descreve o contrário do código é pior que documentação nenhuma.

- *(O quinto item da revisão — o runbook de rollback exigindo `DEL mkt:*:candles:1m` — **já foi
  fechado** por `70f2e7b`, em `docs/DEPLOYMENT.md`. Fica registrado aqui para a revisão poder ser
  conferida item a item.)*

### Do ciclo de execução e do ferramental

- **MEDIUM (produto, `services/execution-worker`) — o pó tem lugar, e ainda não tem assentamento.**
  A decisão está tomada e implementada: o resíduo abaixo do mínimo negociável **não é posição** (não
  segura vaga, não conta exposição, não bloqueia uma segunda ordem na moeda) e **continua visível e
  valorizado** no patrimônio, marcado como pó (`positions.is_residual`, `0009`). O que **não
  existe** é a segunda metade da decisão: **vender o pó** quando o acumulado da moeda passar do
  `min_qty`/`min_notional`, junto da próxima saída ou numa varredura diária. **Cenário:** meses de
  operação paper acumulam dezenas de linhas `closing` que nunca somem; o patrimônio continua certo,
  mas a tabela de posições vira um cemitério e o Everton perde a leitura rápida de "o que está
  aberto". Dono: **T3.5c ou T3.10**. Registrar em `docs/PIPELINE.md` §8 e na tela da carteira
  (T3.8c: "pó").

- **LOW (duplicação com risco de divergência) — `SPOT_VOLUME_FLOOR_USDT = 50.000.000` está escrito
  duas vezes.** `services/execution-worker/.../bridge_universe.py:56` e
  `services/market-worker/.../spot_universe.py:69`. A duplicação é **declarada** no comentário (os
  dois serviços não compartilham módulo), mas é um número que define **quais mercados a carteira
  pode tocar**: mudar o piso num lado e não no outro faz a ponte escolher um mercado que o coletor
  não ingere, e a recusa que aparece é `spot_book_unavailable` — um sintoma que não aponta para a
  causa. **Correção:** mover a constante para `packages/core` (ou `hunter_risk`), com os dois
  serviços importando; ou, no mínimo, um teste que compare os dois valores.

- **LOW (ferramental de teste, Windows) — `WinError 64` intermitente no teardown.** Dois arquivos de
  testcontainers no mesmo processo derrubam o teardown com "The specified network name is no longer
  available" (item 10 de `.claude/state/review-T3.5.md`). **Por que importa:** é um vermelho que
  **não é do produto**, e um vermelho que não é do produto ensina a ignorar vermelho. Contorno atual:
  rodar os arquivos em processos separados. Dono: ferramental.

- **MEDIUM (pré-requisito não escrito da ponte) — `agents` é obrigatório, e a tabela está vazia.**
  A ponte exige uma linha em `agents` **habilitada** para a versão de estratégia, porque a proposta
  nasce com `source='agent'` e o schema cobra o agente. Hoje não existe nenhuma. **Cenário:** o
  Everton (ou eu) liga `ENABLE_PAPER_AUTONOMY`, e **nada acontece** — sem erro, sem alarme, apenas
  `agent_unavailable` no contador; a conclusão natural e errada é "a ponte está quebrada". A ordem
  correta de ativação, e ela precisa estar escrita num runbook antes de alguém tentar: (1) ativar
  uma `strategy_version` com propósito de paper — **decisão do Everton**; (2) criar a linha `agents`
  habilitada para ela, apontando a carteira; (3) só então a bandeira. Dono: **T3.10** (runbook de
  ativação) + a decisão do Everton.

## Abertos no plantão da madrugada de 2026-09-07 (M3 ondas 1–3 + incidente de deploy da VPS)

Os cinco primeiros vêm da revisão adversarial de `.claude/state/review-T3.1b-T3.6-T3.12.md`
(APPROVE_WITH_NITS) e eram **condições escritas para a T3.5/T3.8** — estão no addendum do brief
(`3519107`). **Três deles foram fechados na manhã de 2026-09-07** (admissão do lado da API,
`kill_switch.changed` e o escopo antigo nos docs), um está corrigido no código e **mantido em
observação** (dedupe), e um foi **reconfirmado aberto** (o teto do pico) — cada um com a nota datada
no próprio item. Os dois últimos são do incidente de deploy desta madrugada. Nada aqui bloqueia a
carteira paper que está aberta na VPS, porque nada nela executa ainda.

- **HIGH (admissão, `packages/core`) — a deduplicação casa um pedido que ninguém decidiu ainda, e
  explode.** `admission/dedupe.py:94-105` + `service.py:188-201`: `by_idempotency_key` também acha
  linhas com `status='pending'` e `risk_decision='{}'`, e `RiskDecision.model_validate({})` levanta
  **10 erros de validação**. **Cenário concreto no modelo de papéis que acabei de decidir (T3.1c):**
  a API registra a ordem manual como pedido não decidido, o `execution-worker` vai admitir, encontra
  a própria linha pelo dedupe e **nunca decide nada** — a ordem manual do Everton some em silêncio.
  **Correção:** `find_admitted` só considera linhas **decididas**, e o worker **decide a linha
  existente** em vez de inserir outra. Junto: `service.py:115` fabrica `decided_at`. Dono: **T3.5**.
  **Estado em 2026-09-07 (plantão da manhã): corrigido no código, mantido aberto em observação.**
  `admission/dedupe.py` hoje tem `find_admitted` casando **só linhas decididas**
  (`AND decided_at IS NOT NULL AND status <> 'pending'`) e um `find_pending` separado que trava a
  linha `FOR UPDATE` para ela ser decidida **no próprio lugar**. Não fecho ainda porque a **T3.5c
  está em voo nos mesmos arquivos** (`packages/core` e `services/execution-worker` aparecem
  modificados no worktree) e a verificação com as suítes de integração não foi refeita neste turno —
  fechar um HIGH de admissão por leitura de código, com a tarefa ainda mexendo nele, seria dar por
  provado o que não foi.

- **[FECHADA em 2026-09-07 por `7ecafd2` + `70acb6f` — verificada na leitura do código no plantão da
  manhã]** ~~HIGH (papéis, `apps/api`) — a admissão do lado da API roda inteira como `hunter_app`~~ —
  **a API virou o cartório e o motor virou o juiz.** `apps/api/hunter_api/services/admission.py`
  hoje só **arquiva um pedido pendente**: `source='manual'`, `status='pending'`, sem decisão, sem
  lugar na fila FIFO, sem reserva — e sem `request_digest`, que o motor recomputa. Quem decide é o
  `execution-worker` (`hunter_core.admission.decide_pending`), **na própria linha do pedido**. A
  `0009` deu ao pedido a geometria que faltava para isso ser possível (`request_payload`), e a
  trigger do banco agora **exige** esse payload. O erro 500 que os grants novos causariam deixou de
  ter caminho. *Texto original do achado, preservado:* `apps/api/hunter_api/services/admission.py:129-187`. O `hunter_app` não pode
  avançar o contador FIFO nem enfileirar outbox — a T3.12 já provou isso e contornou nos testes com
  um grant explícito rotulado como experimento condicionado. **Cenário:** assim que a T3.1c aplicar o
  modelo de papéis, a primeira ordem manual pela tela devolve erro 500. **Correção (decidida):** o
  adaptador da API **registra o pedido** (`source='manual'`, `status='requested'`, sem decisão, sem
  reserva) e o `execution-worker` admite. Dono: **T3.5/T3.8**.

- **HIGH (kill switch, `infra/migrations/ddl/paper.py`) — o teto do pico conta snapshot de qualquer
  resolução, e isso pode travar a carteira para sempre.** `_OBSERVED_EQUITY` (linhas 411-417) faz
  `max(s.equity) FROM portfolio_equity_snapshots` **sem filtrar `resolution`**, mas a curva
  operacional é só a de 1 min (`curve.py:36`). **Cenário:** no dia em que existir um roll-up de 1 h
  ou 1 d guardando o **máximo do período**, o teto sobe; o pico é monotônico e nunca desce; o
  drawdown medido contra esse pico inflado estoura o limite de 8 % e a carteira fica
  `TRADING_DISABLED` **permanentemente**, sem que nenhuma perda real tenha acontecido. **Correção:**
  `resolution = '1m'` no subselect. Dono: **T3.1c** (ou follow-up imediato se não couber).
  Confirmado ainda aberto em 2026-09-07 04:40Z. **Reconfirmado aberto em 2026-09-07, plantão da
  manhã:** nem a `0008_paper_roles_2` nem a `0009_paper_geometry` tocaram nisso —
  `infra/migrations/ddl/paper.py:411-416` continua sem filtro de `resolution`, e `docs/DATABASE.md`
  §20 e §21 não mencionam a correção. **Fica com dono novo: T3.0d/T3.1f**, porque a T3.1c e a T3.1e
  já passaram e não o levaram. Enquanto `portfolio_equity_snapshots` só tiver linhas de 1 min, o
  defeito é latente; ele acorda no dia em que existir o primeiro roll-up de 1 h ou 1 d — e, quando
  acordar, trava a carteira em `TRADING_DISABLED` **permanentemente**, sem perda nenhuma ter
  acontecido, e o pico não desce para desfazer.

- **[FECHADA em 2026-09-07 por `7ecafd2` — com uma metade menor reaberta logo abaixo]** ~~HIGH
  (contrato) — nenhuma transição publica `kill_switch.changed`~~ — **o worker publica.** O
  `execution-worker` relê a trava a cada 10 s e dentro de cada transação de efeito, e publica
  `kill_switch.changed` em `outbox_events`
  (`services/execution-worker/hunter_execution_worker/events.py:147-167`, com `event_id` derivado da
  carteira, do estado latchado e do instante — repetir não duplica). O que destravou isto foi
  exatamente a `0007`: o papel do motor ganhou `INSERT` em `outbox_events`. **Fica aberto o que
  sobrou:** a **retomada pela API** ainda não publica — `routers/risk.py:180` chama `resume()` sem
  `publish=True`, e `risk/transitions.py:146` mantém o padrão `False`. **Cenário:** o Everton
  destrava a carteira pela tela e a própria tela continua mostrando BLOQUEADO até o próximo poll,
  contra o < 1 s do contrato. É MEDIUM, não HIGH: o caso que travava a carteira sem ninguém saber
  está coberto. Dono: **T3.5c/T3.8**. *Texto original do achado, preservado:*
  O nome do evento existe (`events/streams.py:57`) e o tipo existe (`domain/enums.py:686`), mas
  `risk/transitions.py` só o cita num docstring: **todos** os chamadores passam `publish=False`.
  **Cenário:** o kill switch trava a carteira e a tela do Everton continua mostrando `ACTIVE` até o
  próximo poll — o contrato v2.2 exige reação em **menos de 1 s**. Estava bloqueado porque o
  `hunter_worker` não tinha `INSERT` em `outbox_events`; a T3.1c destrava. **Correção:** o worker
  publica depois de `evaluate_and_persist`; a API publica na retomada. Dono: **T3.5**.

- **[FECHADA em 2026-09-07 por `2ee79c1` — `grep` no plantão da manhã não acha mais nenhuma
  ocorrência em `docs/`]** ~~MEDIUM (documentação divergente do banco) — `docs/` ainda diz "uma
  carteira principal por workspace"~~ — o contrato v2.2.1 alinhou o escopo para **por organização**
  em **todas** as menções, junto com as assinaturas reais de `evaluate`/`evaluate_exit` e com
  `MarketRegime` marcado como reservado ao M4. Importava mais do que um typo: quem lesse o contrato
  normativo para implementar a T3.5 reimplantaria o furo que o revisor de segurança provou e a
  `0006` fechou no banco. *Texto original do achado, preservado:* `docs/RISK_ENGINE.md:593` e
  `docs/plans/M3.md:118`. **Por que importa mais do que um typo:** foi exatamente esse escopo que o
  `security-reviewer` provou ser um furo (workspace novo = segunda carteira com R$100.000 novos), a
  `T3.1b` fechou no banco, e a documentação normativa continua descrevendo o comportamento **antigo**
  — quem ler o contrato para implementar a T3.5 implementa o furo de volta. Dono: **T3.1c/docs**.

- **MEDIUM (infra, VPS — corrigido no código, ainda não aplicado na VPS) — o Caddy estava preso a um
  IP dentro da faixa dinâmica do Docker.** O Caddy é fixado em `172.28.0.10` porque a API depende
  desse endereço para limitar requisições por cliente (`FORWARDED_ALLOW_IPS`), mas a faixa dinâmica
  da rede cobria o mesmo endereço. **Aconteceu de verdade hoje:** ao recriar os contêineres com o
  perfil de shards, o Docker entregou o `.10` ao `scanner-worker`, o Caddy falhou com "Address
  already in use" e **o site ficou fora por volta de 20 minutos**. Corrigido em `7304709` (faixa
  dinâmica em `172.28.0.128/25`), mas **aplicar o `ip_range` exige recriar a rede no próximo
  deploy** — até lá a VPS continua com a rede antiga. Dono: devops.

- **MEDIUM (processo de deploy) — um `docker compose` na mão perde variáveis que só o `compose.sh`
  deriva.** No mesmo incidente, o deploy manual perdeu `GIT_SHA` (a migração rodou com a imagem
  `hunter-api:dev` velha e **não achou a revisão `0006`**) e `HUNTER_DEFAULT_SNI` (o Caddy serviu um
  certificado de `localhost` e **o HTTPS quebrou no IP** até o contêiner ser recriado com o SNI
  certo). O `7304709` fez o `compose.sh up/update` ler `MARKET_SHARDS` sozinho e falhar alto quando um
  serviço não sobe — mas **a correção é técnica e o hábito é humano**: o item fica aberto até o
  runbook estar escrito e o próximo deploy ter sido feito só com
  `MARKET_SHARDS=4 bash infra/vps/compose.sh update`. Dono: devops + orquestração.

- *(`AssumedCosts` aceita `float` — já registrado no plantão da noite de 2026-09-06, mais abaixo
  nesta mesma página; reconfirmado aberto em 2026-09-07.)*

## Abertos no fecho do M2 (2026-09-07, tarefa T2.8 — ver `docs/reports/M2.md`)

- **MEDIUM (processo, aconteceu de verdade hoje) — dois agentes commitando no mesmo worktree, e um
  leva os arquivos do outro.** Cenário concreto, observado: preparei com `git add` os onze arquivos
  do fecho do M2 (relatório, `EXP-0003`, diário, base, `milestone.json`, `ROADMAP.md`); entre esse
  `git add` e o meu `git commit`, um agente do M3 rodou o próprio `git commit`, que **varreu o índice
  inteiro** e levou os meus arquivos dentro de `6c60653`, cuja mensagem fala de outra coisa
  (`chore(state): brief T3.5`). Repeti três vezes (inclusive com `git add -N` + pathspec explícito no
  `commit`) e a corrida ganhou nas três. Quando percebi, `6c60653` **já estava empurrado** —
  reescrever histórico empurrado exige `--force`, que é decisão do Everton. **Consequência:** a
  história do repositório atribui a um brief do M3 o relatório e o parecer de um milestone inteiro;
  quem auditar por `git log` não acha. **Contorno usado:** nota de rastreabilidade no topo do
  relatório e este item. **Remédio real:** nenhum agente deve rodar `git add -A`/`git commit -a` num
  worktree compartilhado — commit sempre com pathspec explícito dos próprios arquivos — ou cada
  tarefa em voo ganha o próprio worktree (`isolation: worktree`). Dono: orquestração.

- **[FECHADA em 2026-09-07 04:36Z pelo deploy dos 4 shards na VPS — medição abaixo]** ~~HIGH
  (operacional, VPS)~~ — **a cobertura do tape voltou a andar.** Duas leituras somente-leitura desta
  madrugada, no Redis da VPS: às **04:33:16.150Z** `covered_until = 2026-09-07T04:33:15.264548Z`
  (**0,89 s** atrás do relógio) e às **04:36:58.058Z** `covered_until = 04:36:57.366387Z` (**0,69 s**),
  com `session_since = 04:33:05.426833Z` **inalterado entre as duas** — ou seja, uma sessão contínua,
  sem quebra, com 200 campos `sym:` e `HLEN = 202`. A causa era a topologia: um processo com 200
  mercados não dava conta, e é exatamente o que o T2.5g resolve. **Ressalva honesta, e ela importa
  para o M2:** a condição nº 1 de aprovação do M2 exige `covered_until` avançando por **≥ 30 min
  contínuos**, e na hora desta medição a sessão tinha **3 min 52 s**. O sintoma sumiu; o portão de
  30 minutos ainda não foi provado, e é a primeira coisa a medir no próximo plantão.
  *Texto original do achado, preservado:* Leitura de **2026-09-07T03:19:20Z**: `mkt:binance:coverage.covered_until =
  2026-09-07T02:34:57Z` — **44 minutos parado**. `hb:scanner:*` declara `coverage = unproven`;
  `hb:strategy:shadow` conta `{"unavailable": 63.793}` avaliações contra 11.479 `not_triggered` e
  460 `triggered`. **O custo, agora quantificado:** enquanto o carimbo não anda, `trade_velocity_1m`,
  `buy_pressure_5m` e `sell_pressure_5m` se recusam sozinhas, **nenhuma baseline de tape amadurece**
  (0 buckets utilizáveis em 393–398, ver [[EXP-0003-baselines-v1]]) e **nenhum EARLY pode ser
  publicado** — 0 estágios ≠ `NONE` em 299 amostras. É o bloqueio nº 1 do M2 e a razão nº 1 do
  parecer de não aprovação. **Próximo passo inalterado:** medir `queue_oldest_pending_ts` e o motivo
  de quebra **dentro do contêiner da VPS** antes de mudar qualquer linha.
- **[FECHADA em 2026-09-07 04:33Z — implantado]** ~~HIGH (implantação)~~ — **o T2.5g está na VPS.**
  Medido às **04:32–04:33Z**, somente leitura: quatro heartbeats por shard vivos —
  `hb:market:binance:0of4` (52 mercados, 312 assinaturas), `:1of4` (44/264), `:2of4` (45/270),
  `:3of4` (59/354) —, todos `ws_state = connected`, `reconnects = 0`, com o último evento a menos de
  1 s do relógio; **`EXISTS hb:market:binance` devolve `0`**, a chave compartilhada do desenho antigo
  não existe mais. CPU por shard no `docker stats`: **21,85 % · 28,84 % · 41,66 % · 42,50 %**.
  `dropped_events`: **97 no shard 0 e 0 nos outros três** — o 0 é o shard que também coleta o câmbio.
  Contra os **7.073.659** descartes do processo único de ontem, é outra ordem de grandeza.
  *Ressalva:* `open_gaps` somados dão **5.038** (1.329 + 1.092 + 1.097 + 1.520) — o backlog de
  recuperação continua alto e é o item MEDIUM separado ("gaps de mercados não monitorados nunca
  fecham"), não este. *Texto original do achado, preservado:* A chave
  compartilhada `hb:market:binance` (desenho antigo, o HIGH que decidiu a topologia entregue no M1)
  **ainda existe** no Redis da VPS, ao lado de um único `hb:market:<instance>`: a VPS roda **1 shard
  com 200 mercados**, exatamente a topologia em que o tick nasce com 3,7 s de atraso mediano. No
  local, os quatro shards com heartbeat por shard (`hb:market:binance:0of4` … `:3of4`) estão no ar
  e a cobertura anda (`covered_until` a 1 s do relógio). Dono: ops.
- **HIGH (produto, medido) — o score não pode passar de 25,00 de 100.** Com 3 componentes de 9
  disponíveis (pesos 0,20 `volume` + 0,05 `anomalies` + 0,00 `agent_consensus`) contra
  `watching_min = 40`, `hot_min = 75`, `entry_candidate_min = 80`, **nenhum mercado pode alcançar
  WATCHING por pontuação** — os que aparecem como `ANOMALY` chegaram pela rota da severidade
  (`anomaly_severity_min = 60`). Não é defeito de código (o motor recusa redistribuir peso, e
  derruba a `confidence` para 0,0714 em vez de fingir certeza): é falta de evidência, e some quando
  as baselines de tape/livro/derivativos amadurecerem. Registrado porque **é o que o Everton vê na
  tela**.
- **MEDIUM (integridade de pesquisa) — ninguém consome `market.candles.backfilled`.** `grep` no
  repositório encontra só produtores (`backfill_announce.py`, `recovery_drain.py`). Decisão
  consciente da T2.9c (`766f8b6` deixa escritos os quatro requisitos de quem o escrever), mas a
  consequência é real: o scanner **não sabe** quando um pedaço da história que ele pediu chegou —
  descobre no refresh horário seguinte. Dono: `services/scanner-worker`.
- **MEDIUM (cobertura de teste) — os três entregáveis de teste da T2.8 não existem.** O plano do M2
  pede integração ponta a ponta (candle → features → anomalia → score → radar) e os e2e
  `radar.spec.ts` e `opportunity.spec.ts`. `tests/e2e/` tem `markets`, `api-health`, `public` e
  `signup-onboarding`; `tests/integration/` só o pipeline de mercado do M1. Dono: `test-engineer`.
  É a condição nº 4 de aprovação do M2.

## Abertos no plantão da noite de 2026-09-06 (integração das ondas T2.5 / T2.9c / T3.2 / T3.7)

- **[FECHADA em 2026-09-07 04:36Z — mesma causa da entrada acima, mesma prova]** ~~HIGH
  (operacional, VPS)~~ — `mkt:binance:coverage` congelado depois do deploy de `fe8872c`. A hipótese
  que ficou escrita aqui ("ou o produtor saturado — ver o item seguinte") era a certa: com 4 shards a
  cobertura anda a menos de 1 s do relógio e a sessão não quebra. *Texto original do achado,
  preservado:* O commit `fe8872c` (T2.5e) foi entregue
  exatamente para descongelar a cobertura do tape e foi verificado no stack local (`t25e-proof.md`:
  o carimbo passou a avançar a cada ~250 ms). **Na VPS o sintoma reapareceu:** imagem confirmada em
  `fe8872c` (build `2026-09-06T23:34:58Z`, `oldest_pending_ts` presente no código do contêiner em
  execução), duas quebras `tape_coverage_interval_broken reason=reconnect backlog=0` às 23:35:17Z e
  23:35:19Z e **nenhum log de retomada depois disso**; `covered_until` lido quatro vezes entre
  23:40:55Z e 23:44:46Z devolveu sempre `2026-09-06T23:35:18.496199+00:00` — o mesmo valor de
  `session_since` e dos 200 campos `sym:*`, ou seja **um único carimbo, no início da sessão, e nada
  mais em 9 minutos**. No mesmo intervalo o heartbeat do scanner declara `coverage=unproven` e o do
  Lab foi de `{"unavailable":844}` (23:40:47Z) a `{"unavailable":2367}` (23:44:46Z) com
  `not_triggered` parado em 319. **Consequência:** enquanto o carimbo não anda, as features de tape
  (`trade_velocity_1m`, `buy_pressure_5m`, `sell_pressure_5m`) se recusam sozinhas e nenhum EARLY é
  publicado — é o mesmo prejuízo que a T2.5e fechou no local. **Não diagnosticado:** não sei ainda se
  é a mesma causa (a igualdade exata morreu no código), uma sessão que não se reabre depois da
  reconexão dupla do boot, ou o produtor saturado (ver o item seguinte). **Próximo passo:** medir
  `queue_oldest_pending_ts` e o motivo de quebra no contêiner da VPS antes de mudar qualquer linha.
- **[FECHADA em 2026-09-07 04:33Z pelo T2.5g na VPS]** ~~HIGH (capacidade)~~ — o coletor de um
  processo satura com 200 mercados. Fechado pela topologia de 4 shards: **nenhum shard passa de
  42,5 % de um core** e os descartes caíram de 7,07 milhões para 97 (shard 0) e 0 (os outros três).
  **O que NÃO está fechado por isto:** o p99 tick→oportunidade dentro de 3 s continua sendo a
  condição nº 3 de aprovação do M2 — a prova da T2.5g mediu **0,3 %** de cumprimento com 4 shards
  (média 7,74 s), porque `crc32(symbol) % N` equilibra **contagem** e não **tráfego**. Isso é um item
  de produto em aberto, não este bug de capacidade. *Texto original do achado, preservado:* Medido na prova da T2.5d, com a fila de `market.ticks` já em zero: entre o carimbo que
  o coletor põe no payload e o `XADD` da mensagem há **mediana de 3,70 s e máximo de 34 s** nas 200
  entradas mais novas; no fim daquela janela a entrada mais nova tinha **130–147 s** de idade porque
  o `market-worker`, a 99,7 % de **um** core, parou de publicar por mais de dois minutos. O orçamento
  de 3 s da decisão conjunta é contado **a partir desse carimbo**, então ele já está estourado antes
  de a mensagem existir no stream: **nenhum trabalho dentro do scanner pode fechar o p99 enquanto
  isto não cair.** Medições de hoje na VPS na mesma direção: `dropped_events` 969 619 → 1 101 345 em
  ~1 min e `open_gaps` 4 105 → 4 195 em ~4 min. Dono: **T2.5g** (latência de publicação e 200
  mercados em 4 shards com heartbeat agregado), brief já escrito em `7830c89`.
- **MEDIUM (contrato de tipos, `packages/core`) — `AssumedCosts` aceita `float`.**
  `packages/core/hunter_core/strategies/envelope.py:45` converte via `str`, então um `float` entra
  sem erro. Cenário: o envelope de custos é parte do **`code_ref`** de uma versão de estratégia — um
  custo que entra como `0.0004` binário em vez de `Decimal("0.0004")` pode mudar o digest congelado e,
  com ele, a identidade da versão, além de contaminar dinheiro com aritmética binária (a regra dura do
  projeto é `Decimal` em todo valor monetário). Achado pela revisão adversarial da T3.2 (item 10) e
  registrado pelo `risk-engine-guardian` como fora do escopo dele. **Dono: `packages/core`.**
- **MEDIUM (pesquisa/instrumento) — `funding_rates` não guarda instante de ingestão
  (`received_at`).** Sem ele, "esta linha chegou depois daquela avaliação" é **indemonstrável**. Foi
  exatamente o que aconteceu no R1 (`2c6bb2d`): 14 das 339 linhas comparáveis divergiram **só na
  liquidação**, e a explicação — chegada tardia da linha de funding das 20:00 — ficou registrada como
  **compatível, não comprovada**. Enquanto a coluna não existir, toda auditoria de reprodutibilidade
  que envolva funding termina em "não sei dizer". Dono: `database-architect` (migração aditiva) +
  quem escreve `funding_rates`.
- **MEDIUM (proveniência) — `open_interest_history.ts` é o bucket da rodada de poll, não o instante
  real da leitura.** `persist_rows.py` calcula **um** bucket de 5 min para a rodada inteira e depois
  faz REST sequencial por símbolo, então um mercado lido tarde na rodada é gravado com um `ts`
  anterior à leitura. A Astra construiu o contraexemplo que mata qualquer folga finita: rodada
  começa 12:04:59 (bucket 12:00), leitura às 12:05:02, gravada com `ts=12:00` — uma avaliação no
  corte 12:05:00, **três segundos antes da leitura real**, passaria por uma folga de 5 minutos.
  Consequência aceita na S2-context (`7cf9e18`): o OI durável **nunca** é usado como prova de
  `<= corte`, só o hot state (cujo `oi_ts` é o instante real), e uma linha durável sozinha vira
  sempre `timestamp_unprovable`. Ou seja: hoje o Lab decide **sem** open interest sempre que o hot
  state não tiver o valor. Correção de verdade = uma coluna com o instante da leitura em
  `open_interest_history`. Dono: `market-worker` + `database-architect`.
- **[NÃO REPRODUZIDO — preciso da evidência original] — "`test_universe` com eleição de líder
  instável".** Registrado aqui porque me foi relatado, mas **não consegui reproduzir**:
  `uv run pytest services/market-worker/tests/test_universe.py -q` rodou **4 vezes** nesta máquina
  (uma com `-p no:randomly`, três com a ordenação aleatória padrão) e deu **9 passed** em todas
  (31–36 s por execução). Sem cenário de falha, esta entrada não é um bug — é um pedido de
  evidência: quem viu a falha precisa colar a saída (semente do `pytest-randomly` inclusive) para
  que ela vire um bug com dono. Mantida na lista só para não se perder.

## Abertos pela quinta rodada de conhecimento (2026-09-06) — achado da Sexta-feira, confirmado pela Astra

- **[RESOLVIDA em 2026-09-06 por `fa9f957`, no ar na VPS desde o deploy da noite — ver [[Resolved Bugs]]] HIGH (qualidade de dado) — conflito de propriedade de campos entre o ticker REST e o `bookTicker`: `volume_24h` e `bid`/`ask` quase nunca coexistiam no mesmo hash quente.** Achado em [[KB-0044-o-que-morre-em-dez-segundos]] (rodada 5 de conhecimento), com o mecanismo confirmado por leitura de código depois do apontamento da Astra. O refresh de universo busca o ticker de 24h da Binance (`universe.py:107` → `GET /fapi/v1/ticker/24hr`, `binance/rest.py:270`), cujo parser nunca preenche `bid`/`ask` (`binance/normalize.py:212`, docstring explícito), e escreve no hash `mkt:{exchange}:{symbol}:ticker` (`universe.py:181`). O stream `bookTicker` produz `bid`/`ask`/quantidades e nunca volume (`binance/streams.py:168`) e o coalescer escreve **no mesmo hash** (`coalesce.py:158`). Antes da correção os dois escritores declaravam `owned=TICKER_FIELDS` — o conjunto **inteiro** de campos do ticker — e a regra do Lua de `hot_state.py` apaga com `HDEL`, no mesmo `MULTI` do `HSET`, todo campo de propriedade que vier ausente (H4, para não deixar valor velho ao lado de timestamp fresco). Com dois produtores complementares isso faz cada escrita apagar os campos do outro: um refresh REST aceito grava `volume_24h` e apaga `bid`/`ask`; o próximo `bookTicker` aceito grava `bid`/`ask` e apaga `volume_24h` de volta. **Evidência em produção:** de 55.709 linhas em `market_snapshots`, só **6** têm `volume_24h`/`quote_volume_24h` preenchidos — o `HGETALL` que alimenta o snapshot (`sampling.py::write_snapshots`) herda o hash como estiver no instante da leitura, então herdou a perda sem precisar de mudança própria. Refina a entrada LOW mais antiga desta mesma lista ("`volume_24h`... vêm `null` na API") — a causa **não é só o TTL de 30 s**, é a disputa de escritores; aumentar o TTL não resolveria nada.

  **Correção aplicada:** propriedade de campo por produtor em vez de um conjunto único. `hot_state.py` agora tem `TICKER_REST_FIELDS` (o que o ticker de 24h realmente manda: `last`, `volume_24h`, `quote_volume_24h`, `high_24h`, `low_24h`, `change_24h_pct`, `ts`) e `TICKER_WS_FIELDS` (o que o `bookTicker` realmente manda: `last`, `bid`, `ask`, `bid_qty`, `ask_qty`, `ts`), e `write_ticker`/`queue_ticker_hash` exigem um `source: Literal["rest", "ws"]` explícito que escolhe qual conjunto é usado para decidir o que fica "ausente, deve ser apagado" — nunca mais o outro produtor. `universe.py` chama com `source="rest"`; o coalescer (`coalesce.py`), com `source="ws"`. Nenhuma mudança em `sampling.py`: como os dois conjuntos de campos agora convivem no mesmo hash, o snapshot volta a ver `volume_24h` **e** `bid`/`ask`/`spread_pct` juntos sem precisar de alteração própria — confirmado por teste (`test_snapshot_carries_both_rest_volume_and_ws_spread_together`, `services/market-worker/tests/test_persist.py`). Testes de reprodução e regressão em `services/market-worker/tests/test_hot_state.py`: `test_shared_ownership_reproduces_the_kb_0044_bug` fixa o mecanismo exato (um `owned` compartilhado ainda apaga `volume_24h` na próxima escrita `bookTicker`) para que ninguém reintroduza um conjunto único por engano; `test_rest_ticker_and_ws_ticker_coexist_in_same_hash` e `test_rest_ticker_after_ws_ticker_does_not_delete_bid_ask` provam a convivência nos dois sentidos de chegada; os testes H4 (`test_write_ticker_rest_drops_stale_optional_field_under_fresh_ts`, `test_write_ticker_ws_drops_stale_optional_field_under_fresh_ts`) confirmam que a propriedade por produtor não perdeu a proteção original contra campo obsoleto — cada um só apaga o que é seu. `TradeMemory`/`push_trade` foram extraídos para `hot_state_trades.py` (mesmo padrão de `hot_state_candles.py`) para o `hot_state.py` caber no orçamento de 350 linhas depois da correção.

  228 testes de `services/market-worker` verdes, `ruff check`/`ruff format --check`/`pyright` limpos no escopo tocado, `check_file_size.py` sem novos itens acima do orçamento. **Aguardando commit** — dono: `exchange-integration-specialist`.

## Abertos pela subida do Shadow Lab na VPS (S4, 2026-09-06)

Prova completa em `.claude/state/vps-lab-proof.md`.

- **[RESOLVIDA em 2026-09-06 por `98c15bc` — ver [[Resolved Bugs]]] HIGH — o `code_ref` não é portável entre a máquina do Everton e a VPS.** Os digests do mesmo
  commit divergem: `momentum_v1` é `...@sha256:c012f75cdd8492d3...` no dev box e
  `...@sha256:6ccbe8b6c8ac18f3...` na VPS. Investigado até a causa, com os dois lados em `75fc59c` e
  `git status` limpo em `packages/core/hunter_core/strategies/`: `git hash-object` devolve o **mesmo**
  blob nos dois (`core.autocrlf=true` + `.gitattributes` normalizam na entrada), mas os **bytes em
  disco** diferem — `base.py` tem 14.095 bytes no Windows e 13.757 na VPS, e a diferença é
  exatamente 338, o número de linhas do arquivo: quatro módulos do fecho de imports (`base.py`,
  `aggregate.py`, `indicators.py`, `envelope.py`) estão em **CRLF** na árvore de trabalho do Windows
  e em LF na VPS (`tr -cd '\r' < base.py | wc -c` → 338). O `code_ref` é o digest desses bytes.
  **Cenário:** ativar uma versão a partir do dev box contra o banco de produção — ou restaurar um
  dump com versões congeladas no Windows e rodá-las na VPS — faz `load_active_versions` recusar
  **todas** com `shadow_version_code_ref_mismatch`. Graças à correção da S2 o `/ready` fica vermelho
  em vez de mentir, mas o Lab não roda, e campo congelado não se corrige no lugar: só `--supersede`,
  encerrando a coorte anterior. Não morde hoje porque cada ambiente ativou as suas próprias linhas.
  Confirmado independentemente pela Astra, que reproduziu a composição do digest em memória:
  converter só CRLF → LF nos arquivos locais devolve **exatamente** os hashes da VPS, que são iguais
  aos dos blobs do commit (`raw c012f75c… → lf 6ccbe8b6… = git_blob 6ccbe8b6…`). `git ls-files --eol`
  mostra os quatro arquivos como `i/lf, w/crlf` **apesar** de `eol=lf` no `.gitattributes` — a
  normalização vale para o que entra no repositório, não para o que já está na árvore de trabalho.
  **Correção certa:** normalização **mínima** de quebras de linha antes do digest, mantendo nomes,
  ordem e separadores; **não** AST nem bytecode (AST exige inventar uma canonicalização nova,
  bytecode não é estável entre versões do Python — os dois ampliariam o contrato em vez de consertar
  o incidente). Com teste que compare o digest do mesmo módulo em CRLF e em LF. **E a correção
  precisa vir com um plano para as versões já congeladas:** publicá-la muda os digests do lado
  Windows, e as coortes locais de [[EXP-0001-momentum-v1]] e [[EXP-0002-volume-anomaly-v1]] deixam de
  rodar sem `--supersede` auditado; os da VPS, já em LF, não mudam. Dono: quem tocar
  `hunter_strategy_worker/code_ref.py` a seguir.
- **[RESOLVIDA em 2026-09-06 por `2587b9f` — ver [[Resolved Bugs]]] HIGH (deploy) — o `seed` não é idempotente depois da primeira ativação, e não pode entrar no
  fluxo de deploy como está.** Dois problemas encadeados. (a) `compose.sh update` roda `migrate` e
  nunca `seed`: medido antes de ativar o Lab, a VPS tinha 526 mercados e **367.256 velas** coletados
  e **zero** linhas em `strategies`, `strategy_versions` e `feature_definitions` — coletava mercado
  havia horas sem uma única estratégia cadastrada. Só apareceu porque o script de ativação recusou
  com a mensagem certa. (b) A correção óbvia — pôr o `seed` no `update` — **quebraria o próximo
  deploy**, achado da revisão da Astra e reproduzido por mim na própria VPS depois da ativação:

  ```
  $ bash infra/vps/compose.sh run --rm -e HUNTER_COMMAND=seed --entrypoint /app/infra/docker/entrypoint.sh migrate
  sqlalchemy.exc.DBAPIError: asyncpg.exceptions.RaiseError:
    strategy_versions 01a074c5-8f1d-7a75-a88b-2badb6a5dd67 is frozen after activation: code_ref cannot change
  [SQL: INSERT INTO strategy_versions (...) ON CONFLICT (strategy_id, version)
        DO UPDATE SET code_ref = excluded.code_ref ...]
  [parameters: (..., 'v1', 'draft', 'hunter_indicators.strategies.momentum_v1', ...)]
  ```

  `seed.py` sobrescreve `code_ref` com um placeholder; a trigger de congelamento recusa em qualquer
  linha já ativada; e o seed roda numa transação só, então **as oito tabelas revertem juntas**. O
  rollback funcionou (8 estratégias, 8 versões, 28 features, versões ativas intactas), mas um deploy
  que falha inteiro por causa disso é pior que o buraco original. **Correção:** o seed tem de
  **preservar** o `code_ref` de versões já ativadas, com teste `seed → ativação → seed`, **antes** de
  entrar em qualquer fluxo automático. Dono: `devops-engineer` + `database-architect`.
- **MEDIUM (sob investigação) — 18 outcomes na VPS podem ter `funding_missing` falso.** 19 de 70
  acompanhamentos encerrados têm `R_net = NULL` (18 `funding_missing:2026-09-06T04:00:00+00:00`, 1
  `funding_ambiguous_exit`), todos preservando `meta.r_ex_funding` — o comportamento conservador
  está certo. Mas a Astra apontou que `hunter_strategy_worker/funding.py` trunca o intervalo para
  segundos, projeta uma grade de liquidações e exige **correspondência exata de timestamp**, e o
  histórico desta VPS tem `max(funding_time) = 2026-09-06 04:00:00.005+00`. **Cenário:** a liquidação
  real existe cinco milissegundos depois da grade, a busca exata falha, e o outcome é rotulado como
  funding ausente quando o dado está lá. Não cruzei outcome a outcome, então não está provado — mas
  **não dá para classificar esses 18 como ausência legítima de dado**. Correção: identidade de
  liquidação que preserve o timestamp original em vez de exigir igualdade com uma grade calculada.
  Toda avaliação datada sobre a VPS conta os 19 fora dos "encerrados avaliáveis" de qualquer forma.

  **Investigação fechada em 2026-09-06 (turno da tarde) — censo completo em
  [[EXP-0001-momentum-v1]], seção "Hipóteses de falha".** Sobre os 73 outcomes com
  `funding_missing:*` da coorte da VPS (`as_of = 13:00Z`), com evidência graduada: **69** têm linha
  em `funding_rates` do **mesmo mercado** a menos de 2 s do instante pedido mas não no instante
  exato; **3** têm casamento exato na leitura de hoje e causa histórica por demonstrar; **1** não tem
  candidato em ±60 s (o vizinho está a 2 h). Deltas observados: +5 ms (22), −5 ms (18), +1 ms (25),
  +995 ms (1), +1001 ms (3), 0 ms (3). `funding_rates` tem 1883 linhas em 221 mercados e **851 delas
  têm parte de segundos diferente de zero** — a grade real da corretora não é redonda. Por
  liquidação em vez de por outcome: **66 liquidações distintas, 57 mercados, 7 instantes.** A
  hipótese está confirmada como mecanismo dominante; ela deixa de ser "sob investigação" e vira o
  item MEDIUM abaixo, com a proibição explícita da correção ingênua.

## Abertos no plantão da tarde de 2026-09-06 (coorte da VPS)

- **HIGH (operacional, VPS) — o backup do Postgres da VPS nunca rodou; não existe um único dump.**
  `/opt/backups` contém apenas `backup.log`, com uma linha: `/bin/bash: line 1:
  /opt/project-hunter/infra/vps/backup_postgres.sh: Permission denied`. Causa: o arquivo é rastreado
  no git como `100644` (`git ls-files -s infra/vps/backup_postgres.sh`) e a linha instalada pelo
  bootstrap em `/etc/cron.d/hunter-backup` invoca o caminho **diretamente**
  (`infra/scripts/bootstrap_vps.sh:346`), em vez de `bash <caminho>` — que é como o próprio
  cabeçalho do script manda rodá-lo e como todo o resto do repositório invoca esses scripts
  (`compose.sh`, `astra.sh`). Sem bit de execução, o cron falha todo dia às 03:17 e escreve a mesma
  linha no log. **Cenário:** perder o volume do Postgres da VPS apaga a pesquisa inteira do Shadow
  Lab, e ela é **irrecuperável por construção** — `signal_outcomes` avança no lugar, não há
  histórico de estados, e nenhuma avaliação datada passada pode ser reconstruída a partir dos
  sinais. É o único dado do projeto que não se refaz coletando de novo. **Fix (uma linha, duas
  opções):** trocar a linha do cron para `bash <script>` no bootstrap, **ou** marcar o arquivo
  executável no índice (`git update-index --chmod=+x`) e refazer o deploy. **Bloqueado neste turno:**
  tentei as duas coisas na VPS e o gate de permissão da sessão recusou (escrita em `/etc/cron.d` via
  `sudo` e execução do script). Precisa do Everton ou de uma tarefa `devops-engineer` com permissão.
  Dono: `devops-engineer`.
- **MEDIUM (pesquisa/instrumento) — o funding é casado por igualdade exata de timestamp contra uma
  grade calculada, e a corretora não usa grade redonda.** Detalhe e censo acima. **O efeito medido é
  pequeno e isso importa para a prioridade:** entre os outcomes que têm `R_net`, **nenhum** dos 173
  de momentum atravessou uma liquidação e só **9** dos 394 de volume atravessaram, com efeito médio
  de −0,000195 R e extremos −0,027742 / +0,000036. Não é a causa de uma expectancy de −0,2 R; é
  cobertura de pesquisa perdida em silêncio (50 outcomes fora do `R_net` na coorte avaliável).
  **A correção ingênua é proibida** (revisão da Astra em [[S4-hipoteses]], must-fix 5): dar
  tolerância de ±2 s ao `known.get()` permite **cobrar a mesma liquidação duas vezes**, porque
  `strategy-worker/funding.py:126` faz a união da grade calculada com o observado (a grade tem
  `08:00:00` e o observado tem `08:00:00.005`); e uma janela larga passa a cobrar funding
  **posterior** à saída, enquanto o recorte atual termina em `exit_ts` (`settle.py:60`). O protocolo
  correto precisa validar a cadência vigente, exigir associação **única** sem reutilizar liquidação,
  preservar o timestamp original separando identidade de incidência, recusar ambiguidades nas
  fronteiras e usar tolerância muito menor que metade do espaçamento mínimo validado. Dono:
  `quant-engineer` + `exchange-integration-specialist`.
- **LOW (observabilidade) — a hipótese de chegada tardia do funding não é demonstrável com o schema
  de hoje.** Três outcomes têm casamento exato de timestamp e ainda assim foram rotulados
  `funding_missing`, o que só se explica se a linha ficou visível depois da avaliação. Mas
  `FundingRate` não registra horário de ingestão e `SignalOutcome.updated_at` não registra o
  snapshot da consulta de funding, então não há como datar a visibilidade. Enquanto isso não
  existir, "corrida de leitura" fica como hipótese plausível e **não** como diagnóstico.
- **MEDIUM (teste intermitente) — `packages/exchange-adapters/tests/unit/test_ws_client.py::test_quiet_socket_rotates_cleanly_at_the_rotation_deadline`.**
  Apontado pela T2.9 (`.claude/state/notes-T2.9.md`): em execução isolada passou, passou, falhou
  (`assert 3 == 2` no número de conexões). O teste crava a **contagem exata** de reconexões com
  `max_connection_age_s=0.02` — um prazo real de 20 ms numa máquina carregada rende uma rotação a
  mais. `ws_client.py` e `test_ws_client.py` **não** são tocados pelo diff da T2.9, então não é
  regressão dela. **Cenário:** um teste que falha por carga da máquina treina a equipe a reexecutar
  a suíte até passar, e é assim que uma falha real vira ruído aceito. **Fix:** asserção `>= 2`, ou
  prazo vindo de um relógio injetado em vez do relógio real. Dono:
  `exchange-integration-specialist`.
- **Observação (capacidade, não bug) — `dropped_events = 7.073.659` no `hb:market:binance` da VPS**
  em ~14 h, com o `market-worker` a 98,97% de um core (de 12 na máquina, carga 1,32). Por contrato o
  `BoundedEventQueue` **nunca** descarta kline final (`binance/event_queue.py`), e a evidência bate:
  `ingestion_gaps` com 1590 `recovered`, 2 `open`, 2 `failed`, e a última vela de 1 min às 13:27Z. O
  que se perde é evento parcial (hot state), não série durável. Fica registrado em
  [[Market Collector]] como consumo de margem: a folga que hoje absorve 200 mercados é a mesma que o
  scanner do M2 vai querer.

## Abertos pela primeira avaliação do Shadow Lab (S4, 2026-09-06)

- **HIGH (operacional, local) — o `market-worker` do stack local está `unhealthy` e o Lab parou de
  avaliar.** `docker compose ps` às 02:57 UTC: `market-worker  Up 9 minutes (unhealthy)`; o hash de
  heartbeat `hb:market:binance` estava **vazio** (expirado); a última vela persistida era
  `2026-09-06 02:50:00+00` com `now() = 02:57:32`; `ingestion_gaps` acumulou **773 linhas `open`**
  com `gap_start` a partir de 02:04. Consequência medida no Lab: o heartbeat
  `hb:strategy:shadow` às 02:56:38 devolveu `evaluations_by_state = {"unavailable":400,
  "ineligible":1}` sobre `evaluated_bars = 401` — **100% das avaliações recusadas**, porque a
  agregação exige a janela contígua inteira e um minuto perdido custa até ~24 h de avaliações
  naquele mercado. **Não é defeito do Lab**: é a recusa correta de agregar sobre buraco. Causa
  provável: contenção da máquina com a T2.9 em prova mais o Postgres. **Registrado e não
  consertado por instrução** — os arquivos do `market-worker` estão em voo na T2.9. Dono: quem
  fechar a T2.9. Ver [[EXP-0001-momentum-v1]], [[EXP-0002-volume-anomaly-v1]] e [[Market Collector]].
  **Estado em 2026-09-06 13:23Z:** não observável — o Docker Desktop desta máquina está fora
  (`open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified`), então não há
  stack local nenhum de pé. O bug continua **aberto** e não verificado; a coleta e o Lab que
  importam agora estão na VPS, onde `open_gaps = 0` e a última vela é das 13:27Z. Reabrir a
  verificação quando o Everton subir o Docker de novo.
- **HIGH (latente, todo o projeto) — o default de `hunter_core.events.consume()` mata qualquer
  consumidor num stream ocioso.** `consume()` bloqueia o `XREADGROUP` por 5000 ms e
  `hunter_core/redis.py` define `socket_timeout = 5.0`: os dois vencem no mesmo instante e o
  processo morre com `redis.exceptions.TimeoutError` **sempre que o mercado fica quieto**. Medido
  na primeira tentativa da prova da S2 (23:18–23:21 UTC de 2026-09-05,
  `hunter_core/events/consume.py:85`). O `strategy-worker` foi blindado no seu próprio consumidor
  (`CONSUME_BLOCK_MS = 2000` + backoff, com regressão em `tests/test_consumer_supervision.py`),
  **mas o default continua perigoso para todo consumidor futuro** — e a T2.9 está editando
  exatamente `packages/core/hunter_core/events/consume.py` agora. Cenário: o próximo worker que
  usar o default morre em silêncio no primeiro fim de semana quieto. Dono: T2.9 / M2.
- **MEDIUM (observabilidade de pesquisa) — a quebra de `unavailable` por motivo não é persistida em
  lugar nenhum.** O heartbeat `hb:strategy:shadow` agrega só por *estado*
  (`{"unavailable":400,"ineligible":1}`); o motivo (`gap`, `warmup`, `stale`, universo mudado) só
  aparece numa sonda ad-hoc dentro do container. Cenário: uma avaliação datada não consegue dizer
  **por que** perdeu 400 barras sem alguém entrar no container na hora — e depois que a janela
  passa, a informação não existe mais. É requisito de cobertura da S3
  (`.claude/state/notes-S2.md` §14 já pede separar `late:delay`, `late:missed_open`,
  `late:unconfirmed`, `geometry`, `gap:*` e `blocked:*`); esta linha acrescenta que o mesmo vale
  para o lado das avaliações recusadas. Dono: S3.
- **LOW (retenção × pesquisa) — a retenção não conhece o `tracking_hold`.** `tracking_hold` mantém
  a *coleta* de um mercado segurado, mas a poda de 90 dias de `candles_1m`
  (`infra/scripts/prune_partitions.py`) apaga por partição sem olhar `shadow_episodes`. Com
  horizontes de 2–4 h isso não morde hoje; um replay antigo ou uma versão de horizonte longo
  morderia, e o efeito seria censura silenciosa de acompanhamentos. Dono: schema/retention.

## Abertos pela prova operacional da T1.6b (2026-09-05, sharding)

- **HIGH (operacional, encontrado no fecho do M1) — o override do Compose não é aplicado quando o
  `docker compose` é chamado só com o arquivo base, e o worker volta silenciosamente para 200
  mercados.** `infra/docker/docker-compose.override.yml` é carregado automaticamente apenas na
  descoberta padrão de arquivos; com `-f infra/docker/docker-compose.yml` (que é como o
  `CLAUDE.md` documenta o comando) ele **não** entra, e `MARKET_UNIVERSE_SIZE` cai no padrão do
  código, que é 200. Medido na noite de 2026-09-05, minutos depois da aprovação do M1: o container
  foi recriado por outro fluxo, `docker inspect` não mostrava nenhuma das duas variáveis, e a sonda
  devolveu `markets_monitored: 200`, `markets_degraded: 200`, `markets_ok: 0`, hot state completo em
  **7,0%** — exatamente o colapso que a prova da T1.6b mediu para um processo com 200 mercados.
  Cenário: qualquer `docker compose -f infra/docker/docker-compose.yml up -d` devolve a máquina à
  configuração que não se sustenta, sem aviso, e a tela do Everton volta a ficar toda `degraded`.
  **Correção certa:** mover o padrão honesto (`MARKET_UNIVERSE_SIZE: "50"`) para o próprio
  `docker-compose.yml`, em vez de depender do override; o override passa a servir só para
  *aumentar* o universo. Não foi feito agora porque `infra/docker/docker-compose.yml` está sendo
  editado pela tarefa S2 neste momento. Container restaurado à mão em 23:39 UTC com os dois
  arquivos explícitos. **Dono: primeiro item do M2, junto do heartbeat por shard.**
Todos medidos. Prova em `.claude/state/t16b-proof.md`. A HIGH-1 da T1.6 abaixo está
**resolvida** por esta prova: com 4 shards × 50 mercados, `markets_ok` = 198/200 (99,0%),
0 stale, 0 unavailable, 200/200 velas finais por minuto e CPU média por shard entre 36,6% e
64,2% de um core. Ver [[Resolved Bugs]] e [[Market Collector]].

- **HIGH — os shards compartilham a mesma chave de heartbeat.** Todos escrevem
  `hb:market:{exchange}`. Medido na corrida de 2 shards: `/system/market-status` devolveu
  `subscriptions: 636` (assinaturas de **um** shard) com `markets_monitored: 200`. Cenário: um
  shard morre, o outro continua reescrevendo a chave, e o painel do operador segue verde — a
  métrica que existe para detectar worker morto fica cega exatamente na topologia que a T1.6b
  introduziu. **Dono: M2.** Correção: chave por shard (`hb:market:{exchange}:{shard}`) e
  agregação na API, com o total de shards esperado vindo da configuração.
- **MEDIUM — gaps de mercados não monitorados nunca fecham.** `run_recovery` itera
  `universe.symbols`; um mercado que sai do top-N com gap aberto fica `open` para sempre e
  continua contado em `open_gaps`. Medido: no fim da prova restaram **95 gaps abertos, e os 95
  são de mercados não monitorados**. Efeito: o número que o operador acompanha nunca chega a
  zero. **Dono: M2.** (A decisão SHADOW já exige o oposto para o Lab: `tracking_hold` mantém a
  coleta de um mercado excluído enquanto houver acompanhamento aberto.)
- **MEDIUM — a morte de um shard não é rebalanceada.** A fatia `crc32(symbol) % N == i` simplesmente
  deixa de ser coletada até o processo voltar; nada redistribui. `restart: unless-stopped` cobre o
  caso normal, mas não há prova de um shard morto com os outros vivos. **Dono: M2.**
- **MEDIUM — `tests/integration/test_market_invariants.py::test_a_fresh_open_interest_write_never_rejuvenates_a_stale_mark`
  tem orçamento de 2 s de relógio.** Falhou com `assert 2323 < 2000` com a máquina rodando quatro
  shards a ~100% de CPU. Não é defeito de produto; é um teste que assume folga de CPU e vai piscar
  na CI. **Dono: M2.**
- **MEDIUM — `markets_ok` mistura capacidade com backlog de recovery.** Um `ingestion_gap` aberto
  força `degraded` qualquer que seja o frescor do hot state, então a métrica do plano ficou em 0
  durante horas enquanto 122 mercados tinham book fresco. É honesta (há buraco na série), mas não
  serve sozinha como meta de capacidade — por isso a prova mede também "mercados com os três
  componentes `ok`". **Dono: M2** (separar os dois eixos na API e na tela).
- **LOW (follow-up de performance, com número) — `model_construct` do pydantic é o maior custo de
  aplicação restante.** py-spy no shard de 100 mercados (11.110 amostras): `model_construct` 15,0%
  cumulativo, com `resolve_default_value` 2,49% e `inspect._signature_from_callable` 2,75%
  pendurados — ele percorre `model_fields` e resolve defaults **a cada evento**. Trocar os tipos
  normalizados do caminho quente por `dataclass(slots=True)` é o próximo ganho. **Dono: M2.**

## Abertos pela prova operacional da T1.6 (2026-09-05)

Todos medidos, não suspeitados. Prova em `.claude/state/t16-proof.md`.

- **[RESOLVIDA em 2026-09-05 pela prova da T1.6b — ver acima] HIGH-1 — o worker satura um core e o hot state de alta frequência não se sustenta com 200 mercados.** Medido: `docker stats` 100 % de CPU no `market-worker` enquanto o Redis fica em 0,9 % e 103 ops/s e o Postgres em 25 %; `ss -tn` com 769 KB parados no buffer de recepção do socket da Binance; `mkt:*:ticker` e `mkt:*:book` chegando a **zero chave viva** de 200; **1,15 milhão** de eventos descartados. Consequência para o produto: a tela mostra `markets_ok = 0`, tudo `degraded`, sem preço ao vivo. A série durável **não** é afetada (o `BoundedEventQueue` nunca descarta kline final, por contrato — 200/200 mercados por minuto, valores idênticos ao REST). **Dono: M2** (perfilagem primeiro; candidatos são o `LRANGE` de 50 itens com desserialização msgpack a cada trade em `push_trade`, a ausência de pipeline nas escritas de hot state, e a falta de prioridade entre ingestão ao vivo e backfill). **Mitigação disponível hoje, decisão do dono:** reduzir `MARKET_UNIVERSE_SIZE` de 200 para 20–50.
- **MEDIUM — o backlog de recovery não tem prazo nem freio.** Ao fim da corrida havia 4.729 gaps abertos e 2.324 recuperados, com teto de `MAX_GAPS_PER_CYCLE = 50` por ciclo de 60 s e cada busca REST em série. Quanto maior o backlog, mais REST, mais CPU, menos hot state, mais buracos — laço de realimentação sem amortecimento. Ressalva: esse backlog foi inflado por ~10 apagões que eu mesma provoquei em 1h50, não é o de uma operação normal. Falta definir um prazo de convergência aceito e medir contra ele.
- **MEDIUM — a prontidão regride de 503 para 200 sem nenhum dado ter chegado.** `ReadinessState.observe_adapter` zera `connect_timed_out` a cada observação e o rededuz do relógio da tentativa de conexão; quando o adaptador desiste de uma tentativa e abre outra, o relógio reinicia e a prontidão volta ao ramo tolerado. Medido no corte de rede: 503 em T+30s, **200 em T+45s**, com a Binance inalcançável. A tolerância de 120 s acumulados é contrato fechado na decisão conjunta, então responder 200 durante ela não é bug — a **regressão** é, e existe um teste (`test_readiness_grace_is_monotonic_and_not_reset_by_flapping`) cuja intenção ela contraria. Recomendação da Astra, absorvida: exigir *progresso recente* nas conexões, não apenas uma tentativa em curso. **Dono: M2** (mexe em contrato acordado).
- **MEDIUM — apagão de Redis agora vira crash-loop, e o cooldown de rate limit não sobrevive ao restart.** Depois da correção da HIGH-4 o worker morre alto em vez de congelar, o que é o comportamento desejado; mas foram **8 reinícios em 81 s** de apagão. O `IpRateGate` é local ao processo (limitação já registrada do M1), então cada reinício perde o `Retry-After` da Binance, o que pode escalar um `429` para `418` (ban de IP). **Fix já previsto no plano:** persistir `blocked_until` em Redis — com a ironia de que é justamente o Redis que está fora. Alternativa: teto de reinícios ou backoff no supervisor.
- **MEDIUM — nada age quando o worker fica vivo-e-parado.** `restart: unless-stopped` só cobre morte de processo, e o Docker Compose puro **não** reinicia por healthcheck. O healthcheck detectou o zumbi corretamente durante 19 minutos e ninguém escutou. **Dono: T1.7/ops** — `autoheal` no Compose, ou um watchdog interno que mate o processo depois de N minutos de `/ready` reprovado.
- **LOW — `/api/v1/system/workers` mostra dois "workers" para um processo só.** O heartbeat genérico do runtime (chaveado por hostname) e o heartbeat de mercado (chaveado por exchange) aparecem como duas linhas de `role=market`. Não é dado falso, mas induz o operador a contar errado.
- **LOW — `dropped_events` está no Redis mas não na API.** O campo entrou no hash `hb:market:{exchange}` e em métrica; `scan_heartbeats` continua com uma allowlist de campos, então não quebra, mas o número não chega a `WorkerHeartbeatOut` nem à tela. Falta uma mudança aditiva em `apps/api/hunter_api/services/system_status.py` e no schema.
- **LOW — `volume_24h`, `quote_volume_24h` e `price_change_24h_pct` vêm `null` na API.** O refresh de universo grava `quote_volume_24h` no hash do ticker, mas o hash tem TTL de 30 s e é reescrito pela ingestão sem esses campos, então some entre refreshes (15 min). **Causa raiz mais precisa achada em 2026-09-06:** não é (só) o TTL — é a disputa de propriedade de campos entre o refresh REST e o `bookTicker` no mesmo hash. **RESOLVIDA em `fa9f957`** (propriedade por produtor), no ar na VPS desde o deploy da noite de 2026-09-06. Ver a entrada no topo desta lista, [[Resolved Bugs]] e [[KB-0044-o-que-morre-em-dez-segundos]].

## Rastreados desde o fechamento do M0

- **`packages/core/tests/unit/test_logging.py` — erros de pyright strict.** Ficou pendente depois da onda 5; `.claude/state/milestone.json` registra que passou a ser tratado como KNOWN ISSUE em vez de item de resume-checklist. Não corrigido até 2026-09-05.
- **Isenções em `forbidden_patterns.sh`** (o gate de CI que falha em `sqlite`, `localhost` fora de dev/teste, escrita de JSON de estado, `print(` em produção) — mesma origem, ainda não revisado.
- **Isenção de nome de arquivo "bare" em `enums.py`** — mesma origem, ainda não revisado.

## Limitação de segurança aceita conscientemente (M0), a resolver no M1

- **JWT sem claim `azp` é aceito sem verificação de origem** (`auth/clerk.py`, `JwtAuthProvider.verify`). A allowlist de origem só compara quando o token traz `azp`; um token sem esse claim passa sem checagem. No M0 há um único cliente (`apps/web`), então a exposição prática é baixa, mas a decisão foi registrada como aceita apenas para o M0 — `docs/SECURITY.md` §1 marca isso explicitamente "rastreado para o M1", quando `azp` passa a ser obrigatório.

## Contradição encontrada durante a escrita desta base

`.claude/state/milestone.json` (wave 6, T13) afirma que `docs/reports/M0.md` foi escrito e que "Everton approves the close" com base nele — mas **o arquivo `docs/reports/M0.md` não existe no repositório**. O relatório de fechamento do M0 (formato §77) parece não ter sido persistido, apesar de o estado do milestone dizer que foi. Vale confirmar com quem fechou o M0 se o relatório existe em outro lugar ou se precisa ser reescrito.

## Adiados na revisão de T1.5b (2026-09-05) — nenhum bloqueia o commit

Achados reais, com cenário, que ficaram fora do escopo de polimento de UI e foram empurrados para o **M2**. Origem: `.claude/state/review-T1.5b.md` (duas rodadas: `code-reviewer`, `security-reviewer`, Astra/GPT-6 e QA visual).

- **Testes de hidratação de verdade não existem.** `tests/appearance-form.test.tsx` e `tests/motion-showcase.test.tsx` só afirmam o estado **depois** dos efeitos, então **passariam com o bug antigo** (Astra verificou linha a linha). Os mismatches H1/M1/S2 foram corrigidos no código e `tests/use-density.test.tsx` registra o primeiro render — mas cobrir a família toda exige um harness de SSR + hidratação no Vitest. **Dono:** infraestrutura de teste, M2.
- **jsdom não faz layout, então "visível" nunca é medido.** `use-arrow-key-row-selection` e `use-virtualized-rows` provam a aritmética, não a visibilidade física da linha. Fica para o E2E de Playwright do M2.
- **Sem tier de rate limit próprio para o servidor web na API.** Toda a renderização SSR compartilha o balde de 120/min por IP; o lado cliente foi contido (mínimo de 2 caracteres, debounce de 250 ms, `q` limitado a 64), o lado servidor não. **Dono:** `apps/api`, M2. Origem: `security-reviewer`.
- **Tooltip por componente no badge de qualidade** ("qual componente está atrasado") e **explicação do ponto de status acessível por toque no mobile** — as duas precisam de uma superfície de tooltip acessível por toque que a UI ainda não tem. M2.
- **Frescor vs conexão no Live Status:** a tela pode dizer `CONNECTED` com eventos velhos. Depende de um campo de idade por exchange que a API ainda não expõe. M2.
- **Reestruturar o modelo de scroll do `thead` fixo / adotar biblioteca de virtualização.** O sintoma concreto (H4) era aritmética e foi corrigido; a reestruturação é mudança de arquitetura. M2.
- **Layout dos trades a 1024 px com a sidebar aberta** — suspeita da Astra por inferência, sem medição em navegador. Sem cenário provado, sem correção. M2, junto do E2E.
- **QA interativo do command palette nunca rodou.** Dois dev servers concorrentes sobre o mesmo `apps/web/.next` deixaram a página da 3000 sem carregar JavaScript nenhum (`/_next/static/chunks/main-app.js` → 404); encerrar processos era bloqueado pela política daquela sessão. O comportamento está provado por Vitest e por screenshots estáticos, **não** por interação real. Vale repetir num ambiente limpo.

### Aprendizado de processo registrado

`pnpm lint` + `typecheck` + Vitest **não substituem o build de produção**. A T1.5b passou nos três com o `next build` quebrado (`Only async functions are allowed to be exported in a "use server" file`), porque o Vitest não aplica as restrições do Next App Router. **`docker compose -f infra/docker/docker-compose.yml build web` é obrigatório no aceite de qualquer tarefa de `apps/web`.**

## Relacionadas

[[Resolved Bugs]] · [[System Overview]]

## Fontes

`.claude/state/milestone.json`, `docs/SECURITY.md` §1

## Abertos em 2026-09-05
- ~~Banco local com coluna antiga em `processed_events`~~ — corrigido em 2026-09-05 (rename `processed_at → claimed_at`, `completed_at` criada, índices renomeados) a pedido do dono.
- **Codex (Astra) no Windows não funciona com sandbox**: `read-only`/`workspace-write` bloqueiam até leitura de arquivos ("blocked by policy"). Decisão do dono: rodar sem sandbox com controles compensatórios (`infra/scripts/astra.sh`).
- **Limite mensal de gasto da Anthropic** derruba especialistas no meio da tarefa (429). Mitigação: Astra assume tarefas mecânicas; dono avalia aumentar o limite.
- **Agentes personalizados e MCP do Obsidian só carregam em sessão aberta dentro de `C:\dev\project-hunter`**; sessão nascida fora não os vê.

## Abertos na revisão de T1.4/T1.5 (2026-09-05)

- **`last_price` no hash quente carrega o timestamp do `bookTicker`, não o do último trade.** `parse_book_ticker` (`packages/exchange-adapters/hunter_exchanges/binance/streams.py`) carimba o preço do último `aggTrade` em cache com o horário de evento do `bookTicker`, e `write_ticker` (`services/market-worker/hunter_market_worker/hot_state.py`) grava um único `ts` no hash `mkt:*:ticker`. Cenário de falha: o canal de trades para, book e `bookTicker` continuam; `GET /api/v1/markets` devolve o preço antigo com `last_update` recente e o mercado fica `ok`. O payload de tempo real **já** separa `price_ts` e `book_ts` (`ingest.py::build_tick_payload`) e a tela de T1.5 usa `price_ts` corretamente — o buraco é só no caminho REST/hot state. **Dono:** T1.2/T1.3. **Fix:** levar `price_ts` para o hash e expor a idade do preço separada da idade da cotação em `components.ticker`.
- **`apps/api/tests/integration/test_webhook.py::test_a_crash_where_even_the_release_never_runs_still_recovers_after_the_stale_window` falha.** A suíte de `apps/api` estava 428/0 e passou a 445/1 depois que a T1.3 acrescentou `command_timeout: 30` engine-wide em `packages/core/hunter_core/db/session.py`. Falha também isolada (`uv run pytest apps/api/tests/integration/test_webhook.py -q` → 1 failed, 16 passed), então não é ordem de teste. **Dono:** T1.3 (`packages/core`). Nenhum arquivo de T1.4/T1.5 está envolvido.
- **Índice do git compartilhado entre duas sessões.** Com duas instâncias trabalhando no mesmo repositório, `git add` de uma aparece no `git diff --cached` da outra; um `git commit` sem pathspec varreria trabalho alheio. Contorno usado: `git commit -- <caminhos>`, que commita a árvore de trabalho só daqueles caminhos e não toca o resto do índice.
