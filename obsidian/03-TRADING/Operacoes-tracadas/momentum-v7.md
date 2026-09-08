---
tags: [operacoes, momentum, shadow-lab, graficos]
status: em-andamento
owner: quant-engineer
updated: 2026-09-08
strategy: momentum
version: v7
code_ref: hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c
cohort: prospective, replay
as_of: 2026-09-08T23:15:50Z
n: 186
expectancy: -0.0616
---

# momentum v7 — operações traçadas

**186 operação(ões) concluída(s)**, coorte(s) prospective, replay, expectância **-0.0616 R** por operação (média simples de `signal_outcomes.r_multiple`, líquida de custos e funding). Corte da leitura: 08/09/2026 20:15 BRT (23:15Z).

As linhas de tendência destes gráficos são traçadas pelo **mesmo código congelado**
que decide (`hunter_core.strategies.tl_scan`, parâmetros de
`trendline_breakout_v1.default_parameters`), cortado na barra da decisão: nenhuma
vela posterior à decisão participa do traçado. Para toda versão que **não é**
`trendline_breakout_v1`, elas são **contexto calculado depois** — a estratégia não
leu linha nenhuma para decidir. Ver [[Operacoes-tracadas/README]] e [[KB-0076-por-que-perdemos-2026-09-08]].

> [!info] Esta versão **não lê** linhas de tendência para decidir. As linhas abaixo são contexto, nunca entrada da decisão.

**Contrato da hipótese:** `EXP-0018-stop-largo` (T3.47 V1, stop ×1,5 sobre a `momentum v6`) — em redação por outra tarefa, ainda sem nota no vault.

## Tabela

