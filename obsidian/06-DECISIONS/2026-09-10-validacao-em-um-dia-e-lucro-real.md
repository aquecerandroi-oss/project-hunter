---
tags: [decisao, processo, lucro-real, latencia, m3]
titulo: Três regras do dia — um candidato validado por dia, tudo instantâneo (SLO por trecho), lucro real sempre em USDT e BRL
data: 2026-09-10
updated: 2026-09-10
owner: sexta-feira
origem: instruções do Everton ao longo do turno de 2026-09-10 (09:00–15:30 BRT), registradas nas
  tarefas que as executaram
status: registro
decided_on: 2026-09-10
by: everton
---

# Três regras do dia — validação em um dia e lucro real

**Registrado por:** Sexta-feira (Hermes), plantão de arquivamento da tarde de 2026-09-10.
**Não é uma nota nova de opinião** — é a consolidação de três instruções do Everton que já
apareceram, cada uma, no brief ou nas notas da tarefa que as implementou. Nenhum número aqui foi
recalculado por mim; cada um está referenciado na tarefa de origem.

## 1. Um candidato validado por dia — e quem dá ruim morre no mesmo dia

**A instrução, como registrada em `.claude/state/brief-T3.76-validacao-em-um-dia.md`** (citada em
[[EXP-0026-regime-como-estrategia|EXP-0026]]): *"90 dias é muita coisa, precisamos validar dentro de
1 dia"* (Everton, 12:10 BRT de 2026-09-10). Combinada com a regra permanente já documentada em
`.claude/state/notes-T3.76.md` §7 e em [[EXP-0026-regime-como-estrategia|EXP-0026]] §"Aprova quem
cumprir todas": *"a regra permanente do Everton ('as que estão dando ruim pode matar')"* — ou seja,
um candidato entra, é pré-registrado, replayado e julgado dentro do mesmo turno, e o que não passa a
régua editorial (n ≥ 100, ≥ 30 dias, IC 95 % por blocos de dia acima de zero, leave-one-market-out
nunca negativo, 2 de 3 janelas de 30 dias positivas) é aposentado pela via auditada **no mesmo dia**,
não fica "em avaliação" indefinidamente.

**Como foi seguida hoje:** o lote do T3.76/EXP-0026 mediu quatro braços (`mean_reversion`
`v15`/`v16`/`v17`, `momentum v11`) entre 12:20 e 18:11 BRT e os quatro foram descartados e
aposentados no mesmo dia (15:26 BRT, depois do deploy que destravou a `ops` — ver
[[Diario/2026-09-10]] §5–§6). Nenhum ficou pendurado para o dia seguinte.

## 2. Tudo instantâneo — SLO explícito por trecho, nunca um "está lento" vago

**A instrução, citada literalmente em `.claude/state/notes-T3.79.md` §8** (frontend-specialist,
sobre o bloco "Latência" da tela de sistema): *"pedido do Everton ('quero tudo instantâneo') de que
um hop vermelho seja impossível de não notar, não só um badge pequeno"*. A tradução em contrato foi
feita pelo T3.79: cada trecho do caminho (evento da Binance → recebido, vela fechada → publicada,
vela → decisão, decisão → admissão, admissão → fill, ponta a ponta) ganhou um alvo numérico de p50/p95
e um selo (`ok`/`warn`/`critical`/`unknown`) — nunca "lento" sem número, nunca `unknown` fabricado
como `ok`.

**Alvos congelados hoje** (`GET /api/v1/system/latency`, `hunter_api/services/latency.py`):

| Trecho | p50 | p95 |
|---|---|---|
| `ingest` | 0,5 s | 1,0 s |
| `flush` | 0,5 s | 1,0 s |
| `decisão` | 5 s | 20 s |
| `admissão` | 1 s | 2 s |
| `fill` | 1 s | 2 s |
| `end_to_end` | 5 s | 10 s |

**Como foi seguida hoje:** a régua acima não era cumprida em nenhum trecho medido (`flush` e
`decisão` em `critical`, ver [[Diario/2026-09-10]] §7) — o mesmo turno que publicou o SLO também
entregou as três correções que atacam a causa (T3.74c/d, T3.80, T3.81, consolidadas em
[[11-KNOWLEDGE/KB-0087-o-atraso-de-decisao-e-as-tres-correcoes|KB-0087]]), implantadas no deploy
`e81d53e` das 15:25 BRT. O número "depois" ainda não foi relido — fica para o próximo turno.

## 3. Lucro real sempre em USDT e BRL, pela cotação observada

**A instrução, citada literalmente em `.claude/state/notes-T3.78.md` §8** (T3.78b,
backend-specialist): *"Everton (2026-09-10): a API só publicava lucro real em BRL; a regra é lucro
em **USDT** (a moeda operada) **e** BRL pela taxa **observada**, com fonte e instante visíveis."*

**Como foi seguida hoje:** `GET /api/v1/orgs/{org}/lab/daily-goal` ganhou, de forma aditiva (nenhum
campo do contrato original renomeado ou removido), `value_of_1r.real_usdt_p10/p50/p90`,
`progress.real_usdt`, `fx: {rate, source, observed_at, available_at}` (`null` só quando `fx_reason`
está setado — nunca uma taxa adivinhada) e `series_30d[].unique_usdt`. O painel do Lab passou a
mostrar o USDT como número principal, o BRL abaixo, e a linha da cotação com fonte e instante. A meta
diária (`DAILY_GOAL_BRL = 9000`) só acende verde com **valor real** ≥ meta — nunca pelo rótulo
teórico de R$250/R (`value_of_1r.label_brl`). Ver [[Diario/2026-09-10]] §8.

## O que estas três regras não mudam

Nenhuma delas alterou um limite de risco (`risk_per_trade_pct`, tetos de participação/exposição),
nenhuma promoveu uma versão a `paper` e nenhuma tocou `.env*`. São regras de **processo** (cadência
de decisão, visibilidade de latência, honestidade de moeda) — a diferença entre "dando ruim" e
"promovendo" continua sendo a régua editorial de cada EXP.

## Relacionadas

[[EXP-0026-regime-como-estrategia]] · [[Diario/2026-09-10]] ·
[[11-KNOWLEDGE/KB-0087-o-atraso-de-decisao-e-as-tres-correcoes|KB-0087]] ·
[[08-CHANGELOG/Changelog|Changelog]]

## Fontes

`.claude/state/brief-T3.76-validacao-em-um-dia.md` · `.claude/state/notes-T3.76.md` §7 ·
`.claude/state/notes-T3.79.md` §8 · `.claude/state/notes-T3.78.md` §8 (T3.78b)

Ver também [[2026-09-10-universo-de-pesquisa-90-dias]] (quarta regra do dia, aprovada 19:1x BRT).
