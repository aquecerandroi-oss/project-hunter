# Plano — Shadow Lab v0 (estratégias avaliando o mercado real em modo sombra, desde já)

**Status:** DECISÃO CONJUNTA Claude ⇄ Astra fechada em 2026-09-05 (3 rodadas, `.claude/state/dialogue-SHADOW.md`; Obsidian `06-DECISIONS/Dialogos/SHADOW.md`). Pedido do dono: "deixar agentes já fazendo a parte de compra e venda virtual; a Sexta-feira ajuda a achar as falhas pesquisando e analisando, e vai anotando no Obsidian as estratégias lançadas" e "o virtual precisa estar pronto primeiro, antes de gastar dinheiro real". Trilha paralela ao M1/M2; não altera a ordem dos milestones. **A decisão aprova o desenho para implementação; a ativação de qualquer versão depende da entrega e da prova dos critérios de aceite S0–S4.**

**O que é (e o que não é).** É a PARTE 11 da diretiva ("Shadow Mode: Hunter registra 'I would trade here' e depois mede o resultado") antecipada para rodar sobre o dado real do M1. **Não é** paper trading: não há carteira, ordens, fills, posições nem PnL de portfolio (isso é M3/M4, com Risk Engine na frente de qualquer entrada). Cada número do Shadow Lab é **hipotético, rotulado como tal, com custos assumidos declarados** (spread total 2 bps, slippage 5 bps por lado, taxa 4 bps por lado — hipóteses do experimento, não tarifas verificadas).

**Por que vale agora.** A performance de uma estratégia só é mensurável com histórico; começar a coletar decisões sombra hoje faz o M5 (Lab) nascer com dados. As mesmas classes `Strategy` serão as dos agentes do M4.

## Decisão conjunta (contrato do experimento)

