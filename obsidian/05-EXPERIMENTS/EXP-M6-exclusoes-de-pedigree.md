---
tags: [experimento, meme, pumpfun, paper, pre-registro, pedigree, filtro-transversal, m4]
updated: 2026-09-12
status: pre-registrado
owner: quant-engineer
exp: EXP-M6
strategy: "meme/pumpfun — exclusões de pedigree: recusa transversal, em qualquer conjunto, do criador em série e do clone de ticker, contados em meme_tokens na hora da proposta (carteira paper, sem ordem real)"
version: "gate exclusoes_de_pedigree v1 (hunter_indicators.meme.pedigree), aplicado por padrão a todo conjunto desde a T4.16"
result: nao-iniciado
evaluable: 0
days: 0
last_eval: ""
---

# EXP-M6 — exclusões de pedigree: criador em série e clone de ticker

> **Pré-registro escrito na T4.16 em 2026-09-12 (15:xx BRT), ANTES de a recusa ter sido aplicada a uma única
> proposta prospectiva.** Protocolo congelado; avaliações acrescentadas, nunca reescritas. Não é um conjunto de
> regras: é um **filtro transversal** que toda porta aplica antes da sua (E2 do
> [[03-TRADING/Meme/Estudo-2026-09-12-21-apostas|estudo das 21 apostas de 12/09]]). A previsão padrão é
> `descartar`.

## Diretiva de origem

O estudo das 21 apostas: **criador em série** (≥ 2 moedas do mesmo criador na hora anterior) em 6 de 21, todas
perdedoras (DOJO 18, LARPEPE 35, Bupa 15, Dick 4, Traders 3, DIAPER 2); **clone de ticker** (≥ 3 moedas com o
mesmo símbolo em 24 h) em 6 de 21, todas perdedoras (Chaotic 32, CATECOIN 29, DIAPER 27, 67 % 23, Bupa 19,
RISE 9); a única vencedora sem nenhum dos dois. Plantão run 10/13 (M-P3, M-P5, M-P26, M-P29). "E2 vira
pré-condição de E5" — e, por decisão desta tarefa, de todo conjunto.

## Hipótese (congelada)

**H1:** recusar, em qualquer conjunto, a moeda cujo criador lançou ≥ 2 outras na hora anterior
(`creator_prior_mints_1h ≥ 2`) ou cujo ticker aparece em ≥ 3 moedas nas 24 h anteriores (`symbol_dup_24h ≥ 3`,
contando a própria) **melhora a expectância** do conjunto por ≥ 0,10 R sem cortar mais de 40 % das suas
entradas. **H0 (previsão):** os marcadores são reais mas **não independentes** do que a porta de fluxo já mede
(um criador em série lança moedas sem demanda): o Δ contra "sem pedigree" fica dentro de ±0,05 R → `descartar`
como filtro autônomo (mantido como diagnóstico).

## Definição congelada (`exclusoes_de_pedigree v1`)

| insumo | definição | limiar | recusa |
|---|---|---|---|
| `creator_prior_mints_1h` | outras moedas de `meme_tokens` com o mesmo `creator`, `created_at` em `(t − 3 600 s, t]` onde `t` = `created_at` da moeda julgada | `> 1` (i.e. ≥ 2) | `creator_serial` |
| `symbol_dup_24h` | outras moedas com o mesmo `symbol`, `created_at` em `(t − 86 400 s, t]` | `> 2` (i.e. ≥ 3 com a própria) | `symbol_clone` |
| criador desconhecido | `meme_tokens.creator IS NULL` ou `created_at IS NULL` | — | `creator_unknown` |
| símbolo desconhecido | `meme_tokens.symbol IS NULL` | — | `symbol_unknown` |
| pedigree não lido | mint ausente do mapa que o laço leu | — | `pedigree_unknown` |

Contado em `meme_tokens` **na hora da proposta** (`lab_repo_fast.pedigree_for`; só moedas criadas **até** a
julgada — uma lançada depois não é "anterior"), gravado em `reasons` (`feature: pedigree`, os dois contadores
e os dois tetos), **somado** às recusas da própria porta (o heartbeat conta as duas — uma linha excluída por
pedigree ainda diz o que a porta teria dito). Desconhecido recusa por nome, nunca é lido como limpo.

**Fora desta versão (declarado):** `post_sibling_rank_at_create > 1` (M-P33) e "`twitter` ausente **e**
`desc` vazia" — não há coluna para eles hoje (dados da T4.2g/T4.12); uma versão que os inclua é
`exclusoes_de_pedigree v2` e outra página.

## Portão de desenho (C1–C8) — congelado

