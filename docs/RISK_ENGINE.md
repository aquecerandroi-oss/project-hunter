# Risk Engine — contrato v2.1

**Versão 2.1, 2026-09-06.** A v2 (mesma data) foi reescrita a partir da diretiva do Everton de
2026-09-06 (`.claude/state/directive-risk-engine-2026-09-06.md`, verbatim) e das medições da oitava
rodada de conhecimento (`obsidian/11-KNOWLEDGE/Strategy Backlog.md` → "Regras propostas para o Risk
Engine"). Esta revisão fecha, no contrato, as três invariantes que a revisão adversarial da T3.2
(`.claude/state/review-T3.2-risk-core.md`, commits `bf4924b` e `5f86028`) provou faltarem no núcleo
que a v2 já descrevia — nenhum limite do Everton foi alterado; §9.2 lista o que mudou e por quê. O v1
continua legível em `git show 8f42b4d:docs/RISK_ENGINE.md`; a §9 lista o que mudou entre v1 e v2.

Função pura e determinística:

```
evaluate(proposal, portfolio_state, limits, market_liquidity, kill_switch, regime, beta)
    -> RiskDecision
```

Sem rede, sem banco, sem relógio próprio (o instante entra como argumento). Nenhuma ordem de
**entrada** é criada sem uma `RiskDecision.approved = true` persistida em `trade_proposals.risk_decision`
**antes** de a ordem existir. Ordens de **saída** (stop, alvo, fechamento manual, redução por kill
switch) nunca são bloqueadas por este motor — a regra 3 da diretiva é explícita: *"travas de entrada
não podem impedir saídas de proteção"*.

## 1. Entradas

```
TradeProposal      agent, portfolio, market, direction, signal (entry_zone, stop, targets),
                   requested_risk_pct, as_of
PortfolioState     cash, equity, peak_equity, equity_at_trading_day_start, trading_day (America/Sao_Paulo),
                   exposure_notional, open_positions[], pending_entries[] (reservas),
                   planned_risk_open, planned_risk_pending, exposure_by_asset{}, beta_exposure
RiskLimits         perfil do portfolio (§2), com o preset do sistema como origem
MarketLiquidity    quote_volume_24h, quote_volume_last_minute, quote_volume_median_30m,
                   book (níveis, ts), spread_pct, last_price, data_quality, gap_state, in_universe,
                   min_notional, step_size, tick_size
KillSwitchState    system, organization, portfolio → efetivo = o mais restritivo
MarketRegime       regime atual (v0) — só ajusta tamanho, nunca aprova
MarketBeta         beta contra o BTC, com `valid_until` (§6); ausente ou vencido → check `unavailable`
```

Todo insumo carrega carimbo de tempo. Um insumo ausente, vencido ou degradado não vira zero nem
média: vira o estado `unavailable` do check que depende dele (§7).

## 2. Perfil `paper_v1` — os valores do Everton

Preset novo (`risk_preset` ganha `paper_v1`), sistema, `organization_id IS NULL`. É o perfil da
carteira virtual do M3. Os presets `conservative`/`balanced`/`aggressive` do v1 continuam existindo e
**não** são o perfil da carteira.

| Chave | Valor | O que é |
|---|---|---|
| `risk_per_trade_pct` | `0.0025` | Perda planejada no stop, **incluindo custos estimados**, sobre o patrimônio **atual** |
| `max_aggregate_planned_risk_pct` | `0.01` | Soma dos riscos planejados de posições abertas **e** entradas pendentes |
| `max_participation_pct` | `0.01` | Fração do volume de referência de um minuto (§4) |
| `participation_reference` | `min(last_complete_minute, median_30_complete_minutes)` | A referência que ele definiu |
| `max_total_exposure_pct` | `0.40` | Σ notional / equity, incluindo pendentes |
| `max_asset_exposure_pct` | `0.10` | Por moeda (base asset), somando exchanges |
| `max_concurrent_positions` | `5` | Abertas + pendentes |
| `max_beta_btc_exposure` | `0.5` | `Σ \|notional_i × β_i\| / equity` (módulo, R-CORR-1) |
| `min_liquidity_usd_24h` | `50_000_000` | Volume 24 h do par, **na exchange de execução** |
| `max_volume_age_s` | `120` | **Novo em v2.1.** Idade máxima do volume do minuto e do volume de 24 h (mesmo carimbo, R-OPS-2); acima disso, sem carimbo, ou carimbo no futuro, `liquidity_24h` e `participation` viram `unavailable` (§3.1 checks 9 e 19). Origem: a própria v2 já prometia "os insumos com idade máxima declarada... volume de 24 h, volume do minuto" em §7 (R-OPS-2); a revisão adversarial de 2026-09-06 (bloqueante 3) achou que o valor existia no perfil e nunca era lido |
| `max_leverage` | `1` | SPOT, sem empréstimo, sem alavancagem, sem short |
| `kill_switch_warning` | `{daily_loss_pct: 0.01, drawdown_pct: 0.04}` | Modo AVISO (§5) |
| `kill_switch_blocked` | `{daily_loss_pct: 0.02, drawdown_pct: 0.08}` | Modo BLOQUEADO (§5) |
| `warning_size_multiplier` | `0.5` | Aplicado ao **tamanho final aprovado** (§4) |
| `regime_size_multiplier` | gramática do v1 (§2.1) | Aplicado ao **tamanho final aprovado** |
| `max_entry_deviation_pct` | `0.005` | **Novo em v2.1.** Meia largura da zona de entrada em torno do **preço observado** (§3.1 check 7, "entrada fora da zona"). Origem: a v2 já nomeava a zona no texto do check sem publicar o número no perfil; R-OPS-2 e a revisão adversarial de 2026-09-06 (bloqueante 2) exigiram a chave, porque sem ela `entry_ref` nunca era confrontado com o mercado |
| `max_spread_pct`, `max_slippage_pct`, `[min,max]_stop_distance_pct` | herdados do preset conservador, revisáveis | Guardas técnicas, não limites de capital |

**O que a diretiva não define e este contrato não inventa:** nenhum limite acima foi criado por nós.
`max_spread_pct`, a banda de distância de stop e `max_slippage_pct` são as guardas técnicas do v1,
mantidas porque nenhuma foi provada redundante; qualquer alteração de valor é pergunta ao Everton
(`docs/plans/M3.md` → "Perguntas ao Everton antes de alterar qualquer limite").

**O limite é teto, não meta.** Nada no motor aumenta posição nem afasta stop para "chegar" a 0,25 %.
Se o sinal pede menos risco que o teto, o tamanho é o do sinal.

### 2.1 Gramática de `regime_size_multiplier` (mantida do v1)

Uma chave é `<REGIME>` ou `<REGIME>_<DIRECTION>`, com `<REGIME>` um rótulo de `market_regime` e
`<DIRECTION>` um rótulo de `trade_direction`, ambos em maiúsculas; o valor é **string** JSON para
virar `Decimal` sem passar por float. A busca para na primeira que existir: `<REGIME>_<DIRECTION>`,
depois `<REGIME>`, depois `1.0`. Só um multiplicador é aplicado — eles nunca se compõem.

Limites são validados na edição (`max_asset_exposure_pct ≤ max_total_exposure_pct`, etc.). Toda
edição gera `audit_logs` com before/after e um `risk_events` do tipo `limits_changed`.

## 3. Checks — ordem de avaliação

Todos os checks avaliáveis são registrados em `risk_decision.checks[]` como
`{name, state, value, limit, input_ts, message}`, **mesmo depois do primeiro reprovado**, para o
painel de explicação mostrar o quadro inteiro. `state` ∈ `passed | failed | unavailable` — o terceiro
estado é novo no v2 (R-OPS-1) e **reprova por padrão**.

### 3.1 Admissibilidade (antes do sizing)

| # | Check | Reprova quando | Insumo |
|---|---|---|---|
| 1 | `kill_switch` | efetivo ∈ {TRADING_DISABLED, EMERGENCY} | estado do kill switch |
| 2 | `portfolio_status` | portfolio não `active`, ou agente não `enabled` | banco |
| 3 | `modality` | direção ≠ LONG, alavancagem > 1, produto ≠ spot | proposta + perfil |
| 4 | `data_quality` | mercado `degraded`, ou último preço mais velho que o limite declarado | carimbo do preço |
| 5 | `market_gap` | o mercado tem lacuna de coleta **não recuperada** na janela (R-OPS-3) | continuidade |
| 6 | `market_in_universe` | o mercado saiu do universo entre o sinal e a proposta (R-OPS-4) | universo |
| 7 | `signal_validity` | sinal inativo; **ou** stop fora de `(0, entry_ref)`; **ou** stop não abaixo do preço observado; **ou** `\|entry_ref − observado\| / observado > max_entry_deviation_pct` | proposta + preço observado |
| 8 | `stop_distance` | fora de `[min_stop_distance_pct, max_stop_distance_pct]`, medida no preço do sizing (§4, `sizing_price`) | proposta |
| 9 | `liquidity_24h` | `quote_volume_24h` < `min_liquidity_usd_24h` (50 M); **ou** o volume (minuto ou 24 h) tem idade > `max_volume_age_s`, sem carimbo, ou carimbo no futuro → `unavailable` | velas 24 h |
| 10 | `spread` | `spread_pct` > `max_spread_pct` | book |
| 11 | `book_depth` | book ausente, vencido, ou raso demais para qualquer tamanho admissível | book (10 s) |
| 12 | `beta_validity` | sem β válido para o mercado (§6) — o ativo fica só em shadow | `market_betas` |
| 13 | `concurrent_positions` | abertas **+ pendentes** ≥ `max_concurrent_positions` (5) | estado + reservas |
| 14 | `duplicate_position` | já existe posição ou pendente no mesmo mercado neste portfolio | estado + reservas |
| 15 | `aggregate_risk_budget` | `planned_risk_open + planned_risk_pending ≥ max_aggregate_planned_risk_pct` | estado + reservas |
| 16 | `daily_loss` | perda do dia ≥ `kill_switch_blocked.daily_loss_pct` | equity + início do dia |
| 17 | `drawdown` | drawdown ≥ `kill_switch_blocked.drawdown_pct` | equity + pico |

Reprovar em 16 ou 17 também **aciona** a transição de kill switch (§5) — o check não é só um veto,
é o detector.

**`signal_validity` (check 7), por extenso — novo em v2.1.** O preço observado é o `mid` do livro
quando existe, senão `last_price` (`last_price` é obrigatório, então o preço observado nunca é
indisponível; a frescura dele é o check 4, `data_quality`). Reprova a menos que **todas** as
condições valham juntas:

1. o sinal está ativo (`signal_valid`);
2. o stop está abaixo de `entry_ref` (geometria do lado comprado);
3. o stop está abaixo do **preço observado** — um stop já rompido no mercado atual não abre posição;
4. `|entry_ref − observado| / observado ≤ max_entry_deviation_pct` (0,5 % no `paper_v1`) — a zona de
   entrada, medida contra o observado, não contra `entry_ref`.

**A banda é assimétrica, e isso é intencional, não um bug a esconder.** Como o denominador é o preço
**observado**, para `entry_ref = 100` a banda admite observado entre ≈ 99,5025 e ≈ 100,5025 — ela é
levemente mais tolerante à alta. Nenhum caminho de tamanho fica mais generoso por causa disso: o
sizing (§4) usa o **pior** dos dois preços, então a assimetria nunca aumenta o tamanho aprovado; ela
só decide se a proposta é **admissível**. Cenário que motivou o check: `entry_ref = 100`, stop 97,5,
mercado a 110 — antes da v2.1 era aprovado, com notional registrado 1.851,80 contra gasto real
2.036,98 e perda real no stop de 235,55 (1,18 % do patrimônio contra o teto de 0,25 %); e um LONG com
stop 97,5 e mercado a 90 (stop já rompido) também era aprovado.

**Idade do volume (checks 9 e 19) — novo em v2.1.** O insumo de liquidez carrega **um** carimbo
(`volume_ts`) para o volume de 24 h e para a referência do minuto; um carimbo vencido, ausente ou no
futuro invalida os dois de uma vez — `liquidity_24h` (check 9) vira `unavailable`, o sizing não roda
(§4), e `participation`, `sizing`, `slippage_estimate`, `cash` e `exposure_after` saem `unavailable`
em cascata, pelo motivo declarado. Cenário: um volume do minuto observado 45 minutos antes do `as_of`
não pode sustentar o teto de participação como se fosse agora.

### 3.2 Sizing (§4) e checks posteriores

| # | Check | Reprova quando |
|---|---|---|
| 18 | `sizing` | o tamanho final é menor que o `min_notional`/`step_size` do mercado — **rejeita, nunca arredonda para cima** |
| 19 | `participation` | registrado sempre; reprova só se a referência de volume estiver indisponível |
| 20 | `slippage_estimate` | travessia do book para o tamanho final > `max_slippage_pct`; sem book → `unavailable` → rejeita |
| 21 | `cash` | notional > `available_cash` = `cash − Σ reserved_cash` das pendências (SPOT: caixa é o limite duro, não há margem) |
| 22 | `exposure_after` | exposição, exposição por moeda ou exposição em β **após** esta entrada acima do teto — passa por construção, registrado para prova |

## 4. Sizing — mínimo entre os tetos, com o limitante vencedor publicado

**O preço do sizing é o pior entre `entry_ref` e o preço observado — novo em v2.1.** Para um LONG o
pior é o maior. Toda linha abaixo, a perda planejada, o arredondamento por `step_size`, os dois
contrafactuais e a distância de stop (check 8) são medidos em `sizing_price =
max(entry_ref, preço observado)`, que a decisão publica em `sizing.sizing_price` — o `entry_ref`
pedido continua gravado ao lado, sem ser sobrescrito. A garantia é que **o teto nunca fica mais
generoso por causa de um preço velho**: com o mercado acima da referência o motor compra menos
unidades e reconhece a perda maior; com o mercado abaixo, a referência continua valendo. Se essa
diferença é grande o bastante para recusar a proposta é assunto do check 7 (`signal_validity`, §3.1),
não deste módulo.

**Essa garantia vale para o tamanho, não para a geometria do stop — declarado, não escondido.** "Nunca
mais permissivo" é uma frase sobre `qty_final`, e a banda de distância do stop (check 8) é medida no
mesmo `sizing_price`, então ela pode ficar **mais permissiva** quando o mercado se afasta na direção
certa. Exemplo: referência 100, stop 99,8, mercado 100,2 — a distância medida contra `entry_ref` é
0,20 % (abaixo do mínimo de 0,3 % do `paper_v1`, reprovaria), mas medida contra o preço observado
(100,2) é 0,3992 %, dentro da banda. É a mesma medida que o sizing usa para o resto da fórmula; o
contrato registra o comportamento em vez de prometer uma monotonicidade que o `sizing_price` não tem.

O risco planejado inclui custos: a perda no stop é a distância até o stop **mais** os custos estimados
de ida e volta (taxas + slippage estimado), como a diretiva exige.

```
custo_estimado   = fee_entrada + fee_saída + slippage_estimado          (fração do notional)
stop_distance    = |sizing_price − stop| / sizing_price
d_efetiva        = stop_distance + custo_estimado

orcamento_risco  = equity × risk_per_trade_pct                                   (0,25 %)
orcamento_agreg  = equity × max_aggregate_planned_risk_pct − risco_planejado_em_uso   (1 %)
available_cash   = max(0, cash − Σ reserved_cash)                     (§4, "caixa disponível")

qty_by_risk         = min(orcamento_risco, orcamento_agreg) / (sizing_price × d_efetiva)
qty_by_participation= participacao_disponivel / sizing_price         (fórmula única, abaixo)
qty_by_book         = maior qty cuja travessia do book fica em max_slippage_pct
qty_by_exposure     = (max_total_exposure_pct × equity − exposicao_incl_pendentes) / sizing_price
qty_by_asset        = (max_asset_exposure_pct × equity − exposicao_da_moeda) / sizing_price
qty_by_beta         = (max_beta_btc_exposure × equity − Σ|notional_i × β_i|) / (sizing_price × |β|)
qty_by_cash         = (available_cash − taxas_estimadas) / sizing_price

qty_bruta   = min(todos os acima)
limitante   = argmin(...)                          → sizing.binding_constraint   (R-PROV-1)
qty_final   = floor_to_step(qty_bruta × regime_multiplier × ks_multiplier, step_size)
```

`qty_by_beta` com `β = 0` não divide por zero: a contribuição incremental ao teto de β é nula, o teto
não morde, e os outros continuam valendo.

`qty_by_cash` desconta as taxas estimadas: consumir todo o caixa deixaria a taxa sem cobertura.

**Caixa disponível é líquido das reservas — novo em v2.1.** `available_cash = max(0, cash − Σ
reserved_cash)`, e cada reserva pendente carrega o seu **próprio** `reserved_cash` — o espelho de
`trade_proposals.reserved_cash` (T3.1), recebido pelo motor como dado imutável da reserva, nunca
recalculado por este módulo. O `PendingEntry` recusa `reserved_cash < reserved_notional` na
construção: no SPOT o caixa que uma compra segura é o notional mais as taxas, nunca menos. O teto de
caixa (check 21, §3.2) passa a publicar `limit = available_cash` (na v2 publicava `max_leverage = 1`,
que não é um número de dinheiro e não dizia nada à Explanation Panel). Antes da v2.1 o teto de caixa
era o único que ignorava as reservas pendentes (caixa 500, 400 já reservados, aprovava outros 499,5 —
900 comprometidos contra 500) e, na primeira correção, reestimava a reserva alheia com o multiplicador
de custo da proposta **candidata** — um candidato que declarasse custo zero encolhia o compromisso de
quem já havia reservado. As duas falhas estão fechadas: o caixa que uma reserva segura nunca encolhe
por causa da próxima candidata.

**`tied_limits` — desempate estável, novo em v2.1.** Quando dois ou mais tetos empatam no mesmo valor,
o vencedor é o primeiro na ordem declarada de `CAP_ORDER` (`requested`, `risk_per_trade`,
`aggregate_risk`, `market_participation`, `book_depth`, `asset_exposure`, `total_exposure`,
`beta_exposure`, `cash`) — nunca a ordem de iteração do dicionário nem uma escolha implícita do
runtime. `sizing.tied_limits` publica os nomes dos outros tetos empatados, para a Explanation Panel
não esconder que a decisão poderia ter citado outro limitante.

**Janela da referência de volume.** Com `t = floor_minute(as_of)`: o último minuto completo é
`[t−1m, t)` e a mediana é das 30 barras completas `[t−30m, t)`.
`volume_referencia = min(quote_volume[t−1m, t), median(quote_volume das 30 barras))`. Barra ausente é
**indisponibilidade** (check `unavailable` → rejeita), nunca zero e nunca mediana de janela reduzida.

**Orçamento agregado de participação (F6).** O teto não é por ordem, é por mercado e por escopo de
capital, compartilhado por todos os agentes e pela ordem manual, consumido em **janela móvel de 60 s**
a partir de `as_of`:

```
participacao_disponivel = max(0, max_participation_pct × volume_referencia
                                 − consumo_executado_60s − reservas_ainda_executaveis)
```

**Esta é a única fórmula de participação do contrato.** Não existe uma versão "sem consumo": o teto
por ordem isolada seria exatamente o fracionamento que a diretiva proíbe. A chave do orçamento é
`(market_id, escopo_de_capital)`, com o escopo definido na §11.

É assim que "**não fracionar ordens para contornar limites**" vira mecanismo e não frase: duas ordens
de 0,8 % cada não passam isoladamente porque a segunda encontra o orçamento já consumido pela
primeira. Cancelar libera só a parcela **não executada**; um retry não reinicia o orçamento; a virada
do minuto não perdoa consumo ainda dentro da janela de 60 s. Se a referência cair antes do fill, a
entrada pendente é revalidada contra o teto novo — e execuções passadas nunca são desfeitas para a
soma caber. Saídas de proteção **não** consomem este orçamento.

`entry_ref` = meio da `entry_zone`, ou o último preço se ele estiver dentro da zona — calculado por
quem monta a proposta, antes do Risk Engine. O motor recebe esse número, nunca o recalcula, e usa
`sizing_price` (acima) em toda a aritmética; os dois ficam publicados lado a lado na decisão.

**Os multiplicadores agem sobre o tamanho final (R-KS-1).** No v1 eles multiplicavam o orçamento de
risco, e a redução prometida pelo §5 não era garantida: com stop estreito, outro teto vencia e a
posição saía do mesmo tamanho. No v2 a garantia é estrutural e testada:
`multiplicador ≤ 1 ⇒ qty_final ≤ qty_bruta`, e `ks = 0,5 ⇒ qty_final ≤ ⌊qty_bruta/2⌋` no passo.
Depois do arredondamento o `min_notional` é revalidado: se o tamanho reduzido não chega ao mínimo
negociável, a proposta é **rejeitada** — nunca arredondada para cima.

A decisão grava, para a mesma proposta e o mesmo estado, cada teto calculado com o seu valor, qual
venceu, e **dois contrafactuais distintos, que nunca podem ser reportados como um só**:

| Contrafactual | O que responde |
|---|---|
| `size_without_multipliers` | o tamanho que sairia sem o multiplicador de aviso e o de regime (R-KS-2) — mede o degrau do kill switch |
| `size_without_participation` | o tamanho que sairia se o teto de participação não existisse — mede quanto a regra 3 da diretiva está mordendo |

Confundi-los produziria a frase errada nos dois sentidos. É o segundo que responde "em quantos
mercados a participação foi o limitante, e qual seria o tamanho sem ela" — a pergunta 3 ao Everton.
Quando o insumo do contrafactual está indisponível, ele é **nulo com motivo**, nunca zero.

## 5. Kill switch

Escopos: **sistema**, **organização**, **portfolio**. Estado efetivo = o máximo pela ordem
`ACTIVE < WARNING < TRADING_DISABLED < EMERGENCY`.

**Unidade: USDT operacional.** O kill switch decide sobre o patrimônio em USDT; o BRL é exibido ao
lado. Se ele decidisse em BRL, uma variação do câmbio sozinha bloquearia a carteira sem nenhuma
operação ruim. Esta é uma convenção nossa — a diretiva não a define —, e está na lista de perguntas
ao Everton (`docs/plans/M3.md`, pergunta 8).

**Dia de negociação em `America/Sao_Paulo`.** O início do dia é 00:00 no fuso, convertido para UTC e
gravado (`trading_day`, `trading_day_start_utc`, com o instante real da avaliação); todo o resto do
sistema continua em UTC. A referência diária é **persistida**: depois de um restart o motor não usa o
primeiro preço que vir como equity da meia-noite, e sem conseguir reconstruí-la o estado fica
indisponível — entradas novas bloqueadas, proteções preservadas.

```
perda_diaria_pct = max(0, 1 − equity / equity_inicio_dia)
drawdown_pct     = max(0, 1 − equity / peak_equity)
```

Ambas sobre o **patrimônio total**, incluindo posições abertas marcadas a mercado e custos. **Pico
histórico** (`peak_equity`) é monotônico, só sobe, **nunca é resetado**, e é um pico **amostrado**, com
a cadência declarada — não é o máximo intratick, e o contrato diz isso em vez de fingir precisão.

**A perda do dia vem do patrimônio, sempre — declarado na v2, provado na v2.1.** A fórmula acima não é
opcional nem tem fallback: `daily_realized_pnl`, `daily_unrealized_pnl` e `daily_costs` são **apenas de
relato**, e nada no motor decide com eles. A revisão adversarial de 2026-09-06 (bloqueante 1)
reproduziu o buraco que isso fecha: patrimônio de abertura 20.000, agora 19.500 (−2,5 %), campos de
PnL do dia vazios → o check `daily_loss` reportava `PASSED value=0` e aprovava entrada em tamanho
cheio, com o teto de bloqueio de 2 % já rompido. Quando os três campos chegam preenchidos, a
divergência entre eles e o movimento do próprio patrimônio é publicada em
`PortfolioState.daily_decomposition_gap` — **e nunca bloqueia**: exigir que a decomposição bata para
construir o estado tornaria um descasamento contábil de poucas casas decimais capaz de impedir a
construção do `PortfolioState` e, com ela, a saída de proteção que depende dele — exatamente o que a
regra 3 da diretiva proíbe. O `daily_decomposition_gap` existe para a reconciliação da T3.3 medir, não
para este motor punir.

| Estado | Entradas | Saídas | Gestão de posições | Aciona |
|---|---|---|---|---|
| `ACTIVE` | permitidas | normais | normal | — |
| `WARNING` (AVISO) | permitidas com **tamanho final × 0,5** | normais | normal | perda do dia ≥ 1 % **OU** drawdown ≥ 4 % |
| `TRADING_DISABLED` (BLOQUEADO) | bloqueadas; **pendentes canceladas** | permitidas | continua, com proteções ativas | perda do dia ≥ 2 % **OU** drawdown ≥ 8 % |
| `EMERGENCY` | bloqueadas | permitidas | só saídas | manual (OWNER/ADMIN) |

Em `TRADING_DISABLED` **não há liquidação automática**: as posições continuam sendo geridas, os stops
e alvos continuam valendo. A retomada é **sempre** manual e autorizada pelo Everton, auditada em
`kill_switch_transitions` — o v1 permitia `WARNING → ACTIVE` automático no novo dia UTC; o v2 não
permite nenhuma volta automática a partir de `TRADING_DISABLED`.

**`resume` recusa retomar enquanto a avaliação automática ainda bloqueia — novo em v2.1.** O núcleo
puro (`hunter_risk.kill_switch.resume`) exige a avaliação automática do instante do ato: se
`daily_loss` ou `drawdown` ainda estão sobre o limiar de bloqueio, a retomada é **recusada** em vez de
gravada como uma transição que a próxima avaliação desfaria no minuto seguinte — o registro de uma
transição que não muda nada é pior no log do que transição nenhuma (revisão de 2026-09-06, item 5). A
trava durável (a coluna que guarda o estado entre avaliações), a transição auditada e a autenticação
de que é de fato o Everton continuam sendo donas da **T3.6** — o núcleo puro só nega o destravamento
quando ele nasceria já invalidado; ele não persiste nada e não autentica ninguém.

**`evaluate_exit` funciona sem `PortfolioState` — novo em v2.1, achado pela Astra na 2ª rodada da
revisão.** `evaluate_exit(proposal, position, limits, kill_switch, *, portfolio=None)` recebe a
**posição** como argumento obrigatório e o estado da carteira como opcional. O cenário que exige isso:
um restart depois da meia-noite de São Paulo, em que o worker reconstrói a posição a partir do
Postgres muito antes de reconstruir a âncora do dia — e `PortfolioState` não se constrói sem
`day_start_equity` e sem `day_start_utc` validado contra `as_of` (§1). Com a assinatura antiga, o stop
de uma posição já existente esperaria por um número que só limita **entradas**, ou o chamador
inventaria um. Quando o estado da carteira está disponível, ele é usado e a avaliação automática do
kill switch entra na decisão como de costume; **sem ele, o kill switch registrado na saída é o mais
restritivo das travas persistidas** (sistema, organização, portfolio) — as escadas automáticas de
perda e drawdown só *sobem* o estado e não são mensuráveis sem patrimônio, então usar só as travas
persistidas nunca é mais permissivo que a avaliação completa. A mensagem do check diz "sem estado da
carteira", para a proveniência não fingir uma avaliação que não rodou.

**Quantidade vendável é o mínimo entre a posição e a visão da carteira.** Quando `portfolio` chega,
`evaluate_exit` toma `min(qty da posição entregue, qty da posição na carteira)`: depois de uma saída
parcial de 6 unidades, a carteira pode já mostrar 4 enquanto o objeto de posição entregue ainda diz
10, e vender 10 no SPOT venderia unidades que não existem. A divergência **nunca recusa a saída**; ela
só reduz a quantidade aprovada, com o clamp registrado no `ExitPlan`.

Transições para cima são imediatas. Cada transição publica `kill_switch.changed`; os workers reagem
em < 1 s e releem o estado do Redis a cada 10 s.

**O estado durável é a autoridade; o Redis e o evento são projeções.** Ler o cache e depois gravar o
efeito não satisfaz o contrato: a releitura do estado efetivo acontece **na mesma transação que
aplica o efeito de entrada**, com ordem fixa de aquisição de travas — **sistema → organização →
portfolio**. O cenário que isso fecha: o worker lê `ACTIVE`, outra sessão commita `TRADING_DISABLED`
na organização, e o fill entra depois porque os dois nunca disputaram trava nenhuma. Teste
obrigatório em duas sessões reais.

Aprovação antiga não é salvo-conduto: antes de **cada** efeito de entrada o motor relê decisão
válida, reserva, kill switch efetivo e condições de execução.

## 6. β contra o BTC, versionado e com validade

A diretiva é dura: *"sem beta validado, manter o ativo apenas em shadow"*. O β não é feature do M2 e
não existe em código hoje (KB-0071). O contrato:

- Série imutável (`market_betas`, só INSERT): `market_id`, identidade da referência, `window_start`,
  `window_end`, estimador, tipo de retorno, `n_returns` (retornos efetivamente **pareados**, não
  fechamentos), cobertura, `computed_at`, `available_at`, `valid_until`, `algo_version`, motivos de
  invalidez.
- Calculado **fora** do Risk Engine (o motor é puro) e entregue como argumento.
- **Admissão de uma revisão** exige as três condições, juntas: `available_at <= as_of` (uma revisão
  conhecida só depois não reexplica uma decisão anterior), janela **encerrada** até o corte, e prazo
  ainda válido. `valid_until` é ancorado em `window_end`, **não** no relógio do cálculo — recalcular
  hoje uma janela que termina ontem não renova prazo nenhum.
- Retornos horários pareados contra o BTC na mesma exchange e moeda de cotação, barras completas, sem
  preencher lacuna e sem tratar retorno multihorário como se fosse de uma hora.
- O check é `unavailable` quando falta β válido do **candidato, de qualquer posição aberta ou de
  qualquer reserva** — um β vencido não pode sumir da soma agregada. Isso impede **entradas novas**;
  a gestão e a saída das posições existentes continuam.
- BTC tem β = 1 **por identidade**, com os diagnósticos estatísticos marcados como não aplicáveis —
  nada de R² empírico inventado. β = 0 válido não divide por zero (§4).
- Preencher os campos **não** é "beta validado": o protocolo numérico (estimador, janela, cobertura
  mínima, duração da validade) é congelado e revisado pelo quant **antes** do primeiro uso, e não há
  corte de R² escolhido agora.
- **Consequência a declarar, não a esconder:** enquanto a cobertura histórica não existir, poucos
  mercados terão β válido e a carteira abrirá pouco. Quantos, exatamente, é medição — não afirmação.
  Isso é a regra do Everton funcionando, não um defeito.

O check usa **módulo** (`Σ|notional × β|`): com soma assinada, duas pernas opostas de β 1 zeram a
medida e ainda assim perdem nas duas.

## 7. Falhar fechado (R-OPS-1)

Cada check declara o seu insumo e o que fazer quando ele falta. O padrão é **rejeitar**, e o estado
`unavailable` é distinto de `failed` para que a proveniência não minta: "reprovado por não caber" e
"não avaliado por falta de dado" são coisas diferentes na tela e na consulta.

Os insumos com idade máxima declarada (R-OPS-2): preço, book, volume de 24 h, volume do minuto, β,
estado do universo, continuidade de coleta. Nenhum vale "para sempre".

Esta é a única regra do contrato cuja ausência transforma degradação em aprovação silenciosa: sem
ela, o book some no estresse e a proposta é aprovada sem estimativa de slippage exatamente no
momento em que o slippage explode.

## 8. Risk events e garantias

Tipos: `limits_changed`, `proposal_rejected`, `proposal_unavailable_input`, `daily_loss_warning`,
`daily_loss_limit`, `drawdown_warning`, `drawdown_limit`, `exposure_limit`, `participation_capped`,
`beta_missing`, `data_degraded_in_position`, `kill_switch_changed`, `stop_slippage_excess`,
`position_stale_price`. Severidade `info | warning | critical`; `critical` notifica OWNER/ADMIN e vai
ao Sentry.

- Nenhum caminho de código cria `orders` de entrada sem `proposal_id` com `risk_decision.approved = true`.
  Ordens de saída são sempre permitidas.
- Ordem manual paper também gera uma `trade_proposal` (`agent_id` nulo, `actor=user`) e passa pelos
  mesmos checks.
- O motor nunca chama rede nem banco: tudo chega como argumento, o que o torna testável por tabela
  de casos e reutilizável no backtest.
- LLM não tem acesso ao Risk Engine nem aos limites.
- `ENABLE_LIVE_TRADING=false`. O adaptador live levanta `LiveTradingDisabled`.
- **`float` é recusado na construção de todo insumo do motor** (`hunter_risk.base.RiskModel`, todo
  valor money/limite): `Decimal("0.1") != Decimal(0.1)`, e o pydantic converte um `float` para
  `Decimal` sem reclamar, então o erro (um limite que é `0,10000000000000000555…` da equity) nunca
  falha um teste nem aparece num log — a proibição é imposta na construção, não na revisão.
  **Exceção pendente, fora do escopo desta tarefa:** `AssumedCosts`
  (`packages/core/hunter_core/strategies/envelope.py:45`) herda de `_Frozen`, não de `RiskModel`, e
  aceita `float` em `spread_bps`/`slippage_bps`/`fee_bps` — o cenário que expõe o problema é
  `0.1 + 0.2 = 0.30000000000000004` sobrevivendo à conversão para `Decimal` sem erro. `AssumedCosts` é
  dono do `packages/core` (envelope do Shadow Lab, não deste pacote); o `risk-engine-guardian`
  registrou a pendência em `.claude/state/notes-T3.2-risk-core.md` §"Pendência fora do meu escopo" e
  ela segue aberta para quem tocar `packages/core` a seguir.

## 9. O que mudou em relação ao v1, e por quê

| # | v1 | v2 | Por quê |
|---|---|---|---|
| 1 | `risk_per_trade_pct` era a base do sizing, mas **nunca atuava**: os limiares implícitos (12,5 / 10 / 10 %) ficam acima do `max_stop_distance_pct` de cada perfil (3 / 5 / 8 %), então o check de distância reprovava antes e o risco bruto no stop ficava 6 a 8× abaixo do rótulo | 0,25 % é o teto declarado e entra no mínimo junto com os outros; o limitante vencedor é gravado e publicado | KB-0066: o rótulo do contrato não descrevia o comportamento. Sem publicar o limitante, "risco de 0,25 % por operação" é frase que nenhum dado pode contrariar (R-PROV-1) |
| 2 | Multiplicadores (`ks`, regime) multiplicavam o **orçamento de risco** — o §5 prometia "tamanho × 0,5" e o §4 não garantia | Multiplicam o **tamanho final aprovado**, antes do arredondamento, com revalidação do mínimo | KB-0072: a redução acontecia em algumas combinações de perfil/regime e não em outras, e quem decidia era a distância do stop. R-KS-1 |
| 3 | Nada distinguia "reprovado" de "não avaliado" | Estado `unavailable`, padrão rejeitar, idade máxima por insumo | R-OPS-1/R-OPS-2. O contrato v1 não dizia o que fazer quando o book (que vive 10 s e nunca é gravado) faltava no check 18 |
| 4 | `correlation` por `beta > 0.8` contando posições | Exposição agregada em β **em módulo**, teto 0,5× do patrimônio | KB-0071: o critério marcava 147 de 232 mercados, `\|ρ\|` mediana entre pares 0,062, nenhum par acima de 0,8 — ele confundia escala de volatilidade com co-movimento |
| 5 | Sem teto de participação | `max_participation_pct` com referência declarada (mínimo entre o último minuto completo e a mediana de 30) | Regra 3 da diretiva. R-CAP-2 |
| 6 | Sem risco agregado | `max_aggregate_planned_risk_pct` = 1 %, contando posições **e** pendentes | Regra 2 da diretiva |
| 7 | Dia em UTC; `WARNING → ACTIVE` automático no novo dia | Dia em `America/Sao_Paulo`; nenhuma volta automática a partir de `TRADING_DISABLED`, retomada só com autorização | Regra 5 da diretiva |
| 8 | `max_leverage` 1/2/3, margem | SPOT, `max_leverage = 1`, caixa é o limite duro | Regra 6 da diretiva. KB-0073: o controle efetivo nunca vinha do `max_leverage` |
| 9 | Sem checks operacionais de lacuna e universo | `market_gap` e `market_in_universe` | R-OPS-3 (34 de 232 mercados com lacuna em 24 h) e R-OPS-4 (27 sinais em 14 mercados desmonitorados em 15 h) |
| 10 | Três presets genéricos | Preset `paper_v1` com os valores do Everton; os três antigos continuam existindo e não são o perfil da carteira | A diretiva nomeia valores, não perfis |

O que **não** mudou: a gramática de `regime_size_multiplier` (§2.1), a pureza da função, a estrutura
de `risk_decision.checks[]`, os `risk_events`, e as garantias da §8.

### 9.1 Matriz dos controles do v1

"Nenhum controle foi removido" é frase vaga demais para um contrato — cada um tem um destino
declarado, e nada de margem, futuros ou preset mais permissivo entra de carona.

| Controle do v1 | Destino no v2 |
|---|---|
| `kill_switch`, `portfolio_status`, `data_quality`, `signal_validity`, `stop_distance`, `spread`, `duplicate_position`, `slippage_estimate`, `cash` | **mantidos**, com insumo e idade declarados |
| `max_position_pct` | **substituído** por `max_asset_exposure_pct` (10 %) e pelo teto de participação — a diretiva não define teto por posição isolada |
| `risk_per_trade_pct` | **substituído** pelo valor da diretiva (0,25 %) e agora atua de fato (§9, item 1) |
| `max_daily_loss_pct`, `max_drawdown_pct` | **substituídos** pelos dois pares de limiares do kill switch (1 %/4 % e 2 %/8 %) |
| `max_total_exposure_pct`, `max_concurrent_positions`, `max_asset_exposure_pct`, `min_liquidity_usd_24h` | **substituídos** pelos valores da diretiva (40 %, 5, 10 %, 50 M) |
| `correlation` por `beta > 0.8` | **substituído** pela exposição agregada em β em módulo (0,5×) |
| `max_leverage` | **mantido com valor 1**; margem, empréstimo, short e futuros são **inaplicáveis** nesta etapa |
| `max_exchange_exposure_pct` | **inaplicável** enquanto houver uma exchange de execução; volta a valer no M1b |
| `auto_close_on_emergency` | **mantido em `false`**; a diretiva proíbe liquidação automática |
| Presets `conservative`/`balanced`/`aggressive` | **continuam existindo e não são o perfil da carteira**; nada neles pode elevar os limites do `paper_v1` |

### 9.2 O que mudou da v2.0 para a v2.1, e por quê

A v2 já **descrevia** a zona de entrada, a idade máxima do volume e a exclusão das reservas do caixa.
A revisão adversarial da T3.2 (`.claude/state/review-T3.2-risk-core.md`, `bf4924b` → `5f86028`) achou
que o núcleo implementado não cumpria três dessas promessas; a v2.1 fecha o contrato no que o código
passou a fazer, sem mudar nenhum limite do Everton.

| # | v2.0 (texto) | v2.1 (código provado) | Achado bloqueante |
|---|---|---|---|
| 1 | `entry_ref` da proposta nunca era confrontado com o mercado; a "zona de entrada" do check 7 não tinha número no perfil | `max_entry_deviation_pct = 0,005` publicado em §2; `signal_validity` reprova fora da banda, com o stop também confrontado contra o preço observado (não só contra `entry_ref`); o sizing usa `sizing_price = pior(entry_ref, observado)` | Achado 2: `entry_ref = 100`, stop 97,5, mercado a 110 — aprovado, com notional registrado 1.851,80 contra gasto real 2.036,98 e perda real no stop de 1,18 % da equity contra o teto de 0,25 %; e um LONG com stop acima do mercado (90) também aprovado |
| 2 | `max_volume_age_s` existia como campo do perfil (§7, R-OPS-2) mas nunca era lido | `liquidity_24h` e `participation` viram `unavailable` quando o volume (minuto ou 24 h) tem idade > 120 s, sem carimbo, ou carimbo no futuro | Achado 3: volume do minuto observado 45 minutos antes do `as_of` sustentando o teto de participação como se fosse agora |
| 3 | o teto de caixa (§3.2 check 21) não descontava as reservas pendentes | `available_cash = max(0, cash − Σ reserved_cash)`, com cada reserva carregando o seu próprio `reserved_cash`; o teto publica `limit = available_cash`, não mais `max_leverage` | Achado 4: caixa 500 com 400 já reservados aprovava outros 499,5 — 900 comprometidos contra 500 |

Junto com os três achados bloqueantes, a v2.1 registra três decisões que **DEVE CORRIGIR**/sugestões da
mesma revisão: `resume` recusa retomar enquanto a avaliação automática ainda bloqueia (§5); `tied_limits`
tem desempate estável por `CAP_ORDER` (§4); e `evaluate_exit` funciona sem `PortfolioState`, com a
quantidade vendável como o mínimo entre a posição entregue e a da carteira (§5) — este último não veio
da revisão original, mas de uma segunda e uma terceira rodada da Astra sobre o mesmo diff.

## 10. Saídas: tentativa e intenção não são a mesma coisa

Esta distinção é do fechamento com a Astra e evita um defeito que a primeira redação teria criado.

- **Entrada:** uma tentativa contra o livro elegível; o que não foi preenchido é **cancelado em
  definitivo**. Não existe parcelamento automático — se um dia existir, será política explícita com
  prazo e reserva da ordem inteira, nunca comportamento implícito.
- **Saída de proteção:** cada tentativa também termina, mas a **intenção durável permanece** para a
  quantidade remanescente, com novas tentativas em livros elegíveis, identidade própria e sem duplicar
  consumo. Só termina quando a quantidade pretendida foi liquidada ou houve substituição explícita e
  auditada da intenção. Quantidade abaixo do mínimo negociável fica como **resíduo contabilizado e
  impedimento visível**, sem quitação fictícia.

O cenário que isso evita: um stop de 10 unidades encontra 4 vendáveis; se o cancelamento do restante
encerrasse a intenção, 6 unidades ficariam abertas sem proteção, inclusive depois de um restart.

Stop, alvo e fechamento manual concorrentes **compartilham a quantidade vendável sob o mesmo lock** —
não podem vender a mesma unidade duas vezes, o que preserva SPOT sem short. Falta de livro utilizável
não fabrica fill: a saída fica pendente, marcada degradada, com alerta, e executa a quantidade
demonstrável quando houver dado.

## 11. Escopo de capital

O escopo é `(organization_id, workspace_id, type=paper, is_arena=false)`: **uma** carteira principal
permanente por workspace, garantida por índice único parcial no banco. O orçamento de participação
(§4) tem chave `(market_id, escopo_de_capital)` e é compartilhado por todos os agentes e pela ordem
manual dentro do escopo.

Com uma principal por escopo, a trava dessa carteira serializa o orçamento. **Se um dia houver mais
de uma carteira consumindo o mesmo escopo, uma trava própria do orçamento passa a ser pré-requisito**
— isso é condição escrita, não suposição.

A permanência é parte do contrato: a unicidade vale também para carteira pausada ou arquivada (o
predicado não depende de `status` nem exclui `deleted_at` preenchido), e os campos que tirariam a
carteira do escopo não podem ser alterados para liberar uma abertura nova. Transferi-la para outro
workspace, transformá-la em arena ou trocar o workspace para oferecer um recomeço é a mesma
substituição que a diretiva proíbe quando proíbe reset.

