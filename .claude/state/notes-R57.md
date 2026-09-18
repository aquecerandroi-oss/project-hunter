# R57 — Há vantagem em SEGUIR CARTEIRAS VENCEDORAS? (72 h de fita, 15/09 14:36 → 18/09 14:36 BRT)

Medido em **18/09/2026 14:36 BRT** (17:36:20Z, `now()` do Postgres). Banco `hunter-postgres-1`, só SELECT; agregação em Polars no scratchpad (`rank.py`, `rank2.py`, `sig.py`, `outc.py`). Janela: 72 h em três "dias" de 24 h encerrados no instante da medição — **D1** 15/09 14:36 → 16/09 14:36 BRT, **D2** → 17/09 14:36, **D3** → 18/09 14:36. Horários em Brasília (UTC−3). SQL no fim.

Pergunta do Everton (18/09): "parece que nunca mudamos, ficamos sempre na mesma estratégia" — a mesa só filtra a saúde da moeda. Aqui: (1) quem ganha na fita e se continua ganhando no dia seguinte; (2) se comprar *depois* que duas dessas carteiras compram rende alguma coisa; (3) o que a fita **não** enxerga.

## 0. Resposta curta

| | achado |
|---|---|
| Carteiras vencedoras existem e **persistem** | Spearman do PnL realizado D1→D2 ρ = 0,61 (n = 292), D2→D3 ρ = 0,65 (n = 307). O top-30 de D1 ganhou 79,6 SOL em D2 (24 de 27 ativas positivas; média 2,95 SOL/carteira contra 0,14 da base); 10–12 dos 30 seguem no top-30 do dia seguinte. |
| Mas o ganho delas é **velocidade** e **pacote** | Hold mediano de 1–13 s em metade do top-30; 16 % das compras do top a idade ≤ 2 s (mesmo bloco do `create`), 45 % a ≤ 60 s. 43 % dos "sinais" são duas carteiras do top comprando no **mesmo segundo** (bundle = mesmo operador). |
| Sinal "duas do top compraram em 60 s" | n = 341 em D2+D3 (~170/dia). A preço do gatilho (impossível): +60 s mediana 1,11×. **A 3 s** (feed de evento): +60 s 1,01×. **A 20 s** (fita): 0,96×. |
| Desfecho paper (trailing 30 %, 30 min, taxa 1,75 %/perna) | A 20 s: **R médio −0,06, acerto 29 %** contra controle −0,06 / 35 % (Δ +0,00, IC95 [−0,14; +0,16]). A 3 s: +0,03 vs −0,04 (Δ +0,07, IC [−0,06; +0,21]). **Sem vantagem** com a saída da mesa. |
| Única fresta | Segurar 15 min sem stop: a 20 s Δ R = +0,18, IC95 [+0,00; +0,39]; a 3 s +0,27 [+0,08; +0,48]. Mediana **negativa** nos dois; é cauda (SD 1,5–1,7 R) e 30 % das trajetórias estão censuradas pela fita. Não sustenta braço vivo; sustenta um `research_only` pré-registrado com previsão `descartar` (EXP-M15, rascunho). |

## 1. O que a fita realmente cobre (o caveat vem antes dos números)

| medida (72 h, `meme_trades`, `program = pump`) | valor |
|---|---|
| trades / mints / carteiras | 1 224 838 / 5 467 / 157 860 (`buy` 734 570, `sell` 542 705) |
| mints criados no período (`meme_tokens`) | 102 185 (3 172 completaram, 3,1 %) → **a fita cobre 5,3 % dos mints** |
| dos 5 469 com fita, completaram | **891 (16 %)** — a fita é puxada para quem a mesa rastreia/aposta; é um universo já filtrado |
| janela coberta por mint | primeira trade a **−0,5 s** da criação (a primeira puxada traz o histórico), última a **104 s** (p50) / 1 353 s (p90); **1 puxada** (p50), 9 (p90) |
| mints com > 30 min de fita / > 2 h | 381 / 192 |
| atraso `received_at − block_time` | **p50 26 s, p90 99 s** (nas compras do top-30: p50 16,5 s, p90 113 s) |
| `meme_features_1m` por mint | 5 linhas (p50), 8 (p90); só 218 mints com ≥ 35 min de série — não serve de marcação alternativa |

Consequência: **o que a fita vê de uma carteira é, na maioria, os primeiros ~100 s de cada moeda.** Compra-e-vende dentro desses 100 s aparece como round-trip fechado; quem segura mais que isso aparece como posição "aberta" marcada na última cota (otimista: a cota de 100 s é antes do colapso) ou a zero (pessimista). Por isso a classificação abaixo é por **PnL realizado** em pares fechados; as duas marcações de abertos ficam ao lado como sensibilidade.

