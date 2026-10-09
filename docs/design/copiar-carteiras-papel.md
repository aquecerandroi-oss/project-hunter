---
status: proposta (desenho + pré-registro; A/B/C em voo contra o contrato do orquestrador)
data: 2026-10-09
dono: quant-engineer
tipo: arquitetural (pista de papel nova no meme-worker; nenhum caminho para execução)
decisao: obsidian/06-DECISIONS/2026-10-09-piloto-copiar-carteiras-no-papel.md
pre_registro: obsidian/11-KNOWLEDGE/Fila de Hipoteses.md (bloco H-037)
experimento: obsidian/05-EXPERIMENTS/EXP-M28-copiar-carteiras-no-papel.md
dialogo_astra: obsidian/06-DECISIONS/Dialogos/copy-paper.md (transcrição .claude/state/dialogue-copy-paper.md)
contrato: packages/exchange-adapters/hunter_exchanges/pumpfun/leader_events.py
---

# Copiar ~20 carteiras no papel (H-037, EXP-M28)

> Pedido do Everton (09/10/2026): "acompanhar a compra e a venda dele e replicar". Aprovado só em papel.
> Adendos do mesmo dia: (1) até 4 traders escolhidos por ele (emenda 3; eram 5) entram no conjunto congelado, num estrato separado,
> e ele quer ver as compras e vendas de um líder enquanto acontecem; (2) **o caminho de compra é de
> milissegundos**: memória quente, nenhuma IO antes da decisão, carimbo em ms em cada passo.
> Este documento é desenho e pré-registro. As tarefas A, B e C (§9) já estão sendo escritas em paralelo contra o
> contrato `leader_events.py`. Onde o desenho pede mudança no contrato, está em §2.3.
> Rodada 1 da Astra: REQUEST_CHANGES com 8 must-fix (MF1–MF8). Todos estão absorvidos abaixo e marcados `[MFn]`.

## 0. O que a base já sabe, e o que isso muda aqui

| Nota | Achado | O que muda |
|---|---|---|
| KB-0136 (R57) | Os vencedores persistem (ρ ≈ 0,6), mas o lucro é velocidade e pacote. Copiar 3 s depois dá 1,01×; 20 s depois, 0,96×; o R empata com o controle. A única fresta foi segurar 15 min sem stop | A previsão honesta é **NÃO CONFIRMA ou REFUTA**. A saída espelha o líder, com stop largo e teto de 60 min; não o trailing de 10 % da mesa |
| KB-0142 (R61) | O selo KOL chega no pico; comprar 20 s depois dá R −0,071 | Seguidores e selo **não** entram na escolha. Viram pergunta secundária (decisão 2026-10-05) |
| KB-0182 | O que importa é o PnL **de quem copia**. Do slot do gatilho ao nosso pouso: p50 3,5 / p75 5 / p90 12,3 slots (62 compras). Da proposta à confirmação: p50 1,65 s / p90 3,9 s (143 compras) | **Cenário nominal** de execução: 1,65 s. Estresse: 3,9 s (§3.3). Não é um limite demonstrado para esta pista |
| KB-0185 | O `/pnl-leaderboard` tem 6 visões de 100 linhas (300 carteiras distintas). É vivo e curado; no daily combined, 77 % é marcação. Nada ali é ponto no tempo | O quadro só serve para escolher **quem observar daqui para a frente**, com `known_at`. A escolha usa o realizado |
| KB-0186 | O canal `account_balance_change.<carteira>.*` entregou 415/415 e 1 315/1 317 pernas esperadas de 20 carteiras, sem conferir todas as pernas SOL/token. Chega ~0,47 s depois da NATS `processed` e ~0,32 s depois do `logsSubscribe`. É saldo, não swap | A NATS é a fonte primária, com fallback on-chain obrigatório. Lado e valor saem do par de pernas, e só com evidência suficiente (§2.1) |
| KB-0183, KB-0187 | O programa inteiro gera 28–31 M eventos/dia; uma pool chegou a 124 mil eventos/h | Não coletamos o programa inteiro. Só as ≤ 24 carteiras e os mints que copiamos |
| KB-0149 §1, §4, §5 | Custo é o inimigo. A infra é estratégia. Look-ahead mente com convicção. Ligar critério novo na mesa real não é sombra | Custos do motor de papel declarados no conjunto, lacunas explícitas, braço `research_only` |
| EXP-M15 / H-030 | O desenho completo (fita, entidades, C-PnL) segue em paralelo | Este piloto é o **atalho**, com política própria (§3.5) e linhagem declarada (§6) |

## 1. Escolha das carteiras, congelada antes de T0 (tarefa B, `infra/scripts/copy_select_leaders.py`)

> **Emenda 3 do H-037 (09/10/2026 05:24Z), decisão do orquestrador.** A regra vigente é a `copy-leaders-rule/1`,
> implementada e revisada na tarefa B. A regra que esta seção trazia antes (realizado ≥ 10 SOL, ordem por SOL/dia,
> `/user-trades` paginado até 7 dias, veto `top-holders-v2`, até 5 do Everton) **saiu antes de rodar**.
>
> - **Por que saiu:** ela pedia ~600 requisições à pump.fun. A regra enxuta faz ≤ 30, o que é menos carga sob o
>   risco de termos aceito em 06/10, além de ser mais simples e revisável.
> - **O que se perde, declarado:** não há detecção verificada de robô, sniper, pacote ou criador, nem filtro de
>   posse mínima.
>
> A revisão da regra está em `obsidian/06-DECISIONS/Revisoes-Astra/copy-leader-selection.md`.

**A regra (`copy-leaders-rule/1`).** O texto integral está em `infra/scripts/copy_leaders_rule.py`, com sha256
`d0460e856adc5101d415d8aef652de9c5dda09803d2af7c5f6025f6ffa85e18c`, e é impresso em cada execução.

1. **Universo:** as 6 visões do `/pnl-leaderboard` (daily, weekly e monthly × `combined` e `realized`), 100 linhas
   cada. Endereço que não é Solana sai.
2. **Persistência:** a carteira aparece em ≥ 2 **períodos** distintos (`combined` e `realized` do mesmo período
   contam como um).
