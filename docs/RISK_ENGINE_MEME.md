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

**Status da venda na PumpSwap (T4.29a, 2026-09-16): implementada e verificada offline —
não simulada na mainnet real.** `hunter_exchanges.pumpswap` decodifica `GlobalConfig`/`Pool` pela
IDL on-chain do próprio programa (lida ao vivo, sha256 em `decode.py`), deriva o pool canônico de um
mint migrado sem RPC (confirmado contra 3 pools reais), cota a venda por produto constante com as
taxas lidas de `GlobalConfig` (nunca fixas) e monta a instrução `sell` (21 contas, ordem da IDL) mais
o unwrap de WSOL. O executor (`pumpswap_exit.py`) roteia toda posição `migrated` para esse caminho, com
o mesmo verificador/simulação/journal/kill-switch da curva; `pumpswap_pool_not_found` substitui
`pumpswap_sell_not_implemented` quando o pool ainda não existe. **O que não está provado:** nenhuma
venda real foi simulada na mainnet (nenhuma carteira com posição migrada disponível nesta tarefa) nem
enviada; `docs/PUMPFUN.md` §"PumpSwap (venda pós-migração)" e `.claude/state/notes-T4.29a.md` têm o
detalhe completo, incluindo o comando `--simulate-only` que o dono deve rodar na VPS.

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
| `curve_progress_min_pct` / `max_pct` | `0.02` / `0.50` | — | janela de progresso `1 − real_token_reserves/initial_real_token_reserves`. **Unidade (T4.28e):** o numerador é a conta da curva lida por RPC, em subunidades (6 casas); o denominador vem de `meme_tokens.initial_real_token_reserves`, que o radar grava em **tokens** (793,1 M numa curva padrão) — a admissão converte para subunidades em `denominator_subunits()` ao montar o `MemeContext`. Em 16/09/2026 11:46 BRT, sem a conversão, as quatro primeiras compras do estágio 1 foram recusadas com `progress ≈ −541 546` |
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
| `MEME_CREATOR_UNKNOWN_ALLOWED_IF_DEV_MEASURED` | `false` | **decisão do dono** | T4.28h: com `true`, um `creator_net_sol` desconhecido **passa** no check 10 quando o `dev_share` foi medido e está dentro do teto abaixo. **Padrão desligado**; ausente é política completa (não entra nas cinco do `POLICY_ENV`), e um valor que ninguém consegue ler (`maybe`, `sim`) **recusa o boot** com o nome da variável, como as cinco |
| `MEME_CREATOR_UNKNOWN_MAX_DEV_SHARE_PCT` | `0.10` | **decisão do dono** | o teto dessa permissão — os mesmos 10 % que a mesa já usa no `operator/5` (E1 braço 2). Fora de `[0, 1]` ou ilegível: recusa o boot pelo nome |

**O teto é teto, não meta** — a frase do contrato SPOT vale igual: nada aqui aumenta tamanho para
"chegar" ao teto.

**A permissão do check 10 é do dono, e é a única do motor (T4.28h).** As duas variáveis acima não
são política de capital nem parâmetro de estratégia: são a autorização explícita para o executor
aplicar a mesma regra que a mesa já aplica. Medido em 16/09/2026: das 22 ordens reais do dia, **11**
foram recusadas `creator_flow_unknown` porque o `creator_sold` do fold de 1 min chega +123 a +441 s
depois da criação e a entrada acontece entre 30 e 300 s — enquanto o `operator/5` (E1 braço 2,
`creator_unknown_allowed_if_dev_measured`) já propunha a moeda com `dev_share` medido ≤ 10 %. Ou
seja: **a mesa propunha o que o executor recusava.** Com a permissão desligada (o padrão) nada muda.
Ligada, ela **nunca** salva um criador que se sabe vendedor líquido (`creator_net_seller` continua
reprovando), nunca inventa o `dev_share` e nunca aceita uma leitura velha: o executor só entrega ao
motor um `dev_share` medido, **datado** e com ≤ 600 s (`DEV_SHARE_MAX_AGE_S`, a mesma janela do
`bundled_share`).

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
  de um palpite arredondado. **T4.46 (R43):** o aluguel é parte de `sol_spent_lamports` da compra
  (é caixa que saiu, rotulado à parte como `ata_rent_lamports`/`account_rent_lamports`) e volta ao
  caixa quando a venda fecha a conta inteira (`ata_rent_refund_lamports`, `CloseAccount` na venda
  cheia) — nunca em uma venda parcial, que deixaria a ATA aberta com saldo.

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

### 3.5 A segunda flag — `MEME_LIVE_AUTO_APPROVE` (estágio 1 sem clique, T4.28)

Decisão do Everton (16/09/2026 01:2x BRT, "liga sozinho no estágio 1"; registrada em
`obsidian/06-DECISIONS/2026-09-12-teste-pequeno-meme-real.md`): dentro do escopo escrito do teste
pequeno o robô compra e vende **sem** o clique em "Aprovar (REAL)". O desenho não move a decisão de
dinheiro: **o worker não decide dinheiro real; o executor decide**, com os mesmos 25 checks da §4.

