# R1 — Replay de políticas de saída sobre as entradas congeladas (EXP-0004)

**SOMBRA — hipotético, sem capital, custos assumidos.** `purpose=research_only`; nada foi ativado, nada ordena, nenhuma tabela do Lab foi escrita.

- `as_of` (corte de dados, não só de população): `2026-09-06T20:55:00+00:00`
- `input_digest`: `8b9cb982f7caec12` (registros lidos) · `series_digest`: `759c1f5e60a522b8` (velas dobradas). O Lab continua escrevendo; duas execuções só são comparáveis com os mesmos dois dígitos.
- **Limite declarado:** o corte `as_of` vale para as velas; o funding é lido `as_stored_at_read_time`, porque quem consulta `funding_rates` é o `settle` de produção, reusado verbatim. Uma linha de funding ingerida depois do corte é visível à liquidação — é exatamente o que as divergências da §2 mostram.
- semente: `20260906` · reamostras: `10000` · família Holm: `7` · efeito mínimo declarado: `0.05 R`
- políticas: base, INV-B, INV-C, INV-E, TGT-3, TGT-4.5, EXIT-NOTGT, EXIT-CHAN

## 1. Manifesto e população

| strategy_version_id | versão | params_hash | ativada em |
| --- | --- | --- | --- |
| 01a073de-89b8-7f70-8b8a-1a7a08be5dcb | momentum_v1 | 40e1688e6b5f6385 | 2026-09-05T23:19:56.334638+00:00 |
| 098b060c-cdc0-46a6-b88b-70d4a5472b97 | momentum_v2 | 40e1688e6b5f6385 | 2026-09-06T02:08:13.332014+00:00 |
| 01a073de-8a07-76c3-92fc-0f712aee63da | volume_anomaly_v1 | fa5dce78173b2b96 | 2026-09-05T23:20:09.899561+00:00 |
| d6442b18-6e2d-4efd-afac-180edc3981bd | volume_anomaly_v2 | fa5dce78173b2b96 | 2026-09-06T02:08:19.424473+00:00 |

| versão | terminal | no_entry |
| --- | --- | --- |
| momentum_v1 | 65 | 5 |
| momentum_v2 | 74 | 6 |
| volume_anomaly_v1 | 79 | 12 |
| volume_anomaly_v2 | 125 | 11 |

## 2. Reprodução da base (passo 1)

| versão | linhas | comparáveis | reproduzidos | divergentes | late | sem resolver | taxa (tudo) | taxa (trajetória) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| momentum_v1 | 70 | 65 | 65 | 0 | 5 | 0 | 1.0000 | 1.0000 |
| momentum_v2 | 80 | 69 | 64 | 5 | 6 | 5 | 0.9275 | 1.0000 |
| volume_anomaly_v1 | 91 | 82 | 82 | 0 | 9 | 0 | 1.0000 | 1.0000 |
| volume_anomaly_v2 | 136 | 123 | 114 | 9 | 5 | 8 | 0.9268 | 1.0000 |

Divergências: **27** campos em **14** linhas — **14** delas só na liquidação (funding) e **0** campos de trajetória.

Divergência **só de liquidação** é compatível com um settlement de funding ingerido depois de o outcome ter sido liquidado: a mesma trajetória, o mesmo `r_ex_funding`, e um `R_net` que muda porque hoje existe uma linha em `funding_rates` que não existia quando o worker fechou as contas. **Compatível, não comprovado**: `funding_rates` não guarda o instante de ingestão, então nada no banco decide *quando* a linha chegou. Divergência de **trajetória** não teria essa desculpa — seria bug de replay, e o portão do passo 1 barra a execução.

