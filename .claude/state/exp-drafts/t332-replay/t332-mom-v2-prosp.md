# R1 — Replay de políticas de saída sobre as entradas congeladas (EXP-0004)

**SOMBRA — hipotético, sem capital, custos assumidos.** `purpose=research_only`; nada foi ativado, nada ordena, nenhuma tabela do Lab foi escrita.

- `as_of` (corte de dados, não só de população): `2026-09-08T15:00:00+00:00`
- `input_digest`: `70b5ee97a59a5bda` (registros lidos) · `series_digest`: `128d3b1119e36c70` (velas dobradas). O Lab continua escrevendo; duas execuções só são comparáveis com os mesmos dois dígitos.
- **Limite declarado:** o corte `as_of` vale para as velas; o funding é lido `as_stored_at_read_time`, porque quem consulta `funding_rates` é o `settle` de produção, reusado verbatim. Uma linha de funding ingerida depois do corte é visível à liquidação — é exatamente o que as divergências da §2 mostram.
- semente: `20260906` · reamostras: `10000` · família Holm: `7` · efeito mínimo declarado: `0.05 R`
- políticas: base, INV-B, INV-C, INV-E, TGT-3, TGT-4.5, EXIT-NOTGT, EXIT-CHAN

## 1. Manifesto e população

| strategy_version_id | versão | params_hash | ativada em |
| --- | --- | --- | --- |
| 3e655c2a-4ef1-492b-ae80-46ec6f26321c | momentum_v2 | 40e1688e6b5f6385 | 2026-09-08T04:33:56.865371+00:00 |

| versão | terminal | no_entry |
| --- | --- | --- |
| momentum_v2 | 210 | 0 |

## 2. Reprodução da base (passo 1)

| versão | linhas | comparáveis | reproduzidos | divergentes | late | sem resolver | taxa (tudo) | taxa (trajetória) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| momentum_v2 | 210 | 202 | 202 | 0 | 0 | 8 | 1.0000 | 1.0000 |

Divergências: **0** campos em **0** linhas — **0** delas só na liquidação (funding) e **0** campos de trajetória.

Divergência **só de liquidação** é compatível com um settlement de funding ingerido depois de o outcome ter sido liquidado: a mesma trajetória, o mesmo `r_ex_funding`, e um `R_net` que muda porque hoje existe uma linha em `funding_rates` que não existia quando o worker fechou as contas. **Compatível, não comprovado**: `funding_rates` não guarda o instante de ingestão, então nada no banco decide *quando* a linha chegou. Divergência de **trajetória** não teria essa desculpa — seria bug de replay, e o portão do passo 1 barra a execução.

## 3. Cobertura e métricas por política

| política | resolvidos | avaliáveis (R_net) | sem entrada | sem resolver | maturados | gatilhos de invalidação | taxa de alvo | taxa de lucro líquido | expectancy líq. (R) | PF |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base | 202 | 189 (sem funding: 13) | 0 | {"immature": 8} | 152 | {"invalidation": 72} | 0.565891 (73/129) | 0.365079 | -0.185984 | 0.636160 (den. 96.611253) |
| INV-B | 198 | 185 (sem funding: 13) | 0 | {"immature": 12} | 152 | — | 0.435897 (85/195) | 0.437838 | -0.216072 | 0.648444 (den. 113.704071) |
| INV-C | 199 | 185 (sem funding: 14) | 0 | {"immature": 11} | 152 | {"two_closes": 36} | 0.490683 (79/161) | 0.410811 | -0.196644 | 0.647675 (den. 103.254535) |
| INV-E | 200 | 187 (sem funding: 13) | 0 | {"immature": 10} | 152 | {"invalidation": 45} | 0.496732 (76/153) | 0.385027 | -0.219551 | 0.611308 (den. 105.626198) |
| TGT-3 | 192 | 180 (sem funding: 12) | 0 | {"gap": 1, "immature": 17} | 152 | {"invalidation": 83} | 0.359223 (37/103) | 0.227778 | -0.190632 | 0.694538 (den. 112.334315) |
| TGT-4.5 | 191 | 179 (sem funding: 12) | 0 | {"gap": 1, "immature": 18} | 152 | {"invalidation": 86} | 0.239583 (23/96) | 0.167598 | -0.296272 | 0.565495 (den. 122.053255) |
| EXIT-NOTGT | 183 | 171 (sem funding: 12) | 0 | {"gap": 1, "immature": 26} | 152 | {"invalidation": 87} | 0.000000 (0/74) | 0.116959 | -0.509359 | 0.298423 (den. 124.149517) |
| EXIT-CHAN | 183 | 171 (sem funding: 12) | 0 | {"gap": 1, "immature": 26} | 152 | {"channel": 15, "invalidation": 85} | 0.000000 (0/71) | 0.099415 | -0.506409 | 0.297220 (den. 123.219199) |

