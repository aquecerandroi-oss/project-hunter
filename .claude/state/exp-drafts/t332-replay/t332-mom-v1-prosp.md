# R1 — Replay de políticas de saída sobre as entradas congeladas (EXP-0004)

**SOMBRA — hipotético, sem capital, custos assumidos.** `purpose=research_only`; nada foi ativado, nada ordena, nenhuma tabela do Lab foi escrita.

- `as_of` (corte de dados, não só de população): `2026-09-08T15:00:00+00:00`
- `input_digest`: `98a1ffd048090c69` (registros lidos) · `series_digest`: `dfeb03c4200a41e8` (velas dobradas). O Lab continua escrevendo; duas execuções só são comparáveis com os mesmos dois dígitos.
- **Limite declarado:** o corte `as_of` vale para as velas; o funding é lido `as_stored_at_read_time`, porque quem consulta `funding_rates` é o `settle` de produção, reusado verbatim. Uma linha de funding ingerida depois do corte é visível à liquidação — é exatamente o que as divergências da §2 mostram.
- semente: `20260906` · reamostras: `10000` · família Holm: `7` · efeito mínimo declarado: `0.05 R`
- políticas: base, INV-B, INV-C, INV-E, TGT-3, TGT-4.5, EXIT-NOTGT, EXIT-CHAN

## 1. Manifesto e população

| strategy_version_id | versão | params_hash | ativada em |
| --- | --- | --- | --- |
| 01a074c5-8f1d-7a75-a88b-2badb6a5dd67 | momentum_v1 | 40e1688e6b5f6385 | 2026-09-06T03:36:36.988581+00:00 |

| versão | terminal | no_entry |
| --- | --- | --- |
| momentum_v1 | 947 | 16 |

## 2. Reprodução da base (passo 1)

| versão | linhas | comparáveis | reproduzidos | divergentes | late | sem resolver | taxa (tudo) | taxa (trajetória) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| momentum_v1 | 963 | 948 | 915 | 33 | 15 | 0 | 0.9652 | 1.0000 |

Divergências: **37** campos em **33** linhas — **33** delas só na liquidação (funding) e **0** campos de trajetória.

Divergência **só de liquidação** é compatível com um settlement de funding ingerido depois de o outcome ter sido liquidado: a mesma trajetória, o mesmo `r_ex_funding`, e um `R_net` que muda porque hoje existe uma linha em `funding_rates` que não existia quando o worker fechou as contas. **Compatível, não comprovado**: `funding_rates` não guarda o instante de ingestão, então nada no banco decide *quando* a linha chegou. Divergência de **trajetória** não teria essa desculpa — seria bug de replay, e o portão do passo 1 barra a execução.