| signal_id | tipo | campo | gravado | replay |
| --- | --- | --- | --- | --- |
| 7f76892c-674c-5145-9eaa-be371c1720f4 | settlement | r_multiple | — | -1.0462152091 |
| 7f76892c-674c-5145-9eaa-be371c1720f4 | settlement | funding_reason | funding_missing:2026-09-06T19:59:59.004000+00:00 | — |
| 88b49c3f-e544-525a-bf87-b5b692a69475 | settlement | r_multiple | — | 1.0857007862 |
| 88b49c3f-e544-525a-bf87-b5b692a69475 | settlement | funding_reason | funding_missing:2026-09-06T19:59:59.004000+00:00 | — |
| b2c269f0-12ce-53ad-b581-4c7e9504daa7 | settlement | r_multiple | — | -1.1765438247 |
| b2c269f0-12ce-53ad-b581-4c7e9504daa7 | settlement | funding_reason | funding_missing:2026-09-06T20:00:00.004000+00:00 | — |
| d87f16cd-9202-5bed-8543-a954813a5d09 | settlement | r_multiple | — | -0.9735903759 |
| d87f16cd-9202-5bed-8543-a954813a5d09 | settlement | funding_reason | funding_missing:2026-09-06T20:00:00.004000+00:00 | — |
| dd1a5e08-3a2a-59e5-a49a-24b2efa3cc91 | settlement | r_multiple | — | 0.7836282146 |
| dd1a5e08-3a2a-59e5-a49a-24b2efa3cc91 | settlement | funding_reason | funding_missing:2026-09-06T20:00:00.004000+00:00 | — |
| 28fcaa2f-58c2-52e1-9b51-c9685b6d0d5f | settlement | r_multiple | — | -1.2288400340 |
| 28fcaa2f-58c2-52e1-9b51-c9685b6d0d5f | settlement | funding_reason | funding_missing:2026-09-06T20:00:00.004000+00:00 | — |
| 4bf70ade-2947-5ee3-b089-3dda1f681214 | settlement | r_multiple | — | 2.3252364801 |
| 4bf70ade-2947-5ee3-b089-3dda1f681214 | settlement | funding_reason | funding_missing:2026-09-06T20:00:00.004000+00:00 | — |
| 5b027f70-69c0-558d-88bc-ac8ef82df2e9 | settlement | r_multiple | -0.8112908472 | -0.8263601960 |
| 7263e927-6e2a-5fcb-a78b-a43112c46050 | settlement | r_multiple | — | 1.2320173388 |
| 7263e927-6e2a-5fcb-a78b-a43112c46050 | settlement | funding_reason | funding_missing:2026-09-06T20:00:00.004000+00:00 | — |
| 7677dff5-3673-5e5b-b866-db2319c8df7f | settlement | r_multiple | — | 0.6810470770 |
| 7677dff5-3673-5e5b-b866-db2319c8df7f | settlement | funding_reason | funding_missing:2026-09-06T20:00:00.004000+00:00 | — |
| 818b144b-cec3-526e-9828-2b76d59c2723 | settlement | r_multiple | — | -1.0935309418 |
| 818b144b-cec3-526e-9828-2b76d59c2723 | settlement | funding_reason | funding_missing:2026-09-06T19:59:59.004000+00:00 | — |
| 90493b7f-6366-5639-8161-e7e23ebcfc5c | settlement | r_multiple | — | -0.4113374882 |
| 90493b7f-6366-5639-8161-e7e23ebcfc5c | settlement | funding_reason | funding_missing:2026-09-06T20:00:00.004000+00:00 | — |
| bd1a6f5f-f3f7-5fa3-bfaa-0bd7fdbb8ed4 | settlement | r_multiple | — | 1.6937183239 |
| bd1a6f5f-f3f7-5fa3-bfaa-0bd7fdbb8ed4 | settlement | funding_reason | funding_missing:2026-09-06T20:00:00.004000+00:00 | — |
| e0756b20-31a0-58bc-ab57-a00c310864f0 | settlement | r_multiple | — | -1.0425217833 |
| e0756b20-31a0-58bc-ab57-a00c310864f0 | settlement | funding_reason | funding_missing:2026-09-06T20:00:00.004000+00:00 | — |

## 3. Cobertura e métricas por política

