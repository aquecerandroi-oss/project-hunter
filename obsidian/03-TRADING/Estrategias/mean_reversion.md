---
tags: ["estrategia", "catalogo", "mean_reversion", "familia"]
strategy: mean_reversion
updated: 2026-09-10
---
# mean_reversion

<!-- generated:start -->
## Versões

| Versão | Propósito | Status | Veredito | Página |
|---|---|---|---|---|
| `v1` | `research_only` | `active` | **reprovada em 90 dias/16 mercados** (EXP-0025, T3.62b) — 542 avaliáveis, 83 dias; ex-funding **−0,0910 R**, PF 0,851, K3 disparado; estresse `frágil a custos`. Substitui a leitura de 31 dias abaixo. | [[mean_reversion-v1]] |
| `v2` | `research_only` | `active` | **reprovada em 90 dias/16 mercados** (EXP-0025, T3.62b) — 302 avaliáveis, 68 dias; ex-funding **−0,0343 R**, PF 0,940, K3 disparado; estresse `frágil a custos`. Substitui a leitura de 7 dias abaixo. | [[Estrategias/mean_reversion-v2|mean_reversion-v2]] |
| `v3` | `research_only` | `active` | inconclusivo, `REVISE` no portão — 11 avaliáveis, 4 dias; líquida +0,5131 R; corte de 70,3 % dispara a régua do `EXP-0006`. | [[Estrategias/mean_reversion-v3|mean_reversion-v3]] |
| `v4` | `research_only` | `deprecated` | descartar — K1 (10 decisões); aposentada 2026-09-08T23:34:57Z, sem sucessora. | [[mean_reversion-v4]] |
| `v5` | `research_only` | `deprecated` | descartar — K1 (9 decisões), 44 % fora da banda de stop do `paper_v1`; aposentada 2026-09-08T23:34:59Z, sem sucessora. | [[mean_reversion-v5]] |
| `v6` | `research_only` | `active` | manter em pesquisa — melhor candidata do eixo "stop largo" (guarda 95 % da economia de pedágio); K1 (15 decisões). | [[mean_reversion-v6]] |
| `v7` | `research_only` | `active` | manter em pesquisa com ressalva — só 32 % da economia de pedágio sobrevive; K1 (14 decisões). | [[mean_reversion-v7]] |
| `v8` | `research_only` | `active` | inconclusivo (sinal `negativo` no corpo do EXP) — Δ −0,2006 R contra `v6`; mantida pela mensurabilidade, não pelo mérito. | [[mean_reversion-v8]] |
| `v9` | `research_only` | `deprecated` | **efêmera, zero decisões** — variante do eixo de timeframe (`atr_timeframe` 1h, de `v6`), morreu por `atr_warmup`: pedia 5 820 min de contexto contra o teto de 1 560 do worker naquele instante; aposentada no mesmo turno (T3.54), sucessora `mean_reversion v10`. Sem página própria. | — |
| `v10` | `research_only` | `active` | **reprovada em 90 dias/16 mercados** (EXP-0025, T3.62b) — 798 avaliáveis, 89 dias; ex-funding **−0,0293 R**, PF 0,910, K3 disparado. Os +0,1105 R/PF 1,451 de 31 dias eram só a janela de agosto–setembro (Δ contra jun–ago exclui zero); os 4 mercados originais caem a +0,0002 R (zero) nos 90 d; C5 (teto de risco 3 %) 16,8 % em 90 d contra 32,3 % só em agosto. Sem página própria nesta sessão. | — |
| `v11` | `research_only` | `deprecated` | **portão de regime `btc:SIDEWAYS`, de `v6`** (G1 do [[EXP-0020-regime-gate]]) — morta no K1 (1 decisão em 31 dias, 4 mercados): `SIDEWAYS` só tem 6 h na primeira metade da janela de replay. `inconclusivo`, não negativo — as 14 decisões que o portão removeu do pai eram vencedoras (+0,2964 R), evidência **contra** a hipótese; aposentada 2026-09-09T16:07Z, sem sucessora. Sem página própria nesta sessão. | — |

## Ligações

- Convenção: [[Estrategias/README|Estratégias]]
- Eixo "teto de pedágio" (v1→v2/v3): [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]]
- Eixo "stop largo" (v2→v6/v7, v3→v4/v5): [[EXP-0018-stop-largo]]
- Eixo "piso de ATR%" (v2→v8): [[EXP-0019-piso-atr]]
- Eixo "timeframe" (v6→v9/v10): [[EXP-0021-timeframe]]
- Eixo "portão de regime" (v6→v11): [[EXP-0020-regime-gate]]
- Replicação de 90 dias (v1/v2/v10): [[EXP-0025-mean-reversion-90-dias]]
- Irmã de 1 h (módulo novo, código pronto, replay pendente): [[mean_reversion_h1]]
<!-- generated:end -->


