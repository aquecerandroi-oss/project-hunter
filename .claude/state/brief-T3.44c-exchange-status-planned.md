# Brief T3.44c — `exchange_status` precisa de um valor `planned` antes que a Bybit possa sair do agregado do topbar

**Owner:** database-architect. **Não commitar** sem revisão. **Regra operacional: nunca Bash em background; comandos em primeiro plano com timeout ≤ 5 min; testcontainers um arquivo por invocação.**

## Origem

T3.44b (`.claude/state/brief-T3.44b-ws-close-logging-and-bybit-status.md`) pediu para marcar `bybit` como `status=planned` em `exchanges` (o worker nunca foi implantado para ela) e para `system_status.py` excluir exchanges `planned` do agregado do topbar (`exchanges_planned: ["bybit"]` à parte). O brief já previa esta saída: "se `exchanges.status` não tiver um valor `planned` no seu CHECK/enum, diga isso e acione o database-architect em vez de editar migrações" — é exatamente o caso.

## Achado

`infra/migrations/ddl/enums.py:76-79`:

```python
"exchange_status": (
    "active",
    "inactive",
),
```

Materializado como o tipo Postgres `exchange_status` em `infra/migrations/versions/0001_initial_schema.py:144-149` (`exchanges.status`, `postgresql.ENUM("active", "inactive", name="exchange_status", create_type=False)`, `NOT NULL`, `server_default='active'`). Não há terceiro valor em nenhuma migração posterior. Uma query ou um seed que tentasse gravar `status='planned'` hoje falharia em runtime contra o Postgres real (`invalid input value for enum exchange_status`) — não é algo que dê para contornar em `seed_reference.py`/`system_status.py` sem a migração primeiro.

## Decisão pedida

1. Confirmar (ou revisar) que `planned` é o nome certo, e se cabe no mesmo enum ou se merece sua própria coluna/tabela (ex.: `exchanges.status` continua `active`/`inactive` para "operável agora" e um campo separado, tipo `has_collector: bool` ou `onboarding_status`, cobre "cadastrada mas sem worker ainda" — a Bybit não está "inactive" no sentido usual, só ainda não tem coletor).
2. Se a resposta for estender o enum: uma migração Alembic nova que faça `ALTER TYPE exchange_status ADD VALUE 'planned'` (fora de uma transação de bloco, como o Postgres exige para `ADD VALUE`; ver como `0011`/outras migrações do repo tratam DDL fora de `BEGIN`), mais o `ddl/enums.py` atualizado para refletir o novo terceiro valor.
3. Uma vez decidido e migrado, os consumidores prontos para a mudança (não implementados nesta tarefa, aguardando este brief):
   - `infra/scripts/seed_reference.py` — `EXCHANGES` passa a carregar o status desejado por linha (hoje é sempre implícito `active` via `server_default`, e `seed.py:seed_exchanges` nem escreve `status` no upsert — precisa passar a escrever explicitamente para poder mudar um `active` existente para `planned` e vice-versa).
   - `apps/api/hunter_api/services/system_status.py` (`build_market_status`) — excluir do loop principal os `exchange_codes` cujo `status == planned` e devolver a lista separada em `MarketStatusOut.exchanges_planned: list[str]` (aditivo).
   - `apps/api/hunter_api/schemas/system.py` — o novo campo, mantendo o resto do contrato Redis intacto (module docstring já promete "keep the two in sync" com `system_status.py`).
   - `pnpm gen:types` depois de qualquer mudança de schema Pydantic, para o TS ver o campo novo.
   - `apps/web/components/system/live-status.tsx` — nota do backend-specialist (T3.44b) para quem pegar o lado do front: com `exchanges_planned` disponível, o topbar deve ler "1 exchange · CONNECTED · N mercados (bybit planejada)" em vez de contar a Bybit como uma exchange "unavailable" no agregado.
   - `docs/PIPELINE.md` §1 já tem uma nota apontando para este brief (T3.44b); atualizar quando a decisão sair.
4. Comando do operador para re-semear `exchanges` depois da mudança: hoje **não existe** `seed.py --only exchanges` (o `--only` do `seed_cli.py` só cobre `strategies`/`risk_profiles`/`feature_definitions`/`opportunity_weights` — `seed_exchanges` roda incondicionalmente dentro de `seed()`, nunca dentro do fluxo `--only`/`--dry-run`). O brief T3.44b citava esse comando como já existente; corrigido aqui: hoje o único jeito é `uv run python infra/scripts/seed.py` (roda tudo) ou adicionar `"exchanges"` a `seed_dry_run.TABLE_CHOICES` como parte deste trabalho, se granularidade for desejada.

## Prova

Migração revisada por Astra antes de aplicar; teste de integração que sobe a migração, insere `bybit` com `status='planned'` e confirma que o CHECK/enum aceita; `alembic upgrade head` e `alembic check` limpos. Depois de mesclado, novo brief para backend-specialist implementar os itens 3-4 acima.