3. **Linha de referência:** a do período mais longo em que a carteira aparece, na visão `combined` se ela existir.
4. **Realizado:** `realizedPnlSol > 0` em **todas** as linhas da carteira.
5. **Marcação:** `buySpendSol > 0` e realizado / (realizado + max(não realizado, 0)) ≥ 0,5.
6. **Saldo:** realizado + não realizado > 0 na linha de referência.
7. **Massa:** `positionsCount ≥ 10` na linha de referência.
8. **Ordem:** pela média das posições nos três quadros `realized`, com ausente = 101, desempate pelo endereço. Ficam
   as 20 primeiras; se passarem menos, ficam menos.
9. `isVerified` e seguidores são descritivos. Seguidor não lido é desconhecido, nunca 0.
10. **`--include`, até 4,** no estrato `escolha_everton`, sem os filtros. Uma carteira que a regra também escolheria
    fica em `regra` com `everton_pick = true` e não cria vaga extra.
11. **Quadro completo:** 100 linhas legíveis em cada visão, nenhuma malformada. Quadro incompleto, parada
    (401/403/429) ou orçamento esgotado → nenhuma seleção.

**Orçamento:** ≤ 30 requisições anônimas, sendo 6 quadros + ≤ 24 leituras de `/users` para os seguidores.

**Rastreabilidade da regra:**

| Item | Detalhe |
|---|---|
| Hashes | A primeira versão do texto (`f56b5742186ef33a3329b12d98a53c91477dcedf4df0d895a44a1b627c353d17`) mudou uma vez, depois do primeiro dry-run, só nos itens 10–11, para a vigente `d0460e85…85e18c` |
| Dry-runs | Dois `--dry-run` reais, às 04:47Z e às 05:13Z de 09/10, com 26 requisições cada, todas HTTP 200. Eles têm 17 de 20 carteiras em comum (o quadro é vivo) |
| O que foi visto | Listas, não retornos. **Nada foi gravado**, e a regra não foi mexida por causa da composição |
| Execução definitiva | É a **próxima que grava**, qualquer que seja a composição |

**T0.** T0 vem **depois** da gravação do JSON e do início efetivo da pista (§5). O `t0_not_before` do JSON é só um
limite inferior.

**JSON congelado (`copy-leaders/1`).** O formato está na revisão `copy-leader-selection`. Ele vira o `params.leaders`
de `copy_v0/1` (estrato `regra`) e de `copy_everton_v0/1` (estrato `escolha_everton`) na semente (tarefa E).

Se passarem menos de **10** carteiras na regra, o experimento **não nasce**, e isso fica registrado. Limiar não se
afrouxa.

## 2. Acompanhamento (tarefa A, `hunter_exchanges.pumpfun.leader_source_*`)

### 2.1 Fonte primária: NATS por carteira

A fonte é `account_balance_change.<carteira>.*` na instância CORE (`prod-v2`). Nas amostras do KB-0186, cada
mensagem traz a mudança de saldo de **um** ativo (SOL ou um token), com `slot`, `txSignature` e carimbo do servidor
em ms. A tabela mostra de onde sai cada campo:

| Campo | Origem |
|---|---|
| `wallet`, `signature`, `slot` | a própria mensagem |
| `mint`, `token_delta_atoms`, `position_after_atoms` | a perna do token |
| `sol_delta_lamports` | a perna de SOL da mesma assinatura. Inclui rede e aluguel: é o que a carteira gastou, não o preço do swap. Fica **desconhecido** (`None`) se a perna não chegar |
| `side` | o sinal do delta do token |
| `server_ts` | o carimbo do servidor (ms). **Não** substitui o `block_time` |
| `block_time` | só o da cadeia, vindo da confirmação; `None` até lá |
| `first_seen_at` | **nosso** relógio, em ms, ao acordar do `recv` da primeira perna, antes de parsear |
| `fields_complete_at` | quando as pernas necessárias ficaram disponíveis (o instante em que a decisão pôde ser tomada) |

**Emparelhamento em memória** `[MF3]`. A chave é (carteira, assinatura, mint), com espera máxima de **300 ms**
depois da primeira perna. Uma transação com vários tokens **não** atribui o mesmo débito de SOL integral a cada
token: o evento leva `multi_mint = true` e `sol_delta_lamports = None`. Token que sobe com SOL que desce **não prova**
swap (pode ser transferência recebida com taxa paga ou fechamento de ATA). Por isso a evidência mínima para uma
**entrada provisória** é: token subiu, SOL desceu ≥ 0,1 SOL na mesma assinatura e a transação não é `multi_mint`.
Perna ausente ou ambígua nunca vira zero e nunca abre cópia.

### 2.2 Fallback e confirmação

**Fallback obrigatório.** É um `logsSubscribe` (`mentions` = a carteira) no RPC pago que já usamos, uma assinatura
por carteira. Qualquer destes casos gera um `LeaderGap(wallet, start, None, reason)` imediato e a troca para o
fallback:

- credencial trocada;
- recusa do servidor;
- socket caído;
- silêncio maior que 60 s numa carteira cuja última hora teve atividade.

Nunca para em silêncio. Reconectar não recompõe o passado: a lacuna fica.

**Confirmação assíncrona, fora do caminho quente.** Cada assinatura é lida com `getTransaction`
(`maxSupportedTransactionVersion = 1`, KB-0184 item 5) e decodificada pelos decodificadores existentes
(`program_logs.py`, `swap_record.py`). O resultado é um `LeaderConfirmation` com um de cinco estados:

| Estado | Quando |
|---|---|
| `confirmed` | carteira, mint, lado, quantidade e slot batem com o evento |
| `divergent` | algum desses campos não bate |
| `failed_tx` | a transação falhou na cadeia |
| `not_found` | ainda não encontrada; até **3 tentativas em 30 s**. Um `null` momentâneo não prova nada |
| `rpc_error` | o RPC não respondeu (motivo registrado) |

Confirmação repetida da mesma assinatura é idempotente: não reaplica delta nem abre outra cópia. A confirmação
também devolve as reservas logo depois do trade do líder, que alimentam o preço "ideal" (§3.3). Se não vierem, esse
preço fica ausente.

**Credencial** (decisão de 06/10):

- lida em tempo de execução dos props da home pública;
- mantida só em memória e mascarada em `repr`;
- nunca em log, heartbeat, `reasons`, exceção, arquivo, nota ou `.env`;
- nunca `/nats/token`, nunca login.

Revisão obrigatória do security-reviewer (R1).

