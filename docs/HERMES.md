# A Sexta-feira no Hermes — runbook da mudança (2026-09-07)

A Sexta-feira continua trabalhando neste repositório; o que muda é o motor onde ela roda: de uma sessão do Claude Code (`.claude/agents/sexta-feira.md`, cota semanal da conta Claude) para um **perfil do Hermes Agent** (Nous Research, desktop instalado em `%LOCALAPPDATA%\hermes`), que roda com outro modelo e outra cota. O papel, as regras e a memória são os mesmos.

## O que é o quê

| Peça | Onde | O que faz |
|---|---|---|
| Perfil `sexta-feira` | `%LOCALAPPDATA%\hermes\profiles\sexta-feira\` | É o Bot que aparece na aba **Bots** do Hermes Desktop: config, SOUL, memória, skills e rotinas próprios. Não toca no perfil `default`. |
| `infra/hermes/SOUL.md` | repo → copiado para o perfil | Identidade e voz da Sexta-feira (slot nº 1 do prompt do Hermes). |
| `.hermes.md` (raiz do repo) | repo | Contexto do projeto que o Hermes carrega sozinho quando o terminal está no repo. Manda ler `CLAUDE.md` primeiro (o Hermes carrega **um** arquivo de contexto por sessão, e `.hermes.md` tem prioridade sobre `AGENTS.md` e `CLAUDE.md`). |
| `infra/hermes/memories/{MEMORY,USER}.md` | repo → semeados uma vez | Fatos curtos que precisam sobreviver ao início da sessão (2.200 e 1.375 caracteres, limite do Hermes). A memória de verdade continua sendo `obsidian/`. |
| `infra/hermes/skills/project-hunter/*` | repo → copiados para o perfil | Três skills: `sexta-feira-plantao` (o turno), `sexta-feira-relatorio` (formatos de relatório e aprovação), `sexta-feira-briefs` (brief → delegação → revisão → commit). |
| Rotina `[bot:sexta-feira] plantão` | cron do Hermes | A cada hora, roda a skill do plantão dentro do repo e entrega no chat do Bot. Só é criada com `--routine`. |
| MCP `obsidian` | `config.yaml` do perfil | O mesmo servidor de `.mcp.json` (vault `vault/` dentro do repo). |

## Instalar ou atualizar

```bash
bash infra/hermes/install.sh
```

Cria o perfil (clone do perfil ativo: config, `.env` do Hermes e skills), copia o SOUL, semeia a memória se ainda não existir, copia as skills, aponta `terminal.cwd` para o repo e registra o servidor MCP. Rodar de novo só atualiza SOUL e skills; a memória que a Sexta-feira já escreveu não é sobrescrita.

```bash
bash infra/hermes/install.sh --routine
```

Registra também a rotina horária do plantão (aparece em `hermes cron list` e no painel Routines do Bot).

## Depois de instalar (com as suas mãos, Everton)

1. Abra o Hermes Desktop → aba **Bots** → `sexta-feira`. Em **Edit Profile**, fixe o modelo (recomendação: o mesmo GPT-6 da Astra, que já é metade da mente dela; se preferir outro, qualquer par provedor/modelo serve). Confira que a skill `project-hunter/*` e o servidor MCP `obsidian` estão marcados.
2. Primeira mensagem: "Sexta-feira, situação". Ela deve ler `.hermes.md`, `CLAUDE.md`, `obsidian/00-HOME.md`, `milestone.json` e responder com a tabela feito / rodando / bloqueado / precisa de você.
3. Se o `codex` estiver logado, a Astra continua funcionando por `infra/scripts/astra.sh`. Se o `claude` estiver logado, ela pode usar `claude -p` como executor extra; com a cota estourada ela não insiste.

## O que fica igual

- Regras duras de `CLAUDE.md`; nada ativa sozinho; `.env*` é seu; sem segredo em chat, nota ou commit.
- Só você decide: escopo de milestone, serviços pagos, domínio, `ENABLE_*` em produção, ativar versão `paper`, dinheiro real, apagar dados, `force-push`, design.
- Delegado a ela: aprovar relatórios de milestone e testes em seu nome; decisões D1–D13.
- Commits dela levam o trailer `Co-Authored-By: Sexta-feira <sexta-feira@project-hunter.local>`.

## O que muda na prática

- O elenco de especialistas (`.claude/agents/*.md`) vira **cartões de papel** que ela cola no `delegate_task` do Hermes (até 3 em paralelo). Não existe mais o `Agent` do Claude Code.
- Revisões adversariais: `code-reviewer` e os revisores por caminho continuam obrigatórios, executados como subagentes do Hermes ou pela Astra.
- Segurança do terminal: o Hermes roda o shell local com `cwd` no repo. Nunca em background, no máximo 4 suítes com testcontainers, deploy só pelo `compose.sh`.

## Rodar as duas em paralelo por uns dias

A definição do Claude Code (`.claude/agents/sexta-feira.md`) continua no repo. Enquanto a mudança assenta, as duas podem coexistir: a do Hermes é a principal; a do Claude Code só entra se você abrir uma sessão lá. A memória compartilhada (`obsidian/`, `.claude/state/`) evita duas verdades. Quando estiver satisfeito, apague a rotina antiga do Claude Code ("Sexta-feira de plantão") para não haver dois plantões escrevendo o mesmo diário.

## Desfazer

`hermes profile delete sexta-feira` remove o perfil (a memória e o histórico dele vão junto). O repo não perde nada: tudo que ela escreve de duradouro está em `obsidian/` e `.claude/state/`.
