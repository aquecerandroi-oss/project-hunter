---
tags: ["estrategia", "catalogo", "momentum", "familia"]
strategy: momentum
updated: 2026-09-09
---
# momentum

<!-- generated:start -->
## Versões

| Versão | Propósito | Status | Veredito | Página |
|---|---|---|---|---|
| `v1` | `research_only` | `deprecated` | inconclusivo. | [[momentum-v1]] |
| `v2` | `research_only` | `deprecated` | descartar — negativa nas duas coortes (prospectiva −0,2167 R, n=471; replay −0,2247 R, n=248); aposentada 2026-09-09T14:56:27Z (T3.56), sem sucessora. | [[momentum-v2]] |
| `v3` | `paper` | `active` | inconclusivo, −0,2256 R em n=453 (T3.56) — **tentativa de aposentadoria recusada pelo script**: a linha `paper` não pode sair enquanto tiver acompanhamento aberto (5–6 *shadow slots* em voo, e ela continua ativa abrindo novos). Fica `active` até a janela ficar limpa ou a linha paper mudar de versão. | [[momentum-v3-paper]] |
| `v4` | `research_only` | `deprecated` | descartar — negativa nas duas coortes (prospectiva −0,1650 R, n=201; replay −0,1506 R, n=30), 20,9 % das decisões prospectivas acima do teto de stop do `paper_v1`; aposentada 2026-09-09T14:57:16Z (T3.56), sem sucessora. Sem página própria nesta sessão. | — |
| `v6` | `research_only` | `deprecated` | descartar — negativa nas duas coortes (prospectiva −0,2856 R, n=156; replay −0,0513 R, n=195); aposentada 2026-09-09T14:58:00Z (T3.56), **sucessora `momentum v8`**. | [[Estrategias/momentum-v6|momentum-v6]] |
| `v7` | `research_only` | `deprecated` | descartar — Δ pareado −0,0040 R contra `v6`, dominada pela irmã `v8`; aposentada 2026-09-08T23:34:42Z. | [[Estrategias/momentum-v7|momentum-v7]] |
| `v8` | `research_only` | `active` | inconclusivo — Δ pareado +0,0161 R contra `v6` (IC contém zero), ainda perde (PF 0,906). **Única `momentum` viva no roster de 9 do T3.56.** | [[Estrategias/momentum-v8|momentum-v8]] |
| `v9` | `research_only` | `deprecated` | **efêmera, zero decisões** — variante do eixo de timeframe (`atr_timeframe` 1h, de `v8`), morreu por `atr_warmup`: pedia 5 820 min de contexto contra o teto de 1 560 do worker naquele instante; aposentada no mesmo turno (T3.54), sucessora `momentum v10`. Sem página própria. | — |
| `v10` | `research_only` | `deprecated` | descartar — mesma variante de `v9` com `atr_bars` encolhido (cabe no contexto); 252 decisões de replay, líquida −0,0357 R, PF 0,809, **37,3 % das decisões furam o teto de stop do `paper_v1`**; portão C1–C8 = `REJECT` em C5 ([[EXP-0021-timeframe]]); aposentada 2026-09-09T14:58:42Z (T3.56), sem sucessora. Sem página própria nesta sessão. | — |
| `v11` | `research_only` | `active` | **portão de regime `btc:BTC_BULL,HIGH_VOLATILITY`, de `v8`** (G2 do [[EXP-0020-regime-gate]] — dois rótulos, não é o G2 pré-registrado) — 101 decisões, 14 dias, líquida +0,0737 R, PF 1,251; Δ vs `v8` +0,1104 R com IC 95 % [−0,0605; +0,2859] (cruza zero); estresse `frágil a custos` (`custos_x2` reverte o sinal) e dependente de metade. **Não promover — ativa prospectiva**: mantida `research_only` para a coorte prospectiva decidir o que o replay não pode. Sem página própria nesta sessão. | — |

## Ligações

- Convenção: [[Estrategias/README|Estratégias]]
- Eixo "stop largo" (v6→v7/v8): [[EXP-0018-stop-largo]]
- Eixo "alvo mais longe" (v2→v6): [[EXP-0013-momentum-alvo-3-atr]]
- Eixo "timeframe" (v8→v9/v10): [[EXP-0021-timeframe]]
- Eixo "portão de regime" (v8→v11): [[EXP-0020-regime-gate]]
- Roster (16 → 9, T3.56): [[EXP-0021-timeframe]] · `.claude/state/notes-T3.56.md`
<!-- generated:end -->