**Volume.** Só as carteiras de `params.leaders` (≤ 24: 20 da regra + até 4 do Everton). O servidor aceitou 20 na sonda; o limite real é desconhecido.
Recusa por limite vira lacuna + fallback para as excedentes.

### 2.3 Emenda pedida ao contrato `leader_events.py` (antes de fechar A e C) `[MF3]`

1. **Decidir no primeiro sinal confiável.** Hoje o docstring proíbe agir com `confirmed=False`. A emenda permite
   abrir e fechar no evento provisório com a evidência de §2.1, e acrescenta `LeaderConfirmation(signature, wallet,
   mint, status, reason, confirmed_at, block_time, post_reserves | None)` ao `stream`, que passa a produzir
   `LeaderEvent | LeaderGap | LeaderConfirmation`.
2. **Carimbos separados no `LeaderEvent`:** `first_seen_at`, `fields_complete_at` e `server_ts`. O `observed_at`
   atual vira `first_seen_at`, e `block_time` fica só com o da cadeia.
3. **Campos opcionais:** `sol_delta_lamports: int | None` e `multi_mint: bool`.
4. **Transferência:** quando a fonte souber distinguir (saída de token sem entrada de SOL), marca
   `kind = 'transfer'`. Para a saída (§3.4) vale a posição, seja qual for a causa.
5. **Semântica, para o aceite de 0b, A e C** `[R2 item 3]`:
   - `multi_mint = false` quer dizer "nenhum outro mint conhecido neste instante", não prova de ausência.
   - Uma perna que chega depois da decisão só atualiza o diagnóstico. Ela nunca reescreve a evidência original nem
     gera uma segunda compra.
   - A **saída** precisa só da posição observada; o piso de 0,1 SOL é evidência de entrada, não de saída.
   - `confirmed_at` é o instante local em que recebemos o resultado da confirmação, inclusive do timeout. Não é o
     horário do bloco.
   - `not_found` esgotado dispara a liquidação por prazo e fica registrado à parte de `failed_tx`. Ele não afirma
     que a transação era falsa.

## 3. Regra de cópia (tarefa C, `copy_lane.py` + `copy_wiring.py` no meme-worker)

### 3.1 Caminho quente (milissegundos)

Tudo o que a decisão lê está em memória:

- os líderes e seus estratos;
- os parâmetros do conjunto;
- as chaves (estrato, mint) já consumidas;
- a contagem do dia por líder;
- o (líder, mint) já visto desde T0;
- a posição e o pico do líder em cada cópia aberta.

Esse estado é reconstruído na partida, **antes** de assinar a fonte (§4.1). A decisão não faz IO. A proposta, a
assinatura do mint e a leitura de preço vêm depois dela. Os carimbos são em ms e UTC:

| Carimbo | Instante |
|---|---|
| `leader_block_time` | o bloco do líder, na cadeia |
| `server_ts` | o carimbo do servidor da NATS |
| `first_seen_at` | nossa primeira perna recebida |
| `fields_complete_at` | as pernas necessárias disponíveis |
| `decided_at` | a decisão tomada |
| `priced_at` e `priced_slot` | o instante de observação e o slot do estado usado no preço |
| `confirmed_at` | a recepção local do resultado da confirmação, inclusive do timeout (não o horário do bloco) |

**Honestidade sobre a latência.** O nosso processamento pode ser de milissegundos, mas a cadeia anda em slots
(≈ 268 ms hoje, KB-0183 §8.6). Uma cópia **pousa no mínimo um slot depois do líder** e, no cenário nominal, ~6 slots
depois da decisão. Milissegundo no caminho quente não compra o slot do líder.

### 3.2 Entrada

Uma cópia nasce quando chega um evento `buy` de um líder com a evidência de §2.1 e valem todas as condições:

1. `fields_complete_at ≥ T0`.
2. **Primeira compra:** a posição antes do evento (`position_after_atoms − token_delta_atoms`) é 0, e nenhum `buy`
   desse líder nesse mint foi registrado desde T0. Isso vale para qualquer compra, inclusive as que não viraram
   cópia (§4.1).
3. `−sol_delta_lamports ≥ 0,1 SOL`, o piso de gatilho do H-030.
4. A chave (estrato, mint) não foi consumida. Uma tentativa admitida consome a chave mesmo que termine `unfilled`.
   A ordem é a de **chegada**, nunca reorganizada pelo slot confirmado. O primeiro líder fica com o mint; compras
   posteriores de outros líderes do mesmo estrato viram registro `co_compra`.
5. O líder tem < 20 tentativas admitidas no dia UTC, o teto do H-030 (as 20 primeiras, por regra causal).
6. O conjunto do estrato tem < **100** vagas ocupadas, contando as cópias abertas **mais** as tentativas que ainda
   esperam preço. A vaga é reservada na admissão, de forma atômica em memória, e liberada no `unfilled` ou no
   fechamento. Acima disso a tentativa termina `unfilled/teto_aberto`, contada `[R2-4]`.
7. Não há lacuna aberta da fonte desse líder.

O estimando é a **primeira oportunidade observável de cada mint por estrato**. Ele não mede todas as compras dos
líderes nem cada líder isolado, e favorece quem chega primeiro. Isso fica declarado.

### 3.3 Preço da entrada `[MF4]`

**Latência de execução.** O cenário nominal é `exec_latency_s = 1,65`, a mediana proposta → confirmação de outra
amostra (143 compras reais, KB-0182). **Não** é limite demonstrado da decisão → pouso desta pista. O estresse usa
3,9 s, o p90 da mesma amostra.

**Seletor de estado próprio da cópia.** Não serve o `pick_fill_snapshot` do Lab, que escolhe só por
`observed_at > decided_at`. O estado elegível é o **primeiro** que satisfaz as três condições:

- foi observado em ou depois de `decided_at + exec_latency_s`;
- `context slot ≥ slot do líder + 1`;
- veio com compromisso `confirmed`.

A fonte do estado é a assinatura por mint aberta na decisão (`accountSubscribe` da PDA da curva, como na pista de
lançamento) ou uma leitura pontual com `minContextSlot = slot do líder + 1` feita nesse instante, o que chegar
primeiro. Desempate: o de menor `observed_at`, depois o de maior slot. Uma resposta de slot anterior ao do líder é
descartada.

**Prazo do fill: 30 s.** Sem estado elegível até lá, a tentativa termina `unfilled/sem_estado` e consome a chave.

