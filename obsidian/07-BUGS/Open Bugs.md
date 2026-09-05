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

## Adiados na revisão de T1.5b (2026-09-05) — nenhum bloqueia o commit

Achados reais, com cenário, que ficaram fora do escopo de polimento de UI e foram empurrados para o **M2**. Origem: `.claude/state/review-T1.5b.md` (duas rodadas: `code-reviewer`, `security-reviewer`, Astra/GPT-6 e QA visual).

- **Testes de hidratação de verdade não existem.** `tests/appearance-form.test.tsx` e `tests/motion-showcase.test.tsx` só afirmam o estado **depois** dos efeitos, então **passariam com o bug antigo** (Astra verificou linha a linha). Os mismatches H1/M1/S2 foram corrigidos no código e `tests/use-density.test.tsx` registra o primeiro render — mas cobrir a família toda exige um harness de SSR + hidratação no Vitest. **Dono:** infraestrutura de teste, M2.
- **jsdom não faz layout, então "visível" nunca é medido.** `use-arrow-key-row-selection` e `use-virtualized-rows` provam a aritmética, não a visibilidade física da linha. Fica para o E2E de Playwright do M2.
- **Sem tier de rate limit próprio para o servidor web na API.** Toda a renderização SSR compartilha o balde de 120/min por IP; o lado cliente foi contido (mínimo de 2 caracteres, debounce de 250 ms, `q` limitado a 64), o lado servidor não. **Dono:** `apps/api`, M2. Origem: `security-reviewer`.
- **Tooltip por componente no badge de qualidade** ("qual componente está atrasado") e **explicação do ponto de status acessível por toque no mobile** — as duas precisam de uma superfície de tooltip acessível por toque que a UI ainda não tem. M2.
- **Frescor vs conexão no Live Status:** a tela pode dizer `CONNECTED` com eventos velhos. Depende de um campo de idade por exchange que a API ainda não expõe. M2.
- **Reestruturar o modelo de scroll do `thead` fixo / adotar biblioteca de virtualização.** O sintoma concreto (H4) era aritmética e foi corrigido; a reestruturação é mudança de arquitetura. M2.
- **Layout dos trades a 1024 px com a sidebar aberta** — suspeita da Astra por inferência, sem medição em navegador. Sem cenário provado, sem correção. M2, junto do E2E.
- **QA interativo do command palette nunca rodou.** Dois dev servers concorrentes sobre o mesmo `apps/web/.next` deixaram a página da 3000 sem carregar JavaScript nenhum (`/_next/static/chunks/main-app.js` → 404); encerrar processos era bloqueado pela política daquela sessão. O comportamento está provado por Vitest e por screenshots estáticos, **não** por interação real. Vale repetir num ambiente limpo.

### Aprendizado de processo registrado

`pnpm lint` + `typecheck` + Vitest **não substituem o build de produção**. A T1.5b passou nos três com o `next build` quebrado (`Only async functions are allowed to be exported in a "use server" file`), porque o Vitest não aplica as restrições do Next App Router. **`docker compose -f infra/docker/docker-compose.yml build web` é obrigatório no aceite de qualquer tarefa de `apps/web`.**

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
