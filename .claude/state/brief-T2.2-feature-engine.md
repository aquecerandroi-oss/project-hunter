# Brief T2.2 — `hunter_indicators.features` (Feature Engine v1)

**Owner:** quant-engineer (opus). **Revisores depois:** outro quant-engineer (cruzado), code-reviewer, Astra (`bash infra/scripts/astra.sh ask T2.2-features "..."`). **Não commitar** — o orquestrador commita após revisar `git diff --stat`.

## Leia antes (nesta ordem)
1. `CLAUDE.md` (regras duras, comandos canônicos, ≤ 350 linhas, TDD, Decimal/UTC, sem look-ahead).
2. `docs/plans/M2.md` — a linha **T2.2** e a seção **"Decisão conjunta Claude ⇄ Astra (2026-09-05)"** (prevalece): ATR de Wilder com inicialização de origem reproduzível ou checkpoint persistido (sem reseed a cada janela móvel), `spread_pct` em **fração**, envelope por amostra, `FeatureVector` com `ts` e `quality`, sufixo `_live` para o candle em formação, scanner nunca chama REST.
3. `docs/PIPELINE.md` §2 (features, fórmulas, cadências) e `docs/ARCHITECTURE.md` §6.
4. O que já existe e deve ser reaproveitado, não duplicado: `packages/core/hunter_core/strategies/{aggregate,indicators,numeric}.py` (agregação 1 m→5 m/15 m sem janela reduzida, Wilder ATR `wilder_atr` com seed/âncora, `CONTEXT` decimal) e `.claude/state/notes-S1.md` §3 (a política `rolling_window_v1` da S1 é declaradamente diferente do checkpoint contínuo que você vai implementar — as duas calculadoras têm nomes diferentes e nenhuma alega ser a outra; registre a relação em `notes-T2.2.md`).
5. Hot state (fonte do `MarketContext`): `packages/core/hunter_core/redis/keys.py` e os contratos exatos em `services/market-worker/hunter_market_worker/{hot_state,hot_state_candles,coalesce}.py` (ticker hash, book msgpack snapshot top-20, trades lista newest-first, candles 1m lista newest-first com `is_final`, `deriv` hash com `mark_ts/oi_ts/funding_ts`), `packages/core/hunter_core/domain/market.py`.
6. `packages/indicators/` (pacote existe com `pyproject.toml`; veja o que há e siga o padrão dos outros pacotes).
7. `.claude/rules/astra-second-opinion.md` — opinião da Astra sobre `MarketContext`/`FeatureVector`/`quality` ANTES de implementar e sobre o diff antes de reportar.

## Entregar (arquivos permitidos: `packages/indicators/hunter_indicators/features/**`, `packages/indicators/tests/**`, `packages/indicators/pyproject.toml`, `.claude/state/notes-T2.2.md`)
- `MarketContext` carregado do hot state (função de carga pura sobre bytes/dicts já lidos: o IO fica em uma função fina e testável com fakes; nunca REST): 1500 candles 1 m (finais + o em formação separado), book top-20, trades recentes, deriv, BTC de referência; cada entrada com `ts` e disponibilidade.
- `FeatureDefinition` (`key`, `category` = `FeatureCategory` existente, `inputs`, `version`, `params`), registry, `feature_set_version` = hash ordenado das definições (canônico como `hunter_core.strategies.canonical`).
- Calculadoras v1: `return_1m/5m/15m/1h`, `volume_relative`, `volume_acceleration`, `trade_velocity`, `volatility` (ATR% de Wilder com checkpoint/origem declarada), `momentum`, `momentum_acceleration`, `spread_pct` (fração, nunca ×100), `orderbook_imbalance`, `buy_pressure`/`sell_pressure`, `open_interest_change`, `funding_rate`, `funding_change`, `breakout_strength`, `distance_from_high/low`; versão `_live` das que dependem do candle em formação.
- `FeatureVector` (`market`, `ts`, `feature_set_version`, valores `Decimal` na borda, `quality` por feature: `ok|degraded|unavailable` com motivo e idade das entradas).
- polars/numpy no miolo (janelas), `Decimal` na borda; nenhuma feature usa dado com `ts > vector.ts`; candle não-final só entra nas `_live`.
- Testes: cada feature com série sintética e valor esperado calculado à mão (em Decimal); anti-look-ahead (alterar candle futuro ou o em formação não muda a feature não-`_live`); propriedade (hypothesis) de invariância a candle não-final; `quality` degrada com entrada velha/ausente; `feature_set_version` estável e muda quando uma definição muda; `spread_pct` em fração; carga do hot state com fakes exatos dos contratos.

## Regras
TDD; nada fabricado; ≤ 350 linhas por módulo. Comandos: `uv sync --all-packages`, `uv run pytest packages/indicators -q`, `uv run ruff check packages/indicators`, `uv run ruff format --check packages/indicators`, `uv run pyright packages/indicators`, `uv run python infra/scripts/check_file_size.py`. PATH: prefixe `/c/Users/evert/AppData/Local/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe:/c/Users/evert/.local/bin:/c/Program Files/nodejs`. Não toque em `.env*`, não commite, não altere arquivos fora da lista (T2.1 está em voo em `packages/core` e migrações; S2 em `services/**`). Se `uv.lock` mudar por dependência nova do pacote, diga no relatório.

## Relatório final (em português)
COMPLETED · FILES CREATED · FILES MODIFIED · DATABASE CHANGES (nenhuma) · TESTS · TEST RESULTS (saída real) · MOCKS REMAINING · BUGS · SECURITY ISSUES · Segunda opinião (Astra) · NEXT STEP.
