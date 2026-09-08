---
tags: [estrategia, catalogo, convencao]
updated: 2026-09-08
---

# Estratégias — convenção do catálogo (T3.20)

Everton, 2026-09-08: "lembra todas estrategias vao ficar no obsidian esse é o
diferencial gravar cada detalhe cada diametro". Cada linha de
`strategy_versions` — a estratégia inteira, cada parâmetro, cada diâmetro —
ganha sua própria página aqui. Nada disto substitui os experimentos em
[[Experiments Index|05-EXPERIMENTS]]: esta pasta é o **catálogo** (o que
existe, com que parâmetros, quem ativou, quando), aquela é o **registro de
pesquisa** (as avaliações datadas, nunca duplicadas aqui).

## Uma página por versão

`obsidian/03-TRADING/Estrategias/<key>-<version>[-paper].md`, onde `<key>` é
`strategies.key` e `<version>` é `strategy_versions.version`:

- `momentum-v2.md` — versão comum (`purpose = research_only` ou `live`, sem
  sufixo);
- `momentum-v3-paper.md` — quando `purpose = paper` (a linha que a ponte
  sinal → admissão pode um dia alimentar);
- `momentum-v2-irma-03.md` — quando existir um irmão de replicação (T3.19:
  `packages/indicators/hunter_indicators/replication/**`), nomeado pelo
  contrato daquela tarefa quando ele existir.

Cada página traz, nesta ordem: **Parâmetros** (tabela completa — nome, valor,
tipo, vínculo do `parameters_schema`, descrição — nunca só o valor),
**Origem** (o `changelog` congelado e as linhas de `system_events` da
ativação), **Coortes e sinais** (contagens de `agent_signals` por coorte),
**Avaliações** (links para as páginas `EXP-NNNN`; os números ficam lá, nunca
duplicados aqui), **Replicação** (o contrato do T3.19 quando existir, senão
"não iniciada") e **Ligações** (família, versão anterior, irmãs, experimentos,
Risk Engine quando `purpose = paper`).

## Uma página por família

`<strategies.key>.md` (ex.: `momentum.md`) lista toda versão daquela chave
com propósito, status, o veredito mais recente (lido da página `EXP-NNNN`
quando existe) e o link para a página da versão.

## O exportador

`infra/scripts/export_strategies_to_obsidian.py` lê o banco **só leitura**
(`DATABASE_URL`, papel `hunter_app`) e escreve **apenas** o bloco entre
`<!-- generated:start -->` e `<!-- generated:end -->` de cada página — tudo
abaixo do marcador de fechamento é seu, escrito à mão, e sobrevive a toda
rodada. Cria páginas que faltam, nunca apaga uma existente. Saída
determinística (chaves ordenadas, nenhum timestamp exceto `updated`): duas
rodadas no mesmo dia não produzem diff.

```bash
# local (o stack precisa estar de pé)
uv run python infra/scripts/export_strategies_to_obsidian.py --dry-run
uv run python infra/scripts/export_strategies_to_obsidian.py

# VPS (o banco vive lá; esta máquina só tem SSH) — mesmo script, dentro do
# container da API, com a saída copiada de volta
ssh hunter-vps 'docker exec hunter-api-1 python infra/scripts/export_strategies_to_obsidian.py --dry-run'
ssh hunter-vps 'docker exec hunter-api-1 python infra/scripts/export_strategies_to_obsidian.py'
docker cp hunter-api-1:/app/obsidian/03-TRADING/Estrategias/. ./obsidian/03-TRADING/Estrategias/
```

O link entre uma versão e sua página de experimento (`EXP-NNNN`) é uma
tabela manual em `obsidian_strategy_pages.py`
(`EXP_LINKS_BY_STRATEGY_PURPOSE`) — nenhuma página do vault nomeia sua
estratégia sem ambiguidade (a EXP do `volume_anomaly` está marcada `volume`,
não `volume_anomaly`), então quem abre um `EXP-NNNN` novo acrescenta uma
linha ali, uma vez.

## A cada plantão

Rodar o exportador, conferir o diff (`git status --short obsidian/`),
acrescentar links e avaliações que só um humano sabe fazer (a segunda opinião
da Astra, uma nota de contexto) na seção **Notas** de cada página tocada —
nunca dentro do bloco gerado, que a próxima rodada substitui. Quando uma
versão é ativada, superada (`--supersede`) ou vira linha paper
(`--paper-line`), rodar o exportador depois é o que traz a página nova para
o catálogo.

**Pendência de uma linha (T3.20):** falta o gancho no
`infra/hermes/skills/project-hunter/sexta-feira-plantao/SKILL.md` chamando o
exportador automaticamente — aquele arquivo é do T3.15c agora; ver
`.claude/state/notes-T3.20.md`.

## Relacionadas

[[Experiments Index]] · [[Strategy Backlog]] · [[Strategies]] · `docs/plans/REPLICATION.md` (T3.19, quando existir)
