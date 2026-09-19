---
tags: [knowledge, meme, kol, call, evento, identidade, r61, m4]
tema: o sinal de influenciador/call que já gravamos antecipa ou confirma o bum (pump.fun)
fonte: .claude/state/notes-R61.md (medição própria no banco da VPS, 72 h, 19/09/2026)
fonte_url:
lido_em: 2026-09-19
evidencia: medição própria (boards do site por minuto + fotos da curva a ~13 s + meme_tokens) com replay em papel de custos declarados e controle casado por idade/mcap
hipotese_testavel: sim (EXP-M20, condicionada a ler o KOL no patch de 1 s)
astra: pendente
status: vivo
owner: sexta-feira
updated: 2026-09-19
confiança: "backtest do autor"
---

# KB-0142 — KOL e "call" confirmam, não antecipam: o crachá KOL chega com o pico e o casamento de notícia marca clones (R61, 19/09/2026)

## O que afirma
Dos três sinais de "gente chamando" que **já gravamos**, nenhum antecede o bum com R positivo: (1) o `kol_count` dos boards
(carteiras da lista KOL do site que negociaram a moeda) aparece **no mesmo minuto do pico** — pico anterior ou igual ao
sinal em 59 % das moedas, bum (+50 %/60 s) em só 37 % e, quando existe, começando 16 s (mediana) depois do que vemos, com
±55 s de incerteza nossa; comprar 20 s depois dá **R −0,071, acerto 15 % (n 3 486)**, negativo em toda célula executável.
(2) `meme_event_matches` (notícia → moeda) casa **clones de nome criados 19 h depois** do evento: R −0,090, acerto 5 %,
igual ao controle sem sinal. (3) Identidade social no nascimento (perfil no X, X + Telegram, website) multiplica por 3–5 a
chance de **graduar** mas não muda o timing e **sobe** a taxa de pump-and-dump nos 5 primeiros minutos (9,4 % vs 4,8 %).
O KOL ≥ 1 no bloco de criação (33 767 moedas em 72 h, 64 % das sem rede social) é marcador de bot, não de call.

## Onde foi mostrado
Banco da VPS, 16/09 04:55 → 19/09 04:55 UTC. `meme_board_observations` (`new` 114 k mints, `movers` 15,6 k,
`graduating` 5 k, `graduated` 2,8 k; uma linha por mint/board/minuto), `meme_curve_snapshots` (2,25 M fotos, ~13 s entre
2 e 5 min de idade, quase nada depois de 10 min salvo moeda fixada), `meme_tokens` (96 236 criações; X em 48 %, Telegram em
1,6 %). Primeiro incremento de `kol_count` por mint: 4 531 analisadas (3 423 de 0→≥1). Custos do enunciado: 1,25 %/perna,
3 % slippage/lado, trailing 20 % ou 5 min. Controle: moeda sem KOL na vida, mesma idade ±90 s e mcap ±25 % (2 103 pares).

| célula | n | pico ≤ sinal | bum > 30 s depois (dos bums) | r5 p50 | R papel | acerto |
|---|---|---|---|---|---|---|
| todas | 3 486 | 59 % | 40 % | 0,94 | **−0,071** | 15 % |
| controle sem KOL | 1 982 | 69 % | 22 % | 0,95 | −0,114 | 5 % |
| idade < 2 min | 3 082 | 61 % | 51 % | 0,93 | −0,075 | 12 % |
| idade 2–5 min | 322 | 46 % | 8 % (87 % dos bums já começaram) | 1,25 | −0,019 [IC −0,07, +0,04] | 30 % |
| idade 5–30 min | 75 | 47 % | 3 % | 1,17 | −0,094 | 35 % |
| k → k+1 (k ≥ 1) | 816 | 50 % | 30 % | 0,73 | −0,116 | 18 % |
| holders ≥ 100 no sinal | 354 | 33 % | 24 % | 0,87 | −0,062 | 25 % (graduou 66 %) |

Boards a 1 min: em 1 h metade das moedas com KOL vale menos da metade do mcap do sinal (r60 p50 0,46). A moeda com KOL é
mais viva nos dois sentidos (rmax ≥ 2× em 16 % vs 3 %; r5 ≤ 0,5× em 25 % vs 16 %), mas a mediana anda de lado ou cai.

