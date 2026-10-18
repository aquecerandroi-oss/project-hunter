---
tags: [revisao-astra, b3, mt5, rico, robo, risco, execucao, maquina-de-estados, mercado-tradicional]
date: 2026-10-17
updated: 2026-10-17
status: registro
versao_contrato: "1.1 (17/10/2026) — alinhada a R1/R2/R3; revisão curta da Astra com 2 must-fix aceitos"
owner: risk-engine-guardian
decided_on: 2026-10-17
by: risk-engine-guardian + astra
tarefa: "R0a do desenho docs/design/robo-b3-mt5.md §9 — contrato normativo docs/RISK_ENGINE_B3.md (máquinas de estado, queda em cada intervalo, colchete, matriz de falhas, hunter_hb, 25 checks, valores iniciais)"
veredito: "4 rodadas. R1: 10 must-fix (1 CRITICAL), todos aceitos, e o 'reparo idêntico' que eu propus recusado por ela; R2: 8 fechados, 2 parciais (R0a-2 CRITICAL, R0a-9), absorvidos — R0a-2 por caminho diferente do dela, divergência registrada; R3: R0a-9 fechado, 2 pontos (perda após fsync declarada fora do modelo como R-8; §6.7/F6 subordinadas à §4.3); R4: nenhum must-fix restante — 'o contrato pode ser congelado para R1/R2/R5/R7, dentro do modelo de falhas declarado'. Não certifica a semântica da Rico nem autoriza dinheiro real"
---

# Revisão da Astra — contrato de risco do robô B3 (R0a)

**Pedido:** revisar `docs/RISK_ENGINE_B3.md`, o contrato congelado que R1 (motor puro `hunter_risk_b3`), R2
(adaptador MT5), R5 (serviço) e R7 (EA vigia) implementam em paralelo, procurando **buracos das máquinas de estado
sob queda do processo e reconexão**. Origem: desenho `docs/design/robo-b3-mt5.md` (commit `35b174cd`) e a decisão
conjunta de seis rodadas em [[Dialogos/robo-b3-mt5]]. Fontes brutas: `.claude/state/astra-review-R0a-risk-engine-b3.md`,
`-r2.md`, `-r3.md` e `-r4.md`.

**Notas lidas antes e o que mudaram:** [[KB-0149-o-que-a-mesa-real-ensinou]] (custo em todo risco → `fee_schedule_missing`
recusa armar; RPC parado 2 dias sem alarme → dois batimentos e EA com relógio monotônico; revisão adversária paga →
invariantes viram testes obrigatórios); [[Fila de Hipoteses]] (H-038: o real não rotula a hipótese → a saída em C
começa o colchete e grava pretendido × efetivo); [[Execution Engine]] e [[Risk Engine]] (saída é intenção durável;
kill switch "o mais restritivo"). Nenhuma estratégia mudou nesta tarefa.

## Rodada 1 — 10 must-fix (1 CRITICAL), todos aceitos

1. A reavaliação antes do envio reprovava a própria entrada (o check 11 via a própria intenção; o 13 a contava como
   a operação do dia) → os checks 11 e 13 excluem a própria proposta.
2. **CRITICAL** — SLTP gravada só no buffer, morte, a instância nova lia `idle` da API e mandava outra antes de
   reenviar o buffer (A95/B99) → buffer entregue **antes** da concessão de gestão; slot herdado `unknown`.
3. "Nível lido igual ao pedido" não prova autoria (o Everton pode pôr os mesmos níveis à mão); o "reparo idêntico"
   que eu propus cai com uma terceira modificação; P4 por declaração não é prova; `PLACED`/`DONE_PARTIAL` não
   concluem SLTP → P2 retirada, reparo idêntico recusado, P4 exige a linha do Diário, retcodes por ação.
4. O ticket da posição pode mudar (operação de serviço); o identificador não → `position_id` é a identidade;
   P3 só com prova de que a corretora rejeita SLTP com ticket velho (T13); senão a SLTP vira órfã do símbolo.
5. Piso e "stop cruzado no reparo" pediam coisas incompatíveis → `floor_unplaceable` (nada enviado, alerta) e D17
   para o Everton.
6. Conta A → B → A destravava a guarda → travas locais *latched* até reinício.
7. Atribuição de leitura antiga gerindo posição → sem cache; `unreadable` bloqueia mutação.
8. Relógio do PC errado na concessão estendia a autoridade → âncora no relógio da API.
9. Reinício renovava o prazo da saída → `exit_due_at` por gatilho, prazo original.
10. Relógio do PC que volta deixava o batimento morto parecendo vivo; `FILE_SHARE_READ|WRITE` não deixa o `os.replace`
    passar → o EA mede `GetTickCount64` desde a última mudança de `(inst, seq)`.