- **O que a flag faz:** a cada tique de entradas o executor lê as propostas `proposed` do conjunto
  `operator` ativo (`meme_rule_sets.kind = 'operator'`, `status = 'proposed'`, `expires_at > now()`,
  `mode = 'paper'` — a proposta é uma só) e abre **uma** delas como proposta real exatamente como o
  `POST …/approve` com `"mode": "live"` faria: a mesma regra e a mesma `UPDATE … WHERE status =
  'proposed'` (`hunter_core.execution.meme.approval`, compartilhado com a API — reusado, não copiado),
  `decided_by = 'executor:auto_stage1'`, `decision = suggested` (os números do próprio conjunto).
  Daí em diante **nada muda**: admissão (§4), sizing (§5), contador do escopo, kill switch relido antes
  de assinar (§7/§9.5). O laço de papel continua preenchendo a mesma proposta em sombra.
- **Quando ela é lida:** só com `ENABLE_MEME_LIVE_TRADING` ligada **e** `small_test_authorization`
  válido nos portões. Ligada sem escopo escrito ⇒ o boot recusa `auto_approve_needs_small_test` antes
  de tocar a chave; ligada com a flag live desligada ⇒ ignorada (um executor inerte não abre nada).
- **O escopo fecha pelas duas contas:** `max_trades` (compras enviadas) e, desde a T4.28, `max_total_sol`
  (a soma do SOL **real** que cada compra confirmada tirou da carteira — `fill.buy_total_lamports`, o
  delta do pagador; a reserva `max_sol_cost` enquanto uma está em voo). Qualquer uma atingida ⇒
  `small_test_scope_exhausted`; antes disso o pedido é **clampado** ao que sobra
  (`admission.small_test.requested_clamped`) — o teto é teto, a última compra nunca o ultrapassa.
- **Freios que só existem neste modo** (todos nomeados no heartbeat, `auto_skipped`): no máximo 1
  compra por tique e por mint; proposta com `age > 60 s` fica para o humano (a `operator` expira em
  180 s para a mão; o robô decide na primeira passada ou não decide); `MEME_LIVE_AUTO_APPROVE_MAX_PER_HOUR`
  (padrão 5, contado das linhas — sobrevive a restart — e **só das propostas que a admissão não
  rejeitou**, T4.28e: uma recusa não gasta vaga, então no estágio 1 o cap é igual ao `max_trades` do
  escopo e nunca trava antes dele; em 16/09 quatro recusas de um mint em 80 s tinham comido 4 das 5
  vagas da hora sem um lamport sair); kill switch bloqueando, programa divergente ou
  escopo esgotado ⇒ o passe não abre proposta nenhuma; e **toda recusa da admissão** de uma proposta
  aberta pelo robô grava a ordem `refused` **e** marca a proposta `rejected` com o motivo em
  `decision.auto_refusal` (mesma transação) — a mesa mostra por quê.
- **Carência depois de uma recusa determinística** (`recently_refused`, T4.28f,
  `MEME_LIVE_AUTO_APPROVE_REFUSAL_COOLDOWN_S`, padrão 120 s, `0` desliga): a mesa repropõe o mesmo
  mint a cada ~20 s (medido em 16/09/2026 11:46–11:48 BRT: o robô abriu a mesma moeda 5 vezes e a
  admissão recusou as 5 por `progress_below_window`), e reabrir uma moeda cuja recusa **não pode
  mudar em dois minutos** só gasta uma leitura RPC da curva, uma linha `refused` e uma proposta
  `rejected`. Contam para a carência apenas as recusas de `hunter_risk_meme.checks` que dependem do
  **mercado ou do banco** mudar — `progress_above_window`, `token_too_old`,
  `token_age_unknown`, `program_not_allowed`, `unsupported_quote`, `progress_denominator_missing`.
  Uma recusa que **o relógio sozinho** limpa nunca segura a retentativa: `token_too_young` (a janela
  abre em `token_age_min_s`, 30 s), `curve_state_stale`, `volume_unavailable`, `marks_incomplete`,
  `wallet_over_max_sol`. A carência **atrasa**, não proíbe: passada a janela o mesmo mint volta a ser
  elegível, e ela nunca deixa uma ordem existir — só deixa de abrir proposta.
- **Espera pela leitura de risco** (`risk_snapshot_pending`, T4.28g): antes de abrir a proposta o robô
  exige que `meme_risk_snapshots` já tenha um `bundled_share` **medido** do mint dentro de
  `RISK_SNAPSHOT_MAX_AGE_S` (600 s — a mesma janela que a admissão aceita). Sem ele **nada é aberto**:
  a linha fica `proposed` para o humano e para o tique seguinte, nenhuma ordem é escrita e o
  heartbeat mostra o nome em `auto_skipped`. Medido em 16/09/2026 (R5): a leitura chegava numa
  **mediana de 103 s depois** da decisão, então abrir antes só queimava a proposta (`rejected` pelo
  robô, portanto perdida também para o clique) numa recusa `bundled_share_unmeasurable` que o próprio
  minuto seguinte desfaria. **Nenhum limite mudou e o check 11 continua recusando o não medido** — só
  a proposta deixa de ser aberta cedo demais. Do outro lado, o `RiskReader` do worker passou a cobrir
  as propostas `operator` em `proposed` **e** `approved` e os mints com ordem live antes do fill (10
  min, `repo_tape.pending_operator_mints`), e a primeira leitura de um mint nunca é adiada pelo teto
  de 1 leitura/mint/5 min.
