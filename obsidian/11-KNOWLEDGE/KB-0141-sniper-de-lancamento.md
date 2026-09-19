---
tags: [knowledge, meme, lancamento, sniper, evento, r60, m4]
tema: entrada no bloco da criação (pump.fun)
fonte: .claude/state/notes-R60.md (captura própria da cadeia, 19/09/2026)
fonte_url:
lido_em: 2026-09-19
evidencia: medição própria (captura program-wide de 60 min, RPC público) + back-test em papel com custos declarados
hipotese_testavel: sim (testada: EXP-M18, descartada)
astra: pendente
status: vivo
owner: sexta-feira
updated: 2026-09-19
confiança: "backtest do autor"
---

# KB-0141 — Sniper de lançamento não paga: comprar a ≤ 1 s do `create` é ser a contraparte do bloco (R60, 19/09/2026)

## O que afirma
Comprar uma moeda do pump.fun em +0,5 s, +1 s ou +3 s depois do `create` e vender em +6 s, +15 s, +60 s,
no primeiro sell de terceiro ou no primeiro sell de quem comprou no bloco da criação **perde em média em
todas as 18 células** (R líquido −9,6 % a −15,5 %, acerto 6–16 %, mediana −13,9 % = custo com preço
parado). Não é latência: +0,5 s ≈ +1 s ≈ +3 s. Não é custo: só com a taxa de 1,25 %/perna (slippage 0,
prioridade 0) o R médio fica em −3,9 % … +1,7 % — o lançamento típico **não se move** (50 % das moedas
ficam em ±1 % entre +1 s e +6 s) e o pico, quando existe, é feito no mesmo bloco ou nos 3 s seguintes ao
primeiro comprador, que é quem vende para quem chega depois.

## Onde foi mostrado
Captura própria de **60 min** (19/09 03:35–04:35 UTC = **00:35–01:35 BRT, madrugada, hora fraca**),
`logsSubscribe` no programa pump no RPC público, `processed` + `confirmed` em paralelo (mesmos 1 072
`create`; `confirmed` +0,18 s). 1 072 `create`/h (15,8 % com quote ≠ SOL, excluídos), 114 832 trades,
885 lançamentos em SOL avaliados, 0 quadros perdidos. Custos: 1,25 %/perna, slippage 5 % compra / 3 %
venda, prioridade 0,0002 SOL por tx, ticket 0,01 SOL (a prioridade sozinha = 4 % do ticket).

| entrada \ saída | t6 | t15 | t60 | 1.º sell terceiro | 1.º sell comprador do bloco | braço T4.67a | oráculo pico 60 s |
|---|---|---|---|---|---|---|---|
| +0,5 s | −15,1 % | −11,5 % | −11,2 % | −15,1 % | −11,2 % | −14,8 % | +29,2 % (hit 34 %, mediana −13,3 %) |
| +1 s | −15,2 % | −11,9 % | −12,0 % | −15,5 % | −11,9 % | −15,2 % | +28,5 % |
| +3 s | −13,9 % | −10,5 % | −10,0 % | −14,3 % | −9,6 % | −13,9 % | +29,0 % |

n = 885 por célula; ΣR a 0,01 SOL/ticket = −0,85 a −1,37 SOL por hora; MDD ≈ ΣR (só desce); top-3 = 16–44 %
de um lucro bruto menor que a metade das perdas. Oráculo "pico exato em 6 s": −7,2 %. Nenhum subconjunto
positivo: "já subindo em ≤ 1 s" −14,2 %, ≥ 2 compradores em 1 s −13,6 %, +10 % em 1 s −16,6 %, dev-buy
≤ 2 SOL −15,1 %, não nasce cheia −15,2 %. Estável nos quatro quartos de 15 min (−13,8 % a −16,8 %).

Anatomia: nasce cheia (≥ 90 % em 2 s) **2,0 %** dos `create`; sem trade depois do `create` 6,2 %; sem
comprador de terceiros em 60 s 18 %; comprador de terceiros **no slot do `create`** em 30 % (bundle); em
≤ 1 s em 45 %. `create` → 1.º comprador de terceiros p50 **0,69 s** (p25 0,00); `create` → pico p50 9,3 s
(p25 0,8 s); 1.º comprador → pico p50 3,5 s (p25 0,0 s). Pico/dev-buy p50 +9,1 %, p75 +49 %, p90 +188 %;
só 10,5 % sobem > 14 % (custo) até +6 s. Quem dá o primeiro sell depois de +1 s: comprador do primeiro
segundo ou do bloco em 38 %, criador 12 %, comprador posterior 30 %, ninguém 19 %.

## Como mediríamos aqui
Já medido com o feed de evento que o worker tem (`TradeEvent` + `CreateEvent` por `logsSubscribe`);
motor puro `launch_bt.py` com 7 testes sintéticos (trade futuro não altera entrada nem saída). Repetir
de tarde é só rodar `analyze.py` sobre a captura agendada (14:00–15:00 BRT, `day_*.jsonl`).

## Hipótese testável no Lab
EXP-M18 (descartada pela regra pré-registrada). O braço `launch_v0/1` semeado na T4.67a fica
`MEME_LAUNCH_LANE=off`; se ligado em papel, a previsão é **R médio ≈ −15 %, acerto 6–10 %** — controle
negativo, não candidato.

## O que muda na operação
- **Velocidade não compra o lançamento.** RPC regional (+0,5 s) não é melhor que a infra atual (+3 s);
  a vantagem do bloco pertence a quem está na tx do `create` ou no mesmo slot (bundle). Não investir em
  co-locação para este fim.
- **O `create` é evento de radar, não de entrada**: serve para começar a olhar a moeda e para vetar
  (bundle no slot da criação, dev-buy grande), nunca para comprar.
- Ticket de 0,01 SOL é inviável com prioridade: 0,0004 SOL = 4 % por ida e volta; qualquer regra de
  segundos precisa de ticket ≥ 0,1 SOL só para diluir a prioridade — e mesmo assim fica −6 % a −12 %.
- Toda regra de "vender no pico rápido" depende de saber o futuro: o oráculo de 60 s ganha +29 % com 32 %
  de acerto; a regra real mais próxima (−20 % do pico, 6 s) dá −15 %.
- Reforça KB-0138: a explosão de compradores também deu 54/54 células negativas nesta captura.

## Por que pode falhar
- Hora fraca (madrugada BRT; ≈ 60 % do volume da tarde) — a cauda pode ser mais gorda às 14–20 BRT;
  o padrão (mediana = custo, todas negativas) não depende do volume. Captura diurna agendada.
- `processed` do RPC público (sem reorg observado; `confirmed` idêntico); só o que o nó público entrega.
- Relógio = `received_at` local (µs), não o `ts` do evento (1 s); ordem dentro do bloco = ordem de entrega.
- Custos do enunciado (o Lab usa 1,75 %/perna); impacto próprio não modelado; curvas com quote ≠ SOL fora.

## Segunda opinião (Astra)
Pendente.

## Relacionados
[[EXP-M18-sniper-de-lancamento]] · [[KB-0138-explosao-de-compradores-nao-tem-vantagem]] ·
[[KB-0123-graduacoes-born-full]] · [[KB-0136-carteiras-vencedoras-nao-sao-gatilho]] ·
[[KB-0134-websocket-do-rpc-lag-medido-ao-vivo]] · [[Strategy Backlog]] · `.claude/state/notes-R60.md`