## 2. PnL por carteira

**Definição.** Par (carteira, mint) = uma posição. `sol_in` = Σ `sol_lamports` das compras, `sol_out` = Σ das vendas, tokens idem. **Fechada** quando `tok_out ≥ 0,95·tok_in` (e não "sobrevendida": `tok_out ≤ 1,05·tok_in`; sobrevenda = compra fora da cobertura, par descartado — 9 906 pares). PnL fechado = `sol_out − sol_in` (para o total da posição, FIFO e média dão o mesmo número; o FIFO só mudaria a atribuição por trade, e aqui cada par é 1 trade). Abertos: `sol_out − sol_in + tokens restantes × última cota do mint na fita` (e a zero). Vitória = PnL fechado > 0. Dia da posição = dia da primeira trade. **Excluídos:** o criador de cada mint (632 pares) e 165 carteiras com > 200 trades num dia (bots). A taxa da pump.fun está dentro de `sol_lamports` conforme a fita reporta; taxa de rede não está.

| universo (não-criador, não-bot) | D1 | D2 | D3 |
|---|---|---|---|
| pares fechados | 16 455 | 19 292 | 15 109 |
| acerto (PnL > 0) | 51,0 % | 50,5 % | 50,8 % |
| PnL médio / mediano por par | +0,025 / +0,00002 SOL | +0,026 / 0 | +0,028 / +0,00001 |
| hold mediano | 55 s | 39 s | 48 s |
| carteiras com ≥ 8 fechados | 547 | 639 | 527 |
| delas, PnL realizado > 0 | 71,5 % | 64,6 % | 65,1 % |
| PnL realizado mediano dessas | 0,065 SOL | 0,043 | 0,040 |

Metade dos pares fechados na fita duram < 1 min: é o mercado dos snipers. A mediana por par é ≈ 0 porque 10 % dos pares fechados são compra-e-venda em ≤ 2 s (1,8 % com |PnL| ≤ 2 lamports: wash/bundle puro) e o resto se divide meio a meio em torno de zero.

### 2.1 Top-30 por PnL realizado (≥ 8 pares fechados no dia)

Carteira = 8 primeiros caracteres. `abertos a última cota`/`a zero` = as duas marcações das posições não fechadas (SOL). `máx. trades/dia` = pico diário nas 72 h.

### Dia 1