- **A leitura de risco deixou de ser espera e virou leitura (T4.45).** Antes de abrir a proposta, se
  `meme_risk_snapshots` não tem linha do mint dentro de `RISK_SNAPSHOT_MAX_AGE_S` (600 s) o **executor
  lê o mesmo endpoint** que o `RiskReader` do worker lê (`GET /in-memory-coin/{mint}`, o mesmo cliente
  do adaptador), persiste a linha pelo **mesmo escritor** (`hunter_core.db.meme_risk_snapshots`, só o
  `source` muda: `indexer_rest:/in-memory-coin:executor_on_demand`), refaz o contexto e roda a admissão
  com o dado fresco. **Limites:** prazo duro de 1,5 s (`MEME_RISK_READ_TIMEOUT_S`), no máximo **uma**
  leitura por mint a cada 600 s (contando as que falharam — senão o laço de 1 s marteleria um endpoint
  caído), e a leitura só é gasta no mint que o planejador **abriria** neste tique. **Falha ou prazo
  estourado ⇒ o comportamento de antes**: `risk_snapshot_pending` continua sendo o nome do skip, a
  proposta fica `proposed` para o humano e nenhuma ordem existe. Uma leitura que volta **sem**
  `bundled_share` é gravada (é evidência) mas **não** conta como medida — o check 11 continua recusando
  o não medido. No heartbeat: `risk_reads_on_demand` e `risk_reads_on_demand_failed`.
- **Quem liga:** só o Everton, no `.env` da VPS; o guardião de padrões recusa a flag ligada em arquivo
  rastreado (`infra/scripts/forbidden_patterns.sh`). **Desligar:** a flag em `false` + `update`, ou o
  kill switch (que também pára as aprovações automáticas). **O estágio 2 continua exigindo clique.**
- Implementado em `services/meme-executor/hunter_meme_executor/{auto_approve,refusal_cooldown,scope}.py`, testes
  `tests/test_auto_approve.py` (unit) e `tests/test_live_persistence.py::test_stage_1_*` (Postgres).

## 4. Checks de admissão de uma compra na curva

Todos os checks avaliáveis são registrados em `decision.checks[]` como
`{name, state, value, limit, input_ts, message}`, **mesmo depois do primeiro reprovado** — igual à
§3 do contrato SPOT. `state ∈ passed | failed | unavailable`, e `unavailable` **reprova**.

> **Não confundir com o portão de evento do Lab.** A tabela abaixo é a admissão on-chain
> (`hunter_risk_meme`, este documento). O portão de pesquisa `event_v0/1`
> (`hunter_indicators.meme.event_gate`, EXP-M8) é anterior a ela, na proposta, e tem suas próprias
> recusas — `no_event` e, desde a T4.26b, `event_avoid` (um evento cujo `notes->>'action' = 'avoid'`
> casou esse mint: o casamento em si já é um aviso, nunca um sinal de compra). Documentado em
> `docs/DATABASE.md` §52.3–52.4, não nesta tabela.

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
| 10 | `creator_behaviour` | criador é vendedor líquido; fluxo do criador desconhecido — **exceto** (T4.28h, só com `MEME_CREATOR_UNKNOWN_ALLOWED_IF_DEV_MEASURED=true`) quando o `dev_share` foi medido, datado, fresco (≤ 600 s) e ≤ `MEME_CREATOR_UNKNOWN_MAX_DEV_SHARE_PCT`: aí o check **passa** com `message = creator_unknown_dev_share_measured`, `value` = dev share e `limit` = o teto, e a admissão distingue "desconhecido mas permitido" de "conhecido e bom". Desconhecido com `dev_share` ausente **ou acima do teto** continua sendo `creator_flow_unknown` — o mesmo nome, com o teto publicado em `limit`/`message`, nunca um nome novo | `creator_net_seller`, `creator_flow_unknown` |
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

**A ordem causal, corrigida em T4.28g — e o que continua aberto.** Medido em 16/09/2026 (R5,
`obsidian/03-TRADING/Meme/Estudo-2026-09-16-admissao-real-o-que-recusa.md`): 13 das 16 ordens reais
do dia foram recusadas `bundled_share_unmeasurable` com a linha de `meme_risk_snapshots` chegando
numa **mediana de 103 s depois** da decisão — o executor perguntava antes de o coletor ter motivo
para ter perguntado. Duas mudanças fecham isso **sem tocar em check nenhum**: o leitor de risco
cobre as propostas que a mesa abriu (§3.5) e o robô **espera** a leitura em vez de queimar a
proposta. **O que não foi fechado:** `creator_flow_unknown` (7 das 16 ordens). A ideia de derivá-lo
da cadeia no instante da decisão — ler a ATA do criador e comparar com a alocação inicial dele —
**não é implementável honestamente hoje**: não existe coluna com a alocação do criador na criação
(`meme_tokens` não a tem; o `dev_share` de `meme_features_*`/`meme_risk_snapshots` é o
`devHoldingsPercent` do indexador, uma foto **corrente** cuja primeira amostra chega +114 a +419 s
depois da criação). Usá-la como base faria um criador que largou tudo aos 20 s da moeda ser lido
como "segura ≥ inicial" e **passar** o check 10 — exatamente o dump que o check existe para barrar.
Enquanto a alocação inicial não for persistida na criação (ou a fita cobrir o mint desde o minuto
zero), `creator_net_sol` continua `None` e o check recusa por nome. **T4.28h dá a única saída
honesta enquanto isso, e ela é do dono:** não derivar o fluxo que não existe, e sim deixar o
`dev_share` **medido** responder pelo criador desconhecido — a regra que a mesa já aplica — atrás de
`MEME_CREATOR_UNKNOWN_ALLOWED_IF_DEV_MEASURED`, desligada por padrão (§3.1). Isso **não** resolve o
caso do criador que largou tudo antes da primeira medição: a foto é corrente, e por isso a permissão
é uma decisão escrita e reversível, não o novo padrão.

