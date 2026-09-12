---
tags: [operacoes, diario, meme, m4]
status: vivo
owner: sexta-feira
updated: 2026-09-12
---

# Diário Meme — formato do diário operacional do Lab na curva do pump.fun

**Planejado (T4.6) — esta pasta ainda não tem nenhum diário nela.** Esta página fixa o formato antes
do gerador existir, para que a primeira execução da T4.6 escreva no formato certo desde o dia 1
(`.claude/state/brief-T4.6-lab-meme-continuo.md` item 3, sob a diretriz do Everton de 2026-09-12:
"o Lab vai ficar em cima das meme coins simulando sem parar, com o Obsidian indo atrás" —
[[06-DECISIONS/2026-09-12-meta-7m-e-lab-meme]]).

Esta pasta é a irmã meme de [[09-OPERATIONS/Diario/2026-09-11|09-OPERATIONS/Diario]] (o diário geral, escrito
à mão pela Sexta-feira a cada plantão). A diferença: o diário meme nasce de script
(`infra/scripts/meme_diary.py`, planejado — ainda não existe no repositório nesta data, modo
dry-run/apply) com os números do dia já calculados a partir de `meme_paper_bets` e da(s)
`PaperCurveWallet`, e **depois** um arquivista (Sexta-feira) completa com a narrativa — o
aprendizado, o que mudou de ideia, o que virou hipótese nova. Nenhum número financeiro do diário é
digitado à mão; só a narrativa é.

## Convenção de arquivo

Uma nota por dia, `obsidian/09-OPERATIONS/Diario-Meme/AAAA-MM-DD.md`, frontmatter
`tags: [operacoes, diario, meme, m4]`, `status: registro` (é um documento datado — não se reescreve,
mesma semântica de `09-OPERATIONS/Diario/`), `owner: sexta-feira`, `updated`.

## As seções, nesta ordem

1. **Estado da carteira paper** — saldo em SOL no início e no fim do dia, por conjunto de regras
   ativo (`EXP-M<n>` / `meme_rule_sets`), posições abertas ao fechar o dia (mint, custo-base,
   valorização a mercado pela curva — "o que uma venda cheia agora renderia", nunca o preço marginal
   sozinho, mesma honestidade que `docs/plans/T4-MEME-RADAR-UI.md` exige da tela).
2. **Apostas do dia** — tabela: mint, conjunto/`EXP-M<n>`, hora de entrada e saída, motivo de saída
   (alvo / trailing / time stop / migração / rug), R em SOL (risco inicial = perda máxima permitida
   daquela aposta), PnL em SOL e em USD pela cotação SOL/USD observada (fonte + hora, nunca uma
   cotação adivinhada — mesmo padrão do `fx` de `GET /api/v1/orgs/{org}/lab/daily-goal`).
3. **R em SOL do dia e acumulado** — soma do dia e série acumulada desde o início do Lab meme;
   drawdown do dia e drawdown acumulado.
4. **Distância à meta** — os quatro campos do painel Meta
   ([[06-DECISIONS/2026-09-12-meta-7m-e-lab-meme]] §4): capital, retorno diário exigido, retorno
   diário medido, dias restantes — os mesmos números da tela `/meme` (T4.3b), reproduzidos aqui como
   registro datado do dia.
5. **Incidentes** — rug durante posição aberta, falha de dado (RPC/WS fora do ar, snapshot
   atrasado), reconexão, qualquer coisa que o `[!alerta]` cobriria num diário geral
   (`docs/OBSIDIAN.md` §2).
6. **O que o Lab aprendeu** — texto livre do arquivista: o que uma sequência de apostas sugeriu, se
   virou hipótese nova para a fila (`M-P<n>` em `00-INBOX/Hipoteses-do-plantao.md`), se uma nota de
   `11-KNOWLEDGE` foi atualizada. Esta é a única seção que não vem do script.

## O que este diário NÃO é

Não é o plantão de mercado sobre pump.fun em geral (isso é
[[02-MARKET/Meme/README|Meme (Mercado)]] — fontes, papers, taxas-base). Não é conhecimento curado
(isso é [[11-KNOWLEDGE/README-meme|Meme (Conhecimento)]]). Não é evidência de dinheiro real — todo
número aqui é paper (`ENABLE_MEME_LIVE_TRADING=false` até segunda ordem do Everton,
[[06-DECISIONS/2026-09-12-meta-7m-e-lab-meme]] §3).

## Relacionadas

[[09-OPERATIONS/Diario/2026-09-11|Diário (geral)]] · [[06-DECISIONS/2026-09-12-meta-7m-e-lab-meme]] ·
[[03-TRADING/Meme/README|Meme (Trading)]] · [[02-MARKET/Meme/README|Meme (Mercado)]] ·
[[11-KNOWLEDGE/README-meme|Meme (Conhecimento)]] · `docs/plans/T4-MEME-RADAR-UI.md`
