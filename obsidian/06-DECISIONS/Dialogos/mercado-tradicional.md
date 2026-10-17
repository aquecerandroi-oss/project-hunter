---
tags: [dialogo, astra, mercado-tradicional, b3, win, rico, h-038, painel-de-sinais]
date: 2026-10-17
updated: 2026-10-17
status: registro
owner: quant-engineer
decided_on: 2026-10-17
by: claude + astra
tarefa: "estratégia de segunda 19/10 no WIN (H-038), dado ao vivo, capital e módulo puro compartilhado entre painel manual e robô MT5 — depois da decisão do Everton de parar memes e cripto"
veredito: "6 rodadas (a 1.ª saiu vazia por erro na chamada do script). R2: 5 must-fix; R3: 4 bloqueios (exclusão pós-entrada, termos do Yahoo, dado histórico, permutação); R4: 4 (censura, permutação por lado, capital, contrato LONG-only); R5: 3 (tick por lado, corrida de saídas, garantia de perda); R6 DECISÃO CONJUNTA. Não atesta implementação, dados, conta Rico nem vantagem"
---

# Mercado tradicional: a H-038 até a decisão conjunta

**Pedido:** a Sexta-feira, depois de [[2026-10-17-pausar-memes-e-cripto-ir-para-mercado-tradicional]], pediu um
caminho para o Everton operar na B3 a partir de segunda 19/10. O plano é `docs/plans/MERCADO-TRADICIONAL.md`; a
transcrição bruta está em `.claude/state/dialogue-mercado-tradicional.md`. O tópico `binance-foco` pedido no começo
do dia não chegou a ser aberto: o escopo mudou antes.

## O que mudou em cada rodada

| rodada | achado da Astra | o que mudou no plano |
|---|---|---|
| 1 | rodada vazia (erro meu na chamada) | nada; registrado |
| 2 | não chamar de "melhor estratégia"; ajuste ≠ preço de saída; Yahoo sem permissão confirmada; regra de decisão; painel sem "compre 1" e sem "21 %" de IR | hipótese "extrapolada, sem replicação brasileira"; preço-modelo = primeiro negócio depois do instante + 1 tick; três séries separadas (índice, WIN hipotético, execução real); IRRF de 1 % como antecipação |
| 3 | não excluir pregão depois da entrada; os termos do Yahoo proíbem coleta automatizada; WIN 1 min sozinho não dá o r1 nem o stop dentro da barra; patamar pelo resultado líquido; permutação da casa | exclusões só antes da entrada, censura explícita depois; **entrada manual** dos dois números do Ibovespa com instante do evento e prazo O+90; histórico sincronizado índice/WIN; aproximação OHLC rotulada; holdout 80/20 |
| 4 | censura pode esconder uma perda; a permutação tem de recalcular o stop do lado sorteado; "nenhum instrumento serve" não está provado; o `Decision` do Lab só aceita LONG e exige alvo | censura não resolvida **bloqueia o CONFIRMA**; permutação recalcula a estratégia inteira, p = (1 + n) ÷ 10 001; contrato próprio de sinal agendado (compra/venda, sem alvo) |
| 5 | tick favorável nas vendas; corrida entre a saída por tempo e o stop; stop nominal apresentado como perda máxima | deslizamento por lado, contado uma vez; corrida declarada e semântica da plataforma como pendência; o texto da Astra sobre o limite diário adotado |
| 6 | **DECISÃO CONJUNTA** | — |

Uma discordância resolvida a meu favor (rodada 3→4): a Astra pediu IC inferior acima do MRE; mostrei que a regra de
`docs/RESEARCH.md` (média ≥ MRE **e** IC inferior > 0) já não tem a contradição apontada, e que IC > MRE pediria
~4 900 pregões. Ela retirou a exigência.

## Decisão conjunta (rodada 6)

- Uma hipótese, sem filtros novos: **H-038**, momento intradiário de mercado no WIN
  ([[KB-0176-momento-intradiario-condicionado-o-vizinho-mais-perto]]), extrapolada, sem vantagem brasileira demonstrada.
- Sinal pela **entrada manual** dos dois números do Ibovespa, com instante do evento, recebimento e decisão separados
  (`event_at ≤ received_at ≤ decision_at`), prazo O+90, sinal imutável.
- Três séries distintas; o índice nunca é publicado como lucro; WIN hipotético "não mensurável" sem trajetória.
- Censura pós-entrada não resolvida bloqueia o CONFIRMA; aproximação OHLC rotulada; deslizamento por lado uma vez;
  permutação recalculando a estratégia por lado; bootstrap de meses inteiros; holdout intocado.
- Stop nominal ≠ perda máxima; o painel não controla a conta; nenhuma ordem, credencial ou tamanho por agentes.
- Núcleo puro com contrato próprio, compartilhado entre o painel e o robô MT5 (desenho separado), sem autorizar ordens.
- **Pendências verificáveis** (não cumpridas): margem/RLP/custos da Rico; semântica de encerramento e proteção da
  plataforma; símbolo e histórico do índice no MT5 e sincronização; acesso e termos do BDI.

A recomendação da Sexta-feira continua a de não operar real antes de evidência ("não demonstramos vantagem executável
nesta regra"); o Everton decidiu operar.

## Relacionado

[[2026-10-17-pausar-memes-e-cripto-ir-para-mercado-tradicional]] · [[KB-0194-day-trade-no-mini-indice-quase-ninguem-vive-disso]] ·
[[KB-0176-momento-intradiario-condicionado-o-vizinho-mais-perto]] · [[KB-0149-o-que-a-mesa-real-ensinou]] ·
[[Fila de Hipoteses]] · [[Mapa de Estrategias]] · [[Dialogos/Index|diálogos]]
