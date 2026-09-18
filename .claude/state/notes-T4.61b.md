# T4.61b — Tamanho por convicção (executor real, mainnet)

**Data:** 18/09/2026. **Pedido (Everton, 15:0x BRT):** "usa a inteligência que já adquirimos e opera
agora com o dinheiro que temos; pode variar os valores da entrada a partir de agora". Até aqui toda
compra real era `min(policy.max_sol_per_trade, proposal.size)` = **0,28 SOL fixos**.

## O que foi feito

- **`hunter_meme_executor/conviction.py` (345 linhas, puro).** `ConvictionConfig` (frozen, `from_env`,
  `as_json`), `ConvictionEvidence`, `Rung`, `ConvictionLadder`, `evaluate_conviction(evidence, config,
  requested_sol, max_sol_per_trade, min_trade_sol)`. Escada: `creator` (só a fita/ninguém/memória × 0,5;
  cadeia limpa 1,0) → `buyers` (`unique_buyers_60s < 25` ou desconhecido × 0,5) → `holders`
  (`holders_rising` falso/desconhecido × 0,5) → `concentration` (`bundled > 10 %` ou `top10 > 20 %` ou
  desconhecido × 0,5) → `drop` (`real_sol` da leitura desta admissão ≥ 50 % abaixo do máximo de
  `meme_curve_snapshots` em 60 s ⇒ **recusa `entry_after_drop`**; sem foto × 0,5 `peak_unknown`).
  `sol_cap = min(pedido, max_sol_per_trade)`; `sol_sized = quantize_down(sol_cap × Π)`; produto < 0,25
  ou `sol_sized < min_trade_sol` ⇒ **recusa `conviction_too_low`**; a recusa da queda tem precedência.
  `enabled = False` (padrão) ⇒ `applied = False`, `refusal = None`, `requested_sol = sol_cap` (tamanho de
  hoje), mas `ladder_refusal` e os degraus ficam escritos (sombra).
- **`conviction_read.py` (131).** Uma consulta por candidata admitida (`meme_curve_snapshots` max/count
  na janela de 60 s + `LEFT JOIN LATERAL` da linha mais nova de `meme_features_15s` ≤ 120 s),
  `evidence_from(built, curve, series)` (pega `creator_verdict.decided_by`, `bundled/top10` do
  `MemeContext`, `real_sol` da `CurveRead`), `conviction_for(...)`, `apply_ladder(proposal, ladder)`
  (revalida a `MemeEntryProposal` com o pedido dimensionado; intocada quando não aplicada).
- **`entries.py`** (337): `proposal_from` → `conviction_for` → `apply_ladder` → `admit`. O motor avalia
  o pedido dimensionado (vira o teto `requested` da §5, então `binding_constraint = requested` e os
  checks 21–25 julgam o tamanho final). `admission["conviction"]` e `intent["conviction"]` em toda
  ordem; recusa do motor tem precedência (checks completos); depois a da escada. Os 25 checks ficam
  gravados **no tamanho cheio** quando a escada recusa. Para caber nas 350 linhas, `ChainReads`/
  `_read_chain` viraram `chain.EntryReads`/`chain.read_entry`.
- **`config.py`**: `ExecutorConfig.conviction: ConvictionConfig` (`from_env` no boot).
  **`heartbeat.py`**: `policy.conviction_sizing = on|off`.
- **Docs**: `docs/RISK_ENGINE_MEME.md` §17 "Tamanho por convicção" (+ bullet na §5);
  `docs/ACTIVATION.md` 9f (tabela das 12 variáveis); vault `obsidian/11-KNOWLEDGE/KB-0137-tamanho-por-conviccao.md`
  (0135 e 0136 já existiam).

## Variáveis (`.env`, todas opcionais; ilegível/fora da faixa ⇒ padrão, nunca recusa o boot)

`MEME_CONVICTION_SIZING=off|on` (padrão off), `MEME_CONVICTION_TAPE_ONLY_MULT=0.5`,
`MEME_CONVICTION_MIN_UNIQUE_BUYERS=25`, `MEME_CONVICTION_BUYERS_MULT=0.5`, `MEME_CONVICTION_HOLDERS_MULT=0.5`,
`MEME_CONVICTION_BUNDLED_MAX_PCT=0.10`, `MEME_CONVICTION_TOP10_MAX_PCT=0.20`,
`MEME_CONVICTION_CONCENTRATION_MULT=0.5`, `MEME_CONVICTION_DROP_PCT=0.50`, `MEME_CONVICTION_DROP_WINDOW_S=60`,
`MEME_CONVICTION_PEAK_UNKNOWN_MULT=0.5`, `MEME_CONVICTION_FLOOR=0.25`, `MEME_CONVICTION_EVIDENCE_MAX_AGE_S=120`.

