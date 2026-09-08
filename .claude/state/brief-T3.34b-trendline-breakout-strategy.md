# Brief T3.34b — `trendline_breakout_v1`: rompimento de linha de tendência (15 m), `research_only`

**Owner:** quant-engineer. **Reviewers:** `code-reviewer`, Astra, e `risk-engine-guardian` só se
alguém propuser mexer em `base.py`/`aggregate.py` (não deveria).
**Do not commit without the operator's word. Nothing here activates anything and nothing reaches the wallet.**
**Operational rules:** never a background shell; foreground commands with a timeout <= 5 min; the tree is
shared — never `git stash`/`checkout --`/`restore`/`reset`/`clean`/`commit -a`; add exact files only;
do not touch `.env*`; VPS read-only.
**Base:** a primitiva da T3.34 (`packages/indicators/hunter_indicators/patterns/**`), as notas em
`.claude/state/notes-T3.34.md` e a página `.claude/state/exp-drafts/KB-0077-linhas-de-tendencia.md`.

---

## 0. Leia isto antes de escrever uma linha: onde o código da geometria pode morar

A T3.34 entregou a geometria em `hunter_indicators.patterns`. **Uma estratégia de
`hunter_core.strategies` não pode importá-la**, e a razão não é estilo:

1. **ciclo de distribuição.** `hunter-indicators` depende de `hunter-core`
   (`packages/indicators/pyproject.toml`); o caminho inverso não existe. `hunter_indicators.patterns`
   importa `hunter_core.strategies.aggregate` e `...numeric`, então um import de volta fecha o ciclo
   em tempo de importação — não só na declaração de dependência;
