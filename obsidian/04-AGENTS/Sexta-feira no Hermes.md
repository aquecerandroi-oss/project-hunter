---
tags: [agentes, hermes, sexta-feira]
updated: 2026-09-08
status: vivo
owner: sexta-feira
---

# Sexta-feira no Hermes

> [!decisao] A casa voltou ao Claude Code em 2026-09-08 (`c2ee96b`)
> **O Hermes deixou de ser a casa da Sexta-feira.** Em 2026-09-08 o Everton decidiu que a
> Sexta-feira volta a rodar como **agente do Claude Code** (`.claude/agents/sexta-feira.md`, com o
> `.claude/settings.json` do projeto apontando para ela); o **perfil do Hermes continua existindo
> como executor opcional, sem rotina** — ninguém abre plantão nele, e nada agenda tarefa por ele.
> A mudança está em `docs/HERMES.md` e no commit `c2ee96b`.
>
> **Por que a página continua aqui:** ela registra a passagem de 2026-09-07/08 pelo Hermes (o motivo
> foi a cota semanal da conta Claude estourada) e as **regras da casa** que nasceram lá e valem para
> qualquer motor — um brief manda em quem o executa, `git` antes do relatório, um brief por tarefa.
> O que está escrito abaixo descreve **aquele** período; leia como histórico, não como o arranjo de
> hoje.

> A Sexta-feira continua trabalhando neste repositório; o que muda é o motor onde
> ela roda: de uma sessão do Claude Code para um **perfil do Hermes Agent** (Nous
> Research). O papel, as regras e a memória são os mesmos. Runbook completo em
> `docs/HERMES.md`.

## O que mudou

- **Motor:** de Claude Code (`.claude/agents/sexta-feira.md`, cota semanal da conta
  Claude) para Hermes Agent (perfil `sexta-feira` em `%LOCALAPPDATA%\hermes\profiles\`).
  Outro modelo, outra cota, mesmo papel.
- **Delegação:** o elenco de especialistas (`.claude/agents/*.md`) vira cartões de
  papel colados no `delegate_task` do Hermes (até 3 em paralelo). Não existe mais o
  `Agent` do Claude Code.
- **Astra:** continua o segundo motor via `infra/scripts/astra.sh` (Codex CLI,
  GPT-6). Cota do Codex esgotada até 2026-09-12; quando voltar, a revisão
  adversarial do parecer do M2 é a primeira coisa a rodar.
- **Claude Code:** opcional e limitado por cota. Se o `claude` CLI estiver logado,
  `claude -p` pode rodar como executor extra; com a cota estourada (aconteceu em
  2026-09-07), não insiste.

## Regras da casa

- **Um brief por tarefa.** Se `.claude/state/brief-<tarefa>.md` já existe, ele é o
  contrato; não escreva uma segunda versão. O brief manda em quem o executa,
  inclusive na Sexta-feira: se ele diz "não commita", você devolve o diff e não
  commita.
- **Commits da Sexta-feira no Hermes** levam o trailer
  `Co-Authored-By: Sexta-feira <sexta-feira@project-hunter.local>`.
- **Git antes do relatório.** Antes de escrever STATUS em qualquer relatório, rode
  `git log -1` e `git status -sb` e descreva o que de fato aconteceu. Um relatório
  que diz "não commitado" com um commit no `main` é pior do que o commit.
- **index.lock:** se aparecer, espere 30 s e tente de novo.
- **PATH:** prefixar todo shell com `$HOME/.local/bin` e `/c/Program Files/nodejs`.
  Python só via `uv run`; um testcontainers por `pytest`, primeiro plano, no máximo
  4 ao mesmo tempo; nunca shell em background.
- **Deploy da VPS:** `MARKET_SHARDS=4 bash infra/vps/compose.sh update` é o único
  comando. Nunca `docker compose` manual na VPS.

## O que fica igual

- Regras duras de `CLAUDE.md`: nada ativa sozinho; `.env*` é do Everton; sem
  segredo em chat, nota ou commit; `Decimal` em dinheiro; UTC em tempo; RLS em
  tenant; mutação é auditada.
- Só o Everton decide: escopo de milestone, serviços pagos, domínio,
  `ENABLE_*` em produção, ativar versão `paper`, dinheiro real, apagar dados,
  `force-push`, design (`docs/DESIGN.md`).
- Delegado à Sexta-feira: aprovar relatórios de milestone e testes em nome dele;
  decisões D1–D13.
- A memória de verdade continua sendo `obsidian/` e `.claude/state/`; o
  `MEMORY.md`/`USER.md` do Hermes só carrega os fatos curtos que precisam
  sobreviver ao início da sessão (2.200 e 1.375 caracteres, limite do Hermes).

## Relacionadas

[[Mente da Sexta-feira]] · [[Architecture Decisions]] · `docs/HERMES.md` (runbook
completo) · `.claude/agents/sexta-feira.md` (cartão original, ainda no repo)
