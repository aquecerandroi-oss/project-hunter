# R1 — Replay de políticas de saída sobre as entradas congeladas (EXP-0004)

**SOMBRA — hipotético, sem capital, custos assumidos.** `purpose=research_only`; nada foi ativado, nada ordena, nenhuma tabela do Lab foi escrita.

- `as_of` (corte de dados, não só de população): `2026-09-08T04:00:00+00:00`
- `input_digest`: `6000867c3df37418` (registros lidos) · `series_digest`: `3bd45752b9f8bc3d` (velas dobradas). O Lab continua escrevendo; duas execuções só são comparáveis com os mesmos dois dígitos.
- **Limite declarado:** o corte `as_of` vale para as velas; o funding é lido `as_stored_at_read_time`, porque quem consulta `funding_rates` é o `settle` de produção, reusado verbatim. Uma linha de funding ingerida depois do corte é visível à liquidação — é exatamente o que as divergências da §2 mostram.
- semente: `20260906` · reamostras: `10000` · família Holm: `7` · efeito mínimo declarado: `0.05 R`
- políticas: base, INV-B, INV-C, INV-E, TGT-3, TGT-4.5, EXIT-NOTGT, EXIT-CHAN

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
| INV-B | 224 | 223 (sem funding: 1) | 0 | — | 224 | — | 0.521327 (110/211) | 0.497758 | -0.179953 | 0.675450 (den. 123.647065) |
| INV-C | 224 | 222 (sem funding: 2) | 0 | — | 224 | {"two_closes": 47} | 0.588235 (100/170) | 0.454955 | -0.165084 | 0.675591 (den. 112.970314) |
| INV-E | 224 | 222 (sem funding: 2) | 0 | — | 224 | {"invalidation": 64} | 0.649351 (100/154) | 0.454955 | -0.151930 | 0.693934 (den. 110.200079) |
| TGT-3 | 224 | 223 (sem funding: 1) | 0 | — | 224 | {"invalidation": 95} | 0.539823 (61/113) | 0.318386 | -0.063129 | 0.886311 (den. 123.828209) |
| TGT-4.5 | 224 | 223 (sem funding: 1) | 0 | — | 224 | {"invalidation": 95} | 0.382979 (36/94) | 0.286996 | -0.055078 | 0.906273 (den. 131.045140) |
| EXIT-NOTGT | 224 | 223 (sem funding: 1) | 0 | — | 224 | {"invalidation": 97} | 0.000000 (0/63) | 0.251121 | -0.005443 | 0.991224 (den. 138.307103) |
| EXIT-CHAN | 224 | 223 (sem funding: 1) | 0 | — | 224 | {"channel": 21, "invalidation": 97} | 0.000000 (0/58) | 0.237668 | -0.018788 | 0.968968 (den. 135.012777) |

`target2_missing` / `target3_missing` não é falha: `volume_anomaly_v1/v2` persiste um único alvo, então os braços de alvo (L1) só existem para `momentum` — os contrastes `TGT-3 − base` e `TGT-4.5 − base` correm sobre uma subpopulação diferente dos demais, e isso não é comparável linha a linha com os outros cinco.

## 4. Os sete contrastes (pareados por sinal)

| contraste | pares | blocos | Δ médio R_net | IC 95% (blocos) | p | p Holm | rejeita? | abs(Δ) ≥ efeito mín. |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| INV-B - base | 222 | 24 | -0.006247 | [-0.0846, 0.0725] | 0.889306 | 1.000000 | não | não |
| INV-C - base | 221 | 24 | 0.006493 | [-0.0336, 0.0467] | 0.767562 | 1.000000 | não | não |
| INV-E - base | 222 | 24 | 0.019809 | [-0.0273, 0.0664] | 0.458227 | 1.000000 | não | não |
| TGT-3 - base | 222 | 24 | 0.103606 | [-0.0112, 0.2053] | 0.118694 | 0.830858 | não | sim |
| TGT-4.5 - base | 222 | 24 | 0.113629 | [-0.0875, 0.3184] | 0.331683 | 1.000000 | não | sim |
| EXIT-NOTGT - base | 222 | 24 | 0.163487 | [-0.2184, 0.5871] | 0.508275 | 1.000000 | não | sim |
| EXIT-CHAN - EXIT-NOTGT | 223 | 24 | -0.013345 | [-0.0403, 0.0109] | 0.374081 | 1.000000 | não | não |

Sensibilidade sem funding (`r_ex_funding`, cobertura própria):

| contraste | pares | Δ médio | IC 95% |
| --- | --- | --- | --- |
| INV-B - base | 224 | -0.006405 | [-0.0837, 0.0713] |
| INV-C - base | 224 | 0.005323 | [-0.0346, 0.0457] |
| INV-E - base | 224 | 0.019633 | [-0.0271, 0.0659] |
| TGT-3 - base | 224 | 0.106461 | [-0.0079, 0.2074] |
| TGT-4.5 - base | 224 | 0.114825 | [-0.0842, 0.3189] |
| EXIT-NOTGT - base | 224 | 0.165168 | [-0.2126, 0.5865] |
| EXIT-CHAN - EXIT-NOTGT | 224 | -0.013286 | [-0.0401, 0.0108] |

## 5. O que é inconclusivo, e por quê

**Portão do passo 1:** passou — reprodução de trajetória 1.0000 sobre 224 linhas comparáveis (limiar 0.9900); reprodução completa 1.0000; 0 linhas divergiram **só na liquidação**. Os contrastes abaixo só existem porque esse portão passou.

Outcomes da base com horizonte **maturado** no corte: **224** (avaliáveis com `R_net`: 222; limiar 100); dias distintos: **24** (limiar 30). Veredito editorial: **inconclusive**.

Com menos de 100 outcomes maduros ou menos de 30 dias distintos o resultado é **inconclusivo por contrato** (SHADOW-LAB.md §9). O que este piloto entrega é **aprendizado operacional** — quanto do acompanhamento real o replay reproduz *nesta leitura*, quanta cobertura cada política tem e qual é a ordem de grandeza das diferenças —, **não confirmação**. Os p-valores são exploratórios: vêm de inversão de sinal por blocos de dia, cuja validade exige simetria dos efeitos de bloco que nada aqui estabeleceu; com poucos blocos o menor p atingível já é maior que o limiar de Holm, e com um único bloco o teste devolve `p = 1` **por construção** — o que não é evidência de equivalência, é ausência de replicação.

