# Risk Engine MEME — contrato v0.1 (pump.fun / Solana)

**Status: contrato proposto, escrito ANTES do código. Nenhum número aqui está aceito como limite.**

**Versão 0.1, 2026-09-12.** Irmão de `docs/RISK_ENGINE.md` (v2.5, SPOT) para a classe de ativo que
o Everton apontou em 2026-09-12: moedas da bonding curve do pump.fun, numa carteira Solana nova,
exclusiva do Hunter. Ele pediu para "começar a operar ainda hoje nessa carteira". A resposta honesta
está na §0 e é a primeira coisa que ele lê: **hoje só existe papel e radar**. A primeira transação
assinada de verdade depende de um fluxo verificado (a diretiva dele de 2026-09-06: *"só declare o
modo autônomo pronto quando o fluxo completo estiver verificado"*), da chave que só ele digita no
`.env` da VPS, e de um interruptor que só ele liga.

**O que este documento é:** o contrato de risco e execução da classe meme — escopo, insumos, checks
com nome de recusa, sizing, kill switch, caminho de execução com modelo de confiança, as nove
verificações equivalentes às da T3.9, e a definição de "fluxo completo verificado" que destrava
dinheiro real.

**O que este documento não é:** não é código, não cria nada em `packages/`, não altera `hunter_risk`
(§13), não contém chave nenhuma e não toca `.env*`. Também **não é uma tese de que comprar cedo na
curva dá lucro** — isso é hipótese pré-registrada (EXP-M1, T4.5), julgada por evidência. Um motor de
risco seguro não torna a hipótese verdadeira.

**Proveniência:** todo número de protocolo/taxa citado aqui foi lido por mim ao vivo nesta sessão
(§15, com URL e a hora do cabeçalho `Date` do servidor) ou vem de `docs/PUMPFUN-ONCHAIN.md` (T4.0d,
IDL oficial no commit `9c82f61`), `docs/plans/T4-MEME-RADAR.md`,
`.claude/state/astra-review-t40-pumpfun.md`, `.claude/state/notes-T4.0*.md` e
`.claude/state/notes-T4.1.md`. Onde não confirmei, está escrito "não confirmado".

---

## 0. A posição do dono e o que "hoje" pode ser

Três frases, na ordem em que valem:

1. **O Hunter não assina transação real nenhuma antes do fluxo completo verificado** (§12). Não
   existe atalho, nem "só uma de teste com 0,01 SOL": transação assinada é dinheiro do Everton
   saindo, e o critério de liberação é dele.
2. **A chave privada vive só no `.env` da VPS, digitada por ele** (§3.3). Nenhum agente, nenhum log,
   nenhuma métrica, nenhum chat, nenhum commit. O processo que a lê é um só, e ainda não existe.
3. **Dinheiro real exige um interruptor explícito que só ele liga** (`ENABLE_MEME_LIVE_TRADING`,
   §3.4); ligá-lo com as verificações vermelhas é **recusado pelo processo**, não é escolha de
   operação.

**O que "operar hoje" pode significar sem mentir:** carteira de papel sobre dados reais da curva (o
simulador da T4.5 com os snapshots da T4.1/T4.2) e o radar (T4.3). O que **não** pode: assinar,
enviar ou manter posição on-chain. Os motivos são verificáveis, não pudor:

| Falta hoje | Consequência |
|---|---|
| o pacote de risco meme (`hunter_risk_meme`) não existe | não há função que decida uma compra; não existe "aprovado" para gravar |
| o coletor (T4.2) não existe | não há volume do minuto, `top10_share`, `bundled_share` nem fluxo do criador — os checks 10, 11, 12 e 21 saem `unavailable` e **recusam tudo** (§4) |
| o feed de trades é pago e não foi decidido (0,01 SOL / 10.000 eventos) | mesma consequência; sem ele o motor honesto aprova **zero** compras (§14, pergunta 6) |
| as nove verificações meme (VM1–VM9, §11) não existem | não há prova de caps, kill switch, idempotência e restart |
| `ENABLE_MEME_LIVE_TRADING` não existe no código | verificado nesta sessão: `grep` não acha a variável em nenhum arquivo do repo (§15) |

> **Estado em 12/09/2026, fim do dia (T4.8 + T4.14):** as cinco linhas acima mudaram de lado —
> `hunter_risk_meme` existe (§13), o executor existe (`services/meme-executor`), a flag existe e VM1–VM5/VM7
> passam; VM6(c) e as metades Postgres de VM8/VM9 correm no testcontainer do executor. O que **não** mudou é
> a frase 1: nenhuma transação real foi assinada, os Portões A e B seguem vermelhos, e "operar hoje"
> continua sendo papel + radar até ele decidir o teste pequeno por escrito (§12, variante) e digitar o
> que só ele digita (`docs/ACTIVATION.md` §9b). Os checks 10, 11, 12 e 21 continuam a recusar todo mint
> que o radar não mediu — hoje, `bundled_share` em todos.

## 1. Escopo — o que pode ser tocado, e nada além

**Só três ações existem neste contrato:** comprar na bonding curve, vender na bonding curve, vender
no pool canônico do PumpSwap depois da migração. Mais nada.

| Programa | Endereço | O que este contrato permite |
|---|---|---|
| Pump (bonding curve) | `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P` | `buy`/`buy_v2` e `sell`/`sell_v2`, da nossa carteira, no mint da nossa posição |
| PumpSwap (Pump AMM) | `pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA` | **só `sell`** — sair de uma posição que migrou |
| Pump Fees | `pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ` | nenhuma instrução nossa; entra como conta obrigatória (`fee_config`) das instruções acima |
| Mayhem | `MAyhSmzXzV1pTf7LsNkrNwkWKTo4ougAJ1PPg47MD4e` | **leitura apenas** — nunca alvo de instrução nossa (§8.3) |
| qualquer outro programa | — | recusa nomeada `program_not_allowed` |

Endereços e instruções conforme `docs/PUMPFUN-ONCHAIN.md` §0/§1.3/§2.3.

**Proibições, cada uma com o nome da recusa:**

| Proibido | Recusa | Por quê |
|---|---|---|
| alavancagem, empréstimo, margem, short | `leverage_not_supported` | a mesma regra 6 da diretiva que fixa `max_leverage = 1` no SPOT; numa curva, short nem existe |
| comprar com a curva completa (`complete = true`) | `curve_complete` | o preço deixa de ser esta fórmula |
| comprar no PumpSwap | `pumpswap_buy_not_allowed` | o PumpSwap entra só como **porta de saída** de quem migrou com posição aberta |
| criar moeda (`create`/`create_v2`) | `token_creation_not_allowed` | criar é ser o criador que o próprio radar vigia |
| quote ≠ SOL (USDC **já é** quote real — `Global.whitelisted_quote_mints`, T4.0d §7) | `unsupported_quote` | mesmo vocabulário da T4.2/T4.3; caps e simulador são em SOL |
| moedas de outro launchpad no mesmo WS (`pool="bonk"` etc.) | `foreign_launchpad` | `normalize.py` já recusa montar o modelo pump.fun para outro pool (`notes-T4.1.md`) |
| bundle com mais de uma carteira nossa | `multi_wallet_bundle_not_allowed` | é o padrão de bundler que os checks 11 e 12 vigiam nos outros; não o imitamos |
| `collect_creator_fee`, `claim_cashback`, incentivos de volume | `not_in_scope` | não somos criadores e não caçamos incentivo |

**A ordem obrigatória é papel primeiro.** A curva é uma fórmula determinística (§10) — dá para
simular o fill com honestidade, o que o livro SPOT nunca permitiu sem livro real. O caminho live só
é construído depois que o simulador provou as VM1–VM9.

## 2. Insumos — puros, carimbados, sem relógio próprio

A decisão é **pura e determinística**, como `hunter_risk.evaluate`: sem rede, sem banco, sem
relógio. O instante é `wallet.as_of`, e toda idade é medida contra ele. Nomes propostos (o pacote
não existe — §13):

```
evaluate_meme_entry(proposal, wallet, limits, curve, context, kill_switch) -> MemeDecision
evaluate_meme_exit(proposal, position, limits, kill_switch, *, wallet=None) -> MemeDecision
```

`evaluate_meme_exit` recebe a **posição** e não exige a carteira, pela mesma razão da §5 do contrato
SPOT: depois de um restart o executor reconstrói a posição muito antes da âncora do dia, e **trava
de entrada não pode impedir saída** (regra 3 da diretiva).

| Insumo | Campos (proposta) |
|---|---|
| `MemeEntryProposal` | `proposal_id, wallet_id, agent_id?, mint, program, quote, action="buy", requested_sol` (teto, nunca meta), `max_slippage_pct, priority_fee_sol, jito_tip_sol, exit_plan, signal_valid, agent_enabled, mode` (`paper` \| `live`) |
| `CurveState` | `mint, virtual_sol_reserves, virtual_token_reserves, real_sol_reserves, real_token_reserves, total_supply, complete, creator, is_mayhem_mode, slot, commitment, observed_at, source` |
| `MemeContext` | `token_age_s` (com a procedência de `created_at`), `curve_progress_pct, organic_last_minute_sol_volume, volume_window_complete, unique_buyers_1m?, bundled_share_pct?, top10_share_pct?, holder_denominator_valid, creator_net_sol?, mayhem_agent_share?, rug_signals[], participation_used_sol` — **um carimbo por campo** |
| `MemeWalletState` | `wallet_id, as_of, sol_balance, unrecognized_holdings, positions[], pending_intents[], day_start_sol_equity, peak_sol_equity, day_start_utc` (validado contra o dia de São Paulo), `daily_realized_loss_sol, marks_complete, is_active`; deriva `equity_sol, exposure_for_mint(), available_sol, slots_used, daily_loss_sol, drawdown_pct` — **sempre calculados aqui**, nunca recebidos prontos |
| `MemeLimits` | o perfil da §3 |
| `MemeKillSwitchInputs` | `system, organization, wallet` → efetivo = o mais restritivo (§7) |

**Regras de insumo herdadas sem discussão do contrato SPOT:**

- **`float` é recusado na construção** de todo campo de dinheiro/limite (disciplina de
  `hunter_risk.base.RiskModel`). Aqui pesa mais que no SPOT: o WS do PumpPortal manda reservas como
  **float JSON** (`notes-T4.1.md` registra o teste que barrou o arredondamento), e o `normalize` é o
  único lugar onde a conversão acontece.
- **Insumo ausente, vencido ou degradado não vira zero nem média:** vira `unavailable`, e
  `unavailable` **reprova** (§4).
- **Todo carimbo carrega `slot` e `commitment`.** Numa cadeia "quando" tem duas respostas (parede e
  slot), e uma leitura `processed` pode ser revertida (§8.2).
- **`observed_at` nunca é o `now` do ciclo** — é o instante da leitura que produziu o número. É a
  mesma correção que a v2.5 do contrato SPOT fez no `volume_ts`.

## 3. A política da carteira — e a separação entre política e parâmetro

**Duas famílias de número, donos diferentes, e confundi-las seria a fraude deste contrato:**

| Família | Quem decide | Exemplos |
|---|---|---|
| **Política de capital** — quanto pode ser perdido | **só o Everton**, como os valores do `paper_v1` | `MEME_WALLET_MAX_SOL`, `MEME_MAX_SOL_PER_TRADE`, `MEME_DAILY_LOSS_CAP_SOL`, nº de posições, exposição por token, teto de priority fee, teto de tip |
| **Parâmetro de estratégia** — o que se acredita sobre o mercado | a hipótese pré-registrada (EXP-M1, T4.5), revisável por evidência | idade, janela de progresso, múltiplo-alvo, trailing, time stop, limiares de bundled/top-10 |

Os valores da coluna "papel" abaixo são **parâmetros de um experimento em papel**, nunca limites
aprovados. A coluna "live" fica vazia de propósito: **nenhum número de dinheiro real existe até o
Everton escrever o dele** (§14).

### 3.1 Perfil `meme_paper_v0`

| Chave | Papel (proposta, revisável sem tocar dinheiro) | Live | O que é |
|---|---|---|---|
| `profile` | `"meme_paper_v0"` | — | identidade do preset |
| `MEME_WALLET_MAX_SOL` | `2.0` | **a decidir** | teto do saldo da carteira; é o valor que o dono aceita perder **inteiro** |
| `MEME_MAX_SOL_PER_TRADE` | `0.05` | **a decidir** | teto por compra; numa curva **é o risco por operação** (§5) |
| `MEME_DAILY_LOSS_CAP_SOL` | `0.20` | **a decidir** | perda do dia que **trava** a carteira (latched, §7) |
| `max_open_positions` | `3` | **a decidir** | abertas + pendentes |
| `max_exposure_per_mint_sol` | `0.05` | **a decidir** | igual ao teto por trade: em v0 **não há reforço de posição** |
| `max_participation_pct` | `0.01` | **a decidir** | fração do volume **orgânico** do último minuto da curva (§5) |
| `max_price_impact_pct` | `0.005` | **a decidir** | impacto da **nossa própria** compra na curva, pela fórmula |
| `max_slippage_pct` | `0.01` | **a decidir** | tolerância que vira `max_sol_cost` na instrução (§9.4) |
| `max_priority_fee_sol` | `0.002` | **a decidir** | teto absoluto do priority fee |
| `max_priority_fee_pct_of_trade` | `0.05` | **a decidir** | e teto relativo: uma compra de 0,05 SOL nunca paga 0,005 de prioridade |
| `max_jito_tip_sol` | `0.001` | **a decidir** | teto do tip; `0` significa "sem bundle" (§9.3) |
| `token_age_min_s` | `30` | — | tempo mínimo de vida do token |
| `token_age_max_s` | `600` | — | tempo máximo (10 min) |
| `curve_progress_min_pct` / `max_pct` | `0.02` / `0.50` | — | janela de progresso `1 − real_token_reserves/initial_real_token_reserves` |
| `max_bundled_share_pct` | `0.20` | — | **nulo → recusa** (§4, check 11) |
| `max_top10_share_pct` | `0.25` | — | por **owner**, excluindo curva, pool e burn |
| `max_state_age_s` | `5` | — | idade máxima do estado da curva (a curva anda em segundos) |
| `clock_skew_tolerance_s` | `2` | — | herdado literalmente da §7.1 do contrato SPOT |
| `min_commitment` | `"confirmed"` | — | `processed` nunca decide (§8.2) |
| `reservation_ttl_s` | `5` | — | vida da reserva de uma proposta aprovada (§9.5) |
| `rug_mint_ban` | permanente | — | mint que rugou nunca é reentrado |
| `rug_cooldown_s` | `3600` | **a decidir** | pausa da carteira inteira depois de uma detecção de rug |
| `target_multiple` | `2.0` | — | alvo de saída |
| `trailing_from_peak_pct` | `0.30` | — | trailing sobre a **marca honesta** (§6) |
| `time_stop_s` | `900` | — | saída por tempo |
| `day_timezone` | `"America/Sao_Paulo"` | — | o dia de negociação, igual ao SPOT |
| `max_leverage` | `1` | — | identidade: sem empréstimo, sem short |
| `quote` | `"SOL"` | — | §1 |

**O teto é teto, não meta** — a frase do contrato SPOT vale igual: nada aqui aumenta tamanho para
"chegar" ao teto.

### 3.2 A carteira dedicada

- **Uma carteira, um uso.** Ela existe só para este motor: não recebe aporte de outro lugar, não é
  `exchange_connection`, não guarda nada além de SOL e das posições que este motor abriu.
- **Saldo acima do teto recusa entradas** (`wallet_over_max_sol`). O teto é o que o dono aceitou
  perder; um saldo maior significa que alguém depositou além do combinado, e o motor não decide
  sozinho operar mais dinheiro. A varredura do excesso é ato manual auditado.
- **Token desconhecido na carteira recusa entradas** (`wallet_unrecognized_holdings`) e **nunca é
  vendido automaticamente**: airdrop e token envenenado existem, e vender um mint que não abrimos é
  assinar uma transação contra um programa que não está na allowlist da §1.
- **Reserva de aluguel.** SOL preso em rent de ATA não é caixa: `available_sol` desconta rent
  estimado e taxas (§5). A doc oficial cita, por exemplo, `0,0018444` SOL para criar
  `user_volume_accumulator` (T4.0d §6) — o número exato por conta vem do caminho de execução, nunca
  de um palpite arredondado.

### 3.3 A chave — `SOLANA_WALLET_SECRET_KEY`

| Regra | Detalhe |
|---|---|
| Onde vive | **só** no `.env` da VPS, digitado pelo Everton. Não no repo, não em `.env.example` com valor, não em compose commitado, não em chat, não em nota de agente |
| Quem lê | **um** processo: o executor meme (`services/meme-executor/`, proposto — §13). API, web, workers de dados e qualquer agente **não** recebem a variável no ambiente |
| Nunca aparece em | log, métrica, heartbeat, Sentry, resposta de API, mensagem de erro, exceção com repr do config |
| A chave pública | pode aparecer em log interno e na reconciliação; **não** em resposta pública de API — ela entrega nossa estratégia a quem observa a cadeia |
| Prova | teste obrigatório que serializa config, log, heartbeat e métricas e falha se o segredo (ou qualquer prefixo dele) aparecer; e um padrão novo no `forbidden_patterns.sh` para atribuição não vazia (§13, achado 3) |
| Permissão | a carteira não tem "permissão de saque" para desligar como numa exchange: **quem tem a chave move tudo**. É por isso que o teto de saldo (§3.2) é o controle real, não um detalhe de conforto |

### 3.4 A flag — `ENABLE_MEME_LIVE_TRADING`

Irmã de `ENABLE_LIVE_TRADING` e documentada ao lado dela (`docs/DEPLOYMENT.md`, "Feature flags de
sistema"):

- **Default `false`, e hoje inexistente no código** (§15).
- Enquanto `false`: `MemeLiveExecutionAdapter` levanta `MemeLiveTradingDisabled` em **toda** chamada,
  e o executor **recusa subir** se a flag estiver `true` sem as VM1–VM9 verdes registradas — o
  mesmo desenho do `LiveTradingRefused` do `execution-worker` (`docs/DEPLOYMENT.md`).
- Quem liga: **só o Everton**, no `.env` da VPS. Nenhum agente, nenhum PR, nenhum script.
- Ligada, ela **não** aprova nada por si: continua valendo o perfil live da §3.1 (com os números
  dele), o kill switch (§7) e as VM1–VM9 (§11).
- **Achado a fechar antes de a flag existir:** o guardião de padrões proibidos **não** cobre o nome
  novo (§13, achado 3).

> **Implementado em (T4.8 + T4.14):** a flag é lida por
> `hunter_core.execution.meme.gates.load_execution_mode` e composta por
> `services/meme-executor/hunter_meme_executor/config.py::boot` — portões → política (`limits_from_env`)
> → `SOLANA_RPC_URL` → chave, cada ausência uma recusa nomeada (`gates_file_not_configured`,
> `policy_missing`, `rpc_url_missing`, `rpc_url_cluster_mismatch`, `secret_key_missing`;
> `services/meme-executor/tests/test_config_boot.py`). Com a flag desligada o executor sobe **inerte**
> (`allow_send=False` no cliente RPC, `MemeLiveTradingDisabled` antes da chave, toda proposta `live`
> gravada `refused: meme_live_disabled`). A API tem a **sua** cópia da flag (`ApiSettings.
> enable_meme_live_trading`) para uma coisa só: arquivar `meme_proposals.mode = 'live'` e mostrar
> "Aprovar (REAL)" — ela nunca assina.

## 4. Checks de admissão de uma compra na curva

Todos os checks avaliáveis são registrados em `decision.checks[]` como
`{name, state, value, limit, input_ts, message}`, **mesmo depois do primeiro reprovado** — igual à
§3 do contrato SPOT. `state ∈ passed | failed | unavailable`, e `unavailable` **reprova**.

| # | Check | Reprova quando | Nome da recusa |
|---|---|---|---|
| 1 | `kill_switch` | efetivo ∈ {TRADING_DISABLED, EMERGENCY}, ou trava diária latched | `kill_switch_blocked`, `daily_loss_cap_latched` |
| 2 | `wallet_status` | carteira inativa, agente desabilitado, marcas incompletas | `wallet_inactive`, `agent_disabled`, `marks_incomplete` |
| 3 | `live_gate` | `mode="live"` com `ENABLE_MEME_LIVE_TRADING=false` | `meme_live_disabled` |
| 4 | `program_allowed` | programa fora da allowlist da §1 | `program_not_allowed` |
| 5 | `quote_supported` | quote ≠ SOL | `unsupported_quote` |
| 6 | `identity_match` | `mint` da proposta ≠ do estado ≠ do contexto | `identity_mismatch` |
| 7 | `state_freshness` | idade > `max_state_age_s`; sem carimbo; carimbo à frente além de 2 s; commitment abaixo do mínimo | `curve_state_stale`, `curve_state_undated`, `curve_state_clock_skew`, `commitment_too_weak` |
| 8 | `token_age` | fora de `[token_age_min_s, token_age_max_s]`, ou idade de procedência desconhecida | `token_too_young`, `token_too_old`, `token_age_unknown` |
| 9 | `curve_progress` | fora da janela; curva completa; denominador (`initial_real_token_reserves`) ausente | `progress_below_window`, `progress_above_window`, `curve_complete`, `progress_denominator_missing` |
| 10 | `creator_behaviour` | criador é vendedor líquido; fluxo do criador desconhecido | `creator_net_seller`, `creator_flow_unknown` |
| 11 | `bundled_share` | acima do teto; **nulo** | `bundled_share_above_cap`, `bundled_share_unmeasurable` |
| 12 | `top10_share` | acima do teto; desconhecido; denominador sem exclusão de curva/pool/burn | `top10_share_above_cap`, `top10_share_unknown`, `holder_denominator_invalid` |
| 13 | `mayhem_policy` | moeda Mayhem sem política aprovada; estado do agente desconhecido | `mayhem_not_allowed`, `mayhem_state_unknown` |
| 14 | `rug_history` | mint já marcado como rug; carteira em cooldown de rug | `token_rugged_no_reentry`, `rug_cooldown_active` |
| 15 | `duplicate_position` | já existe posição ou pendência neste mint | `duplicate_position` |
| 16 | `concurrent_positions` | abertas + pendentes ≥ `max_open_positions` | `max_open_positions` |
| 17 | `wallet_cap` | saldo > `MEME_WALLET_MAX_SOL`; holdings não reconhecidos | `wallet_over_max_sol`, `wallet_unrecognized_holdings` |
| 18 | `daily_loss` | perda do dia ≥ `MEME_DAILY_LOSS_CAP_SOL` (**também aciona** a trava, §7) | `daily_loss_cap_reached` |
| 19 | `slippage_cap` | `max_slippage_pct` pedido > teto do perfil | `slippage_above_cap` |
| 20 | `fee_caps` | priority fee > teto absoluto ou > fração da compra; tip > teto | `priority_fee_above_cap`, `jito_tip_above_cap` |
| 21 | `participation` | tamanho > fração do volume orgânico do minuto; janela incompleta; volume só do feed pago ausente | `participation_above_cap`, `volume_window_incomplete`, `volume_unavailable` |
| 22 | `price_impact` | impacto da própria compra na curva > teto (sempre calculável das reservas) | `price_impact_above_cap` |
| 23 | `sizing` | tamanho final abaixo do mínimo economicamente sensato (taxas + rent > ganho possível) — **rejeita, nunca arredonda para cima** | `below_min_sol` |
| 24 | `sol_available` | tamanho + taxas + rent + tip > `available_sol` | `insufficient_sol` |
| 25 | `exposure_after` | exposição por mint ou total depois desta entrada acima do teto (passa por construção, registrado para prova) | `exposure_after_above_cap` |

**A consequência de recusar por falta de dado, declarada e não escondida.** Com só os canais
gratuitos do PumpPortal (`subscribeNewToken`, `subscribeMigration`) os checks 10, 11, 12 e 21 são
`unavailable` — e o motor **recusa todas as compras**. Isso não é um bug: é a regra "insumo que não
existe não vira zero" funcionando. O caminho para sair desse estado é dado (feed pago de trades, ou
decodificador on-chain próprio), e é decisão do Everton (§14, pergunta 6), não um afrouxamento do
check.

**O que muda em relação ao SPOT, e por quê:** não existe `book_depth` nem `spread` — não há livro
(T4-MEME-RADAR §0). O papel deles é feito por **dois** checks que a curva permite fazer melhor: o
`price_impact` (22), que é **exato** porque sai da fórmula das reservas, e a `participation` (21),
que mede quanto do fluxo real somos. E não existe `beta_validity`: β contra o BTC numa moeda de 10
minutos de vida seria número inventado (§14, pergunta 7).

## 5. Sizing — o mínimo entre os tetos, com o limitante publicado

**O risco de uma compra na curva é o valor gasto inteiro, não a distância até um stop.** Esta é a
diferença conceitual mais importante em relação ao contrato SPOT, e é o que justifica caps em SOL em
vez de `risk_per_trade_pct`: numa curva o "stop" não é uma garantia — o criador pode largar tudo, a
liquidez real pode desaparecer, a transação de venda pode falhar por slippage, e o resultado
plausível de uma compra é **−100 %**. Dimensionar por distância de stop, aqui, seria prometer uma
proteção que a cadeia não oferece.

```
custo_estimado      = fee_curva(do TradeEvent, §9.6) + fee_do_caminho(§9.1) + fee_de_rede
                      + priority_fee + tip + rent_de_ATA_quando_aplicavel
available_sol       = max(0, sol_balance − Σ reserved_sol − rent_reservado)

sol_by_request      = proposal.requested_sol
sol_by_trade_cap    = MEME_MAX_SOL_PER_TRADE
sol_by_wallet_cap   = max(0, MEME_WALLET_MAX_SOL − exposicao_total_incl_pendentes)
sol_by_mint_cap     = max(0, max_exposure_per_mint_sol − exposicao_do_mint)
sol_by_daily_cap    = max(0, MEME_DAILY_LOSS_CAP_SOL − perda_do_dia − perda_maxima_comprometida)
sol_by_participation= max(0, max_participation_pct × volume_organico_1m − consumo_60s − reservas)
sol_by_impact       = maior gasto cujo impacto na curva (fórmula) fica em max_price_impact_pct
sol_by_available    = max(0, available_sol − custo_estimado)

sol_bruto   = min(todos acima)
limitante   = argmin(...)                       → sizing.binding_constraint
sol_final   = quantize(sol_bruto × ks_multiplier)
```

- **`sol_by_daily_cap` é o que torna o teto diário um teto de verdade.** Como a perda plausível de
  uma compra é o valor inteiro, o compromisso máximo já assumido pelas posições abertas entra na
  conta: cinco compras de 0,05 SOL não passam por baixo de um teto diário de 0,20 SOL.
- **`tied_limits` e `CAP_ORDER`** — desempate estável e declarado, como no SPOT: `requested`,
  `trade_cap`, `daily_cap`, `mint_cap`, `wallet_cap`, `participation`, `impact`, `available`.
- **Dois contrafactuais distintos, nunca reportados como um só:** `size_without_multipliers` (mede o
  degrau do kill switch) e `size_without_participation` (mede quanto a participação está mordendo).
  Insumo indisponível → **nulo com motivo**, nunca zero.
- **O multiplicador age sobre o tamanho final** (R-KS-1 do contrato SPOT), e o mínimo do check 23 é
  revalidado depois: tamanho reduzido que não paga as próprias taxas é **rejeitado**, nunca
  arredondado para cima.
- **Volume orgânico exclui o agente Mayhem** (carteira `BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s`,
  T4.0d §7) e exclui o que reconhecemos como wash/bundle. Sem poder excluir, o volume é
  `unavailable` — não é volume.
- **Orçamento de participação em janela móvel de 60 s**, chave `(mint, carteira)`, compartilhado por
  todos os agentes e pelo pedido manual: é assim que "não fracionar ordens para contornar limites"
  vira mecanismo, igual ao SPOT. Saídas **não** consomem esse orçamento.

## 6. Saídas — sempre permitidas, e a marca tem de ser honesta

`evaluate_meme_exit` **não roda check de entrada nenhum** e aprova sempre (regra 3 da diretiva). O
que ele decide é quantidade e roteamento, não permissão.

| Regra de saída | Gatilho |
|---|---|
| alvo | marca ≥ `target_multiple` × base de custo |
| trailing | marca ≤ pico da marca × (1 − `trailing_from_peak_pct`) |
| time stop | idade da posição ≥ `time_stop_s` |
| dump do criador | venda líquida do criador acima do limiar, ou qualquer venda dele quando a posição dele era a maior |
| conclusão/migração da curva | `CompleteEvent`; `CompletePumpAmmMigrationEvent` → a saída **passa a ser pelo PumpSwap**. **Parâmetro desde a T4.11** (`exit_on_migration`, ver nota abaixo) |
| morta (`dead`, T4.11) | só para um conjunto que segura através da migração: a fita da pool muda há ≥ `dead_stale_s` (900 s) **e** a marca ≤ `dead_mark_pct` (50 %) da entrada |
| sinal de rug | `rug_signals` do coletor; marca o mint como banido (check 14) |
| kill switch | `TRADING_DISABLED`/`EMERGENCY` não fecham posição sozinhos (§7) — as saídas acima continuam correndo |

**A marca é o que uma venda inteira renderia agora, taxas incluídas** — não o preço marginal, não o
"market cap". Preço marginal × quantidade é o número que faz um paper trade parecer lucrativo e um
resgate real sair 30 % abaixo. O mesmo vale para o `equity_sol` (§10).

**A saída na migração passou a ser parâmetro do conjunto (T4.11, `exit_on_migration`).** Os conjuntos
congelados (`meme_paper_v0`, `trendline_v0`, `hype_probe_v0`) mantêm `true` e continuam vendendo na
conclusão/migração da curva. `moonshot_v0/1`, `moonshot_v0/2` e `operator/2` usam `false`: a posição
sobrevive à migração e, a partir daí, a marca honesta é **pelo último trade da fita da pool PumpSwap**
(`meme_trades.program = 'pump_amm'`, `mark_source = 'pool_tape'`) — preço do último trade menos o impacto
estimado pela participação (tamanho ÷ volume dos últimos 5 min, teto 1 %) menos a taxa da **faixa da
PumpSwap pelo mcap do momento** (`docs/PUMPFUN.md` §4.1: 1,25 % logo depois da graduação, caindo por faixa
até 0,30 %; nunca 0,30 % fixo) menos os 0,5 % do caminho; a venda é precificada no trade **seguinte**
(`hunter_indicators.meme.pool`, `services/meme-worker/hunter_meme_worker/pool_mark.py`). A saída `dead`
(acima) é o que substitui o piso de perda nesses conjuntos. **O real herda a regra:** um executor que segure
através da migração vende pela PumpSwap (linha da tabela), com a mesma faixa de taxa, o mesmo orçamento de
participação e o mesmo `mark_stale_s` como sinal de mercado morto — nunca com uma marca pela curva vazia.

**A tentativa acaba, a intenção não.** Cópia literal da §10 do contrato SPOT: cada tentativa de
venda tem identidade própria; a intenção durável guarda a quantidade remanescente; só termina quando
a quantidade pretendida foi liquidada ou houve substituição explícita e auditada. Sem estado
utilizável da curva, a saída fica **pendente degradada, com alerta** — nunca um fill fabricado.

**Venda grande pode precisar de várias transações.** Se o `max_price_impact_pct` não permite vender
tudo de uma vez, a política de fatiamento é **declarada** (número de fatias, intervalo, teto de
impacto por fatia), consome o mesmo orçamento de participação, e o resíduo abaixo do mínimo
negociável fica como **resíduo contabilizado e impedimento visível** — sem quitação fictícia.

## 7. Kill switch meme

Escopos **sistema**, **organização**, **carteira**; efetivo = o mais restritivo, ordem
`ACTIVE < WARNING < TRADING_DISABLED < EMERGENCY`. Unidade de decisão: **SOL** (não USD, não BRL) —
o câmbio do SOL entrando na decisão bloquearia a carteira por um movimento de mercado que não é
nosso. Dia de negociação em `America/Sao_Paulo`, como no SPOT.

```
perda_do_dia_sol = max(0, equity_sol_inicio_do_dia − equity_sol)
drawdown_pct     = max(0, 1 − equity_sol / peak_equity_sol)
```

| Estado | Entradas | Saídas | Aciona |
|---|---|---|---|
| `ACTIVE` | permitidas | normais | — |
| `WARNING` | permitidas com **tamanho final × 0,5** | normais | metade do teto diário, ou drawdown de aviso (valor: §14) |
| `TRADING_DISABLED` | bloqueadas; pendentes canceladas | permitidas | `MEME_DAILY_LOSS_CAP_SOL` atingido |
| `EMERGENCY` | bloqueadas | permitidas | manual (OWNER) |

- **A trava diária é latched.** Diferente do SPOT (onde a avaliação se refaz a cada ciclo), aqui o
  estado **fica** travado depois de atingir o teto, mesmo que a marca suba depois: a marca de uma
  meme pode oscilar 50 % em minutos, e destravar por oscilação é apagar o limite do dono. A retomada
  é **sempre** manual, do OWNER, auditada em transição própria.
- **`resume` recusa retomar enquanto a avaliação do instante ainda bloqueia** — igual ao SPOT: uma
  transição que a próxima avaliação desfaz é pior no log que transição nenhuma.
- **Nenhum estado liquida posição automaticamente.** Em `EMERGENCY`, "só saídas" significa que as
  saídas de proteção continuam permitidas, não que o motor larga tudo na curva. Numa curva sem
  comprador, liquidação forçada é a maneira mais rápida de realizar a perda máxima. Se o Everton
  quiser um `meme_auto_close_on_emergency`, é decisão explícita dele (§14, pergunta 4), com o custo
  declarado — não um default nosso.
- **Os workers releem o estado a cada 10 s, com ou sem evento**, e a releitura do estado efetivo
  acontece **na mesma transação que aplica o efeito de entrada**, com ordem fixa de travas
  **sistema → organização → carteira**. Aprovação antiga não é salvo-conduto (§9.5).

## 8. Falhar fechado

### 8.1 O padrão

Cada check declara seu insumo e o que fazer quando ele falta; o padrão é **rejeitar**, e
`unavailable` é distinto de `failed` para a proveniência não mentir. Insumos com idade máxima
declarada: estado da curva, volume do minuto, features de holders/criador, idade do token, estado do
kill switch, saldo da carteira.

### 8.2 Frescura, slot e commitment

| Situação | Efeito |
|---|---|
| estado sem carimbo | `curve_state_undated` — insumo sem idade não é insumo |
| estado com idade > `max_state_age_s` | `curve_state_stale` |
| carimbo à frente do `as_of` **até 2 s** | tolerado e **contado** (é a ordem que o próprio ciclo cria — §7.1 do contrato SPOT) |
| carimbo à frente além de 2 s | `curve_state_clock_skew` — os relógios discordam, é problema de NTP, não de frescor |
| commitment `processed` | `commitment_too_weak`: decidir sobre leitura reversível é decidir sobre um estado que pode nunca ter existido |
| `confirmed` | mínimo para **decidir** |
| `finalized` | exigido para **contabilizar** posição como real antes de uma entrada nova no mesmo mint |
| RPC/WS ilegível | adia a entrada (`rpc_unreachable`), **nunca** derruba o passe de proteção |

### 8.3 Mayhem — política separada, porque o ruído é injetado por construção

Nas primeiras 24 h de uma moeda Mayhem, um agente do próprio pump.fun cunha 1 bilhão de tokens
extras e compra/vende em random walk (`T4-MEME-RADAR.md`, adendo). Consequências que este contrato
assume:

1. **Trades do agente saem do volume, dos compradores únicos e da razão compra/venda** — filtrando
   pela **carteira** do agente, não pela flag da moeda (T4.0d §7).
2. **A curva de uma moeda Mayhem pode "pular" sem `TradeEvent`:** `set_mayhem_virtual_params` emite
   `UpdateMayhemVirtualParamsEvent` e altera as reservas virtuais (T4.0d §1.3). Um simulador que só
   escute trades vai calcular um fill que a cadeia não daria. Enquanto esse evento não estiver
   decodificado e testado, moeda Mayhem é **recusada** (`mayhem_not_allowed`).
3. **Supply 2 bilhões vs. a régua de tier de taxa "preço × 1 bilhão"** (lida na doc oficial hoje,
   §15) é uma divergência **não resolvida**: não afirmo qual mcap a pump.fun usa para tierizar uma
   moeda Mayhem. Mais uma razão para a recusa em v0.

## 9. Caminho de execução e modelo de confiança

> **Implementado em (T4.8, 2026-09-12, inerte por construção — a doutrina abaixo não mudou):**
> opção **B** (instruções próprias pela IDL) em
> `packages/exchange-adapters/hunter_exchanges/pumpfun/{solana_codec,global_state,tx,quote,trade_event,verify,tx_rpc}.py`
> e `packages/core/hunter_core/execution/meme/{gates,signer,journal,submit}.py`.
> Paridade byte a byte provada contra um `buy` real do roteador do site e um `sell` real de um bot
> (`tests/fixtures/pumpfun/rpc_tx_{buy,probe}_raw.json`); prova de execução por
> `simulateTransaction` na mainnet com `sigVerify=false` (nunca enviada —
> `simulation_proof_mainnet_raw.json`). §9.1 → `verify.py` (teste adversarial em
> `test_pumpfun_verify.py`); §9.2 → `submit.py` + `tx_rpc.py` (`skipPreflight=false`, `allow_send`
> inerte por default); §9.3 → parâmetro `SubmitPolicy.jito_bundle=False` + `jito_tip_transfer`
> verificado contra o teto; §9.4 → `journal.py` (uma linha por proposta, assinaturas listadas,
> trava de assinatura) e `MemeSubmitter.reconcile/on_stream_event`; §9.5 → `expires_at` checado
> antes de tudo; §9.6 → `trade_event.py` (fill = `TradeEvent` decodificado; taxas do evento).
> VM1–VM3/VM7 continuam pendentes do pacote de risco da §13 (`infra/scripts/meme_vm.py` diz isso
> em vez de fingir verde).
>
> **T4.8b (tarde de 12/09/2026, `docs/PUMPFUN-ONCHAIN.md` §6c):** o programa da pump.fun foi
> atualizado às 15:24:04 UTC (slot 446462760). A "conta não documentada" da T4.8 era a PDA
> `["bonding-curve-v2", mint]` da moeda da fixture — agora derivada por mint (`tx.py`), com paridade
> byte a byte com o `sell` real da tarde (`t48b_rpc_tx_sell_raw.json`) e com os dois trades da manhã, e
> `buy`/`sell` simulados na mainnet pelo caminho do executor (`t48b_simulation_proof_mainnet_raw.json`,
> nunca enviados). `TradeEvent` tem `holder_rewards` como campo; `build.py` recusa curvas com quote ≠ SOL
> (`unsupported_quote`). Regra nova de §9.2: **identidade do programa** — `program_identity.py`
> (sha256 da IDL on-chain + slot do último deploy, capturados junto com as fixtures) e, no executor,
> `program_check.py`: divergência no boot ⇒ `program_upgraded` (live: o processo não sobe; nada
> assinado), em tempo de execução ⇒ toda entrada recusada por esse nome até T4.8b ser refeita.

### 9.1 As duas opções, com o custo e o que sai da nossa caixa

| | **A — PumpPortal Local Transaction API** | **B — instruções próprias pela IDL** |
|---|---|---|
| Como funciona | `POST https://pumpportal.fun/api/trade-local` com `publicKey, action, mint, amount, denominatedInSol, slippage, priorityFee, pool`; volta uma transação serializada que **nós** assinamos e enviamos pelo nosso RPC | montamos `buy_v2`/`sell_v2` das 26–27 contas do IDL (T4.0d §1.3/§6), assinamos e enviamos |
| Custo extra | **0,5 % por trade**, "calculada antes do slippage" (lido hoje, §15) — sobre a taxa de 1,25 % da curva | nenhum além de rede/prioridade |
| O que sai da nossa caixa | **a intenção inteira, antes de existir na cadeia**: carteira, mint, tamanho, slippage e priority fee | nada; só a transação assinada, para o RPC |
| Risco declarado | (i) vazamento de intenção a um terceiro — superfície de front-run; (ii) a transação é **escrita por eles**; (iii) disponibilidade e latência dependem deles | erramos por nossa conta: contas, discriminadores, versão da IDL, `max_sol_cost` |
| Onde serve | **protótipo em papel/devnet e comparação** | **o único caminho aceitável para dinheiro real**, depois de suíte própria de verificação |

**Regra que vale para A, sem exceção: nunca assinar uma transação que não conferimos.** Antes de
assinar, a transação decodificada tem de passar por um verificador nosso, e a falha é recusa
(`unverified_transaction`), não aviso:

1. todo `program_id` invocado está na allowlist da §1;
2. o único signatário é a nossa carteira; nenhuma autoridade nossa é delegada ou trocada;
3. nenhuma transferência de SOL/token para destino fora do conjunto esperado (curva, ATAs, fee
   recipients do IDL, tip de Jito dentro do teto);
4. `amount` e **`max_sol_cost`/`min_sol_output`** batem com o que **nós** calculamos — a instrução da
   curva **não tem parâmetro de "% de slippage"** (T4.0d §6): o teto é um número em lamports, e o
   `slippage: 10` que mandamos é a *promessa* deles de traduzir. A prova está nos args da instrução
   que voltou, não no nosso pedido;
5. compute unit limit e price dentro dos tetos (a doc oficial usa 400.000 CU para `buy_v2`/`sell_v2`
   — T4.0d §6);
6. blockhash presente e ainda válido.

### 9.2 Envio e confirmação

- Envio pelo **nosso** RPC (com chave; nunca o público em produção — T4.0 §2).
- `skipPreflight` **desligado** por padrão: preflight é a última chance de a cadeia dizer "isso
  falharia" sem custo.
- Confirmação por `getSignatureStatuses` com `commitment` do perfil; sem resposta dentro do prazo, a
  tentativa vira `submitted_unconfirmed` — que **não é fill nem cancelamento** (§9.5).

### 9.3 Jito bundles

Fatos verificados hoje (§15): body é um **array** de até 5 transações, o `priorityFee` da **primeira**
é usado como **tip** (os seguintes são ignorados), e o bundle vai para
`https://mainnet.block-engine.jito.wtf/api/v1/bundles`.

Política: bundle **só** quando duas instruções precisam ser atômicas de verdade (ex.: criar ATA e
comprar), nunca para competir em leilão de inclusão; **uma** carteira nossa por bundle (§1); tip
sempre ≤ `max_jito_tip_sol` **e** contado como custo no sizing (§5) — tip que não entra no custo é
lucro imaginário; se o bundle não é incluído, **nada** aconteceu, e isso é um resultado esperado, não
um erro para "resolver" com tip maior fora do teto.

### 9.4 Idempotência — o ponto onde uma cadeia é diferente de uma exchange

`client_order_id` deriva do `proposal_id` (`meme:{proposal_id}`), como no SPOT, e é único no banco.
Mas na Solana **a identidade da ordem é a assinatura, e a assinatura muda quando o blockhash muda** —
uma retentativa "igual" com blockhash novo é uma **compra nova**. Regras:

1. Uma linha durável por proposta (`meme_orders`, único por `client_order_id`), com a lista de
   assinaturas já emitidas para ela.
2. Assinar só é permitido com a linha em estado `signing`, tomado sob trava — duas sessões nunca
   assinam a mesma proposta (VM9).
3. Retentativa **reusa o mesmo blockhash** enquanto ele é válido: mesma assinatura, e a rede
   deduplica (a validade de um blockhash em slots **não foi reconfirmada nesta rodada** — a ser
   fixada em T4.6 contra `solana.com/docs`).
4. Blockhash expirado ⇒ a retentativa é uma **tentativa nova**, e exige: reconciliar a assinatura
   anterior (`getSignatureStatuses`) **antes**, reler as reservas, e a reserva da proposta ainda não
   expirada (`reservation_ttl_s`, §9.5).
5. Reentrega do mesmo evento de stream (`meme_trades`, WS, webhook) **nunca** cria uma segunda ordem:
   idempotência por `client_order_id` e por `execution_key` do fill — com teste (VM4).

O modo de falha que essas regras fecham, e que é o mais caro de todos: *timeout no envio → retentativa
com blockhash novo → as duas entram → posição dupla e caixa negativo*.

### 9.5 Reserva, expiração e "aprovação antiga não vale"

Proposta aprovada reserva SOL e vaga. `reservation_ttl_s = 5` (contra os 30 s do SPOT) porque o
estado da curva vale segundos: uma decisão de 30 s atrás foi tomada sobre reservas que já não
existem. Passado o TTL, a reserva expira com o motivo gravado e a proposta **nunca é executada
tarde**. Antes de **cada** efeito, o executor relê decisão válida, reserva, kill switch efetivo e
estado da curva.

### 9.6 O que é um "fill" numa curva

**Fill é o `TradeEvent` decodificado da transação confirmada** — `sol_amount`, `token_amount`,
`fee_basis_points`, `fee`, `creator_fee_basis_points`, `creator_fee` e as reservas resultantes vêm
prontos no evento (T4.0d §1.4/§1.4b). Não é o envio, não é a cotação, não é o que pedimos.

| Estado | Significado | O que o motor faz |
|---|---|---|
| `submitted_unconfirmed` | assinada e enviada, sem status | **bloqueia entradas novas naquele mint**, alerta, reconcilia; nunca retenta cego |
| `failed` | transação confirmada como falha (ex.: `max_sol_cost` estourado) | **não** há posição; a tentativa acabou; o motivo vira evento de risco |
| `filled` | `TradeEvent` decodificado | posição = o que a cadeia diz (tokens recebidos), custo = SOL gasto + taxas do evento |
| divergência | `TradeEvent` ≠ saldo da ATA ≠ nossa linha | `reconciliation_mismatch`: **a cadeia é a verdade**, entradas bloqueadas até reconciliar, nunca correção silenciosa |

**Reconciliação obrigatória depois de cada fill:** `TradeEvent` + saldo da ATA + reservas da curva.
As taxas usadas na contabilidade são as **do evento**, nunca a constante 1,25 % — a própria taxa é
configurável por tier no programa (T4.0d §1.4b), e uma constante estática numa contabilidade é um
erro esperando o dia em que o tier muda.

## 10. O simulador de papel

**Fill de papel = fórmula + taxas + prioridade + slippage de concorrência medido depois do fato.**
Nada de "preenchido ao último preço visto".

1. **Fórmula** (determinística, `x·y = k`): custo de `q` tokens = `k/(x−q) − y`; recebimento de uma
   venda = `y − k/(x+q)`; preço marginal = `y/x` (T4.0d §1.4b, `curve.py`).
2. **Taxas:** 1,25 % da curva **hoje** (creator 0,300 % + protocol 0,950 % + LP 0 %, lido hoje —
   §15) como *default* do papel, **substituído pelo valor do `TradeEvent`** onde o evento existe;
   mais a taxa do caminho escolhido (0,5 % se PumpPortal local — §9.1); mais taxa de rede,
   priority fee, tip e rent.
   **Regra doutrinária: o papel nunca simula um caminho mais barato do que o live vai usar.** Papel
   sem os 0,5 % e live com eles é um backtest que mente 1 % por ida e volta.
3. **Venda pós-migração usa o tier do pool**, não 0,30 %: a tabela oficial lida hoje começa em
   **1,25 %** para mcap 0–420 SOL, que é exatamente onde uma moeda recém-graduada cai (§15).
4. **Slippage de concorrência:** a nossa intenção é reprecificada contra as reservas observadas no
   **próximo** snapshot depois dela (`fill_delay_snapshots`, T4.5). Sem snapshot posterior, **não há
   fill** — a mesma proibição de fill fabricado da V9 do SPOT.
5. **Fill parcial/nenhum:** na curva a transação é atômica — ou o `max_sol_cost` segura, ou a
   transação falha. "Parcial" só existe em dois sentidos, e os dois são modelados: (a) recebemos
   **menos tokens** do que a cotação sugeria (dentro da tolerância) e (b) uma **saída** fatiada por
   impacto (§6).
6. **Invariante testada por propriedade:** `equity_sol = sol_balance + Σ marca(posição)`, com marca =
   o que uma venda inteira renderia agora, taxas incluídas. Round-trip compra→venda sem movimento de
   terceiros perde **exatamente** taxas + impacto próprio — nunca lucro.

7. **Fill na fotografia de 15 s e o desfecho indeterminado (T4.16).** Para as moedas com menos de 5 minutos o
   relógio do papel é o laço `meme-fast` (uma fotografia da curva a cada 15 s, `meme_features_15s`): a porta é
   avaliada **por fotografia** (só com o que tinha chegado até `as_of` — `received_at <= as_of`, nunca o
   futuro) e o fill continua sendo a **primeira** fotografia com `observed_at > decided_at`, que agora chega em
   15 s, não no minuto seguinte (`decision_to_fill_s` medido por aposta e publicado como p50/p95 no
   heartbeat — nunca assumido pela cadência). A regra do item 4 não muda: sem fotografia posterior em 3 min,
   **não há fill**; e uma **venda** sem fotografia em 3 min fecha a zero na linha (`rug_no_snapshot`, o
   resultado plausível do §5) mas com `outcome_quality = indeterminate`: a linha mantém o −1 R e **nenhuma
   soma** (placar, mesa, fechamento diário, a carteira do laço e o teto diário) o conta — o instrumento piscou,
   o mercado não falou. A reclassificação de linhas antigas é ato auditado
   (`infra/scripts/meme_reclassify_indeterminate.py --apply --reason`), nunca edição à mão.

## 11. VM1–VM9 — as nove verificações do motor meme

Equivalente das V1–V9 da T3.9 (`.claude/state/spec-T3.9-verificacoes.md`,
`tests/integration/paper/test_v*.py`). Nomeadas **VM** de propósito: as V1–V9 são do SPOT e
continuam existindo. Nenhum arquivo abaixo existe hoje; os caminhos são a proposta.

| # | O que prova | Teste (proposto) | Comando demo |
|---|---|---|---|
| VM1 | **Sizing**: `sol_final` = mínimo dos tetos, `binding_constraint` publicado, `tied_limits` estável, contrafactuais distintos | `packages/risk-core/tests/unit/meme/test_vm1_sizing.py` (puro, tabela de casos) | `timeout 290 uv run pytest packages/risk-core/tests/unit/meme/test_vm1_sizing.py -q` |
| VM2 | **Caps**: teto por trade, por mint, da carteira e do dia mordem de fato; saldo acima do teto recusa; 5×0,05 não passa sob teto diário de 0,20 | `tests/integration/meme/test_vm2_caps.py` | `timeout 290 uv run pytest tests/integration/meme/test_vm2_caps.py -q` |
| VM3 | **Kill switch**: trava diária latched bloqueia entradas, **não** bloqueia saídas; `resume` só OWNER e recusado enquanto a avaliação bloqueia; releitura de 10 s | `tests/integration/meme/test_vm3_kill_switch.py` | `timeout 290 uv run pytest tests/integration/meme/test_vm3_kill_switch.py -q` |
| VM4 | **Submissão duplicada**: reentrega do evento de stream e retentativa não criam segunda ordem; mesmo blockhash ⇒ mesma assinatura; blockhash novo exige reconciliação antes | `tests/integration/meme/test_vm4_duplicate_submission.py` | `timeout 290 uv run pytest tests/integration/meme/test_vm4_duplicate_submission.py -q` |
| VM5 | **Falha de RPC no meio do envio**: timeout depois de enviar ⇒ `submitted_unconfirmed`, mint bloqueado, reconciliação; **nunca** retentativa cega | `tests/integration/meme/test_vm5_rpc_failure_midsend.py` | `timeout 290 uv run pytest tests/integration/meme/test_vm5_rpc_failure_midsend.py -q` |
| VM6 | **Fill parcial/nenhum**: `max_sol_cost` estourado ⇒ sem posição; tokens recebidos < cotação ⇒ posição = o que a cadeia diz; sem snapshot posterior ⇒ sem fill no papel | `tests/integration/meme/test_vm6_partial_or_no_fill.py` | `timeout 290 uv run pytest tests/integration/meme/test_vm6_partial_or_no_fill.py -q` |
| VM7 | **Rug durante a posse**: sinal de rug força saída, marca o mint (sem reentrada) e liga o cooldown da carteira; saída degradada não fabrica fill | `tests/integration/meme/test_vm7_rug_during_hold.py` | `timeout 290 uv run pytest tests/integration/meme/test_vm7_rug_during_hold.py -q` |
| VM8 | **Restart com posição aberta**: executor reconstrói do Postgres **e** reconcilia com a cadeia; proposta aprovada com reserva vencida nunca executa tarde; divergência bloqueia entradas | `tests/integration/meme/test_vm8_restart_open_position.py` | `timeout 290 uv run pytest tests/integration/meme/test_vm8_restart_open_position.py -q` |
| VM9 | **Duas sessões**: kill switch relido na mesma transação do efeito, travas sistema → org → carteira, orçamento de participação serializado, uma só assinatura por proposta | `tests/integration/meme/test_vm9_concurrent_sessions.py` | `timeout 290 uv run pytest tests/integration/meme/test_vm9_concurrent_sessions.py -q` |

**Cada check da §4 precisa de um caso que passa e um que reprova**, e cada recusa nomeada precisa
aparecer em pelo menos um teste — é a regra do contrato SPOT, aplicada aqui desde o começo.
Cobertura de nomes verificável por um teste que compara o conjunto de nomes da §4 com os nomes
exercitados na suíte.

**Demo de ponta a ponta (proposta):** `infra/scripts/meme_paper_demo.py` roda a carteira de papel
sobre fixtures reais da T4.1 e imprime decisão, checks, limitante e ledger — o equivalente do
caminho manual do operador (§12, item 3).

## 12. "Fluxo completo verificado" — a definição que destrava dinheiro real

Dois portões independentes, **ambos** obrigatórios, mais o interruptor do dono. Confundi-los é o
erro que este documento existe para evitar: motor seguro ≠ estratégia lucrativa.

**Portão A — engenharia (o motor não perde dinheiro por defeito nosso):**

1. VM1–VM9 verdes **na VPS**, com saída real colada em `.claude/state/notes-T4.x.md` (o padrão da
   T3.9/T3.70).
2. **7 dias corridos** de carteira de papel sobre dados reais da curva, sem lacuna não declarada, com
   reconciliação diária de `equity_sol` fechando (diferença zero, ou explicada e registrada).
3. Um `submitted_unconfirmed`, um `failed` por slippage e um restart com posição aberta **observados
   de fato** no papel (ou injetados em devnet), não só testados em unidade.
4. O caminho de execução escolhido (§9.1) com o verificador de transação da §9.1 provado por teste
   adversarial: transação adulterada é **recusada**.
5. A chave lida por **um** processo, com o teste de não-vazamento verde, e o `forbidden_patterns.sh`
   estendido (§13, achados 1 e 4).
6. **Caminho manual do operador provado em papel:** um pedido de compra e um de venda digitados pelo
   Everton passam pelo **mesmo** motor (proposta → checks → decisão persistida → ordem), com
   `Idempotency-Key` e recusa nomeada — o espelho da rota `order-requests` do SPOT
   (`docs/RISK_ENGINE.md` §8). **Nenhum caminho cria ordem de entrada sem decisão aprovada
   persistida antes**, nem o manual; saídas continuam sempre permitidas.

**Portão B — evidência de vantagem (a estratégia tem expectativa positiva):** EXP-M1 (T4.5), pelo
funil já acordado com a Astra: **≥ 100 operações avaliáveis E ≥ 30 dias**, expectativa líquida em SOL
depois de **todas** as taxas com IC 95 % por **blocos de dia** acima de zero, positiva em **2 de 3**
janelas, e **não** dependente do 1 % melhor dos tokens (leave-top-out), sem seleção por sucesso na
retenção.

**Portão C — o interruptor:** o Everton digita a chave no `.env` da VPS, escreve os valores live da
§3.1 e liga `ENABLE_MEME_LIVE_TRADING`. Com A ou B vermelho, o processo **recusa subir** — e isso é
proteção dele contra nós, não burocracia.

**Variante válida dos Portões A e B — o teste pequeno autorizado por escrito (T4.14).** O dono pode
decidir, **por escrito e só ele**, que um teste limitado vale antes de A e B ficarem verdes — é dinheiro
dele, e a diretiva de 2026-09-06 fala do *modo autônomo*, não de um teste que ele mesmo escopa. A forma é
mecânica, não uma frase: `meme_gates.json` traz `small_test_authorization {authorized_by, scope
{max_sol_per_trade, max_total_sol, max_trades}, expires_at, decision_note}` **no lugar** de
`gate_a_engineering.passed`/`gate_b_evidence.passed` (o Portão C continua obrigatório), e
`decision_note` tem de apontar para um arquivo em `obsidian/06-DECISIONS/` — a decisão registrada, com
data. O executor (`hunter_core.execution.meme.gates.load_gates`) valida o bloco inteiro, recusa por nome
(`small_test_unauthorized`, `small_test_invalid`, `small_test_without_decision_note`,
`small_test_expired`) e transforma o escopo em **teto adicional** (`min` com os cinco `MEME_*` do `.env`:
`max_sol_per_trade` e `max_exposure_per_mint_sol` pelo `max_sol_per_trade` do escopo, `wallet_max_sol`
pelo `max_total_sol`) e em **contador** (`small_test_scope_exhausted` depois de `max_trades` compras
enviadas). O heartbeat publica o escopo e a nota. Nada nisto afrouxa um check da §4: um teste pequeno
com `bundled_share` não medido continua recusado `bundled_share_unmeasurable`.

**A declaração honesta sobre "hoje":** dos três portões, hoje existe **zero**. O que existe é o
adapter público (T4.1), o mapa on-chain (T4.0d) e este contrato. "Operar hoje" = papel + radar.

## 13. O que muda no motor atual

**Nada.** A doutrina SPOT fica como está, e o motor meme é outro pacote. Não é preferência de estilo
— é o que o código impõe hoje, e eu verifiquei cada afirmação (§15):

| Fato verificado | Consequência |
|---|---|
| `packages/risk-core/hunter_risk/limits.py:124-126` recusa `max_leverage != 1` com a mensagem "directive §6 is spot only" | qualquer perfil meme dentro de `RiskLimits` seria ou um SPOT disfarçado ou uma mudança na doutrina do Everton |
| `packages/risk-core/hunter_risk/checks.py:80-84` (`modality`) exige `LONG` **e** `MarketType.SPOT` | um mint não passa por esse check sem mentir sobre o que é |
| `packages/core/hunter_core/domain/enums.py:115` — `MarketType` só tem `spot` e `perpetual` | expressar uma curva exigiria um `market_type` novo, e todo consumidor de `MarketType` herdaria a ambiguidade |
| `MarketLiquidity` exige livro (`asks[]`, `spread_pct`) e `MarketIdentity` exige `exchange`/`symbol` (`hunter_risk/inputs.py:39-47`) | reaproveitar o motor exigiria **fabricar um livro** a partir de reservas: exatamente o D1 que o projeto proíbe, e o achado que a Astra já registrou (`astra-review-t40-pumpfun.md`: "Risco SPOT não cobre execução on-chain") |
| `grep` por `solana|pumpfun|bonding` em `hunter_risk/**` e `hunter_execution_worker/**`: nenhuma ocorrência | a fronteira está intacta hoje e deve continuar |

> **Implementado em (T4.14, 2026-09-12; inerte por construção — a doutrina não mudou):**
> `packages/risk-core/hunter_risk_meme/` (`base.py` copia a disciplina de `hunter_risk.base` em vez de
> importá-la; `inputs.py`, `limits.py`, `checks.py` + `checks_wallet.py`, `sizing.py`, `kill_switch.py`,
> `decision.py`, `exits.py`, `evaluate.py`) — a fronteira é provada por
> `packages/risk-core/tests/unit/meme/test_boundary.py` (nenhum import cruzado, nenhum `httpx`/
> `sqlalchemy`/`redis`/`asyncio`/`time`); `services/meme-executor/` (o único leitor de
> `SOLANA_WALLET_SECRET_KEY`; `/health`·`/ready`·`/metrics` do `WorkerRuntime`, nada mais); tabelas em
> `0028_meme_live` (`docs/DATABASE.md` §40) com **nomes diferentes dos propostos abaixo, de propósito**:
> `meme_orders`/`meme_signatures`/`meme_fills` viraram **uma** tabela `meme_live_orders` (a lista de
> assinaturas e o fill são colunas jsonb da própria linha — a trava de assinatura e a assinatura têm de
> ser gravadas na mesma linha que o submitter lê), `meme_positions`/`meme_exit_intents` viraram
> `meme_live_positions` (a intenção durável é coluna), `meme_participation_consumptions` é computada das
> tentativas dos últimos 60 s (`repo.participation_used_sol`), `meme_kill_switch_transitions` ficou como a
> linha latched de `meme_live_kill_switch` (**sem** tabela de transições ainda — a soltura é um `UPDATE`
> manual, `docs/DEPLOYMENT.md` §3.7); `meme_wallets`/`meme_proposals` são as da T4.7/T4.12. Eventos de
> risco: **não** há linhas `risk_events` meme — cada recusa vai inteira para `meme_live_orders.admission`
> e o heartbeat `hb:meme:executor` publica `last_refusal`, trava, fontes do kill switch; a tabela de
> eventos fica para quem ligar a mesa a alertas. Achados 1 e 4 fechados na T4.8 (`forbidden_patterns.sh`
> cobre `ENABLE_(MEME_)?LIVE_TRADING` nas formas `=`/`:`); achado 3 (`meme_trades` PK) segue aberto e
> **não** afeta o executor, que lê o fill do `TradeEvent` da própria transação, nunca de `meme_trades`.

**O que este contrato propôs criar (a lista original, para comparação com o bloco acima):**

- `packages/risk-core/hunter_risk_meme/` — pacote puro irmão: `inputs.py`, `limits.py`, `checks.py`,
  `sizing.py`, `kill_switch.py`, `decision.py`, `exits.py`. **Nunca importado por `hunter_risk`**, e
  vice-versa; um teste de fronteira (import-linter ou equivalente) prova a separação.
- `services/meme-executor/` — o **único** processo que lê `SOLANA_WALLET_SECRET_KEY`; papel de banco
  próprio; sem HTTP além de `/health`/`/ready`/`/metrics`.
- Tabelas (dono: `docs/DATABASE.md`, tarefa futura): `meme_wallets`, `meme_proposals`, `meme_orders`
  (único por `client_order_id`), `meme_signatures`, `meme_fills` (único por `execution_key`),
  `meme_positions`, `meme_exit_intents`, `meme_participation_consumptions`,
  `meme_kill_switch_transitions`.
- Eventos de risco: `meme_proposal_rejected`, `meme_unavailable_input`, `meme_daily_loss_latched`,
  `meme_kill_switch_changed`, `meme_rug_detected`, `meme_unconfirmed_submission`,
  `meme_reconciliation_mismatch`, `meme_participation_capped`, `meme_unverified_transaction`.
  Severidade `info|warning|critical`; `critical` notifica OWNER e vai ao Sentry.

**Quatro achados desta revisão, cada um com cenário de falha:**

1. **`infra/scripts/forbidden_patterns.sh:144` — MÉDIO — o guardião de `ENABLE_LIVE_TRADING=true`
   não cobre o nome novo.** O padrão é
   `ENABLE_LIVE_TRADING[[:space:]]*=[[:space:]]*true`, e `ENABLE_MEME_LIVE_TRADING=true` **não**
   casa (probe em §15). Cenário: alguém commita um compose com `ENABLE_MEME_LIVE_TRADING: "true"`, o
   guardião passa verde, e a única barreira que sobra é um processo que ainda não existe.
   Correção: acrescentar o padrão junto com a flag.
2. **`packages/exchange-adapters/hunter_exchanges/pumpfun/curve.py:41` — BAIXO (documental) — a
   constante `CURVE_TRADE_FEE_PCT = 1.25` descreve o tier de hoje, não uma taxa de protocolo.**
   T4.0d §1.4b já registra isso. Cenário: um dia o tier da curva muda, a contabilidade de fills
   continua debitando 1,25 % e o PnL reportado divirge do extrato on-chain sem nenhum teste falhar.
   Mitigação deste contrato: a taxa da contabilidade vem do `TradeEvent` (§9.6).
3. **`docs/plans/T4-MEME-RADAR.md` §5 (`meme_trades` PK `(signature, ts)`) — MÉDIO para execução —
   dedupe por assinatura não distingue instruções dentro da mesma transação.** MUST-FIX 2 da Astra,
   ainda aberto (§8b do plano). Cenário: um bundle nosso com criação de ATA + compra, ou uma
   transação com dois trades, é contado como um só — e a reconciliação da §9.6 compara a cadeia com
   uma linha que já perdeu um evento. Execução real **não** pode ser liberada antes disso fechar.
4. **`infra/scripts/forbidden_patterns.sh:144` — MÉDIO — o padrão só casa a forma `=`, e os composes
   usam a forma YAML `:`.** `infra/docker/docker-compose.yml:566` escreve
   `ENABLE_LIVE_TRADING: "false"`; o padrão do guardião exige
   `ENABLE_LIVE_TRADING[[:space:]]*=[[:space:]]*true`. Probe desta sessão: `ENABLE_LIVE_TRADING=true`
   é pego, `ENABLE_LIVE_TRADING: "true"` **passa livre** (§15). Cenário: alguém edita o compose para
   `"true"`, o gate fica verde e o único obstáculo restante é a recusa de boot
   (`services/execution-worker/hunter_execution_worker/config.py:107`, `LiveTradingRefused`) — que
   existe, então dinheiro não se move, mas a defesa é **uma camada mais fina do que a documentação
   promete**. Vale para a flag meme em dobro: lá a recusa de boot ainda não existe. Correção: o
   padrão deve aceitar `[:=]` e cobrir os dois nomes.

## 14. Perguntas ao Everton (nenhuma decidida aqui)

1. **Os valores de política** da §3.1 (coluna "live"): teto da carteira, por trade, perda do dia,
   posições, cooldown. Proponho começar pelo menor número com que ele ficaria indiferente a perder
   **tudo** no primeiro dia.
2. **Limiares de AVISO** (metade do teto diário? drawdown?) — o SPOT tem 1 %/4 %; a régua de uma
   carteira meme não é a mesma e não vou inventar.
3. **Mayhem:** recusar em v0 (minha recomendação) ou ter política própria?
4. **`meme_auto_close_on_emergency`:** manter o comportamento do SPOT (nunca liquidar sozinho) ou
   autorizar liquidação em EMERGENCY, sabendo que numa curva ela realiza o pior preço?
5. **Caminho de execução (§9.1):** aceitar 0,5 % do PumpPortal por trade pela velocidade de entrega,
   ou pagar em tempo de engenharia e montar as instruções nós mesmos? Minha recomendação: A só em
   papel/devnet, B para dinheiro real.
6. **Feed de trades pago** (0,01 SOL / 10.000 eventos) ou decodificador on-chain próprio — **sem um
   dos dois, o motor recusa todas as compras** (§4).
7. **β e o universo:** confirmo que não haverá β contra o BTC para memes (seria número inventado), e
   que o piso de 50 M USDT de volume 24 h do SPOT **não** se aplica aqui — a régua é participação e
   impacto. Ele precisa saber que esta é uma diferença deliberada em relação à diretiva dele.

## 15. Proveniência das leituras desta sessão

Hora do servidor do PumpPortal no início da sessão: `Date: Sat, 12 Sep 2026 05:37:03 GMT` (02:37
BRT). Tudo abaixo lido por `curl` read-only, sem chave, nesta sessão (05:37–05:45 UTC / 02:37–02:45
BRT):

| Fonte | O que confirmou |
|---|---|
| `https://pumpportal.fun/local-trading-api/trading-api` (HTTP 200) | `POST https://pumpportal.fun/api/trade-local`; campos `publicKey, action, mint, amount, denominatedInSol, slippage, priorityFee, pool`; devolve transação serializada que o cliente assina localmente |
| `https://pumpportal.fun/fees` (HTTP 200) | **Local Transaction API: 0,5 % por trade**, "calculada antes do slippage"; Lightning 1 %; dados: `subscribeNewToken`/`subscribeMigration` sem custo, `subscribeTokenTrade`/`subscribeAccountTrade` a 0,01 SOL por 10.000 trades; nenhuma dessas taxas inclui rede nem a taxa da curva |
| `https://pumpportal.fun/local-trading-api/jito-bundles` (HTTP 200) | body como **array**, até 5 transações, `priorityFee` da primeira usado como **tip** (os demais ignorados), envio a `https://mainnet.block-engine.jito.wtf/api/v1/bundles` |
| `https://pump.fun/docs/fees` (HTTP 200, "Last Updated: 20 May 2026") | curva: creator 0,300 % + protocol 0,950 % + LP 0 % = **1,25 %**; criar moeda 0 SOL; graduação 0,015 SOL; USDC como quote desde 21/05/2026; PumpSwap por tier de mcap (`preço × 1 bilhão`), **1,25 % em 0–420 SOL**, caindo até 0,30 % acima de 98.240 SOL |
| `grep` no repo | `ENABLE_MEME_LIVE_TRADING`, `SOLANA_WALLET_SECRET_KEY`, `MEME_DAILY_LOSS_CAP_SOL`: **nenhuma ocorrência**; `solana|pumpfun|bonding` em `hunter_risk/**` e `hunter_execution_worker/**`: **nenhuma ocorrência** |
| probe do padrão proibido | `ENABLE_LIVE_TRADING=true` é pego; `ENABLE_LIVE_TRADING: "true"`, `ENABLE_MEME_LIVE_TRADING=true` e `ENABLE_MEME_LIVE_TRADING: "true"` **passam livres** pelo padrão de `forbidden_patterns.sh:144` (achados 1 e 4 da §13) |

Fontes internas: `docs/RISK_ENGINE.md` v2.5 (§2–§5, §7.1, §8, §10, §11), `docs/PIPELINE.md` §7/§8,
`docs/ARCHITECTURE.md` §6, `docs/PUMPFUN-ONCHAIN.md` (T4.0d), `docs/plans/T4-MEME-RADAR.md`,
`.claude/state/astra-review-t40-pumpfun.md`, `.claude/state/astra-review-t40-plano-meme-radar.md`,
`.claude/state/notes-T4.0.md`, `.claude/state/notes-T4.0b.md`, `.claude/state/notes-T4.1.md`,
`.claude/state/spec-T3.9-verificacoes.md`, `.claude/state/notes-T3.70.md`,
`packages/exchange-adapters/hunter_exchanges/pumpfun/{curve,models}.py`.
