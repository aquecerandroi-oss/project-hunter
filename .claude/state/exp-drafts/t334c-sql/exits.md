# R1 — Replay de políticas de saída sobre as entradas congeladas (EXP-0004)

**SOMBRA — hipotético, sem capital, custos assumidos.** `purpose=research_only`; nada foi ativado, nada ordena, nenhuma tabela do Lab foi escrita.

- `as_of` (corte de dados, não só de população): `2026-09-08T22:00:00+00:00`
- `input_digest`: `f2a226822eef4ed0` (registros lidos) · `series_digest`: `449635eaedbf3df4` (velas dobradas). O Lab continua escrevendo; duas execuções só são comparáveis com os mesmos dois dígitos.
- **Limite declarado:** o corte `as_of` vale para as velas; o funding é lido `as_stored_at_read_time`, porque quem consulta `funding_rates` é o `settle` de produção, reusado verbatim. Uma linha de funding ingerida depois do corte é visível à liquidação — é exatamente o que as divergências da §2 mostram.
- semente: `20260906` · reamostras: `10000` · família Holm: `7` · efeito mínimo declarado: `0.05 R`
- políticas: base, INV-B

## 1. Manifesto e população

| strategy_version_id | versão | params_hash | ativada em |
| --- | --- | --- | --- |
| 01a08323-7c1e-7b83-8527-553a329e4c32 | trendline_breakout_v1 | f2e8017c7251e22f | 2026-09-08T22:29:52.701952+00:00 |

| versão | terminal | no_entry |
| --- | --- | --- |
| trendline_breakout_v1 | 47 | 0 |

## 2. Reprodução da base (passo 1)

| versão | linhas | comparáveis | reproduzidos | divergentes | late | sem resolver | taxa (tudo) | taxa (trajetória) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| trendline_breakout_v1 | 47 | 47 | 47 | 0 | 0 | 0 | 1.0000 | 1.0000 |

Divergências: **0** campos em **0** linhas — **0** delas só na liquidação (funding) e **0** campos de trajetória.

Divergência **só de liquidação** é compatível com um settlement de funding ingerido depois de o outcome ter sido liquidado: a mesma trajetória, o mesmo `r_ex_funding`, e um `R_net` que muda porque hoje existe uma linha em `funding_rates` que não existia quando o worker fechou as contas. **Compatível, não comprovado**: `funding_rates` não guarda o instante de ingestão, então nada no banco decide *quando* a linha chegou. Divergência de **trajetória** não teria essa desculpa — seria bug de replay, e o portão do passo 1 barra a execução.

## 3. Cobertura e métricas por política

| política | resolvidos | avaliáveis (R_net) | sem entrada | sem resolver | maturados | gatilhos de invalidação | taxa de alvo | taxa de lucro líquido | expectancy líq. (R) | PF |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base | 47 | 47 (sem funding: 0) | 0 | — | 47 | {"invalidation": 23} | 0.533333 (8/15) | 0.319149 | -0.038163 | 0.922028 (den. 23.003680) |
| INV-B | 47 | 47 (sem funding: 0) | 0 | — | 47 | — | 0.310345 (9/29) | 0.425532 | 0.054063 | 1.110099 (den. 23.078878) |

`target2_missing` / `target3_missing` não é falha: `volume_anomaly_v1/v2` persiste um único alvo, então os braços de alvo (L1) só existem para `momentum` — os contrastes `TGT-3 − base` e `TGT-4.5 − base` correm sobre uma subpopulação diferente dos demais, e isso não é comparável linha a linha com os outros cinco.

## 4. Os sete contrastes (pareados por sinal)

| contraste | pares | blocos | Δ médio R_net | IC 95% (blocos) | p | p Holm | rejeita? | abs(Δ) ≥ efeito mín. |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| INV-B - base | 47 | 14 | 0.092226 | [-0.0618, 0.2151] | 0.264587 | 1.000000 | não | sim |
| INV-C - base | 0 | 0 | — | — (no_pairs) | — | — | não | não |
| INV-E - base | 0 | 0 | — | — (no_pairs) | — | — | não | não |
| TGT-3 - base | 0 | 0 | — | — (no_pairs) | — | — | não | não |
| TGT-4.5 - base | 0 | 0 | — | — (no_pairs) | — | — | não | não |
| EXIT-NOTGT - base | 0 | 0 | — | — (no_pairs) | — | — | não | não |
| EXIT-CHAN - EXIT-NOTGT | 0 | 0 | — | — (no_pairs) | — | — | não | não |

Sensibilidade sem funding (`r_ex_funding`, cobertura própria):

| contraste | pares | Δ médio | IC 95% |
| --- | --- | --- | --- |
| INV-B - base | 47 | 0.093020 | [-0.0616, 0.2166] |
| INV-C - base | 0 | — | — |
| INV-E - base | 0 | — | — |
| TGT-3 - base | 0 | — | — |
| TGT-4.5 - base | 0 | — | — |
| EXIT-NOTGT - base | 0 | — | — |
| EXIT-CHAN - EXIT-NOTGT | 0 | — | — |

## 5. O que é inconclusivo, e por quê

**Portão do passo 1:** passou — reprodução de trajetória 1.0000 sobre 47 linhas comparáveis (limiar 0.9900); reprodução completa 1.0000; 0 linhas divergiram **só na liquidação**. Os contrastes abaixo só existem porque esse portão passou.

Outcomes da base com horizonte **maturado** no corte: **47** (avaliáveis com `R_net`: 47; limiar 100); dias distintos: **14** (limiar 30). Veredito editorial: **inconclusive**.

Com menos de 100 outcomes maduros ou menos de 30 dias distintos o resultado é **inconclusivo por contrato** (SHADOW-LAB.md §9). O que este piloto entrega é **aprendizado operacional** — quanto do acompanhamento real o replay reproduz *nesta leitura*, quanta cobertura cada política tem e qual é a ordem de grandeza das diferenças —, **não confirmação**. Os p-valores são exploratórios: vêm de inversão de sinal por blocos de dia, cuja validade exige simetria dos efeitos de bloco que nada aqui estabeleceu; com poucos blocos o menor p atingível já é maior que o limiar de Holm, e com um único bloco o teste devolve `p = 1` **por construção** — o que não é evidência de equivalência, é ausência de replicação.

