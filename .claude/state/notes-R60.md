# R60 — Sniper de lançamento (EXP-M18): comprar em ≤ 1 s após o `create` paga? — 2026-09-19

**Resposta curta: não.** Sobre a cadeia inteira (60 min, 1 072 `create`, 885 lançamentos em SOL avaliados,
114 832 trades), **as 18 células reais do grid (3 entradas × 6 saídas) dão R médio líquido negativo**:
−9,6 % a −15,5 %, acerto 6–16 %, mediana −13,9 % em todas (= o custo de ida e volta com preço parado).
Entrar mais cedo **não ajuda**: +0,5 s (RPC regional) e +1 s (feed por evento) são iguais ou piores do que
+3 s (a infra atual), porque o preço mediano não se move entre +0,5 s e +6 s (50 % das moedas ficam
dentro de ±1 %). Sem slippage e sem prioridade, só com a taxa de 1,25 %/perna, o R médio fica entre −3,9 %
e +1,7 % — o movimento bruto médio do lançamento é ~0 a +2 %, ou seja, **não há assimetria para pagar
custo nenhum**. Até o oráculo "vender no pico exato dos 6 s seguintes" é negativo (−7,2 %); o oráculo de
60 s é positivo (+29 %), mas com mediana −13,5 % e 32 % de acerto: o lucro existe só para quem sabe o futuro
e é feito em 1/3 das moedas. Regra de decisão pré-registrada → **descartar e registrar**: o jogo do
lançamento é dos bots colocados no bloco (30 % dos lançamentos já têm comprador de terceiros no mesmo slot
do `create`; 45 % têm comprador de terceiros em ≤ 1 s). O achado do R58 se repete nesta captura (54 células
de explosão de compradores: −6,6 % a −9,1 %, nenhuma positiva).

## 1. Dados

| Fonte | Janela | O que é | Limite |
|---|---|---|---|
| Captura ao vivo, `logsSubscribe` **no programa pump** (`6EF8rr…`), RPC público `wss://api.mainnet-beta.solana.com`, **`processed`** | 19/09 03:35:09–04:35:09 UTC (**00:35–01:35 BRT, madrugada, hora fraca**), 60,0 min | 559 935 notificações, 70,2 % tx **falhadas** (bots) descartadas; **1 072 `CreateEvent`** (1 072/h) + **114 832 `TradeEvent`** (2 616 mints), 40 `CompleteEvent`; `received_at` (relógio local, µs) + slot em cada evento | 0 reconexões, 0 frames perdidos, 0 malformados, 6 `TradeEvent` com cauda desconhecida (ignorados); `processed` pode incluir tx de fork (ver §6) |
| Mesma assinatura, segunda conexão em **`confirmed`** | mesma janela | 1 072 `create` (**os mesmos 1 072**, 0 só de um lado), 114 904 trades | serve para medir o atraso entre compromissos: `confirmed` chega **+0,18 s** (p50) / +0,27 s (p90) depois de `processed` |
| Captura diurna (**agendada**, 14:00–15:00 BRT) | 19/09 17:00–18:00 UTC | dois processos desanexados (`processed` e `confirmed`) com `--delay 48292` deixados vivos nesta máquina; escrevem `day_processed.jsonl` / `day_confirmed.jsonl` | **não faz parte deste resultado**; só existe se a máquina ficar ligada; analisar com `analyze.py day_processed.jsonl day_confirmed.jsonl` |

Excluídos: **169 `create` (15,8 %) de curvas com quote ≠ SOL** (`vsol` inicial ≠ 30 SOL; os trades vêm com
`vsol = 0`) — um sniper em SOL não as compra; 18 `create` nos últimos 65 s da captura (censura da janela de
60 s). Restam **885 lançamentos** (≈ 903/h em SOL).

Atraso de escuta (`received_at − block ts`): `processed` p50 1,19 s / p90 1,60 s / p99 1,87 s; `confirmed`
p50 1,38 s / p90 1,79 s (o `ts` do evento tem granularidade de 1 s).

## 2. Método (motor puro, testes sintéticos)

Motor: `scratch/r60/launch_bt.py` (puro; relógio = `received_at(evento) − received_at(create)` na mesma
conexão; sem IO, sem relógio de parede). Testes `test_launch_bt.py` (**7 passam**): R líquido com valor
conhecido (preço parado = −13,91 %), preço em +E s usa só trades já vistos (**trade futuro não altera
entrada nem saída**), saídas por tempo, 1.º sell de terceiro (venda do criador não conta), 1.º sell de
comprador do slot da criação, "nasce cheia", reação, oráculo ≥ toda saída real, regra do braço T4.67a.

