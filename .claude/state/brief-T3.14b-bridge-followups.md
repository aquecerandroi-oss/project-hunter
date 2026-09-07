# Brief T3.14b — os quatro itens da revisão da ponte, mais a T3.5d (eventos do kill switch)

**Owner:** backend-specialist. **Revisor depois:** risk-engine-guardian. **Não commitar.** **Regra operacional: nunca Bash em background; comandos em primeiro plano com timeout ≤ 5 min; suítes com testcontainers um arquivo por invocação; Astra indisponível até 2026-09-12.** Outro agente está editando `tests/integration/paper/**` — não toque. Base: `main` em `90f1862` (T3.5c commitada).

## Leia antes
`.claude/state/review-T3.14.md` (os quatro itens), `.claude/state/brief-T3.5d-kill-switch-events.md` (inteiro — é parte desta tarefa), `.claude/state/notes-T3.5.md` (seções T3.5b e T3.5c), `.claude/state/notes-T3.14.md` se existir, `services/execution-worker/hunter_execution_worker/{bridge,bridge_screen,bridge_universe,bridge_inputs,mtm,events,cycles}.py`, `docs/plans/M3.md` T3.14, `docs/RISK_ENGINE.md` §5.

## Entregar — parte A (review-T3.14.md)
1. **Dedupe de `bridge_candidate_refused`**: o mesmo candidato recusado pelo mesmo motivo não gera um log/métrica por ciclo (1 s) — uma vez por (sinal, motivo), como o padrão "once-per-row warnings" da T3.5b; teste.
2. **Vários candidatos, nenhuma promoção**: teste com 3 sinais elegíveis no mesmo ciclo e D3 (score > custo em R > chegada, **uma vaga por ciclo**) → exatamente um pedido; os outros dois ficam para o próximo ciclo sem ser recusados.
3. **`agent_unavailable`**: teste do caminho em que o agente da versão não está disponível/ativo → recusa nomeada, sem pedido, sem reserva.
4. **Mapeamento `1000SHIBUSDT` → spot `SHIBUSDT` e preço fora da banda**: o perp `1000SHIBUSDT` cota 1000× o spot; a ponte deve mapear símbolo **e** escala, ou recusar com motivo quando o preço de referência do sinal e o último negócio spot divergem além de `max_entry_deviation_pct` (0,5 %). Teste dos dois casos (mapeado corretamente; fora da banda → recusa). Se o mapeamento de escala não existir, **recuse** (não invente fator) e registre o par como não elegível — a lista de pares elegíveis é a dos ≥ 50 M spot.
5. **Flag com duas fontes**: teste que prova que `ENABLE_PAPER_AUTONOMY` é lida de uma única fonte (settings) e que env/compose divergentes não ligam a ponte por acidente.

## Entregar — parte B (T3.5d, ver o brief)
Um único formato de `kill_switch.changed` (o do core), uma única publicação por transição, e a retomada pela API publicada pelo worker no ciclo de 10 s, idempotente por `transition_id`.

## Provar
`services/execution-worker/tests` por arquivo (todos), `packages/core/tests/integration/test_admission*.py` se tocar em `packages/core/hunter_core/admission/**` (evite), `ruff check`/`format --check`/`pyright` em `services/execution-worker packages/core apps/api`, `check_file_size.py`. Nada em `.env*`, `infra/migrations/**`, `packages/core/hunter_core/risk/**`, `apps/**` (exceto adaptar um consumidor do evento se existir — cite). `docs/PIPELINE.md`: formato único do evento. Relatório em português no formato estendido com saída real; `.claude/state/notes-T3.14.md` (parte A) e `notes-T3.5.md` seção T3.5d (parte B).
