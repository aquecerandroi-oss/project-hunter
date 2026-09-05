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