1. **Versões congeladas.** A **primeira ativação** de uma `strategy_version` congela tudo que determina o experimento: `strategy_id`, `version`, `code_ref` (módulo + hash do código das estratégias e das calculadoras), `parameters_schema`, `default_parameters` completos, `params_hash` canônico (`params_format = 1`: chaves ordenadas, decimais como string normalizada sem zeros à direita nem expoente, timestamps ISO-8601 UTC com `Z`, ausentes como `null`; vetores de teste provam identidade igual para representações equivalentes), timeframes, agregação e seed/âncora do ATR, política de reentrada, perfil de entrada/saída/custos, modelo de outcome. Trigger na migração `0002_shadow_lab` rejeita `UPDATE` desses campos e de `activated_at` (inclusive `SET NULL`) para qualquer linha com `activated_at IS NOT NULL`, em qualquer `status` (ativa, deprecated, reativada); só `status` e auditoria mudam. Conteúdo diferente = versão nova. v1 e v2 rodam em paralelo no mesmo intervalo e universo elegível; o Lab reporta cobertura e exclusões por versão. Replay e prospectivo são **coortes** distintas (`prospective` | `replay:<run_id>`); dados usados para desenvolver uma versão não são a sua avaliação futura reservada.
2. **Envelope imutável da decisão.** `agent_signals.supporting_features` é escrito uma vez, na decisão, e nunca depois (teste garante): `observation_ts` = fechamento da barra de referência (`source_bar_close`), `decision_at`, disponibilidade/qualidade por entrada, valores calculados, fontes duráveis, composição/elegibilidade do universo no instante, `purpose = research_only`, `cohort`, `params_format`.
3. **Entrada, saída e custos ("por barras", v0).** Entrada hipotética no **open da primeira barra de 1 min cuja abertura é estritamente posterior a `decision_at`**, com a barra escolhida e a decisão **persistidas antes dessa abertura** (`tracking_state = pending_entry`); limite `entry_bar_open − source_bar_close ≤ 120 s` (12:00/12:05:02/12:06 → `no_entry: late`; 12:00/12:00:02/12:01 → entra); commit que perde a abertura → `no_entry: late`, nunca entrada retroativa; reentrega resolve a barra já comprometida; decisão não persistida antes de uma falha ganha `decision_at` novo. Preços sintéticos sobre OHLC (nunca ask do hot state, nunca bid/ask reconstruído): `P_entry = open × (1 + 6/10000)`, `P_exit = base_exit × (1 − 6/10000)`; taxa fora dos preços. Geometria congelada na decisão e revalidada com `P_entry`: `stop < P_entry < target1`, senão `no_entry: geometry` (níveis intactos). `R_net = ((P_exit − P_entry) − 0,0004·P_entry − 0,0004·P_exit − funding_por_unidade) / (P_entry − stop_inicial)`; funding assinado; funding aplicável não apurável → `R_net = null` com motivo e `r_ex_funding` como métrica separada com cobertura própria. Saída: gap na abertura primeiro (abriu abaixo do stop → sai na abertura com custo adverso), depois toques intrabar; stop e alvo na mesma barra → **stop** (convenção pessimista versionada); alvo único; alvo ultrapassado usa `target1` como base sem crédito; expiração na abertura exatamente em `entry_bar_open + horizonte` (4 h momentum / 2 h volume); invalidação observada no fechamento sai na próxima abertura elegível; eventos comprovados antes prevalecem; nenhum extremo posterior ao horizonte; barra necessária irrecuperável → `censored`. Momentum: stop **e** alvo 1 a 1,5 ATR da referência = "**1 R nominal na referência**", nunca 1 R garantido na entrada (referência 100, ATR 2, stop 97, alvo 103, entrada 101 → 0,5 R bruto).
4. **Episódios e estados.** Avaliação de novas entradas **só em fechamentos distintos do timeframe da estratégia** (momentum 15 min, volume 5 min, UTC); outcomes avançam em barras de 1 min. Um acompanhamento `pending_entry|active` por `(strategy_version_id, market_id, cohort)`; rearme só após uma barra elegível com a condição **falsa após o término** do acompanhamento anterior seguida de nova transição para verdadeira; dado ausente não rearma. Estado durável em `shadow_episodes` (`episode_id`, `last_bar_close`, `armed`, `open_outcome_signal_id`) com lock transacional. Três eixos distintos: `SignalStatus` (validade do sinal), `OutcomeResult` (`target|stop|expired|invalidated|open`) e `signal_outcomes.tracking_state` (`pending_entry|active|terminal|no_entry|censored`, com `no_entry_reason`/`censored_reason`); `terminal`, `no_entry` e `censored` não reabrem; `no_entry` nunca conta como aberto; censura nunca vira `expired`.
5. **MFE/MAE honestos.** `mfe`/`mae`/`mfe_ts`/`mae_ts` canônicos ficam **nulos** quando o extremo total é indeterminado (OHLC não revela o extremo nem o instante); `signal_outcomes.meta.excursions` = `{unit, method: "ohlc_complete_bars_v1", coverage: {bars_known, bars_total}, mfe_complete_bars, mae_complete_bars, bounds: {mfe: [lo, hi], mae: [lo, hi]}, bar_windows, ambiguous, initial_risk, reference_price}`; barra de entrada completa anterior à saída participa; sem barras completas, parcial indisponível (nunca zero inventado); MAE como magnitude positiva; normalização pelo risco inicial congelado. Cenário-guia: entrada 100, stop 99, alvo 102, primeira barra low 98/high 103 → `mfe = null`, `bounds.mfe = [0, 3]`, `ambiguous = true`.
6. **Idempotência e recuperação.** `agent_signals.id = uuid5(NAMESPACE_SHADOW, canonical(strategy_version_id, market_id, params_hash, source_bar_close, cohort))`, `decision_at` fora do hash; `INSERT … ON CONFLICT (id) DO NOTHING`; outcome 1:1 pelo `signal_id`; `event_id = signal_id` só para `shadow.signals.emitted`. Sinal + outcome inicial + episódio/checkpoint + linha de outbox na **mesma transação**, ACK só após commit; reentrega nunca sobrescreve o envelope nem recomputa a entrada com o relógio atual; recovery avança por velas contíguas e nunca reabre estado encerrado. Outbox: `shadow_outbox` na migração `0002_shadow_lab` com despachante, reconciliação e entrega idempotente em S2 (antecipação do contrato T2.9, que a absorve preservando pendências e identidades).
7. **Agregação e ATR.** 1 m → 5 m/15 m só com barras UTC contíguas, finais e disponíveis até `decision_at` (contexto cortado em `source_bar_close`; alterar o futuro nunca altera uma decisão passada); barra atual fora das medianas; warm-up sem janela reduzida; máxima dos 20 fechamentos em 15 min; retornos `close_t/close_{t−n} − 1` em fração; ATR = Wilder(14) de 15 min **também no volume**, seed/âncora persistidos, fórmula compatível com `docs/plans/M2.md` (T2.2).
8. **Universo.** Elegibilidade e motivo gravados no envelope; `tracking_hold` durável (derivado de `shadow_episodes` com outcome `pending_entry|active`) faz o market-worker manter velas de mercado excluído até o término; reconciliado após restart; encerrar v1 não libera a coleta necessária a v2; fontes auditáveis após a retenção ordinária; impossibilidade de recuperar → `censored`. Backfill sempre pedido ao market-worker (dono único do REST, M2).
9. **Métricas com nome certo.** *Taxa de alvo entre toques resolvidos* = target/(target+stop); *taxa de lucro líquido* = encerrados avaliáveis com `R_net > 0` / encerrados avaliáveis (expired/invalidated com resultado conhecido entram); *expectancy líquida hipotética em R por entrada encerrada avaliável* = média de `R_net` nessa população; *PF* = Σ R_net positivos / |Σ negativos|, nulo com motivo sem perdas; denominador vazio → nulo. Contagens completas (emitidos, pendentes, entradas, não entradas por motivo, ativos, target, stop, expired, invalidated, censurados, funding indisponível). Coortes por decisão, horizonte maturado e `as_of` obrigatórios. *Soma de R hipotéticos* com nome e ordenação explícitos; **PnL e drawdown de carteira = não aplicável**. Regra editorial: antes de **100 outcomes avaliáveis E 30 dias distintos**, só descrição e "inconclusivo"; acima, incerteza por reamostragem em blocos de tempo (mercados simultâneos são dependentes), sensibilidade a custos, variantes tentadas, avaliação futura reservada — e ainda assim "pesquisa", nunca promessa.
10. **Isolamento.** Só LONG no v0. Stream próprio `shadow.signals.emitted`; `purpose` persistido no envelope e no evento, copiado de `strategy_versions.purpose` (T3.15/D10: `research_only` por padrão; `paper` só numa linha derivada pelo script de ativação; `live` recusado por nome até a Fase 4); o proposal builder futuro recusa `research_only` (teste); consenso do M2 com peso zero; `active` não implica elegibilidade de execução (M4 terá `execution_eligible` explícito). Strategy-worker é o **único escritor** de outcomes do Lab (transferência futura ao analytics-worker registrada explicitamente, `docs/PIPELINE.md`).
11. **Memória (Sexta-feira/Obsidian).** `EXP-0001` (momentum v1) e `EXP-0002` (volume v1) reservados ao Shadow; o M2 (T2.8, baselines) passa a `EXP-0003`. Hipótese e protocolo preservados; avaliações **datadas e acrescentadas** com SQL, parâmetros, `as_of`, versão da métrica e proveniência; nunca ativar automaticamente a variante vencedora; páginas dos agentes só recebem `status: sombra` após prova operacional.

