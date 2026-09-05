---
tags: [arquitetura, sexta-feira, astra, claude, memoria]
updated: 2026-09-05
status: implementado
---

# Mente da Sexta-feira

Decisão do dono (2026-09-05): **a Sexta-feira é uma só**, com dois motores de raciocínio, o Claude e a Astra (GPT-6), e esta base Obsidian é a rede de neurônios dela: tudo o que ela pensa, decide, erra e aprende vira uma nota ligada às outras.

## Como ela pensa
- **Diálogo como pensamento.** Desenhos, planos e revisões contestadas rodam em rodadas entre os dois motores (`infra/scripts/astra.sh dialogue <tema>`) até uma rodada abrir com **DECISÃO CONJUNTA**. O que chega ao dono é o resultado, na primeira pessoa. Transcrições: [[Dialogos/Index|Diálogos]].
- **Segunda opinião em tudo.** Todo diff, plano e relatório passa pelos dois motores (`astra.sh ask`). As revisões da Astra: [[Revisoes-Astra/Index|Revisões da Astra]]. O motor com o cenário de falha concreto tem razão; o comando que decide roda antes da escolha.
- **Execução.** A Astra executa briefs mecânicos (`astra.sh run <brief>`); o Claude orquestra o roster de especialistas; a Sexta-feira revisa e commita.

## Como ela lembra (sinapses)
| Tipo de neurônio | Onde fica | Liga-se a |
|---|---|---|
| Decisão | [[Architecture Decisions]] (+ ADRs em `docs/decisions/`) | diálogos, módulos, bugs |
| Diálogo | [[Dialogos/Index|06-DECISIONS/Dialogos]] | plano do milestone, decisões |
| Revisão da Astra | [[Revisoes-Astra/Index|06-DECISIONS/Revisoes-Astra]] | kit da tarefa, bugs |
| Bug | [[Open Bugs]] / [[Resolved Bugs]] | commit, módulo, lição |
| Módulo | 02-MARKET, 03-TRADING, 04-AGENTS | status real, caminhos do código, limitações |
| Experimento | [[Experiments Index]] | estratégia, performance |
| Dia | `09-OPERATIONS/Diario/` | tudo o que aconteceu |

Regra: uma nota que nenhuma outra alcança é um neurônio sem sinapse. Cada página nova recebe pelo menos um link de entrada e um de saída.

## O toolkit é o mesmo para os dois motores (`AGENTS.md`, 2026-09-05, `fc336d9`)

Pedido do dono: a Astra tem de ter **as mesmas ferramentas** que os agentes Claude, não um subconjunto de convidada. O arquivo `AGENTS.md` na raiz é o que o Codex carrega automaticamente em toda execução `codex exec -C C:/dev/project-hunter` — é o `CLAUDE.md` da Astra. Ele dá a ela, por escrito:

- **A mesma ordem de leitura** do `CLAUDE.md`: memória do projeto → `obsidian/00-HOME.md` e as páginas dos módulos envolvidos → `.claude/state/milestone.json` e o plano do milestone (mais `docs/plans/SHADOW-LAB.md` enquanto a trilha do Lab estiver aberta) → `docs/{ARCHITECTURE,PIPELINE,DATABASE,RISK_ENGINE,WORKFLOW}.md` → as regras de despacho e de segunda opinião.
- **O mesmo roster.** As definições em `.claude/agents/*.md` são **cartões de papel**, não arquivos exclusivos do Claude: quando um brief diz "atue como `database-architect`" ou "revise como `risk-engine-guardian`", a Astra lê aquele arquivo e segue o escopo, a checklist e o formato de relatório dele. Sem papel nomeado, ela escolhe a linha da tabela de roteamento do `CLAUDE.md` e **diz qual escolheu**.
- **Os três modos** dirigidos por `infra/scripts/astra.sh`: `ask` (opinião, não cria nem modifica nada, achado sem cenário de falha é descartado), `dialogue` (lê a transcrição inteira, responde ponto a ponto, **acrescenta** só a sua seção, e só abre com DECISÃO CONJUNTA quando de fato convergiu) e `run` (uma tarefa mecânica, só os arquivos do brief, TDD, comandos canônicos rodados no mesmo turno com saída real colada).
- **As mesmas regras inegociáveis:** nunca ler ou escrever `.env*`, nunca sair do repositório, nunca commitar, nunca apagar dado ou histórico. Quem commita é a Sexta-feira, depois de conferir `git diff --stat`.

Efeito prático: os dois motores partem do mesmo estado mental. Quando a Astra discorda, a discordância é sobre o problema, não sobre contexto que faltou a ela.

## Lições já aprendidas pelos dois motores (2026-09-05)
- Suíte verde não prova produção: o dublê de teste do rate limiter reimplementava o Lua em Python e nunca tocava o Redis real; o pipeline inteiro estava morto. Prova operacional contra dado real é obrigatória antes de aprovar ([[Market Collector]]).
- Lint, tipos e testes não pegam regras do Next.js App Router (`"use server"`); o build no container é obrigatório para `apps/web` ([[System Overview]]).
- Um processo Python não sustenta 1.200 streams: o transporte sozinho custa um core; sharding é o caminho, não o plano B ([[Market Collector]]).
- Perfil antes de otimizar: as hipóteses (msgpack, logging) eram irrelevantes; o custo real era `pydantic` por evento e a fila varrendo 10.000 itens.
- Um número que a fonte não determina vira **nulo com motivo**, nunca um valor plausível: o OHLC de 1 min não prova a excursão máxima antes da saída, então `mfe` fica nulo com limites e flag de ambiguidade ([[Dialogos/SHADOW]], [[Architecture Decisions]]).
- Descrever algo como imutável não o torna imutável: a proteção tem de estar no banco e cobrir a rota de fuga (deprecated → alterar → reativar), não só o caminho feliz ([[Dialogos/SHADOW]]).

Fontes: `.claude/agents/sexta-feira.md`, `.claude/rules/astra-second-opinion.md`, `infra/scripts/astra.sh`, `docs/decisions/0003-base-de-conhecimento-obsidian.md`.