| carteira | realizado SOL | fechados | acerto % | ROI fechados | hold mediano | abertos | abertos a última cota | abertos a zero | mints | máx. trades/dia |
|---|---|---|---|---|---|---|---|---|---|---|
| 76rdHqai | 10.761 | 8 | 100 | 23.7% | 13s | 3 | 17.361 | -14.164 | 16 | 80 |
| 4Aktn51c | 6.859 | 37 | 68 | 11.1% | 4s | 10 | 4.102 | -12.195 | 61 | 151 |
| J3gZFpvs | 6.755 | 33 | 73 | 13.3% | 4s | 15 | 5.742 | -12.385 | 65 | 156 |
| 3Xk2EuuS | 6.286 | 21 | 67 | 41.2% | 75s | 20 | 7.778 | -13.511 | 71 | 116 |
| 64hJxoZz | 5.692 | 33 | 64 | 10.4% | 4s | 9 | 5.519 | -10.983 | 58 | 139 |
| 4FCjKaFT | 5.169 | 25 | 80 | 18.1% | 60s | 27 | 8.931 | -28.019 | 67 | 166 |
| 7fEXteaT | 5.042 | 16 | 88 | 13.4% | 60s | 0 | 0.000 | 0.000 | 18 | 40 |
| 2pUUZYto | 4.812 | 16 | 62 | 14.9% | 16s | 11 | -3.663 | -29.025 | 37 | 69 |
| AS6akYpZ | 4.579 | 9 | 100 | 51.5% | 112s | 6 | 1.661 | -5.926 | 22 | 38 |
| Bwn6QEBU | 4.290 | 23 | 57 | 18.9% | 181s | 16 | 9.221 | -15.802 | 59 | 92 |
| 2JVS8Juk | 3.984 | 13 | 54 | 12.7% | 110s | 4 | 7.472 | -3.932 | 18 | 43 |
| EaaCfVxV | 3.955 | 32 | 66 | 6.4% | 23s | 11 | 5.276 | -13.001 | 67 | 138 |
| 3oN2NBiW | 3.555 | 41 | 71 | 8.8% | 2s | 8 | -0.737 | -5.447 | 54 | 170 |
| 5t4fzb85 | 3.315 | 8 | 88 | 18.6% | 34s | 10 | 5.079 | -6.328 | 25 | 94 |
| G774YyRx | 3.058 | 15 | 67 | 40.2% | 308s | 17 | 2.471 | -8.162 | 36 | 49 |
| 6vB9VfGp | 2.997 | 26 | 73 | 16.4% | 2s | 6 | 0.804 | -2.867 | 40 | 86 |
| 8pisMPgQ | 2.988 | 36 | 81 | 11.2% | 1s | 9 | 1.079 | -5.512 | 61 | 163 |
| 9keCU8mg | 2.949 | 35 | 69 | 7.1% | 60s | 19 | 4.823 | -21.406 | 77 | 152 |
| 8jsPACii | 2.918 | 30 | 83 | 8.6% | 2s | 10 | 2.768 | -7.826 | 50 | 139 |
| ENaAHa6w | 2.899 | 16 | 56 | 10.5% | 16s | 8 | 6.963 | -8.172 | 35 | 54 |
| 24678QKx | 2.782 | 8 | 88 | 51.9% | 2s | 1 | 0.149 | -0.130 | 10 | 52 |
| Aeg9rNNq | 2.663 | 9 | 56 | 15.0% | 186s | 8 | 2.472 | -11.418 | 26 | 116 |
| 4zwdYcG6 | 2.605 | 11 | 64 | 82.5% | 483s | 9 | 1.935 | -2.665 | 23 | 38 |
| LpieurWu | 2.594 | 16 | 75 | 15.3% | 10s | 7 | 2.670 | -6.263 | 35 | 78 |
| DiwH5biL | 2.510 | 16 | 38 | 19.1% | 117s | 11 | 3.055 | -7.871 | 41 | 73 |
| CxtRuSB9 | 2.432 | 16 | 81 | 11.0% | 15s | 9 | 13.646 | -9.665 | 32 | 32 |
| LivF8Gik | 2.428 | 14 | 86 | 21.2% | 4s | 8 | 1.766 | -5.408 | 32 | 85 |
| 2k6aaxsz | 2.389 | 33 | 64 | 8.5% | 2s | 9 | 0.312 | -6.067 | 53 | 162 |
| HwEKcgZh | 2.385 | 13 | 38 | 12.2% | 17s | 17 | 2.396 | -17.660 | 43 | 121 |
| 4gG4V4iP | 2.335 | 10 | 60 | 38.8% | 26s | 1 | 0.153 | -0.602 | 15 | 41 |

### Dia 2