| # | Critério | Veredito | Justificativa |
|---|---|---|---|
| C1 | Plausibilidade | **PASS** | Um criador que lança em série está a rodar uma fábrica; um ticker repetido é cópia de algo que subiu. Mecanismo claro, medido 12/12 dentro da amostra |
| C2 | Sobreajuste | **PASS** | Dois limiares (2 e 3), do estudo, um dígito cada |
| C3 | Amostra | **PASS** | Só `meme_tokens` — toda moeda rastreada tem os insumos (quando o criador e o símbolo chegaram pela descoberta/boards) |
| C4 | Regime | **REVISE** | A fração de criadores em série muda com o dia (plantão) |
| C5 | Saídas | **N/A** | Não é um conjunto: não tem saída |
| C6 | Concentração | **N/A** | Idem |
| C7 | Execução | **N/A** | Idem |
| C8 | Invalidação | **PASS** | A própria régua: Δ ≤ 0,05 R contra "sem pedigree" invalida |

**Veredito do portão:** **`PASS`** — 2026-09-12, quant-engineer (T4.16).

## Protocolo (congelado — nunca editar)

- **code_ref:** `hunter_indicators.meme.pedigree` (`PEDIGREE_V1`, `evaluate_pedigree`); aplicação em
  `services/meme-worker/hunter_meme_worker/proposals.py` (`evaluate_gate(pedigree=…)`), contagem em
  `lab_repo_fast.pedigree_for`; parâmetro por conjunto `pedigree_exclusions` (padrão `true`; `false` é a palavra
  do braço de falseamento, nunca o padrão).
- **Medição:** por conjunto, a fração de recusas `creator_serial`/`symbol_clone` (`lab_gate_refusals`,
  `meme_lab_ticks`), e — para a régua — a expectância do conjunto **com** o filtro contra a expectância das
  propostas que o filtro **teria** recusado (reconstruível de `reasons`: toda proposta grava os contadores,
  então "o que o filtro cortou" é o conjunto das propostas cujos contadores ultrapassam os tetos — nas
  apostas que já existiam antes da T4.16 e no braço de falseamento).
- **Braço de falseamento:** um conjunto com `pedigree_exclusions: false` e a mesma porta do braço medido —
  a ser semeado **só** se a amostra do braço medido fechar (≥ 100 apostas); até lá a comparação é retrospectiva
  (as 21 de 12/09 e as apostas de conjuntos anteriores, cujas propostas não gravaram o pedigree — recontadas
  por `meme_tokens`).
- **Universo:** toda proposta de todo conjunto ativo desde a T4.16.

## Previsões congeladas

- **P1:** ≥ 30 % das recusas do dia de qualquer porta são `creator_serial`/`symbol_clone` nos primeiros 7 dias.
- **P2:** `creator_unknown` + `symbol_unknown` ≤ 10 % das avaliações (a descoberta e os boards entregam a
  identidade quase sempre).
- **P3:** o Δ do filtro contra "sem pedigree" é positivo na amostra retrospectiva de 12/09 (+0,20 R: as 11
  perdedoras cortadas) e **dentro de ±0,05 R** na prospectiva com a porta de fluxo ligada → `descartar` como
  filtro autônomo, manter como diagnóstico.

## Regra de sucesso (congelada)

`validada` exige Δ ≥ +0,10 R (IC 95 % por blocos de dia, semente 20260912) contra o braço/reconstrução sem
pedigree, cortando ≤ 40 % das entradas, em ≥ 100 propostas avaliadas e ≥ 30 dias. Qualquer coisa menos:
`descartar` — o filtro é desligado por conjunto (`pedigree_exclusions: false` numa versão nova), a página fica.

## Regras de morte

- **K1** — `creator_unknown` + `symbol_unknown` > 50 % das avaliações: o insumo não chega; consertar a
  identidade antes de medir o filtro.
- **K2** — o filtro corta > 80 % das entradas de um conjunto por 7 dias: é o universo, não o pedigree.

## Avaliações (acrescentadas, nunca reescritas)

*Nenhuma.* A página nasce em 2026-09-12 com `result: nao-iniciado`, `evaluable: 0`, `days: 0`.

## Variantes tentadas

| Variante | Quando | Por quê | Onde |
|---|---|---|---|
| — | — | — | — |

## Relacionadas

[[Experiments Index]] · [[03-TRADING/Meme/README|Meme (Trading)]] · [[03-TRADING/Meme/Estudo-2026-09-12-21-apostas]] ·
[[EXP-M5-fluxo-e-holders]] · [[EXP-M4-moonshot]] · [[00-INBOX/Hipoteses-do-plantao]] ·
[[KB-0091-pump-fun-as-taxas-base-e-seus-denominadores]]

## Braço 2 — reincidência do criador (15/09/2026, T4.24)

