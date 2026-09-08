# Notas T3.21 — Bases, callouts, linter e canvases

Sexta-feira, 2026-09-08. Continuação: a sessão anterior entregou frontmatter em 162 notas, as duas
Bases, os dois canvases, os callouts, `docs/OBSIDIAN.md` e a primeira versão do linter. Esta sessão
fechou os defeitos do linter, provou a base e commitou.

## Os defeitos do linter (achados pela própria sessão anterior) e o que se fez

| # | Defeito | Correção |
|---|---|---|
| 1 | Resolução de link só por caminho exato ou nome-base: `[[Dialogos/M3]]` era link morto — **152 falsos positivos** numa base que o Obsidian abre inteira | Índice de sufixos de caminho em fronteira de barra (`obsidian_lint_links.build_index` / `resolve_target`): caminho inteiro tem preferência, sufixo resolve, sufixo que casa com dois arquivos vira `links_ambiguos` |
| 2 | `.base` e `.canvas` fora do índice de alvos: os quatro arquivos novos eram link morto no `00-HOME` e no Changelog | `discover_assets()` indexa `.base`/`.canvas` como **alvos linkáveis** (só pelo nome com extensão, como no Obsidian) sem virarem notas: não têm frontmatter cobrado nem entram na checagem de órfãs |
| 3 | 500 linhas, acima do teto de 350 | Dividido em `obsidian_lint.py` (157), `obsidian_lint_rules.py` (290) e `obsidian_lint_links.py` (144) |
| 4 (novo) | Alias escapado de tabela: `[[EXP-0001-momentum-v1\|em modo sombra]]` era lido com a barra invertida colada no nome do arquivo (4 falsos positivos no `Experiments Index`) | `extract_links` desfaz o `\|` antes de separar o alias |
| 5 (novo) | `03-TRADING/Estrategias/README.md` cobrado como página de estratégia (`strategy`), e `_TEMPLATE-NOTE.md` cobrado por valor em chave que existe **para ser preenchida** (`fonte:`, `lido_em:`) | Exceção por pasta para o README do catálogo (T3.20, arquivo de outra tarefa — não se editou); em `_TEMPLATE-*` cobra-se a **presença** da chave, não o valor |

Nenhum dos 163 achados era defeito da base: eram todos defeito do instrumento. Isso é o motivo de o
teste vir junto — um linter que reprova a base certa treina todo mundo a ignorar o linter.

## Antes (linter da sessão anterior, na base inteira)

```
LINT DA BASE OBSIDIAN — 182 NOTA(S) ANALISADA(S)
Resumo — Links mortos: 154, Links ambíguos: 0, Notas órfãs: 7, Frontmatter incompleto: 2, Valores fora do vocabulário: 0, Procedência da Knowledge Base (KB-*): 0, Reescrita de experimentos (append-only): 0.
...
Notas órfãs (7)
- 03-TRADING/Estrategias/README.md:1 — nenhuma outra nota referencia esta página
- 06-DECISIONS/Dialogos/Index.md:1 — nenhuma outra nota referencia esta página
- 06-DECISIONS/Revisoes-Astra/Index.md:1 — nenhuma outra nota referencia esta página
- 09-OPERATIONS/Diario/2026-09-05.md:1 — nenhuma outra nota referencia esta página
- 09-OPERATIONS/Diario/2026-09-06.md:1 — nenhuma outra nota referencia esta página
- 09-OPERATIONS/Diario/2026-09-07.md:1 — nenhuma outra nota referencia esta página
- 09-OPERATIONS/Diario/2026-09-08.md:1 — nenhuma outra nota referencia esta página

Frontmatter incompleto (2)
- 03-TRADING/Estrategias/README.md:1 — faltam: strategy
- 11-KNOWLEDGE/_TEMPLATE-NOTE.md:1 — faltam: fonte, lido_em

Conhecidos (com motivo) (8)   [os oito [[Estrategias/README]] das páginas de família]

RESULTADO: 163 achado(s)
```

Amostra dos 154 links mortos (todos falsos positivos): `[[Experimentos.base]]`,
`[[Estratégias.base]]`, `[[Fluxo sinal → carteira.canvas]]`, `[[Família momentum.canvas]]`,
`[[Dialogos/M3]]`, `[[Dialogos/SHADOW]]`, `[[Revisoes-Astra/Index]]`, `[[Diario/2026-09-07]]`,
`[[EXP-0001-momentum-v1\]]`. Saída completa em `.claude/state/tmp/lint-antes-v2.txt`.

## Depois (`uv run python infra/scripts/obsidian_lint.py`, saída real)

