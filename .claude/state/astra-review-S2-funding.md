**RESUMO**

**REQUEST_CHANGES.** Os dois cenários anteriores estão corrigidos no resolvedor, mas ainda há um bloqueio concreto na fronteira de saída: os carregadores cortam o histórico antes que o cluster completo chegue à validação.

**ARQUIVOS**

Nenhum arquivo criado ou modificado; nenhum commit. Revisão como `code-reviewer`, em modo OPINIÃO.

**TESTES**

Executei com sincronização, cache e bytecode desativados:

```text
uv run pytest services/strategy-worker/tests/test_funding.py -q -p no:cacheprovider
21 passed in 0.45s
```

Reprodução sintética em memória, com `uv run python -B -`:

```text
full_history: per_unit=None, reason=funding_boundary_uncertain:2026-09-06T16:00:00+00:00, settlements=0
sql_until_exit: per_unit=0.0200, reason=None, settlements=1
```

Não executei PostgreSQL, os 184 testes completos, ruff ou pyright nesta sessão.

**MUST-FIX**

1. **HIGH — O corte SQL em `exit_ts` esconde representações posteriores da mesma liquidação.**

   Cenário: entrada às **15:00**, saída conhecida na abertura às **16:00**, histórico às 00:00/08:00 e duas linhas compatíveis às **16:00:00 / 16:00:00.005**, taxa `0.0002`, preço `100`.

   Com ambas as linhas, o resolvedor retorna corretamente `funding_boundary_uncertain`. Entretanto, `_funding_history` consulta apenas até `candidate.exit_ts`, excluindo a segunda representação. Resultado reproduzido com esse corte: **cobra `0.0200`, sem motivo de indisponibilidade**. [recompute_funding.py:80](C:/dev/project-hunter/infra/scripts/recompute_funding.py:80), [recompute_funding.py:176](C:/dev/project-hunter/infra/scripts/recompute_funding.py:176).

   O fechamento normal tem o mesmo problema: passa `until=exit_ts`, aplicado como limite inclusivo pelo repositório. [settle.py:60](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/settle.py:60), [repo.py:147](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/repo.py:147).

   **Para fechar:** preservar na leitura os membros necessários à análise da fronteira de saída, mantendo a janela cobrável original. Acrescentar regressão com ambas as linhas já persistidas em PostgreSQL, exercitando o carregador real.

**NICE-TO-HAVE**

O teste negativo não exercita a decisão de escrever de `_run`; chama apenas leitura/recomputação e depois verifica ausência de mudança. Se a guarda de `_run` regredir, esse teste continuará verde. Seria útil cobrir essa orquestração. [test_recompute_funding.py:226](C:/dev/project-hunter/services/strategy-worker/tests/test_recompute_funding.py:226), [recompute_funding.py:268](C:/dev/project-hunter/infra/scripts/recompute_funding.py:268).

**O QUE EU FARIA DIFERENTE**

Fecharia a regressão na fronteira **SQL → resolvedor**. Clusterizar todo o histórico recebido resolve a função, mas depende de o carregador preservar as representações relevantes.

**CONCORDO COM**

- As regressões de entrada e `ambiguous_from` agora cobrem exatamente os dois cenários anteriores. [test_funding.py:233](C:/dev/project-hunter/services/strategy-worker/tests/test_funding.py:233).
- Semear diretamente por SQL é adequado ao escopo do recompute. O teste recuperável verifica escrita, auditoria, motivo nulo e exclusão na segunda seleção; usa fixture com PostgreSQL real via testcontainers. Isso atende ao desenho da prova solicitada, embora eu não tenha repetido sua execução. [test_recompute_funding.py:150](C:/dev/project-hunter/services/strategy-worker/tests/test_recompute_funding.py:150), [conftest.py:77](C:/dev/project-hunter/services/strategy-worker/tests/conftest.py:77).

**OBSIDIAN**

- **Open Bugs** — registrar o corte em `exit_ts` que oculta duplicatas após a saída.
- **EXP-0001-momentum-v1** — registrar as regressões aprovadas e o bloqueio restante antes de liberar o recompute.
- **Revisoes-Astra/Index** — vincular este parecer à revisão S2-funding.