# notes-obsidian-meme-2026-09-12 — estrutura Obsidian da linha meme

Tarefa: documentation-writer, brief do orquestrador a partir da diretriz do Everton, 2026-09-12
por volta de 04:5x BRT (meta de US$ 7 M em 30 dias, mapear pump.fun, Obsidian decisório, Lab meme
contínuo). Escopo de escrita: `obsidian/**` e este arquivo. Nenhum código, nenhum `docs/`, nenhum
`.env*` tocado. Nada commitado. `git status`/`git diff`/`git log` não usados para alterar estado
(só leitura, quando usados). Nenhum shell em background; todo comando em primeiro plano.

## Arquivos criados

- `obsidian/06-DECISIONS/2026-09-12-meta-7m-e-lab-meme.md` — as quatro diretrizes verbatim com hora,
  a aritmética honesta do alvo (350× / +21,6 %/dia a partir de R$ 100.000≈US$ 20.000; 70× /
  +15,2 %/dia a partir de US$ 100.000) como conta sobre o alvo, nunca previsão, o que NÃO muda
  (dinheiro real só por switch do Everton depois do fluxo verificado; paper primeiro; funil único;
  `docs/RISK_ENGINE_MEME.md` quando T4.4 fechar), e a especificação do painel "Meta" (§4) para a
  tela `/meme` (T4.3b): capital, retorno diário exigido, retorno diário medido, dias restantes —
  marcada explicitamente como não implementada.
- `obsidian/03-TRADING/Meme/README.md` — hub: o que é uma "estratégia" de meme aqui (conjunto de
  regras pré-registrado sobre a curva, `EXP-M<n>`), distinção entre `M-A/M-B/M-E/M-G` (candidatos
  informais de 2026-09-06), `EXP-M<n>` (pré-registro formal) e `M-P<n>` (fila de hipóteses); tabela
  do que é planejado (T4.1–T4.6) com status real de cada peça nesta data (nenhuma implementada).
- `obsidian/02-MARKET/Meme/README.md` — hub: como os arquivos diários do plantão de pump.fun são
  organizados (`AAAA-MM-DD.md`, um por dia), diferença para `02-MARKET/Plantao/` (geral) e para o
  Diário Meme (operacional) e o Conhecimento (curado). **Não li nem editei**
  `obsidian/02-MARKET/Meme/2026-09-12.md` — não existia no disco no momento desta tarefa; outro
  agente do plantão está escrevendo esse arquivo nesta mesma sessão.
- `obsidian/09-OPERATIONS/Diario-Meme/README.md` — hub: formato do diário operacional do Lab meme
  (estado da carteira paper, apostas do dia, R em SOL, distância à meta, incidentes, o que o Lab
  aprendeu) — marcado como planejado (T4.6), pasta ainda vazia, `infra/scripts/meme_diary.py` ainda
  não existe no repositório.
- `obsidian/11-KNOWLEDGE/README-meme.md` — inventário das `KB-00xx` de tema meme/pump.fun: a rodada
  original de dez notas (KB-0056–KB-0065, 2026-09-06) e o que chegou depois (KB-0091, 2026-09-12).
  Registra explicitamente que a expectativa do brief ("KB-0084…KB-0090 parcialmente") **não se
  confirmou** — nenhuma das duas tem tag `meme` nem trata do tema; nenhuma nota entre KB-0066 e
  KB-0090 é de meme.
- `.claude/state/notes-obsidian-meme-2026-09-12.md` — este arquivo.

## Arquivo editado (só o cabeçalho, não as linhas)

- `obsidian/00-INBOX/Hipoteses-do-plantao.md` — acrescentado um parágrafo entre a introdução e a
  tabela explicando o prefixo `M-P<n>` (a partir de 2026-09-12, decisão do Everton) e deixando
  registrado que as hipóteses de meme já existentes na fila (H-P25, H-P27, H-P28, H-P29, H-P30)
  mantêm a numeração `H-P` original — **nenhuma linha da tabela foi tocada**, só o texto acima dela.

## Achado a reportar (inconsistência entre o brief e o estado real da base)

O brief desta tarefa citava a fila de hipóteses como usando o prefixo `M-P` e um intervalo
"KB-0084…KB-0090 parcialmente" para conhecimento de meme. Nenhum dos dois é verdade hoje: a fila usa
`H-P` para tudo, inclusive meme (H-P25/27/28/29/30, cada uma marcada inline como origem T4.0); e o
intervalo KB-0084–KB-0090 não tem nenhuma nota de meme (só KB-0091 é meme, fora do intervalo citado).
Optei por **registrar a convenção nova (`M-P` a partir de hoje) sem fingir que ela já existia antes**,
e por **corrigir a lista de KBs para o inventário real** em vez de forçar o intervalo esperado — ver
`obsidian/00-INBOX/Hipoteses-do-plantao.md` (parágrafo novo) e `obsidian/11-KNOWLEDGE/README-meme.md`
(seção "Nota sobre uma expectativa que não se confirmou").

## Linter

`uv run python infra/scripts/obsidian_lint.py` — ver saída no relatório final da tarefa.