**O dado passou a existir no instante da decisão (T4.45, 16/09/2026).** O balanço do dia — 58 ordens
reais, **0** fills, `creator_flow_unknown` em 27 e bundle ausente em 36 das 39 ordens na janela — não
mediu limites errados: mediu **perguntas feitas antes de existir resposta**. Duas mudanças, nenhuma
delas em check, limiar ou janela de frescor:

1. **O executor lê o risco sozinho, sob demanda** (§3.5). Sem linha fresca em `meme_risk_snapshots`, ele
   lê o mesmo `/in-memory-coin` com prazo de 1,5 s, grava pela mesma função do worker
   (`source = indexer_rest:/in-memory-coin:executor_on_demand`) e reconstrói o contexto. Falha ⇒ o de
   antes: `bundled_share` continua `None` e o check 11 recusa `bundled_share_unmeasurable`.
2. **O fluxo do criador vem da cadeia contra a compra registrada do dev.** A `0048`
   (`docs/DATABASE.md` §56) grava `creator_initial_tokens`/`creator_initial_sol` no instante do `create`
   — a compra do dev que o próprio frame do PumpPortal traz (`initialBuy`/`solAmount`, em **tokens** e
   SOL). Com `creator_sold` do fold ainda `NULL` **e** base conhecida `> 0`, a admissão lê a ATA do
   criador (`confirmed`, prazo de 1,5 s) e conclui `creator_net_sol = −1` quando o saldo está abaixo de
   `inicial × (1 − MEME_CREATOR_SELL_TOLERANCE_PCT)` (padrão 0,02), `+1` caso contrário, com
   `creator_flow_source = 'chain_ata_vs_initial'` no JSON da admissão. **Isto é o que a T4.28g §2.3 dizia
   faltar** — a base da criação — e por isso a derivação deixou de ser desonesta: um criador que largou
   tudo aos 20 s agora lê `−1` (`creator_net_seller`), não `+1`. O que **não** mudou: `creator_sold`
   conhecido sempre vence (fato de fita > inferência de saldo); base `NULL` ou `0` ⇒ nada é derivado e o
   nome continua `creator_flow_unknown`; conta inexistente com base registrada é **dump**, não "não
   medido" (é o oposto da regra do `creator_watch`, que não tem base contra o que comparar). A permissão
   da T4.28h (§3.1) fica como está — ela deixa de ser necessária no caso comum, não é revogada.

**O que muda em relação ao SPOT, e por quê:** não existe `book_depth` nem `spread` — não há livro
(T4-MEME-RADAR §0). O papel deles é feito por **dois** checks que a curva permite fazer melhor: o
`price_impact` (22), que é **exato** porque sai da fórmula das reservas, e a `participation` (21),
que mede quanto do fluxo real somos — e cujo denominador (`curve_volume_1m_sol`) vem, desde a T4.41,
**do lote `activity_1m` antes da fita por mint** (KB-0116: o lote acompanha a cadeia, sinal igual
85,7 % e razão mediana 1,00; a fita escrevia 0,00 na mediana e inflava a participação). E não existe `beta_validity`: β contra o BTC numa moeda de 10
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

**E nunca mais do que o SOL real na curva (T4.27).** Numa moeda Mayhem o agente empurra a reserva
*virtual* de SOL sem pagar SOL de verdade (`set_mayhem_virtual_params`, `docs/PUMPFUN-ONCHAIN.md`
§1.3): KAT (15/09 17:37 BRT) foi de 23,9 para 1 977 SOL de `virtual_sol_reserves` em 60 s com 5
holders e `real_token_reserves` caindo só 7 %. A fórmula da curva (`S·q/(T+q)`) cotava uma venda que o
cofre não tinha como pagar. Desde a T4.27 a marca e a venda de papel são
`sell_all_value_sol(reserves, tokens, fee, real_sol_reserves=…)` (`hunter_indicators.meme.curve`): o
**bruto** da venda é limitado ao `real_sol_reserves` da mesma fotografia e a taxa incide sobre o que
sai. O teto vale para toda moeda que não seja **sabidamente** padrão e ainda esteja na curva
(`Snapshot.sell_cap_sol`: a foto da cadeia diz o bit `is_mayhem_mode`; senão o `mayhem_enabled` do
token; desconhecido mantém o teto, que numa curva padrão nunca prende — o cofre é o que os compradores
pagaram); numa curva **completa** não há teto (o SOL foi para a pool e a marca honesta é a fita, T4.11).
A linha diz quando o teto prendeu: `exit.real_sol_cap_applied` e `exit.mark_basis`
(`curve` | `real_sol_reserves`). As apostas fechadas em Mayhem antes disso são reclassificadas
`indeterminate` com motivo `mayhem_virtual_sol` (`infra/scripts/meme_reclassify_mayhem.py`, auditado,
dry-run por padrão) — o fechamento diário já as deixa fora. **O real herda a regra:** um executor nunca
precifica uma saída acima do SOL real da curva; o `mcap_sol` das séries continua **teórico** (rótulo)
e `mcap_executable_sol` nasce ao lado (`0042`, `T4-MEME-RADAR.md` §4).

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

### 7.1 Os portões também são relidos em voo (T4.28d)

No mesmo tique de 10 s do kill switch o executor dá **um `stat`** no `meme_gates.json` e só **lê o
arquivo quando o `mtime` mudou** — medido em 16/09/2026 (11:3x BRT): o Everton subiu
`small_test_authorization.scope.max_total_sol` de 0,25 para 0,72 na VPS e o `hb:meme:executor`
continuou publicando `wallet_max_sol 0.25` até um `docker restart`; reiniciar o processo que segura a
chave e as posições abertas não pode ser o preço de mudar um número que o dono escreveu.