| política | resolvidos | avaliáveis (R_net) | sem entrada | sem resolver | maturados | gatilhos de invalidação | taxa de alvo | taxa de lucro líquido | expectancy líq. (R) | PF |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base | 330 | 330 (sem funding: 0) | 34 | {"immature": 13} | 275 | {"invalidation": 117} | 0.561905 (118/210) | 0.366667 | -0.307218 | 0.578044 (den. 240.266655) |
| INV-B | 316 | 316 (sem funding: 0) | 34 | {"immature": 27} | 275 | — | 0.444444 (136/306) | 0.443038 | -0.307178 | 0.620822 (den. 255.996745) |
| INV-C | 325 | 325 (sem funding: 0) | 34 | {"immature": 18} | 275 | {"two_closes": 46} | 0.481884 (133/276) | 0.415385 | -0.313541 | 0.603035 (den. 256.700064) |
| INV-E | 324 | 324 (sem funding: 0) | 34 | {"immature": 19} | 275 | {"invalidation": 56} | 0.500000 (131/262) | 0.413580 | -0.307003 | 0.606512 (den. 252.787412) |
| TGT-3 | 129 | 127 (sem funding: 2) | 34 | {"immature": 10, "target2_missing": 204} | 275 | {"invalidation": 48} | 0.519481 (40/77) | 0.314961 | 0.002812 | 1.005304 (den. 67.332481) |
| TGT-4.5 | 122 | 120 (sem funding: 2) | 34 | {"gap": 1, "immature": 16, "target3_missing": 204} | 275 | {"invalidation": 50} | 0.360656 (22/61) | 0.216667 | -0.100288 | 0.831473 (den. 71.409878) |
| EXIT-NOTGT | 303 | 299 (sem funding: 4) | 34 | {"gap": 2, "immature": 38} | 275 | {"invalidation": 138} | 0.000000 (0/108) | 0.157191 | -0.393073 | 0.566808 (den. 271.308733) |
| EXIT-CHAN | 303 | 298 (sem funding: 5) | 34 | {"gap": 2, "immature": 38} | 275 | {"channel": 18, "invalidation": 137} | 0.000000 (0/104) | 0.164430 | -0.376021 | 0.578637 (den. 265.932343) |

`target2_missing` / `target3_missing` não é falha: `volume_anomaly_v1/v2` persiste um único alvo, então os braços de alvo (L1) só existem para `momentum` — os contrastes `TGT-3 − base` e `TGT-4.5 − base` correm sobre uma subpopulação diferente dos demais, e isso não é comparável linha a linha com os outros cinco.

## 4. Os sete contrastes (pareados por sinal)

| contraste | pares | blocos | Δ médio R_net | IC 95% (blocos) | p | p Holm | rejeita? | abs(Δ) ≥ efeito mín. |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| INV-B - base | 244 | 1 | -0.010928 | — (single_block) | 1.000000 | 1.000000 | não | não |
| INV-C - base | 244 | 1 | -0.006098 | — (single_block) | 1.000000 | 1.000000 | não | não |
| INV-E - base | 244 | 1 | -0.003127 | — (single_block) | 1.000000 | 1.000000 | não | não |
| TGT-3 - base | 87 | 1 | 0.056216 | — (single_block) | 1.000000 | 1.000000 | não | sim |
| TGT-4.5 - base | 86 | 1 | 0.111738 | — (single_block) | 1.000000 | 1.000000 | não | sim |
| EXIT-NOTGT - base | 238 | 1 | 0.094064 | — (single_block) | 1.000000 | 1.000000 | não | sim |
| EXIT-CHAN - EXIT-NOTGT | 237 | 1 | 0.005228 | — (single_block) | 1.000000 | 1.000000 | não | não |

Sensibilidade sem funding (`r_ex_funding`, cobertura própria):

| contraste | pares | Δ médio | IC 95% |
| --- | --- | --- | --- |
| INV-B - base | 244 | -0.010921 | — |
| INV-C - base | 244 | -0.006106 | — |
| INV-E - base | 244 | -0.003135 | — |
| TGT-3 - base | 89 | 0.019847 | — |
| TGT-4.5 - base | 88 | 0.073841 | — |
| EXIT-NOTGT - base | 242 | 0.066522 | — |
| EXIT-CHAN - EXIT-NOTGT | 242 | 0.009927 | — |

## 5. O que é inconclusivo, e por quê

**Portão do passo 1:** passou — reprodução de trajetória 1.0000 sobre 339 linhas comparáveis (limiar 0.9900); reprodução completa 0.9587; 14 linhas divergiram **só na liquidação**. Os contrastes abaixo só existem porque esse portão passou.

Outcomes da base com horizonte **maturado** no corte: **275** (avaliáveis com `R_net`: 330; limiar 100); dias distintos: **1** (limiar 30). Veredito editorial: **inconclusive**.

Com menos de 100 outcomes maduros ou menos de 30 dias distintos o resultado é **inconclusivo por contrato** (SHADOW-LAB.md §9). O que este piloto entrega é **aprendizado operacional** — quanto do acompanhamento real o replay reproduz *nesta leitura*, quanta cobertura cada política tem e qual é a ordem de grandeza das diferenças —, **não confirmação**. Os p-valores são exploratórios: vêm de inversão de sinal por blocos de dia, cuja validade exige simetria dos efeitos de bloco que nada aqui estabeleceu; com poucos blocos o menor p atingível já é maior que o limiar de Holm, e com um único bloco o teste devolve `p = 1` **por construção** — o que não é evidência de equivalência, é ausência de replicação.

