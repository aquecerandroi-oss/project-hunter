# T3.69b — o `execution-worker` passa a ler o perfil da carteira (10/09, BRT). NENHUM limite mudou de valor.

**AVISO AO ORQUESTRADOR, ANTES DO DEPLOY.** Com este código no ar e a carteira da
VPS **ainda sem vínculo** (`portfolios.risk_profile_id` NULL — o Everton não
rodou o `ACTIVATION.md` §8b), a carteira paper passa a admitir **zero** entradas:
manual e ponte autônoma, ambas recusadas com `risk_profile_missing` no log e em
`hb:execution:paper.risk_profile`. É o estado fail-closed pretendido, não uma
falha, e é reversível sem restart (no passo seguinte aos dois comandos do §8b a
mesma carteira volta a admitir). **Saídas de proteção, MTM e kill switch não são
afetados** (regra 3 da diretiva). Deploy consciente: ou os dois comandos vão
junto, ou a carteira fica sem admitir até que vão. Hoje, na prática, ela já não
admite nada por outro motivo (`paper_autonomy=false`, linha 7 do §8).

1. **Onde o número passa a ser lido.** `services/execution-worker/hunter_execution_worker/risk_profile.py`
   (novo): `wallet_limits` lê `portfolios → risk_profiles` (LEFT JOIN, org+portfolio no predicado),
   `resolve_limits` valida em `RiskLimits` e compara campo a campo com `PAPER_V1`. Quatro estados:
   `risk_profile_linked` / `risk_profile_missing` / `risk_profile_invalid` / `risk_profile_diverged`.
   Nos três de recusa: `limits=None`, nada escrito, e **nunca** cai de volta na constante.
2. **Quem aplica.** `admission_cycle.decide_requests` (única porta de entrada — pedido manual e ponte)
   resolve por conta própria quando o chamador não passa `limits`, e devolve `()` sem escrever nada.
   `cycles.admission` resolve uma vez por passo (`RiskProfileGate`, log **na transição**, não 1×/s) e
   publica em `CycleHealth.risk_profile` → `hb:execution:paper.risk_profile`; `bridge._submit` adia o
   candidato com o mesmo nome (`_defer`), sem gastar o sinal.
3. **A constante continua a guarda.** `hunter_risk.limits.diverged_fields(limits, reference=PAPER_V1)`
   (novo, puro) é a mesma comparação usada pelo worker e pela API. Linha divergente = erro de operador
   nomeado, nunca limite novo.
4. **API.** `/risk-limits` mantém `source='risk_profile'` e ganha `preset.diverged_from_engine`.
   Linha que não valida deixou de ser 500: responde `engine_default` + `diverged_from_engine=true`
   (a tela precisa abrir justamente quando o worker parou de admitir).

## Comandos e saídas (tudo em primeiro plano, `timeout 290`, um arquivo testcontainer por vez)

```
uv run pytest packages/risk-core/tests/unit/test_limits.py -q -p no:randomly        -> 17 passed in 0.83s
uv run pytest services/execution-worker/tests/test_risk_profile.py -q -p no:randomly -> 13 passed in 2.01s
uv run pytest services/execution-worker/tests/test_mark_quality.py -q -p no:randomly -> 10 passed in 2.46s
uv run pytest services/execution-worker/tests/test_scheduling.py \
             services/execution-worker/tests/test_supervision.py -q -p no:randomly  -> 82 passed in 1.83s
uv run pytest tests/integration/paper/test_risk_profile_gate.py -q -p no:randomly    -> 4 passed in 31.31s
uv run pytest services/execution-worker/tests/test_bridge_cycle.py -q -p no:randomly -> 9 passed in 102.54s
uv run pytest services/execution-worker/tests/test_entry_guards.py -q -p no:randomly -> 7 passed in 58.18s
uv run pytest apps/api/tests/integration/test_risk_limits_api.py -q -p no:randomly   -> 10 passed in 86.89s
uv run ruff check apps packages services infra tests                                 -> All checks passed!
uv run ruff format --check <19 arquivos meus>                                        -> 19 files already formatted
uv run pyright services/execution-worker apps/api/.../risk_limits.py packages/risk-core \
       tests/integration/paper/test_risk_profile_gate.py                             -> 6 errors, todos em
       services/execution-worker/tests/test_manual_request_decided.py (ver §"não é meu", abaixo)
uv run python infra/scripts/check_file_size.py  -> scanned 596 files; 0 over budget, 0 grandfathered
```