| # | Decisão (BRT) | UTC | Mercado | Coorte | Entrada | Stop | Alvo | Saída | R | Linhas no corte | `line_id` usado | Gráfico |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 001 | 11/08 11:15 | 14:15Z | DOGEUSDT | replay | 0.0713127620 | 0.0706199524 | 0.0720600952 | invalidação | -0.87 | 3 | `—` | [20260811-1415Z-DOGEUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260811-1415Z-DOGEUSDT-invalidated.png) |
| 002 | 11/08 14:00 | 17:00Z | XRPUSDT | replay | 1.0117066600 | 0.9982862004 | 1.0310275991 | invalidação | -0.31 | 4 | `—` | [20260811-1700Z-XRPUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260811-1700Z-XRPUSDT-invalidated.png) |
| 003 | 11/08 17:00 | 20:00Z | ETHUSDT | replay | 1883.1892360000 | 1867.7236995637 | 1908.0626008726 | horizonte | -0.34 | 1 | `—` | [20260811-2000Z-ETHUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260811-2000Z-ETHUSDT-expired.png) |
| 004 | 11/08 17:00 | 20:00Z | DOGEUSDT | replay | 0.0711826840 | 0.0703492439 | 0.0723315121 | alvo | +1.26 | 0 | `—` | [20260811-2000Z-DOGEUSDT-target.png](../../attachments/operacoes/momentum-v7/20260811-2000Z-DOGEUSDT-target.png) |
| 005 | 11/08 17:00 | 20:00Z | SOLUSDT | replay | 75.7954500000 | 75.1188337516 | 76.6523324968 | horizonte | +0.45 | 3 | `—` | [20260811-2000Z-SOLUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260811-2000Z-SOLUSDT-expired.png) |
| 006 | 11/08 17:00 | 20:00Z | XRPUSDT | replay | 1.0164094800 | 1.0058797759 | 1.0335404483 | horizonte | +0.41 | 1 | `—` | [20260811-2000Z-XRPUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260811-2000Z-XRPUSDT-expired.png) |
| 007 | 13/08 00:00 | 03:00Z | DOGEUSDT | replay | 0.0703421800 | 0.0697606550 | 0.0712586899 | horizonte | +0.34 | 1 | `—` | [20260813-0300Z-DOGEUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260813-0300Z-DOGEUSDT-expired.png) |
| 008 | 16/08 22:45 | 01:45Z | SOLUSDT | replay | 75.2351140000 | 74.7282711652 | 76.2934576697 | invalidação | -0.55 | 0 | `—` | [20260817-0145Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260817-0145Z-SOLUSDT-invalidated.png) |
| 009 | 16/08 23:45 | 02:45Z | SOLUSDT | replay | 75.3351740000 | 74.8200301852 | 76.3499396296 | horizonte | +0.43 | 0 | `—` | [20260817-0245Z-SOLUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260817-0245Z-SOLUSDT-expired.png) |
| 010 | 18/08 12:30 | 15:30Z | SOLUSDT | replay | 77.0962300000 | 76.4487822234 | 78.1024355532 | invalidação | -0.54 | 3 | `—` | [20260818-1530Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260818-1530Z-SOLUSDT-invalidated.png) |
| 011 | 19/08 10:30 | 13:30Z | SOLUSDT | replay | 78.6071360000 | 77.9374824449 | 79.5350351102 | invalidação | -0.52 | 4 | `—` | [20260819-1330Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260819-1330Z-SOLUSDT-invalidated.png) |
| 012 | 19/08 11:45 | 14:45Z | SOLUSDT | replay | 79.0774180000 | 78.3449622731 | 80.2800754539 | alvo | +1.49 | 5 | `—` | [20260819-1445Z-SOLUSDT-target.png](../../attachments/operacoes/momentum-v7/20260819-1445Z-SOLUSDT-target.png) |
| 013 | 19/08 12:00 | 15:00Z | ETHUSDT | replay | 1973.8235840000 | 1952.1082005265 | 2005.4535989471 | alvo | +1.33 | 2 | `—` | [20260819-1500Z-ETHUSDT-target.png](../../attachments/operacoes/momentum-v7/20260819-1500Z-ETHUSDT-target.png) |
| 014 | 19/08 12:00 | 15:00Z | XRPUSDT | replay | 1.0320188400 | 1.0236917128 | 1.0507165744 | alvo | +2.07 | 3 | `—` | [20260819-1500Z-XRPUSDT-target.png](../../attachments/operacoes/momentum-v7/20260819-1500Z-XRPUSDT-target.png) |
| 015 | 19/08 12:15 | 15:15Z | DOGEUSDT | replay | 0.0719931700 | 0.0712743542 | 0.0730612915 | alvo | +1.34 | 3 | `—` | [20260819-1515Z-DOGEUSDT-target.png](../../attachments/operacoes/momentum-v7/20260819-1515Z-DOGEUSDT-target.png) |
| 016 | 19/08 13:15 | 16:15Z | ETHUSDT | replay | 2096.8973840000 | 2043.5292747826 | 2179.9114504349 | invalidação | -0.40 | 2 | `—` | [20260819-1615Z-ETHUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260819-1615Z-ETHUSDT-invalidated.png) |
| 017 | 19/08 17:00 | 20:00Z | ETHUSDT | replay | 2103.4513140000 | 2070.0426682377 | 2162.8246635246 | alvo | +1.69 | 0 | `—` | [20260819-2000Z-ETHUSDT-target.png](../../attachments/operacoes/momentum-v7/20260819-2000Z-ETHUSDT-target.png) |
| 018 | 19/08 17:15 | 20:15Z | XRPUSDT | replay | 1.0757450600 | 1.0596173364 | 1.1015653271 | alvo | +1.51 | 1 | `—` | [20260819-2015Z-XRPUSDT-target.png](../../attachments/operacoes/momentum-v7/20260819-2015Z-XRPUSDT-target.png) |
| 019 | 19/08 18:00 | 21:00Z | SOLUSDT | replay | 83.8202620000 | 82.5448718658 | 86.0402562684 | alvo | +1.65 | 1 | `—` | [20260819-2100Z-SOLUSDT-target.png](../../attachments/operacoes/momentum-v7/20260819-2100Z-SOLUSDT-target.png) |
| 020 | 19/08 18:00 | 21:00Z | DOGEUSDT | replay | 0.0741644720 | 0.0731944769 | 0.0760910462 | alvo | +1.88 | 2 | `—` | [20260819-2100Z-DOGEUSDT-target.png](../../attachments/operacoes/momentum-v7/20260819-2100Z-DOGEUSDT-target.png) |
| 021 | 20/08 03:30 | 06:30Z | SOLUSDT | replay | 85.4812580000 | 84.5710057164 | 87.1779885673 | alvo | +1.72 | 1 | `—` | [20260820-0630Z-SOLUSDT-target.png](../../attachments/operacoes/momentum-v7/20260820-0630Z-SOLUSDT-target.png) |
| 022 | 20/08 05:15 | 08:15Z | DOGEUSDT | replay | 0.0763357740 | 0.0755547080 | 0.0782405841 | horizonte | +0.50 | 0 | `—` | [20260820-0815Z-DOGEUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260820-0815Z-DOGEUSDT-expired.png) |
| 023 | 20/08 05:15 | 08:15Z | XRPUSDT | replay | 1.1271759000 | 1.1149756059 | 1.1552487883 | alvo | +2.17 | 2 | `—` | [20260820-0815Z-XRPUSDT-target.png](../../attachments/operacoes/momentum-v7/20260820-0815Z-XRPUSDT-target.png) |
| 024 | 20/08 05:15 | 08:15Z | ETHUSDT | replay | 2276.1548740000 | 2254.6092471314 | 2341.9115057372 | horizonte | -0.28 | 1 | `—` | [20260820-0815Z-ETHUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260820-0815Z-ETHUSDT-expired.png) |
| 025 | 20/08 08:45 | 11:45Z | XRPUSDT | replay | 1.1945162800 | 1.1676831916 | 1.2313336167 | alvo | +1.31 | 2 | `—` | [20260820-1145Z-XRPUSDT-target.png](../../attachments/operacoes/momentum-v7/20260820-1145Z-XRPUSDT-target.png) |
| 026 | 20/08 10:30 | 13:30Z | DOGEUSDT | replay | 0.0774264280 | 0.0766462742 | 0.0799874515 | invalidação | -0.20 | 3 | `—` | [20260820-1330Z-DOGEUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260820-1330Z-DOGEUSDT-invalidated.png) |
| 027 | 20/08 11:15 | 14:15Z | DOGEUSDT | replay | 0.0778967100 | 0.0767710213 | 0.0804579574 | invalidação | -0.32 | 2 | `—` | [20260820-1415Z-DOGEUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260820-1415Z-DOGEUSDT-invalidated.png) |
| 028 | 20/08 12:00 | 15:00Z | DOGEUSDT | replay | 0.0784370340 | 0.0771771551 | 0.0809656898 | alvo | +1.91 | 2 | `—` | [20260820-1500Z-DOGEUSDT-target.png](../../attachments/operacoes/momentum-v7/20260820-1500Z-DOGEUSDT-target.png) |
| 029 | 20/08 12:15 | 15:15Z | XRPUSDT | replay | 1.2588548600 | 1.2268449828 | 1.3317100345 | alvo | +2.21 | 1 | `—` | [20260820-1515Z-XRPUSDT-target.png](../../attachments/operacoes/momentum-v7/20260820-1515Z-XRPUSDT-target.png) |
| 030 | 20/08 12:30 | 15:30Z | ETHUSDT | replay | 2317.0994260000 | 2275.7403271611 | 2387.4593456778 | invalidação | -0.43 | 3 | `—` | [20260820-1530Z-ETHUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260820-1530Z-ETHUSDT-invalidated.png) |
| 031 | 20/08 13:45 | 16:45Z | ETHUSDT | replay | 2344.0555900000 | 2304.3027610668 | 2436.1444778663 | invalidação | -0.57 | 3 | `—` | [20260820-1645Z-ETHUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260820-1645Z-ETHUSDT-invalidated.png) |
| 032 | 20/08 21:30 | 00:30Z | DOGEUSDT | replay | 0.0811686720 | 0.0797104884 | 0.0837890233 | horizonte | +0.48 | 0 | `—` | [20260821-0030Z-DOGEUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260821-0030Z-DOGEUSDT-expired.png) |
| 033 | 20/08 21:30 | 00:30Z | SOLUSDT | replay | 88.3329680000 | 87.4577511124 | 90.2244977753 | invalidação | -0.61 | 3 | `—` | [20260821-0030Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260821-0030Z-SOLUSDT-invalidated.png) |
| 034 | 20/08 22:30 | 01:30Z | ETHUSDT | replay | 2351.2098800000 | 2320.7880966250 | 2415.3238067500 | invalidação | -0.32 | 3 | `—` | [20260821-0130Z-ETHUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260821-0130Z-ETHUSDT-invalidated.png) |
| 035 | 20/08 23:00 | 02:00Z | SOLUSDT | replay | 88.8832980000 | 87.8123994051 | 91.3452011899 | horizonte | +1.27 | 5 | `—` | [20260821-0200Z-SOLUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260821-0200Z-SOLUSDT-expired.png) |
| 036 | 20/08 23:00 | 02:00Z | XRPUSDT | replay | 1.2914744200 | 1.2658956742 | 1.3553086516 | invalidação | -0.22 | 0 | `—` | [20260821-0200Z-XRPUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260821-0200Z-XRPUSDT-invalidated.png) |
| 037 | 21/08 03:30 | 06:30Z | DOGEUSDT | replay | 0.0834200220 | 0.0820090476 | 0.0860619049 | horizonte | +0.34 | 0 | `—` | [20260821-0630Z-DOGEUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260821-0630Z-DOGEUSDT-expired.png) |
| 038 | 21/08 05:15 | 08:15Z | XRPUSDT | replay | 1.3515104200 | 1.3143729028 | 1.4077541944 | alvo | +1.46 | 2 | `—` | [20260821-0815Z-XRPUSDT-target.png](../../attachments/operacoes/momentum-v7/20260821-0815Z-XRPUSDT-target.png) |
| 039 | 21/08 05:30 | 08:30Z | SOLUSDT | replay | 91.4648460000 | 89.9027222905 | 94.3045554190 | stop | -1.08 | 5 | `—` | [20260821-0830Z-SOLUSDT-stop.png](../../attachments/operacoes/momentum-v7/20260821-0830Z-SOLUSDT-stop.png) |
| 040 | 21/08 05:30 | 08:30Z | ETHUSDT | replay | 2388.7724040000 | 2353.6857195009 | 2453.5685609981 | invalidação | -0.53 | 2 | `—` | [20260821-0830Z-ETHUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260821-0830Z-ETHUSDT-invalidated.png) |
| 041 | 21/08 14:15 | 17:15Z | ETHUSDT | replay | 2414.0075360000 | 2378.7268990424 | 2487.3962019152 | horizonte | +0.90 | 4 | `—` | [20260821-1715Z-ETHUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260821-1715Z-ETHUSDT-expired.png) |
| 042 | 21/08 17:45 | 20:45Z | DOGEUSDT | replay | 0.0866719720 | 0.0848437271 | 0.0902925458 | alvo | +1.91 | 5 | `—` | [20260821-2045Z-DOGEUSDT-target.png](../../attachments/operacoes/momentum-v7/20260821-2045Z-DOGEUSDT-target.png) |
| 043 | 21/08 18:30 | 21:30Z | SOLUSDT | replay | 92.9257220000 | 91.4544589204 | 95.4910821592 | horizonte | +0.73 | 6 | `—` | [20260821-2130Z-SOLUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260821-2130Z-SOLUSDT-expired.png) |
| 044 | 21/08 19:15 | 22:15Z | XRPUSDT | replay | 1.4257549400 | 1.3894607261 | 1.4996785477 | alvo | +1.98 | 4 | `—` | [20260821-2215Z-XRPUSDT-target.png](../../attachments/operacoes/momentum-v7/20260821-2215Z-XRPUSDT-target.png) |
| 045 | 21/08 19:45 | 22:45Z | DOGEUSDT | replay | 0.0939563400 | 0.0910045077 | 0.0996309845 | invalidação | -0.37 | 5 | `—` | [20260821-2245Z-DOGEUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260821-2245Z-DOGEUSDT-invalidated.png) |
| 046 | 21/08 23:15 | 02:15Z | XRPUSDT | replay | 1.5070036600 | 1.4478983562 | 1.6090032875 | alvo | +1.69 | 1 | `—` | [20260822-0215Z-XRPUSDT-target.png](../../attachments/operacoes/momentum-v7/20260822-0215Z-XRPUSDT-target.png) |
| 047 | 21/08 23:45 | 02:45Z | SOLUSDT | replay | 95.6073300000 | 94.0138437250 | 99.1023125500 | alvo | +2.11 | 3 | `—` | [20260822-0245Z-SOLUSDT-target.png](../../attachments/operacoes/momentum-v7/20260822-0245Z-SOLUSDT-target.png) |
| 048 | 22/08 00:30 | 03:30Z | DOGEUSDT | replay | 0.0967680260 | 0.0939126776 | 0.1022746448 | stop | -1.05 | 3 | `—` | [20260822-0330Z-DOGEUSDT-stop.png](../../attachments/operacoes/momentum-v7/20260822-0330Z-DOGEUSDT-stop.png) |
| 049 | 22/08 14:30 | 17:30Z | DOGEUSDT | replay | 0.0925054700 | 0.0897734669 | 0.0965730662 | horizonte | +0.27 | 0 | `—` | [20260822-1730Z-DOGEUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260822-1730Z-DOGEUSDT-expired.png) |
| 050 | 22/08 17:00 | 20:00Z | ETHUSDT | replay | 2439.9230760000 | 2418.8509224344 | 2476.8381551312 | invalidação | -0.58 | 1 | `—` | [20260822-2000Z-ETHUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260822-2000Z-ETHUSDT-invalidated.png) |
| 051 | 22/08 21:45 | 00:45Z | SOLUSDT | replay | 96.7480140000 | 94.2885178997 | 100.4729642006 | stop | -1.05 | 0 | `—` | [20260823-0045Z-SOLUSDT-stop.png](../../attachments/operacoes/momentum-v7/20260823-0045Z-SOLUSDT-stop.png) |
| 052 | 23/08 05:45 | 08:45Z | ETHUSDT | replay | 2422.1424140000 | 2391.7536717071 | 2474.6026565858 | invalidação | -0.44 | 1 | `—` | [20260823-0845Z-ETHUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260823-0845Z-ETHUSDT-invalidated.png) |
| 053 | 23/08 07:30 | 10:30Z | DOGEUSDT | replay | 0.0920451940 | 0.0902972708 | 0.0952254585 | horizonte | +1.14 | 1 | `—` | [20260823-1030Z-DOGEUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260823-1030Z-DOGEUSDT-expired.png) |
| 054 | 23/08 08:30 | 11:30Z | XRPUSDT | replay | 1.4946962800 | 1.4592162226 | 1.5596675549 | invalidação | -0.18 | 2 | `—` | [20260823-1130Z-XRPUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260823-1130Z-XRPUSDT-invalidated.png) |
| 055 | 23/08 08:30 | 11:30Z | ETHUSDT | replay | 2429.5468540000 | 2404.6615398669 | 2471.4369202661 | alvo | +1.54 | 1 | `—` | [20260823-1130Z-ETHUSDT-target.png](../../attachments/operacoes/momentum-v7/20260823-1130Z-ETHUSDT-target.png) |
| 056 | 23/08 08:30 | 11:30Z | SOLUSDT | replay | 94.4566400000 | 93.0603754372 | 96.8392491257 | stop | -1.09 | 0 | `—` | [20260823-1130Z-SOLUSDT-stop.png](../../attachments/operacoes/momentum-v7/20260823-1130Z-SOLUSDT-stop.png) |
| 057 | 23/08 10:30 | 13:30Z | XRPUSDT | replay | 1.5089048000 | 1.4732550407 | 1.5678899187 | stop | -1.06 | 3 | `—` | [20260823-1330Z-XRPUSDT-stop.png](../../attachments/operacoes/momentum-v7/20260823-1330Z-XRPUSDT-stop.png) |
| 058 | 23/08 18:15 | 21:15Z | ETHUSDT | replay | 2467.4796000000 | 2440.4297973876 | 2514.2904052248 | stop | -1.13 | 1 | `—` | [20260823-2115Z-ETHUSDT-stop.png](../../attachments/operacoes/momentum-v7/20260823-2115Z-ETHUSDT-stop.png) |
| 059 | 23/08 18:15 | 21:15Z | SOLUSDT | replay | 95.7974440000 | 94.6201006313 | 97.7097987374 | invalidação | -0.55 | 2 | `—` | [20260823-2115Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260823-2115Z-SOLUSDT-invalidated.png) |
| 060 | 23/08 18:30 | 21:30Z | XRPUSDT | replay | 1.5377220800 | 1.5024158696 | 1.6016682608 | invalidação | -0.63 | 3 | `—` | [20260823-2130Z-XRPUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260823-2130Z-XRPUSDT-invalidated.png) |
| 061 | 24/08 04:15 | 07:15Z | ETHUSDT | replay | 2467.4896060000 | 2439.5819464113 | 2529.3361071773 | invalidação | -0.69 | 5 | `—` | [20260824-0715Z-ETHUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260824-0715Z-ETHUSDT-invalidated.png) |
| 062 | 24/08 04:15 | 07:15Z | SOLUSDT | replay | 95.2070900000 | 93.9093309890 | 98.1113380220 | invalidação | -0.80 | 5 | `—` | [20260824-0715Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260824-0715Z-SOLUSDT-invalidated.png) |
| 063 | 24/08 04:15 | 07:15Z | XRPUSDT | replay | 1.4945962200 | 1.4630975368 | 1.5651049264 | invalidação | -0.68 | 2 | `—` | [20260824-0715Z-XRPUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260824-0715Z-XRPUSDT-invalidated.png) |
| 064 | 24/08 07:15 | 10:15Z | ETHUSDT | replay | 2480.4273640000 | 2454.3112859819 | 2538.1574280361 | invalidação | -0.70 | 4 | `—` | [20260824-1015Z-ETHUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260824-1015Z-ETHUSDT-invalidated.png) |
| 065 | 24/08 08:45 | 11:45Z | XRPUSDT | replay | 1.5056028200 | 1.4787538331 | 1.5664923338 | invalidação | -0.40 | 4 | `—` | [20260824-1145Z-XRPUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260824-1145Z-XRPUSDT-invalidated.png) |
| 066 | 24/08 08:45 | 11:45Z | DOGEUSDT | replay | 0.0925254820 | 0.0911787904 | 0.0957724192 | invalidação | -0.32 | 2 | `—` | [20260824-1145Z-DOGEUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260824-1145Z-DOGEUSDT-invalidated.png) |
| 067 | 24/08 08:45 | 11:45Z | SOLUSDT | replay | 96.1276420000 | 94.9773601642 | 98.7952796716 | invalidação | -0.85 | 5 | `—` | [20260824-1145Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260824-1145Z-SOLUSDT-invalidated.png) |
| 068 | 24/08 08:45 | 11:45Z | ETHUSDT | replay | 2501.0297180000 | 2474.1823643490 | 2569.4552713020 | stop | -1.13 | 5 | `—` | [20260824-1145Z-ETHUSDT-stop.png](../../attachments/operacoes/momentum-v7/20260824-1145Z-ETHUSDT-stop.png) |
| 069 | 24/08 10:00 | 13:00Z | SOLUSDT | replay | 96.1976840000 | 94.6689823455 | 99.4420353089 | invalidação | -0.18 | 5 | `—` | [20260824-1300Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260824-1300Z-SOLUSDT-invalidated.png) |
| 070 | 24/08 10:00 | 13:00Z | DOGEUSDT | replay | 0.0929957640 | 0.0915516122 | 0.0965867756 | invalidação | -0.47 | 5 | `—` | [20260824-1300Z-DOGEUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260824-1300Z-DOGEUSDT-invalidated.png) |
| 071 | 24/08 10:00 | 13:00Z | XRPUSDT | replay | 1.5134075000 | 1.4852793571 | 1.5795412858 | stop | -1.07 | 4 | `—` | [20260824-1300Z-XRPUSDT-stop.png](../../attachments/operacoes/momentum-v7/20260824-1300Z-XRPUSDT-stop.png) |
| 072 | 24/08 10:00 | 13:00Z | ETHUSDT | replay | 2509.7749620000 | 2476.5214436166 | 2582.9271127668 | invalidação | -0.83 | 4 | `—` | [20260824-1300Z-ETHUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260824-1300Z-ETHUSDT-invalidated.png) |
| 073 | 24/08 11:30 | 14:30Z | ETHUSDT | replay | 2522.4625700000 | 2476.3920721033 | 2595.8458557933 | invalidação | -0.25 | 3 | `—` | [20260824-1430Z-ETHUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260824-1430Z-ETHUSDT-invalidated.png) |
| 074 | 24/08 11:45 | 14:45Z | XRPUSDT | replay | 1.5242139800 | 1.4850972792 | 1.5961054416 | invalidação | -0.42 | 4 | `—` | [20260824-1445Z-XRPUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260824-1445Z-XRPUSDT-invalidated.png) |
| 075 | 24/08 11:45 | 14:45Z | SOLUSDT | replay | 96.4678460000 | 94.6822277125 | 99.9855445750 | invalidação | -0.29 | 4 | `—` | [20260824-1445Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260824-1445Z-SOLUSDT-invalidated.png) |
| 076 | 24/08 12:30 | 15:30Z | SOLUSDT | replay | 97.2082900000 | 95.4345098392 | 101.0309803216 | invalidação | -0.52 | 4 | `—` | [20260824-1530Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260824-1530Z-SOLUSDT-invalidated.png) |
| 077 | 24/08 19:45 | 22:45Z | SOLUSDT | replay | 97.8586800000 | 96.1300635322 | 100.6598729357 | invalidação | -0.33 | 6 | `—` | [20260824-2245Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260824-2245Z-SOLUSDT-invalidated.png) |
| 078 | 24/08 21:15 | 00:15Z | SOLUSDT | replay | 99.8798920000 | 98.4578995281 | 104.8242009438 | horizonte | +0.92 | 6 | `—` | [20260825-0015Z-SOLUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260825-0015Z-SOLUSDT-expired.png) |
| 079 | 24/08 21:45 | 00:45Z | XRPUSDT | replay | 1.5127070800 | 1.4806732736 | 1.5644534529 | horizonte | -0.18 | 5 | `—` | [20260825-0045Z-XRPUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260825-0045Z-XRPUSDT-expired.png) |
| 080 | 24/08 22:00 | 01:00Z | DOGEUSDT | replay | 0.0915649060 | 0.0899684463 | 0.0942631075 | invalidação | -0.39 | 2 | `—` | [20260825-0100Z-DOGEUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260825-0100Z-DOGEUSDT-invalidated.png) |
| 081 | 24/08 22:00 | 01:00Z | ETHUSDT | replay | 2495.3363040000 | 2467.5605019854 | 2541.4789960293 | invalidação | -0.40 | 2 | `—` | [20260825-0100Z-ETHUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260825-0100Z-ETHUSDT-invalidated.png) |
| 082 | 24/08 23:30 | 02:30Z | DOGEUSDT | replay | 0.0927556200 | 0.0913047661 | 0.0961504678 | horizonte | -0.27 | 2 | `—` | [20260825-0230Z-DOGEUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260825-0230Z-DOGEUSDT-expired.png) |
| 083 | 24/08 23:30 | 02:30Z | ETHUSDT | replay | 2528.1960080000 | 2499.3617240073 | 2587.9465519854 | stop | -1.12 | 4 | `—` | [20260825-0230Z-ETHUSDT-stop.png](../../attachments/operacoes/momentum-v7/20260825-0230Z-ETHUSDT-stop.png) |
| 084 | 25/08 02:30 | 05:30Z | SOLUSDT | replay | 102.6115300000 | 100.4362139731 | 107.1675720538 | invalidação | -0.48 | 3 | `—` | [20260825-0530Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260825-0530Z-SOLUSDT-invalidated.png) |
| 085 | 26/08 07:45 | 10:45Z | SOLUSDT | replay | 97.5284820000 | 96.3616785334 | 99.3266429333 | invalidação | -0.63 | 5 | `—` | [20260826-1045Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260826-1045Z-SOLUSDT-invalidated.png) |
| 086 | 26/08 08:00 | 11:00Z | DOGEUSDT | replay | 0.0868020500 | 0.0858595479 | 0.0887109042 | invalidação | -0.24 | 4 | `—` | [20260826-1100Z-DOGEUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260826-1100Z-DOGEUSDT-invalidated.png) |
| 087 | 26/08 08:00 | 11:00Z | ETHUSDT | replay | 2469.1706140000 | 2448.2965770587 | 2506.4168458826 | invalidação | -0.57 | 2 | `—` | [20260826-1100Z-ETHUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260826-1100Z-ETHUSDT-invalidated.png) |
| 088 | 26/08 15:15 | 18:15Z | ETHUSDT | replay | 2466.6891260000 | 2441.6478953738 | 2515.8442092524 | invalidação | -0.33 | 6 | `—` | [20260826-1815Z-ETHUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260826-1815Z-ETHUSDT-invalidated.png) |
| 089 | 26/08 16:30 | 19:30Z | ETHUSDT | replay | 2476.8051920000 | 2456.0244497491 | 2525.2811005019 | invalidação | -0.49 | 6 | `—` | [20260826-1930Z-ETHUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260826-1930Z-ETHUSDT-invalidated.png) |
| 090 | 26/08 18:15 | 21:15Z | SOLUSDT | replay | 97.5685060000 | 96.3818870124 | 99.6762259752 | alvo | +1.66 | 5 | `—` | [20260826-2115Z-SOLUSDT-target.png](../../attachments/operacoes/momentum-v7/20260826-2115Z-SOLUSDT-target.png) |
| 091 | 26/08 18:15 | 21:15Z | ETHUSDT | replay | 2493.1750080000 | 2468.5047909292 | 2538.5704181415 | horizonte | -0.28 | 6 | `—` | [20260826-2115Z-ETHUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260826-2115Z-ETHUSDT-expired.png) |
| 092 | 26/08 18:30 | 21:30Z | DOGEUSDT | replay | 0.0859615460 | 0.0850386249 | 0.0882227502 | horizonte | +1.24 | 4 | `—` | [20260826-2130Z-DOGEUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260826-2130Z-DOGEUSDT-expired.png) |
| 093 | 26/08 19:15 | 22:15Z | XRPUSDT | replay | 1.4062432400 | 1.3819714553 | 1.4465570895 | invalidação | -0.34 | 5 | `—` | [20260826-2215Z-XRPUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260826-2215Z-XRPUSDT-invalidated.png) |
| 094 | 26/08 20:15 | 23:15Z | SOLUSDT | replay | 100.5102700000 | 98.7710176125 | 103.4179647749 | horizonte | +0.18 | 5 | `—` | [20260826-2315Z-SOLUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260826-2315Z-SOLUSDT-expired.png) |
| 095 | 27/08 03:00 | 06:00Z | SOLUSDT | replay | 101.8610800000 | 100.5345731733 | 104.9908536533 | invalidação | -0.46 | 3 | `—` | [20260827-0600Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260827-0600Z-SOLUSDT-invalidated.png) |
| 096 | 27/08 05:15 | 08:15Z | DOGEUSDT | replay | 0.0881228420 | 0.0872346921 | 0.0902806157 | horizonte | +0.33 | 3 | `—` | [20260827-0815Z-DOGEUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260827-0815Z-DOGEUSDT-expired.png) |
| 097 | 27/08 05:15 | 08:15Z | XRPUSDT | replay | 1.4219526600 | 1.4069034247 | 1.4647931506 | horizonte | +0.28 | 2 | `—` | [20260827-0815Z-XRPUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260827-0815Z-XRPUSDT-expired.png) |
| 098 | 27/08 05:15 | 08:15Z | SOLUSDT | replay | 102.7816320000 | 101.3878267346 | 106.1943465307 | horizonte | +1.00 | 3 | `—` | [20260827-0815Z-SOLUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260827-0815Z-SOLUSDT-expired.png) |
| 099 | 27/08 05:15 | 08:15Z | ETHUSDT | replay | 2516.1187660000 | 2498.8251756702 | 2559.6196486596 | alvo | +2.31 | 3 | `—` | [20260827-0815Z-ETHUSDT-target.png](../../attachments/operacoes/momentum-v7/20260827-0815Z-ETHUSDT-target.png) |
| 100 | 27/08 11:00 | 14:00Z | SOLUSDT | replay | 105.9635400000 | 104.1705654792 | 109.6288690416 | horizonte | +1.01 | 0 | `—` | [20260827-1400Z-SOLUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260827-1400Z-SOLUSDT-expired.png) |
| 101 | 27/08 11:30 | 14:30Z | XRPUSDT | replay | 1.4554727600 | 1.4323967234 | 1.5113065532 | invalidação | -0.65 | 3 | `—` | [20260827-1430Z-XRPUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260827-1430Z-XRPUSDT-invalidated.png) |
| 102 | 27/08 11:45 | 14:45Z | DOGEUSDT | replay | 0.0892435140 | 0.0878220796 | 0.0921958408 | invalidação | -0.29 | 3 | `—` | [20260827-1445Z-DOGEUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260827-1445Z-DOGEUSDT-invalidated.png) |
| 103 | 27/08 13:45 | 16:45Z | DOGEUSDT | replay | 0.0897238020 | 0.0882054569 | 0.0925390861 | invalidação | -0.41 | 2 | `—` | [20260827-1645Z-DOGEUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260827-1645Z-DOGEUSDT-invalidated.png) |
| 104 | 27/08 17:00 | 20:00Z | SOLUSDT | replay | 108.9753460000 | 107.2751856059 | 113.4396287881 | invalidação | -0.19 | 4 | `—` | [20260827-2000Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260827-2000Z-SOLUSDT-invalidated.png) |
| 105 | 27/08 22:30 | 01:30Z | XRPUSDT | replay | 1.4658790000 | 1.4483367576 | 1.5043264848 | stop | -1.12 | 6 | `—` | [20260828-0130Z-XRPUSDT-stop.png](../../attachments/operacoes/momentum-v7/20260828-0130Z-XRPUSDT-stop.png) |
| 106 | 27/08 22:30 | 01:30Z | DOGEUSDT | replay | 0.0898838980 | 0.0889027131 | 0.0918645739 | invalidação | -0.96 | 5 | `—` | [20260828-0130Z-DOGEUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260828-0130Z-DOGEUSDT-invalidated.png) |
| 107 | 28/08 08:15 | 11:15Z | XRPUSDT | replay | 1.4296572800 | 1.4140445856 | 1.4556108288 | invalidação | -0.41 | 3 | `—` | [20260828-1115Z-XRPUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260828-1115Z-XRPUSDT-invalidated.png) |
| 108 | 28/08 11:45 | 14:45Z | ETHUSDT | replay | 2507.3334980000 | 2476.0903097527 | 2574.3093804947 | invalidação | -0.27 | 5 | `—` | [20260828-1445Z-ETHUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260828-1445Z-ETHUSDT-invalidated.png) |
| 109 | 28/08 11:45 | 14:45Z | DOGEUSDT | replay | 0.0875825180 | 0.0862307635 | 0.0903084731 | invalidação | -0.58 | 2 | `—` | [20260828-1445Z-DOGEUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260828-1445Z-DOGEUSDT-invalidated.png) |
| 110 | 28/08 12:00 | 15:00Z | XRPUSDT | replay | 1.4335596200 | 1.4033103266 | 1.4845793468 | invalidação | -0.52 | 3 | `—` | [20260828-1500Z-XRPUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260828-1500Z-XRPUSDT-invalidated.png) |
| 111 | 28/08 12:30 | 15:30Z | SOLUSDT | replay | 106.5939180000 | 104.2930688382 | 111.5138623237 | invalidação | -0.50 | 5 | `—` | [20260828-1530Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260828-1530Z-SOLUSDT-invalidated.png) |
| 112 | 29/08 11:45 | 14:45Z | SOLUSDT | replay | 105.0129700000 | 104.1490507991 | 106.4618984019 | horizonte | -0.18 | 5 | `—` | [20260829-1445Z-SOLUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260829-1445Z-SOLUSDT-expired.png) |
| 113 | 29/08 16:30 | 19:30Z | SOLUSDT | replay | 105.7534140000 | 104.8321240244 | 107.3757519512 | invalidação | -0.67 | 2 | `—` | [20260829-1930Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260829-1930Z-SOLUSDT-invalidated.png) |
| 114 | 30/08 10:00 | 13:00Z | SOLUSDT | replay | 106.0836120000 | 105.2257756279 | 107.6684487441 | horizonte | +0.57 | 4 | `—` | [20260830-1300Z-SOLUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260830-1300Z-SOLUSDT-expired.png) |
| 115 | 30/08 10:00 | 13:00Z | DOGEUSDT | replay | 0.0853311680 | 0.0848050016 | 0.0865599967 | invalidação | -0.42 | 6 | `—` | [20260830-1300Z-DOGEUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260830-1300Z-DOGEUSDT-invalidated.png) |
| 116 | 30/08 11:00 | 14:00Z | XRPUSDT | replay | 1.4071437800 | 1.3970687859 | 1.4298624282 | stop | -1.19 | 1 | `—` | [20260830-1400Z-XRPUSDT-stop.png](../../attachments/operacoes/momentum-v7/20260830-1400Z-XRPUSDT-stop.png) |
| 117 | 30/08 11:00 | 14:00Z | DOGEUSDT | replay | 0.0856513600 | 0.0850812402 | 0.0868175197 | invalidação | -0.60 | 6 | `—` | [20260830-1400Z-DOGEUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260830-1400Z-DOGEUSDT-invalidated.png) |
| 118 | 30/08 13:15 | 16:15Z | ETHUSDT | replay | 2515.9386580000 | 2490.7245300231 | 2547.1409399537 | horizonte | -0.60 | 3 | `—` | [20260830-1615Z-ETHUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260830-1615Z-ETHUSDT-expired.png) |
| 119 | 30/08 13:15 | 16:15Z | DOGEUSDT | replay | 0.0859715520 | 0.0851737707 | 0.0871424587 | stop | -1.15 | 3 | `—` | [20260830-1615Z-DOGEUSDT-stop.png](../../attachments/operacoes/momentum-v7/20260830-1615Z-DOGEUSDT-stop.png) |
| 120 | 30/08 13:45 | 16:45Z | XRPUSDT | replay | 1.4125470200 | 1.3981699467 | 1.4363601065 | invalidação | -0.80 | 2 | `—` | [20260830-1645Z-XRPUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260830-1645Z-XRPUSDT-invalidated.png) |
| 121 | 30/08 15:45 | 18:45Z | DOGEUSDT | replay | 0.0863717920 | 0.0854931580 | 0.0880936840 | invalidação | -0.20 | 3 | `—` | [20260830-1845Z-DOGEUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260830-1845Z-DOGEUSDT-invalidated.png) |
| 122 | 31/08 02:30 | 05:30Z | DOGEUSDT | replay | 0.0829097160 | 0.0818238209 | 0.0849923582 | horizonte | -0.12 | 1 | `—` | [20260831-0530Z-DOGEUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260831-0530Z-DOGEUSDT-expired.png) |
| 123 | 31/08 02:30 | 05:30Z | ETHUSDT | replay | 2436.4509940000 | 2408.9887486894 | 2485.0725026212 | horizonte | +0.26 | 4 | `—` | [20260831-0530Z-ETHUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260831-0530Z-ETHUSDT-expired.png) |
| 124 | 31/08 02:30 | 05:30Z | SOLUSDT | replay | 102.7516140000 | 101.1792819776 | 105.5314360449 | horizonte | +0.16 | 2 | `—` | [20260831-0530Z-SOLUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260831-0530Z-SOLUSDT-expired.png) |
| 125 | 31/08 08:00 | 11:00Z | SOLUSDT | replay | 103.6321420000 | 102.5334436162 | 105.7931127675 | invalidação | -0.58 | 2 | `—` | [20260831-1100Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260831-1100Z-SOLUSDT-invalidated.png) |
| 126 | 31/08 11:45 | 14:45Z | ETHUSDT | replay | 2465.7685740000 | 2439.1176887739 | 2515.2946224522 | horizonte | +0.49 | 4 | `—` | [20260831-1445Z-ETHUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260831-1445Z-ETHUSDT-expired.png) |
| 127 | 31/08 15:30 | 18:30Z | SOLUSDT | replay | 103.8022440000 | 102.5038587470 | 106.1822825060 | invalidação | -0.24 | 6 | `—` | [20260831-1830Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260831-1830Z-SOLUSDT-invalidated.png) |
| 128 | 01/09 00:45 | 03:45Z | ETHUSDT | replay | 2476.3849400000 | 2458.3995142213 | 2510.2709715574 | invalidação | -0.47 | 5 | `—` | [20260901-0345Z-ETHUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260901-0345Z-ETHUSDT-invalidated.png) |
| 129 | 01/09 00:45 | 03:45Z | DOGEUSDT | replay | 0.0832799380 | 0.0826839254 | 0.0846221492 | horizonte | -0.38 | 5 | `—` | [20260901-0345Z-DOGEUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260901-0345Z-DOGEUSDT-expired.png) |
| 130 | 01/09 00:45 | 03:45Z | XRPUSDT | replay | 1.3895332200 | 1.3771796631 | 1.4162406738 | invalidação | -0.43 | 4 | `—` | [20260901-0345Z-XRPUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260901-0345Z-XRPUSDT-invalidated.png) |
| 131 | 01/09 00:45 | 03:45Z | SOLUSDT | replay | 103.8022440000 | 102.9756138328 | 105.6287723344 | invalidação | -0.76 | 3 | `—` | [20260901-0345Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260901-0345Z-SOLUSDT-invalidated.png) |
| 132 | 01/09 03:00 | 06:00Z | XRPUSDT | replay | 1.3950365200 | 1.3811991585 | 1.4202016829 | invalidação | -0.48 | 4 | `—` | [20260901-0600Z-XRPUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260901-0600Z-XRPUSDT-invalidated.png) |
| 133 | 01/09 20:45 | 23:45Z | ETHUSDT | replay | 2422.2624860000 | 2400.8589796567 | 2464.5520406865 | invalidação | -0.38 | 6 | `—` | [20260901-2345Z-ETHUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260901-2345Z-ETHUSDT-invalidated.png) |
| 134 | 02/09 00:30 | 03:30Z | XRPUSDT | replay | 1.3541119800 | 1.3380953743 | 1.3879092514 | invalidação | -0.35 | 5 | `—` | [20260902-0330Z-XRPUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260902-0330Z-XRPUSDT-invalidated.png) |
| 135 | 02/09 10:45 | 13:45Z | XRPUSDT | replay | 1.3451065800 | 1.3274390997 | 1.3807218005 | invalidação | -0.85 | 6 | `—` | [20260902-1345Z-XRPUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260902-1345Z-XRPUSDT-invalidated.png) |
| 136 | 02/09 10:45 | 13:45Z | SOLUSDT | replay | 99.5496940000 | 98.3243521052 | 102.2112957896 | invalidação | -0.42 | 4 | `—` | [20260902-1345Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260902-1345Z-SOLUSDT-invalidated.png) |
| 137 | 02/09 10:45 | 13:45Z | DOGEUSDT | replay | 0.0819591460 | 0.0810637659 | 0.0838124681 | stop | -1.13 | 1 | `—` | [20260902-1345Z-DOGEUSDT-stop.png](../../attachments/operacoes/momentum-v7/20260902-1345Z-DOGEUSDT-stop.png) |
| 138 | 02/09 10:45 | 13:45Z | ETHUSDT | replay | 2417.3895640000 | 2391.0653916216 | 2466.2292167568 | invalidação | -1.04 | 2 | `—` | [20260902-1345Z-ETHUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260902-1345Z-ETHUSDT-invalidated.png) |
| 139 | 02/09 17:15 | 20:15Z | SOLUSDT | replay | 99.5296820000 | 98.5510405002 | 101.6979189996 | invalidação | -0.17 | 2 | `—` | [20260902-2015Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260902-2015Z-SOLUSDT-invalidated.png) |
| 140 | 02/09 17:15 | 20:15Z | XRPUSDT | replay | 1.3492090400 | 1.3341243537 | 1.3787512925 | invalidação | -0.46 | 2 | `—` | [20260902-2015Z-XRPUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260902-2015Z-XRPUSDT-invalidated.png) |
| 141 | 02/09 21:00 | 00:00Z | SOLUSDT | replay | 100.4102100000 | 99.4333218920 | 102.2733562161 | invalidação | -0.89 | 5 | `—` | [20260903-0000Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260903-0000Z-SOLUSDT-invalidated.png) |
| 142 | 02/09 22:15 | 01:15Z | XRPUSDT | replay | 1.3574139600 | 1.3432008617 | 1.3875982767 | horizonte | +0.31 | 2 | `—` | [20260903-0115Z-XRPUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260903-0115Z-XRPUSDT-expired.png) |
| 143 | 02/09 22:15 | 01:15Z | DOGEUSDT | replay | 0.0820492000 | 0.0811927218 | 0.0837345565 | horizonte | +0.67 | 3 | `—` | [20260903-0115Z-DOGEUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260903-0115Z-DOGEUSDT-expired.png) |
| 144 | 02/09 23:45 | 02:45Z | ETHUSDT | replay | 2404.5718780000 | 2384.8374057324 | 2442.5351885352 | stop | -1.17 | 3 | `—` | [20260903-0245Z-ETHUSDT-stop.png](../../attachments/operacoes/momentum-v7/20260903-0245Z-ETHUSDT-stop.png) |
| 145 | 02/09 23:45 | 02:45Z | SOLUSDT | replay | 100.7604200000 | 99.6473672674 | 102.8352654651 | invalidação | -0.52 | 4 | `—` | [20260903-0245Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260903-0245Z-SOLUSDT-invalidated.png) |
| 146 | 03/09 04:15 | 07:15Z | DOGEUSDT | replay | 0.0834300280 | 0.0825766749 | 0.0852266503 | invalidação | -0.50 | 2 | `—` | [20260903-0715Z-DOGEUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260903-0715Z-DOGEUSDT-invalidated.png) |
| 147 | 03/09 04:15 | 07:15Z | ETHUSDT | replay | 2410.4454000000 | 2392.4458160744 | 2450.5683678512 | invalidação | -0.38 | 5 | `—` | [20260903-0715Z-ETHUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260903-0715Z-ETHUSDT-invalidated.png) |
| 148 | 03/09 04:15 | 07:15Z | XRPUSDT | replay | 1.3709220600 | 1.3559155678 | 1.4044688644 | invalidação | -0.24 | 2 | `—` | [20260903-0715Z-XRPUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260903-0715Z-XRPUSDT-invalidated.png) |
| 149 | 03/09 04:15 | 07:15Z | SOLUSDT | replay | 101.0706060000 | 100.0525231920 | 103.2849536160 | invalidação | -0.39 | 3 | `—` | [20260903-0715Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260903-0715Z-SOLUSDT-invalidated.png) |
| 150 | 03/09 05:15 | 08:15Z | XRPUSDT | replay | 1.3733235000 | 1.3560485269 | 1.4087029462 | invalidação | -0.29 | 3 | `—` | [20260903-0815Z-XRPUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260903-0815Z-XRPUSDT-invalidated.png) |
| 151 | 03/09 09:45 | 12:45Z | SOLUSDT | replay | 101.0005640000 | 99.9734511880 | 102.8730976240 | alvo | +1.68 | 4 | `—` | [20260903-1245Z-SOLUSDT-target.png](../../attachments/operacoes/momentum-v7/20260903-1245Z-SOLUSDT-target.png) |
| 152 | 03/09 09:45 | 12:45Z | XRPUSDT | replay | 1.3763253000 | 1.3605220050 | 1.4036559899 | alvo | +1.61 | 2 | `—` | [20260903-1245Z-XRPUSDT-target.png](../../attachments/operacoes/momentum-v7/20260903-1245Z-XRPUSDT-target.png) |
| 153 | 03/09 09:45 | 12:45Z | ETHUSDT | replay | 2413.8774580000 | 2394.3444597766 | 2448.6610804468 | alvo | +1.61 | 5 | `—` | [20260903-1245Z-ETHUSDT-target.png](../../attachments/operacoes/momentum-v7/20260903-1245Z-ETHUSDT-target.png) |
| 154 | 03/09 10:00 | 13:00Z | DOGEUSDT | replay | 0.0834400340 | 0.0828124937 | 0.0852350126 | alvo | +2.67 | 2 | `—` | [20260903-1300Z-DOGEUSDT-target.png](../../attachments/operacoes/momentum-v7/20260903-1300Z-DOGEUSDT-target.png) |
| 155 | 03/09 12:30 | 15:30Z | ETHUSDT | replay | 2490.9836940000 | 2460.2779681106 | 2547.7340637788 | invalidação | -0.21 | 3 | `—` | [20260903-1530Z-ETHUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260903-1530Z-ETHUSDT-invalidated.png) |
| 156 | 03/09 13:00 | 16:00Z | SOLUSDT | replay | 104.9629400000 | 103.4124537876 | 108.5950924249 | invalidação | -0.57 | 3 | `—` | [20260903-1600Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260903-1600Z-SOLUSDT-invalidated.png) |
| 157 | 03/09 13:00 | 16:00Z | XRPUSDT | replay | 1.4616764800 | 1.4340395703 | 1.5242208594 | horizonte | -0.01 | 3 | `—` | [20260903-1600Z-XRPUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260903-1600Z-XRPUSDT-expired.png) |
| 158 | 03/09 13:00 | 16:00Z | DOGEUSDT | replay | 0.0893035500 | 0.0874170626 | 0.0927358749 | horizonte | -0.25 | 1 | `—` | [20260903-1600Z-DOGEUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260903-1600Z-DOGEUSDT-expired.png) |
| 159 | 03/09 17:30 | 20:30Z | XRPUSDT | replay | 1.4795872200 | 1.4549419198 | 1.5328161603 | invalidação | -0.45 | 0 | `—` | [20260903-2030Z-XRPUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260903-2030Z-XRPUSDT-invalidated.png) |
| 160 | 04/09 00:15 | 03:15Z | ETHUSDT | replay | 2511.4459640000 | 2490.0145618939 | 2550.5708762122 | invalidação | -0.40 | 1 | `—` | [20260904-0315Z-ETHUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260904-0315Z-ETHUSDT-invalidated.png) |
| 161 | 04/09 01:30 | 04:30Z | ETHUSDT | replay | 2521.3418980000 | 2503.4862657079 | 2561.2474685842 | invalidação | -0.92 | 3 | `—` | [20260904-0430Z-ETHUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260904-0430Z-ETHUSDT-invalidated.png) |
| 162 | 04/09 06:00 | 09:00Z | ETHUSDT | replay | 2527.5055940000 | 2506.2212657294 | 2566.8474685411 | invalidação | -0.45 | 5 | `—` | [20260904-0900Z-ETHUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260904-0900Z-ETHUSDT-invalidated.png) |
| 163 | 04/09 06:00 | 09:00Z | DOGEUSDT | replay | 0.0876025300 | 0.0867777206 | 0.0893045588 | invalidação | -0.33 | 2 | `—` | [20260904-0900Z-DOGEUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260904-0900Z-DOGEUSDT-invalidated.png) |
| 164 | 04/09 06:00 | 09:00Z | SOLUSDT | replay | 104.3925980000 | 103.4234064928 | 106.1131870145 | invalidação | -0.38 | 4 | `—` | [20260904-0900Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260904-0900Z-SOLUSDT-invalidated.png) |
| 165 | 05/09 03:45 | 06:45Z | DOGEUSDT | replay | 0.0855212820 | 0.0848055191 | 0.0865889619 | horizonte | +0.45 | 5 | `—` | [20260905-0645Z-DOGEUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260905-0645Z-DOGEUSDT-expired.png) |
| 166 | 05/09 09:45 | 12:45Z | DOGEUSDT | replay | 0.0873323680 | 0.0865328259 | 0.0888643482 | horizonte | +0.03 | 0 | `—` | [20260905-1245Z-DOGEUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260905-1245Z-DOGEUSDT-expired.png) |
| 167 | 05/09 11:45 | 14:45Z | XRPUSDT | replay | 1.4172498400 | 1.4065211582 | 1.4358576837 | invalidação | -0.53 | 6 | `—` | [20260905-1445Z-XRPUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260905-1445Z-XRPUSDT-invalidated.png) |
| 168 | 05/09 14:15 | 17:15Z | XRPUSDT | replay | 1.4190509200 | 1.4111254631 | 1.4413490738 | invalidação | -0.72 | 6 | `—` | [20260905-1715Z-XRPUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260905-1715Z-XRPUSDT-invalidated.png) |
| 169 | 05/09 14:15 | 17:15Z | SOLUSDT | replay | 103.8122500000 | 103.2714044323 | 105.4271911355 | stop | -1.27 | 4 | `—` | [20260905-1715Z-SOLUSDT-stop.png](../../attachments/operacoes/momentum-v7/20260905-1715Z-SOLUSDT-stop.png) |
| 170 | 05/09 15:00 | 18:00Z | DOGEUSDT | replay | 0.0936061300 | 0.0920230959 | 0.0985538083 | stop | -1.08 | 1 | `—` | [20260905-1800Z-DOGEUSDT-stop.png](../../attachments/operacoes/momentum-v7/20260905-1800Z-DOGEUSDT-stop.png) |
| 171 | 05/09 23:00 | 02:00Z | SOLUSDT | replay | 104.1624600000 | 103.2503974766 | 105.4692050467 | alvo | +1.27 | 3 | `—` | [20260906-0200Z-SOLUSDT-target.png](../../attachments/operacoes/momentum-v7/20260906-0200Z-SOLUSDT-target.png) |
| 172 | 06/09 00:45 | 03:45Z | DOGEUSDT | replay | 0.0915749120 | 0.0904863097 | 0.0938273805 | stop | -1.12 | 2 | `—` | [20260906-0345Z-DOGEUSDT-stop.png](../../attachments/operacoes/momentum-v7/20260906-0345Z-DOGEUSDT-stop.png) |
| 173 | 06/09 00:45 | 03:45Z | XRPUSDT | replay | 1.4291569800 | 1.4167326665 | 1.4499346671 | stop | -1.16 | 3 | `—` | [20260906-0345Z-XRPUSDT-stop.png](../../attachments/operacoes/momentum-v7/20260906-0345Z-XRPUSDT-stop.png) |
| 174 | 06/09 06:30 | 09:30Z | SOLUSDT | replay | 107.2142900000 | 105.7222386061 | 109.3755227879 | invalidação | -0.72 | 2 | `—` | [20260906-0930Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260906-0930Z-SOLUSDT-invalidated.png) |
| 175 | 06/09 09:45 | 12:45Z | SOLUSDT | replay | 107.0241760000 | 105.9124548318 | 109.0250903365 | invalidação | -0.36 | 0 | `—` | [20260906-1245Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260906-1245Z-SOLUSDT-invalidated.png) |
| 176 | 06/09 11:00 | 14:00Z | SOLUSDT | replay | 106.9841520000 | 105.8469935932 | 109.3960128137 | invalidação | -0.68 | 1 | `—` | [20260906-1400Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260906-1400Z-SOLUSDT-invalidated.png) |
| 177 | 06/09 17:30 | 20:30Z | DOGEUSDT | replay | 0.0899839580 | 0.0891804405 | 0.0913991191 | horizonte | +1.11 | 1 | `—` | [20260906-2030Z-DOGEUSDT-expired.png](../../attachments/operacoes/momentum-v7/20260906-2030Z-DOGEUSDT-expired.png) |
| 178 | 06/09 23:45 | 02:45Z | ETHUSDT | replay | 2526.5250060000 | 2504.2173228956 | 2570.3453542087 | invalidação | -0.86 | 3 | `—` | [20260907-0245Z-ETHUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260907-0245Z-ETHUSDT-invalidated.png) |
| 179 | 06/09 23:45 | 02:45Z | SOLUSDT | replay | 106.7039840000 | 105.4499891857 | 109.2600216286 | invalidação | -0.89 | 3 | `—` | [20260907-0245Z-SOLUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260907-0245Z-SOLUSDT-invalidated.png) |
| 180 | 07/09 09:30 | 12:30Z | DOGEUSDT | replay | 0.0904342280 | 0.0895280636 | 0.0921138728 | invalidação | -0.98 | 5 | `—` | [20260907-1230Z-DOGEUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260907-1230Z-DOGEUSDT-invalidated.png) |
| 181 | 07/09 10:00 | 13:00Z | SOLUSDT | replay | 105.7434080000 | 104.8635594717 | 107.3128810565 | stop | -1.17 | 4 | `—` | [20260907-1300Z-SOLUSDT-stop.png](../../attachments/operacoes/momentum-v7/20260907-1300Z-SOLUSDT-stop.png) |
| 182 | 07/09 10:00 | 13:00Z | XRPUSDT | replay | 1.4124469600 | 1.4007606937 | 1.4332786127 | invalidação | -0.94 | 2 | `—` | [20260907-1300Z-XRPUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260907-1300Z-XRPUSDT-invalidated.png) |
| 183 | 07/09 20:15 | 23:15Z | DOGEUSDT | replay | 0.0907043900 | 0.0897555441 | 0.0929189118 | invalidação | -0.48 | 1 | `—` | [20260907-2315Z-DOGEUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260907-2315Z-DOGEUSDT-invalidated.png) |
| 184 | 08/09 19:30 | 22:30Z | ZROUSDT | prospective | 1.1410842400 | 1.1267443895 | 1.1983112209 | invalidação | -0.46 | 4 | `—` | [20260908-2230Z-ZROUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260908-2230Z-ZROUSDT-invalidated.png) |
| 185 | 08/09 19:45 | 22:45Z | FFUSDT | prospective | 0.1512907200 | 0.1450788840 | 0.1650322319 | invalidação | -0.31 | 3 | `—` | [20260908-2245Z-FFUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260908-2245Z-FFUSDT-invalidated.png) |
| 186 | 08/09 19:45 | 22:45Z | ATOMUSDT | prospective | 1.8571136000 | 1.8113046369 | 1.9363907262 | invalidação | -0.30 | 2 | `—` | [20260908-2245Z-ATOMUSDT-invalidated.png](../../attachments/operacoes/momentum-v7/20260908-2245Z-ATOMUSDT-invalidated.png) |