## Rodada 2 — 8 fechados, 2 parciais, absorvidos

- **R0a-2 ainda aberto:** com API e `fsync` falhando, a SLTP partia sem registro; com o buffer íntegro e sem a linha, a
  nova instância não tinha como saber — e uma posição nova no mesmo símbolo ficava exposta. **Decisão:** nenhuma SLTP
  sem gravação durável **confirmada**; época de gestão com linha `epoch_open` no buffer.
- **R0a-9 ainda aberto:** `EMERGENCY` + 1.ª SLTP rejeitada + morte + rearme apagava a obrigação de sair →
  obrigação recuperada pelas transições duráveis do kill switch dentro da vida da posição.

**Divergência registrada (caminho, não objetivo):** ela propôs um marcador de "época possivelmente incompleta" com o
envio seguindo sem registro; escolhi **não enviar sem registro durável**, porque a completude fica provada por
construção e uma queda comum não vira `unknown` em toda posição. Preço declarado: na falha **dupla** API + disco o
robô para de mexer em níveis (o `sl` confirmado fica no servidor).

## Rodada 3 — R0a-9 fechado; 2 pontos, absorvidos como ela escreveu

- Perda de um **sufixo** de linhas do buffer depois de `fsync` confirmado: nem `epoch_open` nem a cadeia de hash a
  detectam → declarada **fora do modelo suportado** (residual R-8), a opção que ela mesma ofereceu; o contrato
  deixou de afirmar detecção.
- O trecho do buffer e a linha F6 ainda diziam que falha de disco "nunca atrasa" a saída — isso autorizaria de novo
  o envio sem registro → subordinados à regra "nenhuma SLTP sem gravação durável confirmada".

## Rodada 4 — congelamento liberado

Os dois pontos fechados e nenhum must-fix restante: "o contrato pode ser congelado para R1/R2/R5/R7, dentro do
modelo de falhas declarado". O fechamento aprova o contrato como coordenação; **não** certifica a semântica da Rico
(as provas T7, T8, T9, T13 e T14 da sessão demo decidem) e não autoriza dinheiro real.

**Pendências para o Everton surgidas aqui:** D17 (piso que não pode ser colocado: o robô só alerta, ou tenta sair
pelo colchete mais longe que o stop aprovado?) e a confirmação dos valores marcados "proposta R0a" no contrato (§9),
que o desenho não deu.

## O que a base aprendeu

1. **Ler um nível no servidor não prova que uma requisição terminou.** Três fatos — requisição terminou, proteção
   observada, posição encerrada — têm três provas, e nenhuma serve pela outra.
2. **Buffer íntegro não prova completude** se o envio pode acontecer sem gravar. Completude só por construção:
   nenhuma requisição sem registro durável confirmado.
3. **No MT5, `POSITION_TICKET` pode mudar; `POSITION_IDENTIFIER` é a identidade.** Uma máquina de estados por ticket
   perde a cadeia numa operação de serviço.
4. **Prazo de saída e obrigação de saída vêm do histórico** (gatilho e transição durável), nunca da memória do
   processo — senão um reinício dá prazo novo ou esquece a saída.
5. **Excluir a própria proposta** das contagens de "intenção em voo" — senão toda reavaliação antes do envio se
   reprova a si mesma.

## v1.1 (17/10/2026) — o contrato alinhado ao que R1, R2 e R3 implementaram

**Pedido:** publicar a v1.1 de `docs/RISK_ENGINE_B3.md` com o que as três implementações fixaram e uma revisão curta de
consistência da Astra contra os três códigos (`.claude/state/astra-review-R0a-contract-v11.md`). Changelog completo
na §0.1 do contrato (C1–C20); documento normativo editado no lugar, não append-only.

**Notas lidas antes e o que mudaram:** [[Revisoes-Astra/R1-hunter-risk-b3|R1]] (as 11 escolhas a–k e as 4 pendências
para o contrato → C1–C9, C19, C20); [[Revisoes-Astra/R2-mt5-adapter|R2]] (cancelamento, pista `unresolved`, resultado
tardio normalizado, recusas de toque → C10–C13); [[Revisoes-Astra/R3-b3-schema|R3]] e `docs/DATABASE.md` §74 (tipos,
enum do kill switch, ordem de travas, armamento, tabelas extras → C14–C18); [[KB-0149-o-que-a-mesa-real-ensinou]] §1
(custo ausente nunca vira zero → mantido na §8.3 com `DayDeal.commission`/`fee` obrigatórios) e §4.20 (o que para sem
alarme custa mais → o falso positivo da C10 ficou com custo escrito, não escondido); [[Fila de Hipoteses]] H-038 (o
stop dispara com toque igual → a igualdade do piso no toque é colocável). Não existe página EXP para a H-038. Nenhuma
estratégia mudou; [[Mapa de Estrategias]] não foi tocado.

