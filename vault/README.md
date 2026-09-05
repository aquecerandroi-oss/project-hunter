# Vault — memória de longo prazo do HUNTER (Obsidian)

Abra esta pasta (`C:\dev\project-hunter\vault`) como um cofre no Obsidian. É a camada dois da memória do projeto (`.claude/memory/INSTRUCTIONS.md`): o índice pequeno `MEMORY.md` continua sempre carregado; o que é específico, raro ou grande demais vem para cá, buscável sob demanda.

Estrutura (PARA adaptado, vibe-coding-toolkit `docs/tools/08-obsidian-memory.md`):

| Pasta | Guarda |
|---|---|
| `01-projetos/` | trabalho com fim definido (um milestone, uma integração) |
| `02-areas/` | responsabilidades contínuas (risco, exchanges, auth) |
| `03-conhecimento/` | lições atemporais: regra de negócio, decisão de arquitetura, erro corrigido |
| `04-referencia/` | onde algo externo mora (painéis, contas, links) |
| `daily/` | registro rotativo do dia; consolidado em `03-conhecimento` e depois apagado |
| `templates/` | frontmatter e seções obrigatórias de cada pasta |

Regras: `name` em kebab-case igual ao nome do arquivo; `description` obrigatória; `metadata.type` ∈ `feedback | architecture | business-rule | reference | project | area | daily`; seções na ordem do template; `Related` sempre por último; wikilinks só para notas que existem.

Agentes escrevem aqui **apenas** pelas ferramentas MCP do cofre (`.mcp.json`); acesso direto por Read/Write/Edit é bloqueado pelo hook `.claude/hooks/vault-mcp-only.mjs`. Você, no Obsidian, edita à vontade.