## Provas

- `uv run pytest services/meme-executor/tests -q -p no:cacheprovider -m "not live"` → **409 passed**
  (179,6 s, com Docker); `tests/test_conviction.py` = 30 novos (config; cada degrau passa e falha; as
  duas recusas; piso; nunca acima do teto/pedido; quantização; flag off = fixo com sombra; JSON;
  `apply_ladder` + `evaluate_meme_entry` com `sol_final = 0,14`, `binding_constraint = requested`,
  check 23 no tamanho final; leitura faked com uma só consulta e as duas janelas).
- `tests/test_conviction_db.py` (integração, Postgres via testcontainers, papel `hunter_worker`): **2 passed**
  (28,5 s) — o pico é o máximo da janela de 60 s (ignora −80 s e o futuro), a linha de 15 s é a mais
  nova ≤ 120 s, mint sem foto lê `None`/0.
- `ruff check` / `ruff format --check` em `services/meme-executor`: limpos. `pyright` nos 7 arquivos
  tocados: 0 erros. `check_file_size.py`: 969 arquivos, 0 acima do orçamento.

## Ressalvas (para o guardião de risco)

1. **Sombra custa uma consulta por candidata com a flag desligada.** Escolha deliberada (auditável antes
   de ligar); se o Everton preferir zero custo, `conviction_for` pode curto-circuitar com `enabled=False`.
2. **`entry_after_drop` compara fontes diferentes**: o `real_sol` vem da leitura RPC `confirmed` desta
   admissão (lamports/1e9); o pico vem de `meme_curve_snapshots` (todas as fontes: REST, RPC, WS; SOL
   humano). Um REST atrasado pode dar um pico "velho" dentro da janela por `observed_at` — a janela
   filtra por `observed_at`, não por `received_at`.
3. **Uma ordem recusada pela escada tem `admission.approved = true`** (o motor aprovou no tamanho cheio)
   e `reason = entry_after_drop|conviction_too_low`. A API do desk mostra `admission_approved: true` +
   `reason`; quem lê só `first_refusal` (vazio) precisa olhar `reason` ou `admission.conviction.refusal`.
4. **Nenhuma das duas recusas cola carência** (`DETERMINISTIC_REFUSALS`): a mesa repropõe em ~20 s e cada
   tentativa custa os RPCs da admissão. A queda limpa pelo relógio em 60 s; se virar ruído, entra
   `entry_after_drop` numa carência curta (não 120 s).
5. **`peak_unknown` é desconto, não recusa.** Fail-closed por evidência ausente seria recusar; ficou
   × 0,5 porque "sem foto em 60 s" hoje é o radar não ter olhado. Pergunta aberta para a Astra no KB.
6. O `params` da posição não carrega o multiplicador; o `intent`/`admission` da ordem de entrada
   (`entry_order_id`) carregam a escada inteira.
7. Não medido em produção; não commitado.

## T4.61c — os cinco achados da revisão, fechados (18/09/2026)

Revisão: `.claude/state/review-T4.61b.md` (veredito SAFE off com A1; não ligar antes de A2, A4,
A5, A9). Tudo fechado; nada commitado; `.env`, VPS e `uv.lock` intocados.

- **A1 — leitura guardada, custo zero desligada.** `conviction_read.conviction_for` devolve
  `ConvictionOutcome`: flag off ⇒ **nenhuma consulta, nenhuma escada** (`{enabled: false,
  evaluated: false}`; a sombra da T4.61b saiu — medir exige ligar). On ⇒ `asyncio.timeout(3 s)` +
  `try/except` no molde de `read_creator_flow`; timeout/erro ⇒ log, `read_failed` na ordem e o
  degrau `drop` recusa `entry_after_drop_unknown`. Nunca sobe para `entries_once`.
- **A2 — uma foto pós-queda não passa.** O degrau `drop` reutiliza `recent_drawdown` (EXP-M13,
  `hunter_indicators.meme.drawdown`) sobre as fotos guardadas da janela de 60 s (`received_at ≤ now`)
  **mais** a leitura `confirmed` desta admissão como ponto mais novo; menos de duas fotos guardadas
  ⇒ `too_few_points`/`no_observation` ⇒ **recusa** `entry_after_drop_unknown`. `peak_unknown` (× 0,5)
  e `MEME_CONVICTION_PEAK_UNKNOWN_MULT` deixaram de existir (A3 decidido pela revisão: fail closed).
