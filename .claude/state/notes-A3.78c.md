# A3.78c — painel Meta diária

Status: **DONE_WITH_CONCERNS**. Executado em 12/09/2026, Brasília (UTC−3).
Sem commit, deploy, mudança de flags ou acesso a `.env*`.

## RESUMO

- Histórico por intervalo de atividade: `activated_at < fim_do_dia` e `deprecated_at > início_do_dia` ou nulo. A versão que operou durante parte do dia pertence a esse dia; aposentadoria exatamente no início exclui o dia. A consulta de 30 dias filtra novamente a elegibilidade no dia de cada outcome, evitando carregar aposentadas em todos os pontos (`apps/api/hunter_api/repositories/lab_daily_goal.py:115`, `:181`). Não há `superseded_at` no modelo de versões; o campo real é `deprecated_at` (`packages/core/hunter_core/db/models/agents.py:166`).
- Soma por aposta única: cada vencedor da deduplicação conserva seu próprio R e tamanho; funding nulo permanece fora do eixo e tamanho ausente torna o total indisponível, nunca parcial (`apps/api/hunter_api/services/lab_daily_goal_sizing.py:57`).
- Campos aditivos: `real_usdt_summed`, `real_brl_summed`, `summed_reason`, `distance_to_goal_summed_brl`. Os antigos campos por p50 permanecem; a distância somada também é aditiva para não alterar o contrato antigo (`apps/api/hunter_api/schemas/lab_daily_goal.py:73`, `apps/api/hunter_api/services/lab_daily_goal.py:223`). `axis` e `as_of` mantidos. A série `unique_usdt` usa a mesma soma por aposta (`apps/api/hunter_api/services/lab_daily_goal.py:123`).
- Web usa soma como resultado principal, p50 como referência e explica “versões ativas em cada dia”; campos opcionais permitem API antiga sem apresentar a estimativa antiga como soma (`apps/web/components/lab/lab-daily-goal-panel.tsx:44`, `:58`, `:63`, `:115`; `apps/web/lib/api/lab-daily-goal-types.ts:63`). Meta e distância também usam soma (`apps/web/components/lab/lab-daily-goal-format.ts:87`, `:105`).
- Correções demonstradas durante a revisão: a vela deve ter fechado na entrada (`apps/api/hunter_api/repositories/lab_daily_goal.py:223`); quando o orçamento de risco limita o tamanho, usa-se diretamente esse orçamento, evitando dividir e multiplicar pela distância e deixar resíduo decimal (`apps/api/hunter_api/services/lab_daily_goal_sizing.py:125`).
- O teste de integração foi reduzido a 350 linhas reutilizando `lab_fixtures.build_shadow_signal` e centralizando a leitura HTTP; os sete cenários continuam passando (`apps/api/tests/integration/test_lab_daily_goal_api.py:48`, `:96`, `:280`).

## ARQUIVOS

Somente os paths do brief. Lista `git status --porcelain` ao final desta nota; inclui todos os arquivos da tarefa, inclusive esta nota e o teste novo. Alterações de terceiros já existentes permaneceram intactas.

## TESTES

Comandos executados via Git Bash, em primeiro plano, com `timeout 290`. Saídas abaixo são trechos reais; tempos de início em Brasília quando apresentados pelo Vitest.

### TDD — vermelho antes da implementação

```text
timeout 290 uv run pytest apps/api/tests/unit/test_lab_daily_goal_bets.py apps/api/tests/unit/test_lab_daily_goal_sizing.py apps/api/tests/unit/test_lab_daily_goal_service.py -q
ImportError: cannot import name 'sum_priced_bets'
1 error in 1.09s

timeout 290 uv run pytest apps/api/tests/integration/test_lab_daily_goal_api.py -q -p no:randomly
KeyError: 'real_usdt_summed'
AssertionError: assert '0' == '-7'
2 failed, 5 passed in 54.41s

timeout 290 pnpm --filter @hunter/web test tests/lab-daily-goal-honest.test.ts
Test Files  1 failed (1)
Tests  3 failed (3)
Start at  02:06:47
Duration  2.74s
```

O segundo passe da integração expôs a soma `-21.99999999999999999999999999` em vez de `-22`; resolvido usando o orçamento exato. O teste adversarial de vela aberta na entrada mostrou `250` em vez de `140` BRL de 1R, antes da correção temporal:

```text
timeout 290 uv run pytest apps/api/tests/integration/test_lab_daily_goal_api.py -q -p no:randomly
AssertionError: assert '250' == '140'
1 failed, 6 passed in 49.36s
```

### Verde — implementação final

```text
timeout 290 uv run pytest apps/api/tests/unit/test_lab_daily_goal_bets.py apps/api/tests/unit/test_lab_daily_goal_sizing.py apps/api/tests/unit/test_lab_daily_goal_service.py -q
.....................................                                    [100%]
37 passed in 0.69s

timeout 290 uv run pytest apps/api/tests/integration/test_lab_daily_goal_api.py -q -p no:randomly
.......                                                                  [100%]
7 passed in 49.74s

timeout 290 pnpm --filter @hunter/web test tests/lab-daily-goal-honest.test.ts tests/lab-daily-goal-format.test.ts
Test Files  2 passed (2)
Tests  30 passed (30)
Start at  02:08:07
Duration  2.42s

timeout 290 npx turbo run typecheck lint test --filter=@hunter/web
@hunter/web:lint: ✖ 2 problems (0 errors, 2 warnings)
@hunter/web:test: Test Files  131 passed (131)
@hunter/web:test: Tests  1229 passed (1229)
@hunter/web:test: Duration  110.59s
Tasks:    3 successful, 3 total
Cached:    0 cached, 3 total
Time:    1m54.141s

timeout 290 uv run python infra/scripts/check_file_size.py
scanned 639 files; 0 over budget, 0 grandfathered

git diff --check -- apps/api apps/web
(sem saída; exit 0)
```

O lint web conserva dois warnings de tamanho em testes fora deste brief (377 e 557 linhas). Nenhum erro web.

### Gates Python sobre os sete arquivos Python da tarefa

```text
timeout 290 uv run ruff check apps/api/hunter_api/repositories/lab_daily_goal.py apps/api/hunter_api/services/lab_daily_goal.py apps/api/hunter_api/services/lab_daily_goal_sizing.py apps/api/hunter_api/schemas/lab_daily_goal.py apps/api/tests/unit/test_lab_daily_goal_sizing.py apps/api/tests/unit/test_lab_daily_goal_service.py apps/api/tests/integration/test_lab_daily_goal_api.py
All checks passed!

timeout 290 uv run ruff format --check apps/api/hunter_api/repositories/lab_daily_goal.py apps/api/hunter_api/services/lab_daily_goal.py apps/api/hunter_api/services/lab_daily_goal_sizing.py apps/api/hunter_api/schemas/lab_daily_goal.py apps/api/tests/unit/test_lab_daily_goal_sizing.py apps/api/tests/unit/test_lab_daily_goal_service.py apps/api/tests/integration/test_lab_daily_goal_api.py
7 files already formatted

timeout 290 uv run pyright apps/api/hunter_api/repositories/lab_daily_goal.py apps/api/hunter_api/services/lab_daily_goal.py apps/api/hunter_api/services/lab_daily_goal_sizing.py apps/api/hunter_api/schemas/lab_daily_goal.py apps/api/tests/unit/test_lab_daily_goal_sizing.py apps/api/tests/unit/test_lab_daily_goal_service.py apps/api/tests/integration/test_lab_daily_goal_api.py
0 errors, 0 warnings, 0 informations
```

Após reduzir o teste de integração, verificados novamente:

```text
timeout 290 uv run ruff format apps/api/tests/integration/test_lab_daily_goal_api.py
1 file left unchanged
timeout 290 uv run ruff check apps/api/tests/integration/test_lab_daily_goal_api.py
All checks passed!
timeout 290 uv run pyright apps/api/tests/integration/test_lab_daily_goal_api.py
0 errors, 0 warnings, 0 informations
```

### Gates globais — não estão verdes

```text
timeout 290 uv run ruff check .
RUF100 [*] Unused `noqa` directive (non-enabled: `S311`)
  --> packages\exchange-adapters\hunter_exchanges\pumpfun\rest.py:87:68
Found 1 error.

timeout 290 uv run ruff format --check .
14 files would be reformatted, 1521 files already formatted

timeout 290 uv run pyright
28 errors, 0 warnings, 0 informations
```

