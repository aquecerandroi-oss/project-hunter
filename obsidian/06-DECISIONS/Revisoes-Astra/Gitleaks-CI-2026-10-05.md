---
tags: [astra, revisao, seguranca, ci, gitleaks]
status: fechada
owner: devops-engineer
updated: 2026-10-05
decided_on: 2026-10-05
by: security-reviewer + devops-engineer
---

# Revisão — `gitleaks` vermelho no CI desde pelo menos 08/09 (05/10/2026)

Pedido: o job `security` do `ci.yml` falhava em todo push na `main`, no passo `gitleaks`. A pergunta de fundo era a de segurança — há segredo real no repositório (que é público) ou o passo é só ruído? Contexto geral do conserto do CI: [[Infrastructure]] (seção "CI vermelho em 05/10") e [[Open Bugs]].

## Resumo

- **Auditoria do `security-reviewer` (HEAD e histórico completo): nenhum segredo real; nada a rotacionar.** 579 achados, todos falsos positivos: endereços públicos de Solana/EVM nos dumps de `.claude/state/plantao-meme/raw-lane*/` e em fixtures, nomes de arquivo do Zenodo, identificadores (`exit_key`, `idempotency_key`...), falsos documentados.
- **Duas causas de ruído, ambas de infraestrutura:** (1) `gitleaks-action` v2.3.9 sem `GITLEAKS_VERSION` roda o gitleaks 8.24.3, que **ignora** `[[allowlists]]` globais (valem a partir da 8.25) — a allowlist do `.gitleaks.toml` nunca teve efeito no CI; (2) o checkout raso (profundidade 1) faz o push de 1 commit escanear a árvore inteira.
- **Quatro furos no `.gitleaks.toml` antigo, achados na revisão** (todos de "controle que parece funcionar e não funciona"):
  1. a regra `hunter-db-uri-embedded-password` não tinha `secretGroup`: o **segredo reportado era o match inteiro**, então a senha da URI saía no log do CI (repositório público);
  2. a allowlist `(?i)FAKE` por **linha** suprimiria uma chave real em qualquer linha que contivesse "fake";
  3. a exceção de `localhost` também por linha, e sem âncora de fim (`localhost.evil.example` passaria);
  4. a entrada histórica `postgresql\+asyncpg://u:supersecret@host/db` nunca casava com o segredo (que é só a senha).
- **Conserto (CI + config):** `ci.yml`, job `security`: `actions/checkout` com `fetch-depth: 0` e `GITLEAKS_VERSION: 8.30.1` no passo do gitleaks. `.gitleaks.toml` reescrito: `secretGroup = 1` na regra de URI (senha redigida); `FAKE` com `regexTarget = "secret"`; exceção de host com `regexTarget = "match"` e âncora `$`; allowlists de endereços públicos com **caminho E formato ancorado** (`condition = "AND"`, só para `generic-api-key`); literais exatos.

## Verificação (binário oficial 8.30.1, o mesmo que o CI passa a usar)

- `gitleaks git --config .gitleaks.toml --redact` no repositório inteiro: **1057 commits, ~237 MB, 31 s, "no leaks found"** (HEAD e histórico).
- **Controles negativos** (diretório de rascunho fora do repositório, `gitleaks dir` com o mesmo config): URI com senha de 16 caracteres num host de Neon, URI com `@localhost.evil.example`, PAT `ghp_...` com comentário "fake-ish", segredo de AWS, `api_key` num caminho `raw-lane1` com valor que não é endereço, `api_key` real-parecido numa linha de arquivo comum — **6 detectados**; a URI de dev (`hunter:hunter@localhost:5432`) e `sk_test_FAKE_CI_BUILD` **não** foram sinalizados. Sem o controle negativo, "zero achados" depois de alargar allowlists não prova nada.

## Divergência de severidade (escrita)

- **`security-reviewer`: MEDIUM** para a falha de redação da senha no log (regra de URI sem `secretGroup`).
- **Astra: HIGH** para a mesma falha.
- **Registro no [[Open Bugs]]: HIGH**, pelo conjunto (controle de segurança sem efeito num repositório público), não só pela redação. Não há segredo real envolvido nem exploração conhecida; a divergência é de peso, e o conserto é o mesmo.

## Lição

- **Testar com a mesma versão que o CI roda.** O CI rodava o gitleaks 8.24.3, que ignora `[[allowlists]]` globais (valem da 8.25): a allowlist estava escrita e não tinha efeito. A versão passou a ser fixada (`GITLEAKS_VERSION: 8.30.1`) e o config foi verificado com esse mesmo binário.
- **Zero achados depois de alargar allowlists exige controles negativos** — um achado que some por allowlist larga demais é indistinguível, no relatório, de um achado que nunca existiu.
- Allowlist por linha (`regexTarget = "line"`) é a forma mais larga possível; preferir `secret`/`match` e, quando for por local, caminho **e** formato.

Relacionadas: [[Infrastructure]] · [[Open Bugs]] · [[Resolved Bugs]] · [[Revisoes-Astra/Index|índice das revisões da Astra]]
