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

Mais `import-x/no-restricted-paths` para a mesma fronteira e `import-x-debt/...` (`off`, reservado para dívida futura — a própria regra exige `zones` não vazio, então liga em `warn` só quando uma zona real for introduzida).

Dois tiers: `eslint.config.mjs` (rápido, pre-commit) e `eslint.typed.config.mjs` (type-aware, só `pnpm lint:types` em CI). O tier tipado exporta a factory `hunterWebTypedConfig({ tsconfigRootDir })` — igual à `hunterWebConfig` do tier rápido — porque `import.meta.dirname` dentro deste pacote resolveria para `packages/config/eslint`, não para o app consumidor; `apps/web/eslint.typed.config.mjs` chama a factory com o próprio `import.meta.dirname` e reaplica as mesmas globs de arquivo do layout do `apps/web` (`app/**`, `components/**`, `lib/**`, `hooks/**`) para as regras type-aware.

`tsconfig.base.json` é a base estrita para os apps Next.js 15 / React 19 e pacotes TS (`target` ES2022, `moduleResolution` bundler, `strict`, `noUncheckedIndexedAccess`, `verbatimModuleSyntax`, etc.). Sem `paths` — cada app define seu próprio `@/*`. Consumido via `"@hunter/config/tsconfig.base.json"` no `extends` do `tsconfig.json` do app.

**Auto-checagem obrigatória após qualquer alteração de dependência de lint:**

```bash
pnpm --filter @hunter/config test
```

Roda `verify:eslint-rules` (self-teste das regras `quality/*` via `RuleTester`, três linhas `: ok`) e depois `smoke:eslint` (self-teste do config montado — `eslint.config.mjs` — contra arquivos que imitam o layout do `apps/web`; cinco linhas `ok`). Executado com sucesso em 2026-09-04 (Node 24.20, eslint 9.39.5).

## Python

- `ruff.toml` — gate (bloqueia commit e CI).
- `ruff.strict.toml` — tier aspiracional, roda em CI como não-bloqueante até a contagem zerar e a regra migrar para `ruff.toml`.
- Teto de 350 linhas por módulo: `python infra/scripts/check_file_size.py` (mesma régua do lado TS).
