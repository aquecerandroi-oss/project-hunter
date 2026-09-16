---
tags: [experimento, meme, pumpfun, paper, pre-registro, evento, identidade-social, m4]
updated: 2026-09-16
status: pre-registrado
owner: sexta-feira
exp: EXP-M8
strategy: "meme/pumpfun — evento que pode dar bum: só compra moeda ligada a um evento confirmed (figura pública, exchange ou marca), E2, dev ≤ 10 %, sniper ≤ 25 (largo de propósito), sem piso de fluxo, moonshot 10×/trailing 50 %/2 h/segura migração"
version: "gate evento_pode_dar_bum v1 + exit moonshot_10x_trailing_50_apos_3x_2h_segura_migracao v1 (event_v0/1, migração 0041_meme_social, relógio de minuto)"
result: nao-iniciado
evaluable: 0
days: 0
last_eval: ""
---

# EXP-M8 — a identidade social e o evento que pode dar bum

> **Pré-registro escrito na T4.26 em 16/09/2026, ANTES de existir uma proposta do conjunto.** Protocolo
> congelado; avaliações acrescentadas pelo fechamento diário, nunca reescritas. A previsão padrão é
> `descartar` — o mesmo veredito de EXP-M6/EXP-M7 até prova em contrário.

## Diretiva de origem

Everton (16/09/2026 01:1x BRT): "análise sempre acima de gráfico, acima de tendências; mas as meme coins
você vai mais por notícia — assim que uma moeda pode dar bum, que nem a do Trump". **O caso de
referência:** $TRUMP (17/01/2025) — anúncio na conta oficial de uma figura pública, moeda na Solana,
US$ 0 a bilhões em horas. O que decidiu não foi gráfico nem fluxo: foi **quem anunciou, onde, e quão
verificável**. O funil de EXP-M1–M7 lê curva, flow, holders, snipers, dev, pedigree e a vigilância do
criador — e descartava a identidade social que o próprio pump.fun já entrega por moeda (`twitter`,
`website`, `telegram`, `description`, `metadata_uri`; o indexador dá `twitterReuseCount`). O plantão já
tinha medido (M-P17) que um `twitter` apontando para um **post** ≤ 10 min antes da criação se associa às
células lentas, e (M-P33) que clones reutilizam o mesmo handle. A `0041_meme_social` fecha essa lacuna:
onze colunas em `meme_tokens` (nove escritas uma vez, duas mutáveis — o contador de reuso) e a tabela
nova `meme_events`, que guarda o anúncio **antes** de a moeda existir.

## Hipótese (congelada)

**H1:** uma moeda **ligada a um evento `confirmed`** de figura pública, exchange ou marca — o casamento
feito pelo job de minuto contra `meme_tokens.twitter`/`symbol` nos 60 min seguintes ao evento — tem
expectância **positiva** mesmo com um portão largo (sniper ≤ 25, sem piso de fluxo), porque o próprio
anúncio é o mecanismo causal, não a curva. **H0 (previsão):** eventos confirmados e verificáveis por
figura pública são raros demais para 100 apostas em 30 dias, e a maioria do "bum" nas meme coins continua
sendo orgânico/bot, não de notícia; o resultado fica indistinguível de zero ou pior → `descartar`.

## Definição congelada (`event_v0/1`)

| critério | limiar | recusa |
|---|---|---|
| evento | matched a `meme_events` `confirmed`, `kind` ∈ {`public_figure_launch`, `exchange_listing`, `brand_launch`} | `no_event` |
| pedigree | E2 (criador em série, clone) | `creator_serial` / `symbol_clone` |
| dev | ≤ 10 %, desconhecido recusa | `dev_share_above_max` / `dev_share_unknown` |
| sniper | ≤ 25 (largo de propósito — o bum atrai sniper, não é o que desqualifica aqui) | `snipers_above_max` / `snipers_unknown` |
| criador | não vendedor líquido, desconhecido recusa | `creator_is_net_seller` / `creator_net_seller_unknown` |
| fluxo | **sem piso** (`require_positive_flow = false`) — o fluxo vem depois do anúncio, não antes | — |
| participação | ≤ 20 % do volume do minuto (número desta revisão, não do brief — a checagem de participação do gate é incondicional; ver nota abaixo) | `participation_above_cap` |
| janela de idade | 0–3 600 s (o evento pode ter sido casado a uma moeda recém-criada ou já com alguns minutos) | `age_above_max` |