## Gráficos

### 001 — DOGEUSDT · 11/08/2026 11:15 BRT · -0.87 R

![DOGEUSDT momentum v7 11/08 11:15 BRT](../../attachments/operacoes/momentum-v7/20260811-1415Z-DOGEUSDT-invalidated.png)

> Momentum 15m: fechamento 0.0711 acima da máxima dos 20 fechamentos anteriores (0.07088), retorno 15m 0.31%, volume relativo 7.28x da mediana de 96 barras, ATR% 0.30%

### 002 — XRPUSDT · 11/08/2026 14:00 BRT · -0.31 R

![XRPUSDT momentum v7 11/08 14:00 BRT](../../attachments/operacoes/momentum-v7/20260811-1700Z-XRPUSDT-invalidated.png)

> Momentum 15m: fechamento 1.0092 acima da máxima dos 20 fechamentos anteriores (1.009), retorno 15m 0.19%, volume relativo 2.42x da mediana de 96 barras, ATR% 0.48%

### 003 — ETHUSDT · 11/08/2026 17:00 BRT · -0.34 R

![ETHUSDT momentum v7 11/08 17:00 BRT](../../attachments/operacoes/momentum-v7/20260811-2000Z-ETHUSDT-expired.png)

> Momentum 15m: fechamento 1881.17 acima da máxima dos 20 fechamentos anteriores (1876.38), retorno 15m 0.54%, volume relativo 7.99x da mediana de 96 barras, ATR% 0.32%