- **A4 + A9 — a escada entrou no motor.** `hunter_risk_meme.conviction` (novo, 128 linhas):
  `MemeConviction` (insumo: `enabled`, `multiplier`, `sol_sized`, `refusal`, `detail`), check 26
  `conviction` (último da lista; `off` passa) e teto `conviction` em `CAP_ORDER` logo depois de
  `trade_cap` (limita só quando a escada permite um tamanho admissível; recusa ⇒ `sol = null`, os
  25 checks medem o tamanho cheio). `evaluate_meme_entry(..., conviction=None)`. Resultado:
  `binding_constraint = conviction` numa compra descontada com `sizing.requested_sol` = pedido da
  mesa; recusa da escada ⇒ `approved = false`, `first_refusal` nomeado, `reason` da ordem = o mesmo.
  `entries.py` perdeu o `if ladder.refusal` e o `apply_ladder`; `AdmissionInputs.conviction`.
  `REFUSAL_NAMES` += `entry_after_drop`, `entry_after_drop_unknown`, `conviction_too_low`,
  `conviction_too_small` (a tabela §4 exige um caso para cada — `test_checks_table.py`).
- **A5 — `MEME_MIN_TRADE_SOL` existe.** `limits_from_env`: opcional, padrão **0,02 SOL** no perfil
  live (paper mantém 0,001); ilegível/≤ 0/acima do `MEME_MAX_SOL_PER_TRADE` ⇒ `MemePolicyMissing`
  pelo nome. `effective_limits` puxa o piso para `small_test.max_sol_per_trade` quando o escopo é
  menor (senão o boot quebraria por `min_trade_sol > max_sol_per_trade`). O motor recusa
  `conviction_too_small` quando `sol_sized < min_trade_sol` (0,07 × 0,25 = 0,0175 **não sai**).
- **Carência.** `refusal_cooldown.SHORT_COOLDOWNS = {entry_after_drop: 30 s}` (limitada pelo
  cooldown do dono; `cooling_mints_by_window`; a consulta passou a trazer `received_at`).
  `entry_after_drop_unknown` e `conviction_too_low` não colam.
- **Arquivos.** Motor: `packages/risk-core/hunter_risk_meme/{conviction.py (novo), sizing.py,
  evaluate.py, checks.py, limits.py, __init__.py}`. Executor: `hunter_meme_executor/{conviction.py
  (262, reescrito), conviction_config.py (novo, 134 — `ConvictionConfig` saiu do `conviction.py`
  para caber), conviction_read.py (188), entries.py, admission.py, config.py, refusal_cooldown.py}`.
  Docs: `docs/RISK_ENGINE_MEME.md` §4 (linha 26), §5, §17; `docs/ACTIVATION.md` 9f;
  `obsidian/11-KNOWLEDGE/KB-0137`.

### Provas

- `uv run pytest services/meme-executor/tests packages/risk-core/tests -q -p no:cacheprovider -m
  "not live"` → ver o relatório da T4.61c (o executor com Docker, ~2,5 min). Unidade:
  `packages/risk-core/tests` **394 passed** (+ `test_conviction_input.py`, 23 novos: A4 binding,
  empate, A9 por nome × 3, tamanho cheio na recusa, A5 pó, piso exato, precedência, off byte a byte,
  `MEME_MIN_TRADE_SOL` × 5); `services/meme-executor/tests/test_conviction.py` **45 passed** (cada
  degrau; A2 uma foto/nenhuma/recebida tarde/duas bastam/leitura falha; A4; A9 × 3; A5 0,0175 sob
  0,02 e sob 0,001; A1 off sem sessão, exceção, timeout; carência × 4).
- `ruff check` / `ruff format --check` em `packages/risk-core` e `services/meme-executor`: limpos.
  `pyright` nos 12 arquivos tocados: 0 erros. `check_file_size.py`: 971 arquivos, 0 acima
  (`limits.py` está em **350** exatas — próximo toque ali precisa de poda).

### Ressalvas

1. **`hunter_indicators` importado pelo executor sem constar no `pyproject.toml`** do
   `services/meme-executor` (mesmo precedente do `meme-worker`; a imagem instala `--all-packages`).
   Não toquei no `pyproject`/`uv.lock` para não forçar re-lock; declarar a dependência é um
   commit à parte.
2. **O piso de 0,02 SOL muda o caminho com a flag desligada**: tetos entre 0,001 e 0,02 (participação
   de moedas com < 2 SOL/min de volume orgânico, restante de escopo, disponível) passam a recusar.
   É política do Everton — se ele quiser o de antes, `MEME_MIN_TRADE_SOL=0.001` no `.env`.
3. **Testes de integração ajustados**: `POLICY` de `test_live_persistence.py` ganhou
   `MEME_MIN_TRADE_SOL=0.005` (os cenários compram 0,01); `test_config_boot` prova o piso seguindo o
   escopo de 0,01; a contagem de checks na recusa do kill switch é 26.
4. A sombra da T4.61b (escada calculada com flag off) **saiu** por A1 — o custo zero foi a escolha do
   brief. Sem ela, a única medição é com a flag ligada.
5. Não medido em produção; não commitado.