- **Lançamento**: um `CreateEvent` em curva SOL; o dev-buy vem na própria tx do `create` (82,5 % têm;
  mediana 0,10 SOL, p75 0,89, p90 1,98; 7,7 % > 2 SOL); `delta = 0` para os trades da tx do `create`.
- **Entrada** em `create + E`, E ∈ {0,5 s (RPC regional/co-locado), 1 s (feed por evento), 3 s (infra
  atual)}: preço marginal da curva (`vsol/vtok`) após o último trade com `delta ≤ E` (sem trade: preço do
  dev-buy). Ticket 0,01 SOL: `tokens = 0,01 × (1 − 1,25 %) / (P_in × 1,05)`.
- **Saídas**: `t6`/`t15`/`t60` = preço após o último trade com `delta ≤ T`; `tp_sell` = preço após o
  **primeiro sell de quem não é o criador** depois da entrada (teto 60 s → sai a +60 s; "fallback");
  `cb_sell` = primeiro sell de uma carteira que **comprou no slot do `create`** (inclui o criador; teto
  60 s); `arm` = regra semeada na T4.67a (primeiro de: +6 s, 1.º sell de terceiro, −20 % do pico);
  `peak60` = **oráculo** (maior preço após a entrada em 60 s — teto, não negociável).
- **Custos**: 1,25 %/perna, slippage 5 % na compra e 3 % na venda, **prioridade 0,0002 SOL por tx**
  (2 tx = 0,0004 SOL = 4 % do ticket de 0,01; coluna "s/ prioridade" mostra o efeito).
  `R = recebido / 0,01 − 1`. Impacto próprio não modelado (0,01 SOL em 30 SOL virtuais ≈ 0,03 %).
- **Métricas**: n, hit (R > 0), R médio/mediano, ΣR e Σ em SOL (0,01/ticket), top-3 / lucro bruto,
  Σ − top-3, max drawdown da equity ΣR em ordem cronológica, % saídas por fallback, t_out mediano.

## 3. Resultado (60 min, 885 lançamentos; R líquido)

| entrada | saída | n | hit | R médio | R mediano | ΣR | Σ SOL | top-3/lucro | Σ−top3 | MDD | R s/ prior. | fallback | t_out p50 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| +0,5 s | t6 | 885 | 11 % | −15,1 % | −13,9 % | −133,5 | −1,335 | 19 % | −140,1 | −133,5 | −11,1 % | — | 6,0 |
| +0,5 s | t15 | 885 | 16 % | −11,5 % | −13,9 % | −101,9 | −1,019 | 25 % | −121,0 | −103,0 | −7,5 % | — | 15,0 |
| +0,5 s | t60 | 885 | 15 % | −11,2 % | −14,5 % | −98,7 | −0,987 | 32 % | −145,7 | −109,3 | −7,2 % | — | 60,0 |
| +0,5 s | tp_sell | 885 | 9 % | −15,1 % | −14,3 % | −133,6 | −1,336 | 18 % | −137,0 | −133,6 | −11,1 % | 26 % | 7,7 |
| +0,5 s | cb_sell | 885 | 13 % | −11,2 % | −14,5 % | −99,2 | −0,992 | 44 % | −149,4 | −112,9 | −7,2 % | 44 % | 41,0 |
| +0,5 s | arm | 885 | 7 % | −14,8 % | −13,9 % | −131,2 | −1,312 | 22 % | −134,6 | −131,2 | −10,8 % | — | 6,0 |
| +0,5 s | *peak60 (oráculo)* | 885 | 34 % | +29,2 % | −13,3 % | +258,2 | +2,582 | 21 % | +187,4 | −2,8 | +33,2 % | — | 2,3 |
| **+1 s** | t6 | 885 | 10 % | −15,2 % | −13,9 % | −134,4 | −1,344 | 20 % | −140,8 | −134,4 | −11,2 % | — | 6,0 |
| **+1 s** | t15 | 885 | 14 % | −11,9 % | −13,9 % | −105,7 | −1,057 | 21 % | −120,9 | −107,1 | −7,9 % | — | 15,0 |
| **+1 s** | t60 | 885 | 14 % | −12,0 % | −14,5 % | −106,5 | −1,065 | 30 % | −148,7 | −112,0 | −8,0 % | — | 60,0 |
| **+1 s** | tp_sell | 885 | 8 % | −15,5 % | −14,5 % | −137,1 | −1,371 | 18 % | −140,2 | −137,1 | −11,5 % | 27 % | 7,9 |
| **+1 s** | cb_sell | 885 | 13 % | −11,9 % | −14,5 % | −104,9 | −1,049 | 40 % | −147,5 | −113,4 | −7,9 % | 44 % | 43,2 |
| **+1 s** | **arm (T4.67a)** | 885 | 6 % | **−15,2 %** | −13,9 % | −134,8 | −1,348 | 25 % | −138,1 | −134,8 | −11,2 % | — | 6,0 |
| **+1 s** | *peak60 (oráculo)* | 885 | 32 % | +28,5 % | −13,5 % | +252,4 | +2,524 | 22 % | +181,5 | −2,9 | +32,5 % | — | 2,6 |
| +3 s | t6 | 885 | 9 % | −13,9 % | −13,9 % | −122,9 | −1,229 | 16 % | −126,7 | −122,9 | −9,9 % | — | 6,0 |
| +3 s | t15 | 885 | 14 % | −10,5 % | −13,9 % | −93,3 | −0,933 | 17 % | −104,8 | −94,0 | −6,5 % | — | 15,0 |
| +3 s | t60 | 885 | 13 % | −10,0 % | −14,1 % | −88,5 | −0,885 | 30 % | −131,9 | −89,9 | −6,0 % | — | 60,0 |
| +3 s | tp_sell | 885 | 9 % | −14,3 % | −14,1 % | −126,5 | −1,265 | 20 % | −130,6 | −126,5 | −10,3 % | 30 % | 13,9 |
| +3 s | cb_sell | 885 | 12 % | **−9,6 %** (melhor real) | −14,1 % | −85,2 | −0,852 | 43 % | −136,9 | −97,0 | −5,6 % | 50 % | 59,1 |
| +3 s | arm | 885 | 7 % | −13,9 % | −13,9 % | −123,4 | −1,234 | 20 % | −126,7 | −123,4 | −9,9 % | — | 6,0 |
| +3 s | *peak60 (oráculo)* | 885 | 31 % | +29,0 % | −13,6 % | +256,5 | +2,565 | 23 % | +179,3 | −3,4 | +33,0 % | — | 5,1 |