| carteira | realizado SOL | fechados | acerto % | ROI fechados | hold mediano | abertos | abertos a última cota | abertos a zero | mints | máx. trades/dia |
|---|---|---|---|---|---|---|---|---|---|---|
| 64hJxoZz | 15.752 | 38 | 82 | 23.9% | 4s | 13 | 9.320 | -20.406 | 64 | 139 |
| 9keCU8mg | 8.169 | 48 | 75 | 15.3% | 44s | 12 | -0.821 | -12.413 | 88 | 152 |
| nya666pQ | 7.078 | 60 | 55 | 29.5% | 14s | 19 | 11.585 | -10.828 | 124 | 168 |
| 7Y13nYvM | 6.837 | 9 | 78 | 22.0% | 162s | 7 | 5.138 | -17.733 | 25 | 57 |
| DxhpC9c4 | 6.753 | 24 | 58 | 14.3% | 2s | 4 | 8.124 | -0.567 | 32 | 56 |
| 56TNvzzJ | 6.419 | 11 | 91 | 19.8% | 112s | 13 | 8.379 | -32.659 | 32 | 60 |
| CFt926D6 | 6.286 | 60 | 60 | 8.0% | 1s | 9 | 1.631 | -7.705 | 81 | 190 |
| VsgdPSj1 | 6.199 | 25 | 48 | 56.6% | 13s | 24 | 2.405 | -8.727 | 69 | 101 |
| J3gZFpvs | 5.343 | 46 | 72 | 8.0% | 6s | 11 | 4.347 | -14.075 | 80 | 156 |
| AMDEmVoc | 5.196 | 54 | 52 | 12.2% | 4s | 11 | 12.523 | -10.792 | 106 | 157 |
| EaaCfVxV | 4.791 | 39 | 54 | 7.5% | 4s | 6 | 3.255 | -9.079 | 63 | 138 |
| BQEQ48NS | 4.466 | 30 | 57 | 8.0% | 30s | 10 | 10.301 | -15.817 | 50 | 104 |
| 6qudAN2k | 4.145 | 11 | 82 | 13.2% | 67s | 8 | 1.685 | -15.673 | 21 | 44 |
| 6vB9VfGp | 4.001 | 26 | 77 | 21.3% | 2s | 8 | 1.477 | -3.182 | 46 | 86 |
| 24678QKx | 3.985 | 23 | 70 | 28.6% | 1s | 1 | 1.018 | -0.490 | 34 | 52 |
| 7aCYTnqt | 3.975 | 8 | 88 | 14.5% | 160s | 14 | 7.330 | -31.797 | 31 | 59 |
| BYxxKQ7c | 3.924 | 25 | 52 | 18.9% | 70s | 57 | 14.149 | -40.767 | 109 | 180 |
| 3pk5yRhw | 3.739 | 39 | 64 | 10.4% | 1s | 9 | -1.731 | -5.950 | 62 | 153 |
| J6DdwTar | 3.697 | 18 | 83 | 24.3% | 2s | 12 | 4.855 | -8.870 | 40 | 74 |
| 2Zoi2QTw | 3.665 | 25 | 60 | 18.4% | 70s | 57 | 16.095 | -39.560 | 109 | 180 |
| 7cp6zxvh | 3.581 | 12 | 67 | 29.6% | 2s | 1 | 0.377 | -1.026 | 13 | 29 |
| AS6akYpZ | 3.579 | 11 | 82 | 32.9% | 194s | 9 | 4.146 | -8.889 | 27 | 38 |
| 8pisMPgQ | 3.509 | 43 | 86 | 9.4% | 2s | 20 | -0.548 | -13.307 | 76 | 163 |
| AEgkmXuF | 3.503 | 16 | 88 | 10.9% | 0s | 0 | 0.000 | 0.000 | 17 | 24 |
| GZmUDsn8 | 3.495 | 25 | 68 | 13.3% | 18s | 3 | 4.649 | -2.892 | 36 | 66 |
| 8dtx2tr4 | 3.482 | 26 | 38 | 15.3% | 22s | 7 | 6.323 | -4.985 | 46 | 80 |
| 4Aktn51c | 3.427 | 31 | 65 | 7.0% | 11s | 16 | 8.792 | -18.874 | 71 | 151 |
| FftK4vtK | 3.277 | 10 | 60 | 28.7% | 136s | 3 | 1.402 | -2.962 | 18 | 21 |
| CBKgS8Nj | 3.234 | 40 | 62 | 7.5% | 2s | 10 | 1.183 | -4.797 | 58 | 154 |
| 2k6aaxsz | 3.233 | 45 | 67 | 8.7% | 1s | 12 | 3.925 | -7.237 | 72 | 162 |

### Dia 3

