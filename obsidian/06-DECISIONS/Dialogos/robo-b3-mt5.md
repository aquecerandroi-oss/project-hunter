---
tags: [dialogo, astra, b3, mt5, rico, robo, execucao, risco, mercado-tradicional]
date: 2026-10-17
updated: 2026-10-17
status: registro
owner: sexta-feira
decided_on: 2026-10-17
by: risk-engine-guardian + astra
tarefa: desenho do robô de execução real do Everton na B3 (MetaTrader 5, conta dele na Rico)
veredito: "6 rodadas. R1 com 10 achados (3 CRITICAL); R2 com 4 abertos; R3 com 5 (2 CRITICAL); R4 com 3 (1 CRITICAL); R5 com 2; R6 DECISÃO CONJUNTA, sem divergência arquitetural restante. O fechamento aprova o desenho como contrato, não certifica execução na Rico e não autoriza dinheiro real"
---

# Robô B3 no MetaTrader 5: o desenho até a decisão conjunta

**Pedido:** decisão do Everton de 17/10/2026, transmitida pela Sexta-feira: o robô automático **dele**, na conta
**dele** na Rico, pelo MetaTrader 5. Ele digita a credencial, ele põe o dinheiro, ele liga. O desenho é
`docs/design/robo-b3-mt5.md`; a transcrição bruta está em `.claude/state/dialogue-robo-b3-mt5.md`. A estratégia vem de
outra tarefa ([[Dialogos/mercado-tradicional|mercado-tradicional]], H-038 na [[Fila de Hipoteses]]); o robô foi
desenhado para receber qualquer regra mecânica.

**Notas lidas e o que mudaram:** [[KB-0149-o-que-a-mesa-real-ensinou]] (72 % do prejuízo foi custo → custo em todo
cálculo de risco; RPC caído 2 dias sem alarme → cão de guarda fora do PC; revisão adversária pagou-se → sessão demo e
revisões obrigatórias). [[KB-0194-day-trade-no-mini-indice-quase-ninguem-vive-disso]] (97 % das pessoas físicas no WIN
perderam → o robô entrega invariantes, não vantagem). `docs/RISK_ENGINE.md` e `docs/RISK_ENGINE_MEME.md` (forma do
motor puro, kill switch, portões). O `signing_gate`/`program_check` do executor meme (relê o estado antes de enviar;
especificação mudou → só saídas).

## O que mudou em cada rodada

| Rodada | O que a Astra achou | O que mudou no desenho |
|---|---|---|
| 1 | 10 achados. CRITICAL: Python e EA mandando "vende 1" juntos invertem a conta; EA agindo numa conta não autorizada pelo `magic`; dois executores enviando a mesma intenção | risco medido do pior preço admissível (o "nunca passa do limite" vale para o risco **modelado**); contrato da perda do pregão (dedupe por negócio, custo positivo por perna, cobertura contra o patrimônio); sizing com margem livre e `WARNING` (1 vira 0); três relógios (sinal do pregão, insumos, aprovação de 30 s); claim atômico; herança do *netting* corrigida (redução não apaga stop) |
| 2 | um batimento parado não prova que o outro remetente parou | **o EA deixou de mandar ordens**: só avisa o celular (`SendNotification`); atribuição de posição pela cadeia de negócios da corretora |
| 3 | retirar o stop para fechar deixa posição sem stop se o PC cair no meio; repetir fechamento depois de tempo esgotado duplica | **saída pelo aperto do colchete**: `sl` no bid e `tp` no ask, quem fecha é o servidor; armamento por instância |
| 4 | o fechamento direto "só no prazo" ainda disputa com o stop; SLTP numa conta não verificada; "recolocar se ausente" não é condicional | **nenhuma ordem direcional de saída na v1**; **nenhuma mutação sem identidade e autoridade** |
| 5 | o mesmo lease com duas validades; K3 dependia do lease que dependia da reconciliação que dependia do K3 | **um** objeto de autoridade, vencimento absoluto no fim do pregão, três fases: leitura → "Conceder gestão" → "Armar entradas" |
| 6 | — | DECISÃO CONJUNTA |

