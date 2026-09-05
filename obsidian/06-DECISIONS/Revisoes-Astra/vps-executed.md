---
tags: [astra, revisao]
updated: 2026-09-05
fonte: .claude/state/astra-review-vps-executed.md
---

# Revisão da Astra — vps-executed

Parte da [[Mente da Sexta-feira]]. Índice: [[Index|todas as revisões]]. Diálogos relacionados: [[Dialogos/M1|M1]], [[Dialogos/M2|M2]].

**Astra: com o estado executado que você informou, eu seguiria com o backend privado agora. Não vejo motivo para refazer o bootstrap.** Minha revisão foi estática: não acessei a VPS, não li `.env`, não modifiquei arquivos nem fiz commit.

**(1) Must-fixes do parecer anterior**

Os oito itens não estão integralmente encerrados, mas os erros que impediam a execução foram corrigidos:

| Item anterior | Código atual |
|---|---|
| Execução como root | Corrigida com `as_deploy()` usando `sudo -u`, inclusive no Git: [bootstrap_vps.sh:65](C:/dev/project-hunter/infra/scripts/bootstrap_vps.sh:65), [bootstrap_vps.sh:325](C:/dev/project-hunter/infra/scripts/bootstrap_vps.sh:325). |
| Contagem SSH | Corrigido o `0` duplicado e ampliado o reconhecimento de tipos/opções: [bootstrap_vps.sh:72](C:/dev/project-hunter/infra/scripts/bootstrap_vps.sh:72). Ressalva abaixo. |
| CORS | Removida a URL simples do setup e override; wrapper rejeita esse formato: [setup_env.sh:241](C:/dev/project-hunter/infra/scripts/setup_env.sh:241), [docker-compose.prod.yml:67](C:/dev/project-hunter/infra/vps/docker-compose.prod.yml:67), [compose.sh:36](C:/dev/project-hunter/infra/vps/compose.sh:36). |
| Segredo terminado em `=` | Corrigido: preserva valor puro e remove apenas a primeira atribuição: [setup_env.sh:75](C:/dev/project-hunter/infra/scripts/setup_env.sh:75). |
| Escrita atômica | Implementados recusa de symlink, `mktemp`, permissão restrita e substituição por `mv`: [setup_env.sh:213](C:/dev/project-hunter/infra/scripts/setup_env.sh:213), [setup_env.sh:255](C:/dev/project-hunter/infra/scripts/setup_env.sh:255). |
| Versão mínima Compose | Validada explicitamente; a versão informada satisfaz o mínimo: [bootstrap_vps.sh:131](C:/dev/project-hunter/infra/scripts/bootstrap_vps.sh:131). |
| Backup escondendo erro | Corrigido: falha de Compose retorna 1, banco parado retorna 0: [backup_postgres.sh:41](C:/dev/project-hunter/infra/vps/backup_postgres.sh:41). |
| Integridade do backup | **Parcial:** comentário esclarecido, mas continua apenas `pg_restore --list`: [backup_postgres.sh:59](C:/dev/project-hunter/infra/vps/backup_postgres.sh:59). |

Sobram estas partes do pedido original:

- **SSH:** não existe comprovação de uma segunda conexão por chave antes de desabilitar senha. O script reconhece texto parecido com chave e aplica o endurecimento; não prova posse da chave privada nem autenticação bem-sucedida: [bootstrap_vps.sh:295](C:/dev/project-hunter/infra/scripts/bootstrap_vps.sh:295). Isso permanece uma lacuna para novas instalações. Nesta VPS, uma nova conexão por chave bem-sucedida encerra a preocupação operacional; executar o script duas vezes, sozinho, não comprova isso.
- **Backups:** faltam leitura integral, restauração ensaiada e fiscalização da idade do último backup. O script verifica o índice e depois aplica retenção: [backup_postgres.sh:65](C:/dev/project-hunter/infra/vps/backup_postgres.sh:65), [backup_postgres.sh:77](C:/dev/project-hunter/infra/vps/backup_postgres.sh:77). A documentação recomenda restauração, mas não a implementa: [README.md:87](C:/dev/project-hunter/infra/vps/README.md:87). O PostgreSQL define `--list` como listagem do índice, não teste de restauração. [Documentação oficial](https://www.postgresql.org/docs/16/app-pgrestore.html).

**Eu não bloquearia o início da coleta por essas pendências de backup; exigiria resolvê-las antes de depender dos dumps para preservar dados importantes.**

**(2) Sem domínio: o que quebra e o que subir**

**Não encontrei prova de que Clerk dev necessariamente recuse esse IP.** O comentário “costuma recusar” em [Caddyfile:10](C:/dev/project-hunter/infra/vps/Caddyfile:10) não sustenta uma afirmação categórica. A documentação confirma sessões distintas e segurança relaxada em desenvolvimento, sem estabelecer nessa página uma proibição geral de IP. [Clerk: ambientes](https://clerk.com/docs/guides/development/managing-environments).

Os efeitos concretos são:

- O setup gera `http://IP`, `ws://IP/ws` e `:80`: **não há TLS nesse caminho**. [setup_env.sh:180](C:/dev/project-hunter/infra/scripts/setup_env.sh:180).
- Se o login não estabelecer sessão, as páginas protegidas ficam inacessíveis porque passam por `auth.protect()`: [middleware.ts:27](C:/dev/project-hunter/apps/web/middleware.ts:27). Isso precisa de teste de navegador; não foi provado pelo bootstrap.
- **Subir Caddy normalmente também puxa web**, pois depende da saúde dela. Portanto, ele não serve atualmente como borda independente para uma implantação só do backend: [docker-compose.prod.yml:125](C:/dev/project-hunter/infra/vps/docker-compose.prod.yml:125).

Depois de Everton criar a configuração, recomendo que ele execute:

```bash
bash infra/vps/compose.sh up api market-worker postgres redis
```

O wrapper aceita essa seleção; `migrate` entra automaticamente pelas dependências de API/worker. [compose.sh:51](C:/dev/project-hunter/infra/vps/compose.sh:51), [docker-compose.yml:82](C:/dev/project-hunter/infra/docker/docker-compose.yml:82), [docker-compose.yml:99](C:/dev/project-hunter/infra/docker/docker-compose.yml:99).

**Deixaria web e Caddy para domínio + HTTPS.** Nesse estágio inicial, a API fica em `127.0.0.1:8000`, acessível por túnel SSH; **não haverá aplicação em `http://169.58.116.99` nem endpoint público para webhooks**. [docker-compose.prod.yml:80](C:/dev/project-hunter/infra/vps/docker-compose.prod.yml:80).

Mesmo sem web, staging exige os segredos Clerk, inclusive webhook, no `Settings` compartilhado. Não dá para simplesmente omiti-los porque só vai rodar coleta: [settings.py:125](C:/dev/project-hunter/packages/core/hunter_core/settings.py:125). Sem `.env`, o wrapper recusa execução explicitamente — comportamento esperado agora: [compose.sh:21](C:/dev/project-hunter/infra/vps/compose.sh:21).

Quando houver domínio, ajustar URLs e reconstruir web: as variáveis públicas entram no build. [docker-compose.prod.yml:94](C:/dev/project-hunter/infra/vps/docker-compose.prod.yml:94).

**(3) Riscos reais no estado informado**

**Não identifiquei uma exposição crítica demonstrada que exija parar essa VPS agora.** Os riscos concretos são:

- **Comprometer `hunter` equivale a comprometer o host.** Uma chave SSH roubada ou código malicioso executado nessa conta permite usar `sudo` sem senha; o grupo Docker também concede privilégios equivalentes a root. Tirar somente `NOPASSWD` não resolve essa equivalência. [bootstrap_vps.sh:165](C:/dev/project-hunter/infra/scripts/bootstrap_vps.sh:165), [Docker: privilégios do grupo](https://docs.docker.com/engine/install/linux-postinstall). Trate `hunter` como conta administrativa.
- **Se publicar o aplicativo autenticado em HTTP**, um atacante no caminho da conexão pode interceptar tráfego e modificar a página entregue, comprometendo sessões e ações do usuário. Esse risco nasce ao publicar/usar a aplicação, não da instalação atual. O modo sem domínio gera explicitamente HTTP/WS: [setup_env.sh:180](C:/dev/project-hunter/infra/scripts/setup_env.sh:180).
- **Após subir os serviços, um processo comprometido recebe segredos além do necessário**, porque API, worker e web herdam o arquivo inteiro. Isso amplia o impacto de uma falha de execução remota; não significa que os segredos sejam automaticamente enviados ao navegador. [docker-compose.yml:76](C:/dev/project-hunter/infra/docker/docker-compose.yml:76), [docker-compose.yml:96](C:/dev/project-hunter/infra/docker/docker-compose.yml:96), [docker-compose.yml:135](C:/dev/project-hunter/infra/docker/docker-compose.yml:135).

A perda do disco continua sendo risco de perda simultânea do banco e dos backups locais, explicitamente reconhecido em [README.md:94](C:/dev/project-hunter/infra/vps/README.md:94). Isso merece prioridade assim que a coleta acumular dados que vocês precisem preservar.