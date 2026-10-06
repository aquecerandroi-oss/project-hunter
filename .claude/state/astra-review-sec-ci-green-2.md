**RESUMO**

Concordo com 1, 2 e 4; no item 3, concordo com LOW na exposição atual, com ressalvas. Nenhuma SQL injection demonstrada.

**ARQUIVOS**

Nenhum criado ou modificado; nenhum commit.

**TESTES**

- `pnpm audit --audit-level=high`, via Bash: **exit 1**, `Severity: 2 high (1 ignored)`; restante: `source-map-js`.
- Reprodução em memória da regex: `compose.yml: detected`; `compose.yml.example: NOT detected`; `.env.compose.yml: NOT detected`.
- Bandit isolado em `wallet_exceptions.py`: **exit 0**, com warnings sobre o comentário. Não rodei a suíte completa.

**MUST-FIX**

**MEDIUM para concluir “CI verde”** — [pnpm-lock.yaml:2521](C:/dev/project-hunter/pnpm-lock.yaml:2521) mantém `source-map-js@1.2.1`; o [workflow:341](C:/dev/project-hunter/.github/workflows/ci.yml:341) executa o audit bloqueante. Cenário reproduzido: o job termina com código 1.

Concordo com `pnpm update -r source-map-js --depth Infinity`, seguido de nova auditoria, **sem ignore nem redução do portão**. A vulnerabilidade upstream é **HIGH**; MEDIUM aqui descreve o achado contextual de CI. A [correção 1.2.2, publicada em 30/09](https://github.com/7rulnik/source-map-js/releases/tag/v1.2.2), já supera as 24 horas de [pnpm-workspace.yaml:8](C:/dev/project-hunter/pnpm-workspace.yaml:8).

**NICE-TO-HAVE**

O bypass de [forbidden_patterns.sh:159](C:/dev/project-hunter/infra/scripts/forbidden_patterns.sh:159) é **LOW no estado atual**, mas não é intrinsecamente “template não carregado”: Compose pode receber explicitamente um arquivo com outro sufixo.

A allowlist proposta fecha **os dois exemplos apresentados**. Checar somente extensão final `yml/yaml` não fecha `compose.yml.example`; precisa reconhecer também esse sufixo composto.

**O QUE EU FARIA DIFERENTE**

Restringiria a exceção aos nomes dotenv convencionados e acrescentaria os dois casos ao self-test. Nome de arquivo sozinho não prova seu formato.

**CONCORDO COM**

- **29 supressões:** não encontrei valor controlável por request/tenant/linha interpolado. Condições e cursor estão separados em [orders.py:137](C:/dev/project-hunter/apps/api/hunter_api/services/orders.py:137); o lock escolhe fragmentos literais em [dedupe.py:191](C:/dev/project-hunter/packages/core/hunter_core/admission/dedupe.py:191); os status vêm de tuplas constantes em [repo_tape.py:187](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/repo_tape.py:187). Os demais identificadores/fragmentos revisados também são constantes ou campos de dataclass.
- **Item 4:** LOW e preexistente, fora deste diff. [gates.py:88](C:/dev/project-hunter/packages/core/hunter_core/execution/meme/gates.py:88) aceita `1/yes/on`; [forbidden_patterns.sh:161](C:/dev/project-hunter/infra/scripts/forbidden_patterns.sh:161) só procura `true`. Cenário: `ENABLE_MEME_LIVE_TRADING=yes` escapa do detector, embora satisfaça essa flag no runtime.

**OBSIDIAN**

- **CI-verde-2026-10-05** — registrar o audit ainda bloqueante e a ressalva sobre formatos.
- **Infrastructure** — atualizar o bloqueio restante de segurança.
- **Open Bugs** — registrar os bypasses LOW por nome/formato e vocabulário booleano.