**Aritmética.** A do motor de papel: `paper_fill.evaluate_fill` sobre um `Snapshot` montado do estado eleito, e
`hunter_indicators.meme.curve`. Isso inclui o teto de SOL real com o custo da própria compra na curva
(`Snapshot.sell_cap_sol` + `BetState.curve_cost_sol`, conserto do R89 de 07/10) para moedas Mayhem. A prioridade
entra uma vez em cada perna (`paper_fill.py:174`, `paper_engine.py:233`); o relatório **não** soma custo de novo.

**Praças, congeladas em `params.venues`.**

- **Curva da pump.fun:** sempre.
- **Pool da PumpSwap:** só se, antes de T0, passar o aceite próprio: entrada por reservas da pool com a reserva
  virtual (KB-0184 item 3), migração durante a posse, taxas e ATA contados uma vez, contra fixtures reais.
  `pool_mark.py` vende pela fita e não é compra por reservas. Sem esse aceite, `venues = ["curve"]` e os mints da
  pool viram `unfilled/fora_de_praca`, contados.
- **Qualquer outro mint:** `unfilled/fora_de_praca`. A conclusão vale só para as praças de `params.venues`.

**Sensibilidade de latência (não decide).** O mesmo processo grava dois preços de entrada a mais:

- **`ideal`:** as reservas logo depois do trade do líder, vindas da confirmação. É o limite de quem copiasse no
  mesmo slot, e é inalcançável. Se as reservas não vierem, fica ausente; nunca é inventado.
- **`p90`:** o primeiro estado elegível em ou depois de `decided_at + 3,9 s`.

Na saída grava-se o mesmo par. O desfecho em cada latência usa os instantes de intenção da política primária: é uma
sensibilidade **condicionada** à primária, não a execução de uma política de 3,9 s, cujo stop dispararia em outro
instante. Isso fica declarado.

### 3.4 Saída

A primeira das três:

1. **O líder reduziu a posição:** o `position_after_atoms` dele cai a ≤ 50 % do **pico** da posição nesse mint
   desde o gatilho (recompras posteriores contam no pico) ou chega a 0. A intenção nasce no `fields_complete_at` do
   evento. Uma transferência também dispara, com o rótulo `leader_transfer`. Medimos "o líder reduziu a posição", não
   "o líder vendeu".
2. **Stop de segurança:** a marca ≤ **50 %** do `sol_spent`, checada em cada estado observado do mint. A marca é o
   que uma venda total renderia agora, taxas e teto de SOL real incluídos.
3. **Teto de tempo:** 3 600 s depois de `entry_at`.

**Venda** `[R2-2]`. O estado precisa ser observado em ou depois de `intenção + 1,65 s`, com compromisso `confirmed`,
e respeitar um **piso de slot** que depende do gatilho da saída:

| Gatilho | Piso de slot |
|---|---|
| Evento do líder (redução ou transferência) | > o slot do evento que disparou |
| Stop | > o slot do estado cuja marca disparou |
| Teto de tempo ou invalidação | > o slot do último estado aceito pela cópia |

Em todos os casos vale também **a regra de não regressão**: o slot nunca fica abaixo do último estado aceito da
cópia. A leitura pontual de resgate usa `minContextSlot` igual a esse piso e obedece aos mesmos cortes; ela não
escolhe "a primeira foto depois da marca antiga" (`lab_point_read.py:77`). O prazo total é de 60 s, resgate incluído.
Sem estado no prazo, a cópia termina `indeterminate` com `outcome_quality`; nunca é preço inventado.

**Suporte das sensibilidades.** Se a entrada `p90` só puder ser observada depois da intenção de saída primária, a
réplica `p90` daquela cópia fica **indisponível por ordem causal**: não vira uma venda anterior à compra. O `ideal`
na saída só existe quando a saída veio de um evento do líder com reservas confirmadas; para stop e teto de tempo
ele fica indisponível.

**Ordem causal.** Uma ordem enviada não se cancela. Se o líder reduzir antes do nosso fill, a compra pousa assim
mesmo, e a intenção de saída nasce em max(intenção, `entry_at`). Nunca vendemos tokens que ainda não temos.

**Migração da curva durante a posse.** Segue na pool pelo caminho existente (`holds_through_migration`) só se a
PumpSwap estiver em `params.venues`. Senão, a cópia é censurada como `indeterminate/migrou_fora_de_praca`.

**Invalidação** `[MF2]`. Se a confirmação de um evento usado pela cópia volta `divergent`, `failed_tx` ou
`not_found` esgotado:

- **Cópia aberta:** a intenção de saída `invalidated` nasce no `confirmed_at`, e a venda é precificada pelo mesmo
  seletor. A cópia **fica no primário** com o resultado econômico que tiver: a política rápida assumiu esse risco.
- **Cópia fechada:** a invalidação só acrescenta diagnóstico.

**Desfecho.** `r = pnl_sol ÷ entry.sol_spent`, publicado separado do R do H-030.

**Custos do primário, congelados em `params`:** `fee_pct = 1.25` por perna (a taxa da curva usada pelo `absorb_v0/2`,
R62/R64) e `priority_fee_sol = 0.00005` por perna (≈ 50 000 lamports de rede). O aluguel da conta de token é
considerado recuperado, porque a ATA fecha na venda (KB-0149 §6 item 1).

**Sensibilidades:** `fee_pct = 1.75`, e aluguel perdido de 0,00203928 SOL por cópia, o mínimo isento de uma conta de
token, valor que aparece nas fixtures do repositório.

### 3.5 Política própria, parâmetros compartilhados com o H-030 `[Astra item 4]`

O motor do H-030 (`policy.simulate_copy`) é um replay sobre a fita inteira do mint, com outro contrato de preço (o
pior preço do slot). Aqui:

- **Parâmetros compartilhados, por lista explícita:** ficha 0,05 SOL, piso de gatilho 0,1 SOL, stop 0,5, teto de
  3 600 s, 20 por líder/dia. Um teste de C prova a igualdade **só desta lista** contra `FollowPolicy` v1. Não são
  compartilhados: `delay_slots`, `decision_seconds`, `slot_seconds`, `mint_cooldown_seconds`, `r_unit`,
  `network_leg_lamports` e `ata_close_lamports`.