- **Válido ⇒ política recomposta e trocada em memória**, pela mesma função do boot
  (`config.effective_limits`, `min` dos cinco `MEME_*` com o escopo escrito) e sempre a partir da
  política do ambiente — recompor sobre a política já apertada nunca deixaria um escopo **crescer**.
- **Inválido (JSON quebrado, `valid_until` vencido, Portão C desligado, escopo sumido com o robô
  armado, arquivo apagado) ⇒ o kill switch é travado `gates_invalid:<motivo>`** — a mesma trava
  latched desta §7, que só o dono destrava — e a política **anterior** fica em memória só para o
  heartbeat relatar. O laço não cai: derrubar o processo com posição aberta é pior que pará-lo.
- **Um tique de carência antes de travar por falha de leitura (T4.28f).** O dono edita o arquivo com
  `nano` na VPS — escrita **não atômica**, no lugar —, então um tique pode dar `stat` e ler o arquivo
  **pela metade**. Por isso uma falha de *parse* (`gates_file_invalid`, `gates_file_missing`) na
  primeira vez é **adiada**: nada trava, nada é trocado, a política anterior continua valendo e o log
  registra `meme_executor_gates_reload_deferred`; o **tique seguinte** decide — se o arquivo parseia,
  é só uma releitura normal; se falha de novo (mesmo `mtime` ou um novo), **trava**. Invalidade
  *semântica* (vencido, Portão C desligado, escopo sumido com o robô armado) é um arquivo completo
  dizendo não e **trava na hora**. O conselho de gravar com `mv`/`sed -i` (atômico) continua valendo:
  a carência é a segunda rede, não a primeira.
- No heartbeat, enquanto a carência corre, `gates_reload_error = "deferred:<motivo>"`; depois da
  trava é o motivo cru (`gates_file_invalid`, …).
- **Contador nenhum é zerado por uma releitura.** `max_trades` e `max_total_sol` continuam contados
  contra `meme_live_orders` (§12, variante); um escopo que **encolheu abaixo do que já foi gasto**
  não levanta erro: `remaining_sol` trava em 0 e a admissão recusa com o `small_test_scope_exhausted`
  de sempre.
- Publicado em `hb:meme:executor`: `gates`, `gates_mtime`, `gates_reloaded_at`, `gates_reload_error`
  (vazio, `deferred:<motivo>` ou o motivo travado).

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
>
> **T4.8c (15/09/2026, `docs/PUMPFUN-ONCHAIN.md` §6d):** segundo deploy da semana (slot 447228373,
> 07:34:32 BRT) — desta vez a conta da IDL on-chain *foi* republicada (40→47 instruções); `buy`/`sell`
> legados e `TradeEvent` continuam byte a byte iguais (paridade provada com um `buy` e um `sell` reais
> de hoje, `t48c_rpc_tx_{buy_legacy,sell}_raw.json`); taxas no mesmo tier (95/30 bps). Uma instrução
> nova (`sell_v2`) apareceu no roteador do site — não construída por este pacote (documentada, sem
> paridade reivindicada). `EXPECTED_PUMP_PROGRAM` (`program_identity.py`) aponta para os valores de
> hoje; os de T4.8b ficam em `PREVIOUS_PUMP_PROGRAM`/`PUMP_PROGRAM_HISTORY`. Achado à parte, não deste
> upgrade: `BondingCurve.is_holder_reward` (M-P34/`KB-0096`) é um byte que já existia desde pelo menos
> 12/09 (`decode.py` simplesmente não olhava além do byte 115) — `decode.py` agora o lê. Simulação
> mainnet pelo caminho do executor: `buy` ok numa moeda clássica (103 096 CU), numa `is_holder_reward
> = true` (104 600 CU) e numa Mayhem (87 286 CU); `sell` ok na clássica (62 037 CU) e na Mayhem
> (49 556 CU) — o `sell` de uma moeda HR não foi obtido nesta tarefa (a única com atividade real era
> cotada num token custom, recusada por nome antes de simular; a mais barata ainda não tinha comprador
> real na cadeia — `t48c_simulation_proof_mainnet_raw.json`).

