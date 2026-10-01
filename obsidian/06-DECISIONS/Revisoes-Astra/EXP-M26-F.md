---
tags: [astra, revisao, pesquisa, exp-m26, h-022, funil, instrumento, pedigree]
date: 2026-10-01
updated: 2026-10-01
status: fechada
owner: quant-engineer
decided_on: 2026-10-01
by: Astra + quant-engineer
---

# Revisão da Astra — funil F do EXP-M26 (01/10/2026)

**Por que existe:** a etapa F de [[EXP-M26-grafico-em-moedas-maduras]] (H-022 na [[Fila de Hipoteses]]) é o funil
de viabilidade, sem desfecho, que precisa passar antes de congelar o J e semear os braços. Nada foi semeado, então
o quant-engineer avaliou a porta pura de `grafico_ctrl_v1/1` fora do Lab, com o código de R1, sobre 65,5 h de
linhas reais da VPS (somente leitura). A Astra revisou os scripts e as saídas em `.claude/state/m26/f/`.
O bruto está em `.claude/state/astra-review-EXP-M26-F.md`.

**O que estava em jogo:**
- **O mercado passa os pisos:** 417,7 oportunidades/dia, 12,1 `true`/dia, 227 `false`/dia e U = 4,5 %.
- **O instrumento não passa.** A leitura de pedigree do minuto, que volta com C/L/H ativos, levou 6,2–13,7 s para
  ~385 mints, e 26 de 42 minutos passaram do corte de 8 s. Cada corte vira `pedigree_unknown`, que é `sem_proposta`
  por instrumento.

**O que ela disse e o que foi feito:**

| achado | decisão |
|---|---|
| Concorda: F **não passa por instrumento**. Conserta-se e repete-se antes de J/S; P não adia um bloqueio já conhecido | absorvido — J não congelado, semente `0069` intocada |
| 26/42 é a taxa de **consultas lentas**, não a de oportunidades perdidas. E uma E que só se soube offline não existiria no tique cortado | absorvido como ressalva na avaliação; mesmo o trecho mais rápido (2/12 ≈ 17 %) passa três vezes do teto de 5 % |
| Must-fix 2: o estado de conclusão/migração tem de ser lido no relógio do tique (≥ T + 60 s), não no `computed_at` | medido: 3 / 6 / 15 de 1 140 1.ªs oportunidades mudariam até T + 60 / 120 / 180 s (≤ 1,3 %, nenhum piso muda); o F repetido usa o relógio do tique |
| Must-fix 3: Mayhem, criador e símbolo **como eram no tique**; uma moeda antiga descoberta depois muda a contagem de pedigree | não medível com o que existe (não há histórico de Mayhem nem de identidade); fica declarado como desconhecido |
| Conserto: na via de 1 min, só as duas contagens de `PEDIGREE_V1` quando nenhum conjunto do relógio pede `pedigree_repeat_dumper` (28–69 ms medidos); diagnósticos ausentes, nunca zero; a pista de 15 s não muda | aceito como recomendação para o backend-specialist; filtrar pela porta pura foi descartado porque mudaria a trilha de recusas |
| O F repetido precisa de: relógio do tique, ≥ 24 h pela via corrigida com o corte real, união U/I por oportunidade, testes de equivalência e de preservação dos 15 s, duração do ciclo e guardas §6.8 | registrado no "Próximo passo" da avaliação |
| Nice-to-have: rodar `quote_for` puro em vez de só checar `snapshot_ok` | para o F repetido |

**Sem divergência.** Rótulo da etapa: F **não aprovado — instrumento**. Não é veredito da H-022.

Relacionado: [[EXP-M26-grafico-em-moedas-maduras]] (avaliação de 2026-10-01) ·
[[06-DECISIONS/Revisoes-Astra/Token-state-history|Token-state-history]] · [[Open Bugs]] ·
[[06-DECISIONS/Revisoes-Astra/Index|Revisões da Astra]]