| carteira | realizado SOL | fechados | acerto % | ROI fechados | hold mediano | abertos | abertos a última cota | abertos a zero | mints | máx. trades/dia |
|---|---|---|---|---|---|---|---|---|---|---|
| Anubis51 | 7.661 | 23 | 65 | 21.2% | 2s | 8 | 9.445 | -10.475 | 35 | 97 |
| CFt926D6 | 5.624 | 38 | 66 | 11.7% | 1s | 5 | 0.305 | -4.617 | 53 | 190 |
| G8gTguf7 | 5.428 | 25 | 80 | 44.3% | 1s | 4 | 2.260 | -0.508 | 33 | 134 |
| Ezt2W9Fj | 5.223 | 11 | 64 | 46.8% | 94s | 7 | 4.339 | -5.829 | 23 | 33 |
| AXgzGEvb | 4.712 | 10 | 70 | 16.1% | 2s | 1 | -0.249 | -2.933 | 12 | 26 |
| J3gZFpvs | 4.637 | 35 | 63 | 7.3% | 3s | 6 | 3.095 | -7.623 | 47 | 156 |
| 9keCU8mg | 4.595 | 28 | 75 | 21.1% | 35s | 13 | 4.408 | -10.459 | 55 | 152 |
| 5ZnupsyF | 4.361 | 12 | 42 | 43.8% | 10s | 5 | 6.691 | -3.711 | 23 | 47 |
| 2RjnQgvA | 4.355 | 10 | 90 | 45.5% | 148s | 12 | 3.183 | -10.074 | 28 | 54 |
| 3Xk2EuuS | 4.187 | 13 | 62 | 46.9% | 48s | 12 | 6.931 | -8.193 | 40 | 116 |
| GfDh8LF5 | 3.543 | 47 | 57 | 22.6% | 3s | 14 | 1.054 | -4.581 | 73 | 125 |
| 3oN2NBiW | 3.524 | 27 | 74 | 10.5% | 4s | 9 | 2.282 | -7.523 | 44 | 170 |
| 64hJxoZz | 3.520 | 28 | 68 | 8.2% | 6s | 7 | 3.742 | -6.515 | 47 | 139 |
| Govapkt6 | 3.429 | 20 | 70 | 20.7% | 101s | 10 | 2.026 | -7.050 | 42 | 47 |
| AMDEmVoc | 3.400 | 41 | 44 | 11.3% | 8s | 7 | 3.876 | -7.149 | 69 | 157 |
| 9A7um9R3 | 3.396 | 22 | 36 | 25.8% | 3s | 13 | 4.666 | -7.242 | 47 | 83 |
| EaaCfVxV | 3.347 | 31 | 65 | 7.4% | 6s | 7 | 1.003 | -7.449 | 49 | 138 |
| 2k6aaxsz | 3.334 | 33 | 58 | 12.0% | 2s | 6 | 0.765 | -3.340 | 46 | 162 |
| Bwn6QEBU | 3.199 | 30 | 43 | 10.8% | 92s | 11 | 8.304 | -10.864 | 63 | 92 |
| 8pisMPgQ | 3.187 | 32 | 75 | 12.6% | 2s | 9 | 5.493 | -6.169 | 50 | 163 |
| GZmUDsn8 | 3.140 | 19 | 68 | 16.9% | 10s | 1 | 0.076 | -0.935 | 24 | 66 |
| AS6akYpZ | 3.119 | 9 | 89 | 35.1% | 113s | 8 | 2.964 | -6.591 | 24 | 38 |
| BiFYSKmp | 2.969 | 13 | 85 | 36.2% | 97s | 9 | 4.116 | -5.299 | 26 | 66 |
| 24678QKx | 2.946 | 20 | 60 | 21.0% | 2s | 0 | 0.000 | 0.000 | 21 | 52 |
| 8ki679dZ | 2.930 | 14 | 64 | 21.7% | 2s | 10 | 0.763 | -3.753 | 28 | 53 |
| 8jsPACii | 2.928 | 37 | 78 | 9.4% | 2s | 4 | -1.789 | -2.936 | 51 | 139 |
| HUnS29Z2 | 2.773 | 23 | 87 | 15.9% | 19s | 9 | 0.885 | -6.725 | 40 | 82 |
| nya666pQ | 2.751 | 44 | 43 | 15.5% | 9s | 9 | 1.154 | -5.063 | 86 | 168 |
| 5bb5kQKh | 2.616 | 33 | 67 | 10.0% | 1s | 6 | -1.049 | -3.514 | 42 | 136 |
| 6kVeQugG | 2.187 | 8 | 50 | 59.8% | 1326s | 14 | 4.633 | -5.288 | 23 | 74 |

**Leitura.** Hold mediano ≤ 5 s em 13 / 11 / 15 das 30 carteiras de D1 / D2 / D3 (`4Aktn51c`, `J3gZFpvs`, `64hJxoZz`, `3oN2NBiW`, `8pisMPgQ`, `2k6aaxsz`, `CFt926D6`…): compram no bloco do `create` e vendem 1–4 s depois. Estilo pela idade mediana da moeda na compra: **sniper** (≤ 5 s) 1 / 4 / 6, **cedo** (≤ 60 s) 8 / 7 / 8, **segurador** (> 60 s) 21 / 19 / 16 — mas mesmo os "seguradores" têm ROI de 7–20 % por par com hold de 1–3 min. As posições abertas marcadas a zero são −5 a −40 SOL por carteira: a fita perde as vendas de quem segura, então **o PnL total é indeterminado**; só o realizado é auditável.

### 2.2 Estabilidade dia a dia

| | ativas | realizado > 0 | Σ realizado | média / carteira (base) | acerto (base) | ainda no top-30 | no top-100 | elegíveis (≥ 8) |
|---|---|---|---|---|---|---|---|---|
| top-30 D1 → D2 | 27/30 | 24 | +79,6 SOL | 2,95 (0,14) | 65 % (51 %) | 10 | 17 | 24 |
| top-30 D1 → D3 | 27/30 | 24 | +52,5 SOL | 1,94 (0,14) | 63 % (51 %) | 12 | 18 | 21 |
| top-30 D2 → D3 | 27/30 | 22 | +59,7 SOL | 2,21 (0,14) | 63 % (51 %) | 12 | 18 | 20 |

Spearman (carteiras elegíveis nos dois dias): PnL realizado D1↔D2 **ρ = 0,61** (n = 292, t = 12,9), D2↔D3 **ρ = 0,65** (n = 307); acerto D1↔D2 ρ = 0,47, D2↔D3 ρ = 0,48. Interseção dos top-30: D1∩D2 = 10, D2∩D3 = 12, D1∩D3 = 12. **Persistência forte** — mas do lucro de quem é rápido, não de quem escolhe bem: a persistência mede que o mesmo bot continua chegando primeiro.

## 3. Teste do sinal: "≥ 2 carteiras do top-30 do dia anterior compraram o mesmo mint em ≤ 60 s"

