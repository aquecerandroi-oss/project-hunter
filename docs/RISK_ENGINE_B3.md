# Risk Engine B3 — contrato v1.0 (robô MT5 do Everton na Rico)

**Status: contrato normativo congelado para implementação (tarefa R0a de `docs/design/robo-b3-mt5.md` §9), depois
de quatro rodadas de revisão da Astra (§15). Nenhum código existe ainda. Nenhum número aqui autoriza dinheiro real.**

**Versão 1.0, 2026-10-17.** Irmão de `docs/RISK_ENGINE.md` (v2.5, SPOT paper) e de `docs/RISK_ENGINE_MEME.md`
(v0.1, pump.fun). É o **contrato de coordenação** que quatro tarefas implementam em paralelo, cada uma do seu
lado da fronteira: R1 (motor puro `hunter_risk_b3`), R2 (adaptador MT5 `hunter_exchanges.mt5`), R5 (serviço
`services/b3-robot`) e R7 (EA vigia `infra/mt5/HunterVigia.mq5` e `infra/scripts/b3_kill.py`). R3 (schema) e
R4 (API) usam os mesmos nomes de estados, motivos e campos. **Um nome que aparece aqui entre crases é o nome
no código, no banco e no evento**; mudar um nome é mudar este documento primeiro.

**O que este documento é:** as três máquinas de estado (autoridade da instância, intenção de entrada, posição),
a queda do processo em cada intervalo e o que a partida faz em cada caso, a saída pelo colchete, o kill switch,
os 25 checks como dado, o sizing, os valores iniciais, os dois batimentos e a matriz de falhas, com as
invariantes que os testes provam.

**O que este documento não é:** não é o ADR. A exceção "live B3 antes da Fase 4" é a D1 do desenho e está
registrada pelo Everton no ADR 0007 (`docs/decisions/0007-robo-b3-mt5-excecao-live.md`, tarefa R0b). Este
contrato não abre a exceção sozinho nem a amplia; o escopo (WIN só, 1 contrato, 1 operação por dia, um host,
revisão em 31/12/2026) é o do ADR. Também não é estratégia: a regra que o robô executa (H-038) é pré-registro na
[[Fila de Hipoteses]], e nada aqui afirma que ela tem vantagem.

**Origem:** desenho `docs/design/robo-b3-mt5.md` (commit `35b174cd`, DECISÃO CONJUNTA com a Astra na rodada 6;
transcrição `.claude/state/dialogue-robo-b3-mt5.md`, síntese `obsidian/06-DECISIONS/Dialogos/robo-b3-mt5.md`).
Onde este contrato **precisa** decidir algo que o desenho deixou em aberto, a decisão vem marcada **[R0a]** com o
motivo; onde a Astra mudou algo nesta tarefa, **[Astra R0a-n]** (síntese em
`obsidian/06-DECISIONS/Revisoes-Astra/R0a-risk-engine-b3.md`).

---

## 0. O que a base já sabe, e o que isso fixa aqui

| Fonte lida (17/10/2026) | O que diz | O que fixa neste contrato |
|---|---|---|
| `obsidian/00-HOME.md` | toda entrada é AGENTE → PROPOSTA → RISK ENGINE → EXECUÇÃO; paper, memes e spot são operações distintas | o robô B3 é uma quarta operação, com motor próprio e a mesma forma: proposta persistida → decisão persistida → claim → ordem |
| `KB-0149` §1 e §4.23 | 72 % do prejuízo da mesa real foi custo; custo medido por praça antes de operar | a tarifa entra no risco de toda operação e na perda do pregão (§8.3); sem tabela de custo com fonte e data o robô **não arma** (`fee_schedule_missing`) |
| `KB-0149` §4.20–§4.21 | o RPC gratuito parou a mesa 2 dias sem alarme; `.env` mudado não chega ao processo | dois batimentos (§10) e cão de guarda fora do PC; todo limite é dado relido em voo; K1 é a única leitura de ambiente, e só na partida |
| `KB-0149` §5.27–§5.28 | a revisão adversária pagou-se; ligar critério novo em dinheiro real não é sombra | as invariantes da §12 são testes obrigatórios; sessão demo T1–T17 antes de conta real (ADR 0007) |
| `docs/RISK_ENGINE.md` §1, §3, §5, §7, §10 | motor puro; `checks[]` completos mesmo depois da 1.ª reprovação; `unavailable` reprova; kill switch "o mais restritivo"; saída é intenção durável, tentativa não | copiado como forma: §8 (checks), §7 (kill switch), §4 (intenção de saída derivável e durável) |
| `docs/RISK_ENGINE_MEME.md` §0, §7, §7.1, §12 | portões distintos; trava diária *latched*; portões relidos em voo; "aprovação antiga não é salvo-conduto" | `pre_send_gate` (§3.4); trava de rejeições e de inversão *latched*; a trava diária do B3 volta no pregão seguinte (D8, diferença declarada §13) |
| desenho `robo-b3-mt5.md` §1–§10 | o contrato de origem | todos os nomes abaixo |
| `Dialogos/robo-b3-mt5` (6 rodadas) | um só remetente; saída só pelo colchete; nenhuma mutação sem identidade e autoridade; SLTP incerto bloqueia nova modificação; `unknown` atravessa instâncias | §2–§6 são a tabela única de transições que a Astra pediu na rodada 5 ("fonte única de R0a, API, serviço e runbook") |
| `Fila de Hipoteses` → H-038 | sinal até O+90, entrada [C−30, C−25], stop 0,5 %, saída por tempo em C; o real não rotula a hipótese | o plug-in é dado de entrada (§8.1); a saída da H-038 em C começa o colchete e grava pretendido × efetivo (§5.6) |

## 1. Vocabulário congelado

### 1.1 Identidades

| Nome | Forma | Quem cria | Para quê |
|---|---|---|---|
| `instance_id` | UUIDv7, novo a **cada** partida do processo; nunca reaproveitado | o robô, no passo 1 da partida (§6.5) | toda autoridade, aprovação e claim é desta instância e de nenhuma outra |
| `host_hash` | `sha256(utf8(MachineGuid do Windows))`, hex 64 | o robô | a autoridade vale para um host (D15) |
| `account_hash` | `sha256(utf8(str(login) + "\|" + server))`, hex 64, minúsculas | robô e EA calculam igual | identidade da conta sem gravar o número; o Everton registra o hash esperado (`registered_account_hash`) |
| `authority_id`, `fencing_token` | UUIDv7 e inteiro crescente por conta | a API, em "Conceder gestão" | o claim de entrada compara o token; a corretora **não** conhece o token (residual declarado, §6.6) |
| `proposal_id` | UUIDv7 | a API, ao gravar a proposta | chave de idempotência de toda a cadeia de entrada |
| `client_order_id` | `"HB" + base32_rfc4648(sha256(proposal_id.bytes)).rstrip("=").upper()[:16]` (18 caracteres) | o robô | gravado no `comment` da ordem de entrada; procurado na resolução de `unknown` |
| `magic` | inteiro de `b3_strategy_magics(strategy_key, strategy_version) → magic`, único por organização, **nunca reaproveitado** | a API, no armamento da versão | atribuição pela cadeia de negócios (§4.5); `robot_magics` = o conjunto de todos os já atribuídos à organização |
| `position_id` | `POSITION_IDENTIFIER` da corretora, qualificado pelo `account_hash` | corretora | **identidade da máquina C e do slot SLTP**; chave da cadeia de negócios (`history_deals_get(position=…)`). Não muda durante a vida da posição `[Astra R0a-4]` |
| `position_ticket` | `POSITION_TICKET` atual | corretora | o ticket que vai em `MqlTradeRequest.position`; **pode mudar** por operação de serviço no servidor, por isso nunca é identidade |
| `request_position_ticket` | o `position_ticket` efetivamente enviado numa requisição SLTP, imutável | o robô, ao montar a requisição | correlação e prova P3 (§4.3, invariante I-SL-4) |
| `sltp_request_id` | UUIDv7 por requisição SLTP | o robô, **antes** de enviar | correlação do resultado e da resolução de incerteza (§4.3) |
| `session_date` | data local do pregão (`America/Sao_Paulo`) | grade | contagens do dia, âncora da perda, vencimento da autoridade |

### 1.2 Enums (iguais no Postgres, no Pydantic e no TS gerado)

```
b3_authority_phase       = read_only | management | entries          # read_only não tem linha no banco
b3_authority_status      = active | revoked | expired
b3_entry_intent_status   = proposed | rejected | approved | expired | submitting | aborted_before_send
                         | working | partially_filled | filled | cancel_requested | canceled
                         | broker_rejected | unknown | resolved_manual
b3_unknown_cause         = claim_ack_lost | send_no_result | send_timeout | ipc_hang | process_died
                         | cancel_no_result | result_not_persisted | journal_lost | heartbeat_in_flight
b3_position_state        = unprotected | protected | degraded | exiting | exit_overdue | closed | unattributed
b3_degraded_reason       = naked_after_grace | repair_rejected | floor_unplaceable | protection_unknown
b3_sltp_slot             = idle | in_flight | unknown
b3_sltp_request_status   = intended | not_sent | done | rejected | unknown | moot | resolved_manual
                         # intended = gravada e possivelmente enviada; nunca rebaixa um estado terminal (§4.3)
b3_exit_reason           = time_exit | session_flatten | emergency | reversal | overnight_carry
b3_close_cause           = server_sl | server_tp | bracket_sl | bracket_tp | manual | broker_compulsory
                         | unexplained
b3_attribution           = attributed | foreign | ambiguous | unreadable
b3_check_state           = passed | failed | unavailable
b3_kill_state            = ACTIVE | WARNING | TRADING_DISABLED | EMERGENCY     # mesmo enum do SPOT
b3_kill_cause            = daily_loss_limit | broker_reject_breaker | reversal_detected | manual_route
                         | agent_command | owner_command | owner_button
```

Nomes compostos usados em alertas e na tela (não são colunas, são derivados): `exit_in_flight` = posição em
`exiting`/`exit_overdue` com `sltp_slot = in_flight`; `exit_unknown` = posição em `exiting`/`exit_overdue` com
`sltp_slot = unknown`; `protection_in_flight` / `protection_unknown` = o mesmo com a posição em
`unprotected`/`protected`/`degraded`.

## 2. Máquina A — autoridade da instância e armamento

**Uma** linha `b3_robot_authority` por conta, **uma** validade (`authority_expires_at`), três fases, sem ciclo
(desenho §5.2, `[Astra R5]`).

### 2.1 Fases

| Fase | O que a instância pode fazer | Entra por | Sai por |
|---|---|---|---|
| `read_only` (fase 0) | ler corretora (posições, ordens, negócios de toda a vida dos `position_id` abertos), ler registro e kill switch pela API, publicar o **diagnóstico** e avisar. **Nenhuma mutação**, nem SLTP, nem cancelamento | toda instância nasce aqui | concessão de gestão |
| `management` (fase 1) | proteger (repor/apertar `sl`, nunca afrouxar — §5.1), sair pelo colchete (§5), cancelar ordens do robô, reconciliar efeitos | "Conceder gestão" (OWNER, step-up), com a anterior neutralizada (§2.3) | vencimento, revogação, troca de conta/servidor/host, trava local (§2.4) |
| `entries` (fase 2) | além da gestão, entradas (claim de §3.3) | "Armar entradas" (K3, OWNER, step-up), com `management` vigente desta instância, reconciliação limpa e os checks da §8 válidos | desarmar, kill ≥ `TRADING_DISABLED`, K2 desligada observada, API sem resposta há mais de `entries_api_freshness_s` (só suspende a aptidão; ver §2.2) |

### 2.2 Transições

| De | Para | Guarda (dado) | Ator | Efeito persistido |
|---|---|---|---|---|
| — | `read_only` | partida | robô | `b3_robot_instances(instance_id, host_hash, account_hash_seen, started_at)` + auditoria |
| `read_only` | `management` | não existe linha `active` para a conta **ou** ela foi revogada antes; `diagnosis.account_hash = registered_account_hash`; `diagnosis.host_hash = authorized_host_hash`; `diagnosis.instance_id` = o concedido; diagnóstico com menos de 60 s; buffer do host entregue (`buffer_len = 0`) ou declarado `journal_lost` (§6.5); pendências da anterior resolvidas **ou** marcadas `unknown` | Everton (OWNER, step-up) | linha `b3_robot_authority{authority_id, account_hash, host_hash, instance_id, session_date, fencing_token = anterior + 1, authority_expires_at = session_end_utc do pregão vigente, status = active, phase = management}` + auditoria |
| `management` | `entries` | linha `active` desta instância; `last_reconcile.clean`; nenhum `unknown` aberto (intenção ou slot SLTP); os checks estruturais 2, 3, 4, 5, 7, 20, 21, 23 e 24 avaliados agora sem `unavailable` (o check 1 depende do próprio armamento e não entra nesta guarda); tabela de custo vigente; versão de estratégia com nota do Obsidian (§8.1) | Everton (K3, step-up) | `phase = entries`, `armed_at`, `armed_strategy{key, version, params_hash}`, `limits_version`, `spec_pin_id` + auditoria |
| `entries` | `management` | desarmar; kill efetivo ≥ `TRADING_DISABLED`; K2 desligada observada; spec divergente (check 23) | Everton / robô | `phase = management` + auditoria. **Bloqueio local imediato**, antes de qualquer escrita na API; a escrita vem depois e não condiciona o bloqueio `[Astra R4]` |
| `management`/`entries` | `revoked` | ato do Everton; a tela só oferece com a instância neutralizada | Everton | `status = revoked`, `revoked_at` |
| `management`/`entries` | `expired` | `utc_now ≥ authority_expires_at` **ou** `mono_now ≥ authority_mono_deadline` (§2.4) | robô e API, cada um pelo seu relógio | `status = expired`; alerta `critical` se há posição ou residual |

A suspensão da aptidão a entradas por API velha **não** muda a fase no banco: sem API fresca não há claim
(§3.3), e o claim é a única porta de uma entrada. A gestão **não** depende da API: a instância em `management`
continua apertando o colchete com a API fora até `authority_expires_at` (cenário da Astra R5-1).

### 2.3 Neutralização (pré-condição de concessão a uma instância nova)

Uma das duas, mostrada no diagnóstico e confirmada pelo Everton na tela: (a) o processo anterior parou — no
mesmo host o *mutex* do Windows `Global\HunterB3Robot` só é adquirido quando o anterior morreu; noutro host não há
concessão na v1 (D15); (b) "Algo Trading" desligado no terminal anterior (K2), observado. A revogação **não**
resolve uma requisição antiga em trânsito: ela vira `unknown` no diagnóstico da nova (§6.6).

### 2.4 Guarda de mutação (`mutation_guard`) — antes de **toda** mutação, inclusive saída

Avaliada localmente, no mesmo fio de execução, **imediatamente antes** de cada `order_send` (entrada, SLTP,
cancelamento). Falhou qualquer item → nada é enviado, o motivo é gravado.