Leitura: o **MDD ≈ ΣR** em todas as células reais — a equity só desce. O top-3 tem 16–44 % do lucro bruto,
mas o lucro bruto (ex.: +72,8 em `t15`/+1 s, 124 vencedoras, a melhor +744 %) é menos da metade das perdas
(−178,5). A 0,1 SOL por ticket a prioridade pesa 0,4 % em vez de 4 %: o R médio fica ≈ "s/ prioridade"
− 0,4 pp, ainda −6 % a −12 %.

**Só com taxa (slippage 0, prioridade 0)** — o teste de "existe assimetria bruta?":

| entrada → saída | R médio | R mediano | hit |
|---|---|---|---|
| +0,5 s → t6 / t15 / t60 | −3,7 % / +0,1 % / +0,5 % | −2,5 % / −2,5 % / −3,1 % | 18 / 25 / 21 % |
| +1 s → t6 / t15 / t60 | −3,9 % / −0,4 % / −0,4 % | −2,5 % / −2,5 % / −3,1 % | 16 / 23 / 20 % |
| +3 s → t6 / t15 / t60 | −2,5 % / +1,2 % / +1,7 % | −2,5 % / −2,5 % / −2,7 % | 16 / 22 / 19 % |

O movimento bruto de +1 s a +6 s: **50,4 % das moedas ficam em ±1 %**, 13,8 % sobem > 5 %, 25,4 % caem
> 5 %; só **10,5 % sobem > 14 %** (o custo de ida e volta) — e 14,6 % até +15 s. Em algum trade dentro de
6 s / 15 s / 60 s, 17,5 % / 25,3 % / 32,7 % **tocam** +14 %: mesmo um trailing perfeito precisaria acertar
o pico em 1 de 3 moedas e não perder 14 % nas outras 2.

**Subconjuntos (entrada +1 s)** — nenhum vira positivo:

| subconjunto | n | t6 | tp_sell | arm |
|---|---|---|---|---|
| não nasce cheia | 867 | −15,2 % (hit 10 %) | −15,5 % | −15,3 % |
| nasce cheia (≥ 90 % em 2 s) | 18 | −13,9 % (0 %) | −13,9 % | −13,9 % |
| 1.º comprador terceiro ≤ 1 s ("já subindo") | 440 | −14,2 % (13 %) | −14,9 % | −15,0 % |
| ≥ 2 compradores terceiros até +1 s | 241 | −13,6 % (13 %) | −14,9 % | −15,0 % |
| preço em +1 s ≥ +10 % sobre o dev-buy | 188 | −16,6 % (21 %) | −15,3 % | −15,1 % |
| sem comprador terceiro em 60 s | 160 | −14,4 % (0 %) | −14,8 % | −14,3 % |
| dev-buy ≤ 2 SOL (filtro do braço T4.67a) | 817 | −15,1 % (10 %) | −15,7 % | −15,3 % |
| dev-buy ≤ 2 SOL e ≥ 1 comprador terceiro ≤ 1 s | 399 | −14,1 % (12 %) | −14,9 % | −15,0 % |

Por quartos de 15 min (t6, +1 s): −14,3 %, −15,8 %, −16,8 %, −13,8 % (hit 9–12 %) — estável na hora.

## 4. Anatomia do lançamento (885 moedas, 60 s)

| medida | valor |
|---|---|
| `create`/h | 1 072 (903/h em SOL; 15,8 % com quote ≠ SOL) |
| nasce cheia (progresso ≥ 90 % em 2 s) | **2,0 %** (18) — KB-0123 falava de 46 % **das graduações**; entre todos os `create` é raro |
| sem nenhum trade depois da tx do `create` (60 s) | 6,2 % (55); sem **comprador** de terceiros em 60 s: 18,1 % (160) |
| dev-buy na tx do `create` | 82,5 %; p50 0,10 SOL, p75 0,89, p90 1,98; > 2 SOL: 7,7 % |
| comprador de terceiros **no mesmo slot** do `create` (bundle) | 30,4 % dos lançamentos (média 1,02 carteiras) |
| compradores de terceiros em ≤ 0,5 s / ≤ 1 s / ≤ 3 s | ≥ 1: 28,6 % / 44,5 % / 58,8 %; ≥ 3: 13,6 % / 15,6 % / 22,7 % |
| `create` → 1.º comprador de terceiros | p10 0,00 s, p25 0,00 s, **p50 0,69 s**, p75 2,61 s, p90 10,6 s (n = 725; 49,7 % ≤ 1 s, 63,2 % ≤ 3 s) |
| `create` → pico de 60 s (moedas com pico > dev-buy) | p10 0,02 s, p25 0,83 s, **p50 9,3 s**, p75 29,9 s, p90 48,3 s (n = 685) |
| 1.º comprador de terceiros → pico | p25 0,0 s, p50 3,5 s, p75 21 s |
| pico/dev-buy − 1 em 60 s | p25 +0,1 %, **p50 +9,1 %**, p75 +49 %, p90 +188 %; ≥ +20 %: 40,3 % |
| dev-buy → preço em +1 s | mediana 0,0 %, média +11,2 %; ≥ +10 %: 21,2 % |
| quem dá o **primeiro sell** depois de +1 s (60 s) | comprador posterior 30,1 %, comprador ≤ 1 s 22,6 %, comprador do slot do `create` 15,8 %, criador 12,2 %, ninguém 19,3 % |
| oráculo "pico dentro de 6 s" (entrada +1 s) | R médio **−7,2 %**, mediana −13,9 %, hit 17 % |

O que isto diz: quando há pico, ele vem **em 0–3 s do primeiro comprador** (p25 = mesmo instante, ou seja,
mesmo bloco); em metade dos lançamentos ninguém chega em 1 s e o preço fica parado; nos que sobem, quem
vende primeiro é quem estava no bloco ou no primeiro segundo — o comprador de +1 s é a contraparte deles.

## 5. Sanity check do R58 (explosão de compradores) nesta captura

`run_grid.py live night_processed.jsonl 0 inf 0.03 2.0` (mesmo motor do R58, slippage venda 3 %, D = 2 s):
**54/54 células negativas**, R médio −6,6 % … −9,1 %, hit 23–29 %, ΣR sempre negativa, Σ − top-3 ainda
pior. Células de referência: 8/20/20 %/5 min −7,6 % (n 610, hit 26 %); 5/10/20 %/5 −8,1 % (838);
8/30/10 %/2 −8,4 % (1 003); 12/10/20 %/5 −6,6 % (361). Reproduz o R58 (−4,3 % … −9,1 %) em outro horário
e com uma hora inteira.

## 6. Ressalvas

