---
tags: [astra, revisao, indice]
updated: 2026-09-08
status: registro
owner: sexta-feira
decided_on: 2026-09-06
by: astra
---

# Revisões da Astra — índice

Cada revisão é uma opinião do motor Astra da [[Mente da Sexta-feira]] sobre um plano, um diff ou uma decisão; o resultado (aceito/rejeitado e por quê) fica no kit da tarefa em `.claude/state/review-*.md` e nas páginas de [[Open Bugs]] / [[Resolved Bugs]].

- [[2026-09-08-shadow-lab-pronto]] — "o Lab está pronto?" (2026-09-08): **não** — 4 furos no caminho de replicação (T3.18c), 5 etapas da autonomia paper sem prova (T3.29) e a negação de serviço compartilhada do bucket do `web` (T3.28a-seguimento); `inconclusivo` no EXP-0006 confirmado
- [[S4-hipoteses]] — as hipóteses de falha do Shadow Lab sobre a coorte da VPS (5 must-fix; "intervalo do contrafactual" e "72 bugs de identidade" caíram)
- [[S4-vps-lab]] — a prova operacional do Lab na VPS (hashes reproduzidos; 4 achados, incluindo a recomendação que teria quebrado o deploy)
- [[S4-avaliacoes-shadow]] — as primeiras avaliações datadas do Shadow Lab (5 must-fix, todos aceitos antes de publicar)
- [[M1-plan]]
- [[T1.2]]
- [[T1.2b-round2]]
- [[T1.2b-round3]]
- [[T1.2b]]
- [[T1.3-A1]]
- [[T1.3-A2]]
- [[T1.3-final-fixes]]
- [[T1.3-partition-startup]]
- [[T1.4-fixpass]]
- [[T1.4]]
- [[T1.5-fixes-p1]]
- [[T1.5-fixpass]]
- [[T1.5]]
- [[T1.5b]]
- [[binance-skills-hub]]
- [[ccxt]]
- [[design-T1.5b]]
- [[review-T1.2-final]]
- [[review-T1.3-final]]
- [[review-T1.3]]
- [[review-T1.4-final]]
- [[review-T1.5-final]]
- [[review-T1.5b-final]]
- [[review-T1.5b-fixpass]]
- [[t16-proof]]
- [[t16b-sharding]]
- [[vps-bootstrap]]
- [[vps-executed]]
- [[vps-fixes]]

## Desde 19/09/2026 (síntese por tarefa/pesquisa; brutos em `.claude/state/astra-review-*.md`)

- 2026-09-27 — [[Prune-partitions-locks]] (podador sem travar a ingestão)
- 2026-09-27 — [[Create-partitions-lock]] (criador de partições reconhece o lock expirado)
- 2026-09-27 — [[Retencao-disco-execucao]] (código dos passos 1–5 do disco: backup por contagem, `history_v2`, 14/30/2 d, F1–F5 do quant)
- 2026-09-28 — [[Staking-sol-parado]] (staking do SOL parado; checagem de ativos estranhos inerte)
- 2026-09-28 — [[Token-state-history]] (histórico de estado das moedas; must-fix 2 do J fechado)
- 2026-09-28 — [[KB-momentum-semanal]] (H-024, momentum semanal em cripto grande)
- 2026-09-28 — [[Wallet-unrecognized-holdings]] (checagem de ativos estranhos na carteira ligada; adiar sem veredito, slots por programa)
- 2026-09-28 — [[KB-analise-grafica]] (KB-0167, análise gráfica depois do custo; candidatas C1–C3, nada registrado)

