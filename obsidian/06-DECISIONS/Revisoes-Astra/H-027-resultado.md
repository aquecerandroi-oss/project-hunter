---
tags: [revisao-astra, cripto, tendencia-diaria, resultado, h-027, red-team, auditoria-de-dados]
date: 2026-10-01
updated: 2026-10-01
status: registro
owner: sexta-feira
decided_on: 2026-10-01
by: astra
tarefa: R86 — resultado e código da H-027; red-team da C1 e auditoria de dados do Lab (pedidos pelo orquestrador) aplicados como robustez pós-desfecho
veredito: concorda com momentum REFUTA (tamanho previsto) e H-027 global NÃO CONFIRMA; 2 must-fix de instrumento aceitos e corrigidos com saída idêntica; red-team e auditoria rodados como robustez declarada — a refutação do tamanho não sobrevive ao efeito fixo de dia e o grupo razão ≤ 0 tem só 13 datas
---

# Revisão da Astra — resultado da H-027 (R86), com o red-team e a auditoria de dados

**Linha do tempo (UTC, 01/10/2026):** pré-registro 02:56 · emenda 03:02 · lista elegível congelada 03:04:58 (sha256
`f6fb2201…`) · desfechos lidos 03:06:15 · primeira corrida do protocolo ~03:07 · revisão do resultado 03:12 · as duas
entradas do orquestrador chegaram **depois** da leitura dos desfechos (o arquivo do red-team existia no disco desde
03:01:08, mas não foi lido antes; a auditoria foi escrita às 03:09:55). Por isso nenhuma das guardas novas mudou
critério: rodaram como **robustez declarada** (`.claude/state/r86/robust86.py` → `robust.txt`).

## 1. Revisão do resultado e do código

**Pedido:** reproduzir, dizer se os rótulos seguem a letra do pré-registro + emenda, achar defeito que mude número ou
rótulo, e como redigir o que não concluir. Ela rodou os 27 testes, executou `run86` e `smoke86` em memória
(`OUTPUT_EQUALS_SAVED: True`), reconstruiu a lista congelada (mesmo sha256), conferiu IDs únicos nos desfechos e 0
elegíveis sem R.

**Rótulos:** corretos pela letra — `momentum` **REFUTA** (os dois IC superiores < +0,05); global **NÃO CONFIRMA**
(a emenda exige as duas estratégias refutando; a `volume_anomaly` está em limite de dado).

**Dois must-fix de instrumento, aceitos, cada um com teste que falhou antes e passa depois; nenhum número mudou**
(`h027.txt` byte a byte igual, sha256 `c9609a6f…`):

1. **Corte não identificável não bloqueava o rótulo** — ela montou um caso sintético em que o corte −0,05 fica
   constante e o instrumento devolvia REFUTA; pela emenda tem de ser LIMITE (instrumento). → `cuts_invalid` propaga.
   Nos cinco cortes reais, posto completo.
2. **Junção não falhava fechada** — ID repetido nos desfechos sobrescrevia; elegível sem R saía em silêncio. →
   `JoinError` para ID repetido, elegível ausente ou sem R; hash da lista comparado com o congelado.

**Nice-to-have aceitos:** "sem guarda" é só a dos 20 dias (tirando as duas ela achou 944 unidades e β −0,0442,
mesmo quadro); sensibilidades e fumaça declaradas com 2 000 réplicas.

**Redação que ela pediu e que ficou:** NÃO CONFIRMA nesta análise retrospectiva; refuta o tamanho positivo previsto,
não demonstra efeito zero nem negativo; nada vale além dos 16 mercados e da janela; as metades são estabilidade
interna; a coorte futura da C1 não foi feita e **não deve ser priorizada só para repetir este filtro**. A observação
da `mean_reversion v14` (razão ≤ 0: 16 unidades, 7 dias, 7 mercados, 6 no mesmo dia) é no máximo pista descritiva de
reversão — e R_net de sinal perpétuo do Lab não é execução da `spot/1`. Nada sustenta braço de papel.

## 2. Red-team da C1 (`astra-review-astra-redteam-c1.md`) — como robustez pós-desfecho

Doze pontos; os que se medem no dado foram rodados sem mudar critério:

| ponto | resultado | efeito |
|---|---|---|
| momentum entre moedas lido como estado | FE mercado −0,062 [−0,160; −0,021]; FE dia −0,011 [−0,067; +0,058]; FE mercado+dia −0,060 [−0,158; +0,004] | sem componente positivo dentro da moeda; **com FE de dia o IC sup passa de +0,05** — a refutação do tamanho não é robusta a isso |
| um regime só | 23 dias de setembro | conclusão restrita à janela |
| dependência entre dias | blocos de calendário de 3/5/7 dias: IC sup +0,028/+0,036/+0,039; nenhuma saída cruza a fronteira das metades | refutação mantida |
| poucos dias num braço | razão ≤ 0 em 13 datas (180 de 198 unidades em 11–18/09); 2.ª metade: 5 datas | **falha o piso proposto de 15** → contraste por sinal não verificável |
| concentração | β e nível do grupo favorável negativos sem cada um dos 16 mercados | mantido |
| custo | nível já < 0 com IC inteiro < 0 | moot; reconstrução por perna não feita |
| população móvel, falha fechada, réplicas inválidas | já cobertos pela emenda das 03:02Z | — |

## 3. Auditoria de dados do Lab (`astra-review-astra-auditoria-lab.md`) — contagens deste estudo

Spot fora por `market_id`/`market_type` (nunca por símbolo): 163 / 97 / 7 (momentum / volume_anomaly / v14) ·
`no_entry` fora: 925 / 151 / 33 · R_net nulo nunca vira zero: 11 terminais completos fora (momentum 6 com razão > 0 e
4 com ≤ 0; volume_anomaly 1) · buracos internos: ARK sem sinal, MOVR com os 4 terminais sem razão (dia incompleto) ·
685 de 874 unidades usam algum dia completado por backfill (> 5 min depois do fim do dia) antes da emissão → o estado
diário é **reconstrução**.

**Leitura final aceita:** o rótulo do protocolo fica (momentum REFUTA, global NÃO CONFIRMA); a afirmação generalizada
"a tendência diária não acrescenta +0,05 R" é **não confirmada**, não refutada, porque não sobrevive ao FE de dia e o
grupo ≤ 0 é uma semana. Nada rejeitado.

**Bruto:** `.claude/state/astra-review-H-027-result.md` · `.claude/state/astra-review-astra-redteam-c1.md` ·
`.claude/state/astra-review-astra-auditoria-lab.md` · `.claude/state/r86/h027.txt` · `.claude/state/r86/robust.txt`
**Relacionado:** [[KB-0170-tendencia-diaria-nao-separa-os-sinais-do-lab|KB-0170]] · [[H-027-prereg]] ·
[[Fila de Hipoteses]] · [[KB-0179-o-que-um-resultado-da-c1-pode-e-nao-pode-dizer|KB-0179]] · [[Roster-advogado-defensor]]
