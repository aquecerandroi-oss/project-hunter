# R1 — Replay de políticas de saída sobre as entradas congeladas (EXP-0004)

**SOMBRA — hipotético, sem capital, custos assumidos.** `purpose=research_only`; nada foi ativado, nada ordena, nenhuma tabela do Lab foi escrita.

- `as_of` (corte de dados, não só de população): `2026-09-08T04:00:00+00:00`
- `input_digest`: `6000867c3df37418` (registros lidos) · `series_digest`: `3bd45752b9f8bc3d` (velas dobradas). O Lab continua escrevendo; duas execuções só são comparáveis com os mesmos dois dígitos.
- **Limite declarado:** o corte `as_of` vale para as velas; o funding é lido `as_stored_at_read_time`, porque quem consulta `funding_rates` é o `settle` de produção, reusado verbatim. Uma linha de funding ingerida depois do corte é visível à liquidação — é exatamente o que as divergências da §2 mostram.
- semente: `20260906` · reamostras: `10000` · família Holm: `7` · efeito mínimo declarado: `0.05 R`
- políticas: base

## 1. Manifesto e população

| strategy_version_id | versão | params_hash | ativada em |
| --- | --- | --- | --- |
| 3e655c2a-4ef1-492b-ae80-46ec6f26321c | momentum_v2 | 40e1688e6b5f6385 | 2026-09-08T04:33:56.865371+00:00 |

| versão | terminal | no_entry |
| --- | --- | --- |
| momentum_v2 | 224 | 0 |

## 2. Reprodução da base (passo 1)

| versão | linhas | comparáveis | reproduzidos | divergentes | late | sem resolver | taxa (tudo) | taxa (trajetória) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| momentum_v2 | 224 | 224 | 224 | 0 | 0 | 0 | 1.0000 | 1.0000 |

Divergências: **0** campos em **0** linhas — **0** delas só na liquidação (funding) e **0** campos de trajetória.

Divergência **só de liquidação** é compatível com um settlement de funding ingerido depois de o outcome ter sido liquidado: a mesma trajetória, o mesmo `r_ex_funding`, e um `R_net` que muda porque hoje existe uma linha em `funding_rates` que não existia quando o worker fechou as contas. **Compatível, não comprovado**: `funding_rates` não guarda o instante de ingestão, então nada no banco decide *quando* a linha chegou. Divergência de **trajetória** não teria essa desculpa — seria bug de replay, e o portão do passo 1 barra a execução.

## 3. Cobertura e métricas por política

| política | resolvidos | avaliáveis (R_net) | sem entrada | sem resolver | maturados | gatilhos de invalidação | taxa de alvo | taxa de lucro líquido | expectancy líq. (R) | PF |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base | 224 | 222 (sem funding: 2) | 0 | — | 224 | {"invalidation": 82} | 0.669118 (91/136) | 0.414414 | -0.171740 | 0.645428 (den. 107.527412) |

`target2_missing` / `target3_missing` não é falha: `volume_anomaly_v1/v2` persiste um único alvo, então os braços de alvo (L1) só existem para `momentum` — os contrastes `TGT-3 − base` e `TGT-4.5 − base` correm sobre uma subpopulação diferente dos demais, e isso não é comparável linha a linha com os outros cinco.

## 4. Os sete contrastes (pareados por sinal)

| contraste | pares | blocos | Δ médio R_net | IC 95% (blocos) | p | p Holm | rejeita? | abs(Δ) ≥ efeito mín. |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

Sensibilidade sem funding (`r_ex_funding`, cobertura própria):

| contraste | pares | Δ médio | IC 95% |
| --- | --- | --- | --- |

## 5. O que é inconclusivo, e por quê

**Portão do passo 1:** passou — reprodução de trajetória 1.0000 sobre 224 linhas comparáveis (limiar 0.9900); reprodução completa 1.0000; 0 linhas divergiram **só na liquidação**. Os contrastes abaixo só existem porque esse portão passou.

Outcomes da base com horizonte **maturado** no corte: **224** (avaliáveis com `R_net`: 222; limiar 100); dias distintos: **24** (limiar 30). Veredito editorial: **inconclusive**.

Com menos de 100 outcomes maduros ou menos de 30 dias distintos o resultado é **inconclusivo por contrato** (SHADOW-LAB.md §9). O que este piloto entrega é **aprendizado operacional** — quanto do acompanhamento real o replay reproduz *nesta leitura*, quanta cobertura cada política tem e qual é a ordem de grandeza das diferenças —, **não confirmação**. Os p-valores são exploratórios: vêm de inversão de sinal por blocos de dia, cuja validade exige simetria dos efeitos de bloco que nada aqui estabeleceu; com poucos blocos o menor p atingível já é maior que o limiar de Holm, e com um único bloco o teste devolve `p = 1` **por construção** — o que não é evidência de equivalência, é ausência de replicação.

