---
tags: [knowledge, nota, meme, pumpfun, sizing, executor, risco, t4-61b, t4-61c, m4]
tema: memecoin / pump.fun / o tamanho da compra real como fração do teto decidida pela evidência da admissão (escada de convicção) e a recusa "entrada depois da queda"
fonte: docs/RISK_ENGINE_MEME.md §4 (check 26), §5, §17; packages/risk-core/hunter_risk_meme/conviction.py; services/meme-executor/hunter_meme_executor/conviction.py; KB-0118, KB-0108, KB-0103, EXP-M10; .claude/state/notes-R54.md, notes-R56.md, review-T4.61b.md
fonte_url: https://github.com/aquecerandroi-oss/project-hunter/blob/main/docs/RISK_ENGINE_MEME.md
lido_em: 2026-09-18
evidencia: síntese de medições próprias já publicadas (KB-0118 backtest 613 entradas / 5 dias; EXP-M10; R54 e R56 sobre 12 compras reais) — a escada em si ainda não foi medida em produção; revisão de risco T4.61b (5 achados) fechada na T4.61c
hipotese_testavel: sim
astra: pendente
status: vivo
owner: sexta-feira
updated: 2026-09-18
revisado: 2026-09-18 (T4.61c)
confiança: "?"
tipo: pesquisa
hipotese: —
variavel: —
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: —
classe_de_perda: —
mercado: meme
---

# KB-0137 — Tamanho por convicção: a compra real como fração do teto, e a queda que recusa

**Pergunta (Everton, 18/09/2026 15:0x BRT).** "Usa a inteligência que já adquirimos e opera agora com o
dinheiro que temos; pode variar os valores da entrada." Até hoje toda compra real era
`min(MEME_MAX_SOL_PER_TRADE, size_sol)` — **0,28 SOL fixos**, o mesmo para a moeda limpa e para a
moeda que só a fita atrasada vouchou.

## O que afirma

O tamanho de uma compra na curva deve ser uma **fração do teto** decidida pela evidência que a admissão
já tem no instante da decisão, e nunca um número acima dele. Cinco degraus, cada um com a sua medição;
o produto começa em 1,0 e **só desce**; abaixo de 0,25 não se compra (`conviction_too_low`); abaixo
de `MEME_MIN_TRADE_SOL` (0,02 SOL) não se manda pó (`conviction_too_small`); a queda ≥ 50 % do SOL
real contra o pico dos últimos 60 s **recusa** (`entry_after_drop`) em vez de descontar — é o único
degrau com vantagem limpa e a evidência sustenta "não entrar", não "entrar menor"; e a queda que
**não dá para ver** (menos de duas fotos na janela, leitura falha) também recusa
(`entry_after_drop_unknown`, T4.61c) — uma foto só, tirada depois da queda, lia "não caiu".

A escada é **insumo do motor de risco** (T4.61c): check 26 `conviction` e teto `conviction` na
§5. Uma compra descontada tem `binding_constraint = conviction` (não `requested`), e uma recusa da
escada é `approved = false` com `first_refusal` — a mesa e os R-studies leem como qualquer outra
recusa.

