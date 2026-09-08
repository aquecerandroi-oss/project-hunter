# Notas T3.30 — a revisão da Astra sobre o Lab (2026-09-08) entra no Obsidian

## STATUS

`DONE` — os sete itens do brief entregues, `obsidian_lint.py` verde (exit 0), nada commitado, nada
fora de `obsidian/**` tocado (mais este arquivo de notas, exigido pelo próprio brief).

## FILES

Criado:
- `obsidian/06-DECISIONS/Revisoes-Astra/2026-09-08-shadow-lab-pronto.md` — a revisão inteira no
  formato da pasta (frontmatter `by: astra`, callouts veredito/alerta, seções "o que ela concordou",
  os três MUST-FIX com arquivo:linha e cenário, nice-to-have, "o que eu faria diferente", tabela "o
  que virou tarefa", Relacionadas, Fontes). Links `[[...]]` para EXP-0006, EXP-0005, Experiments
  Index, Execution Engine, Paper Trading, Risk Engine, Portfolio, Open Bugs, Architecture Decisions,
  Dialogos/SHADOW, Diario/2026-09-08, Mente da Sexta-feira.

Modificados:
- `obsidian/06-DECISIONS/Revisoes-Astra/Index.md` — entrada nova no topo da lista (a página não
  ficaria órfã) e `updated: 2026-09-08`.
- `obsidian/07-BUGS/Open Bugs.md` — **duas seções novas**, +149 linhas:
  - *Abertos pela revisão da Astra "o Lab está pronto?" (2026-09-08)*: 11 itens, todos com estado
    **"aberto 2026-09-08 (Astra)"**, arquivo:linha e cenário de falha — 4 de replicação (dono
    **T3.18c**), 5 da autonomia + o DSN de dono (**T3.29** / **T3.15d**), a negação de serviço
    compartilhada do bucket do `web` (**T3.28a-seguimento**), o `FORWARDED_ALLOW_IPS` que não resolve
    DNS (LOW, já contornado) e a correção de texto de `REPLICATION.md` §46/§78 (orquestrador). O
    **backup** entrou como **"a comprovar em T3.29" (item 6)**, explicitamente **não** como bug.
  - *Aberto na tarde de 2026-09-08 (revisão do commit `50932ec`)*: o CRITICAL do `earliest_known`
    obsoleto dentro do ciclo — **acréscimo além do brief**, ver CONCERNS.
- `obsidian/05-EXPERIMENTS/EXP-0006-momentum-piso-de-custo.md` — **+32 linhas, 0 remoções**: seção
  datada `### Próximas medições (Astra) — 2026-09-08` com os cinco pontos, inserida **entre** as
  Pendências e o marcador `### Avaliação de <próxima data>`. Hipótese, Protocolo e a avaliação de
  2026-09-08 **intocados** (o próprio linter confirma: `exp_reescrita: 0`). O título deliberadamente
  **não** começa por "Avaliação de" — não é avaliação e não há número novo nela.
- `obsidian/03-TRADING/Execution Engine.md` — status de "planejado / sem implementação" para
  "implementado e rodando na VPS, ponte desligada, caminho autônomo nunca rodou de ponta a ponta"; a
  **tabela dos 7 pré-requisitos** da T3.29 com o estado de cada linha (5 × "não medido", backup "não
  comprovado", DSN "aberto") e o arquivo:linha do risco; heading da Interface corrigido; Relacionadas
  e Fontes atualizadas.
- `obsidian/03-TRADING/Paper Trading.md` — status atualizado (carteira aberta, motor rodando, 0
  ordens porque a ponte está desligada; 154 sinais / 0 propostas / 0 posições / 0 trades) e seção
  apontando para a tabela dos sete itens.
- `obsidian/03-TRADING/Risk Engine.md` — seção nova *Pré-requisitos efetivos da autonomia paper*
  distinguindo **sinal paper de execução paper**, com as quatro linhas que tocam o motor (admissão,
  qualidade do MTM, proteção degradada, β indisponível); `status:` do frontmatter reconciliado (o
  deploy na VPS já aconteceu).
- `obsidian/00-HOME.md` — bloco "Atualizado em 2026-09-08 (fim da tarde)" no topo de *Onde estamos
  agora* (v3 paper ativa 05:57:30Z / 02:57 de Brasília e emitindo desde 06:00:09Z; 154 sinais, 0
  propostas/posições/trades; worker na VPS; 7 pré-requisitos com 5 não medidos; 4 furos da
  replicação; deploys `385dac6` e `50932ec` com o rollback dos market-worker às ~14:10Z; Clerk
  destravado às 13:22Z; o 429 do SSR) + três linhas da tabela de módulos e a legenda do canvas do
  momentum reconciliadas.
- `obsidian/09-OPERATIONS/Diario/2026-09-08.md` — **terceiro bloco do dia** ("Plantão da tarde"),
  acrescentado sem tocar os dois anteriores: veredito, o que foi medido (e o que **não** foi), o que
  bloqueia, decisões, o que foi feito, os dois achados operacionais (o CRITICAL do `before_listing`
  com BTCUSDT 5 / UNIUSDT 5 na VPS às 14:00Z e o rollback às ~14:10Z; o 429 que derrubava a tela às
  13:37Z), o que ficou em aberto, saúde e o que preciso do Everton.

Não tocados: `docs/**` (item 6 do brief — a correção de `REPLICATION.md` §46/§78 ficou anotada em
Open Bugs para o orquestrador), `apps/**`, `services/**`, `infra/**`, `.env*`.

## LINT (saída real)

```
$ uv run python infra/scripts/obsidian_lint.py
LINT DA BASE OBSIDIAN — 185 NOTA(S) ANALISADA(S)
Resumo — Links mortos: 0, Links ambíguos: 0, Notas órfãs: 0, Frontmatter incompleto: 0, Valores fora do vocabulário: 0, Procedência da Knowledge Base (KB-*): 0, Reescrita de experimentos (append-only): 0.

RESULTADO: base limpa
$ echo $?
0
```

Baseline antes das edições: 184 notas, mesma saída limpa. A nota nova é a 185ª.

```
$ git status --short -- obsidian/
 M obsidian/00-HOME.md
 M "obsidian/03-TRADING/Execution Engine.md"
 M "obsidian/03-TRADING/Paper Trading.md"
 M "obsidian/03-TRADING/Risk Engine.md"
 M obsidian/05-EXPERIMENTS/EXP-0006-momentum-piso-de-custo.md
 M obsidian/06-DECISIONS/Revisoes-Astra/Index.md
 M "obsidian/07-BUGS/Open Bugs.md"
 M obsidian/09-OPERATIONS/Diario/2026-09-08.md
?? obsidian/06-DECISIONS/Revisoes-Astra/2026-09-08-shadow-lab-pronto.md

$ git diff --stat -- obsidian/
 8 files changed, 409 insertions(+), 18 deletions(-)
```

## CONCERNS

1. **Acrescentei um bug que o brief não pedia** — o CRITICAL do `earliest_known` obsoleto
   (`50932ec`, hotfix T3.7e, mitigado por rollback às ~14:10Z). Motivo: é um achado de **produção com
   perda de janela histórica** (BTCUSDT 5, UNIUSDT 5 `unrecoverable` às 14:00Z) que só existia em
   `.claude/state/brief-T3.7e-*.md`; sem entrada em `Open Bugs` ele desapareceria da base assim que o
   brief saísse do topo da pasta. Se o orquestrador preferir, é uma seção isolada e sai com um corte
   limpo.
2. **Os deploys de hoje não foram verificados por mim.** O brief nomeia `385dac6` e `50932ec` e o
   rollback está documentado no brief da T3.7e ("VPS market-workers were rolled back to image
   `385dac6` at ~14:10Z"); eu **não** abri SSH nesta tarefa (escopo de escrita `obsidian/**`). O
   Diário diz isso explicitamente na tabela de Saúde: "VPS não verificado neste turno".
3. **"Não medido" é o rótulo de todas as sete linhas da autonomia** — nenhuma delas afirma defeito em
   produção, e escrevi isso na página para que ninguém leia a tabela como lista de bugs confirmados.
   A T3.29 é justamente o que converte "não medido" em número.
4. **A T3.18c não existe como brief.** Os quatro achados de replicação estão registrados com
   arquivo:linha e cenário, apontando para uma tarefa que o orquestrador ainda precisa escrever — se
   ela nunca for escrita, os bugs ficam sem dono efetivo.
5. **A seção nova da EXP-0006 não é uma avaliação e o linter não a trata como tal** (o título não
   casa com `^### Avaliação de `). Isso é deliberado — ela não tem número medido —, mas significa que
   ela **não** está protegida pela regra append-only do linter; uma edição futura dela passaria
   despercebida.
6. **Uma frase do brief da T3.28a estava errada** ("nome/IP de `web`" na lista de confiança): o
   Uvicorn instalado não resolve nome por DNS. A implementação escolheu IP fixo, então não há defeito
   em produção — registrei como LOW só para impedir que alguém "simplifique" de volta para o nome.