Identidade (87 593 criações com leitura social): graduação 9,85 % com X = perfil vs 2,12 % com X = post vs 2,61 % sem
nada; X + Telegram 11,19 %; website 5,65 % vs 2,13 %. Pico ≥ 60 SOL nos 30 min: 11–15 % em todos os grupos.
`twitter_reuse_count` só existe para moeda com aposta/board `graduating` (2 085, todas 0) — inutilizável.

## Como mediríamos aqui
Já medido (`.claude/state/r61/analyze2.py`, séries de fotos em SOL e boards em USD **separadas**, sem misturar unidades;
`analyze_events.py`, `strat.py`, `ci.py`). Os dois limites de latência: `R_mid` (entrada no meio do intervalo de incerteza,
proxy de ler o patch a 1 s) e `R_opt` (`t_prev` + 20 s, **contaminado por look-ahead**, só teto). Entre 2 e 30 min de
idade `R_mid` = **+0,081 [+0,011, +0,163], acerto 38 %, n 445**, sem os 3 maiores +0,037; por dia +0,20 / +0,05 / +0,04 /
−0,03. Abaixo de 2 min os três limites são negativos — latência não compra o bloco (KB-0141).

## Hipótese testável no Lab
EXP-M20 (pré-registro): `kol_v0/1` `research_only`, gatilho = incremento de `kol` lido **no patch de 1 s** dos boards
(T4.68a: `boards.py::ingest` já recebe; hoje só o último do minuto vai ao banco), idade 120–1 800 s, mcap ≥ 0,95 do pico
anterior, holders ≥ 30; saídas trailing 20 % / 300 s; controle `flow_v2/6` no mesmo minuto. Previsão honesta:
**inconclusivo → descartar** (cauda concentrada, um dia em quatro negativo). Sem a leitura a 1 s a EXP não é mensurável.

## O que muda na operação
- **"Começando a bombar" não é o que os boards mostram**: o crachá KOL e o bum chegam juntos; quem entra 20 s depois
  compra o pico de quem chamou. O radar deve tratar `kol_count` como **confirmação/contexto** (KB-0136: carteira vencedora
  não é gatilho), nunca como entrada.
- **Casamento de evento por ticker/keyword marca clone** (o evento `PAID` casou 1 252 moedas; 19 h de atraso mediano).
  Manter como `avoid`/aviso; para a EXP-M8 o casamento precisa de CA ou de janela de minutos, não de 72 h.
- **Identidade é seleção lenta**, não timing: perfil no X e Telegram multiplicam a graduação por 3–5 e já estão em
  `IdentityFeatures`; mas o X também é a ferramenta do call que vende (pump-and-dump 9,4 % vs 4,8 %).
- **Feed de canais de call (T4.68)** só faz sentido com `posted_at` da plataforma + `received_at` nosso (p50 ≤ 3 s),
  `author_handle` + seguidores, **CA** (não ticker), `is_first_mention`, e histórico de acerto por autor calculado por nós;
  3 dias de coleta sem apostar medindo pico − `posted_at` antes de qualquer braço. Spec completa na nota R61 §7.

## Por que pode falhar
- O sinal é gravado por minuto: o KOL negociou em `[t_prev, t_kol]` (p50 55 s); "pico no mesmo minuto" pode ser 30 s antes
  ou depois do trade real. A leitura a 1 s (T4.68a) é o que decide se a porta de 2–30 min existe.
- Série fina só até 5 min de idade (depois só moeda fixada): as células de 5–30 min têm n 75–104 na série de 15 s.
- 36 % das apostas de papel fecham censuradas (série acabou antes de 5 min); custos do enunciado, sem prioridade/impacto.
- 72 h de uma semana sem bull de memes; controle casado em idade/mcap, não em holders/fluxo.
- "KOL" é a lista do site (inclui bots de lançamento); um feed de callers humanos pode se comportar diferente — é exatamente
  o que o T4.68 teria de medir antes de apostar.

## Segunda opinião (Astra)
Pendente.

## Relacionados
[[EXP-M20-sinal-de-call]] · [[KB-0141-sniper-de-lancamento]] · [[KB-0138-explosao-de-compradores-nao-tem-vantagem]] ·
[[KB-0136-carteiras-vencedoras-nao-sao-gatilho]] · [[KB-0100-evento-move-moeda-primeira-medida-16-09]] · [[EXP-M8-evento-que-pode-dar-bum]] ·
[[EXP-M19-subida-com-gente-atras]] · [[Strategy Backlog]] · `.claude/state/notes-R61.md`