| degrau | evidência | × | de onde vem |
|---|---|---|---|
| criador | lido na cadeia (`chain_ata_vs_initial`) | 1,0 | T4.45/T4.56: a ATA contra a compra registrada do dev |
| | só a fita, ninguém, memória de venda | 0,5 | COVER: a fita chegou 37,7 s atrasada (R56 §3.2) |
| compradores | `unique_buyers_60s ≥ 25` | 1,0 | [[05-EXPERIMENTS/EXP-M10-compradores-25\|EXP-M10]]: +0,09 R acima de 25 |
| | < 25 ou sem linha (≤ 120 s) | 0,5 | |
| holders | `holders_rising = true` | 1,0 | [[11-KNOWLEDGE/KB-0108-anatomia-da-morte-depois-da-porta\|KB-0108]]: 49 → 17 holders no minuto da morte |
| | falso ou sem leitura | 0,5 | |
| concentração | `bundled ≤ 10 %` e `top10 ≤ 20 %` | 1,0 | metade dos tetos dos checks 11/12; [[11-KNOWLEDGE/KB-0103-clones-fundo-com-preco-forjado-assinatura-e-custo\|KB-0103]]: o maior comprador paga 25 % nas forjadas × 5 % nas orgânicas |
| | acima de um, ou sem leitura | 0,5 | |
| queda | `recent_drawdown_pct` v1 (EXP-M13) sobre as fotos de `meme_curve_snapshots` em 60 s + o `real_sol` da leitura desta admissão: < 50 % | 1,0 | [[11-KNOWLEDGE/KB-0118-nao-entrar-depois-da-queda\|KB-0118]] |
| | ≥ 50 % | **recusa** | KB-0118 §1: −0,305 R em 73 apostas, cauda 4,1 %, negativa nos 5 dias |
| | menos de duas fotos na janela, ou leitura falha | **recusa** (`entry_after_drop_unknown`) | T4.61c: a borda única falha fechada, como a porta do Lab (`recent_drawdown_unknown`) |

## Onde foi mostrado

- **A queda fresca é a única célula clara.** KB-0118 (613 entradas da porta, 12–16/09, 5 dias): `dd > 50 %`
  com pico ≤ 60 s dá −0,305 R; a mesma queda já parada (60–180 s) dá +0,566 R (n = 17). `N = 60 s` manda
  mais que `X` — alargar a janela corta as moedas que já caíram e se estabilizaram. Por isso a janela é
  60 s e a PS (R56 §2, +0,66 R real, vinha de 67 % a −60 s e **voltou a subir**) passa.
- **Em dinheiro real, era o desenho dominante.** R56 §1: **6 das 7** compras do estágio 1b tinham perdido
  ≥ 50 % do SOL real nos 90 s anteriores ao fill (soly −94 %, COVER −97 %, Punch −97 %); R54: 4 das 5 do
  estágio 1 compraram logo depois de uma queda de progresso. O check 9 (`curve_progress`) só olha a janela
  2–50 % no instante — aprovou todas.
- **O criador pela fita é a fonte atrasada.** R56 §3.2: COVER foi recusada pela cadeia às 19:46:56 e
  comprada 23 s depois porque a fita dizia `false`. Desde a T4.56 a cadeia vence; o degrau desconta o
  caso em que **só** a fita falou.
- **Compradores ≥ 25**: EXP-M10, +0,09 R. **Holders caindo**: KB-0108 §2, mediana 49 → 17 no minuto
  antes da morte contra 20 → 30 nas sobreviventes.

## Como mediríamos aqui

Toda ordem real **com a flag ligada** grava `admission.conviction` (cada degrau com `value`,
`multiplier`, `reason`; `multiplier` total, `sol_cap`, `sol_sized`, `refusal`, `read_failed`) e o
motor grava o check 26 e o teto `conviction` em `sizing.caps`. Desligada, desde a T4.61c, **nada é
lido** (`{enabled: false, evaluated: false}`) — a sombra da T4.61b custava uma consulta por candidata
e podia derrubar o loop de entradas (e o de saídas junto) numa partição travada; medir agora exige
ligar. Consulta: `meme_live_orders.admission -> 'conviction'` × `meme_live_positions.pnl_sol` por
`entry_order_id`, e `admission -> 'checks'` filtrando `name = 'conviction'`. Perguntas: (i) o R médio
por faixa de `multiplier`; (ii) quantas compras `entry_after_drop` recusou e o destino das moedas em
`meme_curve_snapshots` (+10/+30 min, como no R56 q9); (iii) quantas `entry_after_drop_unknown` — se
for a maioria, o radar não está fotografando a tempo e o problema é de cobertura, não de escada;
(iv) quantas `conviction_too_low`/`conviction_too_small` e o R que teriam tido. Com ~7 compras/dia,
uma semana dá 40–50 pontos — o suficiente para o sinal da queda (grande), não para os quatro
descontos (pequenos).