> **T4.29c (16/09/2026):** as taxas deixaram de ser uma constante datada. `fee_config.py` decodifica
> a conta `FeeConfig` do **programa de taxas** (`pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ`, PDA
> `["fee_config", <programa>]`, a mesma conta que o índice 12 de todo `sell` real desde 12/09 carrega) e
> `quote.curve_fee_bps` seleciona o tier pelo *market cap* com a regra exata do programa
> (`calculate_fee_tier`: vence o maior limiar `<=` o market cap; abaixo do primeiro limiar, o primeiro
> tier — `docs/FEE_PROGRAM_README.md`, commit `81091419…`, sha256 `c03c0cc7…`). **Leitura ao vivo
> (slot 447 586 137, `tests/fixtures/pumpfun/rpc_fee_config_raw.json`): a conta da curva tem UM tier,
> limiar 0, lp 0 / protocolo 95 / criador 30** — ou seja 1,25 %, exatamente a constante datada, e
> independente do market cap; a tabela de 25 tiers da `fees.png` está na conta da **PumpSwap**
> (`t429c_rpc_fee_config_amm_raw.json`), para pools. Quando a conta não pode ser lida, o retorno é a
> constante e o chamador loga `meme_fee_config_unavailable`. O executor (`build.fee_bps`) **ainda não**
> chama isso — o gancho de uma linha está descrito em `.claude/state/notes-T4.29c.md` (`build.py` é de
> outro agente nesta leva).
>
> **A venda numa curva `is_holder_reward = true` deixou de ser fé** (o concern nº 1 da T4.8c): simulada na
> mainnet pelo caminho do executor em 16/09 18:21 UTC (`infra/scripts/meme_simulate_trade.py`, moeda
> `Bo5vHuDB…`, detentor real achado na fita pública, `ok=True`, 53 041 CU, **nada assinado, nada enviado** —
> `t429c_simulation_proof_hr_sell_raw.json`). Duas coisas que a simulação provou e que o concern nº 2 da
> T4.8c deixava em aberto: (1) `GetFeesWithQuoteMint` devolveu `lp 0 / protocolo 95 / criador 30`, idêntico
> ao tier que o `FeeConfig` decodificado seleciona; (2) o `TradeEvent` veio com
> `holder_rewards_bps = 30` e `holder_rewards = 112 933` **iguais** a `creator_fee_bps`/`creator_fee` — ou
> seja, na moeda HR a taxa do criador é a mesma, só muda quem recebe; **não** é uma taxa a mais, e
> `quote_sell` com 95 + 30 bps reproduz o evento ao lamport. O custo modelado continua correto.

> **T4.52a (17/09/2026): a decisão de compra deixou de esperar o próximo tick do executor.**
> R55 (`.claude/state/notes-R55.md`) mediu a latência real das 5 primeiras compras: 6,3 s mediana
> porta a porta, com **4,8 s (76 %) gastos entre a proposta ser escrita e o `entries_once` a
> enxergar** — o radar (`lab.py`, T4.2g) escreve `meme_proposals` no seu próprio tick e o executor só
> a lia no ciclo seguinte do seu poll (`config.loop_s`). O executor agora acorda no instante em que a
> proposta é gravada: o radar publica em `meme:proposals:wake` (Redis pub/sub,
> `hunter_meme_worker.wake.wake_publisher`, chamado por `LabContext.wake` uma vez por tick que
> gravou pelo menos uma proposta — tanto pela porta do minuto quanto pela pista rápida de 15 s,
> T4.43) assim que a escrita comita; `hunter_meme_executor.wake.ProposalWakeListener` assina esse
> canal e liga um
> `asyncio.Event` que o loop de entradas espera com `config.loop_s` como **tempo limite, não mais
> como único gatilho** (`main.forever(..., wake_event=...)`). **Não é `LISTEN`/`NOTIFY` do Postgres**
> — `docs/SPEC_REVIEW.md` R7 proíbe no projeto inteiro porque toda conexão passa por um pooler em
> modo transação, que uma sessão de `LISTEN` não sobrevive. Perder uma publicação (Redis caiu, rede
> falhou) custa só o próximo tick do poll — nunca uma proposta, cuja única fonte de verdade continua
> sendo a tabela; o listener reconecta sozinho com backoff exponencial com jitter. Nada do motor de
> admissão, do kill switch, do sizing ou do simulador mudou — a proposta chega mais cedo ao mesmo
> código. Medido nos testes deste pacote (Redis real via testcontainers): publicação → `asyncio.Event`
> setado em bem menos de 200 ms (`test_wake_integration.py`). O heartbeat (`hb:meme:executor`) agora
> publica `proposal_pickup_lag_s_p50`/`_max` (janela das últimas 200 propostas vistas) para que o
> número de R55 seja relido depois do deploy. O tick de 15 s do próprio radar (fila do radar até a
> proposta existir) não muda nesta tarefa — fica para T4.52b.

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

8. **O rastreador não solta uma moeda com aposta aberta (T4.16b).** A regra do item 7 supunha que a fotografia
   faltava porque o mercado parou; em 12/09 faltou porque o **rastreador** expulsou a moeda pelo teto de 120 (cinco
   apostas, última fotografia 13 min antes do `time_stop`). Agora mints com aposta de papel aberta, posição real aberta
   ou proposta pendente são **fixados** (relidos das linhas a cada tique; nunca caem pelo teto nem pela janela), o teto
   vale só sobre as não fixadas (`cap − |fixadas|`, nunca < 20), e antes de fechar `indeterminate` o laço pede **uma**
   leitura pontual da curva pela cadeia e fecha por ela quando ela vem (`meme_lab_bet_closed_by_point_read`).
   Só sem resposta o desfecho fica indeterminado.

9. **A mesa propõe pela porta E1 e diz o plano (T4.19).** Desde a `0033` o conjunto `operator` ativo é o `operator/3`:
   a **mesma** porta e as **mesmas** exclusões do `flow_v2/1` (E1 + E2, `FLOW_V2_PARAMS` composto em SQL), relógio de
   15 s, com só dois números próprios — a proposta ao operador espera **180 s** (`params.ttl_s`; uma compra à mão precisa do
   minuto extra) e no máximo 2 abertas. Na mesma linha de 15 s, `flow_v2/1` e `operator/3` propõem a mesma moeda: a de
   pesquisa nasce aprovada por `rules`, a do operador nasce `proposed`; aprovada, o fill é o do item 7 (primeira fotografia
   depois da decisão). Cada proposta `operator` grava `suggested.manual_plan` na hora da proposta — "Comprar 0,05 SOL de
   <TICKER> até HH:MM:SS (proposta expira). Vender até HH:MM (30 min) — antes disso se triplicar (3×), se recuar 35 % do
   topo depois de 1,5×, se cair pela metade (−50 %), se o dev vender, ou se a linha de suporte quebrar." — todo número
   lido dos `params` (o trailing incluído: o motor vende um recuo 2× → 1,3×, e o texto tem de dizer o mesmo que a regra),
   horas de Brasília; a API só repete o texto, nunca o compõe. O plano é o que o operador executa à mão; a carteira observada (T4.12) grava o que ele
   fez de fato, e o papel continua marcando a aposta por conta própria.