| signal_id | tipo | campo | gravado | replay |
| --- | --- | --- | --- | --- |
| 0b0320ec-cc76-5242-813b-4301c3e518e1 | settlement | r_multiple | -1.0354612114 | -1.0354611987 |
| 1513666a-ae40-5c03-a201-a75d208d2a1a | settlement | r_multiple | 1.2317421618 | 1.2317421641 |
| 1ae107dc-ae6f-580b-ba31-f8d5a67be7fd | settlement | r_multiple | -1.0462152670 | -1.0462152091 |
| 205bed64-89e9-5335-8c62-73d9983d887e | settlement | r_multiple | 0.2440528484 | 0.2440528487 |
| 210f2ef7-a7ee-552b-bec3-18ebb49fbb85 | settlement | r_multiple | 0.9533894448 | 0.9533895057 |
| 2488f297-4e78-572a-b338-0b4499444f7a | settlement | r_multiple | 1.0840919040 | 1.0840921002 |
| 30d9ad62-1bed-536d-8c93-f1d3f004f4a2 | settlement | r_multiple | — | -1.1184471715 |
| 30d9ad62-1bed-536d-8c93-f1d3f004f4a2 | settlement | funding_reason | funding_missing:2026-09-07T18:00:00.002000+00:00 | — |
| 331e428b-8cbf-55fd-961e-32c9b19c043f | settlement | r_multiple | 0.7199657215 | 0.7199650175 |
| 403833b5-6475-5228-9ad8-8fb7a71e75cd | settlement | r_multiple | 0.4184246678 | 0.4184245794 |
| 411fbf7f-295f-5e0e-a9b0-c2d627f7cbc9 | settlement | r_multiple | -1.1473406468 | -1.1473406456 |
| 45d29a2d-f3ff-50a3-9d2c-6ab25702c743 | settlement | r_multiple | — | 1.0805936114 |
| 45d29a2d-f3ff-50a3-9d2c-6ab25702c743 | settlement | funding_reason | funding_ambiguous_exit | — |
| 49f540d8-7767-56e4-a8c6-c8945bcee16d | settlement | r_multiple | -1.0967829384 | -1.0967829939 |
| 4ac19444-e0bf-5528-aadf-e0ad45cfe6bd | settlement | r_multiple | -1.0079032105 | -1.0108431836 |
| 547439ed-f1ca-5149-b557-4a9d85871d36 | settlement | r_multiple | 1.0602612445 | 1.0602612479 |
| 66a81ca5-69a8-5a5c-a3b9-438c35ab8edd | settlement | r_multiple | -0.7473759134 | -0.7494520419 |
| 6969f328-1008-57d7-8172-c658e7085774 | settlement | r_multiple | 1.3297642271 | 1.3297642291 |
| 6ec17c3a-d2a1-575f-b735-05460d5c6762 | settlement | r_multiple | -0.9898761054 | -0.9966749213 |
| 7585bf92-78fd-5918-a12b-97209b1313e2 | settlement | r_multiple | 0.8148859824 | 0.8148860243 |
| 80e92ba6-0e2f-5193-8146-b6fd6f23fd2b | settlement | r_multiple | 0.9714510350 | 0.9714510258 |
| a55555d2-a97a-53a5-8516-d6923f52a10f | settlement | r_multiple | 0.7589355113 | 0.7589354530 |
| aaa69a43-bca5-5369-b2f7-6c536450e8d5 | settlement | r_multiple | -1.1227037950 | -1.1227037548 |
| bafbf982-1574-5f99-b448-8f9d190ea6cd | settlement | r_multiple | — | 0.4766051620 |
| bafbf982-1574-5f99-b448-8f9d190ea6cd | settlement | funding_reason | funding_missing:2026-09-07T16:00:00+00:00 | — |
| bc0c5138-a140-5070-93f4-136622496a67 | settlement | r_multiple | 0.3610522989 | 0.3610522821 |
| bfaf9cf6-7268-5e3d-8211-b17bb0739e79 | settlement | r_multiple | 0.7551633847 | 0.7551633968 |
| c1fbc84e-c9c4-5c42-b7b1-9b4084169840 | settlement | r_multiple | 0.7230755189 | 0.7230755133 |
| c7357dd2-60ca-5f46-940e-7ee7b915f188 | settlement | r_multiple | -0.6359044325 | -0.6392826303 |
| ca6b3408-da61-5964-a344-cf2210d164ef | settlement | r_multiple | 0.4970225155 | 0.4970225151 |
| cd481e10-7a7f-522d-99bf-38fc6e6bf2bd | settlement | r_multiple | -1.0182943748 | -1.0182943457 |
| d26fc239-62bc-56c0-9329-2b61f6f6ec40 | settlement | r_multiple | 0.8876078404 | 0.8876078396 |
| df6114c8-e32b-5edf-85e7-bdee341aa56c | settlement | r_multiple | — | -0.7975324015 |
| df6114c8-e32b-5edf-85e7-bdee341aa56c | settlement | funding_reason | funding_missing:2026-09-07T12:00:00+00:00 | — |
| e251a6f4-2c0e-59c6-8097-abcc927eaebf | settlement | funding_reason | funding_missing:2026-09-06T11:59:59+00:00 | funding_missing:2026-09-06T12:00:00+00:00 |
| eb556cfe-2d40-58ae-9842-bb30c5396cf8 | settlement | r_multiple | -1.0419001881 | -1.0419002310 |
| fc3ccdf4-36c7-5e9f-b437-00aeef9a19d9 | settlement | r_multiple | 1.0889807100 | 1.0889807065 |

## 3. Cobertura e métricas por política

| política | resolvidos | avaliáveis (R_net) | sem entrada | sem resolver | maturados | gatilhos de invalidação | taxa de alvo | taxa de lucro líquido | expectancy líq. (R) | PF |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base | 947 | 933 (sem funding: 14) | 16 | — | 963 | {"invalidation": 353} | 0.600677 (355/591) | 0.386924 | -0.190043 | 0.613872 (den. 459.199497) |
| INV-B | 947 | 941 (sem funding: 6) | 16 | — | 963 | — | 0.456710 (422/924) | 0.453773 | -0.234476 | 0.607274 (den. 561.821729) |
| INV-C | 947 | 941 (sem funding: 6) | 16 | — | 963 | {"two_closes": 168} | 0.503896 (388/770) | 0.416578 | -0.226952 | 0.593058 (den. 524.797968) |
| INV-E | 947 | 937 (sem funding: 10) | 16 | — | 963 | {"invalidation": 258} | 0.562408 (383/681) | 0.411953 | -0.201574 | 0.619847 (den. 496.839103) |
| TGT-3 | 946 | 932 (sem funding: 14) | 16 | {"gap": 1} | 963 | {"invalidation": 416} | 0.396761 (196/494) | 0.245708 | -0.209630 | 0.656155 (den. 568.206461) |
| TGT-4.5 | 945 | 932 (sem funding: 13) | 16 | {"gap": 2} | 963 | {"invalidation": 433} | 0.286364 (126/440) | 0.206009 | -0.206375 | 0.678029 (den. 597.386378) |
| EXIT-NOTGT | 944 | 930 (sem funding: 14) | 16 | {"gap": 3} | 963 | {"invalidation": 439} | 0.000000 (0/333) | 0.173118 | -0.298129 | 0.555730 (den. 624.079079) |
| EXIT-CHAN | 944 | 929 (sem funding: 15) | 16 | {"gap": 3} | 963 | {"channel": 81, "invalidation": 432} | 0.000000 (0/309) | 0.164693 | -0.289060 | 0.558695 (den. 608.506307) |