**Por quê:** pedido do Everton (15/09 20:4x BRT) — "as apostas, temos que tomar cuidado, pois tem gente que sobe
moeda golpe e compramos e por isso perdemos." Medido no banco da VPS (176 apostas de papel medidas até 15/09
20:4x BRT; `infra/scripts/sql/research/2026-09-15-t424-reincidencia.sql`): 89 apostas tinham criador com moeda
anterior no nosso banco; em **31** o criador **já tinha vendido** numa moeda anterior
(`meme_features_1m.creator_sold = true` antes da criação da moeda apostada). Essas 31: R médio −0,168 (contra
−0,140 nas outras 145), **26 das 85 saídas `creator_dump`** e só 4 ganhas (13 %, contra 19 %). Sinal real,
modesto: excluir reincidentes teria evitado −5,2 R e 4 acertos. Não é bala de prata — a maioria dos golpes é de
criador **novo** (carteira nova por moeda) — mas é o filtro mais barato que ainda não existia.

**Hipótese (congelada):** **H1:** recusar, em qualquer conjunto, a moeda cujo criador já vendeu numa moeda
anterior em qualquer janela (`creator_prior_dump_count ≥ 1`) melhora a expectância por ≥ 0,10 R sem cortar mais
de 40 % das entradas. **H0 (previsão):** a maioria dos golpes é de criador novo, sem histórico algum — o sinal é
real mas pequeno e não independente do que a fita/holders já medem → `descartar` como filtro autônomo (mantido
como diagnóstico), a mesma leitura do braço 1.

**Definição congelada (v2, braço 2):** `creator_prior_dump_count` — moedas anteriores do mesmo criador, **em
qualquer janela** até a criação da moeda julgada, em que (a) `meme_features_1m.creator_sold = true`, (b)
`meme_paper_bets.creator_sold_seen_at IS NOT NULL` (vigilância da cadeia, T4.2h) ou (c) uma aposta nossa saiu por
`creator_dump`; limiar `≥ 1` → recusa `creator_repeat_dumper`. `creator_prior_dead_count` — das anteriores, quantas
caíram abaixo de 20 % do próprio topo nos 30 minutos seguintes à criação, se houver série; sem série, a moeda não
entra na contagem (nem viva, nem morta) — diagnóstico, nunca uma recusa. Contado em `meme_tokens` +
`meme_features_1m` + `meme_paper_bets` na hora da proposta (`lab_repo_fast.pedigree_for`); gravado em `reasons`
(`feature: pedigree`, junto de `creator_prior_mints_1h`/`symbol_dup_24h`) sempre que o bloco existe, mesmo nos
conjuntos que não ligam o filtro. **`PEDIGREE_V1` (E2 v1: criador em série, clone de ticker) não muda** — esta é
uma exclusão independente (`evaluate_repeat_dumper`), nunca uma versão nova do gate congelado.

**Regra (`flow_v2/5`, `research_only`, relógio de 15 s; a mesa usa o mesmo braço como `operator/5`):** tudo do
braço 2 da E1 (`flow_v2/2`/`operator/4`) mais `pedigree_repeat_dumper: true`. Saídas iguais (3×, trailing 35 %
após 1,5×, 30 min, `creator_dump`, `line_broken`, −50 %).

**Previsão congelada:** `descartar` como filtro autônomo — a mesma leitura do braço 1 (H0): o sinal é real na
amostra retrospectiva (31 de 89, Δ −0,028 R contra as sem histórico de venda) mas a maioria dos golpes escapa
dele (criador novo, sem histórico algum). **Régua:** a mesma dos braços anteriores (≥ 100 apostas e 30 dias, IC
95 % por blocos de dia, leave-top-out, semente 20260912); `flow_v2/1`/`flow_v2/2` continuam ativos, a comparação
é o ponto. **O que não vale:** ajustar o limiar (`≥ 1`) olhando os primeiros dias prospectivos (KB-0092).

**Migração:** `0039_meme_creator_repeat` (`…0010` para `flow_v2/5`, `…0011` para `operator/5`; `operator/4`
aposentado); `docs/DATABASE.md` §51.

## Fontes

`packages/indicators/hunter_indicators/meme/pedigree.py` · `packages/indicators/tests/unit/test_meme_pedigree.py` ·
`services/meme-worker/hunter_meme_worker/{proposals,proposals_reasons,lab_repo_fast,lab,lab_fast}.py` ·
`services/meme-worker/tests/{test_proposals_flow,test_lab_fast}.py` · `docs/plans/T4-MEME-RADAR.md` §T4.16, §T4.24 ·
`infra/scripts/sql/research/2026-09-12-t416-filtros-de-pedigree-nas-21.sql` ·
`infra/scripts/sql/research/2026-09-15-t424-reincidencia.sql` ·
`infra/scripts/meme_close_{lessons,lesson_kit,render_ops,queries}.py` (braço 2, §6.14 do fechamento diário).