10. **O segundo braço da porta E1 (T4.21).** Com a fita por lote viva, a E1 congelada (`snipers ≤ 2`, holders subindo)
    não propôs nada em 30 min — 0 de 13 moedas com demanda tinham < 6 snipers. Desde a `0034` a mesa propõe pelo
    `operator/4` (braço 2: snipers ≤ 10, ≥ 20 holders não caindo, criador desconhecido só com `dev_share` medido ≤ 10 %,
    progresso **ou** mcap subindo), pré-registrado como `descartar` na EXP-M5; o braço 1 (`flow_v2/1`) continua ativo e
    medido ao lado. Nenhuma outra régua muda: 0,05 SOL, 180 s, alvo 3×, trailing 35 % após 1,5×, 30 min, dev, pedigree.

11. **A orgânica lenta (T4.22, EXP-M7).** O primeiro conjunto que **não** compra recém-nascidas: entra na série de
    minuto entre 3 e 30 min, com a curva em 10–30 % e subindo, ≥ 20 holders subindo, top-10 ≤ 30 %, snipers ≤ 2, dev
    ≤ 10 %, criador não vendedor, E2 — e **segura pela migração** (`exit_on_migration = false`, marca pela pool; alvo 5×,
    trailing 40 % após 2×, 60 min, piso 50 %). Pré-registrado como `descartar`; nada real depende dele.

12. **A venda do criador vista na cadeia (T4.2h), na posição real e com a latência medida (T4.2h-b).** O motivo de
    saída que mais custou em 12/09 (`creator_dump`, 22 de 35) chegava 14 min depois pela fita. O laço lê a conta de
    tokens do criador pela cadeia a cada 15 s e o primeiro decréscimo entre duas leituras vira `creator_sold_seen_at`;
    conta ausente é `creator_ata_missing` — não medido, nunca "o dev não vendeu". Três coisas mudam na T4.2h-b:

    - **A posição real entra no laço** (`0038`): `meme_live_positions` ganha as **mesmas três colunas**, com os mesmos
      CHECKs, e o mesmo laço marca papel e dinheiro real na mesma transação. O executor lê `creator_sold_seen_at` no
      **tique de 5 s** de `exits.py` (`OpenPosition.creator_dump_seen`: venda vista na cadeia **ou** `creator_sold` da
      fita; `None` da fita nunca é venda). A precedência da §6 não se move — `sell_now` do operador e fechamento de
      emergência continuam acima do dump, então uma observação do radar nunca passa na frente do kill switch. Nenhum
      grant se move: a API continua só pedindo a venda.
    - **Uma fotografia, não duas.** A medição de 15/09 (16:13 BRT, 27 vendas vistas) deu **149 s** entre a venda vista e
      a saída: o motor de papel avaliava a saída *por fotografia*, então a venda exigia uma foto para decidir e a
      seguinte para precificar. A venda do criador é uma observação com **relógio próprio** — como o `sell_now` do
      operador —, então o `exit_intent` nasce com `decided_at = creator_sold_seen_at` e `trigger = "creator_watch"`, e a
      **primeira** fotografia posterior precifica. O `exit_on_creator_dump` do conjunto continua valendo. Provado em
      testcontainer: venda vista → saída ≤ 30 s, medido na linha
      (`services/meme-worker/tests/test_creator_watch_persistence.py`).
    - **A latência é publicada, medida das linhas.** `creator_watch_sale_to_exit_s_p50/_p95/_n` no heartbeat e em
      `GET /meme/sources`, percentil por posto sobre as saídas mais novas de papel **e** de posição real — nunca de um
      contador em memória, então um reinício não zera a única prova de que o laço é rápido o bastante. Ao lado:
      `creator_watch_mints`, `_live_mints` (quantos são de dinheiro real), `_calls_60s`, `_drops_1h`, `_missing`,
      `_cycle_s`. Número não medido é `""`, nunca `0`.

13. **Dois braços irmãos da E1, contradizendo o próprio pré-registro (T4.23).** O fechamento de 13/09 mediu
    `snipers > 2` a R médio +0,25 (n = 17) contra −0,28 nas demais (n = 49) e `top10_share` 0,1767–0,257 a +0,25
    (n = 14) contra −0,25 nas demais (n = 52) — os dois contradizem a E1 congelada (`snipers ≤ 2`, sem piso em
    `top10_share`). Pela régua isso não move o que está vivo: planta `flow_v2/3` (braço 2 + `min_snipers 3`) e
    `flow_v2/4` (braço 2 + o piso e o teto do top-10), ambos pré-registrados `descartar`, medidos ao lado de
    `flow_v2/1` e `flow_v2/2`; a mesa (`operator/4`) não muda.

