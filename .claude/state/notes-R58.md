# R58 — Explosão de compradores (buyer burst) tem vantagem? — 2026-09-18

**Resposta curta: não, na amostra sem viés.** Sobre o fluxo por trade da cadeia inteira (25 min, 1 920 mints,
71 032 trades), **as 54 células do grid dão R médio negativo** (−4,3 % a −9,1 %, hit 22–29 %). O "sinal positivo"
que a fita do banco mostra (−0,2 % a +6,8 % com reentrada; +9 % a +19 % na primeira explosão por mint) é
**sobrevivência**: o banco só tem fita, na janela da captura, para 51 dos 1 920 mints (2,7 %) — os que o radar
já priorizava (`graduating`, aposta aberta) —, e nesses mesmos 51 o sinal ao vivo também é positivo (+3 a +8 %),
enquanto nos outros 1 869 é −9 a −14 %. A explosão, em média, é o topo do pacote de lançamento: o pico mediano
fica só +9 % acima da entrada (custo de ida e volta ≈ 5,5 %), chega 5 s depois do gatilho e em 26 % dos casos já
passou quando a compra pousa. **Não abro EXP-M16**: não há sinal a pré-registrar.

## 1. Dados

| Fonte | Janela | Trades | Mints | O que é | Limite |
|---|---|---|---|---|---|
| (b) captura ao vivo, `logsSubscribe` **no programa pump** (`6EF8rr…`), `processed`, RPC público | 18/09 17:38:27–18:03:40 UTC (14:38–15:03 BRT), 25,2 min | 71 032 (2 788/min) | 1 920 | todo `TradeEvent` da curva, reservas pós-trade exatas → preço marginal `vsol/vtok` | 25 min de um horário; `processed` pode incluir tx de fork; 0 reconexões, 0 frames perdidos, 0 malformados; 484 372 notificações, 81,7 % tx **falhadas** (bots) descartadas |
| (b') captura ao vivo, 30 mints mais recentes por PDA, `confirmed` (o desenho do radar/probe) | mesma janela | 1 380 | 26 (4 nunca negociaram) | mesmo decodificador | idade dos 30 na assinatura: 5–57 s; 97 % dos trades coincidem com (b) (1 377/1 423), 46 só em `processed`, 2 só em `confirmed` |
| (c) `meme_trades` (`program='pump'`, `source='swap_api'`) + `meme_tokens` | 17/09 17:39 → 18/09 17:39 UTC, 24 h | 376 800 (181 vendas de 0 lamport removidas) | 1 783 | fita REST polled; `price` = preço médio do trade | `received_at − block_time` p50 29 s, p90 106 s; **cobertura 2,7 % dos mints que negociaram** (medido contra (b)); `price` médio favorece a entrada (compra média < spot) |
| (a) fixtures `t452b_ws_*` | — | 13 logs | — | — | pequenas demais; usadas só para validar o formato |

`meme_features_15s` **não tem** `real_sol_reserves` (tem `mcap_sol`, `curve_progress_pct`); a série de 15 s não
foi necessária porque a fita dá o caminho de preço por trade. Dos 1 920 mints ao vivo, 644 têm linha de 15 s e
1 316 existem em `meme_tokens`.

Cobertura e atraso do RPC público (mesma tx nas duas assinaturas): `received_at − block_time` p50 1,50 s /
p90 2,01 s / p99 5,07 s em `processed`; `confirmed` chega **0,06 s** depois (p90 0,12 s) — no endpoint público
a diferença entre os dois compromissos é desprezível; o `block_time` tem granularidade de 1 s, então o atraso
real é ~1–2 s.

## 2. Método (o mesmo código nas três fontes)

Motor: `scratch/r58/burst_bt.py` (puro, sem IO, relógio = `block_time`); testes sintéticos com valores
esperados em `test_burst_bt.py` (6 passam: 5.º comprador dispara, venda do criador bloqueia, compra do criador não
conta, R do trailing conhecido a 1e-4, saída por tempo usa o último preço ≤ T, **trade futuro não move sinal,
entrada nem saída**).

- **Sinal** (em cada compra, por mint): ≥ N compradores únicos (≠ criador) com compra em `(t−W, t]`,
  fluxo líquido de SOL na janela > 0 (⇔ `real_sol` subindo) e **nenhuma venda do criador** vista até `t`.
  Disparo por borda: um sinal por episódio; rearma quando a condição fica falsa. "Reentrada" = novo sinal
  depois de fechar a posição; "primeira explosão" = só o primeiro sinal do mint.
- **Entrada**: preço da curva após o último trade com `block_time ≤ t_sinal + D`, `D = 2 s` (ouvir 1,5 s +
  pousar; sensibilidade 0/4/5 s). Compra de 1 SOL: `tokens = (1 − 1,25 %) / (P_entrada × 1,03)`.
- **Saída**: primeiro trade com `preço ≤ pico × (1 − X)` (pico corrente desde a entrada) → venda pousa `D`
  depois ao preço então vigente; senão em `t_entrada + T`. Recebe `tokens × P_saída × (1 − 1,25 %)`
  (slippage de venda 0; sensibilidade 3 %). `R = recebido / 1 SOL − 1`.
- **Grade**: N ∈ {5, 8, 12}, W ∈ {10, 20, 30} s, X ∈ {10, 15, 20} %, T ∈ {2, 5} min = 54 células.
- **Métricas**: sinais/h, hit (R > 0), R médio/mediano, ΣR, max drawdown da equity ΣR em ordem
  cronológica, top-3 e ΣR − top-3, % saídas por trailing, tempo de formação (1.º → N-ésimo comprador),
  janela aberta após o gatilho, gatilho → pico, pico/entrada.

## 3. Resultado ao vivo (cadeia inteira, 25 min) — o que vale

Grid completo em `scratch/r58/grid_live_re_d2.md`. Resumo (com reentrada, D = 2 s, slippage venda 0):

| N | W | X | T | n | /h | hit | R médio | R mediano | ΣR | MDD | Σ−top3 | trail | pico/entrada p50 | idade p50 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 5 | 10 | 20 % | 5 | 474 | 1 137 | 24 % | −9,1 % | −14,7 % | −43,1 | −43,7 | −53,5 | 73 % | +6,1 % | 20 s |
| 5 | 30 | 10 % | 2 | 727 | 1 744 | 25 % | −5,5 % | −9,4 % | −40,3 | −40,3 | −50,8 | 78 % | +2,3 % | 31 s |
| 8 | 20 | 20 % | 5 | 367 | 880 | 26 % | −6,0 % | −16,8 % | −22,1 | −23,0 | −34,1 | 79 % | +9,3 % | 16 s |
| 8 | 30 | 10 % | 2 | 517 | 1 240 | 27 % | **−4,3 %** (melhor célula) | −9,8 % | −22,1 | −22,1 | −32,6 | 84 % | +5,0 % | 32 s |
| 12 | 10 | 20 % | 5 | 228 | 547 | 24 % | −8,7 % | −18,3 % | −19,9 | −20,6 | −29,4 | 85 % | +9,4 % | 11 s |
| 12 | 30 | 10 % | 2 | 397 | 952 | 26 % | −5,8 % | −9,8 % | −23,2 | −23,4 | −31,3 | 87 % | +5,0 % | 30 s |

Faixa das 54 células: R médio −4,3 % … −9,1 %; hit 22–29 %; 547–1 744 sinais/h; ΣR sempre negativa e o
top-3 não muda o sinal (Σ−top3 ainda mais negativa). A idade mediana no sinal é 11–34 s: **a explosão típica
é o lançamento** (dev + bundle + primeiros compradores).

Variantes (N = 8, W = 20, X = 20 %, T = 5; `scratch/r58/variants.md`):

| variante | n (/h) | hit | R médio | R mediano | ΣR | Σ−top3 |
|---|---|---|---|---|---|---|
| base D = 2 s | 367 (880) | 26 % | −6,0 % | −16,8 % | −22,1 | −34,1 |
| D = 4 s | 323 (775) | 25 % | −5,8 % | −16,1 % | −18,8 | −30,5 |
| D = 0 s (irreal) | 482 (1 156) | 25 % | −7,1 % | −16,4 % | −34,3 | −45,8 |
| slippage de venda 3 % | 367 (880) | 22 % | −8,8 % | −19,3 % | −32,4 | −44,0 |
| idade < 30 s | 209 (501) | 24 % | −7,9 % | −17,9 % | −16,5 | −25,1 |
| idade 30–120 s | 115 (276) | 25 % | −8,8 % | −19,8 % | −10,1 | −17,7 |
| idade 120–600 s | 61 (146) | 34 % | +0,8 % | −8,1 % | +0,5 | −5,6 |
| idade ≥ 600 s | 28 (67) | 18 % | −9,9 % | −9,7 % | −2,8 | −3,4 |
| formação ≥ 3 s (anti-bundle) | 318 (763) | 26 % | −4,5 % | −16,5 % | −14,3 | −27,4 |
| formação ≥ 5 s e idade ≥ 60 s | 134 (321) | 31 % | −3,3 % | −14,8 % | −4,4 | −13,4 |
| primeira explosão por mint | 179 (429) | 25 % | −8,8 % | −16,8 % | −15,7 | −22,2 |
| N = 5, W = 10, idade ≥ 120 s | 118 (283) | 31 % | −3,9 % | −7,7 % | −4,5 | −10,4 |

Nenhuma variante fica positiva com significância; a única não-negativa (idade 120–600 s, +0,8 %, n = 61) vira
negativa sem o top-3. Sem atraso nenhum (D = 0) continua negativo: **não é problema de latência, é o sinal**.

## 4. Fita do banco (24 h) — e por que ela engana

Grid completo em `grid_db_all.md`, `grid_db_first.md`, `grid_db_slip3_d5.md`.

| política | células | R médio | hit | R mediano | sinais/h | top3/Σ |
|---|---|---|---|---|---|---|
| reentrada, D = 2 s, slip venda 0 | 54 | −0,2 % … +6,8 % (X = 20 %, T = 5 as melhores) | 39–46 % | −2,6 % … −5,3 % | 77–216 | 7–34 % (X = 10 % concentra; sem sentido onde ΣR ≈ 0) |
| reentrada, D = 5 s, slip venda 3 % | 54 | −3,4 % … +1,8 % | 33–41 % | −8,0 % … −8,2 % | 73–191 | 32–51 % onde positiva |
| primeira explosão por mint, D = 2 s | 54 | +8,0 % … +18,8 % | 49–56 % | −0,7 % … +4,2 % | 35–42 | 8–14 % |

Split por idade real (`meme_tokens.first_seen_at`), N=8 W=20 X=20 % T=5: 0–30 s +16,3 % (n=416), 30–120 s
+10,2 % (394), 120–600 s +3,9 % (787), 10–60 min +3,1 % (477), > 1 h +3,7 % (349).

**A prova de que é sobrevivência** (mesmo sinal, mesma captura ao vivo, dividido por "o banco tem fita deste
mint na janela?"; `split_d2.md`):

| célula | grupo | n | hit | R médio | ΣR | Σ−top3 |
|---|---|---|---|---|---|---|
| 8/20/20 %/5, primeira | com fita no banco (51 mints) | 25 | 36 % | **+3,1 %** | +0,8 | −3,4 |
| | sem fita (1 869 mints) | 154 | 23 % | **−10,7 %** | −16,5 | −21,3 |
| 8/20/20 %/5, reentrada | com fita | 96 | 35 % | +7,7 % | +7,4 | −3,0 |
| | sem fita | 271 | 23 % | −10,9 % | −29,5 | −37,1 |
| 5/10/20 %/5, reentrada | com fita | 106 | 39 % | +6,5 % | +6,9 | −3,5 |
| | sem fita | 368 | 20 % | −13,6 % | −49,9 | −54,0 |

A fita por mint é puxada por prioridade (aposta aberta > `graduating` > `new` > resto, 13 req/min) — ela
**existe porque** a moeda já ia bem. Um back-test sobre `meme_trades` herda essa escolha do futuro. Some-se o
preço médio do trade (entrada abaixo do spot) e o atraso de 29 s da fita (irrelevante no back-test por
`block_time`, fatal ao vivo).

## 5. Tempo físico de reação (N = 8, W = 20, todos os sinais ao vivo)

| medida | p25 | p50 | p75 | observação |
|---|---|---|---|---|
| formação: 1.º comprador → 8.º | 2 s | 11 s | 18 s | 22 % em ≤ 1 s = mesmo bloco (bundle) |
| janela aberta após o gatilho (condição continua verdadeira) | 1 s | 8 s | 17 s | 32 % fecha em ≤ 2 s |
| gatilho → pico de preço | 2 s | 5 s | 20 s | 26 % já passou quando a compra pousa (D = 2 s) |
| pico/entrada − 1 | — | +9 % | — | p90 +68 %; custo de ida e volta ≈ 5,5 % |
| ouvir o evento (`received_at − block_time`) | — | 1,50 s | 2,01 s (p90) | p99 5,07 s; RPC público |

Com 1,5 s para ouvir mais ~1 s para pousar, a compra chega quando a mediana do movimento já deu +5 % dos +9 %
que dará; não há assimetria que pague 5,5 % de custo com 25 % de acerto.

## 6. Ressalvas

- **Amostra**: 25 min de um só horário (14:38–15:03 BRT, manhã dos EUA); 367–727 sinais por célula é bastante
  para o sinal médio, pouco para caudas. O padrão (todas negativas, pico ≈ custo) é consistente entre células,
  o que reduz o risco de ser acaso, mas um dia inteiro pela cadeia (a captura custa 25 MB/25 min) é o próximo
  passo se alguém quiser insistir.
- **RPC público**: sem `dropped`, sem reconexão, mas `processed` pode entregar tx que nunca confirmam
  (0 evidências aqui: 97 % de coincidência com `confirmed` e 46 tx a mais em 25 min, parte do efeito de borda).
  A doutrina (§8.2 `RISK_ENGINE_MEME.md`) diz que `processed` nunca decide — a decisão real teria +0,06 s.
- **Sobrevivência**: a fita do banco é 2,7 % dos mints e os melhores; a captura pela cadeia não tem esse viés.
  Ao vivo a idade é contada do primeiro trade **na captura** (mints nascidos antes de 17:38 parecem mais
  jovens) — afeta só os buckets de idade, não o R.
- **Custos**: taxa 1,25 % por ponta (o papel do Lab usa 1,75 %), 3 % de slippage na compra, 0 na venda
  (sensibilidade com 3 %: piora ~3 pp), impacto próprio não modelado (tamanho irrelevante ao resultado);
  posição aberta no fim da captura sai ao último preço visto (censura).
- **Migração/`complete`**: uma curva que completa deixa de ter trades; a saída por tempo usa o último preço da
  curva — em ~0 % dos sinais (mints com 11–34 s de idade não graduam em 5 min).

## 7. Achados operacionais durante a leitura da VPS (não fazem parte da pergunta)

1. `hunter-meme-worker-1` reiniciou ~17:31 UTC e, desde então, `meme_event_gate_crashed_restarting` aparece
   **12 vezes em 45 min** — o `except Exception` em `event_gate.py:194` loga sem `exc_info`, então a causa não
   está no log; cada reinício ressubscreve e zera a cobertura da fita de eventos (`mark_gap`, 60 s de
   aquecimento) — o modo `shadow` está sendo reiniciado a cada ~4 min.
2. Entre 17:22 e 17:28 UTC o laço `lab` falhou 6× com `TypeError: a float is not an exact number`
   (`lab_models.py:244`, `size_sol` de um conjunto ativo gravado como float); cessou após o reinício.
3. Os logs INFO do httpx imprimem a URL do RPC Helius **com a chave de API** — segredo em `docker logs`.

## 8. Decisão

Sem EXP-M16. A hipótese "≥ N compradores em W s com `real_sol` subindo e criador sem vender" **não** tem
vantagem como gatilho de entrada na amostra sem viés; ela é um marcador de lançamento/bundle. O que a fonte por
trade pode render é outra pergunta: usar a explosão como **contexto** (ex.: "houve explosão há 2–10 min e o
preço segurou ≥ 80 % do pico") ou como **veto** (bundle no mesmo bloco), medido com a mesma captura. Se alguém
quiser um braço sombra mesmo assim, a previsão pré-registrada teria de ser R médio ≤ 0 — um controle, não um
candidato.

## Fontes

- Diretório de trabalho (scratch da sessão, não versionado): `C:/Users/evert/AppData/Local/Temp/claude/C--Users-evert-AppData-Roaming-Claude-scratch-workspaces-6c08dfce-5e18-4922-a01b-bbd5beeca4f3-e9de050b-2d22-439a-99ef-da0860eadc92-scratch-2026-09-04-8b8550/9229a213-ae2c-4e9a-bca5-b3f02ae16415/scratchpad/r58/`.
- Captura e motor: `capture.py`, `burst_bt.py`, `test_burst_bt.py`, `run_grid.py`,
  `detail.py`, `split.py`, `variants.py`, `coverage.py`; dados brutos `program_processed.jsonl` (25 MB),
  `mints30_confirmed.jsonl`, `db_trades_24h.csv.gz`; saídas `grid_*.md`, `split_d2.md`, `variants.md`.
- SQL: `COPY (SELECT t.block_time, t.received_at, t.mint, t.trader, t.side, t.sol_lamports, t.token_amount,
  t.price, k.creator, k.first_seen_at FROM meme_trades t LEFT JOIN meme_tokens k USING (mint) WHERE
  t.block_time > now() − interval '24 hours' AND t.program = 'pump')`; cobertura por mint da captura:
  `count(*) FROM meme_trades / meme_features_15s WHERE mint = … AND block_time BETWEEN 17:38 AND 18:04`.
- Testes: `uv run pytest scratchpad/r58/test_burst_bt.py -q` → `6 passed in 0.52s`.