**Decisões principais (motivo no contrato):**

- **C1** — livro invertido/cruzado/zerado é `failed` `quote_invalid` (dado lido que diz "não"; estado real de leilão
  na B3), não `unavailable`; a frase contrária da §8.3 caiu.
- **C9** — frescor único `−2 s ≤ now − ts ≤ máx` (marca, relógio, reconciliação, API; âncora do futuro =
  `day_anchor_missing`); não vale para `created_at`.
- **C10/C12/C13** — `CancelledError` num envio é `unknown`; a pista única fica `unresolved` até `drain_late_results()`;
  resultado tardio normalizado e, para SLTP com veredito terminal, é P1.
- **C11** — recusas de toque da guarda de `send_sltp` na requisição que carrega o piso → `floor_unplaceable`;
  `sl_wrong_side_of_touch` refuta (sem reparo automático, D17), `quote_*`/`tp_wrong_side_of_touch` só não provam (o
  passe seguinte relê). `quote_invalid` passa a significar ¬(`0 < bid < ask`) também no adaptador.
- **C14–C18** — versões e pin comparados em `::text`; `b3_kill_state` = `kill_switch_state`; travas sistema →
  organização → conta para todo escritor; armar = fase `entries`; `b3_robot_accounts`, `b3_session_anchors`,
  `b3_robot_events`.
- **C19/C20** — gatilhos reemitidos até o *latch* chegar (R5 idempotente); `evaluate_exit` sem carimbo (o serviço
  carimba).

**Revisão da Astra — 2 must-fix, os dois aceitos e reproduzidos no código:** (1) o contrato dizia que o piso no toque
(`floor = bid − d`) era inexequível, mas `packages/exchange-adapters/hunter_exchanges/mt5/guards.py:132` recusa só `>`
— o texto passou a seguir o código e a regra do MT5 (`bid − SL ≥ stops_level`); (2) a minha C11 e a §5.1 da v1.0
mandavam uma posição **em saída** para `degraded`, transição que `infra/migrations/ddl/b3_robot_guards.py:530` recusa
— em saída o estado e o prazo ficam e o laço de saída relê. Nice-to-have aceitos: ressalva na C1 (falhas
independentes da cotação vêm antes), dependência 16/17 ← "sem stop" (não o estado do 15), custo do falso positivo da
C10 escrito e regra nova "R5 não cancela envio em curso". Concordou com a aresta de releitura, com `0 < bid < ask` na
guarda de `send_sltp` e com resultado tardio = P1 (gravado antes de liberar o slot; não limpa `ipc_hung`).

**Divergência registrada (com o brief, não com a Astra):** o brief pedia "`quote_invalid`/`quote_unreadable` →
`floor_unplaceable`" sem qualificação. Mantive o mapeamento, mas acrescentei a releitura para as causas que só **não
provam** a colocação: sem ela, um `tick()` que falha uma vez na carência deixaria uma posição nascida sem `sl` (a Rico
o descartou) sem stop até o Everton agir.

**Código que discorda da v1.1:** R2 `guards.py:128` (`quote_invalid` só com `bid ≤ 0 ∨ ask ≤ 0`; num leilão com
livro cruzado, bid 110 / ask 95 e último 97, um `sl` comprado em 98 passa a guarda e dispara na abertura). Melhoria
pendente: R2 expor se uma chamada cancelada começou (`ipc.py:153`).

**O que a base aprendeu**

1. **Um contrato congelado pode contradizer o banco que o implementa** — a v1.0 mandava `exiting → degraded`, e o
   gatilho de R3 (I-X-3) recusa. Toda versão nova do contrato tem de ser lida contra os gatilhos, não só contra o
   motor.
2. **"Não provado" não é "refutado".** Falha de leitura do toque e toque do lado errado pedem o mesmo "nenhum envio",
   mas só a refutação justifica travar a proteção até o humano.
3. **O mesmo nome com dois significados é um defeito.** `quote_invalid` no motor e no adaptador divergiam justamente no
   caso do livro cruzado.

## Relacionadas

[[Dialogos/robo-b3-mt5]] · [[Execution Engine]] · [[Risk Engine]] · [[KB-0149-o-que-a-mesa-real-ensinou]] ·
[[Fila de Hipoteses]] · [[Mapa de Estrategias]] · [[Revisoes-Astra/R1-hunter-risk-b3|R1-hunter-risk-b3]] ·
[[Revisoes-Astra/R2-mt5-adapter|R2-mt5-adapter]] · [[Revisoes-Astra/R3-b3-schema|R3-b3-schema]] · contrato
`docs/RISK_ENGINE_B3.md` · ADR `docs/decisions/0007-robo-b3-mt5-excecao-live.md`