Saídas moonshot: alvo **10×**, trailing **50 %** armado só após **3×**, `max_hold_s` 7 200 (2 h),
`creator_dump`, piso 50 %; **`exit_on_migration = false`** — a posição atravessa a migração (EXP-M4's
shape). Tamanho 0,05 SOL; 5 abertas (o teto do `operator`, o conjunto aqui é `research_only`). Placar só
com desfechos `measured`.

**Nota de engenharia (não no brief):** a checagem de participação do gate (`rules._participation_refusals`)
é incondicional para todo conjunto — um evento recém-casado pode não ter fita de trades ainda
(`curve_volume_1m_unknown`), o que refusaria toda proposta antes mesmo de chegar ao portão de evento. Não
alterei a função congelada `evaluate_entry` para este experimento; a exclusão da EXP-M8 é medida como
está, e uma proposta que morre em `curve_volume_1m_unknown` conta nas recusas do fechamento diário —
diagnóstico, não escondido.

## Portão de desenho (C1–C8) — congelado

| # | Critério | Veredito | Justificativa |
|---|---|---|---|
| C1 | Plausibilidade | **PASS** | O mecanismo é o mais direto do funil inteiro: quem anuncia, com que alcance, decide o preço antes de qualquer curva existir — o caso $TRUMP é o exemplo canônico |
| C2 | Sobreajuste | **REVISE** | Poucos limiares (sniper 25, dev 10 %, participação 20 %), mas o portão de evento em si é binário (confirmed + kind); o risco real é amostral, não de limiar |
| C3 | Amostra | **REJECT-em-potencial, medir primeiro** | Eventos `confirmed` de figura pública são raros — a régua de 100 apostas/30 dias pode nunca fechar; o adendo do plantão (camada 3) faz o post-mortem de quantos eventos por semana viram moeda rastreada |
| C4 | Regime | **REVISE** | Um mercado em alta gera mais anúncios promocionais; a fração de eventos "reais" (figura pública genuína) contra "pump coordenado disfarçado de evento" muda com o ciclo |
| C5 | Saídas | **PASS** | Alvo, trailing tardio, tempo, dump e piso — todas as saídas do funil-padrão, moonshot como EXP-M4 |
| C6 | Concentração | **PASS** | 0,05 SOL, ≤ 5 abertas, ≤ 20 % do volume do minuto |
| C7 | Execução | **REVISE** | O casamento evento↔moeda roda a cada minuto (não em tempo real); um evento verdadeiramente instantâneo pode perder os primeiros minutos do bum — a latência de casamento é medida |
| C8 | Invalidação | **PASS** | A régua: ≥ 100 apostas e 30 dias, IC 95 % por blocos de dia; abaixo disso, `descartar` por amostra insuficiente, não por resultado |

**Veredito do portão:** `REVISE` — C3 e C7 pedem medição antes de qualquer promoção; o experimento roda
porque o custo de tê-lo ligado é zero (research_only, 0,05 SOL) e a amostra é o próprio objeto de estudo.

## Casamento evento ↔ moeda (o que o job faz)

Um job por minuto (`hunter_meme_worker.events.events_match_once`) liga eventos sem `mint`
(`meme_events.mint IS NULL`, observados nos últimos 65 min) a `meme_tokens` criados nos 60 min
**seguintes** ao evento, por `handle_hint` (contra `twitter`, `ILIKE`) ou `symbol_hint` (contra `symbol`,
igualdade); o mais antigo criado dentro da janela vence quando várias moedas compartilham o link
(M-P33 — os "irmãos"). A consulta é bounded nos dois lados: o índice parcial `ix_meme_events_unmatched`
(a tabela é minúscula) e `ix_meme_tokens_created_at` (o índice que já existia) — plano em
`.claude/state/notes-T4.26.md`, medido a 150 007 linhas em `meme_tokens`. Cada evento casado também liga
qualquer proposta aberta para o mesmo mint (`meme_proposals.event_id`).