**Definição.** Para D2 usa-se o top-30 de D1; para D3, o de D2 (nunca o do próprio dia). Por mint, o primeiro instante em que duas carteiras **distintas** do top compram com ≤ 60 s de intervalo; entrada = a 2.ª compra. 341 sinais (205 em D2, 136 em D3); idade da moeda na entrada p10/p50/p90 = 0,6 s / **27 s** / 404 s; **43 % dos sinais têm as duas compras no mesmo segundo** (67 % em ≤ 5 s) — pacote, quase certamente o mesmo operador (7 pares de carteiras respondem por 51 sinais: `2k6aaxsz`+`J3gZFpvs` 11×, `EaaCfVxV`+`8jsPACii` 14×, `24678QKx`+`CFt926D6` 7×…). 21 % dos mints sinalizados completaram a curva — **abaixo** dos 27–28 % do controle (o controle é ponderado por trade, e mints muito negociados graduam mais).

**Trajetória.** Preço = `price` das trades seguintes na fita (SOL/token), relativo ao preço de entrada. Três atrasos de entrada: **0 s** (o preço do gatilho — só para ver o que os bots capturam), **3 s** (o que um feed de evento veria: 1.ª trade ≥ 3 s após o gatilho), **20 s** (piso da fita hoje). Sem trade posterior dentro da janela = preço "inalterado" (na prática moeda morta/ilíquida). **Censura:** se a última trade do mint na fita vem antes de entrada + 30 min, a trajetória é censurada (24–31 % dos sinais, 30 % do controle a 3/20 s) — o exit "no tempo" usa a última cota vista, otimista. **Controle:** 5 431 compras aleatórias da fita (não-criador, mesmas 72 h), mesma régua; ponderação por faixa de idade não muda o controle (R médio −0,038 cru e −0,038 reponderado), então reporto o cru. Paper = trailing 30 % do pico, time-stop 30 min, taxa 1,75 % por perna, **R = (múltiplo líquido − 1)/0,5** (régua da EXP-M14). `hold 5/15 min` = sair a mercado nesse instante, sem stop.