`target2_missing` / `target3_missing` não é falha: `volume_anomaly_v1/v2` persiste um único alvo, então os braços de alvo (L1) só existem para `momentum` — os contrastes `TGT-3 − base` e `TGT-4.5 − base` correm sobre uma subpopulação diferente dos demais, e isso não é comparável linha a linha com os outros cinco.

## 4. Os sete contrastes (pareados por sinal)

| contraste | pares | blocos | Δ médio R_net | IC 95% (blocos) | p | p Holm | rejeita? | abs(Δ) ≥ efeito mín. |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| INV-B - base | 932 | 3 | -0.038225 | [-0.0726, -0.0291] | 0.250000 | 1.000000 | não | não |
| INV-C - base | 932 | 3 | -0.031328 | [-0.0851, -0.0156] | 0.250000 | 1.000000 | não | não |
| INV-E - base | 933 | 3 | -0.009144 | [-0.0466, 0.0053] | 0.500000 | 1.000000 | não | não |
| TGT-3 - base | 930 | 3 | -0.018433 | [-0.0310, 0.0005] | 0.500000 | 1.000000 | não | não |
| TGT-4.5 - base | 930 | 3 | -0.012514 | [-0.0542, 0.0270] | 0.750000 | 1.000000 | não | não |
| EXIT-NOTGT - base | 928 | 3 | -0.101986 | [-0.1156, -0.0488] | 0.250000 | 1.000000 | não | sim |
| EXIT-CHAN - EXIT-NOTGT | 929 | 3 | 0.010679 | [0.0055, 0.0166] | 0.250000 | 1.000000 | não | não |

Sensibilidade sem funding (`r_ex_funding`, cobertura própria):

| contraste | pares | Δ médio | IC 95% |
| --- | --- | --- | --- |
| INV-B - base | 947 | -0.039775 | [-0.0719, -0.0333] |
| INV-C - base | 947 | -0.032907 | [-0.0842, -0.0188] |
| INV-E - base | 947 | -0.010053 | [-0.0462, 0.0038] |
| TGT-3 - base | 946 | -0.021051 | [-0.0305, -0.0057] |
| TGT-4.5 - base | 945 | -0.018637 | [-0.0601, 0.0215] |
| EXIT-NOTGT - base | 944 | -0.108464 | [-0.1236, -0.0558] |
| EXIT-CHAN - EXIT-NOTGT | 944 | 0.009888 | [0.0052, 0.0165] |

## 5. O que é inconclusivo, e por quê

**Portão do passo 1:** passou — reprodução de trajetória 1.0000 sobre 948 linhas comparáveis (limiar 0.9900); reprodução completa 0.9652; 33 linhas divergiram **só na liquidação**. Os contrastes abaixo só existem porque esse portão passou.

Outcomes da base com horizonte **maturado** no corte: **963** (avaliáveis com `R_net`: 933; limiar 100); dias distintos: **3** (limiar 30). Veredito editorial: **inconclusive**.

Com menos de 100 outcomes maduros ou menos de 30 dias distintos o resultado é **inconclusivo por contrato** (SHADOW-LAB.md §9). O que este piloto entrega é **aprendizado operacional** — quanto do acompanhamento real o replay reproduz *nesta leitura*, quanta cobertura cada política tem e qual é a ordem de grandeza das diferenças —, **não confirmação**. Os p-valores são exploratórios: vêm de inversão de sinal por blocos de dia, cuja validade exige simetria dos efeitos de bloco que nada aqui estabeleceu; com poucos blocos o menor p atingível já é maior que o limiar de Holm, e com um único bloco o teste devolve `p = 1` **por construção** — o que não é evidência de equivalência, é ausência de replicação.