## Previsões (congeladas)

- **P1** menos de 1 evento `confirmed` por dia em média nos primeiros 14 dias (a raridade é o próprio C3).
- **P2** a maioria dos eventos registrados pelo plantão nunca casa com uma moeda em 60 min (o anúncio não
  vira lançamento, ou o handle declarado não bate com o `twitter` do coin).
- **P3** ≤ 3 propostas do conjunto nos primeiros 14 dias.
- **P4** R médio indistinguível de zero por amostra insuficiente nos primeiros 30 dias → `inconclusivo`,
  não `confirmar`.
- **P5** quando houver ≥ 10 apostas fechadas, a maior causa de saída será `creator_dump` ou `max_loss`
  (o bum atrai o próprio criador a vender), não o alvo de 10×.

## O que NÃO fazer

Prometer detecção de "próximo $TRUMP" — isto é pesquisa sobre uma cauda rara, não um produto. Ligar
dinheiro real antes da régua. Ajustar o portão de evento (quais `kind`/`confidence` contam) olhando os
primeiros casos (KB-0092). Tratar `reported`/`rumor` como `confirmed` para aumentar a amostra.

## Addendum — 16/09/2026 (T4.26b, KB-0100)

A medição de hoje ([[11-KNOWLEDGE/KB-0100-evento-move-moeda-primeira-medida-16-09]]) achou o buraco
estrutural na seção "Casamento evento ↔ moeda" acima: a janela "para frente, 60 min" só existe se o
evento for registrado **antes** da moeda nascer, e o plantão registra **depois** do fato (latência
mediana medida hoje: 172,8 min). Dos 8 eventos do dia, ARC tinha 60 moedas candidatas pela própria regra
do job e casou zero; o único casamento real ligou um evento de "aviso" (clones "fundo/instituição") a
um clone novo, sem nada impedir esse casamento de virar sinal de compra.

Correção (não muda P1–P5 acima, que continuam congeladas): o job agora varre 72 h para trás
(`MEME_EVENT_MATCH_WINDOW_H`) com 30 min de folga retroativa por moeda (`MEME_EVENT_MATCH_GRACE_MIN`),
casamento passa a ser **um-para-muitos** (`meme_event_matches`, não mais o `mint` único de `meme_events`),
e um evento com `notes->>'action' = 'avoid'` marca toda moeda que nomeia como `avoid` — o portão de
evento recusa `event_avoid` incondicionalmente, mesmo que o `kind`/`confidence` do evento passassem.
Backfill dos 8 eventos de hoje: `infra/scripts/meme_event.py rematch --hours 72 --apply` depois do
deploy. Detalhe completo: `docs/DATABASE.md` §52.3, `.claude/state/notes-T4.26b.md`.

## Avaliação
_(append-only; o fechamento diário acrescenta uma seção datada por dia com aposta fechada)_

## Fontes

`infra/migrations/versions/0041_meme_social.py`, `infra/migrations/ddl/{meme_social,meme_social_checks,meme_events}.py` ·
`packages/core/hunter_core/db/models/{meme,meme_events,meme_social_checks}.py` ·
`packages/exchange-adapters/hunter_exchanges/pumpfun/{social,normalize,models,board_models,indexer_rest}.py` ·
`packages/indicators/hunter_indicators/meme/{identity,event_gate,event_match}.py` ·
`services/meme-worker/hunter_meme_worker/{events,events_repo,events_config,proposals,proposals_identity,proposals_reasons,proposals_row,lab_models,lab_repo,lab_repo_fast}.py` ·
`infra/scripts/{meme_event,meme_event_rematch}.py` ·
`infra/migrations/versions/0043_meme_events_scan_cursor.py`,
`infra/migrations/ddl/meme_event_matches.py` ·
`docs/DATABASE.md` §52 · `docs/RISK_ENGINE_MEME.md` §4 · `docs/PUMPFUN.md` §1.3/§3.1 ·
[[00-INBOX/Hipoteses-do-plantao|M-P17, M-P33]] ·
[[11-KNOWLEDGE/KB-0100-evento-move-moeda-primeira-medida-16-09]] ·
`.claude/state/notes-T4.26.md`, `.claude/state/notes-T4.26b.md`.