- **Contagem do líder diferente, declarada.** No H-030 a saída é "vendeu **mais** da metade do que comprou, em
  ordem de chegada". Aqui é "a posição caiu a ≤ 50 % do pico, ou a 0".
  - Contraexemplo sintético: compra 100, vende 40, recompra 40, vende 31. O H-030 sai (71/140 > 50 %); o H-037 não
    sai (69 de pico 100).
  - Transferência e empate exato também separam as duas.
  - O teste diferencial de C verifica essas **divergências esperadas**, não igualdade.
- **Preço:** o do motor de papel. Um CONFIRMA aqui não valida o C-PnL do H-030, e vice-versa.

### 3.6 Onde mora e quem é dono de cada linha `[MF7]`

A pista mora no **meme-worker**, ao lado da pista de lançamento, cujo módulo `launch_lane_*` é o molde. O modo vem de
`MEME_COPY_LANE=off|paper`. Não existe `on`, nem existirá neste desenho.

São **dois conjuntos** em `meme_rule_sets`, **um por estrato** `[R2-3, R2-4; emenda 1 do H-037]`, ambos com
`kind = research_only`, `exp_ref = EXP-M28`, `params.clock = 'copy'` e os mesmos parâmetros:

| Conjunto | Estrato | Papel |
|---|---|---|
| `copy_v0/1` | `regra` | o único na população do H-037 |
| `copy_everton_v0/1` | `escolha_everton` | só descritivo |

**Recursos separados.** A pista carrega todos os conjuntos `clock = 'copy'` ativos. Cada um tem a sua capacidade, a
sua fila de preço e de confirmação e o seu orçamento de RPC. O `regra` tem **prioridade protegida**: quando falta
recurso, a carga do `copy_everton` é descartada com `unfilled/sobrecarga`, nunca o contrário. O teste E2E repete o
mesmo fluxo do `regra` com e sem o `copy_everton` saturado e prova que as admissões e os prazos do `regra` não mudam.

**Um único dono.** A pista de cópia é a dona exclusiva de fill, marca e saída das linhas de `copy_v0/1`. O Lab de
15 s e de minuto, hoje, lê **toda** proposta `approved` (`lab_repo.py:120`) e toda aposta `open`
(`lab_repo_bets.py:107`). Ele marcaria `unfilled/rule_set_inactive` uma proposta da cópia (`lab_bets.py:101–106`), ou
venderia uma cópia na foto seguinte sem a latência dela (`lab_bets.py:228`). Por isso:

- **Tarefa I:** as consultas do Lab (`_LOAD`, `_APPROVED`, `_OPEN_BETS`, a pista de pool e o resgate pontual)
  passam a excluir `params->>'clock' = 'copy'`, com teste de coexistência. A mesma tarefa confere se as apostas do
  `launch_v0/*` (`clock = 'event'`) já estão protegidas em `_APPROVED`/`_OPEN_BETS`. A exclusão em `lab_repo.py:51`
  vale só para o `_LOAD`, e isto **não foi verificado em produção**.
- **Nascimento atômico** `[MF6]`. A proposta da cópia nasce, numa transação, já `approved` com `mode = 'paper'` e
  `decided_by = 'rules:copy'`, e vira `filled` ou `unfilled` quando o preço se resolve. Ela **nunca** existe como
  `proposed`, então `decide_proposal` (`approval.py:57`, `WHERE status = 'proposed'`) não pode promovê-la a `live`.

**Nenhuma tabela nova.**

## 4. Armazenamento, recuperação e observabilidade

### 4.1 Banco (reuso) e reinício `[MF5]`

**Funil durável em `meme_proposals`** `[R2-3]`. O fato de elegibilidade é a **primeira observação de aumento de
saldo do token** do par (líder, mint) desde T0. Vale qualquer evidência: compra com SOL conhecido ou desconhecido,
poeira abaixo do piso, `multi_mint` ou transferência recebida. Esse fato vira **uma** linha por par e por conjunto,
mesmo quando não admitida, com `origin = rules` e `features_end_time = fields_complete_at` na resolução real do
relógio (µs no Linux da VPS; nada é inventado). O `reasons` leva líder, estrato, assinatura, slot, evidência e os
carimbos. Observações posteriores do mesmo par não geram linha, porque já não podem ser "a primeira". A única exceção à regra "uma linha por par" é a `co_observacao` abaixo.

**Duas regras de identidade:**

- A mesma assinatura vista pela NATS e pelo fallback é deduplicada em memória por (assinatura, carteira, mint) antes
  de qualquer escrita. A primeira a chegar vale.
- O índice `UNIQUE (rule_set_id, mint, features_end_time)` não contém líder nem assinatura
  (`infra/migrations/ddl/meme_lab.py:231`). Ele só colide entre líderes diferentes no mesmo mint, no mesmo conjunto
  e no mesmo µs. **"Par já observado" e "mint consumido por admissão" são fatos distintos**, e a colisão preserva
  os dois `[R3]`:
  - o fato do segundo líder é **acrescentado** ao `reasons` da linha existente, como entrada
    `{"co_observacao": {leader, signature, slot, evidence, fields_complete_at}}`. A decisão da linha existente não
    é tocada;
  - a reconstrução na partida lê também essas entradas, então o par (segundo líder, mint) continua marcado como
    observado depois de um reinício;
  - se o segundo líder seria admitido (mint ainda não consumido), ele **não** é admitido, porque não há linha
    própria onde registrar a tentativa. O resultado é `colisao_nao_admitida`, contado: falha fechada. O mint
    continua livre para um líder posterior;
  - se a escrita no `reasons` também falhar, a pista entra em lacuna global (`copy_leader:*`, motivo
    `funil_indisponivel`) e para de admitir até a escrita voltar.

  Aceite de C/E2E, com os três casos e o reinício:

  | Caso | O que precisa valer depois do reinício |
  |---|---|
  | Dois líderes recusados, mesmo carimbo | a recompra de B continua recusada como `nao_primeira` |
  | Primeiro recusado, segundo elegível | B termina `colisao_nao_admitida`, e nenhum fato se perde |
  | Primeiro admitido, segundo colidente | o consumo do mint sobrevive |

  A duplicata da mesma assinatura pela NATS e pelo fallback continua idempotente.

O status de cada linha depende do que aconteceu:

| Caso | Status | Detalhe |
|---|---|---|
| Admitida | `approved` (paper), depois `filled` ou `unfilled` | — |
| Não admitida | `rejected`, nascida decidida | `decision.reason` ∈ {`nao_primeira`, `abaixo_do_piso`, `ja_copiado`/`co_compra`, `teto_dia`, `lacuna`, `multi_mint`, `evidencia_insuficiente`} |