| # | Condição | Motivo de recusa |
|---|---|---|
| G0 | nenhuma **trava local** ativa nesta instância: `account_changed`, `ipc_hung`, `startup_ineligible` (partida com conta/host/K1 inelegíveis). Travas locais são *latched* até o **reinício do processo**: uma leitura boa depois nunca as limpa `[Astra R0a-6]` | `guard_local_latch:<trava>` |
| G1 | `account_info()` lido **nesta** chamada: `account_hash` = o da autoridade. Divergência → liga a trava `account_changed` (G0) **e invalida** todas as leituras em memória (posições, ordens, histórico, atribuição); nada lido antes da divergência é reutilizado | `guard_account_changed` |
| G2 | `instance_id` = o da autoridade em memória, `status = active` | `guard_no_authority` |
| G3 | `mono_now < authority_mono_deadline` **e** `utc_now < authority_expires_at`. A âncora é o **relógio da API**, não o do PC: a resposta da concessão traz `server_now_utc` e `authority_expires_at`; `authority_mono_deadline = mono_at_grant_request_start + (authority_expires_at − server_now_utc)` — contado do **início** do pedido, então a latência conta contra nós. A âncora é fixada uma vez; releituras e repetições **não** a renovam. A conferência UTC local é só um segundo freio (pode encurtar, nunca alongar) `[Astra R0a-8]`. O relógio monotônico tem de incluir o tempo de suspensão do PC (R5 documenta a fonte e prova com teste) | `guard_authority_expired` |
| G4 | conta REAL ⇒ K1 presente na partida | `guard_k1_absent` |
| G5 | nenhuma chamada MT5 de mutação desta instância está pendurada (§11, F4; liga a trava `ipc_hung`) | `guard_ipc_hung` |
| G6 | só para entrada: fase `entries` e o claim de §3.3 ganho | `guard_not_armed` |
| G7 | só para mutação de posição: a posição está `attributed` **nesta** leitura (§4.5); `unreadable` não herda a atribuição de uma leitura anterior `[Astra R0a-7]` | `guard_not_attributed` |

**A guarda não é check de risco.** O motor nunca bloqueia saída (§8.6). A guarda decide **quem** pode enviar; uma
instância sem autoridade não envia nada, nem saída, e as saídas da posição dependem então do `sl` no servidor e
das rotas R3/R4 do Everton (desenho §4). Diferença declarada em relação à frase "saídas sempre permitidas"
da casa: §13, item 3.

## 3. Máquina B — intenção de entrada

### 3.1 Estados e transições

```
proposed ──evaluate──▶ rejected (terminal)
    │
    └──▶ approved ──(30 s sem claim | instância trocada)──▶ expired (terminal)
             │
             └──claim ganho──▶ submitting ──última conferência falhou──▶ aborted_before_send (terminal)
                                   │
                                   └──order_send──▶ working | partially_filled | filled | broker_rejected | unknown
working ──fill parcial──▶ partially_filled ──fill──▶ filled (terminal)
working | partially_filled ──cancelamento pedido──▶ cancel_requested ──confirmado──▶ canceled (terminal, com filled_volume ≥ 0)
cancel_requested ──sem resultado──▶ unknown
unknown ──prova (§3.6)──▶ working | partially_filled | filled | canceled | broker_rejected
unknown ──ato do Everton (§3.6)──▶ resolved_manual
```

| Estado | Bloqueia novas entradas? | Reenvio permitido? |
|---|---|---|
| `proposed`, `approved`, `submitting`, `working`, `partially_filled`, `cancel_requested`, `unknown` | sim (check 11) | **nunca** |
| `rejected`, `expired`, `aborted_before_send`, `broker_rejected`, `filled`, `canceled`, `resolved_manual` | não (pelo check 11) | — |

**Uma proposta por janela [R0a].** A proposta é única por `(strategy_key, strategy_version, session_date,
window_id)`; `rejected`, `expired`, `aborted_before_send` e `broker_rejected` **consomem** a janela — não há
segunda tentativa no mesmo pregão na v1. Motivo: a prova de "reprocessar não cria segunda ordem" fica trivial
(uma linha, uma intenção), e para a H-038 uma janela perdida é um degrau do funil, contado, não perda de
dinheiro. Rever se o funil mostrar perdas por recusa transitória.

### 3.2 Persistência antes do envio (ordem fixa)

1. proposta (`proposed`) gravada pela API; 2. decisão do motor (`checks[]`, sizing, `approved_at`,
`expires_at = broker.as_of + 30 s`, versões) gravada pela API → `approved` ou `rejected`; 3. claim (§3.3) →
`submitting`; 4. `pre_send_gate` (§3.4); 5. `order_send`; 6. resultado gravado (API; se fora, buffer §6.7).
**Sem API, não há passo 1, 2 ou 3, logo não há entrada.**

### 3.3 Claim atômico (API)

`POST /api/v1/orgs/{org}/b3/robot/intents/{proposal_id}/claim {instance_id, fencing_token}` executa, numa
transação, travas na ordem **sistema → organização → robô** (como `docs/RISK_ENGINE.md` §5):

```
UPDATE b3_entry_intents SET status = 'submitting', claimed_at = now(), claim_instance_id = :instance_id
 WHERE proposal_id = :proposal_id AND status = 'approved' AND expires_at > now()
   AND instance_id = :instance_id
   AND EXISTS (authority WHERE instance_id = :instance_id AND fencing_token = :token
               AND status = 'active' AND phase = 'entries' AND authority_expires_at > now())
   AND kill_effective_in_same_tx IN ('ACTIVE','WARNING')
   AND limits_version = decision.limits_version AND grid_version = decision.grid_version
```

Resposta: `{claimed: true, claimed_at, server_now_utc, send_deadline_utc = min(claimed_at + send_budget_s,
expires_at, authority_expires_at)}` ou `{claimed: false, reason}` com `reason ∈ {not_approved, approval_expired,
authority_mismatch, not_armed, kill_switch, limits_changed, grid_changed}`.

**Idempotência do claim `[Astra R0a, nice-to-have aceito]`.** Repetir o claim para o mesmo `(proposal_id,
instance_id, fencing_token)` devolve **o mesmo resultado** (mesmo `claimed_at`, mesmo `send_deadline_utc`) — é
recuperação de uma resposta perdida, **não** uma nova permissão de enviar. No processo, uma intenção tem **um só
executor** (um único laço de envio por `proposal_id`, e a marca local `send_consumed` ligada antes do
`order_send`); uma segunda resposta `claimed: true` para a mesma intenção nunca dispara um segundo envio.

O robô converte o prazo em relógio monotônico ancorado no **início do primeiro pedido de claim** (repetições não
movem a âncora) e no relógio da API: `send_mono_deadline = mono_at_first_claim_request + (send_deadline_utc −
server_now_utc)`.

### 3.4 `pre_send_gate` — a última conferência, só para entradas

Imediatamente antes do `order_send` da entrada, depois de `order_check` e de toda leitura do terminal, o robô
relê **do agora** e compara com a decisão. Qualquer falha → `aborted_before_send` com o motivo, nada enviado,
janela consumida.

| Releitura | Recusa (`<motivo>_before_send`) |
|---|---|
| `mutation_guard` G1–G6 | `guard_before_send` (com o G que falhou) |
| `terminal_info()`: `connected`, `trade_allowed` (K2), `not tradeapi_disabled` | `terminal_before_send` |
| `positions_get()` e `orders_get()` vazios na conta | `positions_before_send`, `orders_before_send` |
| `symbol_info()` relido **agora** = `spec_pin` | `spec_changed_before_send` |
| tick: idade ≤ `max_quote_age_s`, spread ≤ teto, toque a ≤ `max_slippage_ticks` da referência | `quote_before_send`, `reference_drifted_before_send` |
| janela de entrada (check 6 e 22) ainda aberta | `window_closed_before_send` |
| perda do pregão e margem relidas: `evaluate` de novo com os números de agora (a **própria** intenção excluída das contagens dos checks 11 e 13, §8.2 — sem isso a entrada se reprovaria a si mesma `[Astra R0a-1]`); todos os checks aprovam e o `n_final` de agora é **igual ou maior** que o aprovado (envia-se o aprovado, nunca mais) | `reevaluation_changed_before_send` |
| `limits_version`, `grid_version` = as da decisão (o claim já conferiu no banco; aqui confere a cópia local) | `limits_changed_before_send` |
| `utc_now < send_deadline_utc` **e** `mono_now < send_mono_deadline` | `budget_exhausted_before_send` |
| sem salto entre relógios (`|Δutc − Δmono| ≤ 1 s` desde o claim) e sem intervalo sem batimento local > `send_budget_s` | `clock_jump_before_send` (e força reconciliação) |

**A corrida que sobra é declarada (residual R-1):** depois desta conferência o `order_send` é a fronteira; um
processo suspenso entre a conferência e a chamada envia tarde. A ordem foi autorizada quando partiu, carrega o
`sl` aprovado na própria requisição (nasce protegida) e o resultado tardio é tratado como qualquer resultado.

### 3.5 A requisição de entrada

`symbol` = contrato vigente; `volume` = `n_final` da decisão; preço-limite = `limit_price` da decisão (pior preço
admissível, §8.3); `sl` = `stop_price` da decisão; `tp` = `target_price` ou 0; `magic`; `comment =
client_order_id`; `type_time`/`expiration` e `type_filling` da combinação provada em T14 e fixada no armamento.
O **tipo concreto** (pendente limitada marcável vs. `TRADE_ACTION_DEAL` com preço e `deviation`; IOC/FOK/RETURN)
é escolha de R2, provada em T14; sem combinação provada → check 24 `order_lifecycle_unproven` e nenhuma
entrada. Uma combinação IOC elimina o residual pendente (e com ele o caminho `working`/`cancel_requested`); as
transições ficam escritas para a combinação que deixar ordem no livro.

`entry_cancel_after_s` depois do envio, uma ordem ainda `working`/`partially_filled` recebe pedido de
cancelamento. Cancelamento pedido não é cancelamento: só `canceled` com a ordem no histórico em estado final
(cancelada ou expirada pelo servidor) e `volume_current` final lido. O que preencheu passa à máquina C.

### 3.6 Classificação do retorno e resolução de `unknown`

**Lista fechada, por ação × retcode [R0a, Astra R0a-3]:** o que não está numa linha terminal **da própria
ação** é incerto. Aceitação não é conclusão. Mapeamento candidato, a provar em T9/T13/T14 (R2 escreve a tabela no
código e o teste que falha se aparecer um par ação × retcode fora dela sem classe):

| Ação | Terminal com efeito | Efeito |
|---|---|---|
| entrada (`TRADE_ACTION_DEAL` ou `TRADE_ACTION_PENDING`) | `TRADE_RETCODE_DONE` → `filled`; `TRADE_RETCODE_DONE_PARTIAL` → `partially_filled`; `TRADE_RETCODE_PLACED` → `working` | ler a corretora para confirmar volume e ticket |
| cancelamento (`TRADE_ACTION_REMOVE`) | `TRADE_RETCODE_DONE` → `canceled` **só** depois de lida a ordem em estado final no histórico; até lá `cancel_requested` | |
| `TRADE_ACTION_SLTP` | `TRADE_RETCODE_DONE`, `TRADE_RETCODE_NO_CHANGES` → slot `idle`, nível relido. `PLACED` e `DONE_PARTIAL` **não** concluem uma SLTP → incerto | |

| Classe (todas as ações) | Retornos | Efeito |
|---|---|---|
| terminal sem efeito | `REQUOTE`, `REJECT`, `CANCEL`, `INVALID`, `INVALID_VOLUME`, `INVALID_PRICE`, `INVALID_STOPS`, `TRADE_DISABLED`, `MARKET_CLOSED`, `NO_MONEY`, `PRICE_CHANGED`, `PRICE_OFF`, `INVALID_EXPIRATION`, `INVALID_FILL`, `INVALID_ORDER`, `CLIENT_DISABLES_AT`, `SERVER_DISABLES_AT`, `LIMIT_ORDERS`, `LIMIT_VOLUME`, `LIMIT_POSITIONS`, `LONG_ONLY`, `SHORT_ONLY`, `CLOSE_ONLY`, `POSITION_CLOSED`, `FROZEN`, `TOO_MANY_REQUESTS`, `ONLY_REAL`, `HEDGE_PROHIBITED`, `FIFO_CLOSE`, `INVALID_CLOSE_VOLUME`, `CLOSE_ORDER_EXIST`, `REJECT_CANCEL` (todos com prefixo `TRADE_RETCODE_`) | `broker_rejected` (entrada) ou "rejeitado" (SLTP); conta para o disjuntor só na entrada (§7.3) |
| incerto | `TRADE_RETCODE_TIMEOUT`, `TRADE_RETCODE_CONNECTION`, `TRADE_RETCODE_ERROR`, `TRADE_RETCODE_ORDER_CHANGED`, `TRADE_RETCODE_LOCKED`, qualquer retcode fora da tabela, `order_send` devolvendo `None` (com `last_error()` gravado), exceção, chamada que passa de `ipc_call_timeout_s` | `unknown` (entrada) ou `sltp_slot = unknown` (SLTP) |

**Resolução de uma entrada `unknown`** (nunca reenviar; expirar a aprovação não encerra uma ordem enviada):
procurar em `orders_get()`, `history_orders_get()` e `history_deals_get()` do pregão inteiro, por ticket (se
conhecido), por `comment = client_order_id` e por `magic`.

Um **candidato** é uma cadeia: a ordem e todos os seus negócios contam como um só (vários fills da mesma ordem
não são "dois candidatos").

| Achado | Resultado |
|---|---|
| ticket da ordem já correlacionado e persistido antes da queda (caso `cancel_no_result`, ou resultado gravado no buffer) | o estado que a corretora mostra para esse ticket — prova sem depender do `comment` |
| exatamente um candidato com `comment = client_order_id` e `comment_preserved` provado (T8, fixado no armamento) | o estado que a corretora mostra (`working`/`partially_filled`/`filled`/`canceled`/`broker_rejected`) |
| um candidato só por `magic + símbolo + volume + janela` (sem `comment`) | **indício, não prova**: continua `unknown`, alerta; a posição, se houver, é tratada pela atribuição (§4.5), que é outra pergunta |
| nenhum ou dois candidatos | continua `unknown`, alerta `critical` `entry_unknown` |
| — | `resolved_manual`: **decisão operacional** do Everton (OWNER, step-up), auditada, com o que ele conferiu na aba Histórico do MT5. Não é prova de que nada executou e não é descrita assim; libera o check 11, e a atribuição (§4.5) continua cuidando de qualquer posição que apareça |