```
LINT DA BASE OBSIDIAN — 182 NOTA(S) ANALISADA(S)
Resumo — Links mortos: 0, Links ambíguos: 0, Notas órfãs: 0, Frontmatter incompleto: 0, Valores fora do vocabulário: 0, Procedência da Knowledge Base (KB-*): 0, Reescrita de experimentos (append-only): 0.

RESULTADO: base limpa
```

Código de saída 0. A `ALLOWLIST` ficou **vazia**: os oito `[[Estrategias/README]]` resolvem de
verdade agora, e um item de allowlist que não suprime nada engana quem lê.

Conferência da resolução (não é o próprio linter se auto-aprovando — é o alvo que cada link acha):

```
'Dialogos/M3'                   -> resolved 06-DECISIONS/Dialogos/M3.md
'Revisoes-Astra/Index'          -> resolved 06-DECISIONS/Revisoes-Astra/Index.md
'Diario/2026-09-07'             -> resolved 09-OPERATIONS/Diario/2026-09-07.md
'Estrategias/README'            -> resolved 03-TRADING/Estrategias/README.md
'Experimentos.base'             -> resolved 05-EXPERIMENTS/Experimentos.base
'Estratégias.base'              -> resolved 03-TRADING/Estratégias.base
'Fluxo sinal → carteira.canvas' -> resolved 01-ARCHITECTURE/Fluxo sinal → carteira.canvas
'EXP-0001-momentum-v1'          -> resolved 05-EXPERIMENTS/EXP-0001-momentum-v1.md
'Fantasma'                      -> dead
```

## Verificação

```
uv run pytest infra/scripts/tests/test_obsidian_lint.py -q   -> 26 passed in 0.97s
uv run ruff check <4 arquivos>                               -> All checks passed!
uv run ruff format --check <4 arquivos>                      -> 4 files already formatted
uv run pyright <4 arquivos>                                  -> 0 errors, 0 warnings, 0 informations
uv run python infra/scripts/check_file_size.py               -> obsidian_lint*.py fora da lista
uv run python infra/scripts/obsidian_lint.py                 -> RESULTADO: base limpa (exit 0)
```

Testes novos, todos com vault de brinquedo em `tmp_path` (sem Docker, sem rede): link parcial
resolve; link parcial ambíguo é ambíguo e não morto; sufixo só casa em fronteira de barra;
`.base`/`.canvas` são alvos e não contam como nota; link a `.base` sem extensão é morto;
`_TEMPLATE-*` aceita chave declarada vazia mas não aceita chave ausente; README do catálogo não é
cobrado por `strategy`. Mais o teste de alias escapado em célula de tabela, que estava na árvore e
falhava por uma órfã na fixture (`Nota B` sem link de entrada) — corrigido no lugar.

## O commit saiu com a mensagem de outra tarefa — como e por quê

Os 172 arquivos da T3.21 estavam **montados no índice** (`git add` dos caminhos certos, conferidos:
nada de `03-TRADING/Estrategias/`, nada de outra tarefa) quando uma **sessão concorrente rodou
`git commit` na mesma árvore**. O commit dela levou o índice inteiro junto e saiu como:

```
6a17665 chore(state): brief T3.22 — Brasília time as the primary display everywhere, UTC as the
        detail (Everton, 2026-09-08); dispatch after T3.18 web
        173 arquivos: os 172 da T3.21 + .claude/state/brief-T3.22-brasilia-time.md
```

Quando percebi, `main` já estava igual a `origin/main` (0 à frente, 0 atrás): o commit tinha sido
empurrado. Histórico empurrado não se reescreve — sem `reset`, sem `rebase`, sem force-push —, então
o conteúdo fica onde está e este arquivo é o registro. Nada se perdeu e nada de outra tarefa entrou.

**A lição, para não repetir:** numa árvore compartilhada o índice é global e não pertence a quem o
montou. Montar o índice num comando e commitar noutro abre uma janela em que qualquer sessão
concorrente commita o seu trabalho com a mensagem dela. `git add <caminhos> && git commit -m ...`
no **mesmo** comando, sempre, e verificação de `git log -1` logo depois.

## Fora do escopo, registrado

- `packages/core/hunter_core/db/models/agents.py` está com **351 linhas** (teto 350) no
  `check_file_size.py`. É arquivo de outra tarefa em voo, não commitado aqui.
- A árvore está compartilhada com outras tarefas: este commit levou só `obsidian/**` (menos
  `03-TRADING/Estrategias/**`, que é da T3.20 e já está commitada), `docs/OBSIDIAN.md`,
  `infra/scripts/obsidian_lint*.py` e o teste.
