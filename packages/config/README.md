# @hunter/config

Presets compartilhados de lint, tipos e formatação. Consumidos por `apps/web` (ESLint) e por todo o workspace Python (ruff, pyright).

## ESLint — quality gates (origem: vibe-coding-toolkit)

`eslint/eslint-rules/{utils,core-rules,index}.cjs` e `eslint/verify.mjs` são cópias **byte a byte** de `templates/eslint/` do [vibe-coding-toolkit](https://github.com/soumatheusgomes/vibe-coding-toolkit) (hashes SHA-256 conferidos em 2026-09-04). Não edite; se precisar mudar comportamento, mude a configuração em `eslint/eslint.config.mjs`.

Três regras:

| Regra | Severidade | O que faz |
|---|---|---|
| `quality/max-lines` | error (350) | Teto de linhas por arquivo de produção; `warn` em testes |
| `quality/no-direct-console` | error | Proíbe `console.*` fora de `lib/logger.ts` e `instrumentation*.ts` |
| `quality/no-direct-data-access` | error | `components/**` e `hooks/**` não importam `@/lib/server/**` (server-only) |

Mais `import-x/no-restricted-paths` para a mesma fronteira e `import-x-debt/...` (vazio, reservado para dívida futura em `warn`).

Dois tiers: `eslint.config.mjs` (rápido, pre-commit) e `eslint.typed.config.mjs` (type-aware, só `pnpm lint:types` em CI).

**Auto-checagem obrigatória após qualquer alteração de dependência de lint:**

```bash
pnpm --filter @hunter/config verify:eslint-rules
```

Saída esperada: três linhas terminando em `: ok`. Executada com sucesso em 2026-09-04 (Node 24.20, eslint 9.39.5). Enquanto o workspace pnpm não existe (M0, T01), o equivalente é `npm install --no-package-lock` dentro de `packages/config` seguido de `node eslint/verify.mjs eslint/eslint-rules/index.cjs`.

## Python

- `ruff.toml` — gate (bloqueia commit e CI).
- `ruff.strict.toml` — tier aspiracional, roda em CI como não-bloqueante até a contagem zerar e a regra migrar para `ruff.toml`.
- Teto de 350 linhas por módulo: `python infra/scripts/check_file_size.py` (mesma régua do lado TS).