- [[T4.74-spot-desk]] — fundações, perfil, sinal, dinheiro e saídas da mesa `spot/1` (19/09)
- [[T4.77-close-atas-token2022]] — fechar ATAs cheias, extensão ao Token-2022 (19/09)
- [[T4.78-estrategia-2026-09-20]] — parecer noturno de estratégia + cooldown por mint (20/09)
- [[R65-rent-buys1m]] — recuperar rent da ATA, `buys_1m ≤ 25` (22/09)
- [[R66-pos-graduacao-pumpswap]] — custo pós-graduação na PumpSwap (22/09)
- [[R67-buys1m-oos]] — validação fora de amostra do `buys_1m` (23/09)
- [[R68-proxima-vela-pedagio]] — previsibilidade de perpétuos (KB-0150) (23/09)
- [[R69-coorte-nao-respira]] — percentil dentro da coorte (KB-0151) (23/09)
- [[R70-loaders-lab]] — carimbos/censura do Lab e vereditos H-001/002/005/006/007 (23/09)
- [[R71-identidade-mercados-spot]] — identidade dos mercados NEAR/WBTC/ORCA/XRP (23/09)
- [[R72-oscilacao-giro]] — H-009, reservas pós-gatilho (KB-0152) (23/09)
- [[R73-maior-comprador]] — H-010, concentração do maior comprador (KB-0153) (23/09)
- [[R74-subir-alvo]] — H-011, subir o alvo de saída (KB-0154) (23/09)
- [[R75-equilibrio-porta]] — H-013, moeda em equilíbrio (KB-0155) (23/09)
- [[R76-despejo-em-bloco]] — H-014, despejo em bloco (KB-0156) (23/09)
- [[R77-esperar-recuo]] — H-016, esperar o recuo (KB-0157) (23/09)
- [[Moinho-hipoteses-T4.80-T4.90]] — construção do moinho de hipóteses que sustenta R65–R81 (23/09)
- [[T4.89b-identidade-slot]] — origem inferida da identidade quando o slot é posterior à criação (23/09)
- [[T4.91-recuo-v1]] — braço de papel `recuo_v1/1` para a H-017 (23/09)
- [[Pedigree-timeout-indice]] — índice do timeout de pedigree por minuto (24/09)
- [[R78-recompra-bundle]] — H-015/H-018, recompra e bundle (KB-0158) (25/09)
- [[T4.92-ficha-diaria]] — ficha diária automática com campos Dataview (25/09)
- [[T4.93-obsidian-first]] — portão "Obsidian primeiro" nas ferramentas de mudança (25/09)
- [[T4.94-mint-busy-superseded]] — recusa durável de proposta com mint ocupado (25/09)
- [[T4.95-recuo-ctrl]] — braço de controle `recuo_ctrl_v1/1` (25/09)
- [[Lab-recuo-metricas]] — métricas e estados sem resultado do braço de recuo (25/09)
- [[Meme-refused-probe-apostrophe-guard]] — guarda de apóstrofo nas razões de recusa (23/09)
- [[R80-link-reciclado]] — H-020, link reciclado + coleta REST do pump.fun (26/09)
- [[R81-grafico-5min]] — H-021, gráfico de 5 minutos não existe na porta (26/09)
- [[R82-recuo-controle]] — H-017, o recuo pequeno empata com comprar na hora (KB-0162) (27/09)
- [[R83-maxima-24h]] — H-023, perto da máxima de 24 h não separa os sinais do Lab de cripto (KB-0163) (28/09)
- [[R84-momentum-semanal]] — H-024, evitar as moedas em queda de 14 dias não bate a cesta; sobrevivência auditada em 153 cópias históricas (KB-0166) (28/09)
- [[T4.96-escopo-teste-pequeno]] — corte do débito do escopo, diagnóstico da parada de 26/09 (26/09)
- [[T4.96b-scope-debit]] — corrida SigningLocked/admitted_orphan_expired (26/09)
- [[T4.97b-identity-breaker]] — disjuntor da identidade por mint (26/09)
- [[Confluencia-market-events]] — desenho de confluência de eventos de mercado (23/09)
- [[EXP-M26-design-R1]] — opinião pontual de database-architect sobre o desenho do EXP-M26 (26/09)