## Desenho (consolidado)

- **Framework `hunter_core.strategies`** (arquitetura §6): `Strategy` (Protocol) com `key`, `version`, `parameters_schema`, `default_parameters`, `evaluate(ctx) -> Decision | None` **função pura** sobre um `StrategyContext` (barras finais de 1 min cortadas em `source_bar_close`, agregações 5/15 min, derivativos disponíveis até a decisão, elegibilidade do universo). Sem look-ahead por construção; `params_hash` canônico; nenhum número hardcoded (tudo em `default_parameters`).
- **Estratégias v1:** `momentum_v1` (15 min: close > máxima dos 20 fechamentos anteriores, `return_15m > 0`, volume relativo 15 min ≥ 1,5 vs mediana das 96 barras anteriores, ATR% Wilder(14×15 min) entre 0,3% e 5%; stop e alvo a 1,5 ATR da referência; horizonte 4 h) e `volume_anomaly_v1` (5 min: volume ≥ 4× mediana das 288 barras anteriores, fechamento acima do meio da barra, `return_5m` entre 0 e 2 ATR% com ATR de 15 min; stop = mínima da barra de sinal; alvo 1,5 ATR; horizonte 2 h).
- **`strategy-worker` sombra:** consumidor de `market.candles.closed` (grupo próprio); contexto por mercado (hot state + Postgres para bootstrap, igualdade bootstrap vs contínuo testada); avalia nos fechamentos do timeframe; persiste em transação única; despacha `shadow_outbox`; job de outcomes por barras fechadas de 1 min; supervisão/readiness/heartbeat como o market-worker; `tracking_hold` publicado ao market-worker.
- **API + tela:** `GET /api/v1/lab/shadow/summary` e `/signals` com as métricas do item 9, coortes/`as_of`, nulos com motivo, contagens de cobertura, custos assumidos, rótulo "SOMBRA — hipotético, sem capital, custos assumidos"; `/lab` aba Sombra; nav `lab` → `available` só com a API existente; estados vazios honestos.
- **Ativação:** script de ops com auditoria (`activated_at`, `changelog`), só após S0–S2 aceitos; as outras versões seguem `draft`.