### 004 — DOGEUSDT · 11/08/2026 17:00 BRT · +1.26 R

![DOGEUSDT momentum v7 11/08 17:00 BRT](../../attachments/operacoes/momentum-v7/20260811-2000Z-DOGEUSDT-target.png)

> Momentum 15m: fechamento 0.07101 acima da máxima dos 20 fechamentos anteriores (0.07097), retorno 15m 0.10%, volume relativo 1.58x da mediana de 96 barras, ATR% 0.41%

### 005 — SOLUSDT · 11/08/2026 17:00 BRT · +0.45 R

![SOLUSDT momentum v7 11/08 17:00 BRT](../../attachments/operacoes/momentum-v7/20260811-2000Z-SOLUSDT-expired.png)

> Momentum 15m: fechamento 75.63 acima da máxima dos 20 fechamentos anteriores (75.48), retorno 15m 0.20%, volume relativo 2.57x da mediana de 96 barras, ATR% 0.30%

### 006 — XRPUSDT · 11/08/2026 17:00 BRT · +0.41 R

![XRPUSDT momentum v7 11/08 17:00 BRT](../../attachments/operacoes/momentum-v7/20260811-2000Z-XRPUSDT-expired.png)

> Momentum 15m: fechamento 1.0151 acima da máxima dos 20 fechamentos anteriores (1.0144), retorno 15m 0.17%, volume relativo 1.55x da mediana de 96 barras, ATR% 0.40%

### 007 — DOGEUSDT · 13/08/2026 00:00 BRT · +0.34 R

![DOGEUSDT momentum v7 13/08 00:00 BRT](../../attachments/operacoes/momentum-v7/20260813-0300Z-DOGEUSDT-expired.png)

> Momentum 15m: fechamento 0.07026 acima da máxima dos 20 fechamentos anteriores (0.07001), retorno 15m 0.40%, volume relativo 2.17x da mediana de 96 barras, ATR% 0.32%

### 008 — SOLUSDT · 16/08/2026 22:45 BRT · -0.55 R

