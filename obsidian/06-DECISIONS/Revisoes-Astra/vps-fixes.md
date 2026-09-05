---
tags: [astra, revisao]
updated: 2026-09-05
fonte: .claude/state/astra-review-vps-fixes.md
---

# Revisão da Astra — vps-fixes

Parte da [[Mente da Sexta-feira]]. Índice: [[Index|todas as revisões]]. Diálogos relacionados: [[Dialogos/M1|M1]], [[Dialogos/M2|M2]].

**Must-fix:**

- **Temporário previsível:** [setup_env.sh:216](C:/dev/project-hunter/infra/scripts/setup_env.sh:216) usa `$$`, e a escrita segue eventual symlink nesse temporário. A recusa protege apenas o destino. Use `mktemp` no mesmo diretório.
- **Permissão não garantida:** [backup_postgres.sh:29](C:/dev/project-hunter/infra/vps/backup_postgres.sh:29) ignora falha de `chmod 700`. Precisa abortar se não conseguir restringir o diretório.
- **(f) CORS ainda existe:** [.env.example:13](C:/dev/project-hunter/.env.example:13) continua definindo URL simples. O [compose base:76](C:/dev/project-hunter/infra/docker/docker-compose.yml:76) importa `.env`; portanto, remover do override não elimina uma definição antiga. O setup corrigido resolve para arquivos regenerados.
- **(c) Multilinha só na função:** [extract_key:68](C:/dev/project-hunter/infra/scripts/setup_env.sh:68) aceita texto multilinha e preserva `==`; porém [read_secret:97](C:/dev/project-hunter/infra/scripts/setup_env.sh:97) lê uma linha por vez. Colagem arbitrária pode consumir chaves no prompt errado. Corrigir a captura ou retirar a promessa de colagem multilinha.

**Concordâncias:**

- **(a)** [as_deploy:65](C:/dev/project-hunter/infra/scripts/bootstrap_vps.sh:65) funciona com sudo administrativo padrão. Falha se a política permitir apenas executar como root, ou se root não tiver `sudo` instalado.
- **(b)** [count_ssh_keys:72](C:/dev/project-hunter/infra/scripts/bootstrap_vps.sh:72) não retorna vazio nos caminhos tratados: arquivo vazio, ausente ou erro resultam em `0`.
- **(d)** O [trap:217](C:/dev/project-hunter/infra/scripts/setup_env.sh:217) remove somente o temporário; após [mv:252](C:/dev/project-hunter/infra/scripts/setup_env.sh:252), não apaga o `.env`. A substituição atômica está correta.
- [Compose mínimo:131](C:/dev/project-hunter/infra/scripts/bootstrap_vps.sh:131), [mktemp do uv:217](C:/dev/project-hunter/infra/scripts/bootstrap_vps.sh:217) e [fail2ban:279](C:/dev/project-hunter/infra/scripts/bootstrap_vps.sh:279): correções adequadas para os problemas apontados.
- Backup: [erro com exit 1:34](C:/dev/project-hunter/infra/vps/backup_postgres.sh:34) e [-type f:70](C:/dev/project-hunter/infra/vps/backup_postgres.sh:70) estão corretos.
- **(e)** [Caddyfile:49](C:/dev/project-hunter/infra/vps/Caddyfile:49): sintaxe correta; mascara `token` em `request.uri`, conforme a [documentação oficial](https://caddyserver.com/docs/caddyfile/directives/log#query) e consistente com seu `validate`.