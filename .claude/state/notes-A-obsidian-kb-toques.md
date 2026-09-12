# A-obsidian-kb-toques — 2026-09-12 (Astra)

## RESUMO

Concluído como `documentation-writer`: quatro adendos `Adendo 2026-09-12 (Astra)`, somente acrescentados ao fim das KBs, com procedência por afirmação e por linha da tabela macro.

## ARQUIVOS

Modificados nesta tarefa:
- `obsidian/11-KNOWLEDGE/KB-0025-o-nosso-detector-de-open-interest-so-olha-para-cima.md:149` — lado do desvio de OI independente do preço; funding observado não equivale a custo realizado.
- `obsidian/11-KNOWLEDGE/KB-0070-a-tabela-de-capacidade-quantos-mercados-suportam-cada-tamanho.md:186` — observação, execução e contribuição marginal; limites da fotografia e do cenário D-P19; duração versus trajetória na D-P23.
- `obsidian/11-KNOWLEDGE/KB-0074-risco-operacional-as-regras-de-nao-operar-quando.md:175` — PPI/CPI com horários, referências implícitas e resultados; restrição de agenda distinta de disponibilidade operacional.
- `obsidian/11-KNOWLEDGE/KB-0083-uma-hora-de-34-r-deriva-e-impulso.md:152` — retirada da explicação N²; H-P18 causal e exploratória.

Criado: `.claude/state/notes-A-obsidian-kb-toques.md` (este registro).

O Index não precisou mudar: títulos e descrições existentes foram preservados. A árvore já continha alterações de outras tarefas; nenhuma delas foi editada nesta execução. Nenhum commit.

## TESTES

Comando exigido, executado em primeiro plano antes e depois das edições, ambas as vezes com saída 0:

```text
bash -lc 'timeout 290 uv run python infra/scripts/obsidian_lint.py'
LINT DA BASE OBSIDIAN — 256 NOTA(S) ANALISADA(S)
Resumo — Links mortos: 0, Links ambíguos: 0, Notas órfãs: 0, Frontmatter incompleto: 0, Valores fora do vocabulário: 0, Procedência da Knowledge Base (KB-*): 0, Reescrita de experimentos (append-only): 0.

RESULTADO: base limpa
```

`git diff --check -- obsidian/11-KNOWLEDGE`: sem saída, sem erros de whitespace. `git diff --numstat -- obsidian/11-KNOWLEDGE`: KB-0025 +6/−0; KB-0070 +8/−0; KB-0074 +15/−0; KB-0083 +8/−0. Nenhum teste de código, replay ou consulta às APIs/VPS foi executado; os resultados históricos estão atribuídos aos arquivos de origem.

## MUST-FIX

Nenhum pendente no escopo. Divergência documental explicitada: o resumo do PPI mistura a queda até a mínima com retorno de fechamento de 15 minutos; o adendo usa os OHLC detalhados. O DVOL anterior ao PPI foi recuperado depois do evento, e está rotulado assim, sem fabricar um carimbo prospectivo.

## NICE-TO-HAVE

Nenhum necessário para concluir este brief.

## O QUE EU FARIA DIFERENTE

Manteria os pares implícito/realizado com horizontes declarados e o número de eventos como unidade de evidência, como registrado no adendo da KB-0074.

## CONCORDO COM

Preservar o histórico e incorporar as correções das revisões de 10–11/09 sem promover hipóteses a regras. Conferência da Astra nesta execução: fontes locais e diff; não houve segunda revisão independente.

## OBSIDIAN

- **O nosso detector de open interest só olha para cima** — atualizado: OI relativo à baseline, sem confusão com preço.
- **A tabela de capacidade — quantos mercados suportam 500, 2.000 e 10.000 USDT** — atualizado: observados, executáveis e ganho marginal.
- **Risco operacional — as regras de não operar quando** — atualizado: PPI/CPI e limites da leitura de agenda.
- **Uma hora de −34 R: 9 apostas × 4,3 versões, deriva + impulso de amplitude** — atualizado: retirada do N² explicativo e H-P18 como hipótese.
