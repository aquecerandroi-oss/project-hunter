# Passada de estresse (T3.36) — mean_reversion v1, coorte replay:d0f77894…, VPS 2026-09-08 19:13Z (16:13 Brasília)

Veredito: **frágil a custos** (custos ×2 → −0,12 R, IC do Δ inteiro negativo) e dependente de metade (2ª metade: 7 operações, −0,56 R). Parâmetros (stop/alvo ±25 %, entrada +1 barra) dentro do ruído. Nenhum mercado carrega sozinho.

coorte replay:d0f77894-1e04-454e-a49f-d9a98d894968 · as_of 2026-09-08T19:13:53.302037+00:00 · 37 entradas congeladas · 4 mercados

| cenário | tipo | n | expectancy (R) | PF | Δ vs base | IC 95 % do Δ | descartes |
|---|---|---:|---:|---:|---:|---|---|
| `base` | reprecificacao | 37 | 0.0938 | 1.1856 | — | — | — |
| `custos_x2` | reprecificacao | 37 | -0.1213 | 0.7878 | -0.2150 | [-0.2615, -0.1597] | — |
| `stop_x0.75` | reprecificacao | 37 | 0.0812 | 1.1289 | -0.0126 | [-0.1962, +0.1236] | — |
| `stop_x1.25` | reprecificacao | 37 | 0.1272 | 1.3244 | 0.0335 | [-0.0994, +0.2442] | — |
| `alvo_x0.75` | reprecificacao | 37 | 0.0438 | 1.0925 | -0.0500 | [-0.2122, +0.1346] | — |
| `alvo_x1.25` | reprecificacao | 37 | 0.1012 | 1.1881 | 0.0074 | [-0.2255, +0.1723] | — |
| `entrada_mais_1_barra` | reprecificacao | 37 | 0.0977 | 1.1931 | 0.0039 | [-0.0670, +0.1006] | — |
| `sem_binance:DOGEUSDT` | recorte | 25 | 0.1833 | 1.3935 | — | — | — |
| `sem_binance:ETHUSDT` | recorte | 31 | 0.0706 | 1.1350 | — | — | — |
| `sem_binance:SOLUSDT` | recorte | 29 | 0.0234 | 1.0446 | — | — | — |
| `sem_binance:XRPUSDT` | recorte | 26 | 0.1138 | 1.2270 | — | — | — |
| `1a_metade_ate_2026-08-28` | recorte | 30 | 0.2456 | 1.5734 | — | — | — |
| `2a_metade_apos_2026-08-28` | recorte | 7 | -0.5568 | 0.3331 | — | — | — |

**Veredito:** frágil a custos
- frágil a custos: custos_x2 → expectancy -0.1212810318488431088962096740 (n=37)
- dependente de metade: 2a_metade_apos_2026-08-28 → expectancy -0.5567894557157569318179997923 (n=7)