14. **A reincidência do criador (T4.24, EXP-M6 braço 2).** Medido no banco da VPS (176 apostas de papel,
    15/09/2026): das 89 apostas com criador com moeda anterior, as 31 em que ele **já tinha vendido** numa moeda
    anterior pagaram R médio −0,168 (contra −0,140 nas outras 145), 26 das 85 saídas `creator_dump` e só 4
    ganhas (13 % contra 19 %). `creator_prior_dump_count` (`hunter_indicators.meme.pedigree`) conta, em qualquer
    janela até a criação da moeda julgada, moedas anteriores do mesmo criador vendidas por nós já sabidas — pela
    fita (`meme_features_1m.creator_sold`), pela vigilância da cadeia (`creator_sold_seen_at`, T4.2h) ou por uma
    aposta nossa que saiu `creator_dump`; `creator_prior_dead_count` (moedas que caíram < 20 % do topo em 30 min)
    é diagnóstico, nunca uma recusa. `evaluate_repeat_dumper` recusa `creator_repeat_dumper` quando o contador é
    ≥ 1 — parâmetro por conjunto `pedigree_repeat_dumper`, desligado por padrão; `PEDIGREE_V1` (E2 v1, criador em
    série/clone de ticker) não muda. `flow_v2/5` e `operator/5` (`0039`) ligam o filtro — a mesa passa a usá-lo,
    `operator/4` aposentado; `flow_v2/1`/`flow_v2/2` continuam medidos ao lado, previsão `descartar`.

15. **A via rápida segue a moeda fixada além dos 300 s, e `time_stop` sem foto depois vira
    `series_ended` (T4.33, KB-0113).** Medido em 15/09: `fast_lane.young_mints` largava toda moeda aos
    300 s de vida, aposta aberta ou não — 91 % das séries de 15 s pararam exatamente aí (última foto
    aos 292 s medianos), e 8 das 11 saídas `time_stop` do dia fecharam numa foto de até 32 min de
    idade, sem nenhuma observação posterior — o fecho **foi** precificado, mas o rótulo dizia
    `measured` de um instante que não existia mais. Duas mudanças, independentes:
    - `young_mints` agora admite o conjunto **fixado** (`tracker.pinned` — aposta de papel aberta,
      posição real aberta ou proposta pendente, T4.16b) até `MEME_FAST_LANE_PINNED_MAX_AGE_S`
      (1 800 s por padrão), em vez do teto de 300 s que vale para as demais moedas; sem query nova
      (o pin já é conhecido em memória pelo rastreador), custo medido +2 % de linhas/dia.
    - O fechamento diário (`infra/scripts/meme_reclassify_series_ended.py`, o mesmo padrão auditado
      do `meme_reclassify_indeterminate.py`) reclassifica um `time_stop` `measured` como
      `outcome_quality = indeterminate` com `outcome_quality_reason = 'series_ended'` (nome fixo,
      não frase — o gêmeo mecânico do `no_snapshot_in_window` do laço) quando `meme_features_1m` não
      tem nenhuma linha precificada mais de 90 s depois do `exit_at` dentro dos 35 min seguintes.
      A linha mantém seus números; a soma continua excluindo-a, agora por um motivo que se nomeia.
      Dry-run por padrão; `--day`/`--bet-id` reaplicam sobre dias já fechados.

16. **Por que a moeda X não virou proposta (T4.35, R27).** O estudo de 16/09/2026
    (`obsidian/03-TRADING/Meme/Estudo-2026-09-16-a-porta-real-versus-a-replica.md`) gastou uma hora de
    perícia em SQL para provar que a Kintsugi foi recusada por `snipers_above_max` às 16:20 — porque
    `operator/5` foi editado quatro vezes naquela hora sem nenhuma linha guardando o teto anterior, e o
    único registro por decisão do portão (`meme_lab_ticks.refusals`) é uma contagem por tique, nunca por
    moeda. Duas respostas, a partir de agora: `infra/scripts/meme_rule_set.py --history NAME/VERSION`
    imprime a linha do tempo de cada parâmetro que o operador mudou num conjunto (`meme_rule_set_param_history`,
    `docs/DATABASE.md` §54.1), e `meme_gate_refusals_by_mint` (§54.2) guarda, por moeda e por instante, a
    proposta (`refusal IS NULL`) ou a recusa por um único critério (o quase-passou) — pequena por
    construção, porque a maioria das recusas falha vários critérios de uma vez e não vale a pena manter.
    Uma consulta por `mint` nessa tabela, cruzada com `--history` do conjunto vigente naquele `as_of`,
    responde em segundos o que antes custava uma reconstrução foto a foto:

    ```sql
    SELECT as_of, refusal, value, "limit"
    FROM meme_gate_refusals_by_mint
    WHERE mint = 'Kintsugi...' AND rule_set_id = '<uuid do conjunto>'
    ORDER BY as_of;
    ```

    **Ligada ao tique de 15 s desde T4.43** (`lab_fast.fast_gate_step`): `evaluate_gate` passou a ser
    chamado uma vez por linha (não mais em lote), o que expõe a recusa da própria linha em vez da soma
    do tique; `docs/DATABASE.md` §54.2 tem o desenho completo (o corte `already_open`, o cálculo de
    `value`/`limit`, o teto por tique e a poda diária).

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

**Estágio 1 sem clique (T4.28, §3.5).** Dentro dessa variante o dono pode, também por escrito, dispensar
o clique por proposta: `MEME_LIVE_AUTO_APPROVE` faz o executor abrir a proposta `operator` como real
com a **mesma** regra e a **mesma** escrita da mesa (`decided_by = executor:auto_stage1`), e o escopo
passa a fechar também por `max_total_sol` (SOL real gasto). O que a flag **não** faz: afrouxar um check,
mudar o sizing, aprovar fora do escopo escrito (sem `small_test_authorization` o boot recusa
`auto_approve_needs_small_test`), ou valer para o estágio 2 — esse continua exigindo o clique.

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