## Tarefas
| ID | Descrição | Files: | Depends-on: | Owner | Tier |
|---|---|---|---|---|---|
| S0 | Migração `0002_shadow_lab` + modelos/enums: trigger de congelamento após primeira ativação; `signal_outcomes.meta JSONB NOT NULL DEFAULT '{}'`, `tracking_state` + motivos; `shadow_episodes`; `shadow_outbox` (contrato de despachante/reconciliação); `params_format`/canônico em `hunter_core`; testes de upgrade/downgrade/upgrade e de cada proteção; T2.1 passa a referenciar esta migração | `infra/migrations/versions/0002_shadow_lab*.py`, `packages/core/hunter_core/db/models/agents.py`, `packages/core/hunter_core/domain/enums.py`, `packages/core/hunter_core/strategies/canonical.py`, testes em `packages/core/tests/**` e `apps/api/tests/integration/**` | — | database-architect | opus |
| S1 | `hunter_core.strategies`: Protocol, `StrategyContext`, `Decision`, registry, `params_hash` (usa `canonical.py` de S0 — enquanto não existir, S1 entrega a função e S0 a adota), agregação 1 m→5 m/15 m sem look-ahead, ATR Wilder(14) 15 min com seed/âncora, `momentum_v1`, `volume_anomaly_v1`; testes: gera/não gera, warm-up insuficiente, minuto ausente, vela não-final ou futura alterada não muda a decisão, bootstrap = contínuo, identidade de decisão, prospective/replay | `packages/core/hunter_core/strategies/**`, `packages/core/tests/unit/test_strategies*.py` | M1 dados | quant-engineer | opus |
| S2 | `strategy-worker` sombra: consumidor, contexto, decisão/pending_entry/entrada/outcome por barras, transação única + outbox + despachante, episódios/rearme, `tracking_hold`, censura, supervisão/readiness/heartbeat, serviço no compose, script de ativação auditado; injeção de falhas (antes do commit, entre commit e publicação, após publicação antes do ACK, dois consumidores, eventos fora de ordem, restart no rearme) | `services/strategy-worker/**`, `infra/docker/docker-compose.yml`, `infra/scripts/activate_strategy_version.py`, `services/market-worker/**` (só `tracking_hold`) | S0, S1 | backend-specialist | opus |
| S3 | API `/api/v1/lab/shadow/*` + tela `/lab` (aba Sombra): métricas distintas, PF com denominador, coortes/`as_of`, nulos com motivo, excursões parciais/limites, contagens, rótulo; autorização, contratos, estados vazios; lint/typecheck/test/build | `apps/api/hunter_api/{routers,schemas,services,repositories}/lab*.py`, `apps/web/app/(app)/[orgSlug]/lab/**`, `apps/web/components/lab/**`, `lib/nav-registry.ts` | S2 | backend-specialist + frontend-specialist | sonnet |
| S4 | Obsidian: `05-EXPERIMENTS/EXP-0001-momentum-v1.md`, `EXP-0002-volume-anomaly-v1.md`, índice com reserva (`EXP-0003` = M2), `_TEMPLATE-EXP` (protocolo, avaliações acrescentadas, carteira N/A), páginas dos agentes (`status: sombra` só após prova), `10-PERFORMANCE/*` com as métricas do item 9; rotina do plantão: avaliação datada por turno com SQL | `obsidian/**`, `.claude/agents/sexta-feira.md` (rotina) | S2 | Sexta-feira | opus |