## Notas

**Tabela de versões `v6`–`v8` acrescentada à mão pela Sexta-feira em 2026-09-08** a partir de
[[EXP-0013-momentum-alvo-3-atr]], [[EXP-0018-stop-largo]] e `.claude/state/notes-T3.47b.md` — o
exportador (`infra/scripts/export_strategies_to_obsidian.py`) não alcança o Postgres da VPS a partir
deste host nesta sessão (`ConnectionRefusedError`). Rodar o exportador confirma os campos e substitui
esta nota quando o banco estiver acessível.

**Linhas `v2`, `v3`, `v4`, `v6`, `v9`, `v10` atualizadas/acrescentadas à mão pela Sexta-feira em
2026-09-09** a partir de `.claude/state/notes-T3.56.md` (roster 16 → 9, sete aposentadorias pela via
auditada e a recusa da linha `paper`) e `.claude/state/notes-T3.54.md` (eixo de timeframe, `v9`/`v10`).
`v4`, `v9` e `v10` não têm página individual nesta sessão — o exportador continua sem acesso ao
Postgres da VPS a partir deste host; rodá-lo cria as três páginas que faltam. Os números de `v2`, `v4`
e `v6` são os **medidos por T3.56** (`as_of` 2026-09-09T14:52Z), não os do brief que a abriu — ver
`.claude/state/notes-T3.56.md` §3.0 para as pequenas divergências (nenhuma muda o sinal).

**Linha `v11` acrescentada à mão pela Sexta-feira em 2026-09-09** a partir de
`.claude/state/notes-T3.52d.md` (T3.52d) e [[EXP-0020-regime-gate]]. Portão de elegibilidade por
regime (`eligibility_policy`, `docs/PIPELINE.md` §4b item 10). Achado de método da mesma corrida,
registrado em `docs/PIPELINE.md` §4b itens 11–12 e `docs/plans/SHADOW-LAB.md`: uma versão com
portão **não** é subconjunto do pai nas decisões (só nas barras — 3 das 101 decisões de `v11` não
têm correspondente no pai, todas em 2026-09-03), e o critério K4 (`unavailable`) deixa de ser
mensurável nela — o número honesto é o K4 do pai. Sem página própria nesta sessão.


**Acréscimo de 2026-09-10 (T3.76, quant-engineer) — `v11` medida em 90 dias pela primeira vez, e
negativa.** Pré-registro em [[EXP-0026-regime-como-estrategia]]. A `v11` (portão
`btc:BTC_BULL,HIGH_VOLATILITY` sobre a `v8`) foi replayada em **90 dias × 16 mercados** (12 fatias,
138 240 barras, 0 erros, coorte `replay:70f55430…`): **1 167 desfechos terminais em 47 dias**,
ex-funding **−0,0595 R**, `R_net` −0,0588, PF 0,815, soma −69,4 R. **K3 dispara** (≥ 100 avaliáveis,
≥ 30 dias, expectativa bruta negativa) e o estresse fecha em **`sem_vantagem_na_base`**. Por janela de
30 d: −0,1101 / −0,2137 / +0,0931 — **1 de 3**, a mesma assinatura de calendário da família
`mean_reversion`. Leave-one-market-out: **negativo nos 16** reajustes. Desfechos: 743 `invalidated`,
272 `expired`, 111 `target`, 41 `stop`.

**O contraste pré-declarado não existe, e isso é um fato sobre o roster, não sobre a versão.** O pai
da `v11` é a `momentum v8`, que está `deprecated` desde 2026-09-09T19:21Z — e o replay recusa versão
não executável (`momentum:v8 is not one runnable version`). Sem coorte de 90 d do pai não há Δ contra
o controle pré-registrado; o veredito acima é da **população própria** da `v11`, que já é suficiente
para descartar (K3 + `sem_vantagem_na_base` + 16 LOO negativos) sem precisar do contraste.

Recomendação ao orquestrador: aposentar `momentum v11` (a tarefa não conseguiu — mesmo bloqueio de
`compose.sh ops` descrito em `.claude/state/notes-T3.76.md` §7). Se alguém quiser o contraste contra o
pai algum dia, ele exige reviver a `momentum v8` por via auditada — decisão de quem cuida do roster,
não deste caminho.
