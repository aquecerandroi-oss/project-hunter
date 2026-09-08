# notes-T3.41 — fim do dia no Obsidian: session_orb avaliada, variantes do momentum arquivadas, estresse, aposentadorias, Changelog

**Data:** 2026-09-08 (UTC; Brasília = UTC−3). **Dona:** sexta-feira.
**Brief:** `.claude/state/brief-T3.41-obsidian-fim-do-dia.md`. **Base:** `main` em `1926e53`
(HEAD ao terminar: `d829546`, commit de outra tarefa — T3.39b — que entrou durante a minha janela).
**Nada commitado.** **Escopo de escrita: só `obsidian/**`** (mais este arquivo de notas).
Nenhum `.env*` tocado, nenhum comando em segundo plano, nenhum `git stash`/`checkout --`/`restore`/
`reset`/`clean`/`commit -a`, nenhum container tocado, nenhum SQL rodado.

## STATUS

`DONE_WITH_CONCERNS`. Os oito itens do brief entregues; o linter da base fecha **verde** (saída real
abaixo). As concerns não mudam número nenhum — três delas são escopo que eu ampliei de propósito e
declaro, e as outras são leituras que a base agora carrega e alguém precisa saber que carrega.

| Item do brief | Resultado |
|---|---|
| 1. `EXP-0010`: avaliação datada (REPLAY), estresse com "amostra insuficiente", variantes recusadas, `result: inconclusivo`; T-037 com início 19:42:56Z | **OK** |
| 2. `EXP-0012` descartada por construção e `EXP-0013` mantida; ambas no índice e no Registro (T-039/T-040) | **OK** |
| 3. `EXP-0008` aposentadorias v1/v2 datadas; `EXP-0009` tabela de estresse; nota de rodapé da identidade de custo em `EXP-0006` e `KB-0076` | **OK, com escopo ampliado** — ver CONCERN 1 |
| 4. `Strategy Backlog`: B1 fechado, próximas atualizadas | **OK** |
| 5. `Diario/2026-09-08.md`: bloco final do dia | **OK** |
| 6. `08-CHANGELOG`: commits do dia, dívida da T3.33h | **OK** — 71 linhas, não 9 (a dívida cresceu desde as 14:22) |
| 7. `Open Bugs`: os três novos | **OK**, mais duas dívidas de instrumento declaradas |
| 8. `obsidian_lint.py` verde | **OK** — exit 0 |

## FILES

**Modificados (11) e criados (2), todos em `obsidian/**`:**