Revisores: `database-architect` (S0 é dela; `code-reviewer` + Astra revisam), `quant-engineer` em revisão cruzada de S1, `risk-engine-guardian` em S2 (é o caminho que um dia vira execução; nada pode ordenar), `security-reviewer` em S3, `code-reviewer` em tudo, Astra em tudo. S0 e S1 podem correr em paralelo com T1.6b/T1.7 (arquivos disjuntos).

## Critérios de aceite (checklist da decisão conjunta — nenhum item verificado ainda)

**S0 — Migração e contratos duráveis**
- [ ] Migração aplicada; modelos/enums/DDL alinhados; upgrade, downgrade/upgrade em banco de teste; `alembic check` sem divergência.
- [ ] Congelamento após a primeira ativação provado (ativa, deprecated, reativada; tentativa de zerar `activated_at`; alteração de qualquer campo que identifica ou determina o experimento).
- [ ] Coerência `tracking_state`/`result`/motivos; unicidade e integridade episódio↔outcome; sem acompanhamentos `pending_entry|active` órfãos.
- [ ] Serialização canônica (`params_format = 1`) com vetores de equivalência; isolamento por `run_id`; envelope preservado (nunca reescrito).
- [ ] `shadow_outbox` com contrato de despachante/reconciliação para S2 e absorção futura por T2.9 sem perda de pendências.

**S1 — Estratégias e contratos puros**
- [ ] Parâmetros, código/dependências das calculadoras, formato canônico, ATR/seed, timeframes e perfil de custos congelados e declarados; "1 R nominal na referência" distinto do R na entrada.
- [ ] Cenários testados: sinal, ausência de sinal, warm-up insuficiente, minuto ausente, alteração de vela futura/não-final, bootstrap = execução contínua.
- [ ] Identidade de decisão, contexto temporal (corte em `source_bar_close`), universo elegível e separação prospective/replay especificados e testados.

**S2 — Persistência, worker e outcomes**
- [ ] Migração S0 aplicada antes de qualquer ativação; dependência de outbox declarada e cumprida.
- [ ] Testes: atraso desde a referência, commit que perde a abertura, geometria após gap, custos nos dois lados, funding indisponível, stop/alvo simultâneos, expiração/invalidação, excursões ambíguas.
- [ ] Injeção de falhas antes do commit, entre commit e publicação, após publicação antes do ACK; dois consumidores; eventos fora de ordem; restart durante rearme — um único efeito lógico, sem reabertura de terminal.
- [ ] Recovery contíguo, censura de gap irrecuperável, `tracking_hold` após exclusão de mercado e restart (com duas versões); fontes preservadas após retenção ordinária.
- [ ] Operação sobre dados do M1 demonstrada, readiness/heartbeat, isolamento `research_only`; escritor único de outcomes registrado; ativação auditada só após os pré-requisitos.

**S3 — API e tela**
- [ ] Taxa de alvo, taxa de lucro e expectancy como métricas distintas; PF com denominador explícito; coortes/`as_of`; todas as contagens de cobertura.
- [ ] Desconhecidos como nulos com motivo; intervalos/ambiguidade de excursões; custos assumidos visíveis; nenhuma soma de R apresentada como carteira.
- [ ] Autorização da API, contratos e estados vazios validados; lint/typecheck/test/build verdes.

**S4 — Pesquisa e memória**
- [ ] Reserva de IDs consolidada (aqui, em `docs/plans/M2.md` T2.8 e no índice do Obsidian), protocolo imutável, SQL/parâmetros/`as_of`, avaliações datadas, ligação entre versões; hipótese e histórico preservados.
- [ ] Limiar editorial aplicado, avaliação futura reservada, variantes/cobertura registradas; `status: sombra` só com prova operacional.

## Placar (T3.18)

