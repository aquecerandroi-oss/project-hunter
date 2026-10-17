---
tags: [revisao-astra, b3, mt5, rico, robo, risco, execucao, maquina-de-estados, mercado-tradicional]
date: 2026-10-17
updated: 2026-10-17
status: registro
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

## Relacionadas

[[Dialogos/robo-b3-mt5]] · [[Execution Engine]] · [[Risk Engine]] · [[KB-0149-o-que-a-mesa-real-ensinou]] ·
[[Fila de Hipoteses]] · contrato `docs/RISK_ENGINE_B3.md` · ADR `docs/decisions/0007-robo-b3-mt5-excecao-live.md`