Volume: ≤ alguns milhares de linhas por dia.

**Na partida**, antes de assinar a fonte, a pista reconstrói desse funil:

- as chaves consumidas;
- as contagens do dia;
- o (líder, mint) já visto.

**Posição e pico do líder nas cópias abertas.** Cada mudança vai para o hash Redis `copy:pos:<bet_id>`. Na partida, o
saldo atual de (líder, mint) é lido na cadeia (`getTokenAccountsByOwner`), e o pico vira max(o guardado, o atual). Se
o Redis tiver perdido o hash, o pico vira max(a posição do gatilho, a atual), e a cópia é marcada
`contaminated: restart`. Saldo desconhecido nunca vira zero.

**Queda entre a decisão e a escrita.** A decisão perdida não é reconstruída com informação posterior. O intervalo vira
lacuna, e as compras desse intervalo nunca viram cópia.

**Depois de uma lacuna do líder.** Durante a lacuna, o líder pode ter comprado e zerado um mint inteiro; nesse caso
a próxima compra parte de saldo zero e pareceria "a primeira", e ler o saldo atual não prova o contrário. Por isso,
antes de voltar a admitir esse líder, a pista recompõe os pares vistos na lacuna pelo histórico da carteira na
cadeia: `getSignaturesForAddress` paginado até o início da lacuna, mais `getTransaction`, com teto de **1 000
assinaturas** por lacuna. Os fatos recompostos vão para o funil (`rejected/visto_na_lacuna`) e nunca viram cópia.

Sem recomposição completa (teto atingido ou RPC falhando), o líder fica **sem novas entradas até o fim da coorte**,
contado no heartbeat e no portão de cobertura: falha fechada. As cópias que já estavam abertas seguem marcadas
`contaminated`.

**Cópia** em `meme_paper_bets` (`mode = 'paper'`). Ela guarda:

- os carimbos e as latências;
- os preços de sensibilidade;
- o evento do líder que disparou a saída, com o valor dele;
- o estado da confirmação;
- `contaminated` e o motivo.

**Lacunas** em `meme_ingest_gaps`, com `stream = 'copy_leader:<carteira>'` ou `'copy_leader:*'` e o motivo e a fonte
em `detail`. Uma cópia cujo intervalo [decisão, venda] cruza lacuna do líder fica `contaminated`.

### 4.2 Vista ao vivo e heartbeat

**Stream Redis por líder** `copy:leader:<carteira>` (`MAXLEN ~500`). Cada `buy`/`sell` visto entra com mint, lado,
quantidade, SOL, slot, carimbos, fonte e confirmação, mais o que a pista fez com ele (o status do funil, ou
`saida_disparada`). É **só** para a vista. A elegibilidade vem do funil no banco, nunca deste stream.

**Heartbeat `hb:meme:copy`.** Strings; ausente é `""`, nunca 0. Campos:

- modo, T0 e o sha256 dos líderes;
- fonte ativa por líder (`nats`, `chain` ou `gap`) e a idade do último evento;
- lacunas abertas e totais;
- compras e vendas vistas;
- tentativas por status do funil;
- cópias abertas, fechadas, invalidadas e `contaminated`;
- confirmações pendentes por estado;
- p50 e p95 de cada intervalo: `first_seen_at − leader_block_time`, `fields_complete_at − first_seen_at`,
  `decided_at − fields_complete_at` (o caminho quente, em ms) e `priced_at − decided_at`.

**Vista por líder para o Everton** (`infra/scripts/copy_leader_view.py --leader <carteira> [--follow]`). Mostra, em
ordem, as compras e vendas do líder, as nossas entradas e saídas com motivo, a latência de cada passo e as cópias
abertas. Ver não viola o protocolo: líderes e parâmetros não mudam depois de T0, e mudar encerra as entradas da
coorte (§5). Os agentes da leitura única não leem `pnl_sol` antes da parada.

**Diário:** uma linha por dia com contagens, cobertura e latências, sem PnL.

## 5. Pré-registro (resumo; o texto decisório está no bloco H-037 da Fila)

**T0** `[MF8]`. A semente do conjunto **não** inicia o experimento. T0 é o primeiro instante em que a pista, em
`paper`, com o estado reconstruído e a fonte ligada para todos os líderes, passa a aceitar eventos. A pista grava esse
instante como o **fim** da lacuna inicial `copy_leader:*`, escrita nesse instante com início no `created_at` do conjunto (o CHECK `gap_end > gap_start` de `meme_ingest_gaps` exige as duas pontas) e motivo
`lane_not_started`. É durável e conferível.

| Item | Definição |
|---|---|
| População (F) | cópias preenchidas de `copy_v0/1` com `decided_at ∈ [T0, T0 + 28 d)`, inclusive as invalidadas depois |
| Conjuntos `[R2-1]` | **M** e **U** particionam F, uma linha por `bet_id`. **M** (primário): fechadas, medidas e não contaminadas. **U** = F ∖ M. S1 e S2 reutilizam as mesmas identidades. **S1** = F com r = −1 em U. **S2** = F com U no percentil 90 de M. O portão bloqueia o veredito se \|U\|/\|F\| > 10 %. **REFUTA** vale para as cópias medidas e exige o limite superior < MRE em M **e** em S2. **CONFIRMA** exige M e S1 |
| Interrupção `[R2-5]` | qualquer mudança no conjunto ou aborto antes de 28 d → NÃO CONFIRMA ("coorte interrompida"), só descrição |
| Régua editorial `[R2-5]` | 28 d < 30 d distintos: o `result` da EXP-M28 fica `inconclusivo` qualquer que seja o rótulo da Fila; um CONFIRMA só abre réplica. Estender para 30 d é decisão do Everton, antes de T0 |
| Unidade e clusters | a cópia; clusters por líder e por dia UTC |
| Primário | média de `r` em M |
| Co-primário descritivo | a probabilidade de lucro, sem caminho próprio para CONFIRMA |
| Parada | horizonte fixo: entradas até T0 + 28 d; prazo de maturação T0 + 28 d + 2 h (o que estiver aberto ou pendente nesse instante vai para U) |
| Leitura | única |
| Secundárias | por líder, por faixa de seguidores, imposto de latência (`ideal`, nominal, `p90`), distribuições de latência, `escolha_everton`, mix de saídas, funil |