| arquivo | o quê |
|---|---|
| `C:\dev\project-hunter\obsidian\05-EXPERIMENTS\EXP-0010-session-orb-faixa-de-abertura.md` | frontmatter (`result: inconclusivo`, `evaluable: 20`, `days: 9`, `last_eval`); acréscimo datado no cabeçalho; **duas seções datadas novas** — a avaliação do replay do dia um (T3.33g, com cobertura, denominadores, decomposição por sessão, transbordo, livro de motivos, K1–K5 e a passada de estresse) e o registro datado da parada da T3.33f; +2 linhas em `Variantes tentadas` (as duas **recusadas**). `Hipótese`, `Protocolo` e o portão C1–C8 **não** foram tocados |
| `C:\dev\project-hunter\obsidian\05-EXPERIMENTS\EXP-0012-momentum-teto-de-pedagio.md` | **nova** — `momentum v5`; hipótese, portão C1–C8, protocolo, avaliação REPLAY (população vazia) e **seção datada da aposentadoria** (19:39:00Z) com o porquê de não esperar os 30 dias |
| `C:\dev\project-hunter\obsidian\05-EXPERIMENTS\EXP-0013-momentum-alvo-3-atr.md` | **nova** — `momentum v6`; hipótese, portão, protocolo com o desvio da escada 3/6/9 declarado, avaliação REPLAY pareada completa (4 grupos, Δ pareado, decomposição por motivo de saída, blocos de dia, MFE), 5 linhas de variantes |
| `C:\dev\project-hunter\obsidian\05-EXPERIMENTS\EXP-0008-breakout-compressao-de-volatilidade.md` | frontmatter (`evaluable: 8`, `days: 7`, com a mudança explicada no cabeçalho); **duas seções datadas novas** — a avaliação da `breakout v2` (T3.33f, que faltava na base) e as **duas aposentadorias auditadas**; +3 linhas em `Variantes tentadas` |
| `C:\dev\project-hunter\obsidian\05-EXPERIMENTS\EXP-0009-mean-reversion-pullback-em-tendencia.md` | **seção datada nova** com a passada de estresse (13 cenários, veredito `frágil a custos` + `dependente de metade`, e a ressalva do denominador do `stop_x1.25`) |
| `C:\dev\project-hunter\obsidian\05-EXPERIMENTS\EXP-0006-momentum-piso-de-custo.md` | nota de rodapé datada da identidade de custo (`risco% = stop_atr × ATR%`; v4 ≈ 0,15 R, v5 ≤ 0,067 R) + 3 links novos em `Relacionadas` |
| `C:\dev\project-hunter\obsidian\11-KNOWLEDGE\KB-0076-por-que-perdemos-2026-09-08.md` | callout datado com a mesma correção, dizendo o que **não** muda (nenhum número medido) + 2 links |
| `C:\dev\project-hunter\obsidian\05-EXPERIMENTS\Experiments Index.md` | acréscimo datado declarando as edições de linha; 2 linhas novas no Registro de IDs e 2 na tabela de experimentos; 4 linhas atualizadas (`EXP-0008`, `0009`, `0010` ×2) |
| `C:\dev\project-hunter\obsidian\11-KNOWLEDGE\Registro de Tentativas.md` | acréscimo datado: T-037 com início = ativação, T-039 e T-040 novas, multiplicidade 5 → 8 execuções avaliadas, as oito ativações do dia e as três aposentadorias |
| `C:\dev\project-hunter\obsidian\11-KNOWLEDGE\Strategy Backlog.md` | acréscimo datado: B1 fechado (testado e descartado), V1/V2 saíram do papel, fila reescrita (B2, B3', B4, B5, B6, **B7** e **B8** novas), "o que esta rodada NÃO propõe", seção `Relacionadas` |
| `C:\dev\project-hunter\obsidian\09-OPERATIONS\Diario\2026-09-08.md` | bloco "Plantão da noite (fecho do dia)": deploys alinhados até `1926e53`, **o placar das sete versões**, o achado da `session_orb`, aberto, saúde e as cinco pendências do operador com o estado de hoje |
| `C:\dev\project-hunter\obsidian\07-BUGS\Open Bugs.md` | seção datada com **3 bugs novos** (trava de `positions.agent_id`; rótulo `us` nas 6 h mortas; deriva de imagem nos deploys parciais) + 2 dívidas de instrumento |
| `C:\dev\project-hunter\obsidian\08-CHANGELOG\Changelog.md` | bloco datado com **71 commits** do dia, uma linha por commit, assunto verbatim do `git log` |

**Não tocados:** tudo fora de `obsidian/**`. O `git status` mostra `.claude/`, `docs/`, `infra/`,
`services/` modificados — são de outras tarefas em voo, não desta.

## LINT (saída real)

```
$ uv run python infra/scripts/obsidian_lint.py
LINT DA BASE OBSIDIAN — 195 NOTA(S) ANALISADA(S)
Resumo — Links mortos: 0, Links ambíguos: 0, Notas órfãs: 0, Frontmatter incompleto: 0, Valores fora do vocabulário: 0, Procedência da Knowledge Base (KB-*): 0, Reescrita de experimentos (append-only): 0.
Info: 2 experimento(s) fora do HEAD ignorado(s) na checagem append-only.

RESULTADO: base limpa
exit=0
```

193 → **195 notas** (as duas páginas novas). Os "2 experimentos fora do HEAD" são exatamente
`EXP-0012` e `EXP-0013`: ainda não estão commitados, então o checador append-only não tem versão
anterior com que comparar. As **zero** reescritas cobrem as três páginas que eu editei e que já
estavam no HEAD (`EXP-0006`, `EXP-0008`, `EXP-0009`, `EXP-0010`): nenhuma seção
`### Avaliação de <data>` existente foi removida ou alterada — as novas foram acrescentadas abaixo.

**Escopo, conferido:**

```
$ git status --short -- obsidian
 M obsidian/05-EXPERIMENTS/EXP-0006-momentum-piso-de-custo.md
 M obsidian/05-EXPERIMENTS/EXP-0008-breakout-compressao-de-volatilidade.md
 M obsidian/05-EXPERIMENTS/EXP-0009-mean-reversion-pullback-em-tendencia.md
 M obsidian/05-EXPERIMENTS/EXP-0010-session-orb-faixa-de-abertura.md
 M "obsidian/05-EXPERIMENTS/Experiments Index.md"
 M "obsidian/07-BUGS/Open Bugs.md"
 M obsidian/08-CHANGELOG/Changelog.md
 M obsidian/09-OPERATIONS/Diario/2026-09-08.md
 M obsidian/11-KNOWLEDGE/KB-0076-por-que-perdemos-2026-09-08.md
 M "obsidian/11-KNOWLEDGE/Registro de Tentativas.md"
 M "obsidian/11-KNOWLEDGE/Strategy Backlog.md"
?? obsidian/05-EXPERIMENTS/EXP-0012-momentum-teto-de-pedagio.md
?? obsidian/05-EXPERIMENTS/EXP-0013-momentum-alvo-3-atr.md
```

## CONCERNS

1. **Ampliei o escopo em `EXP-0008`, de propósito, e declaro.** O brief pedia "aposentadorias v1/v2
   datadas". Mas a avaliação da **`breakout v2`** (8 decisões, líquida −0,0810 R, T3.33f) **nunca
   tinha sido arquivada**: a T3.33h rodou às 14:22 e a T3.33f só commitou às 15:37. Registrar "a v2
   foi aposentada" numa página que nunca soube que a v2 existiu seria deixar a base incoerente
   consigo mesma. Portei a seção inteira do rascunho, datada e rotulada REPLAY, **antes** do bloco de
   aposentadorias. Se o revisor achar que isso é escopo demais, a seção é destacável — mas então o
   `evaluable: 8` do frontmatter volta a ser 0 e a página volta a não explicar a própria
   aposentadoria.

2. **Editei linhas de tabela do `Experiments Index`, de novo.** Mesmo argumento (e mesma declaração)
   da T3.33h: é um **índice**, não uma página de experimento; a regra append-only vale para as
   avaliações datadas, e elas foram acrescentadas, nunca reescritas. Sem isso o índice diria
   `nao-iniciado` para uma página que hoje tem 20 decisões. Está declarado na própria seção nova.

3. **`result: inconclusivo` na `EXP-0012` é o vocabulário, não a leitura exata.** O linter só aceita
   `inconclusivo | validada | reprovada | nao-iniciado` (`ENUM_VOCAB` em
   `infra/scripts/obsidian_lint_rules.py`), e a leitura honesta desta página é "a hipótese não foi
   testada; o que foi refutado é a possibilidade de testá-la neste universo". Quem carrega o estado
   real é `status: descartada-por-construcao` e o texto. Mudar o vocabulário é código, fora deste
   brief — é a mesma pendência que a `EXP-0011` já tinha aberto com `bloqueado-por-precheck`.

4. **Recontei duas métricas que a nota de origem publicava com um denominador só, e as duas contas
   batem — mas o número muda de nome.** A `notes-T3.33g` reporta "acerto 10,0 %" para a
   `session_orb`, que é `target / decisões` (2 de 20). Na página publiquei as **três** leituras com
   denominador explícito, como o template exige: taxa de alvo entre toques resolvidos **16,7 %**
   (2 de 12, `target + stop`), taxa de lucro líquido **40,0 %** (8 de 20 com `R_net > 0`, contadas
   uma a uma na tabela das 20 decisões da nota) e a taxa de alvo sobre todas as decisões **10,0 %**,
   que é a da nota. Nenhum número foi recalculado do banco — os três saem da mesma tabela de 20
   linhas. Se alguém comparar "acerto" entre esta página e a nota sem olhar o denominador, vai achar
   que discordam.

5. **O `evaluable`/`days` da `EXP-0008` agora descreve a `v2`, não a `v1`.** O frontmatter é um campo
   só e a página tem duas coortes. Escolhi a **última** (8 avaliáveis, 7 dias) e escrevi isso no
   cabeçalho, mas é uma convenção que a base não tem: nenhuma outra página multi-versão precisou
   decidir isso ainda. Vale fixar a regra no `_TEMPLATE-EXP` antes que apareçam duas convenções.

6. **A dívida do Changelog era nove commits e virou 71.** A T3.33h registrou nove; entre 14:22 e
   17:12 entraram mais 62, incluindo um (`d829546`, T3.39b) que chegou **durante** esta tarefa.
   Escrevi uma linha por commit com o assunto verbatim, sem editorializar. **Consequência de
   processo:** "changelog por commit" só funciona se rodar no mesmo turno do commit; num dia de 118
   commits, um plantão que arquiva o changelog às 14h já nasce devendo.

7. **Nada aqui foi medido por mim.** Todos os números vêm de `notes-T3.33f/g`, `notes-T3.36`,
   `notes-T3.40` e `stress-mean-reversion-v1-2026-09-08.md` (`as_of` das corridas entre 19:11Z e
   19:53Z de 2026-09-08). Não reli o banco, não rodei SQL, não toquei em container. As páginas dizem
   isso; esta nota repete para que a data da **leitura** não se confunda com a do **arquivamento**.

8. **Duas obrigações de portão continuam sem resposta, e uma delas piorou.** A C4 (corte por regime
   do BTC) segue impossível — `market_regimes` tem uma linha —, e agora são **seis** páginas de
   experimento carregando a obrigação declarada como não cumprida, não quatro. Virou candidata
   **B8** no backlog em vez de continuar como nota de rodapé. A C2 da `EXP-0008` (decomposição por
   `squeeze_ratio`) foi **cumprida** hoje pelo `--explain-ledger`, com n = 4 por bucket.

9. **Três aposentadorias no mesmo dia é muita coisa para uma via auditada que nasceu hoje.** O
   `--deprecate` foi commitado às 16:24 (`4929b99`) e usado três vezes entre 19:35 e 19:39. A
   revisão da T3.39 já achou que a trava de posições da linha `paper` lê uma coluna nunca preenchida
   (T3.39b em voo, e está em [[Open Bugs]]). Nenhuma das três versões aposentadas era `paper`, então
   nada dependeu da trava — **mas a próxima pode ser**, e essa é a ordem certa de leitura: a via
   funcionou nos três casos fáceis antes de a proteção do caso difícil estar correta.

10. **O placar do diário é um agregado meu, não uma consulta.** Juntei sete linhas de sete leituras
    diferentes numa tabela só porque ela responde a pergunta que o Everton faz ("e aí, funciona?").
    Cada linha está certa e citada; a **tabela** não existe em lugar nenhum do banco e não deve ser
    citada como se fosse uma corrida. Todas as sete são replay sobre a janela que gerou a própria
    hipótese, e isso está escrito logo abaixo dela.

## O QUE REVISAR DEPOIS DE MIM

- **code-reviewer:** os CONCERNs 1, 2 e 5 são julgamentos de escopo e de convenção, não de
  aritmética — é onde eu posso ter passado do brief.
- **Sexta-feira (integração):** commitar por pathspec exatamente os 13 caminhos listados em FILES;
  a árvore tem trabalho de pelo menos três outras tarefas.
- **Everton:** as cinco pendências de operador continuam intactas, e a (b) — reabrir as 10 janelas
  falsamente terminais — **deixou de estar bloqueada** (o deploy do `1ca7cf5` que ela esperava já
  aconteceu). A decisão de fundo que o dia põe na mesa é esperar 30 dias antes de mexer em alvo.