**Mutação de controle (o teste morde).** Em `decide_requests`, trocar a recusa por
`applied = resolved.limits or PAPER_V1` (o comportamento antigo):
`tests/integration/paper/test_risk_profile_gate.py` → **3 failed, 1 passed** — falham exatamente
"carteira sem vínculo não admite nada", "linha divergente não admite nada" e "vincular volta a
admitir". Revertido em seguida (`grep` confirmando as duas linhas originais).

**O que o teste testcontainer prova** (`tests/integration/paper/test_risk_profile_gate.py`, sobre as
fixtures T3.9): carteira §0 sem vínculo → `decide_requests` devolve `()`, `trade_proposals` = 0,
resolver diz `risk_profile_missing`; linha igual ao `PAPER_V1` vinculada → aprova como antes
(`qty=18,518`, `binding_constraint=risk_per_trade`, reserva `held`, 1 proposta); linha com
`risk_per_trade_pct=0,01` → `()` e 0 propostas, com `risk_profile_diverged: risk_per_trade_pct`;
vincular depois faz a mesma carteira admitir sem restart.

## Fixtures que passaram a precisar do vínculo (nenhum número mudou)

`services/execution-worker/tests/builders.py::open_wallet` ganhou `link_profile=True` (novo helper
`link_paper_profile`, grava `PAPER_V1.model_dump(mode="json")` como `hunter_app`) e
`services/execution-worker/proof/venue.py::open_wallet` faz o mesmo — é o §8b em forma de fixture,
porque desde agora uma carteira sem perfil não admite. `test_bridge_cycle.py` ganhou o caso oposto
(`link_profile=False` → `outcome.deferred == "risk_profile_missing"`, 0 propostas).

## Não é meu (registro, não conserto)

`services/execution-worker/tests/test_manual_request_decided.py` está **vermelho por mudança em voo de
outro agente**: `apps/api/hunter_api/services/admission.py` (T3.68c, modificado e não commitado) tornou
`max_pending` um argumento obrigatório de `file_manual_order`, e o teste não passa o argumento —
`TypeError: file_manual_order() missing 1 required keyword-only argument: 'max_pending'`, antes de
qualquer código meu rodar. Os 6 erros de `pyright` acima são os mesmos. Não toquei nesse arquivo além
do vínculo herdado do `proof/venue.py`.

## Arquivos (git status --porcelain, só os meus)

```
 M apps/api/hunter_api/schemas/risk_limits.py
 M apps/api/hunter_api/services/risk_limits.py
 M apps/api/tests/integration/test_risk_limits_api.py
 M docs/ACTIVATION.md
 M docs/RISK_ENGINE.md
 M infra/scripts/link_portfolio_risk_profile.py
 M packages/risk-core/hunter_risk/__init__.py
 M packages/risk-core/hunter_risk/limits.py
 M packages/risk-core/tests/unit/test_limits.py
 M services/execution-worker/hunter_execution_worker/admission_cycle.py
 M services/execution-worker/hunter_execution_worker/bridge.py
 M services/execution-worker/hunter_execution_worker/cycles.py
 M services/execution-worker/hunter_execution_worker/heartbeat.py
 M services/execution-worker/hunter_execution_worker/state.py
 M services/execution-worker/proof/venue.py
 M services/execution-worker/tests/builders.py
 M services/execution-worker/tests/test_bridge_cycle.py
 M services/execution-worker/tests/test_mark_quality.py
?? services/execution-worker/hunter_execution_worker/risk_profile.py
?? services/execution-worker/tests/test_risk_profile.py
?? tests/integration/paper/test_risk_profile_gate.py
?? .claude/state/notes-T3.69b.md
```

Demais linhas de `git status --porcelain` são de outros agentes (`apps/api/.../admission.py`,
`orders.py`, `settings.py`, `docs/DESIGN.md`, `services/strategy-worker/**`, etc.).
Nada rodado na VPS, nada commitado.

## Documentação

`docs/RISK_ENGINE.md` → **v2.4** (linha de versão, §2 com a regra nova e os três motivos, §9.5 com o
que mudou e a consequência operacional). `docs/ACTIVATION.md` → §8 linha 8 (agora 🔴, com o efeito
escrito) e §8b (tabela "antes × depois do vínculo", os dois motivos extras, e que nada disso afeta
saída de proteção). `infra/scripts/link_portfolio_risk_profile.py`: o parágrafo que dizia "o motor lê
a constante, T3.69b está aberta" passou a dizer o que o motor faz hoje.