Os achados que só ela levantou e dependiam de fato externo foram conferidos na documentação oficial da MetaQuotes
antes de absorvidos: `order_calc_margin` ignora ordens e posições existentes; em *netting* a posição é identificada
pelo símbolo e preencher `position` não torna a ordem só-redução.

## DECISÃO CONJUNTA (rodada 6)

- Uma autoridade por conta/servidor, host, instância e pregão, com vencimento absoluto; o batimento não transfere
  posse nem encerra a gestão.
- Partida só lendo → "Conceder gestão" (ato do Everton) → recuperação e reconciliação → "Armar entradas" (K3). A
  concessão não limpa `EMERGENCY` nem a trava diária.
- Nenhuma mutação sem identidade e autoridade; troca de instância supervisionada, que neutraliza a anterior e herda
  as incertezas dela (`unknown` atravessa instâncias).
- O EA só notifica. Saída automática só pelo colchete, sem retirar stop e sem ordem direcional; prazo vencido é
  degradação com alerta, não zeragem.
- SLTP incerto impede nova modificação até resultado terminal correlacionado.
- Proposta e decisão persistidas antes da ordem, claim exclusivo, conferências finais, Decimal/UTC, auditoria,
  isolamento por tenant, custos sem dupla contagem, risco modelado distinto de perda máxima.
- Engenharia, evidência da H-038 e autorização de dinheiro real são portões distintos.

**Limitações declaradas (não garantias):** a saída pode atrasar; instância nova sem a nossa API só observa; um
remetente neutralizado pode ter requisição em trânsito; o *fencing token* não é aplicado pela corretora; a rota manual
do Everton disputa com o stop.

**Condicionado às provas da sessão demo:** T7/T8 (onde o stop vive na Rico; `magic`/`reason`/`comment` preservados),
T13 (o colchete zera sem criar exposição nova e sem instante sem stop), T14 (ciclo da ordem limitada), T10/T15/T16
(reinício, exclusividade, autoridade), T17 e rotas manuais. Aceite: T1–T17 em duas sessões de dias diferentes, uma
na grade nova de 03/11. Se o colchete falhar, o desenho volta para revisão.

**Decisões do Everton** (os "sim" da coluna de proposta não são consentimento): D1 (ADR da exceção live B3, com
escopo e data de revisão), D2–D8 (capital, mapeamento de "R$ 1.000 por operação", teto por operação, contratos,
horário de zeragem, RLP, trava diária), D9 (PC supervisionado ou VPS), D10–D16 (ninguém além dele zera com o Python
morto, posição manual, custos reais, canal de alerta, dois atos a cada reinício, um host, as duas limitações da v1).

## O que a base aprendeu

1. **No MetaTrader 5 em conta *netting*, uma ordem de fechamento não é só-redução.** O stop do servidor é um segundo
   remetente que não dá para tirar; qualquer "vende 1" nosso pode somar com o dele e inverter a conta. A saída segura
   é mexer só no colchete (`sl`/`tp`) da própria posição.
2. **Batimento é sinal de vida, não exclusão.** Dois processos que decidem quem age por batimento podem agir os dois.
3. **"Recolocar se ausente" não é escrita condicional** quando o servidor não oferece compare-and-set.
4. O site da Rico bloqueia leitura automatizada (403 da CDN da XP); margem, regra de robôs e zeragem compulsória ficam
   com o Everton, não com suposição nossa.

Registrado também em [[Execution Engine]] (seção "Linha B3").

## Relacionadas

[[Dialogos/Index|índice dos diálogos]] · [[Dialogos/mercado-tradicional|mercado-tradicional]] ·
[[KB-0149-o-que-a-mesa-real-ensinou]] · [[KB-0194-day-trade-no-mini-indice-quase-ninguem-vive-disso]] ·
[[Execution Engine]] · [[Risk Engine]] · [[Fila de Hipoteses]]