`GET /api/v1/lab/shadow/scoreboard?as_of=` e `GET /api/v1/lab/shadow/curve?version_id=&as_of=`
são a visão ao vivo do mesmo SQL que o plantão roda à mão (`obsidian/05-EXPERIMENTS/EXP-0001-*`,
`EXP-0002-*`) — mesma população (`prospective`, `emitted_at <= as_of`), mesmas definições do item 9
(`hit_rate` = alvo entre toques resolvidos, `net_profit_rate` = lucro líquido entre avaliáveis,
`expectancy_r` = média de `R_net`, `profit_factor` nulo com motivo quando falta um lado), reusadas
de `lab_summary_metrics.py` sem reabrir a discussão de denominador. `worst_streak` (maior sequência
de perdas consecutivas) e `max_drawdown_r` (maior queda pico-a-vale na curva de `R_net`
acumulado, ordenada por `exit_ts`) são novos nesta entrega. **Veredito mecânico:** `inconclusivo`
enquanto a maturação do item 9 não fechar (**100 outcomes avaliáveis E 30 dias distintos**); madura,
`validada` se `expectancy_r > 0` **e** `profit_factor > 1`, senão `reprovada` — nunca "lucro
garantido", sempre "simulado". `profit_factor` nulo por ausência de perdas (`no_losses`, Σ perdas =
0) conta como `> 1` para o veredito, porque um lado perdedor vazio não pode reprovar a versão; nulo
por população vazia (`no_sample`) não ocorre aqui, pois madura já exige ≥ 100 outcomes com `R_net`
conhecido. A curva **não** aplica o portão de maturação do horizonte (`is_evaluable()`): ela plota
todo resultado já resolvido (`terminal` com `r_multiple` não nulo), porque aquele portão existe para
não enviesar estatísticas agregadas para operações rápidas — nada disso se aplica a uma trajetória.
As avaliações do plantão em `obsidian/05-EXPERIMENTS/` continuam sendo o registro histórico
(datadas, nunca reescritas); o placar é a leitura corrente da mesma régua, não a substitui.

**Esta régua é a única (T3.18c).** O bloco `replication` do mesmo cartão publica `parent` com a
população, a maturidade e o veredito **recalculados sobre esta definição** — mesma população
avaliável (portão `is_evaluable`), mesmos dias de **saída**, mesmo tratamento de `profit_factor`
nulo (só `no_losses`/`sem_perdas`; só perdas é PF `0` com motivo nulo) —, e
`hunter_indicators.replication.PopulationStats`/`scoreboard_verdict` são a implementação pura
compartilhada com a CLI de replicação. Um cartão que mostrasse `verdict` e `parent.verdict`
diferentes estaria publicando dois vereditos sobre a mesma evidência; ver
`docs/plans/REPLICATION.md` §5 e §6. O bloco `replay` e o `replication.status` podem repousar em
evidência de replay, **rotulada**; `verdict` e `maturity`, nunca (D15).

**Sinais idênticos entre versões irmãs são esperados, não um bug (T3.38, Everton, screenshot
08/09 15:16 Brasília: "não tá duplicando não??").** A replicação (item 3 acima) cria dez irmãs de
parâmetro de uma versão `validada`; sempre que a barra decisória cai fora da região em que os
parâmetros de duas irmãs discordam (ex.: `atr_pct_min` mais alto que uma irmã aplica, mas o valor da
barra passa em ambos os limiares), as duas avaliam a mesma entrada geométrica e emitem, cada uma na
sua própria linha de `strategy_versions`, um sinal com o mesmo `(market, source_bar_close,
virtual_entry, exit_price, result)` — inclusive uma cópia byte-idêntica de parâmetros (D10) sempre
concorda. Cada sinal continua sendo uma linha própria em `signal_outcomes` (uma proposta por
versão, nunca deduplicada no banco — cada versão é seu próprio experimento e precisa da própria
amostra para maturar), mas contar a mesma operação de mercado três vezes no placar visual infla a
amostra sem adicionar informação nova. `GET /lab/shadow/signals` (T3.37) resolve isso no servidor,
não no navegador: cada item ganha `identity_key` (hash estável do mesmo tuplo, calculado a partir do
envelope) e `totals` ganha `distinct_operations` por estado — a contagem sobre `identity_key`. A
tabela do Lab (`components/lab/lab-signal-grouping.ts`) agrupa, só na página carregada e só quando
ela mistura mais de uma versão, as linhas que compartilham `identity_key` numa única linha com um
chip por versão (`v2 · v3 paper · v4`); o cartão "Resultado das operações desta página" soma cada
operação uma única vez (primeira ocorrência) e avisa "versões irmãs decidem a mesma barra; cada
operação é contada uma vez"; o escopo "de todas as concluídas" e o `title` de cada aba usam
`totals.distinct_operations` como denominador honesto. Nada disso muda a maturação por versão do
item 9 (cada irmã ainda precisa dos seus próprios 100 outcomes/30 dias) — é puramente uma leitura
que evita contar a mesma barra de mercado como três operações independentes.

