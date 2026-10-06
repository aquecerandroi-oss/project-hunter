---
tags: [astra, revisao, seguranca, ci, pnpm-audit, bandit, forbidden-patterns]
status: fechada
owner: devops-engineer
updated: 2026-10-06
decided_on: 2026-10-06
by: security-reviewer + Astra + devops-engineer
---

# Revisão de segurança do CI verde — segunda rodada (06/10/2026)

O `security-reviewer` revisou o diff de [[CI-verde-2026-10-05]] com a Astra (bruto: `.claude/state/astra-review-sec-ci-green-2.md`). **Aprovou** as 29 supressões `nosec B608` (nenhum valor controlável por request/tenant/linha interpolado: condições e cursor separados em `orders.py`, fragmentos literais escolhidos por bool em `dedupe.py`, status de tuplas constantes em `repo_tape.py`), o `ci.yml`, o `uv.lock` e o ignore do `braces`. **Pediu mudanças** em um MEDIUM e um LOW.

## Achados e o que foi feito

- **MEDIUM — `pnpm audit --audit-level=high` ainda saía 1** com `source-map-js@1.2.1` (GHSA-68fv-2mgg-jv7q, corrigida em 1.2.2, publicada em 30/09, fora do `minimumReleaseAge` de 24 h). Reproduzido pela Astra e por mim (`2 vulnerabilities found, Severity: 2 high (1 ignored)`). Conserto: `pnpm update -r source-map-js --depth Infinity`, sem ignore e sem reduzir o portão. Depois: `pnpm audit --audit-level=high` exit 0 (`1 vulnerabilities found, Severity: 1 high (1 ignored)` — o do `braces`), `pnpm install --frozen-lockfile --lockfile-only --ignore-scripts` "Already up to date", `pnpm lint` e `tsc --noEmit` do web verdes. Por que escapou da minha rodada: o `pnpm audit` que rodei listava 13 high; o `source-map-js` apareceu só quando a cadeia anterior foi corrigida e o registro passou a oferecer a 1.2.2 — o resultado de uma auditoria vale para o instante em que roda.
- **LOW — exceção de comentário do `forbidden-patterns` escolhida pelo nome do arquivo.** `compose.yml.example` e `.env.compose.yml` com flow map `{LABEL: "#desk", ENABLE_MEME_LIVE_TRADING: "true"}` não acertavam (reproduzido: `compose.yml` detected, os outros dois NOT). A Astra notou que checar só a extensão final não fecha `compose.yml.example` — precisa reconhecer o sufixo composto. Conserto: a exceção vale só para `.env`, `.env.example` e `.env.<x>.example`, e nunca para nome com `.yml`/`.yaml` (padrão `*.yml*|*.yaml*` antes do caso dotenv); `--self-test` ganhou os dois casos e `.env.staging.example` (continua dotenv). Todos os fixtures passam.
- **LOW, preexistente, fora do diff — vocabulário booleano.** `gates.py:88` `parse_flag` aceita `1/true/yes/on`, os bools do pydantic aceitam `1/yes/on`; o detector só procura `true`. `ENABLE_MEME_LIVE_TRADING=yes` escapa. Registrado em [[Open Bugs]]; não consertado aqui.
- **`bandit`:** o `nosec` de `wallet_exceptions.py` foi acrescentado pelo orquestrador (linha 48, arquivo de outra frente). A Astra rodou o bandit só nesse arquivo (exit 0); eu rodei o comando completo do CI: exit 0 em 30 s.

## Divergências (escritas)

- Severidade do `source-map-js`: o revisor disse MEDIUM "para concluir CI verde"; a Astra lembrou que a vulnerabilidade upstream é HIGH e MEDIUM descreve o achado contextual de CI. O conserto é o mesmo.
- A exceção por nome: eu havia proposto "template não carregado" como justificativa; a Astra discordou (o Compose pode receber explicitamente um arquivo com outro sufixo) — **ela tem razão**, e por isso a lista ficou restrita aos nomes dotenv convencionados.

## Lição

- Auditoria de dependências é uma foto: rode de novo **depois** de cada correção, no mesmo comando do CI, e leia o código de saída (não só a contagem).
- Nome de arquivo não prova formato; a lista de nomes com exceção deve ser a menor possível.

Relacionadas: [[CI-verde-2026-10-05]] · [[Gitleaks-CI-2026-10-05]] · [[Infrastructure]] · [[Open Bugs]] · [[Resolved Bugs]] · [[Revisoes-Astra/Index|índice das revisões da Astra]]
