---
tags: [mercado, meme, pumpfun, plantao, m4]
status: vivo
owner: sexta-feira
updated: 2026-09-12
---

# Meme (Mercado) — como os arquivos do plantão de pump.fun são organizados

Esta pasta é a irmã meme de [[02-MARKET/Plantao/2026-09-12|02-MARKET/Plantao]]. Aquela cobre o plantão de
mercado geral (T3.64) — o universo SPOT/perp que o Lab já opera. Esta cobre especificamente
pump.fun/meme coins, a partir da diretriz do Everton de 2026-09-12: "mapear cada canto do pump.fun"
e "tudo sobre tendências vai anotando no Obsidian" —
[[06-DECISIONS/2026-09-12-meta-7m-e-lab-meme|registrada aqui]].

**Origem desta pasta:** criada em 2026-09-12 junto com a decisão acima. Antes desta data, achados de
meme apareciam **dentro** do plantão geral — é o caso de
[[KB-0091-pump-fun-as-taxas-base-e-seus-denominadores]], que nasceu de uma faixa do plantão de
2026-09-12 registrada em `02-MARKET/Plantao/2026-09-12.md` (frontmatter daquele arquivo já inclui a
tag `meme`). **2026-09-12 é o dia de transição**: pode haver conteúdo de meme tanto no plantão geral
de hoje quanto no primeiro arquivo desta pasta — nenhum dos dois foi reescrito para "corrigir" isso,
os dois ficam como registro do dia em que a separação começou.

## Convenção de arquivo

- **Uma nota por dia**, em `obsidian/02-MARKET/Meme/AAAA-MM-DD.md` — mesmo padrão de
  `02-MARKET/Plantao/AAAA-MM-DD.md`: frontmatter com `tags: [mercado, plantao, meme, pumpfun, m4]`,
  `status: vivo` (o dia corrente) passando a `registro` quando fechado, `owner: sexta-feira`,
  `updated`.
- **Escopo de cada nota diária**: o que foi observado sobre pump.fun naquele dia — fontes abertas
  (papers, docs, endpoints testados ao vivo, com hora BRT), números medidos com proveniência
  (nunca um número de terceiro sem "lido em"), e as hipóteses que essas observações alimentam na
  fila `00-INBOX/Hipoteses-do-plantao.md` sob o prefixo `M-P<n>` (ver o cabeçalho daquele arquivo e
  [[03-TRADING/Meme/README|Meme (Trading)]] para a distinção entre `M-P<n>`, `EXP-M<n>` e os rótulos
  antigos `M-A/M-B/M-E/M-G`).
- **O que uma nota diária desta pasta NÃO é**: não é o diário operacional do Lab (isso é
  [[09-OPERATIONS/Diario-Meme/README|Diário Meme]] — estado da carteira paper, apostas, R em SOL);
  não é uma página de conhecimento curada (isso vai para `11-KNOWLEDGE/KB-00xx` quando a leitura do
  dia amadurece — [[11-KNOWLEDGE/README-meme|Meme (Conhecimento)]]). Uma nota diária é o registro
  bruto do que foi lido e testado naquele plantão, do jeito que `02-MARKET/Plantao/` já faz para o
  resto do mercado.
- **Não editar retroativamente** uma nota de dia fechado além de acrescentar seção nova e datada —
  mesma disciplina do resto da base (`docs/OBSIDIAN.md` §5, categoria `exp_reescrita`, por analogia:
  aqui não é `EXP`, mas o princípio de "leitura de um instante, nunca corrigida em cima" vale).

## Estado nesta data (2026-09-12)

[[02-MARKET/Meme/2026-09-12|2026-09-12]] é o primeiro arquivo desta pasta — escrito nesta mesma
sessão por outro agente do plantão (T4.64, meme-first), em paralelo a este README. Este README foi
escrito **sem editar nem ler o conteúdo** daquele arquivo além do frontmatter e das duas primeiras
linhas, para não colidir com a escrita em andamento.

## Relacionadas

[[02-MARKET/Plantao/2026-09-12|Plantão de mercado (geral)]] · [[00-INBOX/Hipoteses-do-plantao|Fila de hipóteses]] ·
[[03-TRADING/Meme/README|Meme (Trading)]] · [[09-OPERATIONS/Diario-Meme/README|Diário Meme]] ·
[[11-KNOWLEDGE/README-meme|Meme (Conhecimento)]] · [[06-DECISIONS/2026-09-12-meta-7m-e-lab-meme]] ·
[[KB-0091-pump-fun-as-taxas-base-e-seus-denominadores]] · `docs/plans/T4-MEME-RADAR.md`