## Funil de validação (T3.36)

Cinco etapas, nesta ordem, e **cada uma responde a uma pergunta diferente**. A ordem não é
burocracia: as três primeiras são baratas e matam cedo; as duas últimas custam semanas de calendário
e só valem a pena sobre o que sobreviveu.

```
portão C1–C8  →  implementação  →  replay 31 d  →  estresse  →  prospectivo  →  replicação
 (desenho)        (código)         (mata no dia 1)  (robustez)   (a régua)      (o veredito)
```

1. **Portão de desenho C1–C8** — `obsidian/05-EXPERIMENTS/_TEMPLATE-EXP.md`, seção congelada,
   escrita **antes** do código pelo quant e conferida pelo `code-reviewer`. *Pode dizer:* que a tese
   tem mecanismo, que a entrada não tem oito condições garimpadas, que a estratégia cabe nos limites
   do `paper_v1` e é executável no SPOT acima do piso de 50 M, e que a frequência esperada chega aos
   30 desfechos/ano/mercado sem os quais a régua nunca fecha. *Não pode dizer nada sobre
   desempenho* — nenhum número dele é evidência de vantagem. É o filtro mais barato que existe e o
   único que roda antes de qualquer linha de código.
2. **Implementação** — versão nova, `params_hash` congelado, `purpose = research_only` (item 1). Uma
   mudança de conteúdo depois disto é **versão nova** e recomeça o funil.