## Notas

**Tabela de versões corrigida e ampliada (`v1` estava marcada `draft`/sem veredito, desatualizada
desde a T3.33b) pela Sexta-feira em 2026-09-08**, a partir de
[[EXP-0009-mean-reversion-pullback-em-tendencia]], `.claude/state/exp-drafts/EXP-0014-mean-reversion-teto-025.md`,
`.claude/state/exp-drafts/EXP-0015-mean-reversion-teto-020.md`, [[EXP-0018-stop-largo]],
[[EXP-0019-piso-atr]] e `.claude/state/notes-T3.47b.md`. O exportador
(`infra/scripts/export_strategies_to_obsidian.py`) não alcança o Postgres da VPS a partir deste host
nesta sessão (`ConnectionRefusedError`) — rodá-lo confirma os campos e substitui esta nota quando o
banco estiver acessível. `EXP-0014` e `EXP-0015` (as versões `v2`/`v3`) continuam como rascunhos em
`.claude/state/exp-drafts/`, não arquivados no vault; os números acima vêm deles diretamente.

**Linhas `v9`/`v10` acrescentadas à mão pela Sexta-feira em 2026-09-09** a partir de
`.claude/state/notes-T3.54.md` e [[EXP-0021-timeframe]]. `v9` e `v10` não têm página individual nesta
sessão pelo mesmo motivo acima (exportador sem acesso ao Postgres da VPS). `v10` é, nesta data, a
**única** coorte de `mean_reversion` com população julgável (`n ≥ 30`) e veredito `robusto` — mas o
ganho é de amostra (o piso de ATR% quase não morde em 1 h), não de expectativa: a expectativa bruta e
líquida por decisão não se distingue da `v6` (IC do contraste transversal cobre zero).

**Linha `v11` acrescentada à mão pela Sexta-feira em 2026-09-09** a partir de
`.claude/state/notes-T3.52d.md` (T3.52d) e [[EXP-0020-regime-gate]]. Portão de elegibilidade por
regime (`eligibility_policy`, `docs/PIPELINE.md` §4b item 10) — mede exatamente o que o pai
decidiria dentro do rótulo permitido, sem mudar parâmetro nenhum. Achado de método da mesma
corrida, registrado em `docs/PIPELINE.md` §4b itens 11–12 e `docs/plans/SHADOW-LAB.md`: uma versão
com portão **não** é subconjunto do pai nas decisões (só nas barras), e o critério K4
(`unavailable`) deixa de ser mensurável nela — o número honesto é o K4 do pai. Sem página própria
nesta sessão.

**Acréscimo de 2026-09-10 (plantão de arquivamento, T3.62b) — as linhas `v1`/`v2`/`v10` corrigidas
para o veredito de 90 dias.** As avaliações de 31/17/7 dias citadas acima nas linhas antigas da
tabela **não foram apagadas do histórico** (continuam nas páginas de EXP de origem); a coluna
"Veredito" da tabela `<!-- generated:start -->` foi **atualizada** para refletir a leitura mais
recente e maior, como o gerador faria — ver [[EXP-0025-mean-reversion-90-dias]] para a nota completa,
datada e append-only. Resumo: `mean_reversion` replayada em **90 dias × 16 mercados** (36 corridas,
414 720 barras, 1 644 decisões, 0 erros) mostra as três versões **negativas** no eixo `r_ex_funding`
(cobertura 100 %, forçado pela ausência de `funding_rates` antes de 2026-08-08T16:00Z): `v10`
−0,0293 R/PF 0,910, `v1` −0,0910 R/PF 0,851, `v2` −0,0343 R/PF 0,940 — **K3 dispara nas três**, pela
primeira vez com população suficiente para a régua julgar (≥ 100 avaliáveis e ≥ 30 dias). O motivo:
nas três, as janelas de junho–julho e julho–agosto são negativas e só agosto–setembro é positiva, com
o Δ(J3 − J1J2) excluindo zero nas três (`v10` +0,2265 R, IC [+0,0085; +0,4293]) — **a vantagem medida
antes era a janela de agosto, e só ela**. Os 4 mercados originais que geraram a hipótese caem para
+0,0002 R (exatamente zero) em 90 dias. C5 (fração acima do teto de risco de 3 % do `paper_v1`) é
16,8 % nos 90 dias inteiros contra 32,3 % só na janela de agosto — **propriedade de versão × regime**,
não só de versão. **Nenhuma das três é candidata a linha `paper` neste desenho**; nenhuma foi
depreciada por esta tarefa (recomendação para o orquestrador). O que sobra de valioso é a hipótese de
um portão de regime que restrinja a família à janela em que ela funciona — versão nova, não ajuste,
no mesmo desenho do [[EXP-0020-regime-gate]].