![SOLUSDT momentum v7 16/08 22:45 BRT](../../attachments/operacoes/momentum-v7/20260817-0145Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 75.25 acima da máxima dos 20 fechamentos anteriores (75.19), retorno 15m 0.08%, volume relativo 3.69x da mediana de 96 barras, ATR% 0.31%

### 009 — SOLUSDT · 16/08/2026 23:45 BRT · +0.43 R

![SOLUSDT momentum v7 16/08 23:45 BRT](../../attachments/operacoes/momentum-v7/20260817-0245Z-SOLUSDT-expired.png)

> Momentum 15m: fechamento 75.33 acima da máxima dos 20 fechamentos anteriores (75.25), retorno 15m 0.23%, volume relativo 4.49x da mediana de 96 barras, ATR% 0.30%

### 010 — SOLUSDT · 18/08/2026 12:30 BRT · -0.54 R

![SOLUSDT momentum v7 18/08 12:30 BRT](../../attachments/operacoes/momentum-v7/20260818-1530Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 77 acima da máxima dos 20 fechamentos anteriores (76.98), retorno 15m 0.12%, volume relativo 2.01x da mediana de 96 barras, ATR% 0.32%

### 011 — SOLUSDT · 19/08/2026 10:30 BRT · -0.52 R

![SOLUSDT momentum v7 19/08 10:30 BRT](../../attachments/operacoes/momentum-v7/20260819-1330Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 78.47 acima da máxima dos 20 fechamentos anteriores (78.37), retorno 15m 0.26%, volume relativo 2.21x da mediana de 96 barras, ATR% 0.30%

### 012 — SOLUSDT · 19/08/2026 11:45 BRT · +1.49 R

![SOLUSDT momentum v7 19/08 11:45 BRT](../../attachments/operacoes/momentum-v7/20260819-1445Z-SOLUSDT-target.png)

> Momentum 15m: fechamento 78.99 acima da máxima dos 20 fechamentos anteriores (78.58), retorno 15m 0.64%, volume relativo 4.81x da mediana de 96 barras, ATR% 0.36%

### 013 — ETHUSDT · 19/08/2026 12:00 BRT · +1.33 R

![ETHUSDT momentum v7 19/08 12:00 BRT](../../attachments/operacoes/momentum-v7/20260819-1500Z-ETHUSDT-target.png)

> Momentum 15m: fechamento 1969.89 acima da máxima dos 20 fechamentos anteriores (1939.17), retorno 15m 1.58%, volume relativo 29.77x da mediana de 96 barras, ATR% 0.40%

### 014 — XRPUSDT · 19/08/2026 12:00 BRT · +2.07 R

![XRPUSDT momentum v7 19/08 12:00 BRT](../../attachments/operacoes/momentum-v7/20260819-1500Z-XRPUSDT-target.png)

> Momentum 15m: fechamento 1.0327 acima da máxima dos 20 fechamentos anteriores (1.0225), retorno 15m 1.05%, volume relativo 11.26x da mediana de 96 barras, ATR% 0.39%

### 015 — DOGEUSDT · 19/08/2026 12:15 BRT · +1.34 R

![DOGEUSDT momentum v7 19/08 12:15 BRT](../../attachments/operacoes/momentum-v7/20260819-1515Z-DOGEUSDT-target.png)

> Momentum 15m: fechamento 0.07187 acima da máxima dos 20 fechamentos anteriores (0.07125), retorno 15m 0.87%, volume relativo 18.50x da mediana de 96 barras, ATR% 0.37%

### 016 — ETHUSDT · 19/08/2026 13:15 BRT · -0.40 R

![ETHUSDT momentum v7 19/08 13:15 BRT](../../attachments/operacoes/momentum-v7/20260819-1615Z-ETHUSDT-invalidated.png)

> Momentum 15m: fechamento 2088.99 acima da máxima dos 20 fechamentos anteriores (2086.45), retorno 15m 0.18%, volume relativo 20.30x da mediana de 96 barras, ATR% 0.97%

### 017 — ETHUSDT · 19/08/2026 17:00 BRT · +1.69 R

![ETHUSDT momentum v7 19/08 17:00 BRT](../../attachments/operacoes/momentum-v7/20260819-2000Z-ETHUSDT-target.png)

> Momentum 15m: fechamento 2100.97 acima da máxima dos 20 fechamentos anteriores (2099.57), retorno 15m 0.11%, volume relativo 2.76x da mediana de 96 barras, ATR% 0.65%

### 018 — XRPUSDT · 19/08/2026 17:15 BRT · +1.51 R

![XRPUSDT momentum v7 19/08 17:15 BRT](../../attachments/operacoes/momentum-v7/20260819-2015Z-XRPUSDT-target.png)

> Momentum 15m: fechamento 1.0736 acima da máxima dos 20 fechamentos anteriores (1.0694), retorno 15m 0.57%, volume relativo 3.59x da mediana de 96 barras, ATR% 0.58%

### 019 — SOLUSDT · 19/08/2026 18:00 BRT · +1.65 R

![SOLUSDT momentum v7 19/08 18:00 BRT](../../attachments/operacoes/momentum-v7/20260819-2100Z-SOLUSDT-target.png)

> Momentum 15m: fechamento 83.71 acima da máxima dos 20 fechamentos anteriores (82.58), retorno 15m 1.37%, volume relativo 14.31x da mediana de 96 barras, ATR% 0.62%

### 020 — DOGEUSDT · 19/08/2026 18:00 BRT · +1.88 R

![DOGEUSDT momentum v7 19/08 18:00 BRT](../../attachments/operacoes/momentum-v7/20260819-2100Z-DOGEUSDT-target.png)

> Momentum 15m: fechamento 0.07416 acima da máxima dos 20 fechamentos anteriores (0.07339), retorno 15m 1.05%, volume relativo 12.51x da mediana de 96 barras, ATR% 0.58%

### 021 — SOLUSDT · 20/08/2026 03:30 BRT · +1.72 R

![SOLUSDT momentum v7 20/08 03:30 BRT](../../attachments/operacoes/momentum-v7/20260820-0630Z-SOLUSDT-target.png)

> Momentum 15m: fechamento 85.44 acima da máxima dos 20 fechamentos anteriores (85.36), retorno 15m 0.77%, volume relativo 2.44x da mediana de 96 barras, ATR% 0.45%

### 022 — DOGEUSDT · 20/08/2026 05:15 BRT · +0.50 R

![DOGEUSDT momentum v7 20/08 05:15 BRT](../../attachments/operacoes/momentum-v7/20260820-0815Z-DOGEUSDT-expired.png)

> Momentum 15m: fechamento 0.07645 acima da máxima dos 20 fechamentos anteriores (0.07531), retorno 15m 1.51%, volume relativo 3.70x da mediana de 96 barras, ATR% 0.52%

### 023 — XRPUSDT · 20/08/2026 05:15 BRT · +2.17 R

![XRPUSDT momentum v7 20/08 05:15 BRT](../../attachments/operacoes/momentum-v7/20260820-0815Z-XRPUSDT-target.png)

> Momentum 15m: fechamento 1.1284 acima da máxima dos 20 fechamentos anteriores (1.1128), retorno 15m 1.47%, volume relativo 2.71x da mediana de 96 barras, ATR% 0.53%

### 024 — ETHUSDT · 20/08/2026 05:15 BRT · -0.28 R

![ETHUSDT momentum v7 20/08 05:15 BRT](../../attachments/operacoes/momentum-v7/20260820-0815Z-ETHUSDT-expired.png)

> Momentum 15m: fechamento 2283.71 acima da máxima dos 20 fechamentos anteriores (2262.1), retorno 15m 1.43%, volume relativo 3.87x da mediana de 96 barras, ATR% 0.57%

### 025 — XRPUSDT · 20/08/2026 08:45 BRT · +1.31 R

![XRPUSDT momentum v7 20/08 08:45 BRT](../../attachments/operacoes/momentum-v7/20260820-1145Z-XRPUSDT-target.png)

> Momentum 15m: fechamento 1.1889 acima da máxima dos 20 fechamentos anteriores (1.1675), retorno 15m 1.83%, volume relativo 4.70x da mediana de 96 barras, ATR% 0.79%

### 026 — DOGEUSDT · 20/08/2026 10:30 BRT · -0.20 R

![DOGEUSDT momentum v7 20/08 10:30 BRT](../../attachments/operacoes/momentum-v7/20260820-1330Z-DOGEUSDT-invalidated.png)

> Momentum 15m: fechamento 0.07776 acima da máxima dos 20 fechamentos anteriores (0.07753), retorno 15m 0.61%, volume relativo 1.52x da mediana de 96 barras, ATR% 0.64%

### 027 — DOGEUSDT · 20/08/2026 11:15 BRT · -0.32 R

![DOGEUSDT momentum v7 20/08 11:15 BRT](../../attachments/operacoes/momentum-v7/20260820-1415Z-DOGEUSDT-invalidated.png)

> Momentum 15m: fechamento 0.078 acima da máxima dos 20 fechamentos anteriores (0.07776), retorno 15m 0.71%, volume relativo 1.98x da mediana de 96 barras, ATR% 0.70%

### 028 — DOGEUSDT · 20/08/2026 12:00 BRT · +1.91 R

![DOGEUSDT momentum v7 20/08 12:00 BRT](../../attachments/operacoes/momentum-v7/20260820-1500Z-DOGEUSDT-target.png)

> Momentum 15m: fechamento 0.07844 acima da máxima dos 20 fechamentos anteriores (0.078), retorno 15m 0.59%, volume relativo 2.54x da mediana de 96 barras, ATR% 0.72%

### 029 — XRPUSDT · 20/08/2026 12:15 BRT · +2.21 R

![XRPUSDT momentum v7 20/08 12:15 BRT](../../attachments/operacoes/momentum-v7/20260820-1515Z-XRPUSDT-target.png)

> Momentum 15m: fechamento 1.2618 acima da máxima dos 20 fechamentos anteriores (1.2386), retorno 15m 2.82%, volume relativo 4.99x da mediana de 96 barras, ATR% 1.23%

### 030 — ETHUSDT · 20/08/2026 12:30 BRT · -0.43 R

![ETHUSDT momentum v7 20/08 12:30 BRT](../../attachments/operacoes/momentum-v7/20260820-1530Z-ETHUSDT-invalidated.png)

> Momentum 15m: fechamento 2312.98 acima da máxima dos 20 fechamentos anteriores (2306.25), retorno 15m 0.69%, volume relativo 2.91x da mediana de 96 barras, ATR% 0.72%

### 031 — ETHUSDT · 20/08/2026 13:45 BRT · -0.57 R

![ETHUSDT momentum v7 20/08 13:45 BRT](../../attachments/operacoes/momentum-v7/20260820-1645Z-ETHUSDT-invalidated.png)

> Momentum 15m: fechamento 2348.25 acima da máxima dos 20 fechamentos anteriores (2325.2), retorno 15m 0.99%, volume relativo 3.33x da mediana de 96 barras, ATR% 0.83%

### 032 — DOGEUSDT · 20/08/2026 21:30 BRT · +0.48 R

![DOGEUSDT momentum v7 20/08 21:30 BRT](../../attachments/operacoes/momentum-v7/20260821-0030Z-DOGEUSDT-expired.png)

> Momentum 15m: fechamento 0.08107 acima da máxima dos 20 fechamentos anteriores (0.08069), retorno 15m 0.47%, volume relativo 3.18x da mediana de 96 barras, ATR% 0.75%

### 033 — SOLUSDT · 20/08/2026 21:30 BRT · -0.61 R

![SOLUSDT momentum v7 20/08 21:30 BRT](../../attachments/operacoes/momentum-v7/20260821-0030Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 88.38 acima da máxima dos 20 fechamentos anteriores (87.93), retorno 15m 0.51%, volume relativo 3.49x da mediana de 96 barras, ATR% 0.46%

### 034 — ETHUSDT · 20/08/2026 22:30 BRT · -0.32 R

![ETHUSDT momentum v7 20/08 22:30 BRT](../../attachments/operacoes/momentum-v7/20260821-0130Z-ETHUSDT-invalidated.png)

> Momentum 15m: fechamento 2352.3 acima da máxima dos 20 fechamentos anteriores (2344.74), retorno 15m 0.32%, volume relativo 3.81x da mediana de 96 barras, ATR% 0.60%

### 035 — SOLUSDT · 20/08/2026 23:00 BRT · +1.27 R

![SOLUSDT momentum v7 20/08 23:00 BRT](../../attachments/operacoes/momentum-v7/20260821-0200Z-SOLUSDT-expired.png)

> Momentum 15m: fechamento 88.99 acima da máxima dos 20 fechamentos anteriores (88.47), retorno 15m 0.59%, volume relativo 3.51x da mediana de 96 barras, ATR% 0.59%

### 036 — XRPUSDT · 20/08/2026 23:00 BRT · -0.22 R

![XRPUSDT momentum v7 20/08 23:00 BRT](../../attachments/operacoes/momentum-v7/20260821-0200Z-XRPUSDT-invalidated.png)

> Momentum 15m: fechamento 1.2957 acima da máxima dos 20 fechamentos anteriores (1.2889), retorno 15m 0.68%, volume relativo 1.60x da mediana de 96 barras, ATR% 1.02%

### 037 — DOGEUSDT · 21/08/2026 03:30 BRT · +0.34 R

![DOGEUSDT momentum v7 21/08 03:30 BRT](../../attachments/operacoes/momentum-v7/20260821-0630Z-DOGEUSDT-expired.png)

> Momentum 15m: fechamento 0.08336 acima da máxima dos 20 fechamentos anteriores (0.08295), retorno 15m 0.49%, volume relativo 2.13x da mediana de 96 barras, ATR% 0.72%

### 038 — XRPUSDT · 21/08/2026 05:15 BRT · +1.46 R

![XRPUSDT momentum v7 21/08 05:15 BRT](../../attachments/operacoes/momentum-v7/20260821-0815Z-XRPUSDT-target.png)

> Momentum 15m: fechamento 1.3455 acima da máxima dos 20 fechamentos anteriores (1.3189), retorno 15m 2.41%, volume relativo 2.80x da mediana de 96 barras, ATR% 1.03%

### 039 — SOLUSDT · 21/08/2026 05:30 BRT · -1.08 R

![SOLUSDT momentum v7 21/08 05:30 BRT](../../attachments/operacoes/momentum-v7/20260821-0830Z-SOLUSDT-stop.png)

> Momentum 15m: fechamento 91.37 acima da máxima dos 20 fechamentos anteriores (90.78), retorno 15m 0.71%, volume relativo 2.74x da mediana de 96 barras, ATR% 0.71%

### 040 — ETHUSDT · 21/08/2026 05:30 BRT · -0.53 R

![ETHUSDT momentum v7 21/08 05:30 BRT](../../attachments/operacoes/momentum-v7/20260821-0830Z-ETHUSDT-invalidated.png)

> Momentum 15m: fechamento 2386.98 acima da máxima dos 20 fechamentos anteriores (2385.55), retorno 15m 0.15%, volume relativo 1.64x da mediana de 96 barras, ATR% 0.62%

### 041 — ETHUSDT · 21/08/2026 14:15 BRT · +0.90 R

![ETHUSDT momentum v7 21/08 14:15 BRT](../../attachments/operacoes/momentum-v7/20260821-1715Z-ETHUSDT-expired.png)

> Momentum 15m: fechamento 2414.95 acima da máxima dos 20 fechamentos anteriores (2405.13), retorno 15m 0.41%, volume relativo 1.58x da mediana de 96 barras, ATR% 0.67%

### 042 — DOGEUSDT · 21/08/2026 17:45 BRT · +1.91 R

![DOGEUSDT momentum v7 21/08 17:45 BRT](../../attachments/operacoes/momentum-v7/20260821-2045Z-DOGEUSDT-target.png)

> Momentum 15m: fechamento 0.08666 acima da máxima dos 20 fechamentos anteriores (0.08542), retorno 15m 1.45%, volume relativo 4.71x da mediana de 96 barras, ATR% 0.93%

### 043 — SOLUSDT · 21/08/2026 18:30 BRT · +0.73 R

![SOLUSDT momentum v7 21/08 18:30 BRT](../../attachments/operacoes/momentum-v7/20260821-2130Z-SOLUSDT-expired.png)

> Momentum 15m: fechamento 92.8 acima da máxima dos 20 fechamentos anteriores (92.28), retorno 15m 0.56%, volume relativo 1.73x da mediana de 96 barras, ATR% 0.64%

### 044 — XRPUSDT · 21/08/2026 19:15 BRT · +1.98 R

![XRPUSDT momentum v7 21/08 19:15 BRT](../../attachments/operacoes/momentum-v7/20260821-2215Z-XRPUSDT-target.png)

> Momentum 15m: fechamento 1.4262 acima da máxima dos 20 fechamentos anteriores (1.4063), retorno 15m 1.42%, volume relativo 3.37x da mediana de 96 barras, ATR% 1.14%

### 045 — DOGEUSDT · 21/08/2026 19:45 BRT · -0.37 R

![DOGEUSDT momentum v7 21/08 19:45 BRT](../../attachments/operacoes/momentum-v7/20260821-2245Z-DOGEUSDT-invalidated.png)

> Momentum 15m: fechamento 0.09388 acima da máxima dos 20 fechamentos anteriores (0.09343), retorno 15m 0.64%, volume relativo 3.69x da mediana de 96 barras, ATR% 1.36%

### 046 — XRPUSDT · 21/08/2026 23:15 BRT · +1.69 R

![XRPUSDT momentum v7 21/08 23:15 BRT](../../attachments/operacoes/momentum-v7/20260822-0215Z-XRPUSDT-target.png)

> Momentum 15m: fechamento 1.5016 acima da máxima dos 20 fechamentos anteriores (1.4955), retorno 15m 1.78%, volume relativo 1.59x da mediana de 96 barras, ATR% 1.59%

### 047 — SOLUSDT · 21/08/2026 23:45 BRT · +2.11 R

![SOLUSDT momentum v7 21/08 23:45 BRT](../../attachments/operacoes/momentum-v7/20260822-0245Z-SOLUSDT-target.png)

> Momentum 15m: fechamento 95.71 acima da máxima dos 20 fechamentos anteriores (94.84), retorno 15m 0.92%, volume relativo 2.17x da mediana de 96 barras, ATR% 0.79%

### 048 — DOGEUSDT · 22/08/2026 00:30 BRT · -1.05 R

![DOGEUSDT momentum v7 22/08 00:30 BRT](../../attachments/operacoes/momentum-v7/20260822-0330Z-DOGEUSDT-stop.png)

> Momentum 15m: fechamento 0.0967 acima da máxima dos 20 fechamentos anteriores (0.09418), retorno 15m 3.27%, volume relativo 4.02x da mediana de 96 barras, ATR% 1.28%

### 049 — DOGEUSDT · 22/08/2026 14:30 BRT · +0.27 R

![DOGEUSDT momentum v7 22/08 14:30 BRT](../../attachments/operacoes/momentum-v7/20260822-1730Z-DOGEUSDT-expired.png)

> Momentum 15m: fechamento 0.09204 acima da máxima dos 20 fechamentos anteriores (0.09195), retorno 15m 0.10%, volume relativo 1.51x da mediana de 96 barras, ATR% 1.09%

### 050 — ETHUSDT · 22/08/2026 17:00 BRT · -0.58 R

![ETHUSDT momentum v7 22/08 17:00 BRT](../../attachments/operacoes/momentum-v7/20260822-2000Z-ETHUSDT-invalidated.png)

> Momentum 15m: fechamento 2438.18 acima da máxima dos 20 fechamentos anteriores (2433.81), retorno 15m 0.18%, volume relativo 1.59x da mediana de 96 barras, ATR% 0.35%

### 051 — SOLUSDT · 22/08/2026 21:45 BRT · -1.05 R

![SOLUSDT momentum v7 22/08 21:45 BRT](../../attachments/operacoes/momentum-v7/20260823-0045Z-SOLUSDT-stop.png)

> Momentum 15m: fechamento 96.35 acima da máxima dos 20 fechamentos anteriores (94.76), retorno 15m 2.16%, volume relativo 10.28x da mediana de 96 barras, ATR% 0.95%

### 052 — ETHUSDT · 23/08/2026 05:45 BRT · -0.44 R

![ETHUSDT momentum v7 23/08 05:45 BRT](../../attachments/operacoes/momentum-v7/20260823-0845Z-ETHUSDT-invalidated.png)

> Momentum 15m: fechamento 2419.37 acima da máxima dos 20 fechamentos anteriores (2413.68), retorno 15m 0.53%, volume relativo 4.18x da mediana de 96 barras, ATR% 0.51%

### 053 — DOGEUSDT · 23/08/2026 07:30 BRT · +1.14 R

![DOGEUSDT momentum v7 23/08 07:30 BRT](../../attachments/operacoes/momentum-v7/20260823-1030Z-DOGEUSDT-expired.png)

> Momentum 15m: fechamento 0.09194 acima da máxima dos 20 fechamentos anteriores (0.09142), retorno 15m 0.59%, volume relativo 2.63x da mediana de 96 barras, ATR% 0.79%

### 054 — XRPUSDT · 23/08/2026 08:30 BRT · -0.18 R

![XRPUSDT momentum v7 23/08 08:30 BRT](../../attachments/operacoes/momentum-v7/20260823-1130Z-XRPUSDT-invalidated.png)

> Momentum 15m: fechamento 1.4927 acima da máxima dos 20 fechamentos anteriores (1.491), retorno 15m 0.86%, volume relativo 1.70x da mediana de 96 barras, ATR% 1.00%

### 055 — ETHUSDT · 23/08/2026 08:30 BRT · +1.54 R

![ETHUSDT momentum v7 23/08 08:30 BRT](../../attachments/operacoes/momentum-v7/20260823-1130Z-ETHUSDT-target.png)

> Momentum 15m: fechamento 2426.92 acima da máxima dos 20 fechamentos anteriores (2420.05), retorno 15m 0.28%, volume relativo 3.78x da mediana de 96 barras, ATR% 0.41%

### 056 — SOLUSDT · 23/08/2026 08:30 BRT · -1.09 R

![SOLUSDT momentum v7 23/08 08:30 BRT](../../attachments/operacoes/momentum-v7/20260823-1130Z-SOLUSDT-stop.png)

> Momentum 15m: fechamento 94.32 acima da máxima dos 20 fechamentos anteriores (93.85), retorno 15m 0.50%, volume relativo 2.32x da mediana de 96 barras, ATR% 0.59%

### 057 — XRPUSDT · 23/08/2026 10:30 BRT · -1.06 R

![XRPUSDT momentum v7 23/08 10:30 BRT](../../attachments/operacoes/momentum-v7/20260823-1330Z-XRPUSDT-stop.png)

> Momentum 15m: fechamento 1.5048 acima da máxima dos 20 fechamentos anteriores (1.5014), retorno 15m 0.23%, volume relativo 3.58x da mediana de 96 barras, ATR% 0.93%

### 058 — ETHUSDT · 23/08/2026 18:15 BRT · -1.13 R

![ETHUSDT momentum v7 23/08 18:15 BRT](../../attachments/operacoes/momentum-v7/20260823-2115Z-ETHUSDT-stop.png)

> Momentum 15m: fechamento 2465.05 acima da máxima dos 20 fechamentos anteriores (2449.7), retorno 15m 0.65%, volume relativo 3.05x da mediana de 96 barras, ATR% 0.44%

### 059 — SOLUSDT · 23/08/2026 18:15 BRT · -0.55 R

![SOLUSDT momentum v7 23/08 18:15 BRT](../../attachments/operacoes/momentum-v7/20260823-2115Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 95.65 acima da máxima dos 20 fechamentos anteriores (95.54), retorno 15m 0.61%, volume relativo 1.63x da mediana de 96 barras, ATR% 0.48%

### 060 — XRPUSDT · 23/08/2026 18:30 BRT · -0.63 R

![XRPUSDT momentum v7 23/08 18:30 BRT](../../attachments/operacoes/momentum-v7/20260823-2130Z-XRPUSDT-invalidated.png)

> Momentum 15m: fechamento 1.5355 acima da máxima dos 20 fechamentos anteriores (1.5198), retorno 15m 1.03%, volume relativo 1.55x da mediana de 96 barras, ATR% 0.96%

### 061 — ETHUSDT · 24/08/2026 04:15 BRT · -0.69 R

![ETHUSDT momentum v7 24/08 04:15 BRT](../../attachments/operacoes/momentum-v7/20260824-0715Z-ETHUSDT-invalidated.png)

> Momentum 15m: fechamento 2469.5 acima da máxima dos 20 fechamentos anteriores (2457.16), retorno 15m 0.57%, volume relativo 2.42x da mediana de 96 barras, ATR% 0.54%

### 062 — SOLUSDT · 24/08/2026 04:15 BRT · -0.80 R

![SOLUSDT momentum v7 24/08 04:15 BRT](../../attachments/operacoes/momentum-v7/20260824-0715Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 95.31 acima da máxima dos 20 fechamentos anteriores (94.78), retorno 15m 0.81%, volume relativo 2.09x da mediana de 96 barras, ATR% 0.65%

### 063 — XRPUSDT · 24/08/2026 04:15 BRT · -0.68 R

![XRPUSDT momentum v7 24/08 04:15 BRT](../../attachments/operacoes/momentum-v7/20260824-0715Z-XRPUSDT-invalidated.png)

> Momentum 15m: fechamento 1.4971 acima da máxima dos 20 fechamentos anteriores (1.489), retorno 15m 0.91%, volume relativo 1.66x da mediana de 96 barras, ATR% 1.01%

### 064 — ETHUSDT · 24/08/2026 07:15 BRT · -0.70 R

![ETHUSDT momentum v7 24/08 07:15 BRT](../../attachments/operacoes/momentum-v7/20260824-1015Z-ETHUSDT-invalidated.png)

> Momentum 15m: fechamento 2482.26 acima da máxima dos 20 fechamentos anteriores (2469.5), retorno 15m 0.81%, volume relativo 6.06x da mediana de 96 barras, ATR% 0.50%

### 065 — XRPUSDT · 24/08/2026 08:45 BRT · -0.40 R

![XRPUSDT momentum v7 24/08 08:45 BRT](../../attachments/operacoes/momentum-v7/20260824-1145Z-XRPUSDT-invalidated.png)

> Momentum 15m: fechamento 1.508 acima da máxima dos 20 fechamentos anteriores (1.4971), retorno 15m 1.48%, volume relativo 2.17x da mediana de 96 barras, ATR% 0.86%

### 066 — DOGEUSDT · 24/08/2026 08:45 BRT · -0.32 R

![DOGEUSDT momentum v7 24/08 08:45 BRT](../../attachments/operacoes/momentum-v7/20260824-1145Z-DOGEUSDT-invalidated.png)

> Momentum 15m: fechamento 0.09271 acima da máxima dos 20 fechamentos anteriores (0.0925), retorno 15m 1.49%, volume relativo 2.70x da mediana de 96 barras, ATR% 0.73%

### 067 — SOLUSDT · 24/08/2026 08:45 BRT · -0.85 R

![SOLUSDT momentum v7 24/08 08:45 BRT](../../attachments/operacoes/momentum-v7/20260824-1145Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 96.25 acima da máxima dos 20 fechamentos anteriores (95.31), retorno 15m 1.43%, volume relativo 4.10x da mediana de 96 barras, ATR% 0.59%

### 068 — ETHUSDT · 24/08/2026 08:45 BRT · -1.13 R

![ETHUSDT momentum v7 24/08 08:45 BRT](../../attachments/operacoes/momentum-v7/20260824-1145Z-ETHUSDT-stop.png)

> Momentum 15m: fechamento 2505.94 acima da máxima dos 20 fechamentos anteriores (2482.26), retorno 15m 1.39%, volume relativo 6.26x da mediana de 96 barras, ATR% 0.56%

### 069 — SOLUSDT · 24/08/2026 10:00 BRT · -0.18 R

![SOLUSDT momentum v7 24/08 10:00 BRT](../../attachments/operacoes/momentum-v7/20260824-1300Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 96.26 acima da máxima dos 20 fechamentos anteriores (96.25), retorno 15m 0.34%, volume relativo 3.11x da mediana de 96 barras, ATR% 0.73%

### 070 — DOGEUSDT · 24/08/2026 10:00 BRT · -0.47 R

![DOGEUSDT momentum v7 24/08 10:00 BRT](../../attachments/operacoes/momentum-v7/20260824-1300Z-DOGEUSDT-invalidated.png)

> Momentum 15m: fechamento 0.09323 acima da máxima dos 20 fechamentos anteriores (0.09271), retorno 15m 0.73%, volume relativo 2.39x da mediana de 96 barras, ATR% 0.80%

### 071 — XRPUSDT · 24/08/2026 10:00 BRT · -1.07 R

![XRPUSDT momentum v7 24/08 10:00 BRT](../../attachments/operacoes/momentum-v7/20260824-1300Z-XRPUSDT-stop.png)

> Momentum 15m: fechamento 1.5167 acima da máxima dos 20 fechamentos anteriores (1.508), retorno 15m 0.98%, volume relativo 2.14x da mediana de 96 barras, ATR% 0.92%

### 072 — ETHUSDT · 24/08/2026 10:00 BRT · -0.83 R

![ETHUSDT momentum v7 24/08 10:00 BRT](../../attachments/operacoes/momentum-v7/20260824-1300Z-ETHUSDT-invalidated.png)

> Momentum 15m: fechamento 2511.99 acima da máxima dos 20 fechamentos anteriores (2505.94), retorno 15m 0.51%, volume relativo 4.49x da mediana de 96 barras, ATR% 0.63%

### 073 — ETHUSDT · 24/08/2026 11:30 BRT · -0.25 R

![ETHUSDT momentum v7 24/08 11:30 BRT](../../attachments/operacoes/momentum-v7/20260824-1430Z-ETHUSDT-invalidated.png)

> Momentum 15m: fechamento 2516.21 acima da máxima dos 20 fechamentos anteriores (2514.97), retorno 15m 0.23%, volume relativo 4.48x da mediana de 96 barras, ATR% 0.70%

### 074 — XRPUSDT · 24/08/2026 11:45 BRT · -0.42 R

![XRPUSDT momentum v7 24/08 11:45 BRT](../../attachments/operacoes/momentum-v7/20260824-1445Z-XRPUSDT-invalidated.png)

> Momentum 15m: fechamento 1.5221 acima da máxima dos 20 fechamentos anteriores (1.5176), retorno 15m 1.15%, volume relativo 2.76x da mediana de 96 barras, ATR% 1.08%

### 075 — SOLUSDT · 24/08/2026 11:45 BRT · -0.29 R

![SOLUSDT momentum v7 24/08 11:45 BRT](../../attachments/operacoes/momentum-v7/20260824-1445Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 96.45 acima da máxima dos 20 fechamentos anteriores (96.36), retorno 15m 0.73%, volume relativo 3.03x da mediana de 96 barras, ATR% 0.81%

### 076 — SOLUSDT · 24/08/2026 12:30 BRT · -0.52 R

![SOLUSDT momentum v7 24/08 12:30 BRT](../../attachments/operacoes/momentum-v7/20260824-1530Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 97.3 acima da máxima dos 20 fechamentos anteriores (96.45), retorno 15m 1.08%, volume relativo 3.66x da mediana de 96 barras, ATR% 0.85%

### 077 — SOLUSDT · 24/08/2026 19:45 BRT · -0.33 R

![SOLUSDT momentum v7 24/08 19:45 BRT](../../attachments/operacoes/momentum-v7/20260824-2245Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 97.64 acima da máxima dos 20 fechamentos anteriores (97.51), retorno 15m 0.13%, volume relativo 3.46x da mediana de 96 barras, ATR% 0.69%

### 078 — SOLUSDT · 24/08/2026 21:15 BRT · +0.92 R

![SOLUSDT momentum v7 24/08 21:15 BRT](../../attachments/operacoes/momentum-v7/20260825-0015Z-SOLUSDT-expired.png)

> Momentum 15m: fechamento 100.58 acima da máxima dos 20 fechamentos anteriores (98.96), retorno 15m 1.64%, volume relativo 9.37x da mediana de 96 barras, ATR% 0.94%

### 079 — XRPUSDT · 24/08/2026 21:45 BRT · -0.18 R

![XRPUSDT momentum v7 24/08 21:45 BRT](../../attachments/operacoes/momentum-v7/20260825-0045Z-XRPUSDT-expired.png)

> Momentum 15m: fechamento 1.5086 acima da máxima dos 20 fechamentos anteriores (1.4883), retorno 15m 1.75%, volume relativo 1.65x da mediana de 96 barras, ATR% 0.82%

### 080 — DOGEUSDT · 24/08/2026 22:00 BRT · -0.39 R

![DOGEUSDT momentum v7 24/08 22:00 BRT](../../attachments/operacoes/momentum-v7/20260825-0100Z-DOGEUSDT-invalidated.png)

> Momentum 15m: fechamento 0.0914 acima da máxima dos 20 fechamentos anteriores (0.09116), retorno 15m 0.26%, volume relativo 1.77x da mediana de 96 barras, ATR% 0.70%

### 081 — ETHUSDT · 24/08/2026 22:00 BRT · -0.40 R

![ETHUSDT momentum v7 24/08 22:00 BRT](../../attachments/operacoes/momentum-v7/20260825-0100Z-ETHUSDT-invalidated.png)

> Momentum 15m: fechamento 2492.2 acima da máxima dos 20 fechamentos anteriores (2491.54), retorno 15m 0.03%, volume relativo 2.38x da mediana de 96 barras, ATR% 0.44%

### 082 — DOGEUSDT · 24/08/2026 23:30 BRT · -0.27 R

![DOGEUSDT momentum v7 24/08 23:30 BRT](../../attachments/operacoes/momentum-v7/20260825-0230Z-DOGEUSDT-expired.png)

> Momentum 15m: fechamento 0.09292 acima da máxima dos 20 fechamentos anteriores (0.0914), retorno 15m 2.19%, volume relativo 3.48x da mediana de 96 barras, ATR% 0.77%

### 083 — ETHUSDT · 24/08/2026 23:30 BRT · -1.12 R

![ETHUSDT momentum v7 24/08 23:30 BRT](../../attachments/operacoes/momentum-v7/20260825-0230Z-ETHUSDT-stop.png)

> Momentum 15m: fechamento 2528.89 acima da máxima dos 20 fechamentos anteriores (2497.38), retorno 15m 1.43%, volume relativo 5.75x da mediana de 96 barras, ATR% 0.52%

### 084 — SOLUSDT · 25/08/2026 02:30 BRT · -0.48 R

![SOLUSDT momentum v7 25/08 02:30 BRT](../../attachments/operacoes/momentum-v7/20260825-0530Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 102.68 acima da máxima dos 20 fechamentos anteriores (102.25), retorno 15m 0.80%, volume relativo 1.80x da mediana de 96 barras, ATR% 0.97%

### 085 — SOLUSDT · 26/08/2026 07:45 BRT · -0.63 R

![SOLUSDT momentum v7 26/08 07:45 BRT](../../attachments/operacoes/momentum-v7/20260826-1045Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 97.35 acima da máxima dos 20 fechamentos anteriores (97.18), retorno 15m 0.75%, volume relativo 2.20x da mediana de 96 barras, ATR% 0.45%

### 086 — DOGEUSDT · 26/08/2026 08:00 BRT · -0.24 R

![DOGEUSDT momentum v7 26/08 08:00 BRT](../../attachments/operacoes/momentum-v7/20260826-1100Z-DOGEUSDT-invalidated.png)

> Momentum 15m: fechamento 0.08681 acima da máxima dos 20 fechamentos anteriores (0.08678), retorno 15m 0.03%, volume relativo 1.50x da mediana de 96 barras, ATR% 0.49%

### 087 — ETHUSDT · 26/08/2026 08:00 BRT · -0.57 R

![ETHUSDT momentum v7 26/08 08:00 BRT](../../attachments/operacoes/momentum-v7/20260826-1100Z-ETHUSDT-invalidated.png)

> Momentum 15m: fechamento 2467.67 acima da máxima dos 20 fechamentos anteriores (2464.17), retorno 15m 0.14%, volume relativo 2.32x da mediana de 96 barras, ATR% 0.35%

### 088 — ETHUSDT · 26/08/2026 15:15 BRT · -0.33 R

![ETHUSDT momentum v7 26/08 15:15 BRT](../../attachments/operacoes/momentum-v7/20260826-1815Z-ETHUSDT-invalidated.png)

> Momentum 15m: fechamento 2466.38 acima da máxima dos 20 fechamentos anteriores (2461.98), retorno 15m 0.26%, volume relativo 1.88x da mediana de 96 barras, ATR% 0.45%

### 089 — ETHUSDT · 26/08/2026 16:30 BRT · -0.49 R

![ETHUSDT momentum v7 26/08 16:30 BRT](../../attachments/operacoes/momentum-v7/20260826-1930Z-ETHUSDT-invalidated.png)

> Momentum 15m: fechamento 2479.11 acima da máxima dos 20 fechamentos anteriores (2471.72), retorno 15m 0.39%, volume relativo 2.88x da mediana de 96 barras, ATR% 0.41%

### 090 — SOLUSDT · 26/08/2026 18:15 BRT · +1.66 R

![SOLUSDT momentum v7 26/08 18:15 BRT](../../attachments/operacoes/momentum-v7/20260826-2115Z-SOLUSDT-target.png)

> Momentum 15m: fechamento 97.48 acima da máxima dos 20 fechamentos anteriores (97.12), retorno 15m 0.62%, volume relativo 1.75x da mediana de 96 barras, ATR% 0.50%

### 091 — ETHUSDT · 26/08/2026 18:15 BRT · -0.28 R

![ETHUSDT momentum v7 26/08 18:15 BRT](../../attachments/operacoes/momentum-v7/20260826-2115Z-ETHUSDT-expired.png)

> Momentum 15m: fechamento 2491.86 acima da máxima dos 20 fechamentos anteriores (2479.11), retorno 15m 0.83%, volume relativo 3.93x da mediana de 96 barras, ATR% 0.42%

### 092 — DOGEUSDT · 26/08/2026 18:30 BRT · +1.24 R

![DOGEUSDT momentum v7 26/08 18:30 BRT](../../attachments/operacoes/momentum-v7/20260826-2130Z-DOGEUSDT-expired.png)

> Momentum 15m: fechamento 0.0861 acima da máxima dos 20 fechamentos anteriores (0.08581), retorno 15m 0.34%, volume relativo 2.00x da mediana de 96 barras, ATR% 0.55%

### 093 — XRPUSDT · 26/08/2026 19:15 BRT · -0.34 R

![XRPUSDT momentum v7 26/08 19:15 BRT](../../attachments/operacoes/momentum-v7/20260826-2215Z-XRPUSDT-invalidated.png)

> Momentum 15m: fechamento 1.4035 acima da máxima dos 20 fechamentos anteriores (1.4004), retorno 15m 0.22%, volume relativo 1.62x da mediana de 96 barras, ATR% 0.68%

### 094 — SOLUSDT · 26/08/2026 20:15 BRT · +0.18 R

![SOLUSDT momentum v7 26/08 20:15 BRT](../../attachments/operacoes/momentum-v7/20260826-2315Z-SOLUSDT-expired.png)

> Momentum 15m: fechamento 100.32 acima da máxima dos 20 fechamentos anteriores (100.16), retorno 15m 0.67%, volume relativo 2.67x da mediana de 96 barras, ATR% 0.69%

### 095 — SOLUSDT · 27/08/2026 03:00 BRT · -0.46 R

![SOLUSDT momentum v7 27/08 03:00 BRT](../../attachments/operacoes/momentum-v7/20260827-0600Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 102.02 acima da máxima dos 20 fechamentos anteriores (101.66), retorno 15m 0.78%, volume relativo 2.65x da mediana de 96 barras, ATR% 0.65%

### 096 — DOGEUSDT · 27/08/2026 05:15 BRT · +0.33 R

![DOGEUSDT momentum v7 27/08 05:15 BRT](../../attachments/operacoes/momentum-v7/20260827-0815Z-DOGEUSDT-expired.png)

> Momentum 15m: fechamento 0.08825 acima da máxima dos 20 fechamentos anteriores (0.0871), retorno 15m 1.32%, volume relativo 5.47x da mediana de 96 barras, ATR% 0.51%

### 097 — XRPUSDT · 27/08/2026 05:15 BRT · +0.28 R

![XRPUSDT momentum v7 27/08 05:15 BRT](../../attachments/operacoes/momentum-v7/20260827-0815Z-XRPUSDT-expired.png)

> Momentum 15m: fechamento 1.4262 acima da máxima dos 20 fechamentos anteriores (1.4118), retorno 15m 1.04%, volume relativo 5.09x da mediana de 96 barras, ATR% 0.60%

### 098 — SOLUSDT · 27/08/2026 05:15 BRT · +1.00 R

![SOLUSDT momentum v7 27/08 05:15 BRT](../../attachments/operacoes/momentum-v7/20260827-0815Z-SOLUSDT-expired.png)

> Momentum 15m: fechamento 102.99 acima da máxima dos 20 fechamentos anteriores (102.02), retorno 15m 1.20%, volume relativo 8.23x da mediana de 96 barras, ATR% 0.69%

### 099 — ETHUSDT · 27/08/2026 05:15 BRT · +2.31 R

![ETHUSDT momentum v7 27/08 05:15 BRT](../../attachments/operacoes/momentum-v7/20260827-0815Z-ETHUSDT-target.png)

> Momentum 15m: fechamento 2519.09 acima da máxima dos 20 fechamentos anteriores (2496.78), retorno 15m 0.92%, volume relativo 8.40x da mediana de 96 barras, ATR% 0.36%

### 100 — SOLUSDT · 27/08/2026 11:00 BRT · +1.01 R

![SOLUSDT momentum v7 27/08 11:00 BRT](../../attachments/operacoes/momentum-v7/20260827-1400Z-SOLUSDT-expired.png)

> Momentum 15m: fechamento 105.99 acima da máxima dos 20 fechamentos anteriores (105.36), retorno 15m 1.36%, volume relativo 5.72x da mediana de 96 barras, ATR% 0.76%

### 101 — XRPUSDT · 27/08/2026 11:30 BRT · -0.65 R

![XRPUSDT momentum v7 27/08 11:30 BRT](../../attachments/operacoes/momentum-v7/20260827-1430Z-XRPUSDT-invalidated.png)

> Momentum 15m: fechamento 1.4587 acima da máxima dos 20 fechamentos anteriores (1.4499), retorno 15m 0.90%, volume relativo 4.01x da mediana de 96 barras, ATR% 0.80%

### 102 — DOGEUSDT · 27/08/2026 11:45 BRT · -0.29 R

![DOGEUSDT momentum v7 27/08 11:45 BRT](../../attachments/operacoes/momentum-v7/20260827-1445Z-DOGEUSDT-invalidated.png)

> Momentum 15m: fechamento 0.08928 acima da máxima dos 20 fechamentos anteriores (0.08919), retorno 15m 0.73%, volume relativo 2.08x da mediana de 96 barras, ATR% 0.73%

### 103 — DOGEUSDT · 27/08/2026 13:45 BRT · -0.41 R

![DOGEUSDT momentum v7 27/08 13:45 BRT](../../attachments/operacoes/momentum-v7/20260827-1645Z-DOGEUSDT-invalidated.png)

> Momentum 15m: fechamento 0.08965 acima da máxima dos 20 fechamentos anteriores (0.08945), retorno 15m 0.52%, volume relativo 1.58x da mediana de 96 barras, ATR% 0.72%

### 104 — SOLUSDT · 27/08/2026 17:00 BRT · -0.19 R

![SOLUSDT momentum v7 27/08 17:00 BRT](../../attachments/operacoes/momentum-v7/20260827-2000Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 109.33 acima da máxima dos 20 fechamentos anteriores (109.22), retorno 15m 0.21%, volume relativo 2.54x da mediana de 96 barras, ATR% 0.84%

### 105 — XRPUSDT · 27/08/2026 22:30 BRT · -1.12 R

![XRPUSDT momentum v7 27/08 22:30 BRT](../../attachments/operacoes/momentum-v7/20260828-0130Z-XRPUSDT-stop.png)

> Momentum 15m: fechamento 1.467 acima da máxima dos 20 fechamentos anteriores (1.4552), retorno 15m 0.89%, volume relativo 1.68x da mediana de 96 barras, ATR% 0.57%

### 106 — DOGEUSDT · 27/08/2026 22:30 BRT · -0.96 R

![DOGEUSDT momentum v7 27/08 22:30 BRT](../../attachments/operacoes/momentum-v7/20260828-0130Z-DOGEUSDT-invalidated.png)

> Momentum 15m: fechamento 0.08989 acima da máxima dos 20 fechamentos anteriores (0.0893), retorno 15m 0.66%, volume relativo 1.91x da mediana de 96 barras, ATR% 0.49%

### 107 — XRPUSDT · 28/08/2026 08:15 BRT · -0.41 R

![XRPUSDT momentum v7 28/08 08:15 BRT](../../attachments/operacoes/momentum-v7/20260828-1115Z-XRPUSDT-invalidated.png)

> Momentum 15m: fechamento 1.4279 acima da máxima dos 20 fechamentos anteriores (1.4269), retorno 15m 0.52%, volume relativo 2.07x da mediana de 96 barras, ATR% 0.43%

### 108 — ETHUSDT · 28/08/2026 11:45 BRT · -0.27 R

![ETHUSDT momentum v7 28/08 11:45 BRT](../../attachments/operacoes/momentum-v7/20260828-1445Z-ETHUSDT-invalidated.png)

> Momentum 15m: fechamento 2508.83 acima da máxima dos 20 fechamentos anteriores (2508.72), retorno 15m 0.73%, volume relativo 9.67x da mediana de 96 barras, ATR% 0.58%

### 109 — DOGEUSDT · 28/08/2026 11:45 BRT · -0.58 R

![DOGEUSDT momentum v7 28/08 11:45 BRT](../../attachments/operacoes/momentum-v7/20260828-1445Z-DOGEUSDT-invalidated.png)

> Momentum 15m: fechamento 0.08759 acima da máxima dos 20 fechamentos anteriores (0.08717), retorno 15m 1.15%, volume relativo 5.28x da mediana de 96 barras, ATR% 0.69%

### 110 — XRPUSDT · 28/08/2026 12:00 BRT · -0.52 R

![XRPUSDT momentum v7 28/08 12:00 BRT](../../attachments/operacoes/momentum-v7/20260828-1500Z-XRPUSDT-invalidated.png)

> Momentum 15m: fechamento 1.4304 acima da máxima dos 20 fechamentos anteriores (1.4279), retorno 15m 0.33%, volume relativo 2.76x da mediana de 96 barras, ATR% 0.84%

### 111 — SOLUSDT · 28/08/2026 12:30 BRT · -0.50 R

![SOLUSDT momentum v7 28/08 12:30 BRT](../../attachments/operacoes/momentum-v7/20260828-1530Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 106.7 acima da máxima dos 20 fechamentos anteriores (106.39), retorno 15m 1.38%, volume relativo 7.92x da mediana de 96 barras, ATR% 1.00%

### 112 — SOLUSDT · 29/08/2026 11:45 BRT · -0.18 R

![SOLUSDT momentum v7 29/08 11:45 BRT](../../attachments/operacoes/momentum-v7/20260829-1445Z-SOLUSDT-expired.png)

> Momentum 15m: fechamento 104.92 acima da máxima dos 20 fechamentos anteriores (104.24), retorno 15m 0.65%, volume relativo 5.72x da mediana de 96 barras, ATR% 0.33%

### 113 — SOLUSDT · 29/08/2026 16:30 BRT · -0.67 R

![SOLUSDT momentum v7 29/08 16:30 BRT](../../attachments/operacoes/momentum-v7/20260829-1930Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 105.68 acima da máxima dos 20 fechamentos anteriores (105.45), retorno 15m 0.22%, volume relativo 2.33x da mediana de 96 barras, ATR% 0.36%

### 114 — SOLUSDT · 30/08/2026 10:00 BRT · +0.57 R

![SOLUSDT momentum v7 30/08 10:00 BRT](../../attachments/operacoes/momentum-v7/20260830-1300Z-SOLUSDT-expired.png)

> Momentum 15m: fechamento 106.04 acima da máxima dos 20 fechamentos anteriores (105.7), retorno 15m 0.54%, volume relativo 2.90x da mediana de 96 barras, ATR% 0.34%

### 115 — DOGEUSDT · 30/08/2026 10:00 BRT · -0.42 R

![DOGEUSDT momentum v7 30/08 10:00 BRT](../../attachments/operacoes/momentum-v7/20260830-1300Z-DOGEUSDT-invalidated.png)

> Momentum 15m: fechamento 0.08539 acima da máxima dos 20 fechamentos anteriores (0.08532), retorno 15m 0.23%, volume relativo 1.82x da mediana de 96 barras, ATR% 0.30%

### 116 — XRPUSDT · 30/08/2026 11:00 BRT · -1.19 R

![XRPUSDT momentum v7 30/08 11:00 BRT](../../attachments/operacoes/momentum-v7/20260830-1400Z-XRPUSDT-stop.png)

> Momentum 15m: fechamento 1.408 acima da máxima dos 20 fechamentos anteriores (1.4023), retorno 15m 0.41%, volume relativo 3.74x da mediana de 96 barras, ATR% 0.35%

### 117 — DOGEUSDT · 30/08/2026 11:00 BRT · -0.60 R

![DOGEUSDT momentum v7 30/08 11:00 BRT](../../attachments/operacoes/momentum-v7/20260830-1400Z-DOGEUSDT-invalidated.png)

> Momentum 15m: fechamento 0.08566 acima da máxima dos 20 fechamentos anteriores (0.08544), retorno 15m 0.26%, volume relativo 3.52x da mediana de 96 barras, ATR% 0.30%

### 118 — ETHUSDT · 30/08/2026 13:15 BRT · -0.60 R

![ETHUSDT momentum v7 30/08 13:15 BRT](../../attachments/operacoes/momentum-v7/20260830-1615Z-ETHUSDT-expired.png)

> Momentum 15m: fechamento 2509.53 acima da máxima dos 20 fechamentos anteriores (2479.91), retorno 15m 1.19%, volume relativo 16.87x da mediana de 96 barras, ATR% 0.33%

### 119 — DOGEUSDT · 30/08/2026 13:15 BRT · -1.15 R

![DOGEUSDT momentum v7 30/08 13:15 BRT](../../attachments/operacoes/momentum-v7/20260830-1615Z-DOGEUSDT-stop.png)

> Momentum 15m: fechamento 0.08583 acima da máxima dos 20 fechamentos anteriores (0.08566), retorno 15m 0.59%, volume relativo 3.23x da mediana de 96 barras, ATR% 0.34%

### 120 — XRPUSDT · 30/08/2026 13:45 BRT · -0.80 R

![XRPUSDT momentum v7 30/08 13:45 BRT](../../attachments/operacoes/momentum-v7/20260830-1645Z-XRPUSDT-invalidated.png)

> Momentum 15m: fechamento 1.4109 acima da máxima dos 20 fechamentos anteriores (1.408), retorno 15m 0.34%, volume relativo 2.51x da mediana de 96 barras, ATR% 0.40%

### 121 — DOGEUSDT · 30/08/2026 15:45 BRT · -0.20 R

![DOGEUSDT momentum v7 30/08 15:45 BRT](../../attachments/operacoes/momentum-v7/20260830-1845Z-DOGEUSDT-invalidated.png)

> Momentum 15m: fechamento 0.08636 acima da máxima dos 20 fechamentos anteriores (0.08632), retorno 15m 0.29%, volume relativo 2.21x da mediana de 96 barras, ATR% 0.45%

### 122 — DOGEUSDT · 31/08/2026 02:30 BRT · -0.12 R

![DOGEUSDT momentum v7 31/08 02:30 BRT](../../attachments/operacoes/momentum-v7/20260831-0530Z-DOGEUSDT-expired.png)

> Momentum 15m: fechamento 0.08288 acima da máxima dos 20 fechamentos anteriores (0.08247), retorno 15m 0.80%, volume relativo 3.64x da mediana de 96 barras, ATR% 0.57%

### 123 — ETHUSDT · 31/08/2026 02:30 BRT · +0.26 R

![ETHUSDT momentum v7 31/08 02:30 BRT](../../attachments/operacoes/momentum-v7/20260831-0530Z-ETHUSDT-expired.png)

> Momentum 15m: fechamento 2434.35 acima da máxima dos 20 fechamentos anteriores (2431.11), retorno 15m 0.54%, volume relativo 4.54x da mediana de 96 barras, ATR% 0.46%

### 124 — SOLUSDT · 31/08/2026 02:30 BRT · +0.16 R

![SOLUSDT momentum v7 31/08 02:30 BRT](../../attachments/operacoes/momentum-v7/20260831-0530Z-SOLUSDT-expired.png)

> Momentum 15m: fechamento 102.63 acima da máxima dos 20 fechamentos anteriores (102.28), retorno 15m 0.98%, volume relativo 4.78x da mediana de 96 barras, ATR% 0.63%

### 125 — SOLUSDT · 31/08/2026 08:00 BRT · -0.58 R

![SOLUSDT momentum v7 31/08 08:00 BRT](../../attachments/operacoes/momentum-v7/20260831-1100Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 103.62 acima da máxima dos 20 fechamentos anteriores (103.19), retorno 15m 0.42%, volume relativo 2.76x da mediana de 96 barras, ATR% 0.47%

### 126 — ETHUSDT · 31/08/2026 11:45 BRT · +0.49 R

![ETHUSDT momentum v7 31/08 11:45 BRT](../../attachments/operacoes/momentum-v7/20260831-1445Z-ETHUSDT-expired.png)

> Momentum 15m: fechamento 2464.51 acima da máxima dos 20 fechamentos anteriores (2454.37), retorno 15m 0.81%, volume relativo 4.52x da mediana de 96 barras, ATR% 0.46%

### 127 — SOLUSDT · 31/08/2026 15:30 BRT · -0.24 R

![SOLUSDT momentum v7 31/08 15:30 BRT](../../attachments/operacoes/momentum-v7/20260831-1830Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 103.73 acima da máxima dos 20 fechamentos anteriores (103.65), retorno 15m 0.08%, volume relativo 1.50x da mediana de 96 barras, ATR% 0.53%

### 128 — ETHUSDT · 01/09/2026 00:45 BRT · -0.47 R

![ETHUSDT momentum v7 01/09 00:45 BRT](../../attachments/operacoes/momentum-v7/20260901-0345Z-ETHUSDT-invalidated.png)

> Momentum 15m: fechamento 2475.69 acima da máxima dos 20 fechamentos anteriores (2474.26), retorno 15m 0.40%, volume relativo 2.52x da mediana de 96 barras, ATR% 0.31%

### 129 — DOGEUSDT · 01/09/2026 00:45 BRT · -0.38 R

![DOGEUSDT momentum v7 01/09 00:45 BRT](../../attachments/operacoes/momentum-v7/20260901-0345Z-DOGEUSDT-expired.png)

> Momentum 15m: fechamento 0.08333 acima da máxima dos 20 fechamentos anteriores (0.08309), retorno 15m 0.45%, volume relativo 1.95x da mediana de 96 barras, ATR% 0.34%

### 130 — XRPUSDT · 01/09/2026 00:45 BRT · -0.43 R

![XRPUSDT momentum v7 01/09 00:45 BRT](../../attachments/operacoes/momentum-v7/20260901-0345Z-XRPUSDT-invalidated.png)

> Momentum 15m: fechamento 1.3902 acima da máxima dos 20 fechamentos anteriores (1.3865), retorno 15m 0.83%, volume relativo 1.91x da mediana de 96 barras, ATR% 0.42%

### 131 — SOLUSDT · 01/09/2026 00:45 BRT · -0.76 R

![SOLUSDT momentum v7 01/09 00:45 BRT](../../attachments/operacoes/momentum-v7/20260901-0345Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 103.86 acima da máxima dos 20 fechamentos anteriores (103.46), retorno 15m 0.39%, volume relativo 1.66x da mediana de 96 barras, ATR% 0.38%

### 132 — XRPUSDT · 01/09/2026 03:00 BRT · -0.48 R

![XRPUSDT momentum v7 01/09 03:00 BRT](../../attachments/operacoes/momentum-v7/20260901-0600Z-XRPUSDT-invalidated.png)

> Momentum 15m: fechamento 1.3942 acima da máxima dos 20 fechamentos anteriores (1.3915), retorno 15m 0.19%, volume relativo 1.58x da mediana de 96 barras, ATR% 0.41%

### 133 — ETHUSDT · 01/09/2026 20:45 BRT · -0.38 R

![ETHUSDT momentum v7 01/09 20:45 BRT](../../attachments/operacoes/momentum-v7/20260901-2345Z-ETHUSDT-invalidated.png)

> Momentum 15m: fechamento 2422.09 acima da máxima dos 20 fechamentos anteriores (2420.23), retorno 15m 0.25%, volume relativo 1.78x da mediana de 96 barras, ATR% 0.39%

### 134 — XRPUSDT · 02/09/2026 00:30 BRT · -0.35 R

![XRPUSDT momentum v7 02/09 00:30 BRT](../../attachments/operacoes/momentum-v7/20260902-0330Z-XRPUSDT-invalidated.png)

> Momentum 15m: fechamento 1.3547 acima da máxima dos 20 fechamentos anteriores (1.3528), retorno 15m 0.33%, volume relativo 1.71x da mediana de 96 barras, ATR% 0.54%

### 135 — XRPUSDT · 02/09/2026 10:45 BRT · -0.85 R

![XRPUSDT momentum v7 02/09 10:45 BRT](../../attachments/operacoes/momentum-v7/20260902-1345Z-XRPUSDT-invalidated.png)

> Momentum 15m: fechamento 1.3452 acima da máxima dos 20 fechamentos anteriores (1.3322), retorno 15m 1.50%, volume relativo 3.40x da mediana de 96 barras, ATR% 0.59%

### 136 — SOLUSDT · 02/09/2026 10:45 BRT · -0.42 R

![SOLUSDT momentum v7 02/09 10:45 BRT](../../attachments/operacoes/momentum-v7/20260902-1345Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 99.62 acima da máxima dos 20 fechamentos anteriores (99.18), retorno 15m 1.40%, volume relativo 3.82x da mediana de 96 barras, ATR% 0.58%

### 137 — DOGEUSDT · 02/09/2026 10:45 BRT · -1.13 R

![DOGEUSDT momentum v7 02/09 10:45 BRT](../../attachments/operacoes/momentum-v7/20260902-1345Z-DOGEUSDT-stop.png)

> Momentum 15m: fechamento 0.08198 acima da máxima dos 20 fechamentos anteriores (0.08135), retorno 15m 1.22%, volume relativo 2.75x da mediana de 96 barras, ATR% 0.50%

### 138 — ETHUSDT · 02/09/2026 10:45 BRT · -1.04 R

![ETHUSDT momentum v7 02/09 10:45 BRT](../../attachments/operacoes/momentum-v7/20260902-1345Z-ETHUSDT-invalidated.png)

> Momentum 15m: fechamento 2416.12 acima da máxima dos 20 fechamentos anteriores (2394.65), retorno 15m 1.22%, volume relativo 5.17x da mediana de 96 barras, ATR% 0.46%

### 139 — SOLUSDT · 02/09/2026 17:15 BRT · -0.17 R

![SOLUSDT momentum v7 02/09 17:15 BRT](../../attachments/operacoes/momentum-v7/20260902-2015Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 99.6 acima da máxima dos 20 fechamentos anteriores (99.52), retorno 15m 0.22%, volume relativo 1.88x da mediana de 96 barras, ATR% 0.47%

### 140 — XRPUSDT · 02/09/2026 17:15 BRT · -0.46 R

![XRPUSDT momentum v7 02/09 17:15 BRT](../../attachments/operacoes/momentum-v7/20260902-2015Z-XRPUSDT-invalidated.png)

> Momentum 15m: fechamento 1.349 acima da máxima dos 20 fechamentos anteriores (1.3456), retorno 15m 0.39%, volume relativo 1.62x da mediana de 96 barras, ATR% 0.49%

### 141 — SOLUSDT · 02/09/2026 21:00 BRT · -0.89 R

![SOLUSDT momentum v7 02/09 21:00 BRT](../../attachments/operacoes/momentum-v7/20260903-0000Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 100.38 acima da máxima dos 20 fechamentos anteriores (99.9), retorno 15m 0.52%, volume relativo 1.59x da mediana de 96 barras, ATR% 0.42%

### 142 — XRPUSDT · 02/09/2026 22:15 BRT · +0.31 R

![XRPUSDT momentum v7 02/09 22:15 BRT](../../attachments/operacoes/momentum-v7/20260903-0115Z-XRPUSDT-expired.png)

> Momentum 15m: fechamento 1.358 acima da máxima dos 20 fechamentos anteriores (1.3522), retorno 15m 1.08%, volume relativo 2.10x da mediana de 96 barras, ATR% 0.48%

### 143 — DOGEUSDT · 02/09/2026 22:15 BRT · +0.67 R

![DOGEUSDT momentum v7 02/09 22:15 BRT](../../attachments/operacoes/momentum-v7/20260903-0115Z-DOGEUSDT-expired.png)

> Momentum 15m: fechamento 0.08204 acima da máxima dos 20 fechamentos anteriores (0.08182), retorno 15m 0.84%, volume relativo 2.32x da mediana de 96 barras, ATR% 0.46%

### 144 — ETHUSDT · 02/09/2026 23:45 BRT · -1.17 R

![ETHUSDT momentum v7 02/09 23:45 BRT](../../attachments/operacoes/momentum-v7/20260903-0245Z-ETHUSDT-stop.png)

> Momentum 15m: fechamento 2404.07 acima da máxima dos 20 fechamentos anteriores (2394.79), retorno 15m 0.39%, volume relativo 3.39x da mediana de 96 barras, ATR% 0.36%

### 145 — SOLUSDT · 02/09/2026 23:45 BRT · -0.52 R

![SOLUSDT momentum v7 02/09 23:45 BRT](../../attachments/operacoes/momentum-v7/20260903-0245Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 100.71 acima da máxima dos 20 fechamentos anteriores (100.41), retorno 15m 0.30%, volume relativo 3.14x da mediana de 96 barras, ATR% 0.47%

### 146 — DOGEUSDT · 03/09/2026 04:15 BRT · -0.50 R

![DOGEUSDT momentum v7 03/09 04:15 BRT](../../attachments/operacoes/momentum-v7/20260903-0715Z-DOGEUSDT-invalidated.png)

> Momentum 15m: fechamento 0.08346 acima da máxima dos 20 fechamentos anteriores (0.08316), retorno 15m 0.60%, volume relativo 3.00x da mediana de 96 barras, ATR% 0.47%

### 147 — ETHUSDT · 03/09/2026 04:15 BRT · -0.38 R

![ETHUSDT momentum v7 03/09 04:15 BRT](../../attachments/operacoes/momentum-v7/20260903-0715Z-ETHUSDT-invalidated.png)

> Momentum 15m: fechamento 2411.82 acima da máxima dos 20 fechamentos anteriores (2408.94), retorno 15m 0.19%, volume relativo 3.33x da mediana de 96 barras, ATR% 0.36%

### 148 — XRPUSDT · 03/09/2026 04:15 BRT · -0.24 R

![XRPUSDT momentum v7 03/09 04:15 BRT](../../attachments/operacoes/momentum-v7/20260903-0715Z-XRPUSDT-invalidated.png)

> Momentum 15m: fechamento 1.3721 acima da máxima dos 20 fechamentos anteriores (1.3713), retorno 15m 0.59%, volume relativo 1.85x da mediana de 96 barras, ATR% 0.52%

### 149 — SOLUSDT · 03/09/2026 04:15 BRT · -0.39 R

![SOLUSDT momentum v7 03/09 04:15 BRT](../../attachments/operacoes/momentum-v7/20260903-0715Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 101.13 acima da máxima dos 20 fechamentos anteriores (101.06), retorno 15m 0.28%, volume relativo 2.43x da mediana de 96 barras, ATR% 0.47%

### 150 — XRPUSDT · 03/09/2026 05:15 BRT · -0.29 R

![XRPUSDT momentum v7 03/09 05:15 BRT](../../attachments/operacoes/momentum-v7/20260903-0815Z-XRPUSDT-invalidated.png)

> Momentum 15m: fechamento 1.3736 acima da máxima dos 20 fechamentos anteriores (1.3721), retorno 15m 0.63%, volume relativo 2.18x da mediana de 96 barras, ATR% 0.57%

### 151 — SOLUSDT · 03/09/2026 09:45 BRT · +1.68 R

![SOLUSDT momentum v7 03/09 09:45 BRT](../../attachments/operacoes/momentum-v7/20260903-1245Z-SOLUSDT-target.png)

> Momentum 15m: fechamento 100.94 acima da máxima dos 20 fechamentos anteriores (100.91), retorno 15m 0.24%, volume relativo 2.96x da mediana de 96 barras, ATR% 0.43%

### 152 — XRPUSDT · 03/09/2026 09:45 BRT · +1.61 R

![XRPUSDT momentum v7 03/09 09:45 BRT](../../attachments/operacoes/momentum-v7/20260903-1245Z-XRPUSDT-target.png)

> Momentum 15m: fechamento 1.3749 acima da máxima dos 20 fechamentos anteriores (1.3736), retorno 15m 0.26%, volume relativo 3.56x da mediana de 96 barras, ATR% 0.46%

### 153 — ETHUSDT · 03/09/2026 09:45 BRT · +1.61 R

![ETHUSDT momentum v7 03/09 09:45 BRT](../../attachments/operacoes/momentum-v7/20260903-1245Z-ETHUSDT-target.png)

> Momentum 15m: fechamento 2412.45 acima da máxima dos 20 fechamentos anteriores (2408.74), retorno 15m 0.23%, volume relativo 4.31x da mediana de 96 barras, ATR% 0.33%

### 154 — DOGEUSDT · 03/09/2026 10:00 BRT · +2.67 R

![DOGEUSDT momentum v7 03/09 10:00 BRT](../../attachments/operacoes/momentum-v7/20260903-1300Z-DOGEUSDT-target.png)

> Momentum 15m: fechamento 0.08362 acima da máxima dos 20 fechamentos anteriores (0.08329), retorno 15m 0.48%, volume relativo 2.32x da mediana de 96 barras, ATR% 0.43%

### 155 — ETHUSDT · 03/09/2026 12:30 BRT · -0.21 R

![ETHUSDT momentum v7 03/09 12:30 BRT](../../attachments/operacoes/momentum-v7/20260903-1530Z-ETHUSDT-invalidated.png)

> Momentum 15m: fechamento 2489.43 acima da máxima dos 20 fechamentos anteriores (2488.32), retorno 15m 0.16%, volume relativo 2.63x da mediana de 96 barras, ATR% 0.52%

### 156 — SOLUSDT · 03/09/2026 13:00 BRT · -0.57 R

![SOLUSDT momentum v7 03/09 13:00 BRT](../../attachments/operacoes/momentum-v7/20260903-1600Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 105.14 acima da máxima dos 20 fechamentos anteriores (104.77), retorno 15m 0.89%, volume relativo 4.00x da mediana de 96 barras, ATR% 0.73%

### 157 — XRPUSDT · 03/09/2026 13:00 BRT · -0.01 R

![XRPUSDT momentum v7 03/09 13:00 BRT](../../attachments/operacoes/momentum-v7/20260903-1600Z-XRPUSDT-expired.png)

> Momentum 15m: fechamento 1.4641 acima da máxima dos 20 fechamentos anteriores (1.4497), retorno 15m 1.12%, volume relativo 4.95x da mediana de 96 barras, ATR% 0.91%

### 158 — DOGEUSDT · 03/09/2026 13:00 BRT · -0.25 R

![DOGEUSDT momentum v7 03/09 13:00 BRT](../../attachments/operacoes/momentum-v7/20260903-1600Z-DOGEUSDT-expired.png)

> Momentum 15m: fechamento 0.08919 acima da máxima dos 20 fechamentos anteriores (0.08788), retorno 15m 1.58%, volume relativo 5.97x da mediana de 96 barras, ATR% 0.88%

### 159 — XRPUSDT · 03/09/2026 17:30 BRT · -0.45 R

![XRPUSDT momentum v7 03/09 17:30 BRT](../../attachments/operacoes/momentum-v7/20260903-2030Z-XRPUSDT-invalidated.png)

> Momentum 15m: fechamento 1.4809 acima da máxima dos 20 fechamentos anteriores (1.4709), retorno 15m 0.93%, volume relativo 1.84x da mediana de 96 barras, ATR% 0.78%

### 160 — ETHUSDT · 04/09/2026 00:15 BRT · -0.40 R

![ETHUSDT momentum v7 04/09 00:15 BRT](../../attachments/operacoes/momentum-v7/20260904-0315Z-ETHUSDT-invalidated.png)

> Momentum 15m: fechamento 2510.2 acima da máxima dos 20 fechamentos anteriores (2506.99), retorno 15m 0.13%, volume relativo 2.22x da mediana de 96 barras, ATR% 0.36%

### 161 — ETHUSDT · 04/09/2026 01:30 BRT · -0.92 R

![ETHUSDT momentum v7 04/09 01:30 BRT](../../attachments/operacoes/momentum-v7/20260904-0430Z-ETHUSDT-invalidated.png)

> Momentum 15m: fechamento 2522.74 acima da máxima dos 20 fechamentos anteriores (2510.2), retorno 15m 0.65%, volume relativo 3.12x da mediana de 96 barras, ATR% 0.34%

### 162 — ETHUSDT · 04/09/2026 06:00 BRT · -0.45 R

![ETHUSDT momentum v7 04/09 06:00 BRT](../../attachments/operacoes/momentum-v7/20260904-0900Z-ETHUSDT-invalidated.png)

> Momentum 15m: fechamento 2526.43 acima da máxima dos 20 fechamentos anteriores (2522.74), retorno 15m 0.33%, volume relativo 5.32x da mediana de 96 barras, ATR% 0.36%

### 163 — DOGEUSDT · 04/09/2026 06:00 BRT · -0.33 R

![DOGEUSDT momentum v7 04/09 06:00 BRT](../../attachments/operacoes/momentum-v7/20260904-0900Z-DOGEUSDT-invalidated.png)

> Momentum 15m: fechamento 0.08762 acima da máxima dos 20 fechamentos anteriores (0.08751), retorno 15m 0.57%, volume relativo 1.95x da mediana de 96 barras, ATR% 0.43%

### 164 — SOLUSDT · 04/09/2026 06:00 BRT · -0.38 R

![SOLUSDT momentum v7 04/09 06:00 BRT](../../attachments/operacoes/momentum-v7/20260904-0900Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 104.32 acima da máxima dos 20 fechamentos anteriores (104.24), retorno 15m 0.55%, volume relativo 2.53x da mediana de 96 barras, ATR% 0.38%

### 165 — DOGEUSDT · 05/09/2026 03:45 BRT · +0.45 R

![DOGEUSDT momentum v7 05/09 03:45 BRT](../../attachments/operacoes/momentum-v7/20260905-0645Z-DOGEUSDT-expired.png)

> Momentum 15m: fechamento 0.0854 acima da máxima dos 20 fechamentos anteriores (0.08486), retorno 15m 0.64%, volume relativo 4.73x da mediana de 96 barras, ATR% 0.31%

### 166 — DOGEUSDT · 05/09/2026 09:45 BRT · +0.03 R

![DOGEUSDT momentum v7 05/09 09:45 BRT](../../attachments/operacoes/momentum-v7/20260905-1245Z-DOGEUSDT-expired.png)

> Momentum 15m: fechamento 0.08731 acima da máxima dos 20 fechamentos anteriores (0.08634), retorno 15m 1.12%, volume relativo 6.93x da mediana de 96 barras, ATR% 0.40%

### 167 — XRPUSDT · 05/09/2026 11:45 BRT · -0.53 R

![XRPUSDT momentum v7 05/09 11:45 BRT](../../attachments/operacoes/momentum-v7/20260905-1445Z-XRPUSDT-invalidated.png)

> Momentum 15m: fechamento 1.4163 acima da máxima dos 20 fechamentos anteriores (1.4161), retorno 15m 0.12%, volume relativo 2.09x da mediana de 96 barras, ATR% 0.31%

### 168 — XRPUSDT · 05/09/2026 14:15 BRT · -0.72 R

![XRPUSDT momentum v7 05/09 14:15 BRT](../../attachments/operacoes/momentum-v7/20260905-1715Z-XRPUSDT-invalidated.png)

> Momentum 15m: fechamento 1.4212 acima da máxima dos 20 fechamentos anteriores (1.4163), retorno 15m 0.45%, volume relativo 2.84x da mediana de 96 barras, ATR% 0.32%

### 169 — SOLUSDT · 05/09/2026 14:15 BRT · -1.27 R

![SOLUSDT momentum v7 05/09 14:15 BRT](../../attachments/operacoes/momentum-v7/20260905-1715Z-SOLUSDT-stop.png)

> Momentum 15m: fechamento 103.99 acima da máxima dos 20 fechamentos anteriores (103.36), retorno 15m 0.61%, volume relativo 5.84x da mediana de 96 barras, ATR% 0.31%

### 170 — DOGEUSDT · 05/09/2026 15:00 BRT · -1.08 R

![DOGEUSDT momentum v7 05/09 15:00 BRT](../../attachments/operacoes/momentum-v7/20260905-1800Z-DOGEUSDT-stop.png)

> Momentum 15m: fechamento 0.0942 acima da máxima dos 20 fechamentos anteriores (0.08943), retorno 15m 5.59%, volume relativo 24.00x da mediana de 96 barras, ATR% 1.03%

### 171 — SOLUSDT · 05/09/2026 23:00 BRT · +1.27 R

![SOLUSDT momentum v7 05/09 23:00 BRT](../../attachments/operacoes/momentum-v7/20260906-0200Z-SOLUSDT-target.png)

> Momentum 15m: fechamento 103.99 acima da máxima dos 20 fechamentos anteriores (103.88), retorno 15m 0.22%, volume relativo 2.71x da mediana de 96 barras, ATR% 0.32%

### 172 — DOGEUSDT · 06/09/2026 00:45 BRT · -1.12 R

![DOGEUSDT momentum v7 06/09 00:45 BRT](../../attachments/operacoes/momentum-v7/20260906-0345Z-DOGEUSDT-stop.png)

> Momentum 15m: fechamento 0.0916 acima da máxima dos 20 fechamentos anteriores (0.0909), retorno 15m 0.90%, volume relativo 3.45x da mediana de 96 barras, ATR% 0.54%

### 173 — XRPUSDT · 06/09/2026 00:45 BRT · -1.16 R

![XRPUSDT momentum v7 06/09 00:45 BRT](../../attachments/operacoes/momentum-v7/20260906-0345Z-XRPUSDT-stop.png)

> Momentum 15m: fechamento 1.4278 acima da máxima dos 20 fechamentos anteriores (1.419), retorno 15m 0.66%, volume relativo 3.18x da mediana de 96 barras, ATR% 0.34%

### 174 — SOLUSDT · 06/09/2026 06:30 BRT · -0.72 R

![SOLUSDT momentum v7 06/09 06:30 BRT](../../attachments/operacoes/momentum-v7/20260906-0930Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 106.94 acima da máxima dos 20 fechamentos anteriores (106.4), retorno 15m 1.14%, volume relativo 6.17x da mediana de 96 barras, ATR% 0.51%

### 175 — SOLUSDT · 06/09/2026 09:45 BRT · -0.36 R

![SOLUSDT momentum v7 06/09 09:45 BRT](../../attachments/operacoes/momentum-v7/20260906-1245Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 106.95 acima da máxima dos 20 fechamentos anteriores (106.94), retorno 15m 0.37%, volume relativo 2.38x da mediana de 96 barras, ATR% 0.43%

### 176 — SOLUSDT · 06/09/2026 11:00 BRT · -0.68 R

![SOLUSDT momentum v7 06/09 11:00 BRT](../../attachments/operacoes/momentum-v7/20260906-1400Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 107.03 acima da máxima dos 20 fechamentos anteriores (106.95), retorno 15m 0.55%, volume relativo 1.86x da mediana de 96 barras, ATR% 0.49%

### 177 — DOGEUSDT · 06/09/2026 17:30 BRT · +1.11 R

![DOGEUSDT momentum v7 06/09 17:30 BRT](../../attachments/operacoes/momentum-v7/20260906-2030Z-DOGEUSDT-expired.png)

> Momentum 15m: fechamento 0.08992 acima da máxima dos 20 fechamentos anteriores (0.08956), retorno 15m 0.40%, volume relativo 1.65x da mediana de 96 barras, ATR% 0.37%

### 178 — ETHUSDT · 06/09/2026 23:45 BRT · -0.86 R

![ETHUSDT momentum v7 06/09 23:45 BRT](../../attachments/operacoes/momentum-v7/20260907-0245Z-ETHUSDT-invalidated.png)

> Momentum 15m: fechamento 2526.26 acima da máxima dos 20 fechamentos anteriores (2519.27), retorno 15m 0.65%, volume relativo 7.09x da mediana de 96 barras, ATR% 0.39%

### 179 — SOLUSDT · 06/09/2026 23:45 BRT · -0.89 R

![SOLUSDT momentum v7 06/09 23:45 BRT](../../attachments/operacoes/momentum-v7/20260907-0245Z-SOLUSDT-invalidated.png)

> Momentum 15m: fechamento 106.72 acima da máxima dos 20 fechamentos anteriores (106.57), retorno 15m 0.85%, volume relativo 2.70x da mediana de 96 barras, ATR% 0.53%

### 180 — DOGEUSDT · 07/09/2026 09:30 BRT · -0.98 R

![DOGEUSDT momentum v7 07/09 09:30 BRT](../../attachments/operacoes/momentum-v7/20260907-1230Z-DOGEUSDT-invalidated.png)

> Momentum 15m: fechamento 0.09039 acima da máxima dos 20 fechamentos anteriores (0.08982), retorno 15m 0.65%, volume relativo 1.59x da mediana de 96 barras, ATR% 0.42%

### 181 — SOLUSDT · 07/09/2026 10:00 BRT · -1.17 R

![SOLUSDT momentum v7 07/09 10:00 BRT](../../attachments/operacoes/momentum-v7/20260907-1300Z-SOLUSDT-stop.png)

> Momentum 15m: fechamento 105.68 acima da máxima dos 20 fechamentos anteriores (105.33), retorno 15m 0.51%, volume relativo 1.96x da mediana de 96 barras, ATR% 0.34%

### 182 — XRPUSDT · 07/09/2026 10:00 BRT · -0.94 R

![XRPUSDT momentum v7 07/09 10:00 BRT](../../attachments/operacoes/momentum-v7/20260907-1300Z-XRPUSDT-invalidated.png)

> Momentum 15m: fechamento 1.4116 acima da máxima dos 20 fechamentos anteriores (1.4062), retorno 15m 0.43%, volume relativo 2.25x da mediana de 96 barras, ATR% 0.34%

### 183 — DOGEUSDT · 07/09/2026 20:15 BRT · -0.48 R

![DOGEUSDT momentum v7 07/09 20:15 BRT](../../attachments/operacoes/momentum-v7/20260907-2315Z-DOGEUSDT-invalidated.png)

> Momentum 15m: fechamento 0.09081 acima da máxima dos 20 fechamentos anteriores (0.09071), retorno 15m 0.82%, volume relativo 1.57x da mediana de 96 barras, ATR% 0.52%

### 184 — ZROUSDT · 08/09/2026 19:30 BRT · -0.46 R

![ZROUSDT momentum v7 08/09 19:30 BRT](../../attachments/operacoes/momentum-v7/20260908-2230Z-ZROUSDT-invalidated.png)

> Momentum 15m: fechamento 1.1506 acima da máxima dos 20 fechamentos anteriores (1.1389), retorno 15m 1.03%, volume relativo 1.89x da mediana de 96 barras, ATR% 0.92%

### 185 — FFUSDT · 08/09/2026 19:45 BRT · -0.31 R

![FFUSDT momentum v7 08/09 19:45 BRT](../../attachments/operacoes/momentum-v7/20260908-2245Z-FFUSDT-invalidated.png)

> Momentum 15m: fechamento 0.15173 acima da máxima dos 20 fechamentos anteriores (0.15151), retorno 15m 0.76%, volume relativo 1.68x da mediana de 96 barras, ATR% 1.95%

### 186 — ATOMUSDT · 08/09/2026 19:45 BRT · -0.30 R

![ATOMUSDT momentum v7 08/09 19:45 BRT](../../attachments/operacoes/momentum-v7/20260908-2245Z-ATOMUSDT-invalidated.png)

> Momentum 15m: fechamento 1.853 acima da máxima dos 20 fechamentos anteriores (1.847), retorno 15m 0.49%, volume relativo 2.55x da mediana de 96 barras, ATR% 1.00%