Os 14 paths de formatação externos: `infra/scripts/{backfill_funding,request_backfill}.py`, `infra/scripts/tests/test_request_backfill.py`, `obsidian/02-MARKET/Exchange Adapters.md`, `obsidian/03-TRADING/{Execution Engine,Strategies}.md`, `obsidian/11-KNOWLEDGE/KB-0036-o-tamanho-que-a-sombra-nunca-declara.md`, `packages/core/tests/unit/test_settings.py`, `packages/exchange-adapters/hunter_exchanges/pumpfun/{decode,normalize,rest,ws}.py`, `services/market-worker/hunter_market_worker/funding_announce.py`, `services/market-worker/tests/test_funding_backfill.py`.

Pyright global: erros em `apps/api/tests/integration/test_lab_signals_pagination_api.py:36`, `test_risk_limits_api.py:198`, `infra/scripts/tests/test_render_operations.py:215`, `packages/core/tests/unit/strategies/test_mean_reversion_v1.py:421`, `test_no_lookahead.py:397`, `packages/exchange-adapters/hunter_exchanges/pumpfun/ws.py:147`, `services/strategy-worker/tests/test_replay_drain_pause.py:92`, `test_replay_role_guard.py:59` e `test_replay_stress.py:35`. Nenhum dos 28 aponta para um arquivo desta tarefa. Não corrigidos: fora da lista autorizada, e parte deles está em diretórios expressamente proibidos pelo brief.

## MUST-FIX

Nenhum achado funcional aberto no diff desta tarefa. A aprovação global continua impedida pelos gates externos acima: rodar os gates canônicos sobre a árvore completa retorna exit 1.

## NICE-TO-HAVE

Medir o custo da consulta de 30 dias com o catálogo histórico real, agora maior. O teste EXPLAIN é sobre fixture pequena, não uma medição de produção (`apps/api/tests/integration/test_lab_daily_goal_api.py:157`). Nenhuma consulta de produção foi executada nesta tarefa.

## O QUE EU FARIA DIFERENTE

Em tarefa própria, eliminar o limite herdado de dois dias para buscar emissões: um outcome fechado após retenção superior a dois dias pode ficar fora do dia consultado (`apps/api/hunter_api/repositories/lab_daily_goal.py:61`). A soma continua um contrafactual com patrimônio de referência do dia e limites por aposta, não uma simulação conjunta da carteira (`apps/api/hunter_api/services/lab_daily_goal.py:246`, `apps/web/components/lab/lab-daily-goal-panel.tsx:69`).

## CONCORDO COM

Preservar compatibilidade aditiva, apurar o histórico pelas versões daquele dia e distinguir soma de estimativa p50. Revisão do próprio diff realizada pela Astra. A tentativa de delegação ao frontend-specialist falhou com `no thread with id`; execução local, sem alegar revisão independente por outro agente.

## OBSIDIAN

- **Strategies** — registrar elegibilidade histórica por ativação/aposentadoria no painel diário.
- **Performance Overview** — documentar soma por aposta, referência p50 e indisponibilidade por tamanho incompleto.
- **Diario/2026-09-12** — registrar A3.78c, verificações e os gates globais externos pendentes.

Páginas não editadas: fora dos paths autorizados neste brief.

## Paths para o orquestrador

Comando: `git status --porcelain -- <os 13 paths abaixo>`

```text
 M apps/api/hunter_api/repositories/lab_daily_goal.py
 M apps/api/hunter_api/schemas/lab_daily_goal.py
 M apps/api/hunter_api/services/lab_daily_goal.py
 M apps/api/hunter_api/services/lab_daily_goal_sizing.py
 M apps/api/tests/integration/test_lab_daily_goal_api.py
 M apps/api/tests/unit/test_lab_daily_goal_service.py
 M apps/api/tests/unit/test_lab_daily_goal_sizing.py
 M apps/web/components/lab/lab-daily-goal-format.ts
 M apps/web/components/lab/lab-daily-goal-panel.tsx
 M apps/web/lib/api/lab-daily-goal-types.ts
 M apps/web/tests/lab-daily-goal-format.test.ts
?? .claude/state/notes-A3.78c.md
?? apps/web/tests/lab-daily-goal-honest.test.ts
```

Registro em Brasília: 2026-09-12 02:19:12 -03:00.