- **Hora do dia**: 00:35–01:35 BRT (madrugada; 03:35 UTC), a hora mais fraca; 2 616 mints negociando e 1 914 trades/min
  contra ≈ 4 600 mints/h e 2 788 trades/min no R58 às 14:38 BRT (≈ 60 % do volume da tarde). O padrão (todas as células negativas, mediana = custo,
  estável nos quatro quartos) não depende do volume, mas a **cauda** (as +744 %) pode ser maior de tarde.
  A captura diurna 14:00–15:00 BRT foi agendada (dois processos desanexados; §1) e **não** entrou aqui.
- **`processed`**: pode entregar tx que nunca confirmam; a segunda conexão em `confirmed` viu exatamente
  os mesmos 1 072 `create` e 114 904 trades (72 a mais, efeito de borda), 0,18 s depois. Reorg não
  observado. Uma decisão real em `confirmed` (doutrina §8.2) custaria +0,18 s — indiferente aqui, porque o
  problema não é latência (0,5 s ≈ 1 s ≈ 3 s).
- **Cobertura do RPC público**: 0 `dropped`, 0 reconexões nas duas conexões; 6 `TradeEvent` com cauda
  desconhecida ignorados; a captura só vê o que o nó público entrega (sem `getTransaction`, sem inner
  instructions).
- **Relógio**: os deltas usam `received_at` (µs) da mesma conexão, não o `ts` do evento (1 s). Trades do
  mesmo slot chegam com 0–50 ms de diferença; um trade que chegasse antes do próprio `create` seria
  ignorado (não ocorreu). A ordem dentro do bloco é a ordem de entrega do nó.
- **Custos**: modelo do enunciado (1,25 %/perna, 5 %/3 % de slippage, 0,0002 SOL/tx); o papel do Lab usa
  1,75 %. A conclusão sobrevive a **zero** slippage e **zero** prioridade (só taxa: −3,9 % a +1,7 %).
- **Curvas com quote ≠ SOL** (15,8 %) excluídas por definição; **censura** de 18 `create` no fim.
- Sem impacto próprio; sem `getTransaction`; `creator` do `CreateEvent` (não `user`) define "criador".

## 7. Decisão (regra pré-registrada)

"Vira mesa só se R médio líquido > 0 com ≥ 300 moedas, top-3 < 50 % do lucro e o custo de prioridade
cabe. Se negativo a +1 s, o jogo do lançamento é dos bots colocados no bloco: descartar e registrar."
→ R médio a +1 s: **−11,9 % a −15,5 %** (n = 885 ≥ 300), negativo em todas as saídas, inclusive na regra
exata do braço `launch_v0/1` (−15,2 %); prioridade de 0,0004 SOL = 4 % do ticket, não cabe.
**Descartado e registrado** (KB-0141). O braço `launch_v0/1` semeado na T4.67a fica como está —
`MEME_LAUNCH_LANE=off` — e, se for ligado em papel, a previsão pré-registrada é **R médio ≈ −15 %,
hit ≈ 6–10 %** (controle negativo, não candidato).

## Fontes

- Diretório de trabalho (scratch da sessão, não versionado): `C:/Users/evert/AppData/Local/Temp/claude/C--Users-evert-AppData-Roaming-Claude-scratch-workspaces-6c08dfce-5e18-4922-a01b-bbd5beeca4f3-e9de050b-2d22-439a-99ef-da0860eadc92-scratch-2026-09-04-8b8550/9229a213-ae2c-4e9a-bca5-b3f02ae16415/scratchpad/r60/`:
  `capture60.py` (captura; `CreateEvent` = discriminador `1b72a94ddeeb6376`, decodificado
  name/symbol/uri/mint/curve/user/creator/ts/vtok/vsol/rtok/supply + payload bruto), `launch_bt.py`,
  `test_launch_bt.py`, `analyze.py`; dados `night_processed.jsonl` (71,7 MB), `night_confirmed.jsonl`,
  logs `night_*.log`; saídas `night_report.md`, `extras.md`, `burst_night_slip3_d2.md`,
  `night_processed.jsonl.grid.json`; captura diurna agendada → `day_*.jsonl` (17:00 UTC).
- R58 reutilizado: `scratch/r58/burst_bt.py`, `run_grid.py` (`.claude/state/notes-R58.md`).
- Testes: `uv run pytest scratchpad/r60/test_launch_bt.py -q` → `7 passed in 0.45s`.
- Nada foi lido nem escrito na VPS; nenhuma tx enviada; `.env*` não tocado.
