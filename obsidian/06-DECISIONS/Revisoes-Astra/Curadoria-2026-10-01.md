---
tags: [astra, revisao, curadoria, obsidian, base]
status: fechada
owner: sexta-feira
updated: 2026-10-01
decided_on: 2026-10-01
by: Astra + Sexta-feira
---

# Revisão da Astra — curadoria da base Obsidian (01/10/2026)

Pedido do Everton: "Obsidian impecável". A Astra auditou a base (509 notas, lint "base limpa") e achou **12 contradições de estado e de índice que o lint não pega**: a avaliação nova foi acrescentada, mas o resumo, o frontmatter e o índice continuaram descrevendo a abertura. Bruto: `.claude/state/astra-review-astra-curadoria-obsidian.md`. Este é o registro documental da curadoria, **não** uma avaliação experimental: nenhuma hipótese foi julgada, nenhuma contagem refeita.

Regras seguidas: correções **só por acréscimo** (nunca reescrever nem apagar texto existente; seções congeladas e "### Avaliação de …" intactas); do frontmatter só `status`, `result`, `last_eval`, `version` e `updated`, e só onde a própria página já provava; cada acréscimo cita a prova; cada afirmação da Astra foi conferida nos arquivos citados antes de escrever.

## O que foi aplicado

| # | Achado | Onde | Conferência feita |
|---|---|---|---|
| 1 | Proteção da carteira descrita como inerte | acréscimo em [[KB-0165-staking-do-sol-parado]] | `entries.py:184`, `launch_entries.py:217`, `spot_entries.py:211` passam `holdings.unrecognized`; [[Diario/2026-09-30]]; [[2026-09-28-excecao-auditada-token-golpe]] |
| 2 | HOME com estado antigo como porta de entrada | caixa "Onde estamos agora — corte 2026-10-01" no topo da seção em [[00-HOME]] (texto de 07–08/09 mantido como histórico) | Open Bugs (quatro furos fechados), [[Diario/2026-09-30]], índice das revisões |
| 3 | Token-golpe ainda "bloqueia o deploy / decisão pendente" | encerramento em [[Open Bugs]] + linha em [[Resolved Bugs]] | decisão de 28/09; 30/09 a conta já fechada por terceiro |
| 4 | Reinício por `trailing_arm_x=1.0` ainda pede correção manual | encerramento do incidente em [[Open Bugs]] + linha em [[Resolved Bugs]]; **T4.65b continua aberta** | [[KB-0140-set-param-valida-antes-de-gravar]], `lab_params.py:61`, commit `c569ae7f` |
| 5 | Emergência de disco mistura fato superado e pendência real | atualização em [[Open Bugs]] + linha parcial em [[Resolved Bugs]] | [[2026-09-27-retencao-de-dados-e-backup]], [[Diario/2026-09-27]], [[Diario/2026-09-30]] (41 %) |
| 6 | EXP-0020 "replay pendente" | retificação + `status`/`version`/`last_eval` em [[EXP-0020-regime-gate]] | "Adendo T3.52d — 2026-09-09" |
| 7 | EXP-0008 "em andamento" | retificação + `status` em [[EXP-0008-breakout-compressao-de-volatilidade]] | "Avaliação de 2026-09-08 (3)" |
| 8 | EXP-M1/M3 como pré-registro | retificação + `status: descartado` em [[EXP-M1-comprar-cedo-na-curva]] e [[EXP-M3-sonda-de-hype]] | "Avaliação 2026-09-12 (T4.16)" |
| 9 | EXP-M2 "não iniciado" | retificação + `status`/`result`/`last_eval` em [[EXP-M2-a-linha-manda]] | "Avaliação de 2026-09-26" |
| 10 | EXP-M4/M5/M10/M14 `nao-iniciado` | retificação + `status`/`result` em [[EXP-M4-moonshot]], [[EXP-M5-fluxo-e-holders]], [[EXP-M10-compradores-25]], [[EXP-M14-razao-vendas-compras]] | fechamentos diários de M4/M5; acréscimo de 17–18/09 no [[Experiments Index]] para M10/M14 |
| 12 (só HOME) | Notas centrais sem atalho | mesmo bloco da HOME: [[Fila de Hipoteses]], [[KB-0149-o-que-a-mesa-real-ensinou]], [[Mapa de Estrategias]], [[03-TRADING/Meme/README]], [[T4.98-fechamento-noturno]] | notas existem e já eram citadas |

## O que não foi aplicado (e por quê)

- **Achado 11 (índice do EXP-M24 sem o julgamento R82) e a parte de índice dos achados 6–10 e 12:** estão em arquivos que outros agentes editam agora (Experiments Index, Index do conhecimento, Index das revisões). As linhas prontas estão em `.claude/state/curadoria-indices-pendentes.md` (catálogo KB-0115–KB-0169, 55 notas; estados dos EXP; EXP-M25; T4.98). A prova do achado 11 foi conferida: [[EXP-M24-entrada-no-recuo]] registra a "Avaliação 2026-09-27 (R82)" com 151 pares e `NÃO CONFIRMA`, usando o controle [[EXP-M25-controle-do-recuo]].
- **Contagens de frontmatter (`evaluable`, `days`)** das páginas EXP corrigidas: não foram recalculadas. A definição de "avaliável" por braço mora nas avaliações; recalcular é trabalho de extração, não de curadoria. Cada retificação diz isso.
- **Itens do nice-to-have:** nada foi marcado como implantado ou recuperado sem prova — a T3.87 (replay com a correção, deploy não comprovado) e o isolamento/recuperação do fechamento noturno ([[T4.98-fechamento-noturno]]) seguem como estão em Open Bugs. A emergência de disco foi fechada **só no que está provado**; crons, `VACUUM FULL` e a poda permanente de imagens (T4.63b) seguem abertos.

## Limite que a Astra apontou e que continua valendo

Acréscimo textual não corrige uma tabela dinâmica que lê o frontmatter antigo ([[Experimentos.base]], [[Estratégias.base]], Dataview do [[Mapa de Estrategias]]). Por isso o frontmatter foi alinhado nas páginas em que a evidência é inequívoca; `evaluable`/`days` ficam como pendência de uma tarefa própria de reconciliação de metadados. Nice-to-have aceito para o futuro: data de corte explícita nos resumos vivos (a HOME já ganhou uma).

## Relacionado

[[00-HOME]] · [[Open Bugs]] · [[Resolved Bugs]] · [[Revisoes-Astra/Index|índice das revisões]]