`target2_missing` / `target3_missing` não é falha: `volume_anomaly_v1/v2` persiste um único alvo, então os braços de alvo (L1) só existem para `momentum` — os contrastes `TGT-3 − base` e `TGT-4.5 − base` correm sobre uma subpopulação diferente dos demais, e isso não é comparável linha a linha com os outros cinco.

## 4. Os sete contrastes (pareados por sinal)

| contraste | pares | blocos | Δ médio R_net | IC 95% (blocos) | p | p Holm | rejeita? | abs(Δ) ≥ efeito mín. |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| INV-B - base | 141 | 1 | -0.069672 | — (single_block) | 1.000000 | 1.000000 | não | sim |
| INV-C - base | 140 | 1 | -0.046780 | — (single_block) | 1.000000 | 1.000000 | não | não |
| INV-E - base | 141 | 1 | -0.061901 | — (single_block) | 1.000000 | 1.000000 | não | sim |
| TGT-3 - base | 140 | 1 | 0.008242 | — (single_block) | 1.000000 | 1.000000 | não | não |
| TGT-4.5 - base | 140 | 1 | -0.137966 | — (single_block) | 1.000000 | 1.000000 | não | sim |
| EXIT-NOTGT - base | 140 | 1 | -0.225515 | — (single_block) | 1.000000 | 1.000000 | não | sim |
| EXIT-CHAN - EXIT-NOTGT | 140 | 1 | 0.003603 | — (single_block) | 1.000000 | 1.000000 | não | não |

Sensibilidade sem funding (`r_ex_funding`, cobertura própria):

| contraste | pares | Δ médio | IC 95% |
| --- | --- | --- | --- |
| INV-B - base | 152 | -0.075110 | — |
| INV-C - base | 152 | -0.051200 | — |
| INV-E - base | 152 | -0.064370 | — |
| TGT-3 - base | 151 | -0.010065 | — |
| TGT-4.5 - base | 151 | -0.149817 | — |
| EXIT-NOTGT - base | 151 | -0.235954 | — |
| EXIT-CHAN - EXIT-NOTGT | 151 | 0.002169 | — |

## 5. O que é inconclusivo, e por quê

**Portão do passo 1:** passou — reprodução de trajetória 1.0000 sobre 202 linhas comparáveis (limiar 0.9900); reprodução completa 1.0000; 0 linhas divergiram **só na liquidação**. Os contrastes abaixo só existem porque esse portão passou.

Outcomes da base com horizonte **maturado** no corte: **152** (avaliáveis com `R_net`: 189; limiar 100); dias distintos: **1** (limiar 30). Veredito editorial: **inconclusive**.

Com menos de 100 outcomes maduros ou menos de 30 dias distintos o resultado é **inconclusivo por contrato** (SHADOW-LAB.md §9). O que este piloto entrega é **aprendizado operacional** — quanto do acompanhamento real o replay reproduz *nesta leitura*, quanta cobertura cada política tem e qual é a ordem de grandeza das diferenças —, **não confirmação**. Os p-valores são exploratórios: vêm de inversão de sinal por blocos de dia, cuja validade exige simetria dos efeitos de bloco que nada aqui estabeleceu; com poucos blocos o menor p atingível já é maior que o limiar de Holm, e com um único bloco o teste devolve `p = 1` **por construção** — o que não é evidência de equivalência, é ausência de replicação.

