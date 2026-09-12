---
tags: [knowledge, nota, plantao, meme, pumpfun, estatistica]
tema: memecoin / pump.fun / validação fora da janela / regime
fonte: Kamat, RED-PUMP-2026-v1 v1.5 — pacote de reprodutibilidade pré-registrado (Zenodo 10.5281/zenodo.22286914, 06/09/2026; concept DOI 10.5281/zenodo.20633486), companheiro do preprint arXiv 2607.02823
fonte_url: https://zenodo.org/api/records?q=conceptdoi:"10.5281/zenodo.20633486"
lido_em: 2026-09-12
evidencia: descrição oficial do depósito (metadados da API do Zenodo) de um estudo pré-registrado com bootstrap por blocos de dia, sem revisão por pares; lida em 2026-09-12 05:14–05:16 BRT; o pacote (348,53 MB) não foi baixado nem executado aqui; nenhuma medição própria
hipotese_testavel: sim
astra: pendente
status: vivo
owner: sexta-feira
updated: 2026-09-12
confiança: "?"
---

# O modelo pré-registrado que morreu no holdout (pump.fun, mai–jun/2026)

> Nota do plantão T4.64 (run 4, lane 4). Rascunho com URLs e horas: `.claude/state/plantao-meme/2026-09-12-0509-lane4.md`.
> `confiança: "?"` porque a evidência é a descrição do depósito de um preprint não revisado, sem replicação aqui.

## O que afirma

Na mesma plataforma, com o mesmo coletor e a mesma definição de desfecho, um modelo logístico **pré-registrado** de
associação com a graduação discriminou bem nos 15 dias de desenvolvimento (**AUROC 0,8594**) e ficou **indistinguível do
acaso** nos 14 dias seguintes (**AUROC 0,4642**, intervalo percentil [0,4112; 0,5196], que contém 0,5), com a calibração
destruída ("slope 0,013, intercept +2,816"). Das nove *stability gates* automáticas do pipeline corrigido, duas passam,
seis falham e uma não é avaliável. A versão v1.5 do pacote **substitui** a v1.3 (DOI 10.5281/zenodo.21908375) por meio de
um aviso de correção e retirada do preprint depositado no próprio pacote (`11_corrigendum/…`).

Denominadores do mesmo depósito: 860 213 lançamentos gravados entre 2026-05-08 e 2026-06-10 por um coletor **off-chain**
(polling da API, primeira detecção); coorte primária de **749 816 mints únicos** — **1 597 GRADUATED, 748 219 TIMEOUT**,
ou seja **0,213 %** (cálculo meu). O preprint v3 publica 0,198 % sobre 832 941: o denominador mudou entre versões, o que
por si só ilustra [[KB-0091-pump-fun-as-taxas-base-e-seus-denominadores]].

## Onde foi mostrado

pump.fun (Solana), 34 dias de maio–junho de 2026, desfecho "graduou em 24 h" segundo o classificador terminal do coletor
(auditado no próprio pacote). Features do modelo: presença de Telegram/X/site na metadata e mcap inicial (as do preprint
2607.02823, cujos *hazard ratios* — Telegram 5,40, log(1+mcap) 4,51 — vinham desse mesmo dado). Sem custos, sem execução:
é associação com graduação, não retorno.

## Como mediríamos aqui

O Meme Radar já coleta os mesmos campos no minuto 0 (F-D1..F-D6 do catálogo `docs/plans/T4-FEATURES.md`, `twitter`,
`telegram`, `website`, `usd_market_cap` inicial) com `observed_at`/`received_at` (M-D1). A réplica é barata: ajustar o
mesmo conjunto (regressão logística, sem seleção de features) em um bloco de 15 dias dos nossos dados e avaliar AUROC e
calibração nos 14 dias seguintes, com IC95 % por bootstrap de blocos de dia, repetindo em três janelas pré-fixadas.

## Hipótese testável no Lab

**M-P21** (falseamento, [[Hipoteses-do-plantao]]): "features de presença social + log(mcap inicial) da metadata, ajustadas
em 15 dias, têm AUROC ≤ 0,55 para conclusão em 24 h nos 14 dias seguintes". Refutação: IC95 % do AUROC de validação
inteiramente acima de 0,60 em 2 das 3 janelas. Consequência prática: enquanto M-P21 não for refutada, nenhum score baseado
em presença social entra no funil como filtro; entra só como estrato descritivo.

## Por que pode falhar

- O colapso pode ser do **coletor** (o pacote audita o classificador terminal, mas o polling censura graduações > 6 min —
  ver KB-0091), não do sinal; a nossa coleta por WS + reconciliação on-chain muda a população.
- Regime: maio–junho de 2026 (após a queda de taxa-base para ~0,2 %) pode não representar setembro; por isso as três janelas.
- Um modelo linear pode falhar onde uma interação (Mayhem × social, hora × social) não falharia — mas isso já seria
  outra hipótese, pré-registrada à parte, não um ajuste após ver o resultado.
- Nada disso mede retorno líquido: mesmo uma feature que discrimine graduação não paga a conta de
  [[KB-0076-por-que-perdemos-2026-09-08]].

## Astra (12/09/2026 05:30 BRT)

Parecer `.claude/state/astra-review-plantao-meme-20260912-0509.md`: **limitar a conclusão ao modelo, à coorte e à validação relatados**
— um modelo logístico falhar num holdout de 14 dias não demonstra que features sociais falham universalmente; M-P21 é a primeira
hipótese que ela testaria entre as novas, com a ressalva de separar refutação estatística (IC acima de 0,55) de relevância operacional
(0,60) e de esperar os rótulos de 24 h maturarem antes de ajustar. `astra: pendente` até o parecer específico sobre esta nota.