**Ausência no histórico não resolve sozinha**, nem com a `expiration` da requisição vencida. Um `unknown` sem
candidato fica `unknown` e bloqueia entradas até o ato do Everton (desenho §5.2: "ausência temporária no histórico
não prova que não executou").

## 4. Máquina C — posição: proteção, saída e atribuição

Uma máquina por `position_id` (em *netting*, uma posição por símbolo; o `position_ticket` atual é só o endereço
de envio). Ela serializa saída, zeragem, emergência, reparo de stop e reconciliação: **uma requisição SLTP por
vez** (`sltp_slot`), e nenhuma mutação de posição fora desta máquina.

**Três fatos, três provas, nunca uma pela outra `[Astra R0a]`:** (a) **a requisição terminou** — só pelas provas
da §4.3; (b) **a proteção foi observada** — `sl` lido no servidor; (c) **a posição foi encerrada** — volume 0
explicado pelos negócios do `position_id`. Ler um nível não prova que uma requisição terminou; uma requisição
terminada não prova que a posição está protegida.

### 4.1 Estados

| Estado | Significa | Mutações permitidas (com a guarda §2.4) |
|---|---|---|
| `unattributed` | posição na conta que a §4.5 não atribui ao robô (`foreign`, `ambiguous`, `unreadable`) | **nenhuma**; entradas bloqueadas (check 10), alerta, rota manual |
| `unprotected` | atribuída, volume > 0, sem `sl` confirmado, dentro de `naked_grace_s` contados de `time_msc` do 1.º negócio da posição | SLTP de reparo (§4.2) |
| `protected` | atribuída, `sl` lido no servidor, do lado certo, alinhado ao tick, não mais largo que o piso (§4.4) | SLTP só apertando (reparo de divergência) |
| `degraded` | atribuída e sem proteção confirmada; `degraded_reason ∈ {naked_after_grace, repair_rejected, floor_unplaceable, protection_unknown}` | `naked_after_grace`/`repair_rejected`: SLTP de reparo tentado a cada `reconcile_interval_s`; `floor_unplaceable`/`protection_unknown`: **nenhuma**. Sempre alerta `critical` e rota manual |
| `exiting` | saída pelo colchete em curso (§5) | só SLTP de aperto |
| `exit_overdue` | `exiting` depois de `bracket_deadline_s` | só SLTP de aperto; alerta `critical` `exit_overdue`; rota manual |
| `closed` | volume 0, explicado pelos negócios do `position_id` | nenhuma (terminal) |

### 4.2 Transições

| De | Evento | Para | Notas |
|---|---|---|---|
| — | primeiro fill de uma entrada nossa observado | `protected` se `sl` lido ≠ 0 e válido, senão `unprotected` | a entrada carrega o `sl` na requisição; meta de leitura 1 s (desenho §3) |
| — | posição encontrada na partida/reconciliação | `unattributed` ou, se `attributed`, `protected`/`unprotected`/`degraded` pela idade desde `time_msc` | numa partida que encontra posição sem `sl` desde antes, a carência já acabou → `degraded` |
| `unprotected` | `sl` confirmado | `protected` | |
| `unprotected` | `naked_grace_s` vencido | `degraded` (`naked_after_grace`) | `naked_position` `critical` |
| `unprotected`/`degraded` | o piso (§4.4) não pode ser colocado: para comprado `floor ≥ bid − d`, para vendido `floor ≤ ask + d` (o nível estaria do lado errado do toque) | `degraded` (`floor_unplaceable`) | **nenhum reparo automático**, nenhum colchete abaixo do piso; alerta `critical` e rota manual `[Astra R0a-5]`. Colocar um piso mais largo que o original é exceção de risco que só o Everton decide (D17, §9) |
| `protected`/`unprotected`/`degraded` (exceto `floor_unplaceable`) | `exit_due` (§5.2) e `sltp_slot = idle` | `exiting` | `exit_started_at`/`exit_deadline_at` gravados antes da 1.ª SLTP da saída (§5.2) |
| `exiting` | `utc_now ≥ exit_deadline_at` com volume > 0 | `exit_overdue` | o aperto continua; o prazo é limite para **escalar**, não prova de fill. O prazo **nunca** é renovado por reinício `[Astra R0a-9]` |
| `exiting`/`exit_overdue` | o gatilho desaparece (preço volta, `EMERGENCY` rearmado) | **mesmo estado** | uma saída iniciada só termina em `closed` comprovado |
| qualquer (≠ `closed`) | volume 0 lido **e** Σ dos negócios do `position_id` = 0 | `closed` com `close_cause` | `naked_position_flattened` só aqui, quando aplicável |
| qualquer | volume 0 lido sem negócio que explique | `closed` com `close_cause = unexplained` + kill `TRADING_DISABLED` | desenho §5.3 |
| qualquer | volume diferente do registrado | mesmo estado, volume da corretora | entradas bloqueadas até 2 passes consistentes (check 20) |
| qualquer | lado oposto ao registrado depois de uma saída | `exiting` com `exit_reason = reversal` + kill `TRADING_DISABLED` (`reversal_detected`, *latched*) | só se a cadeia continuar `attributed`; senão `unattributed` |
| qualquer | atribuição deixa de ser `attributed` (negócio manual entrou na cadeia) | `unattributed` | não adota nem zera; rota manual |

**Exclusões:** o reparador nunca toca posição em `exiting`/`exit_overdue`; uma saída não começa com
`sltp_slot ≠ idle`; nenhuma ordem direcional de saída existe em estado algum (§5.5).

### 4.3 O slot SLTP — uma requisição por vez, e o que prova o seu fim `[Astra R5, R6]`

**Nenhuma SLTP sem gravação durável confirmada `[Astra R0a-2 — CRITICAL, rodadas 1 e 2]`.** Toda requisição
SLTP (reparo ou colchete) é gravada **antes** do `order_send` como `b3_sltp_requests{sltp_request_id,
epoch_id, position_id, request_position_ticket, sl, tp, purpose, built_at, status = intended}`, e só é enviada
depois de **uma** confirmação de durabilidade: (1) a API respondeu com sucesso dentro de `sltp_record_api_ms`; ou,
senão, (2) a linha do buffer (§6.7) foi escrita **e o `fsync` retornou com sucesso** dentro do restante de
`sltp_record_budget_ms`. "Tentativa iniciada" não é durabilidade: `fsync` pendente no fim do orçamento conta como
falha. **Sem confirmação, a SLTP não é enviada** neste passo (o colchete pausa, o reparo pausa), alerta `critical`
`sltp_durability_lost`, nova tentativa no passo seguinte; se a linha ficar durável depois sem o envio ter
acontecido, o robô acrescenta `not_sent` quando puder (uma `intended` sem `not_sent` nem resultado é herdada
`unknown` — falso positivo conservador, nunca o contrário). Consequência: **toda SLTP que partiu está na API ou no
buffer**, por construção; a completude do registro é provável, não suposta. O preço é declarado (§13, item 8): com
API e disco falhando **juntos**, o robô para de mexer em níveis — o `sl` confirmado continua no servidor, nada é
retirado, e a rota é a manual.

`sltp_slot`: `idle → in_flight` ao enviar; `in_flight → idle` com prova; `in_flight → unknown` com resultado
incerto.

| Prova de término da **requisição** (lista fechada) | Resultado |
|---|---|
| P1 — `order_send` voltou, **para esta requisição** (retorno síncrono), com um retorno terminal **da ação SLTP** (§3.6: `DONE`, `NO_CHANGES` ou terminal sem efeito) | `idle`; nível relido e gravado como confirmado (ou mantido, se rejeitado) |
| P3 — a posição está `closed` (volume 0 explicado pelos negócios do `position_id`) **e** `stale_ticket_rejection_proven` (T13: uma SLTP atrasada com o `request_position_ticket` de uma posição fechada é rejeitada mesmo com uma posição nova no mesmo símbolo), fixado no armamento | `idle` (moot) |
| P3′ — a posição está `closed`, sem `stale_ticket_rejection_proven` | a máquina da posição fecha, mas a requisição vira **SLTP órfã incerta do símbolo**: bloqueia entradas nesse símbolo (check 11, `orphan_sltp_unknown`) até P4 ou até a prova de T13 `[Astra R0a-4]` |
| P4 — ato do Everton (OWNER, step-up) que registra **evidência terminal correlacionada**: a linha do Diário do terminal com o resultado **daquela** requisição (instante, ticket, níveis, resultado), copiada para o registro; "conferi o Diário" sem a linha não é prova `[Astra R0a-3]` | `idle` |

**Recusadas como prova `[Astra R0a-3]`:** nível lido igual ao pedido (o Everton pode ter colocado os mesmos níveis
à mão — uma mudança manual de SLTP não cria negócio que a §4.5 veja; depois disso B aperta e A, ainda em trânsito,
desfaz o aperto); reler o nível antigo (exemplo da Astra: `sl` 90 confirmado, A para 95 incerto, leitura 90 —
mandar B para 99 deixaria A chegar depois e trocar 99 por 95); `PLACED`/`DONE_PARTIAL` numa SLTP; declaração de
inspeção sem a linha do Diário. **"Reparo idêntico" recusado na v1:** A pede 95 e fica incerto, B repete 95 e volta
`DONE`, P1 libera o slot, C pede 99, A chega e devolve 95 — A e B comutam entre si, mas não com a próxima
modificação.

Com `sltp_slot = unknown`: nenhuma modificação nova, `degraded` (`protection_unknown`) se a posição estava sendo
protegida, ou `exit_unknown` se em saída; alerta e rota manual. O slot é **da posição**, gravado no registro, e
**atravessa instâncias**: conceder gestão não o limpa `[Astra R6]`.

**Época de gestão.** Cada concessão abre uma época (`b3_management_epochs{epoch_id, instance_id, host_hash,
opened_at, closed_at, closed_clean}`, gravada pela API) e, antes da primeira mutação, a instância escreve no buffer
do host a linha de abertura `{kind: epoch_open, epoch_id, instance_id}` com `fsync` confirmado — sem ela, a
gestão não começa. A época fecha limpa só por encerramento ordenado (todos os slots `idle`, buffer entregue,
`epoch_close` confirmado pela API).

**Herança na partida** — o slot de uma posição gerida pela instância anterior nasce `unknown` (nunca `idle`) se
qualquer um: o registro tem SLTP `intended`/`in_flight` sem resultado nem `not_sent`; o último batimento que chegou
à API mostrava `sltp_slot ≠ idle` (`heartbeat_in_flight`); o buffer, entregue na fase 0 (§6.5), tem SLTP sem
resultado; a época anterior não fechou limpa **e** o buffer do host está ilegível, com a cadeia de hash quebrada, ou
sem a linha `epoch_open` dessa época (`journal_lost`). Toda SLTP herdada `unknown` de posição já `closed` vira SLTP
órfã do símbolo (P3′). Com a regra acima (nenhuma SLTP sem gravação durável), um buffer íntegro com a linha da época
mais o registro da API **é** o conjunto completo das SLTP daquela época **sob a hipótese de que um `fsync`
confirmado é durável**. A linha `epoch_open` e a cadeia de hash detectam arquivo sumido, época sem abertura e
corrupção no meio; **não** detectam a perda de um sufixo inteiro de linhas depois de `fsync` confirmado — essa falha
fica **fora do modelo suportado** (residual R-8, §6.6) `[Astra R0a-2, r3]`. API e buffer usam o **mesmo**
`event_id` e o mesmo `sltp_request_id` para a mesma gravação; reenviar uma `intended` nunca rebaixa um resultado
terminal já gravado. Ausência de resultado depois de uma queda é `unknown`, nunca `idle`.

### 4.4 Piso de proteção (o que torna qualquer reordenação inofensiva para o "sem stop")

`floor(p)` = o nível mais apertado já **confirmado** no servidor para a posição `p`; antes de qualquer confirmação,
o `sl` que a ordem de abertura pediu (`ORDER_SL` em `history_orders_get`) — chamado "stop pedido pela ordem",
**não** "aprovação do motor" `[Astra R3-4]`. "Mais apertado" é **pelo lado**: comprado = maior `sl`; vendido =
menor `sl`. Toda requisição SLTP que o robô envia: `sl ≠ 0`; do lado certo do toque; alinhada ao tick; e **pelo
menos tão apertada quanto `floor(p)` no instante em que foi montada** — comprado `sl ≥ floor`, vendido
`sl ≤ floor`.

**O que isso prova, e o que não prova.** Para requisições **aceitas** sobre a **mesma** posição e o **mesmo**
lado, todas montadas respeitando um piso conhecido, qualquer ordem de chegada deixa no servidor um `sl` pelo
menos tão apertado quanto o stop pedido pela ordem (I-SL-2): nenhuma requisição **nossa** deixa a posição sem
stop nem mais larga que ele. **Não** prova proteção contínua quando o servidor remove o stop (virada do pregão),
quando a entrada nasce sem `sl` (a Rico o descartou), ou quando o piso fica inexequível (preço além dele) —
esses casos são `unprotected`/`degraded` com nome próprio, não cobertos pelo piso. E não substitui o slot: o slot
evita **perder aperto**; o piso garante que perder aperto nunca vira ficar mais largo que o stop pedido.

**Virada do pregão.** O servidor **zera** `sl`/`tp` de posição de bolsa na transição do dia (ajuda oficial). Uma
posição atribuída encontrada num pregão novo mantém `floor` = o mais apertado entre `ORDER_SL` e o último
confirmado no registro. Se o piso pode ser colocado → reparo, depois `exiting` com `exit_reason =
overnight_carry` (a v1 é só day trade; padrão do desenho, confirmar com o Everton). Se não pode (o preço abriu
além do stop) → `degraded` (`floor_unplaceable`), sem mutação automática, alerta `critical`, rota manual
`[Astra R0a-5]` — e a posição está **sem stop** até o Everton agir (consequência declarada; D17 pergunta se ele
quer que o robô ponha, nesse caso, um colchete abaixo do piso).

### 4.5 Atribuição — de quem é esta posição

Calculada da **corretora**, por isso existe com a API fora `[Astra R2]`. Insumo: todos os negócios do
`position_id` (`history_deals_get(position=position_id)`, toda a vida) e a ordem de abertura. **Recalculada a cada
leitura, sem cache** `[Astra R0a-7]`: depois de uma desconexão do terminal, de uma troca de conta ou de um histórico
incompleto, a posição é `unreadable` até uma leitura completa provar a cadeia de novo — volume igual ao de antes
não prova continuidade (o Everton pode ter reduzido e recomposto a mão durante a lacuna). `unreadable` bloqueia
toda mutação daquela posição (guarda G7); o stop que já está no servidor fica.

| Classe | Condição (dado) |
|---|---|
| `attributed` | todo negócio do `position_id` tem `magic ∈ robot_magics` **e** `reason ∈ {DEAL_REASON_EXPERT, DEAL_REASON_SL, DEAL_REASON_TP}`, **e** Σ volumes assinados = volume atual; com a API, a cadeia ainda bate com as intenções gravadas (ticket da ordem ∈ ordens registradas, ou `comment = client_order_id` de uma intenção) |
| `foreign` | nenhum negócio com `magic ∈ robot_magics` (posição manual do Everton ou de outro robô) |
| `ambiguous` | qualquer negócio `DEAL_REASON_CLIENT`/`MOBILE`/`WEB` na cadeia (inclusive um que deixe a mesma quantidade final), `magic`/`reason` não preservados (T8), soma que não fecha, ou divergência com as intenções gravadas |
| `unreadable` | leitura do histórico falhou ou veio incompleta |

Somente `attributed` é gerido. `foreign` → `foreign_position_present` (check 10), **não toca** (D11);
`ambiguous`/`unreadable` → não adota nem zera, bloqueia entradas, alerta, rota manual.

**Atribuição não é resolução de intenção.** Uma posição pode ser `attributed` (podemos protegê-la e sair dela)
enquanto a intenção de entrada que a abriu continua `unknown` (não podemos entrar de novo). As duas perguntas têm
respostas separadas, de propósito.

## 5. A saída pelo colchete (desenho §2.2) — sem ordem direcional, sem retirar stop

### 5.1 Níveis

Insumos: lado da posição, `bid`, `ask`, `trade_tick_size`, `point`, `trade_stops_level` e `trade_freeze_level`
(distâncias em **points** — convertidas por `point` e alinhadas ao `trade_tick_size` `[Astra R4]`), níveis
confirmados `sl_c`, `tp_c` (0 = ausente), e `k` = deslocamento aprendido no pregão (§5.3).

```
d   = max(k × tick, ceil_to_tick(trade_stops_level × point))
comprado:  sl* = floor_to_tick(bid − d)     tp* = ceil_to_tick(ask + d)
           sl_novo = max(sl_c, sl*)         tp_novo = tp* se tp_c = 0, senão min(tp_c, tp*)
vendido:   sl* = ceil_to_tick(ask + d)      tp* = floor_to_tick(bid − d)
           sl_novo = sl* se sl_c = 0, senão min(sl_c, sl*)   tp_novo = tp* se tp_c = 0, senão max(tp_c, tp*)
envia só se (sl_novo, tp_novo) ≠ (sl_c, tp_c); nunca sl_novo = 0; nunca mais largo que sl_c
nunca mais largo que o piso (§4.4): comprado sl_novo ≥ floor, vendido sl_novo ≤ floor; se o colchete não
respeita o piso, nada é enviado e a posição vai a degraded (floor_unplaceable)
```

Com `d = 0` o colchete encosta: comprado `sl` no bid e `tp` no ask — o primeiro negócio em qualquer lado do livro
dispara um dos dois (o stop de bolsa dispara pelo último negócio). Com `d > 0` a saída **passa a depender de o
preço andar até o nível** (exemplo sintético da Astra: tick 5, bid 100, ask 105, `sl` 95, `tp` 110 — negócios em
100/105 não disparam nada); a decisão grava `bracket_gap_ticks = d / tick` e a tela diz isso.

Toda requisição: `action = TRADE_ACTION_SLTP`, `symbol`, `position = position_ticket` (o atual, gravado como
`request_position_ticket`), `sl`, `tp`, `magic`. Nada além disso é enviado na saída.

### 5.2 Quando uma saída é devida (`exit_due`, função pura do agora)

`exit_due(now, position, plan, session, kill)` é verdadeiro se qualquer um: `now ≥ plan.exit_at_utc`
(`time_exit`); `now ≥ session.flatten_at_utc` (`session_flatten`); kill efetivo = `EMERGENCY` (`emergency`);
inversão detectada (`reversal`); posição de pregão anterior com piso colocável (`overnight_carry`).

**Instante devido e prazo, sem renovação `[Astra R0a-9]`.** Cada gatilho tem um `exit_due_at` que não depende de
quando o processo percebeu: `time_exit` → `plan.exit_at_utc`; `session_flatten` → `session.flatten_at_utc`;
`emergency` → `changed_at` da transição durável para `EMERGENCY`; `reversal` → `time_msc` do negócio que inverteu;
`overnight_carry` → início do pregão (`open_utc`). Com mais de um gatilho, vale o **menor** `exit_due_at`; um
gatilho novo nunca estende o prazo. `exit_deadline_at = exit_due_at + bracket_deadline_s`. A intenção
`b3_exit_intents{position_id, exit_reason, exit_due_at, started_at, deadline_at}` é gravada com durabilidade
confirmada, como a SLTP (§4.3), antes da 1.ª SLTP da saída.

**A obrigação de sair é recuperável pelo histórico, não pela memória `[Astra R0a-9, rodadas 1 e 2]`.** Na partida,
com gestão, para cada posição atribuída, existe obrigação de saída se **qualquer** gatilho disparou **durante a
vida da posição** (desde o `time_msc` do primeiro negócio do `position_id`): `now ≥ exit_at_utc`; `now ≥
flatten_at_utc`; **alguma transição durável para `EMERGENCY`** (sistema, organização ou robô) com `changed_at`
dentro da vida da posição — **mesmo que já rearmada** depois; negócio de inversão no `position_id`; pregão diferente
do da abertura. O `exit_due_at` é o do gatilho (o menor, se vários), recuperado da intenção gravada se houver, senão
do próprio gatilho; `deadline_at` nunca é recalculado a partir de agora. Se as transições do kill switch ou o
histórico da posição não puderem ser lidos por completo, a obrigação é **presumida** pendente e a posição entra em
`exit_overdue` (sem envio enquanto o slot não estiver `idle`). Rearmar o kill switch **não** cancela uma obrigação de
saída já disparada; ela termina em `closed`.

### 5.3 Laço

1. `exiting`, `exit_started_at` = o instante da 1.ª SLTP (ou o recuperado), `exit_deadline_at` como acima.
2. A cada `bracket_step_s`, se `sltp_slot = idle` e a posição continua aberta: calcula §5.1; envia se apertou.
3. SLTP rejeitado com `TRADE_RETCODE_INVALID_STOPS` → mantém e relê os níveis; `k ← k + 1` para o pregão
   (gravado em `b3_bracket_learning{session_date, symbol, k}`), até `bracket_max_k`; outros rejeitados → mantém,
   relê, tenta no próximo passo. **Nunca** contorna rejeição removendo o `sl`.
4. SLTP incerto → `sltp_slot = unknown` (§4.3): para de modificar, alerta `exit_unknown`, rota manual. Se a
   posição fechar, P3 (ou P3′, que deixa a SLTP órfã bloqueando entradas no símbolo).
5. Prazo vencido → `exit_overdue`, alerta `critical` no app e no celular (Sentry, D13), entradas bloqueadas; o
   laço **continua** apertando enquanto o slot estiver `idle`.
6. Ordem do stop disparada e rejeitada pela bolsa dispara de novo no próximo tick elegível: `sl` presente não é
   saída executada. Fill **parcial** da ordem do stop: o fechamento parcial não muda `sl`/`tp` (*netting*); relê o
   volume, confirma que o `sl` continua lá e segue.
7. Volume 0 lido e explicado pelos negócios → `closed` com `close_cause ∈ {bracket_sl, bracket_tp}` (ou `manual` se
   o Everton fechou, `broker_compulsory` se a zeragem da Rico fechou).

### 5.4 Fim de pregão

`flatten_at_local` é o instante em que a zeragem do robô **começa**; precisa satisfazer
`flatten_at_local ≤ rico_flatten_local − flatten_lead_min` (validado na edição do perfil), para o Everton ter
tempo de agir antes da zeragem compulsória da Rico, que é a última rede (regra não lida, D6).

### 5.5 O que nunca existe na v1 `[Astra R4-1 — CRITICAL]`

Ordem direcional de saída (`TRADE_ACTION_DEAL` reduzindo ou fechando), retirada de `sl` (`sl = 0`), trailing do
terminal, remoção e recolocação de stop. Um teste de R5 percorre todos os caminhos de saída com o falso do MT5 e
falha se qualquer requisição diferente de `TRADE_ACTION_SLTP` for emitida para uma posição aberta. **Se a sessão
demo mostrar que o colchete não zera de forma confiável dentro do prazo, o desenho volta para revisão antes do
dinheiro real** — ninguém troca por um fechamento a mercado "só desta vez".

### 5.6 H-038

A saída pré-registrada da H-038 é "a mercado em C". O robô começa o colchete em C (`time_exit`) e grava
`exit_intended_at`, `exit_effective_at`, preço efetivo e a diferença em ticks. A série-modelo congelada não
muda; a série (iii), execução real, mede a diferença.

## 6. Queda do processo em cada intervalo, e o que a partida faz

Notação: o processo morre **dentro** do intervalo. "Partida" = a sequência da §6.5. Em todos os casos a
instância nova nasce `read_only` e nada é mutado antes de "Conceder gestão".

### 6.1 Caminho de entrada

| Intervalo | O que existe no mundo | Partida (depois da concessão de gestão) |
|---|---|---|
| (sinal, proposta gravada) | nada | nada; uma proposta nova pode nascer se a janela ainda estiver aberta, depois de K3 desta instância |
| (proposta, decisão gravada) | proposta `proposed` | proposta da instância morta → `expired` (`instance_gone`); janela consumida |
| (decisão `approved`, claim) | aprovação desta instância | `expired` (`instance_gone`); a aprovação é da instância e nunca é herdada |
| (claim enviado, claim gravado) | aprovação ainda `approved` | expira em 30 s |
| (claim gravado, resposta recebida) | `submitting`, nada enviado | **processo vivo:** repete o claim (idempotente); com a resposta dentro do prazo segue, senão `aborted_before_send` (`claim_ack_lost`). **Morto:** `unknown` (`claim_ack_lost`) — a partida não distingue "não enviou" de "enviou" |
| (resposta, última conferência) | `submitting` | `unknown` (`process_died`) |
| (última conferência, `order_send` chamado) | `submitting`; residual R-1 | `unknown`; se executou, a ordem tem `sl` e `comment` |
| (`order_send` em curso) | requisição no terminal/na rede | `unknown` (`process_died`); resolução §3.6 |
| (retorno, resultado gravado) | resultado só na memória | `unknown` (`result_not_persisted`); resolução por ticket/`comment` |
| (`working`, fill) | ordem limitada no livro até a validade no servidor | diagnóstico mostra a ordem residual; com gestão: cancela com confirmação; o que preencher é protegido pelo `sl` da requisição; sem confirmação → `unknown` (`cancel_no_result`) |
| (`cancel_requested`, confirmação) | cancelamento pedido | relê; ordem no histórico em estado final → `canceled`; ainda viva → novo pedido de cancelamento (cancelar é idempotente no servidor); sem leitura → `unknown` |
| (fill, `sl` lido) | posição com o `sl` da requisição (ou sem, se a Rico o descartou) | diagnóstico; `sl` presente → `protected`; ausente → `degraded` (a carência conta do `time_msc` do fill, já vencida) → reparo com gestão |

### 6.2 Caminho de proteção (reparo)

| Intervalo | O que existe | Partida |
|---|---|---|
| (divergência vista, SLTP montado) | posição sem/fora do `sl` | diagnóstico mostra; com gestão, o reparo recomeça do zero |
| (SLTP montado, gravação tentada) | talvez nada gravado, nada enviado | gravação na API → `intended` sem resultado → `unknown` herdado; gravação só no buffer → entregue na fase 0 → `unknown` herdado; nada gravado → nada foi enviado (§4.3). Conservador: a partida não sabe se partiu |
| (gravada, enviada, sem retorno) | requisição em trânsito | `unknown` herdado; só P1/P3/P4 liberam (nível lido igual ao pedido **não** libera) |
| (retorno, gravação do resultado) | nível novo aplicado ou não | resultado na memória perdido → `unknown` herdado; o nível lido entra como proteção observada, não como fim da requisição |
| API e disco falham juntos | nenhuma SLTP enviada (sem gravação durável não há envio, §4.3) | nada a herdar; posição com o último `sl` confirmado; com gestão, o reparo recomeça |
| buffer sem a linha `epoch_open` da época anterior, ou ilegível | não se sabe o que partiu | `journal_lost`: slots herdados `unknown`, órfãs por símbolo para posições já fechadas |

### 6.3 Caminho de saída (colchete)

| Intervalo | O que existe no servidor | Partida |
|---|---|---|
| (saída devida, intenção gravada) | o `sl` original (ou o confirmado) | com gestão: intenção recuperada com `exit_due_at`/`deadline_at` **originais** (§5.2) → colchete retoma; prazo já vencido → `exit_overdue` |
| (saída devida, intenção não gravada) | idem | `exit_due_at` derivado do gatilho; se a saída provavelmente começou sem registro → `exit_overdue` direto |
| (SLTP *k* em trânsito) | níveis *k−1* ou *k* | slot `unknown` herdado; sem nova modificação até P1/P3/P4; o colchete *k−1* (mais apertado que o original) segue fechando a posição sozinho |
| (entre passos, slot `idle`) | colchete apertado | a posição tende a fechar pelo servidor com o robô morto; com gestão, retoma com o prazo original |
| prazo vence com o robô morto | colchete apertado, posição aberta | ninguém escala a não ser o cão de guarda (§10.2) e o EA (§10.1); na partida → `exit_overdue` |
| posição fecha com o robô morto | nada | `closed` pelos negócios (`bracket_sl`/`bracket_tp`/`server_sl`) |

### 6.4 Caminho de autoridade

| Intervalo | Partida |
|---|---|
| concessão gravada, instância morre antes de recebê-la | a linha fica `active` para um `instance_id` morto; a instância nova não a herda; o Everton revoga (neutralização = processo parado, observável pelo *mutex*) e concede à nova |
| K3 gravado, instância morre | instância nova em `read_only`; K3 é da instância — nada a herdar |
| revogação gravada com a instância viva e a API fora | a instância não fica sabendo e continua gerindo até `authority_expires_at` — por isso a tela só oferece revogar com a instância neutralizada (residual R-3) |
| K2 desligada observada, processo morre antes de escrever na API | ao voltar, a instância nova está em `read_only` e precisa de concessão e K3 novos; K2 religada **não** destrava nada (§1.3 do desenho) |
| autoridade vence com posição aberta | nenhuma mutação posterior; alerta `critical` `authority_expired_with_position`; o `sl` confirmado fica no servidor até a virada do pregão, quando o servidor o zera (D10) |

### 6.5 Partida (ordem fixa, desenho §5.4)

1. *mutex* `Global\HunterB3Robot` (um processo por host); `instance_id` novo.
2. `mt5.initialize()` **sem** `login`/`password`.
3. `account_info()`: `account_hash` ≠ registrado, ou conta REAL sem K1, ou modo ≠ DEMO/REAL → fica em `read_only`
   para sempre nesta instância (concessão recusada pela API); publica e avisa.
4. Lê posições, ordens e negócios de toda a vida dos `position_id` abertos; classifica atribuição e proteção;
   posição sem `sl` ou não atribuível → alerta `critical` (app se alcançável, EA no celular), **sem mutação**.
5. API, com prazo e repetição: identidade da conta e do host.
6. **Entrega do buffer, ainda em `read_only` `[Astra R0a-2]`**: as linhas do buffer deste host são reenviadas à
   API em ordem (idempotentes). Entregar não é decidir: a API grava, e a decisão continua vindo do registro. Buffer
   ilegível, com cadeia de hash quebrada, ou sem a linha `epoch_open` de uma época que a API mostra aberta sem
   fechamento limpo → `journal_lost`: toda posição que a instância anterior geria tem o slot herdado `unknown`
   (órfã do símbolo, se já fechada) e toda intenção de entrada dela sem resultado vira `unknown`.
7. Lê da API o registro (intenções abertas, slots SLTP, intenções de saída, último batimento da instância
   anterior) e o kill switch; aplica a herança da §4.3 (slot `unknown`, nunca `idle`, sem prova) e da §3
   (`submitting` sem resultado → `unknown`; aprovação de instância anterior → `expired`); publica o diagnóstico
   (§2.1). Sem resposta → continua em 4, só lendo e avisando (D16b).
8. Espera "Conceder gestão" — que a API só aceita com o buffer do host entregue (`buffer_len = 0`) ou declarado
   `journal_lost`. **Nenhuma mutação acontece antes deste passo.** Com a concessão: relê kill switch, conta e
   atribuição (§4.5) — a leitura do passo 4 não vale mais —; protege o atribuível (§4.4, sem afrouxar; slots
   `unknown` continuam `unknown`), retoma saídas devidas com os prazos originais (§5.2), cancela ordens residuais
   do robô, reconcilia efeitos.
9. Reconcilia com o registro (desenho §5.3).
10. `EMERGENCY` (relido agora, inclusive se gravado durante a recuperação) → cancela e zera pelo colchete; K2
    desligada → grava `TRADING_DISABLED` (`manual_route`).
11. Com a reconciliação limpa, espera K3 desta instância → laço de entradas.

### 6.6 Residuais declarados (limitações, não garantias)

R-1 processo suspenso depois da última conferência envia tarde (§3.4). R-2 com API e disco falhando juntos o robô
para de mexer em níveis (o colchete pausa, o reparo pausa) até uma das duas voltar — a posição fica com o último
`sl` confirmado e a rota é a manual (§4.3; é o preço de nunca existir SLTP enviada sem registro). R-3 revogação não alcança instância viva sem API (§6.4).
R-4 o `fencing_token` não é aplicado pela corretora. R-5 a rota humana R3 disputa com o stop do servidor.
R-6 a saída pode atrasar (colchete sem negócio, leilão, rejeições). R-7 instância nova sem API só observa (D16b).
R-8 **fora do modelo suportado**: perda de linhas do buffer **depois** de `fsync` confirmado (disco que mente sobre
durabilidade, falha de firmware). Nem a linha `epoch_open` nem a cadeia de hash detectam a perda de um sufixo
inteiro; se acontecer com a API fora, uma SLTP enviada pode não ser herdada como `unknown` `[Astra R0a-2, r3]`.
A pausa do colchete perto da zeragem (R-2) tem teste próprio: alerta, retomada sem prazo novo, e a zeragem
compulsória da Rico nunca é tratada como confirmação de fechamento — só os negócios do `position_id` são.

### 6.7 O buffer de indisponibilidade

`%LOCALAPPDATA%\HunterB3\outage-buffer.jsonl`: append-only, `fsync` por linha, cada linha
`{seq, event_id, kind, payload, prev_hash, hash}`; a primeira linha de cada época de gestão é `epoch_open` (§4.3).
Nunca lido para decidir. Recebe só eventos que a API recusou ou
não alcançou dentro do orçamento (inclusive as gravações-antes-de-enviar de SLTP e de intenção de saída, §4.3,
§5.2); reenviado em ordem com `Idempotency-Key = event_id` — na partida, **antes** da concessão de gestão (§6.5
passo 6); em operação, em segundo plano. Enquanto não vazio, check 21 recusa entradas.

**Falha de disco, subordinada à §4.3 `[Astra R0a, r3]`:** (a) gravações **obrigatórias antes do envio** (SLTP e
intenção de saída) sem confirmação durável — nem ack da API nem `fsync` com sucesso — **impedem o envio** naquele
passo (F48); (b) falha só de disco, com a API confirmando, não atrasa nada; (c) falha ao gravar o **resultado** de
uma requisição já enviada, ou um evento de auditoria que não precede envio: o evento fica em memória, alerta
`critical` `audit_buffer_unwritable`, entradas bloqueadas, e numa queda a herança é conservadora (§4.3: slot
`unknown`). Nenhum caminho envia uma SLTP depois de uma gravação obrigatória falhar.

## 7. Kill switch

### 7.1 Escopos e estados

Escopos **sistema**, **organização**, **robô**; efetivo = o mais restritivo na ordem
`ACTIVE < WARNING < TRADING_DISABLED < EMERGENCY`. Releitura do estado durável pela API **a cada 2 s, no máximo
10 s** (regra da casa), com ou sem evento; a releitura que vale para entrada é a do claim (mesma transação, §3.3).

| Estado | Entradas | Ordens pendentes do robô | Posições do robô | Aciona (causa) | Volta |
|---|---|---|---|---|---|
| `ACTIVE` | permitidas | — | normais | — | — |
| `WARNING` | permitidas com `n × 0,5` (arredonda para baixo; 1 vira 0) | — | normais | perda do pregão ≥ `warning_fraction × daily_loss_limit_brl` | automática quando abaixo |
| `TRADING_DISABLED` | bloqueadas | **entradas** canceladas | geridas; stops no servidor; **sem zeragem** | `daily_loss_limit` (check 14), `broker_reject_breaker` (check 19), `reversal_detected`, `manual_route` (K2 desligada observada), `agent_command`, `owner_command`, reconciliação inexplicável | `daily_loss_limit`: **no pregão seguinte, depois de reconciliar** (D8); todas as outras: rearme manual do Everton |
| `EMERGENCY` | bloqueadas | canceladas (intenção durável até confirmar) | **zeradas pelo colchete** (§5, `exit_reason = emergency`); prazo vencido → `exit_overdue`; posição/ordem `foreign` não é tocada (D11) | `owner_button` (R1) ou `owner_command` (R2) | só rearme do Everton (K3), posterior ao comando; o rearme **não** cancela a obrigação de saída de posição aberta durante o `EMERGENCY` (§5.2) — ela termina em `closed` |

`auto_close_on_emergency = true` é **comportamento fixo do robô B3**, não chave de perfil (diferença declarada,
§13). A virada do pregão só limpa a trava da perda diária depois de reconciliar; nunca limpa comando,
rejeições, inversão ou `EMERGENCY`. A concessão de gestão não limpa nada disso: a gestão existe justamente para
proteger e zerar sob essas travas.

### 7.2 Quem pode o quê (aplicado na API, não no script)

| Ato | Everton (OWNER, step-up) | Agente (credencial de agente) |
|---|---|---|
| `TRADING_DISABLED` | sim | sim (`b3_kill.py --level disabled`) |
| `EMERGENCY`, rearme, limites, concessão, K3, revogação, `resolved_manual` | sim | **403** + auditoria `[Astra R1]` |

### 7.3 Disjuntor de rejeições

Conta **só** rejeições terminais (`broker_rejected`) de requisições de **entrada** e dos cancelamentos delas
**[R0a]**. Rejeições de SLTP de proteção/saída têm métrica e alerta próprios (`protection_rejected`) e não
disparam o disjuntor — o colchete aprende `k` por `INVALID_STOPS` (§5.3) e isso não pode travar o dia por
rearme manual. O disjuntor só bloqueia entradas; nunca afeta saída.

## 8. Os 25 checks — o motor puro

### 8.1 Assinatura

```
hunter_risk_b3.evaluate(proposal, broker, account, limits, session, calendar, quote, kill_switch,
                        *, spec, margin, ops) -> RiskDecision
hunter_risk_b3.evaluate_exit(exit_request, position, kill_switch) -> RiskDecision    # sempre aprova
```

**[R0a]** A assinatura do desenho §3.1 ganha dois insumos nomeados, porque o motor é puro e não pode buscá-los:
`margin` (margem e `order_check` por volume candidato, calculados pelo serviço **antes** da avaliação para
`v = 1..max_contracts_per_order`) e `ops` (estado do registro: contagens do pregão, intenções abertas,
rejeições, reconciliação, auditoria, âncora). Sem rede, sem banco, sem relógio: o instante é `broker.as_of`.
`RiskModel`-like: `extra="forbid"`, imutável, **`float` recusado na construção** de todo campo monetário,
de preço, de volume e de limite (como `hunter_risk.base`).

Insumos (campos que os checks citam):

```
B3EntryProposal  proposal_id, organization_id, instance_id, strategy_key, strategy_version, params_hash,
                 session_date, window_id, symbol, side (buy|sell), requested_contracts (int ≥ 1),
                 ref_price, stop_price, target_price?, exit_at_utc?, signal_published_at,
                 signal_deadline_utc, entry_window_start_utc, entry_window_end_utc, created_at
BrokerSnapshot   as_of, positions[] {position_id, position_ticket, symbol, side, volume, price_open, sl, tp,
                 magic, time_msc},
                 orders[] {ticket, symbol, type, volume_current, price, magic, comment},
                 positions_ok, orders_ok,
                 terminal {connected, trade_allowed, tradeapi_disabled, version, read_ok}
AccountSnapshot  account_hash, trade_mode (demo|real|contest), currency, margin_mode, equity,
                 balance, margin_free, read_ok
RiskLimitsB3     §9 (com limits_version)
SessionContext   session_date, open_utc, close_utc, flatten_at_utc?, rico_flatten_utc?, session_end_utc,
                 entry_cutoff_utc?, grid_version, clock {offset_ms, measured_at, ok}
CalendarB3       is_holiday, is_shortened, has_grid, current_contract {symbol, root, expiry_date},
                 is_expiry_day, read_ok
QuoteSnapshot    bid, ask, last, time_utc (carimbo do servidor convertido pelo deslocamento medido), read_ok
KillSwitchB3     system, organization, robot (b3_kill_state), authority {phase, instance_id,
                 authority_expires_at}, registered_account_hash, k1_present,
                 armed_strategy {key, version, params_hash}
SpecInputs       pin: SpecPin (fixado no armamento), now: SpecNow (relido) — é o argumento `spec`
SpecPin/SpecNow  trade_tick_size, trade_tick_value, point, digits, volume_min, volume_step, volume_max,
                 trade_mode, filling_mode, expiration_mode, account_margin_mode, terminal_version,
                 package_version, order_lifecycle_proven, comment_preserved, stale_ticket_rejection_proven
                 (os três últimos vêm das provas T14, T8 e T13, gravadas com a evidência); SpecNow.status (ok|changed|unreadable)
MarginInputs     per_volume {v: margin_brl}, order_check {v: ok|refused(reason)}, read_ok
RobotOpsState    entries_today, open_entry_intents, unknown_intents (as três já sem a proposta em avaliação),
                 orphan_sltp_unknown (bool, por símbolo), entry_rejects[] (instantes),
                 breaker_latched, last_reconcile {at, clean, consistent_passes}, audit {api_last_ok_at,
                 buffer_len, buffer_writable}, day {anchor_equity, anchor_at, cash_flows_brl,
                 history_complete, realized_gross_brl, costs_positive_brl, open_mtm_gross_brl,
                 open_exit_fee_brl, mark_time, equity_delta_brl}, fee_schedule {per_leg_brl, source, valid}
```

### 8.2 A tabela

Todos os checks são gravados em `checks[]` como `{id, name, state, value, limit, input_ts, reason, message}`,
**mesmo depois da primeira reprovação**. `state ∈ passed | failed | unavailable`; `unavailable` reprova. Um check
cujo insumo depende de outro indisponível sai `unavailable` com `reason = upstream_unavailable:<id>`.
**Todos os 25 aplicam-se só a entradas; nenhum bloqueia saída** (§8.6). Notação: `tick = spec.trade_tick_size`,
`now = broker.as_of`.

| # | `name` | Insumo | Passa quando (dado) | `reason` se reprova (`failed`) / indisponível (`unavailable`) |
|---|---|---|---|---|
| 1 | `kill_switch` | `kill_switch`, `proposal.instance_id`, `now` | `most_restrictive(system, organization, robot) ∈ {ACTIVE, WARNING}` ∧ `authority.phase = entries` ∧ `authority.instance_id = proposal.instance_id` ∧ `now < authority_expires_at` | `kill_switch_trading_disabled`, `kill_switch_emergency`, `entries_not_armed`, `arming_other_instance`, `authority_expired` |
| 2 | `account_mode` | `account`, `kill_switch.registered_account_hash`, `k1_present` | `account.account_hash = registered_account_hash` ∧ (`trade_mode = demo` ∨ (`trade_mode = real` ∧ `k1_present`)) | `account_mismatch`, `real_account_without_k1`, `account_mode_unsupported` / `account_unreadable` |
| 3 | `terminal_state` | `broker.terminal` | `connected` ∧ `trade_allowed` ∧ ¬`tradeapi_disabled` | `terminal_disconnected`, `algo_trading_off`, `tradeapi_disabled` / `terminal_unreadable` |
| 4 | `symbol_whitelist` | `proposal.symbol`, `calendar.current_contract`, `limits.symbol_roots`, `spec.trade_mode` | `symbol = current_contract.symbol` ∧ `current_contract.root ∈ symbol_roots` ∧ `spec.trade_mode = SYMBOL_TRADE_MODE_FULL` ∧ ¬`is_expiry_day` | `symbol_not_current_contract`, `symbol_root_not_allowed`, `symbol_trade_mode_restricted`, `contract_expiry_day` / `contract_calendar_missing` |
| 5 | `trading_day` | `calendar`, `session.grid_version` | ¬`is_holiday` ∧ `has_grid` (a linha de grade vigente para a data; pregão encurtado só passa com a própria grade cadastrada) | `holiday`, `shortened_session_without_grid` (encurtado e sem grade) / `session_grid_missing` (sem grade, não encurtado), `calendar_unreadable` |
| 6 | `entry_window` | `session`, `limits.no_entry_first_min`, `proposal.entry_window_*` | `open_utc + no_entry_first_min ≤ now` ∧ (`entry_cutoff_utc` nulo ∨ `now ≤ entry_cutoff_utc`) ∧ `entry_window_start_utc ≤ now ≤ entry_window_end_utc` | `before_entry_window`, `after_entry_cutoff`, `outside_strategy_window` |
| 7 | `flatten_margin` | `session.flatten_at_utc`, `session.rico_flatten_utc`, `limits.min_minutes_before_flatten`, `limits.flatten_lead_min` | `flatten_at_utc − now ≥ min_minutes_before_flatten` ∧ `flatten_at_utc ≤ rico_flatten_utc − flatten_lead_min` | `too_close_to_flatten`, `flatten_after_rico_cutoff` / `flatten_schedule_unset` (D6 vazio ⇒ nenhuma entrada) |
| 8 | `quote_fresh` | `quote`, `session.clock`, `limits.max_quote_age_s`, `limits.max_clock_offset_s`, `limits.clock_check_max_age_s` | `0 < bid < ask` ∧ `now − time_utc ≤ max_quote_age_s` ∧ `time_utc − now ≤ 2 s` ∧ `clock.ok` ∧ `now − clock.measured_at ≤ clock_check_max_age_s` ∧ `|offset_ms| ≤ max_clock_offset_s × 1000` | `quote_invalid`, `quote_stale`, `quote_from_future`, `clock_offset_exceeded` / `quote_missing`, `clock_offset_unmeasured` |
| 9 | `spread` | `quote`, `tick`, `limits.max_spread_ticks` | `ask − bid ≤ max_spread_ticks × tick` | `spread_too_wide` / `upstream_unavailable:8` |
| 10 | `open_positions` | `broker.positions`, atribuição (§4.5) | `len(positions) = 0` (qualquer símbolo, nossa ou não; `max_open_positions = 1` = entrar só zerado) | `position_already_open`, `foreign_position_present` / `positions_unreadable` |
| 11 | `order_in_flight` | `broker.orders`, `ops.open_entry_intents`, `ops.unknown_intents`, `ops.orphan_sltp_unknown` | `len(orders) = 0` ∧ `open_entry_intents = 0` ∧ `unknown_intents = 0` ∧ nenhuma SLTP órfã incerta no símbolo (§4.3, P3′). As contagens **excluem a própria `proposal_id`** em avaliação (identificada por `proposal_id + instance_id`; depois do claim, também `fencing_token`); toda outra intenção continua bloqueando `[Astra R0a-1]` | `pending_order_present`, `foreign_order_present`, `entry_intent_in_flight`, `entry_intent_unknown`, `orphan_sltp_unknown` / `orders_unreadable` |
| 12 | `contracts_caps` | `proposal.requested_contracts`, `limits.max_contracts_per_order`, `limits.max_contracts_per_position` | `1 ≤ requested ≤ max_contracts_per_order` ∧ `requested ≤ max_contracts_per_position` | `requested_contracts_invalid`, `contracts_cap_exceeded` |
| 13 | `trades_today` | `ops.entries_today`, `ops.day.history_complete`, `limits.max_trades_per_day` | `entries_today < max_trades_per_day`, com `entries_today = max(nº de intenções do pregão com status ∈ {submitting, working, partially_filled, filled, cancel_requested, unknown, resolved_manual} ou `canceled` com `filled_volume > 0`, nº de negócios de entrada (`DEAL_ENTRY_IN`) com magic ∈ robot_magics no pregão)` — conta o que pode ter gerado exposição, **excluída a própria `proposal_id`** e os negócios da ordem dela (a reavaliação do `pre_send_gate` não cobra a operação duas vezes) | `max_trades_per_day_reached` / `trade_count_unavailable` |
| 14 | `daily_loss` | `ops.day`, `ops.fee_schedule`, `quote`, `limits.daily_loss_limit_brl`, `limits.pnl_reconcile_tolerance_brl` | `loss < daily_loss_limit_brl` (fórmula §8.3) | `daily_loss_limit` (**aciona** `TRADING_DISABLED`) / `day_anchor_missing`, `session_history_incomplete`, `pnl_reconcile_divergent`, `mark_stale` |
| 15 | `stop_geometry` | `proposal.stop_price`, `target_price`, `limit_price` (§8.3), `quote`, `tick`, `limits.min_stop_ticks`, `max_stop_ticks` | stop presente; múltiplo de `tick`; compra: `stop < limit_price` ∧ `stop < bid`; venda: `stop > limit_price` ∧ `stop > ask`; `|limit_price − stop| / tick ∈ [min_stop_ticks, max_stop_ticks]`; alvo, se houver, múltiplo de `tick` e do lado certo | `stop_missing`, `stop_off_tick`, `stop_wrong_side`, `stop_already_crossed`, `stop_too_close`, `stop_too_far`, `target_invalid` |
| 16 | `trade_risk_vs_allowance` | §8.3 | `n_final × risk_per_contract ≤ allowance` (`n_final ≥ 1`) | `trade_risk_exceeds_daily_allowance` / `upstream_unavailable:14`, `fee_schedule_missing` |
| 17 | `trade_risk_cap` | §8.3, `limits.max_loss_per_trade_brl` | `n_final × risk_per_contract ≤ max_loss_per_trade_brl` | `trade_risk_exceeds_cap` / `fee_schedule_missing` |
| 18 | `margin` | `margin`, `account`, `spec_pin.account_margin_mode`, `limits.alloc_per_trade_brl`, `margin_use_max_pct` | `account.currency = BRL` ∧ `account.margin_mode = spec_pin.account_margin_mode` ∧ `margin.per_volume[n_final] ≤ min(alloc_per_trade_brl, margin_free × margin_use_max_pct)` ∧ `margin.order_check[n_final] = ok` | `account_currency_not_brl`, `margin_mode_changed`, `margin_exceeds_allocation`, `margin_exceeds_free_margin`, `order_check_refused` / `margin_unavailable` |
| 19 | `broker_reject_breaker` | `ops.entry_rejects`, `ops.breaker_latched`, `limits.max_rejects`, `reject_window_s` | ¬`breaker_latched` ∧ `|{r ∈ entry_rejects : now − r ≤ reject_window_s}| < max_rejects` | `broker_reject_breaker` (**aciona** `TRADING_DISABLED`, *latched*) |
| 20 | `reconciliation_ok` | `ops.last_reconcile`, `limits.reconcile_interval_s` | `clean` ∧ `now − at ≤ 2 × reconcile_interval_s` ∧ `consistent_passes ≥ 2` | `reconciliation_divergent`, `reconciliation_settling` / `reconciliation_stale` |
| 21 | `audit_path` | `ops.audit`, `limits.entries_api_freshness_s` | `now − api_last_ok_at ≤ entries_api_freshness_s` ∧ `buffer_len = 0` ∧ `buffer_writable` | `audit_api_unreachable`, `audit_buffer_not_empty`, `audit_buffer_unwritable` |
| 22 | `signal_validity` | `proposal`, `kill_switch.armed_strategy`, `limits.approval_ttl_s` | `signal_published_at ≤ signal_deadline_utc` ∧ `entry_window_start_utc ≤ now ≤ entry_window_end_utc` ∧ `(key, version, params_hash) = armed_strategy` ∧ `now − created_at ≤ approval_ttl_s`. O carimbo do sinal nunca é renovado; a aprovação vale 30 s; os insumos de mercado valem segundos (check 8) — três relógios separados | `signal_late`, `signal_outside_window`, `strategy_not_armed`, `strategy_version_mismatch`, `params_hash_mismatch`, `proposal_stale` |
| 23 | `spec_unchanged` | `spec_pin`, `spec_now` | `spec_now.status = ok` ∧ todos os campos de `SpecPin` iguais em `SpecNow` | `spec_changed`, `terminal_version_changed`, `package_version_changed` / `spec_unreadable` (3 falhas seguidas) |
| 24 | `slippage_guard` | `proposal.ref_price`, `quote`, `tick`, `limits.max_slippage_ticks`, `spec_pin.order_lifecycle_proven` | `order_lifecycle_proven` ∧ `ref_price` múltiplo de `tick` ∧ `|ref_price − toque| ≤ max_slippage_ticks × tick` (toque = `ask` na compra, `bid` na venda); `limit_price` derivado (§8.3), nunca recebido | `order_lifecycle_unproven`, `reference_off_tick`, `reference_drifted` |
| 25 | `equity_floor` | `account.equity`, `limits.equity_floor_brl` | `equity_floor_brl` nulo (gravado `passed`, `limit = null`, "desligado") ∨ `equity ≥ equity_floor_brl` | `equity_below_floor` / `account_unreadable` |

Cada um dos 25 tem, na tabela de testes de R1, **um caso que passa e um que reprova** — e, onde existe
`unavailable`, um terceiro caso.

### 8.3 Fórmulas (desenho §3.4–§3.5)

```
limit_price         = ref_price + max_slippage_ticks × tick   (compra) | ref_price − max_slippage_ticks × tick (venda)
stop                = stop_price (já alinhado ao tick pelo lado: compra para baixo, venda para cima; senão check 15)
risk_per_contract   = |limit_price − stop| / tick × trade_tick_value
                    + stop_slippage_ticks × trade_tick_value
                    + 2 × fee_schedule.per_leg_brl                      # tarifas ida e volta, sem deslizamento
loss                = max(0, −(realized_gross_brl − costs_positive_brl + open_mtm_gross_brl − open_exit_fee_brl))
allowance           = daily_loss_limit_brl − loss
```

Contrato da perda do pregão (check 14): cada negócio entra uma vez (chave `deal ticket`); custo por perna =
`max(modelado, |commission| + |fee|)`, sempre positivo (comissão negativa nunca vira ganho); negócios que não são
de negociação ficam fora; a soma é conferida contra `equity_delta_brl − cash_flows_brl` do mesmo intervalo, e
divergência > `pnl_reconcile_tolerance_brl` → `unavailable` `pnl_reconcile_divergent`; a posição aberta desconta
só a tarifa de saída; sem âncora, sem histórico completo ou com marca mais velha que `max_quote_age_s` →
`unavailable`. **O número que esconde perda é o zero**: nenhum campo ausente vira 0.

Sizing:

```
caps = { requested:            requested_contracts,
         max_contracts_per_order, max_contracts_per_position,
         alloc_margin:         floor(alloc_per_trade_brl / margin.per_volume[1]),            # D3
         free_margin:          floor(margin_free × margin_use_max_pct / margin.per_volume[1]),
         trade_risk_cap:       floor(max_loss_per_trade_brl / risk_per_contract),          # D4
         daily_allowance:      floor(allowance / risk_per_contract) }
n_raw   = min(caps.values())
n       = floor(n_raw × 0,5) se efetivo = WARNING, senão n_raw                            # 1 vira 0
n_final = normalizado a volume_min / volume_step / volume_max, sempre para baixo
n_final < 1 → reprovado, decisão com reason "sizing_zero" e o check do teto vencedor reprovado com o seu reason
depois: checks 16, 17, 18 avaliados com n_final (margem e order_check do volume final)
```

`binding_constraint` = a chave de `caps` que deu `n_raw` (desempate pela ordem acima), ou `warning_halving`
se o multiplicador mudou `n`, ou `volume_step` se a normalização mudou `n`. Insumos recusados antes do sizing
(viram `unavailable` no check de origem): valores não finitos ou não positivos, bid/ask invertidos ou zerados,
moeda ≠ BRL, `margin.per_volume[1]` ausente.

### 8.4 `RiskDecision`

```
{ proposal_id, approved, reasons[] (reason dos checks failed/unavailable, na ordem dos ids; mais "sizing_zero"),
  checks[25], sizing {caps, n_raw, n_final, binding_constraint, risk_per_contract_brl, risk_modeled_brl,
  allowance_brl, limit_price, bracket_gap_ticks: null}, kill_switch_effective,
  triggers[] (b3_kill_cause a aplicar: daily_loss_limit | broker_reject_breaker),
  limits_version, grid_version, spec_pin_id, as_of, approved_at = as_of, expires_at = as_of + 30 s }
```

O motor **não escreve** nada: `triggers[]` é o que o serviço persiste como transição de kill switch, auditada.

### 8.5 Invariantes do motor (propriedades, hypothesis)

`risk_modeled = n_final × risk_per_contract ≤ min(max_loss_per_trade_brl, allowance)` sempre que aprovado;
`n_final ≤` cada teto; `WARNING` com `n_raw = 1` dá 0; efetivo ≥ `TRADING_DISABLED` ⇒ nunca aprova; mesma entrada
⇒ mesma decisão (determinismo, hash do JSON); `len(checks) = 25` em toda decisão; `evaluate_exit` sempre aprova;
perda do pregão com negócio duplicado, comissão negativa e depósito no meio do dia = a perda verdadeira.

### 8.6 `evaluate_exit`

`evaluate_exit(exit_request{position_ticket, exit_reason}, position, kill_switch) → RiskDecision(approved =
True)` com checks informativos (`kill_switch` com o efetivo, `position_seen`), nenhum capaz de reprovar. Calculado
localmente e gravado sem esperar a API (buffer). **O motor de risco nunca bloqueia saída.** O que pode impedir a
instância de enviar uma saída é a guarda de mutação (§2.4) e K1 (§13, item 3) — perguntas de identidade, não de
risco.

## 9. Limites e valores iniciais (`b3_risk_profiles.limits`, versionado, editável só pelo Everton)

Toda edição: validação, `audit_logs` antes/depois, nova `limits_version`. **Valores do Everton** vêm da conversa
de 17/10/2026 (desenho §3.2); **padrão do desenho, confirmar com o Everton** = proposta do desenho, não
consentimento; **proposta R0a** = número que o desenho não deu e que este contrato precisa para a sessão demo
rodar, **não medido**, confirmar com o Everton e medir em T11/T13/T14.

| Chave | Valor | Origem |
|---|---|---|
| banca | **pendente (D2)** — "acima de R$ 10.000" (17/10) ou "R$ 1.000" (mensagem anterior do mesmo dia). O robô **lê o patrimônio da corretora** (`account.equity`); nenhum limite é derivado da banca; os limites valem como gravados | Everton; D2 aberta |
| `daily_loss_limit_brl` | **9000** | **Everton, 17/10** (a Sexta-feira avisou uma vez que é ≈ 90 % da banca; ele manteve) |
| `alloc_per_trade_brl` | **1000** | **Everton, 17/10**; leitura "margem de day trade consumida ≤ R$ 1.000" em futuros = **D3, padrão do desenho, confirmar com o Everton** |
| `max_loss_per_trade_brl` | 250 | D4, padrão do desenho, confirmar com o Everton |
| `max_contracts_per_position` | 1 | D5, padrão do desenho, confirmar com o Everton (= escopo do ADR 0007) |
| `max_contracts_per_order` | 1 | D5, padrão do desenho, confirmar com o Everton |
| `max_trades_per_day` | 1 | D5, padrão do desenho, confirmar com o Everton |
| `symbol_roots` | `["WIN"]` | ADR 0007 (WDO fora da v1) |
| `flatten_at_local` | **vazio ⇒ nenhuma entrada** (check 7 `flatten_schedule_unset`) | D6: sem padrão; depende do horário da Rico, que o Everton lê na área logada |
| `rico_flatten_local` | **vazio ⇒ nenhuma entrada** | D6, idem |
| `fee_schedule` | tarifa B3 R$ 0,256 por perna (plano irmão §1.4) **só se o RLP estiver ativo**; sem tabela com fonte e data → robô não arma (`fee_schedule_missing`) | D7, padrão do desenho, confirmar com o Everton |
| trava diária volta no pregão seguinte, depois de reconciliar | sim | D8, padrão do desenho, confirmar com o Everton |
| `warning_fraction` | 0,5 | padrão do desenho, confirmar com o Everton |
| `stop_slippage_ticks` | 2 | padrão do desenho, confirmar com o Everton |
| `reconcile_interval_s` | 5 | padrão do desenho, confirmar com o Everton |
| `bracket_step_s` | 1 | padrão do desenho, confirmar com o Everton |
| `send_budget_s` | 3 | padrão do desenho, confirmar com o Everton |
| `approval_ttl_s` | 30 | **regra da casa, fixa** (não editável) |
| `max_open_positions` | 1 | **fixo na v1** (check 10) |
| `api_heartbeat_s` / `entries_api_freshness_s` | 5 / 15 | padrão do desenho, confirmar com o Everton |
| `ea_hb_stale_s` | 30 | padrão do desenho, confirmar com o Everton (parâmetro do EA) |
| `spec_reread_s` / falhas para `spec_unreadable` | 60 / 3 | padrão do desenho, confirmar com o Everton |
| `max_slippage_ticks` | 1 | proposta R0a (é o "1 tick de entrada pelo preço-limite" da conta do desenho §3.5) |
| `max_quote_age_s` | 5 | proposta R0a |
| `max_clock_offset_s` | 2 | proposta R0a (igual à tolerância de carimbo à frente do check 8) |
| `clock_check_max_age_s` | 900 | proposta R0a (medição a cada 10 min do desenho §7.4, com folga de 5 min) |
| `max_spread_ticks` | 2 | proposta R0a |
| `min_stop_ticks` / `max_stop_ticks` | 10 / 400 | proposta R0a (H-038: stop ≈ 1 035 pts ≈ 207 ticks cabe no meio) |
| `no_entry_first_min` | 5 | proposta R0a |
| `entry_cutoff_local` | vazio (só a janela da estratégia e o check 7) | proposta R0a |
| `min_minutes_before_flatten` | 15 | proposta R0a |
| `flatten_lead_min` | 20 | proposta R0a |
| `bracket_deadline_s` | 120 | proposta R0a |
| `bracket_max_k` | 4 | proposta R0a |
| `naked_grace_s` | 5 | proposta R0a (a meta do desenho é `sl` confirmado em 1 s) |
| `entry_cancel_after_s` | 10 | proposta R0a (dentro da janela de 5 min da H-038) |
| `slippage_alert_ticks` | 2 | proposta R0a |
| `max_rejects` / `reject_window_s` | 3 / 600 | proposta R0a |
| `margin_use_max_pct` | 0,5 | proposta R0a |
| `pnl_reconcile_tolerance_brl` | 5 | proposta R0a |
| `ipc_call_timeout_s` | 10 | proposta R0a |
| `sltp_record_budget_ms` / `sltp_record_api_ms` | 500 / 300 | proposta R0a (orçamento total da gravação durável antes de enviar a SLTP ou a intenção de saída, e a parte dele dada à API; o resto é do `fsync` do buffer, §4.3; com `bracket_step_s = 1` cabe no passo) |
| `hb_file_interval_s` | 2 | proposta R0a |
| `ea_hb_future_tolerance_s` | 5 | proposta R0a (carimbo do batimento mais à frente que isso = ilegível) |
| `equity_floor_brl` | vazio (desligado) | padrão do desenho |

Comportamentos (não são números) que o desenho propõe e o Everton confirma: **D9** PC = operação supervisionada;
sem supervisão = VPS (decidir antes do primeiro dia real). **D10** com o Python morto ninguém além dele zera; o `sl`
confirmado fica no servidor (e é zerado na virada). **D11** posição manual dele: o robô só para. **D12** ele lança a
nota de corretagem. **D13** Sentry `critical` por e-mail até ele escolher outro canal. **D14** todo reinício exige
dois atos dele (conceder gestão, armar entradas). **D15** um host (o PC). **D16** (a) no prazo de saída, nenhuma
ordem a mercado — alerta e ele zera à mão; (b) robô reiniciado sem a API só lê e avisa. Todos: **padrão do
desenho, confirmar com o Everton**. **D17 (nova, desta tarefa `[Astra R0a-5]`)**: quando o piso não pode ser
colocado (posição de um pregão para o outro que abriu além do stop, ou stop rompido enquanto a posição estava
sem `sl`), o robô **não faz nada** e alerta (padrão R0a); a alternativa — pôr um colchete abaixo do piso, isto é,
**tentar sair pelo colchete** (com o atraso possível de toda saída pelo colchete) mais longe do que o stop
aprovado — é exceção de risco que só ele decide.

Validações na edição (recusa nomeada `limits_invalid:<campo>`): `max_contracts_per_order ≤
max_contracts_per_position`; `max_loss_per_trade_brl ≤ daily_loss_limit_brl`; `flatten_at_local ≤
rico_flatten_local − flatten_lead_min`; `min_stop_ticks < max_stop_ticks`; frações em (0, 1]; todo número como
string decimal no JSON (número JSON recusado, como `RiskModel._refuse_float`).

## 10. Batimentos

### 10.1 `hunter_hb` — o arquivo que o EA vigia lê

Caminho: `terminal_info().data_path + "\MQL5\Files\hunter_hb"` (a pasta que o `FileOpen` do MQL5 alcança).
Conteúdo: **uma** linha ASCII, campos `chave=valor` separados por `;`, terminada por `\n`, ≤ 256 bytes, nesta
ordem exata:

```
v=1;ts=<epoch ms UTC>;seq=<inteiro>;inst=<instance_id>;acct=<account_hash>;end=1
```

| Campo | Significado | Regra |
|---|---|---|
| `v` | versão do formato | o EA recusa `v` ≠ 1 como "batimento ilegível" |
| `ts` | instante da escrita, `time.time_ns() // 1_000_000` do PC | o EA compara com `TimeGMT()` do mesmo PC |
| `seq` | contador crescente por instância | o EA detecta parada pela **mudança** do par `(inst, seq)` medida em `GetTickCount64` (abaixo) |
| `inst` | `instance_id` (identificador do remetente) | idem; uma instância nova (`inst` diferente) conta como mudança |
| `acct` | `account_hash` (§1.1) | o EA calcula `sha256(IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) + "\|" + AccountInfoString(ACCOUNT_SERVER))` por `CryptEncode(CRYPT_HASH_SHA256, …)` e compara |
| `end` | sentinela | linha sem `;end=1` final = leitura rasgada, tratada como ilegível |

É sinal de vida (instante + conta, com o identificador do remetente), não estado de negócio (ADR 0007, exceção
dos arquivos locais). Escrita: a cada `hb_file_interval_s`, o robô escreve e **fecha** `hunter_hb.tmp`, depois
`os.replace` para `hunter_hb` (atômico no NTFS). O EA abre o arquivo sem compartilhamento para exclusão
(`FILE_SHARE_READ | FILE_SHARE_WRITE` não inclui "delete"), então a troca **pode falhar** enquanto o EA o lê
`[Astra R0a-10]`: o robô tenta no próximo ciclo, **nunca** trunca nem reescreve no lugar o arquivo final; 5 falhas
seguidas → alerta `warning` `hb_file_unwritable`. Uma troca que falha deixa o arquivo antigo, e o EA alerta por
atraso — fica atrasado, não cego. R7 tem um teste real de colisão (EA lendo enquanto o robô troca). O batimento é
escrito em **toda** fase, inclusive `read_only` — ele prova que o processo vive, não que tem autoridade.

**O que o EA faz com ele (normativo para R7):** `OnTimer` a cada 5 s abre (`FILE_READ | FILE_TXT | FILE_ANSI |
FILE_SHARE_READ | FILE_SHARE_WRITE`), lê a linha **inteira** e confere todos os campos e a sentinela, fecha na hora.
Guarda o último par `(inst, seq)` visto e o `GetTickCount64()` do instante em que esse par **mudou** (reler o mesmo
par não renova nada). O batimento está **parado** se qualquer um: arquivo ausente ou ilegível; `acct` ≠ a conta do
terminal; `ts` mais de `ea_hb_future_tolerance_s` à frente de `TimeGMT()` (relógio do PC andou para trás, ou carimbo
inválido); `TimeGMT() × 1000 − ts > ea_hb_stale_s × 1000`; **ou** `GetTickCount64() − tick_da_última_mudança >
ea_hb_stale_s × 1000` — o tempo monotônico pega o caso em que o relógio do PC retrocede depois de o Python morrer
e o carimbo antigo parece recente `[Astra R0a-10]`. Notifica (`SendNotification`) quando, com
`PositionsTotal() > 0`: (1) batimento parado; (2) uma posição com `POSITION_SL = 0` há mais de `naked_grace_s` (parâmetro do EA); (3)
faltam menos de 15 min para o horário compulsório mais cedo que o Everton grava no parâmetro do EA (D6). No
máximo uma notificação por condição a cada 5 min, e nunca acima do limite oficial (2/s, 10/min). **O EA não
contém `OrderSend`, `OrderSendAsync`, `CTrade` nem `PositionClose`**; o teste de R7 procura esses nomes no fonte e
falha.

### 10.2 `hb:b3:robot` — o batimento pela API

`POST /api/v1/orgs/{org}/b3/robot/heartbeat` a cada `api_heartbeat_s`; a API grava `hb:b3:robot` no Redis da VPS
(TTL 60 s) e a linha mais recente no Postgres. O cão de guarda (R9a) alerta `critical` se faltar por > 30 s
durante o pregão, e com prioridade máxima se o último batimento tinha posição.

```
{ v: 1, as_of, instance_id, host_hash, account_hash, phase (b3_authority_phase), authority_expires_at,
  kill_effective, terminal {connected, trade_allowed, ping_last_us}, clock_offset_ms,
  epoch_id, positions [{position_id, position_ticket, symbol, side, volume, state (b3_position_state),
              degraded_reason, sltp_slot, sl, tp, exit_reason, exit_deadline_at, attribution}],
  sltp_durability_ok,
  open_entry_intents, unknown_intents, last_reconcile_at, reconcile_clean, buffer_len,
  spec_status (ok|changed|unreadable), entries_ready (bool), entries_block_reasons [] }
```

Nunca carrega `login`, senha, `fencing_token` nem o número da conta (teste de segredo, desenho §8).

## 11. Matriz de falhas

Cada linha é um teste de R5 com o falso do MT5 (`test_fm_<id>`) e, onde indicado, uma prova da sessão demo.
"Entradas" e "Gestão" dizem o que continua possível.

| id | Cenário | O que o robô observa | Estado esperado | Entradas | Gestão / saídas | Alerta | Prova |
|---|---|---|---|---|---|---|---|
| F1 | Python morto, posição `protected` | — (o EA vê `ts` parado) | servidor mantém `sl`; na partida: `read_only` → diagnóstico | não | servidor (stop) e Everton (R3/R4) | EA ≤ 30 s; cão de guarda > 30 s | T3, T10 |
| F2 | Python morto, sem posição | — | nada | não | — | cão de guarda | T10 |
| F3 | terminal morto ou desconectado | `initialize` falha ou `connected = False` | todas as leituras `unavailable`; nenhuma mutação possível | não (check 3) | só servidor e Everton | `critical` se havia posição | T16 |
| F4 | IPC travado (chamada MT5 não volta) | chamada > `ipc_call_timeout_s` | trava local `ipc_hung` (G5): nenhuma mutação nova; o resultado da chamada, se vier, é gravado; se era mutação → `unknown`; reinício pelo Everton | não | nenhuma mutação até reinício | `critical` `ipc_hung` | teste com falso |
| F5a | API fora < 15 s | falha HTTP | gestão normal; eventos ao buffer | sim até 15 s, mas claim exige API → na prática não | normal | — | T16 |
| F5b | API fora > 15 s com posição | idem | `management` mantida até `authority_expires_at` | não (check 21) | colchete e proteção continuam | `critical` (cão de guarda) | T16 |
| F6 | disco cheio / `fsync` falha, com a API respondendo | erro de escrita | gravações confirmadas pela API; eventos que não precedem envio ficam em memória | não (check 21) | **não atrasada** (a API confirma a gravação obrigatória); com a API também fora → F48 | `critical` `audit_buffer_unwritable` | teste com falso |
| F7 | troca de conta (demo→real ou outra), inclusive A → B → A | `account_hash` ≠ autoridade em G1 | trava local `account_changed` (G0, *latched*): a volta para a conta certa **não** destrava; leituras anteriores descartadas; nenhuma mutação até reinício; nova instância fica `read_only` se a conta não for a registrada | não | nenhuma | `critical` `account_mismatch` | T16 |
| F8 | K1 desligada com posição aberta (partida em conta real sem K1) | `k1_present = false` | `read_only` inerte, nem saída | não | servidor e Everton; saída por tempo **não** acontece | `critical` "só a rota manual zera" | drill |
| F9 | K2 desligada e religada | `trade_allowed = False` | bloqueio local imediato; `TRADING_DISABLED(manual_route)`; fase `entries → management`; religar não destrava | não até rearme + K3 | terminal recusa toda requisição enquanto K2 off | `critical` | T5, T16 |
| F10 | fill parcial da entrada | `DONE_PARTIAL` / volume < pedido | intenção `partially_filled`; posição com o volume parcial, `sl` da requisição | não (check 11) | proteção do parcial; resto cancelado com confirmação | — | T14 |
| F11 | cancelamento × fill | cancelamento pedido e fill chegam juntos | `cancel_requested` → `canceled` com `filled_volume` lido; posição maior que o registrado → corretora vence | não até 2 passes | protegida (o `sl` em *netting* cobre a posição) | `warning` | T14 |
| F12 | saída por tempo × stop do servidor | `sl` dispara durante o colchete | colchete só manda SLTP; posição fecha pelo servidor (`server_sl`/`bracket_sl`); nenhuma ordem nossa soma exposição | não | — | — | T13 |
| F13 | suspenso depois do claim | ao voltar: `mono` e `utc` saltaram | `aborted_before_send` (`budget_exhausted` ou `clock_jump`); se morto, `unknown` | não | — | `warning` | T15 |
| F14 | suspenso depois da última conferência | — | residual R-1: envio tarde; resultado tratado normalmente; nasce com `sl` | não (check 11 até resultado) | protegida | — | T15 |
| F15 | `order_send` volta depois da expiração da aprovação | retorno tardio | resultado gravado como veio (`filled`/`working`/…); a expiração não desfaz | não | protegida | `warning` `late_send_result` | teste com falso |
| F16 | posição manual no mesmo símbolo que deixa a mesma quantidade final | negócio `DEAL_REASON_CLIENT` na cadeia | `unattributed` (`ambiguous`) | não | nenhuma mutação; rota manual | `critical` | T6 |
| F17 | mudança de limite entre aprovação e envio | versão diferente | claim recusa `limits_changed` ou `limits_changed_before_send` | não nesta janela | — | `info` | teste com falso |
| F18 | partida com posição desprotegida desde antes | `sl = 0`, `time_msc` antigo | `degraded` direto; nenhuma mutação antes da concessão | não | reparo depois da concessão | `critical` (app + EA) | T16 |
| F19 | SLTP incerto (90/95/99), reinício entre A e B | slot `unknown` no registro | slot herdado `unknown`; B **não** é enviado | não | só P1/P3/P4 liberam | `critical` `exit_unknown`/`protection_unknown` | T13 + T16 juntos `[Astra R6]` |
| F20 | PC dormiu | salto `mono` × `utc`, intervalo sem batimento | todo envio pendente abortado; reconciliação forçada; autoridade conferida pelos dois relógios (G3) | não até reconciliar | retoma se a autoridade vale | `warning` | T15 |
| F21 | virada de pregão com posição | `sl = tp = 0` lidos no pregão novo | §4.4: piso colocável → reparo, depois `overnight_carry` (com gestão nova); senão `floor_unplaceable` (F39) | não | depois da concessão | `critical` | demo, se ocorrer |
| F22 | autoridade vence com posição aberta | G3 falha | nenhuma mutação | não | servidor e Everton | `critical` `authority_expired_with_position` | T16 |
| F23 | segundo Windows na mesma conta | `host_hash` ≠ autorizado | `read_only` para sempre; **zero mutações**, com ou sem API | não | nenhuma | `warning` | T15 |
| F24 | relógio do servidor deslocado | `|offset| > max_clock_offset_s` ou não medido | check 8 `unavailable` | não | normal | `warning` | T11 |
| F25 | rejeições em série na entrada | `broker_rejected` ≥ `max_rejects` | `TRADING_DISABLED(broker_reject_breaker)` *latched* | não até rearme | normal | `critical` | T9 |
| F26 | histórico de negócios incompleto (ou reconexão com volume igual depois de mudança manual) | `history_complete = false` ou lacuna de conexão | checks 13 e 14 `unavailable`; atribuição `unreadable` até leitura completa (sem cache, §4.5) | não | **nenhuma mutação** daquela posição (G7); stop do servidor fica | `warning` | teste com falso `[Astra R0a-7]` |
| F27 | `EMERGENCY` com o Python morto | — | durável; a instância nova lê na partida; zera só depois da concessão | não | servidor e Everton até lá | — | T5 passo 2 |
| F28 | inversão detectada | lado oposto ao registrado | `exiting(reversal)` + `TRADING_DISABLED(reversal_detected)` *latched* | não até rearme | colchete | `critical` `reversal_detected` | T13 |
| F29 | `order_send` de entrada devolve `None` | `last_error()` | `unknown` (`send_no_result`) | não | — | `critical` `entry_unknown` | T9 |
| F30 | `unknown` de entrada com dois candidatos | resolução ambígua | continua `unknown` | não | posição tratada pela atribuição | `critical` | teste com falso |
| F31 | reenvio do mesmo sinal/evento 2× | proposta já existe para a janela | nenhuma proposta nova; uma ordem no máximo | — | — | — | teste obrigatório |
| F32 | dois executores com o mesmo sinal | dois claims | um ganha; o outro recebe `claimed: false` | — | — | — | teste com Postgres real |
| F33 | primeira entrada autorizada passa pelo `pre_send_gate` | a própria intenção `submitting` | a reavaliação exclui a própria proposta dos checks 11 e 13; envia | sim (esta) | — | — | teste com falso; e uma 2.ª intenção concorrente **é** bloqueada `[Astra R0a-1]` |
| F34 | API fora, SLTP A gravada só no buffer, processo morre com A em trânsito | — | partida: buffer entregue na fase 0 → slot herdado `unknown` → **B não é enviado** depois da concessão | não | só P1/P3/P4 liberam | `critical` | teste com falso (A95/B99 com A entregue depois) `[Astra R0a-2]` |
| F35 | buffer ilegível na partida | cadeia de hash quebrada | `journal_lost`: slots e intenções da instância anterior herdados `unknown` | não | nenhuma modificação nas posições afetadas até prova | `critical` | teste com falso |
| F36 | o Everton põe à mão os mesmos níveis de uma SLTP incerta | nível lido = pedido | slot continua `unknown` (nível igual não é prova) | não | nenhuma modificação | `critical` | teste com falso `[Astra R0a-3]` |
| F37 | posição fecha com SLTP incerta; nova posição no mesmo símbolo | P3 sem `stale_ticket_rejection_proven` | SLTP órfã incerta bloqueia entradas no símbolo (P3′) | não até P4 ou prova T13 | — | `critical` | T13 (A atrasada → P fecha → Q abre → A chega) `[Astra R0a-4]` |
| F38 | ticket da posição muda por operação de serviço | `position_ticket` novo, mesmo `position_id` | mesma máquina, mesmo slot; envios usam o ticket novo | — | normal | `info` | teste com falso `[Astra R0a-4]` |
| F39 | posição de um pregão para o outro abre além do stop | `sl = 0`, piso do lado errado do toque | `degraded` (`floor_unplaceable`), nenhum envio | não | nenhuma (D17) | `critical` | teste com falso `[Astra R0a-5]` |
| F40 | reinício no meio de uma saída | intenção de saída no registro/buffer | prazo original recuperado; se vencido → `exit_overdue`; gatilho que sumiu não cancela a saída | não | colchete com o prazo original | `critical` se vencido | teste com falso `[Astra R0a-9]` |
| F41 | relógio do PC errado no instante da concessão | `server_now_utc` da API ≠ relógio local | `authority_mono_deadline` ancorado no relógio da API; vencimento real respeitado | — | para no vencimento real | `warning` `clock_offset` | teste com falso `[Astra R0a-8]` |
| F42 | Python morre e o relógio do PC retrocede | `ts` antigo parece recente | o EA usa `GetTickCount64` desde a última mudança de `(inst, seq)` → batimento parado | — | — | EA ≤ `ea_hb_stale_s` | teste do EA `[Astra R0a-10]` |
| F43 | partida com a API fora | sem resposta | `read_only` para sempre até a API voltar; zero mutações | não | servidor e Everton | `critical` | T16 |
| F44 | concessão gravada para instância que já morreu | linha `active` de `instance_id` morto | instância nova não herda; Everton revoga e concede à nova | não | depois da nova concessão | `warning` | T16 |
| F45 | `EMERGENCY` gravado durante a recuperação de uma instância nova | kill relido no passo 10 da partida | zera pelo colchete depois da concessão | não | colchete | `critical` | T16 |
| F46 | resultado de uma requisição da instância anterior chega depois que a nova assumiu | resultado tardio (via reconciliação da corretora) | gravado contra a intenção/slot original; o slot só libera por P1/P3/P4 | não | conforme o slot | `warning` | teste com falso |
| F47 | claim com resposta perdida e repetição | `claimed: true` repetido | mesmo resultado, um só envio (`send_consumed`) | sim (esta) | — | — | teste com falso + Postgres real |
| F48 | API e disco falham juntos com posição aberta (inclusive no meio do colchete) | gravação durável não confirmada | nenhuma SLTP enviada; colchete/reparo pausados; último `sl` confirmado fica | não | pausada até uma das duas voltar | `critical` `sltp_durability_lost` | teste com falso (com `fsync` que trava e que falha) `[Astra R0a-2, r2]` |
| F49 | `EMERGENCY`, 1.ª SLTP da saída rejeitada (nada muda no servidor), processo morre, Everton rearma antes da partida | transição durável de `EMERGENCY` dentro da vida da posição | obrigação de saída recuperada com o `changed_at` original; prazo vencido → `exit_overdue` | não | colchete | `critical` | teste com falso `[Astra R0a-9, r2]` |

## 12. Invariantes (cada uma é um teste que falha se quebrar)

| id | Invariante | Onde |
|---|---|---|
| I-E-1 | nenhuma requisição de entrada sem `proposal_id` com `risk_decision.approved = true` persistida **e** claim ganho por esta instância | R5 + R4 |
| I-E-2 | uma intenção `submitting`/`unknown` nunca é reenviada; reprocessar o mesmo sinal ou evento não cria segunda ordem | R5 (F31) |
| I-E-3 | aprovação com 31 s nunca é executada; aprovação de outra instância nunca é executada | R4 + R5 |
| I-E-4 | `client_order_id` é função só do `proposal_id` | R5 |
| I-SL-1 | nenhuma requisição SLTP com `sl = 0`; nenhuma mais larga que `floor(p)` | R2 (adaptador recusa antes do terminal) + R5 |
| I-SL-2 | para requisições aceitas da mesma posição e lado, qualquer permutação deixa o `sl` pelo menos tão apertado quanto o stop pedido pela ordem — comprado `sl ≥ floor_0`, vendido `sl ≤ floor_0` (propriedade sobre sequências geradas, os dois lados) `[Astra R0a-5]` | R5 |
| I-SL-3 | com `sltp_slot = unknown`, nenhuma modificação nova até P1, P3 ou P4; o slot sobrevive a reinício e a troca de instância; ausência de resultado depois de queda é `unknown`, nunca `idle` | R5 (F19, F34, F35) |
| I-SL-5 | nenhuma SLTP (nem intenção de saída) é enviada sem gravação durável **confirmada** (ack da API ou `fsync` com sucesso) dentro de `sltp_record_budget_ms`; nenhuma mutação de gestão antes da linha `epoch_open` durável | R5 (F34, F48) |
| I-X-4 | obrigação de saída disparada durante a vida da posição (inclusive `EMERGENCY` já rearmado) é recuperada na partida; nunca com prazo recalculado a partir de agora | R5 (F40, F49) |
| I-SL-6 | nenhum colchete nem reparo mais largo que o piso; piso não colocável → nenhum envio (`floor_unplaceable`) | R2 + R5 (F39) |
| I-X-3 | uma saída iniciada termina só em `closed` comprovado; o prazo nunca é renovado por reinício | R5 (F40) |
| I-A-4 | travas locais (`account_changed`, `ipc_hung`, `startup_ineligible`) só caem com reinício do processo | R5 (F7) |
| I-A-5 | nenhuma mutação na partida antes da entrega do buffer e da concessão de gestão | R5 (F34, F43) |
| I-E-5 | a reavaliação do `pre_send_gate` exclui só a própria proposta; outra intenção aberta bloqueia | R1 + R5 (F33) |
| I-SL-4 | toda SLTP carrega `position` = o `position_ticket` atual, gravado como `request_position_ticket`; máquina e slot são por `position_id`, nunca por ticket | R2 + R5 (F38) |
| I-X-1 | nenhuma requisição diferente de `TRADE_ACTION_SLTP` para posição aberta, em qualquer caminho de saída | R5 |
| I-X-2 | requisição que aumenta/inverte num símbolo com posição e `sl = 0` é recusada (`would_delete_stop`); redução e fechamento total nunca são recusados por isso | R2 |
| I-A-1 | nenhuma mutação sem a guarda §2.4; instância sem autoridade (vencida, revogada, outra conta, outro host) envia zero requisições | R5 (F7, F22, F23) |
| I-A-2 | concessão de gestão não limpa `EMERGENCY`, trava diária, rejeições, inversão, nem `unknown` | R4 + R5 |
| I-A-3 | K2 desligada observada bloqueia entradas na mesma iteração, antes de qualquer escrita | R5 |
| I-K-1 | kill efetivo ≥ `TRADING_DISABLED` ⇒ nenhuma entrada aprovada nem enviada | R1 + R4 (mesma transação do claim, teste em duas sessões reais) |
| I-K-2 | releitura do kill switch a cada 2 s (máx. 10 s) com ou sem evento | R5 |
| I-$-1 | dinheiro, preço e volume em `Decimal`; `float` só dentro de `hunter_exchanges.mt5.convert`, com ida e volta exata para todo múltiplo de tick na faixa | R1, R2 |
| I-$-2 | `patrimônio = caixa + Σ posições` no relatório diário | R5 |
| I-S-1 | `login`/`password` nunca em chamada, configuração serializada, log ou batimento | R2, R5 |
| I-S-2 | o EA não contém `OrderSend`/`OrderSendAsync`/`CTrade`/`PositionClose` | R7 |

## 13. Diferenças declaradas em relação às regras da casa (para o ADR 0007 e as revisões)

1. **Dinheiro real antes da Fase 4**, só neste escopo — ADR 0007 (D1).
2. **Dois arquivos locais** (`hunter_hb` e o buffer), nenhum decide — ADR 0007.
3. **"Saídas sempre permitidas" ganha uma precisão.** O motor de risco nunca bloqueia saída (§8.6). Mas
   **quem** envia é a instância com autoridade (§2.4): sem identidade e autoridade verificadas — partida sem API,
   conta trocada, host não autorizado, autoridade vencida — e com K1 ausente em conta real, o robô **não envia
   nada, nem saída**; a posição fica com o `sl` no servidor e as rotas R3/R4 do Everton. É o preço de nunca mexer
   numa conta não verificada (Astra R4-2/R4-3) e é a limitação D16b.
4. **`EMERGENCY` zera** (pelo colchete), ao contrário do SPOT e do meme, a pedido do Everton e porque WIN é o
   contrato mais líquido da B3.
5. **Nenhuma ordem direcional de saída**, nem no prazo, nem no `EMERGENCY` — a saída é só o servidor fechando pelo
   colchete; prazo vencido é degradação com alerta, não zeragem.
6. **A trava da perda diária volta sozinha no pregão seguinte** depois de reconciliar (D8); no SPOT a retomada é
   sempre manual. Rejeições, inversão, comando e `EMERGENCY` continuam manuais.
7. **Releitura do kill switch a cada 2 s** (meta), no máximo 10 s (regra da casa).
8. **Com API e disco falhando juntos, o robô para de mexer em níveis** (§4.3) — diferença em relação à regra 5 do
   buffer no desenho §3.8 ("falha de disco nunca aborta nem atrasa uma saída"), que foi escrita quando a saída
   ainda podia ser ordem direcional. Falha **só** de disco, ou **só** da API, não atrasa nada além do orçamento de
   500 ms. Nada é retirado do servidor: a posição fica com o último `sl` confirmado. Motivo: sem isso, uma SLTP
   enviada sem registro some numa queda, e a instância seguinte pode desfazer um aperto ou atingir uma posição
   nova no mesmo símbolo (Astra R0a-2, rodada 2).

## 14. O que a sessão demo decide (e pode mandar código de volta)

T7 (onde vive o `sl` na Rico), T8 (`comment`, `magic`, `reason` preservados → `comment_preserved` e a atribuição),
T13 (níveis aceitos do colchete, tempo até zerar, rejeição/atraso de SLTP, parcial do stop, nenhuma exposição nova
e nenhum instante sem stop; e a SLTP atrasada com ticket de posição fechada contra uma posição nova no mesmo
símbolo → `stale_ticket_rejection_proven`), T14 (tipo e validade da ordem de entrada → `order_lifecycle_proven`), T9 (tabela de
retcodes da §3.6), T10/T15/T16 (reinício, exclusividade, autoridade, F19 combinado), T11 (relógio), T17 (avisos do
EA). Aceite: T1–T17 verdes em duas sessões de dias diferentes, uma na grade de 03/11 (ADR 0007). **Se o colchete
falhar, este contrato e o desenho voltam para revisão.**

## 15. Segunda opinião (Astra)

Revisão `R0a-risk-engine-b3` (`.claude/state/astra-review-R0a-risk-engine-b3.md`), pedida especificamente sobre
buracos da máquina de estados sob queda e reconexão. Síntese e decisões em
`obsidian/06-DECISIONS/Revisoes-Astra/R0a-risk-engine-b3.md`.

**Rodada 1 — 10 must-fix (1 CRITICAL, 9 HIGH), todos aceitos; a minha proposta de "reparo idêntico" foi
recusada por ela e retirada.**

| # | Achado (cenário dela) | O que mudou |
|---|---|---|
| R0a-1 | a reavaliação do `pre_send_gate` reprovava a própria entrada (check 11 vê a própria intenção; check 13 a conta como a operação do dia) | checks 11 e 13 excluem a própria `proposal_id`; F33; I-E-5 |
| R0a-2 (CRITICAL) | SLTP A só no buffer, processo morre, a nova lê `idle` da API e manda B antes de reenviar o buffer; A chega depois e afrouxa | gravar-antes-de-enviar (API, senão buffer) com orçamento; buffer entregue na fase 0, **antes** da concessão; herança `unknown` por registro, batimento ou `journal_lost`; F34, F35; I-SL-3, I-SL-5, I-A-5 |
| R0a-3 | P2 (nível igual ao pedido) cai se o Everton põe os mesmos níveis à mão; "reparo idêntico" cai com uma 3.ª modificação; P4 por declaração não é prova; `PLACED`/`DONE_PARTIAL` não concluem SLTP | P2 retirada; reparo idêntico recusado; P4 exige a linha do Diário; retcodes por ação × retcode; F36 |
| R0a-4 | `position_ticket` pode mudar (operação de serviço); P3 supunha que o ticket impede atingir posição nova no mesmo símbolo | `position_id` é a identidade, `position_ticket` o endereço, `request_position_ticket` gravado; P3 só com `stale_ticket_rejection_proven` (T13); senão P3′ bloqueia entradas no símbolo; F37, F38 |
| R0a-5 | piso e `stop_crossed_on_repair` exigiam coisas incompatíveis (colchete abaixo do piso); I-SL-2 usava a desigualdade de compra para os dois lados | `stop_crossed_on_repair` retirado; `floor_unplaceable` (nenhum envio, alerta, rota manual); D17 ao Everton; I-SL-2 pelos dois lados; F39 |
| R0a-6 | conta A → B → A: G1 voltava a passar | G0 com travas locais *latched* até reinício; leituras invalidadas na divergência; F7 |
| R0a-7 | F26 permitia gerir posição com atribuição de leitura anterior | atribuição sem cache; G7; F26 |
| R0a-8 | relógio do PC errado no instante da concessão estendia a autoridade | âncora no relógio da API (`server_now_utc`), contada do início do pedido, nunca renovada; mesmo para o claim; F41 |
| R0a-9 | reinício renovava o prazo do colchete, ou esquecia uma saída cujo gatilho sumiu | `exit_due_at` por gatilho, intenção de saída gravada antes da 1.ª SLTP, prazo original recuperado, saída iniciada só termina em `closed`; F40; I-X-3 |
| R0a-10 | relógio do PC que retrocede deixava o batimento morto parecendo vivo; `FILE_SHARE_READ\|WRITE` não permite `os.replace` | EA mede também `GetTickCount64` desde a última mudança de `(inst, seq)` e recusa carimbo no futuro; troca falha = atraso, nunca truncar; teste de colisão; F42 |

**Nice-to-have absorvidos:** claim idempotente devolve o mesmo resultado, não nova permissão (`send_consumed`);
resolução de `unknown` por ticket persistido; candidato = cadeia ordem + negócios; `partially_filled` na resolução;
`resolved_manual` descrito como decisão operacional, não prova; linhas novas na matriz (F33–F47).

**Rodada 2 — 8 dos 10 fechados; 2 parciais, os dois absorvidos.**

| # | Achado (cenário dela) | O que mudou |
|---|---|---|
| R0a-2 (CRITICAL, continua) | API não confirma, `fsync` falha sem estragar o buffer, a SLTP parte mesmo assim, o processo morre: buffer íntegro e sem a linha — a nova manda B; ou a posição já fechou e uma posição nova no mesmo símbolo fica exposta a A | **nenhuma SLTP sem gravação durável confirmada** (ack da API ou `fsync` com sucesso; "tentativa iniciada" não conta); época de gestão com linha `epoch_open` durável antes da 1.ª mutação; F48; I-SL-5; §13 item 8 |
| R0a-9 (HIGH, continua) | `EMERGENCY`, 1.ª SLTP rejeitada, nada gravado, morte, rearme: a nova não acha vestígio da saída | obrigação recuperada pelo histórico: transição durável de `EMERGENCY` dentro da vida da posição, mesmo rearmada; leitura incompleta → obrigação presumida e `exit_overdue`; F49; I-X-4 |

**Divergência registrada (de caminho, não de objetivo):** para R0a-2 ela propôs um marcador conservador de "época
possivelmente incompleta" com o envio seguindo sem registro. Eu escolhi o contrário — **não enviar sem registro
durável** — porque assim a completude fica provada por construção e uma queda comum (com registro íntegro) **não**
vira `unknown` em toda posição; o preço é pausar os níveis na falha dupla API + disco, com o `sl` confirmado no
servidor (§13 item 8). Usei a ideia dela de época para detectar buffer sumido (`epoch_open`).
**Nice-to-have da rodada 2 absorvidos:** `position_id`/`position_ticket` no `BrokerSnapshot` e no batimento;
`seq` agora decide (contradição removida); menor prazo entre gatilhos; D17 diz "tentar sair pelo colchete".

**Rodada 3 — R0a-9 fechado; R0a-2 fechado para a falha de gravação detectada; 2 pontos, os dois absorvidos como ela
escreveu.** (1) Perda de um sufixo de linhas **depois** de `fsync` confirmado não é detectada por `epoch_open` nem
pela cadeia de hash → declarada **fora do modelo suportado** (R-8), a opção (b) que ela mesma ofereceu; o texto
deixou de afirmar que esses mecanismos a detectam. (2) A §6.7 e a linha F6 ainda diziam que falha de disco "nunca
atrasa" a saída, o que autorizaria o envio sem registro → subordinadas à §4.3. Nice-to-have: mesmo `event_id` e
`sltp_request_id` na API e no buffer, replay nunca rebaixa resultado terminal; teste da pausa perto da zeragem.

**Rodada 4 — os dois pontos fechados; nenhum must-fix restante.** Nas palavras dela: "o contrato pode ser congelado
para R1/R2/R5/R7, dentro do modelo de falhas declarado" (`.claude/state/astra-review-R0a-risk-engine-b3-r4.md`).
O fechamento aprova o contrato como coordenação; **não** certifica a semântica da Rico (T7, T8, T9, T13, T14 decidem)
e não autoriza dinheiro real (ADR 0007 e as sessões demo).

## 16. Fontes

`docs/design/robo-b3-mt5.md` (commit `35b174cd`) e as fontes oficiais da MetaQuotes e da B3 listadas na §13
dele (lidas em 17/10/2026); `.claude/state/dialogue-robo-b3-mt5.md` (rodadas 1–6); `docs/RISK_ENGINE.md` v2.5;
`docs/RISK_ENGINE_MEME.md` v0.1; `docs/decisions/0007-robo-b3-mt5-excecao-live.md` (em redação na R0b);
`docs/plans/MERCADO-TRADICIONAL.md` §1.2–§1.5; `obsidian/11-KNOWLEDGE/Fila de Hipoteses.md` (H-038);
`obsidian/11-KNOWLEDGE/KB-0149-o-que-a-mesa-real-ensinou.md`; `obsidian/00-HOME.md`. A tabela de retcodes da §3.6
usa os nomes das constantes `TRADE_RETCODE_*` da documentação MQL5 ("Trade Server Return Codes"); a classificação é
candidata e só fica provada em T9/T13/T14.
