# Fluxo de desenvolvimento (vibe-coding-toolkit aplicado ao Hunter)

Como o trabalho é planejado, despachado, revisado, commitado e reportado. Baseado no [vibe-coding-toolkit](https://github.com/soumatheusgomes/vibe-coding-toolkit) (ADR 0001). Os arquivos que materializam o fluxo:

| Peça | Onde | Origem |
|---|---|---|
| Instruções de projeto | `CLAUDE.md` | `templates/CLAUDE.md.template`, preenchido |
| Roster de especialistas | `.claude/agents/*.md` (12 agentes) | tabela de roteamento do toolkit, adaptada ao domínio |
| Regra de ondas paralelas | `.claude/rules/parallel-subagent-driven-development.md` | cópia literal |
| Hooks | `.claude/hooks/{hook-io,protect-secrets,session-context}.mjs`, `.claude/settings.json` | helper literal + dois hooks próprios |
| Memória camada 1 | `.claude/memory/` | prompt `06-memory-bootstrap` |
| Memória camada 2 | `docs/decisions/` (ADRs) | idem |
| Quality gates TS | `packages/config/eslint/` | `templates/eslint/`, regras byte a byte |
| Quality gates Python | `packages/config/ruff*.toml`, `infra/scripts/check_file_size.py` | mesma filosofia, sem equivalente pronto |
| Planos por milestone | `docs/plans/M<n>.md` | prompts `04` e `05` |
| Estado do milestone | `.claude/state/milestone.json` | injetado pelo hook de sessão |

## 1. Plugins recomendados (instalados pelo usuário, na própria sessão do Claude Code)

Não podem ser instalados pelo agente: `/plugin` é um comando da sessão do usuário.

```
/plugin marketplace add anthropics/claude-plugins-official
/plugin install superpowers@claude-plugins-official
/plugin marketplace add DietrichGebert/ponytail
/plugin install ponytail@ponytail
/plugin marketplace add JuliusBrussee/caveman
/plugin install caveman@caveman
```

Superpowers impõe brainstorm → plano → implementação → revisão com skills nomeadas; Ponytail mantém o "mínimo que resolve"; Caveman comprime a comunicação. O `CLAUDE.md` já codifica o essencial dos três para o caso de não estarem instalados.

## 2. Classificação de todo pedido

| Caminho | Quando | Cerimônia |
|---|---|---|
| **Spike** | pergunta de viabilidade | resposta; nenhum código permanente |
| **Bounded** | ≤ 3 arquivos, dentro de um fluxo que já existe | design em duas frases no chat → aprovação → implementa |
| **Architectural** | subsistema novo, mudança de interface, qualquer milestone | documento em `docs/` → aprovação explícita → plano em `docs/plans/` → ondas |

Na dúvida, o caminho mais pesado. Nunca rebaixar no meio da tarefa.

## 3. De milestone a plano

Cada milestone do `docs/ROADMAP.md` vira `docs/plans/M<n>.md` com:

- cabeçalho: objetivo, pré-requisitos, restrições globais;
- tabela de tarefas com `ID`, descrição, **`Files:`** (caminhos exatos), **`Depends-on:`**, **`Owner:`** (agente do roster), **tier de modelo**, **verificação** (comando ou comportamento observável; "deveria funcionar" não conta);
- tabela de ondas.

Regra de onda: duas tarefas ficam na mesma onda **somente se** nenhuma depende da outra (nem transitivamente) **e** os conjuntos de arquivos são disjuntos. `Files:` vago ou incerto → `Depends-on: tudo anterior` (degrada para serial; nunca gera corrida).

## 4. Execução de uma onda

1. Um brief por tarefa (a linha da tabela + contexto + docs a ler). O brief é autossuficiente: o subagente não vê esta conversa.
2. Despachar todos os implementadores da onda **numa única mensagem**, cada um com o tier de modelo decidido na tabela.
3. Implementadores seguem TDD, se autorrevisam, **não commitam**, e reportam `DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED` + arquivos tocados + saída real dos comandos.
4. O orquestrador commita **uma tarefa por vez, na ordem da onda**, capturando `HEAD` na hora antes de cada commit. Conventional commits.
5. Revisores da onda despachados juntos (só leitura): `code-reviewer` por tarefa; `security-reviewer` se tocou auth/segredos/webhooks/RBAC; `database-architect` se tocou migração; `risk-engine-guardian` se tocou `risk-core`, execução, kill switch ou propostas.
6. Achados `CRITICAL`/`HIGH` viram correção antes da próxima onda; `MEDIUM`/`LOW` a critério, registrados em KNOWN ISSUES.
7. Um único registro de progresso por onda (`.claude/state/milestone.json` e o plano).

Válvula de escape: duas tarefas que precisam tocar o mesmo arquivo são fundidas numa só ou isoladas em worktrees separados — nunca forçadas na mesma onda.

## 5. Tier de modelo por despacho

| Tier | Uso |
|---|---|
| haiku | exploração/grep, edição de um arquivo totalmente especificada |
| sonnet | implementação, integração, testes, revisão geral, DevOps, docs |
| opus | schema, quant, risco/execução, segurança, revisão final da branch |

Turnos importam mais que preço por token: modelo barato que gasta 3× mais turnos sai mais caro.

## 6. Quality gates

- **TypeScript:** `pnpm lint` (rápido, pre-commit) com `quality/max-lines` 350 em `error`, `quality/no-direct-console`, `quality/no-direct-data-access` e fronteira `components/** ↛ lib/server/**`; `pnpm lint:types` só em CI. Auto-checagem das regras e do config montado: `pnpm --filter @hunter/config test` (roda `verify:eslint-rules` e `smoke:eslint`).
- **Python:** `ruff.toml` bloqueia; `ruff.strict.toml` roda não-bloqueante em CI com contagem anotada; `check_file_size.py` aplica o mesmo teto de 350 linhas.
- **Promoção:** regra nova nasce em `warn` com a contagem escrita ao lado; vira `error` ao zerar. Nunca aumentar o teto para um arquivo passar; usar `ignore`/baseline com lista explícita.
- **Arquivo grande:** cortar por responsabilidade (lógica de negócio, UI, acesso a dados), um arquivo por commit, testes entre cada corte. Sem "costura natural", parar e dizer.

## 7. Hooks

| Hook | Evento | Comportamento |
|---|---|---|
| `protect-secrets.mjs` | `PreToolUse` Edit/Write | bloqueia (`exit 2`) escrita em `.env*` (exceto `*.example`), `.pem/.key/...` e conteúdo com cara de credencial; fail-open só quando não há evento utilizável |
| `session-context.mjs` | `SessionStart` | injeta HEAD, milestone atual, próxima ação e bloqueios; fail-open total |

Os dois usam `parseHookEvent` (trata `JSON.parse("null")`). Os comandos em `settings.json` só chamam `node` se ele existir no PATH. **Ainda não executados nesta máquina** (sem Node em 2026-09-04); teste manual obrigatório na T01 do M0:

```bash
echo '{"tool_input":{"file_path":"src/index.ts","content":"ok"}}' | node .claude/hooks/protect-secrets.mjs; echo "exit: $?"   # 0
echo '{"tool_input":{"file_path":".env.local","content":"x"}}' | node .claude/hooks/protect-secrets.mjs; echo "exit: $?"      # 2
echo 'null' | node .claude/hooks/protect-secrets.mjs; echo "exit: $?"                                                          # 0
echo '{}' | node .claude/hooks/session-context.mjs; echo "exit: $?"                                                            # 0 + JSON
```

## 8. Memória

Camada 1: `.claude/memory/MEMORY.md` (≤ 130 linhas) + arquivos de tópico; critério: "uma sessão futura ficaria surpresa e grata de saber isso antes de começar?". Camada 2: `docs/decisions/`. Migração sempre dedup → template → criar → ler de volta → só então apagar.

## 9. Fechamento de milestone

Relatório no formato §77 da especificação, com saída real de lint, typecheck, testes e build colada, mais atualização de `.claude/state/milestone.json`, `docs/ROADMAP.md` e ADRs quando houve decisão nova.