2. **pior: o `code_ref` deixaria de cobrir o cálculo.**
   `hunter_strategy_worker.code_ref.module_closure` fecha **apenas** sobre módulos irmãos planos de
   `hunter_core.strategies` (`_sibling` recusa até subpacote: *"the digest covers flat sibling
   modules only"*). Um import de `hunter_indicators` sairia **fora** do digest: a versão ficaria
   congelada com um hash que continua igual enquanto a geometria que produz as decisões dela muda.
   Essa é a única direção em que o congelamento nunca pode falhar.

Três opções, e a recomendação:

| opção | o que é | custo | veredito |
|---|---|---|---|
| A | a estratégia importa `hunter_indicators.patterns` | ciclo + geometria fora do digest | **recusar** |
| B | `PatternScan` entra no `MarketContext` (`hunter_core/strategies/base.py`) | `base.py` está no fecho de `momentum_v1` **e** de `volume_anomaly_v1`: editá-lo re-congela as duas versões vivas e o Lab emudece atrás de um `/ready` verde | **recusar nesta task** (é uma migração coordenada, com reativação, e merece brief próprio) |
| C | portar a geometria para **módulos irmãos planos** em `hunter_core/strategies/` (`trendline_geometry.py`, e o que não couber em 350 linhas em `trendline_geometry_events.py`), com teste de **paridade numérica** contra `hunter_indicators.patterns` | duplicação de código, controlada por teste | **recomendada** |

A opção C tem precedente escrito no próprio repositório: já existem dois ATR
(`hunter_indicators.features.atr` ancorado vs `hunter_core.strategies.indicators.rolling_window_v1`)
e o docstring do primeiro registra que são políticas diferentes de propósito. A diferença aqui é que
**os números têm de ser os mesmos**, e é isso que o teste de paridade cobra:

> `packages/core/tests/unit/strategies/test_trendline_geometry_parity.py`: para 3 séries fixas
> (o `wave` sintético da T3.34 e duas fatias reais salvas como CSV de teste), `find_pivots`,
> `find_lines`, `find_channels` e `detect_events` das duas implementações devolvem **exatamente** os
> mesmos índices, preços (`Decimal`, igualdade exata) e eventos. Se divergirem, a errada é a cópia.

Quem escrever a T3.34b decide entre C e "pedir a B ao orquestrador"; **não invente a A**.

## 1. O que a estratégia é

Long-only, `research_only`, 15 m. Duas portas de entrada, mutuamente exclusivas na mesma barra
(prioridade: rompimento primeiro):

- **`breakout`** — fechamento acima de uma **resistência descendente válida**
  (`slope_per_bar < 0`, `touches >= min_touches`) por mais de `break_atr`, com
  `relative_volume >= rvol_min`;
- **`bounce`** — repique confirmado numa **suporte ascendente válida** (`slope_per_bar > 0`):
  o extremo tocou a linha dentro de `tolerance_atr` e o fechamento se afastou `bounce_atr`.
  Sem exigência de volume (um repique é continuação, não expansão).

A linha tem de estar **válida no corte** (`valid_from_idx <= barra do corte`) e — decisão nova, e é
a correção nº 1 da KB-0077 — **não pode estar aposentada**: se já houve rompimento dela antes desta
barra e a janela de reteste passou, a linha não serve mais de gatilho. Implemente
`retire_after_break` como parâmetro (`True` por padrão) **na cópia de C**, não na T3.34
(mudar a T3.34 mudaria as figuras já publicadas).

## 2. Identidade

```
strategies.key   = "trendline_breakout"
version          = "v1"
registry key     = "trendline_breakout_v1"
module           = packages/core/hunter_core/strategies/trendline_breakout_v1.py   (<= 350 linhas)
timeframe        = Timeframe.M15
direction        = LONG only
purpose          = research_only
```

Nova linha em `infra/scripts/seed_reference.py` (a chave ainda não existe), `registry.py`
(+2 linhas) e `constraints.py` (+1 entrada) — os três estão **fora** do fecho do digest das versões
vivas e podem ser editados.

**Teste de aceitação obrigatório**, igual ao da T3.33a: depois da mudança,
`version_code_ref("momentum_v1") == "hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c"`
e
`version_code_ref("volume_anomaly_v1") == "hunter_core.strategies.volume_anomaly_v1@sha256:9b8c14ab3390646ac9adb26fbbb90e160a800f1c70f128d873a49ffd1dd19f22"`.
Se algum se mover, a mudança está errada, não o teste.

## 3. A regra de entrada, exatamente

Avaliada em todo fechamento distinto de 15 m, nesta ordem; indisponibilidade é sempre
`UNAVAILABLE`, nunca "condição falsa", para o worker não re-armar o mercado numa barra que não
conseguiu avaliar.

0. `not ctx.eligible` → `INELIGIBLE / "ineligible"`.
1. **Janela.** `aggregate(ctx.candles_1m, M15, ctx.source_bar_close, bars_needed)` com
   `bars_needed = max(pattern_bars, rvol_window + 1, atr_bars)`. Indisponível → `UNAVAILABLE / window.reason`.
   `pattern_bars` (padrão **96**, 24 h) é a janela em que a geometria é procurada.
2. **ATR** — mesmo contrato de `momentum_v1`/`breakout_v1` (`wilder_v1`, 14, 15 m, 97 barras);
   `UNAVAILABLE / "atr_warmup"` etc.
3. **Varredura.** `scan(bars, as_of=len(bars)-1)` da cópia de §0-C, com os parâmetros de §5.
   Sem linha válida → `NOT_TRIGGERED / "no_line"`, com `{"pivots": n}` no envelope.
4. **Gatilho.** Um evento `breakout` **nesta barra** numa resistência descendente, ou um `bounce`
   **nesta barra** numa suporte ascendente. Nenhum → `NOT_TRIGGERED / "no_event"`.
5. **Volume** (só no `breakout`): `relative_volume(bars, rvol_window) >= rvol_min`, senão
   `NOT_TRIGGERED / "rvol_low"`; `None` → `UNAVAILABLE / "rvol_unavailable"`.
6. **Qualidade da linha:** `touches >= min_touches_signal` (padrão 3) e `violations <= max_violations`
   (padrão 0 no rompimento, 2 no repique), senão `NOT_TRIGGERED / "line_weak"`.
7. **Piso de custo:** `atr_pct_min <= atr_pct <= atr_pct_max`, senão `NOT_TRIGGERED / "atr_out_of_range"`.

## 4. Geometria, invalidação, horizonte

```
reference   = close(t)
stop        = min(low do último pivô de baixa confirmado, reference - stop_atr_max * atr)
              # o stop é ESTRUTURAL; o teto em ATR só impede um stop absurdo
risk        = reference - stop
target1     = reference + max(channel_width, target_r * risk)     # channel_width = width_atr * atr
              # sem canal: reference + target_r * risk  (target_r padrão 2.0)
invalidations = (Invalidation(kind="close_below", level=line.projected(t), timeframe="15m"),)
horizon_s   = 28800        # 8 h
```

**A invalidação é a linha, não o momentum.** É o ponto que separa esta versão de `momentum_v1`:
o preço voltar a fechar **abaixo da resistência rompida** desmente a tese inteira, e é um nível
*estrutural* — tem de ficar estritamente entre o stop e a referência.

Três guardas, todas `REJECTED` (a condição valeu, a decisão foi recusada — o mercado **não** re-arma):

- `not 0 < stop < reference < target1` → `REJECTED / "geometry"`;
- `not stop < invalidation_level < reference` → `REJECTED / "geometry_invalidation"`;
- `risk <= 0` ou `risk > max_risk_atr * atr` (padrão 3,0) → `REJECTED / "risk_too_wide"` — o pivô de
  baixa mais recente pode estar longe demais, e um stop de 6 ATR transforma qualquer alvo em piada.

**Reportar, não supor:** o replay do primeiro dia tem de publicar quantas barras morrem em
`risk_too_wide` e em `geometry_invalidation`. Acima de 20% das barras que de outro modo dispararam,
o par (pivô estrutural, teto de risco) está errado — e isso é **versão nova**, não ajuste.

## 5. Parâmetros (`default_parameters`, congelados; nada fixo no caminho do código)

| nome | padrão | faixa proposta para varredura | descrição |
|---|---|---|---|
| `pattern_bars` | 96 | 64–192 | barras de 15 m em que a geometria é procurada |
| `pivot_k` | 3 | 2–5 | confirmação do pivô |
| `min_swing_atr` | `Decimal("1.0")` | 0,5–2,0 | proeminência mínima do pivô |
| `min_touches` | 3 | 3–4 | toques para a linha valer |
| `min_touches_signal` | 3 | 3–5 | toques exigidos da linha que dispara |
| `tolerance_atr` | `Decimal("0.25")` | 0,15–0,40 | "na linha" |
| `break_atr` | `Decimal("0.5")` | 0,3–1,0 | fechamento além da linha |
| `bounce_atr` | `Decimal("0.5")` | 0,3–1,0 | afastamento que confirma o repique |
| `retest_bars` | 10 | 4–16 | janela de reteste (usada por `retire_after_break`) |
| `bounce_bars` | 3 | 2–5 | janela de confirmação do repique |
| `max_violations` | 0 / 2 | 0–3 | violações toleradas (rompimento / repique) |
| `retire_after_break` | `True` | — | linha rompida deixa de servir de gatilho |
| `rvol_window` | 96 | 48–192 | janela do volume relativo |
| `rvol_min` | `Decimal("1.5")` | 1,2–2,5 | volume relativo mínimo do rompimento |
| `atr_period` / `atr_timeframe` / `atr_bars` | 14 / `"15m"` / 97 | — | mesmo contrato das outras versões |
| `atr_pct_min` / `atr_pct_max` | `Decimal("0.005")` / `Decimal("0.05")` | — | piso e teto de custo (o piso é o mesmo de `breakout_v1`, pela KB-0008) |
| `stop_atr_max` | `Decimal("2.0")` | 1,5–3,0 | teto do stop estrutural, em ATR |
| `max_risk_atr` | `Decimal("3.0")` | 2,0–4,0 | risco máximo aceito |
| `target_r` | `Decimal("2.0")` | 1,5–3,0 | alvo mínimo em múltiplos de risco |
| `horizon_s` | 28800 | 14400–43200 | permanência esperada |
| `base_confidence` | `Decimal("0.5")` | — | constante não calibrada |
| `assumed_spread_bps` / `slippage_bps` / `fee_bps` | 2 / 5 / 4 | — | custos assumidos, iguais aos das outras |
| `max_entry_delay_s` | 120 | — | atraso máximo até a barra de entrada |

**Suposições numéricas declaradas (nenhuma medida):** todos os padrões de geometria vêm do brief da
T3.34 e da prática clássica; `target_r = 2,0` é convenção; `max_risk_atr = 3,0` é escolhido para que
o custo assumido de 20 bps não passe de ~15% de 1 R no piso de ATR. A faixa "para varredura" da
tabela é para o EXP, **não** para ajustar durante a implementação.

## 6. Orçamento de janela

`bars_needed <= 97 × 15 min = 1455 min <= SHADOW_CONTEXT_MINUTES (1560)`. Teste obrigatório
afirmando isso com os padrões congelados. `aggregate()` exige **todo** minuto da janela: um minuto
faltando torna a janela inteira `gap`.

## 7. Envelope (`SupportingFeatures`)

Tudo que a decisão usou, para reproduzir depois que as velas de 1 min saírem da retenção:
`close_15m`, `atr_pct_15m` + `AtrEvidence`, `relative_volume_15m`, `volume_median_15m`,
e o **desenho**: `line_kind`, `line_id`, `line_slope_per_bar`, `line_touches`, `line_violations`,
`line_first_idx`/`line_last_idx`/`line_valid_from_idx`, `line_price_at_decision`,
`event_kind`, `event_distance_atr`, `pivot_low_price` (o do stop), `channel_width_atr` (ou nulo),
`pattern_params` (o `as_wire()` inteiro) e `assumed_costs(params)`.

O `line_id` no envelope é o que permite, depois, juntar sinais que dispararam **na mesma linha**.

## 8. Testes — série sintética com valor conhecido

Em `packages/core/tests/unit/strategies/test_trendline_breakout_v1.py`, reaproveitando
`strategies/conftest.py` e a onda sintética da T3.34 (`packages/indicators/tests/patterns/builders.py`
é o modelo; copie o gerador, não importe do outro pacote em código de produção):

1. **dispara** no rompimento: assert direção, `reference_price`, `stop` (= mínima do último pivô),
   `target1`, nível de invalidação, `reason` e o envelope inteiro;
2. **dispara** no repique de suporte ascendente;
3. **não dispara**, um ramo por vez, com o par `(state, reason)` exato: `no_line`, `no_event`,
   `rvol_low`, `line_weak`, `atr_out_of_range`, `ineligible`;
4. **indisponível:** `warmup`, `gap` (um minuto removido do meio), `atr_warmup`, `rvol_unavailable`;
5. **recusado:** `geometry`, `geometry_invalidation`, `risk_too_wide`;
6. **linha aposentada:** a mesma série com o rompimento 20 barras atrás não dispara de novo
   (`retire_after_break`);
7. **sem antecipação (é o ponto do desenho todo):** contexto com (a) vela não-final na janela,
   (b) vela final fechando **depois** de `source_bar_close`, (c) vela futura mutada — a `Decision`
   tem de ser **idêntica** nos três (compare o JSON canônico do envelope). Depois mute a vela
   não-final e assert que nada se move;
8. **pureza:** duas chamadas com o mesmo contexto dão decisões iguais; o módulo não importa
   `datetime.now`/`time`/`redis`/`sqlalchemy`;
9. **paridade da geometria:** o teste de §0-C;
10. **isolamento do digest:** as duas asserções de §2;
11. **`constraints.check_ranges`** recusa `min_touches = 1`, `break_atr = 0`, `target_r = 0`,
    `atr_pct_min > atr_pct_max`, `base_confidence = 42`, `stop_atr_max > max_risk_atr`;
12. **orçamento de janela:** §6.

## 9. Protocolo de replay e EXP (igual ao das outras versões novas)

1. Escreva `.claude/state/exp-drafts/EXP-00xx-trendline-breakout.md` com a hipótese **congelada**
   antes de qualquer corrida, e os critérios de morte K1–K5 no mesmo padrão da T3.33 §5.1.
   Hipótese sugerida, em uma frase: *o rompimento de uma resistência descendente com pelo menos três
   toques e volume relativo ≥ 1,5 tem expectancy líquida positiva em 15 m, e a invalidação estrutural
   (fechar de volta abaixo da linha) corta a cauda esquerda melhor do que a invalidação de momentum.*
2. Ativação só pelo operador, `--dry-run` primeiro:
   ```bash
   docker exec -i hunter-api-1 python - trendline_breakout v1 --dry-run \
     --changelog 'T3.34b: rompimento de linha de tendencia, coorte de pesquisa (research_only, sem carteira)' \
     < infra/scripts/activate_strategy_version.py
   ```
3. Replay em **duas fatias com a mesma coorte**, exatamente como a T3.33a:
   ```bash
   docker exec hunter-strategy-worker-1 python -m hunter_strategy_worker.replay.run \
     --version trendline_breakout:v1 --from 2026-08-08 --to 2026-08-23 \
     --markets ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT --workers 3 \
     --cohort replay:<uuid> --ledger /tmp/replay-trendline-v1.jsonl
   # segunda fatia 2026-08-23 -> 2026-09-08, MESMA coorte
   ```
4. Cole o recibo do livro-razão (barras, segundos, barras/s, contagem por estado, sinais, desfechos,
   erros) no EXP e no relatório. Publique **também**, porque é o que esta versão precisa saber:
   linhas válidas por barra avaliada, distribuição de `touches`, fração de rompimentos com reteste,
   e a taxa de `risk_too_wide`.

## 10. Fora de escopo

Carteira, ordens, posições, PnL de portfólio, Risk Engine, SHORT, qualquer edição em `base.py`,
`aggregate.py`, `indicators.py`, `schema.py`, `envelope.py`, `canonical.py`, `numeric.py`, qualquer
mudança em `SHADOW_CONTEXT_MINUTES`, qualquer edição em `hunter_indicators/patterns/**` (as figuras
da T3.34 já foram publicadas com aquela regra), as figuras da T3.35 (cunha, triângulo, bandeira,
OCO) e ativar qualquer coisa por conta própria.