## 6. Família e caminhos bifurcados

É a **8.ª** tentativa da família "quem está comprando": R57, R61, E2-b, H-010, H-014, H-015 e H-030 (este em curso).
As priores contra são fortes: no KB-0136 os vencedores persistem, mas seguir não é gatilho; no KB-0142 o KOL
confirma, não antecipa.

O que é novo e justifica gastar dado: a saída espelhada no líder, a NATS por carteira com o nosso atraso medido e a
escolha pública congelada.

Os limiares são congelados antes de T0, e mudar qualquer um exige id novo em dado novo. O estudo é um teste
prospectivo da rentabilidade **hipotética** da regra congelada. Sem controle, ele **não** atribui um eventual lucro à
seleção dos líderes. O H-030 não é afetado.

## 7. O que o advogado-de-jesus vai atacar

| Ataque | Guarda |
|---|---|
| Sobrevivência ou quadro com futuro | Escolha numa leitura antes de T0, com `known_at`. O desfecho é só das nossas cópias depois de T0, inclusive as de líderes que quebrarem |
| Gêmeas e sobreposição | Uma cópia por (estrato, mint); cluster por líder; resultado sem o melhor líder; média igual por líder publicada |
| Poucos clusters (≈ 20 líderes) | Duas vias com t de G−1 e bootstrap selvagem (Webb); limite de dado; potência declarada |
| Latência otimista | 1,65 s nominal; slot ≥ líder + 1; estresse a 3,9 s publicado; caminho quente medido, não suposto |
| Custo irreal | `fee_pct` e prioridade congelados; teto Mayhem; sensibilidades de taxa e de aluguel |
| NATS falsa ou atrasada | Confirmação por assinatura; invalidadas ficam no primário; lacunas por líder; fallback |
| Olhar resultado e mexer | Conjunto imutável; mudança encerra as entradas; leitura única |
| Contaminação pelo Lab | Dono único (§3.6), tarefa I, teste de coexistência |

## 8. Revisões obrigatórias

| Revisão | Escopo |
|---|---|
| security-reviewer (R1) | Tarefa A: a credencial da NATS fica só em memória, sem `/nats/token` e sem login, e recusa vira lacuna. Tarefa B: leituras anônimas, sem nome de usuário, no ritmo declarado. **Antes** de o seletor rodar |
| database-architect (R3) | A semente de `copy_v0/1`: só a linha, sem DDL. Confere os CHECKs de `meme_rule_sets` e o `exp_ref` |
| code-reviewer (R2) | A, B, C, I, F, G e o ensaio |
| risk-engine-guardian (R4) | Revisão **limitada à fronteira**, de leitura. Ver abaixo |

**Por que o guardião volta, limitado** `[MF6]`. A primeira versão deste desenho dispensava o guardião, e a Astra
mostrou que a prova era incompleta:

- o executor seleciona por `p.mode = 'live'` **sem** filtrar o `kind` (`hunter_meme_executor/repo.py:111`);
- `decide_proposal` muda o `mode` de qualquer proposta `proposed` (`hunter_core/execution/meme/approval.py:57`);
- o `auto_approve.py:113` filtra `operator`, e a pista de lançamento em `on` lê o `launch_v0/*` (`launch_repo.py`).

A lógica da pista **não** precisa do guardião, porque nada nela é dinheiro. A fronteira, porém, é compartilhada com o
executor, e o `docs/WORKFLOW.md` (linha 59) pede a revisão quando se toca em propostas. Por isso há uma revisão
**limitada**, que confere quatro coisas:

1. o nascimento atômico `approved/paper` (§3.6);
2. um teste que tenta aprovação manual, automática, pista de lançamento em `on`, *polling* e *wake* com linhas da
   cópia presentes, e prova que nenhuma vira `meme_live_orders`;
3. que a pista não publica em `meme:proposals:wake`;
4. que não escreve em `meme_live_orders`.

Se um dia isto alimentar entradas reais, é outro desenho, com o guardião como dono e a decisão do Everton.

## 9. Plano em ondas