## Hipótese testável no Lab

`MEME_CONVICTION_SIZING=on` contra a semana anterior desligada: **R total por SOL arriscado** sobe
(a mesma porta, tamanhos diferentes) e a cauda de −0,9 R (ruína) concentra-se nas ordens que a escada
recusou (destino das moedas em `meme_curve_snapshots`). Refutação: R por SOL igual ou pior com a
escada ligada em ≥ 40 compras, ou a coorte `entry_after_drop` com moedas que subiram depois.

## Por que pode falhar

- **Os quatro descontos são pequenos e podem se anular.** KB-0118 é explícita: o filtro leva a porta de
  −0,022 a +0,016 R por aposta — de perdedora a empatada. Não é vantagem nova.
- **Desconhecido desconta** — e a linha de 15 s só existe para mints que a via rápida fotografou.
  Uma moeda boa sem série paga 0,5 × 0,5 (compradores + holders) = 0,25 e entra no piso — e, se
  também não tem duas fotos de curva em 60 s, é **recusada** (`entry_after_drop_unknown`). Se isso
  dominar, a escada vira um filtro de cobertura do radar; a pergunta (iii) acima mede.
- **Seleção**: KB-0118 mediu nove variantes na amostra que as escolhe (KB-0092). O que sustenta X = 50 %
  / N = 60 s é a coorte cortada ser negativa nos 5 dias, não o Δ.
- **A janela de 60 s perde a TAXCOIN** (pico a 67 s, KB-0118 §3) — por 7 s. Alargar para 120 s pega a
  TAXCOIN e corta a PPC (1,78×). A escolha foi a cirúrgica.
- **A escada não vê o que o motor já recusa** (criador vendedor, bundle acima do teto): nesses casos o
  check 26 fica gravado ao lado dos outros, e `first_refusal` é o do motor.
- **O piso de 0,02 SOL também age com a flag desligada** (é o `min_trade_sol` do perfil live): um teto
  de participação ou um restante de escopo entre 0,001 e 0,02 SOL passa a recusar em vez de mandar
  pó. É decisão de capital do Everton (`MEME_MIN_TRADE_SOL`), não nossa.

## Segunda opinião (Astra)

Pendente. A pergunta original ("`peak_unknown` deveria ser recusa?") foi respondida pela revisão de
risco (`review-T4.61b.md`, A2/A3) e fechada na T4.61c: **recusa**, porque uma foto pós-queda lia
"não caiu" e porque um mint que a via rápida largou no último minuto é sinal. Pergunta nova para
ela: com o piso de 0,02 SOL, duas evidências fracas dão 0,07 SOL (passa) e três recusam — o piso de
0,25 do produto ainda faz sentido, ou o `conviction_too_small` já faz o trabalho?

## Relacionados

[[11-KNOWLEDGE/KB-0118-nao-entrar-depois-da-queda|KB-0118]] · [[11-KNOWLEDGE/KB-0108-anatomia-da-morte-depois-da-porta|KB-0108]] ·
[[11-KNOWLEDGE/KB-0103-clones-fundo-com-preco-forjado-assinatura-e-custo|KB-0103]] ·
[[05-EXPERIMENTS/EXP-M10-compradores-25|EXP-M10]] · [[05-EXPERIMENTS/EXP-M13-sem-entrar-apos-queda|EXP-M13]] ·
[[11-KNOWLEDGE/KB-0135-a-vantagem-nao-esta-na-saida|KB-0135]] · `docs/RISK_ENGINE_MEME.md` §4 (26), §5, §17 ·
`docs/ACTIVATION.md` 9f · `.claude/state/notes-T4.61b.md` (T4.61b e T4.61c) · `.claude/state/review-T4.61b.md`