3. **Replay de 31 dias** (`docs/PIPELINE.md` §6c) — *pode dizer:* "isto não funciona", e dizer no
   primeiro dia. Sobre as velas já persistidas, com o mesmo código, os mesmos custos e as mesmas
   regras de não-antecipação, uma versão sem vantagem aparece imediatamente e não consome trinta
   dias de calendário. *Não pode dizer:* que funciona. A elegibilidade é lida **hoje** (§6c, "o que
   um replay não prova"), a janela é a mesma em que a família inteira foi desenhada, e o veredito do
   placar (`validada`) e a régua de maturidade **continuam só com `prospective`** (D14/D15,
   `REPLICATION.md` §3.5).

   **Critérios de morte K1–K5, congelados por experimento antes da corrida**
   (`.claude/state/notes-T3.33.md` §5.1; aplicados desde `EXP-0008`, nunca antes trazidos a esta
   página até T3.58): **K1** população mínima — < 20 decisões, não é amostra pequena, é ausência
   de população, e mais dias não a criam; **K2** população saturada — > 1 500 decisões (~> 1,2 /
   mercado-dia), não é uma condição, é um relógio; **K3** ≥ 100 desfechos avaliáveis **e** ≥ 30
   dias distintos **e** expectancy bruta (`r_ex_funding`) < 0 — perde antes dos custos, não há
   custo a corrigir; **K4** `unavailable` > 40 % das barras — problema de janela/gap, corrigir é
   versão nova, não ajuste; **K5** cobertura de `R_net` < 70 % — não mata, rebaixa toda leitura
   futura. K1 sozinho é `inconclusivo`, não negativo; qualquer outro disparo é deprecar ou
   declarar.

   **K4 deixa de ser mensurável numa versão com portão de elegibilidade**
   (`eligibility_policy`, `docs/PIPELINE.md` §4b itens 10–12, T3.52d). O portão avalia **antes**
   da checagem de contexto: uma barra que seria `unavailable` por contexto insuficiente nunca
   chega lá, porque já foi recusada como `ineligible`. Uma versão com portão sempre mede
   `unavailable ≈ 0`, e esse zero é falso verde — não ausência de gap de contexto. Medido:
   `mean_reversion v11` e `momentum v11` fecham K4 em 0 % enquanto os pais, na mesma fatia,
   mostram `unavailable: 448` (`.claude/state/notes-T3.52d.md` §6). A leitura honesta de K4 para
   uma versão com portão é o K4 **do pai**, na mesma janela; a fração `ineligible` da filha é
   outro número (barras fora do rótulo permitido) e não substitui K4.
4. **Passada de estresse** (`services/strategy-worker/hunter_strategy_worker/replay/stress.py`) —
   sobre as **entradas congeladas** da coorte de replay, reprecificando os desfechos com custo ×2,
   stop e alvo ×0,75/×1,25, entrada atrasada uma barra, cada mercado deixado de fora e cada metade
   da janela. *Pode dizer:* que a vantagem medida **não sobrevive** ao dobro do custo, a um stop 25 %
   diferente, à ausência de um único mercado ou à segunda metade do período — e cada um desses é
   motivo suficiente para não gastar trinta dias de prospectivo. *Não pode dizer:* que a vantagem é
   real. Ela reusa a mesma população; é o mesmo dado visto por sete ângulos, não sete experimentos.
   Veredito mecânico: `robusto`, `frágil a custos`, `frágil a parâmetros`, `dependente de um
   mercado`, `dependente de metade` — mais `amostra_insuficiente` (< 30 desfechos avaliáveis) e
   `sem_vantagem_na_base`, que é o que ela responde quando a expectancy da base já é ≤ 0 e a
   pergunta "isto é robusto?" não tem sentido.
5. **Prospectivo** (§6b) — a coorte `prospective`, reservada, com a régua editorial do item 9: antes
   de **100 desfechos avaliáveis E 30 dias distintos**, `inconclusivo`. *Pode dizer:* `validada` ou
   `reprovada` pela régua do placar, sobre dado que não existia quando a versão foi congelada. *Não
   pode dizer:* que a vantagem se repete — um único número bom sobre uma única população é
   exatamente o que a literatura manda desconfiar.
6. **Replicação** (`REPLICATION.md`) — os quatro blocos concordando, mais o **controle** declarado do
   §"Controle". *Pode dizer:* `replicada`, `replicando` ou `refutada`. *Não pode dizer:* que a
   estratégia deve ser ativada — promover continua sendo o ato auditado do Everton.

Nada neste funil ativa, promove ou dimensiona coisa alguma, e nenhuma etapa dispensa a seguinte: um
`robusto` no estresse sobre uma coorte de replay é, em toda comunicação, "robusto **no replay**",
rotulado como tal.

## Universo de pesquisa (T3.82)

Desde 09/2026 o `strategy-worker` não decide mais sobre todo o universo monitorado (~200
perpétuos): decide só sobre o mercado cujo `candles_1m` cobre `SHADOW_UNIVERSE_MIN_HISTORY_DAYS`
(90 por padrão) — a mesma janela que o passo 3 do funil (replay de 31 dias, mas a coorte
prospectiva precisa de 90 d de contexto real) e o passo 6 (replicação) exigem para sequer avaliar
uma versão. Medido em 2026-09-10: 16 de ~200 mercados qualificam. Os outros 184 nunca vão passar
por esse funil enquanto não acumularem histórico — decidir sobre eles ao vivo é custo de pesquisa
não validável, não uma população menor do mesmo experimento. Detalhe da regra, do cache e da
métrica: `docs/PIPELINE.md` §6b, `hunter_strategy_worker.universe`. Decisão registrada em
`obsidian/06-DECISIONS/2026-09-10-universo-de-pesquisa-90-dias.md` — aprovação do Everton, o que
muda e o que **não** muda (limites de risco, versões, universo executável da carteira paper).

## Fora de escopo
Carteira, ordens, fills, posições, PnL de portfolio, Risk Engine, SHORT, sinais sobre features do M2 (v2), execução de qualquer natureza.
