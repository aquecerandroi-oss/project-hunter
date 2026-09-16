---
tags: [knowledge, nota, meme, pumpfun, evento, narrativa, m4, exp-m8]
tema: memecoin / pump.fun / evento -> moeda: a primeira medida (8 eventos do plantao de 16/09 contra 18 335 criacoes do dia)
fonte: banco da VPS (meme_events, meme_tokens, meme_curve_snapshots, meme_features_15s, meme_proposals), 16/09/2026 00:00-15:5x BRT
fonte_url: https://github.com/aquecerandroi-oss/project-hunter/blob/main/infra/scripts/sql/research/2026-09-16-r6-q01-casamento-evento-moeda.sql
lido_em: 2026-09-16
evidencia: medicao propria (SQL em infra/scripts/sql/research/2026-09-16-r6-q0{1,2,3,4,5}.sql; 1 009 moedas casadas, amostras de 200 + controle pareado por hora)
hipotese_testavel: sim
astra: nao consultada nesta nota (medida de banco, 16/09 16:0x BRT)
confianca: medicao de um dia so (n pequeno, sem replicacao)
owner: astra-quant
updated: 2026-09-16
status: vivo
---

# KB-0100 — Evento move moeda? A primeira medida (16/09, 8 eventos)

**Pergunta:** dos 8 eventos que o plantao registrou hoje em `meme_events`, algum deixou marca mensuravel nas
criacoes do pump.fun — em **quantidade** de moedas e em **desfecho** delas?

## 0. A regra de casamento (escrita antes de olhar o desfecho)
Uma moeda criada hoje (00:00 BRT ate 15:5x) casa com um evento se **`upper(symbol)` esta na lista de tickers do
evento**, **ou** `name ~* regex-da-narrativa` (com fronteira de palavra, para `arc` nao pegar "march"), **ou**
`twitter ~* handle` quando o evento tem handle. Sem janela temporal na regra — e' justamente a latencia
criacao-vs-`observed_at` que queremos medir. Listas por evento em `2026-09-16-r6-q01-casamento-evento-moeda.sql`
(ex.: ARC = `ARC|ARCH|ARCC|CIRCLE|USDC` + nome ~ `arc|circle`; Elon = `ELON|XMONEY|PAIDLON|800B|H1T|ELONIUS` +
nome ~ `elon|x money|musk`). Colunas sociais da 0041 (`twitter`, `telegram`, `website`) conferidas no banco.

## 1. Quantas moedas cada evento "gerou" (18 335 criacoes no dia)
| evento (`observed_at` BRT) | casadas | antes | depois | mediana da latencia (depois) | leitura |
|---|---|---|---|---|---|
| 1 Fed +25 bp (15:00) | 26 | 16 | 10 | 18,4 min | ruido: ~2/h o dia inteiro |
| 2 Clarity Act / marco fiscal (14:29) | 107 | 104 | **3** | 50,8 min | o pico foi h13 (13 moedas), **antes** do registro |
| 3 Circle Arc mainnet (07:30) | 396 | 69 | **327** | 172,8 min | h07-h09 = 52/55/54 vs ~10-15/h na madrugada — **3-4x a base**, logo apos a noticia |
| 4 Onda Elon/X Money (15:42) | 347 | 328 | 19 | 10,2 min | fluxo constante (~20-30/h); h14-h15 = 49/44 |
| 5 TOKEN2049 (15:50) | **0** | 0 | 0 | — | ninguem cunha o nome de conferencia |
| 6 PRAXIS (15:42) | 105 | **105** | 0 | — | **104 das 105 na hora 14** (0 nas demais) — a onda foi 1h40 antes do registro |
| 7 HBO Max hackeado (14:06) | **0** | 0 | 0 | — | incidente de marca nao vira meme |
| 8 AVISO clones "fundo" (15:42) | 35 | 33 | 2 | 9,3 min | viveiro continuo o dia inteiro (1-5/h) |

Uniao sem repeticao: **1 009 moedas (5,5 % do dia)**. Dois eventos de verdade *precederam* a rajada (ARC) ou
*coincidiram* com ela (PRAXIS); nos demais a rajada nao existe ou o plantao chegou depois dela.

