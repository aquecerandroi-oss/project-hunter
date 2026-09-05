---
tags: [bugs, abertos]
updated: 2026-09-05
---

# Open Bugs

Levantado de `.claude/state/milestone.json` (histórico de M0) e `docs/SECURITY.md`. Nenhum destes bloqueia o fechamento do M0 — foram conscientemente registrados como conhecidos em vez de resolvidos, mas continuam abertos.

## Rastreados desde o fechamento do M0

- **`packages/core/tests/unit/test_logging.py` — erros de pyright strict.** Ficou pendente depois da onda 5; `.claude/state/milestone.json` registra que passou a ser tratado como KNOWN ISSUE em vez de item de resume-checklist. Não corrigido até 2026-09-05.
- **Isenções em `forbidden_patterns.sh`** (o gate de CI que falha em `sqlite`, `localhost` fora de dev/teste, escrita de JSON de estado, `print(` em produção) — mesma origem, ainda não revisado.
- **Isenção de nome de arquivo "bare" em `enums.py`** — mesma origem, ainda não revisado.

## Limitação de segurança aceita conscientemente (M0), a resolver no M1

- **JWT sem claim `azp` é aceito sem verificação de origem** (`auth/clerk.py`, `JwtAuthProvider.verify`). A allowlist de origem só compara quando o token traz `azp`; um token sem esse claim passa sem checagem. No M0 há um único cliente (`apps/web`), então a exposição prática é baixa, mas a decisão foi registrada como aceita apenas para o M0 — `docs/SECURITY.md` §1 marca isso explicitamente "rastreado para o M1", quando `azp` passa a ser obrigatório.

## Contradição encontrada durante a escrita desta base

`.claude/state/milestone.json` (wave 6, T13) afirma que `docs/reports/M0.md` foi escrito e que "Everton approves the close" com base nele — mas **o arquivo `docs/reports/M0.md` não existe no repositório**. O relatório de fechamento do M0 (formato §77) parece não ter sido persistido, apesar de o estado do milestone dizer que foi. Vale confirmar com quem fechou o M0 se o relatório existe em outro lugar ou se precisa ser reescrito.

## Relacionadas

[[Resolved Bugs]] · [[System Overview]]

## Fontes

`.claude/state/milestone.json`, `docs/SECURITY.md` §1

## Abertos em 2026-09-05
- ~~Banco local com coluna antiga em `processed_events`~~ — corrigido em 2026-09-05 (rename `processed_at → claimed_at`, `completed_at` criada, índices renomeados) a pedido do dono.
- **Codex (Astra) no Windows não funciona com sandbox**: `read-only`/`workspace-write` bloqueiam até leitura de arquivos ("blocked by policy"). Decisão do dono: rodar sem sandbox com controles compensatórios (`infra/scripts/astra.sh`).
- **Limite mensal de gasto da Anthropic** derruba especialistas no meio da tarefa (429). Mitigação: Astra assume tarefas mecânicas; dono avalia aumentar o limite.
- **Agentes personalizados e MCP do Obsidian só carregam em sessão aberta dentro de `C:\dev\project-hunter`**; sessão nascida fora não os vê.

## Abertos na revisão de T1.4/T1.5 (2026-09-05)

- **`last_price` no hash quente carrega o timestamp do `bookTicker`, não o do último trade.** `parse_book_ticker` (`packages/exchange-adapters/hunter_exchanges/binance/streams.py`) carimba o preço do último `aggTrade` em cache com o horário de evento do `bookTicker`, e `write_ticker` (`services/market-worker/hunter_market_worker/hot_state.py`) grava um único `ts` no hash `mkt:*:ticker`. Cenário de falha: o canal de trades para, book e `bookTicker` continuam; `GET /api/v1/markets` devolve o preço antigo com `last_update` recente e o mercado fica `ok`. O payload de tempo real **já** separa `price_ts` e `book_ts` (`ingest.py::build_tick_payload`) e a tela de T1.5 usa `price_ts` corretamente — o buraco é só no caminho REST/hot state. **Dono:** T1.2/T1.3. **Fix:** levar `price_ts` para o hash e expor a idade do preço separada da idade da cotação em `components.ticker`.
- **`apps/api/tests/integration/test_webhook.py::test_a_crash_where_even_the_release_never_runs_still_recovers_after_the_stale_window` falha.** A suíte de `apps/api` estava 428/0 e passou a 445/1 depois que a T1.3 acrescentou `command_timeout: 30` engine-wide em `packages/core/hunter_core/db/session.py`. Falha também isolada (`uv run pytest apps/api/tests/integration/test_webhook.py -q` → 1 failed, 16 passed), então não é ordem de teste. **Dono:** T1.3 (`packages/core`). Nenhum arquivo de T1.4/T1.5 está envolvido.
- **Índice do git compartilhado entre duas sessões.** Com duas instâncias trabalhando no mesmo repositório, `git add` de uma aparece no `git diff --cached` da outra; um `git commit` sem pathspec varreria trabalho alheio. Contorno usado: `git commit -- <caminhos>`, que commita a árvore de trabalho só daqueles caminhos e não toca o resto do índice.