| Id | Tarefa | Files | Depends-on | Dono (modelo) | Estado |
|---|---|---|---|---|---|
| 0 | Contrato `LeaderEvent`/`LeaderGap`/`LeaderSource` | `packages/exchange-adapters/hunter_exchanges/pumpfun/leader_events.py` | — | orquestrador | feito |
| 0b | **Emenda do contrato** (§2.3): `LeaderConfirmation`, `first_seen_at`/`fields_complete_at`/`server_ts`, `sol_delta_lamports: int \| None`, `multi_mint`, `kind` | `leader_events.py` + teste | 0 | orquestrador ou exchange-integration (sonnet) | **pendente, bloqueia o fechamento de A e C** |
| A | Fonte NATS + fallback on-chain + combinada, emparelhamento, confirmação, lacunas | `packages/exchange-adapters/hunter_exchanges/pumpfun/leader_source*.py` (`leader_source.py`, `_nats*.py`, `_chain*.py`, `_gaps.py`, `_stats.py`, `_wiring.py`), `packages/exchange-adapters/tests/unit/test_leader_source_*.py`, `tests/live/test_live_leader_source.py` | 0, 0b | exchange-integration-specialist (sonnet) | **em voo** (arquivos na árvore; conferir contra a emenda 0b) |
| B | Seletor `copy-leaders-rule/1` (§1, emenda 3): 6 quadros + ≤ 24 `/users`, ≤ 30 requisições, quadro completo, `--include` ≤ 4, JSON `copy-leaders/1` com hashes | `infra/scripts/copy_select_leaders.py`, `copy_leaders_rule.py`, `copy_leaders_http.py`, `copy_leaders_doc.py`, `infra/scripts/tests/test_copy_leaders_*.py`, `test_copy_select_leaders.py`, `copy_leaders_rig.py` | 0 | exchange-integration-specialist (sonnet) | **código pronto** (3 rodadas da Astra, 2 dry-runs, nada gravado); falta R1 e a execução D |
| C | Pista de cópia (§3, §4): caminho quente sem IO, seletor de estado, nascimento atômico, funil, recuperação, heartbeat, stream Redis, testes (lista de `FollowPolicy`, divergências esperadas da contagem, ordem causal, invalidação, os três casos de colisão). **Ajuste pedido pela emenda 1:** carregar **todos** os conjuntos `clock = 'copy'` ativos (`copy_v0` e `copy_everton_v0`), com capacidade e recursos por conjunto; hoje `copy_spec.py` carrega só `copy_v0` | `services/meme-worker/hunter_meme_worker/copy_*.py`, `services/meme-worker/tests/test_copy_*.py`, `copy_fakes.py`, `copy_rig.py`, `copy_support.py` | 0, 0b | backend-specialist + quant-engineer (sonnet/opus) | **em voo** |
| I | Isolamento do Lab: excluir `clock = 'copy'` das leituras do Lab e conferir o `launch_v0` | `services/meme-worker/hunter_meme_worker/lab_repo.py`, `lab_repo_bets.py`, `lab_repo_pool.py`, `lab_point_read.py`, `services/meme-worker/tests/test_lab_copy_isolation.py` | C (forma dos params) | backend-specialist (sonnet) | pendente |
| P | Aceite da PumpSwap na pista (entrada por reservas, migração, custos uma vez). Sem ele, `venues = ["curve"]` | `services/meme-worker/hunter_meme_worker/copy_pool.py`, testes com fixtures reais | C | quant-engineer (opus) | pendente, opcional para T0 |
| F | Ligação: `main.py`, `config.py` (`MEME_COPY_LANE`), `context.py`, readiness | `services/meme-worker/hunter_meme_worker/main.py`, `config.py`, `context.py` | A, C | backend-specialist (sonnet) | pendente |
| G | Vista por líder + linha do diário | `infra/scripts/copy_leader_view.py`, `infra/scripts/meme_diary_*.py` | C | backend-specialist (sonnet) | pendente |
| X | Análise congelada **antes** da coleta: export SQL só leitura + script da leitura única (duas vias, WCB, portões, secundárias) com testes sintéticos de valor conhecido | `infra/research/copy_h037/export.sql`, `infra/research/copy_h037/read.py`, `infra/research/copy_h037/tests/test_read.py` | pré-registro | quant-engineer (opus) | pendente |
| E2E | Ensaio ponta a ponta com falhas: duplicata NATS/fallback, perna tardia, transferência, multi-mint, confirmação divergente, RPC fora, retomada, curva→pool, relógios, capacidade por estrato | testes de integração em `services/meme-worker/tests/integration/test_copy_e2e.py` | A, C, I, F | test-engineer (sonnet) | pendente |
| R1 | Revisão de segurança de A e B (antes de D) | — | A, B | security-reviewer (opus) | pendente |
| D | Rodar a escolha (B) com o Everton nomeando as dele; congelar o JSON | `infra/research/copy_h037/leaders_T0.json` | B, R1 | backend (sonnet) + Sexta-feira | pendente |
| E | Semente de `copy_v0/1` e `copy_everton_v0/1` a partir do JSON (params de §3 + `leaders` do estrato + `venues` + sha256). A lacuna inicial `copy_leader:*` (`lane_not_started`) tem início lógico no `created_at`, mas a linha é escrita pela pista só na ativação (H), com as duas pontas | `infra/migrations/versions/00xx_meme_copy_v0.py`, teste de migração | D, C | database-architect (opus) | pendente |
| R2 | Revisão de código + Astra no diff | — | A, B, C, I, F, G, X, E2E | code-reviewer (sonnet) | pendente |
| R3 | Revisão da semente | — | E | database-architect (opus) | pendente |
| R4 | Revisão da fronteira (§8) | — | C, I, E2E | risk-engine-guardian (opus) | pendente |
| H | Deploy: código com a pista em `off` → semente E → `MEME_COPY_LANE=paper`. **T0** = fim da lacuna inicial; registrar T0, md5 dos params e sha256 dos líderes na EXP-M28 | `infra/vps/*` (sem mudança esperada) | R1–R4, X, E2E | devops-engineer (sonnet) + Everton | pendente |
| L | Leitura única depois da maturação + advogado-de-jesus/defensor → veredito na Fila e na EXP-M28 | Fila, EXP-M28 | H + 28 d | quant-engineer (opus) | pendente |

**Ondas:** {0b} → {A, B, C} (em voo) → {I, P, F, G, X} → {E2E, R1} → {D} → {E} → {R2, R3, R4} → {H} → 28 d → {L}.
I e C tocam módulos vizinhos, mas os conjuntos de arquivos são disjuntos. F toca `main.py`: se outra tarefa da casa
estiver mexendo nele, F vai sozinha.

## 10. O que o Everton precisa decidir

1. **Quais carteiras dele** entram em `escolha_everton` (até 4), antes de T0.
2. **Decidir na NATS e invalidar depois** (o que ele pediu: milissegundos). Isso exige a emenda 0b do contrato. As
   invalidadas ficam no primário.
3. **PumpSwap no T0 ou depois.** Sem o aceite P, o piloto copia só mints na curva, e os demais viram
   `fora_de_praca`.
4. **Ver o PnL ao vivo** pela vista é permitido; **mexer** depois de ver encerra as entradas da coorte.
5. Ciência de que a previsão é NÃO CONFIRMA ou REFUTA, de que, com 28 dias, o `result` da EXP-M28 fica `inconclusivo` pela régua editorial de 30 dias distintos (estender a 30 d é decisão dele, antes de T0), de que dinheiro
   real está fora do escopo e de que o guardião faz uma revisão limitada à fronteira (§8).

## Fontes

- **Obsidian:** `00-HOME`, KB-0136, KB-0142, KB-0149, KB-0182 a KB-0187, EXP-M15, as decisões 2026-10-06 (NATS),
  2026-10-05 (seguidores) e 2026-10-09 (piloto), e as revisões da Astra `pumpfun-releitura`, `pumpfun-rt-latency` e
  `wallets-*`.
- **Desenho irmão:** `docs/design/seguir-carteiras-lucrativas.md`.
- **Método:** `docs/RESEARCH.md`.
- **Código lido:**
  - `hunter_indicators/meme/wallets/policy.py` e `params.py`;
  - no meme-worker: `launch_lane*.py`, `paper_engine.py`, `paper_fill.py`, `pool_mark.py`, `lab_bets.py`,
    `lab_repo.py` e `lab_repo_bets.py`;
  - no executor: `auto_approve.py`, `launch_config.py` e `repo.py`;
  - `hunter_core/execution/meme/approval.py`;
  - `docs/DATABASE.md` §34.