| atraso | braço | n | +60 s (med / méd) | +5 min | +15 min | máx 30 min med · P(≥1,5×) · P(≥2×) | trailing: acerto · **R méd** · R med · P(R ≥ 1) · P(R ≤ −0,5) | saiu por trail / tempo / censura | hold 5 min R méd (med) | hold 15 min R méd (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 s | sinal | 341 | 1,107 / 1,237 | 1,104 / 1,296 | 1,104 / 1,359 | 1,60 · 55 % · 34 % | 41 % · **+0,04** · −0,21 · 10 % · 33 % | 75 / 1 / 24 % | +0,50 (+0,13) | +0,62 (+0,13) |
| 0 s | controle | 5 431 | 1,000 / 1,050 | 1,000 / 1,063 | 1,000 / 1,060 | 1,03 · 22 % · 11 % | 22 % · **−0,04** · −0,07 · 6 % · 18 % | 35 / 13 / 51 % | +0,05 (−0,07) | +0,05 (−0,07) |
| **3 s** | sinal | 314 | 1,008 / 1,059 | 0,998 / 1,153 | 0,997 / 1,213 | 1,35 · 42 % · 24 % | 36 % · **+0,03** · −0,19 · 11 % · 31 % | 68 / 1 / 31 % | +0,23 (−0,07) | +0,34 (−0,07) |
| 3 s | controle | 2 943 | 1,011 / 1,049 | 1,004 / 1,072 | 0,993 / 1,071 | 1,29 · 36 % · 18 % | 37 % · **−0,04** · −0,20 · 11 % · 33 % | 62 / 8 / 30 % | +0,07 (−0,06) | +0,07 (−0,08) |
| **20 s** | sinal | 255 | 0,964 / 1,000 | 0,967 / 1,088 | 0,967 / 1,152 | 1,35 · 38 % · 22 % | 29 % · **−0,06** · −0,31 · 9 % · 35 % | 69 / 1 / 30 % | +0,10 (−0,13) | +0,23 (−0,13) |
| 20 s | controle | 2 682 | 1,009 / 1,027 | 1,002 / 1,062 | 0,992 / 1,058 | 1,28 · 34 % · 16 % | 35 % · **−0,06** · −0,20 · 10 % · 33 % | 61 / 9 / 30 % | +0,05 (−0,07) | +0,04 (−0,09) |

(A 3 s e 20 s o controle perde as compras sem trade posterior — n cai de 5 431 para ~2 900 — e por isso o controle a 0 s, que inclui 2 385 entradas "mortas", não é comparável aos outros dois.)

**Bootstrap (2 000 reamostras) da diferença sinal − controle em R médio:**

| atraso | trailing 30 % / 30 min | hold 5 min | hold 15 min |
|---|---|---|---|
| 3 s | +0,07 [−0,06; +0,21] | +0,16 [−0,01; +0,32] | +0,27 [+0,08; +0,48] |
| 20 s | +0,00 [−0,14; +0,16] | +0,05 [−0,11; +0,21] | +0,18 [+0,00; +0,39] |

**Distribuição de R (trailing), quantis 5/10/25/50/75/90/95 %:** sinal a 3 s: −0,98 / −0,74 / −0,57 / −0,19 / +0,32 / +1,02 / +1,67; controle: −1,48 / −0,95 / −0,62 / −0,20 / +0,23 / +1,04 / +1,80. A 20 s: sinal −0,97 / −0,80 / −0,62 / **−0,31** / +0,08 / +0,86 / +1,56; controle −1,53 / −0,92 / −0,62 / −0,20 / +0,21 / +0,97 / +1,74. Sinal e controle são a mesma distribuição; a única diferença visível é a cauda esquerda mais curta do sinal (menos ruínas abaixo de −1) — consistente com "mints em que o pacote ainda não descarregou".

**Subconjuntos (a 20 s):** duas compras com ≥ 2 s de intervalo (não-pacote) n = 157: R méd −0,11, acerto 29 %; pacote (< 2 s) n = 98: +0,02; ambas seguradoras (idade mediana > 60 s) n = 93: −0,00, hold 5 min +0,34 (mediana −0,03); entrada com moeda ≥ 60 s n = 135: −0,08. Nenhum subconjunto muda a conclusão; o "ambas seguradoras" é o único com hold-5-min positivo, e n = 93 com SD 1,3 R não decide nada.

**Onde foi parar o lucro do top-30?** Entre o gatilho e 3 s o +60 s cai de 1,107× para 1,008×; entre 3 s e 20 s, para 0,964×. A vantagem das carteiras vencedoras é consumida em **≤ 3 s** — pelo próprio bloco em que elas entram. Seguir é chegar depois do que se queria seguir.

## 4. Caveats (por que os números acima são o teto, não o piso)

1. **Cobertura da fita: 5,3 % dos mints, ~100 s por mint, 1 puxada.** O PnL "realizado" é o dos scalps que cabem em 100 s; o de quem segura não é mensurável (marcação a última cota vs a zero difere em 5–40 SOL por carteira). O ranking é, por construção, um ranking de **snipers e flippers**. R47 mediu 17 de 139 rastreados com fita naquele instante; aqui, 5 469 mints com fita em 72 h contra 102 185 criados.
2. **Atraso da fita 26 s (p50) / 99 s (p90).** Nenhum sinal desta fita é acionável em < 20 s. O portão de evento (T4.52b) recebe todas as trades dos mints jovens e é a fonte que teria o "3 s" — mas é precisamente a 3 s que o sinal já se dissolve (+60 s = 1,01×). O feed corrige o atraso, não a tese.
3. **Sobrevivência dupla.** (a) Só há fita em mints que a mesa rastreou/apostou (16 % deles completaram, contra 3,1 % da população); (b) os desfechos só são medíveis enquanto a fita continua — 24–31 % das trajetórias de sinal e ~30 % do controle são censuradas, e o "exit no tempo" da censura usa a última cota (otimista). Só 31 sinais têm 30 min inteiros de fita; neles, o trailing dá R médio −0,12 (0 s) / −0,22 (3 s) / −0,27 (20 s).
4. **Mesmo operador.** 43 % dos sinais são duas carteiras do top comprando no mesmo segundo; 7 pares fixos respondem por 51 sinais. "Duas carteiras inteligentes concordam" é, na maioria, **um** operador com duas chaves (ou um bundle de lançamento com o criador — 16 % das compras do top são a idade ≤ 2 s, e as carteiras `8ki679dZ`, `24678QKx`, `AMDEmVoc`, `DxhpC9c4`, `7cp6zxvh` compram **antes** do `created_at` registrado, i.e. no mesmo bloco do `create`). Excluí o criador nominal; não consigo excluir os cúmplices dele sem grafo de financiamento.
5. **Bots.** Corte em > 200 trades/dia removeu 165 carteiras (177 077 trades, 14 % da fita). Muitas do top-30 fazem 100–190/dia; o corte é arbitrário e um corte em 100/dia tiraria metade do top.
6. **Régua.** R = (múltiplo líquido − 1)/0,5 com taxa 1,75 %/perna, como na EXP-M14; sem slippage nem taxa de rede; o preço de saída é a trade seguinte na fita, não uma execução. Um dia de top-30 tem só ~170 sinais/dia, e a metade é pacote.
7. **Uma semana só, sem regime.** 72 h de 15–18/09; a persistência ρ ≈ 0,6 pode ser um artefato de bots estáveis nesta semana.

## 5. Decisão sugerida

- **Não** ligar "seguir carteiras" na mesa: com a saída da mesa, R = −0,06 a 20 s e +0,03 a 3 s, indistinguível do controle. A pergunta do Everton está respondida com número, não com opinião.
- A persistência das carteiras (ρ 0,6) é real e barata de manter (uma tabela `meme_wallet_scores` diária). Vale como **feature de contexto** (quantas carteiras persistentes já entraram, e se elas venderam), não como gatilho.
- Se alguém quiser fechar a questão de vez: EXP-M15 (rascunho em `obsidian/05-EXPERIMENTS/EXP-M15-carteiras-vencedoras.md`), `research_only` sobre o portão de evento, previsão `descartar`, com a única fresta (hold 15 min) medida contra o mesmo controle. Pré-requisito: o placar de carteiras (item acima) e o feed de evento com < 3 s.

## 6. SQL e scripts (scratchpad da sessão)

```sql
SET statement_timeout = '60s';
-- cobertura (q1–q3)
SELECT source, coalesce(program,'pump'), count(*), min(block_time), max(block_time), count(DISTINCT mint), count(DISTINCT trader)
FROM meme_trades WHERE block_time >= now() - interval '72 hours' GROUP BY 1,2;
WITH t AS (SELECT t.mint, min(block_time) first_t, max(block_time) last_t, count(*) n, count(DISTINCT received_at) pulls, k.created_at, k.completed_at
           FROM meme_trades t JOIN meme_tokens k USING (mint)
           WHERE block_time >= now() - interval '72 hours' AND coalesce(program,'pump')='pump' GROUP BY 1,6,7)
SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM first_t-created_at)),
       percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM last_t-created_at)),
       percentile_cont(0.5) WITHIN GROUP (ORDER BY pulls), count(*) FILTER (WHERE completed_at IS NOT NULL),
       count(*) FILTER (WHERE last_t-first_t > interval '30 min') FROM t;

-- pares (carteira, mint) para carteiras com >= 8 round-trips (q6; exportado em CSV, ranking em Polars)
WITH tr AS (SELECT trader, mint, block_time, side, sol_lamports, token_amount, price FROM meme_trades
            WHERE block_time >= now() - interval '72 hours' AND coalesce(program,'pump')='pump'),
tc AS (SELECT trader, max(d) max_daily FROM (SELECT trader, count(*) d FROM tr GROUP BY trader, date_trunc('day', block_time)) x GROUP BY trader),
p AS (SELECT trader, mint, min(block_time) FILTER (WHERE side='buy') first_buy, min(block_time) first_t, max(block_time) last_t,
             count(*) FILTER (WHERE side='buy') n_buys, count(*) FILTER (WHERE side='sell') n_sells,
             sum(sol_lamports) FILTER (WHERE side='buy') sol_in, sum(sol_lamports) FILTER (WHERE side='sell') sol_out,
             sum(token_amount) FILTER (WHERE side='buy') tok_in, sum(token_amount) FILTER (WHERE side='sell') tok_out
      FROM tr GROUP BY trader, mint),
rt AS (SELECT trader, count(*) FILTER (WHERE n_buys>0 AND n_sells>0) rt FROM p GROUP BY trader),
lp AS (SELECT DISTINCT ON (mint) mint, price last_price, block_time last_mint_t FROM tr ORDER BY mint, block_time DESC)
SELECT p.*, lp.last_price, lp.last_mint_t, k.created_at, k.completed_at, (k.creator = p.trader) is_creator, tc.max_daily
FROM p JOIN rt USING (trader) JOIN tc USING (trader) JOIN lp USING (mint) LEFT JOIN meme_tokens k ON k.mint = p.mint
WHERE rt.rt >= 8;

-- trades das carteiras do top (q7): WHERE trader = ANY(ARRAY[...64 carteiras...])
-- controle (q8): compras aleatórias, não-criador, 48 h → 1 h atrás, random() < 0.012 LIMIT 8000
-- trajetórias (q9): VALUES (mint, entry) × meme_trades ON block_time BETWEEN entry AND entry + 31 min
-- fim de cobertura por mint (q10): max(block_time) em meme_trades e max(end_time) em meme_features_1m
```

Scripts: `rank.py` (classificação de pares, marcações), `rank2.py` (top-30 realizado, persistência, Spearman), `sig.py` (sinais), `outc.py <LAG>` (trajetórias, trailing, bootstrap). Saídas: `rank2.out`, `outc0.out`, `outc3.out`, `outc20.out`.
