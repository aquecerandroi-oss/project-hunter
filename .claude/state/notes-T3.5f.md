# Notas T3.5f — dívida de tipagem nos testes do execution-worker e no teste do admission adapter

**Status:** DONE

## O que era

`uv run pyright` (o comando exato que o CI roda, sem argumentos) já cobria `apps` e
`services` por inteiro via `[tool.pyright].include = ["packages", "apps", "services",
"infra/scripts"]` em `pyproject.toml` — não há exclusão de `**/tests` em nenhum lugar.
179 erros reais, todos em 6 arquivos:

- `services/execution-worker/tests/test_mtm_and_kill_switch.py` — 46
- `services/execution-worker/tests/test_protection_cycle.py` — 38
- `services/execution-worker/tests/test_order_cycle.py` — 35
- `services/execution-worker/tests/test_restart_recovery.py` — 27
- `apps/api/tests/unit/test_admission_adapter.py` — 19
- `services/execution-worker/tests/test_concurrency.py` — 14

`services/execution-worker/tests/builders.py`, `conftest.py`, `scenarios.py` e
`shadow_builders.py` já estavam limpos.

## Causa raiz

**execution-worker (160 dos 179):** toda função auxiliar local a cada arquivo de teste
(`_open_a_position`, `_stop`/`_gap_snapshot`/`_no_book_snapshot`/`_entry_snapshot`,
`_cycle`/`_protect`/`_mark`, `_admit`, `_run_entries`, `_counts`, `_cash`,
`_stop_snapshot`) tinha parâmetros sem anotação e um `# type: ignore[no-untyped-def]`
na linha da assinatura. Em modo estrito, isso não silencia o problema — silencia só
aquele diagnóstico específico; pyright infere os parâmetros como `Unknown` e a
inferência se propaga: cada `tenant.slug`, `wallet.org_id`, `session_factory=...` etc.
passado a essas funções (e retornado por elas) virou `reportUnknownMemberType` /
`reportUnknownArgumentType` no call site — daí os "160 primeiro vistos em
`test_restart_recovery.py`". Fix: tipar de verdade os parâmetros e o retorno de cada
helper com os tipos reais do domínio (`Tenant`, `Wallet` de `.builders`;
`async_sessionmaker[AsyncSession]`, `AsyncEngine`, `AsyncSession` de sqlalchemy;
`SpotSnapshot`, `SpotMarketData`, `EntryOutcome`, `ProtectionOutcome`, `MarkToMarket`,
`AdmissionResult`, `FxObservation` das próprias funções de produção que os testes
chamam) e remover os `# type: ignore[no-untyped-def]`. Zero `cast`, zero `Any` novo
nesses arquivos.

Um efeito colateral corrigido em `test_mtm_and_kill_switch.py`: os três
`# type: ignore[arg-type]` em `market_identity(second)` / `spec_for(second)` /
`liquidity_for(second)` existiam porque `SecondMarket` (usado nos cenários
cross-market) tem os mesmos campos que `Tenant` (`slug`, `symbol`, `base_symbol`,
`step`) mas não é a mesma classe nominal. Em vez de manter os três ignores,
`services/execution-worker/tests/builders.py` passou a tipar `market_identity`,
`spec_for` e `liquidity_for` como `tenant: Tenant | SecondMarket` — as duas únicas
implementações reais, closed set — e os ignores saíram.

**admission adapter (19 dos 179):** um único ponto,
`apps/api/tests/unit/test_admission_adapter.py:301` — a classe `_Spy(original)` que
espiona `ProposalRequest.__init__` (um `BaseModel` do Pydantic) declarava
`def __init__(self, **kwargs: object) -> None`. Como o `**kwargs` era repassado para
`super().__init__(**kwargs)`, e `ProposalRequest` tem 18 campos com tipos concretos
(`str`, `UUID`, `Decimal`, `MarketIdentity`, etc.), cada um virou
"Argument of type 'object' cannot be assigned to parameter ... " — as 19 linhas do
relatório são as 19 chamadas/campos daquele único `super().__init__`. Fix: trocar
`object` por `Any` (com comentário explicando por quê) — é exatamente o padrão "spy
repassa argumentos arbitrários para o construtor real", não um "tipo errado de
propósito", então não é um `cast`.

## Prova (antes/depois)

```
$ uv run pyright services/execution-worker/tests apps/api/tests/unit/test_admission_adapter.py
... (179 errors, 0 warnings, 0 informations)   # ANTES, HEAD 47cff11

$ uv run pyright services/execution-worker apps/api
0 errors, 0 warnings, 0 informations           # DEPOIS

$ uv run pyright   # exatamente o comando do CI (.github/workflows/ci.yml:39-40)
0 errors, 0 warnings, 0 informations           # repo inteiro, 902 arquivos
```

## Item 3 do brief (escopo do pyright no CI)

`docs/DEPLOYMENT.md §7` hoje é "Variáveis de ambiente", não CI — a numeração do
brief está desatualizada (o doc mudou sob outros agentes). A seção real é §4
(`## 4. CI (GitHub Actions)`, linha 176: *"`python-lint` — ruff, ruff format
--check, pyright, file-size gate"*) e o passo em `.github/workflows/ci.yml:39-40` é
`run: uv run pyright` — sem argumentos. `pyproject.toml` `[tool.pyright]` já tem
`include = ["packages", "apps", "services", "infra/scripts"]` e
`exclude = ["**/node_modules", "**/.venv", "infra/migrations/versions"]` — nenhuma
exclusão de `tests/`. Rodei o comando exato do CI (`uv run pyright`, sem args) antes
de mexer em qualquer arquivo e ele **já** enumerava os 6 arquivos problemáticos (é
assim que os "179 erros" desta tarefa foram descobertos por mim, de forma
independente de rodar com paths explícitos) — então o escopo já cobria essas duas
pastas de teste desde o esqueleto do M0 (`6652c5a`), sem exclusão nunca adicionada.
**Não editei `ci.yml` nem `pyproject.toml`**: mudar um arquivo que já está correto
violaria "mudanças cirúrgicas" e arriscaria mexer em configuração de CI compartilhada
sem necessidade. A prova de que "a dívida não pode voltar em silêncio" é o comando
`uv run pyright` (repo inteiro, sem args) rodando 0 erros acima — é literalmente o
job `python-lint` do CI, e qualquer futuro `# type: ignore[no-untyped-def]`
reintroduzido nesses dois diretórios voltará a aparecer nele.

## Arquivos

- `apps/api/tests/unit/test_admission_adapter.py` — `object` → `Any` em `_Spy.__init__`
- `services/execution-worker/tests/builders.py` — `market_identity`/`spec_for`/`liquidity_for` aceitam `Tenant | SecondMarket`
- `services/execution-worker/tests/test_restart_recovery.py` — helpers tipados
- `services/execution-worker/tests/test_protection_cycle.py` — helpers tipados
- `services/execution-worker/tests/test_order_cycle.py` — helpers tipados (+ `rows: dict[str, int] = {}`)
- `services/execution-worker/tests/test_mtm_and_kill_switch.py` — helpers tipados, 3 ignores removidos
- `services/execution-worker/tests/test_concurrency.py` — helpers tipados

Nenhum arquivo de produção, `.env*`, `apps/web/**` ou `obsidian/**` tocado.