## 2. Desfecho: casadas vs. controle pareado por hora (amostras de 200)
Pico de **SOL real na curva** (`real_sol_reserves`; KB-0098: mcap teorico e' Mayhem), dia todo, mesma hora BRT.
| coorte | n | >= 10 SOL | >= 30 SOL | >= 85 SOL (graduacao) | migraram | mediana pico SOL real | p90 | mediana pico `mcap_sol` (15s) |
|---|---|---|---|---|---|---|---|---|
| casadas (uniao dos 8) | 200 | 33 (16,5 %) | 19 (9,5 %) | **9 (4,5 %)** | 12 (6,0 %) | 0,37 | 30,9 | 28,6 |
| casadas **sem** o viveiro de clones (evento 8) | 200 | 26 (13,0 %) | 12 (6,0 %) | **2 (1,0 %)** | 5 (2,5 %) | 0,34 | 16,2 | 28,6 |
| controle (sem casamento, mesma hora) | 200 | 24 (12,0 %) | 9 (4,5 %) | **1 (0,5 %)** | 6 (3,0 %) | 0,49 | 12,7 | 30,3 |

**A armadilha:** das 9 casadas que chegaram a 85 SOL, **8 sao clones "fundo/instituicao"** (`WOFI`, `ECTF` x3,
`NTDA`, `WOTF`, `WOFI` x2) e a nona e' `PAIDELON` — todas graduaram exatamente em 85,0 SOL, assinatura de
viveiro, nao de demanda. Tirando o evento 8, casada e controle sao **indistinguiveis** (13 % vs 12 % em 10 SOL;
1 % vs 0,5 % em 85 SOL, n = 200). O melhor nao-clone do dia: `ARC` das 08:12 (74,2 SOL, migrou), `h1t` das
14:57 (75,8), `PRAXIS` das 14:20 (59,8). Nota lateral: o controle tem **68 Mayhem** contra 23 nas casadas — quem
copia narrativa de noticia usa menos o agente.

## 3. O casamento automatico do job (T4.26) — 1 de 8, e no evento errado
`meme_events.mint` estava NULL nos 8 durante toda a corrida; as 15:57 BRT o job casou **exatamente um**:
o evento 8 (AVISO) -> `8EoRx3DZxK8vbq8wMkY32QpBfcwnb9dUutq2ZoaTpump` (`matched_at 18:57:19Z`) — e' um **clone
`WOTF` novo**, nao o mint que a nota citava (`NnLz6...`). Ou seja: o unico casamento do dia ligou um aviso de
"nao perseguir" a uma moeda de viveiro. Por que os outros nao casaram (`2026-09-16-r6-q03-job-de-casamento.sql`):
- **ARC tinha 60 candidatas** pela propria regra do job (symbol = `ARC` nos 60 min apos 07:30) e ainda assim nao
  casou: o job so varre eventos com `observed_at` nos **ultimos 65 min**, e o plantao registrou o ARC as ~15:4x
  com `observed_at` retroativo de 8 h. **Evento registrado tarde nunca sera casado** — e' o buraco estrutural.
- `PAIDLON`/`PRAXIS`: 0 candidatas na janela porque a janela e' **so para frente** (60 min apos o evento) e as
  moedas nasceram **antes** (PRAXIS: 103 com simbolo exato entre 14:01 e 14:58; PAIDLON: 2, 11:50 e 15:20).
- Fed, Clarity, HBO, TOKEN2049: sem `symbol_hint`/`handle_hint` — a regra nao tem por onde pegar.
- `meme_proposals`: **874 propostas, 0 com `event_id`**. O `event_gate`/`event_v0/1` ainda nao teve um so caso.

## 4. Conclusao honesta (5 linhas)
1. **Em quantidade, sim, uma vez:** a Circle Arc mainnet triplicou a criacao de moedas "ARC/Circle" por 3 h
   (~15/h -> ~54/h, 327 moedas depois do `observed_at`); PRAXIS mostra a rajada (104 numa hora) mas o plantao
   chegou 1h40 depois dela; Fed, Clarity, HBO e TOKEN2049 nao moveram nada.
2. **Em dinheiro, nao:** sem o viveiro de clones, casada = controle dentro do ruido (n = 200 por braco, 1 dia).
3. **O que existe de vantagem hoje e' o viveiro** (85,0 SOL cravado, migracao imediata) — exatamente o que o E2
   recusa, e deve continuar recusando.
4. **Falta para medir direito:** (a) fonte de noticia **em tempo real** com `observed_at` do fato, nao do
   plantao — sem isso a latencia e a janela do job sao ficcao; (b) janela simetrica no casamento (-30/+60 min) e
   varredura de eventos com `observed_at` retroativo; (c) n de dias (1 dia, 1 009 moedas, e' anedota, nao taxa).
5. **Previsao mantida:** `event_v0/1` -> `descartar` ate que (a) e (b) existam; a nota nao muda limiar nenhum.

## Ligacoes
[[05-EXPERIMENTS/EXP-M8-evento-que-pode-dar-bum]] · [[02-MARKET/Eventos/2026-09-16]] ·
[[11-KNOWLEDGE/KB-0098-quantos-bums-reais-ha-por-dia-e-quanto-tempo-temos]]
